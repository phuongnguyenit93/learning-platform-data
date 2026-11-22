# WINDOW clause và tái sử dụng định nghĩa cửa sổ

Khi một truy vấn cần nhiều hàm cửa sổ trên cùng cách phân vùng và sắp xếp, việc lặp lại toàn bộ `PARTITION BY` và `ORDER BY` trong từng `OVER (...)` khiến SQL dài và dễ lệch logic. MySQL cho phép đặt tên cho một định nghĩa cửa sổ trong mệnh đề `WINDOW`, sau đó tham chiếu tên đó ở nhiều hàm bằng `OVER window_name`.

Named window giúp gom quy tắc phân vùng, thứ tự và đôi khi cả frame vào một định nghĩa dùng chung. Nó làm truy vấn nhất quán và dễ bảo trì hơn. Tên cửa sổ chỉ có phạm vi trong query block chứa `WINDOW`; nó không phải bảng, biến session hay cache dữ liệu. Việc tái sử dụng định nghĩa cũng không tự bảo đảm optimizer chỉ sắp xếp dữ liệu một lần, vì kế hoạch vật lý vẫn do MySQL quyết định.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Hàm cửa sổ**, bài này tập trung vào cú pháp `WINDOW`, phạm vi tên và cách tái sử dụng định nghĩa cửa sổ trong nhiều hàm phân tích.

## 1. Named window giải quyết vấn đề gì?

Giả sử cần đánh số nhân viên, xếp hạng lương và tính tổng lương lũy kế trong từng phòng ban. Các hàm cùng phân vùng theo phòng ban, nhưng có thể cần thứ tự khác nhau: xếp hạng chỉ theo lương để giữ đồng hạng; đánh số và tính lũy kế cần thêm khóa duy nhất để có thứ tự từng hàng ổn định:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS row_num,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS salary_rank,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees;
```

Hai quy tắc sắp xếp gần nhau nhưng có mục đích khác nhau. `RANK()` chỉ xếp theo lương để nhân viên bằng lương được đồng hạng. `ROW_NUMBER()` và tổng lũy kế dùng thêm `employee_id` để xác định thứ tự từng hàng một cách ổn định. Nếu đưa `employee_id` vào cửa sổ của `RANK()`, các hàng có lương bằng nhau sẽ không còn là peer rows.

Named window giúp đặt tên cho cả hai quy tắc và tái sử dụng đúng nơi:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_department_salary_row AS row_num,
    RANK() OVER w_department_salary_rank AS salary_rank,
    SUM(salary) OVER (
        w_department_salary_row
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees
WINDOW
    w_department_salary_rank AS (
        PARTITION BY department_id
        ORDER BY salary DESC
    ),
    w_department_salary_row AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    );
```

`w_department_salary_rank` giữ các hàng có cùng lương ở cùng một hạng. `w_department_salary_row` thêm khóa duy nhất để xác định thứ tự cho `ROW_NUMBER()` và frame `ROWS` của tổng lũy kế. Chỉ dùng chung một named window khi các hàm thật sự cần cùng partition, order và ngữ nghĩa peer rows.

## 2. Cú pháp và vị trí của WINDOW clause

Cú pháp tổng quát trong một câu `SELECT`:

```sql
SELECT
    select_list
FROM table_references
WHERE where_condition
GROUP BY group_list
HAVING having_condition
WINDOW
    window_name_1 AS (window_specification_1),
    window_name_2 AS (window_specification_2)
ORDER BY order_list
LIMIT row_count;
```

Mệnh đề `WINDOW` nằm sau `HAVING` và trước `ORDER BY`. Những phần không cần thiết có thể được bỏ qua, nhưng thứ tự cú pháp vẫn phải được giữ.

Một định nghĩa cửa sổ có dạng:

```sql
WINDOW window_name AS (
    [PARTITION BY partition_expression [, ...]]
    [ORDER BY order_expression [ASC | DESC] [, ...]]
    [frame_clause]
)
```

Ví dụ:

```sql
SELECT
    customer_id,
    order_id,
    order_date,
    total_amount,
    ROW_NUMBER() OVER w_customer_date AS order_sequence
FROM orders
WINDOW w_customer_date AS (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
);
```

Tên `w_customer_date` được tham chiếu bằng `OVER w_customer_date`. Đây là tên định nghĩa cửa sổ, không phải alias của bảng trong `FROM`.

## 3. Phạm vi của tên cửa sổ

Named window chỉ có hiệu lực trong query block có khai báo `WINDOW`. Nó có thể được dùng bởi các biểu thức cửa sổ trong select list và những vị trí truy vấn hỗ trợ window function của query block đó.

```sql
SELECT
    employee_id,
    ROW_NUMBER() OVER w AS row_num
FROM employees
WINDOW w AS (PARTITION BY department_id ORDER BY employee_id);
```

Sau khi câu lệnh kết thúc, tên `w` không còn tồn tại. Câu lệnh độc lập sau không thể sử dụng tên đó:

```sql
-- Lỗi: w không được khai báo trong query block này.
SELECT employee_id, ROW_NUMBER() OVER w
FROM employees;
```

### 3.1. Mỗi query block có WINDOW clause riêng

CTE, derived table và subquery có thể chứa query block riêng. Nếu hàm cửa sổ được tính bên trong CTE, tên cửa sổ phải được khai báo trong chính `SELECT` của CTE:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER w_dept_salary AS row_num
    FROM employees
    WINDOW w_dept_salary AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    )
)
SELECT employee_id, department_id, salary, row_num
FROM ranked_employees
WHERE row_num <= 3;
```

Truy vấn ngoài đọc cột `row_num` đã được CTE tạo ra. Nó không nhìn thấy tên `w_dept_salary` ở bên trong CTE và không thể viết `OVER w_dept_salary` nếu không khai báo một named window khác trong query block ngoài.

Tương tự, một subquery có thể định nghĩa tên cửa sổ riêng. Tên đó không tự truyền ra query block bao quanh.

### 3.2. Cùng một tên có thể được dùng độc lập ở query block khác

Hai query block khác nhau có thể cùng khai báo tên `w` mà không có nghĩa chúng dùng chung định nghĩa. Mỗi tên được giải quyết trong phạm vi query block tương ứng.

```sql
WITH per_department AS (
    SELECT
        employee_id,
        department_id,
        ROW_NUMBER() OVER w AS department_row
    FROM employees
    WINDOW w AS (
        PARTITION BY department_id
        ORDER BY employee_id
    )
)
SELECT
    employee_id,
    department_id,
    RANK() OVER w AS global_rank
FROM per_department
WINDOW w AS (ORDER BY employee_id);
```

CTE có `w` riêng để đánh số trong từng phòng ban. Query ngoài cũng có `w`, nhưng định nghĩa của nó sắp xếp toàn bộ kết quả theo `employee_id`. Hai định nghĩa không liên quan đến nhau.

## 4. Tái sử dụng một định nghĩa trong nhiều window function

Named window hữu ích khi nhiều hàm cần dùng lại một hoặc nhiều quy tắc partition/order:

```sql
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount,
    ROW_NUMBER() OVER w_customer_sequence AS row_num,
    RANK() OVER w_customer_date AS date_rank,
    DENSE_RANK() OVER w_customer_date AS dense_date_rank,
    LAG(total_amount) OVER w_customer_sequence AS previous_amount,
    LEAD(total_amount) OVER w_customer_sequence AS next_amount
FROM orders
WINDOW
    w_customer_date AS (
        PARTITION BY customer_id
        ORDER BY order_date
    ),
    w_customer_sequence AS (
        PARTITION BY customer_id
        ORDER BY order_date, order_id
    );
```

Các hàm dùng hai thứ tự có chủ đích trong từng khách hàng:

- `RANK()` và `DENSE_RANK()` chỉ sắp xếp theo `order_date`, nên các đơn cùng ngày được đồng hạng.
- `ROW_NUMBER()` cấp số thứ tự riêng cho mỗi hàng theo `order_date, order_id`.
- `LAG()` đọc giá trị ở hàng trước và `LEAD()` đọc giá trị ở hàng sau theo thứ tự xác định có tie-breaker.

Named window giúp các hàm có cùng quy tắc dùng chung định nghĩa. Khi ngữ nghĩa peer rows khác nhau, hãy tạo định nghĩa riêng thay vì ép mọi hàm vào một thứ tự duy nhất.

## 5. Khai báo nhiều named window trong cùng một WINDOW clause

Một query block có thể định nghĩa nhiều cửa sổ, phân cách bằng dấu phẩy:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    hired_at,
    ROW_NUMBER() OVER w_department AS department_sequence,
    RANK() OVER w_salary AS salary_rank,
    ROW_NUMBER() OVER w_hire_date AS hire_sequence
FROM employees
WINDOW
    w_department AS (
        PARTITION BY department_id
    ),
    w_salary AS (
        PARTITION BY department_id
        ORDER BY salary DESC
    ),
    w_hire_date AS (
        PARTITION BY department_id
        ORDER BY hired_at, employee_id
    );
```

Ba định nghĩa phục vụ ba cách phân tích:

- `w_department`: chỉ chia nhóm theo phòng ban, không chỉ định thứ tự.
- `w_salary`: xếp theo lương giảm dần trong từng phòng.
- `w_hire_date`: xếp theo thời điểm nhận việc trong từng phòng.

Không ép mọi hàm dùng một named window nếu yêu cầu phân tích khác nhau. Hãy tạo tên riêng thể hiện rõ khác biệt của partition, order hoặc frame.

## 6. Kế thừa định nghĩa cửa sổ

MySQL cho phép một named window tham chiếu một named window đã khai báo trước đó. Cách này giúp tạo một định nghĩa cơ sở rồi bổ sung phần còn thiếu.

Ví dụ, tạo cửa sổ cơ sở chỉ có partition, sau đó thêm thứ tự:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_department_salary AS salary_sequence,
    COUNT(*) OVER w_department AS department_size
FROM employees
WINDOW
    w_department AS (
        PARTITION BY department_id
    ),
    w_department_salary AS (
        w_department
        ORDER BY salary DESC, employee_id
    );
```

`w_department_salary` kế thừa `PARTITION BY department_id` từ `w_department` và bổ sung `ORDER BY`. CTE/window sau chỉ được tham chiếu named window đã định nghĩa trước đó trong cùng `WINDOW` clause.

### 6.1. Quy tắc khi kế thừa

Khi định nghĩa mới tham chiếu một named window khác:

- Window được tham chiếu phải được khai báo trước trong `WINDOW` clause.
- Không thể khai báo lại hoặc ghi đè một thành phần đã có trong window cơ sở.
- Nếu window cơ sở đã có `PARTITION BY`, window kế thừa không thể thêm một `PARTITION BY` khác.
- Nếu window cơ sở đã có `ORDER BY`, window kế thừa không thể thay bằng một `ORDER BY` khác.
- Frame chỉ nên được khai báo ở một tầng phù hợp; không khai báo frame hai lần cho cùng định nghĩa kế thừa.

Mẫu kế thừa dễ kiểm soát là: window cơ sở khai báo `PARTITION BY`; window con thêm `ORDER BY`; hàm cụ thể bổ sung frame nếu cần.

### 6.2. Tham chiếu phía trước không hợp lệ

Ví dụ sau không hợp lệ vì `w_department` tham chiếu `w_base` được khai báo sau:

```sql
SELECT employee_id, ROW_NUMBER() OVER w_department
FROM employees
WINDOW
    w_department AS (w_base ORDER BY employee_id),
    w_base AS (PARTITION BY department_id);
```

Đổi thứ tự khai báo:

```sql
SELECT employee_id, ROW_NUMBER() OVER w_department
FROM employees
WINDOW
    w_base AS (PARTITION BY department_id),
    w_department AS (w_base ORDER BY employee_id);
```

Hãy xem các định nghĩa window theo thứ tự phụ thuộc như một danh sách có hướng: định nghĩa cơ sở trước, định nghĩa mở rộng sau.

## 7. Bổ sung frame khi sử dụng named window

Một named window có thể định nghĩa `PARTITION BY` và `ORDER BY`, rồi một hàm aggregate bổ sung frame khi tham chiếu:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    SUM(salary) OVER (
        w_department_salary
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees
WINDOW w_department_salary AS (
    PARTITION BY department_id
    ORDER BY salary, employee_id
);
```

Frame quy định tập hàng bên trong partition mà hàm cửa sổ đang xử lý tại vị trí hiện tại. Ở ví dụ này, tổng bắt đầu từ hàng đầu tiên của phòng ban đến hàng hiện tại theo thứ tự lương và mã nhân viên.

### 7.1. ROWS và RANGE

MySQL hỗ trợ frame theo `ROWS` và `RANGE`:

- `ROWS` xác định phạm vi theo số hàng vật lý trước/sau vị trí hiện tại trong thứ tự cửa sổ.
- `RANGE` xác định phạm vi theo giá trị của biểu thức `ORDER BY`; các hàng đồng giá trị có thể cùng thuộc frame.

Ví dụ frame lũy kế theo hàng:

```sql
SUM(total_amount) OVER (
    w_customer_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Ví dụ frame lũy kế theo phạm vi giá trị với `RANGE`:

```sql
SUM(total_amount) OVER (
    w_customer_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Nếu nhiều hàng có cùng giá trị `ORDER BY`, `RANGE` có thể đưa tất cả hàng đồng hạng vào frame hiện tại, còn `ROWS` tiến từng hàng theo thứ tự. Nếu cần kết quả theo từng hàng một cách xác định, hãy dùng `ROWS` và thêm tie-breaker duy nhất vào `ORDER BY`.

### 7.2. Frame mặc định có thể làm kết quả khác dự kiến

Với aggregate window function, nếu có `ORDER BY` nhưng không chỉ định frame, MySQL mặc định dùng frame tương đương:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Nếu không có `ORDER BY`, frame mặc định bao phủ toàn bộ partition. Vì vậy, hai biểu thức dưới đây không nhất thiết có cùng ý nghĩa:

```sql
SUM(total_amount) OVER w_customer_date
```

```sql
SUM(total_amount) OVER (
    w_customer_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

Biểu thức đầu thường là tổng lũy kế theo frame mặc định có `ORDER BY`; biểu thức thứ hai là tổng toàn partition cho mỗi hàng. Khi yêu cầu nghiệp vụ là tổng toàn nhóm, hãy bỏ `ORDER BY` ở định nghĩa dùng cho tổng toàn nhóm hoặc khai báo frame toàn partition tường minh.

### 7.3. LAST_VALUE và frame toàn partition

`LAST_VALUE()` trả về giá trị ở hàng cuối của frame hiện tại, không mặc nhiên là hàng cuối của toàn partition. Nếu muốn giá trị cuối của toàn khách hàng theo ngày, cần mở frame đến cuối partition:

```sql
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount,
    LAST_VALUE(total_amount) OVER (
        w_customer_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS final_order_amount
FROM orders
WINDOW w_customer_date AS (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
);
```

Ở đây, `order_id` làm tie-breaker nếu nhiều đơn cùng ngày. Frame được mở đến `UNBOUNDED FOLLOWING` để hàng cuối là hàng cuối toàn partition.

## 8. ORDER BY trong named window khác ORDER BY cuối truy vấn

`ORDER BY` bên trong định nghĩa cửa sổ xác định thứ tự dùng để tính window function. Nó không đảm bảo thứ tự hàng được trả về cho client.

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_salary AS salary_sequence
FROM employees
WINDOW w_salary AS (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
ORDER BY employee_id;
```

Hàm `ROW_NUMBER()` đánh số theo lương giảm dần trong từng phòng ban, nhưng kết quả cuối được sắp xếp theo `employee_id`. Nếu cần hiển thị theo thứ tự lương, phải viết `ORDER BY department_id, salary DESC, employee_id` ở cuối câu lệnh.

Đừng bỏ `ORDER BY` cuối cùng nếu ứng dụng cần thứ tự ổn định, đặc biệt khi phân trang.

## 9. Named window và GROUP BY

Window function hoạt động trên các hàng của query result sau các bước lọc và grouping logic của query block. `GROUP BY` làm giảm số hàng thành một hàng cho mỗi nhóm; window function tính giá trị trên các hàng còn lại mà không tự làm mất từng hàng đó.

Ví dụ tổng doanh thu theo khách hàng, sau đó xếp hạng khách hàng:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    revenue,
    RANK() OVER w_revenue AS revenue_rank
FROM customer_totals
WINDOW w_revenue AS (ORDER BY revenue DESC);
```

CTE `customer_totals` tạo một hàng mỗi khách hàng. Named window `w_revenue` xếp hạng các hàng tổng hợp đó. Đây là hai bước có grain khác nhau: aggregate tạo tập kết quả theo khách hàng, window function phân tích thứ hạng trên tập kết quả ấy.

## 10. Không dùng named window trực tiếp trong WHERE

Window function được tính sau giai đoạn `WHERE` của cùng query block. Vì vậy, không thể lọc trực tiếp theo alias window function trong `WHERE` cùng cấp:

```sql
-- Không hợp lệ: WHERE không thể lọc kết quả window function cùng query block.
SELECT
    employee_id,
    ROW_NUMBER() OVER w_salary AS row_num
FROM employees
WHERE row_num <= 3
WINDOW w_salary AS (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
);
```

Đưa bước tính window vào CTE hoặc derived table rồi lọc ở query block bên ngoài:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER w_salary AS row_num
    FROM employees
    WINDOW w_salary AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    )
)
SELECT employee_id, department_id, salary, row_num
FROM ranked_employees
WHERE row_num <= 3
ORDER BY department_id, row_num;
```

Named window chỉ có phạm vi trong CTE. Truy vấn ngoài dùng cột `row_num`, không dùng lại tên `w_salary` ở trong CTE.

## 11. Khi nào nên dùng một window, nhiều window hoặc kế thừa?

| Tình huống | Cách tổ chức |
|---|---|
| Nhiều hàm có cùng partition/order | Một named window dùng chung. |
| Cùng partition nhưng thứ tự khác | Nhiều named window riêng. |
| Cùng partition, một số hàm có order còn hàm khác không | Window cơ sở có partition, window con bổ sung order. |
| Cùng partition/order nhưng frame khác | Dùng named window cơ sở rồi bổ sung frame ở từng `OVER (...)`, hoặc khai báo định nghĩa riêng nếu rõ hơn. |
| Chỉ một hàm cửa sổ đơn giản | Viết trực tiếp `OVER (...)` có thể ngắn và dễ đọc hơn. |
| Cần dùng định nghĩa ở câu lệnh khác | Khai báo lại trong query block mới; named window không tồn tại xuyên câu lệnh. |

Named window có ích khi nó làm rõ một quy tắc dùng chung. Nếu tạo quá nhiều tên mà mỗi tên chỉ được dùng một lần và không giúp giải thích logic, truy vấn có thể trở nên khó đọc hơn.

## 12. Ví dụ báo cáo hoàn chỉnh: phân tích nhân viên theo phòng ban

Yêu cầu: với mỗi nhân viên, hiển thị lương, thứ hạng trong phòng, số thứ tự theo ngày nhận việc, lương lũy kế theo thứ tự lương và mức lương cao nhất trong phòng.

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    hired_at,
    RANK() OVER w_salary_rank AS salary_rank,
    ROW_NUMBER() OVER w_hire AS hire_sequence,
    SUM(salary) OVER (
        w_salary_sequence
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary,
    MAX(salary) OVER w_department AS department_max_salary
FROM employees
WINDOW
    w_department AS (
        PARTITION BY department_id
    ),
    w_salary_rank AS (
        w_department
        ORDER BY salary DESC
    ),
    w_salary_sequence AS (
        w_department
        ORDER BY salary DESC, employee_id
    ),
    w_hire AS (
        w_department
        ORDER BY hired_at, employee_id
    )
ORDER BY department_id, salary DESC, employee_id;
```

Truy vấn có bốn named window:

- `w_department` là định nghĩa cơ sở, chia nhân viên theo phòng ban.
- `w_salary_rank` kế thừa partition và xếp theo lương giảm dần; nhân viên bằng lương được đồng hạng.
- `w_salary_sequence` kế thừa partition và thêm `employee_id` để xác định thứ tự từng hàng cho tổng lũy kế.
- `w_hire` kế thừa partition và thêm thứ tự ngày nhận việc.

Các hàm dùng đúng định nghĩa theo yêu cầu. `MAX(salary) OVER w_department` không có `ORDER BY`, nên mỗi hàng nhận mức lương cao nhất của toàn phòng. `SUM()` dùng frame `ROWS` từ đầu partition đến hàng hiện tại theo `w_salary_sequence`.

Nếu `department_id` có thể `NULL`, tất cả nhân viên chưa gán phòng sẽ thuộc cùng một partition `NULL`. Nếu nghiệp vụ muốn xử lý nhóm này khác, hãy phân loại rõ bằng biểu thức hoặc lọc trước trong query block.

## 13. Phiên bản MySQL và giới hạn hỗ trợ

Window functions và named `WINDOW` clause được hỗ trợ trong MySQL 8.0. MySQL 5.7 không hỗ trợ cú pháp này; truy vấn cần chạy trên MySQL 5.7 phải được thiết kế lại bằng subquery, self-join hoặc kỹ thuật phù hợp với phiên bản đó.

Trước khi triển khai:

```sql
SELECT VERSION() AS mysql_version;
```

Không chỉ kiểm tra phiên bản trên máy phát triển. Hãy xác nhận phiên bản server mà ứng dụng, môi trường kiểm thử và production thực sự kết nối.

## 14. Hiệu năng và EXPLAIN

Named window giúp tái sử dụng định nghĩa về mặt SQL, nhưng không phải cam kết hiệu năng. Window function có thể cần sắp xếp các hàng theo partition và order. Với tập dữ liệu lớn, sort hoặc materialization có thể tiêu tốn CPU, bộ nhớ và temporary storage.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT
    employee_id,
    department_id,
    salary,
    RANK() OVER w_salary_rank AS salary_rank,
    SUM(salary) OVER (
        w_salary_sequence
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees
WINDOW
    w_salary_rank AS (
        PARTITION BY department_id
        ORDER BY salary DESC
    ),
    w_salary_sequence AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    );
```

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` có thể cung cấp số hàng và thời gian thực tế khi thực thi truy vấn đọc:

```sql
EXPLAIN ANALYZE
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_salary AS row_num
FROM employees
WINDOW w_salary AS (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
);
```

Một số lưu ý:

- Index có thứ tự cột phù hợp với `PARTITION BY` và `ORDER BY` có thể giúp truy cập dữ liệu, nhưng optimizer không phải lúc nào cũng loại bỏ được bước sort.
- Index ghép `(department_id, salary, employee_id)` có thể là ứng viên cho truy vấn trên; cần cân nhắc hướng sắp xếp, tính chọn lọc và workload ghi.
- Nhiều named window có thứ tự khác nhau có thể cần các bước sắp xếp khác nhau.
- Dùng chung một named window không đảm bảo MySQL chỉ thực hiện một lần sort vật lý.
- Lọc hàng trong `WHERE` trước khi window function được tính có thể giảm tập dữ liệu, nhưng chỉ lọc nếu đúng nghiệp vụ.
- Không loại hàng trước window nếu hàng đó cần tham gia xếp hạng, tổng lũy kế hoặc frame.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Unknown window 'w'` | Tên chưa khai báo hoặc nằm ngoài query block | Khai báo `WINDOW w AS (...)` trong đúng SELECT. |
| CTE/subquery không thấy tên cửa sổ bên ngoài | Named window không có phạm vi xuyên query block | Khai báo lại trong query block cần dùng. |
| Window kế thừa tên khai báo phía sau | Forward reference trong WINDOW clause | Đặt window cơ sở trước window con. |
| Không thể thêm PARTITION/ORDER vào window kế thừa | Thành phần đó đã được khai báo ở window cơ sở | Chọn window cơ sở phù hợp hoặc tạo định nghĩa riêng. |
| Hai hàm trả kết quả khác nhau dù nghĩ cùng thứ tự | Một hàm dùng định nghĩa khác hoặc frame khác | Dùng chung named window và kiểm tra frame của từng hàm. |
| Tổng lũy kế tăng theo nhóm giá trị đồng hạng | Frame mặc định RANGE gom peer rows | Dùng `ROWS` nếu cần tiến từng hàng và thêm tie-breaker. |
| LAST_VALUE trả giá trị hiện tại thay vì cuối partition | Frame mặc định kết thúc ở current row | Mở frame đến `UNBOUNDED FOLLOWING`. |
| Kết quả hiển thị không theo thứ tự window | Nhầm ORDER BY trong OVER với ORDER BY cuối | Thêm ORDER BY ở cuối SELECT. |
| WHERE không lọc được row_number | Window function chưa có ở giai đoạn WHERE | Tính trong CTE/derived table rồi lọc ở query ngoài. |
| Truy vấn vẫn chậm dù dùng named window | Named window chỉ tái sử dụng định nghĩa logic | Kiểm tra sort, số hàng, index và EXPLAIN. |

## 16. Quy trình thiết kế WINDOW clause

1. **Xác định grain của hàng đầu vào.** Window function phân tích các hàng hiện có; xác định truy vấn đã lọc hoặc aggregate trước đó chưa.
2. **Xác định partition.** Hàng nào phải được phân tích cùng nhóm?
3. **Xác định order.** Thứ tự nào quyết định rank, lag/lead hoặc running total?
4. **Bổ sung tie-breaker.** Nếu cần thứ tự duy nhất, thêm khóa duy nhất như primary key.
5. **Xác định frame.** Hàm cần toàn partition, lũy kế theo hàng hay phạm vi giá trị?
6. **Tạo named window cơ sở.** Đặt tên cho partition/order được nhiều hàm dùng chung.
7. **Tạo window kế thừa nếu cần.** Khai báo cơ sở trước, chỉ bổ sung thành phần chưa có.
8. **Dùng OVER nhất quán.** Tham chiếu named window cho các hàm có cùng quy tắc.
9. **Kiểm tra phạm vi.** Nếu chuyển phép tính vào CTE/subquery, khai báo window ở query block đó.
10. **Sắp xếp kết quả cuối.** Dùng ORDER BY bên ngoài nếu client cần thứ tự cụ thể.
11. **Kiểm tra hiệu năng.** Dùng EXPLAIN/EXPLAIN ANALYZE và đánh giá index, sort, số hàng.

## 17. Bài tập thực hành

### Bài tập 1: Tái sử dụng một named window

Viết truy vấn đánh số và xếp hạng đơn hàng theo từng khách hàng; xác định riêng thứ tự dùng để đánh số từng hàng và thứ tự dùng để xếp hạng theo ngày.

**Yêu cầu:** dùng `w_customer_sequence` cho `ROW_NUMBER()`, `LAG()` và `LEAD()` với thứ tự `order_date, order_id`; dùng `w_customer_date` cho `RANK()` nếu các đơn cùng ngày cần đồng hạng. Giải thích vì sao hai hàm cần hai định nghĩa khác nhau.

### Bài tập 2: Khai báo nhiều named window

Với bảng nhân viên, tạo các window `w_department`, `w_salary` và `w_hire`.

**Yêu cầu:** dùng `PARTITION BY department_id` cho cả ba; hai window sau có thứ tự khác nhau.

### Bài tập 3: Kế thừa định nghĩa

Tạo window cơ sở chỉ có `PARTITION BY`, rồi khai báo window con thêm `ORDER BY`.

**Yêu cầu:** thử đảo thứ tự khai báo để quan sát forward reference; thử ghi đè PARTITION BY đã có và giải thích vì sao không hợp lệ.

### Bài tập 4: Frame lũy kế

Dùng một named window có partition/order rồi tính `SUM()` với `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

**Yêu cầu:** tạo hai hàng có cùng giá trị sắp xếp, so sánh `ROWS` và `RANGE`.

### Bài tập 5: LAST_VALUE

Tìm số tiền đơn cuối cùng của từng khách hàng bằng `LAST_VALUE()`.

**Yêu cầu:** chạy với frame mặc định rồi mở frame đến `UNBOUNDED FOLLOWING`; giải thích sự khác nhau.

### Bài tập 6: Phạm vi trong CTE

Đưa `ROW_NUMBER() OVER w` vào một CTE rồi lọc `row_num <= 3` ở truy vấn ngoài.

**Yêu cầu:** thử tham chiếu `w` ở truy vấn ngoài mà không khai báo lại và giải thích lỗi phạm vi.

### Bài tập 7: WINDOW và ORDER BY cuối

Xếp hạng nhân viên theo lương trong phòng ban nhưng sắp xếp kết quả cuối theo mã nhân viên.

**Yêu cầu:** giải thích vì sao thứ tự trong `OVER` không quyết định thứ tự hiển thị.

### Bài tập 8: EXPLAIN

Viết truy vấn dùng hai named window có thứ tự khác nhau và chạy `EXPLAIN`.

**Yêu cầu:** quan sát các bước sort/temporary nếu có; giải thích vì sao named window không bảo đảm chỉ một lần sắp xếp.

## 18. Checklist review

- [ ] Named window được khai báo trong đúng query block.
- [ ] `WINDOW` nằm sau HAVING và trước ORDER BY.
- [ ] Tên window rõ nghĩa và không bị nhầm với alias bảng/CTE.
- [ ] Các hàm dùng chung partition/order tham chiếu cùng định nghĩa.
- [ ] Nhiều named window được phân tách bằng dấu phẩy.
- [ ] Window kế thừa chỉ tham chiếu định nghĩa đã khai báo trước.
- [ ] Không ghi đè PARTITION BY/ORDER BY đã có trong window cơ sở.
- [ ] Frame được chọn rõ ràng khi aggregate cần ngữ nghĩa cụ thể.
- [ ] ROWS và RANGE được chọn theo cách xử lý peer rows.
- [ ] Có tie-breaker nếu cần thứ tự hàng duy nhất.
- [ ] Không nhầm ORDER BY trong OVER với ORDER BY cuối truy vấn.
- [ ] Window function được lọc ở query block ngoài qua CTE/derived table khi cần.
- [ ] Named window không bị kỳ vọng dùng xuyên câu lệnh hoặc query block.
- [ ] Đã kiểm tra phiên bản MySQL và kế hoạch bằng EXPLAIN.

## 19. Ghi nhớ

`WINDOW` clause cho phép đặt tên cho một định nghĩa cửa sổ rồi tái sử dụng bằng `OVER window_name`. Mệnh đề này nằm sau `HAVING` và trước `ORDER BY`; tên cửa sổ chỉ có phạm vi trong query block khai báo nó. Một query block có thể định nghĩa nhiều named window và một định nghĩa có thể kế thừa window được khai báo trước đó.

Hãy dùng window cơ sở cho `PARTITION BY`, window con để bổ sung `ORDER BY`, rồi bổ sung frame ở nơi hàm cần. Không ghi đè thành phần đã có trong window được kế thừa. Named window giúp SQL nhất quán nhưng không phải cache và không bảo đảm một lần sort vật lý. Luôn phân biệt thứ tự trong `OVER` với thứ tự kết quả cuối, chọn frame đúng và kiểm tra kế hoạch trên phiên bản MySQL thực tế.

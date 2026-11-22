# Top-N trong từng nhóm và xử lý các giá trị bằng nhau

Một báo cáo có thể cần lấy ba nhân viên có lương cao nhất ở mỗi phòng ban, năm sản phẩm bán chạy nhất trong từng danh mục hoặc các giao dịch mới nhất của mỗi tài khoản. Đây là bài toán **Top-N per group**: giới hạn số hàng trong từng nhóm, thay vì giới hạn toàn bộ kết quả.

Nếu dùng `ORDER BY ... LIMIT 3` thông thường, MySQL chỉ trả về ba hàng cho toàn truy vấn. Để lấy Top-N riêng trong từng nhóm, MySQL 8.0 cung cấp các hàm cửa sổ như `ROW_NUMBER()`, `RANK()` và `DENSE_RANK()`. Ba hàm có cách xử lý giá trị bằng nhau khác nhau, vì vậy cần chọn theo đúng quy tắc nghiệp vụ.

Trong module **DATABASE_MYSQL**, bài học này giúp xây dựng báo cáo Top-N có thể giải thích được: nhóm được xác định ra sao, “Top 3” có bao gồm đồng hạng không, khi nào cần đúng N hàng, và làm thế nào để thứ tự kết quả ổn định.

## 1. Vì sao LIMIT không giải quyết được Top-N trong từng nhóm?

Giả sử bảng `employees` có các cột `employee_id`, `department_id`, `employee_name` và `salary`. Truy vấn:

```sql
SELECT employee_id, department_id, employee_name, salary
FROM employees
ORDER BY salary DESC
LIMIT 3;
```

chỉ lấy ba nhân viên có lương cao nhất trên toàn công ty. Nó không lấy ba nhân viên ở mỗi phòng ban.

Để giải quyết Top-N per group, cần chia dữ liệu thành các nhóm bằng `PARTITION BY`, sắp xếp các hàng trong từng nhóm bằng `ORDER BY` của hàm cửa sổ, sau đó lọc theo số thứ tự hoặc thứ hạng được tính.

## 2. Dữ liệu minh họa

Tạo bảng thử nghiệm:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    employment_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    PRIMARY KEY (employee_id)
) ENGINE=InnoDB;

INSERT INTO employees
    (employee_id, department_id, employee_name, salary)
VALUES
    (101, 10, 'An',   9000.00),
    (102, 10, 'Binh', 8500.00),
    (103, 10, 'Chi',  8500.00),
    (104, 10, 'Dung', 7000.00),
    (105, 10, 'Ha',   6500.00),
    (201, 20, 'Khanh', 9500.00),
    (202, 20, 'Lan',   9200.00),
    (203, 20, 'Minh',  8800.00),
    (204, 20, 'Nga',   8800.00),
    (205, 20, 'Phuc',  7600.00);
```

Phòng ban 10 có hai nhân viên đồng lương `8500.00`; phòng ban 20 có hai nhân viên đồng lương `8800.00`. Những trường hợp đồng hạng này giúp phân biệt ba hàm xếp hạng.

## 3. PARTITION BY chia nhóm, ORDER BY xếp hạng trong nhóm

Hàm cửa sổ có thể tính số thứ tự trong từng phòng ban:

```sql
SELECT
    employee_id,
    department_id,
    employee_name,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id ASC
    ) AS row_num
FROM employees;
```

- `PARTITION BY department_id` chia các hàng thành từng phòng ban. Bộ đếm bắt đầu lại từ 1 ở mỗi phòng ban.
- `ORDER BY salary DESC` xếp lương cao trước trong mỗi phòng ban.
- `employee_id ASC` là tie-breaker duy nhất để quyết định thứ tự giữa các nhân viên có cùng lương.
- `ROW_NUMBER()` cấp một số thứ tự khác nhau cho từng hàng trong một partition.

`PARTITION BY` không làm giảm số hàng như `GROUP BY`. Mỗi nhân viên vẫn xuất hiện trong kết quả; hàm cửa sổ chỉ bổ sung giá trị tính trên các hàng liên quan.

## 4. Lọc Top-N bằng ROW_NUMBER()

Muốn lấy đúng tối đa ba nhân viên mỗi phòng ban, dùng `ROW_NUMBER()` rồi lọc ở query block bên ngoài:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id ASC
        ) AS row_num
    FROM employees
)
SELECT
    employee_id,
    department_id,
    employee_name,
    salary,
    row_num
FROM ranked_employees
WHERE row_num <= 3
ORDER BY department_id, row_num;
```

Kết quả có tối đa ba hàng cho mỗi phòng ban. Nếu hai nhân viên có cùng lương, tie-breaker `employee_id` quyết định ai đứng trước. Truy vấn luôn chọn đúng ba hàng nếu phòng ban có ít nhất ba nhân viên.

Đây là lựa chọn phù hợp khi yêu cầu có nghĩa chính xác là “không quá N hàng trong mỗi nhóm”, chẳng hạn giao diện chỉ hiển thị ba sản phẩm cho mỗi danh mục và không được vượt quá giới hạn số thẻ.

### Vì sao cần query ngoài hoặc CTE?

Không thể dùng trực tiếp alias `row_num` trong `WHERE` cùng query block:

```sql
-- Không hợp lệ: WHERE không nhìn thấy alias window function cùng cấp
SELECT
    employee_id,
    department_id,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS row_num
FROM employees
WHERE row_num <= 3;
```

`WHERE` lọc hàng đầu vào trước khi giá trị window function được tạo. Đưa phép tính vào CTE hoặc derived table rồi lọc ở query ngoài là cách viết đúng.

## 5. ROW_NUMBER, RANK và DENSE_RANK khác nhau thế nào?

Ba hàm thường được dùng để xếp hạng nhưng xử lý đồng hạng khác nhau:

| Hàm | Cách đánh số | Khi có giá trị bằng nhau | Dùng khi |
|---|---|---|---|
| `ROW_NUMBER()` | 1, 2, 3, 4, ... | Mỗi hàng nhận số riêng | Cần đúng tối đa N hàng |
| `RANK()` | 1, 2, 2, 4, ... | Cùng hạng; các hạng sau bị nhảy | Top-N vị trí và muốn giữ tất cả hàng đồng hạng ở ranh giới |
| `DENSE_RANK()` | 1, 2, 2, 3, ... | Cùng hạng; không bỏ số hạng kế tiếp | Top-N mức giá trị khác nhau, ví dụ ba mức lương cao nhất |

Ví dụ với lương giảm dần `100, 90, 90, 80`:

| Lương | `ROW_NUMBER()`* | `RANK()` | `DENSE_RANK()` |
|---:|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

*Lưu ý:* `ROW_NUMBER()` trong ví dụ minh họa cần một thứ tự phụ ổn định; số 2 và 3 giữa hai hàng lương 90 phụ thuộc tie-breaker được khai báo.

`RANK()` phản ánh vị trí của hàng trong thứ tự có đồng hạng. Sau hai hàng cùng hạng 2, hạng kế tiếp là 4. `DENSE_RANK()` đánh số các mức giá trị liên tiếp, không tạo khoảng trống.

## 6. Top-N có giữ các hàng đồng hạng ở ranh giới không?

Đây là câu hỏi nghiệp vụ cần trả lời trước khi chọn hàm.

### Yêu cầu A: đúng tối đa N hàng mỗi nhóm

Dùng `ROW_NUMBER()`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM employees
)
SELECT *
FROM ranked
WHERE rn <= 3;
```

Nếu vị trí thứ ba có nhiều người đồng lương, chỉ một số người được chọn theo tie-breaker. Kết quả không vượt quá ba hàng mỗi phòng ban.

### Yêu cầu B: lấy ba vị trí đầu và giữ toàn bộ người đồng hạng tại vị trí thứ ba

Dùng `RANK()` và chỉ xếp hạng theo tiêu chí xác định đồng hạng, ở đây là `salary`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_rank
    FROM employees
)
SELECT *
FROM ranked
WHERE salary_rank <= 3
ORDER BY department_id, salary DESC, employee_id;
```

Nếu nhiều người cùng mức lương ở vị trí thứ ba, tất cả đều được giữ. Vì thế số hàng trả về mỗi nhóm có thể lớn hơn ba.

**Không thêm `employee_id` vào `ORDER BY` bên trong `RANK()` nếu muốn người cùng lương được đồng hạng.** Nếu xếp hạng theo `(salary DESC, employee_id ASC)`, hai hàng có ID khác nhau không còn là peer và sẽ nhận hạng khác nhau. Có thể dùng `employee_id` ở `ORDER BY` ngoài cùng để sắp xếp hiển thị mà không phá quy tắc đồng hạng.

### Yêu cầu C: lấy ba mức lương cao nhất khác nhau

Dùng `DENSE_RANK()`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        DENSE_RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_level
    FROM employees
)
SELECT *
FROM ranked
WHERE salary_level <= 3
ORDER BY department_id, salary DESC, employee_id;
```

Truy vấn trả về tất cả nhân viên thuộc ba mức lương cao nhất khác nhau trong mỗi phòng ban. Nếu mức lương cao nhất có 10 nhân viên, cả 10 đều được giữ và vẫn chỉ chiếm một mức xếp hạng.

## 7. Phân biệt RANK và DENSE_RANK ở ranh giới Top-N

Với dãy lương `100, 90, 90, 80`:

- `RANK() <= 3` trả các mức `100` và `90`. Mức `80` có rank 4 nên bị loại.
- `DENSE_RANK() <= 3` trả cả `100`, `90` và `80`, vì đó là ba mức lương phân biệt đầu tiên.

Nếu dãy là `100, 100, 90, 80`:

- `RANK() <= 3` trả `100, 100, 90`; hàng `80` có rank 4.
- `DENSE_RANK() <= 3` trả cả bốn hàng, vì ba mức lương khác nhau là `100`, `90`, `80`.

Do đó, “Top 3 có ties” vẫn còn mơ hồ. Cần xác định “ba vị trí đầu” hay “ba mức giá trị đầu tiên”.

## 8. Lọc dữ liệu trước khi xếp hạng hay sau khi xếp hạng?

`WHERE` bên trong CTE được thực thi trước khi window function tính thứ hạng. `WHERE` ở truy vấn ngoài lọc kết quả đã có thứ hạng.

Ví dụ chỉ xếp hạng nhân viên đang làm việc:

```sql
UPDATE employees
SET employment_status = 'INACTIVE'
WHERE employee_id = 105;

WITH ranked_active AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM employees
    WHERE employment_status = 'ACTIVE'
)
SELECT *
FROM ranked_active
WHERE rn <= 3;
```

Nhân viên đã nghỉ việc không tham gia xếp hạng. Nếu đặt điều kiện trạng thái ở query ngoài sau khi đã tính `ROW_NUMBER()`, những nhân viên nghỉ việc vẫn chiếm vị trí trong quá trình xếp hạng; sau đó bị loại, nên mỗi phòng ban có thể còn ít hơn ba nhân viên dù vẫn có nhân viên đang làm việc xếp sau.

Hãy đặt điều kiện lọc ở đúng giai đoạn theo yêu cầu nghiệp vụ: lọc tập ứng viên trước khi xếp hạng, hoặc lọc các hàng sau khi đã xếp hạng.

## 9. Top-N khi dữ liệu có NULL

Nếu cột dùng để xếp hạng cho phép `NULL`, cần xác định vị trí của giá trị thiếu. Trong MySQL, khi sắp xếp tăng dần, `NULL` đứng trước các giá trị không NULL; khi sắp xếp giảm dần, `NULL` đứng sau các giá trị không NULL.

Nếu muốn xếp lương cao trước và đưa lương `NULL` xuống cuối một cách tường minh:

```sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary IS NULL ASC,
             salary DESC,
             employee_id ASC
)
```

Biểu thức `salary IS NULL` trả 0 cho giá trị có lương và 1 cho `NULL`; sắp xếp tăng dần đưa nhóm có lương lên trước. Nếu cột lương là `NOT NULL`, không cần phần xử lý này.

Với `RANK()` hoặc `DENSE_RANK()`, các hàng có `NULL` trong biểu thức xếp hạng có thể trở thành peer với nhau. Nếu `NULL` không phải mức giá trị nghiệp vụ hợp lệ, hãy lọc chúng trước khi xếp hạng:

```sql
FROM employees
WHERE salary IS NOT NULL
```

Không tự động coi `NULL` là 0 bằng `COALESCE(salary, 0)` trừ khi nghiệp vụ thực sự quy định lương thiếu tương đương 0; phép thay thế có thể làm thay đổi thứ hạng.

## 10. Top-N theo nhiều tiêu chí

Có thể xếp hạng theo nhiều cột. Ví dụ chọn ba sản phẩm có doanh thu cao nhất trong từng danh mục; nếu doanh thu bằng nhau, ưu tiên số lượng bán cao hơn:

```sql
WITH ranked_products AS (
    SELECT
        category_id,
        product_id,
        revenue,
        units_sold,
        ROW_NUMBER() OVER (
            PARTITION BY category_id
            ORDER BY revenue DESC,
                     units_sold DESC,
                     product_id ASC
        ) AS rn
    FROM product_sales
)
SELECT category_id, product_id, revenue, units_sold
FROM ranked_products
WHERE rn <= 3
ORDER BY category_id, revenue DESC, units_sold DESC, product_id;
```

Nếu quy tắc đồng hạng chỉ dựa vào doanh thu, hàm `RANK()` phải chỉ dùng `ORDER BY revenue DESC`; `units_sold` và `product_id` có thể được dùng trong thứ tự hiển thị ngoài cùng. Xác định rõ cột nào cấu thành một tie là điều quan trọng.

## 11. Top-N cho từng nhóm kể cả nhóm không có hàng?

Hàm cửa sổ chỉ xếp hạng những hàng hiện diện trong tập đầu vào. Nếu cần hiển thị tất cả phòng ban, kể cả phòng ban chưa có nhân viên, cần lấy danh sách phòng ban làm bảng bên trái rồi `LEFT JOIN` với kết quả Top-N:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        employee_name,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM employees
)
SELECT
    d.department_id,
    d.department_name,
    r.employee_id,
    r.employee_name,
    r.salary
FROM departments AS d
LEFT JOIN ranked_employees AS r
    ON r.department_id = d.department_id
   AND r.rn <= 3
ORDER BY d.department_id, r.rn;
```

Điều kiện `r.rn <= 3` được đặt trong `ON` để giữ lại phòng ban không có nhân viên phù hợp. Nếu đặt nó trong `WHERE`, các hàng có `r.rn IS NULL` sẽ bị loại và `LEFT JOIN` có thể trở thành hành vi tương đương inner filter.

## 12. Hiệu năng và index cho Top-N per group

Window function cần phân vùng và sắp xếp dữ liệu theo các cột trong `PARTITION BY` và `ORDER BY`. Một index có thứ tự phù hợp có thể giúp giảm chi phí đọc hoặc sắp xếp, nhưng không bảo đảm MySQL luôn tránh được sort/materialization.

Với truy vấn xếp hạng nhân viên theo phòng ban và lương:

```sql
CREATE INDEX idx_employees_department_salary
    ON employees (department_id, salary DESC, employee_id);
```

Chạy lệnh tạo index này một lần nếu bảng chưa có index cùng tên; phần DDL ở đầu bài cố ý chỉ tạo khóa chính để ta quan sát riêng tác động của index trong bài thực hành.

Thứ tự index bắt đầu bằng `department_id`, sau đó là `salary` theo hướng xếp hạng và `employee_id` làm tie-breaker. Nếu truy vấn lọc thêm `employment_status`, có thể cần đánh giá index khác, ví dụ `(employment_status, department_id, salary, employee_id)`, dựa trên tính chọn lọc và các truy vấn thực tế.

Kiểm tra kế hoạch:

```sql
EXPLAIN
WITH ranked_employees AS (
    SELECT
        employee_id,
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
WHERE rn <= 3;
```

Kiểm tra số hàng ước lượng, index được chọn, thao tác sort và việc materialize CTE. Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi truy vấn để đo thời gian và số hàng thực tế; chỉ chạy trên môi trường phù hợp vì câu lệnh được thực thi thật.

Đừng giả định window function sẽ chỉ đọc N hàng mỗi partition. Trong nhiều kế hoạch, server vẫn phải đọc và xếp hạng một phần lớn hoặc toàn bộ tập ứng viên trước khi lọc `rn <= N`. Nếu dữ liệu rất lớn, đo lường bằng dữ liệu gần thực tế và cân nhắc mô hình truy vấn phù hợp.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `LIMIT N` cho toàn truy vấn | Chỉ lấy N hàng trên mọi nhóm | Dùng window function với `PARTITION BY` |
| Dùng `ROW_NUMBER()` nhưng nghiệp vụ cần giữ đồng hạng | Một số hàng đồng hạng bị loại | Dùng `RANK()` hoặc `DENSE_RANK()` theo định nghĩa Top-N |
| Dùng `DENSE_RANK()` khi yêu cầu là N vị trí | Có thể trả nhiều hơn mong đợi | Dùng `RANK()` nếu muốn giữ ties ở vị trí biên, hoặc `ROW_NUMBER()` nếu cần giới hạn hàng |
| Thêm khóa duy nhất vào `ORDER BY` trong `RANK()` | Các hàng không còn đồng hạng | Chỉ xếp hạng theo tiêu chí xác định tie; thêm tie-breaker ở `ROW_NUMBER()` hoặc `ORDER BY` ngoài |
| Lọc alias window trong `WHERE` cùng cấp | Lỗi phạm vi alias | Dùng CTE hoặc derived table |
| Lọc dữ liệu sau khi xếp hạng dù muốn loại trước | Thứ hạng bị chiếm bởi hàng không đủ điều kiện | Đưa bộ lọc ứng viên vào CTE trước window function |
| Không có tie-breaker cho `ROW_NUMBER()` | Thứ tự giữa các hàng đồng giá trị không ổn định | Thêm khóa duy nhất vào window `ORDER BY` |
| Không xử lý `NULL` của tiêu chí | Hàng thiếu dữ liệu có thể vào vị trí ngoài ý muốn | Đặt quy tắc NULL rõ ràng hoặc lọc trước khi xếp hạng |

## 14. Checklist chọn hàm xếp hạng

Trước khi viết truy vấn Top-N, hãy trả lời:

1. Nhóm được xác định bởi cột nào trong `PARTITION BY`?
2. Tiêu chí chính để xếp hạng là gì và chiều tăng/giảm ra sao?
3. “Top N” nghĩa là đúng tối đa N hàng, N vị trí có giữ ties, hay N mức giá trị khác nhau?
4. Nếu dùng `ROW_NUMBER()`, tie-breaker nào bảo đảm thứ tự duy nhất?
5. Nếu dùng `RANK()`/`DENSE_RANK()`, những cột nào thực sự định nghĩa đồng hạng?
6. Điều kiện lọc nào phải áp dụng trước khi xếp hạng?
7. Cột xếp hạng có thể `NULL` không và NULL được xử lý thế nào?
8. Có cần hiển thị cả nhóm không có hàng bằng `LEFT JOIN` không?
9. Index có hỗ trợ partition/order/filter không?
10. Đã kiểm tra `EXPLAIN` hoặc `EXPLAIN ANALYZE` trên dữ liệu phù hợp chưa?

## 15. Bài tập thực hành

Sử dụng bảng `employees` ở phần đầu:

1. Viết truy vấn lấy đúng tối đa hai nhân viên lương cao nhất mỗi phòng ban bằng `ROW_NUMBER()`.
2. Dùng `RANK()` để lấy ba vị trí lương cao nhất và giữ tất cả nhân viên đồng hạng ở vị trí biên.
3. Dùng `DENSE_RANK()` để lấy ba mức lương phân biệt cao nhất trong mỗi phòng ban.
4. Bổ sung `employee_id` vào `ORDER BY` của `RANK()`; quan sát cách các hàng cùng lương mất trạng thái đồng hạng và giải thích nguyên nhân.
5. Trên bảng thử nghiệm, cho phép `salary` nhận `NULL` bằng `ALTER TABLE employees MODIFY salary DECIMAL(12,2) NULL`, sau đó thêm một nhân viên có lương `NULL`; thử xếp hạng với và không có quy tắc NULL tường minh.
6. Chỉ xếp hạng nhân viên `ACTIVE`; so sánh kết quả khi lọc trạng thái trong CTE và ở truy vấn ngoài.
7. Dùng `LEFT JOIN` để hiển thị cả phòng ban chưa có nhân viên trong danh sách Top-N.
8. Dùng `EXPLAIN` để xem ảnh hưởng của index `(department_id, salary, employee_id)`.

Bạn hoàn thành bài khi chọn đúng giữa `ROW_NUMBER()`, `RANK()` và `DENSE_RANK()` theo chính sách đồng hạng, tạo được Top-N cho từng partition và giải thích được vì sao thứ tự xếp hạng cần tie-breaker hoặc không được thêm tie-breaker. Hãy xác định ý nghĩa nghiệp vụ của “Top-N” trước khi chọn hàm, vì một lựa chọn khác nhau có thể làm thay đổi số hàng và người được trả về.

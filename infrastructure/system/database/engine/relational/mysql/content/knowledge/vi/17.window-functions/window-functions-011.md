# Lọc kết quả hàm cửa sổ qua CTE hoặc derived table

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao không thể lọc trực tiếp kết quả window function trong WHERE của cùng SELECT.
- Bọc truy vấn có window function bằng CTE hoặc derived table để lọc ở truy vấn ngoài.
- Dùng ROW_NUMBER, RANK và DENSE_RANK để lấy top N theo từng nhóm.
- Phân biệt lọc dữ liệu đầu vào trước khi tính cửa sổ với lọc kết quả sau khi tính cửa sổ.
- Lọc theo running total, LAG, LEAD và các biểu thức cửa sổ khác.
- Chọn đúng hàm xếp hạng theo yêu cầu xử lý đồng hạng.
- Kiểm tra thứ tự, NULL, phạm vi partition và hiệu năng bằng EXPLAIN.

Window function tính một giá trị dựa trên các hàng liên quan trong một tập kết quả, nhưng vẫn giữ lại từng hàng chi tiết. Những ví dụ phổ biến là đánh số thứ tự đơn hàng theo khách hàng, xếp hạng nhân viên trong phòng ban, tính tổng lũy kế và so sánh giá trị với hàng trước.

Một yêu cầu thường gặp là chỉ lấy những hàng có kết quả window function thỏa điều kiện, ví dụ lấy ba đơn gần nhất của mỗi khách hàng hoặc nhân viên thuộc top 10% trong phòng ban. MySQL không cho phép đặt window function trực tiếp trong WHERE hoặc HAVING của cùng query block. Cách giải quyết là tính window function ở một tầng truy vấn, rồi lọc kết quả ở tầng bên ngoài bằng CTE hoặc derived table.

## 1. Vì sao cần một tầng truy vấn bên ngoài?

### 1.1. Window function được tính sau WHERE

Một SELECT có thể hình dung theo thứ tự xử lý logic khái quát:

1. FROM và JOIN tạo tập hàng đầu vào.
2. WHERE lọc hàng đầu vào.
3. GROUP BY và HAVING xử lý nhóm.
4. Window function tính kết quả trên các hàng còn lại.
5. SELECT tạo các cột kết quả.
6. DISTINCT, ORDER BY và LIMIT hoàn thiện tập kết quả trả về.

Đây là mô hình giúp hiểu phạm vi của từng mệnh đề; optimizer có thể thực thi theo kế hoạch khác nhưng phải giữ nguyên ngữ nghĩa SQL.

Window function cần nhìn thấy tập hàng sau các bước lọc và gom nhóm trước đó. Vì vậy, câu lệnh sau không hợp lệ:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC
    ) AS row_num
FROM sales_order
WHERE row_num <= 3;
~~~

WHERE được xử lý trước khi row_num được tính. Tên alias row_num chưa tồn tại tại thời điểm WHERE cần đánh giá. Việc viết trực tiếp biểu thức window trong WHERE cũng không hợp lệ:

~~~sql
SELECT
    order_id,
    customer_id
FROM sales_order
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC
) <= 3;
~~~

MySQL chỉ cho phép window function trong danh sách SELECT và ORDER BY của query block tương ứng. Không thể dùng chúng trực tiếp trong WHERE, GROUP BY hoặc HAVING của cùng query block.

### 1.2. Tính ở trong, lọc ở ngoài

Tách công việc thành hai tầng:

- Tầng trong đọc dữ liệu và tính window function.
- Tầng ngoài đọc kết quả đã có tên cột window rồi lọc bằng WHERE thông thường.

Có thể dùng CTE:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    row_num
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, row_num;
~~~

Hoặc dùng derived table:

~~~sql
SELECT
    ranked.order_id,
    ranked.customer_id,
    ranked.ordered_at,
    ranked.row_num
FROM (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
) AS ranked
WHERE ranked.row_num <= 3
ORDER BY ranked.customer_id, ranked.row_num;
~~~

Hai cách biểu diễn cùng ý tưởng. CTE đặt tên bước trung gian ở đầu câu lệnh; derived table đặt truy vấn con ngay trong FROM. Truy vấn ngoài có thể lọc alias row_num vì lúc này row_num đã là cột của nguồn ranked_orders.

### 1.3. MySQL không hỗ trợ QUALIFY

Một số hệ quản trị cơ sở dữ liệu có mệnh đề QUALIFY để lọc kết quả window function sau khi tính. MySQL 8.4 không hỗ trợ QUALIFY. Khi làm việc với MySQL, hãy dùng CTE hoặc derived table để tạo tầng lọc bên ngoài.

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ dùng bảng đơn hàng đơn giản. Mỗi hàng là một đơn hàng; một khách hàng có thể có nhiều đơn.

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    ordered_at DATETIME NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_status_customer_date (
        order_status,
        customer_id,
        ordered_at,
        order_id
    )
) ENGINE = InnoDB;

INSERT INTO sales_order (
    order_id,
    customer_id,
    order_status,
    ordered_at,
    total_amount
)
VALUES
    (1001, 101, 'completed', '2026-01-05 09:15:00', 1250000.00),
    (1002, 101, 'completed', '2026-01-20 14:30:00', 5200000.00),
    (1003, 101, 'pending',   '2026-02-16 10:00:00',  890000.00),
    (1004, 101, 'completed', '2026-02-12 16:45:00', 1500000.00),
    (1005, 102, 'completed', '2026-01-10 08:20:00', 5200000.00),
    (1006, 102, 'completed', '2026-01-17 12:10:00', 3400000.00),
    (1007, 102, 'completed', '2026-02-03 13:00:00', 3400000.00),
    (1008, 103, 'cancelled', '2026-02-15 11:20:00', 2100000.00);
~~~

Kiểm tra dữ liệu:

~~~sql
SELECT *
FROM sales_order
ORDER BY customer_id, ordered_at, order_id;
~~~

Trong bài này:

- customer_id xác định nhóm khách hàng.
- ordered_at xác định thời điểm đặt hàng.
- order_id là khóa duy nhất, dùng làm tie-breaker khi hai đơn có cùng thời điểm.
- total_amount là giá trị đơn, dùng cho ví dụ xếp hạng.

Dữ liệu có hai đơn của khách 102 cùng giá trị 3.400.000 để minh họa sự khác nhau giữa ROW_NUMBER, RANK và DENSE_RANK.

## 3. Lọc top N hàng trong mỗi nhóm bằng ROW_NUMBER

### 3.1. Lấy ba đơn gần nhất của từng khách hàng

ROW_NUMBER đánh số từng hàng trong partition theo thứ tự được khai báo. Mỗi partition bắt đầu lại từ 1.

Nếu bỏ ORDER BY trong OVER, thứ tự đánh số trong partition không được xác định. Khi cần chọn một hàng cụ thể hoặc top N ổn định, hãy khai báo thứ tự nghiệp vụ và thêm tie-breaker duy nhất.

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    total_amount,
    row_num
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, row_num;
~~~

Giải thích:

- PARTITION BY customer_id chia đơn hàng theo từng khách.
- ORDER BY ordered_at DESC đặt đơn mới nhất trước.
- order_id DESC là tie-breaker để thứ tự luôn xác định khi thời điểm bằng nhau.
- ROW_NUMBER đánh số 1, 2, 3... trong từng khách.
- WHERE row_num <= 3 chỉ giữ tối đa ba hàng mỗi khách.

Nếu một khách có một hoặc hai đơn, kết quả chỉ có một hoặc hai hàng. Điều kiện row_num <= 3 không tự tạo thêm hàng cho đủ ba.

### 3.2. Lấy đúng một hàng mới nhất mỗi nhóm

Mẫu này thường dùng để lấy bản ghi hiện hành từ bảng lịch sử:

~~~sql
WITH latest_order AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    order_status,
    ordered_at
FROM latest_order
WHERE rn = 1
ORDER BY customer_id;
~~~

Mỗi customer_id có tối đa một hàng trong kết quả. Nếu có nhiều đơn cùng ordered_at, order_id DESC quyết định hàng nào được chọn.

Đừng bỏ tie-breaker khi yêu cầu nghiệp vụ cần một kết quả duy nhất. Nếu chỉ sắp theo ordered_at và hai hàng cùng thời điểm, thứ tự giữa chúng không được bảo đảm; hàng nhận rn = 1 có thể thay đổi theo kế hoạch thực thi hoặc dữ liệu.

### 3.3. Lọc theo nhiều điều kiện trên kết quả window

Có thể kết hợp nhiều điều kiện ở tầng ngoài:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 2
  AND order_status = 'completed'
  AND total_amount >= 1000000
ORDER BY customer_id, rn;
~~~

Ở truy vấn này, rn được tính trên tất cả trạng thái đơn. Sau đó truy vấn ngoài mới giữ hai hàng đầu tiên theo từng khách, rồi loại các hàng không completed hoặc có tổng tiền thấp.

Điều đó có nghĩa một khách có thể có ít hơn hai hàng trong kết quả cuối dù có nhiều đơn completed ở vị trí sau. Nếu ý định là lấy hai đơn completed gần nhất, phải lọc order_status bên trong CTE trước khi tính ROW_NUMBER. Phần 7 sẽ phân tích khác biệt này.

## 4. ROW_NUMBER, RANK và DENSE_RANK khi lọc top N

Ba hàm xếp hạng có ý nghĩa khác nhau khi có giá trị đồng hạng.

| Hàm | Quy tắc | Ví dụ thứ hạng cho giá trị 100, 90, 90, 80 |
|---|---|---|
| ROW_NUMBER | Mỗi hàng có số thứ tự riêng | 1, 2, 3, 4 |
| RANK | Hàng bằng nhau cùng hạng, hạng sau bị nhảy | 1, 2, 2, 4 |
| DENSE_RANK | Hàng bằng nhau cùng hạng, không bỏ số hạng | 1, 2, 2, 3 |

### 4.1. ROW_NUMBER: giới hạn số hàng chính xác

Nếu yêu cầu “tối đa ba đơn mỗi khách”, dùng ROW_NUMBER:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

Mỗi nhóm có tối đa ba hàng. Tie-breaker order_id DESC giúp chọn hàng cụ thể khi total_amount bằng nhau.

### 4.2. RANK: giữ tất cả hàng đồng hạng trong top N vị trí

Nếu yêu cầu “lấy các đơn thuộc ba vị trí xếp hạng đầu tiên, giữ cả đơn đồng giá trị”, dùng RANK:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_rank
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE amount_rank <= 3
ORDER BY customer_id, amount_rank, order_id;
~~~

Không thêm order_id vào ORDER BY bên trong RANK nếu muốn các đơn cùng total_amount được đồng hạng. Nếu thêm cột duy nhất vào ORDER BY, mỗi hàng có thể nhận hạng khác nhau vì toàn bộ tuple sắp xếp không còn bằng nhau.

Khi có đồng hạng tại vị trí thứ ba, số hàng trả về có thể nhiều hơn ba.

### 4.3. DENSE_RANK: lấy top N mức giá trị phân biệt

Nếu yêu cầu “lấy ba mức giá trị đơn cao nhất”, dùng DENSE_RANK:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        DENSE_RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_level
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE amount_level <= 3
ORDER BY customer_id, amount_level, order_id;
~~~

Với các giá trị 100, 90, 90, 80:

- RANK <= 3 trả về 100, 90, 90; giá trị 80 mang hạng 4.
- DENSE_RANK <= 3 trả về cả 100, 90, 90, 80 vì đó là ba mức giá trị phân biệt.

Hãy xác định nghiệp vụ cần giới hạn số hàng, vị trí xếp hạng hay số mức giá trị trước khi chọn hàm.

## 5. Lọc kết quả bằng derived table

CTE không phải lựa chọn duy nhất. Derived table tạo một query block bên trong FROM, có thể cung cấp cùng cột window cho query block bên ngoài.

Ví dụ lấy hai đơn gần nhất của mỗi khách:

~~~sql
SELECT
    ranked.order_id,
    ranked.customer_id,
    ranked.ordered_at,
    ranked.row_num
FROM (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS row_num
    FROM sales_order
) AS ranked
WHERE ranked.row_num <= 2
ORDER BY ranked.customer_id, ranked.row_num;
~~~

Alias ranked là bắt buộc cho derived table. Truy vấn ngoài tham chiếu cột bằng ranked.row_num.

### 5.1. Chọn CTE hay derived table?

| Tình huống | Lựa chọn thường dễ đọc |
|---|---|
| Một bước window đơn giản, chỉ dùng một lần | Derived table |
| Nhiều bước trung gian hoặc nhiều CTE liên kết | CTE |
| Cùng tập kết quả cần tham chiếu nhiều lần trong câu lệnh | CTE |
| Muốn đặt tên logic ở đầu câu lệnh | CTE |
| Query con nhỏ, nằm sát nơi sử dụng | Derived table |

Hai cách không tạo khác biệt về ý nghĩa nếu viết cùng phép tính và điều kiện. Chọn cách làm cấu trúc truy vấn dễ đọc, sau đó đo hiệu năng trên dữ liệu thực tế.

### 5.2. CTE có thể được dùng lại ở nhiều vị trí

Ví dụ tính thứ hạng đơn hàng một lần rồi thống kê từ cùng tập kết quả:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT
    customer_id,
    MAX(CASE WHEN rn = 1 THEN total_amount END) AS highest_order,
    COUNT(CASE WHEN rn <= 3 THEN 1 END) AS top_three_count
FROM ranked_orders
GROUP BY customer_id;
~~~

CTE làm rõ bước xếp hạng. Truy vấn ngoài có thể dùng rn trong biểu thức tổng hợp thông thường vì rn đã là cột đầu ra của CTE.

## 6. Lọc kết quả của các window function khác

Cách bọc truy vấn không chỉ áp dụng cho ROW_NUMBER hoặc RANK. Bất kỳ kết quả window function nào cũng có thể được lọc ở query block bên ngoài.

### 6.1. Lọc theo tổng lũy kế

Tính tổng giá trị đơn tích lũy theo thời gian của mỗi khách:

~~~sql
WITH running_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        SUM(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ) AS running_total
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    total_amount,
    running_total
FROM running_orders
WHERE running_total >= 5000000
ORDER BY customer_id, ordered_at, order_id;
~~~

Truy vấn trong tính tổng lũy kế. Truy vấn ngoài chỉ giữ các hàng mà tổng tích lũy đã đạt ít nhất 5 triệu.

Frame ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW diễn tả từ hàng đầu tiên trong partition đến hàng hiện tại. Thêm order_id làm tie-breaker để thứ tự cộng dồn xác định khi ordered_at bằng nhau.

Nếu chỉ viết ORDER BY ordered_at mà có nhiều đơn cùng thời điểm, thứ tự các hàng đồng thời điểm có thể không xác định. Khi đó tổng lũy kế theo từng hàng cũng có thể khác nhau giữa các hàng đó.

### 6.2. Lọc hàng có giá trị thay đổi so với hàng trước

LAG lấy giá trị ở hàng đứng trước theo thứ tự cửa sổ. Có thể dùng nó để tìm những đơn có giá trị tăng so với đơn trước:

~~~sql
WITH order_changes AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
        ) AS previous_amount
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    ordered_at,
    total_amount,
    previous_amount,
    total_amount - previous_amount AS amount_change
FROM order_changes
WHERE previous_amount IS NOT NULL
  AND total_amount > previous_amount
ORDER BY customer_id, ordered_at, order_id;
~~~

Hàng đầu tiên trong mỗi partition không có hàng trước nên previous_amount là NULL. Điều kiện previous_amount IS NOT NULL loại hàng đầu tiên khỏi phép so sánh.

### 6.3. Lọc hàng có giá trị tiếp theo

LEAD đọc giá trị ở hàng sau. Ví dụ tìm đơn mà đơn tiếp theo của cùng khách có giá trị lớn hơn:

~~~sql
WITH order_sequence AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        total_amount,
        LEAD(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
        ) AS next_amount
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    total_amount,
    next_amount
FROM order_sequence
WHERE next_amount > total_amount
ORDER BY customer_id, ordered_at, order_id;
~~~

Hàng cuối mỗi partition không có hàng tiếp theo, nên next_amount là NULL và điều kiện so sánh không đúng.

### 6.4. Lọc theo tỷ lệ so với trung bình nhóm

Ví dụ lấy các đơn có giá trị cao hơn trung bình của khách hàng đó:

~~~sql
WITH orders_with_average AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        AVG(total_amount) OVER (
            PARTITION BY customer_id
        ) AS customer_average
    FROM sales_order
)
SELECT
    order_id,
    customer_id,
    total_amount,
    customer_average
FROM orders_with_average
WHERE total_amount > customer_average
ORDER BY customer_id, total_amount DESC;
~~~

AVG ở dạng window giữ lại từng đơn và thêm mức trung bình của nhóm. Truy vấn ngoài lọc các đơn cao hơn trung bình.

Nếu dùng GROUP BY customer_id ở tầng trong, kết quả sẽ chỉ còn một hàng mỗi khách và không thể giữ từng đơn để so sánh.

## 7. Lọc trước hay sau khi tính window?

Đây là điểm quan trọng nhất khi viết truy vấn nhiều tầng. Một điều kiện đặt bên trong CTE sẽ thay đổi tập hàng mà window function nhìn thấy. Một điều kiện đặt ở truy vấn ngoài chỉ loại các hàng sau khi window đã tính.

### 7.1. Muốn xếp hạng chỉ các đơn completed

Đặt điều kiện trong CTE:

~~~sql
WITH ranked_completed_orders AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
    WHERE order_status = 'completed'
)
SELECT *
FROM ranked_completed_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

Ở đây chỉ các đơn completed tham gia vào ROW_NUMBER. Kết quả là hai đơn completed gần nhất của mỗi khách.

### 7.2. Xếp hạng tất cả đơn rồi mới chỉ hiển thị đơn completed

Đặt điều kiện ở ngoài:

~~~sql
WITH ranked_all_orders AS (
    SELECT
        order_id,
        customer_id,
        order_status,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_all_orders
WHERE rn <= 2
  AND order_status = 'completed'
ORDER BY customer_id, rn;
~~~

Ở đây mọi trạng thái đều tham gia xếp hạng. Sau đó chỉ những hàng vừa nằm trong top 2 vừa có trạng thái completed được trả về.

Hai truy vấn có thể trả kết quả khác nhau. Với khách 101, đơn pending mới nhất có thể chiếm vị trí đầu khi xếp hạng tất cả đơn. Vì vậy, lọc trạng thái sau khi xếp hạng có thể khiến kết quả chỉ còn một đơn completed.

### 7.3. Quy tắc quyết định vị trí điều kiện

Trước khi viết truy vấn, hãy tự hỏi:

- Điều kiện này xác định hàng nào được tham gia tính window? Đặt ở query block bên trong, trước window.
- Điều kiện này chỉ quyết định hàng nào được giữ sau khi window đã tính? Đặt ở query block bên ngoài.
- Nếu đẩy điều kiện từ ngoài vào trong, thứ hạng, tổng lũy kế, LAG/LEAD hoặc trung bình nhóm có thay đổi không?

Không đẩy điều kiện qua ranh giới window chỉ vì muốn giảm số hàng. Việc đẩy lọc có thể thay đổi kết quả nghiệp vụ.

## 8. Kết hợp nhiều tầng window và lọc

Có thể dùng một CTE để tính window, CTE tiếp theo để lọc hoặc tính toán tiếp từ kết quả đó.

Ví dụ lấy hai đơn có giá trị cao nhất mỗi khách, rồi tính tỷ trọng của từng đơn trong tổng giá trị top 2:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS rn
    FROM sales_order
),
top_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount
    FROM ranked_orders
    WHERE rn <= 2
),
top_order_shares AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        SUM(total_amount) OVER (
            PARTITION BY customer_id
        ) AS top_total
    FROM top_orders
)
SELECT
    order_id,
    customer_id,
    total_amount,
    top_total,
    total_amount / NULLIF(top_total, 0) AS share_of_top
FROM top_order_shares
ORDER BY customer_id, total_amount DESC, order_id DESC;
~~~

Ba tầng có ý nghĩa riêng:

1. ranked_orders xếp hạng tất cả đơn trong mỗi khách.
2. top_orders lọc hai đơn đứng đầu.
3. top_order_shares tính tổng của hai đơn đã được chọn.

Window ở tầng thứ ba chỉ nhìn thấy các hàng đã lọc trong top_orders. Nếu tính SUM ở cùng tầng với ROW_NUMBER ban đầu, tổng sẽ là tổng của tất cả đơn trong khách hàng, không phải tổng top 2.

## 9. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng window function trong WHERE cùng SELECT | MySQL báo lỗi cú pháp/ngữ cảnh | Bọc bằng CTE hoặc derived table |
| Dùng alias window trong WHERE cùng query block | Alias chưa có ở thời điểm WHERE | Lọc alias ở query block ngoài |
| Nghĩ HAVING lọc được window function | Window không được phép trong HAVING cùng block | Dùng tầng truy vấn bên ngoài |
| Dùng ROW_NUMBER nhưng không có tie-breaker | Hàng đồng thứ tự có thể đổi vị trí | Thêm cột duy nhất vào ORDER BY |
| Dùng RANK nhưng thêm khóa duy nhất vào ORDER BY | Các hàng không còn đồng hạng | Chỉ xếp theo tiêu chí nghiệp vụ để giữ tie |
| Dùng RANK khi muốn đúng N hàng | Có thể trả về nhiều hơn N do đồng hạng | Dùng ROW_NUMBER |
| Dùng DENSE_RANK khi muốn N vị trí | Trả về N mức giá trị phân biệt | Chọn đúng hàm theo yêu cầu |
| Đặt filter trạng thái sai tầng | Tập hàng tham gia window thay đổi | Xác định điều kiện trước hay sau window |
| Nghĩ ORDER BY trong OVER sắp xếp kết quả cuối | Thứ tự trả về vẫn không được bảo đảm | Thêm ORDER BY ở SELECT ngoài |
| Dùng LIMIT để lấy top N mỗi nhóm | LIMIT chỉ giới hạn toàn bộ result set | Dùng ROW_NUMBER/RANK và lọc bên ngoài |
| Dùng SELECT * cho dữ liệu trung gian lớn | Tăng dữ liệu cần xử lý | Chọn các cột cần thiết |
| Bỏ qua NULL trong cột sắp xếp | Kết quả có thể không theo ý định | Đặt quy tắc NULL rõ ràng trong ORDER BY |

### 9.1. ORDER BY trong OVER không thay ORDER BY ngoài

Window ORDER BY quyết định thứ tự tính toán trong partition. Nó không đảm bảo thứ tự các hàng cuối cùng được trả về.

Luôn đặt ORDER BY ở query block ngoài nếu giao diện, báo cáo hoặc API cần thứ tự cụ thể:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

### 9.2. LIMIT không thay được top N per group

Ví dụ sau chỉ lấy ba hàng trên toàn bộ bảng:

~~~sql
SELECT *
FROM sales_order
ORDER BY ordered_at DESC
LIMIT 3;
~~~

Nó không lấy ba hàng cho mỗi customer_id. Muốn giới hạn theo từng nhóm, phải chia partition và đánh số hoặc xếp hạng từng nhóm bằng window function.

### 9.3. Xử lý NULL trong thứ tự

Trong MySQL, khi sắp xếp ASC, NULL đứng trước giá trị không NULL; khi sắp xếp DESC, NULL đứng sau. Nếu cần quy tắc rõ ràng, có thể đưa biểu thức kiểm tra NULL vào ORDER BY:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY
            (ordered_at IS NULL) ASC,
            ordered_at DESC,
            order_id DESC
    ) AS rn
FROM sales_order;
~~~

Biểu thức (ordered_at IS NULL) ASC đưa hàng có ngày giờ khác NULL lên trước. Sau đó ordered_at DESC sắp ngày giờ mới nhất, order_id DESC phá hòa.

## 10. Hiệu năng và kế hoạch thực thi

Bọc window function bằng CTE hoặc derived table giải quyết giới hạn cú pháp và phạm vi tên. Nó không làm biến mất chi phí tính window.

### 10.1. Chi phí partition và sort

Để tính ROW_NUMBER theo khách và ngày, MySQL cần xử lý hàng theo partition customer_id và thứ tự ordered_at, order_id. Với dữ liệu lớn, bước sắp xếp có thể chiếm đáng kể thời gian và bộ nhớ.

Index có thứ tự cột phù hợp có thể hỗ trợ truy cập dữ liệu:

~~~sql
CREATE INDEX idx_order_customer_date
ON sales_order (
    customer_id,
    ordered_at,
    order_id
);
~~~

Index này phù hợp với nhiều truy vấn lọc hoặc sắp xếp theo customer_id rồi ordered_at. Tuy nhiên, optimizer có thể vẫn cần sort tùy điều kiện, chiều sắp xếp, biểu thức window và execution plan. Không suy luận rằng có index là chắc chắn bỏ được sort.

### 10.2. Lọc đầu vào sớm khi đúng ngữ nghĩa

Nếu chỉ xếp hạng đơn trong một khoảng thời gian, có thể lọc khoảng thời gian ở CTE:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
    WHERE ordered_at >= '2026-01-01'
      AND ordered_at <  '2026-04-01'
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

Window chỉ nhìn thấy đơn trong khoảng thời gian. Điều này khác với việc xếp hạng toàn bộ lịch sử rồi lọc kết quả có ordered_at trong khoảng ngày. Hãy chọn theo yêu cầu nghiệp vụ.

### 10.3. Window function trong CTE và materialization

Trong MySQL, derived table hoặc CTE có window function thuộc các trường hợp không thể merge theo quy tắc tối ưu hóa. MySQL thường phải materialize kết quả query block chứa window function trước khi query ngoài lọc.

Điều đó có thể tạo chi phí ghi/đọc tập trung gian. Hãy giảm số hàng và số cột ở tầng trong khi có thể làm vậy mà không thay đổi kết quả window.

Điều kiện WHERE ở query block ngoài cũng không được đẩy xuyên qua query block có window function theo quy tắc derived condition pushdown của MySQL 8.4. Vì thế, nếu cần giới hạn dữ liệu tham gia window theo khách hàng, trạng thái hoặc thời gian, hãy xác định điều kiện đó có thuộc tập đầu vào nghiệp vụ hay không rồi đặt nó trong query block bên trong ngay từ đầu.

Không đặt điều kiện của truy vấn ngoài vào trong chỉ để giảm materialization nếu điều kiện đó phải được đánh giá sau khi xếp hạng. Làm vậy sẽ thay đổi partition đầu vào và có thể đổi thứ hạng.

### 10.4. Dùng EXPLAIN

Kiểm tra kế hoạch:

~~~sql
EXPLAIN
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

Quan sát:

- Cách MySQL đọc sales_order và index được chọn.
- Số hàng ước lượng đi vào window.
- Bước sort hoặc materialization.
- Số hàng được giữ sau điều kiện rn <= 3.
- Có sort bổ sung ở truy vấn ngoài hay không.

Với MySQL 8.0.18 trở lên, có thể dùng EXPLAIN ANALYZE để xem thời gian và số hàng thực tế của các iterator:

~~~sql
EXPLAIN ANALYZE
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sales_order
)
SELECT *
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

EXPLAIN ANALYZE thực sự chạy câu SELECT. Tránh chạy tùy tiện trên truy vấn nặng ở production. So sánh dữ liệu thực tế, số hàng, thời gian và tài nguyên trước khi quyết định thêm index hoặc viết lại truy vấn.

## 11. Quy trình chọn mẫu lọc

Có thể dùng quy trình sau khi gặp yêu cầu lọc window function:

~~~mermaid
flowchart TD
    A[Viết window function trong SELECT] --> B{Cần lọc theo kết quả window?}
    B -->|Không| C[Dùng query block hiện tại]
    B -->|Có| D[Chọn CTE hoặc derived table]
    D --> E[Đặt window trong query block bên trong]
    E --> F[Đặt alias cho kết quả window]
    F --> G[Đặt điều kiện lọc ở query block ngoài]
    G --> H{Điều kiện có cần lọc đầu vào window?}
    H -->|Có| I[Đưa điều kiện vào query block trong]
    H -->|Không| J[Giữ điều kiện ở query block ngoài]
    I --> K[Kiểm tra tie, NULL và thứ tự]
    J --> K
    K --> L[EXPLAIN và xác minh kết quả]
~~~

Trình tự thực hành:

1. Xác định nhóm cần chia bằng PARTITION BY.
2. Xác định thứ tự hoặc tiêu chí xếp hạng trong OVER.
3. Chọn ROW_NUMBER, RANK, DENSE_RANK hay một hàm window khác.
4. Đặt alias dễ hiểu cho kết quả window.
5. Bọc query bằng CTE hoặc derived table.
6. Viết điều kiện lọc ở tầng ngoài.
7. Xác định điều kiện nào phải lọc trước window.
8. Thêm ORDER BY ngoài nếu cần thứ tự kết quả.
9. Kiểm tra tie, NULL và trường hợp nhóm ít hàng.
10. Dùng EXPLAIN để đánh giá chi phí.

## 12. Bài tập thực hành

### Bài 1: Top ba đơn gần nhất

Dùng ROW_NUMBER để lấy ba đơn gần nhất của mỗi khách. Thêm order_id làm tie-breaker. Kiểm tra khách có ít hơn ba đơn.

### Bài 2: Lấy đơn mới nhất

Dùng CTE để tính ROW_NUMBER theo customer_id. Lọc rn = 1. Thử tạo hai đơn có cùng ordered_at và quan sát tác dụng của tie-breaker.

### Bài 3: So sánh ba hàm xếp hạng

Xếp hạng total_amount theo từng khách bằng ROW_NUMBER, RANK và DENSE_RANK. Tạo dữ liệu có giá trị bằng nhau và giải thích số hàng trả về khi lọc hạng <= 2.

### Bài 4: Top hai đơn completed

Viết hai truy vấn: một truy vấn lọc order_status bên trong CTE trước khi tính ROW_NUMBER; một truy vấn lọc completed ở ngoài sau khi xếp hạng mọi đơn. So sánh kết quả và giải thích.

### Bài 5: Tổng lũy kế đạt ngưỡng

Tính running_total theo customer_id và ordered_at. Dùng CTE lọc các đơn từ thời điểm tổng lũy kế đạt 5 triệu. Xác định frame và tie-breaker.

### Bài 6: So sánh với hàng trước

Dùng LAG để tìm đơn có total_amount lớn hơn đơn trước của cùng khách. Loại hàng đầu tiên của mỗi partition và giải thích giá trị NULL.

### Bài 7: So sánh CTE và derived table

Viết cùng một truy vấn top N per group bằng CTE và derived table. So sánh khả năng đọc và EXPLAIN.

### Bài 8: Xử lý NULL trong thứ tự

Cho phép ordered_at NULL trong bảng thực hành bằng ALTER TABLE sales_order MODIFY ordered_at DATETIME NULL, sau đó thêm ít nhất một hàng có ordered_at là NULL. Xác định NULL cần đứng đầu hay cuối, viết ORDER BY tường minh và kiểm tra thứ hạng.

### Bài 9: Đo hiệu năng

Tạo thêm dữ liệu lớn cho sales_order. So sánh truy vấn top ba theo customer_id trước và sau khi thêm index phù hợp. Dùng EXPLAIN ANALYZE trên môi trường thử nghiệm.

### Bài 10: Thiết kế truy vấn nghiệp vụ

Viết truy vấn lấy các đơn nằm trong top 10% giá trị của từng khách. Xác định có cần PERCENT_RANK hoặc CUME_DIST không, và giải thích điều kiện lọc ở query block ngoài.

## Kết luận

Muốn lọc kết quả window function trong MySQL, hãy tính nó trong một query block rồi lọc ở query block bên ngoài. CTE phù hợp khi muốn đặt tên rõ cho bước trung gian; derived table phù hợp với một truy vấn con dùng tại một vị trí. Cả hai cách đều cho phép truy vấn ngoài tham chiếu alias window bằng WHERE.

Chọn hàm xếp hạng theo yêu cầu: ROW_NUMBER giới hạn số hàng, RANK giữ đồng hạng theo vị trí và DENSE_RANK giữ các mức giá trị phân biệt. Đặt điều kiện lọc ở đúng tầng vì lọc trước window sẽ thay đổi tập hàng tham gia partition. Cuối cùng, thêm tie-breaker, xác định quy tắc NULL, sắp xếp kết quả ở query block ngoài và dùng EXPLAIN để đánh giá chi phí.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Window Function Concepts and Syntax: https://dev.mysql.com/doc/refman/8.4/en/window-functions-usage.html
- MySQL 8.4 Reference Manual — Window Function Restrictions: https://dev.mysql.com/doc/refman/8.4/en/window-function-restrictions.html
- MySQL 8.4 Reference Manual — Window Function Descriptions: https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html
- MySQL 8.4 Reference Manual — Derived Table Optimization: https://dev.mysql.com/doc/refman/8.4/en/derived-table-optimization.html
- MySQL 8.4 Reference Manual — EXPLAIN Statement: https://dev.mysql.com/doc/refman/8.4/en/explain.html


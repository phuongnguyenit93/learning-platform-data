# LAG, LEAD và so sánh với dòng trước hoặc dòng sau

## Mục tiêu

Sau bài này, bạn có thể:

- Dùng `LAG()` để đọc giá trị của dòng đứng trước và `LEAD()` để đọc giá trị của dòng đứng sau trong một cửa sổ.
- Xác định phạm vi so sánh bằng `PARTITION BY` và thứ tự dòng bằng `ORDER BY`.
- Bảo đảm kết quả ổn định bằng cách thêm khóa duy nhất làm tie-breaker.
- Sử dụng offset và giá trị mặc định khi không tồn tại dòng trước/sau.
- Phân biệt dòng không tồn tại với dòng tồn tại nhưng có giá trị `NULL`.
- Tính chênh lệch, tỷ lệ thay đổi, phát hiện thay đổi trạng thái và khoảng cách giữa các sự kiện.
- Nhận diện giới hạn khi dữ liệu thời gian bị thiếu ngày/tháng và chọn cách tạo chuỗi thời gian liên tục.
- Lọc kết quả window function bằng CTE/derived table và kiểm tra hiệu năng bằng `EXPLAIN`.

## 1. LAG và LEAD giải quyết vấn đề gì?

Trong báo cáo, nhiều phép tính cần so sánh một dòng với dòng đứng ngay trước hoặc ngay sau nó theo một thứ tự xác định. Ví dụ:

- So sánh doanh thu tháng này với tháng trước.
- Tính số tiền đơn hàng tăng hoặc giảm so với đơn trước của cùng khách hàng.
- Phát hiện thời điểm trạng thái của một đơn hàng thay đổi.
- Tính khoảng thời gian giữa hai sự kiện liên tiếp.
- Xác định giá trị kế tiếp trong lịch sử giá hoặc tồn kho.

Có thể thực hiện các phép so sánh này bằng self join hoặc correlated subquery, nhưng câu SQL thường phức tạp hơn. `LAG()` và `LEAD()` là các window function giúp đọc giá trị từ dòng lân cận trong cùng một cửa sổ.

- `LAG(expr)` lấy giá trị của biểu thức `expr` ở một dòng đứng trước dòng hiện tại.
- `LEAD(expr)` lấy giá trị của biểu thức `expr` ở một dòng đứng sau dòng hiện tại.

Hai hàm không làm mất các dòng như `GROUP BY`. Mỗi dòng đầu vào vẫn có thể xuất hiện trong kết quả, kèm theo giá trị tham chiếu từ dòng trước hoặc sau.

## 2. Cú pháp LAG và LEAD trong MySQL

MySQL 8.0 hỗ trợ window function, bao gồm `LAG()` và `LEAD()`.

Cú pháp tổng quát:

```sql
LAG(expr [, N [, default]]) OVER (window_specification)

LEAD(expr [, N [, default]]) OVER (window_specification)
```

Trong đó:

- `expr`: biểu thức cần lấy từ dòng lân cận.
- `N`: số dòng dịch chuyển so với dòng hiện tại; mặc định là `1`.
- `default`: giá trị trả về nếu dòng ở vị trí yêu cầu không tồn tại; mặc định là `NULL`.
- `OVER (...)`: định nghĩa cửa sổ, thường gồm `PARTITION BY` và `ORDER BY`.

Ví dụ đơn giản:

```sql
SELECT
    order_id,
    customer_id,
    total_amount,
    LAG(total_amount) OVER (
        ORDER BY created_at, order_id
    ) AS previous_amount,
    LEAD(total_amount) OVER (
        ORDER BY created_at, order_id
    ) AS next_amount
FROM orders
ORDER BY created_at, order_id;
```

`previous_amount` lấy số tiền ở dòng đứng trước; `next_amount` lấy số tiền ở dòng đứng sau theo thứ tự `created_at, order_id`.

Lưu ý có hai vị trí `ORDER BY`:

- `ORDER BY` trong `OVER(...)` quyết định dòng trước/sau mà hàm tham chiếu.
- `ORDER BY` cuối câu lệnh quyết định thứ tự các dòng được trả về cho client.

Hai thứ tự này có thể giống nhau nhưng có vai trò riêng. Nếu cần kết quả hiển thị theo một thứ tự cụ thể, hãy viết `ORDER BY` ở truy vấn ngoài.

## 3. ORDER BY xác định thế nào là dòng trước và dòng sau?

`LAG()` và `LEAD()` không tự biết khái niệm trước/sau theo thời gian, mã tăng dần hay thứ tự vật lý của bảng. Chúng chỉ dựa vào thứ tự được khai báo trong `OVER(...)`.

Ví dụ lấy số dư theo thời điểm:

```sql
SELECT
    account_id,
    transaction_id,
    occurred_at,
    balance,
    LAG(balance) OVER (
        PARTITION BY account_id
        ORDER BY occurred_at, transaction_id
    ) AS balance_before
FROM account_transactions
ORDER BY account_id, occurred_at, transaction_id;
```

Trong mỗi tài khoản, các giao dịch được sắp xếp theo `occurred_at`, sau đó theo `transaction_id`. `LAG(balance)` lấy số dư của giao dịch liền trước trong thứ tự đó.

### 3.1. Thêm tie-breaker để thứ tự xác định

Giả sử hai đơn hàng có cùng `created_at`. Nếu chỉ viết:

```sql
LAG(total_amount) OVER (
    PARTITION BY customer_id
    ORDER BY created_at
)
```

thì thứ tự giữa các đơn có cùng thời điểm không được xác định đầy đủ. Kết quả so sánh có thể thay đổi theo execution plan hoặc trạng thái dữ liệu.

Hãy thêm cột duy nhất:

```sql
LAG(total_amount) OVER (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
)
```

Nếu `order_id` là primary key, cặp thứ tự này xác định được vị trí của từng hàng. Với truy vấn lịch sử, có thể dùng `event_time, event_id`; với bảng giao dịch, có thể dùng `posted_at, transaction_id`.

### 3.2. Thứ tự ASC và DESC làm thay đổi ý nghĩa

Với:

```sql
LAG(status) OVER (
    PARTITION BY order_id
    ORDER BY changed_at ASC, history_id ASC
)
```

`LAG()` lấy trạng thái của sự kiện cũ hơn gần nhất.

Nếu đổi thành `ORDER BY changed_at DESC, history_id DESC`, dòng đứng trước theo thứ tự cửa sổ sẽ là sự kiện mới hơn. Hàm vẫn đúng theo thứ tự được chỉ định, nhưng ý nghĩa nghiệp vụ thay đổi.

Hãy chọn chiều sắp xếp theo câu hỏi cần trả lời: “trạng thái trước đó trong lịch sử” thường dùng thời gian tăng dần; “bản ghi mới hơn kế tiếp trong danh sách mới nhất trước” có thể dùng chiều giảm dần.

### 3.3. NULL trong cột sắp xếp

Nếu cột `ORDER BY` cho phép `NULL`, MySQL áp dụng quy tắc sắp xếp NULL của nó: trong thứ tự tăng dần, NULL thường đứng trước giá trị không NULL; trong thứ tự giảm dần, NULL thường đứng sau. Điều này có thể làm thay đổi dòng mà `LAG()` hoặc `LEAD()` chọn.

Nếu thứ tự thời gian phải có ý nghĩa rõ ràng, ưu tiên cột thời gian `NOT NULL`. Nếu NULL hợp lệ, xác định vị trí của nhóm NULL một cách tường minh và thêm khóa duy nhất để phân định.

## 4. PARTITION BY tạo các phạm vi so sánh độc lập

`PARTITION BY` chia tập kết quả thành các nhóm độc lập. `LAG()` và `LEAD()` không đi qua ranh giới giữa các partition.

Ví dụ, so sánh số tiền đơn hàng trước đó của cùng khách hàng:

```sql
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_order_amount
FROM orders
ORDER BY customer_id, created_at, order_id;
```

Khi chuyển sang khách hàng mới, `LAG()` bắt đầu lại. Dòng đầu tiên của mỗi khách hàng không có dòng trước trong partition và nhận `NULL` nếu không khai báo default.

### 4.1. Không có PARTITION BY

Nếu bỏ `PARTITION BY`, toàn bộ tập hàng thuộc một partition:

```sql
SELECT
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER (
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders;
```

Lúc này, dòng đầu tiên có thể lấy dòng trước từ một khách hàng khác. Đây có thể là điều đúng nếu muốn so sánh toàn bộ luồng đơn hàng, nhưng thường không đúng nếu nghiệp vụ yêu cầu so sánh trong cùng khách hàng.

### 4.2. Nhiều cột trong PARTITION BY

Có thể chia nhóm theo nhiều thuộc tính:

```sql
LAG(stock_quantity) OVER (
    PARTITION BY warehouse_id, product_id
    ORDER BY snapshot_at, snapshot_id
)
```

Mỗi cặp kho/sản phẩm có một chuỗi riêng. Dùng nhiều cột partition khi dữ liệu chỉ có thể so sánh trong đúng phạm vi kết hợp đó.

## 5. LAG: đọc giá trị của dòng trước

### 5.1. Lấy giá trị trước đó

Giả sử bảng `monthly_sales` lưu doanh thu theo tháng:

```sql
SELECT
    store_id,
    sales_month,
    revenue,
    LAG(revenue) OVER (
        PARTITION BY store_id
        ORDER BY sales_month
    ) AS previous_revenue
FROM monthly_sales
ORDER BY store_id, sales_month;
```

Với mỗi cửa hàng, `previous_revenue` là doanh thu của dòng tháng đứng trước trong dữ liệu hiện có.

### 5.2. Tính chênh lệch tuyệt đối

```sql
WITH sales_with_previous AS (
    SELECT
        store_id,
        sales_month,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sales_month
        ) AS previous_revenue
    FROM monthly_sales
)
SELECT
    store_id,
    sales_month,
    revenue,
    previous_revenue,
    revenue - previous_revenue AS revenue_change
FROM sales_with_previous
ORDER BY store_id, sales_month;
```

Nếu doanh thu hiện tại lớn hơn trước đó, `revenue_change` dương; nếu nhỏ hơn, giá trị âm. Dòng đầu tiên của mỗi cửa hàng có `previous_revenue = NULL`, nên phép trừ cũng trả NULL.

### 5.3. Tính phần trăm thay đổi

Công thức:

\[
\text{change\_percent} =
\frac{\text{current} - \text{previous}}{\text{previous}} \times 100
\]

SQL cần xử lý trường hợp giá trị trước bằng 0 để tránh chia cho 0:

```sql
WITH sales_with_previous AS (
    SELECT
        store_id,
        sales_month,
        revenue,
        LAG(revenue) OVER (
            PARTITION BY store_id
            ORDER BY sales_month
        ) AS previous_revenue
    FROM monthly_sales
)
SELECT
    store_id,
    sales_month,
    revenue,
    previous_revenue,
    100.0 * (revenue - previous_revenue)
        / NULLIF(previous_revenue, 0) AS change_percent
FROM sales_with_previous
ORDER BY store_id, sales_month;
```

`NULLIF(previous_revenue, 0)` trả NULL khi giá trị trước bằng 0. Khi đó phần trăm thay đổi không được xác định theo công thức này và kết quả là NULL. Nếu nghiệp vụ muốn hiển thị nhãn như “mới phát sinh” khi từ 0 tăng lên dương, hãy xử lý bằng `CASE` thay vì tự gán một tỷ lệ phần trăm tùy ý.

## 6. LEAD: đọc giá trị của dòng sau

`LEAD()` đối xứng với `LAG()`: nó lấy biểu thức từ dòng đứng sau trong thứ tự cửa sổ.

Ví dụ lấy thời điểm sự kiện kế tiếp của từng đơn hàng:

```sql
SELECT
    order_id,
    history_id,
    status,
    changed_at,
    LEAD(changed_at) OVER (
        PARTITION BY order_id
        ORDER BY changed_at, history_id
    ) AS next_changed_at
FROM order_status_history
ORDER BY order_id, changed_at, history_id;
```

Dòng cuối cùng của mỗi đơn không có sự kiện tiếp theo và nhận NULL.

### 6.1. Tính khoảng thời gian tới sự kiện kế tiếp

```sql
WITH event_sequence AS (
    SELECT
        order_id,
        history_id,
        status,
        changed_at,
        LEAD(changed_at) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS next_changed_at
    FROM order_status_history
)
SELECT
    order_id,
    history_id,
    status,
    changed_at,
    next_changed_at,
    TIMESTAMPDIFF(SECOND, changed_at, next_changed_at)
        AS seconds_until_next_event
FROM event_sequence
ORDER BY order_id, changed_at, history_id;
```

`TIMESTAMPDIFF()` trả NULL nếu `next_changed_at` là NULL. Đây là kết quả hợp lý cho sự kiện cuối cùng vì không có thời điểm kế tiếp để tính khoảng cách.

### 6.2. Xác định thời gian một trạng thái tồn tại

Có thể dùng `LEAD()` để tạo khoảng thời gian hiệu lực của mỗi trạng thái:

```sql
WITH status_intervals AS (
    SELECT
        order_id,
        status,
        changed_at AS valid_from,
        LEAD(changed_at) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS valid_to
    FROM order_status_history
)
SELECT
    order_id,
    status,
    valid_from,
    valid_to,
    TIMESTAMPDIFF(SECOND, valid_from, valid_to) AS duration_seconds
FROM status_intervals
ORDER BY order_id, valid_from;
```

`valid_to` là thời điểm trạng thái kế tiếp bắt đầu. Với dòng cuối, có thể coi trạng thái còn hiệu lực đến thời điểm hiện tại hoặc đến một mốc nghiệp vụ khác; không nên tự dùng `NOW()` nếu báo cáo cần một thời điểm chốt cố định.

## 7. Offset và giá trị mặc định

Tham số `N` cho phép lấy nhiều hơn một dòng trước hoặc sau.

### 7.1. Lấy hai dòng trước hoặc sau

```sql
SELECT
    order_id,
    total_amount,
    LAG(total_amount, 2) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS amount_two_orders_before,
    LEAD(total_amount, 2) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS amount_two_orders_after
FROM orders
ORDER BY customer_id, created_at, order_id;
```

`LAG(..., 2)` lấy giá trị của dòng cách hiện tại hai vị trí về trước; `LEAD(..., 2)` lấy dòng cách hai vị trí về sau. Offset đếm hàng trong partition đã sắp xếp, không phải số ngày hoặc số tháng.

### 7.2. Đặt giá trị mặc định khi không có dòng lân cận

Đối số thứ ba là giá trị thay thế nếu dòng ở offset yêu cầu không tồn tại:

```sql
SELECT
    order_id,
    total_amount,
    LAG(total_amount, 1, 0) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount_or_zero
FROM orders;
```

Với dòng đầu tiên của mỗi khách hàng, `LAG()` trả 0 vì không có dòng trước. Chỉ dùng 0 nếu nghiệp vụ xác định rằng “không có đơn trước” nên được biểu diễn bằng 0.

### 7.3. Default khác với COALESCE

Đây là khác biệt quan trọng:

```sql
SELECT
    order_id,
    LAG(total_amount, 1, 0) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS lag_default,
    COALESCE(
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ),
        0
    ) AS lag_coalesced
FROM orders;
```

- `LAG(total_amount, 1, 0)` dùng 0 khi không có dòng trước. Nếu dòng trước tồn tại nhưng `total_amount` của nó là NULL, kết quả vẫn là NULL.
- `COALESCE(LAG(total_amount), 0)` thay mọi kết quả NULL bằng 0, bao gồm cả trường hợp không có dòng trước và trường hợp dòng trước có giá trị NULL.

Hãy chọn cách viết theo ý nghĩa dữ liệu. Không chuyển NULL thành 0 nếu NULL biểu thị “chưa biết” hoặc “không được ghi nhận”.

### 7.4. Offset bằng 0

Offset bằng 0 tham chiếu dòng hiện tại. Ví dụ `LAG(amount, 0)` lấy giá trị của chính dòng hiện tại. Trường hợp này thường không cần thiết vì có thể chọn trực tiếp `amount`; dùng offset 0 chỉ khi biểu thức được xây dựng động và có lý do rõ ràng.

## 8. Phân biệt dòng không tồn tại và giá trị NULL

Giá trị NULL từ `LAG()` hoặc `LEAD()` có thể có hai ý nghĩa:

1. Không tồn tại dòng ở vị trí được yêu cầu.
2. Dòng đó tồn tại nhưng biểu thức `expr` của nó có giá trị NULL.

Ví dụ:

```sql
CREATE TABLE measurements (
    sensor_id BIGINT NOT NULL,
    measured_at DATETIME NOT NULL,
    temperature DECIMAL(5,2) NULL,
    measurement_id BIGINT NOT NULL,
    PRIMARY KEY (measurement_id)
);
```

```sql
SELECT
    sensor_id,
    measurement_id,
    measured_at,
    temperature,
    LAG(temperature) OVER (
        PARTITION BY sensor_id
        ORDER BY measured_at, measurement_id
    ) AS previous_temperature,
    LAG(measurement_id) OVER (
        PARTITION BY sensor_id
        ORDER BY measured_at, measurement_id
    ) AS previous_measurement_id
FROM measurements;
```

Nếu `previous_measurement_id` là NULL ở dòng đầu partition, không có phép đo trước. Nếu `previous_measurement_id` có giá trị nhưng `previous_temperature` là NULL, phép đo trước tồn tại nhưng nhiệt độ không được ghi nhận.

Để phân biệt hai trường hợp, có thể lấy một cột khóa `NOT NULL` bằng cùng hàm LAG hoặc dùng một dấu hiệu hiện diện. Đừng chỉ dựa vào giá trị của cột nghiệp vụ có thể NULL.

### 8.1. NULL treatment trong MySQL

MySQL hỗ trợ cách xử lý `RESPECT NULLS` cho các window function liên quan. Đây cũng là hành vi mặc định: NULL ở dòng lân cận được giữ nguyên và được trả về. Cú pháp `IGNORE NULLS` hiện không được MySQL hỗ trợ thực thi; nếu dùng, MySQL báo lỗi.

Vì vậy, `LAG(value)` lấy dòng đứng trước theo vị trí, kể cả khi giá trị của dòng đó là NULL. Nó không tự bỏ qua các dòng NULL để tìm giá trị không NULL gần nhất.

Nếu nghiệp vụ cần “giá trị không NULL gần nhất trước đó”, phải xây dựng logic riêng, chẳng hạn đánh số các hàng có giá trị, dùng aggregate/window phụ trợ hoặc tạo một tập dữ liệu đã lọc trước khi nối lại. Cách làm phải giữ đúng quan hệ dòng và được kiểm tra kỹ; không thay `RESPECT NULLS` bằng `COALESCE()` vì hai thao tác có ngữ nghĩa khác nhau.

## 9. LAG/LEAD so sánh dòng liền kề, không phải kỳ lịch liền kề

Đây là điểm rất dễ nhầm khi làm báo cáo thời gian.

Giả sử bảng doanh thu có dữ liệu:

| sales_month | revenue |
|---|---:|
| 2026-01 | 100 |
| 2026-02 | 120 |
| 2026-04 | 160 |

Truy vấn:

```sql
SELECT
    sales_month,
    revenue,
    LAG(revenue) OVER (ORDER BY sales_month) AS previous_revenue
FROM monthly_sales;
```

Ở dòng tháng 4, `LAG()` trả 120 từ tháng 2 vì đó là dòng đứng trước trong tập dữ liệu. Nó không trả NULL và cũng không tự suy ra rằng tháng 3 bị thiếu.

Nếu câu hỏi là “so sánh với tháng trước theo lịch”, phải tạo đủ các tháng trong khoảng cần báo cáo, sau đó LEFT JOIN doanh thu vào chuỗi tháng đó.

### 9.1. Tạo chuỗi tháng trước khi dùng LAG

Với MySQL 8.0, có thể dùng recursive CTE để tạo các tháng:

```sql
WITH RECURSIVE months AS (
    SELECT CAST('2026-01-01' AS DATE) AS month_start
    UNION ALL
    SELECT month_start + INTERVAL 1 MONTH
    FROM months
    WHERE month_start < '2026-06-01'
), monthly_revenue AS (
    SELECT
        CAST(DATE_FORMAT(created_at, '%Y-%m-01') AS DATE) AS month_start,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE created_at >= '2026-01-01'
      AND created_at < '2026-07-01'
    GROUP BY CAST(DATE_FORMAT(created_at, '%Y-%m-01') AS DATE)
), complete_series AS (
    SELECT
        m.month_start,
        COALESCE(r.revenue, 0) AS revenue
    FROM months AS m
    LEFT JOIN monthly_revenue AS r
      ON r.month_start = m.month_start
), compared AS (
    SELECT
        month_start,
        revenue,
        LAG(revenue) OVER (ORDER BY month_start) AS previous_month_revenue
    FROM complete_series
)
SELECT
    month_start,
    revenue,
    previous_month_revenue,
    revenue - previous_month_revenue AS month_change
FROM compared
ORDER BY month_start;
```

Trong ví dụ, tháng 3 không có đơn được tạo thành một hàng với doanh thu 0. Khi đó, `LAG()` ở tháng 4 so sánh với tháng 3 theo lịch. Chỉ dùng `COALESCE(..., 0)` nếu tháng không có bản ghi phải được hiểu là doanh thu bằng 0; nếu dữ liệu thiếu có thể là lỗi thu thập, cần giữ NULL và phân biệt trạng thái dữ liệu.

### 9.2. Phân biệt khoảng thời gian và số dòng

`LAG(value, 7)` có nghĩa là lấy giá trị ở dòng trước bảy vị trí, không có nghĩa là bảy ngày trước. Nếu mỗi ngày có nhiều hàng, hoặc có ngày bị thiếu, hai khái niệm khác nhau hoàn toàn.

Muốn so sánh với một mốc thời gian cụ thể, hãy:

- Chuẩn hóa dữ liệu về đúng độ hạt thời gian (ngày, tuần, tháng) trước khi dùng window function.
- Tạo calendar/date dimension để bảo đảm các kỳ cần so sánh đều có hàng.
- Hoặc JOIN theo khóa thời gian đã tính như `DATE_SUB(current_date, INTERVAL 1 DAY)` khi logic chỉ cần một kỳ cụ thể.

## 10. Lọc kết quả của LAG/LEAD bằng CTE hoặc derived table

Window function được tính sau các bước `WHERE`, `GROUP BY` và `HAVING` trong cùng query block. Vì vậy, không thể đặt trực tiếp `LAG()` trong `WHERE` cùng cấp để lọc theo giá trị window vừa tính.

Ví dụ muốn tìm các đơn có giá trị cao hơn đơn trước của cùng khách hàng:

```sql
WITH order_comparison AS (
    SELECT
        customer_id,
        order_id,
        created_at,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
)
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    previous_amount,
    total_amount - previous_amount AS amount_increase
FROM order_comparison
WHERE previous_amount IS NOT NULL
  AND total_amount > previous_amount
ORDER BY customer_id, created_at, order_id;
```

CTE tính giá trị `previous_amount` trước; truy vấn ngoài mới lọc theo alias đó.

Có thể viết bằng derived table:

```sql
SELECT *
FROM (
    SELECT
        customer_id,
        order_id,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
) AS order_comparison
WHERE previous_amount IS NOT NULL
  AND total_amount > previous_amount;
```

CTE thường dễ đọc khi truy vấn có nhiều bước hoặc cần dùng lại kết quả; derived table phù hợp khi chỉ cần một lớp bọc đơn giản.

## 11. Dùng LAG để phát hiện thay đổi trạng thái

Giả sử `order_status_history` lưu lịch sử trạng thái. Có thể so sánh trạng thái hiện tại với trạng thái trước:

```sql
WITH status_changes AS (
    SELECT
        order_id,
        history_id,
        status,
        changed_at,
        LAG(status) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS previous_status
    FROM order_status_history
)
SELECT
    order_id,
    history_id,
    previous_status,
    status AS current_status,
    changed_at
FROM status_changes
WHERE previous_status IS NULL
   OR previous_status <> status
ORDER BY order_id, changed_at, history_id;
```

Điều kiện trên có một giới hạn: nếu `status` được phép NULL, `previous_status IS NULL` có thể có nghĩa là không có dòng trước hoặc dòng trước có status NULL. Nếu cần phân biệt, thêm `LAG(history_id)` để kiểm tra dòng trước có tồn tại. Nếu status là `NOT NULL`, điều kiện trên đơn giản hơn.

Một cách rõ ràng hơn khi `status` nullable:

```sql
WITH status_changes AS (
    SELECT
        order_id,
        history_id,
        status,
        changed_at,
        LAG(history_id) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS previous_history_id,
        LAG(status) OVER (
            PARTITION BY order_id
            ORDER BY changed_at, history_id
        ) AS previous_status
    FROM order_status_history
)
SELECT
    order_id,
    history_id,
    previous_status,
    status AS current_status,
    changed_at
FROM status_changes
WHERE previous_history_id IS NULL
   OR NOT (previous_status <=> status)
ORDER BY order_id, changed_at, history_id;
```

Toán tử `<=>` là phép so sánh bằng an toàn với NULL của MySQL. `NOT (previous_status <=> status)` phát hiện khác biệt kể cả khi một phía là NULL. Dòng đầu partition vẫn được giữ nhờ `previous_history_id IS NULL`.

## 12. Kết hợp LAG và LEAD trong cùng cửa sổ

Có thể dùng cả hai để xem giá trị trước, hiện tại và sau:

```sql
SELECT
    order_id,
    history_id,
    changed_at,
    status,
    LAG(status) OVER event_window AS previous_status,
    LEAD(status) OVER event_window AS next_status
FROM order_status_history
WINDOW event_window AS (
    PARTITION BY order_id
    ORDER BY changed_at, history_id
)
ORDER BY order_id, changed_at, history_id;
```

`WINDOW event_window AS (...)` đặt tên cho window specification để nhiều hàm dùng cùng partition và order. Đây là cách tránh lặp cùng một định nghĩa cửa sổ trong câu SQL dài.

Có thể thêm nhiều biểu thức:

```sql
SELECT
    account_id,
    transaction_id,
    amount,
    LAG(amount, 1) OVER w AS previous_amount,
    LAG(amount, 2) OVER w AS amount_two_rows_before,
    LEAD(amount, 1) OVER w AS next_amount
FROM account_transactions
WINDOW w AS (
    PARTITION BY account_id
    ORDER BY occurred_at, transaction_id
)
ORDER BY account_id, occurred_at, transaction_id;
```

## 13. Một số bài toán thực tế

### 13.1. Phát hiện khoảng trống giữa các sự kiện

```sql
WITH event_gaps AS (
    SELECT
        device_id,
        event_id,
        occurred_at,
        LAG(occurred_at) OVER (
            PARTITION BY device_id
            ORDER BY occurred_at, event_id
        ) AS previous_event_at
    FROM device_events
)
SELECT
    device_id,
    event_id,
    previous_event_at,
    occurred_at,
    TIMESTAMPDIFF(SECOND, previous_event_at, occurred_at) AS gap_seconds
FROM event_gaps
WHERE previous_event_at IS NOT NULL
  AND TIMESTAMPDIFF(SECOND, previous_event_at, occurred_at) > 3600
ORDER BY device_id, occurred_at, event_id;
```

Truy vấn tìm các khoảng cách giữa hai sự kiện liên tiếp lớn hơn một giờ. `event_id` làm tie-breaker khi timestamp trùng. Nếu một thiết bị có nhiều sự kiện cùng thời điểm, khoảng cách có thể bằng 0; điều đó không nhất thiết là dữ liệu lỗi.

### 13.2. So sánh tồn kho giữa hai lần chụp

```sql
SELECT
    warehouse_id,
    product_id,
    snapshot_at,
    quantity,
    LAG(quantity) OVER (
        PARTITION BY warehouse_id, product_id
        ORDER BY snapshot_at, snapshot_id
    ) AS previous_quantity,
    quantity - LAG(quantity) OVER (
        PARTITION BY warehouse_id, product_id
        ORDER BY snapshot_at, snapshot_id
    ) AS quantity_change
FROM inventory_snapshots
ORDER BY warehouse_id, product_id, snapshot_at, snapshot_id;
```

Mỗi cặp kho/sản phẩm có chuỗi riêng. Nếu chỉ cần tính một lần, có thể dùng CTE để đặt alias cho `LAG(quantity)` và tránh lặp biểu thức.

### 13.3. Tìm lần thay đổi giá kế tiếp

```sql
SELECT
    product_id,
    price,
    effective_from,
    LEAD(effective_from) OVER (
        PARTITION BY product_id
        ORDER BY effective_from, price_history_id
    ) AS next_effective_from
FROM product_price_history
ORDER BY product_id, effective_from, price_history_id;
```

Kết quả có thể dùng để xây dựng khoảng hiệu lực `[effective_from, next_effective_from)`. Với hàng cuối, `next_effective_from` là NULL; ứng dụng cần quy định thời điểm kết thúc mở hoặc mốc chốt báo cáo.

### 13.4. Tìm lần đăng nhập trước và khoảng cách giữa hai lần

```sql
WITH login_sequence AS (
    SELECT
        user_id,
        login_id,
        logged_in_at,
        LAG(logged_in_at) OVER (
            PARTITION BY user_id
            ORDER BY logged_in_at, login_id
        ) AS previous_login_at
    FROM user_logins
)
SELECT
    user_id,
    login_id,
    logged_in_at,
    previous_login_at,
    TIMESTAMPDIFF(MINUTE, previous_login_at, logged_in_at)
        AS minutes_since_previous_login
FROM login_sequence
ORDER BY user_id, logged_in_at, login_id;
```

Đây là một ví dụ hữu ích cho phân tích hành vi, nhưng cần bảo đảm múi giờ và độ chính xác thời gian được lưu nhất quán.

## 14. Hiệu năng và index

Window function thường cần dữ liệu theo đúng partition và thứ tự. Nếu bảng lớn, sắp xếp có thể tốn CPU, bộ nhớ và có thể dùng vùng lưu trữ tạm.

### 14.1. Index theo partition và order

Với truy vấn:

```sql
SELECT
    customer_id,
    order_id,
    created_at,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders;
```

Một index có thể đáng xem xét:

```sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at, order_id);
```

Thứ tự index đặt cột partition trước, sau đó là cột sắp xếp. Tuy nhiên, việc MySQL tận dụng index để tránh hoặc giảm sắp xếp phụ thuộc truy vấn đầy đủ, bộ lọc, hướng sắp xếp, phiên bản và execution plan.

### 14.2. Lọc hàng trước khi tính window

Nếu chỉ cần một khoảng thời gian, điều kiện `WHERE` trong cùng query block được áp dụng trước window function:

```sql
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01';
```

Điều này có nghĩa dòng đầu tiên trong khoảng năm 2026 không nhìn thấy đơn hàng cuối năm 2025. Nếu cần so sánh dòng đầu năm với dòng trước đó nằm ngoài khoảng báo cáo, phải đưa thêm dòng tiền nhiệm vào tập đầu vào rồi lọc kết quả ở query block bên ngoài.

Ví dụ, tính window trước rồi lọc ngày ở ngoài:

```sql
WITH sequenced_orders AS (
    SELECT
        customer_id,
        order_id,
        created_at,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
)
SELECT *
FROM sequenced_orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2027-01-01'
ORDER BY customer_id, created_at, order_id;
```

Trong phiên bản này, LAG có thể nhìn thấy hàng năm trước vì truy vấn con không lọc năm 2026 trước khi tính window. Đổi lại, server có thể phải xử lý nhiều hàng hơn.

### 14.3. Dùng EXPLAIN

```sql
EXPLAIN
SELECT
    customer_id,
    order_id,
    created_at,
    LAG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS previous_amount
FROM orders;
```

Kiểm tra access path, index được chọn, số hàng ước lượng và các bước sort/materialize. MySQL 8.0.18 trở lên có `EXPLAIN ANALYZE` cho các truy vấn phù hợp; lệnh này thực thi truy vấn nên cần đánh giá tải trước khi chạy trên production.

Không tạo index chỉ vì có `LAG()` hoặc `LEAD()`. Hãy dựa vào workload, điều kiện lọc và thứ tự cửa sổ. Index rộng làm tăng dung lượng và chi phí ghi.

## 15. Giới hạn và lỗi thường gặp

| Lỗi/tình huống | Hệ quả | Cách xử lý |
|---|---|---|
| Không khai báo ORDER BY trong OVER | Không có thứ tự trước/sau có ý nghĩa xác định | Định nghĩa thứ tự nghiệp vụ rõ ràng |
| ORDER BY có giá trị trùng nhưng thiếu tie-breaker | Dòng được chọn làm trước/sau có thể không ổn định | Thêm primary key hoặc unique key vào cuối thứ tự |
| Quên PARTITION BY | LAG/LEAD có thể lấy dữ liệu từ nhóm khác | Chia partition theo khóa nghiệp vụ |
| Nghĩ LAG(..., 7) là bảy ngày trước | Offset đếm dòng, không đếm đơn vị thời gian | Tạo chuỗi ngày/tháng đầy đủ hoặc JOIN theo mốc thời gian |
| Nghĩ default thay mọi NULL | Default chỉ áp dụng khi dòng offset không tồn tại | Dùng COALESCE nếu cần thay cả NULL của dòng tồn tại |
| Dùng COALESCE làm mất ý nghĩa NULL | Không phân biệt được dữ liệu thiếu và giá trị 0 | Giữ NULL hoặc thêm cột nhận diện dòng trước |
| Đặt LAG trong WHERE cùng cấp | Window function chưa được tính ở giai đoạn WHERE | Bọc bằng CTE hoặc derived table rồi lọc ở ngoài |
| Dùng IGNORE NULLS | MySQL không hỗ trợ thực thi null treatment này | Dùng logic truy vấn khác đã kiểm thử |
| Lọc khoảng thời gian trước window nhưng cần dòng trước ngoài khoảng | Dòng đầu báo cáo nhận NULL dù có dữ liệu trước đó | Tính window trên tập rộng hơn rồi lọc ở query block ngoài |
| Không kiểm tra index/sort | Truy vấn lớn có thể phải sắp xếp nhiều dữ liệu | Dùng EXPLAIN và đo thực tế |

## 16. Bộ truy vấn kiểm tra nhanh

```sql
-- Lấy dòng trước và sau trong mỗi khách hàng
SELECT
    customer_id,
    order_id,
    created_at,
    total_amount,
    LAG(total_amount) OVER w AS previous_amount,
    LEAD(total_amount) OVER w AS next_amount
FROM orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
)
ORDER BY customer_id, created_at, order_id;

-- Chênh lệch với dòng trước, bảo vệ phép chia cho 0
WITH compared AS (
    SELECT
        customer_id,
        order_id,
        total_amount,
        LAG(total_amount) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS previous_amount
    FROM orders
)
SELECT
    customer_id,
    order_id,
    total_amount - previous_amount AS amount_change,
    100.0 * (total_amount - previous_amount)
        / NULLIF(previous_amount, 0) AS change_percent
FROM compared;

-- Khoảng cách tới sự kiện kế tiếp
SELECT
    order_id,
    changed_at,
    LEAD(changed_at) OVER (
        PARTITION BY order_id
        ORDER BY changed_at, history_id
    ) AS next_changed_at
FROM order_status_history;
```

Các tên bảng/cột là ví dụ. Trước khi dùng, thay bằng schema thực tế và xác nhận khóa dùng trong `PARTITION BY`/`ORDER BY` tạo đúng chuỗi nghiệp vụ.

## 17. Checklist trước khi đưa vào production

- [ ] Đã xác định rõ “dòng trước/sau” theo thời gian, mã hay thứ tự nghiệp vụ nào.
- [ ] `OVER(...)` có `ORDER BY` rõ ràng.
- [ ] Đã thêm tie-breaker duy nhất khi sort key có thể trùng.
- [ ] `PARTITION BY` phản ánh đúng phạm vi so sánh.
- [ ] Offset là số dòng mong muốn, không bị nhầm với ngày/tháng.
- [ ] Giá trị default chỉ dùng cho trường hợp không tồn tại dòng lân cận.
- [ ] Đã phân biệt dòng không tồn tại với cột có giá trị NULL.
- [ ] Đã xác định có cần giữ NULL hay thay bằng 0/chuỗi khác.
- [ ] Nếu cần so sánh kỳ lịch, đã tạo đầy đủ calendar/time series.
- [ ] Nếu lọc kết quả window, đã dùng CTE/derived table ở query block ngoài.
- [ ] Đã kiểm tra tác động của WHERE trước window tới dòng tiền nhiệm.
- [ ] Index và execution plan đã được đánh giá bằng dữ liệu đại diện.
- [ ] Đã kiểm thử partition chỉ có một dòng, nhiều dòng trùng timestamp và dòng đầu/cuối.

## 18. Kết luận

`LAG()` và `LEAD()` giúp truy cập giá trị ở dòng trước hoặc dòng sau trong một cửa sổ mà không phải tự JOIN bảng với chính nó. `PARTITION BY` xác định phạm vi so sánh, `ORDER BY` xác định thứ tự dòng, offset chọn khoảng cách theo số hàng và default chỉ được dùng khi dòng ở vị trí đó không tồn tại.

Để kết quả đáng tin cậy, hãy khai báo thứ tự ổn định với tie-breaker duy nhất, phân biệt NULL với dòng không tồn tại và nhớ rằng offset không phải khoảng thời gian. Khi cần so sánh kỳ lịch, tạo chuỗi thời gian đầy đủ trước khi dùng window function. Dùng CTE để lọc kết quả sau khi tính LAG/LEAD và kiểm tra execution plan trên dữ liệu thực tế trước khi triển khai.

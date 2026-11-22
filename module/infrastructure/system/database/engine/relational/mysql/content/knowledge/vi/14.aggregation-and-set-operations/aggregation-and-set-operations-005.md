# Tổng hợp có điều kiện bằng CASE hoặc biểu thức logic

Trong báo cáo, bạn thường cần nhiều chỉ tiêu trên cùng một tập dữ liệu: tổng số đơn, số đơn đã thanh toán, số đơn đang chờ, doanh thu đã thu, doanh thu bị hủy hoặc số khách hàng đã mua hàng. Nếu chạy một truy vấn riêng cho từng chỉ tiêu, ứng dụng phải gửi nhiều câu SQL và có nguy cơ mỗi truy vấn nhìn thấy một trạng thái dữ liệu khác nhau. **Conditional aggregation** giải quyết vấn đề này bằng cách đặt điều kiện bên trong hàm tổng hợp, nhờ đó nhiều chỉ tiêu có thể được tính trong cùng một lần nhóm dữ liệu.

Trong MySQL, cách phổ biến nhất là kết hợp `CASE` với `SUM()`, `COUNT()`, `AVG()`, `MIN()`, `MAX()` hoặc `COUNT(DISTINCT ...)`. Với điều kiện đơn giản, biểu thức logic của MySQL cũng có thể được cộng bằng `SUM(condition)`, vì kết quả điều kiện thường là `1`, `0` hoặc `NULL`. Tuy nhiên, phải hiểu rõ logic ba giá trị của SQL và xử lý `NULL` có chủ đích để không đếm sai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích conditional aggregation và lý do dùng nó để tính nhiều chỉ tiêu trong một truy vấn.
- Dùng `SUM(CASE WHEN ... THEN ... ELSE ... END)` để tính tổng có điều kiện.
- Dùng `COUNT(CASE WHEN ... THEN ... END)` và `COUNT(DISTINCT CASE ... END)` để đếm có điều kiện.
- Dùng biểu thức logic trong `SUM()` theo quy tắc boolean của MySQL.
- Phân biệt `ELSE 0` và `ELSE NULL`, cũng như tác động của `NULL` đến hàm tổng hợp.
- Xây dựng báo cáo dạng pivot bằng nhiều biểu thức tổng hợp có điều kiện.
- Phân biệt điều kiện lọc toàn bộ nguồn ở `WHERE` với điều kiện riêng của từng chỉ tiêu.
- Kết hợp conditional aggregation với `GROUP BY`, `HAVING`, `LEFT JOIN` và tỷ lệ phần trăm.

## 1. Dữ liệu thực hành

Các ví dụ dùng bảng đơn hàng theo khu vực. Hãy chạy trong database sandbox:

```sql
CREATE TABLE sales_region (
    region_id INT NOT NULL,
    region_name VARCHAR(40) NOT NULL,
    PRIMARY KEY (region_id),
    UNIQUE KEY uq_sales_region_name (region_name)
) ENGINE = InnoDB;

CREATE TABLE sales_order_agg (
    order_id BIGINT UNSIGNED NOT NULL,
    region_id INT NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    sales_rep VARCHAR(80) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    order_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_sales_order_agg_region_date (region_id, order_date),
    KEY idx_sales_order_agg_customer (customer_id),
    CONSTRAINT fk_sales_order_agg_region
        FOREIGN KEY (region_id)
        REFERENCES sales_region (region_id)
) ENGINE = InnoDB;

INSERT INTO sales_region (region_id, region_name)
VALUES
    (1, 'North'),
    (2, 'South'),
    (3, 'West'),
    (4, 'East');

INSERT INTO sales_order_agg
    (order_id, region_id, customer_id, sales_rep,
     order_status, order_date, amount)
VALUES
    (101, 1, 1001, 'An',   'PAID',      '2025-01-02', 120.00),
    (102, 1, 1002, 'Binh', 'PENDING',   '2025-01-03',  80.00),
    (103, 1, 1001, 'An',   'CANCELLED', '2025-01-04',  50.00),
    (104, 2, 1003, 'Chi',  'PAID',      '2025-01-02', 200.00),
    (105, 2, 1004, 'Dung', 'PAID',      '2025-01-05', 150.00),
    (106, 2, 1003, 'Chi',  'REFUNDED',  '2025-01-06', 200.00),
    (107, 1, 1005, 'An',   'PAID',      '2025-02-01', 300.00),
    (108, 3, 1006, 'Hoa',  'PENDING',   '2025-02-02',  60.00),
    (109, 3, 1006, 'Hoa',  'PAID',      '2025-02-03',  90.00),
    (110, 3, 1007, 'Lam',  'CANCELLED', '2025-02-04',  40.00);
```

Khu vực `East` chưa có đơn hàng. Tình huống này sẽ được dùng để minh họa cách giữ các nhóm không có dữ liệu khi báo cáo qua `LEFT JOIN`. Cột `amount` là `DECIMAL` để các ví dụ tiền tệ không dựa trên số thực dấu phẩy động.

Kiểm tra dữ liệu:

```sql
SELECT
    order_id,
    region_id,
    customer_id,
    order_status,
    order_date,
    amount
FROM sales_order_agg
ORDER BY order_id;
```

## 2. Conditional aggregation là gì?

Thông thường, hàm tổng hợp xử lý tất cả hàng trong nhóm:

```sql
SELECT
    region_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM sales_order_agg
GROUP BY region_id;
```

Nếu cần chỉ tính các đơn đã thanh toán, có thể đặt điều kiện trong biểu thức của hàm tổng hợp:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN 1 END) AS paid_order_count,
    SUM(CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END) AS paid_amount
FROM sales_order_agg
GROUP BY region_id;
```

Mỗi hàng vẫn tham gia nhóm theo `region_id`, nhưng chỉ những hàng thỏa điều kiện mới đóng góp vào chỉ tiêu thanh toán. Các hàng khác đóng góp `NULL` cho phép đếm hoặc `0` cho phép tính tổng.

Điểm mạnh của cách này là có thể tính nhiều chỉ tiêu song song:

```sql
SELECT
    region_id,
    COUNT(*) AS all_orders,
    COUNT(CASE WHEN order_status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN order_status = 'PENDING' THEN 1 END) AS pending_orders,
    COUNT(CASE WHEN order_status = 'CANCELLED' THEN 1 END) AS cancelled_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_amount,
    SUM(CASE WHEN order_status = 'PENDING' THEN amount ELSE 0 END) AS pending_amount
FROM sales_order_agg
GROUP BY region_id
ORDER BY region_id;
```

Truy vấn chỉ cần đọc tập hàng nguồn một lần theo kế hoạch thực thi được chọn, rồi tính các biểu thức tổng hợp cho từng nhóm. Optimizer vẫn quyết định cách đọc dữ liệu và cách thực hiện phép nhóm; không nên diễn giải điều này thành cam kết rằng mọi biểu thức luôn được tính trong một lượt quét vật lý duy nhất.

## 3. CASE dùng trong hàm tổng hợp

MySQL hỗ trợ hai dạng `CASE`:

**Searched CASE** kiểm tra lần lượt các điều kiện:

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE default_result
END
```

**Simple CASE** so sánh một biểu thức với các giá trị:

```sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ELSE default_result
END
```

Trong conditional aggregation, searched CASE thường linh hoạt hơn vì điều kiện có thể kết hợp nhiều cột và toán tử logic.

### 3.1. CASE trong SUM

Mẫu tổng quát:

```sql
SUM(
    CASE
        WHEN condition THEN numeric_value
        ELSE 0
    END
)
```

Ví dụ tính doanh thu của các đơn đã thanh toán:

```sql
SELECT
    region_id,
    SUM(
        CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END
    ) AS paid_revenue
FROM sales_order_agg
GROUP BY region_id;
```

Với mỗi hàng, CASE trả về `amount` nếu đơn đã thanh toán và `0` nếu không. `SUM()` cộng các giá trị đó trong từng nhóm.

Nếu cần tính tổng cho nhiều điều kiện, mỗi chỉ tiêu dùng một CASE riêng:

```sql
SELECT
    region_id,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN order_status = 'REFUNDED' THEN amount ELSE 0 END) AS refunded_amount,
    SUM(CASE WHEN order_status = 'CANCELLED' THEN amount ELSE 0 END) AS cancelled_amount
FROM sales_order_agg
GROUP BY region_id;
```

### 3.2. CASE trong COUNT

`COUNT(expression)` chỉ đếm các giá trị khác `NULL`. Vì vậy, mẫu đếm có điều kiện thường trả về một giá trị không null khi điều kiện đúng và bỏ qua các hàng còn lại:

```sql
COUNT(CASE WHEN condition THEN 1 END)
```

Ví dụ:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) AS paid_orders,
    COUNT(CASE WHEN order_status = 'PENDING' THEN order_id END) AS pending_orders
FROM sales_order_agg
GROUP BY region_id;
```

Không cần viết `ELSE 0` trong biểu thức đếm này. Nếu thêm `ELSE 0`, mọi hàng đều tạo ra một giá trị khác null và `COUNT()` sẽ đếm cả hàng không thỏa điều kiện:

```sql
-- Sai nếu mục tiêu là đếm riêng các đơn PAID:
COUNT(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END)
```

Biểu thức trên đếm tất cả hàng vì cả `1` và `0` đều khác `NULL`. Hãy dùng `COUNT(CASE WHEN ... THEN 1 END)` hoặc `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.

### 3.3. CASE trong AVG

Để tính trung bình trên các hàng thỏa điều kiện, có thể trả về giá trị cần lấy trung bình khi đúng và `NULL` khi sai:

```sql
SELECT
    region_id,
    AVG(CASE
            WHEN order_status = 'PAID' THEN amount
        END) AS average_paid_order
FROM sales_order_agg
GROUP BY region_id;
```

`AVG()` bỏ qua `NULL`, vì vậy chỉ các đơn đã thanh toán tham gia cả tử số lẫn mẫu số. Nếu viết `ELSE 0`, các hàng không thỏa điều kiện sẽ tham gia mẫu số với giá trị 0 và làm giảm trung bình; kết quả đó mang ý nghĩa khác.

## 4. CASE kết hợp biểu thức logic

Điều kiện của CASE có thể dùng `AND`, `OR`, `NOT`, so sánh số, khoảng giá trị hoặc kiểm tra null. Ví dụ, đếm các đơn đã thanh toán có giá trị ít nhất 150:

```sql
SELECT
    region_id,
    COUNT(
        CASE
            WHEN order_status = 'PAID' AND amount >= 150
            THEN order_id
        END
    ) AS large_paid_orders
FROM sales_order_agg
GROUP BY region_id;
```

Để tính doanh thu của các đơn có trạng thái thanh toán hoặc hoàn tiền:

```sql
SELECT
    region_id,
    SUM(
        CASE
            WHEN order_status IN ('PAID', 'REFUNDED')
            THEN amount
            ELSE 0
        END
    ) AS settled_or_refunded_amount
FROM sales_order_agg
GROUP BY region_id;
```

Khi dùng `AND` và `OR` cùng nhau, đặt ngoặc để thể hiện đúng ý định:

```sql
CASE
    WHEN order_status = 'PAID'
         AND (amount >= 200 OR region_id = 1)
    THEN amount
    ELSE 0
END
```

Không dựa vào việc người đọc nhớ thứ tự ưu tiên toán tử. Ngoặc giúp điều kiện dễ rà soát và ít bị thay đổi logic khi bổ sung tiêu chí.

## 5. Dùng biểu thức boolean trực tiếp trong SUM

Trong MySQL, biểu thức điều kiện có thể được chuyển thành giá trị số trong ngữ cảnh số:

- Điều kiện đúng trả về `1`.
- Điều kiện sai trả về `0`.
- Điều kiện không xác định do `NULL` trả về `NULL`.

Vì vậy, với cột `order_status` được khai báo `NOT NULL`, có thể viết:

```sql
SELECT
    region_id,
    SUM(order_status = 'PAID') AS paid_orders,
    SUM(order_status = 'PENDING') AS pending_orders,
    SUM(order_status = 'CANCELLED') AS cancelled_orders
FROM sales_order_agg
GROUP BY region_id;
```

Đây là cách viết ngắn gọn theo đặc tính của MySQL. Nó có cùng kết quả đếm với:

```sql
SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END)
```

### 5.1. Khi nào nên dùng CASE thay cho SUM(condition)?

Biểu thức boolean ngắn gọn khi chỉ cần đếm điều kiện đơn giản và cột tham gia không null. CASE rõ nghĩa hơn khi:

- Cần tính tổng một giá trị khác nhau cho mỗi hàng.
- Cần nhiều nhánh phân loại.
- Điều kiện có thể trả về `UNKNOWN` do cột nullable.
- Muốn thể hiện rõ giá trị mặc định cho trường hợp không thỏa.
- Muốn giữ cách viết dễ chuyển giữa nhiều hệ quản trị SQL.

Ví dụ cột trạng thái nullable:

```sql
SELECT
    SUM(order_status = 'PAID') AS paid_count_using_boolean,
    SUM(CASE
            WHEN order_status = 'PAID' THEN 1
            ELSE 0
        END) AS paid_count_explicit
FROM some_legacy_orders;
```

Nếu `order_status` là `NULL`, phép so sánh `order_status = 'PAID'` trả về `NULL`. `SUM()` bỏ qua giá trị null đó. CASE chỉ đi vào nhánh WHEN khi điều kiện là TRUE; FALSE hoặc UNKNOWN đều đi tới ELSE và trả về 0. Hai cách có thể cho cùng kết quả đếm trong ví dụ này, nhưng CASE làm rõ việc mỗi hàng không khớp đóng góp 0.

### 5.2. Không nhầm SUM(condition) với COUNT(condition)

`COUNT(expression)` đếm mọi giá trị khác null. Điều kiện sai thường trả về 0, mà 0 không phải null:

```sql
SELECT
    COUNT(order_status = 'PAID') AS count_of_non_null_predicates,
    SUM(order_status = 'PAID') AS number_of_paid_orders
FROM sales_order_agg;
```

Vì `order_status` là `NOT NULL`, `COUNT(order_status = 'PAID')` đếm tất cả đơn hàng, không chỉ đơn đã thanh toán. Dùng `SUM(condition)` hoặc `COUNT(CASE WHEN condition THEN 1 END)` để đếm số hàng thỏa điều kiện.

## 6. COUNT(IF(...)) và COUNT(DISTINCT CASE ...)

MySQL có hàm `IF(condition, value_if_true, value_if_false)`. Có thể dùng nó cùng `COUNT()`:

```sql
SELECT
    region_id,
    COUNT(IF(order_status = 'PAID', order_id, NULL)) AS paid_order_count
FROM sales_order_agg
GROUP BY region_id;
```

Khi điều kiện đúng, IF trả về `order_id`; khi sai, trả về `NULL`. COUNT chỉ đếm các giá trị khác null. Cách này ngắn nhưng `IF()` là hàm riêng của MySQL; `CASE` là biểu thức SQL dễ đọc và dễ chuyển đổi hơn giữa các hệ quản trị.

Đếm số khách hàng khác nhau đã có ít nhất một đơn thanh toán:

```sql
SELECT
    region_id,
    COUNT(
        DISTINCT CASE
            WHEN order_status = 'PAID' THEN customer_id
        END
    ) AS paid_customers
FROM sales_order_agg
GROUP BY region_id;
```

Các hàng không phải `PAID` tạo ra `NULL`; `COUNT(DISTINCT ...)` bỏ qua null và đếm mỗi customer ID khác nhau một lần. Đây là mẫu hữu ích khi một khách hàng có nhiều đơn hàng nhưng chỉ muốn đếm khách đã tham gia một trạng thái cụ thể.

Không viết `COUNT(DISTINCT customer_id)` nếu mục tiêu là đếm riêng khách có đơn PAID: cách viết đó đếm khách hàng ở mọi trạng thái trong tập nguồn.

## 7. Tính nhiều chỉ tiêu trong cùng một GROUP BY

Một báo cáo theo khu vực có thể đồng thời tính số lượng, doanh thu, giá trị trung bình và số khách hàng duy nhất theo trạng thái:

```sql
SELECT
    r.region_name,
    COUNT(o.order_id) AS all_orders,
    COUNT(CASE WHEN o.order_status = 'PAID' THEN o.order_id END) AS paid_orders,
    COUNT(CASE WHEN o.order_status = 'PENDING' THEN o.order_id END) AS pending_orders,
    COUNT(CASE WHEN o.order_status = 'CANCELLED' THEN o.order_id END) AS cancelled_orders,
    SUM(CASE WHEN o.order_status = 'PAID' THEN o.amount ELSE 0 END) AS paid_revenue,
    AVG(CASE WHEN o.order_status = 'PAID' THEN o.amount END) AS average_paid_order,
    COUNT(DISTINCT CASE
        WHEN o.order_status = 'PAID' THEN o.customer_id
    END) AS paid_customers
FROM sales_region AS r
LEFT JOIN sales_order_agg AS o
    ON o.region_id = r.region_id
GROUP BY r.region_id, r.region_name
ORDER BY r.region_id;
```

Kết quả có một hàng cho mỗi khu vực, kể cả `East` chưa có đơn. Với khu vực không có đơn:

- `COUNT(o.order_id)` trả về 0 vì phía đơn hàng là null-extended row.
- Các biểu thức CASE cho số đơn và doanh thu trả về 0 hoặc không có giá trị đóng góp.
- `AVG(...)` trả về `NULL` vì không có đơn PAID nào để tính trung bình.
- `COUNT(DISTINCT ...)` trả về 0.

Sự khác nhau giữa 0 và `NULL` ở đây có ý nghĩa: doanh thu cộng dồn không có đơn có thể được báo cáo là 0, trong khi giá trị trung bình không có mẫu để tính nên là `NULL`. Nếu giao diện cần hiển thị trung bình là 0, hãy quyết định rõ ở tầng báo cáo bằng `COALESCE()`, không mặc định rằng hai trạng thái có cùng ý nghĩa.

### 7.1. Đặt điều kiện thời gian đúng vị trí với LEFT JOIN

Nếu chỉ muốn báo cáo một khoảng ngày nhưng vẫn giữ khu vực không có đơn trong khoảng đó, đặt điều kiện ngày ở mệnh đề `ON`:

```sql
SELECT
    r.region_name,
    COUNT(o.order_id) AS order_count,
    SUM(CASE WHEN o.order_status = 'PAID' THEN o.amount ELSE 0 END) AS paid_revenue
FROM sales_region AS r
LEFT JOIN sales_order_agg AS o
    ON o.region_id = r.region_id
   AND o.order_date >= '2025-01-01'
   AND o.order_date <  '2025-02-01'
GROUP BY r.region_id, r.region_name
ORDER BY r.region_id;
```

Nếu chuyển hai điều kiện ngày của bảng `o` xuống `WHERE`, các hàng không có đơn có giá trị `o.order_date = NULL` sẽ bị loại; kết quả thực tế sẽ mất các khu vực không có đơn và làm mất tác dụng giữ hàng của LEFT JOIN.

## 8. WHERE lọc nguồn, CASE lọc từng chỉ tiêu

Đây là quyết định quan trọng khi viết báo cáo. `WHERE` loại hàng khỏi toàn bộ quá trình tổng hợp; điều kiện trong CASE chỉ quyết định hàng đóng góp vào biểu thức tổng hợp cụ thể.

Ví dụ, báo cáo muốn đếm cả PAID, PENDING và CANCELLED trong tháng 1:

```sql
SELECT
    region_id,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN order_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_orders,
    SUM(CASE WHEN order_status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders
FROM sales_order_agg
WHERE order_date >= '2025-01-01'
  AND order_date <  '2025-02-01'
GROUP BY region_id;
```

Điều kiện ngày được đặt trong WHERE vì tất cả chỉ tiêu đều chỉ xét tháng 1. Điều kiện trạng thái được đặt trong từng CASE vì mỗi chỉ tiêu cần một tập con khác nhau của các hàng còn lại.

Nếu viết:

```sql
WHERE order_status = 'PAID'
```

thì các đơn PENDING và CANCELLED bị loại khỏi nguồn trước khi nhóm. Các cột đếm PENDING và CANCELLED trong select list khi đó luôn bằng 0; truy vấn không còn khả năng báo cáo đồng thời các trạng thái đó.

Quy tắc thực hành:

- Đặt ở `WHERE` điều kiện giới hạn nguồn chung cho mọi chỉ tiêu.
- Đặt trong `CASE` điều kiện chỉ áp dụng cho một hoặc một nhóm chỉ tiêu.
- Đặt ở `HAVING` điều kiện lọc nhóm sau khi đã tính các chỉ tiêu tổng hợp.

## 9. Phân loại bằng CASE rồi tổng hợp theo nhóm

CASE không chỉ dùng bên trong SUM/COUNT. Nó còn có thể phân loại từng hàng thành một nhóm nghiệp vụ, sau đó dùng kết quả phân loại trong GROUP BY.

Ví dụ chia đơn hàng thành ba mức giá trị:

```sql
WITH classified_orders AS (
    SELECT
        order_id,
        region_id,
        amount,
        CASE
            WHEN amount >= 200 THEN 'HIGH'
            WHEN amount >= 100 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS amount_band
    FROM sales_order_agg
)
SELECT
    region_id,
    amount_band,
    COUNT(*) AS order_count,
    SUM(amount) AS band_amount
FROM classified_orders
GROUP BY region_id, amount_band
ORDER BY region_id, amount_band;
```

CASE được kiểm tra từ trên xuống; nhánh WHEN đầu tiên đúng sẽ quyết định kết quả. Vì vậy, thứ tự điều kiện quan trọng. Nếu đặt `amount >= 100` trước `amount >= 200`, các hàng có amount 200 trở lên sẽ được xếp vào MEDIUM và không bao giờ tới nhánh HIGH.

Các khoảng phân loại trong ví dụ không chồng lấn về kết quả vì CASE chọn nhánh đầu tiên phù hợp. Nếu viết nhiều conditional aggregates riêng, các chỉ tiêu có thể chồng lấn có chủ ý, ví dụ đếm tất cả đơn PAID và đồng thời đếm tập con PAID có giá trị cao. Hãy xác định rõ chỉ tiêu là nhóm loại trừ nhau hay các tập điều kiện độc lập.

## 10. Tạo báo cáo dạng pivot bằng conditional aggregation

Pivot là cách chuyển các giá trị phân loại thành các cột. MySQL không có cú pháp `PIVOT` chuyên biệt như một số hệ quản trị khác, nhưng có thể tạo cột báo cáo bằng các hàm tổng hợp có điều kiện.

Ví dụ, mỗi khu vực thành một hàng và mỗi trạng thái thành một cột:

```sql
SELECT
    r.region_name,
    SUM(CASE WHEN o.order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_count,
    SUM(CASE WHEN o.order_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_count,
    SUM(CASE WHEN o.order_status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_count,
    SUM(CASE WHEN o.order_status = 'REFUNDED' THEN 1 ELSE 0 END) AS refunded_count
FROM sales_region AS r
LEFT JOIN sales_order_agg AS o
    ON o.region_id = r.region_id
GROUP BY r.region_id, r.region_name
ORDER BY r.region_id;
```

Mỗi biểu thức CASE tạo một cột riêng. Nếu có thêm trạng thái mới, báo cáo cần được cập nhật để có cột tương ứng. Khi danh mục trạng thái thay đổi thường xuyên hoặc không biết trước, cân nhắc trả kết quả theo hàng (region, status, count) rồi để tầng ứng dụng pivot động.

## 11. Tính tỷ lệ và phần trăm có điều kiện

Conditional aggregation thường được dùng để tính tỷ lệ chuyển đổi, tỷ lệ đơn đã thanh toán hoặc tỷ trọng doanh thu.

Ví dụ tỷ lệ đơn PAID trên tổng đơn theo khu vực:

```sql
SELECT
    region_id,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    ROUND(
        100.0 * SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_percent
FROM sales_order_agg
GROUP BY region_id;
```

`NULLIF(denominator, 0)` trả về `NULL` nếu mẫu số bằng 0, tránh lỗi chia cho 0. Trong truy vấn nhóm có ít nhất một hàng thì `COUNT(*)` không bằng 0, nhưng cách viết này hữu ích khi công thức được tái sử dụng trong truy vấn phức tạp hoặc kết hợp với bảng dimension có thể không có dữ liệu.

Phải xác định đúng mẫu số theo nghiệp vụ. Tỷ lệ PAID trên tất cả đơn khác với tỷ lệ PAID trên số đơn đã xử lý (loại PENDING), và khác với tỷ lệ PAID trên số khách hàng. Không thay đổi mẫu số mà không nêu rõ định nghĩa chỉ tiêu.

Ví dụ tỷ trọng doanh thu PAID trên tổng doanh thu của các đơn:

```sql
SELECT
    region_id,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_amount,
    SUM(amount) AS all_amount,
    ROUND(
        100.0 * SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END)
        / NULLIF(SUM(amount), 0),
        2
    ) AS paid_amount_share_percent
FROM sales_order_agg
GROUP BY region_id;
```

Nếu amount có thể âm (ví dụ bút toán điều chỉnh) hoặc trạng thái refund được lưu thành số âm, cần định nghĩa lại cách tính doanh thu và mẫu số. Không suy ra ý nghĩa kế toán chỉ từ tên cột.

## 12. NULL và ELSE trong conditional aggregation

SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Điều kiện so sánh với `NULL` thường cho UNKNOWN. Trong CASE, chỉ điều kiện TRUE mới chọn nhánh WHEN; FALSE và UNKNOWN đi tiếp đến nhánh sau hoặc ELSE.

Ba biểu thức dưới đây có ý nghĩa khác nhau:

```sql
CASE WHEN condition THEN amount ELSE 0 END

CASE WHEN condition THEN amount ELSE NULL END

CASE WHEN condition THEN amount END
```

Hai biểu thức cuối tương đương nhau vì CASE không có ELSE mặc định trả về `NULL`.

### 12.1. ELSE 0 khi muốn tổng không có đóng góp bằng 0

```sql
SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END)
```

Hàng không phải PAID đóng góp 0. Nếu một nhóm có hàng nhưng không có đơn PAID, tổng có điều kiện là 0. Đây thường là cách phù hợp cho chỉ tiêu doanh thu cộng dồn cần hiển thị 0 khi không có giao dịch.

### 12.2. ELSE NULL khi muốn bỏ hàng khỏi phép tổng hợp

```sql
AVG(CASE WHEN order_status = 'PAID' THEN amount END)
```

Hàng không phải PAID trả về NULL và bị AVG bỏ qua. Đây là cách phù hợp để tính trung bình chỉ trên tập đơn PAID. Nếu thay bằng ELSE 0, các hàng không PAID làm tăng mẫu số và kéo trung bình xuống.

### 12.3. Tổng hợp trên tập nguồn rỗng

Với truy vấn tổng hợp không có GROUP BY, MySQL vẫn trả một hàng kết quả. `COUNT(*)` trả 0, nhưng `SUM(...)` trả NULL nếu không có hàng đầu vào:

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_amount
FROM sales_order_agg
WHERE order_date >= '2030-01-01'
  AND order_date <  '2030-02-01';
```

Nếu giao diện cần tổng luôn là số 0 khi nguồn rỗng, bọc kết quả bằng `COALESCE()`:

```sql
SELECT
    COUNT(*) AS row_count,
    COALESCE(
        SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END),
        0
    ) AS paid_amount
FROM sales_order_agg
WHERE order_date >= '2030-01-01'
  AND order_date <  '2030-02-01';
```

Đừng dùng COALESCE một cách tự động cho mọi chỉ tiêu. Trung bình của tập rỗng thường nên là NULL vì không có mẫu để tính; tổng doanh thu có thể được quy ước hiển thị 0.

## 13. Conditional aggregation với DISTINCT và nhiều điều kiện

Đếm số khách hàng có đơn PAID từ 100 trở lên:

```sql
SELECT
    region_id,
    COUNT(DISTINCT CASE
        WHEN order_status = 'PAID' AND amount >= 100
        THEN customer_id
    END) AS high_value_paid_customers
FROM sales_order_agg
GROUP BY region_id;
```

Đếm khách hàng có cả đơn PAID và PENDING có thể thực hiện bằng hai chỉ tiêu riêng rồi lọc nhóm ở query ngoài hoặc dùng biểu thức nhóm:

```sql
SELECT
    region_id,
    COUNT(DISTINCT CASE WHEN order_status = 'PAID' THEN customer_id END) AS paid_customers,
    COUNT(DISTINCT CASE WHEN order_status = 'PENDING' THEN customer_id END) AS pending_customers
FROM sales_order_agg
GROUP BY region_id;
```

Nếu cần đếm số khách hàng thuộc cả hai tập, có thể đặt kết quả tổng hợp trong CTE:

```sql
WITH customer_status_by_region AS (
    SELECT
        region_id,
        customer_id,
        MAX(order_status = 'PAID') AS has_paid,
        MAX(order_status = 'PENDING') AS has_pending
    FROM sales_order_agg
    GROUP BY region_id, customer_id
)
SELECT
    region_id,
    COUNT(CASE WHEN has_paid = 1 AND has_pending = 1 THEN customer_id END)
        AS customers_with_both_statuses
FROM customer_status_by_region
GROUP BY region_id;
```

Trong MySQL, biểu thức boolean trả về 1 hoặc 0 trong dữ liệu mẫu có status NOT NULL; MAX trên nhóm cho biết có ít nhất một hàng thỏa điều kiện. Nếu cột status nullable, hãy cân nhắc dùng CASE tường minh để điều khiển UNKNOWN.

## 14. Conditional aggregation và HAVING

`HAVING` lọc nhóm sau khi các chỉ tiêu được tính. Ví dụ chỉ lấy khu vực có ít nhất hai đơn PAID:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) AS paid_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue
FROM sales_order_agg
GROUP BY region_id
HAVING COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) >= 2
ORDER BY paid_revenue DESC;
```

Trong MySQL, có thể tham chiếu alias trong HAVING:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) AS paid_orders
FROM sales_order_agg
GROUP BY region_id
HAVING paid_orders >= 2;
```

Để rõ ràng và dễ chuyển sang hệ quản trị khác, bạn cũng có thể dùng derived table hoặc CTE rồi lọc ở query bên ngoài. Không đặt điều kiện tổng hợp vào WHERE cùng cấp vì WHERE được áp dụng trước khi tạo nhóm.

## 15. Lỗi thường gặp khi viết conditional aggregation

- Dùng `COUNT(CASE WHEN condition THEN 1 ELSE 0 END)` và vô tình đếm mọi hàng.
- Dùng `COUNT(condition)` với biểu thức boolean; điều kiện sai trả về 0 nên vẫn được đếm.
- Dùng `SUM(condition)` mà quên điều kiện có thể trả về NULL khi dữ liệu nguồn nullable.
- Dùng `ELSE 0` trong AVG và vô tình đưa các hàng không thỏa vào mẫu số.
- Dùng `ELSE NULL` cho SUM rồi ngạc nhiên khi tổng của nhóm không có giá trị phù hợp là NULL.
- Đặt điều kiện trạng thái trong WHERE khiến các chỉ tiêu trạng thái khác không còn dữ liệu để tính.
- Dùng nhiều CASE có điều kiện chồng lấn nhưng lại giả định các nhóm loại trừ nhau.
- Đặt thứ tự WHEN sai trong CASE phân loại; nhánh rộng đứng trước có thể che nhánh hẹp.
- Dùng COUNT(DISTINCT customer_id) thay vì COUNT(DISTINCT CASE WHEN ... THEN customer_id END), dẫn đến đếm khách ở mọi trạng thái.
- Đưa điều kiện của bảng bên phải vào WHERE sau LEFT JOIN, làm mất các nhóm không có hàng phù hợp.
- Dùng SUM(amount) để báo cáo tiền mà không xác định rõ trạng thái nào được tính là doanh thu.
- Dùng mẫu số không đúng định nghĩa nghiệp vụ khi tính tỷ lệ.
- Dùng IF() trong truy vấn cần tính tương thích đa hệ quản trị mà không cân nhắc CASE.

## 16. Checklist thiết kế báo cáo có điều kiện

- Đã định nghĩa rõ mỗi chỉ tiêu: đếm hàng, đếm thực thể duy nhất, tổng tiền, trung bình hay tỷ lệ.
- Đã xác định tập nguồn chung và các điều kiện riêng cho từng chỉ tiêu.
- Đã đặt điều kiện chung trong WHERE và điều kiện riêng trong CASE.
- Đã chọn COUNT(CASE...), SUM(CASE...) hoặc SUM(condition) đúng với kiểu dữ liệu và NULL semantics.
- Đã dùng ELSE 0 cho tổng đếm/tổng tiền cần trả 0 khi không có hàng phù hợp; dùng NULL khi cần loại hàng khỏi AVG hoặc phép tổng hợp khác.
- Đã kiểm tra cột điều kiện có cho phép NULL và xử lý UNKNOWN có chủ đích.
- Đã kiểm tra điều kiện CASE có chồng lấn hay cần loại trừ nhau.
- Đã dùng COUNT(DISTINCT CASE...) khi đếm thực thể duy nhất theo điều kiện.
- Đã giữ các nhóm không có dữ liệu bằng LEFT JOIN và đặt bộ lọc bảng phải trong ON khi phù hợp.
- Đã xác định đúng mẫu số và quy tắc chia cho 0 cho các chỉ tiêu tỷ lệ.
- Đã kiểm tra kết quả ở nhóm có dữ liệu, nhóm không có hàng phù hợp và nguồn hoàn toàn rỗng.
- Đã dùng HAVING để lọc nhóm thay vì WHERE khi điều kiện phụ thuộc kết quả tổng hợp.

Conditional aggregation cho phép tính nhiều chỉ tiêu trên cùng một tập dữ liệu bằng cách đặt điều kiện bên trong hàm tổng hợp. CASE là cách diễn đạt rõ ràng và linh hoạt; biểu thức boolean trong SUM là cách viết ngắn gọn theo đặc tính MySQL. Chọn đúng COUNT hay SUM, xử lý ELSE và NULL có chủ đích, đồng thời phân biệt điều kiện chung ở WHERE với điều kiện riêng của từng chỉ tiêu sẽ giúp báo cáo chính xác, dễ bảo trì và ít phải gửi nhiều truy vấn riêng lẻ.

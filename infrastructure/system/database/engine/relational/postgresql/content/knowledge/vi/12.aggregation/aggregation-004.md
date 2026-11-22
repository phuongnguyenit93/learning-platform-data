# FILTER trên hàm tổng hợp và thống kê có điều kiện trong PostgreSQL

Một trang quản trị bán hàng thường hiển thị nhiều chỉ số cùng lúc: tổng đơn hàng, số đơn đã thanh toán, số đơn bị hủy, doanh thu của đơn thành công, giá trị trung bình của đơn đã thanh toán và tỷ lệ chuyển đổi theo kênh. Những con số đó lấy từ **cùng một tập dữ liệu**, nhưng mỗi chỉ số lại quan tâm tới **một nhóm hàng khác nhau**.

Với PostgreSQL, không nhất thiết phải viết một truy vấn riêng cho từng chỉ số hoặc lồng hàng loạt subquery. Cú pháp **`FILTER (WHERE ...)` trên hàm tổng hợp** giúp diễn đạt trực tiếp: *chỉ đưa những hàng thỏa điều kiện này vào phép tổng hợp tương ứng*.

Ví dụ:

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM orders;
~~~

Trong một dòng kết quả, `COUNT(*)` đếm toàn bộ hàng, còn mỗi biểu thức `FILTER` chọn tập hàng riêng cho một phép `COUNT` hoặc `SUM`. **Điều kiện của FILTER không loại các hàng khỏi toàn bộ truy vấn** như `WHERE` ở bên ngoài; nó chỉ tác động đến hàm tổng hợp gắn với nó.

Bài học này xây dựng bộ dữ liệu đơn hàng nhỏ, hướng dẫn cú pháp `FILTER` với `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `DISTINCT`, `ARRAY_AGG`, thống kê theo nhóm và theo tháng, tỷ lệ phần trăm, `HAVING`, cửa sổ `OVER`, cách xử lý `NULL`, so sánh với `CASE` và những lưu ý hiệu năng. Các ví dụ sử dụng cú pháp PostgreSQL hiện đại.

## 1. Ôn lại cách hàm tổng hợp hoạt động

Các hàm tổng hợp (*aggregate functions*) nhận nhiều hàng và trả về một kết quả cho một tập hàng hoặc **mỗi nhóm**.

| Hàm | Chức năng cơ bản | Điểm cần nhớ |
| --- | --- | --- |
| `COUNT(*)` | Đếm số hàng | Đếm cả những hàng có cột null |
| `COUNT(expression)` | Đếm giá trị **không NULL** của biểu thức | Khác `COUNT(*)` khi biểu thức có null |
| `SUM(expression)` | Tính tổng các giá trị không null | Trả `NULL` nếu không có giá trị đầu vào |
| `AVG(expression)` | Tính trung bình các giá trị không null | Mẫu số là số giá trị đầu vào không null |
| `MIN(expression)` | Giá trị nhỏ nhất | Bỏ qua null |
| `MAX(expression)` | Giá trị lớn nhất | Bỏ qua null |
| `BOOL_AND` / `BOOL_OR` | Tổng hợp các giá trị boolean | Bỏ qua null theo ngữ nghĩa aggregate |
| `ARRAY_AGG` / `JSONB_AGG` | Gom giá trị vào mảng/JSON | Cần chú ý thứ tự và tập không có hàng |
| `STDDEV_SAMP` | Độ lệch chuẩn mẫu | Cần đủ giá trị đầu vào |

Ví dụ thông thường:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS sum_amount,
    AVG(amount) AS avg_amount
FROM sales_orders;
~~~

Nếu truy vấn không có `GROUP BY`, những hàm trên tính toán trên cùng một tập hàng được cung cấp cho phép tổng hợp. Khi có `GROUP BY channel_code`, các hàm được tính độc lập theo từng nhóm kênh bán hàng.

### Câu hỏi: nếu cần ba nhóm điều kiện khác nhau?

Cách thường thấy là viết ba truy vấn:

~~~sql
SELECT COUNT(*) FROM sales_orders
WHERE status = 'paid';

SELECT COUNT(*) FROM sales_orders
WHERE status = 'pending';

SELECT COUNT(*) FROM sales_orders
WHERE status = 'cancelled';
~~~

Các truy vấn này đều hợp lệ, nhưng nếu muốn tạo **một hàng thống kê** hoặc nhiều chỉ số cạnh nhau theo cùng kênh/tháng, PostgreSQL có cú pháp gọn và rõ ý hơn: `FILTER`.

## 2. Cú pháp FILTER trong PostgreSQL

Dạng tổng quát:

~~~sql
aggregate_function(arguments)
    FILTER (WHERE boolean_expression)
~~~

Một số ví dụ:

~~~sql
COUNT(*) FILTER (WHERE status = 'paid')

SUM(amount) FILTER (WHERE status = 'paid')

AVG(amount) FILTER (WHERE status = 'paid')

COUNT(DISTINCT customer_id)
    FILTER (WHERE status = 'paid')
~~~

Ý nghĩa là:

1. PostgreSQL xét các hàng đầu vào mà truy vấn hiện tại cung cấp cho aggregate.
2. Đối với **riêng hàm tổng hợp này**, chỉ hàng có điều kiện `FILTER` đánh giá thành `TRUE` mới được đưa vào phép tổng hợp.
3. Giá trị `FALSE` hoặc `NULL/UNKNOWN` của điều kiện lọc không được tính cho aggregate đó.
4. Những hàm tổng hợp **khác** trong cùng `SELECT` vẫn áp dụng điều kiện riêng của chúng hoặc dùng toàn bộ tập đầu vào.

### Sơ đồ trực quan

~~~text
                 Các hàng sau FROM / WHERE
                             |
                  +----------+----------+
                  |          |          |
                  v          v          v
               COUNT(*)    status     status
               toàn bộ    = 'paid'   = 'cancelled'
                  |          |          |
                  v          v          v
               16 đơn     COUNT(*)    COUNT(*)
                            FILTER     FILTER
                              |          |
                              v          v
                            8 đơn       3 đơn
                  |          |          |
                  +----------+----------+
                             |
                             v
                      Một dòng thống kê
~~~

Các số trong sơ đồ là kết quả của bộ dữ liệu thực hành ở phần sau.

### FILTER đứng ở đâu trong biểu thức?

`FILTER` xuất hiện **sau lời gọi hàm tổng hợp**:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
~~~

Không viết:

~~~sql
-- Sai cú pháp:
SUM(FILTER (WHERE status = 'paid') amount)
~~~

Với aggregate được sử dụng dưới dạng **window function**, `FILTER` đứng trước `OVER`:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

Không phải hàm nào cũng được gắn `FILTER`: ví dụ `ROW_NUMBER()` là window function chuyên biệt, **không phải aggregate window function**, nên không nhận `FILTER` như `COUNT()` hoặc `SUM()`.

## 3. Chuẩn bị dữ liệu thực hành

Các ví dụ dùng schema `filter_lab` riêng trên một database PostgreSQL mà bạn được phép tạo đối tượng. Không áp dụng các lệnh DDL hoặc xóa dữ liệu này trên database sản xuất.

### 3.1. Tạo schema và danh mục kênh

~~~sql
CREATE SCHEMA filter_lab;

CREATE TABLE filter_lab.channels (
    channel_code text PRIMARY KEY,
    channel_name text NOT NULL
);

INSERT INTO filter_lab.channels (channel_code, channel_name)
VALUES
    ('web', 'Website'),
    ('store', 'Cua hang'),
    ('partner', 'Doi tac'),
    ('affiliate', 'Tiep thi lien ket');
~~~

Kênh `affiliate` cố ý **chưa có đơn hàng** để kiểm tra cách `COUNT`, `SUM` và `LEFT JOIN` xử lý nhóm rỗng.

### 3.2. Tạo bảng đơn hàng

~~~sql
CREATE TABLE filter_lab.sales_orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_code text NOT NULL
        REFERENCES filter_lab.channels(channel_code),
    customer_id bigint NOT NULL,
    order_date date NOT NULL,
    status text NOT NULL
        CHECK (status IN (
            'paid', 'pending', 'cancelled', 'refunded'
        )),
    amount numeric(12, 2) NOT NULL
        CHECK (amount >= 0)
);
~~~

Ý nghĩa dữ liệu trong bài:

- `paid`: đơn đã thanh toán thành công.
- `pending`: đơn đang chờ.
- `cancelled`: đơn đã hủy.
- `refunded`: đơn được đánh dấu hoàn tiền.
- `amount`: **giá trị đơn ghi nhận trong mẫu**, không tự động là doanh thu thuần hoặc dòng tiền.

Đây là bảng mô phỏng phục vụ học `FILTER`. Với hệ thống kế toán thật, tiền thanh toán và tiền hoàn cần được mô hình hóa rõ bằng giao dịch và quy tắc đối soát.

### 3.3. Chèn 16 đơn mẫu

~~~sql
INSERT INTO filter_lab.sales_orders
    (channel_code, customer_id, order_date, status, amount)
VALUES
    ('web',     1, DATE '2026-01-02', 'paid',      120.00),
    ('web',     2, DATE '2026-01-03', 'paid',       80.00),
    ('web',     1, DATE '2026-01-05', 'pending',    50.00),
    ('store',   3, DATE '2026-01-06', 'paid',      200.00),
    ('store',   4, DATE '2026-01-10', 'cancelled',   0.00),
    ('partner', 5, DATE '2026-01-12', 'paid',      150.00),
    ('partner', 2, DATE '2026-01-14', 'refunded',   70.00),
    ('web',     1, DATE '2026-02-02', 'paid',       90.00),
    ('web',     3, DATE '2026-02-03', 'cancelled',   0.00),
    ('store',   4, DATE '2026-02-04', 'paid',      110.00),
    ('store',   5, DATE '2026-02-05', 'pending',    40.00),
    ('partner', 6, DATE '2026-02-06', 'paid',      180.00),
    ('partner', 7, DATE '2026-02-09', 'pending',    60.00),
    ('web',     2, DATE '2026-02-12', 'refunded',   30.00),
    ('store',   1, DATE '2026-02-15', 'paid',      130.00),
    ('partner', 6, DATE '2026-02-16', 'cancelled',   0.00);
~~~

Kiểm tra tổng số hàng và các trạng thái:

~~~sql
SELECT status, COUNT(*) AS n
FROM filter_lab.sales_orders
GROUP BY status
ORDER BY status;
~~~

Kết quả mong đợi:

| status | n |
| --- | ---: |
| `cancelled` | 3 |
| `paid` | 8 |
| `pending` | 3 |
| `refunded` | 2 |

Tổng cộng là **16 đơn**. Tất cả các ví dụ tiếp theo giả định các bảng vừa tạo từ đầu, chưa bị chèn thêm hoặc thay đổi dữ liệu.

## 4. Đếm nhiều trạng thái bằng COUNT(*) FILTER

Một truy vấn tổng hợp nhiều chỉ số:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders,
    COUNT(*) FILTER (
        WHERE status = 'refunded'
    ) AS refunded_orders
FROM filter_lab.sales_orders;
~~~

Kết quả:

| total_orders | paid_orders | pending_orders | cancelled_orders | refunded_orders |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 8 | 3 | 3 | 2 |

Điểm cần quan sát:

- `COUNT(*)` không có `FILTER` đếm cả 16 hàng.
- `COUNT(*) FILTER (WHERE status = 'paid')` chỉ đếm 8 hàng có trạng thái `paid`.
- Những hàng `pending` vẫn hiện diện trong tập dữ liệu cho các phép tổng hợp khác.
- PostgreSQL không tạo bốn bảng tạm vì bạn viết bốn `FILTER`; đó là các phép tổng hợp có điều kiện trong cùng truy vấn.

### Một FILTER có nhiều điều kiện

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'paid' AND amount > 100
    ) AS paid_above_100
FROM filter_lab.sales_orders;
~~~

Trong dữ liệu mẫu, kết quả là **6**: những đơn đã thanh toán có giá trị 120, 200, 150, 110, 180 và 130. Hai đơn đã thanh toán giá trị 80 và 90 không thỏa điều kiện.

Điều kiện trong `FILTER` có thể là biểu thức boolean dùng `AND`, `OR`, `IN`, khoảng ngày, phép so sánh hoặc kết quả của những biểu thức hợp lệ khác. Khi điều kiện phức tạp, nên viết ngoặc rõ ràng và chú ý cách xử lý `NULL`.

## 5. SUM, AVG, MIN và MAX có FILTER

`FILTER` không giới hạn ở `COUNT`. Các hàm tổng hợp khác cũng có thể nhận bộ điều kiện riêng.

~~~sql
SELECT
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount,
    AVG(amount) FILTER (
        WHERE status = 'paid'
    ) AS avg_paid_order,
    MIN(amount) FILTER (
        WHERE status = 'paid'
    ) AS smallest_paid_order,
    MAX(amount) FILTER (
        WHERE status = 'paid'
    ) AS largest_paid_order
FROM filter_lab.sales_orders;
~~~

Với dữ liệu mẫu:

| Chỉ số | Giá trị |
| --- | ---: |
| Tổng giá trị đơn `paid` | 1060.00 |
| Giá trị trung bình đơn `paid` | 132.50 |
| Giá trị đơn `paid` nhỏ nhất | 80.00 |
| Giá trị đơn `paid` lớn nhất | 200.00 |

Tính trung bình: `1060 / 8 = 132.50`. Các đơn `cancelled` có `amount = 0` **không nằm trong mẫu số** vì không thỏa `status = 'paid'`.

### Nhãn “doanh thu” cần được định nghĩa chính xác

Trong bài, `SUM(amount) FILTER (WHERE status = 'paid')` được gọi là **tổng giá trị đơn đang ở trạng thái paid**. Không tự đồng nhất nó với **doanh thu kế toán** hoặc **doanh thu thuần**:

- Một đơn đã paid có thể được hoàn một phần.
- Trạng thái đơn hiện tại có thể thay đổi, làm giá trị tổng tính lại thay đổi.
- Giao dịch hoàn tiền, chiết khấu, thuế, phí và tỷ giá có thể cần mô hình riêng.

`FILTER` giúp viết thống kê đúng theo **điều kiện đã chọn**, nhưng nó không xác định thay người thiết kế nghiệp vụ rằng điều kiện ấy có đúng với định nghĩa doanh thu hay không.

## 6. FILTER so với WHERE ở mức truy vấn

Hai truy vấn sau đều đếm đơn `paid`:

~~~sql
SELECT COUNT(*) AS paid_orders
FROM filter_lab.sales_orders
WHERE status = 'paid';
~~~

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders
FROM filter_lab.sales_orders;
~~~

Ở đây, cả hai đều cho **8**. Nhưng khác biệt xuất hiện khi có **nhiều chỉ số**.

### WHERE loại hàng trước mọi aggregate

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders
FROM filter_lab.sales_orders
WHERE status = 'paid';
~~~

Kết quả:

~~~text
total_orders      = 8
cancelled_orders  = 0
~~~

Vì `WHERE status = 'paid'` đã loại mọi đơn cancelled khỏi **tập hàng đầu vào**, nên `FILTER (WHERE status = 'cancelled')` không thể đếm lại chúng.

### FILTER giữ nhiều tập thống kê trong cùng truy vấn

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders
FROM filter_lab.sales_orders;
~~~

Kết quả là `16, 8, 3`.

| Thành phần | Tác động |
| --- | --- |
| `WHERE` ngoài truy vấn | Chọn tập hàng tham gia **mọi phép tổng hợp** của truy vấn |
| `FILTER (WHERE ...)` | Chọn tập hàng cho **một phép tổng hợp cụ thể** |
| `GROUP BY` | Chia những hàng còn lại thành các nhóm |
| `HAVING` | Chọn nhóm dựa trên biểu thức nhóm/aggregate |
| `ORDER BY` ngoài cùng | Sắp xếp các hàng kết quả |

Không có quy tắc rằng luôn phải thay `WHERE` bằng `FILTER`. Nếu báo cáo chỉ xem đơn tháng 2, `WHERE order_date >= ...` vẫn là cách tốt để giới hạn tập dữ liệu chung, còn các `FILTER` phân biệt trạng thái **bên trong khoảng tháng đã chọn**.

## 7. GROUP BY kết hợp FILTER: thống kê theo kênh

Để xem nhiều chỉ số theo kênh bán hàng:

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

Kết quả mong đợi:

| channel_code | total_orders | paid_orders | pending_orders | cancelled_orders | paid_amount |
| --- | ---: | ---: | ---: | ---: | ---: |
| partner | 5 | 2 | 1 | 1 | 330.00 |
| store | 5 | 3 | 1 | 1 | 440.00 |
| web | 6 | 3 | 1 | 1 | 290.00 |

Nhóm `affiliate` không xuất hiện vì **bảng đơn hàng không có hàng nào** mang `channel_code = 'affiliate'`. `GROUP BY` không tự tạo một nhóm cho những giá trị nằm ở bảng danh mục khác.

### GROUP BY quyết định ranh giới nhóm, FILTER chọn hàng trong nhóm

Mỗi kênh có các hàng của riêng nó:

~~~text
web:       6 hàng ---> paid = 3, paid_amount = 290
store:     5 hàng ---> paid = 3, paid_amount = 440
partner:   5 hàng ---> paid = 2, paid_amount = 330
~~~

`FILTER` không gom các kênh vào một nhóm chung; nó được áp dụng **bên trong từng tập nhóm** mà `GROUP BY` tạo ra.

### Kết hợp điều kiện chung và điều kiện riêng

Ví dụ chỉ phân tích các đơn tháng 2:

~~~sql
SELECT
    channel_code,
    COUNT(*) AS feb_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS feb_paid_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS feb_paid_amount
FROM filter_lab.sales_orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date < DATE '2026-03-01'
GROUP BY channel_code
ORDER BY channel_code;
~~~

`WHERE` chỉ lấy các đơn tháng 2; mỗi `FILTER` sau đó chỉ lấy đơn có trạng thái phù hợp **trong nhóm tháng 2 của kênh ấy**.

## 8. Thống kê theo tháng bằng FILTER

Trường hợp một dashboard cần mỗi dòng là một tháng:

~~~sql
WITH orders_by_month AS (
    SELECT
        date_trunc('month', order_date::timestamp)::date
            AS month_start,
        status,
        amount
    FROM filter_lab.sales_orders
)
SELECT
    month_start,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) AS cancelled_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM orders_by_month
GROUP BY month_start
ORDER BY month_start;
~~~

Kết quả:

| month_start | all_orders | paid_orders | cancelled_orders | paid_amount |
| --- | ---: | ---: | ---: | ---: |
| 2026-01-01 | 7 | 4 | 1 | 550.00 |
| 2026-02-01 | 9 | 4 | 2 | 510.00 |

Ở đây `date_trunc('month', order_date::timestamp)::date` quy các ngày về **ngày đầu tháng**. Với cột `date` của bộ dữ liệu mẫu, việc ép sang `timestamp` là trực tiếp. Nếu sử dụng `timestamptz`, cách xác định tháng còn phụ thuộc **múi giờ kinh doanh**; cần quy định rõ trước khi nhóm dữ liệu theo thời gian.

### Thống kê nhiều tháng trên cùng một dòng

Đôi khi báo cáo cần những cột cố định:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-01-01'
          AND order_date < DATE '2026-02-01'
    ) AS jan_paid_count,
    SUM(amount) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-01-01'
          AND order_date < DATE '2026-02-01'
    ) AS jan_paid_amount,
    COUNT(*) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-02-01'
          AND order_date < DATE '2026-03-01'
    ) AS feb_paid_count,
    SUM(amount) FILTER (
        WHERE status = 'paid'
          AND order_date >= DATE '2026-02-01'
          AND order_date < DATE '2026-03-01'
    ) AS feb_paid_amount
FROM filter_lab.sales_orders;
~~~

Kết quả `jan_paid_count = 4`, `jan_paid_amount = 550.00`, `feb_paid_count = 4`, `feb_paid_amount = 510.00`.

**Hai dạng báo cáo có mục đích khác nhau:** `GROUP BY month_start` mở rộng tự nhiên khi có tháng mới; các cột `jan_*` và `feb_*` phù hợp khi người dùng cần so sánh **một số kỳ cố định**. Đừng cố viết hàng trăm cột `FILTER` nếu một bảng kết quả theo tháng là định dạng phù hợp hơn.

## 9. COUNT(*) và COUNT(expression): xử lý NULL đúng cách

Hai hàm:

~~~sql
COUNT(*)
COUNT(amount)
~~~

không luôn có cùng kết quả. `COUNT(*)` đếm hàng; `COUNT(amount)` chỉ đếm giá trị `amount` khác `NULL`.

Bảng `sales_orders` hiện có `amount NOT NULL`, nên trong dữ liệu mẫu chúng bằng nhau. Để thấy khác biệt, dùng một tập giá trị thử:

~~~sql
WITH measurements(value) AS (
    VALUES
        (10::numeric),
        (NULL::numeric),
        (20::numeric)
)
SELECT
    COUNT(*) AS number_of_rows,
    COUNT(value) AS nonnull_values,
    SUM(value) AS value_sum,
    AVG(value) AS value_average
FROM measurements;
~~~

Kết quả:

| number_of_rows | nonnull_values | value_sum | value_average |
| ---: | ---: | ---: | ---: |
| 3 | 2 | 30 | 15 |

Khi kết hợp với FILTER:

~~~sql
WITH values_to_check(label, value) AS (
    VALUES
        ('accept', 10::numeric),
        ('accept', NULL::numeric),
        ('reject', 20::numeric)
)
SELECT
    COUNT(*) FILTER (
        WHERE label = 'accept'
    ) AS accept_rows,
    COUNT(value) FILTER (
        WHERE label = 'accept'
    ) AS accept_nonnull_values,
    SUM(value) FILTER (
        WHERE label = 'accept'
    ) AS accept_sum
FROM values_to_check;
~~~

Kết quả: `accept_rows = 2`, `accept_nonnull_values = 1` và `accept_sum = 10`.

### FILTER có điều kiện NULL

Điều kiện:

~~~sql
FILTER (WHERE value > 0)
~~~

không nhận hàng có `value = NULL`, vì `NULL > 0` cho kết quả **UNKNOWN**, không phải `TRUE`.

Nếu muốn đếm hàng có giá trị null:

~~~sql
COUNT(*) FILTER (WHERE value IS NULL)
~~~

Nếu muốn đếm những hàng không null:

~~~sql
COUNT(*) FILTER (WHERE value IS NOT NULL)
~~~

Kết quả của `COUNT(value)` và `COUNT(*) FILTER (WHERE value IS NOT NULL)` tương đương về **số lượng** trên cùng tập hàng, nhưng khác cách biểu đạt ý định.

## 10. COUNT khác SUM khi không có hàng thỏa FILTER

Đây là lỗi phổ biến khi lập báo cáo cho kênh, tháng hoặc nhóm có dữ liệu thưa.

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'unknown_status'
    ) AS count_unknown,
    SUM(amount) FILTER (
        WHERE status = 'unknown_status'
    ) AS sum_unknown,
    AVG(amount) FILTER (
        WHERE status = 'unknown_status'
    ) AS avg_unknown
FROM filter_lab.sales_orders;
~~~

Kết quả:

~~~text
count_unknown = 0
sum_unknown   = NULL
avg_unknown   = NULL
~~~

**`COUNT` trả 0** khi không có hàng phù hợp. Nhưng **`SUM` và `AVG` trả `NULL`** khi không có giá trị đầu vào. Đây là ngữ nghĩa của aggregate, không phải lỗi của `FILTER`.

Nếu báo cáo muốn hiển thị tổng bằng 0 khi không có đơn:

~~~sql
SELECT
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'unknown_status'),
        0::numeric
    ) AS sum_unknown
FROM filter_lab.sales_orders;
~~~

Kết quả `0`.

### Không lạm dụng COALESCE cho tất cả chỉ số

Với `SUM`, không có hàng có thể được trình bày là 0 nếu nghiệp vụ xác định “không phát sinh doanh thu”.

Với `AVG`, giá trị 0 thường **khác ý nghĩa** “không có đơn để tính trung bình”. Nếu thay `NULL` bằng 0, người xem có thể hiểu sai rằng giá trị trung bình thật sự của những đơn tồn tại là 0.

| Chỉ số khi tập lọc rỗng | Giá trị PostgreSQL | Cách hiển thị cần cân nhắc |
| --- | --- | --- |
| `COUNT(*)` | 0 | 0 |
| `SUM(amount)` | `NULL` | Có thể `COALESCE(..., 0)` nếu phù hợp |
| `AVG(amount)` | `NULL` | Thường giữ `NULL` hoặc “N/A” |
| `MIN(amount)` / `MAX(amount)` | `NULL` | Thường “N/A” |
| `ARRAY_AGG(...)` | `NULL` | Có thể đổi thành mảng rỗng |

## 11. LEFT JOIN: hiển thị cả kênh chưa có đơn

Ở phần `GROUP BY` trực tiếp trên đơn hàng, kênh `affiliate` biến mất vì không có hàng. Nếu dashboard cần hiển thị **tất cả kênh**, hãy bắt đầu từ bảng danh mục:

~~~sql
SELECT
    c.channel_code,
    c.channel_name,
    COUNT(o.order_id) AS all_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code, c.channel_name
ORDER BY c.channel_code;
~~~

Kết quả:

| channel_code | all_orders | paid_orders | paid_amount |
| --- | ---: | ---: | ---: |
| affiliate | 0 | 0 | 0 |
| partner | 5 | 2 | 330.00 |
| store | 5 | 3 | 440.00 |
| web | 6 | 3 | 290.00 |

### Vì sao dùng COUNT(o.order_id) thay vì COUNT(*)?

Khi `LEFT JOIN` không tìm được đơn cho `affiliate`, PostgreSQL vẫn tạo **một hàng kết quả bên trái** với các cột của `o` là `NULL`.

Nếu viết:

~~~sql
COUNT(*)
~~~

thì nhóm `affiliate` có thể nhận kết quả **1**, vì có một hàng kết quả join dù phần đơn hàng là null.

Trong khi đó:

~~~sql
COUNT(o.order_id)
~~~

chỉ đếm những hàng ghép thực sự có `order_id` khác null, nên trả **0**.

Đây là một bài học quan trọng: `FILTER` không thay thế việc hiểu **cardinality** của `JOIN`. Khi thống kê đối tượng ở bảng con qua `LEFT JOIN`, thường nên đếm một khóa không null của đối tượng ấy.

### Đặt điều kiện ở ON, WHERE hay FILTER?

Các vị trí có ngữ nghĩa khác nhau:

~~~sql
-- A. Giữ tất cả kênh, join chỉ những đơn paid.
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
   AND o.status = 'paid'
~~~

~~~sql
-- B. Có thể loại kênh không có đơn paid khỏi kết quả:
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
WHERE o.status = 'paid'
~~~

~~~sql
-- C. Giữ toàn bộ đơn đã join cho các thống kê khác,
-- chỉ lọc riêng phép đếm đơn paid:
COUNT(o.order_id) FILTER (WHERE o.status = 'paid')
~~~

Trong trường hợp B, điều kiện `WHERE o.status = 'paid'` làm mất các hàng bên trái mà phần `o` là null, nên `LEFT JOIN` có thể hành xử giống inner join đối với điều kiện đó.

Vị trí đúng phụ thuộc vào việc báo cáo có cần **hiển thị nhóm không có dữ liệu** và có cần thống kê **nhiều trạng thái cùng lúc** hay không.

## 12. Thống kê tỷ lệ với COUNT FILTER

Một chỉ số thường gặp là tỷ lệ đơn đã thanh toán trong tổng số đơn.

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.sales_orders;
~~~

Kết quả:

~~~text
total_orders  = 16
paid_orders   = 8
paid_rate_pct = 50.00
~~~

### Hai lưu ý: chia nguyên và chia cho 0

1. Viết `100.0` hoặc ép kiểu sang `numeric` để phép tính có phần thập phân như mong muốn; không dựa vào phép chia hai số nguyên.
2. Dùng `NULLIF(denominator, 0)` để biến mẫu số 0 thành `NULL`, tránh lỗi chia cho 0.

Với kết quả không có hàng, `COUNT(*) = 0` nên tỷ lệ trở thành `NULL`. Điều này thường hợp lý hơn việc tự ép 0% mà không có dữ liệu.

### Tỷ lệ theo kênh

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

Kết quả:

| channel_code | total_orders | paid_orders | paid_rate_pct |
| --- | ---: | ---: | ---: |
| partner | 5 | 2 | 40.00 |
| store | 5 | 3 | 60.00 |
| web | 6 | 3 | 50.00 |

**Đừng tính tỷ lệ tổng bằng trung bình đơn giản của các tỷ lệ nhóm** khi kích thước nhóm khác nhau. Tỷ lệ chung phải dựa trên **tổng tử số và tổng mẫu số** hoặc trung bình có trọng số phù hợp.

### Tỷ lệ khi LEFT JOIN kênh không có đơn

~~~sql
SELECT
    c.channel_code,
    COUNT(o.order_id) AS total_orders,
    ROUND(
        100.0
        * COUNT(o.order_id) FILTER (WHERE o.status = 'paid')
        / NULLIF(COUNT(o.order_id), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code
ORDER BY c.channel_code;
~~~

Kênh `affiliate` có `total_orders = 0` và `paid_rate_pct = NULL` — một cách biểu diễn rằng **chưa có đơn để tính tỷ lệ**, khác với trường hợp có 100 đơn nhưng không đơn nào paid (khi đó tỷ lệ bằng 0%).

## 13. COUNT DISTINCT kết hợp FILTER

Một báo cáo có thể cần biết **bao nhiêu khách hàng khác nhau** đã thanh toán, thay vì số đơn đã thanh toán.

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(DISTINCT customer_id) FILTER (
        WHERE status = 'paid'
    ) AS unique_paying_customers
FROM filter_lab.sales_orders;
~~~

Kết quả:

~~~text
paid_orders             = 8
unique_paying_customers = 6
~~~

Vì khách hàng `customer_id = 1` có nhiều đơn đã thanh toán, **số đơn và số khách khác nhau không bằng nhau**.

### DISTINCT áp dụng sau khi chọn hàng

~~~sql
COUNT(DISTINCT customer_id)
    FILTER (WHERE status = 'paid')
~~~

có thể hiểu:

1. Chỉ xét các hàng có `status = 'paid'`.
2. Lấy `customer_id` từ những hàng đó.
3. Bỏ các giá trị trùng và `NULL` theo ngữ nghĩa `COUNT(DISTINCT ...)`.
4. Đếm số giá trị khác nhau.

Trong dữ liệu bài học `customer_id NOT NULL` nên không có vấn đề null, nhưng trong bảng thật cột có thể nullable.

### DISTINCT trên nhiều giá trị

PostgreSQL có thể đếm các bộ khóa khác nhau bằng biểu thức row phù hợp; tuy nhiên, cần định nghĩa rõ “duy nhất” đang xét **một khách**, **một cặp khách–kênh** hay **một đơn**.

Nếu truy vấn có các `JOIN` làm mỗi đơn xuất hiện nhiều lần, việc đếm `COUNT(DISTINCT order_id) FILTER (...)` có thể tránh đếm trùng đối tượng. Nhưng cách này không tự sửa một phép `SUM(amount)` đang bị nhân đôi do join; phải xem lại quan hệ và mức độ chi tiết của tập dữ liệu đầu vào.

## 14. FILTER so với SUM(CASE WHEN ...)

Trước khi có cú pháp `FILTER`, người viết SQL thường dùng `CASE`:

~~~sql
SELECT
    SUM(
        CASE
            WHEN status = 'paid' THEN 1
            ELSE 0
        END
    ) AS paid_orders
FROM filter_lab.sales_orders;
~~~

Trong bộ dữ liệu không rỗng, kết quả cũng là **8**, giống:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders
FROM filter_lab.sales_orders;
~~~

### Những biểu thức tương tự

| Dạng | Ý nghĩa |
| --- | --- |
| `COUNT(*) FILTER (WHERE p)` | Đếm hàng thỏa `p` |
| `COUNT(CASE WHEN p THEN 1 END)` | Đếm giá trị 1 không null khi `p` đúng |
| `SUM(CASE WHEN p THEN 1 ELSE 0 END)` | Cộng 1 cho hàng đúng, 0 cho hàng sai |
| `SUM(value) FILTER (WHERE p)` | Cộng giá trị không null của hàng đúng |
| `SUM(CASE WHEN p THEN value END)` | Cộng `value` ở hàng đúng, bỏ qua null các hàng khác |

Các cách trên có thể cho cùng kết quả trong nhiều truy vấn, **nhưng không hoàn toàn tương đương ở mọi tình huống rỗng/null**.

### Không có hàng nào phù hợp

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'not_a_real_status')
        AS count_filter,
    COUNT(CASE WHEN status = 'not_a_real_status' THEN 1 END)
        AS count_case,
    SUM(CASE
            WHEN status = 'not_a_real_status' THEN 1
            ELSE 0
        END) AS sum_case_else_zero,
    SUM(CASE
            WHEN status = 'not_a_real_status' THEN 1
        END) AS sum_case_no_else
FROM filter_lab.sales_orders;
~~~

Với 16 hàng đầu vào:

~~~text
count_filter        = 0
count_case          = 0
sum_case_else_zero  = 0
sum_case_no_else    = NULL
~~~

Lý do:

- `COUNT` trả 0 khi không có giá trị/hàng phù hợp.
- `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` có 16 số 0 để cộng nên trả 0.
- `SUM(CASE WHEN ... THEN 1 END)` có toàn `NULL`, nên trả `NULL`.

Nếu **toàn bộ tập đầu vào rỗng**, ngay cả `SUM(CASE ... ELSE 0 END)` cũng trả `NULL`, vì không có hàng nào để cung cấp giá trị 0. Đây là lý do không nên dùng một công thức `CASE` mà chưa xác định cách xử lý tập rỗng.

### Khi nào CASE phù hợp hơn FILTER?

`CASE` linh hoạt khi cần **biến đổi giá trị đầu vào**, không chỉ loại hàng.

Ví dụ một phép tính giả định theo trạng thái:

~~~sql
SELECT
    SUM(
        CASE status
            WHEN 'paid' THEN amount
            WHEN 'refunded' THEN -amount
            ELSE 0
        END
    ) AS illustrative_balance
FROM filter_lab.sales_orders;
~~~

Đây chỉ là **công thức giả định để minh họa CASE**, không phải công thức doanh thu thuần dùng trong kế toán thật. Trong hệ thống sản xuất, cần dữ liệu giao dịch hoàn tiền chính xác trước khi quyết định cộng/trừ.

Nếu chỉ cần “tổng giá trị của đơn paid”, cú pháp sau thường dễ đọc hơn:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
~~~

## 15. AVG FILTER khác AVG(CASE ... ELSE 0)

Đây là nhầm lẫn có thể làm sai báo cáo mà SQL vẫn chạy bình thường.

So sánh:

~~~sql
SELECT
    AVG(amount) FILTER (
        WHERE status = 'paid'
    ) AS avg_paid_only,
    AVG(
        CASE
            WHEN status = 'paid' THEN amount
            ELSE 0
        END
    ) AS avg_over_all_orders,
    AVG(
        CASE
            WHEN status = 'paid' THEN amount
        END
    ) AS avg_case_without_else
FROM filter_lab.sales_orders;
~~~

Kết quả:

| avg_paid_only | avg_over_all_orders | avg_case_without_else |
| ---: | ---: | ---: |
| 132.50 | 66.25 | 132.50 |

Giải thích:

~~~text
8 đơn paid, tổng amount = 1060
16 đơn tất cả

AVG FILTER                   = 1060 / 8  = 132.50
AVG CASE WHEN paid ELSE 0    = 1060 / 16 = 66.25
AVG CASE WHEN paid THEN ...  = 1060 / 8  = 132.50
~~~

**Không phải ELSE 0 là sai trong mọi trường hợp.** Nếu bạn thực sự cần “giá trị paid bình quân trên tất cả đơn” thì mẫu số 16 có thể đúng. Nhưng nó **không phải** giá trị trung bình của riêng các đơn đã thanh toán.

Tên cột thống kê nên phản ánh rõ mẫu số: `avg_paid_order_amount`, `paid_value_per_all_orders` hoặc một tên tương đương.

## 16. FILTER với ARRAY_AGG và JSONB_AGG

Thống kê không phải lúc nào cũng trả một số. Đôi khi cần danh sách ID đơn hoặc một JSON array cho dashboard.

### 16.1. Gom những ID đã thanh toán theo kênh

~~~sql
SELECT
    channel_code,
    ARRAY_AGG(
        order_id ORDER BY order_date, order_id
    ) FILTER (
        WHERE status = 'paid'
    ) AS paid_order_ids
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

`FILTER` chỉ đưa ID đơn paid vào mảng. `ORDER BY` **nằm bên trong lời gọi aggregate** để quy định thứ tự phần tử.

Không nên dựa vào thứ tự quét bảng hoặc `ORDER BY` ngoài cùng để bảo đảm thứ tự các phần tử trong `ARRAY_AGG`. `ORDER BY channel_code` chỉ sắp xếp **các hàng kết quả nhóm**, không sắp phần tử trong mỗi mảng.

### 16.2. Gom dữ liệu thành JSON

~~~sql
SELECT
    channel_code,
    JSONB_AGG(
        JSONB_BUILD_OBJECT(
            'order_id', order_id,
            'amount', amount
        )
        ORDER BY order_date, order_id
    ) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders_json
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

Mỗi nhóm chứa một JSON array gồm các đối tượng đơn paid. Lưu ý mỗi phần tử là dữ liệu theo **cột đã chọn**, không phải nguyên một bản ghi hàng.

### 16.3. Trả mảng rỗng thay vì NULL

Nếu một kênh không có đơn paid:

~~~sql
SELECT
    c.channel_code,
    COALESCE(
        ARRAY_AGG(
            o.order_id ORDER BY o.order_id
        ) FILTER (
            WHERE o.status = 'paid'
        ),
        ARRAY[]::bigint[]
    ) AS paid_order_ids
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code
ORDER BY c.channel_code;
~~~

Với `affiliate`, kết quả là mảng rỗng của kiểu `bigint[]`. Việc khai báo `ARRAY[]::bigint[]` tránh lỗi vì mảng không có phần tử cần một kiểu phần tử rõ ràng.

Tương tự có thể dùng `COALESCE(JSONB_AGG(...) FILTER (...), '[]'::jsonb)` khi API mong đợi JSON array rỗng.

## 17. FILTER và DISTINCT hoặc ORDER BY trong aggregate

`FILTER` kết hợp được với nhiều tùy chọn của aggregate:

~~~sql
COUNT(DISTINCT customer_id)
    FILTER (WHERE status = 'paid')
~~~

~~~sql
ARRAY_AGG(order_id ORDER BY order_date DESC, order_id DESC)
    FILTER (WHERE status = 'paid')
~~~

Trong ví dụ thứ nhất, phép `DISTINCT` hoạt động trên **những giá trị được đưa vào aggregate sau điều kiện lọc**. Trong ví dụ thứ hai, phần tử mảng chỉ có những đơn paid, sau đó được sắp xếp theo khóa đã nêu.

### Ordered-set aggregate và FILTER

Một số phép thống kê như percentile/median dùng cú pháp `WITHIN GROUP`:

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        FILTER (WHERE status = 'paid')
            AS median_paid_amount
FROM filter_lab.sales_orders;
~~~

Với các giá trị paid `80, 90, 110, 120, 130, 150, 180, 200`, median liên tục ở giữa là **125**.

`PERCENTILE_CONT(0.5)` là ví dụ một ordered-set aggregate; `FILTER` đứng **sau toàn bộ biểu thức `WITHIN GROUP (...)`**. Không viết `FILTER` bên trong `ORDER BY` của `WITHIN GROUP`.

Kết quả của phép percentile phụ thuộc hàm và kiểu dữ liệu đầu vào. Ví dụ ép `amount` sang `double precision` để dùng dạng thống kê liên tục cho số.

## 18. FILTER và các hàm tổng hợp boolean

Một số báo cáo cần kiểm tra “tất cả” hoặc “có ít nhất một” hàng thỏa điều kiện.

~~~sql
SELECT
    channel_code,
    BOOL_OR(status = 'cancelled') AS has_cancelled_order,
    BOOL_AND(amount >= 0) AS all_amount_nonnegative,
    BOOL_AND(status = 'paid') FILTER (
        WHERE status <> 'cancelled'
    ) AS all_noncancelled_orders_paid
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

Với `BOOL_AND(status = 'paid') FILTER (WHERE status <> 'cancelled')`, phép aggregate chỉ xét các đơn **không bị hủy**, sau đó kiểm tra liệu **mọi đơn còn lại** có trạng thái paid hay không. Nếu còn pending hoặc refunded, kết quả là false.

### Trường hợp tập lọc rỗng

`BOOL_AND` và `BOOL_OR` là aggregate, nên khi không có giá trị đầu vào thường trả `NULL` thay vì tự khẳng định true/false. Nếu nghiệp vụ muốn định nghĩa “không có đơn nào bị lỗi” là true, cần biểu diễn quy tắc ấy rõ ràng, chẳng hạn so sánh số hàng vi phạm bằng 0:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'cancelled'
    ) = 0 AS has_no_cancelled_orders
FROM filter_lab.sales_orders;
~~~

Biểu thức trên trả một boolean theo **quy tắc được chọn**; nó không có nghĩa `BOOL_AND` và `COUNT` thay thế nhau cho mọi bài toán.

## 19. FILTER trong HAVING: chọn nhóm theo chỉ số có điều kiện

`HAVING` cho phép lọc những nhóm sau khi tổng hợp, và biểu thức aggregate có thể dùng `FILTER`:

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders
FROM filter_lab.sales_orders
GROUP BY channel_code
HAVING COUNT(*) FILTER (
    WHERE status = 'paid'
) >= 3
ORDER BY channel_code;
~~~

Kết quả gồm `store` và `web` vì mỗi kênh có **3 đơn paid**; `partner` có 2 đơn paid nên không đạt điều kiện.

### WHERE và HAVING không tương đương

~~~sql
WHERE status = 'paid'
~~~

lọc **hàng trước GROUP BY**. Khi đó `COUNT(*)` trở thành số đơn paid, không còn là tổng tất cả đơn.

Trong khi đó:

~~~sql
HAVING COUNT(*) FILTER (WHERE status = 'paid') >= 3
~~~

giữ toàn bộ hàng để tính các chỉ số của nhóm, rồi chỉ **chọn những nhóm** có ít nhất 3 đơn paid.

Điều kiện của aggregate không được sử dụng như một hàm tổng hợp trực tiếp trong `WHERE` thông thường:

~~~sql
-- Sai về vị trí aggregate:
SELECT channel_code
FROM filter_lab.sales_orders
WHERE COUNT(*) FILTER (WHERE status = 'paid') >= 3
GROUP BY channel_code;
~~~

Muốn lọc theo số tổng hợp, dùng `HAVING` hoặc một subquery/CTE chứa kết quả đã tổng hợp.

## 20. FILTER với window aggregate và OVER

Một aggregate có thể được sử dụng như **window function** khi thêm `OVER (...)`. Khi đó, nó không nhất thiết gộp mỗi nhóm thành một hàng; kết quả tổng hợp có thể được hiển thị **bên cạnh từng đơn**.

Ví dụ:

~~~sql
SELECT
    order_id,
    channel_code,
    status,
    amount,
    COUNT(*) OVER (
        PARTITION BY channel_code
    ) AS total_orders_in_channel,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY channel_code
    ) AS paid_orders_in_channel
FROM filter_lab.sales_orders
ORDER BY channel_code, order_date, order_id;
~~~

Mỗi hàng `web` sẽ có:

~~~text
total_orders_in_channel = 6
paid_orders_in_channel  = 3
~~~

trong khi mỗi hàng `store` có `5` và `3`; mỗi hàng `partner` có `5` và `2`.

**Phân biệt hai hướng xử lý:**

- `GROUP BY channel_code` trả **một hàng mỗi kênh**.
- `COUNT(...) OVER (PARTITION BY channel_code)` vẫn giữ **mỗi hàng đơn hàng** và gắn thêm thống kê của kênh.

### FILTER nằm trước OVER

Cú pháp đúng:

~~~sql
COUNT(*) FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

Không viết:

~~~sql
-- Sai cú pháp:
COUNT(*) OVER (PARTITION BY channel_code)
    FILTER (WHERE status = 'paid')
~~~

### FILTER không áp dụng cho mọi window function

~~~sql
-- Không hợp lệ vì ROW_NUMBER là window function
-- không phải aggregate window function:
ROW_NUMBER() FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

Nếu cần đánh số thứ tự của **riêng những đơn paid**, có thể lọc các hàng trước trong một CTE rồi dùng `ROW_NUMBER()`:

~~~sql
WITH paid_orders AS (
    SELECT *
    FROM filter_lab.sales_orders
    WHERE status = 'paid'
)
SELECT
    channel_code,
    order_id,
    ROW_NUMBER() OVER (
        PARTITION BY channel_code
        ORDER BY order_date, order_id
    ) AS paid_sequence
FROM paid_orders
ORDER BY channel_code, paid_sequence;
~~~

Đây là một bài toán khác với **đếm tổng đơn paid theo partition**.

## 21. Tổng lũy kế có điều kiện bằng FILTER OVER

Một cửa sổ có `ORDER BY` và frame cho phép tính tổng lũy kế của những đơn paid theo thời gian.

~~~sql
SELECT
    channel_code,
    order_id,
    order_date,
    status,
    amount,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY channel_code
            ORDER BY order_date, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid_amount
FROM filter_lab.sales_orders
ORDER BY channel_code, order_date, order_id;
~~~

Ý nghĩa:

1. Chia các đơn theo `channel_code`.
2. Với mỗi dòng, cửa sổ xét các dòng **từ đầu kênh tới dòng hiện tại** theo `order_date, order_id`.
3. Chỉ những dòng `status = 'paid'` trong cửa sổ đóng góp `amount` vào `SUM`.
4. Khi chưa có đơn paid, `SUM` là null và `COALESCE` hiển thị 0.

Ví dụ đối với kênh `web` theo thời gian:

| Thời điểm | status | amount | running_paid_amount |
| --- | --- | ---: | ---: |
| 2026-01-02 | paid | 120 | 120 |
| 2026-01-03 | paid | 80 | 200 |
| 2026-01-05 | pending | 50 | 200 |
| 2026-02-02 | paid | 90 | 290 |
| 2026-02-03 | cancelled | 0 | 290 |
| 2026-02-12 | refunded | 30 | 290 |

Đơn pending/cancelled/refunded vẫn **xuất hiện trong kết quả**, nhưng không tăng tổng paid.

### Vì sao viết rõ ROWS?

Với window aggregate có `ORDER BY`, PostgreSQL có quy tắc frame mặc định có thể bao gồm các **peer rows** (các hàng bằng nhau theo khóa `ORDER BY`). Trong ví dụ ta viết:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

để diễn đạt rõ ý muốn **lũy kế theo từng dòng**. Việc bổ sung `order_id` làm khóa phá hòa giúp xác định thứ tự khi nhiều đơn có cùng `order_date`.

### WHERE ở ngoài vẫn tác động tới cửa sổ

Nếu cùng truy vấn có:

~~~sql
WHERE status = 'paid'
~~~

thì các hàng pending/refunded/cancelled bị loại khỏi đầu vào của window, không còn xuất hiện trong kết quả lũy kế. Muốn **giữ toàn bộ dòng** nhưng chỉ tính paid, hãy dùng `FILTER` trong window aggregate như ví dụ trên.

## 22. FILTER với GROUPING SETS và báo cáo tổng

Đôi khi muốn trả vừa thống kê theo kênh, vừa một dòng tổng:

~~~sql
SELECT
    CASE
        WHEN GROUPING(channel_code) = 1 THEN 'ALL_CHANNELS'
        ELSE channel_code
    END AS channel_group,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM filter_lab.sales_orders
GROUP BY GROUPING SETS (
    (channel_code),
    ()
)
ORDER BY GROUPING(channel_code), channel_group;
~~~

Kết quả gồm ba nhóm `partner`, `store`, `web` và một hàng `ALL_CHANNELS` có 16 đơn, 8 đơn paid, tổng paid 1060.00.

`GROUPING(channel_code)` giúp phân biệt dòng tổng với giá trị channel thực sự null nếu lược đồ cho phép null. Không chỉ dùng `COALESCE(channel_code, 'ALL')` nếu cần bảo toàn ý nghĩa của một nhóm có giá trị null thật.

`GROUPING SETS`, `ROLLUP` hoặc `CUBE` xác định **những cấp nhóm cần trả**; `FILTER` vẫn xác định những hàng đóng góp vào **một phép tổng hợp** ở từng cấp nhóm.

## 23. Thống kê điều kiện theo nhiều chiều

Một dashboard muốn theo **kênh và tháng**:

~~~sql
WITH orders_by_month AS (
    SELECT
        channel_code,
        date_trunc('month', order_date::timestamp)::date
            AS month_start,
        status,
        amount
    FROM filter_lab.sales_orders
)
SELECT
    channel_code,
    month_start,
    COUNT(*) AS orders_count,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_count,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM orders_by_month
GROUP BY channel_code, month_start
ORDER BY channel_code, month_start;
~~~

Đây là một **báo cáo nhiều chiều** với mỗi hàng tương ứng một cặp `channel_code`–`month_start`.

Nếu dashboard muốn nhìn trạng thái như các hàng thay vì các cột:

~~~sql
SELECT
    channel_code,
    status,
    COUNT(*) AS n
FROM filter_lab.sales_orders
GROUP BY channel_code, status
ORDER BY channel_code, status;
~~~

Cách này có thể phù hợp hơn khi tập trạng thái thay đổi thường xuyên, vì không phải sửa SQL mỗi khi có nhãn trạng thái mới.

### Chọn GROUP BY status hay FILTER theo status?

| Yêu cầu giao diện | Cách thường phù hợp |
| --- | --- |
| Một dòng mỗi kênh với các cột paid/pending/cancelled | `GROUP BY channel_code` kết hợp nhiều `FILTER` |
| Một dòng cho mỗi cặp kênh–trạng thái | `GROUP BY channel_code, status` |
| Trạng thái thay đổi động, không muốn sửa số cột | `GROUP BY status`, pivot phía ứng dụng nếu cần |
| Cần thống kê toàn bộ và nhiều tập con trong cùng hàng | Các aggregate có `FILTER` khác nhau |

`FILTER` rất tiện cho **conditional aggregation**, nhưng không thay thế hoàn toàn việc chọn cấu trúc kết quả.

## 24. Đừng để JOIN nhân đôi số tiền

Một lỗi không liên quan trực tiếp tới cú pháp `FILTER` nhưng rất thường gặp ở báo cáo là **JOIN một-nhiều làm nhân bản hàng trước khi tổng hợp**.

Giả sử:

~~~text
sales_orders
  order_id = 101, amount = 200, status = 'paid'

order_items
  order_id = 101, item A
  order_id = 101, item B
  order_id = 101, item C
~~~

Nếu:

~~~sql
SELECT
    SUM(o.amount) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_amount
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id;
~~~

thì đơn 101 có thể xuất hiện **ba lần** sau join và bị cộng `200 + 200 + 200 = 600`.

`FILTER` chỉ kiểm tra `o.status = 'paid'` trên **từng hàng sau join**; nó không biết ba hàng ấy thực chất là một đơn hàng nghiệp vụ.

### Cách xử lý

Nếu thống kê tiền của **đơn**, hãy tổng hợp ở mức **một hàng mỗi đơn**:

~~~sql
SELECT
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM filter_lab.sales_orders;
~~~

Nếu cần điều kiện liên quan chi tiết đơn, có thể dùng `EXISTS` để chọn đơn thỏa điều kiện mà không nhân bản hàng:

~~~sql
-- Ví dụ giả định có bảng order_items và cột sku.
SELECT
    COUNT(*) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders_with_sku
FROM filter_lab.sales_orders AS o
WHERE EXISTS (
    SELECT 1
    FROM filter_lab.order_items AS i
    WHERE i.order_id = o.order_id
      AND i.sku = 'SKU-001'
);
~~~

Đây là **ví dụ thiết kế**, không chạy nguyên văn trên lab hiện tại vì phần khởi tạo bài học chưa tạo bảng `filter_lab.order_items`. Nó minh họa cách `EXISTS` kiểm tra sự tồn tại của hàng con mà không biến một đơn thành nhiều hàng trong nguồn aggregate.

Với `COUNT(DISTINCT order_id)`, việc đếm trùng đơn có thể được khắc phục trong một số trường hợp, nhưng **`SUM(DISTINCT amount)` không phải giải pháp tổng quát**: hai đơn khác nhau cùng giá trị tiền sẽ bị gộp sai nếu dùng DISTINCT trên amount.

## 25. FILTER có nhanh hơn CASE hay nhiều subquery không?

Không có quy tắc tuyệt đối rằng `FILTER` luôn nhanh hơn `CASE`. Cả hai có thể được PostgreSQL thực thi hiệu quả, nhưng hiệu năng phụ thuộc vào tập dữ liệu, điều kiện, index, số nhóm, số aggregate và plan.

### Khi FILTER có lợi về cách viết

Nếu cần 10 chỉ số từ cùng một tập hàng, một truy vấn:

~~~sql
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled
FROM filter_lab.sales_orders;
~~~

thường **dễ đọc và dễ duy trì hơn** 4 subquery độc lập. Nó cũng cho phép planner tổ chức các aggregate trên cùng một nguồn đầu vào mà không bắt buộc biểu diễn nhiều lần quét cùng bảng.

### Nhưng FILTER không tự biến thành index scan chuyên biệt

Ví dụ:

~~~sql
SELECT
    SUM(amount) FILTER (WHERE status = 'paid')
FROM filter_lab.sales_orders;
~~~

khác:

~~~sql
SELECT SUM(amount)
FROM filter_lab.sales_orders
WHERE status = 'paid';
~~~

Trong truy vấn thứ hai, `WHERE` là điều kiện cấp quan hệ, giúp planner có cơ hội xét những đường truy cập chỉ tới hàng paid. Với truy vấn thứ nhất, vì dữ liệu nguồn có thể được dùng cho nhiều aggregate khác nhau, đừng mặc định điều kiện trong `FILTER` được **đẩy xuống như một WHERE dùng index**.

### Thử EXPLAIN đúng bối cảnh

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM filter_lab.sales_orders;
~~~

So sánh với những dạng `WHERE` hoặc `CASE` có **cùng ý nghĩa đầu ra** trên dữ liệu đại diện. `EXPLAIN ANALYZE` thực thi truy vấn; với ví dụ `SELECT` đọc dữ liệu là phù hợp, nhưng không áp dụng bừa bãi cho DML có tác dụng thay đổi dữ liệu.

Nếu bảng thực tế rất lớn, cần xét:

- Có điều kiện chung theo tenant, ngày hoặc vùng dữ liệu để đặt ở `WHERE` trước không?
- Index hay partition pruning có giúp giảm tập hàng nguồn không?
- Những điều kiện `FILTER` có tốn nhiều CPU khi tính cho từng hàng không?
- Số nhóm `GROUP BY` có lớn tới mức cần nhiều memory/sort/hash không?
- Báo cáo có thực sự cần thời gian thực, hay nên dùng bảng summary/materialized view?

**Đừng tối ưu theo cú pháp mà không đo query plan và độ trễ.**

## 26. Những lỗi thường gặp với FILTER

### Lỗi 1. Dùng FILTER với hàm không phải aggregate

Không hợp lệ:

~~~sql
-- Không hợp lệ:
SELECT
    ROW_NUMBER() FILTER (WHERE status = 'paid')
        OVER (PARTITION BY channel_code)
FROM filter_lab.sales_orders;
~~~

`FILTER` gắn với aggregate (kể cả aggregate dùng ở dạng window). Để đánh số riêng hàng paid, lọc hàng trong CTE rồi dùng `ROW_NUMBER()` như đã trình bày.

### Lỗi 2. Đặt FILTER sai vị trí so với OVER

Đúng:

~~~sql
SUM(amount) FILTER (WHERE status = 'paid')
    OVER (PARTITION BY channel_code)
~~~

Sai:

~~~sql
-- Không hợp lệ:
SUM(amount) OVER (PARTITION BY channel_code)
    FILTER (WHERE status = 'paid')
~~~

### Lỗi 3. Cho rằng FILTER làm mất hàng của SELECT

`COUNT(*) FILTER (WHERE status = 'paid')` không xóa các hàng pending khỏi kết quả `SELECT` có window aggregate; cũng không xóa nhóm có số paid bằng 0. Nếu muốn loại nhóm, dùng `HAVING`; nếu muốn loại hàng trước khi tổng hợp, dùng `WHERE`.

### Lỗi 4. Dùng COUNT(*) trong LEFT JOIN và đếm thừa

Với nhóm không có đơn, `LEFT JOIN` vẫn có thể sinh một hàng với các cột bên phải null. Đếm `COUNT(o.order_id)` thay vì `COUNT(*)` khi cần số đơn thực sự.

### Lỗi 5. Chờ SUM trả 0 khi tập lọc rỗng

`SUM(...) FILTER (...)` trả `NULL` nếu không có giá trị để cộng. Dùng `COALESCE` khi nghiệp vụ muốn 0, nhưng cân nhắc giữ null với average/min/max.

### Lỗi 6. Dùng AVG với ELSE 0 nhưng gọi là trung bình đơn paid

`AVG(CASE WHEN paid THEN amount ELSE 0 END)` chia cho **tất cả đơn**, không phải chỉ đơn paid. Dùng `AVG(amount) FILTER (WHERE status = 'paid')` hoặc `CASE` không có `ELSE 0` khi cần trung bình riêng nhóm paid.

### Lỗi 7. Tỷ lệ chia cho 0

Khi nhóm không có hàng:

~~~sql
COUNT(*) FILTER (WHERE status = 'paid')
    / COUNT(*)
~~~

có thể gặp chia cho 0 hoặc chia nguyên không như dự kiến. Dùng số thập phân và `NULLIF`, đồng thời thống nhất ý nghĩa “không có mẫu”.

### Lỗi 8. FILTER trên dữ liệu đã bị nhân bản do JOIN

Nếu một đơn có ba dòng chi tiết, `SUM(order.amount) FILTER (...)` sau join có thể cộng tiền ba lần. Cần xác định **granularity** trước khi tổng hợp.

### Lỗi 9. Dùng WHERE loại những trạng thái còn cần cho chỉ số khác

Nếu đặt `WHERE status = 'paid'` rồi tính `COUNT(*) FILTER (WHERE status = 'cancelled')`, kết quả cancelled sẽ bằng 0 vì dữ liệu đã bị lọc trước.

### Lỗi 10. Nghĩ FILTER tự biết định nghĩa nghiệp vụ

Lọc đơn có `status = 'paid'` chưa chắc là cách tính doanh thu thuần; số khách paid không tự tương đương số khách lần đầu; tỷ lệ đơn paid chưa chắc là tỷ lệ chuyển đổi của lượt truy cập. Cần định nghĩa chính xác tử số, mẫu số, thời điểm và trạng thái.

## 27. Bài tập thực hành

Các bài tập dùng 16 đơn mẫu trong `filter_lab.sales_orders`, trừ khi đề bài ghi rõ dữ liệu khác. Hãy viết SQL trước, sau đó đối chiếu đáp án.

### Bài 1. Đếm trạng thái

Viết một `SELECT` trả bốn cột: tổng số đơn, số đơn paid, pending và cancelled. Không dùng subquery.

### Bài 2. Tổng và trung bình đơn paid

Tính `SUM(amount)`, `AVG(amount)`, `MIN(amount)`, `MAX(amount)` chỉ cho đơn paid. Cho biết tổng và trung bình dự kiến của bộ dữ liệu mẫu.

### Bài 3. Thống kê theo kênh

Trả mỗi kênh có đơn một dòng, gồm `channel_code`, tổng đơn, số đơn paid, số đơn refunded và tổng amount paid. Dùng `GROUP BY` và nhiều `FILTER`.

### Bài 4. Giữ kênh chưa có đơn

Viết `LEFT JOIN` từ bảng `channels` sang `sales_orders` để kênh `affiliate` vẫn xuất hiện. Làm sao để tổng đơn của `affiliate` bằng 0 thay vì 1?

### Bài 5. So sánh hai công thức AVG

Hai biểu thức:

~~~sql
AVG(amount) FILTER (WHERE status = 'paid')

AVG(CASE WHEN status = 'paid' THEN amount ELSE 0 END)
~~~

khác nhau ở đâu về mẫu số? Dự đoán hai kết quả trên 16 đơn mẫu.

### Bài 6. Tỷ lệ paid theo kênh

Viết SQL tính tỷ lệ phần trăm đơn paid theo kênh, làm tròn hai chữ số. Cần tránh lỗi gì nếu một kênh không có đơn?

### Bài 7. Đếm khách hàng đã thanh toán

Có bao nhiêu **khách hàng khác nhau** có ít nhất một đơn paid? Viết biểu thức `COUNT(DISTINCT ...) FILTER`.

### Bài 8. Truy vấn theo tháng

Trả mỗi tháng một dòng gồm tổng đơn, đơn paid và tổng amount paid. Vì sao nên dùng `GROUP BY` theo tháng khi dữ liệu sẽ phát sinh tháng 3, tháng 4, ...?

### Bài 9. HAVING với FILTER

Chọn những kênh có ít nhất 3 đơn paid. Truy vấn phải giữ `COUNT(*)` là tổng toàn bộ đơn của kênh.

### Bài 10. Phân biệt NULL và 0

Nếu không có đơn nào có `status = 'unknown'`, `COUNT(*) FILTER (...)` và `SUM(amount) FILTER (...)` trả gì? Khi nào nên dùng `COALESCE`?

### Bài 11. Gom ID paid thành mảng

Viết SQL trả về một mảng ID đơn paid cho mỗi kênh, sắp phần tử theo `order_date, order_id`. Vì sao `ORDER BY channel_code` ở cuối truy vấn không đủ?

### Bài 12. Cửa sổ theo kênh

Trả từng đơn cùng tổng số đơn paid của kênh bằng `COUNT(*) FILTER (...) OVER (PARTITION BY ...)`. Cách này khác `GROUP BY` ở số hàng kết quả như thế nào?

### Bài 13. Tổng lũy kế paid

Tính tổng `amount` lũy kế chỉ với đơn paid theo `order_date, order_id` trong từng kênh. Làm sao vẫn hiển thị các đơn pending/cancelled/refunded mà không cộng tiền của chúng?

### Bài 14. CASE và FILTER

Viết biểu thức `COUNT(*) FILTER (WHERE status='paid')` bằng `COUNT(CASE WHEN ... THEN 1 END)`. Khi nào `SUM(CASE WHEN ... THEN 1 END)` có thể trả null?

### Bài 15. JOIN một-nhiều

Một đơn `paid` có `amount=200` và ba dòng `order_items`. Nếu join đơn với chi tiết rồi `SUM(o.amount) FILTER (WHERE o.status='paid')`, vì sao có thể nhận 600 thay vì 200? Đề xuất một cách xử lý đúng.

### Bài 16. FILTER trên ROW_NUMBER

Có thể viết `ROW_NUMBER() FILTER (WHERE status='paid') OVER (...)` không? Nếu muốn đánh thứ tự cho riêng các đơn paid của mỗi kênh, bạn sẽ tổ chức truy vấn như thế nào?

### Bài 17. Đánh giá hiệu năng

Một bảng 100 triệu đơn có index theo `(status, order_date)`. Cần đếm **chỉ đơn paid trong tháng trước**, không có chỉ số nào khác. Nên cân nhắc `WHERE` hay `FILTER` để giới hạn hàng? Cần công cụ gì để xác nhận lựa chọn?

### Bài 18. Median đơn paid

Viết SQL tính median của `amount` cho riêng đơn paid bằng `PERCENTILE_CONT(0.5) WITHIN GROUP ... FILTER`. Giá trị dự kiến là bao nhiêu?

## 28. Đáp án tham khảo

### Đáp án 1. Đếm trạng thái

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_orders,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_orders
FROM filter_lab.sales_orders;
~~~

Kết quả `16, 8, 3, 3`.

### Đáp án 2. Giá trị đơn paid

~~~sql
SELECT
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount,
    AVG(amount) FILTER (WHERE status = 'paid') AS avg_paid,
    MIN(amount) FILTER (WHERE status = 'paid') AS min_paid,
    MAX(amount) FILTER (WHERE status = 'paid') AS max_paid
FROM filter_lab.sales_orders;
~~~

Tổng `1060.00`, trung bình `132.50`, nhỏ nhất `80.00`, lớn nhất `200.00`.

### Đáp án 3. Theo kênh

~~~sql
SELECT
    channel_code,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'refunded') AS refunded_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

### Đáp án 4. Giữ nhóm không có đơn

~~~sql
SELECT
    c.channel_code,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders
FROM filter_lab.channels AS c
LEFT JOIN filter_lab.sales_orders AS o
    ON o.channel_code = c.channel_code
GROUP BY c.channel_code
ORDER BY c.channel_code;
~~~

Kênh `affiliate` nhận `0` vì `COUNT(o.order_id)` bỏ qua giá trị null ở phía bảng con.

### Đáp án 5. Trung bình

`AVG(...) FILTER (...)` chỉ tính trên 8 đơn paid nên là `132.50`. `AVG(CASE ... ELSE 0 END)` tính trên 16 đơn nên là `66.25`.

### Đáp án 6. Tỷ lệ

~~~sql
SELECT
    channel_code,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

`partner = 40.00`, `store = 60.00`, `web = 50.00`. Với `LEFT JOIN` sang bảng kênh, thay mẫu số bằng `COUNT(o.order_id)` và dùng `NULLIF` để xử lý nhóm không có đơn.

### Đáp án 7. Khách hàng khác nhau

~~~sql
SELECT
    COUNT(DISTINCT customer_id) FILTER (
        WHERE status = 'paid'
    ) AS unique_paying_customers
FROM filter_lab.sales_orders;
~~~

Kết quả **6**.

### Đáp án 8. Theo tháng

~~~sql
WITH src AS (
    SELECT
        date_trunc('month', order_date::timestamp)::date AS month_start,
        status,
        amount
    FROM filter_lab.sales_orders
)
SELECT
    month_start,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM src
GROUP BY month_start
ORDER BY month_start;
~~~

`GROUP BY` cho phép tháng mới tự xuất hiện khi có dữ liệu mà không phải thêm một cột `FILTER` mới cho từng tháng.

### Đáp án 9. Chọn nhóm có đủ đơn paid

~~~sql
SELECT
    channel_code,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders
FROM filter_lab.sales_orders
GROUP BY channel_code
HAVING COUNT(*) FILTER (WHERE status = 'paid') >= 3
ORDER BY channel_code;
~~~

Kết quả `store` và `web`.

### Đáp án 10. NULL và 0

`COUNT(*) FILTER (...) = 0`, còn `SUM(amount) FILTER (...) = NULL` khi không có hàng phù hợp. `COALESCE` thích hợp nếu nghiệp vụ muốn diễn đạt tổng không phát sinh là 0; không tự ép trung bình không có dữ liệu thành 0.

### Đáp án 11. ARRAY_AGG có thứ tự

~~~sql
SELECT
    channel_code,
    ARRAY_AGG(order_id ORDER BY order_date, order_id)
        FILTER (WHERE status = 'paid') AS paid_order_ids
FROM filter_lab.sales_orders
GROUP BY channel_code
ORDER BY channel_code;
~~~

`ORDER BY` bên trong `ARRAY_AGG` sắp thứ tự **phần tử mảng**; `ORDER BY` cuối truy vấn chỉ sắp các hàng kênh.

### Đáp án 12. Window aggregate

~~~sql
SELECT
    order_id,
    channel_code,
    status,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) OVER (
        PARTITION BY channel_code
    ) AS channel_paid_orders
FROM filter_lab.sales_orders
ORDER BY channel_code, order_id;
~~~

Trả từng đơn thay vì gộp thành mỗi kênh một hàng.

### Đáp án 13. Tổng paid lũy kế

~~~sql
SELECT
    channel_code,
    order_id,
    order_date,
    status,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY channel_code
            ORDER BY order_date, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid
FROM filter_lab.sales_orders
ORDER BY channel_code, order_date, order_id;
~~~

### Đáp án 14. CASE tương đương trong trường hợp đếm

~~~sql
COUNT(CASE WHEN status = 'paid' THEN 1 END)
~~~

`SUM(CASE WHEN ... THEN 1 END)` trả `NULL` khi mọi đầu vào đều null hoặc tập đầu vào rỗng.

### Đáp án 15. JOIN nhân bản hàng

Một đơn xuất hiện ba lần sau `JOIN` nên `amount` bị cộng ba lần. Tổng hợp ở cấp đơn trước khi join, hoặc dùng `EXISTS` nếu chỉ cần lọc đơn có chi tiết thỏa một điều kiện. Không dùng `SUM(DISTINCT amount)` như cách sửa chung.

### Đáp án 16. ROW_NUMBER

Không. `ROW_NUMBER()` không nhận `FILTER`. Lọc đơn paid bằng CTE/subquery trước, sau đó tính `ROW_NUMBER() OVER (PARTITION BY channel_code ORDER BY order_date, order_id)`.

### Đáp án 17. Tối ưu

Nếu chỉ cần đơn paid tháng trước, điều kiện `WHERE status = 'paid' AND order_date >= ... AND order_date < ...` giúp planner xét giới hạn hàng ở cấp relation, có thể tận dụng index phù hợp. Dùng `EXPLAIN (ANALYZE, BUFFERS)` và số liệu thực để so sánh; không kết luận chỉ từ tên cú pháp.

### Đáp án 18. Median

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        FILTER (WHERE status = 'paid') AS median_paid
FROM filter_lab.sales_orders;
~~~

Kết quả **125**.

## 29. Danh sách lệnh tra cứu nhanh

| Mục tiêu | Biểu thức |
| --- | --- |
| Đếm tất cả hàng | `COUNT(*)` |
| Đếm hàng thỏa điều kiện | `COUNT(*) FILTER (WHERE condition)` |
| Đếm giá trị không null thỏa điều kiện | `COUNT(column) FILTER (WHERE condition)` |
| Tổng giá trị có điều kiện | `SUM(value) FILTER (WHERE condition)` |
| Trung bình có điều kiện | `AVG(value) FILTER (WHERE condition)` |
| Giá trị nhỏ/lớn nhất có điều kiện | `MIN(value) FILTER (...)` / `MAX(value) FILTER (...)` |
| Đếm giá trị khác nhau theo điều kiện | `COUNT(DISTINCT value) FILTER (...)` |
| Mảng có điều kiện và thứ tự | `ARRAY_AGG(value ORDER BY key) FILTER (...)` |
| JSON array có điều kiện | `JSONB_AGG(value ORDER BY key) FILTER (...)` |
| Tỷ lệ có điều kiện | `100.0 * COUNT(*) FILTER (...) / NULLIF(COUNT(*), 0)` |
| Lọc nhóm theo count có điều kiện | `HAVING COUNT(*) FILTER (...) >= n` |
| Aggregate có điều kiện theo cửa sổ | `SUM(value) FILTER (...) OVER (PARTITION BY key)` |
| Tổng lũy kế có điều kiện | `SUM(value) FILTER (...) OVER (ORDER BY key ROWS ...)` |
| Thay SUM NULL bằng 0 | `COALESCE(SUM(value) FILTER (...), 0)` |

## 30. Tổng kết

`FILTER (WHERE ...)` là công cụ trực tiếp và dễ đọc để **thống kê có điều kiện trong PostgreSQL**. Nó cho phép nhiều aggregate cùng nhìn một nguồn dữ liệu nhưng mỗi phép chỉ dùng các hàng thỏa điều kiện của riêng mình, chẳng hạn số đơn paid, số đơn cancelled, tổng giá trị đơn paid và tỷ lệ đơn paid trên tổng đơn.

Những nguyên tắc quan trọng:

1. **`WHERE` và `FILTER` khác phạm vi.** `WHERE` loại hàng khỏi đầu vào chung; `FILTER` chỉ chọn hàng cho một aggregate.
2. **`COUNT` khác `SUM`/`AVG` khi tập lọc rỗng.** `COUNT` trả 0, còn phần lớn aggregate khác trả `NULL`; hãy dùng `COALESCE` có chủ đích.
3. **Mẫu số quyết định ý nghĩa thống kê.** `AVG(amount) FILTER (WHERE paid)` khác `AVG(CASE WHEN paid THEN amount ELSE 0 END)`.
4. **`GROUP BY`, `HAVING` và `OVER` vẫn tuân theo phạm vi riêng.** `FILTER` có thể đi cùng aggregate theo nhóm hoặc aggregate dạng window, nhưng không gắn với mọi window function.
5. **Chất lượng dữ liệu đầu vào vẫn quyết định kết quả.** `FILTER` không tự sửa dữ liệu bị nhân bản do `JOIN`, không định nghĩa hộ doanh thu và không bảo đảm hiệu năng vượt trội so với `CASE` hoặc `WHERE`.

Khi xây báo cáo, hãy xác định **đơn vị cần đếm/tổng hợp**, **điều kiện cho từng chỉ số**, **mẫu số**, **cách hiểu NULL** và **mức nhóm** trước khi viết SQL. Sau đó dùng `FILTER` để biến các định nghĩa ấy thành một truy vấn rõ ràng, dễ kiểm tra và dễ mở rộng khi nhu cầu thống kê tăng lên.

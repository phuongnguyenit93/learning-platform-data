# WINDOW và tái sử dụng định nghĩa cửa sổ trong PostgreSQL

Khi phân tích đơn hàng, ta thường muốn hiển thị **từng đơn** nhưng đồng thời biết: đơn đó là đơn thứ mấy của khách, số tiền của đơn trước, tổng chi tiêu lũy kế, tổng tiền của toàn bộ khách và trung bình ba đơn gần nhất. Các phép tính này có cùng phạm vi **khách hàng**, thường dùng cùng thứ tự **thời gian đặt hàng**, nhưng khác hàm và đôi khi khác **khung cửa sổ** (*window frame*).

Nếu cứ lặp lại `OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id)` ở nhiều cột, câu SQL sẽ dài, khó đọc và dễ có các định nghĩa không nhất quán. PostgreSQL cho phép khai báo **cửa sổ có tên** thông qua mệnh đề **`WINDOW`**, rồi tái sử dụng chúng trong các hàm cửa sổ.

Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    amount,
    ROW_NUMBER() OVER w_chrono AS order_sequence,
    LAG(amount) OVER w_chrono AS previous_amount,
    SUM(amount) OVER w_running AS cumulative_amount
FROM sales_orders
WINDOW
    w_chrono AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    );
~~~

`w_chrono` định nghĩa **phân nhóm và thứ tự**. `w_running` dùng lại định nghĩa đó và bổ sung khung lũy kế. Đây không phải bảng hay view mới: tên cửa sổ chỉ tồn tại trong **phạm vi của câu `SELECT`**.

Bài học giải thích đầy đủ cú pháp `WINDOW`, các dạng `OVER`, cơ chế kế thừa, `PARTITION BY`, `ORDER BY`, `ROWS`/`RANGE`/`GROUPS`, xử lý hàng đồng hạng (*peers*), hàm xếp hạng, `LAG`/`LEAD`, `FIRST_VALUE`/`LAST_VALUE`, aggregate có điều kiện, kết hợp `GROUP BY`, lưu ý SQL sai cú pháp và cách đọc `EXPLAIN`. Phần thực hành sử dụng PostgreSQL hiện đại và một bộ dữ liệu nhất quán.

## 1. Hàm cửa sổ khác GROUP BY thế nào?

Hàm tổng hợp thông thường có thể gộp nhiều hàng thành một hàng kết quả cho mỗi nhóm:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM sales_orders
GROUP BY customer_id;
~~~

Nếu có bốn đơn của khách 1, `GROUP BY customer_id` chỉ trả **một hàng** tổng cho khách 1.

Hàm cửa sổ vẫn tính toán trên các hàng cùng nhóm nhưng **giữ các hàng nguồn**:

~~~sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_total
FROM sales_orders;
~~~

Với mỗi đơn của khách 1, cột `customer_total` hiển thị cùng tổng của khách 1.

~~~text
                Các hàng đơn hàng
                        |
           +------------+-------------+
           |                          |
        GROUP BY                     OVER
           |                          |
     Một hàng mỗi nhóm        Giữ từng hàng đầu vào
           |                          |
  total_amount/customer      total_amount trên từng order
~~~

**`WINDOW` không tạo thêm một kiểu phân tích khác.** Nó chỉ giúp **đặt tên và tái sử dụng thông số cửa sổ** của các hàm dùng `OVER`.

### 1.1. Cấu trúc một hàm cửa sổ

~~~sql
function_name(arguments) OVER (
    PARTITION BY group_columns
    ORDER BY sort_columns
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Ba thành phần có vai trò riêng:

| Thành phần | Câu hỏi được trả lời |
| --- | --- |
| `PARTITION BY` | Hàng nào thuộc **cùng một nhóm phân tích**? |
| `ORDER BY` trong `OVER` | Các hàng trong nhóm được sắp **theo trật tự nào để tính toán**? |
| Frame `ROWS/RANGE/GROUPS` | Tại **hàng hiện tại**, những hàng nào trong partition được đưa vào phép tính phụ thuộc frame? |

Không phải mọi hàm đều phụ thuộc frame như nhau. `ROW_NUMBER`, `RANK`, `LAG` và `LEAD` dùng partition và thứ tự; các aggregate như `SUM`, `AVG` cùng `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` đặc biệt cần hiểu **frame**.

## 2. Vì sao đặt tên cửa sổ?

Giả sử cần:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS sequence_no,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS next_amount
FROM sales_orders;
~~~

Các định nghĩa `PARTITION BY` và `ORDER BY` lặp ba lần. Cách viết này hợp lệ, nhưng khi bổ sung một khóa phá hòa `order_id` hoặc đổi thứ tự ngày, ta phải sửa ở nhiều nơi.

Khai báo `WINDOW`:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER w_customer_time AS sequence_no,
    LAG(amount) OVER w_customer_time AS previous_amount,
    LEAD(amount) OVER w_customer_time AS next_amount
FROM sales_orders
WINDOW w_customer_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
);
~~~

Lợi ích:

1. **Dễ đọc:** người xem nhận biết ba hàm cùng phân tích theo thứ tự thời gian của mỗi khách.
2. **Đỡ lặp:** định nghĩa partition và sort chỉ nằm tại một chỗ.
3. **Giảm sai lệch:** tránh vô ý xếp theo `ordered_at DESC` ở một hàm nhưng `ASC` ở hàm khác.
4. **Hỗ trợ kế thừa:** có thể tạo một cửa sổ cơ sở rồi tạo các cửa sổ có frame khác nhau.
5. **Diễn đạt ý định:** tên `w_customer_time` hoặc `w_running` giúp nhận ra kiểu thống kê.

Tuy nhiên, `WINDOW` **không bảo đảm truy vấn nhanh hơn** việc viết `OVER (...)` đầy đủ. PostgreSQL tối ưu theo các yêu cầu cửa sổ và kế hoạch thực thi; lợi ích đầu tiên của đặt tên là **khả năng bảo trì và tính nhất quán**.

## 3. Cú pháp WINDOW và vị trí trong SELECT

Dạng tổng quát:

~~~sql
SELECT
    expression_1,
    aggregate_or_window_function(...) OVER window_name
FROM some_table
WHERE row_condition
GROUP BY grouping_columns
HAVING group_condition
WINDOW
    window_name AS (
        PARTITION BY ...
        ORDER BY ...
        frame_clause
    )
ORDER BY output_sort
LIMIT output_limit;
~~~

Các mệnh đề `WHERE`, `GROUP BY`, `HAVING` và `LIMIT` không bắt buộc. Về **thứ tự cú pháp**, `WINDOW` xuất hiện **sau `HAVING` (nếu có)** và **trước `ORDER BY` của câu SELECT ngoài cùng**.

Một định nghĩa cụ thể:

~~~sql
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
~~~

Để sử dụng:

~~~sql
ROW_NUMBER() OVER w
~~~

### 3.1. Có thể khai báo nhiều window

~~~sql
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_chrono AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_channel AS (PARTITION BY channel);
~~~

Các định nghĩa ngăn cách bằng dấu phẩy. Mỗi hàm chọn cửa sổ phù hợp qua tên.

### 3.2. Tên có phạm vi câu SELECT

`w_customer` **không được lưu** thành một đối tượng schema hay bảng. Nếu dùng cùng quy tắc trong một `SELECT` khác, phải khai báo lại `WINDOW` trong `SELECT` ấy hoặc đưa logic vào view/query thích hợp.

Ví dụ, tên window trong CTE bên trong **không tự hiện diện** ở câu SELECT ngoài:

~~~sql
WITH src AS (
    SELECT
        order_id,
        ROW_NUMBER() OVER w AS rn
    FROM sales_orders
    WINDOW w AS (ORDER BY order_id)
)
SELECT order_id, rn
FROM src;
~~~

CTE `src` xuất các **cột kết quả** `order_id` và `rn`; nó không xuất một đối tượng cửa sổ `w` để SELECT ngoài tham chiếu.

## 4. Tạo dữ liệu lab dùng xuyên suốt bài

Các lệnh sau dành cho **database PostgreSQL thực hành**. Không chạy `CREATE SCHEMA` và lệnh thay đổi dữ liệu này trên database sản xuất.

### 4.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA window_lab;

CREATE TABLE window_lab.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL
);

CREATE TABLE window_lab.sales_orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES window_lab.customers(customer_id),
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    channel text NOT NULL
);
~~~

### 4.2. Chèn bốn khách hàng

~~~sql
INSERT INTO window_lab.customers (customer_id, customer_name)
VALUES
    (1, 'Lan'),
    (2, 'Minh'),
    (3, 'Chi'),
    (4, 'Dung');
~~~

Khách `Dung` chưa có đơn để thảo luận việc giữ nhóm rỗng khi cần kết hợp `LEFT JOIN`. Các ví dụ trên `sales_orders` sẽ chỉ có các khách 1, 2, 3.

### 4.3. Chèn mười đơn hàng

~~~sql
INSERT INTO window_lab.sales_orders (
    order_id, customer_id, ordered_at,
    status, amount, channel
) VALUES
    (1001, 1, '2026-01-05 09:00:00+07', 'paid',      120.00, 'web'),
    (1002, 1, '2026-01-07 09:00:00+07', 'paid',       80.00, 'web'),
    (1003, 1, '2026-01-07 09:00:00+07', 'pending',    50.00, 'store'),
    (1004, 1, '2026-01-10 15:00:00+07', 'paid',      200.00, 'web'),
    (2001, 2, '2026-01-06 08:00:00+07', 'paid',       60.00, 'store'),
    (2002, 2, '2026-01-08 11:00:00+07', 'cancelled',  40.00, 'store'),
    (2003, 2, '2026-01-12 14:00:00+07', 'paid',      140.00, 'web'),
    (3001, 3, '2026-01-04 10:00:00+07', 'paid',      110.00, 'partner'),
    (3002, 3, '2026-01-09 10:00:00+07', 'pending',    90.00, 'partner'),
    (3003, 3, '2026-01-11 12:00:00+07', 'paid',      160.00, 'web');
~~~

**Hai đơn 1002 và 1003 của Lan có cùng `ordered_at`**. Đây là tình huống có chủ đích để minh họa các *peer rows* và sự khác biệt giữa frame mặc định với `ROWS` có thứ tự phá hòa.

### 4.4. Các số liệu tham khảo

~~~sql
SELECT
    customer_id,
    COUNT(*) AS n_orders,
    SUM(amount) AS all_amount,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM window_lab.sales_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | n_orders | all_amount | paid_amount |
| ---: | ---: | ---: | ---: |
| 1 | 4 | 450.00 | 400.00 |
| 2 | 3 | 240.00 | 200.00 |
| 3 | 3 | 360.00 | 270.00 |

Toàn bộ bảng có **10 đơn**, gồm **7 paid, 2 pending, 1 cancelled**. Tổng giá trị tất cả đơn là **1050.00**, tổng giá trị đơn paid là **870.00**.

Những kết quả cụ thể ở các phần tiếp theo giả định không chèn hoặc sửa thêm dữ liệu này.

## 5. Cửa sổ chỉ có PARTITION BY

Đếm số đơn và tổng số tiền **của mỗi khách** nhưng vẫn giữ từng hàng:

~~~sql
SELECT
    order_id,
    customer_id,
    amount,
    COUNT(*) OVER w_customer AS customer_order_count,
    SUM(amount) OVER w_customer AS customer_amount
FROM window_lab.sales_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
~~~

Mỗi hàng của Lan có `customer_order_count = 4` và `customer_amount = 450.00`. Mỗi hàng của Minh có 3 và 240.00; mỗi hàng của Chi có 3 và 360.00.

Khi không có `ORDER BY` trong định nghĩa cửa sổ, frame mặc định của một aggregate phù hợp là **toàn bộ partition**. Vì vậy `SUM(amount) OVER w_customer` là tổng toàn khách, không phải tổng lũy kế.

### PARTITION BY khác table partitioning

`PARTITION BY customer_id` trong `OVER` **chia hàng đầu vào thành nhóm tính toán logic**. Nó **không tạo partition table**, không chuyển hàng giữa các phân vùng vật lý và không thay thế `CREATE TABLE ... PARTITION BY` dùng cho bảng phân vùng.

Nếu bỏ `PARTITION BY`:

~~~sql
SELECT
    order_id,
    COUNT(*) OVER () AS total_orders
FROM window_lab.sales_orders;
~~~

thì toàn bộ tập hàng của truy vấn tạo thành một partition; mỗi hàng có `total_orders = 10`.

## 6. Cửa sổ có PARTITION BY và ORDER BY

Đặt tên `w_chrono` cho thứ tự thời gian mỗi khách:

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    status,
    ROW_NUMBER() OVER w_chrono AS order_sequence,
    LAG(order_id) OVER w_chrono AS previous_order_id,
    LEAD(order_id) OVER w_chrono AS next_order_id
FROM window_lab.sales_orders
WINDOW w_chrono AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, order_sequence;
~~~

Kết quả đối với Lan:

| order_id | order_sequence | previous_order_id | next_order_id |
| ---: | ---: | ---: | ---: |
| 1001 | 1 | `NULL` | 1002 |
| 1002 | 2 | 1001 | 1003 |
| 1003 | 3 | 1002 | 1004 |
| 1004 | 4 | 1003 | `NULL` |

`order_id` trong `ORDER BY` dùng làm **khóa phá hòa**: đơn 1002 và 1003 cùng thời điểm nhưng vẫn có một thứ tự quyết định.

### ORDER BY trong OVER không sắp xếp kết quả cuối

Hai chỗ `ORDER BY` có công việc khác nhau:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
~~~

quy định thứ tự **để tính window function**.

Còn:

~~~sql
ORDER BY customer_id, order_sequence
~~~

ở cuối truy vấn quy định thứ tự **các hàng được xuất ra**.

Không nên bỏ `ORDER BY` ngoài cùng và mặc định rằng kết quả hiển thị theo thứ tự của `OVER`. Query planner có quyền chọn đường thực thi khác nếu không có yêu cầu sắp xếp kết quả rõ ràng.

## 7. WINDOW đặt tên và tái sử dụng nhiều lần

Cùng một cửa sổ có thể dùng cho các hàm khác nhau:

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    amount,
    ROW_NUMBER() OVER w_time AS rn,
    LAG(amount) OVER w_time AS previous_amount,
    LEAD(amount) OVER w_time AS next_amount,
    FIRST_VALUE(amount) OVER w_time AS first_amount
FROM window_lab.sales_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, rn;
~~~

Đối với mỗi khách:

- `ROW_NUMBER` đánh thứ tự 1, 2, ...
- `LAG` xem tiền của đơn trước.
- `LEAD` xem tiền của đơn sau.
- `FIRST_VALUE` xem tiền của đơn đầu **trong frame có hiệu lực**; với frame mặc định từ đầu partition tới hàng hiện tại, kết quả luôn là giá trị của đơn đầu.

**Không phải mọi hàm có cùng nhu cầu frame**. Khi thêm `SUM` lũy kế, `AVG` ba đơn gần nhất hay `LAST_VALUE` toàn bộ lịch sử, hãy định nghĩa frame rõ thay vì dùng một cửa sổ duy nhất không điều chỉnh.

## 8. Tái sử dụng bằng kế thừa cửa sổ

PostgreSQL cho phép một định nghĩa trong `WINDOW` **tham chiếu một cửa sổ đã khai báo trước** và bổ sung phần chưa có.

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    COUNT(*) OVER w_customer AS n_customer_orders,
    ROW_NUMBER() OVER w_chrono AS order_sequence,
    SUM(amount) OVER w_running AS running_amount,
    SUM(amount) OVER w_full AS customer_total
FROM window_lab.sales_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_chrono AS (
        w_customer
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_full AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, order_sequence;
~~~

Các tên tạo một chuỗi phụ thuộc:

~~~text
w_customer
  PARTITION BY customer_id
        |
        v
w_chrono
  thêm ORDER BY ordered_at, order_id
        |
        +-----------------------+
        |                       |
        v                       v
w_running                    w_full
  frame đầu -> hiện tại         frame đầu -> cuối
        |                       |
        v                       v
  SUM lũy kế                 SUM toàn khách
~~~

Thứ tự khai báo có ý nghĩa: `w_chrono` phải được định nghĩa **sau** `w_customer`, và `w_running`/`w_full` phải nằm sau `w_chrono` nếu muốn sao chép nó.

### 8.1. Kết quả với Lan

| order_id | amount | running_amount | customer_total |
| ---: | ---: | ---: | ---: |
| 1001 | 120.00 | 120.00 | 450.00 |
| 1002 | 80.00 | 200.00 | 450.00 |
| 1003 | 50.00 | 250.00 | 450.00 |
| 1004 | 200.00 | 450.00 | 450.00 |

**`w_running` và `w_full` có cùng partition và sort, nhưng khác frame.** Cùng một hàng đầu ra vì thế có thể hiển thị cả tổng lũy kế lẫn tổng của toàn bộ khách.

### 8.2. Kế thừa không phải sửa định nghĩa gốc

`w_running` không làm `w_chrono` trở thành một cửa sổ lũy kế cho tất cả hàm. Nó tạo **một định nghĩa mới** sao chép những phần hợp lệ rồi bổ sung frame.

`ROW_NUMBER() OVER w_chrono` vẫn tham chiếu `w_chrono` gốc. `SUM(amount) OVER w_full` lại dùng frame toàn partition của cửa sổ mới.

## 9. OVER w và OVER (w) không hoàn toàn giống nhau

Đây là một chi tiết cú pháp PostgreSQL rất đáng nhớ.

~~~sql
ROW_NUMBER() OVER w
~~~

nghĩa là **tham chiếu trực tiếp tới cửa sổ tên `w`**.

~~~sql
ROW_NUMBER() OVER (w)
~~~

mang nghĩa **sao chép định nghĩa của `w` vào một đặc tả cửa sổ mới**, dù không bổ sung thuộc tính. Hai cách thường cho kết quả giống nhau khi `w` chỉ có `PARTITION BY`/`ORDER BY`, nhưng không hoàn toàn tương đương về tính hợp lệ.

### 9.1. Với cửa sổ không có frame

~~~sql
SELECT
    order_id,
    ROW_NUMBER() OVER w_time AS a,
    ROW_NUMBER() OVER (w_time) AS b
FROM window_lab.sales_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
);
~~~

Cả hai cách có thể được dùng vì `w_time` **không khai báo frame tường minh**.

### 9.2. Với cửa sổ đã có frame

~~~sql
SELECT
    order_id,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

Đây là cách **đúng** để dùng cửa sổ tên đã mang frame.

Ngược lại:

~~~sql
-- Cố ý minh họa cú pháp không hợp lệ trong PostgreSQL:
SELECT
    order_id,
    SUM(amount) OVER (w_running) AS running_amount
FROM window_lab.sales_orders
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

PostgreSQL không cho **copy một named window đã có frame clause** theo cách trên. Dùng `OVER w_running` để tham chiếu trực tiếp.

### Quy tắc ghi nhớ

| Cách viết | Diễn giải | Lưu ý |
| --- | --- | --- |
| `OVER w` | Tham chiếu cửa sổ đã đặt tên | Dùng được khi `w` có frame |
| `OVER (w)` | Sao chép định nghĩa `w` | Không được copy cửa sổ có frame |
| `OVER (w ROWS ...)` | Sao chép `w` rồi bổ sung frame | `w` ban đầu không được có frame |
| `OVER (...)` | Định nghĩa trực tiếp | Không cần tên window |

Đối với cửa sổ đã đặt tên, **ưu tiên `OVER w`** nếu muốn dùng nguyên trạng. Chỉ dùng dấu ngoặc khi có mục đích sao chép và mở rộng định nghĩa hợp lệ.

## 10. Bổ sung frame tại từng lời gọi OVER

Không bắt buộc đặt tên cho mọi biến thể frame. Có thể khai báo một cửa sổ cơ sở không chứa frame:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount,
    AVG(amount) OVER (
        w_chrono
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_three_average
FROM window_lab.sales_orders
WINDOW w_chrono AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, ordered_at, order_id;
~~~

Đây là **sao chép rồi bổ sung**. Vì `w_chrono` chưa có frame, hai biểu thức `OVER (w_chrono ROWS ...)` hợp lệ.

### Khi nào tách thêm tên w_running, w_last_three?

Nếu frame được dùng lại ở nhiều cột, nên đặt tên:

~~~sql
SELECT
    order_id,
    SUM(amount) OVER w_running AS running_amount,
    COUNT(*) OVER w_running AS running_count,
    AVG(amount) OVER w_last_three AS moving_avg
FROM window_lab.sales_orders
WINDOW
    w_chrono AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_last_three AS (
        w_chrono
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    );
~~~

Điểm quan trọng là **không sao chép từ một cửa sổ đã mang frame**. Kế thừa nên đi từ một cửa sổ **cơ sở không có frame** tới các cửa sổ chuyên biệt.

## 11. Điều không được làm khi kế thừa

Trong PostgreSQL, việc kế thừa window có các ràng buộc cú pháp:

1. Chỉ tham chiếu cửa sổ đã được khai báo **trước đó** trong danh sách `WINDOW`.
2. Không sao chép một cửa sổ đã có **frame clause**.
3. Không ghi đè `PARTITION BY` hoặc `ORDER BY` đã xác định trong cửa sổ được sao chép bằng một định nghĩa mâu thuẫn.
4. Mỗi định nghĩa phải tuân theo thứ tự hợp lệ: tên cửa sổ được sao chép, sau đó `PARTITION BY`/`ORDER BY`/frame theo giới hạn cú pháp.

### 11.1. Không định nghĩa lặp PARTITION BY

~~~sql
-- Minh họa KHÔNG hợp lệ:
SELECT
    SUM(amount) OVER w_bad
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_bad AS (
        w_customer
        PARTITION BY channel
    );
~~~

Nếu muốn cửa sổ khác phân nhóm theo `channel`, khai báo một cửa sổ độc lập:

~~~sql
SELECT
    order_id,
    SUM(amount) OVER w_customer AS customer_total,
    SUM(amount) OVER w_channel AS channel_total
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_channel AS (PARTITION BY channel);
~~~

### 11.2. Không thêm ORDER BY lần thứ hai khi đã có

~~~sql
-- Minh họa KHÔNG hợp lệ:
SELECT
    ROW_NUMBER() OVER w_bad
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at
    ),
    w_bad AS (
        w_time ORDER BY amount
    );
~~~

Nếu cần thứ tự theo tiền thay vì thời gian, nên khai báo hai cửa sổ xuất phát từ **cùng một partition chưa có ORDER BY**:

~~~sql
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w_time AS order_by_time,
    ROW_NUMBER() OVER w_money AS order_by_amount
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer
        ORDER BY ordered_at, order_id
    ),
    w_money AS (
        w_customer
        ORDER BY amount DESC, order_id
    );
~~~

### 11.3. Không tạo chuỗi kế thừa sai thứ tự

~~~sql
-- Không hợp lệ: w_child tham chiếu w_base chưa khai báo.
WINDOW
    w_child AS (w_base ORDER BY ordered_at),
    w_base AS (PARTITION BY customer_id)
~~~

Đúng:

~~~sql
WINDOW
    w_base AS (PARTITION BY customer_id),
    w_child AS (w_base ORDER BY ordered_at)
~~~

Đây là một **quan hệ tham chiếu trong cùng danh sách WINDOW**, không phải cơ chế import hay override tùy ý như class inheritance của ngôn ngữ hướng đối tượng.

## 12. Frame là gì và vì sao ảnh hưởng kết quả?

Trong một partition, **frame** là một tập con được xác định tương đối với **hàng hiện tại**.

Ví dụ với các đơn của Lan:

~~~text
Hàng 1: 1001, amount 120
Hàng 2: 1002, amount  80
Hàng 3: 1003, amount  50
Hàng 4: 1004, amount 200
~~~

Nếu frame là:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

thì ở hàng 1003, frame gồm **1001 + 1002 + 1003** và tổng là **250.00**.

Nếu frame là:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

thì ở hàng 1004, frame gồm **1002 + 1003 + 1004**, tổng **330.00**; hàng 1001 đã nằm ngoài ba dòng gần nhất.

Nếu frame là:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
~~~

thì cả bốn hàng của Lan đều dùng **toàn partition** và tổng là **450.00**.

### 12.1. Những từ khóa frame phổ biến

| Biểu thức | Ý nghĩa trong `ROWS` |
| --- | --- |
| `UNBOUNDED PRECEDING` | Bắt đầu partition |
| `N PRECEDING` | N hàng trước hàng hiện tại |
| `CURRENT ROW` | Hàng hiện tại |
| `N FOLLOWING` | N hàng sau hàng hiện tại |
| `UNBOUNDED FOLLOWING` | Cuối partition |
| `BETWEEN ... AND ...` | Quy định biên bắt đầu và kết thúc |

Không phải mọi cặp biên đều có thứ tự hợp lệ. Chọn biên theo đúng câu hỏi nghiệp vụ.

### 12.2. Frame không xóa những hàng khỏi SELECT

Frame chỉ quyết định những hàng **đóng góp vào phép tính của hàm** tại vị trí hiện tại. Một `SUM(amount) OVER w_last_three` vẫn trả **một giá trị cho mỗi hàng đơn** của truy vấn, không gộp các hàng hay lọc khỏi kết quả.

## 13. ROWS, RANGE và GROUPS khác nhau

PostgreSQL hỗ trợ ba đơn vị khung:

- **`ROWS`:** đếm theo **vị trí hàng vật lý trong thứ tự cửa sổ**.
- **`RANGE`:** dùng phạm vi giá trị của khóa `ORDER BY`; `CURRENT ROW` có quy tắc bao gồm **nhóm các hàng đồng hạng**.
- **`GROUPS`:** đếm theo **các nhóm peer** có cùng giá trị `ORDER BY`.

Đối với phân tích theo thứ tự giao dịch từng hàng, `ROWS` với khóa phá hòa thường dễ hiểu nhất.

### 13.1. RANGE mặc định khi có ORDER BY

Trong PostgreSQL, nếu có `ORDER BY` nhưng không viết frame, mặc định về mặt ngữ nghĩa thường là:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Trong chế độ `RANGE`, `CURRENT ROW` bao gồm **hàng hiện tại và những hàng cùng giá trị `ORDER BY` (peers)**.

Vì vậy:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at
)
~~~

có thể cho kết quả khác:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

nếu nhiều đơn có cùng `ordered_at`.

### 13.2. Thử peer rows của Lan

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER w_time_only AS default_range_sum,
    SUM(amount) OVER w_rows AS explicit_rows_sum
FROM window_lab.sales_orders
WHERE customer_id = 1
WINDOW
    w_time_only AS (
        ORDER BY ordered_at
    ),
    w_rows AS (
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
ORDER BY ordered_at, order_id;
~~~

Kết quả:

| order_id | amount | default_range_sum | explicit_rows_sum |
| ---: | ---: | ---: | ---: |
| 1001 | 120.00 | 120.00 | 120.00 |
| 1002 | 80.00 | 250.00 | 200.00 |
| 1003 | 50.00 | 250.00 | 250.00 |
| 1004 | 200.00 | 450.00 | 450.00 |

Hai đơn **1002 và 1003 cùng timestamp**, nên nằm trong cùng peer group của `ORDER BY ordered_at` và được tính cùng lúc ở `RANGE ... CURRENT ROW`. Với `ROWS` và thêm `order_id` phá hòa, tổng tăng theo từng dòng.

### 13.3. GROUPS đếm nhóm peer

~~~sql
SELECT
    order_id,
    amount,
    SUM(amount) OVER (
        ORDER BY ordered_at
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS previous_and_current_time_group
FROM window_lab.sales_orders
WHERE customer_id = 1
ORDER BY ordered_at, order_id;
~~~

Nhóm thời điểm:

~~~text
09:00 ngày 05/01: [1001]         sum = 120
09:00 ngày 07/01: [1002, 1003]   sum = 130
15:00 ngày 10/01: [1004]         sum = 200
~~~

Ở nhóm 07/01, frame gồm **nhóm trước (120) và nhóm hiện tại (130)** nên tổng là **250** cho cả 1002 và 1003. Ở nhóm 10/01, frame gồm nhóm 07/01 (130) và nhóm 10/01 (200), tổng **330**.

**Peer group phụ thuộc vào toàn bộ biểu thức `ORDER BY` trong cửa sổ.** Nếu thêm `order_id` là khóa duy nhất, những hàng đồng thời điểm có thể không còn là peers.

### 13.4. RANGE có offset khác ROWS

`RANGE BETWEEN INTERVAL '7 days' PRECEDING AND CURRENT ROW` trên một khóa thời gian phù hợp biểu diễn phạm vi **giá trị thời gian**, không phải “bảy hàng trước”.

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at
        RANGE BETWEEN INTERVAL '7 days' PRECEDING
                  AND CURRENT ROW
    ) AS amount_last_seven_days
FROM window_lab.sales_orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Trong PostgreSQL, `RANGE` có offset yêu cầu cấu trúc `ORDER BY` thích hợp, thường **một khóa sắp xếp** có kiểu tương thích với offset; không thể thay tùy tiện bằng hai khóa như `ordered_at, order_id` cho cùng một frame offset. Nếu cần phá hòa theo hàng, hãy hiểu rõ sự khác nhau giữa “bảy ngày” và “bảy dòng”.

## 14. Tổng lũy kế và trung bình trượt với WINDOW

Khởi tạo ba cửa sổ chuyên biệt:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER w_running AS cumulative_sum,
    COUNT(*) OVER w_running AS cumulative_count,
    ROUND(
        AVG(amount) OVER w_last_three,
        2
    ) AS avg_last_three
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_last_three AS (
        w_time
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Với Lan:

| order_id | amount | cumulative_sum | cumulative_count | avg_last_three |
| ---: | ---: | ---: | ---: | ---: |
| 1001 | 120.00 | 120.00 | 1 | 120.00 |
| 1002 | 80.00 | 200.00 | 2 | 100.00 |
| 1003 | 50.00 | 250.00 | 3 | 83.33 |
| 1004 | 200.00 | 450.00 | 4 | 110.00 |

Giá trị cuối `avg_last_three = (80 + 50 + 200) / 3 = 110.00`. Đây là **trung bình ba đơn gần nhất tính theo hàng**, không phải trung bình ba ngày gần nhất.

### 14.1. Thay khung từ 3 hàng sang 5 hàng

Nếu nghiệp vụ thay đổi thành trung bình năm đơn gần nhất, chỉ cần đổi:

~~~sql
ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
~~~

thay cho:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

trong định nghĩa named window tương ứng. Khi nhiều biểu thức cùng cần frame này, việc đặt tên giúp giảm chỗ cần sửa.

### 14.2. Frame ở đầu partition ngắn hơn N

Ở đơn đầu tiên của một khách, `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` **không yêu cầu đủ ba hàng**: frame chỉ gồm những hàng thực sự tồn tại tới hàng hiện tại. `AVG` của đơn đầu vì vậy là tiền của chính đơn ấy, không phải null vì thiếu hai hàng trước.

## 15. FIRST_VALUE, LAST_VALUE và NTH_VALUE

Những hàm đọc vị trí trong cửa sổ rất nhạy với frame.

### 15.1. FIRST_VALUE và LAST_VALUE trên toàn partition

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    FIRST_VALUE(amount) OVER w_full AS first_order_amount,
    LAST_VALUE(amount) OVER w_full AS last_order_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Với Lan, mọi hàng có `first_order_amount = 120.00` và `last_order_amount = 200.00`. Với Minh là 60.00 và 140.00; với Chi là 110.00 và 160.00.

### 15.2. LAST_VALUE với frame mặc định có thể làm bạn nhầm

~~~sql
SELECT
    order_id,
    amount,
    LAST_VALUE(amount) OVER w_time AS last_value_in_frame
FROM window_lab.sales_orders
WHERE customer_id = 1
WINDOW w_time AS (
    ORDER BY ordered_at, order_id
)
ORDER BY ordered_at, order_id;
~~~

Khi `ORDER BY ordered_at, order_id` tạo thứ tự không đồng hạng, frame mặc định kết thúc tại **hàng hiện tại**. Vì vậy `LAST_VALUE(amount)` thường trả **amount của hàng hiện tại**, không phải amount của đơn cuối toàn bộ lịch sử.

Nếu yêu cầu “đơn cuối cùng của khách”, dùng frame `... AND UNBOUNDED FOLLOWING` hoặc một kỹ thuật phù hợp khác, không chỉ gọi `LAST_VALUE` với named window sắp xếp.

### 15.3. NTH_VALUE

~~~sql
SELECT
    customer_id,
    order_id,
    NTH_VALUE(amount, 2) OVER w_full AS second_order_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, order_id;
~~~

`NTH_VALUE(amount, 2)` lấy **giá trị của hàng thứ hai trong frame** theo thứ tự window. Ở Lan là 80.00, Minh là 40.00, Chi là 90.00.

Nếu frame chưa có đủ hai hàng hoặc một partition không có đủ hai hàng, kết quả có thể null. Không tự suy rằng `NTH_VALUE` luôn lấy hàng thứ N của **toàn partition** nếu frame không bao phủ toàn partition.

## 16. RANK, DENSE_RANK và ROW_NUMBER tái sử dụng WINDOW

Các hàm ranking phụ thuộc partition và `ORDER BY`:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_amount AS row_no,
    RANK() OVER w_amount AS amount_rank,
    DENSE_RANK() OVER w_amount AS amount_dense_rank
FROM window_lab.sales_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount DESC
)
ORDER BY customer_id, amount DESC, order_id;
~~~

Với một khách có hai đơn cùng `amount`, `RANK` và `DENSE_RANK` cho chúng **cùng thứ hạng**, nhưng `ROW_NUMBER` vẫn tạo số thứ tự khác nhau giữa từng hàng.

### Tạo một tập có đồng điểm rõ ràng

~~~sql
WITH scores(player, score) AS (
    VALUES
        ('A', 100),
        ('B', 90),
        ('C', 90),
        ('D', 80)
)
SELECT
    player,
    score,
    ROW_NUMBER() OVER w_points AS row_no,
    RANK() OVER w_points AS rank_no,
    DENSE_RANK() OVER w_points AS dense_rank_no
FROM scores
WINDOW w_points AS (
    ORDER BY score DESC
)
ORDER BY score DESC, player;
~~~

`rank_no` theo các điểm là 1, 2, 2, 4; `dense_rank_no` là 1, 2, 2, 3. Thứ tự `row_no` của hai người đồng điểm 90 có thể **không ổn định** nếu chỉ `ORDER BY score DESC` trong window. Nếu cần đánh số lần lượt xác định, thêm khóa phụ ổn định, nhưng lưu ý việc thêm khóa đó vào **cùng window ranking** cũng có thể làm mất trạng thái đồng hạng của `RANK`.

Một cách tách biệt:

~~~sql
WITH scores(player, score) AS (
    VALUES
        ('A', 100),
        ('B', 90),
        ('C', 90),
        ('D', 80)
)
SELECT
    player,
    score,
    ROW_NUMBER() OVER w_deterministic AS stable_row_no,
    RANK() OVER w_score AS score_rank
FROM scores
WINDOW
    w_score AS (ORDER BY score DESC),
    w_deterministic AS (ORDER BY score DESC, player)
ORDER BY score DESC, player;
~~~

**Không tái sử dụng một cửa sổ chỉ vì các biểu thức trông gần giống nhau**, nếu một hàm cần giữ peers để xếp đồng hạng còn hàm khác cần khóa phá hòa duy nhất.

## 17. PERCENT_RANK, CUME_DIST và NTILE

Những hàm khác cũng có thể dùng named window:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROUND(
        (PERCENT_RANK() OVER w_amount)::numeric,
        3
    ) AS percent_rank,
    ROUND(
        (CUME_DIST() OVER w_amount)::numeric,
        3
    ) AS cumulative_distribution,
    NTILE(3) OVER w_amount AS amount_bucket
FROM window_lab.sales_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount
)
ORDER BY customer_id, amount, order_id;
~~~

- `PERCENT_RANK` phản ánh vị trí xếp hạng tương đối của hàng trong partition, thường ở khoảng 0 tới 1.
- `CUME_DIST` là tỷ lệ hàng có giá trị sắp xếp **nhỏ hơn hoặc bằng** giá trị của hàng hiện tại theo thứ tự window, với quy tắc peers.
- `NTILE(3)` chia các hàng đã sắp thứ tự thành ba nhóm được đánh số 1, 2, 3, cố gắng có số hàng cân bằng.

Các hàm này không tính median theo cùng một phép nội suy. Nếu cần median, `PERCENTILE_CONT` hoặc `PERCENTILE_DISC` có cú pháp ordered-set aggregate riêng, được dùng đúng nơi với `GROUP BY` khi phù hợp.

### Cẩn thận với kiểu hàm và ROUND

Các hàm `PERCENT_RANK` và `CUME_DIST` trả số thực dấu phẩy động trong PostgreSQL. Trong PostgreSQL, overload `ROUND(value, scale)` thông dụng dùng cho `numeric`; vì vậy để làm tròn theo chữ số thập phân, có thể cần ép sang `numeric`:

~~~sql
ROUND((PERCENT_RANK() OVER w_amount)::numeric, 3)
~~~

Điều này khác `ROUND(value)` một đối số, vốn có thể hỗ trợ kiểu đầu vào khác. Khi kết hợp hàm thống kê, nên kiểm tra kiểu bằng `pg_typeof` nếu gặp thông báo không tìm thấy overload phù hợp.

## 18. Aggregate FILTER kết hợp named WINDOW

`FILTER (WHERE ...)` áp dụng cho **hàm tổng hợp**, kể cả khi aggregate đó được dùng ở dạng cửa sổ.

~~~sql
SELECT
    customer_id,
    order_id,
    status,
    amount,
    COUNT(*) OVER w_customer AS all_customer_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) OVER w_customer AS paid_customer_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) OVER w_running AS running_paid_amount
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Đối với Lan:

| order_id | status | all_customer_orders | paid_customer_orders | running_paid_amount |
| ---: | --- | ---: | ---: | ---: |
| 1001 | paid | 4 | 3 | 120.00 |
| 1002 | paid | 4 | 3 | 200.00 |
| 1003 | pending | 4 | 3 | 200.00 |
| 1004 | paid | 4 | 3 | 400.00 |

Hàng pending **vẫn xuất hiện**, nhưng không tăng `running_paid_amount`.

### FILTER không gắn với ROW_NUMBER

~~~sql
-- Minh họa cú pháp KHÔNG hợp lệ:
ROW_NUMBER() FILTER (WHERE status = 'paid') OVER w_time
~~~

`ROW_NUMBER` là một window function chuyên biệt, không phải aggregate chấp nhận `FILTER`. Nếu muốn số thứ tự của **riêng những hàng paid**, hãy lọc trước trong CTE hoặc dùng biểu thức logic phù hợp.

~~~sql
WITH paid AS (
    SELECT *
    FROM window_lab.sales_orders
    WHERE status = 'paid'
)
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w_paid AS paid_sequence
FROM paid
WINDOW w_paid AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, paid_sequence;
~~~

Query trên chỉ trả **những đơn paid**; nó khác với query trước, nơi mọi trạng thái vẫn được hiển thị.

## 19. WINDOW kết hợp nhiều cách chia partition

Một câu báo cáo có thể cần:

- Số đơn trong **cùng khách**.
- Số đơn trong **cùng kênh**.
- Tổng số đơn **toàn hệ thống**.
- Thứ tự trong **lịch sử khách**.

~~~sql
SELECT
    order_id,
    customer_id,
    channel,
    COUNT(*) OVER w_customer AS customer_count,
    COUNT(*) OVER w_channel AS channel_count,
    COUNT(*) OVER w_all AS global_count,
    ROW_NUMBER() OVER w_customer_time AS customer_sequence
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_channel AS (PARTITION BY channel),
    w_all AS (),
    w_customer_time AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY customer_id, customer_sequence;
~~~

`w_all AS ()` diễn đạt cửa sổ không chia partition và không sắp thứ tự. `COUNT(*) OVER w_all` bằng 10 cho từng đơn trong bộ dữ liệu mẫu.

Các window definitions khác nhau có thể cùng tồn tại trong một câu `SELECT`. Không bắt buộc mọi window function dùng cùng `PARTITION BY`.

### Số lượng hàng không tự thay đổi

Nếu chỉ sử dụng window functions trên 10 đơn và không lọc/sinh thêm hàng, đầu ra vẫn có 10 hàng, dù dùng bốn cửa sổ khác nhau. `WINDOW` không tương đương `JOIN` hay `GROUP BY`.

## 20. WINDOW trong truy vấn có WHERE

`WHERE` giới hạn tập hàng **trước khi** window functions được tính trong một mức truy vấn thông thường.

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    ROW_NUMBER() OVER w_time AS sequence_among_paid
FROM window_lab.sales_orders
WHERE status = 'paid'
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, sequence_among_paid;
~~~

Với Lan, chỉ ba đơn paid được đưa vào window nên `sequence_among_paid` là 1, 2, 3 cho 1001, 1002, 1004. Đơn pending 1003 **không nằm trong tập xếp hạng**.

Nếu muốn đánh số toàn bộ lịch sử rồi **chỉ hiển thị đơn paid**, đặt việc lọc sau cửa sổ thông qua CTE:

~~~sql
WITH ranked_all AS (
    SELECT
        order_id,
        customer_id,
        status,
        ROW_NUMBER() OVER w_time AS sequence_in_all_orders
    FROM window_lab.sales_orders
    WINDOW w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    )
)
SELECT *
FROM ranked_all
WHERE status = 'paid'
ORDER BY customer_id, sequence_in_all_orders;
~~~

Ở Lan, đơn 1004 có `sequence_in_all_orders = 4` vì đơn pending 1003 vẫn nằm trong lịch sử được xếp hạng ban đầu. **Thứ tự lọc và tính window thay đổi ý nghĩa báo cáo.**

## 21. Vì sao không đặt window function trực tiếp trong WHERE?

Ví dụ sai:

~~~sql
-- Không hợp lệ:
SELECT
    order_id,
    customer_id
FROM window_lab.sales_orders
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
) = 1;
~~~

PostgreSQL không cho đặt window function trực tiếp trong `WHERE` của cùng query block; tương tự, không đặt trực tiếp trong `GROUP BY` hoặc `HAVING`. Chúng được xử lý theo các giai đoạn logic phù hợp sau khi đã xác định tập hàng/nhóm.

**Giải pháp:** tính trước ở subquery/CTE rồi lọc ở mức ngoài.

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER w_latest AS rn
    FROM window_lab.sales_orders AS o
    WINDOW w_latest AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT
    customer_id,
    order_id,
    amount
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
~~~

Kết quả đơn mới nhất của Lan, Minh, Chi: **1004, 2003, 3003**. Khách Dung chưa có đơn nên không xuất hiện từ bảng `sales_orders`.

### Muốn giữ cả khách chưa có đơn

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER w_latest AS rn
    FROM window_lab.sales_orders AS o
    WINDOW w_latest AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id AS latest_order_id,
    r.amount AS latest_amount
FROM window_lab.customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
~~~

Khách Dung vẫn hiện diện với các cột `r` bằng null. Điều kiện `r.rn = 1` nằm trong `ON` để không biến `LEFT JOIN` thành kết quả loại hàng không có đơn.

## 22. WINDOW và GROUP BY kết hợp

Hàm cửa sổ có thể được dùng trong truy vấn đã tổng hợp. Khi đó, window functions hoạt động trên **những hàng kết quả sau quá trình GROUP BY** tại query block tương ứng, không tự động thấy từng đơn gốc như trước.

Ví dụ:

~~~sql
SELECT
    customer_id,
    channel,
    COUNT(*) AS orders_in_group,
    SUM(amount) AS amount_in_group,
    SUM(SUM(amount)) OVER w_customer AS customer_total
FROM window_lab.sales_orders
GROUP BY customer_id, channel
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, channel;
~~~

Giải thích:

1. `GROUP BY customer_id, channel` tạo từng nhóm khách–kênh.
2. `SUM(amount)` tính tổng amount của nhóm ấy.
3. `SUM(SUM(amount)) OVER w_customer` cộng **các tổng nhóm** của cùng khách để ra tổng toàn khách.

Đây là cách kết hợp **aggregate lồng trong window aggregate** ở ngữ cảnh được hỗ trợ; nó không phải hành vi “window function lồng trong window function”.

### Cẩn thận với COUNT(*) OVER sau GROUP BY

~~~sql
SELECT
    customer_id,
    channel,
    COUNT(*) AS raw_orders_in_group,
    COUNT(*) OVER w_customer AS channel_groups_for_customer
FROM window_lab.sales_orders
GROUP BY customer_id, channel
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, channel;
~~~

Ở truy vấn này, `COUNT(*) OVER w_customer` đếm **số hàng nhóm khách–kênh** sau `GROUP BY`, **không phải số đơn gốc** của khách.

Nếu một khách có hai channel, kết quả là 2 ở mọi hàng nhóm của khách đó. Đây là lý do phải xác định rõ **độ chi tiết đầu vào của window functions** khi kết hợp GROUP BY.

## 23. WINDOW với ORDER BY ở mức SELECT

Window function được phép xuất hiện trong biểu thức sắp xếp ở nơi hợp lệ, nhưng hãy giữ truy vấn dễ hiểu.

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_high_value AS value_rank
FROM window_lab.sales_orders
WINDOW w_high_value AS (
    PARTITION BY customer_id
    ORDER BY amount DESC, order_id
)
ORDER BY customer_id, value_rank;
~~~

`ORDER BY customer_id, value_rank` ngoài cùng sử dụng alias được tính trong `SELECT`. Nếu bỏ sắp xếp ngoài, thứ tự đầu ra không được SQL bảo đảm.

### Alias trong cùng danh sách SELECT

Một alias cột vừa được tạo trong cùng `SELECT` thường **không thể được dùng như một cột nguồn** ngay trong một biểu thức window khác cùng mức:

~~~sql
-- Không nên kỳ vọng alias value_rank dùng được ở biểu thức kế tiếp:
SELECT
    ROW_NUMBER() OVER w AS value_rank,
    value_rank + 1 AS next_rank
FROM window_lab.sales_orders
WINDOW w AS (ORDER BY order_id);
~~~

Muốn xử lý tiếp kết quả window, dùng subquery hoặc CTE:

~~~sql
WITH ranked AS (
    SELECT
        order_id,
        ROW_NUMBER() OVER w AS value_rank
    FROM window_lab.sales_orders
    WINDOW w AS (ORDER BY order_id)
)
SELECT
    order_id,
    value_rank,
    value_rank + 1 AS next_rank
FROM ranked;
~~~

## 24. Không lồng window function trực tiếp vào window function

Ví dụ không hợp lệ:

~~~sql
-- Không hợp lệ:
SELECT
    SUM(ROW_NUMBER() OVER w) OVER w
FROM window_lab.sales_orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY ordered_at
);
~~~

PostgreSQL không cho gọi window function lồng trực tiếp trong đối số của một window function khác cùng query block.

Nếu cần tổng hợp giá trị ranking, tính chúng trước:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ROW_NUMBER() OVER w_time AS rn
    FROM window_lab.sales_orders
    WINDOW w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    )
)
SELECT
    customer_id,
    SUM(rn) AS rank_number_sum
FROM ranked
GROUP BY customer_id
ORDER BY customer_id;
~~~

Ví dụ này minh họa cách tách query block; tổng số thứ tự chỉ có ý nghĩa nếu nghiệp vụ thật sự cần thống kê đó.

## 25. DISTINCT, LIMIT và số hàng của kết quả WINDOW

Những bước xử lý ở ngoài window có thể làm **giảm số hàng kết quả cuối**, nhưng window functions vẫn được tính trong phạm vi tập hàng của query block theo thứ tự logic.

~~~sql
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w AS rn
FROM window_lab.sales_orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
)
ORDER BY customer_id, rn
LIMIT 5;
~~~

`LIMIT 5` lấy **năm hàng của kết quả cuối**, không phải năm hàng cho mỗi khách. Muốn lấy hai đơn mới nhất **mỗi khách**, hãy tính `rn` và lọc `rn <= 2` ở query ngoài:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER w AS rn
    FROM window_lab.sales_orders
    WINDOW w AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT *
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

Kết quả có **6 hàng**: hai đơn gần nhất của mỗi khách có đơn. Không nhầm với `LIMIT 2` toàn bộ query.

## 26. WINDOW không tự tạo nhóm ngày/tháng bị thiếu

Khi phân tích doanh thu theo ngày, việc dùng window không tự tạo các ngày **không có đơn**:

~~~sql
WITH daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS order_day,
        SUM(amount) AS day_amount
    FROM window_lab.sales_orders
    GROUP BY 1
)
SELECT
    order_day,
    day_amount,
    SUM(day_amount) OVER w_running AS cumulative_amount
FROM daily
WINDOW w_running AS (
    ORDER BY order_day
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY order_day;
~~~

Chỉ những ngày có đơn mới xuất hiện ở CTE `daily`.

Nếu cần báo cáo ngày không phát sinh doanh thu vẫn có một hàng 0, tạo **trục ngày** bằng `generate_series` rồi `LEFT JOIN` với kết quả tổng hợp trước khi áp dụng window:

~~~sql
WITH days AS (
    SELECT d::date AS order_day
    FROM generate_series(
        TIMESTAMP '2026-01-04',
        TIMESTAMP '2026-01-12',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS order_day,
        SUM(amount) AS day_amount
    FROM window_lab.sales_orders
    GROUP BY 1
),
calendar AS (
    SELECT
        d.order_day,
        COALESCE(s.day_amount, 0::numeric) AS day_amount
    FROM days AS d
    LEFT JOIN daily AS s USING (order_day)
)
SELECT
    order_day,
    day_amount,
    SUM(day_amount) OVER w_running AS cumulative_amount
FROM calendar
WINDOW w_running AS (
    ORDER BY order_day
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY order_day;
~~~

**`WINDOW` chỉ tính trên những hàng đầu vào thực tế**, không tự tạo hàng ngày, khách hay sản phẩm còn thiếu. Đây là trách nhiệm của phần xây dựng nguồn dữ liệu.

## 27. Tránh nhầm NULL với nhóm rỗng

Khách Dung không có đơn trong `sales_orders`, nên các window functions chạy trực tiếp trên bảng này **không tạo kết quả cho Dung**.

Nếu muốn một hàng mỗi khách với số đơn và tổng tiền:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS n_orders,
    COALESCE(SUM(o.amount), 0::numeric) AS total_amount
FROM window_lab.customers AS c
LEFT JOIN window_lab.sales_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Với Dung, `n_orders = 0` và `total_amount = 0.00`.

Nhưng hãy chú ý: nếu viết `COUNT(*)` trên `LEFT JOIN` khi không có hàng bên phải, nó vẫn có thể đếm **một hàng null-extended**. Để đếm số đơn thực sự, dùng `COUNT(o.order_id)` với khóa không null của đơn.

Nếu đưa `LEFT JOIN` vào một query có window function trên các cột đơn, cần xác định rõ liệu hàng null-extended có được xem là một hàng trong partition hay không. Có thể **tách thống kê đơn vào CTE** rồi join với khách để tránh đánh số một “đơn không tồn tại”.

## 28. WINDOW và hiệu năng: không phải phép tăng tốc tự động

Việc đổi:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

thành:

~~~sql
SUM(amount) OVER w_running
~~~

với named window tương đương **không thay đổi bản chất logic** của phép tính. PostgreSQL có thể nhận ra những cửa sổ giống nhau, chia sẻ một số công việc sắp xếp hoặc tổ chức nhiều node `WindowAgg` khi cần. Nhưng không có cam kết mỗi tên `WINDOW` tạo đúng một lần quét hoặc một lần sort.

### 28.1. Kế hoạch thực thi thường có gì?

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w_time AS rn,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    );
~~~

Trong kế hoạch, có thể thấy:

- `WindowAgg`: node thực hiện phép tính window.
- `Sort`: sắp xếp nếu đầu vào chưa đáp ứng thứ tự cần thiết.
- `Incremental Sort` trong những tình huống phù hợp khi một phần thứ tự đã có.
- `Index Scan` hoặc `Index Only Scan` nếu truy vấn và trạng thái visibility cho phép.
- `actual rows`, `actual time`, `loops` và `BUFFERS` cho biết số liệu của lần thực thi.

Đừng kết luận rằng một `WindowAgg` nhất định làm toàn bộ SQL chậm. Phải xem chi phí sắp xếp, số hàng, nhóm, kích thước frame, các bước join và lượng dữ liệu phải đọc.

### 28.2. Index phục vụ PARTITION BY và ORDER BY

Với nhiều query chạy theo:

~~~sql
PARTITION BY customer_id
ORDER BY ordered_at, order_id
~~~

ta có thể cân nhắc B-tree index:

~~~sql
CREATE INDEX idx_orders_customer_time
ON window_lab.sales_orders (
    customer_id,
    ordered_at,
    order_id
);
~~~

Nếu planner có thể lấy dữ liệu theo thứ tự này, nó có cơ hội giảm hoặc tránh một số bước sắp xếp. Nhưng bảng lab chỉ có 10 đơn, nên `Seq Scan` và `Sort` vẫn có thể rẻ hơn index scan.

Index còn có **chi phí lưu trữ và duy trì khi ghi**. Chỉ tạo index theo workload thường gặp và xem `EXPLAIN` với dữ liệu đủ đại diện.

### 28.3. Nhiều thứ tự khác nhau có thể cần nhiều sort

~~~sql
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_amount AS (
        PARTITION BY customer_id
        ORDER BY amount DESC, order_id
    )
~~~

hai cửa sổ này có **thứ tự khác nhau**. Tên riêng không giúp dùng chung một thứ tự vật lý cho cả hai trong mọi trường hợp. Nếu query có nhiều định nghĩa sort, chi phí tính toán có thể cao hơn.

### 28.4. Nên lọc dữ liệu sớm khi đúng nghiệp vụ

Nếu chỉ phân tích các đơn của một khách hoặc một khoảng thời gian, điều kiện `WHERE` có thể giảm số hàng cần xử lý. Tuy nhiên, `WHERE` cũng thay đổi **phạm vi lịch sử** được window tính toán. Khi phải lọc sau khi tính xếp hạng toàn lịch sử, hãy dùng subquery đúng thứ tự logic thay vì áp dụng sớm rồi vô tình đổi kết quả.

## 29. Các lỗi thường gặp với WINDOW

### Lỗi 1: Đặt WINDOW sai vị trí

Sai ý tưởng:

~~~sql
-- Không đúng thứ tự cú pháp:
SELECT ROW_NUMBER() OVER w
FROM window_lab.sales_orders
ORDER BY order_id
WINDOW w AS (ORDER BY order_id);
~~~

`WINDOW` phải đứng trước `ORDER BY` ngoài cùng:

~~~sql
SELECT ROW_NUMBER() OVER w AS rn
FROM window_lab.sales_orders
WINDOW w AS (ORDER BY order_id)
ORDER BY rn;
~~~

### Lỗi 2: Dùng tên window chưa khai báo

~~~sql
-- Không có WINDOW w_time AS (...):
SELECT ROW_NUMBER() OVER w_time
FROM window_lab.sales_orders;
~~~

Tên window không phải biến toàn cục. Phải khai báo trong phạm vi `SELECT` tương ứng.

### Lỗi 3: Kế thừa window theo thứ tự ngược

Nếu `w_child` tham chiếu `w_base`, `w_base` phải xuất hiện trước trong `WINDOW`.

### Lỗi 4: Sao chép window có frame

Nếu `w_running` đã mang frame, dùng `OVER w_running`, không dùng `OVER (w_running)`. Cách thứ hai đòi copy một window có frame và bị PostgreSQL từ chối.

### Lỗi 5: Ghi đè PARTITION BY/ORDER BY đã có

Không thêm `PARTITION BY channel` khi sao chép một cửa sổ đã phân nhóm theo khách; không thêm một `ORDER BY` khác khi cửa sổ cơ sở đã chứa `ORDER BY`. Tách cửa sổ cơ sở phù hợp.

### Lỗi 6: Nghĩ ORDER BY trong OVER sắp kết quả cuối

Phải có `ORDER BY` ngoài cùng nếu cần thứ tự output ổn định.

### Lỗi 7: Nhầm RANGE mặc định với ROWS

Khi nhiều hàng có cùng `ORDER BY`, frame `RANGE ... CURRENT ROW` có thể đưa **cả nhóm peers** vào kết quả tại từng hàng. Nếu cần tăng theo từng giao dịch, dùng `ROWS` và khóa phá hòa thích hợp.

### Lỗi 8: LAST_VALUE chỉ lấy giá trị hiện tại

Với frame mặc định kết thúc ở hàng hiện tại, `LAST_VALUE` không nhất thiết là hàng cuối toàn partition. Dùng frame `... UNBOUNDED FOLLOWING` khi đó mới là điều cần.

### Lỗi 9: Lọc sai thời điểm

Nếu `WHERE status='paid'` ở cùng query block, các đơn không paid không tham gia xếp hạng. Nếu cần xếp toàn lịch sử rồi chỉ hiển thị paid, phải tính window trước trong CTE.

### Lỗi 10: Dùng ROW_NUMBER trong WHERE

Window functions không dùng trực tiếp trong `WHERE` cùng query block. Tạo CTE rồi lọc theo alias ranking.

### Lỗi 11: Lồng hai window function

PostgreSQL không cho window function làm đối số trực tiếp của một window function khác. Dùng các query block nối tiếp.

### Lỗi 12: Suy `COUNT(*) OVER` sau GROUP BY là số đơn gốc

Khi `GROUP BY` đã tạo hàng nhóm, window xử lý **hàng nhóm**. Muốn số đơn gốc, cần xây aggregate đúng độ chi tiết.

### Lỗi 13: Không phân biệt ranking có ties

Nếu thêm khóa duy nhất vào cùng named window dùng bởi `RANK`, các hàng đồng điểm có thể không còn đồng hạng. Tách window ranking theo score và window row numbering có khóa phá hòa.

### Lỗi 14: Coi WINDOW là index hoặc cache vật lý

Named window không lưu dữ liệu và không bảo đảm planner chỉ sort một lần. Dùng `EXPLAIN (ANALYZE, BUFFERS)`, không suy hiệu năng từ độ ngắn câu SQL.

## 30. Bài tập thực hành

Các bài tập sau dùng schema `window_lab` và 10 đơn đã tạo. Hãy viết SQL, dự đoán kết quả, rồi đối chiếu lời giải. Các câu truy vấn đọc không làm thay đổi dữ liệu lab.

### Bài 1. Định nghĩa named window

Viết một query trả `order_id`, `customer_id` và `ROW_NUMBER` theo thời gian tăng dần mỗi khách bằng một cửa sổ tên `w_time`. Dùng `order_id` phá hòa.

### Bài 2. Tái sử dụng cùng window

Trong cùng `SELECT`, dùng `w_time` cho `ROW_NUMBER`, `LAG(amount)` và `LEAD(amount)`. Vì sao đặt tên giúp tránh sai khác thứ tự giữa ba hàm?

### Bài 3. Cửa sổ chỉ có PARTITION BY

Trả từng đơn kèm số đơn và tổng amount **của toàn bộ khách**. Cửa sổ `w_customer` không cần `ORDER BY`.

### Bài 4. Kế thừa cửa sổ

Khai báo `w_customer` chỉ có `PARTITION BY customer_id`, rồi `w_time` kế thừa và thêm `ORDER BY ordered_at, order_id`.

### Bài 5. Tổng lũy kế

Khai báo `w_running` kế thừa `w_time` và dùng `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Với Lan, tổng ở đơn 1003 là bao nhiêu?

### Bài 6. Tổng toàn partition

Từ `w_time`, tạo `w_full` để `SUM(amount)` trả tổng toàn khách cho từng đơn. Với Lan, mọi dòng phải có giá trị gì?

### Bài 7. Ba đơn gần nhất

Tạo named window `w_three` và tính `AVG(amount)` của tối đa ba đơn gồm dòng hiện tại và hai dòng trước. Giá trị ở đơn 1004 của Lan là bao nhiêu?

### Bài 8. OVER w hay OVER (w)?

Giả sử `w_running` đã chứa frame `ROWS ...`. Cách nào hợp lệ: `SUM(amount) OVER w_running` hay `SUM(amount) OVER (w_running)`? Vì sao?

### Bài 9. Lấy LAST_VALUE đúng nghĩa

Viết query dùng `LAST_VALUE(amount)` để mọi dòng của Lan thấy giá trị tiền của đơn cuối lịch sử, không phải đơn hiện tại.

### Bài 10. RANGE và peers

Vì sao `SUM(amount) OVER (ORDER BY ordered_at)` trong nhóm Lan có thể trả `250` cho **cả 1002 và 1003**? Viết cách để tổng tăng riêng từng dòng.

### Bài 11. GROUPS frame

Trên các đơn Lan, dùng `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` theo `ordered_at`. Tổng tại nhóm 10/01 là bao nhiêu?

### Bài 12. Lọc trước hay sau window

Hai cách: (a) `WHERE status='paid'` trong query tính `ROW_NUMBER`; (b) tính `ROW_NUMBER` trên mọi đơn rồi lọc paid ở query ngoài. Đơn 1004 của Lan nhận số thứ tự nào trong mỗi cách?

### Bài 13. Lấy đơn mới nhất mỗi khách

Dùng `ROW_NUMBER() OVER w_latest`, CTE và `WHERE rn=1` ở ngoài. Các order ID nào được chọn? Làm sao giữ Dung?

### Bài 14. FILTER trên window aggregate

Tính `running_paid_amount` theo thời gian cho mỗi khách nhưng vẫn giữ các đơn không paid trong kết quả. Với Lan, tổng paid sau đơn 1004 là bao nhiêu?

### Bài 15. Ranking với đồng điểm

Điểm `100,90,90,80`: giải thích `RANK`/`DENSE_RANK`. Nếu muốn `ROW_NUMBER` ổn định trong khi vẫn giữ đồng hạng của `RANK`, nên dùng mấy named windows và vì sao?

### Bài 16. GROUP BY + WINDOW

Viết query tổng amount theo từng `customer_id, channel`, sau đó dùng `SUM(SUM(amount)) OVER w_customer` tính tổng toàn khách. `COUNT(*) OVER w_customer` lúc này đếm gì?

### Bài 17. Thứ tự đầu ra

`ORDER BY ordered_at, order_id` ở trong `OVER` có đảm bảo hàng đầu ra được xếp theo hai cột ấy không? Nếu không, cần gì?

### Bài 18. Cú pháp WINDOW

Sửa các lỗi: (a) đặt `WINDOW` sau `ORDER BY` ngoài cùng; (b) `w_child` khai báo trước `w_base`; (c) thêm `ORDER BY amount` khi copy một window đã có `ORDER BY ordered_at`.

### Bài 19. Tối ưu hiệu năng

Một bảng có hàng triệu đơn, báo cáo dùng các cửa sổ phân nhóm theo khách và sắp theo `ordered_at, order_id`. Đề xuất index đáng thử và cách đo xem planner có sử dụng hay không.

### Bài 20. Tổng hợp theo ngày có ngày rỗng

Nếu một ngày không có đơn, `WINDOW` có tự sinh ngày ấy không? Nêu cách tạo báo cáo đủ mọi ngày trong một khoảng, có tổng lũy kế.

### Bài 21. Kiểu thống kê percent rank

Vì sao `ROUND(PERCENT_RANK() OVER w, 3)` có thể báo lỗi overload trong PostgreSQL? Viết cách ép kiểu đúng trước khi làm tròn.

### Bài 22. So sánh WINDOW với CTE/view

Nêu ranh giới sử dụng của named window: nó có lưu dữ liệu giữa các query không, có thay thế CTE/view không, và có bảo đảm tăng tốc không?

## 31. Lời giải tham khảo

### Bài 1 và 2. Named WINDOW chung

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_time AS seq_no,
    LAG(amount) OVER w_time AS prev_amount,
    LEAD(amount) OVER w_time AS next_amount
FROM window_lab.sales_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, seq_no;
~~~

Chỉ cần chỉnh thứ tự tại một định nghĩa `w_time` nếu cả ba hàm phải đổi theo cùng quy tắc.

### Bài 3. Cửa sổ toàn khách

~~~sql
SELECT
    order_id,
    customer_id,
    COUNT(*) OVER w_customer AS n_orders,
    SUM(amount) OVER w_customer AS total_amount
FROM window_lab.sales_orders
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, order_id;
~~~

Lan có 4 đơn và tổng 450.00.

### Bài 4. Kế thừa

~~~sql
SELECT
    order_id,
    ROW_NUMBER() OVER w_time AS seq_no
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    );
~~~

### Bài 5. Running SUM

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Lan, đơn 1003: `120 + 80 + 50 = 250.00`.

### Bài 6. Full partition

~~~sql
SELECT
    customer_id,
    order_id,
    SUM(amount) OVER w_full AS total_customer_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND UNBOUNDED FOLLOWING
    );
~~~

Lan: `450.00` ở cả bốn hàng.

### Bài 7. Average last three

~~~sql
SELECT
    customer_id,
    order_id,
    ROUND(AVG(amount) OVER w_three, 2) AS avg_last_three
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_three AS (
        w_time ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Ở đơn 1004 của Lan, `(80+50+200)/3 = 110.00`.

### Bài 8. OVER w với frame

`SUM(amount) OVER w_running` hợp lệ; `OVER (w_running)` cố sao chép một định nghĩa đã chứa frame nên không hợp lệ trong PostgreSQL.

### Bài 9. LAST_VALUE toàn lịch sử

~~~sql
SELECT
    customer_id,
    order_id,
    LAST_VALUE(amount) OVER w_full AS last_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, order_id;
~~~

Mọi dòng của Lan có `last_amount = 200.00`.

### Bài 10. Peer rows

1002 và 1003 có cùng `ordered_at` nên `RANGE` mặc định tính cả peer group khi tới timestamp đó. Để có tổng 200 rồi 250:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

### Bài 11. GROUPS

Tại đơn 1004 ngày 10/01, frame gồm nhóm 07/01 (80+50) và nhóm 10/01 (200), tổng **330.00**.

### Bài 12. Lọc và ranking

(a) chỉ đơn paid được xếp, 1004 có `rn = 3`. (b) xếp mọi đơn trước rồi lọc, 1004 có `rn = 4`.

### Bài 13. Top 1 mỗi khách

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER w_latest AS rn
    FROM window_lab.sales_orders AS o
    WINDOW w_latest AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT c.customer_id, r.order_id
FROM window_lab.customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
~~~

Đơn 1004, 2003, 3003; Dung có `order_id = NULL`.

### Bài 14. Running paid

~~~sql
SELECT
    customer_id,
    order_id,
    status,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid')
            OVER w_running,
        0::numeric
    ) AS running_paid
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Lan sau 1004: `400.00`.

### Bài 15. Ties

`RANK`: 1,2,2,4; `DENSE_RANK`: 1,2,2,3. Cần ít nhất hai định nghĩa thứ tự: `w_score AS (ORDER BY score DESC)` giữ peers cho ranking; `w_stable AS (ORDER BY score DESC, unique_id)` để đánh số từng hàng có thứ tự ổn định.

### Bài 16. Grouped sums

~~~sql
SELECT
    customer_id,
    channel,
    SUM(amount) AS channel_amount,
    SUM(SUM(amount)) OVER w_customer AS customer_amount,
    COUNT(*) OVER w_customer AS n_channel_groups
FROM window_lab.sales_orders
GROUP BY customer_id, channel
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, channel;
~~~

`COUNT(*) OVER w_customer` đếm số **nhóm kênh sau GROUP BY**, không phải số hàng đơn ban đầu.

### Bài 17. Output ordering

Không. Cần thêm `ORDER BY` cuối câu `SELECT`, chẳng hạn `ORDER BY customer_id, ordered_at, order_id`.

### Bài 18. Sửa vị trí và kế thừa

Đặt `WINDOW` trước `ORDER BY` ngoài cùng, đặt `w_base` trước `w_child`, và tạo cửa sổ `w_amount` từ một base **chưa có `ORDER BY`** thay vì ghi đè cửa sổ đã sắp theo thời gian.

### Bài 19. Index và EXPLAIN

~~~sql
CREATE INDEX idx_orders_customer_time
ON window_lab.sales_orders (
    customer_id, ordered_at, order_id
);

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

Đánh giá `WindowAgg`, `Sort`/`Index Scan`, thời gian và buffers trên dữ liệu đủ lớn. Index không bảo đảm được chọn trong mọi plan.

### Bài 20. Ngày không có đơn

`WINDOW` không tạo các ngày rỗng. Dùng `generate_series` làm trục ngày, `LEFT JOIN` với aggregate theo ngày, `COALESCE` để hiển thị 0 và dùng `SUM(day_amount) OVER w_running` trên kết quả lịch.

### Bài 21. ROUND và kiểu kết quả

~~~sql
SELECT
    order_id,
    ROUND(
        (PERCENT_RANK() OVER w_amount)::numeric,
        3
    ) AS percent_rank_rounded
FROM window_lab.sales_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount
);
~~~

`PERCENT_RANK` trả số thực dấu phẩy động; ép sang `numeric` cho phép chọn overload `ROUND(numeric, integer)`.

### Bài 22. Phạm vi named window

Tên `WINDOW` dùng trong **một query block**. Nó không lưu dữ liệu, không thay view/CTE cho việc tái sử dụng nguồn dữ liệu giữa các query, và không tự bảo đảm có index hay giảm thời gian thực thi. Lợi ích chính là **định nghĩa partition/order/frame rõ ràng, nhất quán, có thể dùng lại trong cùng SELECT**.

## 32. Bảng cú pháp tra cứu nhanh

| Nhu cầu | Mẫu SQL |
| --- | --- |
| Định nghĩa window có tên | `WINDOW w AS (PARTITION BY key ORDER BY time_col)` |
| Tham chiếu trực tiếp | `ROW_NUMBER() OVER w` |
| Cửa sổ không partition/order | `WINDOW w_all AS ()` |
| Copy cửa sổ chưa có frame | `OVER (w ROWS BETWEEN ...)` |
| Kế thừa partition rồi thêm order | `WINDOW base AS (PARTITION BY key), ordered AS (base ORDER BY time_col)` |
| Kế thừa và thêm frame | `WINDOW running AS (ordered ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` |
| Toàn partition có ORDER BY | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` |
| Trung bình ba hàng gần nhất | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Tổng lũy kế | `SUM(value) OVER running` |
| Xem giá trị trước/sau | `LAG(value) OVER ordered`, `LEAD(value) OVER ordered` |
| Xếp thứ tự | `ROW_NUMBER() OVER ordered` |
| Đồng hạng | `RANK() OVER w_score`, `DENSE_RANK() OVER w_score` |
| Giá trị cuối toàn partition | `LAST_VALUE(value) OVER full_frame` |
| Tổng paid lũy kế | `SUM(amount) FILTER (WHERE status='paid') OVER running` |
| Lọc top N theo khách | CTE tính `ROW_NUMBER` rồi `WHERE rn <= N` ở ngoài |
| Kiểm tra plan | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` |

## 33. Checklist trước khi dùng WINDOW trong hệ thống thật

| Câu hỏi | Tác dụng |
| --- | --- |
| Một hàng đầu vào đại diện cho đơn, khách hay nhóm ngày? | Tránh sai độ chi tiết thống kê |
| Cần giữ từng hàng hay gộp bằng GROUP BY? | Chọn window hay aggregate nhóm |
| Partition là gì? | Xác định đúng ranh giới dữ liệu |
| ORDER BY dùng cột nào và có khóa phá hòa không? | Tránh thứ tự không xác định |
| Hàm có nhạy với frame không? | Đặc biệt SUM, AVG, FIRST/LAST/NTH_VALUE |
| Frame mặc định RANGE có ảnh hưởng peers? | Tránh tổng lũy kế nhảy theo nhóm không mong muốn |
| Có cần ROWS, RANGE hay GROUPS? | Chọn đúng đơn vị khung |
| Có thể tái sử dụng partition/order không? | Đặt tên WINDOW cơ sở |
| Định nghĩa kế thừa có frame ở base không? | Tránh lỗi copy |
| Có nhiều cửa sổ dùng thứ tự khác nhau? | Đánh giá chi phí sort |
| Filter trước hay sau tính window? | Tránh đổi ý nghĩa ranking |
| Kết quả có thiếu khách/ngày không có dữ liệu? | Bổ sung bảng nguồn/LEFT JOIN/trục ngày |
| Hàm thống kê trả kiểu gì? | Tránh lỗi cast/ROUND |
| EXPLAIN cho thấy sort, WindowAgg và buffers ra sao? | Tối ưu trên dữ liệu đại diện |

## 34. Tổng kết

Trong PostgreSQL, mệnh đề **`WINDOW` cho phép đặt tên một hoặc nhiều định nghĩa cửa sổ trong cùng `SELECT`** để các hàm sử dụng qua `OVER window_name`. Đây là công cụ quan trọng khi một báo cáo có nhiều phép tính cùng phân nhóm theo khách, kênh hoặc thời gian, nhờ đó tránh lặp lại `PARTITION BY` và `ORDER BY` ở từng hàm.

Ba nguyên tắc cần nhớ:

1. **`PARTITION BY` quyết định nhóm, `ORDER BY` quyết định thứ tự và frame quyết định phạm vi hàng đóng góp vào những hàm phụ thuộc frame.** Với phép lũy kế, nên khai báo `ROWS ... CURRENT ROW` và khóa phá hòa nếu muốn tăng theo từng giao dịch.
2. **`OVER w` tham chiếu trực tiếp named window; `OVER (w ...)` sao chép để mở rộng.** PostgreSQL không cho sao chép một named window đã có frame, nên hãy xây một cửa sổ cơ sở chưa có frame rồi phát triển các biến thể `w_running`, `w_full`, `w_last_three`.
3. **Tái sử dụng cửa sổ là tái sử dụng định nghĩa logic, không phải cache dữ liệu hoặc bảo đảm tăng tốc.** Chọn phương án theo ý nghĩa nghiệp vụ, kiểm tra peer groups, khung mặc định, thứ tự lọc và dùng `EXPLAIN` để đánh giá hiệu năng.

Khi viết một báo cáo có nhiều window functions, hãy hỏi: **“Những phép tính nào thật sự cùng partition và order? Những phép nào cần frame khác nhau?”**. Khai báo `WINDOW` theo các tầng **partition → order → frame**, rồi gắn từng hàm vào cửa sổ đúng mục đích. Cách này giữ câu SQL dễ đọc, làm rõ quy tắc phân tích và giảm lỗi khi báo cáo phát triển.

# COUNT, SUM, AVG, MIN, MAX và giá trị NULL trong PostgreSQL

Một hệ thống bán hàng có thể cần trả lời: **đã có bao nhiêu đơn**, **tổng giá trị đơn đã thanh toán là bao nhiêu**, **giá trị trung bình mỗi đơn**, **đơn nhỏ nhất/lớn nhất** và **có bao nhiêu dòng chưa biết số tiền**. Những câu hỏi đó thường dùng các hàm tổng hợp (*aggregate functions*) `COUNT`, `SUM`, `AVG`, `MIN` và `MAX`.

Điểm dễ gây nhầm lẫn là PostgreSQL xử lý **`NULL`** theo những quy tắc khác nhau: `COUNT(*)` đếm mọi hàng, `COUNT(column)` bỏ qua giá trị `NULL` của cột đó; `SUM`, `AVG`, `MIN` và `MAX` cũng bỏ qua `NULL`, nhưng **thường trả `NULL` chứ không trả 0 khi không có giá trị đầu vào phù hợp**. Kết quả có thể ảnh hưởng trực tiếp đến doanh thu, tỷ lệ chuyển đổi, chất lượng dữ liệu và logic API.

Bài học này hướng dẫn từ câu lệnh tổng hợp cơ bản đến `GROUP BY`, `WHERE`, `HAVING`, `DISTINCT`, `FILTER`, `LEFT JOIN`, `COALESCE`, phép tính tỷ lệ và kiểu dữ liệu kết quả. Một bộ bảng thực hành nhỏ giúp tự kiểm chứng mọi ví dụ. Trọng tâm là **chọn đúng mẫu số, hiểu giá trị thiếu và diễn giải kết quả theo nghiệp vụ**, không chỉ viết ra câu SQL chạy được.

## 1. Nhìn nhanh năm hàm tổng hợp

Các hàm tổng hợp nhận **một tập các hàng hoặc giá trị** rồi tạo ra một kết quả tổng hợp cho mỗi nhóm:

| Hàm | Câu hỏi trả lời | Có tính giá trị NULL vào phép tính không? | Kết quả với không có giá trị phù hợp |
| --- | --- | --- | --- |
| `COUNT(*)` | Có bao nhiêu **hàng**? | Đếm cả hàng chứa NULL | `0` |
| `COUNT(expression)` | Có bao nhiêu giá trị **khác NULL** của biểu thức? | Không | `0` |
| `SUM(expression)` | Tổng các giá trị số/kiểu được hỗ trợ là bao nhiêu? | Bỏ qua NULL | `NULL` |
| `AVG(expression)` | Trung bình các giá trị có mặt là bao nhiêu? | Bỏ qua NULL | `NULL` |
| `MIN(expression)` | Giá trị nhỏ nhất là gì? | Bỏ qua NULL | `NULL` |
| `MAX(expression)` | Giá trị lớn nhất là gì? | Bỏ qua NULL | `NULL` |

Những kết quả cuối cột đặc biệt quan trọng khi không có hàng sau `WHERE`, hoặc khi **mọi giá trị của cột đang tổng hợp đều là `NULL`**.

Một truy vấn tổng hợp đơn giản:

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(net_amount) AS total_amount,
    AVG(net_amount) AS average_amount,
    MIN(net_amount) AS smallest_amount,
    MAX(net_amount) AS largest_amount
FROM some_orders;
~~~

`some_orders` ở đây là tên minh họa; những ví dụ thực hành bên dưới sẽ dùng bảng `agg_lab_151.orders` có thể tạo bằng SQL.

### 1.1. Aggregate khác phép tính trên từng hàng

~~~sql
-- Biểu thức theo từng hàng:
SELECT 100 + 20 AS value_per_expression;

-- Tổng hợp từ nhiều hàng:
SELECT SUM(amount)
FROM (
    VALUES (100), (20), (30)
) AS v(amount);
-- 150
~~~

Với aggregate, PostgreSQL lấy các giá trị đầu vào tương ứng rồi tính một kết quả đại diện cho tập đó. Nếu dùng `GROUP BY`, mỗi nhóm được tính riêng. Nếu không `GROUP BY`, toàn bộ những hàng đi qua `FROM`/`WHERE` được xem như **một nhóm tổng hợp**.

## 2. Chuẩn bị dữ liệu thực hành

Hãy tạo schema riêng trên **database học tập**, không chạy các lệnh tạo bảng/seed trên production. Nếu schema `agg_lab_151` đã tồn tại và có dữ liệu từ lần thực hành khác, nên chọn tên schema khác; không tự ý xóa dữ liệu đang có.

### 2.1. Bảng khách hàng

~~~sql
CREATE SCHEMA agg_lab_151;

CREATE TABLE agg_lab_151.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NULL
);

INSERT INTO agg_lab_151.customers
    (customer_id, customer_name, region)
VALUES
    (1, 'Nguyễn An',  'Hà Nội'),
    (2, 'Trần Bình',  'Đà Nẵng'),
    (3, 'Lê Chi',     'TP.HCM'),
    (4, 'Phạm Dũng',  NULL);
~~~

Khách `4` **chưa có đơn**. Điều này giúp quan sát sự khác biệt giữa `COUNT(*)` và `COUNT(o.order_id)` khi dùng `LEFT JOIN`.

### 2.2. Bảng đơn hàng

~~~sql
CREATE TABLE agg_lab_151.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NULL
        REFERENCES agg_lab_151.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'NEW', 'CANCELLED')),
    order_date DATE NOT NULL,
    net_amount NUMERIC(12, 2) NULL
        CHECK (net_amount >= 0),
    shipping_fee NUMERIC(12, 2) NULL
        CHECK (shipping_fee >= 0),
    rating INTEGER NULL
        CHECK (rating BETWEEN 1 AND 5)
);
~~~

Các giá trị `NULL` có ý nghĩa minh họa:

- `net_amount = NULL`: số tiền chưa được xác định/ghi nhận ở thời điểm xem dữ liệu.
- `net_amount = 0`: **đã biết số tiền bằng 0**, ví dụ đơn khuyến mãi miễn phí.
- `shipping_fee = NULL`: phí vận chuyển chưa được ghi nhận, **không mặc nhiên là miễn phí**.
- `rating = NULL`: khách chưa đánh giá.
- `customer_id = NULL`: đơn của khách vãng lai.

### 2.3. Nạp tám đơn hàng

~~~sql
INSERT INTO agg_lab_151.orders
    (
        order_id, customer_id, status, order_date,
        net_amount, shipping_fee, rating
    )
VALUES
    (101, 1,    'PAID',      DATE '2026-11-01', 120000, 15000, 5),
    (102, 1,    'NEW',       DATE '2026-11-02', NULL,   NULL,  NULL),
    (103, 2,    'PAID',      DATE '2026-11-02',  80000,     0, 4),
    (104, 2,    'CANCELLED', DATE '2026-11-03', 200000, NULL,  NULL),
    (105, 3,    'PAID',      DATE '2026-11-03',      0, 10000, NULL),
    (106, 3,    'PAID',      DATE '2026-11-04', 300000, NULL,  3),
    (107, NULL, 'PAID',      DATE '2026-11-04', 120000,  5000, NULL),
    (108, 1,    'NEW',       DATE '2026-11-05', NULL,   NULL,  NULL);
~~~

Hai đơn `101` và `107` **cùng số tiền 120.000 nhưng là hai đơn khác nhau**. Điều này đặc biệt quan trọng khi phân tích `SUM(DISTINCT net_amount)`: trùng giá trị **không phải** trùng giao dịch.

### 2.4. Xem dữ liệu gốc

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    net_amount,
    shipping_fee,
    rating
FROM agg_lab_151.orders
ORDER BY order_id;
~~~

| Đơn | Khách | Trạng thái | `net_amount` | `shipping_fee` | `rating` |
| --- | ---: | --- | ---: | ---: | ---: |
| 101 | 1 | PAID | 120.000 | 15.000 | 5 |
| 102 | 1 | NEW | `NULL` | `NULL` | `NULL` |
| 103 | 2 | PAID | 80.000 | 0 | 4 |
| 104 | 2 | CANCELLED | 200.000 | `NULL` | `NULL` |
| 105 | 3 | PAID | 0 | 10.000 | `NULL` |
| 106 | 3 | PAID | 300.000 | `NULL` | 3 |
| 107 | `NULL` | PAID | 120.000 | 5.000 | `NULL` |
| 108 | 1 | NEW | `NULL` | `NULL` | `NULL` |

Dữ liệu có **8 đơn**, trong đó **5 PAID**, **2 NEW**, **1 CANCELLED**. Có **6 giá trị `net_amount` đã biết**, **2 `NULL`**, và **3 đánh giá `rating`**. Trong sáu giá trị tiền có một giá trị 0 hợp lệ.

## 3. COUNT(*): đếm số hàng

`COUNT(*)` đếm tất cả các hàng mà truy vấn đang xét, bất kể cột bên trong có `NULL` hay không.

~~~sql
SELECT COUNT(*) AS total_orders
FROM agg_lab_151.orders;
-- 8
~~~

`COUNT(*)` **không đọc một cột riêng để quyết định có đếm hay không**. Nó đếm hàng, cho nên đơn `102`, `108` với `net_amount = NULL` vẫn được tính.

### 3.1. COUNT(*) kết hợp WHERE

~~~sql
SELECT COUNT(*) AS paid_orders
FROM agg_lab_151.orders
WHERE status = 'PAID';
-- 5
~~~

`WHERE` lọc hàng **trước** khi `COUNT(*)` đếm. Vì vậy, `COUNT(*)` không nhất thiết là số hàng toàn bảng; nó là số hàng **sau mọi điều kiện lọc có liên quan**.

### 3.2. COUNT(*) khi không có dòng

~~~sql
SELECT COUNT(*) AS cancelled_before_2020
FROM agg_lab_151.orders
WHERE status = 'CANCELLED'
  AND order_date < DATE '2020-01-01';
-- 0
~~~

Không có hàng nào thỏa điều kiện, nhưng câu truy vấn tổng hợp **không có GROUP BY** vẫn trả **một hàng**, với `COUNT(*) = 0`.

### 3.3. COUNT(1) và COUNT(*) trong PostgreSQL

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(1) AS all_constant_ones
FROM agg_lab_151.orders;
-- 8, 8
~~~

Vì biểu thức hằng `1` không phải `NULL` ở mỗi hàng, `COUNT(1)` đếm cùng số lượng như `COUNT(*)` trong ví dụ này. Trong PostgreSQL, **`COUNT(*)` là cách viết rõ nghĩa và phổ biến để đếm hàng**. Không nên chọn `COUNT(1)` vì tin rằng nó luôn nhanh hơn; việc tối ưu phụ thuộc planner/phiên bản và ngữ cảnh thực tế.

## 4. COUNT(cột): đếm số giá trị khác NULL

`COUNT(expression)` chỉ tăng bộ đếm khi **giá trị của biểu thức không phải `NULL`**.

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(customer_id) AS orders_with_registered_customer,
    COUNT(net_amount) AS orders_with_known_amount,
    COUNT(shipping_fee) AS orders_with_known_shipping,
    COUNT(rating) AS rated_orders
FROM agg_lab_151.orders;
~~~

| Biểu thức | Kết quả | Vì sao? |
| --- | ---: | --- |
| `COUNT(*)` | 8 | Tất cả đơn |
| `COUNT(customer_id)` | 7 | Đơn 107 không có khách đăng ký |
| `COUNT(net_amount)` | 6 | Đơn 102 và 108 có tiền `NULL` |
| `COUNT(shipping_fee)` | 4 | Chỉ các đơn 101, 103, 105, 107 có phí đã ghi |
| `COUNT(rating)` | 3 | Chỉ các đơn 101, 103, 106 có đánh giá |

**Giá trị 0 vẫn được đếm.** `COUNT(net_amount)` tính đơn `105` vì tiền bằng 0 **khác `NULL`**. `COUNT(shipping_fee)` cũng tính đơn `103` vì phí bằng 0 đã biết.

### 4.1. COUNT trên biểu thức

Đối số không bắt buộc là tên cột:

~~~sql
SELECT
    COUNT(net_amount + shipping_fee)
        AS orders_with_both_amount_and_shipping
FROM agg_lab_151.orders;
-- 4
~~~

Để `net_amount + shipping_fee` khác `NULL`, **cả hai giá trị đều phải có mặt**. Các đơn thỏa là `101`, `103`, `105` và `107`. Cả bốn đơn này đều có hai giá trị khác NULL, nên kết quả là **4**. Đây là điểm dễ nhầm nếu chỉ nhìn cột tiền mà quên kiểm tra phí giao hàng.

Viết cùng ý nghĩa theo điều kiện tường minh:

~~~sql
SELECT COUNT(*) AS both_known
FROM agg_lab_151.orders
WHERE net_amount IS NOT NULL
  AND shipping_fee IS NOT NULL;
-- 4
~~~

Nếu muốn **ít nhất một** trong hai trường có giá trị, `COUNT(net_amount + shipping_fee)` không thích hợp vì phép cộng với `NULL` trả `NULL`. Cần viết điều kiện `OR` hoặc quy tắc `COALESCE` có chủ đích.

### 4.2. COUNT(*) - COUNT(cột): đếm giá trị NULL

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(net_amount) AS known_amounts,
    COUNT(*) - COUNT(net_amount) AS missing_amounts
FROM agg_lab_151.orders;
-- 8, 6, 2
~~~

Cách này hữu ích để đo tỷ lệ dữ liệu thiếu. Một cách khác, thường dễ đọc hơn:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS missing_amounts
FROM agg_lab_151.orders;
-- 2
~~~

Khi dùng `COUNT(cột)` để thay `COUNT(*)`, hãy luôn hỏi **cột đó có thể `NULL` không?** Nếu có, hai hàm có thể trả các con số khác nhau.

## 5. SUM: tổng các giá trị đã biết

`SUM(expression)` cộng các giá trị **khác `NULL`**. Nó không xem `NULL` như số 0 trong dữ liệu; chỉ bỏ qua các giá trị không có mặt trong phép tổng.

~~~sql
SELECT SUM(net_amount) AS total_known_amount
FROM agg_lab_151.orders;
-- 820000.00
~~~

Các giá trị được cộng:

~~~text
120000 + 80000 + 200000 + 0 + 300000 + 120000
= 820000
~~~

Hai đơn `NEW` có `net_amount = NULL` không đóng góp giá trị. Đơn `105` có `net_amount = 0` vẫn là một giá trị đã biết, nhưng không làm thay đổi tổng số học.

### 5.1. Tổng tiền chưa chắc là doanh thu

Kết quả `820000` ở trên **bao gồm đơn `CANCELLED` có số tiền 200000**. Nếu yêu cầu là tổng tiền của các đơn đã thanh toán, phải lọc trạng thái:

~~~sql
SELECT SUM(net_amount) AS paid_amount
FROM agg_lab_151.orders
WHERE status = 'PAID';
-- 620000.00
~~~

Chính sách kế toán thực tế có thể còn phải xét hoàn tiền, thuế, phí, thời điểm thanh toán và đối soát giao dịch. `SUM` chỉ cộng **những giá trị mà truy vấn đưa vào**, không tự hiểu định nghĩa doanh thu của doanh nghiệp.

### 5.2. Tổng số nguyên

~~~sql
SELECT SUM(x) AS total_integer_values
FROM (
    VALUES (10::integer), (20::integer), (30::integer)
) AS v(x);
-- 60
~~~

PostgreSQL có quy tắc kiểu kết quả cụ thể: `SUM(integer)` thường trả `bigint`, còn `SUM(bigint)` trả `numeric` để có phạm vi biểu diễn lớn hơn. Không nên ép tổng số lượng lớn về `integer` khi không cần thiết.

### 5.3. SUM với số âm

`SUM` không yêu cầu mọi giá trị dương:

~~~sql
SELECT SUM(adjustment) AS net_change
FROM (
    VALUES
        (1000::numeric),
        (-200::numeric),
        (NULL::numeric),
        (300::numeric)
) AS t(adjustment);
-- 1100
~~~

Tổng số học `1000 - 200 + 300 = 1100`. Giá trị `NULL` không được cộng. Nếu số âm biểu thị hoàn tiền hoặc điều chỉnh, việc dùng `SUM` là hợp lý **khi cách ghi dữ liệu nhất quán và phạm vi được xác định**.

## 6. AVG: trung bình trên những giá trị không NULL

`AVG(expression)` lấy trung bình các giá trị đầu vào **khác `NULL`**. Điều này tương đương ý tưởng:

\[
\operatorname{AVG}(x)
= \frac{\operatorname{SUM}(x)}{\operatorname{COUNT}(x)}
\]

trong trường hợp có ít nhất một giá trị không NULL và việc so sánh kiểu/số học được xử lý phù hợp. **Mẫu số không phải `COUNT(*)` nếu cột có `NULL`.**

~~~sql
SELECT
    SUM(net_amount) AS total_known_amount,
    COUNT(net_amount) AS known_amount_count,
    AVG(net_amount) AS average_known_amount
FROM agg_lab_151.orders;
~~~

Kết quả:

~~~text
total_known_amount = 820000.00
known_amount_count = 6
average_known_amount ≈ 136666.67
~~~

### 6.1. AVG bỏ qua NULL nhưng tính 0

Đơn `105` với `net_amount = 0` được tính vào **mẫu số 6**. Hai đơn `NEW` có tiền `NULL` không được tính.

Nếu thay `NULL` bằng 0 trước khi tính AVG:

~~~sql
SELECT
    AVG(net_amount) AS average_known,
    AVG(COALESCE(net_amount, 0))
        AS average_when_missing_is_zero
FROM agg_lab_151.orders;
~~~

| Cách tính | Tổng | Số giá trị chia | Trung bình xấp xỉ |
| --- | ---: | ---: | ---: |
| `AVG(net_amount)` | 820.000 | 6 | 136.666,67 |
| `AVG(COALESCE(net_amount, 0))` | 820.000 | 8 | 102.500,00 |

Hai câu trả lời khác nhau vì **hai định nghĩa thống kê khác nhau**:

- Trung bình của các đơn **đã biết số tiền**.
- Trung bình của **mọi đơn**, quy ước đơn chưa biết tiền được tính là 0.

Không thể coi một trong hai luôn đúng mà chưa biết ý nghĩa nghiệp vụ của `NULL`.

### 6.2. AVG chỉ trên đơn đã thanh toán

~~~sql
SELECT
    COUNT(*) AS paid_orders,
    COUNT(net_amount) AS paid_orders_with_amount,
    SUM(net_amount) AS paid_total,
    AVG(net_amount) AS paid_average
FROM agg_lab_151.orders
WHERE status = 'PAID';
~~~

Đáp án: **5 đơn PAID**, **5 giá trị tiền đã biết**, tổng **620.000**, trung bình **124.000**.

Nếu dữ liệu thật có đơn `PAID` nhưng `net_amount IS NULL`, `AVG(net_amount)` sẽ bỏ qua dòng đó. Điều này có thể khiến số trung bình trông hợp lệ dù còn lỗi dữ liệu. Nên báo cáo **`COUNT(*)` song song `COUNT(net_amount)`** để thấy độ đầy đủ.

### 6.3. Trung bình đánh giá

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(rating) AS rated_orders,
    AVG(rating) AS average_rating,
    MIN(rating) AS lowest_rating,
    MAX(rating) AS highest_rating
FROM agg_lab_151.orders;
~~~

Ba rating đã biết là `5`, `4` và `3`:

- `COUNT(rating) = 3`.
- `AVG(rating) = 4`.
- `MIN(rating) = 3`.
- `MAX(rating) = 5`.

**Không chia tổng điểm đánh giá cho 8 đơn** nếu mục tiêu là trung bình trong số những khách đã đánh giá. Ngược lại, để đo **tỷ lệ đơn có đánh giá**, mẫu số lại là toàn bộ số đơn: `COUNT(rating) / COUNT(*)`.

### 6.4. Bình quân có trọng số

Một lỗi phân tích phổ biến: tính **trung bình của các số trung bình nhóm** thay vì trung bình theo số quan sát.

Giả sử ba nhóm có:

~~~text
Nhóm A: 1 đơn PAID, trung bình 120000
Nhóm B: 1 đơn PAID, trung bình  80000
Nhóm C: 2 đơn PAID, trung bình 150000
~~~

Trung bình không trọng số của ba trung bình nhóm là:

\[
(120000 + 80000 + 150000)/3 \approx 116666.67
\]

Nhưng trung bình theo **bốn đơn** của ba khách đăng ký:

\[
(120000 + 80000 + 0 + 300000)/4 = 125000
\]

Hai số khác nhau vì số đơn trong từng nhóm khác nhau. Nếu mục tiêu là “mỗi **đơn** có trọng số như nhau”, cần lấy tổng số tiền chia cho **tổng số đơn có giá trị phù hợp**; nếu mục tiêu là “mỗi **khách** có trọng số như nhau”, trung bình các trung bình theo khách có thể hợp lý.

## 7. MIN và MAX: nhỏ nhất và lớn nhất

`MIN` và `MAX` chọn giá trị thấp nhất/cao nhất trong tập các giá trị khác `NULL`.

~~~sql
SELECT
    MIN(net_amount) AS min_known_amount,
    MAX(net_amount) AS max_known_amount,
    MIN(order_date) AS first_order_date,
    MAX(order_date) AS last_order_date
FROM agg_lab_151.orders;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `MIN(net_amount)` | `0.00` |
| `MAX(net_amount)` | `300000.00` |
| `MIN(order_date)` | `2026-11-01` |
| `MAX(order_date)` | `2026-11-05` |

### 7.1. MIN/MAX bỏ qua NULL

~~~sql
SELECT
    MIN(shipping_fee) AS min_known_fee,
    MAX(shipping_fee) AS max_known_fee
FROM agg_lab_151.orders;
~~~

Phí đã biết là `15000`, `0`, `10000` và `5000`:

- `MIN(shipping_fee) = 0`.
- `MAX(shipping_fee) = 15000`.

Không thể kết luận “mọi đơn đều có phí từ 0 đến 15.000”, bởi **bốn đơn có phí `NULL`** và không thể khẳng định phí thật của chúng.

### 7.2. MIN/MAX với kiểu dữ liệu không phải số

Hàm này còn có thể áp dụng cho các kiểu có quy tắc so sánh thích hợp, ví dụ ngày, thời gian, văn bản:

~~~sql
SELECT
    MIN(order_date) AS earliest,
    MAX(order_date) AS latest
FROM agg_lab_151.orders;
~~~

Với văn bản, “nhỏ nhất/lớn nhất” được quyết định theo quy tắc so sánh/collation, **không nhất thiết theo độ dài chuỗi hoặc nghĩa tự nhiên của từ**. Nếu muốn tìm đơn có giá trị nhỏ nhất kèm `order_id`, xem mục 7.3.

### 7.3. MIN/MAX không tự trả cả bản ghi tương ứng

~~~sql
SELECT MAX(net_amount)
FROM agg_lab_151.orders;
-- 300000
~~~

Truy vấn chỉ trả **giá trị lớn nhất**, không biết thuộc đơn nào. Một cách lấy cả bản ghi:

~~~sql
SELECT
    order_id, customer_id, status, net_amount
FROM agg_lab_151.orders
WHERE net_amount IS NOT NULL
ORDER BY net_amount DESC, order_id ASC
LIMIT 1;
~~~

Kết quả là đơn `106` trong bộ dữ liệu mẫu. Nếu có nhiều đơn cùng giá trị lớn nhất, `LIMIT 1` chỉ chọn một theo thứ tự phụ đã chỉ định. Muốn **tất cả** đơn đạt giá trị tối đa:

~~~sql
SELECT
    order_id, net_amount
FROM agg_lab_151.orders
WHERE net_amount = (
    SELECT MAX(net_amount)
    FROM agg_lab_151.orders
);
~~~

Không viết `SELECT order_id, MAX(net_amount)` mà bỏ `GROUP BY` rồi kỳ vọng PostgreSQL biết “order_id của dòng có max”. Đó là hai loại dữ liệu ở hai cấp khác nhau.

## 8. Giá trị NULL: phân biệt không có hàng và toàn giá trị NULL

Hai tình huống có thể cùng làm `SUM`/`AVG`/`MIN`/`MAX` trả `NULL`:

1. **Không có hàng nào** sau lọc.
2. Có hàng, nhưng **tất cả giá trị của biểu thức được tổng hợp đều là `NULL`**.

### 8.1. Tập hoàn toàn rỗng

~~~sql
SELECT
    COUNT(*) AS rows_found,
    COUNT(net_amount) AS amounts_found,
    SUM(net_amount) AS sum_amount,
    AVG(net_amount) AS avg_amount,
    MIN(net_amount) AS min_amount,
    MAX(net_amount) AS max_amount
FROM agg_lab_151.orders
WHERE order_id < 0;
~~~

Kết quả khái niệm:

| `rows_found` | `amounts_found` | `sum_amount` | `avg_amount` | `min_amount` | `max_amount` |
| ---: | ---: | --- | --- | --- | --- |
| 0 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

**`SUM` không mặc định trả 0 trên tập rỗng**. Đây là hành vi chuẩn quan trọng khi xây báo cáo.

### 8.2. Có hàng nhưng mọi giá trị của cột đều NULL

Hai đơn `NEW` có `net_amount = NULL`:

~~~sql
SELECT
    COUNT(*) AS new_orders,
    COUNT(net_amount) AS known_amounts,
    SUM(net_amount) AS total_amount,
    AVG(net_amount) AS average_amount,
    MIN(net_amount) AS minimum_amount,
    MAX(net_amount) AS maximum_amount
FROM agg_lab_151.orders
WHERE status = 'NEW';
~~~

Kết quả:

~~~text
new_orders     = 2
known_amounts  = 0
total_amount   = NULL
average_amount = NULL
minimum_amount = NULL
maximum_amount = NULL
~~~

So với mục 8.1, `COUNT(*)` giúp nhận ra sự khác biệt giữa **không có đơn** và **có đơn nhưng chưa ghi số tiền**.

### 8.3. Tổng hợp không GROUP BY và có GROUP BY

Không `GROUP BY`:

~~~sql
SELECT COUNT(*) AS cnt
FROM agg_lab_151.orders
WHERE status = 'REFUNDED';
-- Một hàng với cnt = 0.
~~~

Có `GROUP BY`:

~~~sql
SELECT status, COUNT(*) AS cnt
FROM agg_lab_151.orders
WHERE status = 'REFUNDED'
GROUP BY status;
-- Không trả hàng nào.
~~~

Khác biệt:

- Một truy vấn **aggregate không GROUP BY** trên tập rỗng vẫn tạo một nhóm tổng thể và trả một hàng.
- Truy vấn **có GROUP BY theo cột** trên tập rỗng không hình thành nhóm nào, nên trả **0 hàng**.

Khi xây API, cần phân biệt “một hàng có tổng bằng 0” với “không có hàng kết quả”, nhất là khi hiển thị danh sách tháng, ngày hoặc trạng thái.

## 9. COUNT(DISTINCT ...), SUM(DISTINCT ...) và AVG(DISTINCT ...)

Từ khóa `DISTINCT` trong aggregate loại bỏ **các giá trị đầu vào trùng nhau** trước khi tổng hợp. Với các hàm tổng hợp thông thường, `NULL` không đóng góp vào `COUNT(expression)` và những phép toán số.

### 9.1. Đếm khách hàng đăng ký có đơn

~~~sql
SELECT
    COUNT(*) AS order_count,
    COUNT(customer_id) AS orders_linked_to_customer,
    COUNT(DISTINCT customer_id) AS unique_customers_with_orders
FROM agg_lab_151.orders;
~~~

Kết quả:

- `COUNT(*) = 8`: tám đơn.
- `COUNT(customer_id) = 7`: bảy đơn gắn khách đã đăng ký, bỏ đơn guest.
- `COUNT(DISTINCT customer_id) = 3`: chỉ ba mã khách khác nhau `1`, `2`, `3`.

**`COUNT(DISTINCT customer_id)` không đếm khách chưa có đơn** (khách 4) vì bảng đầu vào là `orders`. Nếu cần đếm mọi khách trong hệ thống, truy vấn bảng `customers`.

### 9.2. DISTINCT không phải cách loại bản ghi trùng nghiệp vụ

Trong dataset, hai đơn `101` và `107` có cùng `net_amount = 120000`. Quan sát:

~~~sql
SELECT
    COUNT(net_amount) AS known_amount_rows,
    COUNT(DISTINCT net_amount) AS unique_amount_values,
    SUM(net_amount) AS normal_sum,
    SUM(DISTINCT net_amount) AS distinct_sum,
    AVG(net_amount) AS normal_avg,
    AVG(DISTINCT net_amount) AS distinct_avg
FROM agg_lab_151.orders;
~~~

| Chỉ số | Kết quả |
| --- | ---: |
| `COUNT(net_amount)` | 6 |
| `COUNT(DISTINCT net_amount)` | 5 |
| `SUM(net_amount)` | 820.000 |
| `SUM(DISTINCT net_amount)` | 700.000 |
| `AVG(net_amount)` | khoảng 136.666,67 |
| `AVG(DISTINCT net_amount)` | 140.000 |

`SUM(DISTINCT net_amount)` chỉ cộng giá trị 120.000 **một lần**, dù hai đơn khác nhau cùng có số tiền đó. Đây **không phải tổng doanh thu đúng** nếu cả hai đơn đều hợp lệ.

`DISTINCT` chỉ thích hợp khi người dùng **thực sự muốn tổng hợp các giá trị duy nhất**. Nếu nguồn dữ liệu có duplicate orders do JOIN sai, phải sửa JOIN hoặc thiết kế khóa/aggregation đúng cấp, **không dùng `SUM(DISTINCT money)` để che vấn đề**.

### 9.3. NULL trong COUNT(DISTINCT)

~~~sql
SELECT
    COUNT(DISTINCT customer_id) AS known_customers,
    COUNT(*) FILTER (WHERE customer_id IS NULL)
        AS guest_orders
FROM agg_lab_151.orders;
-- 3 và 1
~~~

`COUNT(DISTINCT customer_id)` không tạo một “khách hàng NULL” như một ID khác. Nhưng khi `GROUP BY customer_id`, PostgreSQL có thể nhóm các giá trị `NULL` lại thành **một nhóm** để tổng hợp. Hai hành vi này không mâu thuẫn: một bên là quy tắc của aggregate với đầu vào NULL, bên kia là quy tắc tạo nhóm.

## 10. GROUP BY: tổng hợp theo từng nhóm

Không có `GROUP BY`, tất cả đơn sau khi lọc được tổng hợp chung. Có `GROUP BY status`, PostgreSQL tạo một nhóm cho mỗi trạng thái.

~~~sql
SELECT
    status,
    COUNT(*) AS orders_count,
    COUNT(net_amount) AS known_amounts,
    SUM(net_amount) AS amount_sum,
    AVG(net_amount) AS amount_avg,
    MIN(net_amount) AS amount_min,
    MAX(net_amount) AS amount_max
FROM agg_lab_151.orders
GROUP BY status
ORDER BY status;
~~~

Kết quả chính:

| `status` | `orders_count` | `known_amounts` | `amount_sum` | `amount_avg` |
| --- | ---: | ---: | ---: | ---: |
| CANCELLED | 1 | 1 | 200.000 | 200.000 |
| NEW | 2 | 0 | `NULL` | `NULL` |
| PAID | 5 | 5 | 620.000 | 124.000 |

Một truy vấn dùng `GROUP BY` thường yêu cầu những cột trong `SELECT` **không nằm trong aggregate** phải tham gia nhóm hoặc được PostgreSQL xác định là phụ thuộc hàm theo các quy tắc được hỗ trợ. Ví dụ:

~~~sql
-- Sai trong truy vấn tổng hợp tổng quát:
-- SELECT status, order_id, COUNT(*)
-- FROM agg_lab_151.orders
-- GROUP BY status;
~~~

`order_id` không có một giá trị duy nhất cho mỗi nhóm `status`. Nếu muốn lấy danh sách ID, cần thiết kế truy vấn khác như `array_agg` hoặc truy vấn chi tiết, không chọn đại một ID.

### 10.1. GROUP BY trên nhiều cột

~~~sql
SELECT
    order_date,
    status,
    COUNT(*) AS count_orders,
    SUM(net_amount) AS sum_known_amount
FROM agg_lab_151.orders
GROUP BY order_date, status
ORDER BY order_date, status;
~~~

Mỗi cặp **`(order_date, status)`** là một nhóm riêng. Nếu cùng ngày có nhiều đơn cùng trạng thái, chúng được tính chung; nếu khác trạng thái, chúng là các nhóm khác nhau.

### 10.2. GROUP BY có thể tạo nhóm NULL

Với khách vãng lai:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS orders_count,
    SUM(net_amount) AS amount_sum
FROM agg_lab_151.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

Những nhóm có mặt:

| `customer_id` | Số đơn | Tổng tiền đã biết |
| --- | ---: | ---: |
| 1 | 3 | 120.000 |
| 2 | 2 | 280.000 |
| 3 | 2 | 300.000 |
| `NULL` | 1 | 120.000 |

Hàng `customer_id IS NULL` được gom thành một nhóm guest. **Không có nhóm khách 4** vì khách 4 chưa có dòng nào trong bảng `orders`. Muốn liệt kê cả khách chưa có đơn, cần truy vấn từ bảng `customers` với `LEFT JOIN` như mục 13.

## 11. WHERE và HAVING: lọc trước hay sau tổng hợp?

Hai mệnh đề phục vụ hai giai đoạn:

- `WHERE` lọc **hàng đầu vào**, trước `GROUP BY` và aggregate.
- `HAVING` lọc **nhóm**, sau khi tính aggregate tương ứng.

### 11.1. WHERE: chỉ xét đơn PAID

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_orders,
    SUM(net_amount) AS paid_amount
FROM agg_lab_151.orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

Lúc này các nhóm chỉ được xây từ **năm đơn PAID**. Khách 2 có một đơn PAID, dù tổng cộng có hai đơn gồm một đơn CANCELLED.

### 11.2. HAVING: chỉ giữ nhóm có từ hai đơn trở lên

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    SUM(net_amount) AS amount_sum
FROM agg_lab_151.orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

Truy vấn giữ các khách 1, 2, 3; nhóm guest chỉ có một đơn nên bị loại. `HAVING COUNT(*) >= 2` là điều kiện trên **kết quả của nhóm**, không thể thay trực tiếp bằng `WHERE COUNT(*) >= 2`.

### 11.3. WHERE + HAVING

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(net_amount) AS paid_amount
FROM agg_lab_151.orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(net_amount) >= 100000
ORDER BY customer_id NULLS LAST;
~~~

Chỉ những nhóm có **tổng tiền PAID từ 100.000 trở lên** mới xuất hiện. Nên diễn giải rõ rằng `WHERE` đã loại đơn không PAID trước, nên `HAVING` không cộng `net_amount` của đơn CANCELLED.

## 12. FILTER: tính nhiều chỉ số có điều kiện trong một truy vấn

PostgreSQL hỗ trợ cú pháp:

~~~sql
aggregate_function(...) FILTER (WHERE condition)
~~~

Nó cho phép một aggregate chỉ xem những hàng thỏa điều kiện **mà không loại các hàng đó khỏi các aggregate khác trong cùng truy vấn**.

### 12.1. Đếm PAID, NEW và CANCELLED cùng lúc

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'NEW')
        AS new_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELLED')
        AS cancelled_orders
FROM agg_lab_151.orders;
~~~

Kết quả: `total_orders = 8`, `paid_orders = 5`, `new_orders = 2`, `cancelled_orders = 1`.

### 12.2. Tổng hợp tiền và mức độ thiếu dữ liệu theo trạng thái

~~~sql
SELECT
    COUNT(*) AS all_orders,
    SUM(net_amount) FILTER (WHERE status = 'PAID')
        AS paid_amount,
    AVG(net_amount) FILTER (WHERE status = 'PAID')
        AS average_paid_amount,
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS missing_amount_orders,
    COUNT(*) FILTER (WHERE net_amount = 0)
        AS zero_amount_orders,
    COUNT(*) FILTER (
        WHERE status = 'PAID' AND net_amount IS NULL
    ) AS paid_but_amount_missing
FROM agg_lab_151.orders;
~~~

Đáp án:

| Chỉ số | Kết quả |
| --- | ---: |
| Tất cả đơn | 8 |
| Tổng tiền đơn PAID | 620.000 |
| Trung bình tiền đơn PAID | 124.000 |
| Đơn có tiền `NULL` | 2 |
| Đơn có tiền bằng 0 | 1 |
| Đơn PAID nhưng tiền `NULL` | 0 |

`FILTER` rất phù hợp cho dashboard cần nhiều KPI trên cùng tập dữ liệu. **Điều kiện `FILTER` chỉ tác động tới aggregate mà nó gắn vào**, không phải toàn bộ câu `SELECT`.

### 12.3. FILTER và WHERE khác nhau

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders
FROM agg_lab_151.orders;
-- 8, 5
~~~

So với:

~~~sql
SELECT
    COUNT(*) AS orders_after_where,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_after_where
FROM agg_lab_151.orders
WHERE status = 'PAID';
-- 5, 5
~~~

Ở truy vấn thứ hai, `WHERE` đã loại mọi đơn không PAID trước khi cả hai aggregate xử lý. Vì vậy không thể dùng truy vấn đó để lấy **tổng số đơn trên toàn bảng**.

### 12.4. Trường hợp không có hàng thỏa FILTER

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_count,
    SUM(net_amount) FILTER (WHERE status = 'REFUNDED')
        AS refunded_amount
FROM agg_lab_151.orders;
~~~

Trong dataset không có `REFUNDED`:

- `refunded_count = 0`.
- `refunded_amount = NULL`.

`FILTER` không làm thay đổi quy tắc trả `NULL` của `SUM` khi không có giá trị đầu vào. Muốn hiện 0 trong báo cáo, có thể thêm `COALESCE` với quyết định nghiệp vụ phù hợp.

## 13. LEFT JOIN và bẫy COUNT(*)

Một bài toán hay gặp: **liệt kê mọi khách hàng, kể cả khách chưa đặt đơn**.

Nếu xuất phát từ `customers` và `LEFT JOIN orders`, khách không có đơn vẫn xuất hiện dưới dạng **một hàng kết quả join**, trong đó các cột của bảng `orders` là `NULL`.

### 13.1. COUNT(*) sai khi mục tiêu là đếm số đơn của mỗi khách

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Với khách 4, `COUNT(*) = 1` **dù khách không có đơn**. Lý do: `LEFT JOIN` vẫn tạo một hàng để bảo toàn khách bên trái.

### 13.2. COUNT(o.order_id) mới đếm số đơn thực

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS actual_orders,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    COALESCE(
        SUM(o.net_amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS paid_amount_for_display
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả cần chú ý:

| Khách | `joined_rows` | `actual_orders` | `paid_orders` | `paid_amount_for_display` |
| --- | ---: | ---: | ---: | ---: |
| Nguyễn An | 3 | 3 | 1 | 120.000 |
| Trần Bình | 2 | 2 | 1 | 80.000 |
| Lê Chi | 2 | 2 | 2 | 300.000 |
| Phạm Dũng | 1 | **0** | **0** | 0 |

`order_id` là khóa chính `NOT NULL` trong bảng thật. Khi không có đơn ghép được, cột `o.order_id` của **hàng join bổ sung** là `NULL`, nên `COUNT(o.order_id) = 0`. Trong các kiểu `LEFT JOIN` khác, hãy chọn một cột chắc chắn **NOT NULL khi có bản ghi thật** làm dấu hiệu nhận diện.

Ở đây `COALESCE(SUM(...), 0)` chỉ phục vụ **mẫu hiển thị**. Nếu muốn phân biệt “chưa có đơn PAID” với “có đơn PAID nhưng tổng tiền bằng 0”, cần giữ thêm `paid_orders` và/hoặc `COUNT(o.net_amount)`.

### 13.3. WHERE ở bảng phải có thể làm mất hàng khách chưa có đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name;
~~~

`WHERE o.status = 'PAID'` loại hàng join của khách chưa có đơn vì `o.status` là `NULL`, điều kiện không TRUE. Vì vậy truy vấn **không còn liệt kê mọi khách hàng**.

Để giữ mọi khách và chỉ ghép đơn PAID, đặt điều kiện vào `ON`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Một cách khác là giữ mọi đơn trong `LEFT JOIN` rồi dùng `FILTER (WHERE o.status = 'PAID')` cho aggregate tương ứng.

### 13.4. JOIN một–nhiều có thể nhân số dòng

Nếu sau này join `orders` với `order_items`, một đơn có ba dòng hàng sẽ xuất hiện **ba lần** trong kết quả join:

~~~text
orders 101 --- item A
           --- item B
           --- item C
~~~

Khi đó:

~~~sql
-- Trong kết quả JOIN như vậy:
-- COUNT(*)                  có thể đếm 3 dòng
-- COUNT(DISTINCT o.order_id) có thể đếm 1 đơn
-- SUM(o.net_amount)         có thể cộng tiền đơn 3 lần (SAI)
~~~

Đừng sửa sai tổng tiền bằng `SUM(DISTINCT o.net_amount)`: hai đơn khác nhau có thể trùng số tiền. Cách đúng thường là **tổng hợp về đúng cấp trước khi JOIN**, hoặc tính riêng tổng theo cấp order rồi ghép các số liệu đã được group đúng.

## 14. COALESCE: thay NULL bằng 0 lúc nào?

`COALESCE(value, default)` lấy giá trị đầu tiên khác `NULL`. Nó thường được dùng quanh các aggregate:

~~~sql
SELECT
    SUM(net_amount) AS nullable_sum,
    COALESCE(SUM(net_amount), 0::numeric)
        AS sum_for_display
FROM agg_lab_151.orders
WHERE order_id < 0;
~~~

Trên tập không có hàng:

- `nullable_sum = NULL`.
- `sum_for_display = 0`.

Nhưng cần phân biệt hai vị trí đặt `COALESCE`.

### 14.1. COALESCE bên trong và bên ngoài SUM

~~~sql
SELECT
    SUM(COALESCE(net_amount, 0))
        AS sum_after_replacing_each_missing_value,
    COALESCE(SUM(net_amount), 0::numeric)
        AS default_after_aggregate
FROM agg_lab_151.orders;
~~~

Trên bộ dữ liệu có các giá trị hợp lệ, cả hai có thể cho cùng tổng **820.000**. Nhưng chúng **không hoàn toàn tương đương**:

- `SUM(COALESCE(x, 0))` biến từng giá trị thiếu thành 0 trước khi cộng.
- `COALESCE(SUM(x), 0)` để `SUM` bỏ qua giá trị thiếu và chỉ thay kết quả tổng hợp khi nó `NULL`.

Đặc biệt, trên **tập không có hàng**, `SUM(COALESCE(x,0))` vẫn trả `NULL`: không có dòng nào để tạo giá trị 0. `COALESCE(SUM(x),0)` mới chắc chắn trả 0 ở cấp kết quả tổng hợp.

### 14.2. COALESCE trong AVG làm đổi mẫu số

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(net_amount) AS known_orders,
    AVG(net_amount) AS avg_known_amount,
    AVG(COALESCE(net_amount, 0))
        AS avg_missing_as_zero
FROM agg_lab_151.orders;
~~~

Đây không chỉ là cách làm đẹp hiển thị: nó làm đổi **cách định nghĩa chỉ số**. Nếu `NULL` nghĩa là “đơn chưa ghi số tiền”, trung bình tính 0 có thể che lỗi ghi nhận hoặc đánh giá thấp giá trị đơn hàng.

### 14.3. Khi nào giữ NULL?

Nên giữ `NULL` khi:

- Không có quan sát nào để tính trung bình.
- Chưa biết phí hoặc số tiền và không được mặc định bằng 0.
- Không có mẫu số hợp lệ để tính tỷ lệ.
- Muốn phân biệt “không có dữ liệu” với “đã xác nhận bằng không”.

Thay bằng 0 có thể phù hợp khi:

- Quy tắc nghiệp vụ xác định **không có giao dịch = tổng bằng 0** cho mục tiêu báo cáo.
- Một cột optional thật sự có nghĩa “không phát sinh khoản phí” và đã có hợp đồng dữ liệu rõ.
- Giao diện quy định phải hiển thị 0 và người dùng vẫn có chỉ số `sample_count` để hiểu dữ liệu.

Nguyên tắc: **thay ở đúng cấp và đúng ngữ nghĩa, không mặc định coi mọi NULL là 0**.

## 15. NULL, phép tính và tổng hợp biểu thức

Không chỉ chính aggregate, **biểu thức đầu vào** của aggregate cũng ảnh hưởng kết quả.

### 15.1. SUM(net_amount + shipping_fee)

~~~sql
SELECT
    SUM(net_amount + shipping_fee)
        AS sum_when_both_fields_known,
    COUNT(net_amount + shipping_fee)
        AS rows_with_both_fields_known
FROM agg_lab_151.orders;
~~~

Vì `a + NULL` cho `NULL`, biểu thức `net_amount + shipping_fee` chỉ khác `NULL` khi cả hai thành phần có mặt. Những đơn đó là 101, 103, 105 và 107:

~~~text
101: 120000 + 15000 = 135000
103:  80000 +     0 =  80000
105:      0 + 10000 =  10000
107: 120000 +  5000 = 125000
--------------------------------
Tổng                   = 350000
~~~

Vì thế `SUM(net_amount + shipping_fee) = 350000` và `COUNT(net_amount + shipping_fee) = 4`.

Không được coi `350000` là tổng tiền của **mọi đơn**, vì những đơn có phí `NULL` đã bị loại khỏi phép cộng.

### 15.2. SUM(COALESCE(net_amount,0) + COALESCE(shipping_fee,0))

~~~sql
SELECT
    SUM(
        COALESCE(net_amount, 0)
        + COALESCE(shipping_fee, 0)
    ) AS estimated_total_with_missing_as_zero
FROM agg_lab_151.orders;
~~~

Tổng `net_amount` đã biết là **820.000**; phí vận chuyển đã biết gồm **15.000 + 0 + 10.000 + 5.000 = 30.000**. Nếu quy ước mọi giá trị thiếu là 0, tổng ước tính = **850.000**.

So với mục 15.1, khác biệt đến từ **quy tắc xử lý NULL**, không phải lỗi của `SUM`. Nếu phí vận chuyển chưa được xác định thì tổng ước tính chưa chắc là tổng thanh toán cuối cùng.

### 15.3. Dùng CASE/FILTER để chọn hàng được cộng

~~~sql
SELECT
    SUM(
        CASE
            WHEN status = 'PAID' THEN net_amount
            ELSE 0::numeric
        END
    ) AS paid_amount_by_case,
    SUM(net_amount) FILTER (WHERE status = 'PAID')
        AS paid_amount_by_filter
FROM agg_lab_151.orders;
~~~

Trên dataset, cả hai trả **620000**. Nhưng trên nhóm không có đơn PAID:

- `SUM(CASE WHEN ... THEN value ELSE 0 END)` có thể trả 0 **nếu nhóm vẫn có hàng không thỏa điều kiện**.
- `SUM(value) FILTER (WHERE ...)` trả `NULL` khi không có giá trị được chọn.

Muốn luôn hiển thị số 0 cho một KPI tổng sau khi tổng hợp, viết rõ:

~~~sql
COALESCE(
    SUM(net_amount) FILTER (WHERE status = 'PAID'),
    0::numeric
)
~~~

Không có một biến thể luôn “đúng hơn”; quan trọng là nêu rõ **chính sách cho tập rỗng và dữ liệu thiếu**.

## 16. COUNT, SUM, AVG và tỷ lệ phần trăm

Một tỷ lệ có dạng tổng quát:

\[
\text{Tỷ lệ (\%)} =
\frac{\text{Số đối tượng đạt điều kiện}}
{\text{Số đối tượng thuộc mẫu}} \times 100
\]

Phải xác định đúng **tử số** và **mẫu số**.

### 16.1. Tỷ lệ đơn PAID trong toàn bộ đơn

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percentage
FROM agg_lab_151.orders;
~~~

Kết quả: `5/8 × 100 = 62.50%`.

`NULLIF(COUNT(*), 0)` chuyển mẫu số 0 thành `NULL`. Trên bảng rỗng, tỷ lệ sẽ `NULL` thay vì lỗi chia cho 0.

### 16.2. Tỷ lệ đơn có giá trị tiền đã biết

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(net_amount) AS orders_with_amount,
    ROUND(
        100.0 * COUNT(net_amount)
        / NULLIF(COUNT(*), 0),
        2
    ) AS amount_completeness_percentage
FROM agg_lab_151.orders;
~~~

Với dữ liệu mẫu: `6/8 × 100 = 75.00%`.

Đây là chỉ số **đầy đủ dữ liệu**, không phải tỷ lệ thanh toán. Dùng cùng các hàm aggregate nhưng chọn sai biểu thức đếm sẽ tạo một KPI có nghĩa hoàn toàn khác.

### 16.3. Tỷ lệ đơn được đánh giá

~~~sql
SELECT
    COUNT(rating) AS rated_orders,
    COUNT(*) AS total_orders,
    ROUND(
        100.0 * COUNT(rating)
        / NULLIF(COUNT(*), 0),
        2
    ) AS rating_coverage_percentage,
    AVG(rating) AS average_rating
FROM agg_lab_151.orders;
~~~

Kết quả:

- Có **3/8 đơn** được đánh giá → **37.50%**.
- Điểm trung bình **4.0** trong số đơn **có đánh giá**.

Hai KPI nên được trình bày cùng nhau. Nếu chỉ nói “rating trung bình 4/5” mà không báo mẫu số 3 và độ phủ 37,5%, người xem có thể hiểu sai mức độ đại diện của kết quả.

### 16.4. COUNT(*) trả bigint: tránh chia số nguyên

Nếu chia các số nguyên theo toán tử chia số nguyên, phần thập phân có thể mất. Nên ép về kiểu thập phân rõ ràng:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID')::numeric
    / NULLIF(COUNT(*), 0)
    AS paid_ratio
FROM agg_lab_151.orders;
-- 0.625
~~~

Hoặc dùng `100.0` như mục 16.1 để tính phần trăm. Khi cần điều khiển số chữ số thập phân:

~~~sql
ROUND(numeric_expression, 2)
~~~

Trong PostgreSQL, hàm `round(value, scale)` với hai đối số thường áp dụng cho `numeric`; nếu biểu thức đang là kiểu floating point, có thể phải ép kiểu phù hợp.

## 17. Kiểu dữ liệu của kết quả tổng hợp

Đầu vào và kết quả của các hàm tổng hợp không nhất thiết cùng kiểu. Đây là vấn đề thực tế khi tạo view, API và dùng JDBC.

| Hàm và đầu vào | Kiểu kết quả PostgreSQL thường gặp |
| --- | --- |
| `COUNT(*)` hoặc `COUNT(expression)` | `bigint` |
| `SUM(smallint)` / `SUM(integer)` | `bigint` |
| `SUM(bigint)` | `numeric` |
| `SUM(numeric)` | `numeric` |
| `AVG(smallint/integer/bigint/numeric)` | `numeric` |
| `SUM(real)` | `real` |
| `SUM(double precision)` | `double precision` |
| `AVG(real/double precision)` | `double precision` |
| `MIN(x)` / `MAX(x)` | Thường cùng kiểu so sánh thích hợp với `x` |

Kiểu cụ thể còn phụ thuộc hàm aggregate và kiểu đầu vào được PostgreSQL hỗ trợ. Có thể kiểm tra trực tiếp:

~~~sql
SELECT
    pg_typeof(COUNT(*)) AS count_type,
    pg_typeof(SUM(1::integer)) AS sum_integer_type,
    pg_typeof(SUM(1::bigint)) AS sum_bigint_type,
    pg_typeof(AVG(1::integer)) AS avg_integer_type,
    pg_typeof(SUM(net_amount)) AS amount_sum_type
FROM agg_lab_151.orders;
~~~

### 17.1. AVG(integer) không chỉ là integer

~~~sql
SELECT
    AVG(x) AS average_value,
    pg_typeof(AVG(x)) AS result_type
FROM (
    VALUES (1::integer), (2::integer)
) AS v(x);
~~~

Trung bình là **1.5**, không phải 1. PostgreSQL trả kiểu `numeric` cho `AVG(integer)`, bảo toàn phần thập phân trong phép tính này.

### 17.2. NUMERIC và floating point

`NUMERIC` thường được chọn cho giá trị tiền cần chính xác theo thập phân. Các kiểu `real`/`double precision` dùng số chấm động nhị phân, có thể phát sinh sai số biểu diễn và sai khác nhỏ trong kết quả `SUM`/`AVG`, đặc biệt khi thứ tự cộng thay đổi.

~~~sql
SELECT
    SUM(x) AS decimal_sum
FROM (
    VALUES (0.1::numeric), (0.2::numeric)
) AS v(x);
-- 0.3
~~~

Đối với tiền, không nên chuyển sang `double precision` chỉ để phép tính nhanh hơn nếu nghiệp vụ yêu cầu đúng từng đơn vị tiền. Ngược lại, dữ liệu đo khoa học có thể phù hợp với floating point; phải hiểu lựa chọn kiểu.

### 17.3. Tránh ép kiểu kết quả về phạm vi nhỏ

`COUNT(*)` trả `bigint` vì số hàng có thể rất lớn. `SUM(integer)` trả `bigint` để giảm nguy cơ tràn so với cộng giữ nguyên integer. Nhưng mọi kiểu số vẫn có phạm vi/giới hạn; nếu ép tổng lớn về `integer`, phép cast có thể lỗi hoặc làm mất yêu cầu ứng dụng.

Ở Java/JDBC, kiểu nhận kết quả nên phù hợp với schema và aggregate: ví dụ `getLong` cho count, `BigDecimal` cho giá trị `NUMERIC`. Nếu cần phân biệt `NULL` ở kết quả, không dùng cách đọc primitive rồi bỏ qua trạng thái `wasNull()`.

## 18. NULL trong điều kiện và logic ba giá trị

`NULL` không phải 0 hoặc chuỗi rỗng. Phép so sánh thông thường với `NULL` cho trạng thái **UNKNOWN**:

~~~sql
SELECT
    NULL::numeric = 0 AS null_equals_zero,
    NULL::numeric = NULL::numeric AS null_equals_null,
    NULL::numeric IS NULL AS is_null_result;
~~~

Hai cột đầu là `NULL`/UNKNOWN, cột thứ ba là `TRUE`.

Muốn chọn các đơn thiếu tiền:

~~~sql
SELECT order_id
FROM agg_lab_151.orders
WHERE net_amount IS NULL
ORDER BY order_id;
-- 102, 108
~~~

Không dùng:

~~~sql
-- Sai mục đích:
-- WHERE net_amount = NULL
~~~

### 18.1. Đếm số 0 và số NULL là hai phép kiểm tra khác nhau

~~~sql
SELECT
    COUNT(*) FILTER (WHERE net_amount = 0)
        AS known_zero_amounts,
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS unknown_amounts
FROM agg_lab_151.orders;
-- 1, 2
~~~

Điều này cần thiết cho kiểm tra chất lượng dữ liệu: **đơn miễn phí** và **đơn chưa biết số tiền** không nên bị gộp thành cùng một trạng thái nghiệp vụ.

### 18.2. GROUP BY và NULL

Trong `GROUP BY`, các hàng có cùng giá trị nhóm `NULL` được gom chung thành **một nhóm**. Nhưng `COUNT(customer_id)` trên nhóm đó bằng 0, bởi bản thân các giá trị của cột đang đếm đều `NULL`:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS rows_in_group,
    COUNT(customer_id) AS non_null_customer_ids
FROM agg_lab_151.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

Nhóm guest có `rows_in_group = 1` và `non_null_customer_ids = 0`. Đó là hai câu hỏi khác nhau, không phải bug của PostgreSQL.

## 19. Tổng hợp theo ngày và tạo ngày không có đơn

Một báo cáo có thể cần **mọi ngày trong kỳ**, kể cả ngày chưa phát sinh đơn. Nếu chỉ `GROUP BY order_date` từ bảng đơn, ngày không có đơn **không xuất hiện**.

### 19.1. Tổng hợp ngày có đơn

~~~sql
SELECT
    order_date,
    COUNT(*) AS order_count,
    COALESCE(
        SUM(net_amount) FILTER (WHERE status = 'PAID'),
        0::numeric
    ) AS paid_amount
FROM agg_lab_151.orders
GROUP BY order_date
ORDER BY order_date;
~~~

Kết quả chỉ có những ngày `2026-11-01` đến `2026-11-05` có đơn trong dữ liệu.

### 19.2. Dùng generate_series cho toàn bộ ngày trong kỳ

~~~sql
WITH calendar AS (
    SELECT day_point::date AS report_date
    FROM generate_series(
        TIMESTAMP '2026-11-01 00:00:00',
        TIMESTAMP '2026-11-07 00:00:00',
        INTERVAL '1 day'
    ) AS g(day_point)
)
SELECT
    c.report_date,
    COUNT(o.order_id) AS order_count,
    COALESCE(
        SUM(o.net_amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS paid_amount
FROM calendar AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.order_date = c.report_date
GROUP BY c.report_date
ORDER BY c.report_date;
~~~

Ngày 06/11 và 07/11 không có đơn nhưng vẫn xuất hiện với `order_count = 0`. Sử dụng `COUNT(o.order_id)` thay vì `COUNT(*)` bởi mỗi ngày không có đơn vẫn có một hàng do `LEFT JOIN` bảo toàn ngày lịch.

Lưu ý: `generate_series` ở đây tạo **ngày dạng calendar** từ timestamp không có timezone. Nếu báo cáo theo ngày địa phương của sự kiện `TIMESTAMPTZ` ở nhiều vùng, cần xác định múi giờ và ranh giới ngày phù hợp trước khi nhóm.

## 20. Aggregate dạng window: tổng hợp mà vẫn giữ từng dòng

`GROUP BY` thu gọn nhiều hàng thành một hàng cho mỗi nhóm. **Window functions** có thể tính tổng hợp theo nhóm mà **vẫn giữ các dòng chi tiết**:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    net_amount,
    COUNT(*) OVER (
        PARTITION BY customer_id
    ) AS orders_of_customer_group,
    SUM(net_amount) OVER (
        PARTITION BY customer_id
    ) AS known_amount_sum_of_group
FROM agg_lab_151.orders
ORDER BY customer_id NULLS LAST, order_id;
~~~

Ví dụ đơn 101, 102, 108 đều có `customer_id=1` nên đều hiển thị `orders_of_customer_group=3`, và tổng tiền đã biết trong nhóm là 120.000.

Đây là phép dùng aggregate với `OVER (...)`, không giống một query `GROUP BY` thông thường. Với nhóm không có giá trị tiền hợp lệ, `SUM` trong window cũng có thể trả `NULL`.

### 20.1. AVG OVER và ý nghĩa mẫu số

~~~sql
SELECT
    order_id,
    status,
    net_amount,
    AVG(net_amount) OVER (
        PARTITION BY status
    ) AS average_amount_for_status
FROM agg_lab_151.orders
ORDER BY status, order_id;
~~~

Hai đơn `NEW` vẫn xuất hiện, nhưng `average_amount_for_status` là `NULL` vì **cả hai net_amount đều NULL**. Các đơn `PAID` đều có giá trị trung bình nhóm là 124.000.

Window functions là chủ đề sâu hơn; bài này dùng chúng để nhấn mạnh rằng **quy tắc NULL của aggregate không thay đổi chỉ vì có OVER**.

## 21. Những giới hạn hiệu năng khi tổng hợp

### 21.1. COUNT(*) không luôn là thao tác tức thì

PostgreSQL dùng MVCC (*multi-version concurrency control*). Số hàng **đang nhìn thấy được** có thể phụ thuộc snapshot của transaction, nên PostgreSQL không thể luôn lấy một con số tổng hàng chính xác bất biến từ metadata mà không kiểm tra khả năng nhìn thấy.

~~~sql
SELECT COUNT(*) FROM agg_lab_151.orders;
~~~

Trên bảng rất lớn, truy vấn có thể cần quét lượng dữ liệu đáng kể. PostgreSQL có thể chọn sequential scan, index-only scan trong điều kiện phù hợp, hoặc kế hoạch song song tùy workload/cấu hình. **Không có đảm bảo `COUNT(*)` luôn O(1)** hoặc luôn nhanh hơn các truy vấn khác chỉ vì không cần trả cột.

### 21.2. Ước tính số hàng khác COUNT(*) chính xác

~~~sql
SELECT
    relname,
    reltuples AS estimated_rows
FROM pg_catalog.pg_class
WHERE oid = 'agg_lab_151.orders'::regclass;
~~~

`reltuples` là **ước tính thống kê** dùng trong hoạt động của PostgreSQL và có thể cũ, nhất là trên bảng mới hoặc sau nhiều thay đổi. Nó không thay thế `COUNT(*)` trong nghiệp vụ cần con số chính xác.

### 21.3. WHERE có thể giúp giảm lượng dữ liệu

~~~sql
SELECT SUM(net_amount)
FROM agg_lab_151.orders
WHERE status = 'PAID';
~~~

Trên bảng lớn, index phù hợp với các bộ lọc/điều kiện nhóm có thể giúp giảm lượng dữ liệu phải xét. Nhưng lập index không tự đảm bảo truy vấn aggregate nhanh; còn phụ thuộc độ chọn lọc, số trang phải đọc, data visibility, parallelism và plan.

Thường cần đo bằng:

~~~sql
EXPLAIN
SELECT
    status,
    COUNT(*),
    SUM(net_amount)
FROM agg_lab_151.orders
GROUP BY status;
~~~

`EXPLAIN` không có `ANALYZE` chỉ lập kế hoạch, không thực thi query để đo actual timing; `EXPLAIN (ANALYZE, BUFFERS)` sẽ chạy truy vấn thật, nên chỉ dùng khi hiểu chi phí và môi trường phù hợp.

### 21.4. GROUP BY, DISTINCT và bộ nhớ

Tùy kế hoạch, PostgreSQL có thể dùng các thao tác như **HashAggregate**, **GroupAggregate** và các bước sort/hash. `COUNT(DISTINCT ...)` có thể phải xử lý thêm tập giá trị duy nhất, tạo chi phí đáng kể khi số lượng giá trị lớn.

Không nên đưa `DISTINCT` vào `SUM` hoặc `AVG` vì tưởng đó là tối ưu hoặc loại duplicate chung. `DISTINCT` **thay đổi ngữ nghĩa** và có thể làm truy vấn tốn tài nguyên hơn.

### 21.5. Tổng hợp trước JOIN khi khác cấp chi tiết

Nếu một bảng mỗi dòng là một **đơn** và bảng kia mỗi dòng là một **mặt hàng trong đơn**, JOIN có thể nhân bản cột số tiền của đơn. Trước khi tính:

~~~sql
SUM(order_amount)
~~~

hãy xác định một dòng trong đầu vào tương ứng **đơn, mặt hàng, giao dịch thanh toán hay khách hàng**. Cấp dữ liệu (*grain*) phải thống nhất với cấp của số liệu cần tổng hợp.

## 22. Những sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `COUNT(net_amount)` để đếm mọi đơn | Bỏ các đơn có tiền NULL | Dùng `COUNT(*)` khi muốn đếm hàng |
| Dùng `COUNT(*)` sau `LEFT JOIN` để đếm bản ghi bên phải | Đếm 1 ngay cả khi không có bản ghi ghép | Dùng `COUNT(o.order_id)` với khóa không NULL |
| Coi `NULL` là 0 | Làm sai báo cáo tiền/chất lượng dữ liệu | Phân biệt thiếu giá trị và giá trị 0 đã biết |
| Cho rằng `SUM` trên tập rỗng trả 0 | API/dashboard nhận NULL không mong đợi | Dùng `COALESCE(SUM(...),0)` khi quy ước cho phép |
| Dùng `AVG(COALESCE(x,0))` mà không cân nhắc | Thay mẫu số, làm lệch trung bình | Dùng `AVG(x)` nếu chỉ tính giá trị quan sát được |
| Chỉ báo `AVG(rating)` mà không báo `COUNT(rating)` | Không biết cỡ mẫu | Trả kèm số mẫu và tỷ lệ phủ |
| Lấy `SUM` của mọi trạng thái làm doanh thu | Cộng cả đơn hủy/chưa thanh toán | Lọc theo quy tắc ghi nhận rõ |
| Dùng `SUM(DISTINCT amount)` để “khử đơn trùng” | Bỏ các đơn khác nhau có cùng tiền | Khử trùng theo khóa đơn, sửa JOIN |
| Viết `COUNT(CASE WHEN cond THEN 1 ELSE 0 END)` | Đếm cả hàng có ELSE 0 | `COUNT(*) FILTER` hoặc `SUM(CASE... ELSE 0 END)` |
| Dùng `WHERE aggregate(...)` | Sai giai đoạn tính | Dùng `HAVING` |
| Đặt điều kiện bảng phải trong `WHERE` của LEFT JOIN | Loại hàng không ghép được | Đưa điều kiện vào `ON` hoặc `FILTER` |
| Dùng `= NULL` trong WHERE | Điều kiện không TRUE | Dùng `IS NULL` |
| `COUNT(DISTINCT customer_id)` để đếm mọi khách | Bỏ khách chưa có đơn, bỏ NULL | Đếm ở bảng khách nếu cần toàn bộ |
| Đếm giá trị `NULL` bằng `COUNT(column)` | Kết quả là số khác NULL | Dùng `COUNT(*) FILTER (WHERE column IS NULL)` |
| Lấy MIN/MAX rồi chọn thêm cột bất kỳ | Không xác định bản ghi có min/max | Truy vấn phụ/ORDER BY và xử lý ties |
| Chia số nguyên để ra tỷ lệ | Có thể mất phần thập phân | Dùng `100.0` hoặc cast sang `numeric` |
| Tin `COUNT(*)` luôn nhanh như đọc metadata | Chậm trên bảng lớn | Kiểm tra plan, mục tiêu chính xác/ước tính |
| Không xét số dòng do JOIN tạo ra | SUM bị nhân nhiều lần | Tổng hợp đúng grain rồi JOIN |
| Không phân biệt kết quả một hàng COUNT=0 với GROUP BY không hàng | Giao diện/logic nhận sai trạng thái | Thiết kế hợp đồng kết quả rõ ràng |

## 23. Bài tập thực hành

### Bài 1 — COUNT(*) so với COUNT(cột)

Truy vấn đồng thời:

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(customer_id) AS known_customers_in_orders,
    COUNT(net_amount) AS known_amount_rows,
    COUNT(shipping_fee) AS known_shipping_rows,
    COUNT(rating) AS rated_rows
FROM agg_lab_151.orders;
~~~

**Đáp án:** `8, 7, 6, 4, 3`.

Giải thích vì sao `COUNT(net_amount)` tính cả đơn có tiền bằng 0 nhưng không tính các đơn có tiền `NULL`.

### Bài 2 — SUM và AVG

Tính `SUM(net_amount)` và `AVG(net_amount)` trên mọi đơn. Sau đó tính riêng với `status='PAID'`.

**Đáp án gợi ý:**

- Mọi đơn: tổng `820000`; trung bình khoảng `136666.67` trên sáu giá trị.
- Đơn PAID: tổng `620000`; trung bình `124000` trên năm đơn.

Tại sao không gọi `820000` là doanh thu đã thanh toán?

### Bài 3 — MIN/MAX và dòng có giá trị cực trị

Tìm `MIN(net_amount)`, `MAX(net_amount)`, sau đó viết truy vấn để hiển thị **tất cả đơn** bằng giá trị `MAX(net_amount)`.

**Đáp án:** min `0`, max `300000`, đơn đạt max là `106` trong dataset.

### Bài 4 — Tập không có hàng

Chạy:

~~~sql
SELECT
    COUNT(*), SUM(net_amount), AVG(net_amount),
    MIN(net_amount), MAX(net_amount)
FROM agg_lab_151.orders
WHERE order_date < DATE '2000-01-01';
~~~

**Câu hỏi:** có bao nhiêu hàng kết quả? `COUNT(*)` trả gì? Các aggregate còn lại trả gì?

**Đáp án:** một hàng; COUNT = 0; SUM/AVG/MIN/MAX = `NULL`.

### Bài 5 — Có hàng nhưng mọi amount là NULL

Chỉ lọc đơn `NEW`, tính `COUNT(*)`, `COUNT(net_amount)` và `SUM(net_amount)`.

**Đáp án:** `2`, `0`, `NULL`. Giải thích vì sao khác với không có đơn trong mục 8.1.

### Bài 6 — COUNT(DISTINCT)

Tìm:

~~~sql
SELECT
    COUNT(customer_id) AS with_customer,
    COUNT(DISTINCT customer_id) AS unique_customers,
    COUNT(DISTINCT net_amount) AS unique_amount_values
FROM agg_lab_151.orders;
~~~

**Đáp án:** `7, 3, 5`. Khách chưa có đơn có được tính không? Hai đơn cùng số tiền có được coi là một đơn không?

### Bài 7 — Vì sao SUM(DISTINCT amount) sai cho doanh thu?

So sánh `SUM(net_amount)` và `SUM(DISTINCT net_amount)`. Giải thích khoản tiền **120000** đã xuất hiện hai lần ở hai đơn khác nhau nên phải được cộng hai lần nếu nghiệp vụ đang tính tổng đơn.

**Đáp án:** `820000` so với `700000`; chênh lệch `120000`.

### Bài 8 — GROUP BY theo trạng thái

Viết báo cáo:

~~~text
status | total_orders | known_amounts | amount_sum | amount_avg
~~~

Từ bảng `orders`. Với `NEW`, `total_orders` phải là 2, `known_amounts` bằng 0, `amount_sum` và `amount_avg` đều `NULL`.

### Bài 9 — HAVING sau GROUP BY

Liệt kê những `customer_id` có ít nhất hai đơn. Truy vấn phải dùng `GROUP BY` và `HAVING COUNT(*) >= 2`.

**Đáp án:** nhóm khách `1`, `2` và `3`.

### Bài 10 — COUNT sau LEFT JOIN

Liệt kê **mọi khách**, kể cả khách `4` chưa có đơn, cùng `COUNT(*)` và `COUNT(o.order_id)`. Giải thích vì sao ở khách 4 hai giá trị lần lượt là `1` và `0`.

### Bài 11 — FILTER và chỉ số chất lượng dữ liệu

Viết một `SELECT` duy nhất trả:

~~~text
all_orders
paid_orders
new_orders
cancelled_orders
amount_missing
zero_amount_orders
paid_amount
average_paid_amount
~~~

Sử dụng `FILTER (WHERE ...)` cho các chỉ số có điều kiện. **Đáp án:** `8`, `5`, `2`, `1`, `2`, `1`, `620000`, `124000`.

### Bài 12 — Tỷ lệ và mẫu số

Tính:

- Tỷ lệ đơn PAID trên mọi đơn.
- Tỷ lệ đơn có `net_amount` đã biết.
- Tỷ lệ đơn có `rating`.

**Đáp án:** `62.50%`, `75.00%`, `37.50%`.

Vì sao cả ba đều có mẫu số 8 nhưng tử số khác nhau? Nếu bảng trống, nên trả `NULL` hay 0 cho các tỷ lệ?

### Bài 13 — AVG với dữ liệu thiếu

So sánh:

~~~sql
SELECT
    AVG(net_amount) AS average_known,
    AVG(COALESCE(net_amount, 0)) AS missing_as_zero,
    COUNT(net_amount) AS known_count,
    COUNT(*) AS total_count
FROM agg_lab_151.orders;
~~~

**Đáp án:** khoảng `136666.67`, `102500`, `6` và `8`. Nêu quy tắc nghiệp vụ nào khiến mỗi cách tính hợp lý.

### Bài 14 — COUNT(CASE ...) sai

Xét:

~~~sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS incorrect_paid_count,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END)
        AS correct_paid_count,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS filter_paid_count
FROM agg_lab_151.orders;
~~~

**Đáp án:** `8`, `5`, `5`. Tại sao `COUNT` đếm cả số 0?

### Bài 15 — Báo cáo có ngày không phát sinh đơn

Dùng `generate_series` tạo danh sách ngày 01–07/11/2026, `LEFT JOIN` bảng đơn và tính số đơn mỗi ngày. Hai ngày cuối cần hiện `0`, **không biến mất** khỏi báo cáo.

### Bài 16 — Tránh nhân doanh thu sau JOIN

Giả sử một đơn 120.000 có ba dòng hàng, JOIN bảng đơn với chi tiết hàng sẽ cho ba dòng. Nếu dùng `SUM(order_amount)` sau JOIN sẽ ra bao nhiêu? Vì sao `SUM(DISTINCT order_amount)` không phải lời giải tổng quát? Hãy mô tả cách tổng hợp đúng cấp trước khi JOIN.

### Bài 17 — Trả dữ liệu cho ứng dụng Java

Một API muốn trả:

~~~text
total_orders: integer
total_paid_amount: decimal | null
avg_rating: decimal | null
rated_orders: integer
~~~

Hãy quyết định kiểu nhận JDBC phù hợp từ `COUNT` và `NUMERIC`, cách biểu diễn `NULL` và có nên luôn thay avg rating bằng 0 không. Giải thích vì sao “chưa có rating” khác “điểm rating bằng 0”.

## 24. Mẫu truy vấn tổng hợp hoàn chỉnh cho dashboard

Một dashboard đơn giản thường cần cả **số lượng**, **tổng tiền**, **trung bình**, **độ phủ dữ liệu** và **giá trị cực trị**. Có thể trả nhiều KPI cùng một câu:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'NEW')
        AS new_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELLED')
        AS cancelled_orders,
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS missing_amount_orders,
    COUNT(*) FILTER (WHERE net_amount = 0)
        AS zero_amount_orders,
    COUNT(net_amount) AS known_amount_orders,
    SUM(net_amount) AS all_known_amount_sum,
    COALESCE(
        SUM(net_amount) FILTER (WHERE status = 'PAID'),
        0::numeric
    ) AS paid_amount_for_display,
    AVG(net_amount) FILTER (WHERE status = 'PAID')
        AS average_paid_amount,
    MIN(net_amount) AS minimum_known_amount,
    MAX(net_amount) AS maximum_known_amount,
    COUNT(rating) AS rated_orders,
    AVG(rating) AS average_rating,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percentage
FROM agg_lab_151.orders;
~~~

Kết quả từ seed là:

| KPI | Giá trị |
| --- | ---: |
| Tổng số đơn | 8 |
| Đơn PAID | 5 |
| Đơn NEW | 2 |
| Đơn CANCELLED | 1 |
| Đơn thiếu số tiền | 2 |
| Đơn có số tiền bằng 0 | 1 |
| Đơn đã biết số tiền | 6 |
| Tổng số tiền đã biết của mọi trạng thái | 820.000 |
| Tổng số tiền của đơn PAID | 620.000 |
| Trung bình tiền đơn PAID | 124.000 |
| Tiền nhỏ nhất đã biết | 0 |
| Tiền lớn nhất đã biết | 300.000 |
| Số đơn đã đánh giá | 3 |
| Điểm trung bình từ các đơn có đánh giá | 4 |
| Tỷ lệ đơn PAID | 62,50% |

**Báo cáo thực tế nên kèm định nghĩa KPI.** Cụ thể, “tổng tiền PAID” là tổng `net_amount` của những hàng có `status = 'PAID'`, chưa xử lý những khái niệm kế toán khác; “trung bình tiền đơn PAID” chỉ chia trên các hàng PAID có tiền khác NULL; “trung bình rating” chỉ lấy các đơn có đánh giá.

### 24.1. Vì sao nên trả đồng thời COUNT và AVG?

Một chỉ số trung bình đơn lẻ có thể bị hiểu quá mức. Ví dụ:

~~~text
average_rating = 4.0
rated_orders   = 3
total_orders   = 8
~~~

Ba thông tin kết hợp cho biết điểm trung bình khá cao, nhưng mới có ba đơn được đánh giá. Độ bao phủ nhỏ chưa phản ánh chắc chắn trải nghiệm của tất cả người mua. Vì vậy các KPI **giá trị** và **độ đầy đủ/mẫu số** nên đi cùng nhau.

## 25. Tài liệu tham khảo PostgreSQL

Để đối chiếu hành vi theo major version PostgreSQL đang dùng:

- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html): `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, kiểu kết quả và xử lý tập rỗng.
- [Aggregate Expressions](https://www.postgresql.org/docs/current/sql-expressions.html#SYNTAX-AGGREGATES): `DISTINCT`, `FILTER` và cách dùng biểu thức tổng hợp.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `WHERE`, `GROUP BY`, `HAVING` và thứ tự xử lý khái niệm.
- [Conditional Expressions](https://www.postgresql.org/docs/current/functions-conditional.html): `CASE`, `COALESCE`, `NULLIF`.
- [Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): so sánh và kiểm tra `NULL`.
- [Window Functions](https://www.postgresql.org/docs/current/functions-window.html): aggregate dùng với `OVER` và `PARTITION BY`.

Đường dẫn `/docs/current/` là tài liệu cho phiên bản ổn định hiện hành. Nếu đang sử dụng PostgreSQL 14, 15, 16 hoặc một phiên bản cụ thể khác, hãy đọc đúng bộ tài liệu của phiên bản đó.

## 26. Tổng kết

Năm hàm `COUNT`, `SUM`, `AVG`, `MIN` và `MAX` là nền tảng của truy vấn tổng hợp trong PostgreSQL. **`COUNT(*)` đếm hàng**, trong khi **`COUNT(expression)` đếm các giá trị khác `NULL`**. `SUM`, `AVG`, `MIN` và `MAX` bỏ qua giá trị `NULL`; khi không có giá trị phù hợp, chúng thường trả `NULL`, **không tự đổi thành 0**. Với `AVG`, mẫu số là số giá trị không NULL, vì vậy thay `NULL` bằng 0 trước khi tính có thể làm đổi ý nghĩa thống kê.

`GROUP BY` tạo kết quả cho từng nhóm; `WHERE` lọc hàng trước khi tổng hợp; `HAVING` lọc nhóm sau khi tổng hợp; `FILTER` giúp tính nhiều KPI có điều kiện cùng lúc. `DISTINCT` chỉ loại **giá trị trùng**, không phải loại giao dịch trùng nghiệp vụ. Với `LEFT JOIN`, dùng `COUNT(khóa_không_NULL_của_bảng_phải)` khi mục tiêu là đếm bản ghi bên phải thật sự được ghép, tránh đếm một hàng do LEFT JOIN tạo ra.

Khi áp dụng vào báo cáo, hãy luôn xác định **cấp dữ liệu đầu vào, phạm vi hàng được chọn, ý nghĩa của `NULL`, mẫu số thống kê và chính sách hiển thị kết quả rỗng**. Những quyết định đó quan trọng không kém cú pháp SQL: chúng giúp truy vấn trả ra **con số đúng với câu hỏi nghiệp vụ**, thay vì một con số có vẻ hợp lý nhưng sai nghĩa.

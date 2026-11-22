# Thiết lập bộ dữ liệu, tải mẫu và đường cơ sở có thể tái lập

Một lần đo hiệu năng chỉ có giá trị so sánh khi điều kiện thử nghiệm được kiểm soát. Nếu lần chạy thứ nhất dùng 100.000 khách hàng, lần thứ hai dùng 2 triệu khách hàng; nếu lần đầu cache đã nóng nhưng lần sau cache lạnh; hoặc tỷ lệ checkout thay đổi giữa hai lần, chênh lệch latency không thể quy hoàn toàn cho một thay đổi về SQL hay index.

Thiết lập một đường cơ sở (baseline) có thể tái lập gồm ba phần liên kết với nhau: bộ dữ liệu đại diện, tải mẫu phản ánh giao dịch nghiệp vụ và quy trình đo có thể chạy lại với cùng điều kiện. Bộ dữ liệu phải giữ được quy mô, phân bố, quan hệ và độ lệch gần thực tế. Tải mẫu phải giữ được tỷ trọng giao dịch, read/write mix, concurrency và cách request đến. Baseline phải ghi lại cấu hình, phiên bản, thống kê, execution plan, số đo và trạng thái dữ liệu để lần sau có thể đối chiếu công bằng.

Bài học thuộc chương **Thực hành tổng hợp** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, bài thực hành này kết nối việc tạo dữ liệu với thiết kế workload, thu thập execution plan, đo CPU, memory, I/O, lock và xác nhận tác động sau mỗi lần tối ưu.

## 1. Đường cơ sở có thể tái lập là gì?

Baseline là bộ số đo được thu thập trong một cấu hình và workload đã xác định, dùng làm mốc để đánh giá thay đổi sau này. Baseline không chỉ là một con số throughput hoặc thời gian chạy truy vấn. Nó phải mô tả đủ điều kiện để một người khác có thể tái tạo phép đo.

Một baseline hữu ích cần cố định hoặc ghi nhận:

- Phiên bản database engine, driver và ứng dụng tạo tải.
- Schema, constraint, index, partition và cấu hình database.
- Quy mô dữ liệu, phân bố khóa, dữ liệu lệch và thời điểm dữ liệu.
- Statistics của optimizer và trạng thái bảo trì liên quan.
- Transaction mix, tỷ lệ đọc/ghi, tham số truy vấn và tốc độ tải.
- Số user, concurrency, think time hoặc arrival rate.
- Kích thước connection pool, số worker và giới hạn của load generator.
- CPU, RAM, storage, network, filesystem và cấu hình máy chạy database.
- Trạng thái cache, thời gian warm-up, thời gian đo và số lần lặp.
- Throughput hoàn tất, latency theo percentile, lỗi, retry và rollback.
- CPU, memory, I/O, temp usage, lock wait, log flush và connection wait.
- Execution plan hoặc query identifier của các truy vấn quan trọng.

Khi một trong các yếu tố này thay đổi, kết quả có thể thay đổi dù mã SQL không đổi. Vì vậy, mỗi lần chạy cần có mã định danh và manifest ghi lại điều kiện.

### 1.1. Baseline, target và regression

| Khái niệm | Ý nghĩa |
| --- | --- |
| Baseline | Kết quả đo ở cấu hình được chọn làm mốc |
| Target | Mục tiêu cần đạt, ví dụ p95 dưới SLA ở một throughput xác định |
| Candidate | Cấu hình hoặc thay đổi đang được đánh giá |
| Regression | Kết quả xấu đi so với baseline ngoài biên độ biến động chấp nhận được |
| Improvement | Kết quả tốt hơn mà vẫn đáp ứng tính đúng đắn và các mục tiêu khác |

Baseline có thể được cập nhật khi phần cứng, dữ liệu hoặc workload mục tiêu thay đổi có chủ đích. Khi cập nhật, giữ lại baseline cũ và ghi rõ lý do, phiên bản cùng các điều kiện khác biệt.

## 2. Xác định mục tiêu và phạm vi bài thực hành

Trước khi tạo dữ liệu, cần trả lời:

1. Cần đánh giá database, ứng dụng hay toàn bộ hệ thống?
2. Giao dịch nào ảnh hưởng trực tiếp đến SLA?
3. Tải bình thường và tải cao điểm là bao nhiêu?
4. Dữ liệu hiện tại và dữ liệu dự kiến sau tăng trưởng có quy mô thế nào?
5. Workload thiên về đọc, ghi, phân tích hay hỗn hợp?
6. Cần kiểm tra latency, throughput, concurrency, capacity hay khả năng ổn định lâu dài?
7. Thay đổi nào sẽ được so sánh với baseline?

Ví dụ mục tiêu capstone:

- Kiểm tra workload OLTP hỗn hợp của một cửa hàng trực tuyến.
- Tạo dữ liệu khách hàng, sản phẩm, tồn kho, đơn hàng và dòng đơn hàng.
- Dùng phân bố dữ liệu có nhóm khách hàng và sản phẩm phổ biến.
- Phát sinh tìm kiếm, xem chi tiết, xem lịch sử đơn, checkout và báo cáo.
- Giữ tải mẫu ở 100 giao dịch nghiệp vụ mỗi giây trong giai đoạn đo.
- Thu thập p50/p95/p99, throughput, lỗi, CPU, memory, I/O, temp và lock wait.
- Lặp lại phép đo sau khi thay đổi một yếu tố như index hoặc câu SQL.

Đây là quy mô ví dụ để hướng dẫn cách tổ chức. Khi thực hiện, điều chỉnh kích thước dữ liệu và tải theo năng lực môi trường thử nghiệm.

## 3. Thiết kế bộ dữ liệu đại diện

Bộ dữ liệu benchmark cần đại diện cho cả quy mô lẫn hình dạng dữ liệu. Chỉ tạo đúng số hàng tổng thể là chưa đủ. Hai bảng có cùng một triệu hàng nhưng khác cardinality, row width, tỷ lệ NULL và phân bố giá trị có thể tạo execution plan rất khác nhau.

### 3.1. Quy mô và scale factor

Xác định quy mô bằng các đại lượng:

- Số hàng mỗi bảng.
- Tổng dung lượng data và index.
- Số giá trị phân biệt của các cột lọc và join key.
- Số partition hoặc shard.
- Số hàng trung bình và lớn nhất trong mỗi nhóm.
- Working set được truy cập thường xuyên so với RAM.
- Tốc độ tăng dữ liệu trong thời gian kiểm thử.

Có thể định nghĩa các mức dữ liệu:

| Mức | Mục tiêu | Ví dụ quy mô |
| --- | --- | --- |
| Smoke | Xác nhận script và luồng nghiệp vụ | 1% dữ liệu mục tiêu |
| Development | Lặp nhanh khi sửa SQL | 5–10% |
| Baseline | Đánh giá plan và tài nguyên | Gần quy mô kiểm thử đã thống nhất |
| Capacity | Đánh giá tăng trưởng và giới hạn | 1,5–2 lần quy mô baseline hoặc theo dự báo |

Các tỷ lệ chỉ là cách tổ chức ví dụ. Quan trọng là lưu rõ scale factor và không so sánh hai lần chạy có quy mô dữ liệu khác nhau mà không hiệu chỉnh.

### 3.2. Cardinality và phân bố

Với mỗi cột quan trọng, ghi nhận:

- Số giá trị phân biệt.
- Giá trị phổ biến nhất và tỷ trọng của nó.
- Histogram hoặc các phân vị tần suất.
- Tỷ lệ NULL và giá trị mặc định.
- Tương quan giữa các cột.
- Phân bố theo thời gian.

Không nên tạo dữ liệu hoàn toàn đồng đều nếu production có long-tail. Ví dụ, một nhóm khách hàng doanh nghiệp có thể tạo nhiều đơn hơn hàng nghìn khách hàng thông thường cộng lại. Một số sản phẩm bán chạy có thể chiếm phần lớn lượt xem và cập nhật tồn kho.

### 3.3. Quan hệ và tính nhất quán

Dataset phải giữ đúng quan hệ khóa ngoại và quy tắc nghiệp vụ:

- Mỗi order thuộc một customer hợp lệ.
- Mỗi order item tham chiếu một order và product có thật.
- Số lượng và giá không âm.
- Tổng tiền đơn hàng khớp với các dòng chi tiết theo quy tắc làm tròn.
- Tồn kho không âm nếu nghiệp vụ không cho phép bán vượt tồn.
- Trạng thái đơn hàng tuân theo các chuyển đổi hợp lệ.

Nếu dữ liệu seed sai, workload có thể thất bại do constraint hoặc logic nghiệp vụ thay vì hiệu năng database.

### 3.4. Working set và dữ liệu nóng/lạnh

Working set là tập dữ liệu được truy cập lặp lại trong khoảng thời gian quan sát. Cần mô phỏng:

- Dữ liệu nóng: khách hàng, sản phẩm hoặc đơn hàng được truy cập thường xuyên.
- Dữ liệu trung bình: phần lớn dữ liệu có tần suất vừa phải.
- Dữ liệu lạnh: lịch sử cũ, ít được truy cập.
- Dữ liệu mới: các bản ghi được tạo hoặc cập nhật liên tục.

Nếu toàn bộ dataset nhỏ hơn buffer cache, benchmark có thể chủ yếu đo CPU và cache hit. Nếu dataset lớn hơn RAM, physical I/O và storage latency có thể chi phối. Cần ghi rõ mục tiêu là warm-cache hay cold-cache test.

## 4. Dùng dữ liệu tổng hợp có thể tái lập

Dữ liệu tổng hợp giúp tạo quy mô lớn mà không đưa dữ liệu cá nhân thật vào môi trường thử nghiệm. Để tái lập, generator cần tạo cùng một đầu vào và cùng một phiên bản script ra cùng một dataset.

### 4.1. Quy tắc tạo dữ liệu

- Dùng ID có quy luật và phạm vi được dành riêng cho dữ liệu seed.
- Dùng công thức xác định từ ID để tạo category, status và ngày tháng.
- Nếu cần random, ghi seed và bảo đảm generator dùng seed theo cách ổn định.
- Tránh phụ thuộc thời gian hiện tại hoặc thứ tự thực thi không xác định.
- Ghi phiên bản generator và scale factor.
- Lưu số hàng và một số aggregate checksum để kiểm tra sau khi nạp.

Ví dụ, category có thể được tạo bằng phép modulo trên product_id; ngày tạo có thể dựa trên hash hoặc công thức xác định của order_id. Cùng một ID luôn sinh cùng một giá trị.

### 4.2. Dữ liệu thật đã ẩn danh

Nếu cần phân bố sát production hơn, có thể dùng bản sao đã ẩn danh theo quy trình được phê duyệt. Phải loại bỏ hoặc biến đổi thông tin nhận dạng, token, bí mật, thông tin thanh toán và dữ liệu nhạy cảm. Chỉ giữ các đặc tính cần cho benchmark như phân bố, tương quan, kích thước và độ lệch.

Không cần đưa dữ liệu production trực tiếp vào bài test chỉ để có tính thực tế. Synthetic data với phân bố được đo và mô tả rõ thường đủ cho phần lớn bài kiểm thử hiệu năng.

## 5. Tạo dataset mẫu bằng PostgreSQL

Phần này xây dựng một dataset minh họa cho cửa hàng trực tuyến. SQL dùng cú pháp PostgreSQL, đặc biệt là generate_series và LATERAL. Với MySQL, SQL Server, Oracle hoặc hệ quản trị khác, cần chuyển phần sinh dữ liệu sang cú pháp tương ứng; nguyên tắc về quy mô, phân bố và tính tái lập vẫn giữ nguyên.

Dataset mặc định:

- 100.000 khách hàng.
- 10.000 sản phẩm.
- 1.000.000 đơn hàng.
- Trung bình 1–4 dòng hàng cho mỗi đơn.
- Có 100 khách hàng hoạt động mạnh hơn nhóm còn lại.
- Phần lớn đơn hàng tập trung trong một khoảng thời gian gần, phần còn lại trải dài hơn.

### 5.1. Tạo schema

~~~sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY,
    region_code text NOT NULL,
    created_at date NOT NULL,
    is_active boolean NOT NULL
);

CREATE TABLE products (
    product_id bigint PRIMARY KEY,
    category_id integer NOT NULL,
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    is_active boolean NOT NULL
);

CREATE TABLE inventory (
    product_id bigint PRIMARY KEY REFERENCES products(product_id),
    available_qty integer NOT NULL CHECK (available_qty >= 0),
    updated_at timestamptz NOT NULL
);

CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers(customer_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL,
    source_channel text NOT NULL,
    total_amount numeric(14, 2) NOT NULL DEFAULT 0
);

CREATE TABLE order_items (
    order_id bigint NOT NULL REFERENCES orders(order_id),
    line_no integer NOT NULL,
    product_id bigint NOT NULL REFERENCES products(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Khóa chính tự tạo index tương ứng. Các index phục vụ truy vấn nghiệp vụ sẽ được tạo sau khi nạp dữ liệu để tránh chi phí cập nhật index cho từng hàng trong quá trình bulk load.

### 5.2. Nạp khách hàng

~~~sql
INSERT INTO customers (
    customer_id,
    region_code,
    created_at,
    is_active
)
SELECT
    g,
    'R' || lpad((1 + (g % 12))::text, 2, '0'),
    DATE '2020-01-01' + (g % 1800)::integer,
    (g % 10 <> 0)
FROM generate_series(1, 100000) AS s(g);
~~~

Công thức tạo 12 vùng và tỷ lệ khách hàng hoạt động khoảng 90%. Dữ liệu hoàn toàn xác định theo customer_id.

### 5.3. Nạp sản phẩm và tồn kho

~~~sql
INSERT INTO products (
    product_id,
    category_id,
    unit_price,
    is_active
)
SELECT
    g,
    1 + ((g * 7) % 100)::integer,
    round(5 + ((g * 19) % 100000)::numeric / 100, 2),
    (g % 20 <> 0)
FROM generate_series(1, 10000) AS s(g);

INSERT INTO inventory (
    product_id,
    available_qty,
    updated_at
)
SELECT
    product_id,
    100000 + (product_id % 5000)::integer,
    TIMESTAMPTZ '2025-01-01 00:00:00+00'
FROM products;
~~~

Tồn kho ban đầu đủ lớn để bài test không nhanh chóng chuyển thành workload lỗi do hết hàng. Nếu mục tiêu là kiểm tra cạnh tranh tồn kho, hãy tạo một profile riêng với số lượng thấp hơn và phân bố sản phẩm nóng rõ ràng.

### 5.4. Nạp đơn hàng với phân bố lệch

~~~sql
INSERT INTO orders (
    order_id,
    customer_id,
    created_at,
    status,
    source_channel,
    total_amount
)
SELECT
    g,
    CASE
        WHEN g % 10 = 0
            THEN 1 + ((g / 10) % 100)
        ELSE 101 + ((g * 7919) % 99900)
    END,
    (
        CASE
            WHEN g % 5 <> 0
                THEN TIMESTAMP '2025-01-01 00:00:00'
                     + ((g * 37) % 90)::integer * INTERVAL '1 day'
            ELSE TIMESTAMP '2022-01-01 00:00:00'
                 + ((g * 7919) % 1000)::integer * INTERVAL '1 day'
        END
    ) + ((g * 13) % 86400)::integer * INTERVAL '1 second',
    CASE
        WHEN g % 100 < 60 THEN 'PAID'
        WHEN g % 100 < 85 THEN 'SHIPPED'
        WHEN g % 100 < 95 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    CASE
        WHEN g % 4 = 0 THEN 'WEB'
        WHEN g % 4 = 1 THEN 'MOBILE'
        WHEN g % 4 = 2 THEN 'STORE'
        ELSE 'PARTNER'
    END,
    0
FROM generate_series(1, 1000000) AS s(g);
~~~

Mỗi đơn hàng có customer_id xác định theo order_id. Khoảng 10% số đơn được gán cho 100 khách hàng hoạt động mạnh; phần còn lại trải trên nhóm khách hàng lớn hơn. Đây là phân bố lệch có chủ đích để kiểm tra truy vấn lịch sử đơn hàng, GROUP BY và khả năng xử lý heavy customer.

80% đơn hàng được tạo trong khoảng thời gian gần 90 ngày, 20% trải dài hơn. Status có phân bố 60% PAID, 25% SHIPPED, 10% PENDING và 5% CANCELLED. Các tỷ lệ được xác định bằng công thức, không phụ thuộc random seed.

### 5.5. Nạp dòng đơn hàng

~~~sql
INSERT INTO order_items (
    order_id,
    line_no,
    product_id,
    quantity,
    unit_price
)
SELECT
    o.order_id,
    s.line_no,
    p.product_id,
    1 + ((o.order_id + s.line_no) % 5)::integer,
    p.unit_price
FROM orders AS o
CROSS JOIN LATERAL generate_series(
    1,
    1 + (o.order_id % 4)::integer
) AS s(line_no)
JOIN products AS p
    ON p.product_id =
       1 + ((o.order_id * 31 + s.line_no * 17) % 10000);
~~~

Mỗi đơn có từ 1 đến 4 dòng hàng. Product được chọn bằng công thức xác định từ order_id và line_no. Giá dòng hàng lấy từ bảng products để dữ liệu nhất quán.

### 5.6. Tính tổng tiền đơn hàng từ dòng chi tiết

~~~sql
UPDATE orders AS o
SET total_amount = x.total_amount
FROM (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_items
    GROUP BY order_id
) AS x
WHERE x.order_id = o.order_id;
~~~

Phép cập nhật này thuộc bước tạo dataset, không đưa vào thời gian đo workload. Nó bảo đảm total_amount bằng tổng giá trị các dòng hàng theo dữ liệu seed.

### 5.7. Tạo index cho workload ban đầu

~~~sql
CREATE INDEX ix_orders_customer_created
    ON orders (customer_id, created_at DESC, order_id DESC);

CREATE INDEX ix_orders_created_status
    ON orders (created_at, status);

CREATE INDEX ix_products_category_active
    ON products (category_id, is_active, product_id);

CREATE INDEX ix_order_items_product
    ON order_items (product_id);
~~~

Đây là index baseline cho các truy vấn minh họa bên dưới, không phải bộ index tối ưu cho mọi ứng dụng. Trước khi tạo index cần xem lại workload thực tế và chi phí ghi. Không tạo index dư thừa chỉ để mọi câu truy vấn đều có một index riêng.

### 5.8. Cập nhật statistics

~~~sql
ANALYZE customers;
ANALYZE products;
ANALYZE inventory;
ANALYZE orders;
ANALYZE order_items;
~~~

Statistics giúp optimizer ước lượng cardinality và chọn execution plan. Sau khi nạp lượng dữ liệu lớn hoặc thay đổi mạnh phân bố, cần cập nhật statistics trước khi lấy baseline. Ghi lại thời điểm ANALYZE và các cấu hình thống kê quan trọng.

## 6. Xác nhận dataset sau khi nạp

Không bắt đầu benchmark trước khi kiểm tra số hàng, quan hệ và phân bố.

### 6.1. Đếm số hàng

~~~sql
SELECT 'customers' AS table_name, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'inventory', COUNT(*) FROM inventory
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'order_items', COUNT(*) FROM order_items;
~~~

Kết quả kỳ vọng với seed mặc định:

| Bảng | Số hàng kỳ vọng |
| --- | ---: |
| customers | 100.000 |
| products | 10.000 |
| inventory | 10.000 |
| orders | 1.000.000 |
| order_items | Phụ thuộc 1–4 dòng/đơn theo công thức |

### 6.2. Kiểm tra phân bố trạng thái

~~~sql
SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status
ORDER BY status;
~~~

Đối chiếu kết quả với tỷ lệ status trong generator. Có thể kiểm tra thêm theo source_channel, tháng, vùng và trạng thái hoạt động.

### 6.3. Tìm nhóm khách hàng lớn

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 20;
~~~

Kết quả phải cho thấy nhóm khách hàng nóng có số đơn cao hơn rõ rệt. Nếu phân bố trở nên đồng đều ngoài dự kiến, cần kiểm tra generator hoặc phép gán khóa.

### 6.4. Kiểm tra tổng tiền

~~~sql
SELECT COUNT(*) AS mismatched_orders
FROM orders AS o
JOIN (
    SELECT order_id, SUM(quantity * unit_price) AS calculated_total
    FROM order_items
    GROUP BY order_id
) AS x ON x.order_id = o.order_id
WHERE o.total_amount <> x.calculated_total;
~~~

Kết quả kỳ vọng là 0. Có thể bổ sung kiểm tra khóa ngoại, tồn kho không âm và số dòng hàng mỗi đơn. Các truy vấn xác nhận này không thuộc workload đo; chạy trước khi snapshot dataset.

## 7. Tạo tải mẫu từ giao dịch nghiệp vụ

Dataset chỉ tạo điều kiện truy cập. Workload mới quyết định cách database được sử dụng. Hãy xây dựng tải từ các giao dịch người dùng hoặc tác vụ nền có ý nghĩa.

Ví dụ workload cửa hàng trực tuyến:

| Giao dịch | Tỷ trọng | Loại truy cập |
| --- | ---: | --- |
| Xem chi tiết sản phẩm | 35% | Đọc một sản phẩm và tồn kho |
| Xem lịch sử đơn hàng | 25% | Đọc theo customer_id, sort và limit |
| Tìm kiếm sản phẩm | 20% | Đọc theo category và trạng thái |
| Checkout | 15% | Đọc kiểm tra và ghi nhiều bảng |
| Báo cáo doanh thu | 5% | Đọc nhiều hàng, aggregate và sort |
| **Tổng** | **100%** | |

Tỷ trọng này là profile mẫu. Khi có telemetry, thay bằng tỷ trọng đo được của giờ bình thường hoặc giờ cao điểm. Lưu profile riêng cho normal, peak, read-heavy, write-heavy và mixed workload.

### 7.1. Truy vấn xem chi tiết sản phẩm

~~~sql
SELECT
    p.product_id,
    p.category_id,
    p.unit_price,
    p.is_active,
    i.available_qty
FROM products AS p
JOIN inventory AS i
    ON i.product_id = p.product_id
WHERE p.product_id = $1;
~~~

Tham số $1 được bind qua driver. Bộ tạo tải chọn product_id theo phân bố nóng/lạnh thay vì chỉ dùng một ID cố định.

### 7.2. Truy vấn lịch sử đơn hàng

~~~sql
SELECT
    order_id,
    created_at,
    status,
    total_amount
FROM orders
WHERE customer_id = $1
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Truy vấn này sử dụng index theo customer_id và thứ tự thời gian. Cần thử cả khách hàng thông thường lẫn nhóm khách hàng lớn để quan sát khác biệt cardinality.

### 7.3. Truy vấn tìm kiếm sản phẩm

~~~sql
SELECT
    product_id,
    category_id,
    unit_price
FROM products
WHERE category_id = $1
  AND is_active = TRUE
ORDER BY product_id
LIMIT 20;
~~~

Tham số category_id nên được chọn theo phân bố thực tế. Không phải mọi category đều có cùng số sản phẩm.

### 7.4. Truy vấn báo cáo doanh thu

~~~sql
SELECT
    date_trunc('day', created_at) AS order_day,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= $1
  AND created_at < $2
GROUP BY date_trunc('day', created_at), status
ORDER BY order_day, status;
~~~

Truy vấn này tạo tải đọc và tổng hợp lớn hơn các truy vấn tra cứu. Tỷ lệ báo cáo trong workload phải phản ánh tần suất thực; nếu chỉ cần kiểm tra OLTP, có thể chạy báo cáo như một workload nền riêng.

### 7.5. Transaction checkout minh họa

Checkout cần đọc và ghi trong một transaction để bảo đảm tồn kho và đơn hàng nhất quán. Ví dụ dưới đây dùng placeholder theo PostgreSQL prepared statement; ứng dụng phải kiểm tra số hàng được cập nhật:

~~~sql
BEGIN;

UPDATE inventory
SET available_qty = available_qty - $1,
    updated_at = clock_timestamp()
WHERE product_id = $2
  AND available_qty >= $1;

-- Ứng dụng phải xác nhận UPDATE ảnh hưởng đúng một hàng.
-- Nếu không, ROLLBACK và trả kết quả hết hàng hoặc dữ liệu không hợp lệ.

INSERT INTO orders (
    order_id,
    customer_id,
    created_at,
    status,
    source_channel,
    total_amount
)
VALUES ($3, $4, clock_timestamp(), 'PENDING', 'WEB', 0);

INSERT INTO order_items (
    order_id, line_no, product_id, quantity, unit_price
)
VALUES
    ($3, 1, $2, $1, $5);

UPDATE orders
SET total_amount = (
    SELECT SUM(quantity * unit_price)
    FROM order_items
    WHERE order_id = $3
)
WHERE order_id = $3;

COMMIT;
~~~

Đây là luồng minh họa một dòng hàng. Workload thực tế có thể có nhiều dòng hàng và các kiểm tra giỏ hàng, giá, coupon hoặc thanh toán. order_id phải duy nhất; trong bài test có thể dành một dải ID mới bắt đầu sau ID lớn nhất của seed. Khi UPDATE inventory ảnh hưởng 0 hàng, ứng dụng phải rollback transaction thay vì tiếp tục tạo đơn.

## 8. Tính tốc độ giao dịch và read/write mix

Giả sử mục tiêu tải là 100 business transaction/giây theo profile mẫu:

| Giao dịch | Tỷ trọng | Tốc độ mục tiêu |
| --- | ---: | ---: |
| Product detail | 35% | 35/s |
| Order history | 25% | 25/s |
| Product search | 20% | 20/s |
| Checkout | 15% | 15/s |
| Revenue report | 5% | 5/s |

Tốc độ từng loại được tính bằng tổng tốc độ nhân tỷ trọng. Đây là tốc độ giao dịch nghiệp vụ, không phải SQL statement rate.

Nếu mỗi lần thực hiện có số statement trung bình như sau:

| Giao dịch | SELECT | DML |
| --- | ---: | ---: |
| Product detail | 1 | 0 |
| Order history | 1 | 0 |
| Product search | 1 | 0 |
| Checkout | 2 | 5,5 |
| Revenue report | 1 | 0 |

Checkout có trung bình 5,5 thao tác ghi vì ví dụ có một cập nhật inventory, một insert order, trung bình 2,5 insert order item và một cập nhật total. Nếu ứng dụng dùng batch insert hoặc tính total trước khi insert, statement count sẽ khác.

Số SELECT mỗi giây:

\[
R = 35 \times 1 + 25 \times 1 + 20 \times 1 + 15 \times 2 + 5 \times 1
= 115
\]

Số DML mỗi giây:

\[
W = 15 \times 5,5 = 82,5
\]

Tỷ trọng statement đọc xấp xỉ:

\[
P_R = \frac{115}{115 + 82,5} \approx 58,23\%
\]

Tỷ trọng statement ghi xấp xỉ 41,77%. Đây chỉ là read/write mix theo số statement. Để sizing I/O cần đo thêm rows examined, rows changed, logical/physical reads, bytes truyền, WAL/log bytes và flush.

Nếu một câu SELECT trả hàng triệu hàng còn một INSERT ghi một hàng, tỷ lệ statement không phản ánh lượng dữ liệu. Luôn ghi rõ mẫu số khi báo cáo read/write ratio.

## 9. Chọn mô hình phát tải

### 9.1. Closed workload

Mỗi virtual user gửi một giao dịch, đợi response, nghỉ theo think time rồi gửi giao dịch tiếp theo. Mô hình này phù hợp để mô phỏng một số lượng người dùng tương tác cố định.

Với N user, response time R và think time Z, throughput gần đúng trong trạng thái ổn định:

\[
X \approx \frac{N}{R + Z}
\]

Khi hệ thống chậm, user closed-loop tự giảm tốc độ gửi request. Vì vậy, closed workload có thể che giấu queueing nếu chỉ quan sát số user.

### 9.2. Open workload

Request được phát ra theo arrival rate mục tiêu, không đợi request trước hoàn tất. Mô hình này phù hợp khi hệ thống nhận event hoặc request theo tốc độ đến tương đối cố định.

Với open workload, khi database chậm, số request chờ có thể tăng. Load generator cần đủ CPU, network và worker để duy trì arrival rate; nếu không, tải thực tế thấp hơn cấu hình.

### 9.3. Think time và pacing

Think time mô phỏng thời gian người dùng đọc hoặc thao tác giữa các request. Pacing là khoảng nghỉ được thêm để điều khiển tốc độ lặp. Ghi lại hai thông số riêng, vì chúng tác động trực tiếp đến concurrency và throughput.

Không trộn think time vào thời gian database. Hãy đo response time ở tầng ứng dụng và database execution/wait time riêng để phân biệt nút thắt.

## 10. Chuẩn bị môi trường trước khi đo

Trước mỗi lần chạy, xác nhận:

- Database ở trạng thái ổn định và không có job ngoài kịch bản.
- Schema, index, constraint và partition đúng phiên bản.
- Dataset đúng scale factor và checksum.
- Statistics đã được cập nhật theo quy trình cố định.
- Cache được chuẩn bị theo mục tiêu warm hoặc cold.
- Connection pool, timeout, isolation level và retry policy được ghi nhận.
- Load generator có đủ tài nguyên và đồng bộ thời gian.
- Logging/monitoring được cấu hình nhất quán.
- Không có benchmark khác chạy đồng thời làm nhiễu kết quả.
- Môi trường được phép thử tải và có giới hạn bảo vệ phù hợp.

Nếu chạy warm-cache test, thực hiện warm-up bằng cùng workload trước giai đoạn đo. Nếu chạy cold-cache test, phải có quy trình làm lạnh cache được hỗ trợ và an toàn cho môi trường; không xóa cache tùy tiện trên production.

## 11. Định nghĩa baseline protocol

Một protocol mẫu:

1. Khôi phục snapshot dataset đã seed.
2. Kiểm tra row count, phân bố và các aggregate xác nhận.
3. Xác nhận index, schema và statistics.
4. Ghi lại engine version, cấu hình, CPU, RAM và storage.
5. Chạy smoke test tải thấp để kiểm tra script.
6. Chạy warm-up theo thời gian cố định.
7. Phát workload ở arrival rate hoặc concurrency mục tiêu.
8. Giữ steady-state trong khoảng đo đã định.
9. Ghi metric theo chu kỳ và lưu log của từng giao dịch.
10. Kết thúc tải, đợi hệ thống trở về trạng thái ổn định.
11. Lưu kết quả, query plan và manifest.
12. Khôi phục cùng snapshot trước lần chạy tiếp theo.

Ví dụ lịch chạy:

| Giai đoạn | Thời lượng ví dụ | Mục đích |
| --- | ---: | --- |
| Smoke | 2 phút | Xác nhận script và dữ liệu |
| Warm-up | 5 phút | Ổn định cache và connection |
| Steady-state | 15 phút | Thu thập số đo chính |
| Cool-down | 3 phút | Quan sát hàng đợi và tài nguyên hồi phục |

Thực hiện tối thiểu ba lần lặp nếu môi trường cho phép. Báo cáo median và độ phân tán giữa các lần chạy; nếu các lần chạy lệch mạnh, điều tra nguyên nhân trước khi kết luận.

## 12. Các chỉ số phải thu thập

### 12.1. Ở tầng ứng dụng và giao dịch

- Offered request rate và completed transaction rate.
- Throughput theo từng transaction class.
- p50, p95 và p99 response time.
- Error rate, timeout, retry và rollback.
- Queue wait và connection pool wait.
- Thời gian xử lý ứng dụng ngoài database.

### 12.2. Ở database

- Query execution time và query count.
- Estimated rows so với actual rows.
- Logical reads và physical reads.
- Rows returned, rows examined và rows changed.
- CPU time và wait events.
- Lock wait, deadlock, blocked session và transaction age.
- Commit rate, log flush latency và log bytes.
- Temp read/write, spill count và spill bytes.
- Active sessions, worker usage và memory grant/work area.

### 12.3. Ở hệ điều hành và storage

- CPU utilization, run queue và context switch.
- RAM, page fault, swap và memory pressure.
- IOPS đọc/ghi, throughput, latency và queue depth.
- Dung lượng còn lại và tốc độ tăng file.
- Network throughput và retransmission nếu có.

### 12.4. Ở load generator

- CPU và memory.
- Số worker/thread đang hoạt động.
- Network bandwidth.
- Request phát ra so với request mục tiêu.
- Queue nội bộ, dropped request và lỗi phía client.

Nếu load generator bão hòa, số đo database không còn đại diện cho tải mục tiêu.

## 13. Lưu execution plan và trạng thái optimizer

Với các truy vấn quan trọng, lưu:

- SQL text đã chuẩn hóa và bind parameter profile.
- Query ID, plan hash hoặc identifier tương đương.
- Estimated rows và actual rows.
- Join order, access path, sort/hash operator.
- Buffer/logical reads, physical I/O và temp spill.
- Thời gian CPU và elapsed time.
- Statistics timestamp và cấu hình optimizer liên quan.

Trên PostgreSQL, có thể dùng EXPLAIN để kiểm tra plan. Trong môi trường kiểm thử, EXPLAIN ANALYZE chạy thật câu lệnh và có thể tạo tải hoặc thay đổi dữ liệu nếu câu lệnh có tác dụng ghi. EXPLAIN (ANALYZE, BUFFERS, SETTINGS) là ví dụ hữu ích cho truy vấn đọc ở các phiên bản hỗ trợ; một số option như WAL phụ thuộc phiên bản. Không chạy tùy tiện trên production hoặc trên câu lệnh ghi chưa được kiểm soát.

Một plan hash giống nhau không bảo đảm thời gian giống nhau: cache, concurrency, storage và phân bố tham số vẫn có thể khác. Ngược lại, plan thay đổi không luôn có nghĩa là regression; cần so actual performance.

## 14. Quản lý trạng thái dữ liệu giữa các lần chạy

Workload ghi làm dataset thay đổi. Nếu không reset, lần chạy sau có thể có nhiều đơn hơn, tồn kho thấp hơn, index lớn hơn hoặc phân bố trạng thái khác.

Các chiến lược:

- Snapshot/restore: khôi phục cùng trạng thái dữ liệu trước mỗi lần chạy.
- Database clone: tạo bản clone từ snapshot cho từng lượt benchmark.
- Seed lại: chạy generator xác định và nạp lại từ đầu.
- Transaction rollback: phù hợp với một số test ghi cô lập, nhưng có thể không đại diện chi phí commit thực.
- Dải dữ liệu riêng theo run: tránh trùng ID và cho phép dọn dữ liệu theo batch.

Với workload commit thật, không dùng rollback cho toàn bộ test nếu mục tiêu là đo WAL, log flush, index maintenance hoặc chi phí commit. Hãy reset bằng snapshot giữa các lượt.

### 14.1. Xác minh trạng thái trước và sau

Lưu:

- Row count mỗi bảng.
- Min/max ID và timestamp.
- Count theo status/category/region.
- Tổng tiền hoặc checksum nghiệp vụ.
- Kích thước bảng và index.
- Số hàng mới được tạo trong run.
- Tồn kho hoặc trạng thái tài nguyên quan trọng.

Các giá trị này giúp phát hiện dataset đã lệch trước khi so sánh kết quả.

## 15. Manifest ghi lại điều kiện benchmark

Mỗi run nên có một manifest. Ví dụ:

~~~yaml
run_id: dbperf-baseline-2026-01
module: DATABASE_PERFORMANCE
environment: isolated-performance-test
database:
  engine: PostgreSQL
  version: "<record exact version>"
  schema_revision: "<migration or schema hash>"
  configuration_revision: "<configuration hash>"
  statistics_time: "<timestamp>"
  cache_profile: warm
hardware:
  cpu: "<model and vCPU count>"
  memory_gb: "<RAM>"
  storage: "<type, capacity, IOPS and throughput limits>"
dataset:
  generator_version: "shop-seed-v1"
  scale_factor: 1
  seed: "deterministic-formula-v1"
  customers: 100000
  products: 10000
  orders: 1000000
  row_counts_checksum: "<stored validation result>"
workload:
  profile: mixed-oltp
  arrival_rate_per_second: 100
  transaction_mix:
    product_detail: 0.35
    order_history: 0.25
    product_search: 0.20
    checkout: 0.15
    revenue_report: 0.05
  model: open
  duration_seconds: 900
  warmup_seconds: 300
  client_version: "<load generator version>"
  driver_version: "<JDBC driver version>"
results:
  completed_transactions_per_second: "<measured>"
  p50_ms: "<measured>"
  p95_ms: "<measured>"
  p99_ms: "<measured>"
  error_rate: "<measured>"
  retry_rate: "<measured>"
  cpu_peak_percent: "<measured>"
  memory_peak_gb: "<measured>"
  temp_peak_gb: "<measured>"
  read_iops: "<measured>"
  write_iops: "<measured>"
  lock_wait_ms: "<measured>"
~~~

Các giá trị trong dấu ngoặc nhọn phải được thay bằng số liệu thực. Không ghi mật khẩu, token, connection string chứa secret hoặc dữ liệu cá nhân vào manifest. Lưu manifest cùng log, plan và kết quả đo trong hệ thống quản lý benchmark của nhóm.

## 16. So sánh baseline với candidate

Khi kiểm tra một thay đổi như thêm index, sửa SQL, đổi fetch size, tăng memory hoặc thay đổi concurrency:

1. Dùng cùng dataset snapshot.
2. Dùng cùng transaction mix và tham số có phân bố tương đương.
3. Dùng cùng arrival rate/concurrency, think time và duration.
4. Dùng cùng warm-up và cache profile.
5. Chỉ thay đổi một nhóm yếu tố chính trong mỗi thử nghiệm.
6. Chạy lặp lại đủ số lần để đánh giá độ ổn định.
7. So throughput, latency percentile, lỗi và tài nguyên cùng lúc.
8. Kiểm tra kết quả nghiệp vụ trước/sau.

Không kết luận một thay đổi tốt chỉ vì p50 giảm. Nếu p99 tăng mạnh, lỗi tăng hoặc throughput hoàn tất giảm, hệ thống có thể đang xấu đi ở vùng tải quan trọng.

### 16.1. Bảng so sánh

| Chỉ số | Baseline | Candidate | Thay đổi |
| --- | ---: | ---: | ---: |
| Completed TPS | Ghi số đo | Ghi số đo | Candidate/Baseline |
| p50 latency | Ghi số đo | Ghi số đo | Phần trăm thay đổi |
| p95 latency | Ghi số đo | Ghi số đo | Phần trăm thay đổi |
| p99 latency | Ghi số đo | Ghi số đo | Phần trăm thay đổi |
| Error rate | Ghi số đo | Ghi số đo | Chênh lệch |
| CPU peak | Ghi số đo | Ghi số đo | Chênh lệch |
| Temp peak | Ghi số đo | Ghi số đo | Chênh lệch |
| Read/write I/O | Ghi số đo | Ghi số đo | Chênh lệch |
| Lock wait | Ghi số đo | Ghi số đo | Chênh lệch |

Với latency, mức giảm phần trăm có thể tính:

\[
\text{Latency improvement} =
\frac{L_{\text{baseline}} - L_{\text{candidate}}}
{L_{\text{baseline}}} \times 100\%
\]

Với throughput, mức tăng phần trăm:

\[
\text{Throughput improvement} =
\frac{X_{\text{candidate}} - X_{\text{baseline}}}
{X_{\text{baseline}}} \times 100\%
\]

Chỉ số tốt hơn phải được đánh giá cùng điều kiện tải và tỷ lệ lỗi. Nếu candidate hoàn tất ít giao dịch hơn vì timeout, latency trung bình của các giao dịch thành công có thể trông thấp giả tạo.

## 17. Ví dụ thực hành: xây dựng baseline đầu tiên

Giả sử môi trường kiểm thử đã có PostgreSQL và một load generator. Nhóm muốn đo workload hỗn hợp ở 100 business transaction/giây.

### Bước 1: chuẩn bị database

- Tạo database thử nghiệm cô lập.
- Chạy DDL ở mục 5.1.
- Nạp customers, products, inventory, orders và order_items theo thứ tự.
- Tính total_amount từ order_items.
- Tạo index baseline.
- Chạy ANALYZE cho các bảng.
- Lưu snapshot dataset và ghi manifest.

### Bước 2: xác nhận dữ liệu

- Đếm row count.
- Kiểm tra foreign key và tổng tiền.
- Kiểm tra phân bố status, category và customer_id.
- Xác nhận nhóm khách hàng nóng xuất hiện đúng như thiết kế.
- Ghi lại dung lượng bảng và index.

### Bước 3: cấu hình workload

- 35% product detail.
- 25% order history.
- 20% product search.
- 15% checkout.
- 5% revenue report.
- Dùng tham số theo phân bố hot/normal/cold đã xác định.
- Cấp ID checkout trong dải chưa sử dụng.
- Kiểm tra mỗi checkout có commit/rollback đúng.

### Bước 4: chạy smoke và warm-up

Chạy tải thấp để xác nhận script không lỗi. Sau đó warm-up bằng profile mục tiêu trong khoảng thời gian cố định. Không đưa số liệu warm-up vào kết quả steady-state.

### Bước 5: đo steady-state

Phát 100 business transaction/giây trong 15 phút. Thu thập latency từng loại giao dịch, completed TPS, lỗi, CPU, memory, I/O, temp, lock wait, connection wait và plan của truy vấn quan trọng.

### Bước 6: lặp lại

Khôi phục cùng snapshot, kiểm tra lại row count và statistics, rồi lặp lại ít nhất hai lần nữa. So median và độ phân tán giữa ba lượt.

### Bước 7: lưu baseline

Lưu manifest, dataset generator version, workload version, log, query plan, dashboard export và ghi chú môi trường. Ghi rõ những khác biệt hoặc sự cố trong từng lần chạy.

### Bước 8: thử một thay đổi

Ví dụ, thêm một index phục vụ truy vấn order history hoặc sửa một câu SQL đang có p95 cao. Tạo candidate mới, giữ nguyên các điều kiện khác, chạy lại protocol và so sánh kết quả.

## 18. Các nguyên nhân làm benchmark không thể tái lập

### Dataset thay đổi giữa các lượt

Giao dịch ghi làm tăng số hàng, thay đổi tồn kho, trạng thái và kích thước index. Khôi phục snapshot hoặc seed lại trước mỗi lượt.

### Generator không xác định

Dùng random không ghi seed, phụ thuộc thời gian hiện tại hoặc sinh khóa theo thứ tự thread có thể làm phân bố khác nhau. Dùng công thức xác định hoặc seed có kiểm soát.

### Cache profile không nhất quán

Một lượt warm cache, một lượt cold cache sẽ có physical I/O và latency khác nhau. Ghi rõ cách warm-up và không trộn hai loại test.

### Statistics khác nhau

Sau bulk load hoặc thay đổi dữ liệu, optimizer có thể dùng statistics khác. Chạy và ghi lại bước ANALYZE/statistics collection theo cùng quy trình.

### Tải phát ra khác tải cấu hình

Load generator có thể bão hòa hoặc closed workload giảm throughput khi response time tăng. Ghi offered rate, completed rate và tài nguyên máy phát tải.

### Có job ngoài kịch bản

Backup, vacuum, index rebuild, ETL hoặc tác vụ hệ thống có thể làm I/O và CPU thay đổi. Ghi lại và kiểm soát tác vụ nền.

### Dùng tham số quá đơn giản

Một customer_id hoặc category_id cố định không đại diện cho phân bố khóa. Dùng tập tham số hot, normal và cold có tỷ trọng được ghi lại.

### Chỉ đo trung bình

Average có thể che giấu tail latency. Ghi p50, p95, p99 và error rate theo từng transaction class.

## 19. An toàn và tính toàn vẹn của môi trường test

Benchmark tạo tải cao và có thể ghi dữ liệu lớn. Hãy dùng môi trường được phép thử tải, có giới hạn tài nguyên và kế hoạch khôi phục.

- Không phát tải tùy tiện vào production.
- Dùng dữ liệu tổng hợp hoặc dữ liệu đã ẩn danh.
- Không ghi secret hoặc thông tin cá nhân vào manifest và log.
- Giới hạn số worker, connection và tốc độ phát tải để tránh làm sập môi trường dùng chung.
- Có kế hoạch dừng test khi error rate, disk usage hoặc latency vượt ngưỡng bảo vệ.
- Kiểm tra backup/snapshot có thể khôi phục trước khi dùng làm mốc.
- Không xóa file data, log hoặc temp thủ công để reset trạng thái.
- Dọn dữ liệu benchmark bằng SQL hoặc quy trình quản trị phù hợp.

## 20. Checklist trước khi công nhận baseline

| Hạng mục | Điều kiện xác nhận |
| --- | --- |
| Scope | Mục tiêu và phạm vi test được ghi rõ |
| Schema | DDL, index, constraint và partition đã lưu phiên bản |
| Dataset | Scale factor, generator, seed và row counts đã ghi |
| Distribution | Cardinality, skew, NULL và working set được mô tả |
| Consistency | Foreign key và aggregate nghiệp vụ hợp lệ |
| Statistics | Statistics được cập nhật theo quy trình cố định |
| Workload | Transaction mix, read/write mix và bind values đã định nghĩa |
| Load model | Open/closed, concurrency, think time và arrival rate đã ghi |
| Environment | Engine, driver, CPU, RAM, storage và config đã ghi |
| Cache | Warm/cold profile và warm-up được xác định |
| Measurement | Throughput, percentile, errors và resource metrics được lưu |
| Repeatability | Có snapshot/reset và protocol để chạy lại |
| Integrity | Kết quả nghiệp vụ được xác nhận sau test |

Nếu một mục chưa có, ghi rõ giới hạn của baseline thay vì tuyên bố phép đo có thể tái lập hoàn toàn.

## 21. Nguyên tắc cần ghi nhớ

- Baseline là tập số đo kèm điều kiện, không phải một con số latency hoặc throughput đơn lẻ.
- Dataset phải đại diện cho quy mô, cardinality, skew, row width, quan hệ và working set.
- Dữ liệu tổng hợp có thể tái lập nên dùng ID, công thức và seed xác định.
- Kiểm tra row count, phân bố và tính nhất quán nghiệp vụ trước khi phát tải.
- Transaction mix và read/write mix cần có mẫu số rõ ràng; statement ratio không thay thế byte/I/O ratio.
- Tải mẫu phải mô tả arrival rate, concurrency, think time, pacing và tham số truy vấn.
- Phân biệt warm-cache và cold-cache test; áp dụng cùng quy trình giữa các lượt.
- Ghi lại engine, driver, schema, index, statistics, phần cứng và storage.
- Khôi phục cùng snapshot hoặc seed lại trạng thái trước khi so sánh workload ghi.
- Thu thập throughput hoàn tất, p50/p95/p99, lỗi, retry, CPU, memory, I/O, temp và lock wait.
- Lưu execution plan và manifest để truy nguyên khác biệt.
- Chỉ thay đổi một nhóm yếu tố chính mỗi lần và xác nhận kết quả nghiệp vụ sau tối ưu.

Một baseline đáng tin cậy được xây dựng từ dữ liệu đúng hình dạng, tải đúng hành vi và quy trình đo được ghi lại đầy đủ. Khi generator xác định, snapshot ổn định, workload mix rõ ràng và các số đo được thu thập ở cùng điều kiện, nhóm có thể phân biệt cải thiện thật với biến động do cache, dữ liệu hoặc môi trường. Đây là nền tảng để tối ưu chỉ mục, SQL, bộ nhớ, I/O và concurrency một cách có thể kiểm chứng.

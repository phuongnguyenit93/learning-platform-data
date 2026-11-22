# Giảm dữ liệu đọc bằng cột cần thiết và điều kiện chọn lọc trong PostgreSQL

Một truy vấn trả về 20 dòng không nhất thiết là truy vấn nhẹ. PostgreSQL có thể phải đọc hàng trăm nghìn dòng, kiểm tra điều kiện trên từng dòng, sắp xếp kết quả rồi mới trả 20 dòng ấy. Ngược lại, một truy vấn cần 20 dòng từ một khách hàng cụ thể có thể tìm chúng qua chỉ mục mà không phải quét toàn bộ bảng.

Hai thay đổi thường đem lại hiệu quả lớn khi tối ưu truy vấn:

1. **Chỉ lấy các cột thực sự cần** thay vì mặc định dùng `SELECT *`.
2. **Giới hạn tập dòng phải xem và phải trả** bằng điều kiện `WHERE` chọn lọc, được viết theo cách PostgreSQL có thể sử dụng chỉ mục, thống kê và những cơ chế giảm dữ liệu đọc.

Ví dụ màn hình danh sách chỉ hiển thị mã đơn, ngày tạo, trạng thái và tổng tiền:

~~~sql
-- Có thể mang về nhiều cột không dùng, kể cả nội dung văn bản lớn.
SELECT *
FROM orders
ORDER BY created_at DESC
LIMIT 20;
~~~

So với:

~~~sql
-- Diễn đạt chính xác nhu cầu của màn hình.
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Truy vấn thứ hai có **projection** (danh sách cột) gọn và **predicate** (điều kiện lọc) cụ thể. Nếu có chỉ mục phù hợp, PostgreSQL có thể giới hạn cả số mục chỉ mục, dòng heap và dữ liệu gửi đến client.

Tuy nhiên, cần phân biệt ba thứ:

- **Dữ liệu logic:** số hàng/cột mà câu SQL yêu cầu xử lý và trả về.
- **Dữ liệu vật lý PostgreSQL phải truy cập:** trang index, heap, TOAST, vùng nhớ đệm hoặc storage.
- **Dữ liệu truyền qua mạng và xử lý trong ứng dụng:** số dòng, byte, đối tượng được deserialize, JSON được tạo, v.v.

Giảm số cột trong `SELECT` **không tự động** giảm số trang heap cần đọc nếu PostgreSQL vẫn thực hiện `Seq Scan` toàn bảng. Giá trị của việc chọn cột chính xác còn nằm ở giảm kích thước tuple đầu ra, hạn chế xử lý giá trị rộng, giảm băng thông, tạo điều kiện dùng **index-only scan**, và loại bỏ dữ liệu không cần thiết ở tầng ứng dụng.

Bài học đi từ nguyên lý đến thực hành PostgreSQL: `SELECT`-list, `WHERE` chọn lọc, **sargable predicates**, B-tree và covering indexes, partial indexes, JOIN, `ORDER BY ... LIMIT`, phân trang, partition pruning, `EXPLAIN (ANALYZE, BUFFERS)`, thống kê và bài tập.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích tại sao `SELECT *` thường không phù hợp cho API và báo cáo chỉ dùng một số cột.
2. Phân biệt **projection**, **filtering** và **số trang/buffer thực tế được đọc**.
3. Dùng `EXPLAIN (ANALYZE, BUFFERS)` để đọc `rows`, `width`, `Index Cond`, `Filter`, `Rows Removed by Filter` và `Buffers`.
4. Ước lượng độ chọn lọc (*selectivity*) của predicate và nhận ra điều kiện có thể dùng B-tree index.
5. Viết lại điều kiện thời gian, biểu thức, `LIKE` và `OR` cho phù hợp những chỉ mục đã có.
6. Chọn chỉ mục ghép và `INCLUDE` để phục vụ lọc, sắp xếp và trả về một số cột.
7. Giảm số hàng trung gian trong JOIN, tránh nhân dữ liệu không cần thiết.
8. Thiết kế truy vấn `LIMIT` và keyset pagination mà không hiểu nhầm rằng `LIMIT` tự giảm dữ liệu phải đọc.
9. Biết khi nào PostgreSQL cố ý chọn `Seq Scan` dù đã có index.
10. Thử thay đổi và đo lại trên dữ liệu, thống kê và workload đại diện.

## 2. Hai phép toán nền tảng: projection và selection

Trong mô hình quan hệ:

- **Projection:** chọn thuộc tính/cột cần hiển thị hoặc dùng cho phép tính.
- **Selection:** chọn các dòng thỏa một điều kiện.

Trong SQL, ý tưởng tương ứng:

~~~sql
SELECT order_id, created_at, total_amount   -- projection
FROM opt_lab.orders
WHERE customer_id = 42                      -- selection
  AND status = 'paid';
~~~

### 2.1. Dữ liệu qua các tầng

~~~text
PostgreSQL storage / buffer cache
          |
          v
    Scan / Index Scan
          |
       Filter
          |
    Join / Aggregate / Sort
          |
      Projection
          |
    Network / Driver
          |
       API / UI
~~~

Đây chỉ là sơ đồ ý niệm: PostgreSQL không bắt buộc xử lý mọi câu SQL theo đúng thứ tự tuyến tính trên. Planner có thể đẩy predicate xuống scan, chọn cách join khác, sắp xếp và tính biểu thức ở các node phù hợp.

**Mục tiêu của tối ưu hóa** là tránh thực hiện công việc không cần thiết càng sớm càng tốt, đồng thời giữ nguyên ngữ nghĩa kết quả.

### 2.2. Truy vấn nhanh không đồng nghĩa dùng index

Một `Seq Scan` trên bảng vài chục hàng thường rẻ hơn nhiều so với việc đi qua index rồi lấy từng tuple ở heap. Index có ích khi nó giúp **loại trừ phần đáng kể dữ liệu** hoặc cung cấp thứ tự truy vấn, nhưng không phải là mục tiêu tự thân.

## 3. Chuẩn bị bộ dữ liệu lab

Những ví dụ sau dành cho PostgreSQL hiện đại và một database thử nghiệm. Chỉ tạo schema và dữ liệu trong môi trường được phép; **không chạy kịch bản sinh dữ liệu trên production**.

### 3.1. Tạo schema và bảng khách hàng

~~~sql
CREATE SCHEMA opt_lab;

CREATE TABLE opt_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    region text NOT NULL,
    registered_at timestamptz NOT NULL
);
~~~

### 3.2. Tạo bảng sản phẩm

~~~sql
CREATE TABLE opt_lab.products (
    product_id integer PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    category text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    description text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

`description` và `attributes` tượng trưng cho những dữ liệu mà màn hình danh sách có thể không cần, nhưng trang chi tiết sản phẩm lại cần.

### 3.3. Tạo bảng đơn hàng

~~~sql
CREATE TABLE opt_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES opt_lab.customers(customer_id),
    product_id integer NOT NULL
        REFERENCES opt_lab.products(product_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL CHECK (
        status IN ('paid', 'shipped', 'cancelled')
    ),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    note text
);
~~~

Các chỉ mục khóa chính/`UNIQUE` phục vụ ràng buộc tương ứng được tạo tự động. **Foreign key không tự tạo index trên cột tham chiếu phía bảng con**, vì vậy `orders.customer_id` hoặc `orders.product_id` chưa có index riêng chỉ do khai báo FK.

### 3.4. Tạo 5.000 khách

~~~sql
INSERT INTO opt_lab.customers (
    customer_id, full_name, email, region, registered_at
)
SELECT
    g,
    'Khách hàng ' || g::text,
    'customer' || g::text || '@example.test',
    CASE (g % 4)
        WHEN 0 THEN 'north'
        WHEN 1 THEN 'south'
        WHEN 2 THEN 'central'
        ELSE 'other'
    END,
    TIMESTAMPTZ '2025-01-01 00:00:00+00'
      + g * INTERVAL '1 hour'
FROM generate_series(1, 5000) AS s(g);
~~~

### 3.5. Tạo 20.000 sản phẩm

~~~sql
INSERT INTO opt_lab.products (
    product_id, sku, product_name, category,
    price, description, attributes
)
SELECT
    g,
    'SKU-' || lpad(g::text, 6, '0'),
    'Sản phẩm ' || g::text,
    CASE g % 4
        WHEN 0 THEN 'book'
        WHEN 1 THEN 'office'
        WHEN 2 THEN 'drink'
        ELSE 'electronics'
    END,
    (10000 + (g % 3000) * 100)::numeric(12, 2),
    repeat(
        'Thông tin mô tả chi tiết cho sản phẩm. ',
        20
    ),
    jsonb_build_object(
        'brand', 'brand-' || (g % 30)::text,
        'warehouse', g % 12,
        'features', jsonb_build_array('standard', 'online')
    )
FROM generate_series(1, 20000) AS s(g);
~~~

Nội dung mô tả được lặp để minh họa dữ liệu dài. PostgreSQL có thể nén/TOAST giá trị tùy kích thước thực, nên **không giả định mỗi mô tả đều chiếm một trang heap riêng**.

### 3.6. Tạo 60.000 đơn

~~~sql
INSERT INTO opt_lab.orders (
    order_id, customer_id, product_id, created_at,
    status, total_amount, note
)
SELECT
    g::bigint,
    ((g - 1) % 5000) + 1,
    ((g - 1) % 20000) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
      + g * INTERVAL '1 minute',
    CASE
        WHEN g % 10 BETWEEN 0 AND 6 THEN 'paid'
        WHEN g % 10 IN (7, 8) THEN 'shipped'
        ELSE 'cancelled'
    END,
    (20000 + (g % 1000) * 125)::numeric(12, 2),
    repeat('Nội dung trao đổi đơn hàng. ', 12)
FROM generate_series(1, 60000) AS s(g);
~~~

Bộ dữ liệu cố ý có:

- 5.000 khách.
- 20.000 sản phẩm.
- 60.000 đơn, mỗi khách có đúng **12 đơn**.
- Mỗi sản phẩm có đúng **3 đơn**.
- Khoảng **70%** đơn `paid`, **20%** `shipped`, **10%** `cancelled`.
- Ngày đơn trải từ đầu tháng 1 sang tháng 2 năm 2026.

Đây là **dữ liệu giả phân bố đều theo công thức**, không phản ánh dữ liệu thương mại thật có skew, mùa vụ và tương quan phức tạp.

### 3.7. Thu thập thống kê

~~~sql
ANALYZE opt_lab.customers;
ANALYZE opt_lab.products;
ANALYZE opt_lab.orders;
~~~

### 3.8. Kiểm tra lượng dữ liệu

~~~sql
SELECT COUNT(*) AS customers FROM opt_lab.customers;
SELECT COUNT(*) AS products FROM opt_lab.products;
SELECT COUNT(*) AS orders FROM opt_lab.orders;

SELECT status, COUNT(*) AS n
FROM opt_lab.orders
GROUP BY status
ORDER BY status;
~~~

Kỳ vọng `customers=5000`, `products=20000` và `orders=60000`. Theo công thức sinh dữ liệu, `paid=42000`, `shipped=12000` và `cancelled=6000`.

## 4. SELECT * mang theo những gì?

~~~sql
SELECT *
FROM opt_lab.products
WHERE product_id = 42;
~~~

Truy vấn yêu cầu **mọi cột hiện tại của bảng**:

~~~text
product_id
sku
product_name
category
price
description
attributes
~~~

Trong khi màn hình danh sách sản phẩm có thể chỉ hiển thị:

~~~sql
SELECT product_id, sku, product_name, price
FROM opt_lab.products
WHERE product_id = 42;
~~~

### 4.1. Vì sao nên tránh SELECT * khi không cần?

- **Network payload:** ít cột hơn có thể giảm byte chuyển từ server đến client.
- **Driver và ứng dụng:** ít giá trị phải giải mã, cấp phát đối tượng, serialize JSON.
- **TOAST/giá trị rộng:** nếu không tham chiếu các cột văn bản/JSON lớn, có thể tránh chi phí lấy hoặc xử lý giá trị ngoài hàng khi không cần thiết.
- **JOIN:** tránh mang những cột trùng tên hoặc dữ liệu lớn qua trung gian.
- **Khả năng covering/index-only scan:** query chỉ dùng cột đã có trong index có thể tránh nhiều lần lấy dữ liệu heap khi điều kiện MVCC cho phép.
- **Hợp đồng API:** danh sách cột cụ thể ổn định hơn trước việc bảng có thêm cột mới hoặc một cột nhạy cảm.

### 4.2. Không khẳng định SELECT ít cột = ít heap blocks

Giả sử PostgreSQL chọn:

~~~text
Seq Scan on products
~~~

cho hai truy vấn:

~~~sql
SELECT * FROM opt_lab.products;

SELECT product_id FROM opt_lab.products;
~~~

Nếu đều quét toàn bộ quan hệ, PostgreSQL vẫn cần **duyệt các trang heap của bảng**. Chỉ chọn `product_id` không nhất thiết làm giảm `shared read/hit` đáng kể.

Nhưng nó có thể giảm công việc dựng output, đọc/giải mã giá trị lớn không cần, xử lý tại client và số byte truyền qua mạng. Với index thích hợp, planner còn có thể chọn một **index-only scan** cho truy vấn cột hẹp.

### 4.3. SELECT * cũng có lúc hợp lý

- Xem một hàng đầy đủ khi debug trong database lab.
- Trang chi tiết thực sự hiển thị tất cả thuộc tính.
- Truy vấn kiểm tra nhỏ, không nằm trên đường xử lý tần suất cao.

Vấn đề là **lấy thừa dữ liệu trên đường nóng** chứ không phải cú pháp `*` luôn sai.

## 5. Đo độ rộng đầu ra bằng EXPLAIN

~~~sql
EXPLAIN
SELECT *
FROM opt_lab.products
WHERE product_id <= 100;

EXPLAIN
SELECT product_id, product_name, price
FROM opt_lab.products
WHERE product_id <= 100;
~~~

Trong plan có thể thấy:

~~~text
... (cost=... rows=... width=...)
~~~

`width` là **kích thước hàng trung bình planner ước lượng**, tính bằng byte cho output của node, không phải số byte mạng được đo chính xác.

### 5.1. Width khác số trang đã đọc

Nếu `width` giảm từ 180 xuống 40 khi chọn ít cột, điều đó cho thấy output dự kiến gọn hơn. **Không suy** số block heap đọc cũng giảm tương ứng `180/40`.

### 5.2. Width của các node khác nhau

Một scan có thể chuyển nhiều cột cho filter/join nhưng node trên chỉ xuất ít cột. PostgreSQL có thể tối ưu danh sách cột cần ở từng node. Đọc **toàn cây plan** để biết nơi cột được dùng, không chỉ xem `width` ở node gốc.

## 6. Cột rộng, TOAST và giới hạn của projection

PostgreSQL có cơ chế **TOAST** để xử lý giá trị dài của một số kiểu như `text` và `jsonb`; giá trị có thể được nén hoặc lưu ngoài dòng heap theo điều kiện, storage setting và kích thước thực.

~~~sql
SELECT product_id, product_name
FROM opt_lab.products
WHERE product_id = 42;
~~~

không cần trả `description` hoặc `attributes`.

~~~sql
SELECT
    product_id,
    product_name,
    description,
    attributes
FROM opt_lab.products
WHERE product_id = 42;
~~~

yêu cầu các giá trị ấy để tạo kết quả.

### 6.1. Giá trị lớn không luôn đọc từ TOAST

Nếu một giá trị được lưu inline hoặc nén vừa đủ trong heap, cách truy cập có thể khác trường hợp giá trị nằm ngoài heap. Mức tiết kiệm từ bỏ cột rộng **phải đo** theo dữ liệu và plan thực.

### 6.2. Hàm trên cột rộng vẫn có thể buộc xử lý nó

~~~sql
SELECT product_id
FROM opt_lab.products
WHERE length(description) > 500;
~~~

Mặc dù kết quả chỉ trả `product_id`, điều kiện lọc **cần đọc/tính `description`** cho những hàng được xét. Chỉ giảm SELECT-list không tự loại mọi công việc trên cột không xuất hiện ở output.

### 6.3. ORDER BY cũng cần dữ liệu

~~~sql
SELECT product_id
FROM opt_lab.products
ORDER BY description
LIMIT 20;
~~~

Đầu ra chỉ có một cột, nhưng PostgreSQL vẫn cần hiểu thứ tự theo `description`, trừ khi có một đường truy cập chỉ mục thích hợp. **Projection nhỏ không bù được biểu thức sort tốn kém**.

## 7. WHERE chọn lọc là gì?

**Selectivity** biểu thị tỷ lệ hàng thỏa predicate so với tập hàng đang xét:

\[
\text{selectivity}\approx
\frac{\text{rows matching predicate}}
{\text{rows examined in relevant population}}
\]

Ví dụ trên 60.000 đơn:

~~~sql
SELECT *
FROM opt_lab.orders
WHERE order_id = 100;
~~~

khớp **1 hàng** với khóa chính, chọn lọc rất cao.

~~~sql
SELECT *
FROM opt_lab.orders
WHERE status = 'paid';
~~~

khớp khoảng **42.000/60.000 = 70%** hàng, chọn lọc tương đối thấp.

### 7.1. “Điều kiện có WHERE” chưa đủ

Hai predicate:

~~~sql
WHERE order_id = 100
~~~

và:

~~~sql
WHERE status = 'paid'
~~~

đều dùng `WHERE`, nhưng khả năng **loại bớt dữ liệu** rất khác.

### 7.2. Chọn lọc phụ thuộc tập dữ liệu và tham số

`customer_id=42` trong lab trả 12 đơn. Trong production, một số khách có thể có hàng triệu đơn còn khách thường chỉ có vài đơn. Một index tốt cho khách ít đơn có thể không tối ưu cho khách cực nhiều đơn trong mọi workload.

### 7.3. Chọn lọc không chỉ là số hàng cuối

Một điều kiện có thể trả 10 hàng nhưng vẫn quét 60.000 hàng:

~~~sql
WHERE lower(status) = 'paid'
  AND order_id < 11
~~~

Vấn đề không chỉ **bao nhiêu hàng output**, mà **để tìm chúng PostgreSQL phải làm bao nhiêu việc**.

## 8. Ba cấp đo dữ liệu được xử lý

Khi đọc plan, phân biệt:

1. **Rows returned:** số hàng node trả cho node cha.
2. **Rows examined/filtered:** số hàng phải kiểm tra; có thể suy từ `Rows Removed by Filter` cùng output ở một số node.
3. **Pages/blocks touched:** `Buffers: shared hit/read` và các số liệu tương ứng.

Ví dụ plan minh họa:

~~~text
Seq Scan on orders
  (cost=0.00..1700.00 rows=12 width=24)
  (actual time=0.050..7.800 rows=12 loops=1)
  Filter: (customer_id = 42)
  Rows Removed by Filter: 59988
  Buffers: shared hit=900
~~~

**Đây là ví dụ giả định**, không phải output cố định của lab.

Ý nghĩa:

- Node trả **12** hàng.
- Đã loại **59.988** hàng bằng filter.
- Có thể đã xem khoảng **60.000** hàng.
- `shared hit=900` là lượt truy cập block trong shared buffers, **không phải 900 hàng**.

Khi có index tốt, plan có thể thay bằng:

~~~text
Index Scan using idx_orders_customer_created on orders
  (actual ... rows=12 loops=1)
  Index Cond: (customer_id = 42)
  Buffers: shared hit=...
~~~

Điều quan trọng là predicate được dùng để **định vị khóa** thay vì phải so với gần như mọi hàng của bảng.

## 9. EXPLAIN: Index Cond và Filter khác nhau

Xem query:

~~~sql
SELECT order_id, created_at
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Với index thích hợp, plan có thể chứa:

~~~text
Index Cond: (customer_id = 42)
~~~

`Index Cond` cho biết điều kiện được index scan sử dụng trong quá trình tìm kiếm/truy cập.

### 9.1. Filter

~~~text
Filter: (status = 'paid')
Rows Removed by Filter: 5
~~~

Nếu điều kiện nằm ở `Filter` trên scan, nó được kiểm tra trên những tuple/node outputs mà scan đã tiếp cận; nó không nhất thiết đã thu hẹp **phạm vi khóa được scan** giống `Index Cond`.

### 9.2. Index Cond không cam kết mọi điều kiện được lọc tại index

Plan có thể vừa có:

~~~text
Index Cond: (customer_id = 42)
Filter: (status = 'paid')
~~~

Index xác định đơn của khách 42, rồi kiểm tra status. Đây vẫn có thể là plan rất tốt nếu khách chỉ có ít đơn.

### 9.3. Filter cũng có thể nằm ở cấp khác

`Filter` xuất hiện trên Seq Scan, Index Scan, Join, Aggregate hoặc node khác tùy biểu thức. Hãy đọc **node chứa Filter**, không chỉ tìm chữ `Filter` rồi kết luận cả truy vấn đang full scan.

### 9.4. Dùng BUFFERS để xác nhận

Một điều kiện chuyển từ `Filter` toàn bảng sang `Index Cond` có thể giảm block truy cập đáng kể. Nhưng nếu điều kiện khớp 70% hàng, planner có thể vẫn chọn Seq Scan hợp lý.

## 10. Tạo chỉ mục cho điều kiện có chọn lọc

~~~sql
CREATE INDEX idx_orders_customer
ON opt_lab.orders (customer_id);

ANALYZE opt_lab.orders;
~~~

Sau đó thử:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Index có thể giúp PostgreSQL tìm khoảng 12 đơn của khách 42 mà không cần quét toàn bộ 60.000 đơn.

### 10.1. Vì sao không tạo index trên mọi cột?

Index thêm chi phí:

- `INSERT`, `UPDATE`, `DELETE` phải duy trì index liên quan.
- Dung lượng đĩa và cache.
- Bảo trì/VACUUM và hiệu ứng tới throughput ghi.
- Thời gian build/rebuild index và khả năng giữ khóa khi migration.

Chỉ tạo index khi các truy vấn, độ chọn lọc và tần suất thực tế chứng minh lợi ích.

### 10.2. Cột có ít giá trị phân biệt

~~~sql
CREATE INDEX idx_orders_status
ON opt_lab.orders (status);
~~~

`status` chỉ có ba giá trị và `paid` chiếm 70%. Với query `WHERE status='paid'`, nhiều trường hợp PostgreSQL **có lý do chọn Seq Scan** thay vì đi qua index rồi chạm đa số heap rows.

Với `status='cancelled'` khoảng 10%, chỉ mục có thể hấp dẫn hơn, nhưng vẫn tùy bảng/cluster/cache và cột cần lấy.

**Sự tồn tại của index không có nghĩa mọi giá trị lọc đều có lợi từ index.**

## 11. SARGable predicates: viết điều kiện có thể khai thác index

*SARGable* là cách nói thực hành cho các predicate mà cơ chế truy cập có thể chuyển thành tìm kiếm theo cấu trúc index thích hợp.

Ví dụ trên B-tree index `orders(created_at)`:

~~~sql
CREATE INDEX idx_orders_created
ON opt_lab.orders (created_at);
~~~

Điều kiện phù hợp:

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00'
~~~

Vì so sánh đặt trực tiếp trên cột `created_at`, PostgreSQL có cơ hội dùng B-tree range scan.

### 11.1. Hàm bọc quanh cột có thể cản index thông thường

~~~sql
WHERE created_at::date = DATE '2026-02-01'
~~~

Biểu thức làm việc trên **ngày được chuyển đổi từ timestamp**, không phải trực tiếp trên giá trị gốc của index `created_at`. Planner không nhất thiết biến biểu thức này thành khoảng timestamp để dùng index như query ở trên.

### 11.2. Viết lại thành khoảng nửa mở

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00';
~~~

Khoảng **[start, end)** có lợi:

- Bao gồm mọi độ chính xác phần giây trong ngày.
- Không cần tự tính “23:59:59.999999”.
- Các khoảng ngày liên tiếp không chồng nhau.
- Phù hợp B-tree range scan trên `created_at`.

### 11.3. Cẩn thận timezone với timestamptz

`created_at::date` phụ thuộc **session time zone** đối với `timestamptz`, trong khi các literal `+00` ở ví dụ xác định khoảng ngày UTC. Hai cách viết chỉ tương đương nếu yêu cầu nghiệp vụ thật sự là **ngày UTC** và các ranh giới được tính đúng theo timezone cần dùng.

Với ngày theo múi giờ của người dùng, ứng dụng nên tính **hai instant UTC tương ứng với đầu/ngày kế tiếp ở timezone ấy**, chú ý ngày chuyển giờ mùa hè tại các vùng có DST.

Không đổi predicate mà vô tình thay đổi ý nghĩa ngày nghiệp vụ.

## 12. Hàm trên cột: khi nào nên dùng expression index?

Ví dụ tìm sản phẩm không phân biệt hoa/thường:

~~~sql
SELECT product_id, product_name
FROM opt_lab.products
WHERE lower(product_name) = 'sản phẩm 42';
~~~

Index mặc định trên `product_name` không nhất thiết có thể dùng để tìm `lower(product_name)`.

Một lựa chọn:

~~~sql
CREATE INDEX idx_products_lower_name
ON opt_lab.products (lower(product_name));
~~~

Sau đó:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM opt_lab.products
WHERE lower(product_name) = 'sản phẩm 42';
~~~

### 12.1. Tìm cách viết đơn giản trước

Nếu một điều kiện có thể viết thành so sánh trực tiếp trên cột, không nên thêm expression index chỉ để giữ một cách diễn đạt phức tạp không cần thiết.

### 12.2. Expression index có chi phí duy trì

PostgreSQL phải tính biểu thức khi index được xây và khi cập nhật hàng ảnh hưởng. Ngoài ra, biểu thức index phải thỏa yêu cầu về tính bất biến (*immutability*) và ngữ nghĩa phù hợp.

### 12.3. Query phải khớp expression

Index trên `lower(product_name)` có thể phù hợp `WHERE lower(product_name) = ...`; không có quy tắc rằng nó tự xử lý mọi `ILIKE`, `LIKE` hoặc phép biến đổi chuỗi khác.

## 13. LIKE, tiền tố và wildcard đầu chuỗi

Hai điều kiện:

~~~sql
WHERE sku LIKE 'SKU-0001%'
~~~

và:

~~~sql
WHERE sku LIKE '%0001%'
~~~

khác nhau về khả năng định vị qua B-tree:

- `'SKU-0001%'` có **tiền tố cố định**.
- `'%0001%'` bắt đầu bằng wildcard, không có khoảng tiền tố B-tree đơn giản.

### 13.1. Collation và pattern_ops

Tại một số locale không phải `C`, B-tree text mặc định có thể không hỗ trợ tốt prefix `LIKE`. Có thể cân nhắc:

~~~sql
CREATE INDEX idx_products_sku_prefix
ON opt_lab.products (sku text_pattern_ops);
~~~

Nếu chỉ mục mặc định có collation `C` và operator class phù hợp, prefix search có thể đã dùng được. **Không tạo thêm index trùng khi chưa kiểm tra `EXPLAIN` và collation**.

### 13.2. Substring search

Với:

~~~sql
WHERE product_name ILIKE '%phẩm%'
~~~

trigram index từ extension `pg_trgm` có thể là lựa chọn:

~~~sql
-- Chỉ chạy trong lab nếu extension được phép cài.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm
ON opt_lab.products
USING gin (product_name gin_trgm_ops);
~~~

Trigram không bảo đảm nhanh với mọi pattern (đặc biệt pattern quá ngắn) và tăng chi phí ghi/index size. Nếu workload cần full-text search theo ngôn ngữ, cân nhắc cơ chế tìm kiếm khác phù hợp.

### 13.3. Đừng thay đổi ý nghĩa LIKE để lấy index

`LIKE 'ABC%'` khác `LIKE '%ABC%'`. Không được bỏ wildcard đầu chỉ để query nhanh hơn nếu nghiệp vụ thực sự cần substring search.

## 14. Tránh ép kiểu trên cột khóa khi không cần

Giả sử `order_id` là `bigint`:

~~~sql
-- Không nên ép sang text chỉ để so ID.
SELECT order_id
FROM opt_lab.orders
WHERE order_id::text = '100';
~~~

Thay vì:

~~~sql
SELECT order_id
FROM opt_lab.orders
WHERE order_id = 100::bigint;
~~~

Trong trường hợp thứ hai, PostgreSQL có thể dùng B-tree primary key index theo kiểu số.

### 14.1. Điều kiện không sargable không luôn đồng nghĩa Seq Scan

PostgreSQL đôi khi có thể dùng index khác, bitmap scan, expression index, hoặc tối ưu biểu thức; không nên tuyên bố mọi hàm/cast trên cột đều bắt buộc full scan.

Nguyên tắc: **giữ predicate càng gần dạng so sánh trực tiếp lên khóa index càng tốt**, và xác minh plan.

### 14.2. Kiểm tra kiểu tham số của ứng dụng

Prepared statement dùng parameter cần bind đúng kiểu:

~~~sql
PREPARE get_order(bigint) AS
SELECT order_id, customer_id, total_amount
FROM opt_lab.orders
WHERE order_id = $1;
~~~

Điều kiện so sánh số với số dễ dự đoán hơn so với việc định nghĩa ID dạng text rồi ép kiểu cột trong WHERE.

## 15. OR, IN và những cách lọc nhiều giá trị

Một truy vấn:

~~~sql
SELECT order_id, status
FROM opt_lab.orders
WHERE status = 'paid'
   OR status = 'shipped';
~~~

logically tương đương:

~~~sql
SELECT order_id, status
FROM opt_lab.orders
WHERE status IN ('paid', 'shipped');
~~~

Nhưng `IN` không phải thần chú làm mọi query nhanh hơn. Hai giá trị ở đây chiếm tới khoảng **90%** bảng; Seq Scan có thể hợp lý.

### 15.1. OR trên nhiều cột

~~~sql
SELECT order_id
FROM opt_lab.orders
WHERE customer_id = 42
   OR product_id = 17;
~~~

PostgreSQL có thể dùng **BitmapOr** kết hợp những index thích hợp, hoặc chọn scan khác. Điều này phụ thuộc chọn lọc và index thực tế.

### 15.2. Khi tách UNION có ích?

Đôi khi tách hai nhánh có chọn lọc cao bằng `UNION`/`UNION ALL` giúp planner có thêm phương án. Nhưng:

- `UNION` loại trùng, có thêm chi phí.
- `UNION ALL` giữ trùng, có thể đổi kết quả so với OR nếu một hàng thỏa cả hai nhánh.
- Không phải mọi OR đều nên viết lại.

Hãy giữ đúng ngữ nghĩa và đo trên workload.

## 16. NULL và điều kiện chọn lọc

~~~sql
WHERE note IS NULL
~~~

và:

~~~sql
WHERE note = NULL
~~~

**khác nhau**. Trong SQL, so sánh `= NULL` cho kết quả unknown, không chọn các hàng có null như mong muốn.

### 16.1. IS NULL có thể dùng index

B-tree PostgreSQL có thể lưu và hỗ trợ tìm kiếm null theo điều kiện phù hợp; một query `WHERE note IS NULL` không phải lúc nào cũng phải Seq Scan.

### 16.2. COALESCE trên cột làm thay đổi biểu thức

~~~sql
WHERE COALESCE(note, '') = ''
~~~

không giống hệt:

~~~sql
WHERE note IS NULL
~~~

vì điều kiện đầu chọn cả chuỗi rỗng lẫn null. Nếu nghiệp vụ chỉ cần null, dùng `IS NULL`. Nếu cần cả hai, viết rõ:

~~~sql
WHERE note IS NULL OR note = ''
~~~

và cân nhắc index/plan tương ứng, không thay đổi nghĩa chỉ để “dễ dùng index”.

## 17. Chỉ mục ghép: kết hợp WHERE và ORDER BY

Trang lịch sử đơn hàng của một khách:

~~~sql
SELECT
    order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Một chỉ mục định hướng đúng:

~~~sql
CREATE INDEX idx_orders_customer_created
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

### 17.1. Vì sao thứ tự cột như vậy?

1. `customer_id` là điều kiện **equality**.
2. Sau khi cố định một khách, `created_at DESC` là thứ tự mong muốn.
3. `order_id DESC` là khóa phá hòa (tie-breaker) khi hai đơn có cùng thời gian.

Với index phù hợp, PostgreSQL có thể lấy đơn mới nhất của khách theo thứ tự index rồi **dừng sớm** khi đủ `LIMIT`.

### 17.2. Không phải luôn phải thêm DESC

B-tree có thể quét xuôi/ngược. Khi có nhiều cột với hướng hỗn hợp và null placement khác nhau, cách khai báo thứ tự lại quan trọng hơn. Đối với `ORDER BY created_at DESC, order_id DESC`, chỉ mục có đúng hai chiều giảm như trên là dễ hiểu.

### 17.3. Nếu cần lọc status nữa

~~~sql
SELECT order_id, created_at, status
FROM opt_lab.orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Có thể cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON opt_lab.orders (
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Trong truy vấn có equality trên `customer_id` và `status`, index có thể định vị nhóm nhỏ rồi trả hàng đúng thứ tự theo thời gian.

### 17.4. Chọn index theo workload, không theo một câu đơn lẻ

Nếu phần lớn màn hình lọc khách nhưng **không lọc status**, index `(customer_id,status,created_at)` không cung cấp trực tiếp một thứ tự `created_at` toàn bộ các trạng thái của một khách, vì `status` nằm trước.

Hai chỉ mục gần giống nhau có thể có lợi cho hai query patterns, nhưng cũng làm tăng write amplification. Đánh giá tần suất, lượng dữ liệu và query thực tế trước khi giữ cả hai.

## 18. INCLUDE và Index Only Scan

Truy vấn lịch sử đơn cần `status` và `total_amount` nhưng chủ yếu lọc/sort theo các key khác:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Có thể tạo covering index:

~~~sql
CREATE INDEX idx_orders_customer_cover
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, total_amount);
~~~

### 18.1. Key columns vs included columns

| Cột | Vai trò |
| --- | --- |
| `customer_id` | Key tìm equality |
| `created_at` | Key thứ tự |
| `order_id` | Key phá hòa/thứ tự |
| `status` | Payload phục vụ output; không làm key tìm kiếm cho index này |
| `total_amount` | Payload phục vụ output |

`INCLUDE` giúp các giá trị có mặt trong index, nhưng **không** biến `status` thành cột điều kiện index theo cùng cách khi nó là key.

### 18.2. Khi nào Index Only Scan khả thi?

PostgreSQL có thể dùng `Index Only Scan` khi:

- Access method có hỗ trợ.
- Tất cả cột/biểu thức cần thiết có thể lấy từ index theo kế hoạch phù hợp.
- Thông tin visibility map và MVCC cho phép tránh hoặc giảm lần đọc heap.
- Planner đánh giá chi phí có lợi.

### 18.3. Heap Fetches

Một plan có thể hiển thị:

~~~text
Index Only Scan using idx_orders_customer_cover ...
  Heap Fetches: 0
~~~

Đây là dấu hiệu **trong lần đo này** không cần truy cập heap để kiểm tra visibility cho những tuple trả về. Nhưng một `Index Only Scan` khác có thể có **Heap Fetches > 0**, đặc biệt khi bảng thường xuyên cập nhật/chưa có các visibility-map bits phù hợp.

### 18.4. Không khuyến nghị INCLUDE mọi cột

Tăng số cột payload làm index lớn, tốn bộ nhớ đệm và tăng chi phí ghi. Giá trị rộng có thể gây vấn đề kích thước index tuple. Chỉ INCLUDE những cột thiết yếu, xuất hiện thường xuyên trong query thực tế.

## 19. Partial index cho nhóm dữ liệu thực sự cần

Nếu phần lớn truy vấn quan tâm các đơn `paid` gần đây, thay vì index tất cả trạng thái:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON opt_lab.orders (
    created_at DESC,
    order_id DESC
)
WHERE status = 'paid';
~~~

Chỉ mục này chứa các hàng thỏa predicate `status='paid'`, không chứa mọi hàng.

Query phù hợp:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 19.1. Ưu điểm

Partial index có thể nhỏ hơn một full index có cùng key nếu predicate chỉ chọn một phần nhỏ bảng; nó có thể giảm chi phí duy trì trên các hàng không tham gia index.

### 19.2. Predicate trong lab chưa thật chọn lọc

`paid` chiếm **70%** đơn, nên partial index này không phải lúc nào cũng có lợi lớn. Một partial index cho trạng thái hiếm hơn hoặc một bộ dữ liệu thực chỉ có vài phần trăm hàng “active” có thể khác đáng kể.

Không lấy ví dụ lab làm bằng chứng rằng partial index luôn nhỏ hoặc nhanh.

### 19.3. Query phải chứng minh được predicate

PostgreSQL chỉ có thể tận dụng partial index khi planner nhận ra điều kiện query **hàm ý** điều kiện index.

~~~sql
WHERE status = 'paid'
~~~

là trường hợp trực tiếp.

Nhưng prepared statement:

~~~sql
WHERE status = $1
~~~

đặc biệt với **generic plan** không biết trước giá trị `$1`, có thể **không chứng minh được** `status='paid'` cho mọi lần thực thi. Không thiết kế chỉ mục dựa trên giả định mọi tham số được substitute thành literal ở planning time.

### 19.4. Không dùng partial index để cắt bỏ dữ liệu nghiệp vụ

Index partial chỉ thay đổi cấu trúc truy cập, **không xóa các hàng ngoài predicate**. Câu query không thỏa điều kiện vẫn có thể cần đường truy cập khác để trả kết quả đúng.

## 20. WHERE + LIMIT không bảo đảm đọc ít dữ liệu

So sánh hai query:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

và:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE status = 'paid'
ORDER BY total_amount DESC
LIMIT 10;
~~~

Query thứ nhất có thể dùng `(customer_id,created_at,order_id)` để tìm và dừng sớm. Query thứ hai, nếu không có thứ tự index phù hợp trên giá, có thể phải xem **rất nhiều đơn paid** trước khi chọn top 10.

### 20.1. Đọc kế hoạch Sort

Ví dụ minh họa:

~~~text
Limit
  (actual ... rows=10 loops=1)
  -> Sort
       (actual ... rows=10 loops=1)
       Sort Key: total_amount DESC
       Sort Method: top-N heapsort
       -> Seq Scan on orders
            (actual ... rows=42000 loops=1)
            Filter: (status = 'paid')
            Rows Removed by Filter: 18000
~~~

`Sort actual rows=10` **không có nghĩa nó chỉ xem 10 hàng**: child đã cung cấp khoảng 42.000 hàng, và Sort chọn top-N theo yêu cầu của parent.

### 20.2. Index hỗ trợ lọc và thứ tự

Một chỉ mục có thể thử nếu query rất phổ biến:

~~~sql
CREATE INDEX idx_orders_status_amount
ON opt_lab.orders (
    status,
    total_amount DESC,
    order_id DESC
);
~~~

Sau đó query có thể lấy top-N trong nhóm `status` theo thứ tự giá. Nhưng nếu query chỉ dùng tổng tiền mà không lọc status, cột `status` đứng đầu khiến index không đảm bảo thứ tự giá toàn bảng.

## 21. Phân trang: OFFSET có thể buộc đi qua rất nhiều hàng

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 1000;
~~~

Để trả 20 hàng ở vị trí sâu, PostgreSQL thường vẫn phải xử lý/đi qua **các hàng trước vị trí OFFSET** theo cách plan lựa chọn. `LIMIT 20` không giúp bỏ qua miễn phí 1.000 hàng đầu.

### 21.1. Keyset pagination

Đối với trang kế tiếp, nếu client giữ `created_at` và `order_id` cuối của trang trước:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
  AND (created_at, order_id)
      < (
          TIMESTAMPTZ '2026-02-01 12:00:00+00',
          45000::bigint
        )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Với **hai cột NOT NULL** và thứ tự giảm của cả hai, phép so sánh tuple `<` có thể mô tả ranh giới trang tiếp theo, và chỉ mục `(customer_id,created_at DESC,order_id DESC)` phù hợp.

### 21.2. Cursor phải xuất phát từ kết quả thật

Hai giá trị trong query trên chỉ là ví dụ. Trong API thực, lấy chúng từ **dòng cuối của trang trước**, không đoán.

### 21.3. Keyset có đánh đổi

- Phải có thứ tự xác định và khóa phá hòa.
- Xử lý null và sắp xếp hỗn hợp cần điều kiện cursor cẩn thận hơn.
- Không trực tiếp “nhảy tới trang số 500” như OFFSET.
- Dữ liệu thay đổi đồng thời vẫn có thể ảnh hưởng trải nghiệm trang, dù thường tránh được nhiều vấn đề của OFFSET sâu.

### 21.4. Chọn ít cột vẫn quan trọng

Nếu client chỉ hiển thị 20 dòng và bốn cột, đừng truy vấn cả `note` rộng hoặc thực hiện một `JOIN` lớn chỉ để lấy dữ liệu không dùng ở trang danh sách.

## 22. JOIN: lọc đúng phía và tránh mang cột thừa

Một API trả đơn của khách có thể cần tên khách và số tiền:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.full_name
FROM opt_lab.orders AS o
JOIN opt_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id = 42
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

Không cần:

~~~sql
SELECT o.*, c.*
~~~

nếu màn hình chỉ dùng bốn cột.

### 22.1. Filter ở bảng nào?

`o.customer_id = 42` có tính chọn lọc cao. PostgreSQL có thể dùng index trên orders, rồi tìm một khách qua primary key. Truy vấn không nhất thiết phải scan/join tất cả 60.000 đơn với 5.000 khách.

### 22.2. WHERE viết sau JOIN không có nghĩa lọc sau khi join hết

Với **INNER JOIN** và điều kiện có thể đẩy an toàn, planner thường có thể áp dụng predicate ở scan phù hợp trước khi join. Đừng khẳng định hệ quản trị luôn tạo toàn bộ kết quả join rồi mới chạy `WHERE` chỉ vì cú pháp SQL viết JOIN trước WHERE.

### 22.3. OUTER JOIN cần giữ ngữ nghĩa

Ví dụ:

~~~sql
SELECT c.customer_id, o.order_id
FROM opt_lab.customers AS c
LEFT JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
WHERE c.customer_id = 42;
~~~

giữ khách 42 dù không có paid orders (trường hợp không có matching row).

Nhưng:

~~~sql
SELECT c.customer_id, o.order_id
FROM opt_lab.customers AS c
LEFT JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 42
  AND o.status = 'paid';
~~~

có thể loại hàng với `o.status IS NULL` và đổi ý nghĩa của LEFT JOIN theo kiểu gần INNER JOIN đối với điều kiện ấy.

**Không tùy tiện đẩy WHERE sang ON (hoặc ngược lại) qua outer join chỉ để mong nhanh hơn.**

## 23. JOIN nhiều bảng và nguy cơ nhân số hàng

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    p.product_name
FROM opt_lab.customers AS c
JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
JOIN opt_lab.products AS p
  ON p.product_id = o.product_id
WHERE c.customer_id = 42;
~~~

Với lab, khách 42 có 12 đơn và mỗi đơn trỏ tới một sản phẩm; kết quả thường là 12 hàng.

### 23.1. Nếu bảng con có nhiều dòng cho mỗi đơn

Khi thêm bảng `order_lines` và `order_events`, join hai quan hệ một-nhiều vào cùng đơn có thể tạo tích số:

~~~text
1 đơn có:
  5 dòng hàng
  10 sự kiện

JOIN cả hai bảng -> có thể 5 × 10 = 50 dòng
~~~

Hệ quả:

- Nhiều hàng trung gian hơn cần thiết.
- Dữ liệu bị lặp trong kết quả.
- Sort/aggregate tốn tài nguyên.
- Có thể tính tổng sai nếu không hiểu cardinality.

### 23.2. EXISTS khi chỉ cần biết có bản ghi liên quan

Thay vì join để tạo rồi loại trùng những hàng con:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM opt_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM opt_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
~~~

`EXISTS` diễn đạt “có ít nhất một đơn paid”, giúp planner có thể chọn **semijoin** hoặc cách kiểm tra tồn tại mà không cần nhân nhiều bản ghi con vào output.

### 23.3. DISTINCT không phải cách chữa mọi join sai

~~~sql
SELECT DISTINCT c.customer_id
FROM opt_lab.customers AS c
JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'paid';
~~~

có thể trả đúng tập ID nhưng vẫn phải xử lý nhiều hàng join rồi loại trùng. Nếu mục đích là tồn tại, `EXISTS` thường nói đúng ý định hơn; không cam kết luôn nhanh hơn trong mọi workload.

## 24. Lọc trước khi gom nhóm

Giả sử cần tổng tiền đơn đã paid của một khách trong tháng 2:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS total_paid
FROM opt_lab.orders
WHERE customer_id = 42
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY customer_id;
~~~

`WHERE` giảm số hàng trước khi đi vào `GROUP BY`, khi đó aggregate chỉ xử lý phần tập dữ liệu cần thiết.

### 24.1. HAVING không thay WHERE

~~~sql
SELECT customer_id, COUNT(*) AS n
FROM opt_lab.orders
GROUP BY customer_id
HAVING COUNT(*) >= 10;
~~~

`HAVING` lọc **nhóm sau aggregation**. Nếu muốn chỉ tính các đơn paid, đặt điều kiện đó trong `WHERE`:

~~~sql
SELECT customer_id, COUNT(*) AS n_paid
FROM opt_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
HAVING COUNT(*) >= 10;
~~~

Hai dạng giải quyết các yêu cầu khác nhau. Không đưa điều kiện row-level xuống/hay lên sai chỗ làm đổi kết quả.

### 24.2. PostgreSQL có thể dùng FILTER trong aggregate

~~~sql
SELECT
    customer_id,
    COUNT(*) FILTER (WHERE status = 'paid') AS n_paid,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS n_cancelled
FROM opt_lab.orders
WHERE customer_id = 42
GROUP BY customer_id;
~~~

`FILTER` hữu ích để tính nhiều thống kê trên cùng tập input; nó không tự giảm input scan bằng cách giống `WHERE status='paid'` nếu còn cần những trạng thái khác để tính kết quả.

## 25. Predicate pushdown và CTE

PostgreSQL planner có thể đẩy những điều kiện an toàn xuống gần scan để tránh tạo dữ liệu trung gian lớn.

### 25.1. CTE không mặc nhiên là hàng rào tối ưu

~~~sql
WITH recent AS (
    SELECT order_id, customer_id, created_at, status
    FROM opt_lab.orders
)
SELECT order_id, created_at
FROM recent
WHERE customer_id = 42;
~~~

Trong PostgreSQL hiện đại, một CTE không đệ quy, không volatile side effects và dùng một lần thường có thể được **inline/fold** vào query chính, cho phép tối ưu chung.

### 25.2. MATERIALIZED thay đổi cơ hội tối ưu

~~~sql
WITH recent AS MATERIALIZED (
    SELECT order_id, customer_id, created_at, status
    FROM opt_lab.orders
)
SELECT order_id, created_at
FROM recent
WHERE customer_id = 42;
~~~

`MATERIALIZED` có thể cố ý tạo ranh giới vật liệu hóa; filter của query bên ngoài không phải lúc nào cũng được đẩy xuống scan của CTE. Điều này có thể buộc xử lý rất nhiều hàng trước khi cuối cùng chỉ lấy 12.

### 25.3. Không coi mọi MATERIALIZED đều sai

Materialization có thể có lợi khi một kết quả được tái sử dụng hoặc tính toán đắt cần thực hiện một lần. Chọn theo truy vấn thật và plan; **không xóa MATERIALIZED một cách máy móc**.

### 25.4. Viết sớm điều kiện khi giúp diễn đạt mục tiêu

Nếu logic cho phép:

~~~sql
WITH recent AS MATERIALIZED (
    SELECT order_id, customer_id, created_at, status
    FROM opt_lab.orders
    WHERE customer_id = 42
)
SELECT order_id, created_at
FROM recent;
~~~

đã diễn đạt phạm vi lọc trong CTE, tránh vật liệu hóa 60.000 đơn khi chỉ cần một khách.

## 26. Partition pruning: không đọc partition không liên quan

Với bảng cực lớn được **partition theo thời gian**, PostgreSQL có thể loại bỏ các partition nằm ngoài khoảng query, giảm dữ liệu cần scan.

Ví dụ định nghĩa rút gọn dành cho lab:

~~~sql
CREATE TABLE opt_lab.events_by_month (
    event_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    event_type text NOT NULL,
    payload jsonb
) PARTITION BY RANGE (created_at);

CREATE TABLE opt_lab.events_2026_01
PARTITION OF opt_lab.events_by_month
FOR VALUES FROM ('2026-01-01 00:00:00+00')
         TO ('2026-02-01 00:00:00+00');

CREATE TABLE opt_lab.events_2026_02
PARTITION OF opt_lab.events_by_month
FOR VALUES FROM ('2026-02-01 00:00:00+00')
         TO ('2026-03-01 00:00:00+00');
~~~

### 26.1. Query dùng trực tiếp partition key

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM opt_lab.events_by_month
WHERE created_at >= TIMESTAMPTZ '2026-02-10 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-11 00:00:00+00';
~~~

Planner có cơ hội chỉ xét partition tháng 2.

### 26.2. Hàm bọc partition key

~~~sql
WHERE created_at::date = DATE '2026-02-10'
~~~

không phải lúc nào giúp pruning như điều kiện khoảng trực tiếp trên khóa phân vùng. Đặc biệt với `timestamptz` phải kiểm soát timezone.

### 26.3. Partition không thay chỉ mục cho mọi truy vấn

Nếu partition tháng 2 vẫn có hàng trăm triệu bản ghi, query trong một ngày có thể cần index **bên trong partition** hoặc một chiến lược khác. Pruning giảm **số partition** phải xét, không nhất thiết giảm mọi scan còn lại.

### 26.4. Giới hạn dữ liệu lab

Bảng events ở ví dụ chưa được chèn dữ liệu. `EXPLAIN` cho thấy khả năng chọn partition theo điều kiện; performance/`BUFFERS` trên bảng trống không phải bằng chứng tăng tốc thực tế.

## 27. COUNT(*) không phải phép lấy số hàng miễn phí

~~~sql
SELECT COUNT(*)
FROM opt_lab.orders;
~~~

Trong PostgreSQL với MVCC, đếm chính xác tất cả hàng phải xác định những hàng nhìn thấy theo snapshot và thường cần quét một cấu trúc thích hợp. Nó không luôn trả tức thì một “row count” chính xác từ metadata.

### 27.1. Đếm phần nhỏ

~~~sql
SELECT COUNT(*)
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

có thể hưởng lợi từ index trên `customer_id`, vì chỉ cần tìm các mục phù hợp và xác định visibility.

### 27.2. Ước lượng nhanh khác đếm chính xác

~~~sql
SELECT reltuples::bigint AS estimated_rows
FROM pg_class
WHERE oid = 'opt_lab.orders'::regclass;
~~~

`reltuples` là **ước lượng** dựa trên thống kê/cập nhật catalog, không bảo đảm bằng kết quả `COUNT(*)` ở snapshot hiện tại.

### 27.3. API phân trang

Không nhất thiết mỗi request trang phải chạy:

~~~sql
SELECT COUNT(*) FROM huge_table;
~~~

nếu giao diện chỉ cần biết “còn trang sau không”. Có thể lấy `page_size + 1` hàng bằng điều kiện/sort phù hợp để suy có hàng kế tiếp, giữ đúng ngữ nghĩa UX mong muốn.

## 28. Chọn đúng cột ở tầng ứng dụng

Không chỉ SQL cần giảm cột. ORM và API cũng cần tránh **fetch cả entity graph** khi endpoint chỉ dùng vài thuộc tính.

Ví dụ API danh sách đơn:

~~~text
GET /customers/42/orders

Response cần:
  orderId
  createdAt
  status
  totalAmount
~~~

SQL:

~~~sql
SELECT
    order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 28.1. DTO/projection trong ORM

Một projection/DTO query có thể giảm số cột gửi về so với load full entity với trường `note` hoặc quan hệ lazy/eager không cần thiết.

### 28.2. Tránh N+1 queries

Nếu lấy 20 đơn rồi thực hiện 20 query riêng để lấy tên sản phẩm:

~~~text
1 query lấy 20 đơn
20 query lấy từng sản phẩm
-> 21 database round trips
~~~

một query join chọn đúng cột có thể thích hợp hơn:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    p.product_name
FROM opt_lab.orders AS o
JOIN opt_lab.products AS p
  ON p.product_id = o.product_id
WHERE o.customer_id = 42
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

N+1 là vấn đề **số lần truy cập database**, khác nhưng bổ sung cho giảm số hàng/cột. Không thay mọi N+1 bằng một join khổng lồ có row multiplication; chọn phương án phù hợp cardinality.

### 28.3. Không trả dữ liệu nhạy cảm không cần thiết

`SELECT *` trong API có thể vô tình đưa cột mới (ví dụ nội bộ, token, ghi chú vận hành) vào bản trả về nếu mapping không được kiểm soát. Một SELECT-list rõ ràng giúp lập hợp đồng dữ liệu và hạn chế lộ thông tin.

## 29. Khi nào SELECT ít cột giúp Index Only Scan?

Trước khi tạo covering index:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, created_at
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC;
~~~

Nếu đã có index `(customer_id,created_at DESC,order_id DESC)`, toàn bộ các cột query dùng có thể nằm trong khóa index. Planner có thể cân nhắc Index Only Scan.

So với:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC;
~~~

`SELECT *` yêu cầu thêm `product_id`, `status`, `total_amount` và `note`. Index key trên chưa chứa đủ cột; PostgreSQL có thể phải đọc heap hoặc chọn plan khác.

### 29.1. MVCC visibility vẫn quan trọng

Ngay cả khi các cột đều có trong index, PostgreSQL có thể cần heap fetches để xác nhận tuple visibility khi visibility map chưa đánh dấu all-visible cho trang. **Index-only không đồng nghĩa luôn 0 heap reads.**

### 29.2. Index-only không thay thế đo buffer và thời gian

Một index covering rất lớn có thể ngốn nhiều cache và khiến workload ghi chậm hơn. Hãy so sánh `Execution Time`, `Buffers`, `Heap Fetches`, index size và write overhead trước khi đưa vào production.

## 30. Xem thống kê lựa chọn của planner

`ANALYZE` thu thập thống kê cho các cột để planner ước lượng selectivity.

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'opt_lab'
  AND tablename = 'orders'
  AND attname IN (
      'customer_id', 'status', 'created_at'
  )
ORDER BY attname;
~~~

### 30.1. null_frac

Tỷ lệ null ước lượng trong cột. Điều này ảnh hưởng các điều kiện `IS NULL`/`IS NOT NULL` và khả năng chọn index phù hợp.

### 30.2. n_distinct

Thông tin về số giá trị phân biệt ước lượng, theo quy ước của PostgreSQL. Số âm thường biểu thị tỷ lệ tương đối so với số hàng bảng, không phải “số giá trị âm”.

### 30.3. most_common_vals và most_common_freqs

Giúp planner nhận diện các giá trị phổ biến và tần suất ước lượng. Với `status` trong lab, `paid` sẽ rất phổ biến. Planner nhờ đó có thể biết điều kiện paid không lọc nhiều như điều kiện tìm theo một `customer_id` cụ thể.

### 30.4. Giá trị ước lượng không bất biến

Stats chỉ là **mẫu/thông tin thống kê**; sau bulk load/update lớn, cần chạy `ANALYZE` hoặc chờ autovacuum/autonalyze theo cấu hình. Không kết luận query sai từ một estimated rows khác actual rows; sai estimate chủ yếu ảnh hưởng lựa chọn plan.

## 31. Extended statistics và điều kiện nhiều cột

Giả sử trong dữ liệu thật, `status` và `region` hoặc `customer_id` có tương quan mạnh. Planner ước lượng các điều kiện đa cột đôi khi chưa chính xác nếu chỉ dựa trên thống kê độc lập từng cột.

Trên cùng bảng, có thể tạo extended statistics:

~~~sql
CREATE STATISTICS st_orders_customer_status
    (dependencies, mcv)
ON customer_id, status
FROM opt_lab.orders;

ANALYZE opt_lab.orders;
~~~

### 31.1. Không phải phép tăng tốc trực tiếp

`CREATE STATISTICS` không tạo index và không giảm block reads trực tiếp. Nó **cung cấp thêm thông tin cho planner** để chọn cách đọc dữ liệu tốt hơn ở một số dạng query.

### 31.2. Giới hạn

Hiệu quả phụ thuộc dạng predicate, độ tương quan và phiên bản PostgreSQL. Extended statistics **không tự giải quyết mọi loại sai lệch ước lượng join**. Nếu query chủ yếu dùng một khách với 12 đơn đều nhau, lợi ích có thể rất nhỏ trong lab.

## 32. Prepared statements: giá trị parameter ảnh hưởng plan

Một prepared statement:

~~~sql
PREPARE recent_orders(bigint) AS
SELECT
    order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = $1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Có thể chạy:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE recent_orders(42);
~~~

### 32.1. Generic plan và custom plan

PostgreSQL có thể dùng kế hoạch phụ thuộc giá trị parameter (custom) hoặc kế hoạch chung (generic) tùy ngữ cảnh và chính sách. Nếu phân bố dữ liệu skew mạnh, một generic plan có thể không tối ưu cho mọi giá trị.

### 32.2. Partial index và parameter

Một partial index `WHERE status='paid'` không được giả định luôn dùng cho `WHERE status=$1`: generic plan không thể chứng minh mọi giá trị param đều là paid.

### 32.3. Không hardcode tất cả tham số

Bind parameters vẫn là lựa chọn quan trọng cho bảo mật và tính đúng. Tối ưu plan cần dựa trên công cụ/driver, phân bố dữ liệu và đo đạc; không dùng string concatenation để đổi plan mà tạo SQL injection risk.

## 33. EXPLAIN (ANALYZE, BUFFERS): quy trình đo đúng

Trước hết đo baseline:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Sau đó đo query tối giản:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Tiếp theo, với index thích hợp:

~~~sql
CREATE INDEX IF NOT EXISTS idx_orders_customer_created
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);

ANALYZE opt_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 33.1. Những số liệu nên ghi

| Thước đo | Cần xem |
| --- | --- |
| `Execution Time` | Thời gian thực thi toàn statement được EXPLAIN báo cáo |
| `Planning Time` | Thời gian lập kế hoạch |
| `actual rows` | Hàng trả từ node; xem cùng `loops` |
| `loops` | Số lần node chạy |
| `Rows Removed by Filter` | Hàng bị filter loại |
| `Index Cond` | Predicate được đẩy vào đường truy cập index |
| `Buffers: shared hit/read` | Footprint truy cập block logic |
| `Sort` / `Sort Method` | Có phát sinh sort hoặc spill không |
| `Heap Fetches` | Với Index Only Scan, số lần phải lấy heap để xác minh visibility |
| `width` | Ước lượng kích thước output row |

### 33.2. Hãy xem Buffers chứ không chỉ duration

Một query có thể chạy nhanh do toàn bộ trang nằm trong cache nhưng vẫn truy cập rất nhiều block. Dưới tải thật, footprints ấy có thể tranh cache và tài nguyên với các query khác.

### 33.3. Read không phải disk seek

`shared read` báo block được đọc vào shared buffers khi cần, **không đồng nghĩa mỗi block là một lần đọc vật lý từ đĩa** vì còn OS cache và I/O coalescing.

### 33.4. Buffers ở node cha thường bao gồm con

Không cộng tất cả `Buffers` từ root xuống leaf như những con số độc lập; bạn có thể **đếm trùng**.

### 33.5. Actual rows và loops

Trong `EXPLAIN ANALYZE` dạng text, `actual rows` thường là **trung bình mỗi loop**. Với inner index scan `rows=12 loops=1000`, tổng output tích lũy xấp xỉ 12.000 hàng, không phải 12.

## 34. Đo mạng và kích thước kết quả

`EXPLAIN (ANALYZE, BUFFERS)` cho biết công việc trên server nhưng **không tự đo đầy đủ số byte truyền tới client cho kết quả thực tế** như một truy vấn bình thường.

Một số cách tiếp cận:

1. Tại ứng dụng, ghi số hàng và kích thước serialized response (ví dụ JSON bytes), có loại bỏ thông tin nhạy cảm.
2. So sánh latency server với latency end-to-end qua nhiều lần chạy, cùng network và cùng mức tải.
3. Trên database lab, thử lấy 20, 200, 2.000 hàng bằng cùng projection rồi quan sát throughput và chi phí mapping.
4. Chú ý JSON encoding, text encoding, compression, object allocations và database driver.

### 34.1. Không dùng pg_column_size làm số byte mạng

~~~sql
SELECT
    pg_column_size(description) AS storage_bytes
FROM opt_lab.products
WHERE product_id = 42;
~~~

`pg_column_size` cho thông tin về cách giá trị được lưu bên trong PostgreSQL, **không phải chiều dài chính xác của JSON/HTTP response** hoặc số byte trên wire protocol.

### 34.2. Một phép tính minh họa

Giả sử API trả **1.000 hàng × 2 KB/hàng ≈ 2 MB** payload. Khi chỉ cần bốn cột với tổng trung bình **150 B/hàng**, output có thể giảm xuống khoảng **150 KB** trước những overhead như JSON field names và framing.

Đây là phép tính minh họa, không phải đo đạc bảng lab. Tác động tới latency còn phụ thuộc kết nối, nén, throughput và serialization.

## 35. Khi index không được chọn dù WHERE chọn lọc

Có index nhưng plan vẫn:

~~~text
Seq Scan on orders
~~~

Các nguyên nhân cần cân nhắc:

- Bảng nhỏ; Seq Scan rẻ hơn.
- Predicate thực sự trả tỷ lệ lớn hàng.
- Statistics chưa cập nhật hoặc phân bố dữ liệu khác giả định.
- Query có biểu thức/ép kiểu/collation không khớp index.
- Index không hỗ trợ đủ thứ tự `ORDER BY`, planner chọn scan+sort.
- Bitmap/Seq Scan rẻ hơn Index Scan do nhiều random heap fetches.
- Data cache, cost parameters và parallelism làm thay đổi so sánh.
- Partial index predicate không được planner chứng minh từ query.

### 35.1. Không coi enable_seqscan=off là giải pháp production

Có thể điều chỉnh các tham số planner trong lab để hiểu lựa chọn, nhưng việc tắt `enable_seqscan` không sửa bản chất dữ liệu/index và có thể gây plan tệ ở query khác.

### 35.2. Không tối ưu từ bảng mười hàng

Tập dữ liệu nhỏ có thể khiến mọi query đều nhanh. Lab 60.000 orders chỉ giúp thể hiện khác biệt; production benchmark nên dùng kích thước, skew, tỷ lệ null, tần suất ghi và cache tương tự hệ thống thật.

## 36. Chi phí của việc giảm dữ liệu quá mức

Tối ưu không có nghĩa chia mọi truy vấn thành nhiều query nhỏ. Ví dụ:

~~~text
1 query lấy 20 đơn với 4 cột
+ 20 query lấy status từng đơn
= 21 round trips
~~~

có thể tệ hơn một query lấy đủ năm cột cần thiết.

### 36.1. Chọn “đủ cột cho use case”

Nếu API phải hiển thị tên sản phẩm, đừng cố tránh JOIN chỉ để có SELECT-list ngắn hơn nhưng lại gọi thêm 20 lần đến DB.

### 36.2. Đừng đánh đổi tính đúng

Không bỏ điều kiện permission/tenant chỉ vì nó khó dùng index. Không thay `LEFT JOIN` thành `INNER JOIN` nếu nghiệp vụ cần giữ hàng thiếu đối tượng liên quan. Không cắt `LIMIT` khiến export mất dữ liệu.

### 36.3. Data minimization phải phù hợp bản quyền truy cập

Đối với hệ thống multi-tenant, predicate:

~~~sql
WHERE tenant_id = $1
~~~

vừa là điều kiện chọn lọc, vừa có thể là thành phần của bảo vệ truy cập. Tối ưu phải giữ nguyên chính sách phân quyền/RLS phù hợp và không suy rằng chỉ có index là đủ đảm bảo an toàn.

## 37. Những lỗi thường gặp

### Lỗi 1: SELECT * trên đường nóng

Trả thêm dữ liệu rộng, tăng network/serialization và có thể mất cơ hội index-only scan. Chỉ lấy cột cần cho chức năng.

### Lỗi 2: Nghĩ ít cột sẽ luôn giảm heap reads

Nếu vẫn Seq Scan toàn bảng, số trang heap quét có thể gần như không đổi. Đo `Buffers` và loại scan.

### Lỗi 3: Nghĩ WHERE nào cũng chọn lọc

`WHERE status='paid'` với paid chiếm 70% không tương đương `WHERE order_id=42`.

### Lỗi 4: Bọc cột timestamp bằng ::date

Có thể khiến index trên timestamp gốc không dùng được trực tiếp; cân nhắc khoảng nửa mở với timezone đúng.

### Lỗi 5: Lấy cuối ngày bằng 23:59:59

Có thể bỏ sót microseconds. Dùng `>= start AND < next_day_start`.

### Lỗi 6: Ép order_id sang text

Biểu thức `order_id::text` khác index trên bigint; bind tham số theo đúng kiểu.

### Lỗi 7: Dùng LIKE '%text%' rồi mong B-tree prefix tối ưu

Wildcard đầu khiến thiếu tiền tố cố định. Cân nhắc trigram/full-text theo workload.

### Lỗi 8: Dùng lower(column) nhưng chỉ có index column

Có thể cần expression index khớp `lower(column)`.

### Lỗi 9: Tạo index cho mọi cột có WHERE

Index nhiều tốn write/storage; chọn theo tần suất, selectivity và kết quả EXPLAIN.

### Lỗi 10: Cho rằng Seq Scan luôn là lỗi

Quét tuần tự có thể là plan đúng và rẻ nhất khi bảng nhỏ hoặc nhiều hàng được chọn.

### Lỗi 11: Bỏ qua ORDER BY khi chọn index

Một index chỉ hỗ trợ WHERE có thể vẫn phải sort hàng chục nghìn dòng. Thiết kế index theo `WHERE + ORDER BY + LIMIT`.

### Lỗi 12: Để status trước created_at trong mọi query

`(customer_id,status,created_at)` không tự cung cấp thứ tự created_at giữa nhiều status của cùng một khách.

### Lỗi 13: Nghĩ INCLUDE columns là key columns

`INCLUDE(status)` có ích cho output/covering, nhưng không tương đương index key `status` về tìm kiếm và thứ tự.

### Lỗi 14: Nghĩ Index Only Scan luôn không đụng heap

Visibility map/MVCC có thể khiến `Heap Fetches > 0`.

### Lỗi 15: Partial index luôn dùng với bind parameter

Generic plan có thể không chứng minh tham số sẽ khớp predicate partial index.

### Lỗi 16: LIMIT 20 nghĩa chỉ đọc 20 hàng

Sort/aggregate/scan bên dưới vẫn có thể xử lý toàn bảng.

### Lỗi 17: OFFSET sâu gần như miễn phí

Executor có thể phải đi qua rất nhiều hàng trước trang cần trả. Cân nhắc keyset pagination.

### Lỗi 18: Dùng DISTINCT để che join nhân hàng

Vấn đề cardinality vẫn có thể làm join rất nặng. Dùng EXISTS khi cần kiểm tra tồn tại.

### Lỗi 19: Đẩy predicate qua LEFT JOIN làm đổi kết quả

Predicate ở ON và WHERE có thể khác semantics. Luôn bảo đảm tính đúng.

### Lỗi 20: HAVING cho điều kiện row-level

Khi muốn chỉ tổng hợp paid orders, lọc bằng WHERE trước grouping nếu phù hợp ngữ nghĩa.

### Lỗi 21: Mặc định CTE luôn materialize

PostgreSQL hiện đại có thể inline CTE thích hợp. `MATERIALIZED` là lựa chọn có chủ đích và có thể ngăn pushdown.

### Lỗi 22: Đếm COUNT(*) theo metadata

`reltuples` là ước lượng; đếm chính xác theo MVCC không luôn miễn phí.

### Lỗi 23: Chỉ nhìn Execution Time một lần

Cache, concurrency, instrumentation và random variation ảnh hưởng. So sánh cả buffers và nhiều lần đo.

### Lỗi 24: Ép planner dùng index vì index đã tạo

Lợi ích phải được xác minh bằng số liệu. Không tắt Seq Scan toàn cục để “cứu” một query.

### Lỗi 25: Chỉ giảm SQL columns mà quên API/ORM

Nếu ORM vẫn load quan hệ lớn hoặc API serialize full entity, lợi ích end-to-end có thể giảm.

## 38. Bài tập thực hành

Làm trên `opt_lab`. Các bài tạo index hoặc chạy `ANALYZE` chỉ dành cho database lab; không thực hiện DDL tùy tiện trên hệ thống dùng chung.

### Bài 1. Projection

Viết query chỉ trả `order_id`, `created_at`, `status` và `total_amount` của khách 42, thay vì `SELECT *`.

### Bài 2. Selectivity

Với 60.000 đơn, `customer_id=42` trả 12 hàng và `status='paid'` trả 42.000 hàng. Predicate nào chọn lọc hơn? Tính tỷ lệ.

### Bài 3. Width

Hai kế hoạch có `width=250` và `width=40` nhưng cùng `Seq Scan` toàn bảng. Có được khẳng định truy vấn thứ hai đọc ít hơn 6,25 lần số heap blocks không?

### Bài 4. Wide column

Vì sao bỏ `description` khỏi SELECT có thể giúp hiệu năng, nhưng không đảm bảo heap pages giảm nếu quét toàn bảng?

### Bài 5. EXPLAIN

Viết `EXPLAIN (ANALYZE, BUFFERS)` để đo query lọc `customer_id=42`. Cần xem những trường nào?

### Bài 6. Index Cond

Giải thích khác biệt giữa `Index Cond: (customer_id=42)` và `Filter: (customer_id=42)` trong plan.

### Bài 7. Range timestamp

Viết query tìm đơn thuộc **ngày UTC 2026-02-01** bằng khoảng `created_at` nửa mở.

### Bài 8. Timezone

Vì sao `created_at::date = DATE '2026-02-01'` có thể khác một khoảng UTC cố định?

### Bài 9. Expression index

Viết index phù hợp `WHERE lower(product_name) = 'sản phẩm 42'`.

### Bài 10. LIKE prefix

`sku LIKE 'SKU-0001%'` khác `sku LIKE '%0001%'` thế nào về khả năng sử dụng B-tree?

### Bài 11. Status index

Tại sao planner có thể không dùng index trên status khi lọc paid chiếm 70% bảng?

### Bài 12. Index ghép

Thiết kế index cho query lọc customer_id, sort theo `created_at DESC, order_id DESC` và LIMIT.

### Bài 13. Hai query patterns

Nếu một API luôn lọc status còn API khác không lọc, index `(customer_id,status,created_at)` có đủ cho mọi query sắp theo created_at không?

### Bài 14. INCLUDE

Viết covering index cho trang lịch sử đơn cần `order_id, created_at, status, total_amount` và lọc customer_id.

### Bài 15. Heap Fetches

Vì sao một `Index Only Scan` vẫn có thể báo `Heap Fetches=100`?

### Bài 16. Partial index

Tạo partial index tìm đơn paid mới nhất. Vì sao prepared query `status=$1` có thể không luôn dùng index đó?

### Bài 17. LIMIT

Một plan có `Limit rows=10`, `Sort rows=10` nhưng child `Seq Scan rows=42000`. Sort có thực sự chỉ xem 10 hàng không?

### Bài 18. OFFSET

Lý do `LIMIT 20 OFFSET 100000` có thể đắt dù chỉ trả 20 hàng?

### Bài 19. Keyset pagination

Viết điều kiện cursor cho thứ tự `created_at DESC, order_id DESC` khi hai cột đều NOT NULL.

### Bài 20. JOIN projection

Viết query trả mã đơn, ngày tạo, tiền và tên khách của customer 42, không dùng `o.*, c.*`.

### Bài 21. EXISTS

Viết query lấy danh sách khách có ít nhất một đơn paid mà không cần nhân nhiều hàng đơn vào output.

### Bài 22. LEFT JOIN

Khác biệt giữa đặt `o.status='paid'` ở `ON` và ở `WHERE` của LEFT JOIN là gì?

### Bài 23. HAVING

Viết query đếm paid orders theo khách và chỉ trả khách có từ 10 paid orders.

### Bài 24. CTE

Vì sao `WITH x AS MATERIALIZED (SELECT ... FROM orders) SELECT ... FROM x WHERE customer_id=42` có thể phải xử lý nhiều dữ liệu hơn CTE được inline?

### Bài 25. Partition pruning

Truy vấn trên bảng partition theo created_at nên viết điều kiện như thế nào để PostgreSQL có cơ hội loại partition không liên quan?

### Bài 26. COUNT

`pg_class.reltuples` có thay hoàn toàn `SELECT COUNT(*)` khi cần số hàng chính xác theo snapshot không?

### Bài 27. pg_stats

Viết query xem `null_frac`, `n_distinct` và `most_common_freqs` của cột status.

### Bài 28. Extended statistics

Tại sao extended statistics có thể giúp planner mà không trực tiếp tạo index hoặc giảm trang đọc?

### Bài 29. Prepared statement

Một custom plan và generic plan có thể khác nhau ra sao khi customer_id có phân bố rất lệch?

### Bài 30. N+1

Tại sao giảm số cột nhưng gọi thêm 20 queries để lấy tên sản phẩm có thể khiến API chậm hơn?

## 39. Lời giải tham khảo

### Bài 1. Chọn đúng cột

~~~sql
SELECT order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC;
~~~

### Bài 2. Tính selectivity

`customer_id=42`: `12/60000 = 0,0002 = 0,02%`. `status='paid'`: `42000/60000 = 70%`. Điều kiện customer_id chọn lọc hơn.

### Bài 3–4. Projection khác physical scan

Không. `width` là ước lượng byte output/hàng; khi cả hai vẫn quét toàn bảng, heap blocks được truy cập có thể gần nhau. Bỏ description giảm dữ liệu xử lý/serialize, có thể tránh xử lý TOAST và tạo cơ hội index-only scan.

### Bài 5. Đo baseline

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Xem `Execution Time`, loại scan, estimated/actual rows, `loops`, `Index Cond`, `Filter`, `Rows Removed by Filter` và `Buffers`.

### Bài 6. Index Cond vs Filter

`Index Cond` được index access path sử dụng để tìm/giới hạn vị trí; `Filter` được kiểm tra trên các tuple mà node đã tiếp cận. Một query có thể có cả hai.

### Bài 7. Ngày UTC

~~~sql
SELECT order_id, created_at
FROM opt_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00';
~~~

### Bài 8. Timezone

`timestamptz::date` được diễn giải theo session time zone; khoảng +00 được định nghĩa theo UTC. Cần tính ranh giới phù hợp ngày nghiệp vụ trước khi thay đổi điều kiện.

### Bài 9. Expression index

~~~sql
CREATE INDEX idx_products_lower_name_answer
ON opt_lab.products (lower(product_name));
~~~

### Bài 10–11. Prefix và selectivity

`'SKU-0001%'` có tiền tố cố định nên có thể dùng B-tree phù hợp, `'%0001%'` không có tiền tố. Lọc paid 70% dữ liệu có thể khiến Seq Scan rẻ hơn index.

### Bài 12. Composite index

~~~sql
CREATE INDEX idx_orders_history_answer
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

### Bài 13. Trạng thái nằm giữa

Không. Khi không cố định status, các hàng được nhóm theo status trước created_at, nên không nhất thiết có thứ tự created_at chung cho tất cả trạng thái của một khách.

### Bài 14. Covering index

~~~sql
CREATE INDEX idx_orders_cover_answer
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, total_amount);
~~~

### Bài 15. MVCC

Visibility map chưa chứng minh trang chứa tuple là all-visible; PostgreSQL vẫn phải lấy heap để xác minh visibility dù cột dữ liệu đã có trong index.

### Bài 16. Partial index

~~~sql
CREATE INDEX idx_orders_paid_answer
ON opt_lab.orders (created_at DESC, order_id DESC)
WHERE status = 'paid';
~~~

Generic plan với `status=$1` không thể giả định tham số luôn là paid để chứng minh predicate của partial index.

### Bài 17–18. LIMIT/OFFSET

Sort có thể nhận 42.000 hàng để chọn top 10. OFFSET 100.000 thường vẫn phải đi qua số lượng lớn hàng trước vị trí trang, không bỏ qua chúng miễn phí.

### Bài 19. Cursor

~~~sql
SELECT order_id, created_at
FROM opt_lab.orders
WHERE customer_id = 42
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-02-01 12:00:00+00', 45000::bigint)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Trong API, cursor phải lấy từ dòng cuối của trang trước; ví dụ dùng literal minh họa.

### Bài 20. JOIN projection

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.full_name
FROM opt_lab.orders AS o
JOIN opt_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id = 42;
~~~

### Bài 21. EXISTS

~~~sql
SELECT c.customer_id, c.full_name
FROM opt_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM opt_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
~~~

### Bài 22. Outer join

Điều kiện trong `ON` giới hạn các hàng orders có thể match và giữ khách bên trái nếu không có match. Đặt `o.status='paid'` trong `WHERE` loại hàng null-extended và có thể đổi ý nghĩa thành kiểu gần INNER JOIN.

### Bài 23. WHERE trước GROUP BY

~~~sql
SELECT customer_id, COUNT(*) AS paid_orders
FROM opt_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
HAVING COUNT(*) >= 10;
~~~

### Bài 24. MATERIALIZED CTE

Materialization có thể cần tạo tập orders lớn trước khi áp điều kiện ở query ngoài; CTE được inline có thể cho planner đẩy `customer_id=42` xuống scan. Không phải CTE nào cũng nên inline khi kết quả được dùng nhiều lần.

### Bài 25. Partition key range

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-02-10 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-11 00:00:00+00'
~~~

### Bài 26. COUNT chính xác

Không. `reltuples` là ước lượng; `COUNT(*)` thực hiện đếm theo những hàng nhìn thấy trong snapshot và plan thực thi tương ứng.

### Bài 27. Thống kê

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'opt_lab'
  AND tablename = 'orders'
  AND attname = 'status';
~~~

### Bài 28. Extended statistics

Nó cải thiện thông tin ước lượng cho planner đối với một số mối liên hệ giữa cột, có thể gián tiếp giúp chọn plan/index/join tốt hơn. Nó không phải access path mới.

### Bài 29. Custom/generic plan

Custom plan có thể xét giá trị customer_id cụ thể và ước lượng số đơn theo phân bố; generic plan dùng chiến lược tổng quát có thể kém cho giá trị cực phổ biến hoặc cực hiếm.

### Bài 30. N+1 round trips

Số lượt gửi SQL và nhận kết quả qua mạng tăng, cũng như overhead parse/execute và pool. Một query JOIN lấy đúng cột có thể giảm round trips; song cần tránh join tạo nhiều hàng trùng hoặc payload quá rộng.

## 40. Bảng tra cứu nhanh

| Mục tiêu | Hướng xử lý |
| --- | --- |
| Không lấy cột không dùng | `SELECT col1, col2, ...` thay vì mặc định `SELECT *` |
| Giảm hàng cần scan | Predicate chọn lọc, index/partition pruning phù hợp |
| Giảm dữ liệu mạng | Cột đủ dùng, số hàng cần dùng, mapping/serialization phù hợp |
| Lọc theo khóa chính | `WHERE id = ...`, B-tree PK |
| Lọc theo khách | Index `(customer_id)` hoặc composite |
| Lọc ngày/timestamp | Khoảng nửa mở `>= start AND < end` |
| Dùng hàm trên cột | Viết lại predicate hoặc expression index thích hợp |
| LIKE prefix | B-tree với opclass/collation phù hợp |
| ILIKE substring | `pg_trgm` GIN/GiST khi workload hợp lý |
| Lọc và sắp xếp | Composite B-tree khớp `WHERE + ORDER BY` |
| Output nhỏ từ index | `INCLUDE` và Index Only Scan khi MVCC cho phép |
| Chỉ một trạng thái cần index | Partial index với predicate khớp query |
| Danh sách trang gần nhất | `ORDER BY ... LIMIT` với index đúng thứ tự |
| Phân trang sâu | Keyset/cursor pagination |
| Kiểm tra tồn tại hàng con | `EXISTS` / semijoin khi đúng ngữ nghĩa |
| Giảm input aggregate | `WHERE` trước `GROUP BY` khi hợp lý |
| Lọc nhóm | `HAVING` đúng ngữ nghĩa |
| CTE làm mất pushdown | Kiểm tra `MATERIALIZED` vs inlining |
| Bảng partition theo thời gian | Điều kiện khoảng trực tiếp trên partition key |
| Đếm chính xác | `COUNT(*)` theo snapshot; không coi metadata là kết quả đúng |
| Ước lượng số hàng | `pg_stats`, `ANALYZE`, extended statistics phù hợp |
| Kiểm tra kế hoạch | `EXPLAIN (ANALYZE, BUFFERS)` |
| Đọc lượng việc | `actual rows`, `loops`, `Rows Removed by Filter`, `Buffers` |
| Đọc cơ chế lọc | `Index Cond` so với `Filter` |

## 41. Checklist trước khi tối ưu một câu SQL

1. API hoặc báo cáo **thực sự cần những cột nào**?
2. Có cột `text`/`jsonb` rộng đang được lấy nhưng không dùng?
3. Query cần trả bao nhiêu dòng, có cần `LIMIT` đúng nghĩa không?
4. `WHERE` có chọn lọc hay chọn gần toàn bộ bảng?
5. Predicate có so sánh trực tiếp với khóa index được không?
6. Có hàm/cast quanh cột làm khó index hoặc partition pruning không?
7. Điều kiện thời gian có dùng [start, end) và timezone đúng không?
8. `LIKE` có tiền tố cố định hay bắt đầu bằng wildcard?
9. Index nào có thể hỗ trợ **cả điều kiện lọc lẫn thứ tự**?
10. `INCLUDE` có thực sự giúp index-only scan và xứng đáng chi phí ghi?
11. Partial index predicate có được query chứng minh không?
12. `LEFT JOIN`/`INNER JOIN`/`EXISTS` có giữ nguyên ngữ nghĩa không?
13. Có row multiplication hoặc N+1 query không?
14. `GROUP BY` có phải xử lý nhiều hàng vì thiếu WHERE cần thiết?
15. `LIMIT` có thực sự dừng scan sớm, hay Sort vẫn quét hàng lớn?
16. `OFFSET` có quá sâu cho workload phân trang không?
17. Có partition key predicate phù hợp để pruning không?
18. Planner statistics có được cập nhật và phản ánh skew không?
19. `EXPLAIN` cho thấy `Index Cond`, `Filter` và `BUFFERS` như thế nào?
20. Kết quả SQL sau tối ưu có **đúng và đầy đủ** như trước không?

## 42. Tổng kết

Giảm dữ liệu đọc trong PostgreSQL không có nghĩa chỉ thêm `WHERE` hoặc đổi `SELECT *` thành một danh sách ngắn hơn. Cần tách ba mục tiêu:

1. **Lấy đúng cột:** giảm output width, xử lý dữ liệu rộng, network và serialization; tạo cơ hội cho covering/index-only scans. Việc này **không tự giảm heap blocks** nếu vẫn quét toàn bảng.
2. **Đọc đúng những dòng cần thiết:** viết predicate chọn lọc, sargable, đúng kiểu và timezone; tạo access path như B-tree, expression/partial/composite indexes hoặc partition pruning khi phù hợp. `Index Cond` và `Rows Removed by Filter` cho biết PostgreSQL đang tìm hay đang lọc sau khi đọc.
3. **Không tạo dữ liệu trung gian thừa:** kết hợp `WHERE + ORDER BY + LIMIT`, dùng `EXISTS` khi chỉ cần kiểm tra tồn tại, tránh row multiplication, lọc trước aggregate khi đúng nghĩa, xem lại CTE materialization và phân trang bằng cursor khi phù hợp.

Điều quyết định cuối cùng là **đo trên kế hoạch thật**. Với `EXPLAIN (ANALYZE, BUFFERS)`, hãy xem node nào đọc nhiều hàng, node nào loại hàng bằng Filter, index nào được chọn, bao nhiêu buffer được chạm và thời gian thay đổi qua các lần chạy tương đương.

Khi nhìn vào một API chậm, hãy bắt đầu bằng hai câu hỏi rất cụ thể: **“Người dùng cần những cột và những hàng nào?”** và **“PostgreSQL phải đọc/kiểm tra bao nhiêu dữ liệu để trả đúng phần ấy?”**. Từ đó mới chọn cách viết lại SQL, thiết kế index và điều chỉnh thống kê để giảm công việc thực tế mà không thay đổi kết quả nghiệp vụ.

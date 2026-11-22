# Đánh giá lược đồ theo truy vấn, ràng buộc và tốc độ tăng dữ liệu trong PostgreSQL

Một lược đồ (*schema*) PostgreSQL có thể hợp lệ về cú pháp, các bảng đã tạo thành công và ứng dụng chạy được với vài trăm bản ghi, nhưng vẫn **chưa phải thiết kế phù hợp để vận hành lâu dài**. Sau một năm, bảng đơn hàng có thể tăng lên hàng chục triệu dòng; câu truy vấn “20 đơn gần nhất” trở nên chậm; nhiều chỉ mục làm tốc độ ghi giảm; hoặc dữ liệu sai xuất hiện vì quy tắc nghiệp vụ chỉ được kiểm tra ở phía ứng dụng.

Đánh giá lược đồ không nên dừng ở câu hỏi **“bảng đã chuẩn hóa chưa?”**. Cần xem xét đồng thời:

1. **Truy vấn và cách sử dụng dữ liệu:** hệ thống đọc gì, lọc theo cột nào, nối bảng nào, sắp xếp và phân trang ra sao, tần suất và độ trễ mong muốn.
2. **Ràng buộc và tính nhất quán:** những trạng thái nào được phép tồn tại, khóa chính/ngoại có bảo vệ được quan hệ dữ liệu không, thao tác cập nhật và xóa có an toàn không.
3. **Tăng trưởng và vòng đời dữ liệu:** số hàng, kích thước bảng/chỉ mục, tỷ lệ ghi/xóa, dữ liệu lịch sử, retention, vacuum, sao lưu và nhu cầu mở rộng.

Bài học sử dụng PostgreSQL hiện đại (chẳng hạn PostgreSQL 16) để xây một lược đồ đơn hàng nhỏ, sau đó đặt các câu hỏi đánh giá như khi chuẩn bị triển khai một hệ thống thật. Ví dụ gồm DDL, truy vấn ứng dụng, `EXPLAIN`, catalog thống kê và các phương án cải tiến. Những con số dung lượng và lưu lượng được ghi rõ là **giả định để tính toán**, không phải benchmark thực tế.

## 1. Lược đồ tốt phải phục vụ một workload cụ thể

**Workload** là tập các thao tác mà hệ thống thực sự thực hiện: đọc, thêm, sửa, xóa, tổng hợp, xuất báo cáo và truy vấn phục vụ tính năng.

Hai ứng dụng dùng cùng một bảng `orders` có thể cần thiết kế khác nhau:

- **Ứng dụng giao dịch:** mỗi giây tạo nhiều đơn, đọc một đơn theo ID, xem 20 đơn gần nhất của khách hàng và cập nhật trạng thái thanh toán.
- **Hệ thống phân tích:** thường quét lượng lớn dữ liệu lịch sử để tổng hợp doanh thu theo ngày, sản phẩm hoặc khu vực.

Với ứng dụng giao dịch, chỉ mục B-tree phù hợp điều kiện lọc và `ORDER BY` có thể quan trọng. Với công việc quét dữ liệu lịch sử lớn, cách tổ chức theo thời gian, tổng hợp sẵn hoặc một kho phân tích riêng có thể đáng cân nhắc hơn.

### Ba tiêu chí phải được cân bằng

~~~text
                    TRUY VẤN
             lọc, JOIN, ORDER BY
                    /      \
                   /        \
                  /          \
         RÀNG BUỘC ---------- TĂNG TRƯỞNG
       dữ liệu hợp lệ        dung lượng, tốc độ ghi,
       khóa, quan hệ         vacuum, retention
~~~

Ví dụ, thêm nhiều chỉ mục có thể giúp truy vấn nhanh hơn nhưng làm `INSERT` và `UPDATE` tốn công bảo trì hơn. Tách dữ liệu thành nhiều bảng có thể bảo vệ quan hệ và tránh lặp dữ liệu, nhưng cũng tạo thêm `JOIN`. Lưu tổng tiền đơn hàng giúp đọc nhanh nhưng phải có cơ chế giữ nó nhất quán với chi tiết đơn.

**Không có một lược đồ tối ưu cho mọi workload.** Mục tiêu là một thiết kế đáp ứng yêu cầu quan trọng, có thể giải thích các đánh đổi và còn khả năng mở rộng khi dữ liệu tăng.

## 2. Bắt đầu bằng bảng mô tả truy vấn nghiệp vụ

Trước khi tạo chỉ mục hoặc chọn partitioning, hãy ghi lại các mẫu truy vấn quan trọng.

Ví dụ hệ thống bán hàng:

| Mã | Nhu cầu | Điều kiện và thứ tự | Tần suất giả định | Mức ưu tiên |
| --- | --- | --- | --- | --- |
| Q1 | Mở chi tiết một đơn | `WHERE order_id = ?` | Rất thường xuyên | Cao |
| Q2 | Xem đơn gần nhất của một khách | `WHERE customer_id = ? ORDER BY created_at DESC LIMIT 20` | Thường xuyên | Cao |
| Q3 | Xem đơn đã thanh toán mới nhất | `WHERE status = 'paid' ORDER BY created_at DESC LIMIT 50` | Thường xuyên | Trung bình |
| Q4 | Đọc các dòng sản phẩm của đơn | `WHERE order_id = ?` trên `order_items` | Rất thường xuyên | Cao |
| Q5 | Tổng hợp doanh thu theo tháng | Lọc `created_at`, nhóm/tổng hợp nhiều đơn | Theo lịch | Trung bình |
| Q6 | Xem lịch sử sự kiện của một đơn | `WHERE order_id = ? ORDER BY event_at DESC` | Khi điều tra | Trung bình |

Các mức tần suất trên **chỉ là giả định minh họa**. Khi có hệ thống chạy thật, nên lấy dữ liệu từ log truy vấn, APM hoặc `pg_stat_statements` nếu đã được cấu hình.

Với mỗi truy vấn quan trọng, nên ghi thêm:

- Độ trễ mục tiêu ở mức p95/p99, không chỉ trung bình.
- Số hàng đầu vào và số hàng dự kiến trả về.
- Tỷ lệ giữa đọc và ghi trong ngày cao điểm.
- Mức chọn lọc của điều kiện `WHERE`, phân bố giá trị phổ biến và trường hợp dữ liệu lệch.
- Có `JOIN`, `ORDER BY`, `GROUP BY`, phân trang sâu hoặc batch lớn hay không.
- Có truy cập dữ liệu mới nhất hay thường xuyên đọc lịch sử nhiều năm.

Một quyết định schema có cơ sở phải có thể chỉ ra: **nó cải thiện hoặc bảo vệ truy vấn/ràng buộc/tốc độ tăng nào**.

## 3. Dựng lược đồ đơn hàng để thực hành

Các câu lệnh sau dành cho **database thực hành** mà người học có quyền tạo schema. Không chạy trong database sản xuất.

~~~sql
CREATE SCHEMA review_lab;

CREATE TABLE review_lab.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_customers_email UNIQUE (email),
    CONSTRAINT ck_customers_display_name
        CHECK (length(btrim(display_name)) > 0)
);

CREATE TABLE review_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    paid_at timestamptz,
    total_amount numeric(14, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES review_lab.customers (customer_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_orders_status
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    CONSTRAINT ck_orders_amount
        CHECK (total_amount >= 0),
    CONSTRAINT ck_orders_paid_time
        CHECK (paid_at IS NULL OR paid_at >= created_at)
);

CREATE TABLE review_lab.order_items (
    order_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(14, 2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES review_lab.orders (order_id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_item_order_sku UNIQUE (order_id, sku),
    CONSTRAINT ck_item_quantity CHECK (quantity > 0),
    CONSTRAINT ck_item_unit_price CHECK (unit_price >= 0)
);

CREATE TABLE review_lab.order_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    event_type text NOT NULL,
    event_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fk_events_order
        FOREIGN KEY (order_id)
        REFERENCES review_lab.orders (order_id)
        ON DELETE RESTRICT
);
~~~

Lược đồ này gồm ba loại quan hệ:

~~~text
customers (1)
    │
    │ fk_orders_customer
    ▼
orders (N)
    │              │
    │              └──────────► order_events (N)
    │                           lưu lịch sử sự kiện
    │
    └─────────────────────────► order_items (N)
                                lưu các dòng sản phẩm
~~~

### Giải thích một số lựa chọn

| Lựa chọn | Lý do | Điểm cần đánh giá tiếp |
| --- | --- | --- |
| `bigint ... IDENTITY` | ID tăng tự động, tránh sớm chạm giới hạn `integer` nếu số hàng lớn | Bên ngoài hệ thống có cần ID khó đoán hoặc phân tán không? |
| `timestamptz` | Lưu thời điểm có ngữ nghĩa múi giờ, thích hợp cho sự kiện | Cách chuyển đổi và hiển thị timezone ở ứng dụng |
| `numeric(14,2)` | Lưu số tiền thập phân chính xác theo độ chính xác đã chọn | Loại tiền tệ, làm tròn, giới hạn số lớn nhất |
| `PRIMARY KEY` | Bảo đảm mỗi hàng có danh tính duy nhất, tạo unique B-tree index tương ứng | Kiểu khóa và cách tham chiếu từ bảng khác |
| `FOREIGN KEY` | Ngăn quan hệ mồ côi giữa đơn và khách/chi tiết | Hành vi khi xóa và chi phí ghi/kiểm tra |
| `CHECK` và `NOT NULL` | Bảo vệ miền dữ liệu ngay tại database | Quy tắc cần kiểm tra qua nhiều bảng/transaction |
| `jsonb` ở `payload` | Phù hợp metadata sự kiện có cấu trúc biến đổi | Không nên thay các cột nghiệp vụ ổn định bằng JSONB tùy tiện |

Đây là **lược đồ khởi đầu để đánh giá**, không phải thiết kế hoàn chỉnh cho mọi nghiệp vụ. Chẳng hạn, việc lưu `total_amount` trong `orders` nhưng cũng có `quantity × unit_price` trong `order_items` đòi hỏi quy tắc bảo đảm hai nguồn luôn nhất quán.

## 4. Thêm dữ liệu mẫu không phụ thuộc số ID sinh ra

~~~sql
INSERT INTO review_lab.customers (email, display_name)
VALUES
    ('lan@example.test', 'Lan'),
    ('minh@example.test', 'Minh'),
    ('an@example.test', 'An');

INSERT INTO review_lab.orders
    (customer_id, status, created_at, paid_at, total_amount)
SELECT
    c.customer_id,
    x.status,
    x.created_at,
    x.paid_at,
    x.total_amount
FROM (
    VALUES
        (
            'lan@example.test',
            'paid',
            '2026-10-01 09:00:00+07'::timestamptz,
            '2026-10-01 09:03:00+07'::timestamptz,
            120000.00::numeric
        ),
        (
            'lan@example.test',
            'pending',
            '2026-10-04 14:30:00+07'::timestamptz,
            NULL::timestamptz,
            300000.00::numeric
        ),
        (
            'minh@example.test',
            'paid',
            '2026-10-02 11:00:00+07'::timestamptz,
            '2026-10-02 11:15:00+07'::timestamptz,
            80000.00::numeric
        ),
        (
            'an@example.test',
            'cancelled',
            '2026-10-05 08:20:00+07'::timestamptz,
            NULL::timestamptz,
            70000.00::numeric
        )
) AS x(email, status, created_at, paid_at, total_amount)
JOIN review_lab.customers AS c
    ON c.email = x.email;
~~~

Chèn một số dòng chi tiết và sự kiện bằng cách tìm ID đơn theo email/thời gian thay vì giả định mọi chuỗi ID luôn bắt đầu từ 1:

~~~sql
INSERT INTO review_lab.order_items
    (order_id, sku, quantity, unit_price)
SELECT o.order_id, 'COFFEE-001', 2, 60000.00
FROM review_lab.orders AS o
JOIN review_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.email = 'lan@example.test'
  AND o.created_at = '2026-10-01 09:00:00+07'::timestamptz;

INSERT INTO review_lab.order_events
    (order_id, event_type, event_at, payload)
SELECT
    o.order_id,
    'payment_confirmed',
    '2026-10-01 09:03:00+07'::timestamptz,
    '{"gateway":"sandbox","result":"ok"}'::jsonb
FROM review_lab.orders AS o
JOIN review_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.email = 'lan@example.test'
  AND o.created_at = '2026-10-01 09:00:00+07'::timestamptz;
~~~

Kiểm tra sơ bộ:

~~~sql
SELECT c.email, o.order_id, o.status, o.created_at, o.total_amount
FROM review_lab.orders AS o
JOIN review_lab.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.created_at, o.order_id;
~~~

Với bộ dữ liệu vài hàng, PostgreSQL rất có thể chọn **sequential scan** thay vì index scan vì đọc toàn bộ bảng nhỏ thường rẻ hơn. Đó không phải bằng chứng chỉ mục không có tác dụng trên bảng hàng triệu hàng.

## 5. Đánh giá lược đồ theo truy vấn: khóa, lọc, JOIN, sắp xếp

Hãy bắt đầu từ các truy vấn trong phần workload, sau đó xác định cấu trúc dữ liệu và chỉ mục hỗ trợ chúng.

### 5.1. Q1: tra cứu đơn theo khóa chính

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM review_lab.orders
WHERE order_id = 12345;
~~~

Vì `orders.order_id` là `PRIMARY KEY`, PostgreSQL tạo chỉ mục B-tree unique hỗ trợ tra cứu theo khóa này. Thông thường **không cần tạo thêm một chỉ mục đơn riêng trên `order_id`**.

Tương tự, constraint `UNIQUE (email)` trên bảng `customers` tạo chỉ mục unique để thực thi tính duy nhất. Một chỉ mục có cùng định nghĩa chỉ để “cho nhanh hơn” thường dư thừa.

### 5.2. Q2: danh sách đơn gần nhất của một khách hàng

~~~sql
SELECT order_id, status, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Truy vấn này có:

- Điều kiện bằng trên `customer_id`.
- Thứ tự giảm dần theo `created_at` và `order_id`.
- Giới hạn 20 hàng.

Một chỉ mục nên cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_created
ON review_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

Thứ tự thành phần giúp PostgreSQL tìm vùng của một khách hàng rồi đọc theo thời điểm mới nhất. `order_id` làm khóa sắp xếp phụ để kết quả ổn định khi nhiều đơn cùng thời điểm.

Đây là một thiết kế dựa trên **query pattern**, không phải máy móc sắp cột theo độ chọn lọc cao nhất. Nếu ứng dụng chủ yếu lọc theo `created_at` trên **tất cả khách hàng**, chỉ mục bắt đầu bằng `customer_id` không tự đáp ứng tốt truy vấn khác đó.

### 5.3. Q3: đơn đã thanh toán mới nhất

~~~sql
SELECT order_id, customer_id, created_at
FROM review_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Vì điều kiện `status = 'paid'` là một phần cố định của truy vấn, có thể cân nhắc **partial index**:

~~~sql
CREATE INDEX idx_orders_paid_created
ON review_lab.orders (created_at DESC, order_id DESC)
WHERE status = 'paid';
~~~

Chỉ mục này chứa các mục phù hợp predicate `status = 'paid'` và sắp theo thời gian, có thể tiết kiệm dung lượng so với chỉ mục toàn bảng trong một số phân bố dữ liệu.

**Không mặc định partial index luôn nhỏ và nhanh hơn.** Nếu 95% đơn hàng là `paid`, chỉ mục vẫn lớn. Bộ tối ưu cũng cần chứng minh điều kiện truy vấn phù hợp với predicate của chỉ mục.

Đặc biệt, với **prepared statement có tham số**:

~~~sql
WHERE status = $1
~~~

PostgreSQL có thể dùng generic plan mà không biết `$1` chắc chắn bằng `'paid'`. Khi đó partial index có thể không được chọn như với một truy vấn dùng literal `status = 'paid'`. Cần kiểm tra **kế hoạch thực tế do ứng dụng sinh ra**, không chỉ chạy `EXPLAIN` cho một câu SQL thay thế.

### 5.4. Q4: lấy các dòng sản phẩm của một đơn

~~~sql
SELECT sku, quantity, unit_price
FROM review_lab.order_items
WHERE order_id = 12345;
~~~

`order_items` đã có constraint:

~~~sql
UNIQUE (order_id, sku)
~~~

Constraint này tạo unique index bắt đầu bằng `order_id`, nên **có thể đã hỗ trợ điều kiện `WHERE order_id = ?`**. Không vội thêm `INDEX (order_id)` nếu index có tiền tố phù hợp đang đáp ứng tốt workload.

Đồng thời, việc khai báo `FOREIGN KEY (order_id)` **không tự tạo một chỉ mục riêng trên cột tham chiếu ở bảng con**. Trong ví dụ, unique index vô tình/đồng thời hỗ trợ truy vấn theo `order_id`; nếu không có unique index đó, cần cân nhắc chỉ mục riêng theo cách truy cập và các thao tác xóa/cập nhật bảng cha.

### 5.5. Q6: lịch sử sự kiện theo đơn

~~~sql
SELECT event_id, event_type, event_at, payload
FROM review_lab.order_events
WHERE order_id = 12345
ORDER BY event_at DESC, event_id DESC
LIMIT 100;
~~~

Đề xuất chỉ mục:

~~~sql
CREATE INDEX idx_events_order_time
ON review_lab.order_events (
    order_id,
    event_at DESC,
    event_id DESC
);
~~~

Chỉ mục B-tree phù hợp đọc lịch sử của một đơn. Ngược lại, nếu hệ thống chủ yếu tìm sự kiện **theo khoảng thời gian trên mọi đơn**, cần đánh giá một đường truy cập bắt đầu bằng `event_at` hoặc một chiến lược tổ chức dữ liệu phù hợp với tốc độ tăng và retention.

### 5.6. Đừng tạo một chỉ mục cho từng câu WHERE bất kỳ

Chỉ mục mang lại lợi ích **đọc**, nhưng có chi phí:

- Tốn dung lượng đĩa và cache.
- Mỗi lần `INSERT` cần thêm mục vào các chỉ mục liên quan.
- `UPDATE` có thể phải cập nhật nhiều chỉ mục; chỉ mục trên cột thường xuyên đổi có thể cản trở **HOT update** trong những tình huống thích hợp.
- `DELETE` và vacuum phải xử lý các mục liên quan.
- Mất thời gian xây dựng, bảo trì và kiểm tra khi nâng cấp schema.

Một lược đồ tốt không phải lược đồ có nhiều index nhất, mà là lược đồ có **những index giải quyết các truy vấn quan trọng với tổng chi phí đọc–ghi hợp lý**.

## 6. Đọc kế hoạch thực thi bằng EXPLAIN

PostgreSQL dùng planner để lựa chọn cách truy cập dữ liệu. Người thiết kế cần kiểm tra cách planner xử lý truy vấn thực, thay vì đoán hoàn toàn từ tên index.

~~~sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Những điểm cần chú ý trong output:

| Thành phần plan | Cách diễn giải |
| --- | --- |
| `Seq Scan` | Đọc tuần tự từ bảng; có thể hợp lý với bảng nhỏ hoặc điều kiện ít chọn lọc |
| `Index Scan` | Truy cập qua index rồi lấy dữ liệu bảng nếu cần |
| `Index Only Scan` | Có thể lấy dữ liệu cần thiết qua index khi điều kiện visibility cho phép |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Gom vị trí hàng từ index rồi truy cập dữ liệu bảng |
| `Sort` | Phải sắp xếp dữ liệu riêng thay vì nhận sẵn từ đường truy cập phù hợp |
| `Hash Join` / `Nested Loop` / `Merge Join` | Những chiến lược nối bảng khác nhau |
| `rows` / `cost` | Ước lượng của planner, không phải số đo thực thi |

### Dùng EXPLAIN ANALYZE đúng mục đích

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

`ANALYZE` **thực sự thực thi câu lệnh** để đo thời gian, số hàng và các bước của plan. Trong bài học, sử dụng `SELECT` để an toàn. Với `UPDATE`, `DELETE` hoặc lệnh làm thay đổi dữ liệu, cần có phương án thử nghiệm tách biệt và xử lý transaction phù hợp; không chạy `EXPLAIN ANALYZE` vô ý trên production rồi cho rằng chỉ “xem kế hoạch”.

`BUFFERS` bổ sung thống kê hoạt động buffer/block; “shared hit” không đơn giản bằng số lượt truy cập đĩa thực tế. Cần xem số liệu nhiều lần, sau khi thống kê đầy đủ, và trong bối cảnh cache, lượng dữ liệu và tính đồng thời.

### Dữ liệu mẫu quá nhỏ không đủ kết luận hiệu năng

Với bốn dòng `orders`, planner có thể chọn `Seq Scan`. Điều này bình thường. Muốn đánh giá lược đồ cho một triệu đơn, hãy dùng dữ liệu thử gần với thực tế về:

- Số hàng và kích thước trung bình của mỗi hàng.
- Phân bố theo `status`, `customer_id` và thời gian.
- Những khách hàng có rất nhiều đơn khác biệt với khách hàng chỉ có một đơn.
- Số lượng các giao dịch ghi đồng thời.
- Tỷ lệ truy vấn theo giờ bình thường và giờ cao điểm.

Khi dữ liệu thay đổi đáng kể, PostgreSQL cần thống kê phù hợp để planner chọn kế hoạch:

~~~sql
ANALYZE review_lab.orders;
ANALYZE review_lab.order_events;
~~~

`ANALYZE` giúp cập nhật thống kê cho planner; nó không tạo index hay bảo đảm mọi truy vấn tự động chuyển sang đường truy cập tốt nhất.

## 7. Đánh giá ràng buộc: dữ liệu nào được phép tồn tại?

Hiệu năng là một phần của thiết kế, nhưng **tính đúng dữ liệu** mới giúp hệ thống đáng tin cậy. Nếu database cho phép lưu đơn có số tiền âm, dòng đơn có số lượng 0 hoặc tham chiếu tới khách hàng không tồn tại, những truy vấn “nhanh” vẫn có thể trả dữ liệu nghiệp vụ sai.

### 7.1. PRIMARY KEY

~~~sql
order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY
~~~

`PRIMARY KEY` bảo đảm giá trị khóa duy nhất và không null; PostgreSQL tạo unique B-tree index để hỗ trợ constraint. Chọn khóa chính dựa trên độ ổn định và cách các bảng khác tham chiếu.

Một mã nghiệp vụ như `order_code` có thể cần `UNIQUE` riêng dù bảng dùng khóa kỹ thuật `order_id`. Không nên chọn một cột có khả năng thay đổi thường xuyên làm khóa chính nếu không có lý do rõ ràng.

### 7.2. FOREIGN KEY

~~~sql
CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES review_lab.customers (customer_id)
    ON DELETE RESTRICT
~~~

Ràng buộc này ngăn đơn tham chiếu tới khách hàng không tồn tại. `ON DELETE RESTRICT` làm thao tác xóa hàng cha bị từ chối khi còn hàng con tham chiếu theo quy tắc áp dụng.

Một số lựa chọn thiết kế:

| Hành vi | Ý nghĩa khi xử lý hàng cha | Khi cân nhắc |
| --- | --- | --- |
| `RESTRICT` | Ngăn xóa hàng cha đang được tham chiếu | Muốn giữ lịch sử đơn |
| `NO ACTION` | Kiểm tra ràng buộc theo thời điểm áp dụng; có thể deferrable nếu cấu hình phù hợp | Cần xử lý quan hệ trong transaction |
| `CASCADE` | Xóa/cập nhật hàng con theo thao tác cha theo quy tắc FK | Dữ liệu con thật sự nên cùng vòng đời |
| `SET NULL` | Đặt giá trị FK của hàng con thành null khi cha bị xóa | Chỉ hợp lý nếu cột và nghiệp vụ chấp nhận null |

Với đơn hàng tài chính, `ON DELETE CASCADE` từ khách hàng sang đơn có thể là sai lầm nghiêm trọng vì xóa khách hàng sẽ mất cả lịch sử đơn. Thường nên giữ đơn, dùng trạng thái vô hiệu hóa khách hàng hoặc quy trình lưu trữ dữ liệu riêng.

**Đừng nhầm** `ON DELETE CASCADE` (xóa các **hàng** liên quan theo FK) với `DROP TABLE ... CASCADE` (xóa **đối tượng schema** phụ thuộc).

### 7.3. NOT NULL và CHECK

~~~sql
status text NOT NULL,
CONSTRAINT ck_orders_status
    CHECK (status IN ('pending', 'paid', 'cancelled')),
CONSTRAINT ck_orders_amount
    CHECK (total_amount >= 0)
~~~

`CHECK` bảo vệ miền giá trị. Nhưng trong PostgreSQL, một biểu thức `CHECK` được coi là đạt nếu kết quả là **true hoặc null**; vì vậy `CHECK (total_amount >= 0)` **không thay thế** `NOT NULL`. Kết hợp cả hai khi cột bắt buộc có giá trị.

Với quy tắc thời gian:

~~~sql
CHECK (paid_at IS NULL OR paid_at >= created_at)
~~~

điều kiện bảo vệ việc thời điểm thanh toán không sớm hơn thời điểm tạo đơn khi có `paid_at`. Nhưng nó **chưa bắt buộc** mọi đơn ở trạng thái `paid` phải có `paid_at`. Nếu đó là yêu cầu nghiệp vụ, cần thêm quy tắc phù hợp, ví dụ constraint hoặc logic chuyển trạng thái có kiểm soát.

### 7.4. UNIQUE và cách xử lý NULL

~~~sql
CONSTRAINT uq_customers_email UNIQUE (email)
~~~

Đối với `email NOT NULL`, constraint bảo vệ tính duy nhất theo quy tắc so sánh của dữ liệu. Nhưng cần xác định nghiệp vụ muốn:

- `Lan@Example.test` có được coi giống `lan@example.test` không?
- Có được tái sử dụng email của tài khoản đã xóa mềm không?
- Khóa duy nhất chỉ trong từng tenant hay trên toàn hệ thống?

Một unique index dùng biểu thức có thể hỗ trợ cách kiểm tra không phân biệt hoa/thường theo biểu thức:

~~~sql
-- Minh họa một lựa chọn THAY THẾ khi thiết kế yêu cầu.
CREATE UNIQUE INDEX uq_customers_email_lower
ON review_lab.customers (lower(email));
~~~

Việc thêm chỉ mục này **không tự xóa** constraint unique cũ; phải thiết kế nhất quán và kiểm tra dữ liệu trùng trước khi áp dụng. Đồng thời, xử lý email thật có nhiều quy tắc hơn việc chỉ gọi `lower()`; cần chính sách chuẩn hóa được thống nhất với ứng dụng.

PostgreSQL 15 trở lên còn hỗ trợ `UNIQUE NULLS NOT DISTINCT` để coi các giá trị null là không phân biệt nhau khi kiểm tra uniqueness. Đây là lựa chọn hữu ích trong một số bài toán, nhưng không thay thế việc xác định rõ cột có được phép null và quy tắc nghiệp vụ mong muốn.

### 7.5. Những quy tắc vượt phạm vi một hàng

Ví dụ `orders.total_amount` được lưu sẵn để màn hình đọc nhanh, còn `order_items` chứa chi tiết:

~~~text
orders.total_amount
    cần tương thích với
SUM(order_items.quantity × order_items.unit_price)
~~~

Một `CHECK` trên `orders` **không thể trực tiếp truy vấn sang các hàng của `order_items`** để tính tổng như một constraint một hàng thông thường. Cần lựa chọn cơ chế nhất quán phù hợp:

- Không lưu tổng, tính từ chi tiết khi truy vấn nếu chi phí chấp nhận được.
- Lưu tổng như dữ liệu được duy trì theo **cùng một transaction** với thay đổi chi tiết.
- Dùng cơ chế trigger hoặc quy trình cập nhật được kiểm thử kỹ khi nghiệp vụ phù hợp.
- Tổ chức đối soát định kỳ cho dữ liệu tài chính hoặc dữ liệu cần tính đúng cao.

Tránh **chỉ dựa vào lời hứa của từng service** rằng nó luôn cập nhật tổng đúng: hệ thống có thể có nhiều đường ghi như import, batch hoặc script vận hành.

## 8. Ràng buộc đồng thời cũng có chi phí vận hành

Ràng buộc mạnh không đồng nghĩa với bỏ qua hiệu năng. Ví dụ:

- Foreign key cần kiểm tra hàng được tham chiếu khi thêm/cập nhật quan hệ.
- Khi xóa hàng cha, PostgreSQL cần tìm các hàng con đang tham chiếu; nếu cột foreign key bên con không có index phù hợp, thao tác này có thể tốn chi phí.
- Unique index cần kiểm tra tính duy nhất lúc ghi và tạo thêm chi phí bảo trì index.
- Constraint phức tạp hoặc trigger có thể làm mỗi giao dịch ghi tốn công hơn.

Tuy vậy, **không nên bỏ ràng buộc chỉ để tăng tốc benchmark ngắn**. Hệ thống cần bảo đảm tính đúng; nếu workload cho thấy constraint quá tốn kém, hãy xem lại mô hình dữ liệu, chỉ mục phụ trợ và cách ghi theo batch/transaction.

### Thêm ràng buộc vào bảng lớn có dữ liệu lịch sử

Với PostgreSQL, một số loại constraint như `FOREIGN KEY` hoặc `CHECK` có thể thêm theo quy trình hai giai đoạn:

~~~sql
ALTER TABLE review_lab.orders
ADD CONSTRAINT ck_orders_reasonable_amount
CHECK (total_amount <= 999999999999.99)
NOT VALID;

ALTER TABLE review_lab.orders
VALIDATE CONSTRAINT ck_orders_reasonable_amount;
~~~

Ví dụ chỉ nên chạy khi giới hạn đó phù hợp nghiệp vụ. `NOT VALID` cho phép trì hoãn việc quét xác minh dữ liệu **đã tồn tại**, nhưng constraint vẫn được kiểm tra cho những hàng mới/sửa phù hợp sau khi thêm. `VALIDATE CONSTRAINT` kiểm tra dữ liệu lịch sử để chuyển sang trạng thái đã xác minh.

Đây **không phải chế độ khóa bằng 0**: các lệnh DDL vẫn lấy lock theo quy tắc PostgreSQL. Cần thử trên bảng có kích thước tương ứng và lập kế hoạch migration.

Đối với yêu cầu `NOT NULL` hoặc unique trên bảng lớn, quy trình và mức lock có thể khác; không giả định mọi constraint đều hỗ trợ `NOT VALID` theo cùng một cách.

## 9. Đánh giá khả năng tăng trưởng: dự báo không chỉ dựa vào số hàng

Giả sử hệ thống nhận **200.000 sự kiện đơn hàng mỗi ngày**. Mỗi sự kiện gồm cột cố định, timestamp, ID và `jsonb payload`, có kích thước trung bình ước lượng **700 byte** (chỉ dữ liệu logic trước khi xét overhead).

~~~text
Số hàng mới/ngày = 200.000
Giả định dữ liệu logic/hàng = 700 bytes

Dữ liệu logic mới/ngày
    = 200.000 × 700
    = 140.000.000 bytes
    ≈ 140 MB/ngày (hệ thập phân)

Trong 365 ngày:
    = 140 MB × 365
    = 51.100 MB
    ≈ 51,1 GB dữ liệu logic
~~~

**51,1 GB không phải kích thước thực tế trên ổ đĩa của PostgreSQL.** Phải tính thêm:

- Header mỗi hàng, alignment, page headers và free space.
- B-tree index và index trên các cột truy vấn thường xuyên.
- TOAST đối với giá trị lớn được lưu tách hoặc nén theo quy tắc PostgreSQL.
- Các phiên bản hàng cũ do MVCC, cập nhật/xóa và vacuum chưa dọn được.
- WAL, temporary files, replication slots và thời gian giữ WAL.
- Dung lượng cần cho backup, restore, thay đổi index và các thao tác bảo trì.

Chỉ số “700 byte/hàng” cũng có thể thay đổi khi cấu trúc `payload` phát triển. Một thiết kế phục vụ năm thứ ba cần xem **tốc độ tăng, tuổi dữ liệu và cách truy vấn dữ liệu cũ**, không đơn giản nhân dữ liệu mẫu vài dòng với số năm.

### Kích thước cần đo theo thời gian

Trong PostgreSQL:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('review_lab.orders'::regclass)
    ) AS main_relation_size,
    pg_size_pretty(
        pg_indexes_size('review_lab.orders'::regclass)
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size('review_lab.orders'::regclass)
    ) AS total_relation_size;
~~~

Các hàm khác nhau:

| Hàm | Ý nghĩa thông dụng |
| --- | --- |
| `pg_relation_size` | Dung lượng quan hệ chính/fork được chỉ định; không phải tổng mọi thành phần |
| `pg_table_size` | Dung lượng bảng gồm cả những phần liên quan như TOAST theo cách PostgreSQL tính |
| `pg_indexes_size` | Tổng kích thước các index gắn với bảng |
| `pg_total_relation_size` | Tổng dung lượng bảng gồm index và các thành phần phụ thuộc lưu trữ liên quan |
| `pg_size_pretty` | Trình bày số byte dễ đọc hơn |

Muốn xem các bảng lớn nhất trong schema thực hành:

~~~sql
SELECT
    c.relname AS table_name,
    pg_size_pretty(pg_table_size(c.oid)) AS table_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'review_lab'
  AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC;
~~~

`relkind = 'r'` trong ví dụ chọn những bảng thường. Nếu sau này dùng partitioned table, bảng cha có thể không lưu dữ liệu trực tiếp; cần đo các partition con và tổng kích thước một cách có chủ đích.

**Theo dõi ít nhất hai lần** theo mốc thời gian (ví dụ hằng ngày) để thấy tốc độ tăng trưởng. Một điểm đo 100 GB không nói rõ database ổn định hay đang tăng 10 GB/ngày.

## 10. MVCC, UPDATE, DELETE và autovacuum ảnh hưởng dung lượng

PostgreSQL sử dụng **Multi-Version Concurrency Control (MVCC)**. Khi cập nhật hàng, hệ quản trị thường tạo phiên bản hàng mới thay vì ghi đè trực tiếp mọi dữ liệu theo một cách đơn giản. Các phiên bản cũ cần được dọn khi không còn cần cho những transaction còn hoạt động.

Điều này liên quan trực tiếp tới schema:

- Bảng được `UPDATE` liên tục có thể phát sinh nhiều dead tuples.
- Index trên cột thường thay đổi có thể làm việc cập nhật tốn công hơn.
- Transaction tồn tại quá lâu có thể giữ lại các phiên bản hàng cũ lâu hơn.
- Autovacuum cần đủ cơ hội chạy để dọn các tuple không còn cần và cập nhật thống kê.
- Một bảng nhiều thao tác sửa/xóa có thể tăng dung lượng dù số hàng logic không tăng tương ứng.

### Xem thống kê bảng

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'review_lab'
ORDER BY relname;
~~~

`n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không phải kết quả đếm chính xác tuyệt đối tại một thời điểm. Các bộ đếm thao tác ghi thường mang tính tích lũy từ lần reset thống kê và có thể thay đổi khi restart/reset/điều chỉnh theo hệ thống.

**Không nên kết luận bảng bị “bloat nghiêm trọng” chỉ từ `n_dead_tup` cao ở một thời điểm.** Cần xem mẫu cập nhật, autovacuum, độ tuổi transaction, mức tăng kích thước và các công cụ chẩn đoán phù hợp.

### VACUUM và VACUUM FULL khác nhau

- `VACUUM` thông thường dọn các tuple không còn cần và giúp tái sử dụng không gian bên trong quan hệ theo quy tắc PostgreSQL.
- `VACUUM (ANALYZE)` vừa vacuum vừa cập nhật thống kê cho planner khi phù hợp.
- `VACUUM FULL` viết lại bảng để thu hồi không gian, nhưng có chi phí cao, yêu cầu thêm dung lượng tạm và lock mạnh; **không phải thao tác bảo trì định kỳ mặc định** trên hệ thống đang phục vụ truy vấn.

Nếu bảng chỉ có 10 triệu hàng nhưng bị cập nhật lặp liên tục, thách thức vận hành có thể lớn hơn bảng 50 triệu hàng chủ yếu ghi thêm và ít sửa. Do đó **tốc độ cập nhật/xóa** là một biến thiết kế không thể bỏ qua.

### HOT update và lựa chọn index

PostgreSQL có thể thực hiện **Heap-Only Tuple (HOT) update** trong điều kiện thích hợp, ví dụ không thay đổi các cột liên quan index và có đủ không gian trang. HOT giảm nhu cầu thêm mục index mới cho một số cập nhật.

Nếu lược đồ gắn nhiều index lên các cột thay đổi thường xuyên như `status` hoặc `updated_at`, có thể làm giảm cơ hội HOT và tăng chi phí ghi. Điều này **không có nghĩa phải bỏ index trên status**: cần cân bằng lợi ích truy vấn với chi phí cập nhật thực tế.

## 11. Khi nào nên cân nhắc partitioning?

**Partitioning** chia dữ liệu của một bảng logic thành các bảng con theo quy tắc, ví dụ theo tháng của `event_at`.

Với bảng sự kiện tăng nhanh:

~~~text
order_events (bảng logic)
│
├── order_events_2026_10   [2026-10-01, 2026-11-01)
├── order_events_2026_11   [2026-11-01, 2026-12-01)
├── order_events_2026_12   [2026-12-01, 2027-01-01)
└── ...
~~~

Partitioning đáng đánh giá khi:

1. Dữ liệu rất lớn và truy vấn thường lọc theo **khóa phân vùng**.
2. Có chính sách xóa/lưu trữ dữ liệu cũ theo khoảng thời gian.
3. Có nhu cầu quản lý bảo trì, backup hoặc thao tác dữ liệu ở mức partition.
4. Số partition và tác động tới planner, constraint và quản trị được tính toán hợp lý.

### Ví dụ RANGE partition theo thời gian

Tạo bảng mới độc lập để minh họa (không thay thế trực tiếp `review_lab.order_events` hiện tại):

~~~sql
CREATE TABLE review_lab.events_partitioned (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE review_lab.events_2026_10
PARTITION OF review_lab.events_partitioned
FOR VALUES FROM ('2026-10-01 00:00:00+00')
             TO ('2026-11-01 00:00:00+00');

CREATE TABLE review_lab.events_2026_11
PARTITION OF review_lab.events_partitioned
FOR VALUES FROM ('2026-11-01 00:00:00+00')
             TO ('2026-12-01 00:00:00+00');
~~~

Một truy vấn có điều kiện khớp khóa partition có thể được planner **partition pruning**, hạn chế đọc những partition không liên quan:

~~~sql
SELECT event_id, event_type
FROM review_lab.events_partitioned
WHERE occurred_at >= '2026-11-01 00:00:00+00'
  AND occurred_at <  '2026-12-01 00:00:00+00';
~~~

### Ràng buộc khóa duy nhất khi partition

Trong PostgreSQL, một `PRIMARY KEY` hoặc `UNIQUE` áp dụng ở cấp partitioned table có các giới hạn liên quan khóa phân vùng. Chẳng hạn, khóa chính ví dụ phải chứa **`occurred_at`**, khóa dùng để phân vùng, để PostgreSQL có thể bảo đảm tính duy nhất theo cơ chế hiện có.

Điều này là một đánh đổi lớn nếu bảng cũ chỉ dùng `event_id` làm khóa chính và nhiều bảng khác tham chiếu tới `event_id`. Không thể tự đổi bảng hiện tại sang partition theo tháng mà bỏ qua thiết kế khóa, quan hệ tham chiếu và chiến lược migration.

### Partition không tự bảo đảm truy vấn nhanh

Nếu truy vấn:

~~~sql
WHERE event_id = 123456
~~~

mà bảng phân vùng theo `occurred_at`, PostgreSQL thường không thể loại bỏ các partition chỉ từ điều kiện `event_id`. Truy vấn có thể phải xét nhiều partition. Tăng số partition còn làm việc quản trị, thống kê, query planning và index maintenance phức tạp hơn.

**Đừng partition chỉ vì “sắp có một triệu hàng”**. Trước tiên xác định phần nào của workload thật sự hưởng lợi từ pruning, retention hoặc quản lý dữ liệu. Một bảng hàng chục triệu dòng có index phù hợp vẫn có thể vận hành tốt mà không cần partition.

## 12. Retention và tăng trưởng lâu dài

Nhiều bảng có vòng đời dữ liệu khác nhau:

| Loại dữ liệu | Tần suất đọc | Vòng đời có thể cân nhắc |
| --- | --- | --- |
| Khách hàng | Tra cứu thường xuyên | Lưu lâu theo nhu cầu và quy định |
| Đơn hàng đã thanh toán | Có thể cần đối soát nhiều năm | Giữ theo chính sách nghiệp vụ/kế toán |
| Sự kiện kỹ thuật chi tiết | Đọc khi chẩn đoán gần thời điểm sự cố | Có thể có retention ngắn hơn |
| Nhật ký debug lớn | Ít đọc sau một thời gian | Lưu trữ ngoài hoặc xóa theo quy trình |

Nếu một bảng sự kiện tăng 200.000 hàng/ngày và áp dụng retention 90 ngày thì trạng thái ổn định có thể vào khoảng **18 triệu hàng gần nhất** trước khi xét biến động, backlog và overhead. Cách dọn dữ liệu nên được thiết kế theo throughput và quy tắc pháp lý/nghiệp vụ.

Trên bảng partition theo thời gian, việc xử lý partition cũ theo quy trình phù hợp có thể hiệu quả hơn chạy một lệnh `DELETE` khổng lồ trên bảng đơn. Tuy nhiên, các ràng buộc tham chiếu, nhu cầu lưu trữ lịch sử và thời gian thực thi DDL vẫn cần đánh giá.

**Không tự động xóa dữ liệu dựa trên ngày tạo** khi chưa xác minh yêu cầu lưu giữ, audit, backup, phân quyền truy cập và cách ứng dụng truy vấn dữ liệu cũ.

## 13. Dùng thống kê PostgreSQL để tìm quyết định cần sửa

Ngoài kích thước bảng, có thể xem những index đang được dùng như thế nào:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'review_lab'
ORDER BY relname, indexrelname;
~~~

Ý nghĩa:

- `idx_scan`: số lần khởi tạo quét index được thống kê.
- `idx_tup_read`: số mục index được đọc theo định nghĩa thống kê.
- `idx_tup_fetch`: số hàng được lấy qua index theo những trường hợp thống kê.

Các số này phụ thuộc khoảng thời gian kể từ lần reset thống kê. `idx_scan = 0` **không đủ để kết luận có thể xóa một index**, đặc biệt khi đó là index thực thi `PRIMARY KEY`/`UNIQUE`, workload hiếm nhưng quan trọng, hoặc chưa trải qua một chu kỳ tải đại diện.

### pg_stat_statements nếu đã được cấu hình

Khi extension `pg_stat_statements` đã được cài và cấu hình phù hợp, có thể xem các câu SQL tiêu tốn thời gian:

~~~sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Ví dụ này **không chạy được trên mọi PostgreSQL ngay lập tức**: extension có thể chưa được tạo, cần cấu hình `shared_preload_libraries` và quyền thích hợp. Các cột và khả năng thống kê cũng có thể khác theo phiên bản.

Điểm lợi ích lớn của `pg_stat_statements` là xem **truy vấn ứng dụng thực tế**, tránh tối ưu một query tự tạo trong khi workload có chi phí cao nhất lại nằm ở một endpoint khác.

### Kết hợp nhiều nguồn số liệu

| Câu hỏi | Nguồn tham khảo |
| --- | --- |
| Truy vấn nào chiếm nhiều thời gian tổng? | `pg_stat_statements` hoặc APM/slow logs |
| Planner có dùng index không? | `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)` |
| Bảng/index chiếm bao nhiêu đĩa? | `pg_total_relation_size`, `pg_indexes_size` |
| Bảng ghi/xóa mạnh không? | `pg_stat_user_tables` |
| Index có được dùng qua chu kỳ tải không? | `pg_stat_user_indexes` |
| Có nhiều dead tuples hoặc autovacuum trễ không? | `pg_stat_user_tables` và giám sát vacuum |
| Đĩa thực tế còn bao nhiêu? | Metrics hệ điều hành/managed service |
| Tải giờ cao điểm thay đổi ra sao? | Metrics theo thời gian, APM, workload log |

## 14. Chuẩn hóa, phi chuẩn hóa và JSONB: quyết định có căn cứ

### 14.1. Chuẩn hóa để bảo vệ quan hệ

Thiết kế:

~~~text
customers(customer_id, email, display_name)
orders(order_id, customer_id, ...)
order_items(order_item_id, order_id, sku, quantity, unit_price)
~~~

tránh việc sao chép tên và email khách hàng vào **mọi dòng đơn** để rồi phải cập nhật hàng loạt nếu khách thay đổi thông tin. Nó cũng giúp có một điểm quản lý danh tính khách hàng và foreign key rõ ràng.

Nhưng lịch sử đơn hàng đôi khi cần **giữ snapshot thông tin tại thời điểm đặt** (ví dụ tên người nhận hoặc giá bán khi giao dịch) để phục vụ đối soát. Khi đó lưu thêm một bản snapshot có thể là lựa chọn nghiệp vụ đúng, không phải mọi sự trùng lặp đều “sai chuẩn hóa”.

### 14.2. Phi chuẩn hóa có chi phí đồng bộ

Ví dụ lưu `total_amount` trên `orders`:

**Lợi ích:** màn hình danh sách đơn không cần cộng các dòng `order_items` mỗi lần.

**Chi phí:** phải đồng bộ khi thêm/sửa/xóa dòng sản phẩm, áp dụng khuyến mại, điều chỉnh thuế hoặc hoàn tiền. Hãy xác định **nguồn dữ liệu chuẩn** (*source of truth*) và quy trình cập nhật nguyên tử.

Một giá trị suy ra được lưu sẵn nên có:

1. Lý do hiệu năng cụ thể.
2. Cơ chế cập nhật nhất quán trong transaction.
3. Kiểm tra đối soát hoặc bài kiểm tra xác nhận không bị lệch.
4. Quy trình sửa sai nếu phát hiện lệch dữ liệu.

### 14.3. JSONB: linh hoạt nhưng không nên bỏ ràng buộc quan trọng

`order_events.payload jsonb` phù hợp với metadata không đồng nhất giữa các loại sự kiện. Nhưng những trường luôn phải có, cần dùng trong `JOIN` hoặc cần khóa ngoại/unique thường nên là **cột quan hệ** rõ ràng.

Ví dụ:

~~~sql
SELECT event_id, event_at
FROM review_lab.order_events
WHERE payload @> '{"gateway":"sandbox"}'::jsonb;
~~~

Nếu truy vấn theo cấu trúc JSONB này xuất hiện nhiều trên tập dữ liệu lớn, có thể cân nhắc một **GIN index** phù hợp với operator và workload. Nhưng index GIN cũng tốn dung lượng và chi phí ghi; không nên tạo chỉ mục cho mọi khóa JSONB chỉ vì kiểu dữ liệu hỗ trợ.

Chọn JSONB vì **độ linh hoạt được yêu cầu**, không phải để thay thế thiết kế schema khi business fields và quan hệ đã ổn định.

## 15. Khóa đa tenant và ranh giới dữ liệu

Trong hệ thống phục vụ nhiều tổ chức (*multi-tenant*), cần đánh giá liệu từng bảng có chứa `tenant_id` và foreign key có bảo vệ đúng tenant hay không.

Ví dụ mô hình:

~~~sql
CREATE TABLE review_lab.tenant_warehouses (
    tenant_id bigint NOT NULL,
    warehouse_id bigint NOT NULL,
    name text NOT NULL,
    PRIMARY KEY (tenant_id, warehouse_id)
);

CREATE TABLE review_lab.tenant_inventory (
    tenant_id bigint NOT NULL,
    warehouse_id bigint NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (tenant_id, warehouse_id, sku),
    FOREIGN KEY (tenant_id, warehouse_id)
        REFERENCES review_lab.tenant_warehouses
            (tenant_id, warehouse_id)
);
~~~

Khóa ngoại ghép giúp ngăn một dòng tồn kho của tenant A vô tình tham chiếu kho của tenant B. Nếu chỉ dùng `warehouse_id` không mang ngữ cảnh tenant trong quan hệ tham chiếu, ứng dụng có thể dựa hoàn toàn vào code để bảo vệ tính đúng này.

Trong môi trường thật, còn cần thiết kế **Row-Level Security (RLS)** hoặc cơ chế kiểm soát truy cập tương đương nếu tenant phải được cách ly về quyền đọc/ghi. Composite foreign key bảo vệ quan hệ dữ liệu, nhưng **không tự thay thế phân quyền**.

Đánh giá multi-tenant cũng ảnh hưởng thứ tự index: nếu hầu hết truy vấn đều có `WHERE tenant_id = ?`, nhiều index có thể cần bắt đầu bằng `tenant_id` để hỗ trợ cả hiệu năng và mẫu truy cập thông thường.

## 16. Sơ đồ đánh giá lược đồ theo từng quyết định

~~~text
               Có truy vấn/quy tắc nghiệp vụ cụ thể?
                              |
                     +--------+--------+
                     |                 |
                   Không                Có
                     |                 |
           Thu thập workload     Xác định điều kiện WHERE,
           và yêu cầu dữ liệu    JOIN, ORDER BY, dữ liệu trả về
                                       |
                                       v
                             Đã có PK/FK/CHECK/UNIQUE
                             bảo vệ trạng thái hợp lệ?
                                       |
                            +----------+----------+
                            |                     |
                           Chưa                    Có
                            |                     |
                   Bổ sung thiết kế        Kiểm tra EXPLAIN
                   constraint phù hợp      trên dữ liệu đại diện
                            |                     |
                            +----------+----------+
                                       |
                                       v
                           Đo chi phí đọc VÀ ghi
                                       |
                                       v
                          Dự báo dữ liệu tăng ra sao?
                                       |
                          +------------+-------------+
                          |                          |
                    Tăng vừa phải          Tăng nhanh / retention
                          |                          |
                  Index + vacuum           Cân nhắc partition,
                  + thống kê đủ?           lưu trữ lịch sử, archive
                          |                          |
                          +------------+-------------+
                                       |
                                       v
                              Thử nghiệm, đo đạc,
                              triển khai có rollback
~~~

Hãy tránh bắt đầu bằng “tạo partition tháng” khi chưa biết ứng dụng có lọc theo thời gian hay không, cũng tránh “thêm index tất cả cột” khi chưa biết tỷ lệ ghi.

## 17. Bảng đánh giá lược đồ trước khi triển khai

| Nhóm | Câu hỏi cần trả lời | Bằng chứng mong muốn |
| --- | --- | --- |
| Truy vấn | Có những mẫu truy vấn quan trọng nào? | Query inventory, tần suất, độ trễ p95/p99 |
| Lọc và JOIN | Index có hỗ trợ điều kiện quan trọng không? | `EXPLAIN` và kế hoạch thực tế |
| Thứ tự và phân trang | `ORDER BY LIMIT` có bị sort tốn kém? | Plan và độ trễ trên dữ liệu đại diện |
| Khóa | Có PK ổn định và unique business key đúng không? | DDL và test dữ liệu trùng |
| Quan hệ | Có FK, đúng hành vi xóa/cập nhật không? | DDL, test hàng mồ côi và xóa cha |
| Miền dữ liệu | Có kiểm tra null, miền giá trị, lượng tiền không âm? | `NOT NULL`, `CHECK` và test dữ liệu sai |
| Tính nhất quán | Dữ liệu suy ra có cơ chế đồng bộ không? | Thiết kế transaction/trigger/đối soát |
| Ghi | Index/trigger có làm insert/update chậm quá mức? | Benchmark ghi và thống kê tuple/index |
| Dung lượng | Bảng/index/TOAST tăng theo tốc độ nào? | Biểu đồ kích thước nhiều thời điểm |
| MVCC | Dead tuples, autovacuum, transaction dài ra sao? | Stats vacuum và cảnh báo |
| Retention | Dữ liệu nào phải giữ, xóa, lưu trữ? | Chính sách dữ liệu và cách thực thi |
| Partitioning | Có lợi ích pruning/retention đủ lớn? | Thử nghiệm cùng query và số partition |
| Vận hành | Backup, restore, migration và rollback đã được thử? | Kết quả diễn tập và checklist |

Không nhất thiết mọi mục đều phải là một câu SQL. Một số câu trả lời chỉ có được khi trao đổi với đội sản phẩm, an ninh thông tin hoặc vận hành.

## 18. Quy trình cải tiến một lược đồ đang chạy

Giả sử `review_lab.orders` đã có hàng triệu dòng và Q2 đang chậm. Một quy trình khả thi:

### Bước 1. Chọn vấn đề có bằng chứng

Ghi nhận Q2 chiếm nhiều thời gian tổng, hoặc p95 vượt mức mục tiêu trong giờ cao điểm. Không tối ưu chỉ vì nhìn một câu `SELECT` “có vẻ phức tạp”.

### Bước 2. Xem plan và phân bố dữ liệu

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Kiểm tra planner đã dùng index gì, có sort không, số hàng thực tế/ước lượng và lượng buffer I/O.

### Bước 3. Đề xuất thay đổi nhỏ, đo được

Nếu workload cần, đề xuất:

~~~sql
CREATE INDEX idx_orders_customer_created
ON review_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

Đây là câu tạo index trong lab. Trên bảng lớn production, có thể cân nhắc `CREATE INDEX CONCURRENTLY` để hạn chế một số dạng chặn ghi; cách này có điều kiện và chi phí riêng, **không chạy trong transaction block**, có thể để lại index invalid nếu thất bại và phải quản lý theo quy trình.

Không thêm index nếu một index tương đương đã tồn tại hoặc kết quả đo cho thấy chi phí ghi tăng vượt lợi ích đọc.

### Bước 4. Đánh giá tác động tới ràng buộc và dữ liệu cũ

Nếu thay đổi không chỉ là index mà còn sửa khóa, kiểu dữ liệu hoặc chia partition, cần xét:

- Dữ liệu hiện tại có vi phạm constraint mới không.
- Foreign key và view nào phụ thuộc cấu trúc cũ.
- Ứng dụng cũ có còn chạy trong lúc triển khai phiên bản mới không.
- Migration có lock mạnh, rewrite bảng hoặc cần thêm dung lượng không.

Ưu tiên chiến lược **expand–migrate–contract** đối với các thay đổi breaking: tạo cấu trúc mới, chuyển dữ liệu, chuyển ứng dụng, xác minh rồi mới bỏ cấu trúc cũ.

### Bước 5. Đo cả lợi ích và chi phí

Sau thay đổi, so sánh trên điều kiện tải tương đương:

- p95/p99 và thời gian tổng của Q2.
- Tỷ lệ hàng phải quét và thao tác sort.
- Throughput `INSERT/UPDATE`, độ trễ commit và chi phí index.
- Kích thước bảng/index và hiệu quả autovacuum.

**Không kết luận thành công chỉ vì `EXPLAIN` đã chuyển sang `Index Scan`.** Mục tiêu là tính đúng và hiệu quả tổng thể của workload khi dữ liệu tăng.

## 19. Những sai lầm thường gặp

### Sai lầm 1: Chỉ thiết kế theo dữ liệu mẫu

Một bảng vài trăm hàng dễ khiến mọi truy vấn đều nhanh. Nếu không dự đoán dữ liệu tăng và skew theo khách hàng/trạng thái, index hoặc khóa được chọn có thể không phù hợp sau một năm.

### Sai lầm 2: Đánh đồng chuẩn hóa với hiệu năng tối ưu

Chuẩn hóa giúp giảm bất nhất, nhưng các truy vấn quan trọng vẫn cần index và có thể cần dữ liệu tổng hợp. Phi chuẩn hóa phải có quy tắc đồng bộ và test cụ thể.

### Sai lầm 3: Nghĩ foreign key tự tạo index trên mọi cột bên con

PostgreSQL tạo chỉ mục để bảo vệ phía **được tham chiếu** qua PK/UNIQUE phù hợp, nhưng **không tự tạo index cho mọi cột FK bên tham chiếu**. Cần đánh giá chỉ mục trên bảng con theo truy vấn và thao tác của bảng cha.

### Sai lầm 4: Dùng CHECK mà quên NOT NULL

`CHECK (quantity > 0)` không nhất thiết từ chối null. Nếu quantity bắt buộc, cần `NOT NULL` bên cạnh điều kiện miền.

### Sai lầm 5: Càng nhiều index càng tốt

Index dư thừa chiếm đĩa, tăng ghi và có thể làm HOT update khó hơn. Hãy ưu tiên mẫu truy vấn thực tế và đo chi phí ghi.

### Sai lầm 6: Xem n_live_tup là COUNT chính xác

`pg_stat_user_tables.n_live_tup` là số liệu ước lượng. Nếu cần đối soát nghiệp vụ chính xác, dùng truy vấn phù hợp và cân nhắc chi phí quét; nếu cần theo dõi tăng trưởng, thống kê ước lượng theo thời gian thường hữu ích hơn.

### Sai lầm 7: Partitioning để “làm mọi truy vấn nhanh”

Partition có thể giúp pruning và retention, nhưng làm thiết kế PK/UNIQUE/FK, index và vận hành phức tạp hơn. Truy vấn không có điều kiện khóa partition có thể vẫn truy cập rất nhiều partition.

### Sai lầm 8: Quên MVCC, vacuum và WAL

Số hàng hiện tại không nói hết dung lượng. Hàng bị update/delete, TOAST, index, WAL và file tạm có thể ảnh hưởng mạnh tới ổ đĩa và thời gian phục hồi.

### Sai lầm 9: Dùng JSONB cho mọi trường

JSONB hữu ích cho metadata linh hoạt, nhưng dữ liệu định danh, khóa quan hệ và các thuộc tính nghiệp vụ có ràng buộc rõ ràng thường cần cột và constraint phù hợp.

### Sai lầm 10: Chỉ nhìn read latency mà bỏ qua tính đúng

Một cải tiến giúp truy vấn nhanh hơn nhưng bỏ constraint và tạo hàng mồ côi có thể làm hệ thống khó bảo trì hơn. Tính nhất quán phải là điều kiện đầu vào của việc tối ưu.

## 20. Bài tập thực hành

### Bài 1. Phân tích workload

Ứng dụng thường xuyên chạy:

~~~sql
SELECT order_id, created_at, status
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Hãy đề xuất một index và giải thích thứ tự từng cột. Nếu chỉ có dữ liệu vài hàng, vì sao planner vẫn có thể dùng `Seq Scan`?

### Bài 2. Foreign key và index

Bảng `order_events` có FK `order_id` tới `orders.order_id`. Nếu không có index trên `order_events.order_id`, PostgreSQL có bắt buộc tự tạo một B-tree index riêng cho cột bên con không? Truy vấn nào khiến bạn cân nhắc thêm index?

### Bài 3. CHECK và NULL

Cho cột:

~~~sql
quantity integer CHECK (quantity > 0)
~~~

Cột có thể nhận `NULL` không? Nếu nghiệp vụ yêu cầu ít nhất một đơn vị sản phẩm, nên khai báo thế nào?

### Bài 4. UNIQUE và email

`UNIQUE (email)` có thể coi `Lan@Example.test` và `lan@example.test` là hai giá trị khác nhau theo quy tắc so sánh hiện hành. Nếu nghiệp vụ muốn kiểm tra tính duy nhất không phân biệt chữ hoa/thường, bạn cần thiết kế thêm điều gì?

### Bài 5. Tổng tiền đơn hàng

Vì sao lưu đồng thời `orders.total_amount` và `order_items.quantity × unit_price` có thể gây lệch dữ liệu? Nêu hai cách quản lý tính nhất quán khi vẫn muốn đọc tổng tiền nhanh.

### Bài 6. Dự báo tăng trưởng

Một bảng sự kiện tăng **100.000 hàng/ngày**, dữ liệu logic trung bình **500 byte/hàng**. Hãy tính ước lượng dữ liệu logic trong 30 ngày theo MB thập phân; vì sao kích thước `pg_total_relation_size` có thể khác con số này?

### Bài 7. Đánh giá partitioning

Một bảng 50 triệu sự kiện được truy vấn chủ yếu bằng `WHERE event_id = ?`, trong khi đề xuất partition theo `occurred_at`. Đây có chắc chắn là cải tiến hiệu năng không? Cần đo và xem thêm điều kiện nào?

### Bài 8. Đọc các chỉ số tăng trưởng

Viết SQL xem:

1. Tổng kích thước bảng `review_lab.order_events`.
2. `n_live_tup`, `n_dead_tup`, `last_autovacuum` của bảng đó.
3. Những index hiện có và số lượt quét theo `pg_stat_user_indexes`.

### Bài 9. Constraint trên bảng lớn

Một bảng có 100 triệu hàng cần bổ sung một `CHECK` mới. Giải thích lợi ích của `NOT VALID` và `VALIDATE CONSTRAINT`, và vì sao quy trình này vẫn cần đánh giá lock và tính tương thích dữ liệu.

### Bài 10. Quyết định về JSONB

Trong `order_events`, trường `event_type` được dùng lọc thường xuyên; `payload` gồm metadata khác nhau theo từng sự kiện. Có nên xóa cột `event_type` rồi chuyển mọi thứ vào một JSONB duy nhất không? Nêu các đánh đổi về constraint, truy vấn và index.

### Đáp án gợi ý

| Bài | Hướng trả lời |
| --- | --- |
| 1 | `(customer_id, created_at DESC, order_id DESC)`; bảng nhỏ có thể quét tuần tự rẻ hơn index |
| 2 | Không. Xem truy vấn lịch sử theo `order_id` và thao tác kiểm tra FK khi xóa/sửa hàng cha |
| 3 | Có thể nhận null; thêm `NOT NULL` và `CHECK (quantity > 0)` |
| 4 | Cân nhắc unique index trên biểu thức `lower(email)` hoặc chính sách chuẩn hóa/type/collation phù hợp, sau khi kiểm tra trùng |
| 5 | Vì hai nguồn được cập nhật ở thời điểm/đường ghi khác nhau. Có thể tính từ chi tiết khi đọc hoặc đồng bộ tổng trong transaction và đối soát |
| 6 | `100.000 × 500 × 30 = 1.500.000.000 bytes = 1.500 MB`; khác vì index, tuple/page overhead, TOAST, MVCC và phần lưu trữ khác |
| 7 | Không chắc. Truy vấn theo event ID không pruning theo thời gian; xem khả năng lọc theo khóa partition và lợi ích retention |
| 8 | Kết hợp `pg_total_relation_size`, `pg_stat_user_tables` và `pg_stat_user_indexes` |
| 9 | `NOT VALID` trì hoãn quét dữ liệu cũ, `VALIDATE` kiểm tra sau; DDL vẫn có lock và phải bảo đảm constraint phù hợp dữ liệu |
| 10 | Không nên mặc định. Dữ liệu ổn định cần lọc/ràng buộc rõ thường nên là cột, JSONB phù hợp metadata linh hoạt |

Ví dụ lời giải bài 8:

~~~sql
SELECT pg_size_pretty(
    pg_total_relation_size('review_lab.order_events'::regclass)
) AS total_size;

SELECT
    relname, n_live_tup, n_dead_tup, last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'review_lab'
  AND relname = 'order_events';

SELECT
    indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'review_lab'
  AND relname = 'order_events'
ORDER BY indexrelname;
~~~

## 21. Bảng tra cứu nhanh khi review schema

| Mục tiêu | Công cụ hoặc cách kiểm tra |
| --- | --- |
| Xem DDL bảng và ràng buộc | `\d+ review_lab.orders` trong `psql` |
| Thống kê số hàng ước lượng | `pg_stat_user_tables` hoặc `pg_class.reltuples` |
| Đo kích thước bảng + index | `pg_total_relation_size()` |
| Đo kích thước chỉ mục | `pg_indexes_size()` |
| Xem index đã tạo | `pg_indexes`, `\di` hoặc `pg_stat_user_indexes` |
| Xem kế hoạch ước lượng | `EXPLAIN SELECT ...` |
| Đo plan thực thi | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` |
| Xem truy vấn nặng | `pg_stat_statements` khi đã bật |
| Xem hoạt động vacuum/dead tuples | `pg_stat_user_tables` |
| Bảo vệ quan hệ | `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE` |
| Bảo vệ miền giá trị | `NOT NULL`, `CHECK` |
| Xử lý bảng tăng theo thời gian | Đo tốc độ tăng, retention, index, partitioning khi có bằng chứng |
| Thay đổi schema an toàn | Staging, migration, kiểm tra phụ thuộc, backup/rollback |

## 22. Kết luận

Một lược đồ PostgreSQL nên được đánh giá bằng **ba câu hỏi xuyên suốt**:

**Thứ nhất: hệ thống đọc và ghi dữ liệu như thế nào?** Hãy lấy các truy vấn thường dùng, kiểm tra `WHERE`, `JOIN`, `ORDER BY`, số hàng trả về, độ trễ và kế hoạch thực tế trước khi quyết định index hoặc tổ chức bảng.

**Thứ hai: dữ liệu hợp lệ được bảo vệ ở đâu?** Hãy dùng khóa, foreign key, unique, `NOT NULL` và `CHECK` phù hợp để giảm khả năng xuất hiện dữ liệu sai ngay cả khi ứng dụng hoặc script vận hành có lỗi. Với dữ liệu tổng hợp/phi chuẩn hóa, phải có chiến lược đồng bộ rõ ràng.

**Thứ ba: thiết kế này sẽ vận hành ra sao khi dữ liệu tăng gấp 10 hoặc 100 lần?** Hãy theo dõi dung lượng bảng/index, tỷ lệ ghi/xóa, hoạt động MVCC/vacuum, chính sách retention và khả năng migration. Chỉ chọn partitioning hoặc thay đổi lớn khi bài toán thực tế cho thấy lợi ích vượt chi phí.

Một thiết kế tốt là thiết kế **đúng dữ liệu, phù hợp workload và có đường nâng cấp an toàn khi quy mô thay đổi**. Việc review schema nên được lặp lại theo số liệu thực tế, chứ không kết thúc vào ngày chạy thành công câu lệnh `CREATE TABLE` đầu tiên.

# Chỉ mục giải quyết bài toán gì và chi phí khi ghi trong PostgreSQL

Một bảng PostgreSQL có 100 hàng thường không tạo ra nhiều khó khăn khi tìm một đơn hàng. Nhưng khi bảng có 100 triệu hàng, câu hỏi “đơn hàng `order_id = 12345` nằm ở đâu?” sẽ khác hẳn câu hỏi “đọc tất cả đơn hàng của tháng này”. Nếu database phải xem lần lượt từng hàng để tìm một vài hàng cần thiết, truy vấn có thể đọc rất nhiều dữ liệu không liên quan.

**Chỉ mục (index)** là cấu trúc dữ liệu bổ sung giúp PostgreSQL **tìm đúng phần dữ liệu cần đọc**, hoặc **đọc dữ liệu theo thứ tự hữu ích**, thay vì luôn quét toàn bộ bảng. Tuy nhiên index không miễn phí:

- Khi `INSERT` một hàng, PostgreSQL có thể phải ghi thêm entry vào nhiều index.
- Khi `UPDATE` các cột liên quan index, PostgreSQL có thể phải cập nhật các cấu trúc index ngoài việc tạo phiên bản hàng mới theo MVCC.
- Khi `DELETE`, index và các phiên bản tuple cũ phải được dọn dẹp theo vòng đời MVCC/VACUUM.
- Index chiếm dung lượng lưu trữ, tạo WAL, gây ghi trang, page split, tăng nhu cầu cache và thời gian bảo trì.
- Một index không phù hợp có thể **ít được planner dùng**, nhưng vẫn làm mọi thao tác ghi tốn thêm công việc.

Bài học này tập trung vào hai câu hỏi không thể tách rời:

1. **Index giải quyết bài toán đọc nào?** Tìm theo khóa, lọc một tập nhỏ, hỗ trợ JOIN, ORDER BY, LIMIT, unique constraint hoặc điều kiện đặc thù như JSONB/địa lý.
2. **Đổi lại ta phải trả những chi phí gì khi ghi?** Chi phí cập nhật index, ảnh hưởng đến HOT update, WAL, bloat, VACUUM, locking, thời gian tạo/rebuild và tài nguyên hệ thống.

Mục tiêu không phải “tạo index cho mọi cột thường xuất hiện trong WHERE”, mà là **thiết kế tập index nhỏ nhưng đúng với workload**.

## 1. Ví dụ trực quan: tìm tên trong cuốn sách

Hãy hình dung một quyển sách dày 1.000 trang.

- Nếu đọc toàn bộ nội dung từ trang đầu để tìm chữ “MVCC”, bạn đang làm công việc giống **sequential scan**.
- Nếu sách có mục lục chỉ ra từ “MVCC” ở trang 230 và 415, bạn có thể tìm vị trí nhanh hơn. Đó là hình ảnh đơn giản của **index lookup**.
- Nếu muốn đọc **toàn bộ quyển sách**, tra mục lục để nhảy đến từng trang có thể tốn công hơn đọc tuần tự từ đầu đến cuối.

Đây là lý do một index có thể giúp truy vấn tìm **một hàng** nhưng không nhất thiết giúp truy vấn trả về **80% hàng của bảng**.

~~~mermaid
flowchart TD
    Q["Câu truy vấn PostgreSQL"] --> P["Planner ước lượng số hàng và chi phí"]
    P --> S["Seq Scan: đọc nhiều hàng theo heap"]
    P --> I["Index Scan: tìm khóa, truy cập hàng phù hợp"]
    P --> B["Bitmap Scan: gom vị trí hàng rồi đọc theo block"]
    P --> O["Index Only Scan: có thể tránh nhiều lần đọc heap"]
    S --> R["Trả kết quả"]
    I --> R
    B --> R
    O --> R
~~~

**Index là một lựa chọn của query planner**, không phải cam kết rằng cứ có index thì PostgreSQL luôn dùng nó.

## 2. Bảng dữ liệu và cấu trúc index khác nhau thế nào?

Trong PostgreSQL, bảng thường lưu các phiên bản hàng trong **heap**. B-tree index, loại phổ biến nhất, lưu các entry được tổ chức theo khóa tìm kiếm và thông tin để tham chiếu tới vị trí tuple trong heap.

Ví dụ bảng:

~~~text
orders
------------------------------------------------------------------
order_id | customer_id | status  | created_at | total
------------------------------------------------------------------
1001     | 11          | pending | ...        | 120.00
1002     | 42          | paid    | ...        |  80.00
1003     | 42          | pending | ...        |  50.00
1004     | 17          | paid    | ...        | 200.00
~~~

Nếu tạo:

~~~sql
CREATE INDEX idx_orders_customer
ON orders(customer_id);
~~~

cấu trúc B-tree có thể minh họa giản lược:

~~~text
Index theo customer_id             Heap chứa hàng đầy đủ

11 → [vị trí hàng 1001] ─────────→ order 1001 ...
17 → [vị trí hàng 1004] ─────────→ order 1004 ...
42 → [vị trí hàng 1002] ─────────→ order 1002 ...
42 → [vị trí hàng 1003] ─────────→ order 1003 ...
~~~

Đây chỉ là **sơ đồ khái niệm**; cấu trúc B-tree thực tế có các trang nội bộ, trang lá, cách quản lý key trùng và các cơ chế tối ưu lưu trữ khác.

### Index có chứa cả hàng không?

Một index thông thường **không thay thế heap**. Nó lưu thông tin cần thiết cho kiểu truy cập index đó. Với B-tree, truy vấn có thể tìm entry trong index rồi phải đọc heap để lấy cột khác và kiểm tra tuple có nhìn thấy theo snapshot MVCC hay không.

Đôi khi PostgreSQL chọn **Index Only Scan** nếu các cột cần trả về đã được index cung cấp và visibility map cho phép tránh đọc heap của nhiều trang. Nhưng index-only không có nghĩa PostgreSQL hoàn toàn bỏ qua visibility.

### Một bảng có thể có nhiều index

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_created ON orders(created_at);
CREATE INDEX idx_orders_status ON orders(status);
~~~

Đây là ba cấu trúc riêng, mỗi cấu trúc có dung lượng và chi phí bảo trì. PostgreSQL không tự gộp chúng thành một index toàn năng; từng query được planner cân nhắc dùng một index, kết hợp bitmap của nhiều index, hoặc bỏ qua index.

## 3. Những bài toán đọc mà chỉ mục có thể giải quyết

| Nhu cầu | Ví dụ câu SQL | Index thường hữu ích |
| --- | --- | --- |
| Tìm một hàng theo khóa | `WHERE order_id = 12345` | B-tree trên khóa chính |
| Lọc khách hàng cụ thể | `WHERE customer_id = 42` | B-tree trên `customer_id` |
| Truy vấn khoảng thời gian hẹp | `WHERE created_at >= ... AND created_at < ...` | B-tree trên `created_at` |
| Lấy bản ghi mới nhất | `WHERE customer_id = ? ORDER BY created_at DESC LIMIT 10` | B-tree nhiều cột phù hợp điều kiện và thứ tự |
| JOIN khóa ngoại | `orders.customer_id = customers.customer_id` | Index trên cột ghép phù hợp |
| Bảo đảm không trùng | `UNIQUE(tenant_id, external_code)` | Unique B-tree tự được tạo bởi constraint |
| Lọc chỉ một nhóm nhỏ | `WHERE status = 'failed'` khi failed hiếm | Partial index thích hợp |
| Tìm trong JSONB | `details @> '{"tag":"urgent"}'::jsonb` | GIN theo operator class phù hợp |
| Truy vấn không gian | Khoảng cách/hình học theo extension/type | GiST hoặc loại phù hợp |
| Dữ liệu rất lớn, tương quan thứ tự vật lý | Quét khoảng ngày trên bảng append-only | BRIN có thể tiết kiệm dung lượng |

Không phải mọi câu `WHERE` đều có thể được một index hỗ trợ hiệu quả. Cần xét **toán tử**, kiểu dữ liệu, thứ tự cột, mức chọn lọc và cách dữ liệu phân bố thực tế.

## 4. Vì sao PostgreSQL đôi lúc chọn Seq Scan dù đã có index?

Giả sử bảng có 1.000.000 hàng.

- Truy vấn A cần **một** hàng bằng khóa chính.
- Truy vấn B cần **900.000** hàng để tổng hợp.

A thường hưởng lợi từ index lookup vì tiết kiệm phần lớn việc quét dữ liệu. Với B, nếu dùng index phải duyệt rất nhiều entry, rồi truy cập nhiều trang heap, có thể tốn hơn đọc liên tục bảng.

Planner cân nhắc các yếu tố:

1. **Selectivity:** tỷ lệ hàng được dự đoán thỏa điều kiện.
2. **Cardinality:** số hàng cần trả và số hàng phải xử lý trung gian.
3. **Chi phí I/O:** đọc tuần tự so với các lần truy cập heap có tính ngẫu nhiên.
4. **Độ tương quan dữ liệu:** vị trí vật lý của các hàng có gần thứ tự index không.
5. **Số trang index và heap:** index cũng phải được đọc.
6. **Cache:** nhiều trang đã nằm trong shared buffers hoặc OS cache chưa.
7. **ORDER BY, LIMIT, JOIN:** index có thể vừa lọc vừa cung cấp thứ tự hữu ích.
8. **Thống kê và tham số chi phí:** `ANALYZE`, `random_page_cost`, `effective_cache_size` và các yếu tố khác.
9. **Khả năng parallel scan:** có thể quét bảng song song khi phù hợp.

Một `Seq Scan` trong kế hoạch không tự là lỗi. Trên bảng nhỏ hoặc khi lấy phần lớn hàng, Seq Scan thường là lựa chọn hợp lý.

## 5. Cách B-tree giúp tìm giá trị

B-tree được thiết kế để hỗ trợ tra cứu theo thứ tự khóa. Các trường hợp phổ biến:

~~~sql
WHERE customer_id = 42
WHERE total >= 100
WHERE created_at >= timestamp_value
WHERE status IN ('paid', 'pending')
ORDER BY created_at DESC
~~~

B-tree đặc biệt hữu ích cho so sánh bằng, so sánh thứ tự, tìm khoảng và sắp xếp phù hợp.

Tuy nhiên, B-tree không phải tối ưu cho mọi toán tử:

- Tìm một phần tử trong mảng hoặc các khóa JSONB thường cần GIN/operator class phù hợp.
- Các điều kiện địa lý/hình học có thể cần GiST/SP-GiST.
- Tìm chuỗi con theo `LIKE '%term%'` không được B-tree thông thường tối ưu theo cách tìm prefix đơn giản; extension `pg_trgm` với GIN/GiST có thể phù hợp.
- Scan một khoảng thời gian rất rộng trên bảng append-only hàng tỷ hàng có thể cân nhắc BRIN.

**Không đặt index trước rồi hy vọng mọi toán tử sẽ dùng nó.** Hãy bắt đầu từ câu SQL thật và operator mà nó cần.

## 6. Dựng bộ dữ liệu thực hành tái lập được

Bộ dữ liệu dưới đây tạo một schema riêng `index_lab`, 1.000 khách hàng và 100.000 đơn hàng với dữ liệu cố định. Quy mô này đủ để nhiều truy vấn có kế hoạch khác nhau khi `ANALYZE` và tạo index, nhưng kết quả cụ thể vẫn tùy máy, cấu hình, thống kê và PostgreSQL version.

**Cảnh báo:** Script đầu tiên dùng `DROP SCHEMA ... CASCADE` và **xóa toàn bộ schema `index_lab` hiện có**. Chỉ thực hiện trong database lab do bạn sở hữu, không dùng trên database sản xuất hoặc database dùng chung.

### 6.1. Tạo schema

~~~sql
-- CẢNH BÁO: chỉ chạy trên database thực hành riêng.
DROP SCHEMA IF EXISTS index_lab CASCADE;
CREATE SCHEMA index_lab;

CREATE TABLE index_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    tier text NOT NULL
        CHECK (tier IN ('standard', 'silver', 'gold'))
);

CREATE TABLE index_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    customer_id integer NOT NULL
        REFERENCES index_lab.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    created_at timestamptz NOT NULL,
    total numeric(12, 2) NOT NULL CHECK (total >= 0),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    note text
);
~~~

Ngay lúc này đã có index hỗ trợ:

- `customers.customer_id`: do `PRIMARY KEY` tạo.
- `customers.email`: do `UNIQUE` tạo.
- `orders.order_id`: do `PRIMARY KEY` tạo.

Chưa có index riêng trên `orders.customer_id`, `orders.tenant_id`, `orders.status` hoặc `orders.created_at`.

### 6.2. Nạp seed cố định

~~~sql
INSERT INTO index_lab.customers (
    customer_id, full_name, email, tier
)
SELECT
    g,
    'Customer ' || g,
    'customer' || g || '@example.test',
    CASE
        WHEN g % 10 = 0 THEN 'gold'
        WHEN g % 3 = 0 THEN 'silver'
        ELSE 'standard'
    END
FROM generate_series(1, 1000) AS gs(g);

INSERT INTO index_lab.orders (
    order_id,
    tenant_id,
    customer_id,
    status,
    created_at,
    total,
    details,
    note
)
SELECT
    g::bigint,
    ((g - 1) % 20) + 1,
    ((g - 1) % 1000) + 1,
    CASE
        WHEN g % 20 = 0 THEN 'cancelled'
        WHEN g % 5 = 0 THEN 'paid'
        ELSE 'pending'
    END,
    timestamptz '2026-01-01 00:00:00+00'
        + (g % 180) * interval '1 day'
        + (g % 86400) * interval '1 second',
    (10 + (g % 1000))::numeric(12,2),
    jsonb_build_object(
        'channel', CASE
            WHEN g % 4 = 0 THEN 'mobile'
            ELSE 'web'
        END,
        'priority', CASE
            WHEN g % 100 = 0 THEN 'high'
            ELSE 'normal'
        END
    ),
    CASE
        WHEN g % 50 = 0 THEN 'Manual review'
        ELSE NULL
    END
FROM generate_series(1, 100000) AS gs(g);

ANALYZE index_lab.customers;
ANALYZE index_lab.orders;
~~~

Những thuộc tính có chủ đích:

| Thuộc tính | Đặc điểm |
| --- | --- |
| `order_id` | Duy nhất từ 1 đến 100.000 |
| `customer_id` | 1.000 khách hàng, mỗi người khoảng 100 đơn |
| `tenant_id` | 20 tenant, mỗi tenant khoảng 5.000 đơn |
| `status` | 75% pending, 20% paid, 5% cancelled |
| `created_at` | Phân bố theo 180 ngày, có thêm thành phần giây |
| `total` | Giá trị numeric không âm, xác định từ `g` |
| `details` | JSONB có channel và priority |
| `note` | Phần lớn NULL, một số hàng Manual review |

Dữ liệu giả này dùng để minh họa khác biệt về **độ chọn lọc**. Nó không phản ánh chính xác phân bố khách hàng/đơn hàng của một ứng dụng thực tế.

### 6.3. Kiểm tra số hàng

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_count,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_count
FROM index_lab.orders;
~~~

Kết quả dự kiến:

| total_orders | pending_count | paid_count | cancelled_count |
| ---: | ---: | ---: | ---: |
| 100000 | 75000 | 20000 | 5000 |

Nếu bạn đã chạy các ví dụ thay đổi dữ liệu rồi commit, các thống kê có thể khác. Hãy reset lab **có chủ đích** nếu muốn tái lập đúng seed.

## 7. Thí nghiệm đầu tiên: tra theo PRIMARY KEY

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM index_lab.orders
WHERE order_id = 54321;
~~~

Vì `order_id` là `PRIMARY KEY`, PostgreSQL đã có unique B-tree index phục vụ việc tra khóa.

Một kế hoạch **có thể** chứa:

~~~text
Index Scan using orders_pkey on orders ...
  Index Cond: (order_id = 54321)
~~~

Các con số cost, actual time, shared hit/read và tên node bổ sung thay đổi tùy server. Không coi mẫu trên là output chính xác phải có trong mọi lần chạy.

### Đọc ý nghĩa

- `Index Scan`: planner dùng index để tìm tuple phù hợp.
- `Index Cond`: điều kiện có thể áp trong quá trình tìm entry của index.
- `actual rows`: số hàng thực tế ở node.
- `Buffers: shared hit/read`: thông tin buffer PostgreSQL dùng khi truy cập dữ liệu.
- `Execution Time`: thời gian thực thi trong lần đo, chịu ảnh hưởng cache và độ tải.

Truy vấn chọn một hàng trong 100.000 hàng là tình huống **có độ chọn lọc cao**, thường phù hợp index.

## 8. Thí nghiệm thứ hai: status phổ biến và Seq Scan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM index_lab.orders
WHERE status = 'pending';
~~~

`pending` chiếm khoảng 75% bảng. Dù tạo index đơn cột:

~~~sql
CREATE INDEX idx_orders_status
ON index_lab.orders(status);

ANALYZE index_lab.orders;
~~~

planner vẫn có thể chọn `Seq Scan` hoặc `Parallel Seq Scan`, vì cần xử lý phần lớn hàng và một lượt đọc bảng có thể rẻ hơn việc duyệt nhiều entry index rồi kiểm tra heap.

Đây là **bằng chứng khái niệm rằng index không tự bảo đảm tăng tốc**.

### Status hiếm hơn thì sao?

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM index_lab.orders
WHERE status = 'cancelled';
~~~

`cancelled` chỉ khoảng 5%. Planner có thể cân nhắc index, Bitmap Scan hoặc Seq Scan tùy chi phí và cấu trúc dữ liệu.

**Không có một ngưỡng 5%, 10% hay 30% cố định** mà dưới đó PostgreSQL bắt buộc dùng index. Ngưỡng thực tế thay đổi theo độ rộng hàng, số trang, tình trạng cache, correlations và plan cost.

## 9. Index Scan, Bitmap Heap Scan và Seq Scan khác nhau

### 9.1. Seq Scan

~~~text
Seq Scan on orders
  Filter: (...)
~~~

PostgreSQL đọc các trang heap theo trình tự để đánh giá điều kiện cho hàng. Thích hợp khi đọc nhiều hàng hoặc bảng nhỏ.

### 9.2. Index Scan

~~~text
Index Scan using idx_orders_customer ...
  Index Cond: (customer_id = 42)
~~~

PostgreSQL tìm khóa qua index rồi truy cập heap khi cần. Thích hợp với tập kết quả nhỏ hoặc khi index đồng thời hỗ trợ thứ tự LIMIT.

### 9.3. Bitmap Index Scan + Bitmap Heap Scan

~~~text
Bitmap Heap Scan on orders
  Recheck Cond: (...)
  -> Bitmap Index Scan using idx_orders_status ...
       Index Cond: (...)
~~~

PostgreSQL thu thập vị trí trang/hàng khớp từ index, sau đó đọc heap theo bitmap để giảm chi phí truy cập ngẫu nhiên. Có thể kết hợp nhiều index bằng `BitmapAnd`/`BitmapOr` khi planner thấy hợp lý.

### 9.4. Index Only Scan

~~~text
Index Only Scan using some_covering_index ...
  Index Cond: (...)
  Heap Fetches: ...
~~~

Có thể trả cột từ index và **tránh phần lớn lần truy cập heap** khi trang tương ứng được visibility map đánh dấu all-visible. Nếu nhiều trang chưa all-visible, vẫn cần heap fetch để kiểm tra MVCC visibility.

Cụm “Index Only” **không hứa Heap Fetches = 0** trong mọi hoàn cảnh.

## 10. Index giúp ORDER BY và LIMIT như thế nào?

Một yêu cầu thường gặp:

> Cho tôi 10 đơn mới nhất của khách hàng 42.

~~~sql
SELECT
    order_id,
    created_at,
    total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

Nếu chỉ có index trên `customer_id`, PostgreSQL có thể tìm khoảng 100 đơn của khách hàng 42, rồi sort để lấy 10 đơn mới nhất. Với một khách hàng có hàng triệu đơn, chi phí này có thể lớn.

Một index phù hợp cả điều kiện lẫn thứ tự:

~~~sql
CREATE INDEX idx_orders_customer_newest
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

B-tree sắp xếp các entry theo thứ tự cột được định nghĩa. Với `customer_id = 42`, planner có thể duyệt một phần index đã theo `created_at DESC, order_id DESC` và dừng sớm khi lấy đủ 10 hàng.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

**Lợi ích không chỉ là giảm số hàng quét**, mà còn có thể **không cần sort toàn bộ tập hàng** trước khi áp `LIMIT`.

### Khi nào index này không đủ?

Nếu truy vấn lấy 10 đơn mới nhất của **toàn bộ hệ thống** mà không lọc customer:

~~~sql
SELECT order_id, created_at
FROM index_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

index bắt đầu bằng `customer_id` không cung cấp một thứ tự toàn cục chỉ theo `created_at` như yêu cầu. Có thể cần index khác bắt đầu bằng `created_at` nếu workload đó đủ quan trọng.

**Thứ tự các cột trong index nhiều cột phải đi theo query pattern**, không chọn theo thứ tự cột xuất hiện trong schema.

## 11. Composite index và nguyên tắc cột đầu

Một B-tree index nhiều cột:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON index_lab.orders (
    tenant_id,
    status,
    created_at DESC
);
~~~

hữu ích cho truy vấn:

~~~sql
SELECT order_id, created_at
FROM index_lab.orders
WHERE tenant_id = 7
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
~~~

Hai cột đầu dùng so sánh bằng; cột sau hỗ trợ khoảng/thứ tự.

### Có dùng được nếu thiếu cột đầu không?

~~~sql
SELECT order_id
FROM index_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC;
~~~

Không nên **mặc định** index bắt đầu bằng `tenant_id` là lựa chọn tốt cho điều kiện thiếu `tenant_id`. PostgreSQL trong một số phiên bản/tình huống có thể dùng scan trên index nhiều cột hoặc tối ưu như skip scan, nhưng khả năng lọc hiệu quả thường phụ thuộc mạnh vào điều kiện của những cột đầu.

Quy tắc thực hành: với B-tree composite, **đặt các cột so sánh bằng thường xuyên ở phần đầu**, sau đó cân nhắc cột range/sort. Dù vậy, hãy kiểm tra truy vấn thật, vì selectivity và index-only scan có thể thay đổi phương án tốt nhất.

### Một index composite thay thế mọi index đơn cột được không?

Không nhất thiết.

`(tenant_id, status, created_at)` có thể tốt cho lookup theo tenant, nhưng không đồng nghĩa với một index hiệu quả cho tất cả các truy vấn chỉ lọc `created_at` hoặc chỉ sắp xếp theo `created_at` trên toàn hệ thống.

Ngược lại, tạo tất cả các biến thể composite cũng có thể khiến chi phí ghi và dung lượng bùng nổ. Phải chọn tập nhỏ có giá trị rõ ràng.

## 12. Index giúp JOIN qua cột khóa ngoại

Ví dụ:

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.total
FROM index_lab.orders AS o
JOIN index_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id = 42;
~~~

Bảng `customers` có primary key trên `customer_id`, nên tra hàng cha hiệu quả. Nhưng nếu cần tìm các hàng `orders` theo `customer_id`, nên cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_id
ON index_lab.orders(customer_id);
~~~

PostgreSQL **tự tạo index cho PRIMARY KEY và UNIQUE constraint**, nhưng **không tự tạo index trên cột tham chiếu foreign key ở phía bảng con**.

Điểm này đặc biệt quan trọng khi bảng cha bị `DELETE` hoặc đổi key: PostgreSQL phải kiểm tra/thi hành ràng buộc FK ở bảng con. Nếu bảng con lớn mà không có index trên FK, thao tác trên bảng cha có thể cần quét nhiều dữ liệu.

### Có phải mọi FK đều cần index?

Không có luật tuyệt đối. Nếu bảng con rất nhỏ, hoặc workload không bao giờ tìm theo cột đó, index riêng có thể không đáng chi phí. Nhưng với bảng con lớn và truy vấn JOIN/xóa cha thường xuyên, index trên cột tham chiếu là một lựa chọn đáng cân nhắc.

**Kiểm tra index hiện có trước**: trong lab, `idx_orders_customer_newest(customer_id, created_at DESC, order_id DESC)` cũng bắt đầu bằng `customer_id`, nên có thể phục vụ nhiều truy vấn theo FK. Tạo thêm `idx_orders_customer_id` có thể trùng lợi ích đọc một phần và tăng chi phí ghi không cần thiết.

## 13. Index bảo đảm tính duy nhất, không chỉ tốc độ

Khi khai báo:

~~~sql
CREATE TABLE index_lab.order_requests (
    request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    external_code text NOT NULL,
    request_amount numeric(12,2) NOT NULL,
    CONSTRAINT uq_order_request
        UNIQUE (tenant_id, external_code)
);
~~~

PostgreSQL tạo unique index phục vụ `uq_order_request`. Nó có hai vai trò:

1. Giúp tìm hàng theo `tenant_id` + `external_code`.
2. **Ngăn hai transaction commit hai hàng có cùng cặp khóa**, kể cả khi cả hai đều kiểm tra trước và tưởng chưa tồn tại.

~~~sql
INSERT INTO index_lab.order_requests
    (tenant_id, external_code, request_amount)
VALUES (1, 'REQ-001', 100.00)
ON CONFLICT (tenant_id, external_code)
DO NOTHING
RETURNING request_id;
~~~

**Unique index mang lại bảo đảm dữ liệu**, không chỉ lợi ích tối ưu đọc. Không được xóa một unique constraint quan trọng chỉ vì thống kê cho thấy nó ít được scan bởi các câu SELECT.

Tuy nhiên uniqueness có chi phí:

- Khi chèn khóa mới phải kiểm tra xung đột.
- Khi nhiều phiên ghi cùng một key có thể phát sinh wait/contension.
- Index phải được duy trì cho những thay đổi liên quan.
- Một upsert `ON CONFLICT DO UPDATE` còn có công việc UPDATE và lock.

Index giúp bảo vệ tính đúng, nhưng không tự biến mọi upsert thành thao tác idempotent. `SET count = count + 1` trong nhánh conflict vẫn có thể lặp hiệu ứng nếu request được retry.

## 14. Chi phí của một INSERT khi bảng có nhiều index

Giả sử bảng `orders` có:

~~~text
1. PRIMARY KEY(order_id)
2. INDEX(customer_id, created_at DESC, order_id DESC)
3. INDEX(tenant_id, status, created_at DESC)
4. INDEX(status)
5. INDEX(created_at)
6. INDEX expression/partial khác
~~~

Khi `INSERT` một hàng mới:

1. PostgreSQL ghi tuple vào heap theo cơ chế bảng và WAL phù hợp.
2. Với những index mà hàng thuộc phạm vi index, PostgreSQL phải tạo entry cần thiết.
3. Unique index phải thực hiện kiểm tra duy nhất và xử lý cạnh tranh với transaction khác.
4. Index page có thể cần đọc/ghi vào buffer, cập nhật WAL và đôi khi tách trang (*page split*).
5. Các ràng buộc, trigger và FK cũng có thể làm tăng công việc của statement.

~~~mermaid
flowchart TD
    I["INSERT orders"] --> H["Ghi tuple vào heap"]
    I --> PK["Bảo trì PRIMARY KEY index"]
    I --> C["Bảo trì customer index"]
    I --> T["Bảo trì tenant/status index"]
    I --> D["Bảo trì date/status/JSON index nếu có"]
    H --> W["WAL / buffers / I/O"]
    PK --> W
    C --> W
    T --> W
    D --> W
~~~

Đây là **sơ đồ về những loại công việc**, không phải bảo đảm chính xác thứ tự vật lý của PostgreSQL.

### Có phải thêm một index làm INSERT chậm đúng 10%?

Không có hệ số cố định. Chi phí còn phụ thuộc kích thước index, dữ liệu có nằm trong cache không, số entry, số trang phải ghi, phân bố key (tuần tự hay ngẫu nhiên), uniqueness, fillfactor, contention và thiết bị lưu trữ.

Nhưng quy tắc định tính rất quan trọng:

> **Mỗi index bổ sung có thể tạo thêm công việc khi ghi**. Vì vậy, lợi ích đọc phải đủ lớn để bù chi phí bảo trì.

## 15. Chi phí của UPDATE trong PostgreSQL gắn với MVCC

PostgreSQL dùng MVCC, nên một câu `UPDATE` thông thường tạo **một phiên bản tuple mới** trong heap. Phiên bản cũ có thể phải giữ lại cho các snapshot đang hoạt động.

~~~sql
UPDATE index_lab.orders
SET note = 'Checked'
WHERE order_id = 1001;
~~~

Ngay cả khi `note` không nằm trong một index nào, thao tác vẫn có thể cần tạo phiên bản tuple mới trong heap, ghi WAL và có công việc vacuum về sau.

Vậy index ảnh hưởng đến UPDATE thế nào?

### Khi cột được index thay đổi

~~~sql
UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id = 1001;
~~~

Nếu bảng có index chứa `status`, entry trong index có thể phải thay đổi để phản ánh khóa mới. Điều này tăng công việc ghi so với một UPDATE chỉ đổi thuộc tính không liên quan index.

### Khi cột không được index thay đổi

~~~sql
UPDATE index_lab.orders
SET note = 'Checked'
WHERE order_id = 1001;
~~~

PostgreSQL có thể tối ưu bằng **HOT update (Heap-Only Tuple)** nếu các điều kiện phù hợp, giúp tránh tạo index entry mới cho các phiên bản tương ứng.

**Không đồng nghĩa rằng UPDATE trên cột không index luôn là HOT.** Còn phụ thuộc không gian trống trên cùng heap page và những chỉ mục khác, bao gồm index expression, partial index predicate hoặc included columns có liên quan.

## 16. HOT update: lý do index có thể khiến UPDATE tốn hơn rất nhiều

**HOT** là một tối ưu MVCC của PostgreSQL. Khi UPDATE không thay đổi những cột cần thiết cho việc duy trì index và phiên bản mới có thể nằm trên cùng heap page theo điều kiện PostgreSQL, các entry index cũ có thể tiếp tục dẫn tới chuỗi phiên bản tuple trong heap, thay vì phải tạo entry mới trong từng index.

~~~text
Không HOT (minh họa):
   UPDATE
      ├─ heap tuple version mới
      ├─ index A entry mới
      ├─ index B entry mới
      └─ index C entry mới

HOT khi đủ điều kiện (minh họa):
   UPDATE
      ├─ heap tuple version mới cùng trang
      └─ chain heap được duy trì;
         có thể tránh tạo entry mới cho các index
~~~

### Vì sao index thừa làm giảm cơ hội HOT?

Giả sử bảng có cột `updated_at`. Nếu bạn tạo index trên `updated_at` vì nghĩ “có thể hữu ích sau này”, nhưng hầu hết UPDATE đều sửa `updated_at`, thì những UPDATE này liên quan tới cột được index và có thể mất cơ hội HOT.

Tương tự, một expression index dùng `lower(email)` có thể làm UPDATE email kéo theo chi phí bảo trì chỉ mục. Một partial index có điều kiện theo `status` cũng có thể ảnh hưởng khả năng HOT khi UPDATE status, kể cả khi index lưu cột khác.

**Điều cần xem không chỉ là index có giúp SELECT, mà còn là các cột trong index có thay đổi thường xuyên hay không.**

### Có ngoại lệ kỹ thuật không?

Trong các phiên bản PostgreSQL mới hơn, một số loại index tóm tắt như BRIN có quy tắc tương tác HOT đặc thù. Với thiết kế thông thường, hãy dùng nguyên tắc thực dụng: **các index phải được duy trì khi biểu thức/thuộc tính được index thay đổi, và càng nhiều index liên quan càng dễ tăng chi phí ghi**. Khi tối ưu ở mức thấp, kiểm tra tài liệu và chỉ số thực tế của đúng major version.

## 17. Quan sát HOT bằng thống kê

PostgreSQL cung cấp thông tin về số lượng UPDATE và HOT updates trong `pg_stat_user_tables`:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'index_lab'
ORDER BY relname;
~~~

Ý nghĩa:

- `n_tup_ins`: số tuple được chèn theo thống kê.
- `n_tup_upd`: số tuple được cập nhật.
- `n_tup_hot_upd`: số lần cập nhật thuộc cơ chế HOT.
- `n_tup_del`: số tuple bị xóa.
- `n_dead_tup`: ước lượng số tuple chết, không phải con số vật lý tuyệt đối.

Đây là **các bộ đếm thống kê**, có thể cập nhật trễ, không phải kết quả của một phép đo transaction đơn lẻ ngay lập tức. Không diễn giải một giá trị 0 ngay sau statement là “PostgreSQL không làm gì”.

### Công thức tham khảo

Khi `n_tup_upd > 0`, có thể tham khảo tỷ lệ:

\[
\text{HOT ratio} = \frac{n\_tup\_hot\_upd}{n\_tup\_upd}
\]

Đây là số liệu mô tả quá trình hoạt động của bảng từ lúc bộ đếm bắt đầu, không phải một KPI mục tiêu chung cho mọi workload.

Một tỷ lệ HOT thấp có thể do:

- Cột thường cập nhật nằm trong index.
- Không có đủ chỗ trên heap page.
- Index expression/predicate/INCLUDE liên quan cột thay đổi.
- Phân bố cập nhật, fillfactor và lịch sử bảng.

Không kết luận “index X chắc chắn gây ra mọi non-HOT updates” chỉ từ một tỷ lệ.

## 18. Chi phí của DELETE: tuple chết và dọn index

Khi `DELETE` một hàng, PostgreSQL đánh dấu phiên bản tuple theo quy tắc MVCC; các snapshot cũ vẫn có thể cần đọc nó. Hàng không nhất thiết biến mất tức thì khỏi mọi cấu trúc vật lý ngay khi transaction commit.

~~~sql
BEGIN;

DELETE FROM index_lab.orders
WHERE order_id = 99999
RETURNING order_id;

ROLLBACK;
~~~

Ví dụ rollback để giữ lab nguyên trạng.

Ở hệ thống thật:

1. DELETE có thể dùng index để **tìm hàng cần xóa**.
2. PostgreSQL xử lý MVCC/transaction và ghi WAL cần thiết.
3. Những entry index liên quan phiên bản hàng không được tùy ý thu hồi khi vẫn còn snapshot có thể cần.
4. VACUUM và các cơ chế dọn dẹp thu hồi không gian/entry đủ điều kiện về sau.
5. Nếu nhiều DELETE/UPDATE, có thể tích tụ dead tuples và bloat, ảnh hưởng I/O và hiệu năng đọc/ghi.

**Index có thể giúp tìm nhanh hàng để DELETE, đồng thời chính index cũng là đối tượng cần được bảo trì sau DELETE.** Đây là hai mặt của cùng một lựa chọn thiết kế.

### Index không phải lịch sử xóa

Không dùng index hoặc tuple version cũ làm nơi truy vết nghiệp vụ lâu dài. Muốn biết ai xóa đơn lúc nào, cần audit/event/temporal history phù hợp; VACUUM có thể thu hồi dữ liệu vật lý cũ khi không còn cần cho MVCC.

## 19. WAL, page split và cache: chi phí khó nhìn thấy trong một câu SQL

Một index tạo thêm các chi phí ngoài thời gian CPU:

| Thành phần | Tác động có thể có |
| --- | --- |
| **WAL** | Dữ liệu index thay đổi cần thông tin phục hồi phù hợp |
| **Buffer cache** | Các trang index cạnh tranh RAM với trang heap và index khác |
| **Page split** | Khi trang B-tree đầy và cần chèn key, có thể phải tách trang |
| **Random I/O** | Truy cập nhiều trang index/heap rải rác |
| **Checkpoint/writeback** | Trang dirty cần được ghi xuống lưu trữ theo cơ chế hệ thống |
| **Replica** | WAL phải được truyền và replay; tăng write workload có thể tăng lag |
| **Vacuum/cleanup** | Index cần được dọn/duy trì cùng vòng đời tuple cũ |
| **Backup/restore** | Index chiếm dung lượng và có chi phí dựng lại/khôi phục |
| **DDL** | Tạo index trên bảng lớn cần scan dữ liệu và tài nguyên hệ thống |

Chi phí ghi có thể thể hiện thành:

- Latency của `INSERT`/`UPDATE` tăng.
- Throughput ghi/giây giảm.
- WAL phát sinh nhiều hơn.
- Disk usage và cache pressure tăng.
- Replica hoặc autovacuum phải làm thêm việc.
- Một số hàng/khóa có contention cao.

Không quy tất cả vấn đề chậm cho index. Trigger, FK, lock, thiết bị lưu trữ, transaction dài và workload đồng thời cũng có thể chi phối.

## 20. Index đơn cột, composite, covering và partial: khác biệt về chi phí ghi

Cùng một query, nhiều thiết kế index có thể giúp đọc, nhưng lượng dữ liệu lưu và số hàng phải bảo trì khác nhau.

| Thiết kế | Lợi ích thường gặp | Đánh đổi |
| --- | --- | --- |
| `(customer_id)` | Index nhỏ, lọc theo khách hàng | Có thể cần sort khi yêu cầu mới nhất |
| `(customer_id, created_at DESC)` | Lọc + thứ tự theo khách | Index rộng hơn, ghi nhiều thông tin hơn |
| `(customer_id, created_at DESC) INCLUDE (total)` | Có thể hỗ trợ index-only query cần total | Entry rộng hơn; thay total ảnh hưởng index |
| Partial index `WHERE status='cancelled'` | Index chỉ chứa một tập hàng | Thay status phải duy trì membership, không giúp query khác |
| Expression index `lower(email)` | Tìm theo biểu thức chuẩn hóa | Tính biểu thức khi ghi, duy trì entry |
| GIN trên JSONB | Hỗ trợ các toán tử JSON/array | Có thể nhiều entry cho một hàng và chi phí ghi đáng kể |

**Không có loại index luôn tốt nhất**. Nó phụ thuộc tần suất truy vấn, số hàng khớp, dữ liệu được ghi/sửa, độ rộng tuple, và ngân sách storage.

## 21. Covering index và INCLUDE có thật sự “miễn phí heap” không?

Giả sử truy vấn:

~~~sql
SELECT order_id, created_at, total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

Ta có thể tạo index chứa cột tìm kiếm/thứ tự và dữ liệu trả về:

~~~sql
CREATE INDEX idx_orders_customer_covering
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (total);
~~~

Cột `total` được lưu như **included payload column** thay vì search key. Với index phù hợp và visibility map thuận lợi, planner có thể cân nhắc `Index Only Scan`.

### Ba giới hạn cần nhớ

1. **Visibility:** index-only vẫn có thể phải đọc heap nếu các trang chưa được xác nhận all-visible theo MVCC. Trên bảng được UPDATE thường xuyên, `Heap Fetches` có thể cao.
2. **Dung lượng:** INCLUDE làm entry rộng hơn, có thể tăng số trang index, WAL và chi phí cache/ghi.
3. **UPDATE:** nếu `total` thay đổi, included value trong index cũng cần được duy trì; cơ hội HOT có thể bị giảm.

Index-only không phải mục tiêu tối thượng. Đôi khi một index hẹp kết hợp vài heap fetch là lựa chọn nhanh hơn và rẻ hơn về write amplification.

### Giới hạn của INCLUDE

Cột INCLUDE không đóng vai trò khóa tìm kiếm/sắp xếp như các key columns. Không đưa một cột vào INCLUDE rồi mong PostgreSQL dùng nó như một cột đầu mới để tìm phạm vi index.

## 22. Partial index: giảm kích thước khi chỉ một nhóm hàng quan trọng

Ví dụ nghiệp vụ cần xử lý đơn đã bị hủy, vốn chỉ chiếm 5% seed:

~~~sql
CREATE INDEX idx_orders_cancelled_created
ON index_lab.orders (created_at DESC, order_id)
WHERE status = 'cancelled';
~~~

Truy vấn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM index_lab.orders
WHERE status = 'cancelled'
ORDER BY created_at DESC
LIMIT 20;
~~~

Partial index chỉ bao gồm các hàng thỏa vị từ `status = 'cancelled'`. Vì ít hàng hơn, nó có thể:

- Nhỏ hơn full index có cùng key.
- Cần ít không gian cache hơn.
- Phục vụ tập truy vấn mục tiêu hiệu quả hơn.

### Chi phí ghi có biến mất không?

Không. PostgreSQL vẫn phải xác định hàng có thuộc partial index hay không, và bảo trì index khi:

- INSERT hàng thuộc tập cancelled.
- UPDATE một hàng từ pending/paid thành cancelled.
- UPDATE một hàng từ cancelled sang trạng thái khác.
- UPDATE cột khóa của index khi hàng thuộc tập.

Một partial index thường giảm số entry cần duy trì so với full index rộng, nhưng nó **không bảo đảm mọi ghi ngoài tập đều không có bất kỳ chi phí đánh giá predicate nào**.

### Truy vấn có phải nêu predicate không?

Planner chỉ dùng partial index khi chứng minh được điều kiện query bao hàm vị từ của index. Ví dụ query phải thể hiện một cách planner nhận diện được rằng hàng cần tìm có `status='cancelled'`.

Với **prepared statement có tham số** như `WHERE status = $1`, một generic plan không luôn chứng minh được `$1 = 'cancelled'` cho mọi lần thực thi. Vì thế partial index có thể không được chọn trong một số trường hợp dù giá trị thực tế truyền vào là cancelled.

Đó là khác biệt giữa “index đúng về nghiệp vụ” và “planner chứng minh index áp dụng được trong plan cụ thể”.

## 23. Vì sao không thể tạo index dựa vào now() như một vị từ động?

Ví dụ không hợp lệ:

~~~sql
-- Cố ý sai: now() là STABLE, không IMMUTABLE.
CREATE INDEX idx_bad_recent
ON index_lab.orders(order_id)
WHERE created_at > now() - interval '7 days';
~~~

Membership trong index sẽ đổi **chỉ vì thời gian trôi qua**, trong khi PostgreSQL không tự cập nhật entry mỗi giây cho những hàng cũ.

PostgreSQL yêu cầu các hàm dùng trong index expression/predicate có đặc tính **IMMUTABLE**. Vì vậy không nên bọc `now()` trong một UDF khai báo IMMUTABLE sai để lách kiểm tra.

### Cách thiết kế phù hợp

Index theo giá trị cột:

~~~sql
CREATE INDEX idx_orders_created_at
ON index_lab.orders(created_at);
~~~

và truyền mốc thời gian động vào query:

~~~sql
SELECT order_id
FROM index_lab.orders
WHERE created_at >= now() - interval '7 days';
~~~

`now()` ổn định trong statement nên có thể dùng như một runtime comparison bound thích hợp cho B-tree index.

Với dữ liệu append-only rất lớn, có thể cân nhắc partitioning hoặc BRIN bên cạnh thiết kế mốc thời gian, nhưng đó là một quyết định kiến trúc khác.

## 24. Expression index: tối ưu query nhưng phải trả chi phí tính toán khi ghi

Nếu ứng dụng thường tìm email không phân biệt chữ hoa/thường:

~~~sql
CREATE INDEX idx_customer_lower_email
ON index_lab.customers (lower(email));
~~~

Query phù hợp:

~~~sql
SELECT customer_id
FROM index_lab.customers
WHERE lower(email) = lower('CUSTOMER42@EXAMPLE.TEST');
~~~

Expression index lưu giá trị đã tính của biểu thức cho từng hàng, có thể tránh phải quét rồi tính `lower(email)` cho mọi hàng khi tra cứu.

### Đổi lại

- INSERT hàng mới phải tính biểu thức và bảo trì index.
- UPDATE cột email có thể cần tính lại biểu thức/index entry.
- Index chiếm không gian lưu trữ.
- Query cần có biểu thức/operator phù hợp để planner dùng hiệu quả.
- Với collation/extension thay đổi, có thể cần xem xét REINDEX và tính nhất quán của dữ liệu index.

Nếu email đã có unique index dạng text và workload không cần case-insensitive lookup, expression index mới có thể là **chi phí ghi không mang lại giá trị đáng kể**.

## 25. Một index JSONB có thể đắt hơn bạn tưởng

Bảng `orders` có:

~~~sql
details jsonb
~~~

Giả sử query thường hỏi:

~~~sql
SELECT order_id
FROM index_lab.orders
WHERE details @> '{"priority":"high"}'::jsonb;
~~~

Một GIN index có thể hỗ trợ containment tùy operator class:

~~~sql
CREATE INDEX idx_orders_details_gin
ON index_lab.orders
USING gin (details);
~~~

GIN hữu ích với dữ liệu chứa **nhiều khóa/giá trị hoặc phần tử** vì nó lập cấu trúc để tìm các phần tử bên trong JSON/array.

Nhưng khi ghi một JSONB object, index có thể cần xử lý nhiều entry liên quan. Dung lượng và độ trễ ghi có thể cao hơn một B-tree index đơn giản theo một cột scalar.

### Cân nhắc thiết kế cột riêng

Nếu hệ thống **chỉ** lọc một thuộc tính `priority` và thuộc tính đó là phần quan trọng trong schema nghiệp vụ, có thể cân nhắc lưu thêm một cột typed `priority`/generated phù hợp thay vì index toàn bộ JSONB không cần thiết.

Ngược lại, nếu query cần nhiều khóa JSONB linh hoạt, GIN có thể hợp lý. Chọn theo workload thực tế, không đánh đồng “JSONB” với “phải có GIN”.

## 26. BRIN: một lựa chọn cho bảng cực lớn, tương quan vật lý

**BRIN (Block Range Index)** lưu thông tin tóm tắt theo các khoảng block heap, thay vì lưu một entry khóa chi tiết tương tự B-tree cho từng hàng theo cách thông thường.

Đặc biệt hữu ích khi:

- Bảng rất lớn.
- Dữ liệu được thêm chủ yếu theo thứ tự thời gian hoặc một trường tăng dần.
- Giá trị cột có tương quan tương đối tốt với vị trí vật lý trong heap.
- Chấp nhận phải đọc và lọc lại một số block ứng viên.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_created_brin
ON index_lab.orders
USING brin (created_at);
~~~

Với seed đơn hàng và độ tương quan vật lý phù hợp từng trường hợp, BRIN có thể nhỏ hơn B-tree rất nhiều, nhưng không nhất thiết tốt hơn cho tìm một hàng theo thời điểm cụ thể.

### BRIN có chính xác không?

BRIN thường là một **lossy index**: nó cho biết khoảng block **có khả năng** chứa hàng thỏa điều kiện. PostgreSQL sau đó kiểm tra lại hàng thực tế để loại false positives.

So sánh khái niệm:

| Đặc tính | B-tree | BRIN |
| --- | --- | --- |
| Tra chính xác một key | Thường rất tốt | Không phải mục tiêu chính |
| Kích thước trên bảng lớn | Có thể lớn | Thường rất nhỏ nếu phù hợp |
| Dữ liệu không tương quan vị trí vật lý | Vẫn hữu dụng | Có thể phải đọc nhiều block không liên quan |
| Ghi dữ liệu append-only | Có chi phí entry theo index | Chi phí tóm tắt theo block range có thể thấp hơn |
| Quét khoảng thời gian lớn | Tùy selectivity | Có thể phù hợp khi dữ liệu clustered theo thời gian |

Lưu ý rằng seed lab phân bố `created_at` theo `g % 180`, không phải tăng đơn điệu, nên **không được mặc định BRIN sẽ thể hiện ưu thế lớn** ở lab này. Cần thử trên phân bố giống production.

## 27. Những loại index chính của PostgreSQL

| Loại | Phù hợp thường gặp | Cân nhắc chi phí |
| --- | --- | --- |
| **B-tree** | So sánh bằng, khoảng, sắp xếp, uniqueness | Entry cho các khóa; maintenance khi ghi |
| **Hash** | So sánh bằng theo toán tử phù hợp | Ít đa dụng hơn B-tree; không phục vụ ORDER BY/range |
| **GiST** | Các loại dữ liệu/toán tử đặc thù như không gian, range, nearest-neighbor khi opclass hỗ trợ | Tùy toán tử, có thể lossy/recheck |
| **SP-GiST** | Dữ liệu phù hợp phân hoạch không gian/cấu trúc phân tách | Phụ thuộc cấu trúc dữ liệu và operator class |
| **GIN** | Arrays, JSONB, full-text/trigram với opclass phù hợp | Có thể có nhiều entry cho một hàng và chi phí update |
| **BRIN** | Bảng rất lớn, cột tương quan với block heap | Nhỏ và gọn, nhưng scan lossy; có thể đọc nhiều block ứng viên |

PostgreSQL mặc định dùng B-tree khi viết `CREATE INDEX ... ON table(column)` mà không chỉ `USING`.

**Không phải mỗi loại đều dùng được cho mọi kiểu dữ liệu/toán tử.** Chỉ mục cần operator class phù hợp; đôi khi còn cần extension, ví dụ `pg_trgm` cho tìm chuỗi con.

## 28. Index có thể làm tăng contention trong workload ghi

Không chỉ tốn CPU và I/O, index còn có thể làm nhiều transaction tranh tài nguyên.

Ví dụ một bảng request có unique index trên:

~~~sql
UNIQUE (tenant_id, external_code)
~~~

Nếu 100 request đồng thời cố tạo cùng `external_code`, PostgreSQL phải phối hợp kiểm tra uniqueness. Một số transaction có thể chờ transaction khác commit/rollback, hoặc đi vào nhánh `ON CONFLICT`.

Các loại contention khác:

- Nhiều INSERT vào những trang B-tree đang nóng.
- Nhiều UPDATE cùng key hoặc vùng dữ liệu, vốn đã có row-level locks.
- Page split và hoạt động maintenance.
- Các transaction DDL tạo/rebuild index chạy song song với workload.
- FK/trigger và các constraint dựa vào index.

**Không nên quy mọi lock wait cho index**. Lock hàng, lock bảng, FK và DDL cũng có thể là nguyên nhân. Cần đo loại wait thực tế bằng `pg_stat_activity`, `pg_locks` và công cụ quan sát phù hợp.

## 29. Index không làm thay đổi tính đúng đắn của SELECT

Với cùng statement và snapshot, PostgreSQL phải trả kết quả logic phù hợp dù dùng `Seq Scan` hay `Index Scan`. Index là cách truy cập, không phải “phiên bản dữ liệu đáng tin hơn”.

Ví dụ:

~~~sql
SELECT *
FROM index_lab.orders
WHERE customer_id = 42;
~~~

Dù planner chọn index hay seq scan, tập hàng phải tuân `WHERE` và MVCC. Nó không được tự bỏ qua hàng chỉ vì index đang được vacuum hoặc một transaction khác chưa commit thay đổi.

Ngoại lệ về mặt mục tiêu nghiệp vụ: unique index/constraint **có thể ảnh hưởng tính hợp lệ của thao tác ghi**; đó là vai trò ràng buộc chứ không phải tối ưu SELECT.

### ORDER BY mới cam kết thứ tự

Một Index Scan có thể tình cờ trả hàng theo thứ tự index, nhưng **không có `ORDER BY` thì SQL không cam kết thứ tự hàng kết quả**. Đừng bỏ `ORDER BY` chỉ vì query hôm nay đang dùng B-tree.

## 30. EXPLAIN: đọc kế hoạch trước khi tạo thêm index

Trước khi thêm index mới, nên kiểm tra truy vấn chậm:

~~~sql
EXPLAIN
SELECT order_id, total
FROM index_lab.orders
WHERE customer_id = 42;
~~~

`EXPLAIN` không có `ANALYZE` chỉ cho **kế hoạch ước lượng**.

Để đo truy vấn SELECT trong lab:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total
FROM index_lab.orders
WHERE customer_id = 42;
~~~

Chú ý những thông tin:

| Thông tin trong plan | Câu hỏi nên hỏi |
| --- | --- |
| `Seq Scan` | Có đang cần nhiều hàng? Bảng nhỏ? Không có index phù hợp? |
| `Index Scan` | Index Cond dùng được những cột/toán tử nào? |
| `Bitmap Heap Scan` | Bao nhiêu block phải truy cập/recheck? |
| `Index Only Scan` | Có bao nhiêu `Heap Fetches`? |
| `Filter` | Có nhiều hàng bị loại sau khi đọc không? |
| `Rows Removed by Filter` | Có đang đọc quá rộng rồi mới lọc? |
| `Sort` | Index có thể hỗ trợ thứ tự query không? |
| `actual rows` vs `rows` ước lượng | Thống kê có dự đoán đúng không? |
| `Buffers: shared hit/read` | Đang đọc cache hay phải đọc block mới vào buffer? |
| `Planning/Execution Time` | Chi phí nằm ở planning hay execution? |

Không so sánh một lần chạy trước với một lần chạy sau rồi kết luận tuyệt đối: lần sau có thể hưởng lợi từ cache nóng. Với số liệu nghiêm túc, thử nhiều lần, kiểm soát workload và so sánh các lựa chọn trên môi trường tương đương.

## 31. EXPLAIN ANALYZE trên UPDATE/DELETE là thao tác thực

Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id = 1001;
~~~

**Câu này thực sự chạy UPDATE.** Nó không phải chế độ “chỉ mô phỏng”. Nếu dùng để học trên lab:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id = 1001;

ROLLBACK;
~~~

`ROLLBACK` hoàn tác thay đổi dữ liệu transaction trong database, nhưng không nhất thiết hoàn tác mọi side effect ngoài transaction hoặc mọi sequence đã cấp. Vì vậy, không dùng `EXPLAIN ANALYZE` cho lệnh ghi trên production chỉ để xem plan khi chưa có kế hoạch an toàn.

### Điều quan sát khi ghi

- Node tìm hàng bằng index hay seq scan.
- Số hàng thực tế bị ảnh hưởng.
- Chi phí trigger/FK nếu được báo cáo.
- Buffer/WAL trong các tùy chọn được version hỗ trợ.
- Thời gian chờ lock (cần xem thêm công cụ riêng).
- Thời gian commit và write throughput ở workload thật.

Một plan tìm hàng nhanh không có nghĩa toàn statement ghi nhanh, bởi phần bảo trì nhiều index có thể chiếm chi phí đáng kể.

## 32. Đo kích thước index bằng catalog

Kiểm tra các index hiện có của `orders`:

~~~sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_index AS x
    ON x.indrelid = t.oid
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'index_lab'
  AND t.relname = 'orders'
ORDER BY pg_relation_size(i.oid) DESC;
~~~

Một cách nhìn tổng quan:

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size('index_lab.orders'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('index_lab.orders'::regclass)
    ) AS all_indexes_size,
    pg_size_pretty(
        pg_total_relation_size('index_lab.orders'::regclass)
    ) AS total_relation_size;
~~~

Trong đó:

- `pg_table_size`: dung lượng bảng và các thành phần liên quan, **không gồm index**.
- `pg_indexes_size`: tổng dung lượng index của bảng.
- `pg_total_relation_size`: tổng dung lượng bảng cùng index và thành phần liên quan.

Các số này thay đổi theo lượng dữ liệu, cấu hình lưu trữ, page fill, VACUUM và việc đã tạo những index nào trước khi đo.

### Không chỉ nhìn thời gian query

Một index giúp tiết kiệm 5 ms ở truy vấn mỗi ngày nhưng tốn hàng GB và làm chậm hàng triệu INSERT/ngày có thể là lựa chọn xấu. Cần tính tổng **chi phí đọc + ghi + lưu trữ + vận hành**.

## 33. Theo dõi index có được truy cập hay không

View `pg_stat_user_indexes` cung cấp thống kê truy cập index:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'index_lab'
ORDER BY relname, indexrelname;
~~~

Ý nghĩa phổ biến:

- `idx_scan`: số lần bắt đầu một index scan được thống kê.
- `idx_tup_read`: số index entries được xử lý/đọc theo cơ chế thống kê của index scan.
- `idx_tup_fetch`: số heap tuples được fetch theo các kiểu index scan được thống kê, có các giới hạn theo kiểu truy cập.

**Không suy chỉ từ `idx_scan = 0` rằng một index chắc chắn vô dụng và xóa được ngay.**

Một index có thể:

- Bảo vệ UNIQUE/PRIMARY KEY mà không xuất hiện như một truy vấn SELECT thường.
- Phục vụ query hiếm nhưng rất quan trọng (cuối tháng, kỳ báo cáo, xử lý sự cố).
- Mới được tạo hoặc thống kê vừa reset.
- Được dùng với tần suất thấp nhưng tránh một full scan rất đắt.
- Là một phần kế hoạch query phụ thuộc vào thời gian, tham số hoặc data distribution.

### Các bộ đếm có lịch sử và độ trễ

Thống kê có thể bị reset và cập nhật không tức thì. Khi đánh giá “index có nên bỏ không”, cần xem **khoảng thời gian quan sát đủ dài**, workload theo giờ/ngày/tháng và các truy vấn trong ứng dụng thực tế.

Không dùng một snapshot thống kê tại thời điểm bất kỳ để quyết định drop index trên production.

## 34. So sánh chi phí đọc và ghi bằng thí nghiệm lab

Có thể thử hai nhóm thao tác trong **database lab riêng**.

### 34.1. Đọc khi chỉ có PRIMARY KEY và một số index

~~~sql
ANALYZE index_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

Nếu đã tạo `idx_orders_customer_newest`, kế hoạch có thể khác so với lúc chưa tạo. Ghi lại plan và số buffer trên môi trường của mình.

### 34.2. Bổ sung index phù hợp

~~~sql
CREATE INDEX IF NOT EXISTS idx_orders_customer_newest
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);

ANALYZE index_lab.orders;
~~~

Đo lại truy vấn SELECT ở bước trước. Đừng chỉ nhìn thời gian, hãy xem có giảm số hàng/blocks phải duyệt và có còn Sort hay không.

### 34.3. Thử UPDATE cột không được index và cột được index

~~~sql
BEGIN;

UPDATE index_lab.orders
SET note = 'Reviewed'
WHERE order_id BETWEEN 20001 AND 20100;

ROLLBACK;
~~~

So với:

~~~sql
BEGIN;

UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id BETWEEN 20001 AND 20100;

ROLLBACK;
~~~

Trên schema có index `status`, thao tác thứ hai có thể phát sinh maintenance index và giảm cơ hội HOT. Nhưng đây **không phải một benchmark chính xác** chỉ với một lần chạy: hai loại UPDATE khác về dữ liệu, số hàng có thể đổi thực sự, cache, WAL và điều kiện HOT.

Muốn đánh giá production, đo trên dữ liệu và workload tương đương với nhiều lượt thử, thời gian đủ dài và thống kê HOT/WAL/index size. Không dùng ví dụ nhỏ để kết luận hệ số tăng/giảm hiệu năng.

## 35. Tạo index là công việc có chi phí và có thể gây lock

Trên bảng lớn đang phục vụ ứng dụng, lệnh:

~~~sql
CREATE INDEX idx_orders_created_normal
ON index_lab.orders(created_at);
~~~

cần đọc dữ liệu bảng, sắp xếp/xây dựng cấu trúc cần thiết, sử dụng tài nguyên hệ thống và áp dụng những loại khóa theo cơ chế `CREATE INDEX` thông thường. Nó có thể chặn một số thao tác ghi đồng thời trong quá trình dựng index.

PostgreSQL hỗ trợ:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_concurrently
ON index_lab.orders(created_at);
~~~

`CONCURRENTLY` được thiết kế để giảm mức chặn thao tác ghi thông thường khi dựng index, nhưng **không miễn phí**:

- Có thể cần nhiều lượt scan bảng và chờ những transaction/snapshot liên quan.
- Thường tốn thời gian và tài nguyên hơn cách tạo index thông thường.
- Không được chạy bên trong một transaction block explicit.
- Nếu thất bại, có thể để lại một index **INVALID** cần được kiểm tra và xử lý.
- Có các hạn chế/concurrency rules đối với việc chạy nhiều lệnh tạo index concurrent trên cùng bảng.

**Không chạy cả hai câu tạo cùng mục đích trong production chỉ để “an toàn hơn”.** Phải chọn tên, cách triển khai, thời điểm và kế hoạch rollback phù hợp.

### Kiểm tra trạng thái index

~~~sql
SELECT
    i.relname AS index_name,
    x.indisvalid,
    x.indisready
FROM pg_index AS x
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE x.indrelid = 'index_lab.orders'::regclass
ORDER BY i.relname;
~~~

`indisvalid = false` báo index chưa hợp lệ cho mục đích dùng trong planner theo tình trạng catalog. Một index invalid vẫn có thể có tác động bảo trì trong một số trạng thái; cần xác định nguyên nhân và khôi phục theo tài liệu.

## 36. Xóa index cũng phải có kế hoạch

Nếu một index đã chứng minh không còn cần thiết, có thể xóa bằng:

~~~sql
-- Chỉ ví dụ trên index lab không phục vụ unique/PK.
DROP INDEX index_lab.idx_orders_created_normal;
~~~

Với môi trường đang ghi mạnh, có `DROP INDEX CONCURRENTLY` để giảm chặn tương ứng nhưng có những hạn chế riêng, bao gồm **không chạy trong transaction block explicit**, và không thể dùng một cách tùy tiện cho index hỗ trợ constraint.

Không tự drop index của `PRIMARY KEY`/`UNIQUE` quan trọng. Thông thường index đó gắn với constraint, và xóa constraint có thể làm mất bảo đảm dữ liệu.

### Trước khi xóa index cần hỏi

1. Index này có đang bảo vệ unique/primary key/exclusion không?
2. Truy vấn ở cuối tháng, batch job hoặc khôi phục sự cố có dùng nó không?
3. Có query theo tenant hoặc FK phụ thuộc không?
4. Một index khác có thực sự thay thế đầy đủ chức năng không?
5. Sau khi drop, các plan có xấu đi đáng kể không?
6. Có cách rollback nhanh, bảo đảm thời gian dựng lại không?
7. Có cần `CONCURRENTLY` và kiểm soát transaction không?

Mục tiêu không phải “ít index nhất” bằng mọi giá mà là **không giữ index không mang lại lợi ích tương xứng với chi phí**.

## 37. REINDEX, bloat và bảo trì index

Với workload nhiều UPDATE/DELETE, cấu trúc index có thể có phần không gian chưa được sử dụng hiệu quả theo thời gian. PostgreSQL có các cơ chế vacuum cleanup và B-tree maintenance, nhưng đôi khi vẫn cần xem xét **REINDEX** khi có dấu hiệu bloat/biến đổi collation/corruption hoặc yêu cầu bảo trì đặc biệt.

Ví dụ cú pháp:

~~~sql
-- Chỉ xem như lệnh tham khảo, không chạy tùy tiện trên production.
REINDEX INDEX index_lab.idx_orders_customer_newest;
~~~

Có các biến thể `REINDEX CONCURRENTLY` ở phiên bản PostgreSQL hỗ trợ, với các hạn chế riêng về transaction và các loại đối tượng.

**REINDEX không phải thao tác cần làm hàng ngày chỉ vì bảng nhiều UPDATE.** Nó có thể tốn I/O, CPU, WAL, không gian đĩa và tranh chấp tài nguyên. Đầu tiên cần hiểu nguyên nhân bloat, autovacuum, transaction dài và mẫu ghi.

### VACUUM và REINDEX khác nhau

- **VACUUM**: dọn phiên bản tuple/index entries đủ điều kiện, bảo trì visibility/freeze và các cấu trúc liên quan.
- **REINDEX**: xây dựng lại một index, thường tạo cấu trúc index mới từ dữ liệu hiện hành phù hợp.

VACUUM không nhất thiết trả mọi byte dung lượng index về OS, còn REINDEX không thay vai trò vacuum/freeze của heap.

## 38. Fillfactor và tối ưu ghi: không có công thức chung

PostgreSQL cho phép một số storage parameters như `fillfactor` để ảnh hưởng cách các trang được lấp đầy.

- Với **heap table**, để lại một phần không gian trống có thể tăng cơ hội HOT khi UPDATE.
- Với **B-tree index**, fillfactor ảnh hưởng không gian dành cho entry mới và các thao tác page split theo workload.

Ví dụ tạo bảng lab mới với cấu hình khác:

~~~sql
CREATE TABLE index_lab.update_hot_demo (
    id bigint PRIMARY KEY,
    frequently_changed_note text
) WITH (fillfactor = 80);
~~~

Đây chỉ là ví dụ cú pháp. **Không nên áp fillfactor 80 cho mọi bảng**: giảm fillfactor tăng số trang dùng để lưu cùng lượng dữ liệu, có thể làm scan/cache kém hiệu quả. Lợi ích chỉ rõ khi tỷ lệ UPDATE và mức tăng kích thước tuple phù hợp.

Một cấu hình “tốt nhất” phụ thuộc read/write mix, đặc tính page fill, cột được cập nhật, bloat và tài nguyên lưu trữ.

## 39. Phân vùng bảng có thay thế index không?

**Partitioning** chia bảng logic thành những phân vùng, ví dụ theo tháng hoặc tenant. PostgreSQL có thể **partition prune** để tránh đọc các phân vùng không liên quan khi query có điều kiện phù hợp.

Nhưng:

- Mỗi partition vẫn có thể cần index để tìm một số ít hàng trong partition.
- Index giúp truy cập hàng, partitioning giúp giới hạn **phạm vi bảng/partition** cần xét.
- Quá nhiều partition/index cũng tăng overhead metadata, planning, maintenance và DDL.
- Thiết kế unique constraints trên partitioned table có quy tắc riêng liên quan partition key.

Ví dụ đơn giản: một bảng partition theo tháng có thể giảm phạm vi quét của query theo tháng, nhưng truy vấn lấy đơn theo `order_id` trong một tháng vẫn có thể cần B-tree index trên khóa đó.

**Không dùng partitioning như một “index khổng lồ” thay thế mọi phương pháp tối ưu đọc.**

## 40. Tại sao tạo index cho mọi cột là một anti-pattern?

Giả sử bảng có 30 cột và người viết tạo index cho từng cột vì “sau này có thể lọc”. Điều này làm:

- Nhiều index cần được bảo trì khi INSERT.
- UPDATE cột nào cũng dễ đụng một index, giảm cơ hội HOT.
- DELETE/VACUUM có thêm việc.
- Tổng storage lớn.
- Thêm index không nhất thiết tạo đúng composite key/order cần cho query quan trọng.
- Planner phải cân nhắc nhiều khả năng hơn, dù không phải lúc nào cũng tăng planning time một cách đáng kể.
- Có thể tồn tại các index gần như trùng nhau.

**Chiến lược tốt hơn: đo và chọn theo các query pattern thật.**

~~~text
Query quan trọng
    ↓
WHERE / JOIN / ORDER BY / LIMIT
    ↓
Cardinality + selectivity + phân bố dữ liệu
    ↓
Index phù hợp tối thiểu
    ↓
EXPLAIN (ANALYZE, BUFFERS)
    ↓
Đo chi phí ghi + dung lượng + HOT/WAL
    ↓
Giữ, sửa hoặc bỏ index có lý do
~~~

## 41. Các trường hợp không nên vội tạo index

### 41.1. Bảng rất nhỏ

Một bảng cấu hình 20 hàng có thể được quét tuần tự nhanh hơn việc dùng index.

### 41.2. Query cần phần lớn hàng

~~~sql
SELECT COUNT(*)
FROM index_lab.orders
WHERE status = 'pending';
~~~

Với 75% hàng pending, Seq Scan có thể hợp lý.

### 41.3. Truy vấn ít chạy

Một index lớn phục vụ truy vấn mỗi năm một lần chưa chắc đáng chi phí ghi hàng ngày.

### 41.4. Cột thay đổi liên tục

Index trên cột `updated_at` nếu mọi UPDATE đều sửa nó có thể làm write amplification tăng mạnh. Chỉ nên tạo nếu query theo thời gian cập nhật quan trọng và đem lại lợi ích thực tế.

### 41.5. Query dùng biểu thức không khớp index

Ví dụ index trên `email` không tự đồng nghĩa query `WHERE lower(email) = ...` luôn dùng được như lookup hiệu quả. Cần expression index hoặc một mô hình normalization phù hợp.

### 41.6. Thống kê chưa được cập nhật

Nếu planner ước lượng sai sau khi nạp lượng dữ liệu lớn, có thể cần `ANALYZE` trước khi kết luận “thiếu index”.

### 41.7. Đã có index composite bao phủ nhu cầu chính

Nếu `(customer_id, created_at DESC)` đã phục vụ lookup theo customer, thêm index `(customer_id)` có thể đem lợi ích nhỏ hơn chi phí ghi mới. Cần kiểm tra query thực tế, không xóa index theo suy đoán.

## 42. Những lỗi thường gặp khi đánh giá index

### 42.1. Nghĩ index luôn làm SELECT nhanh hơn

Planner có thể chọn Seq Scan vì đọc quá nhiều hàng hoặc bảng quá nhỏ.

### 42.2. Chỉ đo query đọc, bỏ qua throughput ghi

Một index tăng tốc báo cáo nhưng làm chậm hàng triệu INSERT/UPDATE mỗi ngày có thể gây hại tổng thể.

### 42.3. Không nhớ PRIMARY KEY/UNIQUE đã có index

Dễ tạo index trùng cột không cần thiết và làm tăng chi phí ghi.

### 42.4. Nghĩ PostgreSQL tự index phía bảng con của FK

PostgreSQL tự index referenced PRIMARY KEY/UNIQUE; không tự index mọi referencing foreign key.

### 42.5. Tạo index trên status ít giá trị phân biệt rồi kỳ vọng luôn có lợi

Nếu 75% hàng cùng status, một index đơn cột có thể không được dùng.

### 42.6. Không xét thứ tự cột trong composite index

`(customer_id, created_at)` và `(created_at, customer_id)` thường phục vụ những kiểu query khác nhau.

### 42.7. Dùng INCLUDE cho mọi cột trả về

Có thể làm index phình to và khiến UPDATE cột included phải duy trì index, giảm lợi thế HOT.

### 42.8. Tạo index expression/partial với hàm STABLE/VOLATILE

`now()` không IMMUTABLE, không phù hợp làm vị từ index động như “7 ngày gần nhất tính tới bây giờ”.

### 42.9. Cho rằng Index Only Scan không bao giờ đọc heap

Visibility map/MVCC có thể buộc heap fetch, nhất là trên bảng update nhiều.

### 42.10. Nghĩ UPDATE chỉ có chi phí khi cột khóa index đổi

Ngay cả UPDATE cột không index cũng tạo heap tuple version, WAL và công việc vacuum; HOT chỉ giúp giảm một phần index maintenance khi đủ điều kiện.

### 42.11. Nhầm VACUUM với REINDEX

VACUUM phục vụ dọn MVCC; REINDEX xây dựng lại cấu trúc index trong những tình huống cần thiết.

### 42.12. Dùng CREATE INDEX thường trên bảng production lớn mà không xét lock

Quá trình build có thể ảnh hưởng ghi. Cân nhắc CONCURRENTLY, lịch triển khai và khả năng thất bại.

### 42.13. Nghĩ CREATE INDEX CONCURRENTLY không tốn tài nguyên

Nó vẫn scan bảng, tạo WAL/I/O và chờ transaction; có thể lâu hơn tạo index thông thường.

### 42.14. Drop index khi idx_scan bằng 0

Bộ đếm có thể reset, chưa bao phủ đầy đủ workload hoặc index bảo vệ constraint.

### 42.15. Dùng EXPLAIN ANALYZE cho UPDATE mà quên nó ghi thật

ANALYZE thực sự thực thi DML. Chỉ thử trong lab/transaction được kiểm soát.

### 42.16. Nghĩ index quyết định thứ tự trả về mà không có ORDER BY

SQL không bảo đảm thứ tự nếu không ghi ORDER BY, dù plan hiện tại đang dùng index.

### 42.17. Không xét query theo tenant/ownership

Index chỉ có `order_id` có thể tìm hàng nhanh, nhưng truy vấn đa tenant cần bảo đảm điều kiện phân quyền và có thể cần composite key/index theo workload. Index không tự cung cấp bảo mật.

### 42.18. Tạo index BRIN trên dữ liệu phân tán ngẫu nhiên rồi kỳ vọng luôn hiệu quả

BRIN phụ thuộc mạnh vào tương quan vật lý; nếu mỗi block range chứa đủ mọi giá trị, khả năng bỏ qua block kém.

### 42.19. Quên partial index có predicate phải được planner chứng minh

Một generic prepared plan với tham số có thể không sử dụng partial index được như query có hằng rõ ràng.

### 42.20. Chỉ nhìn thời gian một lần chạy

Cache, I/O nền và concurrent workload có thể làm kết quả nhiễu. Cần đo nhiều lần và xem BUFFERS.

## 43. Bài tập có đáp án

Các bài sau dựa vào schema `index_lab` ở mục 6. Với lệnh DML, bọc trong `BEGIN ... ROLLBACK` nếu chỉ thử. Với DDL tạo thêm index, nên chạy trên database lab độc lập, tránh đặt lệnh concurrent trong transaction block.

### Bài 1. Index giải quyết bài toán gì?

**Câu hỏi:** Vì sao tìm `order_id = 54321` trong 100.000 đơn thường nhanh hơn khi có primary key index?

**Đáp án:** PostgreSQL có thể tìm theo khóa qua B-tree, đọc ít dữ liệu hơn so với quét toàn bộ heap, dù lựa chọn thực tế vẫn phụ thuộc planner.

### Bài 2. Vì sao có index status nhưng query pending vẫn Seq Scan?

**Đáp án:** Pending chiếm 75% bảng; scan toàn bộ bảng có thể rẻ hơn việc duyệt nhiều entry index và truy cập heap. Index là lựa chọn theo chi phí, không phải yêu cầu bắt buộc.

### Bài 3. Tạo index cho 10 đơn mới nhất của khách hàng

~~~sql
CREATE INDEX idx_exercise_customer_latest
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

**Đáp án:** Phù hợp với `WHERE customer_id = ? ORDER BY created_at DESC, order_id DESC LIMIT 10`. Nếu đã tạo `idx_orders_customer_newest` tương đương ở mục 10, không cần giữ cả hai index trên production.

### Bài 4. FK có tự tạo index ở bảng con không?

**Đáp án:** Không. Referenced primary key/unique phía cha được index; PostgreSQL không mặc định tạo index ở `orders.customer_id`. Cần cân nhắc theo JOIN và thao tác cập nhật/xóa cha.

### Bài 5. Composite index này phục vụ truy vấn nào?

~~~sql
CREATE INDEX idx_exercise_tenant_status
ON index_lab.orders(tenant_id, status, created_at DESC);
~~~

**Đáp án:** Đặc biệt hữu ích cho truy vấn theo tenant và status, sau đó lấy theo created_at. Không bảo đảm tối ưu truy vấn chỉ lọc created_at trên toàn hệ thống.

### Bài 6. Vì sao INCLUDE(total) có chi phí?

**Đáp án:** Cột total được lưu trong index payload, làm entry lớn hơn và khi total đổi cần bảo trì index, có thể giảm cơ hội HOT. Lợi ích index-only còn phụ thuộc visibility map.

### Bài 7. Partial index dành cho đơn cancelled

~~~sql
CREATE INDEX idx_exercise_cancelled
ON index_lab.orders(created_at DESC)
WHERE status = 'cancelled';
~~~

**Đáp án:** Index chỉ chứa nhóm cancelled, khoảng 5% seed; có thể nhỏ hơn full index tương đương và hữu ích cho query nêu rõ status cancelled.

### Bài 8. Có thể dùng now() trong partial index predicate không?

**Đáp án:** Không hợp lệ theo yêu cầu tính immutable của index predicate. Dùng index trên created_at và so sánh `created_at >= now() - interval '7 days'` trong query.

### Bài 9. INSERT có thêm 5 index thì xảy ra gì?

**Đáp án:** PostgreSQL có thể phải duy trì entry ở nhiều index, tăng công việc CPU/I/O/WAL/cache và kiểm tra uniqueness nếu có. Không thể suy ra một hệ số latency cố định từ số index.

### Bài 10. UPDATE note có luôn HOT không?

**Đáp án:** Không. Cần cột không ảnh hưởng index và đủ không gian trên cùng heap page cùng các điều kiện nội bộ. Update note vẫn tạo phiên bản tuple mới theo MVCC.

### Bài 11. UPDATE status tác động ra sao khi có index(status)?

**Đáp án:** Thay status có thể làm thay đổi index entry/predicate membership, tốn maintenance và thường làm giảm cơ hội HOT đối với index thông thường.

### Bài 12. Vì sao DELETE không làm file index tự nhỏ ngay?

**Đáp án:** MVCC còn phải giữ phiên bản cần thiết cho snapshot cũ; cleanup/vacuum thu hồi entry đủ điều kiện về sau. Dung lượng file không nhất thiết co ngay.

### Bài 13. So sánh Index Scan với Bitmap Heap Scan

**Đáp án:** Index Scan tra index rồi truy cập heap theo các hàng phù hợp; Bitmap Scan gom vị trí/blocks từ index rồi đọc heap để giảm truy cập rải rác, có thể recheck trong các tình huống lossy.

### Bài 14. Index Only Scan luôn có Heap Fetches bằng 0?

**Đáp án:** Không. Nếu trang heap chưa được visibility map đánh dấu all-visible, PostgreSQL có thể cần heap fetch để kiểm tra MVCC.

### Bài 15. Vì sao GIN có thể tốn hơn khi ghi JSONB?

**Đáp án:** GIN có thể phải ghi nhiều entry liên quan các khóa/giá trị của một JSONB object; có chi phí index size và maintenance khác với B-tree một cột scalar.

### Bài 16. BRIN thích hợp trường hợp nào?

**Đáp án:** Bảng rất lớn với cột có tương quan cao với vị trí vật lý, thường dữ liệu append theo thời gian; nó nhỏ nhưng lossy và có thể phải đọc/recheck nhiều block.

### Bài 17. Cách xem index chiếm bao nhiêu dung lượng?

~~~sql
SELECT
    pg_size_pretty(
        pg_indexes_size('index_lab.orders'::regclass)
    ) AS indexes_size;
~~~

**Đáp án:** Trả tổng dung lượng các index gắn với bảng orders theo hàm PostgreSQL.

### Bài 18. idx_scan = 0 có nên xóa index?

**Đáp án:** Chưa đủ. Cần xem thời gian quan sát, thống kê reset, truy vấn hiếm, unique/PK/FK, workload định kỳ và phương án thay thế.

### Bài 19. CREATE INDEX CONCURRENTLY có chạy trong BEGIN không?

**Đáp án:** Không. PostgreSQL không cho `CREATE INDEX CONCURRENTLY` chạy trong transaction block explicit. Nó giảm một số xung đột với ghi nhưng vẫn tốn thời gian/tài nguyên và có thể để lại index INVALID khi lỗi.

### Bài 20. Vì sao EXPLAIN ANALYZE UPDATE phải cẩn thận?

**Đáp án:** Vì nó thực thi UPDATE. Dùng `EXPLAIN` không ANALYZE cho ước lượng hoặc bọc `BEGIN ... ROLLBACK` trong lab để đo an toàn.

### Bài 21. Tại sao index không thay thế unique constraint?

**Đáp án:** Một index không unique chỉ giúp truy cập nhanh, không cấm trùng. Unique constraint/unique index có nhiệm vụ bảo đảm bất biến không trùng khi ghi đồng thời.

### Bài 22. Index cần thiết cho COUNT(*) trên cả bảng?

~~~sql
SELECT COUNT(*) FROM index_lab.orders;
~~~

**Đáp án:** Không có index thông thường nào tự làm cho PostgreSQL biết một số đếm luôn đúng với snapshot MVCC hiện tại mà không cần xử lý dữ liệu/visibility thích hợp. Planner có thể dùng Seq Scan hoặc các đường khác tùy hoàn cảnh, nhưng không phải cứ tạo index là `COUNT(*)` tức thì.

### Bài 23. Vì sao index trên updated_at có thể gây hại?

**Đáp án:** Nếu hầu hết UPDATE đều thay updated_at, index này phải được bảo trì thường xuyên và có thể mất cơ hội HOT. Chỉ giữ khi query theo updated_at mang lại lợi ích đủ lớn.

### Bài 24. Đề xuất index cho query sau

~~~sql
SELECT order_id, created_at
FROM index_lab.orders
WHERE tenant_id = 7
  AND status = 'cancelled'
ORDER BY created_at DESC
LIMIT 25;
~~~

**Đáp án gợi ý:** B-tree `(tenant_id, status, created_at DESC)` hoặc partial index theo status cancelled với key `(tenant_id, created_at DESC)`. Chọn theo tỷ lệ cancelled, các tenant và workload ghi thực tế, rồi đo EXPLAIN.

## 44. Quy trình thiết kế index theo workload

Một quy trình thực tế:

1. **Thu thập truy vấn quan trọng** từ application, logs, `pg_stat_statements` nếu extension được bật và bạn có quyền thích hợp.
2. **Xác định vấn đề:** latency, đọc quá nhiều block, sort lớn, JOIN chậm, lock khi xóa cha hay yêu cầu uniqueness.
3. **Đọc plan hiện tại** bằng `EXPLAIN (ANALYZE, BUFFERS)` trong điều kiện an toàn.
4. **Kiểm tra index hiện có:** primary/unique, composite, partial, expression, INCLUDE.
5. **Ước lượng selectivity và cardinality**, xem thống kê của bảng/column có đủ mới không.
6. **Chọn index theo WHERE + JOIN + ORDER BY + LIMIT**, không dựa vào tên cột đơn thuần.
7. **Hỏi truy vấn có cần mọi hàng không:** nếu phần lớn hàng, Seq Scan có thể đúng.
8. **Hỏi cột được index có cập nhật thường xuyên không**, gồm cả predicates, expressions, included columns.
9. **Ước lượng tác động lên INSERT/UPDATE/DELETE, HOT, WAL, VACUUM và storage**.
10. **Đo lợi ích đọc sau khi tạo trong lab/staging** có dữ liệu và workload tương đương.
11. **Đo chi phí ghi**, đừng chỉ đo một lần SELECT.
12. **Kiểm tra contention và transaction dài**, vì index không tự giải quyết lock waits.
13. **Lập kế hoạch triển khai**: CREATE INDEX thông thường hay CONCURRENTLY, lịch maintenance và dung lượng trống.
14. **Theo dõi sau triển khai:** index size, idx_scan, latency, write throughput, HOT ratio, WAL/replica lag.
15. **Dọn các index trùng/không đáng chi phí có kiểm chứng**, không xóa index constraint quan trọng.
16. **Định kỳ đánh giá lại khi workload thay đổi**, vì index tối ưu năm nay chưa chắc phù hợp sau khi bảng lớn gấp 100 lần hoặc query đổi.

## 45. Tài liệu PostgreSQL chính thức

Để xác minh cú pháp, cơ chế và giới hạn theo **major version PostgreSQL thực tế**, tham khảo:

- [Indexes](https://www.postgresql.org/docs/current/indexes.html) — mục đích và chi phí chung của index.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — B-tree, Hash, GiST, SP-GiST, GIN, BRIN.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) — thứ tự và điều kiện trên index nhiều cột.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html) — expression index và chi phí khi ghi.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html) — predicate và điều kiện sử dụng.
- [Index-Only Scans](https://www.postgresql.org/docs/current/indexes-index-only-scans.html) — INCLUDE và visibility map.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — cú pháp, CONCURRENTLY, storage parameters.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, index cleanup, MVCC và vacuum.
- [HOT](https://www.postgresql.org/docs/current/storage-hot.html) — Heap-Only Tuple updates.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — kế hoạch và BUFFERS.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_user_tables, pg_stat_user_indexes.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-admin.html) — các hàm kích thước như pg_relation_size và pg_indexes_size.

`/current/` trỏ đến phiên bản hiện hành trên website. Khi triển khai lên phiên bản cụ thể, nên mở tài liệu đúng major version và kiểm tra những tính năng phụ thuộc phiên bản như một số phương án xây index hoặc tối ưu index scan.

## 46. Tổng kết

**Index giúp PostgreSQL không phải đọc tất cả dữ liệu khi chỉ cần một phần nhỏ, đồng thời có thể hỗ trợ JOIN, ORDER BY, LIMIT và bảo vệ tính duy nhất.** Nhưng index là **cấu trúc lưu trữ và ghi bổ sung**, không phải một tùy chọn tăng tốc hoàn toàn miễn phí.

Những điểm cốt lõi cần nhớ:

1. **Lợi ích đọc:** index hiệu quả khi nó giúp giảm lượng dữ liệu phải đọc hoặc cung cấp đúng thứ tự kết quả; nhưng `Seq Scan` có thể tốt hơn nếu phần lớn hàng cần xử lý.
2. **Chi phí INSERT:** mỗi index cần được bảo trì với các entry mới phù hợp và có thể làm tăng WAL, I/O, cache pressure.
3. **Chi phí UPDATE:** MVCC tạo tuple version mới; cập nhật cột được index có thể gây index maintenance và làm giảm cơ hội HOT.
4. **Chi phí DELETE:** phiên bản cũ và index entries được dọn theo cơ chế VACUUM, không biến mất tức thì.
5. **Thiết kế phải theo workload:** composite/partial/expression/covering/GIN/BRIN giải quyết những nhóm truy vấn khác nhau và trả mức chi phí ghi khác nhau.
6. **Đo thay vì đoán:** dùng EXPLAIN, BUFFERS, catalog size, pg_stat_user_indexes và n_tup_hot_upd, đồng thời xem latency ghi/replica lag khi có workload.
7. **Không xóa index ràng buộc chỉ vì ít SELECT dùng nó:** PRIMARY KEY/UNIQUE mang vai trò bảo vệ dữ liệu, không đơn thuần tối ưu đọc.

Một index tốt là index **giải quyết được vấn đề đọc hoặc tính đúng đắn có giá trị thật, với chi phí bảo trì ghi mà hệ thống chấp nhận được**. Quyết định tạo index chỉ hoàn chỉnh khi bạn trả lời được cả hai câu hỏi: *truy vấn nào được lợi* và *những lần ghi nào sẽ phải trả giá*.

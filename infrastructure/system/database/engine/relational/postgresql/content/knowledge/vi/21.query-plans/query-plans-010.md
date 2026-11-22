# Chênh lệch ước tính với thực tế và cách tìm nút gây tốn kém trong kế hoạch truy vấn PostgreSQL

## 1. Một truy vấn “chậm” không nhất thiết do một câu lệnh SQL dài

Giả sử API tìm các đơn hàng của một nhóm khách hàng chạy trong 100 ms ở môi trường thử nghiệm, nhưng mất 15 giây khi vào production. Câu SQL không thay đổi. Một nguyên nhân có thể là PostgreSQL **ước tính sai số hàng trung gian**, từ đó chọn kiểu join, thứ tự join, index scan hoặc cách sắp xếp không còn phù hợp với dữ liệu thật.

Ví dụ, planner nghĩ một bộ lọc chỉ trả **10 đơn hàng**, nhưng trong thực tế lại trả **80.000 đơn hàng**. Nếu kế hoạch chọn **Nested Loop** và mỗi đơn hàng lại kích hoạt một index lookup khác, chênh lệch nhỏ ở một node phía dưới có thể nhân thành lượng công việc rất lớn.

Phân tích đúng không dừng ở việc thấy chữ “Seq Scan” rồi thêm index. Cần trả lời ba câu hỏi:

1. **Planner đã dự đoán gì?** — `cost`, `rows`, `width`, chọn node, thứ tự join.
2. **Khi thực thi đã xảy ra gì?** — `actual time`, `actual rows`, `loops`, số hàng bị lọc, memory, I/O, temp files, WAL.
3. **Chênh lệch nào thực sự làm tăng tổng chi phí?** — cardinality sai, lặp quá nhiều lần, I/O đĩa, sort tràn disk, hash nhiều batch, hoặc chọn lọc kém.

Bài này tập trung vào **đọc và chẩn đoán** bằng `EXPLAIN` và `EXPLAIN ANALYZE`, chứ không đưa ra mẹo “một tham số sửa mọi truy vấn”.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Đọc chính xác các trường `cost=a..b rows=n width=w`, `actual time=c..d rows=m loops=k`.
- Tính sai lệch ước tính hàng (*cardinality estimation error*) mà không bỏ quên `loops`.
- Phân biệt **ước lượng của planner** với **thời gian đo thực tế**, và phân biệt tổng thời gian truy vấn với thời gian bao gồm cây con.
- Tìm node cần điều tra bằng cách lần từ root xuống node gây khuếch đại công việc.
- Đọc `Rows Removed by Filter`, `Index Cond`, `Filter`, `Join Filter`, `Recheck Cond`.
- Dùng `BUFFERS`, `I/O Timings`, `Sort Method`, `Disk`, `Hash Batches` và các chỉ số parallel để khoanh vùng nguyên nhân.
- Xác định những vấn đề thường gặp: thống kê cũ, skew, tương quan giữa cột, predicates khó ước lượng, join fan-out, không đủ `work_mem`.
- Thử hướng sửa phù hợp: `ANALYZE`, thống kê mở rộng, index chọn lọc, sửa SQL, thiết kế dữ liệu hoặc chiến lược phân trang.
- Thực hiện thí nghiệm trong một bộ dữ liệu lab có thể tái tạo và giải thích kết quả của mình.

> **Nguyên tắc an toàn:** `EXPLAIN ANALYZE` thực thi câu SQL. Không dùng nó tùy tiện với `UPDATE`, `DELETE`, `INSERT`, DDL hoặc những hàm có side effect trên production. Chỉ đo trên tập dữ liệu được phép và có hạn mức tải phù hợp.

---

## 2. Một query plan là gì?

Một **execution plan** là cây các thao tác mà PostgreSQL dự định dùng để lấy, nối, lọc, nhóm và sắp dữ liệu.

Ví dụ cấu trúc (minh họa):

~~~text
Limit
└── Sort
    └── Hash Join
        ├── Seq Scan on orders
        └── Hash
            └── Seq Scan on customers
~~~

Đọc theo luồng dữ liệu:

1. Đọc bảng `customers`.
2. Tạo bảng hash cho một phía join.
3. Đọc `orders`.
4. Hash Join hai luồng dữ liệu.
5. Sort kết quả.
6. Limit số dòng trả về.

Trong kế hoạch in kiểu text, node cha nằm **bên trên** node con. Phần lớn dữ liệu được tạo từ những node lá rồi đi lên; nhưng cách thực thi có thể lazy, pipeline, lặp hoặc dừng sớm vì LIMIT, nên không coi cây là danh sách các bước lần lượt hoàn toàn theo thứ tự.

### 2.1. Node là thao tác, không phải câu lệnh SQL

Một câu SELECT duy nhất có thể sinh nhiều node: Seq Scan, Index Scan, Bitmap Index Scan, Bitmap Heap Scan, Sort, Hash, Hash Join, Nested Loop, Merge Join, Aggregate, Gather và nhiều node khác.

Mỗi node có các **ước tính riêng** và khi dùng ANALYZE có thể có **số đo thực tế riêng**.

### 2.2. Planner và executor có vai trò khác nhau

- **Planner/optimizer:** dùng thống kê, metadata, chỉ mục, điều kiện lọc và cost model để so các candidate plans.
- **Executor:** chạy kế hoạch đã được chọn, tương tác cache/disk/CPU, xử lý các hàng thực và ghi nhận số đo khi EXPLAIN ANALYZE bật instrumentation.

Planner không đo trước chính xác “câu này sẽ tốn 17,2 ms”. Nó **dự đoán tương đối bằng cost units**.

### 2.3. Những con số cụ thể thay đổi theo môi trường

Hai máy cùng dữ liệu có thể chọn plan khác vì:

- PostgreSQL version và extensions.
- Thống kê và thời điểm ANALYZE.
- Khác biệt index, partition, constraint.
- `work_mem`, `random_page_cost`, `effective_cache_size`, parallel settings.
- Cache nóng/lạnh, số connections đang chạy.
- Dữ liệu mới/đã update, bloat, visibility map.
- Giá trị bind parameters và cơ chế generic/custom plans.

Vì thế các execution-plan snippets trong bài là **minh họa định dạng**. Thực hành phải đọc plan thật trên database của bạn.

---

## 3. EXPLAIN và EXPLAIN ANALYZE: khác nhau ở mức thực thi

### 3.1. EXPLAIN chỉ xem ước tính

~~~sql
EXPLAIN
SELECT *
FROM plan_lab.orders
WHERE status = 'paid';
~~~

`EXPLAIN` thông thường cho biết planner dự kiến làm gì, **không chạy SELECT để đo thời gian xử lý thực tế**.

### 3.2. EXPLAIN (ANALYZE, BUFFERS) thực thi SELECT

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM plan_lab.orders
WHERE status = 'paid';
~~~

Thông thường sẽ có cả:

~~~text
Seq Scan on orders  (cost=0.00..3000.00 rows=102000 width=...)
                    (actual time=0.030..26.100 rows=102000 loops=1)
  Filter: (status = 'paid'::text)
  Rows Removed by Filter: 18000
  Buffers: shared hit=..., read=...
Planning Time: ... ms
Execution Time: ... ms
~~~

Đây là một **ví dụ minh họa về cách đọc output**, không phải kết quả cố định của lab. Các giá trị số thực, cách cast, width và buffer counts tùy database.

### 3.3. Cấu hình nên dùng khi chẩn đoán

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    VERBOSE,
    SETTINGS,
    SUMMARY,
    FORMAT TEXT
)
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE customer_id BETWEEN 1 AND 100;
~~~

Giải thích:

| Option | Vai trò |
|---|---|
| `ANALYZE` | Thực sự thực thi; bổ sung actual time/rows/loops |
| `BUFFERS` | Đếm các truy cập buffer/cache/disk/temp ở những node phù hợp |
| `VERBOSE` | Hiển thị thêm target lists, schema, chi tiết internal |
| `SETTINGS` | In những tham số planner liên quan khác giá trị mặc định |
| `SUMMARY` | Tổng thời gian planning/execution và thông tin tổng kết |
| `FORMAT TEXT` | Dễ đọc thủ công |
| `FORMAT JSON` | Tiện lưu/so sánh bằng công cụ; tránh parse text bằng regex mong manh |
| `TIMING OFF` | Giảm overhead đo thời gian từng node khi query quá nhỏ/nhiều loops |
| `WAL` | Cho thấy thống kê WAL của statement phù hợp khi dùng ANALYZE |

### 3.4. TIMING OFF vẫn đo gì?

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM plan_lab.orders;
~~~

`TIMING OFF` tắt đo **thời gian từng node**, giúp giảm overhead instrumentation trong một số tình huống, nhưng vẫn có `actual rows`, `loops` và **Execution Time** tổng. Vì không có actual time từng node, bạn không thể dùng output này để “quy trách nhiệm số ms” cho từng node; đổi lại phép đo tổng có thể ít overhead hơn.

### 3.5. Đừng dùng ANALYZE vô tư trên DML

~~~sql
-- Nguy hiểm trên dữ liệu thật nếu chạy không kiểm soát:
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM plan_lab.orders
WHERE status = 'canceled';
~~~

Lệnh trên **thực thi DELETE**. Trong lab riêng, có thể bao một DML kiểm thử bằng transaction rồi rollback, nhưng hãy nhớ sequence/identity allocation, các side effects bên ngoài database hoặc hàm gọi dịch vụ ngoài **không nhất thiết được rollback**.

Để quan sát mà **không thay đổi dữ liệu**, dùng `EXPLAIN` không ANALYZE. Để đo DML, thực hiện trên staging hoặc transaction kiểm soát trong lab, và kết thúc đúng mọi nhánh khi có lỗi.

---

## 4. Đọc đúng các trường cost, rows, width

Một node mẫu:

~~~text
Index Scan using ix_orders_customer on orders
    (cost=0.42..31.76 rows=12 width=48)
~~~

### 4.1. Startup cost và total cost

- `cost=0.42`: **startup cost** ước tính, lượng công việc phải làm trước khi node có thể trả row đầu tiên.
- `cost=31.76`: **total cost** ước tính để node chạy hết output theo mô hình planner.
- Cost là **đơn vị nội bộ tương đối**, **không phải mili giây**.
- Các cost của node cha đã phản ánh chi phí thành phần của các node con theo cách planner tính toán; **không cộng tất cả total cost các node** để tìm “tổng chi phí thực”.

Một node Sort thường có startup cost đáng kể vì có thể phải gom dữ liệu trước khi trả hàng đầu tiên. Một Index Scan có thể có startup cost thấp để trả sớm vài hàng.

### 4.2. rows là số hàng ước tính xuất khỏi node

`rows=12` nghĩa là planner dự kiến node tạo khoảng **12 row mỗi lần thực thi node**, theo cách giải thích ở `loops` khi đo actual. Không phải 12 row đọc từ storage, không phải 12 page và không phải 12 transaction.

Một Filter node có thể quét 100.000 hàng từ bảng nhưng chỉ **trả 12 hàng** lên node cha.

### 4.3. width là byte trung bình ước tính của output row

`width=48` là **độ rộng trung bình ước tính, theo byte**, của hàng mà node truyền lên. Planner dùng nó trong tính toán lượng dữ liệu, chi phí sort/hash và các operator khác.

Nếu `width` bị ước tính thấp trên cột text/jsonb rộng hoặc các biểu thức phức tạp, bộ nhớ sort/hash và kích thước tuplestore có thể lệch so với dự tính. Tuy vậy, `width` không phải số byte chính xác được ghi trên đĩa của từng tuple.

### 4.4. Không so cost tuyệt đối giữa hệ thống khác nhau

`cost=10000` trên máy/setting A không thể quy đổi trực tiếp thành “10 giây” hoặc so với hệ B nếu statistics/cost constants khác nhau. Điều hữu ích là **so sánh các plan ứng viên dưới cùng điều kiện** và đối chiếu với actual measurement.

---

## 5. Đọc actual time, actual rows và loops

Một node ví dụ:

~~~text
Index Scan using idx_order_items_order_id on order_items
  (cost=0.42..9.60 rows=2 width=32)
  (actual time=0.018..0.045 rows=3 loops=5000)
~~~

### 5.1. actual time=a..b là gì?

- `actual time=0.018`: thời gian trung bình đến hàng đầu tiên mỗi lần node chạy, khi đo per-node timing.
- `actual time=0.045`: thời gian trung bình đến khi node hoàn tất mỗi lần chạy.
- Đơn vị là **mili giây**.
- Khi `loops>1`, các số thời gian thông thường là **trung bình trên mỗi lần thực thi**, không phải tổng toàn bộ 5.000 lần.

### 5.2. actual rows cũng phải đọc cùng loops

`actual rows=3 loops=5000` nghĩa là node trung bình trả khoảng **3 hàng mỗi lần chạy** qua 5.000 lần. Lượng row phát ra tổng cộng xấp xỉ:

\[
3 \times 5000 = 15000 \text{ rows}
\]

`actual rows` có thể được làm tròn khi hiển thị text; nếu cần phân tích tự động, dùng output JSON và hiểu đặc điểm các số đo.

### 5.3. Đừng so “actual rows = 3” với “estimated rows = 2” rồi bỏ qua loops

Chỉ nhìn mỗi lượt, 3 so với 2 là lệch 1,5 lần, có vẻ nhỏ. Nhưng **5.000 lần lookup** có thể là nguồn chi phí chủ yếu.

Với node lặp lại:

~~~text
actual time=0.045 rows=3 loops=5000
~~~

ước tính thô thời gian node được gọi:

\[
0.045\text{ ms} \times 5000 \approx 225\text{ ms}
\]

**Thận trọng:** node timing thường tính **bao gồm công việc con** (inclusive), phép nhân chỉ là phương tiện ước lượng và không đồng nghĩa toàn bộ 225 ms là CPU độc quyền của node; các node cha/con chồng lấn thời gian và có overhead instrumentation.

### 5.4. total actual time không tính bằng cách cộng các node

Sai:

~~~text
Seq Scan 100 ms
Hash     90 ms
Hash Join 120 ms
Sort     50 ms
-----------------
Tổng thời gian = 360 ms  (không hợp lệ nếu cộng kiểu này)
~~~

Các số thời gian ở node cha **đã bao gồm nhiều thời gian ở node con** theo mô hình thực thi. Kế hoạch pipeline, parallel workers và instrumentation làm phép cộng càng không có nghĩa. **Execution Time ở cuối** mới là tổng thời gian executor đo cho cả statement tương ứng.

### 5.5. Một node không có actual rows không nhất thiết vô dụng

`actual rows=0` có thể do:

- Filter loại hết row.
- Limit dừng sớm ở nhánh khác.
- Join phía ngoài không tạo input cho inner.
- Nhánh không được thực thi (`never executed`).
- Partition pruning bỏ nhánh.
- Dữ liệu thật không có giá trị phù hợp.

Phải đọc cả **loops**, node cha và điều kiện; không tự xóa index hay rewrite SQL chỉ vì một nhánh có zero rows trong một lần thử.

---

## 6. Vì sao ước tính sai lệch mới là tín hiệu chẩn đoán quan trọng?

Planner cần dự đoán bao nhiêu hàng sẽ đi qua từng node để đánh giá:

- Chọn Nested Loop, Hash Join hay Merge Join.
- Chọn index scan hay sequential scan.
- Chọn join order.
- Phân bổ dự tính cho Sort, Aggregate, Hash.
- Có nên dùng parallel workers.
- Chiến lược LIMIT, DISTINCT và ORDER BY.

Một node ước tính **100 hàng** nhưng thực tế **1.000.000 hàng** có thể khiến kế hoạch vốn hợp lý cho 100 hàng trở nên rất đắt.

### 6.1. Tỷ số ước lượng/thực tế

Một phép đo thực dụng khi cả hai số dương:

\[
\text{misestimate factor}
=\max\left(
\frac{\text{actual rows}}{\text{estimated rows}},
\frac{\text{estimated rows}}{\text{actual rows}}
\right)
\]

Ví dụ:

| Estimated rows | Actual rows | Sai lệch | Diễn giải |
|---:|---:|---:|---|
| 100 | 120 | 1,2× | Gần nhau |
| 100 | 10.000 | 100× | Đánh giá thấp |
| 20.000 | 50 | 400× | Đánh giá cao |
| 5 | 5 | 1× | Đúng ở node này |
| 1 | 0 | Không dùng tỷ số hữu hạn | Thực tế không có output |

**Không có ngưỡng “10× nghĩa là lỗi” tuyệt đối.** Sai lệch lớn ở node không tốn bao nhiêu tài nguyên có thể ít quan trọng hơn sai lệch 2× tại node lặp một triệu lần.

### 6.2. Chú ý các trường hợp zero

Nếu actual rows bằng 0, phép chia actual/estimated có thể bằng 0 và phép nghịch đảo vô hạn. Không nên báo “∞ lần” như một kết luận tối ưu hóa. Trước tiên kiểm tra input không có dữ liệu, điều kiện quá chọn lọc hoặc LIMIT/pruning khiến node không chạy.

### 6.3. Actual rows bình quân theo loop

Một node có estimated rows=5 và actual rows=3 loops=1000 thường nên được hiểu là **5 dự đoán và 3 thực tế mỗi lần chạy**, không phải planner “dự đoán tổng 5” nhưng thực tế “3000”. Khi phân tích *tổng việc xử lý*, phải xét thêm số lần lặp được dự đoán/diễn ra thông qua node cha.

### 6.4. Một sai lệch nhỏ ở lá có thể trở thành lớn sau join

Ví dụ:

~~~text
Scan khách hàng:       estimated 100, actual 200
Scan đơn/khách:         estimated   2, actual  40
Nested Loop output:     estimated 200, actual 8000
~~~

Sai lệch tăng qua join fan-out. **Nút join có estimated vs actual chênh lớn** là dấu hiệu để lần xuống từng child, tìm chính xác cardinality đã bắt đầu lệch ở đâu.

---

## 7. Xây bộ dữ liệu lab có skew để luyện phân tích

Bài dùng schema `plan_lab`. Tạo riêng trên database thực hành; dữ liệu sinh có quy tắc **tái lập về logic**, nhưng XID, thời gian chạy, cache và kế hoạch phụ thuộc môi trường.

### 7.1. Tạo bảng customers

~~~sql
CREATE SCHEMA IF NOT EXISTS plan_lab;

CREATE TABLE plan_lab.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL,
    is_vip BOOLEAN NOT NULL
);

INSERT INTO plan_lab.customers
    (customer_id, customer_name, region, is_vip)
SELECT
    g,
    'Customer ' || g::text,
    CASE
        WHEN g <= 1200 THEN 'north'
        WHEN g <= 1800 THEN 'south'
        ELSE 'west'
    END,
    (g % 20 = 0)
FROM generate_series(1, 2000) AS g;
~~~

Có 2.000 customers; vùng north chiếm 1.200, south 600 và west 200.

### 7.2. Tạo bảng orders với dữ liệu lệch

~~~sql
CREATE TABLE plan_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES plan_lab.customers(customer_id),
    status TEXT NOT NULL,
    created_at DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO plan_lab.orders
    (order_id, customer_id, status, created_at, amount, payload)
SELECT
    g::bigint,
    CASE
        WHEN g % 10 < 8 THEN (g % 100) + 1
        ELSE (g % 2000) + 1
    END,
    CASE
        WHEN g % 100 < 85 THEN 'paid'
        WHEN g % 100 < 95 THEN 'pending'
        ELSE 'canceled'
    END,
    DATE '2026-01-01' + (g % 365),
    ((g % 9000) + 100)::numeric / 100,
    repeat('x', 80)
FROM generate_series(1, 120000) AS g;
~~~

Có 120.000 orders. Cách gán customer_id làm nhiều order thuộc một nhóm khách hàng nhỏ, tạo **skew**; status có phân bố không đều: paid chiếm phần lớn. `created_at` trải qua nhiều ngày.

Bộ dữ liệu này **không mô phỏng hoàn hảo production**, nhưng đủ để đặt câu hỏi về selectivity, số hàng và join order. Công thức modulo làm một số cột có tương quan; không giả định các thuộc tính độc lập với nhau.

### 7.3. Tạo order_items để quan sát fan-out

~~~sql
CREATE TABLE plan_lab.order_items (
    item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES plan_lab.orders(order_id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL
);

INSERT INTO plan_lab.order_items
    (item_id, order_id, sku, quantity, unit_price)
SELECT
    g::bigint,
    ((g - 1) / 2 + 1)::bigint,
    'SKU-' || (g % 500)::text,
    (g % 5) + 1,
    ((g % 5000) + 100)::numeric / 100
FROM generate_series(1, 240000) AS g;
~~~

Mỗi order có **hai items** theo công thức tạo dữ liệu (không có item thiếu). Điều này giúp biết trước join orders → items có fan-out lý thuyết 2× trong lab.

### 7.4. Cập nhật thống kê sau bulk load

~~~sql
ANALYZE plan_lab.customers;
ANALYZE plan_lab.orders;
ANALYZE plan_lab.order_items;
~~~

`ANALYZE` lấy mẫu/cập nhật thống kê planner, **không tạo index**. Autovacuum/autoanalyze có thể làm việc này về sau, nhưng trong lab nên chủ động chạy sau khi nạp nhiều dữ liệu để các phép đo có dữ liệu thống kê.

### 7.5. Đếm dữ liệu

~~~sql
SELECT 'customers' AS entity, COUNT(*) AS n
FROM plan_lab.customers
UNION ALL
SELECT 'orders', COUNT(*) FROM plan_lab.orders
UNION ALL
SELECT 'order_items', COUNT(*) FROM plan_lab.order_items;
~~~

Kết quả kỳ vọng nếu script nạp một lần vào bảng trống:

| entity | n |
|---|---:|
| customers | 2.000 |
| orders | 120.000 |
| order_items | 240.000 |

**Không chạy lại INSERT trên bảng đã nạp dữ liệu** nếu mong số lượng này; khóa chính sẽ báo trùng.

### 7.6. Một vài truy vấn khám phá phân bố

~~~sql
SELECT status, COUNT(*) AS n
FROM plan_lab.orders
GROUP BY status
ORDER BY n DESC;
~~~

~~~sql
SELECT customer_id, COUNT(*) AS n_orders
FROM plan_lab.orders
GROUP BY customer_id
ORDER BY n_orders DESC, customer_id
LIMIT 20;
~~~

~~~sql
SELECT c.region, o.status, COUNT(*) AS n
FROM plan_lab.orders AS o
JOIN plan_lab.customers AS c USING (customer_id)
GROUP BY c.region, o.status
ORDER BY c.region, n DESC;
~~~

Những số này giúp nhận biết **skew và sự phụ thuộc giữa các thuộc tính** trước khi phân tích plan. Một dự đoán planner tốt cần thống kê phù hợp với phân bố dữ liệu, không chỉ tổng COUNT(*).

---

## 8. Học cách đọc một kế hoạch theo thứ tự

Một quy trình đọc hiệu quả không phải từ trái sang phải toàn bộ text. Hãy làm theo các tầng:

1. **Root node và tổng thời gian:** số hàng cuối, Planning Time, Execution Time.
2. **Nhánh tạo phần lớn dữ liệu:** scan/join/group/sort nào làm nhiều rows?
3. **Đo chênh lệch rows:** node nào bắt đầu lệch so với dự đoán?
4. **Xét loops:** node nhỏ có bị lặp hàng trăm nghìn lần không?
5. **Xét các tài nguyên:** buffers read/hit, temp, I/O timing, sort memory, hash batches.
6. **Tìm nguyên nhân SQL/stats:** predicate, join order, tương quan cột, index, dữ liệu.
7. **Thử một thay đổi có giả thuyết** rồi so plan và actual sau thay đổi.

### 8.1. Đừng chỉ nhìn node cuối có thời gian lớn nhất

Node cha ở gần root thường có `actual time` lớn vì nó **bao gồm việc chạy các node con**. Ví dụ:

~~~text
Aggregate actual time=500 ms
  -> Hash Join actual time=490 ms
      -> Seq Scan on orders actual time=100 ms
      -> Hash ... actual time=390 ms
~~~

Thấy Aggregate 500 ms **không chứng minh phép tính SUM/COUNT bản thân mất 500 ms**. Cần đi xuống để tìm phần tạo input và tiêu thụ tài nguyên.

### 8.2. Đừng chỉ nhìn Seq Scan như “tội phạm”

Nếu query cần 90% bảng, Seq Scan thường hợp lý. Một `Index Scan` với hàng trăm nghìn random heap fetch có thể chậm hơn.

**Câu hỏi đúng:** node đang làm nhiều việc **cần thiết hay không cần thiết** để phục vụ predicate và output?

### 8.3. Node thực sự tốn kém có thể nhỏ nhưng lặp

Ví dụ Index Scan lấy một order_items row nhanh 0,02 ms, nhưng được gọi 100.000 lần. Tổng chi phí sẽ lớn hơn node Sort 20 ms, dù Sort nhìn bề ngoài có thời gian mỗi lần cao hơn.

### 8.4. Tìm "điểm bắt đầu lệch"

Nếu root rows gấp 100 lần dự đoán, kiểm tra input ngay bên dưới. Nếu scan của bảng orders ước tính đúng nhưng join output sai, nghi ngờ **join selectivity** hoặc phân bố khóa join. Nếu ngay tại filter của scan đã lệch, tìm statistics/predicate tương ứng.

---

## 9. Chẩn đoán trường hợp đánh giá thấp số hàng

Một trường hợp điển hình:

~~~text
Nested Loop
  (cost=... rows=100 ...)
  (actual time=... rows=150000 loops=1)
  -> Index Scan on customers
       (cost=... rows=10 ...)
       (actual ... rows=200 loops=1)
  -> Index Scan on orders
       (cost=... rows=10 ...)
       (actual ... rows=750 loops=200)
~~~

Kế hoạch này **chỉ minh họa hình thức**, không phải kết quả từ lab.

Các điểm cần đọc:

1. **Customers:** estimated 10, actual 200 → 20×.
2. **Inner orders:** estimated 10, actual 750 mỗi loop → 75×.
3. **Loops:** inner được gọi 200 lần.
4. **Output Nested Loop:** 200 × 750 = 150.000 rows, trong khi planner dự đoán rất ít.

Một index lookup đơn lẻ có thể rẻ nhưng **200 lần × 750 rows** làm toàn query đắt. Giải pháp có thể cần thống kê tốt hơn, đổi join strategy hoặc thiết kế index/SQL, không đơn giản “thêm index cho inner” nếu index đã tồn tại.

### 9.1. Trong lab: lọc nhóm khách hàng có nhiều đơn

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, o.customer_id, o.amount
FROM plan_lab.orders AS o
WHERE o.customer_id BETWEEN 1 AND 100;
~~~

So `estimated rows` với `actual rows` tại scan/filter. Trên dữ liệu skew, các giá trị 1–100 có thể chứa tỷ lệ đơn hàng lớn hơn nếu planner dùng mô hình phân bố không phù hợp.

### 9.2. Đừng giả định ANAYLZE sẽ tự giải quyết mọi quan hệ

`ANALYZE` giúp cập nhật thống kê. Tuy nhiên các phép ước lượng với cột tương quan, biểu thức phức tạp hoặc mối quan hệ chéo **giữa nhiều bảng** vẫn có thể sai dù đã ANALYZE gần đây. Cần phân biệt thống kê **cũ** với thống kê **không đủ mô hình hóa**.

### 9.3. Lấy actual rows từ đâu?

Trong `EXPLAIN (ANALYZE)`, giá trị `rows` ở dòng `actual ... rows=...` của một scan/filter là số hàng **đã truyền lên node cha**, không phải số page đọc. Để hiểu bao nhiêu hàng bị loại, đọc thêm `Rows Removed by Filter` và điều kiện index.

---

## 10. Chẩn đoán trường hợp đánh giá cao số hàng

Một trường hợp khác:

~~~text
Hash Join
  (cost=... rows=300000 ...)
  (actual ... rows=400 loops=1)
~~~

Planner dự đoán 300.000 rows nhưng thực tế chỉ có 400. Sai lệch lớn **theo hướng overestimate** có thể khiến nó:

- Chọn Hash Join/Seq Scan thay vì Index Scan chọn lọc.
- Dự đoán cần sort/hash lớn.
- Chọn thứ tự join không tối ưu.
- Quyết định parallelism khác.

### 10.1. Không mặc định Hash Join là xấu

Hash Join rất tốt khi cần kết hợp nhiều rows và equality join thích hợp. Nó “xấu” chỉ khi so với phương án khác trên workload thực, chứ không phải vì tên node.

### 10.2. Tìm nguyên nhân ước lượng cao

- Predicate có thực sự rất hiếm nhưng thống kê không phản ánh?
- Giá trị filter nằm trong nhóm MCV hay ngoài MCV?
- Có dependency giữa hai cột?
- Join condition có thêm điều kiện rất chọn lọc?
- Các cột có NULL fraction khác dự tính?
- Query dùng correlated subquery, function/parameter khó ước lượng?
- Planner đang dùng generic plan với thông tin parameter hạn chế?

### 10.3. Đối chiếu actual input và output của join

Nếu hai phía join đều ước lượng đúng nhưng output sai nhiều, nguyên nhân có thể là **tính chọn lọc của điều kiện join**, phân bố khóa hoặc dependency, không phải số hàng cơ sở.

Nếu một phía scan đã ước lượng sai 100×, hãy xử lý nguồn sai lệch ở scan trước khi tinh chỉnh cost constants toàn database.

---

## 11. Tìm node tốn kém bằng BUFFERS: phân biệt đọc cache và đọc từ storage

### 11.1. BUFFERS cho biết điều gì?

Với `EXPLAIN (ANALYZE, BUFFERS)`, bạn có thể thấy:

~~~text
Buffers: shared hit=16000 read=4200 dirtied=12 written=5
Buffers: temp read=1000 written=1030
~~~

Các bộ đếm phổ biến:

| Trường | Ý nghĩa thực hành |
|---|---|
| `shared hit` | Page được tìm thấy trong PostgreSQL shared buffer cache |
| `shared read` | Page phải được đọc vào shared buffers; **không chắc chắn là physical disk I/O** vì OS page cache có thể phục vụ |
| `shared dirtied` | Page được đánh dấu dirty bởi hoạt động được tính |
| `shared written` | Page được ghi ra bởi backend trong quá trình được đo |
| `local hit/read/...` | Buffer cho các relation tạm của phiên liên quan |
| `temp read` / `temp written` | I/O tệp tạm từ các node như Sort/Hash khi cần tràn disk |

`BUFFERS` báo **số lần truy cập vào block**, không phải số hàng. Block size mặc định của nhiều cài đặt PostgreSQL là 8 KiB nhưng có thể cấu hình khác lúc build server. Không lấy một block count mà tự tuyên bố chính xác bao nhiêu byte đã đọc từ ổ cứng vật lý.

### 11.2. Buffers của node cha có tính chất cộng dồn

Trong nhiều kế hoạch, thống kê buffers ở node cha bao gồm truy cập buffer phát sinh bên trong các node con. Vì vậy:

~~~text
Hash Join     Buffers: shared hit=1200
  Seq Scan A  Buffers: shared hit=700
  Hash
    Seq Scan B Buffers: shared hit=500
~~~

**Không** cộng thành 2400. Con số ở node cha đã phản ánh công việc từ các node con theo cách instrumentation của executor.

Khi khoanh vùng nhánh nào chạm nhiều pages, **so sánh các node con** và hiểu tính bao gồm, không cộng toàn cây không kiểm soát.

### 11.3. Shared read cao: dấu hiệu nào?

`shared read` cao gợi ý data page phải được đưa vào PostgreSQL buffer cache. Nhưng để biết query **thực sự chờ I/O lâu hay không**, cần quan sát thêm `I/O Timings` (nếu bật), thời gian node, metrics storage và tình trạng cache.

Một scan đọc 100.000 block tuần tự trên SSD có thể nhanh hơn hàng nghìn lần random heap fetch tản mát.

### 11.4. Shared hit cao cũng có thể tốn CPU

Nếu node có `shared hit=1,000,000` do 100.000 lần index lookup, dù pages có sẵn trong cache, mỗi lookup vẫn tốn CPU và overhead truy cập buffer. “Toàn hit cache” không có nghĩa query sẽ nhanh.

### 11.5. Temp read/written là dấu hiệu cần chú ý

Temp I/O xuất hiện khi một số phép toán cần không gian lớn hơn bộ nhớ sẵn có, ví dụ:

- Sort tràn ra disk.
- Hash Join nhiều batch.
- HashAggregate hoặc tuplestore/materialization theo tình huống.
- Các thao tác khác cần tệp tạm.

Không tự kết luận cứ có temp I/O là phải tăng `work_mem` toàn server. Cần biết **node tạo temp**, lượng dữ liệu, sự lựa chọn chiến lược và số query concurrent.

---

## 12. I/O Timings và thời gian chạy thật

### 12.1. Theo dõi thời gian đọc/ghi I/O

Khi cấu hình `track_io_timing` được bật, `EXPLAIN (ANALYZE, BUFFERS)` có thể hiển thị:

~~~text
I/O Timings: shared read=76.552
I/O Timings: temp read=22.100 write=35.840
~~~

Đơn vị thông thường là **mili giây**.

Kiểm tra:

~~~sql
SHOW track_io_timing;
~~~

Bật đo I/O timings có overhead riêng và phụ thuộc quyền cấu hình. Không cần bật trên production tùy ý nếu chưa có quy trình vận hành; dùng metric khác khi không khả dụng.

### 12.2. Đọc thời gian I/O trong mối quan hệ với node

Nếu Execution Time 2.000 ms nhưng shared read I/O time 30 ms, không hợp lý khi kết luận **toàn bộ 2 giây là disk latency**. Có thể CPU, nhiều loops, sort/hash, expression evaluation hoặc chờ khác mới chiếm đa số.

Ngược lại, I/O timing lớn là gợi ý về nghẽn đọc/ghi; vẫn phải xem kế hoạch truy cập có đụng quá nhiều block không và lý do.

### 12.3. Timing có overhead

Việc EXPLAIN ANALYZE ghi nhận thời gian cho từng lần gọi node có thể gây overhead đáng kể khi số loops cực lớn và mỗi thao tác nhỏ. Để phân tích cardinality không bị ảnh hưởng quá nhiều, có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT ...
~~~

Nhưng nhớ `TIMING OFF` làm **mất per-node actual time**; không dùng kết quả đó để tính thời gian độc lập từng node.

### 12.4. Kết quả phép đo không ổn định tuyệt đối

Độ trễ phụ thuộc cache, CPU scheduling, concurrency, autovacuum, WAL flush, OS cache và trạng thái storage. Nên đo nhiều lần trên dữ liệu đại diện; không kết luận một thay đổi nhanh hơn chỉ vì một lần chạy 11 ms so với 12 ms.

---

## 13. Đọc Seq Scan, Index Scan và Bitmap Scan

### 13.1. Seq Scan

~~~text
Seq Scan on orders
  (cost=... rows=102000 ...)
  (actual time=... rows=102000 loops=1)
  Filter: (status = 'paid'::text)
  Rows Removed by Filter: 18000
~~~

Nếu `paid` chiếm 85% bảng, quét tuần tự có thể hợp lý. Nếu chỉ lấy 10 rows trong 120.000 mà vẫn đọc cả bảng, hãy kiểm tra predicate và index có phù hợp không.

### 13.2. Index Scan

~~~text
Index Scan using idx_orders_customer on orders
  Index Cond: (customer_id = 50)
  Filter: (status = 'paid')
~~~

- `Index Cond`: điều kiện được dùng để giới hạn đường truy cập qua index.
- `Filter`: điều kiện khác được đánh giá trên các row candidate, có thể sau khi lấy heap row.
- Nếu `Rows Removed by Filter` rất lớn, index có thể chỉ thu hẹp được một phần predicate, còn phần filter quan trọng chưa được phục vụ hiệu quả.

Đừng nhầm `Filter` với điều kiện có thể hoàn toàn push vào index. Tùy cột/index/opclass và expression, PostgreSQL không luôn có chiến lược indexable cho mọi predicate.

### 13.3. Bitmap Index Scan → Bitmap Heap Scan

~~~text
Bitmap Heap Scan on orders
  Recheck Cond: (customer_id BETWEEN 1 AND 100)
  Heap Blocks: exact=..., lossy=...
  -> Bitmap Index Scan on idx_orders_customer
       Index Cond: (customer_id BETWEEN 1 AND 100)
~~~

Bitmap Index Scan tạo thông tin về vị trí row/pages; Bitmap Heap Scan truy cập heap theo tập page và kiểm tra cần thiết.

`Heap Blocks: lossy` xuất hiện khi bitmap phải biểu diễn một số block ở mức xấp xỉ (ví dụ giới hạn bộ nhớ), làm tăng việc recheck các row trên page. `Recheck Cond` tự nó **không chứng minh** mọi index đều lossy.

### 13.4. Index Only Scan

~~~text
Index Only Scan using ... on orders
  Heap Fetches: 12000
~~~

Tên `Index Only Scan` không có nghĩa **chắc chắn zero heap access**. PostgreSQL có thể phải kiểm tra visibility map và fetch heap nếu pages chưa được đánh dấu all-visible phù hợp.

Nếu `Heap Fetches` cao, xem index coverage, visibility map, tác động UPDATE/VACUUM. Đừng chỉ thêm INCLUDE columns rồi mặc định sẽ không còn heap fetch.

### 13.5. Rows Removed by Filter

Dòng:

~~~text
Rows Removed by Filter: 9990
actual rows=10 loops=1
~~~

gợi ý node đã kiểm tra khoảng 10.000 candidates, loại 9.990 và trả 10.

Nếu `loops>1`, các counter “Rows Removed ...” thường được trình bày theo **trung bình mỗi lần node chạy**, tương tự actual rows. Không bỏ qua loops khi ước tính tổng row bị xử lý.

### 13.6. Scan nhiều rows không tự là lỗi

Nếu query cần aggregate doanh thu **toàn bộ 120.000 orders**, đọc một phần lớn bảng là việc cần làm; index theo status có thể không làm biến mất nhu cầu xử lý toàn bộ dữ liệu. Cần hỏi liệu query/filter có thể giảm đầu vào, dùng bảng tổng hợp, partition pruning hoặc cách tính khác đúng nghiệp vụ không.

---

## 14. Nested Loop: một node con nhỏ bị gọi quá nhiều lần

### 14.1. Cơ chế khái quát

~~~text
Outer row 1 ──> Inner scan ──> rows match
Outer row 2 ──> Inner scan ──> rows match
...
Outer row N ──> Inner scan ──> rows match
~~~

Nested Loop rất tốt khi **outer nhỏ** và inner lookup có index phù hợp. Vấn đề là planner dự đoán outer nhỏ nhưng thực tế outer lớn, khiến inner lookup chạy nhiều hơn dự kiến.

### 14.2. Lab với order_items

Để phục vụ lookup theo khóa join:

~~~sql
CREATE INDEX ix_plan_items_order_id
ON plan_lab.order_items (order_id);
~~~

Query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.customer_id,
    i.item_id,
    i.quantity
FROM plan_lab.orders AS o
JOIN plan_lab.order_items AS i
  ON i.order_id = o.order_id
WHERE o.customer_id BETWEEN 1 AND 100;
~~~

Với dữ liệu skew, input outer của orders có thể lớn. Planner **có thể chọn** Hash Join, Nested Loop hoặc kế hoạch khác tùy statistics/index/cost; bài tập là đọc kế hoạch thật chứ không mặc định nhận đúng một node join.

### 14.3. Cách xác định chi phí khuếch đại

Nếu có plan:

~~~text
Nested Loop actual rows=60000 loops=1
  -> Bitmap Heap Scan on orders actual rows=30000 loops=1
  -> Index Scan on order_items actual rows=2 loops=30000
~~~

Số lần inner scan bằng khoảng 30.000 outer rows. Cho dù một lookup chỉ tốn trung bình 0,02 ms:

\[
30000 \times 0.02\text{ ms} \approx 600\text{ ms}
\]

Đây chỉ là **ước lượng thực dụng**, không phải tổng exclusive node time chính xác. So kết quả với Execution Time của toàn query.

### 14.4. Nguyên nhân cần kiểm tra

- Outer rows **thực** lớn hơn dự đoán?
- Inner rows mỗi outer lớn hơn dự đoán?
- Index lookup có nhiều heap fetch/random page read?
- Có filter inner chưa được đẩy vào index?
- Join condition có đúng dữ liệu hay vô tình fan-out?
- Có `Memoize` cache lookup lặp trong PostgreSQL phiên bản hỗ trợ không?
- Các row có cùng join key xuất hiện rất nhiều (skew)?

### 14.5. Không tắt Nested Loop toàn server như “cách sửa”

`SET enable_nestloop = off` là công cụ thử giả thuyết trong session lab, không phải thuốc chữa chung. Các truy vấn point lookup nhỏ có thể chậm hơn nhiều nếu ép Hash Join. Nguyên nhân gốc thường là **đánh giá cardinality, cấu trúc index hoặc logic join**.

---

## 15. Hash Join: đọc hash build, số batch và memory

### 15.1. Cơ chế

Hash Join trên equality thường:

1. Đọc một phía join làm **build side**.
2. Tạo hash table theo join key.
3. Đọc phía còn lại làm **probe side** và tìm matches.

Plan khái quát:

~~~text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  -> Seq Scan on orders o
  -> Hash
       Buckets: 4096  Batches: 1  Memory Usage: 210kB
       -> Seq Scan on customers c
~~~

### 15.2. Batches lớn hơn 1 có thể báo tràn bộ nhớ

Khi hash table không vừa ngân sách memory áp dụng, PostgreSQL có thể chia thành nhiều batch, ghi/đọc tệp tạm.

Ví dụ:

~~~text
Hash
  Buckets: 65536  Batches: 16  Memory Usage: 8192kB
Buffers: temp written=...
~~~

Cần xem:

- Batches thực tế.
- Temp I/O ở Hash/Hash Join.
- Số rows và width của build side.
- Có đánh giá thấp cardinality hoặc width không?
- Có filter/join order giúp giảm build side không?
- `work_mem`/`hash_mem_multiplier` và concurrency có phù hợp không?

### 15.3. Không tăng work_mem toàn hệ thống ngay

`work_mem` áp dụng **theo thao tác nội bộ** như sort/hash trong từng query, không phải “giới hạn tổng bộ nhớ mỗi connection”. Một query có nhiều sort/hash, nhiều query chạy song song có thể dùng lượng memory lớn.

Điều chỉnh ở **session/job** có giới hạn, đo trước/sau và xét tổng concurrency. Tăng quá mức có thể đổi temp I/O thành áp lực RAM, swap hoặc OOM.

### 15.4. Sai cardinality ảnh hưởng Hash Join

Nếu planner nghĩ build side có 100.000 rows nhưng thực tế 2.000.000, lựa chọn memory và costs có thể lệch. Hash Join không phải “kế hoạch sai” vì nó dùng hash; cần tìm nguyên nhân cardinality, data skew và I/O thực.

### 15.5. Hash Join và điều kiện join khác equality

Hash Join thường sử dụng equality condition làm hash key. Nếu query có thêm điều kiện bất đẳng thức/tính toán, plan có thể chứa:

~~~text
Hash Cond: (...)
Join Filter: (...)
Rows Removed by Join Filter: ...
~~~

`Join Filter` loại các cặp row đã được xét trong join. Nếu số cặp bị loại khổng lồ, kiểm tra điều kiện join và cơ hội đưa predicate vào scan/giảm input trước khi join, nhưng phải giữ đúng semantics của outer joins.

---

## 16. Merge Join: cần dữ liệu có thứ tự

Merge Join khai thác hai luồng dữ liệu được sắp theo join key phù hợp. Chúng có thể đến từ index scans đã theo thứ tự hoặc các Sort nodes riêng.

~~~text
Merge Join
  Merge Cond: (o.customer_id = c.customer_id)
  -> Sort
       Sort Key: o.customer_id
       -> Seq Scan on orders o
  -> Sort
       Sort Key: c.customer_id
       -> Seq Scan on customers c
~~~

### 16.1. Khi nào Merge Join phù hợp?

- Hai phía lớn.
- Có thể cung cấp/sắp thứ tự join key với chi phí hợp lý.
- Điều kiện join phù hợp.
- Truy vấn tiếp theo cũng cần thứ tự tương ứng.

### 16.2. Điểm gây tốn kém có thể nằm ở Sort con

Merge Join ở root có actual time cao nhưng **hai Sort bên dưới mới là nơi tốn I/O**, nhất là khi có `external merge Disk: ...`.

### 16.3. Không tự tạo index chỉ vì thấy Sort

Một index trả thứ tự có thể loại Sort, nhưng dùng index scan đọc nhiều heap pages cũng có chi phí. Thử plan tự nhiên với/không index trên dữ liệu đại diện.

### 16.4. Điều kiện join khiến fan-out

Khi có duplicate join keys, merge join vẫn có thể tạo nhiều kết quả. Sai cardinality có thể xuất hiện vì số lần trùng khóa hoặc phân bố lệch, không phải do cách sort.

---

## 17. Sort: tìm dấu hiệu tràn đĩa

### 17.1. Memory sort

Một plan có thể có:

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: quicksort  Memory: 4200kB
~~~

`quicksort` và `Memory` cho biết sort hiện tại đã xử lý trong memory theo thuật toán/biểu diễn tương ứng.

### 17.2. External merge: sort tràn disk

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: 64000kB
  Buffers: temp read=... written=...
~~~

Dấu hiệu:

- Dữ liệu phải sắp xếp lớn.
- Không đủ memory cho chiến lược sort trong điều kiện hiện tại.
- Có temp read/write.
- Query có thể bị chi phối bởi I/O tệp tạm.

### 17.3. Lab sort 120.000 rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, amount, payload
FROM plan_lab.orders
ORDER BY amount DESC, order_id;
~~~

Thực tế có tràn disk hay không phụ thuộc `work_mem`, width, statistics, cache và planner. Không giả định chỉ vì 120.000 rows là chắc chắn spill.

### 17.4. Top-N heapsort với LIMIT

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM plan_lab.orders
ORDER BY amount DESC, order_id
LIMIT 10;
~~~

Nếu planner chọn top-N heapsort, sort chỉ cần giữ số lượng candidate tương ứng, giảm memory hơn full sort. **Nhưng nguồn bên dưới vẫn có thể phải đọc mọi row** để biết top 10 nếu không có index phù hợp.

### 17.5. Index hỗ trợ ORDER BY

~~~sql
CREATE INDEX ix_plan_orders_amount_desc
ON plan_lab.orders (amount DESC, order_id);
~~~

Index này có thể giúp `ORDER BY amount DESC, order_id LIMIT 10` trả sớm. Tuy nhiên:

- Query trả hàng rộng cần heap fetch.
- Index có chi phí build/maintenance.
- Nếu lọc mạnh theo status/customer trước, một index theo amount đơn thuần chưa chắc tối ưu.
- Nếu trả hầu hết row, Seq Scan + Sort vẫn có thể tốt hơn.

### 17.6. Incremental Sort

PostgreSQL có **Incremental Sort** trong các trường hợp input đã được sắp một phần theo prefix của sort key:

~~~text
Incremental Sort
  Sort Key: customer_id, created_at
  Presorted Key: customer_id
~~~

Nó có thể giảm lượng dữ liệu cần sort lại so với full sort, nhưng hiệu quả phụ thuộc số nhóm/prefix và cardinality. Nếu số hàng mỗi group bị ước tính sai, kế hoạch thực tế cũng có thể lệch.

---

## 18. GROUP BY, DISTINCT và Aggregate: một hàng output không có nghĩa ít việc

### 18.1. COUNT(*) đầu ra chỉ một hàng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab.orders;
~~~

Có thể thấy:

~~~text
Aggregate actual rows=1 loops=1
  -> Seq Scan on orders actual rows=120000 loops=1
~~~

Aggregate trả **một hàng**, nhưng node con vẫn phải xử lý rất nhiều rows. Nếu chỉ nhìn actual rows của root=1 rồi kết luận query không tốn kém thì sai.

### 18.2. HashAggregate

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(amount)
FROM plan_lab.orders
GROUP BY customer_id;
~~~

HashAggregate có thể dùng bộ nhớ cho các group keys. Nếu số distinct groups thực cao hơn ước tính hoặc rows rộng, nó có thể cần thêm memory, chia batch hoặc ghi tệp tạm.

Tùy version, plan có thể ghi:

~~~text
HashAggregate
  Group Key: customer_id
  Batches: 8
  Memory Usage: ...
  Disk Usage: ...
~~~

### 18.3. GroupAggregate cần thứ tự

Một lựa chọn khác:

~~~text
GroupAggregate
  Group Key: customer_id
  -> Sort ...
~~~

Phải nhìn cả Sort con, không chỉ node GroupAggregate.

### 18.4. DISTINCT có thể tạo sort/hash lớn

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT sku
FROM plan_lab.order_items;
~~~

Nếu chỉ có 500 SKU nhưng hàng đầu vào 240.000, việc đọc/nhóm dữ liệu vẫn có thể tốn kém dù output ít. Nếu thống kê `n_distinct` sai, planner có thể chọn aggregation strategy hoặc ước tính memory chưa hợp lý.

### 18.5. Pushdown aggregation và pre-aggregation

Với query tổng doanh thu theo khách hàng, đôi khi nên aggregate orders trước join với một bảng dimension rộng để giảm số rows đi qua join:

~~~sql
WITH totals AS (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM plan_lab.orders
    GROUP BY customer_id
)
SELECT c.customer_id, c.customer_name, t.total_amount
FROM totals AS t
JOIN plan_lab.customers AS c
  ON c.customer_id = t.customer_id;
~~~

Nhưng không tự áp dụng pre-aggregation cho mọi join vì có thể đổi semantics khi join có fan-out, outer join, filter phụ thuộc từng row hoặc phép tính không phân phối được.

---

## 19. LIMIT: kế hoạch có thể dừng sớm

### 19.1. Một plan được chọn vì startup cost thấp

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM plan_lab.orders
WHERE status = 'paid'
LIMIT 10;
~~~

Nếu rows thỏa filter xuất hiện sớm, Seq Scan có thể dừng rất nhanh khi đủ 10 rows, dù tổng bảng lớn. Planner có thể ưu tiên startup cost thay vì total cost thấp nhất khi query có LIMIT.

### 19.2. LIMIT không làm mọi node xử lý ít rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM plan_lab.orders
ORDER BY amount DESC
LIMIT 10;
~~~

Nếu không có index trả đúng thứ tự, node bên dưới Sort có thể phải đọc toàn bộ rows trước khi xác định top 10.

### 19.3. OFFSET lớn

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM plan_lab.orders
ORDER BY order_id
LIMIT 20 OFFSET 100000;
~~~

Dù chỉ trả 20 rows, database có thể phải duyệt ít nhất 100.020 positions theo thứ tự để bỏ 100.000 rows trước. Trong phân trang production, cân nhắc **keyset pagination** khi ứng dụng có khóa sắp ổn định.

### 19.4. Early termination ảnh hưởng số liệu node

Khi LIMIT dừng sớm, `actual rows` của các node con có thể chỉ phản ánh công việc **đã được yêu cầu đến thời điểm dừng**, không phải toàn bộ rows mà node có thể tạo nếu chạy tới hết. Một sai lệch rows do dừng sớm không nhất thiết là lỗi cardinality của planner.

---

## 20. Parallel plans: không nhân hay cộng rows vô thức

### 20.1. Gather và Gather Merge

Một query đủ lớn có thể dùng parallel workers:

~~~text
Gather
  Workers Planned: 2
  Workers Launched: 2
  -> Parallel Seq Scan on orders
       (actual ... rows=40000 loops=3)
~~~

Với ví dụ minh họa, node Parallel Seq Scan có thể được chạy bởi leader và hai workers; `actual rows=40000 loops=3` gợi ý tổng khoảng 120.000 rows trên ba participants.

**Không** diễn giải `actual rows=40000` là cả query chỉ đọc 40.000 rows. Đồng thời **không** nhân theo `Workers Planned` một cách mù quáng vì số workers thực tế có thể khác và leader có thể tham gia ít/nhiều.

### 20.2. Planned khác Launched

- `Workers Planned`: số workers planner dự kiến.
- `Workers Launched`: số workers thực sự được cấp khi thực thi.

Nếu `Workers Launched` thấp, có thể do hạn chế tài nguyên/parallel worker availability; thời gian thực tế khác dự tính.

### 20.3. Worker instrumentation

Khi bật `VERBOSE` hoặc ở những node hỗ trợ, plan có thể có thống kê theo từng worker: actual rows, sort memory, buffers, JIT hoặc hoạt động khác. Đó là dữ liệu quan trọng khi nghi ngờ **data skew giữa workers**.

### 20.4. Parallel Hash

Một kế hoạch Parallel Hash Join có quy tắc memory/batching và chia công việc phức tạp hơn Hash Join đơn luồng. Nếu thấy Batches lớn hoặc temp I/O, vẫn phải xét **phân phối thực tế** chứ không chỉ nhìn row estimate tổng.

### 20.5. Tổng execution time không bằng tổng worker elapsed

Workers thực hiện một phần công việc **đồng thời**. Cộng thời gian mỗi worker dễ cho kết quả lớn hơn wall-clock execution time; cần phân biệt tổng CPU effort với độ trễ quan sát của một request.

---

## 21. JIT, planning time và execution time

### 21.1. JIT compilation

Với PostgreSQL có JIT và plan được chọn kích hoạt, output EXPLAIN ANALYZE có thể có mục:

~~~text
JIT:
  Functions: ...
  Options: Inlining ..., Optimization ..., Expressions ..., Deforming ...
  Timing: Generation ..., Inlining ..., Optimization ..., Emission ..., Total ...
~~~

JIT có thể giúp query CPU-bound xử lý lượng lớn dữ liệu, nhưng overhead compile đôi khi đáng kể so với query nhỏ. Cần đọc thời gian JIT trong context và đo nhiều lần, không mặc định bật/tắt cho mọi workload.

### 21.2. Planning Time

`Planning Time` đo khoảng thời gian tạo kế hoạch cho statement theo instrumentation của EXPLAIN. Query nhiều bảng/partition hoặc expression phức tạp có thể tốn planning đáng kể dù executor chạy nhanh.

### 21.3. Execution Time

`Execution Time` là thời gian executor đo để thực thi statement trong EXPLAIN ANALYZE, có các quy tắc liên quan đến trigger, instrumentation và overhead; **không đồng nghĩa toàn bộ thời gian từ client gửi request đến nhận hết dữ liệu**.

Ví dụ, EXPLAIN ANALYZE không truyền toàn bộ result rows như một SELECT bình thường; nó đo chạy query plan và trả bản plan. Network serialization/transfer và thời gian xử lý client trong request thực có thể khác.

### 21.4. Một truy vấn với nhiều executions

Một API gọi cùng prepared statement 10.000 lần có thể tốn tổng tài nguyên lớn dù mỗi invocation chỉ 0,5 ms. EXPLAIN của một invocation không thay thế việc xem **tần suất chạy** từ công cụ thống kê query.

---

## 22. Rows Removed by Filter, Join Filter và Index Recheck

Các chỉ số này giúp biết “bao nhiêu công việc bị làm rồi bỏ”.

| Chỉ số | Gợi ý chẩn đoán |
|---|---|
| `Rows Removed by Filter` | Candidate rows đã bị filter ở node |
| `Rows Removed by Join Filter` | Các cặp row đã xét khi join nhưng không qua điều kiện |
| `Rows Removed by Index Recheck` | Candidate bị loại khi executor kiểm tra lại điều kiện index |
| `Heap Blocks: lossy` | Bitmap heap scan phải đại diện một số pages ở mức xấp xỉ |
| `Heap Fetches` | Index Only Scan vẫn phải truy cập heap để xác nhận visibility |
| `Rows Removed by Conflict Filter` | Có thể xuất hiện ở một số execution contexts khác; phải đọc node tương ứng |

### 22.1. Filter sau scan có thể là nút cổ chai

~~~text
Index Scan using idx_orders_customer ...
  Index Cond: (customer_id = 50)
  Filter: (status = 'canceled')
  Rows Removed by Filter: 10000
  actual rows=1
~~~

Nếu workload thường lọc cả customer_id và status, một index composite hoặc partial có thể hữu ích:

~~~sql
CREATE INDEX ix_orders_customer_status
ON plan_lab.orders (customer_id, status);
~~~

Nhưng kết quả phụ thuộc selectivity, tính tương quan và lượng ghi. Không tạo ngay trên production chỉ từ một plan minh họa.

### 22.2. Recheck nhiều có thể do bitmap lossy

Nếu plan báo nhiều `Rows Removed by Index Recheck`, xem `Heap Blocks: exact/lossy`, index operator class và `work_mem`. Nguyên nhân có thể là bitmap memory không đủ, không chỉ do “index sai”.

### 22.3. Join Filter và outer join semantics

Di chuyển một predicate từ `WHERE` sang `ON` hoặc ngược lại có thể **đổi kết quả LEFT JOIN** vì NULL-extended rows. Đừng “push filter” thủ công chỉ để ép plan nhanh mà không kiểm tra logic.

Ví dụ:

~~~sql
-- Chỉ giữ khách có đơn paid: WHERE biến phần unmatched của
-- LEFT JOIN thành không được trả về theo điều kiện này.
SELECT c.customer_id, o.order_id
FROM plan_lab.customers AS c
LEFT JOIN plan_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'paid';
~~~

~~~sql
-- Vẫn giữ khách không có đơn paid, với o.* = NULL:
SELECT c.customer_id, o.order_id
FROM plan_lab.customers AS c
LEFT JOIN plan_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid';
~~~

Hai SQL khác nhau về nghiệp vụ, không được dùng thay nhau chỉ vì plan thứ hai ít rows hơn.

---

## 23. Vì sao ước tính sai? Thống kê của planner

### 23.1. Planner không đọc toàn bộ bảng trước mỗi câu SQL

PostgreSQL không chạy COUNT(*) và duyệt mọi giá trị trước mỗi SELECT. Nó sử dụng thống kê, metadata và các giả định của cost model:

- `pg_class.reltuples`: **ước lượng** số rows của relation.
- `pg_class.relpages`: số pages liên quan.
- `pg_statistic`: thống kê cấp cột ở catalog nội bộ.
- `pg_stats`: view dễ đọc hơn cho thống kê cột khi có quyền.
- `pg_statistic_ext`, `pg_statistic_ext_data` và `pg_stats_ext`: thống kê mở rộng đa cột/biểu thức theo khả năng phiên bản.
- Thông tin về index, constraints, uniqueness, partitions, expressions và planner settings.

Những số liệu này có thể **không còn phản ánh đúng dữ liệu mới** hoặc không đủ để mô hình hóa sự tương quan.

### 23.2. Xem pg_stats

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'plan_lab'
  AND tablename = 'orders'
  AND attname IN ('customer_id', 'status', 'created_at', 'amount')
ORDER BY attname;
~~~

| Trường | Diễn giải |
|---|---|
| `null_frac` | Ước lượng tỷ lệ NULL |
| `n_distinct` | Ước lượng số distinct; giá trị âm có semantics tỷ lệ so với số rows |
| `most_common_vals` | Những giá trị xuất hiện nhiều trong mẫu |
| `most_common_freqs` | Tỷ lệ tương ứng với MCV |
| `histogram_bounds` | Các mốc phân phối để ước lượng predicate khoảng |
| `correlation` | Tương quan thứ tự giá trị với vị trí vật lý, có thể ảnh hưởng cost index scan |

`correlation` ở đây **không phải tương quan giữa hai cột**. Nó liên quan đến thứ tự giá trị trong một cột và thứ tự lưu trữ vật lý, giúp planner dự đoán chi phí heap access.

### 23.3. n_distinct có thể âm

Trong `pg_stats`, `n_distinct` âm biểu diễn số distinct dự kiến tăng theo quy mô bảng, bằng một tỷ lệ âm của số rows. Ví dụ `-1` thường gợi ý gần như mọi hàng mang giá trị distinct riêng. Không hiểu nó là "số lượng distinct bằng -1".

### 23.4. MCV rất quan trọng với skew

Nếu `status='paid'` xuất hiện 85% rows, giả định ba trạng thái có xác suất như nhau là không đủ. `most_common_vals` và `most_common_freqs` giúp ước lượng các giá trị phổ biến.

Một số customer có nhiều đơn hơn khách khác. MCV cho customer_id có thể phân biệt popular customer với rare customer, nhưng độ lớn mẫu, số distinct và generic plans cũng ảnh hưởng độ chính xác.

### 23.5. Histogram không giải quyết mọi predicate

Histogram cấp cột có thể hỗ trợ `created_at BETWEEN ...`. Nó không tự biết customer group, status và amount có phụ thuộc lẫn nhau thế nào. Nhiều predicate đòi mô hình selectivity kết hợp.

---

## 24. Thống kê cũ: nhận diện và sửa bằng ANALYZE

### 24.1. Khi nào thống kê trở nên không đại diện?

- Bulk load nhiều rows sau lần ANALYZE gần nhất.
- Xóa phần lớn rows của một nhóm hoặc partition.
- Backfill thay đổi mạnh phân bố status/region.
- Một chương trình khuyến mại khiến vài khách hàng chiếm phần lớn orders.
- Dữ liệu mới nằm ngoài histogram cũ.
- Partition mới được attach/load nhưng stats của tầng truy vấn chưa phản ánh đầy đủ.

### 24.2. Xem ngày ANALYZE và lượng thay đổi

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname = 'plan_lab'
ORDER BY relname;
~~~

Đây là **ước lượng/counters thống kê**, không phải COUNT(*) chính xác. `n_mod_since_analyze` là chỉ báo về số rows thay đổi kể từ lần ANALYZE.

### 24.3. Cập nhật stats

~~~sql
ANALYZE plan_lab.orders;
ANALYZE plan_lab.customers;
ANALYZE plan_lab.order_items;
~~~

Sau ANALYZE, so kế hoạch và quan sát:

- Estimated rows có gần actual hơn không?
- Join order, scan strategy có đổi không?
- Sort/Hash có giảm temp I/O không?
- Execution Time có cải thiện ổn định qua nhiều lần đo không?

`ANALYZE` **không sửa SQL sai, không tạo index, không bảo đảm plan tốt nhất**, và thống kê lấy mẫu vẫn có sai số.

### 24.4. ANALYZE không phải VACUUM FULL

ANALYZE thu thập thống kê và có chi phí CPU/I/O/lock phù hợp. Nó không rewrite toàn bộ bảng để trả dung lượng về OS. Không chạy quá thường xuyên trên bảng lớn nếu không có nhu cầu dữ liệu/monitoring rõ.

### 24.5. Khi dữ liệu thay đổi rất nhanh

Nếu stats liên tục cũ trước lịch autoanalyze, đánh giá thresholds autovacuum/autoanalyze theo bảng và workload; không tự tăng statistics target mọi cột vì nguyên nhân có thể là tần suất cập nhật hoặc phân bố mới.

---

## 25. Statistics target và chất lượng mẫu

### 25.1. Mặc định có độ chi tiết hữu hạn

`default_statistics_target` ảnh hưởng số mục phổ biến/histogram và lượng mẫu được dùng cho một số thống kê.

~~~sql
SHOW default_statistics_target;
~~~

### 25.2. Tăng target cho cột quan trọng

~~~sql
ALTER TABLE plan_lab.orders
    ALTER COLUMN customer_id SET STATISTICS 500;

ANALYZE plan_lab.orders;
~~~

Tăng target có thể giúp đại diện tốt hơn một phân bố phức tạp nhưng có chi phí thu thập/lưu trữ statistics; không đảm bảo estimate hoàn hảo.

### 25.3. Khi nào nên thử?

- Cột có nhiều distinct values và một số giá trị rất phổ biến.
- Query phụ thuộc độ chọn lọc của cột này.
- MCV/histogram hiện không đủ để phản ánh phân bố.
- Sai lệch bắt đầu ngay tại scan/filter của cột.
- Có before/after plan để đánh giá thay đổi.

Không tăng target lên cực cao trên mọi cột chỉ để có histogram dài hơn.

### 25.4. Xem lại thống kê

~~~sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'plan_lab'
  AND tablename = 'orders'
  AND attname = 'customer_id';
~~~

Khi test lại, dùng cùng SQL, tham số và dataset. Plan có thể hoặc không thay đổi; điều đó phải được đọc như một quan sát, không phải bài tập buộc plan thay đổi.

---

## 26. Extended statistics: tương quan giữa các cột

### 26.1. Vấn đề giả định độc lập

Giả sử:

~~~sql
WHERE status = 'paid'
  AND customer_id BETWEEN 1 AND 100
~~~

Nếu các thuộc tính tương quan, nhân riêng xác suất từng predicate có thể sai.

Ví dụ lý thuyết:

~~~text
P(status='paid') = 0.8
P(customer thuộc hot group) = 0.5

Giả định độc lập: P(cả hai) ≈ 0.8 × 0.5 = 0.4
Dữ liệu thực:    P(cả hai) = 0.65
~~~

Planner có thể ước tính thiếu 0,65/0,4 ≈ 1,625× tại scan. Khi đi qua join, sai lệch có thể khuếch đại.

### 26.2. CREATE STATISTICS

~~~sql
CREATE STATISTICS st_plan_orders_status_customer
    (dependencies, ndistinct, mcv)
ON status, customer_id
FROM plan_lab.orders;

ANALYZE plan_lab.orders;
~~~

| Loại | Mục đích |
|---|---|
| `dependencies` | Mô hình functional dependencies giữa các cột; hữu ích cho một số equality predicates |
| `ndistinct` | Ước lượng số tổ hợp distinct, hữu ích cho GROUP BY/DISTINCT |
| `mcv` | Theo dõi các tổ hợp giá trị phổ biến của nhiều cột |

### 26.3. Xem pg_stats_ext

~~~sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    n_distinct,
    dependencies
FROM pg_stats_ext
WHERE schemaname = 'plan_lab'
  AND tablename = 'orders'
ORDER BY statistics_name;
~~~

Cột và quyền đọc view có thể khác giữa các major versions. Nếu một cột không khả dụng, tra catalog/view của version đang dùng.

### 26.4. Giới hạn của extended stats

- Dependencies không áp dụng cho mọi range/cross-column predicate.
- MCV đại diện một phần phân phối.
- `ndistinct` không thay được toàn bộ join fan-out statistics.
- Trong nhiều PostgreSQL versions hiện hành, extended stats chưa được dùng tổng quát để ước tính selectivity **join giữa hai relation**.
- Dữ liệu thay đổi vẫn cần ANALYZE.

Vì vậy nếu sai estimate bắt đầu **ở join**, tạo stats trên các cột cùng một bảng có thể chưa đủ.

### 26.5. Bài thực hành so trước/sau

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab.orders
WHERE status = 'paid'
  AND customer_id BETWEEN 1 AND 100;
~~~

Sau `CREATE STATISTICS` và ANALYZE, chạy lại. Estimate khác hoặc không khác đều là quan sát hợp lệ: mục tiêu là **đọc bằng chứng**.

---

## 27. Sai ước lượng join: phân bố khóa và fan-out

### 27.1. Cardinality join không chỉ là số hàng hai bảng

~~~sql
SELECT COUNT(*)
FROM plan_lab.orders AS o
JOIN plan_lab.order_items AS i
  ON i.order_id = o.order_id;
~~~

Lab có 120.000 orders, 240.000 items, mỗi order hai items, nên kết quả join là **240.000 rows** nếu dữ liệu được nạp đúng.

### 27.2. Uniqueness giúp planner

`orders.order_id` là PRIMARY KEY, `order_items.order_id` là FOREIGN KEY. Một phía unique theo order_id cung cấp thông tin cấu trúc. Trong ứng dụng thật, số items/order có thể skew; riêng lab tạo đúng hai items/order.

### 27.3. Join key skew

Trong dữ liệu thực, một số join keys có thể xuất hiện cực nhiều. Kiểm tra:

~~~sql
SELECT order_id, COUNT(*) AS item_count
FROM plan_lab.order_items
GROUP BY order_id
ORDER BY item_count DESC, order_id
LIMIT 20;
~~~

Nếu mọi group đều hai rows trong lab, không suy rộng ra production.

### 27.4. Điều kiện join sai có thể tạo output khổng lồ

~~~sql
-- Chỉ minh họa, không thực thi không LIMIT trên bảng lớn:
SELECT *
FROM plan_lab.orders AS o
JOIN plan_lab.order_items AS i
  ON i.order_id >= o.order_id;
~~~

Điều kiện `>=` có thể sinh cực nhiều cặp thay vì mỗi item thuộc một order. Khi output join lớn, cần kiểm tra **semantics của SQL**, không chỉ thống kê.

### 27.5. Những câu hỏi trước khi thêm index

- Khóa join có đúng và đủ cột composite key không?
- Có join fact-to-fact tạo fan-out không?
- Có duplicate hoặc bảng bridge không?
- Một phía có PK/UNIQUE constraint đúng nghiệp vụ không?
- Input estimate sai từ scan hay chỉ sai khi join?
- Có CROSS JOIN không chủ ý không?

### 27.6. Output đúng nhưng vốn đã rất lớn

Nếu business thực sự yêu cầu 10 triệu rows, planner ước tính đúng vẫn có query chậm vì số lượng output. Giải pháp có thể là pagination, pre-aggregation hoặc thay đổi yêu cầu, không phải “sửa stats để rows ít hơn”.

---

## 28. Prepared statements: generic plan và custom plan

### 28.1. Parameter sensitivity

~~~sql
SELECT order_id
FROM plan_lab.orders
WHERE status = $1;
~~~

`$1='paid'` có thể trả 85% bảng, `$1='canceled'` khoảng 5%. Đường truy cập tối ưu có thể khác. **Generic plan** không tối ưu riêng cho mọi giá trị như custom plan.

### 28.2. PREPARE/EXECUTE trong lab

~~~sql
PREPARE find_orders_by_status(text) AS
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE status = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('paid');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('canceled');

DEALLOCATE find_orders_by_status;
~~~

PostgreSQL có thể chọn custom hoặc generic plan theo chính sách và lịch sử prepared statements. Hai lần chạy chưa đủ để chắc chắn generic plan đã được dùng.

### 28.3. Thử so generic/custom trong lab

~~~sql
PREPARE find_orders_by_status(text) AS
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE status = $1;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('paid');
ROLLBACK;

BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('paid');
ROLLBACK;

DEALLOCATE find_orders_by_status;
~~~

Đây là **thí nghiệm** trên session lab, không phải đề xuất ép mọi prepared statement dùng custom/generic plan trong production.

### 28.4. ORM và connection pool

Driver/ORM có thể dùng bind parameters/server-side prepared plans. Một query chỉ chậm với giá trị tham số “hot” có thể liên quan parameter-sensitive plans. Cần thu thập **mẫu tham số đại diện** theo chính sách bảo mật, không chỉ SQL placeholder.

---

## 29. Biểu thức, casts và khả năng dùng index

### 29.1. Function trên cột có thể làm mất điều kiện indexable

Nếu có B-tree trên `created_at`, predicate:

~~~sql
WHERE created_at >= DATE '2026-03-01'
  AND created_at < DATE '2026-04-01'
~~~

thường dễ đối chiếu với index hơn:

~~~sql
WHERE created_at::text LIKE '2026-03%'
~~~

Câu thứ hai chuyển thành text rồi pattern match, có semantics khác và thường không dùng trực tiếp B-tree trên cột DATE cho range scan.

### 29.2. Query rewrite phải giữ đúng semantics

Với cột DATE, hai điều kiện có thể cùng diễn đạt tháng 3. Nhưng với TIMESTAMPTZ, “tháng 3” còn cần timezone nghiệp vụ. Không tự chuyển `date_trunc('day', timestamptz)` thành phạm vi UTC khi business cần ngày theo múi giờ khác.

### 29.3. Expression index là một lựa chọn riêng

~~~sql
CREATE INDEX ix_plan_orders_month_expr
ON plan_lab.orders (
    (date_trunc('month', created_at::timestamp))
);
~~~

Ví dụ cột DATE cast thành timestamp để tính month; index expression có thể hỗ trợ những query dùng đúng biểu thức phù hợp. Nó không tự tăng tốc mọi predicate theo tháng, đồng thời tăng chi phí ghi và phải đáp ứng tính immutable cần thiết cho index expression.

### 29.4. OR và selectivity

~~~sql
WHERE customer_id = 10 OR status = 'canceled'
~~~

PostgreSQL có thể dùng bitmap combination của các index, Seq Scan hoặc đường truy cập khác. Ước lượng OR có thể sai khi các điều kiện tương quan. Không tự thay bằng UNION ALL nếu hai nhánh có thể trả duplicate rows; phải giữ đúng kết quả của predicate OR.

---

## 30. Partial index và composite index

### 30.1. Partial index cho trạng thái hiếm

~~~sql
CREATE INDEX ix_plan_orders_canceled_customer
ON plan_lab.orders (customer_id)
WHERE status = 'canceled';
~~~

Nếu canceled chiếm tỷ lệ nhỏ, index partial có thể nhỏ và phù hợp workload chuyên biệt.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE status = 'canceled'
  AND customer_id = 50;
~~~

Planner có thể dùng partial index khi chứng minh predicate của query **hàm ý** predicate index. Generic plan với `status=$1` có thể không chứng minh được điều kiện cho mọi giá trị tham số.

### 30.2. Composite index

~~~sql
CREATE INDEX ix_plan_orders_customer_created
ON plan_lab.orders (customer_id, created_at DESC);
~~~

Có thể phục vụ:

~~~sql
SELECT order_id, created_at, amount
FROM plan_lab.orders
WHERE customer_id = 50
ORDER BY created_at DESC
LIMIT 20;
~~~

Cột đầu hỗ trợ equality, cột sau hỗ trợ order. Nếu query chủ đạo lọc thêm status hoặc một customer cực kỳ phổ biến, cần đo trên workload thay vì tin index này luôn tối ưu.

### 30.3. INCLUDE

~~~sql
CREATE INDEX ix_plan_orders_customer_date_cover
ON plan_lab.orders (customer_id, created_at DESC)
INCLUDE (amount, status);
~~~

INCLUDE giúp chứa thêm dữ liệu phục vụ một số index-only scan, nhưng cột include **không trở thành search key**, và visibility map có thể khiến Index Only Scan vẫn phải fetch heap.

### 30.4. Không tạo mọi index ứng viên trong production

Ba chỉ mục khác nhau đều tăng chi phí insert/update/delete, disk, VACUUM, reindex và thời gian deploy. Chọn theo truy vấn quan trọng, phân bố, plan và lợi ích đo được.

---

## 31. Một ví dụ điều tra query và thử sửa

### 31.1. Yêu cầu nghiệp vụ

API trả top 20 đơn đã thanh toán mới nhất trong tháng 3, kèm tên khách hàng.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.customer_id,
    o.created_at,
    o.amount,
    c.customer_name
FROM plan_lab.orders AS o
JOIN plan_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
  AND o.created_at >= DATE '2026-03-01'
  AND o.created_at < DATE '2026-04-01'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

### 31.2. Bảng ghi bằng chứng

| Câu hỏi | Nơi tìm |
|---|---|
| Execution Time bao nhiêu? | Dòng tổng kết plan |
| Root trả bao nhiêu hàng? | Actual rows của root |
| Node nào đụng nhiều shared/temp blocks? | `BUFFERS` và nodes con |
| Sort có external merge không? | `Sort Method`/`Disk` |
| Estimate lệch lần đầu ở đâu? | So `rows` với `actual rows` từ lá lên |
| Nested Loop inner chạy bao nhiêu loops? | `loops` của inner |
| Index Scan phải lọc thêm nhiều rows? | `Rows Removed by Filter` |
| Index nào đã tồn tại? | `pg_indexes` |
| Stats mới hay cũ? | `pg_stats`/`pg_stat_user_tables` |

### 31.3. Đề xuất một giả thuyết

Giả thuyết:

> Query mất nhiều thời gian để Sort và scan vì chưa có index phù hợp với status + created_at + order_id trong pattern filter/order.

Index ứng viên:

~~~sql
CREATE INDEX ix_plan_orders_status_created
ON plan_lab.orders (status, created_at DESC, order_id DESC);
~~~

Không khẳng định trước rằng index này luôn tốt hơn một index theo customer_id hay Seq Scan. Nếu query trả phần lớn bảng, hoặc điều kiện filter khác, trade-off có thể đảo chiều.

### 31.4. Đo trước/sau

1. Lưu plan và execution metrics gốc.
2. Tạo index ứng viên trong lab/staging.
3. ANALYZE nếu dữ liệu/stats có thay đổi.
4. Chạy lại đúng query/params.
5. So rows, buffers, sort method, loops và thời gian qua nhiều lần.
6. Đo write throughput, index size và tác động các query khác.
7. Chỉ giữ thay đổi nếu cải thiện đáng tin và chi phí chấp nhận được.

### 31.5. Có thể phải sửa SQL thay vì thêm index

Nếu SQL tạo hàng triệu intermediate rows do join sai, DISTINCT không cần thiết hoặc group sai mức dữ liệu, index chưa chắc giải quyết. Phải xác định **mức chi tiết kết quả** và semantics trước khi tối ưu access path.

---

## 32. Partition pruning và ước lượng trên bảng phân vùng

### 32.1. Dấu hiệu trong plan

~~~text
Append
  -> Seq Scan on orders_2026_03
  -> Seq Scan on orders_2026_04
~~~

Plan còn có thể dùng MergeAppend/Parallel Append. Ở một số tình huống, output có `Subplans Removed` hoặc node `never executed` do execution-time partition pruning.

### 32.2. Không thấy mọi partition không phải lỗi

Nếu query lọc đúng tháng 3 và partition pruning hoạt động, những partition ngoài tháng có thể không được scan. Nhưng nếu predicate bọc partition key bằng cast/function khiến optimizer không suy ra phạm vi, nó có thể xét nhiều partition hơn cần thiết.

### 32.3. Stats trên partition

Phân bố mỗi partition có thể khác nhau. Tháng khuyến mại có tỷ lệ canceled cao, tháng bình thường rất thấp. Cần kiểm tra stats trên parent/child phù hợp phiên bản PostgreSQL, không lấy tổng rows của parent rồi giả định mọi partition đồng nhất.

### 32.4. Partition và parallel workers

Một partition cực lớn có thể khiến phân bố công việc giữa workers không đều; nguyên nhân chậm có thể là **skew và xử lý parallel**, không phải thiếu index.

---

## 33. Các nguồn sai lệch khác cần điều tra

### 33.1. Data skew theo khách hàng

Vài khách có 100.000 đơn trong khi đa số có 1–2 đơn. Ước tính bằng “đơn trung bình/khách” sẽ sai mạnh cho hot keys. Xem MCV/frequency và generic/custom plans.

### 33.2. Correlation giữa filter

Một category gần như chỉ bán trong một region. Khi planner nhân xác suất như hai biến độc lập, kết quả sai. Thử thống kê đa cột nếu hai thuộc tính ở cùng bảng và phiên bản hỗ trợ pattern đó.

### 33.3. Biểu thức khó ước lượng

Function hoặc cast không khớp statistics/index có thể làm estimates kém. Không khai báo một function VOLATILE thành IMMUTABLE nếu nó phụ thuộc thời gian, bảng hoặc session chỉ để planner sử dụng index.

### 33.4. Giá trị nằm ngoài histogram cũ

Bảng append theo thời gian có các timestamp mới hơn mẫu stats. Query tìm một giờ vừa qua có thể có estimates kém nếu autoanalyze không theo kịp lượng dữ liệu mới.

### 33.5. NULL fraction

Nếu 90% dữ liệu là NULL nhưng thống kê phản ánh 5%, `IS NULL`/`IS NOT NULL` có thể sai. Kiểm tra `null_frac`.

### 33.6. Join keys trùng nhiều

Join với bảng thiếu uniqueness hoặc bridge table có duplicates tạo fan-out. PRIMARY KEY/UNIQUE constraint đúng bất biến không chỉ bảo vệ dữ liệu mà còn cung cấp metadata để optimizer chọn kế hoạch.

### 33.7. Prepared plans

Một generic plan dùng chung có thể phù hợp cho status paid nhưng kém với canceled (hoặc ngược lại). Quan sát actual plan/params thực, không chỉ một EXPLAIN với literal.

### 33.8. Dữ liệu rộng

`SELECT *` trên bảng có cột payload TEXT rộng có thể tăng width, sort/hash memory, heap fetch và network transfer. Nếu API chỉ cần `order_id` và `amount`, chọn đúng cột có thể cải thiện mà không thay đổi index.

### 33.9. Concurrent load

Một plan chạy 200 ms ở chế độ đơn luồng có thể mất vài giây khi có 100 requests đồng thời. Không kết luận chỉ do cardinality sai; có thể là queueing, shared I/O, locks, CPU saturation hoặc pool.

### 33.10. JIT trên query nhỏ

Nếu JIT compile chiếm phần lớn Execution Time của câu SQL ngắn, xem cấu hình/threshold JIT và workload. Không chỉ tăng stats target hoặc thêm index mù quáng.

---

## 34. Tìm query tốn tổng tài nguyên qua pg_stat_statements

EXPLAIN giúp phân tích **một lần chạy**. Trong production cần biết query nào gọi rất nhiều lần hoặc gây latency tổng lớn.

Khi extension `pg_stat_statements` đã được cấu hình đúng theo quy trình vận hành:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Lưu ý: chỉ CREATE EXTENSION **không chứng minh cơ chế thu thập stats đã hoạt động**; thường cần preload/cấu hình server tương ứng và quyền phù hợp.

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    LEFT(query, 200) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Chỉ chạy nếu view đã sẵn sàng trên môi trường và role được phép xem.

### 34.1. Tổng thời gian vs thời gian trung bình

| Query | Calls | Mean | Total |
|---|---:|---:|---:|
| A | 100.000 | 2 ms | 200.000 ms |
| B | 10 | 1.000 ms | 10.000 ms |

Query B chậm mỗi lần nhưng A tốn tổng tài nguyên lớn qua tần suất. Phải phân biệt mục tiêu giảm **latency một request** và giảm **tổng tải**.

### 34.2. Mean không phải p95

`mean_exec_time` là trung bình, không phải percentile. Khi cần tail latency, dùng dữ liệu phân phối từ APM/metrics/logging phù hợp.

### 34.3. Queryid và parameters

Query được normalized có thể gom nhiều giá trị tham số dưới một queryid. Nó không cung cấp mọi parameter sample, plan variant hay cache state. Kết hợp query statistics với EXPLAIN representative parameters.

### 34.4. Bảo vệ query logs

Plan và SQL text có thể chứa literal, tên bảng hoặc dữ liệu nhạy cảm. Không gửi production logs cho dịch vụ ngoài không được phê duyệt.

---

## 35. Quy trình điều tra: từ triệu chứng đến nguyên nhân

~~~mermaid
flowchart TD
    A["Query chậm / p95 tăng"] --> B["Thu SQL, params, plan, metrics"]
    B --> C["EXPLAIN ANALYZE BUFFERS ở môi trường được phép"]
    C --> D["Root: planning, execution, output rows"]
    D --> E{"Cardinality estimate lệch lớn?"}
    E -- "Có" --> F["Đi xuống tìm node bắt đầu lệch"]
    F --> G{"Lệch ở filter hay join?"}
    G -- "Filter" --> H["pg_stats, skew, ANALYZE, extended stats"]
    G -- "Join" --> I["Join keys, fan-out, uniqueness, skew"]
    E -- "Không / ít" --> J["Loops, buffers, Sort/Hash, parallel"]
    H --> K["Nêu một giả thuyết dựa trên evidence"]
    I --> K
    J --> K
    K --> L["Đo trước/sau cùng workload"]
    L --> M{"Cải thiện ổn định, trade-off chấp nhận?"}
    M -- "Có" --> N["Triển khai với monitoring"]
    M -- "Không" --> O["Khôi phục, xét giả thuyết khác"]
~~~

### 35.1. Mẫu ghi chú chẩn đoán

~~~text
Query fingerprint:
Parameter profile:
PostgreSQL version:
Row counts / table sizes:
Indexes present:
Last ANALYZE:
Plan captured at:
Planning Time:
Execution Time:
Worst estimate ratio:
First divergent node:
Highest loops and inner node:
Highest shared read / temp I/O branch:
Sort Method / Hash Batches:
Workers planned / launched:
Hypothesis:
Change:
After-plan evidence:
Safety / rollback:
~~~

Không ghi “lỗi tại Hash Join” chỉ vì node Hash Join có inclusive time cao; đi sâu phân tích build, probe, row counts và I/O.

### 35.2. Mục tiêu phụ thuộc workload

Một báo cáo cuối ngày cần giảm thời gian chạy job/tổng tài nguyên, còn API realtime thường cần giảm p95/p99 và tránh blocking. Lựa chọn index/plan được đánh giá theo mục tiêu chính.

### 35.3. Thử từng thay đổi

Không cùng lúc tạo năm index, tăng work_mem, disable Nested Loop và rewrite SQL rồi kết luận “tối ưu thành công” mà không biết nguyên nhân. Mỗi lần thử nên có giả thuyết, bằng chứng và cách rollback.

---

## 36. Checklist đọc kế hoạch

### 36.1. SQL và môi trường

- [ ] Có đúng tham số/literal values đại diện chưa?
- [ ] Đang đo SELECT hay DML có side effects?
- [ ] Có LIMIT/OFFSET, DISTINCT, ORDER BY, outer joins?
- [ ] Cùng dữ liệu/schema/index với môi trường mục tiêu?
- [ ] Có prepared generic/custom plan?
- [ ] Còn transaction/lock/concurrent load nào ảnh hưởng không?

### 36.2. Estimated

- [ ] `rows` ở từng node, không chỉ root.
- [ ] `width` hợp lý với dữ liệu rộng?
- [ ] Không đọc `cost` thành ms.
- [ ] Sai estimate bắt đầu ở scan hay join?
- [ ] Settings/cost model có khác mặc định?

### 36.3. Actual

- [ ] `actual rows` kết hợp `loops`.
- [ ] `never executed`, LIMIT early exit, partition pruning.
- [ ] `actual time` inclusive/per-loop, không cộng toàn cây.
- [ ] `Rows Removed by Filter/Join Filter/Recheck`.
- [ ] `Index Cond` so với `Filter`.
- [ ] `shared hit/read`, temp read/write, I/O timing.
- [ ] Sort Method, Disk, Hash Batches và Memory.
- [ ] Workers Planned/Launched và phân phối worker.

### 36.4. Nguyên nhân và nghiệm chứng

- [ ] Stats cũ hay stats chưa đủ mô hình hóa?
- [ ] Skew/correlation/NULL/duplicate join keys?
- [ ] Index phục vụ filter + ORDER BY + LIMIT?
- [ ] Inner node bị lặp quá nhiều?
- [ ] Query tạo intermediate rows không cần thiết?
- [ ] Có yếu tố concurrency, I/O, JIT, parallelism?
- [ ] Đo trước/sau nhiều lần trên dữ liệu đại diện?
- [ ] Đã đánh giá tác động ghi, disk và regression queries?

---

## 37. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Cách đọc |
|---|---|---|
| “cost=1000 tức 1000 ms” | Cost là mô hình tương đối | Xem actual time và Execution Time |
| “rows=2 loops=5000 nghĩa hai hàng tổng” | Hai rows trung bình **mỗi loop** | Khoảng 10.000 output rows |
| “Năm nodes mỗi node 100 ms ⇒ 500 ms” | Cha bao gồm thời gian con | Dùng Execution Time, đọc cây |
| “Root tốn nhất là lỗi” | Root thường gồm mọi subtree | Lần xuống nhánh con |
| “Seq Scan luôn xấu” | Đọc phần lớn bảng có thể hợp lý | Xem selectivity |
| “Index Scan luôn tốt” | Nhiều random fetch/loops có thể đắt | Buffers, Heap Fetches, loops |
| “Filter loại nhiều ⇒ thêm index là xong” | Index có thể không giúp hoặc workload cần toàn bảng | Xem predicate/workload |
| “Hash Join là kế hoạch sai” | Có thể tối ưu | Xem build side, batches, fan-out |
| “external merge ⇒ tăng work_mem toàn server” | Memory mỗi operator, nhiều query concurrent | Thử cục bộ, đánh giá tải |
| “Recheck Cond ⇒ index trả kết quả sai” | Recheck đảm bảo predicate đúng | Exact/lossy pages, candidates |
| “shared read = physical disk I/O” | OS page cache có thể phục vụ | Kết hợp I/O timings |
| “shared hit không tốn CPU” | Buffer access và loops vẫn có chi phí | Xem actual time |
| “ANALYZE làm estimate luôn đúng” | Correlation/join/params vẫn khó | Đo lại cardinality |
| “Extended stats chữa mọi join estimate” | Hỗ trợ có giới hạn | Xem join keys, uniqueness |
| “Statistics target càng cao càng tốt” | Chi phí stats tăng và nhiều lỗi không liên quan | Điều chỉnh chọn lọc |
| “Planner phải chọn index mới tạo” | Cost-driven | Kiểm tra EXPLAIN |
| “LIMIT 10 nghĩa xử lý tối đa 10 rows” | Sort/Aggregate có thể đọc hết | Xem subtree |
| “OFFSET 100000 chỉ xử lý LIMIT 20” | Phải bỏ nhiều positions | Keyset pagination |
| “Workers Planned là Workers Launched” | Runtime có thể cấp ít hơn | Xem cả hai |
| “EXPLAIN ANALYZE DELETE chỉ dự đoán” | Thực sự DELETE | Lab và rollback phù hợp |
| “Một lần 9 ms vs 10 ms đủ kết luận” | Nhiễu cache/concurrency | Đo nhiều lần |
| “LEFT JOIN WHERE/ON đổi qua lại chỉ để nhanh” | Có thể đổi tập kết quả | Giữ semantics |
| “Mean latency là p95” | Trung bình không phải percentile | Đo phân phối |

---

## 38. Bài tập thực hành

Các bài dùng `plan_lab.customers`, `orders` và `order_items` ở phần 7. Những đoạn plan in text trong đề **chỉ là số liệu giả định để luyện đọc**, không phải output cố định của một PostgreSQL server.

### Bài 1 — Cost không phải mili giây

Cho node:

~~~text
Index Scan on orders
  (cost=0.42..350.00 rows=100 width=24)
  (actual time=0.040..2.800 rows=120 loops=1)
~~~

Giải thích chính xác bốn số 0.42, 350.00, 100, 120. Có thể kết luận node “dự đoán 350 ms nhưng chạy 2,8 ms” không?

### Bài 2 — Startup cost

Một query có `LIMIT 1`. Planner lựa chọn giữa plan A có startup cost thấp nhưng total cost cao và plan B có total cost thấp nhưng startup cost cao. Vì sao A có thể được chọn?

### Bài 3 — Tính tổng output từ loops

~~~text
Index Scan
  (cost=... rows=2 ...)
  (actual time=0.010..0.030 rows=3 loops=10000)
~~~

Ước lượng tổng số rows đã được trả từ node này và thời gian per-node cộng dồn thô theo `actual time`. Nêu giới hạn của phép tính thời gian.

### Bài 4 — Sai lệch cardinality

Tính misestimate factor và hướng sai cho các cặp:

1. Estimated 50, actual 5000.
2. Estimated 30000, actual 100.
3. Estimated 2000, actual 2400.
4. Estimated 1, actual 0.

### Bài 5 — Tìm điểm bắt đầu lệch

~~~text
Hash Join: estimated 10000, actual 500000
  Seq Scan orders: estimated 100000, actual 105000
  Hash:
    Seq Scan customers: estimated 2000, actual 2000
~~~

Các scan có chính xác không? Nên điều tra filter của scan hay selectivity/logic của join trước? Vì sao?

### Bài 6 — Root lớn nhất có phải lỗi?

~~~text
Aggregate actual time=...1000ms
  Hash Join actual time=...990ms
    Seq Scan A actual time=...600ms
    Hash actual time=...390ms
~~~

Có được nói riêng Aggregate mất 1000 ms không? Giải thích inclusive time.

### Bài 7 — Rows Removed by Filter

~~~text
Seq Scan on orders
  actual rows=100 loops=1
  Rows Removed by Filter: 119900
~~~

Khoảng bao nhiêu rows được kiểm tra? Vì sao phải xem predicate trước khi thêm index?

### Bài 8 — Index Cond vs Filter

~~~text
Index Scan on orders
  Index Cond: (customer_id = 50)
  Filter: (status = 'canceled')
  Rows Removed by Filter: 5000
~~~

Điều kiện nào định hướng index lookup? Điều kiện nào loại candidates? Đề xuất một kiểu index ứng viên nếu query này cực kỳ phổ biến.

### Bài 9 — Buffer counts

`shared hit=120000` và `shared read=0`. Có thể kết luận query không tốn tài nguyên và chạy rất nhanh không? Vì sao?

### Bài 10 — Physical disk

`shared read=5000` có nghĩa chắc chắn OS đã đọc 5000 page từ SSD vật lý không? Nêu công cụ/số đo cần xem thêm.

### Bài 11 — Cộng buffer

Node cha có `shared hit=1500`; hai node con có `shared hit=800` và `shared hit=700`. Có thể kết luận tổng là 3000 buffer hits không?

### Bài 12 — External sort

~~~text
Sort
  Sort Method: external merge  Disk: 50000kB
  Buffers: temp read=6500 written=6600
~~~

Đây là dấu hiệu gì? Nêu ít nhất ba hướng điều tra/thử nghiệm.

### Bài 13 — Top-N heapsort

Vì sao `ORDER BY amount DESC LIMIT 10` có thể dùng memory ít hơn full sort, nhưng vẫn cần đọc rất nhiều rows?

### Bài 14 — Hash Batches

~~~text
Hash
  Buckets: 65536 Batches: 16 Memory Usage: 8192kB
~~~

`Batches=16` gợi ý gì? Nêu bốn thông số/điều kiện nên kiểm tra.

### Bài 15 — work_mem

Một query có ba sort và hai hash, 20 query đồng thời. Vì sao tăng `work_mem` toàn server từ 4 MB lên 512 MB có thể nguy hiểm?

### Bài 16 — COUNT(*) một row

~~~text
Aggregate actual rows=1
  Seq Scan orders actual rows=120000
~~~

Vì sao kết quả cuối chỉ một row nhưng query vẫn có thể tốn nhiều thời gian?

### Bài 17 — Nested Loop

Outer trả 20.000 rows, inner index scan trả trung bình hai rows/loop với loops=20.000. Output join xấp xỉ bao nhiêu? Tại sao inner scan 0,025 ms/loop vẫn có thể đáng chú ý?

### Bài 18 — Parallel

~~~text
Gather
  Workers Planned: 3
  Workers Launched: 2
  -> Parallel Seq Scan
       actual rows=30000 loops=3
~~~

Ước tính bao nhiêu rows được xử lý qua parallel node? Có được nhân 30.000 × (Workers Planned + 1) không?

### Bài 19 — ANALYZE sau bulk load

Viết SQL xem `n_mod_since_analyze`, `last_analyze` và `last_autoanalyze` của bảng orders, sau đó ANALYZE. Các số đó có phải COUNT(*) chính xác không?

### Bài 20 — pg_stats

Viết SQL xem `most_common_vals`, `most_common_freqs` và `n_distinct` cho `orders.customer_id`. Nếu `n_distinct` âm, hiểu thế nào?

### Bài 21 — Tăng statistics target

Viết SQL tăng target của `customer_id` lên 500 và cập nhật thống kê. Tại sao không áp dụng cùng mức cho mọi cột?

### Bài 22 — Extended statistics

Viết SQL tạo `CREATE STATISTICS` loại `mcv` và `dependencies` cho `orders(status,customer_id)`. Hạn chế của nó với join liên bảng là gì?

### Bài 23 — Skew và selectivity

Trong lab, status paid chiếm khoảng 85%, canceled khoảng 5%. Vì sao một index chỉ trên `status` có thể có giá trị khác nhau cho hai predicate này?

### Bài 24 — Generic/custom plans

Viết `PREPARE` cho query lọc `status = $1` và `EXPLAIN EXECUTE` với paid, canceled. Vì sao không thể chỉ nhìn một lần chạy rồi kết luận phương án tối ưu cho mọi tham số?

### Bài 25 — Expression vs range

Viết lại predicate:

~~~sql
WHERE created_at::text LIKE '2026-03%'
~~~

bằng range predicate trên cột DATE, bảo đảm lấy các đơn trong tháng 3/2026.

### Bài 26 — Partial index

Viết index partial phục vụ query tìm đơn canceled của một customer. Với prepared generic plan có `status=$1`, tại sao optimizer có thể không dùng index này?

### Bài 27 — Composite index và ORDER BY

Viết một index ứng viên cho:

~~~sql
SELECT order_id, created_at
FROM plan_lab.orders
WHERE customer_id = 50
ORDER BY created_at DESC
LIMIT 20;
~~~

Giải thích cột đầu và cột sau trong index.

### Bài 28 — OFFSET

Tại sao `LIMIT 20 OFFSET 100000` có thể phải xử lý hơn 100.000 positions? Nêu một ý tưởng keyset pagination nếu sắp theo khóa duy nhất `order_id`.

### Bài 29 — Outer join semantics

So sánh:

~~~sql
LEFT JOIN plan_lab.orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'paid'
~~~

và:

~~~sql
LEFT JOIN plan_lab.orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
~~~

Hai query có thể trả cùng tập khách hàng khi khách không có đơn paid không?

### Bài 30 — EXPLAIN ANALYZE DML

Một kỹ sư định chạy `EXPLAIN (ANALYZE) DELETE FROM plan_lab.orders ...` trên production để “chỉ xem plan”. Điều gì sai trong lập luận này? Cách an toàn hơn?

### Bài 31 — JSON plan

Viết một lệnh `EXPLAIN` có `FORMAT JSON, ANALYZE, BUFFERS` cho query đếm orders. Vì sao JSON thuận tiện hơn parse text đối với công cụ tự động?

### Bài 32 — pg_stat_statements

Với extension đã sẵn sàng, viết query lấy 10 normalized statements có `total_exec_time` lớn nhất. Giải thích vì sao query có mean latency thấp vẫn có thể là mục tiêu tối ưu quan trọng.

### Bài 33 — Partition pruning

Một query lọc tháng 3 trên bảng partition theo tháng nhưng plan truy cập 24 partitions. Bạn nên kiểm tra predicate/partition key và stats như thế nào?

### Bài 34 — Query chậm dù estimate khá đúng

Tất cả scan estimates đều gần actual, nhưng plan có external Sort 2 GB, Hash Batches 64 và nhiều temp I/O. Sai cardinality có phải nguyên nhân bắt buộc không? Đề xuất quy trình điều tra.

### Bài 35 — Phân tích truy vấn với ba vấn đề

Giả sử plan cho:

~~~text
Limit actual rows=20 loops=1
  -> Sort actual rows=100000 loops=1
       Sort Method: external merge Disk: 80000kB
       -> Nested Loop actual rows=100000 loops=1
            -> Seq Scan on customers
                 estimated rows=100 actual rows=10000 loops=1
            -> Index Scan on orders
                 estimated rows=1 actual rows=10 loops=10000
~~~

Hãy xác định:
1. Misestimate factor ở customers.
2. Misestimate factor mỗi loop của inner.
3. Total rows inner xấp xỉ bao nhiêu?
4. Những triệu chứng nào có khả năng gây chậm?
5. Tại sao không chỉ tăng work_mem ngay?

### Bài 36 — Bài tổng hợp: lập báo cáo điều tra

Một API query chậm trên production, chỉ với một số customer có nhiều đơn. Hãy đề xuất kế hoạch điều tra an toàn từ thu thập SQL/parameters đến thử index/stats và triển khai, trong đó nêu cách phân biệt sai estimate với nghẽn I/O hoặc concurrent load.

---

## 39. Gợi ý lời giải

### Bài 1 — Cost không phải mili giây

- `0.42` là **startup cost** ước tính theo đơn vị tương đối của planner.
- `350.00` là **total cost** ước tính để node trả hết output theo cost model.
- `rows=100` là số output rows planner dự đoán.
- `actual rows=120` là số output rows thực tế trong lần chạy (vì loops=1).
- `actual time=0.040..2.800` là mili giây đo được đến row đầu và đến khi node hoàn tất.

Không có phép đổi trực tiếp 350 cost units thành 350 ms; kết luận như vậy là sai.

### Bài 2 — Startup cost

Khi query chỉ cần một row, planner có thể ưu tiên plan **trả row đầu tiên sớm** dù tổng chi phí đọc hết bảng cao hơn. Nếu plan A có thể lấy row ngay qua index còn B cần sort toàn bộ để trả row đầu, A có thể phù hợp cho LIMIT 1.

Điều này còn phụ thuộc filter/selectivity và khả năng stop early, không phải “LIMIT luôn sử dụng index”.

### Bài 3 — Loops

`actual rows=3 loops=10000` cho tổng output xấp xỉ:

\[
3 \times 10000 = 30000 \text{ rows}
\]

`actual time=0.030 ms` mỗi loop cho ước lượng thô:

\[
0.030 \times 10000 = 300\text{ ms}
\]

Không coi 300 ms là **exclusive CPU time** vì node timing có tính bao gồm, hiển thị làm tròn và instrumentation overhead. Dùng Execution Time tổng của query làm chuẩn.

### Bài 4 — Misestimate factor

| Estimated | Actual | Factor | Hướng |
|---:|---:|---:|---|
| 50 | 5.000 | 100× | Planner đánh giá thấp |
| 30.000 | 100 | 300× | Planner đánh giá cao |
| 2.000 | 2.400 | 1,2× | Planner đánh giá thấp nhẹ |
| 1 | 0 | Không dùng tỷ số hữu hạn | Không có output thực |

Khi actual=0, cần xem node có được thực thi không, filter/params có khớp không và có LIMIT/partition pruning không. Không kết luận một tỷ số vô hạn là “nguyên nhân lớn nhất”.

### Bài 5 — Join estimate

Hai scan gần đúng:

- Orders: 100.000 dự đoán so với 105.000 thực, sai ~1,05×.
- Customers: 2.000 dự đoán, 2.000 thực, sai 1×.

Join: 10.000 dự đoán so với 500.000 thực, sai **50×**. Nghi ngờ **join selectivity, join keys, duplicate keys hoặc fan-out** trước. Đọc `Hash Cond`, `Join Filter` và phân bố khóa, không chỉ tăng statistics target của một scan vốn đã gần đúng.

### Bài 6 — Inclusive time

Không. Node Aggregate có `actual time` bao gồm việc lấy input từ Hash Join. Nếu Aggregate kết thúc tại ~1000 ms và Hash Join ~990 ms, phép tổng hợp bản thân **không đương nhiên tốn 1000 ms**. Không trừ trực tiếp 1000-990 để có exclusive CPU time chính xác trong mọi plan; instrumentation, pipeline và timing semantics cần được hiểu.

### Bài 7 — Rows Removed by Filter

Trong một loop, khoảng:

\[
100+119900=120000
\]

candidates được xem xét. Nếu WHERE chọn 100 rows từ 120.000, một index phù hợp có thể hữu ích; nhưng cần xem predicate có indexable không, selectivity và mục tiêu query. Nếu việc scan toàn bảng là cần để tính tổng, thêm index chưa chắc cải thiện.

### Bài 8 — Index Cond vs Filter

- `Index Cond: customer_id=50` điều khiển việc tìm candidates qua index.
- `Filter: status='canceled'` được đánh giá sau đó và loại 5.000 rows trong ví dụ.

Ứng viên:

~~~sql
CREATE INDEX ix_plan_orders_customer_status
ON plan_lab.orders(customer_id, status);
~~~

Hoặc nếu canceled hiếm và workload chuyên biệt:

~~~sql
CREATE INDEX ix_plan_orders_customer_canceled
ON plan_lab.orders(customer_id)
WHERE status='canceled';
~~~

Chỉ chọn sau khi đo plan, update cost, query distribution và vấn đề prepared generic plans.

### Bài 9 — Shared hit

`shared hit=120000` vẫn có nghĩa 120.000 buffer accesses được ghi nhận ở các node tương ứng. CPU, repeated index lookups và lock/memory overhead vẫn có thể lớn. Chỉ biết toàn hit PostgreSQL buffer cache không đủ kết luận nhanh.

### Bài 10 — Shared read

`shared read=5000` cho biết PostgreSQL nạp 5.000 block vào shared buffers; OS cache có thể phục vụ mà không cần đọc vật lý từ SSD. Kiểm tra `I/O Timings` (nếu track_io_timing bật), metrics storage, thời gian node và cache state.

### Bài 11 — Cộng buffer

Không. Các buffer counts ở node cha thường đã **bao gồm các node con**. Từ parent=1500 và children=800+700 không thể cộng thành 3000 như ba nhóm độc lập. Hãy dùng cấu trúc cây để tìm nhánh tạo buffer accesses.

### Bài 12 — External sort

Sort đã dùng **external merge** và temp I/O, gợi ý dữ liệu sort vượt bộ nhớ được dùng cho phép toán trong cấu hình hiện tại.

Ba hướng thử:

1. Có thể lọc bớt hoặc trả ít cột trước Sort mà vẫn giữ semantics?
2. Có index hỗ trợ `WHERE` + `ORDER BY`, đặc biệt khi có LIMIT?
3. Có thể tăng `work_mem` **cục bộ và có giới hạn** để tránh spill trong workload này?
4. Xem estimated vs actual rows/width có sai không.
5. Đọc BUFFERS/temp/I/O Timing và concurrency.

Không tăng work_mem toàn server chỉ vì thấy dòng Disk.

### Bài 13 — Top-N heapsort

Với LIMIT 10, top-N heapsort có thể giữ số lượng candidate nhỏ thay vì phải lưu/sắp toàn bộ rows. Nhưng để biết top 10 lớn nhất khi không có ordered index phù hợp, nó vẫn cần **kiểm tra nhiều hoặc mọi hàng nguồn**.

### Bài 14 — Hash Batches

`Batches=16` gợi ý Hash Join phải chia công việc thành nhiều batch, thường vì hash build side không vừa bộ nhớ cho một batch theo chiến lược hiện tại.

Kiểm tra:

- Actual rows/width của build side vs estimate.
- `work_mem` và `hash_mem_multiplier`.
- Temp read/write và I/O Timings.
- Phân bố join keys/skew.
- Các filter có thể giảm build side trước join.
- Concurrency và total available memory.

### Bài 15 — work_mem

`work_mem` là giới hạn/nguồn lực liên quan **từng thao tác sort/hash**, không phải budget duy nhất của một session. Ba sort + hai hash × 20 requests có thể tạo nhiều memory-consuming nodes cùng lúc. Một phép nhân mang tính minh họa 5 × 20 × 512 MB ≈ **50 GiB** cho thấy mức rủi ro, dù cách cấp phát thực phụ thuộc thuật toán và không có nghĩa mọi node đều luôn sử dụng tối đa. Tăng toàn server có thể gây swap/OOM; thử cục bộ và đo.

### Bài 16 — COUNT(*) đầu ra một row

Aggregate chỉ tạo một row chứa tổng count, nhưng Seq Scan con vẫn xử lý 120.000 rows. Phân tích **công việc ở subtree** chứ không chỉ số output rows của root.

### Bài 17 — Nested Loop

Output gần:

\[
20000 \times 2=40000\text{ rows}
\]

Inner index scan gọi 20.000 lần × 0,025 ms ≈ **500 ms** thời gian thô. Nhiều lần tra index có CPU/buffer overhead lớn; muốn quyết định tối ưu cần đọc toàn bộ plan, index/heap fetch và Execution Time.

### Bài 18 — Parallel

`actual rows=30000 loops=3` cho khoảng **90.000 rows** qua node. Không dùng Workers Planned=3 rồi nhân 4 (120.000) vì thực tế Workers Launched=2 và leader có thể tham gia. Xem thông tin worker thực và plan.

### Bài 19 — Last ANALYZE

~~~sql
SELECT
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname='plan_lab'
  AND relname='orders';

ANALYZE plan_lab.orders;
~~~

Các số như `n_mod_since_analyze` là thống kê/ước lượng, không thay COUNT(*). `last_analyze`/`last_autoanalyze` có thể NULL nếu chưa có lần tương ứng.

### Bài 20 — pg_stats

~~~sql
SELECT
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname='plan_lab'
  AND tablename='orders'
  AND attname='customer_id';
~~~

`n_distinct` âm là biểu diễn tỷ lệ số distinct theo tổng số rows, không phải “số distinct âm”.

### Bài 21 — Statistics target

~~~sql
ALTER TABLE plan_lab.orders
  ALTER COLUMN customer_id SET STATISTICS 500;

ANALYZE plan_lab.orders;
~~~

Tăng độ chi tiết giúp ở một số phân bố nhưng làm thống kê/ANALYZE tốn thêm tài nguyên, chưa sửa được mọi correlation/join misestimate. Chỉ tăng cục bộ khi có evidence.

### Bài 22 — Extended statistics

~~~sql
CREATE STATISTICS st_plan_orders_status_cust
    (mcv, dependencies)
ON status, customer_id
FROM plan_lab.orders;

ANALYZE plan_lab.orders;
~~~

Extended stats hỗ trợ một số ước lượng tương quan **trong cùng bảng**, không làm PostgreSQL tự học mọi dependency **giữa hai bảng khác nhau** cho join selectivity. Kết quả cải thiện phải được đo.

### Bài 23 — Skew status

`paid` xuất hiện phần lớn bảng; index scan có thể phải lấy nhiều heap pages, nên Seq Scan hợp lý. `canceled` hiếm hơn, index scan/partial index có thể hữu ích. Kết quả cụ thể phụ thuộc index, selectivity, row width, cache và cost model.

### Bài 24 — Prepared statements

~~~sql
PREPARE orders_by_status(text) AS
SELECT order_id, customer_id
FROM plan_lab.orders
WHERE status=$1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_status('paid');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_status('canceled');

DEALLOCATE orders_by_status;
~~~

Do tham số có phân bố khác nhau và PostgreSQL có generic/custom planning, một lần đo không đủ. Cần quan sát plan variant, tần suất giá trị và latency thực.

### Bài 25 — Predicate range trên DATE

~~~sql
WHERE created_at >= DATE '2026-03-01'
  AND created_at < DATE '2026-04-01'
~~~

Nó tương ứng tháng 3/2026 theo cột DATE và thân thiện với B-tree range. Với TIMESTAMPTZ, phải điều chỉnh theo timezone nghiệp vụ trước khi biến đổi tương tự.

### Bài 26 — Partial index

~~~sql
CREATE INDEX ix_plan_orders_canceled_customer
ON plan_lab.orders(customer_id)
WHERE status = 'canceled';
~~~

Planner chỉ dùng khi biết query predicate hàm ý điều kiện partial. Generic plan `status=$1` không thể giả định mọi giá trị `$1` đều là canceled, nên có thể không sử dụng index.

### Bài 27 — Composite index

~~~sql
CREATE INDEX ix_plan_orders_customer_created
ON plan_lab.orders(customer_id, created_at DESC);
~~~

Equality `customer_id=50` tận dụng cột đầu; thứ tự `created_at DESC` hỗ trợ lấy các hàng mới nhất theo customer. Cần xem row fetch cho output columns và plan thực.

### Bài 28 — OFFSET

`OFFSET 100000` phải bỏ qua 100.000 vị trí trước khi trả 20 rows, dù có index theo thứ tự. Với order_id làm khóa tăng duy nhất, keyset pagination:

~~~sql
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE order_id > 100000
ORDER BY order_id
LIMIT 20;
~~~

Ý tưởng là dùng **last_seen_order_id** của trang trước, không nhất thiết literal 100000; nếu sắp DESC, dùng `order_id < last_seen_order_id` và ORDER BY DESC. API cần xác định semantics khi dữ liệu thay đổi giữa các trang.

### Bài 29 — LEFT JOIN semantics

Không giống nhau:

- `WHERE o.status='paid'` lọc các row unmatched có `o.status IS NULL`, khiến khách không có paid order không còn trong kết quả.
- `ON ... AND o.status='paid'` vẫn giữ mọi row bên trái; khách không có paid order có cột `o.*` bằng NULL.

Không rewrite giữa hai dạng chỉ để plan nhanh hơn mà không xác nhận yêu cầu nghiệp vụ.

### Bài 30 — DML và EXPLAIN ANALYZE

`EXPLAIN ANALYZE DELETE` **thực thi DELETE**. Không chạy tùy tiện trên production. Nếu chỉ muốn estimates, dùng:

~~~sql
EXPLAIN
DELETE FROM plan_lab.orders
WHERE status='canceled';
~~~

Nếu thật sự phải đo DML, dùng database lab/staging; hoặc khi được phép, transaction kiểm soát:

~~~sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM plan_lab.orders
WHERE status='canceled';
ROLLBACK;
~~~

Dù rollback dữ liệu trong DB, side effects ngoài DB và một số cơ chế như sequence allocation có thể không đảo ngược. Không coi ví dụ là lệnh an toàn chạy production.

### Bài 31 — FORMAT JSON

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT COUNT(*)
FROM plan_lab.orders;
~~~

JSON có cấu trúc đối tượng/array rõ hơn cho phần mềm đọc cây plan, đo rows/loops/temps và so sánh; không cần parse text bằng regex phụ thuộc whitespace/indentation. Cần chú ý những field có thể có/mất theo PostgreSQL version và node type.

### Bài 32 — pg_stat_statements

Khi extension đã được cấu hình:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    LEFT(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
~~~

Một query mean 2 ms chạy 100.000 lần tốn 200.000 ms tổng, có thể quan trọng hơn một query 1.000 ms chạy 10 lần. Cần tối ưu theo latency và tổng tải.

### Bài 33 — Partition pruning

Kiểm tra:

1. Partition key thực sự là `created_at` hay một biểu thức khác?
2. Query dùng range/cast phù hợp để optimizer suy ra tháng?
3. Phần WHERE có function khiến pruning khó không?
4. Partition constraints/bounds có đúng không?
5. Có execution-time pruning với `Subplans Removed`/`never executed` không?
6. Stats parent/child có đại diện dữ liệu từng partition không?

Đo lại EXPLAIN sau khi chỉnh query/stats nếu phù hợp, không tạo 24 index mới trước khi biết nguồn quét thừa.

### Bài 34 — Estimate đúng nhưng vẫn chậm

Sai cardinality **không phải nguyên nhân bắt buộc**. External sort 2 GB, hash 64 batches và temp I/O là dấu hiệu cần điều tra:

- Input rows/width quá lớn dù dự đoán đúng?
- SELECT * hoặc join fan-out thật quá lớn?
- Có thể giảm rows/columns trước sort/hash mà vẫn đúng nghiệp vụ?
- Có index hỗ trợ ORDER BY/LIMIT?
- Query đang thiếu memory cho workload hiện tại?
- `work_mem`/`hash_mem_multiplier` có thể thử cục bộ với concurrency budget?
- Storage temp/I/O có đang nghẽn?

Dùng BUFFERS/I/O Timings, Sort Method/Disk, Hash Batches và đo trước–sau.

### Bài 35 — Ba vấn đề phối hợp

1. Customers: estimated 100, actual 10.000 → **100× underestimate**.
2. Inner orders: estimated 1, actual 10 mỗi loop → **10× underestimate**.
3. Tổng output inner xấp xỉ 10 × 10.000 = **100.000 rows**.
4. Các triệu chứng:
   - Outer cardinality sai làm inner lookup lặp 10.000 lần.
   - Inner fan-out sai 10×.
   - Sort nhận 100.000 rows và tràn tệp tạm 80.000 kB.
   - Dù root Limit chỉ 20 rows, Sort có thể phải nhận toàn bộ input trước khi trả top 20.
5. Nếu chỉ tăng work_mem, có thể giảm sort spill nhưng vẫn để **10.000 lookups, cardinality estimate sai và join plan kém**. Nên điều tra stats/filters/join keys và cơ hội ORDER BY index access trước; thử memory chỉ sau khi có giả thuyết/budget.

### Bài 36 — Một kế hoạch điều tra có thể triển khai

1. Ghi **SQL fingerprint**, các tham số cho khách “hot” và khách bình thường, tỷ lệ gọi, p95/p99 (không ghi thông tin nhạy cảm trái quy định).
2. Thu PostgreSQL version, schema/index, row counts, `pg_stats`, `last_analyze` và cấu hình liên quan.
3. Đo `EXPLAIN (ANALYZE, BUFFERS)` trên staging/bản sao đại diện hoặc môi trường production có kiểm soát với SELECT an toàn.
4. Tại root, ghi Planning Time, Execution Time và output rows.
5. Đi xuống từng nhánh: tìm node đầu tiên sai estimate; tính `actual rows × loops` ở inner scans; kiểm tra fan-out.
6. Đọc `BUFFERS`, temp, I/O Timings, Hash Batches, Sort Method, workers; xem query có nghẽn I/O/CPU thay vì statistics không.
7. Nếu chỉ chậm một số customer, kiểm tra MCV/skew, prepared custom/generic plans và index filter phù hợp; tránh lấy average customer làm đại diện.
8. Chọn **một** hướng sửa: ANALYZE/target, index, expression rewrite hoặc query restructuring. Đo chính xác cùng params, dữ liệu và tải.
9. Đo ảnh hưởng write throughput, index size và query regression, không chỉ tốc độ một SELECT.
10. Triển khai theo migration an toàn, theo dõi latency/concurrency và có phương án rollback.

---

## 40. Tổng kết

**Ước tính sai số hàng là một trong những nguồn quan trọng khiến PostgreSQL chọn kế hoạch tốn kém, nhưng không phải mọi query chậm đều do ước tính sai.** Muốn tối ưu đáng tin, phải đọc song song dữ liệu dự báo của planner và bằng chứng thực tế từ executor.

Các điểm cần nhớ:

- `cost` là **đơn vị ước lượng tương đối**, không phải milliseconds.
- `rows` là số output rows ước tính của node; `actual rows` là số đo khi chạy, và **phải đọc cùng `loops`**.
- `actual time` ở node có tính **bao gồm** công việc con; không cộng total time toàn cây. `Execution Time` là số đo tổng của statement trong EXPLAIN ANALYZE.
- Sai lệch ước lượng nên được lần **từ nơi bắt đầu xuất hiện**, không chỉ xem node root.
- Nested Loop có thể đắt vì inner chạy hàng chục nghìn lần; Hash Join có thể bị batch/temp I/O; Sort có thể tràn disk; Aggregate có thể trả một row nhưng đọc hàng triệu input rows.
- `BUFFERS` giúp tìm lượng truy cập memory/storage; `shared read` không tự đồng nghĩa physical disk I/O, và buffer counts ở cha/con có tính bao gồm.
- `Rows Removed by Filter`, `Index Cond`, `Filter`, `Heap Fetches`, `Recheck Cond` và các chỉ số parallel cho biết công việc dư thừa nằm ở đâu.
- Thống kê từ `pg_stats`, `ANALYZE` và extended statistics có thể cải thiện estimates, nhưng không chữa mọi vấn đề correlation, join selectivity hoặc generic plans.
- B-tree/index phù hợp, partial/composite index, query rewrite, pre-aggregation, keyset pagination và memory adjustment đều có điều kiện áp dụng. Chọn dựa trên đo lường thay vì mẹo chung.
- `EXPLAIN ANALYZE` **thực thi câu lệnh**; cần bảo vệ dữ liệu thật và cân nhắc tác động của DML.
- Tối ưu phải đo **trước và sau** trên workload đại diện, xét cả latency, buffers, write cost, disk, concurrency và khả năng rollback.

Quy trình giải quyết vấn đề: **thu đúng SQL và tham số → EXPLAIN ANALYZE BUFFERS có kiểm soát → so estimated/actual rows và loops → tìm nhánh thật sự tiêu tốn CPU/I/O/memory → xác định giả thuyết về stats, query hoặc index → thử một thay đổi → đo và kiểm tra lại kết quả cùng ảnh hưởng vận hành**.

# Nhận biết quét bảng, truy cập chỉ mục, JOIN và sắp xếp

Hai câu SQL trả cùng một tập kết quả có thể chạy với tốc độ rất khác nhau. Một câu đọc lần lượt toàn bộ bảng; câu khác đi qua chỉ mục để tìm vài dòng. Một phép `JOIN` có thể được thực hiện bằng cách lặp tra cứu từng khóa, xây bảng băm trong bộ nhớ, hoặc đi qua hai luồng dữ liệu đã sắp xếp. Một câu `ORDER BY` đôi khi đòi sắp xếp hàng trăm nghìn dòng, nhưng đôi khi chỉ cần đọc một chỉ mục theo đúng thứ tự.

Điều quyết định không phải tên lệnh `SELECT` mà là **kế hoạch thực thi** (*execution plan*) do hệ quản trị cơ sở dữ liệu chọn.

Bài học **“Nhận biết quét bảng, truy cập chỉ mục, JOIN và sắp xếp”** thuộc chương **Chỉ mục và kế hoạch** của module **Database SQL**. Mục tiêu là đọc được một kế hoạch PostgreSQL và trả lời:

1. **Dữ liệu được đọc bằng cách nào?** Quét bảng tuần tự (`Seq Scan`), đọc chỉ mục (`Index Scan`, `Index Only Scan`) hay đọc qua bitmap (`Bitmap Heap Scan`)?
2. **Hai nguồn được nối với nhau bằng cách nào?** `Nested Loop`, `Hash Join` hay `Merge Join`?
3. **Thứ tự kết quả được tạo như thế nào?** Đã có sẵn từ chỉ mục, cần `Sort`, `Incremental Sort`, hay phải `top-N` cho `LIMIT`?
4. **Chi phí thực tế nằm ở đâu?** Node nào đọc nhiều dòng, lặp nhiều lần, loại nhiều dòng bằng `Filter`, đợi I/O hoặc sử dụng bộ nhớ/đĩa cho sort và hash?
5. **Khi nào nên thêm/chỉnh chỉ mục hay viết lại truy vấn?** Dựa trên dữ liệu quan sát, không suy luận rằng “có `Seq Scan` là sai” hoặc “có index là nhanh”.

Ví dụ chủ yếu dùng **PostgreSQL**. Các tên node (`Seq Scan`, `Bitmap Heap Scan`, `Hash Join`...) và cú pháp `EXPLAIN` là của PostgreSQL; những ý tưởng quét, tra cứu, nối và sắp xếp có thể áp dụng rộng hơn, nhưng tên kế hoạch và chi tiết optimizer khác nhau giữa các DBMS.

> **Nguyên tắc mở đầu:** `EXPLAIN` là **dự kiến của bộ tối ưu**, còn `EXPLAIN ANALYZE` là **đo một lần chạy thật**. Muốn hiểu một kế hoạch, đọc **từ các node nguồn ở dưới lên**, xem các dòng chảy qua từng node, rồi so ước lượng với thực tế.

## 1. Từ câu SQL đến kế hoạch thực thi

Xét truy vấn:

```sql
SELECT
    c.region,
    COUNT(*) AS order_count,
    SUM(o.amount) AS total_amount
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.region
ORDER BY total_amount DESC;
```

Về mặt logic, ta cần lọc đơn `PAID`, nối khách hàng để lấy vùng, nhóm theo vùng và sắp theo tổng tiền. Nhưng SQL **không nói trực tiếp** rằng:

- Phải đọc `orders` trước hay `customers` trước.
- Phải dùng chỉ mục `status` hay quét toàn bộ `orders`.
- Phải dùng hash join hay nested loop.
- Phải dùng hash aggregation hay sort/group aggregation.
- Phải tạo thứ tự bằng index hay một bước sort riêng.

PostgreSQL dùng **planner/optimizer** để chọn một kế hoạch dựa trên thống kê dữ liệu, chỉ mục, điều kiện, cardinality, tham số cấu hình và mô hình chi phí.

### 1.1. Một sơ đồ kế hoạch minh họa

```text
Sort (ORDER BY total_amount DESC)
  └─ HashAggregate (GROUP BY region)
       └─ Hash Join (c.customer_id = o.customer_id)
            ├─ Seq Scan on orders
            │    Filter: (status = 'PAID')
            └─ Hash
                 └─ Seq Scan on customers
```

Đây chỉ là **sơ đồ một phương án có thể có**, không phải kế hoạch bắt buộc. Tùy dữ liệu và chỉ mục, PostgreSQL có thể dùng `Index Scan`, `HashAggregate`, `GroupAggregate`, `Nested Loop`, `Merge Join` hoặc các node song song.

### 1.2. Thứ tự đọc kế hoạch

Kế hoạch dạng cây thường có node ngoài cùng ở trên, nguồn của node nằm ở các dòng thụt vào:

```text
Node cha
  └─ Node con
       └─ Node lá đọc bảng/chỉ mục
```

Để hiểu dữ liệu được tạo ra như thế nào, hãy đi từ **node lá → node cha → kết quả**. Để tìm câu lệnh đang trả kết quả theo thứ tự gì, hãy đọc các node **ở gần gốc**.

**Đừng nhầm thứ tự hiển thị của cây với một lịch chạy tuần tự cứng nhắc.** Các node như hash join, sort, aggregate có thể cần tiêu thụ toàn bộ hoặc một phần đầu vào trước khi xuất kết quả, còn những node khác có thể tạo dòng dần dần. Optimizer cũng có thể chạy song song.

## 2. Hai lệnh quan trọng: `EXPLAIN` và `EXPLAIN ANALYZE`

### 2.1. `EXPLAIN`: xem kế hoạch ước lượng

```sql
EXPLAIN
SELECT *
FROM orders
WHERE order_id = 123;
```

PostgreSQL đưa ra **kế hoạch dự kiến** và ước lượng chi phí/số dòng. Với `SELECT`, `EXPLAIN` thông thường **không chạy toàn bộ truy vấn để lấy dữ liệu**, nên không đo thời gian xử lý thực tế của nó.

### 2.2. `EXPLAIN (ANALYZE, BUFFERS)`: thực thi và đo

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE order_id = 123;
```

`ANALYZE` khiến truy vấn **được thực thi thật** và cung cấp các chỉ số thực tế như `actual time`, `rows`, `loops`; `BUFFERS` cho biết hoạt động trên các block/buffer theo cách PostgreSQL báo cáo.

Không đọc `EXPLAIN ANALYZE` như một bản benchmark tuyệt đối: thời gian còn chịu ảnh hưởng cache, tải hệ thống, số lần chạy, mức đồng thời và thời điểm thống kê.

### 2.3. Cảnh báo đặc biệt với lệnh ghi

```sql
EXPLAIN (ANALYZE)
UPDATE orders SET status = 'PAID'
WHERE order_id = 123;
```

**Lệnh trên thực sự thực hiện `UPDATE`**, không chỉ mô phỏng. Với `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `EXPLAIN ANALYZE` có thể làm thay đổi dữ liệu.

Khi cần đo một lệnh DML trong môi trường thử, có thể bọc:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE plan_lab_orders
SET amount = amount + 1
WHERE order_id = 123;

ROLLBACK;
```

`ROLLBACK` hoàn tác thay đổi dữ liệu giao dịch thông thường của ví dụ, nhưng không tự đảo ngược **mọi tác động bên ngoài** như HTTP/email do trigger hay ứng dụng phát đi, và sequence có quy tắc riêng. Tránh chạy phép đo DML trên production nếu chưa đánh giá tác động.

### 2.4. Tùy chọn hay gặp

| Cú pháp | Ý nghĩa |
|---|---|
| `EXPLAIN SELECT ...` | Kế hoạch ước lượng |
| `EXPLAIN (ANALYZE) SELECT ...` | Thực thi và báo runtime thực tế |
| `EXPLAIN (ANALYZE, BUFFERS)` | Thêm thông tin hoạt động buffer/I/O được hỗ trợ |
| `EXPLAIN (VERBOSE)` | Thêm chi tiết cột/biểu thức và một số thông tin nội bộ |
| `EXPLAIN (COSTS OFF)` | Ẩn chi phí ước lượng để tập trung cấu trúc |
| `EXPLAIN (FORMAT JSON)` | Trả cấu trúc máy đọc được cho công cụ phân tích |
| `EXPLAIN (SETTINGS)` | Hiển thị một số cấu hình planner thay đổi khỏi mặc định thích hợp |
| `EXPLAIN (ANALYZE, TIMING OFF)` | Thực thi thật nhưng hạn chế đo thời gian từng node, hữu ích khi overhead đo chi tiết lớn |

**Tên trường và thông tin bổ sung có thể thay đổi theo phiên bản PostgreSQL**; đọc chính kế hoạch của môi trường đang sử dụng.

## 3. Bộ dữ liệu thực hành có kích thước đủ quan sát

Các kế hoạch dưới đây dùng bảng **tạm** trong PostgreSQL để hạn chế rủi ro tác động dữ liệu thật. Số dòng tương đối lớn giúp planner có lý do cân nhắc nhiều cách đọc và nối.

### 3.1. Tạo bảng

```sql
CREATE TEMP TABLE plan_lab_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL,
    customer_tier TEXT NOT NULL
);

CREATE TEMP TABLE plan_lab_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES plan_lab_customers(customer_id),
    ordered_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0)
);
```

### 3.2. Sinh dữ liệu có thể tái tạo

```sql
INSERT INTO plan_lab_customers
    (customer_id, customer_name, region, customer_tier)
SELECT
    g,
    'Customer ' || g,
    CASE g % 4
        WHEN 0 THEN 'North'
        WHEN 1 THEN 'South'
        WHEN 2 THEN 'East'
        ELSE 'West'
    END,
    CASE WHEN g % 10 = 0 THEN 'VIP' ELSE 'STANDARD' END
FROM generate_series(1, 10000) AS s(g);

INSERT INTO plan_lab_orders
    (order_id, customer_id, ordered_at, status, amount)
SELECT
    g::bigint,
    (g % 10000) + 1,
    TIMESTAMP '2026-01-01 00:00:00'
        + (g % 365) * INTERVAL '1 day'
        + (g % 24) * INTERVAL '1 hour',
    CASE
        WHEN g % 10 < 7 THEN 'PAID'
        WHEN g % 10 < 9 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    (100 + (g % 900))::numeric(12, 2)
FROM generate_series(1, 120000) AS s(g);
```

Dữ liệu có **10.000 khách hàng** và **120.000 đơn hàng**. `status` được phân bố theo công thức minh họa: khoảng 70% `PAID`, 20% `PENDING`, 10% `CANCELLED`.

Thời gian được sinh trải trên nhiều ngày năm 2026. Đây là dữ liệu nhân tạo, **không dùng để suy luận phân phối thực tế** của hệ thống bán hàng.

### 3.3. Thêm chỉ mục

```sql
CREATE INDEX idx_plan_orders_customer_date
    ON plan_lab_orders (customer_id, ordered_at DESC);

CREATE INDEX idx_plan_orders_status_date
    ON plan_lab_orders (status, ordered_at DESC);

CREATE INDEX idx_plan_orders_date
    ON plan_lab_orders (ordered_at);

CREATE INDEX idx_plan_customers_region
    ON plan_lab_customers (region);
```

Hai khóa chính đã tạo chỉ mục phù hợp theo cơ chế PostgreSQL; ta bổ sung chỉ mục để minh họa truy cập theo khách, trạng thái và thời gian.

### 3.4. Cập nhật thống kê

```sql
ANALYZE plan_lab_customers;
ANALYZE plan_lab_orders;
```

`ANALYZE` giúp planner có thống kê phân phối và kích thước tương đối cập nhật. Bảng tạm PostgreSQL không được các tiến trình autovacuum của phiên khác tự phân tích như bảng thường theo cách bạn có thể kỳ vọng; sau nạp dữ liệu tạm quy mô lớn, nên chủ động `ANALYZE`.

### 3.5. Kiểm tra kích thước logic

```sql
SELECT COUNT(*) AS customers_count
FROM plan_lab_customers;

SELECT COUNT(*) AS orders_count
FROM plan_lab_orders;

SELECT status, COUNT(*) AS orders_count
FROM plan_lab_orders
GROUP BY status
ORDER BY status;
```

Các con số trên dùng để **hiểu dữ liệu thực hành**, không phải “bài test chất lượng nội dung”. Khi chạy ví dụ, PostgreSQL có thể chọn kế hoạch khác nhau tùy phiên bản/cấu hình/hệ thống; đó là điều bình thường và là một phần của bài học.

## 4. Đọc một dòng plan: `cost`, `rows`, `width`

Một node giả định có thể trông như:

```text
Seq Scan on plan_lab_orders
  (cost=0.00..2400.00 rows=84000 width=32)
  Filter: (status = 'PAID'::text)
```

**Đây là số minh họa, không phải output thực tế cố định của bộ dữ liệu.**

### 4.1. `cost=startup..total`

`cost=0.00..2400.00` là **chi phí ước lượng theo đơn vị nội bộ của planner**, không phải số mili-giây.

- **Startup cost:** chi phí dự kiến trước khi node có thể xuất dòng đầu tiên.
- **Total cost:** chi phí ước lượng để node tạo **toàn bộ** tập dòng dự kiến.

Các node như `Sort` thường phải đọc và sắp đầu vào trước khi trả dòng đầu tiên nên có startup cost đáng kể. Một `Index Scan` tìm đúng một khóa có thể có startup cost nhỏ.

**Không được đọc `cost=2400` là 2.400 ms**.

### 4.2. `rows`

`rows=84000` là **số dòng planner dự đoán node sẽ xuất ra**, không phải số dòng gốc của bảng. Nếu node có `Filter`, số dòng ước lượng là **sau khi áp Filter**.

Ước lượng có thể sai vì:

- Thống kê cũ.
- Phân phối lệch.
- Các cột tương quan nhưng planner ước lượng độc lập.
- Điều kiện dùng hàm/biểu thức khó dự báo.
- Join trên khóa có độ phân bố không đều.

Sai ước lượng dòng ở một node có thể dẫn tới lựa chọn JOIN, sort hoặc index không tối ưu ở các node phía trên.

### 4.3. `width`

`width=32` là **kích thước trung bình ước lượng của một dòng đầu ra**, tính theo byte. Nó ảnh hưởng dự toán bộ nhớ và chi phí truyền dữ liệu giữa các node.

`SELECT *` có thể làm mỗi dòng rộng hơn nhiều so với:

```sql
SELECT order_id, customer_id
FROM plan_lab_orders;
```

Nhưng giảm cột không tự đảm bảo index-only scan; còn tùy chỉ mục có chứa đủ cột cần đọc và điều kiện hiển thị dữ liệu trong MVCC.

## 5. Đọc thời gian và số dòng thực tế

Với `EXPLAIN (ANALYZE)`, plan có thể hiển thị:

```text
Index Scan using plan_lab_orders_pkey on plan_lab_orders
  (cost=0.42..8.44 rows=1 width=...)
  (actual time=0.025..0.027 rows=1 loops=1)
  Index Cond: (order_id = 123)
```

Giá trị số ở đây **chỉ mang tính minh họa**.

| Trường | Cách đọc |
|---|---|
| `actual time=a..b` | Thời gian thực tế trung bình để lấy dòng đầu và hoàn tất node cho mỗi lượt chạy, theo đơn vị ms |
| `rows=x` | Số dòng trung bình node xuất mỗi lượt thực thi, theo cách EXPLAIN báo |
| `loops=n` | Node được thực thi bao nhiêu lượt |
| `Planning Time` | Thời gian lên kế hoạch |
| `Execution Time` | Thời gian thực thi toàn statement theo cơ chế đo của PostgreSQL |
| `Rows Removed by Filter` | Số dòng bị điều kiện lọc của node loại, thường báo trung bình mỗi lượt khi có nhiều loops |

### 5.1. Bẫy `loops`

Giả sử node bên trong nested loop báo:

```text
Index Scan ...
  (actual time=0.015..0.016 rows=1 loops=10000)
```

Không nên nghĩ node đó chỉ chạy 0,016 ms **một lần**. Nó được gọi khoảng **10.000 lần**, mỗi lần lấy trung bình một dòng.

Ước lượng sơ bộ tổng công ở node phải xét **chi phí/thời gian mỗi lượt × loops**, đồng thời tránh cộng thời gian cha và con một cách máy móc vì thời gian node cha thường bao gồm thời gian xử lý con.

### 5.2. So `estimated rows` và `actual rows`

```text
Estimate: rows=100
Actual:   rows=100000 loops=1
```

Sai lệch ba bậc độ lớn là tín hiệu cần điều tra vì planner có thể đã chọn nested loop hoặc bộ nhớ hash quá nhỏ cho dữ liệu thực tế.

Nhưng không phải mọi sai lệch đều là nguyên nhân chậm:

- `rows=1` dự kiến và 2 thực tế thường không đáng lo với query nhỏ.
- Query bị `LIMIT` dừng sớm có thể khiến node chưa cần xuất hết dữ liệu.
- Một node có `loops=1000` phải so dòng **theo mỗi loop** hoặc tổng phù hợp, không lấy số `actual rows` đơn lẻ rồi kết luận.

## 6. `Seq Scan`: quét bảng tuần tự

**Sequential Scan** đọc các trang dữ liệu của bảng theo cách quét qua quan hệ, kiểm tra điều kiện và xuất những dòng hợp lệ.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, amount
FROM plan_lab_orders
WHERE amount >= 100;
```

Trong dữ liệu mẫu, mọi `amount` đều ít nhất 100 và **không có chỉ mục trên `amount`**. Kế hoạch có thể là:

```text
Seq Scan on plan_lab_orders
  Filter: (amount >= 100::numeric)
```

### 6.1. Vì sao quét toàn bảng không phải lúc nào cũng xấu?

Nếu truy vấn cần **phần lớn dòng** của bảng:

- Đọc từng trang dữ liệu liên tục có thể hiệu quả.
- Một index scan sẽ phải tra nhiều mục chỉ mục và có thể ghé rất nhiều trang heap.
- Chi phí đi theo index và lấy dữ liệu bảng có thể lớn hơn quét tuần tự.

Do đó, `Seq Scan` là **chiến lược hợp lý** khi cần phần lớn dữ liệu hoặc bảng rất nhỏ.

### 6.2. `Filter` trong `Seq Scan`

```text
Seq Scan on plan_lab_orders
  Filter: (status = 'PAID'::text)
  Rows Removed by Filter: ...
```

`Filter` là điều kiện được kiểm tra khi node quét và xử lý dòng. `Rows Removed by Filter` giúp thấy tỷ lệ bị loại.

Ví dụ có 120.000 dòng, 84.000 `PAID`, 36.000 không `PAID`. Một `Seq Scan` lọc `PAID` có thể đọc cả 120.000 dòng rồi loại khoảng 36.000.

Không thể chỉ nhìn số dòng bị loại mà quyết định thêm chỉ mục. Phải cân nhắc **tỷ lệ chọn lọc**, kích thước bảng, số cột cần, thứ tự kết quả, chi phí cập nhật chỉ mục và tần suất query.

### 6.3. `Parallel Seq Scan`

Trên bảng đủ lớn và khi planner chọn song song, có thể thấy:

```text
Gather
  └─ Parallel Seq Scan on big_table
       Filter: (...)
```

`Parallel Seq Scan` là nhiều tiến trình tham gia quét dữ liệu theo kế hoạch song song. `Gather` tập hợp kết quả. Không phải cứ thấy `Parallel` là tốc độ tăng tuyến tính theo số worker; có overhead khởi tạo, truyền dữ liệu, đồng bộ và giới hạn I/O/CPU.

## 7. `Index Scan`: truy cập dữ liệu nhờ chỉ mục

Chỉ mục B-tree phù hợp cho nhiều truy vấn bằng (`=`), khoảng (`<`, `>`, `BETWEEN`) và thứ tự theo khóa, tùy cấu trúc chỉ mục và điều kiện.

Ví dụ tìm một đơn theo khóa chính:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, ordered_at, status, amount
FROM plan_lab_orders
WHERE order_id = 123;
```

Kế hoạch thường có thể chọn:

```text
Index Scan using plan_lab_orders_pkey on plan_lab_orders
  Index Cond: (order_id = 123)
```

### 7.1. `Index Cond` và `Filter` khác nhau

Ví dụ:

```sql
EXPLAIN
SELECT *
FROM plan_lab_orders
WHERE customer_id = 77
  AND amount > 800;
```

Vì có chỉ mục `(customer_id, ordered_at DESC)` nhưng không có `amount`, một phương án có thể là:

```text
Index Scan using idx_plan_orders_customer_date
  Index Cond: (customer_id = 77)
  Filter: (amount > 800)
```

`Index Cond` chỉ ra phần điều kiện được dùng để **giới hạn mục index cần duyệt**; `Filter` là điều kiện bổ sung được kiểm tra trên dòng lấy được.

Nếu `customer_id=77` chỉ có khoảng một chục đơn, lọc `amount` sau khi tìm index vẫn hợp lý. Nếu `customer_id=77` có hàng triệu đơn, cần đánh giá chỉ mục và cách tổ chức query khác.

### 7.2. `Index Scan` thường phải đọc heap

Chỉ mục không nhất thiết chứa tất cả cột cần trả. Khi query cần `amount` mà index chỉ có `(customer_id, ordered_at)`, PostgreSQL có thể dùng index để tìm vị trí rồi đọc dữ liệu dòng từ **heap**.

Đó là lý do **index scan không mặc nhiên rẻ**: nhiều lookup rải rác trên bảng có thể phát sinh I/O nhiều hơn một lần seq scan.

### 7.3. Một điều kiện có thể được index hỗ trợ nhưng planner không chọn index

```sql
EXPLAIN
SELECT *
FROM plan_lab_orders
WHERE status = 'PAID';
```

Đã có index `(status, ordered_at DESC)`, nhưng vì `PAID` chiếm khoảng 70% bảng, planner **có thể** thích seq scan hơn.

**Sự hiện diện của index không bắt buộc hệ quản trị phải sử dụng nó.**

## 8. `Index Only Scan`: đọc chủ yếu từ chỉ mục

Một truy vấn có thể chỉ cần những cột đã nằm trong chỉ mục:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, ordered_at
FROM plan_lab_orders
WHERE customer_id = 77
ORDER BY ordered_at DESC;
```

Chỉ mục:

```sql
(customer_id, ordered_at DESC)
```

chứa đủ hai cột được hỏi. Planner có thể dùng `Index Only Scan`.

### 8.1. Vì sao là “only” nhưng vẫn có `Heap Fetches`?

PostgreSQL dùng cơ chế **MVCC** và phải xác nhận một dòng có thể nhìn thấy trong snapshot của query hay không. Thông tin visibility map giúp biết những trang heap mà tất cả tuple có thể xem là hiển thị theo điều kiện phù hợp.

Vì vậy `Index Only Scan` có thể xuất:

```text
Index Only Scan ...
  Heap Fetches: 120
```

Điều đó nghĩa là PostgreSQL vẫn phải ghé heap một số lần để xác nhận hiển thị; `Index Only Scan` **không bảo đảm `Heap Fetches = 0`**.

Với bảng tạm vừa được nạp dữ liệu, trạng thái visibility có thể khác bảng đã được vacuum phù hợp. Bài học về plan không đòi một kết quả `Heap Fetches` cố định.

### 8.2. Covering index và `INCLUDE`

PostgreSQL hỗ trợ thêm cột chỉ phục vụ truy vấn qua `INCLUDE` cho các loại index hỗ trợ:

```sql
CREATE INDEX idx_plan_orders_customer_cover
    ON plan_lab_orders (customer_id)
    INCLUDE (amount, status);
```

Với:

```sql
SELECT customer_id, amount, status
FROM plan_lab_orders
WHERE customer_id = 77;
```

planner có thêm một lựa chọn index-only nếu điều kiện MVCC và chi phí phù hợp. `INCLUDE` không làm các cột thêm vào trở thành **khóa sắp xếp/tìm kiếm có cùng vai trò** như các cột khóa index. Index lớn hơn cũng tăng chi phí ghi và bảo trì.

### 8.3. Phân biệt Index Scan với Index Only Scan

| Đặc tính | `Index Scan` | `Index Only Scan` |
|---|---|---|
| Dùng cấu trúc index để truy cập | Có | Có |
| Cần heap để lấy cột không có trong index | Có thể thường xuyên | Không vì cột đầu ra đã được index đáp ứng |
| Có thể cần heap kiểm tra visibility | Có thể | Có thể, báo `Heap Fetches` |
| Luôn nhanh hơn seq scan | Không | Không |
| Hỗ trợ sắp xếp theo khóa B-tree | Có thể | Có thể |

## 9. `Bitmap Index Scan` và `Bitmap Heap Scan`

Khi điều kiện lọc lấy **một tập dòng trung bình**, PostgreSQL có thể dùng index trước để xác định vị trí các tuple rồi gom những vị trí đó thành bitmap; tiếp theo đọc heap theo thứ tự trang.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, ordered_at, amount
FROM plan_lab_orders
WHERE ordered_at >= TIMESTAMP '2026-12-01'
  AND ordered_at <  TIMESTAMP '2027-01-01';
```

Một kế hoạch khả dĩ:

```text
Bitmap Heap Scan on plan_lab_orders
  Recheck Cond: (ordered_at >= ... AND ordered_at < ...)
  └─ Bitmap Index Scan on idx_plan_orders_date
       Index Cond: (ordered_at >= ... AND ordered_at < ...)
```

### 9.1. Đọc từ dưới lên

1. **`Bitmap Index Scan`**: tìm các vị trí tuple thỏa điều kiện trong index.
2. **`Bitmap Heap Scan`**: truy cập các trang heap liên quan, lấy các dòng và áp điều kiện kiểm tra lại nếu cần.
3. **Node cha**: trả kết quả cho các bước khác như aggregate/sort/join.

Bitmap có thể giảm truy cập heap rải rác so với lấy mỗi tuple theo từng lần tìm index. Nó đặc biệt hữu ích ở vùng chọn lọc trung gian, nhưng không phải chiến lược tối ưu mặc định cho mọi query có index.

### 9.2. `Recheck Cond` và bitmap lossy

Kế hoạch bitmap thường hiển thị `Recheck Cond`. Bitmap có thể lưu vị trí ở mức tuple chính xác hoặc **lossy** ở mức trang khi bị giới hạn bộ nhớ.

Nếu có bitmap lossy, PostgreSQL cần kiểm tra lại điều kiện trên nhiều tuple trong trang. Bạn có thể thấy:

```text
Heap Blocks: exact=... lossy=...
Rows Removed by Index Recheck: ...
```

Không nên suy ra chỉ vì có `Recheck Cond` là mọi dòng đã phải kiểm tra lại. Hãy đọc số `exact/lossy` và chỉ số thực tế khi có.

### 9.3. `BitmapAnd` và `BitmapOr`

Nếu có nhiều index phù hợp, planner có thể kết hợp các bitmap:

```text
Bitmap Heap Scan
  └─ BitmapAnd
       ├─ Bitmap Index Scan on idx_a
       └─ Bitmap Index Scan on idx_b
```

hoặc:

```text
Bitmap Heap Scan
  └─ BitmapOr
       ├─ Bitmap Index Scan on idx_a
       └─ Bitmap Index Scan on idx_b
```

`BitmapAnd` thường ứng với giao các điều kiện; `BitmapOr` thường ứng với hợp các điều kiện trong trường hợp optimizer chọn. Đây **không có nghĩa** mọi `AND` hoặc `OR` đều phải dùng bitmap; nó chỉ là một lựa chọn kế hoạch.

## 10. Nhận biết `Filter` được đẩy tới đâu

Xem hai truy vấn:

```sql
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE customer_id = 77
  AND ordered_at >= TIMESTAMP '2026-07-01';
```

```sql
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE EXTRACT(YEAR FROM ordered_at) = 2026;
```

Với chỉ mục `(customer_id, ordered_at DESC)`, câu thứ nhất có **khóa đầu bằng** và **điều kiện khoảng ở khóa tiếp theo**, rất phù hợp để planner cân nhắc `Index Cond` cho cả hai điều kiện.

Với `EXTRACT(YEAR FROM ordered_at)`, một chỉ mục B-tree thông thường trên `ordered_at` không nhất thiết được dùng để giới hạn khoảng theo cách trực tiếp, vì điều kiện đang áp **biểu thức lên cột**.

### 10.1. Viết khoảng thời gian nửa mở

```sql
WHERE ordered_at >= TIMESTAMP '2026-01-01'
  AND ordered_at <  TIMESTAMP '2027-01-01'
```

thường dễ để planner dùng index `ordered_at` theo khoảng hơn:

```sql
WHERE EXTRACT(YEAR FROM ordered_at) = 2026
```

Đây là một **gợi ý viết điều kiện**, không phải bảo đảm planner sẽ luôn chọn index. Nếu khoảng chọn phần lớn bảng, seq scan vẫn có thể tốt hơn.

### 10.2. Chỉ mục biểu thức

Nếu ứng dụng thường xuyên lọc chính xác một biểu thức:

```sql
CREATE INDEX idx_plan_orders_year
    ON plan_lab_orders ((EXTRACT(YEAR FROM ordered_at)));
```

PostgreSQL có thể cân nhắc chỉ mục biểu thức khi truy vấn có điều kiện tương thích. Cần xem tính bất biến của biểu thức, kiểu dữ liệu, tần suất và chi phí ghi.

Với `TIMESTAMPTZ`, các biểu thức lấy năm phụ thuộc múi giờ phiên có thể không đáp ứng điều kiện tạo index expression nếu chưa cố định ngữ nghĩa thời gian. Không sao chép chỉ mục trên `TIMESTAMP` ở đây sang `TIMESTAMPTZ` mà không xét volatility.

## 11. Chỉ mục nhiều cột: thứ tự khóa quan trọng

Chỉ mục mẫu:

```sql
CREATE INDEX idx_plan_orders_customer_date
    ON plan_lab_orders (customer_id, ordered_at DESC);
```

Nó sắp xếp trước theo `customer_id`, rồi trong mỗi customer theo `ordered_at DESC`.

### 11.1. Truy vấn phù hợp khóa đầu

```sql
SELECT order_id, customer_id, ordered_at
FROM plan_lab_orders
WHERE customer_id = 77
ORDER BY ordered_at DESC
LIMIT 10;
```

Index `(customer_id, ordered_at DESC)` có thể vừa giới hạn đúng một khách, vừa cung cấp thứ tự ngày mới nhất trước, giúp tránh `Sort` riêng trong kế hoạch thích hợp.

### 11.2. Chỉ lọc bằng cột thứ hai

```sql
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE ordered_at >= TIMESTAMP '2026-12-01';
```

Với index `(customer_id, ordered_at DESC)`, các dòng tháng 12 nằm rải dưới nhiều `customer_id`. Planner có thể thích chỉ mục **riêng trên `ordered_at`** hoặc seq scan. Không nên nói “trong index có `ordered_at` nên nó giống hệt index `(ordered_at)`”.

Các phiên bản PostgreSQL mới có thể có tối ưu như skip-scan trong những điều kiện phù hợp, vì vậy tránh quy tắc tuyệt đối “không có điều kiện khóa đầu thì index không bao giờ dùng”. Nhưng **thứ tự cột vẫn là yếu tố thiết kế quan trọng**.

### 11.3. Chọn index theo bộ ba

Khi thiết kế index cho truy vấn thường xuyên, xem:

1. **Điều kiện lọc**: bằng hay khoảng, độ chọn lọc.
2. **JOIN**: cột nào làm khóa tra cứu.
3. **ORDER BY / LIMIT**: có thể đọc index theo đúng thứ tự không.

Một index tốt cho filter có thể không tốt cho sắp xếp. Thêm index cho mỗi cột đơn lẻ cũng không luôn thay thế một index nhiều cột được thiết kế theo truy vấn.

## 12. Nhận biết `Nested Loop Join`

`Nested Loop` là cách nối trong đó các dòng của nguồn ngoài (*outer*) lần lượt được đối chiếu với nguồn trong (*inner*).

```text
Nested Loop
  ├─ Outer: lấy danh sách khách cần tìm
  └─ Inner: với mỗi khách, tìm đơn của khách đó
```

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id, c.region,
    o.order_id, o.amount
FROM plan_lab_customers AS c
JOIN plan_lab_orders AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 77
ORDER BY o.ordered_at DESC;
```

Một kế hoạch có thể là:

```text
Nested Loop
  ├─ Index Scan using plan_lab_customers_pkey on plan_lab_customers c
  │    Index Cond: (customer_id = 77)
  └─ Index Scan using idx_plan_orders_customer_date on plan_lab_orders o
       Index Cond: (customer_id = c.customer_id)
```

**Không bảo đảm** PostgreSQL luôn in đúng cây này; planner có thể rút gọn một số bước hoặc chọn cách khác.

### 12.1. Vì sao `Nested Loop` có thể rất nhanh?

Nếu nguồn ngoài chỉ có **một hoặc vài dòng**, và nguồn trong có index tìm nhanh theo khóa, tổng số lookup nhỏ.

Ví dụ:

```text
1 khách → khoảng 12 đơn → trả 12 dòng
```

Một vài lần tìm index có thể rẻ hơn xây hash table cho toàn bộ khách/đơn.

### 12.2. Vì sao nó có thể rất chậm?

Nếu outer có **100.000 dòng** và inner phải quét rất nhiều lần:

```text
Nested Loop
  ├─ Seq Scan on large_outer (100000 rows)
  └─ Seq Scan on large_inner (loops=100000)
```

thì chi phí có thể tăng rất lớn. Node trong được thực thi lại cho từng dòng outer nếu không có cơ chế tối ưu/caching phù hợp.

### 12.3. Dấu hiệu cần xem

- `loops` của node inner có lớn không?
- Inner dùng `Index Scan`, `Index Only Scan`, `Memoize`, hay `Seq Scan`?
- Có nhiều `Rows Removed by Join Filter` không?
- `actual rows` outer có lớn hơn rất nhiều so với ước lượng không?
- Bộ lọc ở outer đã giảm tập đầu vào trước khi join chưa?

**`Nested Loop` không phải lỗi tự thân.** Nó đặc biệt hợp lý cho truy vấn lookup theo khóa và một tập outer nhỏ.

## 13. Nhận biết `Hash Join`

`Hash Join` thường phù hợp với phép nối bằng (*equality join*) trên hai tập dữ liệu khi cách xây bảng băm và dò theo khóa có chi phí hợp lý.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.region, COUNT(*) AS order_count
FROM plan_lab_orders AS o
JOIN plan_lab_customers AS c
    ON c.customer_id = o.customer_id
GROUP BY c.region;
```

Một kế hoạch có thể có:

```text
HashAggregate
  Group Key: c.region
  └─ Hash Join
       Hash Cond: (o.customer_id = c.customer_id)
       ├─ Seq Scan on plan_lab_orders o
       └─ Hash
            └─ Seq Scan on plan_lab_customers c
```

### 13.1. Cách hoạt động

1. Một phía (thường là phía được chọn làm **build side**) được đọc và xây **hash table** theo khóa join.
2. Phía còn lại (*probe side*) được đọc, tra hash theo khóa và ghép các dòng khớp.
3. Node trả kết quả cho aggregate/sort ở phía trên.

Ở sơ đồ, `Hash` bên dưới `customers` cho biết bảng khách đang là nguồn để xây hash. Một truy vấn khác có thể xây hash từ phía còn lại.

### 13.2. Khi nào Hash Join mạnh?

- Join theo điều kiện bằng như `o.customer_id = c.customer_id`.
- Hai tập đủ lớn để nested loop tra cứu lặp nhiều lần kém hấp dẫn.
- Build side có thể chứa trong bộ nhớ hoặc xử lý theo batches hợp lý.
- Đầu vào không cần sắp theo khóa.

### 13.3. `Buckets`, `Batches`, `Memory Usage`

Trong `EXPLAIN ANALYZE`, node `Hash` có thể báo:

```text
Buckets: 16384  Batches: 1  Memory Usage: 620kB
```

Đây là số minh họa. Nếu phải chia thành **nhiều batch**, có thể liên quan việc hash table không nằm trọn trong giới hạn bộ nhớ phù hợp. Khi đó có thể phát sinh đọc/ghi tạm, tăng chi phí.

Không suy ra “Hash Join luôn tốn nhiều RAM và cần tránh”: với tập join lớn, nó có thể là phương án hiệu quả nhất.

### 13.4. `Hash Cond` khác `Join Filter`

```text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  Join Filter: (o.amount > 500)
```

`Hash Cond` dùng khóa để ghép qua hash. `Join Filter` là điều kiện thêm khi xem xét cặp dòng join. Tùy kiểu join, cách dời điều kiện từ `ON` sang `WHERE` có thể thay đổi ngữ nghĩa (đặc biệt với `LEFT JOIN`), không chỉ là tối ưu.

## 14. Nhận biết `Merge Join`

`Merge Join` ghép các nguồn **đã được sắp theo khóa join**. Nó di chuyển qua hai dãy khóa theo thứ tự để tìm nhóm bằng nhau.

```text
Merge Join on customer_id
  ├─ Nguồn trái đã sắp theo customer_id
  └─ Nguồn phải đã sắp theo customer_id
```

Một kế hoạch minh họa:

```text
Merge Join
  Merge Cond: (o.customer_id = c.customer_id)
  ├─ Index Scan using idx_plan_orders_customer_date on orders o
  └─ Index Scan using customers_pkey on customers c
```

Hoặc nếu đầu vào chưa đúng thứ tự:

```text
Merge Join
  Merge Cond: (o.customer_id = c.customer_id)
  ├─ Sort
  │    Sort Key: o.customer_id
  │    └─ Seq Scan on orders o
  └─ Sort
       Sort Key: c.customer_id
       └─ Seq Scan on customers c
```

### 14.1. Khi nào Merge Join hữu ích?

- Hai tập lớn và có thể đọc theo khóa join đã sắp.
- Có index phù hợp cung cấp thứ tự, hoặc sort đầu vào vẫn rẻ so với phương án khác.
- Kế hoạch phía trên cũng cần thứ tự tương ứng.

Không nên kết luận `Merge Join` luôn nhanh hơn `Hash Join`; nếu phải sort nhiều dữ liệu trên đĩa, chi phí có thể cao.

### 14.2. `Merge Cond`

```text
Merge Cond: (o.customer_id = c.customer_id)
```

cho biết khóa để hai luồng được so khớp. Cần phân biệt với `Join Filter` bổ sung hoặc `Filter` đặt trong các node con.

### 14.3. Một cách quan sát phương án Merge Join

Trong phiên **thực hành**, có thể tạm giảm tính hấp dẫn của các kiểu join khác để xem một phương án:

```sql
BEGIN;

SET LOCAL enable_hashjoin = off;
SET LOCAL enable_nestloop = off;

EXPLAIN
SELECT o.order_id, c.region
FROM plan_lab_orders AS o
JOIN plan_lab_customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.customer_id;

ROLLBACK;
```

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Việc tắt các kiểu join ở mức planner là **kỹ thuật quan sát**, không phải khuyến nghị vận hành production. PostgreSQL có thể vẫn cần kiểu join bị “tắt” ở một số trường hợp không có phương án hợp lệ khác; các cờ này chủ yếu làm tăng chi phí lựa chọn, không phải lệnh cấm tuyệt đối trong mọi tình huống.

**Kế hoạch được ép để học không đại diện cho lựa chọn tối ưu tự nhiên của database.**

## 15. So sánh ba kiểu JOIN

| Đặc điểm | `Nested Loop` | `Hash Join` | `Merge Join` |
|---|---|---|---|
| Ý tưởng | Với mỗi dòng outer, tìm dòng inner khớp | Xây hash một phía, tra từ phía còn lại | Duyệt hai nguồn theo thứ tự khóa |
| Thường mạnh khi | Outer nhỏ, inner có index phù hợp | Join bằng của tập tương đối lớn | Có dữ liệu đã sắp hoặc sort có lợi |
| Tín hiệu trên plan | `Nested Loop` + `loops` inner | `Hash Join`, `Hash`, `Hash Cond` | `Merge Join`, `Merge Cond`, input sorted |
| Rủi ro thường gặp | Inner chạy lặp quá nhiều | Hash build lớn, nhiều batches/temp I/O | Sort lớn hoặc thứ tự index không phù hợp |
| Có nhất thiết dùng index? | Không, nhưng index inner thường rất hữu ích | Không | Không; index có thể tránh sort |
| Có nhất thiết sort? | Không | Không | Các đầu vào phải cung cấp thứ tự, từ index hoặc sort |

### 15.1. Không chọn JOIN chỉ theo số dòng của bảng

Một bảng khách có 10.000 dòng, bảng đơn có 120.000 dòng. Nhưng nếu `WHERE c.customer_id=77`, số khách đầu vào chỉ còn **một dòng**; nested loop có index có thể tốt.

Nếu muốn thống kê **mọi đơn theo vùng**, toàn bộ khách/đơn phải được xử lý, hash join có thể tốt hơn.

**Hình dạng dữ liệu sau `WHERE`** mới là điều quan trọng, không chỉ kích thước bảng gốc.

### 15.2. Điều kiện JOIN có thể làm nổ số dòng

```sql
SELECT o.order_id, c.region
FROM plan_lab_orders AS o
JOIN plan_lab_customers AS c
    ON c.region = 'North';
```

Đây không phải join theo `customer_id`. Mỗi đơn có thể ghép với **mọi khách thuộc North**, gây tăng số dòng cực lớn. Kế hoạch có thể có nested loop, materialize hoặc các node khác; vấn đề chính là **logic join bị sai**, không phải riêng thuật toán join.

Khi `actual rows` sau join lớn bất thường, kiểm tra **độ hạt và khóa nối** trước khi thêm index.

## 16. `Sort`: tạo thứ tự khi đầu vào chưa có sẵn

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM plan_lab_orders
ORDER BY amount DESC
LIMIT 20;
```

Trong bộ dữ liệu ban đầu **không có index sắp theo `amount`**. Một plan khả dĩ:

```text
Limit
  └─ Sort
       Sort Key: amount DESC
       Sort Method: top-N heapsort  Memory: ...
       └─ Seq Scan on plan_lab_orders
```

### 16.1. `Sort Key`

```text
Sort Key: amount DESC
```

cho biết cột/biểu thức và chiều sắp xếp mà node cần tạo.

Trong một plan có nhiều `Sort`, không phải tất cả đều phục vụ `ORDER BY` cuối cùng. Sort có thể phục vụ:

- `Merge Join`.
- `GroupAggregate`.
- `Unique`/`DISTINCT`.
- Một số `WindowAgg`.
- `ORDER BY` và `LIMIT` của truy vấn cuối.

Hãy xem **node cha** để biết vì sao có bước sắp xếp.

### 16.2. `Sort Method`

Một số cách được PostgreSQL báo:

| Sort method | Gợi ý đọc |
|---|---|
| `quicksort` | Sắp xếp trong bộ nhớ bằng thuật toán phù hợp |
| `top-N heapsort` | Giữ ứng viên tốt nhất cho yêu cầu lấy N dòng; thường thấy với `ORDER BY ... LIMIT` |
| `external merge` | Sắp xếp cần dùng **dữ liệu tạm trên đĩa** vì không đáp ứng trong giới hạn bộ nhớ phù hợp |

Đừng đọc `top-N heapsort` là “chỉ đọc N dòng nguồn”. Nó có thể phải **xem rất nhiều dòng** để biết N dòng lớn nhất.

### 16.3. `Memory` và `Disk`

```text
Sort Method: quicksort  Memory: 1200kB
```

cho biết mức bộ nhớ được báo cho sort. Nếu:

```text
Sort Method: external merge  Disk: 24576kB
```

thì có dùng tệp tạm trên đĩa cho sort. Đây là tín hiệu xem xét `work_mem`, lượng dữ liệu đưa vào sort, chỉ mục và điều kiện lọc.

**Không tăng `work_mem` vô hạn**: nhiều sort/hash có thể chạy đồng thời, mỗi query có nhiều node và nhiều connection/worker. Bộ nhớ tổng có thể tăng rất mạnh.

## 17. `ORDER BY` có thể được thỏa trực tiếp từ index

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE customer_id = 77
ORDER BY ordered_at DESC
LIMIT 5;
```

Với index `(customer_id, ordered_at DESC)`, PostgreSQL có thể đi theo các mục index đúng thứ tự:

```text
Limit
  └─ Index Scan using idx_plan_orders_customer_date
       Index Cond: (customer_id = 77)
```

Trong trường hợp này, **không cần `Sort`** vì đường đọc dữ liệu đã cung cấp thứ tự cần thiết.

### 17.1. `ORDER BY` nhiều cột

Một index B-tree `(customer_id, ordered_at DESC)` có thứ tự:

```text
customer_id tăng dần
  └── ordered_at giảm dần trong từng customer
```

Do đó, hai truy vấn này có khả năng tận dụng thứ tự khác nhau:

```sql
WHERE customer_id = 77
ORDER BY ordered_at DESC
```

```sql
ORDER BY customer_id, ordered_at DESC
```

Ngược lại:

```sql
ORDER BY amount DESC, customer_id
```

không có cùng thứ tự với index trên khách/ngày; có thể cần sort.

### 17.2. Thứ tự không được bảo đảm khi không có `ORDER BY`

Nếu plan tình cờ dùng index và dữ liệu xuất ra “trông đã sắp”, câu:

```sql
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE customer_id = 77;
```

**không có hợp đồng thứ tự kết quả**. Một lần planner chuyển sang bitmap/seq scan hoặc dữ liệu thay đổi, thứ tự có thể khác.

Muốn kết quả theo ngày mới nhất thì phải viết **`ORDER BY ordered_at DESC`**; nếu cần thứ tự xác định tuyệt đối khi ngày giờ trùng, thêm khóa phân xử như `order_id DESC`.

## 18. `Incremental Sort`

Một số kế hoạch đầu vào đã **sắp theo tiền tố** của khóa cần thiết. PostgreSQL có thể tận dụng thứ tự đó và chỉ sắp lại trong từng nhóm tiền tố.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, amount, order_id
FROM plan_lab_orders
ORDER BY customer_id, amount DESC, order_id
LIMIT 100;
```

Index `(customer_id, ordered_at DESC)` cung cấp **thứ tự theo `customer_id`** nhưng không theo `amount DESC`. Trong một kế hoạch thích hợp, PostgreSQL có thể chọn:

```text
Incremental Sort
  Sort Key: customer_id, amount DESC, order_id
  Presorted Key: customer_id
  └─ Index Scan using idx_plan_orders_customer_date
```

Thay vì sắp toàn bộ 120.000 dòng như một khối, incremental sort có thể xử lý các nhóm theo `customer_id`.

### 18.1. Cần đọc `Presorted Key`

`Presorted Key: customer_id` cho biết phần thứ tự **đã có sẵn từ node con**. `Sort Key` vẫn là toàn bộ thứ tự cần xuất.

Phương án có lợi nếu các nhóm đủ nhỏ và thứ tự đầu vào thực sự hữu dụng. Nó không phải lúc nào cũng tốt hơn `Sort` thường; planner sẽ cân nhắc chi phí ước lượng.

### 18.2. Vì sao có `LIMIT` vẫn có thể chậm?

Nếu planner dự đoán có thể lấy nhanh 100 dòng theo thứ tự nhưng thực tế phải đọc/sắp rất nhiều nhóm, lợi ích giảm. Khi gặp latency bất thường, xem:

- Số dòng đi qua node con.
- Ước lượng số nhóm và kích thước nhóm.
- `Full-sort Groups` / `Pre-sorted Groups` khi plan phiên bản hỗ trợ báo.
- Có index nào phù hợp **toàn bộ khóa ORDER BY** hơn không?

Không bỏ incremental sort chỉ vì “Sort là xấu”; phải đo dữ liệu thực.

## 19. `LIMIT`: node nào thật sự tiết kiệm công việc?

Hai truy vấn cùng `LIMIT 10` nhưng đặc tính khác nhau:

**A. Tra top 10 đơn mới nhất của một khách từ index**

```sql
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE customer_id = 77
ORDER BY ordered_at DESC
LIMIT 10;
```

Planner có thể đọc một phần index và **dừng sau đủ 10 dòng**, nếu không có node buộc tiêu thụ toàn bộ nguồn.

**B. Tra 10 đơn có amount lớn nhất mà chưa có index amount**

```sql
SELECT order_id, amount
FROM plan_lab_orders
ORDER BY amount DESC
LIMIT 10;
```

Nếu dùng seq scan + top-N heapsort, vẫn phải **đọc toàn bộ tập ứng viên** để xác định 10 giá trị lớn nhất.

### 19.1. Bài học

`LIMIT` chỉ giới hạn **số dòng trả**, không mặc nhiên giới hạn **số dòng phải đọc**.

### 19.2. Offset lớn cũng có chi phí

```sql
SELECT order_id, ordered_at
FROM plan_lab_orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Để bỏ qua 100.000 dòng đầu, engine thường vẫn cần tìm/đi qua các dòng trước đó. Với phân trang sâu, cân nhắc **keyset pagination** dùng khóa sắp xếp ổn định:

```sql
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE ordered_at < :last_seen_time
   OR (ordered_at = :last_seen_time AND order_id < :last_seen_id)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Ví dụ trên giả định có bind parameters và **thứ tự giảm dần** theo `(ordered_at, order_id)`; để khai thác tối ưu, chỉ mục nên phù hợp với cả hai khóa và cách viết predicate có thể được tối ưu thêm bằng row comparison tùy điều kiện.

## 20. `Gather` và `Gather Merge`: đọc kế hoạch song song

PostgreSQL có thể chạy song song một phần kế hoạch:

```text
Gather
  Workers Planned: 2
  Workers Launched: 2
  └─ Parallel Seq Scan on large_table
```

`Gather` nhận dòng từ các worker và leader. **Thứ tự dòng không được bảo đảm chỉ vì mỗi worker xử lý một phần dữ liệu**.

Nếu kế hoạch cần thu thập kết quả **đã sắp đúng khóa** từ nhiều worker:

```text
Gather Merge
  └─ Sort
       └─ Parallel Seq Scan
```

`Gather Merge` ghép nhiều luồng **đã được sắp** để giữ thứ tự. Đây là khác biệt khi đọc kế hoạch có `ORDER BY` và parallelism.

### 20.1. Thống kê worker

`EXPLAIN ANALYZE` có thể hiển thị số worker dự kiến/thực chạy và thống kê theo worker. Nếu `Workers Planned=4` nhưng thực chạy ít hơn, môi trường có thể bị giới hạn tài nguyên và kế hoạch thực thi có hành vi khác dự toán.

### 20.2. Parallel không cứu một join logic sai

Nếu join tạo tích Descartes ngoài ý muốn hoặc thiếu điều kiện khóa, dùng nhiều worker chỉ giúp xử lý một lượng dữ liệu **sai** nhanh hơn hoặc tiêu thụ tài nguyên nhiều hơn. Hãy xác nhận số dòng logic trước tối ưu song song.

## 21. `HashAggregate`, `GroupAggregate`, `WindowAgg` trong bối cảnh sắp xếp

Bài tập trung vào scan, JOIN và sort, nhưng cần nhận ra những node **ở giữa** vì chúng tạo yêu cầu thứ tự/bộ nhớ.

### 21.1. HashAggregate

```sql
EXPLAIN
SELECT customer_id, SUM(amount)
FROM plan_lab_orders
GROUP BY customer_id;
```

Một phương án có thể là:

```text
HashAggregate
  Group Key: customer_id
  └─ Seq Scan on plan_lab_orders
```

Aggregate hash dùng cấu trúc băm để gom nhóm, thường **không bảo đảm kết quả được sắp theo `customer_id`**.

### 21.2. GroupAggregate

Một phương án khác:

```text
GroupAggregate
  Group Key: customer_id
  └─ Sort
       Sort Key: customer_id
       └─ Seq Scan on plan_lab_orders
```

hoặc đọc đầu vào đã có thứ tự từ index. `GroupAggregate` sử dụng luồng dữ liệu được sắp phù hợp để tính nhóm. Việc thấy `Sort` phía dưới `GroupAggregate` không phải nhất thiết do câu SQL có `ORDER BY` ở ngoài.

### 21.3. WindowAgg

```sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY amount DESC, order_id
    ) AS rn
FROM plan_lab_orders;
```

`WindowAgg` có thể cần đầu vào được sắp theo khóa phân vùng và thứ tự cửa sổ; do đó nó thường xuất hiện cùng `Sort`/`Incremental Sort` hoặc index scan có thứ tự phù hợp.

**Mẹo đọc:** Khi gặp `Sort`, nhìn **node cha** và **Sort Key** trước khi kết luận “chậm vì ORDER BY cuối”.

## 22. `Memoize`, `Materialize` và node hỗ trợ JOIN

Trong kế hoạch thực tế, bạn có thể gặp các node nằm giữa `Nested Loop` và nguồn dữ liệu.

### 22.1. Memoize

`Memoize` có thể lưu lại kết quả tra cứu theo **khóa tham số hóa**, hữu ích khi nhiều dòng outer có cùng khóa và nested loop phải tra cùng tập inner nhiều lần.

```text
Nested Loop
  ├─ Seq Scan on orders o
  └─ Memoize
       Cache Key: o.customer_id
       └─ Index Scan on customers c
            Index Cond: (customer_id = o.customer_id)
```

Trong EXPLAIN ANALYZE có thể thấy `Hits`, `Misses`, `Evictions`, `Overflows`, `Memory Usage` theo cơ chế được hỗ trợ. `Memoize` có thể làm nested loop hiệu quả dù outer nhiều dòng **nếu nhiều khóa lặp**.

Đừng đồng nhất “nested loop có 120.000 loops” với “120.000 lần đọc vật lý bảng khách” nếu có cache và nhiều hit.

### 22.2. Materialize

`Materialize` có thể lưu tạm đầu ra của node con để dùng lại, đặc biệt khi bên trên cần quét lại. Đây là một **node thực thi**, không có nghĩa đối tượng nguồn là `MATERIALIZED VIEW`.

```text
Nested Loop
  ├─ ...
  └─ Materialize
       └─ Seq Scan on small_table
```

Vẫn cần xem rows, loops và bộ nhớ/đĩa nếu được báo; một node materialize nhỏ có thể hợp lý hơn đọc lại bảng nhiều lần.

## 23. `Buffers`: quan sát việc đọc dữ liệu

Với:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM plan_lab_orders
WHERE order_id = 123;
```

có thể thấy:

```text
Buffers: shared hit=5 read=1
```

hoặc trên **bảng tạm**:

```text
Buffers: local hit=... read=...
```

Đây là **các ví dụ hình thức**, không phải con số cố định.

### 23.1. Shared, local và temp

| Loại | Ý nghĩa tổng quát |
|---|---|
| `shared` | Buffer cho quan hệ dùng chung của database |
| `local` | Buffer của quan hệ tạm trong phiên, phù hợp bộ dữ liệu `TEMP` ở bài |
| `temp` | Block tạm của thao tác thực thi như sort/hash spill ra tệp tạm |

**Cẩn thận:** “local buffers” vì **bảng TEMP** không đồng nghĩa với “temp disk blocks” do **sort/hash spill**.

### 23.2. `hit`, `read`, `dirtied`, `written`

- `hit`: block tìm thấy trong vùng buffer phù hợp.
- `read`: block phải được đọc vào buffer từ lớp lưu trữ; không kết luận chắc chắn mỗi read là một lần truy cập đĩa vật lý vì còn cache hệ điều hành.
- `dirtied`: block bị đánh dấu thay đổi.
- `written`: block được ghi theo cơ chế báo cáo.

Số buffer của một node thường **bao gồm** hoạt động của các node con theo cách PostgreSQL báo, nên không cộng thẳng tất cả số buffer cha/con để suy ra tổng.

### 23.3. Cache có thể làm hai lần chạy khác nhau

Lần đầu truy vấn đọc nhiều block, lần sau dữ liệu có thể đã ở buffer hoặc cache hệ điều hành:

```text
Lần 1: read nhiều, thời gian cao hơn
Lần 2: hit nhiều, thời gian thấp hơn
```

Không kết luận ngay “thêm index làm nhanh 10 lần” nếu đang so lần chạy cold cache với warm cache mà không kiểm soát.

## 24. Hướng dẫn đọc kế hoạch theo sáu bước

Khi nhận một plan dài, có thể đọc theo thứ tự:

**Bước 1 — Xác nhận SQL và mục tiêu.** Truy vấn cần một ID hay 80% bảng? Có `ORDER BY`, `LIMIT`, `GROUP BY`, `JOIN` nào?

**Bước 2 — Tìm node lá đọc dữ liệu.** `Seq Scan`, `Index Scan`, `Index Only Scan`, `Bitmap Index Scan`/`Bitmap Heap Scan` xuất hiện ở đâu?

**Bước 3 — Xem các điều kiện.** `Index Cond`, `Filter`, `Hash Cond`, `Merge Cond`, `Join Filter` có tương ứng với các khóa/điều kiện SQL không?

**Bước 4 — Theo luồng rows.** Ước lượng và thực tế giảm/tăng ở node nào? Join có nhân số dòng, aggregate có thu gọn như mong muốn?

**Bước 5 — Nhận biết sort/hash và bộ nhớ.** Có `Sort`, `Incremental Sort`, `Hash`, `HashAggregate`, temp disk, nhiều batches không?

**Bước 6 — Xem thời gian, loops, buffers.** Node nào làm nhiều việc? Nguyên nhân là dữ liệu, chỉ mục, câu SQL, thống kê hay contention?

Ví dụ sơ đồ:

```text
Sort  [Sort Key: total DESC]
  └─ HashAggregate [rows: 4 groups]
       └─ Hash Join [rows: 120000 orders]
            ├─ Seq Scan orders [120000 input]
            └─ Hash
                 └─ Seq Scan customers [10000 input]

Đọc theo hướng:
customers/orders → Hash Join → HashAggregate → Sort → output
```

Các số chỉ minh họa quy mô; không phải output bắt buộc của một lần chạy.

## 25. Trường hợp thực hành 1: tìm một đơn hàng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, status, amount
FROM plan_lab_orders
WHERE order_id = 34567;
```

### 25.1. Điều mong đợi khi đọc

- `WHERE order_id=34567` tìm **một khóa chính**.
- Chỉ mục `plan_lab_orders_pkey` phù hợp.
- Kế hoạch thường chọn `Index Scan` nếu chi phí hợp lý.
- Nếu bảng nhỏ bất thường hoặc các điều kiện môi trường khác, vẫn có thể xuất một phương án khác.

**Không cần thêm index mới chỉ vì chưa thấy node như kỳ vọng**. Đầu tiên kiểm tra thống kê, cấu hình, chỉ mục hiện có và dữ liệu.

### 25.2. Khi `actual rows=0`

Query vẫn có thể dùng index hiệu quả dù không tìm thấy ID. `actual rows=0` không có nghĩa planner chọn sai; nó có thể đơn giản là **khóa không tồn tại**.

## 26. Trường hợp thực hành 2: lọc theo khoảng ngày

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at, amount
FROM plan_lab_orders
WHERE ordered_at >= TIMESTAMP '2026-12-25'
  AND ordered_at <  TIMESTAMP '2027-01-01';
```

### 26.1. Những phương án có thể xuất hiện

- `Index Scan` trên `idx_plan_orders_date`.
- `Bitmap Index Scan` + `Bitmap Heap Scan`.
- `Seq Scan` nếu planner dự đoán phần dữ liệu phù hợp lớn hoặc chi phí index không hấp dẫn.

Không có một quy tắc “lọc theo ngày luôn dùng index”.

### 26.2. Tại sao cần khoảng nửa mở?

Điều kiện:

```sql
ordered_at >= TIMESTAMP '2026-12-25'
AND ordered_at < TIMESTAMP '2027-01-01'
```

bao phủ đầy đủ các thời điểm từ đầu 25/12 đến hết 31/12 với mọi phần giây; phù hợp cho truy vấn theo khoảng ngày.

## 27. Trường hợp thực hành 3: JOIN một khách và JOIN toàn bộ

**Truy vấn chỉ một khách:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id, c.region, o.order_id, o.amount
FROM plan_lab_customers AS c
JOIN plan_lab_orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 77;
```

**Truy vấn trên mọi khách:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.region, COUNT(*) AS order_count
FROM plan_lab_customers AS c
JOIN plan_lab_orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.region;
```

### 27.1. Điều cần giải thích

Truy vấn đầu chỉ cần một khách và các đơn của khách đó. Index lookup kết hợp nested loop có thể hiệu quả.

Truy vấn sau đọc rất nhiều đơn và khách; hash join và một dạng aggregate có thể là lựa chọn phù hợp.

Đây là bài học rằng **cùng quan hệ JOIN nhưng khác predicate nên kế hoạch có thể khác**.

### 27.2. Nếu plan không đúng theo “dự đoán” của bạn?

Hãy đọc `actual rows`, `loops` và buffers. Mục tiêu không phải buộc PostgreSQL chọn một node cụ thể, mà là biết vì sao phương án đang có hiệu quả hoặc không hiệu quả với dữ liệu hiện tại.

## 28. Trường hợp thực hành 4: top-N theo index và top-N cần sort

**A. Top-N theo ngày của một khách:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM plan_lab_orders
WHERE customer_id = 77
ORDER BY ordered_at DESC
LIMIT 5;
```

**B. Top-N theo amount của mọi đơn:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM plan_lab_orders
ORDER BY amount DESC, order_id DESC
LIMIT 5;
```

### 28.1. Sự khác biệt dự kiến

Với A, index `(customer_id, ordered_at DESC)` có thể cung cấp thứ tự trực tiếp; có thể **không có Sort**.

Với B, không có index phù hợp trên `(amount DESC, order_id DESC)` trong dữ liệu ban đầu; planner có thể chọn **seq scan + top-N heapsort**.

**Lưu ý:** B có khóa phân xử `order_id DESC` nên khi nhiều đơn có cùng `amount`, thứ tự top-N là xác định; A nếu có nhiều đơn cùng `ordered_at`, kết quả top 5 giữa những dòng đồng hạng có thể thay đổi. Khi cần ổn định, thêm `order_id DESC` và cân nhắc index phù hợp.

## 29. Trường hợp thực hành 5: thay đổi chỉ mục để so kế hoạch

Trên **bộ dữ liệu tạm của bài**, có thể thử thêm một chỉ mục:

```sql
CREATE INDEX idx_plan_orders_amount_order
    ON plan_lab_orders (amount DESC, order_id DESC);

ANALYZE plan_lab_orders;
```

Sau đó chạy lại:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM plan_lab_orders
ORDER BY amount DESC, order_id DESC
LIMIT 5;
```

Planner giờ có thể đi theo thứ tự index, tránh sort trên toàn bộ tập ứng viên.

### 29.1. Vì sao không thêm index cho mọi `ORDER BY`?

Chỉ mục có chi phí:

- Chiếm dung lượng.
- Tăng công cho `INSERT`, `UPDATE`, `DELETE`.
- Tăng thời gian bảo trì, vacuum và một số hoạt động tạo/xây lại index.
- Có thể không hữu ích khi filter quá rộng hoặc query trả nhiều cột không nằm trong index.

Một chỉ mục thường được biện minh bằng **khối lượng truy vấn thực tế** và chi phí end-to-end, không chỉ vì nó thay `Sort` thành `Index Scan` trong một ví dụ.

### 29.2. Tránh so hai query ở hai môi trường khác nhau

Khi so plan trước/sau index, kiểm tra:

- Cùng câu SQL và tham số.
- Cùng số lượng/phân phối dữ liệu.
- Thống kê đã được cập nhật phù hợp.
- Tải hệ thống và cache không khác quá nhiều.
- Plan được quan sát trên đúng phiên/schema.

Không cần cố đo ra một tỷ lệ nhanh lên cố định; nhiệm vụ là **đọc được thay đổi cấu trúc kế hoạch và nguyên nhân**.

## 30. Khi kế hoạch ước lượng sai: thống kê và tương quan

Planner không biết hết mọi thứ về dữ liệu. Nó dựa vào các thống kê như phân phối giá trị, số giá trị riêng biệt và ước lượng selectivity.

### 30.1. Dấu hiệu thống kê cũ

Ví dụ ứng dụng vừa nạp thêm hàng triệu đơn `PAID`, nhưng chưa cập nhật thống kê phù hợp. Planner có thể vẫn nghĩ tỷ lệ `PAID` hoặc tổng số dòng là giá trị cũ và chọn chiến lược không tốt.

```sql
ANALYZE plan_lab_orders;
```

giúp làm mới thống kê cho bảng tạm trong bài. Trong production, autovacuum/analyze thường tự quản lý phần lớn công việc trên bảng thường, nhưng tải ETL lớn hoặc điều kiện đặc biệt có thể cần quan sát và cấu hình.

### 30.2. Các cột tương quan

Ví dụ trong hệ thật:

```text
status = 'PAID'
region = 'North'
```

không nhất thiết độc lập. Nếu 95% đơn của North là PAID nhưng chỉ 50% của South là PAID, một mô hình ước lượng độc lập có thể dự đoán sai số dòng sau `WHERE`.

PostgreSQL hỗ trợ **extended statistics** cho các thuộc tính trên cùng một bảng trong những trường hợp phù hợp. Ví dụ với bảng có `status` và `customer_id`:

```sql
CREATE STATISTICS st_plan_orders_status_customer
    (dependencies, ndistinct, mcv)
ON status, customer_id
FROM plan_lab_orders;

ANALYZE plan_lab_orders;
```

Đây là ví dụ cơ chế thống kê bổ sung; không tự đảm bảo planner dùng mọi loại thống kê cho mọi điều kiện và đặc biệt **không giải quyết trọn vẹn tương quan giữa các bảng độc lập**.

### 30.3. Cơ chế ước lượng còn phụ thuộc tham số

Với prepared statements, planner có thể dùng **custom plan** dựa trên tham số cụ thể hoặc **generic plan** tái sử dụng. Nếu cột phân phối lệch mạnh, cùng câu SQL nhưng giá trị tham số khác nhau có thể cần chiến lược khác nhau.

Đừng coi một `EXPLAIN` trên giá trị ID dễ chọn là đại diện chắc chắn cho mọi tham số trong ứng dụng.

## 31. Khi JOIN trả quá nhiều dòng: kiểm tra cardinality trước

Một câu join hợp lệ cú pháp có thể gây bùng nổ dữ liệu:

```sql
SELECT COUNT(*)
FROM plan_lab_orders AS o
JOIN plan_lab_customers AS c
    ON o.customer_id = c.customer_id;
```

Với dữ liệu mẫu và FK hợp lệ, mỗi đơn có một khách, nên kết quả là **120.000 dòng**.

Nhưng nếu join bằng `region` sau khi đã có region ở cả hai phía, một đơn có thể ghép với hàng nghìn khách trong vùng. Đó là một logic khác.

### 31.1. Dấu hiệu ở plan

```text
Hash Join ... actual rows=30000000
  ├─ Seq Scan ... rows=120000
  └─ ...
```

Nếu truy vấn mong đợi một dòng mỗi đơn mà actual rows sau join thành hàng chục triệu, vấn đề trước tiên có thể là **khóa nối hoặc độ hạt**.

### 31.2. Không dùng `DISTINCT` để che mọi lỗi JOIN

```sql
SELECT DISTINCT o.order_id, ...
```

có thể giảm dòng bị nhân, nhưng:

- Có thể tốn thêm `HashAggregate` hoặc `Sort`/`Unique`.
- Không sửa tính đúng của `SUM(amount)` nếu tổng đã bị nhân ở tầng trước.
- Có thể loại những dòng hợp lệ trùng giá trị các cột được chọn.

Hãy sửa **quan hệ khóa và độ hạt** trước khi dùng `DISTINCT` như một thao tác nghiệp vụ có chủ đích.

## 32. Semi Join, Anti Join và `EXISTS`

Khi cần biết **có hay không có bản ghi liên quan**, `EXISTS` thường diễn đạt đúng ý định hơn join rồi `DISTINCT`.

```sql
EXPLAIN
SELECT c.customer_id
FROM plan_lab_customers AS c
WHERE EXISTS (
    SELECT 1
    FROM plan_lab_orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

Planner có thể thể hiện bằng:

```text
Hash Semi Join
```

hoặc:

```text
Nested Loop Semi Join
```

Tùy dữ liệu, hệ thống có thể chọn biến thể thích hợp.

### 32.1. Semi Join

Một khách chỉ cần **có ít nhất một đơn PAID** là đủ điều kiện; không cần trả một dòng cho từng đơn. Điều này tránh nhân khách hàng thành nhiều bản ghi.

### 32.2. Anti Join

```sql
EXPLAIN
SELECT c.customer_id
FROM plan_lab_customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM plan_lab_orders AS o
    WHERE o.customer_id = c.customer_id
);
```

Planner có thể chọn `Hash Anti Join`, `Nested Loop Anti Join`... để tìm những khách **không có đơn**.

Không đánh đồng `NOT EXISTS` với `NOT IN` trong mọi tình huống, vì `NULL` trong tập phía phải có thể làm `NOT IN` cho kết quả khác theo logic ba giá trị SQL.

## 33. Đừng nhầm dấu hiệu hiệu năng với lỗi ngữ nghĩa

Một số nhận định phổ biến:

| Nhận định | Điều cần hiểu đúng |
|---|---|
| “Có Seq Scan là thiếu index” | Seq scan có thể tối ưu khi lấy phần lớn bảng hoặc bảng nhỏ |
| “Có index thì mọi query trên cột đó sẽ dùng” | Planner chọn theo chi phí; thứ tự cột, độ chọn lọc và cột đầu ra đều quan trọng |
| “Index Only Scan không bao giờ đọc heap” | PostgreSQL vẫn có thể `Heap Fetches` để kiểm tra visibility |
| “Bitmap Scan chính là Seq Scan” | Bitmap dùng index chọn vị trí rồi đọc các trang heap liên quan |
| “Nested Loop luôn chậm” | Rất tốt khi outer nhỏ và inner lookup nhanh; cần xem loops |
| “Hash Join không dùng index nên sai” | Có thể là phương án tối ưu cho join bằng trên tập lớn |
| “Merge Join luôn cần hai Sort node” | Thứ tự có thể đến từ index hoặc node con khác |
| “Có Sort nghĩa là query viết ORDER BY cuối” | Sort có thể phục vụ merge join/group/window/distinct |
| “LIMIT 10 chỉ đọc 10 dòng” | Top-N thường vẫn phải xem nhiều dòng nguồn |
| “Cost là mili-giây” | Là đơn vị mô hình chi phí planner, không phải wall time |
| “Actual rows là tổng mọi loops” | Với node chạy nhiều loops, cần đọc cách EXPLAIN báo trung bình mỗi lượt |
| “Buffers read là số lần đọc đĩa vật lý chắc chắn” | Có thể được phục vụ bởi OS cache; không tương đương trực tiếp I/O vật lý |
| “Sort Method external merge nghĩa là lỗi SQL” | Truy vấn vẫn hợp lệ, nhưng có dùng tệp tạm do sắp xếp |
| “`EXPLAIN ANALYZE UPDATE` chỉ xem trước” | Nó thực thi lệnh ghi thật |
| “Một plan tốt hôm nay luôn tốt” | Phân phối dữ liệu, thống kê và tham số có thể thay đổi |
| “Không thấy node View thì view không được thực hiện” | Planner có thể mở rộng định nghĩa view vào plan |
| “Join trả số dòng lớn là do optimizer kém” | Trước tiên kiểm tra khóa nối và logic nghiệp vụ |

## 34. Quy trình điều tra một truy vấn chậm

Khi có một câu SQL báo cáo từ 200 ms tăng lên 12 giây, dùng quy trình:

### Bước 1 — Định nghĩa tình huống

Ghi:

- Câu SQL và tham số thực tế (đã xử lý dữ liệu nhạy cảm).
- Số dòng dự kiến trả.
- Môi trường, phiên bản DBMS, cấu hình liên quan.
- Thời điểm, tải hệ thống, kích thước dữ liệu.

### Bước 2 — Lấy kế hoạch

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT ...
FROM ...
WHERE ...;
```

Chỉ dùng `ANALYZE` khi việc thực thi thật là chấp nhận được; với DML, áp các biện pháp an toàn thích hợp.

### Bước 3 — Tìm nơi tăng dữ liệu

Đi từ node lá:

```text
Scan → Filter → Join → Aggregate → Sort → Limit
```

Ở node nào `actual rows` cao bất thường? JOIN có bùng nổ số dòng? Filter áp muộn và loại nhiều dữ liệu không?

### Bước 4 — So ước lượng với thực tế

`estimated rows` so với `actual rows` có lệch rất xa không? Nếu lệch, cần xem thống kê, tương quan cột, predicate phức tạp và generic/custom plan.

### Bước 5 — Xem access path

- Một điểm lookup theo PK lại quét toàn bảng?
- Một điều kiện khoảng đang áp hàm lên cột nên không dùng index trực tiếp?
- Index scan phải đọc quá nhiều heap pages?
- Index có thứ tự giúp tránh sort không?

### Bước 6 — Xem JOIN

- Nested loop inner có `loops` rất lớn?
- Hash join có `Batches` nhiều và dùng temp disk?
- Merge join phải sort input lớn?
- Join filter có loại rất nhiều cặp?

### Bước 7 — Xem SORT/Memory/IO

- `Sort Method: external merge`?
- `Disk`/`temp read/write` lớn?
- Có `Sort` cho `ORDER BY` hay phục vụ phép toán khác?
- Có thể lọc sớm hơn hoặc dùng chỉ mục phù hợp thứ tự không?

### Bước 8 — Chọn một thay đổi có lý do

Ví dụ:

- Thêm/chỉnh index **phù hợp truy vấn quan trọng**.
- Viết lại `WHERE` khoảng thời gian.
- Sửa join sai khóa.
- Tổng hợp trước khi join một–nhiều.
- Cập nhật thống kê.
- Giảm cột trả, giảm số dòng trước sort.
- Điều chỉnh cấu hình có đánh giá tổng tài nguyên.

### Bước 9 — So lại trên cùng dữ liệu và ghi kết luận

Không chỉ đo một lần. So cấu trúc plan và các chỉ số thực tế trong điều kiện tương đối tương đương, đồng thời bảo đảm **kết quả SQL vẫn đúng nghiệp vụ**.

## 35. Bài tập thực hành

Các bài dưới đây sử dụng bảng `plan_lab_customers`, `plan_lab_orders` và các index ở mục 3. Mục tiêu là **nhận biết và giải thích**, không bắt PostgreSQL phải sinh đúng một node duy nhất. Khi đề có **đoạn plan giả định**, hãy phân tích đúng đoạn đó. Khi chạy SQL thực tế, kế hoạch có thể khác vì thống kê và môi trường.

### Bài 1 — Đọc một cây đơn giản

Đọc plan:

```text
Aggregate
  └─ Seq Scan on orders
       Filter: (status = 'PAID')
```

Node nào đọc dữ liệu? Node nào tính tổng hợp? Có bắt buộc đây là kế hoạch xấu không?

### Bài 2 — Seq Scan hay Index Scan?

Hai truy vấn:

```sql
SELECT * FROM plan_lab_orders WHERE order_id = 123;
SELECT * FROM plan_lab_orders WHERE amount >= 100;
```

Với dữ liệu bài học, truy vấn nào thường thích hợp truy cập theo khóa chính, truy vấn nào thường phù hợp quét phần lớn bảng? Vì sao?

### Bài 3 — `Index Cond` và `Filter`

Giải thích:

```text
Index Scan using idx_plan_orders_customer_date
  Index Cond: (customer_id = 77)
  Filter: (amount > 800)
```

Điều kiện nào giúp định vị trong index, điều kiện nào được kiểm tra thêm?

### Bài 4 — Index Only và Heap Fetches

Kế hoạch hiển thị:

```text
Index Only Scan ...
  Heap Fetches: 250
```

Có mâu thuẫn không? Vì sao `Index Only Scan` vẫn cần heap trong PostgreSQL?

### Bài 5 — Bitmap

Nêu thứ tự hoạt động của:

```text
Bitmap Heap Scan
  Recheck Cond: (ordered_at >= ...)
  └─ Bitmap Index Scan
       Index Cond: (ordered_at >= ...)
```

Khác gì với một index scan lấy từng tuple?

### Bài 6 — Có index nhưng không dùng

PostgreSQL chọn `Seq Scan` cho `WHERE status='PAID'` dù có index `(status, ordered_at DESC)`. Dữ liệu mẫu có khoảng 70% đơn `PAID`. Giải thích vì sao lựa chọn đó có thể hợp lý.

### Bài 7 — Chỉ mục nhiều cột

Với index `(customer_id, ordered_at DESC)`, truy vấn nào dễ tận dụng index hơn?

```sql
WHERE customer_id = 77
ORDER BY ordered_at DESC
LIMIT 10
```

và:

```sql
WHERE ordered_at >= TIMESTAMP '2026-12-01'
ORDER BY ordered_at DESC
```

Vì sao thứ tự khóa index quan trọng?

### Bài 8 — Hàm trên cột thời gian

So:

```sql
WHERE EXTRACT(YEAR FROM ordered_at) = 2026
```

với:

```sql
WHERE ordered_at >= TIMESTAMP '2026-01-01'
  AND ordered_at < TIMESTAMP '2027-01-01'
```

Cách nào dễ tận dụng index B-tree thông thường trên `ordered_at` theo khoảng?

### Bài 9 — Nested Loop

Giả định:

```text
Nested Loop
  ├─ Index Scan on customers (rows=1)
  └─ Index Scan on orders (actual rows=12 loops=1)
```

Đây có thể là phương án tốt trong tình huống nào?

### Bài 10 — Nested Loop nhiều loops

Giả định:

```text
Nested Loop
  ├─ Seq Scan on outer_table (actual rows=100000 loops=1)
  └─ Seq Scan on inner_table (actual rows=1 loops=100000)
```

Nêu dấu hiệu rủi ro và cách điều tra.

### Bài 11 — Hash Join

Đọc:

```text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  ├─ Seq Scan on orders o
  └─ Hash
       └─ Seq Scan on customers c
```

Nguồn nào dùng để xây hash trong sơ đồ? Điều kiện nào là khóa băm?

### Bài 12 — Hash batches

Plan `Hash` báo `Batches: 16`, có temp I/O. Điều đó gợi ý gì? Có nên lập tức tăng `work_mem` của toàn server không?

### Bài 13 — Merge Join

Vì sao `Merge Join` cần đầu vào theo thứ tự khóa? Những nguồn thứ tự đó có thể là gì?

### Bài 14 — JOIN kiểu nào?

Một query chỉ đọc một customer qua PK rồi lấy đơn của họ. Query khác tổng hợp mọi đơn với mọi customer. Loại join nào thường phù hợp hơn cho từng trường hợp, và tại sao không thể kết luận chắc chắn chỉ từ mô tả?

### Bài 15 — Sort

Đọc:

```text
Sort
  Sort Key: amount DESC
  Sort Method: external merge  Disk: 20480kB
  └─ Seq Scan on orders
```

Sắp xếp đã dùng bộ nhớ hay tệp tạm trên đĩa? Có những hướng tối ưu nào?

### Bài 16 — Top-N

```text
Limit
  └─ Sort
       Sort Method: top-N heapsort
       └─ Seq Scan on orders
```

Vì sao `LIMIT 10` không chứng minh chỉ 10 dòng được đọc?

### Bài 17 — Sort từ index

Với index `(customer_id, ordered_at DESC)`, vì sao `ORDER BY ordered_at DESC LIMIT 5` cho một `customer_id` có thể không cần `Sort`?

### Bài 18 — Incremental Sort

Plan có:

```text
Incremental Sort
  Sort Key: customer_id, amount DESC
  Presorted Key: customer_id
```

Giải thích `Presorted Key` và sự khác biệt với sắp xếp toàn bộ.

### Bài 19 — Cost

Giả sử plan ghi `cost=0.42..8.44 rows=1 width=48`. Có được hiểu `8.44` là 8,44 ms không? Ý nghĩa `rows` và `width` là gì?

### Bài 20 — Actual rows và loops

Node báo:

```text
actual time=0.02..0.04 rows=2 loops=5000
```

Nên suy luận tổng số dòng xuất xấp xỉ bao nhiêu? Vì sao không thể nói node chỉ mất 0,04 ms tổng cộng?

### Bài 21 — Buffers

Giải thích khác nhau giữa `shared hit`, `shared read`, `local hit` và `temp read`. Bảng `TEMP` của bài thường tạo hoạt động buffer thuộc loại nào?

### Bài 22 — Row estimate lệch lớn

Planner ước lượng `rows=50`, thực tế `rows=500000`. Nêu ít nhất bốn nguyên nhân và các bước cần kiểm tra trước khi cố ép join algorithm.

### Bài 23 — Cardinality sau JOIN

Một truy vấn dự kiến trả mỗi đơn một dòng nhưng plan cho thấy số dòng sau join tăng 100 lần. Ngoài chỉ mục, cần kiểm tra gì trước?

### Bài 24 — `EXPLAIN ANALYZE` trên DML

Vì sao nguy hiểm khi chạy `EXPLAIN (ANALYZE)` cho `DELETE` trên production? Mô tả cách thử phù hợp trong môi trường được phép.

### Bài 25 — Semi Join

Bạn chỉ muốn danh sách customer **có ít nhất một đơn PAID**, không cần từng đơn. `EXISTS`/semi join có ưu điểm logic gì so với join rồi `DISTINCT`?

### Bài 26 — Parallel

Phân biệt `Gather` và `Gather Merge`. Khi kết quả cần giữ thứ tự, có nên suy luận một `Gather` thường sẽ tự bảo đảm thứ tự không?

### Bài 27 — Phân trang sâu

Vì sao `LIMIT 20 OFFSET 100000` có thể chậm dù trả 20 dòng? Nêu phương án phân trang bằng khóa ổn định.

### Bài 28 — Đọc plan tổng hợp

Giả sử:

```text
Sort
  Sort Key: (sum(o.amount)) DESC
  └─ HashAggregate
       Group Key: c.region
       └─ Hash Join
            Hash Cond: (o.customer_id = c.customer_id)
            ├─ Seq Scan on orders o
            │    Filter: (status = 'PAID')
            └─ Hash
                 └─ Seq Scan on customers c
```

Hãy mô tả luồng dữ liệu từ bảng nguồn lên kết quả và giải thích vì sao `Sort` ở gốc.

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** `Seq Scan` đọc bảng và lọc `PAID`; `Aggregate` tính kết quả tổng hợp từ các dòng đã lọc. Seq scan không tự xấu nếu cần phần lớn bảng hoặc bảng nhỏ.

**Bài 2:** `order_id=123` phù hợp truy cập PK, thường `Index Scan`. `amount>=100` chọn gần như toàn bộ dữ liệu mẫu, trong khi amount không có index ban đầu; seq scan hợp lý.

**Bài 3:** `customer_id=77` là `Index Cond`, giới hạn mục index cần tra. `amount>800` là `Filter`, kiểm tra thêm trên dòng lấy được.

**Bài 4:** Không mâu thuẫn. Index chứa đủ cột cần, nhưng PostgreSQL vẫn có thể ghé heap để kiểm tra visibility của tuple theo MVCC khi chưa thể dựa hoàn toàn vào visibility map.

**Bài 5:** `Bitmap Index Scan` tìm vị trí thỏa điều kiện, `Bitmap Heap Scan` đọc các trang heap tương ứng và recheck khi cần. Index scan thông thường thường đi theo index rồi lấy heap theo từng vị trí, có thể rải rác hơn.

**Bài 6:** `PAID` chiếm khoảng 70%, nghĩa là phải lấy quá nhiều dòng. Đọc tuần tự các trang heap có thể rẻ hơn tra chỉ mục và truy cập heap nhiều lần. Còn phụ thuộc số cột, thứ tự và cache.

**Bài 7:** Câu đầu có khóa đầu `customer_id` cố định và order theo khóa tiếp nên rất phù hợp. Câu sau chỉ lọc theo `ordered_at`, khi các ngày nằm dưới nhiều khách; index riêng `ordered_at` thường phù hợp hơn. Không khẳng định index nhiều cột tuyệt đối không thể dùng khi thiếu khóa đầu.

**Bài 8:** Khoảng nửa mở trên chính `ordered_at` thường dễ dùng index range scan hơn `EXTRACT(YEAR FROM ordered_at)=2026`. Planner vẫn có thể chọn seq scan nếu phạm vi quá rộng.

**Bài 9:** Khi chỉ cần một khách và khoảng vài đơn, tra PK customer và index order theo customer là rẻ; nested loop với inner lookup ít lần có thể rất tốt.

**Bài 10:** Inner `Seq Scan` chạy 100.000 lượt là dấu hiệu chi phí lặp khổng lồ. Kiểm tra khóa join, ước lượng outer, index inner, điều kiện lọc và khả năng hash/merge join; không chỉ ép plan.

**Bài 11:** `customers` được đọc để xây `Hash`; khóa băm là `customer_id`. `orders` là phía probe trong sơ đồ.

**Bài 12:** Hash table phải chia thành nhiều batches, có thể do giới hạn bộ nhớ và phát sinh temp I/O. Xem actual rows, width, work_mem/hash_mem_multiplier, tải đồng thời và khả năng lọc/giảm dữ liệu; không tự tăng toàn server mà chưa dự toán tài nguyên.

**Bài 13:** Merge join đi đồng thời qua hai luồng đã sắp theo khóa để so khớp. Thứ tự có thể đến từ index scan, sort hoặc node con vốn duy trì thứ tự phù hợp.

**Bài 14:** Một khách thường hợp nested loop + indexed lookup. Toàn bộ dữ liệu thường có thể hợp hash join hoặc merge join. Quyết định thực còn phụ thuộc thống kê, chỉ mục, chi phí, bộ nhớ, điều kiện và planner.

**Bài 15:** `external merge` và `Disk` cho thấy sort dùng tệp tạm trên đĩa. Có thể lọc sớm hơn, giảm width/dòng, dùng index phù hợp thứ tự, phân trang hoặc cân nhắc work_mem có kiểm soát.

**Bài 16:** Top-N heapsort giữ ứng viên tốt nhất trong quá trình quét, nhưng phải xem nhiều hoặc tất cả dòng đủ điều kiện để biết top 10 nếu không có đường đọc index theo đúng thứ tự.

**Bài 17:** Sau khi cố định `customer_id`, thứ tự index `ordered_at DESC` đã đúng với `ORDER BY`. PostgreSQL có thể đọc những mục đầu và dừng sau 5 dòng, tránh node sort riêng.

**Bài 18:** Đầu vào đã được sắp theo `customer_id`; incremental sort chỉ cần sắp phần khóa còn thiếu trong mỗi nhóm customer, thay vì sắp lại toàn bộ mọi dòng như một khối.

**Bài 19:** Không. `cost` là đơn vị nội bộ của planner. `rows=1` là ước lượng số dòng node xuất, `width=48` là độ rộng trung bình ước lượng mỗi dòng, tính theo byte.

**Bài 20:** Khoảng `2 * 5000 = 10000` dòng trên toàn bộ lượt, với lưu ý EXPLAIN báo trung bình/đã làm tròn. `0.04 ms` là thời gian bình quân hoàn tất **mỗi lượt**, phải xét 5000 loops và cấu trúc node cha/con.

**Bài 21:** `shared hit` là block quan hệ dùng chung đã có trong shared buffers; `shared read` là block đưa vào shared buffers; `local hit` là block của bảng tạm có trong local buffers; `temp read` là block từ tệp tạm thực thi, ví dụ sort spill. Bảng TEMP chủ yếu liên quan `local` buffers.

**Bài 22:** Thống kê cũ, phân phối lệch, tương quan giữa cột, predicate biểu thức khó ước lượng, giá trị tham số/generic plan, dữ liệu sau join phức tạp... Kiểm tra `ANALYZE`, thống kê/phân phối thực tế, điều kiện lọc, generic/custom plan, và thử nghiệm thay đổi có kiểm soát.

**Bài 23:** Kiểm tra khóa join có đúng không, quan hệ một–một/một–nhiều, dữ liệu nguồn có trùng khóa, điều kiện `ON` có thiếu, và liệu truy vấn đã thay đổi độ hạt. Sửa logic trước index hoặc `DISTINCT`.

**Bài 24:** `ANALYZE` thực thi `DELETE` thật. Chỉ thử trong môi trường được phép, với transaction và rollback thích hợp, đồng thời đánh giá trigger/side effect ngoài DB; không giả định rollback thu hồi email/API.

**Bài 25:** `EXISTS` diễn đạt “có ít nhất một dòng liên quan” và không nhân một khách theo số đơn. Semi join có thể dừng tìm khi đã có một match, tránh phải join nhiều dòng rồi lọc `DISTINCT` không cần thiết.

**Bài 26:** `Gather` gom dòng từ worker, không mặc nhiên bảo đảm thứ tự; `Gather Merge` trộn các luồng có thứ tự để giữ thứ tự khóa tương ứng.

**Bài 27:** Engine thường phải đi qua hoặc xác định nhiều dòng trước offset lớn. Keyset pagination dùng khóa sắp xác định như `(ordered_at DESC, order_id DESC)` và điều kiện “nhỏ hơn vị trí cuối cùng” cùng index tương ứng.

**Bài 28:** `Seq Scan orders` lọc `PAID`, `Seq Scan customers` cấp dữ liệu cho `Hash`, `Hash Join` ghép đơn với vùng, `HashAggregate` tính SUM theo vùng, `Sort` sắp các nhóm theo tổng giảm dần. `Sort` ở gốc phục vụ `ORDER BY SUM(o.amount) DESC`, không phải để thực hiện join.

</details>

## 36. Mẫu ghi chú phân tích plan

Khi chia sẻ kết quả với đồng đội, thay vì chỉ dán ảnh EXPLAIN, hãy ghi ngắn gọn:

```text
Truy vấn:
  Lấy 20 đơn mới nhất của customer_id=77.

Kết quả mong đợi:
  Tối đa 20 dòng, sắp theo ordered_at DESC và order_id DESC.

Kế hoạch:
  Index Scan trên (customer_id, ordered_at DESC), sau đó ...
  Sort có/không? Limit có đọc bao nhiêu dòng?

Quan sát:
  actual rows, loops, buffers, execution time.
  estimated rows lệch hay không?

Nhận định:
  Các node đọc/ghép/sắp phù hợp hay đang xử lý dư dữ liệu?

Thay đổi đề xuất:
  Chỉ mục, điều kiện WHERE, ORDER BY, số cột, thống kê...

Xác minh:
  Kết quả đúng nghiệp vụ; so lại plan và runtime trong điều kiện tương tự.
```

Không nên ghi “chậm vì Hash Join” mà không chỉ ra **phần dữ liệu, sai số ước lượng hoặc hoạt động I/O nào** khiến hash join thực tế tốn kém.

## 37. Tổng kết

Khả năng **nhận biết quét bảng, truy cập chỉ mục, JOIN và sắp xếp** bắt đầu từ việc đọc được cây execution plan và giải thích **dòng dữ liệu đi qua từng node**:

```text
Scan / Index Access
        ↓
Filter / Index Cond
        ↓
JOIN: Nested Loop / Hash Join / Merge Join
        ↓
Aggregate / Window
        ↓
Sort / Incremental Sort / Index order
        ↓
Limit / Result
```

Nhớ năm nguyên tắc:

1. **`Seq Scan` không phải lỗi**, và **có index không đồng nghĩa phải dùng index**. Chi phí phụ thuộc tỷ lệ dòng cần đọc, kích thước bảng và heap I/O.
2. **`Index Scan`, `Index Only Scan`, `Bitmap Heap Scan` có tính chất khác nhau**. Đọc `Index Cond`, `Filter`, `Heap Fetches`, bitmap exact/lossy để hiểu từng cách truy cập.
3. **JOIN phải được đánh giá bằng số dòng và số vòng lặp thực tế**. Nested loop phù hợp cho lookup nhỏ; hash join thường hữu ích cho nhiều dòng; merge join tận dụng dữ liệu đã sắp. Không có thuật toán luôn thắng.
4. **`Sort` có nhiều lý do xuất hiện**. Xem `Sort Key`, `Sort Method`, `Disk/Memory`, node cha và khả năng index cung cấp thứ tự; `LIMIT` không tự bảo đảm đọc ít dữ liệu.
5. **`EXPLAIN ANALYZE` là bằng chứng về một lần chạy, không phải chân lý vĩnh viễn**. So ước lượng với actual, xem `loops`/buffers, hiểu phân phối dữ liệu và kiểm chứng lại sau thay đổi.

Khi bạn có thể nhìn một kế hoạch dài và nói rõ **bảng nào đang được quét, điều kiện nào dùng chỉ mục, join đang xây hash hay lặp lookup, sort có dùng đĩa không, và vì sao số dòng thực tế khác ước lượng**, bạn đã có nền tảng để tối ưu SQL dựa trên bằng chứng thay vì phỏng đoán.

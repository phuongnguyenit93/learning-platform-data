# Đọc kế hoạch bằng EXPLAIN và công cụ tương đương

## 1. Tại sao một câu SQL đúng vẫn có thể chạy rất chậm?

Hai câu truy vấn có thể trả **cùng kết quả** nhưng sử dụng tài nguyên rất khác nhau:

```sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM plan_orders
WHERE customer_id = 42;
```

Một hệ quản trị có thể:

- Đọc gần như **toàn bộ bảng**, kiểm tra từng hàng có `customer_id = 42` hay không.
- Đi theo **chỉ mục** để tìm đúng những hàng của khách 42, rồi lấy dữ liệu cần thiết.
- Sử dụng một chỉ mục chứa đủ các cột yêu cầu để giảm việc truy cập bảng.
- Chọn một kế hoạch khác vì bảng nhỏ, thống kê chưa cập nhật, dữ liệu phân bố lệch hoặc bộ nhớ đệm khác nhau.

Cú pháp SQL cho biết **muốn lấy gì**, không bắt buộc database thực hiện từng bước **như thế nào**. Hệ quản trị thường có bộ tối ưu hóa truy vấn (*query optimizer*) để lựa chọn một **execution plan** — kế hoạch thực thi.

Khi cần điều tra truy vấn chậm, câu hỏi hữu ích không chỉ là:

> “Đã tạo index chưa?”

mà là:

> “Database thực sự định đọc dữ liệu theo cách nào, nó dự đoán bao nhiêu hàng, nó đã xử lý bao nhiêu hàng và bước nào sử dụng nhiều thời gian hoặc I/O nhất?”

Lệnh `EXPLAIN` trên PostgreSQL và các công cụ tương đương của MySQL, SQL Server, SQLite, Oracle giúp trả lời những câu hỏi ấy.

**Mục tiêu bài học:** Biết đọc kế hoạch từ các nút cơ bản, phân biệt chi phí ước lượng với số liệu thực tế, nhận diện các phép quét, join, sort, aggregate, phát hiện sai lệch ước lượng và kiểm tra tác dụng của chỉ mục một cách có cơ sở.

---

## 2. Execution plan là gì?

Một **execution plan** là mô tả các thao tác mà database dự định hoặc thực sự thực hiện để xử lý câu SQL.

Ví dụ một truy vấn:

```sql
SELECT
    c.region,
    COUNT(*) AS paid_orders
FROM plan_orders AS o
JOIN plan_customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.region;
```

Bộ tối ưu hóa có thể lập một cây gồm:

```text
Aggregate: đếm đơn theo region
    └── Join: ghép orders với customers
            ├── Scan plan_orders và lọc PAID
            └── Scan plan_customers
```

Từng thành phần được gọi là **plan node** hoặc **operator**. Các node tạo thành một cây. **Đọc từ các node con lên node cha** giúp hiểu dữ liệu đi qua những bước nào.

### 2.1. Kế hoạch không phải thứ tự viết SQL

Bạn viết:

```sql
SELECT ...
FROM ...
JOIN ...
WHERE ...
GROUP BY ...
ORDER BY ...;
```

nhưng optimizer có thể:

- Đẩy điều kiện lọc xuống bước đọc bảng.
- Chọn đọc bảng A trước bảng B hoặc ngược lại.
- Chọn `Hash Join` thay vì `Nested Loop`.
- Sử dụng một index để vừa tìm vừa sắp.
- Kết hợp các phép toán nếu quy tắc biến đổi cho phép.

**Không suy luận hiệu năng chỉ từ thứ tự câu chữ** trong truy vấn.

### 2.2. Kế hoạch là một phương án, không phải cam kết cố định

Cùng SQL có thể có kế hoạch khác nhau khi:

- Số hàng tăng lên.
- Phân bố dữ liệu thay đổi.
- Có hoặc không có index.
- Thống kê `ANALYZE` thay đổi.
- Tham số truy vấn thay đổi.
- Cấu hình bộ nhớ hoặc chi phí thay đổi.
- Phiên bản DBMS/optimizer thay đổi.
- Query được chuẩn bị và dùng kế hoạch chung hoặc riêng theo tham số.

Vì vậy, ví dụ kết quả `EXPLAIN` trong bài được chú thích là **minh họa**, không phải một chuỗi output chắc chắn giống trên mọi máy.

## 3. EXPLAIN và EXPLAIN ANALYZE khác nhau thế nào?

Trên PostgreSQL:

```sql
EXPLAIN
SELECT *
FROM plan_orders
WHERE customer_id = 42;
```

lấy **kế hoạch ước lượng**, thường **không thực thi phần truy vấn cần giải thích**.

Còn:

```sql
EXPLAIN ANALYZE
SELECT *
FROM plan_orders
WHERE customer_id = 42;
```

**thực thi truy vấn** và ghi nhận số liệu đo được, như thời gian, số hàng thực tế và số lần node được chạy.

| Câu lệnh PostgreSQL | Truy vấn được thực thi? | Có số liệu thời gian/hàng thực tế? | Dùng khi nào? |
| --- | --- | --- | --- |
| `EXPLAIN SELECT ...` | Thường không thực thi SELECT được giải thích | Không | Khảo sát kế hoạch dự đoán, tương đối an toàn |
| `EXPLAIN (ANALYZE) SELECT ...` | **Có** | Có | Điều tra hiệu năng thực tế |
| `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | **Có** | Có và số liệu buffer | Điều tra CPU/I/O và số trang được truy cập |
| `EXPLAIN (FORMAT JSON) SELECT ...` | Không thực thi SELECT được giải thích | Không | Thu kết quả có cấu trúc cho công cụ |
| `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT ...` | **Có** | Có | Phân tích có cấu trúc và đo thực tế |

### 3.1. Cảnh báo quan trọng với câu lệnh thay đổi dữ liệu

`EXPLAIN ANALYZE` **thực sự chạy DML** trên PostgreSQL.

Ví dụ:

```sql
EXPLAIN ANALYZE
DELETE FROM plan_orders
WHERE status = 'CANCELLED';
```

không chỉ là “xem kế hoạch DELETE” — câu lệnh DELETE được thực hiện. Nếu không có transaction rollback, bạn có thể mất dữ liệu.

Khi chỉ muốn xem dự đoán:

```sql
EXPLAIN
DELETE FROM plan_orders
WHERE status = 'CANCELLED';
```

Trong môi trường thử nghiệm, khi buộc phải đo DML:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE plan_orders
SET status = 'PAID'
WHERE order_id = 123;

ROLLBACK;
```

**Không coi ROLLBACK là phép hoàn tác mọi tác động ngoài database.** Trigger có thể tạo tương tác ngoại vi, sequence có thể tiêu thụ số và câu lệnh vẫn dùng tài nguyên/khóa trong thời gian chạy.

---

## 4. Tạo bộ dữ liệu mẫu PostgreSQL để đọc kế hoạch

Truy vấn trên bảng 6 dòng thường chọn quét tuần tự vì chi phí mở index không đáng. Để thấy lựa chọn kế hoạch đa dạng hơn, bộ dữ liệu mẫu dùng khoảng **60.000 đơn** và **5.000 khách** trong database học tập.

> Các lệnh dưới đây dành cho PostgreSQL; chỉ chạy trên **schema/database thử nghiệm**, không sử dụng với bảng production.

### 4.1. Bảng khách hàng

```sql
CREATE TABLE plan_customers (
    customer_id INTEGER PRIMARY KEY,
    region TEXT NOT NULL
);

INSERT INTO plan_customers (customer_id, region)
SELECT
    g,
    CASE
        WHEN g % 4 = 0 THEN 'HCM'
        WHEN g % 4 = 1 THEN 'HANOI'
        WHEN g % 4 = 2 THEN 'DANANG'
        ELSE 'OTHER'
    END
FROM generate_series(1, 5000) AS g;
```

### 4.2. Bảng đơn hàng

```sql
CREATE TABLE plan_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES plan_customers(customer_id),
    ordered_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
```

Nạp dữ liệu có cấu trúc xác định:

```sql
INSERT INTO plan_orders (
    order_id, customer_id, ordered_at,
    status, total_amount
)
SELECT
    g,
    ((g - 1) % 5000) + 1,
    TIMESTAMP '2026-01-01 00:00:00'
        + ((g * 37) % 180) * INTERVAL '1 day'
        + (g % 86400) * INTERVAL '1 second',
    CASE
        WHEN g % 10 < 6 THEN 'PAID'
        WHEN g % 10 < 8 THEN 'NEW'
        ELSE 'CANCELLED'
    END,
    ((g % 2000) + 1)::NUMERIC(12, 2)
FROM generate_series(1, 60000) AS g;
```

Một số đặc điểm của tập mẫu:

- Mỗi khách nhận đúng **12 đơn** vì `60000 / 5000 = 12`.
- Có **36.000 đơn PAID**, **12.000 đơn NEW** và **12.000 đơn CANCELLED**.
- Thời điểm đơn trải trên 180 ngày kể từ 01/01/2026.
- `customer_id` và `status` có tương quan do cùng được sinh từ công thức theo `g`. Điều này có ích khi thảo luận sai lệch thống kê, nhưng không đại diện mọi phân bố sản xuất.

### 4.3. Cập nhật thống kê sau khi nạp

```sql
ANALYZE plan_customers;
ANALYZE plan_orders;
```

`ANALYZE` giúp PostgreSQL thu thập thống kê phục vụ ước lượng số hàng và chi phí. Nó **không phải** câu lệnh chạy truy vấn thử. Không cần dựa vào auto-analyze ngay sau khi nạp dữ liệu demo.

Kiểm tra số lượng:

```sql
SELECT
    COUNT(*) AS orders,
    COUNT(DISTINCT customer_id) AS customers,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM plan_orders;
```

Kết quả về số lượng theo bộ dữ liệu sinh:

| orders | customers | paid_orders |
| ---: | ---: | ---: |
| 60.000 | 5.000 | 36.000 |

### 4.4. Tại sao phải có bộ dữ liệu vừa đủ lớn?

Nếu bảng chỉ có 7 dòng, database có thể đọc toàn bảng nhanh hơn việc mở chỉ mục. Khi đó thấy `Seq Scan` không phải bằng chứng “index hỏng”.

Ngay cả với 60.000 dòng, optimizer vẫn có thể chọn kế hoạch khác nhau theo version và môi trường. Dùng bộ dữ liệu giúp quan sát xu hướng, không ép một plan bắt buộc.

## 5. Đọc phần đầu của kế hoạch PostgreSQL

Chạy trước khi tạo chỉ mục phụ cho `customer_id`:

```sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    total_amount
FROM plan_orders
WHERE customer_id = 42;
```

Một kế hoạch **minh họa**, số `cost/rows/width` sẽ thay đổi theo môi trường:

```text
Seq Scan on plan_orders
  (cost=0.00..1400.00 rows=12 width=24)
  Filter: (customer_id = 42)
```

Hãy đọc từng phần.

### 5.1. Seq Scan on plan_orders

`Seq Scan` là **sequential scan**: engine đọc các trang của bảng theo đường truy cập tuần tự và kiểm tra điều kiện lọc.

Nó không mặc nhiên xấu:

- Với bảng nhỏ, Seq Scan thường là lựa chọn hợp lý.
- Nếu truy vấn lấy 60% bảng, đọc tuần tự có thể rẻ hơn nhiều lần truy cập index + heap.
- Nếu không có index phù hợp, đây có thể là lựa chọn khả dụng nhất.

### 5.2. cost=0.00..1400.00

Hai số là **ước lượng chi phí khởi động và tổng chi phí** của node theo mô hình optimizer.

- `0.00`: startup cost trong ví dụ minh họa.
- `1400.00`: tổng chi phí ước lượng của node khi hoàn thành phần công việc được mô tả.

Các đơn vị **không phải mili giây** và không phải số byte đọc trực tiếp. Chi phí phụ thuộc tham số như `seq_page_cost`, `random_page_cost`, `cpu_tuple_cost` và mô hình riêng của PostgreSQL.

### 5.3. rows=12

Optimizer **ước lượng** node trả khoảng 12 hàng cho điều kiện đó. Đây không phải số hàng thực tế cho đến khi chạy `ANALYZE` theo ngữ cảnh `EXPLAIN ANALYZE`.

### 5.4. width=24

`width` là **kích thước trung bình ước lượng của một hàng đầu ra của node**, tính bằng byte theo mô hình planner. Nó **không** phải độ dài của toàn bảng hay kích thước kết quả chính xác trên network.

### 5.5. Filter: (customer_id = 42)

Engine lấy các hàng bằng đường scan đã chọn rồi kiểm tra điều kiện lọc ở node.

Một điểm cần phân biệt khi đọc plan:

- `Filter`: điều kiện kiểm tra sau/bên trong node quét.
- `Index Cond`: điều kiện dùng để giới hạn phạm vi truy cập theo index phù hợp.
- `Recheck Cond`: điều kiện cần kiểm tra lại khi xử lý kết quả từ bitmap/đường truy cập liên quan.

Những nhãn này giúp tìm ra **index có thực sự được tận dụng cho bộ lọc** hay không.

---

## 6. Đọc kế hoạch như một cây: đi từ dưới lên

Ví dụ giả định:

```text
Aggregate
  -> Hash Join
       Hash Cond: (o.customer_id = c.customer_id)
       -> Seq Scan on plan_orders o
            Filter: (status = 'PAID')
       -> Hash
            -> Seq Scan on plan_customers c
```

Đọc theo thứ tự logic:

1. `Seq Scan on plan_customers` đọc hàng khách.
2. `Hash` xây cấu trúc hash từ dữ liệu khách.
3. `Seq Scan on plan_orders` đọc đơn và lọc `PAID`.
4. `Hash Join` nối hai nguồn theo `customer_id`.
5. `Aggregate` tổng hợp dữ liệu đã nối.

**Thụt lề và mũi tên cho biết quan hệ cha–con**, không nên chỉ nhìn node trên cùng rồi kết luận toàn bộ nguyên nhân chậm.

### 6.1. Node gốc thường là kết quả cuối

Node cao nhất thường đại diện phép toán cuối mà truy vấn cần thực hiện: `Aggregate`, `Sort`, `Limit`, `Hash Join` hoặc `Seq Scan`.

Nhưng chi phí node gốc **đã bao gồm phần công việc của các node con theo mô hình cost**; không được cộng tổng chi phí từng node theo cách đơn giản để ra chi phí truy vấn.

### 6.2. Thứ tự thực thi thực tế phức tạp hơn một chuỗi

Một `Hash Join` thường cần xây hash từ phía input trước, trong khi `Nested Loop` có thể gọi lại node phía trong nhiều lần.

Vì vậy “đọc từ dưới lên” là cách **hiểu luồng dữ liệu**, không có nghĩa engine luôn hoàn tất tất cả node lá rồi mới bắt đầu node cha.

### 6.3. Những node cha có thể giữ hoặc thay đổi số hàng

- `Filter` giảm số hàng.
- `Join` có thể tăng hoặc giảm số hàng.
- `Aggregate` thường giảm số hàng, trừ aggregate theo nhiều nhóm.
- `Sort` sắp thứ tự nhưng thường không thay số hàng.
- `Limit` dừng sau số hàng yêu cầu nếu kế hoạch cho phép.

Theo dõi **ước lượng số hàng qua từng node** là kỹ năng quan trọng nhất khi phân tích kế hoạch.

## 7. EXPLAIN ANALYZE: số liệu đo thực tế

Chạy:

```sql
EXPLAIN (ANALYZE)
SELECT
    order_id,
    customer_id,
    total_amount
FROM plan_orders
WHERE customer_id = 42;
```

Một output **minh họa**:

```text
Seq Scan on plan_orders
  (cost=0.00..1400.00 rows=12 width=24)
  (actual time=0.040..4.300 rows=12 loops=1)
  Filter: (customer_id = 42)
  Rows Removed by Filter: 59988
Planning Time: 0.120 ms
Execution Time: 4.350 ms
```

Số thực tế **phụ thuộc máy, cache, thống kê và kế hoạch được chọn**, nên không cần khớp chính xác khi tự chạy.

### 7.1. actual time=0.040..4.300

Đây là thời gian đo được tại node, đơn vị **mili giây**, thường diễn đạt:

- Thời gian tới hàng đầu tiên được node xuất.
- Thời gian tới khi node hoàn tất công việc tương ứng.

Giá trị trong một node có `loops > 1` được báo theo **trung bình trên mỗi lần chạy node** trong PostgreSQL; phải đọc cùng `loops`.

### 7.2. rows=12

Đây là số hàng **thực tế node xuất ra trung bình mỗi lần chạy**, không phải chỉ số ước lượng ở dòng `cost`.

So:

```text
estimated rows=12
actual rows=12
```

thì ước lượng khá sát trong ví dụ. Nhưng với các query thực tế, sai lệch có thể lớn hơn nhiều.

### 7.3. loops=1

Node được thực hiện một vòng.

Nếu `loops=1000`, node được gọi nhiều lần, thường gặp ở phía trong `Nested Loop`.

Một node chỉ mất trung bình `0.02 ms` nhưng chạy `50.000` lần vẫn có thể đóng góp đáng kể vào tổng thời gian.

### 7.4. Rows Removed by Filter

Node quét rất nhiều hàng, chỉ giữ một tập nhỏ.

Trong ví dụ: 60.000 đơn, có 12 đơn của khách 42 nên **59.988 hàng** bị loại tại điều kiện này.

Đây có thể là dấu hiệu hữu ích để tìm một index phù hợp, nhưng vẫn cần so **tổng thời gian, I/O và độ chọn lọc**, không chỉ dùng số hàng bị loại làm tiêu chuẩn duy nhất.

### 7.5. Planning Time và Execution Time

- `Planning Time`: thời gian lập kế hoạch được báo.
- `Execution Time`: thời gian thực thi theo số đo của PostgreSQL EXPLAIN ANALYZE.

Chúng không tương đương toàn bộ **latency người dùng cảm nhận**: còn thời gian network, round trip, serialize rows, mapping trong ứng dụng, chờ connection pool, hiển thị UI và các hoạt động ngoài phép đo.

## 8. Những con số dễ bị đọc sai

| Trường | Đúng là | Không phải |
| --- | --- | --- |
| `cost` | Đơn vị chi phí mô hình planner | Mili giây thực tế |
| `rows` ở estimate | Số hàng optimizer dự đoán | Số hàng chắc chắn có |
| `rows` ở actual | Hàng trung bình mỗi vòng của node | Luôn là tổng hàng toàn bộ các vòng |
| `width` | Byte/hàng theo ước lượng | Tổng dung lượng kết quả |
| `loops` | Số lần node được chạy | Số hàng/transaction |
| `Rows Removed by Filter` | Hàng bị lọc trong node theo cách thống kê | Tổng hàng bị loại trong mọi nhánh toàn truy vấn |
| `Execution Time` | Phép đo server cho chạy truy vấn được giải thích | Toàn bộ độ trễ tới UI |
| `shared hit` | Buffer được tìm thấy trong shared buffer cache | Bảo đảm không dùng RAM/bộ nhớ |
| `shared read` | Buffer phải được nạp vào shared buffer cache | Chắc chắn là một lần đọc đĩa vật lý |

### 8.1. rows × loops: phép tính gần đúng hữu ích

Giả sử:

```text
Index Scan on plan_orders
  (actual time=0.015..0.040 rows=3 loops=500)
```

Ước tính số hàng node xuất trong tất cả lượt:

\[
3 \times 500 \approx 1500\ \text{hàng}.
\]

Do `rows` có thể được làm tròn theo trung bình, phép nhân là **ước tính hữu ích**, không luôn chính xác tới từng hàng.

### 8.2. actual time × loops cần cẩn thận hơn

Nếu một node có thời gian trung bình 0,040 ms và 500 vòng, tổng thời gian node được gọi có thể ở cỡ 20 ms. Nhưng:

- Thời gian node có thể **bao gồm công việc node con**.
- Các node có thể lồng nhau.
- Kế hoạch parallel có các worker chạy đồng thời.
- Timing instrumentation tạo overhead.
- Không thể cộng thời gian tất cả node một cách máy móc để ra `Execution Time`.

Dùng phép nhân để **nhận diện node bị gọi quá nhiều**, không để tuyên bố số mili giây chính xác của từng đoạn.

---

## 9. Sequential Scan: khi nào là vấn đề?

`Seq Scan` là đường đọc toàn bảng. Nó thường hợp lý khi:

- Bảng nhỏ.
- Bộ lọc không chọn lọc.
- Truy vấn cần đọc hầu hết hàng.
- Giá đọc index + truy cập dữ liệu rời rạc lớn hơn đọc tuần tự.
- Thống kê cho thấy ít lợi ích từ index.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_orders
WHERE status = 'PAID';
```

Vì `PAID` chiếm khoảng **60%** đơn, PostgreSQL có thể chọn `Seq Scan` hoặc các đường đi khác.

### 9.1. Đừng tối ưu chỉ để làm biến mất Seq Scan

Một số người coi “plan có Seq Scan” là lỗi và cố tạo index tới khi xuất hiện `Index Scan`.

Thực tế, đường index có thể **chậm hơn** cho truy vấn trả nhiều hàng, đặc biệt khi phải đọc heap rời rạc.

Chỉ kết luận sau khi xem:

- Bộ lọc lấy bao nhiêu phần trăm bảng?
- Execution Time.
- Buffers hit/read.
- Đường index có tránh truy cập bảng không?
- Kích thước bảng, thống kê, cache và tính ổn định qua nhiều lần đo.

### 9.2. Một Seq Scan hợp lý vẫn có thể là bottleneck nghiệp vụ

Nếu báo cáo mỗi phút đọc toàn bảng rất lớn, dù optimizer chọn Seq Scan đúng theo model, workload vẫn có thể cần:

- Bảng tổng hợp/materialized view.
- Phân vùng.
- Chỉ mục/đường lọc khác.
- Thay cách phân tích hoặc cache.
- Thiết kế lại các câu hỏi được hỏi liên tục.

Đọc plan giúp hiểu **vì sao đang tốn tài nguyên**, không chỉ ép optimizer đổi operator.

## 10. Tạo index và quan sát kế hoạch trước/sau

Câu truy vấn:

```sql
SELECT order_id, customer_id, total_amount
FROM plan_orders
WHERE customer_id = 42;
```

Bảng `plan_orders` đã có primary key trên `order_id`, **chưa có index được khai báo trên `customer_id`**.

Tạo index phù hợp:

```sql
CREATE INDEX plan_orders_customer_idx
ON plan_orders(customer_id);

ANALYZE plan_orders;
```

Đo:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, total_amount
FROM plan_orders
WHERE customer_id = 42;
```

Kế hoạch có thể chuyển sang:

```text
Bitmap Heap Scan on plan_orders
  Recheck Cond: (customer_id = 42)
  -> Bitmap Index Scan on plan_orders_customer_idx
       Index Cond: (customer_id = 42)
```

hoặc:

```text
Index Scan using plan_orders_customer_idx on plan_orders
  Index Cond: (customer_id = 42)
```

Optimizer tự chọn đường đi dựa trên dự toán chi phí và tình trạng dữ liệu.

### 10.1. Những quan sát cần ghi lại

| Trước index | Sau index |
| --- | --- |
| Loại node đọc bảng | Loại node đọc bảng |
| Estimated rows | Estimated rows |
| Actual rows | Actual rows |
| Rows Removed by Filter | Rows Removed by Filter |
| Buffers shared hit/read | Buffers shared hit/read |
| Execution Time | Execution Time |
| Planning Time | Planning Time |

Không nên kết luận index hiệu quả chỉ vì trong plan xuất hiện tên index; cần xem **kết quả thời gian và I/O qua nhiều lần đo**.

### 10.2. Index cũng có chi phí

- Tốn dung lượng lưu trữ.
- Gây thêm công việc cho INSERT/UPDATE/DELETE.
- Có thể làm tăng chi phí VACUUM/bảo trì.
- Không phù hợp nếu workload hiếm khi dùng.
- Có thể trùng công dụng với index đã có.

Chỉ tạo chỉ mục sau khi xác định query/workload cần tối ưu, không tạo cho mọi cột.

---

## 11. Index Scan, Index Only Scan và Bitmap Scan

Ba nhóm node này dễ bị nhầm.

### 11.1. Index Scan

```text
Index Scan using plan_orders_customer_idx on plan_orders
  Index Cond: (customer_id = 42)
```

Engine sử dụng cấu trúc index để tìm các hàng tương ứng. Nếu query cần cột không nằm trong index, nó có thể phải truy cập **heap/bảng nền** để lấy các cột còn thiếu.

### 11.2. Index Only Scan

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_orders
WHERE customer_id = 42;
```

Index trên `customer_id` có thể đủ để đáp ứng điều kiện và phép đếm. PostgreSQL có thể chọn:

```text
Aggregate
  -> Index Only Scan using plan_orders_customer_idx
       Index Cond: (customer_id = 42)
       Heap Fetches: 0
```

Đây là output **minh họa**. `Heap Fetches` không phải lúc nào cũng bằng 0: PostgreSQL còn phải xét **visibility map** và MVCC để biết có thể xác nhận tính hiển thị của hàng chỉ từ index/metadata hay không.

### 11.3. Bitmap Index Scan + Bitmap Heap Scan

```text
Bitmap Heap Scan on plan_orders
  Recheck Cond: (customer_id = 42)
  -> Bitmap Index Scan on plan_orders_customer_idx
       Index Cond: (customer_id = 42)
```

Bitmap access thường phù hợp với một tập hàng vừa phải, cho phép tập hợp địa chỉ trang/hàng rồi truy cập heap theo phương án hiệu quả hơn so với tra từng tuple ngẫu nhiên.

### 11.4. Bitmap có thể kết hợp nhiều index

Ví dụ một điều kiện:

```sql
WHERE customer_id = 42
  AND status = 'PAID'
```

Nếu có các index riêng trên hai cột, optimizer có thể dùng `BitmapAnd` để kết hợp; với `OR` có thể dùng `BitmapOr` khi thích hợp.

Không nên tạo hai index riêng chỉ vì hy vọng BitmapAnd luôn tốt hơn **một index kết hợp**. Hiệu quả phụ thuộc selectivity và workload.

### 11.5. Recheck Cond không tự là dấu hiệu lỗi

`Recheck Cond` có thể xuất hiện trong `Bitmap Heap Scan`. Khi bitmap bị mất độ chính xác vì áp lực bộ nhớ (*lossy bitmap*) hoặc cơ chế truy cập yêu cầu recheck, có thể có những hàng bị loại sau khi đọc heap.

Vì vậy cần xem `Rows Removed by Index Recheck` nếu xuất hiện, cùng bộ nhớ `work_mem` và tình trạng truy cập, thay vì coi mọi `Recheck Cond` là bất thường.

## 12. Phân biệt Index Cond và Filter

Giả sử có index:

```sql
CREATE INDEX plan_orders_customer_date_idx
ON plan_orders(customer_id, ordered_at);
```

Truy vấn:

```sql
EXPLAIN
SELECT *
FROM plan_orders
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMP '2026-05-01'
  AND total_amount > 500;
```

Một plan minh họa:

```text
Index Scan using plan_orders_customer_date_idx
  on plan_orders
  Index Cond: (
      (customer_id = 42)
      AND (ordered_at >= '2026-05-01'::timestamp)
  )
  Filter: (total_amount > 500)
```

Ý nghĩa:

- `Index Cond`: giới hạn đường tìm bằng các cột của index.
- `Filter`: tiếp tục kiểm tra `total_amount` trên các hàng đã được đưa tới node.
- Nếu điều kiện sau lọc loại gần hết các hàng đã tìm, cân nhắc liệu một index khác hoặc query khác hiệu quả hơn.

### 12.1. Không phải Filter nào cũng cần thêm index

Nếu index đã rút tập ứng viên từ 60.000 còn 2 hàng, việc lọc thêm `total_amount` có thể rất rẻ. Tạo index nữa chỉ để đưa `Filter` thành `Index Cond` không nhất thiết cải thiện hiệu năng.

### 12.2. Thứ tự cột index kết hợp có ảnh hưởng

Với index:

```sql
CREATE INDEX ...
ON plan_orders(customer_id, ordered_at);
```

điều kiện `customer_id = ?` và khoảng ngày có thể phù hợp. Nhưng khi chỉ lọc `ordered_at` mà không có `customer_id`, hiệu quả có thể khác.

Không tồn tại quy tắc “index nhiều cột luôn tốt hơn” hoặc “thứ tự cột không quan trọng”.

## 13. ORDER BY và LIMIT: index có thể tránh Sort

Một truy vấn phổ biến:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM plan_orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 5;
```

Nếu chỉ có index đơn `customer_id`, database có thể tìm các đơn của khách rồi **Sort**.

Tạo index phù hợp với bộ lọc và thứ tự:

```sql
CREATE INDEX plan_orders_customer_recent_idx
ON plan_orders (
    customer_id,
    ordered_at DESC,
    order_id DESC
);
```

Đọc:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    ordered_at,
    total_amount
FROM plan_orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 5;
```

Có thể thấy một đường `Index Scan` đáp ứng thứ tự và `Limit` dừng sau đủ năm hàng, không cần `Sort` riêng.

### 13.1. Không có Sort không có nghĩa không có chi phí

Index có thể đã sắp theo thứ tự phù hợp. Engine vẫn phải đọc các entry/hàng tương ứng, và index có chi phí lưu trữ/bảo trì.

### 13.2. ORDER BY phải đủ xác định nếu cần phân trang ổn định

Chỉ:

```sql
ORDER BY ordered_at DESC
```

không quyết định thứ tự của hai đơn có cùng `ordered_at`. Khi phân trang, có thể thêm khóa unique như `order_id DESC` để tránh thứ tự không ổn định giữa những hàng đồng hạng.

### 13.3. LIMIT có thể làm thay đổi kế hoạch

Nếu chỉ cần năm hàng đầu, optimizer có thể ưu tiên đường truy cập trả kết quả sớm. Cùng SQL bỏ `LIMIT` có thể dùng đường quét và sắp khác.

Đừng lấy plan của query không có `LIMIT` để đại diện hoàn toàn cho query có `LIMIT`.

---

## 14. Sort: nhận diện sắp xếp và tràn ra đĩa

Một phần plan PostgreSQL minh họa:

```text
Sort
  Sort Key: ordered_at DESC
  Sort Method: quicksort  Memory: 2100kB
  -> Seq Scan on plan_orders
```

Ý nghĩa:

- `Sort Key`: cột/biểu thức và thứ tự cần sắp.
- `Sort Method`: thuật toán đã dùng khi thực thi.
- `Memory`: bộ nhớ được báo cho thao tác đó.

Nếu không đủ bộ nhớ phù hợp, có thể thấy dạng:

```text
Sort Method: external merge  Disk: 24000kB
```

Đây là một **dấu hiệu sort cần thao tác với dữ liệu tạm trên đĩa**, thường đáng điều tra nếu bước sort chiếm đáng kể thời gian/I/O.

### 14.1. work_mem không phải toàn bộ bộ nhớ của database

Trong PostgreSQL, `work_mem` có thể ảnh hưởng khả năng sort/hash hoạt động trong RAM. Tuy nhiên, nó có thể được sử dụng bởi **nhiều node, nhiều worker và nhiều truy vấn đồng thời**.

Tăng `work_mem` toàn hệ thống quá mạnh có thể làm tăng nguy cơ tiêu thụ RAM quá mức.

### 14.2. Cách xử lý khi Sort tốn kém

Tùy trường hợp:

- Index phù hợp với `WHERE` + `ORDER BY`.
- Giảm dữ liệu đầu vào trước khi sort nếu đúng nghĩa truy vấn.
- Phân trang đúng cách.
- Xem lại `DISTINCT`/`ORDER BY` không cần thiết.
- Điều chỉnh bộ nhớ có thử nghiệm và quan sát tải đồng thời.

Không nên tăng memory chỉ vì nhìn thấy `Sort`: sort trên vài trăm hàng có thể hoàn toàn bình thường.

### 14.3. Top-N và Sort

Với `ORDER BY ... LIMIT N`, PostgreSQL có thể dùng một thuật toán top-N thay vì sắp toàn bộ theo cách thông thường; trong EXPLAIN ANALYZE có thể xuất hiện `top-N heapsort`.

Tuy vậy, việc chỉ trả N hàng **không có nghĩa** database luôn chỉ đọc N hàng đầu vào; nếu không có đường truy cập theo thứ tự, nó có thể phải kiểm tra rất nhiều hàng để xác định top N.

## 15. DISTINCT, GROUP BY, Aggregate và HashAggregate

Truy vấn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS paid_order_count
FROM plan_orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

Một kế hoạch có thể chứa:

```text
HashAggregate
  Group Key: customer_id
  -> Seq Scan on plan_orders
       Filter: (status = 'PAID')
```

Hoặc:

```text
GroupAggregate
  Group Key: customer_id
  -> Sort
       Sort Key: customer_id
       -> ...
```

### 15.1. HashAggregate

Tạo cấu trúc hash để tổng hợp theo khóa nhóm. Hữu ích khi phân nhóm có số lượng và kích thước phù hợp.

Trong EXPLAIN ANALYZE, có thể thấy các thông tin như `Batches`, `Memory Usage` và `Disk Usage` tùy phiên bản, cấu hình và việc aggregate tràn bộ nhớ.

### 15.2. GroupAggregate

Thường tận dụng đầu vào đã có thứ tự nhóm hoặc một node `Sort`. Nếu dữ liệu đến từ index có thứ tự phù hợp, có thể không cần sort riêng.

### 15.3. COUNT(DISTINCT) có thể tốn nhiều hơn COUNT(*)

`COUNT(DISTINCT customer_id)` phải loại trùng theo khóa được đếm. Đường thực thi có thể sử dụng sort/hash hoặc những kỹ thuật khác tùy plan.

Nhưng **không được bỏ DISTINCT chỉ để giảm thời gian** nếu bài toán cần số khách duy nhất. Muốn tối ưu có thể tạo trước một tập theo grain phù hợp, vật chất hóa bước tổng hợp hoặc thay mô hình dữ liệu.

### 15.4. Estimate của số nhóm quan trọng

Nếu optimizer nghĩ chỉ có 10 nhóm nhưng thực tế 100.000 nhóm, chi phí hash/sort và lượng bộ nhớ có thể khác xa dự đoán.

So số hàng ước lượng và thực tế ở node aggregate, cùng thông tin sử dụng bộ nhớ, giúp phát hiện vấn đề.

---

## 16. JOIN: ba họ thuật toán cần nhận diện

Ba loại phổ biến trên PostgreSQL:

1. **Nested Loop Join**.
2. **Hash Join**.
3. **Merge Join**.

Không có loại nào tốt nhất trong mọi trường hợp.

| Thuật toán | Ý tưởng | Thường phù hợp khi |
| --- | --- | --- |
| Nested Loop | Với mỗi hàng phía ngoài, tìm các hàng khớp phía trong | Một phía ít hàng; phía trong có index seek hiệu quả |
| Hash Join | Xây hash một phía và dò phía còn lại | Join bằng dấu bằng, tập dữ liệu tương đối lớn, đủ bộ nhớ |
| Merge Join | Đọc hai phía theo thứ tự khóa join | Dữ liệu có thể được đưa ra theo thứ tự hữu ích, hoặc chi phí sort hợp lý |

### 16.1. Nested Loop không mặc định là tệ

Ví dụ:

```text
Nested Loop
  -> Index Scan on plan_customers
       Index Cond: (customer_id = 42)
  -> Index Scan on plan_orders
       Index Cond: (customer_id = 42)
```

Nếu phía ngoài chỉ có một khách, phía trong tìm bằng index, đây có thể là plan rất nhanh.

### 16.2. Nested Loop có thể là vấn đề khi gọi phía trong quá nhiều lần

Ví dụ minh họa:

```text
Nested Loop
  -> Seq Scan on plan_customers
       (actual rows=5000 loops=1)
  -> Index Scan on plan_orders
       (actual rows=12 loops=5000)
```

Có khoảng **5.000 lượt tra cứu index**. Điều này vẫn có thể hợp lý, nhưng nếu mỗi lượt đọc nhiều heap page hoặc filter khó, tổng I/O/thời gian có thể cao.

**Xem `loops`** trước khi quyết định.

### 16.3. Hash Join

Ví dụ:

```text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  -> Seq Scan on plan_orders o
  -> Hash
       -> Seq Scan on plan_customers c
```

`Hash` xây dữ liệu cho một phía join. `Hash Cond` cho biết khóa được dùng.

Nếu thiếu bộ nhớ, hash join có thể chia nhiều batch và dùng file tạm. `Batches` và thông tin buffer/temp giúp nhận diện.

### 16.4. Merge Join

Ví dụ:

```text
Merge Join
  Merge Cond: (o.customer_id = c.customer_id)
  -> Index Scan on plan_orders o
  -> Index Scan on plan_customers c
```

Hai đầu vào cần có thứ tự tương thích. Nếu chưa được sắp, engine có thể thêm `Sort`.

Một `Merge Join` không phải kết quả của cú pháp SQL `MERGE INTO`; đây là **thuật toán nối dữ liệu**, khác lệnh DML MERGE.

## 17. Đọc một kế hoạch JOIN có filter và aggregate

Truy vấn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.region,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS revenue
FROM plan_orders AS o
JOIN plan_customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
  AND o.ordered_at >= TIMESTAMP '2026-05-01'
GROUP BY c.region
ORDER BY revenue DESC;
```

Một cây **minh họa về cấu trúc**, không dự đoán số cost/thời gian cụ thể:

```text
Sort
  Sort Key: (sum(o.total_amount)) DESC
  -> HashAggregate
       Group Key: c.region
       -> Hash Join
            Hash Cond: (o.customer_id = c.customer_id)
            -> Seq Scan on plan_orders o
                 Filter: (
                   status = 'PAID'
                   AND ordered_at >= '2026-05-01'
                 )
            -> Hash
                 -> Seq Scan on plan_customers c
```

### 17.1. Câu hỏi nên đặt ở từng node

**Seq Scan orders:** Có đọc quá nhiều đơn so với số hàng cần sau filter không? Một index theo status/date có giúp không?

**Seq Scan customers:** Bảng khách có nhỏ không? Đọc toàn bộ để tạo hash có hợp lý không?

**Hash Join:** Estimated rows và actual rows có lệch lớn không? Có tốn nhiều batch/temp không?

**HashAggregate:** Số nhóm là bao nhiêu? Có chỉ bốn khu vực không? Bộ nhớ có đủ không?

**Sort:** Chỉ sắp bốn khu vực thì có đáng tối ưu không?

Đừng dành thời gian tối ưu node `Sort` nếu nó chỉ sắp vài hàng và chi phí thực nằm ở việc quét hàng chục nghìn đơn.

### 17.2. Hãy nhìn từ dữ liệu ít chọn lọc tới node tốn tài nguyên

Đối với query báo cáo, nơi cần điều tra thường là:

- Quá nhiều hàng được đọc trước khi filter.
- Join làm số hàng tăng mạnh.
- Ước lượng join cardinality sai.
- Aggregate trên tập dữ liệu rất lớn.
- Sort/hash spill.
- Truy vấn lặp lại quá thường xuyên.

### 17.3. LEFT JOIN và vị trí WHERE

Không tự chuyển điều kiện từ `ON` sang `WHERE` của một `LEFT JOIN` chỉ vì tưởng sẽ làm plan nhanh hơn. Với bảng bên phải có thể `NULL`, việc chuyển điều kiện có thể **đổi kết quả** thành giống inner join.

Tối ưu phải giữ nguyên ngữ nghĩa, không chỉ đạt kế hoạch nhìn “đẹp”.

---

## 18. Cardinality misestimation: sai số hàng là đầu mối quan trọng

**Cardinality** là số hàng của một tập trung gian hoặc kết quả.

Một plan minh họa:

```text
Nested Loop  (cost=... rows=5 ...)
  (actual time=... rows=80000 loops=1)
```

Nếu optimizer dự đoán **5** hàng nhưng thực tế có **80.000**, lựa chọn Nested Loop có thể không còn phù hợp.

Các nguyên nhân có thể là:

- Thống kê cũ.
- Dữ liệu phân bố lệch (*skew*).
- Những cột có tương quan nhưng optimizer coi độc lập.
- Biểu thức/hàm làm thống kê khó áp dụng.
- JOIN trên khóa thiếu ràng buộc hoặc thiếu thông tin uniqueness.
- Query parameter khiến kế hoạch ước lượng không phù hợp giá trị cụ thể.

### 18.1. Tỷ lệ estimate/actual

Một phép kiểm tra thực tế:

\[
\text{estimation ratio} =
\frac{\max(\text{estimated rows},\ \text{actual rows})}
     {\max(1,\ \min(\text{estimated rows},\ \text{actual rows}))}.
\]

Đây chỉ là **chỉ số do người phân tích tự đặt** để nhanh chóng nhận diện sai lệch. Không phải metric chuẩn được PostgreSQL in ra.

Nếu ước lượng 100, thực tế 10.000, sai lệch cỡ **100 lần**.

### 18.2. Tìm sai lệch xuất hiện từ đâu

Đừng chỉ xem node gốc. Hãy đi xuống cây:

1. Có lệch ngay tại `Seq Scan` sau filter không?
2. Hay scans đều gần đúng nhưng `Join` làm hàng tăng ngoài dự đoán?
3. Hay `GROUP BY` có số nhóm lớn hơn dự đoán?
4. Có một tham số lọc hiếm/đặc biệt khiến estimate khác dữ liệu thật?

Nơi sai lệch **bắt đầu** thường có giá trị hơn nơi sai lệch lớn nhất ở cuối cây.

### 18.3. Vì sao sai số hàng dẫn đến plan chậm?

Cardinality ảnh hưởng quyết định:

- Dùng index hay seq scan.
- Nested loop hay hash/merge join.
- Đọc bảng nào trước.
- Có sort hay không.
- Cấp phát bộ nhớ cho hash/sort.
- Chọn parallel plan hay không.

Một thống kê sai có thể khiến optimizer chọn cách thực thi không phù hợp, dù SQL logic hoàn toàn đúng.

## 19. ANALYZE: làm mới thống kê, không sửa dữ liệu

PostgreSQL:

```sql
ANALYZE plan_orders;
```

thu thập thống kê về dữ liệu phục vụ optimizer.

Sau khi nạp một lượng lớn dữ liệu, cập nhật rất nhiều hàng hoặc thay đổi phân bố, thống kê cũ có thể làm estimate thiếu chính xác.

### 19.1. Xem một số thống kê mức cột

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals
FROM pg_stats
WHERE tablename = 'plan_orders'
  AND attname IN ('customer_id', 'status', 'ordered_at');
```

Cột `most_common_vals` hiển thị những giá trị phổ biến khi thống kê có thông tin thích hợp, không phải danh sách toàn bộ giá trị.

### 19.2. ANALYZE không chắc tạo ra plan mong muốn

Thống kê tốt hơn giúp optimizer có thêm thông tin, nhưng:

- Index vẫn có thể không hiệu quả.
- Chi phí/độ chọn lọc có thể vẫn ưu tiên Seq Scan.
- Dữ liệu có tương quan khó biểu diễn bằng thống kê đơn cột.
- Tham số cấu hình và query shape vẫn ảnh hưởng.

Đừng chạy `ANALYZE` rồi coi nhiệm vụ tối ưu đã hoàn thành; cần **đo lại plan và thời gian**.

### 19.3. Tăng mức thống kê khi cần

PostgreSQL cho phép điều chỉnh statistics target đối với cột, chẳng hạn:

```sql
ALTER TABLE plan_orders
ALTER COLUMN status
SET STATISTICS 500;

ANALYZE plan_orders;
```

Mức target cao hơn có thể giúp ước lượng trong một số workload nhưng làm tăng chi phí thu thập/lưu thống kê. Không chọn giá trị lớn tùy tiện cho mọi cột.

### 19.4. Extended statistics cho cột có tương quan

Nếu điều kiện lọc kết hợp những cột tương quan, PostgreSQL có `CREATE STATISTICS` cho các dạng thống kê mở rộng phù hợp.

Ví dụ minh họa:

```sql
CREATE STATISTICS plan_orders_customer_status_stats
    (dependencies, mcv)
ON customer_id, status
FROM plan_orders;

ANALYZE plan_orders;
```

Dữ liệu mẫu có tương quan giữa `customer_id` và `status`. Thống kê mở rộng **có thể hỗ trợ một số phép ước lượng kết hợp** trong phạm vi PostgreSQL hỗ trợ; không tự giải quyết mọi sai lệch của JOIN nhiều bảng.

---

## 20. Sargability: viết điều kiện sao cho index có thể hữu ích

Một điều kiện được gọi là *sargable* khi có thể được xử lý hiệu quả bởi cấu trúc truy cập phù hợp, ví dụ điều kiện range trên cột index.

### 20.1. Lọc theo khoảng timestamp

Ít thuận tiện hơn cho index thông thường trên `ordered_at`:

```sql
SELECT *
FROM plan_orders
WHERE DATE(ordered_at) = DATE '2026-05-01';
```

Dạng khoảng nửa mở:

```sql
SELECT *
FROM plan_orders
WHERE ordered_at >= TIMESTAMP '2026-05-01 00:00:00'
  AND ordered_at <  TIMESTAMP '2026-05-02 00:00:00';
```

Với index:

```sql
CREATE INDEX plan_orders_ordered_at_idx
ON plan_orders(ordered_at);
```

optimizer có thể sử dụng khoảng ngày trực tiếp làm `Index Cond`.

### 20.2. Vì sao tránh DATE(column) trong ví dụ này?

Nếu áp dụng hàm cho mọi giá trị cột, một index B-tree thông thường trên nguyên `ordered_at` có thể không được sử dụng theo cách range đơn giản.

Tuy nhiên, PostgreSQL hỗ trợ **expression index**:

```sql
CREATE INDEX plan_orders_order_day_idx
ON plan_orders ((ordered_at::DATE));
```

với những điều kiện phù hợp. Vì thế kết luận đúng không phải “mọi hàm trong WHERE đều cấm dùng index”, mà là **biểu thức truy vấn phải phù hợp với index/operator class được thiết kế**.

### 20.3. Không viết CAST để thay định nghĩa múi giờ

Nếu `ordered_at` là `TIMESTAMPTZ`, việc chuyển sang ngày lịch phụ thuộc múi giờ. Hãy thống nhất múi giờ nghiệp vụ trước khi so, không chỉ bỏ `DATE(...)` mà làm lệch ranh giới ngày.

### 20.4. LIKE và index

`LIKE 'ABC%'` có thể tận dụng một số loại index/operator class/collation phù hợp.

`LIKE '%ABC%'` thường không được B-tree thông thường tối ưu như tìm prefix; PostgreSQL có các lựa chọn khác như trigram index (`pg_trgm`) khi workload cần.

Không kết luận “LIKE luôn quét bảng” hoặc “chỉ cần index B-tree là mọi LIKE đều nhanh”.

## 21. Partial index, covering index và index kết hợp

Khi đọc plan, mục tiêu không chỉ là có một index mà là **index phù hợp điều kiện và cột đầu ra của truy vấn**.

### 21.1. Partial index

Nếu đa số truy vấn chỉ quan tâm đơn `PAID`:

```sql
CREATE INDEX plan_orders_paid_recent_idx
ON plan_orders(ordered_at DESC)
WHERE status = 'PAID';
```

Index chỉ chứa các hàng thỏa predicate khi được duy trì.

Một truy vấn:

```sql
SELECT order_id, ordered_at
FROM plan_orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMP '2026-05-01';
```

có thể tận dụng index này khi planner chứng minh điều kiện truy vấn phù hợp với predicate của index.

**Lưu ý:** Với prepared statement có điều kiện tham số và generic plan, database có thể không chứng minh được predicate cho mọi giá trị tham số. Việc index một phần có được chọn hay không còn phụ thuộc query shape và cơ chế planning.

### 21.2. INCLUDE cho index có cột mang theo

PostgreSQL:

```sql
CREATE INDEX plan_orders_customer_cover_idx
ON plan_orders(customer_id)
INCLUDE (total_amount, ordered_at);
```

Các cột trong `INCLUDE` có thể giúp đáp ứng SELECT mà không phải tìm cột đó từ heap, **nhưng không tự đảm bảo Index Only Scan**. MVCC visibility và điều kiện truy vấn vẫn quan trọng.

### 21.3. Index kết hợp

```sql
CREATE INDEX plan_orders_status_date_customer_idx
ON plan_orders(status, ordered_at, customer_id);
```

có thể phù hợp với điều kiện trạng thái bằng giá trị và một khoảng ngày, tùy truy vấn.

Nhưng thêm index dài có thể:

- Tốn dung lượng.
- Tăng chi phí ghi.
- Ít lợi ích cho những truy vấn không lọc theo các cột tiền tố thích hợp.
- Trùng lắp với index khác.

Hãy dùng `EXPLAIN` để kiểm chứng một **workload truy vấn thật**, không đánh giá index chỉ theo số cột.

---

## 22. BUFFERS: nhìn vào lượng truy cập trang

PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM plan_orders
WHERE customer_id = 42;
```

Một node có thể in:

```text
Buffers: shared hit=120 read=8
```

Đây là **thông tin buffer ở phía PostgreSQL**, hữu ích để phân tích I/O.

### 22.1. shared hit

Buffer cần đọc đã có trong shared buffer cache của PostgreSQL.

Nó **không** nghĩa “không tốn tài nguyên”: vẫn có xử lý CPU, truy cập memory và có thể có các chi phí khác.

### 22.2. shared read

Buffer phải được đọc đưa vào shared buffer cache. Dữ liệu đó có thể đã nằm trong **OS filesystem cache**, nên con số `read` không đồng nghĩa đúng từng lần truy cập đĩa vật lý.

### 22.3. shared dirtied và written

Khi phù hợp, plan có thể báo những buffer bị làm bẩn hoặc được ghi theo các quy tắc instrumentation.

Không nên chỉ nhìn `written=0` rồi kết luận một câu DML không gây ghi dữ liệu lâu dài; việc ghi WAL, checkpoint và dirty buffer flushing có cơ chế thời điểm riêng.

### 22.4. temp read/written

Nếu sort hoặc hash cần file tạm, PostgreSQL có thể báo:

```text
Buffers: temp read=... written=...
```

Kết hợp với thông tin `Sort Method: external merge` hoặc hash batching, đây có thể là tín hiệu thiếu bộ nhớ cho phép toán trung gian.

### 22.5. Buffer của node cha có thể bao gồm công việc con

Số buffer ở các node cha có thể có tính **tích lũy** cho subtree. Không cộng mọi `shared hit` của mọi node để ra số buffer duy nhất của toàn truy vấn — có thể đếm lặp.

Dùng các số để **xác định khu vực trong cây** tạo nhiều hoạt động buffer.

## 23. I/O timing, WAL và các tùy chọn PostgreSQL khác

Một số tùy chọn hữu ích:

```sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    VERBOSE,
    SETTINGS,
    WAL,
    SUMMARY
)
SELECT *
FROM plan_orders
WHERE customer_id = 42;
```

### 23.1. VERBOSE

Hiển thị thêm chi tiết như cột đầu ra của node, tên alias/schema trong một số trường hợp. Hữu ích khi plan có nhiều cột/tên bảng tương tự nhau.

### 23.2. SETTINGS

Có thể hiển thị những tham số cấu hình liên quan đến planning khác giá trị mặc định theo cơ chế PostgreSQL.

Nó không phải danh sách đầy đủ **mọi** tham số server.

### 23.3. WAL

Thông tin về **Write-Ahead Log** có thể hữu ích khi giải thích câu DML hoặc truy vấn có phát sinh WAL theo ngữ cảnh được hỗ trợ.

Một câu `SELECT` thông thường không có nghĩa chắc chắn sinh WAL đáng kể. Không nên coi `WAL` là lựa chọn luôn hữu ích với mọi truy vấn chỉ đọc.

### 23.4. I/O timings

PostgreSQL có các cấu hình đo thời gian I/O như `track_io_timing`, tùy phiên bản và quyền.

Khi được bật, kế hoạch có thể cung cấp thêm thông tin thời gian đọc/ghi. Đo chi tiết hơn có thể gây overhead, nên cần xem hướng dẫn vận hành của hệ thống.

### 23.5. FORMAT JSON/YAML/XML

PostgreSQL có thể xuất định dạng có cấu trúc:

```sql
EXPLAIN (FORMAT JSON)
SELECT *
FROM plan_orders
WHERE customer_id = 42;
```

Định dạng JSON tiện cho lưu kết quả, so sánh tự động hoặc trình xem cây. Đừng viết parser dựa vào khoảng trắng/indent của bản text nếu công cụ cần hoạt động ổn định.

### 23.6. Kết quả EXPLAIN có thể chứa dữ liệu nhạy cảm

Một plan với tham số/literal trong SQL có thể lộ giá trị tìm kiếm, bảng nhạy cảm hoặc cấu trúc schema. Khi chia sẻ plan ra ticket/public chat, cần ẩn hoặc thay thế dữ liệu nhạy cảm, giữ lại những phần cần phân tích.

---

## 24. Parallel Query: tại sao có Gather/Gather Merge?

Với truy vấn đủ lớn và môi trường phù hợp, PostgreSQL có thể chọn kế hoạch song song.

Ví dụ minh họa:

```text
Finalize Aggregate
  -> Gather
       Workers Planned: 2
       Workers Launched: 2
       -> Partial Aggregate
            -> Parallel Seq Scan on plan_orders
```

Các node:

- `Parallel Seq Scan`: nhiều worker tham gia quét dữ liệu theo cơ chế parallel.
- `Partial Aggregate`: mỗi worker tính kết quả trung gian.
- `Gather`: gom hàng từ worker về node lãnh đạo.
- `Finalize Aggregate`: kết hợp kết quả trung gian.
- `Gather Merge`: gom dữ liệu song song đồng thời bảo toàn thứ tự tương ứng khi áp dụng.

### 24.1. Không phải cứ parallel là nhanh hơn

Parallelism có overhead:

- Khởi động/điều phối worker.
- Truyền/ghép kết quả.
- Áp lực CPU và bộ nhớ.
- Tranh chấp I/O.
- Giới hạn khả năng parallel của biểu thức/hàm.

Truy vấn nhỏ có thể chạy chậm hơn nếu cố ép parallel.

### 24.2. Workers Planned khác Workers Launched

Optimizer có thể lên kế hoạch dùng 2 worker, nhưng lúc thực thi không có đủ worker theo tình trạng tài nguyên. Đọc cả hai trường nếu xuất hiện.

### 24.3. Cẩn thận khi cộng thời gian worker

Các worker hoạt động **đồng thời**, nên tổng thời gian các worker không thể cộng trực tiếp rồi so với thời gian thực tế toàn query. Sử dụng plan và profile đúng ngữ nghĩa parallel.

## 25. JIT compilation và kế hoạch thực thi

Một số phiên bản/cấu hình PostgreSQL có thể hiển thị mục `JIT` trong `EXPLAIN ANALYZE` nếu JIT được sử dụng.

JIT có thể giúp với truy vấn tính toán nặng nhưng cũng có **chi phí biên dịch**. Truy vấn ngắn có thể không hưởng lợi.

Nếu thấy thời gian JIT nổi bật:

1. Xem query có nặng về CPU/expression không.
2. Xem tần suất và kích thước dữ liệu.
3. Đối chiếu tổng `Execution Time`.
4. Thử các tùy chọn theo môi trường thử nghiệm, không tắt JIT toàn hệ thống chỉ từ một plan.

Không phải mọi DBMS đều in phần JIT giống PostgreSQL, và không phải mọi kế hoạch đều có JIT.

---

## 26. LIMIT, OFFSET và “chỉ lấy 20 dòng” không luôn rẻ

Truy vấn:

```sql
SELECT order_id, ordered_at
FROM plan_orders
ORDER BY ordered_at DESC
LIMIT 20 OFFSET 50000;
```

Có thể cần tìm/đi qua **50.020 hàng đầu** theo thứ tự trước khi bỏ 50.000 hàng.

Ngay cả khi có index hỗ trợ thứ tự, một `OFFSET` rất sâu vẫn có thể tốn đáng kể.

### 26.1. Quan sát trên plan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at
FROM plan_orders
ORDER BY ordered_at DESC
LIMIT 20 OFFSET 50000;
```

Quan sát node con dưới `Limit`: nó có thể xuất nhiều hơn 20 hàng vì phải phục vụ phần bỏ qua.

### 26.2. Keyset pagination

Nếu ứng dụng điều hướng trang tiếp theo theo khóa thứ tự:

```sql
SELECT order_id, ordered_at
FROM plan_orders
WHERE (ordered_at, order_id)
      < (TIMESTAMP '2026-05-10 12:00:00', 40000)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

với index:

```sql
CREATE INDEX plan_orders_cursor_idx
ON plan_orders(ordered_at DESC, order_id DESC);
```

có thể tránh chi phí bỏ qua hàng chục nghìn dòng như `OFFSET` sâu, nếu contract phân trang và bộ lọc phù hợp.

### 26.3. Keyset không đồng nghĩa snapshot cố định

Khi dữ liệu mới được thêm hoặc cập nhật giữa các trang, keyset giúp điều hướng ổn định hơn theo khóa nhưng **không tự khóa toàn bộ danh sách** tại một ảnh chụp. Nếu cần một báo cáo nhất quán tuyệt đối theo thời điểm, phải xét isolation/snapshot.

## 27. Subquery, CTE và kế hoạch thực thi

CTE thường giúp SQL dễ đọc:

```sql
WITH paid_orders AS (
    SELECT *
    FROM plan_orders
    WHERE status = 'PAID'
)
SELECT customer_id, COUNT(*)
FROM paid_orders
GROUP BY customer_id;
```

Nhưng không được mặc định:

> “CTE luôn tạo bảng tạm và database luôn chạy CTE trước.”

Trong PostgreSQL hiện đại, một CTE SELECT không đệ quy, không có tác dụng phụ có thể được **inline/fold** trong những tình huống nhất định, tùy số lần tham chiếu và các điều kiện.

### 27.1. MATERIALIZED và NOT MATERIALIZED

PostgreSQL hỗ trợ dạng:

```sql
WITH paid_orders AS MATERIALIZED (
    SELECT *
    FROM plan_orders
    WHERE status = 'PAID'
)
SELECT COUNT(*)
FROM paid_orders;
```

và khi phù hợp:

```sql
WITH paid_orders AS NOT MATERIALIZED (
    SELECT *
    FROM plan_orders
    WHERE status = 'PAID'
)
SELECT COUNT(*)
FROM paid_orders;
```

Chúng có thể ảnh hưởng cách tối ưu và chia sẻ kết quả CTE, không phải cú pháp dùng để “bắt buộc nhanh hơn”.

### 27.2. Đọc plan thay vì đoán về CTE

Dùng `EXPLAIN` để xem:

- Có `CTE Scan` không?
- Điều kiện lọc được đẩy xuống đâu?
- Có bước materialization đáng kể không?
- Số hàng ở CTE có quá lớn không?

Một CTE viết đẹp không nhất thiết thực thi rẻ; và một CTE dài không nhất thiết chậm.

### 27.3. Subquery có thể được biến đổi

Optimizer có thể biến đổi `EXISTS` thành semi join, đẩy điều kiện qua subquery hoặc tái sắp join khi ngữ nghĩa cho phép. Không kết luận “SQL có subquery nên chạy từng hàng” nếu chưa nhìn plan.

---

## 28. Phép thử đo trước/sau tối ưu: quy trình có kiểm soát

Khi phát hiện một query chậm, đừng sửa năm thứ cùng lúc rồi không biết thay đổi nào có tác dụng.

### Bước 1: Chốt query thật

Ghi lại:

- SQL và các parameter cụ thể.
- Số hàng kết quả kỳ vọng.
- Version/DBMS.
- Tình trạng index và thống kê.
- Dữ liệu/tải ở môi trường đo.

### Bước 2: Lấy baseline

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, total_amount
FROM plan_orders
WHERE customer_id = 42;
```

Ghi plan, execution time, buffers, actual rows.

### Bước 3: Xác định giả thuyết

Ví dụ:

> “Seq Scan đang đọc 60.000 đơn để lấy 12 đơn của một khách; index trên customer_id có thể giảm lượng trang cần đọc.”

### Bước 4: Thử đúng một thay đổi

```sql
CREATE INDEX plan_orders_customer_test_idx
ON plan_orders(customer_id);
```

Nếu index tương tự đã có, không tạo trùng.

### Bước 5: Đo lại

Chạy lại với **cùng tham số**, so:

- Plan thay đổi ra sao?
- Tổng thời gian nhanh hơn trong nhiều lần chạy không?
- Shared read/hit thay đổi thế nào?
- Có tăng chi phí của workload ghi khác không?

### Bước 6: Kiểm tra tác động hệ thống

Một index giúp SELECT nhanh nhưng có thể làm INSERT hàng loạt chậm hơn hoặc tốn dung lượng. Cân bằng theo workload, không theo một query đơn lẻ.

### 28.1. Vì sao nên chạy nhiều lần?

Lần đầu dữ liệu có thể còn lạnh ở buffer/cache, lần sau đã nóng. Background load, CPU scheduling và I/O khác nhau cũng làm thời gian dao động.

Nên ghi nhiều phép đo trong điều kiện tương đồng và so xu hướng. Không khẳng định cải thiện 5% nếu chênh lệch nhỏ hơn biến động thông thường.

### 28.2. Tránh chỉ tập trung vào execution time

Có thể một query nhanh hơn khi cache nóng nhưng đọc nhiều page hơn, gây áp lực I/O cho workload đồng thời. Đo cả buffers, CPU khi có thể, concurrency và tần suất chạy.

---

## 29. SQL Server: Estimated Execution Plan và Actual Execution Plan

SQL Server có công cụ kế hoạch thực thi rất phát triển trong SQL Server Management Studio (SSMS).

Các cách thông dụng trong SSMS:

- **Display Estimated Execution Plan** (thường là Ctrl+L): lấy plan dự đoán, không thực thi query được chọn.
- **Include Actual Execution Plan** (thường là Ctrl+M, sau đó Execute): thực thi query và hiển thị thông tin runtime của kế hoạch.
- Truy vấn DMVs và Query Store khi cần quan sát lịch sử workload.

### 29.1. Operator tương ứng

| SQL Server operator | Ý nghĩa gần với PostgreSQL |
| --- | --- |
| Table Scan | Đọc dữ liệu dạng quét |
| Clustered Index Scan | Quét cấu trúc clustered index |
| Clustered Index Seek | Tìm theo khóa của clustered index |
| Index Seek | Tìm theo nonclustered index |
| Key Lookup | Tra bảng/clustered index để lấy cột còn thiếu sau một index seek |
| Nested Loops | Nested Loop Join |
| Hash Match | Hash Join hoặc hash aggregate tùy ngữ cảnh |
| Merge Join | Merge Join |
| Sort | Sắp xếp |
| Stream Aggregate | Aggregate trên đầu vào phù hợp thứ tự |
| Hash Match (Aggregate) | Aggregate dựa hash |
| Parallelism | Trao đổi dữ liệu giữa các worker |

**Không coi tên operator tương đương từng chi tiết giữa hai engine.** SQL Server có khái niệm clustered index, key lookup và execution properties riêng.

### 29.2. Estimated Rows và Actual Rows

Trong actual plan, xem số hàng dự đoán và thực tế tại operator. Sai lệch lớn có thể dẫn tới:

- Chọn join không phù hợp.
- Memory grant thiếu hoặc thừa.
- Nhiều key lookup lặp lại.
- Sort/hash spill.

Đây là nguyên tắc tương tự PostgreSQL, dù UI và cơ chế optimizer khác.

### 29.3. Estimated Subtree Cost không phải thời gian thực

Trong SSMS, các phần trăm “cost” trên operator thường dựa trên **chi phí ước lượng tương đối**. Không được kết luận “operator chiếm 80% cost chắc chắn chiếm 80% thời gian thực”.

Dùng runtime stats, actual rows, reads, CPU và duration để xác định nguyên nhân.

## 30. SQL Server: SHOWPLAN_XML và STATISTICS IO/TIME

Để xem kế hoạch ước lượng dạng XML:

```sql
SET SHOWPLAN_XML ON;
GO

SELECT
    order_id,
    customer_id,
    amount
FROM dbo.orders
WHERE customer_id = 42;
GO

SET SHOWPLAN_XML OFF;
GO
```

Đây là ví dụ cho **SSMS/sqlcmd**; `GO` là **dấu phân chia batch của client**, không phải lệnh T-SQL mà JDBC tự hiểu.

Khi `SHOWPLAN_XML ON`, SQL Server trả kế hoạch thay vì thực thi câu truy vấn được yêu cầu trong batch phù hợp.

### 30.1. STATISTICS IO

```sql
SET STATISTICS IO ON;

SELECT
    order_id,
    customer_id,
    amount
FROM dbo.orders
WHERE customer_id = 42;

SET STATISTICS IO OFF;
```

Dữ liệu `STATISTICS IO` giúp xem logical reads, physical reads và các số liệu theo bảng/đối tượng liên quan.

### 30.2. STATISTICS TIME

```sql
SET STATISTICS TIME ON;

SELECT
    order_id,
    customer_id,
    amount
FROM dbo.orders
WHERE customer_id = 42;

SET STATISTICS TIME OFF;
```

Hữu ích để xem các số liệu CPU và elapsed time trong những tình huống phù hợp.

### 30.3. Kết hợp với Actual Execution Plan

Để điều tra sâu:

1. Lấy actual execution plan.
2. Xem estimated vs actual rows ở operator.
3. Xem index seek/scan và key lookups.
4. Xem memory grant, spills/warnings.
5. Xem `STATISTICS IO` và `STATISTICS TIME`.
6. Kiểm tra parameter values/plan cache nếu kết quả thay đổi theo tham số.

### 30.4. Parameter sniffing và plan cache

Một stored procedure có thể được tối ưu dựa trên giá trị parameter ở lúc compile/plan. Nếu dữ liệu phân bố lệch, cùng plan cache có thể phù hợp một parameter nhưng chậm với parameter khác.

Đừng vội thêm index chỉ vì một lần chạy stored procedure chậm: cần xem plan được tái sử dụng, actual parameter và phân bố dữ liệu.

---

## 31. MySQL: EXPLAIN bảng truyền thống

MySQL hỗ trợ:

```sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    amount
FROM orders
WHERE customer_id = 42;
```

Một bảng `EXPLAIN` thường chứa các cột như:

| Cột | Ý nghĩa |
| --- | --- |
| `id` | Định danh thành phần SELECT trong plan |
| `select_type` | Loại SELECT theo cách biểu diễn của MySQL |
| `table` | Bảng/nguồn được xử lý |
| `type` | Kiểu truy cập, ví dụ `ALL`, `range`, `ref`, `eq_ref`, `const` |
| `possible_keys` | Các index có thể được cân nhắc |
| `key` | Index được chọn khi có |
| `key_len` | Độ dài khóa index được sử dụng theo cách MySQL báo |
| `ref` | Cột/hằng dùng với key |
| `rows` | Số hàng ước lượng cần xem xét ở bước tương ứng |
| `filtered` | Tỷ lệ phần trăm ước lượng còn lại sau điều kiện lọc |
| `Extra` | Thông tin bổ sung, ví dụ filter/sort/temp/index coverage |

### 31.1. type=ALL

Thường biểu thị quét toàn bảng; gần về ý tưởng với `Seq Scan` nhưng không đồng nhất chi tiết với PostgreSQL.

### 31.2. type=ref / eq_ref

Thường thể hiện truy cập theo index có quan hệ với hằng hoặc cột join. `eq_ref` thường gắn với phép tra theo unique/primary key khi phù hợp.

### 31.3. type=range

Thường biểu thị đọc một hoặc nhiều khoảng index, ví dụ:

```sql
WHERE ordered_at >= '2026-05-01'
  AND ordered_at < '2026-06-01'
```

nếu có index thích hợp và optimizer chọn dùng.

### 31.4. possible_keys khác key

Có index trong `possible_keys` **không nghĩa optimizer đã dùng nó**. Xem `key` và đường đi được mô tả.

### 31.5. Extra: Using filesort

`Using filesort` cho biết MySQL dùng một thuật toán sắp xếp ngoài thứ tự index phù hợp. **Không có nghĩa chắc chắn đã sort trên đĩa**; đây là tên cơ chế của MySQL, có thể sử dụng bộ nhớ.

`Using temporary` cũng là tín hiệu để xem cấu trúc truy vấn và phép xử lý trung gian, không tự động chứng minh lỗi.

## 32. MySQL: FORMAT=JSON và EXPLAIN ANALYZE

MySQL có thể xuất JSON:

```sql
EXPLAIN FORMAT=JSON
SELECT
    order_id,
    customer_id,
    amount
FROM orders
WHERE customer_id = 42;
```

Với MySQL **8.0.18 trở lên**, `EXPLAIN ANALYZE` cho những câu truy vấn được hỗ trợ **thực thi truy vấn** và cung cấp số liệu runtime, thường theo biểu diễn dạng cây.

```sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    amount
FROM orders
WHERE customer_id = 42;
```

Một phần output minh họa:

```text
-> Index lookup on orders using idx_customer
   (customer_id=42)
   (cost=... rows=...)
   (actual time=... rows=... loops=...)
```

### 32.1. EXPLAIN ANALYZE không chỉ “giải thích”

Nó **chạy query** để đo. Đừng áp dụng nguyên từ khóa hoặc quy tắc cho câu UPDATE/DELETE trên mọi version MySQL mà chưa đọc tài liệu của đúng câu lệnh được hỗ trợ.

### 32.2. So sánh các trường theo ngữ nghĩa MySQL

Mặc dù output có `cost`, `rows`, `actual time`, `loops` tương tự khái niệm PostgreSQL, cách optimizer tính và cơ chế báo số liệu **khác nhau**. Không so trực tiếp “cost 100 ở PostgreSQL” với “cost 100 ở MySQL”.

### 32.3. MariaDB không giống mọi cú pháp MySQL

MariaDB có những lệnh phân tích thực thi như `ANALYZE FORMAT=JSON SELECT ...` theo phiên bản, nhưng cú pháp và cấu trúc output khác MySQL.

Nếu làm việc với cả hai, xem đúng tài liệu sản phẩm; không giả định `EXPLAIN ANALYZE` là một giao diện hoàn toàn thống nhất.

---

## 33. SQLite: EXPLAIN QUERY PLAN

SQLite có cách xem plan tương đối gọn:

```sql
EXPLAIN QUERY PLAN
SELECT
    order_id,
    customer_id,
    amount
FROM orders
WHERE customer_id = 42;
```

Các dòng thường có cột mô tả `detail`, ví dụ minh họa:

```text
SCAN orders
```

hoặc khi có index thích hợp:

```text
SEARCH orders USING INDEX idx_orders_customer
  (customer_id=?)
```

### 33.1. SCAN và SEARCH

- `SCAN`: thường đọc một tập hàng theo đường quét.
- `SEARCH`: thường tìm các hàng theo điều kiện thông qua index/đường truy cập phù hợp.

Chú ý `SCAN` cũng có thể xuất hiện khi SQLite **quét index**, không nhất thiết lúc nào cũng quét bảng.

### 33.2. USE TEMP B-TREE FOR ORDER BY

Nếu query cần sắp xếp mà không thể tận dụng thứ tự index, SQLite có thể báo:

```text
USE TEMP B-TREE FOR ORDER BY
```

Đó là dấu hiệu để xem `ORDER BY`, index và kích thước kết quả.

Tương tự có thể gặp thông tin về `GROUP BY`/`DISTINCT` khi cần cấu trúc tạm.

### 33.3. EXPLAIN khác EXPLAIN QUERY PLAN

SQLite:

```sql
EXPLAIN
SELECT ...
```

có thể trả **opcode của máy ảo SQLite**, chi tiết hơn và khác hẳn cây plan cấp cao.

Để bắt đầu đọc hướng truy cập index, nên dùng:

```sql
EXPLAIN QUERY PLAN
SELECT ...
```

### 33.4. Dạng output không phải API bất biến

SQLite cảnh báo hình thức output `EXPLAIN QUERY PLAN` có thể thay đổi giữa phiên bản. Đừng viết hệ thống parser dài hạn dựa vào đúng chuỗi mô tả của từng bản SQLite mà không có cơ chế tương thích.

### 33.5. Thống kê SQLite

`ANALYZE` và các cơ chế như `PRAGMA optimize` theo phiên bản có thể giúp optimizer có thông tin phù hợp. Không copy `ANALYZE plan_orders` của PostgreSQL và kết luận mọi DBMS dùng cùng metadata.

## 34. Oracle: EXPLAIN PLAN và DBMS_XPLAN

Oracle có:

```sql
EXPLAIN PLAN FOR
SELECT
    order_id,
    customer_id,
    amount
FROM orders
WHERE customer_id = 42;
```

Sau đó xem kế hoạch ước lượng:

```sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Dạng output thường có các cột như:

- `Id`.
- `Operation`.
- `Name`.
- `Rows`.
- `Bytes`.
- `Cost`.
- `Time` ước lượng khi có.

### 34.1. EXPLAIN PLAN không nhất thiết là plan đã chạy thật

Plan ước lượng từ `EXPLAIN PLAN` có thể khác plan thực tế của câu chạy, đặc biệt khi bind values, adaptive features hoặc điều kiện phiên làm việc ảnh hưởng quá trình chọn plan.

Nếu cần điều tra query thật, Oracle có các khả năng xem **cursor thực thi** và số liệu tại runtime.

### 34.2. DBMS_XPLAN.DISPLAY_CURSOR

Một ví dụ Oracle khi đã bật thu thập thống kê plan phù hợp:

```sql
SELECT /*+ gather_plan_statistics */
    order_id,
    customer_id,
    amount
FROM orders
WHERE customer_id = 42;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

`ALLSTATS LAST` có thể hiển thị thông tin như **E-Rows** (estimated rows) và **A-Rows** (actual rows) khi số liệu plan statistics có sẵn và cursor phù hợp được chọn.

**Thực tế vận hành:** Nếu có nhiều SQL chạy xen giữa hoặc công cụ client phát thêm câu lệnh, tham số cursor mặc định có thể không trỏ đúng câu bạn muốn. Khi cần chắc chắn, dùng `SQL_ID`/child cursor tương ứng và quyền phù hợp.

### 34.3. Các dấu hiệu đáng chú ý

- `TABLE ACCESS FULL`: quét bảng.
- `INDEX RANGE SCAN`: đọc khoảng index.
- `INDEX UNIQUE SCAN`: tra unique index.
- `NESTED LOOPS`, `HASH JOIN`, `MERGE JOIN`.
- `SORT GROUP BY` hoặc `HASH GROUP BY`.

Tên operator khác PostgreSQL nhưng tư duy đọc **ước lượng hàng, số hàng thực tế, đường đọc dữ liệu và join** vẫn áp dụng.

### 34.4. Cost của Oracle cũng không phải thời gian thực

Oracle cost là giá trị do optimizer tính theo mô hình của Oracle, không so số tuyệt đối trực tiếp với cost của PostgreSQL hoặc MySQL.

---

## 35. Bảng đối chiếu nhanh công cụ giữa các DBMS

| Nhu cầu | PostgreSQL | MySQL 8+ | SQL Server | SQLite | Oracle |
| --- | --- | --- | --- | --- | --- |
| Plan ước lượng | `EXPLAIN SELECT` | `EXPLAIN SELECT` | Estimated Execution Plan / `SHOWPLAN_XML` | `EXPLAIN QUERY PLAN` | `EXPLAIN PLAN FOR` |
| Plan có số liệu thực | `EXPLAIN ANALYZE` | `EXPLAIN ANALYZE` (phiên bản hỗ trợ) | Actual Execution Plan | Không có cùng giao diện tích hợp tương đương chung | `DBMS_XPLAN.DISPLAY_CURSOR` với runtime stats |
| Plan dạng cấu trúc | `FORMAT JSON` | `FORMAT=JSON` | Showplan XML | Bảng EQP hoặc opcode EXPLAIN | DBMS_XPLAN/cursor metadata |
| Logical reads/buffers | `BUFFERS` | Theo số liệu/công cụ engine | `STATISTICS IO` và plan | Công cụ đo/phân tích khác | Buffer gets qua runtime stats |
| CPU/thời gian | `ANALYZE`, I/O timing phù hợp | `EXPLAIN ANALYZE`, Performance Schema | `STATISTICS TIME`, actual plan, Query Store | Đo query từ app/tool | Runtime stats, SQL Monitor/AWR theo quyền |
| Thống kê optimizer | `ANALYZE` | `ANALYZE TABLE` | Auto/update statistics | `ANALYZE`/`PRAGMA optimize` | `DBMS_STATS` |
| Tìm index đang dùng | `Index Scan`/`Index Cond` | `key`/`type` | Index Seek/Scan/Lookup | `SEARCH ... USING INDEX` | INDEX ... SCAN |

**Nguyên tắc chung:** Có thể chuyển kiến thức **đọc cây và so ước lượng–thực tế** giữa các DBMS, nhưng không chuyển cơ học cú pháp, tên operator hay cost units.

## 36. Kế hoạch tốt trên máy thử chưa chắc tốt trên production

Có nhiều khác biệt:

- Bảng production lớn hơn hàng nghìn lần.
- Dữ liệu lệch vùng/tenant hoặc có “khách lớn” đặc biệt.
- Index khác nhau.
- Thống kê khác nhau.
- RAM, storage, CPU và concurrency khác nhau.
- Query parameter khác nhau.
- Partition, RLS, trigger, computed columns khác nhau.
- Transaction isolation và workload ghi khác nhau.

### 36.1. Một parameter hiếm và một parameter phổ biến

Ví dụ production:

```sql
WHERE tenant_id = :tenant_id
```

Nếu một tenant có 10 hàng và một tenant có 10 triệu hàng, hai giá trị có thể cần kế hoạch khác nhau.

Đo plan với **tham số đại diện cho từng phân khúc**, không chỉ một trường hợp nhẹ.

### 36.2. Index trong bài học không phải khuyến nghị tạo hết

Bài đưa nhiều câu `CREATE INDEX` để minh họa các khả năng. **Không nên tạo tất cả index đó trên một bảng production** chỉ vì chúng xuất hiện trong bài.

Chọn index dựa trên workload, ghi/đọc, storage và kết quả đo.

### 36.3. Tối ưu một query có thể làm query khác chậm

Ví dụ một index mới có thể đẩy query A sang index scan nhanh hơn nhưng làm INSERT hàng loạt tốn thêm chi phí. Cần nhìn toàn bộ hệ thống.

---

## 37. Những dấu hiệu trên plan đáng điều tra đầu tiên

| Dấu hiệu | Có thể liên quan tới | Hướng xem tiếp |
| --- | --- | --- |
| `Seq Scan` lớn, filter loại gần hết hàng | Thiếu index phù hợp hoặc điều kiện không tận dụng index | Selectivity, index, sargability, thời gian và buffers |
| `Index Scan` vẫn đọc rất nhiều heap page | Index không đủ chọn lọc hoặc cần cột ngoài index | Covering/composite index, selectivity |
| `Index Only Scan` có `Heap Fetches` cao | Visibility map/MVCC hoặc điều kiện dữ liệu | VACUUM/maintenance, heap fetches |
| Nested Loop phía trong có `loops` rất lớn | Hàng phía ngoài nhiều, tra phía trong lặp | Join cardinality, index phía trong, thuật toán khác |
| Estimate 10 nhưng actual 1.000.000 | Thống kê lệch, tương quan hoặc query shape | `ANALYZE`, extended stats, parameter |
| Sort có `external merge Disk` | Sort spill | Dữ liệu đầu vào, index thứ tự, `work_mem` |
| Hash có nhiều batches/disk | Hash spill, memory | Cardinality, hash input, memory và query |
| `Rows Removed by Filter` lớn | Đọc nhiều ứng viên rồi loại | Điều kiện và index |
| `Rows Removed by Index Recheck` lớn | Lossy bitmap/recheck | Bitmap memory, độ chọn lọc |
| `Buffers shared read` nhiều | Nạp nhiều trang vào shared buffers | Warm/cold cache, đường đọc, dữ liệu |
| `Gather` và `Workers Launched` ít hơn dự kiến | Thiếu worker/tải hệ thống | Cấu hình, concurrency, resource |
| Planning Time lớn so với Execution Time | Planning/phức tạp query | Query simplification, reuse plan khi hợp lý |
| Một Query có Execution Time thấp nhưng ứng dụng chậm | Ngoài server execution | Network, transfer, ORM, client, lock wait, pool |
| Query chạy nhanh lần hai nhưng chậm lần đầu | Cache/đọc dữ liệu | Buffers, reads, kiểm tra nhiều lần |
| `LIMIT 20` nhưng child đọc rất nhiều hàng | Sort hoặc OFFSET sâu | Index cho order, keyset pagination |

**Chẩn đoán theo bằng chứng:** Những dấu hiệu trên là **gợi ý điều tra**, không phải bản án rằng plan đang sai.

## 38. Lỗi thường gặp khi đọc EXPLAIN

### 38.1. Coi cost là mili giây

Sai: “cost=500 chắc chạy 500 ms”.

Đúng: cost là **đơn vị mô hình optimizer**; muốn biết thực tế phải đo runtime.

### 38.2. Coi Seq Scan là lỗi tuyệt đối

Sai: “Query có Seq Scan thì phải tạo index”.

Đúng: quét tuần tự có thể là lựa chọn tốt khi lấy phần lớn bảng hoặc bảng rất nhỏ.

### 38.3. Chỉ nhìn node gốc

Sai: “Aggregate chậm vì nó ở trên cùng”.

Đúng: xem node con, số hàng đầu vào, buffers và phép toán nào thực sự tiêu tốn công việc.

### 38.4. Cộng thời gian các node

Sai: “A mất 5 ms, B mất 5 ms nên query mất 10 ms”.

Đúng: node có quan hệ cha–con, thời gian có thể bao gồm con; parallel và loops làm phép cộng không hợp lệ.

### 38.5. Không nhân loops khi đọc node trong

Sai: “Node chỉ 0,05 ms nên không quan trọng”.

Đúng: nếu nó chạy 50.000 vòng thì phải xem tổng khối lượng công việc.

### 38.6. Dùng EXPLAIN ANALYZE DELETE trên production để “chỉ xem”

Sai: nó **thực hiện DELETE**.

Đúng: chỉ dùng `EXPLAIN` nếu chưa muốn thực thi; đo DML chỉ khi được phép và có cơ chế an toàn.

### 38.7. Không đo sau khi thêm index

Sai: “Index tạo thành công nghĩa là query đã nhanh”.

Đúng: so plan, runtime, buffers và tác động workload.

### 38.8. Ép dùng index bằng mọi giá

Sai: “Index Seek/Index Scan luôn nhanh hơn Table Scan”.

Đúng: random I/O nhiều, key lookup lặp và tập dữ liệu lớn có thể khiến index chậm hơn.

### 38.9. Bỏ qua sai số ước lượng

Sai: “Estimated rows rất nhỏ nên Nested Loop chắc tốt”.

Đúng: xem Actual Rows, đặc biệt ở chỗ dữ liệu nhân qua join.

### 38.10. So cost giữa các DBMS

Sai: “PostgreSQL cost 100 tốt hơn MySQL cost 200”.

Đúng: hai cost model khác nhau; so hiệu năng thực tế trong điều kiện tương đương.

### 38.11. Coi index tồn tại là optimizer bắt buộc dùng

Sai: “Đã có index nhưng plan không dùng, vậy optimizer hỏng”.

Đúng: có thể index không phù hợp, filter quá rộng, thống kê sai hoặc đường scan rẻ hơn.

### 38.12. Chạy một lần rồi kết luận

Sai: “Bản mới nhanh hơn 2 ms ở một lần chạy nên chắc chắn tốt hơn”.

Đúng: đo nhiều lần, xét cache/tải và tác động concurrency.

---

## 39. Bài tập thực hành có hướng dẫn

Các bài PostgreSQL dùng hai bảng `plan_customers` và `plan_orders` của mục 4. Các kết quả plan có thể thay đổi theo máy, nên bài tập ưu tiên **cách đọc và giải thích** thay vì yêu cầu chuỗi output y hệt.

### Bài 1. Lấy kế hoạch ước lượng

**Yêu cầu:** In kế hoạch của câu tìm đơn khách 42 mà không thực thi SELECT để đo.

```sql
EXPLAIN
SELECT order_id, total_amount
FROM plan_orders
WHERE customer_id = 42;
```

**Gợi ý đọc:** xem loại scan, `rows` ước lượng và `Filter`/`Index Cond`.

### Bài 2. Đo thời gian và buffers

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM plan_orders
WHERE customer_id = 42;
```

**Gợi ý đọc:** so `rows` ước lượng với `actual rows`, xem `Execution Time` và `shared hit/read`.

### Bài 3. Số đơn của khách 42

Bộ dữ liệu tạo 60.000 đơn chia cho 5.000 khách theo công thức vòng tròn.

**Đáp án:** mỗi khách có **12 đơn**, nên khách 42 có 12 hàng trước các điều kiện status/date khác.

### Bài 4. 60.000 hàng nhưng chỉ trả 12 hàng

Một Seq Scan đọc bảng 60.000 đơn và lọc `customer_id=42`.

**Câu hỏi:** khoảng bao nhiêu hàng bị loại tại filter?

**Đáp án:** `60000 - 12 = 59988`, nếu quét đúng toàn bộ bảng và không có điều kiện khác hoặc tối ưu dừng sớm. Đây là ví dụ về một filter rất chọn lọc.

### Bài 5. Chọn index cho truy vấn theo khách

```sql
CREATE INDEX plan_orders_customer_practice_idx
ON plan_orders(customer_id);
```

**Gợi ý:** chạy `EXPLAIN (ANALYZE, BUFFERS)` trước và sau, so `Index Cond`, buffers và thời gian. Nếu đã tạo index trên customer_id ở bài trước thì không tạo trùng.

### Bài 6. Vì sao Index Scan không xuất hiện?

**Câu hỏi:** đã tạo index trên `status` nhưng query `WHERE status='PAID'` vẫn dùng Seq Scan.

**Đáp án:** khoảng 60% đơn là PAID; Seq Scan có thể được optimizer đánh giá rẻ hơn dùng index + đọc nhiều hàng. Cần đo, không coi đó tự động là lỗi.

### Bài 7. Đọc cost

```text
Index Scan ... (cost=0.29..18.00 rows=12 width=24)
```

**Câu hỏi:** 18.00 có phải 18 ms không?

**Đáp án:** không. Đây là tổng **estimated cost** theo mô hình PostgreSQL.

### Bài 8. Đọc rows và loops

```text
(actual time=0.010..0.020 rows=4 loops=250)
```

**Câu hỏi:** node đã xuất xấp xỉ bao nhiêu hàng trong mọi vòng?

**Đáp án:** khoảng `4 × 250 = 1000` hàng; có thể sai khác nhỏ do `rows` làm tròn trung bình.

### Bài 9. So estimate và actual

```text
(cost=... rows=5 ...)
(actual time=... rows=5000 loops=1)
```

**Câu hỏi:** nên điều tra gì?

**Đáp án:** ước lượng lệch cỡ **1000 lần**. Kiểm tra thống kê, phân bố dữ liệu, correlation, predicate và cách join/filter dẫn tới node.

### Bài 10. Đọc index condition

```text
Index Scan ...
  Index Cond: (customer_id = 42)
  Filter: (total_amount > 500)
```

**Đáp án:** index giúp chọn theo `customer_id`; điều kiện tiền được kiểm tra bổ sung tại node. Không có nghĩa index không hoạt động.

### Bài 11. Tối ưu ORDER BY LIMIT

**Yêu cầu:**

```sql
SELECT order_id, ordered_at
FROM plan_orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 5;
```

**Gợi ý index:**

```sql
CREATE INDEX plan_orders_customer_sort_practice_idx
ON plan_orders(
    customer_id,
    ordered_at DESC,
    order_id DESC
);
```

**Đáp án định hướng:** có thể tránh một node Sort riêng khi optimizer chọn đường index có thứ tự phù hợp.

### Bài 12. External merge Disk là gì?

```text
Sort Method: external merge  Disk: 8192kB
```

**Đáp án:** thao tác sort đã cần dùng dữ liệu tạm trên đĩa theo cơ chế sort, đáng kiểm tra nếu tốn thời gian. Không kết luận phải tăng `work_mem` toàn hệ ngay.

### Bài 13. Nested Loop nhỏ hay lớn?

```text
Nested Loop
  -> ... (actual rows=1 loops=1)
  -> Index Scan ... (actual rows=12 loops=1)
```

**Đáp án:** ví dụ này rất nhỏ, Nested Loop có thể hoàn toàn hợp lý. Không thể kết luận chỉ từ tên operator rằng nó chậm.

### Bài 14. Nested Loop gọi phía trong quá nhiều

```text
Nested Loop
  -> ... (actual rows=100000 loops=1)
  -> Index Scan ... (actual rows=1 loops=100000)
```

**Đáp án:** có khoảng 100.000 lần gọi phía trong. Hãy xem tổng I/O, thời gian, estimate, số trang cần truy cập và liệu thuật toán join khác có phù hợp.

### Bài 15. Phân biệt Hash Join và HashAggregate

**Đáp án:** `Hash Join` dùng hash để **ghép hai nguồn** theo điều kiện phù hợp; `HashAggregate` dùng hash để **tổng hợp theo nhóm**. Cùng chữ Hash nhưng chức năng khác nhau.

### Bài 16. DML và EXPLAIN ANALYZE

**Câu hỏi:** có an toàn để chạy `EXPLAIN ANALYZE DELETE FROM plan_orders` trên bảng thật vì nghĩ chỉ xem plan không?

**Đáp án:** không. Trên PostgreSQL, `EXPLAIN ANALYZE` **thực thi DELETE**. Dùng `EXPLAIN DELETE` để xem dự đoán; đo thực tế chỉ trong môi trường được phép, transaction phù hợp và hiểu side effects.

### Bài 17. Chọn index theo bộ lọc ngày

**Yêu cầu:**

```sql
SELECT COUNT(*)
FROM plan_orders
WHERE ordered_at >= TIMESTAMP '2026-05-01'
  AND ordered_at < TIMESTAMP '2026-06-01';
```

**Gợi ý:** thử index `(ordered_at)`; xem `Index Cond`, rows/buffers. Không cần index cho mọi cột chỉ vì nó được dùng trong WHERE.

### Bài 18. Vì sao DATE(ordered_at) có thể bất lợi?

**Đáp án:** một B-tree index thông thường trên `ordered_at` có thể không được dùng như một range index khi lọc bằng biểu thức `DATE(ordered_at)`. Viết khoảng nửa mở hoặc cân nhắc expression index nếu workload yêu cầu.

### Bài 19. Index Only Scan có Heap Fetches khác 0

**Đáp án:** PostgreSQL vẫn có thể phải đọc heap để xác minh tính hiển thị MVCC khi visibility map chưa cho phép chỉ dựa trên index. `Index Only Scan` không cam kết **0 lần** truy cập heap.

### Bài 20. MySQL có possible_keys nhưng key là NULL

**Đáp án:** MySQL đã xem xét một số index tiềm năng nhưng không chọn index nào cho đường truy cập được báo ở bước đó. Xem `type`, `rows`, `Extra` và workload; không coi tên index ở `possible_keys` là đã dùng.

### Bài 21. SQL Server Estimated Cost 90%

**Câu hỏi:** một operator hiển thị 90% estimated cost. Nó chắc chiếm 90% thời gian query không?

**Đáp án:** không. Đó là ước lượng tương đối. Xem actual plan, actual rows, IO/time, spills và duration.

### Bài 22. SQLite SCAN và SEARCH

**Câu hỏi:** output `SEARCH orders USING INDEX ...` khác `SCAN orders` ở điểm nào?

**Đáp án:** `SEARCH` thường biểu diễn việc tìm các hàng theo điều kiện/đường index; `SCAN` là quét một tập dữ liệu. Nhưng SQLite có thể quét index và vẫn gọi là `SCAN`; đọc hết chi tiết output.

### Bài 23. Oracle E-Rows và A-Rows

**Câu hỏi:** E-Rows=10 nhưng A-Rows=100000 trong runtime plan gợi ý gì?

**Đáp án:** cardinality estimation lệch lớn. Xem thống kê, bind values, correlation, join/filter và plan thực thi thực tế.

### Bài 24. Vì sao EXPLAIN ANALYZE nhanh hơn lần hai?

**Đáp án:** dữ liệu có thể đã nằm trong cache, môi trường/tải thay đổi hoặc kế hoạch được chuẩn bị khác. Đo lại nhiều lần và quan sát buffer reads; không kết luận từ một lần đo.

### Bài 25. Đọc một plan tổng hợp

Cho cây:

```text
Sort
  -> HashAggregate
       -> Hash Join
            -> Seq Scan plan_orders
            -> Hash
                 -> Seq Scan plan_customers
```

**Câu hỏi:** bước nào đang đếm theo nhóm? Bước nào nối dữ liệu? Bước nào sắp kết quả?

**Đáp án:**

- `HashAggregate`: tổng hợp theo nhóm.
- `Hash Join`: nối đơn với khách.
- `Sort`: sắp kết quả.
- `Seq Scan`: đọc từng bảng.
- `Hash`: xây cấu trúc cho phía join.

Để biết chậm ở đâu, cần **actual time, actual rows, loops và buffers** chứ không chỉ tên operator.

---

## 40. Một quy trình thực chiến khi nhận ticket “SQL chạy chậm”

### Bước 1 — Xác định truy vấn và triệu chứng

- Câu SQL cụ thể.
- Tham số thực tế.
- Thời gian chậm xảy ra.
- Môi trường và phiên bản.
- Số hàng trả về.
- Có chờ lock, queue hoặc network không?

### Bước 2 — Chọn công cụ đúng rủi ro

- PostgreSQL: `EXPLAIN` trước; `EXPLAIN (ANALYZE, BUFFERS)` cho SELECT an toàn khi được phép.
- SQL Server: Estimated/Actual Execution Plan, `STATISTICS IO/TIME`.
- MySQL: `EXPLAIN`, `FORMAT=JSON`, `EXPLAIN ANALYZE` phiên bản hỗ trợ.
- SQLite: `EXPLAIN QUERY PLAN`.
- Oracle: `EXPLAIN PLAN`, runtime cursor qua `DBMS_XPLAN`.

### Bước 3 — Tìm sai số hàng đầu tiên

Đi từ node lá lên:

- Estimate và actual có phù hợp không?
- Join có làm nổ số hàng không?
- Có filter quá muộn không?
- Thống kê có cũ không?

### Bước 4 — Tìm thao tác tốn tài nguyên

Xem:

- Scan lớn.
- Nhiều loops.
- Sort/hash spill.
- Key lookup/heap fetches.
- Buffers và I/O.
- Concurrency/lock wait nếu DBMS/công cụ có thông tin.

### Bước 5 — Đề xuất một thay đổi có lý do

Ví dụ:

- Index phù hợp.
- Điều kiện sargable.
- Tách/chọn đúng grain trước join.
- Cập nhật thống kê.
- Tránh OFFSET sâu.
- Tổng hợp hoặc materialize có kiểm soát.
- Sửa query logic để giữ nguyên ngữ nghĩa nhưng giảm dữ liệu trung gian.

### Bước 6 — Đo và kiểm tra kết quả

- Kết quả nghiệp vụ không đổi nếu đây là tối ưu tương đương.
- Plan có thực sự thay không?
- Thời gian, buffers/reads có cải thiện ổn định không?
- Ghi/đồng thời và storage có bị ảnh hưởng không?
- Rollback/phương án bỏ thay đổi có sẵn không?

Một đề xuất index nên nói được:

> “Truy vấn lấy khoảng 12 đơn của một khách nhưng đang quét 60.000 đơn. Tôi đề xuất index theo customer_id, sẽ đo lại plan, số buffer và thời gian, sau đó đánh giá chi phí ghi.”

Thay vì:

> “Thêm index vì EXPLAIN có Seq Scan.”

---

## 41. Checklist đọc EXPLAIN trước khi kết luận

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Có chạy truy vấn thực hay chỉ lấy plan? | Phân biệt `EXPLAIN` và `EXPLAIN ANALYZE` |
| Node gốc làm gì? | Xem `Limit`, `Sort`, `Aggregate`, `Join`... |
| Bảng được đọc theo đường nào? | `Seq Scan`, `Index Scan`, `Bitmap`, operator tương đương |
| Index có thật sự hạn chế phạm vi không? | `Index Cond`/`key`/Index Seek, không chỉ index tồn tại |
| Ước lượng đúng không? | Estimated rows so với actual rows |
| Node có bị chạy lặp lại nhiều không? | `loops` hoặc runtime execution count |
| Dữ liệu bị loại ở đâu? | `Filter`, rows removed |
| Join có nhân hàng quá nhiều không? | Rows ở đầu vào và đầu ra |
| Sort/hash có spill không? | Temp buffers, disk, sort/hash details |
| I/O có lớn không? | `BUFFERS`, `STATISTICS IO`, runtime IO |
| Query chậm do planning hay execution? | Planning Time/Execution Time hoặc số liệu tương ứng |
| Có parallelism không? | `Gather`, workers, exchange operators |
| Thống kê có phù hợp không? | `ANALYZE`, stats catalog, estimate mismatch |
| Cùng SQL có nhiều parameter không? | So plan của giá trị hiếm và phổ biến |
| Đã đo nhiều lần chưa? | Cache nóng/lạnh, background load |
| Thay đổi có giữ đúng kết quả không? | Kiểm chứng logic và dữ liệu trước/sau |
| Có rủi ro khi dùng actual plan không? | Actual plan có thể thực thi câu DML |
| Có cần ẩn dữ liệu trước khi chia sẻ plan không? | Literal/parameter/schema nhạy cảm |

## 42. Tóm tắt: đọc kế hoạch để đặt câu hỏi đúng

Nhìn một kế hoạch thực thi, hãy đọc theo chuỗi:

```text
SQL nghiệp vụ
   │
   ▼
EXPLAIN / công cụ tương đương
   │
   ▼
Cây operator: scan, join, sort, aggregate, limit
   │
   ▼
Estimated rows và cost
   │
   ▼
Actual rows, time, loops, buffers (nếu có)
   │
   ▼
Tìm chỗ ước lượng sai hoặc tốn tài nguyên
   │
   ▼
Giả thuyết tối ưu có cơ sở
   │
   ▼
Đo lại + kiểm chứng kết quả + đánh giá toàn workload
```

Bốn ý nên ghi nhớ nhất:

1. **`EXPLAIN` cho biết optimizer dự định làm gì; `EXPLAIN ANALYZE` đo việc thực thi thật trong các DBMS hỗ trợ.**
2. **Cost không phải mili giây; estimated rows không phải actual rows; loops có thể làm một node nhỏ trở nên rất tốn công.**
3. **`Seq Scan` không mặc nhiên xấu và `Index Scan` không mặc nhiên tốt.** Chọn đường truy cập dựa vào số hàng, I/O, thời gian và workload.
4. **Tối ưu hóa là quy trình đo lường.** Hiểu cây plan, tìm sai lệch, đặt giả thuyết, thử một thay đổi, đo lại và kiểm tra tính đúng của kết quả.

**Kết luận:** Kỹ năng đọc kế hoạch bằng `EXPLAIN` và các công cụ tương đương là cầu nối giữa việc **viết SQL đúng** và **vận hành SQL hiệu quả**. Thay vì đoán rằng cần thêm index, đổi JOIN hay tăng bộ nhớ, người học có thể nhìn thấy các bước truy cập dữ liệu, ước lượng của optimizer, số hàng thực, số lần lặp, sort/hash spill và hoạt động I/O. Khi đọc đúng những tín hiệu đó, mỗi quyết định tối ưu đều có nguyên nhân rõ ràng, có phép đo trước/sau và có cách kiểm chứng rằng truy vấn vẫn trả kết quả nghiệp vụ mong muốn.

# Sort, incremental sort, aggregate và bộ nhớ tạm trong PostgreSQL

Một truy vấn PostgreSQL có thể đọc dữ liệu rất nhanh nhưng vẫn mất nhiều thời gian ở giai đoạn **sắp xếp**, **gom nhóm**, **tính aggregate** hoặc **ghi dữ liệu trung gian ra đĩa**.

Ví dụ ứng dụng cần hiển thị doanh thu theo khách hàng:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY total_amount DESC
LIMIT 20;
```

Trong câu SQL ngắn này, PostgreSQL có thể phải:

1. Tìm và lọc các hàng có `status='PAID'`.
2. Gom những hàng cùng `customer_id`.
3. Tính `COUNT` và `SUM`.
4. Sắp kết quả aggregate theo `total_amount DESC`.
5. Chỉ trả 20 nhóm có tổng cao nhất.

Tùy dữ liệu, index và cấu hình, kế hoạch truy vấn có thể chứa `HashAggregate`, `GroupAggregate`, `Sort`, `Incremental Sort`, `Gather Merge` hoặc các node xử lý trung gian khác. Nếu lượng dữ liệu không vừa trong ngân sách bộ nhớ của phép toán, PostgreSQL có thể dùng **temporary files** trên đĩa. Điều này thường làm tăng I/O và latency đáng kể.

Bài học này tập trung vào bốn vấn đề liên kết với nhau:

- **Sort** — sắp xếp dữ liệu và cách PostgreSQL chọn thuật toán.
- **Incremental Sort** — tận dụng tiền tố đã được sắp xếp để chỉ sắp tiếp phần còn lại.
- **Aggregate** — khác biệt giữa `HashAggregate`, `GroupAggregate`, partial/final aggregate và các phép tổng hợp đặc biệt.
- **Bộ nhớ tạm** — cách `work_mem`, `hash_mem_multiplier`, spill, temporary files và song song hóa ảnh hưởng tới truy vấn.

Mục tiêu không phải “luôn loại bỏ Sort” hay “cứ tăng work_mem thì nhanh”, mà là **đọc được bằng chứng từ execution plan, hiểu đánh đổi và chọn cách tối ưu có căn cứ**.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện các node `Sort`, `Incremental Sort`, `HashAggregate`, `GroupAggregate`, `Aggregate`, `Gather` và `Gather Merge` trong kế hoạch.
2. Phân biệt `Sort Key`, `Presorted Key`, thứ tự dữ liệu đầu vào và yêu cầu `ORDER BY` ở SQL.
3. Giải thích các dạng thực thi sort thường gặp: **quicksort**, **top-N heapsort**, **external merge**.
4. Hiểu vì sao `ORDER BY ... LIMIT` có thể dùng top-N sort thay vì sắp xếp toàn bộ tập kết quả.
5. Giải thích điều kiện và lợi ích của **Incremental Sort**; nhận biết trường hợp nó không có lợi.
6. Phân biệt **HashAggregate** và **GroupAggregate**, cùng rủi ro memory/spill của mỗi dạng.
7. Hiểu `work_mem` là ngân sách **cho từng phép toán liên quan**, không phải một giới hạn RAM duy nhất cho cả truy vấn hoặc session.
8. Phân biệt `work_mem` với `shared_buffers`, `temp_buffers` và `maintenance_work_mem`.
9. Phân tích ảnh hưởng của `hash_mem_multiplier` với những phép hash đủ điều kiện.
10. Đọc các dòng `Sort Method: ... Memory: ...`, `Disk: ...`, `Batches` và `Buffers: temp read/written`.
11. Theo dõi temp I/O qua `pg_stat_database`, `pg_stat_statements` (nếu bật), logging và những công cụ phù hợp.
12. Đánh giá vai trò của index B-tree, prefix order, collation, NULL placement và parallel execution.
13. Thiết kế lab có thể thử hai cấu hình `work_mem` bằng `SET LOCAL` và so sánh trên cùng một query.
14. Đề xuất cách tối ưu dựa trên dữ liệu, thống kê, SQL semantics và giới hạn bộ nhớ thực tế.

**Phạm vi:** PostgreSQL hiện đại; Incremental Sort có từ PostgreSQL 13. Chi tiết execution plan, memory accounting và tối ưu planner có thể khác giữa phiên bản. Lab chỉ dành cho database thử nghiệm; không biến các giá trị cấu hình minh họa thành khuyến nghị production.

---

## 2. Sắp xếp và tổng hợp xuất hiện ở đâu trong một truy vấn?

Nhìn câu SQL:

```sql
SELECT
    customer_id,
    COUNT(*) AS orders,
    SUM(amount) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) > 1000
ORDER BY revenue DESC
LIMIT 10;
```

Theo logic SQL, có thể suy nghĩ:

```text
FROM sales
    |
    v
WHERE status='PAID'
    |
    v
GROUP BY customer_id
    |
    v
COUNT, SUM
    |
    v
HAVING SUM(amount)>1000
    |
    v
ORDER BY revenue DESC
    |
    v
LIMIT 10
```

Đây là **thứ tự xử lý logic**, không phải danh sách node vật lý cố định.

Planner có thể biến phần nhóm thành `HashAggregate`, phần order thành `Sort`, hoặc dùng một luồng đã sắp từ index cho `GroupAggregate`. Với parallel execution, còn có thể dùng `Partial Aggregate` và `Finalize Aggregate`.

### 2.1. SQL không chỉ định thuật toán Sort/GroupAggregate

Câu:

```sql
GROUP BY customer_id
```

chỉ yêu cầu gom nhóm đúng. Nó không bắt PostgreSQL phải:

- Sort rồi tính aggregate.
- Hash rồi tính aggregate.
- Trả kết quả theo thứ tự customer_id.

Tương tự, `ORDER BY` là yêu cầu **về thứ tự kết quả**, không có nghĩa phải xuất hiện node `Sort`: nếu input đã có thứ tự phù hợp từ index hoặc plan khác, planner có thể tránh sắp lại.

### 2.2. Lược đồ các phương án

```text
                Dữ liệu đầu vào
                       |
        +--------------+----------------+
        |                               |
        v                               v
   Chưa có thứ tự                 Có thứ tự theo group key
        |                               |
   +----+------+                        |
   |           |                        |
   v           v                        v
HashAggregate  Sort                  GroupAggregate
   |           |                        |
   |           v                        |
   |      GroupAggregate                |
   +-----------+------------------------+
                       |
                       v
               ORDER BY tổng doanh thu
                       |
                     Sort
                       |
                     Limit
```

Tùy query, một nhánh có thể có nhiều node khác, hoặc planner loại bỏ giai đoạn không cần thiết.

---

## 3. Bộ dữ liệu thực hành tự chứa

Ta dùng bảng đơn hàng mô phỏng gồm khách hàng, khu vực, trạng thái, thời gian, tiền và sản phẩm.

> **Cảnh báo:** Các lệnh `DROP TABLE IF EXISTS` xóa bảng lab có cùng tên. Chỉ chạy trên database dành riêng cho thực hành, không phải production.

### 3.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS plan_memory_lab;

DROP TABLE IF EXISTS plan_memory_lab.sales;

CREATE TABLE plan_memory_lab.sales (
    sale_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELED')),
    product_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL
);
```

### 3.2. Nạp 80.000 hàng với dữ liệu tái tạo được

```sql
INSERT INTO plan_memory_lab.sales (
    customer_id, region, status, product_id, amount, created_at
)
SELECT
    ((g.n * 37) % 1000) + 1 AS customer_id,
    (ARRAY['north','south','east','west'])
        [((g.n * 7) % 4) + 1] AS region,
    CASE
        WHEN g.n % 10 < 6 THEN 'PAID'
        WHEN g.n % 10 < 9 THEN 'NEW'
        ELSE 'CANCELED'
    END AS status,
    ((g.n * 13) % 120) + 1 AS product_id,
    (((g.n * 89) % 250000)::NUMERIC / 100)::NUMERIC(12,2)
        AS amount,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n * INTERVAL '1 minute') AS created_at
FROM generate_series(1, 80000) AS g(n);

ANALYZE plan_memory_lab.sales;
```

Mục đích là có đủ hàng để quan sát Sort/HashAggregate, nhưng không quá lớn đối với môi trường lab thông thường. Mức tải thật phụ thuộc cấu hình máy.

### 3.3. Kiểm tra sơ bộ

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT customer_id) AS customer_count,
    MIN(created_at) AS first_time,
    MAX(created_at) AS last_time
FROM plan_memory_lab.sales;
```

`COUNT(*)` sẽ là 80.000 nếu đã nạp đúng một lần sau khi reset. Không dùng các số liệu giả lập này để suy ra cardinality hệ thống sản xuất.

### 3.4. Tạo index phục vụ những đường truy cập khác nhau

```sql
-- Có thể cung cấp thứ tự customer_id, nhưng chưa sắp theo amount.
CREATE INDEX idx_sales_customer
ON plan_memory_lab.sales (customer_id);

-- Thứ tự có thể phù hợp với ORDER BY thời gian mới nhất.
CREATE INDEX idx_sales_created_desc
ON plan_memory_lab.sales (created_at DESC, sale_id DESC);

-- Thứ tự theo region rồi thời gian.
CREATE INDEX idx_sales_region_created
ON plan_memory_lab.sales (region, created_at DESC);

ANALYZE plan_memory_lab.sales;
```

Với kế hoạch nào, planner có dùng index hay không phụ thuộc cost. Không mặc định cả ba index đều được dùng.

---

## 4. Node Sort trong EXPLAIN

Bắt đầu bằng truy vấn không có index phù hợp cho toàn bộ điều kiện sắp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, customer_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;
```

Một kế hoạch **minh họa** có thể có dạng:

```text
Sort
  Sort Key: amount DESC, sale_id DESC
  Sort Method: quicksort  Memory: ...kB
  Buffers: shared hit=...
  -> Seq Scan on sales
       Buffers: shared hit=...
Planning Time: ...
Execution Time: ...
```

Đây **không phải kết quả đo được** từ một database thật trong bài. Tên node, thứ tự và số đo cụ thể phụ thuộc dữ liệu, phiên bản, index, bộ nhớ và planner.

### 4.1. Sort Key

`Sort Key: amount DESC, sale_id DESC` cho biết PostgreSQL cần sắp theo hai tiêu chí:

1. `amount` giảm dần.
2. Khi amount bằng nhau, `sale_id` giảm dần.

Tie-breaker theo `sale_id` giúp xác định thứ tự trong các trường hợp amount bằng nhau. Nếu query chỉ `ORDER BY amount DESC`, các hàng cùng amount có thể xuất hiện theo thứ tự không được đảm bảo.

### 4.2. Input của Sort là gì?

Dưới node Sort có thể là:

- `Seq Scan`.
- `Index Scan`.
- `Hash Join` hoặc `Merge Join`.
- `Aggregate`.
- `Gather`.
- Các node khác.

Sort chỉ xử lý **luồng hàng mà node con tạo ra**. Không nên đọc node Sort rồi suy ra mọi hàng của bảng đều được sắp: có thể chúng đã được lọc trước.

### 4.3. Sort Method

Khi dùng `EXPLAIN ANALYZE`, bạn có thể thấy:

```text
Sort Method: quicksort  Memory: ...
Sort Method: top-N heapsort  Memory: ...
Sort Method: external merge  Disk: ...
```

Những dòng này cho biết kiểu thực thi sort được quan sát:

- **quicksort**: một dạng sắp xếp trong bộ nhớ thường gặp.
- **top-N heapsort**: giữ tập ứng viên tốt nhất khi chỉ cần số lượng nhỏ đầu tiên.
- **external merge**: sort cần dùng dữ liệu trung gian trên đĩa.

Không cam kết mọi phiên bản và query hiển thị đúng một trong ba nhãn đó. Điều quan trọng là hiểu **sort có bị spill và tiêu thụ bộ nhớ/đĩa ở đâu**.

---

## 5. In-memory sort và external sort

Một Sort cần giữ thông tin hàng/khóa đủ để sắp xếp. Khi tập dữ liệu phù hợp với giới hạn bộ nhớ dành cho phép sort, PostgreSQL có thể xử lý ngay trong RAM.

Khi nhiều dữ liệu vượt bộ nhớ dự kiến, engine có thể ghi các run tạm ra disk rồi hợp nhất chúng.

### 5.1. In-memory sort

```text
Input rows
    |
    v
Buffer dữ liệu trong phạm vi bộ nhớ của sort
    |
    v
Sắp xếp trong RAM
    |
    v
Output theo thứ tự yêu cầu
```

Có thể gặp `Sort Method: quicksort Memory: ...`.

### 5.2. External merge sort

```text
Input lớn hơn ngân sách sort
    |
    v
Chia thành các sorted runs
    |
    v
Ghi runs trung gian xuống temporary files
    |
    v
Merge các runs
    |
    v
Output đã sắp
```

Plan có thể hiện:

```text
Sort Method: external merge  Disk: ...kB
Buffers: temp read=... written=...
```

External sort không nhất thiết là lỗi; với một tập dữ liệu rất lớn, sử dụng disk có thể là lựa chọn hợp lý hơn việc cấp RAM khổng lồ cho một query. Vấn đề là **chi phí so với mục tiêu latency, throughput và khả năng bộ nhớ**.

### 5.3. Không quy đổi Disk thành work_mem bằng phép cộng đơn giản

Nếu EXPLAIN hiển thị `Disk: 120MB`, không thể kết luận chỉ cần `work_mem = 121MB` thì chắc chắn sort sẽ ở RAM:

- Dữ liệu trung gian và cấu trúc dữ liệu trong RAM khác layout file.
- Có overhead của tuple descriptors, keys, pointers, alignment.
- Thuật toán và cách quản lý memory khác nhau.
- Có thể nhiều sort nodes hoặc workers.
- Phiên bản PostgreSQL và biểu thức sắp xếp ảnh hưởng chi phí.

Cách đúng là **benchmark có kiểm soát** trong môi trường tương đương, không dùng một hệ số duy nhất cho mọi truy vấn.

---

## 6. Top-N heapsort: ORDER BY kết hợp LIMIT

Nếu chỉ cần 20 đơn có giá trị cao nhất:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC
LIMIT 20;
```

Khi không có index có thể trả đúng thứ tự, PostgreSQL có thể dùng **top-N heapsort** thay vì sắp toàn bộ 80.000 hàng.

Ý tưởng:

```text
Đọc tất cả các hàng ứng viên
     |
     v
Duy trì tập N hàng tốt nhất trong bộ nhớ
     |
     v
Xuất N hàng theo thứ tự yêu cầu
```

### 6.1. Top-N không có nghĩa không cần đọc toàn bộ bảng

Nếu không có đường truy cập theo thứ tự và không có điều kiện giúp loại bỏ đầu vào, engine vẫn phải xét toàn bộ các hàng ứng viên để chắc chắn biết 20 hàng cao nhất.

Tiết kiệm chủ yếu đến từ **không cần giữ và sort toàn bộ tập kết quả**.

### 6.2. LIMIT lớn hoặc OFFSET lớn

```sql
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC
LIMIT 20 OFFSET 50000;
```

Để trả hàng từ vị trí 50.001 đến 50.020, PostgreSQL phải xác định những hàng trước đó theo thứ tự. Bounded sort lúc này có thể cần giữ nhiều ứng viên hơn so với LIMIT 20 OFFSET 0.

Không coi mọi LIMIT nhỏ đều rẻ nếu OFFSET cực lớn.

### 6.3. Tìm top N bằng index

Nếu cần:

```sql
SELECT sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY created_at DESC, sale_id DESC
LIMIT 20;
```

index:

```sql
CREATE INDEX idx_sales_created_desc
ON plan_memory_lab.sales(created_at DESC, sale_id DESC);
```

có thể cho phép PostgreSQL đọc trực tiếp 20 hàng đầu theo thứ tự, không phải sort mọi hàng. Đây là lợi thế của **B-tree order**.

Nhưng nếu query trả phần lớn bảng hoặc cần nhiều cột nằm ngoài index, planner có thể vẫn chọn quét tuần tự và sort vì index access gây random I/O cao hơn.

### 6.4. FETCH FIRST ... WITH TIES

Nếu yêu cầu trả mọi hàng đồng hạng ở ranh giới cuối:

```sql
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC
FETCH FIRST 20 ROWS WITH TIES;
```

Kết quả có thể nhiều hơn 20 hàng. Cơ chế tối ưu bị ảnh hưởng bởi semantics của ties; không coi WITH TIES và LIMIT 20 là hoàn toàn tương đương.

---

## 7. ORDER BY và B-tree: tránh Sort khi thứ tự đã có

Một B-tree index thường có khả năng cung cấp dữ liệu theo thứ tự key.

Ví dụ:

```sql
SELECT sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY created_at DESC, sale_id DESC
LIMIT 30;
```

Có thể dùng `Index Scan` hoặc `Index Only Scan` trên `idx_sales_created_desc` khi phù hợp.

### 7.1. Index có thứ tự không thay ORDER BY về ngữ nghĩa

Nếu bỏ `ORDER BY` khỏi SQL, kết quả **không được bảo đảm có thứ tự**, ngay cả khi một lần chạy tình cờ dùng index scan.

Thứ tự xuất ra là một phần của **hợp đồng câu SELECT** khi có ORDER BY. Đừng phụ thuộc thứ tự vật lý bảng, index scan hiện tại hoặc output tình cờ của GroupAggregate.

### 7.2. Composite B-tree và tiền tố

Một index:

```sql
ON sales(region, created_at DESC)
```

cung cấp dữ liệu sắp theo:

1. `region`.
2. Trong từng region, `created_at DESC`.

Nó có thể phù hợp với:

```sql
ORDER BY region ASC, created_at DESC
```

hoặc các dạng đảo chiều scan tương thích theo thứ tự và NULL placement.

Nhưng **không tự cho toàn bộ bảng sắp theo `created_at DESC`** nếu region khác nhau bị chia thành từng nhóm.

### 7.3. Collation và NULL ordering

PostgreSQL cần xem:

- `ASC` hay `DESC`.
- `NULLS FIRST` hay `NULLS LAST`.
- Collation của biểu thức text.
- Biểu thức và operator family.

Theo mặc định, `ASC` thường đi cùng `NULLS LAST`, `DESC` đi cùng `NULLS FIRST` trong PostgreSQL. Một index có thứ tự NULL khác yêu cầu query có thể không cung cấp đúng thứ tự cho toàn bộ trường hợp.

Ví dụ:

```sql
CREATE INDEX idx_sales_time_nullslast
ON plan_memory_lab.sales (created_at DESC NULLS LAST);
```

Index này diễn tả cụ thể `DESC NULLS LAST`. Trong lab `created_at NOT NULL`, NULL placement không ảnh hưởng tập dữ liệu hiện tại, nhưng nó quan trọng với cột nullable trên hệ thống thật.

### 7.4. Expression ORDER BY

Nếu query sắp:

```sql
ORDER BY lower(region)
```

B-tree trên `region` không tự cung cấp thứ tự chính xác theo `lower(region)` với mọi collation và dữ liệu. Có thể cần expression index khi pattern này quan trọng:

```sql
CREATE INDEX idx_sales_lower_region
ON plan_memory_lab.sales ((lower(region)));
```

Nhưng mỗi index làm tăng write maintenance và dung lượng. Không thêm index trước khi xem plan và workload.

### 7.5. Index scan và Seq Scan + Sort: bài toán cost

Index order có thể tránh Sort, nhưng đọc nhiều hàng qua Index Scan có thể gây nhiều heap fetches. Nếu gần như toàn bộ bảng phải được trả, Seq Scan + Sort đôi khi rẻ hơn.

Vì vậy: **có index đúng ORDER BY không có nghĩa PostgreSQL bắt buộc dùng index**.

---

## 8. Incremental Sort là gì?

**Incremental Sort** tận dụng một luồng đầu vào đã được sắp theo **một tiền tố của yêu cầu ORDER BY**, sau đó chỉ sắp thêm những khóa còn thiếu trong từng nhóm có cùng tiền tố.

Giả sử cần:

```sql
ORDER BY customer_id ASC, amount DESC
```

Nhưng input đã có thứ tự:

```text
customer_id ASC
```

Khi đó mỗi khách hàng là một nhóm cùng prefix key. PostgreSQL có thể sắp `amount DESC` **trong từng nhóm customer_id**, thay vì sắp lại toàn bộ bảng theo cả hai cột.

### 8.1. Mô hình

```text
Input đã sắp customer_id:

customer 1: [amount 20, amount 90, amount 15]
customer 2: [amount 40, amount 10]
customer 3: [amount 70, amount 30, amount 80]

Incremental Sort theo customer_id, amount DESC:

customer 1: [90,20,15]
customer 2: [40,10]
customer 3: [80,70,30]

Ghép các nhóm theo customer_id:
    (1,90),(1,20),(1,15),
    (2,40),(2,10),
    (3,80),(3,70),(3,30)
```

### 8.2. Phần nào đã sắp?

- `Presorted Key`: key được luồng đầu vào bảo đảm đã sắp.
- `Sort Key`: toàn bộ thứ tự mà node Incremental Sort phải tạo ra.

Một plan minh họa:

```text
Incremental Sort
  Sort Key: customer_id, amount DESC
  Presorted Key: customer_id
  Full-sort Groups: ...
  Pre-sorted Groups: ...
  -> Index Scan using idx_sales_customer on sales
```

Tên các trường instrumentation có thể khác theo phiên bản và chiến lược nhóm. Không phải mọi EXPLAIN đều hiển thị cùng số dòng.

### 8.3. Lợi ích có thể có

- Không cần giữ toàn bộ input trong bộ nhớ nếu các prefix groups vừa phải.
- Có thể giảm khối lượng sắp xếp khi input đã có một phần thứ tự.
- Có thể bắt đầu trả một số nhóm đầu sớm hơn full Sort trong những kế hoạch phù hợp.
- Kết hợp với `LIMIT` đôi khi có thể tránh xử lý toàn bộ phần input không cần thiết.

### 8.4. Giới hạn: nhóm có cùng prefix quá lớn

Nếu 99% hàng đều có cùng một customer_id, Incremental Sort phải sắp một nhóm khổng lồ. Lợi ích về memory và cost có thể rất thấp, thậm chí tệ hơn phương án khác.

Hiệu quả phụ thuộc:

- Số nhóm khác nhau của prefix.
- Kích thước và phân bố từng nhóm.
- Input path đang có thứ tự ra sao.
- Số cột cần sort thêm.
- LIMIT và điều kiện lọc.
- Work_mem, disk I/O và chi phí lấy input theo index.

Không mặc định Incremental Sort luôn nhanh hơn Sort.

---

## 9. Lab Incremental Sort bằng index tiền tố

Trong lab có:

```sql
CREATE INDEX idx_sales_customer
ON plan_memory_lab.sales(customer_id);
```

Thử:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id, amount DESC;
```

PostgreSQL **có thể** chọn:

```text
Incremental Sort
  Sort Key: customer_id, amount DESC
  Presorted Key: customer_id
  -> Index Scan using idx_sales_customer ...
```

Hoặc có thể chọn:

```text
Sort
  Sort Key: customer_id, amount DESC
  -> Seq Scan ...
```

Cả hai là phương án hợp lệ; planner quyết định theo cost.

### 9.1. So sánh khi tắt Incremental Sort trong transaction lab

```sql
BEGIN;

SET LOCAL enable_incremental_sort = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id, amount DESC;

ROLLBACK;
```

`SET LOCAL` chỉ thay đổi trong transaction hiện tại. Sau ROLLBACK, setting trở lại giá trị trước đó.

### 9.2. Quan sát một kế hoạch có index input

Nếu planner ưu tiên Seq Scan vì chi phí thấp, có thể thử hạn chế một loại plan **chỉ để học**:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id, amount DESC;

ROLLBACK;
```

Cách này không phải khuyến nghị tối ưu production. Nếu index scan + incremental sort chậm hơn seq scan + full sort, planner có thể đã đúng khi không chọn nó.

### 9.3. Tại sao full Sort có thể thắng?

Đọc 80.000 hàng theo index customer_id có thể đòi hỏi nhiều heap page accesses không tuần tự. Một Seq Scan đọc tuần tự dữ liệu rồi Sort trong RAM có thể nhanh hơn.

Đánh giá **toàn bộ cost của plan**, không chỉ số RAM ở Sort node.

### 9.4. Incremental Sort và LIMIT

```sql
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id ASC, amount DESC
LIMIT 25;
```

Nếu có input đã sắp customer_id và Incremental Sort được chọn, PostgreSQL có thể chỉ cần hoàn thành đủ các nhóm đầu để trả 25 hàng. Còn full Sort thông thường phải xét toàn bộ input để tìm chính xác top 25 trên toàn thứ tự, nếu không có nguồn thứ tự hữu ích.

Lợi ích phụ thuộc nhóm prefix, plan và điều kiện; không có con số cố định.

---

## 10. Incremental Sort không chỉ đến từ index

Một input có thứ tự có thể xuất phát từ:

- Index Scan có ordering tương ứng.
- Merge Join hoặc một nhánh đã sort.
- Một số hoạt động grouping/merge tạo ordering phù hợp.
- Gather Merge khi các input workers có thứ tự.
- Những path khác mà planner xác nhận có pathkeys phù hợp.

Điều kiện cốt lõi không phải “có index”, mà là **plan có thể chứng minh input đã sắp theo tiền tố của yêu cầu**.

### 10.1. Presorted Key phải thực sự trùng semantics

Hai biểu thức trông giống nhau nhưng khác:

- Collation.
- ASC/DESC.
- NULLS placement.
- Expression.
- Loại toán tử/order family.

có thể không cung cấp cùng ordering.

Ví dụ index trên `lower(region)` không tự thay ordering theo `region` của collation có chữ hoa/thường khác nhau.

### 10.2. Incremental Sort và sai ước lượng cardinality

Planner phải ước lượng số lượng nhóm prefix và phân bố. Nếu tưởng có rất nhiều nhóm nhỏ nhưng thực tế chỉ vài nhóm rất lớn, Incremental Sort có thể xử lý kém.

Nguồn sai lệch:

- Statistics cũ.
- Phân bố skewed.
- Tương quan giữa các cột.
- Parameter values thay đổi.
- Biểu thức chưa có statistics phù hợp.

Cần nhìn `estimated rows` vs `actual rows`, thống kê `n_distinct`, MCV và extended statistics khi phù hợp.

### 10.3. Có nên tắt enable_incremental_sort toàn hệ thống?

Không nên coi `enable_incremental_sort=off` là mẹo tổng quát. Nó có thể hữu ích như **thí nghiệm chẩn đoán** hoặc giải pháp tạm theo phạm vi khi xác định regression cụ thể, nhưng cần kiểm thử và kế hoạch khôi phục.

Nguyên nhân gốc có thể là thống kê hoặc index/order mismatch, không phải bản thân tính năng Incremental Sort.

---

## 11. Aggregate: biến nhiều hàng thành kết quả tổng hợp

Aggregate thường là các phép:

```sql
COUNT(*)
SUM(amount)
AVG(amount)
MIN(amount)
MAX(amount)
```

Khi không có GROUP BY:

```sql
SELECT SUM(amount)
FROM plan_memory_lab.sales;
```

có thể thấy node `Aggregate` thông thường.

Khi có GROUP BY:

```sql
SELECT customer_id, COUNT(*), SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Planner có thể chọn `HashAggregate` hoặc `GroupAggregate`, tùy cost, ordering, số nhóm, bộ nhớ và các yếu tố khác.

### 11.1. Hai chiến lược phổ biến

```text
           Input rows
              |
        +-----+------+
        |            |
        v            v
   HashAggregate    Sort theo group key
        |            |
  Hash table         v
  theo từng nhóm   GroupAggregate
        |            |
        v            v
      Các kết quả aggregate
```

Cả hai phải cho **cùng kết quả logic** của SUM/COUNT khi query/kiểu dữ liệu phù hợp, trừ các khác biệt số học hợp lệ như floating-point order sensitivity; chi tiết thứ tự xử lý có thể tác động kết quả kiểu số xấp xỉ.

### 11.2. GROUP BY không có ORDER BY không bảo đảm thứ tự

Ngay cả khi lần chạy hiện `GroupAggregate` đang xuất nhóm theo `customer_id`, SQL không bảo đảm thứ tự trả về nếu thiếu ORDER BY ở mức kết quả.

Viết:

```sql
SELECT customer_id, COUNT(*)
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY customer_id;
```

nếu client thực sự cần thứ tự theo customer_id.

---

## 12. HashAggregate hoạt động như thế nào?

HashAggregate xây một **bảng băm trong bộ nhớ**, ánh xạ group key tới trạng thái aggregate:

```text
Key customer_id=1    -> count=80, sum=...
Key customer_id=2    -> count=80, sum=...
Key customer_id=3    -> count=80, sum=...
...
```

Mỗi input row tìm bucket của group key rồi cập nhật trạng thái SUM/COUNT.

### 12.1. Khi nào HashAggregate thường thuận lợi?

- Input chưa sắp theo group key.
- Có số nhóm có thể xử lý hiệu quả bằng hash.
- Không cần tạo thứ tự nhóm cho downstream hoặc hash rẻ hơn sort.
- Aggregate hỗ trợ kiểu thực thi phù hợp.

### 12.2. Plan có thể trông như thế nào?

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, COUNT(*) AS order_count,
       SUM(amount) AS total_amount
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Ví dụ dạng plan:

```text
HashAggregate
  Group Key: customer_id
  Batches: ...
  Memory Usage: ...kB
  Disk Usage: ...kB
  -> Seq Scan on sales
```

Khi số nhóm lớn hoặc trạng thái aggregate lớn, HashAggregate có thể cần chia **batches** và spill xuống disk trong những phiên bản PostgreSQL hỗ trợ cơ chế đó.

Không suy ra mọi HashAggregate đều ở RAM hoặc mọi HashAggregate có Disk Usage >0.

### 12.3. HashAggregate không có ordering hữu ích mặc định

Hash table không tổ chức kết quả theo customer_id tăng dần. Nếu truy vấn yêu cầu:

```sql
GROUP BY customer_id
ORDER BY customer_id;
```

planner cần cân nhắc thêm Sort sau hash, hoặc chọn GroupAggregate để tận dụng ordering.

### 12.4. HashAggregate có thể spill vì số nhóm, không chỉ vì số hàng

Một bảng 10 triệu hàng chỉ có 5 khu vực có thể gom vào rất ít group states. Ngược lại, 100.000 hàng mà mỗi hàng có một group key gần như duy nhất có thể tạo rất nhiều group states.

Cần phân biệt:

- **Input row count**: số hàng cần đọc.
- **Group cardinality**: số nhóm thực tế.
- **Aggregate state size**: trạng thái duy trì cho mỗi nhóm.

Ba yếu tố đều ảnh hưởng memory và thời gian, nhưng không có hệ số cố định.

---

## 13. GroupAggregate hoạt động như thế nào?

GroupAggregate xử lý các hàng đã được sắp hoặc được cung cấp theo thứ tự phù hợp với group keys.

Ví dụ input:

```text
customer_id amount
1           20
1           10
1           40
2           50
2           15
3            5
```

Khi các hàng cùng customer_id nằm liên tiếp, engine có thể tính aggregate cho nhóm hiện tại, rồi chuyển sang nhóm tiếp theo.

### 13.1. Khi nào GroupAggregate đáng chọn?

- Input đã sắp nhờ B-tree hoặc một node trước.
- Có thể sắp dữ liệu với chi phí rẻ.
- Muốn khai thác ordering cho bước tiếp theo.
- HashAggregate không thuận lợi về memory/cost.
- Cấu trúc aggregate/nhóm có yêu cầu xử lý đặc biệt.

### 13.2. Plan có thể gồm Sort + GroupAggregate

```text
GroupAggregate
  Group Key: customer_id
  -> Sort
       Sort Key: customer_id
       -> Seq Scan
```

Sort cần đọc dữ liệu rồi sắp theo customer_id; sau đó GroupAggregate đi qua các hàng cùng key.

### 13.3. Hoặc Index Scan + GroupAggregate

Nếu có index trên customer_id, planner có thể chọn:

```text
GroupAggregate
  Group Key: customer_id
  -> Index Scan using idx_sales_customer
```

Không cần Sort riêng vì input đã có thứ tự cần thiết. Nhưng index scan vẫn có chi phí; nếu nó phải đọc nhiều page ngẫu nhiên, HashAggregate + Seq Scan có thể thắng.

### 13.4. Thí nghiệm ép tắt hashagg trong phạm vi session

```sql
BEGIN;

SET LOCAL enable_hashagg = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, COUNT(*), SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id;

ROLLBACK;
```

Mục đích là **xem phương án khác**, không khẳng định nó nhanh hơn hoặc phù hợp để cấu hình toàn hệ thống.

---

## 14. HashAggregate vs GroupAggregate: so sánh quyết định

| Tiêu chí | HashAggregate | GroupAggregate |
| --- | --- | --- |
| Input cần có thứ tự theo group key? | Không | Có |
| Cấu trúc trung gian chính | Hash table chứa trạng thái nhóm | Luồng nhóm liên tiếp và aggregate state |
| Khả năng spill | Có thể chia batch/spill khi hash memory hạn chế | Sort đầu vào có thể spill; aggregate state cũng có memory |
| Output order được SQL bảo đảm? | Không, trừ khi ORDER BY | Không, trừ khi ORDER BY |
| Lợi khi input đã có index order | Không nhất thiết | Có thể tránh Sort |
| Lợi khi ít nhóm | Thường đáng cân nhắc | Cũng có thể tốt nếu input đã sắp |
| Lợi khi nhiều nhóm lớn | Phụ thuộc memory và data distribution | Phụ thuộc chi phí sort/scan |
| Khi ORDER BY aggregate result | Thường cần Sort sau | Cũng có thể cần Sort sau |

### 14.1. GROUP BY và ORDER BY không cùng key

```sql
SELECT customer_id, SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY revenue DESC;
```

Dù GroupAggregate nhận input sắp theo customer_id, output phải sắp lại theo revenue. Cần một giai đoạn ordering theo **giá trị aggregate**, không thể chỉ dùng index customer_id để suy ra top revenue.

### 14.2. HAVING được áp dụng ở đâu?

```sql
SELECT customer_id, SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id
HAVING SUM(amount) > 500
ORDER BY revenue DESC;
```

HAVING lọc các nhóm sau khi tính aggregate logic. EXPLAIN có thể hiển thị `Filter` và `Rows Removed by Filter` ở node aggregate.

HAVING có thể giảm số nhóm cần sort sau đó, nhưng không mặc định giảm số input rows cần đọc/tổng hợp.

### 14.3. WHERE giúp giảm input trước aggregate

Nếu query có thể lọc trước:

```sql
WHERE status = 'PAID'
```

thì số hàng đưa vào aggregate thường giảm. Việc đặt một điều kiện có thể áp dụng hợp lệ ở WHERE thay vì chỉ sau aggregate có thể tiết kiệm công việc, nhưng không được thay đổi semantics giữa lọc **hàng** và lọc **nhóm**.

---

## 15. Aggregate cần thứ tự riêng bên trong hàm

Một câu:

```sql
SELECT
    customer_id,
    array_agg(sale_id ORDER BY created_at DESC, sale_id DESC)
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

khác với:

```sql
SELECT
    customer_id,
    array_agg(sale_id)
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Trong trường hợp đầu, **thứ tự phần tử bên trong array** là một phần của yêu cầu. Trường hợp sau, thứ tự các phần tử không được bảo đảm nếu không có ORDER BY phù hợp bên trong aggregate.

### 15.1. Các aggregate có thứ tự quan trọng

Ví dụ:

```sql
SELECT
    customer_id,
    string_agg(product_id::TEXT, ',' ORDER BY product_id) AS products
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Dữ liệu có thứ tự trong `string_agg` và `array_agg` có thể khiến PostgreSQL cần công việc sorting bên trong aggregate hoặc tận dụng ordering phù hợp ở plan, tùy phiên bản.

Không mặc định **chỉ nhìn thấy node Sort ở ngoài** là bạn đã thấy mọi sort nội bộ. Phải hiểu cú pháp aggregate, instrumentation và khả năng tối ưu của phiên bản đang chạy.

### 15.2. DISTINCT bên trong aggregate

```sql
SELECT
    customer_id,
    COUNT(DISTINCT product_id) AS distinct_products
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

`COUNT(DISTINCT ...)` có nhu cầu loại trùng trong từng nhóm. Nó có thể đòi hỏi work và memory khác với `COUNT(*)`. Một số dạng DISTINCT/ORDER BY aggregate ảnh hưởng khả năng dùng hash và parallel partial aggregation.

### 15.3. GROUP BY không tự sắp thứ tự trong array_agg

Ví dụ:

```sql
SELECT customer_id, array_agg(product_id)
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY customer_id;
```

ORDER BY cuối cùng chỉ sắp **những hàng kết quả theo customer_id**. Nó **không cam kết** các phần tử của `array_agg` có thứ tự product_id.

Muốn phần tử có thứ tự, phải viết:

```sql
array_agg(product_id ORDER BY product_id)
```

---

## 16. DISTINCT và DISTINCT ON liên quan Sort/Aggregate

`DISTINCT` loại các hàng kết quả trùng:

```sql
SELECT DISTINCT customer_id
FROM plan_memory_lab.sales;
```

Planner có thể chọn hash-based strategy hoặc sort + unique tùy query và cost.

### 16.1. DISTINCT ON: chọn một hàng trong từng nhóm

PostgreSQL có:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY customer_id, created_at DESC, sale_id DESC;
```

Ý nghĩa: với mỗi customer_id, chọn hàng đầu tiên theo thứ tự đã nêu — ở đây là đơn mới nhất (và sale_id lớn hơn khi timestamp bằng nhau).

Quan trọng:

- `DISTINCT ON` là cú pháp PostgreSQL đặc thù.
- Biểu thức `DISTINCT ON` phải phù hợp những biểu thức đầu của ORDER BY theo quy tắc PostgreSQL.
- Nếu không có ORDER BY xác định, hàng được giữ không đáng tin theo nghiệp vụ.
- Planner có thể dùng Sort + Unique hoặc nguồn có ordering phù hợp từ index.

### 16.2. Index hỗ trợ DISTINCT ON

Một index:

```sql
CREATE INDEX idx_sales_customer_latest
ON plan_memory_lab.sales (
    customer_id, created_at DESC, sale_id DESC
);
```

có thể giúp cung cấp thứ tự phù hợp. Nhưng nó còn chiếm dung lượng và tăng chi phí INSERT/UPDATE, không phải điều kiện bắt buộc của DISTINCT ON.

### 16.3. DISTINCT + ORDER BY

```sql
SELECT DISTINCT customer_id
FROM plan_memory_lab.sales
ORDER BY customer_id;
```

có thể dùng một chiến lược bảo đảm cả unique và ordering. Cách chọn phụ thuộc indexes, dữ liệu và planner; không mặc định luôn có hai Sort node.

---

## 17. GROUPING SETS, ROLLUP và CUBE

PostgreSQL hỗ trợ nhiều mức tổng hợp trong một query:

```sql
SELECT
    region,
    status,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY ROLLUP (region, status)
ORDER BY region NULLS LAST, status NULLS LAST;
```

ROLLUP theo `(region, status)` có các mức:

1. (region, status)
2. (region)
3. Tổng toàn bảng

Các hàng tổng có thể chứa NULL ở các chiều được roll up; nếu dữ liệu thật cũng có NULL thì cần phân biệt bằng `GROUPING(...)`.

### 17.1. MixedAggregate

Một số kế hoạch có thể hiển thị node `MixedAggregate`, `GroupAggregate` hoặc những chiến lược khác cho grouping sets, tùy phiên bản và biểu thức.

Không kết luận lỗi khi thấy node Aggregate khác với ví dụ nhóm đơn giản; grouping sets mở rộng không gian chiến lược thực thi.

### 17.2. Tránh nhầm NULL thật và NULL do tổng hợp

```sql
SELECT
    region,
    status,
    GROUPING(region, status) AS grouping_mask,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY ROLLUP (region, status)
ORDER BY region NULLS LAST, status NULLS LAST;
```

`GROUPING` cho biết cột nào đã bị loại khỏi grouping level của hàng tương ứng. Đây là cách an toàn hơn so với chỉ dựa vào NULL trong output.

---

## 18. Parallel Aggregate và Gather Merge

Với bảng đủ lớn và aggregate phù hợp, PostgreSQL có thể chia công việc cho nhiều worker.

Một plan có thể chứa:

```text
Finalize GroupAggregate
  Group Key: ...
  -> Gather Merge
       Workers Planned: ...
       -> Sort
            Sort Key: ...
            -> Partial HashAggregate / Partial GroupAggregate
                 -> Parallel Seq Scan ...
```

Đây là sơ đồ **minh họa**, không phải một dạng plan bắt buộc.

### 18.1. Partial Aggregate

Worker tính **trạng thái aggregate trung gian** trên dữ liệu của nó, ví dụ count và sum cục bộ.

### 18.2. Finalize Aggregate

Node finalize tổng hợp các trạng thái trung gian thành kết quả chung.

Không phải mọi aggregate đều có thể partial/finalize; khả năng phụ thuộc định nghĩa hàm aggregate và những đặc tính của truy vấn như DISTINCT/ORDER BY trong aggregate.

### 18.3. Gather khác Gather Merge

- `Gather` hợp nhất kết quả worker mà không hứa duy trì thứ tự tổng thể theo key.
- `Gather Merge` hợp nhất **những luồng đã được sắp phù hợp** để tạo một luồng có ordering.

Nếu query yêu cầu ORDER BY, Gather Merge có thể giữ ordering bằng merge; nhưng những bước phía sau vẫn có thể cần Sort mới theo key khác.

### 18.4. Bộ nhớ tăng cùng workers

Các worker có thể thực hiện sort/hash operation riêng. Một query với nhiều worker không phải dùng đúng một quỹ `work_mem` được chia đều cho toàn bộ workers.

Vì vậy, tăng parallelism có thể giảm wall-clock time trong một số workload, nhưng cũng tăng đỉnh CPU, temp I/O và RAM trên hệ thống.

---

## 19. Window functions cũng có thể cần Sort

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    sale_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY amount DESC, sale_id DESC
    ) AS rank_in_customer
FROM plan_memory_lab.sales;
```

Để tính row_number theo từng customer và theo amount giảm dần, executor cần một luồng có ordering phù hợp với `PARTITION BY` và `ORDER BY` trong window definition.

Kế hoạch có thể chứa `Sort`/`Incremental Sort` rồi `WindowAgg`, tùy index và dữ liệu.

### 19.1. ORDER BY trong OVER không là ORDER BY output

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY amount DESC
)
```

xác định thứ tự phục vụ window function, **không tự bảo đảm** thứ tự hàng trả về của SELECT ngoài cùng.

Nếu client muốn thứ tự kết quả:

```sql
ORDER BY customer_id, amount DESC, sale_id DESC
```

phải đặt ORDER BY ở query ngoài. Planner có thể tái sử dụng ordering đã có, nhưng semantics SQL cần được viết rõ.

### 19.2. Nhiều window definitions có thể cần nhiều sort

Nếu query có hai window functions yêu cầu ordering không tương thích, PostgreSQL có thể cần các bước sắp xếp khác nhau. Một Sort không phải lúc nào cũng phục vụ mọi window clause.

---

## 20. work_mem: không phải “RAM tối đa mỗi truy vấn”

`work_mem` là một cấu hình quan trọng cho các phép sort và hash, nhưng rất dễ bị hiểu sai.

### 20.1. Định nghĩa thực dụng

`work_mem` biểu diễn giới hạn cơ sở dành cho **mỗi hoạt động truy vấn dùng memory kiểu tương ứng**, ví dụ Sort hoặc các hash operations theo quy tắc hiện hành.

Nó **không phải**:

- Tổng RAM PostgreSQL được phép sử dụng.
- Tổng RAM một connection được dùng.
- Tổng RAM một SQL statement được dùng.
- Kích thước buffer cache.
- Tổng temp files cả database.

Một truy vấn có **nhiều node sort/hash** có thể dùng nhiều lần ngân sách này. Một số node có thể hoạt động ở các giai đoạn khác nhau; đỉnh thực tế cần đo, không cộng tất cả như thể luôn cấp phát đầy đủ cùng lúc.

### 20.2. Ví dụ tư duy về đỉnh bộ nhớ

Giả sử:

```text
work_mem = 32 MB

Một query có:
  Sort A
  Sort B
  HashAggregate C

Và query có các worker parallel.
```

Không thể suy ra “query này dùng tối đa 32 MB”. Các hoạt động có thể dùng quỹ memory riêng, các hash operations còn chịu `hash_mem_multiplier`.

Nếu có hàng chục query đồng thời, rủi ro tổng bộ nhớ có thể cao hơn nhiều so với một phép sort đơn lẻ.

### 20.3. Quan sát cấu hình

```sql
SHOW work_mem;
SHOW hash_mem_multiplier;
SHOW temp_file_limit;
SHOW temp_tablespaces;
```

Quyền thay đổi các setting phụ thuộc loại tham số và chính sách DBA. Các câu SHOW có thể giúp biết môi trường hiện tại.

### 20.4. Thay đổi theo transaction để làm lab

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;

ROLLBACK;
```

`SET LOCAL` giới hạn thay đổi vào transaction. Giá trị `64kB` là mức nhỏ nhằm **cố tình tạo áp lực spill trong lab**, không phải setting nên dùng toàn hệ thống.

### 20.5. So với 32 MB

```sql
BEGIN;

SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;

ROLLBACK;
```

Quan sát:

- Sort Method.
- Memory hoặc Disk.
- Temp read/written.
- Execution time.
- Buffers.

Chỉ coi đây là **thí nghiệm kỹ thuật**. Đừng suy ra nếu 32MB tốt cho một Sort thì 32MB an toàn cho mọi query và mọi thời điểm.

---

## 21. hash_mem_multiplier: phép hash có quỹ riêng

Các phép hash phù hợp trong PostgreSQL có thể được cấp ngân sách bộ nhớ từ cơ sở `work_mem × hash_mem_multiplier` theo phiên bản và quy tắc quản lý memory.

Ví dụ khái niệm:

```text
work_mem = 16 MB
hash_mem_multiplier = 2.0

Ngưỡng dự kiến cho một số hash operations
  có thể theo cơ sở ~32 MB.
```

Đây không phải lời hứa mọi HashAggregate sẽ dùng 32MB hay mọi thao tác đều được cấp sẵn số đó.

### 21.1. Tại sao có multiplier?

Hash join và hash aggregate có cấu trúc hash khác với sort. Cho phép một ngưỡng memory cao hơn đôi khi giúp giảm số batches và disk I/O.

Nhưng nếu nhiều hash nodes/parallel workers/sessions hoạt động đồng thời, tăng multiplier có thể đẩy áp lực RAM lên cao.

### 21.2. Xem plan HashAggregate

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id,
    COUNT(*) AS n,
    SUM(amount) AS total
FROM plan_memory_lab.sales
GROUP BY sale_id;
```

Vì sale_id gần như unique, số nhóm lớn. Planner có thể chọn `GroupAggregate` tận dụng primary key order hoặc `HashAggregate` tùy cost.

Để quan sát một phương án hash trong lab, có thể dùng cấu hình planner theo transaction, nhưng không có bảo đảm mọi truy vấn đều có thể dùng HashAggregate khi chỉ thay một tham số.

### 21.3. Một truy vấn group cardinality cao để xem hash pressure

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    product_id,
    COUNT(*) AS n,
    SUM(amount) AS total
FROM plan_memory_lab.sales
GROUP BY customer_id, product_id;

ROLLBACK;
```

Trên phân bố 80.000 hàng, có thể có nhiều nhóm. Nếu HashAggregate được chọn và spill, EXPLAIN có thể hiển thị `Batches`, `Memory Usage`, `Disk Usage`.

Nếu planner chọn Sort + GroupAggregate, điều đó cũng hợp lý; quan sát và giải thích cost thay vì tuyên bố SQL này bắt buộc spill hash.

---

## 22. work_mem khác shared_buffers, temp_buffers và maintenance_work_mem

| Tham số | Vai trò chính | Điều không nên nhầm |
| --- | --- | --- |
| `shared_buffers` | Bộ nhớ đệm trang dữ liệu dùng chung | Không phải dung lượng trực tiếp cho mỗi Sort |
| `work_mem` | Ngưỡng cơ sở cho mỗi thao tác sort/hash liên quan | Không phải giới hạn toàn query/session |
| `hash_mem_multiplier` | Hệ số ngân sách cho những hash operations | Không phải tăng giới hạn mọi Sort |
| `temp_buffers` | Buffers của temporary tables trong session | Không phải quỹ bộ nhớ cho external sort |
| `maintenance_work_mem` | Các hoạt động bảo trì như CREATE INDEX/VACUUM theo quy tắc riêng | Không tự giải quyết Sort của SELECT thông thường |
| `autovacuum_work_mem` | Ngân sách memory cho autovacuum workers khi cấu hình phù hợp | Không dùng để tối ưu ORDER BY |
| `temp_file_limit` | Giới hạn dung lượng temporary files theo phạm vi backend/process phù hợp | Không phải giới hạn RAM và không áp dụng như một hạn mức toàn cluster |

### 22.1. Vì sao tên “temp” dễ gây nhầm?

**Temporary table** và **temporary file do query spill** không phải cùng một khái niệm:

- `CREATE TEMP TABLE` tạo một relation tạm với storage và lifecycle theo session/transaction.
- Một external sort hoặc hash spill có thể tạo file tạm nội bộ của executor.
- `temp_buffers` dành cho buffer của temporary tables.
- `work_mem` điều khiển mức dùng bộ nhớ của các sort/hash operations trước khi cần spill.
- `temp_file_limit` hạn chế dung lượng file tạm theo cơ chế nó áp dụng; không phải công tắc tắt temp table.

Không chỉnh `temp_buffers` để chữa một external Sort spill nếu chưa phân biệt đúng tầng.

---

## 23. Temporary files và temp I/O trong EXPLAIN

Để quan sát một Sort có khả năng spill:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, customer_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;

ROLLBACK;
```

Có thể thấy những trường như:

```text
Sort Method: external merge  Disk: ...kB
Buffers: shared hit=..., temp read=... written=...
```

### 23.1. Ý nghĩa temp read/written

- `temp read`: số blocks đọc từ temporary storage được gắn với phạm vi node/instrumentation.
- `temp written`: số blocks ghi vào temporary storage.
- Các đơn vị thường là block theo report của BUFFERS; không nhầm giá trị block với số byte.
- Số liệu ở node cha có thể bao gồm activity của node con theo cách EXPLAIN hiển thị; **không cộng mọi dòng plan một cách mù quáng**.

Temp I/O có thể đến từ Sort, HashAggregate, hash join, materialization hoặc thao tác trung gian khác. Không mặc định có temp read là Sort đã spill khi không xem node tương ứng.

### 23.2. Có Disk Usage nhưng thời gian vẫn nhanh?

Nếu đĩa nhanh và tập dữ liệu vừa phải, một external Sort có thể đủ nhanh cho yêu cầu. Tối ưu cần dựa vào **SLO của ứng dụng, throughput và tổng tải**, không chỉ nhìn chữ “Disk”.

### 23.3. Sort không spill vẫn có thể dùng nhiều RAM

Một Sort hiển thị `Memory: ...` có thể tiêu thụ lượng RAM đáng kể, dù không có temporary files. Khi nhiều query cùng chạy, rủi ro bộ nhớ vẫn quan trọng.

Không có temp files không đồng nghĩa “truy vấn không tốn bộ nhớ”.

---

## 24. Theo dõi temp usage toàn database

PostgreSQL cung cấp thống kê tích lũy ở `pg_stat_database`:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

- `temp_files`: tổng số file tạm được ghi nhận bởi thống kê cho database.
- `temp_bytes`: tổng bytes temporary files được các query ghi theo cơ chế thống kê.
- `stats_reset`: mốc reset thống kê.

### 24.1. Đây không phải số đo riêng một statement

Các giá trị là thống kê **tích lũy toàn database**, có thể chứa hoạt động của nhiều session và truy vấn. Khi đo chênh lệch trước/sau một lab trên server dùng chung, phải biết writer khác cũng có thể tạo temporary files.

### 24.2. Tính tốc độ temp bytes

Nếu monitoring lấy mẫu:

```text
T0: temp_bytes = 10 GB
T1: temp_bytes = 11.5 GB
Khoảng thời gian: 5 phút
```

chênh lệch là khoảng 1.5 GB data được ghi vào temp files theo bộ đếm trong khoảng đó. Nhưng nó **không cho biết chính xác query nào** gây ra, và không phải dung lượng file temp đang tồn tại tại thời điểm T1.

Các giá trị này chỉ mang tính ví dụ, không phải số liệu thật.

### 24.3. Thống kê có độ trễ

Cumulative stats có thể được cập nhật theo cơ chế riêng và được cache snapshot trong transaction. Một phép thử vừa chạy không nhất thiết lập tức phản ánh 100% vào view theo kỳ vọng tại mọi thời điểm.

Có thể dùng:

```sql
SELECT pg_stat_clear_snapshot();
```

để bỏ snapshot thống kê đã cache trong phiên nếu cần; nó không biến thông tin tích lũy thành phép đo per-query chính xác.

---

## 25. Theo dõi temp I/O theo query với pg_stat_statements

Khi extension `pg_stat_statements` đã được cấu hình/cho phép, nó giúp thu thập thống kê theo dạng statement chuẩn hóa.

Ví dụ:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    temp_blks_read,
    temp_blks_written
FROM pg_stat_statements
WHERE query ILIKE '%plan_memory_lab.sales%'
ORDER BY temp_blks_written DESC
LIMIT 20;
```

**Điều kiện:** extension phải được cài đặt và thư viện được cấu hình phù hợp, thường qua `shared_preload_libraries` trước khi server khởi động. Cột/view có thể khác theo phiên bản, quyền và cách cấu hình.

### 25.1. Temp blocks không phải temp files hiện còn

`temp_blks_read/written` là thống kê số block temp I/O của query. Nó không trực tiếp chỉ file nào còn nằm trên ổ đĩa, cũng không phân biệt tất cả nguyên nhân chỉ bằng một con số.

Để phân tích, đối chiếu:

- `calls`.
- Thời gian thực thi.
- Query shape.
- EXPLAIN trên query đại diện.
- Dung lượng dữ liệu và work_mem tại thời điểm đo.

### 25.2. Query text và quyền riêng tư

SQL query text trong monitoring/logs có thể chứa thông tin nhạy cảm, nhất là khi ứng dụng không dùng bind parameters. Việc truy cập/log những view đó phải tuân thủ chính sách bảo mật và phân quyền.

---

## 26. log_temp_files: phát hiện file tạm lớn

Tham số `log_temp_files` cho phép PostgreSQL log những temporary file đủ lớn khi chúng được xóa/hoàn tất theo cơ chế logging.

Ý nghĩa giá trị thường gặp:

- `-1`: tắt logging temp files.
- `0`: log mọi temp file.
- Giá trị dương: ngưỡng kích thước theo đơn vị cấu hình của tham số (thông thường kB).

### 26.1. Khi nào nên bật?

Trong môi trường điều tra có quyền phù hợp, logging temp files có thể giúp liên hệ:

- Query/session.
- Thời điểm.
- Dung lượng temp file.
- Hoạt động disk.

Tuy nhiên bật log mọi file trong hệ thống tải cao có thể tạo lượng log lớn và overhead. Không tự đặt `log_temp_files=0` toàn production chỉ để làm một bài lab.

### 26.2. Không đồng nhất log_temp_files với temp_file_limit

- `log_temp_files`: **quan sát/log**.
- `temp_file_limit`: **giới hạn** dung lượng file tạm theo phạm vi backend/process mà cơ chế áp dụng.

Nếu đặt `temp_file_limit` quá thấp, query cần spill có thể bị lỗi khi vượt giới hạn. Đây là công cụ bảo vệ tài nguyên, không phải biện pháp làm query sort nhanh hơn.

### 26.3. Temp tablespaces

`temp_tablespaces` cho phép chọn tablespace cho các đối tượng tạm theo quy tắc PostgreSQL. Việc chuyển temp I/O sang storage khác có thể giúp cân bằng tải, nhưng còn phụ thuộc cấu hình server, quyền CREATE ở tablespace, reliability, capacity và vận hành.

Không khuyến nghị tự đưa temp files sang ổ đĩa không tin cậy hoặc thiếu dung lượng để “tăng tốc” mà không tính rủi ro.

---

## 27. Khi tăng work_mem có thể hại hệ thống

Giả sử một Sort bị external merge với `work_mem=4MB` và chạy nhanh hơn khi thử `work_mem=64MB` trên một connection lab.

Kết luận sai là “hãy đặt work_mem=64MB toàn hệ thống”.

Tại production:

- Có thể có hàng trăm connections.
- Mỗi query có nhiều Sort/Hash nodes.
- Mỗi query có nhiều parallel workers.
- Hash operations có memory budget khác nhờ multiplier.
- Những session khác cần RAM cho backend, shared buffers, OS cache.
- Query plans có thể thay đổi khi settings đổi.

### 27.1. Ví dụ tư duy, không phải dự báo RAM chính xác

```text
20 queries đồng thời
mỗi query có 3 operations lớn
work_mem = 64 MB

20 × 3 × 64 MB = 3840 MB
```

Con số này minh họa việc **mức dùng có thể cộng dồn qua operations và sessions**, không phải memory cap chính xác vì từng node có thể dùng ít hơn, hoạt động khác pha, có overhead và hash multiplier/worker riêng.

### 27.2. Cách tiếp cận an toàn

1. Xác định đúng truy vấn cần tối ưu.
2. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trên dataset đại diện.
3. Thử `SET LOCAL work_mem` trong transaction/session riêng.
4. So sánh thời gian, sort method, temp I/O và CPU.
5. Xem concurrency tối đa thực tế.
6. Chọn phạm vi thay đổi hẹp nhất khi có thể (transaction/session/role) theo chính sách.
7. Theo dõi memory, latency và nguy cơ OOM sau triển khai.

Không dùng setting toàn cluster như một giải pháp đầu tiên khi một query có WHERE/ORDER BY/index chưa hợp lý.

---

## 28. Planner statistics ảnh hưởng Sort và Aggregate

Planner lựa chọn Sort/HashAggregate/GroupAggregate/Incremental Sort dựa vào **ước lượng cost**.

Một số dữ liệu thống kê quan trọng:

- Số hàng ước lượng.
- Tỷ lệ lọc.
- Số distinct values.
- Most common values (MCV).
- Histogram và correlation.
- Extended statistics về quan hệ giữa nhiều cột.
- Độ rộng trung bình của hàng/biểu thức.

### 28.1. Xem thống kê cột

```sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    correlation
FROM pg_stats
WHERE schemaname = 'plan_memory_lab'
  AND tablename = 'sales'
  AND attname IN (
      'customer_id','region','status','product_id','amount'
  )
ORDER BY attname;
```

`n_distinct` có thể là số ước lượng hoặc biểu diễn tỷ lệ theo quy ước của PostgreSQL; không nhất thiết bằng COUNT(DISTINCT ...) tuyệt đối.

### 28.2. ANALYZE sau khi dữ liệu thay đổi lớn

```sql
ANALYZE plan_memory_lab.sales;
```

Nếu phân bố customer_id/product_id thay đổi đáng kể mà stats quá cũ, planner có thể ước lượng group cardinality sai, dẫn tới chọn HashAggregate hoặc Incremental Sort không phù hợp.

### 28.3. Extended statistics

Khi các cột có tương quan, có thể tạo thống kê mở rộng:

```sql
CREATE STATISTICS st_sales_region_status
    (dependencies, ndistinct, mcv)
ON region, status
FROM plan_memory_lab.sales;

ANALYZE plan_memory_lab.sales;
```

Loại statistics nào giúp được từng dạng ước lượng phụ thuộc cách dùng và khả năng của planner. Extended stats **không tự chữa mọi vấn đề cardinality** trong joins, aggregates và ordering.

### 28.4. Cost estimate khác actual

Khi EXPLAIN:

```text
estimated rows = 100
actual rows = 100000
```

sai lệch lớn có thể dẫn tới kế hoạch khác kỳ vọng. Hãy kiểm tra selectivity, statistics, parameter values và correlation trước khi đề xuất tắt planner node.

---

## 29. Sort và JOIN

Sort có thể xuất hiện trước hoặc sau JOIN:

```text
Seq Scan A ----\
                -> Hash Join -> Sort ORDER BY ...
Seq Scan B ----/
```

Hoặc để merge join:

```text
Sort A --\
          -> Merge Join -> ...
Sort B --/
```

### 29.1. Merge Join cần input ordered

Merge Join thường cần hai luồng sắp theo join keys. Thứ tự này có thể được cung cấp bởi index hoặc Sort.

Vì thế khi thấy Sort trong plan, phải hỏi:

- Sort phục vụ `ORDER BY` cuối?
- Hay phục vụ `Merge Join`?
- Hay phục vụ GroupAggregate, window function, DISTINCT?
- Có thể dùng index ordering để thay không?

Không có quy tắc “Sort ngay trước JOIN là thừa”.

### 29.2. Hash Join cũng dùng memory và có thể spill

Một `Hash Join` có thể tạo bảng băm và chia batches khi không đủ memory. Nó liên quan `work_mem`/`hash_mem_multiplier`, nhưng là thao tác khác với HashAggregate.

Khi temp I/O cao, không chỉ tìm Sort. Một plan gồm nhiều hash nodes cũng có thể là nguồn spill.

### 29.3. ORDER BY trên output JOIN

Một kế hoạch join tốt chưa chắc trả ra theo ORDER BY người dùng yêu cầu. Planner có thể đặt Sort cuối nếu ordering đã mất qua Hash Join/Gather, hoặc chọn một đường merge/index order khi có lợi.

---

## 30. Tối ưu SQL trước khi tăng RAM

Một số câu hỏi thực tế:

### 30.1. Có thực sự cần toàn bộ hàng đã sắp?

Nếu UI chỉ hiển thị 20 hàng mới nhất:

```sql
SELECT sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY created_at DESC, sale_id DESC
LIMIT 20;
```

có thể có lợi từ index order + LIMIT, thay vì trả/sort toàn bộ hàng rồi cắt ở ứng dụng.

### 30.2. Có thể giảm đầu vào bằng WHERE không?

```sql
SELECT customer_id, SUM(amount)
FROM plan_memory_lab.sales
WHERE status = 'PAID'
GROUP BY customer_id;
```

Nếu status filter chọn lọc, giảm rows trước aggregate có thể giúp. Tuy nhiên một index trên status không luôn có lợi nếu phần lớn hàng là PAID; planner có thể chọn Seq Scan.

### 30.3. Có cần sắp theo nhiều cột?

```sql
ORDER BY region, customer_id, created_at DESC, sale_id DESC
```

nhiều keys có thể tăng chi phí sort hoặc khiến index ordering khó khớp. Chỉ bỏ key nếu contract của kết quả cho phép; đừng làm mất tính xác định khi phân trang.

### 30.4. Có thể gom trước rồi sort ít nhóm hơn?

Nếu query cần top 20 customers theo doanh thu, aggregate trước rồi sort 1000 groups thường tốt hơn sort toàn bộ 80.000 rows theo một order không liên quan. Planner thường thực hiện điều này từ cấu trúc SQL đúng, nhưng cần tránh các subquery/sort không cần thiết gây cản trở tối ưu.

### 30.5. Có thể dùng materialized view không?

Nếu báo cáo tổng hợp lịch sử được chạy liên tục mà dữ liệu không cần realtime từng giây, có thể cân nhắc:

- Materialized view với lịch refresh.
- Bảng aggregate được cập nhật theo sự kiện/ETL.
- Partitioning khi dữ liệu rất lớn.
- Caching có chính sách stale phù hợp.

Đây là đánh đổi độ tươi dữ liệu, chi phí refresh và tính phức tạp, không phải thay thế tự động cho HashAggregate.

---

## 31. Kiểm tra Sort spill theo quy trình từng bước

Dưới đây là quy trình lab thực tế:

### Bước 1 — Lấy baseline với cấu hình hiện có

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;
```

Ghi lại plan shape, Sort Method, Memory/Disk, temp read/written, Execution Time.

### Bước 2 — Thử work_mem thấp trong transaction

```sql
BEGIN;
SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;

ROLLBACK;
```

Nếu có external merge, ghi nhận Disk và temp blocks.

### Bước 3 — Thử work_mem cao hơn nhưng chỉ trong lab

```sql
BEGIN;
SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;

ROLLBACK;
```

Đánh giá Sort Method và I/O. Đừng so chỉ một lần khi cache và concurrent workload khác nhau.

### Bước 4 — Xem có đường index order không

Câu SORT theo amount, created_at, sale_id không có index tổng hợp tương ứng trong lab. Cân nhắc **nếu thực sự cần**:

```sql
CREATE INDEX idx_sales_amount_time
ON plan_memory_lab.sales (
    amount DESC, created_at DESC, sale_id DESC
);
```

Sau đó:

```sql
ANALYZE plan_memory_lab.sales;

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC
LIMIT 20;
```

Đường B-tree order có thể giúp, đặc biệt với LIMIT 20. Nhưng index mới tăng chi phí INSERT/UPDATE và dung lượng; không nên tạo trên production chỉ vì một Sort trong EXPLAIN.

### Bước 5 — Kết luận theo workload

So sánh:

- Baseline.
- Work_mem cao hơn.
- Query có LIMIT.
- Query dùng index order.
- Tốc độ ghi và chi phí index mới.
- Số sessions đồng thời.

Không chọn phương án chỉ theo một execution time đơn lẻ.

---

## 32. Kiểm tra aggregate theo quy trình từng bước

### Bước 1 — Hash/Group strategy mặc định

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    customer_id,
    COUNT(*) AS n,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Quan sát node là `HashAggregate` hay `GroupAggregate`.

### Bước 2 — Xem chiến lược không hash

```sql
BEGIN;
SET LOCAL enable_hashagg = off;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT customer_id, COUNT(*), SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id;

ROLLBACK;
```

Phân biệt:

- Sort + GroupAggregate.
- Index Scan + GroupAggregate.
- Các phương án khác.

### Bước 3 — Quan sát khi số nhóm tăng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    product_id,
    COUNT(*),
    SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id, product_id;
```

Cardinality của `(customer_id,product_id)` có thể cao hơn customer_id đơn lẻ; memory/cost của HashAggregate sẽ khác.

### Bước 4 — Xem ORDER BY trên kết quả aggregate

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
```

Phân biệt:

- Tổng hợp các hàng gốc.
- Sort 1000 nhóm sau aggregate để tìm top 20.
- Bước Limit.

Một `Sort Method: top-N heapsort` trên khoảng 1000 nhóm là tình huống hoàn toàn khác với sort 80.000 hàng gốc.

---

## 33. Tình huống thực tế: API phân trang bị chậm

Một API:

```sql
SELECT *
FROM orders
WHERE tenant_id = :tenant
ORDER BY created_at DESC
LIMIT 20 OFFSET 200000;
```

đang chậm.

Nguyên nhân có thể:

- Sort một tập kết quả rất lớn.
- Index order không phù hợp tenant_id + created_at.
- OFFSET lớn buộc đọc/bỏ rất nhiều hàng.
- Trả quá nhiều cột, gây heap fetch.
- Work_mem thấp khiến Sort spill.
- Điều kiện WHERE không đủ chọn lọc.
- Statistics cũ khiến planner chọn plan kém.

### 33.1. Cân nhắc keyset pagination

Nếu có thứ tự ổn định:

```sql
-- Mẫu trên bảng giả định có khóa id và created_at.
SELECT *
FROM orders
WHERE tenant_id = :tenant
  AND (
      created_at < :last_created_at
      OR (
          created_at = :last_created_at
          AND id < :last_id
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Với index phù hợp `(tenant_id, created_at DESC, id DESC)`, keyset có thể tránh phải bỏ qua rất nhiều hàng như OFFSET lớn.

Nhưng phải xử lý:

- Timestamp bằng nhau bằng tie-breaker unique.
- Các hàng mới/chỉnh sửa trong khi user phân trang.
- Semantics ổn định theo snapshot nếu nghiệp vụ cần.
- NULL ordering và điều kiện cursor.
- Index và quyền tenant.

Không thay mọi OFFSET bằng keyset nếu UI cần nhảy trang tùy ý mà không có cursor.

---

## 34. Tình huống thực tế: HashAggregate spill khi GROUP BY nhiều keys

Một báo cáo:

```sql
SELECT
    customer_id,
    product_id,
    DATE(created_at) AS day,
    SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id, product_id, DATE(created_at);
```

có thể tạo nhiều nhóm vì kết hợp ba chiều.

Nếu `HashAggregate` được chọn và hash table lớn:

- Memory Usage cao.
- Batches > 1 khi cần chia batches.
- Disk Usage/temp blocks có thể xuất hiện.
- Execution time tăng do temp I/O.

### 34.1. Đánh giá lại nhu cầu nhóm

Có thực sự cần số liệu tới mức từng customer, từng product, từng ngày không? Nếu dashboard chỉ hiển thị theo region/ngày, nhóm quá chi tiết làm tăng cardinality mà không mang thêm giá trị.

Không được tự thay GROUP BY nếu làm sai báo cáo; chỉ đơn giản hóa khi nghiệp vụ cho phép.

### 34.2. Đánh giá phương án GroupAggregate

Có thể thử `enable_hashagg=off` trong lab; nếu GroupAggregate cần external Sort lớn, giải pháp có thể không tốt hơn HashAggregate spill. Không có quy tắc HashAggregate luôn tốt hơn hoặc kém hơn GroupAggregate khi spill.

### 34.3. Tránh tăng work_mem toàn server ngay

Trước tiên xem:

- Group cardinality thực tế và ước lượng.
- Hash Batches/Disk Usage.
- Concurrency.
- Có filter/range trước aggregate không.
- Có thể preaggregate hoặc materialize kết quả định kỳ không.
- Có index order phù hợp với workload không.

Tuning memory là một trong nhiều lựa chọn, không phải bước duy nhất.

---

## 35. Tình huống thực tế: Incremental Sort regression

Một phiên bản PostgreSQL/plan mới chọn Incremental Sort sau index scan thay vì Seq Scan + full Sort, nhưng latency tăng mạnh.

Các giả thuyết:

1. Ước lượng số nhóm prefix quá cao.
2. Thực tế có vài nhóm rất lớn.
3. Index scan tốn nhiều random heap I/O.
4. LIMIT không thể dừng sớm như planner dự đoán.
5. Điều kiện lọc khiến prefix groups phân bố lệch.
6. Statistics thiếu hoặc sai.
7. Work_mem/parallelism hoặc schema đã thay đổi.

### 35.1. Cách điều tra

- Ghi lại `EXPLAIN (ANALYZE, BUFFERS)` và version PostgreSQL.
- Kiểm tra `Presorted Key` và stats của key.
- So estimated vs actual rows.
- So số groups và kích thước nhóm.
- Thử trong transaction với `SET LOCAL enable_incremental_sort=off`.
- So cost tổng của index scan, I/O và Sort.
- Chạy ANALYZE/extended stats khi có bằng chứng cần.
- Đưa ra thay đổi có phạm vi và kiểm thử.

Không đánh giá tính năng chỉ qua tên node; một Incremental Sort có thể là tối ưu rất tốt ở query khác.

---

## 36. Tình huống thực tế: nhiều temp files và đĩa chậm

Monitoring báo `pg_stat_database.temp_bytes` tăng nhanh và latency của report cao.

Một phương pháp điều tra:

1. Xem thời điểm temp bytes/temp files tăng.
2. Đối chiếu `pg_stat_statements.temp_blks_written` nếu bật.
3. Dùng `log_temp_files` theo quyền/quy trình để xác định các truy vấn lớn.
4. Lấy EXPLAIN cho query đại diện.
5. Xem nguồn spill là Sort, HashAggregate, Hash Join, materialize hay nút khác.
6. Kiểm tra work_mem, hash_mem_multiplier, parallel workers và số sessions.
7. Kiểm tra disk temp tablespace, throughput, filesystem capacity.
8. Tối ưu WHERE/index/order/grouping trước khi tăng memory.
9. Benchmark theo SLO và giám sát thay đổi.

### 36.1. Đừng chỉ nhìn temp_bytes tích lũy

Một server nhiều query nhỏ có thể ghi tổng temp_bytes lớn theo thời gian mà không có một query nào gây sự cố. Ngược lại, một query khổng lồ duy nhất có thể làm disk đầy rất nhanh.

Cần đo **rate, per-query distribution và peak temp disk usage**, không chỉ một bộ đếm tích lũy.

### 36.2. Có phải temp I/O luôn chỉ là thiếu RAM?

Không. Một số query xử lý dữ liệu lớn hơn bất cứ giới hạn RAM an toàn nào, nên external sort là bình thường. Vấn đề có thể là thiết kế query không cần sắp toàn bộ hoặc không có index order, chứ không phải “RAM cấu hình quá thấp”.

---

## 37. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Có ORDER BY nghĩa là chắc có Sort node.” | Index/plan có thể cung cấp ordering |
| “Không có ORDER BY nhưng GroupAggregate thì output luôn có thứ tự.” | SQL chỉ bảo đảm khi có ORDER BY thích hợp |
| “Sort luôn chậm.” | Sort trong RAM trên ít hàng có thể rất rẻ |
| “External Sort là lỗi PostgreSQL.” | Là chiến lược xử lý dữ liệu vượt memory budget |
| “Disk: 100MB nghĩa cần work_mem=101MB.” | Memory layout và overhead khác temp file |
| “LIMIT 20 nghĩa chỉ đọc 20 hàng.” | Nếu thiếu index order, có thể phải đọc toàn input |
| “Top-N heapsort và Index Scan LIMIT là một.” | Hai chiến lược khác nhau |
| “OFFSET 100000 không tốn vì LIMIT 20.” | Phải xử lý/bỏ những hàng trước |
| “Incremental Sort sắp toàn bộ input lại.” | Tận dụng tiền tố đã sắp và sort trong nhóm |
| “Có index bất kỳ thì dùng Incremental Sort.” | Input phải có ordering prefix tương thích |
| “Incremental Sort luôn nhanh hơn Sort.” | Tùy prefix groups, scan cost và memory |
| “Presorted Key chính là Sort Key đầy đủ.” | Presorted Key chỉ là tiền tố đã có |
| “Gần như mọi hàng cùng prefix vẫn tốt.” | Nhóm khổng lồ có thể mất lợi thế |
| “GROUP BY bắt buộc Sort.” | HashAggregate có thể không sort input |
| “HashAggregate luôn hoàn toàn ở RAM.” | Có thể chia batches và spill |
| “GroupAggregate luôn rẻ hơn HashAggregate.” | Có thể phải Sort input lớn |
| “GROUP BY tạo thứ tự customer_id.” | Chỉ ORDER BY mới bảo đảm output order |
| “ORDER BY ngoài cùng sắp các phần tử array_agg.” | ORDER BY trong aggregate mới kiểm soát phần tử |
| “COUNT(DISTINCT) có chi phí giống COUNT(*).” | Có thêm việc deduplicate |
| “B-tree trên created_at luôn được dùng cho ORDER BY.” | Planner có thể chọn Seq Scan + Sort |
| “Index composite bất kỳ sắp được theo cột thứ hai.” | Thứ tự toàn bảng còn phụ thuộc key trước |
| “ASC/DESC và NULLS FIRST/LAST không quan trọng.” | Là một phần của ordering semantics |
| “Gather giữ thứ tự của mọi worker.” | Gather Merge dành cho việc merge luồng đã sắp |
| “Parallel query chia đều một work_mem.” | Operations/workers có memory budget riêng |
| “work_mem là RAM tối đa của một query.” | Nó áp dụng cho mỗi hoạt động liên quan |
| “work_mem=64MB nghĩa 100 connections tổng 64MB.” | Concurrent operations có thể cộng dồn nhiều lần |
| “hash_mem_multiplier cũng tăng Sort memory.” | Chủ yếu liên quan phép hash đủ điều kiện |
| “temp_buffers chữa external Sort.” | temp_buffers dành cho temporary tables |
| “temp_file_limit là cấu hình work_mem.” | Nó giới hạn temp disk theo phạm vi |
| “pg_stat_database.temp_bytes chỉ tính query này.” | Là thống kê tích lũy cấp database |
| “temp_bytes là dung lượng temp files hiện còn.” | Là tổng dữ liệu ghi được thống kê |
| “log_temp_files tự làm query nhanh hơn.” | Chỉ giúp quan sát và chẩn đoán |
| “Temp read ở node cha cộng thêm vào mọi node con.” | Cần hiểu cách BUFFERS tổng hợp, tránh đếm đôi |
| “EXPLAIN cost là thời gian ms.” | Cost là đơn vị tương đối của planner |
| “Ép enable_seqscan=off chứng minh index nhanh hơn.” | Chỉ giúp xem phương án thay thế |
| “Tăng work_mem toàn production luôn tốt.” | Có rủi ro bộ nhớ/OOM do concurrency |
| “ANALYZE không liên quan sort.” | Stats ảnh hưởng plan Sort/Aggregate |
| “Hash Join spill là lỗi Sort.” | Hash join là nguồn temp I/O riêng |
| “Chỉ số temp I/O cao = hệ thống phải thiếu RAM.” | Có thể do thiết kế query và data volume |

---

## 38. Bài tập thực hành

### Bài 1 — Đọc Sort Key

Chạy EXPLAIN với:

```sql
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;
```

Xác định Sort Key và node tạo input. Vì sao `sale_id DESC` là tie-breaker?

### Bài 2 — So sánh hai work_mem

Dùng `SET LOCAL work_mem='64kB'` và `'32MB'` trong hai transaction lab, chạy cùng Sort query. Ghi nhận Sort Method, Memory/Disk và temp read/written.

### Bài 3 — External sort

Giải thích một external merge sort có thể chia runs và merge thế nào. Vì sao Disk usage không chuyển thẳng thành mức work_mem tối thiểu?

### Bài 4 — Top-N heapsort

Chạy `ORDER BY amount DESC LIMIT 20` và so với không LIMIT. Vì sao LIMIT 20 vẫn có thể phải đọc 80.000 hàng?

### Bài 5 — Index order

Chạy `ORDER BY created_at DESC, sale_id DESC LIMIT 20`. Index nào trong lab có thể cung cấp thứ tự? Vì sao có thể không có Sort?

### Bài 6 — OFFSET

So LIMIT 20 OFFSET 0 với LIMIT 20 OFFSET 50000. Tại sao số hàng trả giống nhau nhưng công việc có thể khác nhiều?

### Bài 7 — NULL ordering

Giải thích khác biệt `ORDER BY x DESC` và `ORDER BY x DESC NULLS LAST` khi x nullable. Tại sao index direction/NULL placement ảnh hưởng plan?

### Bài 8 — B-tree composite

Với index (region, created_at DESC), query nào tận dụng ordering tốt hơn: `ORDER BY region, created_at DESC` hay `ORDER BY created_at DESC` trên toàn bảng? Giải thích.

### Bài 9 — Incremental Sort

Với input đã sắp customer_id, query ORDER BY customer_id, amount DESC có thể cần Sort nào? Vẽ dữ liệu theo ba khách hàng và sắp trong từng nhóm.

### Bài 10 — Presorted Key

Trong một plan có `Sort Key: customer_id, amount DESC` và `Presorted Key: customer_id`, phần nào cần sắp thêm?

### Bài 11 — Tắt Incremental Sort trong lab

Dùng `SET LOCAL enable_incremental_sort=off` và so plan. Vì sao việc tắt một node không tự chứng minh plan thay thế luôn tốt hơn?

### Bài 12 — Prefix skew

90% hàng có cùng customer_id. Dự đoán Incremental Sort hiệu quả thế nào khi sort theo customer_id, amount. Cần đo gì?

### Bài 13 — Aggregate không GROUP BY

Chạy `SELECT SUM(amount)`. Node Aggregate dạng nào có thể xuất hiện? Vì sao không cần duy trì nhiều group keys?

### Bài 14 — HashAggregate

Chạy GROUP BY customer_id. Hash table giữ thông tin gì cho COUNT/SUM? Khi nào có thể xuất hiện Batches hoặc Disk Usage?

### Bài 15 — GroupAggregate

Thử tắt hashagg cục bộ. Nếu plan xuất hiện Sort + GroupAggregate, Sort cần key nào? Nếu dùng Index Scan customer_id thì sao?

### Bài 16 — ORDER BY aggregate value

Chạy GROUP BY customer_id ORDER BY SUM(amount) DESC LIMIT 20. Vì sao index trên customer_id không tự sắp theo revenue?

### Bài 17 — HAVING và WHERE

Viết query lọc status PAID ở WHERE rồi lọc SUM(amount)>500 ở HAVING. Phân biệt số hàng vào aggregate và số nhóm sau aggregate.

### Bài 18 — COUNT DISTINCT

So COUNT(*) với COUNT(DISTINCT product_id) theo customer_id. Vì sao phép DISTINCT có thể cần memory/sort/hash bổ sung?

### Bài 19 — array_agg order

Viết `array_agg(sale_id ORDER BY created_at DESC)`. Vì sao ORDER BY ở query ngoài không thay thế ORDER BY bên trong aggregate?

### Bài 20 — DISTINCT ON

Lấy sale mới nhất của mỗi customer bằng DISTINCT ON và ORDER BY phù hợp. Thiết kế B-tree index hỗ trợ thứ tự.

### Bài 21 — ROLLUP

Tổng doanh thu theo (region,status), theo region và toàn bảng. Dùng GROUPING để phân biệt NULL do rollup với NULL thật.

### Bài 22 — Parallel aggregate

Phân biệt Partial Aggregate và Finalize Aggregate. Khi nào Gather Merge hữu ích? Vì sao parallel workers làm memory planning phức tạp?

### Bài 23 — WindowAgg sort

Dùng ROW_NUMBER() PARTITION BY customer_id ORDER BY amount DESC. PostgreSQL cần ordering gì? Có chắc kết quả ngoài cùng tự sắp như vậy không?

### Bài 24 — work_mem

Một query có ba Sort/Hash operations và được chạy đồng thời bởi 20 sessions. Vì sao không thể lấy work_mem nhân một lần rồi coi đó là tổng memory cap?

### Bài 25 — hash_mem_multiplier

Cho work_mem=16MB, hash_mem_multiplier=2.0. Giải thích ngân sách cơ sở của phép hash và vì sao không phải mọi HashAggregate sẽ dùng đúng 32MB.

### Bài 26 — temp_buffers

Phân biệt temporary table buffers với temporary files do external sort. Đổi temp_buffers có phải cách trực tiếp để chữa Sort spill không?

### Bài 27 — pg_stat_database

Truy vấn temp_files, temp_bytes và stats_reset. Vì sao số này không cho biết một query đã sử dụng bao nhiêu temp bytes khi có nhiều sessions đồng thời?

### Bài 28 — pg_stat_statements

Nếu extension đã bật, truy vấn các statement có temp_blks_written cao. Cần thêm metrics nào để phân biệt query gọi rất nhiều lần và query spill cực lớn mỗi lần?

### Bài 29 — log_temp_files

Giải thích sự khác biệt của -1, 0 và giá trị dương. Vì sao không nên bật logging mọi temp file toàn production trong thời gian dài mà không xem log volume?

### Bài 30 — temp_file_limit

Giải thích nó bảo vệ tài nguyên nào, khác work_mem thế nào và tại sao đặt quá thấp có thể làm query thất bại.

### Bài 31 — Sort vs Hash Join spill

Một plan có cả Sort, Hash Join và HashAggregate. Cách xác định node nào gây temp I/O? Vì sao không thể chỉ nhìn tổng temp_bytes?

### Bài 32 — Planner statistics

Xem pg_stats.n_distinct và most_common_vals trên customer_id, region. Sai ước lượng số nhóm có thể tác động lựa chọn HashAggregate/Incremental Sort thế nào?

### Bài 33 — Extended statistics

Tạo statistics trên region,status rồi ANALYZE. Đề xuất phép đo để xem planner estimates có cải thiện không, và nêu hạn chế.

### Bài 34 — Materialized summary

Một dashboard chạy cùng GROUP BY hàng trăm lần/phút trên dữ liệu không cần realtime tuyệt đối. So sánh query trực tiếp với materialized view/bảng tổng hợp về latency và độ tươi.

### Bài 35 — Tối ưu API

Một API ORDER BY created_at DESC LIMIT 20 OFFSET 200000 đang chậm. Đề xuất index, keyset pagination và các kiểm tra cần làm để giữ semantics phân trang.

### Bài 36 — Báo cáo nhiều nhóm

Một report GROUP BY customer_id,product_id,DATE(created_at) bị HashAggregate spill. Nêu ít nhất năm hướng điều tra trước khi tăng work_mem toàn cluster.

### Bài 37 — Incremental Sort regression

Một plan mới có Incremental Sort chậm hơn full Sort. Liệt kê các nguyên nhân có thể: prefix skew, index heap I/O, cardinality, LIMIT, work_mem, planner stats. Thiết kế thử nghiệm để phân biệt.

### Bài 38 — Checklist memory production

Thiết kế một bảng đánh giá gồm concurrent queries, sorts/hashes per query, parallel workers, work_mem, hash multiplier, temp disk capacity, SLO, monitoring và rollback plan.

---

## 39. Checklist vận hành và tối ưu

| Câu hỏi | Cách kiểm tra / ý nghĩa |
| --- | --- |
| Query có ORDER BY thực sự cần không? | Semantics sản phẩm |
| ORDER BY có tie-breaker ổn định? | Pagination/consistency |
| Có Sort node không? | EXPLAIN |
| Sort Key là gì? | Xem yêu cầu ordering |
| Input đã có thứ tự nào? | Index/pathkeys, presorted key |
| Có Incremental Sort không? | EXPLAIN, prefix groups |
| Prefix groups có skew không? | Distribution, stats |
| Sort Method là gì? | quicksort/top-N/external merge |
| Có spill ra disk không? | Disk, temp read/written |
| LIMIT có giúp giảm work không? | Top-N/index-ordered scan |
| OFFSET có quá lớn không? | Keyset pagination |
| Index có match ASC/DESC/NULLS/collation? | Định nghĩa B-tree và ORDER BY |
| Index order có làm random I/O cao không? | BUFFERS/latency |
| Có GROUP BY không? | Aggregate strategy |
| HashAggregate hay GroupAggregate? | Plan node |
| Group cardinality được ước lượng đúng? | estimated vs actual, n_distinct |
| HashAggregate có Batches>1? | Memory/Disk, temp I/O |
| GroupAggregate có Sort trước? | Sort Method / spill |
| ORDER BY kết quả aggregate là key nào? | Có cần Sort sau aggregate |
| Có DISTINCT trong aggregate? | Chi phí deduplicate |
| Có ORDER BY trong array_agg/string_agg? | Semantics và memory |
| Có GROUPING SETS/ROLLUP? | MixedAggregate và nhiều grouping levels |
| Có WindowAgg không? | Sort theo partition/order keys |
| Có parallel workers? | Memory/concurrency, Gather Merge |
| work_mem hiện tại? | SHOW work_mem |
| hash_mem_multiplier? | SHOW hash_mem_multiplier |
| Có nhiều operations trong một query? | Mỗi node có ngân sách riêng |
| Có nhiều sessions cùng chạy? | Peak memory, OOM |
| Có temp tables không? | Phân biệt temp_buffers |
| Có temp disk pressure? | pg_stat_database, OS |
| Query nào tạo temp blocks lớn? | pg_stat_statements nếu bật |
| Có log temp files không? | log_temp_files theo chính sách |
| Có temp_file_limit phù hợp? | Tránh disk exhaustion, hạn mức thực tế |
| Có tablespace phù hợp? | temp_tablespaces, quyền/disk |
| Planner stats có mới? | ANALYZE |
| Có tương quan giữa nhiều cột? | Extended statistics khi phù hợp |
| Có thể filter sớm? | WHERE/partition pruning |
| Có thể giảm số group hoặc sort columns? | Chỉ khi nghiệp vụ cho phép |
| Có nên tạo index mới? | Đọc, ghi, storage, concurrency |
| Có nên tăng work_mem? | Thử theo session, xem tổng tải |
| Có so nhiều lần trên dữ liệu đại diện? | Cache/IO/concurrent load |
| Có kế hoạch rollback tuning? | Reset setting, drop thử nghiệm có kiểm soát |

## Kết luận

Trong PostgreSQL, **Sort**, **Incremental Sort**, **Aggregate** và **bộ nhớ tạm** là những mảnh ghép rất quan trọng của execution plan:

- **Sort** tạo thứ tự mà query yêu cầu khi input chưa có ordering phù hợp. Nó có thể xử lý trong bộ nhớ hoặc dùng external merge và temporary files nếu cần.
- **Top-N heapsort** có thể giúp khi chỉ cần số lượng kết quả đầu, nhưng không tự làm số hàng input cần đọc giảm nếu thiếu đường truy cập theo thứ tự.
- **Incremental Sort** khai thác một tiền tố đã sắp để chỉ sắp tiếp trong từng nhóm. Nó có thể tiết kiệm đáng kể nhưng phụ thuộc phân bố prefix groups và chi phí input path.
- **HashAggregate** gom nhóm bằng hash table; **GroupAggregate** tiêu thụ luồng đã sắp theo group keys. Cả hai có thể tốt hoặc tệ tùy cardinality, ordering, memory và I/O.
- **ORDER BY của kết quả** và **ORDER BY bên trong aggregate/window** có ý nghĩa khác nhau. Không có ORDER BY ngoài cùng thì SQL không bảo đảm thứ tự output.
- **work_mem** là cơ sở bộ nhớ cho từng phép toán liên quan, không phải RAM cap cho toàn truy vấn. Các hash operations có thể dùng ngân sách phụ thuộc `hash_mem_multiplier`; parallel workers và concurrent queries cộng thêm áp lực.
- **Temp I/O** phải được đọc qua plan, `Buffers: temp`, `pg_stat_database`, `pg_stat_statements` và logging theo phạm vi. Một bộ đếm temp_bytes tích lũy không chỉ ra nguyên nhân của một query cụ thể.
- **Index B-tree, statistics và thiết kế SQL** thường là đòn bẩy quan trọng không kém việc tăng memory. Thêm index có lợi cho đọc nhưng cũng tiêu tốn disk và chi phí ghi.
- **Tối ưu an toàn** là đo baseline, thử từng biến trong phạm vi hạn chế, so sánh kết quả đúng và độ trễ, sau đó cân nhắc tải đồng thời trước khi áp dụng production.

Khi bạn đọc được thứ tự input, chiến lược aggregate, loại Sort, memory usage và temp I/O trên cùng một execution plan, những truy vấn báo cáo chậm sẽ trở thành bài toán có thể phân tích và kiểm chứng thay vì chỉ thử tăng `work_mem` rồi hy vọng chúng nhanh hơn.

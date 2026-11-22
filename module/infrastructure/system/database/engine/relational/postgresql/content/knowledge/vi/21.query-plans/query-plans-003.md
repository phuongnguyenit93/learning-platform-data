# Actual rows, loops và cách diễn giải thời gian trong kế hoạch truy vấn PostgreSQL

Khi tối ưu PostgreSQL, rất dễ nhìn thấy một dòng trong `EXPLAIN ANALYZE` như sau:

~~~text
Index Scan using idx_orders_customer on orders o
  (cost=0.29..5.10 rows=4 width=32)
  (actual time=0.010..0.035 rows=3 loops=500)
~~~

Rồi kết luận: “Index Scan chỉ lấy ba dòng và mất 0,035 ms”. Kết luận này **không đầy đủ**, vì node đó đã được gọi **500 lần**. Trong định dạng văn bản thông thường, `actual rows` và `actual time` của node được trình bày **theo giá trị trung bình cho mỗi lần thực thi (loop)**.

Với ví dụ giả định trên:

- `actual rows=3` biểu thị trung bình khoảng **3 hàng mỗi loop**.
- `loops=500` biểu thị node được thực thi **500 lượt**.
- Tổng số hàng đi ra node trong tất cả các lượt xấp xỉ **3 × 500 = 1.500 hàng**.
- `actual time=0.010..0.035` biểu thị thời gian từ lúc bắt đầu lượt tới hàng đầu tiên, và tới khi hoàn tất lượt, **trung bình mỗi loop**, tính bằng mili giây.
- Tổng thời gian được tính cho các lượt của riêng node này có thể được ước lượng theo **0,035 × 500 ≈ 17,5 ms** trong mô hình tuần tự; đó **không** nhất thiết là thời gian đồng hồ từ đầu tới cuối của toàn truy vấn.

Nếu node nằm trong `Nested Loop`, số lần lặp lớn có thể biến một thao tác tìm index rất nhanh thành một phần đáng kể của workload. Ngược lại, khi nhiều worker hoạt động song song, cộng thời gian xử lý của các worker **không có nghĩa** đó là wall-clock latency của truy vấn.

Bài học này hướng dẫn đọc chính xác:

1. `cost=... rows=... width=...`: các **ước lượng** của planner.
2. `actual time=startup..total`: thời gian **đo được** trong từng lượt node.
3. `actual rows`: hàng thực sự được node trả ra **trung bình mỗi lượt**.
4. `loops`: số lần node chạy.
5. `Planning Time` và `Execution Time`: thời gian tổng thể khác với các trường ở từng node.
6. Mối liên hệ với `Nested Loop`, `Hash Join`, `Sort`, `Aggregate`, `LIMIT`, `Materialize`, `Memoize`, parallel query và `BUFFERS`.

Các đoạn kế hoạch ví dụ có số liệu minh họa; **không phải log chạy thực tế trong môi trường của bạn**. Kết quả `EXPLAIN ANALYZE` phụ thuộc phiên bản PostgreSQL, dữ liệu, cache, thống kê, phần cứng và tải cùng thời điểm.

## 1. Tại sao phải đọc số liệu thực thi?

PostgreSQL phải quyết định cách thực hiện câu SQL trước khi thật sự biết kết quả:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

Planner có thể ước lượng một khách có 10 đơn, chọn `Index Scan`, rồi khi chạy thực tế mới phát hiện khách ấy có 2.000 đơn.

Đó là khoảng cách giữa:

- **Estimated values**: planner dự đoán từ thống kê, constraint và mô hình chi phí.
- **Actual values**: executor đo khi câu truy vấn thực sự được chạy.

`EXPLAIN` thông thường chỉ cho thấy ước lượng; `EXPLAIN ANALYZE` chạy câu lệnh và bổ sung số liệu đo. Chính chênh lệch này thường cho biết lý do PostgreSQL chọn plan không phù hợp hoặc một node bị gọi quá nhiều lần.

### 1.1. EXPLAIN và EXPLAIN ANALYZE

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

Hiển thị plan **ước lượng**, không thực thi câu `SELECT` để đo thời gian/hàng.

~~~sql
EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

Thực thi truy vấn và thu thập số liệu. Có thể viết rõ các tùy chọn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

### 1.2. Cảnh báo với lệnh thay đổi dữ liệu

`EXPLAIN ANALYZE` **thực thi** `INSERT`/`UPDATE`/`DELETE`/`MERGE` và các lệnh được hỗ trợ; nó không chỉ mô phỏng.

Để phân tích DML trong môi trường lab và rollback thay đổi transactional:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE perf_lab.orders
SET amount = amount + 1
WHERE order_id = 1;

ROLLBACK;
~~~

Lưu ý rollback không nhất thiết hoàn tác **mọi side effect ngoài database hoặc sequence**, và các trigger/function có thể gây tác dụng khác. Không chạy `EXPLAIN ANALYZE` trên lệnh ghi production nếu chưa hiểu hệ quả.

## 2. Giải phẫu một node của EXPLAIN ANALYZE

Một đoạn minh họa:

~~~text
Index Scan using idx_orders_customer_id on orders o
  (cost=0.29..8.31 rows=15 width=48)
  (actual time=0.016..0.051 rows=12 loops=1)
  Index Cond: (customer_id = 42)
  Buffers: shared hit=5
Planning Time: 0.219 ms
Execution Time: 0.114 ms
~~~

| Trường | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `cost` | `0.29..8.31` | Chi phí startup và total **ước lượng**, đơn vị chi phí planner |
| `rows` trong `cost` | `15` | Số hàng planner **ước lượng node trả ra**, cho mỗi lần thực thi |
| `width` | `48` | Kích thước hàng trung bình ước lượng, tính bằng byte |
| `actual time` | `0.016..0.051` | Thời gian startup/total đo được, **ms trung bình mỗi loop** |
| `actual rows` | `12` | Số hàng thực tế node trả ra, trung bình mỗi loop |
| `loops` | `1` | Node được thực thi một lượt |
| `Index Cond` | `customer_id = 42` | Điều kiện dùng bởi index scan |
| `Buffers` | `shared hit=5` | Số lượt truy cập block từ shared buffers (chi tiết ở phần sau) |
| `Planning Time` | `0.219 ms` | Thời gian lập kế hoạch được báo cáo |
| `Execution Time` | `0.114 ms` | Thời gian thực thi toàn bộ statement theo đo đạc của PostgreSQL |

**Hai trường `rows` cùng xuất hiện nhưng không cùng nghĩa.** `rows=15` cạnh `cost` là dự đoán; `rows=12` cạnh `actual time` là giá trị đo.

### 2.1. “Node trả ra” khác “node đã quét”

Giả sử:

~~~text
Seq Scan on orders
  (actual time=0.100..4.100 rows=100 loops=1)
  Filter: (status = 'paid')
  Rows Removed by Filter: 4900
~~~

Node có thể **kiểm tra 5.000 hàng** nhưng chỉ **trả 100 hàng lên node cha**. Vì vậy `actual rows=100` không nói rằng node chỉ đọc 100 hàng.

Các trường như `Rows Removed by Filter`, `Index Cond`, `Heap Fetches` và `BUFFERS` giúp phân biệt công việc nội bộ với số hàng đầu ra.

### 2.2. Các giá trị khác nhau dù kế hoạch giống nhau

Số liệu thực thi thay đổi theo:

- Hàng trong bảng, thống kê và phân bố dữ liệu.
- Trang đã được cache hay phải đọc từ storage.
- Các transaction đồng thời và lock waits.
- Lựa chọn JIT/parallel execution.
- Phiên bản PostgreSQL, thông số planner, tải CPU và cơ chế đo thời gian.

Không coi một giá trị `actual time=0.051` như hằng số cố định của toán tử `Index Scan`.

## 3. Đọc đúng actual rows

**`actual rows` là số hàng trung bình mà node trả về cho mỗi lượt chạy.**

Ví dụ:

~~~text
Index Scan ...
  (actual time=0.01..0.05 rows=4 loops=1)
~~~

Node trả khoảng 4 hàng trong lượt duy nhất.

~~~text
Index Scan ...
  (actual time=0.01..0.05 rows=4 loops=200)
~~~

Node trả trung bình khoảng 4 hàng trong **200 lượt**.

Tổng hàng xấp xỉ:

\[
\text{total output rows from node}
\;\approx\;
\text{actual rows per loop}
\times
\text{loops}
\]

Với ví dụ thứ hai:

\[
4\times200=800\text{ hàng}
\]

### 3.1. Tại sao cần “xấp xỉ”?

Định dạng text của `EXPLAIN ANALYZE` thường hiển thị số nguyên cho `rows` và làm tròn giá trị trung bình khi có nhiều loops.

Giả sử ba lần chạy trả:

~~~text
Loop 1 -> 0 hàng
Loop 2 -> 1 hàng
Loop 3 -> 2 hàng

Tổng: 3 hàng
Trung bình: 1 hàng/loop
~~~

`rows=1 loops=3` thể hiện đúng trung bình.

Nhưng nếu:

~~~text
Loop 1 -> 0 hàng
Loop 2 -> 0 hàng
Loop 3 -> 1 hàng

Tổng: 1 hàng
Trung bình: 0,333 hàng/loop
~~~

văn bản có thể trình bày `rows=0 loops=3` sau khi làm tròn. Kết luận “không có hàng nào từng được trả” sẽ sai.

Vì vậy, **không khẳng định phép nhân trên cho kết quả đếm tuyệt đối chính xác** khi số liệu per-loop đã bị làm tròn.

### 3.2. Actual rows ở node cha và node con

~~~text
Aggregate  (actual ... rows=1 loops=1)
  -> Seq Scan  (actual ... rows=5000 loops=1)
~~~

`Aggregate` có thể nhận 5.000 hàng rồi trả **một hàng** tổng hợp. Node con trả 5.000 không buộc node cha cũng trả 5.000.

Các node thực hiện những phép biến đổi khác nhau:

- `Filter` làm giảm hàng.
- `Aggregate` gộp hàng.
- `Join` có thể nhân hoặc giảm số hàng.
- `Sort` thường giữ số hàng nhưng đổi thứ tự.
- `LIMIT` trả một phần đầu ra.
- `Unique`/`Distinct` có thể loại trùng.

Khi phân tích số hàng, hãy bám vào **ranh giới đầu vào/đầu ra từng node**.

## 4. Đọc đúng loops

`loops` là số lần node được khởi động/thực thi bởi executor trong kế hoạch đo. Giá trị cao thường xuất hiện khi node nằm ở **nhánh trong của Nested Loop**, ở một `SubPlan` tương quan, hoặc khi các cấu trúc plan được gọi lại.

### 4.1. Một node chỉ chạy một lần

~~~text
Seq Scan on customers
  (actual time=0.015..0.400 rows=2000 loops=1)
~~~

Trong ví dụ, node được quét một lượt và trả 2.000 hàng.

### 4.2. Node chạy nhiều lần

~~~text
Index Scan on orders
  (actual time=0.005..0.020 rows=5 loops=2000)
~~~

Lượt scan index lặp tới **2.000 lần**, mỗi lượt trung bình 5 hàng; tổng khoảng **10.000 hàng đầu ra** của node.

### 4.3. loops không phải số lần chạy SQL từ ứng dụng

Một câu SQL chỉ được ứng dụng gửi **một lần** nhưng có node `loops=2000`. Đó là lặp **bên trong executor**, không phải 2.000 request HTTP hay 2.000 prepared statements từ client.

### 4.4. loops không nhất thiết bằng số hàng của outer node

Trong `Nested Loop` thông thường, inner scan thường được gọi lại theo các hàng của outer input, nên dễ thấy `loops` gần số hàng outer. Tuy nhiên, có những node như `Materialize`/`Memoize`, điều kiện join, short-circuit, parallelism, caching hoặc plan shape làm việc đếm không đơn giản.

Hãy đọc **cây plan thật** và biết node nào được gọi lại, thay vì áp công thức “mọi inner loops bằng số outer rows” cho tất cả trường hợp.

## 5. Đọc đúng actual time = startup..total

Ví dụ:

~~~text
Index Scan ...
  (actual time=0.012..0.080 rows=20 loops=1)
~~~

Hai số thời gian tính bằng **mili giây (ms)**:

- **Startup time (0.012 ms):** thời gian đến khi node tạo ra **hàng đầu tiên** trong lượt thực thi. Với node không trả hàng, vẫn cần công việc để xác định không có hàng.
- **Total time (0.080 ms):** thời gian tới khi lượt thực thi của node hoàn tất/đầu ra đã được xử lý.

Khi `loops > 1`, những con số đó là **trung bình theo lượt**.

### 5.1. Startup thấp, total cao

~~~text
Index Scan
  (actual time=0.010..20.000 rows=100000 loops=1)
~~~

Node trả hàng đầu tiên khá nhanh, nhưng tiếp tục mất thời gian để trả những hàng sau. Đây là đặc điểm hay gặp ở các node có khả năng **stream** dữ liệu.

### 5.2. Startup gần total

~~~text
Sort
  (actual time=25.200..25.600 rows=100000 loops=1)
~~~

Sort phải thu thập/sắp xếp lượng dữ liệu đáng kể trước khi xuất hàng đầu tiên, nên startup lớn.

Một `HashAggregate` hoặc `Aggregate` chặn dữ liệu trong một số dạng cũng có thể có startup gần total vì phải xử lý đầu vào trước khi trả kết quả.

### 5.3. 0.000 không có nghĩa thực sự mất 0 thời gian

Với thao tác rất nhanh, số đo làm tròn tới ba chữ số thập phân có thể thành `0.000 ms`. Điều đó không chứng minh CPU/IO không tốn công.

### 5.4. Ký hiệu thời gian không phải khoảng tin cậy

`0.012..0.080` **không phải** “thời gian nằm trong khoảng từ 0,012 tới 0,080 ms do dao động”. Nó là **hai mốc startup và total của cùng node**, thường được diễn giải theo mỗi loop.

## 6. Công thức đọc total time khi loops lớn

Ví dụ minh họa:

~~~text
Index Scan ...
  (actual time=0.005..0.030 rows=2 loops=600)
~~~

Tổng output xấp xỉ:

\[
2\times600=1200\text{ hàng}
\]

Tổng thời gian được cộng cho các lần thực thi node, trong trường hợp chạy tuần tự và dựa vào số liệu per-loop:

\[
0{,}030\times600\approx18\text{ ms}
\]

Tổng thời gian startup được ghi theo từng lượt:

\[
0{,}005\times600\approx3\text{ ms}
\]

### 6.1. Đây không phải thời gian Execution Time

Ngay cả khi một node tích lũy khoảng 18 ms, toàn query còn:

- Node cha và các node khác.
- Chi phí executor khởi tạo/kết thúc.
- Các hoạt động không được phản ánh hoàn toàn qua phép cộng giản đơn.
- Parallelism, scheduling, instrumentation và JIT khi có.

`Execution Time` được báo cáo ở cuối plan là thời gian thực thi statement theo cách PostgreSQL đo; không bằng tổng `actual total time × loops` của mọi node.

### 6.2. Tình huống song song

Khi nhiều worker cùng làm việc, thời gian tích lũy của các worker có thể **lớn hơn wall-clock elapsed time**, vì các worker tiêu thụ CPU/chờ IO **đồng thời**. Đừng dùng công thức ở trên như đồng hồ chính xác cho parallel plan.

## 7. Time của node bao gồm thời gian node con

Trong plan tree, `actual time` của node cha thường là thời gian **inclusive**: việc node cha hoàn tất có thể cần chờ/call node con, nên bao gồm thời gian làm việc của các node con.

Ví dụ:

~~~text
Aggregate
  (actual time=12.00..12.01 rows=1 loops=1)
  -> Seq Scan on orders
       (actual time=0.02..10.40 rows=50000 loops=1)
~~~

Nếu lấy `12.01 + 10.40 = 22.41 ms` rồi nói “hai node này tiêu tốn 22,41 ms” thì đã **đếm trùng** phần lớn thời gian scan nằm trong aggregate.

### 7.1. Inclusive vs exclusive

- **Inclusive time:** thời gian hoàn thành node tính cả công việc ở nhánh con cần thiết.
- **Exclusive/self time:** phần công việc của riêng node sau khi trừ ảnh hưởng của các node con, nếu việc tách đó có thể diễn giải phù hợp.

`EXPLAIN ANALYZE` ở dạng text **không mặc định hiển thị một cột self time đáng tin cậy cho mọi node**.

### 7.2. Không trừ thời gian máy móc

Đôi khi có thể lấy thời gian cha trừ con để có một ước lượng thô phần xử lý ngoài con trong một đoạn plan tuần tự đơn giản. Nhưng phép trừ dễ sai khi:

- Node con được gọi nhiều lần.
- Có parallel workers.
- Node được rescan hoặc materialize.
- Có overlap thời gian, blocking, instrumentation.
- Số liệu đã làm tròn hoặc cách quản lý node đặc biệt.

**Đừng dùng một phép trừ đơn giản như profiler chính xác** khi chưa hiểu executor và plan shape.

## 8. Ví dụ quan trọng: Nested Loop làm nhân loops

Giả sử một truy vấn lấy 500 khách và danh sách đơn của từng khách:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    o.amount
FROM perf_lab.customers AS c
JOIN perf_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id <= 500;
~~~

Một plan minh họa:

~~~text
Nested Loop
  (cost=0.58..5500.00 rows=12500 width=20)
  (actual time=0.025..16.800 rows=12500 loops=1)
  -> Index Only Scan using customers_pkey on customers c
       (cost=0.28..25.00 rows=500 width=4)
       (actual time=0.008..0.410 rows=500 loops=1)
       Index Cond: (customer_id <= 500)
  -> Index Scan using idx_orders_customer on orders o
       (cost=0.29..9.20 rows=25 width=16)
       (actual time=0.004..0.024 rows=25 loops=500)
       Index Cond: (customer_id = c.customer_id)
~~~

**Đây là số liệu minh họa cho cách đọc, không phải output cam kết từ lab.**

### 8.1. Outer scan

`customers` là nhánh **outer**:

~~~text
rows=500 loops=1
~~~

Executor lấy 500 khách làm đầu vào cho vòng lặp join.

### 8.2. Inner scan

`orders` là nhánh **inner**:

~~~text
rows=25 loops=500
~~~

Mỗi khách kích hoạt một index scan tìm đơn liên quan. Vì vậy:

\[
25 \text{ đơn/khách}\times500 \text{ khách}
=12.500 \text{ dòng}
\]

### 8.3. Total time của inner

`actual time=0.004..0.024` trên inner là **trung bình theo lượt**. Tổng các lượt inner khoảng:

\[
0{,}024\times500=12\text{ ms}
\]

Không nhìn thấy `0.024 ms` rồi kết luận scan orders “gần như miễn phí”: nó được gọi lại 500 lần.

### 8.4. Parent Nested Loop

~~~text
Nested Loop ... (actual time=0.025..16.800 rows=12500 loops=1)
~~~

Node cha trả tổng 12.500 dòng trong một lượt, và thời gian inclusive gần 16,8 ms trong ví dụ.

Không cộng `16.8 + 12 + 0.41` thành thời gian toàn query: parent đã bao gồm phần công việc ở con.

## 9. Nested Loop không tự động là plan xấu

Nhiều người thấy `loops=100000` liền cho rằng query tối ưu kém. Cần xem thêm:

- Mỗi lượt inner scan có rẻ không?
- Index Cond có chọn lọc và hợp lý không?
- Tổng số hàng đọc/đầu ra là bao nhiêu?
- Truy vấn có `LIMIT` nhỏ không?
- Hash Join/Merge Join có đáng giá hơn không?
- Dữ liệu có cache thuận lợi không?
- Ước lượng rows có sai nghiêm trọng không?

### 9.1. Nested Loop tốt

Outer có 10 hàng, inner dùng index tìm 1 hàng mỗi lượt:

~~~text
outer rows=10 loops=1
inner rows=1 loops=10
~~~

Đây thường là cách hợp lý nếu lookup nhanh.

### 9.2. Nested Loop đáng điều tra

Outer có 100.000 hàng; inner scan lại một bảng lớn, thiếu index chọn lọc:

~~~text
outer rows=100000 loops=1
inner rows=5000 loops=100000
~~~

Ngay cả khi inner có một số cache, lượng xử lý lặp có thể quá lớn. Cần nhìn `Rows Removed by Filter`, `BUFFERS` và tổng thời gian.

### 9.3. Không chọn join method chỉ bằng tên

Một `Hash Join` cũng có thể rất chậm nếu bảng build/hash lớn, dữ liệu lệch, tràn ra đĩa hoặc ước lượng sai. Tối ưu cần đo **plan cụ thể**, không áp quy tắc “Hash Join tốt, Nested Loop xấu”.

## 10. Ước lượng rows và sai lệch theo loops

Hai loại rows ở cùng node:

~~~text
(cost=0.29..9.20 rows=4 width=16)
(actual time=0.005..0.060 rows=80 loops=500)
~~~

Planner dự đoán **4 hàng mỗi lượt**, thực tế trung bình **80 hàng mỗi lượt**.

Hệ số chênh lệch:

\[
\frac{80}{4}=20
\]

Nếu 500 lượt xảy ra:

- Ước lượng tổng hàng inner: khoảng `4 × 500 = 2.000`.
- Thực tế tổng hàng inner: khoảng `80 × 500 = 40.000`.

Một **sai lệch 20 lần ở một node được gọi 500 lần** có thể khiến chi phí thực tế lớn hơn nhiều so với planner dự tính.

### 10.1. Hệ số estimate/actual

Với `estimated rows > 0` và `actual rows > 0`, có thể lấy:

\[
\text{actual-to-estimated ratio}
=
\frac{\text{actual rows per loop}}
{\text{estimated rows per loop}}
\]

Giá trị 1 là gần khớp; 10 nghĩa là thực tế gấp khoảng 10 lần dự đoán. Với các node có `rows=0` do làm tròn hoặc estimate tối thiểu đặc biệt, cần xem ngữ cảnh thay vì chia máy móc.

### 10.2. Cần so sánh cùng độ đo

Sai:

~~~text
estimated rows=4  (mỗi lượt)
actual rows=80 × loops=500 = 40000
-> kết luận sai lệch 10000 lần
~~~

Bạn đã so sánh **estimate per-loop** với **actual total across loops**.

Đúng:

~~~text
estimated rows per loop = 4
actual rows per loop = 80
-> sai lệch khoảng 20 lần
~~~

Hoặc nếu biết số lượt thực tế 500:

~~~text
estimated total với 500 lượt ≈ 4 × 500 = 2000
actual total ≈ 80 × 500 = 40000
-> sai lệch khoảng 20 lần
~~~

### 10.3. Nếu loops thực tế khác estimate về outer

Tổng công việc còn sai lệch bởi **số lượt inner** cũng có thể khác dự đoán. Planner có thể dự đoán outer 10 khách nhưng thực tế có 10.000 khách. Khi đó chi phí inner tăng do **hai yếu tố nhân**:

1. Nhiều lần inner scan hơn dự kiến.
2. Nhiều hàng mỗi inner scan hơn dự kiến.

Đó là lý do thường nên tìm **nút đầu tiên có estimated/actual cardinality lệch mạnh ở dưới cây plan**.

## 11. Vì sao ước lượng sai?

Những nguyên nhân thường gặp:

| Nguyên nhân | Dấu hiệu trong plan | Hướng xử lý |
| --- | --- | --- |
| Thống kê cũ | estimated rows khác actual trên bảng đã thay đổi lớn | `ANALYZE`, xem autovacuum |
| Dữ liệu phân bố lệch/skew | Một giá trị có số hàng bất thường | Xem MCV/histogram, statistics target |
| Các cột có tương quan | Filter nhiều cột bị giả định gần độc lập | Extended statistics khi phù hợp |
| Predicate dùng expression | Planner thiếu thống kê phù hợp cho biểu thức | Expression statistics/index, thống kê phù hợp |
| Join trên dữ liệu không đều | Join output lệch mạnh | Đánh giá phân bố khóa join, uniqueness |
| Giá trị tham số biến thiên | Một plan cho nhiều selectivity khác nhau | Đánh giá prepared statement generic/custom plans |
| LIMIT/early stop | Actual rows nhỏ vì node không đọc hết | Hiểu nhu cầu chỉ lấy vài hàng |
| Parallelism | Các hàng/time được chia giữa workers | Xem Workers và loops |

### 11.1. ANALYZE

~~~sql
ANALYZE perf_lab.orders;
~~~

`ANALYZE` cập nhật thống kê planner; nó **không tạo index**, không bảo đảm planner chọn một plan cụ thể và không sửa được mọi loại sai số thống kê.

### 11.2. Extended statistics

Khi nhiều cột có tương quan:

~~~sql
CREATE STATISTICS st_orders_customer_status
    (dependencies, mcv)
ON customer_id, status
FROM perf_lab.orders;

ANALYZE perf_lab.orders;
~~~

Extended statistics có thể hỗ trợ **một số kiểu ước lượng đa cột** ở tình huống phù hợp. Không mặc định rằng chúng giải quyết toàn bộ join misestimation; mức hỗ trợ phụ thuộc biểu thức, phiên bản và dạng query.

### 11.3. Ước lượng khác độ đúng

Một plan có estimated rows sai vẫn phải **trả kết quả SQL đúng** theo ngữ nghĩa query và isolation, nếu không có bug/hỏng dữ liệu. Sai estimate chủ yếu khiến planner chọn đường thực thi kém hiệu quả.

## 12. Đọc actual time trong Nested Loop

Xét:

~~~text
Nested Loop
  (actual time=0.020..150.000 rows=50000 loops=1)
  -> Seq Scan on customers
       (actual time=0.010..3.000 rows=2000 loops=1)
  -> Index Scan on orders
       (actual time=0.008..0.060 rows=25 loops=2000)
~~~

Inner scan có:

\[
0{,}060\text{ ms/loop}\times2000
=120\text{ ms}
\]

Đây là tổng thời gian xấp xỉ của 2.000 lượt inner trong ví dụ tuần tự. Node cha có `total=150 ms` và **bao gồm** thời gian thực thi các node con.

### 12.1. Tại sao thời gian parent lớn hơn tổng một child?

Parent còn:

- Lấy các outer rows.
- Gọi inner scan và điều phối lặp.
- Đánh giá join conditions.
- Tạo từng tuple kết quả.
- Gọi các executor nodes khác khi cần.

Đừng quy toàn bộ chênh lệch cho một tác vụ duy nhất mà chưa đo.

### 12.2. Nếu inner actual time rất thấp mà loops cực cao

Ngay cả `0.001 ms`/lượt × `1.000.000 lượt` là khoảng **1.000 ms** thời gian tích lũy. Đoạn nhỏ lặp hàng triệu lần có thể đáng kể.

Đây là một lý do phải đọc `loops` cùng `actual time`.

## 13. Startup time và node blocking

Không phải node nào cũng tạo ra hàng đầu tiên ngay.

### 13.1. Scan theo luồng

~~~text
Index Scan
  (actual time=0.010..8.000 rows=15000 loops=1)
~~~

Hàng đầu tiên có thể tới sau khoảng 0,010 ms; node tiếp tục trả hàng nhiều lần.

### 13.2. Sort phải thu thập đầu vào

~~~text
Sort
  (actual time=40.000..43.000 rows=15000 loops=1)
  Sort Key: amount DESC
  Sort Method: quicksort  Memory: 1200kB
  -> Seq Scan
       (actual time=0.020..13.000 rows=15000 loops=1)
~~~

`Sort` thường phải có đủ dữ liệu đầu vào để xác định thứ tự trước khi xuất dòng đầu. Startup của Sort vì vậy lớn, và bao gồm thời gian cần để đọc input.

### 13.3. Aggregate

~~~text
Aggregate
  (actual time=12.000..12.001 rows=1 loops=1)
  -> Seq Scan
       (actual time=0.010..9.000 rows=50000 loops=1)
~~~

Một aggregate tổng toàn bảng phải đọc đủ input trước khi biết `SUM` cuối, nên startup gần total.

Một số dạng aggregate/grouping có thể stream output theo nhóm tùy plan; không áp câu “mọi Aggregate đều phải đọc toàn bộ tập dữ liệu trước hàng đầu” cho mọi biến thể.

### 13.4. LIMIT thường dừng nhánh con sớm

~~~text
Limit
  (actual time=0.025..0.100 rows=10 loops=1)
  -> Index Scan
       (actual time=0.020..0.090 rows=10 loops=1)
~~~

Nếu dữ liệu lấy đúng theo thứ tự index, `LIMIT 10` có thể chỉ yêu cầu 10 hàng.

Nếu trước LIMIT là Sort không phù hợp, executor có thể vẫn cần đọc **rất nhiều hàng** để xác định 10 giá trị tốt nhất.

## 14. LIMIT không có nghĩa bảng chỉ có từng ấy hàng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM perf_lab.orders
ORDER BY amount DESC
LIMIT 10;
~~~

Một plan minh họa:

~~~text
Limit (actual time=12.500..12.510 rows=10 loops=1)
  -> Sort (actual time=12.495..12.500 rows=10 loops=1)
       Sort Key: amount DESC
       Sort Method: top-N heapsort  Memory: 26kB
       -> Seq Scan on orders
            (actual time=0.010..4.000 rows=50000 loops=1)
~~~

Đừng thấy `Sort actual rows=10` mà nói “Sort chỉ xem 10 hàng”. Sort đã **nhận khoảng 50.000 hàng** từ Seq Scan, xử lý đủ để chọn top 10, nhưng chỉ **trả 10 hàng lên Limit** do parent không yêu cầu thêm.

### 14.1. rows mô tả output, không phải input

Khi một node có `LIMIT` phía trên, `actual rows` của nó có thể phản ánh số hàng **thực tế được parent yêu cầu**, không phải toàn bộ số hàng nó có thể tạo ra nếu parent yêu cầu đọc hết.

### 14.2. Sort Method bổ sung ngữ cảnh

`quicksort`, `top-N heapsort`, `external merge` và số liệu memory/disk (tùy plan) giúp hiểu node phải sắp theo kiểu nào. Một Sort cần spill ra disk thường là hướng điều tra quan trọng khi thời gian lớn.

## 15. Cẩn thận với câu “actual rows = 0”

Node:

~~~text
Index Scan ...
  (actual time=0.015..0.015 rows=0 loops=1)
~~~

đã chạy nhưng không trả hàng trong lượt đó.

Nhưng:

~~~text
Index Scan ...
  (actual time=0.002..0.002 rows=0 loops=1000)
~~~

không nhất thiết có **0 hàng trên tất cả các lượt**, vì giá trị per-loop có thể bị làm tròn từ trung bình nhỏ hơn 0,5.

### 15.1. loops=0 / never executed

Nếu nhánh plan không được chạy do điều kiện không kích hoạt, PostgreSQL có thể hiển thị:

~~~text
(never executed)
~~~

Hoặc biểu diễn tương đương tùy format/phiên bản. Điều đó khác với **đã chạy nhưng không tìm thấy hàng**.

### 15.2. Vì sao node không được gọi?

Ví dụ:

- Nhánh bên trong `Nested Loop` khi outer input rỗng.
- `CASE`, điều kiện hoặc subplan được short-circuit trong những tình huống được phép.
- Một phần plan bị parent dừng sớm do `LIMIT`.
- Một nhánh plan không được chọn trong logic executor đặc biệt.

Không suy “index không hoạt động” chỉ vì node nằm trong plan nhưng `never executed`.

## 16. Rows Removed by Filter và Rows Removed by Join Filter

Ngoài `actual rows`, plan có thể hiện số hàng bị loại bởi predicate.

~~~text
Seq Scan on orders
  (actual time=0.020..3.500 rows=3000 loops=1)
  Filter: (status = 'paid')
  Rows Removed by Filter: 47000
~~~

Node có thể đã kiểm tra khoảng 50.000 hàng và trả 3.000 hàng lên parent.

### 16.1. Rows Removed by Filter cũng có per-loop semantics

Khi node được chạy nhiều lần, giá trị `Rows Removed by Filter` ở dạng text thường được trình bày **trung bình trên mỗi loop**, có thể bị làm tròn. Cần đọc kèm `loops` như `actual rows`.

### 16.2. Join Filter khác Filter

Trong một `Nested Loop` hoặc join khác:

~~~text
Join Filter: (c.region = o.region)
Rows Removed by Join Filter: 5000
~~~

Các hàng có thể thỏa một phần điều kiện truy cập nhưng không thỏa điều kiện join. Chúng bị loại **trước khi node trả output**, không xuất hiện trong `actual rows` của join.

### 16.3. Index Cond, Recheck Cond, Filter

| Trường | Tác dụng |
| --- | --- |
| `Index Cond` | Điều kiện được dùng để truy cập qua index |
| `Filter` | Điều kiện bổ sung kiểm tra sau bước truy cập của node |
| `Recheck Cond` | Điều kiện cần kiểm tra lại trên hàng trong một số kế hoạch như bitmap |
| `Rows Removed by Filter` | Số hàng bị loại ở bước filter được báo cáo |
| `Rows Removed by Index Recheck` | Hàng bị loại khi kiểm tra lại index condition trong các trường hợp thích hợp |

Các trường giúp giải thích vì sao node **đọc nhiều nhưng trả ít**.

## 17. Actual time và BUFFERS: hai góc nhìn khác nhau

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

Plan có thể báo:

~~~text
Buffers: shared hit=35 read=12
~~~

`hit` nghĩa là các lượt truy cập buffer phù hợp đã được thỏa từ shared buffers; `read` nghĩa là các block phải được đưa vào shared buffers ở thời điểm tương ứng. Một `read` không nhất thiết là một lần chạm **đĩa vật lý chậm**: hệ điều hành có page cache, và PostgreSQL report số block/lượt truy cập theo cơ chế instrumentation.

### 17.1. Buffer counts không phải số hàng

Một block chứa nhiều tuple; một tuple có thể dẫn tới truy cập index và heap khác nhau. Do đó không lấy:

~~~text
shared hit=50
~~~

rồi nói node đọc đúng 50 hàng.

### 17.2. Buffers cũng có tính inclusive

Buffer usage được trình bày tại node có thể phản ánh hoạt động ở node và nhánh con. Không cộng mọi dòng `Buffers` từ cha xuống con thành tổng chung vì dễ **đếm trùng**.

### 17.3. Những thông số BUFFERS phổ biến

| Dữ liệu | Gợi ý |
| --- | --- |
| `shared hit` | Trang shared buffer đã có |
| `shared read` | Trang phải đọc vào shared buffers |
| `shared dirtied` | Trang shared buffer bị đánh dấu dirty |
| `shared written` | Trang shared buffer được ghi trong quá trình quan sát |
| `temp read / written` | Truy cập các block file tạm, thường liên quan spill |
| `local hit/read` | Truy cập local buffers, ví dụ temporary tables |

Không suy một query ghi dữ liệu sẽ có cùng số `dirtied` và `written`: dirty buffer có thể được flush ở thời điểm khác.

### 17.4. BUFFERS và actual time bổ trợ nhau

Hai query cùng trả 100 hàng:

- Query A: `shared hit=5`, `actual total=0.2 ms`.
- Query B: `shared read=5000`, `actual total=150 ms`.

Kết hợp thời gian và buffer footprint giúp phân biệt query làm nhiều I/O logic hơn. Tuy nhiên, phải đo nhiều lần và xem cache/trạng thái hệ thống trước khi quy nguyên nhân duy nhất.

## 18. I/O timing và cách đo

Nếu cấu hình phù hợp (ví dụ `track_io_timing` được bật), kế hoạch với `BUFFERS` có thể báo thêm:

~~~text
I/O Timings: shared read=12.345
~~~

Đây là thời gian I/O được đo ở phạm vi tương ứng, **khác** `actual time` của toàn node và khác số block. Thống kê I/O timing có chi phí đo, phụ thuộc platform/cấu hình.

### 18.1. Thiếu I/O Timings không chứng minh không có I/O

Nếu `track_io_timing` không được bật, `I/O Timings` có thể không xuất hiện dù `shared read` vẫn có. Không suy “không có đọc đĩa” chỉ vì không thấy dòng timing.

### 18.2. Nhiều shared hit nhưng query vẫn chậm

Query có thể CPU-bound vì:

- Filter/expression đắt.
- Join nhân quá nhiều hàng.
- Sort hoặc aggregate nặng.
- Nhiều loops.
- Contention nội bộ.

**Buffer hit cao không đồng nghĩa execution nhanh**.

## 19. Planning Time và Execution Time

Cuối plan thường có:

~~~text
Planning Time: 0.310 ms
Execution Time: 18.720 ms
~~~

### 19.1. Planning Time

Là thời gian lập plan được PostgreSQL báo cáo, theo phạm vi instrumentation của phiên bản và tùy chọn. Không nhất thiết bao gồm toàn bộ thời gian phía client hay mọi overhead trước/sau khi truy vấn đi qua ứng dụng.

### 19.2. Execution Time

Là thời gian PostgreSQL báo cho việc thực thi statement theo cơ chế đo của `EXPLAIN ANALYZE`. Đây thường là con số tổng quan hữu ích nhất để so sánh lần chạy trên server **trong điều kiện đo tương đương**.

### 19.3. Nó có giống thời gian client nhìn thấy?

Không bắt buộc:

~~~text
Ứng dụng
  -> network request
  -> PostgreSQL planning
  -> PostgreSQL execution
  -> network response
  -> decode dữ liệu / deserialize trong driver
  -> render UI
~~~

Latency phía ứng dụng có thể cao hơn vì network, queue, kết nối, nhận kết quả, parsing và hiển thị. `EXPLAIN ANALYZE` cũng có overhead của instrumentation và không truyền toàn bộ các hàng như truy vấn thường.

### 19.4. Không đo một lần rồi kết luận chắc chắn

Hãy thử nhiều lần trong điều kiện có thể kiểm soát, quan sát giá trị trung vị/phân phối, cache và workload. Một lần nhanh hơn 2 ms không nhất thiết chứng minh thay đổi index tốt hơn.

## 20. Overhead do EXPLAIN ANALYZE

Đo thời gian ở từng node đòi hỏi PostgreSQL thu thập đồng hồ và đếm sự kiện. Đối với query gồm rất nhiều lượt nhỏ, instrumentation timing có thể tạo overhead đáng kể.

### 20.1. TIMING OFF

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM perf_lab.orders
WHERE status = 'paid';
~~~

`TIMING OFF` tắt **đo thời gian ở từng node** để giảm overhead, nhưng vẫn thu thập những số liệu hữu ích như:

- `actual rows`.
- `loops`.
- Các số liệu đếm/BUFFERS được bật.
- `Execution Time` tổng thể trong kết quả khi có `ANALYZE`, theo cơ chế hỗ trợ.

Không kỳ vọng nhìn thấy `actual time=...` của mỗi node khi timing bị tắt.

### 20.2. So sánh hai kiểu đo

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING ON)
SELECT COUNT(*)
FROM perf_lab.orders;

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM perf_lab.orders;
~~~

Hai kế hoạch có thể khác thời gian reported vì overhead instrumentation/caching. Dùng `TIMING OFF` khi mục đích chính là xem **cardinality và loops**, đặc biệt ở plan có nhiều node gọi lặp rất nhanh.

### 20.3. ANALYZE không phải lệnh ANALYZE thống kê

Đừng nhầm:

~~~sql
ANALYZE perf_lab.orders;
~~~

với:

~~~sql
EXPLAIN (ANALYZE)
SELECT ...;
~~~

Lệnh thứ nhất thu thập statistics cho planner; tùy chọn thứ hai **thực thi query và đo**.

## 21. Parallel plan: rows, loops và thời gian phải đọc thận trọng

PostgreSQL có thể chạy một số plan song song với **leader** và **parallel workers**.

Một kế hoạch minh họa:

~~~text
Finalize Aggregate
  (actual time=20.0..22.0 rows=1 loops=1)
  -> Gather
       (actual time=19.0..21.9 rows=3 loops=1)
       Workers Planned: 2
       Workers Launched: 2
       -> Partial Aggregate
            (actual time=17.5..17.6 rows=1 loops=3)
            -> Parallel Seq Scan on orders
                 (actual time=0.010..14.5 rows=16667 loops=3)
~~~

### 21.1. Partial Aggregate loops=3

Hai workers và leader có thể cùng thực hiện một phần công việc, nên ở ví dụ `Partial Aggregate` có `loops=3`. Đây là số lượt thực thi node được tính trong output tổng hợp; không đơn giản là “truy vấn chạy 3 lần từ ứng dụng”.

### 21.2. Parallel Seq Scan rows=16667 loops=3

Tổng hàng được quét/đầu ra **xấp xỉ** `16.667 × 3 ≈ 50.001`, phản ánh tổng 50.000 hàng với làm tròn.

Nhưng các worker có thể xử lý **lượng hàng không cân bằng**; dòng tổng hợp chỉ cho trung bình.

### 21.3. Time song song không nhân rồi dùng làm latency

`actual total time=14.5 ms loops=3` không có nghĩa node kéo dài **43,5 ms wall-clock**. Một phần lớn công việc chạy song song; tổng thời gian tích lũy của các participant có thể lớn hơn thời gian đồng hồ.

### 21.4. Workers Planned vs Workers Launched

Nếu:

~~~text
Workers Planned: 4
Workers Launched: 2
~~~

planner dự kiến bốn worker nhưng thực tế chỉ khởi chạy hai. Điều này có thể thay đổi hiệu năng và phân phối workload; hãy xem giới hạn parallel workers và tải hệ thống.

### 21.5. Xem worker details

Trong những plan và tùy chọn phù hợp:

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT SUM(amount)
FROM perf_lab.orders;
~~~

Kết quả có thể hiển thị chi tiết từng worker dưới một số node. Cách hiển thị phụ thuộc phiên bản và lựa chọn execution. **Không giả định luôn có Workers output** cho query nhỏ hay cho mọi câu SQL.

## 22. Gather và Gather Merge

`Gather` nhận kết quả từ các worker rồi đưa lên phần còn lại của plan. `Gather Merge` còn có nhiệm vụ bảo tồn/ghép những luồng kết quả **có thứ tự tương thích**.

~~~text
Gather
  -> Parallel Seq Scan
~~~

không tự bảo đảm một thứ tự cuối:

~~~sql
ORDER BY created_at
~~~

Nếu truy vấn cần thứ tự, planner phải tổ chức plan bảo đảm đúng `ORDER BY`, có thể thông qua `Sort`/`Gather Merge` hoặc cách khác.

### 22.1. Time ở Gather

Time của `Gather` gồm việc nhận/hợp nhất đầu ra theo cơ chế node, phụ thuộc worker scheduling, trao đổi tuple và phía trên có yêu cầu thêm hàng hay không.

Nếu `Gather` lâu, đừng kết luận CPU của Gather tự thân gây toàn bộ độ trễ; thời gian inclusive có thể phản ánh chờ các workers.

### 22.2. Parallel plan và IO

Các worker có thể cùng tạo áp lực memory bandwidth/I/O. Tổng `Buffers` và per-worker values cần được hiểu là hoạt động logic tích lũy, không quy trực tiếp thành số block vật lý duy nhất hay thành số mili giây serial.

## 23. Materialize và Memoize: tránh đọc lại hoặc cache theo tham số

Trong plan, PostgreSQL có thể dùng node `Materialize`:

~~~text
Nested Loop
  -> outer input
  -> Materialize (actual ... rows=1000 loops=50)
       -> Seq Scan on small_table
            (actual ... rows=1000 loops=1)
~~~

### 23.1. Đọc đúng

`Materialize` có thể được gọi nhiều lần (`loops=50`) nhưng child `Seq Scan` chỉ thực sự đọc nguồn một lượt rồi vật liệu hóa kết quả cho các lần quét tiếp theo.

**Không nhìn `Materialize loops=50` rồi nhân toàn bộ chi phí Seq Scan với 50** khi Seq Scan chỉ `loops=1`.

### 23.2. Materialization có giá

Cache trung gian có thể tiêu thụ memory và đôi khi file tạm. Đọc `Buffers`, memory/temp usage và thời gian thay vì kết luận mọi Materialize đều tối ưu.

### 23.3. Memoize

Một plan parameterized inner scan có thể dùng `Memoize` để cache kết quả lookup theo khóa tham số:

~~~text
Memoize
  Cache Key: o.customer_id
  Cache Mode: logical
  Hits: 980
  Misses: 20
  Evictions: 0
  Overflows: 0
  Memory Usage: 16kB
  -> Index Scan ...
~~~

**Số liệu minh họa.** Memoize có thể được gọi 1.000 lần nhưng Index Scan child chỉ cần thực thi cho khoảng những lần miss/cache refill, tùy trường hợp.

### 23.4. Không đồng nhất loops ở cha và con

Trong một số plan:

~~~text
Memoize loops=1000
Index Scan child loops=20
~~~

Điều này không mâu thuẫn. Cache có thể thỏa **980 lượt** mà không gọi child scan.

Khi phân tích tổng số hàng và thời gian, hãy **nhân theo loops của chính node đó**, không dùng loops của cha để nhân cho mọi con.

## 24. SubPlan và InitPlan

Truy vấn có subquery có thể sinh `SubPlan` hoặc `InitPlan`.

### 24.1. SubPlan tương quan

~~~sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.amount)
        FROM perf_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS max_amount
FROM perf_lab.customers AS c
WHERE c.customer_id <= 100;
~~~

Tùy cách planner biến đổi truy vấn, subquery có thể là một `SubPlan` được thực thi nhiều lần theo outer rows.

~~~text
Seq Scan on customers c
  (actual ... rows=100 loops=1)
  SubPlan 1
    -> Aggregate (actual ... rows=1 loops=100)
         -> Index Scan (actual ... rows=25 loops=100)
~~~

Nếu xuất hiện plan dạng này, đây là dấu hiệu cần đọc **loops của subplan** và tổng thời gian tích lũy.

### 24.2. InitPlan

Subquery không tương quan có thể được tính một lần như một `InitPlan` hoặc được tối ưu theo cách khác:

~~~sql
SELECT *
FROM perf_lab.orders
WHERE amount > (
    SELECT AVG(amount)
    FROM perf_lab.orders
);
~~~

Không giả định mọi subquery đều chạy một lần/hàng. **Kế hoạch thực tế quyết định** có subplan lặp hay không.

### 24.3. Viết lại SQL không luôn cần thiết

Đôi khi planner tự biến đổi subquery thành join hoặc aggregate hiệu quả. Chỉ refactor khi plan và workload cho thấy vấn đề cụ thể, không theo quy tắc “mọi correlated subquery đều chậm”.

## 25. Hash Join: hiểu startup và số hàng

Một plan minh họa:

~~~text
Hash Join
  (actual time=6.00..25.00 rows=50000 loops=1)
  Hash Cond: (o.customer_id = c.customer_id)
  -> Seq Scan on orders o
       (actual time=0.02..7.00 rows=50000 loops=1)
  -> Hash
       (actual time=5.20..5.25 rows=2000 loops=1)
       Buckets: 4096  Batches: 1  Memory Usage: 200kB
       -> Seq Scan on customers c
            (actual time=0.02..2.50 rows=2000 loops=1)
~~~

`Hash` phải xây cấu trúc từ input phía build. Startup của Hash Join có thể gồm thời gian xây hash table trước khi bắt đầu trả join rows.

### 25.1. Batches và spill

Nếu hash table lớn hơn nguồn memory phù hợp, PostgreSQL có thể xử lý theo nhiều batch và sử dụng file tạm; `Batches` và `temp read/written` là tín hiệu điều tra.

### 25.2. Hash Join rows không phải số bucket

`rows=50000` trên `Hash Join` là **output rows**, không phải số hash entries, bucket hoặc số lần probe.

### 25.3. Không cộng thời gian Hash và Hash Join

`actual time` của Hash Join bao gồm công việc xây hash từ child. Cộng tất cả node times sẽ đếm trùng như ở các loại join khác.

## 26. Sort và GroupAggregate: số hàng thay đổi theo cấp

Một truy vấn:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM perf_lab.orders
GROUP BY customer_id
ORDER BY total_amount DESC
LIMIT 10;
~~~

Có thể có chuỗi node:

~~~text
Limit (actual ... rows=10 loops=1)
  -> Sort (actual ... rows=10 loops=1)
       Sort Key: (sum(amount)) DESC
       Sort Method: top-N heapsort
       -> HashAggregate (actual ... rows=2000 loops=1)
            Group Key: customer_id
            -> Seq Scan on orders
                 (actual ... rows=50000 loops=1)
~~~

### 26.1. Mỗi số rows trả lời một câu hỏi

- Scan: có 50.000 hàng đơn.
- Aggregate: có 2.000 nhóm khách.
- Sort: trong trường hợp có LIMIT, chỉ chuyển 10 hàng được yêu cầu lên parent, **không có nghĩa chỉ nhận 10 nhóm để sort**.
- Limit: trả 10 hàng cuối cùng.

### 26.2. Vì sao cần đọc cả cây?

Nhìn mỗi `Limit rows=10` che khuất công việc quét 50.000 đơn và gộp 2.000 nhóm. Thời gian thực thi được quyết định bởi **công việc ở tất cả các tầng**.

## 27. Kịch bản lab: tạo dữ liệu đủ để quan sát loops

Những lệnh dưới đây tạo schema riêng trong database thực hành. Chúng không ghi vào bảng production.

### 27.1. Tạo hai bảng

~~~sql
CREATE SCHEMA perf_lab;

CREATE TABLE perf_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    segment text NOT NULL
);

CREATE TABLE perf_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES perf_lab.customers(customer_id),
    amount numeric(12, 2) NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL
);
~~~

### 27.2. Tạo 2.000 khách

~~~sql
INSERT INTO perf_lab.customers (
    customer_id, full_name, segment
)
SELECT
    g,
    'Customer ' || g::text,
    CASE
        WHEN g % 5 = 0 THEN 'vip'
        ELSE 'regular'
    END
FROM generate_series(1, 2000) AS s(g);
~~~

### 27.3. Tạo 50.000 đơn

~~~sql
INSERT INTO perf_lab.orders (
    order_id, customer_id, amount, status, created_at
)
SELECT
    g::bigint,
    ((g - 1) % 2000) + 1,
    (1000 + (g % 500) * 100)::numeric(12, 2),
    CASE
        WHEN g % 4 = 0 THEN 'cancelled'
        ELSE 'paid'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
      + (g * INTERVAL '1 minute')
FROM generate_series(1, 50000) AS s(g);
~~~

Phân bố này được tạo có chủ đích: **mỗi khách có 25 đơn**. `status` có 37.500 đơn paid và 12.500 đơn cancelled. Các mẫu plan có thể khác vì chi phí và cấu hình thực thi.

### 27.4. Tạo chỉ mục phù hợp

~~~sql
CREATE INDEX idx_orders_customer
ON perf_lab.orders (customer_id);

CREATE INDEX idx_orders_customer_created
ON perf_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);

ANALYZE perf_lab.customers;
ANALYZE perf_lab.orders;
~~~

### 27.5. Kiểm tra số liệu nguồn

~~~sql
SELECT COUNT(*) AS n_customers
FROM perf_lab.customers;

SELECT
    COUNT(*) AS n_orders,
    COUNT(DISTINCT customer_id) AS n_customers_with_orders
FROM perf_lab.orders;

SELECT
    MIN(n_orders) AS min_per_customer,
    MAX(n_orders) AS max_per_customer
FROM (
    SELECT customer_id, COUNT(*) AS n_orders
    FROM perf_lab.orders
    GROUP BY customer_id
) AS x;
~~~

Kỳ vọng lần lượt là 2.000 khách, 50.000 đơn, và mỗi khách có đúng 25 đơn.

## 28. Lab 1: so sánh estimate và actual ở Index Scan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id, customer_id, amount
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

Với dữ liệu lab, query này trả **25 đơn** nếu chưa thay đổi dữ liệu. Trong plan, tìm node scan orders:

~~~text
Index Scan / Bitmap Heap Scan / Seq Scan ...
  (cost=... rows=... width=...)
  (actual time=... rows=25 loops=1)
~~~

**Loại scan không được cố định**: planner có quyền chọn hình thức khác nhau. Khi chỉ một query đọc ít hàng, có thể thấy Index Scan hoặc Bitmap access tùy cấu hình/dữ liệu.

### Câu hỏi

1. Estimated rows là bao nhiêu?
2. Actual rows bao nhiêu?
3. Loops bao nhiêu?
4. Có `Index Cond` không, hay chỉ `Filter`?
5. `shared hit/read` bao nhiêu?

Lưu lại số liệu **bạn đo được**, không thay bằng con số minh họa trong bài.

## 29. Lab 2: Nested Loop và tổng số lượt inner

Một cách quan sát inner lookup theo mỗi khách là dùng `LATERAL` với `LIMIT`:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    recent.order_id,
    recent.amount
FROM perf_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT
        o.order_id,
        o.amount
    FROM perf_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent
WHERE c.customer_id <= 100
ORDER BY c.customer_id, recent.order_id DESC;
~~~

Truy vấn cho tối đa ba đơn mới nhất của từng khách trong 100 khách. Trong dữ liệu lab, mỗi khách có 25 đơn, nên kết quả cuối có **300 hàng**.

Kế hoạch có khả năng thể hiện:

- Outer scan trả 100 khách.
- Một `Limit` và `Index Scan` phía trong, được gọi lặp theo `customer_id`.
- Inner `rows≈3 loops≈100`.
- Node join trả khoảng 300 hàng.

### 29.1. Nếu không ra Nested Loop như kỳ vọng

Planner và phiên bản có thể tối ưu theo cách khác. Mục tiêu là đọc **plan thật**, không ép output của máy trùng kế hoạch minh họa. `LATERAL` tương quan với giới hạn top-N mỗi khách thường giúp lộ rõ cấu trúc lookup lặp, nhưng không phải mọi hệ thống đều có cùng plan.

### 29.2. Tính số hàng tích lũy

Nếu inner:

~~~text
(actual time=0.004..0.020 rows=3 loops=100)
~~~

thì output tích lũy inner khoảng:

\[
3\times100=300
\]

Thời gian tích lũy inner khoảng:

\[
0{,}020\times100=2\text{ ms}
\]

Đây là **ước lượng từ số liệu minh họa**, không phải kết quả đo của lab.

### 29.3. Kết quả 300 dòng không có nghĩa bảng chỉ đọc 300 dòng

Index có thể định vị nhanh ba đơn đầu mỗi khách. Nếu thiếu index thích hợp, executor có thể phải đọc nhiều hơn để sort/tìm top-N cho từng khách. Hãy kiểm tra child scans, `Sort Method` và `BUFFERS`.

## 30. Lab 3: LIMIT, Sort và số hàng thực xử lý

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM perf_lab.orders
ORDER BY amount DESC, order_id
LIMIT 10;
~~~

Vì lab chưa có index trên `(amount DESC, order_id)`, planner có thể chọn scan rồi sort/top-N; cần xem plan thực tế.

Ghi các số:

| Node | Cần ghi |
| --- | --- |
| Scan đơn | Actual rows, loops, Buffers |
| Sort | Actual rows, Sort Method, Memory/Disk |
| Limit | Actual rows |
| Toàn statement | Execution Time |

**Bài học:** `Limit rows=10` không có nghĩa chỉ phải nhìn 10 đơn. Khi cần tìm top-N theo cột chưa index phù hợp, executor có thể phải xem tất cả 50.000 đơn.

### 30.1. Tạo index đối chứng

Trong lab, có thể thêm:

~~~sql
CREATE INDEX idx_orders_amount_desc
ON perf_lab.orders (amount DESC, order_id ASC);

ANALYZE perf_lab.orders;
~~~

Chạy lại `EXPLAIN (ANALYZE, BUFFERS)`. Không đảm bảo planner chọn index; hãy so sánh `Sort` có còn không, số block, thời gian và chi phí duy trì index khi ghi.

## 31. Lab 4: Aggregate và giảm hàng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(amount) AS total_amount
FROM perf_lab.orders
GROUP BY customer_id
ORDER BY total_amount DESC
LIMIT 10;
~~~

Truy vấn phải tính tổng từ các đơn của 2.000 khách rồi lấy top 10 khách theo tổng tiền. Dữ liệu ban đầu có 50.000 đơn, nhưng output chỉ 10 hàng.

Plan có thể gồm:

~~~text
Limit ... rows=10
  -> Sort ... rows=10
       -> HashAggregate ... rows=2000
            -> Seq Scan ... rows=50000
~~~

**Không nhầm “query trả 10 hàng” với “executor chỉ làm việc trên 10 hàng”.**

### 31.1. GroupAggregate vs HashAggregate

Tùy plan, PostgreSQL có thể dùng `HashAggregate`, `GroupAggregate` với input sắp theo group keys, hoặc parallel partial/final aggregates. Mỗi node có startup/total/rows khác nhau. Hãy so sánh **cardinality qua từng tầng**.

## 32. Lab 5: TIMING ON và TIMING OFF

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING ON)
SELECT
    c.customer_id,
    (
        SELECT SUM(o.amount)
        FROM perf_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS total
FROM perf_lab.customers AS c
WHERE c.customer_id <= 100;
~~~

So sánh với:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT
    c.customer_id,
    (
        SELECT SUM(o.amount)
        FROM perf_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS total
FROM perf_lab.customers AS c
WHERE c.customer_id <= 100;
~~~

Quan sát:

- `actual rows` và `loops` của subplan có tiếp tục xuất hiện không?
- Per-node `actual time` còn xuất hiện khi timing off không?
- `Execution Time` thay đổi thế nào qua nhiều lần?
- Sự khác biệt đó có thể bị ảnh hưởng bởi cache/instrumentation không?

### 32.1. Không dùng TIMING OFF để chứng minh query nhanh hơn

Tắt instrumentation không tự tối ưu SQL của ứng dụng. Nó chỉ **thay đổi cách đo và chi phí thu thập timing** trong phiên `EXPLAIN ANALYZE`.

## 33. Lab 6: quan sát Parallel Seq Scan

Trên 50.000 hàng, planner có thể không thấy parallel scan có lợi. Bạn có thể thử tăng kích thước lab hoặc đặt tham số **chỉ trong session lab** để tìm hiểu:

~~~sql
BEGIN;

SET LOCAL max_parallel_workers_per_gather = 2;
SET LOCAL min_parallel_table_scan_size = '0';
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;

EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT SUM(amount)
FROM perf_lab.orders;

ROLLBACK;
~~~

Các `SET LOCAL` chỉ nhằm quan sát trong môi trường thí nghiệm. **Không ép planner như vậy trên production chỉ để nhìn thấy workers.** Parallel plan còn tùy tính parallel-safe của biểu thức, tính khả dụng của workers và giới hạn PostgreSQL.

### 33.1. Câu hỏi

1. Có `Gather` hoặc `Gather Merge` không?
2. `Workers Planned` và `Workers Launched` bằng bao nhiêu?
3. `Parallel Seq Scan` có `loops` bao nhiêu?
4. Tổng hàng tích lũy từ worker nodes có gần 50.000 không?
5. Vì sao không dùng tổng `actual total time × loops` như wall-clock query time?

## 34. Lab 7: chênh lệch estimates và skew

Để hiểu tác động của một giá trị phổ biến bất thường, có thể thêm đơn cho một khách trong **database lab**:

~~~sql
INSERT INTO perf_lab.orders (
    order_id, customer_id, amount, status, created_at
)
SELECT
    (1000000 + g)::bigint,
    42,
    (5000 + g % 200)::numeric(12,2),
    'paid',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
      + g * INTERVAL '1 second'
FROM generate_series(1, 5000) AS s(g);
~~~

Giờ khách 42 có khoảng **5.025 đơn**, trong khi các khách khác vẫn 25 đơn.

### 34.1. Trước và sau ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;

ANALYZE perf_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

So sánh estimated rows với actual rows. Sau `ANALYZE`, planner có thể nhận biết giá trị phổ biến qua thống kê MCV, nhưng không cam kết mọi estimate chính xác tuyệt đối.

### 34.2. Truy vấn khách thường

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 43;
~~~

Khách 43 vẫn chỉ có 25 đơn. So sánh plan của khách nhiều đơn và khách thường, tránh cho rằng một kế hoạch là tối ưu cho mọi giá trị tham số.

### 34.3. Đừng chạy bước này trước khi hoàn thành các lab giả định 50.000 đơn

Sau khi thêm 5.000 đơn, tổng số đơn thành **55.000** và những số lượng nguồn ban đầu không còn đúng. Nếu muốn lặp lại bài từ đầu, thực hiện trên database lab mới hoặc tái tạo schema theo quy trình cho phép.

## 35. Cách kiểm tra cấu trúc plan dạng JSON

Định dạng text dễ đọc, nhưng để công cụ phân tích tự động truy cập từng node có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT order_id
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

Kết quả là một cấu trúc JSON chứa cây `Plan` và các trường như `Actual Rows`, `Actual Loops`, `Actual Startup Time`, `Actual Total Time` cùng các estimates.

### 35.1. Dùng JSON để tránh parse chuỗi mơ hồ

Một công cụ đọc JSON có thể duyệt node tree và:

1. Lấy `Node Type`.
2. Đọc `Plan Rows`.
3. Đọc `Actual Rows` và `Actual Loops`.
4. Đọc thời gian startup/total.
5. Tính tỉ lệ estimated/actual khi cần.

**Không chia nhỏ một kế hoạch JSON theo dòng text và đoán cấu trúc từ số dấu cách** nếu có thể dùng parser JSON.

### 35.2. JSON không tự sửa vấn đề per-loop

Đổi format **không thay đổi ngữ nghĩa** của `Actual Rows` và `Actual Total Time`: chúng vẫn phải đọc cùng `Actual Loops`, và parallel plans vẫn cần xét phân phối worker/leader.

### 35.3. Tránh thu thập dữ liệu nhạy cảm

`EXPLAIN` với `VERBOSE` hoặc output từ truy vấn thực tế có thể chứa tên bảng/cột/biểu thức và đôi khi giá trị literal từ SQL. Khi chia sẻ plan ra bên ngoài tổ chức, xem lại thông tin có thể nhạy cảm.

## 36. Quy trình đọc một EXPLAIN ANALYZE từ dưới lên

Thực hành theo thứ tự:

### Bước 1. Đọc tổng quan

Tìm `Planning Time`, `Execution Time`, số node `Sort`, `Hash`, `Nested Loop`, `Gather`, `Buffers` và các dấu hiệu disk spill.

### Bước 2. Đọc node lá

Nhìn `Seq Scan`/`Index Scan`/`Bitmap Heap Scan`:

- Estimated rows so với actual rows **theo loop**.
- `Index Cond`/`Filter`.
- `Rows Removed by Filter`.
- `Buffers` và `actual time`.

### Bước 3. Tìm nhân loops

Với những node `loops≫1`:

- Ai gọi lại node?
- Trung bình bao nhiêu hàng mỗi loop?
- Tổng hàng và thời gian tích lũy xấp xỉ bao nhiêu?
- Có `Materialize`/`Memoize` giúp tránh đọc lại child không?

### Bước 4. Đọc join và cardinality qua từng tầng

So sánh:

- Outer input.
- Inner input (per-loop).
- Join output.
- Group aggregate output.
- Limit output.

### Bước 5. Phân biệt inclusive time

Không cộng mọi total time của các node cha con. Xem `Execution Time` như tổng quan, và dùng node timings để xác định **nhánh** nào tốn công.

### Bước 6. Nếu có parallel plan

Kiểm tra workers planned/launched, loops trên parallel children, chi tiết worker và tính song song của thời gian.

### Bước 7. Đặt giả thuyết cải thiện

Ví dụ:

- Cập nhật statistics/extended statistics vì estimate lệch.
- Tạo index cho điều kiện tìm kiếm/lookup lặp.
- Viết lại query để tránh inner scan hàng nghìn lượt.
- Giảm số hàng được đưa vào sort/aggregate khi đúng nghiệp vụ.
- Điều chỉnh bộ nhớ cho workload phù hợp khi có spill.

### Bước 8. Đo lại trong điều kiện tương đương

So sánh số hàng, loops, buffers, spill và execution time qua nhiều lần. Không đánh đổi **độ đúng kết quả** để đổi lấy plan trông đẹp.

## 37. Những lỗi diễn giải phổ biến

### Lỗi 1: actual rows là tổng hàng

Sai khi node có nhiều loops. Phải hiểu `actual rows` là **trung bình mỗi loop** trong output text thông dụng.

### Lỗi 2: loops là số lần ứng dụng gửi query

Sai. Loops thuộc việc gọi node **nội bộ executor**.

### Lỗi 3: actual time=0.050 nghĩa toàn node chỉ tiêu 0,050 ms

Nếu `loops=1000`, tổng công việc tuần tự của node có thể xấp xỉ `50 ms`, chưa kể cấu trúc cha con và parallelism.

### Lỗi 4: Cộng tất cả thời gian của node

Sai vì timings của node cha thường **inclusive** và có thể đã bao gồm công việc node con.

### Lỗi 5: estimated rows so với actual rows × loops

Sai đơn vị. Phải so **per-loop estimate với per-loop actual**; rồi xét chênh lệch loops riêng.

### Lỗi 6: actual rows=0 loops=1000 là không có hàng nào

Có thể sai do **làm tròn trung bình**.

### Lỗi 7: Limit rows=10 chứng minh executor chỉ đọc 10 hàng

Sai nếu phía dưới có Sort/Aggregate cần đọc rất nhiều đầu vào.

### Lỗi 8: Sort actual rows=10 chứng minh chỉ sort 10 hàng

Sai; Sort có thể nhận 50.000 hàng rồi chỉ trả 10 theo yêu cầu của parent.

### Lỗi 9: Nested Loop luôn chậm

Sai; với outer nhỏ và inner index lookup rẻ, Nested Loop thường rất hợp lý.

### Lỗi 10: Hash Join luôn nhanh

Sai; hash build lớn, spill, skew và sai estimate vẫn có thể gây chậm.

### Lỗi 11: Parallel node time × workers là Execution Time

Sai; các workers chạy đồng thời, có overhead và chia việc không đều.

### Lỗi 12: Buffers hit=100 nghĩa đọc đúng 100 hàng

Sai; buffer counts phản ánh truy cập **block**, không phải số tuple.

### Lỗi 13: Buffers read luôn là 100 lần đĩa vật lý

Sai; còn OS cache và đặc tính đo lường. Cần tách logical block reads với physical storage I/O.

### Lỗi 14: Planning Time + Execution Time bằng latency API

Không đủ. Client/network/driver/UI còn thời gian riêng.

### Lỗi 15: EXPLAIN ANALYZE không làm thay đổi DB

Sai với statement ghi. DML sẽ được thực thi; cần thận trọng với rollback, trigger và side effects.

### Lỗi 16: TIMING OFF làm SQL thật nhanh hơn

Sai; nó chủ yếu giảm chi phí instrumentation trong lần EXPLAIN.

### Lỗi 17: ANALYZE statistics và EXPLAIN ANALYZE là một

Sai: một lệnh thu thập statistics; một tùy chọn chạy query để đo.

### Lỗi 18: Chỉ đọc root node là đủ

Sai; root trả 10 hàng vẫn có thể cần scan hàng triệu hàng ở child.

### Lỗi 19: Seq Scan luôn là lỗi thiếu index

Sai; quét tuần tự có thể rẻ nhất cho bảng nhỏ hoặc truy vấn trả tỷ lệ lớn dữ liệu.

### Lỗi 20: Index Cond và Filter hoàn toàn tương đương

Sai; điều kiện dùng để tìm trong index khác điều kiện được áp sau khi lấy hàng.

### Lỗi 21: Materialize loops=100 nghĩa Seq Scan child cũng 100 loops

Sai; chính child có số loops riêng, có thể chỉ là 1.

### Lỗi 22: Muốn tối ưu chỉ tăng work_mem

Không phải mọi query chậm do Sort/Hash spill. Nếu vấn đề là 100.000 inner lookups hoặc estimate sai, tăng memory có thể không giải quyết đúng nguyên nhân.

## 38. Bài tập thực hành

Đọc các đoạn `EXPLAIN` giả lập sau; tính số liệu xấp xỉ khi có làm tròn. Các bài SQL dùng schema `perf_lab` đã tạo. Đây là bài đọc plan và lập luận, không phải nội dung QA.

### Bài 1. Actual rows và loops

~~~text
Index Scan (actual time=0.010..0.040 rows=5 loops=200)
~~~

Node trả tổng khoảng bao nhiêu hàng? Tổng thời gian tích lũy khoảng bao nhiêu ms trong mô hình tuần tự?

### Bài 2. Startup và total

~~~text
Sort (actual time=35.000..36.000 rows=10000 loops=1)
~~~

Hai số `35` và `36` mang ý nghĩa gì? Có phải khoảng sai số đo không?

### Bài 3. Estimated vs actual

~~~text
(cost=0.20..8.00 rows=2 width=16)
(actual time=0.01..0.10 rows=40 loops=500)
~~~

Sai lệch cardinality theo mỗi loop khoảng bao nhiêu lần?

### Bài 4. Đừng so sai đơn vị

Với bài 3, người khác tính `40×500/2=10000` rồi nói estimate sai 10.000 lần. Hãy giải thích lỗi lập luận.

### Bài 5. Inclusive time

~~~text
Aggregate (actual time=12.00..12.01 rows=1 loops=1)
  -> Seq Scan (actual time=0.02..10.00 rows=50000 loops=1)
~~~

Có được cộng `12.01 + 10.00` để tính Execution Time không? Vì sao?

### Bài 6. Nested Loop

~~~text
Nested Loop (actual ... rows=3000 loops=1)
  -> Seq Scan on customers (actual ... rows=100 loops=1)
  -> Index Scan on orders (actual ... rows=30 loops=100)
~~~

Vì sao inner `loops=100`? Tổng hàng inner khoảng bao nhiêu?

### Bài 7. Row count bằng 0

~~~text
Index Scan (actual ... rows=0 loops=1000)
~~~

Có thể khẳng định index không trả hàng trong cả 1.000 lượt không?

### Bài 8. never executed

Khác biệt giữa `never executed` và `rows=0 loops=1`?

### Bài 9. LIMIT

~~~text
Limit (actual ... rows=10)
  -> Sort (actual ... rows=10)
       -> Seq Scan (actual ... rows=50000)
~~~

Vì sao Sort có thể đã xử lý 50.000 hàng dù chỉ trả 10?

### Bài 10. Filter

~~~text
Seq Scan (actual ... rows=100 loops=1)
  Rows Removed by Filter: 9900
~~~

Node đã kiểm tra khoảng bao nhiêu hàng?

### Bài 11. Buffers

`shared hit=500 read=20` có nghĩa đã đọc đúng 520 hàng không? `read=20` có nghĩa đúng 20 lần disk seek vật lý không?

### Bài 12. Parallel

~~~text
Parallel Seq Scan (actual ... rows=20000 loops=4)
~~~

Tổng output xấp xỉ bao nhiêu? Có được nhân thời gian node với 4 rồi gọi là wall time?

### Bài 13. Workers

`Workers Planned: 4`, `Workers Launched: 2` biểu thị gì?

### Bài 14. Materialize

~~~text
Materialize (actual ... rows=1000 loops=50)
  -> Seq Scan (actual ... rows=1000 loops=1)
~~~

Có phải child Seq Scan thực thi 50 lần không?

### Bài 15. Memoize

Nếu `Memoize Hits=980, Misses=20` trong 1.000 lookup, vì sao index scan phía dưới có thể chỉ có khoảng 20 loops?

### Bài 16. Hash

`HashAggregate rows=2000` phía trên `Seq Scan rows=50000` có bất thường không? Vì sao?

### Bài 17. Tổng thể

`Planning Time=0.5 ms`, `Execution Time=25 ms` nhưng API trả về sau 70 ms. Nêu ít nhất ba thành phần có thể giải thích chênh lệch.

### Bài 18. TIMING OFF

Viết câu `EXPLAIN` vẫn đo `actual rows` và `loops` nhưng tránh đo timing mỗi node.

### Bài 19. DML

Vì sao phải cẩn thận với `EXPLAIN ANALYZE UPDATE`? Viết khối an toàn trên bảng lab để rollback thay đổi có tính giao dịch.

### Bài 20. Statistics

Nếu estimated rows lệch quá lớn sau khi nạp dữ liệu, trước tiên bạn kiểm tra thống kê bằng lệnh gì?

### Bài 21. Index lookup

Viết query tìm tất cả orders của khách 42 và chạy `EXPLAIN (ANALYZE, BUFFERS)`. Ghi những trường nào để biết index có giúp được không?

### Bài 22. LATERAL

Viết query lấy ba đơn mới nhất của mỗi khách trong 100 khách đầu. Vì sao inner lookup có thể `loops≈100`?

### Bài 23. Generic plan

Khi cùng một prepared statement chạy với khách có 25 đơn và khách có 5.025 đơn, vì sao một plan chung có thể không tối ưu cho cả hai?

### Bài 24. Sort vs ordered scan

Muốn lấy top 10 đơn theo `amount DESC, order_id`, chỉ mục nào đáng thử? Những node nào trên plan có thể thay đổi?

### Bài 25. SubPlan

Một correlated SubPlan báo `Aggregate loops=2000`. Vì sao phải cân nhắc số lượt thực thi dù aggregate chỉ trả một hàng/loop?

### Bài 26. Plan JSON

Viết câu lệnh trả EXPLAIN ở định dạng JSON, đồng thời có actual rows/loops và buffers.

### Bài 27. Đọc thời gian

~~~text
Index Scan
  (actual time=0.007..0.035 rows=2 loops=1000)
~~~

Thời gian tích lũy xấp xỉ của node này khi thực thi tuần tự là bao nhiêu? Vì sao không coi đó là Execution Time toàn query?

### Bài 28. Tìm nguyên nhân gốc

Plan có outer estimate 10 hàng nhưng actual 10.000, inner ước lượng 1 hàng/loop nhưng actual 20. Nêu hai kiểu khuếch đại công việc.

## 39. Lời giải tham khảo

### Bài 1

Tổng hàng khoảng `5×200=1000`; tổng thời gian theo lượt khoảng `0.040×200=8 ms`. Không coi 8 ms là độ trễ toàn statement.

### Bài 2

`35 ms` là thời gian tới khi Sort trả hàng đầu; `36 ms` là thời gian tới khi node hoàn tất lượt. Đây không phải khoảng tin cậy/độ lệch chuẩn.

### Bài 3–4

Sai lệch per-loop là `40/2=20 lần`. Phép tính 10.000 lần sai vì lấy **actual toàn 500 lượt** so với **estimated mỗi lượt**.

### Bài 5

Không. Total của Aggregate thường inclusive, chứa công việc của Seq Scan. Cộng sẽ đếm trùng. Xem `Execution Time` và từng nhánh.

### Bài 6

Inner được gọi theo 100 hàng khách outer trong cấu trúc Nested Loop minh họa. Tổng hàng inner khoảng `30×100=3000`.

### Bài 7–8

`rows=0 loops=1000` có thể do làm tròn trung bình, vẫn có lượt trả hàng. `never executed` là node không được gọi; `rows=0 loops=1` đã chạy nhưng không trả output.

### Bài 9

Sort cần đọc input để xác định top 10; child Seq Scan trả 50.000 hàng cho Sort, nhưng parent Limit chỉ yêu cầu 10 output.

### Bài 10

Khoảng `100+9900=10000` hàng được xét trong ví dụ một loop; dữ liệu thực có thể còn chi tiết instrumentation khác.

### Bài 11

Không. Buffers phản ánh các lượt truy cập **block**, không phải số hàng. `read=20` không tương đương đúng 20 lần disk seek vật lý do filesystem cache/I/O behavior.

### Bài 12–13

Tổng output khoảng `20000×4=80000`. Worker/leader có thể chạy đồng thời, không nhân timing rồi gọi wall time. `Planned=4` là dự kiến, `Launched=2` là số workers thực tế khởi chạy.

### Bài 14–15

Materialize có thể phục vụ 50 lượt từ dữ liệu đã lưu, child Seq Scan chỉ chạy một lượt. Memoize với 980 hits tránh gọi child cho những lookup ấy, còn khoảng 20 misses cần child work (tùy eviction/caching thật).

### Bài 16

Không bất thường: 50.000 đơn được gộp thành 2.000 nhóm khách nên aggregate trả 2.000 hàng.

### Bài 17

Chênh lệch có thể do mạng, tạo/mượn connection, driver decode/serialization, application code, hàng đợi, truyền dữ liệu và render UI; số đo EXPLAIN còn có overhead instrumentation khác truy vấn thường.

### Bài 18

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM perf_lab.orders;
~~~

### Bài 19

`EXPLAIN ANALYZE` thật sự chạy UPDATE:

~~~sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
UPDATE perf_lab.orders
SET amount = amount + 1
WHERE order_id = 1;
ROLLBACK;
~~~

Rollback bảo vệ thay đổi transactional nhưng không đảm bảo hoàn tác side effects ngoài DB hay sequence.

### Bài 20

~~~sql
ANALYZE perf_lab.orders;
~~~

Sau đó chạy lại plan và đọc estimate/actual; nếu vẫn lệch, xem skew, correlation, expression statistics và phương thức join.

### Bài 21

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

Ghi `Index Cond`/`Filter`, estimated rows, actual rows, loops, Buffers, actual time và Execution Time; không khẳng định index được chọn nếu chưa nhìn plan.

### Bài 22

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id, recent.order_id
FROM perf_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM perf_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 3
) AS recent
WHERE c.customer_id <= 100;
~~~

Inner lookup tương quan có thể phải tìm ba đơn cho **từng khách**, nên được gọi khoảng 100 lượt trong một Nested Loop plan điển hình.

### Bài 23

Hai khách có selectivity khác nhau rất nhiều. Một generic plan/ước lượng chung có thể chọn scan/join method phù hợp khách thường nhưng kém với khách cực nhiều đơn (hoặc ngược lại). Cần đo theo tập tham số thực và hiểu custom/generic plan behavior.

### Bài 24

~~~sql
CREATE INDEX idx_orders_top_amount
ON perf_lab.orders (amount DESC, order_id ASC);
~~~

Rồi đo lại query `ORDER BY amount DESC, order_id LIMIT 10`. Index ordered scan có thể tránh một Sort, nhưng còn phụ thuộc selectivity và chi phí truy cập heap.

### Bài 25

Một aggregate có thể chỉ trả 1 hàng mỗi loop nhưng chạy 2.000 lần, khiến tổng input scans/CPU/IO tích lũy lớn. Đọc loops cùng actual time của aggregate **và** child.

### Bài 26

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

### Bài 27

Khoảng `0.035×1000=35 ms` tổng các lượt node trong ví dụ tuần tự. Time node có thể inclusive và chỉ là một phần của executor; tổng query xem `Execution Time`.

### Bài 28

(1) Outer thực tế nhiều hơn 1.000 lần dự đoán (10 → 10.000), khiến inner được gọi nhiều hơn. (2) Inner trả 20 lần hàng/loop (1 → 20). Hai sai lệch nhân nhau có thể làm tổng công việc thực tế vượt rất xa dự đoán.

## 40. Bảng tra cứu nhanh

| Dòng trong plan | Cách đọc đúng |
| --- | --- |
| `cost=a..b` | Ước lượng startup/total theo đơn vị chi phí planner, **không phải ms** |
| `rows=E` trong `cost` | Ước lượng node output mỗi lượt |
| `width=W` | Kích thước output row trung bình ước lượng (byte) |
| `actual time=x..y` | Startup/total đo được, ms **trung bình mỗi loop** |
| `actual rows=A` | Output rows trung bình mỗi loop; có thể làm tròn |
| `loops=L` | Số lần node thực thi |
| `A × L` | Xấp xỉ tổng output rows của node |
| `y × L` | Xấp xỉ thời gian tích lũy của các lượt node khi phù hợp; **không phải wall time query** |
| `Rows Removed by Filter` | Số hàng bị loại bởi Filter, thường báo cáo per-loop |
| `Index Cond` | Điều kiện truy cập index |
| `Filter` | Điều kiện xử lý thêm trên hàng |
| `Sort Method` | Cách sort, memory/disk sử dụng |
| `Buckets/Batches` | Thông tin xây hash và khả năng batching |
| `Buffers: shared hit/read` | Truy cập block/buffer, không phải số row |
| `temp read/written` | Dấu hiệu sử dụng file tạm, có thể do spill |
| `Workers Planned/Launched` | Số parallel workers dự kiến/thực |
| `Planning Time` | Thời gian lập kế hoạch được báo cáo |
| `Execution Time` | Thời gian thực thi tổng statement theo EXPLAIN instrumentation |
| `TIMING OFF` | Bỏ per-node timing, vẫn xem cardinality/loops với ANALYZE |
| `FORMAT JSON` | Kế hoạch có cấu trúc để phân tích tự động |

## 41. Checklist phân tích một kế hoạch thực thi

1. Query có thật sự chậm **trên server** hay chỉ chậm ở client/network?
2. Đang đọc `EXPLAIN` hay `EXPLAIN ANALYZE`?
3. Câu lệnh có ghi dữ liệu không? Đã kiểm soát tác dụng phụ nếu dùng `ANALYZE`?
4. `Execution Time` và `Planning Time` bao nhiêu?
5. Node lá nào đọc nhiều hàng/block nhất?
6. Các `Index Cond` và `Filter` có phù hợp với ý định không?
7. Estimated rows vs actual rows **theo mỗi loop** khác nhau bao nhiêu?
8. Node nào có `loops` lớn và ai khiến nó được gọi lại?
9. Tổng output hàng của node khoảng `rows × loops` là bao nhiêu?
10. Tổng thời gian tích lũy của node lặp có đáng kể không?
11. Có cộng trùng thời gian cha/con khi giải thích không?
12. `LIMIT` có che khuất Sort/Scan toàn bảng phía dưới không?
13. `Rows Removed by Filter` hoặc Join Filter có nhiều không?
14. `Sort`/`Hash` có memory/disk spill không?
15. Có `Materialize`/`Memoize` tránh gọi child lại không?
16. Có parallel plan không? Workers launched có bằng planned không?
17. Đã phân biệt CPU, IO, lock và client overhead chưa?
18. Có cần cập nhật statistics hoặc kiểm tra skew/correlation không?
19. Đã đo nhiều lần với dữ liệu và workload đại diện chưa?
20. Sau thay đổi, có kiểm tra **kết quả SQL đúng** và plan mới chưa?

## 42. Tổng kết

Trong `EXPLAIN ANALYZE` của PostgreSQL, **`actual rows` và `actual time` không thể được hiểu đúng nếu tách khỏi `loops`**. Khi một node chạy nhiều lượt, định dạng text báo số hàng và thời gian **trung bình cho mỗi lượt**. Để ước lượng lượng hàng đi ra qua mọi lượt, nhân `actual rows × loops`, nhớ có thể có sai số do làm tròn. Với time, `actual total time × loops` có thể giúp hiểu chi phí tích lũy trong một plan tuần tự, nhưng **không phải** thời gian wall-clock của toàn query, đặc biệt khi có parallelism.

Ba nguyên tắc thiết yếu:

1. **So sánh estimated rows và actual rows cùng đơn vị per-loop.** Nếu sai lệch lớn, tìm nguyên nhân thống kê, skew, correlation, hoặc sai lệch cardinality ở node phía dưới.
2. **Đọc cây thực thi, không cộng thời gian node cha với node con.** Node cha thường có thời gian inclusive; `Nested Loop` nhân số lượt inner, trong khi `Materialize`/`Memoize` có thể giảm số lượt child.
3. **Đặt thời gian vào ngữ cảnh.** `actual time=startup..total` mô tả tiến trình xuất hàng của node; `Planning Time`/`Execution Time` là thống kê tổng thể; `BUFFERS`, `Sort Method`, worker details và `TIMING OFF` giúp đánh giá CPU/I/O/instrumentation một cách thận trọng.

Khi thấy một dòng `actual time=0.03 rows=3 loops=10000`, câu hỏi nên hỏi không phải “0,03 ms có nhỏ không?”, mà là: **“Node này được gọi 10.000 lần vì sao, đã trả tổng bao nhiêu hàng, đã tích lũy bao nhiêu công việc, và planner dự đoán đúng số lượt/hàng chưa?”**. Đó là cách biến con số của `EXPLAIN ANALYZE` thành quyết định tối ưu có cơ sở.

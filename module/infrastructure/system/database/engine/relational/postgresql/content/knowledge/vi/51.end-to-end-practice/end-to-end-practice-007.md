# Chẩn đoán truy vấn chậm bằng EXPLAIN ANALYZE và chỉ mục

## 1. Mục tiêu và cách tiếp cận

Khi một truy vấn PostgreSQL chạy chậm, cần xác định thời gian đang tiêu tốn ở đâu: đọc quá nhiều hàng, lọc sau khi đọc, nối bảng với số vòng lặp lớn, sắp xếp dữ liệu, ghi hoặc đọc dữ liệu tạm, hay dùng ước lượng thống kê sai. `EXPLAIN ANALYZE` cho biết kế hoạch mà PostgreSQL đã chọn và số liệu thực tế khi chạy kế hoạch đó. Chỉ mục có thể giảm lượng dữ liệu phải đọc hoặc giúp truy vấn lấy dữ liệu theo đúng thứ tự, nhưng một chỉ mục mới không tự động làm mọi truy vấn nhanh hơn.

Quy trình có thể tóm tắt như sau:

1. Xác định câu SQL, tham số, tần suất chạy và thời gian chậm thực tế.
2. Thu thập kế hoạch bằng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện.
3. Đọc kế hoạch từ các nút con lên nút cha, so sánh số hàng ước lượng với số hàng thực tế.
4. Tìm nút tiêu tốn nhiều công việc nhất và xác định nguyên nhân.
5. Chọn cách sửa phù hợp: cập nhật thống kê, điều chỉnh câu SQL hoặc tạo chỉ mục.
6. Chạy lại cùng truy vấn và so sánh số liệu trước/sau.

Hãy dùng cùng bộ tham số và dữ liệu có quy mô gần với môi trường thật. Kế hoạch có thể khác nhau khi dữ liệu, phân bố giá trị, thống kê, cấu hình hoặc trạng thái cache thay đổi.

## 2. Thu thập kế hoạch thực thi

### 2.1. Phân biệt EXPLAIN và EXPLAIN ANALYZE

`EXPLAIN` yêu cầu PostgreSQL lập kế hoạch nhưng không thực thi câu SQL. Lệnh này hữu ích để xem dự định của planner:

```sql
EXPLAIN
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42;
```

`EXPLAIN ANALYZE` thực thi câu lệnh rồi đưa thêm số liệu thực tế vào kết quả. Khi cần xem cả lượng block được truy cập, dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42;
```

Các tùy chọn thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| `ANALYZE` | Thực thi câu lệnh và ghi nhận số liệu thực tế như thời gian, số hàng, số vòng lặp |
| `BUFFERS` | Hiển thị block được tìm thấy trong shared buffers, phải đọc vào shared buffers và dữ liệu tạm |
| `VERBOSE` | Hiển thị thêm thông tin chi tiết, tên cột hoặc biểu thức đầy đủ |
| `SETTINGS` | Hiển thị các thiết lập planner khác giá trị mặc định có liên quan đến kế hoạch |
| `TIMING OFF` | Giảm chi phí đo thời gian riêng ở từng nút; vẫn có tổng Execution Time |

**Lưu ý quan trọng:** `EXPLAIN ANALYZE` thật sự chạy câu lệnh. Với `UPDATE`, `DELETE` hoặc `INSERT`, dữ liệu sẽ bị thay đổi. Có thể thử trong transaction rồi `ROLLBACK`:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE orders
SET status = 'archived'
WHERE created_at < DATE '2024-01-01';

ROLLBACK;
```

Rollback không hoàn tác được mọi tác động bên ngoài transaction, chẳng hạn trigger gọi dịch vụ bên ngoài hoặc gửi thông báo. Với câu lệnh ghi có tác động phụ, hãy thử trên môi trường kiểm thử hoặc dùng `EXPLAIN` không có `ANALYZE` trước.

### 2.2. Chọn truy vấn cần điều tra

Nếu extension `pg_stat_statements` đã được bật, có thể dùng nó để tìm câu SQL tiêu tốn nhiều thời gian tổng cộng hoặc có thời gian trung bình cao:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

`total_exec_time` và `mean_exec_time` được tính bằng mili giây. Truy vấn có thời gian trung bình cao có thể cần điều tra riêng; truy vấn chạy rất thường xuyên với thời gian mỗi lần vừa phải cũng có thể chiếm phần lớn tổng thời gian của hệ thống. Hãy lấy đúng câu SQL và giá trị tham số đại diện trước khi phân tích.

## 3. Đọc kết quả EXPLAIN ANALYZE

Kết quả là một cây kế hoạch. Các nút lá thường đọc dữ liệu từ bảng hoặc chỉ mục; kết quả được truyền lên các nút cha để lọc, nối, sắp xếp hoặc giới hạn số hàng. Đọc từ các nút lá lên trên giúp hiểu dữ liệu đi qua từng bước.

Ví dụ về một kế hoạch:

```text
Limit  (cost=1250.00..1250.13 rows=50 width=24)
       (actual time=18.420..18.431 rows=50 loops=1)
  ->  Sort  (cost=1250.00..1260.00 rows=4000 width=24)
            (actual time=18.418..18.424 rows=50 loops=1)
        Sort Key: created_at DESC
        Sort Method: top-N heapsort  Memory: 32kB
        ->  Seq Scan on orders
              (cost=0.00..1100.00 rows=4000 width=24)
              (actual time=0.030..17.200 rows=320 loops=1)
              Filter: (customer_id = 42)
              Rows Removed by Filter: 199680
              Buffers: shared hit=850
Planning Time: 0.240 ms
Execution Time: 18.470 ms
```

Các con số trên chỉ minh họa cách đọc. Kế hoạch thật phụ thuộc dữ liệu và môi trường.

### 3.1. cost, rows và width

Một dòng nút thường có dạng:

```text
(cost=startup_cost..total_cost rows=estimated_rows width=estimated_width)
```

- `startup_cost` là chi phí ước lượng trước khi nút có thể trả về hàng đầu tiên.
- `total_cost` là chi phí ước lượng để hoàn tất nút.
- `rows` là số hàng PostgreSQL dự đoán nút sẽ trả về.
- `width` là kích thước trung bình ước lượng của mỗi hàng, tính theo byte.

Cost là đơn vị nội bộ dùng để so sánh kế hoạch, **không phải mili giây**. Không thể đọc `cost=1000` rồi kết luận truy vấn mất 1.000 ms. Planner chọn kế hoạch dựa trên mô hình chi phí và thống kê mà nó có.

### 3.2. actual time, actual rows và loops

Khi có `ANALYZE`, nút có thêm số liệu thực tế:

```text
(actual time=first_row_ms..last_row_ms rows=actual_rows loops=loop_count)
```

- `actual time` thể hiện thời gian thực tế đến hàng đầu tiên và đến khi nút hoàn tất, tính bằng mili giây.
- `rows` là số hàng thực tế trung bình mỗi lần nút được chạy.
- `loops` là số lần nút được chạy.

Khi `loops > 1`, có thể nhân `rows × loops` để hình dung tổng số hàng nút đã trả qua các lượt chạy. Ví dụ `rows=5 loops=10000` cho thấy nút trả trung bình 5 hàng trong mỗi lượt và được gọi 10.000 lần. Đây có thể là dấu hiệu đáng chú ý trong một Nested Loop.

Thời gian của nút cha thường bao gồm công việc của các nút con. Vì vậy, không cộng thời gian của mọi dòng trong cây để tính tổng thời gian; hãy xem `Execution Time` ở cuối và dùng thời gian từng nút để định vị phần việc đáng chú ý.

### 3.3. Buffers và các chỉ dấu đọc/ghi

Khi bật `BUFFERS`, PostgreSQL báo số block được truy cập:

| Chỉ dấu | Cách hiểu |
|---|---|
| `shared hit` | Block đã có trong shared buffers |
| `shared read` | Block phải được đọc vào shared buffers; dữ liệu vẫn có thể đã nằm trong cache của hệ điều hành |
| `shared dirtied` | Block trong shared buffers bị đánh dấu đã thay đổi |
| `shared written` | Block được ghi từ shared buffers |
| `temp read/written` | Block của dữ liệu tạm được đọc/ghi, thường liên quan sort hoặc hash vượt bộ nhớ cho phép |

Số `shared read` lớn cho thấy truy vấn phải nạp nhiều block vào shared buffers, nhưng không đủ để kết luận tất cả đều đọc trực tiếp từ thiết bị lưu trữ vật lý. Nếu `temp read` hoặc `temp written` xuất hiện nhiều, hãy xem các nút Sort hoặc Hash có đang tràn ra đĩa hay không.

Số liệu buffer ở nút cha có thể bao gồm hoạt động của các nút con. Đừng cộng tất cả các dòng buffer như thể chúng độc lập.

## 4. Nhận diện nguyên nhân trong kế hoạch

### 4.1. Ước lượng số hàng sai lệch lớn

So sánh `rows` ước lượng với `actual rows`. Nếu planner dự đoán vài hàng nhưng thực tế trả về hàng trăm nghìn, lựa chọn join, thứ tự join hoặc cách đọc dữ liệu tiếp theo có thể không phù hợp.

Nguyên nhân thường gặp:

- Thống kê cũ sau khi dữ liệu thay đổi mạnh hoặc vừa nạp hàng loạt.
- Một cột có phân bố giá trị lệch, nhưng thống kê chưa mô tả đủ tốt.
- Hai cột có tương quan, trong khi planner ước lượng chúng như các điều kiện độc lập.
- Biểu thức hoặc kiểu dữ liệu khiến planner khó ước lượng.

Thử cập nhật thống kê:

```sql
ANALYZE orders;
```

Nếu nhiều cột có tương quan, extended statistics có thể cải thiện ước lượng:

```sql
CREATE STATISTICS orders_customer_status_stats
    (dependencies, mcv)
    ON customer_id, status
    FROM orders;

ANALYZE orders;
```

Chỉ tạo thống kê mở rộng khi kế hoạch và phân bố dữ liệu cho thấy cần thiết. Thống kê tốt hơn có thể làm planner chọn kế hoạch phù hợp hơn mà không cần thêm chỉ mục.

### 4.2. Seq Scan không mặc định là xấu

`Seq Scan` đọc lần lượt các hàng của bảng. Nó thường hợp lý khi:

- Bảng nhỏ.
- Truy vấn cần phần lớn hàng trong bảng.
- Điều kiện lọc có độ chọn lọc thấp, tức là trả về tỷ lệ lớn dữ liệu.
- Đọc tuần tự rẻ hơn việc đi qua chỉ mục rồi truy cập nhiều vị trí rời rạc trong heap.

Trong ví dụ ở trên, `Seq Scan` đọc khoảng 200.000 hàng nhưng chỉ giữ lại 320 hàng. Nếu truy vấn này thường xuyên chạy và bảng lớn, có thể cần chỉ mục phù hợp với điều kiện lọc. Tuy nhiên, nếu bảng chỉ có vài trăm hàng hoặc điều kiện trả về phần lớn bảng, Seq Scan vẫn có thể là lựa chọn tốt nhất.

### 4.3. Filter và Index Cond

- `Filter` là điều kiện được kiểm tra sau khi nút đã lấy hàng.
- `Index Cond` là điều kiện được dùng để tìm phạm vi phù hợp trong chỉ mục.
- `Rows Removed by Filter` cho biết có bao nhiêu hàng bị loại bởi điều kiện lọc tại nút đó.

Nếu nhiều hàng bị loại bởi Filter, hãy xem có thể đưa điều kiện vào chỉ mục hay không. Khi đó, chỉ mục có thể tránh đọc các hàng không cần thiết ngay từ đầu. Không phải điều kiện nào cũng có thể chuyển thành Index Cond; điều này phụ thuộc loại chỉ mục, toán tử và cách viết biểu thức.

### 4.4. Join và số vòng lặp

Ba kiểu join thường gặp:

| Nút | Đặc điểm | Khi thường phù hợp |
|---|---|---|
| Nested Loop | Với mỗi hàng bên ngoài, tìm hàng tương ứng ở phía trong | Tập bên ngoài nhỏ và phía trong có đường truy cập hiệu quả, thường là chỉ mục |
| Hash Join | Tạo hash table từ một phía rồi dò bằng phía còn lại | Nối các tập dữ liệu lớn bằng điều kiện bằng nhau |
| Merge Join | Nối hai đầu vào đã được sắp theo khóa nối | Hai đầu vào đã có thứ tự phù hợp hoặc chi phí sắp xếp chấp nhận được |

Nested Loop không phải lỗi. Nhưng nếu phía ngoài có hàng chục nghìn hàng và nút bên trong có `loops=10000`, hãy kiểm tra liệu mỗi lượt có đang quét quá nhiều dữ liệu hay không. Một chỉ mục trên khóa nối ở phía trong có thể giúp giảm công việc. Với Hash Join, xem số batch và buffer tạm; nhiều batch hoặc temp I/O có thể cho thấy hash table không vừa bộ nhớ được cấp.

### 4.5. Sort và dữ liệu tạm

Nút `Sort` có thể sắp xếp trong bộ nhớ hoặc dùng file tạm. Kết quả thường có dòng `Sort Method` và `Memory` hoặc thông tin đĩa. Sort tốn kém có thể xuất hiện khi:

- Truy vấn sắp xếp nhiều hàng nhưng chỉ lấy một phần nhỏ.
- Không có chỉ mục cung cấp thứ tự phù hợp.
- Dữ liệu trung gian quá lớn.
- Bộ nhớ dành cho sort không đủ, khiến PostgreSQL phải dùng file tạm.

Nếu truy vấn lọc theo một khóa rồi sắp xếp theo khóa khác, chỉ mục nhiều cột có thể vừa hỗ trợ lọc vừa cung cấp thứ tự. Đừng tăng `work_mem` trên toàn hệ thống chỉ dựa vào một kế hoạch; một truy vấn có thể có nhiều nút sort/hash và nhiều phiên chạy đồng thời, làm tổng bộ nhớ tăng đáng kể.

## 5. Ví dụ: tối ưu truy vấn đơn hàng theo khách hàng và thời gian

Giả sử bảng `orders` có hàng triệu bản ghi và các cột `id`, `customer_id`, `created_at`, `status`, `total`. Ứng dụng cần lấy 50 đơn hàng mới nhất của một khách hàng trong một khoảng thời gian:

```sql
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
ORDER BY created_at DESC
LIMIT 50;
```

Giả sử kế hoạch ban đầu cho thấy:

- PostgreSQL quét toàn bộ bảng bằng Seq Scan.
- Hàng trăm nghìn hàng bị loại bởi Filter.
- Sort phải xử lý toàn bộ các hàng phù hợp trước khi trả về 50 hàng.
- Số hàng thực tế hoặc thời gian đọc lớn hơn mức ứng dụng chấp nhận.

Một chỉ mục B-tree nhiều cột có thể phù hợp:

```sql
CREATE INDEX idx_orders_customer_created_at
    ON orders (customer_id, created_at DESC)
    INCLUDE (id, total);
```

Lý do chọn cấu trúc này:

- `customer_id` đứng đầu vì truy vấn lọc bằng một giá trị khách hàng.
- `created_at` đứng tiếp theo để giới hạn khoảng thời gian và cung cấp thứ tự giảm dần.
- `id` và `total` nằm trong `INCLUDE` để chỉ mục chứa đủ cột truy vấn cần đọc, tạo cơ hội cho Index Only Scan.

Chạy lại đúng câu SQL với cùng tham số:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
ORDER BY created_at DESC
LIMIT 50;
```

Nếu chỉ mục phù hợp với dữ liệu và thống kê, kế hoạch có thể chuyển sang Index Scan hoặc Index Only Scan. Khi dùng Index Only Scan, PostgreSQL vẫn có thể phải kiểm tra heap nếu visibility map chưa đánh dấu các trang là all-visible; hãy xem chỉ số `Heap Fetches`. Vì thế, có chỉ mục bao phủ không đảm bảo luôn có `Heap Fetches: 0`.

Đánh giá kết quả bằng cách so sánh:

- `Execution Time` trước và sau.
- Số block `shared hit/read` và block tạm.
- Số hàng thực tế được đọc và trả về.
- Nút Sort có còn hay không.
- Số `Heap Fetches` nếu có Index Only Scan.
- Tác động của chỉ mục đến các thao tác ghi và dung lượng lưu trữ.

Một kế hoạch minh họa sau tối ưu có thể trông như sau:

```text
Limit  (cost=0.56..8.20 rows=50 width=24)
       (actual time=0.040..0.090 rows=50 loops=1)
  ->  Index Only Scan using idx_orders_customer_created_at on orders
        (cost=0.56..80.00 rows=500 width=24)
        (actual time=0.038..0.084 rows=50 loops=1)
        Index Cond: ((customer_id = 42)
                     AND (created_at >= '2026-10-01 00:00:00+07'))
        Heap Fetches: 0
        Buffers: shared hit=5
Planning Time: 0.300 ms
Execution Time: 0.110 ms
```

Các số liệu trên chỉ để minh họa, không phải cam kết rằng truy vấn nào cũng đạt kế hoạch hoặc tốc độ này. Nếu truy vấn trả về phần lớn bảng, planner vẫn có thể chọn Seq Scan vì chi phí thấp hơn.

## 6. Chọn loại chỉ mục phù hợp

### 6.1. B-tree: lựa chọn mặc định cho nhiều truy vấn

B-tree phù hợp với các phép so sánh bằng, so sánh khoảng, sắp xếp và nhiều điều kiện tìm kiếm phổ biến:

```sql
CREATE INDEX idx_users_email ON users (email);

SELECT *
FROM users
WHERE email = 'reader@example.com';
```

B-tree cũng hỗ trợ các toán tử như `<`, `<=`, `>`, `>=` và `ORDER BY`. Đây thường là lựa chọn đầu tiên khi truy vấn tìm theo giá trị hoặc khoảng giá trị.

### 6.2. Chỉ mục nhiều cột

Thứ tự cột trong B-tree nhiều cột ảnh hưởng trực tiếp đến khả năng sử dụng. Với:

```sql
CREATE INDEX idx_orders_customer_date
    ON orders (customer_id, created_at);
```

chỉ mục này đặc biệt hữu ích cho điều kiện lọc theo `customer_id`, hoặc theo `customer_id` kết hợp khoảng `created_at`. Nó thường không thay thế tốt một chỉ mục chỉ có `created_at` cho truy vấn không lọc `customer_id`.

Hãy thiết kế thứ tự cột từ các mẫu truy vấn thật: điều kiện bằng, điều kiện khoảng, thứ tự sắp xếp và số lượng hàng cần lấy. Không áp dụng máy móc quy tắc “cột có độ chọn lọc cao nhất luôn phải đứng đầu”; thứ tự tốt phụ thuộc cách truy vấn sử dụng các cột.

### 6.3. Partial index

Partial index chỉ lưu những hàng thỏa điều kiện. Ví dụ, nếu ứng dụng thường xuyên truy vấn đơn hàng đang mở:

```sql
CREATE INDEX idx_orders_open_customer_date
    ON orders (customer_id, created_at DESC)
    WHERE status = 'open';
```

Truy vấn cần có điều kiện mà planner có thể chứng minh phù hợp với predicate của chỉ mục:

```sql
SELECT id, created_at
FROM orders
WHERE status = 'open'
  AND customer_id = 42
ORDER BY created_at DESC;
```

Partial index nhỏ hơn chỉ mục chứa mọi trạng thái và giảm chi phí cập nhật cho các hàng không thuộc phạm vi. Tuy nhiên, nếu truy vấn không thỏa hoặc planner không chứng minh được điều kiện tương ứng, chỉ mục sẽ không được dùng.

### 6.4. Expression index

Nếu truy vấn tìm theo biểu thức, có thể tạo chỉ mục trên chính biểu thức đó:

```sql
CREATE INDEX idx_users_lower_email
    ON users (lower(email));

SELECT id, email
FROM users
WHERE lower(email) = lower('Reader@example.com');
```

Chỉ mục B-tree thông thường trên `email` không nhất thiết hỗ trợ hiệu quả biểu thức `lower(email)`. Expression index hữu ích khi biểu thức xuất hiện thường xuyên và có ý nghĩa ổn định.

### 6.5. INCLUDE và Index Only Scan

`INCLUDE` thêm cột vào phần dữ liệu của chỉ mục nhưng không dùng các cột đó làm khóa tìm kiếm hoặc thứ tự. Nó có thể giúp truy vấn chỉ cần đọc chỉ mục:

```sql
CREATE INDEX idx_products_category
    ON products (category_id)
    INCLUDE (name, price);
```

Index Only Scan còn phụ thuộc visibility map của bảng. Nếu PostgreSQL cần xác minh khả năng nhìn thấy phiên bản hàng trong heap, nó vẫn phải truy cập heap. Thêm quá nhiều cột vào INCLUDE làm chỉ mục lớn hơn, tốn bộ nhớ và tăng chi phí ghi.

### 6.6. GIN, GiST và BRIN

Không phải mọi kiểu dữ liệu đều phù hợp với B-tree:

| Loại | Trường hợp thường dùng |
|---|---|
| GIN | Tìm phần tử trong array, toán tử containment trên JSONB, full-text search |
| GiST | Các kiểu dữ liệu và toán tử cần cấu trúc tìm kiếm tổng quát, ví dụ dữ liệu không gian hoặc khoảng |
| BRIN | Bảng rất lớn có dữ liệu tương quan với thứ tự vật lý, ví dụ bảng log/đo đạc được thêm gần theo thời gian |

Ví dụ GIN cho JSONB containment:

```sql
CREATE INDEX idx_events_payload
    ON events USING GIN (payload);

SELECT id
FROM events
WHERE payload @> '{"type": "payment"}'::jsonb;
```

BRIN thường có kích thước nhỏ và hiệu quả với dữ liệu có tương quan vật lý tốt, nhưng có thể phải đọc thêm nhiều hàng trong mỗi block range. Chọn loại chỉ mục theo toán tử và mẫu truy vấn, không chỉ theo tên kiểu dữ liệu.

## 7. Kiểm tra câu SQL và thống kê trước khi thêm chỉ mục

Một chỉ mục có sẵn vẫn có thể không được dùng nếu biểu thức truy vấn không khớp cách lập chỉ mục hoặc điều kiện không đủ chọn lọc.

### 7.1. Viết điều kiện theo khoảng thay vì bọc cột trong hàm

Cách viết sau có thể khiến chỉ mục B-tree trên `created_at` không được dùng trực tiếp cho điều kiện lọc:

```sql
SELECT *
FROM orders
WHERE DATE(created_at) = DATE '2026-11-14';
```

Nếu cột có chỉ mục B-tree thông thường, hãy viết thành khoảng nửa mở:

```sql
SELECT *
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
```

Khoảng nửa mở tránh trùng ranh giới giữa hai ngày liên tiếp và cho phép tìm theo cột gốc. Nếu nghiệp vụ thật sự cần truy vấn theo biểu thức, hãy cân nhắc expression index tương ứng.

### 7.2. Chú ý kiểu dữ liệu và ép kiểu

Giữ kiểu của tham số tương thích với kiểu cột. Tránh ép kiểu cột trong điều kiện nếu việc đó làm thay đổi biểu thức cần tìm. Dùng parameter binding của ứng dụng và kiểm tra SQL thực tế cùng kiểu tham số được truyền.

### 7.3. Điều kiện LIKE có ký tự đại diện ở đầu

B-tree thông thường thường không giúp tìm chuỗi với mẫu bắt đầu bằng ký tự đại diện, ví dụ `LIKE '%phone%'`. Nếu đây là nhu cầu tìm kiếm thường xuyên, có thể xem xét extension `pg_trgm` cùng GIN hoặc GiST:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm
    ON products USING GIN (name gin_trgm_ops);
```

Cần kiểm tra toán tử, collation và kế hoạch thực tế để xác nhận chỉ mục phù hợp.

### 7.4. Cập nhật thống kê sau thay đổi dữ liệu

Sau khi nạp lượng lớn dữ liệu hoặc thay đổi phân bố dữ liệu, chạy `ANALYZE` trên bảng liên quan. Autovacuum thường tự cập nhật thống kê theo ngưỡng cấu hình, nhưng có thể chưa chạy ngay sau một đợt nạp lớn. `VACUUM` xử lý các phiên bản hàng chết và hỗ trợ cập nhật visibility map; `ANALYZE` thu thập thống kê cho planner. Hai thao tác có mục đích khác nhau.

## 8. Những chi phí cần cân nhắc khi tạo chỉ mục

Chỉ mục giúp tăng tốc một số thao tác đọc, nhưng cũng tạo thêm công việc cho hệ thống:

- Mỗi lần thêm, sửa hoặc xóa hàng có thể phải cập nhật nhiều chỉ mục.
- Chỉ mục chiếm dung lượng đĩa và có thể chiếm một phần đáng kể cache.
- Chỉ mục ít được dùng làm tăng chi phí ghi và bảo trì.
- Nhiều chỉ mục gần giống nhau làm tăng độ phức tạp mà không chắc đem lại lợi ích.
- Sau thời gian dài, bloat và các phiên bản hàng chết có thể ảnh hưởng hiệu quả; cần theo dõi vacuum và tình trạng chỉ mục.

Trên bảng đang phục vụ ghi liên tục, `CREATE INDEX CONCURRENTLY` thường giúp giảm thời gian khóa cản trở thao tác ghi so với cách tạo chỉ mục thông thường. Lệnh này tốn thêm công việc, có thể chạy lâu và không được đặt bên trong transaction block. Cần theo dõi kết quả tạo chỉ mục và xác minh chỉ mục hợp lệ trước khi dựa vào nó.

Không tạo chỉ mục cho mọi cột chỉ vì cột đó xuất hiện trong `WHERE`. Hãy dựa trên truy vấn có tần suất cao, độ chọn lọc, chi phí đọc/ghi và kết quả đo trước/sau. Cũng không nên ép planner tránh Seq Scan như một giải pháp cố định; Seq Scan có thể là kế hoạch tối ưu.

## 9. Quy trình thực hành có thể lặp lại

Với mỗi truy vấn chậm, ghi lại một bộ bằng chứng ngắn:

1. Câu SQL và bộ tham số đại diện.
2. Thời gian hiện tại, tần suất chạy và phiên bản PostgreSQL.
3. Toàn bộ kết quả `EXPLAIN (ANALYZE, BUFFERS)`.
4. Nút có chênh lệch ước lượng/thực tế lớn, nhiều loops, nhiều block đọc hoặc dữ liệu tạm.
5. Giả thuyết nguyên nhân: thống kê, điều kiện lọc, join, sort hay thiếu chỉ mục.
6. Một thay đổi có mục tiêu, chẳng hạn `ANALYZE`, sửa biểu thức lọc hoặc tạo một chỉ mục.
7. Kế hoạch và số liệu sau thay đổi, đo trên cùng truy vấn và bộ tham số.
8. Ảnh hưởng đến thao tác ghi, kích thước chỉ mục và các truy vấn khác.

Đo nhiều lần trong điều kiện tương đương nếu kết quả dao động. Phân biệt lần chạy lạnh cache và lần chạy nóng cache; không so sánh hai lần có điều kiện hoàn toàn khác nhau rồi quy toàn bộ chênh lệch cho chỉ mục mới.

## 10. Bài tập thực hành

Giả sử bảng `orders` có nhiều triệu hàng. Ứng dụng thường chạy:

```sql
SELECT id, status, total
FROM orders
WHERE customer_id = 105
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

Hãy thực hiện các bước sau trên môi trường thực hành:

1. Chạy `EXPLAIN (ANALYZE, BUFFERS)` và xác định nút đọc dữ liệu từ `orders`.
2. So sánh `rows` ước lượng với `actual rows`; ghi lại `loops` và `Rows Removed by Filter`.
3. Kiểm tra có Sort hay không, số block buffer được đọc và có dữ liệu tạm hay không.
4. Đề xuất chỉ mục dựa trên điều kiện lọc và thứ tự sắp xếp. Có thể đánh giá một chỉ mục nhiều cột hoặc partial index cho `status = 'paid'`.
5. Chạy lại truy vấn, so sánh kế hoạch, thời gian và buffer.
6. Giải thích chi phí ghi và dung lượng mà chỉ mục mới tạo ra.

Không có một chỉ mục duy nhất luôn đúng cho mọi hệ thống. Cần dùng dữ liệu thật, truy vấn thật và kế hoạch thực tế để chứng minh lựa chọn.

## 11. Tự kiểm tra kiến thức

**Vì sao Seq Scan có thể nhanh hơn Index Scan?** Khi truy vấn cần phần lớn hàng của bảng, đọc tuần tự có thể ít tốn công hơn việc tra chỉ mục rồi truy cập heap ở nhiều vị trí.

**cost=500 có nghĩa truy vấn chạy 500 ms không?** Không. Cost là đơn vị ước lượng nội bộ của planner, không phải thời gian thực.

**actual rows=2 loops=5000 cho biết điều gì?** Nút trả trung bình 2 hàng mỗi lượt và được gọi 5.000 lượt; cần xem nút cha, đặc biệt Nested Loop, để hiểu tổng công việc.

**Có chỉ mục bao phủ thì luôn có Index Only Scan không?** Không. Planner phải thấy kế hoạch đó có lợi và visibility map phải cho phép tránh truy cập heap ở mức cần thiết.

**Sau khi tạo chỉ mục, cần làm gì?** Chạy lại đúng truy vấn với tham số đại diện, so sánh thời gian, số hàng, buffer, sort và heap fetches; đồng thời đánh giá chi phí ghi và dung lượng của chỉ mục.


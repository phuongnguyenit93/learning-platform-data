# Quy trình đo tải, chọn SQL trọng yếu, sửa và kiểm chứng lại

SQL tuning (tối ưu SQL) là quá trình xác định những câu truy vấn đang tiêu tốn tài nguyên đáng kể, tìm nguyên nhân bằng dữ liệu đo và thay đổi truy vấn, index hoặc cách truy cập dữ liệu để cải thiện kết quả. Tối ưu hiệu quả không bắt đầu bằng việc thêm index hoặc viết lại mọi câu `SELECT`; nó bắt đầu bằng việc hiểu workload và đo baseline.

Một truy vấn có thời gian trung bình thấp vẫn có thể gây tải lớn nếu được gọi hàng chục nghìn lần. Một truy vấn chậm vài giây nhưng chỉ chạy trong báo cáo hàng tháng có thể ít ưu tiên hơn truy vấn chạy trên mọi request. Vì vậy, hãy xếp hạng theo tác động tổng thể, xác định mục tiêu (latency, throughput, I/O, CPU hoặc lock wait), rồi sửa từng nguyên nhân và kiểm chứng bằng cùng dữ liệu, tham số và mức tải.

## 1. Tối ưu SQL là tối ưu workload

Một hệ thống ứng dụng thường chạy hàng trăm hoặc hàng nghìn mẫu truy vấn. Mục tiêu không phải làm mọi câu SQL ngắn hơn mà là cải thiện hiệu năng tổng thể mà vẫn giữ nguyên kết quả nghiệp vụ.

Các câu hỏi đầu tiên:

- Câu truy vấn nào tiêu tốn nhiều thời gian database nhất trong một khoảng quan sát?
- Câu nào có latency p95/p99 cao và ảnh hưởng trực tiếp đến người dùng?
- Câu nào đọc quá nhiều hàng so với số hàng trả về?
- Câu nào chạy quá thường xuyên, gây tổng CPU/I/O cao dù mỗi lần nhanh?
- Câu nào tạo temporary table trên disk, sort lớn hoặc chờ khóa?
- Có truy vấn N+1 khiến một request tạo ra nhiều lượt round-trip không?
- Bottleneck nằm ở SQL, index, dữ liệu, concurrency, network hay ứng dụng?

Không kết luận từ một lần chạy đơn lẻ. Buffer pool, cache, độ nóng dữ liệu, concurrency, tham số truy vấn và trạng thái hệ thống có thể làm thời gian thay đổi đáng kể.

## 2. Xác định mục tiêu và baseline trước khi sửa

Trước khi tối ưu, ghi lại trạng thái ban đầu (baseline). Một baseline hữu ích có thể gồm:

| Chỉ số | Ý nghĩa | Dùng để đánh giá |
| --- | --- | --- |
| Query count | Số lần mẫu SQL chạy trong khoảng đo | Tần suất và tổng tải |
| Total latency | Tổng thời gian database tiêu tốn | Mức đóng góp vào workload |
| Average latency | Thời gian trung bình mỗi lần chạy | Chi phí trung bình |
| p95 / p99 latency | Ngưỡng thời gian mà 95% / 99% request không vượt qua | Trải nghiệm ở đuôi phân bố |
| Rows examined | Số hàng được đọc/xem xét | Hiệu quả lọc và access path |
| Rows sent | Số hàng trả về client | So sánh công việc đọc với kết quả |
| Temporary tables / disk temp tables | Mức dùng bảng tạm và bảng tạm trên disk | Chi phí sort, group, materialization |
| Sort rows / merge passes | Công việc sắp xếp | Truy vấn ORDER BY/GROUP BY lớn |
| Lock wait / deadlocks | Thời gian chờ và xung đột khóa | Ảnh hưởng concurrency |
| CPU, I/O, buffer pool | Tài nguyên toàn server | Phân biệt SQL bottleneck và server bottleneck |

Chốt một mục tiêu đo được, ví dụ: giảm p95 từ 900 ms xuống dưới 300 ms, giảm rows examined trung bình từ 200.000 xuống dưới 5.000, hoặc giảm tổng thời gian của digest đứng đầu 30% trong cùng khoảng tải.

Nếu chỉ đo thời gian của một câu lệnh trên máy phát triển mà không đo query count, p95 và tải đồng thời, có thể tối ưu nhầm truy vấn ít quan trọng.

## 3. Thu thập SQL trọng yếu bằng Slow Query Log

Slow Query Log ghi lại các câu lệnh vượt ngưỡng thời gian được cấu hình. Đây là nguồn dữ liệu hữu ích để tìm truy vấn chậm, đặc biệt khi cần xem SQL cụ thể và số hàng đã xem xét.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'log_output';
SHOW VARIABLES LIKE 'log_queries_not_using_indexes';
```

Trong môi trường có quyền quản trị, có thể bật log và đặt ngưỡng trong runtime:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 0.5;
```

Thay đổi `GLOBAL` đặt giá trị mặc định cho connection mới; session đang mở có thể vẫn giữ giá trị `long_query_time` cũ. Có thể kiểm tra hoặc đặt riêng session:

```sql
SELECT @@SESSION.long_query_time;
SET SESSION long_query_time = 0.5;
```

Runtime setting có thể mất sau khi server khởi động lại nếu không được lưu trong cấu hình triển khai hoặc hệ thống quản lý dịch vụ. Cần quyền phù hợp như `SYSTEM_VARIABLES_ADMIN` hoặc quyền quản trị tương ứng trên phiên bản MySQL đang dùng.

`log_queries_not_using_indexes` có thể tạo log rất lớn, vì nhiều truy vấn quét bảng nhỏ hoặc đọc phần lớn bảng là hợp lý. Chỉ bật khi có mục tiêu điều tra rõ ràng và theo dõi dung lượng log.

Slow Query Log có thể chứa literal, thông tin nghiệp vụ hoặc dữ liệu nhạy cảm. Bảo vệ quyền đọc log, đặt retention và tránh đưa nội dung nhạy cảm vào báo cáo chia sẻ.

## 4. Xếp hạng workload bằng Performance Schema

Performance Schema tổng hợp các câu lệnh theo digest (mẫu truy vấn đã chuẩn hóa literal). Có thể tìm các digest tiêu tốn tổng thời gian lớn:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_NO_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các trường `*_TIMER_WAIT` của Performance Schema được biểu diễn theo picosecond; chia cho (10^{12}) để đổi sang giây. `COUNT_STAR` cho biết số lần thực thi; `SUM_TIMER_WAIT` giúp thấy tổng thời gian của digest; `AVG_TIMER_WAIT` cho biết trung bình.

Có thể xếp hạng theo tần suất hoặc số hàng đọc:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(SUM_ROWS_EXAMINED / NULLIF(COUNT_STAR, 0), 1)
        AS avg_rows_examined
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 20;
```

Kết quả là thống kê tích lũy từ thời điểm Performance Schema bắt đầu thu thập hoặc từ lần reset summary gần nhất. Nó không tự cung cấp p95/p99 cho mọi digest; dùng APM, telemetry ứng dụng hoặc hệ thống metrics để đo phân vị latency theo request.

Nếu cài đặt `sys` schema, view `sys.statement_analysis` có thể trình bày thống kê truy vấn dễ đọc hơn. Kiểm tra view có tồn tại trên môi trường trước khi dùng; không phải mọi dịch vụ MySQL tương thích đều bật đầy đủ các view giống nhau.

## 5. Chọn truy vấn cần tối ưu theo tác động

Một thứ tự ưu tiên thực tế:

1. Truy vấn có tổng thời gian lớn nhất trong workload.
2. Truy vấn có p95/p99 cao và nằm trên đường đi request quan trọng.
3. Truy vấn đọc nhiều hàng nhưng trả về ít hàng.
4. Truy vấn chạy rất thường xuyên, dù latency mỗi lần không cao.
5. Truy vấn gây temporary table trên disk, sort lớn hoặc lock wait.
6. Truy vấn làm tăng tải đồng thời, ví dụ một update chạm nhiều hàng hoặc N+1 query.

Ví dụ, digest A chạy 100.000 lần, mỗi lần 5 ms, tạo tổng 500 giây. Digest B chạy 10 lần, mỗi lần 2 giây, tạo tổng 20 giây. Nếu mục tiêu là giảm tải tổng thể, A có thể đáng ưu tiên hơn B; nếu B chặn một thao tác quản trị quan trọng, mức ưu tiên nghiệp vụ có thể khác.

Đừng chỉ sắp xếp theo `AVG_TIMER_WAIT`. Kết hợp số lần chạy, tổng latency, rows examined, độ quan trọng của request và phân vị latency.

## 6. Tái hiện truy vấn với tham số và dữ liệu đại diện

Sau khi chọn một digest, lấy câu SQL cụ thể từ slow log, APM hoặc log ứng dụng. Cần biết:

- Các giá trị bind parameter thường gặp và trường hợp biên.
- Kích thước bảng, số hàng và phân bố dữ liệu.
- Index hiện có và thống kê optimizer.
- Tần suất thực thi và concurrency.
- Kết quả mong đợi và các trường hợp NULL/duplicate.
- Isolation level và transaction context nếu truy vấn ghi/đọc có khóa.

Một câu SQL với `customer_id` có 2 đơn hàng có thể rất nhanh, nhưng với một tenant có 20 triệu đơn có thể rất chậm. Dữ liệu lab nhỏ hoặc phân bố đều không đủ đại diện cho production.

Chuẩn hóa cách chạy thử: cùng tham số, cùng schema/index, cùng mức concurrency, cùng trạng thái cache nếu có thể, và ghi lại phiên bản MySQL. Không thay đổi nhiều biến cùng lúc.

## 7. Đọc EXPLAIN trước khi sửa câu SQL

`EXPLAIN` cho biết kế hoạch mà optimizer dự kiến sử dụng:

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

Các trường thường xem:

- `type`: access method như `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `possible_keys`: các index optimizer cân nhắc.
- `key`: index được chọn.
- `key_len`: độ dài phần index được dùng.
- `rows`: số hàng ước lượng cần đọc.
- `filtered`: phần trăm hàng ước lượng còn lại sau điều kiện lọc.
- `Extra`: các dấu hiệu như `Using where`, `Using index`, `Using temporary`, `Using filesort`.
- `partitions`: các partition được truy cập nếu bảng đã partition.

Không đánh giá một kế hoạch chỉ qua `type`. Full table scan có thể hợp lý nếu bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu. `Using filesort` cũng không tự động là lỗi; cần xem số hàng được sort, thời gian và khả năng tận dụng index.

Với kế hoạch phức tạp, dùng:

```sql
EXPLAIN FORMAT=JSON
SELECT ...;
```

JSON cung cấp chi tiết hơn về query block, access path, cost và ước lượng hàng. Khi nghi ngờ estimate sai, so sánh với số hàng thực tế.

## 8. Dùng EXPLAIN ANALYZE để đo thực tế

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi truy vấn và hiển thị thời gian, số hàng thực tế và số vòng lặp của các iterator:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

Đối chiếu:

- `estimated rows` với `actual rows`.
- `loops` để biết iterator được gọi bao nhiêu lần.
- `actual time` để tìm bước tiêu tốn thời gian.
- Số hàng đi vào và đi ra sau filter/join.

`EXPLAIN ANALYZE` thật sự chạy câu truy vấn; nó không chỉ in kế hoạch tĩnh. Dùng với `SELECT` phù hợp trên môi trường an toàn và dữ liệu đại diện. Với truy vấn nặng, hãy cân nhắc tải production và thời gian thực thi trước khi chạy.

Nếu estimate lệch lớn, kiểm tra thống kê bảng/index, data skew, histogram, correlation giữa cột và khả năng optimizer chọn sai join order. Không vội thêm hint trước khi hiểu nguyên nhân.

## 9. Sửa predicate để có thể dùng index

Điều kiện lọc nên giữ cột index ở dạng có thể so sánh trực tiếp (sargable) khi có thể.

Ví dụ không ưu tiên:

```sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-03-15';
```

Hàm `DATE()` được áp dụng lên cột; index B-tree thông thường trên `created_at` có thể không được dùng hiệu quả cho range lookup này.

Viết lại thành khoảng:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-03-15 00:00:00'
  AND created_at <  '2026-03-16 00:00:00';
```

Các trường hợp khác cần chú ý:

- Tránh chuyển kiểu ngầm trên cột index; bind parameter đúng kiểu dữ liệu.
- Tránh `LOWER(indexed_column) = ...` nếu chưa có chiến lược functional index/generated column phù hợp.
- `LIKE 'prefix%'` có thể tận dụng B-tree trong điều kiện phù hợp; `LIKE '%suffix'` thường không thể dùng B-tree để tìm prefix.
- Tránh biểu thức tính toán trên cột trong điều kiện nếu có thể chuyển phép tính sang phía hằng số.
- Với cột nullable, giữ rõ ngữ nghĩa `NULL`; không thay bằng giá trị mặc định tùy tiện để “dễ dùng index”.

Mỗi lần rewrite cần kiểm tra kết quả tương đương, timezone, precision ngày giờ, collation và quy tắc NULL.

## 10. Chỉ lấy những cột cần thiết

`SELECT *` có thể đọc và truyền nhiều dữ liệu hơn cần thiết, nhất là khi bảng có `TEXT`, `BLOB`, JSON lớn hoặc nhiều cột ít dùng.

Không ưu tiên:

```sql
SELECT *
FROM customers
WHERE customer_id = 42;
```

Nếu giao diện chỉ cần tên và trạng thái:

```sql
SELECT customer_name, status
FROM customers
WHERE customer_id = 42;
```

Lợi ích có thể gồm giảm bytes đọc từ storage, giảm dữ liệu truyền qua network, giảm bộ nhớ ở server/client và tăng cơ hội dùng covering index. Không phải mọi truy vấn cần covering index; đừng thêm nhiều cột vào index chỉ để tránh một vài lần lookup mà không đo chi phí ghi và kích thước index.

## 11. Thiết kế composite index theo điều kiện truy vấn

Index ghép cần được thiết kế theo các cột truy vấn thực sự dùng. Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
```

Một index ứng viên:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
```

Hai điều kiện equality đứng trước cột sắp xếp theo thời gian. InnoDB có thể dùng leftmost prefix của index và đọc phần dữ liệu của khách hàng/trạng thái theo thứ tự thời gian. Hãy kiểm tra `EXPLAIN` để xác nhận kế hoạch thực tế.

Một số nguyên tắc:

- Leftmost prefix: index `(a, b, c)` có thể hỗ trợ điều kiện trên `a`, `(a,b)` hoặc `(a,b,c)`; không phải lựa chọn tương đương cho điều kiện chỉ có `b`.
- Equality columns thường được đặt trước range/order columns trong nhiều mẫu truy vấn, nhưng thứ tự tối ưu phụ thuộc workload và selectivity.
- Sau một range condition, các cột sau có thể không còn được dùng để thu hẹp range theo cùng cách, dù vẫn có thể hỗ trợ covering hoặc điều kiện khác.
- Index có thêm cột giúp truy vấn nhưng làm tăng dung lượng và chi phí mọi thao tác ghi.
- InnoDB lưu primary key trong secondary index; xét điều đó trước khi thêm lại cột khóa chính không cần thiết.

Không tạo index chỉ vì một cột xuất hiện trong `WHERE`. Hãy xem truy vấn kết hợp `WHERE`, `JOIN`, `ORDER BY`, `GROUP BY`, số hàng và tần suất.

## 12. Chọn index theo selectivity và workload

Một cột có ít giá trị phân biệt không nhất thiết vô dụng trong index. Nếu một giá trị rất hiếm, index vẫn có thể chọn lọc tốt cho giá trị đó. Ngược lại, một cột có cardinality cao nhưng truy vấn thường yêu cầu 80% bảng có thể không đem lại lợi ích.

Ví dụ `status` có các giá trị `active`, `pending`, `failed`. Nếu `active` chiếm 95% bảng, truy vấn `WHERE status = 'active'` có thể dùng full scan. Nhưng `status = 'failed'` chỉ khớp 0,1%, index có thể hữu ích.

Kiểm tra phân bố:

```sql
SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status
ORDER BY row_count DESC;
```

Sau bulk load hoặc thay đổi phân bố lớn, cân nhắc cập nhật thống kê:

```sql
ANALYZE TABLE orders;
```

Với cột lệch mạnh, histogram có thể giúp optimizer ước lượng selectivity của cột đơn. Histogram không thay thế composite index và không mô tả đầy đủ correlation giữa nhiều cột.

## 13. Giảm chi phí JOIN

Khi truy vấn JOIN chậm:

- Xác nhận điều kiện JOIN có đúng kiểu dữ liệu và cùng ngữ nghĩa so sánh.
- Tạo index phù hợp cho join key ở phía cần lookup.
- Lọc sớm theo điều kiện có chọn lọc nếu điều đó phù hợp với query plan.
- Tránh nối các bảng one-to-many độc lập rồi tổng hợp khiến fan-out nhân hàng.
- Chỉ lấy cột cần thiết từ mỗi bảng.
- Dùng `EXISTS` khi chỉ cần kiểm tra có hàng liên quan; dùng `JOIN` khi cần dữ liệu từ cả hai phía.
- Kiểm tra estimate/actual rows ở từng iterator, nhất là nested-loop có nhiều `loops`.

Ví dụ tìm khách hàng có ít nhất một đơn đã thanh toán:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
```

Nếu cần từng đơn hàng cùng thông tin khách hàng, `JOIN` mới là ngữ nghĩa đúng. Không thay JOIN bằng EXISTS chỉ để giảm số hàng nếu ứng dụng thực sự cần từng dòng chi tiết.

## 14. ORDER BY, LIMIT và phân trang

`ORDER BY` có thể yêu cầu sort nếu index không hỗ trợ thứ tự. Khi truy vấn lấy một trang nhỏ, index phù hợp với filter và sort có thể giúp MySQL dừng sớm sau khi tìm đủ hàng.

Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Có thể đánh giá index `(customer_id, created_at)`; InnoDB secondary index lưu primary key nên thứ tự khóa chính cũng có thể tham gia thứ tự index. Tuy nhiên, chiều sort và kế hoạch thực tế cần được kiểm tra bằng `EXPLAIN`.

### 14.1. OFFSET lớn

Phân trang kiểu:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

thường phải đi qua nhiều hàng trước khi bỏ 100.000 hàng đầu, dù chỉ trả 20 hàng. Khi offset lớn, chi phí tăng theo vị trí trang.

### 14.2. Keyset pagination

Nếu ứng dụng có thể gửi cursor từ hàng cuối của trang trước, dùng keyset pagination:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND (
      created_at < '2026-03-15 10:00:00'
      OR (
          created_at = '2026-03-15 10:00:00'
          AND order_id < 900100
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Index `(customer_id, created_at)` có thể hỗ trợ truy cập theo cursor; kiểm tra kế hoạch và phân bố thực tế. Cần có thứ tự xác định, thường thêm khóa duy nhất làm tie-breaker. Keyset pagination tránh phải bỏ qua một offset rất lớn và ổn định hơn khi dữ liệu mới được chèn ở đầu danh sách.

## 15. Tối ưu GROUP BY và aggregate

Với truy vấn tổng hợp, hãy kiểm tra:

- Có lọc dữ liệu trước khi nhóm được không?
- Index có hỗ trợ cột lọc và cột nhóm không?
- Có đang join nhiều bảng con trước khi aggregate khiến số hàng bị nhân không?
- Có thực sự cần `DISTINCT` trước aggregate không?
- Kết quả có thể được tổng hợp trước trong derived table/CTE rồi mới JOIN không?
- Có thể lưu summary/materialized result theo batch nếu yêu cầu freshness cho phép không?

Ví dụ tổng tiền theo khách hàng trong một khoảng thời gian:

```sql
SELECT customer_id, SUM(total_amount) AS paid_total
FROM orders
WHERE status = 'paid'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01'
GROUP BY customer_id;
```

Index phù hợp có thể là `(status, created_at, customer_id)` hoặc một thứ tự khác tùy độ chọn lọc và các truy vấn liên quan. Không thể xác định thứ tự tốt nhất chỉ từ tên cột; hãy đo trên dữ liệu thực.

## 16. Tránh N+1 query và round-trip không cần thiết

N+1 xảy ra khi ứng dụng lấy một danh sách rồi chạy thêm một truy vấn riêng cho từng hàng. Ví dụ lấy 100 khách hàng rồi chạy 100 câu truy vấn lấy đơn hàng gần nhất. Mỗi câu có thể nhanh nhưng tổng latency tăng do round-trip và parse/execute lặp lại.

Các cách xử lý có thể gồm:

- Dùng JOIN khi cần dữ liệu liên quan trong cùng kết quả.
- Dùng một truy vấn `IN (...)` cho tập ID vừa phải, sau đó ghép kết quả ở ứng dụng.
- Dùng window function hoặc derived table để lấy bản ghi mới nhất theo nhóm.
- Batch các thao tác ghi thay vì gửi từng statement nhỏ khi nghiệp vụ cho phép.
- Kiểm tra số query trên mỗi request bằng APM hoặc tracing.

Không gom mọi thứ thành một truy vấn khổng lồ bằng mọi giá. Nếu một truy vấn JOIN tạo fan-out lớn hoặc trả dữ liệu dư thừa, nhiều truy vấn có kiểm soát/batch có thể phù hợp hơn. Hãy so sánh số round-trip, bytes truyền và actual rows.

## 17. Tối ưu DML và batch ghi/xóa

Các câu `UPDATE`/`DELETE` cũng cần tối ưu access path. Điều kiện không có index có thể quét nhiều hàng, giữ khóa lâu và ảnh hưởng các transaction khác.

Ví dụ cập nhật một nhóm đơn hàng:

```sql
UPDATE orders
SET status = 'archived'
WHERE status = 'completed'
  AND created_at < '2025-01-01';
```

Kiểm tra index phù hợp với điều kiện, số hàng thực tế và thời gian khóa. Với tập dữ liệu rất lớn, có thể xử lý theo batch nếu nghiệp vụ cho phép commit từng phần:

```sql
DELETE FROM audit_events
WHERE occurred_at < '2024-01-01'
ORDER BY occurred_at
LIMIT 1000;
```

Ứng dụng có thể lặp batch đến khi không còn hàng phù hợp, theo dõi affected rows và thời gian mỗi batch. Batch thay đổi atomicity: mỗi lần commit độc lập; chỉ dùng nếu quy trình chấp nhận tiến độ từng phần và có thể tiếp tục sau lỗi.

Không chạy một lệnh xóa lớn trên production mà chưa đánh giá lock, undo, redo, replication lag, binlog và dung lượng backup.

## 18. Transaction và concurrency cũng là một phần của SQL tuning

Truy vấn nhanh khi chạy riêng lẻ vẫn có thể làm hệ thống chậm nếu nó giữ khóa lâu hoặc chạy trong transaction kéo dài.

Các nguyên tắc:

- Giữ transaction ngắn; không gọi API ngoài trong khi giữ khóa.
- Dùng index phù hợp để giảm số hàng bị quét/khóa.
- Cập nhật nhiều hàng theo thứ tự nhất quán để giảm deadlock.
- Dùng conditional UPDATE cho read-modify-write đơn giản.
- Phân loại deadlock và lock wait timeout; retry toàn bộ transaction có giới hạn khi phù hợp.
- Theo dõi lock wait, transaction mở lâu và deadlock cùng với latency truy vấn.

Nếu `EXPLAIN ANALYZE` cho thấy truy vấn nhanh nhưng request vẫn chậm, kiểm tra thời gian chờ connection pool, lock wait, network và thời gian xử lý ứng dụng.

## 19. Thử nghiệm có kiểm soát: thay đổi một yếu tố mỗi lần

Khi đã xác định nguyên nhân, tạo một giả thuyết cụ thể:

- “Index ghép này sẽ giảm rows examined từ 80.000 xuống dưới 500.”
- “Đổi điều kiện ngày thành range sẽ cho phép range scan.”
- “Keyset pagination sẽ tránh đọc/bỏ qua 100.000 hàng.”
- “Tách aggregate trước JOIN sẽ loại bỏ fan-out và giảm số hàng trung gian.”

Sau đó:

1. Lưu baseline SQL, plan, số hàng, latency và index hiện có.
2. Thực hiện một thay đổi: query rewrite, index, histogram hoặc schema.
3. Chạy cùng tham số và dữ liệu đại diện.
4. Đo actual rows, loops, latency, CPU/I/O và lock wait.
5. Kiểm tra kết quả SQL có hoàn toàn tương đương không.
6. Kiểm tra tác động lên các truy vấn khác và chi phí DML do index mới.
7. Lặp lại dưới concurrency gần production.

Không thêm ba index và viết lại query cùng lúc rồi kết luận thay đổi nào tạo lợi ích. Thử nghiệm từng yếu tố giúp hiểu nguyên nhân và rollback dễ hơn.

## 20. Đo đúng: cache, concurrency và phân vị latency

Khi benchmark, cần ghi rõ trạng thái cache. Lần chạy đầu có thể đọc từ disk; các lần sau có thể lấy phần lớn dữ liệu từ buffer pool. So sánh một truy vấn cold-cache với một truy vấn warm-cache sẽ cho kết luận sai.

Một số nguyên tắc đo:

- Chạy đủ nhiều lần để tránh kết luận từ một mẫu.
- Dùng tham số đại diện gồm cả giá trị phổ biến và hiếm.
- Giữ cùng số client/concurrency khi so sánh.
- Đo p50, p95, p99 bên cạnh average.
- Quan sát throughput và tài nguyên server, không chỉ latency của một client.
- Tách thời gian chờ pool, network và xử lý ứng dụng khỏi thời gian database nếu có telemetry.
- Không xóa cache production để tạo benchmark; điều đó có thể gây tải đột biến.

`EXPLAIN ANALYZE` hữu ích để hiểu iterator nhưng có overhead đo và thường chạy một truy vấn trong điều kiện riêng. Load test hoặc telemetry ứng dụng mới phản ánh tốt hơn hành vi dưới tải đồng thời.

## 21. Optimizer statistics và histogram

Kế hoạch phụ thuộc vào thống kê. Sau khi bulk load, xóa nhiều hàng hoặc thay đổi phân bố đáng kể, cân nhắc:

```sql
ANALYZE TABLE orders;
```

Với cột đơn có phân bố lệch và phù hợp, có thể đánh giá histogram:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

Histogram MySQL mô tả phân bố từng cột; nó không mô tả đầy đủ tương quan nhiều cột. Nếu truy vấn lọc đồng thời nhiều cột, composite index và thống kê prefix có thể phù hợp hơn. Sau khi thay đổi thống kê, kiểm tra lại kế hoạch và các truy vấn quan trọng khác.

## 22. Khi nào cần query rewrite, index, schema hay cache?

| Dấu hiệu | Hướng xử lý nên đánh giá | Kiểm chứng |
| --- | --- | --- |
| Rows examined lớn hơn nhiều rows sent | Sửa predicate, index, partition pruning hoặc query shape | `EXPLAIN ANALYZE`, rows examined |
| `DATE(column)` hoặc hàm trên cột index | Viết điều kiện range hoặc dùng functional/generated index phù hợp | `EXPLAIN` và kết quả tương đương |
| Sort lớn cho `ORDER BY ... LIMIT` | Index theo filter và thứ tự sort | `EXPLAIN`, actual rows và sort work |
| OFFSET rất lớn | Keyset pagination | Đo rows/latency ở trang sâu |
| N+1 query | JOIN, batch hoặc truy vấn theo tập ID | Số query/request, bytes và latency |
| JOIN tạo fan-out | Aggregate trước JOIN hoặc đổi ngữ nghĩa sang EXISTS nếu chỉ cần existence | Đối chiếu số hàng và tổng hợp |
| Estimate lệch mạnh | Cập nhật statistics/histogram, kiểm tra skew/correlation | Estimated vs actual rows |
| Lock wait cao | Transaction ngắn, index, thứ tự khóa và conditional DML | Lock wait/deadlock metrics |
| Câu SQL đã tối ưu nhưng dữ liệu đọc lặp nhiều | Cân nhắc cache hoặc summary table | Hit rate, freshness, invalidation |
| Schema lưu quá nhiều LOB cho truy vấn danh sách | Chỉ chọn cột cần hoặc tách metadata/content | I/O, bytes trả về và latency |

Cache không phải bước đầu tiên cho mọi truy vấn chậm. Cache thêm vấn đề invalidation, stale data, memory và consistency. Hãy tối ưu truy vấn và access pattern trước; chỉ cache khi dữ liệu được đọc lặp lại, có chính sách freshness rõ và đo được lợi ích.

## 23. Optimizer hints chỉ là lựa chọn cuối

MySQL có optimizer hints và index hints, nhưng ép optimizer dùng một index hoặc join order có thể giúp một tập dữ liệu hiện tại rồi trở thành lựa chọn tệ khi phân bố thay đổi.

Trước khi thêm hint:

- Xác nhận lỗi estimate bằng `EXPLAIN ANALYZE`.
- Kiểm tra thống kê, histogram và composite index.
- Đo nhiều tham số có selectivity khác nhau.
- Xác nhận hint tác động đúng query block và phiên bản.
- Ghi lý do, cách đo và kế hoạch gỡ hint.

Không dùng `FORCE INDEX` chỉ vì thấy `type = ALL`; full scan có thể là kế hoạch đúng khi cần đọc phần lớn bảng.

## 24. Đưa thay đổi vào production an toàn

Một thay đổi tối ưu cần được triển khai có kiểm soát:

1. Lưu SQL và baseline trước thay đổi.
2. Kiểm thử correctness, NULL, duplicate, biên thời gian và quyền truy cập.
3. Đánh giá chi phí tạo index hoặc rebuild bảng, dung lượng đĩa và metadata lock.
4. Triển khai theo cửa sổ phù hợp; với hệ thống lớn, đánh giá online DDL và tác động replication.
5. Theo dõi query digest, p95/p99, throughput, CPU/I/O, lock wait và error rate.
6. Có kế hoạch rollback query hoặc index nếu tải xấu đi.
7. Ghi nhận kết quả thực tế và cập nhật tài liệu vận hành.

Index mới có thể cải thiện SELECT nhưng làm chậm INSERT/UPDATE/DELETE và tăng backup size. Một query rewrite có thể thay đổi cách xử lý NULL hoặc duplicate. Không triển khai chỉ dựa trên benchmark cục bộ.

## 25. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Tối ưu câu SQL có average latency cao nhất là đủ | Tổng tải còn phụ thuộc query count và p95/p99 | Xếp hạng theo tổng latency, tần suất và tác động nghiệp vụ |
| Mọi full table scan đều xấu | Full scan có thể rẻ hơn index khi đọc phần lớn bảng | Xem selectivity, actual rows và thời gian |
| Thêm index luôn làm truy vấn nhanh hơn | Index tăng chi phí ghi và có thể không được optimizer chọn | Đo lợi ích đọc và chi phí DML |
| EXPLAIN rows là số hàng thật | Đây là ước lượng | Dùng EXPLAIN ANALYZE để xem actual rows và loops |
| EXPLAIN ANALYZE chỉ hiển thị, không chạy query | Nó thực thi truy vấn | Chạy SELECT phù hợp và đánh giá tải |
| SELECT * không ảnh hưởng nếu có LIMIT | LOB/cột lớn vẫn có thể tăng I/O và bytes truyền | Chọn đúng cột cần thiết |
| DISTINCT luôn sửa được duplicate JOIN | Nó có thể che lỗi fan-out và tạo sort/hash tốn kém | Xác định cardinality và ngữ nghĩa trước |
| OFFSET lớn chỉ tốn ít vì LIMIT nhỏ | Server vẫn có thể phải bỏ qua rất nhiều hàng | Dùng keyset pagination cho trang sâu |
| Histogram giải quyết mọi estimate error | Histogram đơn cột không mô tả đầy đủ correlation | Đánh giá composite index và actual rows |
| Retry hoặc tăng timeout sẽ chữa truy vấn chậm | Nguyên nhân có thể là scan, lock hoặc plan sai | Đo đúng bottleneck trước khi đổi timeout |
| Cache luôn tốt hơn sửa SQL | Cache có invalidation và consistency cost | Tối ưu query/access path rồi mới đánh giá cache |

## 26. Checklist tối ưu một truy vấn

Trước khi kết luận đã tối ưu, kiểm tra:

- [ ] Có baseline với query count, latency và rows examined.
- [ ] Đã chọn đúng truy vấn có tác động lớn.
- [ ] Đã tái hiện với tham số và dữ liệu đại diện.
- [ ] Kết quả nghiệp vụ được giữ nguyên.
- [ ] Đã đọc `EXPLAIN`/`EXPLAIN FORMAT=JSON`.
- [ ] Đã so sánh estimated rows với actual rows khi phù hợp.
- [ ] Predicate có sargable và kiểu bind đúng không?
- [ ] Có `SELECT *`, LOB hoặc cột không cần thiết không?
- [ ] Index ghép có khớp filter, join, order/group không?
- [ ] Có fan-out, N+1 hoặc OFFSET lớn không?
- [ ] Đã đánh giá transaction, lock wait và concurrency chưa?
- [ ] Đã đo p95/p99, throughput, CPU/I/O và chi phí ghi chưa?
- [ ] Chỉ thay đổi một yếu tố mỗi lần và có kế hoạch rollback chưa?

## 27. Bài tập thực hành

1. Bật Slow Query Log trên môi trường lab với `long_query_time` phù hợp; chạy một truy vấn cố ý chậm và đọc log.
2. Dùng `performance_schema.events_statements_summary_by_digest` để xếp hạng top 20 digest theo tổng thời gian và rows examined.
3. Chọn một truy vấn có nhiều rows examined nhưng ít rows sent; ghi baseline trước khi sửa.
4. Chạy `EXPLAIN` và `EXPLAIN ANALYZE`; xác định iterator đầu tiên có actual rows lệch estimate.
5. Viết lại điều kiện `DATE(created_at) = ...` thành khoảng ngày; so sánh plan và kết quả.
6. Thiết kế composite index cho truy vấn lọc theo customer/status và sort theo thời gian; đo cả SELECT lẫn chi phí INSERT/UPDATE.
7. So sánh `SELECT *` với danh sách cột cần thiết trên bảng có TEXT/BLOB.
8. So sánh `LIMIT ... OFFSET ...` ở trang đầu và trang sâu với keyset pagination.
9. Tìm một truy vấn N+1 trong ứng dụng mẫu; thay bằng JOIN hoặc batch và đo số round-trip.
10. Tạo truy vấn JOIN nhiều bảng con gây fan-out; sửa bằng aggregate trước JOIN và đối chiếu tổng tiền.
11. Chạy truy vấn dưới concurrency; so sánh average, p95/p99, throughput và lock wait.
12. Viết báo cáo trước/sau gồm giả thuyết, thay đổi, kết quả, chi phí phụ và cách rollback.

## 28. Ghi nhớ

Tối ưu SQL bắt đầu từ workload và baseline. Thu thập truy vấn bằng Slow Query Log, Performance Schema digest hoặc APM; xếp hạng theo tổng latency, query count, p95/p99, rows examined, temporary tables và tác động nghiệp vụ. Tái hiện với dữ liệu và tham số đại diện, đọc `EXPLAIN`, rồi dùng `EXPLAIN ANALYZE` để đối chiếu estimated rows, actual rows, loops và thời gian.

Sửa nguyên nhân theo thứ tự phù hợp: predicate sargable, chọn cột cần thiết, composite index đúng leftmost prefix, JOIN/cardinality, GROUP BY, ORDER BY/LIMIT, keyset pagination, N+1 và transaction/concurrency. Cập nhật thống kê khi cần, nhưng nhớ histogram đơn cột không giải quyết đầy đủ correlation. Thay đổi từng yếu tố, đo lại dưới tải đại diện, kiểm tra correctness và chi phí ghi, triển khai có theo dõi cùng kế hoạch rollback. Không có một index, hint hay query rewrite nào luôn tốt cho mọi workload.

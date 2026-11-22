# Thiết kế chỉ mục ghép rồi đo ảnh hưởng đến cả đọc và ghi

Một chỉ mục ghép (composite index) có thể làm truy vấn đọc nhanh hơn rõ rệt khi các cột trong chỉ mục khớp với điều kiện lọc, thứ tự sắp xếp và cách ứng dụng truy cập dữ liệu. Nhưng mỗi chỉ mục mới cũng cần dung lượng lưu trữ và phải được duy trì khi INSERT, UPDATE hoặc DELETE. Nếu chỉ đo truy vấn đọc, ta có thể chọn một thiết kế làm p95 SELECT giảm nhưng throughput ghi giảm, WAL tăng, cache bị chiếm dụng và thời gian bảo trì dài hơn. Bài thực hành này đi qua toàn bộ quy trình: xác định query pattern, chọn thứ tự cột, tạo chỉ mục ghép, đo baseline, đo lại cả đọc lẫn ghi và quyết định có nên giữ chỉ mục hay không.

Bài học thuộc chương **Thực hành tổng hợp** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Trong bài này, việc thiết kế chỉ mục ghép được xem là một thay đổi cần kiểm chứng bằng workload đại diện, execution plan, latency, throughput, I/O, chi phí ghi và tính đúng đắn của kết quả.

## 1. Mục tiêu và tiêu chí hoàn thành

Giả sử một ứng dụng bán hàng thường xuyên hiển thị lịch sử đơn hàng của một khách hàng. Bảng `orders` có hàng chục triệu bản ghi. Truy vấn cần lọc theo khách hàng và trạng thái, giới hạn theo thời gian, sắp xếp mới nhất trước và chỉ trả về một trang nhỏ.

Mục tiêu là thiết kế một chỉ mục ghép phù hợp cho truy vấn này, sau đó trả lời được bốn câu hỏi:

1. Truy vấn đọc có thực sự nhanh hơn không? Cải thiện ở p50, p95, p99 và throughput là bao nhiêu?
2. Execution plan đã đổi theo hướng mong muốn chưa? Logical reads, physical reads, rows scanned và sort work có giảm không?
3. INSERT, UPDATE và DELETE bị ảnh hưởng thế nào? WAL/redo, page split, index size, write latency và throughput thay đổi ra sao?
4. Lợi ích đọc có đủ bù chi phí ghi, dung lượng và bảo trì để giữ chỉ mục trong workload tổng thể không?

Một thay đổi chỉ được xem là thành công khi kết quả nghiệp vụ vẫn đúng, truy vấn mục tiêu đạt SLO và workload tổng thể không vượt giới hạn tài nguyên hoặc làm suy giảm các luồng quan trọng khác.

## 2. Mô hình dữ liệu và truy vấn mục tiêu

Giả sử bảng có cấu trúc khái quát:

```sql
CREATE TABLE orders (
    order_id      BIGINT PRIMARY KEY,
    customer_id   BIGINT NOT NULL,
    status        VARCHAR(20) NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    total_amount  DECIMAL(14, 2) NOT NULL,
    note          VARCHAR(500)
);
```

Giả định workload:

- Bảng có khoảng 30 triệu đơn hàng.
- Một khách hàng có thể có từ vài đơn đến hàng nghìn đơn.
- `status` có số lượng giá trị nhỏ, ví dụ `NEW`, `PAID`, `SHIPPED`, `CANCELLED`.
- Phần lớn truy vấn lịch sử tìm một khách hàng cụ thể, lọc một trạng thái và lấy đơn mới nhất.
- INSERT xảy ra liên tục; `status` được UPDATE khi đơn chuyển trạng thái.
- `created_at` gần như bất biến sau khi tạo đơn.
- Ứng dụng chỉ cần `order_id`, `created_at`, `total_amount` cho màn hình danh sách.

Truy vấn đại diện:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND status = :status
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT 50;
```

Đây là query pattern để thiết kế chỉ mục. Trước khi tạo index, cần xác nhận query này có tần suất đủ cao, chiếm latency đáng kể và thật sự nằm trên đường xử lý quan trọng. Không tạo index chỉ vì một câu SQL nhìn có vẻ hợp lý.

## 3. Thu thập workload trước khi thiết kế

Chỉ mục được thiết kế cho workload, không phải chỉ cho cấu trúc bảng. Hãy thu thập:

- Các câu SELECT/UPDATE/DELETE thường chạy trên bảng.
- Predicate, JOIN key, GROUP BY và ORDER BY của từng query pattern.
- Tần suất gọi và tổng thời gian tiêu thụ của từng query fingerprint.
- Số hàng trả về, số hàng ước lượng và số hàng thực tế phải đọc.
- Phân bố giá trị, độ chọn lọc và tương quan giữa các cột.
- Tỷ lệ INSERT/UPDATE/DELETE so với SELECT.
- Các cột thường xuyên thay đổi.
- Các chỉ mục hiện có và mức sử dụng của chúng.
- Yêu cầu latency/throughput của từng luồng nghiệp vụ.

Không nên lấy một query chậm nhất làm đại diện cho toàn bảng. Một index có thể cải thiện query hiếm gặp nhưng làm mọi lần ghi đều tốn thêm chi phí. Cần ưu tiên theo tổng tác động lên workload.

### 3.1. Tần suất và tổng thời gian

Một query mất 500 ms nhưng chạy một lần mỗi ngày có thể ít quan trọng hơn query mất 8 ms nhưng chạy 50.000 lần mỗi phút. Xem cả latency trung bình, percentile, calls và tổng thời gian tiêu thụ.

### 3.2. Phân bố và độ chọn lọc

Độ chọn lọc (selectivity) mô tả tỷ lệ hàng được giữ lại bởi predicate. Predicate `customer_id = ?` có thể giữ 0,001% hàng, trong khi `status = 'PAID'` có thể giữ 60%. Tuy nhiên, số liệu trung bình không phản ánh mọi giá trị: khách hàng lớn hoặc trạng thái phổ biến có thể có cardinality khác hẳn.

Kiểm tra histogram, most-common values, data skew và correlation. Optimizer cần statistics phù hợp để ước lượng số hàng và chọn index scan, bitmap scan hoặc table scan.

### 3.3. Xác định cột ghi thường xuyên

Nếu `status` thay đổi nhiều, đặt `status` trong key của composite index sẽ khiến index entry cần được duy trì khi trạng thái đổi. Nếu `total_amount` nằm trong phần INCLUDE/covering, cập nhật số tiền cũng có thể cần cập nhật index tùy DBMS. Cần đưa tần suất cập nhật của các cột này vào đánh giá chi phí.

## 4. Nguyên tắc chọn thứ tự cột trong chỉ mục ghép

Chỉ mục B-tree ghép được sắp xếp theo thứ tự các cột khai báo. Với index `(a, b, c)`, các entry được sắp xếp theo `a`, sau đó theo `b` trong cùng giá trị `a`, rồi theo `c` trong cùng cặp `(a, b)`. Thứ tự này ảnh hưởng khả năng tìm một vùng liên tục trong index.

### 4.1. Leftmost prefix

Với index `(customer_id, status, created_at)`, các truy vấn có thể tận dụng các prefix như:

- `customer_id = ?`
- `customer_id = ? AND status = ?`
- `customer_id = ? AND status = ? AND created_at >= ?`

Truy vấn chỉ lọc `status = ?` thường không thể dùng index này để tìm một vùng hẹp theo `status` một cách hiệu quả vì cột đầu `customer_id` không được ràng buộc. Một số DBMS có skip scan hoặc chiến lược khác, nhưng không nên mặc định có.

Leftmost prefix không có nghĩa mọi query dùng prefix đều tốt. Nếu prefix giữ phần lớn bảng, optimizer có thể chọn table scan; nếu index không bao phủ cột cần đọc, engine có thể phải lookup nhiều hàng về base table.

### 4.2. Equality, range và ordering

Một quy tắc khởi đầu hữu ích cho B-tree là:

1. Đặt các cột có điều kiện equality thường xuyên ở phía trước.
2. Đặt cột range sau các cột equality.
3. Xem xét cột ORDER BY để index có thể trả hàng theo thứ tự mong muốn.
4. Đưa cột chỉ cần trả về vào INCLUDE nếu DBMS hỗ trợ và chi phí duy trì chấp nhận được.

Đây là điểm khởi đầu, không phải công thức cứng. Thứ tự giữa các cột equality cần dựa trên các query pattern cần hỗ trợ, leftmost prefix, phân bố dữ liệu, partitioning và khả năng dùng index cho những truy vấn khác. Cột có cardinality cao không phải lúc nào cũng phải đứng đầu nếu các truy vấn quan trọng thường lọc theo cột khác.

### 4.3. Áp dụng cho query mục tiêu

Truy vấn có:

- Equality: `customer_id = :customer_id`.
- Equality: `status = :status`.
- Range: `created_at >= :from_time AND created_at < :to_time`.
- Ordering: `ORDER BY created_at DESC`.

Một index ứng viên là:

```text
(customer_id, status, created_at DESC)
```

Hai cột equality đứng trước, cột thời gian range/order đứng sau. Khi một khách hàng có nhiều đơn, index có thể định vị đoạn dữ liệu theo khách hàng và trạng thái rồi đi theo thứ tự thời gian để lấy các hàng phù hợp.

### 4.4. Tác động của range predicate

Khi index đã dùng một cột range, các cột đứng sau thường không thể tiếp tục thu hẹp một khoảng liên tục theo cùng cách như các cột equality trước range. DBMS vẫn có thể dùng chúng cho index condition, filter hoặc ordering tùy engine, nhưng không nên giả định mọi cột sau range đều giảm số entry phải duyệt.

Ví dụ index `(customer_id, created_at, status)` có thể định vị khách hàng và khoảng thời gian, nhưng `status` nằm sau range. Nếu status là điều kiện quan trọng để loại phần lớn entry trong khoảng, thứ tự `(customer_id, status, created_at)` thường phù hợp hơn cho query đã nêu.

## 5. Thiết kế covering index có kiểm soát

Query trả về `order_id`, `created_at`, `total_amount`. Nếu chỉ mục chứa các cột này, DBMS có thể tránh đọc base table cho một số hoặc toàn bộ kết quả.

Với PostgreSQL, cú pháp minh họa:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC)
INCLUDE (order_id, total_amount);
```

`INCLUDE` là cú pháp PostgreSQL và một số DBMS có cơ chế tương tự nhưng cú pháp/semantics khác nhau. Trên hệ quản trị khác, cần dùng cú pháp tương ứng; không sao chép nguyên câu lệnh một cách máy móc.

### 5.1. Key columns và included columns

- **Key columns** tham gia thứ tự sắp xếp của index và có thể dùng để tìm/range/order.
- **Included columns** được lưu trong leaf level để có thể trả kết quả mà không cần đọc base table, nhưng không tham gia thứ tự key của B-tree.

Không đưa mọi cột SELECT vào key. Cột output không cần dùng để định vị hoặc sắp xếp thường có thể nằm trong INCLUDE nếu hệ quản trị hỗ trợ.

### 5.2. Chi phí của INCLUDE

Included column vẫn làm index lớn hơn. Khi giá trị của included column thay đổi, DBMS có thể cần cập nhật index entry. Cột lớn như JSON/text có thể làm index phình to và tăng I/O. Chỉ thêm các cột nhỏ, thường cần và có lợi ích đo được.

### 5.3. Index-only scan có điều kiện

Có đủ cột trong index chưa chắc mọi lần đọc đều hoàn toàn không truy cập base table. Một số hệ quản trị cần kiểm tra visibility hoặc trạng thái hàng. PostgreSQL có thể cần heap fetch khi visibility map chưa đánh dấu page all-visible. Hãy xem actual plan và số heap fetch, không chỉ dựa vào tên `Index Only Scan`.

## 6. Những truy vấn khác có được hưởng lợi không?

Chỉ mục ghép thường được tạo cho một nhóm query pattern. Cần xem các query liên quan để tránh tối ưu một truy vấn nhưng làm các truy vấn khác xấu đi.

| Query pattern | Khả năng dùng index `(customer_id, status, created_at)` |
|---|---|
| Lọc `customer_id` | Có thể dùng prefix đầu |
| Lọc `customer_id` và `status` | Có thể dùng hai cột đầu |
| Lọc đủ customer, status và range created_at | Phù hợp với toàn bộ key |
| Chỉ lọc `status` | Thường không hiệu quả do thiếu leading column |
| Lọc customer và range created_at nhưng không lọc status | Có thể phải xử lý nhiều status trước khi đến created_at; cần đo |
| Lọc customer và sắp xếp toàn bộ đơn theo created_at không phân biệt status | Index này không nhất thiết trả đúng thứ tự toàn cục theo created_at do status nằm giữa |

Nếu query lịch sử cần mọi trạng thái:

```sql
SELECT order_id, status, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 50;
```

index `(customer_id, created_at DESC)` có thể phù hợp hơn. Có thể cần một index thứ hai nếu query này quan trọng, nhưng mỗi index mới đều có chi phí ghi và dung lượng. Hãy chứng minh bằng workload tổng thể trước khi thêm.

## 7. Các thiết kế cần cân nhắc ngoài B-tree ghép

### 7.1. Partial/filtered index

Nếu query thường chỉ lấy một tập nhỏ trạng thái, partial index có thể nhỏ hơn index chứa mọi hàng. Ví dụ PostgreSQL:

```sql
CREATE INDEX CONCURRENTLY idx_orders_open_customer_created
ON orders (customer_id, created_at DESC)
INCLUDE (order_id, total_amount)
WHERE status IN ('NEW', 'PAID');
```

Partial index chỉ hữu ích khi predicate truy vấn tương thích với điều kiện của index và optimizer chứng minh được điều đó. Nếu query dùng tham số tổng quát hoặc biểu thức khác, khả năng sử dụng có thể bị giới hạn tùy DBMS và plan mode. Partial index cũng cần duy trì khi hàng đi vào hoặc ra khỏi tập điều kiện.

### 7.2. Expression/function-based index

Nếu query lọc theo biểu thức như `LOWER(email)`, có thể cân nhắc expression index nếu DBMS hỗ trợ. Tuy nhiên, index phải khớp biểu thức, collation và semantics. Không tạo expression index để bù cho một predicate có thể viết lại đơn giản và sargable hơn nếu điều đó đủ giải quyết vấn đề.

### 7.3. Unique composite index

Nếu nghiệp vụ yêu cầu một tổ hợp cột là duy nhất, unique composite index vừa thực thi constraint vừa có thể hỗ trợ truy vấn. Cần xác định rõ semantics của NULL và collation vì các DBMS có quy tắc khác nhau. Không dùng unique index chỉ để tối ưu nếu dữ liệu không thỏa uniqueness.

### 7.4. Index trên partitioned table

Với bảng partition, cần hiểu index là local/partitioned hay global tùy hệ quản trị. Query có predicate trên partition key có thể prune partition trước khi dùng index trong partition. Index ghép phải phù hợp cả partitioning strategy lẫn query predicates. DDL và tính năng index trên partitioned table khác nhau giữa DBMS.

## 8. Đo baseline trước khi tạo index

Không thể kết luận một index tốt nếu không biết trạng thái trước thay đổi. Trước hết, đóng băng cấu hình benchmark và ghi lại:

- Phiên bản DBMS, driver và hệ điều hành.
- CPU, RAM, storage, network và topology.
- Row count, table size, index size và data distribution.
- Statistics/histogram và thời điểm cập nhật.
- Query mix, tham số đại diện và concurrency.
- Warm/cold cache state.
- Transaction mix và commit frequency.
- p50, p95, p99, throughput, error rate và timeout.
- Logical reads, physical reads, rows scanned, rows returned.
- CPU, I/O latency, WAL/redo, lock waits và checkpoint/flush.

### 8.1. Lưu execution plan

Với PostgreSQL, có thể lấy actual plan cho SELECT:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42001
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN ANALYZE` thực thi câu truy vấn. Chỉ chạy trên môi trường benchmark hoặc trong phạm vi được phép. Với DML, nó thực sự thực hiện thao tác; không chạy tùy tiện trên dữ liệu production.

Ghi nhận:

- Scan type: Seq Scan, Index Scan, Bitmap Scan hoặc loại tương ứng.
- Estimated rows và actual rows.
- `Rows Removed by Filter` nếu có.
- Shared/local/temp buffers hit/read/dirtied/written.
- Sort method, memory và disk spill.
- Actual time và số vòng lặp.
- Heap fetch nếu dùng index-only scan.

Các hệ quản trị khác có công cụ tương đương như actual execution plan, logical reads, query profile hoặc statement statistics. Dùng cách đo phù hợp DBMS.

### 8.2. Đo query fingerprint thay vì chỉ một lần chạy

Nếu có nhiều giá trị `customer_id`, hãy đo một tập tham số gồm khách hàng nhỏ, trung bình và lớn. Một index có thể rất nhanh với khách hàng có 20 đơn nhưng chậm hơn nhiều với khách hàng có 500.000 đơn. Đo phân bố latency theo tham số để nhận diện skew và parameter-sensitive plans.

## 9. Tạo chỉ mục và cập nhật statistics

Sau khi đã có baseline, tạo index ứng viên trong môi trường benchmark.

Ví dụ PostgreSQL:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC)
INCLUDE (order_id, total_amount);

ANALYZE orders;
```

`CREATE INDEX CONCURRENTLY` giảm mức chặn ghi so với một số cách build index thông thường trong PostgreSQL, nhưng vẫn tiêu tốn I/O/CPU, có thể chờ transaction và không chạy được bên trong transaction block. Cú pháp và mức blocking khác hệ quản trị. Trong benchmark cô lập, có thể chọn cách tạo index phù hợp; trong production phải theo đúng hướng dẫn triển khai của DBMS.

Sau khi tạo index, cập nhật hoặc kiểm tra statistics theo chính sách DBMS. Optimizer có thể chưa chọn index nếu statistics cũ, estimate cho thấy scan rẻ hơn hoặc query không khớp key order.

Không xóa index cũ ngay chỉ vì index mới được tạo. Trước tiên hãy xác minh query plan, correctness và tác động đến các query khác. Việc loại bỏ index cũ cần một bước đánh giá riêng dựa trên usage và dependency.

## 10. Đo lại truy vấn đọc

Chạy cùng query với cùng tập tham số, concurrency, thời lượng và cache protocol như baseline.

So sánh:

| Metric | Baseline | Sau index | Cách diễn giải |
|---|---:|---:|---|
| p50 query latency | Đo | Đo | Thời gian điển hình |
| p95 query latency | Đo | Đo | Tail latency của phần lớn request |
| p99 query latency | Đo | Đo | Các request chậm nhất trong percentile |
| Successful QPS/TPS | Đo | Đo | Throughput thành công |
| Logical reads | Đo | Đo | Số page/buffer phải xử lý |
| Physical reads | Đo | Đo | Đọc storage thực tế trong cửa sổ đo |
| Rows scanned/visited | Đo | Đo | Lượng hàng phải xem xét |
| Sort/spill | Đo | Đo | Có còn sort lớn hoặc ghi temp không |
| CPU/query | Đo | Đo | Chi phí xử lý CPU |

Không điền số liệu giả định vào báo cáo như thể đã đo. Mục tiêu là thu được số liệu từ cùng môi trường và ghi rõ nguồn đo.

### 10.1. Execution plan sau index

Plan có thể đổi từ sequential/table scan sang index scan hoặc index-only scan. Nhưng index scan không luôn tốt hơn table scan. Nếu predicate trả về phần lớn hàng, random lookup nhiều page có thể đắt hơn scan tuần tự. Optimizer có quyền bỏ qua index nếu ước lượng cost cho thấy scan rẻ hơn.

Kiểm tra index condition có sử dụng các cột dự kiến không, filter còn lại bao nhiêu hàng, số heap/table lookup và sort có được loại bỏ hay không. Một plan dùng index nhưng phải đọc rất nhiều entry hoặc fetch từng hàng ngẫu nhiên có thể vẫn chậm.

### 10.2. ORDER BY và LIMIT

Nếu index key có thứ tự tương thích với `ORDER BY`, DBMS có thể đọc theo thứ tự và dừng sau khi đủ 50 hàng phù hợp, tránh sort toàn bộ tập kết quả. Hướng ASC/DESC, NULL ordering và collation có thể ảnh hưởng khả năng dùng index; nhiều B-tree hỗ trợ scan ngược nhưng chi tiết phụ thuộc DBMS.

## 11. Đo ảnh hưởng đến INSERT

Mỗi INSERT vào bảng có index thường phải tạo entry tương ứng cho từng index có liên quan. Composite index rộng làm tăng số byte ghi, page access, WAL/redo và cache pressure.

Đo cùng workload insert trước và sau khi thêm index:

- Inserts per second.
- p50/p95/p99 thời gian INSERT/commit.
- WAL/redo bytes và log flush latency.
- CPU và storage write IOPS/latency.
- Index size và tốc độ tăng dung lượng.
- Page split/fragmentation nếu DBMS cung cấp metric.
- Deadlock, lock wait và error rate.

Nếu ứng dụng insert theo batch, giữ nguyên batch size, commit frequency và transaction boundary. Không so sánh batch insert với insert từng hàng rồi gán chênh lệch cho index.

## 12. Đo ảnh hưởng đến UPDATE và DELETE

UPDATE cột tham gia index key có thể yêu cầu xóa entry cũ và tạo entry mới hoặc một cơ chế tương đương. Nếu cập nhật `status`, index `(customer_id, status, created_at)` phải duy trì thứ tự key mới. UPDATE cột INCLUDE như `total_amount` cũng có thể làm index entry cần thay đổi. DELETE cần đánh dấu/xóa entry và có thể tạo công việc vacuum/cleanup.

Thiết kế workload ghi cần phân biệt:

| Loại ghi | Tác động tiềm năng |
|---|---|
| INSERT hàng mới | Thêm entry vào composite index; tăng WAL/redo và page writes |
| UPDATE `status` | Thay đổi key column; có thể phải cập nhật index entry |
| UPDATE `total_amount` | Nếu là INCLUDE column, index entry có thể phải cập nhật |
| UPDATE `note` | Nếu không thuộc index, có thể tránh cập nhật index đó, tùy storage/engine |
| DELETE | Gỡ/đánh dấu entry, tăng công việc cleanup và maintenance |

Trong PostgreSQL, HOT update chỉ có thể xảy ra khi các điều kiện phù hợp, trong đó thay đổi không làm cần cập nhật index. Việc thêm index trên một cột thường xuyên thay đổi có thể làm giảm cơ hội HOT update. Các hệ quản trị khác có cơ chế lưu trữ và update khác nhau; hãy dùng metrics riêng của DBMS.

### 12.1. Index rộng làm tăng write amplification

Write amplification là hiện tượng một thay đổi logic nhỏ gây ra nhiều công việc ghi vật lý hơn. Khi thêm index, một INSERT có thể phải ghi base table, nhiều index, WAL/redo và các page liên quan. Một index rộng làm tăng bytes phải duy trì và có thể tăng checkpoint/flush workload.

Đo bytes log trên mỗi hàng ghi hoặc trên mỗi transaction, thay vì chỉ nhìn tổng log bytes khi tốc độ tải khác nhau.

## 13. Đo dung lượng và chi phí bảo trì

Index mới tiêu thụ storage và cache. Với bảng lớn, composite index có thể chiếm nhiều GB. Cần đo:

- Tổng kích thước index.
- Tỷ lệ index size so với table size.
- Số page và mức độ sử dụng.
- Growth rate theo ngày/tuần.
- Bloat/fragmentation theo công cụ DBMS.
- Chi phí backup/restore và replication.
- Thời gian build/rebuild và mức ảnh hưởng khi bảo trì.
- Cache hit và eviction của buffer pool.

Index không dùng có thể chiếm cache và làm các page hữu ích khác bị đẩy ra. Tuy nhiên, không xóa index chỉ dựa vào một khoảng đo ngắn; cần xem workload theo chu kỳ, truy vấn hiếm nhưng quan trọng và index dependency/constraint.

## 14. Thiết kế A/B benchmark công bằng

Để xác định ảnh hưởng của index, tạo hai cấu hình có thể so sánh:

- **A — Baseline:** schema và index ban đầu.
- **B — Candidate:** chỉ thêm composite index đang đánh giá.

Giữ các điều kiện khác giống nhau:

- Cùng database version, hardware, storage và network.
- Cùng dataset, row count, data distribution và statistics policy.
- Cùng query parameters và transaction mix.
- Cùng client count/offered rate và connection behavior.
- Cùng warm-up, measurement window và số lần lặp.
- Cùng cache state hoặc tách riêng cold-cache/warm-cache tests.
- Cùng background workload hoặc bảo đảm không có background task làm lệch một phía.

Chỉ thay một yếu tố chính trong mỗi thử nghiệm. Nếu đồng thời đổi index, memory setting, pool size và query text, sẽ khó biết yếu tố nào tạo ra kết quả.

### 14.1. Tránh sai lệch do thứ tự chạy

Nếu luôn chạy A trước rồi B sau, cache, nhiệt độ hệ thống, checkpoint hoặc background activity có thể làm B được lợi. Có thể lặp theo thứ tự A-B-B-A hoặc chạy nhiều vòng với reset/warm-up nhất quán. Không xóa cache tùy tiện trên hệ thống dùng chung.

### 14.2. Dùng cùng workload mix

Một ví dụ mix cần đo:

| Transaction | Tỷ trọng giả định | Mục tiêu |
|---|---:|---|
| Tra cứu lịch sử đơn hàng | 45% | Đo read benefit của index |
| Tra cứu đơn hàng theo ID | 20% | Kiểm tra query khác có bị ảnh hưởng |
| INSERT đơn hàng | 15% | Đo chi phí thêm index entry |
| UPDATE trạng thái | 15% | Đo cập nhật key column |
| UPDATE ghi chú | 5% | Đo ghi cột không nằm trong index |

Tỷ trọng phải lấy từ telemetry hoặc mô hình tải thực tế. Nếu chỉ chạy SELECT, không thể kết luận ảnh hưởng đến workload tổng thể.

## 15. Phân tích kết quả bằng số liệu

Ví dụ bảng báo cáo, các ô cần được điền từ phép đo thật:

| Metric | A: Baseline | B: Composite index | Chênh lệch |
|---|---:|---:|---:|
| History query p95 | Ghi số đo | Ghi số đo | B so với A |
| History query p99 | Ghi số đo | Ghi số đo | B so với A |
| Overall successful TPS | Ghi số đo | Ghi số đo | B so với A |
| INSERT p95 | Ghi số đo | Ghi số đo | B so với A |
| UPDATE status p95 | Ghi số đo | Ghi số đo | B so với A |
| Logical reads/query | Ghi số đo | Ghi số đo | B so với A |
| WAL bytes/transaction | Ghi số đo | Ghi số đo | B so với A |
| Index storage | Không áp dụng | Ghi số đo | Chi phí thêm |
| Error/deadlock rate | Ghi số đo | Ghi số đo | B so với A |

Đánh giá cả phần trăm thay đổi và giá trị tuyệt đối. Ví dụ p95 giảm 20% nhưng từ 1.000 ms còn 800 ms có thể vẫn không đạt SLO; p95 tăng 5% từ 4 ms lên 4,2 ms có thể chấp nhận nếu write throughput và latency đọc quan trọng cải thiện đáng kể.

### 15.1. Không cộng/trừ các percentile

Percentile của tổng latency không bằng tổng percentile của từng thành phần. Nếu cần phân tích thành phần, dùng tracing hoặc histogram theo stage. So sánh p95 của cùng transaction giữa A và B, không cộng p95 query với p95 commit để suy ra p95 request.

### 15.2. Xem cả throughput và latency

Throughput có thể tăng trong khi latency tail xấu đi nếu hệ thống đẩy nhiều request hơn vào queue. Cần đặt giới hạn concurrency/offered rate và theo dõi p95/p99 cùng error rate. Chỉ số TPS cao nhất không nhất thiết là điểm vận hành tốt nhất.

## 16. Ví dụ PostgreSQL: quy trình đo cụ thể

Ví dụ này minh họa cách thu thập plan và statistics trên PostgreSQL. Tên bảng/cột và số liệu là giả định; điều chỉnh cho schema test của bạn.

### 16.1. Baseline query plan

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42001
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
```

Lưu toàn bộ plan và các buffer counters. Chạy cùng truy vấn nhiều lần với các customer ID đại diện; tách warm-cache và cold-cache nếu mục tiêu yêu cầu.

### 16.2. Tạo index ứng viên

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC)
INCLUDE (order_id, total_amount);

ANALYZE orders;
```

Sau khi index hoàn tất, chạy lại đúng câu SELECT và tham số. Kiểm tra planner có dùng index hay không, số buffer read/hit, heap fetch, actual rows và sort node.

### 16.3. Xem index usage và dung lượng

Ví dụ truy vấn thống kê PostgreSQL:

```sql
SELECT
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE relname = 'orders'
ORDER BY pg_relation_size(indexrelid) DESC;
```

Counters trong `pg_stat_user_indexes` có phạm vi và reset behavior riêng. Lấy snapshot trước/sau measurement window và tính delta; `idx_scan` thấp trong một khoảng ngắn không chứng minh index không cần thiết.

### 16.4. Xem workload statement

Nếu `pg_stat_statements` được cài và bật, có thể xem query fingerprint, calls và execution time. Ví dụ:

```sql
SELECT
    queryid,
    calls,
    mean_exec_time,
    total_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Các cột có thể khác theo phiên bản extension. Thống kê là counters tích lũy kể từ reset hoặc thời điểm thống kê được khởi tạo; dùng snapshot/delta và cùng cửa sổ đo. Query text có thể chứa literal nhạy cảm tùy cấu hình; bảo vệ output.

### 16.5. Đo INSERT/UPDATE

Trong database benchmark riêng, chạy cùng một generator hoặc script ghi với hai cấu hình A/B. Ghi số hàng thành công, latency commit, WAL bytes, CPU, I/O và lock waits. Không dùng `EXPLAIN ANALYZE` cho DML như thể nó chỉ lập kế hoạch; nó thực sự thực thi thao tác. Không chạy workload ghi benchmark trên dữ liệu production nếu chưa có kế hoạch được phép và kiểm soát tải.

## 17. Khi nào không nên thêm chỉ mục ghép?

Không nên thêm index nếu:

- Query hiếm gặp và không nằm trong SLO quan trọng.
- Predicate chọn lọc thấp, table scan đã rẻ hơn.
- Query chỉ chạy trên bảng nhỏ.
- Index trùng lặp hoặc gần như trùng với index hiện có.
- Các cột key thay đổi rất thường xuyên và chi phí ghi lớn.
- Index làm tăng dung lượng vượt ngân sách hoặc đẩy working set khỏi cache.
- Query thực tế không khớp leftmost prefix hoặc predicate không tương thích.
- Statistics cho thấy optimizer không thể ước lượng tốt và vấn đề gốc chưa được xử lý.
- Workload phân tích phù hợp với partition pruning, columnar scan hoặc summary table hơn B-tree.

Nếu vấn đề là query trả về phần lớn bảng, tạo thêm B-tree không nhất thiết giúp. Nếu bottleneck là lock contention, CPU, network hoặc application pool, index có thể không giải quyết nguyên nhân chính.

## 18. Rollout và theo dõi sau khi triển khai

Sau benchmark, nếu index có lợi ích tổng thể, triển khai theo quy trình phù hợp DBMS:

1. Kiểm tra dung lượng trống, thời gian build và tài nguyên cần thiết.
2. Chọn phương thức tạo index giảm blocking phù hợp với hệ quản trị.
3. Theo dõi build progress, lock, CPU, I/O, WAL/redo và replication lag.
4. Xác minh index hợp lệ/usable sau khi build.
5. Kiểm tra execution plan của query mục tiêu và query liên quan.
6. Theo dõi read/write latency, throughput, error rate và storage sau rollout.
7. Ghi nhận index usage qua một chu kỳ workload đủ đại diện.
8. Nếu tác động phụ vượt ngưỡng, thực hiện rollback/drop theo quy trình đã chuẩn bị.

Không drop index cũ hoặc index có thể phục vụ constraint trước khi kiểm tra dependency và workload theo chu kỳ. Việc tạo hoặc xóa index trên bảng lớn có thể ảnh hưởng I/O, replication và backup.

## 19. Những sai lầm thường gặp

- **Chỉ chọn cột theo cardinality cao nhất:** bỏ qua query pattern, prefix và ordering.
- **Đặt cột range trước cột equality:** có thể làm các điều kiện phía sau khó thu hẹp vùng index.
- **Đưa mọi cột output vào key:** làm index rộng và tăng write cost; cân nhắc INCLUDE.
- **Tạo index cho một query nhưng bỏ qua query mix:** có thể làm workload tổng thể chậm hơn.
- **Chỉ đo SELECT:** bỏ qua INSERT/UPDATE/DELETE và write amplification.
- **So sánh A/B với cache hoặc dataset khác nhau:** kết quả không công bằng.
- **Chỉ nhìn tên Index Scan:** không xem rows visited, heap fetch, buffers và actual time.
- **Cho rằng index mới luôn được optimizer chọn:** cost model có thể chọn scan nếu rẻ hơn.
- **Không cập nhật/kiểm tra statistics:** optimizer có thể dùng cardinality estimate sai.
- **Đưa cột hay thay đổi vào index mà không đo:** làm tăng maintenance và có thể giảm cơ hội tối ưu update.
- **Không tính storage/backup/replication:** index mới tạo chi phí vận hành dài hạn.
- **Đo một lần duy nhất:** dễ bị nhiễu bởi cache, checkpoint và background task.
- **Không kiểm tra tính đúng đắn:** truy vấn nhanh nhưng thiếu/nhân bản hàng vẫn là thất bại.
- **Dùng cú pháp index của DBMS này trên DBMS khác:** INCLUDE, online/concurrent build, partial index và scan behavior không đồng nhất.

## 20. Bài tập tự kiểm tra

### Bài tập 1: Chọn thứ tự cột

Query thường xuyên lọc `tenant_id = ?`, `status = ?`, khoảng `created_at` và sắp xếp theo `created_at DESC`.

**Câu hỏi:** index ứng viên nào đáng thử trước?

**Gợi ý trả lời:** bắt đầu với `(tenant_id, status, created_at DESC)` vì hai điều kiện equality đứng trước range/order. Xác nhận thêm các query khác có dùng prefix tenant hay không, phân bố status, và actual plan. Đây là giả thuyết cần đo, không phải đáp án đúng cho mọi workload.

### Bài tập 2: Query chỉ lọc cột thứ hai

Có index `(customer_id, status, created_at)`. Một query chỉ có `WHERE status = 'PAID'`.

**Câu hỏi:** có thể kỳ vọng index này tìm trực tiếp một vùng hẹp không?

**Gợi ý trả lời:** thường không, vì thiếu leading column `customer_id`. Một số engine có chiến lược skip scan nhưng phải kiểm tra plan và phiên bản. Có thể cần index khác nếu query quan trọng và chi phí ghi chấp nhận được.

### Bài tập 3: Đọc nhanh hơn, ghi chậm hơn

Sau khi thêm composite index, query history p95 giảm 45%, INSERT throughput giảm 8%, UPDATE status p95 tăng 18% và WAL/transaction tăng 12%.

**Câu hỏi:** có nên giữ index ngay không?

**Gợi ý trả lời:** chưa thể kết luận chỉ từ một query. Đối chiếu tỷ trọng đọc/ghi, SLO từng luồng, tổng throughput, chi phí vận hành và yêu cầu dung lượng. Nếu query history là đường quan trọng, trade-off có thể chấp nhận; nếu UPDATE status nằm trên đường giao dịch chính và vượt SLO, cần thử thiết kế hẹp hơn hoặc index khác.

### Bài tập 4: INCLUDE hay key?

Query lọc theo `customer_id`, `status`, `created_at`, nhưng chỉ trả `total_amount` và `order_id`.

**Câu hỏi:** hai cột output có nhất thiết phải là key columns?

**Gợi ý trả lời:** không. Nếu DBMS hỗ trợ, có thể đặt chúng trong INCLUDE để phục vụ covering/index-only access mà không làm chúng tham gia thứ tự key. Vẫn cần đo kích thước và chi phí UPDATE nếu các cột này thay đổi.

### Bài tập 5: Index mới không được chọn

Sau khi tạo index, execution plan vẫn dùng sequential/table scan.

**Câu hỏi:** cần kiểm tra điều gì trước khi ép optimizer dùng index?

**Gợi ý trả lời:** kiểm tra query predicate và kiểu dữ liệu, leftmost prefix, selectivity, rows estimate, statistics, số hàng thực tế cần trả, cost random lookup và cache. Scan có thể thật sự rẻ hơn nếu query đọc phần lớn bảng. Không ép plan trước khi hiểu nguyên nhân.

### Bài tập 6: Chỉ số đọc cải thiện nhưng p99 không đổi

Logical reads giảm mạnh sau index nhưng p99 end-to-end gần như không đổi.

**Câu hỏi:** những thành phần nào cần điều tra?

**Gợi ý trả lời:** pool wait, network, lock wait, queueing, CPU ở application, result serialization, cache miss ở tầng khác và các tham số skew. Đo query execution riêng với end-to-end trace để tìm bottleneck còn lại.

## 21. Mẫu báo cáo capstone

Ghi lại kết quả bằng một báo cáo ngắn nhưng đủ để người khác lặp lại:

```text
Tên thử nghiệm:
Mục tiêu/SLO:
DBMS và phiên bản:
Hardware/storage/network:
Schema/table size/row count:
Index hiện có:
Query fingerprint và query parameters:
Transaction mix:
Concurrency/offered rate:
Dataset distribution/hot keys:
Warm-up và measurement duration:
Số lần chạy:

Candidate index:
DDL và phương thức build:
Index size:

Kết quả A - baseline:
  Read p50/p95/p99, QPS/TPS, logical/physical reads
  Insert/update/delete throughput và latency
  WAL/redo, CPU, I/O, lock waits, error rate

Kết quả B - candidate:
  Read p50/p95/p99, QPS/TPS, logical/physical reads
  Insert/update/delete throughput và latency
  WAL/redo, CPU, I/O, lock waits, error rate

Execution plan trước/sau:
Correctness checks:
Trade-offs:
Quyết định: giữ / sửa / loại index
Lý do và ngưỡng theo dõi sau rollout:
```

## 22. Checklist thực hành

- [ ] Đã xác định query pattern và lý do cần index bằng workload/telemetry.
- [ ] Đã thu thập các query liên quan và tỷ trọng đọc/ghi.
- [ ] Đã kiểm tra cardinality, selectivity, skew và correlation.
- [ ] Đã xác định equality, range, join và ordering predicates.
- [ ] Đã chọn thứ tự key theo leftmost prefix và query mix.
- [ ] Đã cân nhắc covering/INCLUDE mà không làm index rộng quá mức.
- [ ] Đã kiểm tra index hiện có để tránh trùng lặp.
- [ ] Đã lưu baseline plan, p50/p95/p99, throughput, reads và resource metrics.
- [ ] Đã tạo index ứng viên trong môi trường phù hợp và cập nhật statistics.
- [ ] Đã xác minh query optimizer dùng index theo cách có lợi.
- [ ] Đã đo lại SELECT với cùng dữ liệu, tham số, concurrency và cache protocol.
- [ ] Đã đo INSERT, UPDATE, DELETE và commit latency.
- [ ] Đã đo WAL/redo, index size, CPU, I/O, lock waits và replication impact.
- [ ] Đã xác minh correctness, duplicate, NULL và boundary conditions.
- [ ] Đã lặp lại benchmark và lưu raw output/DDL/plan.
- [ ] Đã quyết định giữ, sửa hoặc loại index dựa trên workload tổng thể.
- [ ] Đã có kế hoạch rollout, theo dõi và rollback phù hợp DBMS.

Thiết kế chỉ mục ghép bắt đầu từ query pattern và thứ tự điều kiện thực tế: equality, range, ordering và các cột cần trả về. Composite index có thể giảm scan, sort và lookup cho truy vấn đọc, nhưng đồng thời làm tăng dung lượng và công việc duy trì khi ghi, nhất là khi các cột key hoặc INCLUDE thường xuyên thay đổi. Hãy đo baseline, tạo một ứng viên, kiểm tra execution plan, benchmark cả SELECT lẫn INSERT/UPDATE/DELETE trong cùng điều kiện, rồi quyết định theo SLO và workload tổng thể thay vì chỉ dựa vào một con số latency.

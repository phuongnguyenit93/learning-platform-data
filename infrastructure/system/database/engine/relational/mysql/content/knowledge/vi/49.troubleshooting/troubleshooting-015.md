# Truy vấn chậm đột ngột do thống kê, dữ liệu lệch hoặc đổi kế hoạch

Một truy vấn MySQL vốn chạy nhanh nhưng đột nhiên chậm có thể do dữ liệu tăng, phân bố giá trị thay đổi, thống kê index không còn đại diện, histogram cũ hoặc optimizer chọn một execution plan khác. Cũng có thể truy vấn không đổi nhưng tải hệ thống, lock contention, I/O hoặc replication làm thời gian phản hồi tăng. Vì vậy, trước khi thêm index hoặc ép optimizer dùng một đường truy cập, cần xác định truy vấn nào chậm, kế hoạch đã thay đổi hay chưa và số hàng thực tế khác ước lượng ở đâu.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung xử lý suy giảm hiệu năng truy vấn do thống kê, data skew và thay đổi execution plan. Nội dung kết nối index, optimizer, `EXPLAIN`, InnoDB persistent statistics, histogram và giám sát production.

Sau bài học, bạn có thể:

- Khoanh vùng truy vấn chậm bằng statement digest và số liệu thực thi.
- So sánh execution plan trước và sau khi hiệu năng thay đổi.
- Đọc estimated rows, actual rows, access type và các bước join.
- Hiểu InnoDB index statistics, persistent stats và auto recalculation.
- Dùng histogram để mô tả phân bố giá trị lệch.
- Phân biệt vấn đề thống kê với vấn đề index, SQL, lock hoặc tài nguyên.
- Khôi phục hiệu năng bằng cách cập nhật stats, cải thiện index hoặc sửa truy vấn.
- Đánh giá rủi ro khi dùng optimizer hint và kiểm soát thay đổi plan.

## 1. Nhận diện đúng phạm vi sự cố

Khi có báo cáo “truy vấn chậm”, hãy xác định đó là một câu SQL, một nhóm truy vấn hay toàn bộ database:

- Chỉ một query digest chậm, còn các truy vấn khác bình thường: tập trung vào SQL, index, thống kê và execution plan.
- Nhiều truy vấn trên cùng bảng cùng chậm: kiểm tra tải I/O, lock, buffer pool, thay đổi dữ liệu hoặc DDL.
- Nhiều truy vấn trên nhiều bảng cùng chậm: kiểm tra CPU, memory, storage latency, connection saturation và workload tổng thể.
- Chỉ một số giá trị tham số chậm: nghi ngờ data skew, độ chọn lọc khác nhau hoặc truy vấn không phù hợp với mọi phân bố dữ liệu.
- Truy vấn chậm sau deploy, bulk load, `ANALYZE TABLE`, thêm index hoặc nâng cấp MySQL: so sánh thay đổi schema, stats, optimizer settings và phiên bản.

Không bắt đầu bằng việc chạy `ANALYZE TABLE` hoặc `FORCE INDEX` ngay khi thấy một query chậm. Trước tiên lưu bằng chứng để biết vấn đề nằm ở đâu và có thể so sánh kết quả sau khi xử lý.

## 2. Khoanh vùng truy vấn bằng Performance Schema

Performance Schema tổng hợp statement theo digest, giúp tìm các câu SQL tiêu tốn thời gian hoặc đọc quá nhiều hàng. Ví dụ truy vấn top digest theo tổng thời gian:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS avg_ms,
    ROUND(MAX_TIMER_WAIT / 1000000000, 2) AS max_ms,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    FIRST_SEEN,
    LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các timer trong Performance Schema được biểu diễn bằng picosecond; chia cho `1,000,000,000` để đổi sang millisecond. `COUNT_STAR`, `AVG_TIMER_WAIT`, `MAX_TIMER_WAIT`, `SUM_ROWS_EXAMINED` và `SUM_ROWS_SENT` giúp nhìn ra truy vấn chạy nhiều lần, truy vấn có độ trễ lớn hoặc truy vấn quét quá nhiều hàng.

Lưu ý:

- Digest chuẩn hóa literal, vì vậy nhiều giá trị tham số có thể được gộp vào cùng một digest.
- `AVG_TIMER_WAIT` có thể che giấu một số lần chạy rất chậm; hãy xem cả `MAX_TIMER_WAIT` và phân vị latency từ hệ thống monitoring.
- `SUM_ROWS_EXAMINED` cao không tự động chứng minh plan sai; cần so với số hàng trả về và mục tiêu truy vấn.
- Performance Schema có thể bị reset khi server restart hoặc khi summary bị truncate; cần lưu số liệu theo chu kỳ nếu cần lịch sử dài hạn.

Kiểm tra truy vấn đang chạy:

```sql
SHOW FULL PROCESSLIST;
```

Ghi nhận SQL fingerprint, schema, thời gian chạy, trạng thái, số hàng đọc/trả về, thời điểm bắt đầu và thay đổi gần đây. Không đưa literal chứa dữ liệu cá nhân hoặc bí mật vào báo cáo chia sẻ rộng.

## 3. Chụp execution plan trước khi thay đổi

`EXPLAIN` cho biết optimizer dự định thực hiện truy vấn theo cách nào. Với một truy vấn đang chậm, lưu plan ở đúng server, schema, session settings và dạng SQL đang được ứng dụng chạy.

### 3.1. EXPLAIN dạng bảng

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `select_type` | Loại SELECT, ví dụ SIMPLE, PRIMARY hoặc SUBQUERY |
| `table` | Bảng hoặc derived table đang được đọc |
| `type` | Access type, từ const/eq_ref/ref/range tới index/ALL |
| `possible_keys` | Index optimizer có thể cân nhắc |
| `key` | Index optimizer dự kiến chọn |
| `key_len` | Độ dài phần index được sử dụng |
| `rows` | Số hàng optimizer ước lượng phải đọc |
| `filtered` | Tỷ lệ hàng ước lượng còn lại sau điều kiện lọc |
| `Extra` | Thông tin bổ sung như Using filesort, Using temporary hoặc Using index |

`ALL` thường biểu thị full table scan; `index` có thể là full index scan. Tuy nhiên, scan toàn bảng có thể là lựa chọn hợp lý khi bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu. `Using filesort` và `Using temporary` cũng không tự động là lỗi; hãy đánh giá lượng dữ liệu, thời gian và kế hoạch tổng thể.

### 3.2. EXPLAIN FORMAT=JSON

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

JSON plan có thêm thông tin về cost, access path, điều kiện được đẩy xuống, estimated rows và join. Đây là định dạng hữu ích để so sánh các plan trong báo cáo tự động.

### 3.3. EXPLAIN ANALYZE

Trên MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi truy vấn SELECT rồi trả về cây thực thi cùng số liệu thực tế:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Output thường có `actual time`, `rows` và `loops` cho từng iterator. So sánh số hàng ước lượng trong `EXPLAIN` với số hàng thực tế trong `EXPLAIN ANALYZE`. Nếu ước lượng sai lệch rất lớn ở một bước, đó là dấu hiệu cần kiểm tra thống kê, data skew, correlation hoặc điều kiện lọc.

`EXPLAIN ANALYZE` thực sự chạy câu SELECT. Không chạy truy vấn nặng trên production nếu chưa đánh giá tải và tác động. Nên dùng staging hoặc replica phù hợp, truy vấn có giới hạn dữ liệu và cửa sổ kiểm tra được kiểm soát. Không dùng nó với một SELECT có stored function gây tác dụng phụ.

## 4. Hiểu vì sao optimizer đổi kế hoạch

MySQL optimizer chọn access path dựa trên chi phí ước lượng. Chi phí phụ thuộc thống kê số hàng, cardinality index, selectivity của điều kiện, histogram, kích thước bảng, index có sẵn và các thiết lập optimizer.

Một thay đổi nhỏ trong thống kê có thể làm thứ tự ưu tiên giữa hai plan thay đổi. Ví dụ:

- Trước đây `order_status = 'PAID'` chỉ khớp 2% hàng, nên index status có vẻ hữu ích.
- Sau một chiến dịch thanh toán, 80% đơn chuyển sang `PAID`.
- Optimizer ước lượng index scan cộng nhiều lần truy cập hàng có thể đắt hơn table scan.
- Kế hoạch mới có thể bỏ index dù SQL không đổi.

Kế hoạch mới không nhất thiết sai. Nếu dữ liệu thực sự thay đổi, plan khác có thể là lựa chọn tốt hơn. Sự cố xảy ra khi ước lượng không phản ánh dữ liệu hoặc plan mới làm truy vấn quan trọng vượt SLA.

Các nguyên nhân thường gặp:

1. Bulk insert/update/delete làm phân bố dữ liệu thay đổi.
2. InnoDB tự động cập nhật persistent stats hoặc quản trị viên chạy `ANALYZE TABLE`.
3. Index mới được tạo, xóa hoặc đổi trạng thái visible/invisible.
4. Histogram không còn phản ánh phân bố hiện tại.
5. Bảng tăng nhanh hoặc thay đổi tỷ lệ giữa các giá trị.
6. MySQL được nâng cấp, optimizer cost model hoặc mặc định thay đổi.
7. `optimizer_switch`, SQL mode, collation hoặc session settings khác giữa môi trường.
8. SQL bị sửa, thêm điều kiện, đổi kiểu tham số hoặc xuất hiện implicit conversion.

Lưu plan và cấu hình trước/sau để phân biệt thay đổi dữ liệu với thay đổi từ ứng dụng hoặc server.

## 5. InnoDB index statistics và persistent statistics

InnoDB duy trì thống kê về bảng và index để optimizer ước lượng cardinality, số hàng và chi phí truy cập. Thống kê index có thể dựa trên sampling một số page, vì vậy giá trị cardinality trong `SHOW INDEX` là ước lượng chứ không phải số đếm chính xác.

Kiểm tra index:

```sql
SHOW INDEX FROM shop.orders;
```

Chú ý các trường:

- `Key_name`: tên index.
- `Seq_in_index`: thứ tự cột trong index ghép.
- `Column_name`: cột được index.
- `Non_unique`: index có cho phép trùng hay không.
- `Cardinality`: ước lượng số giá trị khác nhau.
- `Visible`: index có được optimizer cân nhắc hay không, trên phiên bản hỗ trợ invisible index.

### 5.1. Persistent statistics

InnoDB persistent statistics lưu thống kê qua lần restart server. Trên các phiên bản MySQL hiện đại, persistent stats thường được bật mặc định. Kiểm tra:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

`innodb_stats_auto_recalc` điều khiển việc tự động tính lại persistent stats khi dữ liệu thay đổi đủ lớn theo ngưỡng nội bộ/cấu hình. Với thiết lập mặc định phổ biến, thay đổi khoảng 10% số hàng có thể kích hoạt việc tính lại; đây không phải cam kết thời gian tức thời và có thể bị ảnh hưởng bởi cấu hình table/server.

`innodb_stats_persistent_sample_pages` điều khiển số page được lấy mẫu khi tính persistent stats. Tăng sampling có thể cải thiện độ đại diện trong một số bảng phân bố lệch nhưng cũng làm tăng công việc phân tích. Không tăng biến này toàn cục chỉ vì một query chậm; trước tiên xác định index/table nào có thống kê sai lệch.

Có thể xem thống kê persistent ở các bảng hệ thống nếu có quyền:

```sql
SELECT *
FROM mysql.innodb_table_stats
WHERE database_name = 'shop'
  AND table_name = 'orders';

SELECT
    index_name,
    stat_name,
    stat_value,
    sample_size,
    last_update
FROM mysql.innodb_index_stats
WHERE database_name = 'shop'
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
```

Đây là dữ liệu phục vụ chẩn đoán. Không sửa trực tiếp các bảng thống kê hệ thống để ép optimizer chọn plan. Dùng `ANALYZE TABLE` và các cơ chế được hỗ trợ để cập nhật.

### 5.2. Cập nhật index statistics

Sau khi nạp lượng dữ liệu lớn, xóa nhiều hàng hoặc thay đổi đáng kể phân bố dữ liệu, có thể chạy:

```sql
ANALYZE TABLE shop.orders;
```

Lệnh này yêu cầu MySQL cập nhật thống kê bảng/index. Sau đó chạy lại `EXPLAIN` và đo hiệu năng để xem ước lượng có tốt hơn không.

`ANALYZE TABLE` không phải thao tác vô hại trong mọi môi trường. Nó có thể tiêu tốn I/O/CPU và cần khóa metadata hoặc gây ảnh hưởng ngắn tùy phiên bản, engine và trạng thái bảng. Chạy có kiểm soát, theo dõi workload và tránh cập nhật stats hàng loạt trong giờ cao điểm khi chưa đánh giá.

## 6. Data skew: khi phân bố dữ liệu không đồng đều

Data skew xảy ra khi một số giá trị xuất hiện nhiều hơn hẳn các giá trị khác. Ví dụ bảng `orders` có 50 triệu hàng, trong đó:

| `order_status` | Tỷ lệ minh họa |
|---|---:|
| `PAID` | 78% |
| `CREATED` | 12% |
| `CANCELLED` | 8% |
| `REFUNDED` | 2% |

Index đơn trên `order_status` có thể rất hữu ích khi truy vấn `REFUNDED`, nhưng ít hữu ích cho truy vấn `PAID` vì phần lớn bảng có giá trị này. Nếu optimizer chỉ có thống kê cardinality đơn giản hoặc sampling không đại diện, nó có thể ước lượng selectivity sai.

Kiểm tra phân bố trong môi trường có thể chịu tải:

```sql
SELECT
    order_status,
    COUNT(*) AS row_count,
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (),
        2
    ) AS percentage
FROM shop.orders
GROUP BY order_status
ORDER BY row_count DESC;
```

Với bảng rất lớn, `COUNT(*)` có thể tốn thời gian và I/O. Dùng replica, sampling hoặc thống kê đã tổng hợp nếu cần; ghi rõ đó là số liệu ước lượng.

### 6.1. Cùng một query shape nhưng giá trị khác nhau

Truy vấn:

```sql
SELECT order_id, created_at
FROM shop.orders
WHERE order_status = ?
ORDER BY created_at DESC
LIMIT 50;
```

Giá trị `REFUNDED` có thể rất chọn lọc, trong khi `PAID` khớp phần lớn bảng. Một index hữu ích cho giá trị hiếm có thể không tối ưu cho giá trị phổ biến. Kiểm thử bằng một giá trị duy nhất sẽ không đại diện cho toàn bộ workload.

Khi điều tra, chọn các giá trị đại diện:

- Giá trị phổ biến nhất.
- Giá trị hiếm nhất.
- Giá trị có phân bố trung bình.
- Giá trị thuộc tenant lớn nhất hoặc nhóm dữ liệu có tải cao nhất.

Không ghi literal nhạy cảm vào log. Có thể ghi nhóm phân bố hoặc lớp selectivity thay cho dữ liệu thực.

## 7. Histogram giúp optimizer hiểu phân bố cột

Histogram mô tả phân bố giá trị của một cột để optimizer ước lượng selectivity tốt hơn, đặc biệt khi dữ liệu lệch mà thống kê index thông thường không đủ thông tin. MySQL hỗ trợ histogram cho các cột được chọn và lưu metadata trong data dictionary.

Tạo histogram:

```sql
ANALYZE TABLE shop.orders
    UPDATE HISTOGRAM ON order_status
    WITH 16 BUCKETS;
```

Số bucket tối đa được hỗ trợ là 1024. Nhiều bucket hơn có thể mô tả phân bố chi tiết hơn nhưng không tự động làm plan tốt hơn. Chọn số bucket dựa trên số giá trị khác nhau, mức skew và kết quả kiểm thử.

Xem histogram:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = 'shop'
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME = 'order_status';
```

Xóa histogram:

```sql
ANALYZE TABLE shop.orders
    DROP HISTOGRAM ON order_status;
```

Histogram được quản lý riêng bằng các thao tác `UPDATE HISTOGRAM` và `DROP HISTOGRAM`. Không giả định việc cập nhật index statistics thông thường sẽ tự làm mới mọi histogram. Sau khi dữ liệu thay đổi mạnh, hãy đánh giá histogram có còn đại diện không và cập nhật khi cần.

### 7.1. Giới hạn của histogram

- Histogram mô tả phân bố từng cột; nó không thể hiện đầy đủ mối tương quan giữa nhiều cột.
- Histogram không thay thế index. Nó giúp optimizer ước lượng, còn index mới cung cấp đường truy cập vật lý.
- Một histogram cũ có thể làm ước lượng sai nếu phân bố dữ liệu thay đổi.
- Histogram tốt hơn không bảo đảm optimizer luôn chọn plan nhanh nhất; cost model và workload vẫn ảnh hưởng.

Ví dụ, `tenant_id` và `order_status` có thể tương quan mạnh: tenant A có 95% đơn `PAID`, tenant B chỉ có 10%. Histogram riêng từng cột không mô tả đầy đủ phân bố kết hợp của cặp giá trị này. Khi đó cần kiểm tra composite index, query shape và estimated/actual rows.

## 8. Index ghép và độ chọn lọc

Khi truy vấn lọc theo nhiều cột, index ghép có thể giúp optimizer giảm số hàng phải đọc. Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Một index ứng viên có thể là:

```sql
CREATE INDEX idx_orders_customer_status_created
ON shop.orders (customer_id, order_status, created_at);
```

Thứ tự cột cần dựa trên workload và điều kiện lọc. Quy tắc leftmost prefix có nghĩa index `(customer_id, order_status, created_at)` có thể hỗ trợ điều kiện bắt đầu từ `customer_id`, nhưng không hiệu quả tương đương khi chỉ lọc theo `order_status` mà bỏ cột đầu tiên.

Đánh giá:

- Cột equality thường được đặt trước cột range hoặc sort trong nhiều mẫu truy vấn, nhưng cần kiểm tra plan thực tế.
- Cardinality cao thường giúp lọc tốt hơn, song không phải tiêu chí duy nhất.
- Index thêm vào làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE.
- Nếu truy vấn cần nhiều cột không có trong index, InnoDB có thể phải truy cập clustered index để lấy row.
- Index có thể giúp ORDER BY và LIMIT tránh sort lớn nếu thứ tự cột phù hợp.

Không tạo index chỉ vì một cột xuất hiện trong WHERE. Xem xét tần suất truy vấn, selectivity, write workload và các index hiện có trước khi thay đổi.

## 9. Phân biệt sai lệch thống kê với vấn đề SQL hoặc index

Không phải mọi plan xấu đều do thống kê. Hãy kiểm tra các khả năng sau:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Estimated rows rất khác actual rows | Stats cũ, sampling không đại diện, histogram thiếu hoặc data skew | `EXPLAIN ANALYZE`, `SHOW INDEX`, histogram và InnoDB stats |
| Optimizer không dùng index dù index tồn tại | Predicate không sargable, implicit cast, collation mismatch, selectivity thấp | Xem `key`, `type`, expression trên cột và kiểu tham số |
| Plan tốt nhưng query vẫn chậm | I/O, lock wait, CPU, buffer pool miss hoặc network/result transfer | Processlist, Performance Schema, InnoDB status và metrics hệ thống |
| Một giá trị nhanh, giá trị khác chậm | Data skew hoặc correlation theo tenant/nhóm | Kiểm thử nhiều giá trị đại diện và phân bố thực tế |
| Query bắt đầu chậm sau DDL | Index bị đổi, invisible, drop hoặc schema/plan thay đổi | So sánh `SHOW CREATE TABLE`, `SHOW INDEX` và plan |
| Chậm sau nâng cấp | Optimizer/cost model hoặc mặc định thay đổi | So sánh version, settings và plan trên staging |
| Filesort hoặc temporary table xuất hiện | Index không đáp ứng ORDER BY/GROUP BY hoặc truy vấn cần sort | Kiểm tra lượng hàng, index và output của EXPLAIN |

Các biểu thức như `DATE(created_at) = ...`, `CAST(indexed_col AS ...)` hoặc so sánh khác kiểu dữ liệu có thể làm điều kiện khó dùng index. Thay đổi SQL sang range predicate tương đương có thể hiệu quả hơn:

```sql
-- Có thể khó dùng index trên created_at:
WHERE DATE(created_at) = '2026-11-19'

-- Dạng range thường thân thiện với index hơn:
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
```

Hãy xác nhận kiểu cột và múi giờ để đảm bảo hai điều kiện tương đương về nghiệp vụ.

## 10. Dùng optimizer trace để hiểu quyết định

Khi `EXPLAIN` cho thấy optimizer chọn đường truy cập khó hiểu, có thể bật optimizer trace trong session:

```sql
SET optimizer_trace = 'enabled=on';

EXPLAIN
SELECT order_id, created_at
FROM shop.orders
WHERE customer_id = 42
  AND order_status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE\G

SET optimizer_trace = 'enabled=off';
```

Trace có thể cho biết các access path được xem xét, điều kiện bị loại, cost ước lượng và lý do một index không được chọn. Nội dung khá dài và phụ thuộc phiên bản; chỉ bật trong session điều tra và tắt sau khi lấy dữ liệu cần thiết.

Không sửa cost model hoặc optimizer settings toàn cục dựa trên một trace đơn lẻ. Xác định trước liệu ước lượng sai vì stats, data skew, index hay SQL shape.

## 11. Quy trình xử lý khi plan thay đổi và query chậm

Thực hiện theo thứ tự để giữ lại bằng chứng và tránh tạo thêm biến số:

1. **Xác định query:** lấy digest, schema, latency p95/p99, rows examined/sent và thời điểm bắt đầu chậm.
2. **Khoanh vùng hệ thống:** kiểm tra CPU, I/O, buffer pool, lock wait, connection count và workload cùng thời điểm.
3. **Thu thập SQL:** lấy câu query đại diện và các nhóm giá trị tham số có selectivity khác nhau.
4. **Lưu plan hiện tại:** chạy `EXPLAIN`/`FORMAT=JSON`; dùng `EXPLAIN ANALYZE` có kiểm soát trên truy vấn an toàn.
5. **So sánh plan cũ:** đối chiếu index, join order, access type, estimated rows và actual rows nếu có baseline.
6. **Kiểm tra thay đổi gần đây:** deploy, DDL, bulk load, `ANALYZE TABLE`, upgrade, optimizer variables và thay đổi traffic.
7. **Kiểm tra stats:** xem `SHOW INDEX`, persistent stats, histogram và thời điểm cập nhật.
8. **Xác nhận data skew:** đo phân bố cột và giá trị tham số đại diện.
9. **Chọn biện pháp:** cập nhật stats/histogram, sửa SQL hoặc tạo index có căn cứ.
10. **Đo lại:** chạy cùng truy vấn, cùng nhóm tham số, cùng điều kiện tải và so sánh latency/rows examined.
11. **Triển khai có kiểm soát:** thử staging/canary, theo dõi write overhead và khả năng rollback thay đổi.
12. **Lưu kết quả:** ghi plan, stats, thay đổi và tiêu chí xác nhận đã phục hồi.

## 12. Biện pháp khắc phục theo nguyên nhân

### 12.1. Thống kê index đã lỗi thời

Nếu estimated rows sai lệch và dữ liệu vừa thay đổi đáng kể, cân nhắc:

```sql
ANALYZE TABLE shop.orders;
```

Sau đó chạy lại EXPLAIN và đo thực tế. Không chạy ANALYZE lặp đi lặp lại nếu kết quả không cải thiện; xem sampling, histogram, correlation và query shape.

### 12.2. Histogram không phản ánh data skew

Cập nhật histogram cho cột có phân bố lệch và truy vấn phụ thuộc vào selectivity của cột:

```sql
ANALYZE TABLE shop.orders
    UPDATE HISTOGRAM ON order_status
    WITH 32 BUCKETS;
```

So sánh estimated rows trước/sau và đo cả giá trị phổ biến lẫn hiếm. Nếu histogram làm plan xấu hơn, có thể drop histogram rồi kiểm tra lại:

```sql
ANALYZE TABLE shop.orders
    DROP HISTOGRAM ON order_status;
```

### 12.3. Index chưa phù hợp

Thiết kế index ghép theo predicate, thứ tự sort và selectivity. Trước khi tạo index, kiểm tra index hiện có để tránh trùng lặp hoặc tạo index gần giống chỉ khác thứ tự cột. Đo ảnh hưởng tới write workload và dung lượng.

### 12.4. SQL không sargable

Sửa điều kiện để không áp dụng hàm hoặc cast lên cột index nếu có thể. Dùng range predicate, kiểu tham số khớp kiểu cột và tránh implicit conversion.

### 12.5. Tải hoặc lock mới là nguyên nhân

Nếu plan và estimated/actual rows hợp lý nhưng thời gian vẫn cao, xử lý lock contention, transaction dài, I/O, buffer pool hoặc tải đồng thời. Thay index trong trường hợp này có thể làm write workload nặng hơn mà không giải quyết nguyên nhân.

## 13. Dùng optimizer hint và ép index có kiểm soát

Optimizer hint hoặc `FORCE INDEX` có thể hữu ích như biện pháp tạm thời khi đã chứng minh optimizer chọn plan kém trong một workload cụ thể. Nhưng hint có thể trở nên sai khi dữ liệu hoặc workload thay đổi.

Ví dụ query hint:

```sql
SELECT /*+ INDEX(o idx_orders_customer_status_created) */
       o.order_id, o.created_at, o.total_amount
FROM shop.orders AS o
WHERE o.customer_id = 42
  AND o.order_status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 20;
```

Trước khi dùng hint:

- Chứng minh plan không hint chậm hơn với nhiều nhóm giá trị tham số đại diện.
- Đo trên phiên bản MySQL và dữ liệu gần production.
- Ghi rõ truy vấn, index và lý do hint được thêm.
- Đặt ngày đánh giá lại và điều kiện gỡ hint.
- Theo dõi khi dữ liệu, index hoặc phiên bản server thay đổi.

Không ép index toàn cục hoặc thay optimizer settings chỉ để sửa một query. Nếu hint chỉ giúp một giá trị hiếm nhưng làm giá trị phổ biến chậm hơn, đó không phải giải pháp tổng thể.

## 14. Kiểm tra index bằng invisible index

MySQL 8.0 hỗ trợ invisible index để đánh giá tác động khi optimizer bỏ qua một index mà chưa xóa nó. Đây là công cụ kiểm thử hữu ích trong staging:

```sql
ALTER TABLE shop.orders
    ALTER INDEX idx_orders_status INVISIBLE;
```

Optimizer mặc định không dùng index invisible. Để thử dùng index đó trong session kiểm thử:

```sql
SET SESSION optimizer_switch = 'use_invisible_indexes=on';
```

Khôi phục trạng thái visible:

```sql
ALTER TABLE shop.orders
    ALTER INDEX idx_orders_status VISIBLE;
```

Thay đổi visibility có ảnh hưởng tới optimizer trên toàn bảng, không chỉ session đang thử. Không đổi index production sang invisible khi chưa đánh giá tất cả query phụ thuộc. Dùng staging hoặc cửa sổ thay đổi có kiểm soát, lưu plan trước/sau và có lệnh khôi phục.

## 15. Những điều không nên làm khi truy vấn đột nhiên chậm

- Không chạy `ANALYZE TABLE` trên mọi bảng mà chưa xác định bảng liên quan.
- Không tạo nhiều index thử trên production mà chưa đo write overhead và dung lượng.
- Không dùng `FORCE INDEX` chỉ vì plan hiện tại có `type=ALL`.
- Không tăng `innodb_stats_persistent_sample_pages` toàn cục để chữa một query đơn lẻ.
- Không xóa histogram mà chưa lưu trạng thái trước đó và đo ảnh hưởng.
- Không kết luận `Using filesort` luôn là nguyên nhân chậm.
- Không dùng một giá trị tham số để đại diện cho dữ liệu có skew.
- Không chạy `EXPLAIN ANALYZE` trên query nặng trong giờ cao điểm mà chưa đánh giá tác động.
- Không sửa trực tiếp các bảng `mysql.innodb_*_stats`.
- Không bỏ qua lock wait, I/O và tải hệ thống khi plan không thay đổi.

## 16. Ma trận triệu chứng và chẩn đoán

| Triệu chứng | Khả năng cao | Bằng chứng nên tìm | Bước tiếp theo |
|---|---|---|---|
| Query chậm ngay sau `ANALYZE TABLE` | Stats mới khiến optimizer đổi plan | Plan trước/sau, cardinality, estimated rows | Đánh giá plan mới với nhiều tham số; kiểm tra histogram/index |
| Estimated rows rất thấp nhưng actual rows rất cao | Stats/sampling/histogram không đại diện | `EXPLAIN ANALYZE`, distribution query, index stats | Refresh stats hoặc histogram, sau đó đo lại |
| Một status nhanh, status khác chậm | Data skew | Tỷ lệ từng giá trị, plan theo giá trị | Thiết kế index/query phù hợp workload hoặc chia nhánh truy vấn |
| Plan dùng full table scan sau khi bảng tăng | Index thiếu, selectivity thấp hoặc stats thay đổi | `EXPLAIN`, `SHOW INDEX`, table size | Đánh giá index ghép và cost thực tế |
| Plan giống trước nhưng latency tăng | Lock, I/O, CPU hoặc network | Processlist, wait events, InnoDB metrics | Xử lý contention/tài nguyên thay vì ép index |
| Sau deploy query dùng index khác | SQL shape, schema, stats hoặc optimizer settings thay đổi | Diff SQL, DDL, `optimizer_switch`, plan | Xác định thay đổi gần nhất và rollback/điều chỉnh có kiểm soát |
| Histogram tồn tại nhưng estimate vẫn sai | Tương quan nhiều cột hoặc histogram stale | Histogram JSON, giá trị kết hợp, actual rows | Đánh giá composite index và query design |

## 17. Tình huống thực hành

Một bảng `orders` có 40 triệu hàng. Truy vấn tìm 50 đơn gần nhất theo `order_status` vốn chạy nhanh, nhưng sau khi dữ liệu thanh toán tăng mạnh, truy vấn cho status `PAID` chậm hơn nhiều. Digest cho thấy số hàng examined tăng, và optimizer không còn chọn index cũ.

Thực hiện trong môi trường lab:

1. Ghi lại plan `EXPLAIN FORMAT=JSON` và số liệu digest trước khi nạp thêm dữ liệu.
2. Tạo phân bố ban đầu trong đó `PAID` là giá trị hiếm.
3. Chạy truy vấn với `PAID`, `CREATED` và `REFUNDED`; ghi latency và rows examined.
4. Nạp thêm dữ liệu để `PAID` trở thành giá trị phổ biến, rồi kiểm tra plan thay đổi.
5. Chạy `EXPLAIN ANALYZE` trong lab để so sánh estimated rows với actual rows.
6. Chạy `ANALYZE TABLE` và quan sát cardinality cùng plan sau cập nhật stats.
7. Tạo histogram cho `order_status`, kiểm tra `INFORMATION_SCHEMA.COLUMN_STATISTICS` và đo lại.
8. Thử index ghép `(order_status, created_at)` hoặc `(customer_id, order_status, created_at)` theo query workload thực tế; so sánh read/write cost.
9. Dùng invisible index trong lab để đánh giá tác động khi optimizer bỏ qua index.
10. Thử optimizer hint trên một query cụ thể, kiểm tra nhiều giá trị tham số và ghi rõ điều kiện gỡ hint.
11. So sánh kết quả trước/sau theo p95 latency, rows examined, CPU/I/O và write throughput.
12. Viết runbook nhận diện plan regression và quy trình rollback thay đổi index/histogram.

**Câu hỏi tự đánh giá:**

- Vì sao một truy vấn không đổi SQL vẫn có thể đổi execution plan?
- `Cardinality` trong `SHOW INDEX` có phải số hàng khác nhau chính xác không?
- Persistent stats và histogram khác nhau ở cách quản lý nào?
- Vì sao `ANALYZE TABLE` có thể làm query nhanh hơn hoặc chậm hơn?
- Data skew ảnh hưởng selectivity và lựa chọn index ra sao?
- Histogram đơn cột không mô tả được loại tương quan nào?
- `EXPLAIN ANALYZE` khác `EXPLAIN` thông thường như thế nào và vì sao cần thận trọng?
- Khi nào full table scan có thể là plan hợp lý?
- Vì sao `FORCE INDEX` có thể trở thành vấn đề sau khi dữ liệu thay đổi?
- Làm thế nào phân biệt plan regression với lock hoặc I/O bottleneck?

## Kết luận

Truy vấn chậm đột ngột cần được điều tra bằng số liệu thực thi và execution plan trước khi thay đổi schema. So sánh estimated với actual rows, kiểm tra persistent index stats, data skew và histogram, rồi xác định liệu nguyên nhân nằm ở thống kê, index, SQL hay tài nguyên. Cập nhật stats, tạo index hoặc dùng hint chỉ sau khi đo trên nhiều giá trị dữ liệu đại diện; luôn lưu plan trước/sau và có cách khôi phục thay đổi.

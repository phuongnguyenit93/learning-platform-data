# Đo lợi ích thực tế, chi phí mở bảng và số lượng partition

Partitioning chia một bảng logic thành nhiều partition vật lý theo quy tắc được khai báo. Cách tổ chức này có thể giúp MySQL bỏ qua phần dữ liệu không liên quan (partition pruning), quản lý dữ liệu theo vòng đời và loại bỏ một vùng dữ liệu cũ nhanh hơn việc xóa từng dòng. Tuy nhiên, partitioning cũng làm tăng metadata và công việc quản lý cấu trúc bảng. Nhiều partition có thể làm tăng chi phí mở bảng, lập kế hoạch truy vấn, quản lý file và bảo trì.

Bài học này thuộc phần **Phân vùng** của MySQL. Mục tiêu là đo xem partitioning có cải thiện workload thật hay không, xác định chi phí mở bảng và chọn số lượng partition phù hợp. Bạn sẽ so sánh bảng có và không có partition, đọc kế hoạch pruning, đo latency và I/O, theo dõi metadata, đồng thời đánh giá giới hạn và chi phí vận hành trước khi quyết định triển khai.

## 1. Partitioning đem lại lợi ích trong trường hợp nào?

Partitioning có ích khi cách chia partition khớp với cách ứng dụng truy vấn hoặc quản lý dữ liệu. Các tình huống thường gặp:

- Bảng sự kiện lớn được truy vấn theo khoảng thời gian; partition theo ngày hoặc tháng có thể giúp truy vấn chỉ đọc những khoảng liên quan.
- Dữ liệu có thời hạn lưu trữ; partition cũ có thể được drop hoặc truncate theo chính sách retention thay vì xóa hàng triệu dòng.
- Các tác vụ bảo trì có thể giới hạn vào một partition, ví dụ kiểm tra hoặc nạp dữ liệu theo kỳ.
- Một số workload có thể giảm lượng page cần đọc nếu partition pruning loại bỏ phần lớn partition trước khi truy cập index.

Partitioning thường không giúp nhiều nếu truy vấn không lọc theo partition key, bảng chưa đủ lớn để chi phí quét trở thành vấn đề, hoặc index hiện tại đã đáp ứng tốt. Nó cũng không thay thế index. Mỗi partition vẫn cần index phù hợp với truy vấn.

Ví dụ, partition theo `created_at` có thể phù hợp với báo cáo tháng:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

Truy vấn có thể chỉ đọc partition chứa tháng 3 nếu điều kiện tương thích với biểu thức partition. Nếu ứng dụng thường tìm đơn hàng theo `customer_id` mà không giới hạn `created_at`, MySQL có thể phải xét tất cả partition.

## 2. Partition pruning: lợi ích phải nhìn thấy trong execution plan

**Partition pruning** là quá trình optimizer xác định partition nào có thể chứa dòng phù hợp và loại bỏ các partition còn lại khỏi truy cập của câu lệnh. Đây là cơ chế quan trọng nhất tạo lợi ích truy vấn cho partitioning.

Giả sử bảng được partition theo tháng bằng `RANGE COLUMNS(created_at)`:

```sql
CREATE TABLE orders_by_month (
    order_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY ix_customer_created (customer_id, created_at),
    KEY ix_status_created (status, created_at)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN ('2026-04-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Với bảng partitioned của InnoDB, mọi cột được dùng trong biểu thức partition phải có mặt trong mỗi unique key. Vì vậy ví dụ dùng khóa chính `(order_id, created_at)` thay cho unique key chỉ gồm `order_id`. Đây là ràng buộc thiết kế cần tính trước khi chọn partition key.

Kiểm tra partition được chọn:

```sql
EXPLAIN PARTITIONS
SELECT order_id, customer_id, total_amount
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

Trong kết quả, cột `partitions` cho biết partition mà kế hoạch dự định truy cập. Có thể xem chi tiết hơn bằng:

```sql
EXPLAIN FORMAT = JSON
SELECT order_id, customer_id, total_amount
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

Nếu điều kiện bao phủ nhiều tháng, nhiều partition sẽ được liệt kê. Nếu điều kiện không ràng buộc partition key, thường phải xét tất cả partition có thể chứa dòng phù hợp.

### Viết điều kiện để pruning có thể hoạt động

Ưu tiên điều kiện khoảng nửa mở trên partition key:

```sql
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01'
```

Tránh viết điều kiện bao hàm cột partition trong hàm nếu không cần thiết:

```sql
-- Có thể làm pruning khó nhận diện hơn tùy biểu thức và phiên bản
WHERE DATE(created_at) = '2026-03-15'
```

Điều kiện khoảng vừa tránh lỗi ranh giới thời gian, vừa giữ cột partition ở dạng so sánh trực tiếp. Cũng cần tránh ép kiểu không cần thiết hoặc chuyển đổi kiểu dữ liệu khiến optimizer không xác định được khoảng partition.

Pruning là thuộc tính của từng câu truy vấn. Một bảng được partition không có nghĩa mọi truy vấn trên bảng đều chỉ đọc một partition.

## 3. Partitioning không thay thế index

Mỗi partition của bảng InnoDB có cấu trúc index riêng. Index trên bảng partitioned là các index cục bộ theo partition; MySQL không cung cấp global index dùng chung trên tất cả partition.

Ví dụ:

```sql
SELECT order_id, total_amount
FROM orders_by_month
WHERE customer_id = 1001;
```

Nếu không có điều kiện trên `created_at`, MySQL có thể phải tìm `customer_id = 1001` trong index của nhiều partition. Index `ix_customer_created` vẫn hữu ích trong từng partition, nhưng chi phí phải mở và dò nhiều B-tree có thể lớn hơn truy vấn chỉ cần một partition.

Thử thêm điều kiện thời gian:

```sql
SELECT order_id, total_amount
FROM orders_by_month
WHERE customer_id = 1001
  AND created_at >= '2026-03-01'
  AND created_at <  '2026-04-01';
```

Truy vấn này có thể kết hợp pruning theo thời gian với index `(customer_id, created_at)` trong partition được chọn. Khi thiết kế, cần căn cứ vào các mẫu truy vấn thường xuyên, không chỉ dựa vào cột có thể dùng để chia partition.

Một số ràng buộc InnoDB cần nhớ:

- Mọi unique key, bao gồm primary key, phải chứa tất cả cột của partition expression.
- Bảng InnoDB được partition do người dùng định nghĩa không hỗ trợ foreign key; cũng không thể được tham chiếu bởi foreign key từ bảng khác.
- Partition key và kiểu partition expression phải phù hợp với kiểu dữ liệu và phép so sánh của truy vấn.

Các ràng buộc này có thể ảnh hưởng đến mô hình dữ liệu và tính toàn vẹn tham chiếu. Hãy xác minh khả năng tương thích trước khi partition một bảng đang có nhiều quan hệ khóa ngoại hoặc yêu cầu unique key toàn cục.

## 4. Đo hiệu năng trước và sau partitioning

Không thể kết luận partitioning tốt hơn chỉ từ việc bảng có nhiều partition hoặc file dữ liệu được chia nhỏ. Cần đo trên cùng một workload, cùng dữ liệu và cấu hình tương đương.

Một quy trình benchmark đáng tin cậy gồm:

1. **Chọn workload đại diện.** Lấy các truy vấn quan trọng theo tần suất và chi phí, gồm truy vấn theo partition key, truy vấn không theo partition key, join, báo cáo tổng hợp và ghi dữ liệu.
2. **Tạo hai bản dữ liệu tương đương.** Một bảng không partition và một bảng partition; giữ cùng kiểu cột, dữ liệu, index và thống kê gần tương đương. Nếu ràng buộc unique key khiến thiết kế index phải khác, ghi rõ khác biệt đó trong kết quả.
3. **Làm nóng hoặc kiểm soát cache.** Không so sánh một truy vấn ở trạng thái cold cache với truy vấn còn lại khi toàn bộ page đã nằm trong buffer pool.
4. **Đo nhiều lần.** Ghi p50, p95, p99, throughput và độ biến động; tránh kết luận từ một lần chạy.
5. **Đo tài nguyên.** Theo dõi CPU, I/O, rows examined, page reads, temporary table, lock wait và số partition được truy cập.
6. **Đo chi phí ghi và bảo trì.** Kiểm tra insert, update, bulk load, thêm partition, drop partition và thời gian mở bảng.
7. **Thử ở mức đồng thời gần thực tế.** Một truy vấn đơn lẻ nhanh hơn không có nghĩa hệ thống nhiều session sẽ có throughput cao hơn.

### Tạo bảng đối chứng

Bảng đối chứng không partition nên có cùng cấu trúc cột và các index phù hợp. Để so sánh công bằng, có thể dùng cùng composite primary key:

```sql
CREATE TABLE orders_unpartitioned (
    order_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY ix_customer_created (customer_id, created_at),
    KEY ix_status_created (status, created_at)
) ENGINE = InnoDB;
```

Nạp cùng tập dữ liệu vào hai bảng. Cập nhật thống kê sau khi nạp:

```sql
ANALYZE TABLE orders_unpartitioned, orders_by_month;
```

Không dùng hai tập dữ liệu có phân bố khác nhau để so sánh. Đặc biệt, số dòng mỗi tháng, tỷ lệ trạng thái, số khách hàng và độ lệch dữ liệu có thể làm thay đổi đáng kể lựa chọn access path.

## 5. Đo từng nhóm truy vấn

Một benchmark nên phân nhóm truy vấn theo cách chúng tương tác với partition key.

| Nhóm truy vấn | Ví dụ predicate | Điều cần đo |
| --- | --- | --- |
| Chỉ một partition | `created_at` nằm trong một tháng | Số partition được chọn, rows examined, latency và page reads. |
| Một khoảng nhiều partition | `created_at` bao phủ 6 tháng | Số partition phải mở/đọc, chi phí tổng hợp và latency. |
| Không có partition key | Chỉ lọc `customer_id` | Chi phí dò index qua nhiều partition so với bảng không partition. |
| Quét phần lớn dữ liệu | Không có điều kiện chọn lọc | Chi phí mở/đọc nhiều partition, throughput và I/O. |
| Ghi dữ liệu | Insert theo thời gian hoặc khóa ngẫu nhiên | Throughput, page split, redo, index maintenance và phân bố insert. |
| Join và aggregate | Join theo customer, group theo ngày/tháng | Join order, số dòng thực tế, temporary table và chi phí mở partition. |

Ví dụ truy vấn theo tháng trên cả hai bảng:

```sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01'
  AND status = 'PAID';
```

Chạy truy vấn tương đương trên `orders_unpartitioned`. Dùng `EXPLAIN PARTITIONS` để xác nhận pruning, sau đó dùng `EXPLAIN ANALYZE` để đo số dòng và thời gian thực tế:

```sql
EXPLAIN ANALYZE
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM orders_by_month
WHERE created_at >= '2026-03-01'
  AND created_at <  '2026-04-01'
  AND status = 'PAID';
```

`EXPLAIN ANALYZE` thực thi câu SELECT. Chỉ dùng trên dữ liệu và tải phù hợp; không chạy tùy tiện truy vấn quét lớn trong giờ cao điểm production.

### Đo mức cải thiện

Với mỗi truy vấn, có thể tính phần trăm giảm latency:

\[
\text{Cải thiện latency} =
\frac{T_{trước} - T_{sau}}{T_{trước}} \times 100\%
\]

Nếu thời gian giảm từ 800 ms xuống 500 ms thì cải thiện latency là 37,5%. Nhưng phải so sánh cả throughput và tail latency; partitioning có thể làm một nhóm truy vấn nhanh hơn nhưng làm truy vấn không có partition key chậm hơn.

Đánh giá tổng thể bằng trọng số workload. Ví dụ, nếu truy vấn theo tháng chiếm 70% tải và nhanh hơn đáng kể, còn point lookup không theo partition key chiếm 30% và chậm hơn, cần tính tổng chi phí theo tần suất thực tế thay vì chỉ chọn kết quả đẹp nhất.

## 6. Đo bằng Performance Schema và sys schema

Performance Schema lưu thống kê thực thi câu lệnh theo digest. Có thể xem các truy vấn tốn thời gian hoặc đọc nhiều dòng:

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_CREATED_TMP_TABLES,
    SUM_NO_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các timer trong Performance Schema được biểu diễn theo picosecond ở những trường tương ứng; phép chia trên chuyển `AVG_TIMER_WAIT` sang giây. Kiểm tra Performance Schema có được bật và consumer/instrument cần thiết đã thu thập dữ liệu hay chưa.

Để xem thời gian I/O theo bảng:

```sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    COUNT_READ,
    SUM_TIMER_READ,
    COUNT_WRITE,
    SUM_TIMER_WRITE
FROM performance_schema.table_io_waits_summary_by_table
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME IN ('orders_unpartitioned', 'orders_by_month')
ORDER BY OBJECT_NAME;
```

Đây là số liệu tích lũy từ khi thống kê được khởi tạo hoặc reset. Chụp số liệu trước và sau một khoảng benchmark rồi tính delta; đừng so sánh trực tiếp tổng tích lũy của hai bảng nếu chúng có lịch sử tải khác nhau.

Có thể dùng view `sys.statement_analysis` để xem tổng hợp câu lệnh ở dạng dễ đọc hơn, tùy cấu hình sys schema. Khi đánh giá p95/p99, cần lấy latency theo từng lần chạy hoặc hệ thống giám sát truy vấn; giá trị trung bình trong digest không thay thế phân vị.

## 7. Đo chi phí mở bảng và metadata

Một bảng partitioned vẫn là một đối tượng bảng logic, nhưng server và storage engine phải quản lý định nghĩa partition, metadata, index và tài nguyên liên quan. Khi số partition tăng, chi phí mở/khởi tạo các partition cần thiết, xử lý metadata và lập kế hoạch có thể tăng. Mức tăng phụ thuộc phiên bản MySQL, loại partition, số partition được truy cập và mẫu truy vấn.

Theo dõi các biến cache và giới hạn file:

```sql
SHOW VARIABLES WHERE Variable_name IN (
    'table_open_cache',
    'table_definition_cache',
    'open_files_limit'
);
```

Theo dõi trạng thái mở bảng:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
    'Open_tables',
    'Opened_tables',
    'Opened_table_definitions',
    'Open_table_definitions'
);
```

`Opened_tables` và `Opened_table_definitions` là bộ đếm tích lũy; cần lấy delta theo thời gian và so sánh trong cùng điều kiện tải. `Open_tables` và `Open_table_definitions` cho biết số đối tượng đang mở tại thời điểm xem. Các số liệu này không đo trực tiếp thời gian mở riêng từng partition, nhưng giúp phát hiện áp lực cache và churn.

### Phép thử chi phí mở bảng

Để đo tác động của số partition:

1. Tạo các bảng lab có cùng schema và dữ liệu, nhưng dùng các mức partition count khác nhau, ví dụ 12, 60, 240 và 1.200.
2. Giữ nguyên truy vấn, index, cấu hình MySQL và lượng dữ liệu tổng.
3. Chạy truy vấn cần mở một partition, truy vấn mở nhiều partition và truy vấn không thể pruning.
4. Đo thời gian lần chạy đầu sau khi đóng/mở kết nối phù hợp, sau đó đo các lần lặp khi cache đã nóng.
5. Ghi latency, số partition trong EXPLAIN, số lần mở bảng tích lũy, file descriptor và memory nếu có thể quan sát.
6. Lặp lại ở mức đồng thời đại diện và kiểm tra p95/p99.

Không thể dùng một con số `Opened_tables` duy nhất để khẳng định partitioning làm mở bảng chậm hơn. Cần kết hợp số liệu cache, thời gian thực tế và kế hoạch thực thi. Đồng thời, việc tăng `table_open_cache` chỉ có ích nếu cache là nút thắt; nó không loại bỏ chi phí metadata của một thiết kế có quá nhiều partition.

## 8. Số lượng partition và chi phí tăng theo quy mô

Không có số lượng partition tối ưu cho mọi hệ thống. Số partition nên xuất phát từ:

- Độ lớn tổng dữ liệu và tốc độ tăng trưởng.
- Khoảng thời gian truy vấn thường đọc.
- Độ hạt retention: cần xóa dữ liệu theo ngày, tuần, tháng hay quý.
- Số partition mỗi truy vấn thường phải truy cập.
- Chi phí mở bảng, lập kế hoạch, metadata, file và bảo trì.
- Giới hạn của phiên bản MySQL và storage engine.

MySQL 8.0 hỗ trợ tối đa **8.192 partition cho một bảng**, tính cả subpartition. Đây là giới hạn kỹ thuật, không phải khuyến nghị nên tiến gần đến giới hạn. Partition count thấp hơn nhiều vẫn có thể gây overhead nếu mỗi truy vấn phải xét hầu hết partition.

Ví dụ với dữ liệu lưu 10 năm:

| Độ hạt | Số partition xấp xỉ | Nhận xét |
| --- | ---: | --- |
| Theo năm | 10 | Ít metadata, nhưng thao tác retention và pruning theo khoảng nhỏ có thể thô. |
| Theo quý | 40 | Cân bằng cho workload truy vấn và lưu trữ theo quý. |
| Theo tháng | 120 | Thường phù hợp với báo cáo tháng và retention theo tháng. |
| Theo ngày | 3.650 | Pruning chi tiết, nhưng số partition và chi phí vận hành tăng đáng kể. |

Ví dụ chỉ để minh họa độ hạt; lựa chọn thật phải dựa vào query mix và chính sách lưu trữ. Nếu truy vấn chủ yếu đọc 30 ngày gần nhất, partition tháng có thể chỉ mở 1–2 partition. Nếu cần xóa dữ liệu theo ngày với yêu cầu chính xác, partition ngày có thể hợp lý dù overhead cao hơn.

### Quá nhiều partition có thể gây ra điều gì?

- Metadata partition lớn hơn và thêm công việc khi mở bảng, kiểm tra partition hoặc lập kế hoạch.
- Nhiều cấu trúc index cục bộ cần được duy trì và thống kê.
- Nhiều file hoặc tablespace hơn trong các cấu hình lưu trữ tương ứng, làm tăng yêu cầu filesystem và file descriptor.
- DDL quản lý partition phức tạp hơn; thao tác thêm, bỏ hoặc tổ chức lại partition có thể tốn thời gian.
- Truy vấn không prune được có thể phải truy cập rất nhiều partition, làm giảm lợi ích của việc chia nhỏ.
- Các công cụ backup, restore, schema migration và giám sát cần xử lý cấu trúc partition lớn hơn.

Số partition lớn không tự động đồng nghĩa hiệu năng kém. Nếu workload luôn prune xuống một partition và chi phí quản lý vẫn nhỏ, cấu hình có thể hoạt động tốt. Cần đo thực tế thay vì chỉ dựa vào ngưỡng số lượng.

## 9. Xem kích thước và phân bố dữ liệu theo partition

`INFORMATION_SCHEMA.PARTITIONS` cung cấp metadata về từng partition:

```sql
SELECT
    PARTITION_NAME,
    PARTITION_ORDINAL_POSITION,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_month'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Với InnoDB, `TABLE_ROWS` là ước lượng, không phải số dòng chính xác. `DATA_LENGTH`, `INDEX_LENGTH` và `DATA_FREE` là số liệu thống kê dung lượng; không nên dùng chúng như phép đo byte chính xác của dữ liệu nghiệp vụ. Có thể kết hợp với filesystem, Performance Schema và công cụ giám sát để xác định partition nào tăng trưởng bất thường.

Kiểm tra tổng số partition:

```sql
SELECT COUNT(*) AS partition_count
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_month'
  AND PARTITION_NAME IS NOT NULL;
```

Kiểm tra tổng dung lượng ước lượng:

```sql
SELECT
    SUM(DATA_LENGTH) AS data_bytes,
    SUM(INDEX_LENGTH) AS index_bytes,
    SUM(DATA_FREE) AS free_bytes
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_by_month';
```

Số liệu có thể cần cập nhật thống kê bằng `ANALYZE TABLE`. Việc analyze cũng có chi phí và có thể ảnh hưởng kế hoạch; thực hiện theo quy trình vận hành phù hợp.

## 10. Chi phí ghi dữ liệu và quản lý partition

Khi insert, MySQL phải xác định partition đích theo partition expression, sau đó cập nhật index cục bộ của partition đó. Nếu dữ liệu đến theo thời gian và partition key tăng dần, insert có thể tập trung vào partition mới nhất. Nếu ứng dụng ghi dữ liệu cũ hoặc phân tán thời gian, nhiều partition có thể nhận ghi đồng thời.

Partitioning có thể làm tăng chi phí ghi nếu:

- Mỗi câu lệnh phải duy trì nhiều index cục bộ.
- Partition key không phù hợp với thứ tự truy cập, dẫn đến insert/update phân tán.
- Nhiều partition tạo thêm metadata và công việc mở/đóng tài nguyên.
- Query không prune được và phải truy cập nhiều index cục bộ.

Partitioning cũng có thể giảm chi phí retention. Ví dụ, bỏ một partition cũ theo tháng có thể nhanh hơn xóa từng dòng trong khoảng thời gian đó:

```sql
ALTER TABLE orders_by_month
DROP PARTITION p2026_01;
```

Lệnh này xóa toàn bộ dữ liệu trong partition `p2026_01` và không thể rollback như một thao tác DML thông thường. Chỉ chạy sau khi xác nhận retention, backup và partition đích. Không dùng ví dụ này trên bảng thật khi chưa kiểm tra dữ liệu.

Nếu cần giữ partition `pmax` và bổ sung tháng mới, có thể tổ chức lại partition cuối:

```sql
ALTER TABLE orders_by_month
REORGANIZE PARTITION pmax INTO (
    PARTITION p2026_04 VALUES LESS THAN ('2026-05-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Thao tác `REORGANIZE PARTITION` có thể phải di chuyển dữ liệu đang nằm trong partition được tổ chức lại; thời gian và mức khóa phụ thuộc cấu trúc, phiên bản và khối lượng dữ liệu. Hãy thử trên bản sao có quy mô gần production và chuẩn bị dung lượng tạm.

## 11. Xây dựng ma trận quyết định

Trước khi chọn số partition, lập bảng đo cho từng query pattern:

| Chỉ số | Bảng không partition | Partition ít | Partition nhiều |
| --- | --- | --- | --- |
| p50/p95/p99 latency | Đo từ workload thật | Đo cùng workload | Đo cùng workload |
| Rows examined | EXPLAIN ANALYZE / digest | Cùng truy vấn | Cùng truy vấn |
| Partition được truy cập | Không áp dụng | EXPLAIN PARTITIONS | EXPLAIN PARTITIONS |
| Throughput ghi | Đo cùng tốc độ insert | Đo cùng tốc độ insert | Đo cùng tốc độ insert |
| Opened table counters | Delta trong cùng thời gian | Delta trong cùng thời gian | Delta trong cùng thời gian |
| CPU và I/O | Cùng tải | Cùng tải | Cùng tải |
| Chi phí retention | Delete hoặc archive | Drop/truncate partition nếu phù hợp | Drop/truncate partition nếu phù hợp |
| Độ phức tạp vận hành | Số index/schema hiện tại | Số partition và lịch tạo mới | Metadata, file và lịch bảo trì tăng |

Chọn phương án có tổng chi phí thấp hơn cho workload và chính sách dữ liệu. Một phương án có truy vấn báo cáo nhanh hơn 30% nhưng làm p95 point lookup tăng gấp đôi có thể không phù hợp nếu point lookup chiếm phần lớn giao dịch.

## 12. Quy trình triển khai và theo dõi sau triển khai

1. Thu thập query digest, tần suất, latency, rows examined và dung lượng bảng hiện tại.
2. Xác định partition key từ truy vấn và retention, không chỉ từ cột có nhiều dữ liệu.
3. Kiểm tra unique key, foreign key và các giới hạn partitioning của InnoDB.
4. Tạo bản sao thử nghiệm, nạp dữ liệu có phân bố tương tự production và cập nhật thống kê.
5. Chạy benchmark có kiểm soát cache, concurrency, query mix và thời gian đủ dài.
6. Xác nhận pruning bằng EXPLAIN và so sánh actual rows bằng EXPLAIN ANALYZE.
7. Đo chi phí mở bảng, cache, file descriptor, metadata và thao tác retention.
8. Triển khai theo kế hoạch migration có backup, rollback/restore plan và theo dõi sau thay đổi.
9. Đặt lịch tạo partition tương lai, giám sát partition `MAXVALUE` nếu dùng, và cảnh báo khi partition count hoặc dung lượng tăng bất thường.

Định kỳ xem lại query mix. Nếu ứng dụng bắt đầu truy vấn theo cột khác hoặc retention thay đổi, lợi ích của partition key cũ có thể giảm. Partitioning là quyết định vận hành dài hạn, không phải một lần cấu hình rồi bỏ quên.

## 13. Lỗi đánh giá thường gặp

- **Chỉ đo truy vấn có pruning.** Cần đo cả truy vấn không có partition key vì chúng có thể phải xét mọi partition.
- **So sánh hai tập dữ liệu khác nhau.** Phân bố dữ liệu làm thay đổi thống kê, selectivity và execution plan.
- **Chỉ nhìn thời gian trung bình.** p95/p99 và throughput mới thể hiện ảnh hưởng dưới tải đồng thời.
- **Coi số partition càng nhiều càng tốt.** Partition quá nhỏ có thể tăng metadata và chi phí mở bảng mà không đem lại lợi ích tương ứng.
- **Coi partition thay thế index.** Mỗi partition vẫn cần index phù hợp; không pruning được thì nhiều index cục bộ có thể phải được dò.
- **Dùng `DATE(column)` rồi giả định pruning chắc chắn.** Kiểm tra execution plan và ưu tiên điều kiện khoảng trực tiếp.
- **Đọc `TABLE_ROWS` như số chính xác.** Thống kê InnoDB là ước lượng và cần được diễn giải đúng.
- **Chạy DROP PARTITION mà không kiểm tra.** Đây là thao tác xóa dữ liệu; xác nhận đúng partition và backup trước khi chạy.

## 14. Bài tập tự kiểm tra

1. Partitioning giúp giảm lượng dữ liệu cần đọc bằng cơ chế nào?
2. Vì sao truy vấn chỉ lọc `customer_id` có thể phải truy cập mọi partition nếu bảng được partition theo `created_at`?
3. Làm thế nào xác nhận partition pruning bằng `EXPLAIN PARTITIONS`?
4. Vì sao partitioning không thay thế secondary index?
5. Nêu các ràng buộc unique key và foreign key cần kiểm tra trước khi partition một bảng InnoDB.
6. Thiết kế benchmark để so sánh bảng thường với bảng partition theo tháng; cần giữ những yếu tố nào giống nhau?
7. `Opened_tables` và `Opened_table_definitions` giúp quan sát điều gì? Vì sao cần đo delta?
8. So sánh 120 partition tháng với 3.650 partition ngày cho dữ liệu 10 năm.
9. Vì sao `TABLE_ROWS` trong `INFORMATION_SCHEMA.PARTITIONS` không phải số dòng chính xác?
10. Khi nào `DROP PARTITION` có lợi hơn `DELETE`, và rủi ro dữ liệu là gì?

Quyết định partitioning nên dựa trên chuỗi **query mix → partition pruning → rows và page thực tế được đọc → latency/throughput → chi phí mở bảng và metadata → chi phí ghi, retention và bảo trì**. Chỉ khi lợi ích tổng thể đo được lớn hơn chi phí vận hành thì số lượng và độ hạt partition mới phù hợp.

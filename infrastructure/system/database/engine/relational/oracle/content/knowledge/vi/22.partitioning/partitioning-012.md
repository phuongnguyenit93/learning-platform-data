# Kiểm chứng lợi ích phân vùng bằng kế hoạch và tải thực tế trong Oracle Database

Partitioning (phân vùng) chia một bảng hoặc index lớn thành các phần nhỏ hơn nhưng vẫn được truy vấn như một đối tượng logic. Phân vùng có thể giúp giảm lượng dữ liệu phải đọc, quản lý dữ liệu theo vòng đời, thực hiện bảo trì từng phần và cải thiện một số kiểu join hoặc tải dữ liệu. Tuy nhiên, **một bảng được partition không tự động làm mọi truy vấn nhanh hơn**. Lợi ích chỉ xuất hiện khi thiết kế partition phù hợp với workload và Oracle có thể khai thác nó.

Muốn chứng minh hiệu quả, cần kết hợp hai loại bằng chứng:

1. **Execution plan:** Oracle có thực hiện partition pruning hay không, đọc những partition nào, dùng local/global index ra sao, và số hàng ước lượng có hợp lý không?
2. **Số liệu thực thi:** truy vấn thực sự đọc bao nhiêu buffer, bao nhiêu block vật lý, dùng CPU và thời gian chờ thế nào, throughput thay đổi ra sao khi có nhiều session?

Chỉ nhìn thấy dòng PARTITION RANGE trong plan chưa đủ để kết luận hệ thống nhanh hơn. Cũng không thể kết luận partitioning vô ích chỉ vì một truy vấn thử với vài hàng không dùng pruning. Bài học này xây dựng quy trình đo có đối chứng, dùng cùng dữ liệu và workload, rồi đánh giá cả lợi ích truy vấn lẫn chi phí ghi, index, thống kê và vận hành.

## 1. Phân vùng giải quyết vấn đề gì?

### 1.1. Một bảng logic, nhiều partition vật lý

Ví dụ bảng giao dịch có dữ liệu nhiều năm. Nếu chia theo tháng, mỗi tháng là một partition:

```text
TRANSACTIONS
  P2026_01  -> dữ liệu tháng 01/2026
  P2026_02  -> dữ liệu tháng 02/2026
  P2026_03  -> dữ liệu tháng 03/2026
  ...
```

Ứng dụng vẫn truy vấn bảng TRANSACTIONS. Oracle quản lý việc ánh xạ hàng vào partition theo partition key. Người dùng không cần viết tên partition trong SQL thông thường.

### 1.2. Partition pruning

Partition pruning là khả năng Oracle loại bỏ những partition không thể chứa hàng thỏa điều kiện. Ví dụ bảng được partition theo ORDER_DATE, truy vấn chỉ cần tháng 02/2026:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';
```

Nếu ranh giới partition khớp theo tháng, Oracle có thể chỉ đọc partition tháng 02 thay vì quét mọi partition. Đây là lợi ích thường dễ quan sát nhất.

### 1.3. Các lợi ích khác

- **Quản lý vòng đời dữ liệu:** DROP/TRUNCATE/EXCHANGE một partition có thể xử lý một khoảng dữ liệu nhanh hơn thao tác hàng loạt thông thường.
- **Bảo trì từng phần:** rebuild hoặc quản lý index theo partition trong các cấu hình phù hợp.
- **Partition-wise join:** giảm dữ liệu trao đổi và có thể tận dụng xử lý song song khi hai bảng partition tương thích.
- **Load dữ liệu:** exchange partition hoặc direct-path load có thể giúp nạp dữ liệu theo batch.
- **Availability/maintenance:** một số thao tác có thể giới hạn phạm vi ảnh hưởng vào partition liên quan.

Những lợi ích này cần được đánh giá theo từng workload. Một hệ thống chủ yếu truy cập theo khóa khách hàng, không có predicate trên partition key, có thể không nhận được pruning cho truy vấn quan trọng nhất.

### 1.4. Phân vùng không thay thế index

Partitioning và indexing giải quyết các vấn đề khác nhau:

| Cơ chế | Mục tiêu chính |
|---|---|
| Partitioning | Giới hạn phạm vi dữ liệu, quản lý dữ liệu theo phần |
| B-tree index | Tìm nhanh hàng theo khóa |
| Bitmap index | Hỗ trợ một số workload phân tích với cardinality thấp |
| Local index | Index được chia theo partition của bảng |
| Global index | Index có phạm vi toàn bảng partitioned |

Một truy vấn có thể prune xuống một partition rồi dùng index bên trong partition đó. Ngược lại, nếu không có pruning, Oracle vẫn có thể phải truy cập nhiều partition hoặc nhiều index partition.

## 2. Xác định giả thuyết trước khi đo

Không bắt đầu benchmark bằng câu hỏi chung chung “partitioning có nhanh hơn không?”. Hãy ghi một giả thuyết có thể kiểm chứng:

- Truy vấn báo cáo theo tháng hiện đọc toàn bộ bảng; partition theo tháng sẽ giảm số partition được truy cập.
- Batch xóa dữ liệu cũ hiện chạy DELETE rất lâu; DROP/TRUNCATE partition có thể giảm undo/redo và thời gian bảo trì.
- Join fact table với dimension lớn; partition-wise join có thể giảm dữ liệu trao đổi giữa các parallel worker.
- Truy vấn theo customer_id không có date filter; partition theo ngày có thể không giúp, thậm chí làm tăng chi phí nếu phải dò nhiều partition.

Mỗi giả thuyết phải gắn với một SQL cụ thể, tập bind values, số hàng kết quả, tần suất, concurrency và chỉ số đo. Đặt tiêu chí thành công trước khi chạy thử để tránh chọn số liệu có lợi sau khi đã xem kết quả.

### 2.1. Ghi lại workload

Tạo danh sách truy vấn đại diện:

| Nhóm | Ví dụ predicate | Tỷ trọng/tần suất | Mục tiêu |
|---|---|---:|---|
| Theo ngày/tháng | ORDER_DATE trong một khoảng | Cao | Pruning |
| Theo khóa nghiệp vụ | CUSTOMER_ID = :id | Cao | Kiểm tra truy cập không có partition key |
| Theo ngày và khóa | ORDER_DATE range + CUSTOMER_ID | Cao | Pruning kết hợp index |
| Báo cáo tổng hợp | GROUP BY tháng/khu vực | Trung bình | Scan, aggregate, parallel |
| Nạp batch | INSERT theo tháng | Theo lịch | DML throughput |
| Xóa dữ liệu cũ | Xóa theo retention period | Theo lịch | Partition maintenance |
| Join fact/dimension | Join theo dimension key | Trung bình | Partition-wise join |

Đừng chỉ chọn truy vấn dễ pruning. Nếu workload thật có nhiều truy vấn không lọc theo partition key, chúng phải xuất hiện trong phép đo tổng thể.

### 2.2. Chọn partition key theo workload và vòng đời

Partition key thường được chọn dựa trên:

1. Predicate xuất hiện thường xuyên và có thể giới hạn phạm vi.
2. Quy tắc retention/archive hoặc tải dữ liệu.
3. Kích thước bảng và tốc độ tăng trưởng.
4. Cách các bảng lớn join với nhau.
5. Mức độ phân bố dữ liệu và nguy cơ một partition quá lớn hoặc quá nóng.

Partition key không nên chỉ được chọn vì một truy vấn báo cáo hiếm khi chạy. Nếu chọn ORDER_DATE nhưng phần lớn request chỉ có CUSTOMER_ID, cần đo chi phí truy cập nhiều partition cho các request đó.

## 3. Các dạng partitioning và tác động đến kiểm chứng

### 3.1. Range partitioning

Range partitioning phân chia theo khoảng giá trị:

```sql
CREATE TABLE orders_range_lab (
    order_id      NUMBER(12) NOT NULL,
    order_date    DATE NOT NULL,
    customer_id   NUMBER(10) NOT NULL,
    total_amount  NUMBER(14, 2) NOT NULL
)
PARTITION BY RANGE (order_date) (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION p2026_03 VALUES LESS THAN (DATE '2026-04-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
```

Mỗi partition nhận các giá trị nhỏ hơn upper bound tương ứng và lớn hơn hoặc bằng bound trước. Partition đầu tiên ở ví dụ này không có lower bound tường minh; nó nhận mọi giá trị nhỏ hơn 01/02/2026. Trong hệ thống thật, cần xác định rõ dữ liệu lịch sử và partition đầu tiên.

Range phù hợp với ngày, số thứ tự hoặc khóa có thứ tự và vòng đời rõ.

### 3.2. Interval partitioning

Interval partitioning tự tạo partition kế tiếp khi có dữ liệu vượt transition point:

```sql
CREATE TABLE orders_interval_lab (
    order_id     NUMBER(12) NOT NULL,
    order_date   DATE NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL
)
PARTITION BY RANGE (order_date)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH')) (
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01')
);
```

Oracle tự tạo interval partition cho các khoảng sau transition point khi cần. Khi đo, hãy kiểm tra partition thực tế đã được tạo, tên partition, số lượng và phân bố hàng; không giả định interval partition luôn có sẵn trước khi nạp dữ liệu.

### 3.3. List partitioning

List partitioning phân chia theo tập giá trị rời rạc:

```sql
CREATE TABLE orders_by_region_lab (
    order_id NUMBER(12),
    region_code VARCHAR2(10),
    total_amount NUMBER(14, 2)
)
PARTITION BY LIST (region_code) (
    PARTITION p_north VALUES ('NORTH'),
    PARTITION p_south VALUES ('SOUTH'),
    PARTITION p_other VALUES (DEFAULT)
);
```

List phù hợp khi nhóm giá trị có ý nghĩa nghiệp vụ và truy vấn thường lọc theo nhóm đó. Nếu một nhóm chứa gần như toàn bộ dữ liệu, lợi ích phân bố có thể thấp.

### 3.4. Hash partitioning

Hash partitioning phân phối hàng theo hàm băm của partition key:

```sql
CREATE TABLE customer_events_hash_lab (
    event_id NUMBER(12),
    customer_id NUMBER(10) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    event_type VARCHAR2(30)
)
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

Hash giúp phân phối dữ liệu đều hơn trong một số workload và có thể giảm hotspot, nhưng predicate theo một customer_id chỉ xác định partition nếu Oracle có thể tính hash từ điều kiện đó. Hash không tự hỗ trợ truy vấn theo event_time nếu event_time không phải partition key.

### 3.5. Composite partitioning

Composite partitioning kết hợp hai mức, ví dụ range theo tháng và hash theo customer:

```sql
CREATE TABLE orders_composite_lab (
    order_id NUMBER(12),
    order_date DATE NOT NULL,
    customer_id NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2)
)
PARTITION BY RANGE (order_date)
SUBPARTITION BY HASH (customer_id)
SUBPARTITIONS 4 (
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Composite partitioning có thể prune ở cả partition và subpartition nếu predicate cung cấp thông tin phù hợp. Nhưng số segment, index partition và công việc quản lý tăng theo số partition/subpartition. Chỉ chọn khi workload và quy mô chứng minh được lợi ích.

## 4. Partition pruning trong execution plan

### 4.1. PSTART và PSTOP

Trong output của DBMS_XPLAN, các cột PSTART/PSTOP mô tả phạm vi partition được truy cập ở operation partitioned. Giá trị có thể là:

- Số partition cụ thể: phạm vi tĩnh có thể xác định lúc parse.
- KEY hoặc KEY(I): phạm vi được xác định lúc thực thi từ bind/predicate hoặc cơ chế runtime.
- ROWID: partition được xác định từ rowid trong một số access path.
- MIN/MAX hoặc các giá trị đặc biệt khác tùy operation/release.

Không diễn giải KEY là “đã đọc mọi partition”. Hãy xem predicate, operation, actual rows và thông tin partition pruning tương ứng trong plan.

### 4.2. Static pruning

Điều kiện có literal hoặc biểu thức có thể xác định khi parse:

```sql
SELECT order_id, total_amount
FROM orders_range_lab
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';
```

Oracle có thể xác định partition phù hợp ngay khi tối ưu. Plan thường thể hiện phạm vi PSTART/PSTOP cụ thể.

### 4.3. Dynamic pruning

Với bind variable:

```sql
SELECT order_id, total_amount
FROM orders_range_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;
```

Partition được xác định khi execute theo bind value. PSTART/PSTOP có thể hiển thị KEY hoặc ký hiệu runtime. Điều này không có nghĩa pruning không xảy ra; cần kiểm tra thực thi với các bind khác nhau.

Dynamic pruning cũng có thể xuất hiện khi partition key đến từ join hoặc subquery, ví dụ join dimension cung cấp tập partition cần truy cập.

### 4.4. Full partition scan và pruning khác nhau

Một plan có operation PARTITION RANGE ALL thường cho thấy tất cả partition trong phạm vi được duyệt. PARTITION RANGE SINGLE thường cho thấy một partition được chọn. PARTITION RANGE ITERATOR có thể lặp qua một dải partition.

Tên operation và chi tiết có thể thay đổi theo loại partition, release và access path. Đừng chỉ tìm chữ SINGLE/ALL; phải đối chiếu PSTART/PSTOP, predicate và actual row source.

### 4.5. Predicate phải thân thiện với partition key

Predicate range trực tiếp:

```sql
WHERE order_date >= :from_date
  AND order_date <  :to_date
```

thường thuận lợi cho range partition pruning.

Predicate bọc cột bằng hàm:

```sql
WHERE TRUNC(order_date) = :day
```

có thể khiến pruning khó hơn hoặc phụ thuộc transformation/partition expression. Nếu partition key là ORDER_DATE, cách viết range thường rõ và an toàn hơn:

```sql
WHERE order_date >= TRUNC(:day)
  AND order_date <  TRUNC(:day) + 1
```

Ở đây hàm áp dụng lên bind, không áp dụng lên partition key. Nếu cột là TIMESTAMP/TIMESTAMP WITH TIME ZONE, dùng kiểu bind và ranh giới thời gian tương ứng, tránh chuyển đổi ngầm.

### 4.6. Implicit conversion có thể cản pruning

Nếu ORDER_DATE là DATE nhưng ứng dụng gửi chuỗi, Oracle có thể chuyển kiểu dựa vào NLS_DATE_FORMAT. Điều đó làm semantics phụ thuộc session và có thể khiến predicate không tối ưu.

Hãy bind DATE/TIMESTAMP đúng kiểu:

```sql
WHERE order_date >= :date_from
  AND order_date <  :date_to
```

Không tạo điều kiện bằng cách nối chuỗi ngày vào SQL. Ngoài rủi ro injection, việc chuyển đổi implicit có thể làm plan và pruning khác giữa session.

## 5. Xem plan bằng DBMS_XPLAN

### 5.1. EXPLAIN PLAN

Ví dụ:

```sql
EXPLAIN PLAN FOR
SELECT order_id, total_amount
FROM orders_range_lab
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY(
    NULL,
    NULL,
    'BASIC +PARTITION +PREDICATE +COST +ROWS'
));
```

Các thành phần cần xem:

- Operation và object được truy cập.
- PSTART/PSTOP.
- Access predicates và filter predicates.
- Estimated rows và cost.
- Index access hay full scan.
- Join method và join order nếu truy vấn nhiều bảng.

EXPLAIN PLAN cho plan ước lượng và có thể không phản ánh bind values/runtime behavior thực tế.

### 5.2. Actual plan của cursor

Chạy câu lệnh với thống kê row source:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, total_amount
FROM orders_range_lab
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-03-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE +PEEKED_BINDS'
    )
);
```

ALLSTATS LAST hiển thị số liệu thực tế của lần thực thi gần nhất khi statistics được thu thập. So sánh E-Rows (ước lượng) với A-Rows (thực tế), Starts, Buffers và Reads. PEEKED_BINDS có thể hiển thị bind được peek lúc hard parse nếu thông tin có sẵn; nó không nhất thiết là toàn bộ bind của mọi lần execute.

### 5.3. Xác định đúng cursor

Trong session có nhiều SQL, DISPLAY_CURSOR(NULL, NULL, ...) thường xem cursor gần nhất phù hợp với context. Khi benchmark, ghi SQL_ID và child number để tránh xem nhầm:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       buffer_gets,
       disk_reads,
       rows_processed,
       elapsed_time
FROM v$sql
WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%'
ORDER BY last_active_time DESC;
```

Truy cập V$SQL cần quyền phù hợp. Tránh dùng LIKE quá rộng trên hệ thống nhiều SQL; trong môi trường đo, có thể dùng module/action hoặc SQL_ID đã ghi lại.

### 5.4. Đọc PSTART/PSTOP cùng operation

Ví dụ diễn giải:

| Plan evidence | Cách đọc |
|---|---|
| PARTITION RANGE SINGLE, PSTART=2, PSTOP=2 | Truy cập một partition cụ thể |
| PARTITION RANGE ITERATOR, PSTART=2, PSTOP=4 | Duyệt một dải partition |
| PARTITION RANGE ALL, PSTART=1, PSTOP=12 | Duyệt tất cả 12 partition trong phạm vi |
| PSTART/PSTOP = KEY | Phạm vi partition được xác định khi chạy |

Đây là ví dụ minh họa; số partition và tên operation thực tế phụ thuộc DDL/plan. Cần xem object name và partition metadata để xác định chính xác partition nào.

## 6. Kiểm tra partition metadata và phân bố dữ liệu

### 6.1. Liệt kê partition

```sql
SELECT partition_name,
       partition_position,
       high_value,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_partitions
WHERE table_name = 'ORDERS_RANGE_LAB'
ORDER BY partition_position;
```

HIGH_VALUE thường được lưu dưới dạng biểu thức metadata; không nên parse chuỗi này trong ứng dụng như một giao diện ổn định. NUM_ROWS/BLOCKS là thống kê tại thời điểm gather.

### 6.2. Đếm hàng theo partition

Có thể dùng extended table name trong truy vấn lab:

```sql
SELECT COUNT(*) FROM orders_range_lab PARTITION (p2026_01);
SELECT COUNT(*) FROM orders_range_lab PARTITION (p2026_02);
SELECT COUNT(*) FROM orders_range_lab PARTITION (p2026_03);
```

Hoặc dùng metadata statistics để xem ước lượng. Đếm chính xác toàn bộ từng partition có thể gây I/O đáng kể; chỉ làm trên môi trường thử hoặc trong cửa sổ đo phù hợp.

### 6.3. Kiểm tra partition/subpartition

Với composite partitioning, xem:

```sql
SELECT partition_name,
       subpartition_name,
       subpartition_position,
       num_rows,
       blocks,
       last_analyzed
FROM user_tab_subpartitions
WHERE table_name = 'ORDERS_COMPOSITE_LAB'
ORDER BY partition_position, subpartition_position;
```

Số hàng phân bố lệch có thể làm một partition trở thành hotspot hoặc làm workload không cân bằng. Partitioning không tự cân bằng khi range key có phân bố lệch; cần chọn key/granularity phù hợp.

### 6.4. Kiểm tra index partition

```sql
SELECT index_name,
       partition_name,
       status,
       num_rows,
       leaf_blocks,
       last_analyzed
FROM user_ind_partitions
WHERE index_name = 'IX_ORDERS_RANGE_LAB_LOCAL'
ORDER BY partition_position;
```

Đối chiếu trạng thái từng index partition sau load, exchange, split, merge hoặc maintenance. Index partition UNUSABLE có thể ảnh hưởng truy vấn hoặc thao tác DML theo cách khác nhau tùy index và cấu hình.

## 7. Thiết kế benchmark có đối chứng

### 7.1. Hai cấu trúc so sánh

Để đo lợi ích partitioning, chuẩn bị hai bảng có cùng dữ liệu logic:

- Bảng A: heap table không partition.
- Bảng B: partitioned table theo partition key dự kiến.

Giữ giống nhau ở mức có thể:

- Cùng cột, datatype, nullability và constraint.
- Cùng dữ liệu, số hàng và phân bố.
- Index tương đương về key và tính chất.
- Statistics được thu thập theo cách phù hợp.
- Cùng SQL, bind values và session settings.

Nếu bảng A có index còn bảng B không có index (hoặc ngược lại), benchmark không còn đo riêng tác động partitioning.

### 7.2. Dữ liệu phải đại diện

Không dùng 10 hàng để kết luận về bảng 500 triệu hàng. Dữ liệu thử cần đại diện:

- Số hàng mỗi partition.
- Độ lệch phân bố theo thời gian/khách hàng/khu vực.
- Tỷ lệ NULL và giá trị phổ biến/hiếm.
- Kích thước hàng và LOB nếu có.
- Mật độ index và clustering.
- Tỷ lệ dữ liệu nóng/lạnh.

Nếu workload có dữ liệu skew, tạo bind values cho cả trường hợp phổ biến và hiếm.

### 7.3. Cùng SQL và cùng bind

SQL so sánh nên giống nhau về logic:

```sql
SELECT COUNT(*), SUM(total_amount)
FROM orders_heap_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;
```

và:

```sql
SELECT COUNT(*), SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;
```

Chỉ khác tên bảng. Dùng cùng datatype của bind, cùng thời gian range, cùng session settings và cùng kết quả kỳ vọng.

### 7.4. Đo nhiều kiểu truy vấn

Ít nhất nên có:

1. Một partition (một ngày/tháng).
2. Nhiều partition liên tiếp.
3. Toàn bộ lịch sử.
4. Truy vấn chỉ theo non-partition key.
5. Truy vấn kết hợp partition key và index key.
6. Join với bảng dimension.
7. Aggregate/report.
8. INSERT batch và DELETE/retention operation.

Partitioning có thể cải thiện nhóm 1–3 nhưng không cải thiện nhóm 4. Cần tổng hợp theo tỷ trọng thực tế để tính lợi ích workload tổng thể.

### 7.5. Kiểm soát cache và thứ tự chạy

Cache ảnh hưởng lớn tới benchmark:

- Lần chạy đầu có thể đọc physical I/O; lần sau dữ liệu đã nằm trong buffer cache.
- Chạy A luôn trước B có thể khiến B hưởng lợi cache.
- Không dùng lệnh flush buffer cache/shared pool trên production để làm benchmark “công bằng”.
- Trong lab riêng, có thể dùng thứ tự A/B xen kẽ, nhiều vòng lặp và báo cả cold/warm run nếu có thể kiểm soát.
- Ghi rõ điều kiện cache và không trộn số liệu cold run với warm run.

### 7.6. Lặp lại và thống kê phân phối

Một lần chạy không đủ. Chạy nhiều lần và báo:

- Median.
- p95/p99 nếu đo latency nhiều request.
- Min/max để nhận biết outlier.
- Số lần execute và số request hoàn tất.
- Throughput (requests/second hoặc rows/second).

Không chỉ lấy lần nhanh nhất. Outlier do I/O, checkpoint, concurrent load hoặc background task cần được ghi nhận.

## 8. Chỉ số cần đo

### 8.1. Thời gian và throughput

| Chỉ số | Ý nghĩa |
|---|---|
| Elapsed time | Thời gian từ lúc gửi đến lúc hoàn tất |
| CPU time | Thời gian CPU dùng cho SQL |
| Throughput | Số request hoặc hàng xử lý mỗi giây |
| p95/p99 latency | Độ trễ ở phần đuôi của phân bố |
| Rows processed | Số hàng thực tế được trả/chèn/cập nhật |

Elapsed time thấp trong một session không bảo đảm throughput tốt khi nhiều session chạy đồng thời.

### 8.2. Logical reads và physical reads

- **Buffer gets/logical reads:** số lần truy cập block trong buffer cache; hữu ích để đo công việc logic.
- **Physical reads:** block phải đọc từ storage; phụ thuộc cache và I/O.
- **Disk reads trong V$SQL:** số liệu theo cursor, cần hiểu đơn vị/cách tổng hợp theo release và child cursor.

Partition pruning thường giảm số partition được truy cập; nếu dữ liệu nằm rải trong ít block hoặc index tốt, chênh lệch physical reads có thể không lớn. Hãy xem cả buffer gets, reads và elapsed time.

### 8.3. Wait events và concurrency

Khi nhiều session, quan sát thời gian chờ:

- User I/O.
- Concurrency/buffer busy.
- Enqueue/lock.
- Log file sync và redo-related waits.
- Parallel execution waits.
- CPU saturation.

Partitioning có thể giảm một số tranh chấp hoặc tạo thêm segment/index maintenance; kết quả phụ thuộc kiểu partition và DML pattern.

### 8.4. DML và chi phí bảo trì

Đo thêm:

- INSERT rows/second.
- UPDATE/DELETE elapsed time.
- Redo và undo volume.
- Index maintenance cost.
- Partition exchange/split/drop duration.
- Statistics gather/refresh duration.
- Storage của table, local index và global index.

Không công bố “query nhanh hơn 10 lần” nếu không tính chi phí load, index, refresh, retention và concurrency của workload tổng thể.

## 9. Thu thập số liệu thực thi

### 9.1. DBMS_XPLAN.DISPLAY_CURSOR

Ví dụ:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*),
       SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= :from_date
  AND order_date <  :to_date;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
```

Đọc E-Rows và A-Rows, Starts, Buffers, Reads. Nếu truy vấn có nhiều operation, xem operation nào tiêu tốn buffer/time lớn nhất thay vì chỉ nhìn root operation.

### 9.2. SQL trace và TKPROF

SQL Trace có thể thu thập parse/execute/fetch, CPU, elapsed, logical/physical reads và wait information theo cách phù hợp với cấu hình. TKPROF định dạng trace thành báo cáo dễ đọc.

Trong session lab:

```sql
ALTER SESSION SET sql_trace = TRUE;

-- Chạy workload cần đo tại đây.

ALTER SESSION SET sql_trace = FALSE;
```

DBA cần xác định trace file và chạy TKPROF trên host database hoặc môi trường quản trị. Không bật trace toàn hệ thống hoặc trace dữ liệu nhạy cảm trên production nếu chưa có kế hoạch và quyền phù hợp.

### 9.3. SQL Monitor

SQL Monitoring hữu ích với SQL chạy lâu, parallel query hoặc workload cần quan sát theo operation. Có thể xem qua công cụ quản trị hoặc package report tương ứng. Việc dùng Real-Time SQL Monitoring và một số tính năng liên quan chịu điều kiện license Oracle Tuning Pack/Diagnostics Pack theo hợp đồng và phiên bản. Xác nhận quyền sử dụng trước khi bật trong production.

### 9.4. V$SQL và module/action

Gắn tên module/action để lọc số liệu:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'PARTITION_BENCH',
        action_name => 'RANGE_MONTH_QUERY'
    );
END;
/
```

Sau đó DBA có thể đối chiếu V$SQL/V$SESSION theo module/action. Kết thúc workload có thể reset:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
```

Module/action giúp phân biệt truy vấn benchmark với SQL khác. Không dùng cùng một tag cho nhiều bài thử không liên quan nếu cần tách kết quả.

## 10. Thống kê optimizer cho partitioned table

### 10.1. Table, partition và global statistics

Optimizer cần statistics ở mức bảng và partition. Với partitioned table, thống kê partition mô tả từng phần; global statistics mô tả toàn bảng. Nếu global stats thiếu hoặc không đại diện, optimizer có thể ước lượng sai cho truy vấn chạm nhiều partition.

Thu thập:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS_RANGE_LAB',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        cascade          => TRUE
    );
END;
/
```

GRANULARITY AUTO để Oracle chọn cấp độ thống kê phù hợp theo đối tượng/cấu hình. Trong môi trường partitioned table lớn, hãy xem incremental statistics và chính sách gather thay vì quét lại toàn bộ dữ liệu sau mỗi batch.

### 10.2. Xem partition statistics

```sql
SELECT partition_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS_RANGE_LAB'
  AND object_type = 'PARTITION'
ORDER BY partition_name;
```

Xem global/table statistics:

```sql
SELECT table_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS_RANGE_LAB'
  AND object_type = 'TABLE';
```

Tên object_type và các cột có thể thay đổi theo dictionary view/release. Xác nhận trên phiên bản đang chạy.

### 10.3. Incremental statistics

Với bảng partition rất lớn, incremental statistics có thể dùng synopses để duy trì global statistics từ thống kê partition mới thay vì quét lại toàn bộ bảng:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'ORDERS_RANGE_LAB',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

Tính năng và điều kiện sử dụng phụ thuộc phiên bản, loại partition và kiểu thống kê. Cần kiểm tra preference, synopses và lịch gather; bật incremental không có nghĩa mọi lần gather đều không đọc dữ liệu nguồn.

### 10.4. Histogram và partition skew

Nếu tháng 12 có lượng giao dịch gấp nhiều lần tháng 2, hoặc một customer chiếm phần lớn dữ liệu, thống kê toàn bảng có thể không mô tả đúng từng trường hợp. Histogram, partition stats và extended stats có thể cải thiện ước lượng trong workload phù hợp.

Không tạo histogram cho mọi cột partition key một cách tự động. Xem bind sensitivity, NDV, phân bố và actual rows trước khi thay method_opt.

### 10.5. Statistics sau partition maintenance

ADD/SPLIT/MERGE/EXCHANGE/TRUNCATE/DROP partition có thể làm metadata và thống kê thay đổi. Sau maintenance, kiểm tra:

- Partition mới đã có statistics chưa.
- Global statistics có còn đại diện không.
- Index partition có usable không.
- Partition exchange có giữ/nhập statistics phù hợp không.
- Query plan có thay đổi do cardinality estimate không.

Lập quy trình gather stats riêng cho partition vừa nạp hoặc thay đổi lớn.

## 11. Local index và global index trong benchmark

### 11.1. Local prefixed index

Local index được chia tương ứng với partition của bảng:

```sql
CREATE INDEX ix_orders_local_date_customer
ON orders_range_lab(order_date, customer_id)
LOCAL;
```

Mỗi index partition chứa khóa thuộc partition bảng tương ứng. Local index phù hợp với truy vấn có partition pruning và giúp một số thao tác partition maintenance dễ quản lý hơn.

### 11.2. Local nonprefixed index

Local index không nhất thiết bắt đầu bằng partition key:

```sql
CREATE INDEX ix_orders_local_customer
ON orders_range_lab(customer_id)
LOCAL;
```

Truy vấn chỉ theo CUSTOMER_ID có thể phải dò index partition ở nhiều partition vì không có predicate trên ORDER_DATE. Đây là tình huống cần đưa vào benchmark; local index không tự biến customer lookup thành một lần truy cập duy nhất trên toàn bảng.

### 11.3. Global index

Global index có phạm vi trên nhiều/all table partitions:

```sql
CREATE INDEX ix_orders_global_customer
ON orders_range_lab(customer_id)
GLOBAL;
```

Global index có thể hỗ trợ tìm CUSTOMER_ID không kèm partition key mà không phải mở từng local index partition. Nhưng thao tác DROP/TRUNCATE/EXCHANGE partition có thể ảnh hưởng global index và cần chiến lược maintenance phù hợp.

### 11.4. So sánh chi phí

| Tiêu chí | Local index | Global index |
|---|---|---|
| Phạm vi | Tương ứng partition/subpartition | Nhiều hoặc toàn bộ partition |
| Truy vấn có pruning | Có thể chỉ truy cập index partition tương ứng | Dùng index toàn cục |
| Truy vấn không có partition key | Có thể phải dò nhiều index partition | Có thể tìm theo khóa toàn cục |
| Partition maintenance | Thường dễ khoanh vùng hơn | Có thể cần cập nhật/rebuild/maintenance global index |
| Quản lý | Nhiều index partition | Một cấu trúc index phạm vi rộng |

Không có lựa chọn đúng cho mọi bảng. Đo cả truy vấn và partition maintenance. Index local/global có thể cùng tồn tại nếu workload yêu cầu.

### 11.5. Kiểm tra index status sau maintenance

Một số DDL partition có thể làm global index bị unusable nếu không dùng tùy chọn phù hợp. Với thao tác hỗ trợ, có thể dùng UPDATE GLOBAL INDEXES hoặc lựa chọn tương ứng:

```sql
ALTER TABLE orders_range_lab
TRUNCATE PARTITION p2026_01
UPDATE GLOBAL INDEXES;
```

Chi tiết cú pháp, thời gian và khả năng online phụ thuộc release/index type. Đo cả thời gian DDL và thời gian khôi phục index; không bỏ qua phần này khi tính TCO.

## 12. Partition-wise join

### 12.1. Full và partial partition-wise join

Partition-wise join có thể chia phép join thành các phần nhỏ theo partition tương ứng. Với full partition-wise join, hai bảng được partition tương thích theo join key và có thể join từng partition pair độc lập. Partial partition-wise join có thể phân chia một phía và repartition phía còn lại trong một số plan.

Lợi ích có thể gồm:

- Giảm dữ liệu trao đổi giữa parallel workers.
- Tăng khả năng xử lý song song.
- Giảm footprint trung gian.

Điều kiện phụ thuộc partitioning scheme, join predicate, partition-wise compatibility và parallel settings.

### 12.2. Ví dụ fact/dimension

Giả sử hai bảng fact lớn cùng partition theo ngày:

```sql
SELECT f.order_date,
       SUM(f.amount)
FROM sales_fact_partitioned f
JOIN returns_fact_partitioned r
  ON r.order_date = f.order_date
 AND r.product_id = f.product_id
GROUP BY f.order_date;
```

Đây chỉ là ví dụ cấu trúc. Để partition-wise join có lợi, hai phía phải có cách partition tương thích với join keys và dữ liệu cần join. Chỉ cùng partition theo ORDER_DATE nhưng join không có điều kiện tương ứng chưa đủ.

### 12.3. Đọc plan

Xem DBMS_XPLAN để nhận diện operation partition-wise join hoặc parallel distribution. Tên operation phụ thuộc plan và release. Kiểm tra:

- PSTART/PSTOP trên từng row source.
- PX SEND/PX RECEIVE và distribution method.
- Số hàng trước/sau join.
- Buffers, reads, CPU và elapsed.
- Skew giữa các worker/partition.

Một plan có parallel execution chưa chắc là partition-wise join. Cần đọc toàn bộ cây plan và predicate.

## 13. Partitioning và DML workload

### 13.1. INSERT

INSERT cần xác định partition đích theo partition key. Với range partition theo ngày, hàng mới được định tuyến vào partition chứa ngày đó. Nếu dữ liệu đến muộn và rơi vào partition cũ, local index và partition stats tương ứng cũng phải được duy trì.

Đo:

- Insert rows/second.
- CPU và redo/undo.
- Index maintenance.
- Partition routing overhead.
- Contention trên partition/index nóng.

### 13.2. UPDATE partition key

Nếu UPDATE làm thay đổi partition key, hàng có thể phải chuyển từ partition này sang partition khác. Oracle có thể cho phép row movement khi bật ENABLE ROW MOVEMENT:

```sql
ALTER TABLE orders_range_lab ENABLE ROW MOVEMENT;
```

Nếu row movement bị tắt, một số update làm hàng đổi partition có thể thất bại. Bật row movement có ảnh hưởng đến ROWID và một số ứng dụng phụ thuộc ROWID; kiểm tra trước khi thay đổi.

### 13.3. DELETE theo retention

Xóa từng hàng:

```sql
DELETE FROM orders_range_lab
WHERE order_date < DATE '2025-01-01';
```

Có thể tạo nhiều undo/redo và index maintenance. Nếu toàn bộ partition cũ không còn cần thiết, DROP/TRUNCATE partition thường là cách quản lý vòng đời phù hợp hơn:

```sql
ALTER TABLE orders_range_lab
DROP PARTITION p2024_12
UPDATE GLOBAL INDEXES;
```

DDL partition có semantics transaction khác DML; thường có implicit commit. Không đặt nó giữa transaction nghiệp vụ rồi kỳ vọng rollback như DELETE.

### 13.4. MERGE và batch load

MERGE hoặc INSERT SELECT vào bảng partitioned vẫn cần đánh giá partition key, local/global index và số partition được chạm. Một batch load theo tháng có thể chỉ ảnh hưởng một partition, nhưng nếu dữ liệu trộn nhiều năm thì phải phân phối vào nhiều partition.

### 13.5. Partition exchange

Exchange partition có thể hoán đổi segment của bảng staging với partition đích:

```sql
ALTER TABLE orders_range_lab
EXCHANGE PARTITION p2026_02
WITH TABLE orders_stage_feb
INCLUDING INDEXES
WITHOUT VALIDATION;
```

Ví dụ chỉ minh họa hình thức. Hai phía phải có cấu trúc cột, datatype và index tương thích theo yêu cầu; WITHOUT VALIDATION chỉ dùng khi dữ liệu đã được đảm bảo nằm đúng partition. Nếu giả định sai, dữ liệu có thể nằm ngoài range logic. Xem xét constraints, index, statistics và global index maintenance.

## 14. Những tình huống partitioning không giúp hoặc làm chậm

### 14.1. Không có predicate trên partition key

Truy vấn:

```sql
SELECT *
FROM orders_range_lab
WHERE customer_id = :customer_id;
```

Nếu partition theo ORDER_DATE, Oracle có thể phải truy cập nhiều partition. Local index CUSTOMER_ID có thể được dò ở từng partition; global index có thể phù hợp hơn nhưng có chi phí maintenance khác.

### 14.2. Truy vấn thường đọc phần lớn bảng

Nếu báo cáo cần 80% dữ liệu, pruning chỉ loại một phần nhỏ. Full scan hoặc parallel scan có thể vẫn là plan tốt nhất. Chia bảng thành nhiều partition không làm biến mất chi phí đọc các hàng cần thiết.

### 14.3. Partition quá nhỏ hoặc quá nhiều

Quá nhiều partition/subpartition làm tăng:

- Metadata và dictionary overhead.
- Số đối tượng/index partition cần quản lý.
- Chi phí parse/optimization trong một số truy vấn.
- Công việc statistics và maintenance.
- Số nhánh cần xét nếu query chạm nhiều partition.

Chọn granularity dựa trên kích thước dữ liệu, retention và truy vấn. Không tạo partition theo ngày nếu dữ liệu chỉ vài hàng mỗi ngày mà không có lý do vận hành.

### 14.4. Partition skew

Một partition chứa phần lớn dữ liệu có thể trở thành bottleneck. Hash partitioning có thể giúp phân bố đều theo key, nhưng nếu key không phù hợp hoặc một key nóng, skew vẫn có thể tồn tại.

### 14.5. Index không phù hợp

Partitioning không thay thế thiết kế index. Nếu query lọc theo cột khác, index không phù hợp có thể khiến Oracle scan nhiều block dù đã prune một số partition.

### 14.6. Statistics thiếu hoặc stale

Optimizer có thể ước lượng sai số hàng theo partition, chọn sai join method hoặc parallel degree. Plan xấu không nhất thiết do partitioning; cần kiểm tra statistics và actual rows.

### 14.7. Overhead DML và storage

Mỗi partition có metadata và có thể có local index partition. INSERT/UPDATE phải duy trì các cấu trúc tương ứng. Một workload OLTP ghi nhiều, truy vấn không lọc partition key có thể không thu được lợi ích tương xứng.

## 15. Benchmark concurrency và tải thực tế

### 15.1. Single-session test không đại diện production

Một truy vấn chạy nhanh hơn trong một session chưa chứng minh throughput tăng khi có 100 session. Concurrency làm lộ:

- CPU saturation.
- I/O throughput limit.
- Lock/index contention.
- Buffer cache pressure.
- Parallel execution resource contention.
- Connection pool bottleneck.

Hãy chạy workload với số session đại diện và tỷ lệ SELECT/INSERT/UPDATE/DELETE giống thực tế.

### 15.2. Thiết kế ma trận thử nghiệm

| Thử nghiệm | Sessions | Query mix | Mục tiêu |
|---|---:|---|---|
| A | 1 | SELECT theo tháng | Đo pruning đơn lẻ |
| B | 10 | SELECT theo tháng + customer | Đo cạnh tranh đọc |
| C | 25 | SELECT + INSERT | Đo đọc/ghi đồng thời |
| D | 25 | SELECT + UPDATE/DELETE | Đo DML và index maintenance |
| E | Theo tải đỉnh | Workload production mix | Đo capacity và tail latency |

Các con số chỉ là mẫu. Chọn concurrency theo hệ thống thực tế, giới hạn môi trường thử và không gây tải ngoài dự kiến trên production.

### 15.3. Giữ workload giống nhau

Với mỗi cấu trúc bảng:

- Dùng cùng tập bind values và phân bố tần suất.
- Dùng cùng số session và think time.
- Dùng cùng commit frequency.
- Dùng cùng isolation level và connection pool.
- Dùng cùng dữ liệu và trạng thái cache có kiểm soát.
- Chạy đủ lâu để qua giai đoạn warm-up và quan sát ổn định.

Không chạy A lúc database rảnh và B lúc database đang có batch khác. Ghi nhận background load, checkpoint, backup và job bảo trì.

### 15.4. So sánh latency và throughput

Ví dụ bảng kết quả:

| Metric | Heap baseline | Partitioned | Chênh lệch |
|---|---:|---:|---:|
| SELECT theo tháng p50 |  |  |  |
| SELECT theo tháng p95 |  |  |  |
| SELECT theo customer p95 |  |  |  |
| Requests/second |  |  |  |
| Buffer gets/request |  |  |  |
| Physical reads/request |  |  |  |
| INSERT rows/second |  |  |  |
| Retention operation time |  |  |  |
| Storage table + indexes |  |  |  |

Điền số liệu đo thực tế, không dùng số giả định. Một kết quả tốt cần cho thấy truy vấn mục tiêu cải thiện mà workload tổng thể vẫn đáp ứng SLA.

## 16. Quy trình benchmark từng bước

### Bước 1 — Chốt baseline

Ghi lại:

- DDL hiện tại.
- Số hàng, kích thước bảng, index và partition (nếu có).
- SQL_ID, SQL text và bind distribution.
- Plan, E-Rows/A-Rows, buffers, reads, CPU, elapsed.
- Throughput và latency theo percentile.
- Statistics timestamp.

### Bước 2 — Tạo bảng thử có partition

Tạo bảng mới với cùng cột, constraint và dữ liệu. Không ALTER production chỉ để thử. Dùng CTAS hoặc INSERT SELECT có kiểm soát; sau đó tạo lại constraint, index, grants, triggers và statistics cần thiết vì CTAS không tự sao chép đầy đủ mọi thuộc tính schema.

### Bước 3 — Nạp cùng dữ liệu

Đối chiếu:

```sql
SELECT COUNT(*) FROM orders_heap_lab;
SELECT COUNT(*) FROM orders_range_lab;
```

So sánh checksum/tổng hợp theo các khóa nghiệp vụ và khoảng ngày. COUNT bằng nhau không chứng minh mọi giá trị giống nhau.

### Bước 4 — Tạo index tương đương

Tạo index heap baseline và local/global index cho partitioned table theo thiết kế workload. Ghi rõ sự khác biệt index là một phần của phương án, không phải yếu tố bị bỏ qua.

### Bước 5 — Gather statistics

Thu thập table/partition/index statistics theo cùng một chính sách và kiểm tra stale stats.

### Bước 6 — Chạy SQL với bind đại diện

Chạy một partition, nhiều partition, full range và không có partition key. Thu thập actual plan bằng DISPLAY_CURSOR.

### Bước 7 — Chạy workload đồng thời

Dùng công cụ load test đã được phê duyệt hoặc harness trong lab. Giữ số session, thời gian và mix giống nhau.

### Bước 8 — Đo DML và maintenance

Đo INSERT/UPDATE/DELETE, partition exchange, drop/truncate, index maintenance và gather stats.

### Bước 9 — Tổng hợp và giải thích

Nêu truy vấn nào cải thiện, truy vấn nào không, vì sao pruning xuất hiện hoặc không xuất hiện, và chi phí nào tăng.

### Bước 10 — Ra quyết định

Chỉ triển khai khi lợi ích workload và vận hành vượt chi phí storage, index, refresh, maintenance, migration và kỹ năng quản trị.

## 17. Ví dụ lab đối chứng

Các ví dụ sau tạo hai bảng đơn giản. Dùng schema lab riêng và điều chỉnh kích thước theo tài nguyên cho phép.

### 17.1. Tạo bảng heap

```sql
CREATE TABLE orders_heap_lab (
    order_id NUMBER(12) NOT NULL,
    order_date DATE NOT NULL,
    customer_id NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL,
    status_code VARCHAR2(20 CHAR) NOT NULL
);
```

### 17.2. Tạo bảng range partitioned

```sql
CREATE TABLE orders_range_lab (
    order_id NUMBER(12) NOT NULL,
    order_date DATE NOT NULL,
    customer_id NUMBER(10) NOT NULL,
    total_amount NUMBER(14, 2) NOT NULL,
    status_code VARCHAR2(20 CHAR) NOT NULL
)
PARTITION BY RANGE (order_date) (
    PARTITION p2025_01 VALUES LESS THAN (DATE '2025-02-01'),
    PARTITION p2025_02 VALUES LESS THAN (DATE '2025-03-01'),
    PARTITION p2025_03 VALUES LESS THAN (DATE '2025-04-01'),
    PARTITION p2025_04 VALUES LESS THAN (DATE '2025-05-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

### 17.3. Nạp dữ liệu giống nhau

Giả sử bảng nguồn ORDERS_SOURCE chứa dữ liệu lab:

```sql
INSERT INTO orders_heap_lab (
    order_id, order_date, customer_id, total_amount, status_code
)
SELECT order_id, order_date, customer_id, total_amount, status_code
FROM orders_source;

INSERT INTO orders_range_lab (
    order_id, order_date, customer_id, total_amount, status_code
)
SELECT order_id, order_date, customer_id, total_amount, status_code
FROM orders_source;

COMMIT;
```

Nếu bảng nguồn lớn, chia batch và ghi nhận cùng điều kiện/commit policy. Đảm bảo mọi order_date thuộc partition hoặc pmax.

### 17.4. Tạo index tương đương

```sql
CREATE INDEX ix_orders_heap_date
ON orders_heap_lab(order_date);

CREATE INDEX ix_orders_range_date_local
ON orders_range_lab(order_date)
LOCAL;

CREATE INDEX ix_orders_range_customer_local
ON orders_range_lab(customer_id)
LOCAL;

CREATE INDEX ix_orders_range_customer_global
ON orders_range_lab(customer_id)
GLOBAL;
```

Không nhất thiết tạo cả local và global customer index trong phương án production; lab có thể dùng để so sánh trade-off. Với heap baseline, tạo index customer tương ứng để phép so sánh công bằng.

### 17.5. Gather statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_HEAP_LAB',
        cascade => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS_RANGE_LAB',
        granularity => 'AUTO',
        cascade => TRUE
    );
END;
/
```

### 17.6. Truy vấn theo một tháng

Heap:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*), SUM(total_amount)
FROM orders_heap_lab
WHERE order_date >= DATE '2025-02-01'
  AND order_date <  DATE '2025-03-01';
```

Partitioned:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*), SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= DATE '2025-02-01'
  AND order_date <  DATE '2025-03-01';
```

Xem DISPLAY_CURSOR cho từng SQL, ghi PSTART/PSTOP, A-Rows, Buffers và Reads. Vì bảng nhỏ hoặc cache nóng, elapsed time có thể gần nhau dù pruning hoạt động đúng.

### 17.7. Truy vấn không có partition key

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*), SUM(total_amount)
FROM orders_range_lab
WHERE customer_id = :customer_id;
```

Chạy với local customer index và global customer index trong các cấu hình riêng. Quan sát số index partition được truy cập và chi phí maintenance của từng lựa chọn.

### 17.8. Truy vấn nhiều tháng

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       status_code,
       COUNT(*),
       SUM(total_amount)
FROM orders_range_lab
WHERE order_date >= DATE '2025-01-01'
  AND order_date <  DATE '2025-05-01'
GROUP BY status_code;
```

Truy vấn này có thể chạm tất cả partition range đã tạo. Partitioning vẫn có thể hỗ trợ parallelism/partition-wise operations, nhưng pruning không loại bỏ được phần dữ liệu cần đọc.

### 17.9. Kiểm tra kết quả giống nhau

```sql
SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS amount_sum,
       MIN(order_date) AS min_date,
       MAX(order_date) AS max_date
FROM orders_heap_lab;

SELECT COUNT(*) AS row_count,
       SUM(total_amount) AS amount_sum,
       MIN(order_date) AS min_date,
       MAX(order_date) AS max_date
FROM orders_range_lab;
```

Đối chiếu thêm theo tháng, trạng thái và khóa nghiệp vụ. Nếu cần xác nhận từng hàng, so sánh hai chiều bằng MINUS trên các cột phù hợp trong lab.

## 18. Đọc kết quả và ra quyết định

### 18.1. Trường hợp partitioning có lợi rõ

Bằng chứng thường gồm:

- Truy vấn có partition predicate chỉ truy cập một/vài partition.
- A-Rows và buffers giảm tương ứng với phạm vi dữ liệu cần đọc.
- p95 latency và CPU giảm ở workload thực.
- Throughput tăng hoặc giữ SLA tốt hơn khi concurrency cao.
- Retention/maintenance operation giảm thời gian đáng kể.
- Chi phí index/statistics/storage tăng nằm trong ngân sách.

### 18.2. Trường hợp chỉ plan thay đổi nhưng hiệu năng không đổi

Có thể pruning xuất hiện nhưng bảng nhỏ, dữ liệu đã cache, truy vấn chỉ trả một vài hàng hoặc bottleneck nằm ở network/application. Đây vẫn là bằng chứng pruning đúng, nhưng chưa chứng minh partitioning mang lại lợi ích vận hành đủ lớn.

### 18.3. Trường hợp truy vấn nhanh hơn nhưng workload xấu hơn

Một truy vấn báo cáo có thể giảm 80% thời gian, trong khi insert throughput giảm và customer lookup chậm hơn do nhiều local index partition. Hãy tổng hợp theo tỷ trọng và SLA của từng nhóm; không tối ưu một SQL đơn lẻ mà làm workload chính suy giảm.

### 18.4. Tính lợi ích tổng thể

Có thể lập bảng trọng số:

| Nhóm workload | Tỷ trọng request | Thay đổi p95 | Thay đổi throughput | SLA đạt? |
|---|---:|---:|---:|---|
| Date range |  |  |  |  |
| Customer lookup |  |  |  |  |
| Report aggregate |  |  |  |  |
| Insert batch |  |  |  |  |
| Retention maintenance |  |  |  |  |

Đối với truy vấn, weighted latency có thể giúp mô tả xu hướng nhưng không thay thế percentile tổng hợp trên request stream. Với batch/maintenance, đo thời gian hoàn tất và ảnh hưởng đến hệ thống trong lúc chạy.

### 18.5. Kết luận phải có giới hạn

Một kết luận tốt ghi rõ:

- Oracle release/RU và cấu hình.
- Dữ liệu thử có bao nhiêu hàng, bao nhiêu partition.
- Partition key và granularity.
- Index và statistics.
- SQL/bind distribution và số session.
- Điều kiện cache, thời gian chạy và số lần lặp.
- Các chỉ số được đo.
- Truy vấn nào cải thiện/không cải thiện.
- Chi phí vận hành và rủi ro còn lại.

Không khái quát kết quả từ một schema nhỏ hoặc một query thành cam kết cho toàn hệ thống.

## 19. Checklist kiểm chứng lợi ích phân vùng

- [ ] Có workload và SQL đại diện được ghi nhận.
- [ ] Partition key gắn với predicate hoặc vòng đời dữ liệu thực tế.
- [ ] Bảng heap và partitioned có dữ liệu logic tương đương.
- [ ] Index, constraint, datatype và bind được so sánh công bằng.
- [ ] Statistics của bảng, partition và index đã được thu thập.
- [ ] Execution plan có PSTART/PSTOP và partition pruning được diễn giải đúng.
- [ ] Actual rows, buffers, reads và thời gian được thu thập.
- [ ] Có truy vấn theo partition key và không có partition key.
- [ ] Có workload đọc/ghi đồng thời.
- [ ] Có đo insert/update/delete và retention maintenance.
- [ ] Đã xem local/global index và trạng thái index partition.
- [ ] Đã kiểm tra partition skew và số lượng partition.
- [ ] Đã lặp nhiều lần và kiểm soát cache/ngoại tải.
- [ ] Có p50/p95/p99 hoặc phân phối latency phù hợp.
- [ ] Có so sánh storage, redo/undo, stats và công sức vận hành.
- [ ] Kết luận nêu rõ điều kiện thử và giới hạn áp dụng.

## 20. Câu hỏi tự kiểm tra

1. Partitioning khác indexing ở mục tiêu nào?
2. Partition pruning giúp giảm công việc truy cập dữ liệu ra sao?
3. Range, interval, list, hash và composite partition phù hợp với workload nào?
4. PSTART/PSTOP biểu thị điều gì trong execution plan?
5. Static pruning khác dynamic pruning như thế nào?
6. Vì sao bind variable có thể làm PSTART/PSTOP hiển thị KEY mà vẫn prune?
7. Predicate TRUNC(partition_key) có thể ảnh hưởng pruning thế nào?
8. Vì sao phải bind DATE/TIMESTAMP đúng kiểu?
9. EXPLAIN PLAN khác DISPLAY_CURSOR với ALLSTATS LAST ra sao?
10. E-Rows và A-Rows khác nhau như thế nào?
11. Vì sao một truy vấn không có partition key cần được đưa vào benchmark?
12. Local index và global index có trade-off gì?
13. Partition-wise join cần điều kiện tương thích nào?
14. Vì sao partitioning không tự động tăng tốc truy vấn đọc phần lớn bảng?
15. Partition skew và quá nhiều partition gây vấn đề gì?
16. Statistics partition và global statistics hỗ trợ optimizer thế nào?
17. Incremental statistics có ích trong tình huống nào?
18. Vì sao phải đo concurrency thay vì chỉ chạy một session?
19. Những chỉ số nào chứng minh giảm I/O/CPU và cải thiện latency?
20. Vì sao phải tính cả chi phí DML, index, retention và statistics?
21. Khi nào DROP/TRUNCATE partition có thể thay DELETE hàng loạt?
22. Partition exchange cần điều kiện cấu trúc và dữ liệu nào?
23. Làm thế nào kiểm soát cache để benchmark công bằng?
24. Một kết luận benchmark cần ghi những thông tin nào để có thể lặp lại?

**Nguyên tắc cần nhớ:** partitioning có giá trị khi nó giảm công việc thực sự của workload hoặc đơn giản hóa vận hành dữ liệu theo vòng đời. Hãy chứng minh pruning qua PSTART/PSTOP và plan thực thi, rồi chứng minh tác động bằng actual rows, buffer gets, physical reads, CPU, latency và throughput dưới tải đại diện. Đo cả truy vấn không có partition key, DML, index maintenance, statistics và retention operation. Chỉ quyết định dựa trên kết quả tổng thể, không dựa vào việc bảng đã được chia partition hay một execution plan trông có vẻ đẹp hơn.

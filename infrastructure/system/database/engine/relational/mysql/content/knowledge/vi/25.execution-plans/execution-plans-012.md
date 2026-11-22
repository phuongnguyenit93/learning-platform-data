# So sánh kế hoạch ước tính với số liệu thực thi trên dữ liệu đại diện

Một truy vấn có thể có execution plan trông tốt trên bảng thử nghiệm nhỏ nhưng chạy chậm khi đưa lên production. Ngược lại, full table scan không nhất thiết là sai nếu bảng nhỏ hoặc truy vấn cần đọc phần lớn dữ liệu. Muốn đánh giá đúng quyết định của optimizer, cần đặt kế hoạch ước tính cạnh số liệu thực thi trên tập dữ liệu có quy mô và phân bố gần với workload thật.

MySQL cung cấp hai góc nhìn bổ sung. EXPLAIN cho biết optimizer dự định truy cập bảng, chọn index và ước tính cardinality như thế nào mà không thực thi truy vấn. EXPLAIN ANALYZE thực thi câu SELECT và ghi nhận số hàng, số vòng lặp cùng thời gian của các iterator trong execution plan. So sánh hai kết quả giúp tìm nơi ước lượng sai, xác định bước thực sự tốn thời gian và kiểm chứng một thay đổi index hoặc SQL có cải thiện hay không.

## 1. Estimated plan và actual execution khác nhau thế nào?

### 1.1. Estimated plan

EXPLAIN yêu cầu optimizer lập kế hoạch cho câu SQL. Optimizer dùng thống kê bảng/index, điều kiện truy vấn, cardinality ước tính và mô hình chi phí để chọn access path, join order và các thao tác cần thiết.

Ví dụ:

```sql
EXPLAIN
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01';
```

Kế hoạch ước tính có thể cho biết:

- Optimizer đọc bảng nào trước.
- Bảng được truy cập bằng full scan, index lookup hay range scan.
- Index nào được chọn.
- Ước tính số hàng phải xem xét qua rows.
- Tỷ lệ hàng còn lại sau lọc qua filtered.
- Có thao tác sort, temporary table hoặc điều kiện index nào đáng chú ý trong Extra.

EXPLAIN không chạy toàn bộ SELECT để đo số hàng và thời gian thực tế. Các con số cardinality là dự đoán, có thể sai khi thống kê cũ, dữ liệu lệch hoặc các cột có tương quan.

### 1.2. Actual execution

Từ MySQL 8.0.18, có thể dùng EXPLAIN ANALYZE:

```sql
EXPLAIN ANALYZE
SELECT
    c.id,
    o.id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01';
```

Lệnh này thực sự thực thi SELECT và hiển thị execution tree với thông tin như:

- actual time: thời gian iterator bắt đầu trả hàng và thời gian hoàn tất, tính bằng mili giây.
- actual rows: số hàng thực tế iterator trả ra trung bình cho mỗi lần chạy.
- loops: số lần iterator được thực thi.
- cost và rows: ước lượng của optimizer đặt cạnh số liệu thực tế.

EXPLAIN ANALYZE không phải lệnh chỉ đọc kế hoạch. Nó chạy truy vấn để lấy số đo. Chỉ dùng với SELECT có thể thực thi an toàn, cân nhắc tải và thời gian trên production, đặc biệt với truy vấn quét bảng lớn hoặc gọi nhiều lần.

### 1.3. Không nhầm ba loại số liệu

| Loại số liệu | Nguồn | Ý nghĩa |
|---|---|---|
| Estimated rows | EXPLAIN | Optimizer dự đoán số hàng của bước truy cập |
| Actual rows | EXPLAIN ANALYZE | Số hàng iterator thực sự trả ra trung bình mỗi loop |
| Actual time | EXPLAIN ANALYZE | Thời gian thực tế iterator tiêu tốn theo cách đo của executor |

Số hàng trả ra không đồng nghĩa số page đọc từ đĩa, số record đã kiểm tra trong mọi tầng hay số byte truyền đến client. Để hiểu toàn bộ chi phí, cần đọc cả access path, loops, thời gian và các chỉ số vận hành khác.

## 2. Dữ liệu đại diện quan trọng hơn dữ liệu lớn đơn thuần

Một bộ dữ liệu có một triệu hàng nhưng mọi giá trị phân bố đồng đều có thể không đại diện cho production. Dữ liệu thật thường có giá trị phổ biến, giá trị hiếm, nhóm khách hàng lớn bất thường, hàng NULL, khoảng trống khóa và tương quan giữa các cột.

Khi chuẩn bị môi trường đo, hãy xem xét:

- **Quy mô:** số hàng mỗi bảng, kích thước index và dung lượng dữ liệu.
- **Skew:** một vài giá trị có thể chiếm tỷ lệ rất lớn, chẳng hạn một khách hàng tạo phần lớn đơn hàng.
- **Correlation:** các cột có thể phụ thuộc nhau, ví dụ khách hàng ở một khu vực thường có cùng trạng thái.
- **NULL và giá trị biên:** tỷ lệ NULL, ngày rất cũ/mới, số tiền bằng 0 hoặc giá trị cực lớn.
- **Độ rộng hàng:** cột TEXT/BLOB và số cột được truy vấn có thể ảnh hưởng I/O.
- **Phân bố thời gian:** dữ liệu gần đây có thể được truy cập thường xuyên hơn dữ liệu cũ.
- **Tính duy nhất:** mức độ unique của primary key, unique key và các cột JOIN.
- **Mức cập nhật:** workload đọc/ghi và tỷ lệ thay đổi dữ liệu.

Một benchmark chỉ có dữ liệu đều, bảng nhỏ và cache luôn nóng dễ tạo ra kết luận sai. Hãy dùng snapshot đã ẩn dữ liệu nhạy cảm, bộ sinh dữ liệu có phân bố được kiểm soát hoặc staging chứa dữ liệu tương đương production.

## 3. Chuẩn bị schema và truy vấn cần đo

Ví dụ mô hình đơn hàng:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_customers_region_status (region_code, status)
) ENGINE=InnoDB;

CREATE TABLE orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_orders_customer_created (customer_id, created_at),
    KEY idx_orders_created_customer (created_at, customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;
```

Truy vấn đại diện:

```sql
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

Trước khi đo, xác định truy vấn này đại diện cho thao tác nào: trang lịch sử đơn hàng, báo cáo tháng, API tra cứu hay tác vụ nền. Chọn tham số thực tế gồm cả trường hợp phổ biến và hiếm. Một giá trị khu vực có thể trả về 70% khách hàng, trong khi khu vực khác chỉ trả về 0,2%; một khách hàng có thể có vài đơn, khách hàng khác có hàng triệu đơn.

Không dùng một tham số thuận tiện duy nhất rồi kết luận plan tốt cho mọi lần gọi.

## 4. Giữ điều kiện thử nghiệm có thể so sánh

Khi so sánh hai kế hoạch hoặc hai phiên bản SQL, cần giữ các yếu tố quan trọng giống nhau:

| Yếu tố | Cần ghi nhận |
|---|---|
| MySQL version | Phiên bản chính xác và edition |
| Schema | Cấu trúc bảng, index, constraint |
| Statistics | Thời điểm ANALYZE, histogram và persistent statistics |
| Query | SQL nguyên bản, parameter values và session settings |
| Server | CPU, RAM, storage, buffer pool, cấu hình chính |
| Cache state | Lần chạy đầu hay cache đã nóng |
| Concurrency | Số request đồng thời và workload nền |
| Isolation | Transaction isolation level và autocommit |
| Data state | Snapshot dữ liệu và thời điểm nạp |
| Client path | Cùng driver, network path và cách fetch kết quả |

Nếu thay đồng thời SQL, index, cấu hình optimizer và dữ liệu, sẽ khó xác định thay đổi nào tạo ra kết quả. Mỗi thử nghiệm nên thay một yếu tố chính, ghi lại các yếu tố còn lại.

## 5. Quy trình đo từ EXPLAIN đến EXPLAIN ANALYZE

### Bước 1 — Chụp kế hoạch ước tính

```sql
EXPLAIN
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

Ghi lại:

- Join order.
- Access type và index được chọn cho từng bảng.
- Estimated rows và filtered.
- Các điều kiện access, index condition và residual WHERE nếu có.
- Sort, temporary table, materialization hoặc filesort.

### Bước 2 — Xem kế hoạch chi tiết

```sql
EXPLAIN FORMAT=JSON
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

JSON có thể cung cấp các trường như rows_examined_per_scan, rows_produced_per_join, filtered, cost_info, used_key_parts và điều kiện gắn với từng bước. Cấu trúc lồng phụ thuộc kế hoạch và phiên bản.

### Bước 3 — Đo thực tế

```sql
EXPLAIN ANALYZE
SELECT
    c.id AS customer_id,
    o.id AS order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.id
WHERE c.region_code = 'VN'
  AND c.status = 'ACTIVE'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2026-02-01'
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 100;
```

Đọc từ root iterator xuống các iterator con. Ghi lại actual rows, loops và actual time. Chú ý iterator nào trả nhiều hàng, iterator nào bị gọi lặp nhiều lần và bước nào tiêu tốn thời gian đáng kể.

### Bước 4 — So sánh theo cùng đơn vị

Với mỗi iterator, đối chiếu estimated rows với actual rows trên cơ sở mỗi lần thực thi. Nếu inner iterator chạy 5.000 loops, đừng so estimated rows per scan với tổng actual rows đã cộng qua 5.000 loops.

### Bước 5 — Tìm nguyên nhân chênh lệch

Kiểm tra statistics, skew, correlation, điều kiện JOIN, kiểu dữ liệu, index, số lần lặp và tác động của sort/materialization. Chỉ đề xuất thay đổi sau khi đã xác định được bước gây sai lệch hoặc chi phí.

## 6. Đọc actual rows và loops đúng cách

Trong output EXPLAIN ANALYZE, actual rows được báo trung bình cho mỗi lần iterator chạy; loops cho biết iterator chạy bao nhiêu lần. Vì vậy, để ước lượng tổng số hàng iterator đã trả qua tất cả vòng lặp, có thể nhân:

```text
total_rows_returned_approximately
    = actual_rows_per_loop * loops
```

Ví dụ:

```text
-> Index lookup on orders
   (cost=... rows=4)
   (actual time=... rows=3 loops=5000)
```

Diễn giải:

- Optimizer ước tính khoảng 4 hàng cho mỗi lần lookup.
- Mỗi lần lookup thực tế trả trung bình 3 hàng.
- Iterator được gọi 5.000 lần.
- Tổng lượng hàng trả ra qua các lần lookup xấp xỉ 15.000.

Ước lượng tổng số hàng theo mô hình đơn giản là 4 × 5.000 = 20.000; số thực tế xấp xỉ 3 × 5.000 = 15.000. Trong trường hợp này estimate per-loop khá gần actual.

Không phải mọi iterator đều có ý nghĩa giống nhau. Iterator lọc có thể nhận nhiều hàng từ child nhưng chỉ trả một phần; iterator aggregate có thể trả một hàng dù đọc nhiều hàng đầu vào; iterator sort có thể phải tiêu thụ toàn bộ đầu vào trước khi trả kết quả. Đọc cả cây thay vì chỉ lấy số ở node gốc.

## 7. So sánh thời gian thực thi

Output actual time thường có dạng:

```text
actual time=first_row_time..completion_time
```

Hai mốc biểu diễn thời gian đến hàng đầu tiên và thời gian hoàn tất iterator theo cách đo của executor. Với iterator chạy nhiều loops, thời gian hiển thị có thể là thời gian trung bình mỗi loop. Hãy đọc kèm loops và quan hệ cha/con.

Một node con có thể có thời gian hoàn tất lớn, nhưng thời gian của node cha không đơn giản bằng tổng tất cả thời gian con vì các iterator có quan hệ gọi lồng nhau và cách đo có thể bao gồm công việc ở các tầng khác nhau.

Để đánh giá độ trễ người dùng, vẫn cần đo wall-clock của câu truy vấn từ client hoặc công cụ benchmark:

- Thời gian từ lúc gửi request đến lúc nhận hàng đầu tiên.
- Thời gian đến khi fetch hết kết quả.
- Số hàng/byte truyền về.
- Connection acquisition và network latency nếu đo ở tầng ứng dụng.

EXPLAIN ANALYZE hữu ích để xác định iterator tốn thời gian bên trong server, nhưng không thay thế số đo end-to-end.

## 8. Ví dụ: ước lượng sai ở bảng ngoài JOIN

Giả sử EXPLAIN ước tính:

| Bước | Estimated rows | Filtered | Estimated output |
|---|---:|---:|---:|
| customers | 50.000 | 20% | 10.000 |
| orders lookup | 8 | 50% | 4 mỗi loop |

EXPLAIN ANALYZE cho thấy:

| Bước | Actual rows/loop | Loops | Tổng hàng xấp xỉ |
|---|---:|---:|---:|
| customers | 500 | 1 | 500 |
| orders lookup | 3 | 500 | 1.500 |

Optimizer đã ước lượng số khách hàng đầu vào cao hơn thực tế 20 lần. Vì bảng orders là inner side của nested-loop join, số lần lookup thực tế cũng thấp hơn dự kiến rất nhiều.

Điều cần điều tra đầu tiên là predicate của customers: thống kê region_code và status có phản ánh phân bố thật không, hai cột có tương quan không, histogram có phù hợp không. Chỉ thêm index cho orders có thể không giải quyết sai lệch ở outer input.

Ngược lại, nếu actual customers là 200.000 thay vì 10.000, inner lookup có thể chạy nhiều hơn dự kiến rất nhiều. Khi đó cần xem lại access path, index và cách giảm số hàng đầu vào trước khi JOIN.

## 9. Ví dụ: index được chọn nhưng vẫn đọc quá nhiều hàng

Giả sử truy vấn:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = 120
  AND status = 'PAID'
  AND created_at >= '2026-01-01';
```

Index hiện tại:

```sql
KEY idx_orders_customer (customer_id)
```

Optimizer có thể dùng index theo customer_id, nhưng phải kiểm tra nhiều hàng của khách hàng đó để lọc status và created_at. Nếu khách hàng có hàng trăm nghìn đơn, rows và actual rows ở access path có thể lớn.

Có thể thử index ghép:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
```

Sau khi tạo index trên môi trường thử nghiệm, chụp lại EXPLAIN và EXPLAIN ANALYZE. So sánh:

- Access type và key được chọn.
- Estimated rows và actual rows per loop.
- Số loops.
- Thời gian iterator và tổng thời gian truy vấn.
- Chi phí ghi tăng thêm do index mới.

Index mới có thể giảm số entry phải xem xét, nhưng không bảo đảm truy vấn nhanh hơn trong mọi workload. Nếu query trả phần lớn dữ liệu của khách hàng hoặc sort vẫn chi phối, lợi ích có thể khác kỳ vọng.

## 10. Đo trên nhiều giá trị tham số

Một câu SQL có thể có độ chọn lọc rất khác nhau theo parameter:

- Khu vực lớn có thể chứa phần lớn khách hàng.
- Một khu vực nhỏ chỉ có vài trăm khách hàng.
- Một customer ID có vài đơn hàng, customer khác có hàng triệu đơn.
- Khoảng ngày một tuần khác hẳn khoảng ngày ba năm.

Tạo bộ tham số đại diện:

| Nhóm | Ví dụ |
|---|---|
| Phổ biến | Giá trị xuất hiện nhiều trong dữ liệu |
| Hiếm | Giá trị có rất ít hàng |
| Biên thấp/cao | Ngày cũ nhất, ngày mới nhất hoặc amount cực trị |
| Nhóm lớn bất thường | Tenant/customer có dữ liệu áp đảo |
| Không có kết quả | Tham số hợp lệ nhưng không khớp hàng |

Chạy cả estimated plan và actual plan cho từng nhóm. Ghi nhận plan có thay đổi hay không, estimate lệch ở đâu và độ trễ khác nhau thế nào. Một index có thể tốt cho tham số hiếm nhưng kém hiệu quả với tham số phổ biến.

## 11. Cache nóng và cache lạnh

Lần chạy đầu có thể phải đọc page từ storage; các lần tiếp theo có thể lấy page từ InnoDB buffer pool hoặc cache của hệ điều hành. Vì vậy, thời gian chạy lặp lại thường không đại diện cho lần chạy đầu.

Phân biệt:

- **Cold-ish run:** dữ liệu chưa có sẵn trong cache liên quan; cần nhiều I/O hơn. Không dễ tạo trạng thái cold hoàn toàn nếu không kiểm soát server.
- **Warm run:** page và metadata đã có trong cache; thường gần với workload lặp lại của ứng dụng.
- **Steady-state workload:** nhiều truy vấn cùng hoạt động, cache thay đổi theo workload thực tế.

Không xóa buffer pool hoặc restart production chỉ để tạo benchmark cold-cache. Hãy đo trong môi trường riêng hoặc ghi rõ điều kiện cache. Khi so sánh hai query, chạy warm-up có kiểm soát và dùng cùng cách đo cho cả hai.

## 12. Concurrency và workload nền

Một truy vấn chạy đơn lẻ trong 20 ms có thể chậm lên 500 ms khi có nhiều request đồng thời do:

- CPU cạnh tranh.
- I/O queue tăng.
- Buffer pool pressure.
- Lock wait hoặc metadata lock.
- Connection pool cạn.
- Temporary table và sort cạnh tranh tài nguyên.
- Replication hoặc background maintenance tạo thêm tải.

EXPLAIN ANALYZE chủ yếu giúp quan sát một lần thực thi. Nó không mô phỏng đầy đủ hàng trăm request đồng thời. Sau khi xác định plan hợp lý, chạy benchmark concurrency riêng với số worker và tỷ lệ read/write gần production.

Theo dõi latency median, p95/p99, throughput, CPU, I/O, lock waits, buffer pool và replica lag. Không kết luận một index tốt chỉ vì một lần chạy đơn nhanh hơn.

## 13. Thống kê và histogram trước khi kết luận optimizer sai

Nếu estimated rows lệch nhiều so với actual rows, kiểm tra thống kê:

```sql
SHOW INDEX FROM customers;
SHOW INDEX FROM orders;

ANALYZE TABLE customers, orders;
```

ANALYZE TABLE cập nhật thống kê mà optimizer sử dụng. Với InnoDB, thống kê index có thể dựa trên sampling nên vẫn là ước lượng. Thao tác cập nhật statistics có thể làm plan thay đổi; hãy ghi lại plan trước và sau.

Nếu dữ liệu skew, histogram có thể cải thiện ước lượng cho predicate đơn cột:

```sql
ANALYZE TABLE customers
UPDATE HISTOGRAM ON region_code, status
WITH 100 BUCKETS;
```

Histogram của từng cột không mô hình hóa đầy đủ mọi tương quan đa cột. Nếu region_code và status phụ thuộc nhau, estimate kết hợp có thể vẫn sai dù histogram riêng từng cột có vẻ hợp lý.

Không chạy ANALYZE TABLE hoặc thay histogram trên production một cách tùy tiện. Đánh giá quyền, tác động và khả năng plan thay đổi trước khi triển khai.

## 14. Phân biệt số hàng iterator với số hàng gửi về client

Một query có thể đọc và xử lý hàng triệu hàng nhưng chỉ trả 100 hàng do LIMIT, aggregate hoặc lọc ở tầng sau. Ngược lại, iterator gốc có thể trả ít hàng nhưng các iterator con đã làm nhiều việc.

Ví dụ:

```sql
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id;
```

Iterator aggregate có thể trả một hàng cho mỗi khách hàng, nhưng cần đọc nhiều order rows để tính tổng. Chỉ nhìn actual rows ở node gốc sẽ bỏ qua chi phí đọc đầu vào.

Với LIMIT:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 20;
```

Nếu index hỗ trợ thứ tự, engine có thể dừng sớm. Nếu phải filesort nhiều hàng trước khi lấy 20 kết quả, lượng công việc thực tế lớn hơn số hàng trả về. Đọc cả iterator tree và Extra/JSON plan để hiểu.

## 15. Benchmark có thể lặp lại

Một benchmark hữu ích cần có quy trình cố định:

1. Nạp hoặc khôi phục cùng một snapshot dữ liệu.
2. Ghi phiên bản MySQL, schema, index, statistics và cấu hình liên quan.
3. Chuẩn bị danh sách SQL và bộ parameter đại diện.
4. Chạy EXPLAIN và lưu estimated plan.
5. Chạy EXPLAIN ANALYZE an toàn để lấy actual iterator metrics.
6. Warm-up theo quy trình được ghi rõ.
7. Chạy nhiều lượt benchmark client với concurrency đã xác định.
8. Ghi median, p95/p99, throughput, rows/bytes và tài nguyên.
9. Thay một yếu tố chính, chẳng hạn một index hoặc cách viết query.
10. Lặp lại cùng quy trình và so sánh.

Không chỉ lấy lần chạy nhanh nhất. Dùng median và percentile để hiểu độ ổn định; loại bỏ hoặc ghi chú các lần đo bị ảnh hưởng bởi tác vụ nền bất thường.

### 15.1. Bảng ghi nhận thử nghiệm

| Trường | Trước thay đổi | Sau thay đổi |
|---|---|---|
| SQL/parameter set | Ghi rõ | Giữ nguyên |
| Schema/index | Phiên bản ban đầu | Ghi index thay đổi |
| Estimated rows | Số từ EXPLAIN | Số mới |
| Actual rows/loops | Số từ EXPLAIN ANALYZE | Số mới |
| Iterator time | Thời gian thực tế | Thời gian mới |
| Client p50/p95 | Đo end-to-end | Đo lại |
| Throughput | Query/giây | Query/giây |
| CPU/I/O | Tài nguyên | Tài nguyên |
| Write overhead | Mức nền | Chi phí index mới |
| Kết luận | Bottleneck cũ | Lợi ích và trade-off |

## 16. Khi estimated và actual lệch nhau

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Estimated rows lớn hơn actual nhiều | Statistics cũ, predicate chọn lọc hơn dự kiến, histogram chưa phù hợp | ANALYZE, histogram, phân bố dữ liệu |
| Estimated rows nhỏ hơn actual nhiều | Data skew, giá trị phổ biến, tương quan cột | Test nhiều parameter, kiểm tra skew/correlation |
| Inner iterator loops lớn | Outer input lớn hơn dự kiến hoặc join order không phù hợp | Kiểm tra cardinality bảng ngoài |
| Actual rows ít nhưng thời gian cao | I/O chậm, lock, row rộng, function hoặc chi phí iterator khác | Xem timing, wait và server metrics |
| Estimated rows sát nhưng query vẫn chậm | Nút thắt không nằm ở cardinality | Kiểm tra sort, temporary table, I/O, lock, CPU, concurrency |
| Plan thay đổi giữa môi trường | Statistics, version, config, schema hoặc dữ liệu khác | Chuẩn hóa môi trường và so sánh metadata |
| Một parameter nhanh, parameter khác chậm | Selectivity khác nhau | Benchmark theo nhóm parameter |

Sai lệch estimate/actual là tín hiệu để điều tra, không phải bằng chứng duy nhất rằng optimizer có lỗi. Một kế hoạch có ước lượng chính xác vẫn có thể chậm do I/O, lock hoặc lượng dữ liệu phải xử lý.

## 17. Không ép optimizer trước khi hiểu nguyên nhân

Khi plan không như kỳ vọng, tránh lập tức thêm FORCE INDEX, STRAIGHT_JOIN hoặc optimizer hint. Trước tiên:

- Xác nhận dữ liệu và tham số thử nghiệm đại diện.
- Kiểm tra thống kê và cardinality.
- Xem điều kiện JOIN có đúng kiểu dữ liệu và collation không.
- Kiểm tra index có hỗ trợ access path mong muốn không.
- So sánh actual rows, loops và timing.
- Đánh giá chi phí ghi và lưu trữ của index mới.

Hint có thể hữu ích trong một số trường hợp đã chứng minh optimizer chọn sai, nhưng làm query phụ thuộc vào cấu trúc dữ liệu và phiên bản. Nếu dùng, ghi rõ lý do, phạm vi ảnh hưởng và cách kiểm tra lại sau thay đổi schema hoặc MySQL upgrade.

## 18. Giới hạn của EXPLAIN ANALYZE

- Nó thực thi SELECT; truy vấn có thể tiêu thụ đáng kể CPU, I/O và thời gian.
- Nó đo một lần chạy trong điều kiện tại thời điểm đó, không đại diện mọi concurrency.
- Cache nóng/lạnh và workload nền có thể làm thời gian thay đổi.
- Actual rows ở iterator có ý nghĩa per-loop; cần đọc loops.
- Thời gian iterator không phải toàn bộ latency end-to-end từ ứng dụng.
- Nó không tự giải thích đầy đủ lock wait, network, client fetch hoặc connection pool delay.
- Nó không phải công cụ benchmark tải cao thay cho workload generator.

Hãy kết hợp EXPLAIN ANALYZE với Performance Schema, slow query log, statement digest, server metrics và benchmark ở tầng ứng dụng khi cần.

## 19. Quy trình ra quyết định sau khi so sánh

**Trường hợp A — Estimate sát actual, iterator nhanh:** giữ kế hoạch và theo dõi workload thực tế. Không cần thay index chỉ để làm plan khác đi.

**Trường hợp B — Estimate sai ở outer table:** kiểm tra thống kê, skew, correlation và predicate của bảng đầu vào. Sửa cardinality estimate trước khi thay đổi JOIN order.

**Trường hợp C — Estimate sát nhưng inner loop quá nhiều:** xem số hàng đầu vào, index lookup và khả năng giảm outer rows trước khi JOIN.

**Trường hợp D — Một access path đọc nhiều hàng rồi lọc:** cân nhắc composite index, predicate sargable hoặc thay đổi cấu trúc truy vấn; xác nhận write overhead.

**Trường hợp E — Actual iterator nhanh nhưng client chậm:** điều tra network, fetch size, serialization, connection pool và xử lý ở ứng dụng.

**Trường hợp F — Plan tốt nhưng production vẫn chậm:** kiểm tra concurrency, lock waits, I/O, CPU, cache và các tác vụ nền.

## 20. Checklist so sánh estimated plan và actual execution

- Dataset có quy mô, skew, correlation và tỷ lệ NULL gần workload thật không?
- Schema, index, MySQL version và statistics có được ghi nhận không?
- SQL và parameter values có đại diện cho trường hợp phổ biến lẫn hiếm không?
- Đã lưu EXPLAIN dạng bảng và JSON chưa?
- Đã đọc access type, key, rows, filtered, Extra và join order chưa?
- Đã chạy EXPLAIN ANALYZE an toàn và hiểu nó thực thi SELECT chưa?
- Actual rows có được so sánh theo mỗi loop, không nhầm với tổng rows không?
- Đã xem loops của inner iterator và lượng hàng tích lũy chưa?
- Đã phân tích first-row/completion time cùng thời gian end-to-end chưa?
- Đã kiểm soát cache state, concurrency và workload nền chưa?
- Đã kiểm tra statistics, histogram, data skew và correlation chưa?
- Đã đo nhiều parameter values chưa?
- Thay đổi có chỉ gồm một yếu tố chính để dễ quy nguyên nhân không?
- Đã đo p50/p95/p99, throughput, CPU/I/O và write overhead chưa?
- Kết luận có dựa trên nhiều lần đo và dữ liệu đại diện không?

## Kết luận

So sánh estimated plan với actual execution là cách kiểm chứng optimizer đang dự đoán dữ liệu và thực thi ra sao. EXPLAIN cho biết kế hoạch cùng cardinality ước tính; EXPLAIN ANALYZE thực thi SELECT và cung cấp actual rows, loops và timing của từng iterator. Dữ liệu thử phải phản ánh quy mô, skew, correlation và các nhóm parameter của workload thật. Khi so sánh, luôn quy actual rows về cùng đơn vị per-loop/per-scan, đọc cả cây iterator và đo thêm latency end-to-end cùng concurrency. Nếu estimate lệch, điều tra statistics và phân bố dữ liệu; nếu estimate sát mà vẫn chậm, tìm bottleneck ở I/O, sort, lock, CPU hoặc tầng ứng dụng. Chỉ thay index, SQL hay hint sau khi có bằng chứng lặp lại trên môi trường đại diện.

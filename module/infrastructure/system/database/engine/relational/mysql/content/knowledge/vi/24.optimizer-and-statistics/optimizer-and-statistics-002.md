# Cardinality, selectivity, cost và giới hạn của ước lượng

MySQL không chọn kế hoạch truy vấn chỉ dựa vào việc một cột có index hay không. Optimizer cần ước lượng có bao nhiêu hàng thỏa từng điều kiện, một lần truy cập index sẽ đọc bao nhiêu hàng, các phép join sẽ tạo ra bao nhiêu kết quả trung gian và mỗi phương án tốn bao nhiêu công việc. Những ước lượng này dựa trên thống kê của bảng/index, histogram, cấu trúc truy vấn và cost model.

Ba khái niệm nền tảng là **cardinality**, **selectivity** và **cost**. Cardinality mô tả số giá trị phân biệt được ước lượng trong một cột hoặc index prefix. Selectivity mô tả mức độ lọc của điều kiện. Cost là điểm chi phí tương đối mà optimizer dùng để so sánh các kế hoạch. Nếu thống kê thiếu, cũ hoặc không phản ánh phân bố dữ liệu, optimizer có thể ước lượng sai số hàng và chọn full table scan, index scan hoặc thứ tự join kém hiệu quả.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và tối ưu truy vấn. Mục tiêu là đọc được thống kê, hiểu optimizer đang ước lượng điều gì, nhận ra khoảng cách giữa ước lượng và thực tế, rồi cập nhật thống kê hoặc thay đổi truy vấn/index dựa trên bằng chứng.

Sau bài học, bạn có thể:

- Phân biệt cardinality của index với số hàng của bảng.
- Phân biệt tỷ lệ giá trị phân biệt với tỷ lệ hàng thỏa predicate khi nói về selectivity.
- Giải thích cost model và vì sao cost không phải thời gian chạy tính bằng mili giây.
- Đọc `rows`, `filtered`, `key`, `type` và `cost_info` trong EXPLAIN.
- Kiểm tra persistent InnoDB statistics và index-prefix cardinality.
- Dùng `ANALYZE TABLE` để cập nhật key distribution.
- Tạo, xem và xóa histogram để mô tả phân bố của cột.
- Nhận diện data skew, correlation và sai lệch do lấy mẫu.
- So sánh ước lượng với số hàng thực tế bằng `EXPLAIN ANALYZE`.
- Dùng optimizer trace và chọn cách khắc phục có kiểm chứng.

## 1. Optimizer cần ước lượng những gì?

Khi nhận một câu `SELECT`, MySQL phân tích cú pháp và xây dựng các phương án thực thi. Với mỗi bảng, optimizer cân nhắc cách truy cập dữ liệu; với nhiều bảng, nó cân nhắc thứ tự join và phương pháp join. Để so sánh các phương án, optimizer cần ước lượng:

- Tổng số hàng và số giá trị phân biệt trong các cột/index.
- Số hàng có thể thỏa từng predicate.
- Số hàng cần đọc từ table hoặc index.
- Số hàng còn lại sau khi áp dụng điều kiện lọc.
- Số hàng trung gian khi kết hợp các bảng.
- Chi phí đọc index, đọc data page, lọc hàng, sắp xếp, materialize và thực hiện join.

Optimizer không chạy thử mọi kế hoạch trên toàn bộ dữ liệu rồi chọn kế hoạch nhanh nhất. Nó dùng thống kê và mô hình chi phí để dự đoán. Do đó, chất lượng thống kê ảnh hưởng trực tiếp đến chất lượng kế hoạch.

Ví dụ, với truy vấn:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE status = 'OPEN'
  AND created_at >= '2026-11-01';
```

Optimizer cần ước lượng có bao nhiêu đơn hàng đang mở, bao nhiêu đơn hàng được tạo từ ngày 01/11 và bao nhiêu hàng thỏa cả hai điều kiện. Nếu chỉ có thống kê riêng lẻ của `status` và `created_at`, nhưng hai cột có tương quan mạnh, ước lượng kết hợp có thể sai.

## 2. Cardinality là gì?

Cardinality là số lượng giá trị phân biệt được ước lượng trong một tập dữ liệu hoặc một phần index. Trong MySQL, cột `Cardinality` của `SHOW INDEX` là ước lượng số giá trị khác nhau trong index hoặc index prefix tương ứng; nó không phải số hàng chính xác.

Ví dụ một bảng có 100.000 hàng:

| Cột | Số giá trị phân biệt thực tế | Nhận xét |
| --- | ---: | --- |
| `order_id` | 100.000 | Khóa chính, mỗi hàng có một ID |
| `customer_id` | 5.000 | Một khách hàng có thể có nhiều đơn |
| `status` | 4 | Chỉ có bốn trạng thái |
| `country_code` | 30 | Phần lớn hàng tập trung ở vài quốc gia |

Cardinality cao thường có nghĩa index phân biệt được nhiều giá trị. Cardinality thấp nghĩa nhiều hàng chia sẻ cùng giá trị. Tuy nhiên, cardinality cao không tự động làm mọi truy vấn nhanh; hiệu quả còn phụ thuộc predicate, số hàng cần trả, thứ tự cột trong index và chi phí lookup.

### 2.1. Cardinality của index ghép

Với index:

```sql
KEY idx_orders_customer_date (customer_id, created_at)
```

InnoDB thống kê cardinality cho từng prefix:

- Prefix 1: `(customer_id)`.
- Prefix 2: `(customer_id, created_at)`.

Ví dụ:

| Index prefix | Cardinality ước lượng |
| --- | ---: |
| `customer_id` | 5.000 |
| `customer_id, created_at` | 70.000 |

Điều này cho biết tổ hợp khách hàng và thời điểm có nhiều giá trị phân biệt hơn chỉ riêng khách hàng. Nó không có nghĩa mọi truy vấn lọc theo `created_at` riêng lẻ đều dùng tốt index này; quy tắc leftmost prefix vẫn áp dụng.

### 2.2. Cardinality không phải số hàng

Một index trên `status` có cardinality 4 trong bảng 100.000 hàng vẫn có thể rất hữu ích cho một số truy vấn nếu một trạng thái hiếm và query chỉ cần một phần nhỏ dữ liệu. Ngược lại, nếu một trạng thái chiếm 99% bảng và truy vấn cần hầu hết các hàng đó, optimizer có thể chọn scan thay vì đọc index rồi lookup gần như toàn bộ data pages.

Cardinality cũng không nói phân bố giá trị có đồng đều hay không. Hai bảng cùng 4 giá trị phân biệt có thể có phân bố rất khác:

- Bảng A: mỗi giá trị xuất hiện khoảng 25%.
- Bảng B: một giá trị chiếm 97%, ba giá trị còn lại chia 3%.

Thống kê số giá trị phân biệt đơn thuần không mô tả đầy đủ độ lệch này.

## 3. Selectivity: predicate lọc được bao nhiêu hàng?

Từ “selectivity” thường được dùng theo hai cách liên quan nhưng không giống nhau. Để tránh nhầm, trong bài này phân biệt rõ:

1. **Distinct-value fraction**: tỷ lệ số giá trị phân biệt trên tổng số hàng, thường gần với `cardinality / row_count`.
2. **Predicate selectivity**: tỷ lệ hàng thỏa điều kiện trên tổng số hàng, tức `qualifying_rows / total_rows`.

Với một cột có phân bố đều, equality predicate trên một giá trị có thể ước lượng gần bằng `1 / cardinality`. Nhưng khi dữ liệu lệch, phép chia này có thể sai xa.

Ví dụ bảng có 100.000 hàng và `status` có bốn giá trị:

| status | Số hàng | Predicate selectivity |
| --- | ---: | ---: |
| `OPEN` | 2.000 | 2% |
| `PAID` | 8.000 | 8% |
| `CLOSED` | 85.000 | 85% |
| `CANCELLED` | 5.000 | 5% |

Cardinality của `status` là 4; distinct-value fraction là 0,004%. Nhưng predicate `status = 'CLOSED'` có selectivity 85%, còn `status = 'OPEN'` có selectivity 2%. Cùng một cột, hai giá trị có khả năng lọc rất khác nhau.

Trong cách nói thông thường về index, người ta hay gọi cột có ít hàng khớp cho một giá trị là “selective” hoặc “highly selective”. Hãy nói rõ đang nói tỷ lệ hàng khớp nhỏ hay tỷ lệ distinct lớn để tránh đảo nghĩa.

### 3.1. Vì sao selectivity ảnh hưởng tới lựa chọn index?

Giả sử bảng có 1.000.000 hàng:

- Predicate khớp 100 hàng: index lookup có thể đọc ít index entries và ít data pages.
- Predicate khớp 800.000 hàng: index lookup có thể phải đọc rất nhiều index entries và thực hiện nhiều random row lookup; table scan tuần tự có thể rẻ hơn.

Đây không phải ngưỡng cố định. Optimizer còn xét kích thước hàng, index covering hay không, clustering, cache, chi phí I/O/CPU, thứ tự join và các điều kiện khác.

### 3.2. Kết hợp nhiều predicate

Với:

```sql
WHERE status = 'OPEN'
  AND region = 'NORTH'
```

Nếu optimizer chỉ có selectivity riêng từng cột, nó cần ước lượng số hàng thỏa đồng thời cả hai. Trong trường hợp độc lập, có thể hình dung:

```text
selectivity(status AND region)
    ~= selectivity(status) * selectivity(region)
```

Đây là giả định minh họa, không phải quy luật luôn đúng. Nếu đơn hàng `OPEN` chủ yếu thuộc khu vực NORTH, hai điều kiện có tương quan và phép nhân độc lập có thể đánh giá thấp hoặc cao số hàng thực tế.

## 4. Cost là gì và không phải là gì?

Cost là điểm chi phí tương đối do optimizer tính để so sánh các phương án thực thi. Cost phản ánh ước lượng công việc như đọc page, truy cập index, đánh giá điều kiện, xử lý hàng và các thao tác khác theo cost model.

Cost **không phải**:

- Thời gian chạy thực tế tính bằng mili giây.
- Số lượng hàng trả về.
- Số lần đọc disk chính xác.
- Một con số có thể so sánh trực tiếp giữa mọi server, phiên bản và cấu hình.
- Cam kết rằng kế hoạch có cost thấp nhất sẽ luôn chạy nhanh nhất trong mọi thời điểm.

Optimizer chọn phương án có cost ước lượng thấp nhất trong tập phương án mà nó xem xét. Nếu cardinality hoặc selectivity sai, cost của các phương án cũng có thể sai và quyết định cuối cùng có thể không tốt.

### 4.1. Những thành phần ảnh hưởng cost

Tùy loại truy cập và kế hoạch, cost model có thể tính tới:

- Chi phí đọc index và data page.
- Chi phí truy cập theo range hoặc lookup theo khóa.
- Chi phí CPU để đánh giá predicate.
- Chi phí join và số hàng trung gian.
- Chi phí sort, temporary table và materialization.
- Khả năng dùng covering index, giảm row lookup.

MySQL có các bảng cost model như `mysql.server_cost` và `mysql.engine_cost`. Chúng cho phép cấu hình một số hạng mục chi phí; thay đổi tùy tiện có thể làm optimizer chọn kế hoạch kém hơn.

Kiểm tra cost model:

```sql
SELECT cost_name, cost_value, default_value, comment
FROM mysql.server_cost
ORDER BY cost_name;

SELECT engine_name, device_type, cost_name, cost_value, default_value, comment
FROM mysql.engine_cost
ORDER BY engine_name, device_type, cost_name;
```

Các bảng này có thể cần quyền đọc phù hợp. Không chỉnh cost value chỉ để ép một query cụ thể trước khi xác định nguyên nhân sai lệch thống kê hoặc access path.

## 5. MySQL lấy thống kê từ đâu?

Optimizer có thể sử dụng nhiều nguồn thông tin:

- Số hàng và kích thước bảng ước lượng.
- Cardinality của index và các prefix của index ghép.
- Thống kê persistent của InnoDB.
- Histogram của cột.
- Thông tin từ index dive và range optimizer.
- Metadata về kiểu dữ liệu, nullability, unique key và constraint.

Không phải mọi truy vấn đều dùng tất cả nguồn thống kê. Cách ước lượng phụ thuộc loại predicate, index, phiên bản và cấu trúc query.

### 5.1. Persistent InnoDB statistics

InnoDB có thể lưu thống kê bảng/index bền vững để dùng lại sau khi server restart. Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

- `innodb_stats_persistent` điều khiển việc lưu persistent statistics.
- `innodb_stats_auto_recalc` cho phép tự động tính lại persistent stats khi dữ liệu thay đổi đủ nhiều.
- `innodb_stats_persistent_sample_pages` điều khiển số page được lấy mẫu khi tính persistent stats mặc định.

Với InnoDB, persistent statistics được bật mặc định trong các cấu hình MySQL hiện đại. Tự động tính lại có thể diễn ra bất đồng bộ; sau một đợt bulk load hoặc thay đổi phân bố lớn, thống kê có thể chưa phản ánh ngay trạng thái mới. Có thể chạy `ANALYZE TABLE` để yêu cầu cập nhật.

### 5.2. Thống kê theo từng bảng

Có thể cấu hình persistent stats và sample pages theo bảng:

```sql
ALTER TABLE optimizer_lab STATS_PERSISTENT = 1;
ALTER TABLE optimizer_lab STATS_AUTO_RECALC = 1;
ALTER TABLE optimizer_lab STATS_SAMPLE_PAGES = 64;
```

Các tùy chọn này ảnh hưởng cách InnoDB thu thập và làm mới thống kê cho bảng. Sample pages lớn hơn có thể làm ước lượng ổn định hơn với dữ liệu phân bố không đều, nhưng tốn thêm công việc khi tính thống kê. Không mặc định tăng sample pages cho mọi bảng; đánh giá bảng cụ thể.

### 5.3. Xem thống kê persistent

Thông tin bảng có thể xem qua:

```sql
SELECT
    database_name,
    table_name,
    last_update,
    n_rows,
    clustered_index_size,
    sum_of_other_index_sizes
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'optimizer_lab';
```

Thống kê index:

```sql
SELECT
    index_name,
    stat_name,
    stat_value,
    sample_size,
    last_update
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'optimizer_lab'
ORDER BY index_name, stat_name;
```

Các dòng `n_diff_pfxNN` biểu diễn số giá trị phân biệt ước lượng cho các index prefix. Đây là thống kê lấy mẫu, không phải kết quả `COUNT(DISTINCT ...)` chính xác. Truy cập schema `mysql` có thể yêu cầu quyền phù hợp; trong nhiều tình huống `SHOW INDEX` là đủ.

## 6. Tạo fixture để quan sát cardinality và skew

Tạo bảng lab 1.000 hàng với phân bố `status` lệch rõ rệt. Dùng dữ liệu thử nghiệm để xem optimizer ước lượng, không coi các con số cardinality trên bảng nhỏ là kết quả cố định cho mọi phiên bản.

```sql
DROP TABLE IF EXISTS optimizer_lab;

CREATE TABLE optimizer_lab (
    id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    status VARCHAR(12) NOT NULL,
    region VARCHAR(12) NOT NULL,
    created_at DATE NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_optimizer_customer_date (customer_id, created_at)
) ENGINE = InnoDB;

INSERT INTO optimizer_lab
    (id, customer_id, status, region, created_at, amount)
WITH RECURSIVE seq (n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM seq
    WHERE n < 1000
)
SELECT
    n,
    MOD(n, 100) + 1,
    CASE WHEN n <= 950 THEN 'CLOSED' ELSE 'OPEN' END,
    CASE MOD(n, 4)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'SOUTH'
        WHEN 2 THEN 'EAST'
        ELSE 'WEST'
    END,
    DATE_ADD('2026-01-01', INTERVAL MOD(n, 90) DAY),
    CAST(MOD(n * 37, 100000) / 100.0 AS DECIMAL(10, 2))
FROM seq;
```

Script dùng recursive CTE tạo 1.000 số; giới hạn recursion mặc định 1.000 đủ cho ví dụ này. Nếu môi trường đặt giới hạn thấp hơn, điều chỉnh session trong lab hoặc giảm số hàng.

Kiểm tra phân bố thực tế:

```sql
SELECT status, COUNT(*) AS row_count
FROM optimizer_lab
GROUP BY status
ORDER BY status;

SELECT region, COUNT(*) AS row_count
FROM optimizer_lab
GROUP BY region
ORDER BY region;

SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT customer_id) AS distinct_customers,
       COUNT(DISTINCT created_at) AS distinct_dates
FROM optimizer_lab;
```

Kết quả status là 950 hàng `CLOSED` và 50 hàng `OPEN`. `customer_id` có 100 giá trị phân biệt; `region` có bốn giá trị gần đồng đều. Cột `status` và `region` chưa có index riêng, thuận tiện để quan sát tác dụng của histogram.

## 7. Đọc cardinality bằng SHOW INDEX

Chạy:

```sql
ANALYZE TABLE optimizer_lab;
SHOW INDEX FROM optimizer_lab;
```

Trong kết quả `SHOW INDEX`, tập trung vào:

| Cột | Ý nghĩa |
| --- | --- |
| `Key_name` | Tên index |
| `Seq_in_index` | Vị trí cột trong index |
| `Column_name` | Cột thuộc index |
| `Non_unique` | 0 nếu index unique, 1 nếu không unique |
| `Cardinality` | Số giá trị phân biệt ước lượng cho index prefix tới cột đó |
| `Sub_part` | Prefix length nếu index chỉ một phần chuỗi |
| `Index_type` | Loại index, thường là BTREE với ví dụ này |

Với `idx_optimizer_customer_date`, dòng `customer_id` thể hiện cardinality của prefix một cột; dòng `created_at` thể hiện cardinality của tổ hợp `(customer_id, created_at)`. Các giá trị có thể khác nhau giữa lần phân tích hoặc môi trường do sampling và thay đổi dữ liệu.

Không đọc `Cardinality` như một số chính xác. Nếu cần xác minh dữ liệu thật, dùng `COUNT(DISTINCT ...)` trên phạm vi phù hợp, nhưng nhớ rằng truy vấn này có thể phải quét nhiều dữ liệu và tốn tài nguyên.

## 8. ANALYZE TABLE cập nhật thống kê

Sau khi bulk load, xóa lượng lớn hàng hoặc thay đổi phân bố dữ liệu đáng kể, thống kê cũ có thể khiến optimizer ước lượng sai.

```sql
ANALYZE TABLE optimizer_lab;
```

`ANALYZE TABLE` yêu cầu MySQL cập nhật key distribution và các thống kê liên quan để optimizer sử dụng trong kế hoạch sau đó. Nó không phải lệnh tối ưu dữ liệu hay tạo index; nó làm mới thông tin thống kê.

Những tình huống nên cân nhắc:

- Sau khi nạp một lượng dữ liệu lớn.
- Sau khi xóa hoặc archive một phần lớn bảng.
- Sau khi phân bố giá trị thay đổi đáng kể.
- Khi `EXPLAIN` ước lượng số hàng khác xa thực tế và thống kê đã cũ.
- Sau khi thay đổi index hoặc schema có ảnh hưởng tới access path.

`ANALYZE TABLE` có thể tiêu tốn I/O và cần metadata lock ở một số giai đoạn. Chạy theo cửa sổ phù hợp với workload lớn; kiểm tra trạng thái và thời gian thực thi thay vì đưa lệnh vào mọi request ứng dụng.

## 9. Histogram mô tả phân bố của cột

Index cardinality cho biết số giá trị phân biệt ước lượng, nhưng không nhất thiết mô tả giá trị nào phổ biến. Histogram cung cấp thông tin phân bố theo bucket để optimizer ước lượng predicate trên cột.

Histogram đặc biệt hữu ích khi:

- Cột có skew mạnh.
- Cột không có index riêng nhưng thường được lọc.
- Số distinct value thấp hoặc phân bố không đồng đều.
- Ước lượng predicate equality/range trên cột chưa chính xác.

### 9.1. Tạo histogram

Trên MySQL 8.0 trở lên:

```sql
ANALYZE TABLE optimizer_lab
UPDATE HISTOGRAM ON status, region
WITH 16 BUCKETS;
```

MySQL xây dựng histogram cho các cột được chỉ định. Số bucket là giới hạn bucket tối đa được yêu cầu; cấu trúc histogram thực tế phụ thuộc dữ liệu và loại histogram được chọn.

### 9.2. Xem histogram

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'optimizer_lab';
```

Histogram được lưu dưới dạng JSON. Tùy phân bố dữ liệu, MySQL có thể dùng histogram dạng singleton hoặc equi-height. Singleton phù hợp với số giá trị phân biệt nhỏ; equi-height gom giá trị vào các bucket có số lượng quan sát gần tương đương.

### 9.3. Xóa histogram

```sql
ANALYZE TABLE optimizer_lab
DROP HISTOGRAM ON status, region;
```

Xóa histogram không xóa dữ liệu bảng hoặc index. Optimizer quay lại dựa trên các nguồn thống kê khác có sẵn.

### 9.4. Histogram không phải thống kê đa cột

Histogram MySQL mô tả từng cột độc lập; nó không trực tiếp lưu đầy đủ tương quan giữa các cột như `(status, region)` hoặc `(tenant_id, created_at)`. Nếu hai cột phụ thuộc mạnh, optimizer vẫn có thể ước lượng predicate kết hợp sai dù histogram của từng cột riêng lẻ khá chính xác.

Với truy vấn quan trọng, cân nhắc composite index phù hợp với điều kiện kết hợp, thay đổi cách viết query, hoặc tạo dữ liệu tổng hợp/materialized summary nếu workload yêu cầu. Không kỳ vọng histogram đơn cột giải quyết mọi sai lệch join và correlation.

## 10. So sánh ước lượng trước và sau histogram

Chạy các truy vấn sau trước khi tạo histogram và sau khi tạo histogram:

```sql
EXPLAIN FORMAT=TREE
SELECT id, customer_id, status, amount
FROM optimizer_lab
WHERE status = 'OPEN';

EXPLAIN FORMAT=TREE
SELECT id, customer_id, status, amount
FROM optimizer_lab
WHERE status = 'CLOSED';
```

Do `status` chưa có index riêng, MySQL có thể chọn table scan. Điều cần quan sát là ước lượng số hàng sau filter cho `OPEN` và `CLOSED`, không phải bắt optimizer phải chọn một kế hoạch cụ thể trên bảng lab nhỏ.

Trước histogram, optimizer có thể phải dựa vào ước lượng ít thông tin về phân bố. Sau histogram, nó có thêm dữ liệu để nhận biết `OPEN` hiếm hơn `CLOSED`. Kết quả chính xác phụ thuộc phiên bản, thống kê khác và cấu trúc truy vấn.

Để thấy ảnh hưởng của index, thử tạo index trong lab:

```sql
CREATE INDEX idx_optimizer_status ON optimizer_lab (status);
ANALYZE TABLE optimizer_lab;

EXPLAIN FORMAT=TREE
SELECT id, customer_id, status, amount
FROM optimizer_lab
WHERE status = 'OPEN';
```

Index có thể giúp truy vấn `OPEN` vì chỉ một phần nhỏ hàng khớp. Với `CLOSED` chiếm 95%, table scan có thể rẻ hơn việc đọc nhiều index entries rồi lookup data rows. Optimizer quyết định theo cost ước lượng; không có quy tắc “có index thì luôn dùng index”.

## 11. Đọc EXPLAIN: rows và filtered

Chạy:

```sql
EXPLAIN
SELECT id, customer_id, amount
FROM optimizer_lab
WHERE customer_id = 42
  AND created_at >= '2026-02-01';
```

Các cột thường cần xem:

| Cột | Ý nghĩa |
| --- | --- |
| `type` | Kiểu truy cập như `const`, `eq_ref`, `ref`, `range`, `index`, `ALL` |
| `possible_keys` | Các index optimizer xem là ứng viên |
| `key` | Index thực tế được chọn, nếu có |
| `key_len` | Độ dài phần index được dùng |
| `rows` | Số hàng ước lượng cần đọc/xét ở bước truy cập bảng |
| `filtered` | Tỷ lệ phần trăm hàng ước lượng còn lại sau điều kiện lọc tại bước đó |
| `Extra` | Thông tin bổ sung như `Using where`, `Using index`, `Using temporary`, `Using filesort` |

Ước lượng số hàng truyền sang bước sau có thể hình dung gần đúng bằng:

```text
estimated_output_rows ~= rows * filtered / 100
```

Đây là phép đọc gần đúng cho một bước trong traditional EXPLAIN. Với join nhiều bảng, mỗi bước có ngữ cảnh và ước lượng riêng; không nhân các con số một cách máy móc nếu chưa hiểu access path.

### 11.1. Rows lớn không tự động là xấu

Nếu query cần trả 80% bảng, đọc nhiều hàng có thể là điều không tránh được. Một table scan tuần tự đôi khi rẻ hơn hàng trăm nghìn random lookups qua secondary index.

Ngược lại, nếu query chỉ cần 10 hàng nhưng `rows` ước lượng hàng trăm nghìn, cần điều tra predicate, index, kiểu dữ liệu, thống kê và cách optimizer đánh giá selectivity.

### 11.2. Filtered thấp có thể chỉ ra điều kiện lọc sau access

Nếu `rows = 100000` và `filtered = 1.00`, optimizer ước lượng chỉ khoảng 1.000 hàng còn lại sau filter. Nếu một index tốt có thể đưa predicate chọn lọc vào access condition, query có thể giảm số hàng phải đọc. Tuy nhiên, một số điều kiện không thể dùng index trực tiếp hoặc việc dùng index không rẻ hơn scan.

## 12. Đọc cost trong EXPLAIN FORMAT=JSON và TREE

`EXPLAIN FORMAT=JSON` cung cấp thông tin chi tiết hơn về từng query block và cost:

```sql
EXPLAIN FORMAT=JSON
SELECT id, customer_id, amount
FROM optimizer_lab
WHERE customer_id = 42
  AND created_at >= '2026-02-01';
```

Trong output JSON, tùy kế hoạch có thể thấy:

- `rows_examined_per_scan`: số hàng ước lượng mỗi lần scan.
- `rows_produced_per_join`: số hàng ước lượng sau điều kiện ở bước join.
- `filtered`: tỷ lệ hàng được giữ lại.
- `read_cost`: chi phí đọc ước lượng.
- `eval_cost`: chi phí đánh giá điều kiện ước lượng.
- `prefix_cost`: cost tích lũy tới bước đó.
- `data_read_per_join`: lượng dữ liệu đọc ước lượng.

`EXPLAIN FORMAT=TREE` biểu diễn kế hoạch theo cấu trúc cây, thuận tiện để thấy thứ tự operator và các phép join:

```sql
EXPLAIN FORMAT=TREE
SELECT c.customer_id, COUNT(*) AS order_count
FROM optimizer_lab AS c
JOIN optimizer_lab AS d
    ON d.customer_id = c.customer_id
WHERE c.status = 'OPEN'
GROUP BY c.customer_id;
```

Ví dụ self-join chỉ nhằm minh họa hình dạng kế hoạch; không phải mẫu truy vấn nghiệp vụ được khuyến nghị. Với truy vấn thực tế, xem operator nào đọc nhiều hàng và số hàng trung gian tăng ở đâu.

Cost của các bước thường tích lũy. Không so sánh cost từ hai server khác phiên bản/cấu hình như một phép benchmark tuyệt đối. Dùng cost để hiểu quyết định của optimizer trong cùng môi trường, sau đó kiểm chứng bằng actual execution.

## 13. EXPLAIN ANALYZE: so sánh ước lượng với thực tế

`EXPLAIN ANALYZE` chạy truy vấn và bổ sung số liệu thực tế như thời gian, số hàng và số vòng lặp. Đây là công cụ quan trọng để xác định sai lệch cardinality/selectivity.

```sql
EXPLAIN ANALYZE
SELECT id, customer_id, amount
FROM optimizer_lab
WHERE status = 'OPEN';
```

Output dạng TREE có thể chứa:

- `cost=... rows=...`: ước lượng của optimizer.
- `actual time=first..last`: thời gian thực tế từ lúc bắt đầu tới khi tạo hàng đầu và hoàn tất operator, thường hiển thị theo ms.
- `rows=...`: số hàng thực tế operator trả về trung bình mỗi loop.
- `loops=...`: số lần operator được thực hiện.

Khi so sánh, hãy xem cả rows và loops. Một operator trả 10 hàng mỗi loop nhưng chạy 10.000 loops có thể tạo ra lượng công việc lớn. Thời gian `actual` cũng bao gồm ảnh hưởng của cache, CPU, I/O, concurrency và trạng thái hệ thống tại thời điểm đo.

**Lưu ý:** `EXPLAIN ANALYZE` thực thi truy vấn thật. Dùng với SELECT có phạm vi giới hạn trong môi trường phù hợp; không coi nó như một lệnh chỉ đọc metadata. Tránh chạy trực tiếp trên truy vấn quá nặng trong giờ cao điểm.

### 13.1. Đọc sai lệch estimate

Ví dụ minh họa:

| Operator | Estimated rows | Actual rows | Nhận xét |
| --- | ---: | ---: | --- |
| Index range scan | 100 | 95 | Ước lượng gần thực tế |
| Filter status | 50 | 2 | Optimizer đánh giá selectivity quá cao |
| Join lookup | 5.000 | 180 | Sai lệch được khuếch đại qua join |

Đây là số liệu giả lập để giải thích cách đọc. Khi estimate thấp hơn actual nhiều lần, optimizer có thể chọn nested-loop join hoặc thứ tự join không phù hợp. Khi estimate cao hơn actual nhiều lần, optimizer có thể chọn scan/sort/materialization không cần thiết.

Đừng chỉ nhìn operator cuối. Tìm operator đầu tiên có chênh lệch lớn; sai lệch ở bước sớm có thể lan sang mọi bước phía trên.

## 14. Optimizer trace: tìm lý do một kế hoạch được chọn

Khi EXPLAIN cho thấy kế hoạch bất ngờ, optimizer trace có thể cho biết các phương án và lý do bị loại hoặc được chọn.

```sql
SET optimizer_trace = 'enabled=on';

SELECT id, customer_id, amount
FROM optimizer_lab
WHERE customer_id = 42
  AND created_at >= '2026-02-01';

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE\G

SET optimizer_trace = 'enabled=off';
```

Trace có thể chứa thông tin về:

- Range analysis và các range scan candidate.
- Ước lượng số hàng của từng access path.
- Cost dự kiến của table scan và index access.
- Join order candidate và lý do chọn/thay thế.
- Predicate được đẩy xuống hoặc đánh giá ở bước nào.

Optimizer trace khá dài và phụ thuộc phiên bản. Bật trong session phục vụ điều tra, đọc đúng trace của statement vừa chạy rồi tắt. Không bật toàn cục cho mọi session chỉ để xem một query.

## 15. Những giới hạn của thống kê và ước lượng

Thống kê không phải bản sao đầy đủ của dữ liệu. Một số giới hạn thường gặp:

### 15.1. Sampling và dữ liệu lệch

InnoDB thường lấy mẫu page để ước lượng cardinality. Nếu dữ liệu phân bố không đều giữa các page, sample nhỏ có thể bỏ lỡ vùng chứa giá trị hiếm hoặc giá trị tập trung. Tăng sample pages có thể cải thiện độ ổn định nhưng tốn thêm I/O và thời gian tính thống kê.

### 15.2. Data skew

Một cột có 10 giá trị nhưng một giá trị chiếm 99% khiến giả định phân bố đều không phù hợp. Histogram có thể giúp optimizer nhận ra skew trên từng cột, nhưng bucket hữu hạn vẫn là xấp xỉ.

### 15.3. Correlation giữa nhiều cột

Histogram đơn cột không mô tả đầy đủ quan hệ giữa `status` và `region`, hoặc giữa `tenant_id` và `created_at`. Ước lượng nhiều predicate kết hợp có thể sai nếu optimizer giả định các điều kiện độc lập.

### 15.4. Thống kê cũ

Sau bulk load, archive hoặc thay đổi mạnh phân bố, persistent stats/histogram có thể không còn phản ánh dữ liệu hiện tại. Tự động recalc có thể không xảy ra ngay lập tức. Cần lên lịch `ANALYZE TABLE` khi phù hợp.

### 15.5. Predicate khó ước lượng

Các điều kiện dùng hàm, biểu thức, implicit conversion, JSON path, chuỗi pattern hoặc toán tử phức tạp có thể khó ước lượng hơn so với equality/range predicate đơn giản trên cột có thống kê.

Ví dụ:

```sql
WHERE DATE(created_at) = '2026-11-19'
```

Biểu thức bọc cột có thể ngăn range access trên index `created_at`. Viết lại thành khoảng thời gian thường dễ tận dụng index hơn:

```sql
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00'
```

### 15.6. Cost model không biết toàn bộ trạng thái runtime

Cost estimate không thể dự đoán chính xác mọi yếu tố tức thời như cache đang nóng/lạnh, storage latency biến động, CPU contention, lock wait, network, workload đồng thời hoặc dữ liệu bị thay đổi ngay sau khi thống kê được thu thập.

Do đó, kế hoạch có cost thấp hơn không bảo đảm latency thực tế luôn thấp hơn trong mọi tình huống.

## 16. Quy trình điều tra khi optimizer ước lượng sai

Khi một query chậm hoặc chọn access path bất ngờ, đi theo thứ tự:

1. **Xác nhận query và dữ liệu:** predicate thực tế, parameter, số hàng bảng, phân bố giá trị và kết quả mong muốn.
2. **Đọc EXPLAIN:** xác định access path, index, join order, `rows`, `filtered`, sort và temporary work.
3. **Đo actual:** dùng `EXPLAIN ANALYZE` trên SELECT có phạm vi phù hợp; tìm operator đầu tiên estimate lệch lớn.
4. **Kiểm tra thống kê:** `SHOW INDEX`, persistent stats, last update và histogram.
5. **Làm mới có chủ đích:** chạy `ANALYZE TABLE` hoặc cập nhật histogram nếu dữ liệu đã thay đổi.
6. **Kiểm tra index:** thứ tự cột, leftmost prefix, covering, selectivity và số row lookup.
7. **Kiểm tra correlation:** nếu nhiều predicate liên quan, xem composite index hoặc thay đổi query/model.
8. **Xem optimizer trace:** khi cần biết vì sao một candidate bị loại hoặc cost được tính ra sao.
9. **Đo lại:** so sánh plan, actual rows, latency và tài nguyên trước/sau.

Không thêm index, ép `FORCE INDEX` hoặc thay cost model ngay từ đầu. Trước hết xác định sai lệch nằm ở thống kê, predicate, index hay runtime bottleneck.

## 17. Khi nào nên dùng FORCE INDEX?

Optimizer hints như `FORCE INDEX` có thể hữu ích khi đã chứng minh optimizer liên tục chọn access path kém trong một workload cụ thể và các phương án thống kê/index hợp lý không giải quyết được.

Ví dụ cú pháp:

```sql
SELECT id, customer_id, amount
FROM optimizer_lab FORCE INDEX (idx_optimizer_customer_date)
WHERE customer_id = 42;
```

Không dùng hint chỉ vì một lần EXPLAIN có `type = ALL`. Table scan có thể là lựa chọn đúng nếu query cần phần lớn dữ liệu hoặc index lookup tốn hơn. Hint có thể trở nên sai khi dữ liệu lớn lên, phân bố thay đổi hoặc phiên bản MySQL thay đổi.

Trước khi giữ hint:

- So sánh `EXPLAIN ANALYZE` có và không có hint.
- Kiểm tra nhiều giá trị predicate đại diện, không chỉ một giá trị thuận lợi.
- Xác nhận thống kê đã cập nhật.
- Ghi nhận lý do và điều kiện cần xem xét lại hint.

## 18. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi `SHOW INDEX.Cardinality` là số chính xác | Dự đoán sai số hàng khớp | Nhớ đây là ước lượng dựa trên thống kê/sampling |
| Đồng nhất cardinality với predicate selectivity | Hiểu sai phân bố giá trị | Phân biệt distinct count và tỷ lệ hàng thỏa predicate |
| Nghĩ cardinality cao thì index luôn tốt | Ép dùng index dù query đọc gần hết bảng | Đánh giá số hàng khớp và row lookup |
| Nghĩ cardinality thấp thì index vô dụng | Bỏ qua giá trị hiếm trong cột skew | Xem histogram và predicate cụ thể |
| Nghĩ cost là mili giây | So sánh sai giữa server hoặc kế hoạch | Dùng cost để hiểu lựa chọn; dùng ANALYZE để đo actual |
| Bỏ qua `filtered` | Không thấy lượng hàng bị loại sau access | Đọc cùng `rows` và output rows ước lượng |
| Không cập nhật stats sau bulk load | Optimizer dùng phân bố cũ | Chạy `ANALYZE TABLE` có chủ đích |
| Tăng sample pages cho mọi bảng | Tăng chi phí thu thập stats không cần thiết | Chỉ điều chỉnh bảng có estimate thiếu ổn định |
| Nghĩ histogram mô tả correlation nhiều cột | Ước lượng AND/join vẫn sai | Đánh giá composite index và tương quan dữ liệu |
| Chạy EXPLAIN ANALYZE trên query nặng trong production | Query thật gây tải | Giới hạn dữ liệu, dùng môi trường phù hợp và đánh giá rủi ro |
| Ép FORCE INDEX quá sớm | Kế hoạch dễ lỗi thời khi dữ liệu thay đổi | Sửa stats/index/query trước, hint chỉ khi có bằng chứng |

## 19. Bài tập thực hành

1. Tạo fixture ở phần 6. Dùng `COUNT(DISTINCT ...)` để đo cardinality thật của `customer_id`, `status`, `region`.
2. Chạy `ANALYZE TABLE` và `SHOW INDEX`. So sánh cardinality ước lượng với số distinct chính xác.
3. Tạo index ghép `(customer_id, created_at)`. Giải thích ý nghĩa cardinality của từng prefix và leftmost prefix.
4. So sánh `EXPLAIN` của `status = 'OPEN'` và `status = 'CLOSED'` trước khi tạo histogram.
5. Tạo histogram trên `status`, xem `INFORMATION_SCHEMA.COLUMN_STATISTICS`, rồi so sánh ước lượng.
6. Tạo index trên `status`; quan sát optimizer có thể chọn index cho `OPEN` và scan cho `CLOSED` tùy cost.
7. Viết predicate kết hợp `status` và `region`. So sánh estimate với actual và giải thích ảnh hưởng correlation.
8. Chạy `EXPLAIN FORMAT=JSON`, tìm `rows_examined_per_scan`, `rows_produced_per_join`, `read_cost`, `eval_cost` và `prefix_cost`.
9. Chạy `EXPLAIN ANALYZE` cho SELECT giới hạn. Tìm operator đầu tiên có estimated rows khác xa actual rows.
10. Bật optimizer trace trong session, chạy một truy vấn và xác định lý do một access path được chọn.
11. Thay đổi phân bố dữ liệu trong lab, chạy lại `ANALYZE TABLE`, histogram và EXPLAIN. Viết nhận xét trước/sau.
12. Thử `FORCE INDEX` trong lab và so sánh actual runtime với kế hoạch mặc định trên nhiều giá trị predicate.

## 20. Checklist trước khi kết luận optimizer chọn sai kế hoạch

- [ ] Đã xác nhận số hàng và phân bố dữ liệu hiện tại.
- [ ] Đã phân biệt cardinality với predicate selectivity.
- [ ] Đã kiểm tra index và cardinality từng prefix.
- [ ] Đã kiểm tra persistent stats, sample pages và thời điểm cập nhật.
- [ ] Đã cân nhắc `ANALYZE TABLE` sau thay đổi dữ liệu lớn.
- [ ] Đã xem histogram cho cột skew nếu phù hợp.
- [ ] Đã đánh giá correlation giữa các predicate và giới hạn histogram đơn cột.
- [ ] Đã đọc `rows`, `filtered`, access type, key và join order trong EXPLAIN.
- [ ] Đã hiểu cost là đơn vị tương đối, không phải thời gian thực tế.
- [ ] Đã so sánh estimate với actual rows/loops bằng EXPLAIN ANALYZE an toàn.
- [ ] Đã tìm operator đầu tiên có sai lệch lớn thay vì chỉ nhìn tổng thời gian.
- [ ] Đã dùng optimizer trace khi cần giải thích lựa chọn của optimizer.
- [ ] Chỉ dùng optimizer hint sau khi đã đo và ghi nhận lý do.
- [ ] Đã đo lại kế hoạch và latency sau mỗi thay đổi.

## 21. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích cardinality của index và index prefix, tính selectivity của predicate từ dữ liệu, phân biệt distinct-value fraction với tỷ lệ hàng khớp, mô tả cách cost model so sánh kế hoạch, đọc được `rows`/`filtered`/cost trong EXPLAIN, cập nhật persistent statistics và histogram, rồi dùng `EXPLAIN ANALYZE` để tìm sai lệch giữa ước lượng và thực tế. Bạn cũng cần nêu được giới hạn do sampling, skew, correlation, thống kê cũ và trạng thái runtime.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Optimizer Statistics](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html)
- [MySQL 8.4 Reference Manual — InnoDB Persistent Statistics](https://dev.mysql.com/doc/refman/8.4/en/innodb-persistent-stats.html)
- [MySQL 8.4 Reference Manual — Optimizer Cost Model](https://dev.mysql.com/doc/refman/8.4/en/cost-model.html)
- [MySQL 8.4 Reference Manual — Optimizer Trace](https://dev.mysql.com/doc/refman/8.4/en/optimizer-tracing.html)
- [MySQL 8.4 Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual — ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)

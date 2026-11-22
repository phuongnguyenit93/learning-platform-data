# Độ lệch dữ liệu, tương quan giữa các cột và lỗi ước lượng

MySQL optimizer phải ước lượng số hàng sẽ đi qua từng bước của truy vấn trước khi chọn index, thứ tự JOIN, cách lọc và cách kết hợp bảng. Ước lượng này dựa trên thống kê bảng, thống kê index, histogram và các quy tắc của optimizer. Khi dữ liệu phân bố lệch hoặc các cột có tương quan với nhau, ước lượng có thể sai đáng kể so với số hàng thực tế.

Một kế hoạch có ước lượng sai có thể chọn thứ tự JOIN không phù hợp, lặp nhiều lần việc dò bảng trong, đọc quá nhiều hàng hoặc dùng một index kém hiệu quả. Cách xử lý là đo số hàng thực tế, kiểm tra chất lượng thống kê, cập nhật histogram khi phù hợp, thiết kế composite index cho các điều kiện thường đi cùng nhau và xác minh lại bằng `EXPLAIN ANALYZE`.

## 1. Vì sao optimizer cần thống kê?

SQL mô tả kết quả cần lấy, còn optimizer quyết định cách thực thi. Với truy vấn nhiều bảng, có thể tồn tại nhiều thứ tự JOIN và nhiều access path khác nhau. Optimizer ước lượng chi phí dựa trên số hàng cần đọc, số hàng còn lại sau điều kiện lọc, chi phí truy cập index/table và các thao tác như sort hoặc materialization.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(150) NOT NULL,
    region_code CHAR(2) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status (status)
) ENGINE=InnoDB;

SELECT c.customer_id, c.customer_name, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'failed'
  AND c.region_code = 'VN';
```

Optimizer cần ước lượng có bao nhiêu đơn hàng `failed`, có bao nhiêu khách hàng ở `VN`, mỗi khách hàng có bao nhiêu đơn và thứ tự nào giúp giảm tổng công việc. Nếu nó nghĩ `failed` chiếm 40% bảng trong khi thực tế chỉ chiếm 0,1%, lựa chọn join order có thể không phù hợp.

Thống kê không phải dữ liệu chính xác thay thế truy vấn. Chúng là thông tin tóm tắt để optimizer dự đoán chi phí mà không phải đếm toàn bộ bảng trước mỗi câu SQL.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Cardinality | Số giá trị phân biệt hoặc số hàng tùy ngữ cảnh thống kê | Một cột `status` có 4 giá trị phân biệt |
| Selectivity | Tỷ lệ hàng thỏa một điều kiện | `status = 'failed'` chỉ khớp 0,1% hàng |
| Data skew | Phân bố giá trị không đồng đều | 99% bản ghi có `status = 'active'` |
| Correlation | Phân bố của một cột phụ thuộc vào giá trị cột khác | Hầu hết tài khoản ở `VN` dùng gói `free` |
| Estimate error | Chênh lệch giữa số hàng optimizer dự đoán và số hàng thực tế | Ước lượng 100.000 hàng nhưng thực tế chỉ 50 |

Cardinality cao không đồng nghĩa điều kiện luôn chọn lọc tốt; còn phải xét giá trị cụ thể và phân bố. Một cột có 2 giá trị có thể rất lệch (99,9%/0,1%) hoặc cân bằng (50%/50%). Thống kê chỉ có cardinality đơn giản sẽ không mô tả đủ hai trường hợp này.

## 3. Data skew: phân bố giá trị lệch

Giả sử bảng `subscription_events` có 1 triệu hàng:

| status | Số hàng | Tỷ lệ |
| --- | ---: | ---: |
| `active` | 940.000 | 94% |
| `expired` | 50.000 | 5% |
| `pending` | 9.000 | 0,9% |
| `failed` | 1.000 | 0,1% |

Điều kiện `status = 'active'` trả về phần lớn bảng; `status = 'failed'` chỉ trả về một phần rất nhỏ. Nếu optimizer giả định các giá trị phân bố gần đồng đều, nó có thể ước lượng sai selectivity của từng giá trị.

Độ lệch thường xuất hiện ở:

- Trạng thái đơn hàng, thanh toán hoặc công việc.
- Mã tenant, quốc gia, khu vực hoặc nhóm khách hàng.
- Cờ boolean như `is_deleted`, `is_active`.
- Ngày tháng khi dữ liệu mới tập trung ở một khoảng thời gian gần đây.
- Một số khóa ngoại có số hàng con rất lớn, trong khi phần lớn khóa khác chỉ có vài hàng.

Điều kiện trên giá trị hiếm có thể rất chọn lọc, còn điều kiện trên giá trị phổ biến có thể khiến full table scan rẻ hơn index lookup. Không nên ép optimizer dùng index chỉ vì cột đó có index.

## 4. Correlation: tương quan giữa các cột

Hai cột có tương quan khi phân bố của cột này thay đổi theo giá trị cột kia. Ví dụ:

- Ở khu vực `VN`, phần lớn người dùng dùng gói `free`.
- Ở khu vực `US`, phần lớn người dùng dùng gói `enterprise`.
- Các đơn hàng `failed` tập trung ở một số kênh thanh toán.

Xét truy vấn:

```sql
SELECT COUNT(*)
FROM subscriptions
WHERE region_code = 'VN'
  AND plan_type = 'free';
```

Nếu optimizer ước lượng selectivity của `region_code` và `plan_type` như hai điều kiện độc lập, nó có thể kết hợp các tỷ lệ riêng lẻ theo một giả định gần với độc lập. Khi hai cột tương quan mạnh, kết quả thực tế có thể khác xa phép ước lượng đó.

Histogram chuẩn của MySQL mô tả phân bố **một cột tại một thời điểm**. Histogram của `region_code` không chứa thông tin rằng `VN` thường đi cùng `free`; histogram của `plan_type` cũng không lưu mối quan hệ đó. Vì vậy, hai histogram đơn cột vẫn có thể không giải quyết được lỗi ước lượng do tương quan.

## 5. Tạo bảng thực hành có skew và correlation

Tạo bảng mẫu để kiểm tra điều kiện lọc trên trạng thái, khu vực và loại gói:

```sql
CREATE TABLE subscriptions (
    subscription_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    region_code CHAR(2) NOT NULL,
    plan_type VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (subscription_id),
    KEY idx_subscriptions_customer (customer_id),
    KEY idx_subscriptions_created (created_at)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Giả sử dữ liệu được nạp với phân bố như sau:

- `status = 'active'` chiếm khoảng 94%; `failed` chỉ chiếm khoảng 0,1%.
- `region_code = 'VN'` thường đi cùng `plan_type = 'free'`.
- `region_code = 'US'` thường đi cùng `plan_type = 'enterprise'`.
- Các tổ hợp còn lại xuất hiện ít hơn.

Có thể nạp dữ liệu đại diện bằng ETL hoặc script tạo dữ liệu trong môi trường lab. Điều quan trọng là dữ liệu phải có đủ hàng và giữ được phân bố lệch/tương quan để quan sát estimate; vài hàng mẫu không đủ tạo ra thống kê có ý nghĩa.

Đếm số hàng thực tế trước khi phân tích:

```sql
SELECT status, COUNT(*) AS row_count
FROM subscriptions
GROUP BY status
ORDER BY row_count DESC;

SELECT region_code, plan_type, COUNT(*) AS row_count
FROM subscriptions
GROUP BY region_code, plan_type
ORDER BY row_count DESC;
```

Các truy vấn `COUNT(*)` này đo dữ liệu hiện có. Chúng là baseline để so sánh với ước lượng của optimizer, không phải cách optimizer phải chạy trước mọi truy vấn production.

## 6. Thống kê index của InnoDB

InnoDB duy trì thống kê về bảng và index, bao gồm ước lượng số hàng, số giá trị phân biệt của các prefix index và phân bố key. Optimizer dùng các thống kê này để ước lượng chi phí access path.

Kiểm tra index:

```sql
SHOW INDEX FROM subscriptions;
```

Các cột đáng chú ý:

- `Key_name`: tên index.
- `Seq_in_index`: vị trí cột trong index ghép.
- `Column_name`: cột thuộc index.
- `Cardinality`: ước lượng số giá trị phân biệt của prefix index tương ứng.
- `Sub_part`: độ dài prefix nếu index chỉ một phần giá trị.

`Cardinality` là ước lượng thống kê, không phải phép đếm chính xác mọi giá trị trong bảng. Với index ghép `(a, b)`, thống kê prefix giúp mô tả số giá trị phân biệt của `(a)` và `(a, b)` theo cách InnoDB lưu thống kê index.

Thống kê InnoDB có thể là persistent hoặc transient tùy cấu hình. Kiểm tra các biến liên quan:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

Persistent statistics được lưu để optimizer có thông tin ổn định hơn qua lần khởi động. Việc lấy mẫu page giúp giới hạn chi phí phân tích nhưng cũng có nghĩa thống kê là ước lượng; dữ liệu lệch mạnh hoặc mẫu không đại diện có thể khiến cardinality chưa chính xác.

## 7. ANALYZE TABLE để cập nhật thống kê index

Sau bulk load, xóa nhiều dữ liệu hoặc thay đổi phân bố lớn, thống kê index cũ có thể không còn đại diện. Dùng:

```sql
ANALYZE TABLE subscriptions;
```

Lệnh này yêu cầu MySQL phân tích lại bảng và cập nhật key distribution statistics dùng cho optimizer. Sau đó, kiểm tra lại:

```sql
SHOW INDEX FROM subscriptions;
```

`ANALYZE TABLE` không sửa dữ liệu nghiệp vụ và không thay thế `OPTIMIZE TABLE`. Nó cập nhật thống kê; nó không bảo đảm mọi estimate sẽ chính xác, đặc biệt khi lỗi xuất phát từ tương quan nhiều cột mà thống kê đơn cột không mô tả được.

Với InnoDB, thống kê dựa trên sampling. Nếu kết quả ước lượng dao động hoặc không đại diện, có thể đánh giá số sample page phù hợp, nhưng tăng sampling cũng làm ANALYZE tốn thời gian hơn. Chỉ thay đổi cấu hình sau khi đo và hiểu tác động.

## 8. Histogram trong MySQL

MySQL 8.0 hỗ trợ histogram statistics để mô tả phân bố giá trị của một cột. Histogram đặc biệt hữu ích khi optimizer cần ước lượng điều kiện lọc trên cột không có index. Với cột có index, optimizer còn có thống kê index và các ước lượng từ range optimizer; không nên giả định histogram luôn được ưu tiên hoặc luôn thay thế thống kê index.

Hai loại histogram chính:

| Loại | Cách biểu diễn | Phù hợp với |
| --- | --- | --- |
| Singleton | Mỗi giá trị phân biệt được mô tả bằng bucket riêng | Cột có ít giá trị phân biệt |
| Equi-height | Mỗi bucket đại diện một khoảng giá trị với số lượng hàng gần tương đương | Cột có nhiều giá trị phân biệt |

Histogram lưu thông tin như loại histogram, số bucket, tỷ lệ NULL, khoảng giá trị và tần suất ước lượng. Nó giúp optimizer hiểu rằng `failed` hiếm trong khi `active` phổ biến, thay vì coi mọi giá trị có xác suất như nhau.

Histogram là thống kê ước lượng. Bucket count, sampling, kiểu dữ liệu và phân bố thay đổi theo thời gian đều ảnh hưởng chất lượng.

## 9. Tạo histogram cho cột lệch

Tạo histogram cho `status`:

```sql
ANALYZE TABLE subscriptions
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

Với cột chỉ có vài trạng thái, MySQL có thể tạo singleton histogram nếu số giá trị phân biệt phù hợp với số bucket. `WITH 32 BUCKETS` là số bucket tối đa được yêu cầu cho histogram này; không có nghĩa kết quả bắt buộc luôn có đúng 32 bucket.

Có thể tạo histogram cho nhiều cột:

```sql
ANALYZE TABLE subscriptions
UPDATE HISTOGRAM ON status, region_code, plan_type
WITH 100 BUCKETS;
```

Mỗi histogram vẫn mô tả một cột riêng. Lệnh trên không tạo histogram đa chiều cho tổ hợp `region_code` và `plan_type`.

Kiểm tra histogram:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'subscriptions';
```

`HISTOGRAM` là JSON. Có thể xem trực tiếp hoặc trích xuất trường cần thiết bằng JSON functions để kiểm tra loại histogram, bucket và thời điểm cập nhật.

## 10. Cập nhật và xóa histogram

Histogram không tự phản ánh mọi thay đổi dữ liệu ngay lập tức. Khi phân bố thay đổi đáng kể, hãy cập nhật lại:

```sql
ANALYZE TABLE subscriptions
UPDATE HISTOGRAM ON status WITH 32 BUCKETS;
```

Nếu histogram không còn hữu ích hoặc muốn quay về ước lượng dựa trên thống kê khác:

```sql
ANALYZE TABLE subscriptions
DROP HISTOGRAM ON status;
```

Việc tạo/xóa histogram làm thay đổi thông tin optimizer dùng để ước lượng; kế hoạch truy vấn có thể thay đổi sau đó. Hãy kiểm tra các truy vấn quan trọng bằng `EXPLAIN` và đo lại trước/sau khi thay đổi.

Không cần cập nhật histogram liên tục sau mỗi insert. Chọn lịch cập nhật dựa trên tốc độ thay đổi dữ liệu, mức độ lệch và các truy vấn phụ thuộc vào cột đó.

## 11. Histogram không giải quyết đầy đủ correlation

Giả sử dữ liệu có phân bố:

| region_code | plan_type | Tỷ trọng minh họa |
| --- | --- | ---: |
| VN | free | 70% |
| VN | enterprise | 2% |
| US | free | 3% |
| US | enterprise | 20% |
| Khác | Các gói còn lại | 5% |

Histogram đơn cột có thể mô tả tỷ lệ `VN` và tỷ lệ `free`, nhưng không trực tiếp lưu tỷ lệ của tổ hợp `VN + free`. Nếu optimizer kết hợp hai selectivity theo giả định gần độc lập, estimate có thể lệch vì `VN` và `free` tương quan.

MySQL không cung cấp histogram đa cột tổng quát để lưu phân bố có điều kiện cho mọi tổ hợp cột. Do đó, khi nhiều điều kiện tương quan, cần kết hợp các cách sau:

- Dùng composite index cho các tổ hợp điều kiện xuất hiện thường xuyên.
- Kiểm tra thống kê prefix của composite index.
- Viết truy vấn theo access pattern phù hợp, tránh áp dụng hàm lên cột lọc nếu không cần.
- Tách hoặc chuẩn hóa dữ liệu nếu mô hình hiện tại tạo ra phân bố khó ước lượng và truy vấn quá phức tạp.
- Đo actual rows bằng `EXPLAIN ANALYZE`; không cố ép optimizer dựa trên một histogram đơn cột để mô tả quan hệ nhiều cột.

## 12. Composite index giúp điều kiện kết hợp

Nếu truy vấn thường lọc đồng thời `region_code` và `plan_type`, có thể đánh giá index ghép:

```sql
CREATE INDEX idx_subscriptions_region_plan
ON subscriptions (region_code, plan_type);
```

Index này hỗ trợ truy vấn:

```sql
SELECT subscription_id, customer_id, status
FROM subscriptions
WHERE region_code = 'VN'
  AND plan_type = 'free';
```

Thống kê index ghép có thông tin cardinality cho các prefix của index. Điều này có thể giúp optimizer ước lượng và truy cập tốt hơn cho các điều kiện phù hợp với thứ tự cột.

Thứ tự cột rất quan trọng vì quy tắc leftmost prefix:

- `(region_code, plan_type)` hỗ trợ điều kiện chỉ lọc `region_code` hoặc lọc cả hai cột theo thứ tự.
- Nó không phải lựa chọn tương đương cho truy vấn chỉ lọc `plan_type`.
- Nếu workload chủ yếu bắt đầu từ `plan_type`, cần đánh giá thứ tự `(plan_type, region_code)`.

Composite index không phải histogram đa chiều cho mọi truy vấn. Nó cung cấp access path và thống kê prefix hữu ích cho các cột trong index, nhưng không mô tả mọi tương quan có điều kiện, biểu thức hoặc tổ hợp tùy ý. Chỉ tạo index theo truy vấn thật và đo tác động ghi/lưu trữ.

## 13. So sánh ước lượng và số hàng thực tế

`EXPLAIN` hiển thị kế hoạch dự kiến và các ước lượng. Ví dụ:

```sql
EXPLAIN
SELECT subscription_id, customer_id
FROM subscriptions
WHERE status = 'failed'
  AND region_code = 'VN';
```

Trong output dạng bảng, các trường quan trọng gồm:

- `rows`: số hàng optimizer ước lượng cần đọc ở bước đó.
- `filtered`: tỷ lệ phần trăm hàng dự kiến còn lại sau điều kiện lọc.
- `key`: index được chọn.
- `type`: access method như `const`, `eq_ref`, `ref`, `range`, `index`, `ALL`.
- `Extra`: thông tin bổ sung như `Using where`, `Using index`, `Using temporary` hoặc `Using filesort`.

Trong `EXPLAIN FORMAT=JSON`, có thể xem chi tiết hơn như `rows_examined_per_scan`, `rows_produced_per_join`, `filtered` và `cost_info` tùy cấu trúc query block.

Ước lượng `rows` không phải số hàng cuối cùng chắc chắn trả về. Nó mô tả chi phí/khối lượng dự kiến ở một bước thực thi. Khi so sánh với actual rows, hãy đối chiếu đúng iterator và số vòng lặp.

## 14. EXPLAIN ANALYZE: kiểm tra actual rows và loops

MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE` cho truy vấn đọc. Lệnh này thực thi truy vấn và báo thời gian, số hàng thực tế cùng số vòng lặp của các iterator:

```sql
EXPLAIN ANALYZE
SELECT subscription_id, customer_id
FROM subscriptions
WHERE status = 'failed'
  AND region_code = 'VN';
```

Output dạng tree có thể hiển thị các thông tin như:

- `estimated rows`: số hàng optimizer dự đoán.
- `actual time`: thời gian thực tế của iterator.
- `actual rows`: số hàng iterator thực sự xử lý/trả ra.
- `loops`: số lần iterator được gọi.

Nếu một iterator ước lượng 100.000 hàng nhưng thực tế chỉ có 20, hoặc ngược lại, chênh lệch lớn có thể ảnh hưởng lựa chọn join order và thuật toán. Với iterator lặp nhiều lần, cần xem cả `rows` và `loops`; một lượng nhỏ hàng mỗi lần nhưng hàng nghìn vòng lặp vẫn có thể tốn kém.

`EXPLAIN ANALYZE` thực sự chạy truy vấn. Dùng với `SELECT` an toàn trên môi trường phù hợp, giới hạn dữ liệu và tải khi cần. Không coi nó là phép đo miễn phí hoặc chỉ là explain tĩnh.

## 15. Nhận diện lỗi ước lượng qua kế hoạch JOIN

Giả sử truy vấn nối `customers` và `subscriptions`:

```sql
EXPLAIN ANALYZE
SELECT c.customer_id, s.subscription_id
FROM customers AS c
JOIN subscriptions AS s
  ON s.customer_id = c.customer_id
WHERE s.status = 'failed'
  AND s.region_code = 'VN';
```

Một số dấu hiệu đáng điều tra:

- Optimizer dự đoán tập đầu vào lớn nhưng thực tế rất nhỏ, dẫn đến chọn sai bảng bắt đầu.
- Một nested-loop iterator có `loops` rất lớn và mỗi lần dò bảng trong tốn chi phí.
- Bước lọc trả ra nhiều hàng hơn estimate nhiều lần, làm các bước sau xử lý khối lượng lớn hơn dự kiến.
- Một bảng bị quét toàn bộ dù điều kiện thực tế rất chọn lọc và có thể dùng index phù hợp.
- Sort/materialization xử lý nhiều hàng do điều kiện lọc được áp dụng muộn.

Không phải mọi `ALL` hay full scan đều xấu. Nếu điều kiện trả về phần lớn bảng hoặc bảng nhỏ, full scan có thể rẻ hơn nhiều lần lookup ngẫu nhiên. Cần xem actual rows, thời gian và workload, không đánh giá chỉ từ tên access method.

## 16. Optimizer trace để hiểu quyết định

Khi `EXPLAIN` chưa giải thích được vì sao optimizer chọn một access path hoặc join order, có thể dùng optimizer trace:

```sql
SET optimizer_trace = 'enabled=on';

SELECT subscription_id, customer_id
FROM subscriptions
WHERE status = 'failed'
  AND region_code = 'VN';

SELECT TRACE
FROM INFORMATION_SCHEMA.OPTIMIZER_TRACE;

SET optimizer_trace = 'enabled=off';
```

Trace là JSON chứa các bước optimizer cân nhắc, như range analysis, ước lượng chi phí, lựa chọn index và thứ tự JOIN. Nội dung có thể dài và phụ thuộc phiên bản; hãy lọc đúng phần liên quan thay vì đọc toàn bộ một cách máy móc.

Optimizer trace giúp giải thích quyết định dựa trên thống kê hiện có. Nó không tự sửa thống kê hay bảo đảm kế hoạch được chọn là tốt nhất trên mọi workload.

## 17. Quy trình xử lý estimate error

Khi nghi ngờ optimizer ước lượng sai, làm theo thứ tự:

1. **Tái hiện truy vấn:** giữ nguyên tham số, điều kiện, join và dữ liệu đại diện.
2. **Lấy kế hoạch:** chạy `EXPLAIN FORMAT=JSON` hoặc `EXPLAIN` để xem estimated rows, index và join order.
3. **Đo thực tế:** dùng `EXPLAIN ANALYZE` trên SELECT phù hợp để xem actual rows, loops và thời gian.
4. **Xác định nơi lệch:** tìm iterator đầu tiên có actual rows khác estimate đáng kể; lỗi ở bước sớm có thể lan sang toàn bộ kế hoạch.
5. **Kiểm tra phân bố:** đếm tần suất các giá trị, tìm skew và giá trị hiếm/phổ biến.
6. **Kiểm tra correlation:** xem các điều kiện nhiều cột có phụ thuộc nhau không; so sánh count từng cột với count tổ hợp.
7. **Kiểm tra thống kê index:** xem `SHOW INDEX`; nếu dữ liệu thay đổi nhiều, cân nhắc `ANALYZE TABLE`.
8. **Đánh giá histogram:** tạo hoặc cập nhật histogram đơn cột cho điều kiện phù hợp, nhất là cột không có index.
9. **Đánh giá composite index:** nếu truy vấn thường lọc theo nhiều cột tương quan, thử index ghép với thứ tự phù hợp.
10. **So sánh lại:** chạy cùng truy vấn và tham số, so sánh plan, actual rows, loops và thời gian trước/sau.
11. **Kiểm tra truy vấn liên quan:** một index hoặc histogram có thể cải thiện câu này nhưng làm thay đổi kế hoạch câu khác.
12. **Theo dõi sau triển khai:** phân bố dữ liệu tiếp tục thay đổi; cần lịch refresh và đo lại.

## 18. Khi nào dùng histogram, composite index hay query rewrite?

| Dấu hiệu | Hướng xử lý cần đánh giá | Giới hạn |
| --- | --- | --- |
| Cột không có index, giá trị lệch mạnh | Histogram đơn cột | Không mô tả tương quan với cột khác |
| Thống kê index cũ sau bulk load | `ANALYZE TABLE` | Vẫn là ước lượng và phụ thuộc sampling |
| Truy vấn thường lọc hai cột cùng lúc | Composite index | Thứ tự cột và leftmost prefix quan trọng |
| Nhiều điều kiện có tương quan mạnh | Composite index, query design và kiểm tra actual rows | Không có histogram đa chiều tổng quát |
| Điều kiện dùng hàm trên cột | Xem xét biểu thức sargable hoặc generated column/index phù hợp | Phải giữ nguyên ngữ nghĩa và chi phí ghi |
| Truy vấn chọn quá nhiều cột/LOB | Chỉ chọn cột cần thiết | Không giải quyết lỗi cardinality nhưng giảm I/O |
| Estimate sai ở bước JOIN đầu tiên | Sửa thống kê/access path và kiểm tra join order | Hint không nên là biện pháp đầu tiên |

## 19. Optimizer hints: chỉ dùng sau khi hiểu nguyên nhân

MySQL có optimizer hints và index hints để tác động đến lựa chọn thực thi. Tuy nhiên, ép index hoặc ép join order có thể giúp một tập dữ liệu hiện tại nhưng làm truy vấn tệ hơn khi dữ liệu thay đổi.

Trước khi dùng hint:

- Xác nhận estimate error bằng `EXPLAIN ANALYZE`.
- Kiểm tra thống kê index, histogram và correlation.
- Xác định hint tác động đúng query block và đúng phiên bản.
- Đo trên dữ liệu đại diện ở nhiều mức phân bố.
- Theo dõi kế hoạch sau khi dữ liệu tăng hoặc thay đổi.

Không thêm `FORCE INDEX` chỉ vì thấy optimizer chọn full scan. Full scan có thể là lựa chọn đúng nếu phần lớn hàng cần đọc. Hint nên là biện pháp có chủ đích, được đo và có tài liệu giải thích.

## 20. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Cardinality cao nghĩa mọi giá trị đều chọn lọc tốt | Phân bố có thể lệch mạnh dù cardinality cao | Kiểm tra tần suất từng giá trị và histogram |
| ANALYZE TABLE làm mọi estimate chính xác | Nó cập nhật thống kê index dựa trên sampling | Đo actual rows và kiểm tra skew/correlation |
| Histogram mô tả quan hệ giữa nhiều cột | Histogram MySQL là thống kê đơn cột | Dùng composite index và kiểm tra tổ hợp điều kiện |
| Tạo histogram là optimizer chắc chắn dùng nó | Optimizer chọn nguồn thống kê theo access path và điều kiện | So sánh plan trước/sau, xem trace khi cần |
| EXPLAIN rows là số hàng thực tế | Đây là ước lượng | Dùng EXPLAIN ANALYZE để đo actual rows |
| EXPLAIN ANALYZE chỉ hiển thị, không chạy query | Nó thực thi truy vấn | Chạy SELECT phù hợp trên môi trường an toàn |
| Full table scan luôn xấu | Có thể rẻ hơn index khi cần phần lớn bảng | Đánh giá selectivity, I/O và thời gian |
| Composite index là histogram đa chiều | Nó cung cấp access path và thống kê prefix, không mô tả mọi quan hệ điều kiện | Thiết kế theo workload và đo lại |
| Tăng số bucket luôn tốt | Histogram lớn hơn có chi phí và không sửa được correlation | Chọn bucket theo cardinality và chất lượng estimate |
| FORCE INDEX luôn sửa lỗi estimate | Hint có thể làm kế hoạch kém khi dữ liệu thay đổi | Chỉ dùng sau khi có bằng chứng và kiểm thử |

## 21. Bài tập thực hành

1. Tạo bảng `subscriptions` với phân bố `status` lệch mạnh; dùng `GROUP BY` đếm tần suất thực tế.
2. Chạy `EXPLAIN` cho `status = 'failed'` trước khi tạo histogram; ghi lại estimate và index được chọn.
3. Tạo histogram bằng `ANALYZE TABLE ... UPDATE HISTOGRAM`; kiểm tra `INFORMATION_SCHEMA.COLUMN_STATISTICS`.
4. Chạy lại `EXPLAIN` và `EXPLAIN ANALYZE`; so sánh estimate với actual rows.
5. Tạo dữ liệu có tương quan giữa `region_code` và `plan_type`; đếm từng cột và tổ hợp hai cột.
6. Tạo histogram riêng cho `region_code` và `plan_type`; quan sát vì sao chúng không mô tả đầy đủ phân bố tổ hợp.
7. Tạo composite index `(region_code, plan_type)`; so sánh access path và actual rows.
8. Đổi thứ tự cột trong index trên môi trường lab; kiểm tra leftmost prefix với truy vấn chỉ lọc một cột.
9. Sau bulk load hoặc thay đổi dữ liệu lớn, chạy `ANALYZE TABLE`; kiểm tra cardinality trong `SHOW INDEX`.
10. Dùng optimizer trace để xem optimizer cân nhắc index và join order.
11. Tạo một truy vấn JOIN có estimate sai; xác định iterator đầu tiên lệch nhiều giữa estimated và actual rows.
12. Chỉ sau khi đã đo, thử một optimizer hint trong lab và so sánh trên các phân bố dữ liệu khác nhau.

## 22. Ghi nhớ

Optimizer chọn kế hoạch dựa trên ước lượng số hàng và chi phí. Data skew khiến giá trị phổ biến/hiếm có selectivity rất khác nhau; correlation khiến selectivity của nhiều điều kiện không thể suy ra chính xác từ thống kê đơn cột. InnoDB duy trì thống kê index theo sampling; `ANALYZE TABLE` cập nhật key distribution, còn histogram MySQL 8.0 mô tả phân bố của từng cột bằng singleton hoặc equi-height buckets.

Histogram hữu ích cho skew trên một cột nhưng không phải histogram đa chiều. Với điều kiện nhiều cột tương quan, đánh giá composite index và thống kê prefix, đồng thời đo số hàng thực tế. `EXPLAIN` cho biết estimate; `EXPLAIN ANALYZE` thực thi SELECT và cho actual rows, loops, thời gian. Hãy tìm iterator đầu tiên có estimate lệch, kiểm tra phân bố, cập nhật thống kê phù hợp, thử index/query design rồi đo lại. Chỉ dùng optimizer hint khi đã hiểu nguyên nhân, có bằng chứng và kiểm thử trên dữ liệu đại diện.

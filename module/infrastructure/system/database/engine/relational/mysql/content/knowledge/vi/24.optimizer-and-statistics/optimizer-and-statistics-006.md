# Histogram, loại phân bố và điều kiện bộ tối ưu sử dụng

Bài học thuộc chương **Bộ tối ưu và thống kê** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Histogram là thống kê mô tả phân bố giá trị của một cột, giúp bộ tối ưu ước lượng số hàng thỏa điều kiện lọc chính xác hơn trong những trường hợp thống kê index thông thường chưa đủ thông tin.

Sau bài này, bạn có thể giải thích histogram giúp optimizer điều gì, phân biệt singleton và equi-height histogram, tạo và xóa histogram bằng ANALYZE TABLE, đọc metadata trong INFORMATION_SCHEMA.COLUMN_STATISTICS, nhận diện predicate đủ điều kiện sử dụng histogram, hiểu giới hạn lấy mẫu và dữ liệu cũ, rồi kiểm chứng tác động bằng EXPLAIN và EXPLAIN ANALYZE.

## 1. Histogram giải quyết vấn đề gì?

MySQL dùng cost-based optimizer để chọn cách thực thi truy vấn. Để so sánh chi phí, optimizer cần ước lượng số hàng mà mỗi điều kiện lọc sẽ trả về.

Ví dụ, một bảng orders có 1.000.000 hàng và cột status với phân bố:

| Giá trị status | Số hàng | Tỷ lệ |
|---|---:|---:|
| COMPLETED | 900.000 | 90% |
| PENDING | 80.000 | 8% |
| CANCELLED | 20.000 | 2% |

Hai truy vấn sau có cùng cấu trúc nhưng độ chọn lọc khác nhau:

~~~sql
SELECT *
FROM orders
WHERE status = 'COMPLETED';

SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Nếu optimizer chỉ biết số lượng giá trị phân biệt mà không biết phân bố cụ thể, nó có thể ước lượng hai điều kiện theo một giả định phân bố đơn giản. Giả định đó không phản ánh dữ liệu lệch mạnh như ví dụ trên.

Histogram cung cấp thông tin về tần suất hoặc phân bố giá trị để optimizer ước lượng selectivity (tỷ lệ hàng vượt qua điều kiện lọc). Với ví dụ này, histogram có thể cho biết điều kiện status = 'CANCELLED' chỉ chọn khoảng 2% số hàng.

Ước lượng tốt hơn có thể giúp optimizer:

- Chọn thứ tự JOIN phù hợp.
- Ước lượng số hàng trung gian sau mỗi điều kiện.
- Đánh giá chi phí table scan, index access hoặc các phương án khác.
- Tránh chọn kế hoạch dựa trên giả định phân bố không đúng.

Histogram không lọc dữ liệu thay cho WHERE, không tạo index và không làm truy vấn tự động nhanh hơn. Nó cung cấp thống kê để optimizer dự đoán số hàng và chọn kế hoạch.

## 2. Histogram khác index statistics như thế nào?

MySQL có nhiều loại thống kê. Cần phân biệt thống kê cardinality của index với histogram của cột.

| Loại thống kê | Mô tả | Mục đích thường gặp |
|---|---|---|
| Index cardinality | Ước lượng số giá trị khác nhau trong index hoặc prefix của index | Ước lượng khả năng chọn lọc của index và chi phí truy cập |
| Histogram | Mô tả phân bố giá trị của một cột qua các bucket | Ước lượng tỷ lệ hàng thỏa phép so sánh với hằng số |
| Actual row count | Số hàng thực tế được truy vấn trả về khi thực thi | Đối chiếu với ước lượng của optimizer |

Index statistics trả lời gần đúng câu hỏi “có bao nhiêu giá trị khác nhau?”. Histogram trả lời chi tiết hơn “các giá trị phân bố như thế nào?”.

Ví dụ, hai cột có cùng 10 giá trị phân biệt nhưng phân bố khác nhau:

- Cột A: mỗi giá trị chiếm khoảng 10%.
- Cột B: một giá trị chiếm 91%, chín giá trị còn lại chia nhau 9%.

Chỉ biết cardinality là 10 chưa đủ để mô tả khác biệt này. Histogram có thể lưu thông tin tần suất để optimizer ước lượng tốt hơn.

Histogram thường hữu ích với cột không có index. Nếu cột có index, optimizer có thể dùng index dive hoặc range optimizer để ước lượng; trong một số trường hợp, ước lượng từ index tốt hơn histogram.

## 3. Bucket là gì?

Histogram chia phân bố giá trị thành các bucket. Mỗi bucket đại diện cho một giá trị hoặc một khoảng giá trị, tùy loại histogram.

MySQL hỗ trợ hai loại:

1. **Singleton histogram:** một bucket đại diện cho một giá trị riêng biệt.
2. **Equi-height histogram:** một bucket đại diện cho một khoảng giá trị.

Việc chọn loại nào được quyết định dựa trên số giá trị phân biệt (distinct values) và số bucket được yêu cầu.

### Singleton histogram

Nếu số giá trị phân biệt nhỏ hơn hoặc bằng số bucket được chỉ định, MySQL tạo singleton histogram.

Ví dụ cột status có ba giá trị:

- CANCELLED
- COMPLETED
- PENDING

Với 16 bucket, histogram có thể dùng ba bucket singleton, mỗi bucket đại diện cho một giá trị.

Mỗi bucket singleton chứa:

- Giá trị của bucket.
- Tần suất tích lũy đến giá trị đó.

Ví dụ minh họa:

~~~json
{
  "histogram-type": "singleton",
  "buckets": [
    ["CANCELLED", 0.02],
    ["COMPLETED", 0.92],
    ["PENDING", 1.00]
  ],
  "null-values": 0.0
}
~~~

Các tỷ lệ trong ví dụ là minh họa cho dữ liệu có 2% CANCELLED, 90% COMPLETED và 8% PENDING. Tần suất tích lũy có nghĩa là:

- Đến CANCELLED: 2%.
- Đến COMPLETED: 92%.
- Đến PENDING: 100%.

Thứ tự giá trị phụ thuộc thứ tự so sánh của kiểu dữ liệu và collation tương ứng.

Singleton phù hợp với cột có số giá trị phân biệt thấp hoặc vừa phải, chẳng hạn trạng thái, loại giao dịch hoặc mã phân nhóm.

### Equi-height histogram

Nếu số giá trị phân biệt lớn hơn số bucket được chỉ định, MySQL tạo equi-height histogram.

Mỗi bucket đại diện cho một khoảng giá trị, gồm:

- Giá trị biên dưới (inclusive).
- Giá trị biên trên (inclusive).
- Tần suất tích lũy đến giá trị biên trên.
- Số lượng giá trị phân biệt trong khoảng.

Các khoảng được xây dựng theo hướng mỗi bucket chứa xấp xỉ cùng tỷ lệ hàng; vì phân bố giá trị có thể lệch, số giá trị phân biệt trong từng bucket không nhất thiết bằng nhau.

Ví dụ minh họa:

~~~json
{
  "histogram-type": "equi-height",
  "buckets": [
    [1, 100, 0.25, 100],
    [101, 250, 0.50, 150],
    [251, 500, 0.75, 250],
    [501, 1000, 1.00, 500]
  ]
}
~~~

Các bucket trên chỉ để giải thích cấu trúc. Histogram thực tế có thể có biên và số distinct values khác.

Equi-height hữu ích với cột có nhiều giá trị khác nhau, ví dụ amount, created_at, score hoặc customer_age.

### Singleton và equi-height so sánh

| Tiêu chí | Singleton | Equi-height |
|---|---|---|
| Đại diện | Một giá trị cụ thể | Một khoảng giá trị |
| Điều kiện hình thành | NDV nhỏ hơn hoặc bằng số bucket | NDV lớn hơn số bucket |
| Thông tin trong bucket | Giá trị và cumulative frequency | Biên dưới, biên trên, cumulative frequency, distinct count |
| Ví dụ phù hợp | status, category có ít giá trị | amount, timestamp, score có nhiều giá trị |

NDV là viết tắt của number of distinct values, tức số giá trị phân biệt.

## 4. Histogram lưu thông tin gì?

Histogram được lưu bền vững trong data dictionary. Người dùng xem thông tin qua view INFORMATION_SCHEMA.COLUMN_STATISTICS.

Các trường quan trọng trong JSON histogram:

| Trường | Ý nghĩa |
|---|---|
| buckets | Danh sách bucket và dữ liệu phân bố |
| null-values | Tỷ lệ giá trị SQL NULL |
| last-updated | Thời điểm histogram được tạo/cập nhật, theo UTC |
| sampling-rate | Tỷ lệ dữ liệu được đọc để tạo histogram |
| histogram-type | singleton hoặc equi-height |
| number-of-buckets-specified | Số bucket yêu cầu khi tạo |
| data-type | Kiểu dữ liệu được biểu diễn trong histogram |
| collation-id | ID collation, có ý nghĩa chủ yếu với dữ liệu chuỗi |
| auto-update | Histogram có bật tự động cập nhật hay không |

Các kiểu data-type có thể gặp gồm int, uint, double, decimal, datetime và string. String bao gồm cả chuỗi ký tự và chuỗi nhị phân.

Có thể truy vấn metadata:

~~~sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE();
~~~

Để trích xuất các thuộc tính thường dùng:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM->>'$."histogram-type"' AS histogram_type,
    JSON_LENGTH(HISTOGRAM->>'$."buckets"') AS bucket_count,
    HISTOGRAM->>'$."sampling-rate"' AS sampling_rate,
    HISTOGRAM->>'$."null-values"' AS null_fraction,
    HISTOGRAM->>'$."last-updated"' AS last_updated
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
ORDER BY TABLE_NAME, COLUMN_NAME;
~~~

HISTOGRAM là JSON. Dùng JSON extraction để đọc thuộc tính cụ thể thay vì phải phân tích toàn bộ JSON bằng mắt.

## 5. Tạo histogram bằng ANALYZE TABLE

Dùng mệnh đề UPDATE HISTOGRAM:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status;
~~~

Nếu không chỉ định số bucket, MySQL mặc định dùng 100 bucket.

Chỉ định số bucket:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

Có thể tạo histogram cho nhiều cột trong cùng bảng:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, amount, created_at
WITH 32 BUCKETS;
~~~

Một câu lệnh UPDATE HISTOGRAM chỉ áp dụng cho một bảng. Số bucket hợp lệ nằm trong khoảng 1 đến 1024.

Nếu số giá trị phân biệt của cột status là 3 và yêu cầu 16 bucket, MySQL tạo singleton histogram với ba bucket. Nếu amount có 1.000 giá trị phân biệt và yêu cầu 16 bucket, MySQL tạo equi-height histogram với tối đa 16 bucket.

Tạo histogram là thao tác riêng với việc cập nhật key distribution. Câu lệnh:

~~~sql
ANALYZE TABLE orders;
~~~

không có HISTOGRAM clause sẽ cập nhật thống kê phân bố index/key; histogram hiện có vẫn được giữ nguyên.

## 6. Xóa histogram

Dùng DROP HISTOGRAM:

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status;
~~~

Xóa histogram trên nhiều cột:

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status, amount, created_at;
~~~

Lệnh này xóa thống kê histogram của các cột được nêu trong câu lệnh. Histogram của cột khác không bị ảnh hưởng.

Xóa histogram không xóa dữ liệu bảng, không xóa index và không thay đổi schema.

Có thể kiểm tra lại:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Nếu không còn histogram cho cột vừa xóa, cột đó không xuất hiện trong kết quả.

## 7. Điều kiện predicate mà optimizer có thể dùng histogram

MySQL dùng histogram để ước lượng số hàng thỏa điều kiện so sánh giá trị cột với hằng số.

Các dạng predicate đủ điều kiện gồm:

~~~sql
col_name = constant
col_name <> constant
col_name != constant
col_name > constant
col_name < constant
col_name >= constant
col_name <= constant
col_name IS NULL
col_name IS NOT NULL
col_name BETWEEN constant AND constant
col_name NOT BETWEEN constant AND constant
col_name IN (constant, ...)
col_name NOT IN (constant, ...)
~~~

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE status = 'CANCELLED';

SELECT *
FROM orders
WHERE amount BETWEEN 100.00 AND 300.00;

SELECT *
FROM orders
WHERE status IN ('PENDING', 'CANCELLED');

SELECT *
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

Điều kiện so sánh với hằng số cũng có thể dùng biểu thức hằng số:

~~~sql
SELECT *
FROM orders
WHERE amount < ABS(-300);
~~~

Điểm cần chú ý: histogram không phải thống kê quan hệ giữa hai cột. Predicate như:

~~~sql
orders.status = customers.preferred_status
~~~

là phép so sánh giữa hai cột, không phải dạng so sánh cột với hằng số được liệt kê ở trên.

Histogram một cột cũng không mô tả tương quan giữa các cột. Nếu status và region có phân bố phụ thuộc lẫn nhau, hai histogram riêng lẻ không thể biểu diễn đầy đủ mối tương quan đó.

## 8. Optimizer sử dụng histogram như thế nào?

Histogram tác động vào ước lượng cardinality/selectivity, sau đó ảnh hưởng đến đánh giá chi phí.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Nếu histogram cho biết khoảng 2% hàng có status CANCELLED, optimizer có thể ước lượng số hàng phù hợp gần với tỷ lệ đó.

Trong một truy vấn JOIN:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'CANCELLED';
~~~

Ước lượng số hàng của orders sau WHERE có thể ảnh hưởng đến thứ tự JOIN và chi phí của các phương án kết hợp bảng.

Histogram có thể giúp optimizer nhận ra một điều kiện rất chọn lọc hoặc rất ít chọn lọc, ngay cả khi cột đó không có index.

Tuy nhiên:

- Histogram không tạo đường truy cập bằng index.
- Histogram không thay đổi kết quả truy vấn.
- Histogram không bảo đảm optimizer chọn một kế hoạch tốt trong mọi trường hợp.
- Histogram không khắc phục mọi sai lệch do tương quan giữa nhiều cột.
- Histogram cũ có thể làm ước lượng sai.

## 9. Histogram và range optimizer

MySQL ưu tiên ước lượng hàng từ range optimizer khi range optimizer có thể áp dụng. Trong trường hợp đó, optimizer không dùng histogram để thay thế ước lượng range.

Với cột có index, index dive có thể cho ước lượng tốt hơn đối với một số phép so sánh bằng.

Do đó, histogram hữu ích chủ yếu cho cột không có index hoặc các trường hợp mà thông tin phân bố bổ sung giúp optimizer ước lượng tốt hơn.

Không nên tạo histogram cho mọi cột. Hãy bắt đầu từ truy vấn có sai lệch rõ giữa số hàng ước lượng và số hàng thực tế, đặc biệt với cột có phân bố lệch mạnh và không có index phù hợp.

## 10. Histogram không thay thế index

Giả sử cột status không có index:

~~~sql
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Histogram có thể giúp optimizer ước lượng khoảng 2% hàng thỏa điều kiện. Nhưng nếu không có index thích hợp, MySQL vẫn có thể phải đọc toàn bộ bảng để tìm các hàng phù hợp.

Nếu tạo index:

~~~sql
CREATE INDEX idx_orders_status
ON orders (status);
~~~

Optimizer có thêm một access path. Index statistics hoặc index dive có thể cung cấp ước lượng, và histogram không nhất thiết được sử dụng.

Cần cân nhắc chi phí:

| Lựa chọn | Lợi ích | Chi phí |
|---|---|---|
| Histogram | Bổ sung thông tin phân bố; không cần duy trì theo từng DML | Cần cập nhật theo nhu cầu; có thể cũ |
| Index | Có thể giúp truy cập trực tiếp các hàng phù hợp | Tốn dung lượng và chi phí duy trì khi INSERT/UPDATE/DELETE |
| Cả hai | Có thể cung cấp thông tin bổ sung trong các trường hợp phù hợp | Tăng công việc quản trị; histogram có thể không được optimizer chọn dùng |

Histogram được tạo hoặc cập nhật theo yêu cầu, nên không phát sinh overhead duy trì sau mỗi thay đổi dữ liệu như index. Đổi lại, histogram có thể dần lỗi thời khi phân bố dữ liệu thay đổi.

## 11. Sampling và độ chính xác của histogram

Để tạo histogram, MySQL cần đọc dữ liệu của cột. Nếu dữ liệu cần đọc vượt quá giới hạn bộ nhớ histogram, MySQL lấy mẫu thay vì đọc toàn bộ.

Biến histogram_generation_max_mem_size kiểm soát lượng bộ nhớ tối đa dùng để tạo histogram.

Kiểm tra:

~~~sql
SELECT
    @@GLOBAL.histogram_generation_max_mem_size,
    @@SESSION.histogram_generation_max_mem_size;
~~~

Khi lượng dữ liệu ước tính cần đọc vượt giới hạn, MySQL dùng SYSTEM sampling, một phương pháp lấy mẫu ở cấp page và phân bố mẫu trên toàn bảng.

InnoDB có cơ chế lấy mẫu riêng cho dữ liệu InnoDB để tránh phải full table scan khi tạo histogram trên bảng lớn.

Trong metadata histogram, sampling-rate cho biết tỷ lệ dữ liệu đã được đọc:

- 1.0: đọc toàn bộ dữ liệu, không lấy mẫu.
- 0.5: khoảng một nửa dữ liệu được lấy mẫu.
- 0.1: khoảng một phần mười dữ liệu được lấy mẫu.

Đây là tỷ lệ lấy mẫu, không phải tỷ lệ hàng thỏa WHERE.

Ví dụ đọc sampling-rate:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM->>'$."sampling-rate"' AS sampling_rate
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Nếu một giá trị hiếm nhưng quan trọng không xuất hiện trong mẫu, histogram có thể không phản ánh đúng phân bố của giá trị đó. Khi cần độ chính xác cao, hãy kiểm tra sampling-rate, đánh giá số bucket và cân nhắc nguồn dữ liệu đầy đủ hoặc histogram do người dùng định nghĩa bằng JSON.

Không nên giảm histogram_generation_max_mem_size quá thấp trên bảng lớn chỉ để tạo histogram nhanh hơn. Lấy mẫu ít có thể làm mất thông tin về các giá trị hiếm hoặc vùng phân bố đặc biệt.

## 12. Chọn số bucket

Số bucket là tham số điều khiển độ chi tiết của histogram.

Giá trị hợp lệ: 1 đến 1024. Nếu không chỉ định, mặc định là 100.

Một số nguyên tắc:

- Cột có ít giá trị phân biệt: singleton histogram có thể lưu mỗi giá trị thành một bucket.
- Cột có nhiều giá trị phân biệt: equi-height histogram chia thành các khoảng.
- Nhiều bucket hơn có thể biểu diễn phân bố chi tiết hơn.
- Nhiều bucket hơn cũng làm metadata lớn hơn và không bảo đảm ước lượng luôn chính xác hơn nếu dữ liệu lấy mẫu không đại diện.
- Không có một con số tối ưu chung cho mọi cột.

Ví dụ:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;

ANALYZE TABLE orders
UPDATE HISTOGRAM ON amount
WITH 64 BUCKETS;
~~~

Có thể dùng số bucket khác nhau cho từng cột bằng các câu lệnh riêng.

Hãy so sánh kế hoạch và sai lệch ước lượng trước/sau. Đừng chọn 1024 bucket mặc định cho mọi cột.

## 13. Histogram có thể bị lỗi thời

Histogram được lưu bền vững trong data dictionary. Khi tạo ở chế độ MANUAL UPDATE (mặc định nếu không chỉ định), histogram không tự cập nhật sau mỗi INSERT, UPDATE hoặc DELETE.

Ví dụ:

1. Khi tạo histogram, 90% đơn hàng là COMPLETED.
2. Một đợt import thay đổi dữ liệu khiến PENDING tăng lên 40%.
3. Histogram vẫn phản ánh phân bố cũ cho đến khi được cập nhật.
4. Optimizer có thể ước lượng sai số hàng cho điều kiện status = 'PENDING'.

Cập nhật lại:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;
~~~

Kiểm tra last-updated và sampling-rate để xác định histogram đang mô tả thời điểm nào và được tạo từ lượng dữ liệu bao nhiêu.

### AUTO UPDATE và MANUAL UPDATE

MySQL 9.7 hỗ trợ tùy chọn AUTO UPDATE và MANUAL UPDATE khi quản lý histogram.

Bật tự động cập nhật:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS AUTO UPDATE;
~~~

Chế độ AUTO UPDATE cho phép histogram được cập nhật khi chạy ANALYZE TABLE trên bảng đó và khi InnoDB background statistics thread tính lại persistent statistics của bảng.

Chỉ định cập nhật thủ công:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS MANUAL UPDATE;
~~~

MANUAL UPDATE là mặc định nếu không chỉ định tùy chọn. Histogram không được tự động cập nhật theo cơ chế AUTO UPDATE.

Kiểm tra thuộc tính auto-update trong JSON histogram:

~~~sql
SELECT
    COLUMN_NAME,
    HISTOGRAM->>'$."auto-update"' AS auto_update,
    HISTOGRAM->>'$."last-updated"' AS last_updated
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

AUTO UPDATE không có nghĩa MySQL quét lại histogram sau từng DML. Nó gắn với các sự kiện cập nhật thống kê được tài liệu mô tả; hãy kiểm tra last-updated để xác nhận thời điểm cập nhật thực tế.

### Lưu ý khi chạy ANALYZE TABLE trên production

- ANALYZE TABLE yêu cầu quyền SELECT và INSERT trên bảng.
- Trong lúc phân tích, MySQL dùng read lock cho bảng InnoDB và MyISAM. Hãy đánh giá thời điểm chạy trên bảng có tải ghi cao.
- Mặc định ANALYZE TABLE được ghi vào binary log để các replica nhận được. Chỉ dùng LOCAL hoặc NO_WRITE_TO_BINLOG khi chủ đích vận hành yêu cầu không ghi statement này vào binary log.
- Cú pháp quản lý histogram chỉ nhận một tên bảng trong mỗi câu lệnh.
- ANALYZE TABLE không chạy trên view.

Ví dụ chạy trên source và để statement được ghi vào binary log theo mặc định:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

Nếu có lý do rõ ràng để không ghi statement vào binary log:

~~~sql
ANALYZE LOCAL TABLE orders
UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

## 14. Những trường hợp không thể tạo histogram

MySQL có các giới hạn sau:

- Không tạo histogram cho cột kiểu JSON.
- Không tạo histogram cho cột kiểu geometry/spatial.
- Không hỗ trợ tạo histogram trên encrypted tables.
- Không hỗ trợ tạo histogram trên TEMPORARY tables.
- Không tạo histogram cho cột được bao phủ bởi single-column unique index.
- Có thể tạo histogram cho stored generated column và virtual generated column.

Nếu một câu lệnh UPDATE HISTOGRAM yêu cầu nhiều cột, MySQL cố gắng thực hiện phần hợp lệ và trả diagnostics cho các cột không tồn tại hoặc có kiểu dữ liệu không hỗ trợ.

Ví dụ, nếu bảng có status, payload_json và location_geom:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, payload_json, location_geom
WITH 16 BUCKETS;
~~~

Histogram có thể được tạo cho status, trong khi payload_json và location_geom bị từ chối do kiểu dữ liệu. Hãy đọc kết quả ANALYZE TABLE thay vì giả định toàn bộ danh sách cột đều thành công.

### Histogram bị ảnh hưởng bởi DDL

- DROP TABLE xóa histogram của các cột trong bảng.
- DROP DATABASE xóa histogram của các bảng thuộc database bị xóa.
- RENAME TABLE giữ histogram và gắn chúng với tên bảng mới.
- ALTER TABLE xóa hoặc sửa một cột sẽ xóa histogram của cột đó.
- ALTER TABLE ... CONVERT TO CHARACTER SET xóa histogram của cột ký tự bị ảnh hưởng; histogram cột không phải ký tự vẫn được giữ.

Sau migration schema, hãy kiểm tra lại INFORMATION_SCHEMA.COLUMN_STATISTICS nếu truy vấn phụ thuộc vào histogram.

## 15. Kiểm tra tác động bằng EXPLAIN

Histogram có tác dụng lên ước lượng của optimizer. Cách kiểm tra là so sánh kế hoạch trước và sau khi tạo histogram.

Ví dụ:

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Có thể dùng JSON format:

~~~sql
EXPLAIN FORMAT=JSON
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Quan sát các trường liên quan đến:

- estimated rows.
- filtered.
- access_type.
- possible_keys và key.
- cost estimates trong JSON plan.

Histogram có thể làm ước lượng filtered thay đổi. Tuy nhiên, nếu cột không có index, access type vẫn có thể là ALL vì histogram không tạo access path mới.

### EXPLAIN ANALYZE

EXPLAIN ANALYZE thực thi câu SELECT và trả thêm thông tin iterator, thời gian và số hàng thực tế.

~~~sql
EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

So sánh:

- Estimated rows: số hàng optimizer dự đoán.
- Actual rows: số hàng thực tế iterator trả về.
- Actual time: thời gian thực thi.
- Loops: số lần iterator được gọi.

EXPLAIN ANALYZE thực sự chạy truy vấn. Chỉ dùng với câu SELECT phù hợp và dữ liệu có thể đọc an toàn; không coi nó là lệnh chỉ phân tích cú pháp.

Một kế hoạch tốt thường có ước lượng gần với số hàng thực tế, nhưng vẫn cần xem tổng thời gian, số lần lặp, I/O và chi phí của toàn bộ kế hoạch.

## 16. Bài thực hành: tạo singleton và equi-height histogram

Bài lab tạo dữ liệu lệch phân bố để quan sát hai loại histogram.

### Bước 1: tạo database và bảng

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_histogram_lab;
USE mysql_histogram_lab;

CREATE TABLE orders (
    order_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    created_at DATE NOT NULL
) ENGINE=InnoDB;
~~~

### Bước 2: tạo 1.000 hàng có phân bố lệch

~~~sql
INSERT INTO orders (status, amount, created_at)
SELECT
    CASE
        WHEN n <= 900 THEN 'COMPLETED'
        WHEN n <= 980 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    CAST(n * 1.37 AS DECIMAL(12,2)),
    DATE_ADD('2026-01-01', INTERVAL MOD(n, 90) DAY)
FROM (
    SELECT
        d0.n + 10 * d1.n + 100 * d2.n + 1 AS n
    FROM
        (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
         SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL
         SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS d0
    CROSS JOIN
        (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
         SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL
         SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS d1
    CROSS JOIN
        (SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL
         SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL
         SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9) AS d2
) AS numbers;
~~~

Kết quả dữ liệu:

- 900 hàng COMPLETED.
- 80 hàng PENDING.
- 20 hàng CANCELLED.

Cột status có ba giá trị phân biệt. Cột amount có nhiều giá trị phân biệt vì được tạo từ n nhân với 1.37.

### Bước 3: kiểm tra phân bố thực tế

~~~sql
SELECT
    status,
    COUNT(*) AS row_count,
    COUNT(*) / (SELECT COUNT(*) FROM orders) AS fraction
FROM orders
GROUP BY status
ORDER BY status;
~~~

Kết quả kỳ vọng:

| status | row_count | fraction |
|---|---:|---:|
| CANCELLED | 20 | 0.02 |
| COMPLETED | 900 | 0.90 |
| PENDING | 80 | 0.08 |

### Bước 4: xem kế hoạch trước khi tạo histogram

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Ghi lại rows và filtered trong kết quả. Vì bảng chỉ có khóa chính order_id, status không có index.

### Bước 5: tạo histogram cho status

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;
~~~

Vì status có ba giá trị phân biệt và số bucket yêu cầu là 16, histogram được tạo theo loại singleton.

### Bước 6: tạo histogram cho amount

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON amount
WITH 16 BUCKETS;
~~~

Vì amount có nhiều hơn 16 giá trị phân biệt, histogram được tạo theo loại equi-height.

### Bước 7: kiểm tra metadata

~~~sql
SELECT
    COLUMN_NAME,
    HISTOGRAM->>'$."histogram-type"' AS histogram_type,
    JSON_LENGTH(HISTOGRAM->>'$."buckets"') AS bucket_count,
    HISTOGRAM->>'$."sampling-rate"' AS sampling_rate,
    HISTOGRAM->>'$."null-values"' AS null_fraction
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY COLUMN_NAME;
~~~

Xác nhận status là singleton và amount là equi-height. Số bucket thực tế có thể nhỏ hơn số bucket yêu cầu đối với singleton.

### Bước 8: so sánh kế hoạch sau histogram

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE status = 'CANCELLED';

EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE status = 'CANCELLED';
~~~

Đối chiếu estimated rows/filtered với actual rows. Không yêu cầu optimizer phải chọn index vì status không có index. Mục tiêu là quan sát cách histogram cải thiện ước lượng selectivity.

### Bước 9: thử predicate khoảng giá trị

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE amount BETWEEN 200.00 AND 300.00;

EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE amount BETWEEN 200.00 AND 300.00;
~~~

amount có histogram equi-height, nên optimizer có thể sử dụng thông tin phân bố cho điều kiện BETWEEN nếu các điều kiện áp dụng.

### Bước 10: thử histogram bị lỗi thời

Thay đổi một phần dữ liệu:

~~~sql
UPDATE orders
SET status = 'PENDING'
WHERE order_id BETWEEN 1 AND 300;
~~~

Phân bố status hiện tại đã thay đổi đáng kể, nhưng histogram đang ở MANUAL UPDATE nên chưa được tạo lại chỉ vì câu UPDATE.

Kiểm tra thời điểm:

~~~sql
SELECT
    COLUMN_NAME,
    HISTOGRAM->>'$."last-updated"' AS last_updated
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME = 'status';
~~~

Cập nhật histogram:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status
WITH 16 BUCKETS;
~~~

Chạy EXPLAIN lại và quan sát ước lượng.

### Bước 11: xóa histogram và dọn dẹp

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status, amount;

DROP DATABASE mysql_histogram_lab;
~~~

Chỉ chạy DROP DATABASE trên database lab vừa tạo.

## 17. Quy trình xử lý khi optimizer ước lượng sai

Khi thấy kế hoạch không hợp lý, không tạo histogram ngay lập tức. Thực hiện theo thứ tự:

1. Chọn truy vấn có vấn đề và thu thập EXPLAIN hoặc EXPLAIN ANALYZE.
2. So sánh estimated rows với actual rows tại iterator có sai lệch lớn.
3. Xác định điều kiện lọc có so sánh cột với hằng số và có thuộc dạng histogram hỗ trợ không.
4. Kiểm tra cột có index hay không; range optimizer hoặc index dive có thể đã cung cấp ước lượng tốt hơn.
5. Kiểm tra phân bố dữ liệu thực tế bằng GROUP BY, COUNT và các truy vấn thống kê phù hợp.
6. Kiểm tra histogram đã tồn tại, loại histogram, số bucket, sampling-rate và last-updated.
7. Nếu histogram thiếu hoặc cũ, cập nhật bằng ANALYZE TABLE ... UPDATE HISTOGRAM.
8. Chạy lại EXPLAIN/EXPLAIN ANALYZE trên cùng truy vấn và cùng dữ liệu.
9. So sánh kế hoạch, estimated rows, actual rows và thời gian.
10. Nếu histogram không giúp, kiểm tra index, điều kiện JOIN, tương quan giữa cột, kiểu dữ liệu và các lựa chọn khác của optimizer.

Không dùng FORCE INDEX chỉ vì một lần EXPLAIN cho thấy optimizer chọn table scan. Hãy hiểu selectivity, kích thước bảng, tỷ lệ hàng được chọn và chi phí truy cập trước khi ép kế hoạch.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tạo histogram nhưng truy vấn không nhanh hơn | Histogram chỉ cải thiện ước lượng, không tạo index | Kiểm tra access path và cân nhắc index nếu cần |
| Optimizer không dùng histogram | Predicate không so sánh cột với hằng số hoặc range optimizer có ước lượng ưu tiên | Kiểm tra dạng predicate và kế hoạch |
| Histogram không được tạo cho cột | Kiểu JSON/geometry, bảng encrypted/TEMPORARY hoặc cột có single-column unique index | Kiểm tra giới hạn hỗ trợ |
| Histogram có ít bucket hơn yêu cầu | Cột có NDV thấp nên dùng singleton | Đọc histogram-type và số bucket thực tế |
| Histogram sai sau import dữ liệu | MANUAL UPDATE chưa được làm mới | Chạy ANALYZE TABLE UPDATE HISTOGRAM |
| Sampling-rate thấp | Giới hạn bộ nhớ khiến MySQL lấy mẫu | Đánh giá histogram_generation_max_mem_size và độ đại diện của mẫu |
| Histogram không phản ánh tương quan cột | Histogram là thống kê đơn cột | Kiểm tra tương quan và cấu trúc truy vấn; không kỳ vọng histogram ghép cột |
| EXPLAIN rows vẫn không khớp actual | Histogram lấy mẫu, dữ liệu lệch hoặc optimizer dùng nguồn ước lượng khác | So sánh sampling-rate, range estimates và actual rows |
| ANALYZE TABLE trả warning cho một cột | Cột không hợp lệ hoặc kiểu không hỗ trợ | Đọc Msg_type/Msg_text và xử lý từng cột |
| Histogram biến mất sau ALTER TABLE | Cột bị sửa/xóa hoặc chuyển charset | Tạo lại histogram sau migration nếu cần |
| Histogram JSON khó đọc | Xem toàn bộ JSON thay vì trích thuộc tính | Dùng JSON extraction trên COLUMN_STATISTICS |

## 19. Checklist quản trị histogram

- [ ] Đã xác định truy vấn có sai lệch ước lượng cardinality đáng kể.
- [ ] Đã phân biệt index cardinality với histogram.
- [ ] Đã kiểm tra phân bố dữ liệu thực tế.
- [ ] Đã xác định histogram có thể áp dụng cho predicate đang dùng.
- [ ] Đã kiểm tra cột có index và range optimizer có thể cung cấp ước lượng khác.
- [ ] Đã chọn số bucket trong khoảng 1 đến 1024.
- [ ] Đã hiểu singleton và equi-height.
- [ ] Đã kiểm tra sampling-rate và last-updated.
- [ ] Đã cân nhắc giới hạn histogram_generation_max_mem_size.
- [ ] Đã biết histogram không hỗ trợ JSON, geometry, encrypted tables và temporary tables.
- [ ] Đã kiểm tra cột có single-column unique index hay không.
- [ ] Đã chọn MANUAL UPDATE hoặc AUTO UPDATE có chủ đích.
- [ ] Đã cập nhật histogram sau import hoặc thay đổi phân bố lớn nếu dùng manual.
- [ ] Đã dùng EXPLAIN để kiểm tra ước lượng.
- [ ] Đã dùng EXPLAIN ANALYZE để đối chiếu actual rows khi an toàn.
- [ ] Đã đánh giá index và tương quan nhiều cột nếu histogram không đủ.
- [ ] Đã kiểm tra lại histogram sau migration schema.

## 20. Nguyên tắc cần ghi nhớ

1. Histogram mô tả phân bố giá trị của một cột để optimizer ước lượng selectivity.
2. Histogram không phải index và không tự tạo access path mới.
3. Singleton histogram dùng một bucket cho mỗi giá trị; equi-height dùng bucket đại diện cho khoảng.
4. Loại histogram phụ thuộc số distinct values so với số bucket được yêu cầu.
5. Histogram lưu JSON trong data dictionary và có thể đọc qua INFORMATION_SCHEMA.COLUMN_STATISTICS.
6. ANALYZE TABLE UPDATE HISTOGRAM tạo hoặc cập nhật histogram; DROP HISTOGRAM xóa thống kê.
7. Số bucket hợp lệ là 1 đến 1024, mặc định 100.
8. Optimizer dùng histogram cho các predicate so sánh cột với hằng số thuộc nhóm được hỗ trợ.
9. Range optimizer và index dive có thể được ưu tiên hơn histogram.
10. Histogram chủ yếu hữu ích cho cột không có index hoặc khi phân bố giúp cải thiện ước lượng.
11. Sampling-rate thấp có thể làm histogram bỏ lỡ giá trị hiếm.
12. Histogram manual có thể cũ sau thay đổi dữ liệu; cần cập nhật theo workload.
13. Histogram là thống kê đơn cột, không mô tả đầy đủ tương quan giữa nhiều cột.
14. Dùng EXPLAIN và EXPLAIN ANALYZE để so sánh ước lượng với số hàng thực tế.
15. Chọn histogram, index hoặc cách tối ưu khác dựa trên bằng chứng từ truy vấn thực tế.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [Optimizer Statistics](https://dev.mysql.com/doc/refman/9.7/en/optimizer-statistics.html): cấu trúc histogram, singleton/equi-height, selectivity và điều kiện optimizer sử dụng.
2. [ANALYZE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/analyze-table.html): UPDATE HISTOGRAM, DROP HISTOGRAM, số bucket, AUTO UPDATE/MANUAL UPDATE và lấy mẫu.
3. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): đọc kế hoạch, EXPLAIN ANALYZE và so sánh ước lượng với thực tế.
4. [Optimizing SELECT Statements](https://dev.mysql.com/doc/refman/9.7/en/select-optimization.html): giữ thống kê cập nhật và quy trình điều tra truy vấn chậm.
5. [Optimizer-Related Issues](https://dev.mysql.com/doc/refman/9.7/en/optimizer-issues.html): các công cụ khi cost-based optimizer chọn kế hoạch chưa phù hợp.


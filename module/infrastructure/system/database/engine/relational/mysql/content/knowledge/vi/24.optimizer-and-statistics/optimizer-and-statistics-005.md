# ANALYZE TABLE và thời điểm cập nhật thống kê

MySQL Optimizer cần ước lượng số hàng mà mỗi bước truy vấn sẽ đọc, số hàng còn lại sau bộ lọc và chi phí của từng access path. Những ước lượng này dựa trên thống kê bảng, thống kê chỉ mục và histogram. Nếu thống kê đã cũ hoặc không phản ánh phân bố dữ liệu hiện tại, optimizer có thể chọn sai index, sai thứ tự JOIN hoặc một kế hoạch tốn kém hơn.

ANALYZE TABLE yêu cầu MySQL thu thập lại thống kê cho bảng và các index của bảng. Với InnoDB, thao tác này thường cập nhật cardinality ước lượng dựa trên việc lấy mẫu các trang index. Có thể chạy thủ công sau khi dữ liệu thay đổi đáng kể, sau khi tạo hoặc thay đổi index, hoặc khi ước lượng trong execution plan lệch rõ rệt so với số hàng thực tế.

Tuy nhiên, chạy ANALYZE TABLE không bảo đảm truy vấn sẽ nhanh hơn. Thống kê mới có thể làm optimizer chọn một kế hoạch khác, đôi khi tốt hơn và đôi khi tệ hơn. Vì vậy, cần xác định đúng thời điểm, ghi nhận execution plan trước và sau, đồng thời đánh giá cả tải vận hành.

Trong module **DATABASE_MYSQL**, bài học này giải thích vai trò của thống kê optimizer, persistent statistics của InnoDB, cơ chế tự tính lại, lấy mẫu trang index, histogram và quy trình quyết định khi nào cần ANALYZE TABLE.

## 1. Vì sao Optimizer cần thống kê?

Khi nhận một truy vấn, MySQL phải chọn cách đọc dữ liệu. Với một truy vấn JOIN, optimizer có thể cân nhắc:

- Đọc bảng A trước rồi tìm hàng tương ứng trong bảng B.
- Đọc bảng B trước rồi JOIN sang bảng A.
- Dùng PRIMARY KEY, secondary index hoặc full table scan.
- Dùng nested-loop join với các lần tra cứu lặp lại.
- Áp dụng điều kiện lọc trước hoặc sau một bước JOIN.
- Dùng temporary table hoặc filesort cho một số thao tác.

Optimizer ước lượng chi phí bằng thống kê và mô hình chi phí. Một phần quan trọng là cardinality: số giá trị khác nhau được ước lượng trong một cột hoặc một key prefix.

Ví dụ bảng đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    region_code CHAR(2) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_tenant_status (tenant_id, status),
    KEY idx_region (region_code),
    KEY idx_created_at (created_at)
) ENGINE = InnoDB;
```

Truy vấn:

```sql
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

Nếu optimizer ước lượng chỉ có 20 hàng phù hợp, dùng index có thể rất rẻ. Nếu thực tế có 500.000 hàng phù hợp, một kế hoạch khác có thể tốt hơn. Khi cardinality hoặc phân bố dữ liệu không phản ánh thực tế, quyết định tối ưu có thể sai.

### 1.1. Thống kê không phải dữ liệu nghiệp vụ

Thống kê optimizer là thông tin ước lượng, không phải kết quả đếm chính xác từng truy vấn. Cardinality trong SHOW INDEX thường là ước lượng số giá trị khác nhau. Optimizer dùng chúng để so sánh chi phí, không dùng chúng làm ràng buộc dữ liệu.

Phân biệt:

| Thành phần | Vai trò |
|---|---|
| Dữ liệu bảng | Các hàng nghiệp vụ thực tế |
| Index | Cấu trúc truy cập dữ liệu |
| Index statistics | Ước lượng cardinality và phân bố key prefix |
| Histogram | Mô tả phân bố giá trị của một cột |
| Execution plan | Kế hoạch optimizer chọn dựa trên truy vấn, thống kê và mô hình chi phí |

ANALYZE TABLE cập nhật thống kê; nó không sửa dữ liệu, không tạo index mới và không thay đổi logic WHERE của truy vấn.

## 2. ANALYZE TABLE làm gì?

Cú pháp cơ bản:

```sql
ANALYZE TABLE orders;
```

MySQL trả về thông tin về bảng, thao tác và trạng thái. Với InnoDB, ANALYZE TABLE thu thập lại thống kê cho index, trong đó có cardinality ước lượng của các key part. Optimizer dùng thống kê mới trong những lần lập kế hoạch tiếp theo.

Có thể phân tích nhiều bảng trong cùng một câu lệnh:

```sql
ANALYZE TABLE orders, customers, order_items;
```

Có thể chỉ định partition trong bảng phân vùng nếu cần cập nhật thống kê cho các partition được chọn:

```sql
ANALYZE TABLE orders PARTITION (p2025, p2026);
```

Ví dụ này giả định orders là bảng đã được partition và có hai partition mang tên p2025, p2026; nó không áp dụng cho bảng orders không phân vùng ở ví dụ đầu bài. Kiểm tra cú pháp và tên partition trên phiên bản MySQL đang chạy trước khi dùng trong quy trình tự động.

### 2.1. Kết quả trả về

Kết quả thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| Table | Tên bảng được phân tích |
| Op | Thao tác được thực hiện, thường là analyze |
| Msg_type | Loại thông báo như status, note hoặc error |
| Msg_text | Nội dung kết quả hoặc lỗi |

Đọc Msg_type và Msg_text để xác nhận thao tác có thành công. Không chỉ kiểm tra ứng dụng không ném exception; cần đọc kết quả của câu lệnh quản trị.

### 2.2. ANALYZE TABLE không phải OPTIMIZE TABLE

Hai lệnh có mục đích khác nhau:

| Lệnh | Mục tiêu chính |
|---|---|
| ANALYZE TABLE | Cập nhật thống kê optimizer |
| OPTIMIZE TABLE | Tổ chức lại hoặc rebuild bảng/index tùy storage engine và phiên bản; có thể thu hồi hoặc sắp xếp lại không gian lưu trữ |
| CHECK TABLE | Kiểm tra bảng và một số vấn đề về cấu trúc/tính nhất quán theo engine |
| REPAIR TABLE | Sửa bảng cho một số storage engine; không phải lệnh sửa dữ liệu InnoDB thông thường |

Không chạy OPTIMIZE TABLE chỉ vì execution plan đang có cardinality sai. Trước tiên hãy xác định vấn đề có thực sự nằm ở thống kê hay không.

## 3. Thống kê InnoDB: Persistent và Transient

InnoDB có hai cách quản lý thống kê chính:

- **Persistent statistics:** được lưu lại trong các bảng hệ thống của MySQL và giữ qua lần restart.
- **Transient statistics:** được tính tạm thời, không được lưu bền vững theo cách persistent stats; có thể được tính lại khi bảng được mở hoặc theo vòng đời của bảng.

Trong các phiên bản MySQL hiện đại, persistent statistics được bật mặc định cho InnoDB. Kiểm tra:

```sql
SELECT
    @@GLOBAL.innodb_stats_persistent
        AS innodb_stats_persistent,
    @@GLOBAL.innodb_stats_auto_recalc
        AS innodb_stats_auto_recalc,
    @@GLOBAL.innodb_stats_persistent_sample_pages
        AS persistent_sample_pages;
```

Các biến trong ví dụ được đọc ở phạm vi GLOBAL. Có thể dùng SHOW VARIABLES để kiểm tra giá trị cấu hình hiện hành trên server.

### 3.1. Persistent statistics

Khi persistent stats được bật, InnoDB lưu thống kê trong các bảng hệ thống như:

- mysql.innodb_table_stats
- mysql.innodb_index_stats

Có thể xem thông tin của bảng:

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
  AND table_name = 'orders';
```

Xem thống kê index:

```sql
SELECT
    database_name,
    table_name,
    index_name,
    last_update,
    stat_name,
    stat_value,
    sample_size,
    stat_description
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
```

Trong innodb_index_stats, các dòng có stat_name như n_diff_pfxNN biểu thị số giá trị khác nhau được ước lượng cho các prefix đầu của index. Đây là cơ sở quan trọng để optimizer ước lượng selectivity của composite index.

Các bảng này phục vụ quan sát. Không tự UPDATE/DELETE dữ liệu trong chúng để ép optimizer dùng một kế hoạch. Nếu cần thay đổi thống kê, dùng ANALYZE TABLE hoặc cơ chế được MySQL hỗ trợ.

### 3.2. Transient statistics

Nếu persistent stats bị tắt cho bảng hoặc toàn server, InnoDB dùng transient stats. Thống kê có thể được tính lại khi bảng được mở và không được giữ bền vững qua restart như persistent stats.

Điều này có thể làm execution plan thay đổi giữa các lần mở bảng hoặc sau restart nếu dữ liệu sampling khác nhau. Với hệ thống cần kế hoạch ổn định, persistent stats thường dễ quản lý và theo dõi hơn.

### 3.3. Cấu hình ở cấp bảng

Có thể đặt tùy chọn thống kê cho một bảng bằng table options:

```sql
ALTER TABLE orders
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 1,
    STATS_SAMPLE_PAGES = 64;
```

Ý nghĩa:

| Tùy chọn | Ý nghĩa |
|---|---|
| STATS_PERSISTENT | Bật/tắt persistent stats cho bảng hoặc dùng DEFAULT |
| STATS_AUTO_RECALC | Cho phép/tắt tự tính lại thống kê cho bảng |
| STATS_SAMPLE_PAGES | Số trang index được lấy mẫu khi tính persistent stats cho bảng |

Tùy chọn cấp bảng có thể ghi đè mặc định toàn cục. Hãy dùng SHOW CREATE TABLE orders để kiểm tra table options hiện hành.

Không tăng STATS_SAMPLE_PAGES một cách tùy tiện. Lấy mẫu nhiều trang hơn có thể cải thiện ước lượng với dữ liệu phân bố không đồng đều, nhưng cũng làm ANALYZE TABLE tốn thời gian và I/O hơn.

## 4. Tự động tính lại thống kê

Khi innodb_stats_auto_recalc được bật, InnoDB có thể tự tính lại persistent statistics khi số hàng thay đổi đủ lớn so với quy mô bảng.

Ngưỡng thường dùng mặc định là khoảng 10% số hàng trong bảng đã thay đổi kể từ lần tính thống kê trước. Đây là ngưỡng kích hoạt tự động, không phải cam kết rằng thống kê sẽ được cập nhật ngay sau đúng một câu INSERT/UPDATE/DELETE.

Cơ chế tự tính lại có thể chạy nền bất đồng bộ. Vì vậy, sau một batch import lớn, ứng dụng có thể quan sát thấy dữ liệu đã thay đổi nhưng optimizer chưa dùng thống kê mới ngay lập tức.

Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent';
```

### 4.1. Khi nào auto recalc có thể chưa đủ?

- Bảng mới được bulk load và truy vấn quan trọng cần kế hoạch tốt ngay sau import.
- Dữ liệu thay đổi phân bố đáng kể nhưng tỷ lệ số hàng thay đổi chưa vượt ngưỡng.
- Một cột thay đổi độ lệch phân bố mạnh dù tổng số hàng thay đổi ít.
- Có nhiều truy vấn nhạy cảm với cardinality và cần cập nhật thống kê có chủ đích.
- Hệ thống đang điều tra một plan regression và cần tái lập thống kê rõ ràng.

Trong các trường hợp này, có thể chạy ANALYZE TABLE thủ công sau khi dữ liệu đã ổn định và trước khi đánh giá execution plan.

### 4.2. Tắt auto recalc có nên không?

Tắt tự động cập nhật có thể hữu ích trong một số hệ thống cần kiểm soát thời điểm thay đổi plan. Tuy nhiên, nếu dữ liệu liên tục thay đổi mà không có lịch ANALYZE TABLE thay thế, thống kê sẽ ngày càng cũ.

Nếu đặt:

```sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 0;
```

hãy xây dựng quy trình cập nhật thống kê thủ công dựa trên sự kiện dữ liệu, lịch vận hành hoặc cảnh báo plan estimate. Không tắt auto recalc chỉ để tránh một lần plan thay đổi mà không có cơ chế thay thế.

## 5. Lấy mẫu trang index và độ chính xác thống kê

InnoDB không nhất thiết đọc toàn bộ index để tính cardinality. Nó lấy mẫu một số trang index rồi ước lượng số giá trị khác nhau trên toàn bộ cấu trúc.

Cách này tiết kiệm thời gian nhưng có sai số, đặc biệt khi dữ liệu phân bố không đều hoặc có các vùng index chứa giá trị rất khác nhau.

Ví dụ, bảng có một triệu đơn hàng:

- 70% đơn hàng thuộc tenant 1.
- 20% thuộc tenant 2.
- 10% còn lại chia cho hàng nghìn tenant.

Nếu trang được lấy mẫu không phản ánh tốt vùng tenant 1, ước lượng cardinality hoặc phân bố có thể lệch. Một kế hoạch dựa trên ước lượng sai có thể chọn index hoặc thứ tự JOIN không phù hợp.

### 5.1. Tăng số trang lấy mẫu

Có thể tăng biến toàn cục:

```sql
SET GLOBAL innodb_stats_persistent_sample_pages = 64;
ANALYZE TABLE orders;
```

Hoặc cấu hình riêng cho bảng bằng STATS_SAMPLE_PAGES. Tăng số trang lấy mẫu có thể làm thống kê ổn định hơn, nhưng không đảm bảo chính xác tuyệt đối và có thể tăng chi phí đọc.

Thay đổi bằng SET GLOBAL chỉ áp dụng cho instance đang chạy. Nếu muốn giữ cấu hình sau restart, hãy quản lý giá trị trong option file của MySQL hoặc dùng cơ chế cấu hình bền vững được phiên bản server hỗ trợ.

Khi thử thay đổi, nên:

1. Ghi nhận giá trị cấu hình ban đầu.
2. Đo thời gian ANALYZE TABLE.
3. So sánh cardinality trước và sau.
4. So sánh execution plan của các truy vấn quan trọng.
5. Đo latency/throughput của workload đại diện.
6. Giữ cấu hình mới chỉ khi lợi ích được xác nhận.

### 5.2. Thống kê có thể dao động

Do lấy mẫu, hai lần ANALYZE TABLE trên cùng một bảng có thể tạo ra cardinality hơi khác nhau. Với truy vấn gần điểm hòa giữa hai access path, khác biệt nhỏ có thể làm optimizer chọn index khác.

Nếu plan thay đổi sau ANALYZE TABLE, không nên lập tức kết luận thống kê mới sai. Hãy so sánh:

- Estimate của optimizer.
- Số hàng thực tế.
- Thời gian từng iterator.
- Số lần lặp của nested-loop lookup.
- I/O và cache state.
- Độ ổn định của kết quả qua nhiều lần chạy.

## 6. Histogram: thống kê phân bố cho từng cột

Index statistics thường cung cấp cardinality của index key và các prefix. Tuy nhiên, cardinality không mô tả đầy đủ phân bố giá trị.

Ví dụ cột status có 4 giá trị:

| status | Tỷ lệ hàng |
|---|---:|
| PENDING | 75% |
| PAID | 20% |
| CANCELLED | 4% |
| FAILED | 1% |

Nếu chỉ biết có 4 giá trị khác nhau, optimizer chưa biết PENDING chiếm 75% còn FAILED chỉ chiếm 1%. Histogram giúp mô tả phân bố này để ước lượng selectivity của điều kiện lọc.

MySQL hỗ trợ histogram statistics từ MySQL 8.0.2. Histogram được quản lý riêng với index statistics và cần được tạo/cập nhật bằng câu lệnh ANALYZE TABLE có mệnh đề UPDATE HISTOGRAM.

### 6.1. Tạo histogram

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 100 BUCKETS;
```

Có thể cập nhật nhiều cột trong cùng câu lệnh:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status, region_code
    WITH 100 BUCKETS;
```

Số bucket có thể chọn trong phạm vi MySQL hỗ trợ, tối đa 1024. Nếu không chỉ định, MySQL dùng số bucket mặc định. Nhiều bucket hơn có thể mô tả phân bố chi tiết hơn nhưng làm histogram lớn hơn và tăng chi phí thu thập.

### 6.2. Xem histogram

Histogram được lưu trong data dictionary và có thể xem qua INFORMATION_SCHEMA.COLUMN_STATISTICS:

```sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    JSON_PRETTY(HISTOGRAM) AS histogram
FROM information_schema.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
```

Có thể đọc các thuộc tính chính của histogram trong JSON như loại histogram, số bucket được chỉ định, thời điểm cập nhật, tỷ lệ lấy mẫu và các bucket dữ liệu. Cấu trúc JSON có thể có thêm thuộc tính theo kiểu dữ liệu và phiên bản.

### 6.3. Singleton và equi-height histogram

MySQL có thể dùng hai dạng histogram chính:

- **Singleton:** phù hợp khi số giá trị phân biệt không lớn; mỗi giá trị được mô tả cùng tần suất tích lũy.
- **Equi-height:** chia phân bố thành các bucket có khối lượng dữ liệu gần tương đương; một bucket có thể chứa một khoảng giá trị.

Optimizer chọn dạng phù hợp dựa trên số lượng giá trị khác nhau và số bucket có sẵn. Không cần tự quyết định loại histogram trong câu lệnh thông thường.

### 6.4. Histogram giúp ích khi nào?

Histogram hữu ích khi:

- Cột có phân bố lệch (skewed distribution).
- Có một số giá trị xuất hiện rất thường xuyên.
- Cột không có index riêng nhưng vẫn xuất hiện trong điều kiện WHERE.
- Optimizer ước lượng selectivity không tốt từ index statistics.
- Truy vấn JOIN hoặc lọc có kế hoạch phụ thuộc mạnh vào tỷ lệ hàng được chọn.

Histogram là thống kê một cột. Nó không mô hình hóa đầy đủ tương quan giữa nhiều cột. Ví dụ tenant_id = 42 có thể có tỷ lệ PENDING rất khác toàn bảng; histogram riêng của tenant_id và status không nhất thiết nắm bắt được mối tương quan đó.

### 6.5. Cập nhật và xóa histogram

Histogram không tự động cập nhật chỉ vì hàng trong bảng thay đổi. Khi phân bố cột thay đổi đáng kể, cần cập nhật lại histogram:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 100 BUCKETS;
```

Xóa histogram khi không còn cần hoặc muốn quay lại ước lượng không dùng histogram đó:

```sql
ANALYZE TABLE orders
    DROP HISTOGRAM ON status;
```

Lưu ý: ANALYZE TABLE orders; cập nhật thống kê index của bảng nhưng không đồng nghĩa với việc tự tạo mới mọi histogram đã xóa hoặc cập nhật histogram theo cách rõ ràng. Quản lý histogram bằng UPDATE HISTOGRAM và DROP HISTOGRAM.

## 7. Khi nào nên chạy ANALYZE TABLE?

Không cần chạy ANALYZE TABLE sau mọi transaction. Hãy chạy khi có dấu hiệu thống kê không còn đại diện cho dữ liệu hoặc khi cần chủ động làm mới ước lượng.

### 7.1. Sau bulk import hoặc tải dữ liệu ban đầu

Khi tạo bảng mới và nạp hàng triệu bản ghi, thống kê trước đó có thể trống hoặc không phản ánh phân bố dữ liệu mới.

Quy trình:

```sql
-- Nạp dữ liệu bằng công cụ hoặc câu lệnh import phù hợp.
-- Sau khi batch hoàn tất:
ANALYZE TABLE orders;
```

Sau đó chạy EXPLAIN cho các truy vấn quan trọng để xác nhận optimizer nhìn thấy cardinality mới.

### 7.2. Sau khi xóa hoặc cập nhật diện rộng

Nếu xóa phần lớn dữ liệu cũ, thay đổi trạng thái của một tỷ lệ lớn hàng hoặc chuyển dữ liệu giữa các nhóm, thống kê trước đó có thể không còn đúng.

Ví dụ:

```sql
DELETE FROM orders
WHERE created_at < '2023-01-01';

ANALYZE TABLE orders;
```

Với DELETE rất lớn, nên chia batch và chỉ ANALYZE sau khi đợt thay đổi chính hoàn tất, thay vì chạy sau từng batch nhỏ.

### 7.3. Sau khi tạo hoặc thay đổi index

DDL tạo index thường đi kèm công việc cập nhật metadata/statistics, nhưng nếu execution plan vẫn có ước lượng bất hợp lý, có thể chạy ANALYZE TABLE để thu thập lại thống kê.

```sql
CREATE INDEX idx_tenant_created
    ON orders (tenant_id, created_at);

ANALYZE TABLE orders;
```

ANALYZE TABLE không tạo index và không thay thế việc chọn đúng thứ tự key part. Nếu truy vấn cần status nhưng index chỉ có tenant_id, created_at, cập nhật thống kê không thể làm index tự hỗ trợ điều kiện status như một key part.

### 7.4. Khi EXPLAIN ước lượng lệch đáng kể

Ví dụ EXPLAIN cho biết ước lượng 100 hàng nhưng EXPLAIN ANALYZE thực tế đọc 200.000 hàng hoặc ngược lại. Đây là dấu hiệu cần điều tra:

- Thống kê index có cũ không?
- Cột có phân bố lệch không?
- Có histogram chưa?
- Dữ liệu có thay đổi mạnh gần đây không?
- Có tương quan giữa nhiều cột trong điều kiện không?
- Kiểu dữ liệu/collation có làm điều kiện khó ước lượng không?

Nếu nghi thống kê index cũ, chạy ANALYZE TABLE. Nếu nghi phân bố một cột lệch, cân nhắc histogram. Nếu vấn đề là tương quan đa cột, histogram đơn cột có thể chưa đủ; cần xem lại index ghép, cách viết truy vấn và chiến lược truy cập.

### 7.5. Theo lịch khi workload có biến động

Với bảng có dữ liệu tăng/giảm mạnh theo ngày, có thể lập lịch ANALYZE TABLE trong cửa sổ bảo trì. Nhưng lịch cố định không nên thay thế việc quan sát.

Một số bảng append-only ít thay đổi phân bố có thể không cần ANALYZE thường xuyên. Bảng có dữ liệu xóa theo retention, tenant mới hoặc status chuyển hàng loạt có thể cần cập nhật thường xuyên hơn.

## 8. Khi nào chưa cần chạy ANALYZE TABLE?

Không cần chạy chỉ vì:

- Một câu SELECT đơn lẻ chậm nhưng chưa đọc EXPLAIN.
- Ứng dụng vừa INSERT một vài hàng.
- Có index mới nhưng chưa có truy vấn nào dùng.
- Cardinality hiển thị trong SHOW INDEX không bằng số hàng thực tế.
- Muốn ép optimizer chọn một index cụ thể mà chưa xác định nguyên nhân.
- Đang ở giờ cao điểm và chưa đánh giá chi phí/lock của thao tác.

Trước khi chạy, hãy kiểm tra:

1. Query nào chậm và có tần suất bao nhiêu?
2. Execution plan hiện tại dùng index nào?
3. Estimated rows lệch bao nhiêu so với actual rows?
4. Bảng đã thay đổi bao nhiêu từ lần cập nhật thống kê?
5. Có histogram phù hợp không?
6. Thao tác ANALYZE có thể ảnh hưởng workload ghi tại thời điểm chạy không?

Nếu vấn đề nằm ở thiếu index, biểu thức không sargable, JOIN sai điều kiện hoặc trả về quá nhiều dữ liệu, ANALYZE TABLE không giải quyết gốc rễ.

## 9. Quy trình trước và sau ANALYZE TABLE

Đừng chạy ANALYZE rồi chỉ nhìn thông báo OK. Hãy tạo một quy trình có thể so sánh.

### Bước 1: Ghi nhận truy vấn và execution plan hiện tại

```sql
EXPLAIN FORMAT = JSON
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

Ghi lại key, access type, estimated rows, cost và thứ tự JOIN nếu có.

### Bước 2: Đo số hàng thực tế

Trên MySQL hỗ trợ EXPLAIN ANALYZE (MySQL 8.0.18 trở lên), có thể chạy:

```sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
```

EXPLAIN ANALYZE thực thi truy vấn thật. Chỉ dùng với SELECT phù hợp, tránh truy vấn có chi phí quá lớn trên production nếu chưa đánh giá.

### Bước 3: Ghi nhận thống kê hiện tại

```sql
SHOW INDEX FROM orders;
```

Nếu cần chi tiết hơn, đọc mysql.innodb_table_stats và mysql.innodb_index_stats như phần trước. Không chỉnh sửa trực tiếp các bảng hệ thống này.

### Bước 4: Cập nhật thống kê

```sql
ANALYZE TABLE orders;
```

Nếu cần histogram riêng:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 100 BUCKETS;
```

Hai thao tác phục vụ hai loại thống kê khác nhau: index statistics và column histogram.

### Bước 5: Đọc lại plan và đo lại

Chạy lại EXPLAIN FORMAT=JSON và EXPLAIN ANALYZE với cùng tham số, điều kiện dữ liệu và môi trường càng tương đồng càng tốt.

So sánh:

| Chỉ số | Trước | Sau |
|---|---|---|
| Index được chọn | Ghi nhận | Có thay đổi không? |
| Estimated rows | Ước lượng cũ | Ước lượng mới |
| Actual rows | Số thực tế | Số thực tế |
| Loops | Số lần iterator chạy | Có giảm không? |
| Execution time | Thời gian trước | Thời gian sau |
| Rows examined | Số hàng đọc | Có giảm không? |

Không chỉ so sánh một lần chạy. Cache warm/cold, tải hệ thống và tham số truy vấn có thể làm thời gian khác nhau. Dùng nhiều lần đo và workload đại diện.

## 10. Histogram và index statistics giải quyết hai vấn đề khác nhau

| Tiêu chí | Index statistics | Histogram |
|---|---|---|
| Đối tượng | Index và key prefix | Một cột |
| Thông tin chính | Cardinality, số giá trị khác nhau của key prefix | Phân bố giá trị và tần suất |
| Mục đích | Ước lượng selectivity theo index | Ước lượng điều kiện trên cột |
| Cập nhật | ANALYZE TABLE | ANALYZE TABLE ... UPDATE HISTOGRAM |
| Xem ở đâu | SHOW INDEX, mysql.innodb_index_stats | INFORMATION_SCHEMA.COLUMN_STATISTICS |
| Tương quan đa cột | Composite index có thống kê prefix | Không mô hình hóa đầy đủ tương quan đa cột |

Ví dụ: index (tenant_id, status) có thể cung cấp cardinality ước lượng cho prefix tenant_id và tenant_id + status. Histogram trên status có thể mô tả tần suất từng status trên toàn bảng. Hai nguồn thông tin bổ sung nhau nhưng không hoàn toàn thay thế nhau.

Nếu status = 'PENDING' chiếm 80% toàn bảng nhưng chỉ 2% trong tenant_id = 42, histogram status đơn cột không mô tả được mối tương quan đó. Index ghép có thể cung cấp thông tin tốt hơn cho truy vấn theo cả tenant_id và status, tùy chất lượng thống kê.

## 11. ANALYZE TABLE và replication

ANALYZE TABLE được ghi vào binary log theo mặc định trong các cấu hình replication thông thường, nên thao tác có thể được áp dụng trên replica thông qua replication. Có thể ngăn ghi câu lệnh vào binary log bằng:

```sql
ANALYZE NO_WRITE_TO_BINLOG TABLE orders;
```

Hoặc dùng từ khóa tương đương:

```sql
ANALYZE LOCAL TABLE orders;
```

Chọn chạy trên source hay replica tùy kiến trúc và mục tiêu vận hành. Nếu cần thống kê riêng cho từng server do phân bố dữ liệu hoặc workload khác nhau, cần cân nhắc cách cập nhật cục bộ và hành vi replication để không vô tình ghi lại thao tác.

Không chạy cùng một tác vụ ANALYZE trên source và mọi replica theo lịch mà không hiểu tác động đến binlog và workload. Kiểm tra trạng thái replication và chính sách vận hành của hệ thống.

## 12. Ảnh hưởng vận hành và khóa khi ANALYZE TABLE

ANALYZE TABLE là thao tác quản trị trên bảng, không phải câu SELECT thuần túy. Với InnoDB và MyISAM, thao tác sử dụng read lock: các lượt đọc có thể tiếp tục, còn thao tác ghi phải chờ trong thời gian khóa được giữ. Lệnh cũng cần metadata lock và có thể phải chờ transaction/DDL khác đang sử dụng bảng. Hành vi chi tiết có thể khác theo storage engine và phiên bản.

Trước khi chạy trên production:

- Ưu tiên cửa sổ tải thấp nếu bảng lớn hoặc hệ thống nhạy với write latency.
- Kiểm tra transaction dài và DDL đang chờ.
- Theo dõi lock wait, latency và throughput trong lúc chạy.
- Chạy từng nhóm bảng có kiểm soát, tránh đồng loạt phân tích toàn bộ schema lớn.
- Đọc kết quả trả về và xác nhận trạng thái sau thao tác.

ANALYZE TABLE không rebuild toàn bộ bảng như một số thao tác OPTIMIZE, nhưng vẫn có chi phí đọc trang và cập nhật thống kê. Đừng xem nó là lệnh miễn phí có thể chạy liên tục.

## 13. Tuning histogram và sample pages có kiểm soát

### 13.1. Không đặt bucket quá lớn theo cảm tính

Nhiều bucket hơn có thể mô tả chi tiết phân bố hơn, nhưng histogram vẫn chỉ là mô hình ước lượng. Nếu cột có ít giá trị phân biệt, thêm nhiều bucket không tạo ra thông tin hữu ích tương ứng.

Ví dụ cột status chỉ có bốn giá trị:

```sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 16 BUCKETS;
```

Nếu cột có hàng triệu giá trị phân biệt, cần thử một số số bucket phù hợp và so sánh estimate/actual rows. Không có một số bucket tối ưu cho mọi cột.

### 13.2. Không tăng sample pages để chữa mọi sai lệch

Tăng sample pages có thể cải thiện ước lượng index cardinality khi dữ liệu phân bố không đều. Nhưng nếu vấn đề là optimizer không biết tương quan giữa hai cột, tăng sample pages của index statistics không tự động giải quyết hoàn toàn.

Hãy xác định sai lệch thuộc loại nào:

- Cardinality index sai: xem persistent stats và sample pages.
- Phân bố một cột lệch: xem histogram.
- Tương quan nhiều cột: xem composite index và cấu trúc truy vấn.
- Điều kiện không sargable: viết lại điều kiện hoặc dùng generated/functional index phù hợp.
- Thiếu index: thiết kế index theo workload.
- Ước lượng đúng nhưng query vẫn chậm: xem I/O, CPU, lock, sort, network và lượng dữ liệu trả về.

## 14. Các lỗi và hiểu nhầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chạy ANALYZE TABLE sau mọi INSERT | Tạo overhead quản trị không cần thiết | Dựa vào quy mô thay đổi và dấu hiệu plan |
| Nghĩ ANALYZE TABLE bảo đảm query nhanh hơn | Optimizer có thể chọn plan khác, kể cả plan kém hơn | Đo execution plan trước/sau |
| Nhầm ANALYZE TABLE với OPTIMIZE TABLE | Chạy thao tác rebuild/space maintenance không cần thiết | Dùng đúng lệnh theo mục tiêu |
| Cho rằng auto recalc cập nhật ngay | Plan có thể vẫn dùng stats cũ trong một khoảng thời gian | Chủ động ANALYZE khi cần kết quả ngay |
| Nghĩ cardinality là số hàng chính xác | Đánh giá sai thống kê | Hiểu đây là ước lượng dựa trên sampling |
| Tăng sample pages tối đa | Tốn I/O nhưng không giải quyết sai lệch gốc | Chỉ tăng khi đo chứng minh có ích |
| Nghĩ histogram tự cập nhật sau DML | Histogram có thể cũ dù index stats được tính lại | Cập nhật histogram riêng khi phân bố thay đổi |
| Dùng histogram đơn cột để mô tả tương quan nhiều cột | Optimizer vẫn ước lượng sai điều kiện kết hợp | Cân nhắc composite index và query design |
| Sửa trực tiếp mysql.innodb_index_stats | Có thể làm thống kê không nhất quán | Dùng ANALYZE TABLE |
| Chạy ANALYZE hàng loạt giờ cao điểm | Tăng I/O hoặc gây chờ ghi | Chạy có kiểm soát trong cửa sổ phù hợp |
| Không kiểm tra plan sau ANALYZE | Bỏ lỡ plan regression | So sánh EXPLAIN và actual execution |

## 15. Checklist quyết định thời điểm ANALYZE TABLE

**Nên cân nhắc chạy khi:**

- Vừa bulk load dữ liệu lớn vào bảng.
- Vừa xóa hoặc cập nhật một tỷ lệ lớn hàng.
- Phân bố dữ liệu thay đổi đáng kể.
- Vừa tạo hoặc thay đổi index và plan chưa hợp lý.
- EXPLAIN estimate lệch xa actual rows.
- Bảng có workload thay đổi theo chu kỳ và thống kê không còn đại diện.

**Chưa nên chạy ngay khi:**

- Chưa biết truy vấn nào đang chậm.
- Chưa đọc EXPLAIN.
- Vấn đề nằm ở thiếu index hoặc điều kiện không sargable.
- Chỉ có một lượng nhỏ dữ liệu mới.
- Chưa đánh giá tác động I/O/lock trên production.
- Muốn ép optimizer chọn một index mà chưa benchmark.

**Sau khi chạy:**

- Đọc Msg_type và Msg_text.
- Kiểm tra SHOW INDEX hoặc persistent stats.
- Chạy lại EXPLAIN.
- Dùng EXPLAIN ANALYZE trên SELECT phù hợp.
- So sánh estimated rows với actual rows.
- Đo latency và workload thật.
- Kiểm tra histogram nếu truy vấn phụ thuộc phân bố một cột.
- Ghi nhận thời điểm, bảng, lý do, kết quả và plan regression nếu có.

## 16. Ghi nhớ

- Optimizer dùng thống kê để ước lượng cardinality, selectivity và chi phí access path.
- ANALYZE TABLE cập nhật thống kê index; nó không tạo index và không thay đổi dữ liệu nghiệp vụ.
- InnoDB persistent statistics được lưu trong mysql.innodb_table_stats và mysql.innodb_index_stats.
- Auto recalc thường được kích hoạt khi khoảng 10% số hàng thay đổi, nhưng có thể chạy nền và không cập nhật ngay lập tức.
- STATS_PERSISTENT, STATS_AUTO_RECALC và STATS_SAMPLE_PAGES cho phép điều chỉnh theo bảng.
- InnoDB dùng sampling để ước lượng cardinality; tăng sample pages có thể tăng độ chính xác nhưng cũng tăng chi phí.
- Histogram mô tả phân bố của một cột và được quản lý riêng bằng UPDATE HISTOGRAM/DROP HISTOGRAM.
- Histogram đơn cột không mô hình hóa đầy đủ tương quan giữa nhiều cột.
- Chạy ANALYZE sau bulk load, thay đổi dữ liệu lớn hoặc khi execution plan cho thấy estimate sai đáng kể.
- Không chạy ANALYZE sau mọi transaction và không kỳ vọng nó luôn làm query nhanh hơn.
- So sánh EXPLAIN, EXPLAIN ANALYZE, actual rows và latency trước/sau.
- Đánh giá lock, I/O, replication và plan regression khi chạy trên production.

ANALYZE TABLE là công cụ làm mới thông tin mà optimizer dùng để ra quyết định. Chạy đúng thời điểm, kết hợp persistent statistics, histogram và đo execution plan sẽ giúp MySQL chọn access path sát với dữ liệu thực tế hơn, đồng thời tránh thay đổi kế hoạch truy vấn một cách thiếu kiểm soát.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — ANALYZE TABLE Statement: https://dev.mysql.com/doc/refman/8.0/en/analyze-table.html
- MySQL 8.0 Reference Manual — InnoDB Persistent Statistics: https://dev.mysql.com/doc/refman/8.0/en/innodb-persistent-stats.html
- MySQL 8.0 Reference Manual — InnoDB Statistics Estimation: https://dev.mysql.com/doc/refman/8.0/en/innodb-statistics-estimation.html
- MySQL 8.0 Reference Manual — Optimizer Statistics: https://dev.mysql.com/doc/refman/8.0/en/optimizer-statistics.html


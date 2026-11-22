# Thống kê bảng/chỉ mục và nguồn metadata liên quan

MySQL Optimizer không đọc mọi hàng trong bảng để quyết định kế hoạch cho mỗi câu truy vấn. Nó dựa vào metadata và thống kê để ước lượng số hàng sẽ được đọc, mức độ chọn lọc của điều kiện, chi phí truy cập index, chi phí JOIN và chi phí sắp xếp. Nếu thống kê không phản ánh đúng dữ liệu hiện tại, optimizer có thể chọn một kế hoạch kém hiệu quả dù bảng đã có index phù hợp.

Trong MySQL, thông tin liên quan nằm ở nhiều nguồn:

- Metadata cấu trúc trong INFORMATION_SCHEMA và lệnh SHOW.
- Thống kê bảng và index của InnoDB trong mysql.innodb_table_stats và mysql.innodb_index_stats.
- Histogram theo cột trong INFORMATION_SCHEMA.COLUMN_STATISTICS.
- Số đo hoạt động thực tế trong Performance Schema và các view của sys schema.
- Ước lượng và số liệu thực thi trong EXPLAIN và EXPLAIN ANALYZE.

Các nguồn này có mục đích khác nhau. Cardinality trong SHOW INDEX là ước lượng số giá trị phân biệt; TABLE_ROWS của InnoDB cũng là ước lượng. Chúng không thay thế COUNT(*) hoặc số liệu runtime. Bài học này hướng dẫn đọc đúng từng nguồn, cập nhật thống kê và dùng chúng để chẩn đoán kế hoạch truy vấn.

## 1. Vì sao optimizer cần thống kê?

Giả sử bảng orders có vài triệu hàng và hai index:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status (status),
    KEY idx_orders_created (created_at)
) ENGINE = InnoDB;
~~~

Hai truy vấn sau có thể có chi phí rất khác nhau:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 1001;

SELECT order_id
FROM orders
WHERE status = 'PENDING';
~~~

Nếu customer_id = 1001 chỉ khớp 20 hàng, index customer có thể là đường truy cập rất tốt. Nếu status = 'PENDING' khớp 70% bảng, quét index rồi đọc hàng có thể tốn hơn quét bảng hoặc chọn một kế hoạch khác.

Optimizer cần ước lượng:

- Tổng số hàng và số trang dữ liệu.
- Số giá trị phân biệt của cột hoặc tiền tố index.
- Tỷ lệ hàng khớp với predicate.
- Phân bố dữ liệu có đều hay bị lệch.
- Số hàng trung gian sau mỗi bước JOIN.
- Số hàng cần sắp xếp, nhóm hoặc materialize.
- Khả năng truy vấn được bao phủ hoàn toàn bởi index.

Thống kê tốt giúp optimizer dự đoán chi phí gần thực tế hơn. Thống kê cũ hoặc quá thô có thể khiến optimizer đánh giá sai selectivity và chọn sai access path.

## 2. Phân biệt metadata cấu trúc, optimizer statistics và runtime metrics

Không phải mọi thông tin có chữ “statistics” đều là cùng một loại dữ liệu.

| Nhóm | Nguồn tiêu biểu | Cung cấp thông tin | Dùng để |
|---|---|---|---|
| Metadata cấu trúc | SHOW CREATE TABLE, INFORMATION_SCHEMA.COLUMNS | Kiểu cột, NULL, default, constraint | Hiểu schema |
| Metadata index | SHOW INDEX, INFORMATION_SCHEMA.STATISTICS | Cột index, thứ tự, unique, cardinality ước lượng | Hiểu index và selectivity |
| Thống kê InnoDB | mysql.innodb_table_stats, mysql.innodb_index_stats | Số hàng/trang và số giá trị phân biệt ước lượng | Optimizer ước lượng chi phí |
| Histogram | INFORMATION_SCHEMA.COLUMN_STATISTICS | Phân bố giá trị theo cột | Ước lượng predicate trên cột |
| Runtime metrics | Performance Schema, sys | Số lần đọc/ghi, thời gian chờ, mức sử dụng index | Quan sát workload thật |
| Query plan | EXPLAIN, EXPLAIN ANALYZE | Ước lượng và số đo iterator | Đánh giá một truy vấn cụ thể |

Một câu truy vấn có thể cần đọc cả metadata lẫn runtime metrics. Ví dụ, SHOW INDEX cho biết index tồn tại và cardinality ước lượng; Performance Schema cho biết index đó có được dùng trong khoảng thời gian quan sát hay không.

## 3. Metadata bảng trong INFORMATION_SCHEMA.TABLES

INFORMATION_SCHEMA.TABLES cung cấp metadata về bảng và một số thống kê dung lượng/số hàng.

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    AVG_ROW_LENGTH,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE,
    CREATE_TIME,
    UPDATE_TIME
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
~~~

Các cột thường được quan tâm:

| Cột | Ý nghĩa |
|---|---|
| TABLE_SCHEMA | Database chứa bảng |
| TABLE_NAME | Tên bảng |
| ENGINE | Storage engine |
| TABLE_ROWS | Số hàng ước lượng với InnoDB |
| AVG_ROW_LENGTH | Độ dài hàng trung bình ước lượng |
| DATA_LENGTH | Dung lượng dữ liệu, với InnoDB chủ yếu phản ánh clustered index |
| INDEX_LENGTH | Dung lượng các secondary index theo metadata engine |
| DATA_FREE | Dung lượng trống được báo cáo trong tablespace |
| CREATE_TIME | Thời điểm tạo nếu engine cung cấp |
| UPDATE_TIME | Thời điểm cập nhật metadata nếu engine cung cấp; không phải lúc nào cũng có hoặc chính xác cho mọi engine |

### 3.1. TABLE_ROWS của InnoDB không phải số đếm chính xác

Với InnoDB, TABLE_ROWS là ước lượng. Giá trị có thể lệch đáng kể so với số hàng thực tế, đặc biệt khi dữ liệu thay đổi liên tục hoặc thống kê chưa được cập nhật.

Không dùng truy vấn sau để quyết định số bản ghi chính xác:

~~~sql
SELECT TABLE_ROWS
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Nếu cần số hàng chính xác trong snapshot transaction hiện tại, dùng:

~~~sql
SELECT COUNT(*)
FROM orders;
~~~

COUNT(*) có thể phải đọc index và tốn thời gian trên bảng lớn. InnoDB không duy trì một bộ đếm hàng chính xác dùng chung cho mọi transaction vì mỗi transaction có thể nhìn thấy một snapshot khác nhau theo MVCC.

### 3.2. DATA_LENGTH và INDEX_LENGTH không phải số byte của payload nghiệp vụ

Với InnoDB, DATA_LENGTH thường phản ánh dung lượng clustered index theo page; INDEX_LENGTH phản ánh dung lượng secondary index. Đây là thông tin dung lượng lưu trữ, không phải tổng byte dữ liệu người dùng đã nhập.

Các giá trị phụ thuộc page size, row format, mức lấp đầy page, phân mảnh và cách engine báo cáo. Không dùng chúng để tính chính xác kích thước export hoặc kích thước backup.

### 3.3. SHOW TABLE STATUS

Có thể xem nhanh:

~~~sql
SHOW TABLE STATUS LIKE 'orders';
~~~

Các trường Rows, Data_length, Index_length và Data_free cũng cần được hiểu là số liệu metadata/ước lượng theo engine. Với InnoDB, Rows không phải COUNT(*) chính xác.

## 4. Metadata cấu trúc cột và bảng

Khi thống kê có vẻ bất thường, cần kiểm tra schema trước. Khác biệt kiểu dữ liệu, collation, nullable hoặc biểu thức generated có thể ảnh hưởng predicate và index.

### 4.1. INFORMATION_SCHEMA.COLUMNS

~~~sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    EXTRA,
    GENERATION_EXPRESSION
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Nguồn này cho biết:
- Kiểu dữ liệu thực tế.
- Cột có cho phép NULL không.
- Character set và collation của cột chuỗi.
- AUTO_INCREMENT hoặc thuộc tính generated trong EXTRA.
- Biểu thức của generated column nếu có.

### 4.2. SHOW CREATE TABLE

~~~sql
SHOW CREATE TABLE orders;
~~~

Đây là cách thuận tiện để kiểm tra định nghĩa đầy đủ, gồm primary key, unique key, secondary index, foreign key, engine và table options.

Thống kê index chỉ có ý nghĩa khi đọc cùng định nghĩa index. Ví dụ cardinality của tiền tố thứ hai trong composite index phải được hiểu theo thứ tự cột thực tế.

## 5. Thống kê index qua SHOW INDEX

SHOW INDEX cho biết các index của bảng và ước lượng cardinality.

~~~sql
SHOW INDEX FROM orders;
~~~

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| Table | Tên bảng |
| Non_unique | 0 nếu unique, 1 nếu không unique |
| Key_name | Tên index |
| Seq_in_index | Vị trí cột trong index, bắt đầu từ 1 |
| Column_name | Cột được index; có thể NULL với functional key part |
| Collation | Thứ tự A/D nếu áp dụng |
| Cardinality | Số giá trị phân biệt ước lượng của tiền tố index |
| Sub_part | Độ dài prefix index nếu có |
| Packed | Thông tin đóng gói nếu engine cung cấp |
| Null | Cột index có thể chứa NULL hay không |
| Index_type | Kiểu index, thường BTREE với InnoDB |
| Visible | Index có hiển thị với optimizer hay không |
| Expression | Biểu thức nếu là functional index |

### 5.1. Cardinality là ước lượng

Cardinality không phải số hàng của bảng. Nó là ước lượng số giá trị khác nhau trong cột hoặc tiền tố index tương ứng.

Ví dụ index:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

SHOW INDEX có thể hiển thị hai dòng:

| Seq_in_index | Column_name | Cardinality |
|---:|---|---:|
| 1 | customer_id | 100000 |
| 2 | status | 450000 |

Dòng thứ hai đại diện cardinality ước lượng của tiền tố gồm customer_id và status, không phải riêng status.

### 5.2. Cardinality giúp đánh giá selectivity

Selectivity có thể được hình dung gần đúng bằng:

~~~text
selectivity = số giá trị phân biệt / số hàng
~~~

Với một cột:
- Cardinality gần bằng số hàng: nhiều giá trị phân biệt, equality predicate có thể rất chọn lọc.
- Cardinality thấp: nhiều hàng có thể cùng một giá trị.
- Cardinality bằng 1: cột gần như chỉ có một giá trị trong tập dữ liệu được thống kê.

Đây chỉ là mô hình trực giác. Selectivity của một predicate cụ thể còn phụ thuộc phân bố giá trị. Một cột có 100 giá trị phân biệt không có nghĩa mỗi giá trị xuất hiện đúng 1% số hàng.

### 5.3. Composite index và cardinality theo tiền tố

Với index (customer_id, status, created_at), cardinality của:
- Tiền tố 1: customer_id.
- Tiền tố 2: customer_id + status.
- Tiền tố 3: customer_id + status + created_at.

Thông tin này giúp optimizer ước lượng mức phân biệt của từng tiền tố. Nó không cung cấp trực tiếp cardinality độc lập của status hoặc created_at nếu các cột đó không đứng đầu một index riêng.

### 5.4. INFORMATION_SCHEMA.STATISTICS

Có thể truy vấn cùng metadata qua INFORMATION_SCHEMA:

~~~sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    SUB_PART,
    INDEX_TYPE,
    IS_VISIBLE,
    EXPRESSION
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

CARDINALITY ở đây cũng là ước lượng. Đừng diễn giải nó như kết quả COUNT(DISTINCT column).

## 6. Thống kê persistent của InnoDB

InnoDB có thể lưu thống kê bảng và index lâu dài trong hai bảng hệ thống:

- mysql.innodb_table_stats
- mysql.innodb_index_stats

Khi persistent statistics được bật, các thống kê được lưu và có thể tồn tại qua lần restart server. Đây là cấu hình mặc định phổ biến trong MySQL 8.x.

### 6.1. Xem mysql.innodb_table_stats

~~~sql
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
~~~

Các trường:

| Trường | Ý nghĩa |
|---|---|
| database_name | Schema |
| table_name | Bảng |
| last_update | Thời điểm thống kê được cập nhật |
| n_rows | Số hàng ước lượng |
| clustered_index_size | Số page của clustered index |
| sum_of_other_index_sizes | Tổng số page của các index khác |

clustered_index_size và sum_of_other_index_sizes là số page, không phải byte. Có thể nhân với innodb_page_size để ước tính dung lượng page, nhưng đó vẫn là thông tin phân bổ theo page, không phải kích thước payload chính xác.

~~~sql
SELECT @@GLOBAL.innodb_page_size;
~~~

### 6.2. Xem mysql.innodb_index_stats

~~~sql
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
~~~

Các stat_name thường gặp:

| stat_name | Ý nghĩa |
|---|---|
| n_diff_pfxNN | Số giá trị phân biệt ước lượng của tiền tố gồm NN cột index |
| n_leaf_pages | Số leaf page ước lượng của index |
| size | Tổng số page ước lượng của index |

sample_size cho biết số page được lấy mẫu để ước lượng thống kê tương ứng. stat_description mô tả tiền tố index hoặc thông tin mà thống kê đại diện.

### 6.3. Không chỉnh trực tiếp các bảng thống kê hệ thống

mysql.innodb_table_stats và mysql.innodb_index_stats là nơi InnoDB lưu thông tin nội bộ. Dùng chúng để đọc và chẩn đoán; không UPDATE/DELETE thủ công để ép optimizer chọn kế hoạch.

Để cập nhật thống kê, dùng ANALYZE TABLE và các cấu hình sampling được hỗ trợ. Sửa trực tiếp bảng hệ thống có thể tạo thông tin không nhất quán hoặc gây khó khăn khi nâng cấp/phục hồi.

## 7. Persistent statistics và transient statistics

InnoDB có hai cách duy trì thống kê.

### 7.1. Persistent statistics

Persistent statistics được lưu trong các bảng hệ thống và tồn tại qua restart. Đây là chế độ mặc định phổ biến.

Lợi ích:
- Kế hoạch truy vấn ổn định hơn giữa các lần restart.
- Thống kê có thể được quản lý và cập nhật chủ động.
- Tránh việc mỗi lần mở bảng đều phải ước lượng lại toàn bộ thống kê transient.

### 7.2. Transient statistics

Transient statistics không được lưu bền vững theo cách persistent stats. InnoDB có thể tính lại khi mở bảng hoặc khi cần, tùy cấu hình và hoạt động của engine.

Hạn chế:
- Thống kê có thể thay đổi sau restart hoặc khi bảng được mở lại.
- Kế hoạch truy vấn có thể thay đổi do mẫu dữ liệu khác.
- Việc lấy mẫu có thể tạo biến động giữa các lần tính.

### 7.3. Kiểm tra cấu hình

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_persistent';
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
SHOW GLOBAL VARIABLES LIKE 'innodb_stats_transient_sample_pages';
~~~

Có thể đặt tùy chọn theo bảng:

~~~sql
ALTER TABLE orders
    STATS_PERSISTENT = 1,
    STATS_AUTO_RECALC = 1,
    STATS_SAMPLE_PAGES = 64;
~~~

- STATS_PERSISTENT = 1 bật persistent statistics cho bảng.
- STATS_PERSISTENT = 0 dùng transient statistics.
- STATS_PERSISTENT = DEFAULT theo cấu hình server.
- STATS_AUTO_RECALC điều khiển tự động tính lại persistent stats.
- STATS_SAMPLE_PAGES chỉ định số page lấy mẫu cho thống kê persistent của bảng.

Các table option và system variable phải được kiểm tra theo phiên bản MySQL đang chạy. Thay đổi sampling không tự động có nghĩa thống kê hiện tại đã được tính lại ngay; có thể cần ANALYZE TABLE.

## 8. Tự động cập nhật thống kê InnoDB

Khi persistent statistics được bật và auto recalc được bật, InnoDB có thể tự động tính lại thống kê sau khi lượng dữ liệu thay đổi đủ lớn. Ngưỡng mặc định thường được mô tả là khoảng 10% số hàng của bảng đã thay đổi.

Việc tính lại tự động có thể diễn ra bất đồng bộ. Vì vậy:
- Bulk load xong không có nghĩa thống kê đã cập nhật ngay.
- Một số truy vấn có thể chạy với ước lượng cũ trong một khoảng thời gian.
- Thời điểm recalc phụ thuộc trạng thái engine và workload.
- Có thể dùng ANALYZE TABLE để chủ động yêu cầu cập nhật.

Kiểm tra tùy chọn cụ thể của bảng bằng:

~~~sql
SHOW CREATE TABLE orders;
~~~

Nếu các tùy chọn STATS_PERSISTENT, STATS_AUTO_RECALC hoặc STATS_SAMPLE_PAGES được khai báo tường minh, chúng có thể xuất hiện trong định nghĩa bảng. Khi không được khai báo, bảng dùng giá trị DEFAULT từ cấu hình server. Kết hợp SHOW CREATE TABLE với các system variables ở mục trước để xác định cấu hình thực tế; không suy luận tùy chọn bảng chỉ từ một view metadata không chứa các trường đó.

### 8.1. Bật/tắt auto recalc theo bảng

~~~sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 0;
~~~

Tắt auto recalc có thể hữu ích khi muốn kiểm soát thời điểm cập nhật thống kê, nhưng cũng làm tăng nguy cơ optimizer dùng số liệu cũ. Nếu tắt, phải có quy trình ANALYZE TABLE rõ ràng sau các thay đổi dữ liệu lớn.

Bật lại:

~~~sql
ALTER TABLE orders
    STATS_AUTO_RECALC = 1;
~~~

Không tắt auto recalc chỉ để tránh một lần thay đổi kế hoạch mà chưa hiểu nguyên nhân. Hãy đánh giá độ ổn định của thống kê, sampling và truy vấn bị ảnh hưởng.

## 9. ANALYZE TABLE: cập nhật thống kê bảng và index

ANALYZE TABLE yêu cầu MySQL phân tích bảng để cập nhật thống kê mà optimizer sử dụng.

~~~sql
ANALYZE TABLE orders;
~~~

Kết quả thường trả về các cột Table, Op, Msg_type và Msg_text. Khi hoàn tất bình thường, Msg_text thường là status OK.

Sau khi chạy, kiểm tra:

~~~sql
SHOW INDEX FROM orders;
~~~

Và:

~~~sql
SELECT *
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders';
~~~

### 9.1. Khi nào nên ANALYZE TABLE?

- Sau bulk load hoặc import dữ liệu lớn.
- Sau khi xóa hoặc cập nhật một tỷ lệ lớn hàng.
- Sau khi phân bố giá trị thay đổi đáng kể.
- Sau khi thêm hoặc xóa index.
- Khi EXPLAIN ước lượng số hàng lệch lớn so với thực tế.
- Khi optimizer chọn kế hoạch bất thường và nghi ngờ thống kê cũ.

Không cần chạy ANALYZE TABLE sau mỗi INSERT/UPDATE nhỏ. InnoDB đã có cơ chế auto recalc; phân tích liên tục có thể tạo công việc I/O và thay đổi kế hoạch không cần thiết.

### 9.2. ANALYZE TABLE có phải tạo thống kê chính xác tuyệt đối?

Không. InnoDB vẫn dùng lấy mẫu page để ước lượng cardinality. ANALYZE cập nhật thống kê, nhưng kết quả vẫn có sai số do sampling và phân bố dữ liệu.

Nếu cần số giá trị phân biệt chính xác cho một báo cáo, hãy tính trực tiếp:

~~~sql
SELECT COUNT(DISTINCT customer_id)
FROM orders;
~~~

Câu truy vấn này có thể tốn chi phí đáng kể và không phải thao tác thay thế thông thường cho thống kê optimizer.

### 9.3. Tác động vận hành

ANALYZE TABLE là thao tác đọc và cập nhật metadata thống kê. Với InnoDB, hoạt động phân tích thường cho phép DML đồng thời, nhưng vẫn có thể cần metadata lock và tiêu thụ I/O/CPU. Trên bảng lớn hoặc workload cao, hãy chạy trong thời điểm phù hợp và theo dõi độ trễ.

ANALYZE TABLE không giống ALTER TABLE rebuild index. Nó không được dùng để sửa dữ liệu hoặc tái tạo index bị hỏng.

## 10. Sampling pages và độ chính xác của cardinality

InnoDB ước lượng cardinality bằng cách lấy mẫu các page của index. Nếu sample quá nhỏ:
- Giá trị hiếm có thể không xuất hiện trong mẫu.
- Phân bố lệch có thể bị ước lượng sai.
- Cardinality có thể dao động giữa các lần ANALYZE.

Nếu tăng số page lấy mẫu:
- Ước lượng có thể đại diện tốt hơn.
- ANALYZE TABLE có thể tốn thời gian và I/O hơn.
- Thống kê thường ổn định hơn, nhưng vẫn không trở thành số đếm chính xác.

Ví dụ cấu hình ở mức server:

~~~sql
SET GLOBAL innodb_stats_persistent_sample_pages = 64;
~~~

Biến này ảnh hưởng việc lấy mẫu persistent stats cho các bảng dùng giá trị mặc định. Có thể cấu hình riêng cho một bảng bằng STATS_SAMPLE_PAGES.

Không chọn số page chỉ theo cảm tính. Hãy thử trên bảng có phân bố lệch, so sánh cardinality và kế hoạch trước/sau, sau đó đo chi phí ANALYZE và hiệu năng truy vấn.

## 11. Histogram là gì?

Index statistics cung cấp ước lượng cardinality của index và tiền tố index. Nhưng optimizer đôi khi cần biết phân bố giá trị của một cột, đặc biệt khi:
- Cột không có index.
- Một số giá trị xuất hiện rất thường xuyên, còn phần lớn giá trị hiếm.
- Phân bố dữ liệu lệch mạnh.
- Predicate lọc theo giá trị cụ thể mà cardinality trung bình không phản ánh đúng.

Histogram là thống kê phân bố theo từng cột. MySQL lưu histogram trong data dictionary và cung cấp qua INFORMATION_SCHEMA.COLUMN_STATISTICS.

Histogram không phải index. Nó giúp optimizer ước lượng selectivity; nó không tự tạo đường truy cập B-tree để tìm hàng.

### 11.1. Hai loại histogram phổ biến

- **Singleton histogram**: lưu tần suất cho từng giá trị riêng, phù hợp khi số giá trị phân biệt tương đối nhỏ.
- **Equi-height histogram**: chia miền giá trị thành các bucket có số hàng xấp xỉ bằng nhau, phù hợp khi số giá trị phân biệt lớn hơn.

Histogram có giới hạn số bucket. Số bucket càng lớn có thể mô tả phân bố chi tiết hơn, nhưng cũng làm metadata lớn hơn và không loại bỏ sai số lấy mẫu.

### 11.2. Tạo histogram

~~~sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status
    WITH 32 BUCKETS;
~~~

Có thể tạo histogram cho nhiều cột:

~~~sql
ANALYZE TABLE orders
    UPDATE HISTOGRAM ON status, customer_id
    WITH 64 BUCKETS;
~~~

Histogram là thống kê một chiều theo từng cột. Nó không mô tả đầy đủ tương quan giữa customer_id và status như một thống kê đa cột.

### 11.3. Xem histogram

~~~sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    HISTOGRAM
FROM information_schema.column_statistics
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Có thể định dạng JSON để đọc:

~~~sql
SELECT
    COLUMN_NAME,
    JSON_PRETTY(HISTOGRAM) AS histogram_json
FROM information_schema.column_statistics
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
~~~

Metadata JSON thường chứa:
- histogram-type.
- number-of-buckets-specified.
- sampling-rate.
- last-updated.
- null-values.
- data-type và thông tin collation khi áp dụng.
- danh sách buckets và tần suất tích lũy.

Cấu trúc chi tiết phụ thuộc loại histogram và phiên bản MySQL. Không parse JSON theo một layout duy nhất mà không kiểm tra histogram-type.

### 11.4. Xóa histogram

~~~sql
ANALYZE TABLE orders
    DROP HISTOGRAM ON status;
~~~

Xóa histogram không xóa index và không thay đổi dữ liệu bảng. Optimizer sẽ không còn dùng histogram của cột đó; nó có thể dựa vào các thống kê khác như index statistics và ước lượng mặc định.

### 11.5. Histogram không tự cập nhật theo mọi DML

Histogram cần được quản lý riêng. Khi phân bố dữ liệu thay đổi đáng kể, histogram cũ có thể không còn đại diện. Hãy cập nhật lại bằng ANALYZE TABLE ... UPDATE HISTOGRAM khi cần.

Không nhầm auto recalc của InnoDB persistent index statistics với việc histogram được tự động xây lại sau mọi thay đổi dữ liệu.

## 12. Khi nào histogram giúp ích?

Ví dụ cột status có phân bố lệch:

| status | Tỷ lệ hàng |
|---|---:|
| CLOSED | 80% |
| OPEN | 15% |
| ESCALATED | 4% |
| RARE | 1% |

Nếu optimizer chỉ dựa vào một ước lượng phân bố đều trên bốn giá trị, nó có thể đánh giá sai predicate status = 'RARE' hoặc status = 'CLOSED'.

Histogram cung cấp thông tin phân bố để optimizer ước lượng tốt hơn cho các predicate phù hợp.

Tạo histogram:

~~~sql
ANALYZE TABLE ticket
    UPDATE HISTOGRAM ON status
    WITH 16 BUCKETS;
~~~

Sau đó so sánh:

~~~sql
EXPLAIN
SELECT ticket_id
FROM ticket
WHERE status = 'RARE';

EXPLAIN
SELECT ticket_id
FROM ticket
WHERE status = 'CLOSED';
~~~

Quan sát rows ước lượng, access type và key. Nếu cột có index, optimizer vẫn cân nhắc đường truy cập index và chi phí thực tế. Histogram hỗ trợ ước lượng, không bắt buộc optimizer phải chọn một index.

### 12.1. Histogram không thay thế composite index

Giả sử truy vấn:

~~~sql
SELECT ticket_id
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

Histogram trên status không tạo ra một B-tree ghép customer_id/status. Nó cũng không mô tả chính xác tương quan giữa hai cột.

Nếu workload cần truy cập hiệu quả theo cả hai điều kiện, composite index phù hợp có thể quan trọng hơn. Histogram và index statistics bổ sung cho nhau nhưng giải quyết vấn đề khác nhau.

### 12.2. Cẩn thận với tương quan giữa các cột

Giả sử status = 'ESCALATED' chỉ xuất hiện ở một nhóm customer_id nhất định. Histogram status riêng và thống kê customer_id riêng không nhất thiết mô tả được tương quan này.

Optimizer có thể ước lượng số hàng của điều kiện kết hợp chưa chính xác. Khi đó:
- Kiểm tra actual rows bằng EXPLAIN ANALYZE.
- Xem index ghép có phù hợp không.
- Xem lại cách viết predicate và JOIN.
- Kiểm tra thống kê sau khi dữ liệu thay đổi.
- Không kỳ vọng histogram đơn cột giải quyết mọi sai lệch đa cột.

## 13. Metadata theo partition

Với bảng partition, thống kê và dung lượng có thể được cung cấp theo bảng hoặc theo partition trong INFORMATION_SCHEMA.PARTITIONS.

~~~sql
SELECT
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM information_schema.partitions
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders_partitioned'
ORDER BY PARTITION_ORDINAL_POSITION;
~~~

TABLE_ROWS theo partition của InnoDB vẫn là ước lượng. Dùng thông tin này để hiểu phân bố dung lượng và số hàng tương đối, không thay thế COUNT(*) theo điều kiện partition.

Khi partition có phân bố rất lệch, optimizer có thể ước lượng khác nhau giữa các partition. Kiểm tra pruning và kế hoạch thực thi bằng EXPLAIN.

## 14. Performance Schema: đo hoạt động thực tế

Optimizer statistics mô tả dữ liệu và phân bố để dự đoán chi phí. Performance Schema ghi nhận sự kiện runtime như số lần đọc/ghi và thời gian chờ.

Ví dụ xem I/O theo index:

~~~sql
SELECT
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    COUNT_READ,
    COUNT_WRITE,
    SUM_TIMER_READ,
    SUM_TIMER_WRITE
FROM performance_schema.table_io_waits_summary_by_index_usage
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'orders'
ORDER BY COUNT_READ DESC;
~~~

INDEX_NAME NULL thường đại diện thao tác không gắn với một index cụ thể, chẳng hạn table scan. Cách diễn giải chi tiết cần đối chiếu với loại event và instrumentation đang bật.

Các số liệu Performance Schema là số tích lũy trong khoảng thời gian instrumentation đang thu thập; chúng không phải cardinality và cũng không phải thống kê optimizer. Chúng có thể được reset khi server restart hoặc khi summary table được reset.

### 14.1. Tìm index ít được sử dụng

Sys schema có view hỗ trợ:

~~~sql
SELECT *
FROM sys.schema_unused_indexes
WHERE object_schema = DATABASE();
~~~

View này hữu ích để tìm index chưa được ghi nhận sử dụng trong khoảng thời gian quan sát. Nhưng “không được dùng” không có nghĩa chắc chắn là dư thừa:
- Server có thể vừa restart.
- Workload hiếm theo tháng/quý chưa chạy.
- Index có thể phục vụ constraint hoặc truy vấn bảo trì.
- Một số truy vấn có thể chạy ở thời điểm chưa được quan sát.

Không DROP index chỉ dựa vào một lần đọc schema_unused_indexes. Quan sát đủ chu kỳ nghiệp vụ và kiểm tra ràng buộc trước.

### 14.2. Thống kê hoạt động theo bảng

~~~sql
SELECT *
FROM sys.schema_table_statistics
WHERE table_schema = DATABASE()
  AND table_name = 'orders';
~~~

Các view sys giúp trình bày dữ liệu Performance Schema dễ đọc hơn. Chúng phục vụ chẩn đoán workload, không thay thế thống kê cardinality mà optimizer dùng.

## 15. EXPLAIN: thống kê được dùng trong kế hoạch như thế nào?

EXPLAIN cho biết optimizer ước lượng cách truy cập dữ liệu.

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PENDING';
~~~

Các trường cần xem:

| Trường | Ý nghĩa |
|---|---|
| type | Access type như const, eq_ref, ref, range, index, ALL |
| possible_keys | Index optimizer có thể cân nhắc |
| key | Index được chọn |
| key_len | Độ dài phần khóa được dùng |
| rows | Số hàng ước lượng phải đọc |
| filtered | Tỷ lệ hàng ước lượng còn lại sau điều kiện |
| Extra | Ghi chú như Using index, Using where, Using filesort |

rows và filtered là ước lượng, không phải số hàng thực tế. Chúng chịu ảnh hưởng bởi thống kê bảng, index, histogram và điều kiện truy vấn.

### 15.1. So sánh estimated rows với actual rows

Trên MySQL 8.0.18 trở lên, EXPLAIN ANALYZE thực thi truy vấn và báo số liệu thực tế theo iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PENDING';
~~~

Đối chiếu:
- estimated rows.
- actual rows.
- loops.
- thời gian khởi tạo và thời gian thực thi.
- số hàng ở từng iterator.

Nếu estimated rows là 10 nhưng actual rows là 100.000, optimizer đã đánh giá sai selectivity đáng kể. Kiểm tra thống kê, histogram, tương quan cột và predicate.

EXPLAIN ANALYZE chạy câu SELECT thật. Dùng trên môi trường phù hợp, đặc biệt với truy vấn nặng.

## 16. Optimizer Trace: tìm hiểu lý do chọn kế hoạch

Khi EXPLAIN chưa giải thích rõ vì sao optimizer chọn một access path, có thể dùng optimizer trace trong session thử nghiệm.

~~~sql
SET optimizer_trace = 'enabled=on';

SELECT order_id
FROM orders
WHERE customer_id = 1001
  AND status = 'PENDING';

SELECT TRACE
FROM information_schema.optimizer_trace;

SET optimizer_trace = 'enabled=off';
~~~

Trace có thể chứa:
- Các access path được xem xét.
- Ước lượng chi phí.
- Lý do một index hoặc range scan bị loại.
- Quyết định JOIN order.
- Các bước biến đổi điều kiện.

Optimizer trace là dữ liệu chẩn đoán chi tiết, có thể rất dài. Chỉ bật khi cần và tắt sau khi thu thập. Không coi nội dung trace là API ổn định cho ứng dụng.

## 17. Quy trình cập nhật và kiểm chứng thống kê

Một quy trình có thể áp dụng khi truy vấn chậm bất thường:

1. Ghi lại SQL, tham số đại diện và thời gian thực thi.
2. Kiểm tra schema bằng SHOW CREATE TABLE.
3. Kiểm tra index bằng SHOW INDEX.
4. Kiểm tra TABLE_ROWS, DATA_LENGTH và INDEX_LENGTH để hiểu quy mô tương đối.
5. Đọc mysql.innodb_table_stats và mysql.innodb_index_stats.
6. Kiểm tra histogram hiện có trong INFORMATION_SCHEMA.COLUMN_STATISTICS.
7. Chạy EXPLAIN và ghi lại estimated rows, key, type, Extra.
8. Chạy EXPLAIN ANALYZE trên môi trường phù hợp để lấy actual rows.
9. Nếu thống kê cũ hoặc dữ liệu thay đổi mạnh, chạy ANALYZE TABLE.
10. Nếu phân bố một cột lệch, cân nhắc UPDATE HISTOGRAM.
11. Chạy lại EXPLAIN/EXPLAIN ANALYZE và so sánh.
12. Kiểm tra runtime metrics trong Performance Schema để xác nhận index có được dùng trong workload thật.
13. Theo dõi kế hoạch sau triển khai, vì thống kê và dữ liệu tiếp tục thay đổi.

Không thay index chỉ vì cardinality thấp hoặc cao. Cần xem predicate thực tế, số hàng trả về và chi phí đọc/ghi.

## 18. Những lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| TABLE_ROWS là số hàng chính xác | InnoDB báo ước lượng | Dùng COUNT(*) khi cần số đếm chính xác |
| Cardinality là số hàng của index | Cardinality là số giá trị phân biệt ước lượng | Đọc theo tiền tố index |
| Cardinality dòng thứ hai là riêng cột thứ hai | Composite index báo thống kê tiền tố | Kiểm tra SEQ_IN_INDEX và thứ tự cột |
| ANALYZE TABLE làm thống kê chính xác tuyệt đối | InnoDB dùng sampling pages | So sánh và điều chỉnh sampling khi cần |
| Persistent stats tự cập nhật tức thời | Auto recalc có thể chạy bất đồng bộ | Chủ động ANALYZE sau thay đổi lớn |
| Histogram là index | Histogram chỉ mô tả phân bố | Tạo index nếu cần đường truy cập vật lý |
| Histogram mô tả tương quan nhiều cột | Histogram là thống kê một chiều | Xem composite index và actual rows |
| Histogram tự cập nhật theo mọi DML | Histogram cần được quản lý riêng | Cập nhật lại khi phân bố đổi |
| Performance Schema là nguồn cardinality | Nó ghi nhận hoạt động runtime | Dùng đúng nguồn cho đúng câu hỏi |
| Index không xuất hiện trong sys.schema_unused_indexes là dư thừa | Thời gian quan sát có thể chưa đủ | Theo dõi chu kỳ workload và kiểm tra constraint |
| EXPLAIN rows là số hàng thực tế | Đây là ước lượng | Dùng EXPLAIN ANALYZE |
| Sửa mysql.innodb_index_stats để ép optimizer | Bỏ qua cơ chế quản lý nội bộ | Dùng ANALYZE TABLE và cấu hình hỗ trợ |
| ANALYZE TABLE không ảnh hưởng workload | Có thể tiêu thụ I/O và cần metadata lock | Chọn thời điểm, theo dõi tải |
| DATA_LENGTH là kích thước payload | Nó phản ánh dung lượng page/index | Dùng công cụ đo storage/backup phù hợp |

## 19. Bài thực hành

### Bài 1: Đọc metadata bảng

Tạo bảng orders có vài nghìn hàng. Đọc INFORMATION_SCHEMA.TABLES và SHOW TABLE STATUS. So sánh TABLE_ROWS với COUNT(*). Giải thích vì sao có thể khác nhau.

### Bài 2: Đọc cardinality index

Tạo index đơn trên customer_id và status, sau đó composite index trên (customer_id, status). Chạy SHOW INDEX và đọc Cardinality theo từng Seq_in_index. Xác định cardinality của tiền tố một cột và hai cột.

### Bài 3: Đọc InnoDB persistent stats

Truy vấn mysql.innodb_table_stats và mysql.innodb_index_stats. Tìm n_rows, n_diff_pfxNN, n_leaf_pages và size. So sánh số page với dung lượng metadata.

### Bài 4: Cập nhật thống kê

Nạp thêm nhiều hàng với phân bố status khác hẳn dữ liệu ban đầu. Chạy EXPLAIN trước và sau ANALYZE TABLE. Ghi nhận rows ước lượng và kế hoạch.

### Bài 5: Sampling pages

Trên môi trường lab, thay đổi STATS_SAMPLE_PAGES của bảng hoặc innodb_stats_persistent_sample_pages. Chạy ANALYZE TABLE nhiều lần và so sánh cardinality, thời gian phân tích. Không thực hiện thay đổi global trên production chỉ để thử.

### Bài 6: Histogram cho cột lệch

Tạo dữ liệu status có một giá trị chiếm phần lớn và một giá trị hiếm. Chạy EXPLAIN cho từng giá trị trước khi tạo histogram, sau đó UPDATE HISTOGRAM và chạy lại. So sánh estimated rows.

### Bài 7: Xem metadata histogram

Truy vấn INFORMATION_SCHEMA.COLUMN_STATISTICS, dùng JSON_PRETTY để xem histogram JSON. Xác định histogram-type, sampling-rate và số bucket. Sau đó DROP HISTOGRAM và xác nhận metadata đã thay đổi.

### Bài 8: So sánh estimate và actual

Chạy EXPLAIN ANALYZE cho truy vấn có predicate lệch phân bố. Ghi lại estimated rows, actual rows và loops. Giải thích vì sao sai lệch có thể làm JOIN order hoặc access path kém hiệu quả.

### Bài 9: Runtime index usage

Chạy workload đại diện, đọc performance_schema.table_io_waits_summary_by_index_usage và sys.schema_unused_indexes. Xác định index nào được sử dụng. Khởi động lại lab hoặc reset summary để hiểu ảnh hưởng của thời gian quan sát.

### Bài 10: Báo cáo chẩn đoán

Viết báo cáo ngắn cho một truy vấn chậm, gồm:
- Schema và index liên quan.
- Thống kê bảng/index hiện tại.
- Histogram có hay không.
- EXPLAIN và EXPLAIN ANALYZE.
- Runtime index usage.
- Hành động cập nhật stats hoặc thay đổi index.
- Kết quả đo trước/sau.

## 20. Checklist trước khi kết luận về thống kê

- [ ] Đã phân biệt metadata cấu trúc, optimizer statistics và runtime metrics.
- [ ] Đã hiểu TABLE_ROWS của InnoDB là ước lượng.
- [ ] Đã kiểm tra schema và engine trước khi đọc thống kê.
- [ ] Đã đọc SHOW INDEX và hiểu cardinality theo tiền tố.
- [ ] Đã xem mysql.innodb_table_stats và mysql.innodb_index_stats khi cần.
- [ ] Đã không chỉnh sửa trực tiếp các bảng thống kê hệ thống.
- [ ] Đã kiểm tra persistent/transient stats và auto recalc.
- [ ] Đã xem sample pages nếu cardinality không ổn định.
- [ ] Đã chạy ANALYZE TABLE sau thay đổi dữ liệu lớn khi cần.
- [ ] Đã phân biệt index statistics với histogram.
- [ ] Đã biết histogram là thống kê đơn cột và cần cập nhật riêng.
- [ ] Đã xem INFORMATION_SCHEMA.COLUMN_STATISTICS khi dùng histogram.
- [ ] Đã phân biệt Performance Schema với thống kê optimizer.
- [ ] Đã dùng EXPLAIN để đọc ước lượng.
- [ ] Đã dùng EXPLAIN ANALYZE để so sánh số liệu thực tế khi phù hợp.
- [ ] Đã xem xét tương quan giữa các cột và phân bố lệch.
- [ ] Đã đánh giá tác động vận hành trước khi ANALYZE hoặc đổi cấu hình.
- [ ] Đã đo workload thực tế trước khi thêm/xóa index.

## 21. Kết luận

Thống kê giúp MySQL Optimizer ước lượng chi phí và chọn kế hoạch thực thi. INFORMATION_SCHEMA.TABLES cung cấp quy mô và dung lượng ước lượng; SHOW INDEX và INFORMATION_SCHEMA.STATISTICS mô tả index cùng cardinality theo tiền tố; mysql.innodb_table_stats và mysql.innodb_index_stats lưu thống kê InnoDB persistent; histogram mô tả phân bố giá trị theo từng cột; Performance Schema và sys cho biết workload đã chạy thực tế ra sao.

Không nguồn nào thay thế được các nguồn còn lại. Hãy phân biệt ước lượng với số đếm chính xác, thống kê optimizer với runtime counters, và histogram với index vật lý. Sau khi dữ liệu thay đổi lớn, dùng ANALYZE TABLE hoặc cập nhật histogram có mục tiêu; sau đó so sánh EXPLAIN với EXPLAIN ANALYZE để kiểm tra sai lệch ước lượng. Chỉ thay đổi index hoặc cấu hình sau khi đã đo cả hiệu năng đọc, ghi và tác động vận hành.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – InnoDB Persistent Statistics](https://dev.mysql.com/doc/refman/8.4/en/innodb-persistent-stats.html)
- [MySQL 8.4 Reference Manual – Configuring Persistent Optimizer Statistics Parameters](https://dev.mysql.com/doc/refman/8.4/en/innodb-persistent-stats.html#innodb-persistent-stats-configuration)
- [MySQL 8.4 Reference Manual – InnoDB Transient Statistics](https://dev.mysql.com/doc/refman/8.4/en/innodb-statistics-estimation.html)
- [MySQL 8.4 Reference Manual – ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)
- [MySQL 8.4 Reference Manual – Optimizer Statistics](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html)
- [MySQL 8.4 Reference Manual – Optimizer Statistics: Histograms](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html#optimizer-statistics-histograms)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA TABLES](https://dev.mysql.com/doc/refman/8.4/en/information-schema-tables-table.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA STATISTICS](https://dev.mysql.com/doc/refman/8.4/en/information-schema-statistics-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Information Schema Tables](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-system-tables.html)
- [MySQL 8.4 Reference Manual – Performance Schema Table I/O Wait Summary Tables](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-table-wait-summary-tables.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizer Trace](https://dev.mysql.com/doc/refman/8.4/en/optimizer-tracing.html)


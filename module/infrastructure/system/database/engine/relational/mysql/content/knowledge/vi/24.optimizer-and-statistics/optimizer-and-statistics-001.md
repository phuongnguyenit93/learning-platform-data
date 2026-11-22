# Cost-based optimizer và các đầu vào lựa chọn kế hoạch

MySQL không thực thi một câu SELECT theo đúng thứ tự các bảng và điều kiện xuất hiện trong câu SQL. Trước khi chạy, optimizer phân tích câu truy vấn, xem xét schema và thống kê dữ liệu, tạo các phương án thực thi khả thi rồi ước lượng chi phí để chọn kế hoạch. Cách tiếp cận này được gọi là cost-based optimization (tối ưu dựa trên chi phí).

Một kế hoạch có thể dùng table scan, index lookup, range scan, index merge, thay đổi thứ tự JOIN, materialize subquery hoặc tận dụng index để sắp xếp. Mỗi lựa chọn có chi phí khác nhau. Optimizer ước lượng số hàng cần đọc, số hàng còn lại sau bộ lọc, số lần lặp của nested loop, chi phí truy cập trang dữ liệu và chi phí xử lý. Nó không biết chính xác thời gian chạy tương lai; kết quả phụ thuộc chất lượng thống kê và mô hình chi phí.

Hiểu các đầu vào của optimizer giúp giải thích vì sao cùng một câu SQL có thể có kế hoạch khác nhau sau khi dữ liệu tăng, phân bố giá trị thay đổi, index được thêm hoặc thống kê được cập nhật. Bài học này trình bày các đầu vào chính, cách đọc ước lượng và cách xác minh kế hoạch bằng EXPLAIN, EXPLAIN ANALYZE và optimizer trace.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cost-based optimizer và phân biệt estimated cost với thời gian chạy thực tế.
- Nhận diện ảnh hưởng của câu SQL, schema, index, constraint và storage engine đến kế hoạch.
- Hiểu cardinality, selectivity, fanout và số hàng ước lượng.
- Giải thích vai trò của table statistics, index statistics và histogram.
- Cập nhật thống kê bằng ANALYZE TABLE và quản lý histogram.
- Hiểu persistent statistics và giới hạn của lấy mẫu thống kê.
- Phân tích lựa chọn table scan, index access, range scan, join order và join algorithm.
- Đọc các trường rows, filtered, key, type, Extra và cost trong EXPLAIN.
- So sánh ước lượng với số hàng/thời gian thực tế bằng EXPLAIN ANALYZE.
- Dùng optimizer trace để xem các phương án và lý do lựa chọn.
- Nhận biết các giới hạn của thống kê một cột, dữ liệu lệch và tương quan giữa cột.
- Xử lý kế hoạch kém bằng cách kiểm tra nguyên nhân trước khi ép index hoặc dùng optimizer hint.

## 1. Cost-based optimizer làm gì?

Optimizer nhận câu SQL và metadata liên quan, sau đó xác định các phép biến đổi hợp lệ và các phương án truy cập dữ liệu. Nó ước lượng chi phí của từng phương án mà nó xem xét và chọn một kế hoạch theo mô hình chi phí.

Ví dụ câu truy vấn:

    SELECT
        order_id,
        customer_id,
        order_date,
        total_amount
    FROM sales_order
    WHERE customer_id = 1001
      AND order_date >= '2025-01-01'
    ORDER BY order_date DESC
    LIMIT 20;

Optimizer có thể cân nhắc:

- Quét toàn bộ bảng rồi lọc customer_id và order_date.
- Dùng index trên customer_id, sau đó lọc order_date.
- Dùng index ghép bắt đầu bằng customer_id rồi đến order_date.
- Dùng một index có thể bao phủ toàn bộ cột cần trả về.
- Chọn hướng quét index phù hợp với ORDER BY và LIMIT.

Nếu bảng rất nhỏ, table scan có thể rẻ hơn index lookup. Nếu bảng có hàng triệu hàng và điều kiện chọn rất ít hàng, index range scan thường có lợi hơn. Không có quy tắc “có index thì luôn dùng index”; optimizer so sánh chi phí của các phương án dựa trên thống kê và cost model.

### 1.1. Cost không phải milliseconds

Giá trị cost trong EXPLAIN là đơn vị chi phí nội bộ của optimizer. Nó không phải số milliseconds dự đoán chính xác, cũng không thể so sánh trực tiếp với thời gian của một câu truy vấn khác nếu môi trường, cấu hình hoặc mô hình chi phí khác nhau.

Cost giúp optimizer so sánh các phương án trong cùng bối cảnh. Thời gian thực tế còn phụ thuộc:

- Dữ liệu có nằm trong buffer pool hoặc cache hệ điều hành hay không.
- I/O, CPU, bộ nhớ và mức tải đồng thời.
- Lock wait, metadata lock và network latency.
- Kích thước kết quả và tốc độ client tiêu thụ dữ liệu.
- Cấu hình server, storage engine và phiên bản MySQL.

Vì vậy, một kế hoạch có estimated cost thấp chưa chắc luôn có thời gian chạy thấp trong mọi tình huống. Hãy dùng EXPLAIN để hiểu lựa chọn và đo thời gian thực tế trên workload phù hợp.

### 1.2. Cost-based không có nghĩa thử mọi kế hoạch có thể

Số cách nối bảng tăng rất nhanh theo số bảng. Optimizer sử dụng chiến lược tìm kiếm và pruning để giới hạn không gian kế hoạch. Nó đánh giá các phương án mà quá trình tối ưu hóa tạo ra; không đảm bảo đã duyệt mọi thứ tự và mọi cách thực thi có thể có.

Do đó, kế hoạch được chọn là phương án tốt nhất theo thông tin, mô hình và không gian tìm kiếm mà optimizer sử dụng. Nếu ước lượng cardinality sai hoặc một phương án tốt không được xem xét, kế hoạch cuối cùng vẫn có thể kém.

## 2. Ba nhóm đầu vào chính

Có thể chia đầu vào lựa chọn kế hoạch thành ba nhóm:

| Nhóm | Ví dụ | Ảnh hưởng |
|---|---|---|
| Câu SQL và ngữ nghĩa | JOIN, WHERE, ORDER BY, GROUP BY, LIMIT, subquery, biểu thức | Xác định phép toán và các phương án hợp lệ |
| Schema và cấu trúc lưu trữ | Kiểu dữ liệu, NULL, primary/unique key, index, partition, storage engine | Xác định access path và ràng buộc dữ liệu |
| Thống kê và cost model | Row count, index cardinality, histogram, page count, cost constants | Ước lượng số hàng và chi phí từng phương án |

Optimizer còn chịu ảnh hưởng bởi phiên bản MySQL, optimizer switches, optimizer hints, session variables và một số thiết lập tương thích. Những thiết lập này có thể bật/tắt hoặc hướng dẫn một chiến lược, nhưng không thay thế việc thiết kế SQL, index và thống kê phù hợp.

## 3. Đầu vào từ câu SQL

### 3.1. Điều kiện lọc

Optimizer phân tích các điều kiện WHERE và điều kiện JOIN để xác định có thể dùng index hoặc loại bỏ hàng sớm đến mức nào.

Ví dụ điều kiện equality:

    WHERE customer_id = 1001

Điều kiện range:

    WHERE order_date >= '2025-01-01'
      AND order_date < '2025-02-01'

Điều kiện nhiều cột:

    WHERE customer_id = 1001
      AND order_status = 'PAID'

Điều kiện equality thường cho phép định vị một vùng index hẹp. Điều kiện range có thể đọc một dải index. Điều kiện trên nhiều cột có thể tận dụng index ghép nếu thứ tự cột phù hợp.

### 3.2. Sargability và biểu thức trên cột

Một predicate có tính sargable khi optimizer có thể sử dụng nó để định vị vùng index hiệu quả. Ví dụ:

    WHERE created_at >= '2025-01-01'
      AND created_at <  '2025-02-01'

thường thân thiện với B-tree index trên created_at hơn:

    WHERE DATE(created_at) = '2025-01-15'

Biểu thức hàm áp dụng trực tiếp lên cột có thể khiến index thông thường không dùng được để định vị range. Nếu cần tìm theo biểu thức lặp lại, cân nhắc generated column được index hoặc functional index khi phiên bản hỗ trợ.

Một số dạng điều kiện khác cũng ảnh hưởng khả năng dùng index:

- So sánh hai kiểu dữ liệu khác nhau có thể cần chuyển đổi.
- LIKE 'abc%' có thể tận dụng một range trên index chuỗi trong điều kiện phù hợp; LIKE '%abc' thường không thể định vị bằng prefix B-tree thông thường.
- OR giữa các cột có thể khiến optimizer cân nhắc index merge hoặc table scan.
- NOT, biểu thức phức tạp và hàm không phù hợp có thể làm giảm khả năng dùng index.
- Collation và kiểu so sánh ảnh hưởng tập giá trị khớp.

Không phải mọi biểu thức đều khiến index vô dụng. Cần xem EXPLAIN trên câu truy vấn và schema thật.

### 3.3. JOIN và thứ tự nối

Trong truy vấn nhiều bảng, optimizer có thể thay đổi thứ tự join so với thứ tự viết trong FROM. Nó ước lượng số hàng sau từng bước nối để quyết định bảng nào nên được truy cập trước.

Ví dụ:

    SELECT
        c.customer_name,
        o.order_id,
        o.total_amount
    FROM customer AS c
    JOIN sales_order AS o
        ON o.customer_id = c.customer_id
    WHERE c.country_code = 'VN'
      AND o.order_status = 'PAID';

Nếu country_code = 'VN' chỉ chọn một phần nhỏ customer, bắt đầu từ customer có thể tốt. Nếu điều kiện order_status = 'PAID' chọn rất ít đơn hàng, bắt đầu từ sales_order có thể tốt hơn. Kết quả phụ thuộc thống kê và index của cả hai phía.

### 3.4. ORDER BY, GROUP BY và LIMIT

ORDER BY có thể dùng index nếu thứ tự cột và hướng sắp xếp tương thích với index và điều kiện lọc. Nếu không, MySQL có thể phải sort kết quả.

GROUP BY có thể dùng index hoặc cần temporary table/sort tùy cấu trúc và kế hoạch. LIMIT có thể làm một access path dừng sớm sau khi lấy đủ hàng, khiến index hỗ trợ lọc và sắp xếp trở nên có lợi.

Ví dụ:

    SELECT order_id, order_date
    FROM sales_order
    WHERE customer_id = 1001
    ORDER BY order_date DESC
    LIMIT 20;

Index (customer_id, order_date) có thể giúp tìm đơn của khách hàng và đọc theo thứ tự ngày mà không cần sort riêng. Optimizer vẫn phải cân nhắc selectivity, hướng quét và chi phí lookup.

### 3.5. Subquery và derived table

Optimizer có thể biến đổi một số subquery thành semijoin, materialize kết quả trung gian hoặc merge derived table vào query block bên ngoài. Việc biến đổi phụ thuộc cấu trúc truy vấn, ngữ nghĩa NULL, DISTINCT, GROUP BY, LIMIT và các ràng buộc khác.

Ví dụ:

    SELECT c.customer_id, c.customer_name
    FROM customer AS c
    WHERE EXISTS (
        SELECT 1
        FROM sales_order AS o
        WHERE o.customer_id = c.customer_id
          AND o.order_status = 'PAID'
    );

Optimizer có thể áp dụng chiến lược semijoin phù hợp thay vì thực thi subquery độc lập theo cách đơn giản. Dùng EXPLAIN FORMAT=TREE hoặc JSON để xem cấu trúc thực thi được chọn.

## 4. Đầu vào từ schema và cấu trúc dữ liệu

### 4.1. Kiểu dữ liệu và độ dài

Kiểu dữ liệu ảnh hưởng cách so sánh, kích thước index, chi phí đọc và khả năng chuyển đổi. Ví dụ, khóa JOIN giữa hai bảng nên có kiểu tương thích; không nên nối BIGINT với VARCHAR chứa số nếu có thể chuẩn hóa schema.

Kích thước hàng và index ảnh hưởng số trang cần đọc. Index có key nhỏ thường chứa được nhiều entry hơn trên mỗi trang, nhưng kiểu dữ liệu phải đủ miền giá trị và phù hợp nghiệp vụ.

### 4.2. NULL và ràng buộc

NOT NULL, UNIQUE, PRIMARY KEY và các constraint cung cấp thông tin về dữ liệu và ngữ nghĩa. Unique key cho phép optimizer biết một điều kiện equality có thể trả về tối đa một hàng trong những điều kiện phù hợp. Primary key xác định định danh duy nhất của hàng.

Ràng buộc đúng giúp cả tính toàn vẹn dữ liệu lẫn tối ưu truy vấn. Không khai báo UNIQUE chỉ để “gợi ý” optimizer nếu dữ liệu nghiệp vụ thực tế cho phép trùng; constraint phải phản ánh quy tắc thật.

### 4.3. Index và thứ tự cột

Index là một trong những đầu vào quan trọng nhất của optimizer. Nó cung cấp access path thay thế table scan, đồng thời mang thống kê về phân bố key.

Với index ghép:

    CREATE INDEX idx_order_customer_date
    ON sales_order (customer_id, order_date);

Index này có thể hỗ trợ:

    WHERE customer_id = 1001

và:

    WHERE customer_id = 1001
      AND order_date >= '2025-01-01'

Nhưng không thể giả định index trên luôn hiệu quả cho truy vấn chỉ lọc order_date mà không có customer_id. B-tree composite index chủ yếu hỗ trợ leftmost prefix.

### 4.4. Covering index

Nếu index chứa tất cả cột cần cho truy vấn, MySQL có thể đọc kết quả từ index mà không cần lookup hàng trong clustered index. Đây là covering index.

Ví dụ:

    CREATE INDEX idx_order_customer_date_amount
    ON sales_order (customer_id, order_date, total_amount);

    SELECT order_date, total_amount
    FROM sales_order
    WHERE customer_id = 1001
    ORDER BY order_date DESC
    LIMIT 20;

Index có thể bao phủ các cột truy vấn. Tuy nhiên, index lớn hơn chiếm dung lượng và tăng chi phí INSERT/UPDATE/DELETE. Không thêm mọi cột vào index chỉ để tránh table lookup; hãy đo workload đọc/ghi và kích thước dữ liệu.

### 4.5. Storage engine

Storage engine cung cấp thông tin và chi phí truy cập riêng. InnoDB có clustered primary key, secondary index trỏ về primary key, buffer pool và thống kê index riêng. Optimizer kết hợp chi phí ở server layer với thông tin/chi phí từ storage engine để so sánh phương án.

Hai bảng có cùng số hàng nhưng engine, kích thước index, cache residency và cấu trúc lưu trữ khác nhau có thể dẫn đến cost khác nhau.

## 5. Cardinality, selectivity và fanout

Đây là các khái niệm cốt lõi để hiểu ước lượng của optimizer.

### 5.1. Cardinality

Cardinality của một cột/index key thường nói đến số giá trị phân biệt (distinct values) mà thống kê ước lượng. Với index ghép, thống kê có thể có cardinality cho các prefix của index.

Ví dụ bảng có 1.000.000 đơn:

- order_status chỉ có 4 giá trị phân biệt.
- customer_id có 100.000 khách hàng phân biệt.
- order_id là primary key có 1.000.000 giá trị phân biệt.

Điều kiện equality trên order_id thường rất chọn lọc. Điều kiện order_status = 'PAID' có thể chọn một phần lớn bảng.

Cardinality hiển thị trong SHOW INDEX là ước lượng, không nhất thiết là số đếm chính xác.

### 5.2. Selectivity

Selectivity mô tả tỷ lệ hàng thỏa một điều kiện. Một predicate có selectivity thấp thường chọn ít hàng; selectivity cao thường giữ lại nhiều hàng. Tài liệu và công cụ có thể dùng quy ước diễn đạt khác nhau, nên khi đọc hãy tập trung vào số hàng ước lượng và tỷ lệ còn lại.

Ví dụ bảng có 1.000.000 hàng:

- customer_id = 1001 có thể chỉ khớp 12 hàng.
- order_status = 'PAID' có thể khớp 700.000 hàng.

Điều kiện customer_id thường chọn lọc hơn. Dùng index để tìm 12 hàng có thể rẻ hơn quét toàn bảng; nhưng dùng index để lấy 700.000 hàng rồi lookup từng row có thể đắt hơn table scan.

### 5.3. Fanout

Fanout là số hàng trung bình mà một bước join tạo ra cho mỗi hàng đầu vào, hoặc mức mở rộng hàng qua một phép nối. Nếu một khách hàng trung bình có 20 đơn, nối customer với sales_order có thể tạo khoảng 20 hàng cho mỗi customer phù hợp.

Ước lượng fanout sai ở bước đầu có thể lan sang các bước join sau. Một sai lệch nhỏ ở nhiều bước có thể khiến optimizer đánh giá sai toàn bộ kế hoạch.

### 5.4. Tương quan giữa các cột

Giả sử order_status = 'CANCELLED' thường xuất hiện ở một số region cụ thể. Nếu optimizer chỉ có thống kê riêng lẻ của order_status và region_id, nó có thể giả định mức độc lập gần đúng giữa hai predicate và ước lượng sai khi chúng có tương quan mạnh.

Histogram của MySQL là thống kê theo từng cột; nó không mô tả đầy đủ phân bố kết hợp của nhiều cột. Composite index có thống kê prefix hữu ích cho một số truy vấn nhiều cột, nhưng không thay thế được thống kê đa biến tổng quát.

Khi predicates tương quan mạnh, hãy kiểm tra estimated rows so với actual rows và đánh giá index ghép hoặc cách mô hình hóa dữ liệu phù hợp.

## 6. Table statistics và index statistics của InnoDB

Optimizer cần ước lượng quy mô bảng và phân bố key. Với InnoDB, thống kê được lấy từ metadata và quá trình lấy mẫu index page.

Các thông tin thường có:

- Số hàng ước lượng trong bảng.
- Số trang dữ liệu và index.
- Số giá trị phân biệt của index key/prefix.
- Số record trung bình cho mỗi key.
- Các thống kê phục vụ ước lượng range và lookup.

Vì InnoDB thường dùng lấy mẫu thay vì đếm toàn bộ dữ liệu cho mọi thống kê, giá trị ước lượng có thể sai khác so với COUNT(*) hoặc dữ liệu thực tế. Kết quả lấy mẫu cũng có thể thay đổi theo kích thước sample và trạng thái dữ liệu.

### 6.1. Xem thống kê index

    SHOW INDEX FROM sales_order;

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| Key_name | Tên index |
| Seq_in_index | Vị trí cột trong index ghép |
| Column_name | Cột thuộc index |
| Non_unique | Index có cho phép trùng key hay không |
| Cardinality | Số giá trị phân biệt ước lượng cho prefix |
| Sub_part | Độ dài prefix nếu index một phần |
| Index_type | Kiểu index, thường là BTREE với index thông thường |

Cardinality là ước lượng và có thể NULL khi thống kê chưa có hoặc không áp dụng. Đừng dùng con số này như một phép đếm chính xác.

### 6.2. Xem thống kê InnoDB persistent

Trong MySQL, persistent InnoDB statistics có thể được lưu trong các bảng hệ thống:

    SELECT *
    FROM mysql.innodb_table_stats
    WHERE database_name = DATABASE()
      AND table_name = 'sales_order';

    SELECT *
    FROM mysql.innodb_index_stats
    WHERE database_name = DATABASE()
      AND table_name = 'sales_order';

Các bảng này cung cấp thông tin như số hàng ước lượng, số trang, cardinality theo index prefix và thời điểm cập nhật thống kê. Cần quyền phù hợp để đọc schema mysql.

Persistent statistics giúp thống kê tồn tại qua lần restart thay vì chỉ dựa vào thống kê tạm. Thiết lập liên quan gồm innodb_stats_persistent, innodb_stats_auto_recalc và innodb_stats_persistent_sample_pages. Giá trị mặc định và hành vi có thể khác theo phiên bản/cấu hình; hãy kiểm tra biến thực tế:

    SHOW VARIABLES LIKE 'innodb_stats_persistent';
    SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
    SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';

Không thay đổi sample pages toàn cục chỉ vì một query có kế hoạch kém. Trước hết xác định thống kê nào sai, phạm vi bảng nào bị ảnh hưởng và chi phí của việc lấy mẫu bổ sung.

### 6.3. ANALYZE TABLE cập nhật thống kê

Sau khi tải dữ liệu lớn, xóa nhiều hàng hoặc thay đổi phân bố dữ liệu đáng kể, có thể cập nhật thống kê:

    ANALYZE TABLE sales_order;

ANALYZE TABLE yêu cầu storage engine cập nhật thống kê index/table. Với InnoDB dùng persistent stats, việc phân tích lại có thể giúp optimizer có ước lượng mới hơn.

Lưu ý:

- ANALYZE TABLE không sửa dữ liệu nghiệp vụ.
- Thống kê vẫn là ước lượng, không phải bản đếm chính xác toàn bộ giá trị.
- Cập nhật thống kê có thể làm kế hoạch truy vấn thay đổi.
- Chạy trên production cần xem tải, metadata lock và thời gian thực hiện.
- Không chạy liên tục theo lịch quá dày nếu không có lý do và đánh giá tác động.

Sau khi ANALYZE, kiểm tra lại SHOW INDEX và EXPLAIN. Không giả định rằng mọi truy vấn sẽ nhanh hơn; kế hoạch có thể thay đổi theo hướng khác.

## 7. Histogram: thống kê phân bố của một cột

Index cardinality cho biết số giá trị phân biệt ước lượng, nhưng không mô tả đầy đủ phân bố. Ví dụ một cột có 4 trạng thái, trong đó PAID chiếm 70%, PENDING chiếm 20%, CANCELLED chiếm 9% và REFUNDED chiếm 1%. Chỉ biết có 4 giá trị là chưa đủ để ước lượng một predicate cụ thể.

Histogram bổ sung thông tin phân bố giá trị của một cột. MySQL có thể dùng histogram để cải thiện ước lượng selectivity, đặc biệt với cột không có index phù hợp hoặc các điều kiện mà thống kê index không cung cấp đủ thông tin.

MySQL hỗ trợ hai loại histogram chính:

- Singleton histogram: lưu các giá trị riêng lẻ và tần suất tương ứng.
- Equi-height histogram: chia dữ liệu thành các bucket có số lượng quan sát gần tương đương, mô tả biên và phân bố trong bucket.

Số bucket tối đa và cách tạo histogram phụ thuộc phiên bản; MySQL 8.0 cho phép yêu cầu tối đa 1024 bucket.

### 7.1. Tạo histogram

Ví dụ tạo histogram cho cột order_status:

    ANALYZE TABLE sales_order
    UPDATE HISTOGRAM ON order_status
    WITH 32 BUCKETS;

Có thể yêu cầu histogram cho nhiều cột trong cùng câu lệnh:

    ANALYZE TABLE sales_order
    UPDATE HISTOGRAM ON order_status, sales_channel
    WITH 64 BUCKETS;

Histogram được tạo riêng cho từng cột. Đây không phải histogram đa chiều của tổ hợp order_status và sales_channel.

### 7.2. Xem histogram

MySQL lưu thông tin histogram trong INFORMATION_SCHEMA.COLUMN_STATISTICS:

    SELECT
        SCHEMA_NAME,
        TABLE_NAME,
        COLUMN_NAME,
        HISTOGRAM
    FROM information_schema.column_statistics
    WHERE SCHEMA_NAME = DATABASE()
      AND TABLE_NAME = 'sales_order';

HISTOGRAM là JSON chứa loại histogram, số bucket, số null, số giá trị phân biệt và thông tin phân bố tương ứng.

### 7.3. Xóa histogram

Nếu histogram không còn phù hợp hoặc muốn optimizer quay về nguồn thống kê khác:

    ANALYZE TABLE sales_order
    DROP HISTOGRAM ON order_status;

Xóa histogram không xóa index trên cột và không xóa dữ liệu. Nó chỉ bỏ thống kê histogram đã lưu cho cột.

### 7.4. Histogram cần được cập nhật khi phân bố đổi

Histogram phản ánh dữ liệu tại thời điểm được tạo/cập nhật. Nếu dữ liệu thay đổi đáng kể, histogram cũ có thể không còn đại diện cho phân bố hiện tại. Hãy xác định chính sách cập nhật dựa trên tốc độ biến động dữ liệu và workload.

Không giả định ANALYZE TABLE thông thường luôn tự làm mới mọi histogram hiện có theo cách mong muốn; khi cần cập nhật histogram, dùng cú pháp UPDATE HISTOGRAM rõ ràng và kiểm tra metadata sau đó.

### 7.5. Giới hạn của histogram

- Histogram là thống kê theo một cột, không mô tả đầy đủ tương quan giữa nhiều cột.
- Histogram không tạo access path như index; nó cải thiện ước lượng, không tự làm truy vấn đọc ít trang hơn.
- Histogram không bảo đảm optimizer sẽ chọn index hoặc một kế hoạch cụ thể.
- Histogram có thể kém đại diện nếu số bucket nhỏ so với độ đa dạng hoặc dữ liệu thay đổi nhanh.
- Khi cột có index, optimizer còn có index statistics và các phương pháp ước lượng riêng; không xem histogram là nguồn duy nhất.

## 8. Cost model của MySQL

Sau khi ước lượng số hàng và các phép toán, optimizer cần mô hình chi phí để so sánh phương án. Cost model có thể tính đến:

- Chi phí đọc trang dữ liệu hoặc index.
- Chi phí tìm kiếm và truy cập record.
- Chi phí CPU để xử lý điều kiện và biểu thức.
- Chi phí tạo hoặc đọc temporary table.
- Chi phí sort, join và materialization.
- Chi phí do storage engine cung cấp.

MySQL tách một số chi phí thành hai nhóm:

- Server cost: chi phí ở SQL/server layer.
- Engine cost: chi phí do storage engine cung cấp.

Trong MySQL 8.0, các bảng mysql.server_cost và mysql.engine_cost chứa các cost constant mà optimizer sử dụng. Có thể xem để hiểu cấu hình:

    SELECT *
    FROM mysql.server_cost;

    SELECT *
    FROM mysql.engine_cost;

Một số hàng có thể dùng default_value nếu cost constant chưa được tùy chỉnh. Các giá trị cost là thông số mô hình, không phải benchmark milliseconds.

### 8.1. Không tự ý chỉnh cost constants

Có thể tùy chỉnh cost constants trong một số môi trường, nhưng việc này tác động rộng đến lựa chọn kế hoạch. Một giá trị được điều chỉnh để cải thiện một workload có thể làm workload khác chọn kế hoạch tệ hơn.

Trước khi thay đổi:

1. Xác định nhiều truy vấn đại diện và vấn đề cụ thể.
2. Lưu lại kế hoạch và thời gian thực tế trước thay đổi.
3. Kiểm tra index, thống kê và cấu hình buffer pool trước.
4. Thử trong môi trường staging có workload gần production.
5. Thay đổi có kiểm soát, theo dõi nhiều query digest và chuẩn bị cách quay lại.

Không cập nhật trực tiếp cost constants như một cách chữa một câu query đơn lẻ. Trong đa số trường hợp, sửa SQL, index hoặc thống kê là hướng ít rủi ro hơn.

## 9. Optimizer chọn access path

Access path là cách MySQL lấy hàng từ một bảng hoặc index.

### 9.1. Table scan

Table scan đọc các hàng của bảng để kiểm tra điều kiện. Nó có thể hợp lý khi:

- Bảng nhỏ.
- Điều kiện chọn phần lớn hàng.
- Index lookup cần nhiều lần truy cập random.
- Truy vấn cần nhiều cột và index không bao phủ.
- Thống kê cho thấy table scan có chi phí thấp hơn.

Không xem ALL trong EXPLAIN là lỗi tự động. Với bảng nhỏ hoặc truy vấn trả phần lớn bảng, table scan có thể là kế hoạch đúng.

### 9.2. Index lookup và range scan

Index lookup tìm các key phù hợp rồi lấy hàng. Range scan đọc một vùng key liên tiếp theo điều kiện.

Ví dụ:

    SELECT order_id, order_date
    FROM sales_order
    WHERE customer_id = 1001
      AND order_date >= '2025-01-01'
      AND order_date < '2025-02-01';

Index (customer_id, order_date) có thể tìm đúng vùng khách hàng và ngày.

### 9.3. Index merge

Khi có nhiều index đơn phù hợp với các điều kiện OR/AND, optimizer có thể cân nhắc kết hợp kết quả từ nhiều index. EXPLAIN có thể hiển thị type = index_merge.

Index merge không phải lúc nào cũng tốt hơn index ghép. Nếu một truy vấn thường lọc theo cùng một tổ hợp cột, composite index phù hợp có thể giảm số thao tác hơn. Hãy so sánh số hàng, cost và actual time.

### 9.4. Covering index

Khi mọi cột cần thiết có trong index, MySQL có thể tránh đọc hàng từ clustered index. Trong EXPLAIN truyền thống, Extra có thể hiển thị Using index.

Covering index giúp giảm lookup nhưng tăng kích thước index và chi phí ghi. Cần chọn cột theo workload thực tế.

### 9.5. Index Condition Pushdown

Index Condition Pushdown (ICP) cho phép storage engine kiểm tra một số điều kiện trên index entry trước khi đọc full row. EXPLAIN có thể hiển thị Using index condition.

ICP có thể giảm số lần đọc full row, nhưng không có nghĩa toàn bộ predicate đã được giải quyết chỉ bằng index. Hãy đọc key, key_len, Extra và kế hoạch thực thi đầy đủ.

## 10. Optimizer chọn join order và join algorithm

Với nhiều bảng, optimizer ước lượng số hàng ở mỗi bước join. Nếu bước đầu tạo quá nhiều hàng, các bước sau có thể phải xử lý khối lượng lớn.

Ví dụ:

    SELECT
        c.customer_name,
        o.order_id,
        p.payment_status
    FROM customer AS c
    JOIN sales_order AS o
        ON o.customer_id = c.customer_id
    JOIN payment AS p
        ON p.order_id = o.order_id
    WHERE c.country_code = 'VN'
      AND p.payment_status = 'SETTLED';

Optimizer cân nhắc:

- Bảng nào có điều kiện lọc chọn lọc hơn.
- Có index nào hỗ trợ lookup sang bảng tiếp theo.
- Ước lượng số đơn trên mỗi khách hàng.
- Ước lượng số payment trên mỗi order.
- Chi phí của từng thứ tự nối và thuật toán nối.

MySQL có thể sử dụng nested-loop family và hash join trong các tình huống được hỗ trợ. Hash join được bổ sung trong MySQL 8.0.18; chi tiết thuật toán và các optimizer switch thay đổi theo phiên bản. Dùng EXPLAIN FORMAT=TREE để xem cấu trúc kế hoạch thực tế thay vì đoán thuật toán chỉ từ cú pháp SQL.

### 10.1. Estimated rows qua từng bước

Nếu một bước được ước lượng trả về 100 hàng và bước tiếp theo có fanout 10, optimizer có thể ước lượng khoảng 1.000 hàng sau bước nối. Nếu ước lượng đầu vào sai gấp 100 lần, tổng chi phí kế hoạch có thể sai đáng kể.

Khi đọc kế hoạch nhiều bảng, hãy xác định bước đầu tiên có chênh lệch lớn giữa estimated rows và actual rows. Đó thường là nơi sai lệch bắt đầu; các bước sau chỉ khuếch đại sai số.

## 11. Thực hành: tạo schema để quan sát lựa chọn kế hoạch

Tạo bảng khách hàng và đơn hàng trong database sandbox:

    CREATE TABLE optimizer_customer_demo (
        customer_id BIGINT UNSIGNED NOT NULL,
        customer_name VARCHAR(100) NOT NULL,
        country_code CHAR(2) NOT NULL,
        PRIMARY KEY (customer_id),
        KEY idx_optimizer_customer_country (country_code)
    ) ENGINE = InnoDB;

    CREATE TABLE optimizer_order_demo (
        order_id BIGINT UNSIGNED NOT NULL,
        customer_id BIGINT UNSIGNED NOT NULL,
        order_date DATETIME NOT NULL,
        order_status VARCHAR(20) NOT NULL,
        total_amount DECIMAL(12,2) NOT NULL,
        PRIMARY KEY (order_id),
        KEY idx_optimizer_order_customer (customer_id),
        KEY idx_optimizer_order_date (order_date),
        KEY idx_optimizer_order_status (order_status)
    ) ENGINE = InnoDB;

    INSERT INTO optimizer_customer_demo
        (customer_id, customer_name, country_code)
    VALUES
        (1001, 'An', 'VN'),
        (1002, 'Binh', 'VN'),
        (1003, 'Chi', 'SG'),
        (1004, 'Dung', 'US');

    INSERT INTO optimizer_order_demo
        (order_id, customer_id, order_date, order_status, total_amount)
    VALUES
        (5001, 1001, '2025-01-02 10:00:00', 'PAID',      120.00),
        (5002, 1001, '2025-01-05 11:00:00', 'PENDING',    80.00),
        (5003, 1002, '2025-01-08 12:00:00', 'PAID',      250.00),
        (5004, 1003, '2025-01-10 13:00:00', 'CANCELLED',  40.00),
        (5005, 1004, '2025-02-01 14:00:00', 'PAID',      500.00);

Với bảng rất nhỏ, optimizer có thể chọn table scan dù có index. Đây là điều bình thường: chi phí đọc vài hàng tuần tự có thể thấp hơn khởi tạo index lookup và đọc hàng riêng lẻ. Không dùng kết quả của bảng mẫu nhỏ để kết luận index không có ích trên dữ liệu lớn.

## 12. ANALYZE TABLE và xem kế hoạch trước/sau

Chạy:

    ANALYZE TABLE optimizer_customer_demo;
    ANALYZE TABLE optimizer_order_demo;

Sau đó xem index:

    SHOW INDEX FROM optimizer_order_demo;

Chạy EXPLAIN:

    EXPLAIN
    SELECT
        order_id,
        order_date,
        total_amount
    FROM optimizer_order_demo
    WHERE customer_id = 1001
      AND order_date >= '2025-01-01'
      AND order_date < '2025-02-01'
    ORDER BY order_date DESC
    LIMIT 20;

Optimizer có thể chọn index customer, date hoặc table scan tùy số hàng và thống kê. Với dữ liệu thực tế lớn hơn, thử index ghép:

    CREATE INDEX idx_optimizer_order_customer_date
    ON optimizer_order_demo (customer_id, order_date);

Sau khi tạo index, chạy EXPLAIN lại. Index ghép có thể hỗ trợ equality trên customer_id và range trên order_date; nhưng trên bảng nhỏ, optimizer vẫn có thể chọn table scan. Hãy đánh giá trên dữ liệu có quy mô và phân bố gần production.

## 13. Đọc EXPLAIN truyền thống

Ví dụ:

    EXPLAIN
    SELECT *
    FROM optimizer_order_demo
    WHERE customer_id = 1001;

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| id | Số định danh query block trong kết quả EXPLAIN |
| select_type | Loại SELECT như SIMPLE, PRIMARY, SUBQUERY, DERIVED |
| table | Bảng hoặc derived object được truy cập |
| partitions | Partition được dùng nếu bảng partitioned |
| type | Access type, ví dụ const, eq_ref, ref, range, index, ALL |
| possible_keys | Index có thể được cân nhắc |
| key | Index được chọn |
| key_len | Độ dài key được sử dụng |
| ref | Giá trị/cột dùng để so sánh với index |
| rows | Số hàng ước lượng cần đọc |
| filtered | Tỷ lệ phần trăm hàng còn lại sau điều kiện lọc bổ sung, ước lượng |
| Extra | Thông tin bổ sung như Using where, Using index, Using filesort |

### 13.1. Access type không phải bảng xếp hạng tuyệt đối

Các giá trị type thường gặp:

- system/const: bảng hoặc truy vấn được xác định rất nhỏ, thường tối đa một hàng theo điều kiện phù hợp.
- eq_ref: lookup unique key cho mỗi tổ hợp hàng trước đó.
- ref: lookup theo index không unique.
- range: đọc một vùng index.
- index: quét toàn bộ index.
- ALL: quét toàn bộ bảng.
- index_merge: kết hợp nhiều index.

Các type thường được xem là tốt khi truy vấn chọn ít hàng, nhưng không có type nào luôn tối ưu trong mọi workload. Một range scan trả về 90% bảng có thể đắt hơn table scan; ALL trên bảng vài hàng có thể hoàn toàn hợp lý.

### 13.2. rows và filtered

rows là số hàng ước lượng mà access method cần đọc ở bước đó. filtered là tỷ lệ phần trăm hàng còn lại sau điều kiện lọc mà EXPLAIN mô tả. Tích ước lượng rows và filtered/100 giúp hình dung số hàng được chuyển tiếp đến bước sau, nhưng phải đọc trong bối cảnh join order và query block.

Ví dụ nếu rows = 10.000 và filtered = 5.0, optimizer ước lượng khoảng 500 hàng còn lại sau bộ lọc ở bước đó.

Đây là ước lượng, không phải kết quả đếm thực tế.

### 13.3. Extra thường gặp

| Extra | Ý nghĩa khái quát |
|---|---|
| Using where | Có điều kiện lọc hàng |
| Using index | Có thể trả các cột cần từ index (covering access) |
| Using index condition | Có ICP để lọc bằng điều kiện trên index trước khi đọc full row |
| Using filesort | Cần bước sort riêng; không khẳng định dữ liệu chắc chắn được ghi ra file đĩa |
| Using temporary | Cần internal temporary table cho một phần xử lý |
| Using join buffer | Dùng join buffer cho chiến lược join phù hợp |

Using filesort không đồng nghĩa chắc chắn có lỗi hiệu năng. Nếu chỉ sort một tập nhỏ, chi phí có thể rất thấp. Using temporary cũng cần được đánh giá theo kích thước dữ liệu và loại phép toán.

## 14. EXPLAIN FORMAT=JSON và FORMAT=TREE

FORMAT=JSON cung cấp cấu trúc chi tiết hơn, gồm nested query blocks, access path, cost_info, rows_produced_per_join và thông tin index.

    EXPLAIN FORMAT=JSON
    SELECT
        c.customer_name,
        o.order_id
    FROM optimizer_customer_demo AS c
    JOIN optimizer_order_demo AS o
        ON o.customer_id = c.customer_id
    WHERE c.country_code = 'VN';

FORMAT=TREE thể hiện kế hoạch theo dạng cây, hữu ích để nhìn thứ tự iterator, filter, join và access method:

    EXPLAIN FORMAT=TREE
    SELECT
        c.customer_name,
        o.order_id
    FROM optimizer_customer_demo AS c
    JOIN optimizer_order_demo AS o
        ON o.customer_id = c.customer_id
    WHERE c.country_code = 'VN';

Không chỉ nhìn dòng cuối cùng. Hãy đọc từ các iterator đầu vào lên phía trên để hiểu dữ liệu đi qua từng bước.

## 15. EXPLAIN ANALYZE: so sánh ước lượng với thực tế

EXPLAIN thông thường hiển thị ước lượng của optimizer. MySQL 8.0.18 trở lên hỗ trợ EXPLAIN ANALYZE cho SELECT; câu truy vấn được thực thi và kết quả hiển thị actual timing, actual rows và số vòng lặp (loops) của iterator.

Ví dụ:

    EXPLAIN ANALYZE
    SELECT
        order_id,
        order_date,
        total_amount
    FROM optimizer_order_demo
    WHERE customer_id = 1001
      AND order_date >= '2025-01-01'
      AND order_date < '2025-02-01';

Output có thể chứa dạng:

    -> Index range scan on optimizer_order_demo
       (cost=... rows=...)
       (actual time=... rows=... loops=...)

Đây chỉ là hình dạng minh họa; số liệu thực tế phụ thuộc server, dữ liệu và kế hoạch.

### 15.1. Đọc actual rows và loops

- Estimated rows cho biết optimizer dự đoán số hàng.
- Actual rows cho biết iterator thực tế trả bao nhiêu hàng trong mỗi vòng lặp.
- Loops cho biết iterator được thực hiện bao nhiêu lần.
- Actual time cho biết thời gian thực tế được đo cho iterator theo output của MySQL.

Một iterator có actual rows = 5 và loops = 100 có thể đã xử lý khoảng 500 hàng qua các lần lặp, tùy cách đọc output. Với nested loop, loops ở phía trong thường phản ánh số lần được gọi cho mỗi hàng đầu vào từ phía ngoài.

### 15.2. Tìm điểm sai lệch đầu tiên

Giả sử optimizer ước lượng một predicate trả 100 hàng nhưng thực tế trả 50.000 hàng. Join tiếp theo có thể lặp nhiều hơn dự kiến, khiến kế hoạch ban đầu trở nên đắt.

Khi phân tích:

1. So sánh estimated rows và actual rows ở iterator đầu tiên.
2. Tìm predicate hoặc cột có phân bố không được thống kê tốt.
3. Kiểm tra index cardinality và histogram.
4. Kiểm tra dữ liệu có skew hoặc correlation giữa nhiều cột không.
5. Cập nhật thống kê nếu cần rồi đo lại.
6. Nếu thống kê hợp lý mà kế hoạch vẫn kém, xem xét index, biểu thức SQL hoặc optimizer trace.

### 15.3. EXPLAIN ANALYZE có thực thi truy vấn

EXPLAIN ANALYZE không chỉ “xem kế hoạch”. Nó thực thi SELECT để thu thập actual timing và row counts. Truy vấn đắt có thể tiêu thụ CPU, I/O, bộ nhớ và gây tải tương tự truy vấn thật.

Không chạy EXPLAIN ANALYZE tùy tiện với truy vấn rất nặng trên production. Hãy giới hạn phạm vi, dùng staging hoặc bản sao dữ liệu, kiểm soát thời gian và đảm bảo câu SELECT không tạo tác động vận hành ngoài dự kiến.

## 16. Optimizer trace: xem quá trình lựa chọn

EXPLAIN cho biết kế hoạch cuối. Optimizer trace giúp xem một số phương án được xem xét, các ước lượng và lý do lựa chọn.

Bật trace trong session:

    SET optimizer_trace = 'enabled=on';

Chạy truy vấn cần phân tích:

    SELECT
        order_id,
        total_amount
    FROM optimizer_order_demo
    WHERE customer_id = 1001
      AND order_status = 'PAID';

Đọc trace:

    SELECT TRACE
    FROM information_schema.optimizer_trace;

Tắt trace sau khi hoàn tất:

    SET optimizer_trace = 'enabled=off';

Trace là JSON và có thể dài. Nó có thể cho thấy:

- Query block và các bước biến đổi.
- Candidate access methods.
- Ước lượng range và số hàng.
- Chi phí table scan so với index access.
- Thứ tự join được xem xét.
- Lý do một số phương án bị loại.

Không phải mọi chi tiết nội bộ đều được hiển thị cho mọi truy vấn. Dùng trace như công cụ chẩn đoán bổ sung, không phải output ổn định để ứng dụng parse.

## 17. Vì sao kế hoạch có thể thay đổi?

Kế hoạch không cố định vĩnh viễn. Nó có thể đổi khi một trong các đầu vào thay đổi:

- Số hàng tăng hoặc giảm.
- Phân bố giá trị thay đổi (ví dụ trạng thái PAID tăng từ 20% lên 90%).
- Index được thêm, xóa hoặc thay đổi thứ tự cột.
- ANALYZE TABLE cập nhật cardinality.
- Histogram được tạo, cập nhật hoặc xóa.
- Cấu hình cost model hoặc optimizer switch thay đổi.
- Phiên bản MySQL nâng cấp có optimizer transformation hoặc cost model khác.
- Schema, kiểu dữ liệu, collation hoặc constraint thay đổi.

Một query từng nhanh trên bảng 10.000 hàng có thể chậm khi bảng đạt 100 triệu hàng. Một index từng hữu ích có thể ít chọn lọc hơn khi phân bố dữ liệu thay đổi.

### 17.1. Thống kê cũ và dữ liệu lệch

Giả sử bảng có 10 triệu đơn:

- 8 triệu đơn PAID.
- 1,5 triệu đơn PENDING.
- 400 nghìn đơn CANCELLED.
- 100 nghìn đơn REFUNDED.

Nếu thống kê chỉ biết số giá trị phân biệt mà không biết tần suất, optimizer có thể ước lượng một trạng thái hiếm theo giả định không phù hợp. Histogram giúp mô tả phân bố rõ hơn.

Tuy nhiên, nếu phân bố đổi nhanh sau khi histogram được tạo, histogram cũ có thể khiến estimate sai. Cần theo dõi dữ liệu và cập nhật có chủ đích.

### 17.2. Thay đổi phiên bản

Nâng cấp MySQL có thể thay đổi:

- Các transformation được hỗ trợ.
- Cách tính cost hoặc thống kê.
- Thuật toán join.
- Quy tắc xử lý biểu thức, collation và kiểu dữ liệu.
- Optimizer switches và optimizer hints.

Sau nâng cấp, hãy so sánh kế hoạch và hiệu năng của các truy vấn quan trọng trên staging. Không giả định kế hoạch cũ sẽ giữ nguyên chỉ vì câu SQL và index không đổi.

## 18. Khi nào dùng histogram và khi nào cần index?

Histogram và index giải quyết hai vấn đề khác nhau:

| Công cụ | Mục tiêu chính | Tạo access path mới? |
|---|---|---|
| Index | Tìm và đọc hàng hiệu quả theo key | Có |
| Index statistics | Mô tả cardinality và phân bố key/prefix | Không, nhưng hỗ trợ ước lượng |
| Histogram | Mô tả phân bố giá trị của cột | Không |
| ANALYZE TABLE | Cập nhật thống kê table/index | Không trực tiếp |
| EXPLAIN ANALYZE | Đo actual rows/timing của kế hoạch | Không |

Ví dụ:

- Cần lọc nhanh order_date theo range trên bảng lớn: thường cần index phù hợp.
- Cần optimizer hiểu status = 'REFUNDED' chỉ chiếm 1% khi cột status chưa có index phù hợp: histogram có thể giúp estimate.
- Cần biết tại sao estimate 100 nhưng thực tế 50.000: EXPLAIN ANALYZE.
- Cần xem optimizer cân nhắc index nào và vì sao loại bỏ: optimizer trace.

Histogram không thay thế index. Ngược lại, thêm index không tự động giải quyết mọi sai lệch thống kê, đặc biệt với phân bố dữ liệu lệch hoặc tương quan giữa nhiều cột.

## 19. Optimizer switches và hints

MySQL có optimizer_switch để bật/tắt một số chiến lược tối ưu. Có thể xem cấu hình hiện tại:

    SELECT @@optimizer_switch;

Một số flag liên quan đến chiến lược như index_merge, derived_merge, materialization, semijoin, mrr hoặc index condition pushdown. Danh sách và mặc định thay đổi theo phiên bản.

Optimizer hint có thể hướng dẫn một query block hoặc bảng sử dụng/không sử dụng chiến lược hay index nhất định. Ví dụ:

    SELECT /*+ INDEX(o idx_optimizer_order_customer_date) */
        o.order_id,
        o.order_date
    FROM optimizer_order_demo AS o
    WHERE o.customer_id = 1001;

Hint là công cụ nâng cao. Nếu dùng hint để ép một kế hoạch, cần ghi lại lý do, workload mục tiêu, phiên bản, dữ liệu và cách theo dõi sau triển khai. Hint có thể trở nên bất lợi khi dữ liệu hoặc schema thay đổi.

Không dùng FORCE INDEX hoặc hint làm bước đầu tiên khi query chậm. Trước hết kiểm tra estimated rows, actual rows, index, thống kê và query predicate.

## 20. Quy trình chẩn đoán khi optimizer chọn kế hoạch kém

Khi một query chậm hoặc chọn access path đáng ngờ, đi theo trình tự:

1. Ghi lại câu SQL thực tế, tham số, session variables và phiên bản MySQL.
2. Chạy EXPLAIN để xác định access path, join order và estimated rows.
3. Chạy EXPLAIN FORMAT=JSON hoặc TREE để xem chi tiết.
4. Nếu an toàn, chạy EXPLAIN ANALYZE trên dữ liệu đại diện để lấy actual rows, loops và timing.
5. Tìm iterator đầu tiên có chênh lệch lớn giữa estimated và actual rows.
6. Kiểm tra SHOW INDEX, cardinality và các index prefix liên quan.
7. Kiểm tra ANALYZE TABLE, persistent statistics và histogram.
8. Xem dữ liệu có skew hoặc correlation giữa các predicate hay không.
9. Kiểm tra kiểu dữ liệu, implicit conversion, collation và biểu thức trên cột.
10. Đánh giá index ghép, covering index hoặc thay đổi cách viết predicate.
11. Dùng optimizer trace nếu chưa rõ vì sao phương án bị loại.
12. Đo lại trên cùng dữ liệu, tham số và điều kiện tải; so sánh cả latency lẫn tài nguyên.

Không thay nhiều yếu tố cùng lúc. Nếu đồng thời đổi index, histogram và optimizer hint, sẽ khó xác định yếu tố nào cải thiện hoặc làm xấu kế hoạch.

## 21. Ví dụ chẩn đoán ước lượng sai

Giả sử truy vấn:

    SELECT order_id, total_amount
    FROM sales_order
    WHERE order_status = 'REFUNDED';

EXPLAIN ước lượng 500.000 hàng nhưng EXPLAIN ANALYZE cho thấy chỉ có 10.000 hàng. Một số khả năng:

- Index statistics cũ sau khi dữ liệu thay đổi.
- Histogram chưa có hoặc không còn đại diện.
- Phân bố status lệch mạnh so với giả định của optimizer.
- Điều kiện có chuyển đổi hoặc collation khiến estimate không như dự kiến.

Quy trình:

    ANALYZE TABLE sales_order;

    ANALYZE TABLE sales_order
    UPDATE HISTOGRAM ON order_status
    WITH 32 BUCKETS;

Sau đó chạy lại EXPLAIN và EXPLAIN ANALYZE. So sánh estimates và actuals. Nếu query vẫn đọc quá nhiều hàng và không có index phù hợp, cân nhắc index trên order_status hoặc index ghép theo các predicate thường dùng.

Không tạo index chỉ vì một query có estimated rows lớn. Nếu REFUNDED rất hiếm, index có thể hữu ích; nếu PAID chiếm 90% và query lấy hầu hết PAID, table scan có thể rẻ hơn. Quyết định dựa trên workload, không chỉ một con số.

## 22. Những lỗi thường gặp

- Nghĩ cost trong EXPLAIN là thời gian milliseconds.
- Nghĩ optimizer thử mọi kế hoạch có thể và luôn tìm ra kế hoạch tối ưu tuyệt đối.
- Nghĩ có index thì optimizer bắt buộc phải dùng index.
- Xem type ALL là lỗi dù bảng rất nhỏ hoặc query cần phần lớn dữ liệu.
- Đọc cardinality như số đếm chính xác.
- Nhầm cardinality với selectivity.
- Bỏ qua fanout và sai lệch ước lượng lan qua nhiều bước JOIN.
- Nghĩ histogram tạo index hoặc tự làm truy vấn đọc ít trang hơn.
- Nghĩ histogram một cột mô tả tương quan giữa nhiều cột.
- Cho rằng ANALYZE TABLE bảo đảm query nhanh hơn.
- Không cập nhật histogram sau khi phân bố dữ liệu thay đổi đáng kể.
- Chỉ nhìn key mà bỏ qua rows, filtered, Extra và join order.
- Nghĩ Using filesort luôn có nghĩa sort ghi ra đĩa.
- Nghĩ EXPLAIN ANALYZE chỉ hiển thị kế hoạch mà không thực thi query.
- Chạy EXPLAIN ANALYZE truy vấn rất nặng trên production mà không kiểm soát.
- Dùng FORCE INDEX hoặc optimizer hint trước khi hiểu nguyên nhân.
- Thay đổi nhiều yếu tố cùng lúc khiến không biết nguyên nhân cải thiện.
- Đánh giá hiệu năng bằng bảng mẫu vài hàng rồi suy rộng ra dữ liệu production.

## 23. Checklist đọc và cải thiện kế hoạch

- Đã ghi lại SQL, tham số, phiên bản và session settings.
- Đã xem schema, kiểu dữ liệu, constraint và storage engine.
- Đã xác định index hiện có và leftmost prefix của index ghép.
- Đã đọc access type, key, key_len, rows, filtered và Extra.
- Đã xem join order và estimated fanout qua từng bước.
- Đã phân biệt estimated cost với thời gian thực tế.
- Đã kiểm tra table/index statistics và thời điểm cập nhật.
- Đã đánh giá dữ liệu skew và nhu cầu histogram.
- Đã hiểu giới hạn thống kê một cột và tương quan nhiều cột.
- Đã dùng EXPLAIN ANALYZE an toàn để so sánh estimate với actual.
- Đã xác định điểm sai lệch đầu tiên thay vì chỉ nhìn iterator cuối.
- Đã dùng optimizer trace khi cần biết lý do lựa chọn hoặc loại phương án.
- Đã cân nhắc index ghép/covering index theo workload đọc và ghi.
- Đã đo lại sau từng thay đổi trên dữ liệu và tham số đại diện.
- Đã ghi nhận tác động đến query khác trước khi triển khai rộng.

Cost-based optimizer lựa chọn kế hoạch dựa trên ngữ nghĩa câu SQL, cấu trúc schema, index, thống kê dữ liệu và mô hình chi phí của server/storage engine. Cardinality, selectivity và fanout quyết định phần lớn chất lượng ước lượng; index statistics và histogram cung cấp thông tin về phân bố, còn cost model giúp so sánh các access path và thứ tự join. Khi kế hoạch kém, hãy đối chiếu estimated rows với actual rows bằng EXPLAIN ANALYZE, tìm điểm sai lệch đầu tiên, kiểm tra thống kê và index rồi mới cân nhắc hint. Kế hoạch tốt cần được xác nhận bằng dữ liệu và workload thực tế, không chỉ bằng một con số cost hoặc việc optimizer có sử dụng index.

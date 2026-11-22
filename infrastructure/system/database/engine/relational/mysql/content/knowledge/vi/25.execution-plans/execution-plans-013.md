# Giới hạn của EXPLAIN và tránh kết luận chỉ từ một cột chi phí

EXPLAIN là công cụ quan trọng để hiểu MySQL dự định truy cập bảng, dùng index và nối dữ liệu như thế nào. Tuy nhiên, output EXPLAIN chủ yếu mô tả kế hoạch mà optimizer lựa chọn cùng các ước lượng của nó. Một số cột chỉ cho biết một khía cạnh của kế hoạch; không cột nào tự nó chứng minh truy vấn nhanh, chậm hoặc cần thêm index.

Ví dụ, type = ALL thường biểu thị table scan nhưng có thể là lựa chọn đúng cho bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu. key có tên index không chứng minh index đó chọn lọc tốt. rows là ước lượng, không phải số hàng thực tế. cost là đơn vị chi phí của optimizer, không phải milliseconds. Extra = Using filesort không có nghĩa chắc chắn sort đã ghi ra đĩa; Using temporary cũng không tự động là lỗi hiệu năng.

Muốn đánh giá đúng, cần đọc toàn bộ kế hoạch trong ngữ cảnh câu SQL, schema, index, phân bố dữ liệu, tham số và workload. Khi cần số liệu thực tế, hãy dùng EXPLAIN ANALYZE trên truy vấn an toàn và đối chiếu với đo đạc ở tầng ứng dụng. Bài học này trình bày giới hạn của từng dạng EXPLAIN, các cách diễn giải sai phổ biến và quy trình ra quyết định dựa trên nhiều bằng chứng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích EXPLAIN cho biết điều gì và không thể cho biết điều gì.
- Phân biệt kế hoạch ước lượng với số liệu thực thi thực tế.
- Đọc các cột type, possible_keys, key, key_len, rows, filtered và Extra trong ngữ cảnh.
- Tránh xem một access type hoặc một tên index là thước đo hiệu năng độc lập.
- Hiểu vì sao cost không phải thời gian chạy và không nên so sánh tùy tiện giữa môi trường.
- Nhận biết giới hạn của rows estimate, index cardinality và thống kê.
- Phân biệt Using filesort, Using temporary, Using index và Using index condition.
- Hiểu giới hạn của EXPLAIN ANALYZE và các yếu tố làm số liệu biến động.
- Dùng EXPLAIN FORMAT=JSON, FORMAT=TREE và optimizer trace đúng mục đích.
- Biết khi nào cần xem Performance Schema, slow query log hoặc đo ở tầng ứng dụng.
- Đưa ra quyết định về index, SQL và optimizer hint dựa trên nhiều bằng chứng.

## 1. EXPLAIN là ảnh chụp của một kế hoạch, không phải bản benchmark

Với câu SELECT:

    EXPLAIN
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001
      AND order_status = 'PAID';

MySQL phân tích câu SQL, schema, index, thống kê và cấu hình optimizer để tạo kế hoạch. EXPLAIN hiển thị kế hoạch được chọn cùng các ước lượng liên quan. Nó không chạy truy vấn để đo thời gian thực tế.

Kế hoạch có thể cho biết:

- Bảng nào được truy cập và thứ tự truy cập.
- Access method được chọn.
- Index nào được dùng.
- Số hàng ước lượng cần đọc hoặc trả qua từng bước.
- Các phép sort, filter, temporary table hoặc join buffer mà kế hoạch cần.
- Partition nào được truy cập nếu bảng có partition.

EXPLAIN thông thường không cho biết chính xác:

- Query sẽ mất bao nhiêu milliseconds trong lần chạy tiếp theo.
- Bao nhiêu hàng thực sự được đọc ở từng iterator trong workload hiện tại.
- Bao nhiêu trang phải đọc từ storage, bao nhiêu trang đã có trong buffer pool.
- CPU, I/O, memory, lock wait và network đóng góp bao nhiêu vào latency.
- Ứng dụng mất bao lâu để lấy connection, nhận dữ liệu và xử lý kết quả.
- Tất cả phương án mà optimizer đã từng cân nhắc và lý do chi tiết của từng phương án.

Do đó, hãy xem EXPLAIN là công cụ giải thích kế hoạch, không phải phép đo thời gian chạy.

## 2. Vì sao không nên kết luận từ một cột?

Một dòng EXPLAIN có nhiều cột liên quan lẫn nhau. Mỗi cột mô tả một phần nhỏ:

| Cột | Câu hỏi nó giúp trả lời | Điều không thể kết luận chỉ từ cột đó |
|---|---|---|
| type | Access method thuộc loại nào? | Truy vấn nhanh hay chậm |
| possible_keys | Index nào có thể được cân nhắc? | Index nào chắc chắn sẽ được dùng |
| key | Index nào được chọn ở bước này? | Index được chọn là tối ưu hoặc đủ chọn lọc |
| key_len | Bao nhiêu byte của key được dùng? | Toàn bộ điều kiện đã được xử lý bằng index |
| rows | Optimizer ước lượng bao nhiêu hàng? | Số hàng thực tế đã đọc |
| filtered | Tỷ lệ hàng ước lượng còn lại sau filter? | Tỷ lệ thực tế trong mọi lần chạy |
| Extra | Có thông tin bổ sung gì về kế hoạch? | Mọi thao tác đều đắt hoặc đều xảy ra trên đĩa |
| cost_info | Optimizer ước lượng chi phí ra sao? | Thời gian chạy tính bằng milliseconds |

Một kế hoạch cần được đọc như một cấu trúc. Ví dụ, type = range với rows rất lớn có thể đắt hơn ALL trên bảng nhỏ. key có thể trỏ đến index nhưng access path vẫn phải lookup nhiều hàng từ clustered index. Using filesort có thể chỉ sort vài chục hàng và không phải bottleneck.

Hãy xem cả SQL, index, cardinality, rows, filtered, join order, Extra và actual metrics trước khi đưa ra kết luận.

## 3. Giới hạn của type: access type không phải bảng xếp hạng hiệu năng

Trong EXPLAIN dạng bảng, type cho biết cách MySQL truy cập dữ liệu ở bước đó. Một số giá trị thường gặp:

| type | Ý nghĩa khái quát |
|---|---|
| system | Bảng rất nhỏ, thường chỉ có một hàng |
| const | Tối đa một hàng khớp theo khóa unique/primary key trong điều kiện phù hợp |
| eq_ref | Mỗi tổ hợp hàng từ các bảng trước lookup tối đa một hàng qua unique key |
| ref | Lookup theo index không unique hoặc prefix phù hợp |
| range | Đọc một vùng key của index |
| index | Quét toàn bộ index |
| ALL | Quét toàn bộ bảng |
| index_merge | Kết hợp kết quả từ nhiều index |

Các loại như const, eq_ref và ref thường có lợi khi truy vấn chọn ít hàng. Tuy nhiên, không nên biến danh sách này thành thứ hạng tuyệt đối.

### 3.1. ALL không tự động là kế hoạch xấu

Giả sử bảng country_code chỉ có 10 hàng và truy vấn cần tất cả:

    SELECT country_code, country_name
    FROM country;

Quét toàn bảng là hợp lý. Dùng index cũng cần đọc index rồi có thể lookup hàng; chi phí bổ sung không đem lại lợi ích khi bảng rất nhỏ.

Một truy vấn khác cần 80% hàng của bảng lớn cũng có thể rẻ hơn khi scan tuần tự thay vì dùng index để thực hiện rất nhiều random lookups.

Khi thấy ALL, hãy hỏi:

- Bảng có bao nhiêu hàng và kích thước dữ liệu ra sao?
- Truy vấn cần bao nhiêu phần trăm hàng?
- Có predicate chọn lọc nhưng không dùng được index không?
- Có implicit conversion hoặc hàm trên cột làm mất khả năng range access không?
- Table scan có thật sự là phần chiếm thời gian trong actual plan không?

### 3.2. range không có nghĩa chỉ đọc ít hàng

Một range scan có thể bao phủ phần lớn index:

    SELECT order_id
    FROM sales_order
    WHERE order_date >= '2020-01-01';

Nếu gần như toàn bộ đơn hàng đều sau ngày này, range scan có thể đọc gần hết index và vẫn phải lấy nhiều hàng. type = range chỉ mô tả access method; cần xem rows, filtered, actual rows và kích thước dữ liệu.

### 3.3. index không nhất thiết tốt hơn ALL

Một index lookup thường cần:

1. Tìm key trong B-tree.
2. Đọc index entry phù hợp.
3. Nếu index không covering, lookup hàng trong clustered index.
4. Áp dụng các điều kiện còn lại.

Nếu truy vấn cần rất nhiều hàng, chi phí lookup lặp lại có thể lớn hơn scan. Optimizer có thể chọn ALL vì chi phí ước lượng thấp hơn.

## 4. possible_keys và key: index có thể dùng khác với index được chọn

possible_keys liệt kê các index mà optimizer xem là ứng viên có thể dùng cho việc tìm hàng. key cho biết index được chọn trong kế hoạch ở bước đó.

Các giới hạn:

- possible_keys không bảo đảm index sẽ được dùng.
- key = NULL không tự động chứng minh schema thiếu index; table scan có thể là lựa chọn tốt.
- key có giá trị không có nghĩa mọi predicate đều được dùng để định vị index.
- Index được chọn có thể chỉ xử lý một phần điều kiện; các điều kiện khác vẫn nằm ở filter.
- Index có thể được dùng cho lookup nhưng vẫn trả nhiều hàng hoặc cần sort.

Ví dụ:

    EXPLAIN
    SELECT order_id, customer_id, order_status
    FROM sales_order
    WHERE customer_id = 1001
      AND order_status = 'PAID';

Giả sử bảng có index riêng trên customer_id và order_status. possible_keys có thể liệt kê cả hai, nhưng optimizer chọn một index dựa trên ước lượng. Điều kiện còn lại có thể được áp dụng sau khi đọc hàng.

Nếu query thường lọc theo cả hai cột, hãy đánh giá index ghép:

    CREATE INDEX idx_order_customer_status
    ON sales_order (customer_id, order_status);

Index ghép có thể giảm lượng index entry cần đọc, nhưng phải kiểm tra các truy vấn khác, thứ tự cột, kích thước index và chi phí ghi trước khi thêm.

## 5. key_len không phải chỉ số chọn lọc

key_len cho biết độ dài phần key mà MySQL sử dụng trong access method, tính theo byte. Với index ghép, nó có thể giúp nhận biết MySQL dùng đến phần nào của key.

Ví dụ:

    CREATE TABLE key_len_demo (
        tenant_id INT NOT NULL,
        account_code VARCHAR(20) NOT NULL,
        status_code CHAR(1) NOT NULL,
        PRIMARY KEY (tenant_id, account_code),
        KEY idx_tenant_status (tenant_id, status_code)
    ) ENGINE = InnoDB;

    EXPLAIN
    SELECT *
    FROM key_len_demo
    WHERE tenant_id = 10
      AND status_code = 'A';

key_len phụ thuộc kiểu dữ liệu, charset, nullable, độ dài prefix và các phần của composite key được dùng. Nó không trực tiếp cho biết:

- Bao nhiêu hàng thực tế sẽ khớp.
- Index có chọn lọc tốt không.
- Bao nhiêu trang index phải đọc.
- Truy vấn có covering hay không.
- Điều kiện nào còn phải filter sau lookup.

Không kết luận “key_len dài hơn là tốt hơn” hoặc “key_len ngắn là index kém”. Hãy đọc cùng định nghĩa index, predicate, rows và actual plan.

## 6. rows và filtered chỉ là ước lượng

Trong EXPLAIN truyền thống:

- rows là số hàng MySQL ước lượng cần đọc ở bước đó.
- filtered là phần trăm hàng ước lượng còn lại sau điều kiện lọc bổ sung trong ngữ cảnh của bước.

Ví dụ:

    rows = 10000
    filtered = 5.00

Có thể hình dung khoảng 500 hàng còn lại sau filter. Nhưng đây vẫn là ước lượng. Không dùng phép nhân này như số hàng chính xác của mọi iterator hoặc tổng kết quả cuối cùng, đặc biệt khi có join, subquery, grouping hoặc nhiều điều kiện tương quan.

### 6.1. Ước lượng có thể sai vì thống kê

Optimizer dựa trên table/index statistics và có thể dùng histogram để ước lượng phân bố cột. Sai lệch có thể xảy ra khi:

- Dữ liệu vừa thay đổi đáng kể nhưng thống kê chưa được cập nhật.
- Phân bố dữ liệu bị skew mạnh.
- Giá trị hiếm hoặc phổ biến không được histogram mô tả đủ tốt.
- Nhiều predicate có tương quan giữa các cột.
- Thống kê index dựa trên lấy mẫu.
- Kiểu dữ liệu, collation hoặc biểu thức làm thay đổi cách so sánh.

Nếu estimated rows khác actual rows rất lớn, hãy tìm iterator đầu tiên có sai lệch thay vì chỉ nhìn tổng số hàng ở root.

### 6.2. rows không phải rows examined

rows trong EXPLAIN là estimate của optimizer, không phải bộ đếm thực tế cho mọi record mà storage engine đã xem xét. Trong EXPLAIN ANALYZE, actual rows của iterator là số hàng nó trả cho iterator cha; nó vẫn không đồng nghĩa với mọi index entry hoặc record đã được kiểm tra bên trong.

Muốn đo rows examined ở mức statement, có thể xem Performance Schema, slow query log hoặc session status phù hợp. Các nguồn này có phạm vi và cách tính riêng; cần chọn metric đúng câu hỏi.

### 6.3. filtered thấp không tự động có nghĩa index sai

Một bước có thể dùng index để lấy candidate rows, rồi filter bỏ phần lớn. Điều này có thể cho thấy index chưa bao phủ predicate hoặc thứ tự cột chưa phù hợp. Nhưng cũng có thể index đó vẫn là access path rẻ nhất trong các phương án.

Hãy kiểm tra actual rows, số vòng lookup, predicate còn lại và khả năng tạo composite index. Đừng thêm index chỉ vì filtered thấp.

## 7. cost không phải milliseconds

Trong EXPLAIN FORMAT=JSON hoặc TREE, MySQL có thể hiển thị cost_info hoặc cost estimate. Giá trị này thuộc mô hình chi phí của optimizer, dùng để so sánh các phương án.

Cost không phải:

- Thời gian thực tế tính bằng milliseconds.
- Thời gian CPU chính xác.
- Số lần đọc đĩa chính xác.
- Chỉ số có thể so sánh tùy tiện giữa hai server khác cấu hình.
- Bằng chứng rằng query cost 100 sẽ chạy nhanh gấp đôi query cost 200.

Cost phụ thuộc các giả định và cost constants của phiên bản/cấu hình. Một query có cost thấp vẫn có thể chậm do lock wait, I/O contention, cache lạnh hoặc tải đồng thời. Một query có cost cao có thể hoàn tất nhanh nếu dữ liệu nằm trong buffer pool và workload nhẹ.

### 7.1. So sánh cost đúng cách

Có thể dùng cost để so sánh các phương án mà optimizer ước lượng trong cùng bối cảnh. Nhưng khi đánh giá thay đổi, cần giữ các điều kiện khác ổn định:

- Cùng phiên bản và cấu hình MySQL.
- Cùng schema, index và thống kê.
- Cùng câu SQL và giá trị tham số.
- Cùng dữ liệu hoặc snapshot dữ liệu tương đương.
- Cùng optimizer settings.

Ngay cả khi cost giảm, vẫn cần đo actual execution để xác nhận thay đổi cải thiện latency hoặc tài nguyên.

### 7.2. Không tối ưu để giảm cost bằng mọi giá

Một index mới có thể làm optimizer chọn kế hoạch cost thấp hơn cho một query, nhưng:

- INSERT/UPDATE/DELETE phải duy trì index mới.
- Index chiếm buffer pool và storage.
- Các query khác có thể bị ảnh hưởng do kế hoạch đổi.
- DDL tạo index có chi phí triển khai và metadata lock.

Mục tiêu là cải thiện workload và độ ổn định hệ thống, không phải làm một cột cost nhỏ nhất bằng mọi giá.

## 8. Extra: đọc đúng Using filesort và Using temporary

Extra chứa các thông tin bổ sung về kế hoạch. Hai giá trị dễ bị hiểu sai là Using filesort và Using temporary.

### 8.1. Using filesort không đồng nghĩa ghi ra file đĩa

Using filesort nghĩa MySQL cần một bước sort riêng thay vì lấy kết quả theo thứ tự từ access path hiện tại. Từ “filesort” là tên thuật toán/chiến lược sắp xếp; nó không khẳng định dữ liệu chắc chắn đã được ghi ra file trên đĩa.

Sort có thể được xử lý trong bộ nhớ nếu dữ liệu và giới hạn cho phép. Với tập lớn, sort có thể cần temporary files hoặc spill ra storage. EXPLAIN truyền thống chỉ báo sự hiện diện của bước sort, không cho biết đầy đủ dung lượng, số lần spill hoặc thời gian thực tế.

Ví dụ:

    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001
    ORDER BY total_amount DESC
    LIMIT 10;

Nếu index không cung cấp thứ tự total_amount, MySQL có thể sort các hàng tìm được. Nếu customer_id chỉ có 12 đơn, sort 12 hàng có thể rất rẻ. Nếu có hàng triệu đơn, cần xem actual rows và thời gian.

### 8.2. Using temporary không tự động là lỗi

Using temporary cho biết kế hoạch cần internal temporary table cho một phần xử lý, chẳng hạn một số dạng GROUP BY, DISTINCT hoặc UNION. Temporary table có thể ở bộ nhớ hoặc dùng storage tùy kích thước, kiểu dữ liệu và cấu hình.

Một temporary table nhỏ có thể không đáng lo. Một temporary table lớn gây spill hoặc được tạo nhiều lần có thể trở thành bottleneck.

Hãy dùng EXPLAIN ANALYZE, Performance Schema và status counters phù hợp để xác định kích thước, số lần và thời gian thực tế. Đừng loại bỏ GROUP BY hoặc DISTINCT chỉ để làm biến mất chữ Using temporary nếu điều đó thay đổi ngữ nghĩa kết quả.

### 8.3. Using index và Using index condition khác nhau

- Using index thường cho biết truy vấn có thể lấy các cột cần thiết từ index (covering access), tránh lookup hàng đầy đủ.
- Using index condition cho biết Index Condition Pushdown (ICP) được sử dụng để kiểm tra điều kiện trên index entry trước khi đọc full row.

Hai thông tin này không tương đương. ICP có thể giảm số lần đọc full row nhưng vẫn cần truy cập hàng. Covering index có thể trả toàn bộ cột cần từ index, nhưng không có nghĩa truy vấn không phải đọc nhiều index entry.

## 9. EXPLAIN FORMAT=JSON và TREE cũng có giới hạn

FORMAT=JSON trình bày kế hoạch theo cấu trúc JSON, có thể chứa cost_info, rows_examined_per_scan, rows_produced_per_join, attached_condition và thông tin access path.

    EXPLAIN FORMAT=JSON
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

FORMAT=TREE biểu diễn iterator plan theo cấu trúc cha/con:

    EXPLAIN FORMAT=TREE
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

Các định dạng giúp nhìn kế hoạch chi tiết hơn nhưng vẫn không thay thế số liệu runtime. Tên trường, cấu trúc JSON và cách biểu diễn có thể thay đổi giữa các phiên bản MySQL.

Không xây dựng công cụ production parse cứng output văn bản của TREE mà không khóa phiên bản và kiểm tra tương thích. Với ứng dụng giám sát, ưu tiên nguồn metric có schema và hợp đồng ổn định hơn.

## 10. EXPLAIN ANALYZE cung cấp actual metrics nhưng vẫn không phải toàn bộ bức tranh

MySQL 8.0.18 trở lên hỗ trợ EXPLAIN ANALYZE cho SELECT. Câu truy vấn được thực thi và output TREE có actual time, rows và loops cho iterator.

    EXPLAIN ANALYZE
    SELECT order_id, total_amount
    FROM sales_order
    WHERE customer_id = 1001;

Điều này giúp so sánh estimate với actual, nhưng vẫn có giới hạn:

- Query thực sự chạy và có thể gây tải lớn.
- Instrumentation có overhead.
- Actual rows là hàng iterator trả, không phải mọi record examined.
- rows và timing ở iterator nhiều loops được hiển thị theo trung bình mỗi loop.
- Timing của parent và child lồng nhau không thể cộng như các đoạn độc lập.
- Output không phân rã đầy đủ CPU, physical I/O, buffer pool hit, lock wait, network và client processing.
- Một lần chạy không đại diện mọi giá trị tham số hoặc mọi trạng thái cache.

EXPLAIN ANALYZE phù hợp để hiểu cây thực thi và sai lệch estimate/actual. Muốn đánh giá SLA ứng dụng, cần thêm đo đạc end-to-end.

### 10.1. Không suy ra latency ứng dụng từ root time

Root iterator completion time là chỉ báo hữu ích cho phần thực thi iterator phía server trong lần đo. Nó không bao gồm toàn bộ vòng đời request ở ứng dụng.

Latency end-to-end còn có thể gồm:

- Lấy connection từ pool.
- Network round trip.
- Parse/prepare và gửi tham số.
- Chờ connection hoặc queue.
- Đọc toàn bộ result set qua giao thức.
- Chuyển đổi dữ liệu và xử lý tại client.
- Logic ứng dụng sau khi query hoàn tất.

Một query trả 1 triệu hàng có thể có root iterator time thấp hơn tổng thời gian ứng dụng nhận và xử lý toàn bộ result set. Ngược lại, một query stream hàng có thể trả hàng đầu tiên sớm nhưng chưa hoàn tất toàn bộ kết quả.

### 10.2. EXPLAIN ANALYZE không đo workload đồng thời đầy đủ

Một lần chạy trong session riêng không tái tạo đầy đủ tải production. Tranh chấp CPU, I/O, lock, buffer pool và số lượng query đồng thời có thể làm latency khác đáng kể.

Nếu vấn đề chỉ xuất hiện khi tải cao, hãy kết hợp query plan với Performance Schema, sys schema, slow query log, metrics server và APM.

## 11. Optimizer trace cũng không phải bằng chứng runtime

Optimizer trace có thể cho biết một số candidate access path, cost estimate và quyết định loại/chọn phương án:

    SET optimizer_trace = 'enabled=on';

    SELECT order_id
    FROM sales_order
    WHERE customer_id = 1001
      AND order_status = 'PAID';

    SELECT TRACE
    FROM information_schema.optimizer_trace;

    SET optimizer_trace = 'enabled=off';

Trace giúp trả lời câu hỏi “vì sao optimizer chọn phương án này?” tốt hơn EXPLAIN đơn lẻ trong một số trường hợp. Tuy nhiên:

- Trace là thông tin nội bộ phục vụ chẩn đoán, có thể dài và thay đổi giữa phiên bản.
- Nó phản ánh quá trình tối ưu hóa của statement được trace, không phải benchmark.
- Nó không đo thời gian I/O hoặc latency end-to-end.
- Không phải mọi candidate hay chi tiết nội bộ đều được hiển thị.
- Cần tắt trace sau khi sử dụng và tránh bật rộng trên workload lớn nếu không cần.

## 12. Kế hoạch phụ thuộc tham số và trạng thái dữ liệu

Cùng câu SQL có thể chạy với nhiều giá trị tham số khác nhau. Một khách hàng có 5 đơn và khách hàng khác có 500.000 đơn. Kế hoạch tốt cho nhóm này có thể không phải tốt nhất cho nhóm kia.

Ví dụ:

    SELECT order_id, order_date, total_amount
    FROM sales_order
    WHERE customer_id = ?
    ORDER BY order_date DESC
    LIMIT 50;

Khi đánh giá query này:

- Thử khách hàng có ít đơn.
- Thử khách hàng có rất nhiều đơn.
- Thử khoảng thời gian hẹp và rộng nếu có predicate ngày.
- Thử giá trị trạng thái hiếm và phổ biến.
- Dùng cùng cách bind tham số như ứng dụng.

Không kết luận từ một lần EXPLAIN với một literal nếu production dùng prepared statement và nhiều phân bố tham số. Cần hiểu phiên bản, cơ chế prepare/reprepare và cách optimizer nhận giá trị tham số trong trường hợp thực tế.

## 13. Thống kê và histogram cũng không hoàn hảo

Optimizer có thể dựa trên:

- Row count ước lượng của bảng.
- Cardinality của index và các prefix.
- Persistent InnoDB statistics.
- Histogram theo cột.
- Các giả định về phân bố và tính độc lập giữa predicate.

Các nguồn này có giới hạn:

- InnoDB index statistics thường dựa trên sampling, không phải đếm chính xác mọi giá trị.
- Histogram mô tả từng cột, không mô hình hóa đầy đủ tương quan đa cột.
- Histogram cũ có thể không còn đại diện sau khi dữ liệu thay đổi.
- Bảng nhỏ hoặc dữ liệu lệch có thể khiến estimate dao động.
- ANALYZE TABLE có thể thay đổi kế hoạch mà không bảo đảm kế hoạch mới nhanh hơn.

Ví dụ cột order_status có bốn giá trị nhưng PAID chiếm 95%. Chỉ biết cardinality = 4 không đủ để ước lượng tốt mọi trạng thái. Histogram có thể cải thiện thông tin tần suất, nhưng không tự tạo index và không bảo đảm kế hoạch đúng trong mọi tình huống.

Khi nghi ngờ thống kê:

    ANALYZE TABLE sales_order;

Nếu cần histogram:

    ANALYZE TABLE sales_order
    UPDATE HISTOGRAM ON order_status
    WITH 32 BUCKETS;

Sau đó kiểm tra EXPLAIN và actual metrics. Chỉ cập nhật thống kê/histogram khi có giả thuyết cụ thể và kế hoạch đo lại.

## 14. Partition pruning và cột partitions

Với bảng partitioned, cột partitions trong EXPLAIN cho biết partition được chọn để truy cập theo kế hoạch. Danh sách partition ít hơn có thể cho thấy partition pruning, nhưng không chứng minh toàn truy vấn rẻ.

Ví dụ:

    EXPLAIN
    SELECT order_id, total_amount
    FROM sales_order_partitioned
    WHERE order_date >= '2025-01-01'
      AND order_date < '2025-02-01';

Hãy kiểm tra:

- Predicate có tương thích với partition key không?
- Bao nhiêu partition được truy cập?
- Mỗi partition có bao nhiêu hàng?
- Index local trên partition có phù hợp không?
- Tổng dữ liệu được đọc sau pruning là bao nhiêu?

Một truy vấn có thể chỉ truy cập một partition nhưng partition đó vẫn chứa hàng trăm triệu hàng. Số partition không thay thế rows estimate hoặc actual metrics.

## 15. Những gì EXPLAIN không nói về tài nguyên và chờ đợi

Một kế hoạch có thể trông gọn nhưng query vẫn chậm vì nguyên nhân ngoài access path:

- CPU bị tranh chấp.
- Storage latency cao.
- Buffer pool miss nhiều.
- Temporary table hoặc sort spill.
- Transaction khác giữ row lock.
- Metadata lock làm DDL hoặc query chờ.
- Connection pool cạn.
- Network hoặc client fetch chậm.
- Server đang chạy nhiều truy vấn đồng thời.

EXPLAIN không cung cấp đầy đủ các metric này. Khi kế hoạch có vẻ hợp lý nhưng latency vẫn cao, hãy chuyển sang công cụ phù hợp:

| Câu hỏi | Nguồn nên xem |
|---|---|
| Statement nào chạy lâu và thường xuyên? | Slow query log, sys.statement_analysis, Performance Schema |
| Thời gian query và số hàng examined? | Slow query log, Performance Schema statement events |
| Session nào đang chờ lock? | Performance Schema data_locks/data_lock_waits, metadata_locks, processlist |
| Server có nghẽn CPU/I/O không? | OS metrics, MySQL status, monitoring |
| Query chậm ở production nhưng nhanh ở staging? | APM, tracing, workload và concurrency metrics |
| Client nhận kết quả chậm? | Đo thời gian fetch/deserialize tại ứng dụng |

Không cố giải quyết mọi latency bằng cách thêm index. Trước hết xác định thời gian đang mất ở đâu.

## 16. Ví dụ: bốn kết luận sai từ cùng một EXPLAIN

Giả sử output truyền thống có:

    type = range
    possible_keys = idx_order_date, idx_customer_date
    key = idx_order_date
    rows = 800000
    filtered = 10.00
    Extra = Using where; Using filesort

Các kết luận vội vàng:

1. “range là tốt nên query chắc chắn nhanh.”
2. “key có index nên index đang được dùng tối ưu.”
3. “rows 800.000 là đúng 800.000 hàng thực tế.”
4. “Using filesort nghĩa là sort ghi ra đĩa và là nguyên nhân chậm.”

Các câu hỏi đúng hơn:

- 800.000 là estimate cho access step nào và actual rows là bao nhiêu?
- 10% filtered được áp dụng ở bước nào?
- Index date có chọn lọc đủ tốt không?
- Index ghép có thể hỗ trợ filter và order không?
- Filesort xử lý bao nhiêu hàng, có spill hay không?
- Root iterator completion time và node sort là bao nhiêu?
- Query có thực sự bị sort bottleneck hay chậm do I/O/lock/client?

Chỉ sau khi có actual evidence mới quyết định thay index hoặc sửa query.

## 17. Ví dụ: ALL có thể tốt hơn index lookup

Giả sử bảng audit_event có 2.000 hàng và truy vấn cần 1.800 hàng:

    SELECT event_id, event_type, created_at
    FROM audit_event
    WHERE created_at >= '2025-01-01';

Nếu index created_at sẽ trả gần như toàn bộ bảng, MySQL có thể chọn table scan. Việc đọc tuần tự 2.000 hàng có thể rẻ hơn tìm trong index rồi lookup gần 1.800 hàng.

Nếu bảng tăng lên 100 triệu hàng và điều kiện chỉ khớp 100 hàng, index range scan có thể trở nên tốt hơn. Kế hoạch thay đổi theo quy mô và phân bố dữ liệu là bình thường.

Đừng thêm FORCE INDEX chỉ để loại bỏ ALL khỏi output. Hãy đo kế hoạch hiện tại và phương án thay thế trên dữ liệu đại diện.

## 18. Quy trình đánh giá kế hoạch không dựa trên một cột

Khi nhận một query chậm, thực hiện theo thứ tự:

1. Ghi lại SQL thực tế, giá trị tham số, phiên bản và session settings.
2. Kiểm tra schema, kiểu dữ liệu, constraint, partition và storage engine.
3. Đọc toàn bộ EXPLAIN: join order, type, possible_keys, key, key_len, rows, filtered, partitions và Extra.
4. Xem FORMAT=JSON hoặc TREE để hiểu query block và iterator.
5. Xác định estimate có hợp lý với cardinality và phân bố dữ liệu không.
6. Kiểm tra index statistics, persistent stats và histogram.
7. Nếu an toàn, chạy EXPLAIN ANALYZE để so sánh estimate với actual rows, loops và timing.
8. Tìm iterator đầu tiên có sai lệch lớn hoặc startup/completion time đáng chú ý.
9. Nếu vẫn chưa rõ lựa chọn, dùng optimizer trace.
10. Nếu query plan không giải thích được latency, xem Performance Schema, slow log, lock, OS metrics và APM.
11. Thay một yếu tố mỗi lần: predicate, index, thống kê hoặc hint.
12. Đo lại trên cùng dữ liệu, tham số và điều kiện tải.
13. Đánh giá cả workload đọc, ghi, dung lượng index và query khác bị ảnh hưởng.

Quy trình này tránh việc thay đổi schema chỉ vì một cột EXPLAIN trông không đẹp.

## 19. Khi nào nên dùng optimizer hint hoặc FORCE INDEX?

Hint có thể hữu ích khi đã xác định optimizer chọn kế hoạch không phù hợp trong một workload cụ thể. Nhưng hint làm giảm quyền tự lựa chọn của optimizer và có thể trở nên bất lợi khi dữ liệu thay đổi.

Trước khi ép index:

- Xác minh actual rows và thời gian của kế hoạch hiện tại.
- Xác minh index thay thế thực sự giảm công việc.
- Thử trên nhiều giá trị tham số đại diện.
- Đo cả workload đọc và ghi.
- Ghi lại lý do, phạm vi áp dụng và điều kiện cần xem xét lại.
- Kiểm tra kế hoạch sau nâng cấp MySQL hoặc thay đổi schema.

Không dùng FORCE INDEX chỉ vì:

- type đang là ALL.
- key đang là NULL.
- cost hiển thị lớn.
- Extra có Using filesort.
- Một query sample chạy nhanh hơn một lần khi ép index.

Các dấu hiệu này là điểm bắt đầu điều tra, không phải bằng chứng đủ để ép optimizer.

## 20. Các sai lầm thường gặp

- Coi EXPLAIN là benchmark và đọc cost như milliseconds.
- Xếp hạng type theo một thứ tự tuyệt đối mà không xét số hàng.
- Coi ALL luôn xấu và ref/range luôn tốt.
- Nghĩ possible_keys là danh sách index chắc chắn được dùng.
- Nghĩ key khác NULL chứng minh index được dùng hiệu quả.
- Đọc key_len như selectivity hoặc số hàng khớp.
- Xem rows và filtered là số liệu runtime chính xác.
- Nhầm rows estimate với rows examined.
- Coi Using filesort là bằng chứng sort đã ghi ra đĩa.
- Coi Using temporary là lỗi cần loại bỏ bằng mọi giá.
- Nhầm Using index với Using index condition.
- Cộng cost của các node như thời gian thực tế.
- So sánh cost giữa server khác cấu hình hoặc phiên bản.
- Dùng một lần EXPLAIN ANALYZE để đại diện mọi tham số và trạng thái cache.
- Nghĩ EXPLAIN ANALYZE đo cả network và client fetch.
- Cộng timing parent/child trong iterator tree.
- Nghĩ histogram mô tả tương quan nhiều cột.
- Dùng FORCE INDEX trước khi kiểm tra thống kê và actual metrics.
- Thêm index mà không tính chi phí ghi, storage và tác động đến query khác.
- Cố sửa query plan trong khi nguyên nhân thật là lock wait hoặc nghẽn tài nguyên.

## 21. Checklist trước khi kết luận từ EXPLAIN

- Đã ghi lại câu SQL, tham số và phiên bản MySQL.
- Đã đọc toàn bộ các hàng EXPLAIN, không chỉ một cột.
- Đã xem join order và query block.
- Đã hiểu type là access method, không phải điểm hiệu năng.
- Đã phân biệt possible_keys với key.
- Đã đọc key_len cùng định nghĩa composite index.
- Đã xem rows và filtered như estimates.
- Đã kiểm tra cardinality, statistics và histogram.
- Đã đọc Extra đúng nghĩa, đặc biệt filesort và temporary.
- Đã kiểm tra partitions và điều kiện pruning nếu bảng partitioned.
- Đã xem JSON/TREE khi cần hiểu cấu trúc kế hoạch.
- Đã dùng EXPLAIN ANALYZE an toàn nếu cần actual rows/timing.
- Đã tránh cộng timing parent/child hoặc nhầm rows với rows examined.
- Đã thử nhiều giá trị tham số và điều kiện cache phù hợp.
- Đã kiểm tra lock, I/O, CPU, slow log hoặc APM nếu plan không giải thích latency.
- Đã đo lại sau từng thay đổi và đánh giá cả chi phí ghi.
- Đã có lý do cụ thể trước khi dùng optimizer hint hoặc FORCE INDEX.

EXPLAIN giúp hiểu kế hoạch optimizer lựa chọn, nhưng không phải một cột đơn lẻ có thể kết luận hiệu năng. type mô tả access method; key cho biết index được chọn; rows và filtered là ước lượng; cost là đơn vị nội bộ; Extra mô tả một số bước bổ sung chứ không tự cho biết chi phí thực tế. EXPLAIN ANALYZE bổ sung actual rows, loops và timing nhưng vẫn không thay thế đo latency end-to-end hoặc quan sát tài nguyên và lock trong workload production. Hãy đọc toàn bộ kế hoạch, xác minh estimate bằng actual evidence, xem thống kê và môi trường thực thi rồi mới thay SQL, index hoặc optimizer hint.

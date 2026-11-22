# Cập nhật thống kê sau thay đổi lớn và theo dõi hiệu quả

Bộ tối ưu truy vấn (query optimizer) phải ước lượng số dòng sẽ đi qua từng bước của execution plan trước khi chọn cách truy cập bảng, thứ tự JOIN, thuật toán JOIN, phương pháp sắp xếp và tổng hợp. Những ước lượng này dựa nhiều vào statistics (thống kê). Khi dữ liệu thay đổi lớn về số lượng hoặc phân bố, statistics cũ có thể khiến optimizer đánh giá sai cardinality, chọn index không phù hợp, JOIN theo thứ tự kém hiệu quả hoặc cấp phát memory không đúng.

Cập nhật statistics sau một đợt nạp dữ liệu lớn, xóa dữ liệu, thay đổi phân bố hoặc chuyển partition giúp optimizer nhìn thấy dữ liệu gần với trạng thái hiện tại hơn. Nhưng thao tác cập nhật thống kê không tự động làm mọi truy vấn nhanh hơn. Statistics mới có thể dẫn đến plan mới; plan mới cần được kiểm chứng và theo dõi để phát hiện regression.

Trong chương **Bảo trì dữ liệu**, bài học này tập trung vào việc cập nhật thống kê sau thay đổi lớn và theo dõi hiệu quả. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta sẽ tìm hiểu optimizer dùng thống kê như thế nào, nhận diện thời điểm cần ANALYZE/UPDATE STATISTICS, phân biệt statistics với bảo trì index, áp dụng cơ chế của PostgreSQL, MySQL, SQL Server và Oracle, rồi theo dõi actual plan và workload sau khi cập nhật.

Mục tiêu là duy trì ước lượng đủ tin cậy cho các truy vấn quan trọng mà không tạo ra chi phí bảo trì không cần thiết hoặc thay đổi plan ngoài dự kiến.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích statistics, cardinality, selectivity, NDV và histogram.
- Nhận diện vì sao bulk insert, delete, update, partition load hoặc thay đổi phân bố làm thống kê cũ.
- Phân biệt thống kê bảng/cột/index với kích thước, fragmentation và trạng thái vật lý của index.
- Chọn thời điểm và phạm vi cập nhật thống kê.
- So sánh sampling với full scan và hiểu chi phí của mỗi cách.
- Dùng ANALYZE hoặc UPDATE STATISTICS phù hợp trên PostgreSQL, MySQL, SQL Server và Oracle.
- Hiểu giới hạn của histogram một cột và vai trò của thống kê đa cột/tương quan.
- So sánh estimated rows với actual rows trong execution plan.
- Theo dõi plan, latency, I/O, memory, spill và throughput sau maintenance.
- Xây dựng quy trình cập nhật có baseline, kiểm chứng và phương án xử lý plan regression.

## 1. Statistics giúp optimizer chọn plan như thế nào?

### 1.1. Optimizer cần ước lượng trước khi thực thi

Xét truy vấn:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00';
~~~

Optimizer cần ước lượng có bao nhiêu dòng thỏa các điều kiện. Ước lượng đó ảnh hưởng đến quyết định:

- Dùng index seek/scan hay scan toàn bảng.
- Lọc theo điều kiện nào trước.
- Nên bắt đầu JOIN từ bảng nào.
- Dùng nested loop, hash join hay merge join.
- Có cần sort hoặc hash aggregate không.
- Cần bao nhiêu memory cho hash/sort.
- Có nên chạy song song hay không.

Nếu optimizer dự đoán chỉ có 10 dòng nhưng thực tế có 500.000 dòng, plan có thể dùng hàng trăm nghìn lần index lookup hoặc tạo một hash table lớn hơn dự kiến. Ngược lại, nếu dự đoán quá nhiều dòng nhưng thực tế chỉ có vài dòng, optimizer có thể chọn scan lớn thay vì index access.

### 1.2. Cardinality và selectivity

**Cardinality** trong ngữ cảnh optimizer thường là số dòng dự kiến tại một node của plan. Nó có thể là số dòng sau scan, filter, JOIN hoặc aggregate.

**Selectivity** là tỷ lệ dòng thỏa một điều kiện so với tập đầu vào. Nếu bảng có 1.000.000 dòng và predicate chỉ chọn 10.000 dòng, selectivity xấp xỉ 1%.

Cardinality và selectivity không chỉ phụ thuộc tổng số dòng. Chúng còn phụ thuộc phân bố giá trị, NULL, số giá trị phân biệt, tính duy nhất, tương quan giữa các cột và điều kiện JOIN.

### 1.3. NDV, NULL và histogram

Statistics thường chứa một số thông tin như:

- Tổng số dòng hoặc số dòng ước lượng.
- Number of Distinct Values (NDV): số giá trị phân biệt.
- Tỷ lệ NULL.
- Most common values (MCV): các giá trị xuất hiện phổ biến.
- Histogram: mô tả phân bố giá trị theo các khoảng hoặc bucket.
- Density/correlation hoặc các chỉ số tương tự tùy DBMS.
- Thông tin về tính duy nhất và cấu trúc index.

Histogram giúp optimizer ước lượng predicate theo giá trị cụ thể hoặc khoảng giá trị. Nếu một trạng thái chiếm 95% dữ liệu còn trạng thái khác chỉ chiếm 0,1%, giả định phân bố đều sẽ dẫn đến ước lượng sai.

### 1.4. Statistics là mô hình ước lượng, không phải bản sao dữ liệu

Statistics thường được lấy mẫu hoặc tổng hợp từ dữ liệu. Chúng không lưu mọi giá trị của bảng và không bảo đảm đếm chính xác số dòng thỏa bất kỳ predicate nào.

Vì vậy:
- Statistics có thể đủ mới nhưng vẫn ước lượng sai do tương quan phức tạp.
- Sampling có thể bỏ sót một giá trị hiếm hoặc hot key.
- Histogram có số bucket hữu hạn.
- Thống kê một cột có thể không mô tả được tương quan nhiều cột.
- Optimizer vẫn phải dùng mô hình chi phí và giả định riêng.

Cập nhật statistics làm mới thông tin đầu vào cho optimizer; nó không biến ước lượng thành kết quả chính xác tuyệt đối.

## 2. Vì sao thay đổi lớn làm statistics trở nên lỗi thời?

### 2.1. Bulk insert hoặc nạp dữ liệu ban đầu

Sau khi nạp một lượng lớn dòng vào bảng rỗng, statistics trước đó có thể phản ánh bảng rỗng hoặc kích thước rất nhỏ. Optimizer có thể tiếp tục dự đoán cardinality thấp và chọn nested loop hoặc index lookup không phù hợp với tập dữ liệu mới.

Sau bulk load, hãy cập nhật statistics cho bảng và các cột được dùng trong predicate, JOIN, GROUP BY hoặc ORDER BY quan trọng.

### 2.2. Xóa hoặc archive một lượng lớn dữ liệu

DELETE theo khoảng thời gian, archive dữ liệu cũ hoặc purge dữ liệu hết hạn làm thay đổi số dòng và phân bố giá trị. Một histogram cũ có thể vẫn mô tả các giá trị đã bị xóa hoặc đánh giá sai tỷ lệ của nhóm còn lại.

Cần phân biệt việc cập nhật statistics với việc thu hồi không gian vật lý. ANALYZE/UPDATE STATISTICS cập nhật thông tin cho optimizer; VACUUM, compaction, purge hoặc các thao tác rebuild/reorganize có mục tiêu vật lý khác nhau tùy DBMS.

### 2.3. Update làm thay đổi phân bố

Một UPDATE có thể thay đổi trạng thái của hàng triệu dòng, ví dụ chuyển đơn hàng từ PENDING sang EXPIRED. Tổng số dòng không đổi nhưng phân bố status thay đổi mạnh.

Nếu optimizer dùng histogram cũ, truy vấn status='EXPIRED' có thể được ước lượng sai. Vì vậy, chỉ nhìn số dòng insert/delete không đủ để quyết định statistics có còn hữu ích hay không.

### 2.4. Dữ liệu tăng theo thời gian và giá trị mới

Bảng event hoặc orders thường tăng liên tục. Các giá trị mới như tenant mới, mã vùng mới hoặc ngày mới có thể nằm ngoài phạm vi histogram trước đó. Optimizer có thể dùng giả định về giá trị ngoài histogram và ước lượng không tốt.

Với dữ liệu time-series hoặc partition theo thời gian, mỗi partition mới có thể có phân bố rất khác partition cũ. Cần xem statistics cấp partition và cấp bảng/global tùy DBMS.

### 2.5. Partition load, exchange hoặc switch

Thêm partition mới hoặc thay partition bằng thao tác metadata có thể làm thay đổi mạnh phân bố tổng thể mà không tạo ra một lượng DML thông thường trên bảng cha. Statistics ở cấp partition và cấp bảng có thể cần được cập nhật riêng.

Cách thu thập global/partition statistics khác nhau giữa PostgreSQL, Oracle, SQL Server và MySQL. Hãy kiểm tra semantics của phiên bản và quy trình partition maintenance đang dùng; đừng giả định statistics tự động được đồng bộ chỉ vì partition đã được gắn vào bảng.

### 2.6. Tạo hoặc thay đổi index

Sau khi tạo index mới, DBMS thường tạo hoặc cập nhật statistics liên quan đến index theo cơ chế của nó. Nhưng statistics trên các cột khác, thống kê đa cột hoặc histogram tùy chỉnh có thể vẫn cần cập nhật.

Không dùng ANALYZE như một cách thay thế cho index rebuild. Statistics mô tả dữ liệu để optimizer ước lượng; rebuild/reorganize xử lý cấu trúc vật lý của index.

## 3. Dấu hiệu cho thấy cần cập nhật statistics

Không có một ngưỡng phần trăm chung đúng cho mọi DBMS và mọi workload. Hãy kết hợp các tín hiệu:

- Bảng vừa được bulk load hoặc truncate rồi nạp lại.
- Một đợt DELETE/UPDATE lớn làm thay đổi nhiều dòng.
- Partition mới được thêm, exchange hoặc switch.
- Query plan thay đổi bất thường sau khi dữ liệu tăng.
- Estimated rows chênh lệch lớn với actual rows.
- Truy vấn từng nhanh nay có scan, JOIN order hoặc memory grant khác.
- Hash/sort spill xuất hiện sau khi dữ liệu thay đổi.
- Số lần modification kể từ lần cập nhật statistics tăng cao.
- Histogram không còn đại diện cho giá trị phổ biến hiện tại.
- Một nhóm truy vấn có p95/p99 hoặc logical reads tăng mà SQL không thay đổi.

### 3.1. Không chỉ dựa vào tuổi statistics

Statistics được cập nhật hôm qua vẫn có thể không phù hợp nếu hôm nay có bulk load lớn. Statistics vài tuần tuổi có thể vẫn đủ tốt với bảng gần như bất biến.

Đánh giá theo:
- Số lượng thay đổi kể từ lần cập nhật.
- Tỷ lệ thay đổi so với kích thước bảng.
- Mức độ thay đổi phân bố.
- Tầm quan trọng của query workload.
- Chi phí thu thập statistics.
- Khả năng tự động cập nhật và ngưỡng của DBMS.

### 3.2. Chênh lệch estimated rows và actual rows

Đây là dấu hiệu trực tiếp để điều tra. Ví dụ:

| Node | Estimated rows | Actual rows | Nhận xét |
|---|---:|---:|---|
| Filter status='PAID' | 5.000 | 450.000 | Ước lượng thấp mạnh |
| JOIN orders-customers | 6.000 | 470.000 | Sai lệch tiếp tục lan truyền |
| Hash aggregate | 500 | 490 | Ước lượng nhóm tương đối tốt |

Hãy tìm node đầu tiên có sai lệch lớn. Nếu node scan/filter đã sai, các JOIN phía trên có thể chỉ đang phản ánh sai lệch đó. Không chỉ nhìn node cuối cùng.

Một thước đo trực quan là q-error, tỷ số giữa estimated và actual cardinality theo chiều lớn hơn chia cho chiều nhỏ hơn. Q-error càng cao thì sai lệch càng lớn. Khi actual rows bằng 0, cần xử lý riêng vì phép chia thông thường không xác định.

### 3.3. Plan regression sau cập nhật

Statistics mới có thể làm optimizer chọn plan khác. Plan mới có thể tốt hơn cho đa số tham số nhưng kém hơn cho một số giá trị hiếm hoặc phổ biến.

Nếu latency tăng ngay sau maintenance:
- So sánh plan trước và sau.
- So sánh estimated/actual rows.
- Kiểm tra tham số truy vấn và cache state.
- Kiểm tra index/access path, join order, DOP, memory grant và spill.
- Xác định regression có xảy ra ở mọi giá trị hay chỉ một nhóm tham số.

Không tự động rollback statistics chỉ vì plan hash thay đổi. Thay đổi plan là bình thường; cần đánh giá hiệu năng và correctness.

## 4. Chọn phạm vi statistics cần cập nhật

### 4.1. Statistics ở cấp bảng và cột

Một bảng có thể có nhiều cột nhưng chỉ một số cột ảnh hưởng đến workload quan trọng. Những cột thường cần chú ý gồm:

- Cột trong WHERE predicate.
- Cột JOIN key.
- Cột GROUP BY và ORDER BY.
- Cột có phân bố lệch hoặc nhiều NULL.
- Cột được dùng trong filtered/partial index.
- Cột thường xuyên thay đổi sau ETL.

Không cần tăng statistics target hoặc tạo histogram đặc biệt cho mọi cột. Tập trung vào cột và query fingerprint có tác động lớn.

### 4.2. Statistics của index không phải fragmentation

Statistics liên quan đến index giúp optimizer ước lượng số dòng và chi phí truy cập qua index. Fragmentation, page density và kích thước vật lý mô tả trạng thái lưu trữ của index.

Hai việc này khác nhau:
- Cập nhật statistics giúp optimizer biết dữ liệu có phân bố ra sao.
- Rebuild/reorganize có thể thay đổi cấu trúc vật lý và có thể kéo theo cập nhật statistics tùy DBMS/tuỳ chọn.
- Một index ít fragmentation vẫn có statistics không phù hợp.
- Một index có statistics mới vẫn có thể bị phân mảnh hoặc có page density thấp.

Chẩn đoán đúng vấn đề trước khi chọn thao tác bảo trì.

### 4.3. Statistics đa cột và tương quan

Giả sử mọi đơn hàng của tenant A đều có status='PAID' với tỷ lệ rất cao, còn tenant B có tỷ lệ thấp. Nếu optimizer giả định tenant_id và status độc lập, phép nhân selectivity của từng cột có thể sai.

Statistics một cột không mô tả đầy đủ tương quan này. Một số DBMS hỗ trợ:
- Multi-column statistics.
- Extended statistics về dependencies, distinct combinations hoặc most-common-value combinations.
- Filtered/filtered-index statistics.
- Column group statistics hoặc histogram theo biểu thức.

Sử dụng khi actual plan cho thấy sai lệch do tương quan, không phải chỉ vì có nhiều cột trong WHERE.

### 4.4. Histogram và giá trị skew

Histogram hữu ích khi phân bố không đều. Nếu hầu hết dòng có status='ACTIVE' nhưng một số trạng thái rất hiếm, histogram có thể giúp optimizer ước lượng theo giá trị.

Tuy nhiên, histogram có số bucket giới hạn và có thể không mô tả mọi giá trị. Nếu workload phụ thuộc hot key hoặc giá trị ngoài histogram, cần đo với các tham số đại diện và cân nhắc statistics target hoặc histogram options phù hợp.

### 4.5. Sampling hay full scan?

Sampling đọc một phần dữ liệu để ước lượng statistics. Nó thường nhanh và ít I/O hơn, nhưng có thể không đại diện tốt nếu dữ liệu skew hoặc giá trị hiếm.

Full scan đọc toàn bộ dữ liệu cần thiết để thu thập thống kê chính xác hơn theo cơ chế DBMS, nhưng có thể tốn CPU, I/O và thời gian, đặc biệt với bảng lớn.

Chọn dựa trên:
- Kích thước bảng.
- Độ lệch phân bố.
- Tầm quan trọng của truy vấn.
- Cửa sổ maintenance.
- Chi phí đọc dữ liệu.
- Sai lệch estimate hiện tại.

Không mặc định FULLSCAN cho mọi bảng. Cũng không mặc định sampling nhỏ luôn đủ.

## 5. Cập nhật statistics trong PostgreSQL

### 5.1. ANALYZE

PostgreSQL dùng ANALYZE để thu thập statistics về nội dung bảng và các cột. Ví dụ:

~~~sql
ANALYZE orders;
~~~

Chỉ định cột quan trọng:

~~~sql
ANALYZE orders (tenant_id, status, created_at);
~~~

Cập nhật statistics cho nhiều bảng có thể thực hiện trong cửa sổ maintenance phù hợp. VACUUM (ANALYZE) kết hợp thu hồi/đánh dấu không gian có thể tái sử dụng với thu thập statistics; hai mục tiêu vẫn khác nhau.

### 5.2. Autovacuum và autoanalyze

PostgreSQL có autovacuum daemon để tự động VACUUM và ANALYZE theo ngưỡng cấu hình. Ngưỡng autoanalyze thường dựa trên một giá trị nền cộng với tỷ lệ của số tuple trong bảng; các tham số cụ thể có thể thay đổi theo phiên bản và cấu hình.

Một bảng rất lớn có thể thay đổi nhiều dòng nhưng chưa đạt ngưỡng theo cấu hình mặc định hoặc cấu hình tùy chỉnh. Với bảng có workload quan trọng, hãy theo dõi:
- last_analyze và last_autoanalyze.
- Số tuple insert/update/delete kể từ lần analyze.
- Số dòng ước lượng so với thực tế.
- Query plan và latency.

Có thể xem một số trường trong pg_stat_user_tables:

~~~sql
SELECT relname,
       n_live_tup,
       n_mod_since_analyze,
       last_analyze,
       last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

Các cột và cách cập nhật thống kê phụ thuộc phiên bản PostgreSQL. n_live_tup và modification counters là ước lượng/thống kê vận hành, không phải phép đếm chính xác tại mọi thời điểm.

### 5.3. Tăng statistics target cho cột có skew

PostgreSQL cho phép điều chỉnh statistics target theo cột:

~~~sql
ALTER TABLE orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE orders (status);
~~~

Target lớn hơn có thể cho histogram/MCV chi tiết hơn nhưng tăng công việc thu thập và kích thước statistics. Chỉ tăng khi có bằng chứng histogram hiện tại chưa mô tả đủ phân bố.

Có thể xem thông tin trong view pg_stats, ví dụ n_distinct, most_common_vals, most_common_freqs, histogram_bounds và correlation.

### 5.4. Extended statistics

Với tương quan giữa tenant_id và status:

~~~sql
CREATE STATISTICS st_orders_tenant_status
    (dependencies, mcv)
ON tenant_id, status
FROM orders;

ANALYZE orders;
~~~

dependencies mô tả một số quan hệ phụ thuộc giữa các cột; mcv lưu các tổ hợp giá trị phổ biến. ndistinct có thể hữu ích cho ước lượng số nhóm phân biệt.

Extended statistics có giới hạn và không thay thế mọi dạng thống kê đa chiều. Hãy kiểm tra loại được hỗ trợ trong phiên bản PostgreSQL và xác minh estimated/actual rows sau khi tạo.

### 5.5. Partitioned table

Với bảng partitioned, cần hiểu statistics cấp partition và cấp parent được thu thập như thế nào ở phiên bản đang dùng. Sau khi nạp partition mới hoặc thay partition, hãy kiểm tra statistics ở phạm vi mà query planner sử dụng; có thể cần chạy ANALYZE trên parent và/hoặc partition theo thiết kế và phiên bản.

Không giả định autoanalyze trên một partition luôn cập nhật đầy đủ mọi thống kê toàn cục cần cho truy vấn qua parent.

## 6. Cập nhật statistics trong MySQL/InnoDB

### 6.1. ANALYZE TABLE

MySQL hỗ trợ:

~~~sql
ANALYZE TABLE orders;
~~~

Với InnoDB, thao tác này cập nhật key distribution/statistics mà optimizer dùng để ước lượng access path. Persistent statistics và sampling pages ảnh hưởng cách thu thập; hành vi có thể khác theo phiên bản và cấu hình.

Sau bulk load hoặc thay đổi lớn, hãy kiểm tra EXPLAIN/EXPLAIN ANALYZE và so sánh rows estimate với actual rows nếu phiên bản hỗ trợ.

### 6.2. Persistent statistics và sampling

InnoDB có thể lưu persistent statistics để tránh phải thu thập lại mỗi lần server khởi động. Các tham số như innodb_stats_persistent, innodb_stats_persistent_sample_pages và cấu hình liên quan ảnh hưởng đến việc lưu và lấy mẫu.

Tăng số pages lấy mẫu có thể cải thiện ước lượng trong một số trường hợp nhưng tăng chi phí ANALYZE. Không thay đổi toàn cục chỉ vì một bảng có skew; hãy kiểm tra phạm vi cấu hình và benchmark.

### 6.3. Histogram cho cột

MySQL hỗ trợ histogram statistics cho một số truy vấn và cột. Ví dụ:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, tenant_id
WITH 128 BUCKETS;
~~~

Histogram có thể giúp ước lượng predicate trên cột không có index hoặc cải thiện ước lượng phân bố. Số bucket càng lớn có thể mô tả chi tiết hơn nhưng tốn thêm metadata và chi phí thu thập. Cần kiểm tra phiên bản, loại histogram và khả năng áp dụng với query cụ thể.

Có thể xóa histogram khi không còn phù hợp:

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status;
~~~

Đừng tạo histogram cho mọi cột. Tập trung vào cột có predicate quan trọng và ước lượng đang sai.

### 6.4. Xác minh

Dùng EXPLAIN để xem optimizer ước lượng access path và rows; dùng EXPLAIN ANALYZE ở phiên bản hỗ trợ để quan sát iterator thực tế. ANALYZE TABLE không thay thế kiểm tra query plan, và không phải mọi sai lệch đều được giải quyết bằng histogram.

## 7. Cập nhật statistics trong SQL Server

### 7.1. Auto statistics

SQL Server có cơ chế tự tạo và tự cập nhật statistics theo nhu cầu và cấu hình database. Auto update statistics có thể được kích hoạt khi statistics đủ cũ theo ngưỡng thay đổi của phiên bản, compatibility level và loại statistics.

Nếu bảng thay đổi rất lớn, có thể chủ động cập nhật trước khi chạy workload quan trọng thay vì chờ truy vấn đầu tiên kích hoạt auto update. Tùy chọn asynchronous statistics update có thể thay đổi cách session đầu tiên chờ cập nhật; cần hiểu tác động plan và latency.

### 7.2. UPDATE STATISTICS

Cập nhật statistics cho bảng:

~~~sql
UPDATE STATISTICS dbo.orders;
~~~

Chỉ định statistics object:

~~~sql
UPDATE STATISTICS dbo.orders IX_orders_tenant_status;
~~~

Dùng full scan khi có lý do cần độ chính xác cao:

~~~sql
UPDATE STATISTICS dbo.orders WITH FULLSCAN;
~~~

FULLSCAN đọc toàn bộ dữ liệu liên quan và có thể tốn I/O/CPU. Với bảng lớn, sampling có thể là lựa chọn hợp lý nếu estimate đủ tốt. Không chạy FULLSCAN hàng loạt trong giờ cao điểm mà chưa đánh giá chi phí.

### 7.3. sp_updatestats

sp_updatestats có thể cập nhật statistics trên các bảng trong database theo cơ chế của SQL Server. Đây là tiện ích rộng, không nhất thiết là lựa chọn tối ưu cho mọi maintenance window. Hãy hiểu phạm vi và điều kiện cập nhật của nó, đồng thời đo thời gian và tác động.

### 7.4. Kiểm tra modification counter

Có thể kiểm tra thời điểm cập nhật, số dòng và số thay đổi kể từ lần cập nhật:

~~~sql
SELECT
    OBJECT_NAME(s.object_id) AS table_name,
    s.name AS statistics_name,
    p.last_updated,
    p.rows,
    p.rows_sampled,
    p.modification_counter
FROM sys.stats AS s
CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) AS p
WHERE s.object_id = OBJECT_ID('dbo.orders');
~~~

Các DMV và quyền truy cập phụ thuộc phiên bản/permission. Modification counter là tín hiệu để quyết định điều tra, không phải ngưỡng duy nhất cho mọi workload.

### 7.5. Query Store và plan regression

Query Store có thể lưu lịch sử query, plan và runtime statistics. Sau cập nhật statistics, so sánh:
- Plan trước/sau.
- Duration, CPU và logical reads.
- Wait categories nếu có.
- Số lần thực thi và phân bố tham số.
- Regression theo từng query.

Nếu có plan regression, trước hết tìm nguyên nhân cardinality/plan. Plan forcing có thể là biện pháp tạm thời có kiểm soát, nhưng cần theo dõi khi dữ liệu tiếp tục thay đổi.

## 8. Cập nhật statistics trong Oracle

### 8.1. DBMS_STATS

Oracle dùng package DBMS_STATS để thu thập và quản lý optimizer statistics. Ví dụ:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'APP',
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    cascade          => TRUE
  );
END;
/
~~~

AUTO_SAMPLE_SIZE để Oracle chọn sampling phù hợp; method_opt điều khiển histogram; cascade yêu cầu thu thập statistics cho index liên quan theo semantics của package.

Không dùng SIZE AUTO như một yêu cầu tạo histogram cho mọi cột. Oracle quyết định dựa trên workload và chính sách histogram; cần kiểm tra kết quả và chi phí.

### 8.2. Stale statistics

Oracle theo dõi mức thay đổi dữ liệu và có thể đánh dấu statistics là stale. Cơ chế monitoring và ngưỡng stale phụ thuộc cấu hình và phiên bản.

Có thể kiểm tra các view dictionary như DBA_TAB_STATISTICS, DBA_TAB_MODIFICATIONS và các view liên quan để xem trạng thái và số thay đổi. Cần quyền phù hợp và hiểu rằng thông tin modification có thể được cập nhật theo cơ chế nội bộ.

### 8.3. Partition và incremental statistics

Với bảng partitioned lớn, thu thập statistics toàn bảng có thể tốn kém. Oracle hỗ trợ incremental statistics trong một số cấu hình để cập nhật global statistics từ partition statistics. Việc cấu hình cần theo tài liệu phiên bản, loại partition và workload.

Sau partition exchange/load, xác minh cả partition-level và global statistics. Nếu global statistics không phản ánh partition mới, optimizer có thể ước lượng sai khi truy vấn toàn bảng.

### 8.4. Pending statistics và kiểm chứng

Oracle có các cơ chế cho phép thu thập statistics ở trạng thái pending và kiểm tra plan trước khi publish, tùy cấu hình. Cách này có thể giúp đánh giá ảnh hưởng trước khi statistics mới được dùng rộng rãi. Hãy áp dụng theo quy trình change management và kiểm tra đúng phiên bản.

## 9. Quy trình cập nhật sau thay đổi dữ liệu lớn

### Bước 1: Ghi nhận thay đổi dữ liệu

Xác định bảng và partition chịu tác động, loại thay đổi (insert/update/delete/partition exchange), số dòng, tỷ lệ thay đổi và cột có phân bố thay đổi.

Ví dụ:
- Nạp thêm 30 triệu đơn hàng.
- Chuyển 20 triệu đơn từ PENDING sang EXPIRED.
- Xóa dữ liệu cũ hơn 5 năm.
- Thêm partition tháng mới.
- Tạo index phục vụ truy vấn báo cáo.

### Bước 2: Xác định workload bị ảnh hưởng

Lấy query fingerprint, execution plan và baseline của truy vấn dùng các bảng/cột đó. Ưu tiên query có p95/p99 cao, CPU/logical reads lớn hoặc ảnh hưởng nghiệp vụ.

### Bước 3: Chọn statistics object

Xác định cần cập nhật:
- Table/column statistics.
- Index statistics.
- Histogram trên cột skew.
- Multi-column/extended statistics.
- Partition/global statistics.
- Statistics cho expression hoặc generated column nếu DBMS hỗ trợ.

Không cập nhật mọi statistics object nếu chỉ một phần dữ liệu thay đổi và chi phí maintenance quá cao; nhưng cũng không bỏ sót statistics cấp bảng/global mà optimizer cần.

### Bước 4: Chọn sampling và cửa sổ chạy

Ước lượng chi phí I/O/CPU. Chọn auto sample hoặc full scan theo DBMS và mức sai lệch cần khắc phục. Lên lịch ngoài peak nếu bảng lớn và ANALYZE có thể cạnh tranh tài nguyên.

Với workload nhạy latency, cân nhắc maintenance theo partition hoặc theo bảng quan trọng. Tránh chạy nhiều tác vụ statistics lớn đồng thời trên cùng storage.

### Bước 5: Thu thập statistics

Dùng lệnh phù hợp với DBMS. Ghi lại thời điểm, phạm vi, sampling mode, duration và warnings. Đảm bảo thao tác hoàn tất thành công.

### Bước 6: Kiểm tra freshness và nội dung

Xác minh last updated, rows sampled, modification counter, histogram hoặc các metadata tương ứng. Với cột quan trọng, kiểm tra NDV/MCV/histogram có phản ánh thay đổi đã biết không.

### Bước 7: Kiểm tra actual plan

Chạy các truy vấn đại diện với tham số phổ biến và hiếm. So sánh estimated rows với actual rows, access path, join order, DOP, memory grant, sort/hash spill và buffer reads.

### Bước 8: Đo lại workload

Đo latency, throughput, CPU, memory, I/O, temp usage và waits. Bao gồm query quan trọng khác dùng chung bảng/index để phát hiện tác động phụ.

### Bước 9: Theo dõi plan sau maintenance

Theo dõi trong giờ cao điểm và các chu kỳ batch. Nếu plan mới gây regression, xác định query/parameter cụ thể, xem lại statistics target/sample hoặc dùng biện pháp plan management phù hợp DBMS.

## 10. Theo dõi hiệu quả sau cập nhật

### 10.1. Theo dõi freshness

Duy trì một bảng/đầu mục vận hành ghi:
- Tên bảng/partition.
- Statistics object hoặc cột quan trọng.
- Thời điểm cập nhật gần nhất.
- Số dòng và số dòng lấy mẫu.
- Số thay đổi kể từ lần cập nhật nếu có.
- Phương thức sampling.
- Thời gian chạy và tài nguyên tiêu thụ.
- Người hoặc job thực hiện.

Không cần xây một hệ thống phức tạp nếu DBMS đã cung cấp monitoring phù hợp; mục tiêu là biết statistics nào đã cũ và maintenance nào vừa diễn ra.

### 10.2. Theo dõi chất lượng ước lượng

Với query fingerprint quan trọng, lưu:
- Estimated rows và actual rows tại node quan trọng.
- Q-error hoặc tỷ lệ sai lệch.
- Join order và join algorithm.
- Scan/index access.
- Memory grant và spill.
- Buffer/logical/physical reads.

Có thể so sánh các plan theo thời gian để nhận ra khi cardinality estimates bắt đầu lệch sau khi dữ liệu tăng hoặc phân bố thay đổi.

### 10.3. Theo dõi hiệu năng

Đo:
- p50/p95/p99 duration.
- CPU time.
- Logical reads/buffer hits.
- Physical reads.
- Rows examined và rows returned.
- Memory, temp I/O và spill.
- Lock/latch wait.
- Throughput và concurrency.

Một truy vấn nhanh hơn trong benchmark đơn lẻ nhưng làm tăng CPU hoặc memory toàn hệ thống có thể không phải cải thiện tốt. Đánh giá ở mức workload.

### 10.4. Theo dõi plan regression

Plan có thể thay đổi sau cập nhật statistics, thay index hoặc thay dữ liệu. Dùng query history/plan history của DBMS để xác định:
- Plan nào mới xuất hiện.
- Query nào tăng duration hoặc reads.
- Tham số nào bị ảnh hưởng.
- Regression có kéo dài hay chỉ do cache/warm-up.
- Có liên quan tới auto stats update hoặc maintenance window không.

Nếu DBMS hỗ trợ plan baseline, Query Store hoặc SQL plan management, có thể dùng để quản lý thay đổi, nhưng cần tránh cố định plan vĩnh viễn khi dữ liệu tiếp tục thay đổi.

### 10.5. Theo dõi chi phí của chính maintenance

Statistics update cũng tiêu thụ tài nguyên:
- I/O đọc bảng/index.
- CPU để lấy mẫu và xây histogram.
- Memory cho sort/sample.
- Lock hoặc latch tùy engine.
- Plan invalidation/recompile.
- Tác động tới cache và workload đang chạy.

Ghi nhận thời gian chạy, I/O, CPU và mức ảnh hưởng đến truy vấn khác. Một lịch cập nhật quá thường xuyên có thể tạo tải nền không cần thiết.

## 11. Xử lý khi statistics mới không cải thiện truy vấn

### 11.1. Kiểm tra nguyên nhân sai lệch

Nếu estimate vẫn sai:
- Predicate có biểu thức hoặc implicit cast không?
- Có tương quan nhiều cột không?
- Có skew hoặc hot key không?
- Histogram có đủ bucket không?
- Có dữ liệu ngoài histogram không?
- Query dùng parameter khác với tham số benchmark không?
- Join key có duplicate hoặc NULL không?
- Statistics có đúng bảng/partition mà optimizer sử dụng không?

### 11.2. Cân nhắc extended/multicolumn statistics

Nếu sai lệch đến từ tương quan, dùng cơ chế statistics đa cột hoặc filtered statistics mà DBMS hỗ trợ. Sau khi tạo, thu thập lại và kiểm tra actual plan.

Không tạo statistics đa cột cho mọi tổ hợp cột. Chọn theo query workload và evidence.

### 11.3. Kiểm tra query và index

Statistics tốt không bù được:
- Predicate không sargable.
- Function/cast ngăn dùng index.
- Thiếu index cho access path cần thiết.
- JOIN tạo fan-out ngoài ý muốn.
- Query đọc quá nhiều cột/dòng.
- Partition pruning không hoạt động.

Nếu optimizer đã ước lượng đúng nhưng truy vấn vẫn chậm, nguyên nhân có thể nằm ở I/O, CPU, lock, memory hoặc network chứ không phải statistics.

### 11.4. Kiểm tra parameter sensitivity

Một plan có thể phù hợp với tenant lớn nhưng không phù hợp tenant nhỏ. Nếu optimizer cache plan dựa trên một lần compile, tham số sau có thể chịu plan không tối ưu.

Đánh giá nhiều tham số đại diện, xem plan cache/parameter-sensitive features của DBMS và áp dụng biện pháp phù hợp. Không dùng hint hoặc force plan chỉ dựa trên một trường hợp.

### 11.5. Không ép plan chỉ vì cost estimate thay đổi

Estimated cost là mô hình nội bộ, không phải thời gian thực. Một cost number cao hơn sau statistics update không nhất thiết có nghĩa truy vấn chậm hơn. So sánh actual elapsed time, CPU, reads, waits và kết quả đúng.

## 12. Những thao tác bảo trì khác không nên nhầm với statistics

| Thao tác | Mục tiêu chính | Có thay thế cập nhật statistics không? |
|---|---|---|
| ANALYZE/UPDATE STATISTICS | Cập nhật ước lượng cho optimizer | Đây là thao tác statistics |
| VACUUM (PostgreSQL) | Quản lý dead tuples và khả năng tái sử dụng không gian; tùy lệnh có thể kết hợp ANALYZE | Không thay thế mọi mục tiêu của ANALYZE |
| REINDEX/REBUILD | Xây lại cấu trúc index | Không thay thế thống kê cột/đa cột |
| REORGANIZE/defragment | Tổ chức lại cấu trúc vật lý tùy DBMS | Không bảo đảm histogram phù hợp |
| Partition maintenance | Tạo, detach, exchange, switch hoặc xóa partition | Có thể cần cập nhật partition/global statistics |
| Purge/archive | Loại hoặc di chuyển dữ liệu | Có thể làm statistics cũ |
| Backup | Tạo bản sao phục hồi | Không cập nhật statistics theo mục tiêu truy vấn |

Một số thao tác có thể tự cập nhật một phần statistics. Hãy kiểm tra hành vi cụ thể của DBMS và tùy chọn sử dụng; không suy ra mọi statistics liên quan đã được cập nhật.

## 13. Ví dụ xuyên suốt: nạp dữ liệu đơn hàng lớn

Giả sử bảng orders có 100 triệu dòng. Hệ thống nạp thêm 30 triệu dòng trong một batch. Phần dữ liệu mới chủ yếu thuộc tenant_id=42 và status='PENDING'. Một dashboard truy vấn:

~~~sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
GROUP BY customer_id;
~~~

Trước khi nạp, tenant 42 có ít đơn hàng. Sau nạp, tenant này chiếm tỷ trọng lớn của bảng, dù phần lớn đơn mới là PENDING. Statistics cũ có thể ước lượng tenant_id=42 thấp hơn thực tế, hoặc giả định tenant_id và status độc lập.

Quy trình xử lý:

1. Lưu baseline plan, actual rows, reads, duration và tham số tenant.
2. Hoàn tất batch load và ghi nhận số dòng/các giá trị phân bố mới.
3. Cập nhật statistics trên orders và các cột tenant_id, status, created_at.
4. Nếu actual plan cho thấy tương quan tenant/status, cân nhắc extended hoặc multicolumn statistics theo DBMS.
5. Chạy lại truy vấn với tenant 42 và một số tenant nhỏ để kiểm tra parameter sensitivity.
6. So sánh estimated/actual rows, join/aggregate strategy, memory và spill.
7. Đo p95/p99 và CPU/I/O trên workload dashboard cùng API OLTP.
8. Theo dõi plan sau maintenance trong giờ cao điểm.

Không nên tạo index hoặc ép plan trước khi xem statistics mới đã cải thiện cardinality estimate hay chưa. Nếu estimate đã đúng mà scan vẫn đắt, cần đánh giá index, partition pruning hoặc cách tổ chức dữ liệu.

## 14. Những sai lầm thường gặp

**Cập nhật statistics theo lịch cố định mà không xét thay đổi dữ liệu.** Có bảng gần như bất biến và bảng thay đổi hàng triệu dòng mỗi giờ. Cùng một lịch không phù hợp cả hai.

**Chỉ xem tuổi statistics.** Statistics mới vẫn có thể không mô tả đúng skew hoặc tương quan; statistics cũ có thể vẫn đủ tốt với bảng ổn định.

**Chạy FULLSCAN cho mọi bảng.** Full scan có thể tiêu thụ I/O/CPU lớn. Chọn sampling theo kích thước và mức độ cần chính xác.

**Nghĩ ANALYZE sẽ làm index bớt phân mảnh.** Statistics và cấu trúc vật lý của index là hai vấn đề khác nhau.

**Chỉ cập nhật statistics của index mà bỏ qua cột predicate.** Optimizer có thể vẫn thiếu thông tin về phân bố cột và tương quan.

**Cho rằng statistics mới luôn làm plan nhanh hơn.** Plan có thể đổi và gây regression cho một số tham số.

**Không kiểm tra actual rows.** Một plan nhìn hợp lý hoặc estimated cost thấp chưa chứng minh thực thi tốt.

**Chỉ benchmark một tham số.** Skew và parameter sensitivity có thể làm các tenant/trạng thái khác nhau có chi phí khác nhau.

**Tăng statistics target cho mọi cột.** Statistics chi tiết hơn có chi phí thu thập và lưu trữ; chỉ tăng cho cột có bằng chứng.

**Nhầm partition statistics với global statistics.** Truy vấn qua toàn bảng có thể cần thống kê tổng hợp khác với từng partition.

**Cập nhật statistics trong peak mà không đánh giá tác động.** Maintenance có thể cạnh tranh I/O, CPU và gây recompile.

**Force plan để che một statistics problem.** Plan forcing có thể là biện pháp tạm thời nhưng không sửa nguyên nhân gốc và có thể lỗi thời khi dữ liệu đổi.

## 15. Checklist cập nhật statistics và theo dõi hiệu quả

- [ ] Đã ghi nhận bảng/partition và khối lượng insert/update/delete/load chưa?
- [ ] Đã xác định các cột dùng trong WHERE, JOIN, GROUP BY và ORDER BY chưa?
- [ ] Đã lưu baseline query plan và runtime metrics trước maintenance chưa?
- [ ] Đã so sánh estimated rows với actual rows ở node đầu tiên có sai lệch chưa?
- [ ] Đã kiểm tra skew, NULL, NDV và tương quan nhiều cột chưa?
- [ ] Đã xác định statistics cấp bảng, cột, index, histogram hay partition cần cập nhật chưa?
- [ ] Đã chọn sampling hoặc full scan theo chi phí và mức chính xác cần thiết chưa?
- [ ] Đã chạy ANALYZE/UPDATE STATISTICS đúng DBMS và đúng phạm vi chưa?
- [ ] Đã xác minh thời điểm cập nhật, rows sampled và modification counter chưa?
- [ ] Đã kiểm tra actual plan sau cập nhật với tham số phổ biến và hiếm chưa?
- [ ] Đã đo p50/p95/p99, CPU, reads, memory, spill và waits chưa?
- [ ] Đã kiểm tra plan regression trên các query fingerprint khác chưa?
- [ ] Đã đánh giá chi phí maintenance và tác động lên workload đang chạy chưa?
- [ ] Đã phân biệt statistics maintenance với VACUUM, REBUILD/REINDEX và partition maintenance chưa?
- [ ] Đã có lịch theo dõi và phương án xử lý khi plan regression xuất hiện chưa?

## Kết luận

Statistics là đầu vào quan trọng để optimizer ước lượng cardinality và chọn execution plan. Bulk load, delete/update lớn, thay đổi phân bố, partition maintenance và giá trị mới có thể làm thống kê cũ không còn đại diện. Cập nhật ANALYZE/UPDATE STATISTICS đúng phạm vi giúp optimizer có thông tin mới hơn, nhưng không bảo đảm mọi truy vấn sẽ nhanh hơn; sampling, histogram, tương quan nhiều cột và parameter sensitivity vẫn có thể tạo sai lệch.

Hãy bắt đầu từ workload và actual plan: xác định node đầu tiên có estimated rows khác xa actual rows, kiểm tra freshness và phân bố dữ liệu, chọn statistics object cùng sampling phù hợp, rồi đo lại plan và p95/p99 trên nhiều tham số. Theo dõi cả lợi ích lẫn chi phí maintenance, đồng thời phân biệt statistics với bảo trì cấu trúc index và thu hồi không gian. Quy trình có baseline, readback và giám sát sau cập nhật giúp duy trì chất lượng plan khi dữ liệu tiếp tục thay đổi.


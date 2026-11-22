# Phân mảnh chỉ mục: cách đo và ý nghĩa theo từng hệ quản trị

Chỉ mục B-tree giúp database tìm hàng và duyệt một khoảng khóa mà không phải quét toàn bộ bảng. Trong quá trình INSERT, UPDATE và DELETE, các trang của chỉ mục có thể được tách, để trống một phần hoặc nằm xa nhau trong không gian lưu trữ. Theo thời gian, cấu trúc chỉ mục có thể có phân mảnh logic, mật độ trang thấp hoặc phần không gian bị lãng phí. Những hiện tượng này đôi khi làm tăng số trang phải đọc, giảm hiệu quả cache và kéo dài các truy vấn quét theo thứ tự khóa.

Tuy nhiên, một chỉ mục có tỷ lệ phân mảnh cao không tự động là nguyên nhân gây chậm. Ý nghĩa của chỉ số phụ thuộc hệ quản trị, loại chỉ mục, số trang, kiểu truy vấn và tầng lưu trữ. SQL Server báo tỷ lệ phân mảnh logic của leaf page theo cách riêng; PostgreSQL có thể đo leaf density và leaf fragmentation bằng extension; MySQL InnoDB cung cấp thống kê số trang nhưng không có một tỷ lệ phân mảnh phổ quát tương đương; Oracle có các thống kê cấu trúc riêng. Không thể áp dụng cùng một ngưỡng hoặc cùng một lệnh rebuild cho mọi engine.

Trong DATABASE_PERFORMANCE, việc bảo trì chỉ mục phải bắt đầu từ đo đạc và tác động đến workload. Cần phân biệt phân mảnh logic, page density, bloat và dung lượng trống; đo đúng chỉ mục đang phục vụ truy vấn quan trọng; đánh giá chi phí đọc trước và sau; rồi mới chọn REORGANIZE, REBUILD, COALESCE, REINDEX hoặc không làm gì. Bảo trì quá thường xuyên cũng tiêu tốn I/O, CPU, log, dung lượng tạm và có thể gây blocking.

## 1. Chỉ mục B-tree và các dạng phân mảnh

B-tree thường được tổ chức thành các trang (page hoặc block). Các trang trong tầng lá chứa khóa chỉ mục và thông tin định vị hàng, còn các trang phía trên giúp tìm đường đến vùng khóa cần đọc.

Khi chỉ mục được tạo, các trang được sắp xếp theo thứ tự khóa logic. Sau đó, thay đổi dữ liệu có thể làm cấu trúc vật lý khác dần so với trạng thái ban đầu.

### 1.1. Phân mảnh logic

Phân mảnh logic xảy ra khi thứ tự các trang lá theo khóa không còn tương ứng tốt với thứ tự vật lý của chúng trong file hoặc tablespace. Khi truy vấn phải duyệt một dải khóa, database có thể phải chuyển giữa nhiều vùng lưu trữ thay vì đọc các trang theo thứ tự vật lý thuận lợi.

Khái niệm này phụ thuộc engine. SQL Server có metric logical fragmentation được tính từ thứ tự page trong B-tree. PostgreSQL có metric leaf_fragmentation trong pgstattuple extension. Với InnoDB, không nên tự suy ra một tỷ lệ tương đương chỉ từ số trang hoặc dung lượng file.

### 1.2. Mật độ trang (page density)

Page density thể hiện mức độ sử dụng không gian trong trang. Một trang có density thấp chứa ít entry hơn khả năng của nó, do đó cùng một tập khóa có thể trải trên nhiều trang hơn.

Density thấp có thể làm:

- Tăng số leaf page cần đọc khi range scan.
- Tăng kích thước index và lượng dữ liệu cần giữ trong buffer cache.
- Tăng số lần đọc trang khi working set không nằm trọn trong RAM.
- Tăng chi phí backup, replication hoặc bảo trì do index lớn hơn.

Tuy nhiên, trang có quá ít khoảng trống cũng có thể làm tăng page split khi chèn khóa mới. Một mức fill factor thấp có chủ đích đôi khi giảm split cho workload có insert ngẫu nhiên hoặc update làm tăng kích thước entry.

### 1.3. Bloat và không gian có thể tái sử dụng

Bloat là phần không gian cấu trúc chiếm giữ nhưng không mang lại lượng dữ liệu hữu ích tương xứng. Nguyên nhân có thể là hàng hoặc index entry bị xóa, cập nhật tạo phiên bản mới, trang không được thu hồi hoặc cấu trúc không được compact.

Bloat không hoàn toàn giống phân mảnh logic. Một index có thể có page order tương đối tốt nhưng vẫn lớn do density thấp; ngược lại, index có leaf page nằm rời rạc nhưng vẫn có density tốt.

### 1.4. Phân mảnh chỉ mục và phân mảnh bảng

Phân mảnh index nói về cấu trúc index. Phân mảnh bảng nói về cách các hàng được lưu trong heap, clustered storage hoặc segment. Một bảng có thể có index được tổ chức tốt nhưng dữ liệu bảng bị phân tán; cũng có thể bảng gọn nhưng một secondary index bị bloat.

Khi truy vấn dùng index để tìm khóa rồi phải đọc nhiều hàng từ bảng, chi phí có thể nằm ở lookup vào bảng chứ không phải leaf page của index. Cần xem execution plan và số lần truy cập thực tế để tách hai nguồn chi phí.

## 2. Vì sao phân mảnh xuất hiện?

### 2.1. INSERT vào giữa vùng khóa

Nếu khóa mới thường nằm giữa các khóa hiện có, database phải chèn entry vào leaf page tương ứng. Khi trang không còn đủ chỗ, engine có thể split page và phân phối entry sang trang khác. Việc cấp phát trang mới có thể làm thứ tự vật lý không còn liên tục theo thứ tự khóa.

Khóa ngẫu nhiên như UUID v4 thường phân bố insert trên nhiều vùng B-tree. Điều này có thể làm tăng page split, ghi ngẫu nhiên và mức sử dụng cache so với khóa có tính tuần tự, dù kết quả thực tế còn phụ thuộc engine, kích thước khóa và workload.

### 2.2. DELETE và UPDATE

DELETE có thể để lại khoảng trống trong leaf page hoặc đánh dấu entry là không còn hiệu lực. UPDATE một cột tham gia index có thể tương đương xóa entry cũ và thêm entry mới. UPDATE làm tăng kích thước hàng hoặc entry cũng có thể khiến trang không còn đủ chỗ.

Một số engine tái sử dụng khoảng trống trong trang hoặc thực hiện cleanup dần. Không phải mọi thao tác xóa đều lập tức thu hồi dung lượng file cho hệ điều hành.

### 2.3. Tải ghi và fill factor

Fill factor quy định mức lấp đầy mục tiêu khi tạo hoặc rebuild index ở các hệ quản trị hỗ trợ. Chừa khoảng trống có thể giảm split trong workload insert/update nhất định, nhưng làm index chiếm nhiều trang hơn ngay từ đầu.

Không chọn fill factor thấp cho mọi index. Index chủ yếu đọc và ít thay đổi có thể hưởng lợi từ density cao; index có insert ngẫu nhiên hoặc update thường xuyên có thể cần khoảng trống. Hãy đo page split, page density, index size và read workload sau khi thay đổi.

### 2.4. Dữ liệu tăng trưởng và vòng đời bảng

Index trên bảng ghi liên tục có thể thay đổi cấu trúc thường xuyên. Bảng lịch sử ít thay đổi có thể ổn định trong thời gian dài. Với bảng partition theo ngày hoặc tháng, mỗi partition có vòng đời và phân bố truy cập riêng; cần đo theo partition thay vì áp cùng một thao tác bảo trì lên toàn bảng.

## 3. Phân mảnh ảnh hưởng hiệu năng trong trường hợp nào?

### 3.1. Range scan và index scan

Truy vấn đọc một khoảng khóa có thể phải duyệt nhiều leaf page. Nếu các trang nằm rời rạc hoặc index có nhiều trang hơn cần thiết, số lần đọc và chi phí I/O có thể tăng. Tác động rõ hơn khi working set lớn hơn buffer cache hoặc storage có độ trễ cao.

### 3.2. Point lookup

Truy vấn tìm một khóa duy nhất thường đi qua root, intermediate page và một leaf page. Với point lookup, phân mảnh logic giữa các leaf page có thể ít ảnh hưởng hơn so với range scan. Page density thấp vẫn có thể làm index lớn hơn và giảm hiệu quả cache, nhưng không nên mặc định tỷ lệ fragmentation cao làm point lookup chậm.

### 3.3. Index-only hoặc covering access

Khi index chứa đủ cột truy vấn cần, engine có thể tránh đọc bảng hoặc heap trong một số điều kiện. Index lớn và nhiều leaf page có thể làm tăng số page cần duyệt. Với PostgreSQL, index-only scan còn phụ thuộc visibility map; với SQL Server, covering index có thể tránh key lookup; với các engine khác, cơ chế tương ứng cũng cần được xem xét.

### 3.4. Cache có thể che giấu hoặc khuếch đại tác động

Nếu toàn bộ index nằm trong RAM, các lần đọc rời rạc có thể ít tốn I/O vật lý hơn. Khi working set vượt RAM, index lớn và density thấp có thể làm cache miss tăng. Vì vậy, cùng một index có thể có hiệu năng khác nhau khi cache nóng và cache lạnh.

Đo cả logical reads, physical reads, buffer hit, storage latency và p95/p99. Không chỉ dựa vào thời gian của một lần chạy trong cache nóng.

## 4. Đọc đúng chỉ số trước khi bảo trì

Các chỉ số thường cần xem:

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Page count / leaf pages | Index có đủ lớn để vấn đề cấu trúc đáng quan tâm không? |
| Logical fragmentation | Leaf page có lệch thứ tự vật lý theo định nghĩa của engine không? |
| Page density / average leaf density | Mỗi page đang chứa bao nhiêu dữ liệu hữu ích? |
| Deleted entries / dead tuples | Có nhiều entry đã xóa hoặc chưa được cleanup không? |
| Index size | Index chiếm bao nhiêu dung lượng? |
| Usage statistics | Index có thực sự được workload sử dụng không? |
| Read and write counters | Index phục vụ đọc nào và tạo chi phí ghi ra sao? |
| Query latency and reads | Truy vấn quan trọng có bị ảnh hưởng không? |

### 4.1. Số trang là điều kiện diễn giải quan trọng

Một index rất nhỏ có thể báo tỷ lệ fragmentation cao nhưng chỉ có vài trang. Rebuild nó thường không mang lại lợi ích đáng kể và chi phí thao tác có thể lớn hơn phần đọc tiết kiệm được.

Ngược lại, tỷ lệ fragmentation vừa phải trên một index rất lớn, phục vụ range scan liên tục, có thể đáng điều tra hơn. Hãy luôn xem page count, kích thước index và mức sử dụng.

### 4.2. Usage statistics không phải fragmentation statistics

Chỉ số số lần seek, scan hoặc lookup cho biết index được sử dụng ra sao, không trực tiếp cho biết index bị phân mảnh. Index không được dùng có thể là ứng viên rà soát để giảm chi phí ghi, nhưng cần xét unique constraint, foreign key, workload hiếm và thời gian reset thống kê trước khi loại bỏ.

### 4.3. Thống kê optimizer khác thống kê cấu trúc

ANALYZE hoặc DBMS_STATS thường thu thập thông tin về phân bố dữ liệu để optimizer ước lượng cardinality và chọn plan. Việc cập nhật optimizer statistics không đồng nghĩa index đã được compact hoặc hết phân mảnh.

Ngược lại, rebuild index có thể làm thay đổi cấu trúc và trong một số engine cập nhật hoặc làm mới một phần thống kê, nhưng không nên coi rebuild là thay thế cho quy trình statistics management có chủ đích.

## 5. SQL Server: đo logical fragmentation và page density

SQL Server cung cấp DMV sys.dm_db_index_physical_stats để xem thông tin cấu trúc vật lý của index và heap. Với rowstore B-tree, các cột thường được quan tâm gồm:

- avg_fragmentation_in_percent: tỷ lệ phân mảnh logic theo thứ tự leaf page.
- avg_page_space_used_in_percent: mức sử dụng trung bình của không gian trang.
- page_count: số trang trong cấp đang xem.
- index_level: cấp của B-tree; 0 là leaf level.
- alloc_unit_type_desc: loại allocation unit.

### 5.1. Truy vấn đo cho một bảng

~~~sql
SELECT
    OBJECT_SCHEMA_NAME(ps.object_id) AS schema_name,
    OBJECT_NAME(ps.object_id) AS table_name,
    i.name AS index_name,
    ps.index_type_desc,
    ps.index_level,
    ps.page_count,
    ps.avg_fragmentation_in_percent,
    ps.avg_page_space_used_in_percent
FROM sys.dm_db_index_physical_stats(
    DB_ID(),
    OBJECT_ID(N'dbo.Orders'),
    NULL,
    NULL,
    'SAMPLED'
) AS ps
JOIN sys.indexes AS i
    ON i.object_id = ps.object_id
   AND i.index_id = ps.index_id
WHERE ps.index_level = 0
  AND ps.alloc_unit_type_desc = 'IN_ROW_DATA'
ORDER BY ps.page_count DESC;
~~~

Truy vấn giới hạn ở leaf level của in-row data để tập trung vào phần thường được range scan. Nếu bảng dùng partition hoặc nhiều allocation unit, cần bổ sung partition_number và kiểm tra các dòng kết quả tương ứng. DMV cũng trả thông tin cho loại cấu trúc khác; không áp dụng diễn giải B-tree cho columnstore.

### 5.2. Chọn chế độ LIMITED, SAMPLED hoặc DETAILED

sys.dm_db_index_physical_stats hỗ trợ các chế độ:

- LIMITED: nhanh hơn, kiểm tra ít thông tin hơn; phù hợp khảo sát ban đầu.
- SAMPLED: lấy mẫu để ước lượng trên index lớn.
- DETAILED: kiểm tra chi tiết nhiều trang hơn và tốn tài nguyên hơn.

Không chạy DETAILED cho mọi index trên toàn database trong giờ cao điểm nếu chưa đánh giá chi phí. Bắt đầu bằng LIMITED hoặc SAMPLED, lọc index lớn và workload quan trọng, sau đó mới kiểm tra sâu ứng viên cần thiết.

### 5.3. Ý nghĩa của avg_fragmentation_in_percent

Đây là chỉ số thứ tự logic của leaf page so với thứ tự vật lý kế tiếp theo định nghĩa của SQL Server. Nó không phải tỷ lệ phần trăm dữ liệu bị mất hoặc dung lượng trống. Cần đọc cùng page_count và page density.

Một index nhỏ có tỷ lệ cao không nhất thiết đáng rebuild. Một index có fragmentation thấp nhưng page density thấp vẫn có thể chiếm nhiều trang và làm tăng I/O. Ngưỡng 5%, 10% hay 30% thường thấy trong tài liệu cũ chỉ là quy tắc tham khảo; quyết định phải dựa trên kích thước, kiểu truy vấn và chi phí bảo trì.

### 5.4. REORGANIZE và REBUILD

- ALTER INDEX ... REORGANIZE thực hiện tổ chức lại leaf page theo cách tăng dần, thường ít gây gián đoạn hơn; không tương đương tạo lại toàn bộ index.
- ALTER INDEX ... REBUILD tạo lại index, có thể compact page và thay đổi fill factor. Khả năng online, mức blocking, log và yêu cầu edition/version phụ thuộc cấu hình.

Ví dụ:

~~~sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REORGANIZE;
~~~

~~~sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD WITH (ONLINE = ON);
~~~

ONLINE = ON không được hỗ trợ cho mọi loại index, phiên bản hoặc edition; thao tác vẫn có thể cần khóa ngắn ở các giai đoạn nhất định và sử dụng thêm tài nguyên. Cần kiểm tra khả năng hỗ trợ trước khi dùng.

REORGANIZE không tự cập nhật statistics như một lần index rebuild đầy đủ; nếu optimizer statistics cần cập nhật, hãy lập kế hoạch UPDATE STATISTICS riêng. Rebuild có thể cập nhật index statistics, nhưng vẫn cần đánh giá statistics theo yêu cầu của workload.

## 6. PostgreSQL: đo leaf density và fragmentation bằng pgstattuple

PostgreSQL không cung cấp một tỷ lệ fragmentation B-tree chuẩn trong các view thống kê usage thông thường. pg_stat_user_indexes cho biết số lần scan và số tuple đọc/fetch, không phải phân mảnh cấu trúc.

Extension pgstattuple cung cấp hàm pgstatindex để kiểm tra một B-tree index. Extension phải được cài đặt và quyền truy cập cần phù hợp:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstatindex('public.ix_orders_created_at');
~~~

Các trường thường được quan tâm:

- tree_level: độ sâu của B-tree.
- index_size: kích thước index tính bằng byte.
- internal_pages và leaf_pages: số trang ở các tầng.
- empty_pages và deleted_pages: số trang trống hoặc đã đánh dấu xóa theo cách extension đo.
- avg_leaf_density: mật độ trung bình của leaf page.
- leaf_fragmentation: mức độ phân tán vật lý của leaf page theo định nghĩa pgstattuple.

### 6.1. Diễn giải kết quả

avg_leaf_density thấp có thể cho thấy index dùng nhiều page hơn cần thiết. leaf_fragmentation cao cho biết leaf page phân tán theo cách đo của extension; không được hiểu giống hoàn toàn avg_fragmentation_in_percent của SQL Server.

pgstatindex phải đọc cấu trúc index để thu thập số liệu, do đó có chi phí I/O và CPU tùy kích thước. Không chạy hàng loạt trên mọi index lớn trong giờ cao điểm mà không đo tác động.

### 6.2. Phân biệt pg_stat_user_indexes và pgstatindex

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
~~~

Truy vấn này cho biết index được sử dụng như thế nào kể từ lần reset thống kê phù hợp. Nó không đo page density hoặc leaf fragmentation. Kết hợp usage statistics với pgstatindex để xác định index lớn, bị phân tán và thực sự quan trọng với workload.

### 6.3. VACUUM, REINDEX và pg_repack

- VACUUM giúp dọn dead tuple và làm không gian có thể tái sử dụng theo cơ chế PostgreSQL; VACUUM thông thường không tương đương rebuild toàn bộ B-tree index.
- REINDEX tạo lại index, có thể thu gọn cấu trúc và loại bỏ bloat.
- REINDEX CONCURRENTLY giảm thời gian chặn thao tác ghi so với rebuild thông thường trong các trường hợp được hỗ trợ, nhưng cần thêm dung lượng, thời gian và công việc đồng bộ.
- pg_repack là extension/công cụ bên ngoài có thể tổ chức lại bảng hoặc index với mức blocking được thiết kế thấp hơn, nhưng cần cài đặt, quyền, dung lượng và điều kiện vận hành phù hợp.

Ví dụ:

~~~sql
REINDEX INDEX CONCURRENTLY public.ix_orders_created_at;
~~~

Kiểm tra phiên bản PostgreSQL, loại index và giới hạn của REINDEX CONCURRENTLY trước khi triển khai. Không chạy đồng thời nhiều rebuild lớn chỉ vì một metric fragmentation cao.

## 7. MySQL InnoDB: thống kê trang và giới hạn đo fragmentation

InnoDB tổ chức chỉ mục bằng B-tree. Các trang index được quản lý trong tablespace và buffer pool. MySQL cung cấp thống kê persistent index trong mysql.innodb_index_stats, nhưng không có một tỷ lệ fragmentation B-tree phổ quát tương đương SQL Server.

Có thể xem thống kê:

~~~sql
SELECT
    database_name,
    table_name,
    index_name,
    stat_name,
    stat_value,
    sample_size,
    last_update
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
~~~

Các stat_name thường gặp gồm size, n_leaf_pages và các thống kê cardinality theo prefix như n_diff_pfxNN. Tên và dữ liệu cụ thể phụ thuộc phiên bản, persistent statistics và trạng thái ANALYZE TABLE.

### 7.1. Diễn giải thống kê InnoDB

- size thường biểu thị số trang của index.
- n_leaf_pages biểu thị số trang lá được thống kê.
- n_diff_pfxNN hỗ trợ ước lượng số giá trị phân biệt của các prefix khóa.

Các số liệu này giúp hiểu kích thước và đặc điểm index, nhưng không tự tạo ra phần trăm phân mảnh logic. Không lấy size hoặc n_leaf_pages rồi coi đó là fragmentation percentage.

### 7.2. Kết hợp với usage và I/O

Có thể kết hợp:

- performance_schema.table_io_waits_summary_by_index_usage để xem I/O theo index.
- sys schema nếu đã được cài và cung cấp view tổng hợp phù hợp.
- SHOW ENGINE INNODB STATUS để quan sát buffer pool, I/O và hoạt động InnoDB.
- EXPLAIN ANALYZE để xem số hàng thực tế và thời gian từng iterator.
- Thống kê file I/O và buffer pool để xác định đọc vật lý.

Không phải mọi index có nhiều trang đều bị phân mảnh. Một index lớn có thể đơn giản vì bảng có nhiều hàng hoặc khóa rộng.

### 7.3. ANALYZE TABLE và OPTIMIZE TABLE

ANALYZE TABLE cập nhật thống kê optimizer; nó không đồng nghĩa rebuild index để compact.

OPTIMIZE TABLE với InnoDB thường thực hiện tái tổ chức/rebuild bảng theo khả năng của phiên bản và cấu hình. Vì clustered index chứa dữ liệu hàng, thao tác này có thể làm lại cả cấu trúc bảng và secondary index, tốn I/O, dung lượng tạm, log và thời gian. Khả năng online và mức locking cần kiểm tra trên đúng phiên bản.

Ví dụ:

~~~sql
ANALYZE TABLE orders;
OPTIMIZE TABLE orders;
~~~

Không chạy OPTIMIZE TABLE chỉ vì index lớn. Trước hết xác định có bloat hoặc phân bố trang gây vấn đề hay không, đồng thời đánh giá dung lượng trống và ảnh hưởng tới workload ghi.

## 8. Oracle Database: kiểm tra cấu trúc B-tree index

Oracle có thể thu thập thống kê cấu trúc bằng:

~~~sql
ANALYZE INDEX ix_orders_created_at VALIDATE STRUCTURE;
~~~

Sau thao tác, view INDEX_STATS trong cùng session có thể cung cấp các trường như:

- HEIGHT: chiều cao của B-tree.
- LF_ROWS: số leaf entry.
- DEL_LF_ROWS: số leaf entry đã đánh dấu xóa theo thống kê.
- LF_BLKS: số leaf block.
- BR_BLKS: số branch block.
- PCT_USED: mức sử dụng theo thống kê cấu trúc.
- BTREE_SPACE và USED_SPACE: dung lượng cấu trúc và phần được sử dụng theo định nghĩa của Oracle.

Ví dụ:

~~~sql
SELECT
    name,
    height,
    lf_rows,
    del_lf_rows,
    lf_blks,
    br_blks,
    pct_used,
    btree_space,
    used_space
FROM index_stats;
~~~

INDEX_STATS là thông tin được tạo bởi thao tác validate structure và có phạm vi session; nó không phải view thống kê luôn được cập nhật cho mọi index. Thao tác kiểm tra có thể đọc nhiều block và gây tải, nên cần chọn thời điểm phù hợp.

### 8.1. DBMS_STATS không thay thế validate structure

DBMS_STATS thu thập thống kê optimizer như số hàng, số block, distinct values và histogram. Các thống kê này giúp optimizer ước lượng chi phí và cardinality. Chúng không trực tiếp cho biết leaf block có phân tán hoặc có bao nhiêu entry đã đánh dấu xóa.

Sau rebuild, cần quyết định có gather optimizer statistics theo chính sách của hệ thống hay không. Không gộp hai mục tiêu: cấu trúc vật lý và thống kê tối ưu hóa truy vấn.

### 8.2. COALESCE và REBUILD

- ALTER INDEX ... COALESCE hợp nhất các leaf block có thể gộp và tái sử dụng không gian theo cơ chế Oracle.
- ALTER INDEX ... REBUILD tạo lại index, có thể tổ chức lại cấu trúc và compact hơn; tùy chọn ONLINE có giới hạn và chi phí riêng.

Ví dụ:

~~~sql
ALTER INDEX ix_orders_created_at COALESCE;
~~~

~~~sql
ALTER INDEX ix_orders_created_at REBUILD ONLINE;
~~~

COALESCE và REBUILD không có cùng phạm vi tác động. Chọn dựa trên số leaf entry đã xóa, mức sử dụng block, kích thước, workload và khả năng khóa/online của phiên bản.

## 9. So sánh cách đo giữa các hệ quản trị

| Hệ quản trị | Nguồn đo thường dùng | Metric đáng chú ý | Giới hạn quan trọng |
|---|---|---|---|
| SQL Server | sys.dm_db_index_physical_stats | avg_fragmentation_in_percent, avg_page_space_used_in_percent, page_count | Diễn giải chủ yếu cho rowstore B-tree; chọn LIMITED/SAMPLED/DETAILED theo chi phí |
| PostgreSQL | pgstattuple/pgstatindex; pg_stat_user_indexes | avg_leaf_density, leaf_fragmentation, leaf_pages, idx_scan | View usage không đo fragmentation; pgstatindex phải đọc index |
| MySQL InnoDB | mysql.innodb_index_stats, Performance Schema | size, n_leaf_pages, usage và I/O theo index | Không có một fragmentation percentage phổ quát tương đương SQL Server |
| Oracle | ANALYZE INDEX VALIDATE STRUCTURE, INDEX_STATS | HEIGHT, LF_ROWS, DEL_LF_ROWS, LF_BLKS, PCT_USED | INDEX_STATS gắn với session và thao tác validate; DBMS_STATS là optimizer statistics |

Không so sánh trực tiếp phần trăm giữa các engine. Ngay cả khi hai metric cùng mang tên fragmentation, cách định nghĩa trang, cấp index, phạm vi đo và thời điểm cập nhật có thể khác nhau.

## 10. Khi nào nên bảo trì chỉ mục?

Quyết định nên dựa trên nhiều điều kiện đồng thời:

1. Index đủ lớn để chi phí đọc hoặc dung lượng có ý nghĩa.
2. Truy vấn quan trọng thực sự sử dụng index đó.
3. Query plan và số liệu runtime cho thấy index scan/range scan chịu chi phí đáng kể.
4. Page density thấp, bloat hoặc phân mảnh được xác nhận bằng công cụ phù hợp của engine.
5. Physical reads, logical reads, cache pressure hoặc latency có liên hệ hợp lý với cấu trúc index.
6. Lợi ích dự kiến lớn hơn chi phí rebuild/reorganize và rủi ro vận hành.

### 10.1. Không bảo trì chỉ vì tỷ lệ cao

Một index nhỏ có tỷ lệ fragmentation 80% nhưng chỉ vài chục page có thể không đáng làm gì. Một index rất lớn, phục vụ báo cáo range scan liên tục, có density thấp và physical reads cao có thể cần điều tra.

### 10.2. Không rebuild index ít được dùng một cách tự động

Index ít được dùng có thể vẫn bảo vệ UNIQUE hoặc hỗ trợ FOREIGN KEY. Trước khi bỏ index, phải kiểm tra constraint phụ thuộc, workload theo mùa, báo cáo ít chạy và khoảng thời gian thống kê đã thu thập.

### 10.3. Ưu tiên đúng index

Nếu một bảng có 30 index, không nhất thiết tất cả đều cần bảo trì. Chọn ứng viên theo kích thước, mức độ sử dụng, chi phí I/O và tầm quan trọng của truy vấn. Bảo trì có mục tiêu giúp giảm tải và dễ xác định hiệu quả hơn.

## 11. Chi phí và rủi ro của REBUILD/REORGANIZE

Rebuild hoặc reorganize có thể cần:

- Đọc và ghi lượng lớn page.
- CPU để sắp xếp và tạo lại cấu trúc.
- Transaction log, WAL hoặc redo log.
- Dung lượng tạm hoặc dung lượng song song cho index cũ và mới.
- Khóa hoặc metadata lock ở một số giai đoạn.
- I/O cạnh tranh với truy vấn production.
- Cập nhật statistics và làm thay đổi execution plan.
- Tăng replication lag hoặc thời gian apply log ở replica.

Online không có nghĩa không tốn tài nguyên hoặc không có blocking. Một thao tác online vẫn có thể dùng nhiều I/O, log và bộ nhớ, đồng thời cần khóa ngắn ở đầu/cuối hoặc khi đồng bộ thay đổi.

### 11.1. Kiểm tra dung lượng trước khi rebuild

Đảm bảo có đủ:

- Dung lượng cho index mới hoặc bản sao tạm.
- Dung lượng transaction log/WAL/redo.
- Dung lượng temp/work area nếu engine cần sort.
- Khoảng trống để hệ thống tiếp tục ghi trong thời gian bảo trì.

Thiếu dung lượng giữa chừng có thể làm thao tác thất bại, tạo thêm áp lực dọn dẹp hoặc ảnh hưởng tới toàn database.

### 11.2. Chọn thời điểm và phạm vi

Ưu tiên cửa sổ tải thấp, chạy từng index hoặc từng nhóm nhỏ, đặt giới hạn concurrency và theo dõi log, I/O, latency. Với bảng partition, bảo trì partition có vấn đề thay vì toàn bộ bảng nếu engine hỗ trợ.

Không chạy nhiều job rebuild lớn cùng lúc trên cùng storage nếu chúng tranh chấp I/O. Cần tính cả backup, replication, vacuum, checkpoint và batch job đang chạy.

## 12. Fill factor và page density: cân bằng đọc với ghi

Fill factor thấp hơn có thể để chỗ cho insert/update trong page, giảm page split ở một số workload. Đổi lại, index có nhiều page hơn, tăng kích thước và số trang cần đọc.

Fill factor cao giúp index compact, có thể tốt cho đọc và cache, nhưng page nhanh đầy khi insert ngẫu nhiên. Khi đó split có thể tăng và tạo thêm ghi.

Ví dụ chiến lược:

| Workload | Hướng thử nghiệm |
|---|---|
| Index hầu như chỉ đọc | Density cao, giảm page count nếu không gây split |
| Insert tăng dần vào cuối khóa | Đo contention ở trang cuối và split; không tự động giảm fill factor |
| Insert ngẫu nhiên trên khóa | Thử chừa khoảng trống, đo split và index size |
| UPDATE làm entry lớn hơn | Đo split sau update và chọn fill factor theo phân bố |
| Index ít dùng, dữ liệu lịch sử | Xem xét partitioning hoặc vòng đời dữ liệu trước khi rebuild định kỳ |

Không chọn một fill factor chung cho mọi index. Mỗi index có phân bố khóa, tần suất ghi và truy vấn khác nhau.

## 13. Quy trình đo trước và sau bảo trì

### 13.1. Trước khi thay đổi

1. Xác định index và query cần cải thiện.
2. Lưu execution plan và tham số đại diện.
3. Đo p50/p95/p99, logical reads, physical reads, CPU và elapsed time.
4. Thu thập page count, density, fragmentation hoặc bloat bằng công cụ đúng engine.
5. Kiểm tra index usage và tần suất ghi.
6. Kiểm tra thời gian tải, dung lượng trống, log và replication.
7. Ghi lại fill factor, partition và tùy chọn index hiện tại.

### 13.2. Thực hiện bảo trì

1. Chọn REORGANIZE, REBUILD, COALESCE, REINDEX hoặc không thực hiện.
2. Chạy trong cửa sổ và concurrency phù hợp.
3. Theo dõi tiến độ, I/O, log, blocking và dung lượng.
4. Dừng hoặc hoãn nếu latency production, storage queue hoặc replication lag vượt ngưỡng.
5. Xác nhận thao tác hoàn tất và index ở trạng thái hợp lệ.

### 13.3. Sau khi thay đổi

1. Đo lại cấu trúc bằng cùng công cụ và cùng chế độ.
2. Chạy lại query với cùng tham số và dữ liệu tương đương.
3. So sánh execution plan, page reads, CPU, elapsed time và p95/p99.
4. Kiểm tra statistics có cần cập nhật theo chính sách không.
5. Quan sát workload ghi để phát hiện page split hoặc write amplification tăng.
6. Theo dõi replica và các truy vấn khác dùng chung index.
7. Ghi nhận lợi ích thực tế và quyết định lịch bảo trì tiếp theo.

Một lần đo sau rebuild có thể cho kết quả tốt do cache vừa được làm nóng hoặc statistics vừa thay đổi. Nếu muốn xác định nguyên nhân, cần so sánh trong điều kiện cache và tải tương đương, hoặc chạy nhiều vòng đo.

## 14. Ví dụ quyết định bảo trì cho index đơn hàng

Giả sử bảng orders có 80 triệu hàng và index trên created_at. Báo cáo hằng ngày dùng range scan theo khoảng thời gian. SQL Server báo index có page_count lớn, fragmentation logic đáng kể và page density thấp. Actual plan cho thấy truy vấn đọc nhiều page, physical reads tăng và p95 cao hơn baseline.

Quy trình hợp lý:

1. Xác nhận báo cáo thực sự dùng index này.
2. Kiểm tra page_count và chỉ tập trung leaf level.
3. Đối chiếu logical fragmentation với page density.
4. Đo logical/physical reads và storage latency của truy vấn.
5. Kiểm tra insert pattern và fill factor hiện tại.
6. Ước lượng log, dung lượng và thời gian rebuild.
7. Thử reorganize hoặc rebuild trong môi trường đại diện.
8. Đo lại query, index size, page density và write workload.

Nếu rebuild làm page density tăng nhưng truy vấn không giảm reads hoặc latency, có thể phân mảnh không phải nút thắt chính. Cần kiểm tra thêm predicate, selectivity, partition pruning, memory grant, storage latency hoặc plan regression.

Nếu sau rebuild insert page split tăng mạnh, fill factor có thể quá cao cho workload ghi. Khi đó cần thử lại mức fill factor phù hợp thay vì chạy rebuild lặp đi lặp lại.

## 15. Những nhầm lẫn thường gặp

- **Coi fragmentation percentage là tỷ lệ dữ liệu hỏng:** đây là chỉ số cấu trúc, không phải lỗi toàn vẹn.
- **Dùng ngưỡng 10% hoặc 30% cho mọi engine:** định nghĩa và tác động không giống nhau.
- **Bỏ qua page count:** tỷ lệ cao trên index rất nhỏ thường không đáng quan tâm.
- **Chỉ xem fragmentation mà không xem density:** page density thấp có thể quan trọng ngay cả khi logical fragmentation thấp.
- **Nhầm bloat với phân mảnh logic:** hai hiện tượng liên quan nhưng khác nhau.
- **Dùng usage statistics làm fragmentation statistics:** số lần scan không cho biết thứ tự trang.
- **Cho rằng ANALYZE TABLE hoặc DBMS_STATS sẽ compact index:** cập nhật optimizer statistics không đồng nghĩa rebuild cấu trúc.
- **Cho rằng VACUUM thông thường tương đương REINDEX trong PostgreSQL:** cleanup dead tuple và rebuild index là các công việc khác nhau.
- **Coi MySQL n_leaf_pages là phần trăm fragmentation:** đây là thống kê số trang, không phải metric fragmentation.
- **Coi online rebuild là miễn phí:** vẫn có thể tốn I/O, log, temp space và khóa ở một số giai đoạn.
- **Rebuild mọi index theo lịch cố định:** gây write amplification và tải bảo trì không cần thiết.
- **Không đo sau bảo trì:** không biết thao tác có cải thiện workload hay không.
- **Không kiểm tra workload ghi:** density cao hơn có thể làm page split tăng.
- **Không xem replication lag và log growth:** bảo trì có thể ảnh hưởng cả hệ thống phân tán.

## 16. Checklist đo và bảo trì phân mảnh chỉ mục

- [ ] Đã xác định loại index và hệ quản trị đang dùng.
- [ ] Đã phân biệt logical fragmentation, page density, bloat và table fragmentation.
- [ ] Đã xác định query quan trọng thực sự sử dụng index.
- [ ] Đã đo page count hoặc leaf page count.
- [ ] Đã dùng đúng công cụ và hiểu định nghĩa metric theo engine.
- [ ] Đã chọn chế độ đo phù hợp để tránh scan thống kê quá nặng.
- [ ] Đã xem usage statistics, physical/logical reads và query latency.
- [ ] Đã kiểm tra fill factor và insert/update pattern.
- [ ] Đã đánh giá lợi ích dự kiến so với I/O, CPU, log, temp space và blocking.
- [ ] Đã kiểm tra dung lượng trống và replication trước khi bảo trì.
- [ ] Đã chọn thao tác phù hợp: reorganize, rebuild, coalesce, reindex hoặc không làm gì.
- [ ] Đã bảo trì theo phạm vi nhỏ và có ngưỡng dừng.
- [ ] Đã đo lại cấu trúc và truy vấn trong điều kiện tương đương.
- [ ] Đã kiểm tra statistics và execution plan sau thay đổi.
- [ ] Đã theo dõi workload ghi, page split, cache và replica sau bảo trì.
- [ ] Đã ghi nhận kết quả để điều chỉnh chính sách bảo trì.

Phân mảnh chỉ mục là một đặc tính cấu trúc cần được diễn giải theo hệ quản trị và workload. Hãy đo đúng metric, xem cùng page count, density, mức sử dụng và chi phí truy vấn; sau đó mới quyết định bảo trì. Một REBUILD chỉ có giá trị khi cải thiện được truy cập dữ liệu hoặc dung lượng theo mục tiêu đo được, đồng thời không gây chi phí ghi, log, I/O và gián đoạn lớn hơn lợi ích nhận được.

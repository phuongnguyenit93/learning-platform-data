# Bảo trì phân vùng và kiểm soát kích thước bảng hoặc chỉ mục

Bảng và chỉ mục tăng trưởng theo thời gian. Khi dữ liệu cũ vẫn nằm trong vùng phục vụ truy vấn nóng, các thao tác đọc, backup, vacuum, thống kê và rebuild index có thể phải xử lý ngày càng nhiều dữ liệu. Phân vùng giúp chia bảng thành các phần có ranh giới rõ ràng; quy trình bảo trì tốt giúp tạo trước phần dữ liệu mới, cập nhật thống kê, xử lý phân vùng cũ, lưu trữ và loại bỏ dữ liệu hết hạn theo chính sách.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Bảo trì phân vùng và kiểm soát kích thước bảng/chỉ mục vì vậy phải giải quyết đồng thời ba mục tiêu: giữ phạm vi truy cập hợp lý, duy trì chất lượng thống kê và index, đồng thời kiểm soát dung lượng cùng chi phí vận hành. Việc tạo nhiều phân vùng hoặc rebuild mọi index theo lịch không tự động làm hệ thống nhanh hơn.

Bài học này trình bày cách đo kích thước từng phân vùng và index, lập lịch vòng đời dữ liệu, bảo trì thống kê và dead tuples, xử lý index phình to hoặc ít được sử dụng, vận hành retention an toàn và kiểm chứng tác động trên PostgreSQL, MySQL InnoDB và SQL Server.

## 1. Mục tiêu của bảo trì phân vùng và kích thước

Bảo trì dữ liệu là tập hợp thao tác có kế hoạch để giữ cấu trúc lưu trữ phù hợp với workload và chính sách dữ liệu. Các mục tiêu thường gặp:

- Giới hạn lượng dữ liệu nóng mà truy vấn thường xuyên phải xem xét.
- Giữ thống kê đủ mới để optimizer ước lượng cardinality tốt.
- Thu hồi hoặc tái sử dụng không gian sau UPDATE/DELETE theo cơ chế của engine.
- Kiểm soát kích thước heap/table và index.
- Loại bỏ dữ liệu hết hạn theo retention.
- Giảm thời gian backup, restore, analyze và các thao tác bảo trì.
- Duy trì số lượng phân vùng và index ở mức có thể vận hành.
- Tránh maintenance job cạnh tranh với giao dịch trực tuyến.

Cần phân biệt một số khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Logical data size | Dung lượng dữ liệu nghiệp vụ đang lưu |
| Allocated size | Dung lượng file/segment đã được cấp phát |
| Free space inside object | Khoảng trống có thể tái sử dụng bên trong table/index |
| Bloat/fragmentation | Không gian dư thừa hoặc cấu trúc phân tán làm tăng số trang cần đọc |
| Index size | Dung lượng các cấu trúc index |
| Retained history | Dữ liệu lịch sử phải giữ theo chính sách |
| Backup footprint | Dung lượng bản backup và log archive theo retention |

Xóa một số dòng không nhất thiết làm file trên filesystem nhỏ lại ngay. Một số engine giữ lại trang để tái sử dụng cho lần ghi sau. Vì vậy, cần xác định mục tiêu là giảm số trang truy vấn phải đọc, tái sử dụng không gian bên trong database hay trả dung lượng về hệ điều hành.

## 2. Phân vùng giúp bảo trì theo đơn vị dữ liệu

Phân vùng chia một bảng logic thành các phần vật lý theo khóa và ranh giới. Ví dụ bảng events chia theo tháng:

~~~text
events
  |
  +-- events_2026_01
  +-- events_2026_02
  +-- events_2026_03
  +-- events_2026_04
  +-- events_2026_05
  +-- events_2026_06
~~~

Mỗi phân vùng có thể được theo dõi, phân tích thống kê, bảo trì index, lưu trữ hoặc loại bỏ theo vòng đời riêng, tùy khả năng của hệ quản trị.

### Phân vùng theo thời gian

RANGE partitioning theo ngày/tháng thường phù hợp khi:

- Truy vấn chủ yếu lọc theo thời gian.
- Dữ liệu được ghi liên tục theo thời điểm.
- Có chính sách giữ dữ liệu nóng trong một khoảng thời gian.
- Dữ liệu cũ có thể archive hoặc xóa theo từng khoảng.

Ví dụ, hệ thống giữ 13 tháng dữ liệu trực tuyến. Khi sang tháng mới, quy trình tạo phân vùng tương lai và xác định phân vùng cũ nhất đủ điều kiện archive.

### Phân vùng theo tenant hoặc nhóm nghiệp vụ

LIST hoặc HASH có thể phù hợp nếu truy vấn thường lọc theo tenant/nhóm và phân bố dữ liệu hợp lý. Tuy nhiên, bảo trì theo thời gian khó hơn nếu partition key không phản ánh retention. Một tenant lớn có thể tạo phân vùng nóng hoặc mất cân bằng.

### Ranh giới phải không chồng lấn và bao phủ đúng miền dữ liệu

Với RANGE, cần thống nhất cận dưới/cận trên, múi giờ và cách xử lý giá trị ở ranh giới. Nhiều hệ thống dùng khoảng nửa mở: từ thời điểm bắt đầu bao gồm đến thời điểm kết thúc không bao gồm. Cách này tránh một dòng thuộc hai khoảng liên tiếp.

Phân vùng mặc định (default partition) có thể nhận giá trị chưa khớp ranh giới cụ thể nếu engine hỗ trợ. Cần giám sát nó; nếu dữ liệu ngoài miền tích tụ, việc tạo phân vùng đúng sau này có thể cần chuyển dữ liệu hoặc xác minh constraint.

## 3. Đo kích thước bảng và từng phân vùng trước khi bảo trì

Không nên quyết định archive, drop, vacuum hoặc rebuild index chỉ dựa trên tuổi phân vùng. Hãy thu thập số liệu trước.

Các thông tin cần đo:

- Số dòng ước lượng và số dòng thực tế nếu có thể lấy với chi phí phù hợp.
- Kích thước heap/table.
- Tổng kích thước index và từng index lớn.
- Tốc độ tăng theo ngày/tuần/tháng.
- Dead tuples hoặc phiên bản dữ liệu cũ.
- Số lượt đọc/ghi và truy vấn quan trọng trên phân vùng.
- Thống kê được cập nhật lần cuối khi nào.
- Backup footprint và thời gian restore dự kiến.

### PostgreSQL: xem kích thước các phân vùng

Hàm pg_partition_tree có trên các phiên bản PostgreSQL hỗ trợ partitioning hiện đại. Ví dụ:

~~~sql
SELECT
    relid::regclass AS partition_name,
    level,
    pg_size_pretty(pg_relation_size(relid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(relid)) AS index_size,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_partition_tree('public.events')
WHERE isleaf
ORDER BY relid::regclass::text;
~~~

pg_relation_size đo kích thước relation chính; pg_indexes_size đo tổng index gắn với relation; pg_total_relation_size bao gồm relation và các đối tượng phụ thuộc như index và TOAST theo định nghĩa của PostgreSQL. Đây là số liệu dung lượng, không phải phép đo trực tiếp bloat hay số dòng đang sử dụng.

Có thể xem thống kê hoạt động của một bảng hoặc phân vùng:

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE relname LIKE 'events_%'
ORDER BY relname;
~~~

n_live_tup và n_dead_tup là ước lượng thống kê, không phải phép đếm chính xác. Cần xem delta theo thời gian và kết hợp với kích thước, workload, vacuum progress và execution plan.

### Đo kích thước index

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_index
WHERE indrelid = 'public.events_2026_04'::regclass
ORDER BY pg_relation_size(indexrelid) DESC;
~~~

Truy vấn này giúp tìm index chiếm nhiều dung lượng trên một phân vùng cụ thể. Kích thước lớn chưa đủ để kết luận index không cần thiết; index có thể phục vụ truy vấn quan trọng hoặc constraint.

### Lấy mẫu theo thời gian

Các view thống kê thường chứa counter tích lũy hoặc ước lượng. Hãy chụp nhiều mẫu theo khoảng thời gian cố định để tính tốc độ tăng, dead tuple generation, index usage và hoạt động vacuum/analyze. Ghi nhận thời điểm reset statistics để tránh so sánh hai khoảng không tương đương.

## 4. Lập lịch vòng đời phân vùng

Một quy trình vòng đời thường gồm:

1. Tạo phân vùng tương lai trước khi ứng dụng cần ghi.
2. Kiểm tra ranh giới, quyền, index và constraint.
3. Theo dõi kích thước và tốc độ tăng của phân vùng đang hoạt động.
4. Cập nhật thống kê sau nạp dữ liệu lớn hoặc khi phân bố thay đổi.
5. Chuyển phân vùng hết thời hạn nóng sang trạng thái chỉ đọc hoặc archive.
6. Xác minh bản archive và các phụ thuộc.
7. Detach, switch hoặc drop theo khả năng của engine.
8. Cập nhật metadata, monitoring và retention checkpoint.
9. Ghi nhận dung lượng đã giải phóng hoặc được tái sử dụng.

### Tạo trước phân vùng tương lai

Đừng đợi INSERT đầu tiên của tháng mới mới tạo phân vùng. Một job định kỳ nên tạo trước một hoặc nhiều phân vùng theo lịch. Job phải có tính idempotent: chạy lại không tạo trùng hoặc thay đổi ranh giới đã tồn tại.

Cần cảnh báo khi thiếu phân vùng tương lai, khi default partition bắt đầu nhận dòng hoặc khi phân vùng mới không có index/constraint cần thiết.

### Xử lý dữ liệu đến trễ

Dữ liệu có thể đến muộn do queue, retry hoặc backfill. Quy trình phải xác định phân vùng đích dựa trên event time hay ingestion time. Nếu partition theo event time, dữ liệu cũ có thể ghi vào phân vùng lịch sử. Nếu phân vùng cũ đã archive hoặc detach, cần quy trình nạp lại rõ ràng.

Không đổi partition key hoặc ranh giới chỉ để giải quyết một đợt backfill riêng lẻ mà chưa xem tác động lên toàn bộ workload.

## 5. Retention: archive và loại bỏ dữ liệu hết hạn

Retention xác định dữ liệu nào phải giữ trực tuyến, dữ liệu nào được archive và dữ liệu nào được phép xóa. Đây là quyết định nghiệp vụ, pháp lý và vận hành; nhóm database cần thực thi chính xác chính sách đã được xác nhận.

### Vì sao drop partition có thể hiệu quả hơn DELETE hàng triệu dòng?

DELETE thường tạo công việc theo từng dòng hoặc từng page, ghi log, cập nhật index và để lại phiên bản dữ liệu cũ cần vacuum/cleanup. Drop hoặc detach một phân vùng có thể loại bỏ một đơn vị lưu trữ lớn với ít công việc hơn, tùy engine và cấu trúc phụ thuộc.

Tuy nhiên, thao tác DDL vẫn có thể cần lock, ghi metadata, ảnh hưởng replication và backup. Không được coi drop partition là thao tác không rủi ro hoặc luôn tức thời.

### Quy trình archive an toàn

Trước khi loại bỏ phân vùng cũ:

- Xác minh khoảng thời gian và số liệu của phân vùng.
- Xác minh retention policy, legal hold và yêu cầu kiểm toán.
- Kiểm tra foreign key, view, trigger, job và ứng dụng tham chiếu.
- Tạo archive hoặc backup theo quy trình.
- Kiểm tra checksum, số dòng hoặc mẫu truy vấn phục hồi.
- Xác nhận archive có thể truy cập trong RTO/RPO.
- Ghi lại người phê duyệt, thời điểm và partition identifier.
- Chỉ sau đó mới thực hiện detach/drop theo runbook.

### Không nhầm archive với backup

Archive là dữ liệu lịch sử được tổ chức để truy xuất theo chính sách. Backup là bản sao phục vụ khôi phục khi mất dữ liệu hoặc hỏng hệ thống. Một bản archive đơn lẻ không tự động thay thế backup, và một backup không tự động đáp ứng nhu cầu truy vấn dữ liệu lịch sử.

## 6. PostgreSQL: detach, archive và drop partition

PostgreSQL cho phép detach một partition khỏi bảng cha. Sau khi detach, partition trở thành bảng độc lập và có thể được dump, di chuyển hoặc lưu trữ theo quy trình.

Ví dụ minh họa:

~~~sql
ALTER TABLE public.events
DETACH PARTITION public.events_2025_01;
~~~

Sau khi xác minh partition đã được detach thành công, có thể archive bảng độc lập bằng công cụ backup phù hợp. Chỉ drop bảng khi bản archive đã được xác minh và mọi phụ thuộc đã được xử lý:

~~~sql
DROP TABLE public.events_2025_01;
~~~

Cú pháp detach có tùy chọn CONCURRENTLY trên các phiên bản PostgreSQL hỗ trợ. Cách này dùng quy trình nhiều pha và có giới hạn riêng, bao gồm điều kiện về transaction block và cấu trúc partition. Hãy kiểm tra tài liệu phiên bản đang chạy trước khi chọn chế độ detach.

### Khóa và thời gian DDL

Detach/drop có thể cần khóa trên bảng cha hoặc partition. Một thao tác chờ lock lâu có thể gây hàng đợi DDL/DML phía sau. Hãy:

- Chạy trong cửa sổ bảo trì phù hợp.
- Đặt lock timeout hợp lý nếu runbook yêu cầu.
- Kiểm tra session đang giữ lock.
- Thực hiện từng partition để giới hạn blast radius.
- Theo dõi replication và catalog sau thao tác.

### Attach partition đã archive hoặc nạp lại

Khi gắn lại một bảng thành partition, cấu trúc cột, kiểu dữ liệu, constraint và ranh giới phải tương thích. PostgreSQL có thể phải xác minh các dòng trong bảng có thỏa partition bound hay không. Constraint CHECK hợp lệ có thể giúp giảm công việc xác minh trong các trường hợp được hỗ trợ.

Không attach một bảng staging chỉ dựa trên tên hoặc giả định dữ liệu đúng khoảng. Hãy kiểm tra ranh giới và số dòng trước khi gắn.

## 7. PostgreSQL: VACUUM, ANALYZE và bảo trì phân vùng

PostgreSQL dùng MVCC. UPDATE/DELETE thường tạo row version mới hoặc đánh dấu version cũ không còn phù hợp cho transaction mới. VACUUM giúp thu hồi dead tuples để không gian có thể tái sử dụng và duy trì visibility map/freeze state theo cơ chế engine.

### VACUUM không đồng nghĩa thu nhỏ file

VACUUM thông thường chủ yếu làm không gian trong relation có thể tái sử dụng; nó không nhất thiết trả dung lượng về filesystem. Đây thường là hành vi mong muốn vì dữ liệu có thể tăng lại và database tái sử dụng trang trống.

VACUUM FULL viết lại relation để thu hồi không gian ở mức file, nhưng cần khóa mạnh và dung lượng tạm bổ sung. Nó có thể chặn truy cập trong thời gian chạy. Không dùng VACUUM FULL theo lịch như biện pháp định kỳ cho mọi bảng.

### Vacuum từng phân vùng

Các phân vùng con là relation lưu dữ liệu thực tế, vì vậy cần quan sát và bảo trì chúng theo mức độ ghi/xóa. Ví dụ:

~~~sql
VACUUM (ANALYZE) public.events_2026_04;
~~~

Nếu phân vùng nhận nhiều UPDATE/DELETE, cần theo dõi dead tuples, autovacuum activity, transaction age và vacuum lag. Một phân vùng lịch sử gần như chỉ đọc có thể cần lịch bảo trì khác với phân vùng hiện tại có tần suất ghi cao.

### Thống kê bảng cha và phân vùng con

Optimizer cần thống kê phù hợp để ước lượng số dòng. Có thể chạy:

~~~sql
ANALYZE public.events;
ANALYZE public.events_2026_04;
~~~

Với partitioned table, PostgreSQL không tự động thu thập thống kê trên bảng cha bằng autovacuum như đối với relation có dữ liệu vật lý; khi cần thống kê tổng hợp ở parent, cần lập lịch ANALYZE thủ công theo phiên bản và workload. Các partition con vẫn có thể được autovacuum/analyze riêng theo hoạt động của chúng.

Sau bulk load, detach/attach hoặc thay đổi phân bố lớn, hãy cập nhật thống kê trước khi đánh giá execution plan.

### Autovacuum và phân vùng nóng

Autovacuum trigger dựa trên ngưỡng và tỷ lệ thay đổi. Một phân vùng nhỏ và một phân vùng rất lớn có thể cần cấu hình khác nhau. Nếu một partition nhận update liên tục, hãy xem autovacuum thresholds, scale factors, vacuum cost và khả năng chạy song song nhiều maintenance worker.

Không tắt autovacuum trên bảng nóng chỉ để tránh I/O. Cần xác định nguyên nhân nó chạy quá thường xuyên hoặc không theo kịp, sau đó điều chỉnh có đo lường.

## 8. Kiểm soát kích thước index

Index tăng theo dữ liệu và số cột được lưu. Một index lớn có thể chiếm cache, tăng backup footprint và làm INSERT/UPDATE/DELETE tốn thêm công việc.

### Đánh giá index theo workload

Với mỗi index, cần xem:

- Truy vấn nào sử dụng index?
- Index scan/seek frequency và số dòng đọc.
- Index có phục vụ constraint hoặc foreign key không?
- Index có trùng tiền tố hoặc trùng chức năng với index khác không?
- Chi phí ghi và dung lượng index là bao nhiêu?
- Index có thể thay bằng partial/filtered index hoặc index nhỏ hơn không?
- Dữ liệu phân vùng có đủ chọn lọc để index mang lại lợi ích không?

Index ít được dùng trong một khoảng thời gian không đồng nghĩa có thể xóa ngay. Có thể đó là index phục vụ báo cáo cuối tháng, truy vấn khẩn cấp, constraint hoặc workload theo mùa.

### Tránh tạo index trùng lặp

Hai index có cùng leading columns và khác biệt nhỏ có thể tạo chi phí ghi và dung lượng không cần thiết. Nhưng index có thêm INCLUDE column, sort direction, predicate hoặc collation khác có thể phục vụ truy vấn riêng.

Hãy so sánh định nghĩa index đầy đủ và execution plan của các truy vấn quan trọng trước khi hợp nhất hoặc loại bỏ.

### Partial/filtered index

Nếu chỉ một phần dữ liệu thường được truy cập, partial index (PostgreSQL) hoặc filtered index (SQL Server) có thể giảm kích thước so với index toàn bảng. Ví dụ index chỉ cho đơn hàng đang mở:

~~~sql
CREATE INDEX idx_orders_open_tenant_created
ON orders (tenant_id, created_at DESC)
WHERE status = 'OPEN';
~~~

Ví dụ trên là cú pháp PostgreSQL. Truy vấn chỉ tận dụng index khi điều kiện của nó tương thích với predicate. MySQL có các lựa chọn index khác và không hỗ trợ partial index theo cú pháp này.

### Index theo phân vùng

Một số hệ quản trị tạo local index tương ứng trên từng partition; một số hỗ trợ global index hoặc mô hình khác. Cần biết rõ index có được tạo tự động khi tạo partition mới hay khi attach partition hay không.

Phân vùng mới thiếu index cần thiết có thể khiến truy vấn chậm đột ngột. Checklist tạo partition phải bao gồm index, constraint, quyền và thống kê.

## 9. Rebuild, reorganize và bloat

Bảo trì index có thể gồm reorganize, rebuild hoặc reindex. Những thao tác này khác nhau theo engine và có chi phí về I/O, CPU, log, lock và dung lượng tạm.

### Khi nào cần xem xét?

- Index có bloat/fragmentation đáng kể theo chỉ số phù hợp của engine.
- Số trang đọc tăng bất thường so với số dòng trả về.
- Index size tăng nhanh mà số dòng không tăng tương ứng.
- Index page density thấp hoặc nhiều page split theo chỉ số engine.
- Có thay đổi lớn về dữ liệu hoặc cấu trúc index.
- Benchmark xác nhận rebuild/reorganize cải thiện workload.

Không dùng một ngưỡng fragmentation cố định cho mọi index. B-tree có pattern insert tuần tự, random key và mức update khác nhau. Mức fragmentation ảnh hưởng khác nhau tùy storage, cache, truy vấn và engine.

### PostgreSQL

REINDEX tạo lại index. PostgreSQL hỗ trợ REINDEX ... CONCURRENTLY trên các phiên bản phù hợp, giúp giảm thời gian chặn ghi so với thao tác thông thường nhưng cần thêm I/O, dung lượng tạm và thời gian. Có giới hạn riêng và không chạy được trong transaction block khi dùng CONCURRENTLY.

Không chạy đồng loạt rebuild tất cả index trên giờ cao điểm. Hãy chọn index có bằng chứng về bloat hoặc vấn đề truy cập và đo lại sau khi hoàn tất.

### MySQL InnoDB

InnoDB tổ chức bảng theo clustered index và secondary indexes. UPDATE/DELETE, page split và purge ảnh hưởng đến dung lượng cùng cấu trúc. OPTIMIZE TABLE có thể tái tổ chức bảng hoặc rebuild tùy loại table/engine/version, và có thể tạo I/O lớn cùng yêu cầu dung lượng tạm.

Kiểm tra online DDL support, metadata lock, thời gian copy/rebuild và tác động replication trước khi chạy. Không giả định OPTIMIZE luôn là thao tác online hoặc rẻ.

### SQL Server

SQL Server có thể dùng ALTER INDEX ... REORGANIZE hoặc REBUILD. REORGANIZE thường thực hiện theo từng phần và có đặc tính lock khác REBUILD; REBUILD tạo lại cấu trúc index, có thể cần thêm dung lượng và log. Online rebuild phụ thuộc edition, phiên bản, loại index và giới hạn cụ thể.

Hãy xem page density, fragmentation, index usage, waits và workload. Fragmentation thấp không bảo đảm truy vấn nhanh nếu vấn đề thực sự là cardinality, I/O hoặc query shape.

## 10. Bảo trì theo phân vùng thay vì toàn bảng

Một lợi ích quan trọng của partitioning là giới hạn phạm vi maintenance.

Ví dụ, bảng events có 36 phân vùng tháng. Chỉ phân vùng tháng hiện tại nhận ghi; 35 phân vùng lịch sử gần như chỉ đọc. Có thể:

- Vacuum/analyze thường xuyên hơn trên phân vùng đang ghi.
- Chạy thống kê định kỳ cho phân vùng mới sau bulk load.
- Rebuild index chỉ trên partition có bằng chứng cần thiết.
- Archive/drop partition cũ khi retention hết hạn.
- Giữ phân vùng lịch sử trên storage tier rẻ hơn nếu engine hỗ trợ.
- Tránh bảo trì tất cả partition theo cùng lịch nếu đặc điểm hoạt động khác nhau.

Tuy nhiên, truy vấn xuyên nhiều phân vùng vẫn có thể cần thống kê và index phù hợp ở tất cả phân vùng liên quan. Bảo trì từng phần không có nghĩa bỏ qua tính nhất quán của toàn bộ bảng logic.

## 11. MySQL: quản lý partition và kích thước

MySQL partitioning có các thao tác DDL riêng. Cần xác minh hỗ trợ của engine và phiên bản, đặc biệt với foreign key, unique key và loại partition.

### DROP PARTITION và TRUNCATE PARTITION

Với partition đã hết retention, MySQL có thể dùng ALTER TABLE ... DROP PARTITION để loại bỏ dữ liệu trong partition đó. TRUNCATE PARTITION làm rỗng dữ liệu partition nhưng giữ cấu trúc partition. Đây là thao tác có tác động dữ liệu; phải xác minh archive và retention trước khi thực hiện.

Không dùng DROP PARTITION như một bước archive. Nó loại bỏ dữ liệu của partition khỏi bảng.

### REORGANIZE PARTITION

REORGANIZE PARTITION có thể chia hoặc gộp partition, thay đổi ranh giới và di chuyển dữ liệu giữa các phần. Đây có thể là thao tác tốn I/O và metadata lock. Hãy đo lượng dữ liệu phải di chuyển, thời gian DDL và replication lag.

### Thống kê và index

InnoDB quản lý index theo cấu trúc của bảng/partition tùy phiên bản và cách partitioning. Sau bulk load hoặc thay đổi phân bố, có thể cần cập nhật thống kê bằng ANALYZE TABLE. Kiểm tra optimizer statistics, persistent stats và execution plan trước/sau.

Theo dõi kích thước từ information_schema, data/index length và tablespace metadata; các giá trị có thể là ước lượng hoặc phản ánh cấp phát file tùy engine.

## 12. SQL Server: partition switching và bảo trì index

SQL Server hỗ trợ partition function/scheme để ánh xạ dữ liệu vào filegroup. Với bảng được thiết kế phù hợp, partition switching có thể chuyển một partition sang bảng staging hoặc archive nhanh hơn việc DELETE từng dòng.

### Sliding window

Một mô hình retention thường dùng:

1. Tạo partition cho khoảng thời gian mới.
2. Nạp dữ liệu vào partition hiện tại.
3. Chuẩn bị bảng staging có schema/index/check constraint tương thích.
4. Switch partition cũ sang staging.
5. Backup hoặc lưu trữ dữ liệu staging.
6. Truncate/drop staging sau khi xác minh retention.
7. Cập nhật partition boundary để tái sử dụng vùng.

Partition switching có yêu cầu chặt chẽ về schema, index alignment, constraint, filegroup và trạng thái dữ liệu. Không thể switch tùy ý giữa hai bảng chỉ vì chúng có các cột giống nhau.

### Index aligned và nonaligned

Index aligned có partition scheme tương thích với bảng, giúp các thao tác partition-level dễ quản lý hơn. Index nonaligned có thể làm partition switch hoặc maintenance phức tạp, vì index cần duy trì tính toàn vẹn xuyên partition.

Trước khi thiết kế sliding window, hãy quyết định từ đầu cách partition các index và kiểm tra yêu cầu của phiên bản SQL Server.

### Rebuild theo partition

SQL Server cho phép bảo trì index theo partition trong các trường hợp được hỗ trợ. Điều này hữu ích khi partition mới thường xuyên thay đổi còn partition lịch sử ổn định. Nhưng rebuild vẫn có thể tạo log, tiêu thụ I/O và cần thêm dung lượng; hãy đánh giá online/offline support.

## 13. Kiểm soát số lượng phân vùng

Partition granularity ảnh hưởng trực tiếp đến số đối tượng cần quản lý.

Nếu tạo một partition mỗi giờ trong 5 năm, số partition sẽ rất lớn. Điều này làm tăng metadata, index object, công việc lập kế hoạch, backup và monitoring.

### Phân vùng quá nhỏ

- Nhiều partition có ít dòng.
- Tăng chi phí catalog và planning.
- Mỗi partition có index và thống kê riêng.
- Tạo, attach, detach và backup phức tạp.
- Truy vấn không prune có thể xét rất nhiều partition.

### Phân vùng quá lớn

- Truy vấn khoảng nhỏ có thể phải xử lý nhiều dữ liệu bên trong một partition.
- Vacuum/analyze hoặc rebuild partition có thể kéo dài.
- Archive/drop theo retention không đủ linh hoạt.
- Index của partition có thể lớn hơn working set cache.

### Chọn kích thước theo dữ liệu và vận hành

Hãy dùng:

- Số dòng và byte tăng mỗi ngày/tuần/tháng.
- Khoảng thời gian truy vấn phổ biến.
- Thời gian lưu trữ nóng.
- Kích thước heap và index mục tiêu.
- Cửa sổ bảo trì và thời gian restore.
- Số partition tối đa nhóm vận hành có thể theo dõi.
- Khả năng của engine ở phiên bản hiện tại.

Không có một con số partition chuẩn cho mọi database. Benchmark với số lượng dự kiến và truy vấn đại diện.

## 14. Lập kế hoạch dung lượng và tăng trưởng

Capacity planning cần tính riêng data, index, log, temp, archive và backup. Đừng chỉ theo dõi kích thước bảng cha.

Một mô hình dự báo:

~~~text
Dung lượng dự kiến
  = dữ liệu mới mỗi kỳ × số kỳ retention
  + index footprint
  + phần tăng do update/bloat
  + temp và maintenance headroom
  + backup/archive theo chính sách
~~~

Đây là mô hình ước lượng. Tỷ lệ index, bloat và temp cần lấy từ dữ liệu thật của workload.

### Theo dõi tốc độ tăng

Nếu một partition tháng tăng từ 80 GB lên 110 GB trong 10 ngày, hãy dự báo khi hết tháng và kiểm tra dung lượng còn lại. Cần tính cả tốc độ tăng bất thường do backfill hoặc batch load.

### Dự phòng cho rebuild và migration

Rebuild index hoặc tạo bảng mới có thể cần thêm dung lượng trong khi object cũ vẫn tồn tại. Migration partition có thể tạm thời lưu cả staging và partition nguồn. Hãy dự phòng storage headroom trước khi bắt đầu.

### Kiểm soát file growth

Autogrowth giúp database tiếp tục hoạt động nhưng có thể gây pause hoặc nhiều lần mở rộng. Pre-size file theo tăng trưởng dự kiến và chọn growth increment hợp lý. Không đặt file quá lớn chỉ để tránh growth mà không tính backup/restore và chi phí storage.

## 15. Bảo trì thống kê sau thay đổi dữ liệu

Optimizer dựa trên thống kê để ước lượng số dòng, độ chọn lọc và phân bố giá trị. Khi một partition mới nhận bulk load hoặc dữ liệu thay đổi lệch, thống kê cũ có thể dẫn đến plan kém.

Cần xem xét ANALYZE/UPDATE STATISTICS sau:

- Bulk load hoặc backfill lớn.
- Tạo partition mới và nạp nhiều dòng.
- Archive/drop một partition lớn làm thay đổi phân bố.
- Thay đổi index hoặc schema.
- Một cột có phân bố lệch mạnh theo thời gian.
- Estimated rows lệch xa actual rows trong execution plan.

Không chạy analyze liên tục không có mục tiêu. Hãy xác định cột và bảng có thay đổi đủ lớn để cần cập nhật, sau đó đo planning/execution plan.

## 16. Kiểm soát maintenance window và cạnh tranh tài nguyên

Maintenance cũng là workload. Vacuum, analyze, index rebuild, partition switch, backup và archive đều dùng CPU, memory, I/O, log và lock.

### Lên lịch theo mức độ nóng

- Partition đang ghi: vacuum/analyze theo hoạt động và threshold.
- Partition lịch sử chỉ đọc: kiểm tra định kỳ, archive theo retention.
- Index rebuild: chạy khi có bằng chứng và có đủ headroom.
- Bulk load: lên lịch hoặc giới hạn tốc độ để tránh ảnh hưởng OLTP.
- Backup: cân nhắc replica hoặc storage path riêng, nhưng vẫn đo tác động.

### Giới hạn concurrency

Chạy đồng thời nhiều rebuild hoặc analyze có thể làm bão hòa storage. Một job bảo trì nhanh khi chạy riêng có thể làm toàn hệ thống chậm khi chạy cùng các job khác.

Dùng hàng đợi maintenance, giới hạn worker và theo dõi I/O. Đừng khởi động lại job liên tục khi job cũ đang chờ lock hoặc chưa kết thúc.

### Lock và DDL

Các thao tác DDL có thể cần lock mạnh hoặc metadata lock. Trước khi chạy:

- Kiểm tra transaction dài và session đang giữ lock.
- Chọn lock timeout phù hợp.
- Xác định có thể hủy an toàn nếu vượt maintenance window.
- Có runbook retry và rollback.
- Thử trên bản sao có dữ liệu gần production.

## 17. Đọc execution plan sau bảo trì

Mục tiêu bảo trì là cải thiện hành vi truy cập hoặc giảm chi phí vận hành. Cần kiểm chứng bằng execution plan và runtime metrics.

Kiểm tra:

- Partition pruning có hoạt động đúng không?
- Số partition được truy cập có giảm theo điều kiện lọc không?
- Estimated rows và actual rows có gần nhau hơn không?
- Index scan/seek có chọn đúng index không?
- Logical reads và physical reads thay đổi thế nào?
- Sort/hash spill có giảm không?
- Planning time có tăng do số partition hoặc index object không?
- Query p50/p95/p99 thay đổi ra sao?
- Insert/update latency có xấu đi do index maintenance không?

### PostgreSQL

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at
FROM public.events
WHERE occurred_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-05-01 00:00:00+00';
~~~

Plan có thể hiển thị Append/Merge Append và các partition scan liên quan. Xác nhận chỉ partition phù hợp được truy cập; xem actual rows, loops, buffers và execution time.

EXPLAIN ANALYZE thực thi truy vấn. Với câu lệnh ghi, nó có thể thay đổi dữ liệu; chỉ dùng trong môi trường an toàn hoặc transaction có thể rollback khi phù hợp.

## 18. Quy trình bảo trì phân vùng và index

Một runbook có thể thực hiện theo thứ tự:

1. Thu thập baseline: kích thước partition/table/index, row estimates, dead tuples, usage và query latency.
2. Xác nhận retention và danh sách partition được phép xử lý.
3. Kiểm tra backup/archive và phụ thuộc dữ liệu.
4. Kiểm tra lock, transaction dài và replication lag.
5. Tạo partition tương lai hoặc chuẩn bị staging.
6. Cập nhật thống kê sau bulk load nếu cần.
7. Vacuum/analyze hoặc thao tác bảo trì phù hợp với engine.
8. Rebuild/reorganize chỉ index có bằng chứng cần thiết.
9. Detach/switch/drop partition hết hạn theo runbook.
10. Kiểm tra dung lượng, metadata, constraint và index sau thao tác.
11. Chạy truy vấn đại diện và đọc execution plan.
12. So sánh latency, logical/physical I/O, throughput và maintenance duration với baseline.
13. Ghi log kết quả, thời gian, partition id và lỗi.
14. Cập nhật lịch, cảnh báo và capacity forecast.

Nên thực hiện từng nhóm nhỏ để giới hạn phạm vi ảnh hưởng. Với thao tác khó đảo ngược như drop partition, xác minh archive và retention phải hoàn tất trước khi chạy.

## 19. Benchmark và xác nhận hiệu quả

Benchmark bảo trì cần đo cả kết quả sau thao tác lẫn chi phí trong lúc thực hiện.

| Nhóm đo | Chỉ số |
|---|---|
| Kích thước | Heap/table size, index size, total size, growth rate |
| Phân vùng | Số partition, size skew, pruning, thời gian attach/detach/drop |
| Thống kê | Thời điểm analyze, estimated vs actual rows |
| Vacuum/cleanup | Dead tuples, vacuum duration, freeze progress, cleanup lag |
| Index | Page count, density/fragmentation theo engine, usage, rebuild time |
| Truy vấn | p50/p95/p99, logical reads, physical reads, buffers |
| Tài nguyên | CPU, memory, IOPS, throughput, storage latency |
| Vận hành | Lock wait, replication lag, backup duration, restore time |

### Thiết kế phép thử

1. Chọn partition đại diện: nóng, lịch sử, lớn và có skew.
2. Ghi nhận size, index, stats và execution plan trước bảo trì.
3. Chạy workload đại diện trong điều kiện kiểm soát.
4. Thực hiện một thao tác bảo trì cụ thể.
5. Ghi thời gian, lock, I/O và dung lượng tạm phát sinh.
6. Cập nhật thống kê nếu cần.
7. Chạy lại cùng query mix và concurrency.
8. So sánh latency, rows, buffers, I/O và plan.
9. Kiểm tra insert/update throughput sau rebuild hoặc thay đổi index.
10. Xác minh archive/restore với partition được chuyển.
11. Chỉ đưa thao tác vào lịch định kỳ khi lợi ích lặp lại được và chi phí chấp nhận được.

Không đánh giá thành công chỉ bằng việc kích thước index giảm. Nếu query latency không cải thiện hoặc write cost tăng, cần xem lại lựa chọn.

## 20. Những sai lầm thường gặp

- **Drop partition chỉ dựa trên tên tháng:** có thể xóa nhầm dữ liệu chưa hết retention.
- **Coi detach/drop là archive:** thao tác loại bỏ không tạo bản lưu trữ có thể phục hồi.
- **Không xác minh backup trước khi xóa:** gây mất dữ liệu lịch sử.
- **Tạo partition quá nhỏ:** tăng metadata và chi phí planning/maintenance.
- **Để default partition tích tụ dữ liệu:** che giấu lỗi tạo partition hoặc dữ liệu sai miền.
- **Không tạo index cho partition mới:** truy vấn có thể chậm sau khi chuyển kỳ.
- **Chạy VACUUM FULL theo lịch:** có thể khóa mạnh và cần nhiều dung lượng tạm.
- **Cho rằng VACUUM thường trả file về OS:** thường chỉ làm không gian có thể tái sử dụng bên trong relation.
- **Rebuild tất cả index:** tạo I/O/log lớn và làm tăng write contention.
- **Xóa index chỉ vì idx_scan thấp:** bỏ qua truy vấn theo mùa, constraint và workload hiếm.
- **Không cập nhật thống kê sau bulk load:** optimizer có thể chọn plan dựa trên phân bố cũ.
- **Bỏ qua thống kê bảng cha partitioned:** parent-level estimates có thể không phản ánh dữ liệu con.
- **Chạy nhiều maintenance job đồng thời:** làm bão hòa storage và ảnh hưởng giao dịch trực tuyến.
- **Chỉ đo dung lượng tổng:** không phát hiện partition skew hoặc index chiếm tỷ trọng lớn.
- **Không dự phòng dung lượng rebuild:** thao tác có thể thất bại khi cần cả index cũ và mới.
- **Áp dụng một ngưỡng fragmentation cho mọi engine:** đặc tính storage và access path khác nhau.
- **Không thử restore archive:** có bản sao nhưng không chứng minh khôi phục được.

## 21. Checklist trước khi chạy maintenance

- Partition được chọn đúng theo retention và ranh giới.
- Dữ liệu cần giữ đã được xác định; legal hold và phụ thuộc đã kiểm tra.
- Backup/archive đã hoàn tất và khả năng restore đã được xác minh.
- Đã ghi baseline kích thước heap, index và tốc độ tăng.
- Đã kiểm tra dead tuples, stats, index usage và execution plan.
- Partition tương lai đã được tạo và có index/constraint cần thiết.
- Default partition được kiểm tra.
- Đã xác định lock và transaction dài có thể cản DDL.
- Đã dự phòng I/O, CPU, log và dung lượng tạm cho vacuum/rebuild.
- Maintenance concurrency nằm trong giới hạn.
- Có timeout, retry và phương án dừng an toàn.
- Đã kiểm tra replication lag và backup window.
- Sau thao tác sẽ xác minh partition tree, index, stats và dung lượng.
- Query đại diện được chạy lại để so sánh plan và latency.
- Kết quả được ghi vào runbook và capacity forecast.

## Kết luận

Bảo trì phân vùng và kiểm soát kích thước bảng/chỉ mục là công việc liên tục gắn với workload và chính sách lưu trữ. Phân vùng cho phép quản lý dữ liệu theo đơn vị, nhưng hiệu quả chỉ xuất hiện khi ranh giới phù hợp với truy vấn và retention. Thống kê, vacuum/cleanup và index maintenance cần dựa trên hoạt động thực tế của từng phân vùng.

Hãy đo kích thước heap và index, theo dõi tăng trưởng và phân bố dữ liệu, cập nhật thống kê sau các thay đổi lớn, chỉ rebuild index khi có bằng chứng, và archive/drop dữ liệu theo quy trình đã xác minh. Đánh giá cả lợi ích truy vấn lẫn chi phí I/O, lock, log, backup và restore. Một lịch bảo trì tốt giúp dữ liệu nóng gọn, dữ liệu lịch sử được quản lý an toàn và database duy trì hiệu năng ổn định khi quy mô tăng.

# VACUUM thường, VACUUM FULL và khóa liên quan

PostgreSQL sử dụng **MVCC (Multi-Version Concurrency Control)**: khi một transaction UPDATE hoặc DELETE một hàng, database thường tạo phiên bản mới hoặc đánh dấu phiên bản cũ không còn phù hợp cho các snapshot tương lai. Các phiên bản cũ (*dead tuples*) không thể bị xóa ngay nếu còn transaction/snapshot có khả năng cần nhìn thấy chúng. Theo thời gian, các dead tuples chiếm chỗ trong heap và có thể làm tăng kích thước indexes, I/O và chi phí quét bảng.

Lệnh **VACUUM** giúp PostgreSQL thu hồi những tuple versions đã không còn cần thiết, cập nhật free space/visibility metadata và hỗ trợ chống transaction ID wraparound. Lệnh **VACUUM FULL** thực hiện một lần rewrite bảng để thu gọn file và trả phần không còn dùng về filesystem, nhưng cần khóa mạnh hơn, thêm dung lượng tạm và có thể chặn mọi truy cập vào bảng trong thời gian chạy.

Hai lệnh cùng có chữ VACUUM nhưng khác nhau đáng kể về **cách xử lý dữ liệu, khả năng thu hồi dung lượng, thời gian thực hiện và lock mode**. Chọn nhầm VACUUM FULL trong giờ cao điểm có thể gây gián đoạn ứng dụng; ngược lại, chỉ chạy VACUUM thường khi filesystem đã cạn vì table bloat có thể không giải phóng đủ dung lượng cho hệ điều hành.

Bài học thuộc chương **VACUUM** của module *Database Engine Relational PostgreSQL*. Mục tiêu là hiểu cơ chế MVCC, chọn đúng lệnh bảo trì, đọc lock/progress/maintenance statistics và xử lý bloat, autovacuum cùng nguy cơ transaction ID wraparound.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao UPDATE/DELETE tạo dead tuples trong PostgreSQL.
2. Phân biệt tuple visibility với việc file vật lý đã được giải phóng.
3. Nêu được chức năng của VACUUM thường, VACUUM FULL và ANALYZE.
4. Hiểu lock mode của VACUUM thường và VACUUM FULL.
5. Biết vì sao VACUUM thường thường chạy đồng thời với SELECT/INSERT/UPDATE/DELETE.
6. Biết VACUUM FULL cần ACCESS EXCLUSIVE và ảnh hưởng tới traffic.
7. Phân biệt không gian được tái sử dụng trong relation với dung lượng trả về operating system.
8. Đọc tiến trình VACUUM và lock/blocking sessions.
9. Hiểu autovacuum thresholds, cost settings và per-table storage parameters.
10. Nhận diện transaction dài, replication slots và standby feedback giữ lại dead tuples.
11. Hiểu freeze, XID age và cơ chế chống wraparound.
12. Lập lịch maintenance, đánh giá disk capacity và thực hiện restore/maintenance an toàn.
13. Dùng các view như pg_stat_user_tables, pg_stat_progress_vacuum, pg_stat_progress_cluster và pg_locks để quan sát.
14. Thực hành trên một bảng lab và phân biệt tác động của hai loại VACUUM.

## 2. Vì sao PostgreSQL cần VACUUM?

PostgreSQL dùng MVCC để cho các transaction đọc những phiên bản dữ liệu phù hợp với snapshot của chúng mà không phải khóa mọi reader và writer theo kiểu một transaction độc quyền.

Ví dụ một hàng:

~~~text
Ban đầu:
  id=10, status='new', xmin=100, xmax=0

Transaction UPDATE:
  phiên bản cũ: xmin=100, xmax=205
  phiên bản mới: xmin=205, xmax=0

Transaction DELETE:
  phiên bản hiện tại: xmax=310
~~~

Các giá trị XID trong sơ đồ chỉ minh họa. PostgreSQL dùng metadata nội bộ phức tạp hơn để xác định tuple có visible với snapshot cụ thể hay không.

### 2.1. UPDATE thường tạo phiên bản mới

Một UPDATE không nhất thiết ghi đè trực tiếp giá trị trên cùng tuple. PostgreSQL có thể tạo một tuple version mới và đánh dấu version cũ không còn là phiên bản hiện tại cho những snapshot tương lai.

### 2.2. DELETE đánh dấu tuple không còn hiện hành

DELETE không nhất thiết lập tức xóa bytes khỏi heap page. Nó đánh dấu tuple là đã bị xóa theo transaction ID, để các snapshots cũ vẫn có thể nhìn thấy nếu cần.

### 2.3. Dead tuple

Một tuple version trở thành *dead* khi không còn snapshot/transaction nào được phép nhìn thấy nó. Lúc đó VACUUM có thể thu hồi chỗ của tuple để sử dụng lại.

### 2.4. Vì sao không xóa ngay khi UPDATE/DELETE?

Một transaction khác có thể đã bắt đầu trước thao tác thay đổi và vẫn cần đọc phiên bản cũ. MVCC giữ những version cần thiết cho tới khi an toàn để thu hồi.

### 2.5. VACUUM không phải một lệnh “xóa hàng”

Nó không thay thế DELETE, không quyết định business row nào cần giữ và không tự xóa các hàng còn visible. Nó dọn các phiên bản đã hết vòng đời theo quy tắc visibility của PostgreSQL.

## 3. Heap, page và dead tuples

Một bảng PostgreSQL được lưu thành các pages (thường 8 KB theo build mặc định), chứa tuple versions và các metadata liên quan.

~~~text
Heap page minh họa
+----------------------------------+
| Page header / line pointers      |
+----------------------------------+
| tuple A: LIVE                    |
| tuple B: DEAD                    |
| tuple C: LIVE                    |
| tuple D: DEAD                    |
| free space                       |
+----------------------------------+
~~~

### 3.1. Dead tuple vẫn chiếm dung lượng

Trước khi VACUUM thu hồi, tuple đã dead có thể vẫn chiếm slot/page bytes và góp phần làm relation lớn hơn cần thiết.

### 3.2. Free space map

VACUUM cập nhật thông tin free space để PostgreSQL có thể tìm page có chỗ trống khi cần INSERT hoặc UPDATE tạo tuple mới.

### 3.3. Visibility map

VACUUM quản lý visibility map, ghi nhận các pages mà mọi tuples đều visible với mọi transaction hiện tại (all-visible) và trạng thái all-frozen khi phù hợp. Metadata này hỗ trợ index-only scans và giảm công việc kiểm tra visibility.

### 3.4. Indexes cũng chịu ảnh hưởng

Một UPDATE/DELETE có thể để lại dead index entries cần được cleanup. VACUUM thường phối hợp xử lý heap và index cleanup theo chiến lược của engine/phiên bản.

### 3.5. TOAST data

Giá trị lớn có thể được lưu ở TOAST relation. Việc thu hồi tuple versions và các TOAST chunks cũng cần được quản lý; không chỉ nhìn heap table mà bỏ qua toàn bộ storage liên quan.

## 4. VACUUM thường làm gì?

Lệnh cơ bản:

~~~sql
VACUUM sales.orders;
~~~

VACUUM thường quét relation, xác định tuples không còn cần thiết, thu hồi chúng để tái sử dụng, cập nhật free space/visibility metadata và thực hiện các công việc freeze cần thiết.

### 4.1. Tái sử dụng chỗ trống bên trong relation

Phần lớn không gian được VACUUM thường giải phóng sẽ có thể được sử dụng cho các tuples mới trong cùng relation. File không nhất thiết nhỏ đi trên filesystem.

### 4.2. Có thể truncate các pages trống ở cuối file

Nếu các pages cuối relation hoàn toàn trống và tính năng truncation được bật, VACUUM có thể loại bỏ phần đuôi đó để trả một phần dung lượng về operating system. Việc này cần ACCESS EXCLUSIVE lock trong bước truncate; có thể bị bỏ qua nếu không lấy được lock theo cơ chế của phiên bản/cấu hình.

### 4.3. Truncate không phải compact toàn bảng

Nếu pages trống nằm rải rác giữa relation, VACUUM thường không di chuyển toàn bộ tuples để gom chúng về đầu file. Do đó file có thể vẫn lớn.

### 4.4. Không chặn DML theo cách VACUUM FULL làm

VACUUM thường lấy lock SHARE UPDATE EXCLUSIVE trên relation. Lock này tương thích với các ROW EXCLUSIVE locks của INSERT/UPDATE/DELETE và ACCESS SHARE locks của SELECT, dù vẫn có contention tài nguyên và xung đột với một số thao tác DDL/maintenance.

### 4.5. Có thể tốn I/O và CPU

VACUUM thường không khóa ứng dụng hoàn toàn nhưng vẫn quét pages, đọc/ghi heap và index, dùng CPU và có thể cạnh tranh I/O với query workload.

## 5. VACUUM FULL làm gì?

Lệnh:

~~~sql
VACUUM FULL sales.orders;
~~~

VACUUM FULL tạo một bản rewrite/compact của relation, chỉ giữ những tuple versions còn cần, rồi thay relation cũ bằng bản mới. Indexes liên quan cũng được tái tạo theo quy trình rewrite.

### 5.1. Thu gọn relation vật lý

Vì dữ liệu được viết lại, các khoảng trống rải rác có thể được loại bỏ và dung lượng file sau khi hoàn thành thường giảm đáng kể.

### 5.2. Trả dung lượng về operating system

Không gian của relation cũ được giải phóng sau khi thay thế, vì vậy filesystem có thể nhận lại dung lượng thay vì chỉ giữ free pages trong relation.

### 5.3. Không gian tạm phải đủ lớn

Trong quá trình rewrite, relation cũ vẫn tồn tại trong lúc relation mới được tạo. Cần dự trù thêm dung lượng disk cho bản mới và các indexes/auxiliary files, ngoài dung lượng của dữ liệu hiện tại.

### 5.4. Cần ACCESS EXCLUSIVE lock

VACUUM FULL lấy lock ACCESS EXCLUSIVE trên table và giữ trong quá trình rewrite. Lock này chặn SELECT, INSERT, UPDATE, DELETE và các truy cập relation khác cần lock xung đột.

### 5.5. Không phải lệnh bảo trì hằng ngày

Vì tốn disk, I/O, thời gian và chặn truy cập, VACUUM FULL thường chỉ nên dùng khi thực sự cần compact/reclaim disk và có maintenance window/biện pháp giảm tác động.

## 6. So sánh VACUUM và VACUUM FULL

| Tiêu chí | VACUUM thường | VACUUM FULL |
|---|---|---|
| Thu hồi dead tuples | Có | Có, qua rewrite |
| Giữ relation file hiện tại | Có, thông thường | Rewrite thành relation mới |
| Reuse free space | Có | Có, relation được compact |
| Trả space cho OS | Thường không; có thể truncate tail pages | Thường có sau rewrite |
| Lock chính trên table | SHARE UPDATE EXCLUSIVE | ACCESS EXCLUSIVE |
| SELECT trong lúc chạy | Thường được phép | Bị chặn |
| INSERT/UPDATE/DELETE | Thường được phép | Bị chặn |
| Rewrite toàn heap | Không | Có |
| Rebuild indexes | Cleanup index entries theo quy trình VACUUM | Indexes được tái tạo cùng rewrite |
| Disk tạm | Thường ít hơn | Cần đáng kể |
| Thời gian | Thường phù hợp routine maintenance | Có thể rất lâu |
| Mục đích | Routine cleanup, reuse, freeze | Reclaim/compact mạnh |

### 6.1. Chọn VACUUM thường khi

- Muốn dọn dead tuples định kỳ.
- Bảng vẫn đang được ứng dụng đọc/ghi.
- Không cần trả phần lớn free space cho filesystem ngay.
- Autovacuum chưa kịp xử lý và cần chạy manual maintenance.
- Muốn cập nhật visibility map/freeze metadata.

### 6.2. Cân nhắc VACUUM FULL khi

- Bảng bị phình lớn và cần thu hồi disk thực sự.
- Có khoảng trống lớn phân tán trong heap.
- Có đủ disk tạm để giữ old/new copies trong lúc rewrite.
- Có thể chấp nhận ACCESS EXCLUSIVE lock và downtime/blocking.
- Đã xác định nguyên nhân bloat và có kế hoạch tránh tái diễn.

### 6.3. Không dùng FULL chỉ vì n_dead_tup cao

Số dead tuples là ước lượng và không tự cho biết tỷ lệ bloat vật lý. Cần xem relation size, workload, free space, indexes, transaction horizon và yêu cầu filesystem.

### 6.4. Không dùng VACUUM thường với kỳ vọng filesystem chắc chắn nhỏ lại

Nó chủ yếu làm chỗ trống có thể được tái sử dụng. Nếu mục tiêu là thu hồi nhiều dung lượng cho OS, phải xem rewrite/partition lifecycle/alternative compaction strategy.

## 7. Lock mode của VACUUM thường

VACUUM thường lấy **SHARE UPDATE EXCLUSIVE** lock trên relation được xử lý.

### 7.1. Lock này cho phép SELECT

SELECT thông thường lấy ACCESS SHARE, tương thích với SHARE UPDATE EXCLUSIVE. Readers vẫn có thể truy cập bảng trong khi VACUUM chạy.

### 7.2. Lock này cho phép DML thông thường

INSERT, UPDATE và DELETE thường lấy ROW EXCLUSIVE; lock này tương thích với SHARE UPDATE EXCLUSIVE. Writers có thể tiếp tục hoạt động.

### 7.3. Nó không tương thích với chính nó

SHARE UPDATE EXCLUSIVE xung đột với một SHARE UPDATE EXCLUSIVE khác trên cùng relation. Vì vậy hai VACUUM/ANALYZE hoặc một số maintenance operations có thể phải chờ nhau.

### 7.4. Xung đột với DDL/maintenance

Một số thao tác cần SHARE, SHARE ROW EXCLUSIVE, EXCLUSIVE hoặc ACCESS EXCLUSIVE có thể chờ VACUUM. Ví dụ các thao tác ALTER TABLE có lock mạnh tùy subcommand.

### 7.5. Đừng kết luận “VACUUM không lock”

VACUUM có lock; điểm quan trọng là lock mode thường tương thích với traffic SELECT/DML. Nó vẫn có thể bị chặn bởi transaction giữ lock xung đột hoặc làm workload chậm do I/O.

## 8. Lock mode của VACUUM FULL

VACUUM FULL sử dụng **ACCESS EXCLUSIVE** lock.

### 8.1. ACCESS EXCLUSIVE là lock mạnh nhất

Nó xung đột với mọi table-level lock mode khác, bao gồm ACCESS SHARE mà SELECT thường cần.

### 8.2. SELECT có thể bị block

Khi VACUUM FULL đang giữ lock, SELECT mới trên table phải đợi. Các query đã giữ lock trước đó có thể khiến VACUUM FULL phải chờ trước khi bắt đầu.

### 8.3. DML bị block

INSERT, UPDATE và DELETE cần lock xung đột; ứng dụng có thể tích tụ waiting connections, pool exhaustion và timeout.

### 8.4. Các truy vấn khác có thể kéo dài sự cố

Một transaction mở lâu và giữ lock relation có thể khiến VACUUM FULL chờ mãi. Khi VACUUM FULL đã lấy lock, các ứng dụng mới lại xếp hàng phía sau nó.

### 8.5. Lock wait có thể tạo queue effect

Một DDL/VACUUM FULL đang chờ lock mạnh có thể khiến các truy vấn đến sau phải chờ tùy queueing/lock manager behavior. Vì thế cần xem blockers và thời gian chờ, không chỉ xem process đang chạy.

## 9. Bảng lock compatibility cần nhớ

Một cách nhìn rút gọn:

| Lock được giữ | SELECT (ACCESS SHARE) | DML (ROW EXCLUSIVE) | VACUUM thường (SHARE UPDATE EXCLUSIVE) | VACUUM FULL (ACCESS EXCLUSIVE) |
|---|---:|---:|---:|---:|
| ACCESS SHARE | Tương thích | Tương thích | Tương thích | Xung đột |
| ROW EXCLUSIVE | Tương thích | Tương thích | Tương thích | Xung đột |
| SHARE UPDATE EXCLUSIVE | Tương thích | Tương thích | Xung đột | Xung đột |
| ACCESS EXCLUSIVE | Xung đột | Xung đột | Xung đột | Xung đột |

Bảng chỉ minh họa các lock modes chính; PostgreSQL có nhiều table lock modes hơn. Với lock conflict cụ thể, xem ma trận lock chính thức theo phiên bản server.

### 9.1. ACCESS SHARE

SELECT thông thường lấy lock này khi truy cập relation.

### 9.2. ROW EXCLUSIVE

INSERT/UPDATE/DELETE thường lấy lock này trên table bị thay đổi.

### 9.3. SHARE UPDATE EXCLUSIVE

Dùng bởi VACUUM thường và một số operations bảo trì/DDL. Không chặn SELECT/DML thường, nhưng xung đột với maintenance cùng loại trên cùng relation.

### 9.4. ACCESS EXCLUSIVE

VACUUM FULL, nhiều DDL và một số operations cần quyền độc quyền mạnh. Nó chặn mọi table lock mode khác.

### 9.5. Relation lock khác row lock

Table-level lock của VACUUM FULL không giống row-level locks do SELECT FOR UPDATE/UPDATE giữ trên từng hàng. Đừng dùng hai khái niệm thay thế nhau khi phân tích blocking.

## 10. Vì sao VACUUM FULL có thể gây downtime?

Giả sử bảng `sales.orders` đang có traffic:

~~~text
Application SELECT ---- ACCESS SHARE -----+
Application UPDATE ---- ROW EXCLUSIVE ----+--> Table
VACUUM FULL ----------- ACCESS EXCLUSIVE --+
~~~

### 10.1. Nếu query đã chạy trước

VACUUM FULL phải đợi các transactions đang giữ lock xung đột trên bảng hoàn tất. Một transaction mở lâu có thể kéo dài thời gian chờ.

### 10.2. Nếu VACUUM FULL lấy lock trước

Các SELECT/DML mới sẽ chờ cho tới khi nó hoàn tất và nhả ACCESS EXCLUSIVE.

### 10.3. Connection pool có thể bị cạn

Nhiều connections cùng chờ một table có thể chiếm hết pool. Khi đó cả endpoint khác cũng có thể chậm nếu dùng chung pool.

### 10.4. Timeout không phải cơ chế rollback toàn bộ rủi ro

`lock_timeout` có thể giới hạn thời gian chờ lock khi thiết lập session phù hợp; `statement_timeout` có thể giới hạn statement. Nhưng cần xác định hậu quả và cách ứng dụng retry, không chỉ đặt timeout rồi chạy FULL tùy tiện.

### 10.5. Maintenance window phải tính cả thời gian chờ lock

Không chỉ ước lượng thời gian rewrite. Cần dự trù blockers, queue, disk, I/O, rebuild indexes và xác minh sau thao tác.

## 11. Truncation ở cuối bảng trong VACUUM thường

VACUUM thường chủ yếu giữ free space bên trong relation, nhưng có thể truncate các pages hoàn toàn trống ở cuối heap file.

### 11.1. Vì sao cần lock mạnh?

Để loại bỏ các pages cuối relation an toàn, PostgreSQL cần lock ACCESS EXCLUSIVE cho bước truncate. Bước này khác với SHARE UPDATE EXCLUSIVE lock chính của VACUUM.

### 11.2. Có thể tránh bước truncate

Ở các phiên bản hỗ trợ tùy chọn này, có thể dùng:

~~~sql
VACUUM (TRUNCATE FALSE) sales.orders;
~~~

Hoặc thiết lập storage parameter phù hợp cho bảng theo tài liệu phiên bản đang chạy. Tắt truncate có thể tránh đợt lock mạnh ngắn, nhưng đồng nghĩa bỏ cơ hội trả phần đuôi file trống về OS.

### 11.3. Không biến VACUUM thường thành VACUUM FULL

`TRUNCATE FALSE` chỉ điều khiển việc cắt pages trống ở cuối file; nó không rewrite toàn bộ bảng.

### 11.4. Không phải mọi bảng đều có tail pages trống

Nếu free space phân bố giữa các pages, bước truncate không thể thu gọn file nhiều. Khi đó VACUUM thường vẫn có ích cho reuse nội bộ.

### 11.5. Đọc tài liệu theo PostgreSQL version

Các VACUUM options/storage parameters có thể khác giữa major versions. Kiểm tra `SHOW server_version` và tài liệu tương ứng trước khi dùng.

## 12. VACUUM không giống ANALYZE

`ANALYZE` thu thập thống kê về phân bố dữ liệu để query planner chọn kế hoạch thực thi. Nó không thay thế việc dọn dead tuples.

~~~sql
ANALYZE sales.orders;
VACUUM sales.orders;
VACUUM (ANALYZE) sales.orders;
~~~

### 12.1. ANALYZE

Cập nhật statistics như số lượng giá trị distinct ước lượng, most common values, histogram và null fraction cho các cột được lấy mẫu.

### 12.2. VACUUM

Thu hồi dead tuples, cập nhật free space/visibility metadata và thực hiện freeze theo yêu cầu.

### 12.3. VACUUM ANALYZE

Chạy cả hai công việc trong một thao tác bảo trì:

~~~sql
VACUUM (VERBOSE, ANALYZE) sales.orders;
~~~

### 12.4. Khi query chậm sau một đợt import lớn

Có thể cần ANALYZE để planner nhận biết phân bố dữ liệu mới. Chạy VACUUM FULL chỉ để cập nhật statistics là lựa chọn sai.

### 12.5. ANALYZE không cần ACCESS EXCLUSIVE

ANALYZE dùng lock bảo trì nhẹ hơn và tương thích với traffic thông thường theo lock semantics PostgreSQL. Nó không phải lệnh rewrite bảng.

## 13. VACUUM FREEZE và transaction ID wraparound

PostgreSQL dùng transaction IDs (XIDs) có không gian hữu hạn. Nếu một database không freeze các tuple cũ đúng hạn, các XIDs có thể tiến gần tới wraparound, gây nguy cơ dữ liệu cũ bị hiểu sai về visibility.

### 13.1. Freeze là gì?

VACUUM có thể đánh dấu những tuple đủ cũ là frozen theo quy tắc của PostgreSQL, để không cần tiếp tục so sánh chúng với XIDs cũ theo cách thông thường.

### 13.2. Vì sao cần chống wraparound?

PostgreSQL phải đảm bảo tuple cũ không bị coi là thuộc transaction “tương lai” sau khi XID counter quay vòng. Freeze là một phần cốt lõi của cơ chế bảo vệ này.

### 13.3. VACUUM FREEZE

~~~sql
VACUUM (FREEZE, VERBOSE) sales.orders;
~~~

Đây là yêu cầu freeze tích cực hơn cho relation trong phạm vi lệnh, không phải cách compact file như VACUUM FULL.

### 13.4. Autovacuum anti-wraparound

PostgreSQL có thể kích hoạt autovacuum khẩn cấp để bảo vệ khỏi XID wraparound ngay cả khi cấu hình autovacuum thông thường bị tắt. Không dựa vào việc disable autovacuum để né maintenance.

### 13.5. Đừng đợi tới cảnh báo nghiêm trọng

Nếu database tiến gần giới hạn wraparound, PostgreSQL có thể cảnh báo và cuối cùng ngăn một số thao tác ghi để bảo vệ tính toàn vẹn. Phải monitor tuổi XID và đảm bảo vacuum có thể chạy.

## 14. Autovacuum là cơ chế bảo trì tự động

Autovacuum gồm launcher và các workers chạy nền. Nó quan sát thống kê và thresholds để quyết định khi nào cần VACUUM/ANALYZE các tables.

~~~text
DML workload
     |
     v
Statistics collector / counters
     |
     v
Autovacuum launcher
     |
     +---- worker 1 ---> table A VACUUM
     |
     +---- worker 2 ---> table B ANALYZE
     |
     +---- worker 3 ---> table C VACUUM ANALYZE
~~~

### 14.1. Autovacuum không phải scheduler theo giờ đơn giản

Nó phản ứng theo ngưỡng thống kê và các yếu tố tuổi XID/insert activity, không chỉ chạy “mỗi ngày lúc 2 giờ”.

### 14.2. Mục tiêu là giữ bảng được bảo trì kịp thời

Autovacuum giảm dead tuples tích tụ, cập nhật planner statistics và freeze XIDs trước khi wraparound trở thành sự cố.

### 14.3. Không tắt autovacuum toàn cluster tùy tiện

Tắt nó có thể dẫn đến bloat, query chậm, thiếu thống kê và nguy cơ wraparound. Nếu có workload đặc biệt, tune theo bảng/cluster và đo đạc.

### 14.4. Manual VACUUM vẫn có chỗ dùng

Một lần import/delete lớn, bảng có thay đổi đột biến hoặc autovacuum chưa kịp xử lý có thể cần maintenance thủ công.

### 14.5. Autovacuum dùng lock VACUUM thông thường

Routine autovacuum không tự thực hiện VACUUM FULL. Nó dùng cơ chế VACUUM thường, nên không rewrite toàn bộ relation để compact như FULL.

## 15. Autovacuum thresholds

Ngưỡng vacuum thông thường được tính dựa trên số tuples dead ước lượng và các tham số cấu hình.

~~~text
vacuum threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * estimated_table_tuples
~~~

### 15.1. Threshold cố định

`autovacuum_vacuum_threshold` là phần ngưỡng cơ bản, có thể điều chỉnh trong cấu hình.

### 15.2. Scale factor

`autovacuum_vacuum_scale_factor` nhân với quy mô ước lượng của bảng. Một bảng lớn có thể cần rất nhiều dead tuples trước khi threshold mặc định đạt tới.

### 15.3. Bảng rất lớn có thể cần scale factor thấp hơn

Ví dụ một bảng hàng tỷ rows, scale factor mặc định có thể khiến hàng triệu tuples dead tích tụ trước khi autovacuum được kích hoạt. Có thể hạ threshold theo đặc tính bảng sau khi quan sát.

### 15.4. Analyze có threshold riêng

Các tham số `autovacuum_analyze_threshold` và `autovacuum_analyze_scale_factor` điều khiển thời điểm cần cập nhật statistics. Vacuum và analyze không nhất thiết kích hoạt cùng lúc.

### 15.5. Insert-triggered vacuum

PostgreSQL có các tham số riêng như `autovacuum_vacuum_insert_threshold` và `autovacuum_vacuum_insert_scale_factor` để xử lý các bảng insert-heavy, kể cả khi dead tuple count không phải tín hiệu chính.

## 16. Tune autovacuum theo từng bảng

Có thể đặt reloptions trên bảng:

~~~sql
ALTER TABLE sales.orders
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
~~~

Các con số chỉ là ví dụ. Không sao chép vào production mà chưa đánh giá row churn, write rate, I/O và dung lượng.

### 16.1. Vì sao per-table tuning hữu ích?

Một bảng orders có churn cao khác một bảng country_codes gần như bất biến. Một scale factor áp cho mọi bảng có thể quá chậm với bảng lớn hoặc gây maintenance quá thường xuyên với bảng nhỏ.

### 16.2. Xem reloptions

~~~sql
SELECT
    schemaname,
    tablename,
    reloptions
FROM pg_tables
WHERE schemaname = 'sales'
  AND tablename = 'orders';
~~~

Có thể dùng catalog phù hợp để xem reloptions chính xác; `pg_tables` là view tiện ích.

### 16.3. Reset về mặc định

~~~sql
ALTER TABLE sales.orders
RESET (
    autovacuum_vacuum_threshold,
    autovacuum_vacuum_scale_factor
);
~~~

Chỉ reset những options đã xác định; kiểm tra cú pháp theo version.

### 16.4. Không hạ threshold vô hạn

Vacuum quá thường xuyên có thể tạo I/O overhead, cạnh tranh tài nguyên và ảnh hưởng latency. Mục tiêu là cân bằng churn, bloat và chi phí.

### 16.5. ALTER TABLE không chạy vacuum ngay lập tức

Thay reloptions tác động đến lần launcher/worker đánh giá sau đó. Nếu cần dọn ngay, cân nhắc manual VACUUM trong giờ phù hợp.

## 17. Các tham số autovacuum ở cấp server

| Tham số | Ý nghĩa khái quát |
|---|---|
| `autovacuum` | Bật/tắt cơ chế autovacuum |
| `autovacuum_naptime` | Khoảng chờ giữa các lần launcher kiểm tra |
| `autovacuum_max_workers` | Số workers tối đa |
| `autovacuum_vacuum_threshold` | Ngưỡng dead tuples cơ bản |
| `autovacuum_vacuum_scale_factor` | Phần ngưỡng theo quy mô bảng |
| `autovacuum_analyze_threshold` | Ngưỡng thay đổi cơ bản để ANALYZE |
| `autovacuum_analyze_scale_factor` | Ngưỡng ANALYZE theo quy mô |
| `autovacuum_vacuum_cost_limit` | Cost budget cho autovacuum khi được đặt |
| `autovacuum_vacuum_cost_delay` | Delay theo cơ chế cost-based throttling |
| `autovacuum_work_mem` | Bộ nhớ làm việc riêng của autovacuum khi cấu hình |
| `autovacuum_freeze_max_age` | Ngưỡng tuổi XID thúc đẩy freeze/anti-wraparound |

### 17.1. Số workers

Tăng `autovacuum_max_workers` có thể giúp nhiều tables được xử lý song song, nhưng cũng tăng áp lực CPU, memory và I/O.

### 17.2. Cost-based delay

Cơ chế vacuum cost delay/limit có thể làm chậm maintenance để giảm ảnh hưởng workload. Nếu đặt quá thấp, autovacuum có thể không theo kịp tốc độ churn.

### 17.3. Work memory

VACUUM cần theo dõi dead tuple identifiers và index cleanup. Bộ nhớ thấp có thể dẫn tới nhiều vòng xử lý hơn; bộ nhớ quá cao nhân với nhiều workers có thể gây áp lực RAM.

### 17.4. Không tune theo một metric

Cần quan sát dead tuple estimates, table size, autovacuum frequency/duration, I/O latency, transaction age, WAL generation và query latency.

### 17.5. Parameter context và reload

Một số tham số cần reload/restart tùy context/version. Kiểm tra `pg_settings.context`, `pending_restart` và tài liệu server thay vì đoán.

## 18. Autovacuum có thể không theo kịp vì sao?

Các nguyên nhân phổ biến:

- Bảng có write churn cao hơn năng lực vacuum.
- Scale factor/threshold quá cao.
- Worker slots bị chiếm bởi các tables khác.
- I/O quá chậm hoặc cost delay quá lớn.
- Transaction/snapshot cũ giữ lại dead tuples.
- Replication slot/standby feedback giữ xmin.
- Lock xung đột khiến worker chờ.
- Bảng partitioned parent cần ANALYZE riêng theo semantics/version.
- Dung lượng memory/index cleanup khiến vacuum phải làm nhiều vòng.
- Một số bảng có reloptions riêng không phù hợp.

### 18.1. Worker count tăng không giải quyết horizon bị giữ

Nếu một transaction lâu năm vẫn cần phiên bản cũ, vacuum có chạy liên tục cũng không thể xóa những tuples chưa an toàn.

### 18.2. Scale factor thấp không giải quyết I/O bottleneck

Nó làm vacuum được gọi sớm hơn, nhưng không tự tăng tốc đọc/ghi storage.

### 18.3. Xem worker đang chờ gì

Kết hợp `pg_stat_activity`, `pg_locks`, `pg_stat_progress_vacuum` và logs để xác định wait, không chỉ nhìn bảng có nhiều dead tuples.

### 18.4. Cẩn trọng khi manual VACUUM chạy trùng autovacuum

Chúng có thể xung đột lock trên cùng relation hoặc lãng phí tài nguyên. Kiểm tra workers trước khi chạy lệnh thủ công.

### 18.5. Đừng dừng autovacuum một cách phản xạ

Dừng worker có thể làm việc bảo trì dở dang và khiến vấn đề tiếp tục. Xác định blocker/resource cause trước.

## 19. Transaction lâu giữ lại dead tuples

VACUUM chỉ được phép thu hồi một tuple version khi chắc chắn không còn transaction snapshot nào cần nó. Một transaction mở quá lâu có thể giữ xmin horizon cũ.

~~~text
Transaction A: BEGIN; SELECT ...;  (giữ snapshot cũ)
Transaction B: UPDATE row; COMMIT
Transaction C: DELETE row; COMMIT
VACUUM: chưa thể xóa mọi versions mà A còn cần
Transaction A: COMMIT
VACUUM sau đó có thể thu hồi thêm tuples
~~~

### 19.1. Idle in transaction

Một client chạy BEGIN rồi để connection ở trạng thái `idle in transaction` có thể giữ snapshot dù không còn thực hiện query. Đây là một nguyên nhân phổ biến khiến VACUUM không thu hồi được dữ liệu cũ.

### 19.2. Transaction chạy lâu

Các truy vấn phân tích, cursor hoặc batch transaction kéo dài có thể giữ xmin lâu. Cần xem thời lượng transaction, không chỉ thời lượng statement cuối.

### 19.3. Prepared transactions

Các prepared transactions có thể giữ locks và ảnh hưởng tới tiến trình bảo trì cho tới khi được COMMIT PREPARED hoặc ROLLBACK PREPARED. Theo dõi `pg_prepared_xacts` nếu hệ thống dùng two-phase commit.

### 19.4. VACUUM không thể xóa tuple còn visible

Tăng workers hoặc chạy VACUUM FULL không phải cách giải quyết gốc nếu một transaction còn cần dữ liệu cũ. Phải xử lý transaction horizon theo quy trình an toàn.

### 19.5. Không terminate transaction chỉ dựa trên tuổi

Một transaction lâu có thể đang chạy nghiệp vụ quan trọng. Xác định owner, query, trạng thái, tác động và rollback semantics trước khi terminate.

## 20. Replication slots và standby feedback

Replication cũng có thể giữ lại các tuple versions mà primary chưa được phép thu hồi.

### 20.1. Replication slot giữ xmin

Logical replication slots có thể giữ `xmin` hoặc `catalog_xmin` để consumer còn đọc được dữ liệu cần thiết. Nếu consumer dừng lâu, VACUUM có thể không dọn được một số tuples/catalog rows.

### 20.2. Hot standby feedback

Standby có thể gửi xmin feedback về primary để tránh query trên standby bị conflict với cleanup. Điều này giúp một số read workloads, nhưng có thể làm primary giữ dead tuples lâu hơn và tăng bloat.

### 20.3. Slot lag và WAL retention là hai vấn đề liên quan nhưng khác nhau

Replication slot có thể giữ WAL qua `restart_lsn` và đồng thời giữ xmin/catalog_xmin. Phải monitor cả dung lượng WAL lẫn tuple cleanup horizon.

### 20.4. Kiểm tra slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Một số cột/trạng thái có thể khác theo PostgreSQL version và slot type.

### 20.5. Không drop slot chỉ để ép VACUUM

Xóa replication slot có thể làm consumer không thể tiếp tục replication hoặc logical decoding. Xác minh owner và khả năng rebuild consumer trước khi thay đổi.

## 21. Kiểm tra transaction và xmin horizon

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

### 21.1. backend_xmin

Cho biết xmin của snapshot mà backend đang giữ trong một số trạng thái. Đây là dấu hiệu quan trọng khi điều tra transaction giữ cleanup horizon.

### 21.2. application_name giúp truy vết

Cấu hình ứng dụng có application_name rõ để DBA biết connection đến từ service/batch/reporting job nào.

### 21.3. Không dump toàn query nếu có secrets

Query text có thể chứa literal nhạy cảm trong những ứng dụng viết SQL không an toàn. Trong dashboard/ticket, redaction và quyền xem vẫn quan trọng.

### 21.4. idle_in_transaction_session_timeout

Có thể cấu hình timeout để đóng những sessions idle trong transaction quá lâu, nhưng phải cân nhắc workload và application behavior trước khi áp dụng.

### 21.5. Hủy session có thể rollback transaction

Nếu buộc phải giải phóng horizon, `pg_cancel_backend` hoặc `pg_terminate_backend` có thể ảnh hưởng query/transaction. Đây là thao tác vận hành có tác động, không phải một phần mặc định của VACUUM.

## 22. Quan sát bảng nào cần VACUUM

View `pg_stat_user_tables` cung cấp thống kê ước lượng theo table.

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

### 22.1. n_dead_tup là estimate

Đây là ước lượng thống kê, không phải phép đếm vật lý chính xác mọi dead tuple tại đúng thời điểm query.

### 22.2. Không xếp hạng chỉ bằng con số tuyệt đối

Một bảng có 100.000 dead tuples nhưng 10 tỷ rows có thể ít đáng lo hơn một bảng 120.000 rows mà gần như tất cả versions đang dead.

### 22.3. So với kích thước relation

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(
        pg_relation_size(
            format('%I.%I', schemaname, relname)::regclass
        )
    ) AS heap_size,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', schemaname, relname)::regclass
        )
    ) AS total_size,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC
LIMIT 30;
~~~

Query này dùng tên schema/table từ view để tạo regclass; trong script quản trị thực tế, có thể dùng OID/joins để tránh phụ thuộc search_path và xử lý identifiers rõ hơn.

### 22.4. Heap size và total size khác nhau

`pg_relation_size` đo relation heap chính; `pg_total_relation_size` bao gồm indexes và TOAST liên quan theo semantics của hàm.

### 22.5. Không tự suy bloat chính xác từ n_dead_tup

Để đo sâu hơn có thể dùng extension như `pgstattuple` nếu được cài và có quyền, hoặc công cụ phân tích bloat có hiểu version. Ước lượng thống kê đơn giản chỉ là điểm bắt đầu.

## 23. Theo dõi VACUUM đang chạy

View `pg_stat_progress_vacuum` cung cấp tiến độ của VACUUM thường:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

### 23.1. Phase thay đổi trong quá trình chạy

VACUUM có nhiều phases, ví dụ scanning heap, vacuuming indexes, vacuuming heap, cleaning up indexes, truncating heap và performing final cleanup. Tên phase/cột cần đối chiếu version.

### 23.2. Tỷ lệ tiến độ không đồng nghĩa thời gian còn lại chính xác

Số heap blocks scanned/total là một tín hiệu, nhưng các phases index cleanup hoặc waits có chi phí khác nhau.

### 23.3. VACUUM FULL có progress view khác

VACUUM FULL được triển khai theo hướng rewrite relation và được báo cáo trong `pg_stat_progress_cluster` ở các phiên bản hỗ trợ. Đừng chỉ nhìn pg_stat_progress_vacuum rồi kết luận FULL không chạy.

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written,
    heap_blks_total,
    heap_blks_scanned,
    index_rebuild_count
FROM pg_stat_progress_cluster;
~~~

Các cột có thể thay đổi theo phiên bản; kiểm tra view schema của server đang chạy.

### 23.4. Không phải mọi maintenance đều có progress view giống nhau

Khi query view không trả rows, có thể lệnh chưa chạy, đã kết thúc, bạn thiếu quyền quan sát hoặc operation được báo ở view khác.

### 23.5. Verbose output

~~~sql
VACUUM (VERBOSE) sales.orders;
~~~

VERBOSE ghi thông tin xử lý hữu ích cho chẩn đoán; hãy bảo đảm logs không bị lạm dụng và có quyền phù hợp.

## 24. Xem lock và session đang chặn

Một query cơ bản để xem locks trên bảng:

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    l.mode,
    l.granted,
    now() - a.query_start AS query_age,
    a.wait_event_type,
    a.wait_event,
    left(a.query, 180) AS query_sample
FROM pg_locks AS l
JOIN pg_stat_activity AS a
  ON a.pid = l.pid
LEFT JOIN pg_class AS c
  ON c.oid = l.relation
LEFT JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE l.locktype = 'relation'
  AND n.nspname = 'sales'
  AND c.relname = 'orders'
ORDER BY l.granted, a.query_start;
~~~

### 24.1. granted=false

Backend đang đợi lock. Xác định ai đang giữ lock xung đột và statement nào gây ra.

### 24.2. granted=true

Backend đang giữ lock. Có thể là VACUUM, query hoặc transaction đã lấy lock rồi để mở lâu.

### 24.3. Lock trên relation không phải mọi lock

Query này lọc relation locks; nó không mô tả đầy đủ tuple locks, transactionid locks hoặc waits trên các resources khác.

### 24.4. pg_blocking_pids

PostgreSQL cung cấp `pg_blocking_pids(pid)` để tìm backend đang chặn một PID.

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocker.pid AS blocker_pid,
    blocked.application_name AS blocked_app,
    blocker.application_name AS blocker_app,
    now() - blocker.xact_start AS blocker_xact_age,
    left(blocked.query, 120) AS blocked_query,
    left(blocker.query, 120) AS blocker_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS b(pid)
JOIN pg_stat_activity AS blocker
  ON blocker.pid = b.pid;
~~~

### 24.5. Không chỉ kill PID đang chờ

Hãy xác định root blocker, transaction age, owner và hậu quả. Kill một waiter không giải quyết transaction giữ lock gốc.

## 25. VACUUM thường có thể vẫn bị chặn

Mặc dù lock chính tương thích với DML, VACUUM vẫn có thể đợi lock xung đột từ DDL hoặc maintenance khác.

Ví dụ:

- `ALTER TABLE` cần ACCESS EXCLUSIVE.
- Một VACUUM/ANALYZE khác đang giữ SHARE UPDATE EXCLUSIVE.
- `CREATE INDEX CONCURRENTLY` dùng lock bảo trì có thể xung đột.
- Một số thao tác REINDEX/CLUSTER hoặc schema maintenance.
- Lock queue bị ảnh hưởng bởi một ACCESS EXCLUSIVE đang chờ.

### 25.1. DDL và VACUUM

Lên lịch schema migrations để không đè lên maintenance lớn. Một DDL cần lock mạnh có thể chờ VACUUM; VACUUM sau đó cũng có thể bị queue phía sau DDL tùy thứ tự.

### 25.2. Lock timeout

Có thể đặt timeout cho session bảo trì:

~~~sql
SET lock_timeout = '5s';
VACUUM sales.orders;
~~~

Nếu không lấy được lock trong thời gian cho phép, statement có thể thất bại. Lưu ý VACUUM không chạy trong transaction block; `SET` session vẫn có thể áp dụng khi chạy lệnh ở autocommit.

### 25.3. VACUUM không chạy trong transaction block

~~~sql
-- Không dùng:
BEGIN;
VACUUM sales.orders;
COMMIT;
~~~

VACUUM phải chạy như một utility command ngoài explicit transaction block. Một số migration frameworks tự bao câu lệnh trong transaction; cần cấu hình riêng.

### 25.4. VACUUM không rollback như DML thông thường

Đây là maintenance command có side effects không thể coi như một UPDATE có thể ROLLBACK để khôi phục nguyên trạng. Không chạy trong transaction để “thử xem”.

### 25.5. Quyền chạy VACUUM

Quyền yêu cầu phụ thuộc PostgreSQL version và relation: thường là table owner/superuser, còn các phiên bản mới có thể cung cấp quyền MAINTAIN. Kiểm tra quyền thực tế thay vì cấp superuser rộng.

## 26. VACUUM FULL và disk space

Một điểm quan trọng trước khi chạy FULL: trong quá trình rewrite, bảng cũ và bản mới cùng cần tồn tại.

~~~text
Trước:
  old heap + old indexes

Trong khi rewrite:
  old heap + old indexes
  new heap + new indexes

Sau khi hoàn tất:
  new heap + new indexes
  old files được giải phóng
~~~

### 26.1. Dung lượng cần thêm

Không gian tạm cần thiết phụ thuộc kích thước heap, indexes, TOAST, tablespaces và tiến trình cụ thể. Không dùng kích thước cuối cùng dự kiến làm giới hạn disk trống.

### 26.2. Tablespace

Nếu table/index ở tablespace riêng, dung lượng cần dự trù tại filesystem/volume tương ứng, không chỉ nhìn PGDATA.

### 26.3. Disk đầy giữa rewrite

Thiếu disk có thể làm lệnh thất bại, gây áp lực nghiêm trọng lên cluster và các workload khác. Kiểm tra cả temporary growth và WAL/storage impacts theo kiến trúc.

### 26.4. Index rebuild

VACUUM FULL rewrite relation và xây lại indexes liên quan; do đó có thể tiêu tốn thêm disk, CPU và I/O ngoài heap.

### 26.5. Lập kế hoạch theo worst case

Dùng staging/clone cùng kích thước, đo thời gian và peak disk consumption, dự trù tăng trưởng đồng thời và giữ khoảng trống an toàn.

## 27. VACUUM FULL có thay đổi physical identity của bảng không?

Vì FULL rewrite relation, file vật lý mới được tạo và thay thế file cũ. Các thông tin physical như relfilenode có thể thay đổi.

### 27.1. Đừng hard-code đường dẫn relation files

Không để ứng dụng hoặc script vận hành phụ thuộc tên file nội bộ trong `base/` hoặc `global/`. Dùng SQL/catalog và PostgreSQL-managed tools.

### 27.2. OID object và relfilenode không cùng khái niệm

OID nhận diện catalog object; relfilenode liên quan file storage hiện tại. Rewrite có thể thay file node mà object SQL vẫn là cùng table.

### 27.3. Logical references vẫn được quản lý

Indexes, constraints và dependencies được cập nhật theo thao tác rewrite. Client SQL không nên dựa vào file paths nội bộ.

### 27.4. Locks và prepared statements

VACUUM FULL chặn access trong lúc rewrite. PostgreSQL/driver quản lý plan invalidation và metadata theo cơ chế server; không tự lưu relation file identifiers bên ngoài.

### 27.5. Cần kiểm tra extension/tooling ngoài chuẩn

Các công cụ backup, monitoring hoặc extension đọc file vật lý cần tương thích với maintenance và catalog changes. Không can thiệp trực tiếp vào file table trong lúc rewrite.

## 41. Lab: quan sát progress và blockers

Mở một phiên để chạy lệnh bảo trì trên bảng lab đủ lớn:

~~~sql
VACUUM (VERBOSE) vacuum_lab.items;
~~~

Trong session khác, theo dõi:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
~~~

### 41.1. Theo dõi FULL

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation,
    command,
    phase,
    heap_blks_total,
    heap_blks_scanned
FROM pg_stat_progress_cluster;
~~~

VACUUM FULL có thể được báo qua progress view cho cluster/rewrite operations, tùy phiên bản.

### 41.2. Theo dõi lock

~~~sql
SELECT
    a.pid,
    a.state,
    l.mode,
    l.granted,
    a.wait_event_type,
    a.wait_event,
    now() - a.query_start AS elapsed
FROM pg_locks AS l
JOIN pg_stat_activity AS a USING (pid)
WHERE l.locktype = 'relation'
  AND l.relation = 'vacuum_lab.items'::regclass
ORDER BY l.granted, elapsed DESC;
~~~

### 41.3. Xem blocker

~~~sql
SELECT
    pid,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event,
    left(query, 120) AS query_sample
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
~~~

### 41.4. Chụp trạng thái ở nhiều thời điểm

Progress view là ảnh chụp trạng thái tại lúc query. Một lần query không có row có thể đơn giản là VACUUM đã kết thúc giữa hai lần kiểm tra.

### 41.5. Không chờ vô hạn trong lab

Nếu session bị block ngoài dự kiến, xem blocker và kết thúc transaction lab có chủ đích. Không dùng terminate trên hệ thống chia sẻ.

## 42. Chẩn đoán bloat: dùng nhiều tín hiệu

Bloat là dung lượng vật lý không còn hữu ích cho dữ liệu hiện tại hoặc không được sử dụng hiệu quả, nhưng không có một metric đơn giản nào luôn đo chính xác.

### 42.1. Tín hiệu từ pg_stat_user_tables

`n_dead_tup` giúp phát hiện dead tuple estimates, nhưng không bao quát toàn bộ free space, page density và index bloat.

### 42.2. Tín hiệu từ kích thước

Theo dõi `pg_relation_size`, `pg_indexes_size`, `pg_total_relation_size` qua thời gian. Một bảng tăng size có thể do dữ liệu hợp lệ tăng, không nhất thiết bloat.

### 42.3. Tín hiệu từ workload

Nếu bảng đã dọn nhưng vẫn tiếp tục tăng nhanh, kiểm tra UPDATE churn, DELETE pattern, fillfactor, index count và HOT update ratio.

### 42.4. Extension pgstattuple

`pgstattuple` có thể cung cấp thông tin chi tiết hơn về live/dead/free space trong relation, nhưng cần cài extension, quyền và có chi phí scan. Dùng có kiểm soát trên workload lớn.

### 42.5. Index bloat là một vấn đề riêng

Bảng heap compact không bảo đảm mọi indexes đều compact tối ưu. Đánh giá từng index và chọn REINDEX/maintenance tương ứng khi có bằng chứng.

## 43. Maintenance runbook cho VACUUM thường

Một runbook routine có thể gồm:

1. Chọn database/schema/table cần theo dõi.
2. Xem dead tuple estimates, size, last vacuum/analyze.
3. Kiểm tra transaction age, replication slots và blockers.
4. Xem autovacuum workers và tiến độ hiện tại.
5. Xác định có cần manual VACUUM hay chỉ ANALYZE.
6. Chọn giờ phù hợp nếu table có churn/I/O cao.
7. Chạy VACUUM thường với VERBOSE khi cần chẩn đoán.
8. Theo dõi progress, locks, I/O và application latency.
9. Kiểm tra lại stats và planner behavior.
10. Ghi lại kết quả, bất thường và thay đổi tuning.

### 43.1. Chạy lệnh tối thiểu

~~~sql
VACUUM sales.orders;
~~~

### 43.2. Khi cần cập nhật planner

~~~sql
VACUUM (ANALYZE) sales.orders;
~~~

### 43.3. Khi cần output chi tiết

~~~sql
VACUUM (VERBOSE, ANALYZE) sales.orders;
~~~

### 43.4. Không lên lịch FULL hằng đêm theo thói quen

Routine maintenance nên ưu tiên VACUUM/autovacuum thường. FULL chỉ chạy khi có mục tiêu reclaim và kế hoạch lock/disk.

### 43.5. Đánh giá sau lệnh

Nếu n_dead_tup giảm nhưng query latency không đổi, có thể query chậm vì index/plan/I/O khác. VACUUM không thay phân tích EXPLAIN.

## 44. Maintenance runbook cho VACUUM FULL

Trước khi chạy FULL:

- Xác nhận bảng thật sự có bloat/free space cần thu hồi.
- Ước tính peak disk usage, kể cả indexes/TOAST/tablespaces.
- Xác định thời gian rewrite bằng clone/staging tương đương.
- Kiểm tra transactions và sessions đang giữ lock.
- Kiểm tra application timeout, connection pool và retry behavior.
- Đặt maintenance window và thông báo owner.
- Xác nhận backup/restore point theo quy trình.
- Chuẩn bị cách hủy/rollback vận hành nếu lock không lấy được.
- Chạy trên đúng table/schema/database/host.
- Xác minh size, constraints, indexes và application health sau khi xong.

### 44.1. Câu lệnh

~~~sql
VACUUM FULL (VERBOSE, ANALYZE) sales.orders;
~~~

### 44.2. Không đặt timeout tùy tiện quá thấp

Nếu lock_timeout ngắn, FULL có thể liên tục thất bại trước khi bắt đầu. Nếu quá dài, một lock request có thể nằm trong queue và làm tăng blocking. Chọn theo maintenance plan.

### 44.3. Không chạy nhiều FULL đồng thời một cách mù quáng

Các rewrite cạnh tranh disk/CPU/I/O và cần nhiều temporary space. Một cluster có nhiều bảng lớn có thể phục hồi chậm hơn nếu tất cả FULL cùng lúc.

### 44.4. Không dùng CANCEL như một phương pháp điều khiển thông thường

Hủy một FULL đang chạy có thể làm rollback công việc rewrite và giữ tài nguyên trong quá trình cleanup. Tránh khởi động nếu chưa đủ điều kiện.

### 44.5. Sau FULL vẫn cần giám sát

Bảng compact không có nghĩa autovacuum có thể bị tắt. Workload mới tiếp tục tạo dead tuples và cần routine maintenance.

## 45. Các lỗi và hiểu lầm thường gặp

### 45.1. “VACUUM xóa hàng đã DELETE ngay khỏi file”

Sai. Nó thu hồi dead tuple versions khi an toàn; file vật lý thường vẫn giữ kích thước để tái sử dụng.

### 45.2. “VACUUM thường luôn trả disk về OS”

Sai. Chủ yếu reuse nội bộ; chỉ có thể truncate các pages trống ở cuối relation khi điều kiện phù hợp.

### 45.3. “VACUUM FULL chỉ là VACUUM mạnh hơn một chút”

Sai. Nó rewrite relation, rebuild indexes và cần ACCESS EXCLUSIVE.

### 45.4. “VACUUM thường không lấy lock”

Sai. Nó lấy SHARE UPDATE EXCLUSIVE; lock này tương thích với SELECT/DML thông thường nhưng xung đột với một số maintenance/DDL.

### 45.5. “VACUUM FULL chỉ chặn INSERT/UPDATE/DELETE”

Sai. ACCESS EXCLUSIVE xung đột cả ACCESS SHARE, nên SELECT cũng bị chặn.

### 45.6. “VACUUM FULL luôn chạy nhanh hơn vì dọn sạch hơn”

Sai. Rewrite và index rebuild thường tốn I/O, CPU và disk tạm.

### 45.7. “Chạy FULL không cần thêm dung lượng”

Sai. Old/new relation có thể cùng tồn tại trong lúc rewrite.

### 45.8. “n_dead_tup cao luôn chứng minh cần FULL”

Sai. Đây là estimate; cần xem tỷ lệ, kích thước, free space và mục tiêu reclaim.

### 45.9. “Autovacuum đã bật nghĩa mọi bảng được xử lý kịp”

Sai. Worker capacity, thresholds, locks, I/O và xmin horizon có thể làm nó trễ.

### 45.10. “Tắt autovacuum sẽ tránh CPU overhead an toàn”

Sai. Có thể gây bloat, planner stats cũ và nguy cơ XID wraparound.

### 45.11. “VACUUM FULL thay autovacuum”

Sai. FULL là thao tác rewrite có lock mạnh; routine autovacuum vẫn cần chạy để duy trì bảng sau đó.

### 45.12. “ANALYZE dọn dead tuples”

Sai. ANALYZE thu thập planner statistics; VACUUM cleanup tuple versions.

### 45.13. “Một transaction idle không ảnh hưởng VACUUM”

Sai. Idle in transaction có thể giữ snapshot và cleanup horizon cũ.

### 45.14. “Replica sẽ luôn giải phóng tuples trên primary”

Sai. Replication slots và hot_standby_feedback có thể giữ xmin/catalog_xmin.

### 45.15. “Tăng autovacuum workers giải quyết mọi lag”

Sai. Nó không giải quyết transaction horizon bị giữ, lock blocker hoặc storage bottleneck.

### 45.16. “Kill PID đang chờ sẽ giải phóng blocker”

Sai. Phải tìm root blocker; terminate waiter không kết thúc transaction giữ lock.

### 45.17. “pg_stat_progress_vacuum luôn hiển thị VACUUM FULL”

Sai. FULL được báo ở progress view của cluster/rewrite operation trong các phiên bản hỗ trợ.

### 45.18. “pg_relation_size là toàn bộ dung lượng bảng”

Sai. Indexes và TOAST có thể làm total size lớn hơn heap size.

### 45.19. “VACUUM FULL sửa mọi index bloat trên database”

Sai. Nó tác động tới indexes của relation được rewrite, không phải mọi indexes trong cluster.

### 45.20. “CLUSTER/pg_repack không cần lock”

Sai. Chúng có trade-offs và các giai đoạn lock riêng.

### 45.21. “Partition cũ phải DELETE từng row”

Sai. Với retention theo thời gian, partition detach/drop có thể hiệu quả hơn nếu schema/dependencies cho phép.

### 45.22. “VACUUM có thể chạy trong transaction block”

Sai. Utility command VACUUM phải chạy ngoài explicit transaction block.

### 45.23. “VACUUM có thể ROLLBACK để trở lại trạng thái cũ”

Sai. Đừng xem maintenance như một DML transaction thông thường có thể rollback để đảo ngược cleanup.

### 45.24. “VACUUM FULL là cách xử lý wraparound mặc định”

Sai. Freeze/anti-wraparound được quản lý bởi VACUUM và autovacuum; FULL không phải yêu cầu routine.

### 45.25. “Bảng ít UPDATE/DELETE không cần VACUUM”

Sai. Freeze/XID age và visibility map vẫn quan trọng.

### 45.26. “Nếu VACUUM chạy không có output thì không làm gì”

Sai. Không có VERBOSE không có nghĩa lệnh không thực hiện cleanup; xem stats/progress/logs.

### 45.27. “Một lần VACUUM sẽ dọn sạch mọi dead tuples”

Sai. Tuples còn được snapshot giữ lại chưa thể thu hồi; workload tiếp tục tạo dead tuples.

### 45.28. “Tắt truncate là tắt VACUUM”

Sai. TRUNCATE FALSE chỉ bỏ bước truncation pages cuối file theo option hỗ trợ; cleanup và reuse vẫn diễn ra.

### 45.29. “Sau FULL có thể tắt maintenance”

Sai. Các DML mới tiếp tục tạo tuple versions và cần autovacuum.

### 45.30. “VACUUM làm bảng nhỏ hơn thì chắc chắn query nhanh hơn”

Sai. Query plan, indexes, cache, I/O và selectivity mới quyết định performance; VACUUM có thể cải thiện một số đường truy cập nhưng không bảo đảm.

## 46. Bài tập thực hành

### Bài 1 — MVCC

Vì sao PostgreSQL không xóa ngay tuple cũ khi UPDATE?

**Gợi ý:** Transaction snapshot cũ có thể còn cần nhìn thấy version đó.

### Bài 2 — Dead tuple

Một tuple version trở thành dead khi nào?

**Đáp án:** Khi không còn snapshot/transaction nào có thể cần nó.

### Bài 3 — VACUUM

Mục tiêu chính của VACUUM thường là gì?

**Gợi ý:** Thu hồi dead tuple versions, cập nhật free space/visibility và freeze.

### Bài 4 — VACUUM FULL

Khác biệt cốt lõi về cách lưu trữ?

**Đáp án:** Rewrite relation và compact file.

### Bài 5 — Disk reuse

Vì sao VACUUM thường chạy xong nhưng file vẫn lớn?

**Gợi ý:** Free space được giữ trong relation để reuse.

### Bài 6 — OS reclaim

VACUUM thường có thể trả OS một phần space trong trường hợp nào?

**Gợi ý:** Truncation các pages hoàn toàn trống ở cuối relation.

### Bài 7 — Lock thường

Lock chính của VACUUM thường là gì?

**Đáp án:** SHARE UPDATE EXCLUSIVE.

### Bài 8 — Lock FULL

Lock của VACUUM FULL là gì?

**Đáp án:** ACCESS EXCLUSIVE.

### Bài 9 — SELECT

SELECT thông thường có thể chạy đồng thời với VACUUM thường không?

**Đáp án:** Thường có; ACCESS SHARE tương thích với SHARE UPDATE EXCLUSIVE.

### Bài 10 — DML

INSERT/UPDATE/DELETE thông thường có thể chạy với VACUUM thường không?

**Đáp án:** Thường có; ROW EXCLUSIVE tương thích với SHARE UPDATE EXCLUSIVE.

### Bài 11 — FULL và SELECT

Vì sao VACUUM FULL chặn SELECT?

**Gợi ý:** ACCESS EXCLUSIVE xung đột ACCESS SHARE.

### Bài 12 — Lock queue

VACUUM FULL đang đợi lock có thể ảnh hưởng query mới thế nào?

**Gợi ý:** Lock requests có thể xếp hàng phía sau lock mạnh đang chờ.

### Bài 13 — Transaction lâu

Một transaction idle in transaction có thể gây vấn đề gì?

**Đáp án:** Giữ snapshot/xmin horizon, ngăn cleanup.

### Bài 14 — Replication slot

Slot có xmin/catalog_xmin có thể tác động VACUUM thế nào?

**Gợi ý:** Giữ tuple/catalog versions cần cho consumer.

### Bài 15 — Hot standby feedback

Cấu hình này có thể đánh đổi điều gì?

**Gợi ý:** Giảm query conflicts trên standby nhưng có thể tăng bloat primary.

### Bài 16 — ANALYZE

ANALYZE làm gì?

**Đáp án:** Cập nhật planner statistics.

### Bài 17 — VACUUM ANALYZE

Câu lệnh nào chạy cả hai?

**Đáp án:** `VACUUM (ANALYZE) schema.table;`.

### Bài 18 — FREEZE

VACUUM FREEZE giúp bảo vệ điều gì?

**Gợi ý:** XID wraparound.

### Bài 19 — Autovacuum

Autovacuum thường quyết định chạy dựa vào gì?

**Gợi ý:** Dead tuple/change thresholds, insert activity và XID age.

### Bài 20 — Threshold formula

Viết công thức vacuum threshold cơ bản.

**Đáp án:** `autovacuum_vacuum_threshold + autovacuum_vacuum_scale_factor * estimated_table_tuples`.

### Bài 21 — Scale factor

Vì sao bảng rất lớn có thể cần scale factor thấp hơn?

**Gợi ý:** Ngưỡng dead tuples tuyệt đối mặc định có thể quá lớn.

### Bài 22 — Per-table options

Lệnh nào đặt autovacuum scale factor cho một bảng?

**Gợi ý:** ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = ...).

### Bài 23 — Worker tuning

Tăng autovacuum_max_workers có thể gây trade-off gì?

**Gợi ý:** Nhiều table xử lý song song hơn nhưng thêm CPU/RAM/I/O.

### Bài 24 — Wraparound

Vì sao database ít writes vẫn cần freeze?

**Đáp án:** Tuổi XID vẫn tăng và cần bảo vệ tuple visibility.

### Bài 25 — n_dead_tup

Đây có phải phép đếm dead tuples chính xác tức thời không?

**Đáp án:** Không, là estimate.

### Bài 26 — Size

Hàm nào xem heap size của table?

**Đáp án:** `pg_relation_size`.

### Bài 27 — Total size

Hàm nào bao gồm indexes/TOAST liên quan?

**Đáp án:** `pg_total_relation_size`.

### Bài 28 — Progress thường

View nào quan sát VACUUM thường?

**Đáp án:** `pg_stat_progress_vacuum`.

### Bài 29 — Progress FULL

View nào có thể báo VACUUM FULL rewrite progress?

**Đáp án:** `pg_stat_progress_cluster` trong các phiên bản hỗ trợ.

### Bài 30 — Locks

View nào xem lock grants/waits?

**Đáp án:** `pg_locks`.

### Bài 31 — Blockers

Function nào tìm backend đang block PID?

**Đáp án:** `pg_blocking_pids(pid)`.

### Bài 32 — XID age

Cách xem database nào có datfrozenxid age cao?

**Gợi ý:** Query pg_database và age(datfrozenxid).

### Bài 33 — VACUUM FULL disk

Vì sao cần disk trống bổ sung?

**Gợi ý:** Old/new relation và indexes cùng tồn tại trong rewrite.

### Bài 34 — pg_repack

Có phải công cụ này hoàn toàn không cần lock không?

**Đáp án:** Không; có các giai đoạn lock và requirements riêng.

### Bài 35 — Partition retention

Vì sao DROP partition có thể tốt hơn DELETE hàng triệu rows?

**Gợi ý:** Loại bỏ relation/partition theo phạm vi lớn, tránh row churn.

### Bài 36 — Transaction block

Có thể chạy VACUUM bên trong BEGIN/COMMIT không?

**Đáp án:** Không.

### Bài 37 — VACUUM FULL routine

Có nên chạy VACUUM FULL mỗi đêm trên mọi bảng không?

**Đáp án:** Không; đánh giá bloat, lock, disk và nhu cầu.

### Bài 38 — Lab lock

Một transaction A mở SELECT nhưng chưa COMMIT. VACUUM FULL ở B có lấy ACCESS EXCLUSIVE ngay được không?

**Đáp án:** Không; phải chờ A nhả ACCESS SHARE.

### Bài 39 — Lab thường

Cùng transaction A mở SELECT, VACUUM thường ở B có thể chạy không?

**Đáp án:** Thường có, vì lock modes tương thích, nếu không có blocker khác.

### Bài 40 — Chọn giải pháp

Một bảng lớn có free space rải rác, cần trả disk cho OS, traffic không thể dừng và không có maintenance window. Bạn sẽ làm gì?

**Gợi ý:** Không chạy VACUUM FULL tùy tiện; xử lý nguyên nhân bloat, cân nhắc pg_repack/partitioning theo compatibility và kế hoạch lock/disk, sau đó diễn tập.

## 47. Checklist trước khi chạy VACUUM thường

- [ ] Đã chọn đúng database/schema/table?
- [ ] Đã xem last_vacuum/last_autovacuum và stats?
- [ ] Có transaction lâu hoặc xmin horizon giữ tuples?
- [ ] Có autovacuum đang xử lý cùng relation?
- [ ] Có DDL/maintenance đang giữ lock xung đột?
- [ ] Workload và I/O hiện tại có đủ headroom?
- [ ] Có cần ANALYZE cùng lúc?
- [ ] Có cần VERBOSE/progress monitoring?
- [ ] Có cần tránh tail truncation lock ngắn theo option version hỗ trợ?
- [ ] Đã có baseline để so sánh sau lệnh?

## 48. Checklist trước khi chạy VACUUM FULL

- [ ] Có bằng chứng bloat/free space đáng kể?
- [ ] Mục tiêu là trả disk về OS hay chỉ reuse nội bộ?
- [ ] Đã cân nhắc partition lifecycle/pg_repack/CLUSTER/REINDEX?
- [ ] Đã đo table, indexes và TOAST size?
- [ ] Đã xác minh disk trống ở tablespaces và volume liên quan?
- [ ] Có maintenance window phù hợp?
- [ ] Đã xác định blockers và transaction age?
- [ ] Đã đánh giá tác động ACCESS EXCLUSIVE tới SELECT/DML?
- [ ] Connection pools/timeouts/retries có phù hợp?
- [ ] Đã kiểm tra backup/recovery plan?
- [ ] Có người theo dõi progress, locks, disk, I/O và application latency?
- [ ] Có kế hoạch xác minh sau rewrite?

## 49. Bảng tra cứu nhanh

| Khái niệm | Ghi nhớ |
|---|---|
| MVCC | Nhiều tuple versions phục vụ snapshots |
| Dead tuple | Version không còn cần cho snapshot hiện tại/tương lai |
| VACUUM | Cleanup, free space reuse, visibility map và freeze |
| VACUUM FULL | Rewrite/compact relation, rebuild indexes |
| SHARE UPDATE EXCLUSIVE | Lock chính của VACUUM thường |
| ACCESS EXCLUSIVE | Lock của VACUUM FULL |
| ACCESS SHARE | Lock thường của SELECT |
| ROW EXCLUSIVE | Lock thường của INSERT/UPDATE/DELETE |
| Free space map | Gợi ý pages có chỗ trống để reuse |
| Visibility map | All-visible/all-frozen page metadata |
| ANALYZE | Cập nhật planner statistics |
| FREEZE | Bảo vệ tuple visibility trước XID wraparound |
| Autovacuum | VACUUM/ANALYZE nền theo thresholds và XID age |
| Scale factor | Ngưỡng thay đổi theo quy mô bảng |
| n_dead_tup | Ước lượng dead tuples |
| pg_stat_user_tables | Vacuum/analyze history và tuple estimates |
| pg_stat_progress_vacuum | Tiến độ VACUUM thường |
| pg_stat_progress_cluster | Progress rewrite/CLUSTER và VACUUM FULL theo version |
| pg_locks | Lock grants và waiters |
| pg_blocking_pids | Tìm backend blockers |
| backend_xmin | Snapshot horizon backend giữ |
| Replication slot xmin | Có thể trì hoãn tuple cleanup |
| hot_standby_feedback | Có thể giữ xmin trên primary |
| VACUUM FULL disk | Cần extra space cho rewrite |
| pg_repack | Công cụ rewrite online-ish với trade-offs |
| CLUSTER | Rewrite theo thứ tự index, lock mạnh |
| REINDEX | Rebuild indexes |
| Partition detach/drop | Retention theo relation thay mass DELETE |
| XID age | Metric theo dõi wraparound risk |

## 50. Kết luận

**VACUUM thường và VACUUM FULL phục vụ hai mục tiêu khác nhau.** VACUUM thường thu hồi dead tuple versions, cập nhật free space/visibility metadata và freeze các tuple cần thiết; nó chủ yếu làm dung lượng có thể tái sử dụng bên trong relation, thường không làm file nhỏ đi đáng kể. Nó dùng SHARE UPDATE EXCLUSIVE nên tương thích với SELECT và DML thông thường, dù vẫn có thể gây I/O contention hoặc xung đột với DDL/maintenance khác. Bước truncate các pages trống ở cuối file có thể cần ACCESS EXCLUSIVE lock ngắn và có thể được điều khiển bằng tùy chọn phù hợp phiên bản.

**VACUUM FULL rewrite toàn bộ relation và indexes để compact, thường trả dung lượng về filesystem, nhưng cần ACCESS EXCLUSIVE trong suốt thao tác.** Điều này chặn SELECT/INSERT/UPDATE/DELETE trên bảng và cần thêm disk trong lúc old/new files cùng tồn tại. Vì vậy FULL chỉ nên chạy khi có mục tiêu reclaim rõ, đã đo bloat, đủ dung lượng và có maintenance window/biện pháp kiểm soát traffic.

Autovacuum là cơ chế routine quan trọng, không phải thứ nên tắt để né I/O. Nếu vacuum không thu hồi được tuples, hãy tìm transaction lâu, idle-in-transaction sessions, prepared transactions, replication slots và standby feedback trước khi tăng workers hoặc chạy FULL. Theo dõi n_dead_tup cùng relation sizes, XID age, progress views và pg_locks để hiểu nguyên nhân thay vì đoán từ một metric.

Nguyên tắc vận hành: **dùng VACUUM thường cho cleanup và reuse định kỳ; dùng VACUUM FULL khi thực sự cần rewrite để trả disk và chấp nhận lock độc quyền; luôn xử lý nguyên nhân bloat, theo dõi autovacuum/freeze và kiểm tra blockers trước khi bảo trì.**


## 29. VACUUM thường không phải lúc nào cũng giảm file size

Sau khi VACUUM thường hoàn tất, kiểm tra:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('sales.orders')) AS heap_size,
    pg_size_pretty(pg_total_relation_size('sales.orders')) AS total_size;
~~~

### 29.1. Free space có thể được dùng lại

Một INSERT tiếp theo có thể dùng lại các pages có chỗ trống. Vì thế file vẫn lớn nhưng table không nhất thiết còn “đầy dead tuples”.

### 29.2. Free space không giống bloat

Free pages trong relation có thể là dung lượng hữu ích để hấp thụ workload sắp tới. Không phải mọi free space đều là lãng phí cần loại bỏ.

### 29.3. Đo trước/sau không chỉ nhìn filesystem

Ghi nhận heap size, index size, total relation size, dead tuple estimates, throughput và latency. Dữ liệu cần so sánh cùng điều kiện workload.

### 29.4. VACUUM FULL không đảm bảo luôn giảm nhiều

Nếu bảng đã compact hoặc free space ít, rewrite có thể tốn thời gian/disk mà lợi ích nhỏ.

### 29.5. Đừng chạy FULL để “làm đẹp” dashboard

Chỉ chạy khi có mục tiêu reclaim disk/compact cụ thể và đã hiểu lock, peak disk và tác động.

## 30. Freeze và visibility map trong vận hành

Ngoài cleanup, VACUUM duy trì metadata quan trọng cho hiệu năng đọc và an toàn XID.

### 30.1. All-visible pages

Visibility map đánh dấu pages mà mọi tuples được coi là visible đối với mọi transaction hiện tại. Index-only scans có thể dùng thông tin này để tránh truy cập heap trong những trường hợp phù hợp.

### 30.2. All-frozen pages

Một page được đánh dấu all-frozen khi các tuple trên page đã được freeze theo điều kiện tương ứng. Điều này giúp các lần vacuum sau có thể bỏ qua một số pages an toàn.

### 30.3. DML làm mất trạng thái visibility

UPDATE/INSERT trên page có thể làm visibility information cần được cập nhật lại. VACUUM sau đó xác định trạng thái mới.

### 30.4. VACUUM không phải chỉ để xóa dead rows

Ngay cả bảng ít bloat vẫn cần vacuum/freeze định kỳ để duy trì visibility map và ngăn XID wraparound.

### 30.5. VACUUM FULL không phải chiến lược freeze duy nhất

Freeze behavior được điều khiển bởi các vacuum options và XID age; không cần rewrite toàn bộ bảng chỉ để bảo đảm tuple freezing.

## 31. Kiểm tra tuổi XID và rủi ro wraparound

Tuổi XID theo database:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

Tuổi XID theo relation:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 30;
~~~

### 31.1. XID age không phải số transactions còn lại chính xác

Đây là một metric để theo dõi độ cũ tương đối của frozen horizon. Đọc cùng cấu hình wraparound và cảnh báo server.

### 31.2. Xem database nguy cơ cao nhất

Database có age lớn nhất cần được điều tra, nhưng cũng phải xem relation cũ nhất, vacuum history và worker activity.

### 31.3. Freeze settings

Các tham số như `vacuum_freeze_min_age`, `vacuum_freeze_table_age` và `autovacuum_freeze_max_age` ảnh hưởng hành vi freeze. Đừng thay đổi chúng chỉ dựa trên một blog hoặc một con số đơn lẻ.

### 31.4. Không bỏ qua database ít traffic

Database ít ghi có thể vẫn cần vacuum freeze để ngăn XID age tăng. “Ít dead tuples” không đồng nghĩa “không cần vacuum”.

### 31.5. Anti-wraparound là tình huống ưu tiên cao

Khi server tiến gần giới hạn an toàn, PostgreSQL có thể khởi chạy aggressive autovacuum và cảnh báo. Không trì hoãn hoặc kill các worker này tùy tiện.

## 32. Partitioned tables và VACUUM

Partitioning tạo một parent table logic và nhiều leaf partitions có storage riêng.

~~~text
sales.events (partitioned parent)
       |
       +-- events_2026_01 (heap)
       +-- events_2026_02 (heap)
       +-- events_2026_03 (heap)
~~~

### 32.1. Dead tuples nằm ở partitions

Các leaf partitions là những relations lưu rows. Autovacuum xử lý các partitions dựa trên hoạt động của từng relation.

### 32.2. Parent table có thống kê riêng

Autovacuum không tự cập nhật statistics cho partitioned parent theo cùng cách nó xử lý leaf tables trong một số phiên bản; khi cần planner statistics toàn parent, hãy chạy ANALYZE phù hợp trên parent theo tài liệu phiên bản.

### 32.3. VACUUM parent và leaf

Một lệnh VACUUM trên partitioned table có thể áp dụng cho các partitions theo semantics PostgreSQL; nếu vận hành theo từng partition, xác định rõ đối tượng và xem tiến độ từng relation.

### 32.4. Retention bằng detach/drop partition

Nếu business cho phép bỏ dữ liệu theo tháng, detach/drop partition cũ có thể tránh hàng triệu DELETE và giảm nhu cầu VACUUM trên từng row. Nhưng thao tác DDL này vẫn có lock, foreign keys, dependencies và archive requirements.

### 32.5. Không chạy FULL trên tất cả partitions theo lịch mù

Đánh giá kích thước, churn và disk riêng của từng partition. Một partition immutable không cần cùng chiến lược với partition đang ghi liên tục.

## 33. Những lựa chọn khác ngoài VACUUM FULL

### 33.1. Sửa nguyên nhân gây bloat

Nếu một transaction kéo dài, replication slot bị bỏ quên hoặc autovacuum threshold không phù hợp, xử lý nguyên nhân trước khi rewrite. Nếu không, bloat có thể tái diễn ngay.

### 33.2. Partition rotation

Với dữ liệu hết hạn theo khoảng thời gian, drop/detach partition có thể là cách loại bỏ lượng dữ liệu lớn hiệu quả hơn row-by-row DELETE.

### 33.3. pg_repack

Có thể phù hợp khi muốn rewrite table/index với thời gian giữ lock mạnh ngắn hơn VACUUM FULL, nhưng cần extension/tool tương thích, trigger/log table, dung lượng tạm và kiểm tra vận hành.

### 33.4. CLUSTER

Dùng khi cần tổ chức vật lý rows theo thứ tự index. CLUSTER cũng rewrite table và cần lock mạnh; nó không phải giải pháp online không downtime.

### 33.5. REINDEX

Nếu vấn đề chính là index bloat, đánh giá REINDEX thường/CONCURRENTLY theo index và version. Không giả định VACUUM FULL là lựa chọn duy nhất.

### 33.6. Fillfactor và HOT updates

Điều chỉnh fillfactor có thể để lại khoảng trống page cho HOT updates, giảm index churn trong workload phù hợp. Nó là quyết định thiết kế/tuning, không thay vacuum và không tự compact bảng hiện tại.

## 34. Các lệnh VACUUM thường dùng

~~~sql
-- Dọn một bảng
VACUUM sales.orders;

-- Dọn và cập nhật planner statistics
VACUUM (ANALYZE) sales.orders;

-- Xem chi tiết quá trình
VACUUM (VERBOSE) sales.orders;

-- Dọn, freeze và hiển thị thông tin
VACUUM (FREEZE, VERBOSE) sales.orders;

-- Compact bằng rewrite, khóa độc quyền
VACUUM FULL sales.orders;

-- FULL đồng thời cập nhật statistics
VACUUM (FULL, ANALYZE, VERBOSE) sales.orders;
~~~

### 34.1. Không chạy trong BEGIN/COMMIT

Các lệnh VACUUM phải chạy ngoài explicit transaction block. Một migration tool tự bọc mọi statements trong transaction có thể cần chế độ riêng.

### 34.2. VACUUM không có table name

`VACUUM;` có thể vacuum tất cả tables đủ điều kiện trong database hiện tại. Đây là thao tác rộng, cần xem scope và thời gian trước khi chạy thủ công.

### 34.3. VACUUM FULL không phải option ANALYZE

`FULL` thay đổi cách relation được rewrite; `ANALYZE` yêu cầu cập nhật planner stats. Hai options có mục tiêu khác nhau và có thể kết hợp khi thích hợp.

### 34.4. VACUUM không xóa rows còn sống

Nếu muốn xóa dữ liệu nghiệp vụ, dùng DELETE/TRUNCATE/partition retention theo yêu cầu; VACUUM chỉ thu hồi versions đã hết vòng đời.

### 34.5. Tham khảo vacuumdb

Tool dòng lệnh `vacuumdb` có thể chạy VACUUM/ANALYZE trên databases/tables từ script vận hành. Options tương ứng phụ thuộc version; không chạy nhầm database/host chỉ vì cron job cũ.

## 35. Lab: tạo dead tuples

**Môi trường:** database thử nghiệm riêng và role có quyền tạo schema/table. Không chạy thao tác mass UPDATE/DELETE trên production để minh họa.

~~~sql
CREATE SCHEMA vacuum_lab;

CREATE TABLE vacuum_lab.items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO vacuum_lab.items(payload)
SELECT repeat('x', 500)
FROM generate_series(1, 100000);
~~~

### 35.1. Xem số rows ban đầu

~~~sql
SELECT count(*) FROM vacuum_lab.items;
~~~

### 35.2. UPDATE tạo phiên bản mới

~~~sql
UPDATE vacuum_lab.items
SET payload = repeat('y', 500),
    updated_at = now()
WHERE id % 2 = 0;
~~~

### 35.3. DELETE đánh dấu rows

~~~sql
DELETE FROM vacuum_lab.items
WHERE id % 5 = 0;
~~~

### 35.4. Thống kê dead tuples là estimate

Sau khi statistics được cập nhật, kiểm tra:

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_vacuum
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_lab';
~~~

Nếu autovacuum xử lý quá nhanh trong lab, số ước lượng có thể nhỏ hơn dự đoán. Có thể tạm điều chỉnh thresholds trên bảng lab để quan sát, rồi khôi phục settings sau thực hành.

### 35.5. Đo size trước VACUUM

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total;
~~~

Ghi lại số liệu; không cần kỳ vọng size chính xác như một máy khác vì storage, page layout và phiên bản khác nhau.

## 36. Lab: chạy VACUUM thường

~~~sql
VACUUM (VERBOSE, ANALYZE) vacuum_lab.items;
~~~

### 36.1. Kiểm tra lại thống kê

~~~sql
SELECT
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_analyze
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_lab'
  AND relname = 'items';
~~~

### 36.2. Đọc VERBOSE

Output có thể mô tả số pages, dead tuples, index cleanup và các hoạt động liên quan. Chi tiết output thay đổi theo phiên bản.

### 36.3. Đo size sau VACUUM

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total;
~~~

File có thể không giảm nhiều vì phần lớn space đã được đánh dấu reusable bên trong relation. Đây là kết quả bình thường.

### 36.4. Thử INSERT thêm

~~~sql
INSERT INTO vacuum_lab.items(payload)
SELECT repeat('z', 500)
FROM generate_series(1, 10000);
~~~

VACUUM đã tạo cơ hội tái sử dụng free space. Không nhất thiết database phải xin thêm disk tương ứng cho mọi rows mới, dù thực tế phụ thuộc page layout và mức trống.

### 36.5. Kiểm tra planner statistics

`ANALYZE` trong lệnh trên cập nhật thống kê. Đây là lý do query planner có thể thay đổi kế hoạch sau lệnh, độc lập với việc file size có giảm hay không.

## 37. Lab: so sánh VACUUM thường và VACUUM FULL

Để thấy khác biệt, thực hiện trên một bảng lab đủ lớn và có nhiều dead space. Ghi lại heap/total size, thời gian, lock wait và disk free trước/sau.

~~~sql
VACUUM (VERBOSE) vacuum_lab.items;

SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap_size,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total_size;

VACUUM FULL (VERBOSE, ANALYZE) vacuum_lab.items;

SELECT
    pg_size_pretty(pg_relation_size('vacuum_lab.items')) AS heap_size,
    pg_size_pretty(pg_total_relation_size('vacuum_lab.items')) AS total_size;
~~~

### 37.1. Kết quả kỳ vọng

VACUUM thường chủ yếu đánh dấu free space reusable; VACUUM FULL rewrite để compact, nên file thường nhỏ hơn nếu trước đó có nhiều bloat.

### 37.2. Không kỳ vọng con số cố định

Kích thước phụ thuộc payload, fillfactor, indexes, TOAST, compression, page layout và autovacuum. Điều cần học là cơ chế và trade-offs, không phải một con số byte cố định.

### 37.3. VACUUM FULL cần disk tạm

Trước khi chạy, xem disk capacity và giữ buffer an toàn. Lab nhỏ không phản ánh peak disk của production.

### 37.4. So sánh thời gian

Ghi thời gian thực hiện và quan sát progress. FULL có thể tốn hơn do rewrite và index rebuild.

### 37.5. FULL làm block traffic trên bảng

Không chạy test trên bảng ứng dụng thật đang có người dùng. Dùng session thứ hai để quan sát lock trong lab.

## 38. Lab hai session: VACUUM thường và SELECT/DML

Mở hai terminal/psql sessions tới cùng database lab.

**Session A:**

~~~sql
BEGIN;
SELECT count(*) FROM vacuum_lab.items;
-- Giữ transaction mở để giữ relation lock.
~~~

**Session B:**

~~~sql
VACUUM (VERBOSE) vacuum_lab.items;
~~~

VACUUM thường có thể lấy SHARE UPDATE EXCLUSIVE tương thích với ACCESS SHARE từ SELECT đang chạy trong Session A. Nó có thể hoàn tất dù transaction A còn mở, tùy các điều kiện khác.

### 38.1. Thử DML đồng thời

Trong khi VACUUM đang chạy ở Session B, chạy một UPDATE nhỏ từ Session C. SHARE UPDATE EXCLUSIVE của VACUUM tương thích với ROW EXCLUSIVE của DML thông thường.

### 38.2. Kết thúc Session A

~~~sql
COMMIT;
~~~

Đừng quên kết thúc transaction sau lab; session mở lâu có thể giữ snapshot và ảnh hưởng cleanup.

### 38.3. Quan sát lock

Trong session thứ ba, chạy query từ phần pg_locks để xem relation lock modes và trạng thái granted.

### 38.4. Kết quả không có nghĩa VACUUM không ảnh hưởng latency

Nó vẫn cạnh tranh CPU/I/O, có thể tăng latency của workload và có thể chờ DDL/maintenance.

## 39. Lab hai session: VACUUM FULL và ACCESS EXCLUSIVE

Dùng bảng lab. Chỉ thực hành trong database cô lập.

**Session A:**

~~~sql
BEGIN;
SELECT count(*) FROM vacuum_lab.items;
-- Chưa COMMIT.
~~~

**Session B:**

~~~sql
SET lock_timeout = '5s';
VACUUM FULL vacuum_lab.items;
~~~

### 39.1. Kỳ vọng

VACUUM FULL cần ACCESS EXCLUSIVE nên phải chờ transaction A nhả ACCESS SHARE. Với lock_timeout ngắn, lệnh có thể thất bại vì không lấy được lock trong thời gian cho phép.

### 39.2. Giải phóng lock

Trong Session A:

~~~sql
COMMIT;
~~~

Sau đó có thể thử lại VACUUM FULL trên lab khi đã xác định không còn blocker.

### 39.3. Thử SELECT mới khi FULL giữ lock

Khi FULL đang rewrite, một SELECT từ Session C có thể bị block cho đến khi FULL hoàn tất. Quan sát wait events/locks và dừng thử khi lab đã đủ dữ liệu.

### 39.4. Không kết thúc blocker trên production tùy tiện

Nếu transaction A là một giao dịch nghiệp vụ, terminate có thể rollback công việc và gây retry. Cần incident/maintenance plan.

### 39.5. Hiểu queue

Một ACCESS EXCLUSIVE đang chờ có thể làm các lock requests mới bị xếp hàng phía sau tùy lock queue. Vì vậy FULL chưa bắt đầu rewrite vẫn có thể tạo ảnh hưởng.

## 40. Lab: kiểm tra autovacuum và freeze

Xem các setting hiện hành:

~~~sql
SHOW autovacuum;
SHOW autovacuum_naptime;
SHOW autovacuum_max_workers;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_freeze_max_age;
~~~

### 40.1. Xem tuổi XID theo database

~~~sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

### 40.2. Xem vacuum history

~~~sql
SELECT
    schemaname,
    relname,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'vacuum_lab';
~~~

### 40.3. Không cần ép wraparound trong lab

Không cố tạo hàng tỷ transactions hoặc giảm freeze thresholds nguy hiểm để mô phỏng wraparound. Hãy đọc metrics và hiểu cơ chế trên database thử nghiệm.

### 40.4. Thử per-table thresholds

Có thể đặt thresholds thấp trên bảng lab để thấy autovacuum được kích hoạt sớm hơn, nhưng cần quan sát logs và khôi phục reloptions sau khi xong.

### 40.5. Phân biệt autovacuum với manual VACUUM

Các cột last_autovacuum và last_vacuum giúp biết lần gần nhất đến từ background worker hay lệnh thủ công.


## 28. Khi nào nên cân nhắc pg_repack hoặc CLUSTER?

### 28.1. CLUSTER

`CLUSTER` rewrite table theo thứ tự index được chọn và yêu cầu ACCESS EXCLUSIVE lock trong quá trình thao tác. Nó có thể sắp xếp lại dữ liệu vật lý, không chỉ compact.

### 28.2. pg_repack

`pg_repack` là extension/tool bên ngoài có thể tái tổ chức bảng với thời gian giữ lock mạnh ngắn hơn trong một số trường hợp, bằng cách theo dõi thay đổi và đồng bộ. Nó có yêu cầu vận hành, quyền, dung lượng tạm và compatibility riêng.

### 28.3. Không có phương án “zero lock”

Ngay cả công cụ online rewrite cũng cần các giai đoạn lock để chuẩn bị/chuyển đổi. Cần đọc tài liệu extension đúng version, kiểm tra conflicts và kế hoạch rollback.

### 28.4. REINDEX là thao tác riêng

Nếu index bloat/hỏng là vấn đề, xem `REINDEX` theo mục tiêu. VACUUM thường cleanup dead index entries; VACUUM FULL rebuild indexes cùng rewrite; không phải mọi vấn đề index đều cần FULL table.

### 28.5. Partition lifecycle có thể tốt hơn mass DELETE

Với dữ liệu theo tháng/ngày, drop/detach partition cũ có thể hiệu quả hơn DELETE hàng triệu rows rồi VACUUM FULL. Nhưng partition detach/drop cũng có locks, constraints và dependencies cần tính toán.






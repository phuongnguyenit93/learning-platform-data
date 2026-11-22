# Xây dựng lại chỉ mục: lợi ích, chi phí và điều kiện thực hiện trực tuyến

## 1. Vì sao cần xây dựng lại chỉ mục?

Chỉ mục giúp hệ quản trị cơ sở dữ liệu tìm hàng mà không phải quét toàn bộ bảng. Theo thời gian, thao tác INSERT, UPDATE, DELETE, thay đổi kích thước hàng và phân bố khóa có thể làm cấu trúc chỉ mục kém gọn: các trang lá không còn được sắp xếp gần nhau theo thứ tự khóa, mật độ trang giảm, xuất hiện khoảng trống hoặc nhiều phiên bản dữ liệu không còn cần thiết. Với một số workload, điều này làm tăng số trang phải đọc, giảm hiệu quả read-ahead, tăng cache footprint và kéo dài truy vấn.

Xây dựng lại chỉ mục (index rebuild) tạo lại cấu trúc chỉ mục từ dữ liệu hiện có. Công việc có thể sắp xếp lại các trang, loại bỏ khoảng trống không cần thiết, cải thiện page density và cập nhật một phần thống kê liên quan tùy hệ quản trị. Tuy nhiên, rebuild cũng tiêu thụ CPU, I/O, dung lượng tạm và transaction log; nó có thể cạnh tranh với truy vấn trực tuyến, gây lock hoặc làm replica lag tăng.

Trong tối ưu hiệu năng cơ sở dữ liệu, quyết định rebuild phải dựa trên bằng chứng từ workload và execution plan. Một chỉ mục có fragmentation cao trên báo cáo chưa chắc là nút thắt; một chỉ mục ít phân mảnh nhưng quá rộng hoặc không phù hợp truy vấn vẫn có thể gây nhiều I/O. Cần xác định truy vấn nào được hưởng lợi, loại I/O nào đang tốn kém, mức độ ảnh hưởng tới ghi và khả năng duy trì hoạt động trong suốt thao tác.

Bài học này giải thích fragmentation, bloat và page density; phân biệt rebuild với reorganize/coalesce và cập nhật statistics; đánh giá lợi ích, chi phí và rủi ro; lựa chọn online, concurrent, in-place hoặc resumable theo engine; đồng thời xây dựng kế hoạch triển khai, giám sát và xử lý khi thao tác không hoàn tất. Các tùy chọn và giới hạn khác nhau theo phiên bản, edition và loại chỉ mục. Hãy kiểm tra tài liệu của đúng hệ quản trị trước khi chạy trên production.

## 2. Cấu trúc chỉ mục và các vấn đề tích lũy theo thời gian

### 2.1. B-tree và trang lá

Nhiều chỉ mục quan hệ phổ biến dùng cấu trúc B-tree hoặc biến thể. Trang gốc và trang nhánh dẫn tới các trang lá chứa khóa chỉ mục cùng row locator hoặc dữ liệu hàng tùy cách tổ chức. Truy vấn tìm theo khóa đi qua các mức của cây; truy vấn phạm vi đọc một dãy trang lá theo thứ tự khóa.

Khi dữ liệu thay đổi:

- INSERT có thể phải chèn khóa vào một trang lá đang đầy, dẫn đến page split.
- UPDATE cột được đánh chỉ mục có thể tương đương xóa khóa cũ và chèn khóa mới.
- DELETE đánh dấu mục hoặc trang không còn được sử dụng ngay lập tức; cơ chế dọn và tái sử dụng tùy engine.
- Thay đổi kích thước hàng hoặc phân bố khóa có thể làm mật độ trang khác nhau theo thời gian.
- Các trang được cấp phát mới có thể nằm ở vị trí vật lý xa nhau, làm giảm tính tuần tự của một số lần quét.

Page split không phải lúc nào cũng là lỗi. Nó là cơ chế duy trì thứ tự và cân bằng cây. Vấn đề xuất hiện khi split thường xuyên, mật độ trang giảm hoặc cấu trúc vật lý làm workload đọc phải chạm quá nhiều trang.

### 2.2. Fragmentation — phân mảnh chỉ mục

Fragmentation thường mô tả mức độ các trang lá không liền kề hoặc không theo thứ tự vật lý dự kiến. Với truy vấn range scan lớn, việc đọc nhiều vùng rời rạc có thể làm tăng I/O hoặc giảm hiệu quả read-ahead, đặc biệt trên storage có chi phí seek đáng kể.

Không nên coi một tỷ lệ fragmentation là ngưỡng rebuild phổ quát. Tác động phụ thuộc:

- Truy vấn có scan nhiều trang liên tiếp hay chủ yếu point lookup.
- Số trang và kích thước chỉ mục.
- Storage là HDD, SSD, NVMe, SAN hay cloud volume.
- Buffer cache có giữ phần lớn chỉ mục hay không.
- Mức độ song song và read-ahead của engine.
- Page density và số lần đọc thực tế.

Một chỉ mục nhỏ với fragmentation cao có thể không đáng bảo trì. Một chỉ mục lớn có range scan thường xuyên và nhiều physical read có thể đáng quan tâm dù fragmentation chỉ ở mức vừa phải.

### 2.3. Page density — mật độ sử dụng trang

Page density cho biết tỷ lệ không gian trang đang được sử dụng. Mật độ thấp làm cùng một lượng khóa chiếm nhiều trang hơn, tăng kích thước chỉ mục, buffer cache footprint và số trang phải đọc khi scan. Rebuild thường tạo cơ hội đóng gói lại các mục và đạt mật độ cao hơn, tùy fill factor và engine.

Mật độ tối đa không phải lúc nào cũng tốt. Với workload insert/update thường xuyên, để lại khoảng trống trong trang có thể giảm page split. Fill factor thấp làm chỉ mục lớn hơn và tăng số trang scan, nhưng có thể giảm chi phí split trong workload ghi ngẫu nhiên. Chọn fill factor phải dựa trên mẫu ghi, page split rate, kích thước chỉ mục và hiệu năng đọc.

### 2.4. Bloat và khoảng trống có thể tái sử dụng

Bloat là phần dung lượng cấu trúc lớn hơn nhu cầu dữ liệu hữu ích hiện tại. Nguyên nhân và cách đo khác nhau giữa engine. Trong PostgreSQL, dead tuples và cơ chế MVCC có thể làm bảng/index phình; VACUUM thường tái sử dụng không gian bên trong relation nhưng không nhất thiết trả toàn bộ dung lượng cho filesystem. Trong InnoDB, undo/purge và cấu trúc tablespace có cơ chế riêng. Trong SQL Server, page density và fragmentation là các chỉ số thường được xem xét.

Rebuild chỉ mục có thể tạo cấu trúc mới gọn hơn, nhưng không phải phương án xử lý mọi loại bloat. Nếu nguyên nhân là transaction lâu giữ phiên bản cũ, cần giải quyết transaction và cleanup. Nếu bảng chính phình, rebuild index riêng có thể không đủ. Nếu truy vấn đọc quá nhiều cột hoặc dùng sai access path, rebuild không sửa được thiết kế truy vấn.

## 3. Lợi ích có thể đạt được

Rebuild có thể đem lại một hoặc nhiều lợi ích sau khi có điều kiện phù hợp:

1. **Giảm số trang:** loại bỏ khoảng trống và đóng gói lại khóa, giúp range scan đọc ít trang hơn.
2. **Cải thiện locality:** các trang lá được tạo lại theo thứ tự khóa phù hợp, có thể cải thiện đọc tuần tự và read-ahead.
3. **Giảm cache footprint:** chỉ mục nhỏ hơn có thể giữ được nhiều phần dữ liệu hữu ích hơn trong buffer pool.
4. **Khôi phục page density:** đạt mật độ theo fill factor hoặc chính sách tạo chỉ mục của engine.
5. **Giải quyết cấu trúc bất thường:** tái tạo chỉ mục bị hỏng logic/vật lý khi có quy trình sửa chữa được hỗ trợ; trường hợp corruption cần theo hướng dẫn phục hồi riêng.
6. **Cập nhật một số thống kê:** một số engine cập nhật thống kê của chỉ mục trong quá trình rebuild, nhưng hành vi này không thay thế mọi thao tác ANALYZE/UPDATE STATISTICS.

Lợi ích phải được xác nhận bằng truy vấn đại diện: logical reads, physical reads, elapsed time, CPU, I/O latency, số trang được đọc và execution plan. Nếu thời gian truy vấn không thay đổi hoặc workload không sử dụng chỉ mục đó, rebuild có thể chỉ làm tốn tài nguyên.

## 4. Khi nào rebuild không giải quyết đúng vấn đề?

Không nên rebuild chỉ vì một dashboard báo chỉ mục “cũ” hoặc có fragmentation. Rebuild thường không giải quyết:

- Thiếu hoặc sai chỉ mục khiến optimizer chọn scan không cần thiết.
- Predicate không sargable, chuyển kiểu dữ liệu ngầm hoặc biểu thức làm mất khả năng seek.
- Statistics lỗi thời hoặc cardinality estimate sai nếu engine không cập nhật loại thống kê liên quan.
- Parameter skew, plan cache hoặc kế hoạch thực thi không phù hợp.
- Lock contention do transaction dài hoặc thứ tự cập nhật.
- CPU bottleneck, memory pressure hoặc temp spill không liên quan chỉ mục được rebuild.
- Storage bão hòa bởi workload khác.
- Bảng quá lớn vì dữ liệu lịch sử chưa partition/retention đúng cách.
- Transaction mở lâu làm cleanup bị giữ lại.

Ví dụ, truy vấn lọc theo DATE(created_at) có thể không dùng index trên created_at hiệu quả. Rebuild chỉ mục không thay đổi biểu thức predicate. Cần sửa predicate thành khoảng thời gian có thể seek hoặc tạo expression/computed-column index phù hợp nếu nghiệp vụ và engine hỗ trợ.

## 5. Rebuild, reorganize, coalesce và cập nhật statistics

### 5.1. Rebuild

Rebuild tạo lại cấu trúc chỉ mục. Tùy engine, nó có thể:

- Đọc dữ liệu nguồn và sắp xếp khóa.
- Tạo một cấu trúc chỉ mục mới.
- Xây dựng lại các trang và phân bố khóa.
- Chuyển người dùng sang cấu trúc mới ở một thời điểm chuyển đổi.
- Cần thêm dung lượng cho cấu trúc mới, sort workspace và log.

Rebuild thường có khả năng khôi phục page density và sắp xếp lại nhiều trang hơn reorganize, nhưng chi phí I/O, CPU và log thường cao hơn.

### 5.2. Reorganize hoặc coalesce

Reorganize/coalesce thường điều chỉnh cấu trúc hiện tại theo từng phần hoặc hợp nhất các trang có khoảng trống. Tên và phạm vi phụ thuộc engine:

- SQL Server có ALTER INDEX ... REORGANIZE cho một số loại chỉ mục rowstore.
- Oracle có thao tác coalesce cho index segment; rebuild và coalesce có semantics khác nhau.
- PostgreSQL không có lệnh REORGANIZE B-tree tương đương trong lõi; VACUUM, REINDEX và công cụ mở rộng có vai trò khác nhau.
- MySQL/InnoDB dùng các dạng online DDL, OPTIMIZE TABLE hoặc thao tác rebuild tùy mục tiêu và phiên bản; không đồng nhất chúng với một lệnh reorganize chung.

Reorganize có thể ít tài nguyên và cho phép workload tiếp tục, nhưng thường không thay thế rebuild khi cấu trúc cần tạo lại hoàn toàn hoặc khi cần thay đổi fill factor/storage parameters.

### 5.3. ANALYZE hoặc UPDATE STATISTICS

Statistics giúp optimizer ước lượng số hàng, phân bố giá trị và chi phí của access path. Statistics lỗi thời có thể làm optimizer chọn kế hoạch kém dù chỉ mục vật lý đang tốt.

Rebuild và cập nhật statistics là hai công việc khác nhau:

- PostgreSQL REINDEX tạo lại index nhưng không tự thay thế ANALYZE cho bảng và cột.
- SQL Server index rebuild cập nhật statistics gắn với chỉ mục theo hành vi engine, nhưng không đảm bảo mọi column statistics độc lập đều được cập nhật.
- MySQL ANALYZE TABLE cập nhật thống kê optimizer; nó không đồng nghĩa với rebuild toàn bộ cấu trúc.
- Oracle có cơ chế statistics riêng như DBMS_STATS; rebuild index và gather statistics cần được xem xét độc lập.

Sau maintenance, đọc execution plan và statistics để xác nhận optimizer có thông tin phù hợp. Không chạy ANALYZE hoặc UPDATE STATISTICS toàn bộ cơ sở dữ liệu theo thói quen nếu chỉ một nhóm đối tượng cần cập nhật.

## 6. Đánh giá trước khi thực hiện

### 6.1. Bắt đầu từ truy vấn và workload

Chọn các truy vấn quan trọng đang sử dụng chỉ mục. Thu thập:

- Tần suất chạy và số hàng trả về.
- Logical reads, physical reads và số trang được chạm.
- CPU time, elapsed time và latency percentile.
- Execution plan, seek/scan, lookup và số hàng thực tế so với ước lượng.
- Read/write ratio của chỉ mục.
- Số lần page split, lock wait và I/O wait liên quan.
- Thời gian chạy theo giờ cao điểm và khi có batch/backup.

Nếu truy vấn không dùng index, rebuild index đó khó đem lại lợi ích. Nếu truy vấn dùng index nhưng đọc nhiều hàng hơn dự kiến, cần xem selectivity, predicate và statistics trước.

### 6.2. Đo sức khỏe chỉ mục

Không có một metric chung cho mọi hệ quản trị. Kết hợp:

- Kích thước index và số trang.
- Fragmentation hoặc mức độ không liên tục của trang lá.
- Page density hoặc phần trăm không gian trang đã dùng.
- Số lần seek, scan, lookup và update.
- Số lần đọc trang và cache hit.
- Tốc độ page split và hoạt động ghi.
- Dung lượng có thể thu hồi hoặc bloat estimate.

Chỉ số thống kê có thể tích lũy từ lúc khởi động/reset; hãy so sánh delta trong cửa sổ đo và chú ý thời điểm reset. Không so sánh hai hệ thống nếu cách thu thập hoặc định nghĩa metric khác nhau.

### 6.3. Kiểm tra điều kiện vận hành

Trước khi chọn online rebuild, xác minh:

- Phiên bản và edition có hỗ trợ online/concurrent/resumable cho loại index này không.
- Index có thuộc loại đặc biệt như columnstore, full-text, spatial, partitioned hoặc index trên computed/expression column không.
- Có đủ dung lượng cho index mới, sort workspace, log/WAL/redo và file tạm không.
- Transaction log có đủ chỗ và có thể truncate/reuse trong lúc chạy không.
- Replica, CDC, log shipping, backup và downstream consumer có theo kịp không.
- Có DDL, schema migration hoặc maintenance khác đang giữ metadata lock không.
- Có cửa sổ tải thấp, giới hạn CPU/I/O và phương án dừng/tiếp tục không.
- Có kế hoạch xử lý khi online option không được hỗ trợ hoặc thất bại không.

### 6.4. Ước lượng dung lượng đỉnh

Rebuild thường cần tạo cấu trúc mới trong khi cấu trúc cũ vẫn còn phục vụ truy vấn. Ngoài kích thước index hiện tại, có thể cần dung lượng cho:

- Index mới hoặc bản sao tạm trong giai đoạn build.
- Sort runs và workspace trên memory/tempdb/tablespace.
- Transaction log, WAL, redo hoặc binary log.
- Online change log hoặc journal lưu thay đổi phát sinh đồng thời.
- Khoảng trống cần thiết để database tiếp tục ghi trong lúc rebuild.

Không dùng kích thước index hiện tại làm toàn bộ ước lượng. Cần kiểm tra giới hạn filesystem, tablespace, tempdb, transaction log và quota của cloud volume.

## 7. Online, concurrent, in-place và resumable nghĩa là gì?

Các từ này mô tả những đặc tính khác nhau; chúng không đồng nghĩa.

| Thuật ngữ | Ý nghĩa khái quát | Điều cần xác minh |
|---|---|---|
| Offline rebuild | Có thể chặn đọc/ghi hoặc yêu cầu lock mạnh trong thời gian dài | Thời gian gián đoạn và lock mode |
| Online rebuild | Cho phép một phần hoặc phần lớn DML tiếp tục trong khi tạo index mới | Lock ở đầu/cuối, loại index được hỗ trợ, tài nguyên bổ sung |
| Concurrent rebuild | Xây dựng cấu trúc mới trong khi vẫn cho phép truy cập theo cơ chế riêng của engine | Các pha scan, snapshot wait, giới hạn transaction và index invalid |
| In-place DDL | Thay đổi cấu trúc tại chỗ hoặc theo cơ chế tránh copy toàn bộ bảng | Có thật sự tránh copy không, có cần temp/log không, lock nào phát sinh |
| Resumable operation | Có thể pause/resume một thao tác dài mà không phải bắt đầu lại từ đầu | Điều kiện resume, trạng thái tạm, dung lượng và cleanup khi abort |

**Online không có nghĩa là không khóa.** Engine vẫn có thể cần metadata lock hoặc schema lock ngắn ở đầu và cuối; một số thao tác cần lock mạnh hơn trong một pha. Các DML đồng thời có thể được ghi vào online change log, làm tăng I/O và dung lượng. Nếu transaction dài đang giữ metadata lock, thao tác online có thể chờ hoặc gây hàng đợi lock ảnh hưởng request mới.

## 8. Chi phí và rủi ro của rebuild

### 8.1. CPU và I/O

Rebuild phải đọc dữ liệu nguồn, sắp xếp khóa và ghi cấu trúc mới. Với index lớn, công việc có thể tiêu thụ CPU và I/O đáng kể. Nó cạnh tranh với truy vấn đọc/ghi, checkpoint, backup, ETL và replication.

Nếu storage đã gần bão hòa, rebuild có thể làm latency của toàn hệ thống tăng dù bản thân thao tác hoàn tất nhanh. Giới hạn MAXDOP, parallel workers, I/O throttling hoặc lịch chạy có thể giảm tác động, nhưng cũng kéo dài thời gian maintenance.

### 8.2. Transaction log và replication

Thay đổi cấu trúc chỉ mục có thể tạo lượng log lớn. SQL Server có thể ghi nhiều transaction log; PostgreSQL tạo WAL; MySQL/InnoDB dùng redo/undo và có thể ảnh hưởng binary log theo thao tác; Oracle dùng redo/undo.

Log tăng có thể làm:

- Transaction log đầy hoặc không thể truncate/reuse.
- WAL archive hoặc replica nhận log chậm hơn.
- Replica lag tăng, failover readiness giảm.
- Backup log hoặc archive destination cần thêm dung lượng.
- Recovery time và lượng log cần replay tăng.

Theo dõi log generation rate, log usage, archive backlog, replication send/flush/apply lag và thời gian backup. Đừng bắt đầu rebuild nếu log volume đã gần đầy hoặc replica đang tụt xa.

### 8.3. Lock và metadata contention

Online rebuild thường giảm thời gian chặn DML nhưng vẫn có các pha cần lock. Một DDL có thể phải chờ transaction lâu, metadata lock hoặc schema stability lock. Nếu hàng đợi lock hình thành, request mới có thể xếp sau DDL và tạo blocking chain.

Trước khi chạy, tìm transaction dài, session idle in transaction, DDL khác và lock wait. Chọn chính sách chờ có giới hạn; không để một thao tác maintenance chờ vô hạn trên production.

### 8.4. Temp space và bộ nhớ

Sort index có thể cần memory grant hoặc vùng tạm. Nếu workspace không đủ, engine có thể spill xuống tempdb/temp tablespace, làm tăng I/O. Rebuild song song nhiều index có thể nhân mức sử dụng temp space và memory.

Đặt giới hạn concurrency và theo dõi temp usage, spill, memory grant, tempdb/tablespace growth. Tránh chạy đồng thời rebuild với báo cáo sort/hash lớn nếu cùng chia sẻ storage.

### 8.5. Cache churn và ảnh hưởng sau rebuild

Index mới được tạo có thể làm buffer cache chứa nhiều trang mới, đẩy dữ liệu nóng khác ra khỏi cache. Sau rebuild, workload có thể cần warm-up lại; truy vấn đầu tiên có thể chậm hơn trước khi cache ổn định.

Rebuild cũng có thể làm thay đổi page density và fill factor. Nếu workload ghi ngẫu nhiên nhiều, chỉ mục quá đầy có thể phát sinh page split nhanh sau maintenance. Đánh giá hiệu năng trong một khoảng đủ dài sau rebuild, không chỉ ngay khi lệnh hoàn tất.

## 9. PostgreSQL: REINDEX CONCURRENTLY

### 9.1. Khi nào dùng?

PostgreSQL hỗ trợ REINDEX để tạo lại index. Với bảng đang phục vụ ứng dụng, REINDEX CONCURRENTLY cho phép thao tác xây dựng index mới trong khi các thao tác đọc/ghi thông thường tiếp tục theo cơ chế concurrency của PostgreSQL. Đây thường là lựa chọn cần xem xét khi muốn giảm thời gian chặn DML.

Ví dụ:

~~~sql
REINDEX INDEX CONCURRENTLY public.idx_orders_created_at;
~~~

Hoặc rebuild các index của một bảng theo cú pháp được phiên bản hỗ trợ:

~~~sql
REINDEX TABLE CONCURRENTLY public.orders;
~~~

Kiểm tra tài liệu đúng phiên bản về phạm vi đối tượng, partitioned index, loại index và các giới hạn. Không giả định mọi đối tượng có thể reindex concurrently.

### 9.2. Các pha và chi phí

Reindex concurrently cần tạo index mới trong khi index cũ vẫn phục vụ truy vấn. Engine phải xử lý các thay đổi phát sinh trong lúc build và chờ các transaction/snapshot cũ qua những pha cần thiết. Vì vậy:

- Thao tác có thể lâu hơn REINDEX thông thường.
- Cần thêm dung lượng cho index mới và cấu trúc phụ trợ.
- Có thể chờ transaction lâu hoặc snapshot cũ.
- Tạo thêm WAL và I/O.
- Có thể ảnh hưởng replication lag và cache.

Online/concurrent giảm thời gian chặn truy cập nhưng không loại bỏ mọi lock và không miễn phí.

### 9.3. Giới hạn cần nhớ

REINDEX CONCURRENTLY không được chạy bên trong transaction block tường minh. Một số dạng reindex trên database/system catalog hoặc đối tượng đặc biệt có giới hạn riêng. Khi thao tác thất bại ở một pha, có thể để lại index INVALID cần kiểm tra và dọn theo hướng dẫn PostgreSQL.

Không tự xóa index invalid chỉ dựa trên tên. Xác minh index đó có phải bản dựng mới do thao tác thất bại, index cũ còn hợp lệ hay không, constraint/replica có phụ thuộc và kế hoạch tạo lại. Theo dõi tiến độ bằng các view tiến trình phù hợp phiên bản, transaction age và lock wait.

### 9.4. Sau khi rebuild

REINDEX không thay thế ANALYZE. Nếu phân bố dữ liệu hoặc statistics đã thay đổi, chạy ANALYZE cho bảng/cột phù hợp và xem execution plan. Đối chiếu kích thước index, số trang, buffer hit, physical reads và latency của các truy vấn mục tiêu.

## 10. SQL Server: ONLINE và RESUMABLE

### 10.1. Online rebuild

SQL Server hỗ trợ online index operations cho các loại chỉ mục, phiên bản và edition đáp ứng điều kiện. Ví dụ minh họa:

~~~sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD
WITH
(
    ONLINE = ON
);
~~~

Online rebuild cho phép nhiều truy vấn và DML tiếp tục trong phần lớn thời gian, nhưng vẫn cần lock ở các pha bắt đầu/kết thúc và có thể gặp giới hạn theo loại index, kiểu dữ liệu, edition hoặc tính năng sử dụng. Kiểm tra ma trận hỗ trợ của đúng phiên bản trước khi đưa vào runbook.

### 10.2. Chờ lock với WAIT_AT_LOW_PRIORITY

Một số phiên bản hỗ trợ đặt chính sách chờ lock ưu tiên thấp cho online operation:

~~~sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD
WITH
(
    ONLINE = ON
    (
        WAIT_AT_LOW_PRIORITY
        (
            MAX_DURATION = 5 MINUTES,
            ABORT_AFTER_WAIT = SELF
        )
    ),
    MAXDOP = 4
);
~~~

Trong ví dụ, thao tác chờ tối đa năm phút ở mức ưu tiên thấp; nếu không lấy được lock theo chính sách, thao tác tự hủy thay vì đẩy các session người dùng vào hàng đợi dài. Các giá trị phải được chọn theo SLO và phiên bản. WAIT_AT_LOW_PRIORITY có các lựa chọn hành vi khác nhau; không chọn phương án kill blocker một cách tùy tiện.

### 10.3. Resumable index rebuild

Với phiên bản và loại index được hỗ trợ, resumable operation cho phép tạm dừng và tiếp tục một rebuild dài:

~~~sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
REBUILD
WITH
(
    ONLINE = ON,
    RESUMABLE = ON,
    MAX_DURATION = 60 MINUTES,
    MAXDOP = 4
);
~~~

Sau khi thao tác tự pause hoặc được pause, có thể tiếp tục:

~~~sql
ALTER INDEX IX_Orders_CreatedAt
ON dbo.Orders
RESUME
WITH
(
    MAXDOP = 4,
    MAX_DURATION = 30 MINUTES
);
~~~

Kiểm tra trạng thái trong sys.index_resumable_operations. Nếu quyết định không tiếp tục, dùng ABORT theo quy trình; thao tác abort giải phóng trạng thái resumable nhưng không phải rollback nghiệp vụ. Các giới hạn về explicit transaction, online, loại index và option kết hợp cần được xác minh theo phiên bản.

### 10.4. REORGANIZE và statistics

ALTER INDEX ... REORGANIZE thường là thao tác online và điều chỉnh leaf level theo từng phần, tiêu thụ tài nguyên theo cách khác rebuild. Nó không thay thế mọi trường hợp cần rebuild và không tự cập nhật statistics giống rebuild. Sau maintenance, xem statistics của index và column statistics riêng.

Không dùng một ngưỡng fragmentation cố định cho tất cả bảng. Kết hợp fragmentation, page density, số trang, workload scan, storage và mức độ sử dụng index. Với index nhỏ hoặc workload point lookup, chi phí rebuild có thể lớn hơn lợi ích.

## 11. MySQL/InnoDB: online DDL và rebuild

### 11.1. Online DDL không phải thao tác không khóa

InnoDB hỗ trợ nhiều dạng online DDL. Tùy thao tác và phiên bản, thêm hoặc rebuild index có thể sử dụng ALGORITHM=INPLACE và cho phép LOCK=NONE để DML tiếp tục trong phần lớn thời gian.

Ví dụ thêm một secondary index:

~~~sql
ALTER TABLE orders
    ADD INDEX idx_orders_created_at (created_at),
    ALGORITHM=INPLACE,
    LOCK=NONE;
~~~

Đây là ví dụ online DDL tạo index mới, không phải cú pháp rebuild riêng cho mọi index đã có. Khả năng INPLACE/LOCK=NONE phụ thuộc loại thay đổi, engine và phiên bản. Nếu yêu cầu LOCK=NONE không được hỗ trợ, MySQL có thể từ chối thao tác; hãy đọc lỗi và chọn phương án phù hợp, không bỏ tùy chọn rồi vô tình chấp nhận lock mạnh hơn.

### 11.2. Rebuild bảng hoặc index

Trong InnoDB, một số thao tác như OPTIMIZE TABLE hoặc ALTER TABLE ... ENGINE=InnoDB có thể rebuild lại bảng và các index đi kèm theo cơ chế của phiên bản. Đây là thao tác có phạm vi rộng hơn rebuild một secondary index và có thể cần dung lượng đáng kể.

Trước khi chạy, kiểm tra:

- Algorithm thực tế được chọn.
- Lock level được hỗ trợ.
- Metadata lock ở đầu/cuối.
- Online alter log và giới hạn dung lượng của nó.
- Temporary space, redo/undo và binlog.
- Replication lag và thời gian apply trên replica.

Online DDL có thể phải chờ metadata lock do transaction khác giữ. Nếu một transaction dài đang sử dụng bảng, thao tác DDL có thể xếp hàng và gây ảnh hưởng tới truy vấn mới. Kiểm tra metadata lock và transaction age trước khi bắt đầu.

### 11.3. ANALYZE TABLE

ANALYZE TABLE cập nhật thống kê optimizer, còn OPTIMIZE/ALTER rebuild có mục tiêu cấu trúc vật lý. Sau khi bảo trì, kiểm tra cardinality estimate, execution plan, buffer pool reads và thời gian truy vấn. Không dùng ANALYZE TABLE như một cách thay thế rebuild khi cấu trúc cần tạo lại, và cũng không rebuild chỉ vì statistics chưa cập nhật.

## 12. Oracle: REBUILD ONLINE và COALESCE

Oracle cung cấp thao tác ALTER INDEX ... REBUILD và tùy chọn ONLINE cho các loại index và điều kiện được hỗ trợ:

~~~sql
ALTER INDEX idx_orders_created_at REBUILD ONLINE;
~~~

Rebuild tạo lại index segment; online cho phép một phần DML tiếp tục trong thời gian build, nhưng vẫn có các giai đoạn đồng bộ và yêu cầu lock. Cần kiểm tra loại index, edition, tablespace, quota, temporary segment và khả năng logging theo chính sách database.

COALESCE có thể hợp nhất các leaf block có khoảng trống trong một số điều kiện mà không tạo lại toàn bộ cấu trúc như rebuild. Chọn giữa coalesce và rebuild dựa trên page/leaf block utilization, workload và mục tiêu. Statistics optimizer được quản lý qua DBMS_STATS; không giả định rebuild luôn cập nhật mọi statistics cần thiết.

## 13. Chọn online hay offline?

Quyết định dựa trên mức độ sẵn sàng, chi phí và khả năng hỗ trợ:

| Điều kiện | Hướng xem xét |
|---|---|
| Bảng nhỏ, cửa sổ bảo trì rõ, có thể chấp nhận chặn ngắn | Offline rebuild có thể đơn giản và nhanh |
| OLTP cần DML liên tục, engine hỗ trợ đầy đủ | Online/concurrent rebuild |
| Index rất lớn, thao tác có thể vượt maintenance window | Resumable nếu engine và loại index hỗ trợ |
| Mức phân mảnh vừa, cần điều chỉnh từng phần và engine có reorganize | Reorganize/coalesce |
| Vấn đề chính là optimizer estimate | ANALYZE/UPDATE STATISTICS trước |
| Vấn đề là predicate hoặc index design | Sửa SQL/index design trước |
| Storage/log/replica đã gần giới hạn | Hoãn hoặc giới hạn maintenance cho tới khi đủ headroom |

Online thường tốn thêm dung lượng và công việc đồng bộ thay đổi đồng thời. Offline có thể ít overhead hơn nhưng gây gián đoạn. Resumable tăng tính linh hoạt nhưng cần quản lý trạng thái pause và dung lượng tạm. Không có một lựa chọn luôn tốt nhất.

## 14. Xây dựng ngưỡng bảo trì dựa trên bằng chứng

### 14.1. Không dùng ngưỡng fragmentation máy móc

Một chính sách kiểu “fragmentation trên 30% thì rebuild tất cả” có thể gây bảo trì không cần thiết. Cùng một tỷ lệ fragmentation có tác động rất khác giữa:

- Index vài chục trang và index hàng triệu trang.
- Point lookup và range scan lớn.
- HDD và NVMe.
- Index chỉ đọc và index chịu ghi liên tục.
- Buffer cache nóng và workload đọc từ storage thường xuyên.

Ngưỡng nên kết hợp fragmentation, page density, số trang, read pattern, latency, mức sử dụng index và cửa sổ bảo trì. Dùng metric để tạo danh sách ứng viên, sau đó xác minh truy vấn được hưởng lợi.

### 14.2. Đánh giá read benefit so với write cost

Index được đọc nhiều có thể hưởng lợi từ page density cao và ít trang hơn. Nhưng mỗi index cũng làm tăng chi phí INSERT/UPDATE/DELETE, log generation và storage. Rebuild không làm index rẻ hơn khi ghi; nó chỉ tạo lại cấu trúc. Nếu workload ghi gây page split liên tục, cần xem fill factor, key design và write pattern.

### 14.3. Xác định thứ tự ưu tiên

Ưu tiên ứng viên có:

1. Kích thước đủ lớn để fragmentation/page density ảnh hưởng đáng kể.
2. Range scan hoặc scan leaf-level thường xuyên.
3. Số physical reads hoặc latency có thể cải thiện.
4. Page density thấp so với nhu cầu workload.
5. Tầm quan trọng cao với SLO.
6. Dung lượng và cửa sổ vận hành đủ an toàn.

Hoãn index ít được dùng, nhỏ, chủ yếu point lookup hoặc không có bằng chứng cải thiện.

## 15. Lập kế hoạch triển khai trên production

### 15.1. Chụp baseline

Trước khi bắt đầu, lưu lại:

- Kích thước bảng và index, page count, fragmentation/page density.
- Query plan và statistics liên quan.
- Logical reads, physical reads, CPU, elapsed time và p95/p99.
- Read/write IOPS, throughput, latency và queue depth.
- CPU, memory, temp usage và transaction log/WAL usage.
- Lock wait, blocking, transaction age và deadlock.
- Replica lag, archive backlog và trạng thái backup.

Baseline phải bao phủ cùng loại workload và khoảng thời gian có ý nghĩa. Nếu chỉ đo trong giờ thấp điểm nhưng index được dùng nhiều vào giờ cao điểm, kết quả không đại diện.

### 15.2. Tính headroom và giới hạn tải

Ước lượng kích thước index mới và dung lượng tạm. Xác định giới hạn CPU, I/O, temp space, log/WAL, replication và thời gian bảo trì. Đặt giới hạn concurrency hoặc MAXDOP phù hợp để tránh maintenance chiếm toàn bộ tài nguyên.

Nếu chạy nhiều index, ưu tiên từng index hoặc nhóm nhỏ. Chạy đồng thời nhiều rebuild có thể làm I/O, log và temp usage tăng theo cấp số cộng; chỉ song song khi có số liệu chứng minh hạ tầng chịu được.

### 15.3. Kiểm tra blocker và transaction dài

Tìm transaction dài, session idle in transaction, metadata lock, DDL khác và query đang giữ schema lock. Xác định chính sách khi không lấy được lock:

- Chờ trong khoảng thời gian giới hạn.
- Hủy maintenance nếu có nguy cơ làm request người dùng xếp hàng.
- Dùng low-priority wait nếu engine hỗ trợ.
- Chọn lại cửa sổ hoặc xử lý transaction blocker với chủ sở hữu.

Không tự động kill session người dùng chỉ để rebuild bắt đầu.

### 15.4. Chạy thử ở môi trường đại diện

Thử trên bản sao dữ liệu có kích thước và workload gần production. Ghi thời gian, CPU, I/O, log growth, temp usage, lock wait và replica lag. Kết quả trên dữ liệu nhỏ hoặc cache khác trạng thái không đủ để dự đoán thời gian production.

### 15.5. Chạy theo từng đối tượng

Thực hiện một index hoặc một nhóm nhỏ, quan sát metric trong suốt thao tác. Không xếp hàng hàng trăm DDL rebuild nếu chưa có khả năng dừng và kiểm soát tài nguyên. Dừng nhận thêm việc khi log, temp hoặc replica lag tiến gần ngưỡng cảnh báo.

## 16. Giám sát trong khi rebuild

Theo dõi cùng một timeline:

| Nhóm | Chỉ số | Dấu hiệu cần phản ứng |
|---|---|---|
| Tiến độ | Percent complete, phase, elapsed time | Không tiến triển, chờ transaction hoặc lock quá lâu |
| CPU | Utilization, worker, scheduler queue | CPU bão hòa làm query latency tăng |
| Storage | Read/write IOPS, throughput, p95/p99 latency, queue | Queue và latency tăng trong khi throughput không tăng |
| Log | WAL/redo/log usage, archive backlog | Log gần đầy hoặc archive/replica không theo kịp |
| Temp | Tempdb/temp tablespace, sort spill | Temp volume gần đầy hoặc I/O tăng đột biến |
| Concurrency | Blocking, lock wait, deadlock | Request người dùng xếp hàng sau DDL |
| Replication | Send/receive/redo/apply lag | Replica lag vượt SLO hoặc failover window |
| Ứng dụng | Query latency, error rate, pool wait | Request timeout hoặc p99 tăng bất thường |

Thiết lập ngưỡng dừng trước khi chạy. Ví dụ, dừng hoặc pause nếu log còn ít dung lượng, replica lag vượt giới hạn, p99 của giao dịch quan trọng tăng quá SLO hoặc temp volume gần đầy. Ngưỡng thực tế phải dựa trên hệ thống, không sao chép một con số chung.

## 17. Sau khi rebuild: xác nhận lợi ích

### 17.1. Kiểm tra trạng thái index

Xác nhận index hợp lệ, enabled/visible theo engine, không có index invalid hoặc thao tác resumable còn pause ngoài dự kiến. Kiểm tra số trang, kích thước, fragmentation/page density và metadata của index.

### 17.2. Xác nhận execution plan và statistics

Chạy lại truy vấn đại diện với cùng tham số và dữ liệu tương đương. So sánh:

- Index seek/scan và số lookup.
- Estimated rows so với actual rows.
- Logical reads và physical reads.
- CPU và elapsed time.
- I/O wait và latency percentile.
- Plan hash hoặc các operator quan trọng.

Nếu plan thay đổi ngoài dự kiến, kiểm tra statistics và parameter sensitivity. Rebuild có thể làm optimizer chọn plan khác do statistics hoặc cache behavior; cần xác nhận plan mới tốt với nhiều giá trị tham số, không chỉ một lần chạy.

### 17.3. Warm-up và thời gian quan sát

Index mới có thể chưa nằm trong cache. Truy vấn đầu tiên sau rebuild có thể đọc từ storage nhiều hơn; sau đó cache ấm dần. Đo trong khoảng thời gian đủ dài để phân biệt cold-cache effect với cải thiện ổn định.

### 17.4. Kiểm tra workload ghi

Quan sát INSERT/UPDATE/DELETE sau rebuild. Page density quá cao có thể làm page split tăng khi ghi tiếp; fill factor có thể cần điều chỉnh. Theo dõi log bytes per transaction, write latency và kích thước index theo thời gian.

### 17.5. Đo hiệu quả ròng

Lợi ích thực tế là cải thiện SLO hoặc giảm chi phí tài nguyên của workload mục tiêu sau khi tính cả chi phí maintenance. Nếu truy vấn nhanh hơn rất ít nhưng rebuild gây replica lag lớn và tăng thời gian bảo trì, chính sách cần xem lại.

## 18. Xử lý khi rebuild thất bại, pause hoặc cần dừng

### 18.1. Phân biệt fail, pause và abort

- **Fail:** engine báo thao tác lỗi; có thể để lại trạng thái hoặc cấu trúc tạm cần kiểm tra.
- **Pause:** thao tác resumable vẫn có trạng thái để tiếp tục; dung lượng và metadata có thể còn được giữ.
- **Abort/cancel:** yêu cầu dừng thao tác; engine cần thời gian dọn tài nguyên hoặc rollback phần đang thực hiện.

Không đóng session hoặc kill process một cách tùy tiện khi engine đang cleanup. Xem trạng thái operation và tài liệu về cancellation của phiên bản.

### 18.2. Xác nhận index cũ và mới

Với online/concurrent build, engine có thể duy trì index cũ trong khi tạo index mới. Sau lỗi, cần xác minh index nào đang hợp lệ, có index invalid hoặc bản sao tạm không, constraint có còn được bảo vệ và optimizer đang dùng đối tượng nào.

Không xóa index cũ hoặc index invalid chỉ dựa vào tên gần giống. Xác minh catalog, constraint dependency, usage và trạng thái operation trước khi cleanup.

### 18.3. Rollback không luôn là khôi phục cấu trúc cũ tức thì

Rebuild index thường không thay đổi dữ liệu logic, nhưng DDL đã hoàn tất không nhất thiết có một thao tác rollback đơn giản để quay lại byte layout trước đó. Nếu cấu trúc mới gây vấn đề, có thể cần rebuild lại với fill factor hoặc option khác; nếu index bị lỗi, cần tạo lại từ nguồn dữ liệu đáng tin cậy.

Vì vậy, phương án phục hồi nên gồm hủy/pause khi còn trong tiến trình, xác minh index hợp lệ, giữ đủ dung lượng và có câu lệnh tái tạo. Backup vẫn cần cho dữ liệu và database; bản thân index thường có thể tái tạo từ bảng nhưng việc tái tạo có thể tốn thời gian và tài nguyên.

## 19. Ví dụ quyết định: có nên rebuild một index lớn?

Giả sử bảng Orders có index trên CreatedAt:

| Metric | Giá trị quan sát |
|---|---:|
| Kích thước index | 180 GB |
| Số trang | 23 triệu |
| Page density | 62% |
| Fragmentation | 38% |
| Tỷ lệ workload range scan | Cao |
| Physical reads của truy vấn mục tiêu | Tăng theo thời gian |
| Storage | SSD/NVMe dùng chung data và log |
| Replica lag hiện tại | Thấp nhưng không có nhiều headroom |

Fragmentation 38% chưa đủ để tự động quyết định rebuild. Cần xem range scan có thực sự bị chậm, page density thấp có làm tăng số trang đọc, storage có đang bão hòa và replica có theo kịp lượng log phát sinh không.

Quy trình:

1. Lấy execution plan và logical/physical reads của các truy vấn range scan.
2. So sánh page count, density và index size theo lịch sử.
3. Đo I/O latency, queue và workload log/data trên backend dùng chung.
4. Ước lượng peak space cho index mới, temp và log.
5. Kiểm tra replica apply rate và headroom.
6. Chạy thử online/concurrent trên bản sao production-like.
7. Chọn giới hạn CPU/I/O và chính sách dừng theo p99, log usage, temp và replica lag.
8. Rebuild từng index, giám sát liên tục.
9. Sau rebuild, chạy ANALYZE/UPDATE STATISTICS phù hợp và đo lại cùng truy vấn.
10. Theo dõi page split và write latency sau khi workload ghi trở lại.

Nếu range scan cải thiện rõ và replica vẫn theo kịp, maintenance có thể đáng giá. Nếu physical read không phải nút thắt hoặc truy vấn thực tế không dùng index, ưu tiên sửa access path hoặc query trước.

## 20. Các lỗi thường gặp

- **Rebuild mọi index theo lịch cố định:** tiêu thụ I/O, CPU và log dù không có lợi ích đo được.
- **Dùng fragmentation làm tiêu chí duy nhất:** bỏ qua kích thước index, page density, query pattern và storage.
- **Cho rằng online là không khóa:** metadata lock và lock ở đầu/cuối vẫn có thể chặn request.
- **Nhầm in-place với không tốn tài nguyên:** thao tác in-place vẫn có thể dùng log, temp và I/O lớn.
- **Chạy nhiều rebuild song song:** làm bão hòa storage, temp và transaction log.
- **Không kiểm tra dung lượng đỉnh:** index cũ và mới có thể cùng tồn tại trong lúc build.
- **Không xem transaction dài:** DDL có thể chờ lock hoặc snapshot cũ.
- **Bỏ qua replica lag:** log phát sinh nhanh hơn khả năng apply làm failover kém sẵn sàng.
- **Dùng REORGANIZE thay mọi REBUILD:** hai thao tác có semantics và mức độ tái tạo khác nhau.
- **Cho rằng rebuild luôn cập nhật mọi statistics:** cần kiểm tra và chạy ANALYZE/UPDATE STATISTICS riêng khi cần.
- **Đặt fill factor 100% cho mọi workload:** ghi ngẫu nhiên có thể làm page split tăng trở lại.
- **Đo ngay sau rebuild rồi kết luận:** cache chưa warm hoặc workload chưa đủ đại diện.
- **Kill session để giải phóng lock mà không xem rollback:** cleanup có thể tiếp tục lâu và tạo I/O.
- **Không có kế hoạch dừng/tiếp tục:** thao tác dài có thể vượt maintenance window và để lại trạng thái tạm.
- **Không xác minh index sau lỗi:** index invalid hoặc resumable operation còn dang dở có thể gây vấn đề về sau.

## 21. Quy trình chuẩn cho một lần index maintenance

1. **Chọn ứng viên:** dựa trên query workload, số trang, page density, fragmentation và mức sử dụng.
2. **Xác định mục tiêu:** giảm scan pages, giảm physical reads, cải thiện range scan hay khôi phục cấu trúc.
3. **Kiểm tra thiết kế:** xác nhận predicate, selectivity, statistics và execution plan; sửa vấn đề logic trước.
4. **Kiểm tra khả năng online:** phiên bản, edition, loại index, partitioning và giới hạn DDL.
5. **Ước lượng tài nguyên:** index mới, temp, log/WAL/redo, CPU, I/O và replica.
6. **Kiểm tra concurrency:** transaction dài, idle in transaction, blocker, metadata lock và maintenance khác.
7. **Lập giới hạn:** thời gian chờ lock, MAXDOP/concurrency, I/O cap, log/temp threshold và SLO stop condition.
8. **Chạy thử:** kiểm chứng thời gian và tác động trên môi trường tương đương.
9. **Thực hiện từng bước:** rebuild/reorganize/concurrent/resumable theo kế hoạch, ghi nhận operation ID và trạng thái.
10. **Giám sát:** CPU, I/O, log, temp, lock, replica, request latency và tiến độ.
11. **Xác minh kết quả:** index hợp lệ, statistics phù hợp, execution plan và metric truy vấn.
12. **Theo dõi sau bảo trì:** cache warm-up, page split, write amplification, log và replica lag.
13. **Cập nhật chính sách:** giữ lại ngưỡng có ích, bỏ maintenance không đem lại cải thiện.

## 22. Bài tập tự kiểm tra

**Bài 1.** Một index có fragmentation 45% nhưng chỉ có 80 trang và chủ yếu phục vụ point lookup. Có nên rebuild ngay không?

*Gợi ý:* Chưa có đủ căn cứ. Kích thước nhỏ và point lookup có thể khiến fragmentation ít ảnh hưởng. Xem latency, page density, workload và chi phí trước khi quyết định.

**Bài 2.** Một index lớn có page density thấp và được range scan thường xuyên. Rebuild có thể cải thiện điều gì?

*Gợi ý:* Có thể giảm số trang, tăng locality, giảm physical reads và cache footprint. Phải đo lại cùng truy vấn để xác nhận.

**Bài 3.** Vì sao online rebuild vẫn có thể làm request timeout?

*Gợi ý:* Có thể cần metadata/schema lock ở đầu/cuối, chờ transaction dài, cạnh tranh CPU/I/O/log/temp hoặc tạo hàng đợi lock.

**Bài 4.** PostgreSQL REINDEX CONCURRENTLY hoàn tất nhưng truy vấn vẫn dùng plan kém. Bạn kiểm tra gì tiếp?

*Gợi ý:* Execution plan, ANALYZE/statistics, predicate, parameter sensitivity, buffer cache, số logical/physical reads và access path. REINDEX không thay thế ANALYZE.

**Bài 5.** SQL Server resumable rebuild đã pause nhưng dung lượng vẫn bị giữ. Vì sao?

*Gợi ý:* Operation còn trạng thái resumable và có thể giữ cấu trúc/tài nguyên tạm để resume. Kiểm tra sys.index_resumable_operations và quyết định RESUME hoặc ABORT theo quy trình.

**Bài 6.** MySQL báo LOCK=NONE không hỗ trợ cho một thao tác DDL. Cần làm gì?

*Gợi ý:* Không bỏ tùy chọn rồi chạy mù. Kiểm tra algorithm/lock hỗ trợ cho phiên bản và loại thay đổi, đánh giá metadata lock, chọn phương án hoặc maintenance window phù hợp.

**Bài 7.** Sau rebuild, range scan nhanh hơn nhưng INSERT chậm và page split tăng. Những yếu tố nào cần xem?

*Gợi ý:* Fill factor, key insertion pattern, page density, index width, write amplification và tỷ lệ ghi. Điều chỉnh cấu hình theo workload đọc/ghi cân bằng.

## 23. Ghi nhớ khi tối ưu

Rebuild tạo lại cấu trúc chỉ mục và có thể giảm fragmentation, cải thiện page density, locality và số trang phải đọc. Lợi ích phụ thuộc kích thước index, mẫu truy vấn, storage, buffer cache và workload thực tế. Fragmentation không phải tiêu chí duy nhất; cần xem page density, số trang, range scan, physical reads, latency và mức sử dụng index.

Rebuild có chi phí CPU, I/O, temp, transaction log/WAL/redo, dung lượng đỉnh, lock và replication. Online/concurrent giảm thời gian chặn DML nhưng không có nghĩa không khóa; in-place không có nghĩa miễn phí; resumable cần quản lý trạng thái pause/abort. PostgreSQL, SQL Server, MySQL/InnoDB và Oracle có cơ chế cùng giới hạn khác nhau.

Hãy chọn ứng viên từ workload, xác minh execution plan và statistics, kiểm tra headroom và transaction blocker, giới hạn concurrency, giám sát log/temp/replica và xác nhận kết quả sau khi cache ổn định. Chỉ giữ chính sách rebuild khi đo được cải thiện có ý nghĩa với truy vấn và SLO mục tiêu.

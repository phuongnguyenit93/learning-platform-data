# Bộ nhớ theo truy vấn, theo phép toán và theo phiên kết nối

Một hệ quản trị cơ sở dữ liệu dùng bộ nhớ cho nhiều mục đích: lưu trang dữ liệu thường truy cập, thực hiện phép sắp xếp, xây dựng bảng băm cho phép nối, tạo bảng tạm, duy trì trạng thái phiên và phục vụ các tác vụ nền. Các vùng nhớ này có vòng đời và phạm vi cấp phát khác nhau. Một phần được chia sẻ cho toàn instance; một phần gắn với câu truy vấn; một phần gắn với từng phép toán trong execution plan; phần khác tồn tại theo phiên kết nối.

Không phân biệt các phạm vi đó dễ dẫn đến cấu hình sai. Ví dụ, tăng bộ nhớ làm việc cho mỗi phép sort có thể giúp một truy vấn đơn lẻ nhanh hơn, nhưng khi hàng trăm truy vấn chạy đồng thời, tổng bộ nhớ yêu cầu có thể vượt RAM. Ngược lại, tăng cache dùng chung không nhất thiết giải quyết được một truy vấn hash join bị spill ra đĩa do thiếu bộ nhớ làm việc. Muốn tối ưu đúng, cần xác định vùng nhớ nào đang thiếu, truy vấn hoặc phiên nào đang giữ bộ nhớ, mức đồng thời và chi phí thực tế trong execution plan.

Bài học thuộc chương **Bộ nhớ và bộ đệm** của module DATABASE_PERFORMANCE. Module DATABASE_PERFORMANCE rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, việc phân tích bộ nhớ cần kết hợp phạm vi cấp phát, số truy vấn đồng thời, số phép toán tiêu thụ bộ nhớ, execution plan, spill, cache hit và số liệu hệ điều hành.

## 1. Bốn phạm vi bộ nhớ cần phân biệt

Có thể chia bộ nhớ phục vụ một workload cơ sở dữ liệu thành bốn nhóm chính:

| Phạm vi | Đối tượng sử dụng | Ví dụ công việc | Vòng đời thường gặp |
| --- | --- | --- | --- |
| Bộ nhớ dùng chung của instance | Nhiều session và truy vấn | Buffer pool, shared buffer cache, shared pool | Trong thời gian instance hoạt động |
| Bộ nhớ làm việc của truy vấn | Một lần thực thi câu SQL | Memory grant, work area, sort/hash workspace | Trong thời gian truy vấn hoặc operator cần dùng |
| Bộ nhớ theo phép toán | Một operator trong execution plan | Sort, hash join, hash aggregate, window operation | Trong giai đoạn operator thực thi |
| Bộ nhớ theo phiên kết nối | Một connection/session/process | Stack, trạng thái session, cursor, network buffer, biến phiên | Từ lúc mở đến khi đóng hoặc tái sử dụng session |

Các nhóm này là cách phân tích khái niệm. Cách hệ quản trị cấp phát và thống kê có thể gộp một số vùng hoặc dùng cấu trúc riêng. Chẳng hạn, SQL Server thường cấp memory grant ở cấp truy vấn rồi chia sẻ cho các operator cần workspace; PostgreSQL có thể cấp work_mem riêng cho nhiều phép sort/hash; Oracle quản lý PGA work area theo process và operator; MySQL InnoDB có buffer pool dùng chung trong khi một số buffer làm việc được cấp theo thread hoặc operation.

### 1.1. Bộ nhớ dùng chung

Bộ nhớ dùng chung chứa dữ liệu hoặc cấu trúc có thể được nhiều session sử dụng. Ví dụ:

- Buffer pool hoặc shared buffers lưu các trang dữ liệu và chỉ mục được đọc từ lưu trữ.
- Shared pool hoặc plan cache lưu metadata, SQL plan và cấu trúc có thể tái sử dụng.
- Các cấu trúc đồng bộ, dictionary cache, log buffer và vùng quản lý nội bộ khác.

Mục tiêu thường là giảm truy cập lưu trữ, giảm chi phí phân tích SQL và chia sẻ dữ liệu giữa các truy vấn. Bộ nhớ dùng chung thường được cấu hình ở cấp instance hoặc database. Tăng nó có thể cải thiện cache hit nếu cache thực sự là nút thắt và hệ điều hành còn đủ RAM.

### 1.2. Bộ nhớ làm việc của truy vấn

Bộ nhớ làm việc phục vụ các phép toán cần giữ dữ liệu trung gian trong khi thực thi. Một câu SQL có thể cần bộ nhớ để:

- Sắp xếp hàng theo ORDER BY hoặc phục vụ merge operation.
- Xây dựng hash table cho hash join.
- Gom nhóm bằng hash aggregate.
- Tính window function hoặc xử lý dữ liệu trung gian.
- Materialize một tập kết quả hoặc tạo bảng tạm nội bộ.

Nếu bộ nhớ cấp cho công việc không đủ, hệ quản trị có thể chia dữ liệu thành nhiều lượt, ghi phần trung gian ra đĩa hoặc dùng temporary tablespace. Cách xử lý đó bảo đảm truy vấn vẫn có thể hoàn tất nhưng thường tăng I/O và độ trễ.

### 1.3. Bộ nhớ theo phép toán

Một execution plan có thể chứa nhiều operator tiêu thụ bộ nhớ. Ví dụ:

~~~text
Scan orders
    |
Hash Join  <--- cần vùng nhớ cho hash table
    |
Sort       <--- cần vùng nhớ cho các hàng cần sắp xếp
    |
Hash Aggregate <--- cần vùng nhớ cho các nhóm
    |
Return rows
~~~

Không nên mặc định cả câu truy vấn chỉ dùng một vùng nhớ duy nhất. Trong PostgreSQL, nhiều sort hoặc hash operation có thể được cấp phát riêng theo giới hạn work_mem; với SQL Server, memory grant của truy vấn được dùng cho các operator cần workspace; trong Oracle, các work area được quản lý cho từng operation. Phải hiểu mô hình của engine trước khi ước lượng tổng.

### 1.4. Bộ nhớ theo phiên kết nối

Mỗi kết nối có thể cần bộ nhớ cho:

- Stack hoặc cấu trúc thực thi của thread/process.
- Trạng thái transaction, cursor và prepared statement.
- Buffer mạng, giao thức và dữ liệu đang truyền.
- Biến phiên, temporary table và metadata phiên.
- Các buffer làm việc được cấp phát khi session chạy truy vấn.

Một connection idle có thể vẫn chiếm bộ nhớ cơ bản. Một số buffer chỉ được cấp phát khi có câu lệnh cần đến và được giữ lại hoặc tái sử dụng theo hành vi của engine. Vì vậy, không phải mọi tham số per-connection đều được nhân ngay với số kết nối khi instance khởi động; cần phân biệt mức cấp phát thực tế, mức giữ lại và giới hạn tối đa.

## 2. Vì sao cần biết bộ nhớ thuộc phạm vi nào?

Hãy xem ba triệu chứng:

1. Cache hit thấp, nhiều lần đọc trang từ đĩa và nhiều truy vấn cùng đọc một tập dữ liệu. Đây có thể là vấn đề cache dùng chung hoặc working set lớn hơn RAM.
2. Một truy vấn có sort/hash spill, dù hệ thống còn nhiều RAM. Đây có thể là vấn đề memory grant hoặc work area dành cho truy vấn đó.
3. RAM tăng theo số connection, kể cả khi nhiều session đang idle. Đây có thể là chi phí bộ nhớ nền theo phiên, buffer cấp theo thread hoặc session state.

Ba triệu chứng cần ba hướng điều tra khác nhau. Tăng cache dùng chung không chắc giảm spill; tăng work_mem không chắc cải thiện cache hit; giảm số kết nối có thể giảm baseline memory nhưng không sửa một execution plan đọc quá nhiều hàng.

Một cách đặt câu hỏi hữu ích:

- Bộ nhớ đang được dùng bởi instance, query, operator hay session?
- Nó được cấp phát trước hay chỉ khi cần?
- Nó được chia sẻ hay độc quyền?
- Nó được giải phóng sau câu lệnh, transaction hay khi connection đóng?
- Số truy vấn đồng thời hoặc số operator đang chạy là bao nhiêu?
- Có spill, wait, swap, cache eviction hay lỗi cấp phát không?

## 3. Các operator thường tiêu thụ bộ nhớ

### Sort

Sort cần giữ các hàng hoặc khóa sắp xếp để tạo thứ tự. Nếu tập dữ liệu lớn hơn vùng nhớ, engine có thể tạo các run đã sắp xếp trên đĩa rồi merge nhiều lượt. Execution plan có thể hiển thị external sort, disk spill hoặc temp I/O.

Các nguyên nhân thường gặp:

- Sắp xếp quá nhiều hàng do filter thiếu chọn lọc.
- SELECT lấy nhiều cột làm hàng rộng, tăng bộ nhớ cần thiết.
- Không có chỉ mục phù hợp để cung cấp thứ tự.
- ORDER BY hoặc DISTINCT tạo sort lớn.
- Ước lượng cardinality thấp hơn thực tế khiến bộ nhớ cấp phát không đủ.

### Hash Join

Hash join thường xây dựng hash table từ một phía của phép nối rồi dò phía còn lại. Bộ nhớ cần thiết phụ thuộc số hàng, kích thước hàng, khóa hash và overhead của cấu trúc. Nếu hash table vượt giới hạn, engine có thể chia dữ liệu thành partition và spill ra đĩa.

Một lỗi ước lượng số hàng hoặc độ rộng hàng có thể khiến hash table lớn hơn dự kiến. Cần kiểm tra build input, actual rows, estimated rows, row width và dấu hiệu spill.

### Hash Aggregate

Hash aggregate giữ trạng thái cho các nhóm. Số nhóm phân biệt và kích thước trạng thái tổng hợp quyết định bộ nhớ cần dùng. GROUP BY trên tập dữ liệu có cardinality cao có thể cần nhiều bộ nhớ hơn dự kiến.

Nếu nhóm rất nhiều hoặc bộ nhớ không đủ, hệ quản trị có thể spill các partition hoặc chuyển sang chiến lược khác. Giảm số hàng đầu vào, thu hẹp cột và kiểm tra tính chọn lọc thường có ích hơn việc tăng giới hạn bộ nhớ ngay lập tức.

### Window function và materialization

Window function có thể cần sort theo partition key và thứ tự cửa sổ. Một số plan phải lưu hoặc materialize dữ liệu trung gian để tính kết quả. CTE, subquery hoặc temporary result không nhất thiết luôn được materialize; hành vi phụ thuộc optimizer và hệ quản trị.

### Các phép toán khác

Bitmap, spool, distinct, set operation, temporary table và một số phép xử lý JSON/XML có thể cần bộ nhớ đáng kể. Khi đọc execution plan, hãy tìm operator thực tế tiêu thụ bộ nhớ và tài nguyên tạm, không chỉ dựa vào hình thức SQL.

## 4. Bộ nhớ theo truy vấn và mức đồng thời

Một truy vấn có thể dùng bộ nhớ vừa phải khi chạy riêng lẻ nhưng gây áp lực khi nhiều truy vấn cùng hoạt động. Tổng bộ nhớ phụ thuộc:

- Số session đang hoạt động.
- Số truy vấn đồng thời.
- Số operator tiêu thụ bộ nhớ trong từng truy vấn.
- Số worker song song.
- Kích thước dữ liệu và độ lệch phân bố.
- Cơ chế cấp phát, chia sẻ, giới hạn và thu hồi của engine.

Mô hình ước lượng khái quát:

\[
M_{\text{total}} \approx M_{\text{fixed}} + M_{\text{shared}} + M_{\text{sessions}} + M_{\text{queries}} + M_{\text{background}} + M_{\text{reserve}}
\]

Trong đó:

- \(M_{\text{fixed}}\): cấu trúc nền của tiến trình/instance.
- \(M_{\text{shared}}\): cache và vùng nhớ dùng chung.
- \(M_{\text{sessions}}\): bộ nhớ cơ bản cùng trạng thái của các kết nối.
- \(M_{\text{queries}}\): bộ nhớ làm việc của các truy vấn đang chạy.
- \(M_{\text{background}}\): tiến trình bảo trì, replication, backup và tác vụ nền.
- \(M_{\text{reserve}}\): phần dự phòng cho hệ điều hành, agent, file cache và biến động tải.

Đây là mô hình tư duy, không phải công thức cấp phát chính xác cho mọi engine. Các vùng có thể được chia sẻ hoặc tính trong nhau; cần tránh cộng hai lần cùng một allocation.

### Ví dụ về cấp phát theo operator

Giả sử một workload có 30 truy vấn đồng thời. Mỗi truy vấn có hai phép toán cần bộ nhớ và mỗi phép có giới hạn làm việc xấp xỉ 32 MB. Một phép tính biên trên thô có thể là:

\[
30 \times 2 \times 32\text{ MB} = 1920\text{ MB}
\]

Con số này chưa tính session memory, cache, parallel workers, background tasks và hệ điều hành. Nó cũng không khẳng định mọi operator sẽ dùng tối đa cùng lúc; nó chỉ minh họa vì sao nhân giới hạn với concurrency quan trọng hơn việc nhìn một truy vấn riêng lẻ.

Với engine dùng memory grant cấp truy vấn, không được áp dụng phép nhân operator như thể mỗi operator luôn nhận grant độc lập. Cần đọc cơ chế grant của engine. Với PostgreSQL, work_mem được áp dụng cho từng operation và parallel worker có thể làm tổng cấp phát tăng; với SQL Server, grant được cấp cho truy vấn và phân phối cho các operator cần workspace.

### Bộ nhớ theo kết nối và connection pool

Giả sử mỗi session có baseline 3 MB và ứng dụng mở 600 kết nối vật lý. Chi phí nền xấp xỉ 1,8 GB, chưa tính buffer lớn được cấp khi truy vấn chạy. Đây chỉ là phép tính minh họa; baseline thực tế khác theo engine, driver, extension, workload và cách đo.

Connection pool giúp giới hạn số kết nối vật lý và tái sử dụng session. Tuy nhiên, pool quá lớn vẫn có thể giữ nhiều session cùng lúc; pool quá nhỏ có thể tạo hàng chờ ở ứng dụng. Cần điều chỉnh pool dựa trên concurrency cần thiết và khả năng xử lý của database, không chỉ dựa trên số request web.

## 5. Bộ nhớ dùng chung và cache

Cache dùng chung giảm số lần đọc dữ liệu từ lưu trữ. Ví dụ, buffer pool giữ trang bảng/chỉ mục; shared pool có thể giữ plan hoặc metadata. Cache hit cao thường hữu ích, nhưng không tự động chứng minh cấu hình tối ưu.

Một cache quá nhỏ có thể gây churn: các trang được nạp rồi bị đẩy ra trước khi tái sử dụng. Một cache quá lớn có thể lấy mất RAM dành cho query workspace, hệ điều hành hoặc các tiến trình khác, khiến spill và swap tăng.

### Cache hit không phải mục tiêu duy nhất

Khi đánh giá cache, cần xem:

- Working set có phù hợp với dung lượng cache không?
- Truy vấn đọc trang nào và có tái sử dụng không?
- Physical read có thực sự là nút thắt hay dữ liệu được phục vụ từ OS page cache?
- Có scan lớn đẩy các trang nóng ra khỏi cache không?
- Cache hit thay đổi cùng latency, IOPS và throughput như thế nào?

Một workload đọc tuần tự dữ liệu lớn có thể có tỷ lệ cache hit thấp nhưng vẫn hoạt động tốt nếu I/O tuần tự nhanh và truy vấn hiếm khi lặp lại. Ngược lại, cache hit cao nhưng query workspace thiếu vẫn có thể tạo spill lớn.

## 6. PostgreSQL: shared_buffers, work_mem và bộ nhớ backend

PostgreSQL có các vùng nhớ với phạm vi khác nhau:

- shared_buffers: vùng shared buffer cache dùng chung cho instance.
- work_mem: giới hạn cơ sở cho một số phép toán như sort và hash.
- hash_mem_multiplier: hệ số áp dụng cho giới hạn bộ nhớ của hash operation so với work_mem ở các phiên bản hỗ trợ.
- maintenance_work_mem: bộ nhớ cho một số thao tác bảo trì như VACUUM hoặc tạo index; không phải giới hạn workspace của mọi SELECT.
- Bộ nhớ private của backend: trạng thái kết nối, memory context, parser/executor và các allocation khác.

### Hiểu đúng work_mem

work_mem không phải ngân sách tối đa cho toàn câu truy vấn hay toàn server. Một query có thể có nhiều sort/hash operation; mỗi operation có thể dùng vùng nhớ riêng. Parallel query có thể tạo nhiều worker và làm tổng bộ nhớ tăng. Hash operation có thể dùng giới hạn nhân với hash_mem_multiplier theo phiên bản.

Ví dụ cấu hình ở session:

~~~sql
SET work_mem = '32MB';
~~~

Đây là ví dụ minh họa cách đặt cấu hình trong session. Không nên đặt giá trị lớn cho mọi session chỉ vì một truy vấn cần nhiều bộ nhớ. Có thể cân nhắc cấu hình riêng cho một tác vụ được kiểm soát, sau đó khôi phục giá trị hoặc kết thúc session.

### Quan sát truy vấn và spill

Đọc execution plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(total_amount)
FROM orders
GROUP BY customer_id
ORDER BY SUM(total_amount) DESC;
~~~

Tìm các dấu hiệu như sort method dùng external merge, disk usage, temp read/write hoặc hash batches lớn hơn một. EXPLAIN ANALYZE thực thi truy vấn thật; hãy chọn môi trường và phạm vi thử phù hợp.

Có thể xem số liệu temp theo database:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

Đây là số liệu tích lũy từ lần reset thống kê, không quy trực tiếp cho một query. Có thể bật pg_stat_statements để phân tích query statistics và log_temp_files để ghi nhận file tạm theo ngưỡng; cấu hình và quyền cần phù hợp môi trường.

Để xem memory context của backend hiện tại trên phiên bản hỗ trợ:

~~~sql
SELECT name, parent, level, total_bytes, free_bytes, used_bytes
FROM pg_backend_memory_contexts
ORDER BY used_bytes DESC;
~~~

View này mô tả backend của session đang thực thi truy vấn, không phải báo cáo toàn bộ bộ nhớ private của mọi backend.

### Hướng xử lý

- Giảm số hàng và độ rộng hàng trước sort/hash.
- Bổ sung chỉ mục phù hợp nếu có thể tránh sort.
- Cập nhật statistics để optimizer ước lượng cardinality sát hơn.
- Chỉ tăng work_mem cho phạm vi truy vấn hoặc workload đã đo và có giới hạn concurrency.
- Theo dõi temp bytes, số worker và tổng bộ nhớ backend cùng shared_buffers.

effective_cache_size là ước lượng cho planner về cache có thể dùng, không phải vùng RAM được PostgreSQL cấp phát.

## 7. SQL Server: memory grant và memory clerks

SQL Server sử dụng memory grant cho các truy vấn cần workspace, chẳng hạn sort và hash. Grant thường được quản lý ở cấp truy vấn; các operator cần bộ nhớ dùng chung ngân sách đó theo kế hoạch thực thi. Nếu grant không đủ, sort/hash có thể spill ra tempdb. Nếu grant quá lớn, nó có thể giữ tài nguyên mà truy vấn khác cần và gây memory grant wait.

### Quan sát memory grant đang hoạt động

~~~sql
SELECT
    session_id,
    request_id,
    requested_memory_kb,
    required_memory_kb,
    granted_memory_kb,
    used_memory_kb,
    max_used_memory_kb,
    wait_time_ms,
    grant_time
FROM sys.dm_exec_query_memory_grants
ORDER BY requested_memory_kb DESC;
~~~

Các cột và quyền truy cập có thể khác theo phiên bản. Các giá trị giúp phân biệt truy vấn đang chờ grant, grant lớn nhưng dùng ít, hoặc truy vấn đã dùng gần hết vùng được cấp.

### Quan sát áp lực bộ nhớ instance

sys.dm_os_memory_clerks cho biết các thành phần đang giữ bộ nhớ:

~~~sql
SELECT
    type,
    SUM(pages_kb) AS pages_kb,
    SUM(virtual_memory_committed_kb) AS committed_virtual_kb
FROM sys.dm_os_memory_clerks
GROUP BY type
ORDER BY pages_kb DESC;
~~~

Kết hợp với sys.dm_os_process_memory, sys.dm_os_sys_memory, wait statistics và error log để xem áp lực từ instance hay hệ điều hành. Không kết luận chỉ từ một memory clerk lớn; cần hiểu loại allocation và xu hướng.

### Dấu hiệu và cách xử lý

- RESOURCE_SEMAPHORE có thể cho biết query đang chờ memory grant.
- Sort/hash spill có thể xuất hiện trong actual execution plan hoặc Query Store/Extended Events theo phiên bản.
- Grant lớn nhưng max_used_memory_kb thấp có thể cho thấy ước lượng quá cao hoặc plan cấp dư.
- Grant nhỏ so với nhu cầu có thể gây spill, đặc biệt khi estimated rows thấp hơn actual rows.

Kiểm tra cardinality estimates, thống kê, row width, degree of parallelism và các operator tiêu thụ grant. SQL Server có các cơ chế như memory grant feedback ở những phiên bản/cấu hình hỗ trợ; cần quan sát plan và hành vi thực tế trước khi tự thay đổi giới hạn toàn instance.

## 8. MySQL InnoDB: buffer pool và buffer theo thread

InnoDB dùng innodb_buffer_pool_size cho vùng cache dữ liệu và chỉ mục dùng chung. Đây là một phần lớn của memory footprint của instance. Ngoài ra, một số buffer và cấu trúc làm việc được cấp theo connection/thread hoặc theo operation.

Các tham số có thể liên quan:

- sort_buffer_size: buffer cho sort theo thread.
- join_buffer_size: buffer có thể được dùng cho một số join không tận dụng index lookup; một truy vấn có thể cần nhiều hơn một join buffer tùy plan.
- read_buffer_size: buffer cho một số lần đọc tuần tự.
- read_rnd_buffer_size: buffer phục vụ một số kiểu đọc theo thứ tự sau sort.
- tmp_table_size và max_heap_table_size: giới hạn liên quan đến bảng tạm trong bộ nhớ ở các cấu hình/phiên bản áp dụng; MySQL mới còn có cơ chế TempTable và các tham số riêng.

Các buffer không nhất thiết được cấp đầy đủ cho mọi connection ngay lúc kết nối. Nhiều vùng chỉ cấp khi truy vấn cần. Tuy vậy, tăng giá trị per-thread quá cao có thể làm tổng RAM tăng mạnh khi có nhiều truy vấn đồng thời.

### Quan sát bộ nhớ và bảng tạm

Nếu Performance Schema memory instrumentation được bật, có thể xem allocation theo thread:

~~~sql
SELECT
    THREAD_ID,
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_by_thread_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 30;
~~~

Để xem allocation toàn cục:

~~~sql
SELECT
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 30;
~~~

Các kết quả phụ thuộc instrumentation và phiên bản; không phải mọi allocation đều được ghi nhận. Theo dõi thêm status variables liên quan đến temporary tables, disk temporary tables, buffer pool và process RSS.

### Hướng xử lý

- Dùng index phù hợp cho điều kiện join và thứ tự lọc để tránh buffer join lớn không cần thiết.
- Thu hẹp dữ liệu trước khi sort hoặc tạo temporary table.
- Đặt buffer per-thread theo workload và số truy vấn đồng thời.
- Theo dõi số connection thực, active thread, temporary table và memory instrumentation.
- Tránh tăng đồng loạt sort_buffer_size hoặc join_buffer_size chỉ để xử lý một query.

## 9. Oracle: SGA, PGA và work area

Oracle phân biệt vùng nhớ dùng chung của instance (SGA) và vùng nhớ private của process (PGA). SGA chứa các thành phần như database buffer cache, shared pool và redo log buffer. PGA chứa dữ liệu private của process, bao gồm các work area cho sort, hash join và một số thao tác khác.

Với automatic workarea management, Oracle điều chỉnh bộ nhớ work area dựa trên mục tiêu PGA và tải hiện tại. Các tham số thường gặp gồm PGA_AGGREGATE_TARGET và PGA_AGGREGATE_LIMIT; chúng có vai trò khác nhau và không nên được xem là ngân sách độc lập cho mỗi truy vấn.

### Quan sát work area

Các view như V$SQL_WORKAREA_ACTIVE, V$SQL_WORKAREA và V$SQL_WORKAREA_HISTOGRAM giúp xem work area đang hoạt động, kích thước dự kiến/thực tế và số lần thực hiện optimal, one-pass hoặc multi-pass. Ví dụ:

~~~sql
SELECT
    sid,
    operation_type,
    policy,
    actual_mem_used,
    max_mem_used,
    number_passes,
    tempseg_size
FROM v$sql_workarea_active
ORDER BY actual_mem_used DESC;
~~~

Tên cột và khả năng xem phụ thuộc phiên bản/quyền. NUMBER_PASSES lớn hơn 0 và TEMPSEG_SIZE khác 0 có thể chỉ ra work area cần nhiều lượt hoặc dùng temporary segment.

### Quan sát PGA

~~~sql
SELECT name, value, unit
FROM v$pgastat
WHERE name IN
(
    'total PGA allocated',
    'maximum PGA allocated',
    'over allocation count',
    'cache hit percentage'
);
~~~

Các thống kê này cần được đọc cùng workload và thời gian lấy mẫu. PGA được cấp cho process; tổng bộ nhớ của nhiều process có thể cao dù một session riêng lẻ không lớn.

### Hướng xử lý

- Xem work area nào chạy one-pass hoặc multi-pass và truy vấn tương ứng.
- Kiểm tra cardinality, sort input, hash build input và độ rộng hàng.
- Đánh giá PGA target/limit với RAM vật lý và số process đồng thời.
- Theo dõi SGA, PGA, temporary tablespace và dấu hiệu over-allocation.
- Tối ưu SQL và chỉ mục trước khi nâng giới hạn bộ nhớ diện rộng.

## 10. So sánh cách quản lý giữa các hệ quản trị

| Hệ quản trị | Bộ nhớ dùng chung tiêu biểu | Bộ nhớ làm việc tiêu biểu | Phạm vi cần chú ý |
| --- | --- | --- | --- |
| PostgreSQL | shared_buffers | work_mem, hash_mem_multiplier | Mỗi operation sort/hash và parallel worker có thể làm tổng tăng |
| SQL Server | Buffer pool và memory clerks | Query memory grant | Grant ở cấp query, dùng cho các operator cần workspace |
| MySQL InnoDB | innodb_buffer_pool_size | Sort/join/read buffers, internal temp tables | Nhiều buffer có thể cấp theo thread/operation khi cần |
| Oracle | SGA, buffer cache, shared pool | PGA work area | Work area theo process/operation, tự điều chỉnh khi dùng automatic management |

Tên tham số giống nhau không có nghĩa ngữ nghĩa giống nhau. work_mem của PostgreSQL không tương đương trực tiếp với memory grant của SQL Server hay PGA work area của Oracle. Trước khi chuyển cấu hình giữa các nền tảng, cần hiểu phạm vi cấp phát, cách chia sẻ, giới hạn, thời điểm thu hồi và cách ghi nhận spill.

## 11. Dấu hiệu thiếu bộ nhớ và cấp phát quá mức

### Thiếu bộ nhớ làm việc

- Sort chuyển sang external/disk-based.
- Hash join hoặc hash aggregate chia nhiều batch/partition.
- Temporary file hoặc temporary tablespace tăng.
- Query duration và I/O tăng ở operator cụ thể.
- SQL Server có spill warning hoặc memory grant wait.
- Oracle work area chạy one-pass/multi-pass.
- PostgreSQL tăng temp_files/temp_bytes hoặc log temp file.
- MySQL tăng internal temporary tables trên đĩa hoặc allocation liên quan sort/join.

### Thiếu bộ nhớ dùng chung

- Cache churn và tỷ lệ tái sử dụng trang thấp.
- Physical reads cao trên workload lặp lại.
- Nhiều truy vấn cùng đọc dữ liệu nóng nhưng cache không giữ được working set.
- OS memory pressure xuất hiện khi vùng cache cạnh tranh RAM với các thành phần khác.

### Cấp phát quá mức

- RAM của tiến trình tăng theo concurrency.
- Hệ điều hành bắt đầu swap hoặc reclaim mạnh.
- Cache bị thu hẹp hiệu quả do query workspace chiếm RAM.
- Truy vấn khác chờ memory grant hoặc không thể cấp phát.
- Throughput giảm dù một số truy vấn riêng lẻ có thể nhanh hơn.
- Instance có thể gặp lỗi cấp phát hoặc bị hệ điều hành kết thúc khi vượt giới hạn.

Không phải mọi mức sử dụng RAM cao đều là vấn đề. Cache thường được thiết kế để tận dụng RAM sẵn có. Cần quan sát available memory, swap, paging, allocation trend, spill, wait và latency để xác định áp lực thực.

## 12. Cardinality estimate và kích thước hàng

Optimizer dùng thống kê để ước lượng số hàng và chọn plan. Ước lượng này ảnh hưởng đến memory grant hoặc work area.

Nếu estimated rows thấp hơn nhiều so với actual rows:

- Sort/hash có thể được cấp ít bộ nhớ hơn nhu cầu.
- Hash table có thể spill.
- Kế hoạch join có thể chọn sai thuật toán.
- Query cần nhiều lượt đọc dữ liệu tạm.

Nếu estimated rows cao hơn thực tế:

- Query có thể nhận grant lớn hơn cần thiết.
- Bộ nhớ bị giữ hoặc dành trước cho query trong khi truy vấn khác đang cần.
- Mức đồng thời hữu ích có thể giảm.

Độ rộng hàng cũng quan trọng. SELECT * có thể làm dữ liệu trung gian lớn hơn cần thiết; cột văn bản lớn, JSON hoặc binary có thể tăng memory footprint. Chỉ chọn cột cần dùng và tránh mang dữ liệu rộng qua sort/hash khi có thể.

Hãy so sánh estimated rows với actual rows tại operator gây áp lực, kiểm tra statistics, histogram, skew và correlation giữa các cột. Cập nhật statistics có thể giúp optimizer nhưng không thay thế việc xác minh logic truy vấn.

## 13. Quy trình điều tra bộ nhớ

Khi RAM, temp I/O hoặc query latency tăng, thực hiện lần lượt:

1. **Xác định phạm vi:** áp lực thuộc cache dùng chung, query workspace, operator hay session?
2. **Chụp số liệu nền:** RAM instance/process, available memory, swap, số connection, active query, temp I/O, cache và grant.
3. **Tìm đối tượng tiêu thụ:** query/session/operator nào dùng hoặc được cấp nhiều bộ nhớ nhất?
4. **Đọc execution plan:** xác định sort, hash, aggregate, window hoặc materialize; so estimated và actual rows.
5. **Kiểm tra spill:** xem temp files, spill warning, hash batches, one-pass/multi-pass hoặc disk temporary table.
6. **Đánh giá concurrency:** có bao nhiêu query cùng chạy, mỗi query có bao nhiêu operator/worker và pool đang mở bao nhiêu session?
7. **Xem kích thước hàng và dữ liệu trung gian:** có SELECT thừa cột, join fanout hoặc filter áp dụng muộn không?
8. **Kiểm tra cache:** working set, cache hit, physical reads và eviction có chỉ ra cache pressure không?
9. **Xác định thay đổi phù hợp:** sửa SQL/index/statistics, giảm concurrency, điều chỉnh pool hoặc cấu hình memory scope cụ thể.
10. **Đo lại:** so latency, throughput, spill, RAM peak, temp I/O, cache behavior và chi phí ghi trước/sau.

Không bắt đầu bằng việc tăng tất cả tham số bộ nhớ. Hãy xác định đúng vùng nhớ và đối tượng gây áp lực trước.

## 14. Thứ tự ưu tiên khi tối ưu

### Tối ưu lượng dữ liệu phải xử lý

- Đưa điều kiện lọc có thể áp dụng sớm vào truy vấn.
- Chọn đúng cột thay vì SELECT *.
- Sửa điều kiện JOIN để tránh nhân số hàng ngoài ý muốn.
- Tổng hợp dữ liệu ở grain phù hợp trước khi nối nếu nghiệp vụ cho phép.
- Dùng phân trang hoặc batch có ranh giới rõ ràng cho công việc lớn.

### Tối ưu access path và execution plan

- Tạo hoặc điều chỉnh chỉ mục để tránh sort không cần thiết.
- Chọn thứ tự khóa phù hợp với equality, range và ORDER BY.
- Cập nhật statistics và xử lý phân bố dữ liệu lệch.
- Xem xét join algorithm và thứ tự join theo actual plan.
- Giảm số hàng và độ rộng build input cho hash join/aggregate.

### Điều chỉnh concurrency và connection pool

- Giới hạn số truy vấn nặng chạy đồng thời.
- Tách workload báo cáo và giao dịch nếu cần.
- Cấu hình pool theo khả năng xử lý thực tế của database.
- Tránh mở hàng nghìn connection idle chỉ để phục vụ số request lớn.
- Dùng hàng đợi hoặc semaphore ở ứng dụng cho các tác vụ tiêu thụ bộ nhớ cao.

### Điều chỉnh tham số bộ nhớ

Chỉ thay đổi sau khi có baseline và xác định đúng phạm vi. Thử từng thay đổi có kiểm soát, quan sát peak memory và concurrency, đồng thời chuẩn bị giá trị quay lại. Một giá trị tốt cho truy vấn đơn lẻ có thể gây quá tải khi workload đạt đỉnh.

## 15. Ví dụ: sort spill khi báo cáo chạy đồng thời

Một báo cáo tính doanh thu theo khách hàng rồi sắp xếp giảm dần. Khi chạy một mình, truy vấn hoàn tất trong thời gian chấp nhận được. Vào cuối ngày, 40 phiên báo cáo chạy cùng lúc và hệ thống ghi nhận temp I/O tăng mạnh.

Truy vấn:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= ?
  AND created_at < ?
GROUP BY customer_id
ORDER BY revenue DESC;
~~~

Các bước điều tra:

1. Kiểm tra execution plan để xác định hash aggregate, sort và số hàng đầu vào.
2. So sánh estimated rows với actual rows; xác định khoảng thời gian có dữ liệu tăng đột biến hay statistics cũ.
3. Kiểm tra độ rộng hàng và số customer_id phân biệt.
4. Đo số báo cáo đồng thời, bộ nhớ làm việc mỗi query và tổng temp I/O.
5. Kiểm tra index có hỗ trợ filter theo created_at và khả năng giảm số hàng đọc hay không.
6. Thử giới hạn concurrency báo cáo hoặc chạy theo batch nếu SLA cho phép.
7. Đo lại p95, throughput, peak memory, spill và thời gian hoàn tất toàn bộ batch.

Nếu tăng memory limit cho mọi query, 40 truy vấn đồng thời có thể yêu cầu lượng RAM lớn hơn nhiều. Nếu tối ưu filter, statistics và số nhóm, hoặc giảm số báo cáo chạy cùng lúc, hệ thống có thể giảm spill mà không cần tăng giới hạn toàn cục.

## 16. Ví dụ: RAM tăng theo số kết nối

Một dịch vụ mở connection pool lớn để giảm thời gian tạo kết nối. Khi số kết nối vật lý tăng từ 100 lên 800, RAM tiến trình database tăng dù phần lớn session đang idle.

Không nên kết luận toàn bộ phần tăng là do một tham số buffer cụ thể. Hãy phân tích:

- Bộ nhớ cơ bản theo process/thread hoặc session.
- Buffer theo thread được cấp phát khi truy vấn chạy.
- Temporary table, cursor và prepared statement còn giữ.
- Session có transaction mở hoặc trạng thái phiên lớn không?
- Connection pool có mở nhiều kết nối hơn mức concurrency cần thiết không?
- Một số session có memory leak hoặc allocation tăng theo thời gian không?

Thử giảm pool max size trong môi trường kiểm thử, giữ nguyên workload và đo:

- Peak và baseline memory của database.
- Số connection active/idle.
- Thời gian chờ lấy connection ở ứng dụng.
- Throughput và p95/p99.
- Số query đồng thời và mức sử dụng CPU/I/O.

Pool nhỏ hơn có thể giảm memory footprint nhưng làm tăng hàng chờ ứng dụng nếu đặt quá thấp. Chọn kích thước theo điểm cân bằng giữa concurrency, latency và năng lực database.

## 17. Kế hoạch kiểm chứng sau thay đổi

Trước khi thay đổi, ghi nhận baseline trong một khoảng thời gian đại diện:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Instance/process memory peak | Mức bộ nhớ cao nhất của database |
| Available RAM và swap | Áp lực đối với hệ điều hành |
| Shared cache hit và physical reads | Hiệu quả cache dùng chung |
| Query memory grant/work area | Bộ nhớ cấp cho truy vấn |
| Sort/hash spill và temp bytes | Công việc bị đẩy ra lưu trữ tạm |
| Số connection active/idle | Mức đồng thời và chi phí session |
| p50/p95/p99 và throughput | Chất lượng dịch vụ |
| CPU, IOPS và read/write latency | Tác động lên tài nguyên |
| Thời gian INSERT/UPDATE | Chi phí ghi sau khi thay đổi chỉ mục hoặc cấu hình |

Sau khi thay đổi:

1. Chạy lại cùng workload, cùng tập dữ liệu và điều kiện cache tương đương.
2. Kiểm tra kết quả truy vấn có giữ nguyên ngữ nghĩa.
3. So sánh actual plan, memory grant/work area, số spill và temp I/O.
4. Đo peak memory ở concurrency đại diện và ở giờ cao điểm mô phỏng.
5. Kiểm tra swap, paging, cache eviction và wait events.
6. Đo latency và throughput của cả workload, không chỉ query được tối ưu.
7. Kiểm tra chi phí ghi, bảo trì chỉ mục và tác động lên các session khác.
8. Theo dõi sau phát hành và hoàn nguyên nếu vượt giới hạn bảo vệ đã đặt.

Không kết luận thành công chỉ vì một truy vấn riêng lẻ chạy nhanh hơn. Thay đổi tốt phải cải thiện mục tiêu mà vẫn giữ RAM trong giới hạn, tránh spill/wait quá mức và không làm suy giảm các workload quan trọng khác.

## 18. Nguyên tắc cần ghi nhớ

- Bộ nhớ dùng chung, bộ nhớ làm việc của truy vấn, bộ nhớ theo operator và bộ nhớ theo session có phạm vi và vòng đời khác nhau.
- Sort, hash join, hash aggregate và window operation có thể tiêu thụ nhiều workspace.
- Một query có nhiều operator cần bộ nhớ; concurrency và parallel worker có thể làm tổng cấp phát tăng.
- Không nhân mọi tham số với số connection một cách máy móc; phải hiểu buffer nào được cấp phát ngay, buffer nào cấp khi cần và engine quản lý ra sao.
- PostgreSQL work_mem áp dụng theo operation; SQL Server thường cấp memory grant cho query; MySQL có các buffer theo thread/operation; Oracle quản lý PGA work area.
- Cache dùng chung giảm I/O đọc dữ liệu nhưng không thay thế bộ nhớ làm việc của query.
- Spill, temp I/O, memory grant wait, one-pass/multi-pass và swap là những dấu hiệu cần được đọc cùng execution plan và workload.
- Cardinality estimate và row width ảnh hưởng trực tiếp đến nhu cầu bộ nhớ.
- Ưu tiên giảm dữ liệu trung gian, cải thiện access path, cập nhật statistics và kiểm soát concurrency trước khi tăng giới hạn diện rộng.
- Kiểm chứng bằng peak memory, spill, cache behavior, latency, throughput và chi phí ghi ở mức tải đại diện.

Tối ưu bộ nhớ cơ sở dữ liệu bắt đầu bằng việc xác định đúng phạm vi cấp phát và vòng đời của allocation. Khi tách được cache dùng chung khỏi workspace của truy vấn, operator và session, nhóm vận hành có thể tìm đúng nguyên nhân của spill hoặc memory pressure. Kết hợp execution plan, số liệu theo phiên, concurrency và phép đo trước/sau sẽ giúp chọn cấu hình phù hợp mà không biến một cải thiện cục bộ thành rủi ro thiếu bộ nhớ toàn instance.

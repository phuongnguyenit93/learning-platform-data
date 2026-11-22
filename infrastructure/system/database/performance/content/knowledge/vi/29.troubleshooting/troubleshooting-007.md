# Tràn bộ nhớ, vùng tạm lớn và thiếu dung lượng lưu trữ

Một truy vấn phân tích có thể cần sắp xếp hàng triệu hàng, xây dựng bảng băm để JOIN hoặc GROUP BY, tạo tập kết quả trung gian và ghi dữ liệu tạm trong lúc thực thi. Nếu vùng làm việc trong bộ nhớ không đủ, database có thể chuyển một phần dữ liệu trung gian xuống vùng lưu trữ tạm. Cơ chế này thường được gọi là spill to disk. Spill giúp truy vấn tiếp tục chạy, nhưng có thể làm tăng I/O, latency và dung lượng lưu trữ cần thiết.

Khi nhiều truy vấn cùng spill, vùng tạm có thể tăng nhanh và chạm giới hạn. Nếu filesystem, volume hoặc quota không còn chỗ, truy vấn có thể lỗi, transaction bị hủy, tác vụ nền thất bại hoặc cả dịch vụ database bị ảnh hưởng. Trong một số tình huống, nguyên nhân bắt đầu từ một truy vấn có cardinality estimate sai; ở tình huống khác, từng truy vấn riêng lẻ đều hợp lý nhưng concurrency quá cao khiến tổng nhu cầu bộ nhớ và vùng tạm vượt khả năng hệ thống.

Bài học thuộc chương **Chẩn đoán sự cố** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, điều tra tràn bộ nhớ và thiếu dung lượng phải kết hợp execution plan, thống kê truy vấn, mức dùng bộ nhớ, temp I/O, concurrency và dung lượng thực còn lại.

## 1. Phân biệt bốn hiện tượng liên quan

Các sự cố thường bị gọi chung là “hết memory” hoặc “hết disk”, nhưng cần tách riêng:

| Hiện tượng | Điều gì xảy ra | Dấu hiệu thường gặp |
| --- | --- | --- |
| Memory pressure | Database hoặc hệ điều hành thiếu bộ nhớ khả dụng cho workload | Memory grant chờ, cache bị thu hẹp, paging, OOM hoặc hiệu năng giảm |
| Operator spill | Sort, hash join, hash aggregate hoặc operator khác không giữ được toàn bộ dữ liệu trung gian trong memory grant/work area | Spill warning, số pass, temp bytes/read/write tăng |
| Temp-space pressure | Các truy vấn, temporary table, version store hoặc tác vụ khác dùng vùng tạm nhanh hơn khả năng giải phóng | Temp usage tăng, free temp giảm, allocation wait hoặc lỗi hết chỗ |
| Storage capacity exhaustion | Filesystem, volume, quota hoặc giới hạn dịch vụ không còn dung lượng có thể cấp phát | Disk free gần 0, file growth thất bại, database báo không thể ghi file |

Một operator spill có thể xảy ra trong khi hệ thống vẫn còn dung lượng đĩa. Ngược lại, filesystem có thể đầy vì log, backup hoặc data file dù không có truy vấn nào spill. Temp-space pressure cũng có thể xảy ra trên một tablespace hoặc volume riêng trong khi các volume khác còn trống.

Chẩn đoán phải trả lời ba câu hỏi:

1. Thành phần nào đang tiêu thụ bộ nhớ hoặc dung lượng?
2. Nhu cầu tăng do truy vấn đơn lẻ, concurrency hay tăng trưởng dữ liệu?
3. Giới hạn nằm ở memory, vùng tạm của database, volume, filesystem hay quota của dịch vụ?

## 2. Vì sao database cần vùng làm việc và vùng tạm?

Database dùng bộ nhớ cho cache trang dữ liệu, metadata, session, execution context và vùng làm việc của operator. Một số thao tác có thể cần giữ tập dữ liệu trung gian:

- Sort để thực hiện ORDER BY, DISTINCT hoặc phục vụ merge operation.
- Hash join để xây dựng bảng băm từ một phía của phép JOIN.
- Hash aggregate để gom nhóm và tính tổng hợp.
- Window function cần sắp xếp hoặc phân vùng dữ liệu.
- Materialize, spool hoặc temporary result để tái sử dụng dữ liệu trung gian.
- Temporary table do ứng dụng hoặc stored procedure tạo.

Nếu tập dữ liệu trung gian vượt vùng nhớ được cấp, engine có thể chia thành các phần, ghi một số phần ra vùng tạm rồi đọc lại để tiếp tục xử lý. Với hash join, cách thực hiện có thể chuyển từ in-memory sang grace/hash partitioning hoặc nhiều pass. Với sort, dữ liệu có thể được chia thành các run đã sắp xếp rồi merge.

~~~text
Truy vấn
   |
   v
Sort / Hash / Aggregate
   |
   +---- Dữ liệu vừa memory grant ----> Xử lý trong RAM
   |
   +---- Dữ liệu vượt vùng nhớ -------> Ghi partition/run ra TEMP
                                          |
                                          v
                                      Đọc lại và merge
                                          |
                                          v
                                      Kết quả truy vấn
~~~

Spill không nhất thiết là lỗi logic. Một truy vấn lớn có thể cần vùng tạm ngay cả khi được thiết kế tốt. Vấn đề hiệu năng xuất hiện khi spill quá nhiều, lặp lại thường xuyên, xảy ra đồng thời hoặc cạnh tranh với I/O của workload khác.

## 3. Memory grant và work area

Nhiều database engine ước lượng bộ nhớ cần cho một truy vấn hoặc operator dựa trên execution plan, cardinality, row width, số nhóm và cấu hình. Vùng nhớ được cấp có thể gọi là memory grant, work area hoặc một thuật ngữ tương đương.

### 3.1. Ước lượng bộ nhớ phụ thuộc dữ liệu

Một hash aggregate có thể cần bộ nhớ gần với số nhóm phân biệt và kích thước state của mỗi nhóm. Sort cần giữ các hàng và khóa sắp xếp. Hash join cần cấu trúc hash, khóa, payload và overhead.

Ước lượng đơn giản:

\[
M_{\text{needed}} \approx N \times (S_{\text{row}} + S_{\text{overhead}})
\]

Trong đó:

- N là số hàng cần giữ trong vùng làm việc.
- S_row là kích thước dữ liệu cần thiết cho mỗi hàng.
- S_overhead là overhead của cấu trúc sort/hash, con trỏ, bucket và metadata.

Đây chỉ là mô hình khái niệm. Engine có thể dùng thuật toán khác, nén, cấp phát theo từng giai đoạn hoặc chia dữ liệu thành nhiều partition.

### 3.2. Cardinality estimate sai

Optimizer dự đoán số hàng quá thấp có thể cấp bộ nhớ nhỏ hơn nhu cầu thực. Ví dụ, thống kê cũ cho biết một điều kiện lọc trả 1.000 hàng nhưng thực tế trả 2 triệu hàng. Sort hoặc hash operator có thể spill.

Estimate quá cao cũng gây hại: optimizer có thể yêu cầu memory grant lớn, làm các truy vấn khác phải chờ dù truy vấn hiện tại không dùng hết grant.

Hãy so sánh estimated rows và actual rows tại từng operator, đặc biệt ở đầu vào của sort, hash join và aggregate.

### 3.3. Concurrency làm nhu cầu tổng tăng

Một truy vấn có thể dùng bộ nhớ chấp nhận được khi chạy đơn lẻ. Khi 30 bản chạy đồng thời, tổng memory grant hoặc work area có thể vượt ngân sách.

\[
M_{\text{total}} \approx \sum_{i=1}^{C} M_i + M_{\text{shared}} + M_{\text{engine}}
\]

Trong đó C là số truy vấn đồng thời, M_i là vùng làm việc của truy vấn i, còn các thành phần còn lại là bộ nhớ dùng chung và overhead của engine. Đây là mô hình sizing sơ bộ; cơ chế cấp phát thực tế khác nhau theo sản phẩm.

Không được coi một tham số như work_mem hoặc memory grant là ngân sách tổng cho cả server. Một truy vấn có thể có nhiều operator cần bộ nhớ, nhiều worker song song và nhiều session đồng thời.

## 4. Nhận diện spill trong execution plan

Hãy tìm các operator sort, hash, aggregate, window hoặc materialize và xem chúng có dùng vùng tạm hay không. Tên cảnh báo tùy hệ quản trị:

- Sort spill hoặc external sort.
- Hash warning, hash bailout hoặc partitioning nhiều pass.
- Spill level, spill count hoặc spilled bytes.
- Temp read/write, workfile hoặc worktable activity.
- One-pass/multi-pass work area.

Đọc actual execution plan thay vì chỉ đọc estimated plan nếu môi trường cho phép. Actual plan giúp đối chiếu cardinality thực, số lần operator chạy và số hàng đi qua từng bước.

### 4.1. Những câu hỏi cần trả lời

1. Operator nào spill?
2. Spill xảy ra ở một truy vấn hay nhiều truy vấn?
3. Số byte hoặc số trang được ghi/đọc tạm là bao nhiêu?
4. Operator nhận bao nhiêu hàng thực tế và optimizer ước lượng bao nhiêu?
5. Có skew khiến một worker hoặc partition giữ nhiều dữ liệu hơn không?
6. Spill xuất hiện ở concurrency nào?
7. Thời gian truy vấn tăng chủ yếu ở CPU, memory grant wait hay temp I/O?

### 4.2. Không kết luận chỉ từ một metric

Temp bytes tăng có thể đến từ temporary table, sort/hash spill, version store, index build hoặc tác vụ bảo trì. Memory thấp cũng có thể là hành vi bình thường của cache management. Cần liên kết metric với query, session, operator và thời điểm sự cố.

## 5. Phân biệt bộ nhớ của query với cache của database

Buffer cache giữ các trang dữ liệu được truy cập để giảm physical I/O. Query work area giữ dữ liệu trung gian trong lúc operator thực thi. Hai mục đích khác nhau:

- Tăng buffer cache có thể giảm đọc đĩa nếu working set được tái sử dụng.
- Tăng work area có thể giảm spill của sort/hash.
- Tăng một loại bộ nhớ có thể làm giảm phần ngân sách còn lại cho loại khác nếu tổng RAM bị giới hạn.

Nếu truy vấn spill vì memory grant nhỏ, tăng buffer cache không nhất thiết giải quyết được vấn đề. Nếu truy vấn đọc nhiều trang do thiếu index, tăng work area cũng không loại bỏ lượng logical reads.

Phải xác định đúng pool, vùng nhớ hoặc cơ chế cấp phát mà operator sử dụng trước khi điều chỉnh cấu hình.

## 6. Vùng tạm lớn lên do những hoạt động nào?

Temp-space usage có thể đến từ nhiều nguồn:

| Nguồn | Ví dụ | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| Sort/hash spill | ORDER BY, hash join, GROUP BY | Spill warning, workfile, temp read/write |
| Temporary table | Bảng tạm của ứng dụng hoặc stored procedure | Temp table count, session allocation |
| Materialization | CTE/materialized intermediate hoặc spool | Plan operator, temp allocation |
| Version store | Row version cho snapshot, online operation hoặc tính năng tương tự | Version store usage, transaction lâu |
| Index build/rebuild | Sort dữ liệu để tạo chỉ mục | Temp usage tăng trong thời gian bảo trì |
| Backup/restore/staging | File trung gian hoặc vùng staging | I/O và dung lượng theo job |
| Replication/maintenance | Tác vụ nội bộ của engine | Job, session và metric dịch vụ |

Không nên quy mọi mức tăng temp cho một truy vấn chậm. Hãy xem nguồn cấp phát và thời gian tồn tại của từng loại dữ liệu tạm.

## 7. Dấu hiệu filesystem hoặc volume sắp hết dung lượng

Các dấu hiệu phổ biến:

- Free space giảm liên tục trong lúc workload chạy.
- Temp file hoặc transaction log tăng nhanh.
- Auto-growth thất bại hoặc phải tăng file nhiều lần.
- Database trả lỗi không thể ghi file, không thể mở rộng file hoặc hết quota.
- Backup, index build, sort hoặc batch job thất bại.
- Latency tăng do storage gần đầy, bị giới hạn throughput hoặc phải mở rộng file.
- Một volume đầy trong khi volume khác vẫn còn nhiều dung lượng.

Dung lượng trống của filesystem không luôn bằng dung lượng mà database có thể dùng. Có thể còn quota theo user/project, giới hạn kích thước file, giới hạn service tier, vùng lưu trữ riêng hoặc policy của nhà cung cấp.

### 7.1. Kiểm tra ở cấp hệ điều hành

Trên Linux, các lệnh thường dùng:

~~~bash
df -h
df -i
lsblk
du -xhd1 /path/to/database-or-temp
iostat -xz 1
vmstat 1
free -h
~~~

Ý nghĩa:

- df -h: dung lượng đã dùng và còn trống của filesystem.
- df -i: inode còn lại; filesystem có thể không tạo file mới dù byte còn trống nếu inode cạn.
- lsblk: thiết bị block và mount point.
- du: thư mục đang chiếm dung lượng; cần chọn đúng path và quyền.
- iostat: mức hoạt động, queue và latency thiết bị.
- vmstat/free: memory, swap và hoạt động hệ thống.

Các lệnh chỉ là ví dụ cho Linux. Trên Windows hoặc dịch vụ managed, dùng công cụ hệ điều hành và metric do nền tảng cung cấp. Không xóa file database, temp hoặc log thủ công để giải phóng chỗ.

### 7.2. Xác định đúng volume

Lập bản đồ file:

- Data files.
- Transaction log/WAL/redo.
- Temp files hoặc temp tablespace.
- Backup và archive logs.
- Staging/export files.
- System files và log của ứng dụng.

Nếu data, log và temp cùng nằm trên một volume, một tác vụ ghi log hoặc backup có thể làm temp không còn chỗ. Nếu tách volume, phải kiểm tra từng volume và giới hạn tổng hợp của instance/cloud service.

## 8. Quy trình điều tra sự cố theo thời gian

Khi nhận cảnh báo memory/temp/disk, nên giữ lại mốc thời gian và thực hiện theo thứ tự:

1. **Xác định phạm vi:** database, instance, node, filesystem, volume hay service tier nào bị ảnh hưởng.
2. **Ghi nhận triệu chứng:** lỗi cụ thể, thời điểm bắt đầu, query/job thất bại, latency và mức tải.
3. **Chụp số liệu hiện tại:** free memory, memory grant/work area, temp usage, disk free, IOPS, throughput, latency và queue.
4. **Tìm session/query tiêu thụ:** xác định session, SQL ID, query hash hoặc job có allocation lớn.
5. **Đọc execution plan:** tìm sort/hash spill, estimated/actual rows, join fanout và temp operator.
6. **Kiểm tra concurrency:** số truy vấn cùng chạy, memory grant pending, active transactions và pool usage.
7. **Kiểm tra tác vụ nền:** backup, index build, ETL, vacuum, replication hoặc batch.
8. **Kiểm tra dung lượng vật lý:** file growth, filesystem, inode, quota và giới hạn dịch vụ.
9. **Xác định nguyên nhân gốc:** query plan, thống kê, dữ liệu skew, concurrency, cấu hình hay capacity.
10. **Áp dụng biện pháp có kiểm soát:** thay đổi query, index, memory, concurrency hoặc storage theo bằng chứng.
11. **Đo lại:** xác nhận spill, temp peak, disk free, latency và kết quả nghiệp vụ.

Nếu dung lượng đang cạn và dịch vụ có nguy cơ dừng, cần ưu tiên bảo vệ khả năng ghi và phục hồi dịch vụ theo quy trình vận hành. Việc mở rộng volume hoặc tăng quota có thể là biện pháp khẩn cấp, nhưng vẫn phải tìm nguyên nhân làm dung lượng tăng.

## 9. PostgreSQL: temp files, work_mem và temporary tablespace

PostgreSQL có thể ghi file tạm khi sort, hash hoặc một số operator không thể giữ toàn bộ dữ liệu trung gian trong bộ nhớ. Các metric và cấu hình hữu ích:

- pg_stat_database.temp_files và temp_bytes: số file tạm và tổng byte tạm theo database.
- pg_stat_statements.temp_blks_read và temp_blks_written: block tạm theo statement nếu extension/phiên bản hỗ trợ các cột này.
- log_temp_files: ghi log các file tạm vượt ngưỡng cấu hình.
- work_mem: giới hạn bộ nhớ cơ sở cho một số operation như sort và hash.
- hash_mem_multiplier: hệ số áp dụng cho hash operation ở các phiên bản hỗ trợ.
- temp_file_limit: giới hạn dung lượng file tạm mà một process được phép sử dụng theo quy tắc của PostgreSQL.
- temp_tablespaces: vị trí đặt file tạm.

### 9.1. Xem thống kê temp theo database

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

Đây là bộ đếm tích lũy từ lần reset thống kê. Hãy lấy hai mẫu theo thời gian để tính delta, thay vì so sánh số tuyệt đối giữa các database có tuổi thống kê khác nhau.

### 9.2. Tìm statement tạo temp I/O

Khi pg_stat_statements được cài và bật, có thể xem các statement có temp block lớn:

~~~sql
SELECT
    queryid,
    calls,
    rows,
    temp_blks_read,
    temp_blks_written,
    total_exec_time,
    query
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

Tên cột và quyền truy cập phụ thuộc phiên bản, extension và cấu hình. Query text có thể bị chuẩn hóa hoặc rút gọn. Dùng queryid cùng thời điểm log để đối chiếu.

### 9.3. Điều chỉnh work_mem có kiểm soát

work_mem không phải tổng bộ nhớ cho toàn server. Một truy vấn có thể có nhiều sort/hash node; parallel query có thể dùng nhiều worker; nhiều session có thể hoạt động đồng thời. Tăng work_mem toàn cục quá mạnh có thể làm memory pressure hoặc OOM.

Ưu tiên:

- Tối ưu số hàng đi vào sort/hash bằng filter và join đúng.
- Cập nhật statistics để optimizer ước lượng đúng.
- Xem có index hỗ trợ ORDER BY hoặc điều kiện lọc không.
- Thử điều chỉnh work_mem ở session hoặc transaction cụ thể sau khi tính concurrency.
- Theo dõi temp bytes và memory trong tải đại diện.

Có thể dùng SET LOCAL trong transaction để giới hạn phạm vi cấu hình cho một tác vụ đã được kiểm soát, nhưng phải đảm bảo application pool không để cấu hình session rò sang request khác.

## 10. SQL Server: memory grant, spills và tempdb

SQL Server dùng memory grant cho các operator như sort và hash. Khi grant không đủ, một số operator có thể spill xuống tempdb. tempdb cũng được dùng cho temporary table, table variable, version store và nhiều hoạt động nội bộ.

Các tín hiệu cần theo dõi:

- Memory Grants Pending và Memory Grants Outstanding.
- Sort/hash spill warning trong actual execution plan.
- Spill level, spilled data size hoặc tempdb usage theo query khi phiên bản cung cấp.
- Wait liên quan RESOURCE_SEMAPHORE.
- tempdb data/log file usage và tốc độ tăng.
- Version store usage nếu workload dùng row versioning.

### 10.1. Xem phân bổ trang trong tempdb

~~~sql
USE tempdb;

SELECT
    total_page_count,
    unallocated_extent_page_count,
    version_store_reserved_page_count,
    user_object_reserved_page_count,
    internal_object_reserved_page_count
FROM sys.dm_db_file_space_usage;
~~~

Các cột biểu diễn số trang. Nhân với page size của SQL Server để quy đổi dung lượng. View này cung cấp góc nhìn tổng hợp theo file; cần đối chiếu session/task và version store để tìm nguồn tăng.

### 10.2. Tìm session dùng nhiều tempdb

~~~sql
SELECT
    session_id,
    user_objects_alloc_page_count,
    user_objects_dealloc_page_count,
    internal_objects_alloc_page_count,
    internal_objects_dealloc_page_count
FROM sys.dm_db_session_space_usage
ORDER BY
    (user_objects_alloc_page_count - user_objects_dealloc_page_count
     + internal_objects_alloc_page_count - internal_objects_dealloc_page_count) DESC;
~~~

Các bộ đếm là số trang đã cấp phát/giải phóng theo session và có phạm vi tích lũy theo vòng đời session. Với task đang chạy, cần xem thêm sys.dm_db_task_space_usage và kết hợp session request, SQL text, plan handle. Quyền DMV phụ thuộc phiên bản và quyền server.

### 10.3. Giảm spill và bảo vệ tempdb

- So estimated rows với actual rows.
- Kiểm tra statistics, parameter sensitivity và plan regression.
- Giảm hàng trước sort/hash bằng filter và projection phù hợp.
- Xem index có hỗ trợ thứ tự hoặc join key không.
- Xem memory grant có quá nhỏ hoặc quá lớn.
- Giới hạn concurrency của báo cáo hoặc batch nặng.
- Kiểm tra tempdb data files, growth setting, dung lượng volume và latency.
- Điều tra version store khi transaction snapshot kéo dài.

Không tăng memory grant hoặc cấp thêm RAM theo một query đơn lẻ mà chưa đánh giá tác động tới các request đồng thời.

## 11. MySQL InnoDB: internal temporary table và vùng tạm

MySQL có thể tạo internal temporary table cho một số GROUP BY, DISTINCT, UNION, derived table hoặc thao tác trung gian. Tùy phiên bản và cấu hình, bảng tạm có thể nằm trong memory hoặc chuyển sang lưu trữ trên đĩa.

Các tín hiệu hữu ích:

- Created_tmp_tables và Created_tmp_disk_tables.
- Performance Schema instrumentation liên quan temporary table hoặc file I/O nếu được bật.
- Kích thước file temporary và InnoDB temporary tablespace.
- tmp_table_size, max_heap_table_size và các tham số TempTable theo phiên bản.
- Disk free, I/O latency và tốc độ tăng file.

### 11.1. Xem bộ đếm temporary table

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Created_tmp_tables',
    'Created_tmp_disk_tables'
);
~~~

Đây là bộ đếm tích lũy. Lấy delta trong một khoảng thời gian và chia cho số truy vấn hoặc transaction phù hợp để hiểu xu hướng. Không phải mọi temporary table trên đĩa đều phản ánh một lỗi; một số truy vấn cần lưu trữ trung gian.

### 11.2. Thận trọng khi chỉnh giới hạn memory

Các phiên bản MySQL khác nhau có cơ chế internal temporary table khác nhau. Những tham số như tmp_table_size, max_heap_table_size, temptable_max_ram và temptable_max_mmap không có cùng phạm vi và không nên thay thế lẫn nhau. Đọc tài liệu đúng phiên bản trước khi thay đổi.

Nếu tăng giới hạn memory cho mỗi bảng tạm mà có nhiều truy vấn đồng thời, tổng bộ nhớ có thể tăng vượt dự tính. Hãy xem số lượng bảng tạm đồng thời, kích thước dữ liệu và mức dùng memory của toàn instance.

### 11.3. Tối ưu truy vấn

- Giảm cột và số hàng trước khi GROUP BY hoặc DISTINCT.
- Xem index hỗ trợ điều kiện lọc và thứ tự truy cập.
- Tránh tạo derived result rất lớn không cần thiết.
- Đo tác động của sort, join và aggregation trên dữ liệu thật.
- Xem plan bằng EXPLAIN và công cụ phân tích của phiên bản.

## 12. Oracle: PGA work area và TEMP tablespace

Oracle sử dụng PGA cho work area của sort, hash join, bitmap operation và một số thao tác khác. Nếu work area không đủ, thao tác có thể chạy one-pass hoặc multi-pass và dùng TEMP tablespace.

Các khái niệm:

- PGA: bộ nhớ riêng của process/session server, gồm work area và thành phần khác.
- SGA: vùng nhớ dùng chung cho instance.
- Automatic workarea sizing: cơ chế quản lý work area theo cấu hình và tải.
- TEMP tablespace: lưu dữ liệu tạm khi thao tác không thể giữ toàn bộ trong PGA hoặc khi ứng dụng tạo temporary segment.

### 12.1. Quan sát work area đang hoạt động

~~~sql
SELECT
    sid,
    sql_id,
    operation_type,
    actual_mem_used,
    max_mem_used,
    number_passes,
    tempseg_size
FROM v$sql_workarea_active
ORDER BY tempseg_size DESC NULLS LAST;
~~~

View và cột có thể phụ thuộc phiên bản/quyền. number_passes lớn hơn 0 cho thấy thao tác cần pass bổ sung; tempseg_size giúp nhận diện thao tác đang dùng TEMP.

### 12.2. Xem session dùng TEMP

~~~sql
SELECT
    username,
    session_addr,
    session_num,
    sql_id,
    tablespace,
    segtype,
    blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

Có thể JOIN với V$SESSION theo địa chỉ session để bổ sung serial number, machine, program và trạng thái. Cần lưu ý view chỉ phản ánh allocation hiện tại; truy vấn đã kết thúc có thể giải phóng segment và không còn xuất hiện.

### 12.3. Điều chỉnh PGA và TEMP

- Xem PGA target/limit, workarea policy và mức sử dụng thực tế.
- Xác định query có one-pass hoặc multi-pass do work area thiếu.
- So cardinality estimate với actual rows.
- Giảm dữ liệu trung gian và kiểm tra plan.
- Kiểm soát concurrency của báo cáo nặng.
- Kiểm tra TEMP tablespace có đủ chỗ, autoextend và giới hạn file.

Không tăng PGA_AGGREGATE_TARGET hoặc giới hạn PGA chỉ dựa trên một session. Phải tính ngân sách RAM cho toàn instance và các process khác.

## 13. Tìm truy vấn gây tràn bộ nhớ hoặc temp

Một truy vấn đáng điều tra thường có một hoặc nhiều đặc điểm:

- Sort hoặc hash xử lý số hàng lớn hơn dự kiến.
- Estimated rows lệch nhiều so với actual rows.
- JOIN tạo fanout lớn vì khóa không duy nhất hoặc điều kiện JOIN thiếu.
- GROUP BY có số nhóm rất cao.
- DISTINCT loại bỏ ít bản ghi so với tập đầu vào.
- SELECT lấy cột rộng hoặc LOB không cần thiết.
- Query chạy song song với nhiều worker.
- Nhiều phiên chạy cùng truy vấn vào giờ cao điểm.

### 13.1. Kiểm tra cardinality và thống kê

Thống kê cũ hoặc thiếu histogram có thể làm optimizer đánh giá sai phân bố dữ liệu. Với cột lệch, một giá trị phổ biến có thể trả về nhiều hàng hơn rất nhiều so với giá trị thông thường.

Kiểm tra:

- Thời điểm cập nhật statistics gần nhất.
- Số hàng và distinct values ước lượng.
- Histogram hoặc thống kê phân bố nếu engine hỗ trợ.
- Parameter-sensitive plan.
- Correlation giữa nhiều cột lọc.
- Dữ liệu mới tăng nhanh sau lần thu thập thống kê.

Sau khi cập nhật statistics, so actual plan và hiệu năng ở nhiều tham số. Không mặc định statistics mới luôn làm plan tốt hơn nếu histogram hoặc sampling chưa đại diện.

### 13.2. Kiểm tra join fanout

Nếu một hàng phía trái khớp với nhiều hàng phía phải, số hàng trung gian có thể tăng rất nhanh. Ví dụ một JOIN thiếu điều kiện theo tenant hoặc thời gian có thể nhân bản kết quả.

Đếm số hàng trước và sau mỗi phép JOIN, xác nhận khóa và cardinality kỳ vọng. Với quan hệ một-nhiều, phải kiểm tra liệu truy vấn có cần tất cả hàng con hay chỉ cần EXISTS, aggregate trước hoặc chọn một bản ghi đại diện.

### 13.3. Kiểm tra projection và row width

SELECT * hoặc lấy nhiều cột không dùng làm tăng dữ liệu phải đọc, truyền, sort hoặc hash. Với hàng có JSON, text, XML hoặc LOB lớn, overhead có thể đáng kể.

Chỉ chọn cột cần thiết, tránh đưa payload lớn vào sort/hash nếu có thể xử lý metadata trước rồi lấy payload sau.

## 14. Giảm spill bằng thay đổi SQL và execution plan

Ưu tiên giảm lượng dữ liệu trung gian trước khi tăng memory.

### 14.1. Lọc sớm

Đưa điều kiện lọc có thể áp dụng sớm vào truy vấn hoặc nhánh con để giảm số hàng đi vào join, sort và aggregate. Optimizer có thể tự đẩy predicate; hãy kiểm tra plan thay vì chỉ nhìn vị trí viết điều kiện trong SQL.

### 14.2. Chọn cột cần thiết

~~~sql
-- Tránh chuyển nhiều cột không cần thiết qua operator
SELECT customer_id, SUM(amount) AS total_amount
FROM orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

Nếu truy vấn chỉ cần customer_id và amount, không kéo theo mô tả, JSON hoặc payload lớn.

### 14.3. Tổng hợp trước khi JOIN khi đúng ngữ nghĩa

Nếu một bảng chi tiết có rất nhiều hàng nhưng truy vấn chỉ cần tổng theo order_id, có thể aggregate trước rồi JOIN với bảng còn lại. Cần xác minh phép biến đổi không làm thay đổi kết quả, đặc biệt với NULL, DISTINCT và điều kiện lọc.

### 14.4. Dùng index đúng mục tiêu

Index có thể giảm rows examined, hỗ trợ filter và ORDER BY, hoặc giúp join theo khóa. Tuy nhiên, index không phải giải pháp tự động:

- Index rộng có thể tăng write cost và dung lượng.
- Index không phù hợp có thể không tránh được sort.
- Một truy vấn trả phần lớn bảng có thể vẫn cần scan.
- Index mới có thể làm optimizer chọn plan khác; phải kiểm tra actual plan.

### 14.5. Chia batch hoặc phân trang theo khóa

Một truy vấn lớn có thể được chia thành các batch nhỏ theo khóa ổn định để giới hạn tập dữ liệu mỗi lần. Keyset pagination thường tránh chi phí OFFSET lớn và giảm vùng trung gian so với quét lại từ đầu.

Tuy nhiên, chia batch có thể làm các batch nhìn thấy snapshot khác nhau. Nếu cần báo cáo nhất quán tại một thời điểm, cần snapshot, watermark hoặc cơ chế dữ liệu phù hợp.

### 14.6. Xử lý heavy group và skew

Một khóa có quá nhiều hàng có thể khiến một worker hoặc hash partition trở thành nút thắt. Với phép tổng hợp kết hợp được, có thể dùng partial aggregation hoặc salting rồi merge kết quả. Với DISTINCT, median hoặc percentile, phải dùng thuật toán/state merge đúng ngữ nghĩa; không cộng kết quả trung gian một cách máy móc.

## 15. Điều chỉnh bộ nhớ và concurrency an toàn

Sau khi giảm dữ liệu trung gian và xác minh estimate, có thể cần điều chỉnh vùng nhớ. Hãy thực hiện theo phạm vi hẹp và đo tác động.

### Nguyên tắc

- Xác định bộ nhớ thuộc operator, session, process hay instance.
- Tính số operation đồng thời và số worker song song.
- Giữ ngân sách cho OS, buffer cache, connection/session và background task.
- Thử ở session, workload class hoặc query cụ thể nếu engine hỗ trợ.
- Theo dõi grant wait, spill bytes, memory peak và lỗi OOM.
- Trả cấu hình về mặc định nếu cải thiện không bù được rủi ro.

### Giới hạn concurrency

Nếu một báo cáo cần vùng làm việc lớn, chạy 20 báo cáo cùng lúc có thể làm tổng nhu cầu vượt RAM và TEMP. Có thể:

- Giới hạn số báo cáo nặng chạy đồng thời.
- Đưa báo cáo vào queue có giới hạn.
- Chạy batch theo cửa sổ thời gian.
- Tách workload phân tích khỏi OLTP nếu kiến trúc cho phép.
- Đặt resource group hoặc workload management policy.

Giới hạn concurrency có thể làm tăng thời gian chờ bắt đầu tác vụ, nhưng giúp bảo vệ latency của giao dịch quan trọng và ngăn temp exhaustion.

## 16. Lập ngân sách dung lượng vùng tạm

Dung lượng TEMP cần tính theo peak concurrent usage, không chỉ theo dung lượng trung bình.

Một mô hình lập kế hoạch:

\[
T_{\text{required}} \geq
\sum_{i=1}^{C} T_i + T_{\text{background}} + T_{\text{reserve}}
\]

Trong đó:

- T_i là temp peak của từng workload đồng thời.
- C là số workload có thể chạy đồng thời.
- T_background là dung lượng cho version store, index build, maintenance hoặc tác vụ nền.
- T_reserve là phần dự phòng cho biến động và tăng trưởng.

Ví dụ, nếu có thể đồng thời chạy 4 truy vấn báo cáo, mỗi truy vấn có temp peak 12 GB, tác vụ nền cần 10 GB và dự phòng 30% trên tổng nhu cầu cơ sở:

\[
T_{\text{base}} = 4 \times 12 + 10 = 58\text{ GB}
\]

\[
T_{\text{required}} \approx 58 \times 1,3 = 75,4\text{ GB}
\]

Đây là ví dụ capacity planning, không phải cấu hình khuyến nghị chung. Hãy dùng peak đo được, tính cả file growth, quota, dung lượng log và giới hạn của dịch vụ.

### Dung lượng không phải năng lực I/O

Một volume có đủ dung lượng vẫn có thể không đáp ứng IOPS, throughput hoặc latency khi nhiều truy vấn spill. Ngược lại, volume có tốc độ cao nhưng quá nhỏ vẫn có thể đầy.

Theo dõi riêng:

- Free bytes và tỷ lệ sử dụng.
- Tốc độ tăng dung lượng theo phút/giờ.
- IOPS và throughput đọc/ghi.
- Latency và queue depth.
- File growth events.
- Quota và giới hạn volume/service tier.

## 17. Tăng dung lượng và xử lý khi gần đầy

Khi temp hoặc filesystem gần đầy, lựa chọn phụ thuộc nguyên nhân và khả năng nền tảng:

- Mở rộng volume hoặc quota nếu nhu cầu hợp lệ và có thể dự báo.
- Tăng kích thước temp file hoặc thêm file theo hướng dẫn của engine.
- Chuyển temp sang volume riêng nếu kiến trúc hỗ trợ và giới hạn tổng hợp không bị chạm.
- Dừng hoặc điều tiết job không thiết yếu theo quy trình vận hành.
- Giải phóng dữ liệu tạm đã hết vòng đời bằng cơ chế của database.
- Xử lý transaction hoặc session giữ version/temp lâu nếu đã xác định an toàn.

Không xóa file tạm đang được database sử dụng, không xóa transaction log để lấy chỗ và không xóa file dữ liệu thủ công. Những thao tác đó có thể làm hỏng database hoặc khiến instance không thể phục hồi.

### Dự báo thời gian còn lại

Nếu free space hiện tại là F và tốc độ tăng dung lượng ròng là G byte/giây, thời gian ước lượng đến khi đầy:

\[
T_{\text{remaining}} \approx \frac{F}{G}
\]

Ví dụ còn 90 GB và tăng ròng 1,5 GB/phút:

\[
T_{\text{remaining}} \approx 60\text{ phút}
\]

Phép tính chỉ hữu ích khi tốc độ tăng tương đối ổn định. Temp usage có thể tăng rồi giảm khi truy vấn kết thúc; hãy dùng chuỗi thời gian và peak usage, không ngoại suy một mẫu ngắn.

## 18. Kiểm chứng sau điều chỉnh

Mỗi thay đổi phải được đo trong cùng workload hoặc profile đại diện. Ghi lại baseline và kết quả sau thay đổi:

| Chỉ số | Điều cần xác nhận |
| --- | --- |
| Actual vs estimated rows | Cardinality estimate có sát hơn không |
| Spill count/bytes | Operator spill có giảm không |
| Memory grant/work area | Grant có đủ và không lãng phí quá mức không |
| Temp peak | Peak temp usage có giảm và còn headroom không |
| Disk free/growth | Dung lượng có ổn định và tăng theo dự báo không |
| Temp IOPS/latency | Storage có còn là nút thắt không |
| Query p50/p95/p99 | Truy vấn có nhanh hơn ở tải đại diện không |
| Concurrency | Nhiều truy vấn cùng chạy có ổn định không |
| CPU/cache/I/O | Có chuyển nút thắt sang tài nguyên khác không |
| Correctness | Kết quả SQL và dữ liệu nghiệp vụ còn chính xác không |

Chạy cả truy vấn đơn lẻ và mixed workload. Một cấu hình làm truy vấn riêng lẻ nhanh hơn nhưng tăng memory peak đến mức giảm concurrency có thể làm hệ thống tổng thể kém ổn định.

### Kiểm thử các tình huống biên

- Dữ liệu lớn hơn dự kiến.
- Tham số lọc phổ biến và hiếm.
- Nhiều báo cáo đồng thời.
- Batch hoặc index build chạy cùng OLTP.
- Transaction dài và version store tăng.
- Temp volume gần ngưỡng cảnh báo.
- Tải tăng đột ngột rồi giảm.

Đảm bảo cảnh báo được kích hoạt trước khi vùng tạm hoặc filesystem cạn. Xác nhận quy trình điều tiết hoặc mở rộng hoạt động đúng.

## 19. Ví dụ điều tra: báo cáo GROUP BY làm temp tăng nhanh

Một báo cáo tổng hợp doanh thu chạy trên bảng orders lớn. Khi chạy đơn lẻ, truy vấn hoàn tất nhưng ghi nhiều dữ liệu tạm. Khi có sáu báo cáo đồng thời, temp volume tăng nhanh và một số truy vấn thất bại.

~~~sql
SELECT
    customer_id,
    region_id,
    SUM(amount) AS revenue
FROM orders
WHERE order_date >= DATE '2026-01-01'
GROUP BY customer_id, region_id
ORDER BY revenue DESC;
~~~

Quy trình điều tra:

1. Ghi nhận temp free space, tốc độ tăng, temp I/O và thời điểm bắt đầu lỗi.
2. Xác định sáu session đang chạy cùng SQL và thời gian của mỗi session.
3. Đọc actual plan, kiểm tra rows vào aggregate, số nhóm thực tế và sort sau aggregate.
4. So estimated rows với actual rows; kiểm tra statistics và phân bố customer/region.
5. Xem mỗi truy vấn spill bao nhiêu byte và temp peak theo session.
6. Kiểm tra SELECT có cần toàn bộ dữ liệu và có thể lọc theo partition ngày hay không.
7. Thử giảm dữ liệu đầu vào, kiểm tra index và partial aggregation nếu phù hợp.
8. Giới hạn số báo cáo nặng chạy đồng thời để bảo vệ OLTP.
9. Tính lại temp capacity theo số báo cáo tối đa và peak đã đo.
10. Chạy lại cùng mix, xác nhận temp peak, p95, throughput và kết quả doanh thu.

Nếu sau khi tối ưu mỗi báo cáo vẫn cần 8 GB TEMP và hệ thống cho phép tối đa sáu báo cáo đồng thời, capacity planning phải dựa trên tổng peak tương ứng cùng phần dự phòng. Không nên chỉ cấp thêm dung lượng rồi bỏ qua việc kiểm soát concurrency.

## 20. Những sai lầm thường gặp

### Tăng bộ nhớ ngay khi thấy spill

Spill có thể do estimate sai, join fanout, row width lớn hoặc concurrency. Tăng memory mà không sửa nguyên nhân có thể làm OOM hoặc giảm số truy vấn chạy đồng thời.

### Tăng work_mem hoặc memory grant toàn cục

Một operation có thể dùng nhiều vùng làm việc và nhiều worker. Cần tính tổng nhu cầu ở concurrency mục tiêu trước khi tăng cấu hình.

### Coi mọi temp usage là bất thường

Temporary table, version store, index build và sort lớn có thể dùng TEMP hợp lệ. Cần xác định nguồn và thời gian tồn tại.

### Chỉ theo dõi dung lượng trống

Volume có thể còn chỗ nhưng IOPS, throughput hoặc latency đã bão hòa. Theo dõi cả capacity và I/O.

### Chỉ xem truy vấn đơn lẻ

Sự cố có thể chỉ xuất hiện khi nhiều query hoặc batch cùng chạy. Kiểm thử concurrency và mixed workload.

### Xóa file để giải phóng dung lượng

Xóa file database, temp đang hoạt động hoặc log thủ công có thể gây hỏng dữ liệu. Dùng cơ chế quản trị của engine và quy trình vận hành.

### Bỏ qua version store và transaction lâu

Snapshot hoặc transaction kéo dài có thể giữ phiên bản cũ và làm vùng tạm tăng dù query spill không đáng kể. Kiểm tra transaction age và cơ chế versioning.

### Mở rộng storage mà không tính tốc độ tăng

Thêm dung lượng chỉ kéo dài thời gian đến khi đầy nếu workload vẫn tạo temp vượt khả năng giải phóng. Dự báo growth và đặt cảnh báo.

## 21. Quy trình xử lý chuẩn

1. Xác định loại sự cố: memory pressure, operator spill, temp-space pressure hay storage exhaustion.
2. Xác định database, node, volume, filesystem và service tier bị ảnh hưởng.
3. Lưu error, timestamp, query/session/job và metric trước khi thay đổi.
4. Tìm nguồn cấp phát temp hoặc memory lớn nhất.
5. Đọc actual execution plan, estimated/actual rows, spill và join fanout.
6. Kiểm tra statistics, data skew, row width, index và filter.
7. Đo concurrency, memory grant pending, transaction age và tác vụ nền.
8. Kiểm tra dung lượng, inode, quota, file growth, IOPS, throughput và latency.
9. Giảm dữ liệu trung gian bằng SQL/plan hoặc chia batch nếu đúng ngữ nghĩa.
10. Điều chỉnh memory và concurrency theo ngân sách toàn hệ thống.
11. Mở rộng temp/storage khi nhu cầu hợp lệ và đã tính peak cùng headroom.
12. Kiểm chứng bằng workload đơn lẻ và mixed workload, xác nhận tính đúng đắn.
13. Thiết lập cảnh báo theo xu hướng, tốc độ tăng và thời gian còn lại.

## 22. Nguyên tắc cần ghi nhớ

- Memory pressure, operator spill, temp-space pressure và storage exhaustion là bốn hiện tượng khác nhau.
- Sort, hash join, aggregate và window operation có thể spill khi vùng làm việc không đủ.
- Cardinality estimate sai, row width lớn, join fanout và data skew thường làm tăng nhu cầu memory/temp.
- Một query chạy tốt riêng lẻ vẫn có thể gây sự cố khi nhiều query chạy đồng thời.
- PostgreSQL work_mem, SQL Server memory grant/tempdb, MySQL internal temporary table và Oracle PGA/TEMP có cơ chế riêng; phải đọc tài liệu đúng phiên bản.
- Temp usage còn có thể đến từ temporary table, version store, index build và tác vụ nền.
- Kiểm tra actual execution plan và gắn spill/temp allocation với query, session và thời điểm.
- Giảm dữ liệu trung gian và sửa estimate trước khi tăng memory.
- Tính temp capacity từ peak concurrent usage, tác vụ nền và headroom.
- Dung lượng trống không phản ánh IOPS, throughput hoặc latency; theo dõi cả capacity lẫn I/O.
- Không xóa file database, temp đang hoạt động hoặc transaction log thủ công.
- Đo lại bằng workload đại diện, concurrency thực tế và kiểm tra tính đúng đắn sau mọi điều chỉnh.

Tràn bộ nhớ và vùng tạm là kết quả của cách truy vấn xử lý dữ liệu, cách engine cấp phát work area và mức tải đồng thời. Khi phân biệt rõ spill với thiếu dung lượng vật lý, tìm được operator và session gây tiêu thụ, rồi đối chiếu execution plan, thống kê, temp I/O và tốc độ tăng storage, nhóm vận hành có thể chọn đúng biện pháp. Tối ưu truy vấn, điều chỉnh concurrency, cấp phát memory và mở rộng storage cần phối hợp để giữ hiệu năng ổn định mà vẫn bảo toàn tính đúng đắn của dữ liệu.

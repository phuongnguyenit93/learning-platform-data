# I/O cao: phân biệt quét dữ liệu, truy xuất ngẫu nhiên và ghi nền

Trong chương **Chẩn đoán sự cố** của module **DATABASE_PERFORMANCE**, I/O cao là dấu hiệu cần điều tra theo đường đi của dữ liệu, không phải kết luận rằng ổ đĩa đã hỏng hoặc cần nâng cấp ngay. Database có thể đọc nhiều page do table scan, thực hiện hàng loạt random lookup qua index, ghi log khi commit, flush dirty page trong checkpoint, tạo temporary file khi sort/hash spill hoặc chạy các tác vụ nền như vacuum, purge, backup và index maintenance. Những hoạt động này tạo mẫu I/O khác nhau và cần cách xử lý khác nhau.

Muốn xác định nguyên nhân, hãy kết hợp execution plan, số logical/physical reads, thống kê file và wait event của database với IOPS, throughput, kích thước request, queue và latency ở hệ điều hành/storage. Một truy vấn có thể đọc nhiều page nhưng chủ yếu lấy từ buffer pool; một thiết bị có throughput cao có thể đang phục vụ backup tuần tự; một workload có IOPS cao nhưng MB/s thấp có thể đang thực hiện nhiều random lookup nhỏ. Phải đo cùng thời điểm và đúng volume trước khi kết luận.

## 1. I/O cao biểu hiện như thế nào?

I/O cao có thể xuất hiện dưới nhiều dạng:

- Read throughput tăng mạnh khi truy vấn quét bảng, index hoặc backup đọc data file.
- Read IOPS tăng nhưng throughput không cao khi nhiều truy vấn truy xuất các page nhỏ, phân tán.
- Write throughput tăng khi checkpoint, bulk load, index rebuild hoặc batch DML ghi nhiều page.
- Log flush latency tăng khi transaction commit phải chờ WAL/redo/transaction log được ghi bền vững.
- I/O queue và p95/p99 latency tăng dù throughput không tăng, cho thấy request đang chờ ở một tầng lưu trữ.
- Temp I/O tăng khi sort, hash join, aggregate hoặc truy vấn khác không đủ memory và spill ra đĩa.
- I/O tăng theo chu kỳ khi backup, autovacuum, purge, checkpoint hoặc maintenance chạy.

Không phải mọi I/O cao đều là sự cố. Một full scan có thể là lựa chọn hợp lý cho truy vấn cần đọc phần lớn bảng; backup cần đọc dữ liệu; checkpoint cần ghi dirty page để hỗ trợ phục hồi. Vấn đề cần giải quyết là I/O không cần thiết, I/O vượt năng lực bền vững hoặc I/O nền làm workload chính vi phạm SLO.

### 1.1. Phân biệt các đại lượng

| Đại lượng | Ý nghĩa | Câu hỏi giúp trả lời |
|---|---|---|
| IOPS | Số request đọc/ghi hoàn tất mỗi giây | Thiết bị xử lý bao nhiêu thao tác? |
| Throughput | Lượng dữ liệu đọc/ghi mỗi giây, thường MB/s | Tổng lượng dữ liệu truyền lớn đến đâu? |
| I/O latency | Thời gian hoàn tất một request | Một lần đọc/ghi phải chờ bao lâu? |
| Queue depth | Số request đang chờ hoặc đang xử lý | Có bao nhiêu I/O đang tranh chấp tài nguyên? |
| Request size | Kích thước request trung bình hoặc phân bố kích thước | Mỗi thao tác đang chuyển bao nhiêu dữ liệu? |
| Logical reads | Page được database đọc từ buffer/cache | Truy vấn truy cập bao nhiêu page logic? |
| Physical reads | Page cần được nạp từ tầng lưu trữ bên dưới buffer | Có bao nhiêu lần cache miss dẫn tới I/O? |
| Log flush | Ghi log để xác nhận commit hoặc phục hồi | Commit đang chờ đường log bao lâu? |

IOPS và throughput liên hệ gần đúng qua kích thước request:

\[
Throughput \approx IOPS \times AverageRequestSize
\]

Ví dụ, 10.000 IOPS với request trung bình 8 KiB tương đương khoảng 78 MiB/s. Cùng 10.000 IOPS nhưng request 64 KiB tương đương khoảng 625 MiB/s. Vì vậy, IOPS cao không tự động có nghĩa là throughput cao; cần đọc cả hai cùng request size và latency.

### 1.2. Đọc theo khoảng thời gian

Hầu hết thống kê database và OS là counter tích lũy từ lúc khởi động hoặc reset. Giá trị tổng không cho biết tốc độ hiện tại. Hãy lấy hai mẫu ở các thời điểm cách nhau một khoảng xác định rồi tính delta:

\[
Rate = \frac{Counter_{t2} - Counter_{t1}}{t2 - t1}
\]

Ví dụ, số page read tăng 120.000 trong 60 giây tương đương 2.000 page/giây trong cửa sổ đó. Ghi rõ thời điểm lấy mẫu, uptime, reset và đơn vị. Không so trực tiếp counter tích lũy của hai server có uptime khác nhau.

## 2. Ba mẫu I/O cần phân biệt

### 2.1. Quét dữ liệu tuần tự

Quét tuần tự (*sequential scan/read*) đọc một vùng dữ liệu lớn, thường theo thứ tự page hoặc block gần nhau. Các ví dụ:

- Table scan khi predicate không đủ chọn lọc hoặc bảng nhỏ.
- Index range scan đọc nhiều leaf page liên tiếp.
- Báo cáo tổng hợp đọc phần lớn partition.
- Backup, export hoặc consistency check đọc data file.
- Tác vụ maintenance duyệt toàn bảng/index.

Các dấu hiệu thường gặp:

- Throughput đọc tương đối cao.
- Request size trung bình có thể lớn hơn do read-ahead hoặc gộp request.
- Số page đọc lớn, có thể tăng theo kích thước bảng hoặc phạm vi truy vấn.
- CPU có thể tăng do lọc, join, aggregate hoặc giải nén dữ liệu.
- I/O có thể kéo dài liên tục trong thời gian scan.

Không phải scan nào cũng tuần tự hoàn toàn ở tầng thiết bị. Heap/table layout, partition, parallel workers, filesystem, cache và storage stack có thể làm request bị phân mảnh hoặc xen kẽ. Một truy vấn sequential scan trên plan không bảo đảm mọi I/O vật lý là tuần tự; cần đối chiếu plan và metric thiết bị.

### 2.2. Truy xuất ngẫu nhiên

Truy xuất ngẫu nhiên (*random access*) đọc nhiều page ở vị trí phân tán. Ví dụ:

- Point lookup qua B-tree index rồi lấy row từ heap/table.
- Nested-loop join thực hiện lookup lặp lại cho từng dòng bên ngoài.
- Truy vấn nhiều khóa không liền kề.
- Index lookup trên working set lớn hơn buffer pool.
- Workload nhiều tenant hoặc key phân tán.

Các dấu hiệu thường gặp:

- IOPS tăng cao trong khi throughput MB/s có thể ở mức vừa hoặc thấp.
- Request size thường nhỏ, tùy page size và storage stack.
- Cache miss làm tăng physical read; cùng một truy vấn có thể nhanh khi cache nóng và chậm khi cache lạnh.
- Latency từng request và queue có thể ảnh hưởng rõ tới p95/p99.
- Nhiều lookup nhỏ có thể tạo tổng số page read rất lớn.

SSD giảm chi phí seek cơ học so với HDD, nhưng random I/O vẫn tiêu thụ IOPS, queue, CPU và tài nguyên controller. Nếu truy vấn cần đọc hàng triệu page ngẫu nhiên, chỉ nâng cấp SSD có thể không đủ; cần giảm số lookup hoặc thay đổi access path.

### 2.3. Ghi nền và ghi theo lô

Ghi nền (*background writes*) là các thao tác ghi không nhất thiết phát sinh trực tiếp từ một câu DML của request đang được đo. Ví dụ:

- Checkpoint flush dirty data page.
- Vacuum/purge loại bỏ hoặc tái sử dụng phiên bản cũ.
- Background writer ghi page từ buffer pool.
- Index rebuild/reorganize và statistics maintenance.
- Backup snapshot metadata, archive log hoặc log shipping.
- Bulk load, ETL, retention delete và batch update.
- Temp file của sort/hash spill.

Các dấu hiệu thường gặp:

- Write IOPS/throughput tăng theo thời gian hoặc theo chu kỳ.
- Log generation, WAL/redo hoặc transaction log usage tăng.
- Checkpoint, vacuum, purge, backup hoặc maintenance job trùng với thời điểm I/O tăng.
- Data write latency, log flush latency hoặc replication lag tăng.
- Workload chính chậm dù query không có thêm nhiều logical reads.

Ghi nền có thể là công việc cần thiết. Cần xác định tác vụ nào tạo ghi, có thể điều tiết/lập lịch không và nó có đang làm log hoặc data volume bão hòa không.

## 3. Phân biệt scan lớn và random lookup bằng execution plan

Execution plan cho biết database dự định hoặc đã thực hiện access path nào. Hãy dùng actual execution plan nếu môi trường cho phép, vì estimated plan chỉ phản ánh dự đoán của optimizer.

### 3.1. Dấu hiệu scan

Các node thường gặp:

- `Seq Scan` trong PostgreSQL.
- `Table Scan` hoặc `Clustered Index Scan` trong SQL Server.
- `TABLE ACCESS FULL` trong Oracle.
- Table scan trong MySQL `EXPLAIN`.

Scan không tự động là xấu. Nếu truy vấn cần 60–90% số dòng, đọc liên tục có thể rẻ hơn hàng triệu index lookup. Cần xem:

- Số dòng/page thực tế được đọc.
- Số dòng trả về sau filter.
- Tỷ lệ rows returned so với rows scanned.
- Predicate có thể đẩy xuống storage/access path hay không.
- Có partition pruning hoặc index phù hợp không.
- Query có đọc cột không cần thiết không.
- Scan có gây cache churn hoặc cạnh tranh với workload khác không.

Nếu scan đọc 10 triệu dòng nhưng chỉ trả 100 dòng, cần xem predicate, statistics, kiểu dữ liệu, function trên cột và index. Nếu báo cáo cần 8 triệu dòng trong bảng 10 triệu dòng, scan có thể là lựa chọn hợp lý.

### 3.2. Dấu hiệu random lookup

Các node thường gặp:

- Index Seek/Key Lookup trong SQL Server.
- Index Scan/Index Only Scan/Bitmap Heap Scan trong PostgreSQL.
- `INDEX RANGE SCAN` kết hợp `TABLE ACCESS BY INDEX ROWID` trong Oracle.
- `ref`, `eq_ref`, `range` hoặc lookup qua index trong MySQL.

Hãy chú ý số lần node chạy (*loops*), số dòng mỗi lần và tổng số buffer/page đọc. Một `Index Seek` có vẻ rẻ khi chạy một lần có thể rất đắt nếu được gọi 500.000 lần trong nested loop.

Ví dụ, truy vấn lấy 5.000 đơn hàng rồi lookup khách hàng từng đơn:

```sql
SELECT o.id, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.created_at >= :from_time;
```

Nếu plan dùng nested loop và lookup customer cho từng order, có thể phát sinh hàng nghìn lần truy xuất page. Điều này có thể vẫn tốt nếu số order ít và customer index/cache nóng; nhưng nếu số dòng thực tế lớn hơn estimate nhiều, hash join hoặc một access path khác có thể hiệu quả hơn.

### 3.3. Đọc số lần lặp và số dòng thực tế

Trong plan, đừng chỉ nhìn loại node. Kiểm tra:

- Estimated rows so với actual rows.
- Loops hoặc executions của từng node.
- Buffers/page reads ở từng node nếu engine cung cấp.
- Rows removed by filter.
- Heap/table fetches sau index access.
- Sort/hash spill và temp read/write.

Một node đọc 20 page một lần có thể không đáng lo. Node đọc 20 page nhưng chạy 100.000 lần tạo 2 triệu page access. Cần tính tổng công việc theo số lần lặp.

## 4. Phân biệt logical reads và physical reads

Database thường quản lý dữ liệu qua buffer pool hoặc cache page. Logical read là lần truy cập page qua cơ chế cache của engine; physical read là lần phải lấy page từ tầng storage bên dưới cache database. Tên gọi và counter cụ thể tùy engine.

### 4.1. Logical reads cao, physical reads thấp

Trường hợp này cho thấy truy vấn truy cập nhiều page nhưng phần lớn được phục vụ từ memory. Query vẫn có thể chậm do CPU, latch, memory bandwidth hoặc số thao tác quá lớn, nhưng storage có thể không phải bottleneck trực tiếp.

Hướng điều tra:

- Xem plan có scan quá nhiều page không.
- Xem số logical reads trên mỗi lần gọi và tổng số lần gọi.
- Kiểm tra filter, join, cardinality estimate và index.
- Đo CPU time, latch/wait và memory bandwidth.

### 4.2. Physical reads tăng

Physical reads tăng cho biết cache miss dẫn tới đọc từ tầng dưới. Cần xác định page thuộc data file, index, temp file hay file khác; volume nào thực sự nhận request; request có được OS/controller cache phục vụ không.

Hướng điều tra:

- So buffer cache hit và physical reads theo query/workload.
- Kiểm tra working set so với RAM.
- Xem có nhiều truy vấn scan hoặc random lookup cùng lúc không.
- Đối chiếu OS IOPS, throughput, latency và queue.
- Kiểm tra backup, maintenance hoặc query spill chạy đồng thời.

### 4.3. Cache nóng có thể che bottleneck

Một bài test lặp lại cùng truy vấn thường làm cache nóng. Physical reads giảm mạnh và latency đẹp hơn production khi working set lớn hoặc cache bị cạnh tranh. Benchmark cần mô tả rõ cache state, warm-up và kích thước dữ liệu. Không xóa cache production để tạo cold-cache test; dùng môi trường thử nghiệm hoặc dữ liệu lớn hơn memory.

## 5. Đọc mẫu I/O ở hệ điều hành

### 5.1. Linux: iostat

Lệnh phổ biến từ gói `sysstat`:

```bash
iostat -xz 1
```

Các trường quan trọng thường gồm:

- `r/s`, `w/s`: số request đọc/ghi mỗi giây.
- `rkB/s`, `wkB/s`: throughput đọc/ghi.
- `r_await`, `w_await`: thời gian chờ trung bình của request đọc/ghi.
- `rareq-sz`, `wareq-sz`: kích thước request đọc/ghi trung bình.
- `aqu-sz`: queue size trung bình theo định nghĩa của sysstat.
- `%util`: tỷ lệ thời gian thiết bị được coi là bận trong cửa sổ đo.

Diễn giải gợi ý:

| Mẫu quan sát | Giả thuyết ban đầu | Cần xác minh |
|---|---|---|
| `rkB/s` cao, `r/s` vừa, request lớn | Scan hoặc read-ahead | Execution plan, backup/scan job, file đang đọc |
| `r/s` cao, `rkB/s` thấp/vừa, request nhỏ | Random lookup hoặc nhiều page read nhỏ | Loops, index lookup, cache miss, working set |
| `wkB/s` cao và `w/s` tăng | Checkpoint, batch DML, rebuild hoặc bulk load | WAL/redo, dirty page, maintenance job |
| `w_await` tăng, throughput không tăng | Write queue hoặc backend đang bão hòa | Log/data volume, fsync, queue và storage limits |
| Queue tăng cùng `r_await`/`w_await` | Request phải chờ storage | Đúng device? Shared backend? Burst limit? |

Với NVMe và thiết bị nhiều queue, `%util` gần 100% không đủ để kết luận đã chạm giới hạn. Đọc cùng latency, throughput, queue, IOPS và giới hạn của thiết bị/backend.

### 5.2. Xác định process tạo I/O

Có thể dùng các công cụ quan sát process:

```bash
pidstat -d 1
```

hoặc:

```bash
sudo iotop -oPa
```

Chúng giúp xác định process có lượng đọc/ghi cao trong khoảng lấy mẫu. Tuy nhiên, database có thể dùng nhiều process/worker, I/O bất đồng bộ hoặc kernel thread; process accounting không luôn ánh xạ trực tiếp tới query. Hãy liên kết timestamp, PID, database session và job khi có thể.

### 5.3. Xác định volume và thiết bị thực

Trước khi kết luận volume nào bão hòa, xác định đường ánh xạ:

```bash
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
```

Một mount point có thể nằm trên LVM, RAID, device mapper, SAN hoặc cloud volume. Nhiều volume logic có thể chia sẻ cùng thiết bị vật lý hoặc storage pool. Nếu chỉ đo một partition mà bỏ qua thiết bị cha/backend, có thể hiểu sai mức cạnh tranh.

### 5.4. Windows

Trên Windows, Performance Monitor có thể theo dõi:

- `Disk Reads/sec`, `Disk Writes/sec`.
- `Disk Read Bytes/sec`, `Disk Write Bytes/sec`.
- `Avg. Disk sec/Read`, `Avg. Disk sec/Write`.
- `Avg. Disk Queue Length` và `Current Disk Queue Length`.
- Process I/O bytes và I/O operations nếu counter phù hợp có sẵn.

Đo ở đúng instance volume/device và cùng cửa sổ thời gian với metric database. Với volume ảo hoặc cloud disk, guest counter không nhất thiết cho thấy giới hạn ở backend.

## 6. Phân tích I/O theo loại workload

### 6.1. Full scan hoặc range scan lớn

Dấu hiệu:

- Plan có scan node.
- Logical/physical reads tăng theo số page trong bảng/partition.
- Read throughput và request size có thể tăng.
- Query duration tăng khi scan cạnh tranh storage hoặc cache.

Kiểm tra:

1. Query có thực sự cần đọc phần lớn dữ liệu không?
2. Predicate có chọn lọc nhưng không dùng được index vì cast, function hoặc kiểu dữ liệu không tương thích không?
3. Statistics có phản ánh phân bố dữ liệu hiện tại không?
4. Có partition pruning hoặc index phù hợp không?
5. Có đọc cột thừa hoặc materialize tập trung gian lớn không?
6. Có thể dùng summary/materialized view hoặc columnstore cho workload phân tích không?

Nếu scan là hợp lý, hãy tối ưu song song, read-ahead, partitioning và lịch chạy để giảm ảnh hưởng tới workload khác. Không thêm index chỉ để tránh mọi table scan; index có chi phí storage và ghi.

### 6.2. Nhiều random lookup

Dấu hiệu:

- IOPS cao, request nhỏ và cache miss tăng.
- Plan có nested loop hoặc index lookup với loops lớn.
- Nhiều key lookup/heap fetch hoặc rowid lookup.
- Query có latency cao dù tổng MB đọc không lớn.

Kiểm tra:

1. Node lookup chạy bao nhiêu lần?
2. Có thể join theo set thay vì lookup từng dòng không?
3. Index có bao phủ cột cần trả về không?
4. Có thể giảm số dòng ở outer side trước khi join không?
5. Statistics có ước lượng sai cardinality không?
6. Working set có vượt buffer pool hoặc bị cache churn không?

Ví dụ, thay vì gọi một query lấy chi tiết cho từng order trong vòng lặp ứng dụng, hãy cân nhắc một truy vấn theo danh sách khóa hoặc join phù hợp. Tuy nhiên, `IN` rất lớn cũng có giới hạn parameter và có thể tạo plan kém; dùng batch có kích thước được đo.

### 6.3. Ghi nền do checkpoint

Checkpoint ghi dirty page xuống data file. Khi lượng dirty page lớn hoặc checkpoint diễn ra dồn dập, write I/O tăng và có thể cạnh tranh với query.

Kiểm tra:

- Thời điểm checkpoint so với write throughput và latency.
- Tốc độ phát sinh WAL/redo/log.
- Số dirty page, checkpoint duration và write queue.
- Data file có dùng chung backend với log/temp/backup không.
- Checkpoint có đang bị ép chạy quá thường xuyên do cấu hình hoặc log pressure không.

Không tắt checkpoint để giảm I/O. Cần cân bằng pacing, recovery time, log generation và năng lực storage theo engine.

### 6.4. Ghi nền do vacuum, purge hoặc version cleanup

MVCC engine cần dọn phiên bản cũ khi không còn transaction nào cần. Cleanup có thể đọc và ghi page, tạo I/O nền. Nếu cleanup không theo kịp DML, bloat hoặc undo history tích tụ và làm workload sau đó tốn I/O hơn.

Kiểm tra transaction dài, session idle in transaction, dead tuple/history list/version store, tốc độ DML và cleanup worker. Không tắt vacuum/purge chỉ để làm giảm I/O trước mắt; phải xử lý nguyên nhân cleanup bị chậm hoặc bị chặn.

### 6.5. Ghi nền do index maintenance và bulk load

Rebuild index đọc dữ liệu nguồn, sort key, ghi index mới và có thể tạo log lớn. Bulk load ghi nhiều data/index page. Những tác vụ này có thể làm write throughput và temp I/O tăng trong thời gian chạy.

Kiểm tra job history, số index/table được xử lý, parallelism, temp space, log generation và lock. Chỉ rebuild khi có bằng chứng về fragmentation, page density hoặc hiệu năng access path; không chạy mọi index theo lịch cứng mà không xem workload.

### 6.6. Temp I/O do sort/hash spill

Nếu memory grant hoặc workspace không đủ, sort/hash có thể spill ra temp storage. Dấu hiệu gồm temp read/write tăng, execution plan có spill warning, sort/hash operator lớn và query latency tăng.

Hãy xem estimated rows so với actual rows, memory grant, cardinality, sort order, join strategy và số cột được giữ trong intermediate result. Tăng memory có thể giúp nhưng nếu query tạo tập trung gian quá lớn do join sai hoặc filter muộn, cần sửa plan/SQL trước.

## 7. Đo ở tầng database: PostgreSQL

PostgreSQL cung cấp thống kê theo database, bảng, query và I/O tùy phiên bản.

### 7.1. Thống kê query

Nếu `pg_stat_statements` đã được cài và bật, có thể tìm query tiêu thụ nhiều block:

```sql
SELECT queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       shared_blks_hit,
       shared_blks_read,
       shared_blks_dirtied,
       shared_blks_written,
       temp_blks_read,
       temp_blks_written,
       rows,
       query
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 20;
```

`shared_blks_read` là block được đưa vào shared buffers từ tầng dưới theo thống kê PostgreSQL; nó không nhất thiết tương đương một request vật lý trực tiếp tới NAND vì OS/storage cache vẫn có thể phục vụ. `shared_blks_hit` cho biết block đã có trong shared buffers. `temp_blks_*` giúp tìm query dùng temporary block. Đây là counter tích lũy; hãy so delta giữa hai mẫu để tìm tốc độ trong cửa sổ đo.

### 7.2. Actual plan và buffers

Trong môi trường an toàn, dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
SELECT ...;
```

`ANALYZE` thực thi câu SQL. Không chạy tùy tiện trên câu DML hoặc truy vấn rất nặng trong production; `EXPLAIN ANALYZE` với statement ghi có thể thực sự thay đổi dữ liệu. `BUFFERS` giúp xem shared/local/temp block hit/read/dirtied/written; `WAL` cung cấp thống kê WAL cho các thao tác hỗ trợ. Đối chiếu actual rows, loops và buffers theo node.

### 7.3. Thống kê I/O theo loại hoạt động

Trên PostgreSQL 16 trở lên, `pg_stat_io` cung cấp thống kê I/O theo backend type, object và context:

```sql
SELECT backend_type,
       object,
       context,
       reads,
       read_time,
       writes,
       write_time,
       writebacks,
       writeback_time,
       extends,
       fsyncs,
       fsync_time
FROM pg_stat_io
ORDER BY backend_type, object, context;
```

Các cột thời gian chỉ được thu thập khi cấu hình thống kê I/O timing phù hợp; một số cột hoặc semantics có thể thay đổi theo phiên bản. `pg_stat_io` không phải bộ đếm byte vật lý hoàn chỉnh và không thay thế OS metrics. Hãy dùng delta và đối chiếu với `iostat`.

### 7.4. Quan sát vacuum và checkpoint

Có thể xem hoạt động bảng:

```sql
SELECT relname,
       n_live_tup,
       n_dead_tup,
       last_autovacuum,
       autovacuum_count,
       last_autoanalyze,
       autoanalyze_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Và checkpoint/WAL qua các view thống kê phù hợp phiên bản như `pg_stat_bgwriter` hoặc `pg_stat_checkpointer` trên các phiên bản mới. Tên view và cột đã thay đổi qua các phiên bản PostgreSQL; xác minh schema của phiên bản đang chạy trước khi dùng dashboard cố định.

## 8. Đo ở tầng database: MySQL/InnoDB

### 8.1. Performance Schema theo table

Nếu Performance Schema được bật, có thể xem I/O wait theo bảng:

```sql
SELECT OBJECT_SCHEMA,
       OBJECT_NAME,
       COUNT_READ,
       SUM_TIMER_READ,
       COUNT_WRITE,
       SUM_TIMER_WRITE,
       COUNT_FETCH,
       COUNT_INSERT,
       COUNT_UPDATE,
       COUNT_DELETE
FROM performance_schema.table_io_waits_summary_by_table
WHERE OBJECT_SCHEMA IS NOT NULL
ORDER BY SUM_TIMER_READ + SUM_TIMER_WRITE DESC
LIMIT 20;
```

Các timer của Performance Schema thường được lưu theo picosecond trong các bảng summary; xem tài liệu phiên bản để diễn giải đơn vị và counter. Đây là thống kê wait ở tầng instrumented database, không phải số request vật lý ở thiết bị.

### 8.2. File I/O

Có thể xem thống kê file I/O:

```sql
SELECT FILE_NAME,
       EVENT_NAME,
       COUNT_READ,
       SUM_NUMBER_OF_BYTES_READ,
       SUM_TIMER_READ,
       COUNT_WRITE,
       SUM_NUMBER_OF_BYTES_WRITE,
       SUM_TIMER_WRITE
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_TIMER_READ + SUM_TIMER_WRITE DESC
LIMIT 20;
```

View này giúp tìm file có thời gian chờ đọc/ghi lớn. Cần nhóm file theo data, redo, undo, temp và log để hiểu thành phần nào đang tiêu thụ I/O. Counter tích lũy nên lấy delta.

### 8.3. InnoDB status và buffer pool

`SHOW ENGINE INNODB STATUS` cung cấp thông tin về I/O thread, pending reads/writes, buffer pool, checkpoint, log và transaction. Có thể xem nhanh:

```sql
SHOW ENGINE INNODB STATUS\G
```

Đọc cùng các global status như buffer pool read requests/reads, data reads/writes, log waits và checkpoint age tùy phiên bản. Một lượng logical read lớn không đồng nghĩa thiết bị đang chịu cùng số lần đọc; hãy so buffer pool hit và OS metrics.

### 8.4. Execution plan

Dùng `EXPLAIN ANALYZE` trên phiên bản hỗ trợ để lấy actual execution information; lưu ý câu lệnh được thực thi. Kiểm tra access type, estimated/actual rows, loops, filesort, temporary table và join order. Một nested loop với nhiều vòng lặp có thể tạo random lookup rất lớn dù mỗi lookup dùng index.

## 9. Đo ở tầng database: SQL Server

### 9.1. Query statistics và plan

Query Store hoặc DMV có thể giúp tìm query theo logical/physical reads và thời gian. Một truy vấn mẫu dùng `sys.dm_exec_query_stats`:

```sql
SELECT TOP (20)
       qs.execution_count,
       qs.total_logical_reads,
       qs.total_physical_reads,
       qs.total_logical_writes,
       qs.total_worker_time,
       qs.total_elapsed_time,
       st.text
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
ORDER BY qs.total_physical_reads DESC;
```

DMV chứa counter trong plan cache và có thể reset khi plan bị evict hoặc instance restart. Dùng delta và cân nhắc query có execution count lớn; tổng physical reads không cho biết latency của từng lần gọi.

### 9.2. File I/O latency

```sql
SELECT DB_NAME(vfs.database_id) AS database_name,
       mf.type_desc,
       mf.physical_name,
       vfs.num_of_reads,
       vfs.num_of_writes,
       vfs.io_stall_read_ms,
       vfs.io_stall_write_ms,
       vfs.num_of_bytes_read,
       vfs.num_of_bytes_written
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs
JOIN sys.master_files AS mf
  ON mf.database_id = vfs.database_id
 AND mf.file_id = vfs.file_id
ORDER BY vfs.io_stall_read_ms + vfs.io_stall_write_ms DESC;
```

Có thể tính latency trung bình gần đúng bằng `io_stall_read_ms / NULLIF(num_of_reads, 0)` và tương tự cho write, hoặc lấy delta giữa hai lần chụp. Đây là số liệu tổng hợp theo file, không phải p95/p99 của từng request.

### 9.3. Wait statistics

Các wait như `PAGEIOLATCH_*` có thể gợi ý chờ page I/O; `WRITELOG` gợi ý chờ log flush; `IO_COMPLETION` hoặc wait khác có thể liên quan thao tác I/O. Cần xem delta, loại wait, query và file liên quan. Không kết luận chỉ từ tên wait: một số wait tích lũy từ lúc khởi động và có thể thuộc workload cũ hoặc tác vụ nền.

### 9.4. Actual execution plan

Kiểm tra actual rows, logical reads, physical reads, key lookup, scan, spill warning, memory grant và số lần thực thi operator. Một plan có `Index Seek` vẫn có thể tốn kém nếu key lookup chạy nhiều lần; một `Clustered Index Scan` có thể hợp lý nếu cần phần lớn dữ liệu.

## 10. Đo ở tầng database: Oracle

### 10.1. SQL theo buffer gets và disk reads

Trong môi trường có quyền truy cập các dynamic performance view, có thể xem SQL tiêu thụ nhiều tài nguyên:

```sql
SELECT sql_id,
       executions,
       buffer_gets,
       disk_reads,
       direct_reads,
       direct_writes,
       elapsed_time,
       cpu_time,
       sql_text
FROM v$sql
ORDER BY disk_reads DESC
FETCH FIRST 20 ROWS ONLY;
```

`BUFFER_GETS` phản ánh logical buffer gets; `DISK_READS` và direct I/O counter có semantics theo view/phiên bản. Counter tích lũy theo cursor và có thể bị aging out. Xem thêm executions, rows processed và thời gian trung bình.

### 10.2. File I/O

Có thể xem thống kê file:

```sql
SELECT file_no,
       filetype_name,
       small_read_megabytes,
       large_read_megabytes,
       small_write_megabytes,
       large_write_megabytes,
       small_read_reqs,
       large_read_reqs,
       small_write_reqs,
       large_write_reqs
FROM v$iostat_file;
```

`V$IOSTAT_FILE` cung cấp các nhóm I/O small/large theo file type trên các phiên bản hỗ trợ. Đọc cùng `V$FILESTAT`, `V$SYSTEM_EVENT`, `V$IOSTAT_FUNCTION` hoặc metric AWR/ASH nếu được cấp phép. View và cột cần kiểm tra theo phiên bản/edition.

### 10.3. Wait events

Các wait như `db file sequential read` thường liên quan single-block read và có thể xuất hiện trong index lookup; `db file scattered read` thường liên quan multi-block read như full scan; `direct path read/write` có thể xuất hiện trong direct I/O, scan hoặc temporary operation; `log file sync` liên quan commit chờ log flush. Đây là gợi ý về loại hoạt động, không phải kết luận duy nhất về nguyên nhân.

Phân tích event theo thời gian, SQL_ID, file và module/action. Nếu có AWR/ASH, dùng chúng theo quyền và điều kiện license phù hợp; không mặc định mọi môi trường Oracle đều được phép dùng mọi tính năng Diagnostics/Tuning Pack.

## 11. Nhận diện ghi nền theo nguồn phát sinh

Khi write I/O tăng, cần phân biệt ghi do transaction người dùng với ghi do background process.

### 11.1. Transaction log/WAL/redo

Log thường có mẫu ghi tuần tự và flush nhạy với commit latency. Dấu hiệu:

- Commit latency tăng.
- Log flush wait hoặc `fsync` time tăng.
- WAL/redo/log bytes per second tăng.
- Archive/replication queue tăng nếu downstream chậm.

Nếu log volume là bottleneck, query đọc data có thể vẫn nhanh nhưng transaction ghi bị chậm. Kiểm tra log device riêng, group commit, transaction size và log generation rate.

### 11.2. Checkpoint và background writer

Checkpoint/background writer flush dirty page ra data file. Dấu hiệu:

- Data write throughput tăng theo chu kỳ.
- Dirty page hoặc checkpoint write tăng.
- Query đọc/ghi chậm hơn khi write queue dài.
- Log/checkpoint metrics thay đổi cùng thời điểm.

Kiểm tra checkpoint frequency, pacing, dirty buffer, writeback và storage headroom. Không tắt checkpoint hoặc durability để giảm I/O.

### 11.3. Vacuum, purge và version cleanup

Cleanup đọc/ghi page để xử lý phiên bản cũ. Dấu hiệu:

- PostgreSQL autovacuum hoặc manual vacuum chạy trên bảng lớn.
- InnoDB purge backlog/history list length thay đổi.
- SQL Server version store cleanup và tempdb I/O tăng.
- Oracle undo generation và retention pressure tăng.

Đối chiếu transaction dài, idle-in-transaction, DML rate và số dead tuple/undo/version. Cleanup có thể làm I/O tăng trong ngắn hạn nhưng giảm bloat và chi phí đọc về lâu dài.

### 11.4. Backup, index rebuild và bulk load

Backup thường tạo read throughput lớn; index rebuild có cả read, sort/temp và write; bulk load tạo write/log/index maintenance. Kiểm tra lịch job, process, file và phase của tác vụ. Có thể điều tiết tốc độ, giảm parallelism, chia batch hoặc chuyển sang replica/volume riêng nếu topology thực sự độc lập.

## 12. Phân tích temp I/O và spill

Temp I/O thường bị nhầm với I/O của bảng nguồn. Sort/hash spill có thể ghi nhiều dữ liệu trung gian ra temp volume dù query cuối cùng chỉ trả vài dòng.

### 12.1. Dấu hiệu

- Temp file read/write tăng trong lúc một query chạy.
- Execution plan có sort/hash spill hoặc warning.
- Memory grant/work_mem không đủ so với cardinality thực tế.
- Estimated rows thấp hơn actual rows nhiều.
- Query p95/p99 tăng khi concurrency cao do nhiều operation cùng xin memory.

### 12.2. Hướng xử lý

1. Xem actual plan và xác định operator spill.
2. So estimated rows với actual rows; cập nhật statistics nếu stale.
3. Giảm rows/columns trước sort/hash bằng filter và projection phù hợp.
4. Kiểm tra join order, duplicate rows và cardinality.
5. Điều chỉnh memory grant/work_mem theo concurrency, không tăng vô hạn.
6. Đo temp I/O và workload khác sau khi thay đổi.

Một query đơn lẻ có thể cần memory lớn, nhưng nếu 100 query chạy đồng thời thì tổng memory request có thể vượt RAM. Cần sizing theo concurrency chứ không chỉ theo một execution plan.

## 13. Xây dựng quy trình chẩn đoán từ triệu chứng

### 13.1. Bước 1: xác định thời điểm và phạm vi

Ghi nhận endpoint/query chậm, thời gian bắt đầu, thời lượng, database, host, volume và workload đang chạy. So sánh với baseline cùng giờ hoặc cùng loại tải. Kiểm tra sự kiện deploy, batch, backup, maintenance, failover hoặc thay đổi storage.

### 13.2. Bước 2: xác định read hay write

Đọc IOPS, write IOPS, read/write throughput, latency và queue theo volume. Tách data, log, temp và backup nếu có. Nếu volume dùng chung backend, xác định các workload khác đang cùng chia sẻ tài nguyên.

### 13.3. Bước 3: xác định query tạo I/O

Tìm top SQL theo physical reads, logical reads, read/write bytes, temp blocks, elapsed time và số lần gọi. Nhóm theo fingerprint và liên kết với application trace. Một query nhiều logical reads nhưng ít physical reads khác với query gây physical read lớn.

### 13.4. Bước 4: đọc actual execution plan

Xem scan, lookup, loops, actual rows, estimated rows, buffers, temp spill và index usage. Xác định truy vấn đọc nhiều page vì cần dữ liệu hay vì access path không phù hợp.

### 13.5. Bước 5: đối chiếu tác vụ nền

Kiểm tra backup, checkpoint, vacuum/purge, index maintenance, statistics, batch load, archive và retention. Đối chiếu timestamp của job với write/read I/O và latency workload chính.

### 13.6. Bước 6: xác nhận bottleneck ở đúng tầng

Đối chiếu database metrics với OS/device/backend. Nếu database báo physical read cao nhưng thiết bị không bận, dữ liệu có thể được phục vụ từ OS/storage cache hoặc bottleneck nằm ở tầng khác. Nếu thiết bị bận nhưng query không có nhiều physical reads, có thể workload khác đang dùng volume.

### 13.7. Bước 7: thử một thay đổi có kiểm soát

Chọn biện pháp dựa trên bằng chứng: sửa query/index, giảm scan, giảm lookup, điều chỉnh batch, điều tiết maintenance, tăng cache hoặc tăng năng lực storage. Chỉ thay một nhóm biến trong mỗi thử nghiệm để có thể quy kết kết quả.

### 13.8. Bước 8: xác minh sau điều chỉnh

So sánh cùng workload và thời lượng:

- Query count, logical/physical reads và rows.
- IOPS, throughput, request size, queue và p95/p99 latency.
- CPU, memory, temp spill, log flush và lock wait.
- Throughput, p95/p99 của ứng dụng và error rate.
- Tác động tới backup, replication và maintenance window.

Một query nhanh hơn nhưng làm write amplification tăng mạnh hoặc khiến replica lag vượt ngưỡng chưa chắc là cải thiện tổng thể.

## 14. Ví dụ 1: IOPS đọc cao do nested-loop lookup

Một endpoint lấy danh sách 20.000 giao dịch và join thông tin tài khoản. OS cho thấy read IOPS cao, throughput chỉ ở mức trung bình và request size nhỏ. Query statistics cho thấy một fingerprint chiếm phần lớn physical reads.

Actual plan cho thấy:

- Scan giao dịch trả 20.000 dòng.
- Nested loop gọi index lookup trên account 20.000 lần.
- Mỗi lookup có thể phải đọc index page và heap/table page.
- Estimated rows của node ngoài thấp hơn actual rows nhiều lần.

Hướng điều tra:

1. Kiểm tra statistics của bảng giao dịch và account.
2. Xem join key có index đúng và kiểu dữ liệu tương thích không.
3. Xác định truy vấn có cần mọi cột account hay chỉ vài cột.
4. Thử plan hash join hoặc set-based join phù hợp nếu số dòng ngoài lớn.
5. Thử covering index nếu giảm heap lookup đem lại lợi ích đủ lớn và write cost chấp nhận được.
6. So physical reads, logical reads, CPU và p95/p99 trước/sau.

Không kết luận nested loop luôn xấu. Nếu outer rows chỉ vài dòng và inner index lookup chọn lọc, nested loop có thể là plan tốt nhất.

## 15. Ví dụ 2: Read throughput cao do báo cáo quét toàn bảng

Một báo cáo chạy lúc 9 giờ sáng làm data volume đọc liên tục với throughput lớn. API OLTP có p99 tăng dù CPU không bão hòa. Query plan báo table scan trên bảng lịch sử lớn; báo cáo chỉ lọc theo khoảng ngày nhưng bảng chưa partition theo thời gian và predicate không tận dụng index hiệu quả.

Hướng điều tra:

1. Xác nhận báo cáo cần bao nhiêu phần trăm dữ liệu và có thể giảm cột/dòng không.
2. Kiểm tra predicate có implicit cast hoặc function làm mất khả năng dùng index không.
3. Đánh giá index theo ngày và partition pruning cho truy vấn phổ biến.
4. Nếu báo cáo lặp lại, cân nhắc summary/materialized view hoặc replica phân tích.
5. Chạy báo cáo ngoài giờ cao điểm hoặc giới hạn parallelism/throughput nếu cần.
6. Đo p99 OLTP, báo cáo duration, I/O queue và cache hit sau thay đổi.

Nếu báo cáo thực sự cần gần toàn bộ bảng, sequential scan có thể vẫn là phương án tốt. Mục tiêu khi đó là cách ly và điều tiết tải, không nhất thiết ép optimizer dùng index.

## 16. Ví dụ 3: Write I/O tăng theo chu kỳ checkpoint

Một hệ thống ghi đơn hàng có commit latency bình thường nhưng cứ vài phút lại tăng. Trong cùng khoảng thời gian, data volume có write throughput cao và query đọc cũng chậm hơn. Log cho thấy checkpoint bắt đầu; số dirty page tăng trước đó.

Hướng điều tra:

1. Đối chiếu checkpoint timestamp, dirty pages, WAL/redo generation và write queue.
2. Xác định data và log có dùng chung storage pool không.
3. Kiểm tra batch update hoặc bulk load có tạo write burst trước checkpoint không.
4. Đánh giá checkpoint pacing, log volume và storage sustained write.
5. Thử điều chỉnh batch, lịch job hoặc checkpoint settings theo tài liệu engine.
6. So commit p95/p99, checkpoint duration, data write latency và recovery implications.

Không tắt checkpoint hoặc flush để loại bỏ spike. Checkpoint là một phần của cơ chế phục hồi; cần làm cho hoạt động ghi ổn định hơn và có đủ năng lực storage.

## 17. Những sai lầm thường gặp

- **Thấy disk busy là kết luận query gây tải:** backup, checkpoint hoặc process khác có thể đang dùng cùng volume.
- **Chỉ nhìn MB/s:** bỏ qua IOPS, request size và latency của random access.
- **Chỉ nhìn IOPS:** không biết mỗi request lớn hay nhỏ, throughput có đủ không.
- **Đồng nhất logical reads với physical I/O:** logical reads có thể được phục vụ từ buffer pool.
- **Cho rằng table scan luôn xấu:** scan có thể tốt khi cần phần lớn dữ liệu.
- **Cho rằng index seek luôn rẻ:** lookup có thể lặp hàng trăm nghìn lần và gây random I/O lớn.
- **Chỉ nhìn estimated plan:** estimate có thể lệch xa actual rows và loops.
- **Không lấy delta counter:** counter tích lũy không phản ánh tốc độ trong cửa sổ hiện tại.
- **Bỏ qua temp I/O:** sort/hash spill có thể là nguồn I/O lớn dù bảng nguồn không đọc nhiều.
- **Tắt vacuum/purge/checkpoint:** giảm một số I/O trước mắt nhưng tích lũy nợ bảo trì hoặc ảnh hưởng recovery.
- **Rebuild mọi index theo lịch:** tạo thêm read/write/log mà không chứng minh được lợi ích.
- **Tăng IOPS trước khi tìm access path:** có thể trả chi phí storage cao để phục vụ công việc dư thừa.
- **Đo sai volume:** nhiều volume logic có thể chia sẻ cùng physical device hoặc cloud backend.
- **Chỉ đo average latency:** p95/p99 có thể tăng mạnh khi queue hình thành.
- **Không xác minh workload hỗn hợp:** tối ưu một query có thể làm OLTP, replication hoặc backup chậm hơn.

## 18. Checklist chẩn đoán I/O cao

- [ ] Đã ghi nhận thời điểm, phạm vi database/host/volume và workload bị ảnh hưởng.
- [ ] Đã phân biệt read I/O, write I/O, log flush và temp I/O.
- [ ] Đã lấy IOPS, throughput, request size, queue và p95/p99 latency theo delta.
- [ ] Đã xác định đúng thiết bị/backend và các volume dùng chung tài nguyên.
- [ ] Đã đo logical reads, physical reads, writes và temp blocks theo query/fingerprint.
- [ ] Đã xem actual execution plan, rows, loops, buffers và spill.
- [ ] Đã phân biệt scan lớn với random lookup lặp lại.
- [ ] Đã kiểm tra checkpoint, vacuum/purge, backup, index rebuild, bulk load và batch job.
- [ ] Đã đối chiếu metric database với OS/storage trong cùng cửa sổ thời gian.
- [ ] Đã kiểm tra cache state và working set.
- [ ] Đã xác định bottleneck ở query, CPU, memory, data volume, log volume hay backend.
- [ ] Đã chọn một thay đổi có bằng chứng và benchmark trước/sau.
- [ ] Đã kiểm tra p95/p99, throughput, error rate và tác động tới workload khác.
- [ ] Đã bảo đảm tác vụ nền thiết yếu, durability, backup và replication vẫn đáp ứng yêu cầu.

I/O cao cần được phân loại trước khi tối ưu. Scan lớn thường tạo lượng đọc và throughput đáng kể; random lookup có thể tạo IOPS cao với request nhỏ và nhiều lần truy cập page; ghi nền thường gắn với checkpoint, log, vacuum/purge, backup, rebuild hoặc batch. Khi kết hợp execution plan, logical/physical reads, wait events và metric thiết bị theo cùng cửa sổ thời gian, có thể xác định đúng nguồn tải và chọn biện pháp phù hợp. Đo lại toàn workload sau thay đổi để bảo đảm giảm I/O thực sự cải thiện latency và throughput mà không chuyển bottleneck sang thành phần khác.

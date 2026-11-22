# Độ trễ p99 tăng trong checkpoint, bảo trì hoặc đột biến tải

Một hệ thống cơ sở dữ liệu có thể giữ độ trễ trung bình khá thấp nhưng vẫn khiến một nhóm request chậm bất thường. Ví dụ p50 vẫn ở 35 ms trong khi p99 tăng từ 180 ms lên 2,5 giây. Hiện tượng này thường xuất hiện khi checkpoint ghi nhiều trang bẩn xuống storage, một công việc bảo trì cạnh tranh CPU hoặc I/O, hay traffic tăng đột ngột làm hàng đợi và mức đồng thời vượt năng lực xử lý.

Trong DATABASE_PERFORMANCE, chẩn đoán độ trễ p99 cần kết hợp đo tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Không nên kết luận chỉ từ việc checkpoint hoặc maintenance chạy cùng thời điểm với sự cố. Cần xác định request chậm ở tầng nào, tài nguyên nào bị bão hòa, session nào đang chờ, truy vấn nào tiêu thụ tài nguyên và sự kiện nào bắt đầu trước. Một checkpoint có thể là nguyên nhân trực tiếp, yếu tố khuếch đại một storage bottleneck sẵn có hoặc chỉ xuất hiện trùng thời điểm với một query plan regression.

Bài học này trình bày cách đọc tail latency, phân biệt checkpoint với bảo trì và traffic spike, thu thập bằng chứng trên PostgreSQL, MySQL InnoDB, SQL Server và Oracle, sau đó giảm tác động và kiểm chứng hệ thống đã phục hồi.

## 1. Hiểu p99 và tail latency

P99 là giá trị latency mà 99% request trong tập đo hoàn tất bằng hoặc nhanh hơn; 1% còn lại chậm hơn. Tail latency phản ánh phần đuôi chậm của phân bố thời gian xử lý. Với hệ thống có hàng nghìn hoặc hàng triệu request, 1% có thể là một lượng người dùng đáng kể.

Ví dụ một cửa sổ đo có 100.000 request:

| Chỉ số | Trước sự cố | Trong sự cố |
|---|---:|---:|
| p50 | 28 ms | 34 ms |
| p95 | 90 ms | 420 ms |
| p99 | 180 ms | 2.500 ms |
| p99.9 | 350 ms | 6.000 ms |

Trong ví dụ, phần lớn request vẫn tương đối nhanh nhưng một nhóm nhỏ bị chậm nhiều lần. Nếu chỉ nhìn average, tác động có thể bị che khuất.

### 1.1. Vì sao p99 tăng trước p50?

Khi hệ thống bắt đầu thiếu tài nguyên, một số request gặp đúng thời điểm queue, cache miss, lock wait hoặc I/O chậm sẽ bị kéo dài. Những request khác vẫn được xử lý nhanh. Do đó p99 có thể tăng mạnh trong khi p50 chỉ thay đổi ít.

Một vài nguyên nhân thường gặp:

- Một số page read phải chờ storage trong lúc checkpoint ghi dữ liệu.
- Truy vấn báo cáo chiếm memory grant, CPU hoặc I/O làm truy vấn giao dịch phải chờ.
- Một transaction dài giữ khóa khiến các request đụng cùng hàng bị block.
- Connection pool đầy trong burst, request chờ trước khi SQL được gửi.
- Một truy vấn dùng plan scan hoặc sort spill chỉ ảnh hưởng nhóm tham số nhất định.
- Queue ở ứng dụng, database worker hoặc storage làm một số request chờ lâu hơn.

### 1.2. Không gộp percentile bằng phép trung bình

Không lấy p99 của từng pod hoặc từng phút rồi tính trung bình để suy ra p99 toàn hệ thống. Percentile không có tính cộng tuyến. Hãy gộp histogram hoặc dữ liệu quan sát gốc theo cùng bucket và cùng đơn vị thời gian, sau đó tính lại percentile.

Khi so sánh, giữ cùng:

- Cửa sổ thời gian và độ rộng bucket.
- Định nghĩa request thành công, timeout và bị hủy.
- Nhóm endpoint hoặc query fingerprint.
- Mô hình tải và cách thu thập latency.
- Đơn vị thời gian và quy tắc xử lý outlier.

Nếu chỉ tính latency của request thành công, timeout có thể biến mất khỏi phân bố và khiến p99 trông tốt giả tạo. Hãy báo cáo error/timeout rate riêng cùng latency.

### 1.3. Tách các thành phần latency

Thời gian một request có thể gồm:

1. Chờ thread hoặc queue ở ứng dụng.
2. Chờ lấy connection từ pool.
3. Gửi SQL qua mạng.
4. Chờ database lập lịch và thực thi.
5. Chờ lock, latch, CPU, memory hoặc I/O.
6. Đọc result set và truyền dữ liệu về ứng dụng.
7. Xử lý kết quả và trả response.

Nếu p99 tăng ở pool acquisition, thay đổi checkpoint có thể không phải nguyên nhân trực tiếp. Nếu thời gian SQL tăng cùng physical read latency, cần điều tra storage và database. Trace theo request hoặc query fingerprint giúp phân biệt các tầng.

## 2. Phân biệt ba tình huống thường gây p99 tăng

| Tình huống | Dấu hiệu nổi bật | Nguồn tranh chấp thường gặp |
|---|---|---|
| Checkpoint | Dirty page được ghi theo đợt, write I/O hoặc log/checkpoint activity tăng | Storage bandwidth, IOPS, buffer pool, log và background writer |
| Bảo trì | Có job vacuum, index rebuild, statistics, backup, purge hoặc compaction | CPU, I/O, temp space, log, lock và memory |
| Traffic spike | Offered load hoặc concurrency tăng nhanh | CPU, worker, connection, lock, cache, queue và storage |

Các tình huống có thể xảy ra cùng lúc. Ví dụ spike ghi làm dirty page tăng, checkpoint phải ghi nhiều hơn; maintenance scan chạy đồng thời làm storage bận; kết quả là p99 của giao dịch tăng mạnh.

### 2.1. Checkpoint là gì?

Database thường thay đổi page trong bộ nhớ trước, đánh dấu page là dirty rồi ghi xuống data file theo cơ chế write-back. Checkpoint là một phần của quy trình bảo đảm các thay đổi cần thiết đã được ghi xuống storage để giới hạn lượng công việc recovery và duy trì tính bền vững theo thiết kế engine.

Checkpoint không phải backup và cũng không đơn giản là flush toàn bộ dữ liệu mỗi lần. Cơ chế, chu kỳ, cách phân phối ghi và cách phối hợp với transaction log khác nhau theo hệ quản trị.

Checkpoint quá dồn dập hoặc write workload tạo quá nhiều dirty page có thể gây write I/O burst. Nếu storage không đủ năng lực, page read của truy vấn cũng phải chờ chung thiết bị hoặc queue.

### 2.2. Công việc bảo trì là gì?

Bảo trì có thể bao gồm:

- Rebuild hoặc reorganize index.
- VACUUM, ANALYZE hoặc cleanup phiên bản dữ liệu.
- Gather optimizer statistics.
- Backup, snapshot hoặc export.
- Purge dữ liệu cũ, partition maintenance.
- Compaction, optimize table hoặc segment maintenance.
- Refresh materialized view và ETL.

Một số công việc đọc nhiều, một số ghi nhiều, một số tạo log lớn hoặc giữ metadata lock. Tên job không đủ để kết luận mức tác động; cần xem tài nguyên và wait thực tế.

### 2.3. Traffic spike là gì?

Traffic spike là mức request hoặc transaction đến tăng nhanh so với baseline. Khi arrival rate vượt throughput mà database có thể hoàn tất, backlog tăng. Connection được giữ lâu hơn, pool đầy, worker bận và tail latency tăng.

Spike cũng có thể kích hoạt các cơ chế nền: nhiều INSERT tạo dirty page, log tăng nhanh, cache miss tăng và autovacuum/cleanup có thêm việc. Vì vậy, spike không chỉ là “nhiều request hơn”; nó có thể thay đổi cả hoạt động bảo trì và checkpoint.

## 3. Thu thập bằng chứng trước khi thay đổi cấu hình

Khi p99 tăng, trước tiên ghi lại một mốc thời gian thống nhất:

- Thời điểm p99 bắt đầu tăng và thời điểm trở về bình thường.
- Offered load, completed throughput và concurrency.
- Checkpoint start/end, backup, maintenance job và deploy.
- Số connection active/idle/pending.
- CPU, memory, IOPS, throughput và storage latency.
- Query duration, physical/logical reads và execution plan.
- Lock wait, latch wait, transaction age và deadlock.
- Log generation, flush latency và replication lag.

Đồng bộ clock giữa ứng dụng, database và monitoring. Nếu timestamp lệch, correlation có thể sai và dẫn đến xử lý nhầm nguyên nhân.

### 3.1. Dùng delta thay vì chỉ xem counter tích lũy

Nhiều database counter là số tích lũy từ lúc instance khởi động hoặc từ lần reset thống kê. Một con số lớn không nói được hoạt động đang diễn ra nhanh hay chậm.

Lấy hai mẫu tại thời điểm t1 và t2:

\[
\text{rate} = \frac{\text{counter}_{t2}-\text{counter}_{t1}}{t2-t1}
\]

Ví dụ, nếu số physical read tăng 120.000 trong 60 giây thì tốc độ trung bình trong cửa sổ là 2.000 read/giây. So sánh tốc độ trước, trong và sau sự kiện.

Không so sánh counter qua lần restart hoặc reset nếu chưa điều chỉnh mốc. Ghi rõ uptime và thời điểm reset statistics.

### 3.2. Tách theo endpoint và query fingerprint

P99 toàn dịch vụ có thể tăng do một endpoint hiếm nhưng rất chậm. Phân tách theo:

- Endpoint, operation hoặc loại transaction.
- Query fingerprint và execution plan.
- Tenant hoặc nhóm dữ liệu nếu có skew.
- Read/write path và datasource.
- Replica hoặc database node.

Tránh gắn nhãn metric bằng giá trị tham số có cardinality quá cao hoặc chứa dữ liệu nhạy cảm. Dùng query fingerprint và trace ID có kiểm soát.

### 3.3. Kiểm tra load generator và client

Nếu bài test hoặc monitoring lấy từ client, xác nhận client không phải bottleneck. CPU load generator cao, socket cạn, DNS chậm hoặc thread pool đầy có thể làm latency quan sát được tăng dù database chưa bão hòa.

Đối chiếu server-side query duration với end-to-end latency. Nếu server query time ổn định nhưng request latency tăng, điều tra network, pool wait và ứng dụng.

## 4. Chẩn đoán checkpoint và I/O

### 4.1. Dấu hiệu checkpoint tạo áp lực

Các dấu hiệu có thể gồm:

- Write IOPS hoặc throughput ghi tăng theo chu kỳ.
- Storage latency và queue depth tăng khi checkpoint chạy.
- Dirty page hoặc số page chờ ghi tăng.
- Read query cũng chậm dù SQL không đổi vì read/write cùng cạnh tranh storage.
- Log flush hoặc checkpoint duration tăng.
- p99 có dạng răng cưa, tăng quanh các thời điểm checkpoint.

Tương quan theo thời gian là bằng chứng ban đầu, chưa phải chứng minh quan hệ nhân quả. Cần xác nhận write I/O thực sự chiếm tài nguyên mà truy vấn chậm đang cần.

### 4.2. Đọc read và write latency riêng

Nếu write latency tăng nhưng read latency ổn định, có thể vấn đề tập trung ở log hoặc đường ghi. Nếu cả read và write latency cùng tăng, storage device hoặc volume có thể đang bão hòa chung. Nếu storage latency thấp nhưng query vẫn chậm, xem CPU, lock, memory và plan.

Đo theo file hoặc volume khi có thể. Data file, transaction log, temp file và backup destination có thể nằm trên các thiết bị khác nhau và có hành vi khác nhau.

### 4.3. Checkpoint dồn dập và checkpoint kéo dài

Checkpoint quá thường xuyên có thể tạo nhiều đợt ghi và tăng write amplification. Checkpoint quá chậm hoặc bị giới hạn quá thấp có thể khiến dirty page tồn đọng, recovery window tăng hoặc tiến gần giới hạn log tùy engine.

Không nên chỉ tăng chu kỳ checkpoint để giảm p99. Thay đổi có thể làm tăng lượng log cần replay sau crash, tạo burst lớn hơn về sau hoặc gây rủi ro dung lượng. Cần xem checkpoint duration, dirty page, log generation, storage capacity, recovery objective và khả năng storage trước khi điều chỉnh.

## 5. Chẩn đoán công việc bảo trì

### 5.1. Index rebuild hoặc reorganize

Rebuild có thể đọc cấu trúc cũ, sắp xếp entry, tạo cấu trúc mới và ghi lượng lớn dữ liệu/log. Nó có thể tiêu thụ CPU, memory grant, temp space và I/O. Online rebuild giảm một số loại blocking nhưng không có nghĩa không ảnh hưởng tài nguyên hoặc không cần khóa ở một số giai đoạn.

Kiểm tra:

- Job nào đang chạy và index/table nào bị tác động?
- Số page và kích thước index?
- Read/write IOPS, log generation và temp usage?
- Có blocking hoặc schema/metadata lock không?
- p99 có tăng đúng trong thời gian job chạy?
- Có thể giới hạn concurrency hoặc chia nhỏ theo partition/index không?

### 5.2. VACUUM và cleanup

Trong PostgreSQL, VACUUM dọn các tuple version không còn cần thiết theo quy tắc visibility và giúp tái sử dụng không gian. VACUUM có thể đọc nhiều page và tạo I/O; autovacuum chạy đồng thời với workload. VACUUM FULL có hành vi rewrite và lock mạnh hơn VACUUM thông thường.

Trong InnoDB, purge thread dọn các phiên bản undo không còn cần thiết. Transaction dài có thể giữ read view cũ, làm purge không thể thu hồi phiên bản. Trong SQL Server và Oracle, các cơ chế version store/undo cleanup cũng có thể chịu ảnh hưởng bởi transaction hoặc snapshot kéo dài.

Không tắt cleanup chỉ vì maintenance tạo I/O. Nếu cleanup bị dồn lại, bloat, undo/history list hoặc version store có thể tăng và làm sự cố lớn hơn.

### 5.3. Statistics collection

ANALYZE, UPDATE STATISTICS hoặc DBMS_STATS có thể đọc mẫu dữ liệu, dùng CPU và I/O. Sau khi statistics thay đổi, optimizer có thể chọn execution plan khác. Nếu p99 tăng ngay sau statistics job, cần phân biệt:

- Job statistics trực tiếp gây tranh chấp tài nguyên.
- Statistics mới làm cardinality estimate thay đổi và plan bị regression.
- Cả hai xảy ra đồng thời.

So sánh plan trước/sau, estimated rows và actual rows. Không vội ép plan hoặc revert statistics nếu chưa xác định query nào bị ảnh hưởng và cách khôi phục an toàn.

### 5.4. Backup, snapshot và ETL

Backup có thể đọc nhiều data page và cạnh tranh read bandwidth. Snapshot có thể dùng copy-on-write hoặc cơ chế storage riêng; ETL có thể scan nguồn và ghi khối lượng lớn. Kiểm tra cả nguồn đọc, đích ghi, network và storage queue.

Nếu backup đẩy p99 lên cao, xem lịch, tốc độ đọc, compression CPU, network throughput và vị trí lưu backup. Có thể dùng replica hoặc snapshot storage nếu tính nhất quán và quy trình backup cho phép.

## 6. Chẩn đoán traffic spike và queueing

### 6.1. Offered load so với completed throughput

Nếu request đến nhanh hơn tốc độ database hoàn tất, queue tăng. Độ trễ end-to-end bao gồm cả thời gian chờ, vì vậy p99 có thể tăng trước khi CPU đạt 100%.

Theo dõi:

- Offered request rate.
- Completed transaction/request rate.
- Số request đang chờ.
- Pool pending và acquire latency.
- Database active session và worker queue.
- Timeout, reject và retry.

Nếu completed throughput đứng yên nhưng offered load tiếp tục tăng, hệ thống đã chạm giới hạn ở một tầng.

### 6.2. Connection pool saturation

Khi query chậm, connection bị giữ lâu hơn. Pool active tiến gần maximum và request mới chờ. Pool timeout có thể xuất hiện dù database không hiển thị nhiều query đang chạy, nếu connection bị giữ trong ứng dụng hoặc idle trong transaction.

Kiểm tra usage duration, leak detection, transaction age và stack trace. Không tăng pool ngay nếu database đang bão hòa CPU/I/O; tăng pool có thể đưa thêm query vào hàng đợi phía server.

### 6.3. Retry storm

Khi request timeout, client có thể retry. Nếu retry không có backoff và jitter, một spike ban đầu tạo thêm request mới đúng lúc database đang chậm. Tải tăng theo vòng lặp và kéo dài sự cố.

Giới hạn retry, dùng exponential backoff có jitter, idempotency key và deadline tổng. Không retry lỗi validation hoặc query timeout kéo dài mà không xác định khả năng phục hồi.

### 6.4. Hot key và lock contention

Spike có thể làm nhiều transaction cùng cập nhật một hàng, một tài khoản, một tồn kho hoặc một index page. Khi đó lock wait hoặc latch contention tăng dù tổng CPU và I/O chưa bão hòa.

Tìm blocker chain, transaction age, hot row và query fingerprint. Các giải pháp có thể gồm giảm critical section, phân phối cập nhật, batch hợp lý hoặc dùng mô hình counter/shard phù hợp nghiệp vụ.

## 7. Đo và chẩn đoán trên PostgreSQL

PostgreSQL sử dụng shared buffers, background writer và checkpointer. Checkpointer ghi các dirty buffer cần thiết xuống data file theo checkpoint. WAL được ghi riêng và phải tuân theo quy tắc write-ahead logging.

### 7.1. Quan sát session và wait event

~~~sql
SELECT
    pid,
    backend_type,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

Các wait event như IO, Lock, LWLock hoặc BufferPin có thể giúp phân loại chờ. Tên và chi tiết wait event thay đổi theo phiên bản. Một session không có wait event vẫn có thể đang chạy CPU-bound.

### 7.2. Quan sát checkpoint và I/O

Trên các phiên bản mới, có thể xem thống kê checkpoint trong pg_stat_checkpointer; các phiên bản cũ hơn có một phần thống kê trong pg_stat_bgwriter. pg_stat_io trên phiên bản hỗ trợ giúp phân tích hoạt động I/O theo backend/object/context.

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

Chỉ truy vấn view phù hợp với phiên bản đang chạy. Ghi lại hai mẫu để tính delta cho số checkpoint, số buffer được ghi, thời gian checkpoint và các counter I/O. Bật log_checkpoints trong môi trường phù hợp để có log duration và số buffer được ghi; đánh giá chi phí log trước khi bật rộng rãi.

### 7.3. Điều tra query bị chậm

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMP '2026-10-01'
  AND created_at < TIMESTAMP '2026-11-01';
~~~

EXPLAIN ANALYZE thực thi truy vấn, do đó chỉ chạy trên query an toàn và môi trường phù hợp. So sánh shared hit/read, temp read/write, actual rows, loops và thời gian từng node. Nếu query đọc nhiều page hơn baseline, kiểm tra cache state, plan và dữ liệu; nếu read latency tăng đồng thời checkpoint, kiểm tra storage contention.

### 7.4. Các thiết lập checkpoint cần hiểu

Các tham số thường được xem xét gồm:

- checkpoint_timeout: khoảng thời gian tối đa giữa các checkpoint theo cấu hình.
- max_wal_size: ngưỡng WAL có thể thúc đẩy checkpoint sớm khi vượt.
- checkpoint_completion_target: mục tiêu phân phối công việc checkpoint trong khoảng thời gian.
- max_wal_senders và replication settings: liên quan đến luồng replication, không phải tham số điều tốc checkpoint trực tiếp.

Không tăng max_wal_size hoặc thay đổi completion target chỉ để che write I/O. Đánh giá WAL generation, checkpoint frequency, checkpoint write time, storage capacity, archive throughput và recovery objective. Tên view và vị trí thống kê checkpoint thay đổi theo phiên bản PostgreSQL; phải đối chiếu đúng phiên bản trước khi áp dụng.

## 8. Đo và chẩn đoán trên MySQL InnoDB

InnoDB dùng buffer pool, redo log và page cleaner để quản lý page bẩn. Checkpoint tiến triển theo trạng thái redo và các page đã được flush; nếu dirty page hoặc checkpoint age tăng quá nhanh so với khả năng ghi, hệ thống có thể phải điều tiết hoặc chờ.

### 8.1. Kiểm tra trạng thái InnoDB

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Các phần cần xem:

- LOG: checkpoint age, log sequence và hoạt động redo.
- BUFFER POOL AND MEMORY: dirty pages, free pages và pending reads/writes.
- TRANSACTIONS: transaction lâu, lock wait và history list.
- FILE I/O: pending I/O và hoạt động đọc/ghi.

Định dạng output phụ thuộc phiên bản. Chụp nhiều mẫu cách nhau một khoảng thời gian để xem xu hướng, không chỉ đọc một snapshot.

### 8.2. Status variables

Có thể theo dõi delta của các biến:

- Innodb_buffer_pool_pages_dirty.
- Innodb_buffer_pool_pages_flushed.
- Innodb_buffer_pool_wait_free.
- Innodb_log_waits.
- Innodb_os_log_written.
- Innodb_data_reads và Innodb_data_writes.

Các biến là counter hoặc gauge khác nhau; không diễn giải tất cả như tốc độ. Lấy delta cho counter, còn gauge cần xem giá trị và xu hướng theo thời gian. Kết hợp Performance Schema file I/O summary để phân tích theo file và event.

### 8.3. Phân biệt checkpoint với query plan

~~~sql
EXPLAIN ANALYZE
SELECT id, status
FROM orders
WHERE tenant_id = 42
  AND created_at >= '2026-10-01'
  AND created_at < '2026-11-01';
~~~

Kiểm tra actual rows, iterator time và số vòng lặp. Nếu plan giữ nguyên nhưng thời gian đọc tăng khi page flush/write I/O tăng, nghi ngờ storage contention. Nếu plan thay đổi sau ANALYZE TABLE hoặc deploy, điều tra cardinality và index trước khi điều chỉnh checkpoint.

### 8.4. Điều chỉnh InnoDB có kiểm soát

Các biến như innodb_io_capacity, innodb_io_capacity_max, innodb_max_dirty_pages_pct và cấu hình redo log ảnh hưởng đến cách InnoDB flush page hoặc tiến triển checkpoint. Ý nghĩa và hành vi có thể thay đổi theo phiên bản.

Tăng I/O capacity quá cao có thể làm background flushing cạnh tranh với query; đặt quá thấp có thể để dirty page tích tụ và tạo áp lực về sau. Thay đổi từng biến trong môi trường kiểm thử, quan sát dirty page, checkpoint age, flush rate, storage latency và p99.

## 9. Đo và chẩn đoán trên SQL Server

SQL Server checkpoint ghi dirty page từ buffer pool xuống data file. Indirect checkpoint và target recovery time ảnh hưởng đến cách engine điều phối ghi nền. Index rebuild, statistics update, backup và tempdb workload có thể cùng cạnh tranh I/O, CPU và memory grant.

### 9.1. Kiểm tra I/O theo file

~~~sql
SELECT
    DB_NAME(vfs.database_id) AS database_name,
    mf.type_desc,
    mf.name AS file_name,
    vfs.num_of_reads,
    vfs.io_stall_read_ms,
    vfs.num_of_writes,
    vfs.io_stall_write_ms,
    vfs.size_on_disk_bytes
FROM sys.dm_io_virtual_file_stats(NULL, NULL) AS vfs
JOIN sys.master_files AS mf
  ON mf.database_id = vfs.database_id
 AND mf.file_id = vfs.file_id
ORDER BY vfs.io_stall_write_ms DESC;
~~~

Các giá trị là counter tích lũy từ lúc khởi động hoặc thời điểm thống kê được reset. Lấy hai mẫu và tính latency trung bình mỗi I/O bằng delta stall chia delta operation. Không dùng số tích lũy để kết luận storage đang chậm ở thời điểm hiện tại.

### 9.2. Wait statistics

~~~sql
SELECT TOP (20)
    wait_type,
    waiting_tasks_count,
    wait_time_ms,
    signal_wait_time_ms
FROM sys.dm_os_wait_stats
WHERE wait_type NOT LIKE 'SLEEP%'
ORDER BY wait_time_ms DESC;
~~~

Wait stats cũng là counter tích lũy. Cần lấy delta theo cửa sổ sự cố và loại bỏ wait nền không liên quan. Một số nhóm cần xem:

- PAGEIOLATCH_*: chờ page I/O.
- WRITELOG: chờ ghi/flush transaction log.
- IO_COMPLETION: chờ I/O hoàn tất.
- RESOURCE_SEMAPHORE: chờ memory grant.
- LCK_M_*: lock wait.
- SOS_SCHEDULER_YIELD: nhường CPU scheduler; cần xem cùng CPU và runnable queue.

Không gán nguyên nhân chỉ từ tên wait. Một wait có thể là hệ quả của bottleneck khác.

### 9.3. Xem request, blocking và checkpoint

~~~sql
SELECT
    session_id,
    status,
    command,
    wait_type,
    wait_time,
    blocking_session_id,
    total_elapsed_time,
    cpu_time,
    reads,
    writes,
    logical_reads
FROM sys.dm_exec_requests
WHERE session_id <> @@SPID
ORDER BY total_elapsed_time DESC;
~~~

Kết hợp sys.dm_os_performance_counters với các counter checkpoint, page writes và log flush phù hợp phiên bản. Extended Events có thể ghi sự kiện liên quan checkpoint, blocking, query duration hoặc maintenance. Không bật trace nặng không giới hạn trên production.

### 9.4. Kiểm tra maintenance

Với index rebuild, kiểm tra request đang chạy, wait, memory grant, tempdb, transaction log và blocking. Online index operation vẫn có thể dùng lượng lớn I/O/log và cần khóa ở một số giai đoạn.

Với statistics update, so sánh plan và cardinality trước/sau. Query Store có thể giúp tìm query regression theo thời gian và plan. Không xóa plan cache toàn instance chỉ để xử lý một query chậm.

## 10. Đo và chẩn đoán trên Oracle Database

Oracle sử dụng DBWR để ghi dirty buffer, redo log để bảo đảm recovery và checkpoint để cập nhật thông tin cần thiết về tiến độ ghi. Backup, index rebuild, statistics gathering và workload phân tích có thể cạnh tranh tài nguyên với giao dịch.

### 10.1. Kiểm tra session wait

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    event,
    wait_class,
    seconds_in_wait,
    blocking_session,
    sql_id
FROM v$session
WHERE username IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

Các event thường cần xem gồm:

- db file parallel write: DBWR ghi data file.
- log file parallel write: LGWR ghi redo.
- log file sync: foreground session chờ commit redo được flush.
- free buffer waits: session cần buffer trống và có thể đang chờ DBWR.
- db file sequential read và db file scattered read: các dạng đọc data file.
- enq: TX - row lock contention: chờ row lock.

Tên event cần được diễn giải theo hoạt động và phiên bản. Ví dụ log file sync tăng có thể liên quan latency redo hoặc commit rate cao, không nhất thiết là checkpoint trực tiếp.

### 10.2. Xem thống kê hệ thống

~~~sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'physical reads',
    'physical writes',
    'db block changes',
    'redo size',
    'user commits',
    'user rollbacks'
);
~~~

Lấy delta theo cửa sổ để tính tốc độ. Có thể dùng AWR/ASH nếu hệ thống có quyền sử dụng phù hợp; các báo cáo đó giúp liên hệ wait, SQL ID và thời điểm nhưng cần tuân thủ điều kiện cấp phép.

### 10.3. Kiểm tra checkpoint và redo

Các view như V$INSTANCE_RECOVERY, V$SYSSTAT, V$SYSTEM_EVENT và alert log có thể cung cấp thông tin recovery, checkpoint và wait. Tên counter và khả năng quan sát phụ thuộc phiên bản. Đọc alert log để xác định checkpoint, log switch, archive issue và thông báo I/O cùng thời điểm p99 tăng.

Nếu log file sync tăng, xem commit frequency, redo write latency và batching. Nếu free buffer waits hoặc DBWR write wait tăng, xem dirty buffer và data file I/O. Không tăng kích thước redo log hoặc thay checkpoint frequency chỉ dựa trên một wait event.

## 11. Phân biệt query regression với tranh chấp tài nguyên

Một query có thể chậm vì plan thay đổi hoặc vì cùng plan nhưng tài nguyên bên dưới chậm hơn. Hai trường hợp cần cách xử lý khác nhau.

### 11.1. Dấu hiệu query regression

- Query fingerprint cụ thể tăng latency.
- Execution plan hoặc plan hash thay đổi.
- Estimated rows khác actual rows đáng kể.
- Index seek chuyển thành scan, join order hoặc join type thay đổi.
- Logical reads, CPU hoặc số hàng trung gian tăng.
- Sự cố bắt đầu sau deploy, statistics update hoặc schema change.

### 11.2. Dấu hiệu resource contention

- Nhiều query không liên quan cùng chậm trong một cửa sổ.
- Plan và logical reads gần như giữ nguyên.
- Physical read/write latency, wait hoặc queue tăng.
- p99 tăng đồng thời với checkpoint, backup, maintenance hoặc spike.
- Khi tải nền kết thúc, query latency trở lại gần baseline mà không đổi plan.

### 11.3. Phép so sánh có kiểm soát

Chọn một query đại diện và ghi:

- Plan, tham số và actual rows.
- Logical reads, physical reads và CPU.
- Server execution time và end-to-end latency.
- Cache state và thời điểm chạy.
- Wait events hoặc wait stats trong cùng cửa sổ.

Nếu query chậm khi storage bận nhưng nhanh trở lại khi storage queue giảm, đó là bằng chứng của resource contention. Nếu query vẫn chậm sau khi tài nguyên bình thường và plan khác baseline, cần điều tra regression.

## 12. Quy trình triage khi p99 tăng

### Bước 1: Xác nhận phạm vi

Xác định p99 tăng ở toàn dịch vụ, một endpoint, một query, một tenant hay một database node. Kiểm tra p50/p95/p99, error rate và số request trong cửa sổ. Đảm bảo percentile được tính từ histogram hợp lệ.

### Bước 2: Xác định thời điểm và sự kiện

Đối chiếu mốc bắt đầu với checkpoint, backup, index maintenance, vacuum, statistics job, deploy, failover và traffic spike. Ghi cả thời điểm sự kiện kết thúc và thời gian p99 phục hồi.

### Bước 3: Tách thời gian ở ứng dụng

Kiểm tra thread queue, pool acquire, network, SQL duration và result fetch. Nếu pool wait tăng nhưng SQL time không tăng, điều tra pool saturation, leak hoặc usage time. Nếu SQL time tăng, chuyển sang database metrics.

### Bước 4: Tìm tài nguyên bị bão hòa

So sánh CPU, memory, I/O read/write latency, IOPS, queue depth, log flush, temp spill, worker và connection. Dùng delta counter và phân tích theo file/volume khi có thể.

### Bước 5: Tìm session chờ và blocker

Xem wait type/event, blocking chain, transaction age và query hiện tại. Phân biệt lock wait với I/O wait, CPU scheduling, memory grant và log wait.

### Bước 6: Kiểm tra query plan

So sánh plan, estimated/actual rows, logical/physical reads và query fingerprint trước/sau. Không thực thi lại query nặng trên production chỉ để có EXPLAIN ANALYZE; chọn cách thu thập an toàn.

### Bước 7: Giảm tác động có kiểm soát

Ưu tiên giới hạn concurrency, tạm hoãn job bảo trì có thể dừng an toàn, điều chỉnh lịch backup, route báo cáo sang replica hoặc giảm offered load. Tránh thay nhiều tham số database trong lúc chưa có bằng chứng.

### Bước 8: Xác nhận phục hồi

Kiểm tra p95/p99, throughput, queue, storage latency, checkpoint/maintenance progress và replication lag đã trở lại mục tiêu. Theo dõi đủ lâu để bảo đảm backlog không tăng lại.

## 13. Biện pháp giảm tác động theo nguyên nhân

### 13.1. Khi checkpoint gây write burst

- Xác nhận checkpoint frequency, duration, dirty page và storage write latency.
- Kiểm tra WAL/redo generation và tốc độ archive/replication.
- Điều chỉnh pacing hoặc dung lượng log chỉ sau khi đánh giá recovery objective và storage capacity.
- Tách data, log và backup I/O nếu kiến trúc storage hỗ trợ và phép đo cho thấy có lợi.
- Giảm write amplification bằng cách xem lại batch size, index thừa và cập nhật lặp.
- Kiểm tra storage throttling, snapshot và giới hạn IOPS ở tầng cloud/hypervisor.

Không tắt checkpoint, durability hoặc flush bảo vệ dữ liệu để giảm latency. Không thay đổi cấu hình log chỉ để p99 đẹp hơn nếu chưa đánh giá recovery sau crash.

### 13.2. Khi maintenance cạnh tranh tài nguyên

- Chạy ngoài peak và tránh chồng với backup, ETL hoặc batch.
- Giới hạn số job chạy song song.
- Chia rebuild hoặc cleanup theo index, partition hoặc nhóm nhỏ.
- Dùng chế độ online/low-priority khi engine hỗ trợ và hiểu giới hạn của nó.
- Đặt resource group hoặc workload priority cho job nền.
- Theo dõi log, temp space, I/O và replication lag.
- Chỉ hủy job khi biết trạng thái rollback/cleanup và tác động của việc dừng.

Không tắt autovacuum, purge hoặc cleanup chỉ vì chúng tạo I/O. Nếu cần giảm tốc độ, điều chỉnh có chủ đích và theo dõi bloat, history list, dead tuple hoặc version store để tránh nợ bảo trì tích tụ.

### 13.3. Khi traffic spike

- Áp dụng rate limit và admission control.
- Giới hạn concurrency theo loại endpoint và query.
- Đặt queue có giới hạn và timeout theo deadline.
- Dùng backoff có jitter và giới hạn retry.
- Tách reporting khỏi OLTP.
- Dùng cache hoặc kết quả tổng hợp khi nghiệp vụ cho phép.
- Scale ứng dụng không vượt ngân sách connection và capacity database.
- Bảo vệ hot key bằng thiết kế cập nhật phù hợp.

Tăng connection pool hoặc số worker mà không đo capacity có thể làm database quá tải nhanh hơn.

### 13.4. Khi query plan regression

- So sánh plan và cardinality trước/sau.
- Kiểm tra statistics, parameter sensitivity, schema và index.
- Tối ưu predicate, projection, join và phạm vi dữ liệu.
- Cân nhắc index hoặc partition pruning dựa trên workload.
- Dùng plan forcing/hint chỉ khi có bằng chứng và kế hoạch gỡ bỏ.
- Chạy benchmark cùng dữ liệu và cache state tương đương.

## 14. Ví dụ tình huống tổng hợp

Một API cập nhật đơn hàng có p99 bình thường 220 ms. Vào đầu mỗi giờ, p99 tăng lên 1,8 giây trong khoảng 4 phút. p50 chỉ tăng từ 32 ms lên 45 ms. Cùng thời điểm, một báo cáo tổng hợp bắt đầu chạy và database ghi nhiều page xuống storage.

### 14.1. Dữ liệu quan sát

| Chỉ số | Bình thường | Khi p99 tăng |
|---|---:|---:|
| Offered load | 800 req/s | 850 req/s |
| Completed throughput | 790 req/s | 805 req/s |
| p99 API | 220 ms | 1.800 ms |
| CPU database | 55% | 68% |
| Read latency | 2 ms | 14 ms |
| Write latency | 3 ms | 28 ms |
| Pool pending | 0 | 35 |
| Lock wait | Thấp | Gần như không đổi |
| Checkpoint/write activity | Bình thường | Tăng rõ |

### 14.2. Suy luận

Offered load chỉ tăng nhẹ, do đó spike traffic không phải lời giải thích duy nhất. Lock wait không tăng, trong khi read và write latency cùng tăng; điều này hướng sự chú ý tới storage contention. Pool pending tăng có thể là hệ quả của connection bị giữ lâu hơn do SQL chờ I/O.

Báo cáo và checkpoint xuất hiện cùng thời điểm. Cần kiểm tra báo cáo có scan lớn hay spill không, checkpoint có write burst không, hai hoạt động có dùng chung volume không và query plan của API có giữ nguyên không.

### 14.3. Hành động

1. Chuyển báo cáo sang replica hoặc giới hạn concurrency của báo cáo.
2. Đo lại storage latency và checkpoint activity.
3. Nếu checkpoint write burst vẫn ảnh hưởng, xem pacing, dirty page và storage capacity theo engine.
4. Đặt reporting pool và queue riêng để tránh chiếm connection OLTP.
5. Chạy lại workload hỗn hợp, xác nhận p99 API và thời gian báo cáo.

Không kết luận chỉ từ bảng số liệu trên rằng checkpoint là nguyên nhân duy nhất. Kết luận cần thêm bằng chứng về plan, I/O theo volume và thời điểm các sự kiện.

## 15. Kiểm chứng sau khi xử lý

Một biện pháp chỉ được coi là hiệu quả khi cải thiện mục tiêu mà không tạo vấn đề mới.

Đo lại trong cùng điều kiện:

- p50, p95, p99 và p99.9 của endpoint/query quan trọng.
- Offered load và completed throughput.
- Error, timeout, retry và queue depth.
- Pool active/idle/pending và acquire latency.
- CPU, memory, read/write IOPS và storage latency.
- Checkpoint duration, dirty page và log generation.
- Maintenance duration, temp usage và blocking.
- Lock wait, deadlock, transaction age và wait events.
- Replication lag và khả năng bắt kịp sau job.

Kiểm tra cả thời gian phục hồi sau khi sự kiện kết thúc. Nếu p99 trở lại bình thường nhưng replication backlog hoặc log/archive backlog vẫn tăng, hệ thống chưa thực sự ổn định.

### 15.1. So sánh trước và sau

Giữ nguyên query mix, dữ liệu, cache state, mức concurrency và khoảng thời gian đo. Nếu thay đổi lịch maintenance, chạy test ở thời điểm tương đương. Nếu thay đổi checkpoint pacing, cần quan sát đủ nhiều chu kỳ checkpoint để tránh kết luận từ một cửa sổ ngắn.

### 15.2. Xác nhận tính đúng đắn và độ bền

Không hy sinh durability hoặc consistency để đạt p99 thấp hơn. Sau khi thay đổi, xác nhận:

- Commit vẫn được ghi bền vững theo cấu hình yêu cầu.
- Không mất dữ liệu hoặc bỏ qua cleanup cần thiết.
- Replica và backup vẫn hoạt động.
- Transaction không bị rollback ngoài ý muốn.
- Báo cáo vẫn đọc dữ liệu theo freshness và snapshot policy.
- Job bảo trì hoàn thành trong cửa sổ được phép.

## 16. Thiết kế cảnh báo và runbook

### 16.1. Cảnh báo theo SLO và tín hiệu nguyên nhân

Thiết lập cảnh báo theo:

- p99 vượt SLO trong một cửa sổ đủ dài và có đủ request mẫu.
- Error/timeout rate tăng.
- Pool pending hoặc acquire p95 vượt ngưỡng.
- Storage read/write latency và queue depth tăng.
- Checkpoint duration hoặc dirty page backlog bất thường.
- Lock wait, deadlock hoặc transaction age tăng.
- Replication lag hoặc log backlog vượt mục tiêu.

Tránh cảnh báo chỉ dựa trên một counter tích lũy hoặc một lần p99 cao khi số mẫu rất nhỏ. Kết hợp triệu chứng người dùng với tín hiệu tài nguyên.

### 16.2. Nội dung runbook tối thiểu

- Dashboard p50/p95/p99 theo endpoint và query.
- Lịch checkpoint, backup và maintenance.
- Cách xác định session blocker và query tốn tài nguyên.
- Cách xem I/O theo data/log/temp volume.
- Giới hạn an toàn để tạm dừng hoặc giảm concurrency job nền.
- Người chịu trách nhiệm phê duyệt thay đổi database.
- Điều kiện dừng và rollback.
- Tiêu chí xác nhận p99, queue và replication đã phục hồi.

Không tự động kill mọi session chạy lâu. Một checkpoint, rollback hoặc cleanup nội bộ có thể cần hoàn tất để bảo vệ tính nhất quán. Trước khi hủy query hoặc maintenance job, xác định loại công việc, trạng thái transaction và chi phí rollback.

## 17. Những sai lầm thường gặp

- **Kết luận checkpoint là nguyên nhân chỉ vì trùng thời điểm:** cần bằng chứng về I/O, wait và tác động lên query.
- **Chỉ nhìn CPU:** storage, log, lock, memory grant hoặc pool có thể là nút thắt.
- **Chỉ nhìn latency trung bình:** p99 có thể tăng mạnh trong khi average thay đổi ít.
- **Lấy trung bình p99 của nhiều instance:** percentile phải được tính từ histogram/dữ liệu gộp đúng cách.
- **Dùng counter tích lũy như tốc độ hiện tại:** cần lấy delta theo cửa sổ và biết thời điểm reset.
- **Tăng pool khi database đang bão hòa:** có thể đẩy thêm tải vào database và tăng queue.
- **Tắt checkpoint hoặc cleanup:** tạo rủi ro recovery, bloat hoặc backlog lớn hơn.
- **Chạy rebuild, backup và ETL cùng giờ cao điểm:** làm tài nguyên nền cạnh tranh với giao dịch.
- **Hủy maintenance mà không đánh giá rollback:** có thể tạo thêm I/O hoặc thời gian phục hồi.
- **Tăng timeout để che p99:** request giữ connection lâu hơn và queue có thể lớn hơn.
- **Không kiểm tra plan sau statistics update:** có thể bỏ sót query regression.
- **Không đo thời gian phục hồi:** hệ thống có thể hết spike nhưng backlog vẫn còn.
- **Thay nhiều tham số cùng lúc:** không xác định được biện pháp nào tạo ra cải thiện.

## 18. Checklist chẩn đoán p99 tăng

- [ ] Đã xác nhận p99 bằng histogram hợp lệ và có đủ mẫu.
- [ ] Đã xem p50, p95, p99, p99.9 cùng error/timeout rate.
- [ ] Đã phân tách latency ở ứng dụng, pool, network và database.
- [ ] Đã đối chiếu timestamp với checkpoint, maintenance, backup, deploy và traffic spike.
- [ ] Đã lấy delta counter thay vì chỉ đọc số tích lũy.
- [ ] Đã đo CPU, memory, IOPS, read/write latency và storage queue.
- [ ] Đã kiểm tra dirty page, checkpoint duration, log generation và flush latency.
- [ ] Đã kiểm tra maintenance job, temp usage, blocking và replication lag.
- [ ] Đã kiểm tra active/idle/pending connection và transaction age.
- [ ] Đã xem wait event/type, blocker chain và deadlock.
- [ ] Đã so sánh execution plan, estimated/actual rows và logical/physical reads.
- [ ] Đã phân biệt query regression với resource contention.
- [ ] Đã chọn biện pháp giảm tác động theo nguyên nhân có bằng chứng.
- [ ] Đã giữ durability, consistency và cleanup cần thiết.
- [ ] Đã đo lại p99, throughput, queue và thời gian phục hồi trong điều kiện tương đương.
- [ ] Đã cập nhật cảnh báo và runbook sau khi xử lý.

Độ trễ p99 tăng trong checkpoint, bảo trì hoặc đột biến tải là dấu hiệu hệ thống đang có một nhóm request phải chờ lâu hơn bình thường. Cần xác định request chậm ở tầng nào, tài nguyên nào bị tranh chấp và sự kiện nào có quan hệ thời gian với sự cố. Kết hợp percentile, delta counter, wait event, execution plan và I/O theo file sẽ giúp phân biệt checkpoint pressure, maintenance contention, traffic spike và query regression. Chỉ điều chỉnh sau khi có bằng chứng, rồi đo lại cả SLO, throughput, queue và thời gian phục hồi để xác nhận hệ thống ổn định.

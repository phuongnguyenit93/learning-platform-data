# Chi phí I/O, thiết bị lưu trữ và tham số liên quan trong PostgreSQL

I/O (input/output) là một trong những yếu tố quyết định hiệu năng của PostgreSQL. Khi một truy vấn chậm, nguyên nhân có thể nằm ở CPU, query plan, memory, lock hoặc storage. Một máy chủ còn CPU nhưng storage latency cao vẫn có thể chậm vì backend phải chờ đọc page, ghi WAL, flush dữ liệu hoặc tạo temporary files.

Tối ưu I/O không đơn giản là chọn ổ đĩa có IOPS cao nhất hoặc tăng một tham số cache. Cần hiểu workload thực tế, loại thao tác đọc/ghi, access pattern tuần tự hay ngẫu nhiên, độ trễ, thông lượng, queue depth, durability và cách PostgreSQL sử dụng memory/WAL.

Bốn khái niệm phần cứng cần phân biệt:

- **Latency**: thời gian hoàn thành một thao tác I/O.
- **IOPS**: số thao tác I/O mỗi giây.
- **Throughput**: lượng dữ liệu truyền mỗi giây, thường đo bằng MB/s hoặc GB/s.
- **Queue depth**: số yêu cầu I/O đang chờ hoặc đang được xử lý đồng thời.

PostgreSQL còn có nhiều lớp đệm và cơ chế ghi: shared buffers, OS page cache, WAL buffers, background writer, checkpointer, vacuum và temporary files. Một thay đổi cấu hình có thể giảm I/O ở một lớp nhưng tăng áp lực ở lớp khác.

~~~mermaid
flowchart TD
    A["SQL workload"] --> B["Planner: chọn access path"]
    B --> C["PostgreSQL shared buffers"]
    C -->|"Cache hit"| D["Trả dữ liệu từ memory"]
    C -->|"Cache miss"| E["OS / storage read"]
    F["INSERT / UPDATE / DELETE"] --> G["WAL buffers"]
    G --> H["WAL write + flush"]
    F --> I["Dirty data pages"]
    I --> J["Background writer / checkpointer"]
    J --> K["Data storage"]
    E --> K
    L["Sort / hash / temp objects"] --> M["Temporary files"]
    M --> K
~~~

Bài học thuộc chương **Tối ưu tài nguyên**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu đặc tính thiết bị lưu trữ, mô hình chi phí I/O, cache, WAL/checkpoint, vacuum, temporary files, các tham số liên quan và cách đo hiệu năng trước khi thay đổi cấu hình.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của I/O trong hiệu năng PostgreSQL.
2. Phân biệt latency, IOPS, throughput và queue depth.
3. So sánh HDD, SATA SSD, NVMe, SAN và cloud block storage.
4. Phân biệt random I/O và sequential I/O.
5. Hiểu data directory, WAL, temporary files và tablespaces tạo ra các loại I/O nào.
6. Mô tả vai trò của shared buffers và OS page cache.
7. Phân biệt shared_buffers với effective_cache_size.
8. Hiểu random_page_cost và seq_page_cost là planner cost estimates.
9. Điều chỉnh effective_io_concurrency và maintenance_io_concurrency phù hợp.
10. Kiểm soát work_mem, temporary files và temp_file_limit.
11. Hiểu ảnh hưởng của WAL, fsync, synchronous_commit và wal_sync_method.
12. Điều chỉnh checkpoint và background writer dựa trên số liệu.
13. Hiểu vacuum/autovacuum tạo I/O như thế nào.
14. Theo dõi I/O bằng pg_stat_io, pg_stat_database và pg_stat_wal.
15. Phân tích buffer/I/O trong EXPLAIN.
16. Kết hợp PostgreSQL statistics với OS/storage metrics.
17. Thiết kế benchmark đại diện cho workload.
18. Xây dựng quy trình tối ưu có đo lường và rollback.

## 2. I/O trong database là gì?

I/O là hoạt động trao đổi dữ liệu giữa PostgreSQL, memory và thiết bị lưu trữ. Trong thực tế, một transaction có thể gây ra nhiều loại I/O:

- Đọc data pages để tìm row.
- Đọc index pages để xác định vị trí row.
- Ghi WAL records trước khi data pages được ghi.
- Flush WAL để đáp ứng durability.
- Ghi dirty data pages theo checkpoint/background writer.
- Đọc hoặc ghi temporary files khi sort/hash không đủ memory.
- Đọc metadata, catalog và relation files.
- Đọc/ghi archive WAL hoặc backup files qua các công cụ bên ngoài.

Không phải mọi thao tác SQL đều trực tiếp truy cập disk. Nếu page đã nằm trong shared buffers hoặc OS page cache, lần đọc có thể được phục vụ từ memory. Tuy vậy, cache hit trong PostgreSQL và cache hit ở OS là hai khái niệm khác nhau.

### Read path đơn giản

~~~text
Query executor
     |
     v
Shared buffers
     |
     +-- Page hit --> dùng page trong memory
     |
     +-- Page miss
            |
            v
        OS page cache
            |
            +-- OS cache hit --> trả page
            |
            +-- OS cache miss --> storage device
~~~

### Write path đơn giản

~~~text
Transaction modifies data
          |
          +--> WAL record in WAL buffers
          |         |
          |         v
          |      WAL write/flush
          |
          +--> Dirty data page in shared buffers
                    |
                    v
             Background writer / checkpoint
                    |
                    v
               Data files
~~~

WAL phải được ghi bền vững trước data page tương ứng theo write-ahead logging rule. Điều này giúp PostgreSQL phục hồi thay đổi sau crash.

## 3. Bốn chỉ số của thiết bị lưu trữ

### Latency

Latency là thời gian từ lúc gửi yêu cầu I/O tới lúc nhận kết quả. Với database, latency thấp thường rất quan trọng vì nhiều query có thể phải chờ các lần đọc nhỏ nối tiếp nhau.

Ví dụ, một index lookup có thể cần đọc root page, internal page rồi leaf page và data page. Nếu mỗi lần đọc đều phải xuống storage, tổng latency có thể tăng đáng kể.

Nên xem latency theo percentile:

- p50: trung vị.
- p95: 95% thao tác có latency không vượt quá giá trị này.
- p99: 99% thao tác có latency không vượt quá giá trị này.
- Maximum: giá trị lớn nhất quan sát được, thường nhạy với outlier.

Average latency có thể che giấu các đợt spike. Một hệ thống có average thấp nhưng p99 rất cao vẫn có thể tạo timeout ở ứng dụng.

### IOPS

IOPS đo số thao tác I/O mỗi giây. IOPS phụ thuộc kích thước request, loại đọc/ghi, random/sequential pattern và giới hạn thiết bị.

Một volume quảng cáo 50.000 IOPS không có nghĩa PostgreSQL luôn đạt 50.000 IOPS. Có thể còn giới hạn ở:

- Throughput của volume.
- Queue depth.
- CPU của máy chủ.
- Network path tới storage.
- Hypervisor hoặc cloud throttling.
- Filesystem.
- Số backend phát sinh I/O.
- Kích thước block và read/write mix.

### Throughput

Throughput đo lượng dữ liệu truyền trong một đơn vị thời gian. Một workload sequential scan có thể cần throughput cao, trong khi OLTP index lookup thường nhạy với latency và random IOPS.

IOPS và throughput có liên hệ qua kích thước request:

\[
Throughput \approx IOPS \times Average\ I/O\ size
\]

Ví dụ, 10.000 IOPS với request trung bình 16 KiB tương đương khoảng 156 MiB/s trước khi tính overhead. Đây chỉ là phép quy đổi, không phải cam kết hiệu năng của thiết bị.

### Queue depth

Queue depth là số yêu cầu I/O đang chờ hoặc đang được xử lý. Tăng queue depth có thể giúp thiết bị tận dụng song song, nhưng queue quá sâu có thể làm latency tăng.

Không nên tối ưu chỉ để đạt IOPS cao nhất. Với database OLTP, latency ổn định và tail latency thấp thường quan trọng hơn throughput peak.

## 4. Random I/O và sequential I/O

**Random I/O** truy cập các block ở vị trí không liên tiếp. Index lookup, nested-loop join và nhiều thao tác OLTP có thể tạo random reads/writes.

**Sequential I/O** truy cập các block liên tiếp hoặc gần liên tiếp. Sequential scan, backup stream và một số thao tác bulk có thể tạo access pattern tuần tự.

| Đặc điểm | Random I/O | Sequential I/O |
| --- | --- | --- |
| Truy cập | Block phân tán | Block liên tiếp |
| Quan trọng | Latency và IOPS | Throughput |
| Ví dụ | Index lookup, point lookup | Sequential scan, backup |
| HDD | Bị ảnh hưởng mạnh bởi seek | Có thể đạt throughput tốt hơn random |
| SSD/NVMe | Thường xử lý tốt hơn HDD | Thông lượng cao |

SSD không có cơ chế seek cơ học như HDD, nhưng random I/O vẫn có chi phí về controller, firmware, flash translation layer và queueing. Không nên xem random I/O là miễn phí.

### Một query có thể dùng cả hai

Ví dụ query lọc theo index có thể đọc index pages ngẫu nhiên rồi truy cập heap pages phân tán. Nếu điều kiện chọn nhiều rows, planner có thể chọn bitmap heap scan để gom các heap block và cải thiện locality.

Sequential scan không mặc định là xấu. Nếu query cần phần lớn bảng, đọc tuần tự có thể nhanh và ít tốn công hơn hàng nghìn index lookups.

## 5. Các loại thiết bị lưu trữ

### HDD

HDD có đĩa quay và đầu đọc cơ học. Đặc điểm:

- Giá trên mỗi GB thường thấp.
- Sequential throughput có thể phù hợp cho archive hoặc backup.
- Random I/O latency cao hơn SSD do seek/rotation.
- Hiệu năng phụ thuộc rotational speed, cache, controller và workload.

HDD thường không phải lựa chọn tốt cho workload OLTP nhiều random reads/writes có yêu cầu latency thấp.

### SATA SSD

SATA SSD loại bỏ seek cơ học và thường cải thiện đáng kể random I/O so với HDD. Giao diện SATA có giới hạn throughput thấp hơn NVMe hiện đại.

Có thể phù hợp với workload vừa phải hoặc môi trường có ngân sách giới hạn.

### NVMe SSD

NVMe dùng PCIe và giao thức tối ưu cho thiết bị flash. Đặc điểm thường gặp:

- Latency thấp.
- Nhiều queue và queue depth lớn.
- IOPS và throughput cao.
- Phù hợp với workload database có random I/O cao.

Cần đánh giá endurance, power-loss protection, firmware, thermal throttling và độ bền khi ghi liên tục.

### SAN và network block storage

SAN hoặc network block storage có thể cung cấp volume dùng chung hoặc quản lý tập trung. Hiệu năng phụ thuộc:

- Network bandwidth và latency.
- Storage controller.
- Multipathing.
- QoS/throttling.
- Cache policy.
- Shared contention.
- Failure domain.

Một storage array mạnh vẫn có thể chậm nếu nhiều tenant hoặc volume cạnh tranh tài nguyên.

### Cloud block storage

Cloud volume thường có giới hạn IOPS và throughput riêng, đôi khi gắn với kích thước volume hoặc loại instance. Cần xem:

- Baseline và burst performance.
- IOPS provisioned.
- Throughput cap.
- Instance-level bandwidth.
- Queue length và burst credits.
- Latency theo availability zone.
- Snapshot/backup impact.
- Durability guarantees.

Không lấy con số tối đa trong tài liệu marketing làm kỳ vọng thực tế. Benchmark trên đúng instance, volume type, filesystem và workload.

## 6. Chọn storage theo workload

| Workload | Nhu cầu nổi bật | Lưu ý |
| --- | --- | --- |
| OLTP nhiều point lookups | Latency thấp, random IOPS | NVMe hoặc SSD hiệu năng ổn định |
| Data warehouse | Throughput, parallel reads | Sequential bandwidth và concurrency |
| Batch ETL | Throughput và temporary I/O | Temp storage, memory, parallelism |
| WAL-heavy workload | Low-latency durable writes | WAL device, fsync latency, power-loss protection |
| Backup/archive | Dung lượng và sequential throughput | Storage rẻ hơn nếu restore time phù hợp |
| Mixed workload | Cân bằng read/write/latency | Benchmark theo workload thực tế |

Đừng chọn storage chỉ dựa vào dung lượng. Hai volume cùng 1 TB có thể khác xa về IOPS, throughput, latency, durability và khả năng duy trì hiệu năng.

## 7. Storage layout của PostgreSQL

Một PostgreSQL cluster thường có:

- Data directory: relation files, catalog, control files và cấu hình.
- WAL directory: mặc định là thư mục pg_wal trong data directory.
- Temporary files: thường nằm trong data directory hoặc tablespace được chọn.
- Tablespaces: ánh xạ relation tới các vị trí lưu trữ khác.
- Archive destination: nơi lưu WAL đã archive, thường do archive_command hoặc archive module quản lý.
- Backup destination: nơi lưu base backups và các artifact backup.

### Có nên tách WAL và data ra thiết bị riêng?

Tách WAL và data có thể hữu ích khi:

- WAL write latency là bottleneck rõ ràng.
- Data workload tạo random I/O lớn đồng thời với WAL flush.
- Có thiết bị riêng với durability và performance phù hợp.
- Storage path thực sự độc lập.

Tuy nhiên, nếu hai volume vẫn dùng chung controller, network hoặc physical storage pool, lợi ích có thể nhỏ. Tách volume còn làm tăng độ phức tạp vận hành, capacity planning và recovery.

### Có nên tách temporary files?

Một tablespace riêng cho temporary objects có thể giúp cô lập temp I/O khỏi data files. Nhưng nếu temp workload quá lớn, thiết bị riêng vẫn có thể bị bão hòa. Hãy đo temp bytes và latency trước khi quyết định.

### Tablespaces

Có thể tạo tablespace trên một đường dẫn do PostgreSQL service account truy cập:

~~~sql
CREATE TABLESPACE fast_data
LOCATION '/srv/postgresql/fast_data';
~~~

Sau đó tạo table/index trong tablespace:

~~~sql
CREATE TABLE orders_archive (
    order_id bigint,
    created_at timestamptz,
    total_amount numeric(12,2)
) TABLESPACE fast_data;
~~~

Tablespace chỉ thay đổi nơi lưu relation. Nó không tự phân phối một table thành nhiều thiết bị và không tự bảo đảm hiệu năng. Đường dẫn phải được chuẩn bị đúng quyền và phải được đưa vào backup/restore plan.

## 8. Durability và thiết bị lưu trữ

PostgreSQL dựa vào hệ điều hành và storage để thực hiện write/flush/sync. Nếu thiết bị hoặc controller báo đã flush nhưng thực tế chưa lưu bền vững, database có thể mất dữ liệu khi mất điện.

Các yếu tố cần đánh giá:

- Power-loss protection trên SSD/controller.
- Battery-backed hoặc flash-backed write cache.
- Cache write-through/write-back policy.
- Filesystem và mount options.
- Virtualization/storage layer.
- Cloud volume durability guarantees.
- Hành vi fsync/flush thực tế.
- Backup và recovery test.

Không tắt durability settings để cải thiện benchmark. Một benchmark nhanh hơn nhưng không bảo đảm dữ liệu sau crash không phải tối ưu hợp lệ cho production.

## 9. fsync và full_page_writes

Hai setting cốt lõi:

~~~conf
fsync = on
full_page_writes = on
~~~

### fsync

Khi bật, PostgreSQL yêu cầu hệ điều hành/storage flush dữ liệu cần thiết để bảo đảm durability theo cơ chế được hỗ trợ. Tắt fsync có thể làm database mất dữ liệu hoặc hỏng sau crash/power loss.

### full_page_writes

Khi bật, PostgreSQL ghi full-page image vào WAL trong những điều kiện cần thiết sau checkpoint, giúp phục hồi khỏi torn page.

Tắt full_page_writes có thể làm tăng rủi ro corruption sau crash nếu storage không bảo đảm atomic page writes.

### synchronous_commit

~~~conf
synchronous_commit = on
~~~

Setting này điều khiển khi nào COMMIT trả về so với WAL flush. Nó ảnh hưởng durability của transaction đã được xác nhận, không trực tiếp thay đổi việc data pages đã được ghi xuống heap files hay chưa.

Với asynchronous replication, synchronous_commit=on vẫn bảo đảm local WAL flush theo cấu hình, nhưng không đợi standby remote xác nhận. Với synchronous replication, nó có thể đợi standby theo synchronous_standby_names.

Không nhầm synchronous_commit với synchronous replication hoặc với fsync.

## 10. WAL và I/O

Mỗi transaction sửa dữ liệu tạo WAL records. WAL là write-ahead log: WAL cần được ghi trước data pages tương ứng.

WAL workload thường gồm:

- Ghi WAL buffers ra WAL segment.
- Flush WAL khi commit hoặc theo nhu cầu.
- Ghi full-page images.
- WAL writes do bulk load/index build.
- Archive WAL.
- Replication streaming.
- WAL reads khi recovery/standby replay.

### wal_buffers

~~~conf
wal_buffers = -1
~~~

Giá trị -1 yêu cầu PostgreSQL tự chọn WAL buffers theo version/configuration. Thường không cần chỉnh thủ công nếu chưa có bằng chứng WAL buffer pressure.

### wal_compression

~~~conf
wal_compression = on
~~~

Có thể nén full-page images trong WAL trên các phiên bản hỗ trợ. Nén giảm lượng WAL ghi/đọc nhưng tăng CPU. Benchmark theo tỷ lệ CPU và storage bottleneck.

### wal_sync_method

Tham số này chọn phương thức đồng bộ WAL theo các lựa chọn được hỗ trợ trên nền tảng. Giá trị phù hợp phụ thuộc OS/filesystem/storage. Không đổi chỉ vì một blog benchmark; hãy xem tài liệu đúng OS và đo fsync latency.

### WAL và storage riêng

WAL thường có write pattern khác data files: append-oriented và nhạy với flush latency. Một thiết bị riêng có thể hữu ích nếu workload data I/O gây contention, nhưng chỉ khi thiết bị đó thực sự độc lập và có durability phù hợp.

## 11. Checkpoint và write I/O

Checkpoint ghi dirty buffers xuống data files và tạo checkpoint record trong WAL. Checkpoint quá thường xuyên có thể tạo write pressure; checkpoint quá thưa có thể làm recovery cần replay nhiều WAL hơn.

Các tham số thường dùng:

~~~conf
checkpoint_timeout = '15min'
max_wal_size = '4GB'
min_wal_size = '1GB'
checkpoint_completion_target = 0.9
log_checkpoints = on
~~~

Các giá trị chỉ là ví dụ. Tính theo WAL generation rate, disk capacity, replication slots, archive và recovery objectives.

### checkpoint_timeout

Thời gian tối đa giữa các checkpoint theo timeout. Tăng có thể giảm số checkpoint do thời gian nhưng có thể tăng lượng WAL cần replay sau crash.

### max_wal_size

Ngưỡng mềm điều khiển khi PostgreSQL yêu cầu checkpoint do WAL growth. Đây không phải giới hạn cứng cho thư mục pg_wal. Replication slots hoặc archive failure có thể làm WAL vượt xa ngưỡng này.

### checkpoint_completion_target

Điều khiển mục tiêu trải đều công việc ghi checkpoint trong khoảng thời gian. Giá trị cao giúp giảm burst I/O nhưng cần storage đủ throughput để hoàn tất.

### log_checkpoints

Bật để ghi lý do và thời gian checkpoint, số buffers ghi và thông tin liên quan. Dùng log này để biết checkpoint do timeout hay requested.

## 12. Background writer

Background writer ghi một số dirty buffers trước khi backend cần tái sử dụng buffer. Mục tiêu là giảm việc backend phải tự ghi page trong lúc xử lý query.

Một số tham số:

~~~conf
bgwriter_delay = '200ms'
bgwriter_lru_maxpages = 100
bgwriter_lru_multiplier = 2.0
~~~

Ý nghĩa khái quát:

- bgwriter_delay: khoảng chờ giữa các vòng hoạt động.
- bgwriter_lru_maxpages: số page tối đa background writer cố ghi trong một vòng.
- bgwriter_lru_multiplier: hệ số điều chỉnh số page dựa trên nhu cầu gần đây.

Background writer không thay checkpointer. Nó giúp chuẩn bị buffer sạch; checkpoint vẫn có trách nhiệm ghi các dirty buffers cần thiết theo checkpoint process.

Tăng bgwriter_lru_maxpages có thể tăng background write I/O. Nếu storage đã bão hòa, tăng tham số có thể làm contention nặng hơn.

## 13. Cache: shared_buffers

shared_buffers là vùng shared memory PostgreSQL dùng để cache data pages.

Ví dụ:

~~~conf
shared_buffers = '8GB'
~~~

Đây chỉ là giá trị minh họa. Một điểm bắt đầu thường được tài liệu PostgreSQL nhắc tới là khoảng 25% RAM cho máy chủ database chuyên dụng, nhưng workload, RAM, OS cache, connection count và memory consumers có thể khiến giá trị tối ưu khác nhiều.

### Tăng shared_buffers có luôn tốt?

Không. Khi tăng shared_buffers:

- PostgreSQL có thể giữ nhiều data pages hơn.
- Cache hit trong shared buffers có thể tăng.
- Memory dành cho OS page cache giảm.
- Checkpoint/background writer có thể xử lý nhiều dirty buffers hơn.
- Shared memory footprint tăng.
- Các workload khác có thể thiếu memory.

Hãy đo buffer hit/read, OS cache behavior, memory pressure và latency. Đừng tối ưu một con số cache hit ratio riêng lẻ.

### shared_buffers không phải tổng memory PostgreSQL

PostgreSQL còn dùng memory cho:

- work_mem của sort/hash operations.
- maintenance_work_mem.
- temp_buffers.
- backend process overhead.
- WAL buffers.
- parallel workers.
- extensions và shared memory structures.

Tính tổng memory trong tình huống concurrency cao, không chỉ lấy shared_buffers.

## 14. OS page cache

PostgreSQL thông thường dùng filesystem cache của hệ điều hành bên cạnh shared buffers. Khi PostgreSQL đọc page từ file, page có thể đã nằm trong OS page cache dù không có trong shared buffers.

Vì vậy:

- pg_stat_database.blks_read không nhất thiết là số lần đọc physical disk.
- EXPLAIN BUFFERS read có nghĩa page được đọc vào shared buffers, không chứng minh thiết bị vật lý phải truy cập.
- OS metrics cần thiết để xác nhận physical storage I/O.

Không nên kết luận cache miss trong PostgreSQL tương đương disk read.

### Memory pressure

Nếu hệ điều hành liên tục reclaim page cache hoặc swap, query latency có thể tăng. Database server production nên kiểm soát swap behavior, memory overcommit và các process khác theo chính sách hệ điều hành.

## 15. effective_cache_size

~~~conf
effective_cache_size = '24GB'
~~~

effective_cache_size là ước lượng lượng cache có sẵn cho một query, bao gồm phần cache PostgreSQL dự kiến có thể sử dụng từ shared buffers và OS page cache. Nó **không cấp phát memory** và không phải giới hạn memory.

Planner dùng ước lượng này khi đánh giá khả năng một index access có thể tìm thấy page trong cache.

Nếu đặt quá thấp, planner có thể đánh giá index scan đắt hơn thực tế. Nếu đặt quá cao, planner có thể giả định cache hit nhiều hơn thực tế và chọn index plan không phù hợp.

Đặt theo RAM thực tế, shared_buffers, OS page cache còn lại và các workload cạnh tranh. Đây là planner hint, không phải cache size đo được.

## 16. Planner cost: seq_page_cost và random_page_cost

Planner dùng cost units để so sánh các plan. Hai tham số quan trọng:

~~~conf
seq_page_cost = 1.0
random_page_cost = 4.0
~~~

Các giá trị trên là ví dụ phổ biến; default có thể thay đổi theo version/distribution hoặc cấu hình.

- seq_page_cost: cost tương đối của một page đọc tuần tự.
- random_page_cost: cost tương đối của một page đọc ngẫu nhiên.

Đây là đơn vị cost tương đối trong mô hình planner, không phải milliseconds hoặc IOPS thực tế.

### Khi nào điều chỉnh random_page_cost?

SSD/NVMe có thể làm random reads rẻ hơn tương đối so với sequential reads, vì không có seek cơ học. Có thể cân nhắc giảm random_page_cost nếu benchmark cho thấy planner đang đánh giá random index access quá đắt.

Nhưng giảm quá thấp có thể khiến planner chọn index scan cho query cần đọc phần lớn bảng, gây nhiều random I/O và chậm hơn sequential scan.

### Không tối ưu chỉ một tham số

Planner còn dùng:

- cpu_tuple_cost.
- cpu_index_tuple_cost.
- cpu_operator_cost.
- parallel setup/tuple costs.
- effective_cache_size.
- Statistics về selectivity/cardinality.
- Correlation và các đặc tính index.

Nếu plan sai, kiểm tra statistics, index, data distribution và EXPLAIN trước khi đổi cost constants.

## 17. effective_io_concurrency

Tham số:

~~~conf
effective_io_concurrency = 100
~~~

Nó cho PostgreSQL biết mức I/O concurrency có thể hữu ích cho một số operations, đặc biệt bitmap heap scans và prefetching trên các storage systems hỗ trợ asynchronous I/O phù hợp.

Giá trị phù hợp phụ thuộc storage và platform. HDD đơn lẻ, SSD, RAID array, SAN và cloud volume có behavior khác nhau.

Tăng giá trị có thể cải thiện throughput khi thiết bị xử lý song song tốt, nhưng cũng có thể làm tăng queueing hoặc contention. Benchmark với query plan có bitmap heap scan và workload thực tế.

### maintenance_io_concurrency

Trên các version hỗ trợ, maintenance_io_concurrency điều khiển concurrency cho một số maintenance operations như vacuum. Nó có thể giúp tận dụng storage song song trong maintenance nhưng cần xem version và loại thiết bị.

Không mặc định đặt hai tham số bằng nhau; workload query và maintenance có thể khác.

## 18. work_mem và temporary files

work_mem là lượng memory cơ bản mà một query operation như sort hoặc hash có thể dùng trước khi spill ra temporary files.

Ví dụ:

~~~conf
work_mem = '16MB'
hash_mem_multiplier = 2.0
temp_file_limit = '10GB'
~~~

Các giá trị chỉ minh họa.

### work_mem không phải giới hạn memory cho mỗi connection

Một query có thể có nhiều sort/hash nodes, nhiều parallel workers và nhiều sessions đồng thời. Tổng memory thực tế có thể là bội số của work_mem.

Tăng work_mem có thể giảm temporary I/O nhưng gây memory exhaustion nếu concurrency cao.

### Dấu hiệu spill

- EXPLAIN ANALYZE cho biết sort method có thể là external merge và dùng disk.
- Hash node có batches lớn hơn một, cho biết có thể spill.
- pg_stat_database.temp_files và temp_bytes tăng.
- Logs ghi temporary file nếu log_temp_files được bật.

### temp_file_limit

Giới hạn tổng dung lượng temporary files mà một process có thể dùng theo semantics của PostgreSQL. Khi vượt giới hạn, query có thể bị hủy. Đây là biện pháp bảo vệ disk, không thay thế tuning query/memory.

### log_temp_files

Ví dụ:

~~~conf
log_temp_files = '64MB'
~~~

Ghi log các temporary files có kích thước đạt ngưỡng. Đặt threshold phù hợp để phát hiện query spill lớn mà không tạo quá nhiều log.

## 19. maintenance_work_mem và vacuum

maintenance_work_mem là memory dành cho các maintenance operations như VACUUM và CREATE INDEX trong những giới hạn của operation/version.

Ví dụ:

~~~conf
maintenance_work_mem = '1GB'
autovacuum_work_mem = '256MB'
~~~

Giá trị thực tế cần tính số maintenance workers chạy đồng thời. Autovacuum có thể chạy nhiều worker; memory tổng cộng có thể lớn hơn giá trị tưởng tượng nếu nhân theo concurrency.

Tăng maintenance_work_mem có thể giúp một số operations hoàn thành nhanh hơn và giảm temp I/O, nhưng không thay thế storage bandwidth hoặc vacuum strategy.

## 20. Autovacuum tạo I/O như thế nào?

Autovacuum đọc heap/index pages để tìm dead tuples, cập nhật visibility/free space metadata và có thể ghi các page thay đổi. Nó cạnh tranh I/O với workload ứng dụng.

Các setting liên quan:

~~~conf
autovacuum = on
autovacuum_max_workers = 3
autovacuum_vacuum_cost_limit = 200
autovacuum_vacuum_cost_delay = '2ms'
~~~

Các giá trị là ví dụ; PostgreSQL có thể áp dụng cost limit theo worker và cơ chế chia sẻ theo version.

### vacuum_cost_limit và vacuum_cost_delay

Vacuum cost model ước lượng chi phí page access. Khi đạt cost limit, vacuum có thể ngủ theo cost delay để giảm áp lực I/O.

- Cost limit cao hơn có thể giúp vacuum chạy nhanh hơn nhưng tạo I/O mạnh hơn.
- Cost delay cao hơn làm vacuum chậm lại, giảm pressure nhưng có thể khiến dead tuples tồn tại lâu hơn.
- Tắt throttling hoặc tăng worker count không tự động cải thiện toàn hệ thống.

### Khi autovacuum không theo kịp

Dead tuples tích tụ, table/index bloat tăng và query có thể phải đọc nhiều page hơn. I/O tăng không chỉ do autovacuum; thiếu vacuum còn làm workload đọc/ghi kém hiệu quả.

Cần xem vacuum frequency, dead tuples, table churn và transaction age.

## 21. Checkpoint, background writer và vacuum phối hợp

Ba cơ chế có mục tiêu khác nhau:

| Cơ chế | Mục tiêu | I/O chính |
| --- | --- | --- |
| Background writer | Chuẩn bị clean buffers để backend ít phải tự ghi | Ghi dirty data pages |
| Checkpointer | Hoàn tất checkpoint và flush dirty pages cần thiết | Ghi/sync data files |
| Autovacuum | Dọn dead tuples, cập nhật visibility/free space | Đọc/ghi heap và index |

Tăng một tham số có thể chuyển I/O từ thời điểm này sang thời điểm khác, không nhất thiết giảm tổng lượng I/O.

Ví dụ, background writer ghi sớm nhiều hơn có thể làm giảm write bursts ở backend, nhưng vẫn phải ghi cùng các pages đó xuống storage.

## 22. Tablespace và phân bố I/O

Tablespaces có thể giúp đặt các nhóm relation trên các storage devices khác nhau:

- Tablespace cho hot OLTP tables.
- Tablespace cho indexes.
- Tablespace cho large historical partitions.
- Tablespace cho temporary objects.

Tuy nhiên, phân tách vật lý chỉ có tác dụng khi các đường I/O thực sự độc lập đủ mức. Hai mount points trên cùng volume không tạo thêm IOPS.

### temp_tablespaces

Có thể cấu hình:

~~~conf
temp_tablespaces = 'temp_fast'
~~~

Hoặc đặt theo session/role nếu cần. Temporary files cho sort/hash có thể dùng các tablespaces được chỉ định. Kiểm tra behavior cụ thể của version và đảm bảo quyền/đường dẫn tablespace đúng.

### Rủi ro vận hành

- Một tablespace hết dung lượng có thể làm query/DDL thất bại.
- Backup/restore cần xử lý mọi tablespace location.
- Di chuyển tablespace cần quy trình shutdown/online move phù hợp.
- Storage failure ở một tablespace có thể làm database mất khả năng truy cập các relation đặt ở đó.

Không phân tán relation chỉ để làm sơ đồ storage đẹp hơn; cần có số liệu chứng minh bottleneck và kế hoạch backup/recovery.

## 23. Index và I/O cost

Index giúp giảm số page phải đọc khi predicate có tính chọn lọc tốt. Nhưng index cũng tạo write amplification:

- INSERT phải cập nhật index.
- UPDATE có thể cập nhật nhiều index.
- DELETE để lại dead index tuples cần vacuum.
- Index lớn chiếm cache và storage.
- Index scan có thể gây random heap reads.

Một index không được dùng vẫn tiêu tốn storage, cache và write I/O.

### Kiểm tra index usage

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan;
~~~

Statistics có thể reset và một index có thể được dùng hiếm theo workload mùa vụ. Không drop index chỉ dựa trên một lần quan sát ngắn.

### Index-only scan

Index-only scan có thể giảm heap I/O nếu query lấy được các cột từ index và visibility map cho phép tránh heap fetch. Vacuum giúp visibility map được cập nhật phù hợp.

Index-only scan không có nghĩa luôn đọc zero heap pages; xem EXPLAIN để kiểm tra Heap Fetches.

## 24. Sequential scan và bitmap heap scan

### Sequential scan

Đọc phần lớn hoặc toàn bộ table pages. Có thể là lựa chọn tốt khi predicate trả về tỷ lệ rows lớn hoặc table nhỏ.

### Index scan

Dùng index tìm row locations rồi truy cập heap. Tốt khi selectivity cao và số heap pages cần đọc nhỏ.

### Bitmap heap scan

Dùng bitmap để gom các tuple/page cần đọc, có thể cải thiện locality so với nhiều heap fetch ngẫu nhiên.

Không ép planner dùng index bằng cách đặt random_page_cost cực thấp. Hãy kiểm tra cardinality estimates, statistics và actual plan.

## 25. Đọc EXPLAIN BUFFERS

Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

Các thông tin quan trọng:

- Shared hit: page đã có trong PostgreSQL shared buffers.
- Shared read: page được đọc vào shared buffers.
- Shared dirtied: page bị đánh dấu dirty.
- Shared written: page được ghi trong quá trình query.
- Local/temp buffers: hoạt động trên local hoặc temporary buffers.
- I/O Timings: thời gian read/write nếu track_io_timing bật.
- WAL: số WAL records/bytes/fpi theo khả năng version.

### Cẩn trọng khi đọc

- Shared read không chứng minh physical disk read; page có thể đến từ OS page cache.
- Buffer counts thường là số block, không phải số byte.
- Các dòng plan cha/con có thể báo cáo buffer counts mang tính cộng dồn; không cộng mọi dòng một cách máy móc.
- EXPLAIN ANALYZE thực sự chạy statement.
- DML có thể thay đổi dữ liệu; dùng transaction rollback hoặc staging khi thử nghiệm.
- Một query đơn lẻ không đại diện cho workload concurrency.

## 26. track_io_timing

~~~conf
track_io_timing = on
~~~

Khi bật, PostgreSQL thu thập thời gian I/O trong các statistics và EXPLAIN nơi được hỗ trợ. Việc đo thời gian có thể tạo overhead nhỏ tùy platform và clock implementation.

Dùng để xác định query đang tiêu tốn thời gian đọc/ghi, nhưng phải đối chiếu với OS metrics và workload. Timing tích lũy trong statistics views cần được lấy delta theo thời gian.

## 27. pg_stat_io

Từ PostgreSQL 16, view pg_stat_io cung cấp thống kê I/O theo backend type, object và context.

~~~sql
SELECT *
FROM pg_stat_io
ORDER BY backend_type, object, context;
~~~

Các nhóm field tùy version có thể gồm:

- reads và read_time.
- writes và write_time.
- writebacks và writeback_time.
- extends và extend_time.
- hits.
- evictions.
- reuses.
- fsyncs và fsync_time.
- backend_type, object và context.

View này giúp phân tích backend nào tạo I/O và loại hoạt động nào chiếm nhiều chi phí. Không giả định mỗi counter là physical device operation một-một; PostgreSQL có buffer cache và OS cache ở giữa.

### Lấy delta

Counters là tích lũy từ lần reset. Lấy snapshot tại t1 và t2 rồi tính delta để biết hoạt động trong khoảng thời gian. Ghi nhận stats_reset và server restart để tránh tính sai.

## 28. pg_stat_database và pg_statio

### pg_stat_database

~~~sql
SELECT
    datname,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    blk_read_time,
    blk_write_time
FROM pg_stat_database
ORDER BY blks_read DESC;
~~~

Các cột timing có ý nghĩa khi track_io_timing được bật. blks_read là block được PostgreSQL đọc vào shared buffers; không nhất thiết là physical disk read.

### Cache hit ratio

Có thể tính tỷ lệ hit trong shared buffers:

\[
Hit\ ratio = \frac{blks\_hit}{blks\_hit + blks\_read}
\]

Chỉ số này không mô tả đầy đủ physical cache behavior và không nên dùng làm SLO duy nhất. Một workload sequential scan có hit ratio thấp vẫn có thể hoạt động tốt nếu storage throughput cao và query latency phù hợp.

### pg_statio_user_tables

~~~sql
SELECT
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit
FROM pg_statio_user_tables
ORDER BY heap_blks_read DESC;
~~~

Dùng để xem relation nào có nhiều block reads/hits trong thống kê PostgreSQL. Counters có thể reset; đối chiếu với thời gian và workload.

## 29. pg_stat_wal và checkpoint statistics

### WAL

~~~sql
SELECT *
FROM pg_stat_wal;
~~~

View cung cấp các counters như WAL records, full-page images, bytes, writes, syncs và timing theo version/configuration.

### Checkpoint

PostgreSQL 17 trở lên có checkpoint statistics trong pg_stat_checkpointer:

~~~sql
SELECT *
FROM pg_stat_checkpointer;
~~~

PostgreSQL 16 trở xuống dùng pg_stat_bgwriter cho checkpoint counters:

~~~sql
SELECT *
FROM pg_stat_bgwriter;
~~~

Không dùng query cột của một major version cho version khác mà không kiểm tra schema view.

### Kết hợp

Nếu query latency tăng cùng thời điểm checkpoint write/sync time tăng, storage có thể đang chịu write pressure. Nếu WAL bytes tăng mạnh nhưng checkpoint bình thường, kiểm tra workload, full-page images, logical decoding và archiving/replication slots.

## 30. Theo dõi temporary I/O

Temporary files thường xuất hiện khi sort/hash hoặc một số operations vượt memory budget.

Query theo database:

~~~sql
SELECT
    datname,
    temp_files,
    temp_bytes
FROM pg_stat_database
ORDER BY temp_bytes DESC;
~~~

Tìm query tạo temp I/O bằng pg_stat_statements nếu extension được cài và quyền cho phép:

~~~sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    shared_blks_read,
    shared_blks_hit,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

Tên/cột có thể thay đổi theo extension version. pg_stat_statements không tự được bật chỉ vì PostgreSQL chạy; cần cài extension và cấu hình shared_preload_libraries theo tài liệu.

Giải pháp có thể là:

- Tối ưu query để giảm sort/hash input.
- Tạo index phù hợp.
- Điều chỉnh work_mem thận trọng.
- Giảm concurrency gây memory pressure.
- Dùng temp storage có hiệu năng phù hợp.
- Đặt temp_file_limit để bảo vệ dung lượng.

## 31. WAL và fsync latency

Với workload ghi nhiều transaction nhỏ, commit latency có thể bị chi phối bởi WAL flush/fsync hơn là data page writes.

Theo dõi:

- WAL writes/syncs.
- WAL write/sync time.
- Commit latency.
- synchronous_commit.
- Storage fsync latency.
- Group commit behavior.
- Synchronous standby latency nếu dùng replication đồng bộ.

Group commit cho phép nhiều transaction chia sẻ một WAL flush trong một số tình huống. Không phải mỗi COMMIT luôn tương ứng một physical fsync riêng.

### wal_sync_method

Các lựa chọn phụ thuộc OS. Chọn phương thức phù hợp với filesystem/storage và cách OS implement flush. Không thay đổi setting này nếu chưa benchmark và kiểm tra durability semantics.

### synchronous_commit

Đặt synchronous_commit=off có thể giảm commit latency trong một số workload, nhưng có thể mất các transaction vừa được xác nhận nếu server crash. Database vẫn duy trì consistency theo WAL, nhưng transaction durability window thay đổi.

Chỉ áp dụng cho workload chấp nhận rủi ro này và có business approval. Không dùng làm cách chữa storage lỗi.

## 32. Read/write separation và storage tiering

Một số hệ thống có thể đặt workload hoặc dữ liệu theo tier:

- Hot data trên NVMe.
- Warm data trên SSD.
- Historical/archive data trên storage dung lượng lớn.
- Backup/WAL archive trên object storage.

PostgreSQL không tự động phân loại dữ liệu theo nhiệt độ. Cần dùng partitioning, tablespaces, archival policy hoặc application architecture.

### Partitioning

Partitioning có thể giúp tách dữ liệu theo thời gian/tenant và hỗ trợ drop/detach partition cũ thay vì xóa hàng triệu rows. Tuy nhiên, partitioning không tự giảm I/O nếu query không prune partition hoặc vẫn đọc phần lớn dữ liệu.

### Storage tiering không thay retention design

Dữ liệu archive vẫn cần được backup, kiểm tra integrity và phục hồi theo yêu cầu. Chuyển relation sang storage chậm hơn có thể làm query lịch sử chậm hơn; cần thông báo cho ứng dụng và đặt query routing phù hợp.

## 33. Đo storage từ hệ điều hành

PostgreSQL views cho biết hoạt động nội bộ. OS/storage metrics xác nhận thiết bị thật sự đang làm gì.

Linux tools thường dùng:

~~~bash
iostat -xz 1
vmstat 1
sar -d 1
lsblk
df -h
~~~

Các trường cần quan tâm tùy tool:

- Read/write IOPS.
- Read/write throughput.
- Average request size.
- Await/latency.
- Queue depth.
- Utilization.
- I/O wait.
- Device errors.
- Filesystem free space.

Không diễn giải %util của một thiết bị hiện đại như thước đo duy nhất của saturation; thiết bị NVMe có thể xử lý nhiều queue và utilization semantics khác HDD. Đọc metrics theo tool/kernel version.

Trên Windows/cloud, dùng công cụ Performance Monitor, storage telemetry hoặc provider metrics tương ứng.

## 34. Benchmark storage

Benchmark cần tách hai câu hỏi:

1. Thiết bị có khả năng IOPS/throughput/latency nào?
2. PostgreSQL workload thực tế đạt được hiệu năng nào trên thiết bị đó?

### fio

fio có thể mô phỏng random/sequential reads/writes, block sizes và queue depth. Ví dụ dưới đây chỉ dành cho một file test riêng trên môi trường thử nghiệm:

~~~bash
fio --name=randread \
    --filename=/mnt/test-volume/fio-test.bin \
    --size=4G \
    --rw=randread \
    --bs=8k \
    --iodepth=16 \
    --numjobs=4 \
    --direct=1 \
    --runtime=60 \
    --time_based \
    --group_reporting
~~~

Lệnh có thể ghi/đọc file test và tạo tải I/O mạnh. Không chạy trên data directory đang sử dụng hoặc production volume nếu chưa có change plan. direct=1 bypass một phần page cache trên các platform hỗ trợ; behavior phụ thuộc OS/filesystem.

### pgbench

pgbench tạo workload PostgreSQL và đo transaction throughput/latency. Dùng schema, scale, client count và workload gần production để benchmark end-to-end.

~~~bash
pgbench -i -s 50 testdb
pgbench -c 32 -j 8 -T 300 -P 10 testdb
~~~

Đây là ví dụ workload. Khởi tạo pgbench có thể xóa/tạo các bảng pgbench trong database đích; dùng database benchmark riêng. Thử nhiều client counts và đo p95/p99 latency, TPS, WAL, I/O và CPU.

### Benchmark có kiểm soát

- Chạy cùng workload và data size.
- Warm/cold cache state được ghi rõ.
- Không benchmark khi backup/vacuum khác đang làm lệch kết quả.
- Lặp nhiều lần.
- Ghi cả throughput lẫn tail latency.
- Theo dõi CPU, memory, I/O và network.
- Đánh giá durability settings như production.
- Giữ baseline để so sánh sau thay đổi.

## 35. Quy trình tối ưu I/O

Một quy trình hợp lý:

1. Xác định triệu chứng: query latency, commit latency, throughput hay storage saturation.
2. Chọn cửa sổ thời gian đại diện.
3. Lấy PostgreSQL statistics và OS/storage metrics.
4. Xác định read, write, WAL, temp hay vacuum là nguồn chính.
5. Dùng EXPLAIN để xác định query plan và buffer usage.
6. Kiểm tra cache/memory pressure.
7. Kiểm tra storage limits và queueing.
8. Thay đổi một nhóm nhỏ setting.
9. Benchmark lại cùng workload.
10. So sánh p95/p99 latency, throughput, I/O, WAL và error rate.
11. Giữ hoặc rollback theo tiêu chí đã định.

Không thay nhiều tham số cùng lúc vì sẽ khó xác định nguyên nhân cải thiện hoặc suy giảm.

## 36. Ví dụ điều tra: query chậm do random reads

**Triệu chứng:** một API query theo customer_id chậm khi dữ liệu lớn.

Điều tra:

- Dùng EXPLAIN (ANALYZE, BUFFERS) xem Index Scan hay Bitmap Heap Scan.
- Kiểm tra shared read và I/O timing.
- Xem correlation của index/table và selectivity.
- Kiểm tra cache hit và memory pressure.
- Đo storage read latency và IOPS.
- Kiểm tra index có đủ cột hay không.

Hướng xử lý có thể gồm:

- Tạo/điều chỉnh index nếu query pattern phù hợp.
- Cập nhật statistics.
- Cải thiện query selectivity.
- Tăng cache hợp lý nếu memory còn.
- Dùng storage random-read latency thấp hơn.
- Điều chỉnh planner costs sau benchmark.

Không hạ random_page_cost chỉ để ép Index Scan. Nếu query đọc nhiều heap pages phân tán, sequential scan hoặc bitmap scan có thể nhanh hơn.

## 37. Ví dụ điều tra: WAL flush làm COMMIT chậm

**Triệu chứng:** query DML chạy nhanh nhưng COMMIT có latency cao.

Kiểm tra:

- pg_stat_wal writes/syncs và timing.
- OS fsync/write latency.
- WAL volume và full-page images.
- Synchronous replication status/standby latency.
- synchronous_commit của session/role/database.
- Storage power-loss protection và write cache policy.

Giải pháp có thể:

- Chuyển sang storage có flush latency thấp hơn.
- Giảm WAL volume bằng schema/index/workload tuning.
- Điều chỉnh group commit/concurrency theo benchmark.
- Rà soát synchronous standby network latency.
- Chỉ dùng synchronous_commit=off cho transaction chấp nhận durability window đã được phê duyệt.

Không giảm durability để che một storage device có hành vi flush không đáng tin cậy.

## 38. Ví dụ điều tra: temporary files tăng

**Triệu chứng:** temp_bytes tăng nhanh và filesystem gần đầy.

Kiểm tra:

- pg_stat_database.temp_files/temp_bytes.
- pg_stat_statements temp_blks_written.
- EXPLAIN sort/hash nodes.
- work_mem và concurrency.
- Query join/sort cardinality.
- Temp tablespace capacity và I/O latency.

Giải pháp:

- Tối ưu query và giảm rows trước sort.
- Tạo index hỗ trợ ORDER BY/JOIN khi phù hợp.
- Tăng work_mem theo role/query có kiểm soát.
- Giảm concurrency hoặc giới hạn batch.
- Dùng temp tablespace đủ dung lượng.
- Đặt temp_file_limit và alert.

Không tăng work_mem toàn cục chỉ dựa vào một query spill.

## 39. Ví dụ điều tra: checkpoint tạo I/O burst

**Triệu chứng:** latency tăng theo chu kỳ và storage write throughput có burst.

Kiểm tra:

- log_checkpoints và lý do checkpoint.
- pg_stat_checkpointer (PostgreSQL 17+) hoặc pg_stat_bgwriter (PostgreSQL 16 trở xuống).
- WAL bytes/second.
- max_wal_size và checkpoint_timeout.
- checkpoint_completion_target.
- Background writer statistics.
- Storage write latency/queue depth.
- Replication slots và WAL archive retention.

Giải pháp:

- Tăng max_wal_size nếu requested checkpoints quá thường xuyên và disk đủ.
- Điều chỉnh checkpoint_completion_target để trải đều write workload.
- Kiểm tra background writer behavior.
- Cải thiện storage throughput/latency.
- Giảm WAL generation nếu có index/updates không cần thiết.
- Theo dõi crash recovery time sau khi thay đổi.

## 40. Ví dụ điều tra: autovacuum cạnh tranh I/O

**Triệu chứng:** latency tăng khi autovacuum chạy trên bảng lớn.

Kiểm tra:

- Autovacuum logs.
- pg_stat_progress_vacuum.
- pg_stat_user_tables n_dead_tup và last_autovacuum.
- I/O metrics theo backend type/context trong pg_stat_io nếu hỗ trợ.
- Vacuum cost delay/limit.
- Table churn và index bloat.

Giải pháp:

- Điều chỉnh scale factor/threshold theo kích thước bảng.
- Tăng maintenance capacity nếu storage còn dư.
- Giảm vacuum cost rate nếu ứng dụng cần ưu tiên latency.
- Tăng vacuum frequency để tránh các đợt vacuum quá lớn.
- Xem xét partitioning và index bloat.

Không tắt autovacuum để loại bỏ I/O ngắn hạn; dead tuples có thể tích tụ và làm I/O về sau tệ hơn.

## 41. Các tham số I/O thường gặp

| Tham số | Nhóm | Tác động chính |
| --- | --- | --- |
| shared_buffers | Cache | PostgreSQL shared page cache |
| effective_cache_size | Planner | Ước lượng cache có sẵn, không cấp phát memory |
| seq_page_cost | Planner | Cost tương đối của sequential page read |
| random_page_cost | Planner | Cost tương đối của random page read |
| effective_io_concurrency | Read I/O | I/O concurrency cho một số read/prefetch operations |
| maintenance_io_concurrency | Maintenance | I/O concurrency cho một số maintenance operations |
| work_mem | Query memory | Memory cho sort/hash trước khi spill |
| hash_mem_multiplier | Query memory | Hệ số memory cho hash operations |
| temp_file_limit | Temporary I/O | Giới hạn temp files theo process |
| temp_tablespaces | Temporary I/O | Tablespaces cho temporary objects |
| maintenance_work_mem | Maintenance memory | Memory cho vacuum/index maintenance |
| autovacuum_work_mem | Maintenance memory | Memory cho autovacuum workers |
| wal_buffers | WAL | Shared memory cho WAL records |
| wal_compression | WAL | Nén full-page images trong WAL |
| wal_sync_method | WAL durability | Phương thức đồng bộ WAL theo platform |
| synchronous_commit | Commit durability | Thời điểm COMMIT chờ WAL flush/apply |
| fsync | Durability | Yêu cầu flush dữ liệu bền vững |
| full_page_writes | Durability/WAL | Full-page images bảo vệ torn pages |
| checkpoint_timeout | Checkpoint | Khoảng thời gian tối đa giữa timed checkpoints |
| max_wal_size | Checkpoint/WAL | Ngưỡng mềm cho checkpoint do WAL growth |
| min_wal_size | Checkpoint/WAL | WAL tối thiểu được giữ để reuse |
| checkpoint_completion_target | Checkpoint | Trải đều checkpoint writes |
| bgwriter_delay | Background writer | Khoảng giữa các vòng background writer |
| bgwriter_lru_maxpages | Background writer | Số page tối đa ghi mỗi vòng |
| bgwriter_lru_multiplier | Background writer | Điều chỉnh nhu cầu page cleaning |
| vacuum_cost_delay | Vacuum | Thời gian nghỉ theo vacuum cost |
| vacuum_cost_limit | Vacuum | Cost budget trước khi nghỉ |
| track_io_timing | Monitoring | Thu thập timing I/O |
| track_wal_io_timing | Monitoring | Thu thập WAL I/O timing |
| log_temp_files | Logging | Ghi log temporary files theo ngưỡng |
| log_checkpoints | Logging | Ghi checkpoint events |

Tham số và context có thể khác theo major version. Kiểm tra pg_settings và tài liệu server đang dùng trước khi thay đổi.

## 42. Cách thay đổi tham số an toàn

Trước khi thay đổi:

1. Ghi lại giá trị hiện tại và source.
2. Kiểm tra context: postmaster, sighup, superuser-backend, user hoặc internal.
3. Kiểm tra pending_restart.
4. Xác định tác động lên memory, disk và durability.
5. Chọn workload benchmark.
6. Xác định tiêu chí thành công và rollback.
7. Thay một nhóm setting nhỏ.
8. Reload hoặc restart đúng yêu cầu.
9. Xác minh giá trị hiệu lực.
10. So sánh số liệu trước/sau.

Kiểm tra:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'effective_cache_size',
    'random_page_cost',
    'seq_page_cost',
    'effective_io_concurrency',
    'work_mem',
    'maintenance_work_mem',
    'wal_buffers',
    'checkpoint_timeout',
    'max_wal_size',
    'checkpoint_completion_target',
    'track_io_timing'
)
ORDER BY name;
~~~

Một số tham số cần restart, một số hỗ trợ reload và một số có thể set theo session/role. Không giả định một lệnh pg_reload_conf() áp dụng mọi thay đổi.

## 43. Những sai lầm thường gặp

1. **Chọn storage chỉ theo dung lượng hoặc IOPS quảng cáo**, bỏ qua latency, throughput, queue depth và giới hạn instance.
2. **Coi random I/O và sequential I/O giống nhau**, chọn thiết bị không phù hợp workload.
3. **Cho rằng shared read trong PostgreSQL là physical disk read**, bỏ qua OS page cache.
4. **Tăng shared_buffers mà không tính memory tổng**, làm hệ điều hành và backend khác thiếu RAM.
5. **Coi effective_cache_size là memory allocation**, dẫn tới tính toán memory sai.
6. **Giảm random_page_cost quá thấp**, khiến planner chọn index plan gây nhiều random heap reads.
7. **Tăng effective_io_concurrency mà không benchmark**, tạo queueing và storage contention.
8. **Tăng work_mem toàn cục**, gây memory exhaustion khi nhiều query/worker chạy đồng thời.
9. **Tăng maintenance_work_mem mà quên số autovacuum workers**, tạo áp lực memory.
10. **Dùng temp_file_limit như cách sửa query spill**, trong khi nó chỉ giới hạn dung lượng temp.
11. **Tắt fsync hoặc full_page_writes để đạt benchmark nhanh**, làm suy giảm durability.
12. **Nhầm synchronous_commit với synchronous replication**, đánh giá sai commit guarantees.
13. **Tách WAL/data thành hai mount trên cùng storage pool rồi kỳ vọng I/O độc lập**, không giải quyết contention.
14. **Tăng max_wal_size mà không tính disk và replication slots**, làm filesystem có thể đầy.
15. **Tăng background writer quá mức**, đẩy thêm write I/O vào storage vốn đã bão hòa.
16. **Tắt autovacuum vì nó tạo I/O**, khiến bloat và I/O dài hạn tăng.
17. **Chỉ xem cache hit ratio**, bỏ qua tail latency và OS/device metrics.
18. **Đọc counters tích lũy như số liệu tức thời**, không tính delta và stats_reset.
19. **Dùng query thống kê của PostgreSQL 16 trên PostgreSQL 17+**, bỏ qua thay đổi pg_stat_checkpointer.
20. **Cộng buffer counts ở mọi node EXPLAIN**, có thể đếm trùng số liệu tích lũy.
21. **Chạy fio trực tiếp trên data directory production**, có nguy cơ làm hỏng dữ liệu hoặc gây gián đoạn.
22. **Benchmark chỉ bằng một query**, không đại diện concurrency và workload mix.
23. **Tối ưu throughput nhưng bỏ qua p95/p99 latency**, làm trải nghiệm người dùng xấu đi.
24. **Không kiểm tra cloud volume burst/throttling**, chỉ thấy hiệu năng tốt lúc đầu.
25. **Không đưa tablespaces vào backup/recovery plan**, khiến restore thiếu relation files.
26. **Không theo dõi temporary files và WAL retention**, để disk đầy bất ngờ.
27. **Thay nhiều tham số cùng lúc**, không xác định được nguyên nhân kết quả.
28. **Không lưu baseline và rollback plan**, khó phục hồi cấu hình ổn định.

## 44. Bài tập thực hành có đáp án

### Bài 1. Latency là gì?

**Đáp án:** Thời gian hoàn thành một yêu cầu I/O từ lúc gửi tới lúc nhận kết quả.

### Bài 2. IOPS là gì?

**Đáp án:** Số thao tác I/O mỗi giây.

### Bài 3. Throughput là gì?

**Đáp án:** Lượng dữ liệu truyền mỗi giây, thường đo bằng MB/s hoặc GB/s.

### Bài 4. Queue depth quá cao có thể gây gì?

**Đáp án:** Tăng thời gian chờ và tail latency dù thiết bị có thể xử lý nhiều I/O song song.

### Bài 5. OLTP random lookup cần đặc tính storage nào?

**Đáp án:** Latency thấp và random IOPS tốt, cùng khả năng duy trì hiệu năng ổn định.

### Bài 6. Sequential scan thường nhạy với yếu tố nào?

**Đáp án:** Throughput đọc tuần tự và khả năng xử lý nhiều I/O liên tục.

### Bài 7. shared_buffers là gì?

**Đáp án:** Shared memory cache data pages do PostgreSQL quản lý.

### Bài 8. effective_cache_size có cấp phát memory không?

**Đáp án:** Không. Đây là ước lượng cache cho planner.

### Bài 9. random_page_cost dùng để làm gì?

**Đáp án:** Cost tương đối của random page reads trong mô hình planner.

### Bài 10. seq_page_cost dùng để làm gì?

**Đáp án:** Cost tương đối của sequential page reads.

### Bài 11. effective_io_concurrency tác động tới đâu?

**Đáp án:** Một số operations có thể tận dụng I/O concurrency/prefetching, đặc biệt bitmap heap scans.

### Bài 12. work_mem là memory cho mỗi connection hay mỗi operation?

**Đáp án:** Chủ yếu là memory budget cho mỗi sort/hash operation; một query có thể có nhiều operation và parallel workers.

### Bài 13. Khi nào query tạo temporary files?

**Đáp án:** Khi một số operations như sort/hash vượt memory budget hoặc cần temporary storage.

### Bài 14. temp_file_limit làm gì?

**Đáp án:** Giới hạn tổng dung lượng temporary files mà một process có thể sử dụng theo PostgreSQL semantics.

### Bài 15. WAL phải được ghi trước data pages vì sao?

**Đáp án:** Write-ahead logging bảo đảm PostgreSQL có thể redo thay đổi sau crash.

### Bài 16. fsync=off có rủi ro gì?

**Đáp án:** Có thể mất dữ liệu hoặc corruption sau crash/power loss.

### Bài 17. full_page_writes bảo vệ điều gì?

**Đáp án:** Giúp phục hồi khỏi torn pages bằng full-page images trong WAL khi cần.

### Bài 18. synchronous_commit có thay đổi data page flush không?

**Đáp án:** Nó điều khiển commit acknowledgement so với WAL flush/apply; không có nghĩa heap data pages đã được ghi ngay.

### Bài 19. max_wal_size có phải hard cap?

**Đáp án:** Không. Đây là ngưỡng mềm; WAL có thể vượt do workload, slots và archiving.

### Bài 20. log_checkpoints giúp điều tra điều gì?

**Đáp án:** Lý do, thời gian và lượng buffers của checkpoint/restartpoint.

### Bài 21. pg_stat_io được giới thiệu từ PostgreSQL nào?

**Đáp án:** PostgreSQL 16.

### Bài 22. PostgreSQL 17 xem checkpoint statistics ở view nào?

**Đáp án:** pg_stat_checkpointer.

### Bài 23. PostgreSQL 16 trở xuống xem checkpoint counters ở đâu?

**Đáp án:** pg_stat_bgwriter.

### Bài 24. EXPLAIN BUFFERS shared read có đồng nghĩa physical disk read không?

**Đáp án:** Không. Page có thể được OS page cache phục vụ.

### Bài 25. Vì sao không tăng work_mem toàn cục để chữa temp I/O?

**Đáp án:** Nhiều operation, session và parallel workers có thể dùng memory đồng thời, gây memory exhaustion.

### Bài 26. Vì sao không nên tắt autovacuum để giảm I/O?

**Đáp án:** Dead tuples và bloat tích tụ, làm I/O và hiệu năng dài hạn tệ hơn.

### Bài 27. Khi nào tách WAL và data có ích?

**Đáp án:** Khi hai workload gây contention và storage path riêng thực sự độc lập, có durability phù hợp.

### Bài 28. Công cụ OS nào thường dùng trên Linux để xem disk I/O?

**Đáp án:** iostat, vmstat, sar và các công cụ storage telemetry tương ứng.

### Bài 29. fio có nên chạy trực tiếp trên PostgreSQL production data directory không?

**Đáp án:** Không. Chỉ chạy trên file/device test riêng trong môi trường được kiểm soát.

### Bài 30. Quy trình tuning I/O nên bắt đầu bằng gì?

**Đáp án:** Đo workload và xác định bottleneck bằng PostgreSQL statistics, EXPLAIN và OS/storage metrics trước khi đổi tham số.

## 45. Checklist tối ưu I/O

- [ ] Xác định workload OLTP, analytics, batch hay mixed.
- [ ] Đo latency p50/p95/p99.
- [ ] Đo IOPS, throughput và queue depth.
- [ ] Kiểm tra giới hạn volume, instance và network storage.
- [ ] Phân biệt random và sequential access.
- [ ] Xác định data, WAL, temp và archive I/O.
- [ ] Kiểm tra shared_buffers và memory pressure.
- [ ] Ước lượng effective_cache_size thực tế.
- [ ] Kiểm tra planner cost và EXPLAIN plans.
- [ ] Chỉ đổi random_page_cost sau benchmark.
- [ ] Đánh giá effective_io_concurrency trên storage thật.
- [ ] Kiểm soát work_mem theo concurrency.
- [ ] Theo dõi temp_files/temp_bytes.
- [ ] Đặt temp_file_limit và dung lượng temp tablespace.
- [ ] Bảo đảm fsync và full_page_writes theo durability policy.
- [ ] Theo dõi WAL bytes, write/sync latency.
- [ ] Đánh giá synchronous_commit và synchronous standby nếu có.
- [ ] Bật log_checkpoints.
- [ ] Theo dõi checkpoint statistics đúng version.
- [ ] Kiểm tra replication slots và WAL archive retention.
- [ ] Điều chỉnh background writer/vacuum dựa trên I/O metrics.
- [ ] Theo dõi pg_stat_io, pg_stat_database và pg_stat_wal.
- [ ] Dùng EXPLAIN (ANALYZE, BUFFERS, WAL) phù hợp.
- [ ] Đối chiếu PostgreSQL statistics với OS/storage metrics.
- [ ] Benchmark trên môi trường và workload đại diện.
- [ ] Không chạy destructive I/O tests trên production volume.
- [ ] Thay ít tham số mỗi lần và lưu baseline.
- [ ] Có rollback plan và kiểm tra durability sau tuning.

## 46. Tài liệu PostgreSQL chính thức

Đọc tài liệu theo major version đang triển khai:

- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html) — shared_buffers, work_mem, maintenance_work_mem, effective_cache_size và I/O concurrency.
- [Query Planning Configuration](https://www.postgresql.org/docs/current/runtime-config-query.html) — seq_page_cost, random_page_cost và planner cost settings.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — WAL buffers, fsync, full_page_writes và checkpoint settings.
- [Write Ahead Log](https://www.postgresql.org/docs/current/wal.html) — WAL architecture và durability.
- [Tablespaces](https://www.postgresql.org/docs/current/manage-ag-tablespaces.html) — phân bố relation trên storage locations.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_io, pg_stat_database, pg_statio, pg_stat_wal và checkpoint views.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — đọc query plans, buffers và execution statistics.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — vacuum/autovacuum và quản lý dead tuples.
- [Autovacuum Configuration](https://www.postgresql.org/docs/current/runtime-config-autovacuum.html) — worker, cost delay và vacuum thresholds.
- [pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) — thống kê query workload và temporary block usage.
- [pgbench](https://www.postgresql.org/docs/current/pgbench.html) — benchmark workload PostgreSQL.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — WAL archive và backup storage.

Các URL /current/ trỏ tới tài liệu PostgreSQL hiện hành. Tên/cột statistics views, I/O concurrency options và setting defaults có thể thay đổi theo major version; xác nhận tài liệu đúng phiên bản server và hệ điều hành trước khi triển khai.

## 47. Tổng kết

**Chi phí I/O phụ thuộc cả thiết bị lưu trữ lẫn cách PostgreSQL truy cập, cache, ghi WAL và flush data pages.** Tối ưu tốt cần đo từ query đến hệ điều hành và thiết bị, sau đó thay đổi cấu hình có kiểm soát.

1. **Latency, IOPS, throughput và queue depth là các chỉ số khác nhau.** Workload OLTP và analytics có nhu cầu I/O khác nhau.
2. **Random I/O và sequential I/O cần được đánh giá riêng.** SSD/NVMe cải thiện random access nhưng không loại bỏ mọi storage bottleneck.
3. **shared_buffers và OS page cache cùng tham gia read path.** shared read không đồng nghĩa physical disk read.
4. **effective_cache_size chỉ là planner estimate.** Nó không cấp phát memory.
5. **random_page_cost và seq_page_cost là planner cost units.** Điều chỉnh chúng sau khi xem plan và benchmark.
6. **work_mem có thể nhân theo operation, session và worker.** Tăng quá mức có thể gây memory pressure.
7. **WAL flush và data page writes là hai hoạt động khác nhau.** fsync/full_page_writes phải theo durability policy.
8. **Checkpoint, background writer và vacuum cùng tạo write I/O.** Cần điều chỉnh theo workload và storage capacity.
9. **Temporary files và replication/WAL retention có thể làm đầy disk.** Theo dõi temp bytes, slots và archiver.
10. **pg_stat_io, pg_stat_wal, pg_stat_database và EXPLAIN BUFFERS bổ sung cho OS metrics.**
11. **Benchmark phải đại diện workload và ghi nhận tail latency.** Không dùng một con số IOPS để kết luận database sẽ nhanh.
12. **Không chạy destructive benchmark trên production data.** Lưu baseline, thay từng nhóm nhỏ và có rollback.
13. **Không đánh đổi durability để lấy hiệu năng benchmark.** Tính đúng đắn và khả năng phục hồi là yêu cầu nền tảng.

Một chiến lược I/O hiệu quả bắt đầu bằng việc xác định chính xác query hoặc background process nào tạo tải, storage path nào bị giới hạn và tham số PostgreSQL nào thực sự liên quan. Khi đó, thiết bị, cache, WAL và checkpoint mới được tối ưu theo cùng một mục tiêu vận hành.

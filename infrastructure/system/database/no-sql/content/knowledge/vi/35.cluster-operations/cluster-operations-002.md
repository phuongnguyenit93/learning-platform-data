# Dung lượng, bộ nhớ, CPU, I/O và mạng cho tải mục tiêu

Khi một ứng dụng bắt đầu nhận nhiều người dùng, câu hỏi “cần bao nhiêu node NoSQL?” thường xuất hiện trước khi nhóm kỹ thuật biết workload thực sự tiêu thụ tài nguyên nào. Mua thêm RAM không giải quyết được một hot partition bị giới hạn throughput; tăng CPU không sửa được disk I/O bị bão hòa; mở rộng lưu trữ không tự khiến dữ liệu CDC được đồng bộ nhanh hơn. Một cluster đủ sức chạy trong điều kiện bình thường vẫn có thể ngừng phục vụ khi mất một node, một Availability Zone (AZ), hoặc khi compaction/repair trùng với giờ cao điểm.

**Capacity planning** là quá trình biến **mục tiêu tải và độ tin cậy** thành ngân sách dung lượng, bộ nhớ, CPU, I/O và mạng; sau đó xác nhận bằng đo đạc, load test và kế hoạch phục hồi. Trong chương **Vận hành cụm** của module **Database No SQL**, bài học này tập trung vào cách tính **tổng dung lượng và từng nút**, working set/cache/heap, sức xử lý CPU, IOPS/throughput/tail latency của ổ đĩa, network replication/egress, phân vùng, headroom khi lỗi và chi phí vận hành.

> **Nguyên tắc:** “Đủ dung lượng lưu dữ liệu” không có nghĩa “đủ năng lực phục vụ tải mục tiêu”. Một thiết kế chỉ đạt yêu cầu khi đồng thời thỏa **khối lượng lưu trữ**, **latency/throughput**, **mức dữ liệu mới**, **khả năng chịu lỗi** và **giới hạn chi phí** trong các kịch bản đã công bố.

## 1. Bài toán thực tế: tải mục tiêu phải được mô tả trước

Một nền tảng đặt chỗ có các nhóm thao tác:

~~~text
Mobile / Web
    |
    v
Booking API
    |
    +--> NoSQL booking/inventory store
    |       ├── point reads
    |       ├── conditional writes
    |       └── transactional records
    |
    +--> Redis/cache
    |
    +--> CDC/Outbox → Search/Analytics
~~~

Trước khi chọn số node, hãy thu thập:

1. Bao nhiêu reads/s, writes/s, scans/s tại **bình thường**, **đỉnh**, **burst**?
2. Latency p95/p99 và tỷ lệ lỗi chấp nhận được cho từng loại thao tác?
3. Kích thước bản ghi, chỉ mục, số bản cập nhật, read/write amplification?
4. Dữ liệu tăng bao nhiêu mỗi ngày; retention/TTL và backup policy?
5. Số lượng key/partition, hot key distribution, tỷ lệ truy cập dữ liệu nóng?
6. Replication factor, consistency/quorum, số vùng lỗi (node/rack/AZ/region)?
7. Có cần đáp ứng SLO khi mất node hoặc AZ không?
8. Các workload nền nào chạy đồng thời: backup, compaction, repair, CDC, export?
9. Có giới hạn cost, quota, thời gian provision hoặc điều kiện vendor nào?

**Không có số “requests/giây trên mỗi node” đúng cho mọi NoSQL.** Query shape, kích thước payload và phân phối khóa thường quan trọng không kém QPS.

## 2. Xác định SLO và failure scenarios

Ví dụ yêu cầu sản phẩm (chỉ minh họa):

| Đường nghiệp vụ | Mục tiêu trong peak | Mức độ |
| --- | --- | --- |
| Đọc listing bằng ID | p99 dưới 200 ms | Interactive |
| Đặt phòng có kiểm tồn kho | 99,9% request hợp lệ hoàn thành đúng trong 500 ms | Critical write |
| Search listing | p95 dưới 400 ms; dữ liệu mới trong 10 giây | Read model |
| Analytics batch | Hoàn thành trước 06:00 | Background |
| CDC projection | 99% events visible trong 10 giây | Freshness |

Chọn tải mục tiêu:

~~~text
T0: steady-state bình thường
T1: giờ cao điểm dự kiến
T2: burst 5–15 phút
T3: cao điểm + mất một node
T4: cao điểm + một AZ không khả dụng
T5: cao điểm + compaction/backup/rebuild
~~~

Không phải hệ nào cũng cam kết đầy đủ T4/T5; phải ghi rõ mục tiêu nào được bảo vệ và lúc nào chấp nhận giảm chất lượng. **Số node chỉ có ý nghĩa khi biết kịch bản mà nó cần chịu được.**

## 3. Từ user traffic sang database operations

Giả sử 1.000 API calls/s có thể tạo:

~~~text
GET listing:
  1 cache lookup
  cache miss → 1 DB read

Search:
  1 search query
  maybe 10 DB reads to hydrate results

Reserve:
  1 conditional write
  2 validation reads
  1 outbox event
~~~

Do đó:

\[
DBOpsPerSecond=\sum_i RequestRate_i\times OpsPerRequest_i
\]

Nếu 2.000 reserve requests/s, mỗi request sinh hai reads và một write, đường booking có thể cần khoảng **4.000 reads/s + 2.000 writes/s**, chưa tính retries hoặc cache effects.

### Phân biệt bốn tốc độ

- **Incoming request rate:** API requests/s.
- **Logical DB operations:** yêu cầu đọc/ghi do business logic sinh ra.
- **Physical storage operations:** disk I/O, replica writes, compaction, index updates.
- **Network operations:** round-trips, replication, cross-zone transfers.

Một logical write có thể tạo nhiều physical writes; một query có thể fan-out nhiều partitions và kéo hàng nghìn rows. Không dùng API QPS làm proxy duy nhất cho capacity.

## 4. Peak, average và burst không dùng thay nhau

Ví dụ:

~~~text
Average writes = 120 writes/s
Peak writes    = 1,200 writes/s
Peak reads     = 6,000 reads/s
Burst writes   = 2,500 writes/s for 5 minutes
~~~

- **Average writes** thường hữu ích khi ước lượng dữ liệu phát sinh trong thời gian dài.
- **Peak và burst** quan trọng khi sizing CPU, disk IOPS, connection concurrency và network.
- **Sustained peak duration** quan trọng vì queue, compaction debt và buffer có thể tích lũy.
- **Traffic growth forecast** cần đưa vào mọi phép tính dài hạn.

Một cluster có thể xử lý burst 30 giây bằng cache/queue nhưng không chịu được 30 phút vì backlog tích tụ. Load target phải kèm **thời lượng và hình dạng arrival process**.

## 5. Mô tả workload bằng một bảng thống nhất

| Thuộc tính | Reads | Writes | Scan/CDC |
| --- | --- | --- | --- |
| Bình thường | 1.800/s | 120/s | 20/s |
| Peak | 6.000/s | 1.200/s | 100/s |
| Burst | 10.000/s | 2.500/s | Chạy đồng thời hoặc không |
| Kích thước response | 2 KiB | ACK nhỏ | Có thể lớn |
| Working set | 400 GiB hot data | Nhiều keys | Historical partitions |
| SLA/latency | p99 200 ms | p99 500 ms | Backlog age SLO |
| Key distribution | Có hot keys | Có hot partitions | Sequential scans |

Đây là **hồ sơ tải giả định** để học phương pháp. Một workload thật cần số liệu từ application metrics, query logs, tracing, dữ liệu production và kế hoạch tăng trưởng.

## 6. Tổng quan năm ngân sách tài nguyên

~~~text
Target workload + growth + failure scenarios
                  |
                  v
          Data model/access patterns
                  |
                  v
    +-------------+-------------+
    |             |             |
  STORAGE       MEMORY         CPU
    |             |             |
  IOPS / disk throughput     NETWORK
    |             |             |
    +-------------+-------------+
                  |
                  v
       Node count + topology + headroom
                  |
                  v
         Benchmark / fault test
~~~

Năm ngân sách tương tác:

- RAM thiếu → cache miss tăng → IOPS/latency tăng.
- CPU thiếu → nén/serialization/compaction chậm → queue tăng.
- Disk I/O thiếu → compaction backlog → read amplification và storage usage tăng.
- Network thiếu → replication/repair chậm → replica lag hoặc write latency tăng.
- Storage gần đầy → compaction/recovery không còn khoảng trống, dù QPS thấp.

**Capacity planning là bài toán nhiều ràng buộc; tài nguyên cần nhất chưa chắc là tài nguyên dùng nhiều phần trăm nhất.**

## 7. Đơn vị: KB/MB và KiB/MiB/TiB

| Đơn vị | Số byte |
| --- | ---: |
| 1 KB | 1.000 |
| 1 KiB | 1.024 |
| 1 MB | 1.000.000 |
| 1 MiB | 1.048.576 |
| 1 GB | 1.000.000.000 |
| 1 GiB | 1.073.741.824 |
| 1 TiB | 1.099.511.627.776 |

Disk vendors, cloud APIs và monitoring exporters có thể dùng đơn vị khác nhau. Với storage calculations, ghi rõ **decimal hay binary** và nhất quán trong toàn ví dụ.

### Đơn vị throughput

- IOPS: input/output operations per second.
- MiB/s: lượng dữ liệu đọc/ghi mỗi giây.
- Gbps: gigabits per second, không phải GB/s.
- CPU-second/s: lượng tính toán tương đương một core chạy toàn thời gian.
- Requests/s: logical requests/giây, không đồng nghĩa disk IOPS.

## 8. Công thức dữ liệu logic sinh ra theo thời gian

Với write rate trung bình `W` records/s, retention `D` ngày và kích thước record cơ sở `S` byte:

\[
Records=W\times86{,}400\times D
\]

\[
LogicalDataBytes=Records\times S
\]

Cần biết `W` là **số bản ghi mới** hay số lần cập nhật record cũ:

- Append-only events: mỗi write thường tăng dung lượng.
- Upsert vào cùng key: số documents có thể ổn định dù write throughput lớn.
- Updates có version history/MVCC: storage churn và compaction debt vẫn tăng.
- TTL deletes: dữ liệu hết hạn không nhất thiết được reclaim ngay.

**Không dùng tổng update requests để tính số documents cuối cùng** nếu mỗi update ghi đè cùng tập khóa.

## 9. Index overhead và storage amplification

Một mô hình sơ bộ:

\[
StoredData\approx
LogicalData\times RF\times(1+IndexRatio)
\times(1+OperationalOverhead)
\]

Trong đó:

- `RF`: số bản sao vật lý theo chính sách replication, khi mô hình DB tương ứng.
- `IndexRatio`: dung lượng chỉ mục cộng thêm so với dữ liệu gốc.
- `OperationalOverhead`: metadata, MVCC/tombstones, fragmentation và các overhead **đã được định nghĩa**.

Đây là phép tính **ước lượng**, không phải mô tả mọi storage engine. Replication, compression, indexes, log retention và backup snapshots có thể được tính theo nhiều cơ chế; phải tránh **đếm đôi cùng một overhead**.

### Một số thành phần thường bị quên

| Thành phần | Vì sao phát sinh |
| --- | --- |
| Secondary indexes | Thêm cấu trúc index |
| Bloom filters/index blocks | Hỗ trợ truy vấn storage |
| WAL/commit log | Đảm bảo durability/recovery |
| SSTables/compaction | Nhiều phiên bản tạm thời |
| Tombstones/MVCC | Deletes/updates chưa reclaim |
| Repair/rebalance temp data | Sao chép lại replicas |
| Snapshots/local backups | Có thể giữ blocks lâu hơn |
| Compression dictionaries/metadata | Cấu trúc phụ |
| Object-store backup | Có thể tính phí ngoài local disk |

Không suy một index ratio cố định từ tên “NoSQL”; hãy đo sample dataset và index definitions thực tế.

## 10. Ví dụ tính dung lượng cho retention 90 ngày

Giả định:

~~~text
Average new events:        120/s
Retention:                 90 days
Base stored record:        1 KiB/event
Replication factor:        3
Index overhead:            +40% of base
Other steady overhead:     +15% after data/index/replicas
Target disk utilization:   <=65%
~~~

Số events:

\[
120\times86{,}400\times90=933{,}120{,}000
\]

Dữ liệu cơ sở:

\[
933{,}120{,}000\times1\;\mathrm{KiB}
\approx0.869\;\mathrm{TiB}
\]

Ba copies trước index:

\[
0.869\times3\approx2.61\;\mathrm{TiB}
\]

Thêm index và overhead:

\[
2.61\times1.4\times1.15\approx4.20\;\mathrm{TiB}
\]

Nếu chỉ xét mục tiêu sử dụng đĩa 65%:

\[
RequiredProvisionedDisk\ge
\frac{4.20}{0.65}\approx6.46\;\mathrm{TiB}
\]

**6,46 TiB không phải đáp án số node cuối cùng.** Còn phải xem kích thước shard, phân phối replication, disk IOPS, memory, CPU, network, cách khôi phục khi mất node/AZ và growth.

## 11. Headroom không phải dung lượng thừa vô ích

Ổ đĩa ở 90–95% capacity có thể khiến một số storage engines khó compaction, repair hoặc snapshot. Một ngưỡng như 65% trong ví dụ là **chính sách minh họa** cho workload có yêu cầu headroom, không phải giá trị tối ưu cho mọi DB.

Các lý do cần khoảng trống:

- Background compaction/merge cần temporary bytes.
- Replica repair hoặc rebalance tạo bản sao mới.
- Index build có thể cần không gian bổ sung.
- Retention/TTL cleanup có độ trễ.
- Một node/AZ hỏng khiến dữ liệu cần phân bố lại.
- Burst ingest xảy ra trước khi có thể scale.

### Công thức đơn giản

\[
Provisioned\ge
\frac{ExpectedStoredBytes+TemporaryBytesNeeded}
{TargetUtilization}
\]

Nếu `OperationalOverhead` đã bao gồm temporary bytes, **không cộng thêm lần nữa**. Quan trọng là đặt tên và định nghĩa rõ từng thành phần.

## 12. Từ tổng dung lượng sang số node

Nếu một node có usable data disk `C_node` và giới hạn occupancy `u`:

\[
N_{\text{storage}}=
\left\lceil\frac{StoredBytes}
{C_{\text{node}}\times u}\right\rceil
\]

Với 4,20 TiB stored, disk 1 TiB/node và `u=0.65`:

\[
\left\lceil\frac{4.20}{0.65}\right\rceil=7\;\text{nodes}
\]

Nhưng **bảy node** chỉ là giới hạn dưới theo **tổng raw space**; không đảm bảo phân bố shards/replicas, fault tolerance, CPU, RAM hay network. Cluster có thể cần nhiều hơn đáng kể.

### Đặt số node trong topology

Với ba Availability Zones, thường cần cân nhắc số node cân bằng mỗi AZ, replication placement và cơ chế quorum/failover. Một cluster 7 node chia 3 AZ không đều có thể kém phù hợp hơn topology có cấu trúc rõ ràng, dù tổng raw storage đủ.

## 13. N-1 và AZ failure capacity

Giả sử chọn 12 nodes, mỗi node 1 TiB disk, phân đều 4 node/AZ:

~~~text
AZ A: 4 nodes
AZ B: 4 nodes
AZ C: 4 nodes

Total disk provisioned: 12 TiB
Estimated stored data: 4.20 TiB
Normal total occupancy: 35.0%
~~~

Nếu mất một AZ, còn 8 TiB disk vật lý:

\[
4.20/8=52.5\%
\]

So với 9 nodes (3/AZ), mất một AZ chỉ còn 6 TiB:

\[
4.20/6=70.0\%
\]

Topology 12 node có **tổng headroom tốt hơn** sau sự cố vùng.

**Cảnh báo:** phép chia này không chứng minh hệ vẫn xử lý mọi request. Nó không mô phỏng placement của từng replica, quorum, shard ownership, dữ liệu chưa re-replicate, IOPS/CPU/network của nodes còn lại hoặc recovery time. Khả năng sống sót của một AZ failure phải được kiểm bằng topology và fault test thực tế.

## 14. Replication factor không đồng nghĩa quorum tự động

Nếu một hệ lưu RF=3, cần hiểu:

- Ba copies nằm ở những node/AZ nào?
- Leader/follower hay multi-leader?
- Số replicas cần đọc/ghi theo consistency policy?
- Nếu leader nằm trong AZ mất, failover mất bao lâu?
- Có read/write quorum để tiếp tục hay không?
- Khi chỉ còn hai AZ, placement/repair policy cho phép khôi phục RF thế nào?

RF=3 **không có nghĩa** luôn còn phục vụ mọi write khi mất bất kỳ node hoặc AZ. Product/driver/read-write consistency modes và topology quyết định behavior.

### Dung lượng replica

Nếu một hệ managed NoSQL đã tự tính replicas vào metric billed storage, không nhân RF lần nữa vào chi phí có thể dẫn đến đếm đôi. **Chọn mô hình theo dịch vụ cụ thể**.

## 15. Dữ liệu tăng trưởng và retention

Giả sử lượng write tăng 30% mỗi năm. Không thể sizing ổn định chỉ từ rate hiện tại nếu retention cố định và traffic tăng.

Một mô hình đơn giản:

\[
FutureRate(t)=CurrentRate\times(1+g)^t
\]

với `g` là tốc độ tăng hàng năm, `t` theo năm.

### Retention window trượt

Với TTL 90 ngày, khi hệ đạt steady state, lượng dữ liệu xấp xỉ **dữ liệu sinh ra trong 90 ngày gần nhất**, không phải cộng mọi năm không giới hạn. Nhưng tốc độ ingest tăng làm lượng data trong 90 ngày gần nhất cũng tăng.

### Khi TTL không reclaim ngay

- Tombstones cần compaction.
- Snapshot/backup có thể giữ blocks lâu.
- Replica chậm hoặc repair có thể làm trì hoãn purge.
- Một số DB không có TTL semantics giống nhau.

Đo **physical used bytes** và cleanup lag, không chỉ tính logical live documents.

## 16. Tách backup, snapshot và data capacity

Backup có thể được lưu trong object storage bên ngoài cluster, hoặc dùng local snapshots/hard links/copy-on-write. Những cách này ảnh hưởng disk khác nhau.

| Thành phần | Hỏi gì khi sizing? |
| --- | --- |
| Local snapshots | Có giữ blocks ngăn reclaim không? |
| Object-store backups | Bao nhiêu full + incremental bytes? |
| Backup egress | Đọc khỏi disk và gửi mạng bao nhiêu? |
| Restore temp space | Cần bao nhiêu free bytes? |
| Retention | Bao nhiêu recovery points cần giữ? |
| Encryption/compression | Tăng CPU và ảnh hưởng size thế nào? |

**Không được xem backup là replica**: replication giúp availability, còn backup/recovery phục vụ phục hồi logical deletes, corruption, ransomware và lỗi con người tùy thiết kế.

## 17. Bộ nhớ RAM: phân biệt working set và heap

**Working set** là phần dữ liệu/index được truy cập thường xuyên trong một khoảng thời gian, không nhất thiết là toàn database.

~~~text
Node RAM
  |
  +--> OS/kernel + filesystem buffers
  +--> Database cache / block cache
  +--> Index pages / metadata
  +--> Heap / off-heap structures
  +--> Query execution buffers
  +--> Connections / thread stacks
  +--> Headroom for spikes
~~~

Với MongoDB, Redis, Cassandra hoặc một search engine, tỷ lệ RAM dành cho cache/heap/off-heap rất khác nhau. Không áp chung câu “70% RAM cho heap” lên mọi NoSQL.

### Không chỉ đo `used_memory`

Một hệ có thể dùng nhiều RAM cho cache chủ động và vẫn khỏe. Điều cần xem là **cache miss, major page faults, GC/evictions, swap/reclaim, queue/latency** và giới hạn cgroup/container.

## 18. Cache working set và miss-rate curve

Giả sử hot data truy cập trong một giờ khoảng 400 GiB. RAM cache 200 GiB có thể hit cao nếu access có Zipfian skew, hoặc hit thấp nếu workload truy cập đều khắp 400 GiB.

Cần đo thực nghiệm:

- Cache hit/miss ratio theo read workload.
- Reuse distance hoặc working-set estimate.
- Object/block size distribution.
- Index residency.
- Query scan có đẩy hot pages khỏi cache không?
- Cache warm-up sau restart/failover mất bao lâu?

### Cách sizing thực tế

Thử thay kích thước cache (hoặc dùng canary/benchmark) và quan sát:

~~~text
RAM/cache ↑ → miss rate ↓ → disk read IOPS ↓ → p99 ↓
~~~

Khi tăng thêm RAM không còn giảm đáng kể disk I/O/tail latency, có thể đã tới vùng lợi ích biên thấp. **Dựa vào miss-rate curve**, không chỉ theo lời khuyên “RAM lớn hơn dữ liệu”.

## 19. Ví dụ memory trong topology 12 node

Giả định:

~~~text
Hot working set:       400 GiB
Node RAM:              96 GiB
Effective data cache:  60% RAM/node
Nodes:                 12, 4 per AZ
~~~

Cache budget lý thuyết toàn cụm:

\[
12\times96\times0.60=691.2\;\mathrm{GiB}
\]

Sau khi mất một AZ còn 8 nodes:

\[
8\times96\times0.60=460.8\;\mathrm{GiB}
\]

Trên giấy, 400 GiB hot set có thể vừa. Nhưng cần kiểm:

- Hot pages có được phân bố đều không?
- Có thêm replicas làm tăng cache duplication không?
- Phần RAM dành cho OS, JVM và queries có thật chỉ 40%?
- Cache bị cold sau failover có làm IOPS đột biến không?
- Dữ liệu hot mới có vượt 400 GiB khi traffic tăng không?

**Tổng RAM toàn cụm không chứng minh mỗi partition có đủ cache ở node phải phục vụ nó.**

## 20. Cassandra: heap, off-heap và OS page cache

Một Cassandra node cần RAM cho:

- JVM heap và GC.
- Memtables/structures tùy phiên bản.
- Off-heap caches/buffers.
- OS page cache.
- Connections và background tasks.

Quá nhiều heap có thể làm GC pauses tăng; quá ít heap/off-heap/cache có thể tăng disk reads. Sizing theo **version/config và metrics thực**, không dùng quy tắc heap bằng toàn RAM.

### Tín hiệu cần theo dõi

~~~text
GC pause time
Heap utilization after GC
Memtable pressure / flush backlog
Page cache misses
Disk read IOPS and latency
Read p99 / timeouts
~~~

Khi dataset tăng, cache miss có thể tăng dần dù CPU còn dư.

## 21. MongoDB: WiredTiger cache và index residency

Trong MongoDB sử dụng WiredTiger, cache, file-system page cache, working set và indexes ảnh hưởng đọc/ghi. Hãy xem:

- WiredTiger cache usage và eviction pressure.
- Resident memory/OS page cache.
- Document/key examined vs returned.
- Disk read bytes/IOPS.
- Slow query plan và index coverage.
- P99 khi working set không vừa RAM.

Một query thiếu index có thể scan nhiều documents và phá kế hoạch RAM/IOPS dù mỗi document chỉ vài KB. **Access pattern và index selection là một phần capacity planning**.

## 22. Redis: in-memory không có nghĩa không tốn CPU/I/O

Redis thường được dùng như cache/in-memory store; cần tính:

- Live keys/values.
- Allocator overhead và memory fragmentation.
- Expiration/eviction policy.
- Replication buffers, client buffers.
- Persistence (RDB/AOF) nếu bật.
- Fork/copy-on-write overhead trong những chế độ/version tương ứng.
- Hot keys và per-command CPU/network cost.

### Vùng nguy hiểm

`used_memory` dưới `maxmemory` không đảm bảo đủ cho mọi quá trình, do allocator overhead, buffers, persistence và process overhead. Khi gần giới hạn phải tính capacity cho **eviction behavior, hit rate và DB fallback impact**.

**Không tăng TTL vô hạn chỉ để giảm load DB** nếu dữ liệu cache cần freshness.

## 23. CPU: tính theo chi phí mỗi operation đã đo

Một ước lượng cơ sở:

\[
CPUSecondsPerSecond
\approx\sum_i QPS_i\times CPUSecondsPerOperation_i
\]

Nếu kết quả là 12 CPU-seconds/s, đó là mức tương đương **12 cores chạy 100%**. Nếu target CPU utilization bình thường là 60%:

\[
RequiredEffectiveCores\approx\frac{12}{0.60}=20
\]

Đây mới là **ước lượng aggregate**, chưa đảm bảo các cores nằm đúng node/partition đang nóng.

### Cách đo chi phí mỗi operation

- Đo cluster CPU baseline trước test.
- Tăng tải có kiểm soát từng loại query.
- Quan sát CPU tăng tương ứng.
- Tách background compaction/indexing khỏi foreground.
- Đo trên dữ liệu đủ đại diện và cache trạng thái rõ.
- Hiểu cloud vCPU credits/burst policies và noisy neighbor khi áp dụng.

**Không tự giả định một query MongoDB, Cassandra và DynamoDB có cùng CPU cost.**

## 24. Ví dụ CPU peak

Giả sử phép đo **tổng công CPU trên cluster** cho một logical request, đã phản ánh các replica/engine tasks chính của phép thử:

~~~text
Peak reads:            6,000/s
CPU work per read:      1.4 ms
Peak writes:           1,200/s
CPU work per write:     3.0 ms
Target CPU utilization: 60%
~~~

Tính:

\[
6000\times0.0014+
1200\times0.003=8.4+3.6=12
\]

CPU-seconds/s.

\[
12/0.60=20\;\text{effective cores}
\]

Nhưng một topology 12 nodes × 4 vCPU có 48 vCPU aggregate; **không có nghĩa tự động đủ**:

- Per-node hot spots.
- Repair/compaction/GC/serialization overhead chưa đo.
- Network interrupts, encryption/compression.
- CPU quota/stealing, throttling của container.
- Failed node/AZ khiến tải dồn lên nodes còn lại.

**Nếu CPU cost đo ở một node hoặc không gồm replicas, không được gọi đó là cluster-wide cost.**

## 25. CPU bão hòa và đường cong queue

CPU utilization tăng không tuyến tính vô hạn với throughput. Khi request arrival vượt service rate:

~~~text
Arrivals → Queue → Workers/CPU → Completed requests
             |
             +→ queue wait/p99 grows
~~~

Thường thấy:

- Run queue tăng.
- Thread pool backlog.
- p99 latency tăng.
- Timeout/retries tạo thêm tải.
- Throughput plateau hoặc giảm.

### Little's law

Ở trạng thái ổn định:

\[
L=\lambda W
\]

`L`: trung bình requests trong hệ, `λ`: throughput, `W`: thời gian trung bình trong hệ. Nếu 4.000 requests/s và 50ms:

\[
L\approx4000\times0.05=200
\]

requests in-flight trung bình.

Đây là quan hệ quan sát, **không phải công thức tự chọn thread pool size** khi workload có burst, queues, blocking hoặc saturation.

## 26. I/O: IOPS và throughput khác nhau

Hai loại disk workload:

~~~text
Workload A:
  10,000 random reads × 4 KiB
  ≈ 39 MiB/s
  → demanding IOPS/latency

Workload B:
  100 sequential reads × 4 MiB
  ≈ 400 MiB/s
  → demanding throughput
~~~

IOPS cao chưa chắc cần băng thông lớn; sequential scans có thể ngốn MiB/s nhưng IOPS tương đối thấp.

### Những thông số storage cần đo

- Read/write IOPS.
- Read/write throughput MiB/s.
- p95/p99 disk operation latency.
- Queue depth và saturation.
- Fsync/commit log latency.
- Random vs sequential, block size.
- Burst credit và throttling ở cloud volumes.
- Compaction/indexing/backup I/O nền.

Đừng chọn SSD chỉ bằng thông số “max IOPS” của brochure khi block size, queue depth và durability khác workload thật.

## 27. Read IOPS từ cache miss và read amplification

Một mô hình đầu vào:

\[
PhysicalReadIOPS\approx
LogicalReadsPerSecond
\times CacheMissFraction
\times PhysicalReadsPerMiss
\]

Giả sử:

~~~text
Peak logical reads = 6,000/s
Cache miss fraction = 25%
Storage read amplification = 3 physical reads per miss
~~~

\[
6000\times0.25\times3=4500
\]

**Khoảng 4.500 random read IOPS toàn cluster** trong mô hình minh họa.

Nếu mất AZ khiến working set cold và miss rate tăng lên 60%:

\[
6000\times0.60\times3=10{,}800
\]

IOPS, chưa tính recovery traffic. **Disk capacity phải đủ cho các pha failover/cold cache**, không chỉ steady-state hit ratio.

## 28. Write amplification không thể tính chỉ bằng số requests

Một write có thể sinh:

~~~text
Client write
  |
  +→ WAL/commit log
  +→ Memtable/index changes
  +→ Replica copies
  +→ Flush/compaction
  +→ CDC log/outbox/read model
~~~

Với LSM-tree, số physical bytes ghi lên disk có thể cao hơn bytes của logical writes vì flush và compaction. Với B-tree/MVCC engines, page rewrites/index maintenance và checkpoint cũng tốn I/O.

### Công thức tham khảo

\[
PhysicalWriteBytes\approx
LogicalWriteBytes\times WriteAmplification
\]

Nếu `WriteAmplification` đo **trên tất cả replicas**, không nhân RF lần nữa. Nếu chỉ đo **trên một replica**, cần xét replication placement. Định nghĩa phạm vi phép đo trước khi nhân.

### Lưu ý

Write amplification có thể thay đổi theo dataset, compaction strategy, TTL/tombstones, update ratio, compression và disk pressure. **Chỉ nên dùng hệ số đo được để quyết định hardware.**

## 29. Compaction debt và disk headroom

Một cluster có thể nhận writes nhanh hơn tốc độ compaction trong vài giờ:

~~~text
Incoming SSTable bytes: 200 MiB/s
Compaction effective drain: 150 MiB/s
Net backlog growth: 50 MiB/s
~~~

Trong 1 giờ:

\[
50\times3600=180{,}000\;\mathrm{MiB}
\approx175.8\;\mathrm{GiB}
\]

backlog tương đương trong mô hình đơn giản.

### Hệ quả

- Disk usage tăng dù TTL dự kiến sẽ xóa dữ liệu.
- Read amplification/tombstones tăng.
- Compaction tiêu CPU/disk lúc peak.
- Write path có thể throttle nếu backlog vượt an toàn.

Capacity không chỉ là disk space cho live data; còn là **năng lực xử lý nợ compaction và thời gian drain sau burst**.

## 30. Khi nào HDD, SSD, local NVMe hoặc managed storage?

| Lựa chọn | Ưu điểm thường gặp | Ràng buộc cần kiểm |
| --- | --- | --- |
| HDD | Chi phí/GB có thể thấp | Random IOPS/latency hạn chế |
| Network-attached SSD | Linh hoạt về capacity/replication | Per-volume IOPS, throughput, network limits |
| Local NVMe | IOPS/latency cao | Ephemeral behavior, node failure/rebuild |
| Managed storage | Vận hành đơn giản hơn | Provider quotas, scaling/cost semantics |

Không có “SSD luôn đủ cho NoSQL”. Một query scan lớn có thể bị network băng thông giới hạn; một hot key có thể bị CPU/lock giới hạn dù disk rảnh.

### Quy tắc chọn

Đo p99 disk read/write latency ở **đúng block size, queue depth và sustained load**. So với SLO client và background tasks, không chỉ benchmark thô.

## 31. Network: payload và hướng truyền

Các đường truyền:

~~~text
Client ↔ API ↔ NoSQL Coordinator
                 |
                 +→ Replica node A
                 +→ Replica node B
                 +→ Replica node C
                 |
                 +→ CDC connector / backup
~~~

Network sizing cần:

- Request/response bytes.
- Replication bytes và protocol overhead.
- Cross-AZ/region transfer.
- Streaming repair/rebalance.
- Backup and restore.
- CDC fan-out.
- TLS/encryption overhead.
- Connection count, packet rate, retransmission.

Ghi rõ **inbound/outbound** và băng thông **per node**, không chỉ tổng throughput cluster.

## 32. Ví dụ network cho peak workload

Giả sử:

~~~text
Peak writes:      1,200/s
Logical write:    1 KiB
Replication RF:   3
Peak reads:       6,000/s
Read response:    2 KiB
~~~

Write payload cơ sở:

\[
1200\times1\;\mathrm{KiB/s}
\approx1.17\;\mathrm{MiB/s}
\]

Nếu nguồn gửi tới hai replicas khác và model coi mỗi copy có payload tương ứng:

\[
1200\times1\times(3-1)\;\mathrm{KiB/s}
\approx2.34\;\mathrm{MiB/s}
\]

payload bổ sung cho replication.

Read response payload:

\[
6000\times2\;\mathrm{KiB/s}
\approx11.72\;\mathrm{MiB/s}
\]

Các số nhỏ này **chỉ tính payload logic theo giả định**, không gồm request headers, page scans, retries, aggregation fan-out, CDC, repair, snapshot, TLS, cross-AZ retransmit hoặc protocol chi phí thực.

### Cẩn thận khi tính

Nếu một read phải lấy từ nhiều replicas hoặc truy vấn fan-out nhiều shards, bytes thực cao hơn. Nếu dữ liệu compressed trên wire, thấp hơn. Hãy đo NIC throughput/packets và flow logs trong benchmark.

## 33. Network ở chế độ repair có thể thống trị steady-state

Giả sử cần truyền 2 TiB dữ liệu trong 4 giờ để repair/rebalance:

\[
Bandwidth\approx
\frac{2\times1024\times1024\;\mathrm{MiB}}
{4\times3600\;\mathrm{s}}
\approx146\;\mathrm{MiB/s}
\]

Tương đương khoảng **1,22 Gbps payload** trước overhead.

So với vài MiB/s logical write ở mục trên, recovery traffic lớn hơn rất nhiều.

### Điều cần ghi vào capacity plan

- Mất node/AZ cần rebuild bao nhiêu dữ liệu?
- Thời gian recovery mục tiêu là bao nhiêu?
- Có throttle repair để không phá SLO foreground không?
- Băng thông per-AZ/cross-region và egress cost?
- Disk read/write + CPU của source/destination đủ để stream không?
- Nếu restore từ object store, throughput/requests/quotas có đủ?

**Không chỉ lấy băng thông ban ngày để chọn NIC** nếu mục tiêu recovery đòi streaming lớn.

## 34. Network latency và replication consistency

Với replicated write:

~~~text
Client → Coordinator
             |
             +→ Replica A
             +→ Replica B
             +→ Replica C
             |
             +→ ACK condition satisfied
~~~

Thời gian write phụ thuộc:

- Số ACKs thực sự cần theo consistency policy.
- Network RTT tới replicas.
- Replica storage/CPU latency.
- Leader election/quorum behavior.
- Congestion, packet loss, tail RTT.

Cross-region synchronous writes có thể tăng latency đáng kể. **Không giảm consistency level chỉ để đạt latency** nếu làm sai yêu cầu correctness/độ bền của dữ liệu nghiệp vụ.

## 35. Cross-AZ và cross-region cost

Một cluster trải nhiều AZ có thể phát sinh:

~~~text
Replicated writes
Cross-AZ reads
Repair/rebalance
CDC to another AZ
Backups and restores
~~~

Chi phí theo byte và băng thông có thể khác nhau theo provider/region. Nên đo actual egress/transfer và đưa vào cost model, không dùng giá chung.

Với cross-region replication, cần thêm:

- RPO/RTO.
- Lag và conflict resolution.
- Failover routing.
- Data residency/compliance.
- Network partitions.
- Điều kiện kích hoạt disaster recovery.

**DR replica** không tự tương đương sync quorum replica trong một cluster nội vùng.

## 36. Partitioning: cân bằng key quan trọng hơn số node

Trong hệ sharded/partitioned, key distribution quyết định khả năng dùng tổng tài nguyên.

~~~text
12 nodes with total 12,000 ops/s capacity

Case balanced:
  ~1,000 ops/s per node

Case hot key:
  8,000 ops/s to one shard
  remaining nodes largely idle
~~~

Cluster có tổng CPU/disk/network dư vẫn có thể time out vì **hot partition**.

### Phương án

- Chọn partition key có cardinality và phân bố phù hợp.
- Dùng bucketing/salting khi cần, hiểu tradeoff query/fan-out.
- Tách heavy tenants.
- Tránh monotonic/time-only key gây hotspot ở write path nếu engine không phân tán phù hợp.
- Dùng capacity metrics per shard/partition và throttling reasons.
- Cân nhắc schema/data-model rewrite trước khi mua thêm nodes.

**Scale-out không sửa được mọi hotspot do access pattern.**

## 37. Read/write quorum và tải trên replicas

Một read ở consistency mạnh hơn có thể cần trao đổi với nhiều replicas hoặc coordinator validation. Một write với quorum ACK có thể chịu tail latency từ một số replicas.

Capacity planning cần đo theo:

- Read consistency level.
- Write consistency/ack requirements.
- Replica synchronization behavior.
- Failover/read repair/anti-entropy.
- Hot partitions ở leader/coordinator.

Không dùng cùng một latency/QPS benchmark ở eventual-consistency read để bảo đảm khả năng quorum read cho booking.

### Invariant hơn tốc độ

Nếu một thao tác có thể gây oversell hoặc double-spend, bảo vệ bằng conditional write/transaction tại authority, không dựa vào eventual search/cache để quyết định.

## 38. N-1 không chỉ là trừ một node

Với N nodes, nhiều tài liệu dùng khái niệm N-1 capacity: khi mất một node, phần còn lại vẫn đáp ứng workload cần thiết.

Nhưng cần tính:

- Node bị mất có phải node mạnh nhất/hot nhất?
- Leader/shard ownership chuyển đến đâu?
- Replica repair tạo thêm traffic.
- Cache cold-start.
- Disk/CPU/connection pool trên nodes còn lại.
- Quorum còn hoạt động không?
- Provisioning mất bao lâu?

**Tổng CPU sau trừ một node vẫn lớn hơn tổng CPU cần dùng chưa đủ** nếu dữ liệu/partitions không thể dịch chuyển kịp hoặc một nhóm replicas không còn quorum.

## 39. AZ outage và kiểm failure domain lớn nhất

Một cách kiểm headroom sơ bộ:

\[
RemainingCapacity=
TotalCapacity-CapacityOfFailedDomain
\]

\[
RemainingLoad=
OriginalLoad+RecoveryOverhead
\]

Áp cho CPU, RAM/cache, disk, IOPS và network **riêng từng loại**.

### Những điều phép tính không bắt được

- Replicas phân bố không đều.
- Control plane/quorum mất điều kiện.
- Stateful failover không tức thì.
- DNS/endpoint changes.
- Data đang degraded và chưa thể tái tạo.
- Cross-zone bandwidth bão hòa.

Chỉ một bài **fault test thực tế trong môi trường an toàn** mới kiểm được khả năng đáp ứng SLO khi mất AZ.

## 40. Network partition và CAP không biến mất nhờ overprovisioning

Thêm node, CPU và NIC không loại bỏ network partitions. Khi liên lạc giữa các replicas mất, database phải tuân consistency/availability contract cụ thể.

Capacity plan phải phân biệt:

- **Đủ tài nguyên để xử lý tải**.
- **Còn quorum để chấp nhận write/read**.
- **Dữ liệu đủ mới hoặc nhất quán theo nghiệp vụ**.
- **Có recovery path sau khi partition lành lại**.

Không tuyên bố “cluster có 12 nodes nên luôn available” nếu quorum/leader ở vùng bị mất.

## 41. Background jobs phải được tính như tải thật

Các tác vụ:

| Job | CPU | Disk I/O | Network | Memory |
| --- | --- | --- | --- | --- |
| Compaction | Có | Cao | Có thể ít | Buffers |
| Repair/anti-entropy | Có | Cao | Cao | Buffers |
| Backup | Compression/encryption | Read | Upload | Buffers |
| Rebalance | Có | Read/write | Cao | Cache churn |
| Index build | Cao | Read/write | Có thể | Working memory |
| CDC | Serialization | Commit log read | Publish | Queues |
| Analytics scan | Query CPU | Read | Results | Query buffers |

Một load test chỉ chạy foreground traffic trong lúc background jobs tắt sẽ **đánh giá quá lạc quan** khả năng production.

### Điều phối

- Có lịch/giới hạn tải nền.
- Dự trù thời gian catch-up khi job bị throttle.
- Ưu tiên giao dịch người dùng theo SLO.
- Theo dõi backlog, age và estimated drain time.

## 42. Queue, backpressure và hệ thống đệm

Nếu ghi đến 2.500/s nhưng processor chỉ hoàn tất 1.500/s:

\[
BacklogGrowth=2500-1500=1000\;\mathrm{events/s}
\]

Trong 10 phút:

\[
1000\times600=600{,}000\;\mathrm{events}
\]

Tồn đọng tăng. Bổ sung queue **không giải quyết nguyên nhân** nếu sustained service rate thấp hơn arrival rate.

### Cần bảo vệ

- Queue max size/retention.
- Consumer lag/oldest event age.
- Retry/backoff và poison message policy.
- Admission control và rate limits.
- Thời gian drain backlog sau burst.
- Không để retries làm tăng tải theo vòng lặp tích cực.

**Throughput đủ xử lý trung bình nhưng không đủ phục hồi backlog** có thể khiến hệ stale kéo dài sau incident.

## 43. Capacity cho CDC và read model

Một pipeline:

~~~text
Source DB commit → CDC → Broker → Indexer → Search
~~~

Mỗi tầng có rate riêng:

- Source commits/s.
- CDC capture bytes/s và connector CPU.
- Broker throughput/retention.
- Indexing ops/s và segment merges.
- Query-visible freshness.

Nếu source viết 1.200 events/s nhưng indexer chỉ apply 1.000 events/s sustained, backlog tăng 200/s. Dù database nguồn và broker còn dư tài nguyên, search projection sẽ ngày càng cũ.

### Capacity criterion

\[
SinkSustainedRate \gt SourceSustainedRate
\]

trong những điều kiện cần drain backlog; và phải đo được **freshness SLO**. Dấu `>` chỉ là điều kiện cần đơn giản, chưa xét event sizes, variance và downtime.

## 44. Managed NoSQL vs self-managed cluster

| Chủ đề | Self-managed cluster | Managed service |
| --- | --- | --- |
| Node sizing | Chọn VM/disk/RAM/replicas | Có thể bị ẩn hoặc trừu tượng |
| Disk/compaction | Trực tiếp vận hành | Tùy provider handles |
| IOPS/throughput quotas | Theo hardware/volume | Theo service/capacity mode |
| Replication | Chọn topology | Provider-specific |
| Scaling | Thêm node/rebalance | API/autoscaling, warm-up limits |
| Cost | VM + disk + network + ops | Billing by requests/capacity/storage/transfer |
| Observability | Engine/node metrics sâu | Một số metrics có thể không lộ |

Với DynamoDB chẳng hạn, sizing trực tiếp theo số node không phải giao diện phù hợp; cần capacity mode, consumed/provisioned read-write capacity, item size, hot partitions, API retry và quotas. Với MongoDB/Cassandra self-managed, chọn nodes/VM/disks và repair topology rõ hơn.

## 45. MongoDB sizing theo query shape và shard

Quan sát:

- Document và index sizes.
- WiredTiger cache pressure.
- `docsExamined/nReturned`, `keysExamined`.
- Query fan-out và shard targeting.
- Per-shard CPU/IOPS/latency.
- Replica lag/failover.
- Disk capacity và index rebuild/snapshot headroom.

### Ví dụ

Hai queries cùng trả 20 documents:

~~~text
Query A: examined 20 docs with selective index.
Query B: examined 200,000 docs due to scan.
~~~

Request count giống nhưng CPU/IOPS khác nhiều. Capacity issue có thể bắt đầu từ **thiết kế index/query**, không phải chỉ thiếu nodes.

### Sharding

Shard key ảnh hưởng phân phối và targeted queries. Thêm shard không tự tối ưu query luôn quét toàn cụm. Cần đo distribution, jumbo chunks/hot shards, migrations và latency trong rollout.

## 46. Cassandra sizing theo partition, LSM và repair

Các yếu tố quan trọng:

- Partition size và phân bố hot partitions.
- Read/write consistency.
- Tombstones/TTL.
- SSTables và compaction strategy.
- Disk utilization/headroom.
- Repair windows và streaming bandwidth.
- JVM heap/off-heap/cache.
- Coordinator behavior, timeouts và dropped messages.

### Lỗi phổ biến

Một wide partition chứa dữ liệu lịch sử quá lớn có thể làm reads/range scans nặng; thêm nodes không giúp nhiều nếu partition vẫn là đơn vị truy cập quá lớn.

### Khuyến nghị về phương pháp

Thử với **dataset đại diện, TTL/deletes, repair và compaction bật**, không benchmark chỉ trên dữ liệu mới ít SSTables.

## 47. Redis sizing theo hot set và eviction

Với Redis cache:

\[
RequiredRAM\approx
KeyValueBytes+AllocatorOverhead+Buffers+Headroom
\]

Cần tính thêm:

- Key metadata và object encoding.
- Memory fragmentation.
- Replication/client buffers.
- Persistence overhead nếu bật.
- Maxmemory policy và eviction.
- Hot-key CPU/network.
- Cache stampede khi eviction/expiration.

**Không dùng kích thước JSON value × số keys làm RAM chính xác** vì overhead mỗi key và encoding có thể đáng kể.

### Failover

Redis replica nhận tải đọc/ghi sau failover có thể thiếu CPU/network hoặc cache đã không đủ. Sizing phải xét **topology Sentinel/Cluster/managed service theo deployment**, không lấy tổng RAM master+replica như một working set liên tục.

## 48. DynamoDB sizing theo request units và hot partitions

Các yếu tố:

- Item size (và rounding theo API billing/capacity model).
- Read consistency.
- Read/write request rate.
- GSI/index write amplification.
- Batch/API behavior.
- Capacity mode (on-demand/provisioned).
- Per-partition hot-key limits và throttling.
- SDK retries/backoff làm tăng end-to-end latency.
- Streams/exports/backup và regional replication nếu dùng.

Không ước lượng DynamoDB bằng số node trong cluster tự quản; **đo consumed capacity/throttling và đọc đúng model/provider limits tại thời điểm thiết kế**.

### Một table còn “dư” vẫn có thể throttle

Một partition key nhận phần lớn requests có thể bị giới hạn riêng trong khi bảng chưa đạt tổng capacity. Cần xét key design và metrics throttling reasons, không chỉ tăng tổng provisioned units.

## 49. Search index sizing

Với search engine, lưu trữ không đơn thuần bằng document source bytes:

- Inverted indexes.
- Doc values/columnar data.
- Stored fields và source payload.
- Replicas.
- Segment merges và temporary data.
- Shard overhead.
- Cache/query working set.

Một query với nhiều filters/facets có CPU và memory khác query simple keyword. Indexing throughput và search throughput có thể cạnh tranh tài nguyên.

### Hãy đo cả hai SLO

1. Query latency/error.
2. Source commit → search query visible freshness.

Một search cluster có đủ disk nhưng indexing lag 30 phút vẫn không đáp ứng workload dự kiến.

## 50. Ví dụ sizing Java 17: skeleton có đơn vị rõ

Ví dụ sau là **mô hình sơ bộ cho append-only records**, không phải tool auto-sizing một NoSQL product. Tạo file `NoSqlCapacitySketch.java`:

~~~java
import java.util.Locale;

public final class NoSqlCapacitySketch {
    record Input(
            double avgNewRecordsPerSecond,
            int retentionDays,
            double baseRecordKiB,
            int replicationFactor,
            double indexRatio,
            double otherOverheadRatio,
            double targetDiskUtilization) {
    }

    static double recordCount(Input x) {
        return x.avgNewRecordsPerSecond()
                * 86_400.0 * x.retentionDays();
    }

    static double baseTiB(Input x) {
        // From KiB to TiB: divide by 1024^3.
        return recordCount(x) * x.baseRecordKiB()
                / (1024.0 * 1024.0 * 1024.0);
    }

    static double storedTiB(Input x) {
        return baseTiB(x)
                * x.replicationFactor()
                * (1.0 + x.indexRatio())
                * (1.0 + x.otherOverheadRatio());
    }

    static double requiredDiskTiB(Input x) {
        return storedTiB(x) / x.targetDiskUtilization();
    }

    static int minimumNodesForLargestZoneLoss(
            Input x, int zoneCount, double diskTiBPerNode) {
        if (zoneCount < 2 || diskTiBPerNode <= 0.0) {
            throw new IllegalArgumentException("Invalid topology");
        }

        for (int nodesPerZone = 1;
                nodesPerZone < 10_000; nodesPerZone++) {
            int remainingNodes = nodesPerZone * (zoneCount - 1);
            double remainingRawDisk =
                    remainingNodes * diskTiBPerNode;

            double occupancy = storedTiB(x) / remainingRawDisk;
            if (occupancy <= x.targetDiskUtilization()) {
                return nodesPerZone * zoneCount;
            }
        }
        throw new IllegalStateException("No simple fit found");
    }

    public static void main(String[] args) {
        Input example = new Input(
                120.0, // records/s average
                90,    // retention days
                1.0,   // KiB per stored base record
                3,     // copies
                0.40,  // index overhead
                0.15,  // other steady overhead
                0.65   // disk occupancy policy
        );

        System.out.printf(Locale.US,
                "Records: %,.0f%n", recordCount(example));
        System.out.printf(Locale.US,
                "Base: %.3f TiB%n", baseTiB(example));
        System.out.printf(Locale.US,
                "Stored: %.3f TiB%n", storedTiB(example));
        System.out.printf(Locale.US,
                "Provisioned disk floor: %.3f TiB%n",
                requiredDiskTiB(example));
        System.out.printf(Locale.US,
                "Simple 3-zone disk-only fit: %d nodes%n",
                minimumNodesForLargestZoneLoss(
                        example, 3, 1.0));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac NoSqlCapacitySketch.java
java NoSqlCapacitySketch
~~~

Kết quả xấp xỉ:

~~~text
Records: 933,120,000
Base: 0.869 TiB
Stored: 4.197 TiB
Provisioned disk floor: 6.457 TiB
Simple 3-zone disk-only fit: 12 nodes
~~~

### Giới hạn của chương trình

- Giả định append-only/retention đều; không mô hình updates, compression variability hoặc TTL reclaim delays.
- `replicationFactor` phải tương ứng cách lưu dữ liệu vật lý của DB cụ thể.
- Không bao gồm local snapshots/index builds nếu chưa đưa chúng vào overhead.
- Chọn 12 nodes chỉ theo **tổng capacity sau mất một AZ**, không chứng minh quorum/placement/data recovery/per-node capacity.
- Không tính CPU, RAM, disk latency, IOPS, network, hot partition hoặc cost; **bắt buộc đánh giá các ràng buộc đó riêng**.
- Input cần được ước lượng từ sample dataset và workload measurements thay vì điền tùy ý.

## 51. Bảng kiểm năm ràng buộc cho cùng một topology

Giả sử topology 12 nodes/3 AZ, mỗi node có 1 TiB disk, 96 GiB RAM và 4 vCPU. Bảng sau chỉ minh họa cách suy luận:

| Ràng buộc | Bình thường | Khi mất 1 AZ | Kết luận cần kiểm |
| --- | --- | --- | --- |
| Disk | 4.20/12 ≈35% | 4.20/8 ≈52.5% | Tổng space có vẻ đủ; kiểm placement |
| Data cache | 12×96×60%=691 GiB | 8×96×60%=461 GiB | So 400 GiB hot set, kiểm per-shard |
| CPU | 48 vCPU tổng | 32 vCPU còn | So CPU work 12 cores + recovery |
| Disk IOPS | Chia trên 12 nodes | Chia trên 8, thêm cold cache | Đo p99/queue per node |
| Network | Foreground + replication | Repair + rerouting | Đo cross-AZ peak |

Một ràng buộc có thể bị phá dù bốn ràng buộc khác vẫn dư. **Đừng cộng điểm trung bình để kết luận “cluster đủ 80% capacity”.**

## 52. Điểm nghẽn và giới hạn nhỏ nhất

Mô hình sơ bộ:

\[
AchievableQPS\le\min(
QPS_{\mathrm{CPU}},
QPS_{\mathrm{RAM/cache}},
QPS_{\mathrm{IOPS}},
QPS_{\mathrm{network}},
QPS_{\mathrm{partition}},
QPS_{\mathrm{quota}})
\]

Đây chỉ là trực giác “bottleneck yếu nhất”, không phải phương trình dự đoán chính xác QPS khi tài nguyên tương tác phi tuyến.

### Ví dụ

~~~text
CPU supports:       20k QPS
Disk supports:      12k QPS
Network supports:   30k QPS
Hot partition:       2k QPS for one tenant
~~~

Một tenant dồn vào partition nóng có thể thất bại ở 2k QPS dù tổng hệ đủ 12k.

## 53. Benchmark và load test phải đại diện

Một bài test tốt có:

1. Tập dữ liệu gần production về số records, size, skew và indexes.
2. Tỷ lệ reads/writes/scans giống mục tiêu.
3. Tương tác với consistency/quorum dự kiến.
4. Key distribution có hot tenants/partitions.
5. Connection count và concurrency thực.
6. Warm cache, cold cache và sau failover.
7. Background compaction/repair/backup.
8. Peak, burst và sustained peak.
9. Mất một node/AZ trong môi trường an toàn.
10. Đo p50/p95/p99, errors, throughput và SLO freshness.

### Tránh coordinated omission

Load generator chỉ phát request mới khi request cũ hoàn thành có thể vô tình giảm arrival rate khi hệ chậm, khiến tail latency được đánh giá quá đẹp. Khi cần đo arrival rate cố định, dùng công cụ/cách phát tải phù hợp và hiểu **open-loop vs closed-loop**.

**Không dùng benchmark “đọc cùng một key nằm cache một triệu lần” để đại diện cho workload nhiều partitions và writes.**

## 54. Đo cùng một scenario ở nhiều mức tải

Ví dụ test:

| Reads/s | Writes/s | p99 | Timeout | Disk queue |
| ---: | ---: | ---: | ---: | --- |
| 1.000 | 200 | 40 ms | 0% | Thấp |
| 3.000 | 600 | 70 ms | 0% | Thấp |
| 6.000 | 1.200 | 180 ms | 0.1% | Tăng |
| 8.000 | 1.600 | 650 ms | 2.0% | Cao |

Nếu SLO p99 là 200ms và timeout policy chặt, 6k/1.2k có thể gần vùng giới hạn ở workload test. Nhưng **vẫn cần test dài hơn**, failure and recovery load và dữ liệu đủ lớn.

### Đo điểm uốn

Điểm throughput tăng nhưng p99/queue bắt đầu tăng phi tuyến là cảnh báo capacity headroom. Không chọn deployment liên tục ở sát knee nếu burst/rebalance có thể xảy ra.

## 55. Autoscaling có độ trễ và điều kiện ổn định

Thêm nodes cần:

~~~text
Detect load
   |
Provision node/storage
   |
Join cluster
   |
Rebalance shards/replicas
   |
Warm cache
   |
Serve meaningful share of traffic
~~~

**Autoscaling không tức thì**. Nếu peak tăng gấp ba trong hai phút mà node mới mất hàng chục phút để warm/rebalance, vẫn cần headroom hoặc load shedding.

### Các giới hạn

- Provider quota.
- Instance provisioning availability.
- Rebalance network/IOPS.
- Cache cold-start.
- Database replica placement.
- Leader/failover.
- Cost control và scale-in safety.

Scale-in quá sớm có thể kích hoạt rebalancing/compaction churn liên tục.

## 56. Quota, bursting và cost

Cloud resources có thể có:

- Disk IOPS credits hoặc throughput ceiling.
- Network bandwidth limits theo instance.
- CPU credit/burst behavior với một số instance families.
- Service request quotas.
- Per-partition throughput restrictions.
- Cross-AZ transfer fees.
- Storage/backup retention fees.
- Monitoring/logging/tracing fees.

Đo **sustained capacity**, không chỉ burst benchmark vài phút.

### Chi phí tổng

\[
MonthlyCost\approx
Compute+Storage+IOPS+Network+
Backup+ManagedRequests+Operations
\]

Đừng tối ưu chỉ `cost/GB`. Một node rẻ có disk latency quá cao có thể làm phải mua nhiều nodes hơn và tăng latency đáng kể.

## 57. Monitoring để giữ capacity plan còn đúng

| Lớp | Metrics nên theo dõi |
| --- | --- |
| User-facing | Request rate, p95/p99, good-request fraction |
| Queue | Backlog count/age, admission rejected |
| CPU | Utilization, throttling, run queue |
| RAM | Cache hit, page faults, evictions, GC |
| Disk | Used/free, IOPS, MiB/s, p99 latency, queue |
| Network | In/out throughput, RTT, errors/retransmits |
| Replication | Lag, quorum health, repair progress |
| Storage engine | Compaction/flush, tombstones, index scans |
| CDC | Source commit-to-visible lag, consumer lag |
| Partition | Hot keys/shards, per-node skew |
| Capacity | Growth forecast, headroom after failure |

Một dashboard chỉ có **CPU average** và **disk usage total** sẽ không đủ để chẩn đoán NoSQL cluster.

## 58. Alert khi nào thì có ý nghĩa?

### User-impact alerts

- Availability/latency SLO burn rate cao.
- Write timeouts/conditional write errors bất thường.
- CDC freshness SLO bị vi phạm.

### Imminent capacity alerts

- Disk free không đủ cho compaction/repair.
- Hot partition throttling kéo dài.
- Node/volume IOPS saturation và p99 tăng.
- Forecast time-to-full ngắn hơn thời gian provision/rebalance.
- Replica quorum/placement suy giảm.

### Warning không cần page

- Growth vượt kế hoạch, nhưng có thời gian scale.
- Compaction backlog tăng nhưng drain vẫn ổn và SLO đạt.
- Query CPU tăng sau deploy chưa ảnh hưởng user.

Alerts cần **scope, duration, severity, owner và runbook**. Một alert “CPU >80%” không đủ ý nghĩa nếu không có hành động cụ thể.

## 59. Runbook: tăng tải và read latency xấu

1. Xác định API/operation, region, tenant và SLO impact.
2. Kiểm driver retries, pool wait và queue.
3. So throughput/latency với baseline cùng workload.
4. Kiểm hot partitions, query plan và index hiệu quả.
5. Kiểm cache hit, RAM pressure và page faults.
6. Kiểm disk IOPS/p99 latency/compaction.
7. Kiểm network RTT/packet loss và replica lag.
8. Tách background scan/backup/CDC jobs đang cạnh tranh tài nguyên.
9. Mitigate theo bottleneck: rate limit, query optimize, cache, scale, rebalance.
10. Kiểm p99/error/freshness phục hồi; ghi capacity learnings.

**Không tăng timeout vô hạn chỉ để giảm số lỗi** khi hàng đợi vẫn tích tụ.

## 60. Runbook: storage tăng nhanh

1. Xác định logical data growth hay physical amplification.
2. Kiểm index growth và schema changes.
3. Kiểm TTL expiration/tombstone/compaction lag.
4. Kiểm snapshots/backup retention.
5. Kiểm hot shards/nodes có disk gần đầy.
6. Tính time-to-full với uncertainty và worst-case burst.
7. Kiểm headroom cần cho rebuild/repair.
8. Nếu cần, giảm ingest/batch workload có kiểm soát.
9. Scale storage/nodes theo topology và quorum policy.
10. Xác minh cleanup/rebalance hoàn tất, SLO không suy giảm.

Không xóa data/indices hoặc hạ replication factor tùy tiện trong production nếu chưa đánh giá durability/recovery.

## 61. Runbook: mất node hoặc AZ

~~~text
Detect failure
   |
Confirm quorum/leader and service health
   |
Check remaining nodes' CPU/RAM/IOPS/network
   |
Measure request SLO + replication/freshness lag
   |
Control repair/rebalance bandwidth
   |
Restore/rejoin capacity safely
   |
Validate replicas/data consistency
   |
Recalculate headroom
~~~

### Câu hỏi quan trọng

- Node/AZ mất thuộc những replica groups nào?
- Client retries có đang làm quá tải nodes còn lại?
- Có cần giảm traffic hay chuyển route?
- Dữ liệu nào chưa re-replicate?
- Recovery có đạt RTO/RPO mục tiêu?
- Có giữ lại đủ bằng chứng lỗi phục vụ phân tích sau incident?

Một cluster “tự heal” không nhất thiết “heal kịp SLA”.

## 62. Sai lầm phổ biến

| Hiểu lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| Data size / disk size = số nodes | Bỏ qua CPU/IOPS/network/headroom | Sizing theo nhiều constraints |
| RF3 là ba lần dữ liệu chính xác trong mọi sản phẩm | Billing/storage semantics khác nhau | Kiểm engine/provider |
| CPU average thấp nghĩa còn dư | Hot shard/node có thể saturate | Per-node/per-partition metrics |
| RAM lớn là đủ | Cache locality và GC matters | Working-set/miss curve |
| SSD có IOPS cao sẽ nhanh | Tail latency/queue/throughput khác | Load test đúng workload |
| Network chỉ chuyển request/response | Replication/repair/backup có thể lớn | Full topology traffic |
| TTL xóa bytes ngay | Tombstones/snapshots/compaction | Đo physical usage |
| Storage 90% vẫn còn 10% dư | Compaction/rebuild cần temp | Headroom policy |
| Thêm nodes luôn sửa hot key | Partition key vẫn hotspot | Data model/bucketing |
| Có autoscaling thì không cần dự phòng | Provision/rebalance/warm-up mất thời gian | Peak headroom |
| Một benchmark trên dataset nhỏ là đủ | Cache skew và amplification khác | Representative workload |
| N-1 CPU đủ nghĩa chịu AZ failure | Quorum, placement, cache/IOPS còn | Failure-domain tests |
| Query p99 thấp nghĩa projection mới | CDC lag có thể cao | Freshness SLI |
| Tăng timeout giải quyết saturation | Có thể làm queue tệ hơn | Giải quyết bottleneck |
| Managed NoSQL không phải capacity planning | Còn quotas, costs, hot partitions | Plan theo provider semantics |

## 63. Bài tập thực hành

### Bài 1 — Từ API tới DB operations

Một API có 2.000 reserve requests/s, mỗi request tạo hai reads và một write. Tính logical DB operations/s. Nếu 10% requests retry toàn bộ flow một lần, ước lượng tải tăng thế nào?

**Gợi ý:** 4.000 reads/s + 2.000 writes/s trước retries; phân biệt retries và idempotency.

### Bài 2 — Logical data

120 append-only events/s, 1 KiB/event, retention 90 ngày. Tính số records và base TiB.

**Gợi ý:** 933.120.000 records, khoảng 0,869 TiB.

### Bài 3 — Replication/index/overhead

Tiếp Bài 2, RF3, index +40%, other overhead +15%. Tính stored TiB.

**Gợi ý:** khoảng 4,20 TiB.

### Bài 4 — Storage utilization

Target disk utilization 65%, stored 4,20 TiB. Tính raw disk provisioned tối thiểu nếu chỉ xét aggregate capacity.

**Gợi ý:** khoảng 6,46 TiB.

### Bài 5 — Node count

Mỗi node có 1 TiB data disk, occupancy max 65%. Ước lượng số node theo disk-only formula. Vì sao chưa thể chốt topology?

**Gợi ý:** 7 nodes theo công thức aggregate; chưa xét AZ/replica/quorum.

### Bài 6 — Failure zone

So 9 nodes (3/AZ) và 12 nodes (4/AZ), mỗi node 1 TiB disk, stored 4,20 TiB. Sau mất một AZ, raw occupancy lần lượt bao nhiêu?

**Gợi ý:** khoảng 70% và 52,5% theo phép chia đơn giản.

### Bài 7 — Working set

Hot working set 400 GiB; 12 nodes ×96 GiB RAM với 60% effective cache. Tính cache tổng và cache sau mất một AZ.

**Gợi ý:** 691,2 GiB và 460,8 GiB.

### Bài 8 — Locality

Vì sao tổng cache sau AZ failure lớn hơn 400 GiB **không chứng minh** mọi partition còn cache hit tốt?

**Gợi ý:** skew, replicas, remapping, cold cache.

### Bài 9 — CPU core-seconds

Peak 6.000 reads/s ×1,4 ms CPU-read và 1.200 writes/s ×3ms CPU-write, đo cluster-wide. Tính CPU-seconds/s và số cores ở utilization 60%.

**Gợi ý:** 12 CPU-seconds/s, 20 effective cores.

### Bài 10 — CPU phân bố

Cluster có tổng 48 vCPU nhưng một partition leader dùng hết một node 4 vCPU. Vì sao aggregate CPU vẫn có thể thấp?

### Bài 11 — Little's law

Arrival/throughput 4.000 req/s và time-in-system 50ms. Ước lượng requests in-flight khi ổn định.

**Gợi ý:** khoảng 200.

### Bài 12 — Read IOPS

6.000 reads/s, miss fraction 25%, ba physical reads/miss. Tính random read IOPS.

**Gợi ý:** 4.500 IOPS.

### Bài 13 — Failover cache

Nếu miss fraction tăng lên 60% trong cold cache failover, IOPS ước lượng thay đổi thế nào?

**Gợi ý:** 10.800 IOPS.

### Bài 14 — Write amplification

Một storage engine có 20 MiB/s logical writes và measured write amplification 5× trên một replica. Physical write throughput của replica xấp xỉ bao nhiêu? Khi nào nhân RF sẽ bị đếm đôi?

### Bài 15 — Compaction debt

Ingest flush 200 MiB/s, compaction drain 150 MiB/s. Một giờ backlog tăng bao nhiêu?

**Gợi ý:** khoảng 175,8 GiB.

### Bài 16 — IOPS vs throughput

So 10.000 reads/s ×4 KiB với 100 reads/s ×4 MiB. Loại nào nhấn mạnh IOPS và loại nào nhấn mạnh MiB/s?

### Bài 17 — Network payload

1.200 writes/s ×1 KiB RF3. Tính logical write payload/s và hai replica-copy payload nếu có hai copies mạng.

**Gợi ý:** khoảng 1,17 MiB/s và 2,34 MiB/s.

### Bài 18 — Read response

6.000 reads/s ×2 KiB response. Tính MiB/s. Vì sao bytes thực trên NIC có thể lớn hơn?

**Gợi ý:** khoảng 11,72 MiB/s; headers/replicas/scans.

### Bài 19 — Repair bandwidth

Truyền 2 TiB trong bốn giờ cần payload bandwidth bao nhiêu MiB/s và Gbps?

**Gợi ý:** khoảng 146 MiB/s, 1,22 Gbps.

### Bài 20 — Hot partition

Một cluster 12 nodes còn dư 70% aggregate CPU nhưng một key bị throttle. Hãy đề xuất ba hướng thay đổi data model/access pattern trước khi scale nodes.

### Bài 21 — Quorum

RF3 được đặt trên ba AZ. Nếu một AZ mất, những điều kiện nào quyết định read/write còn phục vụ đúng consistency level?

### Bài 22 — Backup

Phân biệt backup với replication. Nêu ba loại lỗi mà replica bình thường không giúp phục hồi hoàn toàn.

### Bài 23 — MongoDB

Hai queries cùng trả 20 documents nhưng một query examine 200.000 docs. Vì sao sizing dựa trên response size không đủ?

### Bài 24 — Cassandra

Một partition quá lớn có tombstones cao, compaction backlog tăng. Đề xuất metrics và data-model changes nên kiểm.

### Bài 25 — Redis

Giải thích vì sao `size(value) × numberOfKeys` chưa đủ để tính Redis RAM. Thêm memory overhead và failover requirements.

### Bài 26 — DynamoDB

Một table có consumed capacity thấp nhưng hot key bị throttle. Nên quan sát metrics gì và sửa partition key ra sao?

### Bài 27 — CDC

Source viết 1.200 events/s, consumer apply 1.000 events/s. Sau 30 phút backlog tăng bao nhiêu events nếu cả hai rates giữ nguyên?

**Gợi ý:** 360.000 events.

### Bài 28 — Autoscaling

Burst tăng gấp ba trong 2 phút nhưng node provision và warm-up mất 15 phút. Bạn cần headroom, admission control và backlog policy gì?

### Bài 29 — Storage forecast

Stored 4,2 TiB tăng 30%/năm. Với retention trượt, dữ liệu có tiếp tục nhân 1,3 mỗi năm không? Nêu các giả định.

### Bài 30 — Sizing Java

Chạy `NoSqlCapacitySketch.java`. Thay retention 90 →180 ngày, sau đó RF3 →2. So disk floor và rủi ro availability/durability khi giảm replicas.

### Bài 31 — Observability

Thiết kế dashboard một trang hiển thị user p99, disk occupancy, compaction lag, RAM cache misses, per-node CPU, per-node disk IOPS và cross-AZ repair bandwidth.

### Bài 32 — Load test

Viết load-test plan cho sustained peak, burst 5 phút, cold-cache restart, mất một node và mất một AZ. Nêu SLO, duration, pass/fail criteria.

### Bài 33 — Runbook

Trong giờ cao điểm, p99 tăng, CPU trung bình chỉ 40%, disk queue và cache misses tăng. Xác định bước chẩn đoán thay vì tăng CPU.

### Bài 34 — Chi phí

So hai topology có cost/GB và cost/IOPS khác nhau. Những chi phí ẩn nào có thể làm topology “rẻ theo disk” trở nên đắt?

### Bài 35 — Thiết kế cuối chương

Một nền tảng cho thuê có booking store, Redis cache, Cassandra event history, MongoDB listing, search projection và CDC. Hãy:

1. Đặt mục tiêu reads/writes/s, burst và growth.
2. Định nghĩa p95/p99/error/freshness SLO.
3. Tính live data, indexes, replication và retention.
4. Chọn disk occupancy/headroom policy.
5. Phân tích working set và cache after failover.
6. Dùng CPU-seconds/op để ước lượng cores.
7. Tính read IOPS và đo write amplification.
8. Tính foreground và repair network traffic.
9. Chọn số node/topology theo largest failure domain.
10. Xây benchmark/fault test và dashboard để xác nhận.

**Gợi ý:** làm một bảng cho mỗi constraint và chỉ chốt node count sau khi tất cả các ràng buộc đều có bằng chứng đo.

## 64. Checklist triển khai capacity plan

1. Đã định nghĩa target workload ở peak/burst/sustained chưa?
2. API QPS đã chuyển thành logical DB ops theo query mix chưa?
3. Đã phân biệt append writes và updates vào cùng key chưa?
4. Record size và compression đã đo trên dữ liệu đại diện chưa?
5. Index size, commit logs, compaction và backups đã được tính chưa?
6. Replication factor có đúng theo engine/provider billing và physical placement không?
7. Đã có disk utilization và temporary-space headroom chưa?
8. Đã kiểm tổng space sau mất node/AZ và per-shard placement chưa?
9. Có xác minh quorum/read-write consistency trong failure mode không?
10. Working set/cache miss và heap/off-heap đã đo chưa?
11. Cache sau cold failover có làm disk IOPS tăng đột biến không?
12. CPU work per operation được đo trong đúng workload chưa?
13. Có tính CPU cho replication, compaction và background jobs không?
14. Disk IOPS, throughput và p99 latency có được kiểm riêng không?
15. Write amplification và backlog drain đã được đo chưa?
16. Network foreground, replication, repair, CDC và backups đã được tính chưa?
17. Có phân biệt network per-node/cross-AZ/region không?
18. Hot partitions/tenants có được thử không?
19. Autoscaling lag và quotas đã được tính chưa?
20. Load test có dùng realistic dataset, consistency và peak duration không?
21. Có kiểm SLO khi failover, rebalancing và cold cache không?
22. Có dashboard theo node/shard cùng alert cho saturation/capacity không?
23. Có xét recovery time, budget và RPO/RTO không?
24. Có tính storage/compute/IOPS/network/backup cost không?
25. Sau schema/query/index/traffic changes có review lại plan không?

**Một bảng chỉ ghi “database 4 TiB → mua 5 node có tổng disk 5 TiB” chưa phải kế hoạch capacity.** Nó thiếu headroom, replicas, per-node bottleneck, network recovery và mục tiêu latency dưới tải.

## 65. Tổng kết

1. **Dung lượng không tự quyết định số node.** Cần đồng thời đánh giá RAM, CPU, disk IOPS/throughput, network, placement và failure scenarios.
2. **Workload model phải có peak, burst và average riêng**, cùng read/write mix, query shape, item size, hot key skew và background tasks.
3. **Storage sizing** dựa trên dữ liệu logic, retention, replication, index amplification, overhead, headroom và cleanup/repair behavior.
4. **RAM sizing** dựa trên working set, cache locality, miss-rate curve, heap/off-heap, GC và cold-start behavior.
5. **CPU sizing** nên dùng work-per-operation đo được, cộng background overhead và xét per-node bottlenecks thay vì cluster average.
6. **Disk sizing** phải phân biệt random IOPS, sequential MiB/s, p99 latency và write amplification/compaction debt.
7. **Network sizing** gồm foreground requests, replica traffic, cross-AZ/region, CDC, backup và đặc biệt recovery/repair bandwidth.
8. **Replication và N-1/AZ headroom không thay topology/quorum testing.** Phép cộng tổng capacity không chứng minh cluster còn đáp ứng SLO khi lỗi.
9. **Partition key/access pattern quan trọng ngang hardware**; thêm node không cứu được hot partition hay query scan không có index.
10. **Kế hoạch capacity phải được xác nhận và cập nhật liên tục** bằng benchmark, fault injection, metrics, forecast và runbook theo từng release/workload.

**Nguyên tắc thực hành:** trước khi chốt số lượng và cấu hình node NoSQL, hãy chứng minh bằng số đo rằng **dữ liệu vừa**, **working set có RAM hợp lý**, **CPU đủ ở peak**, **disk theo kịp IOPS/compaction**, **mạng đủ cho replication và recovery**, và **các ràng buộc ấy vẫn đủ trong failure mode mà hệ đã cam kết**. Chỉ khi mọi điều kiện cùng đạt, topology mới được coi là đã sizing cho tải mục tiêu.

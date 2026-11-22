# Lập kế hoạch dung lượng, mở rộng tài nguyên và tránh tối ưu theo dữ liệu thử quá nhỏ trong MongoDB

## 1. Vì sao hệ thống chạy nhanh với 10.000 documents vẫn có thể chậm ở production?

Một ứng dụng bán hàng dùng MongoDB để lưu đơn hàng. Trong môi trường phát triển, nhóm kỹ thuật tạo 10.000 orders, chạy vài câu lệnh **find()**, tạo index rồi thấy thời gian phản hồi chỉ vài mili giây. Nhóm kết luận một máy có 4 vCPU, 8 GiB RAM và ổ đĩa 100 GiB đủ phục vụ ba năm.

Sáu tháng sau, production có 50 triệu orders, 2 triệu customers, một số tenants rất lớn, hàng trăm người dùng đồng thời và nhiều batch jobs. Khi đó:

- Truy vấn từng nhanh nay phải quét nhiều documents.
- Index lớn hơn cache, tạo nhiều disk reads.
- CPU tăng vì aggregation, nén/giải nén và index maintenance.
- Truy vấn chậm ở **p95/p99** dù trung bình còn tốt.
- Secondary lag khi writes đột biến.
- Index build, restore và migration kéo dài.
- Tăng RAM không giải quyết được bottleneck CPU, disk hoặc shard key.
- Disk gần đầy, thiếu headroom cho index build, oplog hay migration.

Vấn đề không chỉ là chọn **máy mạnh hay yếu**. Cần hiểu dữ liệu, tốc độ tăng trưởng, workload, độ đồng thời, phân bố giữa tenants và yêu cầu vận hành.

**Lập kế hoạch dung lượng (capacity planning)** là dự báo và kiểm chứng xem MongoDB có đáp ứng được kích thước dữ liệu, tốc độ đọc/ghi, độ trễ và khả năng phục hồi trong khoảng thời gian xác định hay không.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **logical data size**, **physical storage**, **index size**, **working set** và dung lượng tính cả replication.
2. Dự báo tăng trưởng theo ngày/tháng, retention, TTL, thay đổi kích thước documents và indexes.
3. Dự trù **CPU, RAM, WiredTiger cache, disk IOPS/throughput, network, connections** và headroom.
4. Chọn giữa **vertical scaling**, **replica set read scaling**, **sharding** và tối ưu query/index.
5. Định nghĩa KPI/SLO, cảnh báo và ngưỡng quyết định nâng cấp.
6. Thiết kế benchmark với **dataset đủ lớn, phân bố thực tế, concurrency và cache state**.
7. Tránh kết luận sai do dữ liệu thử nhỏ, index luôn trong RAM và tải không có hot keys.
8. Dùng **explain()**, **$collStats**, **$indexStats**, **serverStatus**, profiler và metrics.
9. Xây capacity forecast theo base, high-growth và stress cases.
10. Thiết kế benchmark và scaling rollout có tiêu chí thành công/rollback.

### 1.1. Ba câu hỏi trọng tâm

~~~text
1. Hệ thống đang tiêu thụ tài nguyên nào?
        |
        v
2. Với growth/workload dự kiến, tài nguyên nào cạn đầu tiên?
        |
        v
3. Biện pháp mở rộng nào giải quyết đúng bottleneck?
~~~

Không chọn giải pháp cho câu hỏi thứ ba trước khi có bằng chứng cho hai câu đầu.

## 2. Những chiều dung lượng cần tính riêng

Một cluster MongoDB không có một đại lượng duy nhất tên “size”.

| Chiều | Ý nghĩa | Rủi ro khi đánh giá sai |
|---|---|---|
| **Số documents** | Quy mô logical records. | Không thấy growth/hot partitions. |
| **Logical BSON bytes** | Dung lượng dữ liệu BSON theo metric. | Nhầm với physical bytes. |
| **Collection storage** | Storage engine lưu/cấp phát cho collection. | Thiếu dự trù nén, fragmentation. |
| **Index storage** | B-tree indexes và structures khác. | Thiếu disk và working set. |
| **Working set** | Data/index pages được truy cập thường xuyên. | RAM không phù hợp. |
| **CPU** | Query, aggregation, compression, index maintenance. | Tăng RAM khi CPU là bottleneck. |
| **Disk IOPS/latency** | Khả năng đáp ứng random reads/writes. | Cache misses làm p95 chậm. |
| **Disk throughput** | Bytes/s cho scans, backups, index build. | Batch/restore quá chậm. |
| **Network** | App↔router, replication, backup/migration. | Network saturation và lag. |
| **Connections** | Concurrent requests/driver pools/queues. | Pool starvation dù server còn khỏe. |
| **Replication overhead** | Bản sao dữ liệu trên mỗi member. | Thiếu ngân sách lưu trữ. |
| **Backup/recovery** | Snapshot/archive và restore duration. | Không đạt RPO/RTO. |
| **Sharding distribution** | Owned bytes và QPS theo shard. | Tổng capacity đủ nhưng một shard hot. |

### 2.1. Logical data size khác physical disk

Giả sử dữ liệu logical là 400 GiB. Sau nén WiredTiger, collection storage có thể nhỏ hơn 400 GiB; nhưng indexes, oplog, fragmentation và các collections khác khiến tổng disk lớn hơn.

~~~text
Logical BSON data:          400 GiB
Compressed collection:     250 GiB
Indexes:                   110 GiB
Other/allocated overhead:   40 GiB
---------------------------------
Illustrative used storage: 400 GiB
~~~

**Đây chỉ là số minh họa**, không phải hệ số nén mặc định. Văn bản lặp nén khác ảnh JPEG, blobs đã nén hoặc dữ liệu ngẫu nhiên.

### 2.2. Working set không bằng toàn bộ database

Working set là các data/index pages được truy cập trong một khoảng thời gian đại diện:

~~~text
Total historical orders:   2 TiB
Frequently read last 30d: 120 GiB
Hot indexes/pages:         45 GiB
Other cache needs:         variable
~~~

Không nhất thiết cần nạp toàn bộ 2 TiB vào RAM để phục vụ truy vấn gần đây. Nhưng scans lịch sử, reports và batch jobs có thể làm working set tăng đột biến. Không dùng một tỷ lệ RAM/data cố định thay cho đo **evictions, cache misses, disk I/O và latency**.

### 2.3. Replica set nhân số bản sao vật lý

Một replica set ba data-bearing members lưu ba bản sao logic, cộng overhead riêng của mỗi member:

~~~text
Primary:       400 GiB live storage
Secondary A:   400 GiB live storage
Secondary B:   400 GiB live storage
---------------------------------
Approx. total: 1.2 TiB, before backups
~~~

Số thực tế có thể khác do oplog, compression, fragmentation và index build. Không nhầm **ba replica members** với **ba shards logic**.

### 2.4. Sharding không giảm tổng lượng dữ liệu

Ba shards chia logical dataset thành các phần, chứ không làm dữ liệu biến mất. Mỗi shard có thể là một replica set với nhiều physical copies. Sharding tăng khả năng phân phối data/workload nhưng thêm routing, metadata, migration và operational overhead.

### 2.5. Headroom là một phần của kế hoạch

~~~text
Required capacity
  = expected live storage
    + index/oplog/storage overhead
    + temporary operational space
    + growth/uncertainty headroom
~~~

Phải xét index builds/rebuilds, backup/restore, migration, bursts và fragmentation. Không có một tỷ lệ headroom bảo đảm an toàn cho mọi deployment; cần quyết định theo topology, growth và SLO.

## 3. Mô hình tăng trưởng dữ liệu theo thời gian

### 3.1. Bắt đầu từ đơn vị đo được

Giả sử application lưu orders:

~~~text
orders per day                = 300,000
average BSON document size    = 2.0 KiB
retention period              = 3 years
index storage                 = measured separately
daily update amplification    = measured
~~~

Khi chưa có production, những con số này là **giả định có chủ sở hữu** chứ không phải dữ liệu chắc chắn. Ghi ngày đo, cách đo, nguồn và khoảng sai số.

### 3.2. Tốc độ tăng logical data

300.000 documents mỗi ngày, mỗi document trung bình 2 KiB:

~~~text
newLogicalBytesPerDay
  = documentsPerDay * avgBsonBytes
  = 300,000 * 2,048
  = 614,400,000 bytes/day
  ≈ 586 MiB/day
~~~

Sau 365 ngày, nếu không xóa:

~~~text
586 MiB/day * 365 ≈ 209 GiB
~~~

Đây là **logical inserted bytes**, chưa tính kích thước tăng từ updates, indexes, physical compression, oplog hay temporary files.

### 3.3. Retention/TTL

Nếu chỉ giữ dữ liệu 90 ngày và tốc độ ổn định:

~~~text
steadyStateDocumentCount
  ≈ 300,000 * 90
  = 27,000,000

steadyStateLogicalSize
  ≈ 27,000,000 * 2,048 bytes
  ≈ 51.5 GiB
~~~

Với TTL index, việc xóa diễn ra nền và **không có SLA xóa đúng một giây sau hết hạn**. Khi có backlog, data retained có thể cao hơn mô hình lý tưởng; storage engine cũng không nhất thiết trả physical disk blocks cho OS ngay khi documents bị xóa.

Nếu dữ liệu được archive trước khi xóa, còn phải dự trù **archive storage, transfer và rehydration costs**.

### 3.4. Kích thước documents không đồng nhất

Một production corpus có thể:

| Loại order | Tỷ lệ | BSON trung bình |
|---|---:|---:|
| Ít items | 70% | 1.2 KiB |
| Trung bình | 25% | 3.5 KiB |
| Nhiều items | 5% | 18 KiB |

Weighted average:

~~~text
0.70*1.2 + 0.25*3.5 + 0.05*18
= 0.84 + 0.875 + 0.9
= 2.615 KiB
~~~

Nếu test chỉ tạo orders loại nhỏ (1.2 KiB), dự báo dựa trên test có thể **đánh giá thiếu hơn hai lần** so với trung bình này.

Ngoài average, đo **p50, p95, p99, max BSON size** và array length distribution. MongoDB có **giới hạn 16 MiB cho một BSON document**; arrays tăng không giới hạn còn gây nhiều vấn đề khác trước khi đạt giới hạn đó.

### 3.5. Growth không nhất thiết tuyến tính

Nếu orders/ngày tăng 5% mỗi tháng:

~~~text
docsPerDay(month m)
  = baselineDocsPerDay * (1.05)^m
~~~

Một forecast tốt có ít nhất ba kịch bản:

| Kịch bản | Ý nghĩa |
|---|---|
| **Base** | Theo tốc độ tăng trưởng quan sát và kế hoạch sản phẩm. |
| **High growth** | Tăng nhanh do mở thị trường/khách hàng lớn. |
| **Stress** | Flash sale, import dữ liệu, batch backfill, failure replay. |

Không giả định traffic luôn tăng đều hoặc tăng lũy thừa vô hạn; cần xét mùa vụ, retention và thay đổi business rules.

### 3.6. Updates và deletes cũng tiêu tài nguyên

~~~javascript
{
  _id: "O-100",
  customerId: "C-1",
  statusHistory: [
    { state: "CREATED", at: ISODate("2026-01-01T00:00:00Z") },
    { state: "PAID", at: ISODate("2026-01-01T00:05:00Z") }
  ]
}
~~~

Nếu **statusHistory** tăng theo mỗi update, document sẽ lớn dần. Cần tính:

- Bao nhiêu updates mỗi document trong vòng đời?
- Net BSON size change bao nhiêu?
- Indexed fields có bị đổi và tạo thêm index maintenance?
- Write amplification, oplog, change streams và backups?
- Có giới hạn history hay tách sang collection sự kiện riêng?

Không chỉ lấy inserts × average size rồi coi updates là miễn phí.

### 3.7. Index growth

Giả sử data được nén tốt nhưng có năm indexes compound lớn. Không thể dự báo index bytes bằng một hệ số chung cho mọi workload:

~~~text
indexBytes = f(numberOfEntries, key sizes, multikey fan-out,
               compression, index structure, updates, versions)
~~~

Ví dụ một array field được đánh index theo **multikey** có thể tạo nhiều index keys theo từng document; key cardinality và arrays làm tốc độ tăng index khác dữ liệu.

Hãy lấy baseline indexSize trên representative corpus, rồi dự báo theo số records, document shape và array distributions. Tạo index bổ sung có thể tăng disk/cache/write cost đáng kể.

### 3.8. Oplog retention và workload

Replication oplog là log các thay đổi được lưu trong replica sets. Dung lượng và khả năng giữ lịch sử ảnh hưởng:

- Secondary có thể catch up sau downtime bao lâu?
- Change stream consumers có thể resume từ bao xa?
- Backup/oplog-based recovery workflows?

Không tính oplog theo số documents live: **updates/deletes cũng tạo entries**. Một write-heavy cluster với ít data live vẫn có thể cần oplog đáng kể theo mục tiêu retention và throughput.

### 3.9. Một biểu mẫu forecast theo tháng

| Tháng | Docs mới | Docs hết retention | Docs retained | Logical bytes | Index bytes | Physical storage | Headroom |
|---|---:|---:|---:|---:|---:|---:|---:|
| M0 | Baseline | 0 | Baseline | Đo | Đo | Đo | Theo policy |
| M1 | Dự báo | Dự báo | Tính | Tính | Ước lượng | Ước lượng | Tính |
| M2 | Dự báo | Dự báo | Tính | Tính | Ước lượng | Ước lượng | Tính |
| M3 | Dự báo | Dự báo | Tính | Tính | Ước lượng | Ước lượng | Tính |

Phân biệt **đã đo** với **ước lượng**; cập nhật mô hình bằng metrics thực sau mỗi kỳ.

## 4. Capacity không chỉ là số GB

### 4.1. Throughput và latency là hai SLO khác nhau

Một hệ thống có thể xử lý 10.000 ops/s nhưng p99 latency quá cao. Ngược lại, hệ thống phản hồi 5 ms khi chỉ có một client chưa chắc chịu được 1.000 clients đồng thời.

Ví dụ SLO:

~~~text
GET /orders/{id}:
  p95 < 80 ms under target load
  p99 < 250 ms under stress condition

POST /orders:
  p95 < 150 ms
  error rate < 0.1%
~~~

Đây là **SLO minh họa**, không phải cam kết mặc định của MongoDB. SLO nên đo ở application boundary (cả mạng, driver pool và downstream logic), đồng thời có DB-specific metrics để chẩn đoán.

### 4.2. Concurrent operations và Little's Law

Một quan hệ gần đúng trong hệ thống ổn định:

~~~text
L ≈ λ * W

L = số requests/operations đang trong hệ thống trung bình
λ = throughput hoàn tất trung bình / giây
W = thời gian lưu lại trong hệ thống trung bình (giây)
~~~

Nếu throughput 2.000 requests/s và mỗi request mất 50 ms:

~~~text
L ≈ 2,000 * 0.050 = 100 concurrent requests
~~~

Đây là phép tính cho workload/system boundary được định nghĩa, **không có nghĩa MongoDB cần đúng 100 connections**: một request có thể phát nhiều operations, connection pool có hàng chờ, và các operations có thể không chiếm socket xuyên suốt toàn request.

### 4.3. CPU capacity

CPU tiêu thụ bởi:

- Query execution và filtering/aggregation.
- Sorting, grouping, projections.
- WiredTiger compression/decompression.
- Index maintenance và BSON processing.
- Encryption/TLS, mongos routing.
- Background tasks, replication, index builds.

Nếu CPU đạt giới hạn trong load test, cần phân tích **CPU usage vs useful operations/s**, query plans và service time. Tăng CPU không giúp nhiều nếu bottleneck thực là disk latency hoặc lock/contention.

### 4.4. WiredTiger cache và memory

MongoDB WiredTiger dùng cache để giữ internal data/index pages. Mức cache mặc định phụ thuộc server version, cấu hình và môi trường; ngoài WiredTiger cache vẫn cần memory cho OS, connections, aggregation và các components khác.

Theo dõi:

- Cache bytes in use, dirty bytes, eviction pressure.
- Page reads from disk và disk latency.
- Page faults và memory pressure hệ điều hành.
- Aggregation sort/group spilling theo version.
- Số concurrent operations và memory peaks.

**RAM lớn hơn không tự sửa bad query plan**: một COLLSCAN quét quá nhiều documents vẫn tốn CPU và I/O dù được cache tốt.

### 4.5. Disk IOPS và storage latency

Một workload có nhiều point reads không nằm trong cache có thể cần nhiều random IOPS. Một batch scan đọc nhiều bytes liên tục lại nhạy với throughput.

~~~text
Point lookups with cache misses -> random reads / IOPS
Large scans / index builds      -> throughput and CPU
Heavy writes / updates         -> write IOPS, durability, replication
~~~

Không chọn ổ chỉ theo “1 TiB capacity”; cần xem **sustained IOPS, throughput, p95/p99 disk latency, burst credits và throttling** của nền tảng.

### 4.6. Network và replication

Ứng dụng và cluster phải truyền:

- Read results/write payloads.
- Replication oplog streams.
- Balancer range migration copies.
- Backups/restore/CDC.

Network bottleneck hoặc packet loss có thể gây replication lag và p95 latency tăng. Một replica set có ba members không có nghĩa mỗi write chỉ truyền dữ liệu một lần.

### 4.7. Driver connection pools

Connection pool configuration ảnh hưởng queueing và khả năng thực thi concurrently:

~~~text
Incoming application requests
          |
          v
Driver connection pool
          |
     +----+-----+
     |          |
  Available   Waiting
 connections requests
     |          |
     v          v
MongoDB       Pool wait latency
~~~

Quá ít connections gây pool wait; quá nhiều connections và threads có thể làm mongod cạnh tranh tài nguyên và tăng context switching. Tối ưu pool dựa trên **active operations, checkout latency, server metrics và load tests**, không đặt maxPoolSize khổng lồ mà không đo.

### 4.8. Batch jobs và peak workload

Một hệ thống ổn định 500 writes/s ban ngày có thể nhập 20 triệu documents đêm cuối tháng. Capacity planning phải mô phỏng:

- Peak ingest throughput.
- Concurrent application traffic.
- Backfill/migration.
- Index build/maintenance.
- Replication lag.
- Backup window.

Đừng lấy average QPS toàn ngày làm mục tiêu duy nhất cho provisioning.

## 5. Chọn đúng phương án mở rộng tài nguyên

Trước khi scale, định nghĩa **bottleneck** bằng bằng chứng:

~~~text
Query plan inefficient?
  -> index/schema/query optimization

Cache misses + high disk reads?
  -> working-set and memory/storage analysis

CPU saturated on one mongod?
  -> efficient queries, vertical scaling, possible sharding

Read-heavy traffic?
  -> query tuning, cache, read distribution / replicas

Write throughput concentrated on one shard?
  -> shard-key/write distribution and possible resharding

Disk near capacity?
  -> retention/archive/index cleanup, scale disk or shards
~~~

Không mặc định **thêm shards** là câu trả lời cho mọi query chậm.

### 5.1. Vertical scaling: tăng tài nguyên mỗi node

**Scale up** là tăng vCPU, RAM, disk, IOPS/throughput hoặc node class.

Ưu điểm:

- Ít thay đổi kiến trúc ứng dụng và shard key.
- Hợp lý khi bottleneck nằm trên một node và có thể giải quyết bằng hardware.
- Có thể giúp working set gần vừa cache hoặc CPU có thêm headroom.

Giới hạn:

- Có mức máy tối đa, giá có thể tăng không tuyến tính.
- Failover/maintenance vẫn cần xem replica set và member compatibility.
- Chỉ tăng vCPU không giúp nếu disk I/O đã nghẽn.
- Bad query plan không tự tốt lên nhờ máy lớn hơn.

Nếu WiredTiger cache pressure cao và nhiều random disk reads, tăng RAM có thể giúp. Nhưng phải so **cache misses, latency và IOPS trước/sau** để chứng minh.

### 5.2. Read scaling bằng replica set

Replica set có secondaries phục vụ availability và trong một số workload có thể phân phối read operations theo **read preference**.

Lưu ý:

- Writes chủ yếu xử lý tại primary và replicate sang secondaries.
- Reads trên secondaries có thể stale vì replication lag.
- Không tự chia đều mọi query chỉ nhờ thêm secondaries.
- Data/indexes được lưu trên mỗi data-bearing member.
- Read workload trên secondary có thể cạnh tranh I/O với replication.

Ví dụ cấu hình Java theo read preference trong workload chấp nhận eventual consistency:

~~~java
MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .readPreference(ReadPreference.secondaryPreferred())
    .build();
~~~

Đây là minh họa cấu hình, cần imports/khởi tạo client đầy đủ và consistency contract ở production. Không chuyển mọi truy vấn giao dịch tài chính sang secondary reads chỉ để giảm primary CPU.

### 5.3. Sharding để phân phối data và workload

**Sharding** partition sharded collections trên nhiều shards và giúp mở rộng capacity khi:

- Dataset/working set vượt giới hạn kinh tế hoặc kỹ thuật của một replica set.
- Write throughput cần phân phối.
- Query patterns có thể target shard theo shard key.
- Đội vận hành có khả năng giám sát mongos, CSRS, balancer, migration.

Không phù hợp khi:

- Query chính thiếu shard key và thường scatter-gather.
- Một hot key chiếm phần lớn writes.
- Dataset quá nhỏ so với complexity thêm.
- Vấn đề là thiếu index hoặc aggregation không hiệu quả.

### 5.4. Chọn shard key theo workload

~~~javascript
{ createdAt: 1 }
~~~

Với inserts timestamp tăng liên tục, range ở rìa keyspace có thể thành write hot spot.

~~~javascript
{ deviceId: "hashed" }
~~~

có thể phân tán nhiều devices, nhưng một device tạo 70% events vẫn có nguy cơ hot. Đánh giá **cardinality, frequency, monotonicity, query targeting, zone constraints và future growth** trước khi sharding.

### 5.5. Shard mới không nhận data tức thì

Balancer cần thời gian chuyển eligible ranges theo chính sách và resource limits. Không lập kế hoạch giả định:

~~~text
Add shard at 10:00
All data balanced by 10:01
~~~

Trong migrations cần thêm network bandwidth, recipient disk headroom và replication capacity. Zones hoặc oversized ranges có thể hạn chế migration.

### 5.6. Retention/archive thay vì chỉ scale

Nếu 95% queries đọc 90 ngày gần nhất nhưng collection giữ logs 10 năm:

~~~text
Hot collection: last 90 days
Cold archive: older data according to retention
~~~

có thể giảm working set/index size. Nhưng phải thiết kế archive query, compliance, TTL cleanup, restore và dữ liệu cần rehydrate.

### 5.7. Cache ứng dụng

Catalog data được đọc lặp lại có thể được cache ở tầng ứng dụng/Redis/CDN nếu semantics cho phép. Cache giảm read load nhưng thêm complexity về expiration, invalidation, stale reads và authorization.

Không dùng cache để che bad query plan mà chưa đo tác dụng; cache key phải đúng user/tenant permissions khi dữ liệu có phân quyền.

### 5.8. Bảng lựa chọn

| Triệu chứng | Kiểm tra | Biện pháp cân nhắc |
|---|---|---|
| COLLSCAN lớn | explain, predicates | Query/index optimization. |
| RAM pressure, disk reads cao | WiredTiger cache, working set | RAM/storage hoặc giảm hot data. |
| CPU cao do aggregations | Profiler, pipeline | Tối ưu pipeline, thêm vCPU khi cần. |
| Disk latency cao | Cache misses, IOPS | Storage tier, query changes. |
| Primary read load cao | Consistency, pool, traffic | Secondary reads/cache/query tuning. |
| Hot writes một key | Shard key frequency | Redesign partition/reshard. |
| Dataset vượt node | Retention, growth, disk | Scale node/disk hoặc shards. |
| Disk một shard đầy | Balancer, zone, indexes, orphans | Fix placement/capacity theo evidence. |
| Backup quá lâu | Throughput, snapshot, RPO/RTO | Backup architecture và bandwidth. |

## 6. Vì sao dữ liệu thử quá nhỏ tạo kết luận sai?

Một trong các bẫy tối ưu MongoDB là **test corpus không giống production** về quy mô, hình dạng documents, phân bố values và concurrency.

### 6.1. Data/indexes luôn nằm trong RAM

Ở local:

~~~text
Data:     10 MiB
Indexes:   4 MiB
RAM:       8 GiB
~~~

Point reads gần như toàn từ cache.

Ở production:

~~~text
Data:      2 TiB
Indexes: 400 GiB
RAM:      64 GiB
~~~

Cache misses và random I/O trở nên quan trọng. Kết quả 10 MiB không dự báo tin cậy latency của 2 TiB.

### 6.2. Query planner chọn plan khác

Với 20 documents, **COLLSCAN** có thể rất nhanh hoặc hợp lý. Với 50 triệu documents, cùng query có thể cần index.

~~~javascript
db.orders.find({
  customerId: "C-100",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
~~~

Một compound index ứng viên:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
~~~

Index này không phải khuyến nghị áp dụng mù quáng: cần xem mọi query patterns, cardinality, index size và write cost. Phải so **explain.executionStats** trên corpus đại diện.

### 6.3. Selectivity thay đổi

Trong test:

~~~text
status="PAID": 10% of documents
~~~

Trong production:

~~~text
status="PAID": 95% of documents
~~~

Index đơn trường status có thể kém hữu ích hơn kỳ vọng. Cần giữ đúng **value frequency distributions, correlations giữa fields và số records mỗi tenant**.

### 6.4. Không có hot keys/tenant skew

Test:

~~~text
100 tenants, 1,000 documents each
~~~

Production:

~~~text
Tenant A: 65% data, 80% QPS
Tenant B: 10% data
Other tenants: remaining 25%
~~~

Uniform random test không tái tạo hot shard, cache pressure và hot document contention.

### 6.5. Document shape quá đơn giản

Test:

~~~javascript
{ _id: 1, userId: 42, value: 100 }
~~~

Production:

~~~javascript
{
  _id: ObjectId("65a000000000000000000001"),
  tenantId: "t-001",
  userId: "u-0042",
  status: "PAID",
  amountCents: NumberLong(99900),
  items: [
    { sku: "SKU-100", quantity: 2, priceCents: 34900 },
    { sku: "SKU-200", quantity: 1, priceCents: 30100 }
  ],
  shipping: { city: "Hanoi", country: "VN" },
  statusHistory: [
    { state: "CREATED", at: ISODate("2026-01-01T00:00:00Z") },
    { state: "PAID", at: ISODate("2026-01-01T00:02:00Z") }
  ],
  createdAt: ISODate("2026-01-01T00:00:00Z")
}
~~~

Arrays, subdocuments, field lengths và multikey index fan-out ảnh hưởng đến storage, cache và update throughput.

### 6.6. Không có concurrency

Test một client:

~~~text
find -> wait -> find -> wait
~~~

Production:

~~~text
200 concurrent clients
80% point reads
10% filtered list queries
8% writes/updates
2% large aggregations
~~~

Concurrency bộc lộ pool waits, CPU contention, cache evictions, disk queueing và replication lag.

### 6.7. Không có long-tail documents

Average order có hai items nhưng 1% orders có 200 items; 5% customers tạo lượng events lớn. Tail distribution có thể chi phối p99 latency, index fan-out và aggregation memory peaks.

### 6.8. Một lần chạy không đủ

Một query nhanh có thể do warm cache, không background writes, không backup/index build, JIT đã warm, local networking hoặc storage đang dùng burst credits.

Đo **repeat runs, warm-up, steady state, cache regimes, p95/p99** và tài nguyên cùng thời điểm.

### 6.9. Dữ liệu nhỏ che chi phí của $lookup

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $limit: 20 }
]);
~~~

Một pipeline chạy trên 100 orders không thể chứng minh chi phí trên hàng chục triệu records. Cần xét cardinality, foreign indexes, early filtering, join candidates, result sizes, pipeline ordering và shard topology.

### 6.10. Nhầm “index có mặt” với “index có ích”

Với 1.000 documents, mọi index đều rất nhỏ. Trong production:

- Index compound có thứ tự fields không phù hợp có thể không hỗ trợ sort.
- Index nhiều fields có thể chiếm nhiều disk/cache và làm writes chậm.
- Query dùng regex không anchored hoặc kiểu dữ liệu không phù hợp có thể ít tận dụng index.
- Một partial index chỉ dùng cho queries thỏa predicate tương ứng.
- Multikey index có những giới hạn và overhead riêng.

Không xây 15 indexes chỉ vì mỗi câu query trong dataset nhỏ có một index tương ứng. Hãy đánh giá workload tổng thể và **write amplification**.

### 6.11. Test query sai kiểu dữ liệu

Production:

~~~javascript
{ customerId: ObjectId("65a000000000000000000001") }
~~~

Test:

~~~javascript
{ customerId: "65a000000000000000000001" }
~~~

String không bằng ObjectId. Benchmark trả 0 results rất nhanh có thể chỉ chứng minh bạn **truy vấn sai kiểu**. Luôn kiểm tra số kết quả và BSON types; không coi 0 ms với zero matches là thành công.

### 6.12. Không có cache churn

Một benchmark liên tục đọc 100 documents giống nhau sẽ đo cache-friendly behavior. Production có người dùng đọc nhiều tenants, reports và time ranges khác nhau, khiến hot pages bị đẩy khỏi cache.

Thiết kế **access distributions**: hot subset, cold subset, random reads và scans có tỷ lệ gần production.

### 6.13. Bảng những điều test nhỏ chưa chứng minh

| Quan sát từ test nhỏ | Không đủ chứng minh |
|---|---|
| 5 ms với 10.000 docs | 5 ms với 50 triệu docs. |
| 0 disk reads | Production working set vừa RAM. |
| COLLSCAN nhanh | Không cần index. |
| Một client đạt 1.000 ops/s | 200 clients cũng đạt tương tự. |
| Import 100 docs nhanh | Import 100 triệu docs không ảnh hưởng replication. |
| Index build 0.2 giây | Build trên production không cần headroom. |
| Không có hot shard | Shard key chịu được tenant skew. |
| Simple documents chạy tốt | Arrays/large docs vẫn tương đương. |
| Mean latency thấp | p99 đáp ứng SLO. |
| Test disk còn trống | Đủ dung lượng cho retention/backup/growth. |
| Zero-result query rất nhanh | Truy vấn đúng dữ liệu thực. |

## 7. Thiết kế bộ dữ liệu benchmark có tính đại diện

Benchmark tốt không nhất thiết là bản sao toàn bộ production, nhưng phải phản ánh những đặc điểm làm thay đổi execution cost.

### 7.1. Năm chiều phải đại diện

| Chiều | Cần mô phỏng |
|---|---|
| **Scale** | Số documents, tổng bytes, index size so với RAM. |
| **Shape** | Fields, types, nested documents, arrays, sizes, p95/p99 length. |
| **Distribution** | Tenant sizes, status frequencies, hot keys, date recency, missing/null. |
| **Access** | Point vs range reads, writes, updates, aggregations, hot/cold mix. |
| **Concurrency** | Clients/threads, arrival rate, batch jobs, long-running operations. |

Đừng dùng 10 triệu documents **đều giống nhau** rồi coi là benchmark đủ lớn: dữ liệu lặp có thể nén cực tốt và có selectivity không thực tế.

### 7.2. Cách lấy phân bố từ production an toàn

Nếu có production metrics, lấy các thống kê đã **ẩn danh/aggregate**:

- Document size buckets (0–1 KiB, 1–4 KiB, 4–16 KiB, ...).
- Số records trên mỗi tenant percentile, tránh xuất tenant IDs nhạy cảm.
- Status frequency và correlations với createdAt/tenant.
- Số elements trong arrays.
- Tỷ lệ records mới/cũ, retention và update frequency.
- Tỷ lệ query types và độ đồng thời.
- Một số hot keys theo cách băm/ẩn danh hợp lệ.

Không copy trực tiếp dữ liệu khách hàng, tokens hay secrets sang laptop hoặc test môi trường ít bảo mật. Synthetic data nên có **hình dạng và phân bố giống**, không cần chứa PII thật.

### 7.3. Chọn dataset theo tỷ lệ working set

Một test quy mô vừa vẫn có thể hữu ích nếu tỉ lệ **hot data/index pages so với cache** gần đúng production.

Ví dụ:

~~~text
Production:
  hot working set 200 GiB / effective cache 50 GiB = 4.0

Representative smaller environment:
  hot working set 20 GiB / effective cache 5 GiB = 4.0
~~~

Tỷ lệ giống nhau không bảo đảm hiệu năng giống nhau: CPU/IOPS/network, concurrency, storage and cache algorithms vẫn khác. Nhưng nó **tốt hơn nhiều** so test 10 MiB nằm hoàn toàn trong RAM khi production cache miss.

### 7.4. Quy mô theo số documents và số distinct values

Một benchmark phải có đủ cardinality để tái tạo query selectivity:

~~~text
documents: 10,000,000
unique customers: 1,000,000
unique tenants: 1,000
status values: 6, skewed frequencies
time range: 2 years
items per order: p50=2, p95=12, p99=40
~~~

Các con số là ví dụ. Một benchmark 10 triệu documents nhưng chỉ có 10 distinct customers không phản ánh hệ thống million-customer.

### 7.5. Tạo hot tenants

Production có thể có một tenant tạo 30% requests, 10 tenants tạo thêm 40% và phần còn lại chia 30%.

Nếu synthetic dataset phân đều 1.000 tenants, khả năng cạnh tranh cache, hotspot và tính phân phối shard key sẽ khác.

Hãy tạo **Zipf-like distribution** hoặc một phân bố weighted tùy telemetry, thay vì sử dụng random uniform mặc định.

### 7.6. Thời gian và retention

Queries thường ưu tiên dữ liệu mới nhất:

~~~text
70% reads -> last 7 days
20% reads -> last 90 days
10% reads -> older history
~~~

Dataset phải có timestamps trải dài qua các giai đoạn và test read filters tương ứng.

Nếu mọi document synthetic có cùng createdAt, index theo date, shard key monotonicity và range queries sẽ không phản ánh thực tế.

### 7.7. Dữ liệu cần có null/missing/edge cases

Thêm tỷ lệ thực tế cho:

- Field không tồn tại.
- Field null.
- Empty arrays.
- Long text.
- Unicode và tiếng Việt.
- Documents có nhiều nested objects.
- Duplicate values.
- Large values ở tail.

Ví dụ một partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  { partialFilterExpression: { status: "PENDING" } }
);
~~~

Chi phí/query behavior phụ thuộc tỷ lệ **PENDING**, không chỉ tổng số records. Nếu test 0% PENDING, benchmark sẽ vô nghĩa cho endpoint này.

### 7.8. Indexes phải đúng như môi trường dự kiến

Một test có data nhưng không có index set production sẽ đo sai. Ngược lại, test tạo quá nhiều indexes không có ở production cũng có write cost khác.

Chuẩn bị:

1. Cùng indexes, key order, partial/sparse/TTL/collation options khi phù hợp.
2. Cùng schema validation quan trọng.
3. Cùng sharding setup/zone constraints khi đang đánh giá sharded cluster.
4. Cùng read/write concern về mặt business semantics.
5. Cùng MongoDB/driver version hoặc ghi rõ khác biệt.

### 7.9. Nén dữ liệu phải tự nhiên

Nếu mọi record đều dùng:

~~~javascript
{ payload: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" }
~~~

compression có thể quá cao. Nếu dùng random bytes hoàn toàn thì compression gần như không có. Cả hai đều có thể không giống data thật.

Hãy dùng strings/arrays/field variation tương ứng với production; **đo actual compressed storage và index sizes**, không suy theo số ký tự synthetic.

### 7.10. Tách dữ liệu benchmark và dữ liệu chuẩn dùng cho correctness

Một tập nhỏ có thể dùng cho **unit tests, contract tests và kiểm tra tính đúng**. Một tập lớn đại diện mới phục vụ **performance/capacity evaluation**.

Không bắt mọi test CI phải seed 100 triệu documents. Có thể thiết kế các tầng:

~~~text
Unit / contract:
  Small deterministic fixtures, milliseconds.

Functional integration:
  Moderate dataset, real MongoDB, correctness.

Performance integration:
  Millions of representative documents, indexes.

Capacity / stress:
  Production-like data-to-cache ratio,
  traffic distribution and concurrency.
~~~

Không thay mục tiêu test nhỏ bằng benchmark lớn: **hai loại test giải quyết hai câu hỏi khác nhau**.

## 8. Thiết kế workload benchmark có thể so sánh

### 8.1. Workload matrix

Một bộ test cho orders:

| Loại thao tác | Tỷ lệ | Pattern | Điều cần đo |
|---|---:|---|---|
| Get order by _id | 40% | Point read | p50/p95/p99, cache hits. |
| List recent orders by customer | 25% | Filter + sort + limit | Index scan, pages read, latency. |
| Create order | 15% | Insert + indexes | Write throughput, replication lag. |
| Update status | 10% | Update indexed/unindexed fields | Write amp, locks/queues. |
| Search/report by date/status | 8% | Range/group/sort | CPU, memory, spill, I/O. |
| Batch reconciliation | 2% | Background aggregation | Tail latency impact. |

Tỷ lệ cần lấy từ telemetry thực tế và có thể tách **peak scenario** khác steady state.

### 8.2. Arrival rate vs fixed concurrency

Hai kiểu benchmark:

- **Closed-loop:** mỗi client gửi request tiếp theo sau khi request trước hoàn thành.
- **Open-loop:** hệ thống phát requests theo arrival rate được đặt trước, kể cả khi service chậm.

Closed-loop có thể làm throughput giảm khi latency tăng và che một phần overload (coordinated omission). Open-loop mô phỏng arrival load tốt hơn trong một số mục tiêu nhưng cần kiểm soát backlog và thời gian chờ.

**Báo cáo rõ mô hình tải**, không chỉ ghi “100 users”.

### 8.3. Ramp-up, steady-state và spike

~~~text
0–5 min:    warm-up
5–15 min:   200 ops/sec
15–25 min:  500 ops/sec
25–35 min:  1,000 ops/sec
35–45 min:  1,500 ops/sec
45–50 min:  spike to 3,000 ops/sec
50–60 min:  recovery/steady-state
~~~

Số và durations là kịch bản minh họa. Mục tiêu là tìm:

- Mức tải bền vững đạt SLO.
- Điểm p95/p99 bắt đầu tăng mạnh.
- Queue/pool wait và disk/CPU saturation.
- Khả năng phục hồi sau spike.

Không chỉ báo throughput cao nhất khi hệ thống đang trả nhiều lỗi.

### 8.4. Cache warm vs cold

Hai kịch bản:

| Kịch bản | Mục đích |
|---|---|
| **Warm cache** | Đo hiệu năng sau warm-up với hot working set. |
| **Cold/mixed cache** | Xem độ nhạy khi không có đủ cached pages hoặc workload đổi. |

Không restart MongoDB production hoặc xóa hệ thống cache để thử “cold cache”. Trong môi trường lab có thể tạo controlled cold workload, thay query ranges hoặc khởi tạo instance riêng; ghi rõ cách thực hiện để kết quả có thể lặp lại.

### 8.5. Query correctness là tiền đề

Với mỗi operation:

~~~text
expected result count / invariants
actual result count
error category
query/transaction semantic correctness
latency
resource consumption
~~~

Một query rất nhanh nhưng trả sai tenant hoặc zero results do sai kiểu dữ liệu **không phải một kết quả benchmark thành công**.

### 8.6. Đo latency distribution

Thu thập:

- p50.
- p90/p95.
- p99 (cần đủ số samples).
- Max hoặc slow outliers.
- Timeouts/errors.
- Queue time vs service time nếu có thể tách.

Một dashboard chỉ hiển thị **average latency** dễ che tail; 1% queries mất nhiều giây có thể tác động đáng kể tới người dùng.

### 8.7. Không trộn load generator bottleneck với database bottleneck

Nếu load generator CPU 100% hoặc network link của máy benchmark đã đầy, QPS đo được không phản ánh MongoDB maximum throughput.

Theo dõi:

~~~text
Load generator CPU and memory
Client connection pool waits
Network on generator and database
MongoDB server CPU/cache/disk
Application latency and error rate
~~~

Sử dụng nhiều generators hoặc tách load injector khỏi database nếu cần, và ghi topology để biết nút thắt.

### 8.8. So sánh trên cùng điều kiện

Khi so Index A với Index B:

- Cùng corpus/number of documents.
- Cùng workload mix và query parameter distribution.
- Cùng hardware/version.
- Cùng warming policy.
- Cùng concurrency/arrival rate.
- Không có background migrations ngoài ý muốn.
- Có nhiều lần chạy để kiểm soát variance.

Không kết luận “Index B nhanh hơn 50%” nếu lần thử B được chạy sau khi OS cache đã nóng còn A là cold run.

### 8.9. Stress, soak và failure tests

- **Stress:** tăng tải tới khi vượt SLO hoặc thấy giới hạn, trong môi trường được phép.
- **Soak:** chạy dài để phát hiện memory growth, queue buildup, fragmentation, oplog/TTL backlog.
- **Failure/recovery:** mô phỏng node restart/election/network degradation trong lab để đánh giá availability và recovery.

Không gây failover hoặc disk exhaustion trên production chỉ để lấy số liệu benchmark.

### 8.10. Kết quả benchmark phải có bối cảnh

Một báo cáo tối thiểu:

~~~text
Dataset: 25,000,000 docs; 85 GiB logical; indexes 32 GiB
Node: 8 vCPU, 32 GiB RAM, SSD IOPS tier specified
Topology: replica set 3 members
MongoDB + driver version: recorded
Workload: 50% reads, 30% writes, 20% aggregate
Traffic model: open-loop 1,200 requests/sec
Duration: 30 min steady state after warm-up
P95 application latency: measured
P99 application latency: measured
Error/timeouts: measured
CPU/disk/cache/replication: measured
Conclusion: passes/fails defined SLO and headroom requirement
~~~

Không đưa một con số throughput lên slide mà không có data shape, resource baseline, errors và SLO.

## 9. Đo MongoDB thực tế bằng mongosh và monitoring

Những ví dụ ở đây dành cho môi trường được phép quan sát. Một số commands yêu cầu **clusterMonitor** hoặc privileges tương ứng. Đầu ra và metric field names thay đổi theo MongoDB version, storage engine và topology.

### 9.1. Đo số documents và kích thước collection

Trong mongosh:

~~~javascript
use commerce

db.orders.estimatedDocumentCount();
~~~

**estimatedDocumentCount()** thích hợp khi cần count ước lượng từ metadata; không đồng nghĩa chính xác với **countDocuments({})** trong mọi tình huống, đặc biệt khi sharded cluster/migrations đang diễn ra.

Có thể dùng collection stats:

~~~javascript
db.orders.stats({ scale: 1024 * 1024 });
~~~

Một số phiên bản công cụ có cách hiển thị khác; đặc biệt cần hiểu các fields như **size, storageSize, totalIndexSize, indexSizes, count** và đơn vị scaling.

### 9.2. $collStats

~~~javascript
db.orders.aggregate([
  {
    $collStats: {
      storageStats: { scale: 1048576 },
      count: {}
    }
  }
]);
~~~

Kết quả có thể chứa per-shard stats tùy deployment và version. **storageStats.storageSize không luôn đồng nghĩa owned logical bytes**; có thể khác dataSize do nén, allocation và orphan effects.

Không dùng sum của các metrics có definition khác nhau để lập kế hoạch disk.

### 9.3. Xem indexes

~~~javascript
db.orders.getIndexes();
~~~

Đối chiếu:

- Có bao nhiêu indexes?
- Những queries chính dùng chúng?
- Indexes compound có key order phù hợp?
- Có index unique, partial, TTL, multikey?
- Collation và filter expression có phù hợp?

**Không xóa index trên production chỉ vì một benchmark nhỏ không sử dụng nó.** Cần xem toàn bộ workload theo thời gian, báo cáo, background jobs và constraints.

### 9.4. $indexStats để quan sát usage

~~~javascript
db.orders.aggregate([
  { $indexStats: {} },
  {
    $project: {
      name: 1,
      key: 1,
      accesses: 1
    }
  }
]);
~~~

Trường **accesses.ops** biểu diễn số hoạt động index access theo nguồn/server semantics kể từ thời điểm thống kê, không phải “số queries duy nhất” hoặc lượng bytes được truy cập. Counters có thể reset khi node restart/reindex và cần quan sát đủ dài để thấy các jobs hiếm.

### 9.5. explain trên query quan trọng

~~~javascript
db.orders.find({
  customerId: "C-100",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

Xem những thành phần như:

- Winning plan.
- **IXSCAN** hay **COLLSCAN**.
- **totalKeysExamined**.
- **totalDocsExamined**.
- **nReturned**.
- Execution time và các stages.
- Sort có dùng index hay cần stage bổ sung.
- Shards targeted nếu collection sharded.

Đừng chỉ nhìn executionTimeMillis rồi bỏ qua **nReturned**. Một query trả 0 records có thể nhanh vì chưa thật sự đo đúng data path.

### 9.6. Ví dụ so chỉ số hiệu quả của query

~~~text
Plan A:
  nReturned = 20
  totalDocsExamined = 1,000,000
  totalKeysExamined = 0

Plan B:
  nReturned = 20
  totalDocsExamined = 20
  totalKeysExamined = 20
~~~

Plan B thường cho thấy index targeting tốt hơn trong ví dụ này. Nhưng cần thêm write/index cost và workload mix để chọn thiết kế tổng thể.

Một ratio:

~~~text
documentsExaminedPerResult =
  totalDocsExamined / max(nReturned, 1)
~~~

Giúp phát hiện scan amplification, nhưng khi query dùng count/group hoặc trả 0 results, cách diễn giải khác. Không đặt một ngưỡng cứng cho mọi query types.

### 9.7. serverStatus

Trên một mongod member được phép:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptime: s.uptime,
  opcounters: s.opcounters,
  connections: s.connections,
  network: s.network,
  opLatencies: s.opLatencies,
  wiredTigerCache: s.wiredTiger ? s.wiredTiger.cache : undefined
});
~~~

**serverStatus** có nhiều counters/gauges. Không lấy raw counter tích lũy làm QPS:

~~~text
ops(t0) = 1,000,000
ops(t1) = 1,060,000
Δtime = 60 s

rate = (1,060,000 - 1,000,000)/60
     = 1,000 ops/s
~~~

Theo dõi resets khi mongod restart; mongos và mongod member trả metrics khác nhau.

### 9.8. DB stats

~~~javascript
db.stats(1024 * 1024);
~~~

Lệnh cung cấp thống kê database theo version/engine, không tự thay thế các chỉ số per-collection, per-shard hoặc per-replica-member.

### 9.9. Query profiler và slow operations

Database profiler có thể giúp tìm slow queries, nhưng **bật profiler hoặc tăng mức profiler là thay đổi có overhead**. Chỉ điều chỉnh trên production với quyền và quy trình đã phê duyệt.

Nếu profiling đã được bật theo chính sách:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    millis: 1,
    ns: 1,
    planSummary: 1,
    keysExamined: 1,
    docsExamined: 1
  }
).sort({ ts: -1 }).limit(20);
~~~

Thống kê profiler phụ thuộc version/thiết lập, có thể chứa nội dung query nhạy cảm và không phải mọi workload đều được ghi. Dùng sampling và data retention phù hợp để không làm lộ PII.

### 9.10. current operations

Một số công cụ có thể dùng **$currentOp** hoặc lệnh currentOp theo version để điều tra operations đang chạy, lock waits và long-running jobs. Output ngắn hạn và có thể rất nhiều; không chạy kiểu lấy toàn bộ không kiểm soát trên cluster lớn.

Ưu tiên:

- Slow query dashboards.
- Aggregated query latency metrics.
- Profiler/log sampling.
- Query explain có kiểm soát.
- Driver command monitoring với bảo vệ dữ liệu nhạy cảm.

### 9.11. Mongostat, mongotop và Atlas metrics

**mongostat** giúp quan sát các counter/rate theo thời gian; **mongotop** giúp xem activity theo collection trên mongod trong những điều kiện phù hợp.

MongoDB Atlas/Ops Manager hoặc monitoring stack có thể cung cấp charts:

- CPU, memory, disk capacity/IOPS/latency.
- Opcounters và network traffic.
- WiredTiger cache/evictions.
- Connections, queues.
- Replication lag, oplog.
- Storage/index growth.
- Query latency và alerts.

Không nhầm metric có sẵn ở một sản phẩm quản lý với field mặc định trong vanilla serverStatus; tên/độ phân giải tùy deployment.

### 9.12. Khi dùng sharding

Capacity planning theo shards cần đo:

~~~text
ownedDataBytes by shard
diskFreeBytes by member
read/write QPS by shard
balancer migrations and failures
zone constraints
hot shard-key values
application p95/p99
~~~

Sharded cluster có tổng disk dư nhưng một shard cạn tài nguyên vẫn có nguy cơ mất SLO.

## 10. Chuẩn bị bộ dữ liệu lab lớn hơn toy dataset

Một ví dụ **mongosh seed generator** dành riêng cho **database lab**. Nó tạo orders với tenants/statuses/createdAt/items có phân bố thay vì 100 bản ghi giống nhau.

**Không chạy script trên production.** Tạo database/cluster thử nghiệm riêng, giới hạn số documents và cân nhắc disk/CPU trước khi tăng scale.

### 10.1. Dataset generator bằng mongosh

~~~javascript
// Run only on an isolated benchmark MongoDB deployment.
const benchDb = db.getSiblingDB("perf_capacity_lab");
const orders = benchDb.getCollection("orders_benchmark");

// Change this deliberately for larger experiments.
const TOTAL_DOCUMENTS = 20000;
const BATCH_SIZE = 500;
const BASE_TIME = Date.UTC(2026, 0, 1);
const SPAN_DAYS = 365;
const ONE_DAY_MS = 86400000;

// The script refuses to append data to an existing test collection.
if (orders.estimatedDocumentCount() !== 0) {
  throw new Error(
    "orders_benchmark is not empty; use a fresh lab collection"
  );
}

let state = 20261114;
function nextRandom() {
  // Deterministic, non-cryptographic pseudorandom numbers.
  state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
  return state / 4294967296;
}

function pickTenant() {
  const x = nextRandom();
  if (x < 0.30) return "tenant-hot";
  if (x < 0.50) return "tenant-large-2";
  return "tenant-" + Math.floor(nextRandom() * 400);
}

function pickStatus() {
  const x = nextRandom();
  if (x < 0.55) return "PAID";
  if (x < 0.80) return "SHIPPED";
  if (x < 0.92) return "PENDING";
  if (x < 0.98) return "CANCELLED";
  return "REFUNDED";
}

function pickItemCount() {
  const x = nextRandom();
  if (x < 0.70) return 1 + Math.floor(nextRandom() * 3);
  if (x < 0.95) return 4 + Math.floor(nextRandom() * 9);
  return 13 + Math.floor(nextRandom() * 28);
}

function buildOrder(i) {
  const itemCount = pickItemCount();
  const items = [];
  let totalCents = 0;

  for (let j = 0; j < itemCount; j++) {
    const skuNumber = Math.floor(nextRandom() * 100000);
    const price = 1000 + Math.floor(nextRandom() * 50000);
    const quantity = 1 + Math.floor(nextRandom() * 3);

    items.push({
      sku: "SKU-" + skuNumber,
      quantity: quantity,
      priceCents: price,
      label: "product-" + skuNumber + "-variant-" + (j % 7)
    });
    totalCents += price * quantity;
  }

  const dayOffset = Math.floor(nextRandom() * SPAN_DAYS);
  const at = new Date(BASE_TIME + dayOffset * ONE_DAY_MS);
  const tenant = pickTenant();

  return {
    _id: "BENCH-" + String(i).padStart(10, "0"),
    tenantId: tenant,
    customerId: "C-" + Math.floor(nextRandom() * 300000),
    status: pickStatus(),
    createdAt: at,
    amountCents: totalCents,
    items: items,
    shipping: {
      country: "VN",
      city: ["Hanoi", "Danang", "HCMC"][
        Math.floor(nextRandom() * 3)
      ]
    }
  };
}

for (let offset = 0; offset < TOTAL_DOCUMENTS; offset += BATCH_SIZE) {
  const batch = [];
  const end = Math.min(offset + BATCH_SIZE, TOTAL_DOCUMENTS);

  for (let i = offset; i < end; i++) {
    batch.push(buildOrder(i));
  }

  orders.insertMany(batch, { ordered: true });
}

print("Inserted " + TOTAL_DOCUMENTS + " synthetic documents");
~~~

Những số được chọn nhằm **minh họa phân bố**, không phải dữ liệu có nguồn từ một hệ thống thực. Script mặc định chỉ 20.000 records để dễ khởi đầu; tăng lên hàng triệu chỉ khi môi trường và quota cho phép.

### 10.2. Vì sao generator này tốt hơn insert cùng một document?

Nó có:

- Tenant hot/large so với tenants nhỏ.
- Status values không uniform.
- Số items khác nhau, kể cả long tail.
- CreatedAt trải qua một khoảng thời gian.
- Nhiều customer IDs/SKU values.
- Nested fields và arrays.
- Deterministic random để tái tạo theo cùng seed.

Tuy vậy nó **chưa đủ là production-like** nếu actual document shapes, value correlations, update patterns, sizes và workloads khác xa. Đây là điểm xuất phát để điều chỉnh theo telemetry.

### 10.3. Tạo indexes phục vụ ví dụ

~~~javascript
orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});

orders.createIndex({
  customerId: 1,
  createdAt: -1
});
~~~

Nên đo **index size, build time và insert throughput** sau khi tạo indexes, và so với cách tạo indexes trước khi ingest. Không kết luận cách nào luôn tốt nhất cho mọi production write path.

### 10.4. Quan sát dataset lab

~~~javascript
print("Count: " + orders.countDocuments({}));

orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);

orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } },
  { $limit: 10 }
]);
~~~

Sau khi xác định distribution, hãy chạy workloads có selectivity tương ứng. **Đây là bước thiết kế test**, không phải chứng minh tự động rằng synthetic data đã giống production.

## 11. So sánh query plans trên corpus lớn

### 11.1. Điểm truy vấn có index ứng viên

Với index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

chạy:

~~~javascript
orders.find({
  tenantId: "tenant-hot",
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(50).explain("executionStats");
~~~

Đánh giá:

- Có IXSCAN phù hợp index key order không?
- Keys/docs examined bao nhiêu?
- Có SORT stage phải xử lý thêm không?
- Returned documents có đúng tenant/status?
- Latency thế nào với hot tenant so với tenant hiếm?

**Không** lấy một execution plan được cache trong test nhỏ rồi giả định planner/working set production luôn giống.

### 11.2. Query thiếu index prefix

~~~javascript
orders.find({
  status: "PAID"
}).sort({
  createdAt: -1
}).limit(50).explain("executionStats");
~~~

Index bắt đầu bằng tenantId không nhất thiết hiệu quả cho mọi query chỉ có status/createdAt; cần xem MongoDB planner và query shape.

Thay vì thêm index mới ngay, cần hỏi:

- API này có phải luôn cần tenantId nhưng client quên truyền?
- Truy vấn cross-tenant có hợp lệ theo security/business?
- Một index thứ hai có đủ read benefits để bù write/storage overhead?
- Frequency của query so với truy vấn khác?

### 11.3. Dữ liệu nhỏ làm index decision khác

Một test có 100 orders:

~~~text
COLLSCAN 100 docs -> 1 ms
IXSCAN 10 keys -> 1 ms
~~~

Không thể suy hai plans tương đương trên 50 triệu orders. Khi dữ liệu lớn, số docs examined và I/O trở nên phân biệt rõ, đặc biệt khi working set vượt cache.

### 11.4. Query có kết quả không đều

Test cùng một query shape trên:

~~~text
tenant-hot:       millions of records
tenant-large-2:   hundreds of thousands
tenant-123:       small number of records
~~~

Lưu ý:

- Hot tenant có nhiều pages cần đọc.
- Ranges và sort/limit behavior khác nhau.
- Kết quả nReturned có thể giống 50 nhưng work trước khi lấy top 50 khác.
- Query plan caching và parameter distribution có thể ảnh hưởng variation.

Nên đo **per-query-shape distributions**, không chỉ một query parameter đẹp.

### 11.5. $group và spill

~~~javascript
orders.aggregate([
  {
    $match: {
      tenantId: "tenant-hot",
      createdAt: {
        $gte: ISODate("2026-06-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$status",
      total: { $sum: "$amountCents" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1 } }
], { allowDiskUse: true });
~~~

**allowDiskUse** cho phép một số pipeline stages dùng temporary disk khi đáp ứng điều kiện của server/version; không làm query miễn phí hoặc tránh mọi memory limit. Đo spills, temp I/O và p95 trong khi ứng dụng vẫn có traffic.

### 11.6. $lookup và cardinality

Nếu customers collection có index theo _id, join point lookup có thể khác join với foreignField không index. Với data lớn và shards khác nhau, join cost có thể vượt dự đoán từ vài trăm documents.

Hãy so:

~~~text
Number of outer documents
Foreign index availability
Average and p99 matches per join key
Result document size
Memory/disk spilling
Network cost in sharded cluster
~~~

Không chỉ benchmark query trả 20 orders ở cuối pipeline nếu những stages trước đã xử lý hàng triệu records.

### 11.7. Index không chỉ cải thiện reads

Mỗi additional index tạo chi phí:

- Disk và memory.
- Insert write amplification.
- Update khi indexed fields đổi.
- Index build/rebuild time.
- Backup/restore time.
- Operational complexity.

Đánh giá index trong **mixed workload**, không chỉ một read query đơn lẻ.

### 11.8. TTL và cleanup

Nếu dùng TTL cho log/session:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

Với lượng documents hết hạn cao, TTL deletes tạo write load và oplog entries. Dự trù purge backlog và I/O theo tốc độ hết hạn; **TTL cleanup không có thời điểm chính xác tuyệt đối**.

Đừng lấy bộ test chỉ có documents chưa hết hạn để kết luận TTL deletion không ảnh hưởng throughput.

## 12. Worked example: dự báo dung lượng cho một collection

Giả sử hệ thống có:

~~~text
Current retained documents:       30,000,000
Average BSON size:                2.5 KiB
Net new documents/day:            250,000
Forecast horizon:                 365 days
Index size observed at baseline:  45 GiB
Storage compression ratio:        measured, not assumed
Replica set:                      3 data-bearing members
~~~

### 12.1. Dự báo số documents

Nếu không có deletes/retention và growth ổn định:

~~~text
documentsAfterOneYear
  = 30,000,000 + 250,000 * 365
  = 121,250,000
~~~

### 12.2. Dự báo logical bytes

~~~text
logicalBytes
  = 121,250,000 * 2,560 bytes
  = 310,400,000,000 bytes
  ≈ 289.1 GiB
~~~

Con số này chưa bao gồm tất cả indexes, oplog, overhead và những document updates làm document lớn thêm.

### 12.3. Không lấy index ratio cố định một cách vô điều kiện

Nếu baseline:

~~~text
current logical data ≈ 71.5 GiB
current index size  = 45 GiB
~~~

Tỷ lệ index/logical hiện tại xấp xỉ 0.63. Nhưng index growth tương lai còn phụ thuộc:

- Cardinality tăng.
- Key size tăng hay giảm.
- Multikey arrays thay đổi.
- Index definitions được thêm/bớt.
- Compression và storage engine behavior.

Có thể dùng ratio đo được làm **giả định dự báo ban đầu** với khoảng sai số, rồi kiểm tra khi corpus lớn hơn; không biến 0.63 thành hằng số bất biến.

### 12.4. Physical storage theo mô hình kịch bản

Giả sử cho bài toán minh họa:

~~~text
Projected logical BSON: 289 GiB
Scenario compression factor: 0.65
Estimated collection storage: 188 GiB
Estimated index storage: 180 GiB
Other allocated/oplog overhead: 50 GiB
------------------------------------
Estimated per-member storage: 418 GiB
~~~

Các thành phần là **ước lượng**, không phải kết quả từ một deployment cụ thể. Cần dùng metrics thực để điều chỉnh.

Nếu yêu cầu **30% operational free headroom** theo chính sách ví dụ:

~~~text
Required usable volume capacity
  ≈ 418 GiB / (1 - 0.30)
  ≈ 597 GiB per data-bearing member
~~~

Với ba data-bearing members:

~~~text
Approximate provisioned volumes:
  597 GiB * 3 = 1,791 GiB
~~~

Trong thực tế nên làm tròn theo storage tiers/provider offerings, có kế hoạch oplog/index build/migration phù hợp và dự trù backups riêng.

**30% chỉ là giả định minh họa**; thay đổi tỷ lệ khi có benchmark, retention và SLO đáng tin. Đừng lấy trực tiếp làm quy chuẩn chung.

### 12.5. Capacity cho backup khác live storage

Một replica set có ba bản sao không thay thế backup:

~~~text
Replication:
  protects service availability and copies current state.

Backup:
  supports recovery from deletion, corruption,
  operational mistakes and historical restore.
~~~

Nếu bug xóa 100.000 orders, thao tác xóa cũng có thể được replicate tới secondaries. Phải dự trù snapshot retention, PIT oplog/backup chain, encryption và restore bandwidth độc lập.

### 12.6. Giới hạn mô hình tuyến tính

Mô hình trên chỉ đúng trong giả định:

- Net new documents cố định.
- Average size không đổi.
- Không có giới hạn retention đáng kể.
- Compression/index growth đã được ước lượng.

Nếu tốc độ tăng growth hoặc archive được bật, phải xây lại forecast theo **net retained bytes**, không chỉ lấy documents tạo mới.

## 13. Worked example: khi nào tăng RAM thay vì thêm shard?

Giả sử một replica set có:

~~~text
Total live data:          800 GiB
Frequently read dataset:  70 GiB
Hot indexes:              25 GiB
Current memory:           64 GiB
Disk read IOPS:           high at peak
CPU:                      40% average at peak
p95 read latency:         misses SLO
~~~

Giả thuyết hợp lý: working set thường xuyên vượt available cache, dẫn tới disk reads. Nhưng đây **chưa phải kết luận**: phải kiểm tra WiredTiger eviction metrics, IO latency, query plans, memory allocation và query selectivity.

### 13.1. Hai phương án

**Phương án A — Nâng RAM/node size:**

- Có thể giúp nhiều hot data/index pages nằm cache hơn.
- Ít thay đổi topology.
- Cần kiểm tra khả năng upgrade/failover và giá.

**Phương án B — Thêm shards:**

- Phân phối data/workload nếu shard key tốt.
- Cần mongos/CSRS/balancer và migration.
- Tăng operational cost và complexity.
- Query cross-shard/scatter-gather vẫn có thể tốn nhiều.

Nếu bottleneck chính là cache và workload còn vừa một replica set mạnh hơn, **phương án A có thể đơn giản hơn**. Nếu write throughput/storage growth sắp vượt giới hạn một node, sharding có thể đáng cân nhắc.

### 13.2. Biến quyết định

| Điều kiện | Có xu hướng ủng hộ |
|---|---|
| CPU/disk còn headroom, cache misses lớn | Xem tăng RAM hoặc giảm working set. |
| Dataset growth vượt node size kinh tế | Xem sharding/retention. |
| Writes có thể phân phối theo shard key tốt | Sharding có cơ sở hơn. |
| Một hot key tạo phần lớn writes | Sửa shard-key/workload trước. |
| Nhiều cross-shard analytics | Cân nhắc query design/analytics architecture. |
| Nhu cầu operational đơn giản | Scale-up có lợi thế khi còn đủ. |

### 13.3. Kết luận phải dựa trên experiment

Thử **cùng workload và corpus** ở cấu hình 64 GiB vs RAM lớn hơn; đo cache/IOPS/p95 và cost. Đồng thời mô phỏng sharding trong môi trường riêng nếu đó là phương án thực tế.

Không chọn theo cảm giác “sharding sẽ luôn nhanh hơn” hoặc “RAM càng lớn càng tốt”.

## 14. Java Sync Driver: benchmark đọc với nhiều threads

Ví dụ dưới đây thực hiện **read-only queries giới hạn** trên collection lab đã seed, dùng một MongoClient chung và đo latency ở client.

**Không chạy trên production.** Công cụ này chỉ minh họa cách thu samples, không thay thế load generator có open-loop arrival rate, soak, error reporting và resource instrumentation.

### 14.1. Một workload Java có giới hạn

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicInteger;

public final class MongoReadBenchmark {
    private static final int THREADS = 8;
    private static final int OPS_PER_THREAD = 200;

    private static double percentileMillis(
            List<Long> sortedNanos,
            double quantile) {
        if (sortedNanos.isEmpty()) {
            return Double.NaN;
        }
        int index = Math.max(0,
                (int) Math.ceil(sortedNanos.size() * quantile) - 1);
        return sortedNanos.get(index) / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_BENCHMARK_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_BENCHMARK_URI is required for lab");
        }

        List<Long> latencies =
                Collections.synchronizedList(new ArrayList<>());
        AtomicInteger errors = new AtomicInteger();
        AtomicInteger returnedDocs = new AtomicInteger();

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                    client.getDatabase("perf_capacity_lab")
                            .getCollection("orders_benchmark");

            ExecutorService executor =
                    Executors.newFixedThreadPool(THREADS);
            List<Future<?>> futures = new ArrayList<>();
            long started = System.nanoTime();

            for (int thread = 0; thread < THREADS; thread++) {
                Callable<Void> task = () -> {
                    for (int i = 0; i < OPS_PER_THREAD; i++) {
                        boolean hot = ThreadLocalRandom.current()
                                .nextDouble() < 0.7;
                        String tenant = hot
                                ? "tenant-hot"
                                : "tenant-" + ThreadLocalRandom.current()
                                        .nextInt(400);

                        long operationStart = System.nanoTime();
                        try {
                            List<Document> result = orders.find(
                                    Filters.and(
                                            Filters.eq("tenantId", tenant),
                                            Filters.eq("status", "PAID")
                                    )
                            ).sort(Sorts.descending("createdAt"))
                             .limit(20)
                             .into(new ArrayList<>());

                            returnedDocs.addAndGet(result.size());
                            latencies.add(
                                    System.nanoTime() - operationStart);
                        } catch (RuntimeException ex) {
                            errors.incrementAndGet();
                        }
                    }
                    return null;
                };
                futures.add(executor.submit(task));
            }

            try {
                for (Future<?> future : futures) {
                    future.get();
                }
            } finally {
                executor.shutdown();
                if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            }

            double seconds = (System.nanoTime() - started)
                    / 1_000_000_000.0;
            Collections.sort(latencies);

            int attempted = THREADS * OPS_PER_THREAD;
            System.out.printf(
                    "attempted=%d errors=%d resultDocs=%d%n",
                    attempted, errors.get(), returnedDocs.get());
            System.out.printf("attemptedOpsPerSec=%.1f%n",
                    attempted / seconds);
            System.out.printf("p50=%.2fms p95=%.2fms%n",
                    percentileMillis(latencies, 0.50),
                    percentileMillis(latencies, 0.95));
        }
    }
}
~~~

### 14.2. Giới hạn của đoạn code này

1. Đo client-side operation elapsed time, chưa đo toàn bộ HTTP request.
2. Là **closed-loop workload**: mỗi thread đợi query trước xong mới gửi tiếp.
3. Chưa có warm-up tách riêng, arrival rate cố định, soak hoặc failure testing.
4. 1.600 operations là quá ít cho p99 đáng tin; cần nhiều samples.
5. Exception được đếm nhưng chưa phân loại timeout/network/pool error.
6. attemptedOpsPerSec **tính cả failures**, không phải successful throughput.
7. Chưa có concurrent writes hay resource metrics.
8. Lựa chọn 70% hot-tenant access là giả định minh họa.

Để đánh giá capacity cần mở rộng workload mix, tăng số samples và đo **CPU, disk, cache, network, replica lag** đồng thời.

### 14.3. Đừng tạo MongoClient mới mỗi operation

**MongoClient được thiết kế để dùng chung và có connection pooling**. Khởi tạo client mỗi query làm tăng connection/authentication/setup overhead, khiến benchmark khác ứng dụng thật.

### 14.4. Timeout và cancellation

Với concurrent workload, phải đo:

~~~text
successful operations
timeouts
pool checkout failures
server errors
client cancellations
~~~

Không nâng throughput bằng cách bỏ qua errors. Nếu 40% requests timeout, số attempted requests cao không phải benchmark đạt SLO.

## 15. Spring Boot/Spring Data: đo ở application boundary

Repository/MongoTemplate calls có overhead mapping, connection pool, service logic và network.

### 15.1. Database latency khác HTTP latency

~~~text
HTTP latency
  = gateway/proxy
    + authentication/authorization
    + application processing
    + driver pool wait / network
    + MongoDB execution
    + response serialization
~~~

Query MongoDB 10 ms không bảo đảm API trả trong 10 ms. Cần đo **DB operation latency** để tìm query/index bottleneck và **end-to-end latency** để xác nhận SLO người dùng.

### 15.2. Micrometer Timer

Spring Boot có thể thu HTTP/JVM/pool metrics theo cấu hình và phiên bản. Ví dụ tạo một Timer cho operation:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedOrderQuery {
    private final MongoTemplate mongoTemplate;
    private final Timer timer;

    public InstrumentedOrderQuery(
            MongoTemplate mongoTemplate,
            MeterRegistry registry) {
        this.mongoTemplate = mongoTemplate;
        this.timer = Timer.builder("app.orders.query.duration")
                .description("Duration of a MongoDB order query")
                .tag("operation", "countByTenant")
                .register(registry);
    }

    public long countByTenant(String tenantId) {
        return timer.record(() ->
                mongoTemplate.getCollection("orders")
                        .countDocuments(
                                new Document("tenantId", tenantId)
                        )
        );
    }
}
~~~

Ví dụ instrumentation, **không** khuyến nghị chạy countDocuments trên collection lớn cho mọi HTTP request. Phải đo tần suất/chi phí của operation.

### 15.3. Low-cardinality metrics labels

Nên:

~~~text
operation="listRecentOrders"
collection="orders"
environment="benchmark"
~~~

Tránh:

~~~text
customerId="C-182763847"
orderId="O-890127341"
rawQuery="..."
~~~

Labels triệu giá trị gây **metrics cardinality explosion** và nguy cơ lộ dữ liệu. Dùng query shape/template được kiểm soát.

### 15.4. Command monitoring và tracing

MongoDB Java Driver hỗ trợ command monitoring và integrations tùy version. Khi instrument:

- Không ghi raw BSON documents chứa PII/secrets.
- Tách client pool wait và DB execution nếu có thể.
- Sample dữ liệu phù hợp traffic.
- Gắn correlation ID, service name và operation shape.
- Xem overhead của instrumentation trong benchmark.

### 15.5. Pagination là một biến capacity

~~~javascript
db.orders.find({ tenantId: "tenant-hot" })
  .sort({ createdAt: -1 })
  .skip(100000)
  .limit(20);
~~~

Deep pagination bằng skip lớn có thể tốn nhiều hơn trang đầu dù index tốt. Cân nhắc **keyset/cursor pagination** với sort fields có stable unique tie-breaker và filter đúng scope.

Không chỉ benchmark trang đầu tiên.

## 16. Capacity planning gắn với SLO và growth triggers

Một capacity plan hữu ích phải chỉ rõ **khi nào cần hành động**, không chỉ dự báo số GiB.

### 16.1. Targets và early warnings

| Metric | Hiện tại | Target / SLO | Early-warning trigger |
|---|---|---|---|
| Read p95 | Đo | Theo yêu cầu sản phẩm | Trend tăng, gần vi phạm SLO. |
| Write p95 | Đo | Theo yêu cầu sản phẩm | P95 tăng cùng queues/IOPS. |
| Error rate | Đo | Trong error budget | Sustained failures. |
| Disk free | Đo | Đủ operational headroom | Runway dưới lead time. |
| CPU saturation | Đo | Còn burst headroom | Bão hòa kéo dài kèm latency. |
| Cache eviction/disk reads | Đo | Stable baseline | Tăng cùng tail latency. |
| Replication lag | Đo | Theo consistency target | Vượt ngưỡng theo member. |
| Backup age/restore test | Đo | Đáp ứng RPO/RTO | Backup stale hoặc restore drill fail. |

Các targets là **của hệ thống cụ thể**, không phải một bộ ngưỡng chung do MongoDB áp dụng.

### 16.2. Forecast runway và lead time

Giả sử:

~~~text
Usable free space: 480 GiB
Net storage growth: 20 GiB/day
Expected runway: 480 / 20 = 24 days
~~~

Nếu cần 14 ngày để duyệt, provision, test và rollout nâng cấp, runway 24 ngày có thể thiếu buffer cho growth spikes.

~~~text
Trigger resource expansion when:
  estimatedRunwayDays
  <= provisioningLeadTimeDays + safetyBufferDays
~~~

Runway là ước lượng: retention, migrations, batch import và hardware scaling có thể thay đổi tốc độ tăng. Dùng rolling trends và điều chỉnh khi có sự kiện bất thường.

### 16.3. Mỗi tài nguyên có runway riêng

~~~text
Disk runway:         30 days
CPU runway:          90 days
IOPS runway:          7 days
Network runway:     150 days
~~~

Bottleneck gần nhất là **IOPS**, không phải dung lượng disk. Tăng storage bytes nếu vẫn giữ cùng IOPS tier có thể không cải thiện SLO.

### 16.4. Forecast theo mùa vụ

~~~text
Normal:      1,000 writes/sec
Campaign:    5,000 writes/sec
Flash peak: 15,000 writes/sec
~~~

Cần biết:

- Peak kéo dài 30 giây hay 6 giờ?
- Write concern/retries và indexing overhead?
- Có queue/buffering hay bắt buộc realtime?
- Replication lag/consumer backlog tăng thế nào?
- Có giảm tải được qua backpressure hoặc batching?

Nếu peak ngắn và có queue, giải pháp có thể khác workload bắt buộc xử lý mọi write ngay.

### 16.5. Không chỉ xem trung bình

~~~text
Average CPU: 40%
Peak CPU: 98% for 20 minutes
Read p95 misses SLO during peak
~~~

Average CPU 40% không chứng minh hệ thống đủ capacity. Hãy dùng rolling peaks, duration, p95/p99 và error budgets.

### 16.6. Theo collection/tenant

~~~text
Cluster total growth: 3% per month
Hot tenant growth:  25% per month
~~~

Trên sharded cluster, tenant/range có thể đạt giới hạn trước khi toàn cluster hết capacity. Dự báo theo **tenant cohorts, shard-key ranges và eligible zones** nếu skew lớn.

### 16.7. Recovery time cũng là một giới hạn

RTO bị ảnh hưởng bởi backup download bandwidth, restore/index rebuild throughput, số shards/nodes, replication catch-up và data validation.

Một database 10 TiB với network restore thấp có khả năng phục hồi khác hẳn một database 1 TiB với bandwidth cao, dù cả hai backup mỗi ngày.

### 16.8. Capacity planning phải bao gồm risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Growth forecast quá thấp | Hết disk sớm | High-growth scenario, rolling reforecast. |
| Một tenant đột biến | Hot shard/cache | Workload skew monitoring, shard-key review. |
| Index build làm tăng disk | Capacity incident | Reserve headroom, change window. |
| Backup/restore không đạt RTO | Recovery chậm | Restore drills, throughput sizing. |
| Secondary lag khi writes tăng | Stale reads/resume risk | Oplog planning, I/O headroom. |
| Cloud IOPS throttling | Tail latency tăng | Sustained load test, storage tier sizing. |

## 17. Lập kế hoạch nâng cấp an toàn

### 17.1. Trước thay đổi

1. Xác định bottleneck bằng metrics/traces/explain.
2. Ghi cluster topology, MongoDB/driver version, workload và SLO.
3. Lưu baseline p95/p99, QPS, errors và resources.
4. Dự báo data/index/oplog/operational headroom.
5. So alternatives: query/index, retention, RAM, storage, replicas, shards.
6. Kiểm tra backup, failover và maintenance policy.
7. Định nghĩa tiêu chí thành công, điều kiện rollback và người phê duyệt.

### 17.2. Khi scale up

Theo deployment:

- Có thể cần rolling maintenance hoặc failover.
- Kiểm tra node types, members và supported upgrade procedure.
- Xem storage expansion có tăng IOPS/throughput tương ứng không.
- Theo dõi replication lag và primary elections.
- Không nâng toàn bộ members bằng cách không được vendor hỗ trợ.

### 17.3. Khi thêm shard

Theo dõi:

- Shard đã được mongos nhận diện.
- Zone placement và balancer window.
- Owned bytes/chunks theo collection.
- Migration commit/failure.
- Donor/recipient disk, network, replication headroom.
- Application p95/p99 trong rebalance.

Không kỳ vọng shard mới nhận chính xác 1/N data trong vài phút; workload skew, sizes và zones có thể khiến placement khác.

### 17.4. Khi tạo/đổi index

Dự trù build time ở scale thật, disk/CPU/memory overhead, effects lên writes và version-specific replica set/sharded index build behavior. Index build trên 100 records không chứng minh index build 100 triệu records an toàn trong giờ cao điểm.

### 17.5. Khi bật TTL/archive

Nếu có 500 triệu documents sắp hết retention, không giả định bật TTL là xóa ngay không tải:

- TTL deletes là background work.
- Deletes tạo oplog/write activity.
- Index fragmentation/physical storage có thể thay đổi.
- Có thể cần phased cleanup theo batch và SLO.
- Archive correctness và backup retention cần được tính.

### 17.6. Điều kiện rollback

~~~text
Abort or roll back via supported procedure if:
  application p95 stays above approved threshold
  error rate threatens error budget
  replication lag exceeds safe window
  free disk falls below operational headroom
  index build / migration repeatedly fails
~~~

Rollback phụ thuộc loại change: **resharding hoặc migration lớn không luôn đảo ngược tức thì**. Cần hiểu các commit points và phương án phục hồi chính thức.

### 17.7. Sau thay đổi

So cùng workload:

~~~text
p50, p95, p99
successful throughput
errors/timeouts
CPU/cache/disk/network
replication lag
storage/runway
cost per useful operation
~~~

Nếu node size tăng gấp đôi nhưng successful throughput chỉ tăng 3% và latency không tốt hơn, hãy xem lại giả thuyết bottleneck.

## 18. Tối ưu theo tổng chi phí, không chỉ latency của một query

### 18.1. Tổng chi phí sở hữu

Một MongoDB deployment có những khoản chi:

- Compute: vCPU, RAM cho mongod/mongos/CSRS.
- Storage: data, indexes, oplog, snapshots/retention.
- Provisioned IOPS và throughput tiers.
- Network egress, replication/migration traffic.
- Observability/log storage và support.
- Kỹ thuật vận hành cluster, backup/restore, incident response.
- Chi phí thay đổi schema/index/shard key.

Một index thêm vào có thể giảm 100 ms ở một query hiếm nhưng làm tăng 15% write cost trên mọi inserts. Quyết định tốt phải xem **tần suất query, SLO và tổng workload**, không chỉ một microbenchmark.

### 18.2. Cost per useful operation

Một metric kinh tế:

~~~text
costPerMillionSuccessfulOps
  = totalInfrastructureCostForPeriod
    / successfulOperationsInPeriod
    * 1,000,000
~~~

Nhưng vẫn phải giữ SLO và availability. Nếu giảm cost bằng cách làm p99 latency tăng gấp mười, hiệu quả kinh doanh có thể xấu hơn.

### 18.3. Chi phí scale-up không luôn tuyến tính

Ví dụ:

| Node size | Chi phí tương đối | Throughput đạt SLO (minh họa) |
|---|---:|---:|
| 4 vCPU / 16 GiB | 1.0× | 800 ops/s |
| 8 vCPU / 32 GiB | 1.9× | 1.500 ops/s |
| 16 vCPU / 64 GiB | 3.8× | 1.900 ops/s |

Nếu sau 8 vCPU tăng tài nguyên chỉ tăng throughput ít, có thể đã chạm giới hạn IOPS, locking, network hoặc inefficient query. **Số liệu trên là ví dụ**, không đại diện cho một MongoDB product tier.

### 18.4. Tối ưu query có thể rẻ hơn scale

Nếu:

~~~text
Query A:
  docsExamined = 2,000,000
  nReturned    = 20

After appropriate index:
  docsExamined = 25
  nReturned    = 20
~~~

Query/index optimization có thể giảm CPU/IOPS hơn nhiều so với mua node lớn. Tuy nhiên index mới vẫn tạo storage/write overhead nên cần benchmark mixed workload.

### 18.5. Không bỏ chi phí chạy benchmark

Benchmark production-like có thể yêu cầu:

- Tạo dữ liệu hàng trăm GiB hoặc TiB.
- Chạy cluster test trong nhiều ngày.
- Lưu logs, trace samples, metrics.
- Tách môi trường và backup.
- Tạo traffic generators đủ mạnh.

Đây là chi phí để giảm rủi ro mua sai capacity hoặc outage production. Có thể tối ưu bằng **representative sampling, staged experiments và data-to-cache ratio**, thay vì chỉ thử dataset quá nhỏ.

## 19. Tình huống vận hành thường gặp

### 19.1. Case A — Production tăng từ 5 triệu lên 50 triệu documents

~~~text
Before:
  5M docs, indexes fit in cache, p95 20 ms

After:
  50M docs, cache evictions high, p95 250 ms
~~~

Điều tra:

1. Query shape/index plan có thay đổi?
2. Keys/docs examined có tăng nhanh hơn nReturned?
3. Working set và index bytes tăng bao nhiêu?
4. Cache eviction/disk IOPS/latency có tăng cùng p95?
5. Read/write QPS và long-tail queries có thay đổi?
6. Có retention/archive hoặc index reduction hợp lý?

Không kết luận “MongoDB chậm vì nhiều documents” trước khi xác định nguyên nhân.

### 19.2. Case B — Disk usage vượt dự báo

~~~text
Forecast: 300 GiB used after 1 year
Actual:   600 GiB after 8 months
~~~

Kiểm tra:

- BSON size trung bình có tăng không?
- Index count, multikey fan-out và key sizes?
- TTL/archive có hoạt động và backlog không?
- Có duplicated data, failed cleanup hoặc long-running migrations?
- Oplog/backup snapshots nằm ở đâu?
- Compression và storage engine allocation khác giả định?
- Data copies/replica members bị cộng nhầm?

Sửa **định nghĩa metric** trước khi sửa forecast; tránh trộn logical bytes với tổng physical copies.

### 19.3. Case C — CPU cao, disk thấp

~~~text
CPU: 95%
Disk IOPS: 20% capacity
Cache eviction: stable
P95 query latency: high
~~~

Ưu tiên kiểm tra aggregation/sorts, execution plans, CPU-intensive expressions, BSON processing và concurrency. Nâng disk throughput có thể không giúp.

### 19.4. Case D — CPU thấp, disk latency cao

~~~text
CPU: 25%
Random disk reads: high
IOPS throttling: observed
P99 latency: high
~~~

Phân tích cache misses, working set, storage tier, access patterns và index selectivity. Tăng vCPU có thể không giảm p99.

### 19.5. Case E — Một tenant rất nóng

~~~text
Tenant A: 70% write load
All other tenants: 30%
Overall cluster disk: balanced
One shard primary CPU: 98%
~~~

Đây có thể là **workload skew**. Kiểm tra shard key, hot-key frequency và query targeting. Balancer chủ yếu điều phối ranges; có thể cần thay cách partition thay vì chờ owned bytes đều hơn.

### 19.6. Case F — Read scaling bằng secondary làm dữ liệu chậm cập nhật

Sau khi chuyển read preference sang secondaryPreferred, API giảm primary load nhưng user vừa update order không luôn đọc được state mới ngay.

Đây là vấn đề **consistency contract**. Cần xác định endpoint nào cho phép stale reads và endpoint nào cần đọc primary/causal consistency. Không đánh đổi correctness lấy throughput mà không có thiết kế nghiệp vụ.

### 19.7. Case G — Index build làm disk gần đầy

Một index mới lớn cần thêm storage, có thể gây temporary overhead và I/O cao. Nếu disk free sát ngưỡng, build có nguy cơ thất bại hoặc ảnh hưởng availability.

Trước khi build:

1. Ước lượng index size trên representative corpus.
2. Đo free space và growth trong thời gian build.
3. Xem version-specific index build behavior.
4. Lên maintenance/rollout/rollback plan.
5. Theo dõi replication, CPU, disk latency và application errors.

### 19.8. Case H — Benchmark chạy tốt chỉ vì page cache nóng

Lần 1:

~~~text
p95 180 ms
disk reads high
~~~

Lần 2:

~~~text
p95 20 ms
disk reads low
~~~

Không vội kết luận hệ thống đã tối ưu. Kiểm tra cache state, thứ tự chạy, warm-up, query key distributions và OS cache. Báo cáo cả **warm và mixed/cold workload**.

### 19.9. Case I — Query chạy nhanh vì không có kết quả

Test query dùng customerId String, production field là ObjectId. Benchmark trả nReturned=0 trong 1 ms. Đó là **sai correctness**, không phải thành công hiệu năng.

Luôn xác minh matched data theo kiểu BSON và expected result count.

### 19.10. Case J — p95 ổn nhưng p99/timeout tăng

~~~text
p50: 12 ms
p95: 80 ms
p99: 4 seconds
timeouts: 1%
~~~

Điều tra long-tail queries, batch jobs, pool queues, primary elections, disk stalls và large documents. Mở rộng capacity cần mục tiêu **tail latency và error rate**, không chỉ mean.

### 19.11. Case K — Thêm shard nhưng cost tăng, latency không đổi

Nếu workload chủ yếu scatter-gather do thiếu shard-key predicates, thêm shards làm tăng fan-out/cost mà chưa giảm p95.

Kiểm tra query targeting bằng explain trên mongos, sửa query/index/schema trước khi mở rộng tiếp.

### 19.12. Case L — Backup restore không đạt RTO

Live cluster đáp ứng 2.000 ops/s nhưng restore 4 TiB cần nhiều giờ hơn RTO cho phép. Cần xem backup topology, snapshot/PIT strategy, bandwidth, index rebuild, replica catch-up và restore drills.

**Capacity includes recoverability**, không chỉ live query throughput.

## 20. Bảng lựa chọn một biện pháp tối ưu và phép đo kiểm chứng

| Biện pháp | Giả thuyết | Metrics phải cải thiện | Side effects cần theo dõi |
|---|---|---|---|
| Compound index | Giảm scanned docs/sort | Docs/keys examined, p95 | Index bytes, write latency. |
| Tăng RAM | Giảm cache misses | Disk reads/eviction, p95 | Cost, memory pressure khác. |
| Tăng IOPS tier | Giảm disk queue | Disk latency, p99 | Storage cost. |
| Tăng vCPU | Giảm CPU contention | CPU headroom, throughput | I/O có thể thành bottleneck mới. |
| Secondary reads | Giảm primary read CPU | Primary QPS, latency | Staleness, secondary lag. |
| Add shard | Phân bố storage/work | Owned bytes/QPS by shard | Migration, zones, scatter-gather. |
| Reshard collection | Tăng entropy/targeting | Hot shard ratio, p95, QPS | Operational impact, index design. |
| TTL/retention | Giảm retained data | Data/index growth, working set | TTL backlog, delete I/O, compliance. |
| Archive cold data | Giảm hot storage | Cache/disk/latency | Rehydration, query complexity. |
| Application cache | Giảm repeat reads | DB read QPS, latency | Invalidation, stale data. |
| Pagination change | Giảm deep skip cost | Keys/docs examined, p95 at page N | Cursor semantics. |
| Batch writes | Giảm overhead per record | Successful throughput | Batch size, failures/retries. |

Không tối ưu một metric trong bảng mà không theo dõi những side effects cùng hàng.

## 21. Checklist lập kế hoạch dung lượng và benchmark

### 21.1. Inventory và baseline

- [ ] MongoDB deployment type/version, driver version, topology đã được ghi.
- [ ] Có số documents và BSON sizes theo từng collection.
- [ ] Có indexSizes, compression/storage estimates và disk allocation.
- [ ] Tách logical bytes với physical storage và replica copies.
- [ ] Có working set/cache metrics và disk IOPS/latency.
- [ ] Có CPU, memory, network và connection pool metrics.
- [ ] Có throughput/read-write mix theo giờ cao điểm.
- [ ] Có p50/p95/p99 latency và error/timeout rates.
- [ ] Có replication lag/oplog/backup health.
- [ ] Nếu sharded: có owned bytes/QPS theo shard và shard-key statistics.

### 21.2. Growth model

- [ ] Số records mới theo ngày/tháng.
- [ ] Net documents retained sau TTL/archive/deletes.
- [ ] Kích thước trung bình và tail BSON sizes.
- [ ] Updates làm document lớn thêm hoặc đổi indexed fields.
- [ ] Số indexes, multikey index fan-out, key size growth.
- [ ] Compression ratio dựa trên representative corpus.
- [ ] Oplog retention, snapshots, backup archive và restore capacity.
- [ ] Forecast base/high growth/stress.
- [ ] Operational headroom cho index build/migration/bursts.
- [ ] Quyết định trigger theo runway và lead time.

### 21.3. Test corpus

- [ ] Có đủ documents/bytes để không luôn vừa cache.
- [ ] Field types BSON tương ứng production.
- [ ] Có arrays, nested objects, null/missing và large-tail values.
- [ ] Tenant/customer/status/cardinality distributions thực tế.
- [ ] Hot keys và skew được mô phỏng.
- [ ] Timestamp trải dài theo retention và query recency.
- [ ] Index definitions giống cấu hình dự kiến.
- [ ] Query results đã được xác thực đúng nghiệp vụ.
- [ ] Dữ liệu không chứa PII/secrets production ngoài chính sách.
- [ ] Seed process có thể tái tạo và không xóa dữ liệu ngoài lab.

### 21.4. Benchmark workload

- [ ] Có nhiều query shapes và tỷ trọng tương ứng telemetry.
- [ ] Có reads, writes, updates, aggregations và batch jobs.
- [ ] Có concurrency thực tế và mô tả arrival model.
- [ ] Có warm-up, steady state, spike và soak khi phù hợp.
- [ ] Có warm/mixed cache scenarios.
- [ ] Đo successful throughput và tỷ lệ errors.
- [ ] Có p50/p95/p99 thay vì chỉ average.
- [ ] Đo load generator CPU/memory/network.
- [ ] Thu server CPU/cache/disk/replication đồng thời.
- [ ] So nhiều lần chạy với cùng cấu hình/baseline.

### 21.5. Quyết định mở rộng

- [ ] Bottleneck được chứng minh bằng measurements.
- [ ] Alternatives đã được so sánh (index, scale RAM/IOPS, replicas, shard).
- [ ] Consistency/read preferences được xem xét khi read-scaling.
- [ ] Shard key/zone constraints được đánh giá nếu sharding.
- [ ] Có capacity cost và operation complexity estimate.
- [ ] Đã xét downtime/failover/upgrade compatibility.
- [ ] Backup/restore có thể đạt RPO/RTO sau thay đổi.
- [ ] Có kế hoạch migration và rollback theo supported procedures.
- [ ] Có người sở hữu SLO và phê duyệt change.
- [ ] Post-change benchmark và monitoring được lên kế hoạch.

## 22. Bài thực hành

Các bài tập dùng dữ liệu lab riêng, không yêu cầu chạy load trực tiếp trên production.

### Bài 1 — Phân biệt những loại size

Giải thích sự khác nhau giữa **logical BSON bytes, physical collection storage, totalIndexSize, working set và diskUsedBytes**. Vì sao không nên gộp tất cả thành một trường tên "databaseSize"?

### Bài 2 — Tốc độ tăng logical

Ứng dụng ghi 250.000 documents/ngày, trung bình 3 KiB. Tính logical inserted GiB/ngày và GiB/năm nếu không xóa.

### Bài 3 — Retention 90 ngày

Một service ghi 500.000 sessions/ngày, trung bình 1 KiB, giữ 90 ngày. Ước lượng steady-state document count và logical data. Vì sao TTL lag/physical storage có thể khác dự báo?

### Bài 4 — Weighted average document size

70% docs 1 KiB, 25% docs 4 KiB, 5% docs 20 KiB. Tính average BSON size. Vì sao chỉ test docs loại 1 KiB sẽ sai?

### Bài 5 — Growth 5% tháng

Lập forecast docs/ngày cho tháng 0, 1, 3, 6, 12 nếu baseline là 300.000 và tăng 5% mỗi tháng. Phân biệt compounding growth với tăng tuyến tính.

### Bài 6 — Index ratio

Current logical data 120 GiB, indexes 50 GiB. Tính index/logical ratio, rồi giải thích vì sao không thể áp cùng ratio vĩnh viễn nếu thêm multikey index.

### Bài 7 — Replica storage

Một data-bearing member dùng 400 GiB, replica set có ba members. Ước tính tổng live physical storage và liệt kê overhead chưa tính.

### Bài 8 — Sharding và replication

Một collection 900 GiB được chia đều trên ba shards, mỗi shard replica set ba members. Phân biệt approximate data per shard và tổng physical replicated data trước index/overhead.

### Bài 9 — Headroom

Projected live storage là 420 GiB/member. Nếu policy yêu cầu 25% free headroom, tính minimum provisioned volume capacity bằng công thức dữ liệu / (1-0.25).

### Bài 10 — Disk runway

Shard còn 500 GiB usable free, tăng ròng 25 GiB/ngày. Tính runway. Nếu change lead time là 15 ngày và safety buffer 10 ngày, đã tới ngưỡng mở rộng chưa?

### Bài 11 — CPU vs IOPS

Tình huống A: CPU=95%, disk latency thấp. B: CPU=25%, disk latency 40 ms và IOPS throttled. Với mỗi case, bạn sẽ đo gì và ưu tiên giả thuyết nào?

### Bài 12 — Working set

Database 2 TiB nhưng 90% reads chỉ tới 100 GiB gần đây. Vì sao không thể suy RAM phải đúng 2 TiB? Điều kiện nào khiến 100 GiB hot set vẫn chưa đủ để sizing?

### Bài 13 — Cache misses

Khi tăng dataset 10× nhưng RAM không đổi, disk reads và p99 tăng mạnh. Nêu tối thiểu năm metrics/queries cần điều tra trước khi mua RAM.

### Bài 14 — Little's Law

Workload ổn định đạt 3.000 requests/s với average response time 40 ms. Tính concurrency trung bình xấp xỉ. Vì sao số đó không bằng maxPoolSize cần thiết?

### Bài 15 — Query với index

~~~javascript
db.orders.find({
  customerId: "C-100",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
~~~

Đề xuất một compound index ứng viên và chỉ ra các metrics trong explain.executionStats cần đo để xác nhận.

### Bài 16 — Truy vấn trả 0 kết quả

Production field customerId là ObjectId, nhưng benchmark dùng string. Vì sao latency rất nhỏ không đáng tin? Hãy chỉ ra cách kiểm tra BSON type và correctness.

### Bài 17 — Selectivity

Status PAID là 10% docs trong test nhưng 95% trong production. Index đơn trường status có thể thay đổi độ hữu ích như thế nào?

### Bài 18 — Tenant skew

10 tenants lớn tạo 75% queries, 990 tenants còn lại 25%. Hãy thiết kế workload generator tái tạo skew thay vì uniform random.

### Bài 19 — Long-tail document sizes

1% orders có hơn 100 items, phần còn lại có 1–5. Tại sao test chỉ với trung bình 3 items không phù hợp đánh giá p99 và index fan-out?

### Bài 20 — Query planner

Collection 1.000 docs dùng COLLSCAN nhanh. Bạn phải thu thập điều gì trước khi kết luận không cần index ở 100 triệu docs?

### Bài 21 — Mixed workload

Thiết kế workload 50% point reads, 20% list/filter, 20% writes, 10% aggregation. Cần đo gì để một index giúp list queries nhưng làm writes chậm không bị bỏ sót?

### Bài 22 — Open-loop vs closed-loop

Giải thích hai mô hình phát tải. Vì sao closed-loop có thể che overload/coordinated omission khi service latency tăng?

### Bài 23 — Warm vs cold cache

Một test chạy lần 2 nhanh hơn lần 1 gấp 5. Nêu các giả thuyết và cách thiết kế repeat runs công bằng mà không gây hại production.

### Bài 24 — Bench có lỗi

Một load test báo 4.000 attempted ops/s nhưng 20% requests timeout. Tính successful ops/s xấp xỉ nếu giả sử chỉ có 80% thành công, và giải thích vì sao benchmark có thể không đạt SLO.

### Bài 25 — p50/p95/p99

Một API có average=25 ms, p95=80 ms, p99=3 s. Vì sao dựa trên average để scale sẽ bỏ sót vấn đề? Đề xuất metrics bổ sung.

### Bài 26 — Data-to-cache ratio

Production working set 180 GiB, effective cache 45 GiB. Test working set 18 GiB, effective cache 4.5 GiB. Tính ratio ở cả hai, rồi giải thích những biến vẫn chưa giống.

### Bài 27 — $collStats

Viết pipeline lấy storageStats/count theo collection với scale MiB. Giải thích vì sao storageSize không nhất thiết là logical BSON dataSize.

### Bài 28 — $indexStats

Viết aggregation xem index accesses. Vì sao accesses.ops không phải index bytes hoặc số queries duy nhất? Điều gì xảy ra khi node restart?

### Bài 29 — Profiler

Nêu cách sử dụng profiler/slow query logs an toàn: quyền, privacy, sampling và overhead. Vì sao không bật profiler mức cao mọi lúc trên production?

### Bài 30 — Java benchmark

Thiết kế Java Sync Driver workload dùng một MongoClient chung, 8 threads, query theo tenant skew và đo p95. Nêu hạn chế của closed-loop workload và sample count thấp.

### Bài 31 — Spring Boot metrics

Giải thích chênh lệch giữa MongoDB operation latency và HTTP latency. Viết tên ba operation-shape metric labels an toàn, tránh user IDs.

### Bài 32 — Deep pagination

Với query skip(100000).limit(20), vì sao trang sâu có thể chậm? Đề xuất keyset pagination và yêu cầu tie-breaker.

### Bài 33 — Scale-up hay sharding?

Current cache miss cao, CPU 40%, disk 50%, dataset vẫn có thể vừa một node mạnh hơn. Đề xuất benchmark để quyết định tăng RAM hay thêm shards.

### Bài 34 — Read scaling và consistency

Sau khi chuyển readPreference secondaryPreferred, primary CPU giảm nhưng user thấy state cũ. Tại sao? Thiết kế endpoint nào được phép secondary reads và endpoint nào cần stronger consistency.

### Bài 35 — Hot key trên shard

Một tenant chiếm 60% write QPS, owned data phân đều. Vì sao balancer có thể vẫn đang làm đúng việc? Đề xuất cách phân tích shard key frequency và phương án architecture.

### Bài 36 — Index build planning

Index build trên 50.000 test records mất 1 giây. Bạn cần đo và dự trù điều gì khi build trên 500 triệu records?

### Bài 37 — TTL backlog

Chuyển 100 triệu expired sessions sang TTL cleanup. Nêu các rủi ro writes/oplog/disk và cách phased cleanup phù hợp.

### Bài 38 — Cost per successful operation

Infrastructure cost 2.000 USD/tháng, xử lý 100 triệu successful operations/tháng. Tính USD/million successful operations. Vì sao metric này vẫn cần kèm SLO?

### Bài 39 — RTO và storage

Restore 5 TiB với sustained effective bandwidth 200 MiB/s (bỏ qua rebuild/validation), ước tính lower bound thời gian chuyển bytes. Những công đoạn nào làm RTO thực lớn hơn?

### Bài 40 — Kế hoạch tăng trưởng

Hãy xây một capacity proposal cho service orders gồm:

~~~text
Current data and indexes
Growth forecast (base/high/stress)
Hot working set
SLO latency/throughput/error
CPU/RAM/IOPS/network utilization
Replica set/sharding topology
Recovery RPO/RTO
Options: query tuning, RAM, disk, shards
Cost and risks
Triggers, rollout, rollback
Benchmark evidence
~~~

Không được chọn option chỉ dựa trên kết quả 10.000 toy documents.

## 23. Câu hỏi ôn tập

1. Capacity planning MongoDB khác việc chỉ xem ổ đĩa còn bao nhiêu GB thế nào?
2. Logical dataSize và physical storageSize khác nhau ra sao?
3. Index size ảnh hưởng RAM, disk và write throughput như thế nào?
4. Working set là gì? Có nhất thiết bằng toàn bộ database không?
5. Vì sao total physical storage của replica set có nhiều data-bearing members lớn hơn logical dataset?
6. Sharding có làm tổng lượng dữ liệu tự giảm không?
7. Operational headroom dùng cho những tác vụ nào?
8. Tính net growth khác gross inserted bytes ra sao?
9. TTL/retention làm mô hình tăng trưởng thay đổi như thế nào?
10. Vì sao TTL deletes không đồng nghĩa physical disk giảm ngay?
11. Vì sao average document size chưa đủ để dự báo tail behavior?
12. Multikey index fan-out ảnh hưởng storage/index maintenance thế nào?
13. Tại sao oplog storage phụ thuộc write activity chứ không chỉ live data?
14. CPU, IOPS và network bottlenecks có biểu hiện khác nhau thế nào?
15. WiredTiger cache pressure nên được hiểu với eviction/I/O/latency ra sao?
16. Little's Law liên hệ throughput, latency và concurrency thế nào?
17. Vì sao maxPoolSize không thể được tính trực tiếp chỉ từ concurrent HTTP requests?
18. Tại sao read preference secondaryPreferred có thể tạo stale reads?
19. Vertical scaling có giới hạn nào?
20. Khi nào sharding phù hợp hơn scale up?
21. Vì sao shard key tăng theo timestamp có thể tạo hot shard?
22. Vì sao một hot tenant có thể khiến hashed shard key vẫn chưa phân phối tải tốt?
23. Zone sharding ảnh hưởng capacity planning thế nào?
24. Vì sao thêm shard không bảo đảm phân bố dữ liệu tức thì?
25. Vì sao một COLLSCAN nhanh trên 100 documents không chứng minh không cần index?
26. Selectivity test khác production có thể thay đổi plan/cost ra sao?
27. Tại sao cần dữ liệu synthetic có document shape, array lengths và tail sizes gần thực tế?
28. Tại sao uniform tenant distribution có thể che một hot key?
29. Những yếu tố nào làm benchmark warm cache nhanh hơn cold/mixed cache?
30. Closed-loop benchmark có thể che overload như thế nào?
31. Open-loop traffic giúp mô phỏng arrival rates khác gì closed-loop?
32. Vì sao benchmark phải đo errors/timeouts cùng throughput?
33. Tại sao p99 có thể quan trọng hơn mean latency?
34. $collStats và $indexStats cung cấp những dữ liệu gì?
35. Vì sao không được coi indexStats.accesses.ops là tổng bytes của index?
36. explain.executionStats giúp đánh giá scan amplification thế nào?
37. Tại sao phải xác thực nReturned và BSON type khi benchmark?
38. Một index mới có thể giảm read latency và tăng write latency như thế nào?
39. Một benchmark Java dùng MongoClient mới cho mỗi query có vấn đề gì?
40. Tại sao Spring Boot HTTP latency thường lớn hơn MongoDB execution time?
41. Vì sao metrics không nên gắn orderId/tenantId có cardinality rất cao làm label?
42. Disk runway và provisioning lead time phải được kết hợp ra sao?
43. Vì sao IOPS runway có thể ngắn hơn disk-capacity runway?
44. Làm thế nào lập forecast base/high/stress có xét mùa vụ?
45. Vì sao cần backup/restore drills để đánh giá capacity?
46. Khi nào archive cold data là lựa chọn tốt hơn mở rộng hot storage?
47. Vì sao một cluster có total capacity dư vẫn có thể có một hot shard?
48. Khi scale, những metrics nào phải đo trước và sau để chứng minh cải thiện?
49. Rollback một index hoặc resharding change có những khác biệt gì?
50. Một kết luận benchmark đầy đủ cần ghi những thông tin gì về dataset, workload, hardware và SLO?

## 24. Tổng kết

Khi tối ưu hiệu năng MongoDB, ba câu hỏi cần được nối lại với nhau:

~~~text
                 Production-like workload
                         |
                         v
                Data shape and growth
                         |
                         v
         Current CPU / RAM / disk / network
                         |
                         v
                   Bottleneck?
                         |
              +----------+-----------+
              |                      |
              v                      v
        Query/index issue      Capacity distribution?
              |                      |
              v              +-------+----------+
       Optimize workload      |                  |
                              v                  v
                       Scale up / storage     Replica/sharding
                              |                  |
                              +--------+---------+
                                       |
                                       v
                             Repeat realistic benchmark
                                       |
                                       v
                        Validate p95/p99, errors and cost
                                       |
                                       v
                          Monitor growth / trigger next step
~~~

### 24.1. Những nguyên tắc quan trọng nhất

1. **Data size không phải toàn bộ capacity**: phải tính indexes, working set, oplog, replicas, physical storage, backup và operational headroom.
2. **Tối ưu theo tài nguyên đang nghẽn**: tăng RAM không giải quyết CPU bottleneck; tăng vCPU không sửa query scan hay storage latency.
3. **Forecast cần nhiều kịch bản**: base, high growth, stress, net retention, document growth và seasonal spikes.
4. **Đừng lập capacity dựa trên 10.000 documents khi production có hàng chục triệu**; scale, selectivity, array shape và cache behavior có thể thay đổi hoàn toàn.
5. **Dữ liệu thử phải đại diện cả phân bố**, bao gồm hot tenants, document size tails, timestamps, missing values và query parameter frequency.
6. **Benchmark phải có concurrency và tail latency**, không chỉ một query chạy tuần tự hoặc mean latency.
7. **Đo đúng kết quả query**: một query trả 0 vì sai BSON type không chứng minh hiệu năng tốt.
8. **Index trade-off hai chiều**: giảm scanned docs cho reads nhưng dùng thêm disk/cache và làm inserts/updates đắt hơn.
9. **Replica reads đánh đổi consistency**, còn sharding đánh đổi complexity/routing để phân phối data và workload.
10. **Shard key quyết định khả năng scale**; một hot shard-key value có thể vẫn nóng dù cluster có nhiều shards.
11. **Headroom và recoverability là yêu cầu bắt buộc**: index builds, migration, backup restore, replication catch-up cần capacity ngoài live traffic.
12. **Đặt triggers trước khi cạn tài nguyên**: runway phải lớn hơn lead time plus safety buffer.
13. **Benchmark kết luận bằng SLO và successful throughput**, kết hợp CPU/cache/disk/network/replication, không chỉ số ops tối đa.
14. **Chi phí toàn hệ thống quan trọng hơn microbenchmark**: lựa chọn phải có bằng chứng về cost/latency/availability và vận hành.
15. **Sau scale phải đo lại**, vì bottleneck mới có thể xuất hiện ở tài nguyên khác.

### 24.2. Một bảng báo cáo capacity tối thiểu

| Câu hỏi | Bằng chứng cần trình bày |
|---|---|
| Bao nhiêu dữ liệu và tăng nhanh thế nào? | Docs count, BSON sizes, retained bytes, indexes, monthly forecasts. |
| Dữ liệu được truy cập ra sao? | Hot/cold access, read/write mix, top query shapes, tenant skew. |
| Nút thắt hiện tại là gì? | CPU, WiredTiger cache, disk IOPS/latency, network, explain. |
| Hệ thống chịu tải tối đa nào trong SLO? | Representative benchmark, p95/p99, success QPS, error rate. |
| Khi nào cần nâng cấp? | Runway, lead time, safety buffer, growth scenarios. |
| Nên nâng cấp gì? | Options analysis: index, RAM, IOPS, replicas, shards, archive. |
| Có khôi phục được không? | Backup/restore drill, RPO/RTO, free space và replication. |
| Thành công được đo thế nào? | Baseline vs after, regression guard, operational cost. |

### Tài liệu tham khảo chính thức

- [MongoDB Performance Best Practices](https://www.mongodb.com/docs/manual/administration/analyzing-mongodb-performance/) — quan sát và phân tích hiệu năng.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — thiết kế index và trade-offs.
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plans và execution metrics.
- [db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/) — cách xem explain cho queries.
- [$collStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/collStats/) — collection storage statistics.
- [$indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/) — index usage metrics.
- [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — mongod metrics.
- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — storage, compression và cache.
- [Replica Set Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — read routing và consistency implications.
- [Sharding](https://www.mongodb.com/docs/manual/sharding/) — data/workload partitioning.
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/) — cardinality, frequency và query targeting.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — retention/cleanup.
- [MongoDB Backup Methods](https://www.mongodb.com/docs/manual/core/backups/) — backup/recovery planning.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — aggregation, command monitoring và client API.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — MongoTemplate, query integration và application patterns.

Các metrics và API options có thể thay đổi theo MongoDB, mongosh, Java Driver, Spring Data và deployment (Atlas/self-managed). Trước khi thay đổi topology hoặc capacity production, đối chiếu tài liệu đúng phiên bản và kiểm chứng trên môi trường tương ứng.

**Kết luận:** Đừng tối ưu MongoDB dựa trên tốc độ của một truy vấn chạy với vài trăm records hoặc một dataset đủ nhỏ để nằm trong RAM. Hãy mô hình hóa dữ liệu thật, tính tăng trưởng và headroom, đo workload đủ quy mô/concurrency, xác định chính xác tài nguyên nghẽn, rồi chọn giải pháp mở rộng có thể chứng minh bằng **SLO, successful throughput, recovery capability và tổng chi phí vận hành**.













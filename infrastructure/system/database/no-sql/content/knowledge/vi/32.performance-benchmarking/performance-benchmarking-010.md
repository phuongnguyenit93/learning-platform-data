# Compaction, garbage collection hoặc tác vụ nền theo từng hệ

## 1. Mở đầu: tại sao cùng một truy vấn lại chậm vào những thời điểm khác nhau?

Một dịch vụ Java dùng NoSQL để ghi sự kiện hoạt động của người dùng. Mỗi request ghi một document nhỏ; trong 20 phút đầu, p99 của thao tác ghi chỉ khoảng 12 ms. Sau một thời gian chạy ổn định, p99 tăng lên 280 ms dù mã Java, lưu lượng gửi vào và số node không đổi. Vài phút sau latency tự giảm.

Những nguyên nhân đáng kiểm tra không chỉ là query thiếu index hay mạng yếu. Trong nhiều hệ NoSQL, hệ thống chạy **tác vụ nền** để xử lý hậu quả của writes, deletes và updates:

- Flush dữ liệu từ memory sang các tệp trên đĩa.
- **Compaction** nhiều tệp hoặc segment thành cấu trúc mới.
- Dọn metadata xóa, tombstones, expired documents hoặc obsolete versions.
- Tạo checkpoint, snapshot, backup hoặc rewrite log.
- Cập nhật/chuyển index, rebuild view hay materialized projection.
- Repair/anti-entropy, replication catch-up, rebalancing và shard migration.
- Thu hồi bộ nhớ ở database, runtime JVM hoặc tầng cache.

Các tác vụ này có thể tranh CPU, disk I/O, network, memory bandwidth, page cache và connection capacity với request của người dùng. Một benchmark chạy quá ngắn có thể kết thúc trước khi compaction backlog xuất hiện; kết quả “database rất nhanh” vì thế không đại diện cho vận hành liên tục.

Chủ đề bài học là **“Compaction, garbage collection hoặc tác vụ nền theo từng hệ”**, thuộc chương **“Hiệu năng và đo tải”** của module **Database No SQL**.

**Câu hỏi trung tâm:** tác vụ nền nào đang tiêu thụ tài nguyên, khi nào nó được kích hoạt, chi phí được trả ở đâu, và đo như thế nào để không nhầm độ trễ tạm thời với giới hạn thực sự của thiết kế?

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt compaction LSM, merge segment, storage garbage collection, TTL cleanup và JVM GC.
2. Giải thích **write amplification, read amplification, space amplification** và compaction debt.
3. Hiểu vòng đời memtable, WAL/commit log, SSTable, flush, compaction và tombstone.
4. So sánh đặc điểm tác vụ nền ở Cassandra, RocksDB, MongoDB, Redis, DynamoDB, Elasticsearch và Couchbase.
5. Nhận biết compaction/GC qua latency, I/O, disk usage, metrics và timeline.
6. Thiết kế benchmark NoSQL đủ dài để đi qua các chu kỳ maintenance.
7. Phân tích các tình huống TTL burst, bulk delete, backfill, rebalance và replica recovery.
8. Lựa chọn cấu hình/tối ưu ở đúng tầng, không áp một tham số cho mọi engine.
9. Xây dashboard, ngưỡng cảnh báo, capacity budget và runbook khi maintenance gây nghẽn.
10. Giải thích giới hạn của tuning: không thể xóa hoàn toàn chi phí write/delete chỉ bằng đổi tên một compaction strategy.

---

## 2. “Tác vụ nền” có nghĩa gì trong NoSQL?

Một request **foreground** là việc trực tiếp phục vụ thao tác như GET, INSERT, UPDATE, DELETE, QUERY. Một tác vụ **background** là công việc engine hoặc dịch vụ thực hiện để duy trì/biến đổi dữ liệu và hạ tầng, đôi khi do foreground work tạo ra.

~~~mermaid
flowchart TD
    A["Ứng dụng Java: read/write/delete"] --> B["NoSQL foreground path"]
    B --> C["Memory, WAL, page cache"]
    C --> D["On-disk files/segments"]
    D --> E["Background compaction / merge / GC"]
    E --> F["Reclaimed space, new indexes, new files"]
    E -. "CPU, disk I/O, memory, network" .-> B
    G["TTL, replication, index builds, backups"] -. "Maintenance load" .-> E
~~~

Không nên hiểu “background” là **hoàn toàn không ảnh hưởng foreground**. Hai nhóm cùng chạy trên tài nguyên hữu hạn và đôi khi một write có thể bị throttle hoặc stall khi engine chưa xử lý kịp backlog.

### 2.1. Công việc nền không phải lúc nào cũng liên tục

Một số hoạt động chạy theo timer; một số được kích hoạt bởi ngưỡng kích thước, số tệp, dữ liệu bẩn hoặc traffic:

- Memtable đầy → flush.
- Quá nhiều SSTables trong một level → compaction.
- Đủ tỷ lệ obsolete entries → segment merge hoặc compaction.
- TTL monitor phát hiện documents hết hạn → cleanup.
- Oplog/stream retention → xóa lịch sử quá hạn.
- Cluster topology thay đổi → rebalance.
- Index mới được khai báo → backfill/index build.

### 2.2. Một engine có nhiều tầng lưu trữ

Có thể có đồng thời:

~~~text
Java GC
   +
Driver buffers/pool
   +
Database server memory allocator/GC
   +
Database buffer cache / block cache
   +
OS page cache
   +
SSD internal garbage collection
```

Nếu p99 tăng, phải xem **tầng nào có bằng chứng**; không kết luận “do GC” chỉ vì biểu đồ latency có hình răng cưa.

---

## 3. Phân biệt ba kiểu “GC” dễ nhầm

| Loại | Đối tượng được dọn | Mục tiêu | Ví dụ |
|---|---|---|---|
| **JVM garbage collection** | Java objects không còn reachable | Thu hồi heap của Java process | G1, ZGC trong ứng dụng Java hoặc server dùng JVM |
| **Storage garbage collection** | Old versions, tombstones, expired records, obsolete files | Thu hồi dung lượng hoặc giảm read cost | Cassandra compaction, LSM obsolete entries, Lucene merges |
| **SSD/flash garbage collection** | Flash pages/blocks và wear leveling nội bộ | Chuẩn bị free blocks cho thiết bị | SSD controller/firmware |

Cùng từ “GC” nhưng **metrics, ngữ nghĩa và cách khắc phục khác nhau**.

### 3.1. JVM GC

Java server hoặc Java client có thể bị pause/CPU overhead khi heap pressure. Cần JFR/GC logs, allocation rate, heap occupancy và pause distribution.

### 3.2. Storage GC

Một DELETE trên LSM thường để lại marker, chờ các thành phần lưu trữ tương ứng được xử lý an toàn. Read có thể phải lọc nhiều tombstones; disk chưa giảm ngay.

### 3.3. SSD GC

Sau nhiều writes/deletes, SSD có thể phải di chuyển valid pages để giải phóng erase blocks. Hiệu năng có thể ảnh hưởng bởi device wear, TRIM/discard, free space và write pressure. Đây là tầng khác với compaction của database.

**Không lấy việc JVM GC giảm 30% làm bằng chứng SSTable compaction đã được cải thiện.**

---

## 4. Vì sao NoSQL cần compaction?

Nhiều NoSQL systems dùng kiến trúc **LSM-tree** hoặc cấu trúc segment bất biến nhằm tăng hiệu quả ghi.

Một mô hình đơn giản:

~~~text
Client writes
      |
      v
WAL / Commit log (durability)
      |
      v
Memtable (memory)
      |
      | flush when threshold reached
      v
SSTable #1   SSTable #2   SSTable #3
      \          |          /
       \---------+---------/
                |
           Compaction
                |
           SSTable #4
```

Khi một key được cập nhật, engine thường không sửa trực tiếp mọi vị trí của version cũ trong tệp đã ghi. Nó có thể thêm version mới, rồi dọn/cộng gộp các versions trong quá trình compaction.

### 4.1. Ghi nhanh lúc đầu, trả chi phí sau

Ghi tuần tự vào WAL/memtable và flush theo batch thường nhanh hơn cập nhật ngẫu nhiên rất nhiều chỗ trên đĩa. Nhưng compaction về sau phải đọc lại, so sánh, hợp nhất và ghi tệp mới.

Chi phí không biến mất; nó được **dịch chuyển theo thời gian**.

### 4.2. Compaction thường tạo I/O hai chiều

Ví dụ 20 GiB SSTables đầu vào cần merge:

- Đọc dữ liệu từ các tệp đầu vào.
- Tạo những tệp mới.
- Cập nhật metadata/manifest.
- Xóa tệp cũ khi an toàn.
- Có thể tạm giữ cả tệp đầu vào và đầu ra.

Vì thế “compact 20 GiB” không đồng nghĩa chỉ ghi thêm 20 GiB; tùy thuật toán còn có nhiều lần đọc/ghi và file overlap.

### 4.3. Không phải mọi NoSQL đều sử dụng LSM-tree

MongoDB WiredTiger thường dùng B-tree storage với checkpoints/eviction; Redis in-memory cache không dùng SSTable compaction như Cassandra; DynamoDB ẩn chi tiết engine nội bộ của dịch vụ; Elasticsearch dùng Lucene segment merge.

Tên “NoSQL” **không có nghĩa** chúng dùng cùng thuật toán compaction.

---

## 5. Ba dạng khuếch đại: write, read và space

### 5.1. Write amplification — WA

Trong một mô hình đo cụ thể:

\[
WA=\frac{\text{Bytes vật lý ghi xuống storage}}{\text{Bytes ghi logic của workload}}.
\]

Nếu application ghi 1 GiB dữ liệu logic nhưng flush/compaction/indexing khiến disk ghi 7 GiB, write amplification xấp xỉ 7 lần.

Cần ghi rõ mẫu số và phạm vi đo: payload bytes hay serialized record bytes, một node hay toàn cluster, có WAL/index/replica writes hay không. Các tài liệu engine có thể dùng định nghĩa hơi khác.

### 5.2. Read amplification — RA

Một read phải kiểm tra bao nhiêu files/levels/versions/bloom filters hay thực hiện bao nhiêu I/O so với lý tưởng? Read amplification tăng khi có nhiều overlapping SSTables hoặc chưa compaction đủ.

Bloom filters/indexes/caches có thể giảm physical reads nhưng chiếm memory và có chi phí cập nhật.

### 5.3. Space amplification — SA

Một cách diễn đạt:

\[
SA=\frac{\text{Bytes storage đang chiếm}}{\text{Bytes logical live data}}.
\]

Tử số có thể gồm obsolete versions, tombstones, tệp cũ chưa xóa, compaction outputs, index/metadata, snapshots tùy định nghĩa.

### 5.4. Ba mục tiêu có đánh đổi

Một strategy giảm số files cần đọc có thể tạo nhiều rewrite hơn và tăng WA. Một strategy ít rewrite có thể giữ nhiều overlapping files, làm RA cao. Muốn giảm dung lượng ngay sau bulk delete có thể cần compaction mạnh, tạm tăng I/O và disk.

**Không tối ưu cả WA, RA và SA về mức thấp nhất đồng thời mà không có trade-off.**

---

## 6. Compaction debt: nợ bảo trì tích tụ sau writes

Nếu data ingest liên tục nhanh hơn engine xử lý được compaction, lượng công việc chưa hoàn thành sẽ tăng.

Một mô hình khái quát:

\[
D(t+\Delta t)
=
\max\{0,D(t)+W_{\mathrm{new}}-W_{\mathrm{done}}\}.
\]

Trong đó \(D\) là backlog công việc cần compaction tính theo đơn vị được định nghĩa nhất quán, không nhất thiết là tổng bytes raw SSTables.

### 6.1. Dấu hiệu debt tăng

- Số SSTables/segments hoặc files mỗi level tăng.
- Estimated pending compaction bytes tăng.
- Flush không bắt kịp memtable.
- Compaction queue và disk utilization tăng.
- Read latency tăng dần.
- Write stalls/throttling xuất hiện.
- Disk free space giảm dù logical live data không tăng tương ứng.

### 6.2. Debt “đứng yên” không có nghĩa khỏe

Nếu hệ đang giới hạn frontend writes để compaction kịp tốc độ mới, backlog có thể đứng yên nhưng **goodput giảm**. Phải đo cả **tỷ lệ rejected/stalled foreground writes**.

### 6.3. Có thể xuất hiện sawtooth

~~~text
Disk used
   ^
   |         /|        /|
   |        / |       / |
   |       /  |      /  |
   |______/   |_____/   |_____> time
       ingest compaction
~~~

Ví dụ mang tính minh họa: dữ liệu và các tệp có thể tăng trong khi ghi, rồi giảm sau compaction và xóa obsolete files. Các động thái thực tế không nhất thiết là một răng cưa đều.

### 6.4. Compaction debt có thể chuyển từ disk sang memory

Nếu disk quá chậm, flush bị trì hoãn, memtables/immutable memtables tích tụ. Một số engine phải tạm dừng writes để tránh hết memory; tăng RAM không thay thế I/O capacity dài hạn.

---

## 7. Vòng đời WAL, memtable và SSTable

Một write thường trải qua các ranh giới có bảo đảm khác nhau:

~~~mermaid
sequenceDiagram
    participant C as Java Client
    participant DB as NoSQL Engine
    participant WAL as WAL/Commit log
    participant M as Memtable
    participant D as SSTables
    C->>DB: Write K=v3
    DB->>WAL: Append change
    DB->>M: Apply in memory
    DB-->>C: ACK per configured durability
    Note over M,D: Memtable fills
    M->>D: Flush immutable SSTable
    Note over D: Compaction later merges versions/files
~~~

### 7.1. Không nhầm flush với fsync

- **Memtable flush**: dữ liệu từ bộ nhớ nội bộ ra tệp SSTable/segment.
- **WAL flush/fsync**: liên quan độ bền của log trước crash.
- **Filesystem writeback**: OS page cache xuống thiết bị.
- **Database checkpoint**: đánh dấu trạng thái có thể phục hồi.

Tên lệnh và thứ tự ACK khác nhau theo engine. Không suy “đã flush memtable” nghĩa mọi request trước đó đều bền theo mọi failure model.

### 7.2. Compaction không nhất thiết cần cho read-after-write

Một record mới trong memtable vẫn có thể đọc được theo consistency contract. Compaction chủ yếu tối ưu storage/read path, không phải bước “commit transaction”.

### 7.3. Crash giữa compaction

Các engine trưởng thành có cơ chế manifest/checkpoint để tránh dữ liệu mất chỉ vì đang rewrite files. Nhưng disk corruption, hết dung lượng và lỗi recovery vẫn cần được thử và vận hành đúng; không tự xóa tệp SSTable đang dùng.

---

## 8. Các compaction strategy phổ biến của LSM

### 8.1. Size-Tiered Compaction Strategy — STCS

Gộp các SSTables có kích thước gần nhau theo nhóm.

**Ưu điểm thường gặp:** write amplification thuận lợi với một số write-heavy workloads, triển khai theo nhóm file.

**Đánh đổi:** có thể có nhiều SSTables chồng lấn về key ranges; read amplification và dung lượng tạm thời có thể cao.

### 8.2. Leveled Compaction Strategy — LCS

Phân SSTables theo levels với tổ chức overlap chặt hơn ở những tầng phù hợp.

**Ưu điểm:** point reads và phạm vi tệp cần tìm có thể dễ dự đoán hơn.

**Đánh đổi:** dữ liệu có thể bị rewrite qua nhiều levels, làm write amplification cao hơn trong một số workloads.

### 8.3. Time-Window Compaction Strategy — TWCS

Gom dữ liệu theo cửa sổ thời gian, thường phù hợp với workloads time-series có TTL và dữ liệu hầu hết được ghi theo thời gian.

**Ưu điểm:** khi data windows hết hạn đồng loạt, có thể giảm chi phí cleanup nếu model và timestamp/TTL phù hợp.

**Đánh đổi:** late/out-of-order writes, mix TTL và long-lived data có thể làm kết quả kém; không phải mọi event time-series đều hợp TWCS.

### 8.4. Universal/FIFO/Adaptive strategies

Một số LSM engines như RocksDB có universal/fifo/leveled compaction; Cassandra có thêm các lựa chọn chiến lược theo version (chẳng hạn UCS ở những bản hỗ trợ). **Không giả định tên cấu hình hoặc tham số giữa hai engine là tương đương.**

### 8.5. Chọn bằng workload

| Workload | Cân nhắc ban đầu | Điều cần đo |
|---|---|---|
| Write-heavy, point lookup ít | Size-tiered hoặc write-optimized | WA, disk, read p99 |
| Point reads nhiều, mixed updates | Leveled | Read p99, stalls, WA |
| Time buckets, TTL đồng nhất | Time-window | SSTable expiry, tombstones, late data |
| Cache/ephemeral recent data | FIFO khi engine hỗ trợ và semantics phù hợp | Data loss policy, retention |
| Mixed workloads lớn | Engine default hoặc adaptive | Tài nguyên và p99 thực tế |

Không đổi strategy chỉ vì một bài benchmark ngắn cho kết quả tốt hơn; phải xét backfill, migration, disk headroom và retention.

---

## 9. Cassandra: hệ LSM với compaction và tombstone rõ nét

Apache Cassandra sử dụng memtables, commit logs và SSTables; compaction giúp quản lý phiên bản, tệp trên disk và dữ liệu đã xóa.

Một write có thể tạo SSTable mới sau flush; updates/deletes ở cùng partition để lại các thành phần cần merge/reconcile về sau.

### 9.1. Các hoạt động nền quan trọng

- Memtable flush.
- SSTable compaction.
- Tombstone cleanup theo điều kiện an toàn.
- Repair/anti-entropy giữa replicas.
- Hinted handoff replay theo cấu hình.
- Read repair/reconciliation theo semantics phiên bản.
- Streaming SSTables khi bootstrap/rebuild node.
- Index/SAI maintenance theo tính năng đang dùng.
- Cleanup sau thay đổi token ownership.
- Snapshot/backup và commit-log recycling.

### 9.2. STCS

Thường phù hợp khi write throughput quan trọng và có khả năng chấp nhận nhiều overlapping SSTables; nhưng một read có thể phải kiểm tra nhiều tệp, và compaction có thể yêu cầu disk headroom đáng kể.

### 9.3. LCS

Thường hữu ích cho read-heavy/mixed workloads cần point-read predictability; đổi lại có thể tăng I/O rewrite. Kiểm theo partition size, workload TTL và SSD budget.

### 9.4. TWCS

Thích hợp khi dữ liệu vào các time windows và phần lớn hết TTL theo cùng tuổi. Ví dụ IoT events theo ngày có retention 30 ngày; việc tổ chức theo cửa sổ giúp engine có cơ hội loại các SSTables đã hết hạn.

Nhưng nếu một SSTable chứa giá trị sống lâu hoặc write tới partition cũ, việc bỏ cả SSTable không còn dễ. **Không dùng TWCS như phép màu cho mọi bộ dữ liệu có trường timestamp.**

### 9.5. Unified Compaction Strategy và khác biệt phiên bản

Các bản Cassandra mới có thể hỗ trợ chiến lược khác và tham số khác. Trước khi cấu hình phải xác nhận **engine version, table options, migration path và behavior** trong chính deployment. Không sao chép config giữa Cassandra 3.x/4.x/5.x mà không đối chiếu.

---

## 10. Cassandra tombstones và `gc_grace_seconds`

Một row bị DELETE trong Cassandra không thể đơn giản biến mất ở mọi replica ngay lập tức.

~~~text
RF=3: A, B, C giữ K=v1
B offline
A và C nhận DELETE K với tombstone mới hơn
B vẫn có bản cũ
~~~

Tombstone cần tồn tại đủ điều kiện để replica cũ không cung cấp lại giá trị “zombie”.

### 10.1. `gc_grace_seconds` không phải “sau đúng N giây chắc chắn xóa”

Tham số này tham gia vào điều kiện được phép garbage-collect tombstones, nhưng **compaction, overlapping SSTables, repairs và điều kiện lưu trữ** quyết định lúc nào có thể thực sự dọn dữ liệu.

### 10.2. Giảm grace quá thấp gây rủi ro

Nếu B offline quá lâu, tombstone ở A/C đã biến mất và B quay lại với giá trị cũ, repair/reconciliation có thể làm record hồi sinh trong một số điều kiện.

### 10.3. Tăng grace quá cao cũng có chi phí

Tombstone giữ lâu làm tăng storage, compaction và read overhead, đặc biệt với dữ liệu TTL/churn nhiều. Không chọn một con số cực lớn chỉ vì “an toàn” mà bỏ qua capacity.

### 10.4. Repair và GC phải thiết kế cùng nhau

Cần hỏi:

- Thời gian replica tối đa được phép offline trước khi re-seed?
- Lịch repair hoàn chỉnh có theo kịp không?
- Có ranges nào thường bị bỏ qua?
- Tombstone-heavy tables có SLA đọc riêng?
- Backup/restore và bootstrap node cũ có thể tái nhập stale data không?

### 10.5. Bulk delete/TTL cần có kế hoạch

Một job DELETE hàng triệu rows có thể làm tombstones tăng nhanh, p99 đọc xấu đi dù disk chưa giảm. Với retention theo thời gian, xem xét partition bucketing và model xóa theo nhóm thay vì tạo hàng triệu delete riêng lẻ không kiểm soát.

### 10.6. Diagnostic thích hợp

Các công cụ như `nodetool tablestats`, `compactionstats`, `tpstats`, `netstats` và metrics SSTable/tombstone/repair có thể giúp điều tra, nhưng tên trường và quyền thao tác thay đổi theo version.

**Chỉ dùng lệnh đọc thông tin trong production trừ khi đã có runbook được phê duyệt cho thao tác thay đổi.**

---

## 11. Cassandra: làm sao phân biệt compaction quá tải với query sai mô hình?

Ví dụ một API truy vấn:

~~~sql
SELECT * FROM events_by_user
WHERE tenant_id = ?
  AND user_id = ?
LIMIT 100;
~~~

Nếu partition có hàng triệu events và rất nhiều tombstones, đọc 100 rows sống có thể phải quét nhiều cells/segments hơn dự đoán.

### 11.1. Những dấu hiệu của vấn đề dữ liệu

- P99 tăng ở một vài partitions/key cohorts, không phải tất cả.
- Tombstone scan warnings hoặc số tombstones trên read cao.
- Partition size tăng bất thường.
- Query không giới hạn clustering range phù hợp.
- SSTables per read tăng.

### 11.2. Những dấu hiệu của vấn đề maintenance toàn node

- Disk read/write utilization tăng đồng loạt.
- Compaction backlog tăng kéo dài.
- Flush backlog/blocked writes.
- Mọi query class trên node cùng chậm hơn.
- P99 gắn với các đợt repair/streaming.

### 11.3. Hai nhóm có thể cùng tồn tại

Một data model tạo nhiều tombstones **gây** compaction pressure, rồi compaction pressure lại làm read latency tăng. Tuning threads/I/O chỉ chữa triệu chứng; data model và retention pattern vẫn là nguyên nhân gốc.

### 11.4. Không nên ép manual major compaction để “dọn nhanh”

Manual major compaction có thể đòi disk headroom, làm I/O cao, ảnh hưởng tombstone handling và thay đổi hình thái SSTables. Không chạy trên bảng lớn lúc traffic cao nếu chưa hiểu rủi ro và kế hoạch rollback/backup.

---

## 12. RocksDB/LevelDB: cơ chế LSM ở mức engine

RocksDB là embedded LSM storage engine được dùng trong nhiều ứng dụng/hệ dữ liệu. Nó có:

- WAL và memtables.
- SST files trong các levels.
- Background flush/compaction threads.
- Block cache, Bloom filters, indexes.
- Level/universal/FIFO compaction options.
- Rate limiters và write-stall behavior.
- Snapshot/iterator semantics và obsolete-version retention.

### 12.1. Flush không phải compaction

**Flush** chuyển memtable thành SST. **Compaction** sắp xếp/gộp SSTables về sau. Khi memtables đầy mà flush không kịp, RocksDB có thể throttle hoặc stall writes.

### 12.2. Compaction pending bytes

Một metrics family hữu ích là lượng pending compaction bytes theo engine. Nếu nó tăng liên tục trong cùng workload, compaction capacity có thể không theo kịp.

### 12.3. Property/metrics minh họa

Những RocksDB properties thường được dùng để điều tra (tên khả dụng tùy phiên bản):

~~~text
rocksdb.estimate-pending-compaction-bytes
rocksdb.num-running-compactions
rocksdb.num-immutable-mem-table
rocksdb.cur-size-all-mem-tables
rocksdb.stats
rocksdb.levelstats
rocksdb.num-files-at-level<N>
~~~

Không phải mọi property tồn tại ở mọi bản build. Cần đọc version-specific docs và tránh poll thống kê nặng quá thường xuyên.

### 12.4. Tuning thường gặp

- Background jobs/compaction concurrency.
- SST target file sizes và level sizing.
- Write buffers/memtable budgets.
- Rate limit để giữ foreground I/O.
- Compression per level.
- Bloom/filter/block cache.
- Subcompactions khi tính năng hỗ trợ.
- Periodic compaction hoặc bottommost compaction theo use case.

Mỗi thay đổi có trade-off về memory, SSD writes, read latency và space.

### 12.5. Compaction có thể tạm cần thêm disk

Input SSTables thường chưa thể xóa cho tới khi output đã được ghi và metadata đổi an toàn. Nếu volume sắp đầy, compaction có thể thất bại, làm hệ rơi vào vòng luẩn quẩn: **cần compaction để lấy chỗ nhưng không đủ chỗ để compact**.

### 12.6. Không coi setting RocksDB là setting của Cassandra

Hai engine đều có LSM nhưng implementation, thread pools, rate controls, replication và deployment khác nhau.

---

## 13. MongoDB WiredTiger: checkpoint, eviction và cleanup khác LSM

MongoDB với WiredTiger không dùng cùng chu trình SSTable compaction của Cassandra. Những công việc đáng chú ý gồm:

- Cache eviction và reconciliation pages.
- Checkpoint.
- Journal/durability path.
- TTL monitor/background deletion.
- Index builds.
- Collection compaction khi được yêu cầu và hỗ trợ.
- Replication/oplog maintenance.
- Sharding balancer/chunk migrations.
- WiredTiger history store và dữ liệu phiên bản theo transaction/snapshot needs.
- Backup/restore và oplog window management.

### 13.1. WiredTiger cache eviction

WiredTiger giữ các trang dữ liệu/index trong cache. Khi bộ nhớ chịu áp lực hoặc dirty pages tích tụ, eviction cần chọn/reconcile pages để giải phóng chỗ, có thể tăng CPU/disk work và tạo latency spikes.

### 13.2. Checkpoint

Checkpoint tạo một recovery boundary của storage theo engine. Checkpoint activity có thể tăng disk write pressure, nhưng không được coi là một lần “merge SSTables”. Journal và checkpoint có vai trò khác nhau đối với crash recovery.

### 13.3. Xóa document không tự thu nhỏ file trên filesystem

Sau nhiều deletes, storage có thể có **không gian trống để tái sử dụng** trong file nội bộ. `storageSize`/file size trên disk không nhất thiết giảm ngay theo logical document count.

### 13.4. `compact` là thao tác riêng

MongoDB có command/tooling liên quan compact collection theo version và deployment; nó có thể giúp thu hồi/reorganize storage trong một số điều kiện, nhưng cần xem:

- Tác động tới reads/writes.
- Yêu cầu disk headroom.
- Replica set/sharded deployment.
- Quyền và cơ chế chạy an toàn.
- Kỳ vọng không gian thực sự trả lại OS.

Không dùng `compact` như câu trả lời mặc định cho mọi p99 spike.

---

## 14. MongoDB: TTL monitor và index builds

### 14.1. TTL index không xóa đúng thời điểm tuyệt đối

Ví dụ:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

Nếu `expiresAt` là thời điểm hết hạn, TTL monitor có thể xóa documents **sau** mốc đó theo background schedule và tải hệ thống.

### 14.2. TTL burst có thể gây I/O

Nếu hàng triệu documents có cùng `expiresAt`, TTL deletion có thể tạo khối lượng delete lớn cùng giai đoạn, ảnh hưởng disk, indexes, oplog/replication và downstream CDC.

### 14.3. Logical expiry và physical cleanup

Session có `expiresAt` trong quá khứ nên được coi là hết hiệu lực ở application access check, kể cả nếu TTL monitor chưa xóa vật lý.

### 14.4. Index build/backfill

Tạo index lớn có thể đọc nhiều dữ liệu, dùng memory/disk và gây contention tùy phiên bản/loại index. Một index giúp read sau rollout nhưng quá trình tạo ban đầu là **background workload cần ngân sách**.

### 14.5. Sharding balancer

Chunk/range migration có thể sao chép dữ liệu và cập nhật routing, tiêu thụ network/disk và ảnh hưởng load distribution. Không quy mọi latency spike trong sharded cluster cho WiredTiger eviction.

### 14.6. Quan sát bằng server metrics

~~~javascript
db.serverStatus().wiredTiger
db.serverStatus().metrics
db.stats()
db.currentOp()
~~~

Các field thống kê cụ thể thay đổi theo MongoDB version; nhiều lệnh cần quyền thích hợp. So `cache bytes`, dirty/eviction activity, checkpoint timings, TTL deletions, replication lag, index build và disk IOPS với timestamp của p99.

---

## 15. Redis: active expiry, eviction, defragmentation và persistence

Redis thường dùng cấu trúc in-memory; nó không có SSTable compaction giống Cassandra. Các công việc nền/tự động đáng chú ý:

- **Lazy expiry:** khi một key được truy cập, Redis có thể phát hiện nó đã hết hạn.
- **Active expiry:** nền quét/chọn keys để loại expired values.
- **Maxmemory eviction:** loại keys theo policy khi memory pressure.
- **Active defragmentation:** giảm fragmentation trong những cấu hình/phiên bản hỗ trợ.
- **RDB snapshot (`BGSAVE`)**.
- **AOF rewrite**.
- **Replica synchronization**.
- **Lazy free/background freeing** ở những operations phù hợp.
- **Redis Cluster failover/rebalance/resharding**.

### 15.1. TTL expiry không phải timer chính xác

Một key có TTL đến hạn không có nghĩa background thread đã xóa vật lý đúng ngay microsecond đó. Access path cần coi key hết hạn theo semantics của Redis.

### 15.2. Eviction khác expiry

- Expiry: key đã hết thời gian hợp lệ.
- Eviction: engine loại key theo memory pressure và `maxmemory-policy`.

Không diễn giải `evicted_keys` tăng là “nhiều sessions đã hết hạn đúng lịch”.

### 15.3. Persistence cũng ảnh hưởng latency

RDB snapshot và AOF rewrite có thể dùng background child process/fork và copy-on-write behavior. Trên workload ghi nhiều, memory CoW và I/O có thể tăng; cần headroom cho RAM/disk, không chỉ tính `used_memory` ban đầu.

### 15.4. Active defrag không miễn phí

Defrag có thể giảm fragmentation lâu dài nhưng tiêu thụ CPU. Nếu latency target chặt, phải đo hiệu quả và overhead thay vì bật cực đại không kiểm chứng.

### 15.5. Lazyfree

Một số lệnh/cấu hình có thể chuyển công việc giải phóng object lớn sang nền; điều này giúp tránh blocking quá lâu ở đường chính trong tình huống phù hợp, nhưng không làm công việc giải phóng memory biến mất. Latency và memory-release completion vẫn có thời gian riêng.

---

## 16. Redis: số liệu nên xem khi có spike

Những chỉ số/lệnh hữu ích theo điều kiện deployment:

~~~text
INFO memory
INFO persistence
INFO stats
INFO replication
LATENCY LATEST
LATENCY DOCTOR
SLOWLOG GET
```

Các metric hướng điều tra:

- `used_memory`, `used_memory_rss`, fragmentation-related metrics.
- `expired_keys`, `evicted_keys`.
- RDB save status/duration, AOF rewrite state.
- Fork latency và copy-on-write memory khi có báo cáo phù hợp.
- Command execution latency.
- Replication lag.
- Memory allocator/active defrag state.

### 16.1. `SLOWLOG` không phản ánh toàn bộ end-to-end latency

Redis slow log tập trung thời gian thực thi command theo semantics của server; nó không bao gồm đầy đủ network wait, client pool queue hoặc mọi thời gian blocked ở client. Phải đo ở Java lẫn Redis.

### 16.2. RSS tăng không tự là memory leak

RSS khác logical used memory bởi fragmentation, allocator, shared memory/CoW và OS behavior. So nhiều tín hiệu và hành vi ổn định sau traffic mới kết luận.

### 16.3. `BGSAVE` và AOF rewrite có thể trùng peak traffic

Với server sát RAM/disk giới hạn, maintenance có thể dẫn đến I/O spikes hoặc lỗi persistence. Lịch backup/rewrites cần xem theo tải thực tế.

### 16.4. Redis không phải nơi giữ mọi trạng thái nghiệp vụ quan trọng

Nếu mất persistence/replica khi cache có session/lock/idempotency, hậu quả khác nhiều so với mất derived cache. Hiệu năng maintenance và durability cần thiết kế cùng một failure model.

---

## 17. DynamoDB: tác vụ nền được managed, không phải không tồn tại

AWS DynamoDB là managed service. Người dùng không điều chỉnh SSTable levels/compaction threads như RocksDB self-hosted. Tác vụ nền/online maintenance có thể bao gồm:

- TTL item deletion.
- Backfill Global Secondary Index (GSI) khi tạo mới.
- Index/storage management do dịch vụ thực hiện.
- Replication của global tables theo mode cấu hình.
- On-demand/provisioned capacity adaptation và partition-level resource management.
- Export/PITR/backup theo tính năng đang dùng.

### 17.1. TTL là xóa bất đồng bộ

Một item có `expiresAt` không được hứa sẽ bị xóa vật lý đúng lúc hết hạn. Dùng điều kiện `expiresAt > now` trong application read/conditional workflow khi business cần thời gian hết hạn chính xác, không chỉ tin TTL cleanup.

### 17.2. GSI creation/backfill

Tạo GSI trên một table đã có dữ liệu có thể cần backfill dữ liệu lịch sử, tiêu thụ write capacity/index resources và tạo throttling nếu thiết kế capacity không phù hợp.

Trước rollout:

- Xác định index access patterns.
- Kiểm tra billing/capacity và khả năng ảnh hưởng writes.
- Theo dõi index creation/backfill status.
- Không chuyển ứng dụng sang GSI khi index chưa sẵn sàng theo contract.
- Thử rollback/retry ở staging.

### 17.3. GSI consistency khác table source read

GSI thường eventual consistent; đồng bộ index chưa theo kịp có thể tạo stale reads. Đừng kết luận “TTL chưa chạy” chỉ vì query một GSI còn thấy item; hãy phân biệt source/item freshness và index lag.

### 17.4. Managed không có nghĩa mọi latency do “AWS compaction”

Nếu p99 tăng, cũng cần xem:

- Hot partition key.
- Throttled requests.
- Read/write capacity.
- GSI capacity.
- Client retry/backoff.
- Network/SDK connection handling.
- Item size.
- Transaction contention.
- Traffic spikes.

Không có metrics chứng minh internal compaction thì không nên quy lỗi cho một quy trình mà khách hàng không quan sát trực tiếp.

### 17.5. Những metrics có ích

Theo CloudWatch/service metrics và SDK:

~~~text
ConsumedReadCapacityUnits
ConsumedWriteCapacityUnits
ReadThrottleEvents / WriteThrottleEvents
SuccessfulRequestLatency
SystemErrors / UserErrors
GSI-related capacity and throttling metrics
TimeToLiveDeletedItemCount (when available)
```

Tên/semantics có thể khác theo dimension và API version; đọc service documentation chính thức của deployment.

---

## 18. Elasticsearch/OpenSearch: Lucene segment merges

Elasticsearch/OpenSearch dựa trên Lucene segments. Writes tạo document versions và segments; updates/deletes có thể đánh dấu tài liệu không còn active, rồi merge các segments về sau để thu hồi/tối ưu.

~~~text
Indexing:
  new docs / updates / deletes
       |
       v
  Segment A / Segment B / Segment C
       |
       v
  Background segment merge
       |
       v
  Segment D (live docs compacted)
```

### 18.1. Refresh, flush và merge không giống nhau

- **Refresh** giúp các thay đổi trở nên searchable theo near-real-time model.
- **Flush/translog management** liên quan persistence/recovery bookkeeping.
- **Merge** gộp segments và có thể thu hồi deleted-docs storage.

Một document đã delete có thể không xuất hiện trong search sau refresh, nhưng physical bytes chưa được reclaim cho tới các chu kỳ thích hợp.

### 18.2. Bulk indexing tạo merge pressure

Ingest hàng triệu documents nhanh có thể tăng số segments và merge I/O; search p99 có thể xấu khi merge chạy. Bulk batch size, index refresh interval và shard count đều ảnh hưởng.

### 18.3. Force merge cần đúng giai đoạn

Force merge có thể phù hợp với index đã **ngừng ghi** hoặc sau rollover trong một số vận hành, nhưng có thể rất nặng về I/O/disk và không nên chạy đại trà trên write-heavy indexes.

### 18.4. Shard relocation và recovery

Shard movement/recovery tiêu thụ network/disk; có thể đồng thời với merge. Đừng quy một spike theo time cho merge nếu cluster đang rebalance nhiều shards.

### 18.5. Quan sát

~~~text
GET /_nodes/stats/indices/merges
GET /_stats/merge
GET /_cat/segments?v
GET /_cluster/health
```

Cần thêm node CPU, disk watermark, JVM GC, indexing/search p99, thread-pool rejections, recovery progress. Endpoint/field cụ thể tùy Elasticsearch/OpenSearch version.

---

## 19. Couchbase và hệ document có disk compaction

Couchbase có data service, indexes, DCP/replication streams và các hoạt động như auto compaction theo cấu hình/dịch vụ. Ngoài document expiry/deletion, còn có disk fragmentation và index maintenance.

### 19.1. Data compaction và index/view compaction

Tùy phiên bản/loại index, data store và index store có thể cần maintenance riêng. Dọn dữ liệu ở bucket không đồng nghĩa secondary index đã reclaim tương ứng tức thời.

### 19.2. Auto compaction windows

Có thể cấu hình thresholds/scheduling phù hợp ở các phiên bản/triển khai hỗ trợ. Cần quan sát ảnh hưởng foreground KV reads/writes và disk I/O, không chỉ “đã hoàn thành compaction job”.

### 19.3. DCP, replicas và XDCR

Replication/catch-up/streaming giữa nodes/regions có thể tạo background network/disk load. Một job compaction hoàn thành không đảm bảo remote replica/view đã áp tất cả mutations.

### 19.4. TTL, tombstones và purge interval

Với các hệ có purge metadata, cần xét thời gian replica/consumer offline, backup/restore và replay horizon để tránh resurrect bản cũ hoặc mất event deletion.

### 19.5. Đừng chuyển Cassandra settings sang Couchbase

Tên “compaction” giống nhau nhưng cấu trúc dữ liệu, đơn vị cấu hình, auto-compaction và cách đo rất khác. Hãy dựa trên metrics và official settings của bản cài thực tế.

---

## 20. Neo4j và graph databases: khác dạng maintenance

Graph databases có thể thực hiện:

- Page cache eviction.
- Transaction-log checkpoint/rotation.
- Index population/rebuild.
- Store compaction/space reuse theo engine.
- Background statistics/maintenance.
- Cluster replication/catch-up.
- JVM GC nếu server chạy JVM.

### 20.1. Graph traversals chậm chưa chắc do GC

Một traversal bùng số neighbors/hops có thể tự rất đắt dù không có maintenance. Cần xem query plan và cardinality trước khi đổ lỗi cho background activity.

### 20.2. Index population

Một index xây từ graph lớn có thể tiêu thụ tài nguyên đáng kể. Đo tiến độ, memory, page-cache hit và ảnh hưởng tới query latency.

### 20.3. Transaction logs và checkpoints

Làm việc với log retention/backup phải phân biệt thông tin cần cho recovery với file có thể xóa. Không tự thao tác xóa log bởi vì volume đang đầy.

### 20.4. Bài học chung

Cùng tên “GC” nhưng cơ chế tối ưu storage khác nhau; cần tìm **nguồn cạnh tranh tài nguyên thực** thay vì tìm một nút “compact now” trong mọi database.

---

## 21. So sánh nhanh theo từng hệ

| Hệ | Công việc nền đáng chú ý | Dấu hiệu thường thấy | Đường can thiệp nên xem |
|---|---|---|---|
| Cassandra | Flush, SSTable compaction, tombstone GC, repair | SSTables/tombstones, pending compactions, disk I/O | Data model, strategy, repair, throughput |
| RocksDB | Memtable flush, level/universal compaction | Pending bytes, write stalls, level stats | Rate limits, compaction options, I/O headroom |
| MongoDB WiredTiger | Cache eviction, checkpoint, TTL, indexes, balancer | Dirty/eviction metrics, checkpoint, TTL ops | Query/index, cache config, TTL schedule, shard distribution |
| Redis | Expiry, eviction, defrag, RDB/AOF rewrite | Fork, RSS/fragmentation, expiry/eviction counts | Memory, TTL/eviction policy, persistence headroom |
| DynamoDB | Managed TTL, GSI backfill, replication | Throttle, capacity metrics, index status | Key design, capacity, backfill rollout |
| Elasticsearch | Lucene merge, refresh, translog, shard recovery | Segments/merge I/O, JVM GC, rejected tasks | Bulk rate, shards, rollover, merge scheduling |
| Couchbase | Data/index compaction, expiry, replication | Fragmentation, compaction progress, disk queue | Auto-compaction, capacity, index/replica load |
| Neo4j | Checkpoint, logs, index population, page cache | Page cache miss, index progress, GC | Query design, index rollout, log/disk headroom |

Bảng này để **định hướng quan sát**, không thay tài liệu phiên bản cụ thể hay tính năng managed/self-hosted.

---

## 22. Tác vụ nền có thể cùng lúc: “maintenance storm”

Một tình huống vận hành:

~~~text
00:00  TTL expires many keys
00:05  Analytics export reads full table
00:10  DB snapshot backup starts
00:12  New secondary index backfill starts
00:15  Node repair/catch-up begins
00:20  LSM compaction backlog rises
```

Mỗi công việc có thể chấp nhận được khi chạy riêng; khi trùng giờ, chúng cùng dùng disk/network và biến p99 thành tail lớn.

### 22.1. Nhìn vào resource budgets

Có thể phân lớp:

- Foreground critical reads/writes.
- Background essential maintenance.
- Optional analytics/backfill.
- Recovery/repair.
- Backup/snapshot.

### 22.2. Không trì hoãn mọi maintenance mãi mãi

Nếu luôn ưu tiên foreground và không cho compaction/repair chạy, debt và độ rủi ro tăng. Một lịch maintenance tốt phải bảo đảm **long-term steady state**, không chỉ p99 đẹp lúc hiện tại.

### 22.3. Đặt maintenance windows theo workload

Chạy backfill/index build vào giờ thấp tải có ích, nhưng không phải engine nào hỗ trợ đặt lịch cho nội bộ compaction. Với managed services, có thể điều khiển **load ứng dụng hoặc job tự quản** thay vì scheduler nội bộ.

### 22.4. Các thay đổi topology có thể làm mọi lịch lệch

Một node mới bootstrap hoặc disk replacement có thể tạo stream/repair load ngoài kế hoạch. Capacity plan cần headroom cho các trường hợp bất thường.

---

## 23. Vì sao latency p99 tăng mà p50 không đổi?

Một trace của 1.000 requests:

~~~text
950 requests: 10 ms
45 requests:  60 ms
5 requests:  500 ms
```

p50 có thể vẫn gần 10 ms, trong khi p99 phản ánh nhóm chậm do queue contention hoặc pause.

### 23.1. Maintenance có thể ảnh hưởng không đồng đều

- Chỉ một shard nhận compaction nặng.
- Chỉ key range có nhiều tombstones.
- Chỉ requests chạm SSTables đang cold.
- Chỉ Java process bị GC pause.
- Chỉ replica leader đang snapshot.

### 23.2. Không đo mỗi trung bình

Cần p50, p95, p99, max có ý nghĩa, error rate, timeout, retry và throughput. Với histogram, kiểm coordinated omission (load generator không gửi request khi bị block làm che tình trạng quá tải).

### 23.3. P99 của từng tầng không cộng đơn giản

Một request đi qua network, queue, DB và decode. Tổng p99 end-to-end **không bằng** tổng p99 của từng tầng một cách tự động vì distributions/correlations khác nhau.

### 23.4. Có thể có tail do retries

Driver timeout sau 200 ms rồi retry tạo request cuối thành 450 ms dù DB mỗi attempt chỉ 100–200 ms. Metrics phía server và client có thể kể hai câu chuyện khác nhau; cần correlating request IDs.

---

## 24. Đo work và saturation, không chỉ latency

Một dashboard hữu ích có bốn lớp:

### 24.1. Workload inputs

- Logical reads/writes/deletes/s.
- Item/row/document size distribution.
- Write update/delete ratio.
- TTL expiration rate.
- Read selectivity, scans/range reads.
- Per-partition/key popularity.
- Backfill/batch/analytics traffic.

### 24.2. Maintenance progress

- Compaction bytes read/written/s.
- Pending compaction bytes/files.
- Flush queue/latency.
- Tombstone age/count.
- TTL deleted items/s.
- Index build progress.
- Repair/catch-up progress.
- Disk space reclaimed.

### 24.3. Resource saturation

- CPU/steal, memory/RSS.
- Disk IOPS, read/write throughput, device busy/queue.
- Page-cache misses.
- Network throughput/RTT.
- JVM GC pause/allocation.
- Database thread-pool/executor queues.
- Connection acquisition waits.

### 24.4. User impact

- End-to-end p50/p95/p99.
- Successful logical operations/s (*goodput*).
- Timeouts, throttles, retries.
- Data staleness/read-model lag.
- Error budgets.
- Correctness invariants (không mất write/không resurrect deletes).

**Chỉ khi ba lớp đầu và user impact được nhìn cùng timeline, ta mới có cơ sở quy một đợt latency cho tác vụ nền.**

---

## 25. Một mô hình capacity cho compaction I/O

Giả sử:

~~~text
Application logical ingest:    4.000 writes/s
Average logical write size:    1 KiB
Effective physical WA estimate: 8
```

Logical throughput:

\[
R_{\text{logical}}
=4000 \times 1\text{ KiB/s}
=3.90625\text{ MiB/s}.
\]

Nếu WA = 8 trong phạm vi đo đã chọn:

\[
R_{\text{physical-write}}
\approx 31.25\text{ MiB/s}.
\]

Đó là storage write traffic ước lượng, **chưa thêm** network replication, disk reads do compaction, analytics scans hay workloads khác nếu WA chưa bao gồm chúng.

### 25.1. Tính theo dung lượng còn trống

Ví dụ device có budget an toàn 60 MiB/s sustained writes cho database trong điều kiện test, những workload khác dùng 20 MiB/s, thì phần còn lại khoảng 40 MiB/s; 31,25 MiB/s chưa vượt budget, nhưng headroom chỉ ~8,75 MiB/s.

Nếu một bulk backfill thêm 20 MiB/s, tổng sẽ vượt budget; latency và backlog có thể tăng. Không dùng “max SSD throughput” marketing thay sustained bandwidth khi có cả reads/writes.

### 25.2. WA không hằng số

Nó thay đổi theo key distribution, deletes, compaction strategy, level fullness, compression, index writes và snapshot retention. Giá trị 8 chỉ là ví dụ.

### 25.3. Không quên read I/O

Compaction thường vừa đọc vừa ghi; disk read budget cũng cần. Nhiều engines có cache/page-cache interactions làm foreground reads bị đẩy khỏi memory khi quét compaction/backfill.

### 25.4. Không quên replication

RF=3 có thể nhân tổng physical work cluster trong một số điều kiện, nhưng không thể đơn giản lấy WA×RF để dự đoán mọi engine vì replication protocol, data movement và storage khác nhau.

---

## 26. Sizing disk headroom cho compaction

Một node có 500 GiB **logical live data** không có nghĩa disk 500 GiB là đủ:

- Các old versions/tombstones có thể còn.
- Flush tạo tệp mới.
- Compaction giữ input và output tạm thời.
- Snapshots/backups dùng hardlinks hoặc copies tùy engine.
- Index builds cần disk bổ sung.
- Repair/bootstrap có thể stream thêm SSTables.
- WAL/commit logs cũng dùng disk.
- Disk fragmentation và filesystem overhead tồn tại.

### 26.1. Không có tỷ lệ headroom duy nhất

Một số operations có thể cần temporary space gần bằng một phần lớn dữ liệu đầu vào. Tỷ lệ tùy strategy, compaction scheduling và workload.

### 26.2. Disk full có thể làm tình hình tệ hơn

Nếu thiếu dung lượng để ghi output compaction, engine có thể không reclaim được old files và bị write stalls. Dọn nhầm WAL/SSTables thủ công để lấy chỗ có thể gây corruption/mất dữ liệu.

### 26.3. Theo dõi disk tăng theo ngày

Tạo biểu đồ:

~~~text
logical_live_bytes
physical_storage_bytes
obsolete_version_bytes (if exposed)
pending_compaction_bytes
disk_free_bytes
snapshot/backup_reserved_bytes
```

Nếu logical live data ổn định nhưng physical storage tiếp tục tăng, cần điều tra retention/compaction/history store/index backlog.

### 26.4. Shard imbalance

Cluster có tổng 30% free space nhưng một shard/node chỉ còn 3% vẫn có thể gặp outage. Capacity cần xem **per-node/per-shard** không chỉ cluster average.

---

## 27. Garbage collection của JVM trong Java client/server

Nếu NoSQL engine hoặc ứng dụng dùng JVM, JVM GC là một nguồn latency độc lập.

### 27.1. Khi nào nghi GC?

- Application p99 tăng cùng timestamps với GC pauses.
- GC logs/JFR ghi pause duration/heap cycles.
- Allocation rate tăng do deserialize documents lớn.
- Object churn từ `List<Document>`/JSON conversion.
- Heap occupancy gần limit.
- CPU dành cho GC tăng.

### 27.2. Một ví dụ anti-pattern

~~~java
List<Document> all =
    mongoCollection.find(filter).into(new ArrayList<>());
~~~

Nếu query trả hàng triệu documents, ứng dụng giữ tất cả objects trong heap. Memory/GC pressure có thể rất lớn; cách tốt hơn là cursor với bounded batching theo nhu cầu.

### 27.3. Streaming không tự hết allocation

Reactive `Flux` giảm nhu cầu gom toàn bộ list nhưng vẫn tạo objects/buffers/operator state. `collectList()` ở cuối pipeline vẫn có thể gom tất cả.

### 27.4. JVM GC và DB storage maintenance có thể cộng hưởng

Một process Java bị GC pause có thể xử lý response chậm, làm client retries; database lúc đó đang compaction nên chậm thêm. Cần trace hai phía.

### 27.5. Không áp một garbage collector cho mọi JDK

G1/ZGC có trade-offs và hành vi thay đổi theo JDK version. Chọn theo measurements, heap requirements và SLO. Không chỉnh JVM GC để chữa database disk bottleneck.

---

## 28. Cách cô lập root cause bằng timeline

Một cách điều tra một spike lúc 02:10:

~~~text
02:08  API p99: 12 ms
02:09  Compaction pending bytes tăng
02:10  Disk write throughput đạt ngưỡng
02:10  API p99: 250 ms
02:10  JVM GC pause: không tăng
02:12  Compaction pending bytes giảm
02:13  API p99: 14 ms
```

Đây là **bằng chứng tương quan đáng xem** nhưng chưa đủ chứng minh nhân quả.

### 28.1. Kiểm confounders

Có batch job hay traffic burst cũng bắt đầu 02:09 không? Có node restart, network jitter, backup hoặc index build không?

### 28.2. So node không bị ảnh hưởng

Nếu chỉ node A compaction và chỉ keys trên A tăng latency, khả năng liên quan cao hơn. Nhưng load balancer retry có thể làm các nodes khác bị ảnh hưởng gián tiếp.

### 28.3. Thực nghiệm có kiểm soát

Trong staging:

1. Tạo workload giống production.
2. Quan sát steady state.
3. Tăng/giảm maintenance concurrency/rate trong giới hạn.
4. Giữ request mix cố định.
5. Đo p99, backlog, goodput, storage.
6. Lặp nhiều chu kỳ.
7. Kiểm lại correctness và recovery.

### 28.4. Không dừng compaction trên production chỉ để kiểm giả thuyết

Nhiều engine cần compaction để duy trì giới hạn lâu dài. Tắt/giảm quá mức có thể gây mất ổn định sau đó. Dùng canary hoặc staging theo quy trình phê duyệt.

---

## 29. Benchmark ngắn dễ “đẹp giả”

Một benchmark chạy 60 giây chỉ tạo 10 GiB writes, nhưng compaction cycle của engine cần vài phút/giờ mới tích lũy debt. Nếu kết thúc ngay khi ingest dừng, benchmark có thể không trả chi phí maintenance.

### 29.1. Ba giai đoạn nên phân biệt

1. **Warm-up:** làm nóng caches, connections, compaction levels.
2. **Sustained steady load:** đủ dài để quan sát backlog không tăng vô hạn.
3. **Recovery/cool-down:** sau khi dừng tải, đo thời gian maintenance trả nợ, disk reclaim và read performance.

### 29.2. Với time-series/TTL cần thời gian mô phỏng phù hợp

Nếu retention là 30 ngày, một benchmark 30 phút sẽ không phản ánh dữ liệu hết hạn và tombstone churn. Có thể dùng staging dataset với TTL ngắn hợp lệ để mô phỏng lifecycle, nhưng phải tránh kết luận tương đương tuyệt đối với production.

### 29.3. Với bulk deletes

Đo ngay sau DELETE và sau compaction/cleanup. Một lệnh DELETE hoàn thành nhanh không chứng minh disk usage và read p99 sẽ trở lại mức đầu ngay.

### 29.4. Với index backfill

Đo baseline, build period và hậu build. Một index có thể cải thiện query p99 sau khi hoàn thành, nhưng phá SLO nếu rollout không có ngân sách.

### 29.5. Đo pending maintenance sau test

Một benchmark có p99 xanh nhưng để lại 100 GiB pending compaction debt chưa phải một phép đo sustained capacity đáng tin.

---

## 30. Workload matrix để thử tác vụ nền

| Kịch bản | Write/read pattern | Background task muốn quan sát | Oracle |
|---|---|---|---|
| W01 | Insert-only tốc độ cao | Flush/compaction | Throughput bền vững, pending bytes |
| W02 | Update cùng hot keys | Old versions compaction | WA, read latency, SSD writes |
| W03 | Random updates nhiều partitions | Compaction và cache churn | p99 và CPU/disk |
| W04 | TTL cùng mốc | Expiry/tombstones | Deletion lag và p99 |
| W05 | TTL rải đều | Background deletion đều | Resource smoothness |
| W06 | Bulk delete | Tombstone cleanup | Disk reclaim, no resurrection |
| W07 | Range scan cùng ingest | Read/compaction contention | Read p99, IO budget |
| W08 | New index build | Index backfill | Foreground SLO/throttling |
| W09 | Node repair/replica catch-up | Streaming/anti-entropy | Lag, throughput, no data loss |
| W10 | Shard rebalance | Data movement | Key hotspots, network, p99 |
| W11 | Snapshot/backup | Checkpoint/copy load | Latency, backup success |
| W12 | Disk nearly full in test | Compaction pressure | Reject/stall predictably, recover |
| W13 | Long transaction/snapshot | Old-version retention | Storage growth, cleanup |
| W14 | Large result materialization | JVM GC | Heap, GC p99 |
| W15 | Small result streaming | Cursor/page cache | Bounded memory |
| W16 | Redis AOF rewrite | Fork/CoW/disk I/O | p99, memory headroom |
| W17 | Redis mass expiry | Active expiry | CPU, expired key backlog |
| W18 | DynamoDB GSI backfill | Managed index population | Write throttling, index ready |
| W19 | Elasticsearch bulk index | Segment merge | Merge bytes/segments, search p99 |
| W20 | Cassandra time buckets | TWCS and TTL aging | SSTable drop, late data cost |
| W21 | Offline replica past grace | Tombstone GC/repair | No zombie data/reseed |
| W22 | Restore old backup | Replay and cleanup | Deletes/versions do not regress |
| W23 | Rolling schema migration | Background backfill + CDC | No gaps, p99 budget |
| W24 | Burst load then idle | Debt drain | Time-to-recover and disk headroom |
| W25 | Concurrent compaction+backup | Maintenance overlap | Admission and SLO |
| W26 | Device I/O throttled | Flush/compaction stalls | Queue bounded, graceful reject |
| W27 | Mixed tenants hot/cold | Per-partition maintenance | Isolation/fairness |
| W28 | Cross-region failover | Replication/rebuild | Source correctness + recovery p99 |

---

## 31. Kiểm thử tác vụ nền không làm hỏng dữ liệu

Performance tuning không được phá correctness.

### 31.1. Tombstone resurrection

Cassandra: nếu tombstones bị loại quá sớm so với offline replica/repair, bản ghi cũ có thể hồi sinh.

### 31.2. Compaction giữa crash

Sau crash/restart trong lúc compaction/flush (trong staging), committed writes phải khôi phục theo durability contract. Không chỉ kiểm “process lên lại” mà phải đối chiếu dữ liệu/versions.

### 31.3. TTL và business expiry

Database có thể xóa vật lý chậm, nhưng application không được cho phép dùng expired token/reservation vì chờ TTL monitor.

### 31.4. Snapshot và delete

Một snapshot trước delete được restore sau sự cố có thể hồi sinh PII. Cần deletion ledger/replay hoặc revalidation theo chính sách.

### 31.5. Index backfill correctness

Index build phải bắt kịp concurrent updates/deletes theo protocol. Nếu đọc từ index chưa ready, có thể trả kết quả thiếu hoặc stale.

### 31.6. Migration version

Trong lúc background backfill, write mới không được bị bản snapshot cũ ghi đè. Version/checkpoint guard cần được kiểm.

---

## 32. Hạn chế compaction thay vì chữa data model: sự đánh đổi nguy hiểm

Một anti-pattern:

~~~text
Latency tăng -> giảm compaction workers về 0
               -> latency tốt 5 phút
               -> SSTables và disk tăng
               -> reads phải quét nhiều files
               -> write stalls + disk full
```

### 32.1. Tuning đúng mục tiêu

Giảm I/O aggressiveness có thể cần thiết để bảo vệ foreground latency trong peak window, nhưng phải có **kế hoạch trả debt** và quan sát backlog.

### 32.2. Chọn data model hợp cleanup

Nếu TTL dùng theo time buckets, partition phù hợp và window có hạn, engine có thể loại dữ liệu hiệu quả hơn so với xóa từng row rời rạc.

### 32.3. Giảm write amplification ở application

- Tránh cập nhật document lớn cho thay đổi nhỏ khi model cho phép.
- Giảm writes trùng/không cần thiết.
- Batch updates theo engine semantics.
- Bớt indexes không dùng.
- Không tạo nhiều TTL churn không cần thiết.
- Giảm hot key contention.

### 32.4. Giảm read amplification

- Truy vấn theo partition/key.
- Giới hạn range scans.
- Dùng indexes/Bloom filters phù hợp.
- Giảm tombstone-heavy partitions.
- Điều chỉnh compaction strategy theo benchmark.
- Kiểm page/block cache hit ratio.

### 32.5. Đừng tự làm mất dữ liệu để cải thiện p99

Tắt WAL, giảm replication hoặc ép tombstone GC khi chưa hiểu durability/consistency là những thay đổi lớn hơn rất nhiều so với tuning maintenance. Chỉ làm nếu business contract thực sự chấp nhận và có phê duyệt.

---

## 33. Java: đo latency ở ranh giới repository

Một cách phù hợp trong ứng dụng Java là dùng Micrometer `Timer` để đo latency của logical database operations. Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Objects;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public final class NoSqlTiming {

    private final MeterRegistry registry;

    public NoSqlTiming(MeterRegistry registry) {
        this.registry = Objects.requireNonNull(registry);
    }

    public <T> T timeSync(
            String operation,
            Supplier<T> work) {

        Timer timer = Timer.builder("nosql.client.operation")
            .tag("operation", operation)
            .tag("mode", "sync")
            .register(registry);

        return timer.record(work);
    }

    public <T> CompletionStage<T> timeAsync(
            String operation,
            Supplier<CompletionStage<T>> work) {

        Timer timer = Timer.builder("nosql.client.operation")
            .tag("operation", operation)
            .tag("mode", "async")
            .register(registry);

        Timer.Sample sample = Timer.start(registry);

        try {
            return work.get().whenComplete((value, error) ->
                sample.stop(timer)
            );
        } catch (RuntimeException | Error failure) {
            sample.stop(timer);
            throw failure;
        }
    }
}
~~~

### 33.1. Đo đến khi operation thực sự hoàn tất

Nếu với async code chỉ đo thời gian `client.getItem()` trả `CompletableFuture`, bạn đang đo thời gian **khởi tạo request**, không phải I/O completion.

### 33.2. Không dùng key/tenant/user ID làm tag tùy tiện

Một metric tag chứa hàng triệu document IDs gây **high cardinality** và tăng chi phí monitoring. Dùng bounded labels như `operation=point_read`, `store=cassandra`, `result=success/error`.

### 33.3. Tách logical operation và attempt

Một logical request có thể retry 3 lần. Nên đo:

~~~text
nosql.logical_latency
nosql.attempt_latency
nosql.attempt_count
nosql.timeout_count
```

Không lấy số attempts/s làm goodput của business requests.

### 33.4. Hạn chế của code minh họa

Đoạn này không gồm metrics result status, cancellation semantics hay tracing context. Nếu future bị hoàn tất sớm do local timeout nhưng remote operation còn chạy, sample stop đo **caller-visible completion**, không nhất thiết server-side request completion.

### 33.5. Metric path của Cassandra/MongoDB/Redis khác nhau

Adapter trên dùng được ở tầng repository nhưng không thay driver metrics (pool wait, retries, server selection, cursor fetch) và server metrics (compaction, cache eviction, TTL).

---

## 34. Java: bounded execution cho maintenance job do ứng dụng tự quản

Không tự điều khiển engine compaction từ code Java, nhưng **backfill, warm-up, export, reindex** của ứng dụng có thể được giới hạn.

~~~java
import java.util.concurrent.Semaphore;

public final class BoundedBackfill {

    private final Semaphore permits;

    public BoundedBackfill(int maxConcurrentBatches) {
        if (maxConcurrentBatches < 1) {
            throw new IllegalArgumentException(
                "Positive concurrency is required"
            );
        }
        permits = new Semaphore(maxConcurrentBatches);
    }

    public boolean processBatch(Runnable batch) {
        if (!permits.tryAcquire()) {
            return false; // Scheduler retry later, not hot-loop.
        }

        try {
            batch.run();
            return true;
        } finally {
            permits.release();
        }
    }
}
~~~

### 34.1. Gating khác scheduling

Đoạn trên giới hạn số batch **trong một JVM**. Nếu job chạy trên 10 instances, số tác vụ toàn hệ vẫn có thể gấp 10 lần. Cần budget toàn job/cluster khi phù hợp.

### 34.2. Không block chờ permit vô hạn

Một job backfill đang tranh DB với checkout cần có pause/retry/deadline. Giữ hàng triệu tasks đang chờ permit không giải quyết capacity.

### 34.3. Checkpoint và idempotency

Nếu batch đã cập nhật DB nhưng process crash trước đánh dấu hoàn tất, retry phải an toàn. Dùng stable batch ID, source version và checkpoint sau commit, không chỉ dựa vào semaphore.

### 34.4. Dynamic throttle

Job có thể giảm concurrency khi DB p99 hoặc pending compaction bytes tăng; chỉ mở rộng khi hệ đủ headroom. Tránh oscillation bằng hysteresis và observation windows.

---

## 35. Cách benchmark không bị coordinated omission

Một load generator gửi request **tiếp theo chỉ sau khi request trước hoàn tất** có thể giảm offered load khi DB chậm, khiến báo cáo latency không phản ánh queue thực tế.

### 35.1. Closed-loop load

~~~text
client -> request -> wait response -> next request
```

Nó phù hợp một số mục tiêu, nhưng throughput tự giảm khi latency tăng.

### 35.2. Open-loop hoặc arrival-rate control

~~~text
Scheduled arrivals at 1.000 requests/s
       |
       v
Measure queueing, rejects, completed requests, p99
```

Giúp quan sát saturation và backlog dưới offered load ổn định. Tuy nhiên công cụ phải xử lý đúng requests chưa hoàn thành và có bảo vệ để không gây hỏng cluster.

### 35.3. Thống kê đúng population

Ghi:

- Offered operations.
- Accepted/rejected.
- Timed out.
- Completed successful.
- Retry attempts.
- p99 của logical requests, không chỉ successes nếu lỗi chiếm tỷ lệ lớn.

### 35.4. Mục tiêu là steady-state sustainable capacity

Một engine đáp ứng 50.000 ops/s trong 2 phút nhưng compaction debt tăng không giới hạn có thể có sustained capacity thấp hơn nhiều.

---

## 36. Hiệu năng theo giai đoạn vòng đời dữ liệu

Một bài test đầy đủ nên qua nhiều trạng thái:

~~~mermaid
flowchart LR
    A["Empty / warmed cache"] --> B["Sustained writes"]
    B --> C["SSTables/segments accumulate"]
    C --> D["Compaction/GC active"]
    D --> E["TTL/deletes accumulate"]
    E --> F["Repair/rebuild/backup"]
    F --> G["Long-running steady state"]
~~~

### 36.1. Trạng thái vừa tạo database

SSTables/segments ít, tombstones bằng 0, cache chưa có dữ liệu cũ; một số đường đọc/ghi khác production đã chạy 6 tháng.

### 36.2. Trạng thái đã update nhiều

Old versions và index maintenance có thể tăng. Benchmark insert-only chưa phản ánh update-heavy workload.

### 36.3. Trạng thái TTL/delete nhiều

Storage bloat và reads phải lọc dữ liệu xóa có thể chi phối. `DELETE` command latency nhỏ không nói được cleanup cost.

### 36.4. Trạng thái sau failure recovery

Replicas catch up, snapshots restore và compaction/repair đồng thời: đó thường là lúc business SLO khó giữ nhất. Nên có disaster recovery capacity testing trong phạm vi an toàn.

---

## 37. Tài nguyên cần dành cho foreground và background

Một cách phân bổ (minh họa, không là config chung):

~~~text
Disk sustainable mixed I/O budget = 100 units
Critical foreground reserve        = 55
Essential compaction/repair         = 25
Optional backfill/analytics         = 10
Safety margin                       = 10
```

### 37.1. Không có giới hạn cứng hoàn hảo

Một số engine không cho tách CPU/I/O chính xác theo tác vụ; OS cgroups/I/O scheduler có hiệu lực khác nhau. Cần đo thực tế, không coi budget trên là guarantee.

### 37.2. Foreground traffic thay đổi

Peak traffic có thể làm compaction chậm; sau peak có thể phải tăng maintenance để trả debt. Nếu peak kéo dài 24/7, chiến lược “compaction làm lúc rảnh” không bền vững.

### 37.3. Backfill là công việc có thể hoãn

Nếu index migration hoặc export không critical, tạm hoãn nó khi engine đang repair/compaction thường hợp lý hơn dừng compaction cốt lõi.

### 37.4. QoS và tenants

Trong multi-tenant systems, một tenant gây TTL/delete churn lớn có thể làm p99 của tenant khác tăng. Có thể dùng partitioning, quota, workload isolation và fairness controls ở application/service layer.

---

## 38. Failure modes cần chú ý khi điều chỉnh maintenance

| Failure mode | Triệu chứng | Rủi ro nếu xử lý sai |
|---|---|---|
| Pending compaction tăng | Disk I/O gần trần, SSTables tăng | Stall hoặc disk full |
| Flush backlog | Memtable/dirty buffer tăng | Write throttling/OOM |
| Tombstone accumulation | Read p99 cao, data chưa reclaim | Zombie nếu GC quá sớm |
| Long-running snapshot | Old versions không được dọn | Disk/history store bloat |
| Index build đang chạy | p99 writes tăng, throttle | Partial index/use before ready |
| Repair + compaction | CPU/disk/network trùng tải | Replica lag, availability |
| Redis AOF rewrite | Fork/CoW/memory tăng | OOM/persistence error |
| Mongo TTL burst | Delete/oplog/index load | CDC lag, query latency |
| Dynamo GSI backfill | Write throttling/index status | SLO violation |
| Elasticsearch merge storm | Search/index p99 cao | Disk watermark/rejections |
| JVM GC pressure | Pause hoặc CPU GC cao | Deadline/retry cascade |
| Over-aggressive cleanup | Data cũ xuất hiện hoặc event bị bỏ | Correctness/privacy violation |
| Under-aggressive cleanup | Disk tiếp tục tăng | Storage exhaustion |
| Backup restore old snapshot | Deleted records trở lại | Data privacy/consistency |

### 38.1. Nhiều failure modes là chuỗi nhân quả

Bulk delete → tombstones → compaction backlog → disk pressure → write stalls → retries → nhiều requests hơn. Chỉ tăng client timeout có thể làm chuỗi kéo dài mà không chữa nguyên nhân.

---

## 39. Runbook khi p99 tăng cùng compaction hoặc GC

### Bước 1 — Xác định phạm vi

- Tất cả requests hay chỉ read/write?
- Tất cả nodes/shards hay một partition?
- Chỉ một tenant/key range?
- Giai đoạn sau deploy/index/TTL/batch?
- p99 tăng nhưng goodput có giảm không?

### Bước 2 — Thu timeline đồng bộ

Ghi timestamps của:

~~~text
application p50/p95/p99
logical QPS / error / retries
server CPU/memory
disk read/write IOPS and throughput
compaction/flush/TTL/index progress
JVM GC pauses
replication lag and maintenance jobs
```

### Bước 3 — Phân loại engine

**Cassandra/RocksDB:** SSTables/levels, pending bytes, stalls, tombstones, repair.

**MongoDB:** WiredTiger eviction/checkpoint/dirty pages, TTL, indexes, balancer.

**Redis:** expiry/eviction, fork/CoW, AOF rewrite, defrag, persistence, command latency.

**DynamoDB:** throttles, capacity, hot keys, GSI backfill, TTL; không tự gán internal compaction.

**Elasticsearch:** merge/segments, indexing/search queues, JVM GC, shard recovery.

### Bước 4 — Bảo vệ foreground

- Pause/throttle optional backfill/export.
- Giới hạn client retries và in-flight.
- Tránh queue vô hạn.
- Giữ capacity cho business writes.
- Nếu source không đủ, reject/defer một phần requests có kiểm soát.

### Bước 5 — Kiểm ổn định dài hạn

- Compaction debt có giảm không?
- Disk free space có hồi phục không?
- Pending TTL/delete backlog có xả được không?
- Replica lag có giảm không?
- p99 và goodput có trở lại bình thường không?

### Bước 6 — Nếu cần thay compaction/GC settings

- Đọc chính xác tài liệu engine/version.
- Mô phỏng staging với dataset đủ lớn.
- Ước lượng I/O/disk headroom.
- Triển khai canary và quan sát debt.
- Không đổi nhiều knobs một lúc.
- Có phương án khôi phục về cấu hình trước.

### Bước 7 — Đối soát correctness

Kiểm committed writes, delete/tombstone safety, index query results, backup/restore viability và mọi business invariant nhạy cảm.

### Bước 8 — Postmortem

Ghi nguyên nhân chính, triggering workload, compaction window, đo WA/RA/SA, thay đổi config, rủi ro data loss và regression tests để ngăn lặp.

---

## 40. Bài tập 1 — Phân loại tác vụ theo từng hệ

Cho các hiện tượng:

~~~text
A. Cassandra có nhiều SSTables và tombstone warnings.
B. MongoDB tăng dirty cache pages, checkpoint time.
C. Redis used_memory_rss tăng trong BGSAVE.
D. DynamoDB tạo GSI lớn trên bảng đang hoạt động.
E. Elasticsearch nhiều deleted docs nhưng disk chưa giảm.
F. Java API có GC pause 400 ms.
```

Hãy giải thích:

1. Có phải compaction LSM, TTL, segment merge, JVM GC hay tác vụ khác?
2. Một metric nào giúp xác nhận hiện tượng?
3. Tài nguyên cạnh tranh chính là gì?
4. Đường can thiệp nào ít rủi ro nhất?
5. Vì sao không dùng một nút “run compact” cho tất cả trường hợp?

---

## 41. Bài tập 2 — Tính write amplification và capacity

Một ứng dụng ingest:

~~~text
6.000 writes/s
2 KiB logical payload/write
WA quan sát = 5
Disk sustained write budget = 80 MiB/s
Other workloads = 25 MiB/s
```

1. Tính logical MiB/s.
2. Ước lượng physical write MiB/s theo WA đã cho.
3. Còn bao nhiêu write bandwidth headroom?
4. Nếu backfill thêm 30 MiB/s, điều gì có thể xảy ra?
5. Tại sao kết luận phải xét thêm compaction read I/O, replication và skew?
6. Tại sao WA có thể thay đổi khi dataset lớn hơn?

Gợi ý:

\[
6000\times2\text{ KiB}
=11.71875\text{ MiB/s}.
\]

\[
R_{\mathrm{physical}}\approx58.59\text{ MiB/s}.
\]

Nếu cộng 25 MiB/s other writes, đã vượt 80 MiB/s dù chưa có backfill.

---

## 42. Bài tập 3 — Compaction debt sau peak

Một engine tạo thêm 10 GiB compaction work/giờ ở tải bình thường và xử lý được 12 GiB/giờ. Trong peak, workload phát sinh 25 GiB/giờ nhưng công suất xử lý vẫn 12 GiB/giờ.

1. Sau 4 giờ peak, debt tăng bao nhiêu?
2. Nếu hết peak và xử lý còn dư 2 GiB/giờ, cần bao lâu để trả debt?
3. Nếu disk headroom chỉ 30 GiB thì rủi ro gì?
4. Làm sao thay đổi workload/index/TTL để giảm phát sinh debt?
5. Vì sao tăng background threads không chắc tăng throughput nếu SSD đã bão hòa?

Gợi ý: tăng \(25-12=13\) GiB/giờ, sau 4 giờ là 52 GiB debt, cần ~26 giờ với tốc độ dư 2 GiB/giờ trong mô hình đơn giản.

---

## 43. Bài tập 4 — Cassandra và dữ liệu zombie

Cụm Cassandra RF=3:

~~~text
Node C offline 10 ngày.
A/B nhận DELETE hàng triệu rows.
Tombstones được GC khi đủ điều kiện.
C quay lại với các giá trị cũ.
```

Hãy trả lời:

1. Tombstone cần tồn tại để giải quyết vấn đề gì?
2. Vì sao `gc_grace_seconds` không là timer xóa đúng giờ?
3. Repair/reseed cần phối hợp thế nào với offline horizon?
4. Tại sao giảm grace chỉ để tiết kiệm disk có thể nguy hiểm?
5. Tại sao giữ tombstone rất lâu cũng có chi phí?
6. Khi workload chủ yếu là time-series TTL, TWCS có thể phù hợp trong điều kiện nào?
7. Cần test và metrics gì trước khi đổi strategy?

---

## 44. Bài tập 5 — MongoDB TTL và checkpoint

Một collection MongoDB có 50 triệu sessions, nhiều documents cùng hết hạn lúc 00:00.

1. TTL monitor có xóa tất cả đúng 00:00 không?
2. Điều gì xảy ra với write load, indexes, oplog và CDC?
3. Query session nên kiểm `expiresAt` ra sao?
4. Làm thế nào giảm TTL burst?
5. Nếu disk file không thu nhỏ ngay sau deletes, điều đó có chứng minh TTL bị lỗi không?
6. Tại sao dùng WiredTiger `compact` cần riêng capacity/maintenance plan?
7. Metrics nào giúp phân biệt TTL load với checkpoint/eviction?

---

## 45. Bài tập 6 — Redis persistence và memory pressure

Redis cache bật RDB snapshots và AOF rewrite. Trong peak write traffic:

~~~text
used_memory gần maxmemory
used_memory_rss tăng
AOF rewrite in progress
API p99 tăng
expired_keys và evicted_keys tăng
```

1. Phân biệt expiry và eviction.
2. Vì sao fork/CoW có thể làm RSS tăng?
3. Active defrag có thể giúp gì và tiêu tốn gì?
4. BGSAVE/AOF rewrite khác LSM compaction ra sao?
5. Có nên giảm `maxmemory` hoặc tắt persistence ngay không?
6. Nếu Redis giữ idempotency/session state duy nhất, failure model thay đổi thế nào?
7. Hãy đề xuất metrics và headroom kiểm chứng được.

---

## 46. Bài tập 7 — DynamoDB GSI backfill

Một table đã có 100 triệu items. Nhóm phát triển muốn thêm GSI rồi chuyển API sang query qua index mới.

Yêu cầu viết kế hoạch:

1. Kiểm query/access pattern và partition key của GSI.
2. Ước lượng capacity/index storage.
3. Xác định thời điểm tạo GSI ít tải.
4. Theo dõi trạng thái/backfill và throttling.
5. Giới hạn background traffic từ ứng dụng.
6. Chỉ cutover khi index sẵn sàng và dữ liệu được đối soát.
7. Kiểm eventual read semantics của GSI.
8. Có rollback/read fallback.
9. Đo p99/throughput trước, trong, sau backfill.
10. Không tuyên bố tự điều chỉnh “compaction threads” của DynamoDB managed service.

---

## 47. Bài tập 8 — Thiết kế benchmark 24 giờ

Một workload NoSQL gồm:

~~~text
50% point reads
25% inserts
15% updates
10% deletes
TTL retention: 7 ngày
Periodic analytics scan: mỗi giờ
Index rebuild: mỗi tuần
```

Thiết kế benchmark/staging simulation gồm:

- Dataset đủ tuổi và phân phối keys.
- Warm-up và sampling.
- Sustained load qua nhiều flush/compaction cycles.
- Bulk TTL expiry/delete scenario.
- P99 latency và goodput.
- Compaction debt, read/write/space amplification.
- Disk/network/memory/JVM GC.
- Repair/backup overlap.
- Driver retries và timeout budgets.
- Snapshot/rebuild correctness.
- Điều kiện dừng nếu staging gần disk full.
- Phân biệt những hoạt động có chu kỳ 7 ngày/1 tuần chưa thể tái hiện đầy đủ trong 24 giờ; dùng test lifecycle riêng.

---

## 48. Các ngộ nhận thường gặp

| Ngộ nhận | Điều đúng hơn |
|---|---|
| “Compaction là một kiểu GC của JVM.” | LSM storage compaction khác JVM heap GC |
| “Background task không ảnh hưởng requests.” | CPU/disk/network/memory được chia sẻ |
| “Write đã ACK nghĩa đã compact.” | ACK và compaction là ranh giới khác |
| “DELETE giải phóng disk ngay.” | Tombstones/obsolete versions có thể còn |
| “TTL đến hạn nghĩa physical delete đúng giây.” | Nhiều hệ dọn bất đồng bộ |
| “Có nhiều SSTables nghĩa chắc bị lỗi.” | Tùy workload/strategy; cần metrics |
| “Giảm compaction threads luôn giảm latency lâu dài.” | Debt có thể tăng và gây stalls |
| “Tăng compaction threads luôn tăng throughput.” | Bị giới hạn bởi I/O/CPU |
| “WA là hằng số của database.” | Phụ thuộc workload/strategy/dataset |
| “LCS luôn tốt hơn STCS.” | Trade-off read vs write/disk |
| “TWCS tự động hợp mọi bảng có timestamp.” | Cần window/TTL/late-write pattern phù hợp |
| “`gc_grace_seconds` là TTL của row.” | Liên quan tombstone GC và repair safety |
| “Repair giống compaction.” | Repair đồng bộ replicas; compaction tổ chức storage |
| “Manual major compaction luôn an toàn.” | Có thể gây I/O/disk spikes |
| “MongoDB WiredTiger giống RocksDB LSM.” | Storage architecture khác |
| “MongoDB xóa nhiều thì file chắc thu nhỏ.” | Không gian có thể được tái sử dụng nội bộ |
| “Redis BGSAVE là SSTable compaction.” | Snapshot/persistence khác |
| “Redis expired và evicted keys là một.” | Expiry theo TTL, eviction theo memory |
| “DynamoDB không có maintenance.” | Managed tasks vẫn có ảnh hưởng |
| “Có thể chỉnh compaction threads của DynamoDB.” | Không có cùng quyền kiểm soát như self-hosted LSM |
| “Elasticsearch refresh là merge.” | Refresh, flush và merge khác nhau |
| “Force merge mọi index để có p99 thấp.” | Có thể gây I/O lớn, không hợp write-heavy index |
| “p50 tốt nghĩa p99 tốt.” | Maintenance có thể tạo tail |
| “Benchmark 1 phút đủ đo sustained throughput.” | Debt thường xuất hiện muộn |
| “Kết thúc benchmark khi latency đẹp là xong.” | Cần đo debt/drain và disk |
| “Tăng pool threads chữa disk saturation.” | Có thể tăng queue/retries |
| “Chỉ nhìn cluster disk free tổng thể.” | Một shard/node có thể gần đầy |
| “GC pause ở Java app giải thích mọi DB spike.” | Cần correlate server metrics |
| “Đổi knobs không cần test correctness.” | Tombstones/retention/restore có rủi ro dữ liệu |
| “Managed cache/DB có RPO=0 chỉ vì có replica.” | Durability/replication contract riêng |

---

## 49. Checklist vận hành và đo tải

- [ ] Xác định engine và phiên bản trước khi thay maintenance config.
- [ ] Phân biệt flush, compaction, GC, TTL, repair, index build và snapshot.
- [ ] Ghi rõ read/write/space amplification của benchmark.
- [ ] Có biểu đồ pending compaction/flush backlog.
- [ ] Có metrics p95/p99/goodput, errors, retries.
- [ ] Có per-shard/per-node disk free và I/O saturation.
- [ ] Có baseline memory, page cache và JVM GC pause nếu áp dụng.
- [ ] Workload đủ dài để quan sát steady-state maintenance.
- [ ] Đo thời gian debt drain sau peak.
- [ ] Không để maintenance job tự quản chạy vô hạn trong peak.
- [ ] Có rate/concurrency limit cho backfill/index migration.
- [ ] Cassandra tombstone retention/repair policy an toàn.
- [ ] MongoDB TTL/index/checkpoint behavior được quan sát.
- [ ] Redis expiry/eviction/persistence overhead có capacity headroom.
- [ ] DynamoDB GSI/TTL và throttling được đo theo CloudWatch.
- [ ] Elasticsearch merge/indexing và shard recovery có metrics.
- [ ] Backup/restore và old-version cleanup có runbook.
- [ ] Có test crash giữa compaction/flush trong staging nếu phù hợp.
- [ ] Không tự xóa WAL, SSTables, oplog hay snapshot trên production.
- [ ] Không đánh đổi durability/consistency tùy tiện để lấy p99.
- [ ] Có canary, rollback và success gates khi đổi strategy.
- [ ] Correctness sau delete/replay/restore được kiểm riêng hiệu năng.
- [ ] Cảnh báo khi disk gần đầy hoặc backlog tăng không giảm.
- [ ] Metrics đo kết quả sau migration, không chỉ trạng thái job `DONE`.

---

## 50. Tổng kết

**Compaction, garbage collection và các tác vụ nền chính là phần chi phí bị trì hoãn của một kiến trúc lưu trữ.** Một NoSQL engine ghi nhanh trong 30 giây chưa chắc duy trì cùng thông lượng trong 30 giờ, nhất là khi nhiều updates, deletes, TTL và read models phải được bảo trì.

Những kết luận quan trọng:

1. **Compaction không phải JVM GC.** Cần nhận diện đúng tầng lưu trữ, runtime hoặc thiết bị đang thu hồi tài nguyên.
2. **LSM chuyển một phần chi phí writes/deletes sang nền.** Flush tạo SSTables; compaction merge tệp/versions và có thể gây write, read, space amplification.
3. **Compaction debt phải về trạng thái ổn định.** Backlog tăng mãi dù p50 đẹp là dấu hiệu capacity dài hạn không đủ.
4. **Cassandra/RocksDB có compaction strategies cụ thể** với trade-off giữa read latency, write amplification và disk; tombstone GC cần an toàn cùng repair/reseed.
5. **MongoDB WiredTiger dùng checkpoint/eviction/TTL/index management**, không được tuning như LSM Cassandra.
6. **Redis có expiry/eviction/defrag/RDB/AOF rewrite**, với memory/CPU/fork/CoW và persistence risks riêng.
7. **DynamoDB managed che chi tiết maintenance nội bộ** nhưng TTL/GSI backfill, throttling và partition design vẫn ảnh hưởng SLO.
8. **Elasticsearch merge Lucene segments** khác refresh, flush và application-level delete.
9. **Benchmark phải đi qua maintenance lifecycle**, đo cả p99/goodput, disk, backlog và thời gian trả debt, không chỉ 1 phút đầu ingest.
10. **Tuning maintenance không được phá correctness.** Tránh làm mất committed writes, resurrect tombstones, phục hồi dữ liệu đã xóa hoặc trả index chưa hoàn chỉnh.

**Câu cần nhớ: “Hiệu năng NoSQL bền vững không phải tốc độ của lần ghi đầu tiên; đó là tốc độ hệ còn duy trì được khi flush, compaction, garbage collection, repair, TTL và mọi công việc nền đều phải được trả đủ chi phí mà dữ liệu vẫn đúng.”**

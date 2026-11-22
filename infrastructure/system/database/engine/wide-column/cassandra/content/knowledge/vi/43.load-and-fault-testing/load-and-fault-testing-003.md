# Giai đoạn làm nóng và trạng thái cache/compaction khi đo tải, thử lỗi Apache Cassandra

> **Chương:** Đo tải và lỗi phân tán  
> **Đối tượng:** Kỹ sư Java, SRE, DBA và người xây dựng test hiệu năng/fault injection trên Apache Cassandra 4.x/5.x. Bài học tập trung vào việc thiết kế **warm-up có kiểm chứng**, đo **cold-start và steady-state** riêng, nhận biết cache nóng/lạnh, memtable flush, SSTable/compaction, và tránh kết luận sai về p95/p99 hoặc khả năng chịu lỗi. Chạy mọi lệnh tạo tải hoặc fault injection **chỉ trên lab/staging được phê duyệt**, không mặc định áp vào production.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Nêu vì sao **JVM/driver warm-up**, **Cassandra/OS cache warm-up** và **compaction catch-up** là **ba quá trình khác nhau**.
2. Phân biệt **độ trễ cold**, **warm-up/transient**, **steady-state** và **giai đoạn phục hồi sau fault**, không trộn tất cả thành một con số p99.
3. Giải thích tác động của **key cache, row cache, chunk cache/OS page cache, memtable, SSTable, bloom filter** lên đường đọc.
4. Giải thích đường ghi **commit log → memtable → flush → SSTables → compaction**, ảnh hưởng tới CPU/disk I/O, write amplification, read amplification và tombstones.
5. Đọc các chỉ số như `KeyCacheHitRate`, `RowCacheHitRate`, `SSTablesPerReadHistogram`, `LiveSSTableCount`, `PendingCompactions`/`PendingTasks`, `CompactionBytesWritten`, flush pending, GC và disk await đúng ngữ cảnh.
6. Lập **kế hoạch warm-up theo query mix, throughput, working set, CL/RF, partition size, TTL**, thay vì một khoảng ngủ cố định.
7. Xác định **steady-state gate** bằng rolling windows về QPS, p95/p99, cache hit/miss, compaction backlog, SSTable count, GC, I/O và resource headroom.
8. Thiết kế thử nghiệm **A/B với cùng dataset và điều kiện môi trường**, biết lúc nào phải đưa dữ liệu nguội vào workload để không overfit hot cache.
9. Viết lab CQL/Java Driver 4.x để phân biệt truy vấn **đọc cùng hot key** và **đọc nhiều phân vùng**, đồng thời ghi metadata/latency có kiểm soát.
10. Dùng `cassandra-stress` làm công cụ minh họa, hiểu giới hạn của schema/phân phối mặc định so với tải ứng dụng Java.
11. Lập runbook đo tải và fault testing với **baseline → warm-up → steady → fault → recovery → post-recovery**, tiêu chí GO/HOLD/STOP và rollback.
12. Phân biệt “node đã UP” với “cache/compaction đã ổn” và “truy vấn ở consistency level nghiệp vụ thực sự đạt SLO”.

**Bối cảnh module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra là cơ sở dữ liệu wide-column phân tán; partition key quyết định token và natural replicas, replication factor (RF) quyết định số bản sao, consistency level (CL) xác định số phản hồi/ACK cần có. Thiết kế theo truy vấn, dữ liệu phân vùng, memtable/SSTable/compaction và Java Driver cùng ảnh hưởng hiệu năng. Đo tải chỉ có ý nghĩa khi **phân biệt các tầng này** và giữ đúng consistency contract của ứng dụng.

## 2. Warm-up là gì, và tại sao bỏ nhầm số liệu rất nguy hiểm?

**Warm-up** là khoảng thời gian chạy workload có kiểm soát để một số thành phần có trạng thái phụ thuộc lịch sử sử dụng: JIT đã biên dịch hot paths, connections/prepared statements đã được tạo, caches đã nhận những keys/pages thường dùng, memtables/SSTables đã chuyển trạng thái ban đầu và compaction/flush của giai đoạn chuẩn bị đã được nhận diện.

Warm-up **không có nghĩa** “toàn bộ dữ liệu đã nằm trong RAM”, “mọi compaction đã kết thúc” hoặc “cluster tự động ready cho production”. Dưới một workload ghi liên tục, compaction bình thường vẫn chạy trong steady state. Một hệ thống ổn định là hệ thống **không tích lũy backlog mất kiểm soát**, không phải hệ thống có `PendingCompactions=0` ở mọi giây.

### 2.1. Dòng thời gian một bài đo tải

~~~text
T0  Tạo cluster hoặc restart service
    |
    v
BOOT: JVM, native port, gossip, driver metadata, schema
    |
    v
SEED: đổ dataset đúng volume/partition/TTL, chờ initial flush
    |
    v
WARM-UP: request mix có kiểm soát
    |     driver JIT + connections + prepared
    |     key/row/chunk/page cache warming
    |     memtable/SSTable transitions + compaction catch-up
    v
STEADY BASELINE: rolling metrics/throughput/latency ổn định
    |
    v
MEASUREMENT: thu p50/p95/p99, errors, CL, CPU/IO/GC
    |
    v
FAULT (nếu có): node/network/latency/replica disruption
    |
    v
RECOVERY: ring + replica availability + cache + compaction
    |
    v
POST-RECOVERY STEADY: đo khả năng phục hồi và backlog
~~~

**Sai lầm điển hình:** Test A bắt đầu sau khi cache đã nóng từ vòng chạy trước, còn test B bắt đầu trên dataset mới/OS cache lạnh. Kết luận “A nhanh hơn B” có thể chỉ đo **lịch sử cache khác nhau**, không đo hiệu quả thay code hay compaction strategy.

### 2.2. Tách hai mục tiêu đo

| Mục tiêu | Có loại bỏ warm-up khỏi metric chính? | Cần báo cáo gì? |
|---|---|---|
| **Cold-start SLA** (khởi động sau outage) | **Không** | Time-to-first-success, p95/p99 ngay sau start, thời gian cache phục hồi |
| **Steady-state capacity** | Có thể **loại khỏi cửa sổ tính KPI chính** sau khi đạt gate | QPS/p95/p99/error/resource dưới trạng thái ổn định đã chứng minh |
| **Failover/recovery SLA** | **Không** loại phần fault/recovery | Time-to-recover ở CL yêu cầu, error budget, backlog drain |
| **So sánh compaction strategy** | Có phân pha, nhưng phải báo cả chi phí catch-up | Steady throughput, read/write amp, disk space, recovery time |
| **Production-like workload** | Không thể “làm nóng” hơn thực tế | Hit ratios, active working set, temporal skew như production |

Không được trộn cold-start latency và steady latency rồi báo một p99 mà không ghi tỷ trọng pha. Ngược lại, **không giấu giai đoạn phục hồi xấu** khi SLA yêu cầu khôi phục trong vài phút sau restart.

### 2.3. “Warm 5 phút” không phải định luật

Thời gian warm-up phụ thuộc:

- **Kích thước working set**: 10 nghìn hot partitions khác 100 triệu partitions.
- **Phân phối truy cập**: hot 1% keys (Zipfian) khác uniform random.
- **QPS và concurrency**: warm-up có 50 RPS không giống production 5.000 RPS.
- **Read/write mix, range/paging**, partition width và cache admission/eviction.
- **Memory/OS cache** so với dataset; việc có seed/flush/compaction chưa?
- **Compaction strategy, disk throughput, tombstone/TTL, repair, RF/CL**.
- **Driver/JVM:** JIT, metadata, prepared cache, connection pool, Netty event loops và GC.

Một con số cố định như 5 phút chỉ có thể là **ngân sách tối thiểu** của một thí nghiệm cụ thể, không thể thay **quan sát trạng thái**.

## 3. Nhiều “cache” nằm ở những tầng khác nhau

~~~text
Client / Java application
  - HTTP/service caches và object pools (nếu có)
  - JVM JIT, class loading, GC
  - Java Driver CqlSession, connections, metadata, prepared cache
                   |
                   | CQL QUERY/EXECUTE
                   v
Cassandra coordinator
  - Request parsing/prepared metadata
  - Scheduling, replica requests, hints/retries (theo trường hợp)
                   |
                   v
Natural replicas (theo partition token + RF)
  - Memtable: writes mới nhất, read path kiểm trước/trong merge
  - Key cache: tìm partition/index positions hiệu quả hơn
  - Row cache: dữ liệu row/partition hot nếu được cấu hình
  - Chunk cache: SSTable compression chunks ở một số phiên bản
  - OS page cache: file pages của SSTables/indexes được kernel giữ
  - SSTable bloom filters, index summaries, partition index
  - SSTables + compaction + disk filesystem
~~~

**Không trộn** “Java Driver prepared statement đã cache” với “data của partition đã trong OS page cache”. Hai thứ có thể cùng ấm lên khi chạy nhiều SELECT nhưng được đo bằng metrics và bị reset bởi sự kiện khác nhau.

### 3.1. Bảng so sánh tầng warm-up

| Tầng | Biến đổi khi warm | Reset/ảnh hưởng bởi | Metric/tín hiệu hữu ích |
|---|---|---|---|
| **JVM app** | JIT code hot, allocation pattern, heap | Restart JVM, GC, workload mới | JFR, GC pause, CPU, allocation |
| **Driver** | Connections/pools, metadata, prepared statements, token-aware routing | Restart service/session, node topology | Pool open connections, in-flight, retries, request latency |
| **Cassandra JVM** | Class loading/JIT, allocations, GC | Restart node, workload/heap pressure | GC/pause, CPU, thread pool pending |
| **Key cache** | Hot partition/index lookup caching | Cache size, replacement, restart/save settings | Hit rate, entries, size/capacity |
| **Row cache** | Cached row/partition content khi bật | Disabled/default, TTL/invalidations, memory | Hit rate, entries, hit/miss |
| **Chunk cache** | Hot compressed SSTable chunks theo implementation | Cache size, restart, compaction changing chunks | Hit/miss/evictions khi có |
| **OS page cache** | Hot SSTable/index disk pages | Host memory pressure, host restart, file churn | Disk read bytes/ops, major faults, page-cache residency |
| **Memtable** | Recent writes còn ở memory | Flush thresholds, flush/truncate/rollback | Memtable size/flush metrics |
| **SSTable set** | Số/tầng/size SSTables và lookup work | Flush, compaction, repair, restore | LiveSSTableCount, SSTablesPerReadHistogram |
| **Compaction** | Merge/rewrite SSTables, xử lý tombstones | Strategy, write rate, size/tombstones | Pending tasks/bytes, compaction throughput, disk/CPU |

**Quan trọng:** Không phải Cassandra deployment nào cũng bật `row cache`. Trong nhiều cấu hình Cassandra 4.x/5.x, row cache **tắt hoặc rất nhỏ** theo mặc định; key cache và OS page cache quan trọng hơn với nhiều workload. `Chunk cache` và tên metric phụ thuộc version/setting. Hãy lấy **effective cassandra.yaml + JMX/metrics thực** trước khi nói một cache “đã nóng”.

### 3.2. Cache warm không chỉ là “hit rate cao”

Một cache có hit rate 99% dưới 100 reads của **cùng một partition** có thể gần như vô ích với workload production đọc 10 triệu partitions khác nhau. Luôn gắn hit ratio với:

- **Query family**, number of distinct partition keys và distribution.
- **Lượng dữ liệu được đọc**: 1 KB/partition khác 5 MB/partition.
- **Những cache misses đắt**: disk I/O, SSTables accessed và tombstones scanned.
- **Evictions/capacity**: hit rate nhất thời cao nhưng cache churn làm p99 bất ổn.

Cache hit rate không thay thế p95/p99 và kiểm đúng kết quả ở CL. Những node không phải natural replica của hot partition có cache khác, nên cùng một SELECT qua coordinator khác có thể có latency khác.

## 4. Cassandra read path: cache nóng và amplification

### 4.1. Đọc partition đi qua những gì?

~~~text
SELECT ... WHERE partition_key = ?
               |
         coordinator
               |
        choose replicas by CL
               |
         replica read path
               |
       Memtable + row cache (nếu có)
               |
         SSTable candidates
               |
       Bloom filters/index summary
               |
     Key cache / partition index search
               |
      OS page cache or physical disk
               |
        Data blocks / decompression
               |
       Reconcile timestamps/tombstones
               |
        Coordinator merges responses
               |
             ResultSet
~~~

Đây là **sơ đồ khái niệm**, không phải thứ tự thực thi cố định của mọi phiên bản/truy vấn. Bloom filter và key cache hỗ trợ tránh/giảm tra cứu SSTables không cần thiết, nhưng một query có thể phải chạm nhiều SSTables ngay cả khi key cache hit.

### 4.2. Key cache

Key cache chủ yếu giúp giảm chi phí tìm **vị trí partition/index** trong SSTables. Khi nó hot, một số disk index lookups giảm, đặc biệt trên workload point-lookup. Nhưng:

- **Key cache hit không phải data cache hit**: đọc SSTable data vẫn có thể cần disk.
- Một partition có nhiều SSTables sau nhiều flush/compaction có thể gây nhiều lookups.
- Key cache không làm `ALLOW FILTERING` hay range scan lớn trở nên rẻ.
- Cache state phụ thuộc restart/saved caches và compaction; không mặc định restart là key cache hoàn toàn rỗng.

### 4.3. Row cache

Row cache khi được bật có thể lưu dữ liệu các partitions/rows thường đọc để giảm SSTable I/O, tùy chiến lược cache và partition layout. Đổi lại nó chiếm memory, phải invalidate/update hợp lệ khi ghi, và có thể không hiệu quả nếu:

- Access keys phân tán rộng, không có hot set.
- Partition rộng hơn giới hạn row-cache capacity.
- Writes liên tục vào cùng partitions làm cache churn.

Đừng bật row cache chỉ để benchmark có p99 đẹp rồi đem so với production row cache disabled.

### 4.4. OS page cache và chunk cache

Linux/Windows kernel có thể giữ các file pages đọc gần đây trong RAM. Cassandra thường dựa mạnh vào OS page cache cho SSTable I/O. Tùy phiên bản và compression config, chunk cache có thể giữ các chunk đã decompression/đã đọc để giảm I/O/CPU.

**Ba sự kiện khác nhau:**

1. Đọc cùng partition lần hai có thể không cần physical disk do page cache.
2. Restart **Cassandra JVM** trên cùng host có thể **không xóa** toàn bộ kernel page cache.
3. Compaction tạo SSTables mới, thay đổi file paths/layout và có thể làm cache cũ ít hữu ích hơn.

Vì vậy phép thử “restart Docker container = cold disk cache” **không đáng tin** nếu container dùng cùng host page cache và volumes.

### 4.5. SSTables-per-read: một chỉ báo read amplification

Giả sử 1 partition có dữ liệu rải trong 12 SSTables sau nhiều flush:

~~~text
Read P -> examine SSTable S1, S2, ..., S12
             |
        merge cells/timestamps
             |
          1 row returned
~~~

Sau compaction phù hợp, một lần đọc có thể phải kiểm ít SSTables hơn. Tuy nhiên “ít SSTables” không bảo đảm nhanh hơn trong mọi trường hợp: compaction chạy nền cũng ngốn disk CPU, tombstone density và page cache ảnh hưởng mạnh. Dùng `SSTablesPerReadHistogram` cùng read latency, scanned/returned rows, disk I/O và key-cache metrics.

## 5. Write path: memtable, flush và điểm xuất phát của compaction

### 5.1. Một write CQL không đợi compaction

~~~text
Java Driver: INSERT/UPDATE at CL LOCAL_QUORUM
                  |
              Coordinator
                  |
         Natural replicas RF3
             /     |     \
            A      B      C
            |      |      |
      Commitlog + Memtable  (trên từng replica)
            |      |      |
          ACK    ACK    ...
             \     /
       CL satisfied -> client success
                  |
             Sau đó theo thời gian
                  |
           Memtable flush -> SSTables
                  |
           Compaction rewrites SSTables
~~~

Một INSERT ACK thành công ở `LOCAL_QUORUM` không có nghĩa SSTable đã flush hay compaction đã kết thúc. Cassandra sử dụng write-ahead commit log và memtable để hoàn tất write path; flush/compaction diễn ra sau. Benchmark ghi thường có **throughput rất cao lúc đầu** vì phần lớn dữ liệu còn ở memtable/commitlog, rồi giảm khi flush/compaction hoạt động và disk capacity được sử dụng thật.

### 5.2. “Đo ghi ngay sau khi tạo bảng” thường quá lạc quan

~~~text
Time      Data path                        Nguy cơ đo sai
0-2 min   Memtable receiving new writes    Disk còn ít SSTables, throughput cao
2-5 min   Memtable flush -> SSTables        Disk writes tăng, p99 biến động
5-15 min  Compaction starts/catches up      CPU/IO amplification xuất hiện
15+ min   Có thể ổn định hoặc backlog tăng  Phụ thuộc tải, disk, strategy
~~~

Các mốc chỉ **minh họa**, không phải thời gian cố định của Cassandra. Nếu dataset rất lớn, background compaction có thể kéo dài nhiều giờ; nếu nhỏ và RAM/disk khỏe, có thể nhanh hơn nhiều.

### 5.3. Khi nào memtable flush?

Memtable có budget riêng và flush được kích hoạt bởi các điều kiện như memory/commitlog pressure, manual flush, hoặc lifecycle đặc thù. Flush biến dữ liệu memtable thành SSTable bất biến. Đừng tin một kịch bản load test đã “hoàn thành write steady state” nếu:

- Memtable size vẫn tăng nhanh mà chưa có chu kỳ flush đại diện.
- Commitlog/disk queue đang tích tụ.
- Disk flush throughput chưa tới mức bình thường của workload.
- Test kết thúc trước khi compaction liên quan tới dữ liệu vừa seed có cơ hội chạy.

**Không chạy `nodetool flush` để “chữa benchmark”** khi thí nghiệm yêu cầu mô phỏng flush tự nhiên; manual flush có thể làm thay đổi số/lớp SSTables và so sánh không còn công bằng. Chỉ dùng manual flush trong **lab có mục đích riêng**, ghi rõ đây là một biến được kiểm soát.

### 5.4. Metrical distinctions: memtable vs flush queue vs compaction

| Tín hiệu | Ý nghĩa | Nếu tăng kéo dài |
|---|---|---|
| Memtable on/off-heap size | Dữ liệu write gần đây trong bộ nhớ | Có thể đang nhận write nhanh; xem flush cadence |
| Pending flushes / flush writer queues | Công việc ghi SSTables chưa xử lý xong | Disk/flush throughput không theo kịp |
| Commitlog activity/disk bytes | Write-ahead log I/O và áp lực commitlog segments | Disk hoặc commitlog flush/recycle bottleneck |
| Live SSTable count | Số SSTables đang tồn tại cho table | Nhiều files có thể tăng read amplification |
| Pending compaction tasks | Công việc compaction chờ | Có thể compaction capacity đang thiếu |
| Compaction bytes processed/written | Lượng I/O do merge/rewrite | Overhead có thể tăng cùng write load |
| Disk utilization/await | Tài nguyên I/O vật lý | Read/write p99 có thể tăng |
| GC pause / CPU steal | JVM/host contention | Có thể tạo timeout giả do backlog |

Một pending compaction task không tương đương một đơn vị dữ liệu cố định; so sánh **chỉ số tasks đơn lẻ** giữa các bảng/strategies có thể sai. Kết hợp với bytes, SSTable sizes và throughput qua thời gian.

## 6. Compaction strategy làm steady-state khác nhau thế nào?

**Compaction** chọn và hợp nhất SSTables, xử lý các version/tombstones theo quy tắc, giảm số nơi read phải tìm dữ liệu nhưng phát sinh read/write I/O, CPU và disk space amplification. Strategy khác nhau có mục tiêu khác nhau; không được “so sánh trước/sau” mà dataset/TTL/query mix thay đổi đồng thời.

### 6.1. Một số chiến lược phổ biến

| Strategy | Phù hợp điển hình | Dạng chi phí đặc trưng | Lưu ý kiểm thử |
|---|---|---|---|
| **STCS** — SizeTieredCompactionStrategy | Write-heavy, sizes theo tiers | Nhiều SSTables size tương tự được gom; read amplification có thể tăng | Cần đủ dữ liệu tạo các tiers thực tế |
| **LCS** — LeveledCompactionStrategy | Read-heavy/đọc point lookup, cần giới hạn SSTables overlap | Write amplification và I/O rewrite có thể cao hơn | Đo cả disk CPU/bytes compacted, không chỉ read p99 |
| **TWCS** — TimeWindowCompactionStrategy | Time-series/TTL có time-bucket phù hợp | Compaction theo cửa sổ thời gian; late data/timestamp out-of-order gây vấn đề | Kiểm phân phối thời gian, TTL, window size, late arrivals |
| **UCS** — UnifiedCompactionStrategy | Cassandra phiên bản hỗ trợ, nhiều workload cân bằng | Tuning/overhead khác theo level/shape | Ghi rõ phiên bản, config, không áp mặc định cho 4.x |

**Không nói “LCS luôn nhanh hơn STCS” hoặc “TWCS luôn ít tombstone”**. Kết quả phụ thuộc partition cardinality, key distribution, TTL, hardware, reads/writes và thời gian test.

### 6.2. Vì sao phải có đủ vòng flush/compaction?

Giả sử so sánh hai bản thiết kế:

~~~text
Test A: STCS, chạy 3 phút, 1 SSTable sau một flush
Test B: LCS, chạy 3 phút, 1 SSTable sau một flush

Kết quả: gần như bằng nhau.

Sai kết luận: "Strategy không có khác biệt".
Đúng kết luận: "Đã đo quá sớm/chưa có compaction regime".
~~~

Muốn so sánh ổn định, phải có **representative SSTable count/levels, compaction backlog và workload duration**. Với LCS, nhìn số SSTables **theo level**; với TWCS, cần dữ liệu trải nhiều **time windows** tương ứng retention và late-arrival policy.

### 6.3. Compaction chạy thường trực không nhất thiết là sự cố

Trong tải ghi ổn định, `CompactionExecutor` luôn làm việc là bình thường. Mục tiêu là cân bằng:

\[
\text{compaction work arriving per second}
\;\lesssim\;
\text{sustainable compaction work served per second}.
\]

Nếu arrival rate vượt capacity lâu dài, backlog/SSTable count/space amplification sẽ tăng và p99 có xu hướng xấu dần. Nếu chúng dao động quanh vùng ổn định theo chu kỳ workload, đó có thể là **steady state với background work đang diễn ra**. Gate “`PendingCompactions=0` trong 60 giây” thường không phù hợp với production-like sustained write.

### 6.4. Tombstones, TTL và thời gian dài

Một stress test 10 phút trên bảng có TTL 30 ngày **không** thể bộc lộ hành vi hết hạn/tombstone churn của 30 ngày workload thực. Ngược lại, đặt TTL 30 giây để “giả lập” 30 ngày có thể tạo compaction dynamics không thực tế.

~~~text
Time-series:
Day 0: write events, TTL ~ 30 days
Day 1..30: continuous late writes + reads
Day 31: expiry, compaction/tombstone reclamation

10-minute benchmark:
  chưa đi qua vòng đời expiry/compaction tương ứng
~~~

Tombstone có thể được loại bỏ khi đủ điều kiện an toàn, tùy repaired state, overlap và `gc_grace_seconds`/các chế độ mới theo phiên bản. Đừng ép chạy `nodetool compact` liên tục trên production để làm metric đẹp; compaction nhân tạo có thể khiến test khác tải thực và làm đĩa cạn.

### 6.5. Disk free space cũng là giới hạn compaction

Compaction cần **đọc SSTables cũ và ghi SSTables mới** trước khi giải phóng đầu vào; temporary space overhead phụ thuộc strategy và task. Nếu disk đã đầy, compaction có thể fail hoặc gây domino:

~~~text
Heavy writes -> nhiều SSTables
             -> compaction cần thêm disk
             -> disk available giảm
             -> compaction fail/backlog tăng
             -> read amplification + latency tăng
             -> retries tăng -> tải lại tăng
~~~

Thử nghiệm tải phải có **disk headroom**, không chỉ CPU/RAM. Không chạy stress đến cạn đĩa của cluster chia sẻ hoặc production.

## 7. Định nghĩa trạng thái đo: COLD, WARMING, STEADY, SATURATING, RECOVERING

| State | Dấu hiệu | Có đưa vào KPI nào? |
|---|---|---|
| **COLD** | JVM/driver mới, ít truy cập hot keys, cache chưa đại diện | Cold-start latency/SLA |
| **WARMING** | Hit ratio, JIT/CPU, SSTables/flush thay đổi nhanh | Time-to-warm, transient cost |
| **STEADY** | Throughput đạt target; latency, errors, cache churn, backlog **không trôi xu hướng** | Steady-state capacity/SLO |
| **SATURATING** | Queue/in-flight/disk await/backlog tăng cùng p99, QPS không tăng tương ứng | Saturation knee/capacity limit |
| **FAULTED** | Node/rack/latency failure, CL không đạt hoặc retries tăng | Availability/failure window |
| **RECOVERING** | Node UP nhưng cache nguội/streaming/repair/compaction backlog tăng | Recovery SLO, warm-up sau fault |
| **POST-RECOVERY STEADY** | CL/data oracle/SLO và background work trở về trạng thái đại diện | Return-to-service criteria |

**Một trạng thái có thể khác nhau theo query family và node.** Hot partition trên node A có cache nóng, còn read qua replica B hoặc C sau failover có thể chậm như cold start. Client pool trên service pod mới cũng có thể cold dù Cassandra replicas vẫn warm.

### 7.1. State transitions và yếu tố gây nhiễu

~~~text
COLD --warm workload--> WARMING --gate PASS--> STEADY
                             |                    |
                   compaction/backlog?           | fault
                             v                    v
                         SATURATING <-------- FAULTED
                             |                    |
                         backpressure             v
                             |                RECOVERING
                             |                    |
                             +----> STEADY <------+
                                       |
                               POST-RECOVERY REPORT
~~~

Không nên gắn nhãn `STEADY` cho một đoạn số liệu chỉ vì **thời gian warm-up cấu hình đã hết**. Phải có các cửa sổ giám sát đủ dài và đo được sự ổn định.

### 7.2. Đừng nhầm “cache steady” với “data steady”

- Cache hit/miss tạm ổn định nhưng writes mới vẫn tạo SSTables và compaction backlog tăng.
- Compaction backlog ổn định nhưng cache đang thrash vì working set lớn hơn RAM.
- Cả cache/compaction ổn định nhưng Java application đang GC/JIT hoặc connection retries nhiều.
- Cả client/server ổn định nhưng CL đang bị **hạ** so với yêu cầu nghiệp vụ.

Do đó **steady-state gate** phải là hội của nhiều điều kiện, không chỉ một chỉ số.

## 8. Thiết kế steady-state gate bằng rolling windows

### 8.1. Một gate minh họa có thể đo được

Giả sử một workload staging read/write 70/30 mục tiêu **2.000 CQL logical requests/s**, latency SLO p99 tối đa **80 ms**, CL `LOCAL_QUORUM`, RF3 trong một DC. Các con số dưới đây là **ví dụ để học cách đặt gate**, không phải default đúng cho mọi cluster:

| Điều kiện | Cách đo | Ví dụ threshold cho lab |
|---|---|---|
| Throughput | Số completed requests/giây theo query mix | Trong ±5% target ở **5 cửa sổ 60s** liên tiếp |
| Latency | p95/p99 từng query family, histogram đủ mẫu | p99 không vượt 80ms; giữa các cửa sổ không trôi xu hướng |
| Error/timeout | Errors, `UNAVAILABLE`, read/write timeout, client timeout | Không tăng bất thường; lỗi nghiệp vụ = 0 |
| Key/row/chunk cache | Hit ratio, entries, evictions theo node | Thay đổi nhỏ/không có churn mạnh, hoặc ghi rõ warm set lớn hơn cache |
| SSTables-per-read | Histogram/quartiles theo table | Không tăng đều trong các cửa sổ |
| Compaction backlog | Pending tasks/bytes, throughput, age | Không tích lũy liên tục; có thể >0 |
| Memtable flush | Flush queue và bytes/giây | Có chu kỳ đại diện; queue không tăng mãi |
| Disk | Read/write IOPS, throughput, await, free space | Có headroom, không bão hòa kéo dài |
| CPU/GC | CPU%, GC pause, allocation | Không có pause/CPU saturation làm p99 vọt |
| Driver/client | Pool in-flight, retries, connection churn, JVM GC | Không trôi, request profile/CL không bị đổi |

**Phải kiểm số lượng mẫu đủ cho p99.** Nếu một query family có 100 requests trong một cửa sổ, p99 gần như một quan sát cực đoan duy nhất; không báo độ chắc chắn như khi có 100.000 requests. Với low-QPS, mở rộng cửa sổ hoặc báo phân phối/raw samples thay vì ép p99 chính xác giả.

### 8.2. Cách đánh giá “không trôi” thay vì nhìn một snapshot

Giả sử pending compactions qua 5 phút:

~~~text
Window 1:  10
Window 2:  12
Window 3:  10
Window 4:  11
Window 5:  10
=> dao động quanh một mức; có thể ổn định.

Window 1:  10
Window 2:  25
Window 3:  50
Window 4:  85
Window 5: 130
=> backlog tích lũy; chưa gọi steady.
~~~

Không chỉ nhìn `PendingTasks`; một task 100MB và một task 100GB khác nhau rất lớn. Dùng **bytes remaining/throughput** khi phiên bản cung cấp, kết hợp SSTable counts/levels, disk await và trend p99.

### 8.3. Rolling-window gate tránh hiệu ứng chu kỳ

Flush/compaction có thể diễn ra theo chu kỳ. Nếu chỉ lấy cửa sổ **30 giây đúng lúc compaction nghỉ**, latency sẽ “đẹp” nhưng không phản ánh 10 phút tiếp theo. Chọn thời gian đo bao phủ **ít nhất vài chu kỳ hoạt động** mà workload và hardware dự kiến tạo ra; lưu raw timeline với mốc compaction start/finish.

Ví dụ:

~~~text
00:00-05:00  preload/cold state
05:00-11:00  warm-up
11:00-16:00  rolling steady gate
16:00-36:00  đo chính
36:00-...    kiểm drain/recovery

Chỉ dùng các mốc này nếu metrics xác nhận trạng thái phù hợp.
~~~

Nếu compaction strategy TWCS có window hàng ngày hoặc TTL dài, bài test 20 phút không thể bao phủ lifecycle đầy đủ. Kết quả cần ghi **coverage gap**.

### 8.4. Gate khác nhau cho read-heavy và write-heavy

**Read-heavy:** ưu tiên working-set coverage, page cache, key cache, SSTables-per-read, tombstones, read p99.  
**Write-heavy:** ưu tiên sustained bytes/s, memtable flush cycles, commitlog latency, compaction backlog, disk free space, write p99.  
**Mixed workload:** đo **cả read và write p99**; một metric toàn cục có thể che việc read p99 xấu trong lúc throughput write tốt.

### 8.5. Đủ mẫu và uncertainty

Không so p99 của hai giai đoạn có khác biệt quá lớn về request mix. Cần ghi:

- **Count** và **duration** từng cửa sổ.
- Histogram bins/precision và tool tính percentile (HDR Histogram, Prometheus histogram, driver timer).
- Scope **client end-to-end** hay **server coordinator**.
- Attempt/retry count và timeouts (những request lỗi không có success latency có thể bị bỏ khỏi histogram).
- Workload generator có phát theo target open-loop hay chỉ “cố gửi hết” closed-loop.

Một p99 thành công giảm trong khi **timeouts tăng** không phải performance improvement. Nếu các request chậm nhất đã fail và bị loại khỏi latency histogram, cần báo **error rate và timeout counts** cùng p99.

## 9. Working set, hit ratio và sự khác biệt hot-key/uniform-key

### 9.1. Working set không bằng tổng dung lượng table

**Working set** là những keys/partitions/pages được truy cập đủ thường xuyên trong một cửa sổ để tác động cache. Table 2TB có thể có hot working set 2GB; table 20GB nhưng workload random uniform trên nhiều columns/pages có thể buộc hệ thống đọc phần lớn dataset.

~~~text
Production:
  table size       = 1 TB
  top 1% partitions = 70% reads
  24h distinct PKs = 4,000,000

Benchmark giả:
  table size       = 1 TB (seed đủ)
  100 fixed keys   = 100% reads
  ==> cache hit quá cao, p99 quá tốt
~~~

Tạo đủ dung lượng **trên đĩa** nhưng query chỉ 100 khóa sẽ vẫn là một benchmark “hot-cache-only”. Hãy đo/tạo **phân phối keys thật**.

### 9.2. Uniform, Zipfian và churn

| Pattern | Đặc trưng | Hệ quả |
|---|---|---|
| Uniform random | Mỗi key gần như đồng xác suất | Hit ratio thấp hơn nếu working set lớn |
| Zipfian/hotspot | Ít keys được đọc nhiều | Cache và replica hotspots rất rõ |
| Sequential/range | Keys gần nhau hoặc clustering slice | Prefetch/page locality khác point read |
| Temporal locality | Key vừa ghi được đọc lại | Memtable/page cache dễ làm query nhanh |
| Churned hot set | Hot keys đổi theo giờ/ngày | Warm-up của hôm qua không đại diện hôm nay |
| Multi-tenant skew | Tenant lớn chiếm nhiều traffic | Partition hotspot, noisy neighbors |

**Đừng cố ý gây một hot partition cực lớn** để làm “cache nóng” rồi đo throughput toàn cluster. Nó có thể bão hòa một số natural replicas trong khi các nodes khác idle; đây là thí nghiệm **hotspot failure** riêng.

### 9.3. Tính nhanh số keys đã có cơ hội được chạm

Giả sử uniform random trên **N=1.000.000 keys**, chạy **m=300.000** độc lập point reads. Kỳ vọng số keys distinct đã truy cập xấp xỉ:

\[
E[D] = N\left(1-\left(1-\frac{1}{N}\right)^m\right)
\approx N\left(1-e^{-m/N}\right).
\]

Thay số:

\[
E[D] \approx 10^6(1-e^{-0.3}) \approx 259{,}182.
\]

**Chỉ khoảng 26% keys** đã được chạm ít nhất một lần theo mô hình đó. Không thể gọi “đã warm toàn bộ 1 triệu keys” chỉ vì chạy 5 phút tại 1.000 reads/s. Đây mới chỉ là keys, chưa tính pages/index chunks và bộ dữ liệu có thể lớn hơn RAM.

### 9.4. Nếu working set lớn hơn bộ nhớ khả dụng

Ví dụ:

~~~text
Hot disk pages cần thường xuyên: 40 GiB
Memory khả dụng cho OS page cache: 16 GiB

Không có warm-up duration nào khiến 40 GiB cùng nằm
trong 16 GiB cache một cách bền vững.
~~~

Trạng thái đúng lúc này là **steady cache turnover/thrashing tùy pattern**, có thể đo bằng hit/miss và disk reads ổn định. Đừng “đợi tới khi hit ratio 95%” nếu xác suất/capacity thực tế không thể đạt.

### 9.5. Data growth/TTL làm working set dịch chuyển

Với time-bucketed tables, một workload thực có thể ưu tiên “today” và “last 7 days”, trong khi test seed tất cả rows vào ngày cũ. TWCS/TTL/partition bucketing có thể làm kết quả sai hoàn toàn. Cần seed theo **event time/ingest time/late arrivals** và query mix. Dù mục tiêu là Cassandra engine, test dữ liệu nên phản ánh **mô hình wide-column theo truy vấn**.

## 10. Open-loop vs closed-loop: warm-up có thể che saturation

### 10.1. Closed-loop clients

~~~text
N workers:
  send request
  wait response
  then send next

Throughput bị giới hạn bởi number of workers và latency.
Khi Cassandra chậm, clients tự gửi ít hơn.
~~~

Closed-loop có ích để tìm maximum throughput với concurrency cố định nhưng có thể bị **coordinated omission**: khi server chậm 2 giây, generator không phát số requests mà workload real-time lẽ ra vẫn đến trong hai giây.

### 10.2. Open-loop arrivals

~~~text
Arrival schedule: 1000 requests/s bất kể latency
  t=0, 1ms, 2ms, ...

Nếu server chậm, queue/in-flight tăng.
Phải có bounded queue/admission/deadline.
~~~

Open-loop có thể gần hơn với API QPS theo thời gian, nhưng khi thiếu backpressure/rate cap dễ làm cluster quá tải. Chỉ thực hiện trong staging capacity plan có **hard stop** và metric client queue.

### 10.3. Little's Law không dùng p99 thay mean

Trong ổn định, số requests trung bình đang phục vụ/chờ:

\[
L = \lambda W
\]

với `λ` là arrival/throughput trung bình và `W` là **response time trung bình**. Ví dụ 1.000 req/s và mean latency 20ms, `L≈20` in-flight requests trên phạm vi cùng đo. **Không** lấy p99=200ms để suy “L=200” như một đẳng thức; p99 là tail, không phải mean.

Nếu backlog tăng liên tục, điều kiện steady-state của Little's Law không còn được thỏa một cách thực tế. Khi đó đo queue growth/overload trực tiếp, không dùng công thức để “chứng minh capacity”.

### 10.4. Nhớ giới hạn client

Ứng dụng Java có thể là bottleneck trước Cassandra:

- JVM GC, thread pool/Netty event loops.
- Driver request throttler, connection pool in-flight, max streams, retry/speculation.
- Serialization/codec, TLS/auth overhead.
- Load generator CPU hoặc network/NIC saturation.
- Logging/tracing quá nặng.

Vì vậy warm-up client **và** server phải đo riêng. Một kết quả QPS thấp chưa chắc là giới hạn của compaction; có thể load generator đã đạt CPU 100%.

## 11. Hệ thống metrics: phải thấy cả cache, SSTables và compaction

### 11.1. Nguồn dữ liệu đo

| Nguồn | Thu gì? | Không dùng nó để kết luận gì? |
|---|---|---|
| Load generator/JMeter/Gatling/NoSQLBench | Offered load, completed QPS, p50/p95/p99, errors | Không tự suy Cassandra-only latency |
| Java Driver 4.x metrics | Session CQL requests, per-node messages, pool in-flight, retries/client timeouts | Không tự thay server compaction metrics |
| Cassandra JMX/Metrics | Read/write latency, key/row cache, memtable, SSTables-per-read, compaction, pending | Không biết toàn bộ HTTP business SLO |
| `nodetool info/tablestats/compactionstats/tpstats` | Snapshot node/table/threadpool/task state | Không thay histogram liên tục 1 phút |
| Host metrics | CPU, RSS, GC, disk IOPS/await, page faults, network | Không xác minh expected value/CL |
| Business correctness probes | Read/write CL và data oracle | Không đo saturation toàn cluster |

Không trộn **client p99** (có pool queue/network/retry) với **coordinator read latency** (server-side) thành một số bằng cách lấy hiệu hai percentiles. Percentiles lấy từ hai tập mẫu khác nhau **không được trừ** để suy chính xác network time.

### 11.2. Những metric Cassandra cần hiểu

| Nhóm | Metric/tên thường gặp | Câu hỏi cần trả lời |
|---|---|---|
| Cache | `KeyCacheHitRate`, `KeyCacheHits`, `KeyCacheRequests` | Lookup partition/index đang hit nhiều hơn hay chỉ workload hot key giả? |
| Cache | `RowCacheHitRate`, `RowCacheHits` | Row cache có bật? Hit theo key distribution thật? |
| Cache | Chunk cache hit/miss/capacity nếu có | Page/chunk cache warm hay thrash? |
| Table read | `ReadLatency`, `SSTablesPerReadHistogram` | Read amp và tail latency có thay cùng nhau? |
| Table write | `WriteLatency`, memtable size/pending flushes | Write path có nghẽn do flush không? |
| SSTables | `LiveSSTableCount`, disk space live/total | Data/SSTables có đang tăng vô hạn? |
| Compaction | `PendingTasks`, `BytesCompacted`, active tasks, throughput | Merge có theo kịp write/TTL lifecycle? |
| Tombstones | Tombstone scanned histogram, warnings/failures | Có read amp do tombstone density? |
| Coordinator | ClientRequest Read/Write Latency, Timeouts, Unavailables | CL request thất bại vì replica? |
| JVM/host | GC pause, CPU%, disk await, I/O bytes/s | Cache/compaction có cạnh tranh tài nguyên? |

**Lưu ý tên metric:** JMX MBeans có thể nằm dưới `org.apache.cassandra.metrics` với scope `Cache`, `Table` hoặc `Compaction`; khác tên mà Grafana/Prometheus exporter hiển thị. Cassandra version, metrics exporter và configuration quyết định metric nào có thật. **Đối chiếu JMX/endpoint thực**; đừng viết alert tham chiếu series chưa xuất.

### 11.3. `nodetool` commands không phá dữ liệu

~~~bash
# Chỉ trong Cassandra lab/staging được cấp quyền
nodetool status
nodetool info
nodetool tablestats perf_lab.events_by_tenant_day
nodetool compactionstats
nodetool tpstats
nodetool netstats
nodetool gcstats
~~~

Ý nghĩa:

- `nodetool info` cho snapshot cache sizes/hits và trạng thái node.
- `nodetool tablestats` cho per-table SSTable count, latency, disk usage, bloom filters, tombstone metrics tùy version.
- `nodetool compactionstats` cho active/pending compaction tasks và throughput.
- `nodetool tpstats` cho thread pool active/pending/dropped messages.
- `nodetool status` cho ring/gossip, không chứng minh data phục vụ đúng CL.

Các lệnh là **quan sát read-only** theo mục đích; không thay thế việc thu metrics đều đặn qua thời gian. Một snapshot 0 pending tasks khi test kết thúc **không** chứng minh trong 20 phút trước đó compaction không làm p99 tăng.

### 11.4. Tách metric theo node, table và query family

~~~text
query_family = events.byTenantDay
table        = perf_lab.events_by_tenant_day
CL           = LOCAL_QUORUM
DC           = dc1

client:
  request latency p99 / throughput / timeout/retry

node A:
  key cache hit rate, SSTables-per-read, compaction bytes/s

node B:
  same metrics

node C:
  same metrics
~~~

Nếu chỉ đo node A, trong khi partitions hot chủ yếu nằm ở B/C, sẽ đọc sai cache state. Với CL `LOCAL_QUORUM`, coordinator có thể dùng nhiều replicas để hoàn tất request, nên cần **per-node** charts và phân phối token.

### 11.5. Prometheus — ví dụ tư duy, không phải series names có sẵn

Giả sử exporter ánh xạ tới counters/latency histograms cụ thể, một báo cáo nên tính:

\[
qps = \frac{\Delta \text{completed requests}}{\Delta t},\quad
timeoutRate = \frac{\Delta \text{timeouts}}{\Delta \text{requests}}.
\]

Nếu Prometheus histogram có buckets `*_bucket` chuẩn, có thể dùng `histogram_quantile(0.99, sum by (le, query_family)(rate(..._bucket[5m])))`. Nhưng Java driver có thể xuất timer dưới dạng summary/snapshot hoặc custom registry, không nhất thiết là Prometheus histogram. **Không copy nguyên PromQL giả vào production mà không kiểm series đã được export**.

### 11.6. Một log sample có thể replay

~~~text
run_id=lab-2026-11-21-r1
phase=WARMING
query_family=events.byTenantDay
CL=ONE
target_rps=500
completed_rps=490
latency_p95_ms=18.1
latency_p99_ms=39.6
key_cache_hit_rate=0.74
sstables_per_read_p95=4
pending_compactions=12
disk_read_mb_s=80
disk_write_mb_s=45
gc_pause_ms_per_min=80
~~~

Các số là **dữ liệu giả minh họa format**, không phải kết quả đã chạy. Với production, không log raw partition keys, user IDs, payment IDs hoặc PII; dùng query family/CL/DC/status low-cardinality labels và trace IDs đã được kiểm soát.

## 12. Một experiment manifest phải ghi gì?

### 12.1. Phần môi trường

~~~yaml
experiment:
  id: cassandra-warm-cache-v1
  purpose: compare cold_and_steady_reads
  environment: isolated_staging
  cassandra_version: "5.0.x"
  java_driver_version: "4.18.x"
  topology:
    dcs: {dc1: 3}
    full_rf: 3
    consistency_read: LOCAL_QUORUM
    consistency_write: LOCAL_QUORUM
  hardware:
    cpu_cores_per_node: 8
    memory_gib_per_node: 32
    disk_type: dedicated_ssd
    disk_headroom_target_percent: 30
  table:
    compaction: STCS
    compression: enabled
    row_cache: disabled
    keys: 5000000
    ttl: none
  workload:
    read_percent: 70
    write_percent: 30
    access_distribution: zipf_like
    target_rps: 2000
    page_size: 100
    bounded_inflight: true
  phases:
    baseline_seconds: 120
    warmup_minimum_seconds: 300
    warmup_maximum_seconds: 1800
    steady_window_seconds: 60
    steady_windows_required: 5
    measure_seconds: 1200
  checks:
    record_cache_metrics: true
    record_sstable_and_compaction_metrics: true
    verify_data_oracle: true
    abort_on_disk_pressure: true
~~~

Đây là một **manifest minh họa trong Markdown**, không phải cấu hình chuẩn Cassandra hay file cần tạo. Những giá trị phải điều chỉnh cho cluster, SLO, active dataset và quyền vận hành; không dùng `30% disk headroom` làm định mức chung khi compaction strategy hoặc deployment khác.

### 12.2. Những biến phải giữ nguyên khi so sánh A/B

| Nhóm | Giữ hoặc báo riêng |
|---|---|
| Topology | Node count, DC/rack, RF, CL, token ownership |
| Software | Cassandra, JDK, driver, JVM flags, GC, OS/kernel |
| Hardware | CPU/RAM/storage class, noisy neighbors, network |
| Cassandra | Memtable/commitlog/cache sizes, compaction strategy, compression |
| Dataset | Số partitions, rows/partition, bytes/row, TTL, tombstones, timestamp age |
| Workload | Query mix, QPS schedule, concurrency, key distribution, page size |
| Timeline | Preload/flush/compaction, warm-up start, measure, fault, recover |
| Metrics | Histogram backend, sampling resolution, error handling |
| Driver | Consistency, timeout, retries, speculative execution, pooling |
| State | Cold/warm cache, SSTables count/levels, pending compactions |

Chỉ một biến khác nhau? Thực tế vẫn phải đo **độ bất định**. Randomize thứ tự A/B hoặc chạy nhiều lần trên cùng điều kiện có reset được xác minh; tránh luôn chạy B sau A khi B được hưởng cache nóng do A.

### 12.3. Ưu tiên dataset đã seed ổn định

Nếu mục tiêu so **read latency**, cần seed dataset trước, để dữ liệu/compaction đạt trạng thái phù hợp rồi mới warm reads. Nếu đang đo **mixed read/write steady state**, phải để writes tiếp tục qua giai đoạn đo và tính compaction như một phần workload, không chỉ dừng writes để compaction hết rồi mới đo read.

Hai câu hỏi khác nhau:

~~~text
Q1: Read-only query trên dataset đã ổn định nhanh thế nào?
Q2: Cùng query khi continuous writes/flush/compaction diễn ra nhanh thế nào?
~~~

Không thể trả lời Q2 bằng phép thử Q1 rồi thêm vài giây writes lúc cuối.

## 13. Phân pha thí nghiệm chuẩn: preflight → seed → warm → measure

### 13.1. Preflight gate

- Confirm environment **không phải production**, có owner/stop authority.
- Kiểm cluster nodes `UN` hoặc expected degraded mode, không có bootstrap/repair ngoài kế hoạch.
- Chốt RF/CL/table schema/compaction strategy và driver local DC.
- Xác nhận disk free, CPU/memory, traffic isolation và generator capacity.
- Baseline errors/timeouts/retries/GC, table SSTable count, caches, compaction backlog.
- Kiểm query correctness trên known-key sentinel, không chỉ `SELECT system.local`.
- Có kill switch/rate cap/bounded in-flight và alert abort khi disk/latency xấu.

### 13.2. Seed/preload

1. Tạo data đúng partition/cardinality/time/TTL, không chỉ tạo một hot partition.
2. Verify row counts bằng **source manifest/sampled known keys**, không dùng `COUNT(*)` toàn bảng hàng giờ.
3. Quan sát flush/SSTable generation và compaction của giai đoạn seed.
4. Chờ hoặc mô tả **preload stabilization** trước phép đo mục tiêu.
5. Chụp snapshot metrics trước warm-up.

### 13.3. Warm-up đúng query mix

1. Khởi chạy generator ở **rate có kiểm soát**, ví dụ tăng từ 20% → 50% → 100% target.
2. Dùng distribution hot/cold và mix read/write đại diện.
3. Đo **client app JVM/driver**: prepared/pool/JIT/GC.
4. Đo **Cassandra replicas**: cache hit/churn, disk reads, SSTables-per-read.
5. Đo **write path**: flush/compaction backlog qua nhiều windows.
6. Chỉ chuyển đo khi steady-state gate PASS; nếu hết max warmup budget mà không PASS, báo **NOT_STEADY**, không che số liệu.

### 13.4. Measurement

~~~text
Warm-up gate PASS
   |
Start measurement window + mark timestamp
   |
Keep target distribution/rate and CL unchanged
   |
Collect p50/p95/p99 + success/errors/timeouts
   |
Collect node/cache/flush/SSTable/compaction metrics
   |
Collect data-correctness canaries
   |
Stop generator safely at end
   |
Continue observe backlog drain if relevant
~~~

**Không chuyển workload từ 500RPS/100 hot keys trong warm-up sang 5.000RPS/1 triệu keys khi measurement bắt đầu** rồi giả định caches đã tương ứng nóng. Nếu mục tiêu là *cold-miss shock*, hãy ghi rõ đó là transition đang được đo.

### 13.5. So sánh giai đoạn bằng timestamp và dữ liệu thô

Giữ riêng:

~~~text
boot_phase.csv
seed_phase.csv
warmup_phase.csv
steady_phase.csv
fault_phase.csv
recovery_phase.csv
~~~

Tên file ở đây là **minh họa cách tách kết quả**, không yêu cầu tạo file trong repository. Có thể dùng Prometheus recording rules, time range tags hoặc test harness metadata tương đương. Không xóa số liệu warm-up chỉ vì chúng xấu; báo chúng ở mục cold/warm/recovery để minh bạch.

## 14. Lab A — CQL: hot partition và tập partition đa dạng

**Mục tiêu:** Tạo dữ liệu nhỏ để minh họa **hot-key repetition** và **đọc phân tán**, chứng minh query correctness trước khi đo độ trễ. Lab này **không đủ dữ liệu để benchmark OS page cache hoặc compaction**: 16 rows có thể vừa một page, không đại diện GB/TB. Các phần stress/soak ở mục sau mới phục vụ đo tải thật.

### 14.1. Môi trường

- Apache Cassandra 4.1 hoặc 5.0, **một node lab**.
- `cqlsh` và quyền tạo keyspace/table riêng; không dùng production keyspace.
- Java Driver 4.x nếu chạy Lab B.
- Dùng `ONE` trên RF1; đo RF3/`LOCAL_QUORUM` phải dùng multi-node fixture thật.
- Không chạy nhiều load generators cạnh tranh trên một máy dev yếu rồi gọi kết quả “Cassandra capacity”.

### 14.2. Tạo schema đơn giản, đúng partition key

~~~sql
CREATE KEYSPACE IF NOT EXISTS perf_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS perf_lab.events_by_tenant_day (
  tenant_id text,
  event_day date,
  event_id uuid,
  status text,
  score int,
  received_at timestamp,
  PRIMARY KEY ((tenant_id, event_day), event_id)
) WITH CLUSTERING ORDER BY (event_id ASC)
  AND compaction = {
    'class': 'SizeTieredCompactionStrategy'
  };

CONSISTENCY ONE;
~~~

**Mô hình:** `(tenant_id,event_day)` là composite partition key, `event_id` là clustering key. Thực hiện point lookup/range-in-partition, tránh `ALLOW FILTERING` khi so sánh warm-up để không trộn full scan với hiệu ứng cache. STCS được chọn **cho lab**, không phải lời khuyên mặc định cho tất cả workload.

### 14.3. Seed 8 rows ở một hot partition

~~~sql
INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000001,'OK',1,
        '2026-11-21T00:00:01Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000002,'OK',2,
        '2026-11-21T00:00:02Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000003,'OK',3,
        '2026-11-21T00:00:03Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000004,'OK',4,
        '2026-11-21T00:00:04Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000005,'OK',5,
        '2026-11-21T00:00:05Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000006,'OK',6,
        '2026-11-21T00:00:06Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000007,'OK',7,
        '2026-11-21T00:00:07Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000008,'OK',8,
        '2026-11-21T00:00:08Z');
~~~

### 14.4. Seed 8 rows trên 8 partitions khác

~~~sql
INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-01','2026-11-21',
        00000000-0000-0000-0000-000000000001,'OK',101,
        '2026-11-21T00:01:01Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-02','2026-11-21',
        00000000-0000-0000-0000-000000000002,'OK',102,
        '2026-11-21T00:01:02Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-03','2026-11-21',
        00000000-0000-0000-0000-000000000003,'OK',103,
        '2026-11-21T00:01:03Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-04','2026-11-21',
        00000000-0000-0000-0000-000000000004,'OK',104,
        '2026-11-21T00:01:04Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-05','2026-11-21',
        00000000-0000-0000-0000-000000000005,'OK',105,
        '2026-11-21T00:01:05Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-06','2026-11-21',
        00000000-0000-0000-0000-000000000006,'OK',106,
        '2026-11-21T00:01:06Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-07','2026-11-21',
        00000000-0000-0000-0000-000000000007,'OK',107,
        '2026-11-21T00:01:07Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-08','2026-11-21',
        00000000-0000-0000-0000-000000000008,'OK',108,
        '2026-11-21T00:01:08Z');
~~~

### 14.5. Hai kiểu query cần so sánh

~~~sql
-- Point lookup (hot key; thử gọi lại cùng statement)
SELECT event_id, status, score
FROM perf_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-hot'
  AND event_day = '2026-11-21'
  AND event_id =
      00000000-0000-0000-0000-000000000001;

-- Một partition range/scan có giới hạn
SELECT event_id, status, score
FROM perf_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-hot'
  AND event_day = '2026-11-21'
LIMIT 8;

-- Một partition khác (nếu chuyển lần lượt tenant-01..08)
SELECT event_id, status, score
FROM perf_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-08'
  AND event_day = '2026-11-21';
~~~

**Expected:** Point lookup trả score=1; range hot partition trả 8 rows, tenant-08 trả một row score=108. Nếu không đúng, **dừng benchmark trước**: không so latency của query sai. Đừng gộp point lookup với range scan vào một p99 duy nhất.

### 14.6. Ghi chú về cache trên dataset nhỏ

Với 16 rows, gần như chắc working set quá nhỏ để phân biệt physical disk cold/warm ổn định. Chỉ dùng lab này để tập:

- Giữ nguyên statement/query family và CL.
- Phân biệt hot key vs coldish keys về **phân phối**, không tuyên bố kết quả vật lý.
- Kiểm CQL shape/partition key và expected values.
- Hiểu vì sao benchmark thật cần **hàng triệu partitions và GB dữ liệu** để tạo cache misses đại diện.

Không chạy `nodetool invalidatekeycache`, thay cache capacity, drop OS page cache hoặc restart node trên shared cluster để làm một thí nghiệm 16 rows “cold”.

## 15. Lab B — Java Driver 4.x: warm-up và đo point-read có giới hạn

### 15.1. Mục tiêu và nguyên tắc

Ví dụ Java 17 sau **không benchmark capacity**. Nó cho người học:

1. Prepare CQL một lần, dùng một `CqlSession` xuyên suốt.
2. Tạo cùng query shape cho tất cả requests.
3. Kiểm đúng row/score; không âm thầm tính latency của response rỗng.
4. Tách **vòng warm-up** khỏi **vòng đo** và ghi kết quả latency p50/p95/p99.
5. Chạy hai access patterns có control rõ ràng.

Với lab nhỏ, p99 phần lớn chỉ là nhiễu của JIT/OS scheduler/Java overhead, không được gọi là “Cassandra p99 production”. Muốn load test thật, chạy concurrency, dataset và duration đại diện, dùng histogram có sample count và saturation metrics.

### 15.2. Chương trình Java 17 đầy đủ

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.Arrays;
import java.util.UUID;

public final class CassandraWarmupLab {
    private CassandraWarmupLab() {}

    static final LocalDate DAY = LocalDate.parse("2026-11-21");
    static final UUID HOT_ID = UUID.fromString(
        "00000000-0000-0000-0000-000000000001");

    record Stats(String name, int samples,
                 double p50Ms, double p95Ms, double p99Ms,
                 double maxMs) {}

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement point = session.prepare(
                "SELECT score FROM perf_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? " +
                "AND event_id = ?");

            // Pattern A: cố tình hot key, warm-up rồi measure.
            BoundStatement hot = point.bind(
                    "tenant-hot", DAY, HOT_ID)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            warm(session, hot, 500);
            Stats hotStats = measure(
                "hot-point-read", session, point, true, 1000);
            System.out.println(hotStats);

            // Pattern B: đi qua 8 partitions khác nhau,
            // nhưng vẫn là dataset QUÁ NHỎ cho cache benchmark.
            warmVaried(session, point, 500);
            Stats variedStats = measure(
                "varied-point-read", session, point, false, 1000);
            System.out.println(variedStats);

            System.out.println(
                "Do not compare as real cold-vs-warm capacity");
        }
    }

    static BoundStatement select(
            PreparedStatement p, boolean hot, int i) {
        if (hot) {
            return p.bind("tenant-hot", DAY, HOT_ID)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);
        }

        int id = i % 8 + 1;
        String tenant = String.format("tenant-%02d", id);
        UUID eventId = UUID.fromString(String.format(
            "00000000-0000-0000-0000-%012d", id));
        return p.bind(tenant, DAY, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setIdempotent(true);
    }

    static void warm(
            CqlSession s, BoundStatement b, int iterations) {
        for (int i = 0; i < iterations; i++) {
            Row row = s.execute(b).one();
            if (row == null || row.getInt("score") != 1) {
                throw new IllegalStateException(
                    "Wrong hot key/value during warmup");
            }
        }
    }

    static void warmVaried(
            CqlSession s, PreparedStatement p, int iterations) {
        for (int i = 0; i < iterations; i++) {
            Row row = s.execute(select(p, false, i)).one();
            int expected = i % 8 + 101;
            if (row == null || row.getInt("score") != expected) {
                throw new IllegalStateException(
                    "Wrong varied key/value during warmup");
            }
        }
    }

    static Stats measure(
            String name, CqlSession s, PreparedStatement p,
            boolean hot, int iterations) {

        long[] nanos = new long[iterations];
        for (int i = 0; i < iterations; i++) {
            BoundStatement req = select(p, hot, i);
            long t0 = System.nanoTime();
            Row row = s.execute(req).one();
            nanos[i] = System.nanoTime() - t0;

            int expected = hot ? 1 : (i % 8 + 101);
            if (row == null || row.getInt("score") != expected) {
                throw new IllegalStateException(
                    "Data oracle failed during measurement");
            }
        }

        Arrays.sort(nanos);
        return new Stats(name, iterations,
            nthMs(nanos, 0.50), nthMs(nanos, 0.95),
            nthMs(nanos, 0.99), nanos[iterations - 1] / 1e6);
    }

    static double nthMs(long[] sorted, double percentile) {
        int index = Math.max(0, Math.min(sorted.length - 1,
            (int) Math.ceil(percentile * sorted.length) - 1));
        return sorted[index] / 1e6;
    }
}
~~~

### 15.3. Cách đọc kết quả lab

Output giả định:

~~~text
Stats[name=hot-point-read, samples=1000,
      p50Ms=1.8, p95Ms=3.1, p99Ms=5.5, maxMs=9.1]
Stats[name=varied-point-read, samples=1000,
      p50Ms=2.0, p95Ms=3.8, p99Ms=6.7, maxMs=13.0]
Do not compare as real cold-vs-warm capacity
~~~

Các số chỉ là **ví dụ minh họa định dạng**, không phải benchmark đã chạy. Nếu hot nhanh hơn varied, không thể suy cache/compaction là nguyên nhân duy nhất vì app allocation (`String.format`/`UUID.fromString`), network scheduling và key placement cũng khác. Benchmark production cần workload harness chuẩn, histogram đủ mẫu, cùng offered load, CPU/RAM/IO metrics.

### 15.4. Vì sao code synchronous hữu ích nhưng không đo maximum throughput?

Vòng lặp trên gửi **một request rồi chờ hoàn thành** — closed-loop concurrency ≈1. Nó dùng tốt để dạy **warm-up vs measurement và data correctness**, không thử được saturation knee, pool backpressure hoặc concurrent compactions dưới tải nặng. Ứng dụng Java production thường cần:

- `executeAsync` với giới hạn in-flight/backpressure phù hợp.
- Prepared statements reuse, typed CQL values.
- Histogram/timer theo **query family**, không raw user ID.
- Workload generator tách khỏi Cassandra host để không tranh CPU/disk.
- CL/RF/DC đúng production, không dùng RF1/ONE lab rồi ngoại suy.

### 15.5. Một bẫy khi đo p99 trong mã demo

Mã đang đo **từ trước `session.execute` tới lúc nhận row**, bao gồm công việc Java xây result, network/driver/coordination. Nó **không** đo thuần server SSTable read time và không tính chi phí tạo `BoundStatement` ngay trước `t0`. Nếu muốn client end-to-end, phải quyết định đo từ khi nhận request HTTP hay từ sau bind; ghi lại scope. Với request paging, đo “first page” và “full result” riêng.

## 16. Lab C — `cassandra-stress`: workload có duration và phases rõ

### 16.1. Công cụ dùng cho mục tiêu gì?

`cassandra-stress` hỗ trợ workload write/read/mixed trên schema do tool tạo và **user mode** cho schema riêng; có các tùy chọn `-pop`, `-rate`, `-node`, `-schema`, `-sample` và latency reporting. Trong tài liệu Cassandra 5.0, công cụ này được đánh dấu **deprecated** và Apache giới thiệu **NoSQLBench** là lựa chọn tốt hơn cho benchmark Cassandra mới. Xem [Cassandra Stress — Apache Cassandra](https://cassandra.apache.org/doc/stable/cassandra/tooling/cassandra-stress.html).

Vì vậy:

- **Lab cũ/đơn giản:** `cassandra-stress` hữu ích để học cách load data, warm-up và đọc histogram.
- **Benchmark nghiêm túc:** cân nhắc NoSQLBench hoặc generator phù hợp query model/Java app, pin version/workload spec và metric backend.
- **Bất kể tool:** phải giữ dataset, CL, key distribution, QPS, phase markers và server metrics như nhau khi so A/B.

### 16.2. Kiểm trợ giúp phiên bản trước khi chạy

~~~bash
cassandra-stress help
cassandra-stress help write
cassandra-stress help read
cassandra-stress help mixed
cassandra-stress help -rate
cassandra-stress help -pop
~~~

**Đây là bước bắt buộc:** flags/sub-options có thể khác giữa Cassandra versions. Đừng copy lệnh từ bài 3.x vào Cassandra 5.x mà không kiểm output `help`. Khi dùng password/TLS/JMX, áp `-mode`/`-transport`/`-credentials-file` theo tài liệu của bản đang chạy, **không hardcode secrets vào shell history**.

### 16.3. Một chuỗi lệnh minh họa trên isolated lab

~~~bash
# 1. Chỉ tạo data trong stress schema/keyspace riêng do tool quản lý.
#    KHÔNG nhắm production nodes.
cassandra-stress write n=100000 \
  -rate threads=16 \
  -node 127.0.0.1

# 2. Warm read: cùng key population đã tạo ở bước 1.
cassandra-stress read duration=5m \
  -pop dist=UNIFORM(1..100000) \
  -rate threads=16 \
  -node 127.0.0.1

# 3. Measure read với cùng distribution + concurrency.
cassandra-stress read duration=10m \
  -pop dist=UNIFORM(1..100000) \
  -rate threads=16 \
  -node 127.0.0.1
~~~

**Giải thích:**

- Các lệnh là **mẫu cú pháp minh họa**, cần xác minh help thực của tool; `UNIFORM(1..100000)` có thể tạo một workload có nhiều cache misses hơn fixed hot key nhưng vẫn chưa chắc đại diện production.
- `n=100000` giới hạn số operations seed; `duration=5m`/`10m` giới hạn thời gian chạy.
- `-rate threads=16` giới hạn mức concurrency theo công cụ; **không cố định completed QPS** nếu backend chậm. Muốn đo target RPS, dùng cấu hình throttle/rate tương thích tool version.
- Seed + read run có thể không chạm chính xác cùng số keys nếu workload generator/schema/options khác nhau; xác minh row/key population và test correctness.
- Mặc định `cassandra-stress` **không mô phỏng bảng `perf_lab.events_by_tenant_day`**. Nó dùng schema riêng trừ khi cấu hình user mode, nên không dùng kết quả trên làm benchmark của query ứng dụng.
- **Không** dùng `-pop` làm cách giả lập RF hoặc CL; đó là distribution. CL/RF phải set bằng options/schema phù hợp và xác minh thật.

### 16.4. Vì sao phải nhìn compaction trong cả ba bước?

~~~text
WRITE/SEED:
  disk writes và memtable flush tăng
  -> SSTable count/compaction backlog thay đổi

WARM READ:
  key/OS caches dần nhận hot keys
  -> đồng thời compaction từ SEED có thể còn chạy

MEASURE READ:
  muốn đo "read-only steady" thì cần biết compaction nào còn lại,
  chứ không mặc định compaction đã dừng vì generator không ghi nữa.
~~~

Nếu seed quá sát measurement, một test “cold vs warm read” có thể thực chất đo **read trong khi compaction đang chạy vs sau khi compaction xong**. Muốn đo tác động cache riêng, cần giữ compaction/IO state tương đương hoặc báo rõ confounder.

### 16.5. User mode vs built-in schema

Để stress đúng CQL/partition model của ứng dụng, dùng **user profile** (YAML) do công cụ hỗ trợ để định nghĩa:

~~~yaml
specname: events_profile
keyspace: perf_lab
table: events_by_tenant_day
# column specifications and query bindings depend on your schema:
queries:
  by_tenant_day:
    cql: "SELECT event_id, status FROM events_by_tenant_day WHERE tenant_id = ? AND event_day = ?"
    fields: samerow
~~~

Đoạn trên **chỉ là fragment giải thích mục tiêu**: profile hoàn chỉnh còn cần `columnspec`/data generators/insert definitions theo loại cột và phiên bản stress; nó **không phải file chạy được ngay**. Hãy xây và kiểm một user profile hợp lệ trên môi trường lab, seed data trước, rồi chạy workload tương ứng. Không tự tạo file profile trong bước viết Markdown này.

**Lưu ý bảo mật:** Một số ví dụ stress trên mạng dùng `truncate=once` trong user mode; đó là thao tác **xóa sạch table** và tuyệt đối không copy vào shared/prod keyspace. Chỉ dùng trên table được tạo riêng và xóa được có chủ đích.

### 16.6. Giá trị của `cassandra-stress` và giới hạn cần nêu trong report

| Hữu ích | Không tự chứng minh |
|---|---|
| Seed/load số lượng lớn vào stress schema | Query model ứng dụng có cùng partition shape |
| Đo throughput/latency với concurrency/rate | Java service end-to-end SLO |
| Thử đọc population distribution | Dữ liệu/time/TTL/tombstones đúng production |
| Điều khiển warm-up vs measure duration | Cache/compaction đã steady theo metrics |
| So sánh phiên bản/strategy có kiểm soát | Mọi tenant/token/rack chịu lỗi như production |

## 17. Thiết kế một dashboard warm-up và compaction

### 17.1. Bộ biểu đồ nên đặt cùng trục thời gian

Panel A — Offered RPS / Completed QPS / Errors / Timeouts.  
Panel B — App p50/p95/p99 theo query family và CL.  
Panel C — Java Driver logical cql-requests, node cql-messages, retries.  
Panel D — Key cache/row cache/chunk cache hit-miss, entries/evictions.  
Panel E — SSTables-per-read, live SSTables, tombstones scanned.  
Panel F — Memtable/flush pending, compaction pending/active bytes.  
Panel G — Disk read/write MB/s, IOPS/await, free space.  
Panel H — CPU/GC, Netty pool in-flight, queue, network.  
Panel I — Event markers: SEED/WARM/STEADY/FAULT/RECOVER.

Đây là **sơ đồ dashboard**, không phải yêu cầu tạo file dashboard. Các panel liên quan phải hiển thị **cùng time range**, nếu không khó xác định p99 xấu đúng lúc compaction nào bắt đầu.

### 17.2. Hãy phân biệt gauges, counters, histograms

| Loại metric | Ví dụ | Cách tính/diễn giải |
|---|---|---|
| Counter | `BytesCompacted`, total requests | `rate`/`increase` qua thời gian, không dùng giá trị tuyệt đối làm QPS |
| Gauge | `PendingTasks`, memtable size, disk free | Theo dõi level và slope/biến động |
| Histogram/timer | `ReadLatency`, driver `cql-requests` | Percentiles/quantiles với count và buckets phù hợp |
| Ratio | Key cache hits/requests | Dùng cùng time window, phân loại reads, tránh chia thiếu mẫu |
| Derived trend | SSTables count slope, backlog growth | Tăng ổn định hay tích lũy |

Ví dụ `BytesCompacted=5TB` là counter từ lúc node khởi động, **không** nghĩa compaction đang xử lý 5TB trong cửa sổ 5 phút. Cần tính delta theo timestamp và reset khi process restart.

### 17.3. Kết quả p99 đẹp nhưng hệ thống xấu dần

~~~text
Window       QPS    p99 read   PendingCompactions  Disk free
  1          2000     50ms          15               43%
  2          2000     53ms          40               40%
  3          2000     57ms          80               36%
  4          2000     65ms         150               31%
  5          2000     78ms         240               26%

SLO p99 <= 80ms: đang gần chạm ngưỡng.
Nhưng trạng thái KHÔNG STEADY vì backlog tăng nhanh.
~~~

Đây là **dữ liệu tưởng tượng** để diễn giải. Nếu chỉ nhìn 5 phút cuối, có thể đánh dấu PASS tạm nhưng sau 30 phút máy sẽ chạm ngưỡng. Phải dự báo/cảnh báo từ **trend**.

### 17.4. Độ trễ tăng do cache miss hay compaction?

| Evidence | Nghi cache miss | Nghi compaction pressure |
|---|---|---|
| Key/OS cache hits | Giảm rõ khi workload mở working set | Có thể ổn định |
| Disk read I/O | Tăng đột ngột theo misses | Có thể tăng do compaction reads |
| Disk write I/O | Không nhất thiết tăng | Thường tăng do rewrite SSTables |
| Pending compactions | Có thể không thay đổi | Thường tăng hoặc active bytes/s cao |
| SSTables-per-read | Có thể ổn định | Có thể tăng trước compaction hoặc giảm sau merge |
| Read p99 | Tăng khi misses đi tới disk | Tăng do disk/CPU contention |
| Writer throughput | Không nhất thiết đổi | Có thể giảm khi flush/compaction tranh I/O |

Không dựa vào **một** chỉ số để chẩn đoán. Compaction cũng có thể làm **OS page cache bị đẩy ra**, khiến cache miss và compaction pressure xảy ra **đồng thời**. Cần cùng timeline và thử A/B trong điều kiện tương đương.

## 18. Không làm “cold cache” bằng các thao tác phá hoại trên cluster chung

### 18.1. Những cách gây cold thường bị hiểu sai

| Cách làm | Vấn đề |
|---|---|
| Restart Java service | Làm cold JVM/driver; Cassandra và host page cache có thể vẫn warm |
| Restart Cassandra process/container | JVM caches có thể thay; OS page cache trên host chưa chắc bị xóa |
| Restart host riêng | Có thể làm OS page cache cold, nhưng thay nhiều biến (boot, IO, gossip) |
| Tắt key/row cache | **Đổi cấu hình/thuật toán**, không phải chỉ “làm lạnh” trạng thái |
| Linux drop_caches | Thao tác host-wide, ảnh hưởng processes khác; không đại diện steady production |
| `nodetool invalidatekeycache`/`invalidate...` | Thay cache state có chủ đích, khác workload tự nhiên |
| `nodetool compact` | Force rewrite/IO, thay SSTable layout và page cache; không đơn thuần warm |
| `TRUNCATE` rồi seed lại | Thay dữ liệu và SSTables/TTL/timestamps, nguy cơ xóa dữ liệu |

**Không thực hiện** cache invalidation, host `drop_caches`, restart/kill nodes, thay compaction strategy hoặc truncate trên shared/production cluster chỉ để “đo cold”.

### 18.2. Các phép thử thay thế an toàn hơn

**Phương án A — đo natural cold start:** Thu timeline từ một **cluster lab mới tạo** với dữ liệu snapshot/seed manifest rõ ràng; chấp nhận rằng nhiều tầng cùng cold, vì chính đó là mục tiêu RTO.

**Phương án B — cache residency nhỏ vs lớn:** So sánh **working set vừa RAM** và **working set lớn hơn RAM** trên cluster lab, cùng schema/disk/CL; đo cache hits/disk reads để giải thích khác biệt.

**Phương án C — workload shift:** Tạo hai tập partition keys không overlap, chuyển từ tập A sang B ở thời điểm marker, đo transient p99 và time-to-new-steady. Không cần xóa page cache của toàn host.

**Phương án D — app-only restart:** Restart load generator/service client trong lab, giữ Cassandra không đổi, đo JIT/driver warm-up riêng.

### 18.3. Đừng gọi phương án C là “100% cold OS cache”

Hai key sets không overlap không đảm bảo các SSTable/index file pages cũng không overlap, đặc biệt nếu dữ liệu gần nhau trong một SSTable hoặc index summaries được dùng chung. Hãy mô tả nó là **controlled working-set shift** và đo physical disk/cache metrics, không gọi nó là flush toàn bộ page cache.

## 19. Fault testing: node UP trở lại chưa có nghĩa cache/compaction hồi phục

### 19.1. Hai loại recovery time phải báo riêng

Sau khi node/đường mạng phục hồi:

1. **Functional recovery:** Truy vấn tại CL yêu cầu bắt đầu thành công và data oracle đúng.
2. **Performance recovery:** p95/p99, retries, cache hit/churn, flush/compaction backlog và disk resource trở về vùng SLO/steady được công nhận.

Chúng có thể lệch nhau vài phút hoặc nhiều hơn. Một node `UN` và CQL read `ONE` thành công **không** chứng minh `LOCAL_QUORUM` read p99 đã trở lại baseline.

Đặt mốc:

\[
RTO_{\mathrm{CL}} =
t_{\mathrm{first\ sustained\ CL\ success}}-t_{\mathrm{fault\ onset}},
\]

\[
RTO_{\mathrm{perf}} =
t_{\mathrm{steady\ gate\ recovered}}-t_{\mathrm{fault\ removed}}.
\]

**Khác điểm mốc!** Khi so báo cáo phải ghi rõ RTO tính từ fault onset, failover start hay fault removed. Không trộn hai con số rồi kết luận máy đã phục hồi hoàn toàn.

### 19.2. Ví dụ: một node mất trong RF3, CL LOCAL_QUORUM

~~~text
dc1 RF3, natural replicas A/B/C
CL LOCAL_QUORUM = 2

Warm baseline:
  A/B/C UP
  hot keys nằm trong cache của A/B/C
  read p99 = 25ms

Fault:
  C không phục vụ
  A/B vẫn đủ quorum
  read p99 = 55ms, retries/queue tăng

Recovery:
  C UP/UN, cần catch-up (hints/repair/streaming theo kịch bản)
  cache C và local data I/O có thể khác baseline
  compaction/repair cạnh tranh disk
  read p99 = 90ms tạm thời

Post-recovery steady:
  data oracle tại LOCAL_QUORUM PASS
  p99 ổn định lại trong SLO
  backlog không tiếp tục tăng
~~~

Các giá trị p99 là **giả định minh họa**. Không suy rằng mỗi lỗi node luôn làm p99 tăng; nếu node C không phục vụ hot keys hoặc quorum chọn A/B, tác động có thể rất khác.

### 19.3. Failure matrix có kiểm soát

| Fault | Thành phần có thể lạnh/biến đổi | Quan sát bắt buộc | An toàn |
|---|---|---|---|
| Restart **Java service** | JIT, driver pools, prepared caches | Client p99, connection churn, node messages | Chỉ service staging riêng |
| Restart một **Cassandra process** | Server JVM/JIT/cache, gossip/pool, commitlog replay | CL availability, Cassandra GC/cache, data oracle | Chỉ cluster dedicated fault lab |
| Restart **host** | OS page cache và nhiều biến hệ thống | Cold start + disk I/O + quorum | Rất rủi ro; dedicated lab/approval |
| Latency network một node | Retry/CL selection, in-flight | Timeouts, data correctness, tail latency | Fault proxy/throttling trong lab |
| Stop một natural replica | Quorum headroom, coordinator routing | Unavailable/timeout per token/DC | Không làm trên production |
| Bật tải writes cao | Memtable/flush/compaction | Pending tasks/bytes, disk p99 | Hard rate cap/abort |
| Chạy repair staging | Streaming/anticompaction/disk/GC | Data oracle, backlog, RTOperf | Owner/runbook riêng |
| Đổi workload hot-key distribution | Cache residency, hotspot | Cache miss, read p99, token skew | Có thể không cần fault node |

**Fault injection không bắt buộc phải làm node DOWN.** Một bước chuyển từ hot working set A sang B có thể đủ để thử cache-warm recovery mà không ảnh hưởng topology. Khi mục tiêu là CL availability dưới node failure, phải biết **natural replicas** của probe keys; tắt một node không thuộc replica set có thể chẳng tạo lỗi.

### 19.4. Quy trình một fault test an toàn

~~~text
Preflight:
  isolated staging + permissions + rollback owner
  RF/CL known, representative token keys
  disk/CPU/network headroom
  rate/timeout/in-flight hard limits
  health checks and data oracle baseline
      |
Steady-state gate PASS
      |
Mark T_fault_onset and inject ONE fault
      |
Observe CL success/errors/retries/p99, resource
      |
Mark T_fault_removed
      |
Wait for node/ring/streaming/repair as appropriate
      |
Observe cache/flush/SSTable/compaction recovery
      |
Post-recovery steady-state gate PASS or timeout
      |
Restore original configuration and archive evidence
~~~

**Không đổi nhiều biến cùng lúc** như kill node, đổi RF và tăng load 10 lần nếu mục tiêu là suy nguyên nhân p99. Thử từng fault class và có baseline đối chứng.

### 19.5. Consistency và unknown write outcomes trong fault test

Một `WriteTimeoutException`/`DriverTimeoutException` có thể xảy ra sau khi coordinator đã gửi mutation tới một số replicas. Không được đếm mọi timeout là “write chắc chắn thất bại”, rồi replay bằng UUID mới làm trùng dữ liệu.

Thử nghiệm fault cần:

- Stable operation/event ID cho mỗi logical write.
- Data oracle/đối soát sau lỗi và sau repair, CL phù hợp.
- Ghi `acknowledged`/`unknown`/`reconciled`/`failed-confirmed` riêng.
- Không bật speculative execution cho counter/list append hoặc write không idempotent.
- Không dùng error rate thấp hơn do **hạ CL** như bằng chứng benchmark được cải thiện.

### 19.6. Sau recovery phải tiếp tục đo compaction

Node có thể UP, đáp ứng `LOCAL_QUORUM`, nhưng vừa nhận hints/streaming data và cần flush/compaction. Nếu dừng thu metrics đúng lúc `nodetool status` chuyển sang `UN`, kết quả **bỏ sót phần chi phí phục hồi**. Giữ monitoring cho tới khi:

1. Data oracle trên representative keys PASS.
2. Read/write p99 và timeout trở lại vùng yêu cầu nhiều cửa sổ liên tiếp.
3. Compaction/flush backlog không tích lũy.
4. Disk free/await/GC có headroom và không trôi bất thường.
5. Không có streaming/repair/decommission chưa được account theo kịch bản.

## 20. A/B compaction/cache: làm sao tránh kết luận giả?

### 20.1. Hai phương án nên có control rõ

Ví dụ muốn so STCS và LCS trên một workload read-heavy:

~~~text
Cluster A:
  STCS, dataset S, RF3, LOCAL_QUORUM
  Java load Q, partitions/TTL distribution D

Cluster B:
  LCS, dataset S, RF3, LOCAL_QUORUM
  Java load Q, partitions/TTL distribution D

Khác biến chính:
  compaction strategy

Đo:
  steady read p99, write p99, CPU, disk I/O,
  SSTables-per-read, compaction bytes, disk space, RTO
~~~

Điều kiện **cluster A/B tương đồng** khó đạt nếu phần cứng, data history, SSTable layout, compaction timing và OS cache khác. Nếu test tuần tự trên cùng cluster, phải có quy trình **đưa state về baseline được xác minh**. Đổi compaction strategy bằng `ALTER TABLE` rồi đo ngay có thể đang đo **transient rewrite backlog**, không phải steady strategy.

### 20.2. Bảng câu hỏi trước khi kết luận

| Câu hỏi | Nếu câu trả lời “không biết” |
|---|---|
| Đã chạy workload với cùng QPS/mix/CL/RF chưa? | Không thể quy khác biệt cho strategy |
| Dataset identical về rows/TTL/tombstones? | Có confounder data shape |
| Cả A/B đều có representative flush/compaction cycles? | Có thể chỉ đo startup regime |
| Cache hit/miss và OS disk reads tương đồng hoặc được báo riêng? | Cache bias chưa kiểm soát |
| SSTable count/levels/overlap có đạt trạng thái mong đợi? | Strategy chưa ổn định |
| Compaction backlog không trôi trong đo? | Throughput có thể không bền |
| P99 có đủ sample count cùng histogram precision? | Percentile comparison thiếu chắc chắn |
| Errors/timeouts/retries được tính? | Có thể số đẹp do loại bỏ requests thất bại |
| Đã lặp nhiều run/randomize thứ tự? | Kết quả có thể do order/host noise |
| Data correctness và CL giữ nguyên? | Không đánh đổi consistency lấy latency |

### 20.3. Baseline nên lấy theo nhiều mốc

~~~text
B0: before seed
B1: after seed/preload stabilization
B2: after cache warm-up gate
B3: steady measurement end
B4: after fault removed (nếu có)
B5: after post-recovery steady gate
~~~

Nếu B2 và B3 có compaction bytes/write MB/s khác nhau lớn, một cửa sổ 2 phút có thể chưa đủ. Báo cả evolution, không chỉ average latency.

### 20.4. Có nên tắt compaction để “đo riêng read cache”?

**Không khuyến nghị** như phép đo hiệu năng đại diện. Tắt auto-compaction làm SSTable count tăng và thay đổi read amplification/capacity dynamics; khi bật lại có thể gây một **compaction storm** không giống workload bình thường. Chỉ thực hiện trong **thí nghiệm lab được thiết kế riêng** để tách cơ chế, có snapshot/rollback và disk headroom; không áp trên production.

### 20.5. A/B phải báo cái giá của tốc độ

Một strategy có thể:

- Giảm read p99 nhưng tăng write I/O/CPU và compaction bytes.
- Giảm disk space amplification nhưng tạo write amplification nhiều hơn.
- Tốt ở hot-cache point reads nhưng xấu ở uniform scans.
- Tốt ở steady nhưng recovery sau fault lâu hơn.

Không gọi “chiến lược thắng” chỉ vì p99 của một SELECT giảm 10%. Cần cân nhắc **read/write SLA, disk cost, maintenance/RTO và correctness** cùng nhau.

## 21. Chẩn đoán p99 tăng: cache miss, compaction, GC hay query shape?

### 21.1. Decision tree

~~~text
App p99 tăng / timeout tăng
             |
     Offered QPS có thay?
      /               \
    CÓ                 KHÔNG
     |                   |
Rate/load shape?      Query mix/keys/CL có đổi?
     |                     |
     +----------+----------+
                |
      Cassandra server p99 tăng?
          /                 \
         CÓ                 KHÔNG
          |                   |
  Per-node disk/GC         Driver pool/queue/JIT
  compaction metrics       network/TLS/codec
          |
  Cache hit/miss đổi?
      /         \
    CÓ           KHÔNG
     |             |
Working set?     Pending compaction/flush tăng?
     |             /           \
Read I/O tăng?  CÓ             KHÔNG
     |           |                |
Cache/eviction  SSTables/IO       Hot partition?
                backlog          Tombstone scans?
                    \             /
                     Data model / query profile
                              |
               Thử đối chứng với biến được kiểm soát
~~~

Sơ đồ này **gợi hướng điều tra**, không chứng minh quan hệ nhân quả. Ví dụ compaction có thể thay OS page cache, nên cả cache miss và disk contention cùng tăng. Cần timeline, traces/samples và controlled experiments.

### 21.2. Ma trận giả thuyết → dữ liệu phải thu

| Giả thuyết | Dấu hiệu củng cố | Dấu hiệu phản bác/thiếu |
|---|---|---|
| JVM/JIT warm-up | Client CPU/allocation tăng lúc đầu, server latency không đổi nhiều | Server p99 tăng cùng thời điểm |
| Driver pool cold | Open connections/routing/handshake thay đổi, requests queued | Pool ổn định, nhưng disk reads tăng |
| Key-cache miss | Key cache hit ratio giảm, partition/index lookups đắt hơn | Hit ratio không đổi, disk writes tăng |
| OS page-cache miss | Physical disk read bytes/await tăng khi keys mở rộng | Disk reads giữ nguyên dù client p99 tăng |
| Memtable flush contention | Pending flushes, disk writes, commitlog/memtable pressure tăng | Không có flush/IO changes |
| Compaction contention | Pending/active compaction, bytes rewritten, disk await tăng | Compaction idle, read-only p99 vẫn tăng |
| SSTable read amplification | SSTables-per-read, SSTable count/overlap tăng | Chỉ đổi JIT/connection |
| Tombstones/TTL | Tombstones scanned, read timeouts/warnings, expired data tăng | Dữ liệu không xóa/TTL, scans thấp |
| Hot partition | CPU/IO skew rõ trên few natural replicas | All nodes đều chịu tải cân đối |
| Replica/DC/CL issue | `UNAVAILABLE`, retries, coordinator/replica-specific errors | CL và RF/route không đổi, errors không tăng |
| Load generator bão hòa | Generator CPU 100%, offered/completed QPS lệch | Generator headroom tốt, server queue tăng |

### 21.3. Mô hình kiểm tra sau một phát hiện

1. **Xác nhận scope:** Chỉ một query family hay toàn app? Chỉ một node/token/DC hay mọi replicas?
2. **Dựng timeline:** Mark mốc seed/warm/measurement/fault/compaction/repair và client deployment.
3. **Kiểm sự thay đổi:** Query shapes/CL/partition distribution/TTL có đổi không?
4. **So throughput và error:** p99 của completed requests có loại bỏ timeouts không?
5. **Kiểm cache và I/O:** Key/row/chunk hits, disk physical read vs write, SSTables.
6. **Kiểm background work:** Flush/compaction/streaming, GC, repairs.
7. **Chọn một giả thuyết và một biến để kiểm:** Không đổi 4 settings rồi gán toàn bộ lợi ích cho một setting.
8. **Đối chiếu correctness:** Read/write vẫn đúng CL, kết quả không stale/sai.

### 21.4. Khi không có metric cache OS trực tiếp

Kernel page cache không nhất thiết có hit-rate riêng per-table. Bạn có thể dùng **gián tiếp**: cache residency nếu có, major/minor faults, file-system/disk reads, throughput, hot key distribution và so read latency. **Đừng gán “page cache hit = 100%” chỉ vì disk await thấp**: SSD nhanh, read-ahead hoặc Cassandra chunk cache cũng có thể giải thích.

### 21.5. Metric ghi nhận sau process restart bị reset

Nhiều counters như `BytesCompacted`, total requests/GC count **reset về 0 khi process restart**. Dashboard lấy đạo hàm/rate cần xử lý reset; nếu so raw totals trước/sau restart, sẽ tưởng compaction/workload “giảm 99%” khi thực chất chỉ reset counter. Dùng timestamp/process uptime và sampling đúng.

## 22. Hai mươi tình huống thực tế về warm-up, cache và compaction

### Ca 1 — Đọc lần đầu chậm, lần hai nhanh trên một partition

**Quan sát:** Point lookup đầu 80ms, 100 lần sau 5ms.

**Có thể do:** Driver/JIT/connection mới, key/index/OS page cache miss, coordinator/replica lookup, GC.  
**Không kết luận:** “Key cache đã xử lý toàn bộ read”.  
**Kiểm:** Driver pool/JIT warm-up, Cassandra key-cache hits, disk physical reads, SSTables-per-read cùng timestamp.

### Ca 2 — Benchmark mới luôn nhanh hơn benchmark cũ

**Quan sát:** Run B nhanh hơn A, dù cùng code và rate.

**Có thể do:** B thừa hưởng kernel page cache, prepared statements hoặc compaction đã chạy xong sau A.  
**Sửa:** Randomize A/B, snapshot state và xác minh warm-up gates trước mỗi run; báo state differences.

### Ca 3 — Restart container rồi vẫn thấy hot latency

**Quan sát:** Docker restart Cassandra nhưng reads vẫn gần tốc độ hot.

**Giải thích:** OS page cache trên host có thể còn pages; saved cache/SSD cũng ảnh hưởng.  
**Không kết luận:** “Cassandra khởi động xong cache đã fill đầy”.  
**Sửa:** Ghi rõ loại restart, đo file I/O và cache metrics, không dùng restart làm cold cache oracle.

### Ca 4 — Write QPS đẹp 3 phút đầu, sau đó tụt

**Quan sát:** 25k writes/s ban đầu, sau 10 phút chỉ 8k, pending compaction tăng.

**Giải thích:** Memtable/commitlog ban đầu hấp thu writes, flush và compaction bắt đầu tranh disk/CPU, workload tiến vào sustained I/O regime.  
**Sửa:** So throughput trong đủ chu kỳ flush/compaction và disk headroom; không báo initial burst là sustainable throughput.

### Ca 5 — `PendingCompactions=0` nhưng read p99 cao

**Giải thích:** Không có queued compactions không có nghĩa disk/cache/partition tốt; có thể OS page misses, tombstones, hot partition hoặc compaction đã xong nhưng SSTable layout chưa phù hợp.

**Kiểm:** SSTables-per-read, page cache/disk read, read latency theo key, row size/TTL và driver queue.

### Ca 6 — Compaction luôn active nhưng latency ổn

**Giải thích:** Continuous writes cần background maintenance; một compaction thread active là bình thường.  
**Quyết định:** Có thể **STEADY** nếu QPS/p99/errors đạt SLO, backlog/space không trôi và disk còn headroom. Không bắt buộc pending về 0.

### Ca 7 — Chuyển từ 100 hot keys sang 1 triệu keys, p99 vọt

**Giải thích:** Working set mở rộng, key/index/OS caches miss và physical disk reads tăng.  
**Sửa:** Báo **workload shift transient** riêng; nếu production thực có long-tail keys, giữ chúng trong warm-up/measurement mix.

### Ca 8 — Cache hit 99% nhưng một tenant vẫn timeout

**Giải thích:** Tổng hit ratio bị hot keys chi phối; tenant đó có partition rộng/tombstones hoặc natural replicas nghẽn.  
**Sửa:** Split query family/tenant tier (không log raw tenant ID), per-replica metrics, partition-size/tombstone scans.

### Ca 9 — So STCS/LCS sau một flush, kết quả bằng nhau

**Giải thích:** Compaction strategies chưa vào steady regime; chưa có đủ SSTables/levels.  
**Sửa:** Dài hơn và nhiều flush cycles, giữ cùng data/TTL/query mix, đo disk write amp và SSTables-per-read.

### Ca 10 — Bật LCS cải thiện read p99 nhưng disk viết tăng mạnh

**Giải thích:** LCS có thể giảm read amplification đổi lại nhiều rewrite I/O.  
**Sửa:** Báo cả read/write SLO, compaction bytes, disk free, recovery duration, không chỉ một p99.

### Ca 11 — TWCS test 15 phút không lộ tombstone/TTL issues

**Giải thích:** Production retention 30 ngày/time windows, nhưng test chưa chạm expiry/late events.  
**Sửa:** Long soak hoặc time-aware dataset/controlled retention scenarios, ghi coverage gap. Không ép TTL vô lý để đại diện toàn bộ 30 ngày.

### Ca 12 — Sau restart node Cassandra, `UN` nhưng app vẫn chậm

**Giải thích:** JVM/OS caches khác, driver reconnect, hints/streaming/repair, compaction I/O có thể còn ongoing.  
**Sửa:** Tách time-to-CL-success và time-to-p99-baseline, giám sát hậu phục hồi.

### Ca 13 — Node failover làm hot partition chậm

**Giải thích:** Coordinator/replica B ít được đọc trước đó nên key/page cache lạnh; routing/CL và retries cũng đổi.  
**Sửa:** Per-replica cache metrics, trace coordinator, kiểm RF3/LQ data oracle và RTOperf.

### Ca 14 — Càng tăng load, completed QPS càng giảm

**Giải thích:** Saturation, queue/backpressure, disk/compaction overload; closed-loop generator có thể tự giảm offered throughput khi latency cao.  
**Sửa:** Vẽ offered/completed QPS và in-flight/queue, xác định saturation knee, không chỉ tăng threads.

### Ca 15 — Application p99 tăng nhưng Cassandra server p99 không đổi

**Giải thích:** JVM GC, connection pool/throttler, network/TLS, serialization/bind, client retries.  
**Sửa:** Thu driver `cql-requests` và node `cql-messages`, JFR, pool metrics; đừng tăng `compaction_throughput` theo cảm tính.

### Ca 16 — Cassandra server read p99 cao đúng lúc backup/repair

**Giải thích:** Snapshot/repair/streaming/anti-compaction và reads cùng tranh disk/CPU.  
**Sửa:** Gắn event markers cho maintenance, đo riêng normal baseline và maintenance-under-load SLO; không loại hết bảo trì khỏi test nếu production có chạy thường kỳ.

### Ca 17 — `cassandra-stress` báo tốc độ cao hơn Java app 5 lần

**Giải thích:** Stress dùng schema/phân phối/row size khác, không có HTTP/business logic, có thể CL khác.  
**Sửa:** Chạy stress user mode hoặc NoSQLBench với CQL/profile tương đương; so offered load, CL, page size, retries và data cardinality.

### Ca 18 — Error rate tăng nhưng p99 thành công giảm

**Giải thích:** Những requests chậm nhất bị timeout/loại khỏi success histogram, nên percentile của requests còn sống giảm.  
**Sửa:** Báo failures/timeouts, end-to-end deadline, SLO success latency và censored samples; không tuyên bố tối ưu.

### Ca 19 — Flush queue tăng sau bulk import, đã dừng import nhưng p99 vẫn xấu

**Giải thích:** Background SSTable flush/compaction còn trả “nợ” của write burst.  
**Sửa:** Tiếp tục đo drain, pending/active tasks, disk writes và read p99; phân biệt workload recovery với acceptance steady state.

### Ca 20 — Benchmark test compaction xong vì disk đầy rồi “thành công”

**Sai:** Tool generator đã chạy đủ duration; báo PASS dù disk free rất thấp/compaction fail.  
**Đúng:** STOP, bảo vệ cluster, ghi thông số và rollback/resume theo runbook; không tiếp tục load đến mức mất khả năng ghi hay mở rộng. **Khả năng duy trì tải** quan trọng hơn kết quả tức thời.

## 23. Runbook GO/HOLD/STOP cho warm-up và fault test

### 23.1. Các điều kiện trước khi chạy

1. **Có quyền và phạm vi rõ:** Dedicated lab/staging, cluster/namespace được phép thử, maintenance window nếu có.
2. **Có người giám sát:** Owner của Cassandra cluster, application, load generator và rollback.
3. **Có dataset manifest:** Partition cardinality, distribution, TTL/tombstones, row size/compaction policy.
4. **Có topology contract:** RF per DC, CL read/write, application local DC, token coverage.
5. **Có workload contract:** Query families, QPS/concurrency, rate cap, error budget, duration, first/full page.
6. **Có metrics đủ:** Client request/attempts, server JMX, disk/CPU/GC, cache/SSTable/compaction.
7. **Có stop thresholds:** Disk free/await, error rate, timeouts, GC pauses, backlog growth, data mismatch.
8. **Có test oracle:** Known keys và values/versions để không đánh đổi correctness lấy throughput.
9. **Có phương án restore:** Không truncate/kill/disable compaction bừa bãi; có quyền dừng generator và phục hồi setup.

### 23.2. Giao thức đo từng pha

~~~text
START
  |
  v
PREFLIGHT: ENV + CL + RF + DATA ORACLE
  |
  +-- FAIL --> STOP / FIX CONFIG
  |
  v
SEED / PRELOAD at controlled rate
  |
  v
WAIT: initial flush/compaction observation
  |
  v
WARM-UP: same query mix & key distribution
  |
  v
STEADY-STATE GATE?
  |                 |
 FAIL/BUDGET EXPIRED   PASS
  |                 |
 HOLD: NOT_STEADY      v
  |               MEASURE
  |                 |
  |              FAULT? -- NO --> REPORT
  |                 |
  |                YES
  |                 |
  |         INJECT ONE CONTROLLED FAULT
  |                 |
  |          OBSERVE CL + ERRORS + p99
  |                 |
  |          RESTORE FAULT CONDITION
  |                 |
  |          POST-RECOVERY GATE?
  |                /            \
  |             PASS             FAIL
  |               |               |
  +------------->REPORT      STOP + ESCALATE
                      |
          Archive phase metrics and limits
~~~

Đừng tự động bỏ qua warm-up gate thất bại vì đã chạy quá duration. Nhãn trung thực là `NOT_STEADY_WITHIN_BUDGET`; đây **chính là một phát hiện quan trọng** về capacity/working-set hoặc workload không đại diện.

### 23.3. Quyết định GO/HOLD/STOP

| Quan sát | Hành động | Lý do |
|---|---|---|
| Preflight: wrong CL/DC, schema/data mismatch | **STOP** | Không được benchmark sai consistency contract |
| Dataset chưa seed đủ cardinality/time distribution | **HOLD** | Cache results có thể quá lạc quan |
| Cold metrics thu đủ, warm-up vẫn đang làm cache tăng | **HOLD** | Chưa vào trạng thái target |
| Warm-up duration hết nhưng compaction backlog tăng đều | **HOLD/NOT_STEADY** | Sustained throughput không được chứng minh |
| Cache steady, compaction stable, p99/error đạt target đủ windows | **GO** | Có bằng chứng đạt phạm vi test |
| Driver request timeouts tăng, p99 success giảm | **HOLD/STOP** | Có thể censored slow requests |
| Disk free thấp hơn guardrail hoặc compaction fail | **STOP ngay** | Rủi ro tới dữ liệu/khả năng phục hồi |
| Fault quá lớn, node mất CL và data oracle sai | **STOP fault, restore** | Không duy trì thí nghiệm hủy hoại |
| Node UP nhưng post-recovery p99/backlog chưa ổn | **HOLD** | Functional recovery khác performance recovery |
| Post-recovery gates/accuracy/SLO đạt qua nhiều windows | **GO report** | Có bằng chứng hồi phục |

**Không có một threshold chung** như “p99≤100ms” hay “disk free ≥30%” cho mọi cluster. Guardrails phải dựa trên SLO, capacity của storage class, compaction strategy, RF/CL và baseline được phê duyệt.

### 23.4. Điều kiện ABORT tức thời

Trong dedicated lab, dừng generator/fault injection nếu có một trong:

- Data oracle sai/tombstone resurrection/data corruption nghiêm trọng.
- Unexpected node failures hoặc có nguy cơ mất CL vượt phạm vi thử.
- Disk full, filesystem read-only, commitlog write failures, compaction errors.
- GC/OOM/CPU throttling vượt guardrail gây rủi ro cho dữ liệu/cluster.
- Test tool đang nhắm **sai cluster/IP/keyspace** so với allowlist.
- Credentials/PII bị log hoặc workload thực hiện mutation không được phép.

Không “giảm CL tạm” để giữ benchmark chạy trong khi consistency contract đã hỏng. Đánh dấu thí nghiệm FAIL hoặc INCONCLUSIVE và chuyển sang runbook khôi phục.

### 23.5. Recovery và bàn giao

Sau khi dừng workload:

1. Ghi chính xác timestamp của ngừng generator và fault removal.
2. Kiểm nodes/ring, RF/CL data oracle, write unknown outcomes.
3. Theo dõi flush/compaction/repair streaming backlog cho tới gate hoặc hết budget.
4. Kiểm disk headroom và physical I/O có trở lại vùng an toàn không.
5. Tách `RTO_CL` và `RTO_perf`; không chỉ dựa vào `nodetool status UN`.
6. Thu raw metrics, sample counts, histogram method và manifest versions.
7. Đưa system settings về baseline chỉ theo runbook/owner; **không tự xóa SSTables/snapshots**.
8. Báo cáo limitations: dataset nhỏ, chưa đủ time windows, không đủ token/DC coverage, transient replication nếu có.

### 23.6. Mẫu kết quả không che giai đoạn xấu

~~~text
EXPERIMENT_ID:
OWNER / UTC START:
CLUSTER / CASSANDRA VERSION / DRIVER:
RF PER DC / READ CL / WRITE CL:
QUERY FAMILIES / QPS TARGET / GENERATOR:
DATASET: partition_count, rows_per_partition, bytes, TTL
COMPACTION: strategy, settings, initial SSTables
CACHE: key/row/chunk config, working set estimate

COLD PHASE:
  duration, latency p50/p95/p99, errors
  cache misses, disk reads, JIT/GC

WARM-UP PHASE:
  actual duration, gate PASS/NOT_STEADY
  cache hit trend, compaction/flush trend

STEADY MEASUREMENT:
  completed/target QPS, latency hist counts
  p50/p95/p99 by query family
  retries/timeouts/unknown outcomes
  SSTables-per-read, compaction bytes/queues
  physical disk I/O, GC, disk headroom

FAULT PHASE (if any):
  fault type/scope, T_fault_onset, T_fault_removed
  CL availability, p99/error, data oracle

RECOVERY PHASE:
  RTO_CL, RTO_perf, repairs/streaming
  cache state, compaction backlog, disk headroom

RESULT: GO / HOLD / STOP
LIMITATIONS / DATA CORRECTNESS / NEXT ACTION:
~~~

Các dòng trên là **mẫu nội dung báo cáo**, không phải yêu cầu tạo thêm file trong thư mục module. Kết luận cuối phải kèm **phạm vi**: query families, dataset, topology, offered QPS, CL, duration, hardware và warm/cold state.

## 24. Checklist khi code review một kế hoạch load/fault test

### 24.1. Khả năng tái lập

- [ ] Cassandra, JDK, Java Driver, load generator versions được pin.
- [ ] Node count/DC/rack/RF/CL và schema table được ghi rõ.
- [ ] Compaction strategy/config, compression, cache config được snapshot.
- [ ] Dataset cardinality/row size/TTL/tombstones/partition width có manifest.
- [ ] Workload key distribution hot/uniform/range/temporal tương ứng production.
- [ ] Rate schedule, concurrency, queue/in-flight limits và test duration rõ.
- [ ] Thử A/B giữ các biến không phải mục tiêu ở mức tương đương.
- [ ] Có multiple runs, randomize order hoặc reset state được kiểm chứng.
- [ ] Không mặc định restart container làm OS page cache cold.
- [ ] Không quên client JVM/driver warm-up và load-generator headroom.

### 24.2. Read path

- [ ] Queries đúng partition key/clustering pattern; không `ALLOW FILTERING` vô chủ đích.
- [ ] CL read đặt tường minh, không âm thầm trở về default profile.
- [ ] Đo p50/p95/p99 riêng theo query family, page 1 vs full result nếu cần.
- [ ] Cache hit/miss có sample count, node scope và working-set context.
- [ ] Đo physical disk reads/page-cache evidence phù hợp.
- [ ] Có `SSTablesPerReadHistogram`/SSTable count và tombstone scans.
- [ ] Không trộn point lookup với table/range scans vào một percentile chung.
- [ ] Không gọi hot-key-only test là random production benchmark.
- [ ] Data oracle xác minh đúng PK/value/version, không chỉ “query không exception”.

### 24.3. Write path/compaction

- [ ] Đã có đại diện memtable flush cycles trong measurement hoặc nêu limitations.
- [ ] Đo commitlog/memtable/flush pending và disk write throughput.
- [ ] Compaction backlog/bytes/SSTable level/count không tăng mãi trong steady target.
- [ ] Không dùng “pending compactions=0” làm điều kiện duy nhất.
- [ ] Có headroom disk cho compaction output/repair, không chạy đến 100% disk.
- [ ] TTL, tombstone và late-arrival patterns đúng vòng đời dữ liệu.
- [ ] Không tắt auto-compaction chỉ để làm throughput tức thời đẹp.
- [ ] Không tự chạy manual major compaction/truncate trong shared cluster.
- [ ] Báo cả read/write amplification và maintenance/recovery costs.

### 24.4. Latency/thống kê

- [ ] Offered QPS và completed QPS được ghi riêng.
- [ ] QPS ổn định trong nhiều rolling windows, không chỉ một snapshot.
- [ ] p99 có đủ samples và cách tính histogram rõ.
- [ ] Errors/timeouts/cancelled requests không bị loại khỏi SLO report.
- [ ] Percentiles client/server không bị trừ để “tính network time”.
- [ ] Cache/compaction/GC/Disk/Latency metrics có timestamp cùng time range.
- [ ] Driver retries/speculative executions được tính vào physical load.
- [ ] Little's Law chỉ dùng mean latency và state ổn định; không thay mean bằng p99.
- [ ] Có phân pha COLD/WARM/STEADY/FAULT/RECOVERY và ghi duration thực.
- [ ] Không gọi “STEADY” khi backlog tăng hoặc cache drift kéo dài.

### 24.5. Safety và fault testing

- [ ] Cluster test nằm trong allowlist, không phải production/shared environment.
- [ ] Có người được phép inject fault, rollback và hủy test.
- [ ] Có stop criteria cho data mismatch, disk pressure, node failure, timeout spikes.
- [ ] Fault injection chỉ thay **một biến chính** mỗi lần nếu muốn suy nhân quả.
- [ ] Biết natural replicas/CL trước khi dừng node trong dedicated lab.
- [ ] Sau restart đo cả CL recovery và performance/compaction recovery.
- [ ] Write timeout có xử lý unknown outcome/idempotency key.
- [ ] Không hạ CL hoặc lạm dụng retry để làm báo cáo đẹp.
- [ ] Không thao tác host `drop_caches`, kill/iptables/truncate tùy tiện.
- [ ] Không ghi raw credentials/PII/bind values/high-cardinality IDs vào dashboard.
- [ ] Chỉ kết luận trong phạm vi đã đo; có limitation/next validation plan.

## 25. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** Vì sao bỏ 30 giây đầu rồi gọi mọi thời gian sau là steady state là sai?  
**Gợi ý:** JIT/cache/flush/compaction có thể vẫn chuyển trạng thái; phải qua rolling-window gate có số liệu.

**Câu 2.** Warm-up của Java Driver giống warm-up của OS page cache không?  
**Gợi ý:** Không; prepared/connection/metadata/JIT ở client khác data/index pages ở server.

**Câu 3.** Đọc cùng partition 1.000 lần có thể chứng minh random production workload đã warm không?  
**Gợi ý:** Không; key distribution/working set khác nhau.

**Câu 4.** Key cache hit chứng minh SSTable data đã ở RAM chưa?  
**Gợi ý:** Không; key cache chủ yếu giúp định vị partition/index, data pages vẫn có thể cần disk.

**Câu 5.** Row cache có mặc định bật và giúp mọi query không?  
**Gợi ý:** Không; phụ thuộc config/version, hot partitions, writes/invalidations và memory.

**Câu 6.** Cassandra restart container có đảm bảo OS page cache cold không?  
**Gợi ý:** Không; page cache ở kernel/host có thể tồn tại qua process/container restart.

**Câu 7.** Vì sao compaction có thể làm cache hit giảm?  
**Gợi ý:** SSTables mới/thay layout và I/O cạnh tranh/evict OS page cache.

**Câu 8.** Cassandra viết vào SSTable trực tiếp trước khi ACK một CQL INSERT không?  
**Gợi ý:** Thông thường mutation đi qua commitlog + memtable; flush SSTable sau đó.

**Câu 9.** Ghi ACK thành công ở QUORUM có nghĩa compaction xong không?  
**Gợi ý:** Không; CL write khác background flush/compaction lifecycle.

**Câu 10.** Vì sao write throughput đầu bài test có thể cao hơn sustained throughput?  
**Gợi ý:** Ban đầu memtable/commitlog hấp thụ burst, disk compaction/flush chưa đầy tải.

**Câu 11.** Nếu pending compaction khác 0, chắc chắn NOT_STEADY không?  
**Gợi ý:** Không; sustained writes có thể luôn tạo compaction. Quan trọng là backlog/trend và SLO.

**Câu 12.** Pending compaction từ 10→25→50→100 có cho phép gọi steady không?  
**Gợi ý:** Không nếu tăng liên tục trong cùng tải, dù p99 tạm chưa vượt ngưỡng.

**Câu 13.** `BytesCompacted` là counter hay gauge?  
**Gợi ý:** Counter; cần rate/increase qua thời gian và chú ý reset khi node restart.

**Câu 14.** `PendingTasks` là số byte chờ compaction không?  
**Gợi ý:** Không; đó là số tasks ước lượng, các tasks có kích thước khác nhau.

**Câu 15.** Vì sao phải theo dõi `SSTablesPerReadHistogram`?  
**Gợi ý:** Chỉ báo read amplification — một read phải kiểm bao nhiêu SSTables.

**Câu 16.** STCS, LCS và TWCS phù hợp những workload nào?  
**Gợi ý:** STCS thường write-heavy/general, LCS read-heavy/update, TWCS time-series TTL mostly immutable; cần benchmark theo phiên bản.

**Câu 17.** UCS có phải bật được trên mọi Cassandra 4.x không?  
**Gợi ý:** Không; availability/config/version phải kiểm, nhất là Cassandra 5.x.

**Câu 18.** Vì sao test TWCS 10 phút không chứng minh lifecycle TTL 30 ngày?  
**Gợi ý:** Chưa có expiry/late writes/compaction time windows thực tế.

**Câu 19.** Có nên đặt TTL 1 giây để “giả lập” retention 30 ngày không?  
**Gợi ý:** Không; tạo churn/tombstones không tương đương production.

**Câu 20.** 1 TB table có thể có working set 2 GB không?  
**Gợi ý:** Có; phụ thuộc phân phối truy cập, không chỉ table size.

**Câu 21.** 40 GiB active pages và 16 GiB RAM page cache thì warm lâu có giúp giữ toàn bộ 40 GiB trong cache không?  
**Gợi ý:** Không; trạng thái có thể là stable turnover/thrashing, cần đo miss rate.

**Câu 22.** Uniform random và Zipfian có cùng cache behavior không?  
**Gợi ý:** Không; Zipfian có hot keys, uniform chạm keys rộng hơn.

**Câu 23.** Sau 300k reads uniform trên 1 triệu keys, đã chạm đủ cả triệu keys chưa?  
**Gợi ý:** Chưa; kỳ vọng distinct ~259k keys, chưa tính page/index working set.

**Câu 24.** Tại sao hot partition làm sai benchmark cluster-wide?  
**Gợi ý:** Few natural replicas bão hòa trong khi các nodes khác rảnh.

**Câu 25.** Một closed-loop generator khi latency tăng sẽ tạo offered load thế nào?  
**Gợi ý:** Có thể tự giảm vì workers chờ response, gây coordinated omission.

**Câu 26.** Open-loop load có cần giới hạn queue/in-flight không?  
**Gợi ý:** Có; nếu Cassandra chậm sẽ tích lũy requests, phải có hard stop/backpressure.

**Câu 27.** Có thể lấy p99 thay mean latency trong Little's Law `L=λW` không?  
**Gợi ý:** Không; `W` là response time trung bình trong steady state.

**Câu 28.** p99 latency thành công giảm nhưng timeout tăng, có nghĩa performance tốt hơn không?  
**Gợi ý:** Không; requests chậm có thể đã fail và không còn trong success histogram.

**Câu 29.** Vì sao cần ghi count của samples khi báo p99?  
**Gợi ý:** Ít samples khiến tail percentile không ổn định và dễ overinterpret.

**Câu 30.** Có thể suy network latency = app p99 − Cassandra server p99 không?  
**Gợi ý:** Không; percentiles từ tập mẫu khác nhau không cộng/trừ như mean.

**Câu 31.** Một warm-up gate nên kiểm những nhóm nào?  
**Gợi ý:** QPS, p95/p99, errors, caches, SSTables-per-read, flush/compaction backlog, disk/CPU/GC, driver.

**Câu 32.** Nếu compaction backlog tăng mà client p99 tạm ổn, nên làm gì?  
**Gợi ý:** HOLD/NOT_STEADY, không gọi sustained capacity PASS.

**Câu 33.** Tại sao measurement cần đủ thời gian cho flush cycles?  
**Gợi ý:** Burst ban đầu chưa thể hiện I/O cost dài hạn của SSTable/compaction.

**Câu 34.** Test compaction strategy phải giữ những gì tương đương?  
**Gợi ý:** Dataset, workload mix, CL/RF, hardware, OS/driver settings, warm state và histograms.

**Câu 35.** Có nên tắt autocompaction để làm read benchmark “sạch” không?  
**Gợi ý:** Không nếu mục tiêu là production-like steady; tắt thay SSTable evolution, có thể gây backlog storm sau đó.

**Câu 36.** `cassandra-stress` còn được khuyến nghị là công cụ benchmark mới nhất trong Cassandra 5.0 không?  
**Gợi ý:** Tài liệu đánh dấu deprecated và giới thiệu NoSQLBench; vẫn dùng được cho lab khi hiểu giới hạn.

**Câu 37.** Benchmark built-in `cassandra-stress` có tự động mô phỏng bảng/order API của ứng dụng không?  
**Gợi ý:** Không; cần user mode/custom workload hoặc NoSQLBench/Java generator đúng schema/query.

**Câu 38.** Vì sao chạy stress write rồi chuyển sang read ngay có thể gây nhiễu cache test?  
**Gợi ý:** Compaction/flush từ seed vẫn còn làm disk/OS cache thay đổi.

**Câu 39.** Bật `drop_caches` trên shared host có phải cách benchmark cold được chấp nhận mặc định không?  
**Gợi ý:** Không; phá state của processes khác, rủi ro và khác production; chỉ trong dedicated lab theo policy.

**Câu 40.** Chuyển workload hot set A→B có chứng minh mọi OS cache pages của B cold 100% không?  
**Gợi ý:** Không; file/index pages có thể overlap, phải đo physical disk/cache metrics.

**Câu 41.** Vì sao Cassandra node `UN` sau restart vẫn có thể làm app p99 cao?  
**Gợi ý:** JIT/cache/pools/streaming/repair/compaction có thể chưa ổn.

**Câu 42.** `RTO_CL` và `RTO_perf` khác gì?  
**Gợi ý:** Một cái là phục hồi khả năng trả kết quả đúng ở CL; cái kia là phục hồi SLO/cache/compaction steady.

**Câu 43.** Với RF3 `LOCAL_QUORUM`, dừng một replica là đủ để chắc mọi query fail không?  
**Gợi ý:** Không; hai replicas còn lại có thể đủ quorum, phụ thuộc natural replica set/latency.

**Câu 44.** Vì sao sau timeout write không sinh UUID mới để retry bừa?  
**Gợi ý:** Mutation có thể đã áp, outcome unknown, sinh ID mới có thể nhân đôi nghiệp vụ.

**Câu 45.** Nếu disk free thấp và compaction fail, có nên tiếp tục test tới hết thời gian cấu hình?  
**Gợi ý:** Không; STOP và thực hiện recovery theo runbook, bảo vệ dữ liệu.

**Câu 46.** App p99 tăng nhưng server read latency không tăng thì kiểm gì trước?  
**Gợi ý:** Driver pool/throttling/retries, JVM JIT/GC, network/TLS, serialization, generator.

**Câu 47.** Key cache hit ổn định nhưng physical disk reads tăng — có thể vì sao?  
**Gợi ý:** Key cache chỉ giúp lookup, data pages/chunks vẫn miss; compaction có thể cạnh tranh.

**Câu 48.** Kết luận cuối nên phát biểu thế nào?  
**Gợi ý:** “Query family X trên dataset D, topology T, CL Y, QPS Z đạt p99 SLO qua N windows, background backlog ổn định, trong phạm vi được kiểm” — không công bố “Cassandra nhanh tuyệt đối”.

## 26. Tổng kết: warm-up là một phép đo trạng thái, không phải một nút bấm

~~~text
                     CASSANDRA LOAD / FAULT TEST
                                 |
                      1. Define contract
          dataset + partition pattern + RF/CL + query mix
                                 |
                     2. Isolate environment
                versions + hardware + stop limits
                                 |
                     3. Seed known data
               verify oracle + observe flush/SSTables
                                 |
                     4. Controlled warm-up
                Java/driver/JVM + server caches
                memtables/flush/compaction lifecycle
                                 |
               +-----------------+-----------------+
               |                                   |
          Gate NOT_STEADY                       Gate PASS
               |                                   |
        HOLD and explain                      5. Measure
        capacity/workload                   p99 + errors
        or coverage gap                    cache + SSTables
               |                           compaction + disk
               |                                   |
               |                              6. Fault?
               |                             /       \
               |                           NO        YES
               |                           |          |
               |                         REPORT   Inject one fault
               |                                      |
               |                                  CL recovery
               |                                      |
               |                                 Perf recovery
               |                                      |
               +----------------+---------------------+
                                |
                        7. GO / HOLD / STOP
                      with honest limitations
~~~

### 26.1. Năm nguyên tắc bắt buộc nhớ

1. **Đừng gộp mọi warm-up:** JVM/driver caches, Cassandra key/row/chunk caches, OS page cache và SSTable/compaction state có thời gian/trigger khác nhau.
2. **Đừng chỉ chờ một duration:** Đánh giá steady theo nhiều rolling windows và cả backlog/resource trends.
3. **Đừng đo hot key thay cả production:** Working set, key/tenant distribution, TTL/partition size/CL phải đại diện.
4. **Đừng bỏ qua chi phí maintenance:** Flush/compaction/repair có thể làm p99 xấu, ngay cả sau khi generator dừng hoặc node `UN`.
5. **Đừng chỉ nhìn p99:** Kiểm errors, timeouts, correctness, RF/CL, driver attempts, disk headroom và RTO.

**Thông điệp cốt lõi:** Với Apache Cassandra, warm-up có thể vừa **giảm latency** vì cache nhận hot keys, vừa **tăng latency** khi flush/compaction bắt đầu xử lý chi phí của writes trước đó. Một benchmark đáng tin **phải chỉ rõ trạng thái mà nó đo**, bao gồm client/driver cache, data working set, SSTable/compaction lifecycle, consistency level và thời gian quan sát. Chỉ báo một số p99 mà thiếu bối cảnh này sẽ dễ dẫn tới quyết định capacity và failover sai.

## Tài liệu tham khảo

- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — JMX metrics cho Cache, Table, Compaction, client requests, tombstones và streaming.
- [Apache Cassandra — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — memtable → SSTable, compaction lifecycle, strategies, tombstones, read/write amplification.
- [Apache Cassandra — Cassandra Stress](https://cassandra.apache.org/doc/stable/cassandra/tooling/cassandra-stress.html) — commands/options/user mode, ghi chú deprecated và NoSQLBench.
- [Apache Cassandra — Nodetool compactionstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/compactionstats.html) — active/pending compaction và throughput.
- [Apache Cassandra — Nodetool overview](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/nodetool.html) — `tablestats`, `tpstats`, `compactionstats`, các thao tác quan sát và thay đổi có kiểm soát.
- [Apache Cassandra — Use nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html) — compaction state, read/write performance, dropped messages và disk troubleshooting.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — coordinator, tokens, replicas, RF và consistency level.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-first partition design, replication và access patterns.
- [Apache Cassandra Java Driver 4.18 — Metrics](https://apache.github.io/cassandra-java-driver/4.18.0/core/metrics/) — session/node timers, pooling, metrics backends và percentiles.
- [Apache Cassandra Java Driver 4.18 — Pooling](https://apache.github.io/cassandra-java-driver/4.18.0/core/pooling/) — in-flight streams, connections và request multiplexing.
- [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/) — server/client prepared caches và reprepare.
- [Apache Cassandra Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — policy retry, faults và workload amplification.
- [Apache Cassandra Java Driver 4.18 — Request throttling](https://apache.github.io/cassandra-java-driver/4.18.0/core/throttling/) — admission, client queue và timeouts.
- [NoSQLBench](https://docs.nosqlbench.io/) — workload-based benchmarking hiện đại; xem tài liệu riêng về syntax/scenarios.
- [OpenJDK JFR](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html) — Java Flight Recorder theo dõi JIT/GC/allocation và JVM events.
- [Gil Tene — How NOT to Measure Latency](https://www.infoq.com/presentations/latency-response-time/) — coordinated omission và những sai lầm thống kê khi đo latency.


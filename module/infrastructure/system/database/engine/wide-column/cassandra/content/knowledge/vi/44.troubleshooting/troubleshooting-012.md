# Heap/GC kéo dài, bộ nhớ ngoài heap và tài nguyên hệ điều hành trong Apache Cassandra

## 1. Mục tiêu và phạm vi chẩn đoán

Apache Cassandra là hệ quản trị cơ sở dữ liệu phân tán **wide-column**, trong đó mỗi yêu cầu CQL đi qua coordinator, replica, memtable, SSTable, commit log và các lớp cache. Khi ứng dụng Java báo p99 tăng, node bị kill hoặc xuất hiện `OutOfMemoryError`, nguyên nhân có thể không nằm ở “heap thiếu” mà ở **bộ nhớ ngoài heap**, Linux page cache, tài nguyên cgroup, queue, disk I/O hoặc một query đọc partition quá lớn.

Bài này thuộc chương **Xử lý sự cố** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, hướng dẫn điều tra từ JVM đến hệ điều hành, liên hệ với thiết kế partition key, mức nhất quán đọc/ghi, compaction, repair, kết nối Java Driver và các luồng tải thực.

Sau bài học, bạn có thể:

1. Phân biệt **Java heap**, **off-heap/native/direct memory**, **RSS**, **virtual memory**, **Linux page cache**, **filesystem cache**, **container memory limit** và **host RAM**.
2. Đọc GC pause, allocation rate, heap occupancy, full/young GC và phân biệt **GC là nguyên nhân** hay **hậu quả** của workload quá nặng.
3. Chẩn đoán `java.lang.OutOfMemoryError: Java heap space`, `Direct buffer memory`, native allocation failure và OOM-kill từ kernel/cgroup.
4. Hiểu tác động của memtable, cache, read path, SSTables, tombstones, compression và compaction đến heap, off-heap và I/O.
5. Dùng `nodetool`, JMX, GC logs, `jcmd`, `jstat` và lệnh Linux/cgroup để thu bằng chứng an toàn.
6. Liên hệ CPU throttling, swap, disk wait, file descriptors, threads và page cache với p95/p99, timeout, dropped messages.
7. Xây dựng **runbook triage, mitigation, rollback, recovery verification** cho nhiều kiểu sự cố bộ nhớ.
8. Thiết kế test load/fault, dashboard và guardrails để tránh lặp lại sự cố.

**Lưu ý phiên bản:** tên JVM flag, collector, metric JMX, bộ đệm off-heap và cấu hình Cassandra có thể khác đáng kể giữa Cassandra 3.x, 4.x, 5.x, các bản phân phối và JDK. Ví dụ dưới đây chỉ là **khung chẩn đoán cần kiểm tra với release thật**, không phải tập tham số tuning áp dụng đồng loạt.

**Phạm vi thao tác:** các câu lệnh minh họa phải được chạy **chỉ khi có quyền vận hành**, ưu tiên read-only. Các lệnh tạo heap dump, class histogram, thay GC, restart node, compaction/repair hoặc thay kernel/cgroup **cần change procedure riêng**. Bài học không thực thi bất kỳ lệnh nào.

## 2. Phân biệt các lớp bộ nhớ

### 2.1. Một node không chỉ tiêu thụ Java heap

~~~mermaid
flowchart TB
    A["Host / VM RAM"] --> B["Container / cgroup memory accounting"]
    B --> C["Cassandra JVM process"]
    B --> D["Page cache / kernel-accounted memory"]
    C --> E["Java heap: objects, allocations"]
    C --> F["Native/off-heap: direct buffers, malloc, mmap residency"]
    C --> G["Metaspace, code cache, thread stacks, GC/JVM native"]
    C --> H["Memory-mapped files / shared libraries"]
    D --> I["SSTables, commit log, filesystem cache"]
~~~

Sơ đồ là **mô hình logic**: trong Linux, các trang `mmap` có thể được tính đồng thời trong ánh xạ bộ nhớ của process và trong các thống kê page cache; **không cộng mù tất cả ô** thành một tổng vật lý.

### 2.2. Các thuật ngữ

| Thuật ngữ | Là gì? | Đơn vị/điểm dễ nhầm |
|---|---|---|
| JVM heap | Vùng quản lý Java objects, GC xử lý | `-Xmx` là giới hạn tối đa heap, không phải RSS |
| Heap used/committed/max | Dùng thực/đã commit/tối đa | Used giảm sau GC không đồng nghĩa RSS giảm tương ứng |
| Off-heap / native | Bộ nhớ ngoài heap do JVM, thư viện, direct buffers, malloc... dùng | Không nhất thiết được quản lý bởi Java heap GC |
| Direct buffer | `ByteBuffer.allocateDirect`/network I/O buffers | Có thể gặp `Direct buffer memory` dù heap chưa đầy |
| Metaspace / code cache | Class metadata, compiled code | Nằm ngoài Java heap |
| Thread stacks | Stack từng native/Java thread | Nhiều threads có thể làm native memory thiếu |
| `mmap` | Memory mapping file/anonymous region | Virtual size lớn không có nghĩa tất cả RAM đã cấp |
| RSS | Resident Set Size: các trang đang resident của process | Có thể tính cả shared/file-backed pages; không phải toàn host RAM |
| PSS | Proportional Set Size: chia phần shared pages | Hữu ích khi so process dùng shared mappings |
| VSZ/VIRT | Tổng không gian địa chỉ ảo được ánh xạ | Thường **không** phản ánh lượng RAM thật đã dùng |
| Linux page cache | Cache file pages của OS | Là tài nguyên hữu ích, có thể reclaim theo điều kiện |
| Cgroup memory | Bộ nhớ được kernel tính cho container/group | Có thể bao gồm page cache/kernel, không chỉ RSS của JVM |
| Swap | Đưa trang bộ nhớ ra swap device | Có thể gây latency rất lớn; phải xem activity, không chỉ size |
| OOM-kill | Kernel/cgroup giết process khi không đủ bộ nhớ theo policy | Khác Java `OutOfMemoryError` |

### 2.3. Phép tính capacity sơ bộ

Giả sử một container có memory limit **16 GiB**, JVM `-Xmx = 12 GiB`. **Không** có nghĩa còn chính xác 4 GiB cho mọi thành phần khác, vì:

- Heap chưa chắc commit toàn bộ 12 GiB ở mọi thời điểm.
- JVM còn metaspace, JIT code cache, GC metadata, thread stacks.
- Direct/native buffers và các native allocations có thể tăng theo tải.
- Page cache/kernel memory được cgroup account theo kernel/version/config.
- Memory-mapped file pages có resident set, không đơn giản cộng bằng file size.
- Cgroup memory pressure và OOM policy phụ thuộc giới hạn thực tế của pod/container.

Mục tiêu là **một budget có headroom**, không phải “đặt Xmx = 90% RAM là tối ưu”. Cần đo **peak thực**, nền tải, phần trăm cache và mức tăng trong compaction/repair/restart.

### 2.4. Đừng cộng RSS và page cache mù quáng

`/proc/PID/status VmRSS` có thể chứa file-backed resident pages; `memory.stat file` phản ánh một số trang filesystem cache được account trong cgroup. Cộng `RSS + page cache` có thể **đếm đôi**. Khi phân tích:

1. Chọn một **ranh giới đo** (host, cgroup, process).
2. Ghi rõ memory metrics được account ở đâu.
3. Nếu cần chia sẻ mappings, dùng PSS/`smaps_rollup` với quyền phù hợp.
4. Xem `memory.current`, `memory.stat` và `memory.events` cho container, không chỉ heap JMX.
5. So theo **time-series**, không chỉ snapshot tại lúc node gần chết.

## 3. Triệu chứng ban đầu và nguyên nhân có thể

| Triệu chứng | Giả thuyết cần ưu tiên | Bằng chứng phân biệt |
|---|---|---|
| Heap used tăng liên tục, Full GC không giảm | Retained objects, cache/buffer, leak, workload nhiều live objects | Post-GC old/live occupancy, heap histogram/dump có kiểm soát |
| Young GC nhiều, heap sau GC vẫn thấp | Allocation churn, mapping/pages/large rows | Allocation rate, pause tổng, object profile |
| Stop-the-world pauses kéo dài | GC pressure, humongous allocations, CPU throttling hoặc collector config | GC log + CPU throttling + JVM safepoint |
| JVM `Java heap space` | Heap allocation không cấp được | JVM log/error, heap after GC, histo |
| JVM `Direct buffer memory` | Direct memory pressure/limit | Native/direct buffer pools, NMT nếu bật |
| Process exit 137/`OOMKilled` | Kernel/cgroup có thể đã kill | `memory.events`/container status/kernel logs |
| Cgroup memory.current cao nhưng heap thấp | File cache, native, mmap, kernel accounting | `memory.stat` breakdown, RSS/PSS |
| Host `free` available thấp, swap-in/out tăng | Memory pressure/swap | `vmstat si/so`, PSI, latency |
| CPU quota throttling cao nhưng GC pause tăng | GC/JVM không được cấp CPU kịp | `cpu.stat`, per-core, GC timeline |
| `too many open files` | FD limit/socket/SSTable files | `/proc/PID/fd`, `ulimit`, `lsof` theo quyền |
| `unable to create native thread` | Native memory/thread PID limit | Thread counts, cgroup `pids.current`/`pids.max` |
| Read p99 tăng cùng SSTables/tombstones | Read amplification hoặc partition rộng | `tablestats`, table histogram, tracing có giới hạn |
| Write p99 tăng cùng memtable flush/compaction | Disk/commitlog/background I/O | `compactionstats`, disk await/IOPS, commitlog metrics |

**Không gán nguyên nhân chỉ từ một chỉ số.** Ví dụ Full GC dài có thể do heap live set thật lớn, nhưng cũng có thể kéo dài vì container bị CPU throttling.

## 4. Quy trình triage 10 phút đầu

### 4.1. Bảo toàn bằng chứng trước khi restart

1. Ghi **UTC timeline**: bắt đầu p99 tăng, service deploy, schema/data change, compaction, repair, traffic burst, node restart.
2. Xác định **blast radius**: một node, một rack/DC, coordinator nào, ứng dụng Java hay toàn cluster?
3. Xem lỗi phân loại: timeout, `OverloadedException` (nếu version hỗ trợ), OOM, connection refused, dropped message, `UnavailableException`.
4. Xem **GC pauses + post-GC heap used**, không chỉ số lần GC.
5. Xem **process RSS/PSS** và **cgroup memory.current/max/events**, phân biệt OOMKilled từ Java OOM.
6. Xem **CPU throttling**, swap, disk wait, pending queue, compaction backlog.
7. Xem driver concurrency, query templates, rows/page, bytes/row, hot partitions.
8. Ghi nhận config có hiệu lực: Cassandra/JDK, GC, `-Xms`/`-Xmx`, limits/requests, memory tunables.
9. Áp dụng **giảm tải có kiểm soát** nếu vượt guardrails; không thay JVM flags toàn cluster trong lúc mất quorum.
10. Kiểm tra sau giảm tải: p99/error/queue/GC/RSS có phục hồi không? Ghi cả điều **không** phục hồi.

### 4.2. Bản đồ quyết định ban đầu

~~~mermaid
flowchart TD
    A["Node p99 tăng / restart / OOM"] --> B{"Process bị kill bởi kernel/cgroup?"}
    B -->|Có| C["Kiểm memory.events, pod OOMKilled, RSS/native/file cache"]
    B -->|Không| D{"JVM báo OutOfMemoryError?"}
    D -->|Có| E["Phân loại heap space vs direct vs native threads/metaspace"]
    D -->|Không| F{"GC pause và post-GC heap tăng?"}
    F -->|Có| G["Allocation/live set/heap config + CPU throttling"]
    F -->|Không| H["Disk/network/FD/threads/replica queues/compaction"]
    C --> I["Guardrails + targeted remediation"]
    E --> I
    G --> I
    H --> I
    I --> J["Theo dõi recovery, quorum, correctness, SLO"]
~~~

### 4.3. Triaging không phải “chạy mọi lệnh”

Thu bằng chứng nào **ít tốn tài nguyên nhất** trước:

- Metrics/GC logs đã có → read-only và ít intrusive.
- `nodetool info/tpstats/compactionstats` hoặc JMX metrics → quan sát cluster.
- `/proc`, `vmstat`, `pidstat`, cgroup files → quan sát OS/container.
- `jcmd Thread.print`, class histogram, heap dump → có thể gây pause/chiếm CPU/disk, **chỉ khi có phê duyệt**.

Không chạy `jcmd GC.heap_dump` trên node gần full disk chỉ để “xem heap”, vì heap dump có thể lớn đến mức làm cạn disk và làm tình hình tệ hơn.

## 5. GC pause và heap occupancy: nên nhìn những gì?

### 5.1. Ba hình dạng GC khác nhau

**A. Allocation churn:** heap tăng nhanh giữa các lần young GC, giảm mạnh sau GC; throughput có thể cao nhưng tổng thời gian GC/second nhiều, gây latency jitter.

**B. Live set tăng:** sau mỗi full/mixed GC, heap used vẫn cao và tăng dần; có thể do cache/buffer retain, threadlocals, page-result retention hoặc leak.

**C. GC không đủ CPU:** heap sống chưa quá lớn nhưng pause wall-clock kéo dài khi container bị CPU quota throttling hoặc host steal time cao; cần chứng cứ thời gian CPU bị hạn chế.

### 5.2. Ví dụ biểu đồ thời gian dưới dạng bảng

| UTC | Heap used trước GC | Heap used sau GC | GC pause | CPU throttled % | Read p99 |
|---|---:|---:|---:|---:|---:|
| 10:00 | 8,0 GiB | 4,1 GiB | 60 ms | 0% | 75 ms |
| 10:05 | 9,0 GiB | 5,0 GiB | 95 ms | 3% | 120 ms |
| 10:10 | 10,5 GiB | 7,9 GiB | 420 ms | 28% | 650 ms |
| 10:15 | 11,5 GiB | 10,2 GiB | 2.100 ms | 35% | 3.000 ms |

**Số liệu giả định**, minh họa đồng thời live heap và throttling tăng. Không suy causality chỉ từ correlation; cần GC log, workload và cgroup samples quanh timestamp ấy.

### 5.3. Percentile pause không bằng p99 request

- JVM GC pause max 300 ms có thể ảnh hưởng nhiều in-flight requests, nhưng **không thể cộng 300 ms vào mọi request p99**.
- Driver p99 đo client→coordinator; Cassandra GC pause là một thành phần có thể gây queue/retry.
- Gộp histogram GC pause với histogram API p99 bằng phép trung bình không có ý nghĩa.
- Một ứng dụng đọc RF=3/CL=LOCAL_QUORUM có thể bị ảnh hưởng khác nhau tùy replica/coordinator nào pause.

### 5.4. Tỷ lệ thời gian GC

Giả sử một node có 4,8 giây stop-the-world pause trong một cửa sổ 60 giây:

~~~text
GC pause fraction = 4.8 / 60 = 8%.
~~~

Đây là **tỷ lệ wall-clock bị dừng bởi các pha stop-the-world** theo phép đo tương ứng, không phải CPU utilization tổng cho GC. Các collector có cả concurrent phases dùng CPU nhưng không phải STW. Với GC concurrent, cần đo riêng CPU/overhead và pause time.

### 5.5. Post-GC occupancy hữu ích hơn chụp heap used tức thời

Heap used đạt 90% ngay trước young GC có thể là bình thường nếu còn nhiều short-lived objects. Trái lại, heap used 80–90% **ngay sau những chu kỳ reclaim phù hợp** có thể báo hiệu live set lớn và ít headroom.

Nhưng mỗi collector có cách phân bổ generations, concurrent cycle và bước mixed collection khác nhau. Không dùng một điều kiện “after one young GC 80% = leak” cho mọi JDK.

## 6. JVM collector và GC logging theo phiên bản

### 6.1. Kiểm tra collector thực tế thay vì đoán

Các bản Cassandra/JDK trong thực tế có thể dùng các collector khác nhau như CMS (cũ), G1 hoặc những collector được release hỗ trợ. **JDK mới có thể đã bỏ collector cũ**; Cassandra release cũng có bộ JVM options riêng.

Không sao chép flag `-XX:+UseConcMarkSweepGC` từ một bài cũ sang JDK hiện đại. Trước khi thay GC phải xác minh:

- Cassandra version và **supported JDK versions**.
- Collector đang chạy thực tế trong `VM.flags`/startup log.
- Heap size, host/container CPU/memory và restart/rolling policy.
- GC log hiện có, baseline workload và SLO.
- Compatibility của flags và vendor JDK.

### 6.2. Ví dụ GC logging trên JDK có Unified Logging

~~~text
# Chỉ minh họa flag syntax cho JVM/JDK hỗ trợ.
-Xlog:gc*,safepoint:file=/var/log/cassandra/gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

Đối với **JDK cũ**, logging options khác, ví dụ `-XX:+PrintGCDetails` có thể thuộc hệ flags cũ. **Đừng đưa cả hai cấu hình vào production mà không test**, và không đặt gc.log trên volume có quota quá nhỏ hoặc bị logging storm.

Một dòng GC log thường cho biết:

- Collector phase/cause.
- Pause duration (thường ms).
- Heap usage trước/sau cùng committed capacity.
- CPU wall/user/sys timing nếu release hỗ trợ.
- Safepoint time, concurrent cycle và allocation pressure.

### 6.3. GC log và request timeline

~~~text
12:00:01.000  API p99 bắt đầu tăng
12:00:01.200  Cassandra node B GC pause 1.4 s
12:00:01.250  Driver timeout/retry attempts tăng
12:00:02.700  Node B hết pause, pending queue còn cao
12:00:05.000  API p99 trở lại baseline sau drain queue
~~~

Đây chỉ là timeline giả định. Phải xác minh clocks/UTC, request IDs và per-node metrics; không lấy lệch giờ giữa máy rồi kết luận pause xảy ra “trước” retry.

## 7. Các nguyên nhân làm heap allocation tăng trong Cassandra

### 7.1. Query theo khóa phân vùng vẫn có thể đắt

Một CQL hợp lệ:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

có thể tương đối rẻ khi partition vừa phải và ít tombstone. Nhưng workload khác:

~~~cql
-- Bài học cảnh báo: đọc toàn bộ một partition rất rộng.
SELECT *
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

có thể trả hàng triệu row. Kể cả chỉ một logical partition, các page, row decoding, large collection values và request context có thể gây allocation trên server và client.

### 7.2. Những nguồn áp lực heap/read path

- Partition quá rộng: nhiều clustering rows/large cells.
- Nhiều tombstone hoặc TTL hết hạn: read path phải scan dữ liệu không còn sống.
- Nhiều SSTable chưa compaction: merge/read amplification tăng.
- Không giới hạn `LIMIT` hoặc client tiêu thụ toàn bộ pages.
- `ALLOW FILTERING` scan nhiều partition.
- Index query có selectivity thấp, nhiều replica scan.
- Large batches hoặc quá nhiều đồng thời.
- LWT hot keys làm queue/latency tăng.
- Bulk backfill và repair/streaming cạnh tranh I/O/CPU.

**Đừng chỉ tăng `-Xmx` để giữ một access pattern không phù hợp Cassandra.** Fix root cause thường nằm ở data modeling, bucket, page size, TTL/tombstone và admission control.

### 7.3. Client Java cũng có thể OOM riêng

Ở ứng dụng Java Driver:

~~~java
// ANTI-PATTERN: hút toàn bộ pages vào một List lớn.
List<Row> allRows = new ArrayList<>();
for (Row row : session.execute(statement)) {
    allRows.add(row);
}
~~~

Driver có thể fetch nhiều page; List giữ references và làm heap ứng dụng tăng. **OOM client không chứng minh node Cassandra bị heap OOM**. Cần xem heap metrics của **process phát sinh lỗi**.

Khi business API cần streaming/async/reactive, dùng paged consumption, bounded concurrency/backpressure và giới hạn response bytes. Không giả định reactive `Flux` tự bảo đảm bounded memory nếu vẫn `collectList()`.

## 8. Cassandra memtable, caches và off-heap

### 8.1. Memtable không phải “mọi thứ luôn nằm trong Java heap”

Cassandra ghi mutation vào memtable theo storage engine/config version, sau đó flush thành SSTable. **Memtable allocations có thể dùng on-heap, off-heap hoặc dạng lai tùy phiên bản/config**, vì vậy không thể nhìn `nodetool tablestats` rồi gọi toàn bộ memtable size là Java heap used.

Khi memtable pressure tăng:

- Flush diễn ra thường xuyên hơn.
- Disk write/commitlog/compaction pressure tăng.
- Background tasks tranh CPU/disk.
- Read path có thể phải merge thêm SSTables.
- p99 write/read có thể tăng dù heap sau GC không quá cao.

### 8.2. Các bộ đệm thường gặp

| Thành phần | Tác dụng | Rủi ro điều tra |
|---|---|---|
| Memtable | Giữ mutations trước flush | Heap/off-heap pressure; flush backlog |
| Key cache | Giúp tìm vị trí SSTable/index | Chiếm memory và thay đổi read I/O |
| Row cache | Cache dữ liệu row theo config | Có thể tăng footprint/invalidation cost |
| Chunk/file cache | Cache chunks/buffers tùy Cassandra version | Direct/native memory pressure |
| Bloom filter | Tránh đọc SSTables không chứa partition | Memory footprint; false positives |
| Index/compression metadata | Phục vụ SSTable lookup/decompression | Off-heap/mapped structures tùy release |
| OS page cache | Cache file pages | Reclaimable nhưng pressure có thể gây I/O burst |
| Driver connection buffers | Native transport/network | Direct/native buffers và concurrency |

**Đừng cộng toàn bộ các cache sizes với `-Xmx` rồi gọi đó là RSS.** Một số cache được account trên heap, một số off-heap, một số là file-backed/mmap hoặc page cache; cần kiểm release và metrics.

### 8.3. Không tắt cache mù quáng

Nếu key cache hoặc chunk cache gây footprint cao, tắt ngay có thể làm read I/O tăng và p99 tệ hơn. Một thay đổi cache cần:

1. Đo hit/miss, footprint, disk await và p99 trước.
2. Xác nhận cache nằm heap/off-heap theo version.
3. Thử trên lab, có dataset/warm-up thực.
4. Điều chỉnh hạn mức **theo tài nguyên tổng**.
5. Rollout từng node và kiểm retry/CL/headroom.
6. Có rollback nếu disk/latency tăng.

## 9. Compaction, tombstone và bộ nhớ

### 9.1. Compaction là I/O rewriting, không chỉ vấn đề heap

Compaction đọc nhiều SSTables, merge/rewrite dữ liệu, sử dụng CPU, RAM buffers và disk read/write bandwidth. Khi compaction backlog tăng:

- SSTable count cao khiến read amplification tăng.
- Disk await cao làm replica đáp ứng chậm.
- Page cache có thể bị thay thế mạnh.
- Native/heap allocations có thể thay đổi.
- Commitlog/memtable flush bị ảnh hưởng nếu disk đã bão hòa.

Vì vậy **GC pause tăng cùng compaction pending** không đủ kết luận compaction “leak Java heap”. Có thể compaction tranh CPU/disk, kéo dài wall-clock GC hoặc tạo hiệu ứng domino qua queue.

### 9.2. TTL và tombstones

Trong Cassandra, cell có TTL hết hạn thường không còn xuất hiện như dữ liệu sống, nhưng dữ liệu/marker có thể tiếp tục tồn tại cho tới khi compaction và các điều kiện an toàn. Khi query phải scan nhiều tombstone để trả ít row:

~~~text
SELECT trả 20 live rows
Nhưng read path đã xét:
  50.000 expired/deleted cells
  nhiều SSTables

Người dùng: 20 row
Chi phí thực: lớn hơn nhiều 20 row
~~~

Số liệu trên là ví dụ. Query rất nhiều tombstone làm CPU, disk I/O, allocation và tail latency tăng. Điều chỉnh TTL/retention, partition bucketing và compaction strategy phải theo data lifecycle.

### 9.3. Không cưỡng ép major compaction khi node thiếu RAM/disk

`nodetool compact` và các tác vụ tương tự có thể tiêu thụ nhiều disk/CPU/I/O tạm. Trên node đang `OOMKilled` hoặc disk free thấp, một thao tác compaction không kiểm soát có thể làm outage nặng hơn.

Ưu tiên đo workload, giảm tải, kiểm capacity và thực hiện SOP trên môi trường được phép. Repair/streaming cũng tiêu thụ I/O/network nên phải xem cùng timeline.

## 10. `nodetool` và JMX: phân biệt heap với storage load

### 10.1. Các lệnh quan sát cơ bản

~~~bash
# Tên lệnh/cú pháp phụ thuộc Cassandra release.
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats telemetry_lab.readings_by_device_day
nodetool tablehistograms telemetry_lab readings_by_device_day
nodetool gcstats
nodetool netstats
~~~

Tất cả là **lệnh minh họa**, không chạy trong bước soạn bài. Kiểm `nodetool help` và quyền truy cập phù hợp trước khi dùng. Một số release không hỗ trợ cùng cú pháp/metric.

| Công cụ | Chỉ số hữu ích | Giới hạn diễn giải |
|---|---|---|
| `status` | Node UP/DOWN, DC/rack, ownership | `UN` không chứng minh p99/GC khỏe |
| `info` | Heap usage, uptime, caches và load tùy release | Heap không bằng RSS/cgroup memory |
| `tpstats` | Stage pending/active/completed/dropped | Stage tasks không phải logical HTTP requests |
| `compactionstats` | Compaction active/pending/progress | Backlog tăng chưa chỉ ra heap leak |
| `tablestats` | SSTables, memtable, read/write stats | Memtable size không mặc định toàn on-heap |
| `tablehistograms` | Table latency/distribution nếu hỗ trợ | Không thay client end-to-end percentile |
| `gcstats` | GC aggregate theo release | Không thay GC pause timeline/log |
| `netstats` | SSTable streaming | Trống không có nghĩa CQL network idle |

### 10.2. Lớp metrics JMX nên thu

| Nhóm | Metric | Vì sao cần |
|---|---|---|
| JVM heap pools | Used, committed, max | Live/available Java heap |
| JVM GC | Collection count/time, pause histogram nếu có | Pauses và GC overhead |
| BufferPoolMXBean | Direct/mapped buffers và memory | Một phần off-heap, không bao hết native allocations |
| JVM threads | Count, peak, blocked | Thread/native-stack pressure |
| Cassandra stages | Active, pending, dropped | Queue khi node chậm |
| Memtable | Occupancy/flush/pending theo release | On/off-heap và disk pressure |
| SSTables | Count, read amplification, tombstones | Query/storage layout |
| Compaction | Pending/bytes/progress | Background CPU/disk |
| Commitlog | Sync latency, segments, pressure | Write path |
| Native transport | In-flight/connection counts | Buffers, request pressure |

JMX MBean names, GC pool names và exporter labels **khác theo Cassandra/JDK/version**. Phải kiểm mapping collector đang có; không tự gán một metric tưởng tượng cho hệ thống.

### 10.3. Ví dụ quan sát có nhiều nguyên nhân

~~~text
Time      ReadStage Pending    GC pause    Disk await
10:00                    20       40 ms        4 ms
10:05                   350      150 ms       10 ms
10:10                 2.100      950 ms       70 ms
~~~

Một khả năng là disk chậm → queue dồn → sống nhiều request objects → GC nặng. Khả năng khác là GC pause trước → queue dồn → I/O burst sau. **Timeline và các thông số khác** cần thiết để xác định nguyên nhân và chiều tác động.

## 11. Lệnh Linux read-only: host và process

### 11.1. Host memory, CPU và disk

~~~bash
free -h
vmstat 1 5
top -b -n 1
ps -eo pid,ppid,rss,vsz,%cpu,%mem,comm
df -h
df -i
~~~

`free -h` có thể phản ánh RAM host, **không phải memory limit của pod**. `vmstat` cần đọc các mẫu interval, không chỉ sample đầu. `df -i` giúp phát hiện inode exhaustion ngay cả khi còn disk bytes.

### 11.2. Ý nghĩa `vmstat`

| Field | Ý nghĩa khái quát | Không nên kết luận |
|---|---|---|
| `r` | Runnable tasks chờ CPU | Tất cả đều là GC threads |
| `b` | Blocked tasks | Chỉ vì heap |
| `si`/`so` | Swap-in/swap-out | SwapUsed khác 0 luôn là nguyên nhân |
| `bi`/`bo` | Block I/O | Bằng số CQL requests |
| `us`/`sy` | CPU user/system | Không có CPU throttling cgroup |
| `wa` | CPU iowait | Không phải % disk busy trực tiếp |
| `st` | VM steal time | Không đáng kể nếu host CPU trung bình thấp |

Nếu `si/so` tăng liên tục cùng p99 và GC pause, cần kiểm memory pressure/swap policy. Không chỉ tắt swap hoặc chỉnh kernel sysctl theo suy đoán khi chưa có change control.

### 11.3. Process resident memory

~~~bash
# PID 12345 chỉ là placeholder; xác minh đúng PID Cassandra.
ps -p 12345 -o pid,etime,rss,vsz,%cpu,%mem,comm
cat /proc/12345/status
cat /proc/12345/smaps_rollup

# Nếu sysstat có sẵn:
pidstat -r -u -d -p 12345 1 5
~~~

- `VmRSS`: resident set theo process, có thể gồm shared/file-backed pages.
- `VmSize`/`VSZ`: không gian ảo, **không đồng nghĩa RAM đã cấp**.
- `Pss` từ `smaps_rollup`: có ích khi shared mappings đáng kể.
- `Threads`: giúp nhận biết native thread pressure.
- `VmSwap`: một chỉ báo swap pages theo process, không bao toàn bộ host.

Đọc `smaps_rollup`/`lsof` liên tục có thể có chi phí trên JVM nhiều mappings. Chỉ thu có điều kiện; redact host/file names nhạy cảm khi báo cáo.

## 12. Cgroup: tại sao heap chưa đầy mà pod vẫn `OOMKilled`?

### 12.1. Cgroup v2 read-only files

~~~bash
# Đường dẫn ví dụ khi shell đang ở đúng cgroup v2.
# Trong Kubernetes path thực có thể nằm dưới một hierarchy khác.
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events

cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpu.max

cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
~~~

`memory.max` trả `max` nếu không có hard limit theo cgroup v2. `memory.events` có các counter như `high`, `max`, `oom`, `oom_kill` tùy kernel. Lấy **delta theo thời gian** trên **đúng cgroup của Cassandra**, tránh suy từ root cgroup.

Cgroup v1 có tên file khác, ví dụ `memory.usage_in_bytes` và `memory.limit_in_bytes`; đối chiếu hệ thống hiện hành.

### 12.2. JVM OOM khác kernel OOM-kill

~~~text
JVM-level:
  java.lang.OutOfMemoryError: Java heap space
  java.lang.OutOfMemoryError: Direct buffer memory
  java.lang.OutOfMemoryError: unable to create native thread

Kernel/container-level:
  Process bị SIGKILL (có thể exit 137)
  Pod reason: OOMKilled (nếu runtime báo)
  cgroup memory.events oom_kill tăng
~~~

**Exit 137 một mình không chứng minh kernel OOM**: `SIGKILL` có thể đến từ nguồn khác. Cần container runtime status, cgroup counter hoặc kernel logs nếu được phép.

### 12.3. Một phép tính diễn giải

~~~text
Container memory.max      16 GiB
Container memory.current  15.8 GiB
JVM -Xmx                  10 GiB
JVM heap used              7.5 GiB
Process RSS               12 GiB
memory.stat file           4 GiB
memory.events oom_kill     +1

=> Heap chưa đầy -Xmx vẫn có thể bị OOMKilled.
=> Không cộng RSS và file cache mù vì có thể đếm đôi.
=> Phải tìm native/file/kernel memory bên trong memory.current.
~~~

Số liệu chỉ minh họa. Cgroup memory accounting bao gồm các thành phần khác Java heap; page cache có thể được reclaim nhưng reclaim không miễn phí hoặc luôn đủ nhanh. Không chọn `-Xmx` bằng 100% `memory.max`.

## 13. CPU throttling có thể kéo dài wall-clock GC

### 13.1. Cgroup CPU counters

~~~text
usage_usec         110000000
nr_periods             10000
nr_throttled            1200
throttled_usec       4500000
~~~

Đây là cumulative counters minh họa trên cgroup v2. `nr_throttled / nr_periods` là tỷ lệ scheduling periods bị throttled, **không bằng phần trăm GC time**. `throttled_usec` và cách tổng hợp qua CPU/threads phụ thuộc kernel/cgroup.

### 13.2. Vì sao quan trọng?

- Host còn CPU rảnh nhưng container có `cpu.max`/quota thấp.
- GC worker threads và Cassandra executor threads không được scheduler cấp CPU đúng lúc.
- Stop-the-world pause **wall time** có thể dài hơn mức workload tương ứng nếu không bị throttling.
- Driver retry/connection storm có thể tiêu hao CPU thêm.
- Một node nóng dễ chịu ảnh hưởng hơn cluster average.

Chẩn đoán: đặt `cpu.stat` delta, GC pause log, CPU per-core, request QPS và `tpstats` Pending trên cùng timeline. **Tăng heap không tự chữa CPU throttling**. Điều chỉnh CPU quota/requests cần capacity và canary test.

## 14. Swap, PSI và memory pressure

### 14.1. Swap activity

- `SwapUsed > 0` không tự là lỗi.
- `vmstat si/so` có hoạt động liên tục cùng disk latency/p99 mới là dấu hiệu hữu ích.
- Không thay `vm.swappiness` hoặc tắt swap trên production thiếu SOP.
- Kubernetes/kernel versions có swap policy khác, phải kiểm runtime thực tế.

### 14.2. Pressure Stall Information

~~~bash
# Chỉ dùng trên kernel hỗ trợ PSI.
cat /proc/pressure/memory
cat /proc/pressure/cpu
cat /proc/pressure/io
~~~

PSI có thể cung cấp `avg10/avg60/avg300` và `total` về thời gian tác vụ phải chờ tài nguyên. Trên một số cgroup v2 có `memory.pressure`/`cpu.pressure`/`io.pressure`. Scope host và scope cgroup khác nhau; **không so hai chỉ số như cùng một population**.

## 15. `jcmd`, `jstat` và công cụ JVM

### 15.1. Công cụ theo mức độ tác động

~~~bash
# PID 12345 là ví dụ; xác minh đúng PID và JDK.
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jstat -gcutil 12345 1000 5

# Có thể ảnh hưởng node, chỉ khi được cho phép:
jcmd 12345 Thread.print
~~~

| Công cụ | Giá trị | Rủi ro |
|---|---|---|
| GC logs/JMX metrics sẵn có | Pause, heap, GC pools | Thường ít intrusive |
| `jcmd VM.flags` | JVM flags/collector | Cần quyền attach |
| `jcmd GC.heap_info` | Heap usage/committed | Attach overhead |
| `jstat -gcutil` | GC counters | Phụ thuộc JDK |
| `jcmd Thread.print` | Thread/lock states | CPU/pause và metadata nhạy cảm |
| `jcmd GC.class_histogram` | Class/object counts | Có thể kích hoạt GC/safepoint |
| `jcmd GC.heap_dump` | Heap objects/references | File lớn, pause, secrets |
| `jcmd VM.native_memory` | NMT categories | Cần NMT, coverage không đầy đủ |

### 15.2. Đừng lấy heap dump làm bước triage đầu tiên

~~~text
Không chạy tự phát trên node gần hết disk:
    jcmd 12345 GC.heap_dump /secure/path/heap.hprof

Chỉ khi:
    có change approval và chỗ lưu an toàn;
    đủ disk headroom, tính đến pause/CL;
    artifact được bảo vệ vì có thể chứa secrets/user data;
    có phương án recovery/rollback.
~~~

Một class histogram có nhiều `byte[]` không tự chứng minh memory leak. Cần xem **post-GC live heap trend** qua nhiều windows cùng workload, phân tích ownership/reference paths và loại trừ cache/in-flight pages chủ ý.

## 16. Native Memory Tracking và direct buffers

### 16.1. Giới hạn của NMT

Nếu đã bật `-XX:NativeMemoryTracking=summary`/`detail` từ startup trên HotSpot/JDK tương thích:

~~~bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff
~~~

NMT phân nhóm một phần bộ nhớ JVM: heap reserved/committed, class metadata, GC, thread stacks, code cache. **NMT không đo mọi JNI/libc/native allocations và Linux page cache**, lại có overhead theo mức summary/detail. Không coi NMT total bằng RSS/cgroup memory.

### 16.2. Reserved và resident khác nhau

~~~text
JVM reserved virtual space  30 GiB
NMT committed              12 GiB
Process RSS                13 GiB
Cgroup memory.current      15 GiB

Các số minh họa; KHÔNG cộng thành 70 GiB.
~~~

Virtual reservation không nhất thiết resident; committed không bằng chính xác RSS; cgroup có kernel/file cache accounting.

### 16.3. Direct buffer OOM

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
java.lang.OutOfMemoryError:
  Cannot reserve ... bytes of direct buffer memory
~~~

Kiểm direct/mapped BufferPoolMXBean, native allocations, process RSS/PSS, cgroup memory.events, driver/network in-flight và payload bytes. Nguyên nhân có thể là nhiều buffers, page/row lớn, native leak, cap không phù hợp hoặc retry storm.

**Không tăng `-XX:MaxDirectMemorySize` vô điều kiện**: nếu container memory limit không tăng/headroom không đủ, có thể chuyển từ Java direct-memory OOM sang kernel OOMKilled.

## 17. Threads, file descriptors và tài nguyên OS

### 17.1. Native thread exhaustion

~~~text
java.lang.OutOfMemoryError:
  unable to create native thread
~~~

Có thể vì thread leak, stack reservations, `pids.max`, `TasksMax`, `ulimit -u`, OS commit/memory limits. Kiểm `Threads` trong `/proc/PID/status`, JVM thread count, `pids.current/max`, process limits và thread dump có kiểm soát.

**Tăng Java heap không giải quyết hết native thread limits.**

### 17.2. FD exhaustion

~~~bash
# Nếu có quyền và đúng PID:
cat /proc/12345/limits
ls /proc/12345/fd
~~~

`Too many open files` có thể liên quan sockets, SSTables, logging và connection churn. Xem FD count trend với limit, SSTable counts, native transport và leak. Không nâng `nofile` vô hạn hoặc chạy `lsof` toàn host liên tục trên node quá tải.

### 17.3. I/O pressure có thể khiến heap tăng gián tiếp

Disk chậm → memtable flush/commitlog/compaction chậm → pending requests giữ objects lâu → heap live occupancy/GC tăng → driver timeout/retry tiếp tục khuếch đại tải. Vì vậy **disk await, free space, IOPS và compaction pending** phải được đặt cạnh heap/GC trên timeline.

## 18. Java Driver paging, concurrency và OOM client/server

### 18.1. Một CQL query có thể gây áp lực ở hai JVM

~~~text
REST /readings
  -> Java app / driver
    -> SELECT theo partition key
      -> Cassandra coordinator/replica
         -> memtables, SSTables, tombstones
    <- nhiều pages
  -> client gom kết quả thành List/JSON
~~~

Ở server: CPU, disk I/O, heap/off-heap buffers và tombstone scanning. Ở client: result references, JSON serialization, `List`, futures và direct network buffers.

| Cơ chế | Giới hạn | Không giới hạn |
|---|---|---|
| CQL `LIMIT 20` | Result rows | Tombstones/storage cells phải scan |
| Driver page size 100 | Mục tiêu rows/page | Tổng rows của query |
| In-flight cap 64 | Outstanding requests trong scope quota | Tất cả client instances |
| Reactive `request(n)` | Demand downstream | Data model / server IO |
| `flatMap(...,8)` | Concurrency trong pipeline | Concurrency toàn HTTP service |

### 18.2. Anti-pattern Java

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.ArrayList;
import java.util.List;

// Anti-pattern: tích lũy tất cả rows của truy vấn dài.
List<Row> rows = new ArrayList<>();
for (Row row : session.execute(statement)) {
    rows.add(row);
}
~~~

Driver có thể fetch nhiều pages, nhưng `List` vẫn giữ mọi row. **Application heap OOM không tự chứng minh Cassandra node OOM**.

Query bounded:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 20;
~~~

Vẫn cần kiểm tombstone density, vì LIMIT 20 có thể buộc read path scan nhiều tombstones để tìm đủ 20 live rows.

### 18.3. Retry amplification

~~~text
1.000 logical reads/s
20% retry thêm một attempt
=> ~1.200 driver attempts/s

Gateway retry / speculative execution có thể làm cao hơn.
~~~

Không retry vô hạn khi GC/queue đã bão hòa. Timeout write/LWT/counter/TTL không chứng minh mutation chưa apply.

## 19. Phân lớp quan sát và timeline

### 19.1. Đo đúng process

| Bằng chứng | Scope | Điều tra |
|---|---|---|
| Java app `OutOfMemoryError` | Client/driver JVM | Result lists/JSON/futures |
| Cassandra GC log | Cassandra node JVM | Live heap/GC pauses |
| Driver request p99 | Client→coordinator | Pools/network/retry |
| `tpstats` Pending | Server executor | Queues, stalls |
| `memory.events oom_kill` | Cgroup cụ thể | Hard memory cap |
| `smaps_rollup` | Process PID | RSS/PSS/file mappings |
| Disk await/IOPS | Node/device | Compaction/commitlog/SSTables |

### 19.2. Correlation không tự là nguyên nhân

| UTC | CQL p99 | GC pause max | Post-GC heap | Cgroup mem | ReadStage pending | Disk await |
|---|---:|---:|---:|---:|---:|---:|
| 10:00 | 90 ms | 50 ms | 4,1 GiB | 9 GiB | 20 | 4 ms |
| 10:05 | 250 ms | 150 ms | 5,0 GiB | 11 GiB | 350 | 14 ms |
| 10:10 | 1.200 ms | 800 ms | 7,9 GiB | 14 GiB | 2.100 | 65 ms |
| 10:15 | 170 ms | 100 ms | 5,4 GiB | 12 GiB | 120 | 10 ms |

Toàn bộ số liệu **giả định**. Cần offered load, per-node workload, retries, compaction, CPU quota, swap và change timeline để tìm root cause.

### 19.3. Labels metrics phải hữu hạn

~~~text
component=cassandra-server
dc=dc1
symptom=gc_pause_and_queue_growth
post_gc_heap_band=high
cgroup_oom_kill_delta=0
cpu_throttled_band=high
query_template=latest20_by_device_day
~~~

Đây là schema log/metric đề xuất, **không phải Cassandra metrics mặc định**. Không đưa raw tenant/device IDs, routing keys, secrets hoặc bind values vào labels.

## 20. Memory budget theo capacity và failover

### 20.1. Phân vùng budget (mô hình, không cộng snapshot mù)

~~~text
Java heap
JVM native/metaspace/thread stacks
Direct/network/off-heap structures
Memory-mapped/file-backed resident pages
Kernel/accounted page cache
Safety margin cho compaction/repair/failover

Các vùng có thể chồng lấp khi đo bằng RSS/NMT/memory.stat.
~~~

| Container 32 GiB giả định | Budget hoạch định |
|---|---:|
| Heap cap `-Xmx` | 16 GiB |
| JVM native/metadata/threads | 2 GiB |
| Direct/off-heap | 3 GiB |
| File cache/mmap/kernel | 6 GiB |
| Margin | 5 GiB |
| **Tổng mô hình** | **32 GiB** |

Không áp dụng bảng như tuning recommendation. Phải đo peak theo workload, check cgroup accounting và giữ headroom khi node down/repair/streaming.

### 20.2. Đủ quorum không có nghĩa đủ memory

Với RF=3, `LOCAL_QUORUM` thường cần hai replica trong DC. Nếu một node down, hai replica còn lại có thể đạt điều kiện ACK, nhưng workload/in-flight/buffers trên chúng tăng. Hints/repair/streaming khi node quay lại còn tạo tài nguyên nền.

## 21. Runbook A — Post-GC live heap tăng và pause kéo dài

**Tình huống:** Cassandra node `-Xmx=16 GiB`, post-GC heap từ 8 lên 14 GiB trong một giờ; pauses từ 100 ms lên vài giây, `ReadStage Pending` tăng.

1. **Scope:** node/rack/DC, JDK/collector, Cassandra version, changes.
2. **Đo:** GC logs before/after heap, pause, allocation rate, p99/error, `tpstats`.
3. **Phân biệt:** allocation churn vs retained/live heap; GC có reclaim được không?
4. **Query:** wide/hot partitions, `SELECT *`, tombstones, report scans, batches.
5. **Resource:** disk await, compaction, CPU throttling, swap, retries.
6. **Mitigation:** throttle batch/backfill, cap fan-out, bảo vệ user SLO.
7. **Diagnostics nâng cao:** class histogram/heap dump chỉ khi duyệt disk/CL/security.
8. **Root cause:** cache/retention, queue, leak, data modeling hoặc version bug.
9. **Thử fix:** bounded query, bucketing, cache/heap options trên staging.
10. **Canary:** theo dõi live heap, p99, errors, node health sau rolling.

**Không chỉ tăng Xmx**, đặc biệt khi cgroup limit không có khoảng trống.

## 22. Runbook B — `OOMKilled` khi Java heap chưa đầy

**Tình huống:** heap used 7 GiB, Xmx 10 GiB; container limit 16 GiB, restart reason `OOMKilled`.

1. Xác minh container OOM events, không dựa duy nhất vào exit 137.
2. Đọc `memory.current/max/stat/events` trên đúng cgroup.
3. So process RSS/PSS, mapped/file cache và JVM heap.
4. Xem direct/native buffer pools, NMT nếu đã bật, threads.
5. So network in-flight, compaction/repair, cache warmup.
6. Giảm concurrency/bytes và background pressure có kiểm soát.
7. Tránh heap dump trên disk/quota nguy cấp.
8. Rebudget heap/off-heap/page cache trong staging.
9. Test sustained load và degraded replica scenario.
10. Canary và báo cáo `oom_kill` delta, memory.current, p99, errors.

**Heap chưa chạm Xmx không phủ định cgroup memory pressure**.

## 23. Runbook C — GC pause tăng cùng CPU throttle hoặc swap

**Tình huống:** GC wall pauses dài nhưng heap sau GC giảm tốt; `cpu.stat nr_throttled` hoặc `vmstat si/so` tăng.

1. So GC log **wall time vs CPU time**, safepoint timeline.
2. Đo CPU quota, per-core usage, `nr_throttled` delta.
3. Đo host steal time, PSI memory/CPU/io và swap-in/out.
4. Xem retry storms, compaction và query workload CPU.
5. Throttle nonessential workloads/admission control.
6. Kiểm việc thay CPU quotas/requests trên staging.
7. Không đổi collector hoặc tăng heap trước khi có evidence.
8. Đo lại pauses, p99, queue và throughput.
9. Không chỉnh kernel sysctl/swap toàn prod thiếu SOP.
10. Lưu regression test dưới CPU cap giống môi trường lỗi.

**GC chậm không luôn nghĩa heap leak**; scheduler/OS pressure có thể là nguyên nhân.

## 24. Runbook D — Direct memory OOM và connection buffers

**Tình huống:** `Direct buffer memory`, Java heap vẫn thấp, native transport in-flight tăng.

1. Xác định PID gây OOM: Cassandra node hay Java app.
2. Xác minh JDK/direct cap và buffer pool metrics.
3. So RSS/PSS, cgroup memory, NMT nếu có.
4. Nhóm queries trả large rows/pages và số bytes/response.
5. Kiểm concurrency, retries, connection churn/TLS.
6. Giảm rate, page/response sizes và outstanding requests.
7. Kiểm known driver/server leaks theo release nếu có bằng chứng.
8. Chỉ tăng direct budget khi memory headroom thực sự đủ.
9. Canary xem OOM events, native memory, p99/error.
10. Thêm guardrail bytes/s và memory pressure alerts.

**Tăng MaxDirectMemorySize vô điều kiện có thể chuyển lỗi sang kernel OOMKilled**.

## 25. Runbook E — Compaction/flush chậm gây GC và timeout dây chuyền

**Tình huống:** Cluster đang backfill, `compactionstats` pending lớn, disk await tăng, memtable flush chậm, heap live occupancy và write p99 cùng tăng.

1. **Xác định thời điểm:** backfill/repair/compaction bắt đầu khi nào, schema/cell sizes có thay đổi?
2. **Đo chi phí lưu trữ:** disk free, IOPS, await, SSTable count, compaction bytes và pending tasks.
3. **Kiểm read/write mix:** incoming writes, commitlog sync, memtable occupancy, replication factor.
4. **Phân biệt server vs client:** Cassandra heap/GC khác Java client buffers; cả hai có thể chịu ảnh hưởng.
5. **Giảm tải có kiểm soát:** dừng/giảm backfill theo checkpoint, rate limit writes hoặc bulk scans không thiết yếu.
6. **Không chạy major compaction/repair bổ sung** chỉ vì đang thấy backlog; việc này có thể tăng I/O.
7. **Kiểm query shape:** hot partitions, tombstone density, large batches, TTL expirations.
8. **Kiểm capacity và recovery:** flush/compaction queues có drain khi giảm offered load không?
9. **Thử giải pháp staging:** bucket/retention/compaction strategy hoặc disk capacity, có baseline rõ.
10. **Canary:** p99 read/write, GC pauses, disk await và pending tasks phục hồi về vùng ổn định.

**Không tăng Xmx làm phương án đầu tiên** khi bottleneck là disk throughput và request references giữ lâu vì hàng đợi.

## 26. Runbook F — Không tạo được native thread hoặc cạn file descriptor

**Tình huống:** Node có lỗi `unable to create native thread` hoặc `Too many open files`, nhưng heap used không quá cao.

1. **Phân loại đúng thông báo:** native thread allocation, FD limit, socket exhaustion hay JVM heap OOM.
2. **Đo threads:** JVM ThreadMXBean, `/proc/PID/status Threads`, `pids.current/max`.
3. **Đo file descriptors:** `/proc/PID/limits` và FD count trend, không dump mọi path vào ticket.
4. **So cấu hình:** pool/thread stack size, systemd TasksMax, `ulimit -n/-u`, container PID policy.
5. **Đánh giá workload:** application có tạo session/connection mỗi request không? Cassandra có SSTable/file churn không?
6. **Điều tra leak:** thread count/FD tăng ngay cả khi offered load ổn định hoặc đã hạ tải?
7. **Mitigation:** giảm connection churn, cap concurrency, tạm dừng job không thiết yếu; tránh kill các process ngẫu nhiên.
8. **Tuning có kiểm soát:** điều chỉnh OS/container limits chỉ khi hiểu resource budget và FD/threads thực.
9. **Xác minh:** thread/FD counts ổn, memory native giảm, connection errors và p99 phục hồi.
10. **Regression:** test sustained load, rolling restart, reconnect storms và high SSTable count.

Một lỗi FD/PID có thể gây timeout/connection failure mà **không có Full GC**. Đừng thay collector nếu nguyên nhân là OS resource limit.

## 27. Ma trận kiểm thử và diễn tập an toàn

| ID | Tình huống | Bằng chứng quan trọng | Điều kiện chấp nhận |
|---|---|---|---|
| T01 | Young allocation churn | GC count, allocation/s, heap after GC | Không vượt pause/error SLO |
| T02 | Live heap tăng theo thời gian | Post-GC heap trend, histogram | Không tăng không giới hạn |
| T03 | Heap-space OOM trên lab | JVM error/GC log | Phân loại đúng loại OOM |
| T04 | Direct-buffer OOM trên lab | BufferPoolMXBean, native/RSS | Không kết luận từ heap alone |
| T05 | Container OOMKilled | memory.events, runtime reason | Phát hiện dù heap còn headroom |
| T06 | Cgroup CPU throttling | cpu.stat, GC wall vs CPU | Nhận diện không nhầm heap leak |
| T07 | Swap pressure trong lab | vmstat si/so, PSI, p99 | Có guardrail và triage |
| T08 | File-backed page cache lớn | memory.stat, RSS/PSS | Không cộng đếm hai lần |
| T09 | Native thread exhaustion | pids.max, Threads | Không chữa bằng tăng Xmx |
| T10 | File descriptor exhaustion | /proc/PID/limits, count | Nhận diện đúng resource |
| T11 | Wide partition read | rows/partition, read p99 | CQL/response bounded |
| T12 | Tombstone-heavy query | Tombstones/read, SSTables | Điều tra read amplification |
| T13 | Large `SELECT *` trong Java client | App heap/response bytes | Tránh collect-all OOM |
| T14 | Async fan-out không giới hạn | In-flight, buffers, errors | Admission control hoạt động |
| T15 | Reactive collectList lớn | App heap/GC | Bounded memory path |
| T16 | Retry storm khi node chậm | Attempts/logical op | Retry budget bảo vệ backend |
| T17 | Compaction backlog | Disk await, pending, p99 | Không overload I/O |
| T18 | Backfill cạnh tranh read traffic | QPS, compaction, GC | Pause/throttle khi vượt guardrail |
| T19 | RF=3 mất một replica | Replica headroom, CL, error | Phục vụ theo SLO thiết kế |
| T20 | Node restart và cold cache | Page cache, disk I/O, p99 | Warm-up/recovery có giới hạn |
| T21 | Container limit thay đổi | memory.max/current/events | Không phát sinh OOM kill |
| T22 | JDK/GC collector thay đổi | GC logs, flags, p99 | Compatible release + canary |
| T23 | NMT summary so native pressure | NMT vs RSS/cgroup | Không suy NMT bao toàn bộ native |
| T24 | Heap dump khi gần hết disk (negative) | SOP/guardrail | Không cho phép thao tác nguy hiểm |
| T25 | Ngưỡng dừng load test | OOM/GC/disk/queue alerts | Test dừng có kiểm soát |

### 27.1. Phân nhóm test theo môi trường

- **Unit tests:** tính toán limit/timeout, pagination, retry budget và admission control.
- **Integration đơn node:** basic CQL, bounded paging, GC/memory metrics và query data volume.
- **Load tests cô lập:** wide/hot partitions, compaction backlog, disk pressure, CPU/memory quota, OOM fault injection.
- **Cluster RF/CL lab:** một replica down, rolling upgrades, hints/repair/streaming và read/write correctness.

**Không chạy OOM fault, CPU throttling experiment, heap dump hoặc compaction stress trên production**. Một test single-node RF=1 không chứng minh hành vi quorum RF=3.

### 27.2. Tiêu chí dừng

~~~text
[ ] Error/timeout rate vượt budget đã duyệt.
[ ] Cgroup oom_kill tăng hoặc memory.current sát hard limit.
[ ] GC pause/time ratio vượt alert threshold liên tục.
[ ] Disk free dưới mức tối thiểu cho compaction/snapshots.
[ ] Pending messages/compaction tăng mà không có drain.
[ ] Load generator chính nó CPU/GC/OOM.
[ ] Node down ngoài phạm vi fault plan.
[ ] Quorum/CL hoặc data correctness có nguy cơ không đạt.
~~~

**Dừng vì guardrail là kết quả đo có giá trị**; không che giấu và không tiếp tục nâng tải để đạt “peak QPS”.

## 28. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “JVM -Xmx 12 GiB nghĩa process chỉ dùng 12 GiB.” | Metaspace/native/direct/threads/mmap ở ngoài heap |
| “Heap chưa đầy thì không thể OOMKilled.” | Cgroup account nhiều loại memory ngoài heap |
| “RSS bằng heap used.” | RSS có native/heap/file-backed resident pages |
| “VSZ 100 GiB nghĩa RAM 100 GiB.” | Virtual address reservation không bằng resident RAM |
| “Cứ cộng RSS với file cache để tính total.” | Có thể đếm đôi shared/mapped pages |
| “NMT tổng kết mọi native allocations.” | Coverage giới hạn; page cache không thuộc NMT |
| “Direct buffer OOM chữa bằng tăng Xmx.” | Cần kiểm native cap/usage và in-flight |
| “OOMKilled luôn là Java OutOfMemoryError.” | Kernel/cgroup kill là lớp khác |
| “Exit 137 chắc chắn memory OOM.” | Có thể là SIGKILL từ nguồn khác |
| “Full GC nhiều nghĩa luôn có memory leak.” | Có thể allocation, workload, CPU throttle, capacity |
| “GC pause dài thì tăng heap là đủ.” | CPU/disk/swap/queue có thể là nguyên nhân |
| “Heap 90% trước GC chắc chắn lỗi.” | Cần xem after-GC occupancy và collector |
| “CPU host rảnh nên pod không bị throttled.” | Cgroup quota có thể hạn chế pod riêng |
| “SwapUsed > 0 luôn là nguyên nhân p99.” | Cần swap activity/PSI/time-series |
| “Cassandra memtable size = Java heap.” | On/off-heap phụ thuộc version/config |
| “Cache lớn luôn phải tắt.” | Tắt cache có thể tăng disk IO/p99 |
| “Compaction pending lớn thì chạy major compaction.” | Có thể làm tranh I/O và disk nặng hơn |
| “LIMIT 20 nghĩa scan 20 storage cells.” | Tombstone/merge work có thể lớn hơn |
| “Page size 100 giới hạn cả SELECT 100 rows.” | Chỉ điều tiết từng page |
| “Async/Flux tự đảm bảo bounded memory.” | In-flight/buffers/collectList vẫn có thể OOM |
| “Node UN nghĩa hết sự cố.” | Phải kiểm heap/GC/p99/CL/replica work |
| “netstats trống nghĩa Cassandra không có traffic.” | Chủ yếu SSTable streaming |
| “jcmd heap_dump read-only nên vô hại.” | Có thể gây pause, disk full và lộ dữ liệu |
| “Lệnh /proc nào cũng miễn phí để poll liên tục.” | smaps/lsof/class histogram có thể tốn tài nguyên |
| “Thay collector của một release áp dụng cho mọi release.” | Cần compatibility matrix Cassandra/JDK |
| “Nâng OS ulimit vô hạn sửa FD leak.” | Chỉ che lỗi cho đến khi limit tiếp theo chạm |
| “GC p99 = API p99.” | Hai phân bố/scope khác nhau |
| “Đủ quorum thì memory headroom cũng đủ.” | Failover có thể tăng tải replica còn lại |

## 29. Bài tập và đáp án

### Câu 1 — Heap và RSS

Node có `-Xmx=12 GiB` và RSS 15 GiB. Có chứng minh memory leak không?

**Đáp án:** Không. RSS có heap, native, mapped/file-backed pages và shared memory. Cần đo trend, post-GC heap, buffer pools, NMT/cgroup và workload.

### Câu 2 — OOMKilled

Heap used 7 GiB, Xmx 10 GiB, pod limit 16 GiB nhưng `memory.events oom_kill` tăng. Có thể xảy ra không?

**Đáp án:** Có. Cgroup account native/file cache/kernel memory, không chỉ Java heap.

### Câu 3 — Exit 137

Một container exit code 137. Đã đủ khẳng định OOM-kill chưa?

**Đáp án:** Chưa. SIGKILL có thể đến từ nguồn khác; xem runtime reason, cgroup events và kernel logs theo quyền.

### Câu 4 — VSZ

`ps` báo VSZ 100 GiB, RSS 12 GiB. Có phải server đã dùng 100 GiB RAM?

**Đáp án:** Không. VSZ là virtual address space. RSS/PSS và cgroup accounting phản ánh các khía cạnh resident/memory pressure.

### Câu 5 — Đếm đôi page cache

Có nên cộng RSS 12 GiB với `memory.stat file 4 GiB` rồi khẳng định process dùng đúng 16 GiB không?

**Đáp án:** Không. Một số file-backed pages có thể nằm trong cả hai phép đo; dùng scope cgroup, PSS và breakdown với hiểu biết accounting.

### Câu 6 — GC churn

Heap trước GC rất cao nhưng sau GC giảm xuống 40%, pause nhỏ. Có chắc live set leak không?

**Đáp án:** Không. Có thể allocation churn/short-lived objects. Cần theo trend và GC/time impact.

### Câu 7 — Live heap

Post-GC heap tăng qua nhiều giờ cùng workload, full/mixed GC không reclaim được nhiều. Bước tiếp theo?

**Đáp án:** Kiểm retained references/caches/in-flight, query size, version bug và class histogram/dump có phê duyệt; không kết luận chỉ từ một điểm đo.

### Câu 8 — CPU throttling

GC wall pause dài nhưng CPU time thấp, cgroup `nr_throttled` tăng. Giả thuyết?

**Đáp án:** JVM không được cấp đủ CPU theo quota hoặc chịu scheduling contention; đo CPU quota/per-core và workload.

### Câu 9 — Direct buffer OOM

Java báo `Direct buffer memory` nhưng heap còn nhiều. Có nên chỉ tăng Xmx?

**Đáp án:** Không. Kiểm direct native buffers, cap, RSS/cgroup, in-flight và memory headroom.

### Câu 10 — NMT

NMT summary = 8 GiB, RSS = 12 GiB. Có phải 4 GiB chắc chắn bị leak?

**Đáp án:** Không. NMT không bao mọi native/file-backed allocations, có cách accounting khác RSS.

### Câu 11 — Memtable

`nodetool tablestats` báo memtable live data cao. Có nghĩa chính xác bấy nhiêu Java heap đang dùng?

**Đáp án:** Không. Memtable implementation/config có thể dùng heap/off-heap; xem release và metrics JVM/native.

### Câu 12 — Tombstones

Một SELECT có LIMIT 20 nhưng phải scan nhiều tombstone. Vì sao p99 vẫn cao?

**Đáp án:** LIMIT giới hạn result rows, không giới hạn tombstone/SSTable scan và merge work.

### Câu 13 — Paging

Driver page size 100, query trả 100.000 rows. Có đảm bảo chỉ tải tối đa 100 rows tổng cộng không?

**Đáp án:** Không. Page size điều tiết từng page; cần CQL LIMIT hoặc dừng consumption có chủ đích.

### Câu 14 — App heap OOM

Spring service OOM khi dùng `collectList()`, Cassandra node heap khỏe. Sửa ở đâu trước?

**Đáp án:** Ở client pipeline: bounded streaming/paging/rows/bytes/concurrency. Không mặc định tăng heap Cassandra.

### Câu 15 — Disk pressure

GC pauses tăng cùng compaction pending và disk await. Có chứng minh GC collector sai cấu hình không?

**Đáp án:** Không. Disk stall/queue có thể giữ objects lâu làm GC tăng; xác minh root bottleneck.

### Câu 16 — Heap dump

Node còn 3 GiB disk trống, heap 12 GiB; có nên lập tức tạo heap dump trên cùng volume?

**Đáp án:** Không. Dump có thể đầy disk/pause, chứa secrets. Cần approval, chỗ lưu an toàn và quorum impact.

### Câu 17 — Thread creation

JVM báo `unable to create native thread`, heap mới dùng 50%. Điều tra?

**Đáp án:** Thread count/stacks, `pids.max`, `TasksMax`, `ulimit -u`, native memory và leak.

### Câu 18 — FD count

`Too many open files` tăng sau connection churn. Đổi GC collector có giải quyết trực tiếp không?

**Đáp án:** Không. Điều tra FD limits, socket/file lifecycle và leak; GC không thay per-process open-files quota.

### Câu 19 — RF/CL

RF=3, LOCAL_QUORUM, một node down. Hai replica còn lại khỏe về logical availability; có thể p99/GC vẫn tăng không?

**Đáp án:** Có. Tải dồn lên replica còn lại, retries/hints/recovery làm resource pressure tăng.

### Câu 20 — `netstats`

`nodetool netstats` trống. Có nghĩa không có native CQL network traffic?

**Đáp án:** Không. Netstats chủ yếu SSTable streaming; dùng native transport/OS network metrics.

### Câu 21 — Retry amplification

1.000 logical reads/s, 20% retry một lần. Attempts tối thiểu là bao nhiêu?

**Đáp án:** Xấp xỉ 1.200 attempts/s nếu các điều kiện minh họa đúng; thêm gateway retry/speculative execution có thể cao hơn.

### Câu 22 — Cgroup CPU

Host CPU usage thấp, Cassandra pod bị throttled thường xuyên. Có mâu thuẫn không?

**Đáp án:** Không. Host có thể dư tài nguyên nhưng pod bị giới hạn `cpu.max`/quota riêng.

### Câu 23 — Recovery

Node sau restart báo `UN` và heap giảm. Đủ kết luận phục hồi?

**Đáp án:** Chưa. Kiểm API p99/errors, memtable/compaction, hints/streaming, cgroup memory, GC và RF/CL.

### Câu 24 — Capacity

Container 16 GiB, Xmx 15 GiB, hoạt động cache/direct buffers nhiều. Có hợp lý chỉ vì heap còn trống 1 GiB?

**Đáp án:** Không. Cần ngân sách cho native/page cache/kernel/threads, peak và failover; một GiB ngoài heap có thể không đủ.

### Câu 25 — Measurement

Một GC pause 1 giây trên node B có bằng p99 API 1 giây không?

**Đáp án:** Không. Hai phạm vi đo và phân bố khác nhau, query có thể chọn coordinator/replica khác, còn queue/network/retry ảnh hưởng API.

## 30. Checklist vận hành: trước, trong và sau sự cố

### 30.1. Trước khi xảy ra sự cố

~~~text
[ ] Cassandra/JDK/driver versions và collector được inventory.
[ ] JVM -Xms/-Xmx và cgroup memory/cpu limits được đo thực tế.
[ ] GC logs có rotation, timestamp UTC, storage quota và retention.
[ ] Thu metrics heap used/committed, post-GC live set, GC pauses.
[ ] Thu RSS/PSS, native/direct buffers, memory.current/events.
[ ] Thu cpu.stat throttle, memory/CPU/io PSI khi kernel hỗ trợ.
[ ] Thu disk free/IOPS/await, swap activity và FD/thread counts.
[ ] Thu nodetool/JMX metrics tpstats, compactionstats, tablestats.
[ ] Query templates, partition distribution, TTL/tombstone mix rõ.
[ ] Có admission control, bounded paging/concurrency và retry budget.
[ ] Có guardrails cho repair/backfill/streaming và capacity headroom.
[ ] Có runbook rolling, RF/CL availability và recovery plan.
[ ] Heap dump/stack artifacts có quyền và storage bảo mật nếu cần.
[ ] Không phụ thuộc một giá trị p99 hoặc heap % duy nhất.
~~~

### 30.2. Trong lúc triage

~~~text
[ ] Xác định đúng node, PID, container, DC/rack và timezone UTC.
[ ] Tách Java app OOM, Cassandra server JVM OOM và kernel OOMKilled.
[ ] Thu snapshot GC logs, post-GC heap, allocation/pause trend.
[ ] Thu memory.current/max/stat/events và runtime OOM status.
[ ] Đo cgroup cpu throttling và host swap/PSI cùng thời điểm.
[ ] Kiểm disk await/free, memtable flush, compaction/repair queues.
[ ] Kiểm query shape: partition key, LIMIT, page size, tombstones.
[ ] Kiểm driver outstanding, retries, connection churn, bytes.
[ ] Kiểm threads/PID cap, FD count/limits nếu lỗi phù hợp.
[ ] Không chạy heap dump/class histogram liên tục thiếu approval.
[ ] Không restart đồng loạt gây mất quorum.
[ ] Không tự major compact/repair trong tình huống disk chật.
[ ] Không tăng heap/direct cap khi chưa tính cgroup headroom.
[ ] Ghi được evidence, hypothesis và mitigation đã áp dụng.
~~~

### 30.3. Sau khi điều chỉnh/khôi phục

~~~text
[ ] Post-GC heap ổn định trong các windows workload đại diện.
[ ] GC pauses/overhead và p95/p99 CQL/API đạt SLO.
[ ] memory.events oom_kill không tăng, native/RSS không drift.
[ ] Cgroup CPU throttling, swap-in/out, PSI về mức chấp nhận.
[ ] Disk IOPS/await/free và compaction backlog không tăng vô hạn.
[ ] Stage pending/dropped, driver timeouts/retries về baseline.
[ ] Node status, internode communication, hints/repair an toàn.
[ ] RF/CL, read/write correctness và business invariants đạt.
[ ] Test trên partition lớn, TTL/tombstone và fault headroom.
[ ] Quan sát một khoảng sustained thay vì vài giây sau restart.
[ ] RCA ghi rõ nguyên nhân gốc, bằng chứng loại trừ, rollback.
[ ] Alert/memory budget/query guardrail được cập nhật.
[ ] Mọi changes được ghi vào quy trình vận hành có owner.
[ ] Content QA STEP 6 vẫn là giai đoạn riêng, chưa thực hiện ở đây.
~~~

## 31. Quy tắc báo cáo và phân định trách nhiệm

Một báo cáo sự cố hữu ích không nên chỉ viết “Cassandra bị OOM”. Cần diễn đạt theo mẫu:

~~~yaml
# Ví dụ cấu trúc báo cáo, không phải kết quả sự cố có thật.
incident_id: cassandra-mem-001
environment: isolated-staging
timestamp_utc: "2026-11-21T10:00:00Z"
scope:
  datacenter: dc1
  affected_nodes: 1
  affected_apps: ["telemetry-api"]
symptom:
  category: "cgroup_oom_kill"
  customer_impact: "CQL timeouts and API 5xx"
observations:
  jvm_heap_after_gc: "stable"
  process_rss: "high"
  cgroup_memory_events: "oom_kill increased"
  disk_compaction: "normal"
hypothesis:
  category: "native-plus-file-cache-headroom"
mitigation:
  action: "bounded client concurrency / rollback oversized workload"
validation:
  success_rate: "within agreed SLO"
  p99: "within agreed SLO"
  memory_events: "no new oom_kill over observation window"
limitations:
  - "No heap dump taken; native allocation attribution incomplete"
~~~

Đây chỉ là **mẫu báo cáo**, không tuyên bố metric nào đã được quan sát trong một cluster thật. Nên có owner, thay đổi đã áp dụng, phạm vi quyền, thời gian bắt đầu/kết thúc, link đến đồ thị đã được lưu có kiểm soát và tình trạng bằng chứng chưa đủ.

### 31.1. Những câu kết luận phải đi kèm điều kiện

- “OOMKilled” → cần runtime/cgroup/kernel evidence, không chỉ exit 137.
- “Heap leak” → cần retention trend, không chỉ một lần `heap used=90%`.
- “GC gây timeout” → cần timeline, không bỏ qua disk/CPU/network/queue.
- “Tăng Xmx đã sửa” → phải đo cgroup/native headroom và fault scenario.
- “Cluster hồi phục” → cần API SLO, retries, replica RF/CL, repair/compaction, không chỉ `UN`.
- “Cache ăn RAM vô ích” → cần biết cache role/hit-rate và read IO trade-off.

## 32. Tổng kết

Để xử lý **Heap/GC kéo dài, bộ nhớ ngoài heap và tài nguyên hệ điều hành** trong Cassandra một cách có hệ thống:

1. **Tách JVM heap, off-heap/native, RSS/PSS, mmap, page cache và cgroup accounting.** Đây là các góc nhìn khác nhau, không cộng số liệu mù quáng.
2. **GC pause phải đọc cùng post-GC live heap, allocation rate và CPU throttling.** Pause dài chưa chứng minh memory leak hoặc collector sai.
3. **Java OOM và kernel OOMKilled là các sự kiện khác nhau.** Dùng JVM logs, container status và `memory.events` để phân loại.
4. **Memtables, caches, compression metadata và native transport có thể dùng cả heap/off-heap** tùy release; `-Xmx` không phải toàn bộ memory budget.
5. **CQL data modeling ảnh hưởng trực tiếp tài nguyên**: partition rộng, tombstones, SSTables, `ALLOW FILTERING`, batch lớn và retry amplification có thể tạo pressure.
6. **Page size không thay LIMIT**, async/reactive không tự đảm bảo bounded memory, và client Java OOM không mặc định là lỗi heap Cassandra.
7. **Disk, compaction, repair, streaming và commitlog phải xem cùng GC** vì I/O stall có thể làm request queues/retained objects tăng.
8. **Native memory, thread stacks, file descriptors, PID caps và swap** là những giới hạn OS cần được đo riêng.
9. **`nodetool`, JMX, GC logs, `/proc`, cgroup và công cụ JVM có mức tác động khác nhau**; heap dump/class histogram không phải thao tác mặc định trên production.
10. **Headroom phải tính cho failover, compaction và bursts** chứ không chọn heap/direct cap sát giới hạn pod khi cluster đang idle.
11. **Khôi phục cần bằng chứng theo nhiều lớp**: GC/heap/native ổn, cgroup không OOM, disk/queues không tích lũy, RF/CL và API p99/error đạt yêu cầu.
12. **Runbook và test phải có giới hạn an toàn**: không thử OOM/fault trên production, không restart nhiều replica cùng lúc, không thu heap dumps chứa dữ liệu nhạy cảm nếu chưa được phê duyệt.

Câu hỏi quan trọng nhất không chỉ là **“Tại sao heap/GC Cassandra tăng?”**, mà là: **“Chính xác process/cgroup nào chịu áp lực, vùng bộ nhớ và tài nguyên nào đang cạn, query hoặc tác vụ nền nào giữ/tiêu thụ tài nguyên, và thay đổi nào giúp khôi phục p99 cùng tính đúng RF/CL mà không tạo sự cố mới?”**. Chẩn đoán theo những ranh giới này giúp tránh việc tăng heap mù quáng, bỏ sót OOM-kill ngoài JVM hoặc nhầm disk/CPU bottleneck thành memory leak.



# Memtable, flush queue và pending compaction trong quan sát cluster Apache Cassandra

> **Chương:** Quan sát hệ thống  
> **Trọng tâm:** Đọc đúng vòng đời ghi từ memtable đến SSTable, phát hiện hàng đợi flush bị nghẽn và compaction không theo kịp, phân biệt dấu hiệu với nguyên nhân gốc bằng `nodetool`, JMX/metrics, hệ điều hành và chỉ số ứng dụng Java. Nội dung định hướng Apache Cassandra 4.1/5.0; metric, thread-pool và cấu hình có thể khác theo phiên bản hoặc bản phân phối.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **memtable đang ghi**, **memtable đã switch đang đợi flush**, **flush writer**, **SSTable bất biến**, **compaction task** và **commit log**.
2. Đọc đúng `MemtableOnHeapSize`, `MemtableOffHeapSize`, `AllMemtablesOnHeapSize`, `MemtableSwitchCount`, `PendingFlushes`, `PendingCompactions` và `Compaction.PendingTasks`.
3. Xác định queue nào thực sự nghẽn bằng `nodetool tpstats` và các thread pools `MemtableFlushWriter`, `PerDiskMemtableFlushWriter_*`, `MemtablePostFlush`, `CompactionExecutor`.
4. Tương quan metrics theo **node → table → workload** để phân biệt áp lực RAM, I/O, CPU, flush và compaction.
5. Thiết kế dashboard, cảnh báo theo **xu hướng** thay vì một snapshot có giá trị khác 0; tránh sai lầm khi lấy hiệu giữa hai gauge/counter.
6. Thực hành quan sát trong lab bằng CQL, `nodetool` và ví dụ Java Driver; tạo runbook xử lý backlog mà không làm mất dữ liệu hoặc tự gây “compaction storm”.

Trong kiến trúc Cassandra phân tán, mỗi replica ghi và flush **cục bộ**. Một client có thể ghi thành công theo `LOCAL_QUORUM` dù một replica còn lại đang chịu nhiều flush/compaction. Vì vậy quan sát phải theo **từng node, datacenter, bảng và mức nhất quán đọc/ghi**, không chỉ nhìn giá trị trung bình cả cluster.

## 2. Đường ghi: vì sao có hai loại hàng đợi?

Cassandra sử dụng đường ghi gần với **Log-Structured Merge Tree (LSM-tree)**. Một mutation được lưu trong **commit log** để hỗ trợ khôi phục sau crash và được áp dụng vào **memtable** của bảng. Memtable giữ dữ liệu có thể đọc được và cuối cùng được ghi thành một hoặc nhiều SSTable bất biến.

~~~text
Ứng dụng Java / CQL
       |
       | WRITE với consistency level
       v
    Coordinator ---> các natural replica
                          |
                   +------+------+
                   |             |
                CommitLog      Memtable (đang ghi)
                   |             |
             segment / fsync      | đạt ngưỡng hoặc được yêu cầu
                   |             v
                   |        Memtable switch
                   |             |
                   |        Flush queue / writers
                   |             |
                   |             v
                   |        SSTable mới trên đĩa
                   |             |
                   +--> Post-flush / có thể giải phóng
                         segment commit log đủ điều kiện
                                 |
                               Nhiều SSTable
                                 |
                                 v
                          Compaction backlog
                                 |
                            Compaction workers
                                 |
                         SSTable đầu ra mới
~~~

Phân biệt hai luồng công việc:

| Công việc | Đầu vào | Đầu ra | Khi chậm sẽ thấy |
|---|---|---|---|
| **Flush** | Memtable đã được switch | SSTable được ghi ra đĩa, memtable được giải phóng khi an toàn | Pending flush / flush thread pool tăng, áp lực memtable, có thể chặn cấp phát |
| **Compaction** | Nhiều SSTable hoặc tác vụ bảo trì SSTable | SSTable được hợp nhất/viết lại, file cũ được loại khi đủ điều kiện | Pending compaction, số SSTable, write amplification, đọc nhiều SSTable |

**Flush không phải compaction.** Một flush thường tạo SSTable **mới**, có thể làm compaction sau đó bận hơn. Một compaction xử lý những SSTable **đã có trên đĩa**, không trực tiếp ghi memtable đang hoạt động.

### 2.1. Vì sao write ACK chưa đợi compaction?

Với durable writes thông thường, Cassandra xác nhận mutation dựa trên đường ghi/commit log và số replica ACK cần thiết theo CL; không đợi compaction hoàn tất. Flush và compaction là công việc lưu trữ phía sau. Điều này giúp tốc độ ghi cao nhưng tạo **write amplification** và nhu cầu quan sát backlog.

Tuy nhiên, không nên diễn giải “write ACK không đợi compaction” thành “compaction không ảnh hưởng write”. Nếu cùng đĩa bị I/O saturation, compaction có thể làm flush chậm, memtable chưa giải phóng được bộ nhớ, và đường ghi phải chờ **backpressure** hoặc gặp timeout.

### 2.2. Vì sao dữ liệu vẫn an toàn khi memtable chưa flush?

Khi một node crash trước lúc memtable được ghi thành SSTable, Cassandra có thể **replay commit log** để phục hồi mutation đã ghi bền vững theo cấu hình. Commit log segment không được giải phóng tùy tiện nếu còn chứa dữ liệu của memtable chưa được flush thành công.

Do đó, quan sát memtable cần song hành với `CommitLog.TotalCommitLogSize`, `CommitLog.PendingTasks` và `CommitLog.WaitingOnSegmentAllocation`. Nếu commit log sắp đầy và buộc flush, ta có thể thấy **flush thường xuyên dù memtable không quá lớn**.

## 3. Memtable: không chỉ là một con số RAM

Một table thường có **memtable đang hoạt động**. Trong quá trình switch, memtable cũ chuyển sang trạng thái pending/đang flush trong khi memtable mới tiếp tục nhận ghi. Secondary index, materialized view và các cấu trúc phụ có thể làm tổng bộ nhớ lớn hơn số đo chỉ memtable hoạt động của base table.

~~~text
            Table: orders_by_customer
                      |
              Active memtable M2
                  (đang ghi)
                      |
           bộ nhớ vượt ngưỡng / manual flush
                      |
                Switch M2 -> M3
                      |
           +----------+----------+
           |                     |
      M2 chờ flush          M3 tiếp tục nhận write
           |
      Flush writer
           |
      SSTable mới
           |
    Giải phóng tài nguyên M2 khi an toàn
~~~

### 3.1. Các metric Table liên quan memtable

| Metric JMX (Table scope) | Loại | Cách hiểu đúng |
|---|---|---|
| `MemtableOnHeapSize` | Gauge, bytes | Dữ liệu/cấu trúc memtable trên JVM heap, có overhead |
| `MemtableOffHeapSize` | Gauge, bytes | Phần memtable ngoài heap, nếu cấu hình sử dụng |
| `MemtableLiveDataSize` | Gauge, bytes | Ước lượng kích thước dữ liệu sống, không gồm toàn bộ overhead |
| `AllMemtablesOnHeapSize` | Gauge, bytes | Tổng memtable trên heap, **kể cả memtable đang pending flush và index phụ** theo định nghĩa Cassandra |
| `AllMemtablesOffHeapSize` | Gauge, bytes | Tổng memtable ngoài heap, gồm phần pending và index phù hợp |
| `AllMemtablesLiveDataSize` | Gauge, bytes | Tổng live data của memtables; không coi là số byte RAM thực tế |
| `MemtableColumnsCount` | Gauge, số cột/cell | Số lượng cột trong memtable theo cách engine đếm, không phải số dòng của table |
| `MemtableSwitchCount` | Counter | Số lần switch do flush kể từ khi metric/node được khởi tạo |

Ví dụ cách suy luận:

- `MemtableOnHeapSize` giảm sau flush **có thể là bình thường**, nhưng nếu `AllMemtablesOnHeapSize` vẫn cao thì memtable cũ **có thể chưa được giải phóng** hoặc các memtable khác/index vẫn chiếm RAM.
- `MemtableLiveDataSize` nhỏ hơn `MemtableOnHeapSize` không phải lỗi: bộ nhớ có **overhead, ghi đè và cấu trúc quản lý**.
- `MemtableSwitchCount` tăng đều không có nghĩa queue đang nghẽn; một workload ghi mạnh hoặc một bảng flush chủ động cũng làm counter tăng.
- `MemtableOffHeapSize` thấp/0 không tự chứng minh “memtable không dùng bộ nhớ”: có thể allocation chủ yếu trên heap.

**Bộ nhớ memtable không bằng toàn bộ heap JVM.** Cassandra còn heap cho cache, đối tượng đọc/ghi, compaction metadata, hệ thống và GC. Đọc thêm JVM heap usage, direct/off-heap, GC pause và tình trạng cgroup/container.

### 3.2. Memory limit và thời điểm flush

Các cấu hình thường gặp trong `cassandra.yaml`:

~~~yaml
# Ví dụ tên tham số, KHÔNG phải cấu hình khuyến nghị sao chép trực tiếp.
memtable_heap_space: 2048MiB
memtable_offheap_space: 2048MiB
memtable_allocation_type: heap_buffers

# Tùy chọn cần rà soát kỹ theo phiên bản và môi trường:
# memtable_flush_writers: 2
~~~

**Không chỉnh theo số ví dụ.** Nhiều tham số trong file cấu hình được comment và có mặc định theo phiên bản hoặc số data directories. `memtable_cleanup_threshold` trong các phiên bản hiện đại được đánh dấu **deprecated**; Apache khuyến nghị cách tính mặc định theo số flush writers thay vì tùy ý sửa.

Memtable flush có thể được kích hoạt do:

1. Dung lượng memtable tiến tới ngưỡng quản lý bộ nhớ.
2. Commit log đạt giới hạn và cần làm sạch segment; có thể ép flush các bảng có dirty data trong segment.
3. Lệnh chủ động như `nodetool flush` (dành cho vận hành/lab).
4. Các thao tác lifecycle/bảo trì cần flush phù hợp với cơ chế của Cassandra.

**Đừng suy memtable tự flush khi đạt một kích thước “đúng 2 GiB cho từng bảng”**. Những cấu hình memtable là bộ nhớ quản lý ở phạm vi node/pool, cách chọn bảng flush còn phụ thuộc nhiều yếu tố.

## 4. Flush queue: các metric cần phân biệt

**Flush queue** ở đây là tập các memtable đã switch hoặc các task liên quan đang chờ hoàn thành flush/post-flush; không phải một hàng đợi duy nhất với tên metric chung cố định cho mọi bản Cassandra.

### 4.1. PendingFlushes là số ước lượng, không phải tổng lần flush

Trong tài liệu metric Apache:

| Metric | Loại trong tài liệu | Ý nghĩa |
|---|---|---|
| `Table.PendingFlushes` | **Counter** (tên/ý nghĩa là pending, ước lượng) | Số tác vụ flush đang pending cho table tại thời điểm quan sát |
| `Table.BytesFlushed` | Counter | Tổng byte đã flush từ lúc node start/restart |
| `Table.MemtableSwitchCount` | Counter | Số lần memtable switch |
| `ThreadPools.PendingTasks` của flush pool | Gauge | Task **đang chờ** xử lý trong pool tương ứng |
| `ThreadPools.ActiveTasks` của flush pool | Gauge | Task **đang chạy** |
| `ThreadPools.CompletedTasks` của flush pool | Counter | Tổng task hoàn tất, cần lấy rate để nhìn throughput |
| `MemtablePool.BlockedOnAllocation` | Chỉ số chờ cấp phát; kiểm loại metric qua JMX bản chạy | Bằng chứng đường ghi bị chặn vì chờ memory được giải phóng sau flush |

**Bẫy tên metric:** Apache phân loại `PendingFlushes` là `Counter`, nhưng mô tả là **estimated number of pending flush tasks**. Vì vậy **không mặc định áp dụng hàm rate/increase chỉ vì type ghi Counter** như với một counter hoàn thành thuần túy. Hãy xem giá trị thực tế, hướng tăng/giảm và đối chiếu `tpstats`. Sau khi đã xác minh exporter có mapping đúng kiểu/cơ chế, mới viết PromQL phù hợp.

### 4.2. Các thread pool thường xuất hiện khi flush

Trên Cassandra 4.x/5.0, tên pool từ tài liệu bao gồm:

| Pool (dạng điển hình) | Công việc | Khi `PendingTasks` tăng liên tục |
|---|---|---|
| `MemtableFlushWriter` | Ghi memtable thành SSTable | Flush bị tồn đọng; cần xác định có writer khác theo disk hay không |
| `PerDiskMemtableFlushWriter_0`, `_1`... | Writer tương ứng từng data directory/disk | Có thể phát hiện bottleneck **riêng một disk** |
| `MemtablePostFlush` | Công việc hậu flush, gồm dọn commit log khi đủ điều kiện | SSTable có thể đã tạo nhưng cleanup/giải phóng segment bị chậm |
| `MemtableReclaimMemory` | Giải phóng/tái sử dụng bộ nhớ memtable | Có thể giải thích bộ nhớ không hạ ngay sau flush |
| `CompactionExecutor` | Tác vụ compaction SSTable | Đừng gộp queue compaction với queue flush |

Các pool có thể thay đổi tên/số lượng theo phiên bản, hệ điều hành và cách đặt data directory. `nodetool tpstats` trên **binary thực tế** là đầu vào xác nhận, không áp một tên pool được copy từ bảng sang tất cả cluster.

Ví dụ `tpstats` **minh họa, không phải output thực từ một node**:

~~~text
Pool Name                         Active   Pending   Completed   Blocked
MemtableFlushWriter                  2         7         380       0
MemtablePostFlush                    1         3         377       0
PerDiskMemtableFlushWriter_0         2         5         379       0
CompactionExecutor                   2        18         212       0
~~~

Giá trị “Pending=7” trên pool và “PendingFlushes=7” trên Table **không nhất thiết tương đương**. Một cái có phạm vi **thread pool**, một cái có phạm vi **table**; một flush gồm nhiều pha, vài pool có thể phản ánh các phần liên quan của cùng công việc. **Không cộng thẳng** tất cả PendingTasks để ra “tổng số flush”.

### 4.3. MemtablePool.BlockedOnAllocation là triệu chứng đáng chú ý

Theo mô tả của Apache cho `memtable_flush_writers`, `MemtablePool.BlockedOnAllocation` nên bằng 0 trong điều kiện bình thường; giá trị khác 0 có thể chỉ ra **thread bị chặn khi xin bộ nhớ memtable, phải chờ flush giải phóng memory**.

Nó quan trọng hơn việc chỉ nhìn một thời điểm `PendingFlushes=1`, bởi nó nối trực tiếp backlog với áp lực lên đường ghi. Tuy nhiên, cần kiểm tên metric/kiểu MBean của phiên bản hiện tại trước khi thiết lập alert hoặc xác định đây là số thread tại thời điểm đọc hay thống kê dạng khác.

## 5. Pending compaction: vì sao nhiều SSTable dẫn đến áp lực kéo dài?

Sau các lần flush, có thêm SSTable; UPDATE/DELETE không sửa file cũ mà lưu các phiên bản khác nhau. **Compaction** chọn nhóm SSTable rồi hợp nhất, loại dữ liệu bị che/tombstone theo điều kiện, tạo SSTable đầu ra và thu hồi file cũ khi đủ điều kiện.

~~~text
Flush #1 -> SSTable 001  ┐
Flush #2 -> SSTable 002  ├-> Compaction theo strategy -> SSTable 005
Flush #3 -> SSTable 003  ┤                        \
Flush #4 -> SSTable 004  ┘                         \-> Giảm số SSTable
                                                   nếu đầu ra phù hợp
~~~

Nếu tốc độ SSTable mới sinh ra cao hơn năng lực compaction trong thời gian dài:

- Số SSTable một table tăng; khi đọc partition có thể phải xét nhiều file hơn.
- Disk I/O và read amplification tăng, đặc biệt với workload UPDATE/DELETE và SSTable chồng lấn.
- Không gian đĩa tạm thời cho output compaction có thể tăng.
- Compaction tranh CPU/I/O với flush và CQL, khiến **flush queue cũng tăng theo**.
- Tombstone chỉ có thể được thu hồi khi điều kiện grace/compaction phù hợp; không được cưỡng ép dọn chúng bằng cách bỏ bảo đảm nhất quán.

### 5.1. Metric chính và ý nghĩa

| Metric | Phạm vi | Loại | Diễn giải |
|---|---|---|---|
| `Compaction.PendingTasks` | Node | Gauge | **Ước lượng** số tác vụ compaction còn lại cần thực hiện |
| `Compaction.PendingTasksByTableName` | Node / phân rã theo keyspace-table | Gauge map | Xác định **bảng nào** đóng góp backlog |
| `Table.PendingCompactions` | Table | Gauge | Ước lượng pending compaction của bảng |
| `Compaction.CompletedTasks` | Node | Gauge được tài liệu liệt kê | Giá trị task hoàn thành; xác minh semantics/version trước khi tính rate |
| `Compaction.TotalCompactionsCompleted` | Node | Meter | Tốc độ các compaction đã hoàn thành |
| `Compaction.BytesCompacted` | Node | Counter, bytes | Byte được compaction kể từ khi start/restart |
| `Table.CompactionBytesWritten` | Table | Counter, bytes | Byte do compaction đã ghi |
| `Table.LiveSSTableCount` | Table | Gauge | Số SSTable **đang sống** của bảng |
| `Table.LiveDiskSpaceUsed` | Table | Chỉ số bytes | Dung lượng SSTable đang sống; xét cùng `TotalDiskSpaceUsed` |
| `ThreadPools.CompactionExecutor.PendingTasks` | Pool | Gauge | Tác vụ trong hàng đợi executor; không nhất thiết bằng chiến lược estimate backlog |

`PendingCompactions`/`PendingTasks` là **estimate**, không phải tổng hàng còn phải compact, không phải dung lượng bytes và không thể tự biến thành ETA bằng “pending × thời gian compaction trung bình”. Một công việc lớn có thể giữ pending nhỏ trong khi chiếm tài nguyên nhiều giờ; ngược lại nhiều task nhỏ có thể giảm rất nhanh.

### 5.2. Đọc `nodetool compactionstats`

~~~bash
nodetool compactionstats
nodetool compactionstats -H
~~~

Output **mô phỏng**:

~~~text
pending tasks: 14
- orders.events_by_tenant: 9
- orders.orders_by_id: 5

id            compaction type    keyspace   table             completed  total      unit  progress
...           Compaction         orders     events_by_tenant  24 MiB     96 MiB    bytes 25.00%

Active compaction remaining time: 0h00m36s
~~~

Đọc kết quả:

1. **Pending tasks 14** là estimate node tại thời điểm lệnh, không mặc nhiên là 14 task đang chạy.
2. Dòng progress phản ánh **task đang hoạt động**, không cam kết toàn bộ backlog hoàn thành đúng ETA.
3. Dữ liệu theo table cho biết nên điều tra bảng `events_by_tenant` trước.
4. Kiểm cả lịch sử các snapshot: pending giảm rồi tăng theo burst có thể bình thường; pending tăng **không dừng** cùng SSTable count, disk pressure và latency mới đáng lo.
5. Compaction không chỉ là merge thường: repair validation/anti-compaction, scrub, upgradesstables hoặc các thao tác bảo trì có thể tranh tài nguyên nhưng xuất hiện trong công cụ theo loại khác; hãy xem “compaction type” và logs.

### 5.3. Compaction strategy ảnh hưởng ý nghĩa pending

| Chiến lược | Điều nên nhìn kèm pending | Đặc điểm |
|---|---|---|
| `SizeTieredCompactionStrategy` (STCS) | Số SSTable, nhóm size tier, read amplification | Gộp file theo kích thước; burst flush có thể sinh nhiều SSTable nhỏ |
| `LeveledCompactionStrategy` (LCS) | Phân phối SSTable theo level, số file L0, compaction giữa levels | Backlog tại level thấp có thể ảnh hưởng đọc/ghi |
| `TimeWindowCompactionStrategy` (TWCS) | Cửa sổ thời gian, TTL, SSTable ngoài cửa sổ, out-of-order writes | Hữu ích workload time series; dữ liệu đến trễ có thể làm giảm khả năng thu hồi |
| `UnifiedCompactionStrategy` (UCS, Cassandra 5.0) | Cấu hình strategy, shard/level và nguồn task | Không diễn giải như STCS/LCS; chọn tuning đúng phiên bản |

**Không so sánh số pending giữa hai chiến lược như một thước đo hiệu năng tuyệt đối.** Workload, quy mô SSTable, compaction strategy và cách estimate task quyết định con số này.

## 6. Phân biệt triệu chứng theo chuỗi nhân quả

Mục đích quan sát không phải liệt kê con số, mà xác định **đầu vào đến nhanh hơn công việc nền giải quyết ở đâu**.

~~~text
                         CQL write rate tăng
                                  |
                                  v
                          Memtable lớn nhanh
                                  |
                         Switch/flush dày
                                  |
                 +----------------+----------------+
                 |                                 |
           Flush theo kịp                    Flush đợi I/O
                 |                                 |
          SSTable sinh thêm              PendingFlushes tăng
                 |                       MemtablePool blocked
                 |                                 ^
                 v                                 |
       Compaction cần theo kịp                      |
                 |                                 |
          Pending compaction tăng ----+------> cạnh tranh disk
                 |                    |
                 v                    v
       SSTablesPerRead tăng       Write/read latency tăng
                 |
          Read amplification
~~~

Sơ đồ chỉ là một **chuỗi có thể xảy ra**. Một table có nhiều flush không nhất thiết compaction nghẽn; một node có compaction backlog tăng không nhất thiết ngay lập tức gặp memtable allocation block. Cần **đo quan hệ thời gian**: tín hiệu nào xuất hiện trước, sau, và thay đổi gì khi lưu lượng giảm.

### 6.1. Phân biệt năm trạng thái

| Trạng thái quan sát | Metrics điển hình | Giải thích ban đầu | Cần xác minh thêm |
|---|---|---|---|
| **Write burst ngắn** | Memtable tăng, switch/bytes flushed tăng; pending chỉ nhô lên rồi về nền | Thường bình thường | Hồi phục của queue, p95/p99, disk headroom |
| **Flush writer không theo kịp** | `PendingFlushes` và flush pool pending tăng liên tục; all-memtables memory cao | Memtable chờ được ghi ra disk | Disk latency, writer active, post-flush, `BlockedOnAllocation` |
| **Compaction không theo kịp** | `PendingCompactions` tăng lâu; SSTable count và read latency tăng | Nhiều SSTable chờ merge | Compaction throughput, strategy, CPU/disk, task đang chạy |
| **Commit log I/O chậm** | `CommitLog.PendingTasks`, `WaitingOnCommit` hoặc `WaitingOnSegmentAllocation` tăng | Fsync/segment bị chậm, có thể không bắt nguồn từ memtable | Commit log disk, allocation, sync mode, disk free |
| **Nghẽn request/CPU khác** | `MutationStage.PendingTasks`/`Native-Transport-Requests.PendingTasks` tăng; flush và compaction không quá tải | Request path xử lý chậm, khác flush backlog | CPU, GC, coordinator, network, query patterns |

Một số từ như “tăng liên tục” phải được định nghĩa bằng **cửa sổ quan sát và baseline SLO riêng của cluster**. Không có ngưỡng toàn cầu kiểu “pending > 5 là hỏng” cho tất cả Cassandra.

### 6.2. Khi `AllMemtables...` cao nhưng active memtable nhỏ

Ví dụ một node có hai ảnh chụp:

~~~text
Tại 10:00:
  MemtableOnHeapSize          120 MiB
  AllMemtablesOnHeapSize     650 MiB
  PendingFlushes                  6

Tại 10:05:
  MemtableOnHeapSize           90 MiB
  AllMemtablesOnHeapSize     710 MiB
  PendingFlushes                  9
~~~

Đây là **số mô phỏng** để luyện diễn giải. Memtable đang nhận ghi không quá lớn nhưng tổng memory của memtable có thể bao gồm memtable chờ flush và cấu trúc phụ. Khoảng cách tăng cùng pending flush là một giả thuyết mạnh về flush chậm, **chưa đủ kết luận** nếu chưa nhìn từng thread pool, `BlockedOnAllocation` và I/O.

### 6.3. Khi compaction pending tăng nhưng flush queue thấp

~~~text
T0: PendingFlushes=0, PendingCompactions=8,  LiveSSTableCount=35
T1: PendingFlushes=0, PendingCompactions=19, LiveSSTableCount=53
T2: PendingFlushes=0, PendingCompactions=31, LiveSSTableCount=76
~~~

Đây có thể là compaction backlog tích lũy từ trước, dù flush vẫn hoàn thành. Cần xem dữ liệu theo bảng, compaction output throughput, disk I/O, chiến lược STCS/LCS/TWCS/UCS và tác động tới latency đọc. **Không** mặc định tăng `memtable_flush_writers`: điều đó có thể tạo **nhiều SSTable nhỏ hơn** và tăng khối lượng compaction.

### 6.4. Khi PendingCompactions cao nhưng số SSTable không tăng mạnh

Có thể do:

- Task hiện tại lớn/chạy lâu; số file không phải kích thước work.
- Một số task liên quan maintenance/repair/validation khác với compaction thông thường.
- Strategy estimate backlog khác với số SSTable cần hợp nhất.
- SSTable đang compact lại sinh output khác kích thước/số lượng.
- Chỉ số so sánh đang lấy từ **hai bảng/nodes khác nhau** hoặc một metric exporter đã reset.

Lúc này, `nodetool compactionstats`, loại compaction, progress byte, `Compaction.BytesCompacted` theo thời gian và disk metrics đáng tin hơn một snapshot SSTable count.

## 7. Quan sát bằng nodetool: quy trình ba mức

### Mức 1 — Kiểm cluster/node có khỏe không?

~~~bash
# Đọc trạng thái; chạy trên node cần kiểm hoặc qua JMX được cấp quyền.
nodetool status
nodetool version
nodetool info
~~~

Xác định:

1. Node nào đang DOWN, JOINING, LEAVING hoặc NORMAL?
2. Các node cùng datacenter có dung lượng đĩa, heap/GC, write latency và thread queue lệch nhau không?
3. Có streaming/repair/bootstrapping/backup đang diễn ra, gây I/O nền không?
4. Tình trạng tải xuất hiện **trên mọi replica của một partition hay chỉ một node**?

**Một node UN** chỉ có nghĩa đang UP/NORMAL theo gossip tại thời điểm xem, không chứng minh flush/compaction backlog bằng 0.

### Mức 2 — Xem table và hai hàng đợi

~~~bash
nodetool tablestats
nodetool tablestats -H
nodetool tablestats observability_lab.events_by_tenant

nodetool tpstats
nodetool compactionstats
nodetool compactionstats -H
~~~

Các phiên bản hỗ trợ `tablestats` có khác biệt về field/human-readable và có thể có `-F json` hoặc `-F yaml`. Xem `nodetool help tablestats` trên binary thực khi viết script phân tích.

Đọc `tablestats` theo thứ tự:

1. **Memtable data size**, số lần switch, pending flush nếu có trên output.
2. **SSTable count**, dung lượng live/total disk, compaction counter.
3. **Write/Read latency**, SSTables per read, tombstone metrics để đánh giá tác động.
4. Ưu tiên **bảng nóng** hoặc bảng có sự khác biệt lớn giữa node, không đọc hàng trăm bảng mà bỏ ngữ cảnh workload.

Đọc `tpstats` theo thứ tự:

1. `MemtableFlushWriter` và `PerDiskMemtableFlushWriter_*`: active, pending.
2. `MemtablePostFlush` và `MemtableReclaimMemory`.
3. `CompactionExecutor`.
4. `MutationStage`, `Native-Transport-Requests`, `ReadStage`, dropped messages (nếu output hỗ trợ) để tìm áp lực lên request path.

Đọc `compactionstats` theo thứ tự:

1. Pending tasks của **node**.
2. Bảng nào đóng góp bao nhiêu.
3. Task đang active, loại task, byte hoàn thành/tổng, tốc độ tiến triển giữa hai lần đo.
4. ETA chỉ là ước lượng; không đưa ETA của một task làm cam kết hoàn tất toàn backlog.

### Mức 3 — Liên hệ nguyên nhân bên ngoài Cassandra

~~~bash
# Các lệnh hệ điều hành chỉ minh họa cho Linux lab/server.
# Tùy quyền và công cụ cài sẵn, không mặc định có trên mọi máy.
iostat -xz 1 5
vmstat 1 5
df -h
~~~

Kiểm:

- Disk `await`/latency, throughput, utilization và sự chênh lệch **từng thiết bị**.
- Commit log và data directories có chia sẻ đĩa/volume đang bão hòa không.
- CPU user/system, iowait, run queue, container CPU throttling.
- Heap GC pause và direct/off-heap memory.
- Disk free và tốc độ tăng dung lượng, kể cả **snapshot** giữ file SSTable cũ.
- Network/streaming nếu đang repair/bootstrap.

**Chú ý:** `%util` cao trên SSD/NVMe không tự chứng minh saturation ở mọi hệ thống; phải kết hợp latency, hàng đợi I/O và throughput thực tế.

## 8. JMX và metric exporter: tên, scope và kiểu dữ liệu

Cassandra dùng Dropwizard Metrics; metrics thường truy cập được qua **JMX**, virtual tables/metric reporter hoặc hệ thống giám sát. Dữ liệu thô là **theo từng node**: Prometheus/Grafana hay hệ thống khác phải tổng hợp theo mục đích, không mặc định giá trị Cassandra đã là tổng cluster.

### 8.1. Tên Table metrics qua JMX

Với bảng `observability_lab.events_by_tenant`, các MBean ví dụ:

~~~text
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=MemtableOnHeapSize
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=AllMemtablesOnHeapSize
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=PendingFlushes
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=BytesFlushed
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=PendingCompactions
org.apache.cassandra.metrics:type=Table,keyspace=observability_lab,scope=events_by_tenant,name=LiveSSTableCount
~~~

Cùng một metric có thể xuất hiện dưới dạng tên reporter:

~~~text
org.apache.cassandra.metrics.Table.MemtableOnHeapSize.observability_lab.events_by_tenant
org.apache.cassandra.metrics.Table.PendingCompactions.observability_lab.events_by_tenant
~~~

Thứ tự thuộc tính trong tên JMX ObjectName có thể thay đổi cách hiển thị mà không đổi ý nghĩa. Dùng client JMX để tìm domain/type/keyspace/scope/name thay vì xây parser phụ thuộc đúng một string đã sắp thứ tự.

### 8.2. Tên ThreadPool và Compaction MBean

~~~text
org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=MemtableFlushWriter,name=PendingTasks
org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=MemtablePostFlush,name=PendingTasks
org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=CompactionExecutor,name=PendingTasks
org.apache.cassandra.metrics:type=Compaction,name=PendingTasks
org.apache.cassandra.metrics:type=Compaction,name=BytesCompacted
org.apache.cassandra.metrics:type=CommitLog,name=WaitingOnSegmentAllocation
~~~

**Không đồng nhất** `Table.PendingCompactions`, `Compaction.PendingTasks` và `ThreadPools.CompactionExecutor.PendingTasks`:

- Một metric ước lượng compaction **theo bảng**.
- Một metric ước lượng **toàn node**.
- Một metric là queue **của executor** và có thể khác theo phiên bản/cách lập lịch.

Nếu dashboard chỉ có một trong ba, khó xác định **bảng gây backlog** hay task đã được lập lịch vào executor hay chưa.

### 8.3. Export sang Prometheus đúng kiểu

JMX exporter/agent có thể đổi dấu chấm, chữ hoa và tên label. Vì vậy **không giả định** có sẵn metric Prometheus tên `cassandra_table_pending_compactions` trong mọi tổ chức.

Một cách thiết kế dashboard **mang tính khái niệm**:

~~~text
Raw JMX:
  Table.PendingCompactions (gauge, per table)
  ThreadPools.PendingTasks (gauge, per pool)
  Table.BytesFlushed (counter)
  Compaction.BytesCompacted (counter)

Exporter:
  <metric_name do chính config xác định>
  labels: cluster, dc, node, keyspace, table, type/pool

Grafana:
  panel 1: pending flush theo node + table
  panel 2: flush pool active/pending và blocked allocation
  panel 3: pending compaction theo node + table
  panel 4: bytes flushed/compacted theo tốc độ
  panel 5: SSTable count, disk latency, p99 read/write
~~~

Mỗi biểu đồ phải ghi **đơn vị**, **kiểu metric**, **thời điểm** và **nhóm label**. Với metric counter tăng tích lũy như `BytesFlushed`, lấy tốc độ (bytes/second) qua nhiều điểm đo; với gauge như `PendingCompactions`, giữ giá trị tức thời/smoothing, không “rate” tùy tiện. Riêng `PendingFlushes` phải xác nhận semantics sau exporter vì tài liệu gắn type Counter trong khi ý nghĩa mô tả là trạng thái pending.

### 8.4. Những lỗi dashboard thường gặp

| Lỗi | Vì sao sai? | Sửa thế nào? |
|---|---|---|
| Cộng mọi `AllMemtablesOnHeapSize` và `MemtableOnHeapSize` | Có thể double count phần active | Chọn metric đúng phạm vi, không cộng hai biến chứa chồng lấn |
| Dùng `rate(PendingCompactions)` như throughput | Pending là gauge **ước lượng công việc**, không phải counter hoàn thành | Dùng snapshot/trend pending và `TotalCompactionsCompleted`, `BytesCompacted` |
| Chỉ xem trung bình cluster | Một node bị disk full có thể bị che bởi các node khỏe | Dùng max/p95 theo node, drill-down theo table |
| Chỉ xem số SSTable | TWCS và các strategy khác có số SSTable hợp lý khác nhau | Kết hợp strategy, SSTables-per-read, pending, latency |
| Gán “0 pending” đồng nghĩa storage khỏe | Queue có thể 0 vì traffic thấp, compaction bị disable, node không nhận task hoặc metric thiếu | Kiểm query SLO, disk/GC, compaction enabled, metric scraping |
| Đo một lần rồi cảnh báo | Flush/compaction theo burst tự nhiên | Theo dõi cửa sổ và thời gian hồi phục |
| Trộn bytes MiB với MB hoặc microseconds với milliseconds | So sánh sai ngưỡng/SLA | Chuẩn hóa đơn vị trong dashboard và exporter |
| Không phân biệt node restart | Counter có thể reset; series mới không cùng baseline | Dùng rate counter phù hợp, ghi uptime/restart event |

## 9. Thiết kế alert: queue dài có phải lúc nào cũng nguy hiểm?

**Không có một ngưỡng pending chung cho mọi Cassandra cluster.** Cần xây baseline riêng theo write rate, compaction strategy, disk, số data directory, RF, partition size, TTL và độ lớn dataset.

### 9.1. Cấu trúc cảnh báo nhiều tín hiệu

Một ví dụ **policy minh họa**, ngưỡng thực phải lấy từ lịch sử và SLO:

| Mức | Điều kiện kết hợp | Hành động |
|---|---|---|
| Quan sát | Pending flush/compaction tăng 3–5 phút nhưng chưa ảnh hưởng latency, đĩa còn dư | Kiểm trend, burst hay sustained |
| Cảnh báo flush | Pending flush tăng 10–15 phút **và** `AllMemtables...` tăng hoặc `BlockedOnAllocation` xuất hiện | Điều tra disk/flush writer, ưu tiên không làm thêm flush |
| Cảnh báo compaction | Pending compaction tăng 15–30 phút **và** SSTable count/read latency/disk pressure tăng | Điều tra strategy/throughput và bảng gây backlog |
| Khẩn cấp | Write timeouts/unavailables tăng, blocked allocation/commitlog allocation kéo dài hoặc disk free quá thấp | Chuyển sang runbook sự cố, giảm nguồn áp lực có kiểm soát |

Các khoảng phút trên **không phải mặc định Apache Cassandra**. Ví dụ cluster có đợt bulk load 10 phút có thể cần cửa sổ khác so với cluster thanh toán latency nhạy cảm.

### 9.2. Tư duy arrival rate và service rate

Gọi:

- \(\lambda_f\): tốc độ các memtable cần flush (task/giây).
- \(\mu_f\): tốc độ flush hoàn thành (task/giây).
- \(\lambda_c\): tốc độ sinh công việc compaction.
- \(\mu_c\): tốc độ công việc compaction hoàn tất.

Về trực giác, khi \(\lambda_f > \mu_f\) kéo dài, **flush queue có xu hướng tăng**; khi \(\lambda_c > \mu_c\), **compaction backlog có xu hướng tăng**. Nhưng task có kích thước không đồng đều và Cassandra chỉ đưa ra một số **ước lượng** backlog, nên biểu thức này là **mô hình để nghĩ**, không phải một công thức tính ETA chính xác.

Đặc biệt, **tăng \(\mu_f\) bằng cách thêm flush writer** có thể tạo nhiều SSTable nhỏ hơn, làm tăng \(\lambda_c\) hoặc chi phí compaction. Vì vậy tối ưu **hai hàng đợi cùng nhau** cùng disk/CPU mới hợp lý.

### 9.3. Tín hiệu theo node thay vì mỗi cluster total

Cho cùng một table, đặt cảnh báo:

- Node nào có `PendingFlushes` cực đại, không chỉ sum toàn cluster.
- Node nào có `AllMemtablesOnHeapSize`/memtable budget cao nhất.
- Node nào có `Compaction.PendingTasks` và `Table.PendingCompactions` tăng lâu nhất.
- Node nào có `CommitLog.WaitingOnSegmentAllocation` hoặc `BlockedOnAllocation` kéo dài.
- Node nào bị write p99 cao và đồng thời disk `await` cao.

Nếu chỉ một replica bị nghẽn, CL=`ONE` có thể chưa lộ lỗi ngay; `LOCAL_QUORUM` có thể vẫn thành công khi những replica khác khỏe. **Việc ghi thành công từ ứng dụng không chứng minh mọi node đã flush/compaction theo kịp.**

## 10. Runbook điều tra backlog: tìm nguyên nhân trước khi chỉnh cấu hình

### 10.1. Bước 1 — Xác định mức độ ảnh hưởng

Chốt những thông tin cơ bản:

- Cluster, DC/rack/node, Cassandra version, uptime/restart gần nhất.
- Thời điểm vấn đề bắt đầu; trùng bulk load, repair, bootstrap, snapshot, restore, cấu hình compaction hay deploy ứng dụng nào?
- Table nào có write tăng, TTL/DELETE nhiều hoặc partition đặc biệt lớn?
- SLO đọc/ghi theo p95/p99, timeout/unavailable, consistency level (ONE/LOCAL_QUORUM...) và loại request.
- Disk free, disk I/O latency, CPU, heap/off-heap và GC.
- Tình trạng **từng replica**; đừng chỉ hỏi một coordinator đã nhận ACK hay chưa.

Nếu ứng dụng bắt đầu timeout, cần **ổn định nguồn tải** theo cơ chế được phê duyệt trước, đồng thời bảo tồn log/metrics. Không cố tạo flush/compaction lớn để “xóa queue” khi đĩa đã bão hòa.

### 10.2. Bước 2 — Chụp snapshot trong cùng cửa sổ thời gian

~~~bash
# Trên node điều tra, lưu output kèm thời điểm ngoài lệnh.
nodetool status
nodetool tablestats -H observability_lab.events_by_tenant
nodetool tpstats
nodetool compactionstats -H
nodetool getcompactionthroughput
nodetool gcstats
~~~

Lấy thêm JMX metric **trên đúng node**:

~~~text
Table:
  AllMemtablesOnHeapSize, AllMemtablesOffHeapSize
  MemtableOnHeapSize, MemtableOffHeapSize
  PendingFlushes, MemtableSwitchCount, BytesFlushed
  PendingCompactions, LiveSSTableCount, CompactionBytesWritten

Pools:
  MemtableFlushWriter.PendingTasks/ActiveTasks/CompletedTasks
  PerDiskMemtableFlushWriter_*.PendingTasks/ActiveTasks
  MemtablePostFlush.PendingTasks
  CompactionExecutor.PendingTasks/ActiveTasks/CompletedTasks

Compaction:
  PendingTasks, PendingTasksByTableName, BytesCompacted,
  TotalCompactionsCompleted

CommitLog:
  TotalCommitLogSize, PendingTasks, WaitingOnSegmentAllocation,
  WaitingOnCommit

Others:
  MemtablePool.BlockedOnAllocation (nếu metric có trên binary)
  MutationStage.PendingTasks, ClientRequest.Write Latency/Timeouts
  JVM heap usage, GC pause, OS disk latency/IOPS, disk free
~~~

**Thu ít nhất hai hoặc nhiều điểm đo cùng cadence**, ví dụ mỗi 30–60 giây trong một số phút. Một snapshot không đủ suy luận queue có đang dài thêm hay đang thoát backlog.

### 10.3. Bước 3 — Dùng cây quyết định

~~~text
Pending flush tăng lâu?
  |
  +-- CÓ --> AllMemtables* có tăng? BlockedOnAllocation?
  |            |
  |            +-- CÓ --> Kiểm memtable budget, disk latency,
  |            |           flush pool active/pending, commit log
  |            |
  |            +-- KHÔNG --> Kiểm job flush ngắn theo burst,
  |                         metric exporter và thời điểm sample
  |
  +-- KHÔNG --> Pending compaction tăng lâu?
               |
               +-- CÓ --> Kiểm compaction throughput, strategy,
               |           active tasks, SSTable count, disk pressure
               |
               +-- KHÔNG --> Nếu request vẫn chậm:
                            kiểm CPU/GC, network, read path,
                            commit log fsync, client/coordinator
~~~

Nếu **cả hai pending cùng tăng**, ưu tiên đo **disk I/O saturation** và công việc tranh đĩa: compaction có thể làm flush đợi, trong khi flush tạo thêm đầu vào compaction. Đây là một vòng luẩn quẩn có thể cần **giảm arrival rate hoặc dời tác vụ bảo trì**, không chỉ thêm thread.

### 10.4. Bước 4 — Đánh giá I/O và throughput thực tế

| Quan sát | Giả thuyết | Thao tác tiếp theo |
|---|---|---|
| Disk latency tăng, `PerDiskMemtableFlushWriter_0` pending cao | Một data directory/volume bị giới hạn | Kiểm phần cứng, snapshot/repair, phân bố dirs và headroom |
| Flush pool luôn Active gần MaxPoolSize, pending tăng | Năng lực writer chưa đủ hoặc I/O chậm | Đo throughput, CPU, disk; xem tham số flush writers **sau khi loại trừ I/O bottleneck** |
| Compaction backlog tăng, throughput thực thấp hơn cap | CPU/disk/request contention hoặc task chờ | Kiểm active task, GC, I/O và loại compaction |
| Compaction backlog tăng, throughput chạm cap ổn định, disk còn headroom | Giới hạn throughput có thể quá thấp với workload | Cân nhắc tăng cap có kiểm soát |
| Compaction backlog tăng, disk 100% busy/await cao | Storage saturation | Không nâng cap ngay; giảm tranh chấp, lên kế hoạch capacity |
| `WaitingOnSegmentAllocation` cao | Commit log cấp phát segment/flush cleanup không theo kịp | Kiểm commit log disk, post-flush, total space |
| Disk free thấp và `TotalDiskSpaceUsed` lớn hơn `LiveDiskSpaceUsed` | Snapshot/file obsolete hoặc compaction giữ space | Kiểm snapshot/cleanup policy **không xóa file tay** |

### 10.5. Bước 5 — Kiểm định sau can thiệp

Đối với **một thay đổi** được phê duyệt, ghi lại:

1. Thời điểm, người thao tác, node/table, giá trị cũ/mới và mục tiêu.
2. Flush pending có giảm và `BlockedOnAllocation` có hết không?
3. Compaction pending có xu hướng về nền, SSTable/read latency ổn định không?
4. Disk `await`/CPU/GC/write p99 có cải thiện hay tệ hơn?
5. Có phát sinh số SSTable nhỏ nhiều hơn, compaction backlog mới hoặc disk tăng không?
6. Kết quả CQL theo CL của ứng dụng Java có giữ đúng dữ liệu không?

Nếu queue giảm nhưng p99 timeout tăng, **không xem là thành công**. Một hệ thống khỏe phải phục vụ query đúng SLA và còn đủ dự phòng để xử lý burst mới.

## 11. Những nút cấu hình và thao tác dễ bị lạm dụng

### 11.1. `memtable_flush_writers`: không phải càng nhiều càng tốt

Theo tài liệu Apache, `memtable_flush_writers` chi phối số writer theo disk và mức flush đồng thời. Mặc định tùy số data directories; nhiều writer có thể giúp khi **I/O thỉnh thoảng nghẽn**, nhưng cũng tạo **flush nhỏ và thường xuyên hơn**, tăng chi phí compaction.

Chỉ cân nhắc thay sau khi:

- Có `PendingFlushes`/flush pool pending tồn đọng đủ lâu.
- Có dấu hiệu cấp phát bộ nhớ bị chặn hoặc write latency bị ảnh hưởng.
- Disk có khả năng chịu throughput/IOPS tăng; không chỉ “disk bận 100%”.
- Hiểu số data directories, đường commit log và storage topology.
- Benchmark trước/sau bằng cùng workload và compaction strategy.

**Không** chỉnh `memtable_cleanup_threshold` deprecated để “tự cứu” khi flush chậm, và không tăng heap vô tội vạ khiến GC pause nặng hơn.

### 11.2. `compaction_throughput`: cần nhìn disk headroom

Trong Cassandra 5.0, `compaction_throughput` giới hạn throughput compaction tổng thể, đơn vị thể hiện trong cấu hình là MiB/s. Có thể xem trên node bằng:

~~~bash
nodetool getcompactionthroughput
nodetool help setcompactionthroughput
~~~

Lệnh **thay đổi** (chỉ để biết cú pháp; KHÔNG chạy production nếu chưa duyệt):

~~~bash
# Ví dụ lab, chỉ sau khi đã đo năng lực disk/CPU và có kế hoạch rollback.
# Tham số là giới hạn MiB/s theo nodetool Cassandra 5.0.
nodetool setcompactionthroughput 32
~~~

**Cảnh báo:** `0` ở lệnh này **không có nghĩa dừng compaction**; nó **bỏ giới hạn throughput** theo tài liệu. Nếu đĩa đang quá tải, bỏ giới hạn có thể làm read/write p99 tệ hơn.

Không tự lấy `32` làm ngưỡng chuẩn: ở cluster khác, cap này có thể quá thấp hoặc quá cao. Cấu hình có thể thay đổi theo version; kiểm `getcompactionthroughput` thực tế và cơ chế persistence khi restart.

### 11.3. `concurrent_compactors`: phải phân biệt bận với thực sự song song có ích

Tăng số compactor cho phép nhiều task chạy cùng lúc, nhưng cũng có thể **tranh đĩa/CPU** với nhau và với flush. Nếu disk throughput đã là bottleneck, thêm worker không tạo thêm băng thông vật lý. Theo hướng dẫn Apache, khi compaction quá nhanh/quá chậm nên xem `compaction_throughput` và tài nguyên thực trước khi chỉnh concurrency.

Đối với Cassandra 5.0, một số compaction đặc biệt như repair validation có các worker/giới hạn riêng. Không dựa vào một `CompactionExecutor.PendingTasks` để tăng chung mọi concurrency và hy vọng tất cả công việc chạy nhanh hơn.

### 11.4. `nodetool flush` và `nodetool compact` không phải “reset hàng đợi”

~~~bash
# Chỉ ví dụ cho node/table LAB, không dùng làm cách chữa nghẽn.
nodetool flush observability_lab events_by_tenant

# Tài liệu vận hành có thể cho phép major compaction,
# nhưng KHÔNG tự chạy để chữa backlog production:
nodetool compact observability_lab events_by_tenant
~~~

Vì:

- `flush` **tạo công việc flush** và thường tạo SSTable mới; khi writer đang bận, nó có thể **làm queue dài thêm**.
- `compact` có thể tạo **I/O rất lớn**, cần temporary disk headroom và làm cạnh tranh với flush/CQL. Với một số compaction strategy, major compaction còn có hậu quả vận hành dài hạn.
- `disableautocompaction` trong thời gian dài làm tích tụ SSTable; bật lại có thể tạo backlog lớn.
- Xóa file SSTable/tombstone bằng tay hoặc giảm `gc_grace_seconds` để “giải phóng đĩa nhanh” có nguy cơ **mất dữ liệu/zombie data** và không giải quyết nguyên nhân I/O.

**Thứ tự hợp lý:** xác định bottleneck → giảm/điều tiết nguồn gây tải nếu cần → xem tài nguyên và strategy → chỉ sau đó điều chỉnh một tham số → đo lại và rollback nếu xấu đi.

### 11.5. Phân biệt lỗi do workload/model dữ liệu

Một bảng có **partition rất rộng**, UPDATE dày, TTL ngắn hoặc DELETE theo range có thể tạo nhiều tombstone/SSTable và chi phí compaction:

- Partition key quá thô (ví dụ mọi sự kiện một tenant rất lớn vào cùng partition) làm bộ nhớ và đọc phân bố lệch.
- TTL của hàng triệu cell hết hạn gần nhau tạo đợt tombstone/compaction.
- Bulk ingest tạo nhiều SSTable kích thước tương tự nhưng không có headroom để compact.
- Replaying data trễ vào TWCS làm các cửa sổ thời gian chồng lấn hoặc khó thu hồi.
- SAI/secondary index, materialized view có thêm công việc ghi và lưu trữ.

Khi nghẽn kéo dài ở **một vài bảng**, cách sửa đúng có thể là thiết kế lại **partition key, bảng theo truy vấn, time buckets, TTL strategy hoặc lịch ingest**, không phải luôn tăng thread.

## 12. Lab CQL/nodetool: nhìn memtable chuyển thành SSTable

**Mục tiêu:** Quan sát memtable, flush counter và số SSTable trước/sau những đợt ghi nhỏ, không cố tạo disk saturation hay timeout. Bài này **không cần tạo pending queue lớn**; một cluster khỏe có thể flush nhanh đến mức bạn chỉ nhìn thấy pending = 0.

**Môi trường:** Cassandra 4.1 hoặc 5.0 **lab một node**, `cqlsh`, `nodetool` và JMX exporter/console nếu có. Chỉ thực thi trên môi trường được phép thay đổi dữ liệu; **không** chạy hàng loạt `nodetool flush` trên production để thử dashboard.

### Bước 1 — Tạo keyspace/bảng riêng

~~~sql
CREATE KEYSPACE IF NOT EXISTS observability_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS observability_lab.events_by_tenant (
    tenant_id text,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND compaction = {
      'class': 'SizeTieredCompactionStrategy'
  };
~~~

`SimpleStrategy` RF=1 **chỉ phù hợp demo một node**, không dùng làm mẫu triển khai production nhiều DC. Với ứng dụng thật, chọn `NetworkTopologyStrategy`/RF theo DC và thiết kế partition key tránh partition quá rộng.

### Bước 2 — Chụp baseline trước khi ghi

~~~bash
nodetool status
nodetool tablestats observability_lab.events_by_tenant
nodetool tpstats
nodetool compactionstats
~~~

Nếu có JMX console hoặc exporter, ghi lại các giá trị:

~~~text
Table.MemtableOnHeapSize
Table.AllMemtablesOnHeapSize
Table.MemtableSwitchCount
Table.PendingFlushes
Table.BytesFlushed
Table.LiveSSTableCount
Table.PendingCompactions
Compaction.PendingTasks
~~~

Tập giá trị **phải mang nhãn node và table** để so sánh sau. Với Cassandra 5.0, không nên giả định mọi metric xuất sẵn thành cùng một tên Prometheus; điều chỉnh dashboard theo mapping JMX exporter.

### Bước 3 — Ghi vài mutation và đọc dữ liệu

~~~sql
CONSISTENCY ONE;

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-a', '2026-11-21T01:00:00Z',
        11111111-1111-1111-1111-111111111111, 'create');

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-a', '2026-11-21T01:01:00Z',
        22222222-2222-2222-2222-222222222222, 'update');

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-b', '2026-11-21T01:02:00Z',
        33333333-3333-3333-3333-333333333333, 'create');

SELECT event_time, event_id, payload
FROM observability_lab.events_by_tenant
WHERE tenant_id = 'team-a';
~~~

**Quan sát hợp lý:** `MemtableLiveDataSize` hoặc `MemtableOnHeapSize` có thể tăng khi dữ liệu được ghi. Không đảm bảo mức tăng đúng bằng kích thước chuỗi payload, vì còn key, timestamp và overhead.

### Bước 4 — Chủ động flush **một** bảng trong lab

~~~bash
nodetool flush observability_lab events_by_tenant

nodetool tablestats observability_lab.events_by_tenant
nodetool tpstats
nodetool compactionstats
~~~

Sau một flush hoàn tất:

- `MemtableSwitchCount` có thể tăng so với baseline.
- `BytesFlushed` có thể tăng vì SSTable mới được viết.
- Kích thước active memtable thường giảm hoặc chuyển sang memtable mới.
- `LiveSSTableCount` có thể tăng, nhưng còn phụ thuộc compaction và thời điểm sampling.
- `PendingFlushes`/pool pending có thể về **0 ngay khi bạn kịp xem**.
- `PendingCompactions` chưa chắc tăng; STCS có ngưỡng và số lượng SSTable để lập lịch.

**Quan trọng:** Không cố tạo queue lớn bằng cách chạy nhiều flush đồng thời hay ghi liên tục tới khi disk đầy. Mục tiêu là hiểu **quan hệ nhân quả và cách quan sát**, không phải gây một sự cố thật.

### Bước 5 — Tạo thêm vài SSTable nhỏ trong lab

~~~sql
INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-a', '2026-11-21T01:03:00Z',
        44444444-4444-4444-4444-444444444444, 'paid');

INSERT INTO observability_lab.events_by_tenant
  (tenant_id, event_time, event_id, payload)
VALUES ('team-b', '2026-11-21T01:04:00Z',
        55555555-5555-5555-5555-555555555555, 'processed');
~~~

~~~bash
nodetool flush observability_lab events_by_tenant
nodetool tablestats observability_lab.events_by_tenant
nodetool compactionstats
~~~

Nếu table đủ điều kiện compaction, có thể thấy một task tự động; nếu không thì kết quả `pending tasks: 0` **không phải lỗi lab**. Không chạy major compaction chỉ để tạo một biểu đồ đẹp.

### Bước 6 — So sánh ba mốc

| Metric | Trước ghi | Sau flush #1 | Sau flush #2 | Điều cần giải thích |
|---|---|---|---|---|
| `MemtableOnHeapSize` | Ghi lại | Có thể về thấp | Có thể về thấp | Memtable đang hoạt động |
| `AllMemtablesOnHeapSize` | Ghi lại | Có thể giảm sau flush | Có thể dao động | Bao gồm các memtable chưa reclaim |
| `MemtableSwitchCount` | Ghi lại | Có thể tăng | Có thể tăng nữa | Counter, theo dõi chênh lệch |
| `BytesFlushed` | Ghi lại | Tăng khi flush thực | Tăng tiếp | Tính rate/bytes, không phải pending |
| `PendingFlushes` | Ghi lại | Thường về 0 nhanh | Thường về 0 nhanh | Ảnh chụp trạng thái, dễ bỏ lỡ task ngắn |
| `LiveSSTableCount` | Ghi lại | Có thể +1 | Có thể +1 hoặc giảm nếu compact | Không giả định monotonic |
| `PendingCompactions` | Ghi lại | Có thể =0 | Có thể =0 | Phụ thuộc strategy/đầu vào |

Thực hành đạt yêu cầu khi người học **đo được ít nhất một biến đổi hợp lý** của switch/flush/SSTable và giải thích được vì sao một số pending vẫn =0. Kết quả phụ thuộc thời điểm, cluster và cách Cassandra tự lập lịch.

### Bước 7 — Kiểm dữ liệu logic và không thay đổi CL vô cớ

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_id, payload
FROM observability_lab.events_by_tenant
WHERE tenant_id = 'team-a';

SELECT event_time, event_id, payload
FROM observability_lab.events_by_tenant
WHERE tenant_id = 'team-b';
~~~

Flush/compaction đúng phải **giữ nguyên kết quả đọc CQL** theo mutation đã ghi. Nếu thấy missing row, timeout hoặc lỗi khác, không kết luận ngay “do compaction”: kiểm CL, node availability, logs, disk, schema và timestamp.

## 13. Java Driver: quan sát từ phía ứng dụng

Một ứng dụng Java **không nhìn trực tiếp vào memtable**. Cassandra Java Driver 4.x gửi CQL đến coordinator; ứng dụng có thể đo **request success/latency/timeouts**, còn memtable/flush/compaction được quan sát qua JMX/nodetool trên **server**.

### 13.1. Ví dụ Java dùng prepared statements

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.UUID;

public final class LabEventWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public LabEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO observability_lab.events_by_tenant " +
            "(tenant_id, event_time, event_id, payload) VALUES (?, ?, ?, ?)");
    }

    public long insertAndMeasureNanos(
            String tenantId, String payload) {
        BoundStatement statement = insert.bind(
                tenantId, Instant.now(), UUID.randomUUID(), payload)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE);

        long startedAt = System.nanoTime();
        session.execute(statement);
        return System.nanoTime() - startedAt;
    }
}
~~~

Trong lab RF=1, CL ONE cần một replica phản hồi. Với production RF≥3, dùng CL theo SLA/độ sẵn sàng và local DC, **không** sao chép CL ONE từ bài này vào hệ thống nghiệp vụ.

`insertAndMeasureNanos` đo **thời gian request nhìn từ client**, gồm kết nối, driver, coordinator, mạng và xử lý replica; nó **không đo thời gian flush/compaction riêng**. Chỉ một kết quả đo không phải p99: cần nhiều request, histogram và phân phối theo thời gian.

### 13.2. Chụp cùng lúc application và server metrics

Ví dụ bảng correlation cho một sự cố giả định:

| Mốc UTC | Java write p99 | Java timeouts/phút | Node pending flush | Node pending compaction | Disk await |
|---|---:|---:|---:|---:|---:|
| 10:00 | 12 ms | 0 | 0 | 2 | 1 ms |
| 10:05 | 20 ms | 0 | 3 | 12 | 3 ms |
| 10:10 | 180 ms | 18 | 11 | 24 | 24 ms |
| 10:15 | 40 ms | 1 | 2 | 17 | 5 ms |

Đây là **dữ liệu minh họa**, không phải sự kiện quan sát từ Cassandra thật. Có quan hệ giữa disk await, backlog và p99, nhưng cần điều tra sự kiện nào gây I/O: compaction, flush, snapshot, repair, backup hay workload khác.

Thực hành điều tra từ app:

1. Gắn nhãn `cluster`, `dc`, `service`, `operation`, `consistency_level`, `table`/workload (không log partition key nhạy cảm).
2. Ghi timeouts theo loại (read, write, unavailable), retry count và driver pool/reconnection state nếu được hỗ trợ.
3. Đối chiếu thời điểm lỗi với **node sở hữu replica**, không mặc định mọi request đi cùng một coordinator.
4. Kiểm **idempotency** trước khi retry mutation timeout: ACK có thể bị mất trong khi write đã xảy ra.
5. Không bật speculative execution/retry vô hạn chỉ để vượt qua backlog, vì dễ **khuếch đại lưu lượng** và làm đĩa bận hơn.

### 13.3. Đo p99 bằng một hệ thống metrics, không bằng `println`

Với Java Driver, nên dùng driver metrics tích hợp và/hoặc metrics của service (Micrometer, OpenTelemetry...) theo cấu hình/thư viện đã chuẩn hóa. Nếu cần một histogram CQL latency:

- Đo nhiều request thành công và thất bại; phân nhánh loại request.
- Dùng **histogram/timer** đúng loại, xuất p50/p95/p99 trong cửa sổ có đủ sample.
- Đồng bộ đồng hồ để tương quan server/client, nhưng **thời gian request** nên đo bằng monotonic clock như `System.nanoTime()`.
- Theo dõi retry, request rate, in-flight, connection pool, client timeouts cùng với chỉ số server.
- Đặt ngưỡng alert dựa trên **SLO**; đừng biến mọi compaction nền bình thường thành cảnh báo người dùng.

**Tính đúng của dữ liệu:** CQL đọc sau flush không thay thế anti-entropy repair. Nếu một replica chậm và bị bỏ lỡ mutation, cần kiểm hints/repair/CL theo topology thay vì chỉ nhìn bảng metrics của coordinator.

## 14. Case study: chẩn đoán các tình huống thường gặp

### Ca A — Flush queue tăng, compaction chưa bùng lên

**Tín hiệu (minh họa):**

~~~text
Node N1, table events_by_tenant
  PendingFlushes:             3 -> 9 -> 17
  AllMemtablesOnHeapSize:   500 -> 740 -> 900 MiB
  MemtablePool blocked:      0 -> 2 -> 5 (theo exporter)
  PendingCompactions:        2 -> 3 -> 4
  Disk await:                2 -> 20 -> 35 ms
~~~

**Giả thuyết:** Flush đang bị disk I/O chặn, không nhất thiết do compaction chưa đủ worker. Phải kiểm:

- `tpstats`: flush writer active/pending, `MemtablePostFlush`.
- Disk I/O của đúng data directory, commit log directory và các tác vụ OS.
- Snapshot/backup, `nodetool netstats`, compaction task nào đang đọc/ghi cùng đĩa.
- Memory budget, các table khác (có thể một table khác đang chiếm flush writer chung).

**Không nên:** tăng `memtable_flush_writers` ngay khi disk đã saturated; thêm writer có thể tạo thêm tranh chấp. **Ưu tiên:** ổn định write burst/backup/repair có kiểm soát, sửa disk bottleneck, rồi đánh giá backlog có hồi phục không.

### Ca B — Compaction backlog tăng dần, flush vẫn bình thường

~~~text
Node N2, table orders_by_customer
  PendingFlushes:           0 -> 0 -> 0
  PendingCompactions:      10 -> 25 -> 42
  LiveSSTableCount:        58 -> 87 -> 126
  SSTablesPerRead:         tăng
  p99 read latency:        tăng
~~~

**Giả thuyết:** Công việc compaction đang sinh nhanh hơn xử lý được; có thể compaction cap quá thấp, kích thước SSTable bất hợp lý hoặc workload tạo nhiều update/TTL.

**Điều tra:** `compactionstats` loại task và tiến độ, `getcompactionthroughput`, CPU/disk headroom, compaction strategy của table và các sự kiện bulk ingest. Nếu disk còn dư và throughput thực đang chạm cap, mới cân nhắc thay cap **từng bước**. Nếu disk đã nghẽn, tăng cap có thể làm read latency tệ hơn.

### Ca C — Flush và compaction cùng tăng, write timeout xuất hiện

~~~text
N3:
  MemtablePool.BlockedOnAllocation: xuất hiện kéo dài
  Flush pool PendingTasks:       tăng
  Compaction.PendingTasks:       tăng
  CommitLog.WaitingOnSegmentAllocation: tăng
  Data disk await:               tăng cao
  Client write timeouts:         tăng
~~~

**Giả thuyết:** Có vòng tranh chấp tài nguyên: compaction/flush/commit log đều cần I/O, memtable không giải phóng được kịp, client bắt đầu chờ.

**Ưu tiên:** bảo vệ tính sẵn sàng và disk headroom, tạm điều tiết nguồn ingest theo cơ chế đã duyệt, xem các job nền có thể dời, phân tích disk và limit theo từng node. Không dùng `nodetool flush` hoặc major compaction để “clear backlog” trong lúc disk đang quá tải.

### Ca D — Commit log chậm nhưng memtable pending thấp

~~~text
N4:
  PendingFlushes:                  0
  PendingCompactions:              1
  CommitLog.WaitingOnCommit:       tăng
  CommitLog.PendingTasks:          tăng
  Write p99:                       tăng
~~~

**Giả thuyết:** Đường fsync/commit log có vấn đề, không phải flush queue. Phải xem commit log sync mode, disk latency, volume placement và tình trạng segment. **Đừng chỉnh compaction thread trước khi chứng minh compaction tranh I/O**.

### Ca E — Pending compaction luôn khác 0 nhưng dịch vụ khỏe

~~~text
N5:
  PendingCompactions:      3 -> 5 -> 2 -> 4
  LiveSSTableCount:        ổn định theo strategy
  Compaction throughput:   hoạt động
  Read/write p99:          trong SLO
  Disk free/IO latency:    bình thường
~~~

Đây có thể là **hoạt động nền bình thường**, nhất là với workload ghi đều và compaction chạy liên tục. Không nên tạo cảnh báo P1 chỉ vì một gauge hiếm khi bằng 0. Cần dùng trend dài hơn, backlog tuổi bao lâu và dấu hiệu ứng dụng bị ảnh hưởng.

### Ca F — Chỉ một node trong DC bị nóng

Một node có memtable/flush/compaction cao hơn hẳn những node khác:

- Có **hot partition/hot token range** dẫn nhiều write về node đó?
- Keyspace RF, racks/DC và token distribution có cân bằng?
- Node đó vừa replace/bootstrap, repair/streaming nặng hoặc hardware kém?
- Cùng table có compaction strategy/config khác các node vì thao tác JMX cục bộ?
- Một disk trong nhiều data directories lỗi hoặc performance giảm?

**Đừng tổng hợp bằng trung bình cluster rồi bỏ qua node nóng**. Với RF=3, chỉ một node nghẽn có thể bị client che khuất trong một thời gian nhưng sẽ làm giảm khả năng chịu lỗi khi node khác DOWN.

## 15. Checklist dashboard và ứng phó production

### 15.1. Các biểu đồ tối thiểu

| Panel | Nhãn cần có | Cách đọc |
|---|---|---|
| Active/all memtable bytes | cluster/DC/node/keyspace/table | Phân biệt dữ liệu đang ghi và memtable pending/index |
| Memtable switch rate, bytes flushed/sec | node/table | Tốc độ tạo SSTable qua flush, đối chiếu burst |
| Pending flush + flush pool active/pending | node/table/pool | Queue dài do producer nhanh hay writer thiếu tài nguyên |
| Memtable blocked allocation | node | Phát hiện backpressure trực tiếp lên cấp phát |
| Pending compaction theo table và node | node/table | Xác định bảng tạo backlog |
| Bytes compacted/sec, compaction task progress | node/compaction type | Năng lực xử lý, task lớn kéo dài |
| SSTable count + SSTables per read | node/table | Read amplification và đặc tính strategy |
| CommitLog pending/wait timers | node | Phân biệt nghẽn fsync/segment |
| Disk I/O latency/throughput/free space | node/disk | Bằng chứng tài nguyên gốc |
| JVM GC/heap/off-heap | node | Phân biệt memory pressure và flush bottleneck |
| Java p95/p99 latency, timeouts, retry | service/DC/operation/CL | Tác động trực tiếp tới SLO |

### 15.2. Checklist xử lý trong lúc cảnh báo

- [ ] Đã định vị **node/DC/table** chịu backlog; xác định metrics có được scrape liên tục không.
- [ ] Đã kiểm `nodetool status`, topology, streaming, repair/backup và recent changes.
- [ ] Có ít nhất hai hoặc nhiều mốc cùng cadence cho pending flush/compaction và rates liên quan.
- [ ] Đã xem flush pools, post-flush và `BlockedOnAllocation`, không chỉ `PendingFlushes`.
- [ ] Đã xem compaction type, progress và số SSTable theo strategy, không chỉ total pending.
- [ ] Đã so với disk latency, disk free, CPU/GC, commit log fsync, request p99.
- [ ] Đã phân biệt traffic burst bình thường với backlog **không hồi phục**.
- [ ] Đã giữ nguyên hoặc bảo vệ CL theo yêu cầu ứng dụng; không hạ CL không phê duyệt.
- [ ] Nếu thay cấu hình, chỉ thay **một biến** mỗi lần, có số liệu trước/sau và rollback.
- [ ] Không xóa SSTable/snapshot/tombstone bằng tay, không ép flush/major compaction để chữa queue.
- [ ] Đã kiểm CQL CRUD và ứng dụng Java không hồi quy sau xử lý.
- [ ] Đã ghi nguyên nhân gốc, bảng/node ảnh hưởng và hành động phòng ngừa.

### 15.3. Mẫu báo cáo ngắn cho một incident

~~~text
INCIDENT: CASSANDRA-WRITE-LATENCY-EXAMPLE
Window UTC:    2026-11-21 10:00 .. 10:20
Cluster/DC:    test-east / dc1
Node/Table:    n3 / observability_lab.events_by_tenant

Symptoms:
  Flush pending 2 -> 18; compaction pending 10 -> 32.
  All-memtables memory rising; disk await 3 -> 28 ms.
  Write p99 15 -> 220 ms; client timeout spike.

Correlated events:
  Bulk ingest overlapped repair + compaction on same volume.

Hypothesis:
  I/O contention delayed flush, then blocked memtable allocation.

Action:
  Ingest rate limited under approved runbook; repair rescheduled.
  No forced flush/compaction, no change to gc_grace_seconds.

Verification:
  Flush pending returned to baseline; compaction queue decreasing.
  Disk await and write p99 recovered, no new timeouts.

Residual risk:
  Recheck backlog and disk headroom over next compaction cycle.
~~~

Số trong mẫu là **dữ liệu giả lập**, không phải ngưỡng mặc định hoặc báo cáo incident có thật.

## 16. Câu hỏi tự đánh giá

**Câu 1.** Vì sao `MemtableOnHeapSize` nhỏ nhưng `AllMemtablesOnHeapSize` lớn không nhất thiết mâu thuẫn?  
**Gợi ý:** Tổng có memtable chờ flush, index và thành phần khác; active memtable có thể đã switch.

**Câu 2.** `MemtableSwitchCount` tăng trong 10 phút có đủ chứng minh flush đang nghẽn không?  
**Gợi ý:** Không; nó là số lần switch. Phải nhìn pending, active writer, thời gian hồi phục và blocked allocation.

**Câu 3.** `PendingFlushes` mang chữ pending nhưng Apache liệt kê metric type Counter. Nên vẽ rate/increase ngay không?  
**Gợi ý:** Không tự động; xác minh semantics/version/exporter, kết hợp `tpstats` và snapshots theo thời gian.

**Câu 4.** Vì sao tăng `memtable_flush_writers` có thể khiến `PendingCompactions` tăng?  
**Gợi ý:** Có thể tạo nhiều SSTable nhỏ và thường xuyên hơn, tăng công việc compaction.

**Câu 5.** `Compaction.PendingTasks=100` có nghĩa còn 100 giây nữa hoàn thành không?  
**Gợi ý:** Không. Đó là estimate số task, kích thước/chí phí không đồng đều và ETA không được suy ra từ số task.

**Câu 6.** `PendingFlushes=0`, `PendingCompactions` tăng lâu và `SSTablesPerRead` tăng. Nên kiểm gì?  
**Gợi ý:** Compaction strategy, throughput, các task đang hoạt động và disk/CPU, không ưu tiên thêm flush writer.

**Câu 7.** Flush và compaction cùng tăng, disk await rất cao. Có nên lập tức đặt `setcompactionthroughput 0`?  
**Gợi ý:** Không; 0 bỏ giới hạn, có thể làm đĩa nghẽn hơn.

**Câu 8.** Tại sao `nodetool flush` không phải cách giải quyết backlog?  
**Gợi ý:** Nó thêm công việc flush/tạo SSTable, không làm writer hoặc disk nhanh hơn.

**Câu 9.** Vì sao nên xem `CommitLog.WaitingOnSegmentAllocation` khi write chậm?  
**Gợi ý:** Commit log segment allocation có thể bị chặn do disk/flush cleanup, khác với compaction queue.

**Câu 10.** Vì sao sum pending compaction toàn cluster có thể che sự cố?  
**Gợi ý:** Một node với disk lỗi có thể bị che bởi các node không có backlog; xem max/trend theo node/table.

**Câu 11.** Trên một cluster khỏe, lab với ba INSERT và một flush có thể luôn thấy PendingFlushes=0. Lab có thất bại không?  
**Gợi ý:** Không; queue có thể rất ngắn và được xử lý trước khi sample. Đo counter switch/bytes flushed và SSTable.

**Câu 12.** Java Driver báo timeout nhưng server compaction pending thấp. Có thể kết luận Cassandra không có vấn đề không?  
**Gợi ý:** Không; kiểm commit log, request thread pools, GC, network, coordinator và client retry.

**Câu 13.** Tại sao không dùng read/write latency trung bình duy nhất để đánh giá compaction?  
**Gợi ý:** SLO nhạy p95/p99, hot partitions/node và tail latency; trung bình dễ che spike.

**Câu 14.** Nếu tăng compaction throughput và pending giảm nhưng p99 read tăng mạnh, thay đổi có đạt mục tiêu không?  
**Gợi ý:** Không; đánh giá cả SLO và tài nguyên, cân nhắc rollback và giới hạn throughput.

**Câu 15.** Vì sao repair/streaming cùng thời điểm compaction là dữ kiện quan trọng?  
**Gợi ý:** Chúng có thể tranh disk/network/CPU và tạo thêm công việc nền, làm queue dài.

## 17. Tổng kết và sơ đồ ghi nhớ

~~~text
                 CQL WRITE / JAVA DRIVER
                           |
                CommitLog + Memtable
                           |
                    Memtable switch
                           |
              +------------+------------+
              |                         |
       Flush queue/pools            Active memtable mới
              |
        Memtable flush writers
              |
          SSTable mới
              |
       Compaction backlog
              |
       Compaction executor
              |
          SSTable merged
              |
       Đọc nhanh hơn nếu giảm
       read amplification phù hợp

Quan sát đồng thời:
  - Memtable active/all bytes + BlockedOnAllocation
  - PendingFlushes + flush/post-flush thread pools
  - PendingCompactions + Compaction.PendingTasks
  - BytesFlushed/sec + BytesCompacted/sec + SSTable count
  - CommitLog fsync/segments + OS disk/CPU/GC
  - Java request p95/p99, errors, retries, CL

Đọc TREND và tương quan nguyên nhân;
không điều chỉnh thread/cap chỉ vì một gauge khác 0.
~~~

**Nguyên tắc trọng tâm:** Memtable, flush queue và pending compaction là **ba lớp nối tiếp của đường ghi Cassandra** nhưng có tài nguyên, metric và tốc độ xử lý khác nhau. Quan sát đúng đòi hỏi đối chiếu **node–table–time window**, phân biệt counter/gauge và ghép với disk/CPU/GC cùng độ trễ Java. Khi backlog kéo dài, hãy giải quyết **nút thắt thực**; đừng đẩy thêm công việc vào hàng đợi bằng flush/major compaction cưỡng bức.

## Tài liệu tham khảo

- [Apache Cassandra 5.0 — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — tên và loại Table, ThreadPools, Compaction, CommitLog, JVM/ClientRequest metrics.
- [Apache Cassandra 5.0 — Storage Engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTable, flush và đường ghi.
- [Apache Cassandra 5.0 — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — compaction strategy, tombstone, throughput, công cụ vận hành.
- [Apache Cassandra 5.0 — cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — `memtable_flush_writers`, `memtable_cleanup_threshold`, memtable memory budgets, `concurrent_compactors`, `compaction_throughput`.
- [Apache Cassandra 5.0 — nodetool tpstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tpstats.html) — thread-pool usage và cách dùng.
- [Apache Cassandra 5.0 — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) — thống kê table và các tùy chọn format.
- [Apache Cassandra 5.0 — nodetool compactionstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/compactionstats.html) — pending tasks, compaction đang chạy và tiến độ.
- [Apache Cassandra 5.0 — nodetool flush](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/flush.html) — cú pháp flush một hoặc nhiều table.
- [Apache Cassandra 5.0 — getcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/getcompactionthroughput.html) và [setcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/setcompactionthroughput.html) — giới hạn compaction throughput; giá trị `0` bỏ giới hạn.
- [Apache Cassandra 5.0 — Use nodetool for troubleshooting](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html) — cách diễn giải compaction backlog, thread pools và dropped messages.

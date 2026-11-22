# Log hệ thống, GC log và tương quan với tăng độ trễ

## 1. Bài toán: vì sao p99 tăng mạnh nhưng CPU trung bình vẫn bình thường?

Một ứng dụng Java đọc dữ liệu từ **Apache Cassandra** theo partition key. Trong nhiều giờ, độ trễ p99 của API khoảng 40 ms. Đến 10:05 UTC, p99 tăng lên 2 giây, xuất hiện một số `ReadTimeout`, rồi tự giảm sau vài phút. Dashboard CPU trung bình của cả cluster vẫn chỉ khoảng 45%. Nếu chỉ nhìn CPU hoặc vài dòng `ERROR` của ứng dụng, khó biết vấn đề nằm ở **JVM garbage collection (GC)**, **SSTable/read path**, **compaction**, **ổ đĩa**, **mạng** hay một **replica** cụ thể.

Trong Cassandra, một truy vấn qua coordinator có thể cần phản hồi từ nhiều replica. Chỉ một replica bị tạm dừng hoặc bị nghẽn cũng có thể làm tail latency tăng, nhất là khi consistency level (CL) yêu cầu phản hồi của replica ấy. Ngược lại, thấy một dòng “GC pause” trong log gần thời điểm sự cố **không tự chứng minh GC là nguyên nhân**.

Bài này hướng dẫn cách **ghép bằng chứng theo mốc thời gian** từ:

- **System/application log:** sự kiện trên node, timeout, dropped messages, flush, compaction, repair và trạng thái cụm.
- **GC log:** hoạt động cấp phát/thu hồi heap, những lần *stop-the-world* (STW) và thời lượng pause.
- **Metrics:** độ trễ p50/p95/p99, số timeout, queue, heap, disk I/O, tombstone scan và backlog.
- **CQL tracing:** các bước xử lý của **một truy vấn được chọn** qua coordinator/replica.
- **Client/Java Driver:** request đã chạy trên client bao lâu, CL nào, coordinator nào và kết quả lỗi nào.

**Mục tiêu:** đọc đúng log và đơn vị thời gian, xây dựng timeline có thể kiểm chứng, tách tương quan khỏi quan hệ nhân quả, điều tra nhiều giả thuyết cạnh tranh, thực hành `cqlsh`/`nodetool`/Java và viết báo cáo sự cố có bằng chứng.

> Phạm vi: Cassandra vận hành trên JVM với full replica thông thường, ví dụ theo `NetworkTopologyStrategy`. Tên file log, cấu hình GC, metric JMX, câu chữ của log và tùy chọn tracing thay đổi theo phiên bản Cassandra/JDK. Mọi dòng log minh họa trong bài là **ví dụ**, không phải output đã đo từ một cluster thật.

## 2. Mô hình tư duy: yêu cầu đi qua nhiều lớp độ trễ

Với bảng có partition key `(device_id, event_day)`, một read không chỉ là một thao tác truy cập file:

~~~mermaid
flowchart TD
    A["Java client gửi SELECT"] --> B["Network tới coordinator"]
    B --> C["Coordinator chọn replica theo token, RF và CL"]
    C --> D["Replica: queue + CPU + JVM"]
    D --> E["Memtable / key cache / Bloom filter / SSTable"]
    E --> F["Đọc disk, giải nén, hòa giải version/tombstone"]
    F --> G["Replica gửi kết quả hoặc digest"]
    G --> H["Coordinator đối chiếu và trả response"]
    H --> I["Driver đọc page, decode và ứng dụng xử lý"]
    J["GC pause / heap pressure"] -.-> C
    J -.-> D
    K["Disk I/O / compaction / repair"] -.-> E
    L["Mạng / replica down"] -.-> B
    L -.-> G
~~~

Một độ trễ end-to-end có thể được hình dung theo các phần:

~~~text
Client latency
  ≈ thời gian client/network
  + chờ/điều phối tại coordinator
  + chờ/xử lý trên replica
  + truyền và hợp nhất phản hồi
  + decode/page và phần công việc ứng dụng tính vào phép đo
~~~

Đây là **phân rã khái niệm**, không phải các số hạng có thể cộng trực tiếp từ mọi metric. Các replica xử lý **song song**, và có thể có speculative retry, paging hoặc timeout; không được cộng thời gian của ba replica thành một tổng tuyến tính.

### Trung bình không mô tả sự cố tail latency

| Chỉ số | Ý nghĩa | Điều cần cảnh giác |
| --- | --- | --- |
| **p50** | Một nửa số request nằm ở hoặc dưới mốc này. | Có thể vẫn tốt dù một phần nhỏ request rất chậm. |
| **p95** | Khoảng 95% request không vượt mốc này. | Nhạy hơn với đuôi phân phối so với trung bình. |
| **p99 / p99.9** | Mô tả những request chậm nhất theo phân vị. | Cần đủ mẫu; phân vị từ các nhóm nhỏ không được lấy trung bình tùy tiện. |
| **Timeout rate** | Tỷ lệ request không hoàn tất trước deadline đã cấu hình. | Không phải mọi timeout đều do GC. |
| **Throughput** | Số request/s trong cùng khoảng đo. | Lưu lượng tăng đột biến có thể tạo queue ngay cả khi CPU trung bình chưa bão hòa. |

Ví dụ trong một phút có 10.000 request, 9.900 request mất 20 ms và 100 request mất 2.000 ms: **đa số request vẫn nhanh**, nhưng phần đuôi ảnh hưởng nghiêm trọng tới người dùng. Dashboard cần giữ **latency histogram, error count và request rate** trên **cùng cửa sổ thời gian**, không chỉ một số trung bình.

## 3. Mỗi loại log nói được điều gì?

| Nguồn | Nội dung nên tìm | Giới hạn |
| --- | --- | --- |
| **`system.log`** Cassandra | Node lifecycle, gossip/topology, timeout/dropped messages, warnings, flush/compaction/repair, disk hoặc JVM-related events tùy phiên bản. | Dòng log là tín hiệu/sự kiện; không phải mọi request đều được ghi chi tiết. |
| **`debug.log`** (nếu cấu hình) | Dấu vết chi tiết hơn để điều tra một cơ chế cụ thể. | Có thể tạo I/O và khối lượng log đáng kể; không nên bật toàn cluster vô hạn. |
| **GC log** JVM | Thời điểm, loại GC, thời lượng pause, heap trước/sau GC, concurrent phases theo cấu hình. | Không tự biết partition nào, truy vấn nào hoặc disk nào gây áp lực cấp phát. |
| **Java client/driver log** | Bắt đầu/kết thúc request, coordinator nếu được ghi, timeout, retry, request id và CL. | Client time có thể gồm network, queue, paging và mã ứng dụng. |
| **OS/storage log và metrics** | Disk latency, I/O errors, saturation, OOM, network drops, container throttling. | Phải đối chiếu với PID/node/volume mà Cassandra thực sự sử dụng. |
| **Tracing session** | Một số bước thực thi của truy vấn được chọn trên coordinator/replicas. | Không phải trace phân tán hoàn chỉnh của mọi tầng ứng dụng; có overhead và TTL lưu vết. |

### 3.1. Đừng giả định đường dẫn giống nhau ở mọi môi trường

Tùy cách cài đặt:

- Cassandra có thể lưu log dưới thư mục `logs/` của cài đặt, một thư mục riêng như `/var/log/cassandra/`, hoặc chuyển ra **journald/stdout** trong container.
- GC log có thể ở file riêng được JVM bật qua cấu hình, hoặc chuyển vào stdout; có hệ thống **không bật GC log đầy đủ**.
- File `system.log`, `debug.log` và log xoay vòng có retention riêng; bản phân tích cần ghi rõ **node, phiên bản Cassandra/JDK, file và khoảng thời gian**.
- Cấu hình logging ở các phiên bản thường liên quan tới **Logback** và tùy chọn JVM. Đừng sửa hàng loạt file cấu hình giữa sự cố khi chưa hiểu tác động và cơ chế reload.

**Các lệnh đọc log dưới đây chỉ minh họa cách dùng trên máy Linux có quyền được phép**, không có nghĩa các file thật nằm đúng đường dẫn ví dụ:

~~~bash
# Tìm lỗi, warning hoặc timeout từ file system.log đã xác minh.
grep -Ei 'timeout|dropped|overload|error|warning|compaction|flush' \
  /var/log/cassandra/system.log

# Đọc phần cuối trong môi trường lab.
tail -n 200 /var/log/cassandra/system.log

# Khi hệ thống chuyển log qua journald:
journalctl -u cassandra --since "2026-11-21 10:00:00" \
  --until "2026-11-21 10:20:00"
~~~

Các lệnh sẽ phải thay đường dẫn, service name và **timezone của timestamp** theo node đang xem. `grep` có thể bỏ qua sự kiện liên quan vì câu chữ log khác; nên kiểm tra ngữ cảnh xung quanh mốc thời gian, không chỉ các dòng chứa `ERROR`.

## 4. Tạo một timeline đáng tin cậy: chuẩn hóa đồng hồ trước khi tìm nguyên nhân

Đây là bước hay bị bỏ qua nhất khi phân tích “GC xuất hiện gần thời điểm độ trễ tăng”.

### 4.1. Năm loại thời gian không được lẫn

| Nguồn thời gian | Đặc điểm | Quy tắc khi ghép |
| --- | --- | --- |
| Application log | Có thể theo UTC, local timezone hoặc format tùy logger. | Ghi rõ zone; chuyển về UTC. |
| Cassandra system log | Format/zone tùy logging config và host. | Xác nhận offset, không đoán từ tên DC. |
| Java GC log | Có thể in timestamp UTC với offset, uptime từ khi JVM khởi động hoặc cả hai. | Nếu dùng uptime, xác định mốc start và độ lệch đồng hồ tương ứng. |
| Metrics dashboard | Timestamp scrape, aggregation window và sampling interval. | Phân biệt **event time** với **scrape time**; độ chính xác hữu hạn. |
| CQL tracing | Event timestamp, elapsed từ session start, trace session id. | Kiểm tra đơn vị microsecond/millisecond và thời gian của node ghi sự kiện. |

Một số log GC của JDK mới dùng **unified logging** (chẳng hạn `-Xlog:gc*`); chúng có thể chứa timestamp dạng `[2026-11-21T10:05:02.123+0000]` hoặc uptime dạng `[12345.678s]` tùy decorator. Log GC của JDK cũ có format khác. **Uptime 12.345 giây không phải 12:34:05 UTC**.

### 4.2. Quy trình đồng bộ mốc

1. Chọn **mốc sự cố UTC** từ client SLO, ví dụ 10:05:00–10:10:00 UTC.
2. Kiểm tra NTP/clock skew và timezone của **tất cả node liên quan**, kể cả Java client/coordinator/replica. Một node lệch đồng hồ 30 giây có thể làm mối liên hệ nhân quả nhìn đảo ngược.
3. Xác nhận log rotation: phần trước và sau sự cố có thể nằm ở file khác.
4. Ghi riêng **timestamp bắt đầu, kết thúc, duration, node và nguồn** của từng sự kiện.
5. Chồng dữ liệu theo cùng time window; giữ cả raw timestamp và mốc UTC đã chuẩn hóa.
6. Đánh dấu **độ bất định**: một metric scrape cách 30 giây không thể chứng minh chính xác thứ tự của hai sự kiện cách nhau 2 ms.

Ví dụ timeline **giả lập**:

| Mốc UTC | Nguồn | Sự kiện | Điều có thể kết luận |
| --- | --- | --- | --- |
| 10:04:40 | Application | p99 read khoảng 45 ms | Baseline trước sự cố. |
| 10:05:01 | JVM N2 | GC STW pause 1.8 giây | N2 tạm dừng một phần xử lý Java trong khoảng pause. |
| 10:05:01–10:05:04 | Client metrics | p99 read 2.1 giây, timeout tăng | Có tương quan thời gian với pause, nhưng chưa chứng minh nguyên nhân. |
| 10:05:03 | Cassandra N1 | Một số request đọc tới replica chậm | Có thể liên quan N2; cần xem query/endpoint cụ thể. |
| 10:05:10 | Metrics N2 | Queue giảm dần, p99 trở về baseline | Phù hợp một đợt nghẽn tạm thời; vẫn kiểm tra I/O, traffic. |

**Tương quan mạnh hơn** khi thấy: pause bắt đầu **trước hoặc trong** khoảng chậm, request thực sự cần N2, queue tăng trên N2, và p99 giảm sau khi pause kết thúc. **Tương quan yếu** nếu GC ở một node khác không tham gia query, hoặc disk I/O đã bão hòa trước GC.

## 5. Hiểu GC log: pause, concurrent phase và áp lực heap

### 5.1. GC là gì đối với Cassandra?

JVM tạo nhiều object khi xử lý request, giải mã dữ liệu, lập bảng kết quả, đọc/ghi và chạy công việc nền. **Garbage collector** thu hồi vùng nhớ không còn được tham chiếu. Một số pha GC yêu cầu **stop-the-world**: application threads của JVM bị tạm dừng trong khoảng thời gian đó. Những pha khác có thể chạy **concurrently**, không đồng nghĩa node bị dừng toàn bộ trong suốt pha ấy.

| Dấu hiệu trong GC log | Ý nghĩa khái quát | Mối liên hệ với latency |
| --- | --- | --- |
| **Young GC / evacuation pause** | Thu hồi thế hệ trẻ, thường có đoạn STW. | Pause ngắn, thường xuyên có thể cộng vào p99 nếu dài hơn budget của request. |
| **Mixed collection** (với collector hỗ trợ) | Thu hồi thêm vùng già trong một số chu kỳ GC. | Cần xem pause distribution và heap sau GC. |
| **Full GC** | Vùng xử lý rộng hơn, có thể đi kèm pause lớn tùy collector/phiên bản. | Cần điều tra nếu xuất hiện cùng timeout hoặc lặp liên tục. |
| **Concurrent mark/cleanup** | Một phần công việc GC chạy song song với application threads. | Không quy toàn bộ duration của pha concurrent thành STW pause. |
| **Allocation failure / evacuation failure** | GC gặp áp lực cấp phát/di chuyển object. | Có thể gợi ý heap pressure hoặc tốc độ cấp phát cao. |
| **Heap after GC vẫn cao** | Nhiều object vẫn sống hoặc chưa được collector thu hồi. | Nên xem xu hướng, working set và nguyên nhân giữ object. |

### 5.2. Minh họa cách đọc một dòng GC log

~~~text
# Ví dụ GIẢ LẬP theo kiểu unified GC logging của JVM:
[2026-11-21T10:05:01.100+0000][info][gc,start] GC(420) Pause Young (Normal)
[2026-11-21T10:05:02.900+0000][info][gc] GC(420) Pause Young (Normal) 5G->3G(8G) 1800.000ms

# Những dữ liệu muốn lấy ra:
collector_phase  = Pause Young
pause_duration   = 1800 ms = 1.8 giây
heap_before      = 5 GiB (ví dụ ký hiệu minh họa)
heap_after       = 3 GiB
heap_capacity    = 8 GiB
gc_id            = 420
node             = N2
~~~

**Không suy rằng Cassandra “bị treo 1.8 giây vì thiếu heap” chỉ từ một lần GC.** Pause dài có thể chịu ảnh hưởng của collector, cấu hình heap, object graph, tốc độ cấp phát, CPU contention, cgroup throttling hoặc phần cứng. Cần thêm history và metrics.

### 5.3. Phân biệt heap với off-heap, OS page cache và bộ nhớ container

Cassandra còn sử dụng **off-heap/direct memory**, memory-mapped/index structures và **OS page cache**. Một JVM heap chưa đầy không chứng minh node không có memory pressure; ngược lại, hệ điều hành sử dụng RAM để cache không nhất thiết là rò rỉ heap.

Các tín hiệu nên quan sát cùng nhau:

- Used/committed/max heap, allocation rate và **heap sau GC**.
- GC pause count/total duration, max pause, p99 pause nếu có đủ mẫu.
- Process RSS, direct/off-heap, cgroup/container memory limit và OOM/throttling.
- CPU user/system/steal, run queue, disk page faults và disk I/O latency.
- Cấu hình collector, heap size, phiên bản JDK và Cassandra.

**Đừng sửa heap hoặc đổi collector ngay giữa sự cố chỉ vì thấy GC trong log.** Điều chỉnh JVM cần baseline, kiểm tra tương thích phiên bản và thử nghiệm có kiểm soát; heap quá lớn cũng có thể ảnh hưởng pause, còn heap quá nhỏ tăng tần suất GC.

### 5.4. Lệnh quan sát GC

~~~bash
# Dùng trên node được cấp quyền; đối chiếu cú pháp theo phiên bản.
nodetool gcstats

# Khi JDK/OS cho phép và PID đã được xác minh:
jcmd <cassandra-java-pid> GC.heap_info
~~~

`nodetool gcstats` cung cấp số liệu GC tổng hợp theo phiên bản, hữu ích để nhận ra hoạt động GC tăng. `jcmd` với lệnh đọc thông tin heap có thể hỗ trợ điều tra; **không tùy tiện chạy heap dump hay lệnh gây pause** trên production, vì có thể tốn dung lượng hoặc ảnh hưởng dịch vụ. Lệnh chứa `<cassandra-java-pid>` chỉ là placeholder, không được dán nguyên xi.

## 6. Đọc system.log: tìm dấu hiệu hỗ trợ hoặc bác bỏ giả thuyết GC

Trong Cassandra, lỗi request có thể xuất hiện từ nhiều lớp và log không nhất thiết ghi toàn bộ hành trình của request. Khi thấy latency tăng, nên hỏi **node nào, thao tác nào và thời điểm nào**.

| Nhóm sự kiện có thể gặp | Giả thuyết | Bằng chứng phải kiểm tra thêm |
| --- | --- | --- |
| **Timeouts / dropped messages / overloaded** | Một thread pool/replica không xử lý kịp. | `nodetool tpstats`, request rate, queue, GC, network và disk. |
| **GC/pause-related warnings** | JVM tạm dừng làm response trễ. | GC log: pause bắt đầu/kết thúc, duration và trùng với endpoint của query. |
| **Compaction/flush activity** | Disk I/O tranh tài nguyên read/write. | `compactionstats`, disk latency/IOPS, pending flush, SSTable count. |
| **Tombstone / large partition warnings** | Replica quét nhiều dữ liệu chết/partition quá lớn. | Query, `tablestats`, tracing, `tablehistograms` và partition model. |
| **Gossip / node down / topology** | Replica không khả dụng hoặc route thay đổi. | `status`, network latency, retries, CL và coordinator. |
| **Repair/streaming events** | Công việc đồng bộ tạo CPU/network/disk pressure. | `netstats`, repair logs, disk/network metrics. |
| **Filesystem errors / out-of-disk** | Write/flush/read path bị chặn hoặc thất bại. | `df`, disk latency, kernel/storage logs và volume thật. |

Ví dụ **giả lập** để minh họa cách suy luận:

~~~text
10:05:01.050 UTC  [N1] WARN Request timeout for a read
10:05:01.200 UTC  [N2] INFO Compaction started
10:05:01.250 UTC  [N2] GC pause begins
10:05:03.050 UTC  [N2] GC pause ends (1800 ms)
10:05:03.100 UTC  [N1] WARN Replica response arrived late
~~~

Dù GC gần request timeout, **thứ tự ở bảng trên còn phải được xác thực**: timestamp có đồng bộ không? N1 có thực sự chờ N2 hay không? Compaction đã đẩy disk latency lên trước khi GC bắt đầu chưa? Có thể **GC và latency đều là hậu quả** của một đợt cấp phát/compaction nặng.

**Không lấy severity làm thước đo duy nhất.** Có hệ thống ghi thông tin quan trọng ở `INFO` hoặc `WARN`, trong khi client p99 đã tăng trước khi server ghi bất kỳ `ERROR` nào.

## 7. Tương quan log với metric Cassandra

### 7.1. Bộ lệnh kiểm tra từ một node

Trong lab/staging hoặc theo quyền vận hành production:

~~~bash
nodetool status
nodetool info
nodetool gcstats
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool proxyhistograms
nodetool tablestats telemetry_diag.events_by_device_day
nodetool tablehistograms telemetry_diag events_by_device_day
~~~

Tên lệnh, đối số và kết quả chi tiết **phụ thuộc phiên bản**. Nếu công cụ của cluster có cú pháp khác, kiểm tra `nodetool help <command>` trước khi dùng.

| Lệnh/nhóm chỉ số | Tìm gì? | Phân biệt với GC ra sao? |
| --- | --- | --- |
| `gcstats` và GC metrics | Tần suất/duration GC tăng có trùng sự cố? | Nếu GC phẳng nhưng disk latency tăng, ưu tiên giả thuyết I/O. |
| `tpstats` | Pending/blocked tasks và dropped messages theo thread pool. | Queue cao có thể do GC, overload, disk hoặc mạng; cần timeline. |
| `compactionstats` | Compaction active/pending và backlog. | I/O contention có thể làm read chậm ngay cả khi không có STW dài. |
| `netstats` | Streaming/handoff liên quan topology/repair. | WAN/network bão hòa có thể gây timeout dù JVM vẫn hoạt động. |
| `proxyhistograms` | Latency phân phối đo ở phía coordinator theo chức năng lệnh. | Có thể đối chiếu với client latency, nhưng không phải cùng thời điểm/mẫu hoàn toàn. |
| `tablehistograms` | Phân phối kích thước/độ trễ cấp bảng theo công cụ. | Nếu chỉ một bảng chậm và tombstone dày, không quy ngay cho toàn JVM. |
| `tablestats` | SSTable count, dung lượng, partition/tombstone metrics, read/write stats. | Dữ liệu cũ/tombstone và chồng lấn SSTable có thể tăng read work. |
| `status` | Node/DC/rack nào up/down/joining. | CL có thể phải chờ replica bị lỗi hoặc chịu phân bố tải bất thường. |

Các số liệu `nodetool` có thể là **tổng từ khi node khởi động, giá trị gần thời điểm gọi hoặc histogram tích lũy**, tùy chỉ số và phiên bản. Không được lấy chênh lệch hai counter làm “request cuối cùng” khi không biết ý nghĩa. Với histogram, phải xem cửa sổ mẫu, số request và có reset/restart hay không.

### 7.2. Dashboard tối thiểu để nhìn quan hệ nhân quả

Nên hiển thị trên **cùng trục thời gian UTC**:

1. Request rate, p50/p95/p99, timeout/unavailable/errors **phía ứng dụng** theo query name/CL.
2. Coordinator read/write latency, timeout và dropped messages **phía Cassandra**.
3. GC pause count, max pause, tổng thời gian pause và heap after GC **theo node**.
4. CPU/GC CPU, memory RSS, cgroup throttling, disk await/queue depth, free disk và network latency **theo node/volume**.
5. Pending/active compaction, flush, repair/streaming, hints và SSTable/tombstone signals.
6. Node membership, DC/rack và các sự kiện deploy, backup, thay topology.

**Không lấy trung bình p99 của nhiều node** để làm p99 toàn cluster. Nếu có histogram buckets phù hợp, gộp dữ liệu phân phối theo đúng toán học rồi tính phân vị; nếu không, hiển thị p99 theo node hoặc thêm chú thích giới hạn. Tránh label có `partition_key`, `request_uuid` hoặc `trace_id` trên metrics diện rộng vì cardinality quá cao và có thể lộ dữ liệu.

## 8. Bốn giả thuyết hay gặp và cách bác bỏ

### 8.1. Giả thuyết A — GC pause kéo dài

**Dấu hiệu ủng hộ:** p99/timeout spike cùng lúc JVM N2 có STW pause lớn; trên N2, request queue tích tụ và trả lời tăng trở lại ngay sau pause; trace/client cho thấy request đang chờ N2.

**Điều cần bác bỏ:** liệu disk/CPU/network đã nghẽn trước? Có phải GC concurrent chứ không phải STW? N2 có tham gia đúng partition và consistency level của request không?

**Hành động:** tìm nguồn allocation/heap pressure, kiểm tra cấu hình JVM/GC, batch/row size và traffic, nhưng chỉ tuning qua môi trường thử nghiệm với baseline.

### 8.2. Giả thuyết B — Compaction hoặc disk I/O làm read chậm

**Dấu hiệu ủng hộ:** disk latency và I/O queue tăng trước p99; `compactionstats` có backlog; system log cho thấy compaction/flush nặng; GC pause không tăng tương ứng.

**Điều cần bác bỏ:** throughput đọc/ghi có tăng đột biến, ổ đĩa lỗi, snapshot/streaming tạo thêm I/O hay không? Một compaction bắt đầu đúng mốc chưa chắc là thủ phạm nếu disk vẫn rảnh.

**Hành động:** kiểm tra capacity và headroom, tốc độ compaction, chiến lược SSTable, partition size, concurrent maintenance và lịch tải; không ép major compaction lúc disk gần đầy.

### 8.3. Giả thuyết C — Tombstone scan hoặc partition quá lớn

**Dấu hiệu ủng hộ:** chỉ một nhóm query/bảng chậm; có tombstone warnings, nhiều SSTable/partition lớn; tracing cho thấy phải quét nhiều dữ liệu hơn số hàng trả về.

**Điều cần bác bỏ:** có index/cache miss, phân phối dữ liệu lệch/hot partition hoặc đọc token range thay vì exact partition không? GC pause là hậu quả allocation của query nặng hay nguyên nhân độc lập?

**Hành động:** thiết kế partition key/bucketing theo truy vấn, giới hạn clustering range, TTL/delete, đo tombstone và compaction. `LIMIT 10` **không** đảm bảo replica chỉ duyệt 10 item trên disk.

### 8.4. Giả thuyết D — Replica/mạng hoặc quorum không đủ

**Dấu hiệu ủng hộ:** timeout tập trung ở DC/rack/node nhất định, network retransmit hoặc node flapping, gossip events, `LOCAL_ONE` và `LOCAL_QUORUM` có độ trễ rất khác nhau.

**Điều cần bác bỏ:** có thể là replica chậm vì GC hoặc disk chứ không phải mạng; tracer đã chọn replica nào? CL `LOCAL_QUORUM` với RF = 2 cần **cả hai** replica tại DC đó, khác RF = 3 cần hai trong ba.

**Hành động:** điều tra node/network/driver routing, xác nhận RF/CL và tình trạng repair; **không hạ CL ngay** mà chưa hiểu tác động tới tính nhất quán và độ bền kỳ vọng.

| Tín hiệu nổi bật | GC | Disk/compaction | Tombstone/partition | Mạng/replica |
| --- | --- | --- | --- | --- |
| STW pause dài trùng spike | Mạnh | Có thể là yếu tố phụ | Có thể do allocation | Không đặc hiệu |
| Disk await/queue tăng trước spike | Không đặc hiệu | Mạnh | Có thể đi kèm | Không đặc hiệu |
| Tombstones scanned tăng ở một bảng | Không đặc hiệu | Có thể cùng xảy ra | Mạnh | Không đặc hiệu |
| Lỗi tập trung một rack/DC | Có thể nếu JVM ở rack đó | Có thể nếu ổ tại rack đó | Ít đặc hiệu | Mạnh |
| p99 giảm ngay khi node khỏi pause | Mạnh hơn nếu có trace xác nhận | Vẫn cần đối chiếu | Vẫn cần đối chiếu | Vẫn cần đối chiếu |

Bảng mang tính **định hướng điều tra**, không phải bộ chẩn đoán tự động.

## 9. CQL tracing: soi một truy vấn, không bật tracing toàn traffic

### 9.1. Bảng lab theo mô hình truy vấn Cassandra

Ví dụ cụm lab có DC `dc1` với ít nhất ba replica hoạt động:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_diag
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_diag.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  quality text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`(device_id, event_day)` là **partition key kép**: xác định token/replica; `event_time, event_id` là clustering columns. Truy vấn theo một partition và khoảng thời gian thường phù hợp thiết kế này hơn việc quét tất cả partition.

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_diag.events_by_device_day
  (device_id, event_day, event_time, event_id, reading, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:05:00Z',
   123e4567-e89b-42d3-a456-426614174001, 20.75, 'OK');

INSERT INTO telemetry_diag.events_by_device_day
  (device_id, event_day, event_time, event_id, reading, quality)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:10:00Z',
   123e4567-e89b-42d3-a456-426614174002, 21.10, 'OK');
~~~

### 9.2. Bật trace có chọn lọc trong `cqlsh`

~~~sql
TRACING ON;

SELECT event_time, event_id, reading
FROM telemetry_diag.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 20;

TRACING OFF;
~~~

`CONSISTENCY` và `TRACING` là **lệnh của cqlsh**, không phải phần của một CQL statement được driver gửi nguyên văn. Sau khi chạy truy vấn, cqlsh có thể hiển thị **Tracing session** cùng các event, host và elapsed time, tùy phiên bản/trạng thái.

Ví dụ các pha có thể gặp, **không phải output cố định**:

~~~text
Tracing session: <trace-session-uuid>
Activity                                  Source     Elapsed
Execute CQL3 query                        N1         0 us
Sending READ message                       N1        50 us
Replica begins read                        N2       450 us
Reading from SSTables / merging results     N2       900 us
Sending response                           N2      1500 us
Request complete                           N1      2000 us
~~~

**Cách đọc an toàn:**

1. `Source` cho biết node nào tạo event; không phải mọi event đến từ coordinator.
2. `Elapsed` thường tính từ mốc của trace session và có thể ở **microsecond**, không đồng nhất với millisecond của dashboard client.
3. Số sự kiện không đồng nghĩa toàn bộ wait time đã được instrument; việc không thấy event về GC **không chứng minh GC không xảy ra**.
4. Để ghép nhiều node, phải đối chiếu session id, timestamp/elapsed, clock skew và tracing semantics của phiên bản.
5. Bản ghi tracing nằm trong cơ chế lưu vết của Cassandra với **retention/TTL và overhead**; không coi nó là nơi lưu vĩnh viễn mọi request.

### 9.3. Có thể tra trace session bằng CQL không?

Khi môi trường cho phép và trace chưa hết hạn, các bảng hệ thống như `system_traces.sessions` và `system_traces.events` có thể chứa thông tin phiên tracing theo phiên bản:

~~~sql
-- Thay UUID bên dưới bằng session ID thật do cqlsh/driver cung cấp.
SELECT *
FROM system_traces.sessions
WHERE session_id = 123e4567-e89b-42d3-a456-426614174099;

SELECT *
FROM system_traces.events
WHERE session_id = 123e4567-e89b-42d3-a456-426614174099;
~~~

Khi trace không tồn tại, có thể do TTL, tracing không bật/không ghi thành công, request timeout, quyền truy cập hoặc khác biệt phiên bản. Không suy ra truy vấn không từng xảy ra. **Tránh bật tracing cho tất cả request production** vì trace bản thân tạo thêm mutation, I/O và công việc nền, có thể làm sự cố nặng hơn.

## 10. Java Driver 4.x: đo client latency và lưu trace id một cách có chọn lọc

Ứng dụng Java nên gắn **tên truy vấn ổn định** (không gắn toàn bộ CQL chứa dữ liệu nhạy cảm), đo latency bằng đồng hồ **monotonic** và ghi timestamp UTC để ghép với log server. Ví dụ sử dụng Apache Cassandra Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class TraceSlowRead {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement select = session.prepare(
                    "SELECT event_time, event_id, reading " +
                    "FROM telemetry_diag.events_by_device_day " +
                    "WHERE device_id = ? AND event_day = ? LIMIT 20");

            // CHỈ trong lab hoặc request đã được chọn để chẩn đoán.
            // Không bật tracing liên tục cho mọi traffic production.
            BoundStatement read = select.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setTracing(true);

            Instant startedUtc = Instant.now();
            long startNanos = System.nanoTime();

            try {
                ResultSet rs = session.execute(read);
                ExecutionInfo execution = rs.getExecutionInfo();
                UUID traceId = execution.getTracingId();
                int rows = 0;
                for (Row row : rs) {
                    rows++;
                }
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - startNanos);
                System.out.println("query=events_by_device_day"
                        + " started_utc=" + startedUtc
                        + " cl=LOCAL_QUORUM"
                        + " status=success"
                        + " elapsed_ms=" + elapsedMs
                        + " rows=" + rows
                        + " trace_id=" + traceId);
            } catch (RuntimeException ex) {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - startNanos);
                System.err.println("query=events_by_device_day"
                        + " started_utc=" + startedUtc
                        + " cl=LOCAL_QUORUM"
                        + " status=failure"
                        + " elapsed_ms=" + elapsedMs
                        + " exception=" + ex.getClass().getSimpleName());
                throw ex;
            }
        }
    }
}
~~~

**Đọc kết quả đúng cách:**

- `System.nanoTime()` đo **duration**, không phải timestamp UTC. `Instant.now()` cho mốc có thể ghép log; giữ riêng hai khái niệm.
- Vòng `for (Row row : rs)` có thể fetch thêm page (nếu nhiều dữ liệu) và làm phép đo gồm **client iteration**; muốn đo riêng response đầu hoặc từng page cần instrument tách biệt.
- `ExecutionInfo.getTracingId()` có thể trả `null` nếu request không có trace id. Thông tin này thường gắn với execution/page liên quan; không mặc định một ID đại diện toàn bộ chuỗi paging.
- Khi request bị timeout, client có thể không nhận trace id dù phía server đã xử lý một phần. Timeout **không chứng minh request chưa được thực hiện**.
- Trong production, nên ghi structured log hoặc metrics bằng thư viện logging/observability của ứng dụng, gắn `query_name`, `status`, CL, DC và một request/correlation ID do ứng dụng tạo. Không đưa **UUID của mọi request** thành label Prometheus vì cardinality quá cao.
- `127.0.0.1` và `dc1` chỉ là cấu hình lab. Hệ thống thật phải xác định đúng contact points, local DC, TLS/authentication và timeout/retry policy.

**Cảnh báo:** snippet dùng `setTracing(true)` có chủ đích chỉ cho request chẩn đoán. Nếu cần đo lưu lượng thường xuyên, dựa vào metrics và **sampling** thay vì trace mọi query.

## 11. Case study: dựng lại một sự cố từ bốn loại bằng chứng

### 11.1. Dữ liệu thu thập

Giả sử từ 10:00 tới 10:15 UTC có 4.000 read/s vào `telemetry_diag.events_by_device_day`, RF = 3 tại dc1, CL = `LOCAL_QUORUM`.

| Nguồn | Bằng chứng giả lập |
| --- | --- |
| Application metrics | p50 = 24 ms, p99 tăng từ 60 ms lên 2.2 giây lúc 10:05; ReadTimeout tăng. |
| GC log N2 | Một **STW pause 1.8 giây** bắt đầu 10:05:01 UTC; heap sau GC giảm rõ. |
| Cassandra `tpstats` N2 | Queue đọc tăng rồi giảm sau khi JVM tiếp tục. |
| CQL tracing | Một số request chậm cho thấy phản hồi từ N2 chậm trong khoảng thời gian ấy. |
| Disk metrics N2 | Disk await tương đối ổn định, không có đỉnh I/O tương ứng. |
| GC log N1 và N3 | Không có pause dài trùng thời điểm. |

### 11.2. Lập giả thuyết và kết luận có điều kiện

**Giả thuyết có sức nặng:** GC STW trên N2 góp phần làm chậm phản hồi replica, khiến một phần read cần N2 bị ảnh hưởng; p99 tăng khi các request chờ N2 và giảm khi N2 tiếp tục xử lý.

**Chưa được phép kết luận:** “100% timeout đều do GC”, “GC bị kích hoạt bởi memtable” hoặc “chỉ tăng heap sẽ chữa được”. Để tiến thêm cần kiểm tra allocation rate, heap sau GC qua nhiều lần, loại collector, CPU throttling và workload tại N2.

Một điểm thú vị: nếu `LOCAL_QUORUM` chỉ cần hai replica trong ba và coordinator nhận đủ phản hồi nhanh từ N1/N3, **không phải mọi request đều phải chờ N2**. Hành vi chọn replica, speculative retry, tính sẵn sàng từng node và thời điểm quorum đủ có thể giải thích vì sao **p50 ổn định nhưng p99 tăng**.

### 11.3. Trường hợp tương quan đánh lừa

Thay dữ kiện:

- `GC log N2` chỉ có nhiều **concurrent marking phases**, STW dưới 20 ms.
- Disk await trên N2 tăng tới hàng trăm ms **từ trước 10:05**, compaction/streaming cùng chạy.
- Tracing cho thấy khoảng chờ đọc SSTable lớn, heap sau GC ổn định.

Lúc này nên ưu tiên điều tra **I/O contention và compaction**. Gán nguyên nhân cho GC chỉ vì trong log có chữ `GC` là sai: **concurrent phase duration không phải pause toàn bộ JVM**, và disk I/O có thể vừa làm read chậm vừa gián tiếp làm allocation/GC biến động.

## 12. Quy trình chẩn đoán trên production theo thứ tự ít rủi ro

### Bước 1 — Xác định triệu chứng và phạm vi

Ghi rõ **UTC start/end**, ứng dụng/query name, CL, keyspace/table, DC/rack, node chịu ảnh hưởng, p50/p95/p99, request rate và loại lỗi. Phân biệt **read vs write** và **exact partition read vs scan**. Không kết luận một node có vấn đề từ dashboard đã gộp toàn cluster.

### Bước 2 — Kiểm tra sức khỏe và thay đổi gần thời điểm sự cố

Xem node up/down, deploy ứng dụng, thay cấu hình, streaming/repair, backup, compaction, disk space, CPU và network. Nếu cả cluster đồng loạt p99 tăng, điều tra các tài nguyên chung; nếu chỉ một rack/node, ưu tiên lỗi cục bộ hoặc traffic lệch.

### Bước 3 — Thu thập log ở **đúng node** và chuẩn hóa thời gian

Lưu khoảng trước/sau sự cố từ system log, GC log và application log. Ghi phiên bản JDK/Cassandra, timezone, NTP skew và mốc uptime nếu GC log không có wall-clock. Tránh lọc mất ngữ cảnh do chỉ xem `ERROR`.

### Bước 4 — Đặt GC cạnh latency và queue

Tìm **STW pause thật sự** và duration tương ứng, heap before/after, GC count. Đồng thời so `tpstats`, disk I/O, CPU và coordinator/replica latency. **Nếu GC không trùng request hoặc pause rất ngắn**, đừng đổ lỗi cho GC.

### Bước 5 — Lấy tracing có chọn lọc

Chọn vài query đại diện trên lab hoặc ở production với sampling/permission được duyệt. Đối chiếu trace id, query name, coordinator, replica và event duration. Tracing tạo overhead nên **không bật toàn traffic** khi hệ thống đang quá tải.

### Bước 6 — Kiểm chứng giả thuyết bằng dấu hiệu bác bỏ

Viết tối thiểu **hai giả thuyết cạnh tranh** và bằng chứng có thể bác bỏ từng giả thuyết, ví dụ:

| Giả thuyết | Nếu đúng thường thấy | Bằng chứng làm giả thuyết yếu đi |
| --- | --- | --- |
| GC làm request chậm | Pause overlap, queue tích tụ, trace chờ đúng node. | GC pause nhỏ/khác node, disk/network đã nghẽn trước. |
| Disk/compaction làm request chậm | Disk await và compaction backlog trùng spike. | Disk latency ổn, chỉ JVM N2 có STW lớn. |
| Tombstone scan gây latency | Chỉ một bảng/query chậm, scan nhiều marker/hàng cũ. | Nhiều bảng cùng chậm, dữ liệu đọc nhỏ, không có tombstone pressure. |
| Replica/mạng gây timeout | Lỗi theo DC/rack, retransmit, node flapping, CL không đủ. | Các replica khỏe, slowdown bám theo một batch query hoặc JVM pause. |

### Bước 7 — Khắc phục đúng nguyên nhân và xác minh sau can thiệp

Đánh giá rủi ro của hành động: giảm tải truy vấn, sửa hot partition/schema, điều chỉnh compaction schedule, giải quyết disk/network, bảo trì replica hoặc tuning JVM **theo runbook/kiểm thử**. Không chạy major compaction, heap dump, tăng concurrency hoặc hạ CL tùy tiện khi cluster đang căng.

Sau thay đổi, đo **cùng metrics trước–sau** và ít nhất vài chu kỳ hoạt động: p99, error rate, throughput, pause GC, heap sau GC, disk/queue và client impact. Ghi lại điều kiện chưa chắc chắn trong báo cáo thay vì khẳng định quan hệ nhân quả quá mức.

## 13. Dashboard và alert: nên đo gì liên tục?

| Nhóm | Đo/alert gợi ý | Tại sao? |
| --- | --- | --- |
| **Client SLO** | p95/p99 latency, timeout rate, request rate theo query name + CL. | Phát hiện ảnh hưởng người dùng trước khi tìm nguyên nhân. |
| **Cassandra coordinator** | Read/write/range latency, timeouts, unavailable, dropped messages. | Phân biệt lỗi request xử lý phía server với thời gian ứng dụng. |
| **JVM GC** | STW pause max/p99, total pause time per minute, heap after GC, allocation rate. | Xác định tail latency có liên quan JVM pause không. |
| **Thread pools** | Pending/blocked/dropped tasks; pool read/write/flush theo phiên bản. | Phát hiện queue tích tụ và khả năng nghẽn. |
| **SSTable/read path** | SSTable count, partition size, tombstone scanned, cache misses. | Tìm query quá nặng/đọc nhiều version. |
| **Disk & maintenance** | Disk latency, IOPS, free space, compaction/flush/repair/streaming backlog. | Phân biệt sự cố I/O với GC và dự đoán rủi ro thiếu disk. |
| **Replica/network** | Node membership, cross-DC latency, packet loss, failed repairs/hints. | Thấy replica không nhận/trả lời mutation đúng hạn. |

Không có một ngưỡng GC pause phổ quát áp dụng cho mọi hệ thống. Ví dụ API có **SLO 200 ms** có thể bị ảnh hưởng bởi pause 300 ms, trong khi batch workload deadline hàng phút thì khác. Cảnh báo nên dựa vào **latency budget, baseline, độ dài pause, tần suất và mức ảnh hưởng**, không chỉ `GC happened`.

Một báo cáo sự cố tối thiểu nên có:

~~~text
Incident ID:
UTC start/end:
Service, query name, CL:
Affected DC/rack/node:
Client p50/p95/p99, throughput, timeout:
Server latency/queue:
GC phase, STW duration, heap before/after:
Disk/compaction/repair/network context:
Tracing session ID và replica involved (nếu có):
Timeline đã chuẩn hóa + clock uncertainty:
Primary hypothesis / alternatives / contradictory evidence:
Mitigation, result, follow-up và owner:
~~~

## 14. Những kết luận hấp tấp cần tránh

| Nhận định | Đúng/sai | Lý do |
| --- | --- | --- |
| “Thấy GC log cùng phút p99 tăng thì GC chắc chắn là nguyên nhân.” | **Sai** | Cần chứng minh pause liên quan request và loại trừ disk/network/query. |
| “Concurrent GC chạy 5 giây nên JVM đứng im 5 giây.” | **Sai** | Concurrent phase không đồng nghĩa STW suốt thời lượng. |
| “CPU trung bình thấp nghĩa không thể có GC pause.” | **Sai** | STW ngắn có thể làm p99 spike dù average CPU vẫn vừa phải. |
| “Một dòng `ERROR` của coordinator đủ để biết replica nào chậm.” | **Sai** | Cần trace, endpoint, CL và timeline các node. |
| “`LOCAL_QUORUM` yêu cầu mọi replica tại DC.” | **Sai** | RF = 3 cần 2 ACK; RF = 2 mới cần 2/2. |
| “p99 toàn cluster = trung bình p99 của các node.” | **Sai** | Phân vị không cộng/trung bình theo cách ấy. |
| “`LIMIT 10` nghĩa Cassandra chỉ đọc 10 hàng từ SSTable.” | **Sai** | Tombstone và version cũ có thể làm scan nhiều hơn. |
| “Tracing toàn bộ request là cách nhanh nhất để debug.” | **Sai** | Tracing tạo thêm I/O và dữ liệu, có thể khuếch đại sự cố. |
| “GC log từ JVM uptime có thể ghép thẳng với giờ UTC.” | **Sai** | Cần mốc JVM start hoặc wall-clock decorator và kiểm tra clock. |
| “Write timeout nghĩa không replica nào đã ghi.” | **Sai** | Một số replica có thể đã áp dụng mutation; client không đủ ACK. |
| “Có timeline UTC và giả thuyết có thể bác bỏ giúp chẩn đoán đáng tin hơn.” | **Đúng** | Giảm nhầm lẫn do clock skew và confirmation bias. |

## 15. Bài tập tự kiểm tra có đáp án

**Bài 1.** Application p99 tăng từ 50 ms lên 1.5 giây lúc 10:00 UTC. GC log của node N2 có pha `Concurrent Mark` kéo dài 4 giây, nhưng STW pause lớn nhất chỉ 10 ms. Có đủ bằng chứng quy lỗi cho GC không?

**Đáp án:** **Không.** Pha concurrent không phải toàn bộ thời gian JVM dừng. Cần kiểm tra CPU/disk/queue/trace và những STW pause thật sự trùng request.

**Bài 2.** Một node in GC timestamp dạng `[12345.678s]`, application log in `2026-11-21T10:05:01Z`. Có thể so sánh trực tiếp hai con số đó?

**Đáp án:** **Không.** GC timestamp này là JVM uptime, phải có mốc start và sai số đồng hồ để chuyển về wall-clock/UTC.

**Bài 3.** Cluster RF = 3 ở dc1, read `LOCAL_QUORUM` dùng hai phản hồi replica. N2 có STW 2 giây, nhưng p50 vẫn tốt và một phần p99 tăng. Tại sao?

**Đáp án:** Không phải mọi request đều phải chờ N2: coordinator có thể chọn/nhận nhanh hai replica khác trong nhiều request. Những request cần N2 hoặc gặp chậm ở coordinator/replica liên quan có thể thuộc phần đuôi phân phối.

**Bài 4.** System log báo dropped messages, `tpstats` cho pending read tasks tăng. Có thể kết luận nguyên nhân gốc là JVM GC?

**Đáp án:** **Chưa.** Queue/dropped messages là hậu quả của nhiều loại nghẽn: GC, disk, hot partition, traffic spike hoặc network. Cần ghép GC log, OS metrics, tracing và request rate.

**Bài 5.** Hai node có p99 lần lượt 100 ms và 1.000 ms, số request là 9.900 và 100. p99 toàn cluster có bằng `(100+1000)/2 = 550 ms` không?

**Đáp án:** **Không.** p99 của tập hợp phụ thuộc toàn bộ phân phối và trọng số request; không thể lấy trung bình p99 của node. Cần histogram/tập dữ liệu tổng hợp đúng cách.

**Bài 6.** Tracing một câu `SELECT` thấy phần đọc SSTable mất lâu, GC pause trên node ổn định. Nên kiểm tra thêm điều gì?

**Đáp án:** Disk await/IOPS, compaction/streaming, SSTable count, tombstone scan, partition size, cache và kiểu truy vấn (exact partition hay scan).

**Bài 7.** Khi p99 đang cao, một nhóm định bật `TRACING ON` cho mọi request của mọi ứng dụng. Rủi ro là gì?

**Đáp án:** Tracing tự tạo thêm mutation, I/O, storage và xử lý, có thể làm hệ thống quá tải thêm. Chỉ chọn mẫu nhỏ có kiểm soát, ưu tiên metrics/log trước.

**Bài 8.** Sau khi điều chỉnh lịch compaction, p99 giảm; có thể nói compaction là nguyên nhân gốc 100% không?

**Đáp án:** **Chưa chắc.** Traffic, GC hoặc node health cũng có thể thay đổi đồng thời. Cần so các chỉ số trước–sau, timeline, nhóm đối chứng nếu khả thi và bằng chứng bác bỏ giả thuyết khác.

## 16. Sơ đồ quyết định khi độ trễ tăng

~~~mermaid
flowchart TD
    A["Cassandra API p99/timeout tăng"] --> B["Xác định query/CL, UTC window, node/DC"]
    B --> C["Ghép client metrics, system log, GC log và OS metrics"]
    C --> D{"Có STW GC pause dài trùng request/replica?"}
    D -->|Có| E["Kiểm tra queue, heap, allocation và nguyên nhân pause"]
    D -->|Không / chưa đủ| F["Đo disk, compaction, tombstone và network"]
    E --> G{"Tracing/metrics xác nhận node chậm nằm trên request path?"}
    F --> G
    G -->|Có| H["Ưu tiên giả thuyết được nhiều nguồn hỗ trợ"]
    G -->|Không| I["Tìm bằng chứng khác, kiểm tra clock skew"]
    I --> C
    H --> J["Mitigation theo runbook, tránh thao tác gây tải mạnh"]
    J --> K["Đo lại p99, timeout, GC, disk, queue và ghi kết luận có điều kiện"]
~~~

**Ghi nhớ:** system log cho biết **sự kiện gì xảy ra**, GC log giúp xác định **JVM có dừng trong bao lâu**, còn metrics/tracing cho biết **request nào và phần xử lý nào bị chậm**. Chỉ khi ghép các nguồn vào **cùng timeline có kiểm soát timezone/clock skew**, liên hệ tới **đúng coordinator/replica và CL**, rồi thử bác bỏ những giả thuyết cạnh tranh, ta mới có cơ sở kết luận GC, disk, tombstone, compaction hay network đã góp phần làm tăng độ trễ. Mục tiêu của chẩn đoán là **khôi phục dịch vụ dựa trên bằng chứng**, không phải tìm một dòng log để đổ lỗi.

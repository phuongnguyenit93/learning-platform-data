# Thay đổi có kiểm soát, mức cơ sở và điều kiện quay lại cấu hình cũ trong Apache Cassandra

> **Chương:** Tối ưu tài nguyên  
> **Trọng tâm:** Thiết kế một thay đổi tài nguyên có thể kiểm chứng và quay lại an toàn trên Apache Cassandra: xây dựng baseline, xác định giả thuyết, chỉnh một tham số có phạm vi rõ ràng, canary/ramp-up, theo dõi nhiều lớp, đặt rollback gates và đánh giá sau triển khai. Ví dụ tham chiếu Cassandra 4.1/5.0 và Java Driver 4.x; luôn đối chiếu cú pháp/config với phiên bản đang vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **baseline** bằng dữ liệu trước thay đổi về SLO, workload, CPU, heap/GC, disk, network, memtable, compaction và mức nhất quán đọc/ghi.
2. Viết một **giả thuyết tuning kiểm chứng được**, chẳng hạn tăng giới hạn throughput compaction liệu có giảm backlog mà không làm tail latency xấu đi.
3. Phân loại thao tác nào là **runtime knob**, thao tác nào cần **rolling restart**, và thao tác nào kéo theo **thay đổi dữ liệu/ring** nên không thể rollback chỉ bằng sửa file cấu hình.
4. Xây dựng kế hoạch **canary → đánh giá → mở rộng → giám sát**, tránh chỉnh đồng thời nhiều biến khiến không biết nguyên nhân cải thiện/hồi quy.
5. Thiết lập **ngưỡng dừng và rollback** đo được bằng p95/p99, timeout, availability, disk headroom, backlog, GC và replica health.
6. Thực hiện lab quan sát trước–sau thay đổi giới hạn compaction trên node thử nghiệm, lưu lại giá trị cũ, hoàn nguyên và xác nhận hoàn nguyên thật sự có hiệu lực.
7. Thiết kế theo dõi từ Java Driver, tính tới retry, CL, request family, schema/partition key và tác động phân tán giữa các replica.

**Ý tưởng cốt lõi:** Tuning không phải phép thử “đặt số mới rồi nhìn thấy một metric giảm”. Một lần tuning được coi là tốt khi **workload và kết quả dữ liệu tương đương**, giảm nút thắt mục tiêu, không gây suy giảm tính nhất quán/khả dụng và có cách quay lại đã thử trước.

## 2. Vì sao Cassandra cần thay đổi có kiểm soát?

Trong Cassandra, một request trải qua nhiều thành phần có tài nguyên chia sẻ:

~~~text
Ứng dụng Java / CQL request
          |
          v
   Driver load balancing
          |
      Coordinator
          |
      Replica set
      /     |     \
    Node A Node B Node C
      |      |      |
    Commit log + memtable
      |      |      |
    Flush -> SSTable
      |      |      |
    Compaction / repair
      |      |      |
   CPU, memory, disk, network

      SLO user, CL, RF
       bao trùm toàn bộ
~~~

Một chỉnh sửa trên một node hoặc một thành phần có thể ảnh hưởng nhiều thành phần khác:

- **Tăng compaction throughput** có thể giảm pending compaction nhưng làm disk I/O cạnh tranh với read/flush, tăng p99.
- **Tăng số flush writers** có thể giúp giải phóng memtable nhưng tạo nhiều SSTable, tăng việc compaction.
- **Tăng JVM heap** có thể tránh một số áp lực cấp phát nhưng làm GC pause thay đổi; thiếu RAM ngoài heap hoặc page cache vẫn khiến disk reads chậm.
- **Tăng retry/speculative execution của Java Driver** có thể cải thiện một số request đuôi nhưng tăng số request thật đến coordinator/replica, tạo vòng quá tải.
- **Giảm consistency level** có thể làm latency đẹp hơn nhưng thay đổi hợp đồng dữ liệu, nguy cơ stale reads và khả năng ghi không đạt yêu cầu; không được tính là tối ưu tài nguyên tương đương.
- **Thêm node hoặc đổi RF** thay đổi replica ownership/streaming, không phải thay một knob độc lập trên một máy.

### 2.1. Ba kết quả rất khác nhau

| Kết quả | Ví dụ | Có phải tuning thành công? |
|---|---|---|
| **Nhanh hơn và an toàn hơn** | p99 read giảm, disk wait và timeout không tăng, dữ liệu đúng | Có thể, nếu kết quả ổn định dưới workload tương đương |
| **Nhanh hơn nhưng rủi ro hơn** | p99 giảm vì hạ `LOCAL_QUORUM` xuống `ONE` | **Không**, nếu yêu cầu consistency ban đầu không cho phép |
| **Một metric đẹp hơn nhưng toàn hệ thống xấu đi** | Pending compaction giảm, write timeout và GC tăng | **Không**, chưa đạt các điều kiện chấp nhận |

Quy tắc thực hành: **xác định điều không được phép xấu đi trước khi mở thay đổi**, không đặt điều kiện rollback sau khi sự cố đã xảy ra.

### 2.2. Tuning khác capacity expansion và data migration

- **Tuning:** thay một tham số hoặc chính sách chạy để cải thiện sử dụng tài nguyên trong cùng mô hình nghiệp vụ/topology.
- **Capacity expansion:** thêm node, disk hoặc nâng cấu hình máy; có thể cần bootstrap/streaming và metadata refresh của driver.
- **Data-model migration:** tạo bảng theo truy vấn, đổi partition key bằng bảng mới/backfill; có giai đoạn dual-write và rủi ro dữ liệu lệch.
- **Recovery:** sửa node/dữ liệu lỗi, repair/restore/replace; không nên gộp vào tuning thuần túy.

Một change request có thể bao gồm nhiều loại, nhưng phải **chia thành các bước riêng có checkpoint**. Nếu chỉnh compaction concurrency cùng lúc thay RF và rolling restart, kết quả rất khó quy nguyên nhân.

## 3. Baseline là gì và tại sao một snapshot không đủ?

**Baseline** là tập dữ liệu tham chiếu đại diện cho **hệ thống trước thay đổi**, bao gồm trạng thái workload, sức khỏe cluster, kết quả dữ liệu và các giới hạn chấp nhận. Baseline không phải một lệnh `nodetool status` hoặc con số CPU trung bình tại một thời điểm.

### 3.1. Năm chiều baseline bắt buộc

| Chiều | Thông tin phải lưu | Vì sao quan trọng? |
|---|---|---|
| **Workload** | QPS trung bình/peak, tỉ lệ đọc:ghi, query families, partition sizes, hot keys, batch jobs | Để so trước–sau trên tải tương đương |
| **SLO và kết quả** | p50/p95/p99, tỷ lệ timeout/unavailable, success rate, correctness, CL | Metric giảm không có ý nghĩa nếu request lỗi hoặc đọc sai |
| **Tài nguyên** | CPU, heap/off-heap, GC pause, disk IOPS/latency/free, network, queue | Biết ràng buộc vật lý đang giới hạn hệ thống |
| **Storage engine** | Memtable, flush pending, commit log, SSTable count, compaction pending, tombstones/read | Hiểu chuỗi nguyên nhân, không tối ưu nhầm lớp |
| **Cluster/config** | Cassandra version, node/DC/rack, RF, ring, replica health, configs, Java Driver | So sánh đúng topology và phục hồi giá trị cũ |

Với Cassandra có RF=3, mỗi write theo `LOCAL_QUORUM` có thể hoàn tất khi **hai replica đủ ACK** trong local DC. Nếu chỉ nhìn latency ứng dụng, một node thứ ba đang overload có thể bị che khuất. Baseline phải lấy **từng node**, không dùng mỗi số trung bình cluster.

### 3.2. Ba cửa sổ thời gian tham khảo

| Cửa sổ | Mục tiêu | Chú ý |
|---|---|---|
| **Steady state** | Tải bình thường sau warmup | Giữ trạng thái cache, không so cold với warm |
| **Business peak** | Kiểm headroom và tail latency thực | Cần đủ mẫu, giống ngày/giờ trong chu kỳ tương ứng |
| **Maintenance/batch** | Xem đợt repair, backup, streaming, bulk ingest | Không loại bỏ khỏi baseline nếu chúng là công việc vận hành lặp lại |

Một baseline thực dụng có thể dùng dữ liệu **7–14 ngày** để nhìn seasonality, cộng snapshot chi tiết **30–60 phút** ở peak cho phép so sánh canary. Đây là ví dụ lập kế hoạch, **không phải thời lượng Cassandra yêu cầu**. Một service tuần tự có thể cần chu kỳ dài hơn.

### 3.3. Baseline phải lưu mẫu và phạm vi

Ví dụ bảng **giả định** cho ba node trong một DC:

| Chỉ số | Node A | Node B | Node C | Diễn giải |
|---|---:|---:|---:|---|
| CPU p95 | 62% | 58% | 61% | Còn headroom vừa phải |
| Disk read p99 | 12 ms | 9 ms | 11 ms | Chưa thấy node lệch lớn |
| Disk free | 42% | 39% | 41% | Có chỗ cho SSTable tạm thời |
| Pending compactions | 18 | 20 | 17 | Backlog cần xem **xu hướng** |
| Pending flush | 0 | 1 | 0 | Chưa cho thấy flush bị nghẽn lâu |
| Write p99 ở ứng dụng | \- | \- | \- | 75 ms trên histogram ứng dụng |
| Timeout rate | \- | \- | \- | 0,05% tổng request trong peak |

Không suy “pending compactions=20 là quá tải” chỉ từ bảng này. Phải theo dõi liệu nó **đang tích lũy**, throughput compaction thực, disk latency và SLA; strategy STCS/LCS/TWCS/UCS cũng khiến pending estimate mang nghĩa khác nhau.

### 3.4. Những thứ cần cố định trước khi thử

- Cấu hình cũ: giá trị runtime thực, `cassandra.yaml`/JVM flags đang áp dụng, Java Driver config và phiên bản ứng dụng.
- Topology: số node, token ranges, RF theo DC, node down/joining/leaving, repaired ranges nếu liên quan.
- Tải: tỷ lệ read/write, QPS theo query family, payload/partition size, CL, page size, retries, background jobs.
- Trạng thái dữ liệu: các khóa sample và kết quả nghiệp vụ, TTL/tombstone nếu thao tác ảnh hưởng storage.
- Thời gian: UTC thống nhất, khoảng đo, tình trạng clock skew, lịch deploy/compaction/repair khác.

Một phiên bản cấu hình đã lưu trong Git **chưa chắc là giá trị runtime đang hiệu lực**: có tham số bị override bởi system property/JMX, một số thay đổi cần restart, và có tham số được đọc lại ở thời điểm khác. Khi có thể, đọc trực tiếp giá trị đang áp dụng bằng `nodetool get...` hoặc JMX.

## 4. Baseline theo tầng: ứng dụng, driver, coordinator, replica, hệ điều hành

### 4.1. Metric ở phía Java

| Nhóm | Nguồn | Cần theo dõi |
|---|---|---|
| **Business SLO** | API timer/histogram | p95/p99, error budget, timeout rate, user-visible failures |
| **Query family** | Repository instrumentation | Query count, QPS, duration, rows/pages, success/failure theo operation |
| **Driver session** | Java Driver 4.x metrics | `cql-requests`, `cql-client-timeouts`, connected nodes |
| **Driver node** | Java Driver metrics | `cql-messages`, pool in-flight/open connections, retries/connections |
| **Application runtime** | JVM/Micrometer/OpenTelemetry | CPU, heap, allocation, GC, thread pools, queue, network |

Một `session.execute()` hoặc `executeAsync()` có thể có retry/speculative execution; **logical application QPS không bằng physical coordinator attempts**. Theo dõi cả hai phía để tránh tình huống latency được cải thiện bề ngoài bằng cách tạo thêm tải cho Cassandra.

### 4.2. Metric phía Cassandra

| Nhóm | Dữ liệu cần ghi | Cách đọc |
|---|---|---|
| `ClientRequest.Read/Write.Latency` | Latency coordinator cho từng loại request | Không tự phân theo query family |
| `ClientRequest.Timeouts/Unavailables` | Rate lỗi theo node và loại request | Gắn với CL/RF và thời điểm node lỗi |
| `Table.ReadLatency/WriteLatency` | Độ trễ local table trên replica | Không giống end-to-end Java p99 |
| `Table.SSTablesPerReadHistogram` | Read amplification | Tăng có thể do compaction chậm hoặc query shape |
| `Table.TombstoneScannedHistogram` | Tombstones phải xem trong read path | Tác động từ DELETE/TTL/partition model |
| `Table.PendingFlushes` | Công việc flush đang tồn đọng | Đọc trend cùng flush pools, không kết luận từ một sample |
| `Table.PendingCompactions`, `Compaction.PendingTasks` | Ước lượng compaction backlog | Gauge/estimate; không phải ETA |
| `Compaction.BytesCompacted` | Byte đã xử lý | Lấy rate có xét restart/reset |
| `CommitLog.WaitingOnSegmentAllocation` | Áp lực phân bổ segment | Có thể liên quan flush hoặc commit log disk |
| `ThreadPools.*.PendingTasks/ActiveTasks` | Queue/worker ở từng stage | Chẩn đoán bottleneck read/write/flush/compaction |

Đọc các metric dưới JMX theo **node**, **keyspace**, **table**. Exporter có thể đổi tên/kiểu metric, do đó kiểm mapping trước khi viết alert. **Không lấy trung bình đơn giản các p99 node để có p99 cluster**: percentiles phải được gộp từ histogram hoặc dữ liệu phù hợp.

### 4.3. Baseline của hệ điều hành

~~~bash
# Chỉ là lệnh quan sát trên Linux; công cụ phụ thuộc hệ điều hành.
iostat -xz 1 5
vmstat 1 5
df -h
~~~

Disk latency, IOPS, throughput, queue depth, %iowait và CPU throttling cần được xem cùng dữ liệu Cassandra. **CPU idle cao không có nghĩa storage còn headroom**: hệ thống có thể chủ yếu chờ disk. `%util` cao trên SSD/NVMe không tự chứng minh saturation; đọc thêm latency và throughput.

### 4.4. Ghi log baseline bằng nodetool

~~~bash
# Lệnh chỉ đọc trạng thái; áp dụng theo quyền truy cập được cấp.
nodetool version
nodetool status
nodetool describecluster
nodetool info
nodetool tablestats
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool gcstats
nodetool getcompactionthroughput
~~~

`tablestats` có thể in rất nhiều bảng; trong production nên lọc vào các **table trọng yếu**, lưu output cùng mốc UTC và phiên bản. `nodetool status` trên một node chỉ là góc nhìn ring tại thời điểm đó, không xác nhận từng replica đã repair hoặc không có lỗi dữ liệu.

## 5. Từ triệu chứng sang giả thuyết có thể bác bỏ

Trước khi đổi tham số, bắt buộc diễn đạt theo cấu trúc:

> **Trong điều kiện [workload và topology], vì [bằng chứng về nút thắt], thay [một biến X từ giá trị A sang B] sẽ cải thiện [metric mục tiêu] ít nhất [mức định lượng] mà không vi phạm [các guardrails].**

Ví dụ:

~~~text
Triệu chứng:
  Compaction.PendingTasks tăng trong peak nhiều ngày.
  SSTablesPerReadHistogram và p99 read tăng.

Giả thuyết:
  Compaction đang chạm giới hạn configured throughput.
  Disk/CPU còn headroom khi compaction active.

Can thiệp:
  Tăng throughput cap trên 1 node canary từ
  giá trị runtime cũ C0 lên C1, không chỉnh concurrency.

Mục tiêu:
  Pending compaction giảm theo xu hướng và không tăng
  read/write p99, timeout, disk await hoặc disk usage.

Điều bác bỏ:
  Pending không giảm dù throughput không chạm cap,
  hoặc p99/disk await xấu đi ngay khi cap tăng.
~~~

Nếu không đo được compaction có bị **cap** giới hạn hay không, chưa có lý do vững để tăng cap. Nếu disk đã bão hòa, giả thuyết “thêm compaction throughput làm nhanh hơn” thậm chí có thể ngược thực tế.

### 5.1. Khái niệm “một biến” không hoàn toàn giống “một số”

Một thay đổi `cassandra.yaml` có thể buộc **restart** node: bản thân restart làm cache lạnh, connection pool bị xây lại, replica availability giảm tạm thời. Khi đó thí nghiệm gồm **tuning + hiệu ứng restart**; cần giai đoạn warmup và dùng node đối chứng thích hợp.

Tương tự, đổi cache size sẽ ảnh hưởng page cache/GC theo thời gian; tăng số concurrent compaction worker sẽ ảnh hưởng cả CPU/disk. Không dùng một cửa sổ 30 giây sau restart làm kết quả “sau tuning”.

### 5.2. Mọi giả thuyết phải có metric âm tính

Không chỉ nêu metric muốn giảm; cần nêu những metric **không được tăng**:

- `PendingCompactions` giảm nhưng `read p99` tăng thì không đạt.
- `MemtablePool.BlockedOnAllocation` giảm nhưng `SSTable count` và disk backlog tăng không kiểm soát thì không đạt.
- CPU utilization tăng nhưng **throughput hoàn thành** không tăng, request lỗi tăng thì không đạt.
- Java client timeout giảm nhờ retry gấp nhiều lần có thể làm cluster quá tải, phải xét số attempts vật lý.

## 6. Phân loại mức độ có thể hoàn nguyên trước khi đổi

| Lớp thay đổi | Ví dụ | Cách hoàn nguyên | Nguy cơ thường bị bỏ qua |
|---|---|---|---|
| **Runtime setting có API đối xứng** | `nodetool setcompactionthroughput` | Gọi lại với **giá trị đã đọc trước đó**, xác minh bằng get | Runtime value có thể khác YAML; restart có thể đặt lại |
| **File/JVM setting cần restart** | Memtable allocation, heap/GC flags, một số thread counts | Phục hồi cấu hình cũ, **rolling restart có kiểm soát** | Cold cache, giảm số replica UP, thời gian phục hồi |
| **Java Driver/application setting** | Retry, pool, timeout, page size, metrics | Feature flag/redeploy/đổi config theo khả năng reload | Kết nối đồng loạt, retry storm, CL bị thay |
| **Table schema/compaction strategy** | `ALTER TABLE ... WITH compaction = ...` | Không đơn giản “đổi rồi đổi lại”: dữ liệu/SSTables có thể đã được viết lại | Nền compaction, I/O, file format, dữ liệu tồn tại |
| **Data model/TTL/retention** | Thêm bảng, đổi TTL, xóa dữ liệu | Cần backfill/khôi phục theo nguồn sự thật | Tombstone và dữ liệu đã purge không tự quay lại |
| **Topology/RF** | Bootstrap/decommission, `ALTER KEYSPACE` | Quy trình dữ liệu riêng: streaming, repair/rebuild | Đổi config không tự khôi phục đúng replica placement |

**Rollback là một thay đổi production thứ hai.** Với runtime knob đơn giản, hoàn nguyên nhanh tương đối khả thi. Với schema, dữ liệu và topology, chỉ “đặt lại số cũ” có thể **không phục hồi** phân phối dữ liệu hoặc trạng thái trước đó.

### 6.1. Định nghĩa rollback chính xác

- **Configuration rollback:** đặt lại tham số runtime/file/driver.
- **Operational rollback:** dừng rollout, không đổi thêm node; có thể cần khôi phục capacity hoặc chế độ traffic trước.
- **Data rollback:** đưa dữ liệu về trạng thái logic đúng bằng nguồn sự thật/backup/replay; không phải thao tác tự động của cấu hình.
- **Forward fix:** khi không an toàn để đảo chiều, giữ trạng thái tạm và tiến hành sửa hướng tới trước với plan riêng.

Mỗi change request phải ghi rõ **loại rollback áp dụng** và điều kiện chuyển sang escalation nếu không thể rollback an toàn.

## 7. Thiết kế thí nghiệm thay đổi có kiểm soát

### 7.1. Bảy thành phần của một change proposal

Một proposal có thể kiểm toán cần ghi ít nhất:

1. **Thành phần và phạm vi:** phiên bản Cassandra, DC/node/rack/table/JVM service, config file hoặc runtime API.
2. **Giá trị cũ được đọc thực tế:** ví dụ throughput cap `C0`, không chỉ giá trị được ghi trong tài liệu.
3. **Giá trị mới và lý do:** `C1` dựa trên đo capacity, không chọn một số “nghe có vẻ nhanh”.
4. **Giả thuyết có thể bác bỏ:** metric mục tiêu và dấu hiệu chứng minh nguyên nhân không phải điều dự đoán.
5. **Baseline và so sánh:** workload window, SLO, histograms, node/resource metrics, data checks.
6. **Thực hiện/quan sát:** người phụ trách, giới hạn concurrency, canary và kế hoạch mở rộng.
7. **Rollback/escalation:** trigger đo được, lệnh/đường cấu hình quay lại, cách xác minh, khi nào phải dừng.

Đây là cấu trúc một thử nghiệm tốt, không chỉ một thủ tục hành chính. Nếu mục tiêu/rollback trigger chưa được quyết định, hãy **chưa triển khai**.

### 7.2. Thứ tự kiểm soát khi nhiều node và rack

~~~text
                           ĐỀ XUẤT
                              |
                    Baseline + giá trị C0
                              |
                      Kiểm tra preflight
                              |
                    +---------+--------+
                    |                  |
                 ĐẠT                KHÔNG ĐẠT
                    |                  |
                 Canary             HỦY/HOÃN
                  1 node
                    |
           Quan sát guardrails đủ mẫu
               /                \
             ĐẠT              VI PHẠM
              |                  |
          Mở rộng từng         Hoàn nguyên C0
          batch/rack           và xác minh
              |                  |
         So lại workload       Điều tra nguyên nhân
              |
         Hoàn tất + ghi nhận
~~~

**Đừng triển khai cùng lúc toàn bộ replica của một token range.** Ví dụ trên RF=3 trong một DC, nếu phải restart node, chỉ cho một node xuống tại một thời điểm và đảm bảo hai replica còn lại khỏe đủ `LOCAL_QUORUM`. Cần biết rack/DC placement và các node đang lỗi, không tính rủi ro chỉ bằng “cluster có ba node”.

Với runtime knob không restart, canary một node vẫn có tác động tới **những query có replica trên node đó**; các node còn lại **không phải nhóm đối chứng hoàn toàn độc lập**, vì chúng cùng phục vụ dữ liệu replicated và có thể chia sẻ coordinator/traffic.

### 7.3. Vì sao phải so workload tương đương?

Giả sử trước tuning có 1.000 QPS và p99 100 ms, sau tuning có 250 QPS và p99 40 ms. Không đủ bằng chứng rằng tuning cải thiện: giảm QPS bốn lần có thể giải thích hầu hết thay đổi.

Một phép so sánh chặt hơn cần:

- Cùng nhóm **query families** và tỉ lệ read/write, không chỉ QPS tổng.
- Giới hạn sự khác biệt về **peak QPS, payload, hot partitions, page size, consistency level**.
- Cùng loại trạng thái **warm cache** hoặc đo rõ cold/warm.
- Có số lượng requests đủ lớn cho p99, không công bố p99 từ vài chục request.
- Theo dõi công việc nền: repair, compaction, bootstrap, backup, streaming và OS cron.
- Kiểm áp lực tài nguyên trên **node canary và cả node còn lại**.

Khi không có tải tương đương trên production, nên chạy **staging benchmark có bộ dữ liệu đại diện**, rồi canary production cẩn thận; không cố bơm traffic tải cực lớn vào hệ thống live để tạo một benchmark sạch.

### 7.4. Kiểm soát confounders

| Yếu tố gây nhiễu | Tác động | Biện pháp |
|---|---|---|
| Rolling restart bắt buộc | Cache lạnh, pool bị khởi tạo lại | Ghi nhận warmup, không đo ngay sau node UP |
| Compaction đã gần xong trước thay đổi | Pending có thể giảm tự nhiên | Có control window, quan sát throughput và số task |
| Node repair/bootstrap cùng lúc | Dùng disk/network ngoài baseline | Hoãn hoặc ghi nhận như biến độc lập |
| Traffic app đã giảm khi triển khai | p99 tự cải thiện | So theo cùng traffic bucket/giờ peak |
| TTL/delete burst khác ngày | Tombstones và disk scans khác nhau | Kiểm dataset/time bucket và workload |
| Thay retry policy Java cùng lúc | Physical attempts tăng | Giữ policy cố định khi đánh giá knob server |
| Tăng RF hoặc đổi CL | Thay số replica cần đọc/ghi | Không coi là so sánh tương đương |

## 8. Đặt điều kiện dừng/rollback trước khi thay đổi

### 8.1. Ba lớp guardrail

| Lớp | Ví dụ điều kiện | Hành động |
|---|---|---|
| **An toàn dữ liệu/quorum** | Replica thiếu khiến CL mục tiêu không thể đạt, ghi/đọc sai, node bất ngờ DOWN | **Dừng ngay** và chuyển sang runbook sự cố; chỉ rollback nếu thao tác đảo chiều an toàn |
| **SLO ứng dụng** | p99 vượt SLO; timeout rate tăng liên tục; lỗi `Unavailable` | Dừng mở rộng, hoàn nguyên canary theo ngưỡng đã phê duyệt |
| **Tài nguyên** | Disk free quá thấp, disk await/GC tăng, queue không hồi phục, CPU throttling kéo dài | Dừng mở rộng; phân tích và rollback nếu thay đổi tạo ra |

**Một trigger an toàn nghiêm trọng có thể yêu cầu rollback ngay**, không cần chờ ba cửa sổ. Ngược lại, một histogram p99 hơi cao do 20 samples chưa chắc đáng rollback; cần đặt điều kiện sample count, mức nghiêm trọng và khoảng quan sát.

### 8.2. Ví dụ ngưỡng rollback có đơn vị và thời gian

Giả sử **số liệu giả định** cho family `order.getById` ở peak:

| Chỉ số | Baseline | Guardrail minh họa trong canary |
|---|---:|---|
| `read p99` | 85 ms | Dừng nếu `>120 ms` trong **3 cửa sổ 5 phút** cùng tải; hoặc vi phạm SLO hard limit |
| `write p99` | 75 ms | Dừng nếu `>110 ms` trong **3 cửa sổ 5 phút** |
| `client timeout rate` | 0,05% | Rollback nếu `>0,5%` trong **2 cửa sổ 5 phút** và sample đủ |
| `Unavailable errors` | ≈0 | Điều tra ngay nếu tăng bất thường và có ảnh hưởng tới CL |
| `disk await p95` | 8 ms | Dừng mở rộng nếu `>18 ms` kéo dài cùng compaction tăng |
| `disk free` | 40% | Không tiếp tục nếu giảm xuống dưới ngưỡng an toàn đã duyệt (ví dụ 25%) |
| `Compaction.PendingTasks` | 20, giảm/tăng theo burst | Mục tiêu xu hướng giảm; không dùng một điểm 20→19 làm bằng chứng |
| `GC pause p99` | 15 ms | Dừng nếu tăng quá mức ngân sách GC đã duyệt |
| `node UP/NORMAL` | 3/3 | Không tiếp tục nếu có node xuống bất thường |

Những con số **chỉ là thí dụ** để cho thấy một guardrail có **đơn vị, mốc, ngưỡng, cửa sổ và hành động**. Chúng **không phải giá trị Apache khuyến nghị**. Trên một hệ thống ngân hàng/real-time, SLO và trigger có thể nghiêm ngặt hơn nhiều; trên cluster batch có thể khác.

**Điểm quan trọng:** Ngay cả khi `read p99=125 ms` vẫn dưới SLO tuyệt đối `150 ms`, nó có thể vi phạm **ngưỡng non-regression** của đợt tuning. Mục tiêu không phải tận dụng hết error budget của một API để cải thiện metric khác.

### 8.3. Đặt ngưỡng theo quan hệ nguyên nhân

Một trigger tốt nên liên kết **sự thay đổi** với **tín hiệu mục tiêu và tác dụng phụ**:

~~~text
Tuning: tăng compaction throughput C0 -> C1

Tiêu chí chấp nhận:
  pending compaction giảm ổn định theo nhiều cửa sổ
  AND compaction bytes/sec có tăng hợp lý
  AND read/write p99 không xấu đi
  AND disk await/free và timeout không vi phạm guardrails

Rollback:
  p99 hoặc disk latency vượt ngưỡng đủ lâu
  OR một dấu hiệu mất an toàn nghiêm trọng xuất hiện
  OR throughput cap tăng mà không cải thiện backlog
     và chi phí tài nguyên tăng rõ
~~~

Tránh trigger mơ hồ kiểu “hệ thống trông chậm” hoặc “pending chưa bằng 0 sau hai phút”. Một số compaction kéo dài hàng giờ vì SSTable lớn; pending là **ước lượng task**, không phải ETA chính xác.

### 8.4. Kế hoạch rollback phải có “điều kiện không rollback tự động”

Không phải mọi sự cố đều nên gọi lại lệnh cũ ngay:

- Node đang ở giữa **bootstrap/decommission**: đổi topology ngược giữa chừng có thể gây thêm streaming/rối ownership.
- Có sự cố **dữ liệu sai hoặc tombstone**: rollback config không tạo lại dữ liệu đã mất.
- Node đang DOWN và quorum thiếu: rolling restart “để phục hồi file config” có thể làm cluster **càng unavailable**.
- Một thay đổi compaction/schema đã tạo SSTable mới: đổi lại strategy không hoàn nguyên tức thì file đã viết.

Trong các trường hợp này, **dừng rollout, bảo toàn trạng thái, mở incident và dùng runbook recovery chuyên dụng**. “Rollback” không được là một lệnh shell chạy vô điều kiện khi alert bật.

## 9. Cấu hình nào nên thử trước? Ma trận rủi ro theo tài nguyên

### 9.1. Bảng quyết định trước tuning

| Tài nguyên/nút thắt giả định | Tín hiệu ủng hộ | Hướng thay đổi khả dĩ | Rủi ro/cần kiểm |
|---|---|---|---|
| Compaction bị cap thấp | `PendingTasks` tăng, throughput chạm cap, disk/CPU còn dư | Tăng vừa phải `compaction_throughput` | Đụng read/flush disk và SLA |
| Disk thực sự saturated | Disk await và queue cao, I/O tranh chấp | Giảm/điều tiết job nền, xem capacity/disk placement | **Không** tăng mọi throughput cap |
| Memtable flush không theo kịp | `PendingFlushes`, `MemtablePool.BlockedOnAllocation`, pending flush pool tăng | Phân tích đĩa, memtable budgets; cân nhắc `memtable_flush_writers` | Nhiều flush writers có thể tăng SSTable/compaction |
| Compaction concurrency thiếu | Tasks pending tăng, disk/CPU còn headroom, ít task active | Xem `concurrent_compactors` theo version | CPU/disk saturation, ghi đồng thời nhiều file |
| GC pause lớn, heap pressure | GC pause p99 cao, heap occupancy, allocation pressure | Xem heap sizing/GC flags/JDK theo runbook | Restart, cache cold, RAM off-heap/page cache giảm |
| Commit log waits | `CommitLog.WaitingOnCommit`/`WaitingOnSegmentAllocation` tăng | Phân tích disk commit log, sync và space | Đổi durability/sync mode cần kiểm bảo đảm dữ liệu |
| Cache miss/read I/O cao | Read p99 và disk reads cao, key cache hit thấp | Xem key/row cache phù hợp workload | Cache chiếm memory, cold restart |
| Java Driver pool/in-flight quá tải | Pool in-flight/retries/client timeout cao | Giới hạn concurrency, tune pool/retry có cơ sở | Retry storm, tăng attempts, thay CL |
| Hot partition/row rộng | Một vài token ranges rất nóng, tombstones/read cao | Thiết kế lại partition/bucket/schema | Backfill/dual-write/semantics, không chỉ knob |
| Node/rack thiếu capacity | Nhiều node cùng trên ngưỡng disk/CPU | Mở rộng capacity theo runbook | Bootstrap/streaming và metadata refresh |

**Không có thứ tự tham số áp dụng cho mọi cluster.** Một workload time-series TTL/TWCS khác một workload giao dịch point lookup/LCS; chọn theo bằng chứng chứ không theo “top 10 config nên tăng”.

### 9.2. Ví dụ runtime: compaction throughput

~~~bash
# Quan sát giá trị ĐANG ÁP DỤNG trên đúng node canary.
nodetool getcompactionthroughput

# Xem cú pháp bản đang chạy, đơn vị và giới hạn.
nodetool help setcompactionthroughput
~~~

Trong Cassandra 5.0, `nodetool setcompactionthroughput` nhận giới hạn theo **MiB/s** và giá trị `0` thường được dùng để **bỏ giới hạn**, không phải “dừng compaction”. Các bản cũ có cách hiển thị/đặt tên đơn vị khác; xác minh trước khi chạy.

**Lệnh thay đổi tham khảo cho lab, không phải số khuyến nghị:**

~~~bash
# Chỉ sau khi đã lưu giá trị C0 và có quyền vận hành.
nodetool setcompactionthroughput 32

# Xác minh runtime đã nhận C1.
nodetool getcompactionthroughput
~~~

Đổi throughput cap **không tạo thêm băng thông vật lý**. Nếu disk đã saturated, tăng cap chỉ tăng cạnh tranh với CQL/flush. Ngược lại nếu cap thực sự quá thấp và disk dư, thay đổi vừa phải có thể giúp backlog giảm.

### 9.3. Ví dụ có thể cần restart: memtable flush writers

Một số giới hạn flush/JVM được khai báo trong `cassandra.yaml`/JVM options. Việc áp dụng có thể cần **restart node**, và các bản Cassandra khác nhau có defaults khác nhau:

~~~yaml
# Ví dụ cú pháp để nhận diện trong cấu hình; KHÔNG copy số
# sang production nếu chưa đánh giá số data directories và disk.
memtable_flush_writers: 2
~~~

Trước khi chỉnh, xác minh:

- Flush queue tăng **thật**, `BlockedOnAllocation` có diễn ra không.
- Writer có active hết không, hay đĩa/post-flush đang chậm.
- Mỗi disk/data directory có hiệu năng thế nào.
- Tăng writers có làm nhiều SSTable nhỏ hơn, tăng `PendingCompactions` không.
- Rolling restart có còn đủ RF và CL, và có thời gian warmup hợp lệ không.

Không coi tham số có trong file là bằng chứng nó **có thể reload nóng**; ghi rõ yêu cầu restart của đúng phiên bản.

### 9.4. JVM heap/GC và dữ liệu ngoài heap

Ví dụ JVM heap 8 GiB **không có nghĩa** Cassandra chỉ dùng 8 GiB RAM. Còn off-heap memtable/buffers, page cache của OS, direct memory và native overhead. Tăng heap có thể làm giảm page cache hiệu quả và khiến đọc SSTable chậm hơn.

Một thay đổi heap/JDK/GC:

1. Phải kiểm cấu hình JVM, giới hạn container/cgroup, OS RAM và page cache.
2. Có baseline về allocation rate, GC pause, heap occupancy, direct memory.
3. Cần rolling restart, không sửa nhiều node cùng một lúc khi replica đang thiếu.
4. Không dùng p99 ngay sau restart để so sánh với lúc cache đã warm.
5. Nếu heap giảm áp lực nhưng disk read latency tăng kéo dài, có thể cần rollback.

**Không tự đổi GC collector bằng một flag từ blog cũ**: Cassandra version và JVM compatibility phải theo tài liệu vận hành tương ứng.

### 9.5. Driver tuning cũng cần baseline

Đối với Java Driver 4.x:

- `request.timeout`: không tăng vô hạn để che nghẽn.
- Page size: cân bằng số fetch và response/client memory.
- Retry policy/speculative execution: kiểm **idempotency** và số physical attempts.
- Pool/concurrency: quan sát in-flight, saturation và reconnect.
- CL/serial CL: giữ theo hợp đồng dữ liệu, không “tune” bằng cách hạ bảo đảm.
- Local DC/token map: lỗi routing có thể làm query đi xa hoặc coordinator kém tối ưu.

Khi thay Java Driver config, xác định nó được reload động hay cần **rebuild session/redeploy** trong app hiện tại. Một số thay đổi driver không có hiệu lực chỉ bằng sửa file bên ngoài process.

## 10. Canary trên một node có phải luôn an toàn?

Không. Canary có ý nghĩa **giới hạn blast radius**, nhưng Cassandra có **replication** và shared workloads:

~~~text
                       RF=3, DC=dc1
                      query tenant-a
                            |
                      Coordinator B
                            |
                 +----------+----------+
                 |          |          |
             Replica A  Replica B  Replica C
               canary      old        old
               cap C1    cap C0     cap C0
                 |          |          |
                Disk       Disk       Disk

Một coordinator có thể chờ replica A trong quorum.
Canary A ảnh hưởng query end-to-end dù app không gửi
CQL trực tiếp tới A.
~~~

### 10.1. Chọn node canary như thế nào?

- Node UP/NORMAL, không streaming/repair/failing disk.
- Đại diện hardware, disk class, data directory và workload của các node mục tiêu.
- Có metrics theo node và tập partition/queries có thể kiểm.
- Không ở rack/DC đã thiếu replica hoặc sắp bảo trì.
- Có operator trực, sẵn đường rollback đã kiểm.
- Không chứa duy nhất bản dữ liệu quan trọng mà những replica khác không thể phục hồi.

Trên cluster nhỏ chỉ có RF=1 hoặc RF=2, tác động của rolling restart khác đáng kể. Không thực hiện canary theo mẫu RF=3 mà bỏ qua thực tế replica placement.

### 10.2. Thứ tự phát hành đề xuất

| Pha | Phạm vi | Điều kiện chuyển bước |
|---|---|---|
| Baseline | Không thay đổi | Đủ dữ liệu theo node/query family và lưu C0 |
| Canary | Một node hoặc một app instance có kiểm soát | Không chạm guardrails; đủ mẫu và workload |
| So sánh | Canary vs baseline + các node khác | Tác dụng chính đo được, không tạo tác dụng phụ |
| Batch 1 | Một nhóm nhỏ, tách rack/replica phù hợp | Quorum và capacity còn an toàn; metric ổn |
| Batch tiếp | Mở rộng có giám sát | Không có lỗi tích lũy qua thời gian |
| Kết thúc | Tất cả phạm vi mục tiêu | Đúng config runtime, SLO ổn, không quên node nào |

Một chỉnh sửa có thể cho tác động **chậm** (cache warmup, compaction backlog, SSTable rewrite). Thời gian canary phải đủ để quan sát loại tác động đó, không áp cứng “5 phút là xong” cho mọi knob.

## 11. Rollback đúng: đưa trạng thái vận hành trở lại, không chỉ chạy lệnh ngược

### 11.1. Chuỗi rollback cho một runtime knob

~~~text
Metric vi phạm guardrail hoặc thử nghiệm không đạt
                         |
                  DỪNG RAMP-UP
                         |
             Kiểm tra node/quorum có an toàn
                /                   \
              CÓ                    KHÔNG
               |                       |
       Gọi lại runtime C0       Incident response riêng:
               |               không restart/stream bừa
          Đọc giá trị thực              |
               |                    Escalation
      Đợi thời gian ảnh hưởng
               |
          Đo SLO + tài nguyên
               |
       Có hồi phục về baseline?
          /            \
        CÓ             KHÔNG
         |               |
    Ghi rollback       Tiếp tục điều tra
    thành công         nút thắt thực
~~~

**Phải phân biệt “lệnh set trả thành công” và “hệ thống đã hồi phục”.** Nếu compaction backlog đã tích lũy hoặc đĩa đầy, việc đặt cap trở lại chưa chắc khiến p99 về baseline ngay. Các task đã lập lịch có thể cần thời gian tự hoàn thành. Cần theo dõi hậu rollback.

### 11.2. Rollback runtime của compaction throughput

Giả sử trước canary, `nodetool getcompactionthroughput` xác nhận `C0=64 MiB/s` (giá trị ví dụ), sau đó thử `C1=96 MiB/s` trên node A:

~~~bash
# Thay đổi khi được phê duyệt:
nodetool setcompactionthroughput 96
nodetool getcompactionthroughput

# Khi guardrail bị vi phạm:
nodetool setcompactionthroughput 64
nodetool getcompactionthroughput
~~~

**Không** copy số 64/96 sang production nếu không đúng giá trị đã đọc. Điều kiện thành công là **cap runtime thật trở lại C0** trên đúng node, đồng thời các chỉ số p99, timeout, disk await và backlog hồi phục theo kế hoạch. Nếu trước đó `C0=0` nghĩa là unlimited, cần hiểu hậu quả trước khi phục hồi. Nên ghi *nguyên văn output* giá trị cũ cùng đơn vị và phiên bản.

### 11.3. Rollback config cần rolling restart

~~~text
Canary node A được chỉnh cassandra.yaml rồi restart.
Thử nghiệm thất bại.

1. Dừng rollout B/C.
2. Kiểm cluster đủ replica để có thể restart A lần nữa.
3. Khôi phục backup/commit của cấu hình cũ trên A.
4. Xác minh diff và chính sách restart của version.
5. Restart A có kiểm soát (không làm B/C cùng down).
6. Chờ A UP/NORMAL, client pools hồi phục, warm caches.
7. Kiểm runtime effective value, SLO, disk/GC và dữ liệu.
~~~

Nếu node A không thể trở lại UP/NORMAL hoặc CL không còn đạt, **không tiếp tục restart những node khác**. Mở incident về availability và bảo vệ replica trước khi thao tác tiếp.

### 11.4. Rollback cấu hình Java Driver

Nếu thử tăng retry hoặc pool size trong service Java:

1. Dừng rollout/canary và ghi commit/config version, feature flag.
2. Đưa config trở lại giá trị cũ hoặc deploy phiên bản cũ theo quy trình.
3. Xác minh session đã nhận config; thay file không đảm bảo phiên driver hiện tại tự reload.
4. Theo dõi `connected-nodes`, pool in-flight, physical attempts, client timeout và latency.
5. Tránh **restart tất cả instances cùng lúc**, có thể tạo connection storm và tăng tải Cassandra.

Đối với thay `consistency level` hoặc logic retry của mutation, cần đánh giá **request nào đã được thực thi nhưng client nhận timeout** trước khi tự retry lại; dùng idempotency/audit nghiệp vụ.

### 11.5. Khi “rollback” phải chuyển thành recovery

| Thay đổi | Vì sao gọi lại config cũ chưa đủ? | Hướng hành động |
|---|---|---|
| `ALTER KEYSPACE` đổi RF | Tập replicas/dữ liệu đã thay đổi, những bản sao mới cần repair/streaming | Có runbook replication riêng, xác nhận đầy đủ dữ liệu trước/sau |
| Decommission/replace node | Token ownership và data đã stream | Dùng bootstrap/rebuild/replace an toàn; không tự gắn node cũ vào ring |
| Hạ `gc_grace_seconds` rồi compaction purge tombstone | Bằng chứng xóa có thể đã biến mất | Điều tra zombie, repair/restore theo nguồn sự thật |
| Schema drop/TTL delete | Dữ liệu đã xóa không tự tái tạo | Backup/CDC/audit, backfill hoặc restore chọn lọc |
| Đổi compaction strategy | SSTable đã được rewrite theo quá trình nền | Xác minh compatibility, kế hoạch chuyển ngược và headroom |
| Đổi partition key bằng bảng mới | Bảng cũ/mới có dữ liệu và luồng ghi riêng | Dual-write/dual-read, backfill, đối chiếu và feature flags |

**Không đánh dấu một thay đổi dữ liệu là “fully reversible” chỉ vì CQL `ALTER TABLE` có thể chạy với giá trị cũ.**

## 12. Runbook production trước, trong và sau tuning

### 12.1. Preflight: điều kiện cho phép bắt đầu

1. **Hệ thống đủ khỏe:** Không có node đang down bất thường, đang bootstrap/replace chưa xong hoặc repair quan trọng thất bại.
2. **Config được xác nhận:** Giá trị cũ C0 từ runtime và từ hệ thống quản lý cấu hình, biết precedence/JVM overrides.
3. **Baseline có thời gian:** Cùng workload, QPS/CL, latency histograms, errors, CPU/disk/GC, queues và disk free.
4. **Kiểm rủi ro dữ liệu:** Thay đổi có chạm RF, tombstone, TTL, schema hay cleanup không? Nếu có phải tách runbook.
5. **Mức độ phê duyệt phù hợp:** Đặc biệt với runtime JMX, config restart, network và các tác vụ đụng dữ liệu.
6. **Rollback đã thử:** Có lệnh/cấu hình quay về C0, operator và kịch bản không thể rollback.
7. **Change freeze hợp lý:** Không chạy cùng lúc bulk ingest, migration, topology change hoặc một tuning khác nếu ảnh hưởng phép so.
8. **Kênh quan sát và liên lạc:** Dashboard theo node/DC, business owner, on-call, mốc quyết định.

### 12.2. Trong khi thay đổi

~~~text
T0  Ghi baseline + xác nhận C0 trên node
T1  Preflight: ring/replicas/disk/CL đạt
T2  Bật thay đổi C1 trên canary
T3  Đọc lại effective value, lưu event/UTC timestamp
T4  Quan sát warmup/batch đủ mẫu theo loại knob
T5  Đối chiếu SLO, resource và correctness
T6  Nếu đạt: mở rộng theo batch nhỏ, lặp lại T3–T5
T7  Nếu không đạt: dừng mở rộng, rollback hoặc escalation
T8  Hoàn tất: kiểm consistency config mọi node, theo dõi dài hạn
~~~

Không tự đặt T3–T5 là “đợi đúng 60 giây”: cache, compaction và traffic theo chu kỳ có latency phản ứng khác nhau. **Đủ mẫu và đủ loại workload** quan trọng hơn một thời gian cố định.

### 12.3. Các mức quyết định

| Trạng thái | Bằng chứng | Hành động |
|---|---|---|
| `GO` | Baseline hợp lệ; canary tốt hơn/không kém đáng kể; không guardrail bị chạm | Mở rộng từng batch |
| `HOLD` | Chưa đủ số mẫu, workload thay đổi, số liệu bất nhất | Giữ phạm vi canary, quan sát/điều tra |
| `ROLLBACK` | Có tác dụng phụ rõ, trigger định lượng được kích hoạt, và đảo config an toàn | Đưa về C0, xác minh runtime và SLO |
| `ESCALATE` | Replica/quorum nguy cấp, dữ liệu sai, streaming/schema đang dở hoặc rollback có thể nguy hiểm | Dừng, xử lý incident theo runbook riêng |
| `CANCEL` | Giả thuyết không được chứng minh hoặc lợi ích quá nhỏ | Không rollout, lưu bài học |

### 12.4. Kết thúc đợt thay đổi

Một đợt chỉ được đóng khi:

- Mọi node/JVM trong phạm vi mục tiêu đã có **effective config** được ghi nhận, không chỉ Git commit.
- Các metric mục tiêu cải thiện hoặc đạt ngưỡng đã định.
- Không có lỗi SLO hoặc resource regressions ở query families khác.
- Cluster ring/replica/repair không gặp lỗi mới.
- Các sample CQL có kết quả đúng theo nguồn nghiệp vụ.
- Nếu có rollback: C0 đã xác minh và hoạt động hồi phục, không chỉ lệnh set thành công.
- Có báo cáo nguyên nhân, kết quả, dư địa tăng trưởng và kế hoạch monitor.

## 13. Định lượng hiệu quả mà không nhầm latency với CPU

### 13.1. Đặt cặp chỉ số mục tiêu + guardrail

Ví dụ với compaction tuning:

~~~text
Primary objective:
  Pending compactions theo node/table giảm về baseline
  hoặc không còn tăng trong business peak.

Supporting:
  Compaction bytes/sec tăng khi cap được nâng.
  Live SSTable count/SSTablesPerRead không xấu đi.

Guardrails:
  Read/write p95/p99 và timeout không vượt giới hạn.
  Disk await, disk free, CPU, GC, memtable flush vẫn an toàn.
  Không có replica UNAVAILABLE, node không rơi khỏi ring.
~~~

Một metric mục tiêu giảm không đủ: nếu `PendingCompactions` giảm vì **compaction bị disable hoặc data ingest ngừng**, đó không nhất thiết là hiệu quả của tuning.

### 13.2. Phân biệt rate và trạng thái tức thời

| Metric | Loại thường gặp | Phép phân tích |
|---|---|---|
| `Compaction.PendingTasks` | Gauge/estimate | Trend, max, thời gian backlog kéo dài |
| `Table.PendingFlushes` | Metric pending với semantics cần xác minh theo version/exporter | Quan sát số pending và flush pool; không áp rate mù quáng |
| `Compaction.BytesCompacted` | Counter | Bytes/sec qua nhiều sample, xét reset sau restart |
| `ThreadPools.CompletedTasks` | Counter | Tasks/sec theo đúng pool |
| `ClientRequest.*.Timeouts` | Counter/meter theo exporter | Tỷ lệ lỗi/giây hoặc fraction trên request count |
| CPU | Gauge (% hoặc normalized cores) | p95/time window, tránh nhầm host với container |
| Disk free | Gauge (bytes, %) | Headroom tuyệt đối và xu hướng |
| p95/p99 latency | Histogram/timer/distribution | Gộp đúng histogram, kèm sample count |

**Không lấy mean của p99 từng pod** để công bố p99 dịch vụ, và không lấy hiệu hai percentiles ở các lớp khác nhau để tính độ trễ network. Khi cần quy nguyên nhân, dùng tracing/metrics theo cùng request/time window.

### 13.3. Mô hình queue trực giác

Nếu tác vụ compaction đến với tốc độ `λ` tasks/s và hệ thống xử lý với tốc độ `μ` tasks/s, backlog có xu hướng tăng khi `λ > μ` đủ lâu. Nhưng tasks rất khác nhau về bytes/chi phí, nên `PendingTasks / completed_tasks_per_second` **không phải ETA đáng tin trong mọi trường hợp**.

Một cách kiểm tốt hơn:

1. So **bytes compacted/sec**, CPU/disk throughput và loại compaction.
2. Theo dõi số SSTable và read amplification theo table.
3. Kiểm backlog có thực sự thoát sau peak workload không.
4. Quan sát p99 và timeout của client ở cùng cửa sổ.
5. Chấp nhận rằng một compaction lớn chạy lâu có thể giữ số pending thấp.

### 13.4. Biểu đồ trước–sau minh họa

| Metric | Baseline | Canary C1 | Sau hoàn nguyên C0 | Kết luận giả định |
|---|---:|---:|---:|---|
| Pending compactions sau peak | 30 | 12 | 29 | C1 giảm backlog |
| Compaction bytes/sec | 40 MiB/s | 80 MiB/s | 42 MiB/s | C1 tăng throughput |
| Read p99 | 85 ms | 160 ms | 88 ms | **Vi phạm guardrail**, cần rollback |
| Write p99 | 75 ms | 115 ms | 76 ms | Xấu hơn và hồi phục sau rollback |
| Disk await p95 | 8 ms | 25 ms | 9 ms | Cạnh tranh I/O là giả thuyết mạnh |
| Timeout rate | 0,05% | 0,6% | 0,07% | Tăng vượt ngưỡng |

**Số liệu hoàn toàn giả định.** Đợt thử không thành công dù compaction backlog giảm. Điều đúng là đặt lại C0 và điều tra storage capacity/traffic, không báo “đã tối ưu compaction” theo một metric riêng.

## 14. Lab CQL/nodetool: thay cap compaction rồi hoàn nguyên

**Mục tiêu:** Học trình tự **baseline → lưu C0 → đổi C1 → xác minh runtime → đo → trả C0 → xác minh rollback** trên một node thử nghiệm. Không cần cố tạo backlog: một cluster lab nhỏ có thể có pending compaction bằng 0 trong cả hai trạng thái. Thành công của lab là **quy trình kiểm soát được**, không phải tạo tình huống I/O nghẽn.

**Môi trường:** Cassandra 4.1/5.0 **cluster lab một node**, `cqlsh`, `nodetool` với quyền quản trị đúng node. Không thực hiện thay throughput trên production chỉ để làm bài tập. Nếu đang chạy Cassandra phiên bản có cách diễn giải unit khác, dùng cú pháp trong `nodetool help`/tài liệu phiên bản đó.

### Bước 1 — Tạo dữ liệu tách biệt với hệ thống khác

~~~sql
CREATE KEYSPACE IF NOT EXISTS resource_tuning_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS resource_tuning_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CONSISTENCY ONE;

INSERT INTO resource_tuning_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
        11111111-1111-1111-1111-111111111111, 'created');

INSERT INTO resource_tuning_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
        22222222-2222-2222-2222-222222222222, 'paid');

INSERT INTO resource_tuning_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, payload)
VALUES ('tenant-b', '2026-11-21', '2026-11-21T08:10:00Z',
        33333333-3333-3333-3333-333333333333, 'created');

SELECT event_time, event_id, payload
FROM resource_tuning_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

**Giới hạn:** `SimpleStrategy` RF=1 chỉ dùng trên cluster lab một node. Trên production nhiều DC hãy dùng `NetworkTopologyStrategy`/RF phù hợp và kiểm CL theo ứng dụng. Với ba row rất nhỏ, **không** có đủ dữ liệu để benchmark compaction thực tế.

### Bước 2 — Lấy baseline và sao lưu giá trị cũ

~~~bash
nodetool version
nodetool status
nodetool getcompactionthroughput
nodetool compactionstats
nodetool tpstats
nodetool tablestats resource_tuning_lab.events_by_tenant_day
~~~

Lưu nguyên văn output, UTC timestamp và giá trị `C0` từ `getcompactionthroughput`. Nếu C0 là “unlimited” hoặc bằng 0, **ghi rõ điều đó**, không tự thay bằng một số đoán. Thêm snapshot disk free, CPU, GC và đọc CQL.

~~~text
PHIẾU LAB — các dòng phải điền bằng kết quả thực
  Node:
  Cassandra version:
  Effective C0 + units:
  Baseline timestamp:
  Pending compactions:
  Disk free / CPU / I/O:
  SELECT tenant-a kết quả:
~~~

### Bước 3 — Xác minh lệnh trên đúng phiên bản

~~~bash
nodetool help setcompactionthroughput
nodetool help getcompactionthroughput
~~~

Nếu binary không hỗ trợ lệnh, quyền JMX không đủ hoặc node không healthy, **dừng lab** và chỉ hoàn thành phần phân tích. Không chuyển sang cách chỉnh một config khác khi chưa nắm rollback.

### Bước 4 — Chỉnh một runtime knob trên lab

~~~bash
# Ví dụ C1=32 MiB/s theo cú pháp Cassandra 5.0.
# KHÔNG dùng C1 này như khuyến nghị cho cluster thực.
nodetool setcompactionthroughput 32

# Bắt buộc đọc lại giá trị effective đã được áp dụng.
nodetool getcompactionthroughput
~~~

**Không** chạm đồng thời `concurrent_compactors`, `memtable_flush_writers`, CL, retry policy hoặc compaction strategy. Nếu muốn có số đo hiệu năng thực, cần dataset/traffic đủ lớn và một load test staging riêng, không tăng ghi trong lab đến mức đầy đĩa.

### Bước 5 — Quan sát sau thay đổi

~~~bash
nodetool compactionstats
nodetool tpstats
nodetool tablestats resource_tuning_lab.events_by_tenant_day
nodetool getcompactionthroughput
~~~

Trong cqlsh:

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_id, payload
FROM resource_tuning_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, payload
FROM resource_tuning_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-b'
  AND day = '2026-11-21';
~~~

Nếu `pending tasks = 0` ở cả hai thời điểm, đó là **kết quả bình thường** của lab nhỏ. Tham số đã đổi nhưng không có công việc nền đủ để tạo khác biệt quan sát được. Không được kết luận “32 MiB/s tối ưu hơn” hoặc “thay đổi không có tác dụng” từ các row này.

### Bước 6 — Hoàn nguyên C0, không dùng một giá trị mẫu

Ví dụ **chỉ khi đã ghi C0=64 MiB/s từ baseline**:

~~~bash
# Số 64 chỉ minh họa C0; thay bằng giá trị C0 THỰC TẾ.
nodetool setcompactionthroughput 64
nodetool getcompactionthroughput
~~~

Nếu C0 không phải 64, lệnh trên **không** hoàn nguyên đúng! Người học phải thay bằng giá trị gốc đã đọc hoặc chuyển sang trạng thái cần hỗ trợ nếu chưa biết C0. **Không bỏ bước đọc lại**, vì chạy lệnh thành công chưa đảm bảo operator đã chạm đúng node.

### Bước 7 — So sánh kết quả và viết kết luận

| Trường | Trước C0 | Khi C1 | Sau rollback C0 | Cần điền |
|---|---|---|---|---|
| Thời gian/Node | Baseline UTC | UTC sau set | UTC sau restore | Điền |
| Throughput cap effective | C0 | C1 | **Bằng C0** | PASS/FAIL |
| `PendingCompactions` | Snapshot | Snapshot | Snapshot | Trend nếu đủ mẫu |
| `BytesCompacted/sec` | Nếu có compaction | Nếu có | Nếu có | Không đoán |
| Disk free/await | Baseline | Quan sát | Quan sát | Không hồi quy |
| CQL SELECT results | 2/1 rows mẫu | Giữ nguyên | Giữ nguyên | Correctness |
| Errors/Timeouts | Baseline | Quan sát | Quan sát | Không tăng |

**Đạt lab khi:** C0 được lưu, C1 có hiệu lực, C0 được khôi phục và kiểm lại; dữ liệu CQL vẫn đúng. **Không cần** ép một benchmark “C1 cải thiện 20%” nếu dữ liệu không đủ.

## 15. Java Driver: đo cùng request trước và sau

Ứng dụng Java nên có **query family** cố định và cùng CL/page size khi so baseline. Ví dụ sau dùng Java Driver 4.x; `CqlSession` do ứng dụng tạo và tái sử dụng, không tạo mới cho từng request.

### 15.1. Code mẫu đo thời gian cả truy vấn, không chỉ bắt đầu request

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class TuningReadProbe {
    public record ReadSample(
            long elapsedNanos,
            int returnedRows,
            List<String> payloads) {}

    private final CqlSession session;
    private final PreparedStatement readByDay;

    public TuningReadProbe(CqlSession session) {
        this.session = session;
        this.readByDay = session.prepare(
            "SELECT payload FROM resource_tuning_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND day = ?");
    }

    public ReadSample readAll(String tenantId, LocalDate day) {
        BoundStatement statement = readByDay.bind(tenantId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setPageSize(50);

        long start = System.nanoTime();
        ResultSet result = session.execute(statement);
        List<String> payloads = new ArrayList<>();
        for (Row row : result) {
            payloads.add(row.getString("payload"));
        }
        long elapsed = System.nanoTime() - start;
        return new ReadSample(elapsed, payloads.size(), payloads);
    }

    public static double elapsedMillis(ReadSample sample) {
        return sample.elapsedNanos() / 1_000_000.0;
    }
}
~~~

Ví dụ gọi từ phương thức có `session`:

~~~java
TuningReadProbe probe = new TuningReadProbe(session);
TuningReadProbe.ReadSample measured = probe.readAll(
    "tenant-a", LocalDate.parse("2026-11-21"));

System.out.printf(
    "duration_ms=%.3f rows=%d values=%s%n",
    TuningReadProbe.elapsedMillis(measured),
    measured.returnedRows(),
    measured.payloads());
~~~

Điểm cần giải thích:

1. Đo bằng `System.nanoTime()` cho **thời gian elapsed**, không dùng đồng hồ epoch có thể nhảy khi NTP chỉnh.
2. Vòng lặp `ResultSet` đọc đủ các page được cần để trả danh sách; chỉ gọi `execute()` có thể đo thiếu chi phí fetch tiếp.
3. `PreparedStatement` được tạo một lần; partition key bind giúp driver có routing information.
4. `CL=ONE` **chỉ cho lab RF=1**, không dùng mặc định khi ứng dụng production yêu cầu `LOCAL_QUORUM`.
5. Một sample không phải p99. Thu **histogram đủ mẫu** tại metrics backend, phân theo query family, DC và outcome; đo cả timeout/failure.
6. Method này **không đọc metrics compaction của Cassandra**. Phải ghép với JMX/nodetool, disk và các mốc thay config.

### 15.2. Những gì cần giữ cố định trong A/B

| Thuộc tính | Vì sao không nên đổi trong cùng thử nghiệm? |
|---|---|
| `LOCAL_QUORUM` / `ONE` | Đổi CL làm biến đổi hợp đồng replica và latency |
| Page size, `LIMIT` | Thay khối lượng rows/network |
| Prepared statement vs simple | Thay routing key/token-aware behavior |
| Driver retry/speculative policy | Thay số attempts và tải server |
| Local datacenter | Có thể chuyển request tới DC khác |
| Độ lớn dataset/hot key distribution | Thay read amplification và cache |
| JVM version/service release | Đổi GC/connection behavior và application overhead |

**Không coi query nhanh hơn sau khi hạ CL là bằng chứng compaction tuning có ích.** Trong thí nghiệm muốn đo compaction cap, giữ CL và statement không đổi.

### 15.3. Xuất histogram thay vì in một dòng

Trên ứng dụng thật, dùng Micrometer/OpenTelemetry/driver metrics theo chuẩn. Metric theo query family có thể gồm:

~~~text
app_cql_requests_total{service,query_family,outcome,dc}
app_cql_duration_seconds_bucket{service,query_family,dc,le}
app_cql_timeouts_total{service,query_family,dc}

datastax_driver_session_cql_requests_... (tên tùy exporter)
datastax_driver_node_cql_messages_...   (tên tùy exporter)
~~~

Các tên trên là **mẫu thiết kế**, không khẳng định exporter tạo sẵn đúng series ấy. Không đưa raw CQL, partition key, email hay tenant ID trực tiếp vào metric labels, vì rủi ro cardinality/riêng tư.

Khi làm dashboard:

- Gộp histogram đúng cách theo nhiều JVM; **không** lấy trung bình p99 của từng JVM.
- Đặt marker lúc canary/rollback; so cùng mức tải và số mẫu.
- Đếm errors/timeouts riêng; histogram chỉ success có thể che vấn đề.
- Theo dõi retries/pool in-flight để nhận diện driver khuếch đại traffic.
- Ghép với p99 coordinator/table và CPU/disk/GC trên natural replicas.

## 16. Case study: lựa chọn GO, HOLD, ROLLBACK hay ESCALATE

### Ca A — Cap compaction cao hơn, backlog giảm nhưng read latency tăng

**Baseline giả định:** Node A có pending compaction 25–35 tasks; disk await p95 khoảng 8 ms; read p99 khoảng 85 ms. Compaction throughput chạm configured cap, CPU/disk còn headroom trong một số cửa sổ.

**Canary:** Tăng cap một bước. Sau đó pending giảm còn 12 nhưng disk await lên 25 ms và read p99 lên 160 ms. Timeout rate tăng.

**Quyết định:** `ROLLBACK` về C0. Mục tiêu “giảm pending” không đủ khi SLO và tài nguyên nền bị xâm phạm. Tiếp theo kiểm disk throughput, compaction type, thời gian overlap với peak và phân bố task; có thể cần **chuyển lịch compaction nặng hoặc nâng capacity**, chứ không tiếp tục tăng cap.

**Bài học:** Nút thắt là **hiệu quả phục vụ query dưới tải tổng**, không chỉ tốc độ dọn SSTable.

### Ca B — Flush backlog giảm nhưng số SSTable nhỏ tăng

**Baseline:** `MemtablePool.BlockedOnAllocation` xuất hiện, pending flush tăng theo burst và người vận hành cho rằng writers thiếu.

**Canary:** Tăng flush writers và restart một node. Trong giờ đầu, pending flush giảm, nhưng `LiveSSTableCount` và `PendingCompactions` bắt đầu tăng nhiều; read p99 xấu đi sau vài giờ.

**Quyết định:** Nếu guardrail đã kích hoạt, `ROLLBACK` cấu hình và rolling restart có kiểm soát. Nếu còn đủ headroom và chưa vượt trigger, có thể `HOLD` để thu số liệu do compaction phản ứng chậm. Không mở rộng toàn cluster chỉ nhờ 15 phút đầu.

**Bài học:** Một tuning **cải thiện queue trước** có thể gây hậu quả **phía sau** trong mô hình LSM.

### Ca C — Heap lớn hơn, GC pause giảm nhưng disk reads tăng

**Baseline:** GC pause p99 và heap occupancy cao. Node có đủ RAM tổng nhưng page cache vốn đang hỗ trợ đọc nhiều SSTable.

**Canary:** Heap lớn hơn, restart node. GC pause giảm, nhưng disk read latency và `Table.ReadLatency` tăng kéo dài sau warmup vì page cache bị thu hẹp.

**Quyết định:** `HOLD` để xác minh có phải hiệu ứng cold cache tạm thời; nếu tác động kéo dài và SLO vi phạm, `ROLLBACK` bằng cấu hình JVM cũ và rolling restart. Không tự tăng heap nữa.

**Bài học:** **JVM heap không phải toàn bộ bộ nhớ Cassandra**. Phải cân bằng heap, off-heap và OS page cache.

### Ca D — Timeout giảm sau khi bật retry mạnh, physical attempts tăng

**Baseline:** Java service có read p99 gần SLO, timeout cao trong peak. Một team bật retry/speculative execution rộng hơn mà không hạn chế.

**Canary:** Client-visible timeout giảm một phần, nhưng `cql-messages`/`cql-requests` tăng, pool in-flight và CPU của coordinator tăng, node p99 xấu.

**Quyết định:** Dừng rollout và rollback policy hoặc giảm concurrency theo kế hoạch. Điều tra network/replica/storage bottleneck thật; với mutation, kiểm **idempotency** trước khi retry.

**Bài học:** Hết lỗi ở client có thể chỉ là **đẩy chi phí sang server**. Theo dõi request logic và attempts vật lý.

### Ca E — Đổi config trong file nhưng runtime vẫn giữ giá trị cũ

**Triệu chứng:** `cassandra.yaml` chứa cap/setting mới nhưng `nodetool get...` vẫn trả C0; operator kết luận tuning không hiệu quả.

**Nguyên nhân có thể:** Tham số không được reload nóng, bị override bởi JMX/system property, file chưa được deploy tới node, hoặc node chưa restart.

**Quyết định:** `HOLD`, xác minh effective config và cơ chế reload trên đúng phiên bản. **Không** sửa thêm các biến khác chỉ để thấy p99 đổi. Nếu thay đổi cần restart, lập lại preflight/rolling restart và warmup; nếu không an toàn, `CANCEL`.

**Bài học:** **Source-of-truth của cấu hình** phải đi cùng **bằng chứng tham số đang có hiệu lực**.

### Ca F — Một node canary bị lỗi, toàn bộ ứng dụng bắt đầu timeout

**Bối cảnh:** RF=3, app `LOCAL_QUORUM`. Đúng lúc canary restart, một replica khác mất kết nối.

**Kết quả:** Chỉ còn một replica khỏe ở một số phạm vi, `LOCAL_QUORUM` không thể đạt; request timeout/unavailable.

**Quyết định:** `ESCALATE` theo runbook khả dụng. Dừng mọi rolling restart tiếp theo; phục hồi đủ replica/driver connectivity trước. Không tiếp tục “rollback bằng restart node khác” và không tự hạ CL.

**Bài học:** Một kế hoạch rollback dựa vào restart chỉ an toàn khi **trạng thái replica lúc rollback** cho phép.

### Ca G — Baseline không tương đương vì bulk ingest kết thúc đúng lúc canary

**Bối cảnh:** Trước tuning CPU p95 90%, sau tuning 50%. Nhưng bulk ingest ngừng giữa hai cửa sổ.

**Quyết định:** `HOLD` hoặc `CANCEL` kết luận hiệu năng; lấy lại thí nghiệm dưới workload tương đương. Không công bố “giảm 40 điểm CPU” là lợi ích của knob mới.

**Bài học:** Correlation theo thời gian **không đủ** để quy nguyên nhân. Change markers và workload mix là một phần bắt buộc của baseline.

### Ca H — Đổi `gc_grace_seconds` để giải phóng disk nhanh

**Bối cảnh:** Disk free giảm, một người đề xuất hạ grace để tombstone sớm được purge.

**Nguy cơ:** Replica đã bỏ lỡ DELETE có thể giữ dữ liệu cũ; nếu tombstone bị garbage collect quá sớm, repair có thể **không còn bằng chứng xóa**, gây zombie data.

**Quyết định:** Không coi đây là tuning có rollback đơn giản. `CANCEL` hoặc mở quy trình riêng về data retention/repair và capacity. Đổi giá trị grace trở lại sau khi tombstone đã purge **không khôi phục được tombstone đã mất**.

**Bài học:** Không đánh đổi **tính đúng dữ liệu** để lấy một biểu đồ disk usage đẹp hơn.

## 17. Mẫu change record và báo cáo sau thay đổi

Một phiếu thay đổi nên giúp người chưa tham gia cũng **tái dựng được quyết định**:

~~~text
CHANGE_ID: CASSANDRA-TUNE-EXAMPLE-017
OWNER / ONCALL: <người/nhóm phụ trách theo hệ thống>
ENV: staging
CLUSTER / DC / NODE: test-ring / dc1 / node-a
CASSANDRA / JDK / DRIVER: <phiên bản thực>
CHANGE_CLASS: runtime-setting
SETTING: compaction throughput cap
PREVIOUS_EFFECTIVE_VALUE: C0 (đọc bằng nodetool)
PROPOSED_VALUE: C1 (theo khả năng storage)
WORKLOAD_WINDOW: peak tương đương (UTC, query families, QPS)
DEPENDENCIES: không topology/repair/backup đang thay đổi

HYPOTHESIS:
  Throughput đang chạm cap và disk còn headroom;
  tăng cap sẽ giảm pending compaction không làm SLO xấu.

BASELINE:
  read/write p99, timeout%, QPS, physical attempts
  compaction pending + bytes/sec, SSTablesPerRead
  disk await/free, CPU, GC, memtable/commitlog
  ring status + RF/CL + sample CQL results

GUARDRAILS:
  số liệu đủ mẫu, p99 non-regression threshold
  timeout/unavailable, disk await/free, GC, replica health

CANARY PLAN:
  một node A; operator trực; timestamp/command log
  không đổi cùng lúc các tham số khác

ROLLBACK:
  set runtime về đúng C0; đọc effective value
  xác minh ring, SLO và backlog sau rollback
  nếu quorum hoặc dữ liệu nguy cấp: ESCALATE

RESULT:
  GO / HOLD / ROLLBACK / ESCALATE / CANCEL
  hiệu quả/tác dụng phụ theo node và query family
  evidence links, residual risks, next review
~~~

Trường trong dấu `<...>` của mẫu **là chỗ người vận hành điền**, không phải lệnh shell hay output có sẵn. Không dùng mẫu để lưu password, token hoặc raw CQL có dữ liệu nhạy cảm.

### 17.1. Ví dụ một báo cáo rollback đã hoàn tất

~~~text
CHANGE_ID: CASSANDRA-TUNE-EXAMPLE-018 (giả định)
Thay đổi: C0=64 MiB/s -> C1=96 MiB/s trên node-a
Baseline peak:
  Read p99=85ms, timeout=0.05%, disk await p95=8ms
Canary (cửa sổ đủ mẫu):
  Read p99=160ms, timeout=0.60%, disk await p95=25ms
  Pending compactions 30 -> 12
Guardrail:
  p99 >120ms kéo dài; timeout >0.5%
Action:
  Dừng rollout; setcompactionthroughput 64; verify C0
Post-rollback:
  Read p99=88ms, timeout=0.07%, disk await p95=9ms
Conclusion:
  ROLLBACK thành công về runtime, SLO đang phục hồi.
  Không triển khai trên các node khác.
Residual risk:
  Backlog vẫn tăng vào peak; cần capacity/compaction review.
~~~

Mọi số liệu trong ví dụ là **minh họa**, không phải bằng chứng vận hành thật. Đối với sự cố thực, người chịu trách nhiệm phải cung cấp link metrics, trace/alert, config diff và mốc UTC.

### 17.2. Điều gì chứng minh “rollback đã xong”?

1. Giá trị effective **trở về đúng C0 trên toàn bộ phạm vi đã thay đổi**.
2. Node/ring/replica giữ khả dụng, không có streaming/repair mới bị lỗi.
3. Query SLO, timeout, tài nguyên trở lại baseline hoặc có lời giải thích cho phần chậm hồi phục.
4. Những query family/data samples quan trọng vẫn trả kết quả đúng.
5. Không có file config hoặc deploy pipeline nào sẽ **tự áp C1 trở lại ở lần restart sau**.
6. Có owner theo dõi backlog/repair hoặc hệ quả kéo dài.

Nếu rollback chỉ sửa runtime nhưng hệ thống quản lý cấu hình vẫn mang C1, node có thể **tự đổi về C1** ở lần restart sau. Vì vậy phải đồng bộ source-of-truth config theo chính sách, trong đúng phạm vi và quyền thay đổi.

## 18. Những sai lầm thường gặp khi tuning

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Chỉnh nhiều tham số cùng lúc | Không quy được nguyên nhân | Thử một biến trong một pha, ghi markers |
| Không lưu effective C0 | Không biết trả về giá trị nào | Đọc runtime và chụp config trước |
| Chỉ so p99 một lần | Sampling bias, peak khác nhau | Nhiều cửa sổ, sample count và workload tương đương |
| Bỏ failures khỏi histogram | p99 có thể đẹp hơn khi timeout tăng | Kết hợp error rate và latency |
| Chỉ nhìn trung bình cluster | Node nóng/đĩa lỗi bị che | Drill-down theo node/DC/table |
| Tăng mọi throughput cap | Disk/CPU tranh chấp mạnh hơn | Xác định bottleneck thực và headroom |
| Tăng flush writer khi disk saturated | Tạo thêm SSTables, đẩy backlog xuống compaction | Đo disk/post-flush/blocked memory trước |
| Chỉ nhìn PendingCompactions | Không biết task lớn hay nhỏ, không biết I/O | Đọc progress/bytes/sec/SSTablesPerRead |
| Bật retry vô hạn | Retry storm và thêm writes | Xem idempotency, attempt count, concurrency |
| Hạ CL để giảm latency | Thay consistency contract | Giữ CL cố định trong tuning tương đương |
| Restart tất cả replicas cùng lúc | Mất quorum/unavailable | Rolling restart theo topology và node health |
| Coi file config là runtime truth | Đánh giá sai hiệu lực | Đọc giá trị đang áp dụng |
| Đổi `gc_grace_seconds` để reclaim nhanh | Nguy cơ zombie dữ liệu | Repair/capacity runbook, bảo toàn tombstone |
| Dùng `nodetool compact` để “xóa queue” | Major compaction có thể làm disk/IO bùng nổ | Chỉ dùng khi có mục đích và headroom rõ |
| Coi rollback schema/RF là đảo một dòng | Data/ownership đã thay đổi | Có kế hoạch migration/recovery riêng |
| Kết thúc ngay sau set C0 | Backlog/SLO có thể chưa hồi phục | Xác minh effective value và hậu rollback |
| Không đồng bộ config management | Lần restart tới lại áp C1 | Ghi lại source-of-truth/config diff |
| Thiếu data correctness checks | Hệ thống nhanh nhưng sai dữ liệu | Test sample CQL, consistency và nghiệp vụ |

## 19. Checklist vận hành: đi từ baseline tới hoàn nguyên an toàn

### 19.1. Trước thay đổi

- [ ] Đã xác định rõ **nút thắt**, không chỉ thấy một metric cao.
- [ ] Giả thuyết viết được dưới dạng **nếu X thì Y**, có cách bác bỏ bằng số liệu.
- [ ] Chỉ định **một knob** và phạm vi node/DC/service cụ thể.
- [ ] Biết Cassandra/JDK/Java Driver version, RF, CL, data directories và compaction strategy.
- [ ] Đã lưu **effective C0**, config file/JVM flags/driver config và đường rollback.
- [ ] Baseline có QPS, peak, query families, latency histogram, error/timeout và resource metrics.
- [ ] Có thông tin theo **từng node/table**, không chỉ average toàn cluster.
- [ ] Không có sự cố node/quorum, repair/streaming chưa xong hoặc thiếu disk headroom.
- [ ] Tính đúng dữ liệu được kiểm bằng tập khóa/sample từ nguồn kỳ vọng.
- [ ] Đã đặt guardrails **có ngưỡng, đơn vị, thời gian và người ra quyết định**.
- [ ] Đã phân biệt config-only rollback với data/topology recovery.
- [ ] Đã lập kế hoạch canary, warmup, mở rộng batch và on-call.

### 19.2. Trong canary

- [ ] Đã đánh dấu thời điểm canary trên dashboard và ghi lại lệnh thay đổi.
- [ ] Đọc lại **effective C1** để bảo đảm knob thật sự đổi.
- [ ] Kiểm đủ sample/trạng thái workload; không so cold cache với warm cache.
- [ ] Theo dõi primary metric và các metric tác dụng phụ cùng cửa sổ.
- [ ] Ghi nhận physical retries/requests trong Java Driver, không chỉ logic QPS.
- [ ] Kiểm replica health và quorum sau mỗi bước có restart.
- [ ] Không đồng thời tăng concurrency hoặc đổi schema/CL nếu không nằm trong thiết kế thử.
- [ ] Có thể chọn rõ `GO`, `HOLD`, `ROLLBACK` hoặc `ESCALATE` từ dữ liệu.

### 19.3. Sau rollout hoặc rollback

- [ ] Đã kiểm toàn bộ phạm vi mục tiêu có effective setting đúng.
- [ ] Đã kiểm p95/p99, timeout, error budget và dữ liệu CQL không hồi quy.
- [ ] Đã kiểm disk await/free, CPU, heap/GC, memtable, commit log và compaction backlog.
- [ ] Có đủ thời gian quan sát hệ quả chậm: compaction, caches, SSTables.
- [ ] Nếu rollback, C0 đã được kiểm bằng lệnh GET và không bị config management ghi đè về C1.
- [ ] Nếu cần recovery, đã mở ticket/runbook riêng, không ghi “rollback complete” thiếu bằng chứng.
- [ ] Đã xuất change report, bài học rút ra và lần review tiếp theo.

## 20. Câu hỏi tự đánh giá

**Câu 1.** Vì sao p99 đọc giảm sau khi QPS sụt một nửa không chứng minh hiệu quả tuning?  
**Định hướng:** Workload không tương đương; giảm tải có thể là nguyên nhân độc lập.

**Câu 2.** Nếu `PendingCompactions` giảm nhưng `read p99` và timeout tăng, có được chọn `GO` không?  
**Định hướng:** Không; guardrails đã vi phạm, cần rollback/escalation phù hợp.

**Câu 3.** Tại sao trước khi chạy `setcompactionthroughput` phải gọi `getcompactionthroughput`?  
**Định hướng:** Cần biết C0 **đang có hiệu lực** và đúng unit để hoàn nguyên; file YAML không đủ.

**Câu 4.** Một node đã nhận C1 nhưng các node khác vẫn C0. Có thể so node ấy với những node kia như một A/B hoàn toàn độc lập không?  
**Định hướng:** Không; replicated reads/writes, coordinator và workload có thể liên hệ nhiều node.

**Câu 5.** Với RF=3 và `LOCAL_QUORUM`, điều gì xảy ra nếu restart canary đồng thời một replica khác down?  
**Định hướng:** Có thể không đủ hai replica phản hồi, gây unavailable; dừng rolling restart.

**Câu 6.** Vì sao không nên tăng `memtable_flush_writers` khi disk đã saturated?  
**Định hướng:** Thêm worker không tạo thêm disk bandwidth, có thể tăng SSTables/compaction contention.

**Câu 7.** Tại sao tăng JVM heap đôi khi làm read p99 xấu đi?  
**Định hướng:** Cạnh tranh RAM với off-heap/page cache, GC và cold restart effects.

**Câu 8.** Vì sao `Compaction.PendingTasks` không được coi là số giây còn lại của backlog?  
**Định hướng:** Tasks có kích thước khác nhau, pending là estimate, phải nhìn progress/bytes/sec/strategy.

**Câu 9.** Một `nodetool setcompactionthroughput 0` có “dừng compaction” không?  
**Định hướng:** Trên các phiên bản được mô tả, 0 **bỏ giới hạn throughput**, không phải dừng.

**Câu 10.** File `cassandra.yaml` đã sửa nhưng runtime GET vẫn trả C0. Có nên tuyên bố tuning thất bại?  
**Định hướng:** Chưa; kiểm cơ chế reload/restart và override, xác minh thay đổi thực sự có hiệu lực.

**Câu 11.** Hạ consistency level để đạt p99 mục tiêu có phải một so sánh tuning tương đương không?  
**Định hướng:** Không; đổi bảo đảm dữ liệu/replica, phải được đánh giá như thay hợp đồng consistency.

**Câu 12.** Tại sao không thể rollback hạ `gc_grace_seconds` chỉ bằng đặt lại giá trị cũ?  
**Định hướng:** Tombstone đã purge có thể không trở lại, nguy cơ dữ liệu zombie vẫn còn.

**Câu 13.** Nếu canary phải restart node, khi nào nên đo p99 sau thay đổi?  
**Định hướng:** Sau khi node/pools khỏe và đạt trạng thái cache/workload tương đương; không đo ngay cold start.

**Câu 14.** Có cần đo client retries/physical attempts khi chỉnh cấu hình driver không?  
**Định hướng:** Có; retry có thể giảm user timeout nhưng tăng tải server và latency node khác.

**Câu 15.** Một rollback runtime đã trả C0 nhưng p99 vẫn xấu. Được ghi “đã phục hồi hoàn toàn” chưa?  
**Định hướng:** Không; cần tìm nguyên nhân kéo dài và kiểm SLO, tài nguyên, data correctness.

**Câu 16.** Tại sao áp C0 trở lại ở JMX nhưng để C1 trong cấu hình quản lý lại nguy hiểm?  
**Định hướng:** Lần restart/deploy kế tiếp có thể tự áp C1 trở lại, tạo regression lặp.

**Câu 17.** Trong trường hợp nào nên chọn `HOLD` thay vì `GO` hoặc `ROLLBACK`?  
**Định hướng:** Thiếu mẫu/không cùng tải, cache còn warmup, chưa đủ thông tin hoặc kết quả mâu thuẫn.

**Câu 18.** Nếu giảm backlog bằng cách chạy `nodetool compact` một lần trên production có phải tuning an toàn?  
**Định hướng:** Không; forced major compaction có thể tiêu I/O/đĩa rất lớn, phải có mục đích/headroom và runbook riêng.

**Câu 19.** Truy vấn Java dùng `execute()` rồi mới duyệt 20 pages. Timer dừng tại `execute()` sẽ sai ở đâu?  
**Định hướng:** Nó có thể chỉ đo thời gian đến trang đầu, bỏ chi phí fetch các page sau.

**Câu 20.** Những bằng chứng tối thiểu nào chứng minh rollback thành công?  
**Định hướng:** Effective C0, health/quorum, SLO/resource trở lại mức chấp nhận, đúng dữ liệu và config management không tái áp C1.

## 21. Tổng kết

~~~text
                       RESOURCE TUNING
                              |
                    Thu thập BASELINE
                workload / SLO / resources
                              |
                   Nêu HYPOTHESIS rõ
                     X: C0 -> C1
                              |
                 Guardrails và ROLLBACK
                 định nghĩa TRƯỚC T2
                              |
                       Preflight
                  node / replica / disk
                              |
                       CANARY C1
                              |
                  Đọc effective value
                              |
                  Đủ sample / cùng tải?
                  /                  \
                KHÔNG                CÓ
                  |                   |
                 HOLD            Kiểm các cổng
                              /       |         \
                          DATA      SLO       RESOURCE
                              \       |         /
                                Quyết định
                          /        |         \
                         GO     ROLLBACK    ESCALATE
                         |         |            |
                    Mở theo      Trả C0     Recovery runbook
                     batch       + kiểm SLO   khi có nguy cơ
                         |         |
                    Theo dõi hậu thay đổi
                              |
                 Báo cáo có bằng chứng
~~~

**Nguyên lý cốt lõi:** Một thay đổi cấu hình Cassandra chỉ có giá trị khi **biết hệ thống trước đó hoạt động ra sao**, **đo được nguyên nhân và tác dụng của thay đổi**, **giữ nguyên bảo đảm dữ liệu/consistency**, và **có thể trả về trạng thái vận hành an toàn** khi kết quả không đạt. Tuning đúng không phải giảm số pending bằng mọi giá; đó là cải thiện khả năng phục vụ request dưới workload đại diện **mà không làm tổn hại SLO, replica health, dữ liệu hoặc khả năng khắc phục sự cố**.

## Tài liệu tham khảo

- [Apache Cassandra — Configuration file (cassandra.yaml)](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — tham số memtable, compaction, commit log, cache và các thay đổi phụ thuộc phiên bản.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — JMX Table, ClientRequest, CommitLog, Compaction, ThreadPools và JVM metrics.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTable, flush và compaction.
- [Apache Cassandra — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — strategies, compaction overhead và throughput.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — replica synchronization, tombstone grace và phạm vi repair.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — nguy cơ zombie khi tombstone bị purge quá sớm.
- [Apache Cassandra — Node operations / topology changes](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/topo_changes.html) — bootstrap, decommission, replace, streaming và các rủi ro khi thay ring.
- [Apache Cassandra — nodetool getcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/getcompactionthroughput.html) — đọc giới hạn compaction đang áp dụng.
- [Apache Cassandra — nodetool setcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/setcompactionthroughput.html) — thay giới hạn compaction, cách hiểu giá trị `0`.
- [Apache Cassandra — nodetool compactionstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/compactionstats.html) — backlog và task đang chạy.
- [Apache Cassandra — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) — metric theo table để đối chiếu trước/sau.
- [Apache Cassandra — nodetool tpstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tpstats.html) — các hàng đợi flush, compaction và request stages.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — session/node metrics và cách bật.
- [DataStax Java Driver 4.17 — Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/) — cấu hình session, timeout, pooling và khả năng thay đổi runtime theo phiên bản.
- [DataStax Java Driver 4.17 — Speculative execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — đánh đổi giữa tail latency và thêm physical attempts.

# Streaming/repair throughput và ảnh hưởng đến truy vấn nghiệp vụ

> **Chương:** Tối ưu tài nguyên  
> **Phạm vi:** Apache Cassandra, hệ cơ sở dữ liệu phân tán *wide-column* sử dụng partition key, replica, SSTable và consistency level. Bài tập trung vào **streaming dữ liệu** và **anti-entropy repair** khi chạy chung với truy vấn CQL từ ứng dụng Java.  
> **Mục tiêu:** Phân biệt tốc độ streaming với chi phí repair; hiểu giới hạn băng thông, số công việc đồng thời và tài nguyên đĩa/CPU; đo tác động lên p95/p99 đọc–ghi; xây lịch điều tiết sao cho **không vi phạm SLO** nhưng vẫn hoàn thành repair trong cửa sổ an toàn tombstone.

## 1. Tình huống: repair chạy nhanh hơn nhưng API chậm hơn

Một cluster Cassandra có hai datacenter, mỗi DC có nhiều node và các keyspace dùng `NetworkTopologyStrategy`. Bình thường API Java đọc partition theo khóa và ghi sự kiện ở mức `LOCAL_QUORUM`:

- p99 đọc: khoảng 70 ms.
- p99 ghi: khoảng 45 ms.
- Timeout rất ít; disk và mạng còn khoảng trống.

Đội vận hành vừa tăng băng thông streaming và số phiên repair chạy đồng thời để rút thời gian bảo trì. Sau đó:

- p99 đọc tăng lên 350 ms, write timeout xuất hiện.
- Disk read/write queue tăng; có node network egress sát ngưỡng.
- `nodetool netstats` báo nhiều stream đang hoạt động.
- `nodetool compactionstats` và `nodetool tpstats` cho thấy backlog tăng.

**Không thể kết luận “repair nhanh là tốt” chỉ vì số GiB truyền mỗi giờ tăng.** Với Cassandra, các job nền và request nghiệp vụ chia sẻ **replica, CPU, disk, memory và NIC**. Chạy nhiều công việc hơn có thể làm tất cả cùng chậm, thậm chí repair bị timeout và phải chạy lại.

Bài toán tuning phải giải hai ràng buộc đồng thời:

1. **Tính sẵn sàng và hiệu năng:** p95/p99, error rate và timeout của CQL còn trong SLO khi repair/streaming hoạt động.
2. **An toàn dữ liệu:** repair phải bao phủ đúng replica/token ranges **trước khi khoảng bảo vệ tombstone (`gc_grace_seconds`) trở nên không an toàn**.

Mục tiêu không phải tăng một tham số tới mức cao nhất mà là tìm **throughput hữu dụng lớn nhất khi cluster vẫn đạt SLO và có khoảng dự phòng**.

## 2. Streaming và repair là hai công việc liên quan nhưng không đồng nhất

### Streaming là gì?

**Streaming** là quá trình truyền dữ liệu giữa các node Cassandra theo phạm vi SSTable/partition/token range. Nó xuất hiện trong nhiều thao tác:

- **Bootstrap:** đưa node mới vào topology và nhận dữ liệu cho ranges mà node sở hữu.
- **Rebuild:** dựng dữ liệu trên node, điển hình khi bổ sung datacenter từ replica nguồn.
- **Replace hoặc decommission:** chuyển quyền sở hữu và dữ liệu khi thay/loại node.
- **Repair:** sau khi so sánh replica, cần truyền những phần dữ liệu khác nhau.
- Một số hoạt động quản trị khác tùy phiên bản.

Streaming tạo **network traffic**, nhưng cũng cần **đọc SSTable ở nguồn, ghi dữ liệu tại đích**, kiểm tra dữ liệu và có thể kích hoạt hoạt động lưu trữ bổ sung.

### Repair gồm những gì ngoài streaming?

**Anti-entropy repair** đối soát replica cùng chịu trách nhiệm cho những token ranges. Tùy phiên bản và loại repair, chi phí có thể gồm:

1. Lập kế hoạch session, chọn replica và range.
2. **Validation:** đọc dữ liệu/SSTable để xây, so sánh cấu trúc kiểm tra như Merkle trees.
3. Xác định phần khác biệt.
4. **Streaming:** truyền phần dữ liệu cần đồng bộ khi có khác biệt.
5. Hoàn tất, cập nhật trạng thái repair; incremental repair có thể liên quan tới **anti-compaction** và phân loại repaired/unrepaired SSTable.

**Một repair không truyền gần như byte nào vẫn có thể rất tốn I/O và CPU**, vì validation vẫn phải đọc/so sánh dữ liệu. Ngược lại, bootstrap/rebuild có thể truyền rất nhiều dữ liệu mà không mang cùng mục đích anti-entropy của repair.

```text
REPAIR
  |
  +--> Khởi tạo / chọn token ranges và replica
  |
  +--> Validation: đọc SSTable, tính/so sánh dữ liệu
  |        |                       |
  |        +--> CPU                +--> Disk reads
  |
  +--> Có sai khác?
  |        |
  |        +--> Có: STREAM dữ liệu   -> source disk read + NIC + target disk write
  |        +--> Không: ít/không stream, validation vẫn đã tốn tài nguyên
  |
  +--> Hoàn tất, có thể có anti-compaction/metadata update
  |
  +--> Theo dõi thành công theo range, không chỉ lệnh bắt đầu
```

Bởi vậy, `stream throughput` và `repair throughput` **không phải cùng một chỉ số**.

## 3. Bốn loại throughput cần đo riêng

| Thước đo | Đơn vị thường dùng | Trả lời câu hỏi nào? | Dễ bị hiểu sai thành |
| --- | --- | --- | --- |
| **Network streaming throughput** | Mb/s, MB/s hoặc MiB/s | Node đang truyền bao nhiêu byte/giây? | Toàn bộ tốc độ repair |
| **Validation/scan throughput** | GiB dữ liệu kiểm tra/giờ | Repair đọc và đối soát SSTable nhanh đến đâu? | Chỉ số byte thực sự chuyển qua mạng |
| **Repair coverage throughput** | Token ranges, bảng hoặc phần dữ liệu được đối soát thành công/giờ | Lịch có hoàn tất phạm vi cần bảo vệ không? | Số job được khởi chạy |
| **Business throughput** | CQL request/s, event/s, transaction/s | Ứng dụng vẫn phục vụ được bao nhiêu việc hữu ích? | Mức CPU hoặc băng thông cao |

Ví dụ một repair kiểm tra 800 GiB dữ liệu, chỉ khác 2 GiB:

```text
Dữ liệu validation quét: 800 GiB
Dữ liệu thật sự streaming: 2 GiB
Kết quả: stream bytes thấp nhưng job vẫn có thể tốn hàng giờ.
```

Nếu đặt băng thông streaming cao hơn, thời gian validation có thể **không giảm tương ứng**. Cần xem bottleneck trước khi đổi bất kỳ throttle nào.

### Phân biệt bit và byte

- `Mb/s`: megabit/giây (thường 10^6 bit/giây).
- `MB/s`: megabyte/giây (thường 10^6 byte/giây).
- `MiB/s`: mebibyte/giây, bằng 2^20 byte/giây.
- `1 byte = 8 bit`, chưa tính overhead protocol/TLS/TCP hoặc thay đổi theo nén.

Ví dụ giới hạn `160 Mb/s` tương ứng tối đa khoảng `20 MB/s` theo phép chia bit/byte đơn giản. Nó **không** có nghĩa `160 MB/s`. Khi đọc `nodetool` hoặc file cấu hình, phải xác nhận **đơn vị của phiên bản Cassandra** đang dùng.

## 4. Đường đi của request và nguồn tài nguyên bị cạnh tranh

Giả sử ứng dụng Java đặt local DC là `dc1` và truy vấn partition key rõ ràng:

```text
          JAVA APPLICATION
                 |
                 v
           Coordinator (dc1)
                 |
        +--------+--------+
        |                 |
   Replica A           Replica B       LOCAL_QUORUM chờ đủ ACK
        |                 |
   Memtable/SSTable   Memtable/SSTable
        |                 |
        +--------+--------+
                 |
       Cùng chia sẻ node:
          CPU, memory, cache
          disk / commit log
          network internode
          compaction / repair
```

Lúc repair/streaming chạy, các node này đồng thời có thể đảm nhiệm **source** và **destination** của những stream khác nhau.

### Disk đọc

Validation repair phải duyệt SSTable; streaming nguồn cần đọc dữ liệu. Đọc nghiệp vụ cũng cần SSTable, partition index, bloom filter và dữ liệu liên quan. Trên thiết bị có I/O latency cao hoặc nhiều SSTable/tombstone, sự cạnh tranh có thể khiến:

- Disk await tăng.
- Read request pending tăng.
- Replica trả lời coordinator chậm.
- p99 và read timeout tăng.

### Disk ghi

Node đích streaming ghi dữ liệu nhận được. Đồng thời Cassandra phải:

- Ghi commit log và memtable theo đường mutation.
- Flush memtable thành SSTable.
- Compaction các SSTable.
- Xử lý anti-compaction hoặc công việc lưu trữ liên quan đến repair khi áp dụng.

Thiếu disk throughput hoặc headroom có thể gây backlog, đe dọa cả availability và khả năng kết thúc repair.

### CPU và bộ nhớ

Validation/hashing, serialization, nén/giải nén, TLS và compaction dùng CPU. Buffer, metadata và một số cấu trúc ngoài heap dùng RAM. Khi CPU bão hòa, container bị throttling hoặc GC pause tăng, không chỉ stream bị chậm mà cả CQL executor cũng có thể bị xếp hàng.

### Network

Một node có thể gửi dữ liệu streaming cùng lúc vẫn nhận CQL từ ứng dụng, replication messages và các thông điệp gossip/repair. Trong multi-DC, bão hòa đường truyền WAN ảnh hưởng đến việc replication sang DC kia, dù request `LOCAL_QUORUM` trong DC gần có thể hoàn tất mà không chờ ACK từ DC xa.

**Không đồng nhất “local quorum không chờ remote ACK” với “WAN không quan trọng”.** WAN bão hòa có thể tạo backlog đồng bộ xuyên DC, khiến client ở DC kia đọc dữ liệu chậm cập nhật hơn.

## 5. Hai núm điều tiết chính: tốc độ và mức song song

Tuning streaming/repair thường có **hai nhóm điều khiển tách biệt**.

### Nhóm A — Giới hạn throughput streaming

Các bản Cassandra có cơ chế cấu hình giới hạn tốc độ gửi dữ liệu streaming (outbound) và có thể có giới hạn riêng cho luồng giữa các DC. Những tên tham số điển hình tùy phiên bản gồm:

- `stream_throughput_outbound_megabits_per_sec`;
- `inter_dc_stream_throughput_outbound_megabits_per_sec`.

Một số phiên bản cung cấp lệnh `nodetool` tương ứng để xem/chỉnh ở runtime. Cần đọc help **trên chính node đang dùng** vì tên cờ, cách xử lý streaming entire-SSTable và đơn vị có thể khác giữa các release.

Ví dụ lệnh quan sát trước:

```bash
nodetool help getstreamthroughput
nodetool getstreamthroughput

nodetool help getinterdcstreamthroughput
nodetool getinterdcstreamthroughput

nodetool help setstreamthroughput
nodetool help setinterdcstreamthroughput
```

Đây không phải danh sách lệnh chắc chắn tồn tại trên mọi bản hoặc dịch vụ Cassandra tương thích CQL. Nếu phiên bản không hỗ trợ một lệnh, kiểm tra tài liệu/cấu hình được hỗ trợ thay vì tự phỏng đoán cú pháp.

**Một thay đổi trên một node không tự biến thành giới hạn chung của toàn cluster.** Với outbound throttle theo node, các source nodes vẫn có thể cộng dồn băng thông trên cùng một liên kết mạng.

Ví dụ giả định: mỗi một trong bốn source nodes được phép gửi tới 150 Mb/s; nếu cùng chia sẻ liên kết liên DC chỉ có 400 Mb/s khả dụng, mức **cấu hình cộng dồn** có thể lên tới 600 Mb/s và làm bão hòa đường WAN. Đừng nhầm node-level limit với cluster-level bandwidth budget.

### Nhóm B — Mức song song của công việc

Bao gồm:

- Số node được chạy rebuild/bootstrap/repair đồng thời.
- Số repair sessions/jobs/ranges đang hoạt động.
- Số stream/channels tới từng peer.
- Số tác vụ validation và anti-compaction xuất hiện cùng lúc.
- Cách lịch repair phân bố theo token ranges, replica và datacenter.

Tùy phiên bản, `nodetool repair` có các lựa chọn điều chỉnh mức song song hoặc số jobs; cần xem `nodetool help repair` của node. Một cách an toàn hơn là dùng orchestrator hiểu token range/replica, đặt **giới hạn concurrency trên cả node nguồn lẫn đích**, không chỉ “cho chạy N coordinator”.

### Tại sao chỉ tăng throttle không đủ?

Một stream bị giới hạn tốc độ có thể hoàn tất nhanh hơn khi nâng cap. Nhưng nếu bottleneck là:

- **Validation đọc disk**, nâng network cap gần như không giúp.
- **CPU thiếu**, network cao hơn không tạo CPU thêm.
- **Destination disk write**, nguồn gửi quá nhanh có thể tăng queue.
- **Nhiều repair ranges cùng đánh một replica**, tăng concurrency chỉ nhân chi phí.

Nút thắt quyết định throughput hữu dụng, không phải giá trị cap lớn nhất được phép nhập.

## 6. Cách đọc `nodetool netstats` và các công cụ liên quan

Trên node lab hoặc node production được phép quan sát:

```bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats lab.events_by_device_day
```

| Công cụ | Thông tin hữu ích | Giới hạn |
| --- | --- | --- |
| `nodetool status` | Node/DC nào đang Up/Down và trạng thái topology | `UN` không bảo đảm p99 hay disk khỏe |
| `nodetool netstats` | Tiến độ streaming, các session send/receive và thống kê mạng tùy phiên bản | Không cho biết toàn bộ chi phí validation/anti-compaction |
| `nodetool compactionstats` | Compaction đang chạy/đợi, khối lượng xử lý và một số tác vụ liên quan | Không thay thế thông tin token ranges repair đã thành công |
| `nodetool tpstats` | Các thread pool/stage active, pending, completed, dropped messages | Một snapshot không đủ chứng minh queue kéo dài |
| `nodetool tablestats` | Dung lượng/SSTable/memtable/độ trễ theo bảng | Không mô tả hết băng thông NIC hay full end-to-end API latency |

### Nguồn đo ngoài Cassandra

```bash
vmstat 1
iostat -xz 1
pidstat -u -p <pid> 1
```

Tùy OS có thể cần công cụ mạng như `sar`, telemetry của switch/firewall/WAN và metrics từ container/cgroup. Với Java/JVM, xem GC pause, heap/off-heap/RSS và CPU throttling để không bỏ sót nguyên nhân chạy chậm.

Tất cả các lệnh trên là **quan sát**; không chạy thay đổi compaction/repair ở production khi chưa có cửa sổ bảo trì và runbook.

### Số GiB chuyển không đủ để biết tác động

Giả sử trong 10 phút có 100 GiB được stream:

- Nếu đọc/ghi trên SSD còn headroom, p99 CQL vẫn ổn thì có thể chấp nhận.
- Nếu read p99 tăng gấp năm và compaction pending cao, cùng tốc độ đó là quá mức.
- Nếu stream nhanh nhưng phải chạy lại vì timeout/error, throughput **hữu dụng** của cả chu kỳ có thể thấp.

Luôn ghép throughput với **tỷ lệ thành công của repair, thời gian hoàn tất và SLO nghiệp vụ**.

## 7. Lập ngân sách mạng và I/O theo node, replica, DC

### Giả lập một cụm RF=3

Giả sử dc1 có 6 node, mỗi node giữ một phần dữ liệu của keyspace dùng RF=3; ứng dụng đọc/ghi liên tục với `LOCAL_QUORUM`.

Repair do node N1 điều phối có thể kéo các replica N2 và N3 vào validation và streaming. Một repair song song khác do N4 điều phối có thể dùng lại N2. **N2 bị tải từ hai repair** dù trên dashboard mỗi coordinator chỉ có một job.

```text
Repair job A:  Coordinator N1 ---> Replica N2 <--- Coordinator N4 :Repair job B
                                  |
                          chung CPU / disk / NIC
                                  |
                         CQL replicas đang phục vụ
```

Lịch phải kiểm tra **điểm giao của replica**, không chỉ chia số node cho số jobs.

### Ước lượng thời gian truyền theo cap

Một ví dụ giả định: cần stream **300 GiB** giữa hai nhóm node qua một liên kết, throughput hữu dụng quan sát được **150 Mb/s**:

```text
300 GiB ≈ 300 × 2^30 byte
         ≈ 2,58 × 10^12 bit

Thời gian tối thiểu vì mạng ≈ 2,58 × 10^12 / (150 × 10^6)
                           ≈ 17.180 giây ≈ 4,8 giờ
```

Đây là **ước tính theo băng thông một chiều**, chưa tính protocol overhead, tranh mạng, biến động nguồn/đích, disk và lỗi stream. Nếu repair còn validation 2 TiB dữ liệu, không thể lấy 4,8 giờ làm thời gian toàn job.

### Ngân sách an toàn không dùng toàn bộ NIC

Dù một NIC có tốc độ danh nghĩa 10 Gb/s, băng thông ứng dụng, replication, backup, repair và lưu lượng khác vẫn phải chia sẻ. Nên đo lưu lượng **thực tế lúc cao điểm**, xác định phần dự phòng cần giữ và đặt tổng throughput streaming sao cho không làm queue và p99 vi phạm SLO.

Với liên kết WAN giữa DC, xem cả **tốc độ truyền khả dụng**, latency, packet loss, egress cost và đường dự phòng. Đặt inter-DC stream throttle độc lập khi phiên bản hỗ trợ có thể giúp ngăn rebuild một DC làm nghẽn replication nghiệp vụ.

## 8. Tác động lên đường đọc: p99, SSTable và tombstone

Một câu đọc theo partition key thường:

1. Driver chọn coordinator (ưu tiên DC cục bộ theo policy).
2. Coordinator xác định replica dựa trên token và RF.
3. Replica đọc memtable/cache/SSTable theo yêu cầu.
4. Coordinator chờ đủ phản hồi theo consistency level.
5. Driver trả kết quả cho ứng dụng.

Khi repair chạy nặng, **disk read bandwidth/latency của replica** có thể bị cạnh tranh. Điều này đặc biệt rõ khi:

- Một partition trải qua nhiều SSTable vì compaction backlog.
- Nhiều cell đã TTL-expire hoặc bị xóa, khiến scan tombstone cao.
- Query đọc dải clustering rất rộng.
- Có hot partitions, khiến ít replica nhận phần lớn read traffic.
- Repair validation phải quét nhiều SSTable ngay tại những replica đó.

```text
Repair validation đọc SSTable --> disk queue tăng
                                  |
CQL SELECT cũng đọc SSTable ------+
                                  |
                         replica read latency tăng
                                  |
               coordinator đợi LOCAL_QUORUM lâu hơn
                                  |
                        API Java p99 / timeout tăng
```

### Vì sao `LIMIT 20` vẫn có thể chậm?

`LIMIT 20` giới hạn số hàng **trả về**, không giới hạn số cell/SSTable vật lý phải xét trước khi tìm đủ hàng sống. Nếu một partition có nhiều tombstone, repair/compaction làm disk bận có thể đẩy p99 lên mạnh hơn nữa.

Tối ưu streaming mà bỏ qua **partition key, TTL/delete pattern và SSTable count** có thể làm sai hướng chẩn đoán: nguyên nhân gốc là read amplification, còn repair chỉ làm lộ rõ thiếu headroom của đĩa.

## 9. Tác động lên đường ghi: commit log, memtable, replication

Ghi Cassandra đến replica phải xử lý commit log và memtable; flush và compaction đến sau. Repair/streaming ghi tại node đích chia sẻ cùng storage và một phần CPU/network.

Hệ quả:

- **Commit log fsync/ghi:** latency storage tăng có thể ảnh hưởng thời gian ACK theo chính sách và tải của node.
- **Memtable flush:** có thể chậm khi disk write queue cao; dữ liệu chưa flush tích lũy.
- **Compaction backlog:** nhiều SSTable cần hợp nhất nhưng disk đang dành cho stream.
- **Replica ACK:** nếu một replica cần thiết quá chậm, coordinator không đạt consistency level kịp thời.
- **Inter-DC replication:** luồng mutation đi sang DC xa có thể bị ảnh hưởng bởi băng thông WAN bị streaming chiếm.

Một write timeout **không chứng minh mutation chưa được replica nào nhận**. Với ứng dụng Java, retry cần xét idempotency và timestamp/TTL, đặc biệt trong điều kiện repair chạy giữa các thay đổi topology.

### LOCAL_QUORUM không loại bỏ rủi ro gián tiếp từ WAN

Với RF=3 mỗi DC, `LOCAL_QUORUM` tại dc1 chỉ cần hai ACK của dc1. Khi link WAN tắc do rebuild dc2:

- CQL ghi tại dc1 vẫn có thể hoàn tất nếu các replica local khỏe.
- Nhưng mutation sang dc2 có thể đến chậm, và các đọc `LOCAL_QUORUM` **ở dc2** có thể chưa thấy giá trị mới.
- Nếu đĩa/NIC dc1 cũng bị tải streaming lớn, chính CQL local có thể chậm.

Tối ưu phải xét **SLO của cả hai DC** và yêu cầu dữ liệu mới đến DC dự phòng trong bao lâu.

## 10. Thực hành CQL: mẫu bảng và truy vấn dùng để đo

Ví dụ dùng keyspace `lab` đã tồn tại trong cluster thử nghiệm. Bảng lưu sự kiện theo thiết bị và ngày để partition có giới hạn hơn việc gom toàn bộ lịch sử của thiết bị:

```cql
CREATE TABLE IF NOT EXISTS lab.events_by_device_day (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Ghi một dữ liệu minh họa:

```cql
INSERT INTO lab.events_by_device_day
    (device_id, event_day, event_time, event_id, event_type, payload)
VALUES (
    'device-01',
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'heartbeat',
    'ok'
);
```

Đọc bằng partition key đầy đủ:

```cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, event_id, event_type, payload
FROM lab.events_by_device_day
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21'
LIMIT 50;
```

Trong `cqlsh`, `CONSISTENCY LOCAL_QUORUM` đặt CL cho phiên CQL đang kết nối. Để đánh giá đúng multi-DC, cần biết node coordinator mà `cqlsh` kết nối tới, RF từng DC và trạng thái replica.

Mẫu này dùng để **đo latency của một partition thực**, không phải tạo tải quá lớn để gây nghẽn. Benchmark cần nhiều partition, nhiều node, dữ liệu đủ lớn, các đường đọc/ghi và phân phối skew đại diện.

### Tracing có ích khi nào?

```cql
TRACING ON;

SELECT event_time, event_id, event_type, payload
FROM lab.events_by_device_day
WHERE device_id = 'device-01'
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
```

Tracing giúp xem một request mẫu đi qua coordinator/replica nào, nhưng **không tự cho biết bandwidth streaming toàn cluster** và có overhead. Kết hợp tracing với `tpstats`/`netstats`, metrics của node và driver thay vì bật trace 100% trong giờ cao điểm.

## 11. Lệnh quan sát và thay đổi throughput trong lab

### Bước A — Chụp baseline trước khi streaming/repair

```bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats lab.events_by_device_day

nodetool getstreamthroughput
nodetool getinterdcstreamthroughput
```

Ghi timestamp, Cassandra version, DC, RF, tên node, số GiB được quản lý và các giới hạn thực tế. Nếu phiên bản không có một trong hai lệnh `get...`, tra cấu hình/hướng dẫn tương ứng, **không chạy lệnh `set...` theo suy đoán**.

### Bước B — Hiểu thao tác cấu hình trước khi thay đổi

Các bản Cassandra có thể hỗ trợ những lệnh runtime tương tự:

```bash
nodetool help setstreamthroughput
nodetool help setinterdcstreamthroughput
nodetool help repair
```

Ví dụ **minh họa cú pháp phổ biến** trong lab, chỉ dùng sau khi kiểm tra đơn vị và cờ bằng `help`:

```bash
# Ví dụ: đặt giới hạn outbound streaming trên node đang quản trị.
# Kiểm tra release để xác nhận "200" được hiểu theo đơn vị nào.
nodetool setstreamthroughput 200

# Ví dụ: giới hạn outbound streaming giữa các datacenter.
# Tên lệnh / tùy chọn có thể khác theo phiên bản.
nodetool setinterdcstreamthroughput 100
```

**Không copy hai lệnh đặt giá trị vào production.** Đây là thao tác thay đổi tài nguyên, có thể chỉ tác động một node và có khác biệt giữa streaming thường/entire-SSTable streaming. Đọc lại `get...` và quan sát actual throughput để xác nhận thay đổi thực sự có hiệu lực.

### Bước C — Kiểm chứng khi có công việc thực

Ở cluster lab, một lượt repair giới hạn phạm vi theo kế hoạch có thể dùng `nodetool repair` với primary ranges và keyspace phù hợp:

```bash
nodetool help repair

# Chỉ minh họa: repair primary ranges của node cho keyspace lab
# Theo phiên bản, chế độ full/incremental và mức song song cần chọn rõ.
nodetool repair -pr lab
```

Lệnh này **không repair toàn cluster chỉ vì chạy một lần trên một node**. Muốn bao phủ tất cả ranges/replica phải có lịch điều phối đầy đủ; không khởi chạy đồng thời trên mọi node khi chưa biết topology và tác động tài nguyên.

Khi repair chạy, quan sát:

```bash
nodetool netstats
nodetool compactionstats
nodetool tpstats
```

Và lấy metrics JVM/OS/driver với thời gian đồng bộ. Thử ở tải đại diện; nếu repair cần stream gần 0 byte, kết quả thí nghiệm chủ yếu phản ánh **validation**, không đủ để kết luận về throttle network khi stream lớn.

## 12. Phân biệt giới hạn streaming với compaction throughput

Trong Cassandra, `compaction throughput` và `stream throughput` là những cơ chế điều tiết **khác nhau**. Tùy release có công cụ như `nodetool getcompactionthroughput` và `setcompactionthroughput`.

| Giới hạn | Chủ yếu tác động | Không trực tiếp giới hạn |
| --- | --- | --- |
| Streaming outbound throughput | Tốc độ dữ liệu stream gửi ra node/giữa DC theo cấu hình | Toàn bộ validation reads, toàn bộ compaction, CQL request |
| Compaction throughput | Mức tài nguyên/byte dành cho compaction theo cách thực thi phiên bản | Mọi network streaming và coordinator read path |
| Repair concurrency/jobs | Số hoạt động repair có thể chạy song song | Mỗi node luôn chỉ nhận một session hoặc mọi stream đều có giới hạn riêng |
| Scheduling window | Thời điểm/cụm phạm vi được chạy | Tốc độ tức thời nếu không đặt throttle/concurrency |

**Throttle streaming thấp không bảo đảm query ổn** nếu validation vẫn đang saturate disk. **Throttle compaction rất thấp cũng không tự giúp**, vì để tồn SSTable/compaction backlog có thể khiến read amplification và dung lượng disk tăng.

Một thay đổi đúng phải xem **công việc nền nào** thực sự đang cạnh tranh với đường đọc/ghi.

## 13. Điều phối theo mức tải thay vì tốc độ cố định

Một chính sách thực tế có thể phân ra ba chế độ, áp dụng bằng orchestrator và thông số hỗ trợ của phiên bản:

| Chế độ | Điều kiện | Hướng điều tiết |
| --- | --- | --- |
| **Giờ cao điểm** | p99 sát SLO, lưu lượng client cao | Giảm số job repair song song, dành network/disk cho truy vấn |
| **Giờ thấp điểm** | CPU/disk/network còn headroom; p99 ổn | Tăng song song/throttle có kiểm soát nếu completion budget cần |
| **Sự cố hoặc phục hồi DC** | Node thiếu dữ liệu hoặc grace budget sắp hết | Ưu tiên an toàn, giới hạn concurrency nhưng tăng capacity/giảm tải ứng dụng theo runbook |

Không nên hiểu bảng này như chính sách “dừng repair trong giờ cao điểm bằng mọi giá”. Nếu trì hoãn quá lâu làm khoảng cách repair thành công vượt `gc_grace_seconds`, nguy cơ zombie data tăng. Khi không thể đồng thời đáp ứng SLO và deadline, cần giải quyết **capacity và kế hoạch vận hành**, không chỉ giảm tốc vô hạn.

### Chính sách điều khiển phản hồi theo metric

Một vòng điều chỉnh thận trọng:

1. Đặt baseline: p99, timeout, read/write throughput, disk await/queue, CPU, NIC, backlog và repair coverage.
2. Chọn mức concurrency/throughput bắt đầu tương đối thấp.
3. Chạy trên **một tập range/node** với giới hạn rõ.
4. Đo tác động trong khoảng đủ dài, có tính đến burst và GC/compaction nền.
5. Nếu SLO và headroom còn tốt, chỉ tăng **một tham số mỗi lần**.
6. Nếu p99, dropped messages hoặc queue vượt ngưỡng, giảm hoạt động nền theo runbook.
7. Ghi lượng dữ liệu thực sự đã được repair/stream thành công, cập nhật lịch những range còn thiếu.

Tránh vòng điều khiển quá nhạy, mỗi phút tăng–giảm nhiều lần: repair/streaming không luôn phản ứng tức thì với thay đổi throttle, và số liệu p99 cần một cửa sổ quan sát đủ đại diện.

## 14. Ví dụ benchmark có kiểm soát

Một cluster lab có workload đại diện. Đo hai mức outbound streaming và mức song song khác nhau. Số dưới đây **hoàn toàn giả định**:

| Phương án | Source jobs đồng thời | Cap outbound mỗi source | Stream hữu dụng | CQL read p99 | CQL write p99 | Kết quả |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline không repair | 0 | — | — | 65 ms | 42 ms | Mốc so sánh |
| A | 1 | 100 Mb/s | 85 Mb/s | 76 ms | 49 ms | Tải nền thấp |
| B | 2 | 200 Mb/s | 300 Mb/s tổng | 105 ms | 68 ms | Có thể phù hợp nếu SLO cho phép |
| C | 4 | 400 Mb/s | 450 Mb/s tổng | 320 ms | 240 ms | Không đạt SLO, nghẽn tài nguyên |

Ở phương án C, dù giới hạn lý thuyết của các source rất cao, **stream hữu dụng không tăng tương ứng** vì disk/NIC/CPU đã thành nút thắt. Độ trễ request nghiệp vụ lại tăng mạnh.

Đây không phải bằng chứng B là cấu hình tốt nhất cho mọi cluster. Nếu workload có tombstone nhiều, đĩa chậm, RF khác hoặc đường WAN nhỏ hơn, điểm tối ưu sẽ khác. Cũng cần đo **thời gian repair hoàn tất thành công**, không chỉ một cột tốc độ stream.

### Một thí nghiệm tốt phải giữ cố định những gì?

- Cùng schema, partition key, kiểu truy vấn và dữ liệu đại diện.
- Cùng RF/CL/local DC, loại repair, token ranges và replica source/target.
- Cùng lưu lượng CQL hoặc profile tải có thể tái tạo.
- Cùng phiên bản Cassandra/JVM và điều kiện disk/cache tương đương.
- Theo dõi cả error rate, timeouts, stream failures và repair coverage.
- So sánh qua đủ chu kỳ background tasks; không kết luận từ một burst ngắn.

## 15. Quan sát từ Java Driver 4.x

Ứng dụng Java nên đo **trọn đường client request** để phản ánh SLO và phân biệt coordinator. Ví dụ đọc một partition với Java Driver 4.x:

```java
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Node;

public final class EventReadProbe {
    private final CqlSession session;
    private final PreparedStatement prepared;

    public EventReadProbe(CqlSession session) {
        this.session = session;
        this.prepared = session.prepare(
            "SELECT event_time, event_id, event_type, payload " +
            "FROM lab.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT ?"
        );
    }

    public int readDay(String deviceId, LocalDate day) {
        BoundStatement statement = prepared.bind(deviceId, day, 50)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true)
            .setPageSize(50);

        long startNs = System.nanoTime();
        try {
            ResultSet result = session.execute(statement);
            Node coordinator = result.getExecutionInfo().getCoordinator();

            int count = 0;
            for (Row row : result) {
                count++;
            }

            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNs);

            System.out.printf(
                "read_ms=%d count=%d coordinator_dc=%s%n",
                durationMs,
                count,
                coordinator == null ? "unknown" : coordinator.getDatacenter());
            return count;
        } catch (RuntimeException ex) {
            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNs);
            System.err.printf(
                "read_error_ms=%d type=%s%n",
                durationMs, ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
```

Giả định `CqlSession` được cấu hình đúng contact points, authentication, local DC, keyspace và các node có RF phù hợp `LOCAL_QUORUM`. `setIdempotent(true)` là khai báo phù hợp cho SELECT thông thường; **không tự bật speculative execution**.

Code minh họa ghi log từng request chỉ để dễ học; trong production, hãy xuất **histogram/metrics có sampling và nhãn hợp lý**, không in mỗi call tốc độ cao. Phải đo cả **lỗi**, nếu chỉ tính các request thành công sẽ che các lần timeout tăng khi streaming nặng.

### Bốn phép đo song song

1. **Java API p99** theo operation/customer cohort.
2. **Driver request latency, in-flight/queue, timeouts/retries** và coordinator host/DC.
3. **Cassandra client request latency** theo node/loại read-write.
4. **Replica resource metrics** trên các node đang tham gia stream/validation.

Không trừ trực tiếp `API p99 – Cassandra p99` để lấy “WAN p99”, vì phân vị của hai phân phối không có phép trừ như vậy. Muốn quy trách nhiệm chính xác cần traces có cùng request, timestamps và sampling phù hợp.

## 16. Repair phải nằm trong ngân sách `gc_grace_seconds`

Một thao tác `DELETE` ghi tombstone để chặn dữ liệu cũ trên SSTable/replica khác. Nếu replica offline bỏ lỡ xóa và tombstone bị purge trước khi repair/khôi phục phù hợp, giá trị cũ có thể sống lại (*zombie data*).

Vì thế, **giảm throughput để giữ p99 đẹp nhưng khiến repair mãi không hoàn tất cũng không an toàn**.

### Ngân sách thời gian bảo thủ

Đặt:

- `G`: thời gian grace áp dụng cho dữ liệu có nguy cơ, thường tham chiếu `gc_grace_seconds` cấp bảng.
- `I`: khoảng cách giữa các lần bắt đầu chu kỳ repair.
- `D`: thời gian dài nhất để hoàn tất coverage đúng ranges/replica.
- `F`: thời gian dự phòng sự cố, node offline, retry.
- `M`: khoảng đệm an toàn cho biến động tải.

Một quy tắc vận hành bảo thủ:

```text
I + D + F + M < G
```

Đây không phải công thức nội bộ Cassandra. Nó là công cụ lập kế hoạch để tránh việc repair kéo dài/có lỗi vượt qua cửa sổ bảo vệ xóa. Điều quan trọng hơn cả là **khoảng thời gian từ lần repair thành công cuối của từng range/bảng/DC**, không chỉ số job bắt đầu.

Ví dụ với `G = 10 ngày`:

| Thành phần | Kế hoạch A | Sau khi giảm throughput quá mức |
| --- | ---: | ---: |
| Chu kỳ khởi chạy `I` | 4 ngày | 4 ngày |
| Hoàn tất `D` | 2 ngày | 4 ngày |
| Sự cố/retry `F` | 2 ngày | 2 ngày |
| Đệm `M` | 1 ngày | 1 ngày |
| Tổng | 9 ngày | 11 ngày |
| An toàn theo quy tắc | Đạt | **Không đạt** |

Nếu throughput giảm làm repair kéo dài tới bốn ngày, không nên chỉ chấp nhận lịch mới. Cần **tăng capacity, giảm dữ liệu phải xử lý, đổi concurrency/thời điểm, chia ranges hợp lý hoặc xem lại grace có căn cứ**. Không hạ `gc_grace_seconds` tùy tiện để GC nhanh hơn: nó làm cửa sổ bảo vệ ngắn lại.

### Khi node mất kết nối lâu

Nếu một replica offline dài hơn grace và có thể giữ dữ liệu cũ, **chạy repair trễ không bảo đảm tự loại mọi rủi ro zombie** nếu các tombstone cần thiết đã bị thu hồi ở replica lành. Cần đánh giá runbook rebuild/replace/restore phù hợp với phiên bản và tình trạng nguồn.

## 17. Full, incremental repair và chi phí tài nguyên

Cassandra có các chế độ repair tùy version:

- **Full repair:** đối soát dữ liệu trong phạm vi được chọn rộng hơn; có thể tốn I/O và thời gian hơn.
- **Incremental repair:** tập trung vào dữ liệu unrepaired theo cơ chế repaired SSTable/anti-compaction ở phiên bản tương ứng.

Không được kết luận incremental luôn rẻ hơn full trong mọi tình huống hoặc repair nào cũng stream nhiều byte. Trong workload đã đồng bộ tốt, validation/anti-compaction có thể là thành phần tiêu tốn tài nguyên chính.

Để chọn throughput/concurrency, phải ghi rõ:

1. Cassandra version và chế độ full/incremental cụ thể.
2. Bảng, token ranges, datacenter và replica tham gia.
3. Dung lượng SSTable repaired/unrepaired và tốc độ cập nhật.
4. Lượng validation data, stream bytes, anti-compaction và kết quả ranges thành công.
5. Rủi ro overlap với các job repair/compaction/backup khác.

Một chỉ số repair “completed” của một node không đồng nghĩa cả cluster đã repair xong. Phải theo dõi **coverage theo token range và replica**.

## 18. Các kịch bản sự cố và cách phản ứng

### A — Streaming cap cao nhưng network throughput thấp

**Triệu chứng:** đã tăng cap, `netstats` vẫn truyền chậm; p99 nghiệp vụ không cải thiện hoặc không thay đổi.

**Kiểm tra:** disk đọc nguồn/ghi đích, CPU/TLS, packet loss, cap khác (inter-DC, QoS), số stream hoạt động, chênh lệch dữ liệu thực sự và trạng thái validation.

**Hướng xử lý:** xác định bottleneck thực rồi mới đổi throttle; đừng tăng cap nữa nếu network không phải nút thắt.

### B — Stream bytes rất nhỏ nhưng repair quá lâu

**Triệu chứng:** replica gần đồng nhất, hầu như không stream nhưng job dài nhiều giờ.

**Kiểm tra:** validation scanning, Merkle tree, SSTable count, CPU, disk queue, anti-compaction và cách chia ranges.

**Hướng xử lý:** tối ưu concurrency/đặt cửa sổ phù hợp cho validation và I/O; tăng bandwidth stream không đủ để chữa.

### C — API read p99 tăng đúng lúc repair

**Triệu chứng:** `Pending READ`, disk read await và compaction pending tăng cùng repair.

**Kiểm tra:** replica nào cùng nhận CQL và validation, hot partitions, SSTable count, tombstone scanned.

**Hướng xử lý:** giảm job song song gây trùng replica, dời cửa sổ, xử lý compaction backlog hoặc tối ưu schema/query nếu nó gây read amplification nặng.

### D — Ghi bị timeout khi node đích đang stream

**Triệu chứng:** disk write queue, commit log latency, pending mutation tăng; coordinator không đủ ACK theo CL.

**Kiểm tra:** storage bandwidth/headroom đích, flush, compaction, RF/CL, node nào là replica của partition.

**Hướng xử lý:** giảm stream write pressure và cải thiện năng lực đĩa; ứng dụng phải xử lý write timeout như **trạng thái kết quả chưa chắc chắn**, không retry thao tác không idempotent bừa bãi.

### E — Mở DC mới làm ứng dụng DC cũ chậm

**Triệu chứng:** source DC gửi quá nhiều streaming sang DC mới, WAN hoặc disk source bão hòa.

**Kiểm tra:** inter-DC throttle, các source nodes gửi đồng thời, hiệu ứng lên replication nghiệp vụ và failover readiness.

**Hướng xử lý:** giới hạn tổng lưu lượng theo link thực, chia đợt rebuild, đo lag/độ mới dữ liệu và đừng bật traffic DC mới trước khi xác minh ranges.

### F — Tăng concurrency làm repair chậm hơn

**Triệu chứng:** số session đồng thời nhiều hơn, stream error/retry và GC/compaction tăng; runtime chu kỳ kéo dài.

**Kiểm tra:** replica overlap, CPU throttling, disk await và NIC saturation; đo **completed successful ranges/giờ**.

**Hướng xử lý:** giảm concurrency, cho các range chạy tránh tranh replica, tăng throughput ổn định thay vì tổng throughput tức thời không bền.

### G — Throughput bị giảm mạnh, repair không kịp grace

**Triệu chứng:** p99 ổn sau throttle nhưng những ranges chưa repair gần vượt deadline an toàn.

**Kiểm tra:** lịch repair thành công, `gc_grace_seconds` các bảng, tuổi node offline, duration forecast và recovery margin.

**Hướng xử lý:** bổ sung năng lực, ưu tiên ranges rủi ro, điều phối tải hoặc điều chỉnh kế hoạch. Không chấp nhận một lịch “không ảnh hưởng SLO” nếu nó có thể làm dữ liệu sai.

## 19. Dashboard và cảnh báo cần có

Một dashboard tuning nên hiển thị theo **cluster → DC → node → công việc → ứng dụng**:

| Nhóm | Chỉ số nên thu thập | Câu hỏi |
| --- | --- | --- |
| Streaming | Bytes sent/received, throughput theo node/peer/DC, active/error sessions | Data đang di chuyển ở đâu, có ổn định không? |
| Repair | Validation duration, ranges thành công/thất bại, time since last success | Tiến độ coverage có kịp deadline không? |
| Disk | Read/write latency, queue, IOPS, throughput, free space | Storage có bị cạnh tranh quá mức không? |
| Compaction | Active/pending, bytes processed, backlog | I/O nền có bị đẩy nợ sang tương lai? |
| CPU/GC | CPU usage, throttling, heap/native, GC pause | Node có còn compute headroom? |
| Network | NIC/WAN throughput, packet loss, retransmits, RTT | Giới hạn là link hay node? |
| CQL | Read/write p95/p99, timeouts, unavailable, coordinator/replica | Business SLO có bị ảnh hưởng không? |
| Driver | Request latency, inflight, errors/retries, local DC | Client đang chịu thêm gì? |
| Topology | RF/DC, node health, token range ownership | Lịch có chạy đúng phạm vi không? |

### Ba cảnh báo trọng yếu

1. **Business SLO degradation:** p99 hoặc timeout vượt ngưỡng trong khi streaming/repair đang hoạt động.
2. **Repair coverage deadline:** có range/bảng chưa thành công quá lâu, ngân sách trước `gc_grace_seconds` sắp cạn.
3. **Resource saturation:** disk await/queue, GC pause, CPU throttle hoặc network saturation kéo dài đồng thời khiến throughput hữu dụng giảm.

Thêm cảnh báo stream error/retry nhiều lần và disk headroom thấp. Khi alert, phải có hành động phân loại: **giảm job/stream** nếu cluster bão hòa, hoặc **tăng capacity/ưu tiên repair** nếu deadline đe dọa an toàn. Không tự động tăng timeout trong mọi tình huống.

### Chú ý cách tổng hợp metrics

- Counter byte và lỗi cần tính **rate**, có xử lý reset khi node restart.
- `p99 toàn cluster` không phải trung bình các p99 node.
- Phân tích theo DC/rack, tránh trung bình che một replica cực chậm.
- Dùng timestamp đồng bộ để ghép job repair, compaction, GC và API latency.
- Tránh nhãn partition key cho tất cả metrics vì cardinality rất lớn; dùng sampling khi tìm hot partition.

## 20. Runbook điều tiết có thể triển khai

### Trước thay đổi

1. Xác nhận mục đích: bootstrap, rebuild, replace hay repair; mỗi loại có chi phí khác nhau.
2. Kiểm tra RF, token ranges, DC/rack, trạng thái replica nguồn/đích và lịch repair gần nhất.
3. Đo baseline CQL p95/p99, timeout, disk, CPU, network, compaction và ứng dụng.
4. Tính dung lượng cần validate/stream và độ bất đối xứng nguồn–đích.
5. Kiểm tra cấu hình throttle, đơn vị, scope theo node/DC và runtime support của phiên bản.
6. Xác định completion deadline liên quan đến `gc_grace_seconds` nếu là repair bảo vệ tombstone.

### Trong lúc chạy

7. Bắt đầu với số job và throttle đã được thử nghiệm trên phạm vi nhỏ.
8. Ghi tiến độ thành công theo range/node, stream throughput và chi phí validation.
9. Quan sát p99, timeout, `tpstats` pending/dropped, disk await, compaction và GC.
10. Nếu vượt SLO, giảm áp lực ở **nút thắt đang xác minh**; tránh thay nhiều núm cùng lúc.
11. Nếu còn headroom nhưng job dự báo trễ, tăng concurrency/throttle **từng bước** và đo lại.
12. Không khởi chạy thêm repair trùng ranges khiến các replica đang bận nhận tải nhân đôi.

### Sau hoàn tất

13. Đối chiếu mọi ranges/replica dự kiến đã repair/stream thành công; không chỉ thấy process exit 0.
14. Kiểm tra backlog compaction/flush và dung lượng đĩa sau hoạt động.
15. So sánh p95/p99/error rate với baseline, xem hiệu ứng chậm còn kéo dài sau job không.
16. Kiểm tra dữ liệu/replica cần thiết trước chuyển traffic, đặc biệt sau rebuild datacenter.
17. Lưu cấu hình cuối cùng, số liệu, phạm vi, thời gian và hướng xử lý retry cho chu kỳ sau.

**Không xóa SSTable thủ công, ép `gc_grace_seconds=0` hoặc chạy repair/full compact toàn cluster chỉ để thử throughput.** Đây là thao tác nhạy với dữ liệu và tài nguyên, cần runbook riêng.

## 21. Những ngộ nhận thường gặp

**“Repair càng stream nhiều GiB/giây càng tốt.”** Sai. Repair còn validation và cần đạt SLO cùng completion deadline; nhiều stream có thể tạo lỗi và tăng p99.

**“Không có streaming nghĩa là repair không tốn I/O.”** Sai. Validation có thể phải đọc nhiều SSTable dù replica hoàn toàn giống nhau.

**“`setstreamthroughput` đặt giới hạn băng thông cho cả cluster.”** Không nên giả định. Cấu hình thường có phạm vi node/outbound, và các nguồn có thể cộng tải trên một link.

**“Đặt streaming throttle thấp sẽ chắc chắn bảo vệ CQL.”** Sai. Validation/anti-compaction/compaction và CPU vẫn có thể cạnh tranh tài nguyên.

**“Repair dùng toàn bộ mạng thì `LOCAL_QUORUM` vẫn miễn nhiễm.”** Sai. Replica local vẫn chia sẻ disk/NIC/CPU; traffic cross-DC có thể đến chậm, ảnh hưởng data freshness/failover.

**“Thấy `nodetool netstats` trống tức là repair đã hoàn thành.”** Sai. Repair có thể đang validation, tạm dừng, lỗi hoặc chưa chạy đủ ranges.

**“Tăng concurrency từ 2 lên 8 làm job nhanh hơn 4 lần.”** Không chắc. Replica overlap, disk và network contention có thể khiến runtime dài hơn.

**“Disk còn dung lượng thì có thể stream tối đa.”** Sai. Free space khác IOPS/throughput/latency và cần headroom trong lúc compaction.

**“Chỉ cần chỉnh timeout ứng dụng khi repair chạy.”** Sai. Timeout dài có thể che nghẽn và tăng số request inflight mà không cải thiện throughput.

**“Full/incremental repair đều giống nhau về chi phí.”** Sai. Phạm vi validation, trạng thái SSTable và anti-compaction thay đổi theo loại và phiên bản.

**“Repair chạy một lần trên N1 là toàn keyspace đã repair xong.”** Sai. Cần kiểm chứng ownership/token ranges/DC và kết quả trên toàn tập replica yêu cầu.

**“Giảm repair vì p99 tăng thì luôn an toàn.”** Sai nếu deadline trước `gc_grace_seconds` không còn được bảo đảm.

## 22. Bài tập thực hành

1. Một repair validation 1 TiB dữ liệu nhưng stream chỉ 500 MiB. Vì sao `setstreamthroughput` gấp đôi có thể không giúp rút thời gian repair?
2. Phân biệt GiB dữ liệu được scan, GiB được streamed và số token ranges repair thành công. Chỉ số nào trực tiếp phản ánh coverage?
3. Liên kết inter-DC còn 400 Mb/s headroom. Bốn source nodes đều được cap 150 Mb/s. Tại sao tổng traffic có thể gây nghẽn?
4. Trong phép tính đơn giản, 160 Mb/s tương ứng bao nhiêu MB/s? Vì sao không coi đó là throughput TCP thực tế?
5. Khi disk read await, pending READ và API p99 cùng tăng lúc repair, bạn sẽ kiểm tra thứ tự nguyên nhân như thế nào?
6. Vì sao một coordinator `LOCAL_QUORUM` ở dc1 vẫn có thể bị ảnh hưởng bởi streaming giữa dc1 và dc2?
7. Nếu destination disk write đầy tải, tăng outbound cap ở source có giải quyết được không?
8. Repair chạy hai coordinator nhưng cùng chạm replica N2. Vì sao cần giới hạn concurrency theo *replica* thay vì chỉ coordinator?
9. Một cụm có grace 10 ngày: `I=4`, `D=4`, `F=2`, `M=1`. Lịch có đạt quy tắc bảo thủ không? Nêu ít nhất hai cách xử lý.
10. So sánh điều tiết streaming throughput và điều tiết compaction throughput; vì sao một loại không tự thay thế loại kia?
11. Java Driver ghi `LOCAL_QUORUM` timeout khi repair chạy. Vì sao retry mù có thể gây trùng tác dụng hoặc làm tải tệ hơn?
12. Nếu `netstats` có nhiều stream mà p99 không đổi, bạn cần thêm số liệu gì trước khi tăng cap?
13. Lập kế hoạch thử nghiệm ba mức streaming throttle, nêu các metrics và điều kiện dừng bắt buộc.
14. Sau rebuild dc2, `netstats` trống và tất cả node `UN`. Còn cần kiểm tra gì trước khi cho client đọc ở dc2?
15. Giải thích tại sao p99 không thể lấy bằng trung bình p99 của mọi node.
16. Thiết kế runbook khi repair bị chậm do validation I/O nhưng thời gian còn lại trước grace rất ngắn.

## 23. Sơ đồ quyết định tóm tắt

```text
                  STREAMING / REPAIR ĐANG CHẠY
                              |
               +--------------+---------------+
               |                              |
       Repair progress có đạt?          API SLO có đạt?
               |                              |
        +------+-----+                 +------+------+
        |            |                 |             |
       Có          Không              Có          Không
        |            |                 |             |
  Tiếp tục đo   Xác định bottleneck     |        Định vị CPU,
  và xác nhận   (validation? stream?    |        disk, mạng, GC,
  coverage      CPU/disk/network?)      |        replica overlap
        |            |                 |             |
        +------------+-----------------+-------------+
                              |
             Điều chỉnh throttle / concurrency / lịch
             dựa trên metric, không đổi nhiều núm cùng lúc
                              |
                Kiểm chứng p99 + timeout + coverage
                              |
                Đảm bảo deadline trước gc_grace
```

**Ghi nhớ:** **Streaming throughput** mô tả tốc độ chuyển dữ liệu, còn **repair throughput hữu dụng** phải tính cả validation, streaming, anti-compaction và tỷ lệ token ranges hoàn tất thành công. Throttle băng thông chỉ kiểm soát một phần chi phí nền; **CPU, I/O, network, concurrency và vị trí replica** quyết định ảnh hưởng lên truy vấn Cassandra. Tuning tốt là giữ **p95/p99 và timeout của ứng dụng trong SLO**, đồng thời bảo đảm **repair hoàn thành với khoảng dự phòng an toàn trước `gc_grace_seconds`**.

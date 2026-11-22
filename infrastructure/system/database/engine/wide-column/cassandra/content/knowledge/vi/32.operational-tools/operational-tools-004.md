# nodetool tpstats/compactionstats/netstats và hoạt động nền trong Apache Cassandra

## 1. Vì sao phải nhìn hoạt động nền khi Cassandra chậm?

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**, chia partition theo **partition key** và lưu nhiều bản sao theo replication strategy. Khi ứng dụng Java chạy `SELECT` hoặc `INSERT` ở một consistency level nhất định, coordinator cần tương tác với các replica. Đồng thời, Cassandra phải duy trì nhiều tác vụ nền: **memtable flush, SSTable compaction, hinted handoff, repair, streaming khi bootstrap/rebuild và xử lý message nội bộ**.

Các tác vụ nền cần thiết để cluster hoạt động bền vững nhưng có thể tranh chấp **CPU, bộ nhớ, disk I/O, network và thread pools** với read/write của người dùng. Vì vậy, một nút báo trạng thái `UN` trong `nodetool status` vẫn có thể gặp read/write timeout nếu hàng đợi kéo dài hoặc disk bị bão hòa.

Trong chương **Công cụ vận hành** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, ba lệnh đặc biệt hữu ích là:

- **`nodetool tpstats`**: quan sát executor/thread pool nội bộ, hàng đợi và một số chỉ số dropped messages.
- **`nodetool compactionstats`**: quan sát các tác vụ compaction đang chạy và lượng công việc đang chờ.
- **`nodetool netstats`**: quan sát trạng thái chuyển dữ liệu qua **streaming** và một số thông tin liên quan tùy phiên bản.

Không lệnh nào tự đưa ra kết luận “cluster khỏe” hay “bảng này hỏng”. Bài học hướng dẫn cách **ghép ba góc nhìn** với latency, storage, replication và log để chẩn đoán đúng nguyên nhân.

### Kết quả mong đợi

Sau bài này, bạn có thể:

1. Phân biệt các số đo **Active, Pending, Completed, Blocked và Dropped** trong `tpstats`.
2. Hiểu vì sao **pending compactions** tăng, và cách đọc tiến độ/khối lượng của `compactionstats`.
3. Phân biệt **SSTable streaming** trong `netstats` với request CQL thông thường.
4. Dựng timeline điều tra p99, timeout và nghẽn disk/network mà không sửa cấu hình thiếu căn cứ.
5. Dùng CQL và Java Driver để liên hệ query shape, consistency level với các công cụ vận hành.
6. Biết giới hạn dữ liệu theo **phiên bản Cassandra** và tránh những thao tác can thiệp nguy hiểm.

## 2. Ba lệnh, ba câu hỏi khác nhau

| Lệnh | Câu hỏi chính | Chỉ số đầu ra thường gặp | Điều lệnh không chứng minh |
|---|---|---|---|
| `nodetool tpstats` | Executor nào đang bận, có hàng đợi hay message bị drop không? | Active, Pending, Completed, Blocked, All time blocked; dropped message counts | Không cho biết trực tiếp disk IOPS, latency của từng query hoặc nguồn gốc mọi lỗi |
| `nodetool compactionstats` | Có compaction nào đang chạy, tiến độ ra sao và còn bao nhiêu tác vụ đợi? | Pending tasks, loại/nguồn công việc, tổng/đã xử lý dữ liệu, progress tùy phiên bản | Không đo toàn bộ sức khỏe disk hoặc bảo đảm bao giờ backlog hết |
| `nodetool netstats` | Node có đang gửi/nhận luồng **streaming** dữ liệu không? | Mode, send/receive streaming sessions, files/bytes, progress; thống kê bổ sung tùy phiên bản | Không đo toàn bộ network CQL, gossip hoặc replica messaging |

Các lệnh chạy từ **node đang được kiểm tra** và thường lấy thông tin qua JMX hoặc cơ chế quản trị tương ứng. Một lần chụp trên node A **không thay thế** quan sát trên node B/C; đặc biệt khi một replica là nút nghẽn.

### Sơ đồ liên hệ

~~~mermaid
flowchart TD
    A["API Java: read/write p99 tăng"] --> B["Đo theo query, CL, DC và thời gian"]
    B --> C["nodetool tpstats: pool/queue/dropped"]
    B --> D["nodetool compactionstats: compaction backlog"]
    B --> E["nodetool netstats: active streaming"]
    C --> F["Đối chiếu disk, CPU, GC và network"]
    D --> F
    E --> F
    F --> G{"Nghẽn nào được số liệu xác nhận?"}
    G --> H["Giảm áp lực có kiểm soát hoặc xử lý root cause"]
    H --> I["Đo lại p95/p99, throughput và error rate"]
~~~

**Không suy luận nhân quả chỉ từ việc hai đồ thị cùng tăng.** Ví dụ `Pending` tăng đúng lúc streaming chạy chưa chứng minh streaming là nguyên nhân duy nhất. Phải kiểm tra disk throughput/latency, CPU và lượng request đang đến.

## 3. Preflight cho công cụ vận hành

Trước khi chạy chẩn đoán trên production:

- Xác nhận **phiên bản Apache Cassandra, cách đóng gói và phiên bản `nodetool`**; tên field, định dạng output và tham số có thể thay đổi.
- Xác định node nào đang gặp vấn đề, **datacenter/rack**, keyspace/table, replication factor (RF), consistency level (CL) của request.
- Xác định nguồn số đo: **local node**, coordinator, một replica, hay dashboard đã tổng hợp toàn cluster.
- Ưu tiên các lệnh **đọc trạng thái** và thực hiện vài lần ở những mốc đo rõ ràng.
- Đảm bảo operator có quyền kết nối JMX và môi trường không bị cấu hình firewall/auth sai; lỗi kết nối `nodetool` không tự có nghĩa Cassandra down.
- Ghi lại thời gian UTC, hostname, JVM uptime/restart gần nhất, traffic rate, error rate và p95/p99.

Ví dụ nhóm lệnh đầu tiên:

~~~bash
# Xem phiên bản, trạng thái node và khả năng của nodetool.
nodetool version
nodetool status
nodetool help

# Ba góc nhìn chính của bài.
nodetool tpstats
nodetool compactionstats
nodetool netstats
~~~

Nếu cú pháp không được nhận, chạy `nodetool help <command>` trên đúng node. **Không sao chép option của một phiên bản khác mà không kiểm tra**.

## 4. `nodetool tpstats`: thread pools, hàng đợi và dropped messages

### 4.1. Vì sao Cassandra có nhiều stage?

Cassandra xử lý request thông qua nhiều nhóm executor hoặc **stage**, chẳng hạn các nhóm liên quan đọc, mutation, flush, compaction và xử lý tác vụ nội bộ. Một stage có các worker thực hiện việc đã được lên lịch và có thể có queue để giữ việc chưa được thực thi.

Ví dụ logic:

~~~text
Request / message đến
       |
       v
  Executor queue   <-- Pending
       |
       v
  Worker threads   <-- Active
       |
       v
  Hoàn thành việc  <-- Completed tăng
~~~

Nếu lượng việc đến cao hơn năng lực xử lý trong một thời gian đủ dài, **Pending** có thể tăng. Nhưng queue tăng không nói rõ nguyên nhân; worker có thể đang chờ disk, CPU, lock hoặc network, hoặc đơn giản traffic đột biến.

### 4.2. Cách đọc từng cột

| Trường thường thấy | Diễn giải | Lưu ý khi điều tra |
|---|---|---|
| **Pool Name** | Tên stage/executor được báo cáo | Danh sách pool và tên cụ thể khác nhau theo release |
| **Active** | Số tác vụ đang được xử lý tại thời điểm đo | Active cao chưa chắc xấu nếu throughput tương ứng cao |
| **Pending** | Việc đã xếp hàng nhưng chưa được worker xử lý | Quan trọng là **xu hướng** và thời gian queue duy trì |
| **Completed** | Tổng lượng tác vụ đã hoàn thành trong phạm vi đo/counter | Thường là counter tích lũy; tính delta theo thời gian, không coi là tốc độ tức thời |
| **Blocked** | Các tác vụ/việc bị chặn do khả năng tiếp nhận hàng đợi hoặc giới hạn executor theo semantics của bản dùng | Không đồng nghĩa “bao nhiêu TCP connection đang chờ mạng” |
| **All time blocked** | Counter tích lũy của trường blocked | Phải xét reset/restart và mức tăng, không chỉ nhìn trị tuyệt đối |

Đối với phần **Dropped Messages**, output có thể hiển thị số message bị drop theo loại như message liên quan read, mutation hay các luồng xử lý khác. Tên và cách thống kê phụ thuộc phiên bản. **Dropped** khác **Pending**: message có thể đã không được xử lý theo yêu cầu thời hạn/đường xử lý trong khi Pending là việc vẫn xếp trong queue.

### 4.3. Ví dụ đầu ra mang tính minh họa

~~~text
Pool Name                Active  Pending   Completed  Blocked  All time blocked
ReadStage                    8      350     9800000        0                 0
MutationStage                4       12    12100000        0                 0
MemtableFlushWriter          2      120      180000        0                 0

Message type                                    Dropped
READ                                               75
MUTATION                                            3
~~~

Đây là **số liệu giả định**, không phải output chính xác ở tất cả phiên bản Cassandra. Không dựa vào tên stage hoặc tên loại message trong ví dụ để viết parser cố định.

Cách đặt giả thuyết:

- `ReadStage Pending=350`: có backlog xử lý read; cần biết mức tăng giảm trong những phút tiếp theo và p99 đọc.
- `MutationStage Pending=12`: có queue ghi nhưng chưa thể kết luận nó gây timeout.
- `MemtableFlushWriter Pending=120`: có thể có backlog flush; cần đối chiếu với `compactionstats`, commitlog usage và disk latency.
- `READ Dropped=75`: cần xem counter có **đang tăng** khi read timeout tăng không; 75 có thể là di tích trước đó kể từ khi node khởi động.

### 4.4. Đọc hai ảnh chụp để tính delta

Giả sử cùng một node, cách nhau 60 giây:

| Chỉ số ReadStage | 10:00 | 10:01 | Diễn giải |
|---|---:|---:|---|
| Active | 6 | 8 | Worker bận hơn |
| Pending | 100 | 1.300 | Backlog tăng 1.200 |
| Completed | 1.000.000 | 1.012.000 | Hoàn tất thêm 12.000 việc trong 60 giây |
| READ dropped | 10 | 130 | Tăng thêm 120 message bị drop |

Tốc độ hoàn thành quan sát được:

~~~text
(1.012.000 - 1.000.000) / 60 s
= 200 tác vụ hoàn thành / giây
~~~

Counter `Completed` theo stage **không nhất thiết tương đương số CQL request**; một request có thể tạo nhiều việc nội bộ. Không dùng nó làm thước đo QPS tuyệt đối của API.

Từ số liệu trên có thể kết luận **queue đang tăng, dropped messages cũng tăng**, nhưng muốn xác định vì sao, cần đo CPU/GC, disk latency, query shape, replica timeout và tác vụ nền. Không suy ra trực tiếp rằng thiếu đúng `1.200 / 60 = 20` thread/giây hoặc phải tăng số worker theo tỷ lệ ấy.

### 4.5. Những bẫy khi đọc tpstats

1. **Cộng Pending của các pool khác nhau** có thể không có ý nghĩa vì một request có thể tạo nhiều việc ở nhiều stage.
2. **Completed là tổng tích lũy**, không phải QPS; phải lấy delta và kiểm tra counter có reset do restart không.
3. **Blocked cao** không nhất thiết có nghĩa tài nguyên CPU bị khóa; cần hiểu semantics của executor.
4. **Dropped messages không bằng trực tiếp số request thất bại**. Một request có thể có retry, nhiều replica và timeout.
5. **Pending=0 tại một thời điểm** không loại trừ tail latency cao do một replica chậm, network hay I/O.
6. **Active luôn cao** có thể là trạng thái bình thường của một stage bận nếu queue và p99 vẫn ổn định.

### 4.6. Khi nào cần điều tra ReadStage hoặc MutationStage?

| Dấu hiệu | Giả thuyết | Kiểm tra tiếp |
|---|---|---|
| ReadStage Pending tăng cùng read p99 | Quá tải read, partition rộng/hot, disk chậm | Query shape, `tablehistograms`, SSTables per read, disk I/O |
| MutationStage Pending tăng cùng write timeout | Replica xử lý mutation chậm hoặc overload | Commitlog sync, disk, network, write CL, CPU/GC |
| Flush stage Pending tăng lâu | Flush không theo kịp ghi, disk data chậm | Commitlog disk usage, SSTable write, compaction |
| Dropped messages tăng khi node còn `UN` | Queue/latency hoặc xử lý message quá tải | Logs, timeout, dropped by type, resource saturation |
| Chỉ một node Pending cao | Hotspot hoặc lỗi cục bộ | Partition distribution, node CPU/disk, DC/rack |
| Mọi node Pending tăng | Tăng tải diện rộng, deploy mới hoặc phụ thuộc chung | QPS, concurrency, client retries, background tasks |

## 5. `nodetool compactionstats`: backlog và công việc đang chạy

### 5.1. Compaction giải quyết việc gì?

Cassandra ghi dữ liệu vào memtable rồi flush thành **SSTable bất biến**. Theo thời gian, nhiều SSTable chồng lấn tạo read amplification; tombstone và bản cập nhật cũ cần được xử lý theo chính sách an toàn. **Compaction** đọc các SSTable nguồn, merge dữ liệu và ghi ra SSTable mới.

Compaction là công việc nền **tiêu thụ disk read, disk write, CPU và dung lượng tạm**. Nếu workload ghi tạo SSTable nhanh hơn khả năng compaction, số SSTable có thể tăng, khiến read latency và disk usage xấu đi.

~~~mermaid
flowchart LR
    A["Memtable flush"] --> B["Nhiều SSTable bất biến"]
    B --> C["Pending compaction tasks"]
    C --> D["Đọc SSTable nguồn"]
    D --> E["Merge / reconcile"]
    E --> F["Ghi SSTable mới"]
    F --> G["Giải phóng SSTable cũ khi đủ điều kiện"]
    H["Repair / streaming / client I/O"] -. tranh tài nguyên .-> D
    H -. tranh tài nguyên .-> F
~~~

### 5.2. Đầu ra của compactionstats

~~~bash
nodetool compactionstats
~~~

Tùy phiên bản, output có thể chứa:

- **Pending tasks**: lượng công việc đang đợi trong các cấu trúc liên quan.
- Những tác vụ đang chạy: loại công việc, keyspace/table, task ID, bytes đã hoàn thành và tổng bytes dự kiến.
- Progress/throughput/ước lượng thời gian còn lại nếu phiên bản/tool có cung cấp.

**Pending tasks không phải số SSTable**. Một task có thể xử lý nhiều SSTable và các loại việc nội bộ có chi phí khác nhau; không nhân pending count với một kích thước cố định để suy ra số byte hoặc phút còn lại.

Ví dụ **minh họa**:

~~~text
pending tasks: 22
id       compaction type    keyspace  table                   completed   total
task-01  COMPACTION         telemetry events_by_device_day   24 GiB      80 GiB
task-02  COMPACTION         telemetry readings_by_device    12 GiB      15 GiB
~~~

Không dùng ví dụ làm template parse vì output thực tế thay đổi theo version.

### 5.3. Vì sao backlog compaction tăng?

Những nguyên nhân thường gặp:

- **Write/flush rate cao**: SSTable mới được tạo nhanh hơn tốc độ merge.
- **Nhiều update và delete**: dữ liệu lịch sử/tombstone làm tăng khối lượng xử lý.
- **Compaction strategy** không phù hợp với workload, ví dụ nhầm STCS/LCS/TWCS.
- **I/O bị chia sẻ** với streaming, repair, flush và read/write của ứng dụng.
- **Disk đã gần đầy**, thiếu headroom để viết SSTable đầu ra trước khi giải phóng SSTable cũ.
- **CPU/nén** làm tác vụ chậm hoặc có lỗi I/O.
- Một số **partition quá lớn** hoặc số SSTable lớn gây quá tải không đều.

Không được nhìn `pending tasks=100` rồi kết luận “phải tăng `concurrent_compactors` lên gấp đôi”. Nếu disk đã bão hòa, tăng concurrency có thể khiến các tác vụ càng chậm hoặc làm client p99 xấu hơn.

### 5.4. Kiểm tra bằng chứng trước khi tuning

Một chuỗi điều tra tốt:

1. `compactionstats`: backlog có tăng qua nhiều thời điểm không? Active tasks có tiến triển không?
2. `tpstats`: queue của executor liên quan có tăng không? Read/Mutation stage có bị ảnh hưởng không?
3. `tablestats` hoặc `tablehistograms`: số SSTable, read latency và SSTables per read của bảng bị ảnh hưởng thế nào?
4. Disk telemetry: read/write throughput, await/p99 disk latency, free bytes, IOPS và controller throttling.
5. Logs: exception I/O, error compaction, pause hoặc shutdown.
6. Background activities: repair/streaming đang chạy trên cùng storage hay không?

Nếu pending cao nhưng **giảm đều**, disk/CPU và client SLO vẫn khỏe, đây có thể là giai đoạn bình thường sau burst load. Nếu pending tăng liên tục, thời gian xử lý không tiến và disk free giảm, nguy cơ cao hơn.

### 5.5. Dung lượng tạm khi compaction

Trong compaction, Cassandra thường phải giữ **SSTable cũ** đồng thời ghi **SSTable mới** trước khi giải phóng dữ liệu cũ an toàn. Vì vậy:

~~~text
Disk headroom cần thiết
≈ dung lượng SSTable đầu ra tạm thời
  + flush/streaming/repair đang xảy ra
  + dữ liệu tăng trưởng bình thường
  + biên an toàn của cluster
~~~

Không dùng công thức này như một cam kết kích thước chính xác: các chiến lược compaction khác nhau (STCS/LCS/TWCS), tombstone, compression và snapshot có ảnh hưởng riêng. Cần đo dung lượng thật và lịch tác vụ.

### 5.6. Compaction có thể bị giới hạn tốc độ

Một số phiên bản có cơ chế xem/điều chỉnh throughput hoặc concurrency của compaction (ví dụ các lệnh `nodetool` liên quan `getcompactionthroughput`/`setcompactionthroughput` nếu được hỗ trợ).

**Không nên tăng/giảm bừa**. Giảm throttle có thể giải phóng I/O cho query trong ngắn hạn nhưng khiến backlog và SSTable count tích lũy. Tăng throughput có thể giải phóng backlog nhanh nhưng gây p99 xấu hoặc thiếu dung lượng. Mọi thay đổi cần phê duyệt, baseline và rollback; trong bài chỉ sử dụng các lệnh đọc trạng thái.

## 6. `nodetool netstats`: streaming, không phải mọi gói tin TCP

### 6.1. Streaming là hoạt động gì?

**Streaming** là cơ chế chuyển dữ liệu giữa các node, thường dùng trong:

- **Bootstrap/add node**: node mới nhận token range và dữ liệu ban đầu.
- **Rebuild/replace/decommission/topology change**: chuyển giao trách nhiệm dữ liệu.
- **Repair**: trong một số giai đoạn cần đồng bộ sai lệch qua streaming.
- Một số quy trình khôi phục hoặc di chuyển dữ liệu khác tùy phiên bản.

Streaming thường truyền dữ liệu ở mức **SSTable hoặc đơn vị dữ liệu lưu trữ**, khác với request CQL đọc/ghi thông thường. Nó có thể gây **network throughput cao và disk I/O cao** mà số request client không tăng.

### 6.2. Đọc netstats

~~~bash
nodetool netstats
~~~

Bạn có thể gặp:

- **Mode** như NORMAL hoặc trạng thái node liên quan vận hành.
- Thông tin đang **sending** hoặc **receiving streams**.
- Session/peer, file hoặc bytes đã chuyển/tổng dự kiến, progress tùy phiên bản.
- Một số thống kê bổ sung như read repair/network/message pool tùy release.

Ví dụ **mang tính minh họa**:

~~~text
Mode: NORMAL
Receiving streams from node-X:
  transferred: 80 GiB / 200 GiB
Sending streams to node-Y:
  transferred: 12 GiB / 50 GiB
~~~

Các tên trường, cách nhóm và đơn vị thực tế phụ thuộc Cassandra version. **Không kết luận mọi kết nối CQL hoặc gossip đều có trong `netstats`.**

### 6.3. Những ngộ nhận về netstats

| Nhận định | Vì sao không đúng? |
|---|---|
| “`netstats` không thấy stream → cluster không có network traffic.” | CQL, gossip, replica messaging, heartbeat vẫn có traffic riêng |
| “Không có stream → repair đã xong.” | Repair còn bước chuẩn bị/validation; có thể không phải lúc nào cũng có phiên stream |
| “Stream progress 90% → chắc chắn còn 10% thời gian.” | File size, session, rate, finalization, retry và disk latency có thể thay đổi |
| “Node `UN` → streaming chắc chắn đã kết thúc toàn cluster.” | Cần kiểm tra task/status và các node liên quan; cùng lúc có stream từ công việc khác |
| “Có streaming nghĩa là cluster đang bootstrap.” | Repair, replace, rebuild và decommission cũng có thể tạo streaming |
| “`netstats` cho biết dữ liệu replica đã đúng toàn bộ.” | Streaming session không phải kiểm chứng anti-entropy toàn keyspace |

### 6.4. Tính tốc độ gần đúng

Giả sử cùng một receiving session, đo:

~~~text
10:00:00  transferred = 80 GiB
10:02:00  transferred = 86 GiB
Delta     = 6 GiB / 120 giây
          = 6 × 1024 MiB / 120
          ≈ 51,2 MiB/s
~~~

Đây là tốc độ trung bình của **khoảng đang đo**, không phải băng thông mạng tối đa hay dự báo chính xác thời gian còn lại. Stream có thể thay đổi file/source, bị throttle, chuyển sang phase mới hoặc gặp retry.

Nếu hai ảnh chụp thuộc **hai session khác nhau**, việc trừ counters trực tiếp là vô nghĩa; cần bảo đảm đồng nhất session/peer và đơn vị.

### 6.5. Streaming tác động read/write thế nào?

Khi node N1 gửi nhiều SSTable tới node mới N4:

1. N1 đọc lượng lớn dữ liệu từ disk, cạnh tranh với `SELECT`.
2. Network N1/N4 có thêm lưu lượng streaming, có thể cùng tuyến với replica traffic.
3. N4 ghi dữ liệu nhận vào disk, tạo áp lực write I/O và các công việc hậu streaming.
4. Compaction/flush/repair vẫn có thể tiếp tục, dẫn tới tranh tài nguyên nhiều chiều.
5. Ứng dụng Java có thể thấy p99 tăng ngay cả khi query shape và CL không đổi.

**Không mặc định tắt streaming là giải pháp an toàn.** Bootstrap/repair/replace đang thực hiện nhiệm vụ duy trì replication và availability. Cần xác định quy trình đang chạy và xem có thể điều tiết hoặc lên lịch lại theo runbook.

## 7. Liên kết ba lệnh với hoạt động nền cụ thể

| Hoạt động | Trong `tpstats` có thể thấy | Trong `compactionstats` có thể thấy | Trong `netstats` có thể thấy |
|---|---|---|---|
| **Read traffic cao** | Stage liên quan read Pending/Active tăng | Có thể backlog tăng gián tiếp do I/O tranh chấp | Thường không hiện read CQL thành stream |
| **Write traffic cao / flush** | Mutation/flush stage bận, pending tăng | SSTable mới làm tăng nhu cầu compaction | Thường không hiện write CQL thành stream |
| **Compaction nặng** | Executor liên quan bận tùy version | Active tasks, bytes processed, pending tasks | Thường không báo compaction cục bộ như stream |
| **Repair** | Stage/queue liên quan có thể tăng | Các hoạt động liên quan compaction/validation tùy version | Stream dữ liệu sai lệch nếu repair cần truyền |
| **Bootstrap/replace/rebuild** | Một số stage I/O và message tăng | Có thể thấy tác vụ nền phụ trợ | Send/receive stream rõ nhất |
| **Hinted handoff** | Messaging/queue và load trên node giữ hint | Không phải compaction trực tiếp | Không mặc định được xem như SSTable streaming |
| **Disk full / I/O stall** | Pending tăng ở nhiều stage | Active progress chậm, pending có thể tăng | Session có thể chậm hoặc retry |

Bảng cố tình dùng từ **có thể**. Các stage cụ thể, bộ đo và cơ chế tích hợp khác nhau theo Cassandra version. Việc một hàng “trống” không chứng minh tác vụ tương ứng không diễn ra.

### Vòng phản hồi gây quá tải

~~~mermaid
flowchart TD
    A["Traffic ghi tăng"] --> B["Flush sinh SSTable nhanh"]
    B --> C["Compaction backlog tăng"]
    C --> D["Read amplification và disk contention"]
    D --> E["Read p99 / timeout tăng"]
    E --> F["Client retry mạnh hơn"]
    F --> G["Tải mới tăng trên coordinator / replica"]
    G --> H["tpstats Pending và dropped messages tăng"]
    H --> D
    I["Repair hoặc streaming đồng thời"] --> D
~~~

Đây là **một kịch bản có thể xảy ra**, không phải định luật mọi incident. Điểm can thiệp đôi khi nằm ở client backpressure/retry và điều tiết công việc nền, thay vì tăng kích thước thread pool.

## 8. Các lệnh bổ trợ để kiểm chứng giả thuyết

Ba lệnh chính thường không đủ. Có thể kết hợp các lệnh đọc trạng thái:

~~~bash
# Trạng thái topology / replica theo DC, rack.
nodetool status

# Thông tin node, tải tổng quan.
nodetool info

# Thống kê read/write và SSTable theo bảng.
nodetool tablestats telemetry.measurements_by_device_day

# Phân bố latency, SSTables per read ở bản hỗ trợ.
nodetool tablehistograms telemetry measurements_by_device_day

# Histogram gần coordinator, tùy bản.
nodetool proxyhistograms

# Xem commit log / compaction / stream qua metrics và logs,
# không chỉ dựa vào một output nodetool.
~~~

Ngoài `nodetool`, hãy kiểm tra:

- **CPU và GC**: pause, CPU throttling, heap/off-heap.
- **Disk**: free bytes, disk await/latency, IOPS, bandwidth, SMART/cloud volume throttling.
- **Network**: RTT, retransmissions, packet loss, throughput giữa node/DC.
- **Driver**: request p95/p99, in-flight, retry/speculative executions, timeout/unavailable.
- **Cassandra logs**: stack trace lỗi compaction, disk read/write, dropped messages, bootstrap/repair timeline.
- **JMX/Prometheus**: counters/rates liên quan stage, compaction pending, streaming và latency theo node.

Hãy **ghi đơn vị** (ms/µs/s, MiB/GiB, bytes, counts), khoảng đo và phiên bản exporter. Một số counters reset khi node restart, làm phép trừ delta xuất hiện số âm; đó là cảnh báo về dữ liệu đo chứ không phải “server xử lý âm số message”.

## 9. Ví dụ CQL: query shape có thể tạo áp lực gì cho stage?

### 9.1. Schema theo truy vấn

Giả sử keyspace và bảng:

~~~cql
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE telemetry.measurements_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Partition key là **`(device_id, event_day)`**, giúp truy vấn đọc một thiết bị trong một ngày có phạm vi rõ:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, metric_value
FROM telemetry.measurements_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Với partition có kích thước hợp lý, query trên thường rẻ hơn một full scan. Tuy nhiên ngay cả `LIMIT 50` vẫn có thể gây đọc nhiều SSTable/tombstone trước khi tìm đủ 50 row sống. `tpstats` cho thấy read stage đang quá tải nhưng **không thay việc kiểm tra query shape**.

### 9.2. Truy vấn dễ gây tải ngoài ý muốn

~~~cql
-- Minh họa anti-pattern: không khuyến nghị làm API production.
SELECT device_id, event_day, event_time, metric_value
FROM telemetry.measurements_by_device_day
WHERE metric_value > 80
LIMIT 50
ALLOW FILTERING;
~~~

`ALLOW FILTERING` và thiếu partition key có thể khiến Cassandra quét phạm vi rộng. `LIMIT 50` giới hạn row trả về, không bảo đảm chỉ 50 entry được đọc. Khi nhiều API gọi query kiểu này, `ReadStage Pending` hoặc disk I/O có thể tăng; nếu compaction cũng backlog, tail latency còn xấu hơn.

Phương án bền vững thường là **thiết kế bảng theo truy vấn** hoặc cơ chế index/search phù hợp với phiên bản và workload. Không mặc định chữa bằng tăng worker thread.

### 9.3. CL và khả năng chờ replica

Với RF=3 một DC:

- `ONE` cần phản hồi từ một replica theo semantics thao tác.
- `LOCAL_QUORUM` cần quorum cục bộ, tức hai replica trong DC.
- `ALL` yêu cầu mọi replica được chỉ định.

Nếu một replica chậm do streaming, request `LOCAL_QUORUM` có thể bị ảnh hưởng khi số replica khỏe đủ nhanh không đạt quorum. Nhưng không được kết luận **“LOCAL_QUORUM luôn chậm hơn ONE đúng một RTT”**: replica requests diễn ra song song và latency phụ thuộc đường thực thi.

Chỉnh CL là quyết định về **tính nhất quán/availability**, không chỉ tuning latency. `tpstats`, `netstats` và `compactionstats` giúp phát hiện tải, **không thay thế thiết kế correctness của ứng dụng**.

## 10. Java Driver 4.x: liên hệ client latency với hoạt động nền

Ứng dụng Java nên phát ra metric theo **query ID ổn định**, consistency level, DC và outcome. Không gắn giá trị partition key làm metric label vì cardinality lớn và có thể lộ thông tin nhạy cảm.

Ví dụ đọc một partition với prepared statement:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

// session được tạo và quản lý ở vòng đời ứng dụng.
PreparedStatement query = session.prepare(
    "SELECT event_time, metric_value " +
    "FROM telemetry.measurements_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 50"
);

BoundStatement statement = query.bind(
        UUID.fromString("11111111-1111-1111-1111-111111111111"),
        LocalDate.of(2026, 11, 21))
    .setPageSize(50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

long startNs = System.nanoTime();
String outcome = "success";

try {
    ResultSet rs = session.execute(statement);
    for (Row row : rs) {
        processMetric(row.getInstant("event_time"),
                      row.getDouble("metric_value"));
    }
} catch (RuntimeException ex) {
    outcome = "error";
    throw ex;
} finally {
    long latencyMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - startNs);

    // Demo: thay bằng histogram/log có giới hạn cardinality.
    recordRequest("read_measurements_by_day",
                  "LOCAL_QUORUM", outcome, latencyMs);
}
~~~

Hai hàm `processMetric` và `recordRequest` là **hook giả định**; hãy hiện thực với bộ ghi metrics/logging của ứng dụng. Cần tránh chặn callback hoặc giữ quá nhiều kết quả trong bộ nhớ.

Mốc đo trên bao trùm vòng lặp tiêu thụ tối đa 50 row; nếu code dùng paging không giới hạn, phải phân biệt **time to first page** với **time to consume all pages**. Driver cũng có metrics riêng về request latency, retries và connection pools tùy cấu hình.

Khi p99 Java tăng:

1. Đối chiếu timestamp và operation ID với `tpstats` tại các coordinator/replica liên quan.
2. Kiểm tra `compactionstats` xem backlog/active compaction có trùng thời điểm không.
3. Xem `netstats` có streaming tới/đi từ các node ấy không.
4. Kiểm tra disk/GC/network và error rate để xác nhận nguyên nhân.
5. So số lần retry và timeout để tránh tình huống client retry khiến tải tự tăng.

`execute` thành công không chứng minh mọi replica đã đồng bộ hoặc các tác vụ nền đã kết thúc; nó phản ánh kết quả của request theo CL đã chọn.

## 11. Runbook A: read p99 cao, ReadStage Pending tăng

**Tình huống:** Một DC có ba replica cho keyspace RF=3. P99 của API `read_measurements_by_day` tăng từ 70 ms lên 900 ms, `ReadStage Pending` của node B tăng liên tục.

### Bước 1 — Xác định ảnh hưởng

Thu thập thời điểm bắt đầu, p50/p95/p99, QPS, timeout, CL, node, DC/rack. Xem có chỉ một API bị ảnh hưởng hay tất cả query.

### Bước 2 — Chụp nhiều mẫu tpstats

Lấy `tpstats` trên B và ít nhất một node khỏe để so sánh. Ghi `Active`, `Pending`, delta `Completed` và delta `Dropped` qua các mốc thời gian. Nếu B có queue tăng mà các node khác không, kiểm tra phân bố token/hot partition và tài nguyên riêng của B.

### Bước 3 — Đối chiếu compaction và streaming

Kiểm tra `compactionstats` và `netstats` trên B. Nếu compaction nhiều, streaming lớn, và disk I/O latency tăng, giả thuyết tài nguyên lưu trữ bị tranh chấp có cơ sở. Nếu không có streaming nhưng read queue tăng, tìm query scan/tombstone và CPU/GC.

### Bước 4 — Kiểm tra bảng và truy vấn

Xem `tablehistograms`, SSTables per read, tombstone warning, partition size và query có đủ partition key không. Không dùng `LIMIT` làm bằng chứng truy vấn đã rẻ.

### Bước 5 — Giảm áp lực an toàn

Tùy nguyên nhân, có thể hạn chế backfill, hạ concurrency của job không quan trọng, sửa query shape hoặc điều chỉnh lịch repair/streaming theo runbook. **Không tăng thread pool, tắt compaction hoặc hạ consistency level mù quáng.**

### Bước 6 — Xác minh phục hồi

Queue giảm về mức nền; dropped delta không tiếp tục tăng; p99 và timeout giảm; disk/CPU/GC ổn định. Theo dõi thêm sau khi tác vụ nền kết thúc để chắc chắn không còn backlog tích lũy.

## 12. Runbook B: compaction backlog dài và data disk gần đầy

**Tình huống:** `compactionstats` báo pending tasks tăng từ 15 lên 180 trong một giờ; data disk còn 12% free, nhiều update/TTL đang diễn ra.

1. **Xác nhận backlog thật:** chụp `compactionstats` theo thời gian, xem active tasks có tiến triển không; kiểm tra bảng nào đang góp nhiều việc.
2. **Phân tích flush và write load:** `tpstats` xem flush stages, mutation queue; đo số SSTable được tạo và commit-log/disk activity.
3. **Đo disk headroom thực tế:** old/new SSTables có thể tồn tại đồng thời trong compaction; tính cả snapshots, streaming và flush.
4. **Kiểm tra chiến lược compaction:** STCS/LCS/TWCS có đặc tính write/read/space amplification khác nhau; không đổi strategy ngay trong sự cố nếu chưa có kế hoạch.
5. **Giảm tải không thiết yếu:** điều tiết import/backfill hoặc thao tác nền được phép theo runbook; ưu tiên duy trì đường ghi/đọc còn an toàn.
6. **Không xóa SSTable bằng tay:** thao tác này có thể làm mất dữ liệu hoặc gây inconsistency nghiêm trọng.
7. **Xác minh:** pending giảm, active compaction có tiến triển, disk free không rơi xuống mức nguy hiểm, p99/timeout trở lại bình thường.

**Chú ý:** “đã dừng compaction” không đồng nghĩa có thể thu hồi ngay mọi dung lượng cũ. Việc dừng/thay đổi compaction cần hiểu trạng thái tệp, dữ liệu đã được tạo, snapshot và hành vi phiên bản.

## 13. Runbook C: streaming khi bootstrap làm tăng write timeout

**Tình huống:** Node N4 đang bootstrap, `netstats` tại N1/N4 có stream lớn. Cùng lúc `MutationStage Pending` và write p99 tăng trên một số node.

1. Xác định thao tác nào sinh stream: **bootstrap, repair, rebuild hay replace**, phạm vi token/keyspace và owner của change.
2. Đọc `nodetool status` để biết joining/normal và node down; **`UJ` chưa phải `UN`**.
3. Theo dõi `netstats` theo **session/peer**, bytes transferred và delta theo thời gian. Không lấy progress % của một session làm ETA toàn cluster.
4. Kiểm tra disk read latency trên nguồn, disk write trên đích, network throughput/packet loss và quota cloud volume.
5. Xem `tpstats` có pending/dropped ở mutation/read stages; xem `compactionstats` có thêm cạnh tranh I/O.
6. Nếu tài nguyên chạm giới hạn, trao đổi với owner change để **điều tiết stream hoặc workload không quan trọng theo runbook**; không ngắt hoặc xóa dữ liệu đang nhận một cách tùy tiện.
7. Khi N4 chuyển `UN`, vẫn cần xác minh stream hoàn tất, ứng dụng ổn định và kế hoạch cleanup/repair hậu topology change phù hợp.

Nếu request `LOCAL_QUORUM` chỉ cần hai ACK trong DC, sự có mặt của ba node không bảo đảm hai ACK luôn đến kịp khi streaming đang gây I/O stall; phải quan sát client timeout thực tế.

## 14. Alert và dashboard: đừng đặt ngưỡng chỉ trên một ảnh chụp

### 14.1. Nên cảnh báo theo tổ hợp tín hiệu

| Tình huống cảnh báo | Tín hiệu kết hợp | Vì sao tốt hơn một metric đơn |
|---|---|---|
| **Read overload** | ReadStage Pending tăng liên tục + read p99/timeout tăng | Phân biệt queue có ảnh hưởng người dùng với burst bình thường |
| **Write overload** | MutationStage/flush backlog tăng + write timeout + disk latency cao | Gợi ý đường ghi đang nghẽn |
| **Compaction không theo kịp** | Pending compactions tăng + SSTables per read cao + disk headroom giảm | Kết hợp backlog, tác động hiệu năng và rủi ro dung lượng |
| **Streaming kéo dài** | Bytes còn lại lớn / throughput thấp + node joining lâu + error/retry | Dễ phân biệt stream hợp lệ và stream không tiến |
| **Dropped message bất thường** | Delta dropped > baseline + timeout tăng | Counter tích lũy đơn lẻ có thể từ sự cố cũ |
| **Tác vụ nền tranh I/O** | Compaction/streaming active + disk await cao + p99 xấu | Chứng minh nguồn tài nguyên đang chịu áp lực |
| **Rủi ro khôi phục** | Node down kéo dài + repair/hints không theo kịp + capacity cảnh báo | Tránh xem node UP trở lại là đủ |

Các ngưỡng số cụ thể phải xuất phát từ **baseline, traffic, SLA/SLO, kích cỡ cluster và phiên bản**. Không có một mức `Pending > 100` luôn nguy hiểm cho mọi stage/node.

### 14.2. Những phép tổng hợp cần tránh

- **Không lấy trung bình p99 của từng node** để ra p99 cluster. Percentile cần histogram/phân bố có thể gộp đúng.
- **Không tổng hợp các queue khác loại** thành một con số “pending toàn cluster” rồi diễn giải như số request đang chờ.
- **Không lấy Completed counter tích lũy** làm throughput; tính delta/time và kiểm tra reset.
- **Không lấy netstats bytes transferred** từ hai stream khác session để tính tốc độ.
- **Không lấy total pending compactions** thay dung lượng disk còn cần; task size khác nhau.

### 14.3. Một dashboard tối thiểu

- Hàng đầu: API read/write QPS, p50/p95/p99, timeout/unavailable theo DC/CL.
- Hàng hai: `tpstats` Pending/Active/delta dropped theo node và stage quan trọng.
- Hàng ba: `compactionstats` active/pending, SSTables per read, data disk free/latency.
- Hàng bốn: `netstats` active streaming, bytes/s theo node/peer và bootstrap/repair events.
- Hàng cuối: CPU, heap, GC, network errors, commitlog/hints/flush, thay đổi cấu hình hoặc deploy.

Không nên gắn partition key hoặc user ID làm nhãn time-series để “debug chi tiết” vì cardinality và rủi ro thông tin nhạy cảm; dùng query ID ổn định và trace/log có kiểm soát.

## 15. An toàn vận hành: đọc trước, can thiệp sau

Ba lệnh chính của bài là **quan sát**, nhưng hoạt động nền mà chúng mô tả có thể rất nhạy với can thiệp.

| Việc định làm | Tại sao cần thận trọng? |
|---|---|
| Tăng concurrency/throughput compaction | Có thể gây disk contention và p99 xấu hơn hoặc thiếu disk headroom |
| Giảm throughput compaction quá thấp | Có thể làm backlog SSTable kéo dài, read amplification tăng |
| Dừng một stream giữa bootstrap/repair | Có thể kéo dài trạng thái chưa hoàn tất, để lại công việc dở dang cần recovery |
| Tăng số worker thread khi Pending cao | Nếu nguyên nhân là disk/network nghẽn, nhiều worker không sửa được bottleneck |
| Xóa SSTable, commit log hoặc hint để giải phóng disk | Có thể làm mất dữ liệu chưa an toàn hoặc làm hỏng cơ chế khôi phục |
| Chạy `nodetool compact`, `repair` hoặc `flush` chỉ để thử | Là thao tác tạo tải và có thể cần nhiều disk/network; không phù hợp làm lệnh đo mặc định |
| Hạ `LOCAL_QUORUM` xuống `ONE` để giảm timeout | Thay đổi consistency/correctness, không chỉ hiệu năng |

**Quy tắc khi xử lý production:** ghi baseline → xác minh phiên bản và nguyên nhân → đề xuất thay đổi nhỏ, có owner và rollback → quan sát p99/error/capacity → mới mở rộng áp dụng. Chỉ dùng lệnh can thiệp theo runbook đã được phê duyệt.

## 16. Bài tập tình huống

### Câu 1 — Queue có tăng hay không?

`ReadStage Pending` tăng từ 120 lên 1.020 trong 60 giây, `Completed` tăng từ 500.000 lên 518.000. Tốc độ hoàn thành quan sát được là bao nhiêu? Có thể kết luận cần thêm bao nhiêu thread không?

**Đáp án:** `(518.000 - 500.000)/60 = 300` tác vụ/giây. Queue tăng 900 đơn vị. Chưa thể kết luận số thread cần tăng; cần biết service time, workload, disk/CPU và semantics của stage.

### Câu 2 — Completed lớn nhưng không có lỗi

Một node có `Completed=100.000.000`, `Pending=0` và p99 ổn định. Completed cao có chứng minh node quá tải không?

**Đáp án:** Không. Đây thường là counter tích lũy của tác vụ đã xử lý. Cần xét delta, queue, dropped/error và latency.

### Câu 3 — Pending compactions lớn

`compactionstats` báo pending=70 nhưng tất cả compaction đang chạy vẫn tiến, read/write SLO tốt và disk đủ chỗ. Có bắt buộc chỉnh throughput ngay không?

**Đáp án:** Không. Cần theo dõi xu hướng backlog và resource; pending đơn lẻ không đủ kết luận. Thay concurrency/throttle có thể gây tranh I/O không cần thiết.

### Câu 4 — Không thấy stream

`nodetool netstats` không có phiên streaming, trong khi Java `SELECT` vẫn chậm và network traffic cao. Có mâu thuẫn không?

**Đáp án:** Không. `netstats` tập trung vào streaming ở mức dữ liệu lưu trữ; CQL và replica messaging vẫn có network traffic riêng.

### Câu 5 — Repair có thể vẫn hoạt động khi netstats trống?

Một operator khẳng định “netstats trống nghĩa là không còn repair nào”. Đúng hay sai?

**Đáp án:** Sai. Repair có thể ở pha không thực hiện SSTable streaming, và netstats không phải công cụ duy nhất xác nhận repair hoàn tất. Cần logs/metrics và trạng thái tác vụ repair.

### Câu 6 — Cùng lúc stream và compaction

Khi bootstrap, `netstats` báo gửi 150 GiB, `compactionstats` báo backlog tăng, disk await tăng và read p99 tăng. Hãy đưa ra chuỗi chẩn đoán hợp lý.

**Đáp án:** Kiểm tra source/destination stream, tốc độ bytes/s và disk utilization; đối chiếu backlog compaction, số SSTable và read stage queue; xem p99/timeout theo node; giảm tải hoặc điều tiết công việc nền theo runbook nếu thật sự nghẽn.

### Câu 7 — Dừng streaming

Node mới đang `UJ`, một operator muốn dừng stream và cho phép phục vụ toàn bộ traffic vì `nodetool status` báo UP. Nên làm gì?

**Đáp án:** Không coi `UJ` là `UN`. Node đang joining chưa hoàn tất bootstrap; cần xác minh transfer và trạng thái bình thường theo quy trình, không ép phục vụ hoặc xóa tệp đang nhận.

### Câu 8 — Dropped messages

Counter READ dropped từ 5 lên 305 sau một phút, trong khi read timeout cũng tăng. Có thể kết luận chính xác 300 request SELECT thất bại không?

**Đáp án:** Không. Counter phản ánh message theo loại, không ánh xạ 1:1 với request. Có thể nói dropped message delta tăng 300 và tương quan với timeout, cần điều tra stage/replica và logs.

### Câu 9 — Compaction cần chỗ trống

Một node gần đầy disk và compaction đang tạo SSTable đầu ra. Xóa thủ công vài SSTable nguồn để “có chỗ” là giải pháp đúng không?

**Đáp án:** Không. SSTable nguồn cần giữ cho đến khi quá trình chuyển đổi an toàn; xóa tay có nguy cơ làm mất dữ liệu. Phải xử lý capacity/backlog theo runbook.

### Câu 10 — Theo dõi cụm đa DC

Ứng dụng dùng `LOCAL_QUORUM` tại `dc1`. Một node `dc2` đang streaming rất lớn và có pending queue cao, nhưng API tại `dc1` vẫn khỏe. Có cần kết luận tất cả request sẽ chậm không?

**Đáp án:** Không. Độ phụ thuộc DC xa còn tùy CL, topology, kiểu thao tác và tài nguyên chia sẻ. Nên theo dõi từng DC/node và không suy diễn tình trạng một node thành toàn bộ cluster.

## 17. Tổng kết

`nodetool tpstats`, `nodetool compactionstats` và `nodetool netstats` tạo thành **ba góc nhìn bổ sung nhau** về hoạt động nền Cassandra:

1. **`tpstats`** cho biết executor đang xử lý bao nhiêu việc, backlog có tăng không và dropped messages có xuất hiện; phải xem **delta và xu hướng**.
2. **`compactionstats`** cho biết backlog cùng tiến độ tác vụ compaction; pending count **không phải số byte hay ETA cố định**.
3. **`netstats`** cho biết các **phiên streaming** đang gửi/nhận dữ liệu; nó **không đo toàn bộ CQL network traffic** và không chứng minh repair hoàn tất.
4. **Background work tranh CPU, disk, network và memory** với read/write; tìm nghẽn bằng cách ghép metrics tài nguyên, p99/error và hoạt động tác vụ.
5. **Node `UN` chưa chứng minh hiệu năng khỏe**, và `UJ` chưa phải bootstrap hoàn tất.
6. **Không sửa concurrency, throttle hoặc dừng nhiệm vụ chỉ từ một snapshot**; phải xác định phiên bản, ảnh hưởng correctness và phương án rollback.
7. **Java và CQL vẫn cần mô hình partition key, query shape và CL đúng**; không một công cụ vận hành nào có thể biến một full-scan tốn kém thành truy vấn tối ưu.

Khi Cassandra chậm, câu hỏi đúng không chỉ là “lệnh nào báo pending lớn?”, mà là **“công việc nào đang tạo backlog, tài nguyên nào đang bão hòa, replica nào bị ảnh hưởng và điều đó giải thích được bao nhiêu request chậm?”**. Chỉ khi liên kết được các bằng chứng này mới nên thay đổi cách vận hành cluster.

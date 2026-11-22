# Đo tải khi bootstrap, streaming, repair hoặc backup

> **Chương:** Đo tải và lỗi phân tán  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình wide-column. Hiểu partition key, bảng thiết kế theo truy vấn, replication, mức nhất quán đọc/ghi, CQL, compaction, repair và Java Driver là điều kiện để đo đúng ảnh hưởng của các thao tác vận hành.  
> **Trọng tâm:** Thiết kế và thực hiện phép đo tải **trước, trong, sau** node bootstrap, SSTable streaming, repair và backup mà không nhầm việc hoàn tất thao tác nền với chất lượng phục vụ người dùng.

## 1. Bài toán: cluster vẫn hoạt động nhưng API chậm gấp nhiều lần

Một cụm Cassandra đang phục vụ API ghi sự kiện và đọc lịch sử theo tenant. Bình thường, tỷ lệ request thành công cao và độ trễ p99 ổn định. Đội vận hành thêm node để tăng dung lượng; trong giai đoạn **bootstrap**, node mới cần nhận dữ liệu từ các replica hiện có. Cùng lúc, hệ thống có thể:

- Đọc SSTable và truyền dữ liệu qua network.
- Ghi dữ liệu streaming xuống ổ đĩa node nhận.
- Chạy compaction, flush, repair hay housekeeping.
- Xử lý các request CQL của ứng dụng Java qua coordinator/replica.
- Chịu sự thay đổi số replica/token ranges và cân bằng tải khi topology chuyển trạng thái.

Một bảng điều khiển chỉ báo **node UP** hoặc **bootstrap completed** không nói API còn đạt SLO. Một dashboard chỉ có CPU trung bình cũng có thể bỏ sót disk I/O bão hòa, pending tasks, GC pause, hot partition hoặc cross-DC network.

**Câu hỏi của bài học không phải chỉ là “thao tác có hoàn tất không?” mà là:**

1. Khi thao tác bắt đầu, **throughput thành công, p95/p99 và error rate** của workload sản xuất thay đổi thế nào?
2. Thành phần nào trở thành nút thắt: coordinator, replica, disk, network, JVM, compaction, thread pool hay ứng dụng Java?
3. **Tiêu tốn bao nhiêu headroom**, mất bao lâu để hoàn tất và cluster có trở về baseline sau khi kết thúc không?
4. Có thể tiếp tục thao tác, giảm tốc, tạm dừng theo runbook hay phải **STOP** vì nguy cơ ảnh hưởng dữ liệu/quorum?
5. Dữ liệu sau bootstrap/repair/backup có đúng, đầy đủ và **khôi phục được** theo hợp đồng RPO/RTO không?

Để trả lời đáng tin cậy, cần **một thí nghiệm đo tải có phương pháp**, không dựa vào vài ảnh chụp CPU hoặc cảm giác hệ thống “có vẻ ổn”.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả khác biệt giữa **bootstrap**, **streaming**, **repair**, **snapshot** và **sao chép backup ra ngoài cluster**.
- Lập kế hoạch đo **baseline → tác vụ nền → phục hồi**, với workload CQL và RF/CL đại diện.
- Chọn **metrics phía ứng dụng, Java Driver, Cassandra node, disk, network và tài nguyên nền**.
- Dùng **nodetool** ở chế độ quan sát; biết lệnh vận hành nào chỉ được chạy khi có quyền và runbook.
- Viết Java load probe bất đồng bộ có giới hạn số request đang bay.
- Xác định **success throughput, error budget, p99, pending tasks, streaming progress, disk headroom** và tiêu chí dừng.
- Phân biệt **backup đã tạo file** với **backup đã được sao chép/khôi phục/đối soát**.
- Đọc kết quả để ra quyết định về lịch bảo trì, topology và capacity planning.

> **Ranh giới an toàn:** Các bài thử bootstrap, decommission, rebuild, repair, fault injection và backup tải lớn chỉ thực hiện trên **cluster staging/lab được phê duyệt** hoặc qua change window/runbook riêng của production. Bài học **không yêu cầu** tắt replica, làm mất network, thay token/RF hay chạy sửa chữa trên cluster thật để học.

## 2. Cơ chế vận hành nào tạo tải gì?

### 2.1. Bootstrap: node mới tham gia và nhận token ranges

Khi một node tham gia cluster Cassandra ở chế độ bootstrap, cluster cần bố trí dữ liệu theo token ranges và cơ chế replication. Node mới thường nhận SSTable data qua **streaming** từ những node phù hợp. Trong thời gian này, trạng thái topology có thể thể hiện node đang **JOINING** trước khi ở trạng thái phục vụ bình thường; diễn giải cụ thể phụ thuộc phiên bản/topology.

Hệ quả cần đo:

- **Node gửi:** đọc đĩa, network outbound, CPU và metadata/streaming tasks.
- **Node nhận:** network inbound, ghi SSTable, disk I/O, disk free, CPU và công việc nền tiếp theo.
- **Cluster:** tác động lên coordinator, thay đổi ownership/token map, read/write p99, pending compactions, availability.
- **Client:** driver khám phá topology/load balancing, kết nối mới, node health và lỗi trong giai đoạn chuyển tiếp.

**Không kết luận** “thêm node là tải giảm ngay”. Trong bootstrap, các node cũ có thể bận hơn vì đang **vừa phục vụ CQL vừa gửi dữ liệu**. Headroom trước thao tác quan trọng hơn số node sau khi hoàn thành.

### 2.2. Streaming: chuyển SSTable giữa các node

**Streaming** là cơ chế chuyển dữ liệu giữa node, có thể xuất hiện trong bootstrap, rebuild, replacement/decommission, repair và một số thao tác tái cân bằng khác tùy phiên bản/cấu hình.

Dấu hiệu quan sát:

- Số **bytes/files/sessions** đang gửi/nhận và tốc độ thực.
- Disk read phía sender, disk write phía receiver.
- Network throughput và packet retransmission/error.
- CPU/GC/native memory và hàng đợi disk/network.
- Read/write latency của workload CQL trong lúc cạnh tranh tài nguyên.

**Không đồng nhất streaming với repair**: repair có bước so sánh và đồng bộ giữa replica; streaming có thể là một phần của quy trình repair, nhưng một session streaming không cho biết repair toàn cluster đã hoàn tất.

### 2.3. Repair: đối soát và đồng bộ replica

Cassandra dùng cơ chế **anti-entropy repair** để so sánh những replica chứa cùng token ranges và đồng bộ khác biệt. Tùy phiên bản/chiến lược, quy trình có thể có validation, Merkle-tree-related work, streaming sessions, pending compactions và bookkeeping.

Repair có thể sử dụng đồng thời:

- CPU và I/O để đọc/đối chiếu SSTables.
- Network giữa các replica.
- Ổ đĩa để nhận/chứa dữ liệu và compaction.
- Threads, queues và bộ nhớ cho các công việc repair/streaming.
- Thời gian replica cần thiết cho request **LOCAL_QUORUM**.

Repair **không** phải backup, không biết cách phục hồi một DELETE hợp lệ nhưng sai nghiệp vụ, và không tự tạo giao dịch ACID đa partition. **Full/incremental repair, flags, tác động lên repaired SSTables và khả năng tạm dừng** phụ thuộc phiên bản Cassandra và công cụ; đọc runbook của phiên bản thực tế.

### 2.4. Backup: snapshot khác sao chép ra ngoài cluster

Một **Cassandra snapshot** thường giữ tham chiếu hard link tới các SSTable hiện có. Tạo snapshot có thể nhanh hơn sao chép toàn bộ dữ liệu, nhưng:

- Snapshot **giữ các SSTable** không được thu hồi cho tới khi xóa snapshot theo quy trình; disk free có thể giảm theo thời gian.
- Snapshot không tự nằm **ngoài miền lỗi** của node/ổ đĩa.
- Snapshot mới tạo không đồng nghĩa bản backup có checksum/manifest và đã được chuyển ra external storage.
- Thao tác **copy/upload backup** tiêu thụ disk read, network, CPU (nén/mã hóa/checksum) và I/O ở nơi nhận.
- Incremental backup hoặc archive commitlog, nếu bật, có cách lưu và dung lượng riêng; phải đo và kiểm tra cấu hình/version.

Backup được đánh giá bằng cả **ảnh hưởng tới workload đang chạy** và **khả năng khôi phục dữ liệu**; một job báo “upload succeeded” vẫn chưa chứng minh restore đạt RPO/RTO.

### 2.5. So sánh nhanh

| Tác vụ | Đường tải thường thấy | Hệ quả cần kiểm chứng | Không được suy ra |
|---|---|---|---|
| **Bootstrap** | Sender disk read/network, receiver disk write, topology changes | Node gia nhập đúng trạng thái, dữ liệu/token và CL vận hành đúng, p99 phục hồi | Thêm node luôn làm API nhanh ngay |
| **Streaming độc lập** | Network/disk read-write, sessions và retries | Tiến độ/bytes, không thiếu dữ liệu, CQL vẫn đạt SLO | Streaming thành công nghĩa mọi repair hoàn tất |
| **Repair** | Validation I/O/CPU, network và streaming khác biệt | Repair coverage và tiến độ, replica health, correct data | Repair thay thế backup |
| **Snapshot** | Metadata/hard links, flush nếu quy trình yêu cầu, pinned SSTables | Snapshot manifest, dung lượng lưu giữ, disk headroom | Snapshot local đã an toàn ngoài miền lỗi |
| **Copy/upload backup** | Disk read, nén/mã hóa/checksum, network outbound | Bản sao độc lập, checksum và restore drill | Copy xong là tự động khôi phục được |

## 3. Luồng tải từ ứng dụng Java đến node Cassandra

~~~mermaid
flowchart LR
    A["Load generator\nCQL / Java Driver"] --> B["Coordinator\nrouting + CL"]
    B --> C["Replica 1\nmemtable/SSTable"]
    B --> D["Replica 2\nmemtable/SSTable"]
    B --> E["Replica 3\nmemtable/SSTable"]
    F["Bootstrap / repair / backup"] --> G["Disk + Network + CPU/GC"]
    G --> C
    G --> D
    G --> E
    C --> H["Compaction, flush, streaming"]
    D --> H
    E --> H
    H --> G
~~~

Một statement được định tuyến dựa vào **partition key** và token ownership. Với **RF = 3** trong một DC, request **LOCAL_QUORUM** thường cần phản hồi từ **hai trong ba replica**. Khi một replica đang gửi SSTable hoặc một ổ đĩa bị bão hòa, request có thể chậm dù coordinator không dùng nhiều CPU.

Cũng có thể có **hot partition**: hàng nghìn request cùng trỏ đến một partition và nhóm replica của nó. Khi đó số node được thêm không có nghĩa tải của key nóng tự chia đều; cần thiết kế lại bucketing/sharding theo truy vấn.

### 3.1. Bốn nguồn nhiễu khi đo

1. **Thay đổi distribution của partition key** làm kết quả khác vì hot token, không phải vì repair.
2. **Thay đổi consistency level** làm độ trễ/error thay đổi mà không phản ánh cùng cam kết nghiệp vụ.
3. **Thay đổi query/payload** làm byte hoặc tombstone/collection cost khác nhau.
4. **Thay đổi số load generators/connection pools** có thể khiến client bão hòa trước Cassandra.

Do đó, giữ workload/query shape/CL/data fixture tương đương giữa baseline và tác vụ. Nếu bắt buộc thay đổi, phải ghi lại đó là **biến thí nghiệm**.

## 4. Thiết kế bảng thử nghiệm theo truy vấn

Mô hình ví dụ: dịch vụ ghi event và đọc lịch sử của một tenant theo ngày.

~~~sql
-- Chỉ cho lab/staging có topology phù hợp dc1, RF 3.
CREATE KEYSPACE IF NOT EXISTS load_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS load_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_at, event_id)
) WITH CLUSTERING ORDER BY (event_at DESC, event_id ASC);

-- Mẫu point-lookup theo một business request.
CREATE TABLE IF NOT EXISTS load_lab.event_by_id (
    tenant_id uuid,
    event_id uuid,
    event_at timestamp,
    event_type text,
    PRIMARY KEY ((tenant_id, event_id))
);
~~~

**Thiết kế:**

- **(tenant_id, event_day)** là partition key cho truy vấn lịch sử. Query phải bind cả hai thành phần; ngày là bucket để tránh một partition tăng vô hạn.
- **event_at, event_id** là clustering columns; sắp mới nhất trước, ID phân biệt các event có timestamp bằng nhau.
- **(tenant_id, event_id)** là partition key của bảng lookup riêng. Một bảng có thể được ghi dạng denormalized; nếu dual-write, phải có idempotency/reconciliation phù hợp.
- **payload** ảnh hưởng row size và network/disk throughput; nên dùng dữ liệu tổng hợp, không dùng PII/secret thật.
- Với tenant cực nóng, bucket theo ngày vẫn có thể lớn; cần đo row count, bytes/partition, tombstone và thay bucket/shard khi cần.

### 4.1. Prepared read và write

~~~sql
-- Đọc một partition có giới hạn.
SELECT event_at, event_id, event_type, payload
FROM load_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;

-- Ghi event với khóa được tạo từ đầu logical request.
INSERT INTO load_lab.events_by_tenant_day (
    tenant_id, event_day, event_at, event_id, event_type, payload
) VALUES (?, ?, ?, ?, ?, ?);

-- Điểm đọc độc lập theo một event ID.
SELECT event_at, event_type
FROM load_lab.event_by_id
WHERE tenant_id = ?
  AND event_id = ?;
~~~

Bộ nạp tải phải **preload dữ liệu bằng một quy trình riêng**, với key distribution ổn định trước khi đo. Đọc vào partition trống có thể nhanh nhưng **không đại diện** cho workload có nhiều SSTable/tombstone. Ngược lại, viết liên tục vào một partition duy nhất có thể đo **hotspot** chứ không phải throughput bình thường.

### 4.2. Kiểm soát schema, keyspace và fixture

- Schema/keyspace được tạo **trước baseline**, không chạy DDL từ mọi client khi benchmark bắt đầu.
- Preload phải được đánh dấu hoàn tất và kiểm tra row count/partition sample.
- Dùng cùng kiểu dữ liệu, payload size, TTL/tombstone distribution và tỷ lệ read/write cho mọi lượt so sánh.
- Không dùng **ALLOW FILTERING** để tạo một workload khó dự đoán rồi kết luận từ latency.
- Không tự thêm index/secondary table hoặc đổi compaction strategy giữa hai lượt nếu mục tiêu là đo tác động riêng của bootstrap.
- Nếu workload thực có TTL/tombstone, tạo fixture đại diện và theo dõi riêng tác động read amplification.

## 5. Định nghĩa các loại workload và tài nguyên

Không có benchmark “Cassandra chung” đủ dùng cho mọi ứng dụng. Hãy chọn ít nhất hai cấu hình:

| Workload | Mục đích | Thành phần cần giữ ổn định |
|---|---|---|
| **Representative mix** | Mô phỏng lưu lượng thực: ví dụ 70% reads, 30% writes | Query shapes, partition distribution, row size, CL, page size |
| **Read-heavy** | Xem read p99, tombstone/SSTable pressure | Phân phối partition và kích thước kết quả |
| **Write-heavy** | Xem commitlog/memtable/flush/compaction | Mutation bytes/s, batch và concurrency |
| **Hot-partition case** | Thử giới hạn khi một tenant nóng | Danh sách hot keys và tỷ lệ skew |
| **Bulk/batch job** | Xem ảnh hưởng backfill/export thực tế | Bounded parallelism, retry budget, deadline |
| **Control workload** | So dữ liệu khi không có tác vụ vận hành | Cùng code/driver/cluster size/capacity |

Các tỷ lệ **70/30, N requests/s, page size 100** trong bài chỉ là ví dụ. Giá trị nghiệm thu phải theo SLO, truy vấn và dữ liệu thực của hệ thống.

### 5.1. Hai cách tạo tải

- **Open-loop:** phát request theo **arrival rate** định trước, đo cả request bị admission từ chối/timeout. Giúp thấy hệ thống đối phó thế nào khi tải không tự giảm theo latency.
- **Closed-loop:** N workers gửi request kế tiếp sau khi request trước hoàn thành. Khi server chậm, tốc độ phát tự giảm; có thể **che điểm bão hòa** nếu chỉ xem error rate.

Nên dùng cả hai khi có thể và ghi rõ mô hình. Nếu chỉ chạy **N threads** rồi báo “1.000 ops/s” mà không theo dõi số request đã gửi, đã hoàn tất và đã bị drop, phép đo dễ sai.

### 5.2. Đặt giới hạn từ phía client

Java Driver cho phép bất đồng bộ, nhưng **async không có nghĩa số request vô hạn là an toàn**. Cần:

- Giới hạn **in-flight** (Semaphore/concurrency control) và hàng đợi.
- Giới hạn **arrival rate**, timeout và số attempts.
- Ghi riêng **logical requests** và **physical driver attempts/retries**.
- Với paging, đo **first-page latency** và **full-result latency**; không chỉ đo executeAsync trang đầu.
- Đừng chạy generator, Cassandra node và công cụ backup trên cùng máy nếu việc đó làm CPU/disk/nic của máy tạo tải bão hòa rồi gây sai kết luận.

## 6. Kịch bản đo có kiểm soát

Một lượt đo cần ít nhất ba pha:

~~~mermaid
flowchart TD
    A["Preflight: schema, RF/CL, node health, disk free"] --> B["Warm-up + workload ổn định"]
    B --> C["Baseline: đo p50/p95/p99 và throughput"]
    C --> D["Một tác vụ: bootstrap / stream / repair / backup"]
    D --> E["Giữ cùng workload và ghi metrics theo thời gian"]
    E --> F{"Vượt stop gate?"}
    F -->|Có| X["Dừng phát tải / can thiệp theo runbook"]
    F -->|Không| G["Tác vụ hoàn tất và xác minh"]
    G --> H["Recovery window: đo thời gian trở lại baseline"]
    H --> I["So sánh, ghi evidence và quyết định GO/NO-GO"]
~~~

**Chạy từng tác vụ độc lập trước khi thử chồng lấp.** Nếu repair và backup cùng chạy rồi p99 tăng, bạn không biết phần ảnh hưởng của từng thao tác trừ khi đã có baseline và thử nghiệm đối chứng. Dùng cùng workload và điều kiện đầu vào giữa các lượt, lặp lại khi cần để giảm nhiễu.

### 6.1. Ma trận thí nghiệm đề xuất

| Case | Workload CQL | Tác vụ nền | Cần đo thêm |
|---|---|---|---|
| **C0** | Representative mix | Không chạy tác vụ mới | Baseline, traffic/noise có sẵn |
| **B1** | Cùng mix | Bootstrap thêm một node lab | Streaming bytes, node JOINING → NORMAL, p99 |
| **S1** | Cùng mix | Streaming theo một thủ tục lab được duyệt | Sender/receiver disk/network, tiến độ |
| **R1** | Cùng mix | Repair token ranges được phép | Repair session, validation, streaming/compaction |
| **P1** | Cùng mix | Snapshot local có kiểm soát | Snapshot duration, disk pinned/free |
| **P2** | Cùng mix | Sao chép backup ngoài node | Copy throughput, network/disk, checksum |
| **C1** | Cùng mix | Không chạy thêm, sau thao tác | Recovery time, p99 và backlog |
| **X1** | Cùng mix | Repair + backup chồng lấp có chủ đích | Tương tác tài nguyên, chỉ thử sau khi tách riêng |

**C0/C1 không được hiểu là không có compaction nền**: Cassandra vẫn có hoạt động bình thường. Mục đích là đo cùng điều kiện hoạt động nền thực tế và ghi những sự kiện có thể làm nhiễu.

### 6.2. Warm-up, thời lượng và repeated runs

- Warm-up đủ để client connection pool, cache, memtable/GC và instrumentation ổn định; tránh chỉ đo vài giây đầu.
- Đo baseline qua nhiều cửa sổ 1–5 phút hoặc theo SLO của hệ thống, không chọn một ảnh chụp p99 duy nhất.
- Một tác vụ có thể kéo dài hàng giờ. Cần dashboard/recording ổn định và chia kết quả theo các pha tải/tiến độ.
- Chạy **ít nhất vài lần** trên staging nếu cần so sánh giữa các bản cấu hình; độ biến thiên tự nhiên của disk/GC/compaction phải được thừa nhận.
- Không khởi động lượt tiếp khi cluster chưa trở lại trạng thái bình thường hoặc disk headroom chưa được phục hồi.
## 7. Đo những gì? Chỉ số từ caller đến node

Một phép đo vận hành chỉ đáng tin nếu có **correlation giữa thay đổi hệ thống và ảnh hưởng ứng dụng**. Cần thu dữ liệu trước/sau ở cùng độ phân giải thời gian.

### 7.1. Phía người gọi và Java Driver

| Nhóm | Chỉ số | Cách diễn giải |
|---|---|---|
| **Traffic** | Offered RPS, accepted RPS, completed successful RPS | Phân biệt tải gửi đến với throughput được phục vụ |
| **Latency** | p50, p95, p99, max, first-page/full-result | Người dùng có gặp tail latency khi tác vụ nền chạy? |
| **Errors** | Timeout, ReadFailure/WriteFailure, Unavailable, Overloaded | Có thiếu replica/CL, overload hay client deadline? |
| **Concurrency** | In-flight, client queue depth/wait, shed/rejected | Driver/app có bị dồn request hay không? |
| **Retries** | Service/driver/gateway retries, speculative execution | Lưu lượng vật lý có bị khuếch đại? |
| **Connections** | Pool/channel utilization, reconnects, coordinator/DC | Topology change có làm client chuyển hướng bất thường? |
| **Paging** | Số page/query, row/page, page latency | Query dài có chậm chỉ ở page sau? |
| **Correctness** | Missing/duplicate event, failed invariant, stale-read expectation | Không đánh đổi dữ liệu đúng lấy throughput cao |

**p99 tăng khi thành công giảm** có thể rất nguy hiểm: chỉ đo latency của request thành công sẽ bỏ qua các request timeout bị loại khỏi histogram. Vì vậy phải đặt **error rate và deadline-exceeded** cạnh các percentile; phân biệt successful-only latency với client-observed latency.

### 7.2. Phía Cassandra cluster

| Tầng | Metric/quan sát | Vì sao quan trọng |
|---|---|---|
| **Coordinator** | Read/Write latency, request counts, failures, timeouts | Hợp đồng CL còn đáp ứng không? |
| **Replica** | Local read/write, thread pools, pending/dropped tasks | Replica nào trở thành điểm nghẽn? |
| **Disk** | Read/write bytes/s, IOPS, await/latency, queue depth, utilization, free | Bootstrap/repair/backup cạnh tranh với CQL |
| **Network** | In/out bytes/s, cross-node/cross-DC, retransmits, packet drops | Streaming có chiếm băng thông/đường WAN? |
| **JVM** | Heap, off-heap/native RSS, GC pauses, CPU | Buffer/GC có gây tail latency? |
| **Storage internals** | SSTable count, compaction pending/active, memtable/flush | Khối lượng SSTable và I/O nền thay đổi? |
| **Streaming** | Active sessions, bytes/files sent/received, progress, failed/retried transfers | Thao tác chuyển dữ liệu có tiến triển hay bị kẹt? |
| **Repair** | Sessions/ranges hoàn thành, validation/streaming, failures | Repair coverage/tiến độ có phù hợp kế hoạch? |
| **Backup** | Snapshot count/size, pinned SSTables, copied bytes, checksum failures, external storage | Dữ liệu có thể khôi phục mà không hết disk? |
| **Topology** | Node status, DC/rack, RF, token ownership, schema agreement | SLO có dựa trên đủ replica không? |

Tên metric cụ thể khác nhau theo **Cassandra version, JMX exporter, monitoring stack, phiên bản operator hoặc managed service**. Đừng invent một tên Prometheus metric để báo là có sẵn; đọc từ **metrics registry của cluster** và ghi rõ mapping metric thực tế.

### 7.3. Phân tách pha đo theo mốc thời gian

Gắn mốc sự kiện từ orchestrator:

~~~text
T0: cluster healthy, warm-up xong
T1: bắt đầu baseline
T2: baseline kết thúc, bắt đầu tác vụ nền
T3: streaming/repair/backup đạt trạng thái tải cực đại
T4: tác vụ nền báo hoàn tất
T5: xác minh integrity và backlog nền
T6: API p99/error/throughput trở lại ngưỡng baseline
~~~

**Thời gian phục hồi sau tác vụ = T6 − T4**, không tự động bằng 0. Compaction backlog, file retention, cache thay đổi hoặc driver connection churn có thể còn ảnh hưởng lâu sau khi tool báo hoàn tất.

## 8. Lệnh quan sát Cassandra an toàn cho phép đo

Chỉ đọc metadata/metrics với các lệnh được hỗ trợ ở phiên bản đang chạy:

~~~bash
# DC/rack/token và trạng thái node.
nodetool status

# Thông tin node và một số số liệu heap/off-heap/disk.
nodetool info

# Streaming hiện tại và network tasks, nếu version hỗ trợ.
nodetool netstats

# Thread pools, pending và dropped messages.
nodetool tpstats

# Compaction đang chạy và backlog.
nodetool compactionstats

# Thống kê keyspace/table liên quan.
nodetool tablestats load_lab.events_by_tenant_day

# Kích thước partition/row và phân phối theo version.
nodetool tablehistograms load_lab events_by_tenant_day

# Snapshot đã tạo; phải đối chiếu tên/đường dẫn version.
nodetool listsnapshots
~~~

**Chỉ số từ nodetool là một phần của bằng chứng**, không thay histogram từ ứng dụng Java hoặc OS-level disk/network. Ví dụ:

- **nodetool status** cho biết node Up/Down/Joining/Leaving theo công cụ, nhưng Up không đảm bảo p99 tốt.
- **nodetool netstats** cho biết streaming đang diễn ra; **đừng suy throughput thực** chỉ từ một lần lấy counter, phải lấy nhiều mẫu và tính delta theo thời gian.
- **nodetool tpstats** có thể cho thấy pending/dropped tasks tăng; so với baseline và request error để xác định nghẽn.
- **nodetool compactionstats** cho thấy công việc compaction, nhưng latency ổ đĩa vẫn cần theo dõi độc lập.
- **nodetool listsnapshots** cung cấp thông tin snapshot theo công cụ; không cho biết bản backup đã được copy an toàn tới remote location.

Các lệnh **nodetool repair**, **rebuild**, **decommission**, **cleanup**, thao tác join/replace node, **snapshot** và **clearsnapshot** có thể thay đổi cluster hoặc dữ liệu lưu giữ. **Không chạy chúng như lệnh đọc để chẩn đoán**; chỉ thực thi qua người vận hành có quyền, đúng runbook và change window. Đặc biệt, **clearsnapshot** có thể khiến mất recovery point nếu chưa backup xong.

### 8.1. Quan sát hệ điều hành

Trên node Linux/VM/container có telemetry hợp lệ, thu:

- Disk read/write throughput, per-device latency và queue depth.
- Network in/out từng interface, retransmissions/drops.
- CPU user/system/iowait, memory, file descriptor và cgroup pressure.
- GC duration/pause, heap/off-heap, compaction I/O.
- Disk free **trước và trong** thao tác; phân biệt data dir, snapshot dir và filesystem riêng nếu có.

**Không mặc định CPU 50% nghĩa còn 50% headroom**. Một ổ SSD có thể đang đạt giới hạn IOPS hoặc p99 I/O cực cao trong khi CPU còn thấp. Tương tự, NIC throughput trung bình chưa đầy có thể vẫn có retransmit/queue và cross-DC latency.

## 9. Java load probe bất đồng bộ có giới hạn in-flight

Ví dụ dưới đây là một **thành phần của harness đo tải**, không phải benchmark production hoàn chỉnh. Nó:

- Dùng một **CqlSession** chia sẻ và **PreparedStatement**.
- Đọc một partition đã preload với **LOCAL_QUORUM**.
- Giới hạn request đang bay bằng **Semaphore**.
- Ghi nhận **thời gian trang đầu**, số success/failure/rejection và histogram qua **Micrometer Timer**.
- Không retry ở tầng ứng dụng; chính sách retry thực của driver vẫn phải được review.
- Không block callback của driver bằng **join/get/sleep**.

### 9.1. Code probe

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class BoundedReadProbe {
    private final CqlSession session;
    private final PreparedStatement select;
    private final Semaphore slots;
    private final Timer firstPageLatency;

    private final LongAdder successes = new LongAdder();
    private final LongAdder failures = new LongAdder();
    private final LongAdder rejected = new LongAdder();

    public BoundedReadProbe(
            CqlSession session, MeterRegistry registry,
            int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException(
                "maxInFlight must be positive");
        }
        this.session = session;
        this.slots = new Semaphore(maxInFlight);
        this.select = session.prepare(
            "SELECT event_at, event_id, event_type, payload " +
            "FROM load_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

        this.firstPageLatency = Timer
            .builder("cassandra.load.first_page")
            .description("Latency of first Cassandra result page")
            .publishPercentileHistogram()
            .register(registry);
    }

    public CompletionStage<AsyncResultSet> tryRead(
            UUID tenantId, LocalDate day) {

        if (!slots.tryAcquire()) {
            rejected.increment();
            return failed(new RejectedExecutionException(
                "Load probe in-flight limit reached"));
        }

        final long started = System.nanoTime();
        try {
            BoundStatement query = select
                .bind(tenantId, day, 100)
                .setPageSize(50)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            return session.executeAsync(query)
                .whenComplete((page, error) -> {
                    try {
                        firstPageLatency.record(
                            System.nanoTime() - started,
                            TimeUnit.NANOSECONDS);
                        if (error == null) {
                            successes.increment();
                        } else {
                            failures.increment();
                        }
                    } finally {
                        slots.release();
                    }
                });
        } catch (RuntimeException error) {
            failures.increment();
            firstPageLatency.record(
                System.nanoTime() - started,
                TimeUnit.NANOSECONDS);
            slots.release();
            return failed(error);
        }
    }

    public long successes() { return successes.sum(); }
    public long failures() { return failures.sum(); }
    public long rejected() { return rejected.sum(); }

    private static <T> CompletionStage<T> failed(
            Throwable error) {
        java.util.concurrent.CompletableFuture<T> result =
            new java.util.concurrent.CompletableFuture<>();
        result.completeExceptionally(error);
        return result;
    }
}
~~~

**Phụ thuộc:** API Java Driver 4.x và Micrometer Core có phiên bản tương thích. **CqlSession phải được tạo/cấu hình TLS/auth, local DC, contact points và lifecycle** bởi ứng dụng test trước khi truyền vào probe. Một process Java có thể chia sẻ session; không tạo session cho mỗi request.

**Quan trọng:** Bộ đếm success ở đây nghĩa là **trang đầu được nhận thành công**, không phải tất cả rows đã được tiêu thụ. Nếu workload thật trả nhiều page, phải **compose fetchNextPage() đến trang cuối**, đo **full-result latency** và chỉ giải phóng permit sau toàn pipeline; nếu không, số đo có thể quá lạc quan.

### 9.2. Tạo rate có kiểm soát

Một scheduler/tập workers của load test quyết định **arrival rate** và chọn **tenantId/day** từ bộ fixture đã preload. Không viết loop phát hàng triệu **CompletableFuture** rồi mới đợi chúng ở cuối.

Pseudocode:

~~~text
Tải thử nghiệm: 500 logical reads/s, tối đa 80 requests in-flight
Trong mỗi giây:
    chọn partition keys từ phân phối đã chốt (normal + hot)
    kiểm tra rate budget và admission slot
    nếu slot không còn: ghi rejected, KHÔNG enqueue vô hạn
    nếu được nhận: gọi probe.tryRead(key, day)
    ghi returned result hoặc exception class

Kết thúc mỗi phase:
    ngừng tạo request mới
    đợi outstanding operations hoàn thành trong deadline
    giữ nguyên metric histograms, error counts và run ID
~~~

**Không chỉ đo 500 requests được lên lịch.** Phải đo **offered, admitted, completed success, failed, rejected**. Nếu client từ chối 20% vì hết slots, successful throughput có thể chỉ bằng một phần tốc độ gửi danh nghĩa.

### 9.3. Không làm méo benchmark bằng chính harness

- Chạy load generator ở máy riêng có đủ CPU/network, không chung disk với node Cassandra.
- Preload fixture và warm up trước khi đo; tránh tạo UUID/serialize payload quá nặng trong mỗi callback.
- Kiểm tra generator CPU, GC, connection pool và queue; nếu nó bão hòa, phép đo không còn chỉ phản ánh Cassandra.
- Giữ cùng phiên bản Java driver, timeout, retry policy, CL và prepared statements giữa các case.
- Micrometer histogram giúp quan sát phân phối latency, nhưng cần kiểm tra **sampling/export/percentile** và độ phân giải; **không dùng thời gian trung bình thay p99**.
- Với ứng dụng Spring Boot có metrics sẵn, có thể đo trực tiếp tại API endpoint, rồi dùng probe như đối chứng; probe không tự thay thế **end-to-end SLA test**.

## 10. Đọc/ghi hỗn hợp và tính đúng dữ liệu khi benchmark

Một workload chỉ SELECT có thể bỏ qua áp lực flush/commitlog của production; một workload chỉ INSERT có thể không tái hiện vấn đề read path do nhiều SSTable/tombstone. Thiết kế phối hợp:

~~~text
Logical operation mix (ví dụ):
  65% SELECT theo tenant + event_day
  25% INSERT event mới với event_id ổn định
  10% point SELECT theo tenant + event_id

Mỗi operation ghi:
  query_shape, logical_request_id, key_distribution_group,
  regular_consistency, elapsed_ms, result_state,
  driver_attempts_observed, payload_bytes_group
~~~

Đây là **tỷ lệ minh họa**. Nếu dual-write hai bảng, cần đo tổng mutations và đảm bảo không nhầm **một logical event** với **hai physical writes**. Khi retry sau timeout:

- Ghi mới cần **event_id cố định** trên các attempts, không tạo duplicate IDs.
- Chỉ đánh dấu **setIdempotent(true)** cho mutation đã xác minh an toàn (key/value/timestamp/TTL và side effects).
- Với **WriteTimeout/WriteFailure**, outcome có thể UNKNOWN; không coi là “chưa ghi”.
- Đo **successful logical operations** thay vì đếm tất cả mutations/driver attempts như kết quả kinh doanh.

Nếu test cần bảo đảm event được xử lý một lần end-to-end, thêm **idempotency key, kiểm tra đối soát và reconciliation** ở tầng service. Việc benchmark lên tới throughput cao mà làm mất/nhân đôi dữ liệu không đạt tiêu chí chất lượng.

## 11. Ma trận chỉ số kết hợp sự kiện với tác động

| Nếu quan sát thấy | Cần kiểm tra thêm | Giả thuyết có thể kiểm chứng |
|---|---|---|
| p99 tăng, success RPS giảm | Disk await, streaming network, pending read | Streaming cạnh tranh disk/network với CQL |
| p99 tăng nhưng CPU thấp | Disk latency/queue, GC pause, replica skew | Nút thắt không nằm ở CPU trung bình |
| Network outbound sender tăng | netstats sessions, retransmits, cross-DC | Bootstrap đang chiếm bandwidth |
| Compaction pending tăng sau stream | SSTable count, disk free, compaction throughput | Node nhận còn áp lực nền sau khi copy xong |
| Repair duration tăng bất thường | Repair ranges, validation, I/O, failed sessions | Repair bị cạnh tranh tài nguyên hoặc một range nóng |
| Snapshot nhanh nhưng disk free giảm dần | Snapshot size, SSTable retention, backup copy status | Snapshot pin SSTables, cleanup chưa đúng thời điểm |
| Backup upload chậm, read latency xấu | Backup read I/O, NIC, checksum CPU | Copy/chunking/throughput làm nghẽn resource |
| Client timeout tăng, server timeout không tăng tương ứng | Queue, driver timeout, retry, network | Có nghẽn tại client/connection path |
| LOCAL_QUORUM error tăng khi node mất | RF, node status, coordinator logs | Không đủ replica/timeout theo CL |
| Đọc thấy thiếu dữ liệu sau topology change | Schema, token ownership, CL, fixture, logs | Phải điều tra correctness; không chỉ nâng timeout |

Đây là **giả thuyết**, không phải quan hệ nhân quả được bảo đảm. Cần so sánh timeline, baseline và kiểm thử lặp hoặc test đối chứng để kết luận.

## 12. Preflight: điều kiện được phép bắt đầu

Trước khi chạy từng case, ghi rõ:

1. **Môi trường và quyền:** cluster staging/lab nào, ai có quyền vận hành, ai phê duyệt?
2. **Topology:** Cassandra version, số node, DC/rack, keyspace RF, local DC của Java Driver.
3. **Node health:** không có node DOWN bất thường, gossip/schema agreement phù hợp.
4. **Tình trạng dữ liệu:** fixture preload đầy đủ, partitions/hotkeys phân bố hợp lệ, backup phục hồi gần nhất.
5. **Disk headroom:** có đủ chỗ cho streaming nhận, snapshot pin và compaction; không chỉ tính kích thước data hiện tại.
6. **Capacity headroom:** network, disk IOPS, CPU/GC chưa ở ngưỡng đỏ ngay baseline.
7. **Monitoring:** metrics đủ timestamp và dashboard p99, errors, streaming, compaction, backup.
8. **Tải generator:** đã kiểm tra không nghẽn client và có công tắc dừng.
9. **Stop/rollback plan:** ai quyết định, điều kiện dừng, thao tác nào **không thể hủy an toàn**.
10. **Tính đúng dữ liệu:** có fixture/hash/count và phương pháp đối soát trước/sau.
11. **Các tác vụ khác:** compaction, repair, backup, ETL theo lịch có thể gây nhiễu; ghi nhận, không tắt bừa.
12. **Version-specific operations:** xác minh cú pháp và giới hạn của nodetool/operator cho cluster hiện tại.

Nếu baseline đã ở mức quá tải hoặc disk free quá thấp, **NO-GO** với bài thử bootstrap/repair lớn. Bài học không khuyến nghị tạo thêm áp lực để “xem hệ thống chịu tới đâu” khi chưa có headroom/recovery path.

## 13. Case B1 — đo tải khi một node bootstrap

### 13.1. Mục tiêu và phạm vi

Câu hỏi: **Một node mới được thêm vào cluster trong khi workload CQL giữ nguyên có làm vượt p99/error budget không?** Kèm theo đó, xác minh việc nhận token ranges/dữ liệu diễn ra an toàn và thời gian phục hồi sau bootstrap.

Chỉ thực hiện trên cluster staging có cấu trúc tương ứng với production, với kế hoạch thêm node đã được DBA/SRE phê duyệt. Không tạo node mới chỉ bằng cách thay container count khi chưa xác minh token/seed/DC/rack/replication, disk capacity và Cassandra version.

### 13.2. Các bước kiểm thử

1. **Preflight:** xác minh số node, DC/rack, RF, schema agreement, disk headroom, SSTable count, GC, compaction và các phiên bản Cassandra/SSTable format.
2. **Preload:** chuẩn bị dữ liệu đủ lớn để tạo streaming có ý nghĩa, nhưng không vượt khả năng chịu tải của môi trường thử; không dùng dữ liệu khách hàng thật.
3. **Baseline:** chạy representative read/write mix ở arrival rate đã chốt. Ghi p50/p95/p99, successful RPS, failures, retries, in-flight và OS metrics.
4. **Mark T2:** ghi thời điểm người vận hành bắt đầu quy trình bootstrap qua cơ chế được hỗ trợ và được phê duyệt.
5. **Theo dõi mỗi cửa sổ:** nodetool status/netstats, bytes sent/received, sender/receiver disk, network và pending compaction, request p99/error rate.
6. **Không tăng load generator** giữa chừng khi thấy Cassandra có thêm node. Đối tượng nghiên cứu là tác động topology, không phải khả năng chịu tải khi đồng thời đổi arrival rate.
7. **Khi bootstrap hoàn tất:** kiểm tra node ở trạng thái kỳ vọng, token ownership/replica placement và schema, streaming sessions không còn lỗi chưa xử lý.
8. **Recovery window:** giữ workload thêm một khoảng phù hợp, đo pending tasks/compactions, disk free và p99 trở về baseline.
9. **Đối soát:** đọc fixture từ các partition đại diện ở nhiều token ranges; không chỉ xác minh node UP.
10. **Kết luận:** nêu thời gian bootstrap, peak network/disk, worst p99/error, recovery time và tình trạng dữ liệu.

### 13.3. Kết quả có thể quan sát

| Giai đoạn | Quan sát giả định | Diễn giải cần xác minh |
|---|---|---|
| Trước bootstrap | p99 ổn định, disk/network dưới ngưỡng | Baseline hợp lệ |
| Đang nhận SSTable | Sender disk read cao, receiver disk write cao | Streaming đang cạnh tranh với workload |
| Streaming sắp xong | P99 vẫn có thể tăng, compaction pending | Công việc hậu streaming chưa hoàn tất |
| Node chuyển trạng thái bình thường | Netstats hết luồng, node UP/NORMAL | Chưa đủ để kết luận API đã phục hồi |
| Sau 15–30 phút quan sát | p99/throughput và queue trở lại baseline | Có bằng chứng về recovery |

Khoảng **15–30 phút** là ví dụ; tùy dữ liệu và tải nền, window có thể dài hơn. Không đặt mốc thời gian cứng làm tiêu chí duy nhất.

### 13.4. Những điều không nên làm

- Không tự thay **RF** chỉ để bootstrap trông nhanh hơn; đó là một thay đổi replication cần kiểm soát riêng.
- Không ép **LOCAL_QUORUM → ONE** trong load generator để giảm error mà không ghi rõ đã đổi biến thí nghiệm.
- Không dùng “bootstrap finished” thay thế kiểm tra dữ liệu và API latency.
- Không tạo nhiều node cùng lúc nếu chưa thử một node; nhiều streamers có thể nhân tải.
- Không chạy repair/cleanup hay thay token giữa bootstrap chỉ vì thấy tác vụ chậm, trừ khi runbook chính thức yêu cầu.
- Không suy rằng hot partition đã được giải quyết: workload nóng vẫn có thể dồn vào nhóm replica lưu cùng token range.

## 14. Case S1 — đo streaming độc lập

Streaming xuất hiện ngay trong bootstrap (case B1), nhưng có thể còn phát sinh khi rebuild/replacement/decommission hoặc repair theo cơ chế được hỗ trợ. Cần phân biệt:

- **Đo streaming nằm trong bootstrap:** giữ đầy đủ bối cảnh topology change.
- **Đo riêng chi phí truyền SSTable:** dùng một tình huống streaming khác đã được phê duyệt trên cluster thử nghiệm, và ghi chính xác operation gây stream.
- **Không giả lập “streaming” bằng copy file SSTable thủ công vào data directory**; có thể gây rủi ro dữ liệu và không đại diện protocol streaming.

### 14.1. Những chỉ số quan trọng

1. **Bytes cần chuyển:** lượng dữ liệu dự kiến theo token ranges/repaired SSTables.
2. **Effective throughput:** bytes hoàn thành / elapsed time, phân biệt inbound/outbound.
3. **Số sessions đồng thời**, failed/retried sessions và tail duration.
4. **Sender disk read, receiver disk write**, IOPS, disk latency và free.
5. **NIC throughput/retransmissions** theo tuyến giữa các node, đặc biệt khi qua DC/WAN.
6. **CQL p99/error, queue/in-flight** và retry amplification trong cùng thời điểm.
7. **Compaction backlog** và tình trạng snapshot/backup có đang pin SSTables không.

Ví dụ, giả sử phải chuyển **120 GiB** ở tốc độ hiệu dụng **60 MiB/s**:

~~~text
120 GiB = 122.880 MiB
122.880 MiB / 60 MiB/s = 2.048 giây ≈ 34,1 phút
~~~

Đây chỉ là **ước lượng lý tưởng** từ dữ liệu/throughput; còn overhead protocol, concurrent streams, validation, retries, tài nguyên cạnh tranh, biến động tốc độ và việc giữ p99 dưới SLO. **Không dùng công thức này như dự báo hoàn tất chắc chắn.**

### 14.2. Streaming nhanh nhất không phải mục tiêu duy nhất

Nếu tăng tốc streaming làm disk utilization bão hòa, read p99 có thể vượt SLO hoặc phát sinh timeout. Cân nhắc profile:

| Profile | Giới hạn băng thông/tác vụ nền | Trọng tâm |
|---|---|---|
| **Ưu tiên API** | Streaming được điều tiết, giữ resource headroom | Bảo vệ SLO interactive |
| **Cân bằng** | Có headroom ổn định cho API và transfer | Tối ưu tổng thời gian theo mục tiêu |
| **Ưu tiên hoàn tất bảo trì** | Có thể dùng thêm tài nguyên trong window cho phép | Chỉ phù hợp khi traffic thấp/có chấp thuận |

Các option điều tiết streaming cụ thể phụ thuộc Cassandra version/operator. Trước khi thay config, cần đối chiếu cơ chế **throttling thực tế** và test trên staging, tránh sao chép tên property cũ từ một phiên bản khác.

### 14.3. Tách độ trễ network với disk

- Nếu **network thấp** nhưng disk await cao: khả năng bị giới hạn bởi disk read/write, flush hoặc compaction.
- Nếu disk còn headroom nhưng **network bão hòa/retransmit cao**: xem NIC, routing, WAN, MTU và streaming sessions.
- Nếu hai phía đều thấp nhưng progress đứng yên: kiểm tra failed sessions, node health, errors và task queue.
- Nếu chỉ client p99 xấu trên một nhóm partition: xem coordinator/replica placement và hot token range; không kết luận mọi node cùng bị nghẽn.

Một lần nhìn throughput chỉ cho biết “hệ đang bận”; cần tương quan nhiều cửa sổ với thời điểm progress và SLO.

## 15. Case R1 — đo tải trong repair

### 15.1. Repair là workload đọc/đối soát/ghi, không chỉ một lệnh

Repair cần được lập lịch theo chính sách nhất quán của tổ chức, dựa trên phiên bản Cassandra, RF/DC, số node và chiến lược repair. Trên cluster thử nghiệm, **chỉ người vận hành được phê duyệt** kích hoạt một phiên repair đã chọn phạm vi, ví dụ một keyspace/table hoặc những token ranges cụ thể.

Thử nghiệm cần ghi:

- **Loại repair:** full/incremental hoặc phiên bản tool/operator đang dùng.
- **Phạm vi:** keyspace, table, ranges, DC/hosts theo hỗ trợ.
- **Đồng thời:** bao nhiêu repair sessions/validation/streaming.
- **Dữ liệu:** dung lượng, SSTable count, mức độ khác biệt giữa replica.
- **Tài nguyên:** disk I/O/CPU/network/GC và backlog compaction.
- **Ngữ nghĩa hoàn tất:** phạm vi/ranges nào thực sự được repaired và có lỗi nào không.

Đừng dùng lệnh **repair toàn cluster/toàn keyspace** như một bài benchmark nhanh khi chưa có runbook và capacity plan. Repair có thể nặng hơn nhiều so với snapshot local, đặc biệt trên dữ liệu lớn, nhiều SSTable hoặc mạng chậm.

### 15.2. Phép đo theo ba pha

| Pha | Metric đáng quan sát | Câu hỏi |
|---|---|---|
| **Validation/so sánh** | Disk read, CPU, SSTable I/O, time/range | Chậm vì phải đọc dữ liệu hay vì tài nguyên thiếu? |
| **Streaming khác biệt** | Bytes sent/received, network, disk write | Bao nhiêu dữ liệu cần đồng bộ, bandwidth có bị nghẽn? |
| **Hậu repair** | Compaction backlog, disk free, CQL p99 | API có phục hồi và repair hoàn tất đúng phạm vi? |

Phân chia thực tế có thể khác theo version/repair implementation; không mặc định mọi phiên repair đều có tỷ lệ streaming dữ liệu lớn. Nếu các replica không có khác biệt đáng kể, repair vẫn có thể tốn I/O validation dù bytes streamed nhỏ.

### 15.3. Những thử nghiệm hữu ích

1. **Baseline CQL** không có repair mới.
2. Chạy một phiên repair đã chốt phạm vi, giữ nguyên workload.
3. Ghi **thời điểm bắt đầu/validation/stream/end** cùng timeline metric.
4. Nếu runbook hỗ trợ, thử chính sách **giới hạn parallelism/throughput** ở một lượt riêng.
5. So **repair completion time** với p99/error/in-flight/disks của các lượt.
6. Kiểm tra dữ liệu sample có các kết quả đúng sau repair bằng CL thích hợp.
7. Theo dõi **hậu repair** cho đến khi compaction/backlog trở lại mức chấp nhận.

**Không tạo inconsistency bằng cách chỉnh SSTable trực tiếp, sửa system tables hoặc ép tắt node production.** Fault test về replica khác biệt phải thực hiện qua cơ chế lab được hỗ trợ với kế hoạch restore rõ.

### 15.4. Khi repair làm lộ ra lỗi

Nếu thấy nhiều **ReadTimeout, WriteTimeout, Unavailable hoặc Overloaded**:

- Kiểm tra RF/CL/node health trước khi chỉ tăng timeout.
- Xem disk queue/latency và compaction, không chỉ CPU.
- Kiểm tra repair concurrency/streaming pressure có vượt resource budget không.
- Giữ workload và giảm tác vụ nền theo runbook nếu có thể, hoặc **PAUSE/STOP** theo tiêu chí đã duyệt.
- Không retry CQL vô hạn trong Java; những write đã timeout có outcome chưa rõ và cần idempotency key/reconciliation.

### 15.5. Repair không phải một chỉ số backup

Repair thành công không chứng minh có thể phục hồi cluster sau DROP sai, lỗi vận hành hoặc mất cả DC. Cần backup độc lập, manifest, bảo mật và restore drill. Ngược lại, backup tốt không thay thế trách nhiệm repair/replica convergence của cluster.

## 16. Case P1/P2 — đo snapshot và backup ngoài cluster

### 16.1. Tách thao tác thành các pha

~~~mermaid
flowchart TD
    A["Preflight backup: disk free, source health"] --> B["P1: tạo snapshot theo runbook"]
    B --> C["Ghi manifest/SSTable links và dung lượng pinned"]
    C --> D["P2: copy/upload dữ liệu ra miền lỗi độc lập"]
    D --> E["Checksum/encryption/manifest validation"]
    E --> F["Restore drill trên cluster cô lập"]
    F --> G["Đối soát CQL/schema và RPO/RTO"]
    G --> H["Xóa snapshot local khi được phê duyệt"]
~~~

**Đo cả chuỗi.** Một snapshot tạo trong vài giây không có nghĩa backup toàn bộ đã hoàn thành: upload qua mạng, checksum và restore có thể chiếm phần lớn thời gian/tài nguyên.

### 16.2. Snapshot local

Cassandra snapshot giữ SSTable files thông qua hard links ở data directory theo thiết kế SSTable snapshot. Cần theo dõi:

- **Snapshot creation duration**, flush hoặc I/O kèm theo theo cách gọi/version.
- **Snapshot count, tag, paths, SSTable filenames/bytes**.
- **Disk free/pinned bytes** trong thời gian giữ snapshot; compaction có thể không thu hồi được SSTables vẫn được snapshot tham chiếu.
- **Flush/compaction latency** và ảnh hưởng read/write khi tạo/giữ snapshot.
- **Tính nhất quán của backup set** qua nodes/token ranges và schema/metadata.

Không tạo snapshot liên tục để “benchmark” nếu disk headroom thấp. Một snapshot local vẫn chịu chung lỗi vật lý node/volume.

### 16.3. External backup copy

Trong giai đoạn copy ra storage độc lập, theo dõi:

| Nguồn đo | Metric | Mục đích |
|---|---|---|
| Source node | Disk read bytes/s, await/queue | Backup có cạnh tranh với Cassandra reads? |
| Host/sidecar backup | CPU nén/mã hóa/checksum, heap/queue | Backup tool có thành nút thắt? |
| Network | Upload bytes/s, retransmits, egress link | Đường truyền có bão hòa/cross-DC charge? |
| Object store/destination | Completed bytes, failed chunks, retry count | Copy có tiến triển ổn định không? |
| Cassandra | p95/p99, successful RPS, read/write errors | API có mất SLO vì backup? |
| Storage | Snapshot pinned/retained size và disk free | Recovery points có gây thiếu dung lượng? |

Một thao tác copy có thể đọc file SSTable lớn và chiếm I/O trong khi Cassandra cũng đang compaction/streaming. Nếu có nhiều nodes copy đồng thời, tổng network/disk load có thể lớn hơn số đo trên một node.

### 16.4. Tính toàn vẹn và khả năng restore

Backup chỉ đạt khi có bằng chứng:

1. **Phạm vi chính xác:** keyspace/tables, token coverage, schema và version.
2. **Manifest/checksum:** file cần thiết có mặt, checksums/size khớp, backup job không báo partial.
3. **Bảo mật:** TLS, encryption-at-rest, KMS/IAM và retention theo chính sách.
4. **Bản sao khác miền lỗi:** không chỉ một snapshot trên cùng disk/node.
5. **Restore drill:** phục hồi trên môi trường cô lập tương thích Cassandra/Java driver, không phá cluster nguồn.
6. **Đối soát dữ liệu:** fixture/query theo partition key, row counts/khóa mẫu/invariant.
7. **RPO/RTO:** mất dữ liệu tối đa và thời gian khôi phục được đo thực tế, không chỉ dự đoán.

Nếu hệ thống yêu cầu **point-in-time recovery**, snapshot có thể cần kết hợp incremental backup/commitlog archiving theo kế hoạch và version cụ thể. Không tự giả định chỉ một snapshot đủ khôi phục mọi write đến đúng thời điểm T.

### 16.5. Ví dụ bảng đánh giá backup

| Giai đoạn | Thời lượng | Ảnh hưởng API | Bằng chứng |
|---|---|---|---|
| Snapshot local | Đo thực | p99/error lúc tạo | Snapshot tag/manifest |
| Copy ngoài cluster | Đo thực | p99/error trong copy | Checksums, remote objects |
| Verify integrity | Đo thực | CPU/disk của verifier | Match hashes/coverage |
| Restore drill | Đo thực | Chạy trên cluster cô lập | Data correctness, RPO/RTO |
| Cleanup local | Đo thực | Disk free sau cleanup | Xác nhận recovery point đã an toàn |

Không xóa snapshot local cho tới khi chính sách retention và **xác nhận external backup** cho phép. Ngược lại, không giữ vô hạn làm disk full; cần lifecycle backup được quản lý bởi owner.
## 17. Khi repair, streaming và backup chồng lấp

Trong production, maintenance thường cạnh tranh cùng những tài nguyên vật lý:

~~~text
Repair validation       → SSTable reads + CPU
Streaming sender        → SSTable reads + network outbound
Streaming receiver      → Network inbound + SSTable writes
Backup copy             → SSTable reads + network outbound
Compaction              → SSTable reads + SSTable writes + CPU
CQL application reads   → Memtable/SSTable reads + network
CQL application writes  → Commitlog/memtable + flush/compaction
~~~

Khi những công việc này cùng chạy, throughput disk/network có thể chạm giới hạn ngay cả khi từng công việc riêng lẻ ở dưới ngưỡng.

### 17.1. Đo chi phí chồng lấp sau khi đã có số đo riêng

| Test | Tác vụ | Mục đích | Điều kiện |
|---|---|---|---|
| **R1** | Repair đơn độc | Đo overhead repair | Baseline hợp lệ |
| **P2** | Backup copy đơn độc | Đo overhead backup network/disk | Backups có đủ storage |
| **X1** | Repair + backup copy | Đo tác động cộng hưởng | Đã hiểu R1/P2 và có stop gates |
| **X2** | Bootstrap + backup | Mô phỏng khung bảo trì khó | Chỉ khi thật sự cần và được phê duyệt |
| **C1** | Không có tác vụ mới sau X1/X2 | Đo recovery/backlog | Cluster vẫn đủ headroom |

Không nên chạy X1/X2 nếu riêng R1/P2 đã làm request p99/error vượt SLO. Thử chồng lấp cần **kịch bản business thực**, không phải thử hủy hoại cluster.

### 17.2. Đừng cộng đơn giản hai giá trị p99

Nếu repair riêng làm p99 tăng 80 ms và backup riêng tăng 50 ms, không thể dự đoán p99 khi cả hai chạy bằng **baseline + 80 + 50**. Tail latency chịu queueing, cache, disk contention, GC, token skew và retry amplification phi tuyến. Cần **đo trực tiếp** kịch bản chồng lấp và so cả success throughput/error, không chỉ p99.

### 17.3. Lập lịch và giới hạn tác vụ nền

Đội vận hành có thể chọn:

- Không cho repair và backup copy nặng chạy cùng lúc trong giờ cao điểm.
- Điều tiết backup upload hoặc streaming throughput theo bandwidth/disk headroom.
- Giới hạn số jobs/nodes tham gia repair cùng lúc theo công cụ được hỗ trợ.
- Dùng calendar để tránh chồng lấp với upgrade, restore drill, ETL/backfill lớn.
- Tăng headroom hay thêm capacity **trước** khi triển khai một lịch bảo trì mới.

Các quyết định dựa trên **SLO và khả năng phục hồi**; không tối ưu chỉ theo tốc độ hoàn thành maintenance. Một job chạy nhanh nhất nhưng làm gián đoạn API không nhất thiết là lựa chọn tốt.

## 18. Stop gates: khi nào tiếp tục, giảm tải hoặc dừng?

Phải định nghĩa điều kiện **GO / THROTTLE / PAUSE / STOP / ESCALATE** trước khi test. Các ngưỡng sau chỉ là **ví dụ**, không phải tiêu chuẩn chung của Cassandra:

| Tiêu chí minh họa | GO | Cần xem xét điều tiết | STOP/ESCALATE |
|---|---|---|---|
| **API p99** | Dưới ngưỡng SLO đã duyệt | Tăng kéo dài dù chưa vi phạm | Vượt SLO liên tục qua nhiều cửa sổ |
| **Error rate** | Trong error budget | Tăng bất thường theo case | Unavailable/Overloaded hoặc error budget bị đe dọa |
| **Disk free** | Còn headroom cho stream/compaction/snapshot | Dự báo không đủ cho phần còn lại | Chạm giới hạn an toàn hoặc tăng nguy cơ disk full |
| **Disk latency/queue** | Trong ngưỡng đại diện | Tăng và p99 bắt đầu xấu | Saturation kéo dài, pending tasks tăng liên tục |
| **Streaming/repair progress** | Có tiến độ và không báo failed tasks | Chậm, retries tăng | Stuck, failed ranges hoặc lỗi dữ liệu |
| **Node health** | Replica đủ CL, schema healthy | Một node trở nên chậm bất thường | Có nguy cơ mất quorum/khả năng phục vụ |
| **Data correctness** | Fixtures và invariants đúng | Kết quả chưa thể xác minh | Dữ liệu sai/thiếu hoặc rủi ro corruption |
| **Backup integrity** | Manifest/checksum đầy đủ | Copy chậm/partial | Integrity fail, không có recovery point hợp lệ |

### 18.1. Ví dụ ngưỡng định lượng của một service

Giả sử service **đã xác nhận trước test**:

~~~yaml
slo_example:
  read_p99_ms_max: 250
  logical_error_rate_max_percent: 1.0
  successful_rps_min: 900
maintenance_gates_example:
  warning_after_consecutive_windows: 2
  stop_after_consecutive_windows: 3
  window_minutes: 2
  disk_free_min_percent: 20
  no_failed_repair_ranges: true
  no_unverified_backup_chunks: true
  no_data_correctness_failures: true
~~~

Các giá trị **250 ms, 900 RPS, 20% disk free** là **minh họa của một hợp đồng thử nghiệm**, không phải defaults hay khuyến nghị chung. Disk headroom cần tính **dung lượng tuyệt đối**, estimated SSTable/backup growth và overhead compaction; một tỷ lệ phần trăm duy nhất có thể không đủ.

### 18.2. Phản ứng đúng khi stop gate bị kích hoạt

**Điều đầu tiên cần kiểm soát là nguồn tải thử nghiệm.** Có thể dừng phát request mới, giữ bằng chứng, giảm công việc nền theo cơ chế hỗ trợ, hoặc chuyển incident mode. Nhưng:

- **Không kill JVM Cassandra, hủy streaming/repair hoặc xóa snapshot bằng tay** chỉ vì p99 tăng, trừ khi runbook và owner đã cho phép.
- Các thao tác streaming/repair đang dở có thể để lại công việc tiếp tục/resume/cleanup cần quản lý. Dừng load generator không đồng nghĩa tác vụ nền cũng dừng.
- Nếu mất replica/quorum hoặc có khả năng sai dữ liệu, **ưu tiên bảo vệ data** hơn kết thúc benchmark.
- Nếu backup copy bị lỗi, không xóa recovery point đã có trước khi có bản thay thế được xác minh.
- Ghi rõ người đã quyết định, thời điểm, trạng thái cluster, tác vụ đang tiến hành, hành động tiếp và điều kiện resume.

### 18.3. Giao trách nhiệm GO/NO-GO

| Vai trò | Quyết định/chứng cứ |
|---|---|
| **Service owner/Java team** | SLO, business correctness, query mix, client metrics |
| **DBA/Cassandra owner** | RF/DC, topology, repair/streaming, schema, storage risk |
| **SRE/platform** | Capacity, network/disk, alerting, maintenance orchestration |
| **Backup/DR owner** | Backup integrity, remote copy, RPO/RTO, restore approval |
| **Change approver/incident commander** | GO/PAUSE/STOP và lịch tiếp tục trên production |

Một bài test có dashboard xanh nhưng không ai chịu trách nhiệm xác minh data correctness/restore không nên được coi là đã hoàn tất nghiệm thu.

## 19. Đọc số liệu và tính capacity: một ví dụ

Giả sử chạy **cùng offered load 1.000 logical requests/giây** trong ba pha. Dữ liệu hoàn toàn **giả định**:

| Chỉ số | Baseline C0 | Đang bootstrap B1 | Sau phục hồi C1 |
|---|---:|---:|---:|
| Offered logical RPS | 1.000 | 1.000 | 1.000 |
| Successful completed RPS | 995 | 940 | 995 |
| Failed completed RPS | 5 | 60 | 5 |
| p99 successful read latency | 140 ms | 390 ms | 155 ms |
| Client in-flight trung bình | 170 | 490 | 190 |
| Sender disk read | 110 MiB/s | 310 MiB/s | 120 MiB/s |
| Network outbound sender | 70 MiB/s | 160 MiB/s | 75 MiB/s |
| Pending compaction tasks | 3 | 25 | 4 |

**Đánh giá:**

1. Offered load không đổi, nhưng **success throughput giảm 55 RPS**.
2. Error rate tính trên các request hoàn tất tăng từ khoảng **0,5% lên 6%**.
3. p99 read tăng từ **140 ms lên 390 ms**, vượt SLO minh họa 250 ms ở mục 18.
4. In-flight và pending compactions tăng rõ, phù hợp với giả thuyết resource contention.
5. Sau phục hồi, p99 đã giảm về 155 ms; cần kiểm tra error rate, disk backlog và dữ liệu trước khi kết luận.
6. **Không quy nguyên nhân một cách tuyệt đối** chỉ vì các chỉ số cùng tăng: phải xem timeline, server logs, warm-up, retries, compactions có sẵn và load generator health.

Kết luận hợp lý là: **case B1 theo cấu hình này không đạt ngưỡng SLO đã giả định**, dù tác vụ bootstrap có thể hoàn thành thành công. Thử phương án giảm streaming pressure, đổi lịch, tăng capacity hoặc điều chỉnh điều kiện bảo trì trên staging rồi đo lại.

### 19.1. Ước lượng headroom không chỉ từ phần trăm CPU

Giả sử source disk đã dùng **350 MiB/s** ở baseline trên ổ có throughput thực phù hợp khoảng **500 MiB/s**. Streaming/backup dự định cần thêm **250 MiB/s** đọc cùng ổ:

~~~text
Nhu cầu tổng ước lượng = 350 + 250 = 600 MiB/s
Năng lực đo hiệu dụng ≈ 500 MiB/s

Nhu cầu vượt năng lực quan sát khoảng 100 MiB/s,
chưa kể seek/IOPS, write latency, compaction, queue.
~~~

Đây là phép tính **ước lượng sơ bộ**, không phải mô hình disk scheduling chính xác. Băng thông tuần tự 500 MiB/s không đồng nghĩa ổ xử lý tốt workload hỗn hợp random read/write cùng throughput. Phải đo disk latency/p99 I/O trên phần cứng thật.

### 19.2. Capacity cho snapshot và SSTable retention

Giả sử data directory đang dùng **700 GiB**, còn **300 GiB trống**, và chính sách giữ snapshot trong vài ngày. Không thể chỉ tính “snapshot là hard link nên dùng 0 byte”. Khi compaction tạo SSTables mới, các SSTable cũ vẫn được snapshot giữ lại, làm **không gian đã dùng** tăng. Cần:

- Dự đoán lượng dữ liệu ghi, tốc độ compaction và tốc độ retention.
- Theo dõi **disk usage thực**, snapshot pinned/retained bytes, chứ không chỉ kích thước tên file được liệt kê.
- Đặt ngưỡng cảnh báo trước disk full và kế hoạch copy/verify/cleanup.
- Kiểm tra nếu cùng lúc bootstrap/repair tạo thêm SSTables thì headroom còn đủ không.

Không lấy kích thước snapshot hiển thị rồi cộng toàn bộ một cách máy móc nếu hard links trỏ tới cùng inode; phải hiểu cách monitoring/accounting của filesystem để không double count hoặc đánh giá thấp space retention.

### 19.3. Số liệu throughput không thay điều kiện nhất quán

Nếu test A dùng LOCAL_ONE còn B dùng LOCAL_QUORUM, throughput A cao hơn chưa chứng minh phương án A tốt hơn cho ứng dụng cần strong consistency condition theo hợp đồng. Ghi rõ RF/DC, CL và retry policy trên từng phase, rồi so các trường hợp **cùng điều kiện nghiệm thu**.

## 20. Mẫu báo cáo kết quả phép đo

Đội dự án có thể lưu thông tin phép đo theo mẫu sau trong hệ thống báo cáo/changelog của mình:

~~~yaml
experiment:
  id: "load-lab-bootstrap-2026-11-example"
  operation: "bootstrap"
  environment: "staging-isolated"
  owner: "cassandra-platform"
  approved_change: "<change-reference>"
  started_at_utc: "<timestamp>"
  finished_at_utc: "<timestamp>"
versions:
  cassandra: "<exact-version>"
  java_driver: "<exact-version>"
  jdk: "<exact-version>"
topology:
  dc: "dc1"
  nodes_before: 3
  nodes_after: 4
  keyspace: "load_lab"
  replication_factor_in_dc1: 3
client_workload:
  offered_rps: 1000
  query_mix: "representative-read-write"
  partition_distribution: "normal-plus-known-hot-set"
  read_consistency: "LOCAL_QUORUM"
  write_consistency: "LOCAL_QUORUM"
  max_in_flight: 100
  request_timeout_ms: "<configured-and-verified>"
  retry_policy: "<policy-name-and-budget>"
baseline:
  success_rps: 995
  p99_read_ms: 140
  error_percent: 0.5
during_operation:
  success_rps_min: 940
  p99_read_ms_max: 390
  error_percent_max: 6.0
  streaming_bytes: "<observed>"
  peak_disk_read_mib_s: 310
  peak_network_out_mib_s: 160
  failed_stream_sessions: "<observed>"
after_operation:
  p99_read_ms: 155
  error_percent: 0.5
  recovery_minutes: "<measured>"
correctness:
  fixture_queries_passed: true
  missing_events: 0
  duplicate_logical_events: 0
  schema_and_topology_verified: true
decision:
  verdict: "NO-GO for this load/SLO profile"
  action: "test throttling or different maintenance window"
evidence:
  metrics_dashboard: "<link>"
  nodetool_logs: "<location>"
  generator_report: "<location>"
  change_log: "<location>"
~~~

Đây là **mẫu báo cáo minh họa**, không phải cấu hình để Cassandra chạy trực tiếp. Nếu một trường không được đo, ghi **NOT_MEASURED** thay vì invent số liệu. Đừng log tenant identifiers thật, raw payload, access token, object store secrets hoặc dữ liệu nhạy cảm vào artifact benchmark.

### 20.1. Những câu cần có trong phần kết luận

Báo cáo nên trả lời được, bằng dữ liệu:

- **Tác vụ có hoàn tất đúng phạm vi không?** Bootstrap token ranges/repair ranges/backup manifest có đạt không?
- **Trong lúc chạy, API có vi phạm SLO không?** Bao nhiêu phút, loại lỗi nào?
- **Bao lâu phục hồi sau khi tác vụ báo xong?**
- **Bottleneck chính có chứng cứ gì?** Disk, network, GC, coordinator, replica skew hay driver?
- **Độ tin cậy của kết luận?** Tác vụ nào chồng lấp, bao nhiêu lượt test, noise đã loại trừ gì?
- **Data correctness và khả năng restore được xác minh đến đâu?**
- **Khuyến nghị vận hành:** lịch, concurrency/throughput limit, capacity, stop gate, owner và test cần lặp.
## 21. Fault scenarios và phục hồi sau tác vụ

Đo tải trong điều kiện cluster khỏe chỉ là bước đầu. Chương **Đo tải và lỗi phân tán** cũng cần biết điều gì xảy ra khi thao tác nền không hoàn thành trọn vẹn. Những fault dưới đây chỉ được kích hoạt **trên cluster lab được phê duyệt**, có recovery path được kiểm chứng.

### 21.1. Node nguồn streaming trở nên không khả dụng

**Kịch bản:** trong bootstrap lab, một source node đang gửi SSTables bất ngờ ngừng phản hồi.

Điều phải quan sát:

- Bootstrap/streaming có **failed/retried sessions** hay còn tiến độ không?
- Replica placement và CL có còn đủ để ứng dụng phục vụ không?
- Java Driver có **Unavailable/ReadTimeout/WriteTimeout** và retry amplification không?
- Node tham gia có bị kẹt ở trạng thái chuyển tiếp?
- Có data correctness/repair/cleanup bước sau được runbook yêu cầu không?

**Không kết luận** “streaming failed là dữ liệu đã mất” hoặc “node Up thì mọi thứ an toàn”. Xác minh thông tin cụ thể từ topology, token coverage, server logs và prepared CQL; cho phép owner quyết định resume/replace/rollback theo quy trình của đúng phiên bản.

### 21.2. Repair validation xong nhưng streaming phần khác biệt thất bại

**Kịch bản:** repair chạy validation có tiến độ, sau đó một session đồng bộ SSTable lỗi mạng.

Đúng cách báo cáo:

~~~text
repair_status: PARTIAL / FAILED
validation_completed: <observed coverage>
streaming_failed: <failed ranges/sessions>
data_correctness: NOT_YET_VERIFIED
repair_complete: false
next_action: inspect logs; resume/fix-forward via approved runbook
~~~

**Không đánh dấu COMPLETE** chỉ vì validation đã chạy xong hoặc command return một phần status. Khi có lỗi, phải biết phạm vi repair đã hoàn tất, phạm vi chưa đồng bộ và bước khôi phục phù hợp version.

### 21.3. Backup storage từ chối upload khi snapshot đang giữ SSTables

**Kịch bản:** copy backup ra object storage bắt đầu, sau đó gặp access denied/quota/network timeout. Snapshot local vẫn tồn tại và disk đang giảm.

Cần:

1. **Phân loại lỗi remote storage**: auth/quota/network/checksum chứ không gộp vào Cassandra write timeout.
2. **Giữ recovery point cũ** đã được xác minh.
3. Kiểm tra manifest/chunks đã upload và cơ chế resume của backup tool.
4. Đánh giá snapshot pinned bytes và disk free; nếu sắp full, escalates theo chính sách retention/backup ownership.
5. Chỉ khi backup mới verified hoặc có quyết định DR được phê duyệt mới thực hiện cleanup snapshot.
6. Chạy restore drill trên cluster cô lập để kiểm chứng RPO/RTO.

Một bản backup **partially uploaded** không được coi là usable chỉ vì vài SSTables đã có ở remote storage.

### 21.4. Client timeout trong lúc backup và repair

Java service báo **WriteTimeout** khi disk bão hòa. Một số replica có thể đã áp dụng mutation. Nếu gateway retry với request ID mới, dữ liệu nghiệp vụ có thể trùng.

Phương án:

- Ghi **logical request ID** ổn định và kiểm soát idempotency.
- Giảm load/rate hoặc điều tiết maintenance theo runbook; không retry tức thì khi Overloaded.
- Không tự hạ LOCAL_QUORUM xuống LOCAL_ONE làm thay đổi cam kết consistency.
- Đối soát trạng thái CQL theo partition key khi outcome không rõ.
- Nếu dữ liệu/invariant đã sai, xử lý incident riêng; không coi việc hoàn thành repair/backup là đã sửa lỗi nghiệp vụ.

### 21.5. Tăng tải quá mức làm benchmark mất giá trị

Nếu hệ đang bão hòa, load generator vẫn tiếp tục tăng arrival rate để “tìm cực đại”, số successful RPS có thể giảm, error rate tăng, backlog và disk I/O kéo dài ngay cả sau khi dừng generator. Phép thử lúc đó có thể làm biến đổi trạng thái fixture/cache/SSTable quá nhiều để so với baseline trước đó.

Cần giữ **stop gate** và cho cluster hồi phục; muốn chạy lại phải xác minh baseline C0 mới, không nối tiếp dữ liệu từ một giai đoạn đang lỗi như thể môi trường không đổi.

## 22. Bài tập thực hành và đáp án gợi ý

### Bài 1 — Node Up nhưng API chậm

Sau bootstrap, **nodetool status** báo node mới UP/NORMAL. Tuy nhiên, p99 đọc vẫn gấp 2,5 lần baseline, pending compactions tăng và disk await cao.

**Câu hỏi:** Có thể báo bootstrap test PASS theo SLO không?

**Đáp án gợi ý:** Không, nếu SLO p99 đã bị vi phạm. Node UP chỉ cho biết một phần tình trạng cluster. Tiếp tục đo recovery window, compaction/disk và application latency; đánh giá GO/NO-GO theo tiêu chí đã chốt.

### Bài 2 — Tốc độ streaming và thời gian lý tưởng

Cần chuyển **120 GiB**. Tốc độ thực trung bình đạt **60 MiB/s** trong lúc không có lỗi. Ước lượng thời gian copy lý tưởng?

**Đáp án:** 120 × 1.024 / 60 = **2.048 giây**, khoảng **34,1 phút**. Chưa tính validation/retry/compaction/headroom và các giai đoạn không truyền dữ liệu.

### Bài 3 — So hai benchmark có CL khác nhau

Case A dùng **LOCAL_ONE** cho đọc; case B dùng **LOCAL_QUORUM**. Case A nhanh hơn 30%.

**Câu hỏi:** Có thể kết luận bootstrap ở A ít ảnh hưởng hơn không?

**Đáp án gợi ý:** Không so trực tiếp như cùng điều kiện. CL là một biến đã thay đổi, ảnh hưởng số phản hồi replica và latency. Chạy lại với cùng CL theo hợp đồng nghiệp vụ rồi so baseline/tác vụ.

### Bài 4 — Snapshot rất nhanh, disk free vẫn giảm

Snapshot được tạo trong vài giây nhưng một ngày sau disk free giảm mạnh trong khi không có tăng traffic đáng kể. Dashboard còn ghi nhiều compactions.

**Câu hỏi:** Điều gì có thể xảy ra?

**Đáp án gợi ý:** Snapshot giữ hard links đến SSTables; compaction tạo file mới trong khi file cũ còn bị snapshot pin, gây tăng disk usage. Kiểm tra listsnapshots, filesystem, backup copy/retention và cleanup đã phê duyệt. Không xóa recovery point chưa verified.

### Bài 5 — Repair và backup đồng thời

R1 chạy riêng có p99 = 180 ms; P2 riêng p99 = 170 ms; baseline p99 = 130 ms.

**Câu hỏi:** Có thể tính p99 X1 bằng 180 + 170 − 130 = 220 ms không?

**Đáp án gợi ý:** Không. Queueing, disk/network contention, retries và GC phi tuyến. Phải đo X1 trực tiếp trên staging sau khi R1/P2 riêng đạt headroom và có stop gate.

### Bài 6 — Client đạt 1.000 RPS được không?

Generator báo đã gửi 1.000 requests/s, nhưng chỉ có 780 requests/s thành công, 80 fail, 140 bị admission reject.

**Câu hỏi:** Throughput thành công là bao nhiêu?

**Đáp án:** **780 successful logical requests/s** (theo số liệu đã cho), không phải 1.000. Phải báo cả failed/rejected và hiểu lý do số được phát lớn hơn số phục vụ.

### Bài 7 — Backup upload thành công là đủ?

Job trả success sau khi copy 5 TB backup ra remote storage. Đội vận hành chưa lưu schema/manifest/checksum và chưa từng restore.

**Câu hỏi:** Có thể báo đạt RTO 1 giờ không?

**Đáp án gợi ý:** Không. Backup copy hoàn tất không chứng minh restore thành công trong 1 giờ. Cần manifest/checksum/keys, runbook và restore drill trên cluster cô lập để đo RPO/RTO.

### Bài 8 — Có nên repair toàn cluster để benchmark?

Cluster staging 10 TB, p99 đã sát SLO. Một người đề xuất chạy **full repair toàn cluster** ngay để xem hệ có chịu được không.

**Đáp án gợi ý:** Không nên bắt đầu khi chưa có headroom/risk assessment. Chọn phạm vi repair nhỏ hơn theo công cụ được hỗ trợ, có change owner, stop gates, metric và recovery path; không chạy full repair chỉ để thử.

### Bài 9 — Sau repair vẫn có ReadTimeout

Repair hoàn tất và các replica đang đồng bộ, nhưng app vẫn có ReadTimeout trên một tenant rất nóng.

**Câu hỏi:** Repair có sửa hot partition không?

**Đáp án gợi ý:** Không. Hot partition tập trung request trên các replica sở hữu token, dù dữ liệu giữa chúng đã hội tụ. Cần phân tích partition key/bucket/shard, row size, SSTables/tombstones, read latency và capacity.

### Bài 10 — Streaming network không đầy nhưng tốc độ thấp

NIC 10 Gbps chỉ sử dụng một phần nhỏ, song streaming rất chậm. Sender disk await và queue depth cao.

**Câu hỏi:** Nên tăng bandwidth limit để sửa?

**Đáp án gợi ý:** Chưa. Disk có thể là nút thắt, tăng network allowance không làm đĩa đọc nhanh hơn. Đo per-disk IOPS/latency, compaction và SSTable read, so với workload đang chạy.

### Bài 11 — Kết quả benchmark thiếu thời điểm

Một báo cáo chỉ có “read p99 trung bình cả ngày là 240 ms”, không đánh dấu lúc bootstrap bắt đầu/kết thúc.

**Câu hỏi:** Vì sao chưa đủ?

**Đáp án gợi ý:** Không phân biệt baseline, peak, post-maintenance recovery và các công việc nền khác. Cần timestamp event và metric theo cửa sổ thời gian, ghi rõ traffic/CL.

### Bài 12 — Open-loop và closed-loop

Test A có 100 workers gửi request tiếp sau khi request trước hoàn tất; khi Cassandra chậm, RPS tự giảm. Test B phát cố định 1.000 RPS.

**Câu hỏi:** Vì sao hai phép thử cho cảm nhận tải khác nhau?

**Đáp án gợi ý:** A là closed-loop, tự giảm offered rate khi latency tăng nên dễ che điểm bão hòa; B là open-loop, giữ arrival rate nên bộc lộ queue/rejection/error. Phải nói rõ mô hình và so đúng mục tiêu.

### Bài 13 — WriteTimeout khi đang copy backup

Java ghi event vào Cassandra trong khi backup đọc SSTables, sau đó WriteTimeout. Service tạo event_id mới để retry.

**Câu hỏi:** Có thể gây lỗi gì?

**Đáp án gợi ý:** Nếu mutation đầu đã được một số replica áp dụng, retry bằng ID mới tạo hai logical events. Dùng identity ổn định, idempotency contract và reconciliation; giảm pressure thay vì retry storm.

### Bài 14 — Repair partial vẫn báo complete

Một repair job có 95% ranges đã xác minh, 5% fail vì network. Tool báo “completed with errors” nhưng báo cáo nội bộ đánh dấu PASS.

**Câu hỏi:** Có hợp lệ không?

**Đáp án gợi ý:** Không. Phải báo **PARTIAL/FAILED**, liệt kê failed ranges và thực hiện kế hoạch xử lý theo runbook/version; không coi coverage 95% là hoàn tất 100% khi contract yêu cầu toàn phạm vi.

### Bài 15 — Tính tổng tải disk

Ổ đĩa đã đọc **350 MiB/s** ở baseline; streaming dự kiến thêm **250 MiB/s**, trong khi thông lượng ổ hiệu dụng khoảng **500 MiB/s** cho workload tương tự.

**Câu hỏi:** Rủi ro?

**Đáp án:** Nhu cầu sơ bộ **600 MiB/s**, vượt khoảng **100 MiB/s** so với năng lực quan sát; có thể làm queue/disk latency tăng và p99 xấu. Cần đo hỗn hợp random I/O thực và điều tiết task hoặc tăng headroom.

### Bài 16 — Giữ snapshot và bootstrap cùng lúc

Một node chỉ còn 15% disk free, có snapshot cũ pin SSTables và chuẩn bị nhận dữ liệu bootstrap.

**Câu hỏi:** Có nên GO?

**Đáp án gợi ý:** Chưa. Phải dự báo dung lượng nhận/compaction/snapshot retention, kiểm tra bản backup ngoài node đã verified, và theo runbook cleanup hoặc tăng capacity trước. Không xóa snapshot một cách vội vàng.

## 23. Checklist trước, trong và sau phép đo

### 23.1. Trước khi bắt đầu

- [ ] Chỉ thực hiện trên môi trường/khung bảo trì có **approval** và owner rõ.
- [ ] Ghi version Cassandra/JDK/Java Driver/operator và các giới hạn version-specific.
- [ ] Ghi DC/rack, số node, RF, CL, schema agreement, token distribution và trạng thái node.
- [ ] Preload dữ liệu tổng hợp đại diện, query shape theo partition key, payload size và key skew đã chốt.
- [ ] Đã xác định **open-loop hay closed-loop**, offered rate, max in-flight, deadline, retry budget.
- [ ] Không để load generator bão hòa CPU/disk/network trước Cassandra.
- [ ] Có baseline p50/p95/p99, successful throughput, error rate, GC/disk/network và compaction.
- [ ] Đủ disk headroom cho streaming nhận, compaction, snapshot retention và backup copy.
- [ ] Có backup/recovery point và kế hoạch restore/rollback nếu tác vụ có nguy cơ dữ liệu.
- [ ] Có stop gates/alerting và runbook quyết định THROTTLE/PAUSE/STOP.

### 23.2. Trong khi chạy

- [ ] Ghi start/end/phase timestamps cho bootstrap, stream, repair, snapshot, copy/upload.
- [ ] Giữ nguyên CL/query mix/rate để phép so sánh có ý nghĩa.
- [ ] Theo dõi **p99 cùng success RPS và lỗi**, không dùng một metric đơn độc.
- [ ] Theo dõi disk latency/queue/free, network, CPU/GC/native RSS và pending tasks.
- [ ] Theo dõi nodetool status/netstats/tpstats/compactionstats/tablestats đúng version.
- [ ] Ghi riêng repair coverage, failed sessions và streaming bytes/files.
- [ ] Phân biệt snapshot creation time với upload/copy, checksum và restore time.
- [ ] Không tự tăng retries hoặc hạ consistency để làm benchmark “xanh”.
- [ ] Nếu stop gate vượt, dừng nguồn tải và theo runbook; **không kill node hoặc xóa snapshot tùy tiện**.
- [ ] Có correlation/run ID nhưng không ghi secrets, raw partition keys nhạy cảm hoặc payload người dùng.

### 23.3. Sau khi hoàn tất

- [ ] Xác minh node health, topology/token placement, schema agreement và replica/CL phù hợp.
- [ ] Đối soát fixture qua prepared CQL, kiểm tra missing/duplicate logical events.
- [ ] Đối với repair, xác minh phạm vi ranges/failed sessions được xử lý.
- [ ] Đối với backup, xác minh remote manifest/checksum/keys và restore drill trên cluster cô lập.
- [ ] Theo dõi recovery window tới khi p99/error/throughput và compaction backlog ổn định.
- [ ] Ghi peak/average resource, elapsed time, recovery time, error budget consumed.
- [ ] Không xóa snapshot local trước approval; tuân thủ retention và capacity.
- [ ] So C0/B1/S1/R1/P1/P2/X1 bằng cùng điều kiện, không cộng p99 bằng số học.
- [ ] Ghi GO/NO-GO, bottleneck giả định có bằng chứng, test cần lặp và owner hành động.
- [ ] Lưu evidence có kiểm soát truy cập, không để báo cáo trôi mất khi kết thúc job.

## 24. Tổng kết

**Đo tải khi bootstrap, streaming, repair hoặc backup** không chỉ là đo số MiB/s mà các node truyền hoặc đọc đĩa. Trong Cassandra, các tác vụ nền cùng dùng **disk, network, CPU/GC, SSTables, compaction và thời gian replica phục vụ yêu cầu theo consistency level**. Một thao tác có thể báo hoàn tất trong khi API Java vẫn gặp p99 cao, timeout, error budget vượt ngưỡng hoặc backlog tiếp tục kéo dài.

Quy trình đáng tin cậy là **preflight → baseline representative workload → một tác vụ có kiểm soát → metrics theo timeline → xác minh dữ liệu → recovery window → GO/NO-GO**. Chỉ thử chồng lấp repair/backup/streaming sau khi đã hiểu từng tác vụ riêng và có stop gates rõ. Dùng **nodetool** cùng telemetry OS/JVM, nhưng luôn đối chiếu **successful throughput, end-to-end p99 và dữ liệu đúng** từ ứng dụng Java.

Cuối cùng, **replication không thay backup, repair không hoàn tác lỗi nghiệp vụ, snapshot local không phải bản sao ngoài miền lỗi, và tải nền hoàn tất không có nghĩa RPO/RTO đã được chứng minh**. Một bài benchmark đạt chất lượng phải cho biết hệ thống **phục vụ được bao nhiêu việc đúng, dưới tải và lỗi nào, trong bao lâu, với mức ảnh hưởng và rủi ro khôi phục ra sao**.



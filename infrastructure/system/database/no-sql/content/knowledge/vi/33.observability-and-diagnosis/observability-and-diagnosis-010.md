# Theo dõi tiến độ repair, rebalance, compaction hoặc tác vụ tương ứng

## 1. Tại sao tiến độ tác vụ nền là một phần của sức khỏe NoSQL?

Một cụm NoSQL vẫn có thể trả `GET` và `PUT` thành công trong khi một công việc nền quan trọng đang bị kẹt:

- Một replica đã mất liên lạc được **repair** nhưng chưa đồng bộ xong dữ liệu.
- Sau khi thêm node, dữ liệu đang **rebalance** sang các node mới.
- Một LSM storage engine có hàng nghìn **compaction tasks** đang chờ, làm tăng write amplification.
- Elasticsearch đang **relocate shards** nhưng một shard liên tục recovery thất bại.
- Một chỉ mục mới đang **backfill/index build**, còn API dựa vào nó chưa thể sử dụng đúng.
- Một hệ managed NoSQL đang **restore/import/split partition** mà ứng dụng chỉ quan sát được một phần tiến độ.

Nếu chỉ nhìn CPU, RAM hoặc HTTP 200, đội vận hành có thể không biết rằng mức dự phòng đã giảm, dung lượng trống đang cạn, read latency có thể tăng mạnh hoặc một thao tác bảo trì không bao giờ hoàn tất.

Bài học này trình bày cách **xác định công việc, theo dõi trạng thái, đo tiến độ thật, nhận diện đứng yên, đánh giá tác động tới người dùng và xử lý an toàn**. Trong NoSQL, repair, rebalance và compaction **không phải cùng một thao tác**; thuật ngữ cũng thay đổi theo từng sản phẩm. Vì vậy ta dùng một mô hình quan sát chung rồi đối chiếu từng hệ.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt repair, rebalance, compaction, rebuild, recovery, restore và index backfill.
2. Chọn metric phù hợp: tổng/đã xử lý, bytes, ranges, shards, pending tasks, rate, age, retries.
3. Giải thích vì sao `% progress` và ETA đôi khi không có ý nghĩa.
4. Theo dõi tác động bảo trì lên latency, throughput, disk, network, replication và dữ liệu.
5. Dựng dashboard/alert phản ánh **tiến triển và an toàn**, không chỉ một thanh phần trăm.
6. Áp dụng các công cụ quan sát của Cassandra, Elasticsearch, MongoDB, Redis và những hệ khác.
7. Thiết kế Java instrumentation, nhật ký tác vụ, runbook và bài kiểm thử phục hồi.

## 2. Ba khái niệm chính khác nhau ở mục đích

| Tác vụ | Mục tiêu | Thường xử lý | Ví dụ |
|---|---|---|---|
| **Repair** | Khôi phục tính nhất quán giữa bản sao hoặc sửa dữ liệu thiếu | Ranges, partitions, Merkle trees, replicas | Cassandra anti-entropy repair |
| **Rebalance** | Phân phối lại dữ liệu hoặc ownership khi topology/load thay đổi | Tokens, shards, vBuckets, slots, ranges | Elasticsearch shard relocation, Redis Cluster reshard |
| **Compaction** | Hợp nhất/tổ chức lại dữ liệu lưu trữ để giảm chi phí truy cập và xử lý xóa | SSTables, segments, tombstones, files | Cassandra/HBase/RocksDB LSM compaction |
| Recovery/initial sync | Dựng lại bản sao sau khi thêm/mất node | Snapshot, log replay, shard copy | MongoDB replica initial sync |
| Index build/backfill | Tạo chỉ mục từ dữ liệu đã có | Documents, index entries, partitions | MongoDB index build, DynamoDB GSI backfill |
| Restore/import | Nạp trạng thái từ backup/export | Chunks, objects, metadata | Managed database point-in-time restore |

### 2.1. “Repair” không có nghĩa database luôn bị hỏng

Ở các hệ dùng eventual consistency/anti-entropy, repair có thể là tác vụ định kỳ để đồng bộ bản sao, kể cả khi không có báo lỗi hỏng dữ liệu.

### 2.2. “Rebalance” không chỉ là copy bytes

Hệ có thể đổi metadata ownership, sao chép dữ liệu, catch up ghi mới, chuyển traffic rồi dọn bản cũ. Việc copy xong không đồng nghĩa mọi bước an toàn đã hoàn tất.

### 2.3. “Compaction” không phải backup

Compaction có thể thu gọn nhiều file và tombstones, nhưng **không thay thế backup, repair, replication hoặc kiểm chứng dữ liệu**. Nó còn tiêu thụ I/O và có thể cần thêm dung lượng đĩa tạm.

## 3. Mô hình vòng đời của một tác vụ nền

Một mô hình khái quát:

```text
PLANNED
   |
   v
QUEUED ------> WAITING_FOR_RESOURCE
   |                    |
   +--------------------+
   |
   v
RUNNING (phase 1 -> phase 2 -> phase 3)
   |   \
   |    +----> RETRYING / BACKOFF
   |                 |
   |                 v
   +-------------- RUNNING
   |
   +----> PAUSED / BLOCKED
   |                 |
   |                 v
   +-------------- RUNNING
   |
   +----> FAILED
   |
   +----> CANCELED
   |
   v
VERIFYING
   |
   v
SUCCEEDED
```

**Đây là state machine tham chiếu, không phải API trạng thái dùng chung cho mọi NoSQL.** Một hệ có thể không hỗ trợ pause; một task thất bại có thể tạo task mới; một compaction tự động có thể không có thời điểm hoàn tất của “toàn backlog”.

### 3.1. Đừng chỉ dùng `isRunning`

`isRunning=false` có thể có nghĩa:

- Công việc hoàn tất.
- Công việc chưa được lên lịch.
- Worker chết.
- Tác vụ bị lỗi/cancel.
- API quan sát bị mất kết nối.
- Một attempt kết thúc và attempt khác được tạo.

Cần **terminal status, reason, last update, expected work và verification**.

### 3.2. Tên và danh tính

Ghi `taskType`, `taskId`, `attemptId`, `clusterId`, `scope`, `owner`, `phase`, `startedAt`, `lastProgressAt`, `state`, `parentTaskId` nếu có.

### 3.3. Một công việc gồm nhiều subtasks

Rebalance một cluster có thể gồm hàng trăm shard moves. Một parent `REBALANCE` có thể RUNNING trong khi nhiều child SUCCEEDED và một child FAILED. Không đánh dấu parent thành công chỉ vì “tất cả child đang hoạt động đã xong”.

## 4. Phân biệt trạng thái, tiến độ và kết quả đúng

Một dashboard cần ba câu hỏi độc lập:

1. **Alive:** worker/coordinator còn heartbeat, task còn chạy?
2. **Progressing:** có công việc hữu ích được thực hiện và khối lượng còn lại có giảm?
3. **Correct:** trạng thái cuối đã thỏa điều kiện dữ liệu/topology/availability chưa?

Ví dụ:

```text
Repair task:
  status             RUNNING
  heartbeat age      2 s
  bytes transferred  80 GiB
  remaining ranges   không thay đổi 45 phút
  retries            tăng liên tục
```

Worker có thể còn sống, network đang bận, nhưng repair **không hội tụ**. Chỉ hiện “RUNNING/80 GiB” là chưa đủ.

### 4.1. Kiểm chứng sau hoàn tất

- Repair: các replicas/ranges được xử lý theo yêu cầu và job báo thành công; freshness/consistency health phù hợp.
- Rebalance: ownership/placement đạt mục tiêu, không có shard/slot/range kẹt, reads/writes vẫn đúng.
- Compaction: backlog về vùng ổn định, disk pressure và read/write latency giảm theo kỳ vọng.
- Index build: index usable, query plan/coverage và dữ liệu đúng.
- Restore: nguồn mục tiêu ở trạng thái mở phục vụ, dữ liệu/snapshot consistency được kiểm chứng.

**Thanh tiến độ 100% không thay nghiệm thu.**

## 5. Đơn vị tiến độ: số tác vụ, bytes, ranges hay partitions?

Một dashboard dễ sai vì cộng các đơn vị khác nhau:

| Tác vụ | Đơn vị thường hữu ích | Lưu ý |
|---|---|---|
| Repair | Token ranges, tables, sessions, repaired/unrepaired bytes, streamed bytes | Một range có thể chứa dữ liệu lớn hơn nhiều range khác |
| Rebalance | Shards/slots/vBuckets/ranges moved, bytes, owner assignment | 1 shard không tương đương 1 GiB |
| Compaction | Pending tasks, bytes input/output, SSTables/segments, compaction time | Tổng số tasks có thể thay đổi khi writes tiếp tục |
| Index build | Scanned docs, indexed records, phase, index state | Count dự kiến có thể không chính xác khi concurrent writes |
| Restore | Bytes/chunks/objects restored, replay lag, phase | Restore copy xong chưa chắc đã replay/log catch up |
| CDC catch-up | Source position, committed sink position, oldest event age | Offset giữa shards không là global percentage |

### 5.1. Cần công bố “đã làm được bao nhiêu của cái gì”

`processed=5_000` không rõ là 5.000 documents, 5.000 key ranges, 5.000 MiB hay 5.000 RPCs.

### 5.2. Mẫu số có thể mở rộng

Compaction là công việc liên tục được sinh bởi foreground writes; tổng pending tasks không cố định. Số “5/10 hoàn thành” có thể biến thành “6/14” dù hệ đang xử lý bình thường.

### 5.3. Đừng so thẳng metrics theo sản phẩm

`pending compactions=100` trong một engine không tương đương `100 relocating shards` ở search engine. Cần dùng SLO và mức backlog an toàn từng hệ.

## 6. Khi nào được dùng % hoàn thành?

Chỉ khi có denominator hợp lệ:

\[
\text{progress\%}=
\frac{\text{completed work units}}
{\text{total work units}} \times 100
\]

Điều kiện tối thiểu:

- Tập công việc đã xác định.
- Đơn vị công việc có ý nghĩa.
- Có cách đếm total đáng tin.
- Biết task split/merge/retry có làm thay denominator không.
- Cùng phase hoặc đã chuẩn hóa weight qua các phases.

### 6.1. Ví dụ có thể dùng

Restore một snapshot có tổng 200 files, 150 files copy thành công: 75% **theo số file**, không đồng nghĩa 75% **theo bytes**, và chưa gồm log replay.

### 6.2. Ví dụ không nên dùng

Cụm LSM tạo compaction liên tục, dashboard suy “80% complete” từ pending queue tại một thời điểm mà không biết tổng tasks tương lai.

### 6.3. Percentage có thể lùi

Nếu một shard relocation thất bại phải copy lại hoặc cluster add new shards, progress có thể quay từ 90% xuống 70%. Không ép số hiển thị luôn tăng bằng cách `max(previous, current)` rồi che việc làm lại.

### 6.4. Hiển thị thay thế

```text
Phase: STREAMING
Bytes copied: 240 GiB
Current rate: 75 MiB/s
Pending shards: 12
Oldest pending age: 18 min
Retries: 2
```

Đó có thể là thông tin hữu ích hơn một ETA giả.

## 7. ETA và tốc độ xử lý

Nếu tổng và tốc độ ổn định có thể ước lượng:

\[
\text{ETA}\approx
\frac{\text{work remaining}}{\text{effective processing rate}}
\]

Ví dụ:

```text
Remaining bytes: 120 GiB
Measured useful copy rate: 60 MiB/s
```

\[
\text{ETA}\approx\frac{120\times1024}{60}
=2048\ \text{s}\approx34{,}1\ \text{phút}
\]

Đây là ETA **riêng phase copy**, chưa gồm verify, catch-up, handoff hoặc cleanup.

### 7.1. Effective rate khác raw network rate

Network interface 200 MiB/s có thể gồm application traffic và retries. ETA cần **bytes hữu ích đã commit cho mục tiêu**, không lấy toàn NIC bandwidth.

### 7.2. Dùng cửa sổ tốc độ

Rate trong 5 phút gần nhất và 30 phút cho biết hệ có giảm tốc không. Đừng dùng instantaneous rate khi job vừa restart.

### 7.3. ETA chưa biết là câu trả lời đúng

Khi backlog sinh thêm, denominator không rõ, rate dao động hoặc task bị blocked, hiện `ETA: unknown` kèm lý do. Không hứa “còn 10 phút” dựa vào thanh tiến độ.

### 7.4. Giới hạn độ chính xác

Ngay cả khi tính được 34 phút, nên báo “khoảng 30–45 phút nếu tốc độ không đổi” nếu cần ước lượng, và nêu giả định. Không tạo cam kết thời gian từ mẫu đo vài giây.

## 8. Các tín hiệu một task có thể đã đứng yên

Không chỉ kiểm tra `status=RUNNING`. Xem đồng thời:

- `lastHeartbeatAt`: worker còn sống?
- `lastProgressAt`: lần gần nhất công việc hữu ích tăng?
- `bytesCompleted`/`workUnitsCompleted`: còn tăng?
- `remaining`/`backlog`: giảm, ổn định hay tăng?
- `retryCount`: có retry cùng một bước vô hạn?
- `phaseEnteredAt`: stuck trong phase?
- `errorCode`: lease, auth, disk, network, checksum, lock?
- `source/sink bandwidth`: làm việc thật hay chờ?
- `node CPU/disk/network`: bão hòa hay nhàn rỗi bất thường?
- `cluster state`: blocked vì mất quorum hoặc placement rules?
- `downstream lag`: tasks hoàn tất nhưng projection chưa bắt kịp?

### 8.1. Ngưỡng stalled phải theo phase

Một backup verify có thể không tăng `copiedBytes` nhưng vẫn đọc checksum. Một recovery đang chờ index build có thể không phát network traffic. Cần hiểu phase trước khi báo stall.

### 8.2. Idle không luôn là lỗi

Compaction queue bằng 0 thường là trạng thái tốt, không phải “compaction service chết”. Repair định kỳ ở trạng thái IDLE sau khi hoàn tất cũng bình thường nếu schedule phù hợp.

### 8.3. Không lấy một lần scrape làm kết luận

Metrics có thể bị delay; nên yêu cầu nhiều intervals hoặc cửa sổ đủ dài, kết hợp job logs.

## 9. Bốn tầng quan sát một maintenance task

```text
                       User impact
                  p95/p99, errors, SLO
                           |
                           v
                    Service capacity
            CPU / RAM / disk / network / queues
                           |
                           v
                       Task process
             state / phase / progress / retries
                           |
                           v
                    Data correctness
             coverage / ownership / replicas
```

### 9.1. Trạng thái task

Trả lời “đang làm bước nào, còn bao nhiêu và đã lỗi chưa?”.

### 9.2. Tài nguyên

Trả lời “job có tranh CPU, disk, network với traffic chính không?” và “còn headroom để hoàn tất không?”.

### 9.3. Mức độ phục vụ

Trả lời “API vẫn đạt SLO/availability không?”; bảo trì không nên gây outage ngoài kế hoạch.

### 9.4. An toàn dữ liệu

Trả lời “số replicas/ownership/consistency và khả năng khôi phục có phù hợp không?”. Một job có thể chạy nhanh nhưng tác động tiêu cực đến safety.

## 10. Repair: bản chất anti-entropy và phạm vi đo

Ở một số hệ phân tán như Cassandra, replicas có thể có sự khác biệt do network partition, node downtime hoặc writes chưa được đồng bộ. **Anti-entropy repair** so sánh và truyền dữ liệu để làm các bản sao hội tụ.

Quy trình khái quát:

```text
Coordinator
    |
    +--> Identify token ranges / replicas
    |
    +--> Compare data summaries / Merkle trees
    |
    +--> Detect differences
    |
    +--> Stream missing/divergent data
    |
    +--> Mark ranges/sessions completed
```

### 10.1. Phân biệt repair với read repair

- Background repair: công việc được lên lịch/chủ động chạy trên ranges.
- Read repair: một số hệ/phiên bản có thể sửa chênh lệch trên đường đọc theo semantics riêng.
- Hinted handoff: lưu và gửi lại một số writes bị lỡ; không thay định kỳ anti-entropy repair.
- Replication recovery/initial sync: dựng lại replica hoặc node khi tham gia cụm.

Không xem các cơ chế này là một.

### 10.2. Metric nên có

- Số repair sessions/ranges/table hoàn tất, thất bại, pending.
- Bytes read/hashed/compared/streamed.
- Time in validation vs streaming.
- Peer/replica unreachable.
- Retry count, timeout và checksum mismatches.
- Oldest unrepaired age hoặc lịch sử repair theo range.
- Network/disk utilization và API p99 trong repair.
- Ổ đĩa trống để stream/temporary files.
- Tombstone/repair frequency relative to deletion retention policy.

### 10.3. Repair “success” phải rõ coverage

Một lệnh repair chỉ một keyspace/table/range không chứng minh toàn cluster đã được repair. Cần biết **phạm vi được yêu cầu, đã xử lý và còn thiếu**.

## 11. Cassandra: công cụ quan sát cơ bản

Apache Cassandra có `nodetool`/JMX/metrics/diagnostic logs. Các ví dụ **đọc trạng thái**, dùng trên cluster và phiên bản tương thích:

```bash
nodetool status
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats
```

Ý nghĩa khái quát:

| Công cụ | Thông tin chính | Điều không tự chứng minh |
|---|---|---|
| `nodetool status` | Trạng thái node, datacenter, ownership/tokens theo version | Mọi replica đã được repair |
| `nodetool netstats` | Streaming sessions/progress và network transfer | Mọi repair subtask thành công |
| `nodetool compactionstats` | Các compactions hiện tại, pending/bytes tùy version | ETA toàn backlog chính xác |
| `nodetool tpstats` | Thread pools, pending/blocked tasks, dropped messages | Nguyên nhân duy nhất của mọi chậm trễ |
| `nodetool tablestats` | Metrics theo table/storage/read/write | Job repair đã cover đủ ranges |

**Lưu ý:** Câu lệnh/fields khác theo bản Cassandra và distribution. Chạy lệnh kiểm tra trên đúng môi trường, sử dụng xác thực và JMX access hợp lệ; đọc output/hướng dẫn phiên bản chứ không suy mọi field giống nhau.

### 11.1. Theo dõi job repair

Lưu lệnh đã chạy, keyspace/table, loại repair (full/incremental theo khả năng version), datacenter/hosts, start time, job identity/repair command output và log coordinator.

### 11.2. Quan sát streaming

`netstats` có thể cho thấy dữ liệu đi giữa các peers. Streaming byte count tăng không có nghĩa toàn job xong, vì còn validation, anti-compaction, finalization hoặc retries.

### 11.3. Incremental repair

Repair có thể dùng các cơ chế tracking/anti-compaction khác nhau theo version. Không lấy một statistic “repaired SSTables” làm bằng chứng mọi ranges đã khỏe nếu không hiểu metadata.

### 11.4. Không chạy `nodetool repair` chỉ để kiểm tra

`repair` là tác vụ **thay đổi trạng thái và tiêu tốn tài nguyên**, không phải read-only inspection command. Trước khi kích hoạt, cần kế hoạch, quyền hạn và kiểm soát ảnh hưởng.

## 12. Cassandra: một runbook khi repair có vẻ kẹt

Tình huống:

```text
repair session RUNNING 90 min
bytes transferred: 80 GiB
last useful progress: 40 min ago
network retries: increasing
API p99: 4x normal
```

Tiếp cận an toàn:

1. Kiểm tra repair job identity, phiên bản, keyspace/table/ranges và source/target replicas.
2. Đọc coordinator logs/diagnostic events để xác định phase đang chạy.
3. So dữ liệu của các lần `netstats`, `compactionstats`, `tpstats` theo thời gian, không nhìn một snapshot.
4. Kiểm tra disk free, disk latency, network errors, peer reachability và pending compactions.
5. Kiểm tra node đang bootstrap/decommission/move hoặc repair trùng phạm vi.
6. Đối chiếu p95/p99 foreground reads/writes với SLO.
7. Xác định nguyên nhân: blocked peer, rate-limited streaming, full disk, network, long validation, retry loop.
8. Tham khảo runbook/version support trước khi throttle, pause hoặc hủy job.
9. Nếu job failed, bảo đảm lịch repair/coverage tiếp theo không bỏ quên phạm vi.
10. Xác minh job result và data-health indicators sau xử lý.

### 12.1. Điều cần tránh

- Tự động restart repair liên tục mỗi khi thấy tiến độ không tăng trong 5 phút.
- Chạy nhiều full repairs đồng thời khiến disk/network bão hòa.
- Thay đổi `gc_grace_seconds` hoặc xóa tombstones tùy tiện để “giải quyết backlog”.
- Kết luận repaired chỉ vì job process đã biến mất.

## 13. Cassandra rebalance: bootstrap, token ownership và streaming

Khi thêm/bỏ/move node trong Cassandra, dữ liệu/ownership được tổ chức lại dựa trên token ranges và replica placement.

```text
Before:
  Node A owns ranges X,Y
  Node B owns ranges Z

After adding Node C:
  Some ownership moves to C
  Source nodes stream relevant data
  C catches up and becomes serving member
```

### 13.1. Không chỉ nhìn số node

Một node mới đã xuất hiện trong `nodetool status` không đảm bảo mọi streaming hoàn tất hoặc token ownership đạt phân bố kỳ vọng. Cần đọc trạng thái bootstrap và log.

### 13.2. Theo dõi source và destination

- Source streaming bytes, sessions.
- Destination received bytes và disk usage.
- Token/range ownership.
- Bootstrap/decommission phase và errors.
- Replica availability và consistency failure rates.
- API p99, throughput, dropped messages.
- Skew sau redistribution.

### 13.3. VNodes

Nhiều virtual nodes giúp chia ranges nhưng tạo số work units/stream sessions khác. Đếm số ranges moved mà không xét bytes/load có thể sai.

### 13.4. Data skew

Balance theo bytes không tự balance theo QPS. Một partition cực nóng có thể vẫn nghẽn dù disk usage đồng đều.

## 14. Cassandra compaction: backlog và I/O mới là trung tâm

Trong các LSM stores, write tạo memtable/SSTables, sau đó các compactions hợp nhất file, loại metadata không cần theo chính sách và giảm read amplification.

```text
Client writes
   |
   v
Memtable -> Flush -> SSTable L0/L1/...
                       |
                       v
                Compaction queue
                       |
                       v
                 Merge/Rewrite
```

### 14.1. Metrics cần theo dõi

- Pending compaction tasks theo table/node.
- Active compactions và phase.
- Input/output bytes, read/write throughput.
- SSTable count và size distribution.
- Compaction debt/backlog theo engine nếu có.
- Disk utilization và free space.
- Tombstone count/scan pressure.
- Flush queue, memory/memtable pressure.
- Foreground read/write p99 và dropped requests.
- Compaction errors/retries.

### 14.2. Không có “toàn bộ compaction hoàn thành” trong workload ghi liên tục

Foreground writes tạo thêm work. Một backlog tăng có thể phản ánh write ingress > compaction capacity, chứ không phải một job độc lập cứ bị đứng.

### 14.3. Compaction mạnh không phải luôn tốt

Tăng compaction concurrency có thể giảm backlog nhưng tranh disk/CPU với foreground traffic, làm p99 tệ hơn hoặc hết temporary disk space.

### 14.4. Tombstone safety

Tombstone cleanup phải tuân theo replication/repair/grace semantics của engine. Không ép compaction xóa dữ liệu đánh dấu xóa trước khi các replicas có cơ hội hội tụ.

## 15. Elasticsearch/OpenSearch: shard relocation và recovery

Elasticsearch/OpenSearch thường có các thao tác tương ứng:

- Shard allocation/reallocation/relocation.
- Primary/replica shard recovery.
- Snapshot restore.
- Segment merge và index maintenance.
- Reindex hoặc index creation.
- Cluster state updates và pending tasks.

Một số API quan sát **GET**, tùy sản phẩm/phiên bản:

```http
GET /_cluster/health
GET /_cat/shards?v
GET /_cat/recovery?v
GET /_cat/pending_tasks?v
GET /_nodes/stats/indices/merges
GET /_cluster/allocation/explain
```

`/_cluster/allocation/explain` có thể yêu cầu tham số tùy trường hợp; nhiều trường hợp dùng GET với body để hỏi cụ thể. Đừng suy lệnh này tự thay đổi placement.

### 15.1. Các giai đoạn recovery

```text
Shard assigned
      |
      v
File copy / peer recovery
      |
      v
Transaction log / sequence catch-up
      |
      v
Verification / finalization
      |
      v
Shard STARTED
```

Giai đoạn cụ thể phụ thuộc engine/version/mode. Đừng coi file recovery 100% đồng nghĩa shard đã nhận search traffic ở trạng thái STARTED.

### 15.2. Cluster health

- `green`: primaries và replicas được phân bổ theo quy tắc cluster.
- `yellow`: thông thường primary shards đã phân bổ nhưng có replica shards chưa phân bổ.
- `red`: có primary shards chưa được phân bổ.

Các nhãn không phải lời hứa tất cả truy vấn đều đúng/nhanh; ứng dụng có thể vẫn thấy latency xấu vì shard relocation hoặc merge pressure.

### 15.3. Theo dõi relocation

- Relocating/initializing/unassigned shard counts.
- Recovery stage, bytes/files recovered, source/target nodes.
- Recovery speed/ETA theo phase.
- Allocation failures/retries và allocation deciders.
- Disk watermarks/node storage utilization.
- Network và indexing/search p99.
- Cluster pending tasks và master/cluster-manager stability.

### 15.4. Cẩn trọng với merges/force-merge

Segment merging là hoạt động nền liên tục; **forcemerge** là thao tác có ảnh hưởng lớn, không chạy vì thấy `segments count` cao mà không có plan. Đo merge time, throttling, disk và index/search latency.

## 16. Elasticsearch: khi relocation không tiến triển

Một dashboard:

```text
Cluster health: yellow
Relocating shards: 2
Unassigned replicas: 1
Recovery bytes: no increase for 25 minutes
One node: disk 92%
Indexing p99: +120%
```

Cách đọc:

1. Xem shard nào và từ node nào sang node nào.
2. Kiểm tra allocation explain để biết vì sao replica chưa phân bổ.
3. Kiểm tra disk watermarks, network, node health, recovery throttling.
4. Xem recovery `stage` và bytes tăng theo cửa sổ.
5. Kiểm tra index merge/recovery pressure và foreground SLO.
6. Đánh giá còn bao nhiêu replica hữu ích và rủi ro khi thêm một node lỗi.
7. Cân nhắc capacity hoặc thao tác điều phối **theo runbook/version**, không tự thay các allocation settings khi thiếu thông tin.
8. Xác minh shard `STARTED` và cluster health sau khi xử lý.

### 16.1. Đừng tự động coi yellow là outage

Single-node cluster không thể đặt replica trên cùng node, nên có thể yellow dù primary phục vụ bình thường. Tuy nhiên yêu cầu HA có thể không được đáp ứng.

### 16.2. Đừng tự xóa index để giải phóng disk

Xóa index là thay đổi dữ liệu có thể không phục hồi được. Điều tra disk usage, snapshot/retention và data ownership trước mọi thao tác phá hủy.

## 17. MongoDB: chunk/range migration khác Cassandra repair

MongoDB sharded clusters có cơ chế phân phối lại **chunks/ranges** giữa shards. MongoDB replica sets có **replication, initial sync, rollback**; WiredTiger có checkpoints và storage housekeeping. Không gọi tất cả là “repair” theo nghĩa Cassandra anti-entropy.

### 17.1. Các mốc của migration

Một mô hình khái quát:

```text
Choose range/chunk to migrate
           |
           v
Copy data to destination
           |
           v
Catch up concurrent changes
           |
           v
Commit routing/ownership metadata
           |
           v
Range deletion/cleanup at source
```

Tên và chi tiết stages thay đổi theo MongoDB version.

### 17.2. Quan sát

- Balancer/range migration status.
- `sh.status()` hoặc thông tin balancer được hỗ trợ bởi mongosh/server version.
- `currentOp`/administrative operation diagnostics khi được phép.
- Shard distribution: bytes/chunks/collections, jumbo/hot ranges.
- Migration errors/retries, balancer pauses.
- Range deletion/cleanup backlog.
- Replication lag, primary election.
- API query latency/lock or resource contention.

Ví dụ **đọc trạng thái** trong mongosh theo phiên bản tương thích:

```javascript
sh.status()
db.currentOp()
```

Các lệnh có thể đòi quyền monitoring/admin; đầu ra có thể chứa metadata nhạy cảm. Không cho rằng `currentOp()` hiển thị mọi giai đoạn migration hoặc có field thống nhất giữa versions.

### 17.3. “Đã copy” khác “đã cleanup”

Source có thể còn giữ orphaned/range data một thời gian sau ownership transfer, theo cơ chế cleanup. Disk usage không nhất thiết giảm ngay khi migration hoàn tất.

### 17.4. Replica initial sync

Với replica set, quan sát initial sync progress và replication catch-up, không áp chỉ số “chunks moved” của balancer.

## 18. MongoDB: index builds và storage maintenance

Một tác vụ tương đương đáng theo dõi là **index build**:

- Collection size/records scanned.
- Build phase/status và operation log.
- Foreground write/read p99 trong lúc build.
- Disk/I/O/index storage.
- Thời gian scan/build/commit.
- Khả năng index được sử dụng sau khi hoàn tất.
- Build failure, restarts và replica coordination.

### 18.1. Không tự suy 100% scanned = index usable

Một số hệ cần drain side writes, validate hoặc commit metadata trước khi planner sử dụng index.

### 18.2. WiredTiger không phải LSM compaction

MongoDB WiredTiger có checkpoints, cache eviction và storage maintenance theo engine. Không ép nó vào cùng biểu đồ pending SSTable compactions như Cassandra.

### 18.3. Rebuild/compact là thao tác có chi phí

Không tự chạy database `compact` chỉ vì thấy file lớn; các lệnh maintenance có constraints, locking/resource cost và hiệu quả phụ thuộc engine/version.

### 18.4. Replica lag

Sau index build hoặc sync, replica có thể trễ. Với read preference dùng secondaries, đọc stale và failover risk có thể là triệu chứng quan trọng hơn phần trăm tiến độ.

## 19. Redis Cluster: resharding, slot migration và persistence tasks

Redis Cluster phân chia keyspace logic thành **16.384 hash slots**. Resharding chuyển quyền phục vụ slots và keys giữa nodes.

```text
Source node
  hash slots 1000..1200
       |
       | MIGRATING / key transfer
       v
Destination node
  IMPORTING / receiving keys
       |
       v
Slot ownership switched
```

### 19.1. Các lệnh quan sát (không thay topology)

```text
CLUSTER INFO
CLUSTER NODES
CLUSTER SLOTS
INFO stats
INFO persistence
INFO replication
```

`CLUSTER SHARDS` có trên những versions phù hợp. Phân biệt các lệnh **đọc** này với `CLUSTER SETSLOT`, `MIGRATE`, `redis-cli --cluster reshard`, là hành động thay đổi topology.

### 19.2. Cần theo dõi

- Hash slots đã chuyển quyền, đang migrating/importing, còn lại.
- Keys/bytes thực sự phải migrate.
- Source/destination memory, fragmentation, network.
- `MOVED`/`ASK` redirects và client retry.
- `cluster_state`/cluster slots coverage.
- Replication lag/health và failover.
- Redis command latency, CPU và evictions.

### 19.3. Một slot không cùng kích thước với slot khác

“8.000/16.384 slots đã cân bằng” không đồng nghĩa 50% bytes hoặc 50% traffic đã cân bằng. Một hot key vẫn có thể gây hotspot.

### 19.4. Persistence là tác vụ khác

RDB snapshot, AOF rewrite và loading/catch-up có progress/flags riêng; `INFO persistence` có thể cung cấp các fields như `rdb_bgsave_in_progress`, `aof_rewrite_in_progress` tùy version/config. Đây **không** là rebalance progress.

## 20. Couchbase: rebalance và vBucket ownership

Couchbase có khái niệm **rebalance**, vBuckets và service-specific resource movement. Một rebalance có thể phải di chuyển active/replica vBuckets, điều phối DCP và index/query services.

Theo dõi:

- Rebalance task state và từng phase.
- vBuckets planned/moved/remaining.
- Bytes moved và transfer rate.
- Node/service capacity và disk utilization.
- Index build/rebalance backlog.
- DCP replication lag.
- Bucket readiness, active/replica placement.
- KV latency, failover/availability và query p99.

### 20.1. UI/API progress là một nguồn, không phải toàn bộ

Couchbase Console/REST/API có thể hiển thị task progress, nhưng một progress percentage chưa nói traffic có bị throttled hay vẫn mất replica placement.

### 20.2. Rebalance bị retry

Một node vừa rời cụm hoặc index service không đủ disk có thể làm nhiệm vụ tạm dừng. Lưu failed reason, attempt count và scope bị ảnh hưởng.

### 20.3. Không coi vBucket moved = đủ capacity

Skew theo key popularity và index workload có thể vẫn gây hotspot.

## 21. HBase: region movement, splits và compaction

Apache HBase có:

- Region assignment/movement và balancing.
- Region splits, làm tăng số regions.
- MemStore flush.
- Minor/major compaction.
- WAL replication và recovered edits.

Sơ đồ:

```text
HBase RegionServer
   |
   +--> Regions / StoreFiles
   |         |
   |       flush
   |         |
   |         v
   |      compaction queue
   |
   +--> region assignment / balance
```

### 21.1. Những metrics

- Regions assigned/unassigned/RIT (regions in transition).
- Balancer work và region count/size skew.
- Compaction queue length, compaction progress.
- StoreFile count, read/write amplification.
- WAL replication lag.
- RegionServer CPU/memory/GC/disk.
- Client RPC p95/p99 và blocked calls.

### 21.2. Minor/major compaction

Công việc hợp nhất StoreFiles khác với region split/assign. Không dùng một counter duy nhất cho cả hai.

### 21.3. HBase Shell

Các lệnh xem trạng thái như `status` và tooling/JMX tương thích phiên bản có thể hỗ trợ quan sát. Đừng chạy `balance_switch`, manual `major_compact` hay region move như lệnh “kiểm tra”.

## 22. DynamoDB: tác vụ được quản lý thay vì manual repair

Amazon DynamoDB managed service không cung cấp một tác vụ `nodetool repair` hoặc `LSM compaction queue` cho khách hàng quản lý theo kiểu Cassandra.

Những việc tương ứng có thể quan sát:

- GSI create/backfill state.
- Table creation/restore/import status.
- Capacity scaling/partition throttling.
- Global tables replication health/latency theo mode.
- TTL/Streams consumer lag.
- PITR/export/backup operations.

### 22.1. GSI

`DescribeTable` trong AWS API có thể cung cấp `IndexStatus` và `Backfilling` cho GSIs theo điều kiện. **Không suy luôn có phần trăm backfill chính xác**.

### 22.2. Metric bên ngoài

CloudWatch metrics như consumed capacity, read/write throttles và latency service/client có thể giúp đánh giá ảnh hưởng lên foreground workload. Tên metrics và support theo operation/capacity mode cần tra tài liệu version hiện hành khi triển khai.

### 22.3. Đọc trạng thái vs can thiệp

Các request kiểu Describe thường dùng để quan sát; update provisioned throughput, delete/rebuild index hoặc restore là hành động có chi phí/rủi ro riêng, không tự động làm khi dashboard thấy tiến độ chậm.

### 22.4. Khi không expose backend progress

Ghi rõ **“service-managed, không có percentage nội bộ được công bố”** và theo dõi API trạng thái cùng latency/throttling. Không tự suy percent từ số giờ đã trôi qua.

## 23. Azure Cosmos DB for NoSQL: partition split và change feed

Cosmos DB là managed NoSQL service; nhiều công việc nền nằm bên trong dịch vụ:

- Physical partition split.
- Autoscale/throughput changes.
- Index transformations theo API/mode.
- Restore/backup operations.
- Change Feed Processor leases/checkpoints.
- Cross-region replication.

### 23.1. Những gì ứng dụng có thể theo dõi

- Normalized RU consumption và 429 throttling.
- Request latency p95/p99.
- Partition-key hot spots.
- Storage size/quota theo metric được cung cấp.
- Change Feed lag, feed-range ownership/leases.
- Query/index freshness theo yêu cầu.
- Restore/import operation status, nếu API expose.

### 23.2. Không nhầm 429 với repair failed

Một spike 429 có thể do request charge/capacity nóng, không có nghĩa partition split bị lỗi. Cần correlating service metrics với topology/capacity changes.

### 23.3. Feed processor rebalance

Khi nhiều workers cùng xử lý change feed, leases được chuyển ownership; quan sát số feed ranges assigned, last processed watermark và retry. Đây là **consumer workload rebalance**, không phải physical partition repair.

### 23.4. Service-managed progress

Nếu platform không expose task percent, không vẽ một thanh tiến độ ước lượng rồi trình bày như metric chính thức.

## 24. Firestore và Neo4j: tác vụ tương ứng

### 24.1. Firestore

Những tác vụ có thể quan sát gồm:

- Index creation/backfill qua long-running operations hoặc trang index status.
- Export/import operations.
- Backup/restore theo dịch vụ và phiên bản.
- Query errors khi index thiếu/chưa usable.
- Document read/write latency và quota/limits.

Đây không phải hệ cung cấp manual SSTable compaction/replica anti-entropy cho application operators.

### 24.2. Neo4j

Neo4j có thể cung cấp:

- Index population trạng thái `POPULATING`/`ONLINE` hoặc trạng thái khác theo version.
- Store copy/replica catch-up/cluster topology.
- Backup/restore và recovery phases.
- Page cache, checkpoint, transaction log metrics.
- Query execution latency, pending transactions.

Ví dụ Cypher xem index metadata, khi phiên bản hỗ trợ:

```cypher
SHOW INDEXES
```

Không tự giả định mọi edition có một global `repairPercent` hoặc các trường index giống mọi release.

### 24.3. Bài học chung

Tên “maintenance progress” cần map sang tác vụ **sản phẩm thực sự expose**, thay vì cố ép tất cả NoSQL lên một `repair/rebalance/compaction` enum không phản ánh thực tế.

## 25. Bảng đối chiếu các hệ NoSQL

| Hệ | Repair hoặc tương đương | Rebalance hoặc tương đương | Compaction hoặc tương đương |
|---|---|---|---|
| Cassandra | Anti-entropy repair, range/replica coverage | Bootstrap/decommission/token streaming | SSTable compaction, pending tasks |
| Elasticsearch/OpenSearch | Shard recovery/replica sync, snapshot restore | Shard allocation/relocation | Lucene segment merges |
| MongoDB | Replica initial sync/recovery, integrity operations theo version | Chunk/range migration qua sharding balancer | WiredTiger housekeeping/checkpoints; không LSM compaction kiểu Cassandra |
| Redis Cluster | Replica resync/persistence recovery | Hash-slot and key migration | AOF rewrite, memory defrag; không SSTable compaction |
| Couchbase | Replica/recovery/DCP catch-up | vBucket rebalance | Storage-engine-specific compaction |
| HBase | Region recovery/WAL replay | Region balancing/movement | HFile major/minor compaction |
| DynamoDB | Service-managed durability/replication | Service-managed partition placement; GSI backfill | Không expose manual compaction |
| Cosmos DB | Service-managed recovery/replication | Physical splits/throughput; feed lease balancing | Index/storage maintenance managed |
| Firestore | Managed recovery/restore | Managed partitioning, index building | Không expose manual LSM compaction |
| Neo4j | Store copy/cluster catch-up/recovery | Cluster topology / member roles | Storage/index/checkpoint maintenance theo engine |

Đây là so sánh **khái niệm**, không khẳng định các hệ hỗ trợ cùng công cụ, kiểm soát hoặc bảo đảm.

## 26. Mô hình metric chung cho task tiến độ

Một event/record trạng thái do hệ quan sát tổng hợp:

```json
{
  "cluster": "orders-prod",
  "taskType": "SHARD_RELOCATION",
  "taskId": "opaque-task-123",
  "attempt": 2,
  "scope": {
    "sourceNode": "node-a",
    "targetNode": "node-b",
    "shard": "orders-3"
  },
  "state": "RUNNING",
  "phase": "FILE_COPY",
  "startedAt": "2026-11-14T10:00:00Z",
  "lastProgressAt": "2026-11-14T10:12:00Z",
  "completedBytes": 21474836480,
  "totalBytesEstimate": 32212254720,
  "retries": 1,
  "errorCode": null
}
```

**Đây là schema minh họa**, không là payload native của Elasticsearch. Một backend managed có thể không cung cấp `totalBytesEstimate` hoặc `lastProgressAt`.

### 26.1. Fields bắt buộc và tùy chọn

Bắt buộc để vận hành một job có ID: identity/scope/state/observedAt. Phần progress như `completedBytes`/`totalBytes` chỉ ghi nếu có nguồn đáng tin.

### 26.2. Cách dùng percent

Nếu `totalBytesEstimate` là estimate có thể thay, percent phải chú thích **estimated** và có thể thay đổi theo thời gian.

### 26.3. Không log payload người dùng

Metrics/operations logs nên chứa IDs/hashes/size/counts, không đưa raw documents hoặc PII vào hệ monitoring.

## 27. Metrics dạng counter, gauge và histogram

| Kiểu metric | Ví dụ | Cách đọc |
|---|---|---|
| Counter | `maintenance_processed_bytes_total` | Tổng hữu ích đã xử lý từ khi reset/instance start |
| Counter | `maintenance_attempts_total` | Tổng attempts/retries theo type/reason |
| Gauge | `maintenance_active_tasks` | Số tác vụ đang chạy tại thời điểm scrape |
| Gauge | `maintenance_pending_tasks` | Số công việc chờ |
| Gauge | `maintenance_oldest_pending_seconds` | Tuổi backlog lớn nhất |
| Gauge | `maintenance_disk_free_bytes` | Headroom dung lượng |
| Histogram | `maintenance_phase_duration_seconds` | Phân phối thời gian mỗi phase |
| Histogram | `nosql_foreground_request_seconds` | Tác động tới latency người dùng |

### 27.1. Counter resets

Khi process restart, counter có thể về 0. Với Prometheus-style queries, dùng `rate`/`increase` có xử lý reset thay vì lấy hiệu hai số thô và báo tốc độ âm.

### 27.2. Gauge có thể tăng hoặc giảm

Backlog không phải “công việc đã xong”. Nó có thể tăng do writes liên tục, split tasks hoặc retries.

### 27.3. Long-running task không nên chỉ đo completed duration

Nếu chỉ ghi Timer sau khi job kết thúc, một job kẹt 8 giờ sẽ **không** tạo duration observation mới trong suốt thời gian kẹt. Cần gauges/long-task timer/last-progress age.

### 27.4. Phân biệt `taskId` và metric label

`taskId` có cardinality cao. Giữ taskId trong logs/traces hoặc một task metadata store; metrics thường dùng labels hữu hạn như `taskType`, `phase`, `cluster`, `result`, `reasonClass`.

## 28. Aggregate tiến độ nhiều subtasks không được lấy trung bình phần trăm

Giả sử:

```text
Shard A: 90% của 100 GiB
Shard B: 10% của 1 GiB
```

Trung bình % bằng `(90+10)/2=50%`, nhưng theo bytes:

\[
\frac{0.9\times100+0.1\times1}{100+1}
=\frac{90.1}{101}\approx89.2\%
\]

### 28.1. Dùng trọng số thích hợp

Nếu đơn vị là bytes, dùng tổng completedBytes / totalBytes; nếu completion cần verify every shard, báo thêm số shards `SUCCEEDED / TOTAL`.

### 28.2. Bảo vệ khỏi duplicate counting

Một shard bị retry từ đầu không được cộng lại bytes cũ vào `uniqueCompletedBytes` mà không giải thích. Tách `bytesTransferredTotal` và `uniqueBytesVerified`.

### 28.3. Multi-phase weights

File copy 100% nhưng transaction-log catch-up mới 0% không thể gọi “job 100%”. Nếu phase weights không có dữ liệu, hãy báo trạng thái từng phase, không tự bịa trọng số 70/20/10.

### 28.4. Parent/child lineage

Khi child shard split hoặc move lại, task graph có thể đổi. Tổng child count biến động; lưu lineage/retries để giải thích thay đổi.

## 29. Nhận biết tốc độ và backlog tăng/giảm

Ví dụ:

```text
Pending work at T0 = 2,000 units
New work arriving  = 300 units/min
Work completed     = 400 units/min
```

Tốc độ giảm backlog theo mô hình đơn giản:

\[
\frac{dB}{dt}\approx 300-400=-100\ \text{units/min}
\]

Nếu cùng rate giữ nguyên, backlog khoảng 20 phút để về 0. Nhưng nếu arrival tăng, rate giảm hoặc tasks được split, ETA thay đổi.

### 29.1. Thông lượng hữu ích

Đo `completedSuccessBytes/s` hoặc verified ranges/s, không chỉ `attemptedBytes/s`.

### 29.2. Tỷ lệ retry

Nếu processed 1 TiB nhưng transferred 4 TiB do retries, raw bandwidth lớn không phản ánh hội tụ.

### 29.3. Work backlog và age

Cùng pending=100, một hệ có oldest pending 20 giây khác hệ có oldest pending 3 ngày. Đo cả size lẫn **oldest age**.

### 29.4. Đừng gộp các units

`30 tasks pending` và `200 GiB pending` là hai trục; dùng cả hai khi task sizes lệch lớn.

## 30. Maintenance SLO và độ an toàn

Một SLO vận hành ví dụ:

```text
Repair:
  100% required ranges completed within maintenance window
  No range remains unrepaired beyond agreed coverage age

Rebalance:
  Target placement reached before deploy window closes
  No primary/required replica remains unassigned beyond threshold

Compaction:
  Pending debt remains bounded under steady-state writes
  Foreground API p99 stays within SLO

Index build:
  Index ONLINE within rollout window
  No incorrect query result or unsafe cutover
```

Đây là các **mẫu yêu cầu** để team điền giá trị, không phải SLO mặc định của từng hệ.

### 30.1. SLO bảo trì khác SLO người dùng

Job có thể hoàn thành đúng giờ nhưng API error rate tăng không chấp nhận được. Cần cả task SLO và foreground SLO.

### 30.2. Safety margin

Không nên dùng toàn bộ CPU/disk/network để làm bảo trì khi dịch vụ còn phục vụ traffic. Mức headroom phụ thuộc topology, peak load và failover budget.

### 30.3. Mục tiêu “mọi backlog bằng 0” có thể không thực tế

Compaction trên hệ ghi liên tục luôn phát sinh việc mới. Định nghĩa **bounded backlog/age và steady-state drain capacity**, không bắt queue luôn trống.
+## 31. Dashboard tối thiểu cho một cụm NoSQL

Một dashboard nên cho người trực ca trả lời theo thứ tự:

1. Có tác vụ nào đang hoạt động hoặc thất bại?
2. Tác vụ quan trọng nhất đang ở phase nào?
3. Nó có **tiến triển hữu ích** không?
4. Còn bao nhiêu công việc và đã trễ bao lâu?
5. Dịch vụ foreground đang bị tác động thế nào?
6. Có rủi ro về dữ liệu, quorum hoặc dung lượng không?
7. Cần hành động, tiếp tục theo dõi hay chờ đến ngưỡng đánh giá tiếp theo?

Một bố cục gợi ý:

```text
+----------------------------------------------------------+
| Cluster health: DEGRADED  | API p99: 210ms | Error: 0.4% |
+---------------------------+------------------------------+
| Repair active: 2          | Rebalance pending: 7 shards  |
| Compaction pending: 155   | Disk free min: 18%           |
+---------------------------+------------------------------+
| Job table: Task / Phase / Last progress / Retry / Owner   |
+----------------------------------------------------------+
| Useful bytes/s       | Pending work trend | Oldest age    |
+----------------------------------------------------------+
| Node CPU/IO/Network  | Replica health     | Hot partitions|
+----------------------------------------------------------+
| Logs / events / maintenance timeline / runbook links      |
+----------------------------------------------------------+
```

### 31.1. Khi nào có thanh phần trăm?

Chỉ cho task có `total` đáng tin. Cạnh thanh phần trăm ghi rõ **theo bytes, files, ranges hay jobs**, cùng thời điểm dữ liệu được cập nhật.

### 31.2. Không dùng một đèn “healthy” tổng hợp để che lỗi

Một cluster có search traffic tốt nhưng một replica rebuild thất bại vẫn phải hiện sự cố redundancy. “Service đang phục vụ” khác “cluster đã khôi phục đúng mức dự phòng”.

### 31.3. Dashboard phải có lịch sử

Biểu đồ một phút hiện tại không cho biết backlog đã tăng liên tục sáu giờ. Cần đường xu hướng qua các khoảng 5 phút, 1 giờ, 24 giờ hoặc thời gian phù hợp với maintenance window.

## 32. Prometheus-style queries: ví dụ khái niệm

Giả sử exporter của bạn công bố các metrics:

```text
nosql_maintenance_processed_bytes_total
nosql_maintenance_pending_tasks
nosql_maintenance_active_tasks
nosql_maintenance_last_progress_timestamp_seconds
nosql_maintenance_retry_total
nosql_maintenance_oldest_pending_seconds
```

**Tên ở đây là convention ví dụ do đội phát triển định nghĩa**, không phải tên metric mặc định chung cho Cassandra, Elasticsearch hoặc AWS.

### 32.1. Tốc độ xử lý bytes

```promql
sum by (cluster, task_type) (
  rate(nosql_maintenance_processed_bytes_total[5m])
)
```

Cần counter đếm bytes hữu ích và xử lý reset khi process restart. Nếu nguồn chỉ trả bytes copied của task hiện tại (gauge reset theo phase), không nên đưa trực tiếp vào `rate` như counter monotonic.

### 32.2. Backlog

```promql
sum by (cluster, task_type) (
  nosql_maintenance_pending_tasks
)
```

Nếu cùng task bị báo từ nhiều exporters, `sum` có thể đếm trùng. Thiết kế quyền sở hữu metric/labels trước khi tổng hợp.

### 32.3. Tuổi backlog lớn nhất

```promql
max by (cluster, task_type) (
  nosql_maintenance_oldest_pending_seconds
)
```

Metric này chỉ có ý nghĩa nếu exporter thực sự biết timestamp task được enqueue, không phải lấy từ process start time.

### 32.4. Thời gian không có tiến độ

```promql
time() - nosql_maintenance_last_progress_timestamp_seconds
```

Chỉ cảnh báo khi task được kỳ vọng tiến triển ở phase tương ứng. Với task chưa từng có progress hoặc không active, `last_progress` có thể thiếu/zero; cần rule xử lý trường hợp đó.

### 32.5. Đừng nhầm scrape failure thành zero backlog

Nếu exporter down, metric có thể mất khỏi query thay vì về zero. Có alert riêng cho exporter/target `up`, data freshness và missing series.

## 33. Thiết kế cảnh báo theo kết hợp điều kiện

Một cảnh báo “active repair > 0” sẽ spam trong khi repair định kỳ bình thường.

Các quy tắc có ý nghĩa hơn:

| Tên cảnh báo | Điều kiện định hướng | Mức độ |
|---|---|---|
| RepairStalled | RUNNING và last useful progress quá lâu trong phase cần tiến triển | Warning/Critical theo coverage |
| RepairFailed | Terminal FAILED + phạm vi chưa được repair | Critical nếu ảnh hưởng safety |
| RebalanceStalled | Ownership chưa đạt, retry/age vượt ngưỡng | Warning/Critical |
| ShardUnassigned | Required primary/replica chưa phân bổ | Theo impact availability/redundancy |
| CompactionDebtGrowing | Pending/debt tăng sustained, drain capacity không đủ | Warning |
| DiskHeadroomLow | Free disk dưới margin khi job còn cần temporary space | Critical |
| MaintenanceHurtingSLO | p99/error foreground vượt ngưỡng cùng thời gian job chạy | Critical |
| RetentionRisk | CDC/repair backlog age sắp vượt safe window | Critical |
| TaskTelemetryMissing | Job active nhưng không có trạng thái mới | Warning/Critical |

### 33.1. Có thời gian `for` hợp lý

Một phase có vài phút không cập nhật bytes có thể bình thường. Không đặt 30 giây cho mọi maintenance jobs. Ngưỡng phải dựa vào loại task, cluster size và lịch sử thực tế.

### 33.2. Multi-signal giúp giảm false positives

Một alert mạnh hơn có thể kết hợp:

```text
Repair RUNNING
AND last progress > threshold
AND pending work > 0
AND peer unreachable OR retries rising
```

Không áp điều kiện quá chặt khiến bỏ sót job stuck do deadlock mà CPU thấp/không có retries.

### 33.3. Alert theo rủi ro, không chỉ thời gian

Repair chậm nhưng còn đủ redundancy và tiến triển đều có mức ưu tiên khác repair chậm ngay trước khi repair window/tombstone safety deadline hết hạn.

### 33.4. Có alert về hành động thất bại

Một task FAILED cần người sở hữu và hướng xử lý; không nên chỉ biến mất khỏi bảng active tasks.

## 34. Runbook mẫu: từ alert tới hành động

Một runbook chung:

```text
Alert fired
    |
    v
Verify monitoring freshness
    |
    v
Identify task type, phase, scope, owner
    |
    v
Check source+target progress and data safety
    |
    v
Check user SLO and infrastructure headroom
    |
    +--> Progressing; safety OK
    |         |
    |         v
    |     Continue observe + next check time
    |
    +--> Blocked or failed
              |
              v
       Classify root cause
              |
              +--> capacity
              +--> network/peer
              +--> authorization/config
              +--> data/index integrity
              +--> expected wait/coordination
              |
              v
         Approved intervention
              |
              v
         Verify task + business SLO
              |
              v
         Record incident / follow-up
```

### 34.1. Bước 1: xác minh nguồn quan sát

Exporter có bị restart không? Metrics timestamp còn mới không? Control plane trả trạng thái khác data plane không? Alert do stale scrape hay công việc thật?

### 34.2. Bước 2: định danh

Ghi `taskId`, cluster, owner, phiên bản, keyspace/index/bucket, source/target node, phase và attempt number. Không trộn log của run cũ với run hiện tại.

### 34.3. Bước 3: đánh giá dữ liệu

Đang mất replicas chưa? Có unassigned primary không? Có missing token range không? Có retention window sắp hết? Cần ưu tiên safety hơn tốc độ.

### 34.4. Bước 4: đánh giá tác động người dùng

API p99, error, timeouts, thottling và queueing có vượt error budget không? Một job bảo trì có thể cần giảm tốc thay vì cố hoàn tất nhanh nhất.

### 34.5. Bước 5: hành động đã được phép

Throttle, resume, cancel, restart, node replacement, capacity add, rebalance reroute hoặc rebuild đều có rủi ro. Phải dựa trên runbook phù hợp phiên bản và quyền vận hành, **không chạy theo phản xạ khi thấy percent đứng yên**.

### 34.6. Bước 6: nghiệm thu

Kiểm chứng cluster health, data placement, repair coverage, backlog trend, foreground SLO và không còn error log liên quan.

## 35. Java: mô hình trạng thái tác vụ dùng chung

Một Java service giám sát có thể chuẩn hóa dữ liệu từ vendor APIs thành model typed:

```java
import java.time.Instant;
import java.util.OptionalLong;

public record MaintenanceSnapshot(
        String cluster,
        String taskType,
        String taskId,
        String attemptId,
        String phase,
        State state,
        Instant observedAt,
        Instant lastProgressAt,
        long completedWorkUnits,
        OptionalLong estimatedTotalWorkUnits,
        String workUnit,
        long pendingTasks,
        long retryCount,
        String sourceNode,
        String targetNode
) {
    public enum State {
        QUEUED,
        RUNNING,
        PAUSED,
        RETRYING,
        SUCCEEDED,
        FAILED,
        CANCELED,
        UNKNOWN
    }

    public boolean hasKnownTotal() {
        return estimatedTotalWorkUnits.isPresent()
                && estimatedTotalWorkUnits.getAsLong() > 0;
    }
}
```

### 35.1. Vì sao dùng `OptionalLong`?

Một số APIs không cung cấp total work. Dùng `-1` hoặc `0` rồi hiển thị 0% dễ gây hiểu nhầm. `UNKNOWN` có ý nghĩa riêng.

### 35.2. `lastProgressAt` có thể không có

Nếu source không cung cấp progress timestamp, không nên tự tạo từ `observedAt`. Có thể để trường optional hoặc dùng một observer riêng suy progress qua successive samples, kèm độ tin cậy.

### 35.3. Không ép mọi tasks thành same unit

`workUnit` phải mang giá trị như `bytes`, `ranges`, `shards`, `files`. UI có thể hiện `N/A` thay vì lấy `bytes / shards`.

### 35.4. Định danh attempts

Một task retry có thể tạo ID mới; nếu không lưu lineage, dashboard tưởng job cũ hoàn tất và job mới xuất hiện độc lập.

## 36. Java: adapter đọc trạng thái, không khởi chạy repair

Một adapter design:

```java
import java.util.List;

public interface MaintenanceStatusReader {
    List<MaintenanceSnapshot> readCurrentSnapshots()
            throws MonitoringException;

    class MonitoringException extends RuntimeException {
        public MonitoringException(
                String message,
                Throwable cause
        ) {
            super(message, cause);
        }
    }
}
```

Các implementations:

```text
CassandraStatusReader:
  JMX/metrics/nodetool-compatible read endpoint

ElasticsearchStatusReader:
  read-only cluster health/recovery/tasks APIs

RedisStatusReader:
  CLUSTER INFO / INFO persistence / replication

ManagedNoSqlStatusReader:
  vendor Describe/Get operation status API
```

### 36.1. Tách hành động khỏi quan sát

Reader chỉ cần quyền đọc. Nó **không gọi** `nodetool repair`, `force-merge`, `CLUSTER SETSLOT` hoặc thao tác cancel/restart.

### 36.2. Polling có thể quá tải control plane

Đặt poll interval hợp lý, timeout, exponential backoff và rate limit. Không gọi APIs nặng hàng trăm lần/s để đo progress chính xác đến mili-giây.

### 36.3. Snapshot thiếu = không biết

Nếu API timeout, không ghi “pending=0, succeeded=true”. Giữ last-known state cùng `observedAt` và đánh dấu telemetry stale.

### 36.4. Đồng bộ snapshot

Nếu APIs trả nhiều thành phần ở thời điểm khác nhau, phải ghi timestamp/collection window. Một báo cáo 90% từ task endpoint và 0 pending từ endpoint khác có thể là do delay.

## 37. Java Micrometer: xuất gauges cho dashboard

Một adapter giám sát dùng `MeterRegistry` và gauges đại diện cho một cluster/type:

```java
import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public final class MaintenanceTelemetry {

    private final AtomicLong activeTasks = new AtomicLong();
    private final AtomicLong pendingTasks = new AtomicLong();
    private final AtomicLong oldestPendingSeconds =
            new AtomicLong();

    public MaintenanceTelemetry(
            MeterRegistry registry,
            String cluster,
            String taskType
    ) {
        Gauge.builder(
                "nosql.maintenance.active.tasks",
                activeTasks,
                AtomicLong::doubleValue
        ).tag("cluster", cluster)
         .tag("task_type", taskType)
         .register(registry);

        Gauge.builder(
                "nosql.maintenance.pending.tasks",
                pendingTasks,
                AtomicLong::doubleValue
        ).tag("cluster", cluster)
         .tag("task_type", taskType)
         .register(registry);

        Gauge.builder(
                "nosql.maintenance.oldest.pending.seconds",
                oldestPendingSeconds,
                AtomicLong::doubleValue
        ).tag("cluster", cluster)
         .tag("task_type", taskType)
         .register(registry);
    }

    public void update(
            long active,
            long pending,
            long oldestAgeSec
    ) {
        activeTasks.set(active);
        pendingTasks.set(pending);
        oldestPendingSeconds.set(oldestAgeSec);
    }
}
```

### 37.1. Không giả định đây là native exporter

Code này chỉ biến **dữ liệu do `MaintenanceStatusReader` thu được** thành metrics. Nó không tự đọc Cassandra/Redis/Elasticsearch. Cần adapter, authentication và mapping semantics thật.

### 37.2. Gauge với `AtomicLong`

Giữ các objects sống cùng lifecycle với registry để gauges không biến mất. Không tạo mới một meter với label `taskId` cho từng task và để cardinality tăng vô hạn.

### 37.3. Collector phải tôn trọng trạng thái lỗi

Nếu poll thất bại, có thể xuất `probe_success=0` cùng timestamp last success, thay vì gán các gauges về zero làm dashboard nói “đã hết backlog”.

### 37.4. Histogram foreground

Xuất thêm request latency p50/p95/p99/error rate bằng Timer/histogram phù hợp để gắn maintenance với user impact.

## 38. Java LongTaskTimer cho công việc do ứng dụng tự quản

Nếu Java service **tự chạy** reindex/backfill/cleanup, Micrometer `LongTaskTimer` có thể theo dõi các tasks còn hoạt động:

```java
import io.micrometer.core.instrument.LongTaskTimer;
import io.micrometer.core.instrument.MeterRegistry;

public final class RebuildJob {
    private final LongTaskTimer timer;

    public RebuildJob(MeterRegistry registry) {
        this.timer = LongTaskTimer.builder(
                "nosql.application.rebuild.duration"
        ).tag("task_type", "search_backfill")
         .register(registry);
    }

    public void run() {
        LongTaskTimer.Sample sample = timer.start();
        try {
            performRebuild();
        } finally {
            sample.stop();
        }
    }

    private void performRebuild() {
        // Implementation thuộc ứng dụng.
        // Phải có checkpoint/recovery nếu tác vụ bền vững.
    }
}
```

### 38.1. Khi nào hữu ích?

Một Timer truyền thống chỉ ghi duration **sau khi xong**; LongTaskTimer có thể cho biết active count/duration của công việc đang chạy.

### 38.2. Nó không chứng minh tiến độ

Một job hoạt động 5 giờ có thể đang xử lý đều hoặc kẹt; vẫn cần completed units, last-progress và backlog.

### 38.3. Không dùng cho task chạy trên node khác nếu không có nguồn

Nếu Elasticsearch tự relocate shard, tạo LongTaskTimer trong Java monitoring app chỉ vì bắt đầu poll không tự phản ánh lifecycle thật. Dùng vendor task status.

## 39. Logs, events và traces liên kết điều gì?

Metrics cho tổng quan; logs/traces để chẩn đoán từng job.

Một event log minh họa:

```json
{
  "time": "2026-11-14T11:30:00Z",
  "level": "WARN",
  "cluster": "orders-prod",
  "taskType": "REBALANCE",
  "taskId": "rb-107",
  "attempt": 3,
  "phase": "STREAMING",
  "sourceNode": "node-a",
  "targetNode": "node-c",
  "progressBytes": 21474836480,
  "reasonCode": "PEER_TIMEOUT",
  "retryAfterSeconds": 30
}
```

### 39.1. Không log raw records

Không cần ghi tên khách hàng, token đăng nhập hoặc dữ liệu bản ghi vào maintenance logs. Các identifiers node/shard cũng có thể nhạy cảm về hạ tầng; bảo vệ truy cập.

### 39.2. Correlation ID

Dùng một `taskId` ổn định để tra logs của coordinator, source, target và downstream. Nếu retry sinh taskId mới, lưu parent/attempt mapping.

### 39.3. Tracing

Span mẫu:

```text
RebalanceJob
  |
  +-- PlanRanges
  +-- StreamToNodeC
  |     +-- WaitForNetwork
  |     +-- VerifyChecksum
  +-- CommitOwnership
  +-- CleanupOldRange
```

Đây là trace khái niệm; một số engine không expose spans chi tiết. Có thể chuyển phase events thành trace spans ở tầng orchestration nếu nguồn đáng tin.

### 39.4. Sampling

Một repair kéo dài nhiều giờ tạo rất nhiều events. Cần log lifecycle/phase transitions, retry và errors đầy đủ, còn per-chunk tracing có thể sample để tránh gián tiếp làm chậm hệ.

## 40. Kiểm soát phạm vi và thời gian của telemetry

### 40.1. Theo node

Repair/compaction trên node A có thể kẹt trong khi cluster average vẫn bình thường. Cần per-node metrics cho bottlenecks.

### 40.2. Theo table/index/collection

Compaction debt có thể tập trung ở một table nhiều tombstones; index build có thể chậm chỉ ở một collection.

### 40.3. Theo partition/shard/vBucket

Một shard nhiều dữ liệu có thể quyết định ETA; các counters toàn cluster che hotspot.

### 40.4. Theo phase/attempt

Một task restart nhiều lần không được gộp làm duration của một attempt duy nhất nếu cần tìm retry cost.

### 40.5. Theo cửa sổ thời gian

Rate 5 phút, 1 giờ và tổng công việc hoàn tất là những góc nhìn bổ sung, không thay nhau.

### 40.6. Cardinality

Không đẩy mọi `taskId`, `keyRange`, `customerId` vào Prometheus labels. Với các đối tượng nhiều/biến động, lưu logs hoặc task metadata store, còn metrics tổng hợp theo các chiều hữu hạn.

## 41. Trước bảo trì: chuẩn bị an toàn

Một kế hoạch tốt phải được ghi **trước khi bấm chạy**:

- Mục tiêu: repair phạm vi nào, rebalance vì sao, compaction có cần cưỡng bức không?
- Phạm vi: clusters, regions, nodes, tables, token ranges, indexes.
- Prerequisites: cluster health, replicas, backups và recovery ability.
- Dung lượng: free disk/temp space, network, CPU, IO margin.
- Lịch: maintenance window và peak traffic.
- Phụ thuộc: backup, CDC, index build, repair khác, failover.
- Tải foreground và error budget.
- Cấu hình throttling/concurrency cho phép.
- Trạng thái/triggers để pause/abort theo runbook.
- Dashboard, alerts và logs đã được kiểm tra hoạt động.
- Ownership/escalation/communication.
- Xác minh dữ liệu và topology sau khi hoàn thành.
- Kế hoạch xử lý thất bại giữa chừng.

### 41.1. Không chỉ có “free disk hiện tại”

Một compaction có thể cần temporary space trước khi xóa file cũ. Một replica rebuild có thể cần toàn bộ dữ liệu cộng log. Đánh giá peak disk usage theo engine và data size.

### 41.2. Không coi backup thành công là đã restore được

Một backup đã tạo nhưng chưa test restore hoặc thiếu keys/credentials có thể vô dụng. Với thao tác phá hủy, phải có đường recovery thực tế.

### 41.3. Không kích hoạt nhiều jobs nặng đồng thời tùy tiện

Compaction, repair, snapshot và rebalance có thể tranh disk/network. Tính scheduler/budgets để tránh overload.

## 42. Case study A: Cassandra repair tiến triển nhưng service chậm

**Bối cảnh:** Cassandra 6 nodes, replication factor theo thiết kế, repair đã truyền 400 GiB nhưng API read p99 từ 30 ms lên 250 ms.

Quan sát:

```text
Repair streams:      progressing
Disk IO utilization: 95%
Compaction pending:  rising
Foreground p99:      250ms
Read timeouts:       increasing
```

### 42.1. Chẩn đoán

Repair không bị kẹt. Vấn đề là **resource contention**, có thể đồng thời với compaction. Tăng tốc repair thêm nữa có thể làm foreground SLO tệ hơn.

### 42.2. Hành động có thể cân nhắc

- Xem giới hạn streaming/concurrent repair theo version.
- Dời phần còn lại sang maintenance window phù hợp.
- Giảm concurrency/throttle theo runbook.
- Đảm bảo repair coverage vẫn được hoàn thành trong safety window.
- Kiểm tra disk IOPS và khả năng cấp thêm capacity nếu phù hợp.

### 42.3. Kết quả phải đo

API p99/error giảm, backlog repair vẫn có khả năng hoàn tất và không còn ranges bỏ sót. Không chỉ báo “repair đang chạy nhanh 100 MiB/s”.

## 43. Case study B: compaction queue tăng liên tục

**Bối cảnh:** Một cụm Cassandra/RocksDB-like store ghi 30.000 operations/s. Pending compaction từ 40 lên 800 trong hai giờ.

Quan sát:

```text
Write ingress:          30k ops/s
Compaction bytes/s:     fluctuating
Pending tasks:          40 -> 800
Disk free:              20% -> 12%
Read p99:               30ms -> 140ms
```

### 43.1. Ý nghĩa

Có dấu hiệu compaction capacity không theo kịp write workload. Nhưng cần xem các task sizes, compaction policy, flush, data skew, tombstones và disk throughput. Chỉ `pending count` chưa đủ.

### 43.2. Không ép số pending về zero tức thời

Tăng compaction concurrency vô hạn có thể làm disk cạn, gây write stalls. Cần đánh giá throughput hữu ích, headroom và ưu tiên SLO.

### 43.3. Phân biệt spike và nợ dài hạn

Một spike có thể tự giảm sau ingest burst; backlog tăng đều suốt nhiều giờ dưới steady input là dấu hiệu cần điều chỉnh capacity/compaction strategy.

### 43.4. Xác minh

Backlog có xu hướng bounded, free disk ổn định và foreground p99 trở lại mục tiêu. Nếu vẫn tăng dù mới scale, xem skew hoặc write amplification.

## 44. Case study C: rebalance dừng ở một shard lớn

**Bối cảnh:** Elasticsearch có 30 shards cần relocate; 29 shards đã STARTED, một shard 500 GiB còn recovery.

Dashboard:

```text
Shards completed: 29 / 30
Bytes copied:     70% total
Last progress:    18 min ago
Target disk free: 8%
Recovery retries: 4
```

### 44.1. Vì sao 29/30 không đồng nghĩa 96,7% bytes?

Shard cuối chiếm phần lớn dữ liệu. Cần xem **bytes** và phase, không trung bình shard counts.

### 44.2. Nguy cơ

Disk target thấp có thể chặn relocation hoặc khiến allocation deciders từ chối. API có thể vẫn khỏe nhưng redundancy target chưa đạt.

### 44.3. Điều tra

Đọc recovery stage, allocation explain, node disk watermarks, recovery throttle, network errors và replica health. Xác định vì sao last-progress không đổi.

### 44.4. Không tự reroute bất chấp policy

Thay allocation constraints sai có thể đặt dữ liệu ở nơi không đủ disk/availability. Hành động phải tuân thủ topology và runbook.

## 45. Case study D: Redis Cluster slot migration có redirect tăng

Một Redis Cluster đang chuyển nhiều hash slots.

```text
Slots moving:        600
Keys transferred:    increasing
MOVED/ASK redirects: increasing
Client p99:          8ms -> 65ms
Target memory:       91%
```

### 45.1. Giải thích

Key migration và routing change có thể gây redirects, extra round trips và contention. Target memory gần limit là rủi ro eviction/OOM theo policy.

### 45.2. Không đo chỉ slots completed

Một slot có thể chứa nhiều keys/hot traffic. Theo dõi key counts/bytes và latency, kết hợp slot ownership.

### 45.3. Client compatibility

Redis Cluster-aware client phải xử lý `MOVED`/`ASK` theo protocol. Một Java client không hỗ trợ đúng topology updates có thể timeout dù server migration hợp lệ.

### 45.4. Sau migration

Kiểm tra slot coverage, không còn trạng thái importing/migrating bất thường, replica health, memory skew và p99. Không chỉ nhìn CLI báo quá trình đã dừng.

## 46. Case study E: GSI backfill trong DynamoDB

Một ứng dụng tạo GSI để phục vụ query mới:

```text
TABLE Orders
  new GSI CustomerOrders
  state: CREATING/BACKFILLING (vendor semantics)
```

### 46.1. Metric quan trọng

- Index status/backfilling indication.
- Table and GSI write capacity/throttling.
- Backfill-related errors theo API/metrics hỗ trợ.
- Write p99/throughput trong build.
- Index readiness cho query mới.
- Data/index correctness sau ACTIVE.

### 46.2. Không suy ETA nếu API không expose tổng

“GSI đã chạy 2 giờ” không cho biết đã xong 50%. Chỉ dùng tiến độ chính thức nếu có.

### 46.3. Rollout

Ứng dụng không nên chuyển toàn bộ reads sang GSI chưa `ACTIVE` hoặc chưa đúng consistency/access pattern; bản thân GSI reads có eventual-consistency semantics.

### 46.4. Đánh giá cost

GSI backfill và steady-state index writes có thể làm tăng consumed capacity và storage. Cần benchmark query benefit cùng write cost.

## 47. Case study F: MongoDB chunk rebalance không giảm dung lượng nguồn

**Bối cảnh:** range migration hoàn tất theo control plane, nhưng source shard disk usage chưa giảm rõ.

### 47.1. Có thể xảy ra gì?

- Range deletion/cleanup chạy sau metadata handoff.
- WiredTiger/disk file allocation chưa trả bytes về OS.
- Dữ liệu mới đã ghi thêm.
- Replica orphans/cleanup backlog còn tồn tại.
- Dashboard disk filesystem đo khác logical data size.

### 47.2. Không kết luận migration failed chỉ từ dung lượng file

Đối chiếu ownership, range placement, cleanup state/log và logical data size. Cần đọc cơ chế disk reclamation thực tế của engine/version.

### 47.3. Điều không nên làm

Không xóa thủ công các file storage engine hoặc dữ liệu trên shard để “thu hồi ngay” khi chưa có runbook chính thức. Có thể làm hỏng dữ liệu/metadata.

### 47.4. Nghiệm thu

Routing/ownership đúng, dữ liệu không thiếu/trùng trên đường query, cleanup theo kỳ vọng, disk headroom an toàn và p99 ổn định.

## 48. Trạng thái “SUCCEEDED” và bài toán dữ liệu đúng

Một tác vụ completed status từ orchestration mới chứng minh **hệ quản lý tác vụ tin rằng các bước được giao đã hoàn tất**.

### 48.1. Repair

- Đã xử lý đúng toàn bộ phạm vi yêu cầu?
- Có host/range bị skip?
- Lịch sử repair có cập nhật đúng?
- Có replicas stale cần repair riêng?
- Có tombstone/retention risk chưa giải quyết?

### 48.2. Rebalance

- Ownership metadata phù hợp?
- Tất cả required primaries/replicas có được phân bổ?
- Có routing/keyspace gap?
- Node mới có thể phục vụ tải thực không?
- Client drivers đã nhận topology mới chưa?

### 48.3. Compaction

- Backlog về mức bounded?
- Read amplification/tombstone scan giảm?
- Disk free ổn định?
- Query p99/timeout đạt SLO?
- Có lỗi SSTables/segments hoặc failures chưa xử lý?

### 48.4. Restore/index build

- Data parity/correctness sample.
- Read/write access hoạt động.
- Index query plans hợp lệ.
- Không còn replay lag hoặc pending verification.
- Có backup/recovery mới sau change nếu policy yêu cầu.

**Trạng thái cuối phải nối với một tiêu chí nghiệm thu có thể quan sát.**

## 49. Kiểm thử hệ quan sát trước khi xảy ra sự cố thật

Một dashboard chỉ mới vẽ đẹp nhưng chưa có test có thể thất bại đúng lúc cần dùng.

### Test 1 — Tác vụ đang chạy lâu

Tạo task staging có long-running phase; dashboard hiện active duration, last heartbeat và progress. Không chỉ hiện finished duration.

### Test 2 — Không có total

Source trả total unknown; UI hiện `N/A/unknown`, không ép 0% hay 100%.

### Test 3 — Tổng công việc tăng

Task từ total 100 lên 150 do phát sinh work; biểu đồ giải thích denominator change, không giả “đã lùi mất dữ liệu”.

### Test 4 — Retry

Worker xử lý cùng chunk ba lần; counter transfer bytes có thể tăng ba lần, nhưng unique completed work không tăng 3 lần.

### Test 5 — Worker chết sau khi đã báo progress

Heartbeat ngừng, last-progress age tăng, trạng thái có thể vẫn RUNNING trong snapshot cũ; alert cần nhận diện telemetry stale.

### Test 6 — Exporter down

Metrics biến mất; hệ phải cảnh báo monitor unavailable, không báo backlog=0.

### Test 7 — Network partition

Repair/replica catch-up bị chặn; dashboard phân biệt peer unreachable với “tiến độ 0%”.

### Test 8 — Disk full

Compaction/rebalance bị blocked; alert liên kết disk headroom, task state và foreground errors.

### Test 9 — Foreground latency regression

Task đang tiến triển đều nhưng API p99 vượt SLO; phải hiển thị user impact và hướng giảm áp lực.

### Test 10 — Success but invalid placement

Task báo success nhưng một required shard vẫn unassigned; verification không được coi healthy.

### Test 11 — Stale event

Retry callback từ attempt cũ đến sau attempt mới; task metadata không được chuyển SUCCEEDED thành RUNNING do event cũ.

### Test 12 — High-cardinality task IDs

Tạo hàng nghìn tasks; metrics backend không nổ cardinality vì labels theo từng UUID.

### Test 13 — Timestamp skew

Nguồn API có clock lệch; monitoring phải có timestamp provenance và không suy negative elapsed time là progress.

### Test 14 — Managed service opaque progress

Describe API chỉ trả CREATING/ACTIVE; dashboard không tự bịa percentages.

### Test 15 — Node restart

Counters reset; rate/increase không báo âm; last-known task ownership được cập nhật.

### Test 16 — Source/target disagreement

Source báo sent 100 GiB, target nhận 80 GiB; dashboard không coi copy complete chỉ từ source sent counter.

### Test 17 — LSM background compaction

Pending tasks thay đổi liên tục; alert dùng trend/oldest age thay vì đòi về zero từng phút.

### Test 18 — Maintenance window end

Công việc còn incomplete khi hết window; có owner/escalation và quyết định tiếp tục hoặc dừng theo runbook, không tự đánh dấu thành công.

## 50. Những nhầm lẫn dễ gây sự cố

**“Task RUNNING nên đang tiến triển.”** Chưa chắc; có thể kẹt hoặc retry vô hạn.

**“Không còn task RUNNING nghĩa đã xong.”** Có thể FAILED/CANCELED hoặc mất telemetry.

**“Repair chỉ là sửa dữ liệu hỏng.”** Trong hệ anti-entropy, repair thường là đồng bộ bản sao định kỳ.

**“Rebalance xong copy dữ liệu là xong.”** Còn metadata, catch-up và cleanup.

**“Compaction xong là database đã được backup.”** Không liên quan.

**“Tăng compaction concurrency luôn tốt.”** Có thể tranh I/O và gây write stalls.

**“Pending=0 sau exporter crash nghĩa backlog hết.”** Không; metrics có thể stale.

**“Cùng 10 shards nghĩa cùng 10 GiB.”** Không; shard sizes lệch.

**“Progress 90% chắc chắn còn 10% thời gian.”** Không; phase, retries và throughput thay đổi.

**“Network bytes/s cao nghĩa repair đang hội tụ.”** Chưa chắc đang truyền lại cùng dữ liệu.

**“Một lần scrape đủ báo stalled.”** Không; cần lịch sử/phase.

**“Cassandra `nodetool repair` là lệnh xem repair.”** Không; lệnh kích hoạt công việc nặng.

**“Elasticsearch yellow luôn là mất dữ liệu.”** Không; thường là replica unassigned nhưng vẫn cần kiểm tra redundancy.

**“MongoDB WiredTiger giống LSM compaction của Cassandra.”** Không; storage architecture khác.

**“Redis Cluster đã chuyển 50% slots nghĩa chuyển 50% bytes.”** Không.

**“Managed DynamoDB bắt buộc phải expose compaction %.”** Không; nhiều tác vụ internal không public.

**“Couchbase rebalance 100% nghĩa QPS cân bằng tuyệt đối.”** Không; hot key vẫn có thể tồn tại.

**“GSI index ACTIVE nghĩa query có strong read.”** Không; consistency contract của GSI vẫn phải được hiểu.

**“Chỉ nhìn cluster CPU trung bình là đủ.”** Không; một hot shard có thể nghẽn.

**“Index build hoàn tất thì foreground SLO không cần đo nữa.”** Không; steady-state write amplification có thể tăng.

**“Một meter cho mỗi task ID là luôn an toàn.”** Không; time-series cardinality tăng nhanh.

**“Chỉ cần logs, không cần last-progress metrics.”** Logs đơn lẻ khó phát hiện trend/stall có điều kiện.

**“Một task succeeded chắc chắn mọi dữ liệu đúng.”** Cần scope và verification.

**“Có thể ép cancel/restart mọi job stuck.”** Hành động phụ thuộc engine/version/safety.

**“Bảo trì làm giảm p99 thì có thể đánh đổi durability.”** Không nếu business contract không cho phép.

## 51. Bài tập thực hành

### Bài tập 1 — Nhận diện tác vụ

Một Cassandra node phải so sánh ranges và streaming dữ liệu khác biệt với replicas.

**Câu hỏi:** Đây là repair, rebalance hay compaction?

**Gợi ý:** Anti-entropy repair.

### Bài tập 2 — Phân biệt compaction

Nhiều SSTables được hợp nhất để giảm read amplification.

**Câu hỏi:** Có phải backup không?

**Gợi ý:** Không; compaction khác backup và replica repair.

### Bài tập 3 — Rebalance

Elasticsearch đang di chuyển shards sang node mới.

**Câu hỏi:** Cần monitor gì ngoài bytes copied?

**Gợi ý:** Shard state/ownership, retries, disk/cluster health và user SLO.

### Bài tập 4 — Progress không có total

Một task managed chỉ trả `RUNNING`.

**Câu hỏi:** Có nên hiển thị 50% vì chạy được một nửa maintenance window không?

**Gợi ý:** Không; total unknown.

### Bài tập 5 — Tính phần trăm

Snapshot copy 600 GiB trên tổng 800 GiB.

**Câu hỏi:** Tiến độ theo bytes?

**Gợi ý:** 75%, chưa gồm verify/catch-up.

### Bài tập 6 — ETA

Remaining 120 GiB, useful rate 60 MiB/s.

**Câu hỏi:** ETA phase copy gần đúng?

**Gợi ý:** 2048 giây, khoảng 34 phút nếu rate ổn định.

### Bài tập 7 — Rate sai

NIC truyền 200 MiB/s nhưng retry 150 MiB/s.

**Câu hỏi:** Có nên lấy 200 MiB/s tính ETA công việc hữu ích?

**Gợi ý:** Không; chỉ useful progress rate.

### Bài tập 8 — Trung bình percent

Shard A 90% của 100 GiB, shard B 10% của 1 GiB.

**Câu hỏi:** Percent theo bytes gần bao nhiêu?

**Gợi ý:** Khoảng 89,2%, không phải 50%.

### Bài tập 9 — Tổng work tăng

Compaction pending từ 10 lên 15 dù đã hoàn thành 5 tasks.

**Câu hỏi:** Có phải worker không xử lý được gì?

**Gợi ý:** Không; new work có thể sinh nhanh hơn rate hoàn tất.

### Bài tập 10 — Stall

Repair RUNNING, heartbeat mới 2 giây nhưng không tăng verified ranges trong 45 phút.

**Câu hỏi:** Có thể kết luận health chỉ từ heartbeat không?

**Gợi ý:** Không; kiểm tra phase/retries/blocked peers.

### Bài tập 11 — Cassandra observability

Muốn xem streaming sessions và compaction backlog.

**Câu hỏi:** Những lệnh read-only nào hữu ích?

**Gợi ý:** `nodetool netstats`, `nodetool compactionstats` theo version.

### Bài tập 12 — Cassandra safety

Một kỹ sư chạy `nodetool repair` để “xem tiến độ”.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Nó có thể kích hoạt repair thực, không phải trạng thái read-only.

### Bài tập 13 — Cassandra tombstones

Muốn xóa tombstones ngay để giảm disk khi replicas còn offline.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Resurrection/consistency violations; tuân thủ repair và grace semantics.

### Bài tập 14 — Elasticsearch health

Cluster yellow, một replica chưa được phân bổ.

**Câu hỏi:** Có chắc primary đã mất không?

**Gợi ý:** Không; yellow thường có primary được phân bổ và replica thiếu.

### Bài tập 15 — Recovery progress

Elasticsearch copy files 100%, shard vẫn INITIALIZING.

**Câu hỏi:** Có lỗi nhất thiết không?

**Gợi ý:** Chưa; có thể còn replay/finalization.

### Bài tập 16 — Redis slots

8.192/16.384 slots đã chuyển.

**Câu hỏi:** Có thể kết luận 50% traffic đã di chuyển không?

**Gợi ý:** Không; hot keys/bytes lệch.

### Bài tập 17 — Redis persistence

`aof_rewrite_in_progress=1`.

**Câu hỏi:** Đây có phải slot rebalance đang chạy?

**Gợi ý:** Không; AOF rewrite là maintenance khác.

### Bài tập 18 — MongoDB range migration

Chunk ownership đã chuyển nhưng source disk usage không giảm.

**Câu hỏi:** Tác vụ có chắc thất bại không?

**Gợi ý:** Không; range cleanup và disk reclamation có thể trễ.

### Bài tập 19 — MongoDB index build

Documents scanned 100%, index chưa usable.

**Câu hỏi:** Còn bước gì?

**Gợi ý:** Commit/finalize/index state theo engine/version.

### Bài tập 20 — DynamoDB GSI

`IndexStatus=CREATING`, không có percent.

**Câu hỏi:** Dashboard nên làm gì?

**Gợi ý:** Hiện trạng thái, elapsed time, throttling/capacity; ETA unknown.

### Bài tập 21 — Cosmos DB

API p99 cao và 429 tăng; team khẳng định physical partition split lỗi.

**Câu hỏi:** Bằng chứng đủ chưa?

**Gợi ý:** Chưa; có thể hot partition/capacity throttling.

### Bài tập 22 — Couchbase vBuckets

Tất cả vBuckets đã chuyển, nhưng một tenant vẫn chậm.

**Câu hỏi:** Cần xem gì?

**Gợi ý:** Hot key/workload skew, index/service resource.

### Bài tập 23 — HBase

Region split tăng số regions, compaction queue vẫn cao.

**Câu hỏi:** Có cùng loại công việc không?

**Gợi ý:** Không; region balancing/split khác HFile compaction.

### Bài tập 24 — Metrics missing

Exporter không scrape 20 phút, dashboard query hiện không có active tasks.

**Câu hỏi:** Có thể kết luận bảo trì đã hoàn tất không?

**Gợi ý:** Không; giám sát freshness và target up.

### Bài tập 25 — Counter reset

Task byte counter từ 100 GiB về 0 sau process restart.

**Câu hỏi:** Tốc độ xử lý có phải âm không?

**Gợi ý:** Không; counter reset, cần rate/increase reset-aware.

### Bài tập 26 — Long task timer

Java job rebuild đang kẹt 4 giờ, completed Timer chưa có mẫu.

**Câu hỏi:** Nên dùng metric gì?

**Gợi ý:** LongTaskTimer/active duration + last-progress/backlog.

### Bài tập 27 — Cardinality

Mỗi lần repair có UUID mới, engineer thêm UUID làm Prometheus label.

**Câu hỏi:** Vấn đề?

**Gợi ý:** Time-series cardinality lớn; để UUID trong logs/task store.

### Bài tập 28 — Repair scope

Repair một table trên một node thành công.

**Câu hỏi:** Đã chứng minh toàn keyspace/cluster khỏe chưa?

**Gợi ý:** Chưa; kiểm tra coverage.

### Bài tập 29 — Foreground SLO

Compaction backlog giảm mạnh nhưng API write p99 tăng 4 lần.

**Câu hỏi:** Có nên tăng concurrency hơn nữa?

**Gợi ý:** Không chỉ vì backlog; đánh giá resource contention và SLO guardrails.

### Bài tập 30 — Thiết kế dashboard tổng hợp

Một nền tảng dùng Cassandra cho events, Elasticsearch search, Redis Cluster cache và DynamoDB cho inventory.

**Yêu cầu:** Thiết kế per-system task states, progress units, alerts, dashboard foreground SLO, read-only monitoring commands/APIs, action runbook và verification.

**Gợi ý:** Cassandra repair/compaction ranges+bytes, Elasticsearch shard recovery, Redis slot/keys migration, DynamoDB GSI/managed operations; tránh ghép các % thành một tiến độ chung.

### Bài tập 31 — Sau task thành công

Rebalance `SUCCEEDED` nhưng cluster vẫn có required replica unassigned.

**Câu hỏi:** Có được đóng incident không?

**Gợi ý:** Không; verification/availability target chưa đạt.

### Bài tập 32 — Không hứa ETA

Restore job không có known total, throughput dao động mạnh.

**Câu hỏi:** Cần hiển thị gì?

**Gợi ý:** Phase, elapsed, completed metrics nếu có, ETA unknown và lý do.

## 52. Checklist vận hành

- [ ] Đã phân biệt repair, rebalance, compaction, restore, recovery và index build.
- [ ] Đã xác định engine/version và tính năng maintenance thực sự có.
- [ ] Đã nêu source/target, scope, parent/subtasks, owner và attempt ID.
- [ ] Có state và phase, không chỉ một boolean `running`.
- [ ] Có `lastHeartbeatAt`, `lastProgressAt`, elapsed và age của backlog.
- [ ] Có counter useful progress và backlog theo units chính xác.
- [ ] Chỉ tính percent khi có denominator được hỗ trợ.
- [ ] ETA được ghi giả định và giới hạn cho đúng phase.
- [ ] Không trung bình percent các child tasks có kích thước khác.
- [ ] Có per-node, per-table/index, per-partition/shard breakdown.
- [ ] Đã tách copied bytes, verified bytes và retried bytes.
- [ ] Biết task có thể sinh work mới hoặc denominator thay đổi.
- [ ] Biết command nào chỉ đọc và command nào thay đổi hệ thống.
- [ ] Không chạy repair/rebalance/force-merge để “kiểm tra”.
- [ ] Có CPU, disk free, IOPS, network và pool/queue metrics.
- [ ] Có foreground p95/p99/error/goodput guardrails.
- [ ] Có quorum/replica/shard/ownership/data safety checks.
- [ ] Không coi telemetry missing là task complete.
- [ ] Có alert stalled theo phase và liên tục qua nhiều samples.
- [ ] Có alert failed task và owner/escalation cụ thể.
- [ ] Có alert disk pressure/retention deadline.
- [ ] Có lịch sử repair coverage và maintenance schedule.
- [ ] Có runbook cho peer unreachable, network, disk, auth và throttle.
- [ ] Có backup/restore plan với các thay đổi rủi ro cao.
- [ ] Đã đánh giá competing maintenance jobs và tài nguyên dự phòng.
- [ ] Có metrics labels cardinality hữu hạn, task IDs trong logs.
- [ ] Có dashboard per-system thay vì ép cùng metric `repairPercent`.
- [ ] Managed NoSQL không expose percent thì hiển thị unknown.
- [ ] Đã kiểm thử retry, restart, stale metric, counter reset và data verification.
- [ ] Đã diễn tập node failover/compaction pressure trong staging.
- [ ] Có tiêu chí nghiệm thu sau `SUCCEEDED`.
- [ ] Có incident timeline, artifacts và bài học sau khắc phục.

## 53. Tổng kết

Repair, rebalance và compaction đều là các công việc nền quan trọng nhưng giải quyết **những mục tiêu khác nhau**:

- **Repair** tập trung vào sự hội tụ hoặc phục hồi dữ liệu giữa các replicas/ranges, điển hình ở Cassandra. Cần theo dõi coverage, validation, streaming, failed ranges và các điều kiện an toàn.
- **Rebalance** chuyển dữ liệu hoặc ownership giữa nodes/shards/slots/vBuckets. Cần theo dõi source/target, phases, bytes hoặc partitions moved, placement và tình trạng phục vụ sau handoff.
- **Compaction** tổ chức lại lưu trữ, giảm read amplification và xử lý các file/tombstones theo policy. Đây thường là backlog biến động liên tục; đo pending age, bytes rate, disk pressure và tác động tới p99 thay vì đòi “100% complete”.
- **Tác vụ tương ứng** ở từng hệ có thể là shard recovery, replica initial sync, index backfill, GSI build, restore, DCP catch-up hoặc managed partition operation; không cố gán một biểu đồ % repair cho mọi database.

Một hệ quan sát đáng tin luôn kết hợp **trạng thái – tiến độ hữu ích – tài nguyên – an toàn dữ liệu – ảnh hưởng tới người dùng**. Độ trễ của một task không đồng nghĩa task lỗi, và một phần trăm hoàn thành đẹp không chứng minh dữ liệu đã an toàn. Chỉ can thiệp sau khi xác minh phase, nguồn thông tin, root cause và runbook được phép.

**Nguyên tắc cốt lõi:** *Đừng chỉ hỏi “repair/rebalance/compaction đã hoàn thành bao nhiêu phần trăm?”. Hãy hỏi “những đơn vị công việc nào thực sự đã được kiểm chứng, những phần nào còn lại hoặc bị kẹt, có rủi ro dữ liệu gì, foreground SLO đang ra sao, và điều kiện nào chứng minh tác vụ đã hoàn tất an toàn?”.*




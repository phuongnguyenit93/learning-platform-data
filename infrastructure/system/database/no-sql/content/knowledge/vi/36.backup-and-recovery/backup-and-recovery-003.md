# Sao lưu logic, sao lưu vật lý và điều kiện tính nhất quán

Một hệ thống đặt hàng sử dụng NoSQL có thể tạo backup mỗi đêm nhưng vẫn không khôi phục được dữ liệu đúng sau sự cố. Ví dụ, bản export đọc tập `Orders` lúc 01:00 nhưng đọc `OrderItems` lúc 01:12, trong khi hệ thống liên tục tạo, sửa và hủy đơn. Khi restore, một số đơn hàng có thể không có đủ dòng hàng. Ngược lại, sao chép nguyên thư mục dữ liệu từ database đang ghi cũng không tự đảm bảo các tệp cùng thuộc một trạng thái nhất quán.

Bài học thuộc chương **Sao lưu và phục hồi**, module **Database No SQL**, tập trung vào ba câu hỏi:

1. **Sao lưu logic và sao lưu vật lý khác nhau thế nào?** Chúng sao chép ở tầng nào, giữ metadata gì và phù hợp tình huống nào?
2. **“Nhất quán” trong backup nghĩa là gì?** Cần crash-consistent, transaction-consistent, application-consistent hay consistent cut của cụm phân tán?
3. **Làm sao biết backup khôi phục được?** Cần metadata, log, khóa giải mã, restore drill, kiểm chứng dữ liệu và mục tiêu RPO/RTO nào?

Ví dụ MongoDB, Cassandra/ScyllaDB, Redis, DynamoDB và search/read models được dùng để minh họa. Các sản phẩm **không có cùng lệnh backup hoặc bảo đảm snapshot**. Cú pháp, retention, quyền, online-backup capability và version compatibility phải được xác minh trên **engine, phiên bản và topology thực tế**. Mọi con số là giả định học tập.

> **Nguyên tắc:** Một backup đáng tin không chỉ chứa dữ liệu đã sao chép; nó có **ranh giới nhất quán được định nghĩa**, metadata/chuỗi log đầy đủ, quyền giải mã và **bằng chứng phục hồi thành công**.

## 1. Backup, replication, archive và disaster recovery không đồng nghĩa

| Khái niệm | Mục đích chính | Có thay backup không? |
|---|---|---|
| **Backup** | Tạo bản sao dùng để khôi phục một trạng thái được định nghĩa | Là nguồn phục hồi nhưng phải kiểm chứng |
| **Replication** | Tăng khả dụng, nhân thay đổi qua replicas | **Không**: delete/corruption có thể lan sang replica |
| **Snapshot** | Ghi trạng thái tại điểm hoặc khoảng thời gian theo cơ chế cụ thể | Có thể là thành phần backup, vẫn cần consistency/restore |
| **Archive** | Giữ dữ liệu/sự kiện dài hạn | Hỗ trợ rebuild nhưng không tự là full backup |
| **CDC/event log** | Truyền/replay thay đổi | Chỉ nếu retention và semantics còn đủ |
| **Disaster recovery (DR)** | Khôi phục dịch vụ khi hạ tầng/vùng hỏng | Cần backup, replication, config và runbook |

Ba replicas cùng áp lệnh xóa nhầm collection sẽ **nhân bản cả lỗi**. Muốn quay về trước lúc xóa, cần một recovery source độc lập theo mục tiêu nghiệp vụ.

### 1.1. Backup không tự lưu mọi transaction đến thời điểm sự cố

Backup lúc 01:00 có thể phục hồi trạng thái tới 01:00. Những write đã xác nhận lúc 01:03 có thể mất nếu không có log/PITR. Cần xác định **Recovery Point Objective (RPO)** thay vì chỉ nói “backup hằng ngày”.

## 2. Sao lưu logic là gì?

**Logical backup** xuất records/documents/keys, collections/tables và metadata như schema/index definitions theo giao diện hiểu được ở tầng dữ liệu logic.

~~~mermaid
flowchart LR
    DB[("NoSQL source")] --> READ["Logical read / export"]
    READ --> ENCODE["Encode data + metadata"]
    ENCODE --> FILE[("Logical backup files")]
    FILE --> IMPORT["Decode / import"]
    IMPORT --> TARGET[("Restored NoSQL")]
~~~

Một cấu trúc minh họa:

~~~text
backup-2026-11-14/
  metadata.json
  collections/
    orders.ndjson.zst
    order_items.ndjson.zst
    customers.ndjson.zst
  schemas/
    indexes.json
    validators.json
  manifest.json
  checksums.txt
~~~

Đây **không phải format chuẩn của một sản phẩm**. Xuất mọi documents có thể vẫn thiếu users/roles, sharding metadata, encryption configuration, transaction logs hoặc external secrets.

### 2.1. Đặc trưng logical backup

- Dễ đọc/chuyển đổi khi format và schema tương thích.
- Có thể phục hồi một phần, lọc tenant/collection nếu quyền và công cụ cho phép.
- Có thể hỗ trợ migration sang engine/version khác, nhưng không bảo đảm tương thích.
- Restore phải parse, insert, rebuild indexes và khôi phục metadata phù hợp.
- Không giữ nguyên internal page/cache/SSTable layout.
- Full scan/serialization/network có thể tiêu tài nguyên nguồn lớn.
- **Không tự là transaction-consistent nếu writes vẫn diễn ra**.

## 3. Sao lưu vật lý là gì?

**Physical backup** sao chép dữ liệu ở tầng file/volume/storage engine image hoặc native snapshot, ví dụ các data files, segments, pages, SSTables và commit logs cần thiết.

~~~mermaid
flowchart LR
    ENGINE["NoSQL storage engine"] --> VOL["Data files + logs"]
    VOL --> SNAP["Engine/storage coordinated snapshot"]
    SNAP --> COPY[("Physical backup")]
    COPY --> RECOVER["Restore + engine recovery"]
    RECOVER --> TARGET[("Restored instance")]
~~~

### 3.1. Đặc trưng physical backup

- Có thể tận dụng native storage snapshots và incremental changed blocks.
- Có thể phục hồi nhanh hơn logical import ở một số quy mô/topology.
- Phụ thuộc storage format, engine/version, OS/volume, encryption keys.
- File copy thủ công khi DB đang ghi có thể không tự nhất quán.
- Cần snapshot/checkpoint/quiesce protocol được hỗ trợ.
- Có thể phải giữ WAL/commitlog/oplog và topology metadata.
- Không phải lúc nào dễ khôi phục một document riêng hoặc chuyển engine.

**Sao chép thư mục dữ liệu đang hoạt động bằng file copy thông thường không đồng nghĩa physical backup nhất quán.**

## 4. So sánh sao lưu logic và vật lý

| Tiêu chí | Logical backup | Physical backup |
|---|---|---|
| Tầng dữ liệu | Records/schema/collections | Pages/files/segments/storage image |
| Phụ thuộc engine | Thường ít hơn | Thường nhiều hơn |
| Portability | Có thể thuận lợi hơn | Cần format/engine tương thích |
| Nhất quán khi có writes | Cần read/snapshot protocol | Cần engine/storage coordinated snapshot |
| Tải lên nguồn | Query/scan, encode, egress | Snapshot COW, flush, copy disk I/O |
| Kích thước | Tùy data/format/compression | Tùy blocks/segments, snapshot chain |
| Partial restore | Thường thuận lợi hơn | Có thể phải restore instance tạm |
| Restore | Import/index rebuild có thể tốn thời gian | Có thể nhanh nếu native restore hỗ trợ |
| Metadata | Cần export/import schema/index/roles riêng | Một số metadata nằm trong image, vẫn phải kiểm tra |
| PITR | Cần log/history tương thích | Thường kết hợp snapshot + logs |
| Phân tán | Cần consistent cut/reconciliation | Cần coordinated node/shard snapshots |
| Bảo mật | Có thể xuất plaintext PII | Có thể chứa toàn bộ image/raw data |

**Không có loại sao lưu tốt nhất mọi trường hợp**. Lựa chọn dựa trên RPO/RTO, dữ liệu, portability, topology, granularity, storage cost và khả năng verify.

## 5. Full, incremental và differential là chiều phân loại riêng

Đừng nhầm “logical/physical” với “full/incremental/differential”.

- **Full:** sao lưu đầy đủ một scope vào một trạng thái/mốc xác định.
- **Incremental:** phần thay đổi từ mốc tham chiếu theo cơ chế của tool/engine.
- **Differential:** phần thay đổi so với full backup gốc nếu công cụ hỗ trợ.

Ví dụ incremental:

~~~text
Sunday: full B0
Monday: incremental B1
Tuesday: incremental B2
Wednesday: incremental B3

Restore Wednesday:
  B0 + B1 + B2 + B3
~~~

Ví dụ differential:

~~~text
Sunday: full B0
Monday: differential D1 from B0
Tuesday: differential D2 from B0
Wednesday: differential D3 from B0

Restore Wednesday:
  B0 + D3
~~~

Một incremental bị mất có thể khiến cả chuỗi không phục hồi được. Engine thực tế có thể dùng block changed lists, synthetic full, snapshot dependencies hoặc backups dạng khác, nên **recovery chain phải xuất phát từ manifest thực tế**.

### 5.1. Incremental backup không đồng nghĩa CDC log

Incremental snapshot có thể lưu blocks/files, không phải một lịch sử business events. CDC có thể thiếu before image hoặc retention không đủ. Không suy chỉ vì “incremental” mà có thể phục hồi tới bất kỳ giây nào.

## 6. Cấp độ nhất quán của backup

| Cấp | Định nghĩa | Điều chưa được bảo đảm |
|---|---|---|
| File copy không phối hợp | Sao chép từng file tại thời điểm bất kỳ | Có thể không mở được |
| **Crash-consistent** | Tương đương storage image sau mất nguồn tại một instant trong snapshot scope | Chưa gồm giao dịch nhiều hệ |
| **Database-/transaction-consistent** | Hợp lệ theo commit/transaction semantics tại cutoff | Chưa gồm API/external effects |
| **Application-consistent** | Các business invariants có thể phục hồi trên nhiều stores | Cần protocol ứng dụng |
| **Distributed-consistent cut** | Không có hậu quả event thiếu causal predecessor theo model | Không tự có trên mọi cluster |

Một volume snapshot có thể crash-consistent cho volume đó, nhưng chưa nhất quán cho nhiều DB shards hoặc DB và event broker.

**Một snapshot được gọi tên “snapshot” không tự chứng minh cấp consistency nào.** Phải ghi engine, scope, cơ chế và cách xác minh.

## 7. Crash-consistent: hiểu cơ chế khôi phục sau mất nguồn

Một engine dùng WAL/commitlog có thể khôi phục từ data image và log nếu snapshot thỏa **write-order rules** của engine:

~~~text
WAL state + data files from consistent storage cut
    -> engine crash-recovery procedure
    -> committed work replayed if needed
    -> incomplete work discarded/rolled back if applicable
    -> recoverable DB state
~~~

Nhưng bản sao phải gồm **đủ files/volumes cần thiết**. Nếu WAL ở volume A và data files ở volume B, hai snapshot độc lập chụp cách nhau có thể không tạo một trạng thái hợp lệ. Hệ cần atomic multi-volume snapshot hoặc một protocol phối hợp/chụp checkpoint được nhà cung cấp hỗ trợ.

**Crash-consistent không đồng nghĩa application-consistent.** Một database instance có thể recovery thành công nhưng payment provider hoặc message broker vẫn ở thời điểm khác, nên cần reconciliation.

## 8. Transaction-consistent: đọc cùng một mốc

Giả sử:

~~~text
T0: Transaction X begins.
T1: Export starts reading Orders.
T2: Transaction X commits Orders + OrderItems.
T3: Export starts reading OrderItems.
~~~

Nếu export chỉ đọc “latest committed” trong từng lần gọi, tập `Orders` và `OrderItems` có thể đại diện cho hai thời điểm khác nhau. Nếu hệ có snapshot read tại **cùng logical timestamp S** và công cụ giữ snapshot S xuyên toàn quá trình, việc đọc có thể cùng một trạng thái theo semantics của engine.

Cần trả lời rõ:

- Snapshot bao phủ một key, collection, database, shard hay toàn cluster?
- Một session/snapshot timestamp có được giữ giữa nhiều pages, connections không?
- Engine cho giữ snapshot bao lâu khi scan 10 TB?
- Old versions/undo/compaction cần giữ khiến storage tăng thế nào?
- Index/DDL changes có thể xảy ra khi export không?
- Có cần pin log/history và yêu cầu read consistency đặc biệt?
- Nếu backup dùng nhiều worker, chúng có share cùng cut được không?

**Read concern mạnh cho từng GET không tự tạo atomic snapshot xuyên hàng triệu GETs.**

## 9. Application-consistent: phục hồi đúng bất biến nghiệp vụ

Một đơn hàng có thể trải qua:

~~~text
1. Inventory reservation committed.
2. Order state CONFIRMED committed.
3. Outbox event committed.
4. CDC/search projection updates later.
5. Payment provider confirms charge.
~~~

Một database backup có thể chứa bước 2 nhưng chưa chứa projection bước 4; điều đó có thể **chấp nhận được** nếu search là derived data và có thể rebuild. Tuy nhiên nếu backup thiếu outbox event cần phát, hệ restore có thể làm downstream bị mất thông báo.

Phải xác định:

1. **Source of truth** cho từng trường và business fact.
2. Workflow state nào là hợp lệ giữa các bước.
3. Outbox/inbox, idempotency key và pending job state phục hồi thế nào.
4. Broker offsets và CDC consumers bắt đầu từ vị trí nào.
5. External effects (charge/email/third-party) đã diễn ra nhưng không còn trong DB backup được reconcile ra sao.
6. Những projections nào được rebuild thay vì restore nguyên xi.

Không cần backup mọi hệ ở một nanosecond nếu đã có **protocol tái hội tụ** từ durable source/outbox và nguyên tắc đối soát.

## 10. Snapshot phân tán: node và shard có thời điểm khác nhau

~~~mermaid
flowchart TD
    API["Application"] --> ROUTER["Router / coordinator"]
    ROUTER --> S1["Shard A"]
    ROUTER --> S2["Shard B"]
    ROUTER --> S3["Shard C"]
    S1 --> B1["Snapshot A"]
    S2 --> B2["Snapshot B"]
    S3 --> B3["Snapshot C"]
~~~

Nếu:

~~~text
Snapshot A: 01:00:00
Snapshot B: 01:00:18
Snapshot C: 01:00:43
~~~

thì tập file có thể không đại diện cho một **global consistent cut**. Giao dịch xuyên shard có thể được thấy ở một bản nhưng không ở bản khác.

Các lựa chọn tùy engine:

- Native cluster-consistent snapshot.
- Shared logical snapshot/read timestamp.
- Coordinated write pause/quiescence.
- Snapshot ở các điểm khác nhau + **đủ log replay** tới một consistent recovery target.
- Reconcile application facts theo invariants nếu không cần global snapshot.
- Tách authoritative source và derived copies, rebuild phần sau.

Không tự copy từng node rồi ghép file vào một cluster mới nếu sản phẩm không hỗ trợ restore topology đó.

## 11. Consistent cut theo quan hệ nhân quả

Ví dụ:

~~~text
Shard A: reserve inventory  ----causes---->
Shard B: confirm order
~~~

Một cut chứa confirmation nhưng thiếu inventory reservation có thể sai nếu app kỳ vọng chúng phải nhất quán. Tuy nhiên trong saga, trạng thái reservation đã có nhưng order chưa confirmed có thể vẫn hợp lệ nếu workflow có retry/compensation state.

**Định nghĩa hợp lệ phải xuất phát từ state machine và invariant của ứng dụng**, không áp một quy tắc “mọi component phải commit cùng lúc” cho mọi hệ.

Cần kiểm tra causal relationship giữa outbox events, business records, logs và snapshots. Nếu có nhiều write origins độc lập, timestamp wall-clock không tạo total order chính xác.

## 12. Manifest: mốc khôi phục không phải chỉ tên file

Một manifest khái niệm:

~~~json
{
  "backupId": "orders-bk-20261114-0100",
  "clusterRef": "orders-prod",
  "engine": "example-nosql",
  "engineVersion": "documented-version",
  "backupKind": "physical-snapshot",
  "consistency": "engine-coordinated",
  "startedAt": "2026-11-14T01:00:00Z",
  "completedAt": "2026-11-14T01:05:00Z",
  "sourcePositions": {
    "shard-A": "log-position-A",
    "shard-B": "log-position-B"
  },
  "schemaVersion": "schema-v12",
  "keyReference": "backup-key-reference"
}
~~~

Đây là **metadata minh họa**, không có nghĩa mọi engine có global log position hoặc timestamp tương tự. Manifest cần giúp trả lời: đã chụp ở đâu, theo consistency contract nào, cần những files/logs/schema/keys gì và restore được tới mốc nào.

**CompletedAt** chỉ là thời gian kết thúc công việc tạo backup, không mặc nhiên là recovery point.

## 13. WAL, oplog, commitlog và PITR

**Point-in-Time Recovery (PITR)** là khả năng phục hồi tới một thời điểm/commit position được engine hỗ trợ, thường kết hợp baseline snapshot và transaction/change logs phù hợp.

~~~mermaid
flowchart LR
    B["Base snapshot at S"] --> R["Restore base image"]
    L["Continuous log archive S..T"] --> P["Replay to target T"]
    R --> P
    P --> D[("Recovered state at T")]
~~~

Điều kiện:

- Log có đủ và liên tục từ snapshot checkpoint tới target.
- Thứ tự/commit semantics phù hợp với engine; không bỏ lỗ hổng log.
- Có metadata mapping log/transaction ID và target.
- Snapshot tương thích với log segment/version.
- Retention dài hơn mọi độ trễ upload/restore cần thiết.
- Có encryption keys, permissions, storage và công cụ replay.
- Khôi phục không replay những events sau target.

**Không lấy một CDC topic bất kỳ để thay WAL/PITR log.** CDC có thể chỉ chứa ảnh sau thao tác, thiếu transaction boundaries hoặc không đáp ứng semantics của crash recovery.

## 14. RPO và RTO: biến “backup tốt” thành mục tiêu đo được

**RPO**: thời lượng dữ liệu được phép mất tính từ sự cố tới recovery point bảo đảm.

**RTO**: thời gian mục tiêu để dịch vụ đạt trạng thái hoạt động theo yêu cầu sau sự cố.

Ví dụ:

~~~text
Incident time: 12:00
Latest verified recovery point: 11:50
Service usable again: 12:42

Observed data-loss window: 10 minutes
Observed recovery duration: 42 minutes
~~~

Nếu RPO mục tiêu là 5 phút, việc có daily backup là không đủ trừ khi có log/PITR hoặc cơ chế khác thỏa yêu cầu. Nếu RTO mục tiêu là 30 phút, một backup rất đầy đủ nhưng restore/index rebuild mất 7 giờ cũng không đạt.

### 14.1. “Có backup mỗi giờ” không nhất thiết RPO một giờ

Backup chạy 01:00 nhưng kết thúc 01:45 với consistency cut tại 01:00; nếu backup sau bị lỗi, recovery point có thể còn cũ hơn. Cần đo **last successfully restorable point**, độ trễ chuyển bản sao sang storage độc lập, và verify trạng thái log chain.

## 15. Tính toán sơ bộ dung lượng, thời gian và ngân sách

Giả định dữ liệu 8 TiB, throughput restore hiệu dụng 400 MiB/s, bỏ qua overhead:

\[
T_{\mathrm{transfer}}
=\frac{8\times 1024\times1024\ \mathrm{MiB}}{400\ \mathrm{MiB/s}}
\approx20.972\ \mathrm{s}
\approx5{,}8\ \mathrm{giờ}.
\]

Đây **chỉ là lower-bound thô cho transfer**, chưa tính API calls, decrypt, unpack, log replay, index rebuild, data validation, replicas resync và application warm-up. Tốc độ từ provider docs không tự bằng throughput restore thực tế ở topology của bạn.

Một logical export 8 TiB có thể phải đọc hàng tỷ records; một physical snapshot copy có thể dùng changed blocks, nhưng vẫn phải chuyển đủ dữ liệu để restore vào nơi mới. Đo **restore time**, không chỉ backup creation time.

### 15.1. Một ngân sách RTO thực tế gồm nhiều pha

~~~text
Incident detection + decision
+ provision target environment
+ acquire backup and encryption keys
+ restore base data
+ replay logs to target
+ rebuild indexes / replicas if needed
+ validate consistency and business invariants
+ switch routing and warm critical paths
= end-to-end recovery time
~~~

RTO cần tính cả people/process time, nhất là nếu approval/access phải xử lý trong khẩn cấp.

## 16. Recovery granularity: khôi phục gì, tới đâu?

Một backup policy phải trả lời:

- Restore toàn cluster hay một database/collection/table?
- Một tenant, một document, một key, một partition?
- Restore trạng thái hiện tại hay trước một delete/corruption?
- Có cần khôi phục các relationship/related aggregates cùng nhau?
- Có phải restore vào cluster tạm rồi selective copy?
- Có cần giữ order IDs, primary keys, indexes và TTL metadata?
- Đích có chấp nhận schema/version cũ hay phải migrate?

**Partial restore** làm tăng nguy cơ lẫn dữ liệu từ hai thời điểm. Ví dụ khôi phục riêng một Order từ hôm qua vào source hôm nay có thể phá inventory/payment invariants; phải qua domain reconciliation, không coi document backup là sự thật độc lập.

## 17. Logical export khi hệ vẫn đang ghi

Giả sử exporter đọc theo pages:

~~~text
Page 1 at 01:00:00: Orders O1..O100
Page 2 at 01:00:20: Orders O101..O200
Page 3 at 01:00:40: Orders O201..O300
~~~

Trong lúc đó người dùng liên tục tạo, sửa và xóa documents. Các tình huống:

- Record sửa sau khi exporter đã đọc → file chứa version cũ.
- Record tạo ở vùng keyspace đã quét → có thể bị bỏ.
- Key/sort order thay đổi → có thể lặp hoặc mất trong pagination.
- Record bị xóa trước khi đến lượt → có thể không xuất.
- Related collections được đọc tại hai mốc khác nhau.
- TTL expiration hoặc schema migration làm record đổi hình dạng.
- Driver scan retry gây duplicate page; snapshot cursor hết hiệu lực.

Không thể nói “đã quét đủ mọi page nên nhất quán”. Cần **consistent snapshot** hoặc **snapshot + change log handoff** với protocol xử lý overlaps/versions.

## 18. Snapshot + CDC: logical bootstrap có thể bắt kịp thay đổi

~~~mermaid
flowchart TD
    A["Establish source checkpoint S"] --> B["Read consistent snapshot if supported"]
    B --> C["Export IDs/versions"]
    C --> D["Replay changes since S"]
    D --> E["Catch up to target T"]
    E --> F["Validate and seal backup"]
~~~

Điểm khó: **gắn snapshot với log position S thực sự có nghĩa**. Một số connectors cung cấp snapshot+stream tích hợp; nếu tự viết, phải chứng minh không tạo gap và không replay sai thứ tự.

| Biến cố | Snapshot có thể thấy | Replay cần |
|---|---|---|
| Update trước lúc đọc key | State cũ hoặc mới | Xác định version |
| Update sau lúc đọc key | State cũ | Áp update mới |
| Insert đang quét | Có hoặc không | Dedup hoặc tạo record |
| Delete đang quét | Có thể chứa bản cũ | Tombstone |
| Nhiều updates cùng key | Một bản state | Full-state vs delta semantics |
| Shard rebalance | Cursor/routing đổi | Connector checkpoint semantics |

**CDC không lưu lịch sử vô hạn**. Nếu backup kéo dài quá retention và không có archive/log pinning, recovery chain có thể không đầy đủ.

## 19. Current-state backup khác history/event backup

Latest Order:

~~~json
{
  "orderId": "O1001",
  "status": "REFUNDED",
  "totalMinor": 240000,
  "sourceVersion": 14
}
~~~

không tự cho biết nó từng CONFIRMED lúc nào, giá gốc nào và REFUNDED ra sao. Báo cáo lịch sử có thể cần các facts:

~~~text
OrderCreated
OrderConfirmed
PaymentCaptured
RefundRequested
RefundCompleted
~~~

Một current-state export thích hợp cho read model hiện tại, nhưng không phải bản thay thế event store nếu business report/audit cần toàn bộ chuyển trạng thái. **Lựa chọn dữ liệu sao lưu dựa trên thứ phải khôi phục được**, không chỉ dễ xuất nhất.

## 20. Logical backup cần metadata ngoài document

Những thành phần thường cần ghi:

- Collections/tables/keyspaces và namespace mapping.
- Data types, binary/decimal/timestamp/UUID serialization.
- Primary/partition/clustering keys.
- Index definitions, uniqueness, collation.
- Validation schema, TTL/retention policies.
- Schema/data-transform version.
- Table/collection options.
- Permissions/roles cần khôi phục theo policy.
- ID generation/sequence state nếu ứng dụng phụ thuộc.
- CDC/checkpoint/log reference.
- Encryption key references.
- Counts/bytes/checksums, producer version, backup scope/cutoff.

Nếu import documents nhưng quên indexes/TTL, hệ có thể chậm hoặc giữ dữ liệu lâu hơn chính sách. Không tự import raw production credentials vào test cluster; quyền và secrets phải được cấp lại theo môi trường.

## 21. Logical data type fidelity

Chuyển NoSQL documents sang JSON text có thể mất:

- 64-bit integer precision nếu đi qua JS Number.
- Decimal/currency precision nếu dùng floating point.
- Binary subtype/UUID/ObjectId.
- Timestamp precision/timezone.
- Missing field so với explicit null.
- Array order/collation.
- TTL absolute expiration vs relative duration.
- Stable primary key, schema metadata.

Một ví dụ type-aware trung gian:

~~~json
{
  "orderId": "O1001",
  "amount": "9007199254740993",
  "amountEncoding": "int64-as-decimal-string",
  "createdAt": "2026-11-14T01:00:00.123Z",
  "sourceVersion": 12
}
~~~

Chỉ là **minh họa về giữ precision**, không phải schema bắt buộc. Với engine có logical export format giữ types, nên dùng công cụ tương thích và verify restore fidelity.

## 22. Backup phạm vi một tenant: dependency closure

Một doanh nghiệp muốn export riêng tenant t01:

~~~text
tenant t01
  -> Orders
  -> OrderItems
  -> CustomerProfiles
  -> Attachments references
  -> Shared catalog references
~~~

Cần xét:

- Order có payment reference ở hệ khác không?
- Global catalog có version nào tương ứng snapshot?
- Có cross-tenant shared objects/constraints hợp lệ không?
- Search/analytics collection có dữ liệu tenant khác không?
- Export query có server-derived tenant scope trên mọi page không?
- Key collisions khi restore vào cluster mới có thể xảy ra không?

Một phần backup có thể thiếu dependency của business invariant. **Partial restore cần kế hoạch merge/reconcile**, không chỉ đổi string tenant ID trong records.

## 23. Logical backup tải nặng lên NoSQL source

Một full logical scan có thể:

- Tiêu read IOPS/RCU, CPU và network.
- Đẩy dữ liệu hot ra khỏi cache.
- Giữ MVCC old versions hoặc snapshot resources lâu.
- Tạo large cursor/batch memory.
- Tăng replication lag hoặc làm hot partitions chậm.
- Kéo dài CDC/log retention requirements.
- Tạo retry amplification khi bị throttling.
- Gây egress cost lớn.

Cần giới hạn **read ops/s, bytes/s, per-shard concurrency**, backlog, retry budgets và có pause/resume. Backup không được đẩy transaction source vượt p99/error SLO; backup chạy đêm vẫn có thể trùng compaction/repair jobs.

## 24. Logical restore: import phải phục hồi semantics

Một pipeline:

~~~text
Provision compatible target
 -> validate manifest, checksums, keys, scope
 -> create collections/tables and required policies
 -> import records with correct types and stable IDs
 -> build/verify indexes and constraints
 -> restore related metadata/objects
 -> apply recovery log if needed
 -> reconcile counts, hashes, business invariants
 -> switch traffic only after complete validation
~~~

Index build trước/sau import có trade-off: trước bảo vệ uniqueness nhưng tốn insert cost; sau có thể nhanh hơn nhưng phải xử lý duplicates và xác minh constraints. Phụ thuộc engine. Không skip mọi invalid record rồi coi restore complete; cần lưu IDs/lý do và repair plan.

## 25. Java pseudocode: export pages có checkpoint nhưng chưa tự nhất quán

~~~java
import java.util.List;

public interface SnapshotReader {
    Page readNext(String snapshotRef, String cursor, int maxItems)
            throws Exception;
    record Row(String id, long version, byte[] encoded) {}
    record Page(List<Row> rows, String nextCursor, boolean done) {}
}

public interface BackupSink {
    void writeBatch(String backupId, int batchNo,
                    List<SnapshotReader.Row> rows) throws Exception;
    void checkpoint(String backupId, int batchNo,
                    String nextCursor) throws Exception;
}

public final class LogicalBackupJob {
    private final SnapshotReader reader;
    private final BackupSink sink;

    public LogicalBackupJob(SnapshotReader reader, BackupSink sink) {
        this.reader = reader;
        this.sink = sink;
    }

    public void export(String backupId, String snapshotRef,
                       String startCursor) throws Exception {
        String cursor = startCursor;
        int batch = 0;
        while (true) {
            SnapshotReader.Page page =
                reader.readNext(snapshotRef, cursor, 500);
            sink.writeBatch(backupId, batch, page.rows());
            // Checkpoint after durable batch write only.
            sink.checkpoint(backupId, batch, page.nextCursor());
            if (page.done()) break;
            cursor = page.nextCursor();
            batch++;
        }
    }
}
~~~

Mã này **chỉ minh họa pagination/checkpoint**, không tạo snapshot consistency. Nó chưa có engine-specific snapshot acquisition/expiration, stable cursor, atomicity giữa artifact write và checkpoint, retry/idempotent batch identity, byte limits, throttling, metadata, encryption, log handoff và validation.

**Xuất hết pages không tự chứng minh bản sao có thể dùng để khôi phục chính xác.**

## 26. Physical backup: file copy, filesystem snapshot và native backup

Có ít nhất ba cách sao lưu tầng vật lý:

1. **File copy khi DB đang chạy:** bắt mỗi file ở một thời điểm khác; **không mặc định restore được**.
2. **Filesystem/storage snapshot:** lưu image ở một điểm theo phạm vi volume/filesystem được hỗ trợ.
3. **Engine-native physical backup:** công cụ database/provider phối hợp checkpoint, log, metadata và snapshot files.

Một filesystem snapshot có thể atomic **trong một volume**, nhưng hệ có WAL ở volume A và data files ở volume B cần **coordinated multi-volume snapshot** hoặc protocol engine phù hợp.

### 26.1. Copy-on-write không miễn phí

COW snapshot thường giữ phiên bản trước của blocks khi source tiếp tục ghi, tạo chi phí:

- Changed-block storage và metadata.
- Write amplification.
- I/O latency, cleanup.
- Retention/storage headroom.
- Rủi ro snapshot failure nếu hết dung lượng.

Lệnh tạo snapshot hoàn tất nhanh **không đồng nghĩa chi phí copy/retention bằng không**. Cần đo storage growth và ảnh hưởng foreground I/O.

## 27. Checkpoint, flush và snapshot scope

Database có thể giữ data trong memory trước khi flush, nhưng bảo đảm durability còn phụ thuộc WAL/commitlog. Một công cụ physical backup được hỗ trợ có thể:

- Trigger checkpoint/flush theo API engine.
- Tạm ngưng writes hoặc lock ở mức cần thiết và giới hạn thời gian.
- Đảm bảo WAL/log nằm trong recovery chain.
- Đóng băng group volumes đúng thứ tự.
- Lưu recovery checkpoint/log position.
- Đảm bảo data files ở state engine chấp nhận.
- Giải phóng locks/quiescence cả khi backup lỗi.

Không suy một lệnh `sync` hoặc volume snapshot thủ công đủ để gọi là DB-consistent. Một checkpoint có thể giảm log recovery nhưng không tự đồng bộ mọi shard.

## 28. Multi-volume physical snapshot và write ordering

Ví dụ:

~~~text
Volume A: WAL/commitlog
Volume B: data files
Volume C: secondary index files

At time T:
  WAL describes transaction X.
  Data B contains only some updates.
  Index C still has an older view.
~~~

Chụp A lúc T, B lúc T+5s và C lúc T+20s có thể tạo image không được engine hỗ trợ recovery. Một vài engine có thể rebuild index, nhưng phải dựa vào tài liệu, không đoán.

Câu hỏi:

1. Engine có hỗ trợ snapshot layout multi-volume này không?
2. Có atomic group snapshot capability?
3. Có cần DB-level freeze/checkpoint?
4. WAL retention và restore checkpoint được giữ ở đâu?
5. Volumes có cùng region/zone, backup permissions và encryption?
6. Restore cần permissions/paths/owner gì?
7. Mất một volume trong chain ảnh hưởng recovery thế nào?

Khi chuyển WAL sang disk riêng, **backup procedure cũng phải đổi**.

## 29. Physical incremental: dependency chain và retention

Một chain:

~~~text
Base image B0
 -> changed blocks I1
 -> changed blocks I2
 -> changed blocks I3

Restore target after I3:
 B0 + I1 + I2 + I3
~~~

Rủi ro:

- Corrupt I2 khiến recovery target sau I3 không đầy đủ.
- Xóa B0 phá incrementals còn tham chiếu.
- Retention/lifecycle xóa nhầm manifest/chunks.
- Một log segment PITR nằm ngoài retention.
- Khóa giải mã backup cũ bị revoke.
- Replication bản backup cross-region chưa hoàn tất khi primary region mất.

Retention phải giữ **dependency closure** cho mọi mốc restore được cam kết, không chỉ “30 files gần nhất”.

## 30. Physical restore không chỉ là sao chép file trở lại

~~~text
Provision compatible engine/version/topology
 -> verify manifest, files, key access
 -> restore images to supported volumes/paths
 -> restore WAL/log/metadata per engine protocol
 -> start isolated recovery
 -> engine crash recovery
 -> verify schema, node/cluster health
 -> validate business records, indexes, replication
 -> configure security, CDC, backup and routing
 -> cut over only after checks
~~~

Cần xét file owner/permissions, storage format, CPU architecture, encryption keys, cluster/node IDs, replica membership, token/shard assignment, version compatibility, secrets và external attachments.

**Không khởi chạy restored image song song với nguồn trong cùng cluster bằng duplicated node identity**. Phải có quy trình dựng cluster mới hoặc replace-node được engine hỗ trợ.

## 31. Online vs offline backup

| Thuộc tính | Online | Offline |
|---|---|---|
| Hệ tiếp tục ghi | Có thể, theo capability | Thường cần dừng write/process |
| Cần coordination | Cao | Ít hơn nếu toàn scope thật sự quiescent |
| Availability | Ít downtime hơn nhưng thêm tải | Có maintenance/downtime |
| Consistency | Dựa vào engine protocol | Phải bảo đảm đã flush/stop đúng |
| Multi-shard | Vẫn cần distributed cut | Dừng một node không đủ |
| RPO/RTO | Có thể hỗ trợ thường xuyên | Tùy lịch dừng và copy |

Offline snapshot của một replica **không đồng nghĩa toàn ứng dụng đã ngừng ghi**. Node đó có thể lag so với primary, hoặc broker/service bên ngoài vẫn thay đổi. Cần gắn backup point vào contract khôi phục.

## 32. Backup từ replica: giảm tải primary nhưng có thể cũ hơn

Backup từ replica/secondary đôi khi giảm tải primary, nhưng cần xác nhận:

- Replica đã áp commits đến checkpoint mong muốn chưa?
- Có đang initial sync, repair hoặc lag lớn?
- Snapshot làm replica lag tăng thêm không?
- Nếu primary failover, backup job sẽ chuyển node ra sao?
- WAL/oplog history ở replica còn đủ?
- Recovery point cũ hơn primary có đạt RPO không?
- Replica ở AZ/region phù hợp và backup key có quyền không?

Secondary lag 90 giây có thể tạo image **hợp lệ theo trạng thái secondary** nhưng cũ hơn dữ liệu đã ACK ở primary. Đừng suy recovery point từ thời điểm nhấn nút snapshot.

## 33. Backup coordinator của cụm phân tán

~~~mermaid
flowchart TD
    C["Backup coordinator"] --> H["Discover topology and health"]
    H --> CUT["Establish supported cut/checkpoint"]
    CUT --> A["Shard/node A"]
    CUT --> B["Shard/node B"]
    CUT --> D["Shard/node C"]
    A --> M["Manifest + checksums"]
    B --> M
    D --> M
    M --> S[("Encrypted independent storage")]
    S --> V["Verify chain and recoverability"]
~~~

Coordinator cần xử lý: node failure giữa chừng, topology thay đổi, partial completion, idempotent retries và log retention. Chỉ đánh dấu **FULL BACKUP COMPLETE** khi mọi artifact bắt buộc có mặt và metadata khớp.

Nếu 8/9 shards backup thành công, job có thể giữ phần đã chụp để resume nhưng **không được công bố là recovery point toàn cluster**.

## 34. Các cấp độ kiểm chứng backup

1. **Job completed:** process kết thúc không lỗi.
2. **Files readable:** artifacts tải, giải nén, giải mã được.
3. **Chain complete:** base/incrementals/logs/metadata không thiếu.
4. **Engine restore succeeds:** phiên bản tương thích phục hồi được.
5. **Business state valid:** records/invariants/queries đúng.
6. **RPO/RTO met:** phục hồi đúng mốc và thời gian yêu cầu.

Checksum giúp phát hiện byte corruption. Cryptographic hashes/signatures có thể hỗ trợ integrity/provenance theo policy. Nhưng **checksum đúng không chứng minh tính nhất quán giao dịch**. Nếu attacker có quyền sửa cả backup lẫn manifest hash, cần bảo vệ bằng vùng lưu/bằng chứng độc lập.

## 35. Restore rehearsal: kiểm chứng bằng restore thật

Một diễn tập:

~~~text
Choose recovery target T.
Provision isolated compatible engine/topology.
Retrieve backup chain, metadata and decryption keys.
Restore base image, replay logs to T.
Validate engine health, indexes, replicas, auth.
Run business reads, conditional writes and reconciliation.
Measure end-to-end recovery duration.
Store evidence, failure reasons and follow-up owners.
Securely destroy/retain isolated environment by policy.
~~~

Đo time-to-provision, transfer throughput, missing chunks, decrypt issues, log replay, actual recovery point, index rebuild, replication catch-up và business readiness.

Một backup được tạo hằng ngày nhưng chưa từng restore **chưa có bằng chứng thỏa RTO hoặc business recovery correctness**.

## 36. MongoDB: mongodump, oplog và coordinated snapshots

MongoDB có những hướng backup tùy deployment:

- **Logical:** `mongodump` và `mongorestore` hoặc công cụ provider, với phạm vi database/collection và metadata được hỗ trợ.
- **Logical + changes:** một số workflow replica set có thể kết hợp oplog option/replay trong điều kiện hỗ trợ; phải xác minh giới hạn của `--oplog`, version, DDL và sharded topology.
- **Physical:** storage snapshot/backup agent phối hợp WiredTiger, log và topology.
- **Managed:** snapshot/PITR theo recovery window và nhất quán do dịch vụ cam kết.

Không được giả định:

1. `mongodump` khi ứng dụng liên tục ghi sẽ tạo một global transaction snapshot cho tất cả collections.
2. Oplog không bao giờ hết khi logical dump kéo dài.
3. Replica set backup tương đương full sharded cluster backup.
4. Copy thư mục WiredTiger đang hoạt động là một backup hợp lệ.
5. Dump đã chứa cluster config, secrets, users/roles và mọi metadata cần để DR.
6. Partial collection restore không cần business reconciliation.

Một ví dụ **cú pháp tham khảo để hình dung công cụ**, chưa phải production runbook:

~~~text
mongodump --uri="<uri-provided-securely>" --out="/isolated/backup"
mongorestore --uri="<isolated-target-uri>" "/isolated/backup"
~~~

Không ghi credentials vào command history/logs; dùng cơ chế xác thực bảo vệ phù hợp. Những lệnh đơn giản này **không tự bảo đảm snapshot consistency, encryption, verification hoặc PITR**.

## 37. Cassandra: SSTable snapshots theo node

Apache Cassandra có những workflow chụp SSTable snapshots, thường dùng `nodetool snapshot` theo phiên bản tương ứng. Tuy nhiên:

- Một snapshot node **không tự là global consistent cut**.
- Cần schema/keyspace, token/rack/DC topology, replication factors và data placement.
- Memtable/flush và commitlog semantics phải theo snapshot tool.
- Một replica không mặc nhiên giữ mọi writes đã ACK ở toàn cluster.
- Các node snapshot tại những mốc khác nhau có thể không đồng nhất khi writes liên tục.
- Restore SSTables có cơ chế ingest/refresh/streaming riêng; không chỉ copy files vào cluster sống.
- Repair, hinted handoff, tombstones/TTL và consistency level ảnh hưởng kết quả khôi phục.
- Node-replacement khác dựng cluster mới từ backup.

Wide-column datasets lớn có thể khiến logical full scan tốn nguồn rất nhiều; snapshot vật lý đáng cân nhắc, nhưng **phải thiết kế rõ completeness và read/write consistency trên các replicas**.

## 38. ScyllaDB: đừng giả định identical với Cassandra

ScyllaDB có mô hình wide-column và một số khái niệm SSTable/compaction, nhưng **công cụ backup, API, format và restore protocol có thể khác theo sản phẩm/phiên bản**.

Cần xác định:

- Native snapshot/backup tool đang hỗ trợ.
- Node/shard/token layout và metadata để dựng cluster.
- Có incremental/PITR không theo edition/service thực tế.
- Ảnh hưởng snapshot/copy lên disk I/O và OLTP p99.
- TTL/tombstone, compaction và replication.
- Restore vào cluster mới hay cluster đang hoạt động.
- Schema, encryption keys, access privileges.
- Repair/streaming/reconciliation sau restore.

Không sử dụng lệnh của Cassandra trên ScyllaDB một cách máy móc. Phải thử restore theo phiên bản đang vận hành.

## 39. DynamoDB: on-demand backups, PITR và export

Với DynamoDB managed service, người dùng không tự copy server data files. Các hướng gồm:

- On-demand table backup và restore theo API provider.
- PITR khi đã bật và target còn trong recovery window.
- Export to S3 hoặc phương thức export được hỗ trợ, phù hợp workflow dữ liệu.
- Streams/event archive khi cần xây lại derived read models, không thay backup/PITR.

Câu hỏi:

1. PITR có bật trước sự cố, recovery window còn target?
2. Restore tạo table mới hay thay thế table hiện hữu theo API?
3. Indexes, TTL, Streams, IAM, policies, tags và capacity settings nào phải cấu hình lại?
4. Backup/export giữ type/metadata gì?
5. KMS/IAM/S3 permissions cho artifact và restore?
6. Global tables/multi-region cần reconciliation hay rebuild replication?
7. Application routing và endpoints đổi thế nào khi cutover?
8. Hot partition/import throughput ảnh hưởng RTO ra sao?

**DynamoDB Streams retention không đồng nghĩa lưu trữ lịch sử vô hạn**, và export-to-object-storage không phải transaction log mặc định cho PITR.

## 40. Redis: RDB, AOF và chính sách theo vai trò

Phải phân biệt Redis là cache hay authoritative datastore.

- Nếu chỉ là **cache có thể dựng lại**, backup NoSQL durable source và warm-up plan có thể quan trọng hơn backup mọi cache keys.
- Nếu Redis giữ state không thể mất, phải thiết kế persistence/backup/replication theo business RPO.

Những khái niệm:

- **RDB:** point-in-time snapshot theo cơ chế Redis.
- **AOF:** lưu operations theo persistence policy, có thể hỗ trợ restart/recovery nhưng **không tự là immutable, independent backup**.
- **Replication:** lỗi xóa/sửa nhầm có thể propagate.
- **Offsite backup:** copy/verify files ở nơi độc lập với instance.

TTL/expire có thể làm keys đã restore khác kỳ vọng theo elapsed time/expiry semantics. Nếu Redis lưu idempotency tokens, distributed locks hoặc session state, khôi phục snapshot cũ có thể tạo race/replay nguy hiểm; cần expiration/fencing/reconciliation theo contract.

## 41. Elasticsearch/OpenSearch: native snapshots cho read models

Với search engines, **copy trực tiếp live shard directories** thường không phải backup path được hỗ trợ. Native snapshot/repository mechanisms điều phối index/segment metadata.

Cần xem:

- Index/shard/cluster state và snapshot completeness.
- Repository IAM, encryption, retention.
- Snapshot task status, partial failures.
- Templates, aliases, ingest pipeline, security metadata theo version.
- Index name collisions khi restore vào same cluster.
- Refresh/visibility, reindex và search query correctness.
- CDC lag so với NoSQL source.

Search index có thể khôi phục từ snapshot hoặc **rebuild từ authoritative NoSQL + CDC**. Nếu chọn rebuild, phải có replay nguồn đầy đủ, áp tombstones, tenant policies và giới hạn source read QPS.

## 42. HBase/Couchbase và các hệ NoSQL khác: nguyên tắc chuyển giao

Với HBase, Couchbase, graph databases hay managed document services khác, không suy sao lưu mặc định từ tên “NoSQL”. Cần điều tra:

- Native backup/snapshot API và consistency scope.
- Storage engine file format và transaction log.
- Sharding/partitioning/replication behavior.
- Cross-node coordination, online backup requirements.
- Full/incremental/point-in-time support.
- Index metadata, schema, users/roles và permissions.
- Limits on import/export/restore versions.
- Operational overhead, source I/O và backup cost.
- Vendor support khi backup failed hoặc storage corrupted.

Một lớp abstraction “backupAll()” không nên che giấu rằng engine A hỗ trợ cluster snapshot có cutoff còn engine B chỉ hỗ trợ per-node filesystem snapshots. **Khả năng khôi phục phải được ghi cụ thể theo engine và topology**.

## 43. Chọn chiến lược theo loại dữ liệu

| Data class | Nguồn phục hồi | Hướng sao lưu đáng cân nhắc |
|---|---|---|
| Transaction Orders | Authoritative NoSQL, outbox | Native consistent backup + PITR/log nếu cần |
| Product catalog | Source NoSQL | Logical export hoặc physical backup tùy RTO |
| Search index | Derived from catalog/orders | Snapshot index hoặc rebuild + CDC |
| Redis cache | Rebuildable | Backup source + bounded warm-up |
| Event store | Durable event log/archive | Log retention, copies, schema/version metadata |
| Reporting aggregates | Derived from immutable facts | Backup facts; rebuild aggregate hoặc snapshot |
| User uploaded files | Object storage | Object versioning/backups + DB reference reconciliation |
| Audit evidence | Tamper-resistant store | Immutability, controlled retention/keys |
| Config/secrets | IaC + secret manager | Versioned config, encrypted key recovery |

Một hệ thống có thể cần **nhiều chiến lược cùng lúc**. Điều quan trọng là các recovery points và dependencies được liên kết; không phải ép mọi store về cùng một công cụ.

## 44. Backup phải độc lập với failure domain của database

Backup nằm cùng disk/host/account với nguồn có thể bị mất bởi disk failure, xóa nhầm, ransomware, region outage hoặc credential admin bị chiếm. Nguyên tắc **3-2-1** có thể dùng để suy nghĩ về nhiều bản sao và bản ngoài failure domain; không nhất thiết áp máy móc vào mọi cloud-native setup.

Các guardrails:

- Separate account/project/credential và IAM.
- Offsite/cross-region copy theo DR policy.
- Object versioning, immutability/WORM khi phù hợp.
- Backup job không có quyền xóa toàn bộ backup.
- Audit cho list/download/decrypt/delete/restore.
- Retention đủ cho base, incremental và PITR log chain.
- Kiểm tra cross-region copy complete và decrypt key available.

**Replication của backup đang chạy không đồng nghĩa đã có bản offsite khôi phục được.** Hãy theo dõi latest complete recovery point tại cả primary và DR storage.

## 45. Encryption, KMS và quyền của backup artifacts

Backup có thể chứa toàn bộ dữ liệu lịch sử/PII, nên quyền bảo vệ có thể phải chặt hơn API point lookup:

1. TLS cho đường truyền/backup API.
2. Encryption at rest cho objects/volumes.
3. Key manager/KMS policies và audit decrypt.
4. Tách download permissions khỏi decrypt privileges.
5. Rotation/revocation và hỗ trợ đọc các bản backup đời cũ hợp lệ.
6. JIT/approval cho privileged restore.
7. Không ghi plaintext secrets vào manifests/log/CLI arguments.
8. DR key availability khi primary region/identity service lỗi.
9. Retention/deletion đúng privacy/legal policy.

Một bản copy ở region B có thể vô dụng nếu decryption key chỉ hoạt động tại region A đã mất. Restore drill phải thử **data + key + permission + target** cùng nhau.

## 46. Backup và privacy deletion: không hồi sinh dữ liệu đã xóa

~~~text
T0: Snapshot contains customer profile.
T1: Authorized privacy deletion completed.
T2: Incident triggers restore from T0.
T3: Without suppression, old profile reappears.
~~~

Cần có policy cho deletion events/tombstones, source of truth về privacy requests và bước suppression/reconciliation **trước khi mở restored service**. Backup retention và legal hold có thể có quy định riêng; không suy mọi deletion đồng nghĩa phải xóa tức khắc mọi encrypted historical backup trong mọi hệ.

Với derived stores/search/cache, cũng phải áp deletion propagation khi rebuild. **Restore về state cũ không phải giấy phép phục vụ công khai tất cả dữ liệu cũ.**

## 47. Metrics giám sát backup và khả năng restore

| Metric | Câu hỏi |
|---|---|
| Latest successful backup | Job gần nhất chạy thành công? |
| Latest verified restorable point | Thực sự phục hồi được tới mốc nào? |
| Last restore drill duration | RTO đo thực tế bao lâu? |
| Backup age/retention headroom | Có vượt RPO hoặc thiếu logs? |
| Artifact checksums/verification | Bytes/chunks có integrity không? |
| Incremental chain completeness | Có mất dependency không? |
| Partial shard/node counts | Backup có đủ scope không? |
| Snapshot COW storage growth | Có gây áp lực capacity không? |
| Source read IOPS/CPU/p99 | Backup có gây hại OLTP không? |
| Replica/CDC lag | Backup có làm recovery point cũ đi không? |
| Decrypt/access failures | Có thể sử dụng key và artifact không? |
| Cross-region copy lag | DR copy đã sẵn sàng chưa? |
| Restore business mismatch count | Phục hồi có đúng invariant không? |
| Security audit events | Có download/delete ngoài policy không? |

Không đồng nhất **backup job success** với **backup verified restorable**. Alert quan trọng nên liên quan latest recoverable point age và chain health, không chỉ lệnh backup thất bại.

## 48. Scheduling và giới hạn tốc độ sao lưu

Backup có thể tiêu read units, disk, CPU, memory, network egress và làm cache/compaction bị ảnh hưởng. Một lịch ban đêm vẫn có thể trùng ETL, repair, TTL cleanup hoặc backup khác.

Cần đặt:

- Read ops/s và bytes/s.
- Per-node/partition concurrency.
- Batch/page size, retry budget và backoff.
- Disk/volume snapshot growth limit.
- Background job priority và ability to pause.
- Stop threshold theo OLTP p99, throttle, disk free, replication lag.
- Log retention headroom để pause không làm mất recovery chain.

Khi source có dấu hiệu overload, giảm tốc/pause an toàn; nhưng phải theo dõi **RPO trade-off** nếu backup chậm lại quá lâu.

## 49. Backup failure matrix

| Sự cố | Vì sao quan trọng | Hướng xử lý |
|---|---|---|
| Thiếu một shard | Không đủ full-cluster image | Không mark complete; retry/repair |
| WAL/oplog gap | Không thể PITR qua khoảng đó | Tìm archive/backup khác |
| Checksum mismatch | Corrupt artifact | Lấy verified copy khác |
| Key decrypt denied | Backup không thể dùng | Khắc phục IAM/KMS đúng policy |
| Replica backup lag | RPO thực tế cũ hơn | Chọn nguồn/cut hợp lệ |
| Incremental base bị xóa | Broken chain | Giữ dependency/đổi restore target |
| Backup làm DB quá tải | API SLO xấu | Throttle/pause source reads |
| Export pagination gap | Missing/duplicate record | Snapshot/CDC protocol, retry |
| Schema/index thiếu | Restore sai hoặc rất chậm | Khôi phục/rebuild metadata |
| DR copy incomplete | Region failover không có đủ backup | Theo dõi/đẩy copy, không công bố ready |
| Restore test thất bại | Không có bằng chứng recoverability | Mở incident/task sửa workflow |
| Deleted PII hồi sinh | Privacy risk | Quarantine và deletion reconciliation |

**Lỗi thiếu log không chữa bằng tăng import workers; lỗi thiếu KMS key không chữa bằng bỏ mã hóa.** Phân loại đúng nguyên nhân trước khi sửa.

## 50. Runbook A — Xóa nhầm collection khi source vẫn nhận writes

Giả sử collection Orders bị xóa lúc 11:10. Full backup tạo lúc 00:00, log/PITR còn tới 11:08. Sau 11:08 có những writes đã ACK.

Quy trình:

1. **Contain:** ngăn destructive command tiếp theo, giữ audit và log evidence.
2. Xác định scope xóa: collection, tenant, region, derived stores.
3. Xác minh backup chain, log range và recovery target trước lệnh xóa.
4. Tính RPO và **writes sau target có thể bị thiếu**.
5. Dựng target cluster cô lập, đúng version/schema/keys.
6. Restore full backup và replay log tới target được hỗ trợ.
7. Reconcile Orders, items, inventory reservations, payment references.
8. Xác minh idempotency/outbox events/unknown outcomes.
9. Áp privacy suppression cho dữ liệu đã bị xóa hợp lệ.
10. Chọn cutover/routing và giải pháp hòa nhập writes mới theo domain policy.
11. Giám sát p99, errors, replication, CDC và business outcomes.
12. Ghi actual RPO/RTO, sự cố và kiểm soát ngăn xóa nhầm.

Không restore đè lên production đang sống một cách vội vàng nếu còn writes sau recovery target; việc đó có thể phá thêm dữ liệu hợp lệ.

## 51. Runbook B — Một node NoSQL hỏng disk

Giả sử một node Cassandra-like mất disk, các replicas khác vẫn khỏe.

1. Xác định **node-replacement** hay full-cluster disaster.
2. Kiểm tra healthy replicas, consistency/quorum và source of truth.
3. Xem rebuilding từ peers có an toàn/nhanh hơn restore image không.
4. Nếu dùng physical backup, theo replace-node/bootstrap protocol của engine.
5. Không tạo duplicated node ID/token ownership gây xung đột.
6. Khôi phục disk permissions, certificates, encryption keys.
7. Chạy streaming/repair/anti-entropy theo yêu cầu.
8. Theo dõi disk, compaction, replication và foreground p99.
9. Verify records/partition samples và application queries.
10. Đưa node vào phục vụ có kiểm soát, cập nhật backup metadata.

Trong cụm replicated, restore từ backup **không phải lúc nào là đường phục hồi node tốt nhất**. Quyết định theo engine, replicas còn sống, RTO và khả năng giữ integrity.

## 52. Runbook C — Backup có nhưng restore chậm hơn RTO

Giả định:

~~~text
Backup size:             12 TiB
Effective transfer:      250 MiB/s
RTO target:              2 hours
~~~

Lower-bound data transfer:

\[
T\approx
\frac{12\times1024\times1024\ \mathrm{MiB}}
{250\ \mathrm{MiB/s}}
\approx 50.332\ \mathrm{s}
\approx 14\ \mathrm{giờ}.
\]

Đã vượt xa hai giờ dù chưa tính decrypt, log replay, index rebuild, resync, verify và routing.

Các hướng thiết kế:

- Native snapshot restore/fast cloning nếu có khả năng phù hợp.
- Storage/network/provisioning throughput cao hơn.
- Parallel restore theo phạm vi engine cho phép.
- Warm standby/DR replica **kèm backup độc lập**, không dùng replication thay backup.
- Ưu tiên phục hồi một số chức năng critical trước nếu business cho phép.
- Đảm bảo backup chain không làm chậm quá nhiều.
- Thực hiện restore drill và điều chỉnh kiến trúc/RTO mục tiêu sau risk review.

**Một RTO không khả thi về throughput phải được nhận diện trước incident.**

## 53. Runbook D — Restore engine chạy được nhưng dữ liệu sai

Tình huống:

~~~text
Backup job: SUCCESS
Restore engine: HEALTHY
Orders count: gần khớp nguồn
Some Orders have no OrderItems
Reserved inventory total does not match confirmed Orders
~~~

Điều tra:

1. Logical export có dùng cùng snapshot/read timestamp?
2. Có read-page gap/duplicate do concurrent updates không?
3. Shards có chụp cùng consistent cut?
4. WAL/oplog chain có đủ tới target?
5. Import có bỏ poison records hoặc type mismatch?
6. Related index/collection metadata có bị thiếu?
7. Có external payment/CDC/outbox effects ngoài cutoff?
8. TTL/deletes/tombstones có bị xử lý sai?
9. Counts/hashes có được so ở **cùng recovery point**?
10. Có thể restore lại từ target khác hoặc replay missing events?

Nếu không thể chứng minh invariants, mark restore **UNVERIFIED** và không tự cutover vì service đã Running. Tổng row count gần giống không bảo đảm đúng quan hệ nghiệp vụ.

## 54. Runbook E — Incremental/PITR chain bị thiếu

Ví dụ:

~~~text
Base B0: complete
Increment I1: complete
Increment I2: MISSING
Increment I3: complete
WAL archive after I3: present
~~~

Không thể tự bỏ I2 rồi ghép B0+I1+I3 và hy vọng image hợp lệ. Quy trình:

1. Xem manifest/dependency graph và provider backup semantics.
2. Đánh dấu recovery points phụ thuộc I2 là unavailable.
3. Tìm verified copies/mirrors/object versions của I2.
4. Kiểm tra encryption keys và byte integrity.
5. Nếu không có I2, xác định recovery point gần nhất **không phụ thuộc** I2.
6. Xem có synthetic full/new base đủ điều kiện không.
7. Đánh giá RPO bị vi phạm và báo chủ hệ thống.
8. Sửa retention/lifecycle policy, cross-region copy và alerts.
9. Diễn tập restore chain sau sửa.

Không thay đổi manifest để đánh dấu “complete” khi dependency thực sự thiếu.

## 55. Runbook F — Backup gây quá tải production

Giả sử:

~~~text
Checkout p99:        150 ms -> 850 ms
Backup scan reads:     0 -> 15.000 ops/s
Source disk await:     4 ms -> 90 ms
Driver retries:       1.1x -> 2.5x
Backup copied:        35% of planned dataset
~~~

Hành động:

1. Kiểm tra correlation với backup job, compaction/repair cùng lúc.
2. Bảo vệ user-facing SLO: giảm/pause backup có checkpoint và cancellation đúng.
3. Giảm retry storms, giữ idempotency cho writes.
4. Đo disk/network/cache pressure và per-partition source load.
5. Nếu backup snapshot pin log/history, theo dõi retention/space khi pause.
6. Không đánh dấu incomplete backup thành successful.
7. Xem source replica/offload/export service như phương án an toàn hơn.
8. Áp throttling đa chiều: reads/s, bytes/s, per-shard concurrency.
9. Resume dưới quota và monitor p99 + recovery-point age.
10. Cập nhật capacity plan, maintenance window và backup RPO alert.

**Giảm tốc backup để bảo vệ giao dịch có thể làm recovery point cũ hơn.** Cần quan sát cả hai rủi ro và có kế hoạch tăng capacity hoặc đổi chiến lược nếu không đồng thời đạt SLO/RPO.

## 56. Bảng quyết định: logical, physical hay phối hợp?

| Nhu cầu | Phương án đáng xem xét | Điều phải chứng minh |
|---|---|---|
| Restore toàn cụm nhiều TiB, RTO ngắn | Engine-native physical snapshots/PITR | Consistent scope, restore throughput, metadata |
| Xuất một collection để migrate | Logical export | Type fidelity, schema, snapshot consistency |
| Rebuild search index | Source snapshot + CDC hoặc index snapshot | Không mất update, tombstones, freshness |
| Quay lại trước destructive write | PITR/backup + log | Target cut và chain complete |
| Restore riêng một tenant | Logical selective hoặc restore cô lập rồi merge | Dependencies, auth, no key collisions |
| Mất toàn region | Offsite backup + keys + IaC + runbook | Actual DR RPO/RTO |
| Redis chỉ là cache | Durable source + warm-up | Source capacity/miss path |
| Redis giữ unique business state | Persistence + independent backup | Durability/restore correctness |
| Khôi phục historical reporting | Event/fact archive + schema | Full history, dedup |
| Chống ransomware | Immutable/isolated copy | Identity/delete separation |
| Thay một node replicated cluster | Replica resync hoặc engine-specific restore | Quorum, topology, integrity |

Một chiến lược tốt có thể **kết hợp physical baseline, incremental/log replay và logical export có chọn lọc**. Không ép mọi data class vào cùng một phương pháp.

Các câu hỏi trước khi chọn:

1. RPO và RTO bắt buộc là bao nhiêu?
2. Phải phục hồi toàn cluster hay chỉ collection/tenant?
3. Data size, write rate, shard count và active transactions?
4. Engine có native consistent snapshots và PITR không?
5. Restore cùng engine/version hay cần portability?
6. Có cần lịch sử events hay chỉ state hiện tại?
7. External effects/outbox/attachments có dependencies gì?
8. Offsite copy và decrypt keys sống sót khi mất region?
9. Restore drill gần nhất đạt mục tiêu chưa?

## 57. Bài tập A — Export nhiều collections khi writes vẫn diễn ra

Cho hệ:

~~~text
Orders/O1001 -> status CONFIRMED
OrderItems/O1001/1 -> SKU-A, qty=2

01:00 exporter reads Orders.
01:04 O1002 is created with two items.
01:07 exporter reads OrderItems.
01:10 backup completes.
~~~

Hãy:

1. Vì sao hai collections có thể không cùng snapshot?
2. Đề xuất consistent read timestamp hoặc snapshot+CDC handoff.
3. Checkpoint S phải có semantics gì?
4. Insert/update/delete trong lúc scan xử lý ra sao?
5. Retry một page có thể tạo duplicate thế nào?
6. Full-state và delta CDC khác nhau khi replay?
7. TTL/tombstone nào cần giữ?
8. Manifest cần schema version, source positions và checksum gì?
9. Giới hạn source read QPS/bytes/s ra sao?
10. Kiểm tra Order–OrderItems invariant khi restore thế nào?
11. Nếu backup dài hơn CDC retention, làm gì?
12. Khi nào job phải được đánh dấu INCOMPLETE?

## 58. Bài tập B — Tính RPO và RTO

Giả định:

~~~text
Full backup cut:          00:00
Incrementals:             mỗi 4 giờ
PITR log complete until:  14:55
Incident time:            15:02
Restore start:            15:20
Service usable:           16:35
~~~

Hãy:

1. Tính data-loss window nếu restore tới 14:55.
2. Tính observed recovery time từ lúc incident.
3. Với RPO=5 phút, mục tiêu đạt không?
4. Với RTO=90 phút, mục tiêu đạt không?
5. Job completed 00:30 có đồng nghĩa cut 00:30?
6. Nếu một log segment từ 12:01–12:04 mất, PITR 14:55 có còn bảo đảm?
7. Nếu incremental base bị mất, kiểm tra dependency chain thế nào?
8. Nếu DR copy chậm hơn primary, DR RPO có khác không?
9. Dashboard nên hiển thị latest **verified** recovery point thế nào?
10. Đề xuất restore drill đủ cả provisioning, replay và validation.

**Gợi ý:** 14:55 đến 15:02 là 7 phút; 15:02 đến 16:35 là 93 phút. Hai số đánh giá **hai chỉ tiêu khác nhau**.

## 59. Bài tập C — Snapshot ba shards không cùng thời điểm

Giả định:

~~~text
Shard A snapshot at 01:00:00
Shard B snapshot at 01:00:30
Shard C snapshot at 01:01:00

Transaction X begins 01:00:10
Transaction X commits 01:00:20
~~~

Yêu cầu:

1. Vì sao snapshots độc lập có thể thiếu global consistent cut?
2. Vì sao wall-clock timestamps chưa chắc phản ánh commit order?
3. Native coordinated backup có thể giúp gì?
4. Nếu chỉ có snapshots vật lý, cần log/metadata gì để recovery?
5. Nếu A chưa thấy X nhưng B đã thấy X, invariant nào có thể sai?
6. Nếu workflow là saga, pending state nào cần giữ?
7. Đặt recovery target T và điều kiện dữ liệu phải thỏa.
8. Dựng cluster restore cần versions, identities, keys nào?
9. Làm sao reconcile counts, versions và multi-shard effects?
10. Một shard không chụp xong, status job nên là gì?

## 60. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách đúng |
|---|---|---|
| “Ba replicas là ba backups” | Corruption/delete có thể nhân rộng | Independent backup |
| “Có snapshot là nhất quán” | Scope/cut không rõ | Consistency contract |
| “Copy folder là physical backup chuẩn” | Files không cùng trạng thái | Engine-supported backup |
| “Crash-consistent bằng application-consistent” | External effects/flows khác | Recovery protocol/reconcile |
| “Logical export luôn portable” | Types/schema/index khác | Type-preserving restore test |
| “Export đủ pages thì atomic” | Writes chen giữa pages | Snapshot+CDC/consistent read |
| “Full backup nghĩa là physical backup” | Hai trục độc lập | Full/incremental tách logic/physical |
| “Incremental là CDC log” | Changed blocks khác business events | Log semantics |
| “TTL rollback phục hồi data hết hạn” | Records đã bị xóa | Restore/replay |
| “Quorum replication tự cho global snapshot” | Shard cuts khác nhau | Coordinated snapshot |
| “Oplog/Streams có lịch sử vô hạn” | Retention có giới hạn | Backup/long-term archive |
| “Job success = restore được” | Có thể thiếu keys/chunks/schema | Restore rehearsal |
| “Checksum đúng = business đúng” | Chỉ kiểm tra byte integrity | Invariant reconciliation |
| “CompletedAt là recovery cutoff” | Job start/end không phải cut | Manifest/checkpoint |
| “Backup mỗi giờ bảo đảm RPO một giờ” | Jobs có thể fail, lag | Verified recovery point |
| “Backup nhanh thì restore nhanh” | Import/index/log/rebalance chậm | Actual RTO drill |
| “Chỉ backup DB là đủ” | Attachments/outbox/config/keys | Dependency inventory |
| “Secondary backup luôn mới” | Có thể replication lag | Checkpoint verification |
| “Thêm workers chắc restore nhanh hơn” | Disk/network/quota bị giới hạn | Benchmark bottleneck |
| “Partial document restore luôn an toàn” | Related invariants bị ảnh hưởng | Domain reconciliation |
| “Encrypted backup luôn usable” | Decrypt grants/key có thể mất | DR key test |
| “Cross-region copy tự luôn hoàn tất” | Copy asynchronous có lag | Verify remote chain |
| “Archive cũ restore không có privacy risk” | Deleted PII có thể hồi sinh | Suppression/retention |
| “Search snapshot thay source backup” | Search eventual/derived | Authoritative source |
| “Redis AOF là immutable backup” | Log có thể corrupt/xóa cùng nguồn | Protected independent copy |
| “Một node snapshot đủ toàn Cassandra cluster” | Node/replica scope | Coordinated backup |

## 61. Câu hỏi tự kiểm tra

1. Logical backup khác physical backup ở tầng dữ liệu nào?
2. Full, incremental và differential thuộc trục phân loại nào?
3. Vì sao replication không thay backup?
4. RPO khác RTO ở đâu?
5. Recovery point khác backup completion time thế nào?
6. Crash-consistent snapshot cần những điều kiện nào?
7. Tại sao multi-volume snapshots có thể không hợp lệ?
8. Transaction-consistent khác application-consistent ra sao?
9. Consistent cut liên quan causal dependencies thế nào?
10. Vì sao mỗi shard snapshot riêng chưa là global snapshot?
11. Logical scan có thể bỏ record khi concurrent writes ra sao?
12. Snapshot+CDC handoff cần checkpoint gì?
13. Deletes, TTL và tombstones được xử lý thế nào?
14. Latest document có tái tạo đủ event history không?
15. Vì sao type fidelity quan trọng cho tiền, UUID, timestamps?
16. Logical backup có cần schema/index/roles metadata không?
17. Partial tenant backup cần dependency closure vì sao?
18. Làm sao giới hạn tải backup lên source?
19. Checksum có chứng minh transaction consistency không?
20. Một incremental chain mất base thì sao?
21. PITR log cần liên tục từ checkpoint tới target vì sao?
22. CDC log khác WAL/crash recovery log ở đâu?
23. Physical restore cần quan tâm node identity/topology thế nào?
24. Backup secondary lag ảnh hưởng RPO ra sao?
25. COW snapshot còn gây I/O/storage cost sau khi tạo không?
26. Khi nào replica resync phù hợp hơn restore node?
27. MongoDB logical dump có tự tạo global sharded cut không?
28. Cassandra node snapshot có tự đủ để khôi phục cluster không?
29. DynamoDB PITR khác Streams ở điểm nào?
30. Redis RDB khác AOF thế nào?
31. Search index có thể rebuild từ NoSQL source khi nào?
32. Backup nên ở failure domain nào để chống region loss?
33. Làm sao xác minh KMS key availability ở DR?
34. Khôi phục từ backup cũ có thể hồi sinh PII đã xóa ra sao?
35. Metrics nào đại diện latest verified recovery point?
36. Restore drill phải đo những giai đoạn nào?
37. Vì sao source p99 có thể xấu khi logical backup chạy?
38. Backup source không có outbox sẽ gây vấn đề gì?
39. Nên làm gì trước khi restore đè production đang nhận writes?
40. Những data tests nào chứng minh Order–Inventory khớp?
41. Vì sao phải tách backup completed và restore verified?
42. Tính lower bound restore transfer time như thế nào?
43. Khi WAL archive có gap, nên công bố RPO ra sao?
44. Partial restore một tenant có thể phá unique constraints nào?
45. Ai cần sở hữu backup, restore, KMS và privacy suppression runbooks?

## 62. Tổng kết: backup có giá trị khi dữ liệu phục hồi được và có nghĩa

**Sao lưu logic** xuất dữ liệu ở mức record/document cùng metadata, thuận tiện cho khôi phục chọn lọc hoặc chuyển đổi nhưng cần xử lý consistency của scans, data types và schema/index. **Sao lưu vật lý** giữ storage-engine images, có thể thuận lợi với data lớn nhưng phụ thuộc checkpoint/WAL, coordinated volumes/shards, version compatibility và topology-aware restore.

Cả hai đều có thể là full hoặc incremental, và cả hai đều có thể **không nhất quán** nếu thực hiện sai protocol. Một database-consistent image vẫn có thể chưa application-consistent với outbox, broker, object attachments và payment effects. RPO/RTO phải được chứng minh bằng restore drill và business reconciliation, không chỉ bởi nhãn “backup enabled”.

Một quy trình đáng tin:

~~~text
1. Xác định authoritative data, dependencies, RPO và RTO.
2. Chọn logical/physical, full/incremental theo engine capability.
3. Định nghĩa consistency scope và recovery cutoff.
4. Phối hợp snapshot, WAL/log/CDC theo supported protocol.
5. Giữ schema/index, metadata, keys và topology information.
6. Throttle backup để bảo vệ OLTP SLO.
7. Bảo vệ artifacts và log chain ở failure domain độc lập.
8. Verify checksum, chain completeness và decrypt permissions.
9. Restore thử trên target cô lập với engine/version phù hợp.
10. Reconcile counts, versions, invariants và deletion policy.
11. Đo actual RPO/RTO kể cả provisioning, replay và cutover.
12. Alert khi latest verified recovery point quá cũ.
13. Cập nhật runbook, retention và security sau mỗi drill/sự cố.
~~~

**Kết luận cốt lõi:** *Backup chỉ thực sự có giá trị khi nó cho phép khôi phục một trạng thái dữ liệu có nghĩa, trong thời gian đã cam kết, bằng một chuỗi bước có thể kiểm chứng và lặp lại.* Hãy thiết kế tính nhất quán và đường phục hồi trước khi tối ưu tốc độ hay dung lượng sao lưu.











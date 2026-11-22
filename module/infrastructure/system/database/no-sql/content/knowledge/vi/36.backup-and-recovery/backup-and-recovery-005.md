# Sao lưu trong lúc ghi và phạm vi dữ liệu cần bổ sung

Một hệ thống NoSQL phục vụ người dùng 24/7 thường không thể dừng tất cả lệnh ghi để sao lưu. Trong lúc một tiến trình backup đang quét collection, sao chép SSTables, chụp volume snapshot hoặc xuất dữ liệu ra object storage, ứng dụng vẫn tạo đơn hàng mới, thay trạng thái, cập nhật số dư, xóa bản ghi và thay đổi cấu trúc dữ liệu. **Chép được nhiều bytes không đồng nghĩa tạo được bản backup có thể khôi phục thành một trạng thái nhất quán.**

Bài học này thuộc chương **Sao lưu và phục hồi** của module **Database No SQL**, tập trung vào hai câu hỏi phải được trả lời cùng nhau:

1. **Sao lưu trong lúc ghi như thế nào để không bỏ sót, trộn sai trạng thái hoặc tạo bản sao không thể phục hồi?**
2. **Ngoài dữ liệu chính, phải bổ sung những gì — log, metadata, cấu hình, khóa mã hóa, dữ liệu ngoài database và mốc đồng bộ — để sau khi restore ứng dụng thật sự hoạt động và đạt RPO/RTO?**

Phương pháp chung là xác định **ranh giới thời gian/tiến độ nguồn có ý nghĩa**, dùng kỹ thuật snapshot/backup được database hỗ trợ, bảo toàn **các thay đổi cần thiết để đi từ snapshot tới điểm khôi phục**, và **kiểm chứng bằng restore**, không chỉ nhìn thông báo `backup completed`.

> **Nguyên tắc trung tâm:** Một bản backup đúng phải có **phạm vi dữ liệu xác định, điểm khôi phục xác định, đủ thông tin để replay/khôi phục, tính toàn vẹn được kiểm tra và bằng chứng restore thành công**. Khi hệ tiếp tục ghi, cần hiểu chính xác snapshot bao gồm mutation nào, loại trừ mutation nào, và phần thay đổi trong khoảng giao được lưu ở đâu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **offline backup, online/hot backup, crash-consistent snapshot, application-consistent snapshot, logical export, physical snapshot và incremental backup**.
2. Hiểu vì sao **quét dữ liệu đang thay đổi** không nhất thiết tạo một consistent cut.
3. Mô tả **write ACK, transaction commit, WAL/commit log/oplog, MVCC, snapshot boundary, checkpoint và recovery replay**.
4. Xác định điều kiện để backup bao gồm mọi thay đổi trước mốc khôi phục và không lẫn một phần giao dịch sau mốc.
5. Phân biệt **sao lưu online trên một node** với **snapshot nhất quán toàn replica set, shard group, nhiều partitions/collections và nhiều hệ thống**.
6. Xác định những dữ liệu cần bổ sung: **log tail, indexes/schema, tombstones, TTL state, topology/roles, encryption keys, users/permissions, config, external blobs, CDC/outbox offsets và dependencies**.
7. Thiết kế **backup manifest**, checkpoint, checksum, retention chain và replay có thể lặp lại.
8. Chẩn đoán các lỗi **gap, overlap, stale snapshot, missing deletes, log retention expiry, orphan blobs, schema mismatch và backup thiếu khóa giải mã**.
9. Lập kế hoạch RPO/RTO, PITR, restore rehearsal, isolation và kiểm thử fault injection khi hệ vẫn có writes.
10. Đối chiếu những khác biệt quan trọng của MongoDB, Cassandra/ScyllaDB, Redis, DynamoDB, Cosmos DB và Elasticsearch/OpenSearch mà không áp nhầm guarantee giữa sản phẩm.

## 2. Bài toán xuyên suốt: backup Order Service trong giờ cao điểm

Giả sử một ứng dụng Java xử lý:

~~~text
Database: 80 million Orders
Logical stores:
  Orders collection / table
  OrderItems collection / table
  Payments ledger or outbox
  Search index / read model
  Object storage holding order attachments

Traffic during backup:
  12,000 reads/s
   2,000 writes/s

Backup:
  Starts at 10:00
  Completes at 10:30
  Database continues accepting writes.
~~~

Trong 30 phút sao lưu có các thay đổi:

~~~text
10:03 Order O101 CREATED
10:07 Order O102 PAID
10:10 Order O101 CANCELLED
10:11 Order O103 DELETED
10:20 Order O102 SHIPPED
10:25 Order O104 CREATED
~~~

Nếu backup job đọc O102 lúc 10:05 và đọc O101 lúc 10:28 thì bản export có thể chứa:

~~~text
O102: status=CREATED   (đọc trước PAID/SHIPPED)
O101: status=CANCELLED (đọc sau update)
~~~

Đó **không chắc** là trạng thái database tại bất kỳ thời điểm đơn nhất nào. Nếu `OrderItems`, `Payments` và `Orders` còn được quét theo các thứ tự khác nhau, backup có thể trộn một `Order` mới với `Payment` cũ hoặc ngược lại.

### 2.1. Nguy cơ của việc “copy toàn bộ file trong lúc database chạy”

Ở một physical store, database có thể đang:

- Ghi WAL/commit log.
- Flush dirty pages/memtables.
- Compaction/merge files.
- Cập nhật manifest/index metadata.
- Thay đổi files và generations.

Nếu dùng file-copy chung (`cp`, `robocopy`, rsync một lần) mà **không có cơ chế snapshot/hot-backup của engine**, các files có thể thuộc nhiều thời điểm, thiếu log hoặc thiếu manifest. Database có thể **không khởi động được sau restore** hoặc tự phục hồi về trạng thái không được chứng minh.

### 2.2. Nguy cơ của việc “Scan rồi nhận change stream từ lúc scan xong”

~~~text
t0: Begin full scan.
t1: Scan key O101 version 3.
t2: Source updates O101 to version 4.
t3: Finish scan.
t4: Subscribe CDC from LATEST.
~~~

Event cập nhật v4 ở giữa scan và subscription có thể **không có trong bản quét lẫn stream**. Đây là **gap**.

Không thể sửa gap chỉ bằng cách tăng số workers hoặc kiểm tra tổng số bản ghi đọc.

### 2.3. Một backup có thể “thành công” nhưng không phục vụ RPO

Backup hoàn thành lúc 10:30 nhưng có consistent cut lúc 10:00, không có log bổ sung. Nếu sự cố xảy ra 10:31, hệ chỉ có thể restore tới 10:00: **có thể mất 31 phút writes** theo failure scenario, dù object storage nhận được backup ở 10:30.

Vì vậy phải phân biệt:

- `backupStartedAt`: thời điểm job bắt đầu.
- `snapshotBoundary`: trạng thái mà ảnh chụp đại diện.
- `backupFinishedAt`: thời điểm bytes được copy xong.
- `lastRecoverablePosition`: vị trí cuối **đã có đủ dữ liệu backup/log** để khôi phục.
- `recoveryTarget`: điểm người vận hành chọn lúc restore.

## 3. Các loại bản sao lưu và mức nhất quán

| Loại | Ý nghĩa | Lưu ý khi vẫn có writes |
| --- | --- | --- |
| **Offline backup** | Dừng database/writes hoặc chuyển sang trạng thái quiesced phù hợp | Dễ xác định trạng thái, gây downtime |
| **Online/hot backup** | Tạo bản backup khi database tiếp tục phục vụ | Phải dùng protocol/tool được hỗ trợ |
| **Logical backup/export** | Trích xuất documents/rows/objects | Quét nhiều pages có thể không cùng snapshot |
| **Physical backup** | Sao chép data files/SSTables/volume snapshots | Cần file/log/checkpoint consistency |
| **Crash-consistent snapshot** | Trạng thái như thiết bị bị cắt điện tại một instant được xác định | Chỉ an toàn nếu engine hỗ trợ crash recovery từ tổ hợp volumes/logs đó |
| **Application-consistent snapshot** | Ứng dụng và DB hoàn thành/đóng băng các ràng buộc cần thiết | Phải có coordinator cho nhiều stores/services |
| **Full backup** | Baseline hoàn chỉnh theo phạm vi | Đắt storage/bandwidth, có thể lâu |
| **Incremental backup** | Changes từ baseline trước | Cần chuỗi đầy đủ và order/versions |
| **Differential backup** | Changes từ một full baseline | Giảm độ dài chain theo một số mô hình |
| **PITR (Point-in-Time Recovery)** | Restore tới một điểm được hỗ trợ trong cửa sổ | Cần baseline + log/change history liên tục |

### 3.1. Hot backup không đồng nghĩa snapshot isolation của mọi query

Một công cụ backup có thể tạo consistent snapshot nội bộ đúng sản phẩm. Nhưng một truy vấn thường qua API như `find()` hoặc `Scan` trên dữ liệu đang thay đổi **không vì đang dùng cùng database mà tự được bảo đảm consistent snapshot**.

### 3.2. Crash-consistent khác application-consistent

Ví dụ Java Order Service đang chuyển tiền:

~~~text
Step 1: Database writes Payment=CAPTURED.
Step 2: External payment provider confirms payment.
Step 3: Database writes Order=PAID.
~~~

Một crash-consistent DB backup ngay sau Step 1 có thể hoàn toàn hợp lệ đối với storage engine, nhưng **business workflow giữa DB và payment provider** đang dở. Khi restore, cần **idempotency/outcome reconciliation**. Database snapshot không tự tạo distributed transaction với đối tác thanh toán.

### 3.3. Snapshot nhất quán phải nói rõ scope

Có ít nhất các mức:

~~~text
One document / key
One partition / transaction scope
One node / local storage engine
One shard / replica group
All shards in one database cluster
Multiple database clusters
Database + object storage + external provider
~~~

Một primitive atomic theo key không bảo đảm consistent cut trên nhiều shards, và snapshot một filesystem không tự bao phủ files trên volume khác.

## 4. “Consistent cut” là gì khi database tiếp tục ghi?

Hãy coi database có một lịch thay đổi đã commit:

~~~text
C1 -> C2 -> C3 -> C4 -> C5 -> C6
~~~

Với một nguồn có ordered commit log, một consistent snapshot tại mốc \(L=4\) lý tưởng phản ánh:

~~~text
Included: C1, C2, C3, C4
Excluded: C5, C6
~~~

Tức snapshot đại diện **một trạng thái hợp lệ sau prefix đã commit**; với transactions, nó không được chứa *nửa transaction* nếu scope của snapshot hứa transaction consistency.

### 4.1. Snapshot + log replay

Một mô hình PITR:

~~~mermaid
flowchart LR
    S["Snapshot state at L0"] --> R["Replay committed changes (L0, Ltarget]"]
    R --> T["Recovered state at Ltarget"]
    M["Backup manifest / schema / keys"] --> S
    L["Archived WAL / oplog / change history"] --> R
~~~

Nếu \(S(L_0)\) đã bao gồm toàn bộ changes tới \(L_0\), replay các changes **sau** \(L_0\) theo semantics của engine. Nếu API chỉ hỗ trợ replay inclusive ở \(L_0\), recovery tool cần xử lý overlap/duplicate theo nguồn và engine; không tự apply non-idempotent delta lần hai.

### 4.2. Vì sao backup có thể chạy nhiều phút nhưng vẫn có một boundary?

Database có thể dùng **MVCC, copy-on-write pages, immutable SSTables, snapshot handles, transaction log pinning** và cơ chế khác để tạo ảnh logic tại một cut trong khi bytes được copy dần. Điều kiện là engine/tool kiểm soát **những version/files/logs cần giữ sống cho tới khi copy xong**.

Nếu không có cơ chế giữ consistent view, một long scan dễ đọc các versions khác nhau và không có một cut chung.

### 4.3. Một snapshot online có thể cần “fuzzy” pages nhưng vẫn phục hồi đúng

Trong một số physical backup protocols, các pages/files được copy tại nhiều thời điểm nên bản vật lý nhìn “fuzzy”, nhưng **transaction log đủ và recovery protocol được engine hỗ trợ** có thể redo/undo để khôi phục về trạng thái nhất quán. Không đồng nhất “mỗi file được copy khác giờ” với “backup chắc chắn hỏng”; điểm mấu chốt là **backup tool + required logs + restart/recovery contract**, không phải tự suy từ trình tự copy.

### 4.4. Snapshot/cut của distributed cluster khó hơn local crash cut

Giả sử transaction chuyển trạng thái:

~~~text
Shard A: decrement reserved inventory.
Shard B: create order.
~~~

Nếu backup shard A ở trước transaction, shard B ở sau transaction, restore có thể có Order mà inventory chưa reserve, trừ khi engine cung cấp **distributed snapshot/transaction recovery semantics** hoặc business repair. Snapshot mỗi node độc lập không tự là global transaction-consistent backup.

### 4.5. Các “happens-before” quan trọng

Khi một write completed trước một snapshot có contract mạnh tại boundary sau write, state phải phản ánh write ấy. Khi write concurrent với snapshot, backup chỉ cần tuân thủ **scope và cut protocol** đã công bố; không mặc định mọi write đang chạy phải xuất hiện.

## 5. Các mốc thời gian không được trộn

| Mốc | Ví dụ | Câu hỏi quan trọng |
| --- | --- | --- |
| Client sends write | t=10:05:00 | Chỉ là request, chưa commit? |
| DB ACK | t=10:05:01 | ACK theo durability/write concern nào? |
| Source commit position | L=1500 | Có thuộc same log/epoch? |
| Snapshot cut | L=1400 | Snapshot chứa tới đâu? |
| Backup file copy completed | 10:30:00 | Chỉ thời điểm vận chuyển bytes xong |
| Archived log position | L=1490 | Có gap giữa 1400 và 1490 không? |
| Restore target | L=1475 | Logs có thể replay đúng tới đây không? |

Một backup copy xong lúc 10:30 với log chỉ tới L=1490 **không** có nghĩa khôi phục được committed write ở L=1500. Muốn xác nhận RPO, phải biết **durable backup set và log high-water**.

### 5.1. Wall-clock time không tự là log sequence

Nhiều engines có logical positions như LSN, oplog timestamp/term, sequence number, commit-log replay position hoặc checkpoint token. Chúng có semantics và scope riêng. Không dùng `updatedAt` do client cấp thay cho source log position.

### 5.2. Multi-shard có thể cần vector positions

~~~yaml
snapshotBoundary:
  shardA: "opaque-A-500"
  shardB: "opaque-B-630"
  shardC: "opaque-C-910"
~~~

Ba positions không tự là một **global consistent cut**. Cần protocol xác nhận chúng phù hợp với distributed transactions/dependencies của cluster. Đừng tự gộp bằng `max()` hoặc so sánh offsets giữa shards khác nhau.

### 5.3. Thời gian sao lưu không bằng tuổi có thể khôi phục

Một dashboard tốt cần ít nhất:

~~~text
lastSuccessfulBackupCompletion
lastVerifiedRestorableSnapshotBoundary
lastContiguouslyArchivedLogPosition
oldestAvailablePITRPosition
latestAvailablePITRPosition
lastSuccessfulRestoreDrill
~~~

Nếu chỉ đo “đã 24 giờ từ lần backup thành công”, bạn chưa biết log archiving có ngừng từ 10 giờ trước hay không.

## 6. Sao lưu trong lúc ghi: các giao thức chính

### 6.1. Giao thức A — Dừng writes trong khoảng ngắn có kiểm soát

~~~text
Pause writes / stop accepting new mutations.
Drain in-flight transactions to a known state.
Establish backup boundary.
Create supported snapshot.
Resume writes.
Copy snapshot bytes / archive logs.
~~~

Ưu điểm: đơn giản để lý luận. Nhược điểm: phụ thuộc khả năng quiesce thật ở **tất cả writers/services/regions** và backup primitive có thể tạo boundary nhanh. Chỉ “bật maintenance UI” không đủ nếu background workers vẫn ghi.

### 6.2. Giao thức B — Snapshot consistent qua cơ chế của database

~~~text
Database establishes snapshot handle/cut.
Writers continue.
Backup tool copies stable snapshot view.
Manifest records snapshot generation and source position.
Restore tool reconstructs that exact view.
~~~

Phù hợp khi engine hỗ trợ online backup/snapshot ở scope cần. Không dùng ordinary paginated scan để tự thay thế primitive nếu không có guarantee tương đương.

### 6.3. Giao thức C — Physical backup + WAL/commit-log continuation

~~~text
Start backup with engine-approved checkpoint/log archive.
Copy data files while writes continue.
Keep all required WAL/commit log segments.
Record the log sequence needed to begin recovery.
Continue archiving through desired restore target.
Restore base backup and replay logs in documented order.
~~~

Điểm quan trọng là **không mất bất kỳ required segment nào**. Nếu một segment giữa L1000 và L1050 bị xóa, giữ đến L2000 cũng không bù được gap.

### 6.4. Giao thức D — Logical snapshot + CDC chồng lấp

Một hệ không có global snapshot primitive có thể dùng:

~~~text
Open CDC before beginning scan.
Persist a safe start position.
Scan initial data by bounded chunks.
Buffer/replay changes emitted during scan.
Apply version-aware merge + delete tombstones.
Mark complete after proving no gap.
~~~

Đây là **một nhóm thiết kế**; không có thuật toán “mở CDC trước rồi scan là đủ” cho mọi NoSQL. Cần source-specific cursor/sequence, collision/window handling, per-key ordering, transaction boundaries và version semantics để không có snapshot row cũ ghi đè change mới.

### 6.5. Giao thức E — Managed point-in-time backup

Một managed database có thể cung cấp PITR/continuous backups như feature chính thức; service quản lý snapshot/log capture bên trong. Team vẫn phải kiểm tra:

- RPO/retention window thật và mode được hỗ trợ.
- Scope từng table/container/cluster/region.
- Những resources không nằm trong backup.
- Restore tạo **resource mới** hay replace tại chỗ.
- Config/IAM/network/keys có tự được khôi phục không.
- Cách ứng dụng chuyển traffic và validate sau restore.

Không tự giả định tên gọi “continuous backup” đồng nghĩa recovery toàn bộ microservices vào cùng global cut.

## 7. Ba race điển hình khi backup gặp write

### 7.1. Race A — Lost update giữa scan và change capture

~~~text
t0 Scan O101 v1
t1 UPDATE O101 to v2
t2 Scan completes
t3 CDC starts at LATEST
~~~

Nếu snapshot giữ v1 và CDC không bắt event v2, restore sai vĩnh viễn. Phải có **snapshot cut với log continuation** hoặc capture changes trước/during scan theo protocol.

### 7.2. Race B — Snapshot row cũ hồi sinh delete

~~~text
t0 Scanner reads O102 v9 into an in-memory page.
t1 Source DELETE O102 v10 commits.
t2 CDC applies DELETE v10 to backup-derived target.
t3 Scanner flushes its buffered v9 upsert.
~~~

Nếu target blind-upsert, O102 **hồi sinh**. Cần ordering/version guard và tombstone/generation semantics; với file-system snapshot native engine, recovery semantics phải xử lý điều này theo contract của snapshot/log, không tự ghép bản scan.

### 7.3. Race C — Multi-record transaction bị cắt đôi

~~~text
Transaction T42:
  Write Payment PAID in partition P1.
  Write Order CONFIRMED in partition P2.

Backup P1 at logical time 12:01.
Backup P2 at logical time 12:00.
~~~

Nếu không có global transaction snapshot, restore có thể có Payment mà không có Order. Cần distributed transaction/consistent cut hoặc **reconciliation of business invariants** với event/outbox/ledger history sau restore.

### 7.4. Race D — Log bị truncate khi backup còn đang chạy

~~~text
t0 Backup captures base at L100.
t1 WAL segment covering L101..L200 is archived temporarily.
t2 Source retention removes that segment.
t3 Backup finishes and tries to replay from L100.
~~~

Nếu segment L101..L200 chưa được lưu bền vào backup repository, recovery chain bị đứt. **Retention capacity là một yêu cầu correctness**, không chỉ tối ưu dung lượng.

### 7.5. Race E — Schema đổi trong lúc export

~~~text
t0 Export first half using schema v1.
t1 Deployment changes shape/index/serialization.
t2 Export second half using schema v2.
~~~

Backup cần engine-supported schema cut/DDL capture hoặc transformer versioning; nếu không, restore có thể thiếu field, sai default hay đọc sai data. Phạm vi sao lưu **bao gồm metadata/schema changes** khi chúng ảnh hưởng cách diễn giải bytes.

## 8. Backup phải trả lời câu hỏi “khôi phục được tới đâu?”

### 8.1. Recovery Point Objective (RPO)

**RPO** là mức mất dữ liệu tối đa business chấp nhận khi có sự cố. Một cách thể hiện:

~~~text
RPO target: <= 5 minutes of acknowledged writes
~~~

Muốn đo phải xác định writes đã ACK theo mode nào và last recoverable source position/time là gì. Backup hàng ngày nhưng log archive liên tục có thể đạt RPO khác với chỉ full backup hàng ngày.

### 8.2. Recovery Time Objective (RTO)

**RTO** là thời gian phục hồi dịch vụ đến mức đã định. Nó gồm:

~~~text
Detect incident
  -> authorize recovery
  -> allocate restore resources
  -> copy/read base backup
  -> replay logs / rebuild indexes
  -> validate correctness
  -> reconnect clients / cut over
  -> warm up caches and stabilize
~~~

Một bản backup nhỏ hơn không mặc nhiên có RTO nhỏ hơn nếu chain incremental dài, decrypt keys unavailable hoặc index rebuild kéo dài.

### 8.3. PITR granularity

Tùy engine, target có thể chỉ được chọn theo **timestamp, LSN, cluster time hoặc giới hạn gần nhất**. Không tự hứa recovery đến từng millisecond nếu service chỉ hỗ trợ coarse granularity hoặc log retention gaps.

### 8.4. RPO khác write replication lag

Replica đã bắt kịp primary không có nghĩa backup repository đã có dữ liệu mới nhất. Ngược lại, log archive có thể đã lưu committed changes khi một follower đang lag. **Replication health và backup recoverability phải có metrics riêng**.

### 8.5. Durability phải nói rõ failure model

Một backup đặt cùng account/region/credentials với source có thể biến mất khi ransomware hoặc admin script xóa cả hai. Muốn bảo vệ disaster scenario phải tính **failure domain của backup repository**, cross-region/object-lock/immutable backup, credentials isolation và restore drill, không chỉ engine consistency.

## 9. “Phạm vi dữ liệu cần bổ sung” là gì?

Một backup có thể chứa **mọi document/row** nhưng vẫn thiếu nhiều thông tin quan trọng để khôi phục ứng dụng. Cần lập **inventory về state và dependencies** trước khi chọn công cụ sao lưu. Phạm vi phải xuất phát từ các bất biến nghiệp vụ và đường phục hồi, không chỉ từ tên database.

### 9.1. Ma trận thành phần cần xét

| Thành phần | Vì sao có thể cần | Nếu thiếu, điều gì hỏng? |
| --- | --- | --- |
| Dữ liệu chính: documents/rows/keys | Source-of-truth state | Mất record/giá trị |
| WAL/commit log/oplog/log tail | Replay changes sau snapshot/PITR | Mất writes giữa backup và recovery point |
| Database metadata/manifests | File/table/shard mapping, file generations | Không mở được physical backup hoặc sai phạm vi |
| Schema/collection/keyspace definitions | Data types, validators, TTL, partition strategy | Restore bytes nhưng ứng dụng không đọc/ghi đúng |
| Index definitions | Unique/search/access semantics | Performance sai, uniqueness enforcement có thể khác |
| Tombstones/delete history | Phản ánh những records đã bị xóa | Old backup có thể hồi sinh bản ghi |
| Transaction/commit metadata | Commit/abort, distributed transaction recovery | Half-transaction hoặc apply uncommitted state |
| User/roles/permissions | Quyền DB và service accounts | Service không đăng nhập hoặc quyền vượt mức |
| TLS/certificates/trust bundles | Kết nối và xác minh endpoint | Client handshake lỗi |
| Encryption keys/KMS references | Giải mã data files/backup objects | Có bytes nhưng không giải mã được |
| Database engine/version/config | File format, compression, feature flags | Restore không tương thích |
| Shard/rack/region/topology metadata | Sắp xếp replicas và routing | Cluster khởi động với placement/routing sai |
| CDC/outbox connector offsets | Tiếp tục event processing | Events bị gửi lại hoặc bỏ qua |
| Consumer checkpoints/read model positions | Biết projection đã apply tới đâu | Search/cache/analytics sai hoặc double-effect |
| External blobs/attachments | File nằm ngoài NoSQL | Record trỏ tới object không còn |
| Backup catalog/manifests/checksums | Xác định chain và tính toàn vẹn | Không biết restore tập nào |
| Audit/ledger/idempotency keys | Phân biệt operation đã thực hiện | Double-charge/double-reserve sau restore |
| Application version/migrations | Giải mã và xử lý schema cũ | Code mới không đọc được state cũ |
| Infrastructure config/IaC | Khởi tạo vùng mạng/storage/runtime | Có backup nhưng không tái tạo được service |

**Không phải mọi thành phần đều phải nằm trong cùng một tarball.** Điều quan trọng là mỗi thành phần cần thiết có **nguồn khôi phục, version, ownership và procedure** đã kiểm chứng.

### 9.2. Phân loại thành ba nhóm

**A. Dữ liệu phải sao lưu hoặc có bản khôi phục tương đương**

- Authoritative entities.
- Immutable event/ledger history.
- Objects ở blob storage cần giữ.
- Changelog/logs cho PITR.
- Encryption key material hoặc cách phục hồi quyền sử dụng keys.

**B. Dữ liệu có thể tái tạo, nhưng phải có kế hoạch**

- Secondary/search indexes nếu có thể rebuild từ authoritative source.
- Cache entries nếu cache không là source of truth.
- Materialized views với deterministic rebuild.
- Derived aggregates có đủ raw events.

**C. Metadata/cấu hình để dựng môi trường khôi phục**

- Data model/schema/index policies.
- Topology, permissions, secrets/key references.
- Service configs, DNS/endpoints, feature flags.
- Backup manifests, checkpoints, migration version.

Phân loại phụ thuộc sản phẩm và business. Một search index tưởng là “derived” nhưng chứa các human annotations chỉ tồn tại tại index thì **không còn tái tạo hoàn toàn được**.

## 10. Dữ liệu chính và phạm vi logical collection/table

### 10.1. Inventory theo domain thay vì tên collection

Ví dụ Order domain:

~~~text
Orders
OrderItems
Payments
PaymentIdempotency
Refunds
OrderEvents
Outbox
CustomerCreditReservations
AuditTrail
AttachmentsMetadata
~~~

Nếu chỉ backup `Orders`, restore có thể tạo Order “PAID” nhưng thiếu Payment ledger, refund records hoặc idempotency entries. **Backup scope phải phản ánh invariant** chứ không chỉ API GET Order.

### 10.2. Các namespace mới trong lúc backup

Nếu app triển khai version mới tạo `orders_v2` khi backup đang chạy, một job đã chụp danh sách collections từ đầu có thể không bao phủ namespace mới. Cần:

- Database-native consistent catalog/snapshot.
- Backup discovery policy với schema/catalog changes.
- Backup version/manifest bao gồm namespaces được bảo vệ.
- Một freeze/migration policy trong snapshot window nếu engine/tool yêu cầu.

### 10.3. Temporary collections và staging

Không phải mọi data tạm đều cần backup. Nhưng cần phân biệt:

- Collection tạm chỉ chứa rebuildable workspace.
- Queue/staging chứa **commands chưa được xử lý**.
- Outbox chứa events chưa publish.
- Upload staging chứa file chưa finalize nhưng đã trả ACK.

Xóa nhầm staging “tạm” trong restore có thể làm mất một operation đã được người dùng xác nhận.

### 10.4. Unique indexes và validators

Nếu unique index/validator được định nghĩa ngoài dữ liệu hoặc được rebuild theo policy khác, restore có thể chấp nhận writes trùng hoặc từ chối một bản ghi hợp lệ. **Lưu index definitions/constraints** hoặc xác định cách tái tạo chính xác.

### 10.5. Secondary indexes đôi khi rebuild được

Một số hệ khôi phục data rồi tự tái tạo indexes; có thể không cần copy physical index files. Nhưng **định nghĩa index và thời gian rebuild** vẫn ảnh hưởng RTO và hiệu năng sau cutover. Không ghi “index không cần backup” như một quy tắc chung.

## 11. Log thay đổi và “khoảng thời gian cần bổ sung”

Giả sử có:

~~~text
Snapshot boundary: L1000
Backup ends:       L1800 (source progress at finish)
Crash later:       L2200
~~~

Để phục hồi tới L2200, cần:

1. Snapshot hợp lệ tại L1000.
2. **Toàn bộ committed changes được yêu cầu từ sau L1000 tới L2200**.
3. Metadata để xác định log order, transaction boundaries và source identity.
4. Recovery tool có khả năng replay đúng.

**Không đủ** nếu chỉ lưu một export tại L1000 và last known record ở L2200 nhưng thiếu L1001…L2199.

### 11.1. Log không luôn là domain-event stream

**WAL/commit log** dùng cho storage recovery có thể khác:

- CDC change stream.
- Kafka topic of domain events.
- App audit log.
- Outbox.
- Replica shipping log.

Một CDC topic có thể lọc operations, chỉ chứa latest values, mất tombstones hoặc không giữ đủ thời gian. Nó **không tự thay thế WAL** cho physical database recovery trừ khi product-backed recovery protocol cho phép.

### 11.2. Immutable baseline + ordered changes

Trong mô hình đơn giản:

~~~text
RecoveredState(Ltarget) =
  ApplyCommittedChanges(
      BaselineSnapshot(Lbase),
      ChangeRange(after Lbase, through Ltarget)
  )
~~~

Điều kiện:

- Snapshot có boundary hợp lệ.
- Change range **đầy đủ và theo thứ tự được engine yêu cầu**.
- Transactions/abort/rollback được xử lý.
- Duplicate overlap không gây repeat non-idempotent effects.
- Delete/TTL/schema/key changes có representation đúng.

### 11.3. Log pinning và retention

Khi backup chạy, source có thể cần giữ log segments lâu hơn bình thường. Nếu snapshot mất 12 giờ nhưng oplog/commit log hữu dụng chỉ giữ 2 giờ, tool có thể phải:

- Pin/retain segments đúng cách.
- Archive liên tục trước khi source truncate.
- Giảm snapshot duration.
- Tăng log/archive capacity.
- Hoặc đổi sang snapshot mechanism khác.

**Không kéo dài retention một cách tùy tiện** mà không tính disk usage/compaction và limits của engine.

### 11.4. Snapshot + incremental chain

Ví dụ:

~~~text
Full F1 at L1000
Increment I1: L1001..L1500
Increment I2: L1501..L2000
Increment I3: L2001..L2300
~~~

Muốn restore tới L2250 cần F1 + I1 + I2 + phần hợp lệ của I3. Nếu I2 mất, I3 có thể vẫn là object hợp lệ nhưng **không tạo được một chain hoàn chỉnh**.

### 11.5. Change logs bị compaction theo key

Một log giữ “latest value per key” có thể hỗ trợ dựng **latest-state projection** trong một số thiết kế, nhưng không giữ mọi business event/delta. Nếu target cần replay `points += 5`, `points -= 3` hoặc audit toàn bộ lịch giao dịch, compacted latest-state log **không tương đương event ledger đầy đủ**.

### 11.6. Unknown write outcomes khi crash

Client timeout trước ACK có thể đã commit. Khi restore, không suy “request timeout nên không có trong backup”. Nguồn authoritative commit history và idempotency operation ID phải quyết định outcome; cần reconciliation với client/external effects.

### 11.7. WAL copy phải tương thích backup tool

Không tự đọc/cắt/ghép WAL bytes giữa các engine hoặc phiên bản. Thứ tự, headers, checksums, log segment rotation, compression, transaction records và retention đều **thuộc protocol riêng**. Dùng recovery API/tool đã được vendor hỗ trợ.

## 12. Tombstones, deletes, TTL và các bản ghi “không còn”

**Xóa dữ liệu** là một mutation quan trọng đối với khôi phục. Một backup không có tombstones hoặc delete events có thể hồi sinh dữ liệu mà business đã xóa.

### 12.1. Lịch ví dụ

~~~text
Snapshot at L100:
  O101 version 8 exists.

L110:
  DELETE O101 version 9.

Restore from snapshot L100
  and replay only INSERT/UPDATE events.
~~~

Kết quả sai: O101 vẫn tồn tại. Muốn recover L110 đúng, phải replay delete/tombstone theo semantics engine.

### 12.2. Physical tombstone khác logical delete event

Trong LSM engines, tombstones có thể là các cấu trúc nội bộ dùng để ngăn old SSTables hồi sinh values. Một **logical deletion record** trong CDC/outbox có thể là abstraction khác. Khi backup bằng physical snapshots, engine phải giữ các tombstones cần thiết; khi dựng read model từ logical events, consumer cần xử lý delete semantics đúng.

### 12.3. TTL là một phần trạng thái hoặc chính sách

Một record có:

~~~json
{
  "sessionId": "s-100",
  "state": "ACTIVE",
  "expiresAt": "2026-11-14T12:00:00Z"
}
~~~

Backup lúc 11:00 và restore vào 14:00 có thể gặp policy:

- Engine TTL đánh giá expiration theo restore/runtime clock.
- TTL metadata được giữ hoặc không theo backup type.
- TTL delete đã được áp trước/đang trong backup.
- Business yêu cầu sessions đã hết hạn không được coi active.

Vì thế phải kiểm tra **TTL metadata, expiration policy và thời gian khôi phục**. Không hứa “state đúng y như lúc 11:00” mà bỏ qua clock-dependent expiration.

### 12.4. Tombstone retention và snapshot cũ

Nếu một snapshot cũ có O101 v8, một downstream replay cần biết O101 bị xóa v9. Nếu tombstone bị dọn trước khi old snapshot merge hoàn tất, target có thể resurrect. Cần version/generation/retention guard phù hợp với **oldest replayable snapshot**.

### 12.5. Delete do yêu cầu riêng tư

Backup có thể chứa dữ liệu mà người dùng đã yêu cầu xóa. Thiết kế retention, encryption-key destruction, legal hold và restore procedure phải đáp ứng chính sách/law applicable. **Không được restore backup cũ rồi vô tình tái xuất bản dữ liệu đã được xóa hợp lệ**; có thể cần replay deletion ledger hoặc post-restore deletion controls.

### 12.6. Soft-delete và hard-delete khác nhau

Một bản ghi `deleted=true` là trạng thái có giá trị cần bảo toàn. Hard-delete tạo absence; để kiểm chứng absence sau restore cần biết **đã từng có key đó và delete đã commit ở mốc nào**, nếu mục tiêu là đảm bảo không resurrect.

## 13. Transaction boundaries và nhiều collections/partitions

### 13.1. Atomicity theo document/partition không kéo sang toàn cluster

Một NoSQL database có thể bảo đảm atomic single-document hoặc single-partition updates; điều đó không tự cấp **consistent backup of all collections** trong lúc nhiều transactions chạy. Scope của backup và scope transaction phải được đối chiếu.

### 13.2. Cross-shard transactions

Nếu engine hỗ trợ distributed transactions, backup/PITR cần xác định cách xử lý:

- Transaction begun before snapshot cut, commits after cut.
- Commit decision đã durable nhưng một shard chưa apply.
- Transaction aborted sau khi prepare.
- Coordinator/transaction metadata nằm ngoài data shard.

Không ghép một snapshot độc lập mỗi shard rồi chọn “gần cùng timestamp” để tự tạo transactionally consistent result.

### 13.3. Outbox và inbox là phần dữ liệu nghiệp vụ

Ví dụ Java:

~~~text
Transaction:
  save Order PAID
  save OutboxEvent(OrderPaid, eventId E42)
~~~

Nếu snapshot chứa Order nhưng không chứa OutboxEvent ở cùng consistency boundary, downstream có thể không nhận sự kiện. Nếu chỉ khôi phục Outbox mà không khôi phục Order, có thể publish một event không có source state tương ứng.

### 13.4. Consumer state và event IDs

Sau restore, connector/consumer có thể đọc lại E42. Hệ cần:

- Stable event/operation IDs.
- Idempotent target apply.
- Checkpoints phù hợp với **đã apply bền vững**, không chỉ đã fetch.
- Procedure khi offsets đã hết retention.

Không lấy một checkpoint của môi trường cũ gắn thẳng vào database restored theo snapshot cũ mà không xử lý khả năng **checkpoint đi trước state**.

### 13.5. Payment provider không thuộc cùng DB backup

Nếu Payment đã được capture thật bên ngoài, database restore có thể chưa phản ánh capture đó. Khi khởi động lại, phải reconcile qua **idempotent provider queries/webhooks/ledger**, không tự gọi capture lần nữa dựa vào record local cũ.

## 14. Dữ liệu ngoài NoSQL và ranh giới nhiều hệ thống

Một Order document có thể chỉ lưu đường dẫn file:

~~~json
{
  "orderId": "O900",
  "invoiceObjectKey": "invoices/2026/O900.pdf",
  "invoiceObjectVersion": "obj-ver-12",
  "status": "PAID"
}
~~~

Nếu NoSQL backup giữ document nhưng object storage bucket không giữ `obj-ver-12`, file hóa đơn mất. **Backup database và backup blob phải có kế hoạch consistency xuyên các hệ thống.**

### 14.1. Referential consistency với blobs

Giả sử:

~~~text
t0 Upload blob B1.
t1 Write DB reference to B1.
t2 Delete old blob B0.
~~~

Nếu backup DB tại t1 nhưng backup blob ở trước t0, restore DB có orphan reference B1. Nếu backup blob sau t2 nhưng DB backup trước t1, DB vẫn trỏ B0 đã bị xóa.

### 14.2. Giao thức object-versioned backup

Một thiết kế:

1. Lưu **immutable object versions** hoặc object version IDs.
2. DB record trỏ tới version cụ thể, không chỉ “latest path”.
3. Đảm bảo bucket snapshot/backup/retention giữ những versions DB snapshot có thể tham chiếu.
4. Chọn một recovery cut cho DB.
5. Restore/validate object references theo manifest.
6. Garbage-collect objects cũ **chỉ sau retention cần thiết**.

Object versioning không tự bảo đảm consistent cut; cần retention/reference tracking và recovery policy.

### 14.3. Message broker

Kafka/queue có thể chứa events đã publish nhưng chưa xử lý. Backup DB tại L100 và broker state tại offset 300 có thể gây:

- Event đã publish nhưng DB restore chưa thấy source write.
- DB đã chứa outbox event, broker lại thiếu.
- Consumer checkpoint báo đã xử lý nhưng target restore chưa áp.

Cần xác định **event replay protocol, producer idempotency, outbox state và checkpoint recovery**, không chỉ copy topic files.

### 14.4. Cache và search read models

Cache thường được chọn **không backup**, vì tái dựng được, nhưng khi restore source:

- Cache entries từ trước disaster có thể chứa **future state** so với restored DB.
- Search index có thể đã apply events vượt điểm khôi phục.
- Client sessions có expectedVersion vượt restored source.

Do đó cần **invalidate/reset/rebuild** theo recovery epoch hoặc khôi phục projection tới cùng cut. Không tái sử dụng một cache/index “còn chạy” mà không so source lineage.

### 14.5. Tenant-specific scope

Nếu chỉ restore một tenant:

- Dữ liệu có thể nằm chung shard/collection với tenants khác.
- Unique indexes/aggregate counters có scope global.
- Cross-tenant references hoặc shared auth rules có thể ảnh hưởng.
- Replay chỉ tenant events có thể cần filter nhưng phải bảo toàn invariants.

Một engine hỗ trợ cluster PITR chưa chắc hỗ trợ **transactionally consistent single-tenant restore** mà không đụng tới tenants khác. Cần export/import/reconciliation procedure riêng.

## 15. Metadata, cấu hình, quyền và khóa mã hóa

Một bản backup có bytes nhưng thiếu metadata hoặc keys có thể **không sử dụng được**.

### 15.1. Schema và migration version

Cần lưu:

~~~text
database engine/version
collection/table/namespace definitions
index and uniqueness definitions
TTL policy
validation rules
serialization formats / schema registry
application migration version
compatibility notes
~~~

Ví dụ restore database về schema v3 nhưng deploy Java service chỉ hiểu v5 có thể gây lỗi hoặc ghi data theo format không tương thích.

### 15.2. Shard topology và routing

Physical backups có thể chứa partition/shard placement metadata và replication terms theo engine. Restore sang cluster mới có thể yêu cầu **reconfigure topology**, không copy trực tiếp member IDs/hostnames/config để khởi động cùng identity trên mạng production.

Đặc biệt cần tránh **hai cluster cùng nhận mình là authoritative** khi khôi phục trong môi trường test gần production.

### 15.3. User/roles/permissions

Backup chỉ dữ liệu không luôn bao gồm:

- Database users/roles.
- Service account mappings.
- Authentication configuration.
- Network allowlists.
- TLS trust/certificates.
- IAM policies.

Cần có Infrastructure-as-Code/secrets-management/privileged recovery procedure để tái tạo đúng quyền, **không tự copy credentials plaintext vào chung object backup**.

### 15.4. Encryption at rest và KMS

Nếu backup được mã hóa bằng key ID K1, restore cần **khả năng giải mã bằng K1 hoặc recovery wrapping key**. Nếu K1 bị xóa/disabled/revoked, backup có thể trở thành vô dụng.

Lưu:

~~~text
key reference / version / region
encryption algorithm/mode metadata
roles authorized to decrypt
key-retention policy >= backup retention
cross-region key portability constraints
documented emergency recovery procedure
~~~

Không lưu **private key/password/secret bytes** vào bài học, logs hoặc manifest public; thiết kế quyền tối thiểu và separation of duties.

### 15.5. Encryption in transit và restore isolation

Một restore drill không được kết nối nhầm tới production broker hoặc payment provider với credentials thật rồi phát side effects. Môi trường restore cần **network isolation, dummy credentials/endpoints, masked test data và no outgoing customer notifications**.

### 15.6. Backups là dữ liệu nhạy cảm

Backup có thể chứa PII, tokens, credentials nhúng trong documents. Cần encryption, access logs, immutability, retention/deletion policy, geographic residency và audit theo yêu cầu pháp lý/tổ chức.

## 16. Backup manifest: bản mô tả để chứng minh một recovery set

Một backup không nên chỉ là thư mục `backup_2026-11-14/` có hàng nghìn files. Cần **manifest** mô tả mỗi artifact, nguồn, snapshot boundary, logs, dependencies, checksums, version và khả năng phục hồi.

### 16.1. Manifest minh họa

~~~yaml
backupId: "orders-prod-20261114-100000"
formatVersion: 1
status: "COMPLETE"
createdAtUtc: "2026-11-14T10:00:00Z"
completedAtUtc: "2026-11-14T10:32:15Z"
source:
  engine: "illustrative-nosql"
  engineVersion: "documented-release"
  clusterIdentity: "orders-prod-r1"
  region: "r1"
  epoch: "term-42"
scope:
  namespaces:
    - "orders"
    - "payments"
    - "outbox"
  excludedNamespaces:
    - "rebuildable-temporary-cache"
consistency:
  guarantee: "engine-supported-point-in-time-snapshot"
  snapshotBoundary: "opaque-source-position-L1000"
  transactionScope: "documented-by-engine"
artifacts:
  - id: "base-001"
    uri: "object://private-backups/orders/base-001"
    sizeBytes: 100000000000
    sha256: "<calculated-checksum>"
requiredChangeHistory:
  startExclusive: "L1000"
  archivedThroughInclusive: "L1800"
  archiveArtifacts:
    - "logs-1001-1400"
    - "logs-1401-1800"
dependencies:
  schemaBundle: "schema-version-15"
  appRelease: "order-service-42"
  encryptionKeyRef: "kms:private-key-reference"
  objectVersionCatalog: "object-catalog-20261114"
  cdcCheckpointPolicy: "reconcile-after-restore"
validation:
  checksumStatus: "PASS"
  restoreDrillId: "not-yet-run"
  verifiedRestorableThrough: "L1800"
~~~

Đây là **mẫu thông tin**, không phải format phổ quát được một database hoặc backup tool tự động hiểu. Giá trị `status: COMPLETE` chỉ nên được publish khi các files/log segments/checksums/cut metadata đã được commit bền; `restoreDrillId: not-yet-run` nghĩa chưa có bằng chứng đã restore được.

### 16.2. Snapshot boundary và log range có tính inclusive/exclusive

`startExclusive: L1000` nghĩa snapshot đã chứa mutations tới L1000, log replay bắt đầu từ **sau L1000**. Nếu tool dùng inclusive source positions, cần protocol xử lý duplicate đúng engine. Không mô tả mơ hồ “backup log từ khoảng 10 giờ”.

### 16.3. Manifest immutable sau publish

Một pattern:

~~~text
1. Write artifacts to staging prefix.
2. Upload and verify checksums and lengths.
3. Verify source-log coverage / artifact generation.
4. Write immutable complete manifest last.
5. Publish a small pointer to latest complete manifest.
~~~

Nếu crash ở bước 2, không có manifest complete, backup chưa được coi thành công. Nếu object storage/backup repository cung cấp atomic put/conditional write/versioning, sử dụng chúng theo contract; không giả định directory rename là atomic trên mọi object store.

### 16.4. Checksum bảo đảm điều gì?

SHA-256/CRC giúp phát hiện corruption hoặc transfer mismatch theo mục tiêu và phạm vi. **Checksum không chứng minh database state nhất quán** hoặc mọi document đều có trong backup. Một archive scan thiếu delete nhưng bytes không lỗi vẫn có thể có checksum “đúng”.

### 16.5. Signed manifest và provenance

Trong môi trường rủi ro cao, có thể ký manifest và ghi:

- Backup agent/tool version.
- Source cluster identity và term.
- IAM principal thực hiện.
- Timestamp và location.
- Repository generation/object version.
- Approval/audit trail.

Đừng tin file `latest.txt` nếu không xác minh được manifest được ký/ủy quyền phù hợp, đặc biệt khi khôi phục sau security incident.

## 17. Chuỗi backup và điều kiện “không có gap”

Một incremental chain có thể trông như sau:

~~~text
F1: full snapshot at position L1000
I1: changes L1001..L1200
I2: changes L1201..L1600
I3: changes L1601..L1900
~~~

Restore target L1800 đòi chuỗi F1 → I1 → I2 → một phần I3 theo recovery protocol. **Thiếu I2 là mất cả khả năng recover L1800**, dù I3 còn nguyên.

### 17.1. Tại sao timestamp overlap chưa đủ?

Hai archive artifacts:

~~~text
File A: 10:00..10:10
File B: 10:10..10:20
~~~

Chúng trông liền nhau theo wall clock, nhưng chưa chứng minh log positions liên tục, đặc biệt khi:

- Source clock nhảy.
- Log segment rotation.
- Shard failover/epoch change.
- Log compaction.
- Data stream có gaps trong interval.

Nên dùng source positions/segments và vendor recovery chain validation.

### 17.2. Incremental type phụ thuộc engine

Incremental có thể nghĩa:

- Changed file blocks.
- Newly created immutable SSTables.
- New WAL segments.
- Logical change records.
- Managed service snapshots.

Không đưa một incremental file từ baseline F1 ghép với F2 chỉ vì cùng namespace, nếu versions/file identity/backup chain không tương thích.

### 17.3. Garbage collection có thể xóa base backup cần thiết

Nếu retention chỉ nhìn ngày tạo và xóa F1 nhưng I1..I5 vẫn đang tham chiếu F1, incremental chain trở thành unusable. Cần quản lý **dependency graph của restore sets** trước khi expire artifacts.

### 17.4. Garbage collection trong object repository

Các blobs còn được tham chiếu bởi một manifest active không được xóa. GC cần hiểu:

~~~text
Live manifests
  -> required baseline artifacts
  -> incremental/log artifacts
  -> object versions
  -> key references
~~~

Nếu manifest bị publish trước khi artifacts tồn tại bền, GC hoặc restore process có thể quan sát một backup “complete” nhưng thiếu bytes.

### 17.5. Backup chain length ảnh hưởng RTO

Restore một full + 100 incrementals có thể tốn nhiều time/metadata/objects hơn một full mới, dù total stored bytes nhỏ. Cần thử **actual restore throughput and dependency resolution**, không chỉ tối ưu storage bill.

## 18. Kiểm soát retention của WAL/oplog/commit logs

Log retention phải bao phủ **oldest required recovery boundary** với headroom và source pressure.

### 18.1. Bài toán tốc độ log

Giả sử:

~~~text
Average committed log production: 30 MiB/s
Full snapshot duration:           6 hours
Safety reserve:                   2 hours
~~~

Lượng log thô cho 8 giờ nếu tốc độ ổn định:

\[
30\ \mathrm{MiB/s}\times8\times3600
=864\,000\ \mathrm{MiB}
\approx843{,}75\ \mathrm{GiB}
\]

Chưa tính compaction, compression, traffic peaks, per-shard skew, filesystem overhead và replication backlog. Nếu source chỉ giữ 100 GiB và không archive song song, khả năng giữ đủ log là đáng nghi.

### 18.2. Không chờ backup xong mới xuất log nếu retention ngắn

Nếu log window 2 giờ nhưng snapshot mất 6 giờ, bắt đầu log archive **sau** snapshot có thể bỏ những committed changes đầu phiên. Phải có **log archiving/pinning before or during snapshot** theo engine.

### 18.3. Headroom phải tính worst-case

Ngày lễ hoặc batch import có thể tăng write rate gấp 5. Retention theo average có thể cạn trong một giờ. Theo dõi:

- Archive rate/byte backlog.
- Oldest log still retained.
- Last contiguously archived segment.
- Log disk used and free.
- Expected snapshot duration remaining.
- Per-shard max delay.

### 18.4. Archive pipeline cũng có failure modes

- Object storage throttling/outage.
- KMS unavailable.
- Network egress saturation.
- Insufficient local staging disk.
- Corrupted/partial upload.
- Wrong permissions/expiration.
- Worker checkpoint ahead of durable upload.

Một collector báo “đã đọc WAL” không đồng nghĩa WAL **đã được backup repository bảo quản bền vững**.

### 18.5. Missing log segment: không sửa bằng `LATEST`

Nếu cần restore L1000→L2000 nhưng segment L1300→L1400 mất, không được nhảy qua và tuyên bố PITR thành công. Cần:

- Chọn một valid later full snapshot.
- Khôi phục tới trước gap nếu đáp ứng RPO có thể chấp nhận.
- Tìm alternate copy/archive hợp lệ.
- Hoặc công khai recovery gap/data loss và reconciliation plan.

### 18.6. Log archiving có thể ảnh hưởng source

Pinning log quá lâu khiến disk đầy hoặc compaction/recycle không thể tiến. Hệ phải cân bằng backup coverage và live availability bằng storage budget, rate control và alarms, không hy sinh production để giữ vô hạn log cũ.

## 19. Quản lý backup under concurrent compaction/rebalance

NoSQL có thể đổi file layout và shard placement **trong khi dữ liệu logic không đổi**.

### 19.1. LSM compaction

Một LSM engine có thể xóa SSTable cũ sau khi merge thành files mới. Nếu backup job tự copy directory mà không có file pinning/snapshot handle, files có thể biến mất giữa list và open. Cần **snapshot manifest/hardlink/filesystem snapshot/backup API** đúng engine.

### 19.2. MongoDB/WiredTiger page versions

MongoDB có storage engine/cache/journal và replication oplog semantics riêng. Không coi copy live data directory qua ordinary filesystem commands là một online backup hợp lệ. Sử dụng phương pháp supported (logical, physical snapshot/hot backup, managed service backup) theo topology.

### 19.3. Resharding trong lúc backup

Một key có thể chuyển shard A→B khi snapshot quét song song:

~~~text
Scanner A has not yet read the key.
Migration moves key from A to B.
Scanner B already passed its destination range.
~~~

Nếu backup không có cluster-aware snapshot/resharding semantics, key có thể bị **bỏ hoặc xuất hai lần**. Đừng tự quét từng shard không phối hợp rồi ghép thành consistent database image.

### 19.4. Leader election/term change

Trong backup source leader failover, positions/terms có thể thay đổi. Một backup chain cần engine protocol để theo log history và rollback/commit point; không trừ offset của hai epochs như một dãy liên tục.

### 19.5. TTL/compaction và replica divergence

Một replica đang chậm có thể giữ files/rows cũ khác primary. Lấy physical backup từ một replica không đủ eligibility có thể tạo recovery point thấp hơn kỳ vọng. Chọn **healthy/caught-up/appropriate read source** theo backup tool và write concern; không chỉ ưu tiên follower vì ít tải.

### 19.6. Snapshot nhiều volume

Nếu WAL ở volume V1 và data files ở V2, chụp volume snapshots tuần tự không có nhóm atomic/coordinated snapshot có thể tạo inconsistent crash image. Cần **multi-volume consistency mechanism hoặc documented recovery ordering**.

### 19.7. Backup từ replica để giảm tải leader

Đó có thể là một chiến lược, nhưng phải tính:

- Replica đã applied/durable tới đâu?
- Backup tool có hỗ trợ từ secondary/follower?
- Thao tác backup ảnh hưởng replication apply/catch-up?
- Có snapshot/log cut nối tới authoritative source?
- Có thể ghi nhận exact restorable position không?

Backup từ follower chậm không tự đạt RPO chỉ vì follower là một bản sao dữ liệu.

## 20. Online backup và ảnh hưởng lên hiệu năng cụm

Backup là workload thật, tiêu thụ:

- Storage read IOPS/throughput.
- Page cache / DB cache.
- CPU cho compression/checksum/encryption.
- Memory cho buffers.
- Network egress và object-storage uploads.
- WAL/log retention space.
- Rebalance/compaction bandwidth.

### 20.1. Scan làm mất cache locality

Một full scan 50 TiB có thể đẩy hot pages của point reads ra khỏi cache. Người dùng thấy p99 tăng, dù backup chỉ “đọc”. Nên đo cache misses, device queue, page cache churn và read traffic theo source.

### 20.2. Backup tác động write latency

Nếu backup copy cạnh tranh disk với WAL fsync/compaction, write p99 tăng dù logical write QPS không đổi. Cần:

- Rate-limit backup I/O.
- Chọn backup source phù hợp.
- Tránh trùng heavy maintenance windows.
- Điều chỉnh concurrency theo live SLO.
- Có stop/throttle trigger khi latency vượt ngưỡng.

### 20.3. Một budget minh họa

~~~yaml
backup:
  maxConcurrentReaders: 3
  maxReadMiBPerSecond: 250
  maxUploadMiBPerSecond: 200
  maxBufferMiB: 1024
  pauseWhen:
    criticalWriteP99MsAbove: 600
    walFreeGiBBelow: 100
  resumePolicy: "from durable checkpoint"
~~~

Đây là **policy mẫu**, không phải config chuẩn cho mọi NoSQL engine.

### 20.4. Nguồn lực archive còn quan trọng hơn backup full

Nếu backup full được throttle mạnh nhưng log production tiếp tục cao, archive spool có thể đầy. Throttle phải được thiết kế cùng **log retention and catch-up**, không chỉ giảm load của scanner.

### 20.5. Mục tiêu đo

Một backup hoạt động an toàn khi:

~~~text
Live API SLO remains acceptable.
No source log coverage gap.
Backup objects are durably stored.
Snapshot/metadata boundaries remain valid.
Archive backlog stays within budget.
Restore drill succeeds from published manifest.
~~~

“Backup job chạy nhanh hơn 30%” không đủ là thành công nếu làm p99 API xấu hoặc bỏ log segments.

## 21. An ninh của backup repository và anti-ransomware

Một cluster multi-AZ không bảo vệ backup khỏi một credential có quyền xóa tất cả objects.

### 21.1. Các lớp bảo vệ

- Backup repository tách quyền khỏi application write principal.
- Write-once/immutability/object lock nếu hạ tầng hỗ trợ và được cấu hình đúng.
- Versioning và delete protection.
- Encryption at rest/in transit.
- Offsite/cross-region copy theo residency policy.
- KMS key-retention kế hoạch tương ứng backup retention.
- Separate recovery role với approval/audit.
- Verification và restore drills định kỳ.

### 21.2. Không lấy “replicas nhiều vùng” thay thế backups

Một accidental delete hoặc ứng dụng deploy bug có thể replicate ngay sang mọi vùng. Immutable backup với retention và isolated restore plan giúp bảo vệ nhiều tình huống **logical/cyber corruption** mà replication không giải quyết.

### 21.3. Kiểm tra quyền khôi phục riêng

Không cho backup job service account vừa ghi source vừa xóa mọi backup generations nếu không cần thiết. Restore operator cần quyền giải mã/đọc backups khi khẩn cấp nhưng phải có audit/least privilege. Kiểm thử **emergency break-glass procedure** trên môi trường được cho phép.

### 21.4. Backup độc lập với region failure

Nếu backup repository nằm cùng region với database mà mục tiêu chống mất toàn region, phải có copy/retention ở failure domain khác hoặc một dịch vụ managed được cam kết tương đương. Chỉ có three-AZ data replicas trong một region không đạt DR objective chống region failure.

### 21.5. Dữ liệu bị xóa và chính sách lưu giữ

Retention để chống ransomware có thể xung đột yêu cầu deletion/privacy nếu thiếu policy. Phải thiết kế dữ liệu backup, key revocation, deletion ledger, expiration và restore guard theo quy định áp dụng; không giữ dữ liệu vô hạn vì lý do “càng nhiều backup càng an toàn”.

## 22. MongoDB: logical dump, oplog, physical snapshots và sharded clusters

MongoDB là ví dụ điển hình cho việc **cùng một sản phẩm có nhiều backup procedures khác nhau**, tùy standalone, replica set, sharded cluster hay managed service. Không trộn guarantees giữa các chế độ.

### 22.1. `mongodump` là logical export

Ví dụ shell minh họa:

~~~bash
mongodump --uri="mongodb://backup-user@replica-hosts/?replicaSet=orders-rs" --out=/secure/backup/orders
~~~

Đây chỉ là command shape, chưa xử lý secrets/TLS/output/storage/policy. Đừng đặt password vào command line lịch sử. Khi dữ liệu thay đổi trong quá trình quét, **ordinary logical dump không tự tạo global consistent snapshot cho mọi namespaces/shards**.

### 22.2. Oplog-assisted dump/replay trong trường hợp được hỗ trợ

Một số MongoDB Database Tools hỗ trợ `mongodump --oplog` và `mongorestore --oplogReplay` trong những topology/use cases nhất định. Ý tưởng là **ghi lại oplog changes xảy ra trong dump và replay chúng cùng baseline**, theo đúng điều kiện hỗ trợ của tool.

~~~text
Start logical dump with supported oplog capture.
Dump documents/collections.
Retain oplog entries covering modifications during dump.
Restore baseline and replay captured oplog.
~~~

Phải xác minh **phiên bản tools, replica-set topology, phạm vi dump, oplog window và restrictions**. Không áp nguyên recipe đó lên sharded cluster rồi tuyên bố có global consistent backup.

### 22.3. Oplog retention

Nếu dump kéo dài hơn oplog window và source đã truncate required changes, khả năng nối log bị mất. Cần theo dõi oplog capacity, write rate, first retained position và tool error handling.

### 22.4. Sharded MongoDB

Một sharded cluster có:

- Nhiều shards (thường là replica sets).
- Config servers và metadata/catalog.
- Routers `mongos`.
- Cross-shard transactions/resharding/balancer behavior.

Tự dump từng shard độc lập ở các thời điểm khác nhau **không tự tạo transactionally consistent cluster-wide state**. Cần snapshot/backup procedure được MongoDB hoặc managed service hỗ trợ cho **sharded cluster và phiên bản đó**, bao gồm metadata và transaction/rebalance semantics.

### 22.5. Physical snapshots

Filesystem/volume snapshot có thể hữu ích nếu storage engine và documented procedure đảm bảo recovery correctness, đặc biệt với journal/data volumes. Không dùng `cp -r` live data directory làm giải pháp mặc định. Phải tính multi-volume consistency, journaling, snapshot handle, log continuation và identity khi khởi động restored member.

### 22.6. MongoDB Atlas/managed backups

Managed deployments có thể cung cấp snapshots/PITR với window và restore workflows riêng. Cần ghi:

~~~text
Cluster/tier/region supported?
Snapshot frequency and retention?
PITR time granularity and window?
Restore in-place or new cluster?
Index/schema/users/network config included?
Encryption/key permissions?
Sharded transactions and topology behavior?
~~~

Không suy từ việc Atlas/managed backup thông báo `snapshot complete` rằng một service Java mới sẽ tự kết nối đúng endpoint/permissions sau restore.

### 22.7. Change Streams không tự là full backup

Change stream thường không chứa toàn bộ historical state trước khi subscription, retention hữu hạn và delete payload có thể khác update payload. Để rebuild từ zero cần **initial state + complete change range + schema/delete semantics**, hoặc dùng native backups.

### 22.8. Một thí nghiệm cần có

Trong staging replica set:

1. Tạo 100.000 synthetic Orders.
2. Chạy writes/inserts/deletes khi logical backup.
3. Restore theo tool-supported procedure vào cluster isolated.
4. So state tại documented recoverable boundary, including deletes.
5. Kiểm tra backup phải fail nếu oplog window không đủ.

Không kiểm tra bằng cách so restore với **source live hiện tại** mà không có cùng consistent cut; source có thể tiếp tục thay đổi sau boundary.

## 23. Cassandra/ScyllaDB: SSTable snapshots và commit log

Với Cassandra/ScyllaDB, dữ liệu persistent thường được lưu dạng SSTables/LSM artifacts; snapshot có thể giữ immutable file generations để sao chép an toàn, tùy engine/version/tool.

### 23.1. `nodetool snapshot` là node/table scoped mechanism

Ví dụ Cassandra, với quyền và môi trường thích hợp:

~~~bash
nodetool snapshot -t backup-orders-20261114 orders
~~~

Tên/cú pháp flags phụ thuộc version; đây là minh họa cho **keyspace snapshot** trên một node. Snapshot có thể liên quan tới flush/memtables theo implementation; hãy dùng exact documented procedure.

Quan trọng: **Một `nodetool snapshot` trên một node không tự là global, transaction-consistent snapshot của tất cả partitions trên mọi replicas trong cluster.**

### 23.2. Scope cần xác định

- Những keyspaces/tables được bảo vệ.
- Những nodes chứa replicas cho mỗi token range.
- Topology/DC/RF/snitch configuration.
- Schema definitions.
- SSTable format/version/manifest/checksums.
- Commit-log/CDC/incremental policy.
- Tombstone/TTL/repair semantics.

### 23.3. Incremental backup và commit-log archiving

Cassandra có những cơ chế incremental backup liên quan SSTable flush/backup và commit logs khác nhau. **Không tự cho rằng bật incremental SSTable backups tạo một PITR solution complete**. Muốn point-in-time recovery phải xác định baseline, log/archive coverage, consistency scope và documented restore procedure.

### 23.4. Repair/tombstone retention

Khi restore một replica snapshot cũ, nếu các replicas khác đã có delete tombstones hoặc mutations mới, cần tuân theo protocol restore/rebuild/repair của engine. Nếu tombstone đã được dọn hoặc timestamp/conflict semantics khác, dữ liệu cũ có thể được tái xuất hiện trong một số recovery scenarios.

### 23.5. Cluster topology và token ownership

Snapshot artifacts của node N ở thời điểm token ownership T0 không được gán bừa cho node M sau khi token ranges đã rebalance. Cần xác định data-range ownership và tool support cho restore sang cluster mới hoặc khôi phục một node.

### 23.6. Snapshot giữa nhiều datacenters

Nếu DC1 và DC2 replicates asynchronous/concurrent writes, chụp snapshots riêng mỗi DC không tạo tự động **một global causal cut**. Chọn datacenter/consistency và restore strategy phù hợp business.

### 23.7. ScyllaDB Manager và vendor tools

ScyllaDB có tool/manager backup orchestration theo phiên bản. Chọn native supported backup/restore mechanisms, kiểm tra snapshot consistency, SSTable retention và incremental/restore guarantees của release cụ thể; không áp nguyên command Cassandra cho mọi Scylla deployment.

### 23.8. Cassandra validation examples

~~~text
Can the restored cluster start with expected schema?
Do RF/DC/rack settings match target topology?
Do token ranges contain expected keys?
Are deletes and TTL semantics preserved?
Are LWT/conditional writes and timestamps safe after restore?
Does anti-entropy/repair converge safely?
~~~

Không chạy repair trên restored/production cluster một cách máy móc trước khi xác định identity và mục tiêu khôi phục.

## 24. Redis: RDB snapshot, AOF và replication không phải backup

Redis có nhiều deployment modes; nếu Redis chỉ là cache rebuildable, backup có thể không cần. Nếu nó giữ durable business state, cần thiết kế persistence/backup khác.

### 24.1. RDB snapshot

RDB là một biểu diễn snapshot dataset theo cơ chế Redis. `BGSAVE` có thể tạo snapshot trong lúc primary tiếp tục nhận writes, thường dùng background process/copy-on-write behavior tùy platform/version.

~~~text
t0 Redis begins background snapshot.
t1 Writes continue.
t2 RDB snapshot file completes.
~~~

Một RDB snapshot thường đại diện một trạng thái thời điểm snapshot theo engine, **không chứa tự động mọi writes mới sau boundary**. Cần hiểu RPO nếu chỉ dùng RDB định kỳ.

### 24.2. AOF persistence

Append Only File (AOF) ghi các commands/mutations theo configured persistence policy. AOF có thể hỗ trợ recovery tiến gần hơn tới các writes mới, nhưng durability không phải mặc định “mọi command đã ACK đều fsync bền tức thời”; phụ thuộc `appendfsync`/AOF rewrite/OS failure modes.

### 24.3. RDB + AOF không phải chỉ ghép hai file tùy tiện

Redis versions có thể sử dụng **multi-part AOF** với base/incremental artifacts và manifest. Sao chép live files không theo documented backup/atomic rotation method có thể tạo một bộ không đầy đủ. Cần backup procedure đúng Redis version/config/persistence mode.

### 24.4. Copy-on-write memory overhead

Trong lúc background save/rewrite, active writes có thể làm tăng copy-on-write memory usage. Khi RAM/cgroup limit thấp, một backup job có thể gây memory pressure/OOM. Theo dõi fork latency, COW size, persistence status và free RAM.

### 24.5. TTL/expiration và cache semantics

Redis keys có expiration; backup/restore có thể tái hiện expiry behavior theo timestamps/engine policy. Một session đã hết hạn sau thời gian restore **không được coi active** chỉ vì backup trước đó còn key.

### 24.6. Replication không phải independent backup

Primary và replicas có thể cùng nhận `DEL`, data corruption về mặt business hoặc command xấu. Redis Cluster/Sentinel failover giúp availability trong phạm vi, không thay immutable backup/PITR.

### 24.7. Redis Cluster

Redis Cluster phân keys theo hash slots trên multiple primaries. Một RDB/AOF của một node **không chứa toàn bộ cluster dataset**. Backup cần group coverage, slot assignment/cluster identity và restore procedure qua tất cả primaries/shards theo time semantics.

### 24.8. Khi nào nên bỏ cache rồi rebuild?

Nếu Redis chỉ là derived cache từ MongoDB/Cassandra source:

~~~text
Restore authoritative NoSQL.
Invalidate old cache namespace/generation.
Rebuild cache lazily or by bounded warm-up.
~~~

Không backup cache stale rồi nạp vào môi trường đã restore về recovery point cũ hơn, vì cache có thể chứa **future values** so với source mới.

## 25. DynamoDB: on-demand backup và PITR theo table/resource

DynamoDB là managed NoSQL; service cung cấp backup/recovery features theo table và các điều kiện service hiện hành. Không tự copy storage files hoặc đọc WAL trên host.

### 25.1. On-demand table backup

Một on-demand backup có thể tạo recovery artifact theo service contract, không cần ứng dụng dừng writes. Phải kiểm tra table/index scope, encryption, retention và restore API của dịch vụ.

### 25.2. Point-in-time recovery

PITR cho phép khôi phục tới một điểm nằm trong **cửa sổ được dịch vụ hỗ trợ** cho bảng được bật tính năng. Những details như available time range, granularity, region, restore destination và feature limitations cần lấy từ tài liệu tại phiên bản triển khai.

### 25.3. Restore thường tạo tài nguyên mới

Trong nhiều workflows DynamoDB, restore tạo **table mới** thay vì ghi đè table đang chạy. Điều này giúp validate/route cutover, nhưng ứng dụng phải:

- Chuyển table name/ARN/endpoint configuration.
- Khôi phục/đối chiếu IAM/streams/TTL/autoscaling/capacity/tags/global table membership theo feature support.
- Kiểm tra indexes và table settings.
- Đối soát outbox/consumer checkpoints.
- Bảo vệ clients đang đọc/ghi table cũ trong cutover.

Không giả định mọi operational setting tự được phục hồi cùng item data.

### 25.4. DynamoDB Streams không thay PITR

Streams giữ changes trong cửa sổ hữu hạn, phụ thuộc stream view type và shard sequencing. Nó phù hợp event-driven/CDC trong phạm vi, nhưng **không tự chứa full historical baseline** và không phải bản backup durable dài hạn.

### 25.5. Global Tables cần scope theo region

Nếu Global Tables replicate nhiều regions, một table backup/restore của Region A không mặc nhiên tái tạo đủ conflict history/settings/routing của toàn Global Table. Cần region-specific and global table recovery plan.

### 25.6. TTL và deletes

DynamoDB TTL deletion có thời gian xử lý bất đồng bộ; restore cần bảo vệ business expiration invariants và hiểu stream record behavior theo region/table mode. Không dùng TTL worker như cơ chế **exact-time deletion** hoặc backup consistency cut.

### 25.7. Application-level consistency

PITR một bảng Orders không tự đồng bộ với Payment table/object storage/queue. Nếu transaction/business invariants trải nhiều tables hoặc systems, restore cần **coordinated or compensating recovery protocol**.

## 26. Azure Cosmos DB for NoSQL: continuous/periodic backup modes

Cosmos DB có managed backup modes/capabilities phụ thuộc account configuration/region/API. Một số chế độ hỗ trợ periodic backups, một số hỗ trợ continuous backup/PITR với constraints riêng.

### 26.1. Phải ghi rõ mode và scope

~~~text
Account API kind and mode
Continuous or periodic backup
Target region
Restore point/window
Containers/databases included
Account-level configuration dependencies
Encryption key and identity dependencies
~~~

Không suy “Cosmos DB có backup” nghĩa mọi tài khoản đều có cùng recovery granularity hoặc multi-region consistency guarantees.

### 26.2. Transactional batch scope

Một transaction trong Cosmos DB for NoSQL có scope logical partition theo sản phẩm; điều đó không tự tạo **atomic cut of all containers/regions** tại một user-chosen time.

### 26.3. Change feed không thay full restore

Change feed modes khác nhau về latest versions, deletes và history. Để dùng feed tái tạo data sau snapshot, cần baseline, start position, continuation tokens, partition range changes, retention và delete semantics. Không coi một feed mode chỉ phát current state là audit log đầy đủ.

### 26.4. Restore sang tài nguyên cách ly

Sau restore, kiểm tra account/database/container identities, partitions, throughput/RU configs, region routing, consistency mode, IAM/keys và application connection settings. Không route production traffic đến target khi chưa validate source watermark/schema.

## 27. Elasticsearch/OpenSearch: snapshots không phải một global instant cho mọi shards

Search engines có native snapshot repository APIs lưu index/shard data và metadata theo version/feature scope.

### 27.1. Snapshot khi indexing vẫn chạy

Engine có thể chụp snapshots trong lúc active writes/indexing. Snapshot thường ghi **một dải tiến độ theo các shards** theo documented API; **không tự xem đó là một transactionally consistent cut toàn cluster tại đúng một wall-clock instant**.

### 27.2. Index vs cluster state

Một snapshot có thể bao gồm selected indexes/data streams và optional cluster state/feature states tùy API/config. Cần inventory:

- Index mappings/settings/templates.
- Ingest pipelines.
- Aliases/ILM policies.
- Security/feature states.
- Repository registrations/credentials.
- External application configurations.

Không tự suy mọi resource operational nằm trong snapshot mặc định.

### 27.3. Search là read model hay source of truth?

Nếu search index được xây từ Order source:

~~~text
Restore authoritative Orders.
Recreate search schema/mapping.
Rebuild index from source / replay CDC.
Validate before alias cutover.
~~~

Nếu search index chứa annotations/business state không tồn tại ở nguồn khác, nó **phải được bảo vệ như source data**, không đơn thuần là cache.

### 27.4. Index refresh/visibility sau restore

Một index đã restore shards thành công vẫn có thể đang recovery/rebalance/cold cache, làm search p99 tăng. RTO phải tính search readiness/alias/routing và data freshness, không chỉ API snapshot restore success.

### 27.5. Snapshot repository và version compatibility

Một snapshot có format/index compatibility constraints theo engine versions. Phải kiểm tra matrix restore chính thức, đặc biệt khi đổi major versions hoặc chuyển giữa Elasticsearch và OpenSearch.

## 28. Bảng so sánh nhanh các cơ chế

| Hệ | Đơn vị backup thường gặp | Trọng tâm khi vẫn ghi | Phạm vi cần bổ sung |
| --- | --- | --- | --- |
| MongoDB replica set | Logical dump + oplog trong trường hợp hỗ trợ, physical/managed snapshot | Oplog capture window, read/write concern | Index/schema/users, oplog, keys |
| MongoDB sharded | Cluster-aware backup | Cross-shard transactions/metadata/resharding | Config servers, shards, recovery cut |
| Cassandra/ScyllaDB | SSTables/node snapshots, managed backup | Multi-node consistency, flush/commit logs | Schema, token ranges, repair/tombstones |
| Redis | RDB/AOF/versioned artifacts | COW memory, AOF fsync/rewrite, slot coverage | AOF manifest, TTL, per-shard files |
| DynamoDB | Managed table backups/PITR | Table/region/time restore scope | IAM/settings, streams, global table policy |
| Cosmos DB | Managed backup/restore modes | Account/region/consistency scope | Container config, keys, change feed |
| Elasticsearch/OpenSearch | Native snapshot repository | Per-shard snapshot timing, index changes | Cluster/index/feature states, aliases |

Đây là **bảng khái quát kiến trúc**, không thay cho tài liệu version-specific của từng provider. Chọn công cụ theo **restore guarantee cần thiết**, không chỉ tốc độ copy.

## 29. Thiết kế kiến trúc online backup cho Order Service

Một phương án logical architecture:

~~~mermaid
flowchart LR
    API["Java Order Service"] --> DB["NoSQL source of truth"]
    DB --> SNAP["Native snapshot / backup agent"]
    DB --> LOG["Engine-supported log archiver"]
    SNAP --> REPO["Protected backup repository"]
    LOG --> REPO
    META["Schema / config / keys references"] --> MAN["Backup manifest"]
    REPO --> MAN
    MAN --> VALID["Isolated restore drill"]
    VALID --> REPORT["Recovery validation report"]
~~~

### 29.1. Các vai trò

**Application**

- Tiếp tục ghi theo write contract.
- Dùng idempotency và transaction/outbox patterns phù hợp.
- Giám sát p99/throughput/errors khi backup chạy.

**Backup coordinator**

- Yêu cầu database-native snapshot boundary.
- Duy trì source log archiving/retention khi cần.
- Theo dõi artifact progress/checksum.
- Publish complete manifest **sau** các checks vật lý/protocol.

**Repository**

- Lưu artifacts + metadata bền.
- Bảo vệ trước accidental deletion/security incident.
- Cung cấp versioning, retention, audit.

**Restore controller**

- Đọc manifest immutable.
- Tạo môi trường target cách ly.
- Áp base backup + changes theo engine.
- Validate source/target invariants trước cutover.

### 29.2. State machine của backup

~~~mermaid
flowchart TD
    A["REQUESTED"] --> B["ESTABLISHING_BOUNDARY"]
    B --> C["COPYING_BASE"]
    C --> D["ARCHIVING_REQUIRED_CHANGES"]
    D --> E["VERIFYING_ARTIFACTS"]
    E --> F["PUBLISHING_MANIFEST"]
    F --> G["COMPLETE"]
    B --> X["FAILED / RETRYABLE"]
    C --> X
    D --> X
    E --> X
    F --> X
~~~

Trong một số sản phẩm, archiving phải bắt đầu **trước khi establish boundary** hoặc chạy song song với snapshot. State machine chỉ mô tả milestones điều phối, không thay thế source-specific order constraints. Một job không nên ghi `COMPLETE` khi vẫn chưa biết log continuity.

### 29.3. Trạng thái restore độc lập

~~~text
RESTORE_REQUESTED
  -> RESOLVING_DEPENDENCIES
  -> COPYING_BASE
  -> APPLYING_HISTORY
  -> ENGINE_RECOVERING
  -> VALIDATING
  -> READY_FOR_CUTOVER
  -> SERVING
~~~

Nếu thiếu artifact hoặc khóa giải mã, **fail closed** ở bước dependency resolution; không dựng một target có data gap rồi route traffic.

### 29.4. Publish một backup khác publish một recovery capability

Một snapshot hoàn chỉnh ở L1000 có thể là **backup usable** cho L1000, dù ongoing log archiving đang tiến tới L2000. Có thể publish hai mốc riêng:

~~~text
Base snapshot complete at L1000.
Last continuous log archived through L1800.
Latest verified recoverable target: L1800.
~~~

Không cần chờ vô hạn tới “current latest log” để có recovery set; nhưng phải xác định target cuối **đã được lưu bền và continuous**.

## 30. Ví dụ Java: kiểm tra chuỗi log không có gap

Mã sau mô phỏng **một log tuần tự có số nguyên liên tiếp trên một partition**. Nó **không phải parser WAL của MongoDB/Cassandra/Redis**, và không thay được các vendor-native recovery validators. Mục tiêu là minh họa một quy tắc: muốn restore từ cut đến target, các log segments phải bao phủ **liên tục** các vị trí cần thiết.

~~~java
import java.util.Comparator;
import java.util.List;

public final class ArchiveCoverage {
    public record Segment(
        long firstInclusive,
        long lastInclusive,
        String artifactId
    ) {
        public Segment {
            if (firstInclusive < 0 || lastInclusive < firstInclusive) {
                throw new IllegalArgumentException("Invalid segment range");
            }
            if (artifactId == null || artifactId.isBlank()) {
                throw new IllegalArgumentException("Missing artifact ID");
            }
        }
    }

    public static void assertContiguous(
        long snapshotCut,
        long target,
        List<Segment> segments
    ) {
        if (snapshotCut < 0 || target < snapshotCut) {
            throw new IllegalArgumentException("Invalid restore positions");
        }
        if (target == snapshotCut) {
            return; // No post-snapshot changes needed.
        }
        if (snapshotCut == Long.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid snapshot position");
        }

        long nextRequired = snapshotCut + 1L;
        var ordered = segments.stream()
            .sorted(Comparator.comparingLong(Segment::firstInclusive))
            .toList();

        for (Segment segment : ordered) {
            if (segment.lastInclusive() < nextRequired) {
                continue; // Segment wholly before required position.
            }
            if (segment.firstInclusive() > nextRequired) {
                throw new IllegalStateException(
                    "Missing source positions starting at "
                    + nextRequired
                    + " before artifact "
                    + segment.artifactId()
                );
            }
            // The current segment covers nextRequired.
            if (segment.lastInclusive() >= target) {
                return;
            }
            nextRequired = segment.lastInclusive() + 1L;
        }
        throw new IllegalStateException(
            "Archive does not reach target position " + target
            + "; next required: " + nextRequired
        );
    }
}
~~~

### 30.1. Cách sử dụng

~~~java
var ok = List.of(
    new ArchiveCoverage.Segment(1001, 1200, "seg-1"),
    new ArchiveCoverage.Segment(1201, 1500, "seg-2"),
    new ArchiveCoverage.Segment(1501, 1800, "seg-3")
);

ArchiveCoverage.assertContiguous(1000, 1750, ok); // Covered.

var broken = List.of(
    new ArchiveCoverage.Segment(1001, 1200, "seg-1"),
    new ArchiveCoverage.Segment(1301, 1800, "seg-3")
);

ArchiveCoverage.assertContiguous(1000, 1750, broken);
// Throws: missing range starting at 1201.
~~~

### 30.2. Giới hạn của mô hình số nguyên

Log thật có thể có:

- Opaque positions, terms, epochs.
- Non-consecutive IDs.
- Transaction records, abort markers.
- Multiple partitions/shards.
- Compacted histories.
- Cross-shard ordering dependencies.
- Checksums and segment generations.

**Không convert source positions thực sang `long` rồi trừ khi engine không có total-order semantics đó.** Một coverage oracle production phải do database/connector API được hỗ trợ xác nhận hoặc có formal proof về nguồn stream.

### 30.3. Checksum chưa được validate trong ví dụ

Code chỉ xem metadata ranges, **không mở artifacts** để xác minh bytes/checksum. Một `Segment(1001,1200)` do người dùng tự nhập không chứng minh file chứa đủ 200 records. Trước khi publish manifest cần xác minh object receipt, checksums, source identity và recovery-tool compatibility.

## 31. Ví dụ Java: kiểm tra toàn vẹn file backup

Sau khi upload một backup artifact, có thể tính digest trên bytes và so với manifest. Đây là **kiểm tra storage integrity**, không phải Content QA của bài học hoặc kiểm chứng consistency state.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class BackupDigest {
    public static String sha256(Path file) throws IOException {
        final MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }

        try (InputStream source = Files.newInputStream(file);
             DigestInputStream in =
                 new DigestInputStream(source, digest)) {
            byte[] buffer = new byte[1024 * 1024];
            while (in.read(buffer) != -1) {
                // DigestInputStream feeds bytes to the digest.
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

### 31.1. Upload integrity vs remote durability

Nếu chỉ hash local file rồi gửi nó lên object storage, bạn mới xác nhận **local source bytes**. Muốn kiểm tra remote copy cần:

- Upload outcome/ETag/checksum semantics đúng provider.
- Object version/length.
- Repository readback hoặc provider checksum validation.
- Storage retention/access controls.
- Manifest chỉ reference durable committed object version.

Không mặc định một HTTP 200 upload response có cùng nghĩa durability ở mọi storage service nếu chưa đọc contract.

### 31.2. Checksum không thay restore drill

Một file backup có SHA-256 khớp có thể vẫn thiếu `config server` metadata, một WAL segment, KMS access hoặc một index definition. **Chỉ khôi phục vào môi trường thật và kiểm tra invariants mới cho bằng chứng end-to-end.**

## 32. Ví dụ Java: domain metadata để đối soát restore

Một Order record có thể mang version/generation và idempotency key:

~~~java
public record RestorableOrder(
    String tenantId,
    String orderId,
    long generation,
    long version,
    String status,
    String invoiceObjectVersion
) {}

public record RecoveryObservation(
    String keyHash,
    long expectedGeneration,
    long expectedVersion,
    long observedGeneration,
    long observedVersion,
    boolean objectReferenceResolvable
) {}
~~~

### 32.1. Không so bằng `updatedAt` đơn độc

Một restored record có `updatedAt=10:30` chưa chắc chứa đúng committed write. Client clock skew, mutable timestamps hoặc wrong data projection có thể đánh lừa. So **source-authoritative version/generation, checksums/payload projections và commit cut** khi có.

### 32.2. Không cần mọi records cùng “thời gian cuối”

Để restore snapshot tại 10:00, một Order chỉ được cập nhật lần cuối năm ngoái vẫn đúng nếu đó là latest committed state **trước 10:00**. Đừng đòi `updatedAt >= snapshotAt` cho mọi record.

### 32.3. Deletes phải được kiểm tra

Một Order bị delete trước recovery target **phải absent hoặc tombstoned** trong state theo policy. Chỉ so record count có thể bỏ lỡ một delete và một insert sai khiến tổng count không đổi.

### 32.4. Kiểm tra business invariants

Ví dụ:

~~~text
For each PAID order:
  matching payment ledger entry exists.

For each captured payment:
  unique idempotency key exists.

For each invoice object reference:
  exact object version is retrievable.

For each outbox event:
  event identity and source aggregate version are consistent.
~~~

Nếu source backup cắt giữa distributed workflows, invariants có thể cần **reconciliation** chứ không thể chỉ assert một cách cơ học ngay sau restore.

## 33. Quy trình restore an toàn khi backup được chụp trong lúc ghi

### 33.1. Giai đoạn 1 — Chọn recovery target

Xác định:

- Incident xảy ra khi nào.
- Nghi vấn corruption bắt đầu từ khi nào.
- Recovery target hợp lệ **trước corruption** hay gần nhất theo RPO.
- Available baseline/log chain/region.
- Business impact nếu bỏ mutations sau target.
- Tình huống **một số external operations đã thực hiện sau target**.

Nếu accidental delete xảy ra lúc 11:15, chọn PITR 11:14 có thể cứu data, nhưng transactions từ 11:14–11:30 cần được xử lý tiếp riêng; không tự coi tất cả chúng không tồn tại trong thế giới thật.

### 33.2. Giai đoạn 2 — Cách ly target

~~~text
Create isolated restore cluster/account.
Disable outgoing payment/email/webhook side effects.
Block production writes until authority decisions are made.
Do not reuse source cluster/member identity blindly.
Set secure credentials and encryption key access.
~~~

Điều này tránh việc restored outbox/consumer publish lại events và gây double charge/email.

### 33.3. Giai đoạn 3 — Xác minh dependencies

- Manifest complete, signed/authorized if required.
- Full/incremental/log artifacts có đủ.
- Checksums/length/object versions phù hợp.
- Engine/version/format supported.
- KMS keys/permissions còn hợp lệ.
- Schema/config/application versions có thể chạy.
- Object-storage versions cần thiết còn.

Nếu thiếu một dependency bắt buộc, **dừng trước cutover**, không tự phục hồi một phần rồi gắn `READY`.

### 33.4. Giai đoạn 4 — Restore base + replay history

Theo documented engine procedure:

~~~text
Restore base snapshot at cut L0.
Recover engine internal files/transactions.
Replay or apply changes through target Lt.
Ensure correct commit/abort and delete semantics.
Rebuild or verify indexes if required.
Do not replay effects beyond Lt unless policy says so.
~~~

Các thao tác này **không tương đương** việc viết một custom loop đọc JSON và `upsert` nếu source có distributed transaction, timestamp conflicts hoặc complex storage metadata.

### 33.5. Giai đoạn 5 — Reset/reconcile dependent systems

- Cache: invalidate hoặc version/epoch rotate.
- Search/read models: rebuild hoặc rewind/position-align.
- CDC/outbox: xác định start position và replay idempotently.
- Message broker: không dùng stale consumer offsets để bỏ events.
- Object storage: đối chiếu referenced object versions.
- External systems: reconcile payments/reservations/shipments.
- Auth/user/session stores: xác định session invalidation policy.

### 33.6. Giai đoạn 6 — Validation

Chạy một nhóm assertions:

~~~text
Database is readable and accepts permitted test writes.
Expected namespaces/schema/indexes exist.
Counts and checksums match a consistent comparison scope.
Critical sample keys have correct versions and values.
Deletes and TTL are respected.
Cross-entity business invariants checked/reconciled.
Object references resolve to expected versions.
Application smoke tests pass without real side effects.
~~~

### 33.7. Giai đoạn 7 — Cutover

Chỉ route traffic khi:

1. Recovery authority được xác định.
2. Old system/fork được fenced hoặc chặn conflicting writes.
3. Client endpoints/DNS/secrets đổi có kiểm soát.
4. Read model/cache policy phù hợp restored source.
5. RPO/data gap được chấp nhận/công bố khi có.
6. Rollback plan và monitoring đã sẵn sàng.

### 33.8. Giai đoạn 8 — Theo dõi sau phục hồi

- Read/write p50/p95/p99.
- Business operation success/error rate.
- Unexpected duplicate events/charges.
- CDC backlog.
- Cache/search freshness.
- Replication health và storage capacity.
- New backup generation from recovered authority.

Một restore thành công lúc database khởi động nhưng gateway vẫn dùng endpoints cũ **chưa đạt RTO end-to-end**.

## 34. Khôi phục một phần và “phục hồi chỉ một khách hàng”

Tình huống: Tenant A cần lấy lại Orders tại 10:00, còn Tenant B không được rollback.

### 34.1. Cluster PITR toàn bộ không tự đáp ứng

Nếu restore cả cluster về 10:00, Tenant B có thể mất những writes sau 10:00. Một lộ trình an toàn hơn thường là:

~~~text
Restore snapshot to isolated temporary cluster.
Extract tenant A data under consistent scope.
Compare tenant A current and historical versions.
Apply a domain-aware repair plan to live source.
Use version/idempotency guards and audit every mutation.
~~~

### 34.2. Khó khăn của references

Tenant A records có thể tham chiếu:

- Shared catalog/product IDs.
- Payment ledger.
- External invoice objects.
- Global unique indexes.
- Cross-tenant aggregate caches.

Không chỉ copy một JSON document rồi coi đã phục hồi domain state.

### 34.3. Không ghi đè những writes mới hợp lệ

Nếu live Tenant A có Order v15 nhưng backup chứa v12, một blind-upsert sẽ làm mất updates từ v13–v15. Cần **compare versions, lựa chọn fields/history và business approval** cho từng loại correction.

### 34.4. GDPR/privacy deletion và tenant restore

Nếu dữ liệu đã bị xóa vì yêu cầu hợp lệ sau backup, restore cũ phải áp dụng deletion ledger/policy tương ứng trước khi dữ liệu được phục vụ. Backup retention và data-deletion compliance là thành phần của restore.

## 35. Case study A — Backup hoàn thành nhưng thiếu mutation trong lúc quét

**Tình huống:** Một team tự viết Java scanner, quét 10 triệu documents và gửi JSON sang object storage.

~~~text
10:00 Start Scan.
10:03 Scan O101 version 2.
10:05 User updates O101 to version 3.
10:30 Finish Scan.
10:31 Subscribe to Change Stream using LATEST.
11:00 Source fails.
~~~

### 35.1. Điều gì bị bỏ sót?

Backup vẫn chứa O101 v2; stream bắt đầu sau update v3 nên không có event ấy. Nếu không có native snapshot boundary hoặc connector capture-before-scan protocol, **O101 v3 nằm trong gap**.

### 35.2. Vì sao tổng record count không phát hiện?

Một `UPDATE` không nhất thiết đổi record count. Backup có đủ 10 triệu JSON documents vẫn sai content.

### 35.3. Cách sửa

Chọn database-native consistent snapshot/PITR hoặc:

1. Khởi động capture từ source position được hỗ trợ trước scan.
2. Spool changes bền, không để hết retention.
3. Quét chunks với version/collision semantics hợp lệ.
4. Áp changes/deletes và checkpoint theo target apply.
5. Chứng minh no-gap trước khi publish backup.

### 35.4. Bằng chứng nghiệm thu

Lặp synthetic writes trong scan, restore và kiểm tra O101 v3 có mặt tại target phù hợp. Chạy fault injection ở các mốc scan, source position và checkpoint.

## 36. Case study B — Backup vật lý đủ files nhưng không khởi động

**Tình huống:** Data SSTable files nằm trên volume A; WAL/commit log nằm trên volume B. Backup job gọi snapshot volume A trước rồi snapshot volume B vài phút sau, không có multi-volume coordination.

~~~text
t0: Snapshot data volume A.
t1: Source commits transactions and rotates logs.
t2: Snapshot log volume B.
~~~

### 36.1. Vì sao có thể lỗi?

Hai snapshots thuộc **hai crash instants**. Data files và WAL trong restored set có thể không thỏa recovery invariant, tùy engine. Có thể thiếu log segment cần cho data files, hoặc log trỏ tới file generation không có.

### 36.2. Cách sửa

Sử dụng **engine-supported multi-volume/online backup procedure**, nhóm snapshot atomic khi storage supports, hoặc thực hiện quiesce/checkpoint phù hợp để tạo recovery set. Đối chiếu exact product recovery semantics; không “sửa” bằng cách đổi thời gian snapshot ngẫu nhiên cho gần nhau.

### 36.3. Bằng chứng cần có

Restore engine thành công, log recovery clean, checksums/version mapping đúng và business records/transactions có state hợp lệ tại advertised boundary.

## 37. Case study C — Chụp follower đang lag

**Tình huống:** Primary đã commit tới L2000; follower backup source mới apply tới L1800. Backup hoàn thành lúc 12:00 và team báo “khôi phục được tới 12:00”.

### 37.1. Sai ở đâu?

`backupFinishedAt=12:00` không đồng nghĩa backup phản ánh writes mới nhất đến 12:00. Nếu chỉ snapshot follower ở L1800, **advertised recoverable cut** có thể chỉ L1800, trừ khi log archive/recovery tool bù được phần còn lại.

### 37.2. Tín hiệu cần đo

- Primary committed/majority positions.
- Follower applied/durable positions.
- Backup source read concern/eligibility.
- Snapshot cut.
- Archived log tail through target.

### 37.3. Cách xử lý

Dùng supported backup source selection/cut protocol, chọn healthy caught-up follower hoặc kết hợp logs như engine cho phép. Nếu follower không đủ điều kiện, backup phải report một **older recovery point**, không gắn nhãn latest.

## 38. Case study D — Xóa dữ liệu rồi restore làm hồi sinh

~~~text
Backup snapshot at 10:00: user profile U1 exists.
10:05: privacy deletion request completes.
11:00: database corrupts.
11:10: restore snapshot from 10:00.
~~~

Nếu chỉ restore snapshot cũ rồi cho public API hoạt động, U1 có thể xuất hiện trở lại. Cần:

- Deletion/tombstone history được bảo vệ.
- Privacy deletion workflow/ledger.
- Restore target lựa chọn đúng điểm thời gian.
- Post-restore deletion reconciliation trước khi phục vụ.
- Audit/approval theo legal/retention policy.

**Không đánh đổi yêu cầu xóa dữ liệu hợp lệ chỉ để rút ngắn RTO.**

## 39. Case study E — Redis backup làm OOM primary

**Tình huống:** Redis primary có memory usage cao, sử dụng background snapshot; active writes lớn làm copy-on-write overhead tăng.

~~~text
Before backup:
  Resident memory near configured/container limit.

During background persistence:
  Write churn increases COW footprint.
  Memory pressure rises.
  Primary process is terminated.
~~~

### 39.1. Tại sao “backup chỉ đọc” vẫn gây lỗi?

Persistence có thể fork/copy-on-write và làm phát sinh additional memory pressure tùy implementation/version. Cần headroom, monitoring và test với **write churn**, không chỉ lượng key data hiện tại.

### 39.2. Biện pháp

Điều tiết writes/persistence timing nếu phù hợp, tăng memory headroom, backup qua supported replica/snapshot mode, giới hạn conflict với AOF rewrite và kiểm tra failover/RPO. Không tắt persistence/durability một cách tùy tiện.

## 40. Case study F — Incremental chain thiếu một segment

~~~text
Full F1 at L1000.
I1 covers L1001..L1200.
I2 should cover L1201..L1500 but upload failed.
I3 covers L1501..L1800.

Manifest incorrectly says recoverableThrough=L1800.
~~~

### 40.1. Hậu quả

Không thể khẳng định restore đúng tới L1800 vì các mutations L1201..L1500 không có source. Checksums của F1/I1/I3 có thể đều chính xác mà recovery **vẫn sai**.

### 40.2. Cách sửa

- Manifest publish chỉ sau khi archive coverage verifier pass.
- Gap detection bằng source positions/segment identities.
- Alert log archive durability backlog.
- Không tự skip missing segment.
- Chọn later valid full snapshot hoặc alternate archive khi cần.

## 41. Case study G — Database restore thành công, file đính kèm mất

~~~text
NoSQL restored Order O900.
Order references invoice object version V12.
Object storage retention deleted V12.
Public API GET /orders/O900/invoice fails.
~~~

### 41.1. Root cause

Recovery scope chỉ bao gồm NoSQL documents, **không bao gồm external object versions**. Một DB backup không chứng minh business entity đã phục hồi đầy đủ.

### 41.2. Giải pháp

Inventory object references/versions, align bucket retention with backup window, có object catalog và verify link integrity trong restore drill. Nếu không còn object version, công bố partial recovery và business repair procedure.

## 42. Case study H — Outbox được restore về quá khứ

**Tình huống:** Source database restore về L1000, nhưng broker consumer/checkpoint vẫn ở L1500.

~~~text
Restored DB outbox contains E1..E100.
Broker already contains E1..E150.
Downstream consumer checkpoint = E150.
~~~

### 42.1. Hai nguy cơ trái nhau

- Nếu app publish lại E1..E100, downstream có thể double-process.
- Nếu connector tiếp tục từ checkpoint E150, những mutations cần tái tạo sau restore có thể bị bỏ qua, tùy recovery plan.

### 42.2. Cần làm gì?

Xây **recovery epoch**, xác định source-of-truth event history, phối hợp idempotency keys/dedup/inbox và connector offsets. Nếu old broker có events vượt recovery target, quyết định business reconcile/compensate trước khi tiếp tục. Không chỉ reset tất cả consumer offsets về earliest và hy vọng đúng.

## 43. Case study I — Khóa KMS không còn

~~~text
Backup artifacts in remote object storage: intact.
SHA-256 checksums: pass.
Encryption key K1: revoked/deleted.
Restore environment: cannot decrypt.
~~~

Một backup có bytes và checksum đầy đủ vẫn **không thể restore**. Cần key lifecycle/rotation policy, key-retention tương ứng backup retention, cross-region decrypt permissions và emergency recovery verification.

Đừng thử lấy plaintext key lưu ra log/worksheet để “dễ restore”; đó là tạo lỗ hổng bảo mật.

## 44. Case study J — Backup đủ nhưng RTO vượt mục tiêu

~~~text
Full backup copy/download: 2 hours
Incremental chain replay: 4 hours
Index rebuild: 3 hours
External object verification: 1 hour
App validation/cutover: 1 hour
Total serial critical path: ~11 hours
Business RTO: 2 hours
~~~

Backup có thể **recoverable** nhưng không đạt RTO. Biện pháp có thể gồm:

- Shorter incremental chains/new full baselines.
- Pre-provisioned standby.
- Parallel restore per shard khi tool hỗ trợ.
- Precomputed object inventories.
- Warm standby/read-model rebuild strategy.
- Faster storage/network/provisioning.

RTO phải đo trong **restore drill đầy đủ**, không suy từ upload duration.

## 45. Case study K — Backup trước thay schema, restore với app version mới

**Tình huống:** Backup lưu schema v4; ứng dụng đã deploy v7, chỉ có serializer v7.

~~~text
Restored DB:
  Orders use amount decimal in schema v4.

New Java service:
  Expects amountMinorUnits long in schema v7.
~~~

Khởi động ứng dụng mới ngay có thể đọc sai/sai tiền hoặc lỗi. Cần:

- Schema bundle và migration version trong manifest.
- Compatible application release hoặc forward migration được kiểm soát.
- Reconciliation/checksums theo business units.
- Rollout/cutover sau smoke tests.

Không coi “database port mở” là proof ứng dụng khôi phục được.

## 46. Case study L — Hai regions, hai snapshots không cùng business cut

Region A nhận order, Region B quản lý payment events. Hai managed backup jobs chạy lúc 10:00 gần nhau.

~~~text
Region A backup boundary: before Order E42 committed.
Region B backup boundary: after Payment E42 committed.
~~~

Hai timestamps gần nhau không chứng minh consistency trên **distributed workflow**. Cần idempotent reconciliation/ledger/event identities hoặc coordinated snapshot protocol được hỗ trợ. Nếu không thể có global cut, ghi rõ **recovery consistency model** và runbook sửa business state sau restore.

## 47. Case study M — Xóa backup base vẫn giữ incrementals

Một retention script xóa full baseline F1 vì “hơn 30 ngày”, nhưng còn các incrementals I2/I3 đang phụ thuộc F1.

**Kết quả:** Chuỗi incremental còn file nhưng không restore được. Giải pháp là retention dựa trên **dependency graph của complete recovery sets**, có dry-run, reference counting và verified alternate baselines trước khi delete.

## 48. Case study N — Backups gây log disk đầy

Một snapshot online kéo dài 14 giờ; source phải giữ nhiều log segments và archival process bị network throttle. WAL volume đầy, writes bị stall.

Cần:

- Dự báo max log production và retention.
- Durable archiving pipeline độc lập.
- Disk free/headroom alarms.
- Bounded snapshot duration/rate.
- Abort/restart/rebaseline procedure nếu coverage không thể giữ.

**Backup không được phép làm sập source một cách bất ngờ** chỉ để giữ một snapshot đã quá hạn.

## 49. Kế hoạch fault injection có kiểm soát

Các thí nghiệm chỉ chạy ở **staging/lab hoặc môi trường được cho phép**, dùng synthetic data, không thực hiện destructive backup tests trên production tùy tiện.

| Tình huống | Fault được tạo | Kết quả cần xác minh |
| --- | --- | --- |
| Write trong scan | INSERT/UPDATE/DELETE giữa chunks | No gap, đúng recoverable cut |
| Snapshot row đến muộn | CDC delete apply trước old snapshot row | Không resurrect |
| Crash scanner | Crash sau target copy trước checkpoint | Retry an toàn |
| Crash archiver | Crash sau upload trước manifest | Không publish false complete |
| Missing log segment | Xóa một archived segment trong lab | Restore bị chặn |
| Oplog retention expired | Hold connector qua retention | Gap được phát hiện |
| Failover trong backup | Leader/term thay đổi | Source identity/position handled |
| Schema migration | Đổi data format giữa scan | Metadata/version handling |
| Resharding | Di chuyển key giữa shards | No missing/duplicate key theo protocol |
| TTL expire | Record hết hạn trong backup | Restore policy đúng |
| Delete/tombstone | Delete sau snapshot cut | Delete được replay |
| Cross-shard transaction | Commit khi snapshot chạy | Không half-transaction theo guarantee |
| KMS unavailable | Disable decrypt permission trong lab | Recovery fails closed |
| Object version missing | Xóa version tham chiếu trong test | Referential check fail |
| Incremental chain gap | Bỏ I2 | Validation fail |
| Storage corruption | Làm hỏng artifact test | Checksum fail |
| Resource stress | Tăng I/O/GC/compaction khi backup | Live SLO và retention vẫn an toàn |
| Consumer checkpoint ahead | Restore DB cũ, giữ broker offset mới | Reconcile được |
| App schema mismatch | Restore v4 với Java v7 | Migration/compatibility gate |
| Region outage | Mất source region trong lab | RPO/RTO/backup availability |

### 49.1. Có phải mọi test đều cần thực thi trên cùng engine?

Không. Một managed NoSQL có thể không cho truy cập WAL hoặc kill replica; thay bằng **provider-supported failure simulation/restore drills** và kiểm tra kết quả ở tầng service. Test phải dựa trên failure model và API có thể điều khiển.

### 49.2. Mỗi test cần kết quả có bằng chứng

Một record:

~~~yaml
testId: "hot-backup-delete-race"
sourceEngineMode: "recorded"
backupId: "test-backup-01"
injectedEvent:
  type: "DELETE"
  key: "synthetic-O102"
  version: 10
expected:
  atRecoveryCut: "ABSENT"
observed:
  result: "ABSENT"
  checksum: "recorded"
status: "PASS"
~~~

Chỉ dùng dữ liệu giả và ghi nguồn/protocol; không công bố pass nếu restore chưa thực sự được chạy đến target cut.

## 50. Runbook xử lý khi backup vẫn chạy mà source bị lỗi

### Bước 1 — Bảo vệ dữ liệu hiện tại

Xác định nguồn authoritative, log retention, replicas, commit positions và những writes đã ACK. Tránh kill/cleanup log archives có thể còn cần để recovery.

### Bước 2 — Xác định backup set hoàn chỉnh gần nhất

Đọc immutable manifests, source identity, snapshots, archived log high-water, checksum/keys, retention. **Không chọn backup mới nhất chỉ vì tên timestamp lớn nhất**.

### Bước 3 — Chọn mục tiêu khôi phục

Nếu corruption xảy ra từ L1800, có thể cần restore trước L1800; nếu mất hạ tầng nhưng dữ liệu không corrupt, cần gần nhất theo RPO. Ghi business quyết định về data loss và external side effects.

### Bước 4 — Chuẩn bị target cách ly

Khởi tạo environment/region/credentials, chặn production side effects, xác nhận keys và restore destination. Không “restore trực tiếp” vào healthy source mà chưa có thay đổi được phê duyệt.

### Bước 5 — Restore theo vendor procedure

Base + log/chain, giữ transaction/delete/schema semantics. Nếu missing artifact, dừng và điều tra alternative complete recovery sets.

### Bước 6 — Đối soát nhiều hệ

Orders/Payments/Outbox/Objects/Indexes/Caches/CDC positions, idempotency, privacy deletes. Đối soát unknown write outcomes trước khi cho payment/notification workflows chạy lại.

### Bước 7 — Cutover và quan sát

Fencing old authority, route clients, load smoke-test read/write, alert version mismatches/duplicates/latency, tạo backup generation mới từ recovered authority.

### Bước 8 — Postmortem

Ghi actual RPO/RTO, last recoverable cut, missing changes, ảnh hưởng người dùng, nguyên nhân failure và coverage gaps, test nào thiếu và yêu cầu sửa quy trình.

## 51. Bài tập thực hành

### Bài 1 — Live copy không phải online backup

Một kỹ sư chạy `cp -r /var/lib/database /backup` trong lúc database đang ghi trên nhiều files.

1. Những loại state nào có thể không nhất quán?
2. Vì sao copy xong với exit code 0 không chứng minh restore được?
3. Khi nào một filesystem snapshot có thể hợp lệ?
4. Điều kiện gì phải biết về journal/WAL, multi-volume và engine?

### Bài 2 — Backup quét 30 phút

~~~text
10:00 Start ordinary paginated Scan.
10:10 Read O100 version 1.
10:20 UPDATE O100 -> version 2 commits.
10:30 Finish scan.
10:31 Subscribe CDC from LATEST.
~~~

1. O100 trong backup có thể là version nào?
2. Mutation v2 có chắc nằm trong CDC không?
3. Đây là gap loại gì?
4. Đề xuất một giao thức có chứng minh không bỏ sót.

### Bài 3 — Snapshot cut và logs

Snapshot tại L1000; archive có toàn bộ log L1001…L1800.

1. Restore tới L1500 cần gì?
2. L1000 có cần replay lại nếu snapshot đã chứa L1000?
3. Nếu replay inclusive ở L1000, phải xử lý gì?
4. Nếu backup archive chỉ tới L1800 mà source đã ở L2000, last recoverable point là gì?

### Bài 4 — Tính dung lượng log

Source tạo trung bình 20 MiB/s commit log; snapshot kéo dài sáu giờ.

1. Ước lượng log bytes trong sáu giờ theo GiB.
2. Nếu archive spool có 100 GiB, có đủ nếu không có consumer draining trong sáu giờ?
3. Với write burst gấp 4, cần thêm safety factor như thế nào?
4. Vì sao retention còn phụ thuộc log segment overhead/compaction?

### Bài 5 — Full + incremental

~~~text
F1 at L1000
I1 L1001..L1200
I2 L1201..L1500  (missing)
I3 L1501..L1800
~~~

1. Có restore đúng tới L1700 được không?
2. Có thể dùng I3 trực tiếp với F1 không?
3. Những lựa chọn hợp lệ khi I2 mất?
4. Retention cleanup phải dùng dependency graph thế nào?

### Bài 6 — Delete race

~~~text
Scanner buffers O101 v10.
Source commits DELETE O101 v11.
CDC target applies DELETE v11.
Scanner later writes O101 v10.
~~~

1. Nếu target dùng blind upsert thì chuyện gì xảy ra?
2. Cần version/tombstone guard ở đâu?
3. Nếu physical snapshot do engine hỗ trợ, điều gì khác với custom scan?
4. Nếu key được tạo lại với generation mới, comparator cần biết gì?

### Bài 7 — TTL

Backup lúc 09:00 chứa Session S1 với expiration 12:00, restore lúc 15:00.

1. Nên cho S1 active hay expired theo business policy?
2. TTL metadata cần được khôi phục thế nào?
3. Khác biệt giữa logical expiration check và physical TTL cleanup?
4. Vì sao so số row ngay sau restore với bản backup có thể gây hiểu nhầm?

### Bài 8 — Multi-volume snapshot

Database chứa data files trên V1 và WAL trên V2. V1 snapshot lúc 10:00, V2 lúc 10:05.

1. Vì sao không chắc tương đương một crash instant?
2. Điều kiện nào cho phép engine recover an toàn?
3. Có thể tự ghép hai volume backups theo timestamp không?
4. Nên kiểm thử điều gì trong restore drill?

### Bài 9 — Transaction xuyên shards

Transaction T1 cập nhật Order và Payment ở hai shards. Backup shard A trước khi T1 commit, shard B sau T1 commit.

1. Những bất biến nào có thể bị vi phạm?
2. Một distributed snapshot/transaction recovery protocol phải bảo vệ điều gì?
3. Nếu không có global cut, dùng event ledger/reconciliation ra sao?
4. Tại sao gần cùng wall-clock timestamp chưa đủ?

### Bài 10 — Schema migration trong lúc backup

Schema Order đổi `priceDecimal` thành `priceMinorUnits` trong lúc dump.

1. Backup cần schema version nào?
2. Nếu export có cả v1/v2 documents, restore/migration pipeline phải làm gì?
3. Nếu app chỉ còn reader v2, cần chuẩn bị gì?
4. Có nên silently drop unsupported fields không?

### Bài 11 — External invoice blob

Order O900 trong DB trỏ `invoiceObjectVersion=V12`. Backup DB có O900 nhưng object storage chỉ giữ V11.

1. Hệ đã phục hồi đầy đủ chưa?
2. Vì sao giữ object key thôi chưa đủ?
3. Làm sao đồng bộ retention giữa DB snapshots và object versions?
4. Validation cần đối chiếu gì?

### Bài 12 — Outbox và consumer checkpoint

Database restore về source position L1000, consumer checkpoint của message broker ở L1400.

1. Những nguy cơ mất event hay duplicate nào?
2. Khi nào phải reset/reconcile consumer progress?
3. Vì sao event identity/idempotency quan trọng?
4. Có nên cho restored worker kết nối payment provider ngay không?

### Bài 13 — KMS

Backup 10 TiB được mã hóa với K1, lưu ở Region B. Sau một năm, K1 bị hủy vì key rotation.

1. Bytes backup còn thì có restore được không?
2. Nên lưu key reference/region và quyền gì?
3. Làm sao kiểm tra cross-region decrypt trong restore drill?
4. Vì sao không nên đưa plaintext K1 vào manifest?

### Bài 14 — Backup từ follower

Primary position L2000, follower applied L1800. Backup follower kết thúc lúc 12:00.

1. Có thể quảng bá recovery point 12:00/latest không?
2. Điều kiện nào cho phép bù từ L1800 tới L2000?
3. Nếu follower là read-only backup source, nó có thể lag vì nguyên nhân gì?
4. Các metrics nào nên báo?

### Bài 15 — MongoDB

Một team dùng `mongodump` với ordinary scan ở sharded cluster đang ghi, sau đó muốn restore về “chính xác 10:00” trên mọi shards.

1. Vì sao yêu cầu này chưa được chứng minh?
2. Khi nào oplog-assisted dump có thể hữu ích?
3. Tại sao không áp một cách tùy ý lên sharded cluster?
4. Cần xem config server/transaction/resharding metadata nào?

### Bài 16 — Cassandra/ScyllaDB

Team chạy snapshot ở một Cassandra node rồi copy SSTables để restore toàn cluster.

1. Snapshot node có chứa toàn bộ token ranges không?
2. Có cần schema/keyspace definitions không?
3. Commit-log/incremental và repair/tombstone semantics ảnh hưởng gì?
4. Điều gì xảy ra khi topology đã rebalance?

### Bài 17 — Redis

Redis giữ state quan trọng; dùng RDB snapshot mỗi giờ, không archive AOF/changelog.

1. RPO có thể là bao nhiêu trong failure window?
2. RDB background snapshot dưới write churn ảnh hưởng RAM thế nào?
3. Nếu Redis Cluster có ba primaries thì một RDB đủ không?
4. Khi nào chọn tái dựng Redis cache từ NoSQL source thay vì restore cache?

### Bài 18 — DynamoDB PITR

Orders nằm trong DynamoDB table; Payments ở table khác; invoices ở object storage.

1. PITR của Orders table có tự tạo global business cut không?
2. Restore table mới cần application cutover thay đổi gì?
3. Streams có thay PITR dài hạn không?
4. TTL/permissions/GSI/global tables cần kiểm chứng những gì?

### Bài 19 — Cosmos DB

Một account Cosmos DB dùng continuous backup mode; ứng dụng có multi-region read/write và external Kafka consumers.

1. Restore mode/window/region scope cần kiểm tra gì?
2. Session tokens và consistency settings có ảnh hưởng read paths sau restore không?
3. Kafka offsets có tự rewind cùng database không?
4. Những invariants nào cần reconcile?

### Bài 20 — Search snapshot

Team chụp OpenSearch index đang index liên tục và coi snapshot là state đúng tại đúng 10:00 trên mọi shards.

1. Vì sao assumption này có thể sai?
2. Search index có thể tái dựng từ authoritative Order source không?
3. Nếu không tái dựng được, cần backup scope nào?
4. Feature/index mappings/aliases/version compatibility kiểm tra ra sao?

### Bài 21 — RPO

~~~text
Latest full snapshot:  01:00
Latest complete log:   10:55
Incident:              11:02
Business RPO target:   <= 5 minutes
~~~

1. Dựa trên data giả định, gap giữa incident và latest recoverable cut?
2. RPO mục tiêu đạt chưa nếu không có nguồn logs khác?
3. Vì sao backup full 01:00 không nhất thiết quyết định RPO?
4. Cần metric cảnh báo nào để phát hiện từ trước?

### Bài 22 — RTO

~~~text
Provision restore resources:  20 min
Download/decrypt baseline:    45 min
Replay log:                  100 min
Rebuild indexes:             60 min
Validate/cutover:            25 min
~~~

1. Tổng thời gian nếu các steps tuần tự?
2. RTO 3 giờ có đạt không?
3. Những steps có thể tối ưu/parallellize trong giới hạn tool?
4. Vì sao dựa vào backup upload time là sai?

### Bài 23 — Java log coverage

Cho:

~~~text
Snapshot cut: L500
Target:       L900
Segments:
  S1 [501, 600]
  S2 [601, 750]
  S3 [752, 950]
~~~

1. Java coverage checker nên báo gì?
2. Missing position là gì?
3. Nếu thay S3 thành [751,950], còn gap không?
4. Vì sao một range metadata liên tục chưa đủ chứng minh file bytes đúng?

### Bài 24 — Restore đã có checksum khớp

Restore hoàn thành, SHA-256 mọi files đều khớp. Tuy nhiên Java API không mở được collection vì thiếu schema validator và KMS permission.

1. Có được đánh dấu restore thành công không?
2. Checksum đã chứng minh điều gì?
3. Những metadata/dependencies nào đã bị thiếu?
4. Các smoke tests nào nên chạy?

### Bài 25 — Recovery epoch và cache

Database restore về Order v18, nhưng Redis cache/search vẫn chứa Order v22 từ trước disaster.

1. Đây là vấn đề replication lag hay **recovery epoch mismatch**?
2. Bằng cách nào tránh API trả “future data” so với restored authority?
3. Có thể xây shadow index/rebuild thế nào?
4. Cần đối soát user sessions có minVersion=22 ra sao?

### Bài 26 — Retention dependency

Full F1 được tạo ngày 1, các incrementals ngày 2–15 dựa trên F1. Retention script xóa mọi file trên 10 ngày tuổi.

1. Tại ngày 15, các incrementals còn lại có phục hồi được không?
2. Cần tính dependency graph như thế nào?
3. Khi nào mới được xóa F1 an toàn?
4. Vì sao thử restore từ newest complete manifest là cần thiết?

### Bài 27 — Backup ảnh hưởng production

Trong khi backup đang chạy:

~~~text
CPU +10%
Storage read IOPS +500%
WAL free space: 70 GiB -> 5 GiB
Write p99: 100ms -> 900ms
~~~

1. Phân biệt vấn đề storage pressure với CPU.
2. Rủi ro khi WAL free tiếp tục giảm?
3. Có nên tăng backup scan concurrency không?
4. Thiết kế throttle/abort/retry/checkpoint policy.

### Bài 28 — Partial restore một tenant

Tenant A muốn restore dữ liệu về ngày hôm qua nhưng Tenant B vẫn cần dữ liệu hôm nay.

1. Vì sao cluster PITR in-place có thể làm hỏng Tenant B?
2. Kế hoạch isolated restore→extract→guarded repair là gì?
3. Các shared references/global uniqueness cần kiểm tra?
4. Làm sao bảo toàn những writes mới hợp lệ của Tenant A?

### Bài 29 — Bài tập tổng hợp: thiết kế backup chiến dịch bán hàng

~~~text
Database: 200 million Orders over 12 shards
Write rate: 8,000 mutations/s
Backup duration: 6 hours
WAL production peak: 120 MiB/s
Source oplog/log retention: 3 hours at typical rate
RPO target: 5 minutes
RTO target: 3 hours
External invoice objects: 100 TB
Cross-shard transactions and outbox enabled
~~~

Đề xuất:

1. Backup method hỗ trợ online consistent cut.
2. Log archive policy vượt qua snapshot duration.
3. Dung lượng spool/retention với peak và safety margin.
4. Cross-shard transaction/metadata coverage.
5. Object version retention và manifest.
6. Encryption key availability/cross-region DR.
7. Incremental/full schedule đạt RTO.
8. End-to-end restore drill, sampling/verification.
9. Degraded-mode p99 guard.
10. Phương án khi log chain gap.

### Bài 30 — Phản biện đề xuất backup

Một đề xuất viết:

> “Mỗi ngày lúc 01:00 dùng script `cp` data directory trong lúc app đang chạy. Backup vào cùng server. Đọc đủ số file là xong. Sau đó xóa WAL để tiết kiệm disk. Chỉ lưu Orders collection, vì Payments nằm ngoài phạm vi. Không cần indexes/schema/keys vì có trong app. Redis cache cứ giữ nguyên khi restore. Khi cần khôi phục thì copy files ngược lại và chạy Java service mới.”

Hãy tìm **ít nhất mười rủi ro hoặc assumptions chưa được chứng minh** và sửa thành một kế hoạch có backup boundary, log coverage, external dependencies, security, RPO/RTO và restore drill.

## 52. Gợi ý lời giải cho một số bài tập

### 52.1. Bài 2 — Scan rồi subscribe tạo gap

Backup có thể chứa O100 v1; vì CDC subscribe từ `LATEST` sau thời điểm v2 commit, event v2 có thể **không được phát lại**. Cần database-native snapshot + log position hoặc capture-before-scan/merge protocol đầy đủ, có tombstone/version ordering và continuous source log coverage.

### 52.2. Bài 3 — Boundary L1000

Restore tới L1500 cần snapshot L1000 và change history **sau L1000 tới L1500**. Nếu restore API nhận L1000 inclusively, phải xử lý overlap theo engine; không blindly reapply delta đã nằm trong snapshot. Nếu log chỉ có tới L1800 và không có nguồn khác, **latest supported recovery target là L1800** theo scope/chain đã xác minh, bất kể source hiện ở L2000.

### 52.3. Bài 4 — Log storage

Trong sáu giờ:

\[
20\ \mathrm{MiB/s}\times6\times3600
=432\,000\ \mathrm{MiB}
\]

\[
432\,000/1024=421{,}875\ \mathrm{GiB}
\]

100 GiB spool không đủ nếu **không có consumer/archive draining** trong sáu giờ theo tốc độ cố định. Nếu peak gấp bốn, raw six-hour log volume có thể tăng tới **1.687,5 GiB** trong giả định peak kéo dài suốt sáu giờ, chưa tính overhead. Cần đo peak duration/source backlog, không chỉ lấy average.

### 52.4. Bài 5 — Incremental I2 missing

Không thể khẳng định restore đúng L1700 từ F1 + I1 + I3 nếu I2 mất. Có thể tìm alternate I2, một later full snapshot có valid cut, hoặc chọn một recovery target trước gap nếu business chấp nhận. Retention phải bảo vệ **mọi dependency của active complete manifests**.

### 52.5. Bài 6 — Tombstone race

Blind upsert O101 v10 sau DELETE v11 **hồi sinh** dữ liệu đã xóa. Target merge phải dùng atomic version/generation/tombstone guard nếu là custom snapshot+CDC. Native physical backup phải được engine recovery protocol xử lý; không tự trộn file snapshot với JSON CDC một cách tùy tiện.

### 52.6. Bài 7 — TTL sau restore

Session có expiry 12:00, restore lúc 15:00 thì business policy thường coi nó **expired** (trừ khi có yêu cầu khác được công bố). Physical cleanup có thể chưa chạy, nhưng API nên kiểm tra expiration để không cho phiên đăng nhập cũ active. Preserve TTL/expiration semantics trong recovery plan.

### 52.7. Bài 8 — Multi-volume

Data V1 và WAL V2 chụp cách nhau năm phút không tự tạo một crash-consistent state. Cần snapshot group/engine backup procedure hoặc recovery log coordination theo product. Restore drill phải kiểm tra startup, log replay và committed transaction validity.

### 52.8. Bài 11 — Object version

DB khôi phục O900 nhưng thiếu invoice object version V12 thì business state **chưa đầy đủ**. Object key chỉ chỉ ra logical path; version ID và retention cần bảo vệ đúng bytes. Validate exact object version/hash/permissions, không chỉ HTTP 200 trên “latest”.

### 52.9. Bài 12 — Outbox checkpoint

Database ở L1000, consumer vẫn checkpoint L1400 có thể bỏ events/changes chưa nằm trong restored state; nếu replay early có thể gây duplicate external effects. Cần recovery epoch, event IDs, idempotency/dedup và reconcile business ledger. Không cho restored worker tự phát payment events tới provider thật trước khi kiểm soát side effects.

### 52.10. Bài 13 — Key retention

Không có decrypt key K1 hoặc quyền sử dụng tương đương, backup có thể hoàn toàn không đọc được dù checksum khớp. Cần key lifecycle, KMS reference/version, region/policy, test decrypt và separation of duties; không lưu secret plaintext cạnh backup manifest.

### 52.11. Bài 14 — Follower lag

Follower backup ở L1800 không thể quảng bá latest L2000 chỉ vì job kết thúc lúc 12:00. Chỉ khi có complete replayable log L1801…L2000 theo đúng source history mới có thể khôi phục tới L2000, và còn phải kiểm tra term/transaction/log retention.

### 52.12. Bài 17 — Redis snapshot cadence

RDB mỗi giờ không có log continuation có thể khiến mất **tới gần một giờ writes** trong outage xảy ra ngay trước lần snapshot kế tiếp, theo giả định snapshot cuối hợp lệ và write ACK/durability mode. Actual RPO phụ thuộc completion times, replication/persistence settings và nguồn khôi phục khác. Trong lúc background save, COW memory có thể tăng theo write churn; Redis Cluster cần coverage mỗi primary/hash-slot group.

### 52.13. Bài 21 — RPO

Incident 11:02, latest recoverable log 10:55:

\[
11{:}02-10{:}55=7\text{ phút}
\]

Theo dữ liệu đã cho, **không đạt RPO ≤5 phút**. Full backup lúc 01:00 vẫn hữu ích làm baseline; continuous log coverage mới quyết định latest recovery point. Cảnh báo khi **oldest unarchived age/last contiguous archived source position** vượt safety threshold.

### 52.14. Bài 22 — RTO

Giả sử năm bước tuần tự:

\[
20+45+100+60+25=250\text{ phút}
\]

250 phút = **4 giờ 10 phút**, vượt RTO 3 giờ. Có thể giảm chain length, dùng newer full baseline, parallel shard restore/index rebuild nếu supported và pre-provision recovery infrastructure. Không suy total restore time từ tốc độ backup upload.

### 52.15. Bài 23 — Coverage gap

S1 [501,600], S2 [601,750], S3 [752,950] thiếu **position 751**. Coverage checker phải fail. Đổi S3 thành [751,950] loại gap trong integer model; vẫn phải đọc/verify actual log bytes/checksum/source epoch và transaction compatibility.

### 52.16. Bài 25 — Cache từ tương lai

DB restored v18, cache chứa v22: đây là **recovery epoch mismatch**, không đơn giản replica lag. Cache nên bị invalidate/namespace rotate, search rebuilt/rewound, client session tokens cao hơn recovery state phải được xử lý theo application policy; không trả “v22 latest” khi authoritative restored source ở v18.

### 52.17. Bài 27 — Backup quá tải

Storage IOPS tăng mạnh, WAL free giảm và write p99 tăng cho thấy backup/recovery work có thể **cạnh tranh I/O và đe dọa source availability**. Không tăng scan concurrency. Có thể throttle/pause backup, bảo vệ log archive, tăng nguồn lực có kiểm soát và abort/rebaseline nếu coverage không còn giữ được.

### 52.18. Bài 28 — Tenant restore

Không PITR trực tiếp toàn cluster nếu Tenant B không được rollback. Restore backup vào isolated cluster, trích Tenant A với đúng consistency cut, so versions/operations với live, áp guarded repair kèm audit và domain reconciliation. Tránh blind overwrite những writes mới hợp lệ.

### 52.19. Bài 29 — Log sizing peak

Nếu peak 120 MiB/s kéo dài **đủ sáu giờ**:

\[
120\times6\times3600
=2\,592\,000\ \mathrm{MiB}
\]

\[
2\,592\,000/1024
=2\,531{,}25\ \mathrm{GiB}
\approx2{,}47\ \mathrm{TiB}
\]

Đây là một extreme scenario, chưa gồm overhead/safety margin. Với retention ba giờ ở typical rate, snapshot sáu giờ không thể chỉ trông chờ source giữ log từ đầu; phải có **durable continuous archiving từ trước/đúng boundary**, hoặc dùng một protocol khác. RTO 3 giờ cũng cần restore drill thực tế với 200 triệu Orders, 100 TB objects và indexing.

### 52.20. Bài 30 — Những lỗ hổng chính

Proposal `cp` live DB directory có ít nhất các vấn đề:

1. Không có database-native snapshot/online backup contract.
2. File set có thể bị thay đổi trong lúc copy.
3. Data và WAL không ở một consistent recovery boundary.
4. Xóa WAL phá PITR và có thể cả recovery.
5. Backup cùng server là single failure domain.
6. Không có offsite/immutable/permission isolation.
7. Không backup Payments/Outbox/business invariants.
8. Không backup external objects/versions.
9. Không chứng minh indexes/schema/metadata coverage.
10. Không giữ encryption key references/permissions.
11. Không có source log/epoch/transaction boundary.
12. Không quản lý backup manifest/checksum/incremental dependencies.
13. Không có restore drill/RPO/RTO.
14. Không xử lý Redis cache chứa future state.
15. Không kiểm soát restored app side effects.
16. Không xác định authority/fencing khi cutover.
17. Không có privacy deletes/TTL/tombstone reconciliation.
18. Không có load/throttle/space monitoring trong backup.

Hướng sửa là **engine-supported online snapshot + contiguous log coverage**, manifest đầy đủ, protected repository, backup scope theo domain, restore isolated + validation + coordinated cutover, và capacity/RPO/RTO test.

## 53. Checklist vận hành trước khi bật online backup

### 53.1. Nguồn và backup boundary

1. Database engine/version/topology có được ghi rõ không?
2. Backup mechanism được vendor hỗ trợ khi **writes vẫn chạy** không?
3. Có biết logical/physical/crash-consistent/application-consistent scope không?
4. Snapshot cut có source position/epoch/term hợp lệ không?
5. Có transaction boundaries/commit/abort semantics cần bảo vệ không?
6. Có tránh ordinary Scan bị nhầm thành consistent snapshot không?
7. Có xác định write ACK/durability level dùng cho RPO không?
8. Có plan cho leader failover, resharding và schema changes khi backup không?

### 53.2. Logs và retention

9. Có bắt đầu/giữ log archive đúng thời điểm so với snapshot cut không?
10. Có kiểm tra log coverage **không gap** từ snapshot tới recovery target không?
11. Có phân biệt log read/received với durably stored in repository không?
12. Có bảo vệ multi-shard positions/transaction metadata đúng scope không?
13. Có alert khi log retention sắp không đủ cho snapshot/recovery không?
14. Có tính log production peak và archive spool capacity không?
15. Có hiểu inclusive/exclusive replay position không?
16. Có phân biệt engine WAL/commit log với CDC/domain events không?
17. Có recovery plan khi segment bị mất/expired không?

### 53.3. Dữ liệu chính và supplemental state

18. Có inventory toàn bộ authoritative collections/tables/keyspaces không?
19. Có bao phủ Orders/Payments/Outbox/Idempotency/Audit theo domain không?
20. Có schema, index definitions, unique constraints, TTL policies không?
21. Có data/metadata về deletes/tombstones và generation/version không?
22. Có external blob/object versions cùng retention không?
23. Có CDC offsets, consumer checkpoints, event IDs và reconciliation plan không?
24. Có nêu derived caches/search indexes nào sẽ rebuild không?
25. Có xử lý transient staging/queues đã ACK nghiệp vụ không?
26. Có client/application migration compatibility và serializer versions không?
27. Có tenant-specific restore requirements không?

### 53.4. Metadata, cấu hình và security

28. Backup manifest có cluster identity/region/source epoch không?
29. Có engine/version/format/feature compatibility không?
30. Có database roles/users/IAM/network/TLS dependencies không?
31. Có KMS key reference, retention và cross-region decrypt permission không?
32. Có encryption at rest/in transit và least privilege không?
33. Có immutable/versioned backup object storage theo threat model không?
34. Có separation of duties cho backup vs delete/restore không?
35. Có audit logs/signed manifest/provenance khi cần không?
36. Có quản lý retention/deletion/privacy policy cho backups không?

### 53.5. Backup execution và integrity

37. Có staging→verify→publish manifest protocol không?
38. Có verify artifact checksums, lengths và object versions không?
39. Có backup chain dependency graph trước GC không?
40. Có checkpoint/retry sao cho crash không publish false success không?
41. Có bounded concurrency, memory và I/O throttle không?
42. Có metrics live API p99/errors khi backup chạy không?
43. Có metrics cache misses, WAL space, compaction, network egress không?
44. Có stop/abort policy khi ảnh hưởng production hoặc retention gap không?
45. Có cách đo **latest verified recoverable position** không?

### 53.6. Restore rehearsal và cutover

46. Có restore drill vào môi trường **cách ly** không?
47. Có test old/new application/schema compatibility không?
48. Có replay PITR tới target cụ thể và test deletes/TTL không?
49. Có so source/restore tại consistent boundary không?
50. Có kiểm tra business invariants, external objects và idempotency không?
51. Có cleanup/reset/rebuild caches/search/read models không?
52. Có event/outbox/broker checkpoint reconciliation không?
53. Có chặn payment/email/webhook side effects trong restore tests không?
54. Có old-source fencing và authority handoff khi cutover không?
55. Có measured RPO/RTO **end-to-end** chứ không chỉ download duration không?
56. Có rollback plan nếu restored cluster fail trong cutover không?

### 53.7. Giám sát và continuous improvement

57. Có báo latest complete backup, latest PITR position và restore drill status không?
58. Có alert missing segment/checksum/key decrypt/backup retention dependency không?
59. Có thử fault injection write-during-backup, crash, delete, schema change, region outage không?
60. Có owner/runbook quyết định recovery target, data loss communication và approval không?

## 54. Ma trận quyết định: chọn chiến lược sao lưu

| Điều kiện | Chiến lược ưu tiên xem xét | Điều phải chứng minh |
| --- | --- | --- |
| Engine có native hot backup + PITR | Dùng native snapshot/log archive | Recovery cut, log coverage, retention |
| Snapshot có thể tạo nhanh khi quiesce | Brief write pause + supported cut | In-flight writes drained, all writers paused |
| Data nhỏ, read-only hoặc ít ghi | Logical consistent export | Snapshot read scope + metadata |
| Database sharded + cross-shard transactions | Cluster-aware backup | Global cut/transaction recovery |
| Chỉ cần rebuild derived search/cache | Backup authoritative source, rebuild target | RTO/replay and schema compatibility |
| Multi-system ledger + external blobs | Coordinated recovery + object versioning | Referential/business consistency |
| Log retention ngắn hơn snapshot | Parallel durable archive/pinning | No gap before source truncate |
| RPO vài phút, RTO vài giờ | Full/incremental/PITR with rehearsal | Measured latest recovery position and total restore time |
| Ransomware threat model | Immutable isolated backups | Key/credential separation and restore authority |
| Một tenant cần rollback | Isolated cluster restore + guarded repair | Không rollback tenants khác |

## 55. Những điều không được suy từ một chỉ số đẹp

| Dashboard hiển thị | Điều chưa được chứng minh |
| --- | --- |
| `backupStatus=SUCCESS` | Backup đã restore được |
| Checksum files khớp | Data nhất quán, không thiếu log |
| 100% documents scanned | Mọi concurrent writes/deletes đều được giữ |
| Backup completed at 10:30 | Recovery cut là 10:30 |
| Replication lag=0 | Backup repository đã lưu mọi writes |
| Consumer lag=0 | Target không thiếu source events |
| Có RF=3 | Chịu logical deletion/ransomware |
| Có PITR bật | Mọi tables/external blobs cùng một global cut |
| Redis RDB hoàn thành | Không mất writes mới sau snapshot |
| Restore DB process healthy | Java API/business workflow đã phục hồi |
| Index restored | Search query thấy mọi data mới tại cùng cut |
| KMS key ID tồn tại | Restore role có quyền giải mã |
| All shards have snapshots | Cross-shard transactions nhất quán |
| Logs archived through L2000 | Không có gap từ snapshot L1000 |

## Kết luận

**Sao lưu trong lúc ghi** là bài toán xác định và bảo vệ một **trạng thái khôi phục hợp lệ**, không đơn thuần sao chép bytes khi hệ vẫn chạy. Một snapshot có thể được tạo trong vài phút hoặc sao chép hàng giờ, nhưng việc kết luận backup đúng phụ thuộc vào **consistent cut, WAL/oplog/commit log coverage, transaction semantics và bản manifest có thể kiểm chứng**.

Những điểm cần ghi nhớ:

- **Ordinary paginated scan hoặc copy live files không tự là consistent online backup.** Dùng native mechanisms của database hoặc protocol có no-gap proof.
- **Snapshot boundary khác thời điểm job hoàn thành.** Latest recoverable position đến từ base + complete archived history, không phải tên thư mục backup.
- **WAL/oplog/log tail quan trọng khi writes tiếp diễn.** Giữ đủ segments, phát hiện gaps và không silently skip expired positions.
- **Replication không thay backup.** Corruption, logical deletion và security incidents có thể lan sang mọi replicas.
- **Phạm vi khôi phục vượt data documents.** Schema/index definitions, transaction metadata, TTL/tombstones, outbox/idempotency, object versions, config/keys và app compatibility có thể quyết định restore thành bại.
- **Backup nhiều shards hoặc nhiều hệ thống đòi consistency scope rõ.** Snapshot từng node/từng table không tự là một global transaction cut.
- **Incremental backups cần dependency chain hoàn chỉnh.** Có đủ files mới nhưng thiếu baseline hoặc một log segment vẫn không recover được.
- **KMS và security là dependency của restore.** Backups được mã hóa nhưng mất key hoặc thiếu permission có thể trở thành vô dụng.
- **Restore phải cách ly và đối soát external effects.** Không tự chạy lại payment/email/outbox ở môi trường restored mà thiếu idempotency/reconciliation.
- **RPO/RTO phải được đo bằng restore rehearsal.** Không lấy `backup SUCCESS` hoặc download time làm bằng chứng dịch vụ đã hồi phục.
- **NoSQL products có cơ chế rất khác nhau.** MongoDB oplog, Cassandra SSTables, Redis RDB/AOF, managed PITR và search snapshots không có một protocol chung có thể copy/paste.

Câu hỏi kết thúc quan trọng nhất là:

> **“Bản backup này đại diện chính xác cho trạng thái đã commit nào? Mọi thay đổi phải có sau mốc ấy nằm ở đâu, những metadata và dữ liệu ngoài database nào cần bổ sung, và đã có lần nào khôi phục thật tới mốc mục tiêu với nghiệp vụ đúng chưa?”**

Nếu có thể trả lời từng ý bằng **source positions, manifests, checksums, restore logs và kết quả đối soát**, bạn đã chuyển từ việc “có file sao lưu” sang **năng lực phục hồi NoSQL có thể kiểm chứng**.

# Thay đổi shard key, cách chia bucket hoặc cấu trúc tài liệu

Một dịch vụ Java quản lý đơn hàng cho nhiều tenant. Khi mới triển khai, database đặt mọi Order của một tenant trong cùng một phân vùng theo `tenantId`, còn lịch sử trạng thái được nhúng trong mảng `events` của Order. Hai năm sau, một tenant lớn chiếm phần lớn traffic, phân vùng của tenant đó bị throttling, document có mảng lịch sử quá dài và thao tác liệt kê Order cần quét hàng triệu bản ghi. Nhóm đề xuất chuyển sang `tenantId + hashBucket(orderId)` và tách `events` thành collection riêng.

Về ý tưởng, thay đổi này có thể giảm tải trên phân vùng nóng và chi phí đọc document. Nhưng không thể chỉ đổi hàm hash trong Java rồi triển khai: hàng triệu bản ghi vẫn nằm tại vị trí cũ, clients cũ còn đang ghi, change events có thể đến trong lúc sao chép, nhiều indexes và transactions đang phụ thuộc mô hình ban đầu. Một lỗi nhỏ có thể khiến Order “biến mất” khỏi query, bị tạo hai bản, mất cập nhật đã xác nhận hoặc hiện lại sau khi xóa.

Bài học thuộc chương **Di chuyển và thay đổi** của module **Database No SQL**. Nội dung hướng dẫn thay đổi ba lớp thường liên quan:

1. **Shard/partition key:** thay khóa định tuyến hoặc phương thức phân phối logical entities.
2. **Bucketing:** thêm bucket, đổi số bucket, đổi hash/time bucket hoặc chuyển ownership giữa các virtual buckets và physical shards.
3. **Document structure:** tách, gộp, đổi field/nested array, đổi embedded sang referenced documents và quản lý nhiều schema versions.

Mục tiêu là hiểu cách lên kế hoạch, backfill dữ liệu lịch sử, áp dụng ghi mới, chốt nguồn có thẩm quyền, kiểm chứng kết quả và xóa dữ liệu cũ mà vẫn bảo toàn nghiệp vụ.

> **Nguyên tắc:** Migration là một quá trình chuyển quyền sở hữu dữ liệu giữa hai mô hình. Khi hệ thống vẫn nhận writes, phải luôn biết **nơi nào có quyền ghi chính thức**, **version nào là mới nhất** và **đọc từ đâu sau mỗi giai đoạn**. Copy dữ liệu thành công không tự chứng minh quá trình chuyển đã đúng.

## 1. Khái niệm nền tảng

| Thuật ngữ | Vai trò | Rủi ro khi đổi |
|---|---|---|
| Shard | Nhóm lưu một phần dữ liệu vật lý hoặc logic theo engine | Cân bằng tải, routing, capacity |
| Shard key | Trường hoặc tổ hợp trường engine dùng phân phối tài liệu | Move/reshard, query targeting |
| Partition key | Khóa xác định phạm vi đặt dữ liệu/nhất quán theo sản phẩm | Hot partition, transaction scope |
| Application bucket | Nhóm do ứng dụng tính từ ID/hash/time | Key mapping, fan-out, migration |
| Virtual bucket | Bucket logic ổn định, được ánh xạ sang owner vật lý | Ownership, mapping epoch |
| Physical shard | Server/partition/cluster thực đang phục vụ data | Rebalance, availability |
| Document | Đơn vị chứa fields, nested objects/arrays | Read/write amplification |
| Aggregate | Ranh giới nghiệp vụ cần duy trì invariant | Transaction và concurrency |
| Routing directory | Nơi ánh xạ logical key/bucket sang owner | Stale clients, split-brain |
| Backfill | Chuyển dữ liệu cũ sang mô hình đích | Thiếu/trùng/sai version |
| Change capture | Thu thập writes/deletes phát sinh trong migration | Gaps, duplicate, reordering |
| Cutover | Chuyển reads/writes chính thức | Fencing, rollback |

### 1.1. Shard key khác địa chỉ shard

Một `orderId` có thể là khóa định danh ổn định; tên shard A hay B chỉ là nơi lưu hiện tại. Nếu clients gắn shard name vào business ID, relocation rất khó và có thể phá references.

### 1.2. Bucketing của ứng dụng khác cơ chế phân mảnh bên trong database

Ứng dụng có thể tạo `bucket = hash(orderId) mod 32` trước khi ghi key. Database lại có thể tự hash primary key và quản lý partition movement. Cần hiểu cả hai, không mặc định thêm tầng bucket sẽ giải quyết mọi vấn đề.

### 1.3. Schema-flexible không đồng nghĩa migration tự động

Hệ document cho phép v1/v2 cùng tồn tại, nhưng Java readers, indexes, validators, CDC consumers và security policies vẫn phải hiểu semantics của từng version.

## 2. Ba dạng thay đổi và chi phí của chúng

### 2.1. Đổi shard/partition key

Trước:

~~~text
PK = tenantId
SK = orderId
~~~

Sau:

~~~text
PK = tenantId + "#" + bucket(orderId)
SK = orderId
~~~

Order phải được tìm ở một vị trí khác; mọi phương thức đọc/ghi dùng key, indexes và query plans cần điều chỉnh. Nếu engine không hỗ trợ đổi key trực tiếp, phải tạo records hoặc container/table mới.

### 2.2. Đổi số bucket hoặc thuật toán bucket

Nếu tăng từ 8 lên 32 buckets bằng cách thay `mod 8` thành `mod 32`, nhiều Order sẽ được định tuyến tới bucket chưa có dữ liệu. Cần migration hoặc một lớp routing versioned.

### 2.3. Đổi cấu trúc document

Trước:

~~~json
{
  "tenantId": "T1",
  "orderId": "O7",
  "status": "PAID",
  "version": 15,
  "events": [
    {"sequence": 1, "type": "CREATED"},
    {"sequence": 2, "type": "PAID"}
  ]
}
~~~

Sau:

~~~text
orders_v2:
  tenantId, orderId, status, version, summary

order_events_v2:
  tenantId, orderId, sequence, eventId, type, payload
~~~

Read summary nhanh hơn và events có thể được phân trang, nhưng ghi Order và thêm event có thể không còn cùng một atomic document.

### 2.4. Đổi cả ba cùng lúc

Việc này tăng khả năng lỗi và làm khó rollback. Khi có thể, chia thành nhiều thay đổi tương thích ngược để xác định tác động của từng bước; nếu phải gộp, dùng một kế hoạch có checkpoint, version và cutover rõ ràng.

## 3. Trước khi di chuyển, xác định vấn đề thật

Một shard nóng có thể do quá nhiều entities, nhưng cũng có thể do một entity được cập nhật liên tục. Hai tình huống cần giải pháp khác nhau:

~~~text
Case A:
    100,000 orders, mỗi order ghi ít
    Tất cả cùng partition tenant A
    -> Có thể tách theo orderId/bucket

Case B:
    Một inventory item nhận 30,000 CAS writes/s
    -> Hash item ID vẫn vào cùng một bucket
    -> Phải xem lại invariant/serialization boundary
~~~

### 3.1. Đo per-partition thay vì trung bình cluster

CPU toàn cluster thấp nhưng một partition bị throttle vẫn là saturation thực. Quan sát per-shard QPS, write capacity, hot keys, size, p99, retries và conflicts.

### 3.2. Đo chi phí truy vấn

Nếu `listOrdersByTenant` phải quét quá nhiều records do thiếu index, sửa access path có thể rẻ hơn full re-sharding.

### 3.3. Đo kích thước và tăng trưởng document

Histogram p50/p95/p99 bytes, số elements trong arrays, write amplification, request/response bytes và GC giúp quyết định có cần tách document không.

### 3.4. Không chạy migration chỉ vì thuật toán mới “đẹp hơn”

Yêu cầu phải có mục tiêu: giảm p99, giảm throttling, giảm số partitions touched, giữ RPO/RTO và bảo toàn invariants.

## 4. Thiết kế mô hình đích từ access patterns

| Đường truy cập | Key `tenantId` | Key `(tenantId,bucket(orderId))` |
|---|---|---|
| Get Order theo tenant+ID | Có thể target tenant | Tính bucket để target |
| List mọi Orders của tenant | Thường có locality | Cần fan-out hoặc read model |
| Get Order events | Embedded gây document lớn | Query event collection theo Order |
| Update một Order | Có thể tranh với nhiều Order khác cùng key | Phân tải theo Order |
| Update một inventory item hot | Vẫn hot tại item | Vẫn hot nếu cùng item |
| Tenant-wide uniqueness/quota | Có thể cùng partition | Cần authority/registry khác |
| Query theo tháng | Cần index | Có thể thêm time bucket/index |

### 4.1. Hãy viết query matrix trước schema

Với mỗi API, ghi partition predicates, range/sort, số records, consistency requirement và transaction scope. Một key tốt cho GET chưa chắc tốt cho liệt kê theo thời gian.

### 4.2. Hash phân phối đều nhưng giảm locality

Hash orderId có thể giảm hot partition, song việc đọc 50 Orders mới nhất của tenant có thể phải fan-out 32 buckets rồi merge. Cân nhắc materialized view hoặc secondary index.

### 4.3. Time bucket hợp với retention

`tenantId + yyyyMM` giúp dọn và truy vấn theo tháng, nhưng bucket tháng hiện tại có thể rất nóng. Có thể kết hợp thêm hash suffix có kiểm soát.

### 4.4. Chọn key theo atomicity

Nếu cần giao dịch cùng partition cho Order và Outbox, phải xem partitioning mới có còn cùng transactional boundary của engine không. Performance không được đánh đổi correctness.

## 5. Vì sao tăng bucket count không phải chỉnh config nhỏ?

Một hash cố định cho Order O9 cho ra giá trị 29:

~~~text
Old: 29 mod 8  = 5
New: 29 mod 32 = 29
~~~

Record hiện đang nằm ở bucket 5. Nếu toàn bộ application lập tức dùng 32, request tìm ở bucket 29 và có thể trả not found dù dữ liệu vẫn còn.

### 5.1. Hash version là một phần hợp đồng persisted data

Version, encoding, normalization và số bucket phải ổn định qua deployments. Tất cả Java services và migration workers phải tính cùng ID.

### 5.2. Consistent hashing giảm lượng di chuyển nhưng không loại migration

Nó có thể giảm số keys đổi owner khi thêm node, nhưng bytes phải được chuyển và writes trong khi chuyển vẫn phải được phối hợp.

### 5.3. Rendezvous hashing cũng cần version

Thay danh sách hoặc trọng số nodes làm đổi owner của một phần keys. Không để hai phiên bản của service tự chọn owner khác nhau rồi cùng ghi.

### 5.4. Tách logical bucket khỏi physical node

Giải pháp thường tốt hơn là có nhiều virtual buckets cố định rồi ánh xạ buckets tới physical shards; khi thêm server, chỉ chuyển ownership một số buckets.

## 6. Virtual bucket và directory định tuyến

~~~mermaid
flowchart LR
  K["tenantId + orderId"] --> H["Stable hash"]
  H --> V["Virtual bucket 0..255"]
  V --> DIR["Versioned bucket directory"]
  DIR --> A["Shard A"]
  DIR --> B["Shard B"]
  DIR --> C["Shard C"]
~~~

Giả sử có 256 virtual buckets. Ban đầu, A giữ 0–85, B giữ 86–170, C giữ 171–255. Khi thêm shard D, control plane có thể chuyển một số bucket IDs sang D mà không đổi virtual bucket ID của Orders.

### 6.1. Thêm physical shard khác tăng virtual bucket count

Nếu bucket 42 quá nóng vì toàn bộ writes vào một Order, chuyển bucket 42 sang node D có thể chỉ dời điểm nghẽn. Chia bucket 42 thành sub-buckets là một migration khóa mới.

### 6.2. Directory là control plane quan trọng

Một entry có thể gồm `keyspace`, `bucketId`, `owner`, `region`, `epoch`, `state`, `schemaVersion`. Các update ownership phải có compare-and-set/transaction/consensus phù hợp.

### 6.3. Reader cache có thể bị cũ

Ứng dụng cache mapping nhưng phải xử lý `STALE_EPOCH` hoặc `MOVED`, refresh route và retry có idempotency. Không tự đổi shard khi request thất bại mà thiếu authority.

### 6.4. Residency trước placement

Nếu tenant chỉ được phép ở region R, router không được đặt bucket của tenant đó vào region khác vì tiện cân bằng tải.

## 7. Đổi cấu trúc tài liệu và aggregate boundary

### 7.1. Embedded data có ưu điểm

Một Order có tối đa 10 line items, luôn đọc cùng nhau và cập nhật atomically có thể phù hợp khi nhúng chúng trong cùng document.

### 7.2. Mảng tăng vô hạn gây chi phí

`orderEvents[]` tăng theo năm khiến document lớn, đọc summary phải tải lịch sử, updates cần sửa/serialize nhiều data và có thể chạm giới hạn engine.

### 7.3. Tách có thể giảm read amplification

Giữ `orders` cho summary và `order_events` theo `(orderId, sequence)` để phân trang. Nhưng readers cũ phải được sửa và indexing/reconciliation phải bao gồm collection mới.

### 7.4. Atomicity có thể thay đổi

Trước đây một update trong Order document chứa status và event. Sau khi tách, hai writes có thể ở hai transactions/partitions. Cần transaction được hỗ trợ hoặc outbox/materialization protocol.

### 7.5. Đừng tự đổi source of truth

Event history có thể là nguồn authority còn Order summary là projection, hoặc ngược lại. Migration plan phải nêu rõ nguồn nào quyết định version và business transition hợp lệ.

## 8. Các phụ thuộc thường bị quên

| Thành phần | Khía cạnh cần sửa |
|---|---|
| CRUD repositories | Key builder, queries, conditional writes |
| API pagination | Cursor chứa bucket/shard/version |
| Indexes | Query targeting, uniqueness scope |
| Jobs/ETL | Scan ranges, old schema readers |
| Kafka/CDC consumers | Ordering, resume tokens, duplicates |
| Caches | Key format, invalidation |
| Outbox/event publisher | Transaction scope, event identity |
| Authentication/authorization | Trusted tenant scope |
| Analytics/reporting | Old and new data layouts |
| Backups/PITR | Schema/placement version khi restore |
| Retention/TTL | ExpiresAt, deletes, tombstones |
| Monitoring | Metrics theo cohort, old/new routes |

### 8.1. Clients không nên biết shard name

Business key `(tenantId, orderId)` nên ổn định; physical route là quyết định của router. External references nhúng địa chỉ shard cũ cần alias hoặc migrate.

### 8.2. Không bỏ qua support scripts

Một job xử lý Order timeout vẫn ghi vào old table sau cutover có thể phá convergence. Liệt kê tất cả writers, kể cả manual/admin tools.

### 8.3. Backup còn giữ schema cũ

Nếu restore snapshot v1 sau khi code chỉ còn v2, application có thể không đọc được. Giữ compatibility/migration tooling trong thời gian retention cần thiết.

## 9. Tách quá trình thành các trạng thái

~~~mermaid
flowchart TD
  P["PREPARED"] --> B["BACKFILLING"]
  B --> C["CATCHING_UP"]
  C --> S["SHADOW_READING"]
  S --> F["CUTOVER_PENDING"]
  F --> N["NEW_PRIMARY"]
  N --> D["DRAINING_OLD"]
  D --> R["OLD_RETIRED"]
  P --> X["ABORTED"]
  B --> X
  C --> X
  S --> X
~~~

### 9.1. PREPARED

Target schema/indexes/keys đã sẵn sàng; backup verified; capacity/metrics/feature flags và rollback plan được phê duyệt.

### 9.2. BACKFILLING

Copy records lịch sử từ consistent snapshot. Source cũ vẫn có quyền ghi chính thức.

### 9.3. CATCHING_UP

Áp dụng inserts/updates/deletes mới từ CDC/outbox với đúng watermark/order/idempotency.

### 9.4. SHADOW_READING

Đọc target để so sánh nhưng không trả dữ liệu target cho business response khi chưa công bố authority.

### 9.5. CUTOVER_PENDING

Fencing/drain old writes, chốt watermark, verify target, commit route epoch mới.

### 9.6. NEW_PRIMARY, DRAINING, RETIRED

Target nhận ghi authoritative; old source không còn quyền ghi, chỉ giữ theo chính sách recovery trước khi được retired.

## 10. Nguồn có thẩm quyền theo từng giai đoạn

| Giai đoạn | Old data | New data | Public reads |
|---|---|---|---|
| Backfill | Authoritative read/write | Nhận copy, không làm authority | Old |
| Catch-up | Authoritative | Replayed changes | Old |
| Shadow | Authoritative | Đọc kiểm chứng | Old |
| Cutover pending | Fenced/draining | Ready at watermark | Pause/bounded retry khi cần |
| New primary | Không nhận writes mới | Authoritative | New |
| Retire | Archived/deleted theo policy | Authoritative | New |

### 10.1. Hai writers độc lập là nguy cơ chính

Nếu old và new đều nhận authoritative writes sau cutover, có thể xảy ra split-brain và ghi lùi version. Đối với Order/Inventory, conflict resolution theo timestamp thường không đủ.

### 10.2. Dual-write không mặc định an toàn

Một lệnh ghi old thành công, target timeout; retry bằng ID mới có thể tạo duplicate. Cần stable `commandId` và outbox/change replay hoặc transactional protocol phù hợp.

### 10.3. Read fallback có thể hồi sinh dữ liệu

Sau cutover, target không thấy record do đã xóa nhưng fallback về old trả record cũ. Chỉ dùng fallback nếu đã xử lý tombstone/version và quyền authoritative rõ.

## 11. Offline và online migration

### 11.1. Offline migration

Dừng writes, tạo consistent export, transform/import, verify, chuyển router rồi nhận writes lại. Dễ lý luận hơn nhưng downtime có thể không chấp nhận.

### 11.2. Online migration

Giữ service hoạt động, copy snapshot cũ và catch up live changes. Khó hơn do writes/deletes có thể tới trong lúc copy; cần watermarks và fencing.

### 11.3. “Zero downtime” phải có định nghĩa

Một migration có thể cần pause writes vài giây để chốt authority. Không được nói zero downtime khi chưa định nghĩa user-facing errors, stale reads và SLO.

### 11.4. Không tất cả hệ đều có cùng tính năng

Một số database có native resharding; hệ khác cần new table/container. Online tools của vendor có version-specific giới hạn về transaction, indices, load và rollback.

## 12. Lấy snapshot nhất quán và watermark

~~~mermaid
flowchart LR
  SRC["Old authoritative source"] --> SNAP["Consistent snapshot S"]
  SRC --> FEED["Changes from position W"]
  SNAP --> BULK["Backfill transform"]
  BULK --> DEST["Target"]
  FEED --> APPLY["Ordered idempotent apply"]
  APPLY --> DEST
~~~

### 12.1. Timestamp ứng dụng không là checkpoint database

`System.currentTimeMillis()` không tự chứng minh snapshot và CDC stream nối liền. Cần snapshot token/position/transaction boundary do source hoặc tool hỗ trợ.

### 12.2. Gap giữa snapshot và CDC

Snapshot ở W1, stream bắt đầu W2>W1 có thể bỏ sót writes trong khoảng. Cần consistent capture protocol hoặc capture changes trước và deduplicate sau.

### 12.3. Multi-shard snapshots

Chụp độc lập từng shard không tự bảo đảm global transaction consistency. Backup/migration tool phải hỗ trợ coherent point nếu ứng dụng cần.

### 12.4. Resume tokens có thời hạn

CDC retention hoặc oplog window có thể hết trước khi backfill xong. Theo dõi lag và thời điểm lịch sử cũ nhất còn có thể đọc.

## 13. Backfill lịch sử: checkpoint và backpressure

~~~text
read durable migration checkpoint

for each stable source range:
    read bounded batch at snapshot S
    transform records deterministically to schema v2
    conditionally apply to target by entity version
    wait for durable acknowledgement
    persist checkpoint for completed range

after all ranges:
    consume changes after W
    reconcile source vs target at an agreed watermark
~~~

### 13.1. Checkpoint phải ghi sau target writes

Nếu checkpoint ghi trước rồi worker crash, records còn thiếu có thể bị bỏ qua. Nếu target commit trước nhưng checkpoint chưa ghi, chạy lại phải idempotent.

### 13.2. Dùng stable ranges/cursors

Offset pagination trên nguồn liên tục insert/delete có thể skip hoặc lặp records. Chọn stable snapshot/partition ranges/continuation tokens theo khả năng engine.

### 13.3. Limit concurrency

Backfill phải có max in-flight operations, batch bytes, retry budget và adaptive throttling, để không làm production requests vượt p99 SLO.

### 13.4. Worker errors phải phân loại

Timeout có thể retry, malformed document cần quarantine, conditional version conflict có thể là expected newer target, permission error cần dừng. Không retry vô hạn cùng lỗi vĩnh viễn.

## 14. CDC và thứ tự thay đổi

### 14.1. Inserts/updates/deletes đều cần được capture

Chỉ copy records đang tồn tại không bảo toàn xóa hoặc TTL. Một record bị xóa trong lúc backfill có thể quay trở lại nếu thiếu tombstone.

### 14.2. Event ID khác business command ID

`commandId` dùng deduplicate requests nghiệp vụ; `eventId` dùng deduplicate deliveries; `aggregateVersion` dùng chặn ghi lùi state. Không thay thế nhau một cách tùy ý.

### 14.3. Ordering thường có phạm vi

Một change stream có thể đảm bảo thứ tự theo partition/key chứ không phải mọi entities. Không dựa vào global timestamp để resolve concurrent updates nếu source không bảo đảm.

### 14.4. Backlog tăng khi copy quá nhanh

Nếu source tạo 50.000 changes/s và target chỉ apply 30.000/s, backlog tăng 20.000 changes/s; phải tăng effective throughput hoặc giảm load trước khi hết history window.

### 14.5. Late events không nên phá target

Target apply event cũ sau event mới phải dùng conditional/version semantics.

## 15. Monotonic version apply

Giả sử:

~~~text
10:00 snapshot contains Order v7
10:02 user commits Order v8
10:03 CDC applies v8 to target
10:04 backfill attempts to write v7
~~~

### 15.1. Không upsert mù

Nếu backfill replace v8 bằng v7, một acknowledged update bị mất. Target chỉ nhận record nếu incoming version mới hơn current version theo authority contract.

### 15.2. Equal version

Cùng version, cùng canonical state có thể là duplicate. Cùng version nhưng nội dung khác là conflict/corruption và cần quarantine/reconciliation.

### 15.3. Check ở nơi ghi

Đọc current version trong Java rồi mới put không atomic trước concurrent writers. Dùng conditional write/CAS/transaction của database theo scope hỗ trợ.

### 15.4. Cross-entity invariants

Version từng Order chưa đủ để bảo vệ reservation duy nhất trên một Property hay aggregate quota toàn tenant; cần transaction/registry/authority thích hợp.

## 16. Delete, TTL và tombstone

### 16.1. Delete là thay đổi có version

Một tombstone `deleted=true, version=9` phải ngăn backfill snapshot v7 ghi lại record.

### 16.2. TTL phải bảo toàn ý nghĩa

Nếu session hết hạn lúc 12:00, copy lúc 11:59 không nên đặt TTL mới 24 giờ từ lúc copy, khiến session sống dài hơn.

### 16.3. Hard delete và erasure

Source/target/staging/backup có thể chứa các bản dữ liệu nhạy cảm. Migration phải tuân thủ retention, erasure policy và không resurrect qua replay.

### 16.4. Tombstone retention

Chỉ GC tombstones khi mọi consumers/replicas/migration workers đã qua watermark cần thiết. Không dọn “cho nhẹ đĩa” khi backfill còn chạy.

## 17. Dual-write và unknown commit

~~~text
Command C (idempotencyKey=K)
    -> Old write: COMMITTED
    -> New write: TIMEOUT

Unknown: New may have committed, response may be lost.
~~~

### 17.1. Retry với key mới là sai

Một lệnh Order/Payment/Inventory retry với `commandId` khác có thể tạo side effect lần hai.

### 17.2. Dùng outbox/change log làm cầu nối

Old remains authority; ghi outbox intent atomically theo engine contract; consumer cập nhật target idempotently. Vẫn phải kiểm version/order/tombstones.

### 17.3. Nếu buộc dual-write

Thiết kế rõ trạng thái partial failure, reconciliation, retries, ownership, invariant và recovery. Không gọi nó “2 copies an toàn hơn” nếu không có protocol.

### 17.4. Sau cutover

New owner có authority. Old route chỉ được reject/forward theo epoch, không tiếp tục ghi một lịch sử riêng.

## 18. Cutover: chuyển authority, không chỉ đổi endpoint

~~~text
1. Declare cutover for bucket/tenant cohort.
2. Fence old owner against new writes.
3. Drain in-flight operations or resolve unknown outcomes.
4. Apply source changes through committed watermark W.
5. Verify target data and business invariants at W.
6. Atomically advance routing directory epoch.
7. Allow target owner authoritative writes.
8. Monitor stale routes, p99, errors, divergence.
~~~

### 18.1. Fencing tại data plane

Chỉ đặt flag trong Java client không đủ; old owner/router phải có cơ chế từ chối writes stale sau khi mất quyền.

### 18.2. Epoch tăng đơn điệu

Từ epoch 15 sang 16, mọi stale clients dùng 15 phải refresh. Nếu reverse migration, dùng epoch mới, không tái sử dụng 15.

### 18.3. In-flight writes

Một request bắt đầu trước fence nhưng commit sau route switch có thể bị mất khi target không thấy nó. Quy trình phải drain/coordinate commit boundary.

### 18.4. Canaries

Chuyển một tenant hoặc một tập virtual buckets trước để quan sát. Nhưng các cross-bucket queries/transactions có thể cần toàn bộ topology cùng sẵn sàng.

## 19. Đọc trong giai đoạn chuyển

### 19.1. Public reads old, shadow reads new

Đường đọc chính vẫn là old; đường new dùng để so sánh cùng logical version/watermark. Không trả shadow result vào business response khi chưa chốt.

### 19.2. New-only reads sau cutover

Đã chuyển authority thì target là nguồn đọc chính thức. Fallback về old thiếu tombstone guard có thể trả state cũ.

### 19.3. Read repair cần cẩn thận

Thấy old/new khác nhau rồi “copy bên có timestamp lớn hơn” có thể sai khi clock skew/unknown commit. Dùng source authority và monotonic version/sequence.

### 19.4. Cursors đổi theo routing

Continuation token chứa old bucket hoặc shard có thể không dùng được sau migration. Version cursors, định nghĩa expiry/restart và tránh silently skip/duplicate pages.

## 20. Truy vấn sau bucketing: fan-out và phân trang

Trước:

~~~text
listOrders(tenantId)
  -> one partition query ordered by createdAt
~~~

Sau:

~~~text
listOrders(tenantId)
  -> query B virtual buckets
  -> merge by (createdAt DESC, orderId DESC)
  -> return bounded page
~~~

### 20.1. Tie-breaker ổn định

Nhiều Orders có cùng createdAt; thêm orderId làm sort deterministic. Cursor phải nhớ vị trí/routing version của các buckets.

### 20.2. Không quét toàn bộ buckets cho mọi page nếu tránh được

Một materialized view hoặc index theo `(tenantId,createdAt)` có thể phù hợp, nhưng cần tính write amplification và eventual consistency.

### 20.3. Aggregation và unique constraints

Khi Orders không còn cùng partition, tenant-wide unique orderNumber, quotas và counters có thể cần registry/conditional authority.

### 20.4. Query consistency

Cursor trên các buckets cập nhật song song có thể thấy duplicate/skip nếu không có snapshot consistency. API cần nêu semantics thực, không hứa ổn định tuyệt đối.

## 21. Định danh, references và uniqueness

### 21.1. Giữ business ID

`orderId` không nên đổi chỉ vì shard đổi. Payment receipts, external webhooks và CDC events thường tham chiếu ID cũ.

### 21.2. Không biến shard address thành identity

Reference lưu `shardA/order123` gây coupling vật lý. Dùng logical ID và router, hoặc versioned alias khi chuyển.

### 21.3. Unique key scope có thể thay đổi

Nếu uniqueness trước đây được bảo đảm trong partition tenant, chia 16 buckets làm uniqueness local mỗi bucket không đủ. Cần registry/transaction phù hợp.

### 21.4. Event IDs deterministic

Backfill lịch sử không nên tạo UUID mới mỗi lần chạy vì retry sẽ nhân đôi events. Dùng stable source event identity hoặc deterministic derivation có kiểm soát.

## 22. Schema evolution: expand, migrate, contract

### 22.1. Expand

Triển khai readers hiểu v1 và v2; thêm indexes/fields mới và versioned converters. Không deploy writer v2 trước khi readers cũ có thể hiểu hoặc bị định tuyến tránh v2.

### 22.2. Migrate

Backfill documents, bắt live changes, so source/target trên canonical model. Có thể dùng lazy upgrade kết hợp background job nếu phù hợp.

### 22.3. Contract

Chỉ gỡ v1 readers/fields sau khi toàn bộ jobs/clients/consumers đã chuyển và recovery backup cũ có tooling tương thích.

### 22.4. Không đoán version từ field optional

Nếu `customer` thiếu vì business null hợp lệ, không suy document là v1 chỉ vì field đó không có. Dùng explicit schemaVersion khi cần.

### 22.5. Conversion phải giữ semantics

Money precision, timezone, Unicode, encryption, TTL, null/missing và default values phải được mapping rõ; không chỉ rename fields.

## 23. Java: hàm gán virtual bucket ổn định

Ví dụ Java 17:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class OrderBucketing {
    public static final int BUCKETS = 256;
    public static final String HASH_VERSION = "sha256-v1";

    private OrderBucketing() {}

    public static int bucket(String tenantId, String orderId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("invalid key");
        }
        String encoded = tenantId.length() + ":" + tenantId
            + orderId.length() + ":" + orderId;
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(encoded.getBytes(StandardCharsets.UTF_8));
            long hash = ByteBuffer.wrap(digest, 0, 8).getLong();
            return (int) Long.remainderUnsigned(hash, BUCKETS);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

### 23.1. Không đổi số buckets âm thầm

`BUCKETS=256` và hash version thuộc persisted routing contract; đổi chúng là migration, không chỉ sửa cấu hình.

### 23.2. Chuẩn hóa đa ngôn ngữ

Ví dụ dùng Java `String.length()` theo UTF-16 units. Nếu Go/Python cùng tính bucket, phải chuẩn hóa canonical byte framing/Unicode và dùng golden test vectors ở mọi runtime.

### 23.3. Test workload thực

Hash đồng đều với ID ngẫu nhiên không bảo đảm QPS đều nếu một vài IDs nhận phần lớn requests. Đo per-bucket heat.

## 24. Java: routing directory với epoch

~~~java
public record BucketRoute(
    int bucket,
    String ownerCluster,
    String allowedRegion,
    long epoch,
    State state
) {
    public enum State { ACTIVE, MOVING, FENCED }
}

public interface BucketDirectory {
    BucketRoute resolve(int bucket);

    boolean compareAndAdvance(
        int bucket,
        long expectedEpoch,
        BucketRoute proposedRoute
    );
}

public record OrderWrite(
    String trustedTenantId,
    String orderId,
    String commandId,
    long expectedVersion,
    String newStatus
) {}

public enum WriteStatus {
    COMMITTED, VERSION_CONFLICT, STALE_EPOCH, UNKNOWN
}

public interface FencedOrderRepository {
    WriteStatus apply(
        OrderWrite command,
        BucketRoute route
    );
}
~~~

### 24.1. Method không tự tạo guarantee

`compareAndAdvance` phải atomic theo control plane; nơi nhận writes phải enforce fencing token, không chỉ tin cache ở client.

### 24.2. UNKNOWN outcome cần reconcile

Timeout không chứng minh chưa commit. Retry cùng commandId nếu protocol cho phép, hoặc tra authoritative receipt; không tạo commandId mới.

### 24.3. Region là security constraint

Không gửi tenant tới một owner ở region không được phép; dù routing directory trả route, authorization/residency policy vẫn phải kiểm.

## 25. Java: chuyển document v1 sang v2

~~~java
import java.util.List;

public record LegacyEvent(
    long sequence, String eventId, String type) {}

public record LegacyOrder(
    String tenantId,
    String orderId,
    String status,
    long version,
    List<LegacyEvent> events
) {}

public record OrderV2(
    String tenantId,
    String orderId,
    String status,
    long version,
    int schemaVersion
) {}

public record OrderEventV2(
    String tenantId,
    String orderId,
    long sequence,
    String eventId,
    String type
) {}

public final class OrderTransform {
    public static OrderV2 summary(LegacyOrder source) {
        if (source == null || source.version() < 0) {
            throw new IllegalArgumentException("invalid order");
        }
        return new OrderV2(
            source.tenantId(), source.orderId(),
            source.status(), source.version(), 2);
    }

    public static List<OrderEventV2> events(
            LegacyOrder source) {
        return source.events().stream()
            .map(e -> new OrderEventV2(
                source.tenantId(),
                source.orderId(),
                e.sequence(), e.eventId(), e.type()))
            .toList();
    }
}
~~~

### 25.1. Converter thuần nên deterministic

Không gửi email, charge payment hoặc tạo random eventId trong converter. Backfill retry cùng input phải ra cùng output.

### 25.2. Ghi Order và events có thể không atomic

Transformation chỉ tạo output; target writer phải có transaction/outbox/reconciliation protocol theo khả năng engine.

### 25.3. Ví dụ không thay schema mapping thực

Ứng dụng phải bổ sung mọi field, null validation, event ordering, precision và encryption. Một document lớn có thể cần streaming từng chunk.

## 26. Java JUnit: kiểm tính ổn định và retry

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class OrderBucketingTest {
    @Test
    void sameIdentityGetsSameBucket() {
        int first = OrderBucketing.bucket("T1", "O9");
        int second = OrderBucketing.bucket("T1", "O9");
        assertEquals(first, second);
        assertTrue(first >= 0 && first < 256);
    }

    @Test
    void blankTenantIsRejected() {
        assertThrows(IllegalArgumentException.class,
            () -> OrderBucketing.bucket("", "O9"));
    }
}
~~~

### 26.1. Golden vectors cần có giá trị kỳ vọng cố định

Test trên chỉ kiểm deterministic trong một runtime. Với production, cố định expected bucket cho nhiều keys, Unicode và byte encodings để phát hiện đổi thuật toán khi deploy.

### 26.2. Test failure giữa page

Worker ghi 90/100 documents rồi crash trước checkpoint. Restart phải copy lại không tạo events trùng hoặc overwrite version mới.

### 26.3. Test tombstone race

Snapshot v4, CDC delete v5, backfill v4 đến sau; target vẫn phải được coi là deleted version 5.

### 26.4. Test stale epoch

Writer cũ giữ route epoch 10, directory đã epoch 11; write phải bị reject/redirect theo protocol và không tạo thứ tự ghi song song.

## 27. MongoDB: resharding và schema refactor

MongoDB sharded cluster hỗ trợ cơ chế phân mảnh theo shard key. Các phiên bản mới có công cụ resharding/native migration, nhưng tính năng, điều kiện, unique indexes, transaction behavior và operational constraints cần kiểm theo version/deployment cụ thể.

### 27.1. Move chunk khác đổi shard key

Move/split chunks có thể thay physical placement trong cùng key definition; resharding thay cách dữ liệu được chia theo key. Đừng nhầm hai thao tác.

### 27.2. Không có một quy tắc “shard key tuyệt đối không thể đổi”

Một số thay đổi giá trị shard key và thao tác collection resharding được hỗ trợ có điều kiện ở các version cụ thể. Không suy API/limitations từ thông tin cũ.

### 27.3. Native resharding không sửa mảng events

Đổi shard key có thể được engine hỗ trợ, nhưng embedded-document split, Java readers, old indexes, CDC và aggregate boundaries vẫn là application migration.

### 27.4. Change streams

Kiểm resume tokens/retention/consumer behavior khi thay topology; không giả định CDC consumer đã dừng lâu vẫn resume được từ token cũ.

### 27.5. Operational readiness

Kiểm disk/headroom, data skew, zone constraints, long transactions, canary queries, backup compatibility và rollback plan.

## 28. DynamoDB: primary key đổi thường cần item/table mới

Trong DynamoDB, primary key của một item xác định identity. Không sửa partition/sort key của item bằng `UpdateItem` như một field bình thường; tạo item ở key mới và xử lý old item theo protocol.

### 28.1. Table schema

Muốn đổi partition key schema của cả table thường cần một table mới hoặc công cụ migration được hỗ trợ. Thêm GSI không thay primary key của item.

### 28.2. Source-to-target

Export/Scan có kiểm soát, transform `PK/SK`, conditional writes, source Streams/outbox catch-up và cutover application routing.

### 28.3. Per-partition hot key

`PK=TENANT#T1` bị throttle có thể được phân tán thành `TENANT#T1#B07`; nhưng list tenant tốn fan-out và uniqueness có thể không còn local.

### 28.4. Transactions có giới hạn

`TransactWriteItems` có phạm vi/giới hạn API, không thể gộp hàng triệu item moves trong một transaction toàn bảng.

### 28.5. Streams retention không vô hạn

Backfill dài cần kiểm capture position/catch-up margin; nếu history hết hạn, phải bootstrap lại theo source semantics.

## 29. Cosmos DB for NoSQL: partition key và container

Partition key là quyết định mô hình quan trọng. Khả năng thay đổi partition key bằng API/tool phụ thuộc account và feature/version; cách làm phổ biến là dựng container đích rồi chuyển dữ liệu.

### 29.1. RU budget

Bulk copy, query cross-partition và change feed consumption đều tiêu tốn tài nguyên; cần throttle worker để production không bị 429.

### 29.2. Transactional scope

Transactional batch và stored procedure semantics thường gắn với một logical partition. Đổi partition key có thể phá atomic scope cũ.

### 29.3. Unique keys

Uniqueness có phạm vi liên quan partition. Nếu application cần unique orderNumber toàn tenant, cần verify sau khi chia buckets.

### 29.4. Change feed delete

Các change feed modes/configurations có khả năng ghi nhận deletes khác nhau; không tự assume physical delete sẽ có event đầy đủ. Có thể cần domain tombstone/outbox.

### 29.5. Data residency

Migration worker có thể move data giữa containers/regions; mọi tenant phải ở nơi được phép.

## 30. Cassandra/ScyllaDB: primary key dẫn dắt table

Trong Cassandra/ScyllaDB, partition key và clustering keys liên quan token locality, query shape và row identity. Đổi primary key thường là tạo table mới và chuyển data.

### 30.1. Query-driven tables

Các tables `orders_by_id` và `orders_by_tenant_time` có thể phục vụ access patterns khác nhau. Một table không cần đáp ứng mọi truy vấn.

### 30.2. Time bucketing

`(tenantId, monthBucket, hashSuffix)` có thể giảm partition width, nhưng tháng hiện tại có thể nóng và query tháng cần fan-out.

### 30.3. Không chữa key mới bằng `ALLOW FILTERING`

Nếu API query không phù hợp primary key, `ALLOW FILTERING` có thể làm scan nặng; cần thiết kế access path thực sự.

### 30.4. LWT/batches/CDC

Lightweight transactions, batches và CDC có semantics/phạm vi khác nhau theo sản phẩm/version; không coi logged batch là transaction đa partition tùy ý.

### 30.5. TTL, tombstone, repair

Giữ delete/retention semantics khi chuyển data, không xóa SSTables/commitlog thủ công để dọn old schema.

## 31. Redis Cluster: đổi key pattern và hash slots

Redis Cluster có hash slots. Thay tên key hoặc hash tag có thể làm key đổi slot:

~~~text
Old: order:T1:O9
New: order:{T1}:O9
~~~

### 31.1. Key rename không đơn thuần sửa String

Records hiện vẫn tồn tại ở key cũ; cần copy/restore/rekey với TTL và type đúng, xử lý live writes và kiểm consistency.

### 31.2. Hash tag và locality

Cùng `{T1}` có thể giúp một số multi-key operations cùng slot, nhưng cũng có thể dồn tenant lớn vào một hot slot.

### 31.3. Cluster slot migration khác application migration

Chuyển ownership slot vật lý qua Redis Cluster mechanism khác với đổi key format trong Java code.

### 31.4. TTL preservation

Copy key không giữ exact expiresAt có thể kéo dài sống dữ liệu hoặc làm session hết hạn sớm. Kiểm trong môi trường thử nghiệm.

## 32. Multi-tenant shared sang dedicated placement

Không phải mọi hotspot đều cần đổi shard key. Có thể chuyển whale tenant khỏi shared cluster sang dedicated cluster, giữ logical IDs/schema cũ.

### 32.1. Directory theo tenant

`tenantId -> region, cluster, epoch, state`. Backfill tenant-scoped, catch up, fence old owner và chuyển route theo tenant.

### 32.2. Hot item vẫn cần xem riêng

Dedicated cluster không làm một inventory item có thể chấp nhận vô hạn conditional writes. Aggregate invariant vẫn giới hạn.

### 32.3. Cross-collection data

Tenant move cần Orders, Events, Payment receipts, idempotency records, indexes, outbox và backup settings; không chỉ bảng chính.

### 32.4. Policy

Dedicated cluster có thể có encryption keys/region/retention khác; migration phải bảo đảm hợp đồng tenant.

## 33. Reconciliation: counts chưa đủ

Source và target có cùng một triệu records nhưng 100 records sai version vẫn không phải migration thành công.

### 33.1. Compare theo logical ID

So `(tenantId, orderId)`, version, status, amount, delete state, event sequence và expiresAt.

### 33.2. Canonical transform và hash

Biến v1 thành canonical v2 representation rồi tính digest; loại các fields transient theo contract. Cùng hash chưa chứng minh mọi business invariant nhưng giúp phát hiện lệch.

### 33.3. So tại cùng mốc

Source có v11 trong khi target v10 vì CDC lag thì compare ngay sẽ báo false discrepancy. Dùng watermark/version-aware reconciliation.

### 33.4. Per-tenant/per-bucket stats

Counts, bytes và checksums theo bucket giúp tìm missing key ranges, không chỉ tổng toàn cluster.

### 33.5. Domain invariants

Order không duplicate, inventory không âm, version monotonic, ledger cân, event sequence hợp lệ và tenant isolation phải được kiểm độc lập.

## 34. Metrics và quality gates

| Nhóm | Chỉ số |
|---|---|
| Backfill | Records/bytes completed, checkpoint |
| CDC | Lag, oldest event, retention horizon |
| Routing | Stale epoch, old-owner writes |
| Data | Missing/extra IDs, version mismatches |
| Deletes | Tombstones applied, resurrection cases |
| Business | p95/p99, error, conflict, order duplicate |
| Capacity | CPU, IO, RU/RCU/WCU, disk/network |
| Query | Fan-out, scanned/returned, index usage |
| Compatibility | v1/v2 reads, stale clients/jobs |
| Security | Cross-tenant/residency violations |
| Cost | Backfill requests, extra storage/egress |

### 34.1. Cutover gate có kiểm chứng

Ví dụ: target đã áp dụng CDC tới W, không còn unexplained gaps, full data reconciliation trong phạm vi bắt buộc đã pass, old owner fencing hoạt động, APIs đáp ứng SLO trong canary.

### 34.2. Quality gate theo nghiệp vụ

Số mismatches cần định nghĩa và có owner. Một field debug lệch khác với status/amount/balance lệch; không tự loại bỏ những fields quan trọng để có biểu đồ “0 mismatch”.

### 34.3. Lag nhỏ vẫn có thể không đủ

Lag trung bình 1 giây nhưng một partition đã kẹt 30 phút; cần max lag/oldest unapplied age theo partition.

## 35. Capacity và chi phí migration

### 35.1. Source đọc thêm

Backfill scan có thể làm cache miss, disk IO và p99 user tăng. Cần rate budgets/maintenance windows thích hợp.

### 35.2. Target ghi thêm

Bulk imports, indexes, compaction và replication có thể cần nhiều disk/RU hơn live data footprint. Target phải có headroom.

### 35.3. Network egress

Cross-region copy có chi phí và data residency constraints; không chỉ tính DB operations.

### 35.4. Migration kéo dài tăng double storage

Old và new cùng lưu dữ liệu trong nhiều ngày/tuần. Chi phí snapshot/backup, indexes và CDC cũng tăng.

### 35.5. N−1 failure

Target vừa đủ dưới điều kiện bình thường chưa chắc sống được khi mất node. Cutover readiness phải tính capacity lúc degraded.

## 36. Rollback trước và sau cutover

### 36.1. Trước cutover

Old vẫn authority; có thể dừng backfill/shadow và giữ public reads/writes ở old. Dọn staging theo retention/supported API.

### 36.2. Sau cutover

New đã nhận writes mới. Chuyển route về old khi chưa copy ngược writes sẽ mất dữ liệu đã ACK. Rollback lúc này là một migration nữa hoặc phải roll-forward bằng cách sửa target.

### 36.3. Reverse migration

Nếu buộc chuyển ngược, dựng reverse capture, đồng bộ target→old, fence new owner, chốt watermark và advance epoch mới. Không bật lại old writer tự do.

### 36.4. Data retention

Giữ old copies cho recovery window đã được quyết định, nhưng không vô hạn. Khi xóa phải tuân thủ privacy/legal hold, backups và khả năng restore.

## 37. Runbook thay đổi shard key/bucket/schema

1. Xác định pain point, workloads và SLO/correctness requirements.
2. Ghi inventory controllers, consumers, scheduled jobs, indexes, caches, backups, tenants và IAM.
3. Thiết kế key/bucket/schema v2, versioning, routing epoch và transaction invariants.
4. Kiểm query matrix, uniqueness, fan-out, partition skew và expected costs.
5. Chuẩn bị target indexes, quotas, routing directory, capacity và verified backup.
6. Triển khai compatible readers/writers, converters và feature flags.
7. Bắt source changes theo consistent snapshot/watermark protocol.
8. Backfill theo batches có checkpoint và idempotent/versioned writes.
9. Catch up CDC, bảo toàn deletes/TTL, quarantine errors và reconcile.
10. Thử shadow read/canary với production-shaped workload và tenant isolation.
11. Fence/drain old writes, chốt watermark, advance route epoch.
12. Monitor new authority, stale clients, p99, conflicts, data divergence và costs.
13. Tăng dần cohorts, giữ recoverability và rollback/roll-forward runbook.
14. Retire old schemas/data sau khi tất cả consumers, backups và retention gates đã đạt.

### 37.1. Mỗi bước cần điều kiện hoàn thành

Không nhảy từ “copy 100% records” sang “đã an toàn cutover” nếu CDC lag, deletes hoặc old writers còn hoạt động.

### 37.2. Runbook phải chỉ owner

Ai có quyền advance epoch? Ai phê duyệt xóa old table? Ai đối soát Orders và Payments? Ai dừng migration khi SLO xấu? Tránh một job tự quyết tất cả.

## 38. Case study: whale tenant

Một SaaS đặt phòng có tenant A chiếm 60% Order writes. Team chọn 32 hash buckets cho Orders.

### 38.1. Lợi ích

Writes phân tán trên nhiều logical keys, giảm hotspot do tenantId-only nếu traffic trải nhiều Orders độc lập.

### 38.2. Rủi ro

`listOrdersByTenant` trở thành multi-bucket merge; reservation theo Property vẫn cần authority bảo đảm no double-booking.

### 38.3. Migration

Backfill Orders, capture events, validate versions, shadow read, switch tenant routing epoch và monitor skew.

### 38.4. Bài học

Không đánh đồng “chia nhiều Orders” với “chấp nhận nhiều concurrent writes lên cùng một reservation”.

## 39. Case study: đổi sang time bucket

Hệ thống IoT lưu events trong partition `deviceId`, nhiều năm dữ liệu. Thiết kế mới dùng `(deviceId,yearMonth)` cho truy vấn gần đây và retention.

### 39.1. Timestamp nào dùng để bucket?

Event time hay ingest time? Late events có thể đến sau nhiều ngày; cần quy tắc rõ. Định nghĩa timezone UTC hoặc business zone thống nhất.

### 39.2. Current bucket có thể nóng

Thiết bị gửi 10k events/s đều vào current month. Có thể thêm hash suffix nhưng query một tháng phải fan-out.

### 39.3. TTL

Retention dựa `event occurred at` khác `copied at`. Giữ original expiresAt để không kéo dài tuổi dữ liệu.

### 39.4. Verify

Kiểm min/max event time, event IDs, duplicates, chronological ordering, late arrivals và archive policy.

## 40. Case study: tách history array

Order v1 chứa `events[]` và liên tục rewrite document. Order v2 tách summary và event records.

### 40.1. Converter

Giữ deterministic `(tenantId, orderId, sequence, eventId)`, không tạo random IDs trong mỗi lần backfill.

### 40.2. Consistency

Status transition và append event phải có source of truth, transaction/outbox guard; không ghi hai collections độc lập rồi cầu may.

### 40.3. Read APIs

`getOrderSummary` đọc v2 summary; `listOrderEvents` phân trang; clients đòi full history cần thay API contract.

### 40.4. Old data

Chỉ bỏ embedded events v1 sau khi event sequence/hash/recovery kiểm đủ, không chỉ kiểm Order summary.

## 41. Case study: tăng 8 lên 64 buckets

Một hệ thống hardcode `hash(orderId)%8` trong key. Sau khi dùng 64, nhiều lookups thất bại.

### 41.1. Nguyên nhân

Service mới tính bucket khác nơi record cũ đang nằm. Nếu một số service vẫn 8, hai bộ clients có thể ghi cùng Order ở hai nơi.

### 41.2. Fix

Đóng băng v1 mapping, dựng v2 keyspace/route version, backfill + catch-up và switch authority theo cohort. Đối soát duplicates/missing IDs.

### 41.3. Nếu có virtual buckets

Có thể chỉ thay owner mapping khi thêm physical shards, không cần thay logical bucket count nếu số virtual buckets đủ mịn.

### 41.4. Prevent

Version hash and route contract, golden vectors, reject writes từ clients route stale và migration runbook.

## 42. Những ngộ nhận thường gặp

### “Thay shard key chỉ là đổi annotation”

Sai: data placement, routing và query plans cần chuyển.

### “Đổi modulus là mở rộng bucket miễn phí”

Sai: nhiều logical IDs đổi vị trí.

### “Hash đều nghĩa mọi writes đều đều”

Sai: hot entities và hot tenants có access frequency lệch.

### “Thêm shard sửa được single hot counter”

Không khi một invariant cần serialization ở một entity.

### “Sao chép xong là an toàn”

Không khi source có live writes và không có snapshot/CDC.

### “Bắt CDC sau snapshot lúc nào cũng được”

Không: có thể tạo gap.

### “Backfill upsert luôn idempotent”

Không nếu ghi đè version mới hoặc sinh IDs khác mỗi lần.

### “Chỉ cần timestamp chọn record mới”

Không khi clock skew hoặc source ordering không theo timestamp.

### “Deletes không cần migrate”

Sai: có nguy cơ resurrection.

### “Dual-write là hai bản an toàn”

Không: partial failure, reordering và unknown commit gây divergence.

### “Cutover là đổi endpoint”

Không: còn fencing, draining, watermark và authority.

### “Rollback sau cutover chỉ việc đổi flag”

Không khi target đã ACK writes mới.

### “Số record bằng nhau nghĩa đúng”

Sai: values/versions/events có thể lệch.

### “Document tách nhỏ luôn tốt hơn”

Không nếu cần atomic updates/locality cho một aggregate.

### “Engine native resharding giải quyết mọi vấn đề”

Không: business transactions, authorization, indexes, CDC và schema vẫn cần kiểm.

### “NoSQL schema linh hoạt không cần version”

Sai khi nhiều app versions và stored documents cùng tồn tại.

### “Đổi key không ảnh hưởng security”

Sai: tenant routing và data residency có thể thay đổi.

## 43. Checklist trước khi cutover

1. Mục tiêu migration được đo theo SLO và correctness chưa?
2. Đã phân biệt hot partition với hot entity chưa?
3. Access pattern/read-write matrix đã được xem xét chưa?
4. Logical IDs có giữ ổn định không?
5. Bucket hash/encoding/version đã cố định chưa?
6. Routing directory có owner và epoch không?
7. Fencing được enforce ở nơi ghi chưa?
8. Index/unique constraints của v2 có sẵn chưa?
9. Aggregate/transaction scope có được bảo toàn chưa?
10. Tất cả producers/consumers/jobs/caches đã kiểm kê chưa?
11. Có compatible v1/v2 readers/writers không?
12. Backup/restore đã được xác minh chưa?
13. Target có đủ capacity cho live + migration không?
14. Backfill lấy snapshot nhất quán chưa?
15. CDC nối liền snapshot bằng watermark hợp lệ chưa?
16. Backfill/checkpoints có retry idempotent không?
17. Versioned CAS guards ngăn ghi lùi chưa?
18. Deletes/TTL/tombstones đã được xử lý chưa?
19. Shadow reads so tại cùng logical version chưa?
20. Đã kiểm counts/hash/invariants theo tenant/bucket chưa?
21. Có canary và load profile đại diện chưa?
22. Old in-flight writes được drain/fence chưa?
23. Stale routes có thể refresh/retry an toàn chưa?
24. Read pagination/cursors theo version mới chưa?
25. Data residency, IAM và tenant isolation đã kiểm chưa?
26. Có plan khi UNKNOWN commit và partial failure không?
27. Có roll-forward/reverse migration plan sau cutover không?
28. Có alert/owner và đủ CDC retention margin không?
29. Data cũ được giữ theo retention/backup/privacy policy không?
30. Có quy trình ký duyệt retirement của source cũ không?

## 44. Bài tập thực hành

### Bài 1 — Nhận diện ba dạng thay đổi

Phân biệt di chuyển physical shard, đổi partition key, tăng hash buckets, đổi virtual bucket owner và tách embedded array. Việc nào đòi re-key data?

### Bài 2 — Hot partition

Cluster 12 shards, CPU average 35% nhưng một shard 98%; tenant A chiếm 60% writes. Thu metrics nào trước khi quyết định migration?

### Bài 3 — Hot entity

Một inventory item chịu hàng nghìn conditional decrements/s. Vì sao thêm buckets theo itemId không tự giải quyết contention?

### Bài 4 — Hash modulo

Cho hash=29, B=8 và B=32. Tính bucket cũ/mới, mô tả lỗi nếu thay config đồng loạt.

### Bài 5 — Virtual buckets

Thiết kế 256 virtual buckets cho 4 shards; sau khi thêm shard thứ năm, chuyển ownership thế nào mà không đổi Order ID?

### Bài 6 — Routing epoch

Client có epoch 10, directory epoch 11. Viết protocol xử lý stale write, refresh và giữ idempotency.

### Bài 7 — Khóa theo tenant

So các PK: tenantId, tenantId#orderId, tenantId#bucket và tenantId#month cho get/list/range queries.

### Bài 8 — Fan-out

Tenant có 64 buckets, API trả 20 Orders mới nhất. Thiết kế merge sort, cursor và concurrency limits.

### Bài 9 — Uniqueness

`orderNumber` phải duy nhất trong một tenant nhưng Orders nằm nhiều buckets. Thiết kế registry hoặc transactional authority.

### Bài 10 — Quota

Tenant có quota 1.000 active jobs, phân tán nhiều buckets. Tại sao đếm eventual rồi cho phép ghi có thể vượt quota?

### Bài 11 — Document split

Order có events[] tăng không giới hạn. Đề xuất schema summary+events, nêu transaction/outbox semantics.

### Bài 12 — Không tách quá mức

Một Order luôn chứa tối đa năm line items và mọi GET cần chúng. Có nên tách? Giải thích aggregate tradeoff.

### Bài 13 — Schema version

Đổi `customerName` sang `customer.displayName`; thiết kế readers v1/v2 và expand–migrate–contract.

### Bài 14 — Upsert ghi lùi

Backfill snapshot v7 tới sau khi CDC đã ghi v8. Viết điều kiện apply an toàn.

### Bài 15 — Tombstone

Source xóa v9, backfill v7 tới muộn. Vì sao target không được resurrect record?

### Bài 16 — TTL

Session có expiresAt gốc 12:00. Copy nó lúc 11:59 nhưng target đặt TTL 24 giờ từ lúc copy thì sai ở đâu?

### Bài 17 — Watermark

Snapshot W1, CDC bắt đầu W2>W1. Giải thích gap và cách tạo consistent handoff.

### Bài 18 — CDC reordering

Target nhận v10 rồi v9 của cùng Order; định nghĩa monotonic apply và duplicate handling.

### Bài 19 — Crash sau 90 writes

Worker commit 90/100 target records rồi crash trước checkpoint. Làm sao resume không duplicate?

### Bài 20 — Unknown commit

Old write success, target timeout; đề xuất outbox/idempotency/reconciliation thay vì retry lệnh mới.

### Bài 21 — Cutover fencing

Một old writer bắt đầu trước route switch nhưng commit sau switch. Thiết kế drain/epoch protocol.

### Bài 22 — Backlog

Source tạo 50k events/s, consumer apply 30k/s. Tính backlog tăng và điều kiện để catch up.

### Bài 23 — MongoDB

Phân biệt chunk movement, resharding và document schema migration. Những gì native resharding không thể tự sửa?

### Bài 24 — DynamoDB

Từ PK=tenantId sang tenantId#bucket, lập kế hoạch table mới, conditional copy, Streams và cutover.

### Bài 25 — Cosmos DB

Đổi partition key cho container: nêu RU, transaction scope, unique key và change feed delete risks.

### Bài 26 — Cassandra

Từ `orders_by_tenant` sang `orders_by_tenant_month`, chọn partition widths, clustering order và TTL/tombstones.

### Bài 27 — Redis Cluster

Đổi `order:T1:O9` sang `order:{T1}:O9`: phân tích hash slots, hot tenant và TTL.

### Bài 28 — Java transform

Viết converter thuần từ LegacyOrder sang OrderV2+EventV2 với deterministic event IDs.

### Bài 29 — Golden vectors

Viết test hash outputs cho Unicode và punctuation; vì sao phải chốt canonical byte format giữa Java/Go?

### Bài 30 — Security

Worker đọc tenant A rồi ghi vào bucket của B. Thiết kế kiểm tenant/region và credential scope.

### Bài 31 — Reconciliation

Source/target cùng 1 triệu records nhưng 100 records sai status. Thiết kế so ID/version/hash và business invariants.

### Bài 32 — Shadow reads

Source v11, target v10 vì CDC lag. Làm sao so tại cùng watermark trước khi kết luận lỗi?

### Bài 33 — Rollback

Target đã nhận 20k writes sau cutover. Vì sao flip route về old là không an toàn? Đề xuất reverse migration.

### Bài 34 — SLO regression

Get Order p99 giảm nhưng list-by-tenant p99 tăng tám lần. Chọn SLO/cost gate theo workload mix.

### Bài 35 — Restore compatibility

Backup cũ chứa schema v1 nhưng application chỉ còn v2. Thiết kế restore/migration và lưu tooling tương thích.

### Bài 36 — Tổng hợp

Hãy lập runbook cho 100 triệu Orders: thiết kế virtual buckets, indexes, consistent snapshot, CDC, backfill, quality gates, fencing, canary, cutover và retirement.

### Bài 37 — Phát hiện chuỗi lỗi

Team đổi B=8 thành B=32, dual-write không idempotency, bỏ tombstones và dùng cursor cũ. Liệt kê ít nhất tám rủi ro cùng hướng sửa.

### Bài 38 — Booking

Hệ booking có whale tenant, một property hot và Order events quá lớn. Phần nào cần chia bucket, phần nào tách document và phần nào cần giữ invariant no double-booking riêng?

---

**Kết luận:** **Thay đổi shard key, cách chia bucket hoặc cấu trúc tài liệu** là quá trình chuyển cả **vị trí lưu, giao thức đọc/ghi và ranh giới nhất quán** của dữ liệu NoSQL. Hash/bucketing phải có contract ổn định; đổi số buckets không tự di chuyển records. Tách document làm thay đổi chi phí đọc lẫn transaction/outbox semantics. Khi vẫn có live writes, cần snapshot và change capture nối liền bằng watermark, backfill có checkpoint/idempotency, version guards và tombstones, so sánh dữ liệu tại cùng logical version, rồi **fence old owner trước khi chuyển routing epoch**. Sau cutover, rollback không còn là đổi flag khi target đã nhận writes mới. Chỉ retire dữ liệu cũ sau khi queries, tenants, caches, CDC, backups, permissions và business invariants đều được xác minh. Mục tiêu là phân phối và truy cập hiệu quả hơn **mà không mất, nhân đôi, đọc sai phạm vi hay làm hồi sinh dữ liệu nghiệp vụ**.

# Di chuyển khi hệ nguồn còn ghi và đồng bộ dữ liệu tăng thêm

Một nền tảng đặt hàng dùng MongoDB làm database chính, cần chuyển dữ liệu đơn hàng sang một cụm mới mà không dừng API trong nhiều giờ. Cơ sở dữ liệu có hàng trăm triệu documents, người dùng tiếp tục tạo, cập nhật và hủy đơn trong suốt thời gian chuyển. Nhóm vận hành bắt đầu copy từng document; sau sáu giờ, bộ copy báo hoàn tất. Nhưng một order đã được cập nhật trạng thái từ `CREATED` sang `PAID` trong lúc copy, một order khác bị xóa, và một collection mới được thêm index. Nếu nhóm chỉ so record count hoặc chuyển traffic ngay khi batch cuối chạy xong, dữ liệu đích có thể thiếu thay đổi, tồn tại bản ghi đã xóa hoặc trả kết quả sai.

Bài toán này là **di chuyển trực tuyến khi nguồn còn ghi** (*online/live migration*) với **đồng bộ dữ liệu tăng thêm** (*incremental synchronization*). Khó khăn không nằm chủ yếu ở việc copy file lớn: nó nằm ở việc xác định **một mốc nhất quán**, thu được **mọi thay đổi kể từ mốc đó**, áp dụng chúng **đúng thứ tự và không gây hiệu ứng lặp**, rồi chỉ chuyển hệ đích thành nguồn có thẩm quyền khi đã có bằng chứng phù hợp.

Bài học thuộc chương **Di chuyển và thay đổi**, module **Database No SQL**. Ta sẽ học cách thiết kế snapshot + Change Data Capture (CDC), backfill có checkpoint, bảo toàn xóa/TTL và phiên bản, xử lý event đến muộn, đối soát dữ liệu, shadow read, cutover, rollback, và những giới hạn riêng của MongoDB, DynamoDB, Cassandra, Redis, CouchDB cùng hệ search/index. Các tên lệnh và số liệu chỉ mang tính minh họa; với sản phẩm cụ thể luôn phải xác minh version, mode triển khai và bảo đảm nhất quán của API đang sử dụng.

> **Nguyên tắc:** Không thể kết luận dữ liệu đích đã bắt kịp chỉ vì snapshot/backfill hoàn tất. Phải chứng minh rằng **mọi thay đổi hợp lệ đến một hàng rào xác nhận (barrier/watermark) đã được áp dụng và kiểm chứng**, sau đó kiểm soát rõ nơi duy nhất được phép nhận các writes tiếp theo.

## 1. “Nguồn còn ghi” làm thay đổi bản chất việc di chuyển

Di chuyển offline:

~~~text
Stop writes -> Take snapshot -> Copy -> Verify -> Switch -> Resume writes.
~~~

Di chuyển online:

~~~text
Source vẫn nhận writes.
  |                |
  +-> Snapshot ----+----> Target backfill.
  |
  +-> CDC/log ----------> Target incremental apply.
                                      |
                                      v
                              Reconciliation.
                                      |
                                      v
                         Controlled source cutover.
~~~

Trong mô hình online, người dùng có thể cùng lúc:
- Tạo bản ghi mới sau khi job copy đã quét qua vị trí tương ứng.
- Cập nhật bản ghi đang được backfill.
- Xóa bản ghi trước hoặc sau khi nó được copy.
- Thay đổi nhiều records trong một giao dịch.
- Thay đổi TTL/index/schema.
- Retry một write sau timeout mà chưa biết commit thành công chưa.

**Nguồn dữ liệu tiếp tục biến đổi, nên không tồn tại một “bản copy hoàn tất” chỉ dựa vào lượt quét đầu tiên.**

## 2. Hai mục tiêu thường mâu thuẫn: liên tục phục vụ và nhất quán

Người vận hành muốn:
- Hạn chế thời gian ngừng ghi.
- Không mất acknowledged writes.
- Không tạo duplicate business operations.
- Giữ độ trễ API trong SLO.
- Di chuyển nhanh để giảm chi phí vận hành song song.
- Có phương án rollback.

Nhưng:
- Quét nhanh tạo I/O, cache pollution và compaction.
- CDC phát sinh liên tục trong khi backfill chạy.
- Một snapshot không nhất quán có thể copy dữ liệu từ nhiều thời điểm.
- Kiểm toàn bộ dữ liệu tốn thời gian.
- Sau khi đích nhận writes, rollback về nguồn không còn là thao tác đổi DNS đơn giản.

Cần định nghĩa **tiêu chí hoàn tất theo đúng nghiệp vụ**, thay vì cố gọi mọi kế hoạch là “zero downtime, zero data loss” khi không có cơ chế chứng minh.

## 3. Phân biệt các kiểu di chuyển

| Cách | Nguồn nhận writes trong lúc copy? | Đồng bộ phần phát sinh | Điểm khó |
|---|---|---|---|
| Offline snapshot | Không | Không cần nếu nguồn thực sự đóng băng | Downtime |
| Snapshot + CDC | Có | Change stream / log | Fence, ordering, delete, replay |
| Backfill + application outbox | Có | Domain events/outbox | Coverage của mọi write path |
| Temporary dual-write | Có | Application ghi hai nơi | Partial failure, conflict, order |
| Source replication / managed migration | Có theo capability | Cơ chế của engine/service | Compatibility, cutover semantics |
| Rebuild derived index | Có | Snapshot + stream replay | Lag, mapping và index cutover |

**Dual-write không tự động mạnh hơn CDC**. Nó tạo ra hai kết quả commit riêng biệt và nhiều tình huống một bên thành công, bên kia thất bại. Nếu engine cung cấp streaming/replication phù hợp, snapshot + CDC thường giảm số đường ghi cần thay đổi.

## 4. Một nguyên tắc chỉ định nguồn có thẩm quyền

Trong phần lớn kế hoạch an toàn, ban đầu:

~~~text
Source S: authoritative cho mọi business writes.
Target T: replica/migration destination, chưa nhận writes nghiệp vụ.
~~~

Ứng dụng có thể shadow-read T để kiểm chứng nhưng không dùng T làm nguồn commit nghiệp vụ. Khi cutover thành công:

~~~text
Target T: authoritative cho writes mới.
Source S: read-only/frozen hoặc theo rollback protocol đã định.
~~~

Nếu cả S và T cùng nhận writes độc lập không có giao thức xử lý conflict/transaction, chúng có thể phân kỳ. **Một request được ACK ở T không tự có mặt ở S** nếu chỉ chạy CDC S → T.

## 5. Bản đồ hệ thống cần lập trước khi copy

Một inventory nên gồm:
- Dataset, collections/tables/keyspaces/indexes.
- Số bản ghi, kích thước, phân bố khóa nóng.
- Read/write/update/delete/TTL rates.
- Partition/shard key, replication, consistency và durability.
- Client SDK/driver và ứng dụng trực tiếp truy cập nguồn.
- Các cron/batch/import/ETL jobs có ghi trực tiếp.
- Backup/PITR và log/CDC retention.
- Những workflow dùng multi-document/partition transactions.
- Triggers, secondary indexes, materialized views, search indexes.
- Cache invalidation, CDC sinks, outbox consumers.
- Security/IAM, TLS, encryption, data residency.
- Mục tiêu RPO/RTO và SLO trong cửa sổ chuyển đổi.

Một nguồn “không còn writers” phải được chứng minh ở **tất cả write paths**, không chỉ web API chính.

## 6. Điều kiện GO/NO-GO trước migration

Một số câu hỏi trọng yếu:
1. Source backup có được khôi phục thử chưa?
2. CDC có bắt đầu được tại vị trí đủ sớm và không mất events không?
3. Log retention còn đủ trong thời gian backfill cộng sự cố dự phòng không?
4. Target có đúng schema/index/unique/TTL/authorization settings không?
5. Phiên bản ứng dụng có tương thích cả S và T không?
6. Network, disk, IOPS, partition capacity và write amplification có đủ?
7. Có kế hoạch đối soát và xử lý differences không?
8. Có thể cô lập target khỏi business writes cho tới cutover không?
9. Có người quyết định STOP, rollback/rollforward và incident response?
10. Có đo được lag, queue, failure count và last successfully applied cursor không?

**Không GO chỉ vì thử chuyển 1.000 records thành công** nếu chưa kiểm các trường hợp ghi đồng thời, xóa, lỗi mạng và tail latency.

## 7. Nhất quán của snapshot là điểm xuất phát

Nếu source hỗ trợ snapshot nhất quán với mốc \(T_0\):

~~~text
T0: Source state có một cách nhìn nhất quán.
Snapshot: phản ánh state ở T0 trong phạm vi được bảo đảm.
CDC: cung cấp thay đổi đã commit sau T0.
~~~

Khi target áp dụng snapshot rồi đầy đủ events sau T0 theo đúng semantics, target có thể tiến tới state nguồn tại một mốc mới.

Nhưng “snapshot cùng timestamp” có thể không có nghĩa một global transaction boundary trên nhiều shards/datacenters. Phải kiểm **engine có hỗ trợ consistent snapshot ở phạm vi nào**: một partition, một collection, một database, hay cả cụm.

## 8. CDC: Change Data Capture thực sự là gì?

CDC là cơ chế theo dõi các thay đổi ở nguồn sau một mốc:
- INSERT/CREATE.
- UPDATE/PATCH.
- REPLACE.
- DELETE.
- Một số sự kiện DDL/schema/transaction tùy sản phẩm.
- Một số loại TTL expiration hoặc background deletion tùy sản phẩm.

Nguồn có thể là:
- Database change stream/oplog.
- Transaction/commit log.
- DynamoDB Streams.
- Logical decoding/binlog tương đương.
- Application transactional outbox.
- Event log nghiệp vụ đủ coverage.

**Không phải mọi change feed đều durable, replayable hoặc ghi đầy đủ mọi dạng mutation.** Đặc biệt, cache invalidation/keyspace notifications thường không thể dùng thay CDC nguồn có thẩm quyền nếu không có bảo đảm giữ/replay.

## 9. Mốc bắt đầu CDC là vấn đề sống còn

Giả sử:

~~~text
10:00  Bắt đầu copy snapshot.
10:01  Order 7 cập nhật trạng thái.
10:30  Backfill tới order 7 với dữ liệu đọc ở 10:00.
11:00  Bắt đầu CDC từ 11:00.
~~~

Thay đổi ở 10:01 đã **lọt vào khoảng trống**. Không thể tự phát hiện chỉ từ record count.

Hai thiết kế khả thi tùy hệ:

**A. Snapshot gắn với vị trí log:**
- Database tạo consistent snapshot và cung cấp cursor/LSN/token tương ứng \(L_0\).
- Backfill state tại \(L_0\).
- Replay các changes sau \(L_0\).

**B. Capture trước, rồi backfill:**
- Bắt đầu stream tại \(L_0\) trước khi quét dữ liệu.
- Giữ/buffer/replay events trong suốt backfill.
- Dùng version/ordering hoặc một hàng rào nhất quán để xử lý chồng lấn.
- Không mất events khi stream backlog tăng.

**Mốc \(L_0\) phải có hợp đồng với snapshot**; việc ghi hai wall-clock timestamps gần nhau không tự chứng minh không có gap.

## 10. Sơ đồ migration có hàng rào thay đổi

~~~mermaid
flowchart LR
    W["Writers"] --> S["Authoritative Source S"]
    S -->|"Consistent state at L0"| SNAP["Snapshot / Backfill"]
    S -->|"Committed changes after L0"| CDC["CDC reader + checkpoint"]
    SNAP --> APPLY["Target apply pipeline"]
    CDC --> APPLY
    APPLY --> T["Target T, chưa nhận business writes"]
    T --> REC["Validation + reconciliation"]
    S --> BAR["Cutover barrier Lc"]
    BAR --> CHECK["All changes through Lc applied?"]
    REC --> CHECK
    CHECK -->|"Yes and safe"| CUT["Switch write ownership"]
    CHECK -->|"No"| WAIT["Remain on S / repair"]
~~~

`L0` và `Lc` là tên **hàng rào logic**, không nhất thiết là số nguyên hay timestamp. Ví dụ MongoDB change stream resume token là **opaque**; không được tự so sánh như bộ đếm tuyến tính nếu API không định nghĩa như vậy.

## 11. Backfill: copy trạng thái ban đầu theo lô

Một pipeline cơ bản:

~~~text
Enumerate stable source key ranges or snapshot partitions.
Read a bounded batch.
Transform schema.
Apply to target with safe write semantics.
Persist checkpoint only when batch is durable.
Repeat until all ranges complete.
~~~

Cần:
- Resume checkpoint theo range/partition.
- Không dùng offset pagination trên dữ liệu thay đổi nếu có thể làm bỏ sót/trùng.
- Ưu tiên stable key ranges, snapshot cursors hoặc engine-supported scan segmentation.
- Giới hạn batch bytes, concurrency và QPS.
- Cân bằng hotspots, không dồn vào một target partition.
- Tách metrics read/transform/write/verify.
- Ghi progress theo **bytes và keyspace coverage**, không chỉ số records.

Nếu chỉ copy vài triệu hot keys đầu tiên, kết quả chưa đại diện toàn dữ liệu dù throughput có vẻ cao.

## 12. Đọc từ nguồn khi vẫn có ghi: tránh quét từ trạng thái lẫn lộn

Một scan đọc documents từng thời điểm có thể thấy:
~~~text
Key A ở version 3.
Key B ở version 8.
Key C mới tạo sau khi đã quét range C.
~~~

Đó không phải một snapshot nhất quán theo thời điểm duy nhất.

Nếu engine không cho snapshot point-in-time trong phạm vi cần:
- Dùng stream capture khởi động đủ sớm.
- Mỗi document có monotonic source version/commit metadata nếu khả thi.
- Thiết kế backfill và CDC idempotent, so phiên bản an toàn.
- Có cơ chế quét bổ sung/anti-entropy reconciliation.
- Thực hiện write gate ngắn để xác nhận final state trước cutover.

Không tuyên bố phép quét `scan()` đang concurrent với writes tự là consistent snapshot.

## 13. Race nguy hiểm: snapshot ghi đè cập nhật mới

Timeline:

~~~text
T0: Backfill đọc product P version=10.
T1: Source cập nhật P -> version=11.
T2: CDC apply P version=11 vào target.
T3: Backfill insert/replace P version=10 vào target.
~~~

Nếu T3 dùng overwrite vô điều kiện, target **thụt lùi về version 10**.

Một cách phòng ngừa khi source cung cấp version có thứ tự đáng tin **trong phạm vi key**:

~~~text
apply(incoming):
  current = target.version(incoming.key)
  if incoming.version > current:
      target.conditionalWrite(incoming)
  else:
      ignore_as_stale_or_duplicate
~~~

Khi storage không hỗ trợ conditional write atomic, có thể **chờ backfill xong rồi mới replay CDC có thứ tự**, hoặc dùng một writer duy nhất theo key/partition. Không triển khai “compare version trong ứng dụng rồi write” một cách không atomic nếu có nhiều workers ghi cùng key.

## 14. Version số nguyên và CDC offset là hai khái niệm khác

Per-document version:
~~~json
{"_id":"p-7","price":2000,"version":11}
~~~

CDC cursor:
~~~text
opaque-source-resume-token
~~~

Version giúp xác định bản ghi nào mới hơn **trong phạm vi thực thể** nếu nguồn tăng atomic và không reset. Cursor giúp consumer **tiếp tục stream** từ một vị trí hợp lệ.

Không mặc định:
- Cursor là timestamp so sánh được.
- Version toàn cục giữa các shards.
- Một record có `updatedAt` mới hơn luôn là state mới hơn khi clock lệch.
- Một event tới sau luôn là mutation commit sau.

Chọn ordering primitive theo contract engine, tránh thay thế bằng wall-clock khi dữ liệu cần nghiêm ngặt.

## 15. Race nguy hiểm hơn: DELETE bị hồi sinh

~~~text
T0: Backfill đọc account A còn tồn tại, version=4.
T1: Source DELETE account A.
T2: CDC DELETE tới target, target xóa A.
T3: Backfill UPSERT A version=4.
~~~

Kết quả: dữ liệu đã xóa **sống lại** ở target.

Nếu apply CDC song song với backfill, cần lưu **tombstone có delete version hoặc một barrier** đủ lâu để từ chối write cũ:

~~~text
Target key A:
  state = DELETED
  sourceVersion = 5

Backfill UPSERT A version=4:
  reject vì 4 <= 5.
~~~

Nếu nguồn không phát version cho delete, có thể buộc backfill hoàn tất rồi mới replay toàn bộ CDC từ fence bảo đảm, trong thứ tự đúng, hoặc dùng cơ chế snapshot/cutover/reconciliation khác. **Tombstone xóa quá sớm có thể khiến backfill cũ làm hồi sinh record.**

## 16. DELETE, soft delete, TTL và physical purge khác nhau

| Hành vi | Ý nghĩa | Điều cần bảo đảm ở target |
|---|---|---|
| Hard DELETE | Record không còn theo semantics nguồn | Không bị backfill tạo lại |
| Soft delete | Record có `deleted=true`/status | Giữ trạng thái và query filters |
| TTL expiry | Record hết hạn theo thời điểm/policy | Không kéo dài lifetime vô ý |
| Physical purge/compaction | Bytes được dọn khỏi storage | Không đồng nhất với business delete |
| GDPR/privacy deletion workflow | Xóa/hạn chế theo policy | Không tái tạo từ backup/CDC sai |

Không phải engine nào cũng phát CDC event cho TTL cleanup giống customer-initiated DELETE. Phải kiểm **điều gì được CDC ghi nhận, điều gì cần quét/đối soát riêng**.

## 17. TTL: copy thời điểm hết hạn, không reset đồng hồ

Ví dụ:
~~~text
Source key được tạo 10:00, TTL 2 giờ.
Di chuyển lúc 11:30.
~~~

Nếu target đặt TTL = 2 giờ **tính từ lúc copy**, key sẽ sống đến 13:30 thay vì 12:00.

Một thiết kế phù hợp nếu business semantics cho phép:
- Lưu `expiresAt` tuyệt đối ở metadata.
- Tính remaining TTL tại thời điểm apply.
- Nếu đã hết hạn, không tạo mới.
- Cân nhắc clock drift và engine TTL semantics.
- Bảo toàn chính sách xóa hợp pháp.

Nếu dữ liệu nguồn không chứa expiry metadata đủ chính xác, cần protocol dự phòng, chứ không giả định source TTL luôn được nhìn thấy qua API.

## 18. At-least-once delivery là tình huống thường gặp

CDC relay có thể:
~~~text
Read event e1.
Apply e1 to target.
Crash before checkpoint.
Restart from previous cursor.
Apply e1 again.
~~~

Consumer cần **idempotent effects**. Một UPDATE có full state và version guard dễ replay hơn:
~~~text
SET status="PAID" IF sourceVersion < 12.
~~~

Một operation tăng số:
~~~text
INCREMENT counter by 1.
~~~

nếu replay hai lần sẽ thành +2. Với các changes không idempotent:
- Dùng stable `eventId` và inbox/dedup trong cùng atomic boundary với effect nếu có.
- Hoặc chuyển event thành state/absolute value với version guard.
- Hoặc dùng engine-supported transactional stream-to-sink protocol.
- Xây reconciliation để phát hiện lỗi thực.

Đừng khẳng định **delivery exactly-once** chỉ nhờ auto checkpoint của connector.

## 19. Checkpoint: chỉ lưu sau khi target đã nhận thay đổi

Sai:
~~~text
Read CDC e42.
Commit cursor=42.
Attempt target write, timeout.
Restart from 43 -> e42 mất.
~~~

Đúng về ý tưởng:
~~~text
Read e42.
Apply e42 durably to target (or stage durably).
Commit cursor after effect is safe.
~~~

Nhưng nếu target commit thành công rồi consumer crash trước checkpoint, e42 có thể bị đọc lại. Vì vậy cần idempotency.

Một thiết kế mạnh trong cùng transactional sink:
~~~text
transaction:
  check processedEventId not present
  apply mutation
  insert processedEventId
  update checkpoint (if supported with semantics)
commit
~~~

Khi target và checkpoint nằm ở hai hệ khác nhau, tính atomic có thể không có. Phải dùng dedup/version checks và recovery semantics được mô tả rõ, không giả định hai writes có thể cùng commit.

## 20. Idempotency key và event identity

Các ID cần phân biệt:
- `commandId`: một ý định nghiệp vụ.
- `eventId`: một thay đổi đã commit.
- `deliveryAttemptId`: mỗi lần relay gửi.
- `sourcePosition`: vị trí CDC.
- `snapshotPartition`: vùng backfill.
- `targetVersion`: phiên bản đã áp dụng.

Nếu một business command retry sau timeout, nó có thể tạo nhiều HTTP attempts nhưng chỉ được tạo một business effect theo idempotency contract.

Nếu một committed change event bị giao hai lần, consumer phải xem là **một fact với nhiều deliveries**, không tăng counter hai lần.

## 21. Thứ tự theo key khác thứ tự toàn cụm

Nhiều NoSQL cluster chỉ có ordering được bảo đảm ở một phạm vi:
- Một document/partition/aggregate.
- Một shard hoặc stream shard.
- Một transaction log.
- Một CDC partition.

Đừng tự áp dụng một global order cho nhiều shards.

Ví dụ:
~~~text
S1: order A -> PAID.
S2: inventory B -> RESERVED.
~~~

Không phải mọi backend phát hai events này theo một thứ tự toàn cục có ý nghĩa nghiệp vụ. Nếu workflow cần atomic multi-key invariant, phải dùng transaction boundary hoặc reconciliation riêng.

Một sink worker có thể partition theo stable aggregate ID để giữ ordering của **cùng một entity** khi source semantics và connector cho phép.

## 22. Multi-document transactions và atomicity

Một transaction source có thể:
~~~text
Decrease inventory.
Create order.
Record payment intent.
Commit.
~~~

Nếu CDC consumer apply từng mutation độc lập:
~~~text
Target thấy order nhưng inventory chưa đổi.
~~~

Nếu target được dùng để phục vụ requests trước khi đồng bộ đủ, một read có thể thấy trạng thái trung gian sai.

Chiến lược tùy engine và nhu cầu:
- Ghi nhóm changes theo source transaction metadata nếu có và apply atomic ở target nếu hỗ trợ.
- Chỉ đưa target ra phục vụ sau barrier toàn bộ transaction đã áp dụng.
- Thiết kế read models chịu eventual consistency và không dùng chúng cho hard invariants.
- Đối soát theo business operation/ledger.
- Dùng source làm nơi quyết định business constraints cho tới cutover.

**Per-key version guard không tự đảm bảo atomic multi-key transaction semantics.**

## 23. Schema transformation trong lúc live migration

Một kế hoạch có thể đổi dạng document:
~~~json
// Source
{"price": 1250.75, "currency": "VND"}

// Target
{"priceMinorUnits": 125075, "currency": "VND", "schemaVersion": 2}
~~~

Đây là ví dụ giả định; trong thực tế VND thường không dùng phần thập phân theo đơn vị nhỏ nhất, nên **quy tắc chuyển đơn vị tiền phải đến từ nghiệp vụ và chuẩn tiền tệ cụ thể**, không suy từ tên field.

Các yêu cầu:
- Transform deterministic.
- Xử lý null/missing/wrong types.
- Không mất precision của tiền/thời gian.
- Giữ source version và event ID.
- Có migration schema version.
- Có cách kiểm trước/sau với dữ liệu mẫu.
- Cả backfill và CDC dùng **cùng contract transform**.
- Định nghĩa lỗi không thể transform: quarantine/dead letter và policy cutover.

Không transform snapshot bằng logic v1 nhưng stream changes bằng logic v2 mà không có compatibility gate.

## 24. Event “patch” đôi khi không đủ tái tạo target schema

Nguồn:
~~~json
{"customer": {"email":"person@example.com","status":"ACTIVE"}}
~~~

CDC:
~~~text
SET customer.status = "PAUSED"
~~~

Target schema mới có thể gộp nhiều fields thành `customerSummary`. Một PATCH đơn lẻ có thể không đủ tái tạo document mới nếu thiếu context trước đó.

Có thể cần:
- Full document after-image khi nguồn hỗ trợ/được cấu hình.
- Event enrichment đọc nguồn có version guards.
- Recompute projection từ source state theo invariant.
- Outbox/domain event chứa đủ sự kiện nghiệp vụ.
- Idempotent reprocessing.

Đừng dùng “fetch latest record” không kiểm version rồi gắn nó cho một event cũ: kết quả có thể không còn tương ứng event đó.

## 25. Key/ID mapping phải ổn định

Chuyển từ key cũ sang key mới:
~~~text
sourceKey = "tenant-7/order-101"
targetKey = hash(tenant) + ":" + orderId
~~~

Yêu cầu:
- Mapping deterministic.
- Không collision.
- Không đổi theo thứ tự backfill.
- Đủ thông tin xử lý DELETE/UPDATE cũ.
- Ổn định qua retries và process restart.
- Ràng buộc tenant isolation.
- Cẩn thận nếu khóa mới tạo hotspot.

Nếu dùng random UUID mới cho mỗi event delivery, cùng source entity có thể thành nhiều target records. Có thể dùng immutable mapping table với uniqueness và retention phù hợp.

## 26. Đối với relationships và denormalization

Một nguồn có thể lưu:
~~~text
orders
orderItems
customers
~~~

Target có thể nhúng items và customer summary vào order document.

Trong lúc nguồn tiếp tục ghi:
- Items update trước/ sau order.
- Customer name thay đổi.
- Một event đến sau backfill.
- DELETE customer cần ảnh hưởng đến summary.
- Two collections có transaction ordering khác nhau.

Nên xác định **projection contract**, event ordering, rebuild strategy và consistency window. Nếu không có transaction toàn cục, hãy thiết kế eventual-convergence và kiểm business invariants trước cutover.

## 27. Tải backfill phải được điều tiết

Backfill có thể làm:
- Source disk scans tăng.
- Cache pages nóng bị thay thế.
- Read latency tăng.
- Replica lag lớn.
- Compaction/backpressure ở target.
- Network/egress cost tăng.
- CDC queue bị đói CPU.

Các giới hạn nên theo dõi:
- Source p95/p99, error rate.
- Source read IOPS và disk latency.
- Target write latency/throughput.
- Source replication/CDC lag.
- Target compaction/index backlog.
- Network utilization.
- Queue oldest age.
- CPU/memory của migrator.

Không đặt QPS backfill cố định rồi bỏ mặc; dùng rate/concurrency controls giảm tốc khi SLO hoặc lag xấu đi.

## 28. Tốc độ backlog quyết định khả năng bắt kịp

Gọi:
- \(\lambda\): tốc độ events mới từ source (events/s).
- \(\mu\): tốc độ apply CDC vào target (events/s).

Nếu \(\lambda>\mu\), backlog thường tăng. Nếu \(\mu>\lambda\), pipeline có thể bắt kịp, miễn còn năng lực đọc/replay và không mất log.

Ví dụ giả định:
~~~text
Source CDC: 8.000 events/s.
Target apply: 6.000 events/s.
Backlog tăng xấp xỉ 2.000 events/s.
~~~

Trong một giờ:
\[
B_{\text{added}}\approx2.000\times3.600=7.200.000\ \text{events}
\]

Đây là mô hình trung bình đơn giản. Size/shape events khác nhau, retries, batch effects và rate theo giờ khiến backlog thật biến động. Hãy đo cả **events, bytes và tuổi sự kiện cũ nhất chưa xử lý**.

## 29. Log retention cần bao phủ cả backfill và sự cố

Ví dụ:
~~~text
CDC history chỉ giữ 24 giờ.
Backfill dự kiến 20 giờ.
Nếu migrator dừng thêm 6 giờ -> cursor có thể quá cũ.
~~~

Một thiết kế chỉ “vừa đủ 24 giờ” có rủi ro rất cao.

Cần capacity model:
- Worst-case backfill duration.
- Change volume/bytes trong thời gian đó.
- Outage/retry buffer.
- Peak write rates.
- Log retention theo từng shard/partition.
- Consumer lag và oldest unread cursor.
- Rate CDC apply sau backfill.
- Khả năng tăng retention hoặc tạo durable staging.
- Kế hoạch resnapshot nếu cursor mất hiệu lực.

Nếu source đã xóa phần log mà consumer cần, **không tự tiếp tục từ latest và tuyên bố đồng bộ**. Phải resnapshot/reconcile theo protocol đã định.

## 30. Không đánh giá độ trễ chỉ bằng “consumer lag seconds”

Metric có thể hiển thị:
~~~text
consumer lag = 0s
~~~

nhưng:
- Source không phát event vì stream bị tắt.
- Một shard không còn được subscribe.
- Connector checkpoint nhầm.
- Target reject một số records.
- Events thiếu nhưng consumer không biết.

Cần thêm:
- Source event production/capture rates.
- Last durable source position.
- Per-shard checkpoint.
- Applied event count và failure count.
- Snapshot coverage.
- Checksums/anti-entropy result.
- Target sourceVersion watermark.
- End-to-end test mutations.

**Lag = 0 chỉ có nghĩa trong phạm vi pipeline và metrics đang hoạt động đúng.**

## 31. Kiểm tra snapshot coverage

Backfill nhiều partitions:
~~~text
Range A: complete.
Range B: complete.
Range C: pending.
Range D: failed at key K.
~~~

Một dashboard “99% bytes copied” không chứng minh các entities còn lại không quan trọng. Hãy lưu:
- Danh sách ranges/shards.
- Begin/end key của từng range.
- Snapshot watermark.
- Checkpoint key/page/cursor.
- Applied count và checksum buckets.
- Status, retry history, error types.
- Owner/attempt ID.

Chỉ xác nhận snapshot complete khi **mọi range nằm trong inventory đã được xử lý hoặc có exception được phê duyệt và đối soát**.

## 32. Validation phải so cùng một mốc logic

Sai:
~~~text
Count source lúc 12:00.
Count target lúc 12:10.
Source vẫn nhận writes.
Chênh lệch 100.000 records -> kết luận copy lỗi.
~~~

Có thể đơn giản vì data tiếp tục tăng.

Cần:
- Freeze/read barrier \(L_c\) hoặc consistent snapshot cùng mốc.
- Đảm bảo CDC đã apply qua barrier.
- So counts/checksums khi cả hai biểu diễn cùng state.
- Hoặc dùng version-based reconciliation mỗi key, loại các key đang thay đổi.
- Lặp nhiều windows để xác định eventual convergence.

**So hai hệ đang chuyển động tại hai thời điểm khác nhau không phải phép kiểm tương đương.**

## 33. So count thôi chưa đủ

Hai datasets có cùng 1 triệu documents nhưng:
- 10.000 documents mang status sai.
- Một số DELETE bị hồi sinh.
- Giá trị tiền bị làm tròn.
- Tenant ID bị map nhầm.
- TTL lệch.
- Unique/index semantics khác.
- Người dùng có quyền xem dữ liệu tenant khác.

Validation nên có nhiều mức:
1. Record count theo table/collection/partition.
2. Sampled per-key comparison.
3. Deterministic canonical hashes cho buckets.
4. Aggregate business invariants.
5. Referential/denormalized projection checks.
6. Deletes/tombstones/TTL behavior.
7. Index/query-plan/access control verification.
8. Differential API read tests trên state tương đương.

## 34. Canonical hóa dữ liệu trước khi hash đối soát

Không hash nguyên JSON bytes nếu:
- Thứ tự fields khác.
- `1` và `1.0` có semantics tương đương theo business.
- Timestamp timezone formatting khác.
- Array ordering có thể hoặc không thể mang ý nghĩa.
- Metadata như `_id`, migrationVersion khác.
- Target đổi schema có chủ đích.

Thiết kế:
~~~text
canonicalBusinessState(record):
  select relevant business fields
  normalize types/precision/timezones
  sort object keys
  preserve meaningful array order
  exclude approved derived metadata
  return stable serialization
~~~

Sau đó hash theo keys/buckets, kiểm các mismatch bằng cách có kiểm soát. Cẩn thận không log plaintext PII khi xuất diff report.

## 35. Reconciliation theo bucket

Với tập keys lớn:
~~~text
Bucket = hash(stableLogicalKey) mod N.
Count + hash of normalized records per bucket.
~~~

Nếu bucket khác:
- Drill down thành smaller ranges.
- So per-key versions.
- Phân loại missing, extra, stale, transform error.
- Tạo repair job idempotent.
- Recheck sau repair.

Hash theo bucket không tự chứng minh mọi record đúng nếu hash/canonicalization không được thiết kế phù hợp; tránh XOR/cộng hash đơn giản nếu có nguy cơ collisions không chấp nhận. Một digest có khóa hoặc cryptographic digest/canonical sorted records có thể hợp hơn theo threat model và chi phí.

## 36. Shadow read và differential testing

Sau khi target đủ dữ liệu:
~~~text
User request vẫn trả từ source S.
Một tỷ lệ requests được đọc thêm từ target T.
So normalized business response.
Ghi mismatch count, không trả dữ liệu T cho user.
~~~

Lợi ích:
- Kiểm query compatibility.
- Phát hiện missing indexes.
- Đo latency target.
- Tìm lỗi serialization/projection.

Nhược điểm:
- Tăng read load.
- Trạng thái thay đổi giữa hai reads có thể tạo mismatch giả.
- Shadow requests không được gây side effects.
- Phải bảo vệ PII/tenant scope và credentials.

Nên so theo **version/watermark**, hoặc chỉ so entities có đủ ổn định, tránh gán mọi khác biệt tạm thời là lỗi migration.

## 37. Canary read khác canary write

**Canary read:** Một tỷ lệ người dùng đọc target, writes vẫn tới source. Nếu target lag, nghiệp vụ có thể thấy dữ liệu cũ; chỉ làm nếu contract cho phép và có khả năng fallback.

**Canary write:** Một nhóm ghi target làm source-of-truth cho nhóm đó. Phức tạp hơn vì:
- Hai nơi có thể trở thành authoritative cho những keys khác nhau.
- Cross-group transactions/conflicts khó xử lý.
- Có thể phải reverse-sync target → source nếu rollback.
- Cần route requests nhất quán theo tenant/partition.

Không coi canary write là bước vô hại như shadow read.

## 38. Dual-write: failure matrix

Một service viết S và T:
| S | T | Hậu quả |
|---|---|---|
| Success | Success | Hai nơi đồng bộ ở operation đó |
| Success | Fail | Source có thay đổi, target thiếu |
| Fail | Success | Target có thay đổi mà source từ chối |
| Timeout/unknown | Success | Không chắc source đã commit |
| Success | Timeout/unknown | Không chắc target đã commit |

Nếu source vẫn authoritative:
- Ack business command dựa trên source contract.
- Target write là async replication/repair obligation.
- Có durable outbox cho changes.
- Không để target success riêng khiến workflow tiến lên khi source fail.

Nếu yêu cầu cả hai commit atomic, hai database độc lập **không tự trở thành một transaction** nhờ `Promise.all` hoặc hai awaits.

## 39. Đơn giản hóa dual-write bằng transactional outbox

Một transaction source có thể:
~~~text
UPDATE order in S
INSERT outbox event with stable eventId and version
COMMIT atomically
~~~

Relay đọc outbox và gửi tới target:
~~~text
Outbox event -> transform -> idempotent target write -> ack.
~~~

Ưu điểm:
- Event không bị mất do app crash sau commit nếu outbox nằm trong cùng atomic boundary.
- Có stable event ID.
- Có retries và backlog tracking.

Giới hạn:
- Phải bảo đảm **tất cả write paths** đi qua outbox.
- Transaction boundary có thể chỉ trong một document/partition hoặc không được hỗ trợ qua nhiều records tùy engine.
- Events cần đủ thông tin reconstruct state.
- Relay/consumer vẫn at-least-once.
- Retention và cleanup outbox cần phối hợp.

## 40. Ai ghi trực tiếp ngoài ứng dụng?

Có thể còn:
- Data repair scripts.
- DBA manual updates.
- ETL/batch jobs.
- Scheduled TTL cleanup.
- Imports.
- Background migrations.
- Third-party connectors.
- Other microservices.
- Admin console.
- Triggers/stored procedures nếu engine hỗ trợ.

Nếu dùng application outbox nhưng một script ghi trực tiếp database, target không thấy thay đổi đó.

Trước cutover phải:
1. Inventory mọi write principals.
2. Chặn/đổi đường bypass không được phép.
3. Dùng CDC ở storage layer nếu cần coverage rộng hơn.
4. Audit direct writes và reconciliation.
5. Có policy phát hiện source writes sau write-freeze.

**Một ứng dụng cập nhật đúng không bảo đảm toàn bộ nguồn đã ngừng biến đổi**.

## 41. Quy trình cutover có hàng rào cuối

Mô hình với source S còn authoritative trước cutover:

~~~text
1. Preflight: target health, indexes, schema, access, lag, backup.
2. Chặn/điều phối writes mới vào S ở một điểm chung.
3. Đợi in-flight commands được xử lý/định danh outcome.
4. Ghi nhận final source barrier Lc.
5. CDC apply đầy đủ qua Lc, gồm deletes và transactions.
6. Reconcile data/business invariants tới Lc.
7. Chuyển routing/ownership writes sang T.
8. Mở writes, canary rồi tăng traffic.
9. Theo dõi correctness, p99, errors, lag và source-write violations.
~~~

Đây là protocol khái niệm. Một số hệ hỗ trợ atomic routing/leadership transfer hoặc zero-write-pause gần như hoàn toàn; nơi khác cần **write gate ngắn**. Đừng tuyên bố “không downtime” khi vẫn cần chặn writes, trừ khi product contract định nghĩa và đo rõ khoảng dừng đó.

## 42. Cutover barrier không chỉ là “lag gần 0”

Một final check:
- All backfill ranges complete.
- All CDC partitions/shards have applied watermark through Lc.
- No unresolved error/dead-letter events.
- Every in-flight source write before gate có outcome được xác minh.
- No unauthorized direct writer bypassed gate.
- Target indexes/validators/TTL/security match.
- Counts/checksums/business reconciliation đạt.
- Target service healthy và đủ capacity.
- Drivers/clients/retry/idempotency tested.
- Rollback/rollforward decision prepared.

**Một stream shard bắt kịp không có nghĩa mọi shards khác đã bắt kịp.** Barrier phải được định nghĩa ở đúng phạm vi cần thiết cho cutover.

## 43. Không tự dựa vào DNS TTL để đổi write owner

Ứng dụng có thể:
- Giữ kết nối database cũ trong pool.
- Cache DNS hoặc service discovery.
- Có batch/worker deploy chậm.
- Retry request tới endpoint cũ.
- Có direct connection bypass proxy.

Cần cơ chế routing và fencing:
- Chặn writes ở S sau cutover.
- Dùng routing/epoch version.
- Xác định stale clients và timeout.
- Kiểm write attempts vào old source.
- Cập nhật secrets/permissions/endpoints.
- Cho phép draining in-flight requests có kiểm soát.

Nếu old source vẫn chấp nhận writes, chỉ đổi DNS không đảm bảo không còn diverging writes.

## 44. Fencing token và epoch

Một pattern khái niệm:
~~~text
currentWriteEpoch = 8
Source S accepts writes only epoch <= 8 before cutover.
At cutover:
  routing authority advances to epoch 9.
  Source S rejects new business writes.
  Target T accepts epoch 9 writes.
~~~

Giả định cần cơ chế thực thi fencing đáng tin ở gateway/application/database layer, không chỉ một biến trong một instance Java. Nếu clients có thể bỏ qua gate hoặc epoch không kiểm tra atomic, hai nguồn vẫn có thể cùng nhận writes.

**Epoch không tự thay được distributed coordination**; nó chỉ là một công cụ trong protocol sở hữu quyền ghi.

## 45. Cutover của read path

Sau khi writes chuyển sang T, reads có thể chuyển:
- Đồng thời tại barrier nếu T đủ consistency.
- Từng nhóm clients nếu có routing ổn định.
- Với shadow fallback trong thời gian ngắn nếu nghiệp vụ chấp nhận.

Không đọc S khi S đã bị freeze mà người dùng cần read-your-writes từ T; kết quả sẽ stale. Nếu dùng read fallback, phải định nghĩa:
- Khi nào fallback được phép.
- Source version nào đáng tin.
- Những operations nào không được fallback.
- Có thể lộ dữ liệu sau privacy DELETE không.
- Cache invalidation theo endpoint mới.

## 46. Giai đoạn “dual-run” sau cutover

Một kế hoạch có thể giữ S ở read-only thêm một khoảng để:
- So business metrics.
- Đối chiếu state tại cutover.
- Điều tra mismatches.
- Giữ khả năng forensic recovery.

Nhưng nếu T nhận writes mới:
- S sẽ stale nếu không reverse-sync.
- Không thể chỉ trỏ writes trở lại S khi cần rollback.
- Cần retention/data privacy policy cho S.
- Chi phí vận hành hai cụm vẫn tiếp diễn.

Phải xác định **trạng thái của S sau cutover**: archived, read-only, reverse-replicated hay planned retirement.

## 47. Rollback trước cutover thường đơn giản hơn sau cutover

**Trước cutover:**
- S còn authoritative.
- Có thể ngừng backfill/CDC.
- Không phải merge writes từ T về S nếu T không nhận business writes.

**Sau cutover:**
- T đã nhận writes.
- Trở lại S đòi đồng bộ ngược các mutations T → S hoặc một kế hoạch khôi phục/compensation.
- Schema mới có thể không đảo được.
- External effects đã phát sinh không tự rollback.

Vì vậy cần xác định **point of no return** và “rollback window”. Không gọi `switch connection string back` là kế hoạch rollback khi S đã mất các writes mới.

## 48. Reverse CDC có thật sự khả thi?

Reverse sync từ T về S cần:
- Target phát change events đủ coverage.
- Schema transform đảo được hoặc có business mapping.
- DELETE/TTL semantics phù hợp.
- Stable source/target identities.
- Idempotency và ordering.
- Handling transaction boundaries.
- Loop prevention nếu S ↔ T đồng bộ hai chiều.
- Conflict policy nếu S và T đã diverge.
- Logs và capacity đủ lâu.

Một transform từ nhiều fields sang summary có thể mất thông tin, **không đảo ngược được**. Khi đó rollback có thể cần write gate, manual reconciliation hoặc chuyển tiếp tới bản sửa ở T.

## 49. Change stream retention và rollback window liên quan nhau

Nếu sau cutover vẫn muốn rollback:
- Reverse CDC phải chạy và được kiểm.
- S phải có khả năng nhận/apply schema mới.
- Source retention cũ có thể không còn liên quan; target retention mới quan trọng.
- Mọi mutations sau switch cần được tái tạo.
- Có kiểm tra parity trước khi đảo routing.

Không giữ S read-only một tuần rồi nghĩ có thể trỏ trở lại mà không mất một tuần writes.

## 50. RPO và RTO khi live migration

**RPO** đo mức mất dữ liệu có thể chấp nhận tại thời điểm khôi phục/cutover; mục tiêu "không mất acknowledged writes" đòi protocol và validation phù hợp, không chỉ lag thấp.

**RTO** bao gồm thời gian dịch vụ trở lại contract sau failure/cutover, gồm app reconnect, cache warm-up và projection catch-up.

Trong migration cần đo thêm:
- Write-gate duration.
- Source-to-target CDC lag.
- Time to safe cutover.
- Post-cutover error/p99 spike.
- Time-to-SLO.
- Rollback execution time và data loss risk.

Một dashboard chỉ báo `copy 100%` không trả lời các mục tiêu này.

## 51. MongoDB: Change Streams và resume token

MongoDB cung cấp Change Streams trong các deployment/điều kiện được hỗ trợ, dựa trên cơ chế ghi thay đổi. Khi dùng làm nguồn incremental sync cần:
- Xác nhận replica set/sharded deployment hỗ trợ.
- Lưu **resume token opaque** một cách bền.
- Kiểm cursor/history còn tồn tại khi consumer dừng.
- Xử lý insert, update, replace, delete và các event hệ thống liên quan.
- Lựa chọn updateDescription hoặc full-document lookup phù hợp.
- Hiểu sự khác biệt giữa dữ liệu ngay sau event và dữ liệu **mới nhất khi lookup** nếu update liên tục.
- Xử lý collection rename/drop, invalidate, resnapshot theo semantics.
- Kiểm transaction ordering/cluster-level stream behavior theo version.
- Không log raw documents và PII vào telemetry.

Một `resumeToken` không nên được sửa hoặc suy thành số. Nếu resume thất bại vì history bị dọn, cần recovery/rebaseline thay vì skip.

## 52. MongoDB: ví dụ khung consumer không giả định exactly-once

Pseudocode Java-like:

~~~java
while (running) {
    ChangeEvent e = stream.next(); // từ resume token bền
    MigrationMutation m = transform(e);

    // Target apply phải idempotent hoặc conditional theo version.
    applyDurablyWithDedupOrVersionGuard(m);

    // Cursor chỉ được checkpoint sau khi effect đã an toàn.
    saveCheckpointSafely(e.resumeToken());

    metrics.recordApplied(e.operationType());
}
~~~

Đây chỉ là khung tư duy, không phải Java SDK code dùng trực tiếp. Nếu `applyDurably...` và `saveCheckpoint...` không atomic, retry sẽ phát lại event sau crash; logic apply phải chịu được duplicate. Với DELETE cần tombstone/ordering. Với fullDocument lookup phải kiểm semantics về phiên bản; không tự suy `latest` tương đương after-image ở commit event.

## 53. MongoDB: đọc snapshot nhất quán và sharding

Khi copy collections hoặc shards:
- Dùng cơ chế consistent snapshot/backup tool được engine hỗ trợ theo version.
- Ghi resume point tương ứng (nếu API cung cấp cách thiết lập hợp lệ).
- Không suy rằng một scan từng shard có cùng cluster-wide snapshot.
- Kiểm changes trong lúc shard chunk movement và resharding.
- Xác định indexes, validators, shard keys và collation ở target.
- Kiểm write concern/read concern và read preference khi quét.
- Với transactions, xác nhận consumer không tạo partial business state cho read path.

Thao tác migration có thể sử dụng managed database migration tool, nhưng vẫn phải xác minh **coverage và cutover contract cụ thể**, không chỉ nhãn “online”.

## 54. DynamoDB: Streams và thời hạn dữ liệu

DynamoDB Streams có thể phát thông tin thay đổi item theo StreamViewType, với retention và ordering semantics của dịch vụ. Cần lưu ý:
- Có thể cần enable stream đúng thời điểm trước backfill.
- Lựa chọn keys-only/new/old image tùy transform và deletion handling.
- Checkpoint theo stream shard/sequence semantics.
- Dùng stable item key và idempotent apply.
- Streams có retention hữu hạn (thường ngắn hơn các đợt copy dữ liệu lớn); phải xác minh giới hạn hiện hành và planned outage budget.
- TTL-driven deletions có metadata đặc thù theo API/region/version; không mặc định mọi TTL expiry được đánh dấu giống user delete.
- Global Tables và replication có thể tạo nguồn changes từ nhiều regions, phải hiểu origin/conflict contract.
- Không coi scan đồng thời writes là một snapshot toàn bảng nhất quán nếu API không bảo đảm.

Nếu stream cursor hết hạn trước khi backfill hoàn tất, phải dùng cách capture/staging/snapshot khác hoặc resync.

## 55. DynamoDB: conditional update làm idempotent apply

Một target item có thể lưu:
~~~json
{
  "pk": "ORDER#101",
  "status": "PAID",
  "sourceVersion": 12
}
~~~

Ý tưởng:
~~~text
SET fields from event version 12
ONLY IF sourceVersion is absent OR sourceVersion < 12
~~~

DynamoDB có conditional expressions và transactional APIs nhưng cần kiểm capacity, conflicts và key/attribute type semantics. Nếu source không có version đơn điệu trên item, không được tự lấy stream sequence từ shard A để so với event của shard B hoặc snapshot record rồi suy total order.

DELETE cần giải quyết tombstone hoặc sequencing, tránh old snapshot upsert làm tái tạo item.

## 56. Cassandra: CDC và logical data model

Cassandra có các cơ chế CDC/commit-log-based capture tùy version, config và tooling, nhưng không giống MongoDB Change Streams hay DynamoDB Streams về API và operational contract.

Khi chuyển keyspace/table:
- Bảo vệ replication strategy, token/partition layout và table schema.
- Xác định cách thu writes từ tất cả nodes/replicas để không đếm trùng hoặc bỏ thiếu.
- Xử lý tombstones, TTL và timestamp semantics.
- Hiểu nhiều rows/tables denormalized cho cùng business operation.
- Theo dõi CDC segment/commit-log retention, disk headroom và connector failures.
- Không tự coi `nodetool snapshot` là stream toàn bộ updates sau đó.
- Tránh quét full table quá tải, dùng token ranges và rate limits.
- Đối soát theo partition/row business state.

**Cassandra không có một leader toàn cluster phát global ordered CDC events** theo kiểu một source log duy nhất.

## 57. Cassandra: timestamp và last-write-wins không phải giải pháp chung

Một số storage conflicts có thể được giải quyết theo timestamp logic của engine; nhưng:
- Clock skew có thể làm write cũ thắng.
- Tombstone timestamp phải được hiểu đúng.
- Một business version không tự trùng storage timestamp.
- Cross-partition ordering không được bảo đảm.
- Client-supplied timestamps có thể gây bất ngờ.

Nếu migration dùng target “last write wins” theo wall-clock thời điểm nhận event, event tới muộn có thể thắng sai.

Nên thiết kế source-authoritative version/ordering ở phạm vi cần và giữ **tombstone semantics**; không tự trộn ngôn ngữ “LWW” của engine với version nghiệp vụ.

## 58. Redis: keyspace notifications không phải durable CDC

Với Redis, một số cơ chế quan sát thay đổi keys/commands không bảo đảm lưu và replay giống database transaction log.

Do đó:
- Không coi keyspace notifications hoặc MONITOR là durable incremental synchronization cho dữ liệu authoritative.
- Phân biệt Redis chỉ là cache (có thể rebuild) với Redis giữ state nghiệp vụ cần migrate chính xác.
- Với Redis Cluster, kiểm hash slots, multi-key commands, failover và client redirects.
- Xem TTL absolute expiry, eviction và memory pressure.
- Dùng engine-supported replication, persistence hoặc application outbox/protocol có coverage khi cần.
- Kiểm ACL/TLS, key naming/serialization, modules/script dependencies.
- Đo cache miss surge nếu chọn rebuild thay copy.

Một `SCAN` trả về keys theo các lần quét nhưng không tự là consistent snapshot; concurrent writes có thể khiến kết quả thay đổi.

## 59. CouchDB: `_changes` feed và revisions

CouchDB có `_changes` feed hỗ trợ tracking changes theo semantics của database, cùng replication/checkpoints và revision conflicts.

Cần quan tâm:
- Chọn starting sequence phù hợp.
- Durable checkpoint và replay.
- Conflicting revisions và winning revision policy.
- Deletes/tombstones và purge semantics.
- Design documents/views.
- Scope replication/filters theo quyền.
- Không coi một sequence token là business global timestamp hoặc sourceVersion có thể so trên mọi databases.
- Đối soát conflict state, không chỉ document count.

Một feed đầy đủ changes không tự giải quyết application-level identity mapping hoặc business conflict policy.

## 60. Search và derived read models: rebuild có thể là lựa chọn tốt

Nếu target chỉ là search index hoặc cache:
~~~text
Authoritative NoSQL S -> snapshot -> search index T
                        -> CDC after snapshot -> T
~~~

Target có thể eventual consistent, nhưng:
- Mapping/analyzer version phải đúng.
- Xóa/TTL cần được phản ánh.
- Index build/replay có thể dài hơn RTO.
- Alias cutover phải bảo đảm query không trỏ nửa chừng.
- Không ghi business mutations vào search index.
- Validation phải so normalized business output, không dựa trên internal index documents.

Không gộp “search projection sẵn sàng” với “transactional source đã thay thế” nếu chúng có hợp đồng nhất quán khác nhau.

## 61. Bảo mật và quyền khi chuyển dữ liệu

Migration pipeline thường cần đọc nhiều dữ liệu nhạy và ghi target:
- Dùng service identity riêng, least privilege.
- Có IAM/network allowlist, TLS/encryption.
- Target tách tenant đúng policy.
- Không log raw PII trong reconciliation mismatches.
- Encrypt checkpoint/outbox/quarantine files.
- Có retention/cleanup cho staging/temporary copies.
- Giới hạn ai có quyền chạy backfill hoặc đổi routing.
- Audit cutover, config changes, source freeze và target grants.
- Rà soát data residency/region trước khi copy.
- Thu hồi quyền migration sau khi hoàn thành.

**Một lần di chuyển dữ liệu không phải lý do cấp admin vô hạn hoặc bỏ qua quy trình bảo vệ thông tin cá nhân.**

## 62. Target không được yếu về schema và security

Một target đã nhập đủ records vẫn có thể sai:
- Unique constraints thiếu.
- TTL cleanup khác.
- Index query quan trọng chưa build.
- Read/write consistency thấp hơn.
- Role user rộng hơn.
- Tenant isolation bị lỗi.
- Encryption/KMS/TLS chưa đúng.
- Backup policy chưa bật.
- CDC downstream consumers không được cập nhật.

Pre-cutover gate cần kiểm **schema, indexes, config, roles và backups**, không chỉ `rowCount` và `consumer lag`.

## 63. Manifest migration mẫu

~~~yaml
migration:
  id: "orders-live-migrate-2026-11"
  owner: "data-platform"
  source:
    engine: mongodb
    clusterAlias: orders-source
    authority: true
    snapshotReference: "snapshot-ref-opaque"
    captureFence: "L0-opaque-cursor"
  target:
    engine: mongodb
    clusterAlias: orders-target
    acceptsBusinessWrites: false
    schemaRevision: "schema-v8"
    indexRevision: "index-v12"
  workload:
    estimatedDocuments: 100000000
    writeEventsPerSecond: 8000
    maxAllowedSourceP99Ms: 200
  backfill:
    rangeManifest: "snapshot-ranges-v2"
    batchMaxBytes: 4000000
    parallelWorkers: 8
  incremental:
    transport: "change-stream"
    checkpointStore: "durable-migration-checkpoint"
    applyMode: "idempotent-version-guarded"
    deleteMode: "versioned-tombstone"
  gates:
    requireAllRangesComplete: true
    requireCDCThroughCutoverBarrier: true
    requireNoUnresolvedDeadLetters: true
    requireReconciliation: true
    requireApplicationAndSecurityChecks: true
  rollback:
    beforeCutover: "retain source authority"
    afterCutover: "requires reverse sync or documented recovery"
~~~

Đây là **schema thông tin**, không phải cấu hình thực thi của một sản phẩm. Không lưu raw credentials, full customer records hay encrypted key material có thể bị lạm dụng trong manifest.

## 64. Các phase và deliverables

| Phase | Nhiệm vụ | Bằng chứng để qua phase |
|---|---|---|
| 0. Plan | Inventory, RPO/RTO, risks, permissions | Signed migration plan |
| 1. Prepare | Target schema/index/ACL, backup/restore | Schema diff, recovery drill |
| 2. Capture | CDC/outbox từ mốc hợp lệ | Durable cursor, stream health |
| 3. Backfill | Quét nguồn theo ranges | Complete range checkpoints |
| 4. Catch-up | Apply incremental changes | Per-shard watermark, no gaps |
| 5. Validate | Counts, hashes, business invariants | Reconciliation report |
| 6. Shadow | API/query equivalence, performance | Mismatch classification, SLO |
| 7. Cutover | Gate writes, final barrier, route switch | Approved GO/NO-GO record |
| 8. Observe | Post-cutover errors, data, security | Stable SLO and consistency |
| 9. Retire | Cleanup old source, staging, access | Retention-approved disposal |

Không bỏ qua phase kiểm soát quyền, backup và rollback chỉ vì dữ liệu đã gần giống.

## 65. Dashboard trong migration

| Metric | Câu hỏi |
|---|---|
| `snapshot_ranges_completed` | Đã quét đầy đủ phạm vi? |
| `snapshot_bytes_copied` | Còn bao nhiêu dữ liệu? |
| `backfill_read_qps` | Source chịu tải bao nhiêu? |
| `target_apply_qps` | Target ghi thực tế bao nhiêu? |
| `cdc_events_captured` | Capture còn hoạt động? |
| `cdc_events_applied` | Effect đã bền ở target? |
| `cdc_oldest_unapplied_age` | Backlog già tới đâu? |
| `cdc_shard_checkpoint` | Những partitions nào còn chậm? |
| `cdc_out_of_order_count` | Có version đến không đúng thứ tự? |
| `duplicate_events_skipped` | Replay/dedup đúng? |
| `stale_upserts_rejected` | Có race snapshot/CDC? |
| `delete_tombstones_applied` | Xóa có coverage? |
| `dead_letter_count` | Có records không transform được? |
| `reconciliation_mismatch_count` | Chênh lệch business state? |
| `source_write_after_gate_count` | Có writers bỏ qua cutover? |
| `api_error_rate/p99` | Có vi phạm SLO? |
| `target_compaction_backlog` | Sink có chịu writes bền? |

Không gắn raw orderId/customerId thành metric label vì cardinality và dữ liệu nhạy. Per-key debugging dùng restricted logs/diff store với retention ngắn.

## 66. Phân loại sai khác trước khi sửa

Một mismatch có thể là:
- **Missing target:** source có, target không.
- **Extra target:** target có, source không; có thể delete resurrected.
- **Stale version:** target version thấp hơn.
- **Incorrect transform:** phiên bản ngang nhưng nội dung khác.
- **TTL difference:** khác vì expiry timing.
- **Out-of-window comparison:** đọc hai state khác mốc.
- **Index/read model mismatch:** underlying state đúng nhưng query khác.
- **Authorization mismatch:** data vẫn có, quyền khác.
- **Unknown/source corruption:** dữ liệu nguồn cũng có lỗi.
- **Approved exception:** field được chủ đích chuyển đổi schema.

Không viết “sửa target bằng latest source” hàng loạt nếu chưa xác định source có còn authoritative và mỗi key đang ở version nào.

## 67. Runbook: CDC lag ngày càng tăng

1. Xác nhận rate source changes \(\lambda\) và target apply \(\mu\).
2. Kiểm consumer/exporter queue, retries và errors.
3. Kiểm target CPU/disk/IOPS/compaction/backpressure.
4. Kiểm partition skew và worker saturation.
5. Giảm backfill load để nhường capacity CDC.
6. Tăng apply concurrency **chỉ khi giữ per-key ordering**.
7. Kiểm source log retention còn đủ.
8. Không skip error events để làm lag về 0.
9. Đánh giá scale target hoặc sửa transform bottleneck.
10. Nếu không thể bắt kịp trước log expiry, STOP/đổi chiến lược/resnapshot có kiểm soát.

## 68. Runbook: snapshot đã xong nhưng target sai dữ liệu

1. Chọn barrier/watermark phù hợp, không so trạng thái đang đổi tùy tiện.
2. Kiểm all ranges đã complete và checkpoint đúng.
3. Kiểm CDC từ \(L_0\) tới \(L_c\) không có gaps.
4. Phân loại missing/extra/stale/transform/TTL errors.
5. Kiểm tombstone và backfill race.
6. Kiểm event idempotency và checkpoint-after-apply.
7. Kiểm writer bypass/outbox coverage.
8. Kiểm schema/index/serialization.
9. Sửa với source versions và atomic conditional apply.
10. Reconcile lại trước cutover.

## 69. Runbook: CDC cursor hết hạn

1. **Dừng cutover** vì không còn chứng cứ stream đầy đủ.
2. Xác định shard/collection và mốc mất.
3. Xác nhận backup/log copies có khả năng phục hồi đoạn thiếu không.
4. Nếu có, replay có kiểm chứng từ nguồn durable phù hợp.
5. Nếu không, xây consistent new snapshot/capture fence.
6. Rescan affected ranges hoặc toàn dataset theo protocol.
7. Reconcile business state và deletes/TTL.
8. Đảm bảo retention/capacity cho đợt mới.
9. Ghi incident, nguyên nhân và thay đổi kế hoạch.
10. Không sửa checkpoint sang `latest` rồi coi đạt.

## 70. Runbook: phát hiện source vẫn nhận writes sau cutover

1. Chặn những writers chưa chuyển, không để hai sources tự diverge.
2. Đóng băng hoặc định tuyến lại theo quyền chính thức.
3. Bảo toàn source/target logs và audit records.
4. Tìm danh sách operations/versions trên S và T sau barrier.
5. Xác định outcome từng command và side effects.
6. Tạo reconciliation/merge plan có chủ sở hữu business.
7. Không dùng wall-clock LWW bừa bãi cho dữ liệu tài chính/tồn kho.
8. Thực hiện correction idempotent có audit.
9. Kiểm end-to-end invariants.
10. Cải thiện fencing, access controls và client rollout.

## 71. Runbook: target ghi thành công nhưng lỗi authorization

Một migration có thể thành công ở data layer nhưng ứng dụng đọc target bị `AccessDenied` hoặc đọc nhầm tenant.

Các bước:
- Kiểm principal thực, resource policy, DB roles, IAM và network.
- Kiểm mapping tenant trên target.
- Kiểm KMS key access, TLS/trust/secret rotation.
- So permission matrix source-target.
- Kiểm positive/negative authorization tests.
- Không cấp global admin chỉ để qua cutover.
- Thu hồi temporary migration credentials.
- Đưa lỗi phân quyền vào NO-GO nếu ảnh hưởng security contract.

## 72. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| Copy xong tức đồng bộ | Writes vẫn tiếp diễn | CDC + barrier |
| Bắt đầu CDC sau snapshot là đủ | Có khoảng trống giữa hai mốc | Coordinated fence |
| `updatedAt` đủ xác định thứ tự | Clock skew và simultaneous writes | Source version/order |
| Thấy lag=0 nghĩa không mất event | Connector có thể thiếu shard | Coverage và reconciliation |
| Snapshot overwrite luôn an toàn | Ghi đè version mới | Conditional apply hoặc tuần tự |
| Delete không cần tombstone | Backfill có thể làm sống lại | Versioned deletes/barrier |
| CDC events luôn exactly-once | Retry và crash tạo duplicate | Idempotent effects |
| Checkpoint trước write cho nhanh | Mất event khi sink fail | Checkpoint after durable apply |
| Retry INCREMENT vô hại | Counter bị nhân đôi | Event dedup/absolute state |
| Một stream có total order toàn cụm | Nhiều shards/partitions | Scope ordering đúng |
| Per-key ordering đủ cho multi-key tx | Lộ intermediate states | Transaction/reconciliation |
| Count bằng nhau nghĩa đúng | Field contents/TTL khác | Hash/invariants |
| So source/target bất kỳ lúc nào | Source vẫn thay đổi | Comparable watermark |
| Scan là consistent snapshot | Concurrent updates làm lệch | Engine snapshot/capture |
| TTL hai giờ từ lúc copy là đúng | Kéo dài lifetime | Absolute expiry semantics |
| Consumer offline bao lâu cũng được | Source log retention hữu hạn | Retention/headroom |
| Keyspace notifications là durable CDC | Có thể mất/replay không được | Reliable source capture |
| Dual-write là atomic | Hai commits độc lập | Outbox/failure matrix |
| Target success là command success | Source có thể fail | Single authority |
| DNS cutover đủ dừng old writes | Pool/clients stale | Fencing/write gate |
| Rollback sau cutover chỉ đổi URL | T đã có writes mới | Reverse sync/recovery |
| Shadow read có thể mutate | Tạo side effects | Read-only shadow |
| CDC sửa mọi sai khác schema | Transform có thể mất dữ liệu | Deterministic mapping/tests |
| Search rebuild đồng nghĩa DB migrate | Read model khác source | Separate contract |
| Không cần backup vì có CDC | Stream không thay snapshot | Backup + log chain |
| Retry không cần event ID | Duplicate logical effects | Stable IDs |
| Target index có thể xây sau switch | p99/uniqueness hỏng | Pre-cutover gates |
| Source đã đóng thì an toàn | Direct writer bypass | Inventory/fencing/audit |
| Chỉ cần monitoring kỹ thuật | Business invariants/tenant leaks | Functional/security validation |
| Tăng workers luôn tăng tốc | Hot partition/order bottleneck | Bounded parallelism |
| Zero downtime nghĩa không đổi gì | Có thể cần write gate nhỏ | Đo và công bố |
| Cùng số documents là recovery đủ | Permissions/CDC/projections còn thiếu | End-to-end postflight |

## 73. Bài tập thực hành

### Bài tập 1 — Online và offline

So sánh migration offline và snapshot + CDC khi nguồn có 100 triệu documents và write traffic liên tục. Nêu chi phí downtime, rủi ro và bằng chứng cần có.

### Bài tập 2 — Khoảng trống CDC

Snapshot bắt đầu 10:00, order đổi trạng thái 10:01, CDC bắt đầu 11:00. Vì sao thay đổi bị bỏ sót? Đề xuất hai cách phối hợp fence.

### Bài tập 3 — Consistent snapshot

Một scan MongoDB kéo dài ba giờ trong khi writes tiếp tục. Vì sao không tự coi nó là snapshot tại một thời điểm? Cần API/strategy nào?

### Bài tập 4 — Race update

Backfill đọc version 10, CDC apply version 11, backfill ghi version 10 sau đó. Thiết kế version-guarded apply hoặc thay đổi thứ tự pipeline để ngăn thụt lùi.

### Bài tập 5 — Delete resurrected

CDC delete key version 5, sau đó snapshot upsert version 4. Thiết kế tombstone và thời hạn giữ nó trong migration.

### Bài tập 6 — TTL

Key có TTL 2 giờ từ 10:00, được copy lúc 11:30. Nếu target đặt lại TTL 2 giờ, hành vi gì sai? Đề xuất `expiresAt` hoặc remaining TTL policy.

### Bài tập 7 — Event trùng

Consumer apply UPDATE rồi crash trước checkpoint. Làm sao retry không tạo business effect hai lần?

### Bài tập 8 — Counter

CDC event `INCREMENT stockViewCount by 1` được gửi hai lần. Vì sao không thể đơn giản apply hai lần? Thiết kế idempotent delta processing.

### Bài tập 9 — Checkpoint sai thứ tự

Một consumer commit offset trước khi target write và sau đó timeout. Xác định mất dữ liệu và thay checkpoint/effect protocol.

### Bài tập 10 — Multi-key transaction

Nguồn commit order+inventory atomically, target apply từng event. Khi nào có thể lộ trạng thái trung gian? Đề xuất mitigation.

### Bài tập 11 — Event ordering

Hai shards phát events về cùng service. Vì sao không thể tự suy total order bằng thời điểm đến collector? Xác định phạm vi order thật cần.

### Bài tập 12 — Schema transform

Chuyển document orders từ nested items sang denormalized summary. Thiết kế deterministic transform chung cho snapshot và CDC, xử lý partial update.

### Bài tập 13 — Key mapping

Source key là `tenant/order`, target key là UUID mới. Làm thế nào giữ mapping ổn định khi retries và DELETE?

### Bài tập 14 — Source QPS

Backfill làm source read p99 tăng từ 50 ms lên 600 ms. Thiết kế throttle theo SLO và metrics để tự giảm tải.

### Bài tập 15 — Backlog math

Source tạo 8.000 events/s, target apply 6.000/s. Tính backlog tăng sau một giờ và nêu giả định.

### Bài tập 16 — Log retention

Stream chỉ giữ một ngày, backfill cần 20 giờ, incident kéo dài 6 giờ. Xác định NO-GO và chiến lược bảo vệ log/đổi migration.

### Bài tập 17 — Validation cùng mốc

Source count lúc 12:00 và target count lúc 12:10 khác nhau khi nguồn vẫn ghi. Thiết kế watermark-based validation.

### Bài tập 18 — Checksum canonicalization

Source JSON field order khác target, decimal/timezone representations khác. Viết quy tắc canonicalization để so business state.

### Bài tập 19 — Reconciliation

Một bucket có missing 100 keys, extra 50 keys và 20 stale versions. Thiết kế repair có source-version guards và kiểm lại.

### Bài tập 20 — Shadow read

Làm sao so API source/target mà không bị mismatch giả khi data thay đổi giữa hai reads? Nêu privacy và side-effect constraints.

### Bài tập 21 — Dual-write failures

Vẽ ma trận outcomes khi S và T có success/fail/timeout. Chọn nơi authoritative và cách recover target thiếu changes.

### Bài tập 22 — Transactional outbox

Tạo pseudocode ghi business update và audit/outbox trong cùng atomic unit; mô tả relay idempotent và direct-writer gap.

### Bài tập 23 — Source writers inventory

Một ETL ghi trực tiếp Cassandra ngoài Java API. Vì sao application outbox không bắt được? Đề xuất bảo vệ coverage.

### Bài tập 24 — Final cutover barrier

Viết runbook ngắn: gate writes → drain in-flight → ghi nhận Lc → apply all changes → validate → route switch → reopen writes.

### Bài tập 25 — DNS và stale clients

Một batch job giữ connection pool tới S sau cutover. Làm sao phát hiện và chặn writes đi sai nơi?

### Bài tập 26 — Rollback sau cutover

Target đã nhận 100.000 writes trong hai giờ. Vì sao không thể chỉ đổi DNS về source? Thiết kế reverse-sync hoặc remediation.

### Bài tập 27 — MongoDB Change Streams

Giải thích resume token, updateDescription, full-document lookup và các giới hạn khi source changes nhanh. Vì sao lookup latest không tự là state ở event time?

### Bài tập 28 — DynamoDB Streams

Scan bảng lớn với writes liên tục và Streams retention hữu hạn. Thiết kế capture, checkpoint và safety margin; nêu vì sao TTL deletes cần kiểm semantics.

### Bài tập 29 — Cassandra CDC

Một keyspace có RF=3 và nhiều denormalized tables. Nêu cách tránh duplicate events từ replicas và bảo toàn tombstones/TTL.

### Bài tập 30 — Redis keyspace notifications

Tại sao Redis SCAN + keyspace notifications có thể không đủ để chứng minh migration chính xác cho một key-value store authoritative? Đề xuất hướng an toàn.

### Bài tập 31 — CouchDB `_changes`

Một source có conflict revisions và purge. Thiết kế strategy xử lý checkpoints, deletes/conflicts và so sánh target.

### Bài tập 32 — Target indexes và security

Record count đúng nhưng index unique thiếu và service account có quyền đọc chéo tenant. Vì sao phải NO-GO? Xây validation matrix.

### Bài tập 33 — Failure drill

Thử crash migrator sau target commit trước checkpoint, CDC cursor expiry, target disk full, source failover, direct writer bypass và TTL expiry. Hãy chỉ ra expected safety behavior cho mỗi lỗi.

### Bài tập 34 — Thiết kế migration tổng hợp

Một hệ có Java API, MongoDB orders, Cassandra events, Redis cache, DynamoDB preferences và search index. Hãy thiết kế:

1. Source-of-truth và phạm vi mỗi dataset.
2. Snapshot consistency và CDC start fence.
3. Backfill ranges, throttling và checkpoints.
4. Version/order/idempotency/tombstones/TTL.
5. Schema/index/key mapping.
6. At-least-once apply và log retention.
7. Reconciliation counts/checksums/business invariants.
8. Shadow/canary read, security, performance.
9. Final cutover barrier, routing/fencing.
10. Post-cutover monitoring, rollback/rollforward, retirement.

### Bài tập 35 — Phản biện kế hoạch sai

Một đội đề xuất:

~~~text
Chạy SELECT/SCAN toàn bộ khi source vẫn ghi.
Sau khi copy xong mới bật CDC.
CDC event nhận lần nào cũng apply INCREMENT trực tiếp.
DELETE chỉ xóa key, không có tombstone/version.
Nếu CDC lag về 0 thì chuyển ngay.
So count source 9:00 với target 10:00.
Chỉ thay DNS, không chặn old writes.
Sau cutover nếu có lỗi thì trỏ lại old source.
Không cần sao lưu vì vẫn có cả source và target.
~~~

Hãy chỉ ra từng lỗi, hậu quả và viết lại protocol có **snapshot/CDC fence, idempotent apply, delete safety, checkpoint, comparable validation, authoritative write ownership và rollback có thể chứng minh**.

---

**Kết luận:** Khi di chuyển dữ liệu NoSQL trong lúc hệ nguồn còn ghi, **snapshot/backfill chỉ tạo trạng thái khởi đầu; dữ liệu tăng thêm phải được capture và replay đầy đủ theo một mốc được định nghĩa chặt chẽ**. Hệ đích cần xử lý **duplicate delivery, race giữa backfill và CDC, out-of-order updates, DELETE/tombstone, TTL, schema transform và transaction boundaries**, không chỉ copy cho đủ số records. Trước cutover phải xác nhận **tất cả ranges đã hoàn tất, mọi CDC partitions đã tới hàng rào cuối, các sai khác đã được đối soát, indexes/quyền/cấu hình đúng và SLO đạt**. Source chỉ thôi có thẩm quyền khi **write gate/fencing và định tuyến đã ngăn đường ghi cũ**; sau đó rollback cần xét những writes mới ở target, không đơn giản đổi endpoint. Một kế hoạch tốt dùng **checkpoint bền, idempotency, security, giám sát lag/retention, failure drills và runbook GO/NO-GO** để giảm downtime mà vẫn bảo vệ tính đúng đắn của dữ liệu.

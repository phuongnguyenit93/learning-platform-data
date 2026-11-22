# Backfill dữ liệu và giới hạn tác động đến tải đang phục vụ

Trong **Database No SQL**, *backfill* là quá trình đọc dữ liệu lịch sử đang tồn tại và ghi bổ sung, chuyển đổi hoặc xây dựng lại dữ liệu ở nơi cần dùng. Nó xuất hiện khi thay schema, tạo read model mới, đổi partition key, chuyển từ một database sang database khác, tạo index/projection chuyên biệt, thêm trường được tính toán hoặc chuẩn bị cutover sang hệ mới.

Điểm khó là **production vẫn đang nhận đọc và ghi**. Một job quét 100 triệu documents không chỉ tốn thời gian. Nó cạnh tranh CPU, cache, disk I/O, throughput và network với các request đang phục vụ khách hàng. Trong lúc job chạy, dữ liệu nguồn tiếp tục thay đổi, thậm chí bị xóa, nên một bản ghi cũ đọc từ snapshot có thể **ghi đè một cập nhật mới** nếu không có cơ chế ordering.

Ví dụ:

~~~text
10:00:00 Backfill đọc Order O-100, status=PENDING, version=7.
10:00:01 API nhận thanh toán, cập nhật status=PAID, version=8.
10:00:02 CDC consumer cập nhật read model thành PAID/v8.
10:00:03 Backfill ghi lại snapshot PENDING/v7 vào read model.
~~~

Một backfill chỉ dùng thao tác ghi đè vô điều kiện đã làm read model **đi lùi**. Nếu ở thời điểm khác operator tăng concurrency từ 10 lên 500 workers để chạy nhanh hơn, nó có thể làm p99 checkout tăng, DynamoDB throttling hoặc MongoDB secondary lag tích tụ.

Bài thuộc chương **Di chuyển và thay đổi** trong **Database No SQL**, trình bày cả hai mục tiêu:

1. **Đúng dữ liệu:** không mất bản ghi, không hồi sinh dữ liệu đã xóa, không bỏ sót thay đổi khi có traffic mới, không duplicate side effects.
2. **Không phá tải đang phục vụ:** giới hạn bandwidth/IO/CPU/RCU/WCU/connections, kiểm soát queue, bảo vệ SLO và có khả năng dừng/tiếp tục an toàn.

Nội dung đi qua mô hình snapshot + CDC, version guard, idempotency, checkpoints, shadow reads, cutover/rollback, rate limiting và adaptive throttling; có các ví dụ Java, MongoDB, DynamoDB, Cassandra, Redis, cùng runbook và bài tập. Các con số minh họa là **giả định của bài toán**, không phải hiệu năng cố định hay cam kết API cho bất kỳ nhà cung cấp nào.

> **Backfill tốt không phải backfill chạy nhanh nhất; đó là backfill kết thúc với trạng thái đúng, có thể chứng minh coverage và không đẩy dịch vụ đang hoạt động ra ngoài SLO.**

---

## 1. Backfill khác migration và rebuild như thế nào?

| Khái niệm | Mục tiêu | Ví dụ |
|---|---|---|
| **Schema migration** | Đổi cấu trúc/hợp đồng dữ liệu | Thêm field `normalizedEmail` |
| **Backfill** | Điền dữ liệu lịch sử theo cấu trúc mới | Tính `normalizedEmail` cho 10 triệu users |
| **Data migration** | Chuyển dữ liệu giữa mô hình/cluster/engine | MongoDB → DynamoDB |
| **Projection rebuild** | Dựng lại read model từ source | Orders → Search |
| **Reindex** | Tạo lại cấu trúc index | Xây secondary index trên collection |
| **Reshard/repartition** | Đổi phân phối key/partition | `tenantId` → `tenantId#bucket` |
| **CDC catch-up** | Áp thay đổi xảy ra khi backfill chạy | Change Stream → target |
| **Cutover** | Chuyển read/write traffic sang target | API đọc projection v2 |

Một dự án migration có thể gồm nhiều loại cùng lúc. Backfill là **một giai đoạn của chuyển đổi**, không tự đồng nghĩa đã hoàn thành cutover.

## 2. Tại sao backfill phải chạy cùng traffic đang phục vụ?

Nhiều hệ không thể dừng ghi nhiều giờ để copy dữ liệu vì:

- API checkout/order vẫn nhận giao dịch.
- Users cập nhật profile liên tục.
- CDC consumers đang cập nhật projections.
- Scheduled jobs và TTL cleanup vẫn chạy.
- Source DB phải giữ SLO uptime.
- Backup, compaction, replication không ngừng.
- Dữ liệu mới phải xuất hiện trên hệ sau migration.

Có thể bảo trì/downtime được lên kế hoạch cho một số hệ, nhưng với zero/low downtime migration cần giải quyết **sự thay đổi đồng thời** chứ không chỉ sao chép snapshot.

## 3. Bốn câu hỏi đầu tiên của thiết kế

Trước khi viết một vòng lặp `scan -> save`, hãy xác định:

1. **Source of truth là đâu?** Collection/table/event log nào quyết định dữ liệu đúng?
2. **Đích dùng để làm gì?** Cache, analytics, search, read model hay nguồn ghi mới?
3. **Trong lúc backfill, ai đang thay đổi nguồn?** API, batch jobs, TTL, transaction, CDC?
4. **Đúng có nghĩa gì?** Bằng phiên bản hiện tại, bằng snapshot nhất quán tại mốc T, hay đủ dữ liệu tới commit watermark nào?

Không có định nghĩa thứ tư, việc kiểm “target count bằng source count” thường chưa chứng minh gì.

## 4. Luồng tổng quát

~~~mermaid
flowchart TD
  API["Production API traffic"] --> Source["Source NoSQL - source of truth"]
  Source --> Scan["Bounded historical scan"]
  Source --> CDC["CDC / Outbox / Change Stream"]
  Scan --> Transform["Deterministic transform + version"]
  CDC --> Apply["Version-aware idempotent applier"]
  Transform --> Apply
  Apply --> Target["Target model / database"]
  Target --> Verify["Reconcile coverage + correctness"]
  Verify --> Gate{"SLO and data gates pass?"}
  Gate -->|Yes| Cutover["Gradual read cutover"]
  Gate -->|No| Pause["Throttle / pause / repair"]
~~~

Một pipeline không nhất thiết có broker hoặc CDC nếu nguồn ghi đã dừng và snapshot thật sự bất biến. Nhưng khi nguồn tiếp tục ghi, cần **một phương thức bắt kịp thay đổi** có tính chất ordering và replay rõ ràng.

## 5. Những rủi ro chính

| Rủi ro | Hậu quả | Biện pháp trọng tâm |
|---|---|---|
| Full scan vượt I/O budget | API p99 tăng | Rate limit + adaptive throttle |
| Quét gây cache eviction | Read hit rate giảm | Small batches, scheduling, resource isolation |
| Thêm quá nhiều writes | Throttling/replica lag | Destination write quotas |
| Backfill ghi đè state mới | Lost update | Source version/CAS |
| Delete xảy ra trong scan | Zombie record xuất hiện | Tombstone/deletion version |
| Scan bị gián đoạn | Bỏ sót/ghi trùng | Durable checkpoint + idempotency |
| CDC retention hết | Gap không thể replay | Lag monitoring + rebuild strategy |
| Cutover quá sớm | Read stale/missing | Watermark/coverage validation |
| Two writers không có rule | Data divergence | Single authority/transaction protocol |
| Rollback thiếu đường quay | Outage kéo dài | Expand–migrate–contract + rollback rehearsal |

Cần đánh giá **đúng dữ liệu và tài nguyên** ngay từ đầu, không đợi target gần đủ rồi mới xem live consistency.

## 6. Snapshot tĩnh và snapshot nhất quán khác nhau

Một vòng scan có thể lấy dữ liệu ở những thời điểm khác nhau:

~~~text
Scan shard A at 10:00
Scan shard B at 10:20
Scan shard C at 10:40
```

Đó là một **fuzzy snapshot** nếu engine không cung cấp snapshot isolation thích hợp. Dữ liệu của ba shards có thể không cùng một logical point in time.

Một *consistent snapshot* có thể cung cấp view tại thời điểm/mốc xác định theo phạm vi hỗ trợ. Nhưng một snapshot dùng được cho migration thường cần:

- Point-in-time/log watermark được định nghĩa.
- CDC bắt đầu không có gap so với snapshot.
- Khả năng giữ/khôi phục log đủ lâu.
- Không làm source giữ snapshot quá lâu gây storage/transaction overhead.

Không giả định `find()` hoặc `Scan()` mặc định là snapshot của toàn database.

## 7. Tại sao chỉ copy một lần là không đủ?

Giả sử source chứa 10 triệu users; job chạy ba giờ. Trong ba giờ:

- Có users mới.
- Có users bị xóa.
- Có số điện thoại được sửa.
- Có tài khoản chuyển tenant.
- Có trạng thái bị rollback/correction.
- Có TTL expiration.
- Có các batch jobs khác cập nhật dữ liệu.

Ngay cả khi copy thành công toàn bộ records được nhìn thấy trong quá trình scan, target có thể **không tương đương trạng thái hiện tại của source**.

Phải có **change capture** hoặc **chuyển đổi write path** trong thời gian giao thoa.

## 8. Hai chiến lược chính

**Chiến lược A — Dừng writes rồi snapshot và import**

~~~text
Stop source writes
Take consistent backup/snapshot
Import target
Verify
Switch reads and writes
Resume traffic
```

Đơn giản hơn về concurrency nhưng downtime/risk cutover có thể lớn. Phù hợp hơn khi hệ có maintenance window và dữ liệu đủ nhỏ.

**Chiến lược B — Snapshot/backfill kết hợp CDC**

~~~text
Start reliable change capture at boundary
Backfill historical data
Apply historical + new changes with ordering rule
Catch up CDC to chosen watermark
Verify target
Gradual cutover
```

Phù hợp low downtime nhưng khó hơn nhiều: versioning, replay, deletes, idempotency, CDC retention và checkpoint.

## 9. Expand–migrate–contract

Một quy trình thường an toàn hơn:

1. **Expand:** thay schema/API để đọc hiểu cả old/new formats; chuẩn bị target và instrumentation.
2. **Establish change capture:** bảo đảm writes mới có thể tới target theo một contract.
3. **Migrate/backfill:** điền dữ liệu lịch sử, batch nhỏ, có checkpoints.
4. **Catch up and verify:** áp những thay đổi mới, đo coverage và correctness.
5. **Cut over:** chuyển một phần traffic đọc rồi tăng dần.
6. **Stabilize:** quan sát SLO và divergences.
7. **Contract:** sau rollback window mới loại bỏ old schema/paths.

Không drop old fields/collections ngay sau khi job báo 100% progress nếu target vẫn chưa đạt consistency watermark.

## 10. Nguồn dữ liệu phải được ghi rõ

Một câu như “copy `users` từ database cũ sang database mới” chưa đủ. Cần biết:

- Database/cluster/namespace.
- Collection/table và partition keys.
- Consistency/read concern.
- Version/schema generation.
- Quyền đọc và data classification.
- Retention/TTL.
- Những fields được phép chuyển.
- Quá trình xóa/anonymization.
- CDC source và change-log retention.
- Business state invariants.

Khi target là search/read model, **không copy cả PII hoặc secrets** nếu projection không cần.

## 11. Kết quả mong đợi phải định lượng

Ví dụ:

~~~yaml
migrationGoal:
  source: OrdersV1
  target: OrdersProjectionV2
  coverage: allEligibleOrders
  correctness:
    - noMissingEligibleRecords
    - noResurrectedDeletes
    - noStaleOverwriteOfNewerSourceVersion
    - noCrossTenantLeakage
  freshnessSlo:
    maxAppliedLagSeconds: 30
  productionGuardrails:
    checkoutP99Ms: belowDefinedSlo
    errorRate: belowDefinedSlo
    replicationLag: bounded
  cutover: stagedAndRollbackable
~~~

Đây là **ví dụ đặc tả**, không phải cấu hình chạy tự động.

## 12. Source key, target key và tính ổn định

Nếu source dùng `userId` nhưng target dùng `tenantId#userId`, việc chuyển tenant có thể khiến target key đổi.

Cần quyết định:

- Key có bất biến không?
- Rename/move được xem là delete old + insert new?
- Có unique constraint/collision không?
- Có mapping version không?
- Khi retry, transformer tạo cùng target key không?
- Có cleanup old key không?

Một transformer không deterministic có thể tạo hai records cho cùng source entity khi job retry.

## 13. Deterministic transformation

Một hàm transform nên có đặc tính:

~~~text
transform(sourceRecord, schemaVersion)
    -> same canonical target state
```

nếu inputs giống nhau.

Không nên để:

~~~text
targetId = randomUUID()
createdAt = Instant.now()
```

trong mỗi retry nếu những giá trị đó là identity/business fields của record. Thay vào đó:

- Giữ stable source identity.
- Sử dụng source business timestamps/versions.
- Gắn `migrationRunId` vào metadata, không thay state nghiệp vụ.
- Dùng chuẩn hóa string/number/timezone nhất quán.
- Version hóa transformer.

Nếu cần backfill một trường **ngày tạo mới**, hãy nêu đó là `migrationComputedAt`, không giả mạo `createdAt` lịch sử.

## 14. Một target envelope hữu ích

~~~json
{
  "pk": "TENANT#17#ORDER#100",
  "status": "PAID",
  "totalMinorUnits": 250000,
  "sourceVersion": 8,
  "sourceGeneration": 1,
  "schemaVersion": 2,
  "isDeleted": false,
  "lastAppliedEventId": "evt-1008",
  "migrationRunId": "run-2026-11"
}
~~~

Ở đây:

- `sourceVersion` phục vụ ordering theo **source entity**.
- `sourceGeneration` phân biệt lifetime/generation nếu ID được tái sử dụng.
- `schemaVersion` xác định representation.
- `lastAppliedEventId` phục vụ dedupe theo scope được thiết kế.
- `migrationRunId` chỉ là metadata quan sát.

Không coi `migrationRunId` mới hơn là lý do ghi đè một `sourceVersion` lớn hơn.

## 15. Backfill không được ghi đè event mới hơn

Phép apply minh họa:

~~~text
incoming = {
  key: O-100,
  state: PENDING,
  sourceVersion: 7
}

target = {
  key: O-100,
  state: PAID,
  sourceVersion: 8
}
```

Điều kiện:

\[
\text{apply only if }V_{\text{incoming}}>V_{\text{target}}
\]

Nếu incoming version 7, **skip**. Với version bằng nhau, cần xác định replay/idempotency hoặc conflict divergence; không tự ghi đè theo timestamp ingestion.

**Chỉ version số lớn hơn đủ khi nguồn bảo đảm version tăng đơn điệu và có ý nghĩa ordering cho key/generation đó.**

## 16. Version guard phải được kiểm atomically

Sai:

~~~text
current = target.get(key)
if current.version < incoming.version:
    target.put(key, incoming)   // Race
```

Hai workers có thể cùng đọc version 5, rồi v8 ghi trước, v7 ghi sau và thắng.

Đúng hơn:

~~~text
conditionalUpsert(
  key,
  if target missing OR target.version < incoming.version,
  newValue = incoming
)
```

Điều kiện và write phải là **atomic operation/transaction** theo scope mà NoSQL engine hỗ trợ. Tùy database, conditional upsert có các giới hạn khi document chưa tồn tại hoặc với composite keys.

## 17. Version bằng nhau nhưng payload khác

Hai events cùng `sourceVersion=8` nhưng dữ liệu khác:

~~~text
Event A: status=PAID, version=8
Event B: status=CANCELLED, version=8
```

Đây không nên được xử lý bằng “chọn event đến sau”. Có thể là:

- Source version generation bị reset.
- Event producer lỗi.
- Hai nguồn cùng dùng version mà không có single owner.
- Transformer/version format khác.
- Một trường đã bị tính không deterministic.

Nên **quarantine/conflict alert** và đối chiếu authoritative source. Version guard không sửa dữ liệu sai từ nguồn.

## 18. Deletes là một mutation có version

Một delete xảy ra giữa scan và CDC:

~~~text
10:00 Snapshot source: User U1 version=9, active.
10:01 Source deletes U1, event version=10.
10:02 CDC applies tombstone version=10.
10:03 Backfill writes snapshot U1 version=9.
```

Nếu target xóa hẳn U1 ở bước 10:02 và quên version 10, bước 10:03 có thể tạo lại U1. **Delete phải để lại tín hiệu về thứ tự** trong giai đoạn replay/backfill.

Một cách là tombstone:

~~~json
{
  "pk": "U1",
  "sourceVersion": 10,
  "isDeleted": true
}
~~~

Đảm bảo backfill v9 bị từ chối. Sau khi toàn pipeline qua mốc an toàn, mới xem xét garbage-collect tombstone theo retention protocol.

## 19. TTL deletion không luôn tương đương explicit delete

Các engines có semantics TTL khác nhau:

- Database TTL cleanup có thể bất đồng bộ.
- CDC có thể có cách biểu diễn delete đặc thù.
- Expiry có thể được quyết định theo thời gian đọc.
- Một snapshot có thể chứa item chưa bị xóa nhưng đã quá business expiry.

Backfill cần quyết định:

- Có migrate expired records không?
- TTL còn lại được giữ hay reset?
- Khi target TTL bắt đầu tính từ now, dữ liệu có bị sống thêm không?
- Nếu source tombstone không còn trong stream, làm sao biết delete?
- Cần expiry timestamp tuyệt đối hay duration?

**Không reset TTL của session từ 5 phút còn lại thành 30 ngày** chỉ vì item được import lại.

## 20. Giữ semantics của expiration

Ví dụ source:

~~~json
{
  "sessionId": "S1",
  "createdAt": "2026-11-14T08:00:00Z",
  "expiresAt": "2026-11-14T09:00:00Z"
}
~~~

Backfill lúc 08:45 nên giữ `expiresAt=09:00` nếu contract là fixed absolute expiry. Đừng chạy:

~~~text
target.ttl = 3600 seconds from backfill write
```

vì sẽ làm session sống tới 09:45.

Nếu target engine cần epoch seconds TTL, chuyển `expiresAt` sang đúng đơn vị, không lấy thời gian import làm mốc mặc định.

## 21. Backfill khi nguồn có nhiều writers

Nếu một document có thể được cập nhật bởi nhiều regions hoặc processes không có một `sourceVersion` tuyến tính, điều kiện `incoming.version > target.version` có thể không đủ.

Cần:

- Single authoritative writer/aggregate ownership; hoặc
- Causal/CRDT merge policy được định nghĩa; hoặc
- Consensus transaction version; hoặc
- Change-stream ordering theo source và conflict reconciliation; hoặc
- Scoped generation/epoch + sequence.

Không so `updatedAt` từ hai client clocks như version toàn cục khi nghiệp vụ cần strong correctness.

## 22. Một cách tiếp cận với event log

Khi source có event history đầy đủ:

~~~text
OrderCreated v1
OrderItemAdded v2
OrderConfirmed v3
OrderPaid v4
```

Có thể rebuild target bằng **replay** theo aggregate ordering và idempotency.

Nhưng cần:

- Initial event retention còn đủ không?
- Sự kiện có đủ fields để dựng state hiện tại?
- Có schema evolution/upcasting không?
- Có event bị xóa theo retention/privacy policy không?
- Có snapshot state tối ưu cho replay không?
- Có exactly-once business effect hay chỉ at-least-once delivery?

Event-sourcing replay và **database state backfill** là hai mô hình khác nhau, không tự hoán đổi.

## 23. Snapshot + CDC: ranh giới bắt đầu ở đâu?

Một pipeline lý tưởng có:

~~~text
Source consistent snapshot at checkpoint C
CDC stream begins at (or safely before) C
Backfill snapshot state
Apply CDC entries > C in correct order
Catch up to target watermark W
```

Điểm nguy hiểm là **gap**:

~~~text
Snapshot at 10:00
CDC subscription begins 10:05
Writes from 10:00 to 10:05 are lost
```

Cần API tạo snapshot + log position đồng bộ theo guarantees của engine, hoặc một thiết kế **overlap capture** có replay và idempotency để không bỏ sót.

## 24. Bắt đầu CDC sớm rồi backfill

Một chiến lược hay gặp:

1. Thiết lập CDC stream và lưu token/log position được hỗ trợ.
2. Bắt đầu capture các mutation phát sinh và persist chúng trong durable buffer.
3. Đọc/backfill lịch sử.
4. Áp CDC có ordering/conditional version guard.
5. Khi scan hoàn tất, tiếp tục CDC cho tới khi target lag dưới SLO.
6. Verify coverage và invariants.
7. Chuyển traffic theo cutover plan.

**Không mặc định mọi engine cho token tại một snapshot boundary nhất quán**; tính đúng phải được chứng minh theo capability và concurrency model thực.

## 25. Có cần lưu CDC vào queue riêng?

Backfill có thể kéo dài hàng chục giờ, trong khi change streams có retention hữu hạn. Một durable broker/outbox có thể giúp:

- Lưu mutations để replay.
- Tách backfill throughput và live change throughput.
- Giữ offset/checkpoint theo partition.
- Chống mất events khi worker restart.
- Cách ly tạm thời target overload.

Nhưng broker cũng có:

- Retention/capacity limits.
- Consumer lag và DLQ.
- Partition ordering semantics.
- At-least-once replay.
- Chi phí vận hành và network.

Một broker không tự cung cấp **end-to-end exactly-once state** nếu sink không idempotent.

## 26. Snapshot quá lớn kéo dài retention

Một long-running snapshot có thể khiến hệ phải giữ:

- MVCC versions.
- Oplog/WAL/CDC history.
- Compaction leftovers.
- Transaction metadata.
- Disk space.
- Backup snapshot state.

Một số engine không cho giữ consistent snapshot trong nhiều giờ mà không có chi phí đáng kể. Nếu không thể snapshot ổn định, hãy thiết kế **incremental scans + overlapping CDC + version reconciliation**, có proof về no-gap.

## 27. Chọn checkpoint theo vị trí dữ liệu

Một checkpoint không chỉ là “đã đọc 1 triệu dòng”.

Ví dụ:

~~~json
{
  "runId": "bf-2026-11",
  "shardId": "range-04",
  "lastCommittedKey": "TENANT#17#ORDER#102039",
  "sourceGeneration": "snapshot-001",
  "targetSchemaVersion": 2,
  "completed": false
}
~~~

Checkpoint có thể lưu:

- Range/shard/partition assignment.
- Key/cursor/resume token.
- Snapshot or stream generation.
- Transformer version.
- Last **durably applied** boundary.
- Retry/failed keys queue.
- Source/target cluster identity.
- Success/skip/conflict counters.

**Đánh dấu checkpoint trước khi target write durable** có thể làm mất dữ liệu khi worker crash.

## 28. Checkpoint sau commit, không sau read

Sai:

~~~text
Read page P
Persist checkpoint "P completed"
Write page P to target
Crash halfway
Resume after P
```

Phần page chưa ghi bị bỏ sót.

An toàn hơn:

~~~text
Read page P
Write each item idempotently
Verify required durable result
Persist checkpoint after all required work from P settled
```

Nếu checkpoint update thất bại sau target commit, retry page là bình thường **vì apply phải idempotent**. Việc checkpoint và target nằm ở hai systems không có shared transaction cần được thiết kế theo at-least-once behavior.

## 29. Partial failure trong một batch

Một batch 100 items:

~~~text
70 success
15 transient throttled
10 version skipped
5 validation failed
```

Không đánh dấu cả 100 “done” chỉ vì API batch trả HTTP success hoặc có một phần thành công.

Cần:

- Phân loại result per item.
- Retry throttled items với backoff và budget.
- Đếm version-skipped là outcome xác định theo policy.
- Quarantine invalid items/repair queue.
- Chỉ checkpoint coverage khi mọi item có **durable disposition**.
- Không đưa poison records vào vòng retry vô hạn.

Với DynamoDB `BatchWriteItem` đặc biệt phải xử lý `UnprocessedItems` theo API, không coi request cấp batch là tất cả đã ghi.

## 30. Resume token/cursor có thể hết hạn

Một source cursor hoặc CDC resume token có thể không còn dùng được do:

- Retention window quá ngắn.
- Shard split/merge hoặc topology change.
- Storage engine limitations.
- Session timeout.
- Snapshot generation bị thu hồi.
- Collection re-creation.
- Schema/partition-key migration.

Khi cursor invalid, không tự tiếp tục từ “index số 10.000” theo thứ tự không ổn định. Cần **replay, overlap scan, new snapshot hoặc full restart** theo proof correctness.

## 31. Chia range để chạy song song

Một backfill lớn có thể chia:

~~~text
Range A: keys 0000...1FFF
Range B: keys 2000...3FFF
Range C: keys 4000...5FFF
...
~~~

Mỗi range có:

- Stable id.
- Assigned worker.
- Cursor/checkpoint.
- Completed/failure state.
- Fair work allocation.
- Rate limit/quota.
- Reassignment mechanism.

Cần bảo đảm **coverage không gap** kể cả khi partitions/keys thay đổi trong lúc scan. Fixed key ranges và token ranges có ưu/nhược riêng theo engine.

## 32. Offset/skip pagination là một lựa chọn rủi ro

Một loop:

~~~text
find().skip(0).limit(1000)
find().skip(1000).limit(1000)
...
```

có thể:

- Trở nên đắt khi offset lớn.
- Bỏ sót/đọc trùng khi inserts/deletes đổi thứ tự.
- Phụ thuộc một order không được đảm bảo.
- Tạo query scans ngày càng tốn CPU/IO.

Với access pattern thích hợp, **keyset/range pagination** theo stable indexed key thường đáng tin và rẻ hơn. Nhưng nó vẫn cần CDC và key mutation handling nếu nguồn đang thay đổi.

## 33. Keyset pagination

Ví dụ khái niệm:

~~~text
SELECT records WHERE stableKey > lastKey
ORDER BY stableKey ASC
LIMIT batchSize
```

Sau khi xử lý thành công batch, cập nhật `lastKey`.

Điều kiện:

- `stableKey` có total ordering trong scan scope.
- Key không bị thay đổi giữa các pages hoặc có rule cho key changes.
- Query dùng index/key range phù hợp.
- Có quy tắc với inserts có key **nhỏ hơn lastKey**.
- Live changes được bù qua CDC hoặc dual-write.
- `lastKey` checkpoint sau target durable commit.

Không khẳng định keyset pagination tự cung cấp snapshot consistency.

## 34. Quét theo partition/range với skew

Một số tenants/partitions có hàng triệu items, trong khi đa số rất nhỏ. Chia theo số ranges bằng nhau không nhất thiết cân bằng công việc.

Có thể dùng:

- Partition/token range ownership.
- Split large ranges theo cardinality.
- Dynamic work stealing với checkpoint.
- Priority theo lag/remaining size.
- Adaptive concurrency per shard.
- Separate heavy tenants.
- Fairness để không “bỏ quên” small partitions.

Nhưng split/reassign phải giữ **at-least-once processing và no-gap coverage**. Không để hai workers cùng update checkpoint của một range mà không có generation/fencing.

## 35. Checkpoint ownership cũng cần fencing

Hai workers cùng xử lý range R:

~~~text
Worker A owns range R, generation=5
A pauses
Coordinator assigns R to B, generation=6
A resumes and writes checkpoint from an old cursor
```

Nếu A ghi checkpoint vô điều kiện, có thể lùi tiến độ hoặc nhảy qua việc B chưa hoàn tất.

Nên dùng conditional update theo:

~~~text
rangeId, expectedAssignmentGeneration, expectedCheckpointVersion
```

và chỉ cho worker đang sở hữu generation hợp lệ cập nhật. Tương tự sink apply idempotent và checkpoint design vẫn cần chịu được **in-flight writes từ owner cũ**.

## 36. Progress percent dễ gây ảo giác

`processedCount / estimatedTotalCount` có thể không chính xác vì:

- Source count thay đổi trong thời gian scan.
- Một số records lớn/nhỏ khác nhau.
- Retry và version skips làm processedCount tăng.
- Count không phản ánh CDC catch-up.
- Có ranges bị kẹt dù tổng đạt 99,9%.
- Target ghi thành công nhưng chưa được validate.

Nên báo song song:

- Scan ranges completed / total.
- Records with durable disposition.
- Bytes read/written.
- Failed/poison records.
- CDC lag by partition.
- Reconciliation mismatch count.
- ETA với confidence và throughput trend.
- SLO impact.

**100% scan progress không đồng nghĩa 100% migration complete.**

## 37. Backfill có thể chạy nhiều ngày

Nếu có \(N=100\,000\,000\) records và tốc độ xử lý **ổn định thành công** 2.000 records/s:

\[
T=\frac{100\,000\,000}{2\,000}=50\,000\text{ s}
\]

Tức khoảng 13,9 giờ **chưa kể failures, retries, pauses và catch-up**.

Nếu payload trung bình 2 KiB, logic data volume khoảng 190,7 GiB; bytes thực qua network/storage có thể lớn hơn do indexes, metadata, encryption, retries và replication.

Không dùng scan throughput trong 30 giây cache ấm để hứa thời gian hoàn tất cho hàng trăm triệu records.

## 38. Data size và write amplification

Một target write có thể làm:

~~~text
Data write
+ secondary index maintenance
+ WAL/commitlog
+ replica propagation
+ compaction
+ CDC event
+ cache invalidation
```

Vì vậy 1 GiB logical backfill có thể tạo nhiều hơn 1 GiB storage IO và network traffic. Đo **physical write bytes, disk queue, compaction backlog và replication lag**, không chỉ số bytes trong payload.

## 39. Query shape của source quyết định tải

Một scan có index covering/partition range phù hợp khác hoàn toàn unbounded collection scan hoặc scatter-gather query.

Cần xem:

- Index/partition key used.
- Keys/docs examined.
- Full-document fetches.
- Result/projection size.
- Cursor batch size.
- Read preference/consistency.
- Page cache hit/miss.
- Chunk/range distribution.
- Connection occupancy.

Backfill từ một replica phụ có thể giảm tải đọc trên primary **khi consistency và topology cho phép**, nhưng vẫn cạnh tranh replication apply/catch-up và có thể đọc stale data.

## 40. Read source qua secondary cần kiểm skew

Khi backfill dùng MongoDB secondary, dữ liệu có thể trễ so với primary. CDC từ primary nhận update mới và target cập nhật v8; sau đó secondary scan trả v7.

Nếu target có version guard, v7 bị skip. Nếu không, secondary read **làm hỏng projection**.

Ngoài ra:

- Secondary reads không tự là snapshot đúng mốc.
- Replica apply lag có thể tăng khi scan nặng.
- Read preference và read concern xác định semantics.
- Không ép source đọc từ secondary đang quá tải chỉ vì muốn “đỡ primary”.

## 41. Read/write SLO của production phải có ngưỡng

Ví dụ minh họa:

~~~yaml
productionSlo:
  checkoutP99Ms: 250
  searchP99Ms: 500
  http5xxPercent: 0.2
  durableWriteTimeoutPercent: 0.1
  replicationLagSeconds: 10
  cdcOldestAgeSeconds: 30
backfillPolicy:
  pauseIfAnyCriticalSloBreached: true
  resumeOnlyAfterHysteresis: true
~~~

Những thresholds là **ví dụ**; lựa chọn thực cần từ SLO/error budget. Không lấy dashboard “CPU < 80%” làm điều kiện duy nhất để tiếp tục migration.

## 42. Guardrails cần phân biệt source và target

Một job có thể đọc từ source và ghi target:

| Nơi | Tín hiệu phải đo |
|---|---|
| **Source** | Read p99, CPU, disk cache, outgoing bytes, replication lag |
| **Target** | Write p99, throttling, capacity, compaction/index backlog |
| **Java worker** | In-flight, heap/GC, pool wait, retries, batch queue |
| **CDC/broker** | Lag per partition, oldest age, retention margin |
| **Production API** | p99/p95, errors, timeout, success throughput |
| **Network** | Cross-AZ/region traffic, egress limits, packet loss |

Nếu source khỏe nhưng target throttling, tăng source scan speed chỉ làm backlog tăng. Nếu target khỏe nhưng source p99 xấu, phải giảm scan rate/concurrency hoặc thay read path.

## 43. Một ngân sách tải rõ ràng

Không nên viết “backfill ưu tiên thấp” mà không có cơ chế.

Ví dụ một ngân sách giả định:

~~~text
Source read budget:  5% of measured sustainable read capacity
Target write budget: 10% of measured safe write capacity
Worker concurrency:  8 processes x 4 requests in-flight
Per-shard cap:       limited independently
Priority:            production > CDC catch-up > historical backfill
```

Một cấu hình có thể phù hợp trong giờ thấp điểm nhưng không phù hợp khi traffic spike. Nên **throttle theo headroom thực tế**, với stop condition rõ.

Không cộng các phần trăm máy móc nếu operations có chi phí khác nhau.

## 44. Token bucket cho rate limiting

Một **token bucket** cấp tokens với tốc độ \(r\) và cho phép burst tối đa \(B\).

Ví dụ:

~~~text
refill rate r = 500 write units/s
bucket capacity B = 1,000 units
each operation consumes estimated cost units
```

Khi hết tokens, workers phải chờ hoặc defer work, không tiếp tục gửi. Burst capacity giúp tận dụng headroom ngắn hạn nhưng cũng có thể tạo spike không mong muốn.

Nếu mỗi item/operation có cost khác nhau, **token theo bytes/RCU/WCU/estimated IO** hữu ích hơn chỉ token theo request.

## 45. Rate limit không thay concurrency limit

- **Rate limit:** giới hạn operations/bytes mỗi giây.
- **Concurrency limit:** giới hạn requests đang xử lý cùng lúc.
- **Batch-size limit:** giới hạn số items/bytes cho một batch.
- **Pending queue limit:** giới hạn công việc đang đợi.
- **Deadline:** giới hạn thời gian chờ/attempt.
- **Retry budget:** giới hạn work amplification.

Ví dụ 1.000 operations/s nhưng một query mất 10 giây có thể tạo nhiều in-flight calls. Cần đồng thời **rate và concurrency cap** để không ăn hết driver pool.

## 46. Java worker và semaphore

Ví dụ skeleton có giới hạn đồng thời:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class BoundedBackfillWorker {
    private final Semaphore permits = new Semaphore(8);
    private final TargetRepository target;

    public BoundedBackfillWorker(TargetRepository target) {
        this.target = target;
    }

    public ApplyResult apply(BackfillRecord record)
            throws InterruptedException {

        boolean acquired = permits.tryAcquire(
            100, TimeUnit.MILLISECONDS
        );
        if (!acquired) {
            return ApplyResult.DEFERRED_OVER_CAPACITY;
        }

        try {
            return target.applyIfNewer(record);
        } finally {
            permits.release();
        }
    }
}
~~~

`TargetRepository`, `BackfillRecord`, `ApplyResult` là domain types minh họa. `applyIfNewer` **phải** thực hiện condition atomically ở target; semaphore chỉ giới hạn requests trong một JVM, **không tự bảo đảm idempotency hay consistency**.

## 47. Tổng concurrency của nhiều pods

Nếu có 12 workers, mỗi worker giữ 16 in-flight requests:

\[
C_{\text{global max}}=12\times16=192
\]

Đây là **tổng giới hạn phía ứng dụng** nếu tất cả worker đều hoạt động đồng thời; chưa tính SDK retries, requests ngoài backfill hoặc multiplexing của driver.

Cần tính global cap qua:

- Worker count × per-worker permits.
- Shared token bucket/central quota nếu cần.
- Per-shard caps.
- Per-tenant fairness.
- Autoscaling behavior.
- Downstream quotas.

Một deployment tăng replicas từ 4 lên 20 có thể vô tình tăng backfill traffic gấp 5 lần nếu chỉ giới hạn local.

## 48. Adaptive throttling

Một **adaptive controller** có thể giảm tốc độ khi:

- Production p99 tăng.
- API error rate vượt ngưỡng.
- Target throttling tăng.
- DB CPU/IO/replication lag chạm cap.
- CDC backlog tuổi tăng.
- Client pool wait tăng.
- Background compaction debt tích tụ.

Khi metrics hồi phục, tăng tốc **từng bước nhỏ**, không nhảy ngay về max rồi dao động.

Cần hysteresis/cooldown vì metrics có noise và độ trễ.

## 49. Điều khiển kiểu AIMD

Một mô hình đơn giản:

~~~text
Every control interval:
  if SLO threatened or throttling:
      rate = max(minRate, rate * 0.5)
  else if stable for cooldown:
      rate = min(maxRate, rate + smallStep)
```

Đây là **Additive Increase, Multiplicative Decrease** ở mức ý tưởng, không phải controller tối ưu chung. Threshold, interval và per-stage limits phải được thử để tránh oscillation.

Khi xảy ra **critical correctness error**, throttle thôi chưa đủ: phải **pause/fail closed**, giữ checkpoint và điều tra.

## 50. Bảo vệ production bằng workload priority

Một policy có thể là:

~~~text
Priority 1: authoritative user writes
Priority 2: correctness-critical CDC catch-up
Priority 3: interactive reads
Priority 4: historical backfill
Priority 5: optional analytics refresh
```

Đây là ví dụ phân loại. Không có một thứ tự tuyệt đối cho mọi hệ; một hệ có read SLO rất chặt có thể ưu tiên interactive reads hơn background writes.

Cách triển khai:

- Separate concurrency pools.
- Per-collection/table quotas.
- Admission control.
- Pausable scheduler.
- Nighttime windows nếu phù hợp.
- Fairness per tenant/shard.
- Isolate bulk writes khỏi latency-critical operations.

**Ưu tiên thấp không nghĩa job được phép giữ vô hạn connections rồi chờ.**

## 51. Backfill phải nhường khi server gần saturation

Giả sử nguồn có capacity đo được là 10.000 read units/s. Production bình thường dùng 7.500 units/s, nhưng giờ cao điểm tăng 9.700 units/s.

Một backfill cố giữ 2.000 units/s sẽ khiến tổng yêu cầu 11.700 units/s, có thể gây queueing và timeout.

Không nên lấy 10% hay 20% của “capacity danh nghĩa” mà không xem **current headroom và reliability margin**. Một controller hợp lý có thể tính available budget theo:

\[
B_{\text{backfill}}\le\max(0,C_{\text{safe}}-L_{\text{production}}-H)
\]

Trong đó:

- \(C_{\text{safe}}\): throughput bền vững giữ SLO.
- \(L_{\text{production}}\): tải traffic đang phục vụ.
- \(H\): reserve cho burst/failure/repair.

Đây là mô hình khái niệm, không phải số liệu tự suy từ CPU hay một hệ số cố định.

## 52. Đo chi phí theo work units

Hai items:

~~~text
Record A: 1 KiB, point read + small indexed update
Record B: 3 MiB, large arrays + multiple index updates
```

Cùng một “record” nhưng B có thể tốn nhiều network/IO/CPU hơn. Nếu chỉ rate-limit 100 records/s, workload rất dễ dao động.

Có thể tính theo:

- Estimated read/write capacity units.
- Bytes read/written.
- Query/scan work.
- Index entries changed.
- CPU/disk milliseconds.
- Empirically measured cost per operation class.

Không cần có estimator hoàn hảo trước mới throttle; **kết hợp token budget, concurrency và phản hồi SLO thực**.

## 53. Cache pollution

Full scan có thể kéo lượng dữ liệu rất lớn qua cache:

~~~text
Hot production read set = 20 GiB
Cache memory = 30 GiB
Backfill sequential scan = 300 GiB
```

Nếu scan làm dữ liệu nóng bị đẩy khỏi cache, production reads chuyển thành disk reads và p99 tăng dù CPU không đạt 100%.

Giảm tác động bằng:

- Hạn chế scan concurrency/batch size.
- Dùng replica/read path phù hợp.
- Chia thời gian xử lý.
- Tránh repeated scanning.
- Projection chỉ lấy fields cần.
- Có metric cache evictions/page faults.
- Tách workloads sang nguồn snapshot/offline nếu tính đúng cho phép.

Không mặc định “đọc secondary thì miễn phí”: secondary vẫn cần cache/IO để apply replication.

## 54. Full scan ảnh hưởng disk I/O và compaction

Với storage engine kiểu LSM, backfill writes có thể tạo nhiều SSTables/compaction. Với index/page-oriented engine, scans và index updates cũng có chi phí page cache/disk.

Dấu hiệu:

- Disk read/write queue tăng.
- Compaction backlog tăng.
- CPU tăng vì serialization/merge.
- Replication lag tăng.
- Checkpoint/WAL flush chậm.
- Read amplification.
- Tail latency tăng dù average ổn.

Đo **sustained workload** và giai đoạn catch-up; nếu compaction debt tăng liên tục, job có thể chưa đạt tốc độ bền vững.

## 55. Hạn chế batch size

Một batch quá lớn:

- Giữ memory lâu.
- Tạo payload network lớn.
- Làm GC pause/heap spike.
- Tăng transaction duration.
- Có thể vượt API size/count limits.
- Gây retry toàn batch hoặc partial failures khó xử lý.
- Tạo burst disk/replica traffic.

Một batch quá nhỏ:

- Tăng request/round-trip overhead.
- Tốn nhiều metadata/HTTP/TLS.
- Có thể không tận dụng bulk API.

Cần thử nhiều mức `batchSize` trên **data shape thật**, đo p99, rate, memory và error outcomes. Không có một con số batch size tối ưu cho mọi engine.

## 56. Bounded queue trong Java worker

Thiết kế:

~~~text
Scan workers -> bounded transform queue -> bounded target writers
```

Nếu target chậm, queue đầy thì **scanner phải dừng/giảm**, không tiếp tục đọc rồi giữ hàng triệu documents trong RAM.

Có thể dùng:

- `ArrayBlockingQueue` với capacity rõ.
- `Semaphore` cho in-flight writes.
- Demand/backpressure trong reactive stream.
- Batching có max bytes và max wait.
- Durable broker nếu backlog phải sống qua process restart.
- Metrics queue depth và oldest queued age.

Một in-memory queue **không phải durable checkpoint**; process crash có thể mất những items chưa ghi, nên resume phải đọc lại qua durable progress boundary.

## 57. Khi target không khả dụng

Một backfill nên:

1. Tạm ngừng phát writes mới.
2. Giới hạn retries + exponential backoff + jitter.
3. Giữ durable checkpoint tại phần đã hoàn thành.
4. Chờ target hồi phục hoặc operator can thiệp.
5. Không ACK checkpoint cho items chưa ghi.
6. Kiểm CDC lag/retention trong lúc pause.
7. Nếu retention có nguy cơ hết, chuyển sang kế hoạch re-snapshot/reconcile.

Không dùng vòng lặp retry không giới hạn vì một mục tiêu “phải hoàn thành migration”.

## 58. Retry budget

Ví dụ:

~~~text
Per-item max attempts = 5
Total retry time = bounded by deadline
Throttle retries separately from new work
Transient errors only
Poison records -> quarantine after policy
```

`version conflict` có thể là **skip vì incoming cũ**, không phải transient. `validation error` có thể cần sửa transform/schema, không retry. `unknown write outcome` cần read/reconcile bằng key/version/idempotency trước khi gửi lại.

Nếu SDK tự retry, application phải tính **tổng attempts**, tránh nested retry amplification.

## 59. Jitter tránh retry đồng loạt

Sau target throttling, 1.000 workers cùng sleep chính xác 1 giây rồi retry có thể tạo **thundering herd**.

Backoff + jitter phân tán attempts:

~~~text
retry delay = random(0, min(maxBackoff, base * 2^attempt))
```

Đây là ý tưởng *full jitter*, không phải quy tắc bắt buộc cho mọi lỗi. Phải có global budget, stop condition, giới hạn concurrent requests và deadline.

## 60. Dynamic pause khác kill job

**Pause an toàn** thường có nghĩa:

- Ngừng nhận ranges/pages mới.
- Chờ hoặc cancel in-flight operations có kiểm soát.
- Ghi durable dispositions.
- Flush/checkpoint đúng boundary.
- Dừng target writes.
- Giữ CDC capture hoặc bảo đảm replay window.
- Cho phép resume cùng `runId`/transform version.

Kill process có thể vẫn an toàn nếu mọi apply idempotent và checkpoint sau commit, nhưng có thể làm **tăng replay work** và không được dùng như “pause function” chính thức nếu cần operator control.

## 61. Kill switch phải có trước cutover

Một migration quan trọng nên có:

~~~yaml
backfillControl:
  enabled: true
  pauseOnCriticalSlo: true
  maxConcurrentWrites: configured
  maxReadRate: configured
  maxWriteRate: configured
  maxOldestCdcLagSeconds: configured
  maxErrorBudgetUsage: configured
  emergencyStop: operatorControlled
~~~

Các fields minh họa. Operator phải có quyền **giảm tốc/dừng ngay** mà không redeploy toàn hệ hoặc sửa source-of-truth data.

## 62. Hysteresis ngăn bật/tắt liên tục

Nếu controller:

~~~text
p99 > 250ms -> pause
p99 <= 250ms -> resume immediately
```

metric dao động quanh 250 ms khiến job bật/tắt liên tục.

Một chính sách:

- Pause ngay khi vượt critical threshold đủ điều kiện.
- Chờ ổn định trong nhiều measurement windows.
- Resume ở rate thấp hơn.
- Tăng dần khi ổn định.
- Cooldown sau mỗi lần điều chỉnh.
- Manual gate cho correctness incident.

Tách **sự cố SLO do backfill** với **sự cố độc lập** nếu có thể, nhưng khi ảnh hưởng nghiêm trọng đến production hãy ưu tiên an toàn.

## 63. Rate limit theo tenant, collection và shard

Một global quota có thể che:

~~~text
Total source usage: 60%
Shard 7 usage: 100%
Other shards: 40%
```

Backfill nên có giới hạn theo:

- Source shard/partition.
- Tenant workload.
- Target partition.
- Operation class.
- Read/write capacity.
- Region/network path.

Một hot partition có thể bị overload dù tổng cluster còn headroom. Rate limit chỉ theo cluster tổng không đủ.

## 64. Fairness và quyền ưu tiên

Một tenant chiếm 70% dữ liệu có thể khiến những tenants nhỏ chờ mãi, kéo dài thời gian xác nhận cutover theo tenant.

Có thể:

- Weighted fair scheduling.
- Per-tenant parallelism caps.
- Split large tenants thành ranges.
- Track coverage per tenant.
- Ưu tiên high-value/critical cohorts nhưng không bỏ starvation.
- Track oldest unfinished range.
- Đặt deadline/exit criteria theo migration phase.

**Tiến độ tổng 99% không hợp lệ nếu 1% còn lại là toàn bộ một tenant quan trọng chưa được di chuyển.**

## 65. Giới hạn chi phí tài chính

Backfill vào managed NoSQL có thể tăng:

- Read/write capacity consumption.
- On-demand API requests.
- GSI write capacity.
- Replicated storage.
- Cross-region transfer.
- Backup/snapshot size.
- CDC/stream read charges.
- KMS encryption requests.
- Worker CPU/instance cost.

Một throttle có thể phải thỏa **cả SLO và ngân sách chi phí**, ví dụ giới hạn cross-region egress GB/ngày. Không chọn tốc độ tối đa nếu làm hóa đơn vượt budget không được phê duyệt.

---

## 66. MongoDB: quét theo indexed key

Ví dụ collection có `_id` dạng ổn định, có thể sử dụng keyset pagination:

~~~javascript
const page = db.orders
  .find(
    { _id: { $gt: lastId } },
    { projection: { _id: 1, status: 1, version: 1, tenantId: 1 } }
  )
  .sort({ _id: 1 })
  .limit(500)
  .toArray();
~~~

Lưu ý:

- `lastId` phải là giá trị đúng kiểu BSON/ObjectId/string.
- `_id` của documents thường không thay, nhưng inserts có `_id` **nhỏ hơn cursor** có thể không được scan; dùng CDC overlap.
- Query phải đúng index/shard targeting.
- Read concern/preference cần được chọn theo source semantics.
- Mỗi page không tự cùng một consistent snapshot.

Đây là mẫu shell minh họa, không phải lệnh dùng nguyên xi để migrate dữ liệu thật.

## 67. MongoDB: thay `skip` bằng keyset ở dataset lớn

Ví dụ `skip(5_000_000).limit(500)` có thể bắt engine phải đi qua lượng dữ liệu trước offset, tốn tài nguyên. Từ đó mỗi page sau còn đắt hơn.

Keyset:

~~~text
Read page where _id > checkpointId
Order by _id ascending
Checkpoint last _id after durable target applies
```

giúp tránh chi phí offset quá lớn trong nhiều access patterns. Tuy nhiên, như đã nêu, **đúng snapshot/mutations** là một bài toán riêng và phải kết hợp change capture.

## 68. MongoDB: Change Streams trong backfill

MongoDB Change Streams (trong deployments đáp ứng hỗ trợ) có thể phát các mutations sau một resume token/operation time theo contract.

Khi dùng cho backfill:

- Thiết lập subscription và durable resume state.
- Hiểu full-document lookup semantics.
- Xử lý insert/update/delete và invalidate.
- Không mất events trong retention window.
- Chống replay bằng event identity/version.
- Có checkpoint stream riêng với scan checkpoint.
- Khi resume token invalid, có recovery path được xác minh.

`fullDocument: updateLookup` có thể trả **trạng thái document tại thời điểm lookup**, không nhất thiết là ảnh chính xác của mutation ban đầu theo mọi race; cần version/ordering rõ.

## 69. MongoDB: version-aware target update

Một ý tưởng pseudocode:

~~~javascript
db.orders_v2.updateOne(
  {
    _id: "order-100",
    sourceVersion: { $lt: incoming.sourceVersion }
  },
  {
    $set: incoming
  }
);
~~~

Điều kiện này không match khi target chưa tồn tại và cũng cần xử lý trường hợp version missing; bật `upsert:true` ngây thơ cùng predicate có thể đụng unique `_id` nếu target đã tồn tại nhưng version >= incoming.

Thiết kế thực cần **atomic conditional create-or-advance** phù hợp với schema, có thể sử dụng một update pipeline, transaction hoặc xử lý duplicate-key/compare-on-retry theo capabilities và semantics.

Không copy một đoạn `updateOne` rút gọn rồi tin rằng nó đã giải mọi race của upsert.

## 70. MongoDB Java: cursor và batch

Ví dụ Java sync driver:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.types.ObjectId;

public void scanPage(
        MongoCollection<Document> source,
        ObjectId lastSeenId,
        int pageSize) {

    try (MongoCursor<Document> cursor = source
            .find(Filters.gt("_id", lastSeenId))
            .sort(Sorts.ascending("_id"))
            .limit(pageSize)
            .batchSize(Math.min(pageSize, 200))
            .iterator()) {

        while (cursor.hasNext()) {
            Document doc = cursor.next();
            // Transform; apply idempotently; persist checkpoint.
            // This snippet does NOT implement durability/CDC/rate limit.
        }
    }
}
~~~

Các types/API minh họa MongoDB Java Sync Driver. Nếu `lastSeenId` ban đầu null, cần query khác hoặc conditional filter; code này chỉ mô tả một page sau checkpoint có ObjectId hợp lệ. Không mở một MongoClient cho mỗi page.

## 71. MongoDB BulkWrite: partial errors và ordering

Bulk writes có thể giảm roundtrips nhưng:

- Ordered/unordered modes có semantics lỗi khác.
- Duplicate-key và validation errors cần phân loại.
- Retryable writes/transactions có scope riêng.
- Phải kiểm individual outcomes/counters theo API.
- Chưa chắc mọi operation cùng semantics khi network failure.
- Write concern ảnh hưởng ACK/durability.

Không ghi checkpoint cả batch nếu phần target chưa được xác minh. Với `unordered`, **thứ tự apply** không được dùng như source version ordering; conditional guard phải làm đúng.

## 72. MongoDB secondary lag và throttling

Một backfill chạy readPreference=secondary có thể:

- Dùng read capacity của secondary.
- Làm lag secondary tăng do IO/cache pressure.
- Ảnh hưởng những production reads cũng dùng secondary.
- Có thể đọc stale states.
- Khi secondary trở thành primary, gánh tải thay đổi.

Monitor **per-member replication lag, read latency, CPU/IO, cursor timeout**. Throttle hoặc chuyển path an toàn trước khi lag đe dọa CDC retention/freshness.

## 73. MongoDB index build và backfill

Nếu target cần index mới:

~~~text
Create collection/schema
Build indexes
Backfill writes
CDC catch-up
Cutover
```

Tạo index trước có thể làm mỗi backfill write đắt hơn, nhưng thiếu index có thể khiến queries verification/cutover chậm. Build index sau có thể cần scan lớn và maintenance window.

Cần **benchmark hai lịch trình phù hợp** và hiểu unique index, migration constraints, index build resource/locking semantics theo version. Không bỏ unique constraint có ý nghĩa nghiệp vụ chỉ để tăng tốc import.

---

## 74. DynamoDB: Scan không có consistent snapshot toàn table

DynamoDB `Scan` đọc các items theo API pagination. `ConsistentRead=true` có thể tăng consistency của individual read theo scope hỗ trợ, nhưng **không biến toàn bộ multi-page Scan thành snapshot nhất quán tại một thời điểm**.

Với live writes:

- Một item có thể được thay đổi giữa pages.
- New item có thể nằm trước cursor.
- Deletes/updates có thể xảy ra.
- Parallel Scan segments không có global ordering.
- `LastEvaluatedKey` là pagination cursor, không phải CDC watermark.

Cần chiến lược **DynamoDB Streams, dual-write/outbox hoặc export point-in-time theo service capability**, kết hợp version guard và reconciliation.

## 75. DynamoDB: Parallel Scan

DynamoDB hỗ trợ `Segment` và `TotalSegments` cho parallel scan. Mỗi segment có cursor riêng và các requests có thể chạy đồng thời.

Ví dụ:

~~~text
TotalSegments = 8
Workers:
  segment 0 -> LastEvaluatedKey 0
  segment 1 -> LastEvaluatedKey 1
  ...
  segment 7 -> LastEvaluatedKey 7
```

Lưu:

- Segment ID.
- TotalSegments.
- LastEvaluatedKey.
- Durable last applied page/record state.
- Worker assignment generation.
- Result counts/failed items.

Không đổi tùy tiện `TotalSegments` giữa một checkpointed run mà không hiểu việc partition/coverage; muốn reshard work nên có planned restart/repartition strategy.

## 76. DynamoDB: consumed capacity và throttling

Đo:

- Consumed ReadCapacityUnits/WriteCapacityUnits.
- Provisioned/on-demand limits.
- Throttled requests và reasons.
- Hot partition-key traffic.
- GSI capacity.
- SDK retry count.
- Source/target latency.
- Stream lag/freshness.

Một `Scan` tốn capacity theo item sizes và read behavior; không chỉ số returned items. Đặt **read budget** và giảm tốc khi production consume capacity tăng.

## 77. DynamoDB: `Limit` không đồng nghĩa số items trả về

Khi Query/Scan dùng filter expression, số items **được đánh giá** khác số items trả về sau filter. `Limit` và page size/response size rules của DynamoDB có semantics cụ thể.

Nếu chỉ đo returned record count, job có thể tưởng workload nhẹ dù đã tiêu tốn nhiều read capacity để scan/filter. Cần đo **ScannedCount, Count, ConsumedCapacity** khi API cho phép.

## 78. DynamoDB: Java SDK v2 Scan pagination

Ví dụ skeleton:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ScanRequest;
import software.amazon.awssdk.services.dynamodb.model.ScanResponse;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;

public void scanOneSegment(
        DynamoDbClient client, String table,
        int segment, int totalSegments) {

    Map<String, AttributeValue> nextKey = null;

    do {
        ScanRequest request = ScanRequest.builder()
            .tableName(table)
            .segment(segment)
            .totalSegments(totalSegments)
            .exclusiveStartKey(nextKey)
            .limit(100)
            .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
            .build();

        ScanResponse response = client.scan(request);

        for (var item : response.items()) {
            // Transform + conditional apply with retry/classification.
        }

        // Persist checkpoint only after all page items have
        // a durable disposition.
        nextKey = response.lastEvaluatedKey();
    } while (nextKey != null && !nextKey.isEmpty());
}
~~~

Code mô tả control flow, không đủ thành worker production: chưa có persisted cursor, source/target credentials, interruption, TTL, retries, rate/concurrency limits và idempotent sink. Khi SDK builder nhận null field cần đối chiếu version/API; có thể chỉ set `exclusiveStartKey` khi có cursor.

## 79. DynamoDB: conditional upsert theo `sourceVersion`

Một target item có `sourceVersion`. Có thể dùng ConditionExpression:

~~~text
attribute_not_exists(pk)
OR sourceVersion < :incomingVersion
```

Trên một item với primary key đã biết, conditional PutItem/UpdateItem có thể ngăn ghi bản cũ hơn nếu biểu thức và schema được thiết kế phù hợp.

Cần xem:

- Composite partition/sort key nếu có.
- Condition khi `sourceVersion` missing.
- Equality/replay behavior.
- Generation/tenant correctness.
- Version monotonicity nguồn.
- ConditionalCheckFailed xử lý như **stale/duplicate** hay conflict.
- Transaction scope nếu thêm nhiều items/GSI/ledger.
- Global Tables/multi-region semantics có conflict rules riêng.

Đừng tự retry vô hạn `ConditionalCheckFailedException`.

## 80. DynamoDB BatchWriteItem không hỗ trợ condition per write

`BatchWriteItem` hữu ích cho những công việc bulk theo API constraints, nhưng không phù hợp khi cần **conditional sourceVersion guard trên từng item** như một PutItem/UpdateItem có condition.

Nếu dùng batch writes để đạt throughput, có thể ghi đè một CDC state mới hơn. Khi correctness cần CAS, phải chọn **conditional operations/transactions hoặc kiến trúc nạp dữ liệu khác có ordering guarantee**, rồi đo chi phí.

Đây là một đánh đổi quan trọng: **bulk throughput không phải lý do bỏ version safety**.

## 81. DynamoDB Streams và giới hạn replay

DynamoDB Streams cung cấp change records theo stream/shard semantics khi bật và cấu hình hỗ trợ. Cần:

- Đảm bảo stream enabled trước mutation boundary cần capture.
- Kiểm retention/consumer lag.
- Checkpoint sequence numbers per shard.
- Xử lý shard lifecycle/splits.
- Chống duplicates/retries.
- Không suy global total order giữa shards.
- Xử lý deletes/TTL events theo service semantics.
- Nếu backlog quá hạn retention, chọn re-export/reconcile.

Tùy bài toán, PITR export tới S3 có thể là nguồn snapshot rất hữu ích; phải nối snapshot point và stream events đúng theo contract để không gap.

## 82. DynamoDB PITR export có thể giảm scan pressure

Một managed point-in-time export (khi dịch vụ hỗ trợ) có thể cho phép đọc từ file xuất ở object storage thay vì quét trực tiếp production table, giảm một số loại pressure trên source API.

Tuy nhiên:

- Export có latency/cost.
- File format/splitting/order cần xử lý.
- Export timestamp phải được nối với CDC.
- Data access/PII/IAM/encryption cần bảo vệ.
- Target write vẫn có thể quá tải.
- Không giả định export file chứa toàn bộ stream mutations sau export point.

Thiết kế **snapshot-export + change stream catch-up** vẫn cần version/CAS/reconciliation.

---

## 83. Cassandra: thiết kế backfill theo partition key

Cassandra/wide-column data model được tối ưu theo partition/clustering keys, không phải arbitrary full-table scans xuyên tất cả nodes bằng một truy vấn chung.

Để backfill, cần xem:

- Partition key/table schema.
- Token ranges.
- Data locality.
- Replica placement.
- Consistency levels.
- Coordinator selection.
- Large partitions và tombstones.
- Compaction/repair load.

Một CQL query **không có partition key** hoặc dùng `ALLOW FILTERING` trên bảng lớn có thể tạo tải rất nặng. Không dùng nó làm cách backfill mặc định.

## 84. Cassandra: token-range scanning

Một số công cụ/triển khai cho phép quét theo token ranges hoặc dùng Spark connector/backup/export phù hợp.

Ý tưởng:

~~~text
Assign token range [A,B) to worker W1
Assign token range [B,C) to worker W2
...
```

Nhưng:

- Token range khác range theo business key.
- Partition count/size phân bố không đều.
- Cluster topology/resharding có thể thay.
- Pagination and continuation state phức tạp.
- Không có global snapshot chỉ từ token range.
- Repairs/compaction/consistency ảnh hưởng tính đầy đủ và latency.

Một database-aware tool có support phù hợp có thể an toàn hơn tự viết CQL `token(...)` loop nếu phạm vi dữ liệu lớn.

## 85. Cassandra: consistency level cho scan

Read consistency level (ví dụ ONE/LOCAL_ONE/LOCAL_QUORUM theo cấu hình) tác động:

- Số replicas cần phản hồi.
- Freshness/repair semantics.
- Read latency.
- Availability dưới node failure.
- Tài nguyên coordinator/replicas.

Dùng mức thấp có thể giảm load nhưng đưa dữ liệu stale; dùng mức cao tăng áp lực và không tự có snapshot multi-partition.

Nếu target có `sourceVersion` tin cậy, một stale scan record có thể bị chặn bởi CDC newer version. Nhưng CDC cho Cassandra có **capabilities và limitations theo deployment**; không mặc định giống MongoDB Change Streams.

## 86. Cassandra: timestamp-based LWW và backfill

Nếu source/target dùng write timestamps để reconcile, một backfill ghi với timestamp “bây giờ” có thể thắng một write nghiệp vụ hợp lệ đã xảy ra trước đó, dù payload mang state cũ.

Ngược lại dùng client timestamps của nguồn cũng có thể bị clock skew/old future timestamp. Cần:

- Phân biệt **business version** với Cassandra cell timestamp.
- Xác định write timestamp policy khi import.
- Thống nhất conflict/TTL semantics.
- Không để backfill override live writes.
- Dùng LWT/conditional pattern phù hợp khi cần atomic compare.
- Test tombstones và resurrection.

Không giải bằng cách cấp cho backfill một write timestamp vô hạn thấp/cao mà không hiểu storage behavior.

## 87. Cassandra: TTL, tombstones và migration

Một row đã gần hết TTL tại source có thể được ghi mới tại target và kéo dài lifetime ngoài ý muốn. Delete/tombstones có thể bị skip nếu chỉ xuất non-deleted rows.

Cần:

- Preserve intended expiry semantics.
- Capture explicit deletes.
- Reconcile tombstone visibility.
- Test reinserted keys và generation.
- Theo dõi tombstone scanning/compaction.
- Không bỏ `gc_grace_seconds`/repair policy chỉ để tăng tốc backfill.

**Backfill cũ không được hồi sinh delete mới.**

## 88. Cassandra: CDC/stream không phải khả năng thống nhất mọi phiên bản

Apache Cassandra có cơ chế CDC theo table/commitlog trong những phạm vi/version có hỗ trợ, nhưng thiết kế, throughput, retention và toolchain khác Change Streams hoặc DynamoDB Streams.

Không mặc định:

- Có durable global ordered log.
- Stream giữ vô hạn.
- Có delete snapshot đầy đủ.
- Có exactly-once sink apply.
- Có global transaction timestamp.

Cần xác minh connector/tool sử dụng, backpressure và khả năng replay khi lag vượt retention.

---

## 89. Redis: `SCAN` không phải snapshot ổn định

Redis `SCAN` hỗ trợ incremental iteration qua keyspace, thích hợp hơn `KEYS *` cho nhiều mục đích vận hành, nhưng **không cung cấp consistent snapshot** của keyspace đang thay đổi.

Có thể:

- Trả duplicate keys.
- Không cho total ordering theo key.
- Những keys thêm/xóa trong lúc iteration có visibility không đơn giản.
- TTL có thể làm key biến mất.
- `COUNT` là hint chứ không nhất thiết exact page size.

Một Redis backfill cần **dedupe/idempotency** và chiến lược capture changes hoặc source-of-truth khác; không dùng `SCAN` một lần như bằng chứng đã thấy mọi key trong live keyspace.

## 90. Redis: tránh lệnh chặn dài

Không nên dùng:

~~~text
KEYS *
GET each key, SET target
```

trên một Redis instance lớn mà không đánh giá sự ảnh hưởng của command execution/network/connection và client queue.

Thay thế thường:

- SCAN incremental.
- Small bounded batches.
- Pipelining có giới hạn.
- Per-key TTL preservation.
- Stop/retry logic.
- Tránh Lua scripts quét keyspace không giới hạn.
- Theo dõi Redis event loop latency, CPU, memory, network và eviction.

Redis nhanh cho point ops không nghĩa full keyspace scan vô hạn rẻ.

## 91. Redis: giữ TTL còn lại

Ví dụ source key còn 20 giây TTL:

~~~text
PTTL session:S1 -> 20000 ms
```

Nếu target được `SET EX 3600`, session sẽ sống thêm một giờ thay vì 20 giây. Nên migrate expiration với semantics phù hợp:

- Lấy TTL còn lại gần thời điểm copy.
- Trừ elapsed copy/clock uncertainty khi cần.
- Có policy cho key expire giữa đọc và ghi.
- Với business expiry, dùng absolute expiry được kiểm tại read.
- Tránh migrate keys đã hết hạn.
- Retry idempotent không reset expiry vô tình.

Cần phân biệt `PTTL` báo key không tồn tại và key tồn tại không có TTL theo semantics lệnh.

## 92. Redis replication/failover và writes

Nếu Redis target có asynchronous replicas, `SET` success trên primary không luôn đồng nghĩa write đã durable ở mọi replica. Một failover ngay trong backfill có thể làm target mất acknowledged writes theo topology.

Checkpoint/durability policy phải phù hợp:

- Persisted target outcome theo contract.
- Reconciliation sau failover.
- Idempotent reapply.
- Snapshot/replication safety.
- Key conflict handling.

Không dùng Redis transient cache làm sole authority cho migration ledger trừ khi durability yêu cầu đã được bảo vệ riêng.

---

## 93. Elasticsearch/OpenSearch như read model đích

Một hệ NoSQL có thể backfill MongoDB → search index. Dù search engine không phải source-of-truth, migration vẫn ảnh hưởng:

- Indexing thread pools/queues.
- Refresh/merge CPU/IO.
- Shard size/hotspot.
- Bulk indexing latency.
- Replica apply.
- Disk watermarks.
- Search query p99.
- Mapping conflicts.
- Eventual visibility.

Thay vì chỉ so `bulk indexed count`, phải đo **source commit-to-search visible** và full read-model correctness.

## 94. Search index versioning

Nếu historical backfill v7 và CDC v8 cùng index document O-100, một **external version/CAS-compatible indexing strategy** hoặc guarded application-side projector có thể ngăn v7 overwrite v8 theo capabilities của engine.

Cần xét:

- External version semantics.
- Delete/tombstone version retention.
- Index re-creation/alias cutover.
- Partial update behavior.
- Retry/duplicate requests.
- When bulk writes become search-visible.
- Version overflow/generation changes.

Không dựa vào bulk request order từ hai workers để đại diện source order.

## 95. Reindex alias cutover

Một cách xây Search v2:

~~~text
orders_v1 (live index)
orders_v2 (building)
    <- historical backfill
    <- CDC after boundary
Verify coverage, query results and lag
Switch read alias / traffic gradually
Keep v1 for rollback window
```

Một alias switch có thể nguyên tử theo API của search engine trong phạm vi hỗ trợ, nhưng **application query cache, clients và in-flight operations** vẫn cần tính.

Đừng xóa v1 ngay sau alias switch; rollback có thể cần nó.

---

## 96. Cẩn thận với dual writes

Một ứng dụng ghi source và target trong cùng request:

~~~text
write source
write target
```

có nguy cơ **partial success**:

- Source success, target fails.
- Source fails, target success.
- Timeout khiến outcome không biết.
- Target ghi trước source mà data bị rollback.
- Hai hệ không có distributed transaction.

Nếu không có transaction atomic xuyên hai systems, dual write chỉ an toàn theo contract khi có **outbox/event capture, idempotency, compensation/reconciliation**. Không coi hai SDK calls liên tiếp là atomic dual commit.

## 97. Transactional outbox

Một mô hình đáng cân nhắc:

~~~text
Within authoritative source transaction:
  update Order version=42
  insert Outbox event version=42
  commit

Background publisher:
  read durable Outbox
  deliver event at least once
  target applies iff version newer
  mark/checkpoint published appropriately
```

Ưu điểm: giảm khoảng trống giữa source mutation và event publication nếu nguồn hỗ trợ **atomic write of state + outbox** trong scope. Chi phí: outbox retention/cleanup, publisher retries, monitoring.

Không mặc định mọi NoSQL engine có multi-item transaction theo cùng semantics; cần thiết kế aggregate phù hợp.

## 98. Dual-write source of truth

Khi chuyển nguồn ghi từ old DB sang new DB, phải chọn **đúng một authority tại mỗi giai đoạn** hoặc một protocol giải quyết conflicts.

Một plan:

~~~text
Phase 1: old authoritative, new follows.
Phase 2: cutover write authority after gate.
Phase 3: new authoritative, old retained read-only / replicated for rollback.
```

Nếu sau cutover muốn rollback writes về old DB, cần **reverse CDC/replay** hoặc một write path đã bảo vệ đồng bộ. Giữ old DB tồn tại không có nghĩa rollback dữ liệu mới tự thực hiện được.

## 99. Migration đọc và migration ghi có độ khó khác

**Read cutover**:

- Thay routing đọc tới target.
- Có thể canary một số requests/users.
- Có fallback đọc source nếu consistency policy cho phép.
- Source vẫn là write authority.

**Write cutover**:

- Thay nơi quyết định giao dịch.
- Phải xử lý unknown commits/idempotency.
- Tránh two concurrent write authorities.
- Cần rollback/reconciliation phức tạp.
- Phải bảo vệ ordering và durability.

Nên tách hai phases khi khả thi, không chuyển read/write toàn bộ cùng một phút chỉ để đơn giản hóa deployment.

## 100. Shadow reads và diff

Trước cutover, API có thể tiếp tục trả kết quả từ source nhưng **đọc thêm target để so**:

~~~text
Client request -> authoritative source -> return response
                          |
                          +-> asynchronous target shadow read
                                  -> compare normalized results
                                  -> metric differences
```

Cần giới hạn shadow read sampling để không tạo **double read load** hoặc làm tăng client latency. Không để shadow result làm thay đổi quyết định business khi chưa cutover.

Diff phải hiểu:

- Eventual consistency lag.
- Field normalization/format changes.
- TTL expiration.
- Intentional projection differences.
- Security/PII filters.
- Version boundaries.

Một khác biệt tạm thời vì target chưa bắt kịp có thể chấp nhận trong SLO; khác biệt ở **same source version** là cảnh báo nghiêm trọng hơn.



## 101. Canary reads

Một canary có thể chuyển 0,1% traffic đọc sang target, sau đó tăng 1%, 5%, 25%, 100% nếu metrics đạt.

Đo:

- Correctness/diff rate.
- p95/p99.
- Missing records.
- User-visible errors.
- Cache behavior.
- Target resource saturation.
- Regional/tenant breakdown.
- CDC lag/retention.

**Canary success rate không chứng minh mọi tenants/rare access patterns đúng**. Cần stratified sampling, representative queries và full validation trước khi đạt 100%.

## 102. Cutover gate

Không cutover chỉ vì scanner báo xong. Gate có thể yêu cầu:

~~~text
All assigned ranges: durable disposition achieved
No unresolved critical transform errors
CDC coverage continuous from snapshot boundary
CDC applied watermark >= chosen target
No expired retention / event gaps
Source-target diff within contract
No resurrection of deleted state
Production SLO within guardrail
Target capacity headroom validated
Rollback plan rehearsed
```

Nếu chỉ thiếu một metric quan trọng, hãy nêu **uncertainty/risk** chứ không tự giả định pass.

## 103. Chọn watermark cutover

Không có một timestamp `now()` hoàn hảo dùng cho mọi engines. Có thể dùng:

- Source log position per shard.
- CDC sequence/LSN/resume token.
- Aggregate sourceVersion.
- Broker offset per partition.
- Transaction commit watermark theo API.

Một partition offset 1000 không chứng minh đã bắt kịp partition khác. Nên lưu **vector/high-water map theo từng partition**, cùng semantics của snapshot boundary.

## 104. Kiểm full coverage

Không thể chỉ dùng:

~~~text
sourceCount == targetCount
```

vì:

- Hai bên có thể chứa các keys khác nhau nhưng cùng count.
- TTL may remove expired records.
- Target intentionally filters records.
- Source continues to change.
- Duplicates/missing cancel each other.
- Backfill/CDC can lag.

Các cách:

- Key-range reconciliation.
- Source-target key set checks per stable boundary.
- Hashes/digests normalized canonical projections.
- Sampled deep comparisons.
- Version watermark coverage.
- Missing-key/extra-key counts.
- Delete/tombstone consistency.
- Aggregate business totals.

## 105. Hash reconciliation phải định nghĩa canonicalization

Ví dụ JSON:

~~~json
{"a":1,"b":"x"}
~~~

và:

~~~json
{"b":"x","a":1}
~~~

có thể tương đương về business nhưng serialized bytes khác. Một digest có ích nếu:

- Field order canonical.
- Numbers/dates normalized.
- Unicode normalization defined.
- Null/missing distinguished theo contract.
- Excluded fields (migration metadata) documented.
- Encryption/nonce fields xử lý phù hợp.
- Projection transformations deterministic.

Không dùng hash của raw BSON/JSON ngẫu nhiên làm chứng minh divergence mà bỏ schema semantics.

## 106. Reconciliation khi source vẫn thay đổi

Một diff thực hiện giữa 10:00 và 11:00 có thể đọc source O-100 v8 rồi target O-100 v9, báo “khác” dù target đã mới hơn.

Nên đối soát dựa trên:

- Source version/snapshot watermark.
- Target applied version.
- Current source reads với bounded catch-up.
- Event coverage records.
- Per-key normalized canonical values.
- Cách phân loại target-newer/source-newer.
- Rerun sampling sau khi CDC catch-up.

**Không so những snapshots khác thời điểm như thể đó là một phép so tuyệt đối**. Nếu engine không có cross-store snapshot, cần thiết kế validation chấp nhận và giải thích những kết quả chuyển tiếp.

## 107. Xác nhận dữ liệu đã xóa

Đối soát deletion là phần khó nhất của backfill:

~~~text
Source no longer contains key K.
Target still has K.
```

Có thể do:

- Target apply delete chậm.
- Source TTL xóa nhưng stream không được capture.
- Key được move/rename.
- Scan/verify race.
- Target record được cố ý giữ làm archive.
- Một stale backfill đã hồi sinh K.

Cần định nghĩa **lifecycle contract** và nguồn deletion authority. Trong một số hệ, phải giữ tombstone/version trong target tới khi chắc chắn mọi historical mutations cũ đã hết khả năng replay.

## 108. Khi không có tombstone đầy đủ

Một source có retention xóa dữ liệu hoàn toàn và không có CDC history đủ dài. Không thể phân biệt:

~~~text
Key K never existed
Key K existed and was deleted last week
```

chỉ bằng đọc source hiện tại.

Các lựa chọn:

- Dựng full snapshot mới để làm source-of-truth key set tại mốc rõ.
- Reconcile target orphan keys một cách có kiểm soát.
- Dùng audit/outbox/deletion ledger từ thời điểm trước.
- Thực hiện planned read-only cutover window nếu có thể.
- Giữ tombstone trong future schema.
- Bổ sung data generation/revision.

Không tuyên bố incremental sync là lossless nếu **delete events đã mất và không có cách nhận diện deletion**.

## 109. Target indexes và migration mapping

Trong lúc backfill cần chọn thứ tự:

~~~text
Create target storage
Install correctness-critical constraints
Import/backfill
Build optional heavy indexes
Verify and catch up
Cut over
```

Nhưng nếu target phải phục vụ production reads/shadow reads trong backfill, một số indexes phải có sớm.

Một unique index là **guardrail correctness**; không nên bỏ nó chỉ vì tạo index chậm khi business invariant cần uniqueness. Đo bulk write overhead, index build IO, target query p99 và có lịch trình an toàn.

## 110. Schema evolution trong khi backfill

Một job chạy ba ngày nhưng deploy v2/v3 trong lúc đó:

~~~text
Day 1 transformer schema v2
Day 2 API starts writing schema v3
Day 3 worker resumes from old checkpoint
```

Có thể tạo mixed representations mà target không đọc được. Cần:

- Versioned transformer.
- Source/target schema generation.
- Backward-compatible reader.
- Checkpoint ghi transformer version.
- Plan upcast hoặc re-scan old outcomes.
- A migration run owner/approval for version switches.

Không đổi transform logic âm thầm trong cùng run nếu checkpoint không xác định phần dữ liệu nào đã được xử lý theo phiên bản nào.

## 111. Dữ liệu lỗi và poison records

Một record có thể:

- Thiếu field bắt buộc.
- Date sai định dạng.
- Foreign key reference không còn.
- Document size vượt target limit.
- PII không được phép đưa sang target.
- Trùng target key.
- Không thể decrypt bằng key cũ.
- Byte stream malformed.
- Source schema đã bị retire.

Không retry vô hạn. Lưu **durable error disposition** với source key, reason code, migration run, attempt count, schema version và reference đến log phù hợp, **không log plaintext PII**.

Khi sửa transformer, có đường **replay riêng những records lỗi**.

## 112. Quarantine không đồng nghĩa “hoàn tất thành công”

Một batch 1.000 records:

~~~text
950 applied
30 stale-version skipped legitimately
15 transient retries pending
5 malformed quarantined
```

Không báo “100% migrated” nếu 15 chưa có final disposition và 5 bị quarantine chưa được policy chấp nhận.

Phải phân biệt:

- `APPLIED`.
- `ALREADY_UP_TO_DATE`.
- `STALE_SKIPPED`.
- `DELETED_SKIPPED`.
- `RETRY_PENDING`.
- `QUARANTINED`.
- `FAILED_FATAL`.
- `UNKNOWN_RESULT`.

Cutover gate quyết định lỗi nào được chấp nhận, lỗi nào block.

## 113. Quarantine phải giữ được thông tin để phục hồi

Một bản ghi lỗi:

~~~json
{
  "runId": "bf-2026-11",
  "rangeId": "shard-04",
  "sourceKeyHash": "masked-hash-for-triage",
  "errorCode": "TARGET_SCHEMA_VALIDATION",
  "sourceVersion": 18,
  "transformVersion": 3,
  "attempts": 4,
  "quarantineAt": "2026-11-14T08:00:00Z"
}
~~~

Không nên lưu full PII trong exception message hay tracing labels. Khi replay, cần resolve source key một cách được ủy quyền và lấy **current authoritative source state** nếu contract yêu cầu latest, không mặc định sử dụng stale payload đã lỗi.

## 114. Backfill không tự gửi email/payment

Một transformer chạy cùng code domain với API có thể vô tình kích hoạt:

- Gửi email.
- Tính phí.
- Tạo invoice.
- Publish một business event mới.
- Kích hoạt push notification.
- Cập nhật external ledger.

Backfill thường phải phân biệt **rebuild state** với **new domain event**:

~~~text
Backfill mutation:
  "Represent existing history in new model"
Live command:
  "Perform a new business action"
```

Nếu target trigger CDC, cần `changeReason=BACKFILL` hoặc metadata tương đương để downstream consumers không coi nó là một payment mới. Không dùng cờ bypass bảo mật/authorization một cách thiếu kiểm soát.

## 115. Retrying một bulk request có thể tạo duplicate effects

Nếu target apply 70/100 items rồi connection mất trước khi client nhận response, retry toàn batch có thể:

- Ghi đè newer versions.
- Tạo duplicate inserts.
- Tăng index/storage work.
- Phát duplicate CDC events.
- Kích hoạt downstream side effects.

Cần conditional version guard, stable operation IDs và **idempotent sink**. `insertMany` hoặc `BatchWriteItem` với retries đơn giản không tự đủ correctness cho every workload.

## 116. Deduplication theo event ID

Một CDC sink có thể lưu inbox:

~~~text
if eventId not processed:
    apply state transition
    remember eventId
```

Để đúng, **apply và marking processed** cần một atomic boundary hoặc protocol tương đương. Nếu đánh dấu trước apply, crash mất event; nếu đánh dấu sau apply, crash có thể apply trùng.

Với target state updates có `sourceVersion`, một compare-and-set có thể làm việc idempotent mà không giữ vô hạn event IDs, tùy semantics; với `increment`/payment side effect vẫn cần cách dedupe riêng.

## 117. Nếu sự kiện delta đến sai thứ tự

Ví dụ:

~~~text
v10: balance += 10
v11: balance -= 5
```

Nếu nhận v11 trước v10 và chỉ áp “version lớn hơn”, sau đó bỏ v10, state có thể sai vì **delta** khác **full-state replacement**.

Cách xử lý:

- Full state snapshot theo version; hoặc
- Buffer các events thiếu predecessor.
- Track expected sequence vNext.
- Re-read source authoritative state khi gap.
- Rebuild from baseline + contiguous event log.

Version guard đủ cho **latest full-state overwrites** theo contract; không tự đủ cho mọi delta stream.

## 118. Partial update không giống full image

Một CDC event:

~~~json
{
  "entityId": "O100",
  "version": 12,
  "patch": { "status": "PAID" }
}
~~~

Không chứa `total`, `tenantId`, `items`. Nếu target chưa có baseline vì backfill chưa tới O100, apply patch có thể tạo incomplete record.

Cần:

- Backfill baseline trước patch sequence; hoặc
- Fetch current full source image theo version; hoặc
- Event log đủ để replay từ initial state; hoặc
- Buffer patches tới khi baseline tồn tại.

Không dùng patch event thay full-state upsert vô điều kiện.

## 119. Race giữa backfill và CDC về target

Nếu worker backfill và consumer CDC cùng ghi target:

~~~text
Backfill writes O100 version 10
CDC writes O100 version 11
```

**Ordering tại sink** phải bảo đảm v11 thắng dù network responses đảo thứ tự. Không dựa vào “CDC queue có priority cao hơn” vì async execution vẫn có thể làm backfill v10 commit sau.

Atomic version guard là một cách trong single source per-key ordering model.

## 120. Separate checkpoints cho scan và CDC

Một migration thường cần ít nhất:

~~~yaml
scan:
  rangeId: range-04
  lastDurablyAppliedKey: ...
  complete: false
cdc:
  partition: p-07
  lastDurablyAppliedPosition: ...
  running: true
```

Checkpoint scan và CDC không thể thay nhau vì:

- Scan cursor đi theo key range.
- CDC offset đi theo change log partition.
- Chúng có ordering và retention khác.
- Một pipeline có thể đã scan xong nhưng CDC còn lag.
- CDC có thể bắt kịp nhưng scan chưa bao phủ dữ liệu cũ.

Cutover gate cần cả hai.

## 121. Dual checkpoint không có global transaction

Nếu scan/CDC checkpointer ở database X và target ở database Y, việc ghi target và checkpoint không phải một atomic transaction chung trừ khi có cơ chế hỗ trợ.

Thiết kế thường chọn:

~~~text
At least once read/retry
+
Idempotent version-aware target apply
+
Checkpoint only after durable outcome
```

Chấp nhận replay sau crash, đổi lấy việc **không bỏ sót**. Nếu job yêu cầu exactly-once business effect, phải thiết kế cơ chế riêng đúng phạm vi.

---

## 122. Công thức ước tính thời gian backfill

Giả sử:

- \(N\): số records cần xử lý.
- \(\mu\): successful processing rate (records/s).
- \(p\): phần tỷ lệ records cần extra retry work (đơn giản hóa).
- \(T_{\text{pause}}\): tổng thời gian pause.

Ước lượng sơ bộ:

\[
T_{\text{nominal}}\approx \frac{N}{\mu}+T_{\text{pause}}
\]

Nhưng \(\mu\) phải là **committed/disposition rate ổn định**, đã bao gồm chi phí retries/throttling trong quan sát. Không nhân thêm một hệ số retry nếu \(\mu\) đã là rate thực tế sau retries.

Nếu job scan 30.000 items/s nhưng target chỉ apply 5.000 items/s, throughput thực của pipeline là **khâu thấp hơn**, và queue sẽ tăng nếu không backpressure.

## 123. Ví dụ thời gian hoàn tất với pause window

Có 36 triệu records, job chạy hiệu quả 1.500 successful records/s trong những lúc được phép, và chỉ chạy 8 giờ/ngày:

\[
36\,000\,000/1\,500=24\,000\text{ s}\approx 6.67\text{ h}
\]

Nếu mọi điều kiện thật giống giả định, job có thể hoàn thành trong một ngày làm việc 8 giờ. Nhưng thêm retry, non-uniform record size và source pressure có thể kéo dài sang ngày sau.

Đánh giá **schedule feasibility** từ sustained throughput và allowed windows, không từ peak rate.

## 124. Ước tính bytes/network

100 triệu records, 2 KiB/record:

\[
B_{\text{logical}}\approx 100\,000\,000\times2\text{ KiB}
\approx190.7\text{ GiB}
\]

Nếu source read đầy đủ document, target write lại fields, engine nhân replicas/indexes và retries thì physical IO/network có thể cao hơn nhiều.

Cần tính thêm:

- Serialization/metadata bytes.
- Compression ratio.
- Source read amplification.
- Cross-region egress.
- Target indexes.
- Replication fan-out.
- CDC duplicate/replay.
- Backups/checkpoints.

## 125. Capacity planning theo nguồn yếu hơn

Một pipeline:

~~~text
Source scan capacity allowed: 20,000 records/s
Transform capacity:           8,000 records/s
Target sustained apply:       5,000 records/s
CDC live flow:                1,000 records/s
```

Nếu target tổng capacity an toàn là 5.000 writes/s và live CDC cần 1.000, historical backfill budget có thể chỉ **4.000 writes/s** trước headroom khác.

Không phát 20.000/s vào unbounded worker queue rồi kỳ vọng average cuối ngày đúng. Phải rate-limit phù hợp **nút cổ chai** và dành capacity cho live changes.

## 126. Catch-up có thể không bao giờ đạt nếu target chậm hơn source

Khi source tạo 10.000 mutations/s nhưng CDC target chỉ apply tối đa 8.000/s, lag tăng:

\[
\Delta Q\approx(10\,000-8\,000)t
\]

Ngay cả khi historical scan đã xong, target **không thể bắt kịp** ở rate này.

Các hướng:

- Tăng target sustainable throughput.
- Giảm mutation work per event.
- Batch/bulk optimize có đúng idempotency.
- Scale partitions/workers nếu target có headroom.
- Giảm optional historical backfill load.
- Thay data model/partitioning.
- Chọn cutover window/quiescence hợp lệ nếu có thể.

Không bật cutover khi lag đang tăng không giới hạn.

## 127. CDC retention là đồng hồ đếm ngược

Giả sử change log giữ 24 giờ, nhưng oldest unapplied event hiện đã 20 giờ tuổi. Một outage/backfill pause tiếp 5 giờ có thể làm các events cần thiết không còn sẵn.

Cần alert:

- Oldest unprocessed age.
- Log retention horizon.
- Margin to retention expiry.
- Per-partition lag.
- Replay failure/invalid cursor.
- Target apply throughput.

Khi margin nguy hiểm, có thể cần **tạm ngừng historical scanning để dành capacity cho CDC** hoặc chuyển sang new snapshot plan, không cố chạy tiếp backfill.

## 128. Pause historical scan nhưng vẫn chạy CDC

Đây là một policy hữu ích:

~~~text
Production traffic high:
  historical backfill paused
  CDC consumer still processes live writes
```

Lợi ích: target vẫn tươi nếu CDC throughput đủ. Nhưng CDC cũng tiêu tốn source/target resources, nên phải đảm bảo **production SLO, CDC retention và target capacity**. Nếu target chậm nghiêm trọng, cả pipeline có thể cần isolate/circuit breaker cùng recovery plan.

## 129. Khi consumer lag về 0 vẫn chưa chứng minh đủ

Một consumer có thể “lag=0” vì:

- Offset bị reset bỏ qua records.
- Đã ACK events trước target commit.
- Broker retention đã xóa sự kiện.
- Một partition không được đăng ký.
- Log position không so sánh đúng generation.
- Transformer bỏ nhầm deleted events.
- Consumer ghi v11 trước v10 nhưng logic delta thiếu v10.

Cần **coverage evidence + reconciliation** thay vì chỉ một gauge lag.

---

## 130. Java: kiến trúc worker có thể resume

Một worker nên có các thành phần:

~~~java
public interface BackfillSource {
    Page readNext(RangeAssignment assignment, Cursor cursor);
}

public interface BackfillTransformer {
    TargetMutation transform(SourceRecord source);
}

public interface TargetApplier {
    ApplyOutcome applyIfNewer(TargetMutation mutation);
}

public interface CheckpointStore {
    Checkpoint load(String rangeId);

    boolean advanceIfOwner(
        String rangeId,
        long assignmentGeneration,
        Cursor durablyAppliedCursor);
}
~~~

Các interfaces/types minh họa, chưa biên dịch thành ứng dụng đầy đủ. Mục tiêu là tách:

- Source scan.
- Deterministic transformation.
- Atomic/version-aware target apply.
- Durable range checkpoint.
- Worker assignment ownership.
- Rate/concurrency controls.
- Error classification.

## 131. Java: skeleton vòng scan có checkpoint

~~~java
public void processRange(
        RangeAssignment assignment,
        BackfillSource source,
        BackfillTransformer transformer,
        TargetApplier target,
        CheckpointStore checkpoints,
        BackfillController controller) {

    Checkpoint cp = checkpoints.load(assignment.rangeId());
    Cursor cursor = cp.cursor();

    while (!cp.completed()) {
        controller.awaitBudget();    // bounded wait / pause-aware
        Page page = source.readNext(assignment, cursor);

        if (page.items().isEmpty() && page.endOfRange()) {
            checkpoints.markCompleteIfOwner(
                assignment.rangeId(),
                assignment.generation(),
                cursor
            );
            break;
        }

        boolean allSettled = true;
        for (SourceRecord record : page.items()) {
            TargetMutation mutation = transformer.transform(record);
            ApplyOutcome outcome = target.applyIfNewer(mutation);

            if (!outcome.isDurablySettled()) {
                allSettled = false;
                controller.recordPendingOrFailed(record, outcome);
            }
        }

        if (!allSettled) {
            // Retry/reconcile page before passing the cursor;
            // do not silently skip failed records.
            controller.pauseOrScheduleRetry(assignment, page);
            return;
        }

        Cursor next = page.nextCursor();
        if (!checkpoints.advanceIfOwner(
                assignment.rangeId(),
                assignment.generation(),
                next)) {
            throw new OwnershipLostException();
        }

        cursor = next;
        cp = checkpoints.load(assignment.rangeId());
    }
}
~~~

Đây là **pseudocode Java**: domain types/methods chưa được định nghĩa. Hợp đồng `isDurablySettled` phải phân biệt `APPLIED`, `ALREADY_UP_TO_DATE`, `STALE_SKIPPED`, `QUARANTINED` theo migration policy; `unknown result` cần reconciliation. Khi page rỗng nhưng chưa end, tiếp tục theo cursor, không tự suy hết range.

## 132. Java: một vòng adaptive rate controller

Pseudocode:

~~~java
public void adjust(ProductionMetrics m) {
    if (m.correctnessIncident()) {
        paused = true;
        return;
    }

    if (m.checkoutP99TooHigh()
            || m.targetThrottlingHigh()
            || m.replicaLagTooHigh()) {
        currentRate = Math.max(minRate, currentRate * 0.5);
        cooldownUntil = monotonicNowPlusCooldown();
    } else if (m.stableSloForMultipleWindows()
            && cooldownElapsed()) {
        currentRate = Math.min(maxRate, currentRate + increment);
    }

    rateLimiter.updateRate(currentRate);
}
~~~

Pseudocode có monitoring/instrumentation assumptions. Không dùng `Instant.now()` để đo elapsed cooldown trong một JVM; dùng monotonic duration. Phải giới hạn rate **global across workers** khi cần, không chỉ cục bộ.

## 133. Java: transient vs permanent error classifier

Một outcome model:

~~~java
public enum ApplyOutcome {
    APPLIED,
    ALREADY_UP_TO_DATE,
    STALE_SKIPPED,
    VERSION_CONFLICT,
    RETRYABLE_THROTTLED,
    RETRYABLE_NETWORK_FAILURE,
    UNKNOWN_COMMIT,
    INVALID_SOURCE_RECORD,
    UNAUTHORIZED,
    FATAL_SCHEMA_MISMATCH
}
~~~

Mỗi outcome có policy:

- `APPLIED`/`ALREADY_UP_TO_DATE`: settled.
- `STALE_SKIPPED`: settled nếu version ordering đã được chứng minh.
- `VERSION_CONFLICT`: reread/reconcile.
- Throttle/network: bounded retry.
- `UNKNOWN_COMMIT`: query/reconcile target outcome.
- Invalid record: quarantine/repair queue.
- Unauthorized/schema mismatch: pause/fail, không retry vô hạn.

Không “catch Exception → sleep → retry” cho tất cả.

## 134. Java: không log plaintext nhạy cảm

Một record fail do invalid BSON/JSON có thể chứa PII.

Nên log:

~~~text
runId, rangeId, maskedSourceKey, sourceVersion
transformVersion, errorCode, elapsedMs
```

Không log toàn bộ `SourceRecord`/`TargetMutation`, credential, encryption key, customer email hoặc raw API response để “dễ debug”.

Đảm bảo quarantine/error storage cũng có encryption/access control/retention phù hợp.

---

## 135. Telemetry tối thiểu của backfill

| Nhóm | Chỉ số |
|---|---|
| Scan | records/bytes read, page latency, cursor errors |
| Apply | success/stale/duplicate/conflict, write RTT, bytes |
| Rate | offered RPS, allowed RPS, actual completed RPS |
| Queue | pending depth, oldest age, worker in-flight |
| Error | throttle, timeout, unknown commit, poison records |
| Data correctness | missing/extra keys, mismatched versions, delete resurrection |
| CDC | per-shard lag, oldest unapplied age, retention margin |
| Source | CPU, cache, disk I/O, replica lag, p99 |
| Target | write latency, capacity, compaction, index backlog |
| API | p95/p99, 5xx, successful throughput, timeouts |
| Cost | RCU/WCU, bytes, egress, worker spend |
| Progress | ranges done, settled keys, remaining ranges |
| Control | rate limit state, pauses, resumes, operator actions |

Một số managed services không có host CPU metric; dùng service capacity/throttling API thay vì bịa số.

## 136. Prometheus metrics gợi ý

Ví dụ tên metric do ứng dụng tự định nghĩa:

~~~text
backfill_records_total{runId,phase,outcome}
backfill_bytes_total{runId,direction}
backfill_page_duration_seconds_bucket{source,le}
backfill_target_apply_duration_seconds_bucket{target,le}
backfill_inflight_requests{stage}
backfill_pending_queue_depth{stage}
backfill_oldest_pending_age_seconds{stage}
backfill_rate_limit_units_per_second{stage}
backfill_throttle_total{sourceOrTarget,reason}
backfill_checkpoint_age_seconds{rangeClass}
backfill_reconciliation_mismatch_total{type}
backfill_cdc_oldest_age_seconds{pipeline}
backfill_paused{reasonClass}
```

Không dùng raw user/tenant keys làm labels có cardinality cực cao. Nếu hàng chục nghìn `runId` cũ không được cleanup, label set cũng có thể phình; kiểm soát retention/metrics lifecycle.

## 137. PromQL: production p99

Với classic histogram:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, route) (
    rate(http_request_duration_seconds_bucket{
      route=~"/checkout|/orders"
    }[5m])
  )
)
~~~

Đây là ví dụ metric naming; histogram buckets, labels và units phải khớp thực tế. Không lấy trung bình p99 từ các pods rồi dùng làm p99 toàn service.

## 138. PromQL: backfill settled rate

~~~promql
sum by (outcome) (
  rate(backfill_records_total{
    phase="apply"
  }[5m])
)
~~~

Không coi mọi outcomes đều là migrated writes. `STALE_SKIPPED` có thể là xử lý hợp lệ nhưng không làm target thay đổi; `RETRY_PENDING` không được tính settled.

Cần một counter định nghĩa **successful durable disposition rate** riêng hoặc phép lọc outcome rõ.

## 139. PromQL: CDC lag tuổi

~~~promql
max by (pipeline) (
  backfill_cdc_oldest_age_seconds
)
~~~

Dùng max để không che partition bị kẹt. Ngoài ra phải alert khi **retention margin** quá thấp, không chỉ khi record count lớn.

## 140. PromQL: count các lỗi throttling

~~~promql
sum by (sourceOrTarget,reason) (
  rate(backfill_throttle_total[5m])
)
~~~

Đối chiếu throttling với production p99 và target capacity. Một vài throttles do controller chủ động tạm chờ có ý nghĩa khác lỗi throttle từ managed service; metric labels phải tách.

## 141. Thành công không chỉ là completion rate

Trong overload, job có thể tăng `processed records/s` nhờ bỏ qua lỗi. Dashboard cần báo:

- Records read.
- Records transformed.
- Records durably applied.
- Records confirmed already-up-to-date.
- Records skipped legitimately.
- Records quarantined/failed.
- Unknown outcomes.
- Remaining coverage ranges.

Một “throughput 100.000/s” không có outcome breakdown là không đáng tin để quyết định cutover.

## 142. SLO guardrail và canary

Một rollout có thể chia:

~~~text
Canary range: 0.1% data
Measure 30 min under representative load
Then: 1%, 5%, 25%, 100% of allowed backfill budget
```

Các phần trăm là **lịch trình minh họa**, không phải chuẩn. Với 0,1% random sample có thể bỏ qua large tenants/hot partitions, nên cần stratified ranges và có bài test riêng trên worst-case data.

## 143. Ngưỡng dừng

Một job cần pause nếu:

- Production p99 vượt critical SLO theo policy.
- Error budget bị tiêu thụ quá nhanh.
- Source replication lag tăng liên tục.
- Target throttling kéo dài.
- CDC retention có nguy cơ hết.
- Unknown commit outcomes tăng.
- Fencing/checkpoint ownership không tin cậy.
- Data correctness mismatch nghiêm trọng.
- Encryption/key/security policy không đáp ứng.

Throttling giúp chống resource overload; **lỗi correctness có thể đòi dừng ngay** thay vì chỉ giảm rate.

## 144. Một thí nghiệm controlled load

Để biết backfill có phá production hay không:

1. Đo baseline traffic thật trên staging đại diện hoặc canary production được phép.
2. Ghi read/write mix, cache hit, p95/p99, CPU/IO, cost.
3. Chạy backfill với rate rất thấp.
4. Tăng từng bước, giữ mỗi bước đủ lâu để thấy compaction/lag.
5. Ghi production p99 và successful RPS.
6. Quan sát target writes, retries, CDC age.
7. Thử giảm rate/pause; hệ có hồi phục không?
8. Chọn rate bền vững có headroom.
9. Test failed shard/target throttle.
10. Ghi lại config/version và rollback gate.

Không tự chạy load test gây failure injection trên production nếu chưa được phép và không có kill switch.

## 145. Open-loop và closed-loop test

**Closed-loop** load generator gửi request mới sau khi response trước hoàn tất, nên khi hệ chậm, offered load có thể giảm, làm sai kết luận về capacity.

**Open-loop** phát theo arrival schedule định trước, giúp thấy queue tăng khi server saturated nhưng cần kiểm client/backlog và **coordinated omission**.

Khi đo tác động backfill, cần biết workload đang giữ **offered RPS thực** hay tự giảm, tránh kết luận “API vẫn khỏe” trong khi user traffic đã bị shed.

## 146. Cache cold và compaction debt

Một canary nhỏ có thể thấy mọi records trong cache. Sau 5 giờ, scan làm cache churn và compaction debt tăng, p99 mới xấu.

Thử cả:

- Cold cache.
- Warm production cache.
- Long soak.
- Index build.
- Secondary catch-up.
- Recovery after pause.
- Repeated retry bursts.
- Target full/near storage watermark.

Đừng chọn tốc độ dựa trên 10 phút đầu tiên mà không xem background maintenance work.

## 147. Kịch bản sự cố: source khỏe, target chậm

Triệu chứng:

~~~text
Source scan 10,000 items/s
Target applies 2,000 items/s
Worker queue grows
CDC lag increases
```

Hành động:

- Throttle source reads xuống near sustainable apply rate.
- Dành priority cho live CDC.
- Tối ưu target key distribution/indexes.
- Kiểm throttling/IO/compaction.
- Không tăng workers vô hạn.
- Theo dõi oldest queue age và retention.

Nếu source scan nhanh không thể **làm target mạnh hơn**.

## 148. Kịch bản sự cố: production p99 tăng

Triệu chứng:

~~~text
Checkout p99: 120ms -> 700ms
Database CPU: 55% -> 95%
Backfill scan started 5 minutes earlier
```

Hành động:

1. Pause/throttle backfill theo guardrail.
2. Quan sát p99/CPU/IO hồi phục không.
3. Tách source reads, write amplification, index/cache eviction.
4. Kiểm queries mới có full scan/secondary spill không.
5. Khởi động lại ở lower rate khi ổn định và approved.
6. Ghi incident/limit mới.

Đây là **giả thuyết tương quan**; không bỏ qua những thay đổi traffic/deploy khác cùng lúc.

## 149. Kịch bản sự cố: checkpoint bị ghi quá sớm

~~~text
Worker reads page P.
Worker checkpoints P as done.
Only half the page reaches target.
Worker crashes.
Resume starts after P.
```

Hậu quả: **missing records**. Cần sửa ordering checkpoint-after-durable-disposition và chạy **reconciliation/replay** cho phạm vi có nguy cơ bị skip. Không chỉ restart worker với cùng cursor cũ.

## 150. Kịch bản sự cố: CDC token hết hạn

Backfill scan hoàn thành sau 30 giờ, stream giữ 24 giờ và consumer đã lag quá retention.

Không thể tuyên bố no-gap nếu token không còn. Cần:

- Pause cutover.
- Inventory thời gian/partitions bị gap.
- Rebuild/reconcile từ snapshot mới hoặc nguồn event history khác.
- Thiết kế lại capacity/retention.
- Verify lại coverage.

“Consumer lag 0 sau offset reset” **không phải đã phục hồi lost events**.

## 151. Kịch bản sự cố: tombstone bị xóa quá sớm

Deleted item version 50 có tombstone. TTL dọn tombstone khi backfill version 49 vẫn đang pending.

Backfill có thể hồi sinh version 49 vì target không còn record/version để chặn.

Cần:

- Retain tombstones qua replay horizon.
- Gắn generation/epoch để tránh reuse identity.
- Quarantine stale mutation nếu history đã hết.
- Reconcile target orphan keys.
- Không dùng TTL cleanup như một cơ chế xóa ordering history tùy tiện.

## 152. Kịch bản sự cố: background job tạo event nghiệp vụ mới

Backfill ghi 10 triệu orders vào target; consumer thấy 10 triệu `OrderCreated` events và gửi email.

Nguyên nhân: không tách **state reconstruction** và **business command**.

Giải pháp:

- Event contract phân biệt `BACKFILL_REPRESENTATION` với domain events.
- Downstream dedupe theo stable operation IDs.
- Disabled/safe side effects theo migration mode có kiểm soát.
- Không publish external notifications từ import path.
- Test toàn event chain trong staging.

## 153. Kịch bản sự cố: target chỉ partial write

DynamoDB `BatchWriteItem` trả `UnprocessedItems`; worker vẫn checkpoint toàn page.

Hậu quả: missing items. Cần retry unprocessed items có bounded backoff, durable disposition, idempotency và checkpoint sau thành công.

Nếu cần condition theo sourceVersion, **đừng đổi sang BatchWriteItem vô điều kiện chỉ để nhanh**.

## 154. Kịch bản sự cố: schema đổi giữa run

Worker v1 viết target schema2, sau deploy worker v2 viết schema3. Validation phát hiện record mixed format.

Cần:

- Stop/version-pin run.
- Dựng mixed-format upgrade/backfill plan.
- Checkpoint-transformer association.
- Versioned decoder.
- Re-run affected ranges nếu cần.
- Không rewrite target vô điều kiện khi live writes đã tới version mới.

## 155. Kịch bản sự cố: source key được đổi

Record `tenantA#U1` chuyển sang `tenantB#U1`, nhưng historical scan đã copy key cũ và CDC chỉ tạo key mới.

Cần đảm bảo event contract biểu diễn **delete old + create new** hoặc có migration mapping. Sau cutover, tránh user nhìn thấy cả hai tenants hoặc dữ liệu xuyên tenant.

Tenant migration là **authorization/data isolation boundary**, không chỉ chuyện rename key.

---

## 156. Runbook trước khi bắt đầu backfill

~~~text
PREPARE
  Define source of truth, target and correctness invariants.
  Document schema/key mapping and transformer version.
  Define snapshot/CDC overlap boundary and no-gap proof.
  Capture live traffic and backend SLO baseline.
  Record index/replication/consistency configuration.
  Estimate data volumes, RCU/WCU/IO and cost.
  Configure concurrency, rate, queue and retry budgets.
  Set per-shard/tenant limits and CDC retention alerts.
  Prepare durable checkpoints and failure quarantine.
  Verify idempotent target apply and tombstones.
  Test crash, pause, retry and malformed records.
  Ensure pause/kill switch and rollback operators.
  Obtain required approvals and change window.

START
  Enable change capture with persistent checkpoint.
  Start small canary ranges.
  Observe production p99/CPU/IO and target capacity.
  Increase only within validated headroom.
~~~

Không bắt đầu scan toàn bảng khi chưa có đường dừng và chưa biết mức load của traffic đang phục vụ.

## 157. Runbook khi production vượt SLO

~~~text
TRIGGER
  Production p99/error rate crosses backfill guardrail.

IMMEDIATE
  Pause new historical scan / target writes as designed.
  Preserve durable checkpoints, CDC capture and event logs.
  Identify affected shards, collection, operation classes.
  Check source CPU/IO/cache and target throttle/compaction.
  Check CDC oldest event age and retention margin.

RECOVER
  Restore production headroom; reduce background load.
  Verify in-flight/unknown outcomes.
  Reconcile any partial page and stale writes.
  Restart at lower bounded rate if approved.
  Observe steady-state and gradual rate increase.

CLOSE
  Record root cause, safe rate, changes and evidence.
  Update guardrails, alerts and runbook.
~~~

Không tiếp tục import chỉ vì deadline migration nếu đang ảnh hưởng availability hoặc correctness nghiêm trọng.

## 158. Runbook khi backfill có dữ liệu sai

~~~text
TRIGGER
  Missing record, stale overwrite, delete resurrection,
  version conflict, schema mismatch or cross-tenant leak.

CONTAIN
  Stop affected range / target writes and cutover.
  Preserve source truth, checkpoints and change logs.
  Stop downstream effects caused by imported records.
  Revoke unsafe read routing if necessary.

DIAGNOSE
  Compare authoritative source version and target version.
  Check snapshot/CDC boundary, missing events and ordering.
  Check tombstone retention and source ID generation.
  Examine transform version, concurrency and checkpoint.
  Identify affected tenants/ranges.

REPAIR
  Rebuild/replay affected scope from trusted source.
  Use conditional/idempotent apply, not blind overwrite.
  Re-run reconciliation and business invariant checks.
  Verify no event gaps or side effects remain.

RESUME
  Resume only after correction and signoff.
  Record rollback/cutover decision.
~~~

Một mismatch có thể là lỗi privacy/authorization; không chỉ là chênh lệch số đếm.

---

## 159. Bài tập A — Ước tính thời gian scan

Có 100 triệu records, tốc độ **durable processing** ổn định là 2.000 records/s.

**Hỏi:** thời gian lý tưởng tối thiểu theo mô hình?

**Hướng giải:** \(100\,000\,000/2000=50\,000\) giây, khoảng 13,9 giờ; chưa kể pause, catch-up, retries, verification.

## 160. Bài tập B — Resource budget

Source chịu được 10.000 read units/s trong SLO; production đang dùng 9.700 units/s, reserve 200 units/s.

**Hỏi:** budget tối đa sơ bộ cho backfill?

**Hướng giải:** \(10\,000-9\,700-200=100\) units/s, không phải 2.000 units/s chỉ vì đã đặt quota cố định khi thấp điểm.

## 161. Bài tập C — Concurrency nhiều pods

Có 12 worker pods, mỗi pod cho tối đa 16 target requests in-flight.

**Hỏi:** global max theo giới hạn local?

**Hướng giải:** 192 in-flight, chưa tính requests khác và retries. Phải theo dõi tổng khi autoscale.

## 162. Bài tập D — Historical overwrite

Backfill đọc Order v7 `PENDING`; CDC đã áp v8 `PAID`.

**Hỏi:** target nên làm gì khi nhận backfill v7?

**Hướng giải:** skip qua atomic version guard, không overwrite v8. Với delta events cần thêm contiguous-sequence logic.

## 163. Bài tập E — Version guard không atomic

Hai workers cùng đọc target v5; một ghi v8 rồi một ghi v7.

**Hỏi:** lỗi gì xảy ra nếu kiểm version trong Java rồi `save` vô điều kiện?

**Hướng giải:** lost update/stale overwrite. Dùng conditional mutation tại target.

## 164. Bài tập F — Delete resurrection

CDC áp tombstone v10 rồi xóa hẳn target record; backfill v9 đến sau.

**Hỏi:** rủi ro?

**Hướng giải:** v9 được tạo lại nếu không còn tombstone/version để fence. Cần giữ deletion version qua replay horizon.

## 165. Bài tập G — Reset TTL

Session trên source hết hạn sau 15 phút nữa. Backfill target tạo TTL mới 1 giờ.

**Hỏi:** đúng không?

**Hướng giải:** không nếu contract là absolute expiry cũ. Giữ `expiresAt` và chuyển unit đúng.

## 166. Bài tập H — Pagination `skip`

Một MongoDB scan dùng `skip(5_000_000)` trên collection đang có inserts/deletes.

**Hỏi:** vấn đề?

**Hướng giải:** offset lớn tốn work, concurrent mutation có thể gây duplicate/missing, không có snapshot guarantee. Xem stable keyset/range scan + CDC.

## 167. Bài tập I — Stable keyset chưa đủ

Một item mới được tạo với key **nhỏ hơn** last scanned key.

**Hỏi:** keyset scan có tự nhìn thấy nó không?

**Hướng giải:** không chắc; cần overlapping CDC hoặc snapshot boundary khác bảo đảm không gap.

## 168. Bài tập J — Checkpoint trước target write

Worker lưu cursor đã qua page P rồi mới ghi target, crash sau 30% batch.

**Hỏi:** hậu quả?

**Hướng giải:** resume có thể bỏ sót 70% P. Chỉ checkpoint sau durable disposition, và cho replay idempotent.

## 169. Bài tập K — Partial batch

Batch 100 items: 60 applied, 20 `UnprocessedItems`, 20 condition-skipped đúng phiên bản.

**Hỏi:** page đã checkpoint được chưa?

**Hướng giải:** chưa, 20 unprocessed cần retry/reconcile. Các condition-skips chỉ settled nếu policy chứng minh incoming stale/duplicate.

## 170. Bài tập L — Overlap CDC

Snapshot tại 10:00, CDC bắt đầu 10:05.

**Hỏi:** có thể bảo đảm không mất writes từ 10:00–10:05 không?

**Hướng giải:** không từ thông tin này; cần snapshot-log boundary hoặc capture trước và replay overlapping events.

## 171. Bài tập M — Hết CDC retention

Stream giữ 24 giờ; consumer bị ngưng 30 giờ.

**Hỏi:** chỉ resume bằng token cũ có được?

**Hướng giải:** token có thể hết hiệu lực và events không còn. Cần rebuild/reconcile/new snapshot theo API và proof no-gap.

## 172. Bài tập N — CDC delta đảo thứ tự

Target có baseline v10; nhận delta v12 rồi v11.

**Hỏi:** rule “chỉ áp version lớn hơn” có đủ cho delta không?

**Hướng giải:** không. Phải theo contiguous sequence hoặc re-read full state; không bỏ v11 nếu v12 phụ thuộc v11.

## 173. Bài tập O — Same version, different payload

Hai records cùng sourceVersion 8 nhưng payload khác nhau.

**Hỏi:** nên chọn record đến sau?

**Hướng giải:** không tự động; đó là divergence cần quarantine và xác minh source version/transformer/generation.

## 174. Bài tập P — Replica lag

Primary production khỏe, secondary dùng cho backfill có apply lag tăng từ 1 lên 600 giây.

**Hỏi:** có thể nói source không bị ảnh hưởng không?

**Hướng giải:** chưa. Secondary lag có thể ảnh hưởng read freshness, failover và retention; throttle/stop và kiểm member health.

## 175. Bài tập Q — Cache pollution

Backfill scan dữ liệu 300 GiB qua cache 30 GiB; production hot set 20 GiB.

**Hỏi:** p99 reads có thể xấu đi dù CPU không đầy?

**Hướng giải:** có, cache eviction có thể biến hits thành disk reads; đo page faults/cache hit/IO.

## 176. Bài tập R — Rate và concurrency

Job giới hạn 1.000 requests/s nhưng mỗi request mất 10 giây.

**Hỏi:** chỉ rate limit đã đủ giới hạn in-flight chưa?

**Hướng giải:** không, concurrency có thể tăng lớn. Cần max in-flight/queue/deadline.

## 177. Bài tập S — Hysteresis

Controller pause khi p99 >250 ms, resume ngay khi p99 <=250 ms.

**Hỏi:** rủi ro?

**Hướng giải:** oscillation/bật-tắt liên tục. Cần ổn định qua nhiều windows và cooldown.

## 178. Bài tập T — DynamoDB Scan

`ConsistentRead=true` trên một DynamoDB Scan nhiều pages.

**Hỏi:** có tạo point-in-time snapshot toàn bảng không?

**Hướng giải:** không. Cần PITR export/boundary hoặc CDC reconciliation theo supported service semantics.

## 179. Bài tập U — DynamoDB `Limit`

Scan có filter trả 10 items nhưng đánh giá hàng nghìn items.

**Hỏi:** có thể tính capacity chỉ từ 10 returned items không?

**Hướng giải:** không. Xem ScannedCount/ConsumedCapacity và item sizes.

## 180. Bài tập V — DynamoDB BatchWriteItem

Target yêu cầu reject incoming version cũ; nhóm dùng BatchWriteItem để tăng throughput.

**Hỏi:** có điều kiện per item phù hợp không?

**Hướng giải:** BatchWriteItem không hỗ trợ condition per write; cần conditional operations/transaction hoặc kiến trúc khác bảo vệ version.

## 181. Bài tập W — MongoDB `updateLookup`

Change Stream phát update; consumer dùng fullDocument lookup.

**Hỏi:** fullDocument có chắc là ảnh state đúng lúc mutation vừa xảy ra không?

**Hướng giải:** không mặc định dưới concurrent updates; phải xem semantics và version guard.

## 182. Bài tập X — Cassandra timestamp

Backfill một state cũ nhưng gán write timestamp lớn hơn live writes.

**Hỏi:** nguy cơ?

**Hướng giải:** LWW reconciliation có thể ưu tiên stale backfill. Cần timestamp/write policy và authoritative version semantics đúng.

## 183. Bài tập Y — Cassandra partition scan

Một scan dùng CQL `ALLOW FILTERING` trên table hàng tỷ rows.

**Hỏi:** có nên dùng như mặc định?

**Hướng giải:** không. Xem token/partition ranges, connector/export tools và resource throttling phù hợp.

## 184. Bài tập Z — Redis SCAN

Redis SCAN trả một key hai lần trong một iteration.

**Hỏi:** đó có phải lỗi script không?

**Hướng giải:** SCAN không hứa no-duplicates; sink phải idempotent và scan không được coi consistent snapshot.

## 185. Bài tập AA — Redis TTL

Source Redis PTTL còn 20.000 ms; worker target dùng `SET EX 3600`.

**Hỏi:** target lifetime có đúng không?

**Hướng giải:** không nếu giữ original expiry. Phải bảo toàn remaining/absolute expiry theo contract.

## 186. Bài tập AB — Backfill tạo email trùng

Target document insert trigger `OrderCreated`; job import 1 triệu orders cũ.

**Hỏi:** chuyện gì xảy ra?

**Hướng giải:** downstream có thể gửi email/notification trùng. Phân biệt rebuild state với new business event, idempotency và side-effect suppression được thiết kế.

## 187. Bài tập AC — Full scan hoàn tất, CDC lag tăng

Scanner báo 100%, target CDC oldest age tăng.

**Hỏi:** cutover được không?

**Hướng giải:** chưa; còn live mutations chưa áp và có thể gần retention limit.

## 188. Bài tập AD — Count bằng nhau

Source và target có cùng 1 triệu records nhưng 100 IDs khác nhau.

**Hỏi:** migration đúng chưa?

**Hướng giải:** chưa; equal counts không chứng minh key set/canonical state giống nhau. Cần per-key/range reconciliation.

## 189. Bài tập AE — Hash JSON khác field order

Hai JSON objects có cùng fields/values nhưng thứ tự field khác.

**Hỏi:** raw serialized hash có nhất thiết bằng không?

**Hướng giải:** không; cần canonical encoding/normalization trước khi hash.

## 190. Bài tập AF — Rename tenant key

User chuyển từ tenant A sang B; CDC chỉ tạo new target key mà không delete old key.

**Hỏi:** nguy cơ?

**Hướng giải:** duplicate/cross-tenant data exposure. Cần move semantics và xóa key cũ có version/authorization.

## 191. Bài tập AG — Dual-write partial success

API ghi source success, target timeout.

**Hỏi:** đã bảo đảm data nhất quán chưa?

**Hướng giải:** chưa. Cần outbox/retry/reconciliation, không xem hai calls là atomic.

## 192. Bài tập AH — Source chuyển authority

Từ DB cũ sang DB mới, nhóm chuyển writes ngay rồi cho phép rollback bằng cách đổi endpoint về DB cũ.

**Hỏi:** còn thiếu gì?

**Hướng giải:** DB cũ không tự có writes mới. Cần reverse CDC/replay, dual-write consistency protocol hoặc controlled failback có proof.

## 193. Bài tập AI — Shadow reads

Shadow read target làm API gọi thêm một query cho mọi request, source đang gần capacity.

**Hỏi:** làm sao giảm tác động?

**Hướng giải:** sampling/bounded asynchronous shadow reads, quotas và separate failure handling; không làm user-facing response chờ shadow result.

## 194. Bài tập AJ — Poison record

Một malformed record retry vô hạn và chặn range.

**Hỏi:** đúng không?

**Hướng giải:** không. Quarantine có reason/secure metadata, replay sau sửa; chỉ settle checkpoint theo policy.

## 195. Bài tập AK — Worker generation

A xử lý range R generation 5, bị pause; B nhận generation 6. A resume ghi checkpoint cũ.

**Hỏi:** cần gì?

**Hướng giải:** conditional checkpoint update theo owner/generation để A không làm lùi/nhảy tiến độ.

## 196. Bài tập AL — Migration schema version

Job chạy từ schema v2 sang v3 giữa tiến độ, checkpoint không lưu transform version.

**Hỏi:** khó khăn gì?

**Hướng giải:** không biết records đã dùng transformer nào; cần version pin/checkpoints và strategy upcast/re-run.

## 197. Bài tập AM — Unknown commit

Target write timeout sau khi nhận request.

**Hỏi:** có chắc record chưa ghi?

**Hướng giải:** không. Dùng idempotency/version state query/reconciliation trước khi retry side effects.

## 198. Bài tập AN — Production p99 vượt SLO

Sau khi tăng backfill từ 500 lên 5.000 writes/s, checkout p99 vượt SLO.

**Hỏi:** ưu tiên?

**Hướng giải:** pause/throttle ngay theo guardrail, xem resource metrics và retries; không giữ tốc độ chỉ vì gần deadline.

## 199. Bài tập AO — Target cannot catch up

Source tạo live mutations 10.000/s, target chỉ áp 8.000/s.

**Hỏi:** có thể chờ đủ lâu để lag bằng 0 không?

**Hướng giải:** không nếu rates giữ nguyên; backlog tăng 2.000/s. Phải nâng capacity/giảm work hoặc có controlled quiescence.

## 200. Bài tập AP — Per-shard overload

Cluster average CPU 40%, một partition nhận toàn bộ write traffic và bị throttled.

**Hỏi:** global rate limit có đủ không?

**Hướng giải:** không chắc; cần per-partition/tenant caps và key distribution redesign.

## 201. Bài tập AQ — Target search visible

Bulk indexing trả success nhưng search query chưa thấy documents ngay.

**Hỏi:** đây là failed write?

**Hướng giải:** chưa thể kết luận; có refresh/visibility semantics riêng. Đo commit-to-search-visible lag.

## 202. Bài tập AR — Cron backfill không có checkpoint

Job restart sau outage và bắt đầu lại từ đầu. Target ghi 50% dữ liệu rồi.

**Hỏi:** việc chạy lại có an toàn?

**Hướng giải:** chỉ khi apply idempotent/version-guarded; mất checkpoint làm chậm và tăng load, cần checkpoint durable.

---

## 203. Checklist trước khi chạy backfill

**Hợp đồng dữ liệu và concurrency**

1. Đã xác định source of truth chưa?
2. Đã xác định target dùng cho read/write gì chưa?
3. Đã xác định stable source key/target key chưa?
4. Có data classification, tenant isolation và privacy filters không?
5. Transformer có deterministic và versioned không?
6. Có immutable business timestamps và migration metadata riêng không?
7. Có sourceVersion/generation rõ theo aggregate không?
8. Có atomic version guard tại target không?
9. Có xử lý version bằng nhau nhưng payload khác không?
10. Có delete/tombstone version đủ retention không?
11. Có bảo toàn TTL/absolute expiry không?
12. Có schema migration đọc hiểu old/new formats không?
13. Có xử lý moving/renamed keys không?
14. Có kiểm transaction scope và partial commit không?
15. Có ngăn backfill kích hoạt external business side effects không?

**Snapshot, CDC và scan**

16. Snapshot có consistency boundary thực không?
17. CDC bắt đầu không gap với snapshot chưa?
18. CDC retention có đủ thời gian chạy/phục hồi không?
19. Có per-partition stream watermark không?
20. Có xử lý CDC duplicates và out-of-order không?
21. Event type full-state/patch/delta được phân biệt chưa?
22. Có xử lý delete/TTL mutations trong change capture không?
23. Có recovery path khi resume token hết hạn không?
24. Scan có range/page model ổn định không?
25. Có tránh offset/skip pagination lớn không?
26. Có nhận thức keyset scan không tự bao phủ live inserts không?
27. Các ranges có no-gap/no-overlap coverage không?
28. Có split hot partitions/ranges không?
29. Có durable per-range checkpoint không?
30. Checkpoint chỉ advance sau target durable disposition không?
31. Có fencing worker ownership/generation không?
32. Có test crash ngay trước/sau checkpoint không?
33. Có replay dedupe/idempotency không?
34. Có quarantine/replay cho malformed records không?

**Bảo vệ tải đang phục vụ**

35. Có baseline production p95/p99, error, successful RPS không?
36. Có source CPU/IO/cache/replica lag metrics không?
37. Có target write latency/throttling/compaction metrics không?
38. Có CDC oldest age/retention margin metrics không?
39. Có token/rate limit theo work cost không?
40. Có max in-flight concurrency và bounded queue không?
41. Có per-shard/tenant quotas không?
42. Có tính global cap khi autoscale workers không?
43. Có tách production/CDC/historical priority không?
44. Có pause/kill switch có kiểm soát không?
45. Có adaptive throttle và hysteresis/cooldown không?
46. Có guardrail dừng khi SLO vi phạm không?
47. Có tính batch size theo bytes/API limits không?
48. Có retry/backoff/jitter với budget không?
49. Có phân loại unknown commit và version-skipped không?
50. Có tính write amplification/indexes/replication cost không?
51. Có quan sát cache pollution và compaction debt không?
52. Có ước tính time/cost dựa trên sustained success throughput không?
53. Có chạy thử dưới peak production traffic không?
54. Có tránh làm load generator/driver pool thành bottleneck mới không?

**Validation, cutover và rollback**

55. Có key-range coverage verification không?
56. Có normalized value/version digest comparisons không?
57. Có phân biệt diff vì target lag với diff same-version không?
58. Có validate tombstone/TTL correctness không?
59. Có validate cross-tenant isolation không?
60. Có kiểm all error/quarantine dispositions trước cutover không?
61. Có full CDC catch-up watermark theo mọi partitions không?
62. Có shadow read/canary routing giới hạn tải không?
63. Có rollback trigger và operator signoff không?
64. Có giữ old schema/collection đủ rollback window không?
65. Nếu write authority đổi, có reverse sync/failback plan không?
66. Có monitor user-facing errors sau cutover không?
67. Có planned cleanup/deletion sau khi rollback window kết thúc không?
68. Có backup/restore được kiểm chứng không?
69. Có audit migration runs, permissions và data provenance không?
70. Có thể dừng an toàn ngay khi correctness/security bị vi phạm không?

## 204. Một hợp đồng backfill mẫu

~~~yaml
migration:
  runId: orders-v2-2026-11
  ownerTeam: DataPlatform
  source:
    engine: MongoDB
    namespace: orders_v1
    authoritative: true
    readConsistency: documented
    snapshot:
      capability: verifyForDeployment
      boundary: recorded
    changeCapture:
      mechanism: ChangeStreamOrOutbox
      checkpointPerPartition: true
      retentionMarginAlert: true
  target:
    engine: DynamoDB
    table: OrdersProjectionV2
    schemaVersion: 2
    sourceVersionAttribute: sourceVersion
    keyMapping: deterministic
    conditionalApply: required
    tombstoneRetention: throughReplayHorizon
  transform:
    version: 3
    deterministic: true
    preserveBusinessTimestamps: true
    preserveExpiry: true
    piiMinimization: required
  execution:
    ranges: explicitAndCheckpointed
    workerOwnershipGeneration: required
    batchSize: tunedFromLoadTest
    maxInflightPerWorker: bounded
    globalRateBudget: configured
    perShardAndTenantLimits: enabled
    pauseOnProductionSloViolation: true
    resumeWithCooldown: true
    retries: boundedWithJitter
    unknownCommit: reconcile
    poisonRecords: durableQuarantine
  correctness:
    noGapBetweenSnapshotAndCdc: required
    noStaleOverwrite: required
    noDeletedRecordResurrection: required
    noCrossTenantLeak: required
    sourceTargetVersionDiff: monitor
    fullCoverageCheck: required
    cdcCatchUpWatermark: required
  productionGuardrails:
    apiP99: existingSlo
    apiErrorRate: existingSlo
    sourceReplicaLag: bounded
    targetThrottling: bounded
    cdcOldestAge: belowRetentionMargin
    criticalIncident: immediatePause
  cutover:
    shadowReads: sampled
    canary: staged
    gateOwner: designated
    readSwitch: afterDataGatesPass
    writeSwitch: separatelyApproved
    rollback:
      oldSchemaRetained: true
      reverseSyncIfNeeded: planned
  evidence:
    - scanRangeCheckpoints
    - applyOutcomeBreakdown
    - cdcPositionPerPartition
    - validationReports
    - productionSloTimeline
    - rollbackDrill
~~~

Đây là **YAML mô tả yêu cầu** chứ không phải cấu hình có thể chạy nguyên xi cho MongoDB, DynamoDB hay Java. Các trường phải được ánh xạ theo API, version và chính sách vận hành thực tế.

## 205. Mẫu bảng quyết định vận hành

| Tình huống quan sát | Quyết định mặc định nên xem xét | Bằng chứng sau hành động |
|---|---|---|
| Production p99 tăng sau backfill | Pause/throttle | p99 và headroom hồi phục |
| Target throttles | Giảm target writes + backoff | Throttle rate/queue age giảm |
| CDC lag gần retention | Ưu tiên catch-up, giảm scan | Retention margin tăng |
| Backfill stale writes bị skip | Ghi nhận legitimate outcome | Version target luôn >= incoming |
| Same-version payload conflict | Quarantine/pause affected scope | Root cause và source truth rõ |
| Tombstone resurrection | Dừng affected range | Không còn old writes được apply |
| Resume token invalid | New snapshot/reconciliation | No-gap coverage được chứng minh lại |
| Shadow diff vượt threshold | Không tăng canary | Normalized diff/vectors pass |
| Cutover lỗi | Rollback theo authority contract | Không mất writes sau cutover |
| Unknown commit tăng | Hạn retry, reconcile | Không duplicate business effects |

Bảng này chỉ là hướng dẫn chọn giả thuyết; policy thực tế phụ thuộc SLO, criticality và sự kiện đang diễn ra.

## 206. Một ví dụ end-to-end: Orders v1 → Orders v2

Giả sử một hệ Java nhận Orders ở MongoDB, cần tạo read model DynamoDB để phục vụ tra cứu theo tenant và status.

**Thiết kế nguồn:**

~~~text
orders_v1:
  _id
  tenantId
  status
  totalMinorUnits
  sourceVersion
  expiresAt
```

**Mục tiêu đích:**

~~~text
OrdersProjectionV2:
  pk = TENANT#{tenantId}
  sk = ORDER#{orderId}
  status
  totalMinorUnits
  sourceVersion
  isDeleted
```

**Giai đoạn 1 — Chuẩn bị**

- Java API vẫn ghi MongoDB.
- Source updates tăng `sourceVersion` atomically.
- Outbox/Change Stream được thiết lập có replay checkpoint.
- DynamoDB target có key/index design và least privilege.
- Source/target concurrency limits, p99 guardrails, tracing được bật.

**Giai đoạn 2 — Backfill lịch sử**

- Chia MongoDB key ranges.
- Đọc từng page có projection fields.
- Transform deterministic.
- Conditional Put/Update target nếu incoming version mới hơn.
- Checkpoint sau durable disposition.
- Throttle khi checkout p99 hoặc replica lag xấu.
- Quarantine document lỗi thay vì bỏ im lặng.

**Giai đoạn 3 — Catch-up**

- CDC consumer áp insert/update/delete với version ordering.
- Tombstone cho delete.
- Per-partition applied watermark.
- Giám sát oldest age và retention margin.

**Giai đoạn 4 — Kiểm chứng**

- Key-range coverage checks.
- Sample deep diffs theo cùng source version.
- Không có cross-tenant key collisions.
- Deleted records không bị hồi sinh.
- No unresolved critical quarantines.
- Production SLO còn headroom.

**Giai đoạn 5 — Cutover**

- Shadow reads và canary read routing.
- Tăng traffic đọc từng đợt khi đạt gate.
- Source tiếp tục là write authority nếu chưa có bước write migration riêng.
- Giữ rollback window và theo dõi CDC lag.

Đây là một **kiến trúc tham khảo**. Mức độ nhất quán chính xác giữa MongoDB snapshot và Change Streams phải dựa vào supported deployment semantics, không thể chỉ lấy hai timestamps do Java tạo rồi coi là guarantee.

## 207. Kết luận

Backfill trong một cụm **Database No SQL** đang phục vụ traffic là một bài toán **di chuyển dữ liệu đồng thời với điều khiển tải**.

Một giải pháp đáng tin phải:

- Xác định **source of truth**, semantic của target và tiêu chí đúng dữ liệu.
- Kết hợp **historical scan** với một cơ chế **change capture không gap** hoặc một window dừng ghi có kiểm soát.
- Dùng **stable key, deterministic transform, source version và atomic conditional apply** để tránh historical write ghi đè state mới.
- Xử lý **delete/tombstone, TTL, delta events và generation** thay vì chỉ copies records hiện còn tồn tại.
- Có **durable checkpoint sau commit**, retries idempotent, quarantine và recovery khi cursor/token hết hạn.
- Giới hạn **rate, concurrency, batch size, queue, per-shard/per-tenant load**; throttle theo tình trạng thực của production và target.
- Đặt **production SLO làm guardrail**, có pause/kill switch, cooldown và quyền điều hành rõ.
- Theo dõi **CDC lag/retention, replica apply lag, compaction, cost và errors** cho tới khi mọi backlog bền vững.
- Kiểm chứng bằng **key coverage, normalized state/version diff, delete validation và canary shadow reads**, không chỉ record counts.
- Tách **read cutover** khỏi **write authority transfer** và có rollback/reverse-sync plan trước khi bỏ đường cũ.

> **Đúng và an toàn quan trọng hơn tốc độ. Một backfill kết thúc sớm nhưng làm checkout timeout, bỏ sót mutation hoặc hồi sinh dữ liệu bị xóa là một migration thất bại.**

Khi vận hành một backfill, hãy liên tục trả lời bốn câu hỏi: **Đã điền tới đâu? Thay đổi mới có đang theo kịp không? Dữ liệu target đã được kiểm chứng đúng chưa? Và tải đang phục vụ có còn nằm trong SLO không?** Chỉ khi cả bốn câu trả lời có bằng chứng thì mới nên tiến tới cutover và loại bỏ mô hình cũ.

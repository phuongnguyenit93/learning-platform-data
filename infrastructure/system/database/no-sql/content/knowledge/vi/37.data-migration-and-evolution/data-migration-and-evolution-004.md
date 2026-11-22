# Xuất/nhập theo lô và theo dõi tiến độ có thể tiếp tục trong NoSQL

## 1. Bài toán: đã nhập 80 triệu bản ghi thì tiến trình bị dừng

Một hệ thống Java phải chuyển 100 triệu documents từ một cụm NoSQL cũ sang cụm mới. Lần đầu, nhóm triển khai chạy chương trình:

```text
Source NoSQL --read all--> Java process --insert all--> Target NoSQL
```

Sau 12 giờ, khoảng 80 triệu records đã được xử lý thì máy chạy job mất kết nối. Không có thông tin đáng tin cậy về records nào đã ghi bền, records nào mới được đọc vào bộ nhớ, batch nào server đã commit nhưng client không nhận phản hồi. Một người đề xuất chạy lại từ đầu, người khác muốn bỏ qua 80 triệu records đầu tiên.

Cả hai cách đều nguy hiểm:

- Chạy lại bằng thao tác `insert` không idempotent có thể tạo duplicate business records hoặc lỗi unique key.
- Bỏ qua 80 triệu records dựa trên counter RAM có thể **mất dữ liệu** nếu phần cuối chưa ghi bền.
- Dùng `skip(80000000)` có thể rất chậm; nếu source thay đổi trong lúc export, vị trí offset có thể dịch.
- Một write batch bị timeout có thể đã **commit một phần hoặc toàn bộ** dù chương trình nhìn thấy exception.
- Nếu source tiếp tục nhận writes trong suốt 12 giờ, việc copy dữ liệu tại nhiều thời điểm không tự tạo một snapshot nhất quán.

Bài học này thuộc chương **Di chuyển và thay đổi** của module **Database No SQL**. Mục tiêu là thiết kế quy trình **xuất/nhập theo lô có khả năng tạm dừng, tiếp tục, kiểm tra tiến độ và phục hồi sau lỗi**, đồng thời giữ đúng dữ liệu và hạn chế ảnh hưởng đến hệ đang phục vụ.

Ý tưởng trọng tâm:

> **Một job “đã đọc đến đâu” chưa chắc “đã ghi bền đến đó”. Điểm tiếp tục đáng tin phải được đặt sau ranh giới xử lý bền, gắn với nguồn dữ liệu và được kiểm chứng bằng cơ chế idempotency/reconciliation.**

## 2. Mục tiêu học tập

Sau bài học, bạn cần:

1. Phân biệt **bulk export**, **bulk import**, **online migration**, **backfill**, **rebuild read model** và **snapshot + CDC catch-up**.
2. Lập kế hoạch migration theo schema, partitioning, index, dữ liệu nhạy cảm, consistency và downtime budget.
3. Chọn cơ chế duyệt nguồn: **keyset pagination**, cursor, partition scan, opaque continuation token và snapshot boundary.
4. Thiết kế **batch size** theo số records, bytes, thời gian, throughput và giới hạn từng hệ NoSQL.
5. Định nghĩa checkpoint theo **run ID, source identity, partition/range, cursor/last key, snapshot generation và sink commit**.
6. Giải thích vì sao **at-least-once + idempotent writes** thường dễ vận hành hơn lời hứa exactly-once chung chung.
7. Thiết kế idempotency ở document/item level, conditional revision updates và output chunk manifests.
8. Xử lý crash windows, ambiguous commit, partial write failures, retries, poison records và quá hạn continuation token.
9. Đo tiến độ bằng **records/bytes processed, persisted, verified, lag, ETA có độ tin cậy**, không chỉ một phần trăm tùy ý.
10. Thực hành với MongoDB, DynamoDB, Cassandra, Redis, Elasticsearch/OpenSearch và Java 17.
11. Xây dựng runbook từ dry-run đến cutover, rollback, verification và decommission.

## 3. Từ ngữ cơ bản: cùng là “di chuyển” nhưng hợp đồng khác nhau

| Công việc | Đầu vào | Đầu ra | Đặc điểm |
|---|---|---|---|
| **Export** | Source NoSQL | File/object stream hoặc dataset trung gian | Có thể cần snapshot và manifest |
| **Import** | File/object stream hoặc nguồn khác | Target NoSQL | Cần ghi bền, retry và index |
| **Backfill** | Source hiện có | Trường/index/read model mới | Thường chạy khi writes vẫn tiếp tục |
| **Migration offline** | Source tạm ngừng writes | Target sau bulk copy | Cutover đơn giản hơn, cần downtime |
| **Migration online** | Source liên tục nhận writes | Target song song | Cần capture thay đổi và cutover |
| **CDC replay** | Ordered change log | Sink projection | Cần offset/token và idempotency |
| **Restore** | Backup/snapshot + logs | Trạng thái hệ tại recovery point | RPO/RTO và integrity |

### Hai lớp mục tiêu

**Dữ liệu đúng:** không thiếu record, không áp duplicate effect, không ghi version cũ đè version mới, không mất delete/TTL và không phá tenant isolation.

**Vận hành ổn:** có giới hạn tải, biết job đang ở pha nào, có thể resume sau restart/failover, theo dõi tài nguyên và có rollback.

Đọc được 100 triệu records chỉ chứng minh source read path đã chạy; **không chứng minh target phục vụ cùng kết quả nghiệp vụ**.

## 4. Kiến trúc tổng thể của một job an toàn

```text
                   CONTROL / METADATA PLANE
          +------------------------------------+
          | jobId, source identity, schema     |
          | snapshot boundary, partitions     |
          | checkpoint, lease, counters       |
          | chunk manifest, audit, errors     |
          +------------------------------------+
                  ^                      |
                  | progress             | work assignment
                  |                      v
Source NoSQL --> Reader --> Transformer --> Bounded queue --> Writer --> Target
                   |             |                            |
                   |             |                            v
                   |             +-----------------------> Verify/repair
                   |
           Source snapshot / change log
```

Các thành phần:

- **Reader:** lấy dữ liệu theo một thứ tự hoặc partition strategy có thể tiếp tục.
- **Transformer:** chuyển schema, chuẩn hóa data types, lọc trường được phép, map IDs.
- **Writer:** đưa records vào target qua bulk/conditional APIs, xử lý kết quả từng item.
- **Checkpoint store:** lưu mốc đã xử lý bền và metadata của run, độc lập với heap tiến trình.
- **Manifest:** mô tả chunks đã tạo, checksum, count, range, version.
- **Verifier:** đối soát counts, hashes/revisions và business invariants.
- **Controller:** phân công ranges, timeout/lease/fencing, pause/resume/cancel, throttling.

Một số triển khai gom các thành phần thành một chương trình Java. Điều quan trọng là **ranh giới và hợp đồng**, không nhất thiết phải có nhiều microservices.

## 5. Xác định phạm vi và điều kiện chấp nhận trước khi viết code

Một kế hoạch ví dụ:

```yaml
migration:
  id: "orders-v2-2026-11"
  purpose: "move order read model to new NoSQL target"
  source:
    cluster_id: "orders-source-prod"
    database: "orders"
    collection: "orders"
    scope: "approved tenant partitions"
  target:
    cluster_id: "orders-target-prod"
    database: "order_views"
    collection: "orders_by_customer"
  schema_version: 2
  consistency: "snapshot-and-cdc"
  correctness:
    unique_order_identity: true
    preserve_deletes: true
    no_stale_overwrite: true
  constraints:
    load_budget: "approved source and target capacity"
    max_parallelism: "measured limit"
  rollback: "source remains authoritative until acceptance"
```

Đây là **metadata minh họa**, không phải cấu hình của một công cụ có sẵn.

### Cần trả lời trước khi chạy

1. Source và target là database/cluster/version nào?
2. Chuyển tất cả dữ liệu hay subset tenant/time range?
3. Có chuyển cả attachments, indexes, TTL, tombstones, ACL, metadata không?
4. Kiểu dữ liệu có đổi không? Chuyển BSON Date, UUID, Decimal, binary, null/missing thế nào?
5. Source còn nhận writes trong lúc bulk copy không?
6. Cần consistency tại một snapshot hay cho phép eventually converge?
7. RTO/downtime/cutover deadline là bao nhiêu?
8. Rollback về source có an toàn sau khi target đã nhận writes không?
9. Ai được phép đọc/di chuyển PII và lưu dump ở đâu?

Không làm rõ các câu hỏi ấy thì việc chọn batch size hay số worker là tối ưu **một công việc chưa có định nghĩa đúng**.

## 6. Phân biệt bốn mốc của tiến độ

Một batch 500 records có thể đi qua:

```text
SOURCE READ       500 records obtained
      |
      v
TRANSFORMED       498 valid, 2 quarantined
      |
      v
SINK REQUESTED    498 writes sent
      |
      v
SINK CONFIRMED    496 applied, 2 retryable
      |
      v
CHECKPOINTED      only contiguous durable prefix advanced
      |
      v
VERIFIED          source/target correctness checked
```

Các số này **khác nhau có chủ đích**.

| Counter | Ý nghĩa | Có thể dùng làm recovery checkpoint không? |
|---|---|---|
| `records_read` | Reader đã nhận dữ liệu | **Không** nếu writer chưa bền |
| `records_transformed` | Transform thành công | Không |
| `records_attempted` | Đã gọi sink API | Không |
| `records_applied` | Sink có ACK theo mức đã định | Có thể là bằng chứng, nhưng chưa đủ khi async/partial errors |
| `records_checkpointed` | Mốc contiguous durable progress đã lưu | **Có**, theo protocol |
| `records_verified` | Đã đối soát với source/expected state | Bằng chứng correctness độc lập |

Một job có `records_read=1000000` nhưng `records_checkpointed=700000` chỉ an toàn khi resume ở mốc 700000 với retry idempotent. Nếu dashboard hiển thị “100%” từ read count, người vận hành sẽ có kết luận sai.

## 7. Định nghĩa ranh giới snapshot của source

Khi source có ghi đồng thời, việc đọc từng page ở các thời điểm khác nhau có thể tạo “bản chụp pha trộn”:

```text
T0 source: O1=PENDING, O2=NEW
T1 export page 1 includes O1=PENDING
T2 writer changes O1=PAID, O2=CANCELED
T3 export page 2 includes O2=CANCELED
```

File export chứa trạng thái từ **hai mốc**. Điều đó có thể chấp nhận cho một backup eventual theo hợp đồng, nhưng không được tuyên bố là snapshot-consistent nếu chưa có cơ chế.

### Ba chiến lược

1. **Ngừng writes tạm thời:** chọn freeze boundary, export, import, verify, cutover. Dễ lập luận hơn nhưng cần downtime.
2. **Snapshot-consistent read:** nếu engine cung cấp snapshot/PITR/read timestamp phù hợp và đủ thời hạn, đọc cùng một mốc.
3. **Snapshot + CDC:** lấy baseline theo snapshot/high-water mark, rồi replay changes từ boundary đến khi target bắt kịp để cutover.

Lựa chọn thứ ba thường cần nhất cho online migration nhưng khó hơn vì phải phối hợp **không có lỗ hổng giữa scan và change capture**.

## 8. Snapshot + CDC: tránh khoảng mất cập nhật

Anti-pattern:

```text
09:00 start full scan
09:40 scan complete
09:41 start CDC from "now"
```

Một update xảy ra 09:20 trên record **đã scan từ 09:05** không nằm trong baseline mới nhất và không xuất hiện trong CDC bắt đầu 09:41 → **mất cập nhật**.

### Mô hình đúng hơn

```text
Source
  |
  +-- establish consistent snapshot boundary S
  |         |
  |         v
  |      bulk scan at S -----------> target baseline
  |
  +-- retain/capture changes from S
            |
            v
        CDC replay ----------------> target revisions
            |
            v
      catch up to verified boundary C
            |
            v
         cutover
```

Tùy engine, CDC có thể cần bắt đầu **trước snapshot**, có snapshot phase do connector điều phối, hoặc dùng log position/transaction timestamp được bảo đảm. Không tự đoán `now()` thay cho source-consistent position.

### Xử lý sự kiện đến muộn

Trong giai đoạn snapshot và replay song song:

```text
CDC updates O1 to revision 12.
Later snapshot loader writes O1 revision 9.
```

Nếu chỉ dùng unconditional upsert, snapshot v9 có thể **ghi đè dữ liệu mới**. Cần source revision/ordering guard hoặc staging/cutover protocol để state cuối là revision 12.

## 9. Chọn cách duyệt source

| Kỹ thuật | Phù hợp | Hạn chế khi resume |
|---|---|---|
| Offset/`skip` | Dataset nhỏ, ổn định | Deep scans đắt, insert/delete làm dịch vị trí |
| Keyset/seek by immutable key | Duyệt thứ tự index ổn định | Cần key unique, sort/condition chính xác |
| Server cursor | Streaming trong một session | Cursor có TTL và có thể mất khi process crash |
| Opaque SDK paging token | APIs như DynamoDB/Cassandra | Token gắn query/partition, có thể không sống lâu |
| Partition/range scan | Dataset lớn, parallelizable | Cần không overlap/missing và checkpoint per range |
| Snapshot/file chunks | Object storage staged export | Cần manifest, immutable parts và integrity |
| Change-log offset | CDC incremental replay | Phải bảo đảm source retention/identity |

### Tránh dùng deep offset làm “checkpoint”

```text
Resume with skip(80_000_000)
```

Ở nhiều database, server vẫn phải đi qua rất nhiều records. Khi source thay đổi, vị trí offset còn có thể dịch và gây duplicate/missing.

### Keyset với sort giảm dần

Sort `createdAt DESC, id DESC`, trang tiếp theo cần:

\[
createdAt<t_{\mathrm{last}}\;\lor\;
(createdAt=t_{\mathrm{last}}\land id<id_{\mathrm{last}})
\]

Đặt sort tuple đầy đủ trong checkpoint. Timestamp có thể trùng; nếu chỉ lưu `createdAt`, có thể bỏ records cùng timestamp chưa xuất.

### Keyset không phải snapshot

Nếu sort key mutable hoặc records bị insert/delete trong lúc scan, một keyset traversal cũng có thể thiếu/trùng so với một tập tại thời điểm cố định. Vì vậy cần định nghĩa **consistency boundary, immutable key và CDC** khi business đòi chính xác.

## 10. Chia vùng dữ liệu để xuất/nhập song song

Đừng nhất thiết cho một worker chạy duyệt toàn bộ keyspace. Có thể chia:

```text
Source key space
  Range A:  [0000, 2500)
  Range B:  [2500, 5000)
  Range C:  [5000, 7500)
  Range D:  [7500, MAX]

Worker A -> checkpoint A
Worker B -> checkpoint B
Worker C -> checkpoint C
Worker D -> checkpoint D
```

### Điều kiện bắt buộc

- Mỗi record thuộc **một range** theo partition strategy được định nghĩa.
- Ranh giới kiểu `[start, end)` không overlap.
- So sánh keys/collation/BSON types chính xác.
- Checkpoint độc lập từng range.
- Khi reassignment, worker cũ không tiếp tục ghi trái quyền.
- Tổng hợp tiến độ không dùng `max(lastKey)` của cả job.

### Dữ liệu phân bố không đều

Chia theo giá trị ID có thể khiến Range A chứa 90% records, còn ba range kia gần trống. Có thể dùng histogram/sampling/counters/phân hoạch hash/partition key hoặc adaptive splits, nhưng phải giữ **định nghĩa snapshot, ownership và checkpoint**.

### Partition scope quan trọng hơn số workers

Với Cassandra/DynamoDB, đọc cùng hot partition bằng 100 workers có thể làm tệ hơn. Với MongoDB sharded cluster, split theo shard key/snapshot index nên tránh scatter-gather đắt. Đo actual read units, disk I/O và per-shard pressure trước khi tăng parallelism.

## 11. Opaque continuation token không phải con số thứ tự

Một response của source API:

```json
{
  "items": ["..."],
  "nextToken": "opaque-source-token"
}
```

Token có thể mã hóa partition position, query plan, last evaluated key hoặc session state. Không tự parse, sửa hoặc xây lại từ page number.

### Token phải gắn query

Checkpoint cần ghi:

```text
source_cluster_id
table_or_collection
partition/range
query/filter/sort fingerprint
page size / schema version if required
opaque token bytes or last key
snapshot generation / source log boundary
```

Nếu thay filter/tenant/shard layout mà vẫn dùng token cũ, bạn có thể resume sai dataset.

### Token expiry và topology changes

Một số paging state/cursor token không hợp lệ sau restart, reshard, TTL expiration hoặc source log retention. Chương trình phải phát hiện và **dừng có kiểm soát/restart range từ mốc bền**, không âm thầm reset sang trang đầu rồi báo tiến độ như không có gì xảy ra.

## 12. Không dùng một counter global làm checkpoint

Ba workers:

```text
Range A: committed through key 120
Range B: committed through key 650
Range C: committed through key 830
```

Checkpoint không phải `lastKey=830` cho cả job. Nếu workers A/B chết rồi resume từ 830, phần còn lại ở A/B có thể bị bỏ qua.

Một bản ghi trạng thái phù hợp hơn:

```json
{
  "jobId": "MIG-007",
  "generation": 4,
  "ranges": [
    {"id": "A", "lastCommittedKey": "120"},
    {"id": "B", "lastCommittedKey": "650"},
    {"id": "C", "lastCommittedKey": "830"}
  ]
}
```

Đây là sơ đồ minh họa; khóa thực tế có thể là object phức hợp, opaque paging state hoặc log position, không nhất thiết chuỗi số.

## 13. Một checkpoint đáng tin nên chứa những gì?

Một ví dụ:

```json
{
  "jobId": "MIG-007",
  "runGeneration": 5,
  "source": {
    "clusterId": "source-cluster-A",
    "collection": "orders",
    "snapshotId": "snapshot-2026-11-14",
    "schemaVersion": 2
  },
  "target": {
    "clusterId": "target-cluster-B",
    "collection": "orders_by_customer",
    "mappingVersion": 7
  },
  "rangeId": "tenant-T01-day-2026-11-14",
  "rangeEndExclusive": "2026-11-15T00:00:00Z",
  "lastDurableSourceKey": {
    "createdAt": "2026-11-14T10:00:00Z",
    "orderId": "O12345"
  },
  "lastDurableChunkId": "chunk-000045",
  "lastVerifiedChunkId": "chunk-000042",
  "attemptedRecords": 120000,
  "confirmedRecords": 119997,
  "quarantinedRecords": 3,
  "updatedAt": "2026-11-14T11:00:00Z"
}
```

**Cảnh báo:** record này mang ý nghĩa thiết kế; không copy nguyên IDs nhạy cảm/tenant IDs vào logs/telemetry hoặc dashboard công khai. Chọn cấu trúc phù hợp với engine và data classification.

### Những trường không nên thiếu

| Nhóm | Vai trò |
|---|---|
| Source identity | Không resume nhầm cluster đã recreate |
| Query identity | Không áp token cho filter/sort/schema khác |
| Range identity | Biết mốc chỉ áp cho shard/partition/range nào |
| Generation/owner epoch | Ngăn worker cũ ghi checkpoint sau khi bị thay |
| Durable boundary | Mốc source đã được sink xử lý bền |
| Sink outcome/manifest | Reconcile unknown commit và partial failures |
| Snapshot/CDC boundary | Kết nối baseline với changes mà không có gap |
| Counters/timestamps | Quan sát và debug, không tự làm authority |

### Không ghi secrets vào checkpoint

Checkpoint có thể chứa access tokens, resume tokens hoặc source identifiers; cần scope quyền, encryption at rest và audit. **Không đặt raw DB password hoặc KMS key** trong job metadata.

## 14. Checkpoint là lời hứa, không phải “vị trí con trỏ hiện tại”

Hãy phân biệt ba vị trí:

```text
Reader position:   record 1200 was fetched
Sink durable:      record 1160 was committed
Checkpoint stored: through record 1100
```

Nếu process crash, resume từ **record 1101** theo contract của cursor/last-key checkpoint, chứ không phải 1201.

Tại sao không resume từ 1161? Vì sink đã commit đến 1160 nhưng checkpoint đó chưa được ghi bền. Có thể:

1. Truy vấn/reconcile sink để biết 1160 là durable.
2. Hoặc đọc lại 1101..1160 và áp dụng **idempotently**.

Lựa chọn thứ hai thường dễ thực hiện hơn khi target hỗ trợ deterministic keys và conditional writes. Nhưng nếu write là `INCR` hoặc append event không có dedup, replay có thể tạo effects trùng.

### Boundary cần có hướng chính xác

Với Kafka, committed offset thường là **offset kế tiếp cần đọc**. Với last-key keyset, checkpoint thường là **key cuối đã hoàn tất** và next query dùng predicate loại key đó. Với DynamoDB `LastEvaluatedKey` hoặc Cassandra paging state, semantics lại theo API.

**Đừng đổi giữa “last completed” và “next to read” mà không có field naming rõ.**

## 15. State machine cho từng range và toàn job

Job:

```text
CREATED -> VALIDATING -> SNAPSHOTTING -> EXPORTING
                                        |
                                        v
                                   IMPORTING
                                        |
                                        v
                                   CDC_CATCHUP
                                        |
                                        v
                                   VERIFYING
                                        |
                                        v
                                   READY_TO_CUTOVER
                                        |
                                        v
                                   CUTOVER -> COMPLETED
```

Các trạng thái khác:

```text
PAUSING -> PAUSED -> RESUMING
FAILED_RETRYABLE
FAILED_PERMANENT
CANCELED
ROLLING_BACK -> ROLLED_BACK
```

### State per range

```text
PENDING -> LEASED -> READING -> WRITING -> CHECKPOINTED
                                   |
                                   v
                              RETRY_WAIT
                                   |
                                   v
                                WRITING

CHECKPOINTED -> VERIFYING -> VERIFIED
```

Một job được ghi `COMPLETED` **chỉ khi tất cả ranges và những điều kiện cuối cùng đều đã hoàn tất**, không phải vì tổng `records_read` bằng một estimate.

### Terminal outcomes

Một lỗi schema không thể xử lý có thể khiến range ở `FAILED_PERMANENT` hoặc `QUARANTINED`. Nếu policy cho phép terminal quarantine, cần theo dõi số items không được nhập và bảo đảm cutover **không giả định chúng đã nhập**.

## 16. Bốn cửa sổ crash quan trọng

### A. Crash sau read, trước write

```text
read 100 records -> crash -> none written
```

Nếu checkpoint không tiến, replay 100 records là đúng.

### B. Crash sau checkpoint, trước write

```text
read -> checkpoint advanced -> crash -> write never occurs
```

Đây là **anti-pattern gây mất records**. Checkpoint không được tiến trước effect bền.

### C. Crash sau sink commit, trước checkpoint

```text
read -> sink commit -> crash -> checkpoint unchanged
```

Replay là có thể. Đây là cửa sổ bình thường của **at-least-once**; phải dùng idempotency/conditional state update.

### D. Sink commit xong nhưng ACK bị mất

```text
client sends batch
target commits some/all items
network drops response
client sees timeout/unknown
```

Client không thể kết luận “batch chưa ghi gì”; cần query/reconcile theo keys/event IDs hoặc retry idempotently.

### Tóm tắt

| Cửa sổ | Outcome đã biết? | Phản ứng an toàn |
|---|---|---|
| Read trước write | Chưa ghi | Replay từ checkpoint |
| Checkpoint trước write | Sai thứ tự | Sửa protocol; tìm gap |
| Commit trước checkpoint | Sink có thể đã ghi | Replay idempotent hoặc reconcile |
| Timeout sau dispatch | Unknown/partial | Per-item status, idempotent retry |

## 17. Vì sao “exactly-once toàn pipeline” khó?

Nguồn, checkpoint store và target có thể là **ba hệ thống khác nhau**:

```text
Source Cassandra
    |
    v
Java migration worker
    |
    +--> MongoDB target write
    |
    +--> PostgreSQL checkpoint store
```

Nếu không có một transaction chung cho **target effect + checkpoint**, crash giữa hai commit tạo replay hoặc gap. Có thể cố dùng distributed transaction khi các hệ hỗ trợ, nhưng nhiều NoSQL combinations không cung cấp atomic cross-system commit thực tế.

### Thiết kế có thể vận hành

1. Đọc theo thứ tự/range xác định.
2. Ghi **idempotently** vào target.
3. Xác nhận effect bền theo target API.
4. Tiến checkpoint sau success và lưu durable.
5. Sau restart, replay từ checkpoint trước đó khi cần.

Kết quả mong muốn là **một trạng thái business đúng** dù thao tác vận chuyển có thể xử lý cùng record nhiều lần.

### Exactly-once có phạm vi

Một DB transaction có thể bảo đảm exactly-once trong phạm vi transaction/ledger được hỗ trợ. Kafka transactions có phạm vi các operations Kafka liên quan, không tự gộp một Redis `INCR` hay MongoDB write ở ngoài transaction. Khi phát biểu guarantee, nói rõ **system boundaries**.

## 18. Thiết kế idempotency cho target

Các kỹ thuật:

| Kỹ thuật | Ví dụ | Điều cần chú ý |
|---|---|---|
| Deterministic key | `targetId=sourceOrderId` | Scope tenant, collision, source recreation |
| Idempotent replacement | `SET state=v7` | Có thể bị version cũ overwrite |
| Conditional revision | “Chỉ update nếu sourceVersion mới hơn” | Source revision phải đơn điệu và so sánh đúng |
| Event ledger/inbox | Unique `eventId` đã xử lý | Ledger và effect cần atomic boundary |
| Idempotency key provider | External API nhận cùng key | TTL và semantics của provider |
| Chunk identity | `part-0034` ghi immutable/conditional | Không trùng part khi retry |

### Tại sao `UPSERT` chưa đủ?

Giả sử CDC đã áp order revision 12 rồi bulk loader retry revision 10:

```text
target = revision 12
bulk retry: upsert revision 10
target = revision 10  <-- regression
```

Upsert cùng key tránh duplicate documents nhưng **không tránh stale overwrite**. Cần điều kiện revision hoặc staging/cutover strategy.

### Nếu source không có revision?

Có thể cần:

- Tạo stable source change position/version trước khi migrate.
- Dùng snapshot phase tách biệt rồi phát changes theo đúng order.
- Single-writer per entity cùng deterministic order.
- Full replace từ snapshot mới khi cutover, nếu downtime cho phép.

Không tự so timestamp giữa hai server có clock skew để quyết định bản nào mới hơn nếu business cần consistency mạnh.

## 19. Atomicity theo từng item so với atomicity của cả batch

Một target có thể cho single-item conditional write atomic nhưng bulk batch chỉ báo từng item:

```text
Batch [A,B,C,D]
  A committed
  B committed
  C throttled
  D committed
```

Nếu pipeline bắt buộc thứ tự A→B→C→D theo cùng entity, không được checkpoint qua D khi C chưa bền. Nếu items độc lập, có thể theo dõi per-item outcomes rồi retry C và tiến checkpoint trên **contiguous completed prefix**.

### Tính tiến độ liên tục

```text
Offsets delivered:    100,101,102,103,104
Completed offsets:    100,101,103,104
Next safe checkpoint: 102
```

Sau khi 102 thành công, next checkpoint có thể thành 105 nếu 103/104 đã được lưu bền.

### Không mặc định bulk là transaction

MongoDB bulk operations, DynamoDB BatchWriteItem, Cassandra CQL BATCH, Redis pipeline và Elasticsearch Bulk API đều có giới hạn/semantics riêng. “Một network request” không đồng nghĩa “một atomic commit”.

## 20. Output manifest cho export files

Nếu export sang object storage trước khi import, chia thành **immutable chunks**:

```text
exports/MIG-007/
   manifest.json
   chunks/
       range-A-000001.enc
       range-A-000002.enc
       range-B-000001.enc
       ...
```

Một manifest có thể ghi:

```json
{
  "exportId": "MIG-007",
  "sourceClusterId": "source-cluster-A",
  "snapshotBoundary": "source-specific-boundary",
  "schemaVersion": 2,
  "format": "ndjson-v2",
  "compression": "gzip",
  "encryption": "managed-key-reference",
  "chunks": [
    {
      "chunkId": "range-A-000001",
      "rangeId": "range-A",
      "firstKey": "A00001",
      "lastKey": "A10000",
      "records": 10000,
      "sizeBytes": 5120000,
      "sha256": "actual-digest-generated-by-exporter"
    }
  ],
  "state": "SEALED"
}
```

Đây là định dạng logic minh họa; digest trong ví dụ không phải hash thật.

### Ghi manifest an toàn

1. Ghi chunk vào temporary object/key hoặc immutable destination.
2. Verify upload và bytes/checksum theo protocol.
3. Ghi chunk record vào durable manifest/control store.
4. Khi **mọi chunk của snapshot được xác minh**, seal manifest.
5. Importer chỉ dùng manifest `SEALED` và file checksum hợp lệ.

### Crash sau upload trước manifest

Một orphan chunk có thể tồn tại. Khi resume, kiểm tra object theo deterministic chunk ID, verify content/generation và hoàn thiện manifest hoặc dọn theo lifecycle. Không append cùng data thành hai chunks khác IDs nếu không có dedup/reconciliation.

### Integrity khác authenticity

SHA-256 file giúp phát hiện corruption **nếu digest được bảo vệ đáng tin**. Nếu attacker sửa cả object và manifest, một hash thường không chứng minh provenance; cần signed/authenticated manifest hoặc trust boundary phù hợp.

## 21. Import checkpoint là gì nếu nguồn là manifest?

Giả sử có 500 chunks đã seal:

```text
chunk 001 imported and verified
chunk 002 imported and verified
chunk 003 imported but ACK lost
chunk 004 not yet started
```

Khi worker restart, đọc **durable import ledger** theo `(jobId, chunkId, targetGeneration)`:

```json
{
  "jobId": "MIG-007",
  "targetGeneration": 4,
  "chunks": {
    "001": "VERIFIED",
    "002": "VERIFIED",
    "003": "UNKNOWN"
  }
}
```

Với chunk 003, phải reconcile target theo record IDs/revisions/checksum trước khi quyết định retry. Nếu imports idempotent, có thể replay 003 và chỉ mark verified sau kiểm tra.

### Không dùng file existence làm success

`chunk-003.csv` tồn tại ở object store chỉ chứng minh export file có mặt; **không chứng minh importer đã ghi mọi records vào target**. Phân biệt `EXPORTED`, `IMPORTED` và `VERIFIED`.

## 22. Checkpoint store cần durable và có concurrency control

Một checkpoint lưu tại:

```text
worker local file /tmp/checkpoint.json
```

không còn khi host bị thay hoặc job chạy trên máy khác. Nếu dùng shared object store hoặc DB:

- Ghi bền, với consistency phù hợp.
- Có conditional update/CAS theo owner generation.
- Không bị ghi lùi bởi worker cũ.
- Có audit/version history để khôi phục lỗi thao tác.
- Đồng bộ trạng thái job/chunks với outcomes.

### Optimistic concurrency

```text
READ checkpoint version=9, ownerEpoch=4
WORK ...
UPDATE checkpoint to version=10
IF version=9 AND ownerEpoch=4
```

Nếu bị một worker mới sở hữu epoch=5, update từ epoch=4 phải fail.

### Phải có quyền đọc source sau resume

Checkpoint rất tốt cũng vô dụng nếu snapshot/PITR token hết hạn hoặc source log đã bị truncate. Giữ **retention headroom**, có policy restart-from-new-snapshot/rebuild nếu boundary không còn hợp lệ.

## 23. Worker ownership, lease và fencing token

Khi chạy nhiều workers, controller có thể giao Range A cho worker W1:

```text
T0 W1 acquires lease epoch=7
T1 W1 reads range A, starts batch 20
T2 W1 pauses due to long GC/network partition
T3 lease expires; W2 acquires epoch=8
T4 W2 processes batch 20 and checkpoint advances
T5 W1 wakes, attempts to update checkpoint
```

Nếu W1 vẫn ghi checkpoint hoặc dữ liệu cũ, nó có thể **ghi lùi trạng thái**.

### Fencing phải được thực thi

```text
W1 update checkpoint with epoch=7 -> REJECT
W2 update checkpoint with epoch=8 -> ACCEPT
```

Quan trọng hơn, nếu W1 đã được phép ghi vào target mà chưa có revision guard/identity fence, việc chỉ chặn checkpoint có thể **không chặn stale target write**. Cần giải quyết cả ownership của writer hoặc dựa vào idempotent/versioned sink semantics.

### TTL không đủ

Hết TTL lease không giết process cũ. Trong distributed systems, một paused worker có thể tiếp tục gửi network writes sau khi quyền sở hữu đã đổi. Đây là lý do dùng **generation/epoch và conditional writes** tại boundary có thể kiểm soát.

### Bài tập tư duy

Hỏi: “Nếu hai workers cùng xử lý một range trong 1 giây, dữ liệu cuối vẫn đúng không?” Nếu không có bằng chứng, kế hoạch resume chưa vững.

## 24. Batch size: tối ưu theo item, bytes và thời gian

Không có con số batch size đúng cho mọi NoSQL. Một cách thiết kế:

```text
Flush batch when any condition holds:
  itemCount >= maxItems
  estimatedBytes >= maxBytes
  elapsedSinceFirstItem >= maxWait
```

### Vì sao không chỉ theo số documents?

```text
99 documents x 2 KiB   = 198 KiB
1 document x 900 KiB   = 900 KiB
Total                  = 1098 KiB
```

Batch 100 records có thể vượt byte budget dù count nhỏ. Đồng thời một record riêng lẻ vượt giới hạn API phải được xử lý theo **large-item policy**, không gom vào batch rỗng rồi retry vô hạn.

### Tham số độc lập

| Tham số | Tác động |
|---|---|
| Items/batch | Per-call overhead |
| Serialized bytes/batch | Network/memory/API size limits |
| Max wait time | Latency khi traffic thấp |
| Max in-flight batches | Throughput vs DB queueing |
| Max queued bytes | Heap/backpressure |
| Retry budget/backoff | Khả năng phục hồi vs overload |
| Transaction size/time | Lock/conflict/timeout (nếu dùng transactions) |

### Không giả định batch càng lớn càng nhanh

Batch lớn có thể giảm RTT nhưng làm p99, memory, GC, retry cost và partial-failure handling tăng. Một batch chứa 50.000 updates có thể bị server tự chia, throttle hoặc từ chối vì limit.

## 25. Một phép tính RTT đơn giản

Giả sử 120.000 records, batch 100 records và mỗi request tuần tự có RTT 10 ms:

\[
R=\left\lceil\frac{120000}{100}\right\rceil=1200
\]

Ước lượng **riêng thành phần chờ RTT**:

\[
T_{\mathrm{RTT}}\approx1200\times10\mathrm{ms}=12\mathrm{s}
\]

Tăng batch lên 1.000:

\[
R=120,\quad T_{\mathrm{RTT}}\approx1.2\mathrm{s}
\]

Nhưng đây không phải thời gian hoàn thành thực:

- Payload bytes tổng hầu như không đổi.
- Transfer time, parse/serialization, disk/CPU, index updates vẫn tồn tại.
- Batch lớn có thể vượt memory hoặc response limits.
- Concurrent requests có thể chồng lấp RTT.
- Retry/partial failures có thể làm tổng requests nhiều hơn.

**Đo số network calls và bytes thực**, không chỉ dùng công thức lý tưởng để chọn cấu hình.

## 26. Backpressure: reader không được nhanh hơn writer mãi

Một pipeline:

```text
Source reader:     10,000 records/s
Target writer:      2,000 records/s
Queue growth:       8,000 records/s
```

Sau 60 giây, queue có thể tăng:

\[
(10000-2000)\times60=480000\text{ records}
\]

Với mỗi record chiếm trung bình 4 KiB serialized bytes, payload thuần đã gần 1.83 GiB; bộ nhớ Java thực có thể lớn hơn do objects/buffers/GC.

### Biện pháp

1. Dùng bounded queue theo **items và bytes**.
2. Không fetch page tiếp khi buffer đã đầy.
3. Giới hạn max in-flight writes.
4. Tách read capacity và write capacity, có rate limiter.
5. Khi sink throttle, backoff và giảm tốc độ reader.
6. Có dead-letter/quarantine workflow cho records lỗi không thể chuyển.
7. Giữ checkpoint ở durable boundary, không chạy theo tốc độ fetch.

### Pipeline reactive cũng không tự đúng

Reactive Streams có thể cung cấp cơ chế demand/backpressure, nhưng nếu code bên trong `flatMap` tạo unbounded futures hoặc commit checkpoint ngay khi dispatch, vẫn có memory/correctness bugs.

## 27. Import cần phân loại lỗi, không retry mù

| Lỗi | Ví dụ | Phản ứng |
|---|---|---|
| Transient network | Connection reset, timeout | Retry có idempotency và backoff |
| Rate limit/throttle | Capacity exhausted | Giảm concurrency, backoff theo policy |
| Invalid schema | Field type không hỗ trợ | Quarantine hoặc fix transform |
| Authorization | Permission denied | Dừng, kiểm tra roles; không retry vô hạn |
| Unique conflict | Target ID đã tồn tại | Reconcile: duplicate đúng hay data conflict |
| Oversized record | Vượt item/document size | Chia model/alternate storage/quarantine |
| Stale revision | Event version cũ hơn target | Skip có chứng cứ; không ghi đè |
| Unknown commit | Timeout sau target commit | Read/reconcile hoặc idempotent retry |
| Source token expired | Cursor/log position không còn hợp lệ | Dừng/resnapshot theo runbook |
| Integrity mismatch | File checksum sai | Quarantine artifact, không import tiếp |

### Đừng coi mọi lỗi unique là thành công

Nếu target đã có key `O1001` nhưng payload thuộc tenant khác hoặc version khác không hợp lệ, “duplicate key → skip” có thể làm mất dữ liệu hoặc che cross-tenant corruption. Phải kiểm tra **identity scope và business invariant**.

## 28. Partial batch failure: cần giữ kết quả từng item

Ví dụ:

```text
Input:    E100 E101 E102 E103 E104 E105
Result:    OK   OK   FAIL  OK   OK   WAIT
```

Nếu import order quan trọng, không thể ghi checkpoint theo item cuối `E104` chỉ vì nó success. Cách xử lý:

1. Ghi thành công/terminal status theo source item ID.
2. Retry `E102` với idempotent operation.
3. Đợi `E105` thực sự durable hoặc xử lý terminal quarantine theo policy.
4. Chỉ tiến checkpoint qua **contiguous completed prefix**.
5. Đừng vứt kết quả thành công của `E103/E104`; khi replay, version/idempotency guard phải xử lý chúng.

### DynamoDB

`BatchWriteItem` có thể trả `UnprocessedItems`; HTTP thành công **không có nghĩa tất cả items đã được ghi**. Retry unprocessed items theo backoff và giữ capacity limits.

### Elasticsearch/OpenSearch

Bulk API trả một response có **item statuses**. Phải inspect từng action status/error và chỉ checkpoint khi tất cả relevant effects của đoạn liên tục đã bền theo contract, không chỉ nhìn top-level HTTP status.

### MongoDB

Bulk write ordered/unordered có thể có write errors và write concern errors; phải phân biệt partial success/unknown outcome, không xem whole-batch như một transaction trừ khi thực sự có transaction hỗ trợ đúng phạm vi.

## 29. Poison records và quarantine không làm biến mất nghĩa vụ hoàn tất

Một record có field trái schema:

```json
{
  "orderId": "O123",
  "totalMinor": "not-a-number"
}
```

Nếu không thể import, quy trình có thể:

- **FAIL_FAST:** dừng toàn job để sửa transform/migration.
- **QUARANTINE:** ghi record vào vùng kiểm soát, đánh dấu terminal exception theo policy.
- **REPAIR_THEN_RETRY:** sửa mapping và chạy lại.

### Khi nào có thể checkpoint qua record lỗi?

Chỉ nếu business contract cho phép terminal quarantine với evidence bền, có owner/reconciliation và cutover criteria tính rõ **unimported records**. Không được âm thầm bỏ record rồi báo “100% imported”.

### Security của quarantine

Quarantine/DLQ thường giữ raw payload nhạy cảm lâu hơn normal data. Cần encryption, least privilege, retention, audit và không gửi nguyên record vào alert/chat.

### Không để một record làm toàn pipeline treo mãi

Retry vô hạn một lỗi schema permanent vừa tăng tải vừa làm checkpoint đứng. Phân biệt transient/permanent bằng error class; log redacted diagnostics đủ tái hiện bằng synthetic fixture.

## 30. Định lượng tiến độ khi tổng số records không biết chính xác

Nhiều NoSQL query không cung cấp count chính xác rẻ hoặc snapshot-consistent:

```text
Estimated records = 100 million
Processed records = 80 million
```

Không thể tuyên bố chính xác **80% complete** nếu source có thêm 20 triệu records hoặc estimate được lấy từ statistics cũ.

### Ba mức độ tin cậy

1. **Exact total**: manifest có số chunks/records cố định trong snapshot đã seal, hoặc total được đếm có cùng consistency boundary.
2. **Estimated total**: thống kê/scan estimate; hiển thị `~80% estimated`.
3. **Unknown total**: chỉ hiển thị records/bytes, ranges finished và throughput, không bịa một phần trăm chính xác.

### Cần phân biệt số đã nhập và đã verify

```text
Exported:      100.0% of sealed chunks
Imported:       97.8% of chunks
Verified:       95.1% of chunks
CDC catch-up:   14 seconds behind source
Cutover-ready:  NO
```

Một progress bar duy nhất dễ che bước verification/catch-up còn dang dở.

## 31. Công thức ETA và giới hạn của nó

Nếu có exact remaining bytes \(D_{\mathrm{left}}\) và throughput trung bình bền \(v\) bytes/s:

\[
\mathrm{ETA}\approx \frac{D_{\mathrm{left}}}{v}
\]

Giả sử còn 120 GiB và throughput bền 40 MiB/s:

\[
\mathrm{ETA}\approx\frac{120\times1024}{40}\text{ s}
=3072\text{ s}\approx51.2\text{ phút}
\]

Nhưng ETA có thể sai khi:

- Records ở cuối lớn hơn phần đầu.
- Một shard hot làm stage cuối chậm.
- Target throttles hoặc compaction tăng.
- CDC liên tục sinh thêm work.
- Worker rebalances/retries và phải reprocess.
- Verify/index build chưa được tính.

### Cách hiển thị tốt hơn

```text
Estimated import ETA: 45–70 minutes (based on last 15m)
Snapshot export stage: completed
Verified chunks: 810/1000
Source CDC oldest unprocessed age: 2m 15s
Readiness to cutover: blocked by sink validation
```

Đưa **cửa sổ đo, độ không chắc và pha** để người vận hành không hiểu một con số như cam kết.

## 32. Tốc độ bền khác tốc độ đọc

Một job xuất 20.000 docs/s nhưng nhập chỉ 5.000 docs/s. Nếu dashboard báo 20.000 docs/s “migration throughput”, quản lý có thể nghĩ job kết thúc sớm hơn bốn lần.

Nên có:

- `read_records_per_second`.
- `transformed_records_per_second`.
- `durably_written_records_per_second`.
- `verified_records_per_second`.
- `source_bytes_per_second` và `sink_bytes_per_second`.
- `retry_records_per_second`.
- `quarantined_records_total`.
- `oldest_unapplied_change_age_seconds`.

### Phân biệt unit

Records/s không đủ khi document size biến thiên rất lớn. MiB/s phản ánh bytes nhưng không thể thay correctness: một job copy nhiều bytes vào target sai vẫn có “throughput cao”.

## 33. Progress theo chunks và ranges

Một job:

```text
Range A: 100/100 chunks verified
Range B:  60/100 chunks verified
Range C:  99/100 chunks verified
Range D:   5/100 chunks verified
```

Nếu mỗi chunk có cùng số records/bytes, khoảng 66% chunks hoàn tất. Nhưng khi kích thước chunk khác nhau, cần trọng số bytes/records hoặc exact manifest.

### Tại sao progress bị kẹt ở 99%?

- Range cuối có hot partition.
- Một chunk chứa oversized record.
- Index build hoặc compaction ở target.
- Quarantine cần người quyết định.
- CDC chưa bắt kịp source.
- Verification/reconciliation còn mismatch.

**Đừng tự “force 100%” khi dữ liệu chưa đúng**. Dashboard phải thể hiện pha và blocker.

## 34. Progress API cho người vận hành

Một response:

```json
{
  "jobId": "MIG-007",
  "state": "IMPORTING",
  "sourceSnapshot": "snap-2026-11-14",
  "progress": {
    "rangesCompleted": 18,
    "rangesTotal": 24,
    "chunksImported": 870,
    "chunksVerified": 851,
    "chunksTotal": 1000,
    "recordsApplied": 8800000,
    "recordsQuarantined": 2,
    "bytesWritten": 8500000000
  },
  "rate": {
    "durableRecordsPerSecond": 12000,
    "windowSeconds": 300
  },
  "estimatedCompletion": {
    "secondsRange": [600, 1200],
    "confidence": "low"
  },
  "cutoverEligible": false
}
```

Các số **minh họa**, không phải thực nghiệm. Một API thực phải có authentication/authorization, che source IDs/tokens và không phơi nội dung nhạy cảm của checkpoint.

### Atomic snapshot của progress?

Counters được cập nhật bởi nhiều workers có thể không khớp tuyệt đối tại một thời điểm. Nếu cần report kiểm toán, dùng snapshot/generation nhất quán từ control store hoặc chú thích metrics là **eventually consistent**. **Không dựa vào progress dashboard làm authority duy nhất để quyết định cutover**.

## 35. MongoDB: export theo cursor và `batchSize`

MongoDB Java Sync Driver hỗ trợ streaming qua `MongoCursor`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Sorts.*;
import static com.mongodb.client.model.Projections.*;
import org.bson.Document;

public final class MongoExportReader {
    public void exportTenant(
        MongoCollection<Document> collection,
        String verifiedTenantId,
        java.util.function.Consumer<Document> sink) {

        try (MongoCursor<Document> cursor = collection.find(
                eq("tenantId", verifiedTenantId))
                .sort(ascending("_id"))
                .projection(include("_id", "tenantId",
                    "status", "createdAt", "sourceRevision"))
                .batchSize(500)
                .iterator()) {

            while (cursor.hasNext()) {
                sink.accept(cursor.next());
            }
        }
    }
}
```

### Các giới hạn

- `batchSize(500)` là **yêu cầu về kích thước batch cursor**, không bảo đảm 500 docs mỗi network fetch; server có byte limits.
- Một cursor đang mở không phải durable checkpoint; process crash có thể làm cursor vô hiệu.
- `Consumer` ở ví dụ cần dùng bounded, durable sink; nếu chỉ collect vào `ArrayList` vô hạn, vẫn có nguy cơ OOM.
- `_id` chỉ dùng làm stable resume key nếu ordering/type/collation và scope đúng.
- Projection không tự tạo snapshot read consistency.

### Dùng keyset để resume dài hạn

Trang tiếp theo theo `_id` tăng:

```java
var query = and(
    eq("tenantId", verifiedTenantId),
    gt("_id", lastCommittedId)
);
var page = collection.find(query)
    .sort(ascending("_id"))
    .limit(501)
    .batchSize(500);
```

Trang đầu không có last key sẽ dùng predicate không có `gt`. Lấy 500 records rồi sử dụng phần tử thứ 501 (nếu có) để biết còn trang, nhưng **checkpoint phải bám vào record cuối thực sự đã ghi bền**, không phải item look-ahead chưa xử lý.

### MongoDB sharded source

Nếu shard key khác `_id`, query theo `_id` của toàn cluster có thể phải scatter-gather. Với dataset lớn, nên xem shard-aware ranges/query plans và phiên bản sharding đang dùng, đồng thời giữ mapping khi resharding.

## 36. MongoDB: `mongodump`/`mongorestore` khác custom JSON migration

Một số workload cần backup logical hơn là transform documents bằng Java.

| Công cụ/luồng | Phù hợp | Lưu ý |
|---|---|---|
| `mongodump` | Xuất BSON/metadata theo công cụ | Consistency, version compatibility, access controls |
| `mongorestore` | Nhập archive/dump MongoDB | Namespace mapping, indexes, write concerns, conflicts |
| Custom cursor exporter | Đổi schema/tenant subset/projection | Tự chịu checkpoint/transform |
| Managed snapshot/restore | Cluster recovery/migration theo provider | RPO/RTO, account/region/KMS/retention |
| Change Streams/CDC | Theo dõi updates trong online migration | Resume token và oplog history |

### Không tự coi `mongodump` có resume record-by-record

Logical dump tools có options và failure/restart behavior riêng theo version. Một archive bị dở không phải mặc nhiên có thể nối bytes hoặc seek tới record thứ N như custom exporter có manifest. Cần dùng semantics và hướng dẫn chính thức đúng phiên bản, verify output và có restart strategy.

### Indexes và write performance

Khi import hàng triệu records, indexes/unique constraints vừa giúp integrity vừa tăng write amplification. Có thể cân nhắc build index sau bulk load trên **target offline/staging** nếu kế hoạch cho phép, nhưng:

- Duplicates có thể khiến index build fail.
- Queries đang phục vụ có thể cần index trong quá trình import.
- TTL/index options/collation cần tương thích.
- Build index cũng cần memory/disk và thời gian tính vào cutover readiness.

Không xóa indexes production đang phục vụ chỉ để tăng import speed.

## 37. MongoDB: conditional update theo source revision

Đối với đọc snapshot v8 và CDC v10 cùng order, cần “chỉ áp bản mới hơn”.

Ví dụ mô hình:

```text
Target contains:
  _id=O1, sourceRevision=10, status=PAID

Incoming snapshot:
  _id=O1, sourceRevision=8, status=PENDING

Expected:
  ignore stale revision 8
```

Một điều kiện:

```javascript
db.target.updateOne(
  {
    _id: "O1",
    sourceRevision: { $lt: 8 }
  },
  {
    $set: {
      status: "PENDING",
      sourceRevision: 8
    }
  }
);
```

**Ví dụ này chỉ minh họa update cho document đã tồn tại có sourceRevision thấp hơn.** Nếu document chưa tồn tại, filter với `sourceRevision` làm câu chuyện upsert phức tạp hơn: cần thiết kế uniqueness/conditional insert/CAS protocol xử lý race để không tạo duplicate hoặc lỗi unique key. Không dùng `upsert=true` một cách mù quáng trên filter có revision rồi xem lỗi duplicate là “đã thành công”.

### Revision có phạm vi

Một timestamp hoặc integer revision chỉ so sánh an toàn khi được phát bởi **cùng authority theo cùng entity** và có quy tắc ordering rõ. Nếu source revision reset sau re-create, cần source incarnation/epoch trong identity.

### Delete tombstones

Delete event revision 11 phải ngăn snapshot revision 8 hồi sinh document. Có thể giữ tombstone/version record cho đến khi chắc chắn mọi nguồn replay cũ đã hết. Nếu xóa hẳn tombstone quá sớm, một retried old snapshot có thể reinsert.

## 38. DynamoDB: `Scan`, `Query` và `LastEvaluatedKey`

DynamoDB `Scan`/`Query` trả continuation state qua `LastEvaluatedKey`. Một page có thể bị giới hạn bởi **khoảng 1 MB dữ liệu đọc** theo API trước khi filter/projection, nên `Limit` không bảo đảm số items trả đúng bằng tham số.

### Java AWS SDK v2: một page Query

```java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.*;

public final class DynamoPageReader {
    private final DynamoDbClient client;

    public DynamoPageReader(DynamoDbClient client) {
        this.client = client;
    }

    public QueryResponse onePage(
        String verifiedTenantId,
        Map<String, AttributeValue> exclusiveStartKey
    ) {
        var builder = QueryRequest.builder()
            .tableName("Orders")
            .keyConditionExpression("tenantId = :tenant")
            .expressionAttributeValues(Map.of(
                ":tenant",
                AttributeValue.builder()
                    .s(verifiedTenantId).build()
            ))
            .limit(100);

        if (exclusiveStartKey != null
                && !exclusiveStartKey.isEmpty()) {
            builder.exclusiveStartKey(exclusiveStartKey);
        }

        return client.query(builder.build());
    }
}
```

**Điều kiện:** table/index phải có key schema hỗ trợ Query tenant theo ví dụ. Với table không thể Query theo tenant, phải dùng GSI hoặc data model khác; không biến Scan toàn bảng thành Query bằng một filter tùy ý.

### Điểm quan trọng cho checkpoint

- Dùng nguyên `LastEvaluatedKey` của response cho page tiếp, gắn với same table/index/query/filter/operation.
- Một page **rỗng sau `FilterExpression`** vẫn có thể còn `LastEvaluatedKey`; không dừng chỉ vì `Items.isEmpty()`.
- Một token không bảo đảm có thêm item hợp filter.
- Paging qua nhiều calls không mặc định tạo snapshot tại cùng thời điểm.
- Với Parallel Scan, mỗi segment cần checkpoint riêng và totalSegments/segment identity nhất quán trong run.

### Đừng checkpoint token trước khi target bền

Sau khi nhận page P và token T, xử lý items và xác nhận sink đúng rồi mới lưu T làm next-page boundary. Nếu API trả page có items lỗi, token T tiến quá các items đó có thể làm mất dữ liệu.

## 39. DynamoDB: `BatchWriteItem` và per-item retries

`BatchWriteItem` có những giới hạn tiêu biểu:

- Tối đa 25 put/delete requests mỗi call.
- Request payload tối đa 16 MB theo API.
- Item size tối đa 400 KB.
- Không hỗ trợ condition expressions hoặc `UpdateItem` trong API batch này.
- **Không atomic cho toàn bộ batch**; có thể trả `UnprocessedItems`.

### Pseudocode

```text
for each bounded chunk:
    pending = chunk
    while pending not empty and retry budget remains:
        result = BatchWriteItem(pending)
        pending = result.UnprocessedItems
        if pending not empty:
            exponentialBackoffWithJitter()

    if pending not empty:
        mark range/chunk retryable, do not checkpoint past it
    else:
        durable checkpoint / verify according to contract
```

### Rủi ro với blind Put

`PutRequest` có thể ghi đè item mới hơn; nếu cần conditional source revision, dùng `PutItem`/`UpdateItem` có condition hoặc `TransactWriteItems` khi phù hợp giới hạn API, dù sẽ tốn thêm requests. Đừng đánh đổi correctness chỉ để tận dụng BatchWriteItem.

### BatchGetItem

Khi đọc nhiều keys, `BatchGetItem` có giới hạn số keys/bytes và có thể trả `UnprocessedKeys`; response items không bảo đảm cùng thứ tự request. Map theo key và retry unprocessed, không dùng array index làm identity.

## 40. Cassandra: partition-aware scan và paging state

Cassandra được thiết kế hiệu quả nhất khi query gắn với partition key và clustering columns. Một dữ liệu ví dụ:

```sql
CREATE TABLE orders_by_tenant_day (
    tenant_id text,
    bucket_day date,
    created_at timestamp,
    order_id text,
    status text,
    PRIMARY KEY (
        (tenant_id, bucket_day),
        created_at, order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC, order_id DESC
);
```

Một migration job có thể chia work thành **tenant×day buckets** và checkpoint riêng từng bucket. Điều này thường dễ kiểm soát hơn quét toàn cluster qua `ALLOW FILTERING`.

### Java Driver paging

```java
var prepared = session.prepare(
    "SELECT order_id, created_at, status " +
    "FROM orders_by_tenant_day " +
    "WHERE tenant_id=? AND bucket_day=?"
);

var statement = prepared.bind(tenantId, bucketDay)
    .setPageSize(200);

var rs = session.execute(statement);
for (var row : rs) {
    processRow(row);
}
```

Ví dụ giả định `session` là `CqlSession` và các bound values có kiểu tương ứng. Sync iterator có thể fetch thêm pages ngầm; **một call `execute` không có nghĩa chỉ một network trip**.

### Paging state và resume

Paging state do driver trả phải được giữ trong **đúng query/bound values/driver semantics**. Nó không phải con số offset chung. Nếu token hết hạn/invalid, worker phải có kế hoạch restart bucket/range với idempotent writes hoặc dựng snapshot mới.

### RF/consistency/large partitions

- Read CL ảnh hưởng availability và dữ liệu nhìn thấy.
- Tombstones có thể khiến page trả ít rows dù server scan nhiều.
- Large partitions làm scan và compaction chậm.
- Token-range scan cần hiểu token ownership/replicas và topology.
- Tránh quá nhiều concurrent scans cùng hot partition.

### CQL BATCH không phải bulk-loader accelerator

Gom hàng nghìn writes tới nhiều partitions trong `BEGIN BATCH` có thể tăng coordinator/batchlog overhead và tạo timeout. Với independent partitions, thường nên cân nhắc **bounded asynchronous prepared statements**, không dùng logged multi-partition batch như network-packet optimization mặc định.

## 41. Redis: `SCAN` là iterator không ổn định trên keyspace đang đổi

`SCAN`:

```redis
SCAN 0 MATCH app:orders:* COUNT 100
```

trả cursor tiếp và danh sách keys. **COUNT là hint**, không bảo đảm 100 keys. Có thể trả 0 keys nhưng cursor khác 0; chỉ dừng khi cursor trả 0 theo protocol.

### Redis data export

Các cách khác nhau:

- RDB/AOF và managed snapshots: phù hợp backup/restore, cần hiểu persistence/durability.
- `SCAN` + read values: logical export cho subset/migration, **không phải consistent snapshot**.
- Application-managed key list/index: hỗ trợ deterministic traversal nếu design sẵn.
- Redis Streams: checkpoint theo stream IDs/consumer group semantics, không theo SCAN cursor.

### Duplicates/missing

Trên keyspace đang update, `SCAN` có thể trả duplicate keys và không cung cấp cùng snapshot state tại một thời điểm. Một resume protocol chỉ lưu SCAN cursor **không đủ để cam kết exactly-once coverage**.

### Redis Cluster

Mỗi node/shard có cursor riêng tùy client topology; không suy một cursor duy nhất duyệt toàn cluster. Khi resharding, cần mapping/repair protocol. Tốt hơn nếu có thể **freeze source/backup snapshot** hoặc lưu authoritative index của keys cho migration.

### TTL

Nếu source key có TTL còn 30 giây, import ở target sau 10 phút mà set lại TTL 30 giây làm kéo dài đời sống trái business contract. Cần quyết định lưu **absolute expiry timestamp** và tính remaining TTL tại import; với keys đã hết hạn, không hồi sinh chúng trừ khi policy nói rõ.

## 42. Elasticsearch/OpenSearch: bulk import và `search_after`

Với search index:

- `from + size` deep pagination thường đắt và có result window limits.
- `search_after` cùng sort key ổn định có thể duyệt sâu hiệu quả hơn.
- PIT (*point in time*) có thể giữ search view ổn định trong thời hạn phù hợp.
- Bulk API nhập documents nhanh hơn từng request nhỏ nhưng **mỗi item có status riêng**.

### Một bulk request minh họa

```text
{ "index": { "_index": "orders-v2", "_id": "O1" } }
{ "tenantId": "T01", "status": "PAID", "sourceRevision": 12 }
{ "index": { "_index": "orders-v2", "_id": "O2" } }
{ "tenantId": "T01", "status": "NEW", "sourceRevision": 3 }
```

Đây là NDJSON-like bulk payload minh họa; execution thực tế phải tuân byte framing/endpoint API và authentication. Kiểm tra per-item status, không chỉ HTTP 200.

### Stale overwrite

Chọn deterministic document IDs và source revision/versioning strategy. Một replay v8 sau v12 có thể ghi đè projection nếu unconditional index. Các cơ chế external versioning/optimistic concurrency (khi engine hỗ trợ) hoặc subscriber-side revision guard cần được thiết kế theo đúng API.

### “Imported” khác “search-visible”

Index API ACK xong chưa chắc query lập tức thấy data do refresh semantics. Verification phải đo **source-to-search-visible** và query correctness, không dùng bulk ACK làm điều kiện cutover duy nhất.

### Mapping và alias cutover

Một chiến lược:

```text
Existing alias "orders-search" -> index-v1
Import into index-v2
Verify index-v2
Replay remaining changes
Switch alias atomically if supported
```

Alias switch có thể atomically update routing metadata trong phạm vi API, nhưng phải đồng bộ với source writes/CDC/versioning để tránh target ngay lập tức tụt lại; không coi alias switch tự giải quyết mọi in-flight clients và write routing.

## 43. Graph và vector stores: vấn đề không chỉ là record count

Với graph:

- Có thể cần import nodes trước edges.
- Node IDs mới phải map đồng nhất trong mọi relationships.
- Edge uniqueness/direction, properties và tenancy phải đúng.
- Các lượt nhập có thể tạo dangling edges nếu checkpoint nodes/edges không phối hợp.
- Graph traversal correctness sau import quan trọng hơn số edges đã gửi.

Với vector store:

- Embedding dimension/model version phải phù hợp.
- Vector quantization/index build có thể diễn ra sau raw import.
- Search quality (recall@k, filters, metadata consistency) là điều kiện verification.
- Bulk vector ingestion có memory/index-compaction cost riêng.

### Mốc tiến độ riêng

```text
Nodes imported      100%
Edges imported       98%
Edge integrity       96%
Index built          70%
Query-ready           NO
```

Một job import graph/vector được coi hoàn thành chỉ khi **truy vấn đích hoạt động theo hợp đồng**, không chỉ khi số bytes đã ghi đạt estimate.

## 44. Schema migration trong lúc export/import

Nguồn có:

```json
{
  "orderId": "O1",
  "total": "123.45",
  "createdAt": "2026-11-14T09:00:00Z"
}
```

Target cần:

```json
{
  "_id": "O1",
  "totalMinorUnits": 12345,
  "currency": "VND",
  "createdAtEpochMillis": 1794646800000,
  "schemaVersion": 2
}
```

**Ví dụ trên chỉ để minh họa mapping fields; thời gian/số tiền cần conversion thật theo currency/timezone/business rules.** Với VND thường không có đơn vị lẻ thập phân như USD; không nên tự nhân mọi giá tiền với 100 mà không có currency exponent policy.

### Các vấn đề dễ bỏ qua

- Missing field khác `null` và empty string.
- Decimal precision/overflow, binary/UUID/ObjectId.
- Unicode normalization và collation.
- Timestamp timezone/time precision.
- TTL/expiry tính theo thời điểm nào.
- Nested arrays, free-text và schema version hỗn hợp.
- Partition/shard key mới và hot partitions.
- Historical event decoder vs new writer schema.
- Dữ liệu không còn hợp lệ theo validation mới.

### Transform phải versioned

Nếu code mapping được deploy từ v7 sang v8 giữa job, checkpoint cũ có thể đã nhập một nửa dữ liệu theo v7. Có thể:

1. Pin mapping version cho một run.
2. Hoặc lưu transform version per chunk và có reconciliation/upgrader rõ.
3. Hoặc restart/rebuild target staging generation mới.

Không đổi quy tắc mapping âm thầm mà vẫn giữ progress bar 80% như thể mọi records dùng cùng một contract.

## 45. Dữ liệu được xóa và tombstones: đừng hồi sinh records

Một online migration:

```text
T0 snapshot O1 revision=5 ACTIVE
T1 source DELETE O1 revision=6
T2 CDC applies DELETE O1 revision=6 to target
T3 slow snapshot worker retries UPSERT O1 revision=5
```

Nếu target đã xóa record và không giữ **version/tombstone**, lần upsert v5 có thể hồi sinh O1.

### Quy tắc

Giữ metadata cho source revision cao nhất đã áp:

```json
{
  "recordId": "O1",
  "sourceRevision": 6,
  "deleted": true
}
```

Một incoming revision 5 phải bị bỏ qua. Chỉ dọn tombstone sau khi chắc chắn không còn snapshot/CDC/retry có thể áp lại revision cũ theo **replay retention và migration lifecycle**.

### Không có tombstone miễn phí

Tombstone storage giữ extra state, cần TTL/compaction/retention và có thể gây write/read amplification. Chọn duration dựa trên **max replay window**; đừng xóa ngay khi UI không còn hiển thị item.

### Dữ liệu xóa vì privacy

Nếu một record có PII và bị xóa theo policy, các export files, DLQ, snapshots và target staging có thể vẫn giữ nội dung lịch sử. Migration phải phối hợp **deletion reconciliation và data disposition**, không chỉ apply delete vào live table.

## 46. TTL/expiry và thời gian tuyệt đối

Nguồn:

```text
Source record created 12:00, expires 13:00.
Export at 12:50, import at 13:10.
```

Nếu import lại `TTL=60 minutes`, record sống tới 14:10, **kéo dài vòng đời dữ liệu không đúng**.

### Thiết kế

- Xuất `expiresAt` absolute timestamp khi data model cho phép.
- Tại import: `remainingTTL = expiresAt - now`.
- Nếu remainingTTL không dương, bỏ/tombstone theo policy.
- Cân nhắc clock skew và precision.
- Với TTL source-specific không thể extract chính xác, phải định nghĩa approximate behavior và kiểm chứng.

### TTL vs vật lý

Một record hết hạn logic có thể chưa được thu hồi vật lý ngay; snapshots/CDC logs có retention riêng. Không dùng TTL để chứng minh dữ liệu đã xóa khỏi mọi bản sao.

### TTL và CDC

Một số TTL expiry không phát ra cùng loại event như delete thông thường, tùy engine/config. Nếu online migration dựa vào CDC, cần có chiến lược sync expiry/expireAt bên target.

## 47. Thứ tự events và causal dependencies khi import

Một số records độc lập có thể nhập song song:

```text
Order O1, Order O2, Order O3
```

Nhưng các sự kiện cho cùng entity cần ordering hoặc revision:

```text
O1 revision 1: NEW
O1 revision 2: PAID
O1 revision 3: CANCELED
```

Nếu worker async áp revision 3 trước 2 rồi 2 ghi đè 3, target sai.

### Các giải pháp

1. Serialize per entity key nếu throughput cho phép.
2. Dùng conditional sourceRevision max.
3. Dùng state-based snapshots thay vì delta-only events khi replay out-of-order.
4. Theo dõi sequence gaps nếu update phải áp theo thứ tự chính xác.

### Delta-only khó hơn full-state

```text
Inventory quantity +2
Inventory quantity -1
```

Không thể chỉ lấy max revision rồi skip event nhỏ hơn nếu thiếu một delta khiến kết quả cuối sai. Với delta-only, cần ordered application hoặc complete event history/ledger, và reconciliation với source.

### Cross-entity invariants

Order/Payment/Inventory có thể ở nhiều partitions. Dữ liệu cuối phải giữ quan hệ nghiệp vụ, không chỉ nhập từng document đúng. Có thể cần staging + transactionally coordinated cutover, foreign-key-like validation hoặc workflow compensation tùy data model.

## 48. Referential integrity cho denormalized read models

Một source:

```text
orders:          O1(customer=C1)
customers:       C1(name=N)
ordersByCustomer:C1 -> [O1]
searchIndex:     O1 + C1 summary
```

Khi nhập:

- Đơn O1 có thể đến trước khách hàng C1.
- Mapping customer IDs có thể đổi.
- Read model/index có thể được build sau.
- Event update khách hàng có thể đến giữa bulk import.

### Hai hướng

**Hướng A:** Nhập authoritative entities trước, sau đó rebuild derived models từ target.

**Hướng B:** Nhập đồng thời theo consistent source revisions/CDC, kiểm tra cross-reference invariants.

Hướng A thường dễ kiểm tra hơn nếu mục tiêu cuối là một read model có thể tái tạo. Nhưng phải dự toán thời gian rebuild/indexing và cutover.

### Checkpoints riêng

```text
customersImported = 100%
ordersImported = 100%
ordersByCustomerRebuilt = 92%
searchVisible = 75%
cutoverReady = false
```

Không gộp tất cả vào “target data migration 100%”.

## 49. Reconciliation: count bằng nhau chưa đủ

Hai datasets đều có 1 triệu records nhưng có thể khác:

```text
Source: O1, O2, O3, O4
Target: O1, O2, O3, O5
Count: 4 == 4
```

### Nhiều tầng verification

| Tầng | Kiểm tra | Giới hạn |
|---|---|---|
| Counts | Số records theo tenant/range/chunk | Không thấy record thay thế |
| IDs/keys | Set of keys hoặc hashed key sets | Chưa kiểm tra payload |
| Hash/checksum | Canonical normalized payload digest | Phải cùng canonicalization và snapshot |
| Field-level diff | Fields quan trọng/schema mapping | Tốn chi phí, có thể sampled |
| Revisions | Highest applied source revision, deletes | Cần revision semantics rõ |
| Business invariants | Unique, sums, references, authorization | Cần domain-specific logic |
| Query parity | So kết quả từ source và target | Cần account for consistency windows |

### Không so hash trên bytes thô khi schema đổi

Nếu JSON field order khác, `1.0` so với `1.00` hoặc timestamp precision khác, raw byte hash khác dù business data tương đương. Hãy xây **canonical representation** trước khi hash, theo mapping version và normalization rules.

### Tránh dùng một digest global không thể debug

Nếu global checksum khác nhưng không biết range nào sai, phải quét lại toàn bộ. Lưu **per-range/per-chunk digests**, counts và version; dễ khoanh vùng, rescan hoặc repair.

## 50. Sampling và full verification: chọn đúng mức tin cậy

Full compare mọi record rất tốn chi phí, nhưng một sampling 0.01% không đủ để bảo đảm **zero missing records**.

### Chính sách theo rủi ro

- Financial ledger/critical invariants: đối soát đầy đủ hoặc kiểm tra bằng protocol mạnh.
- Search read model: có thể kết hợp counts/hashes và query parity sampling, cùng chế độ repair.
- Analytics: kiểm tra aggregates/boundaries và sampling theo acceptance criteria.
- Migration cutover: những trường/IDs quyết định business correctness cần verification tương ứng.

### Sampling có thể lệch

Lấy 1.000 bản ghi đầu thường chỉ kiểm tra một key range, không phát hiện lỗi ở cuối hoặc một tenant nhỏ. Dùng stratified/range-aware sampling và special cases như null/missing, TTL, large docs, unicode.

### Snapshot boundary

So source live tại T2 với target snapshot T1 sẽ báo “mismatch” hợp lệ do source đã đổi. Verification phải biết **comparable data boundary** hoặc replay CDC tới cùng source revision trước khi so.

## 51. Cutover: đổi read/write authority sau khi đã đủ bằng chứng

Quy trình online migration có thể dùng:

```text
1. Build target staging from snapshot.
2. Continuously capture/replay CDC.
3. Validate target indexes and business invariants.
4. Observe CDC lag until within threshold.
5. Quiesce writes or perform agreed fencing/epoch barrier.
6. Establish final source position C.
7. Replay target through C and validate.
8. Switch routing/alias/authority under controlled protocol.
9. Monitor writes/reads, latency, integrity.
10. Retain rollback capability according to policy.
```

### Ai là source of truth?

Trước cutover, source thường là authority. Sau cutover, target có thể trở thành authority. Không để hai bên **cùng nhận authoritative writes** nếu chưa có conflict strategy, fencing và bidirectional sync.

### CDC lag = 0 chưa đủ

Một broker consumer có offset lag 0 nhưng:

- Source connector đã ngừng publish.
- Sink có pending index refresh.
- DLQ giữ một event bị lỗi.
- Projection có missing record.

Cutover phải dựa trên **source-to-target verified boundary** và ứng dụng query parity, không một metric đơn lẻ.

### Cutover là một protocol

Một DNS/feature flag flip có thể không ảnh hưởng ngay mọi JVM client/pool/cached endpoint. Phải đo clients trên cả old/new path và có cách chặn writes vào authority cũ.

## 52. Dual-write và lý do cần thận trọng

Một ứng dụng:

```text
Business write
    +-- write source
    +-- write target
```

Nếu source thành công, target fail, hai hệ lệch. Nếu retry target bằng thao tác non-idempotent, có thể trùng effect.

### Những phương án

- **Source-of-truth + CDC/outbox:** một authoritative write, downstream nhận changes/replay.
- **Dual-write có idempotency và reconciliation:** chấp nhận vận hành phức tạp, có queue để sửa lệch.
- **Transactional boundary chung:** chỉ khi engine/architecture thật sự hỗ trợ.

Không gọi hai lệnh write liên tiếp trong Java là “atomic dual-write”.

### Rollback khi đã có target-only writes

Sau cutover, target nhận writes mới. Nếu chuyển toàn bộ reads/writes về source cũ mà không replay ngược, những writes này **mất khỏi source**. Rollback phải:

1. Chặn/fence writers phù hợp.
2. Xác định target-only changes.
3. Reconcile/replay theo business ordering.
4. Verify source authority rồi mới route về.

Hoặc chọn **forward fix** thay vì rollback nếu reverse migration không đủ an toàn.

## 53. Shadow reads và query parity

Trước cutover có thể:

```text
Client request
  |
  +-- primary read source -> response to user
  |
  +-- shadow read target -> compare asynchronously
```

### Lợi ích

- Thử access patterns/indexes của target bằng traffic gần thực tế.
- Phát hiện missing IDs, pagination differences, sort/collation mismatches.
- Đo p95/p99 và read capacity của target.
- Không cần trả kết quả target cho user ngay.

### Điều kiện

- Shadow reads không gây side effects.
- Phải có traffic sampling/rate limit để không quá tải target.
- So sánh dựa cùng source revision/snapshot hoặc có tolerance cho eventual lag.
- Redact PII và dùng access controls.
- Không tự dùng target response nếu comparator fail, vì shadow stage chưa được phép phục vụ.

### Không dùng average latency

Target có average nhanh hơn nhưng p99 chậm 10 lần ở tenant lớn vẫn có thể fail SLO. Chạy query parity theo tenant tier, hot partition và endpoint class, không chỉ tổng hợp chung.

## 54. Rollback plan phải được viết trước cutover

Một runbook nên có:

```text
Before cutover:
  source authoritative and read/write
  target staging, CDC catch-up
  rollback = stop import and discard/rebuild target

During cutover:
  fence old writers, final boundary verification
  routing change guarded by generation
  rollback = controlled route reversal if safe

After target-only writes:
  rollback may require reverse sync/reconciliation
  or prefer forward fix
```

### Không giữ source cũ mãi mà không có policy

Sau migration, source có thể tốn chi phí, giữ PII lâu và thành đường truy cập không được patch/monitor. Decommission chỉ sau:

- Cutover stable qua observation window.
- Backup/restore và key retention phù hợp.
- Rollback window đã hết theo approval.
- Downstream consumers chuyển hết.
- Audit/data deletion obligations hoàn tất.

### Đừng xóa source khi target còn chưa verify

Các metrics `records_imported=100%` không thay thế verified business state. Nếu source bị xóa sớm, không còn authority để repair data inconsistencies.

## 55. Java 17: mô hình mốc resume theo range

Đầu tiên mô tả source item và state rõ nghĩa:

```java
import java.time.Instant;
import java.util.List;

record SourceRecord(
    String tenantId,
    String sourceId,
    long sourceRevision,
    boolean deleted,
    String payload
) {}

record SourcePage(
    List<SourceRecord> records,
    String nextToken
) {}

record RangeCheckpoint(
    String jobId,
    String rangeId,
    long ownerEpoch,
    long checkpointVersion,
    String nextPageToken,
    long confirmedRecords,
    Instant updatedAt
) {}
```

### Các trường có ý nghĩa gì?

- `jobId`: phân biệt migration runs; không dùng chung checkpoint giữa source/target generation khác nhau.
- `rangeId`: chia work theo partition/range; metadata ranh giới nằm trong job specification.
- `ownerEpoch`: bảo vệ trước worker cũ sau lease expiry.
- `checkpointVersion`: conditional update/CAS khi nhiều writes tới state.
- `nextPageToken`: vị trí mà source SDK hiểu **cần đọc tiếp**.
- `confirmedRecords`: đã có durable outcome theo contract, không phải count read.

### Không lưu field payload trong checkpoint

Payload có thể rất lớn và nhạy cảm. Chỉ lưu position, IDs/provenance và counters tối thiểu, được mã hóa/bảo vệ theo mức dữ liệu.

### Một giả định rõ

Ví dụ Java phía dưới giả định source paging token có thể dùng lại sau process restart và source read result không đổi trong snapshot của job. **Nếu engine không bảo đảm điều đó, phải thay token bằng stable keyset/snapshot protocol thích hợp.**

## 56. Java: giao diện nguồn, đích và checkpoint

```java
import java.util.List;

interface PageSource {
    SourcePage readPage(
        String rangeId,
        String nextPageToken,
        int maxRecords
    ) throws Exception;
}

record WriteOutcome(
    String sourceId,
    boolean durable,
    boolean retryable,
    String reason
) {}

interface IdempotentTarget {
    // Implementation must enforce source ID + tenant scope
    // and reject obsolete revisions/deletes.
    List<WriteOutcome> applyBatch(
        List<SourceRecord> records
    ) throws Exception;
}

interface DurableCheckpointStore {
    RangeCheckpoint load(
        String jobId,
        String rangeId
    ) throws Exception;

    // Atomic compare-and-set; false means version/owner changed.
    boolean saveIfVersionMatches(
        RangeCheckpoint expected,
        RangeCheckpoint updated
    ) throws Exception;
}
```

### Hợp đồng quan trọng

`IdempotentTarget.applyBatch` **không chỉ gửi requests**. Khi trả `durable=true` cho item, adapter phải xác nhận outcome bền theo target API và write concern đã định.

`DurableCheckpointStore.saveIfVersionMatches` phải thực hiện **atomic conditional update**, không phải:

```text
read checkpoint version
if version looks equal:
    blind write
```

vì hai workers có thể cùng đọc version cũ rồi ghi đè nhau.

### Có thể dùng loại storage nào?

MongoDB conditional update, DynamoDB conditional update, SQL transaction, một consistent metadata service hoặc object-store conditional ETag/generation **nếu API và quyền sở hữu cung cấp CAS thật**. Không tự gán tính atomicity cho một file JSON trên shared volume nếu filesystem/protocol không bảo đảm.

## 57. Java 17: vòng xử lý page đơn giản có checkpoint sau write

Đây là **bộ khung học tập**, cố ý chạy tuần tự mỗi page để dễ thấy ranh giới; production cần cancellation, retry policy, byte limits và observability.

```java
import java.time.Instant;
import java.util.List;

public final class ResumablePageWorker {
    private final PageSource source;
    private final IdempotentTarget target;
    private final DurableCheckpointStore checkpoints;

    public ResumablePageWorker(
        PageSource source,
        IdempotentTarget target,
        DurableCheckpointStore checkpoints
    ) {
        this.source = source;
        this.target = target;
        this.checkpoints = checkpoints;
    }

    public void runOnePage(
        String jobId,
        String rangeId,
        int pageSize
    ) throws Exception {
        RangeCheckpoint current =
            checkpoints.load(jobId, rangeId);

        SourcePage page = source.readPage(
            rangeId, current.nextPageToken(), pageSize
        );

        List<SourceRecord> records = page.records();
        List<WriteOutcome> outcomes =
            target.applyBatch(records);

        if (outcomes.size() != records.size()) {
            throw new IllegalStateException(
                "Target must report one outcome per input record"
            );
        }

        for (int i = 0; i < records.size(); i++) {
            if (!records.get(i).sourceId().equals(
                    outcomes.get(i).sourceId())
                || !outcomes.get(i).durable()) {
                throw new IllegalStateException(
                    "Page not fully durable; checkpoint unchanged"
                );
            }
        }

        // Only after ALL page items have durable outcomes.
        RangeCheckpoint next = new RangeCheckpoint(
            current.jobId(),
            current.rangeId(),
            current.ownerEpoch(),
            current.checkpointVersion() + 1,
            page.nextToken(),
            current.confirmedRecords() + records.size(),
            Instant.now()
        );

        boolean stored = checkpoints.saveIfVersionMatches(
            current, next
        );
        if (!stored) {
            throw new IllegalStateException(
                "Checkpoint owner/version changed"
            );
        }
    }
}
```

### Vì sao checkpoint sau target write?

Nếu crash trước `applyBatch`, checkpoint không tiến. Nếu crash sau sink commit trước `saveIfVersionMatches`, page được replay và `IdempotentTarget` phải đảm bảo không tạo side effects trùng.

### Những giả định cần thay trong production

1. `WriteOutcome` được trả **cùng thứ tự inputs** theo giao diện; một số bulk APIs không bảo đảm thế, nên adapter phải map bằng deterministic item key/index.
2. Source token có thể null khi hết dữ liệu; phải có explicit `hasMore`/EOF state để không đọc lại page đầu.
3. Item-level partial success cần một loop retry/quarantine có budget hoặc checkpoint theo prefix; mẫu này **không tiến cả page** nếu có bất kỳ lỗi nào.
4. Nếu records trùng `sourceId` ở nhiều tenants, mapping phải dùng composite identity để tránh ghép nhầm.
5. `ownerEpoch` cần được check trong checkpoint CAS, và target phải bảo vệ stale worker writes khi necessary.
6. `pageSize > 0`, memory/bytes budget và timeouts phải được validate.
7. Nếu source page thay đổi giữa retries, same token có thể trả nội dung khác; điều kiện snapshot là bắt buộc cho lập luận này.
8. `confirmedRecords` là counter từng page thành công; nếu state metadata update trả unknown, đọc lại checkpoint trước khi retry.

## 58. Java: cursor EOF và explicit terminal status

Một lỗi phổ biến:

```text
nextToken = null
persist checkpoint
restart job
readPage(null) => first page again
```

Nếu source API dùng null là **bắt đầu từ đầu**, không thể dùng null vừa đại diện “hết dữ liệu” vừa đại diện “trang đầu”.

### Thiết kế

```java
enum RangeState {
    NEW,
    IMPORTING,
    EOF_REACHED,
    VERIFYING,
    VERIFIED,
    FAILED
}

record RangeProgress(
    String jobId,
    String rangeId,
    RangeState state,
    String nextPageToken,
    String lastDurableKey,
    long ownerEpoch,
    long checkpointVersion
) {}
```

### Hợp đồng

- `NEW` + token null: bắt đầu page đầu.
- `IMPORTING` + token: tiếp tục.
- `EOF_REACHED`: không gọi source read thêm.
- `VERIFYING`: kiểm tra correctness, có thể quay lại repair.
- `VERIFIED`: range hoàn tất.

Khi source trả **empty items nhưng next token vẫn có**, không đánh dấu EOF. Đặc biệt quan trọng với APIs có filter sau giới hạn đọc như DynamoDB.

### Empty page và bộ đếm vòng lặp

Một số source có thể trả nhiều empty pages liên tiếp. Loop phải theo token state, đồng thời có safeguards cho **token không tiến** hoặc API trả lặp đúng token vô hạn, để phát hiện lỗi protocol mà không silently skip.

## 59. Java 17: tính contiguous prefix cho imports song song

Khi import song song, kết quả có thể về không theo thứ tự. Ví dụ từ offset 20:

```text
Completed order:
  20, 23, 22, 24, 21, 25
```

Mốc có thể checkpoint:

| Sau khi hoàn thành | Đã durable | Next safe offset |
|---|---|---:|
| Ban đầu | Không | 20 |
| 20 | {20} | 21 |
| 23 | {20,23} | 21 |
| 22 | {20,22,23} | 21 |
| 24 | {20,22,23,24} | 21 |
| 21 | {20..24} | 25 |
| 25 | {20..25} | 26 |

Một class minh họa:

```java
import java.util.HashSet;
import java.util.Set;

public final class ContiguousProgress {
    private long nextUncommitted;
    private final Set<Long> finishedOutOfOrder =
        new HashSet<>();

    public ContiguousProgress(long initialOffset) {
        if (initialOffset < 0) {
            throw new IllegalArgumentException("initialOffset");
        }
        this.nextUncommitted = initialOffset;
    }

    public synchronized long markDurable(long offset) {
        if (offset < nextUncommitted) {
            return nextUncommitted; // already committed prefix
        }
        finishedOutOfOrder.add(offset);
        while (finishedOutOfOrder.remove(nextUncommitted)) {
            nextUncommitted++;
        }
        return nextUncommitted;
    }

    public synchronized long nextUncommittedOffset() {
        return nextUncommitted;
    }
}
```

### Giới hạn

Class giữ state ở RAM, **không phải durable checkpoint store**. Khi crash, offset có thể lùi và replay. Phải lưu `nextUncommitted` bền sau khi sink outcomes được xác nhận.

Nếu một offset bị lỗi vĩnh viễn, không được bỏ qua trừ khi có **terminal quarantine** được policy công nhận và đã lưu bền. Cần giới hạn số in-flight offsets để Set không tăng vô hạn.

Một offset cũng chỉ có nghĩa trong **một partition/range**; không dùng số max offset toàn bộ Kafka topic làm một checkpoint chung.

## 60. Java: batcher giới hạn count và bytes

Một utility dùng cho import:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.ToLongFunction;

public final class BoundedBatcher<T> {
    private final int maxItems;
    private final long maxBytes;
    private final ToLongFunction<T> byteEstimator;
    private final List<T> pending = new ArrayList<>();
    private long pendingBytes;

    public BoundedBatcher(
        int maxItems,
        long maxBytes,
        ToLongFunction<T> byteEstimator
    ) {
        if (maxItems <= 0 || maxBytes <= 0) {
            throw new IllegalArgumentException("limits");
        }
        this.maxItems = maxItems;
        this.maxBytes = maxBytes;
        this.byteEstimator = byteEstimator;
    }

    public synchronized List<List<T>> add(T item) {
        long bytes = byteEstimator.applyAsLong(item);
        if (bytes <= 0 || bytes > maxBytes) {
            throw new IllegalArgumentException("oversized item");
        }

        List<List<T>> flushed = new ArrayList<>();
        if (!pending.isEmpty() &&
            (pending.size() >= maxItems
                || pendingBytes + bytes > maxBytes)) {
            flushed.add(drain());
        }

        pending.add(item);
        pendingBytes += bytes;

        if (pending.size() >= maxItems) {
            flushed.add(drain());
        }
        return flushed;
    }

    public synchronized List<T> flush() {
        return drain();
    }

    private List<T> drain() {
        if (pending.isEmpty()) return List.of();
        List<T> batch = List.copyOf(pending);
        pending.clear();
        pendingBytes = 0;
        return batch;
    }
}
```

### Hạn chế của ví dụ

- Không có max-wait timer, do đó cần flush khi kết thúc range hoặc scheduled deadline.
- `byteEstimator` chỉ ước lượng bytes; phải có margin so với request size hard limits.
- Buffer RAM không durable; crash trước write cần replay từ source checkpoint.
- Không dùng batcher output như bằng chứng sink write thành công.
- Với item size biến thiên, có thể cần byte-weighted semaphore/queue bên cạnh count limit.
- Nếu byteEstimator trả giá trị quá lớn gây overflow cộng, thực tế cần safe arithmetic/validation.

## 61. Java 17: giới hạn concurrency cho writer

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Semaphore;

interface AsyncTarget<T> {
    CompletableFuture<Void> writeDurably(List<T> items);
}

public final class LimitedDispatcher<T> {
    private final Semaphore permits;
    private final AsyncTarget<T> target;

    public LimitedDispatcher(
        int maxInFlight,
        AsyncTarget<T> target
    ) {
        if (maxInFlight < 1) {
            throw new IllegalArgumentException("maxInFlight");
        }
        this.permits = new Semaphore(maxInFlight);
        this.target = target;
    }

    public CompletableFuture<Void> send(List<T> items)
        throws InterruptedException {
        permits.acquire();
        List<T> batch = List.copyOf(items);

        try {
            CompletableFuture<Void> future =
                target.writeDurably(batch);
            return future.whenComplete(
                (ignored, error) -> permits.release()
            );
        } catch (RuntimeException ex) {
            permits.release();
            throw ex;
        }
    }
}
```

### Bài học từ code

- `Semaphore` tạo **backpressure** cho producer thread.
- Permit được release khi future hoàn tất theo giao diện sink.
- Caller **phải giữ/await futures** để biết errors; không tiến checkpoint khi chỉ mới dispatch.
- Timeout/cancel của future không nhất thiết rollback remote write; unknown outcome cần reconciliation.
- Nếu future never completes, permit có thể bị giữ mãi; cần deadline/cancellation policy.
- In-flight batches limit không đồng nghĩa bytes limit; kết hợp bounded byte budget.
- Khi reassign range, fencing/idempotency ở target vẫn bắt buộc.

Không coi đoạn code này là production-ready ingestion framework; nó minh họa ranh giới cần bảo vệ.

## 62. Java: checkpoint CAS và ambiguous metadata commit

Giả sử target batch đã commit và job lưu checkpoint:

```text
CAS checkpoint version=20 -> 21
Metadata store commits
Response lost
Worker sees timeout
```

Worker không thể khẳng định CAS fail. Cách xử lý:

1. Đọc lại checkpoint bền.
2. Nếu version=21, ownerEpoch và next token khớp expected state → đã hoàn tất.
3. Nếu version=20 → có thể retry CAS, theo policy.
4. Nếu ownerEpoch đã đổi/version khác → worker không còn quyền; dừng và báo controller.
5. Nếu metadata store unavailable → giữ job ở unknown state và retry/reconcile, không lập checkpoint mới tùy ý.

### Tránh duplicate progress

Counters tăng bằng `+batchSize` trong một CAS retry mù có thể tăng hai lần nếu save đã thành công trước đó. Metadata update nên set **expected cumulative count** từ một state version cụ thể, chứ không cộng tự do mỗi lần retry.

### Source API token có state

Ngay cả khi checkpoint CAS thành công, nếu source cursor token là session-local và hết hạn khi worker restart, vẫn phải có một **recovery fallback** như stable keyset hoặc job resnapshot, không “tiếp tục” bằng token vô hiệu.

## 63. Pause và resume theo giao thức, không chỉ kill process

Một operator nhấn “Pause” khi job đang có 10 batches in-flight. Nếu worker lập tức kill mà không có state management, lần sau phải xử lý nhiều outcome unknown.

### Graceful pause

```text
PAUSE_REQUESTED
   |
   v
Stop fetching new pages
   |
   v
Let in-flight writes settle up to deadline
   |
   v
Checkpoint confirmed contiguous prefixes
   |
   v
Release/expire range leases
   |
   v
PAUSED
```

### Force cancel

Nếu job treo không thể graceful:

- Ghi controller state `CANCELING`.
- Ngăn cấp new ranges/epochs.
- Hủy futures/cursors/requests được phép.
- **Không suy cancel là rollback DB writes**.
- Kiểm tra/reconcile ambiguous outcomes khi resume.
- Thu hồi short-lived credentials khi cần.

### Resume

Trước khi resume:

1. Xác minh source identity/snapshot/log position còn hợp lệ.
2. Xác minh target generation và mapping version không đổi trái policy.
3. Kiểm tra ranges nào VERIFIED, retryable hoặc unknown.
4. Cấp ownerEpoch mới.
5. Chạy lại các records/chunks chưa hoàn tất bằng idempotent operations.
6. Đo kết quả sau khi resume có đạt progress và data correctness.

## 64. Upgrade code trong lúc job đang chạy

Một migration kéo dài nhiều ngày có thể gặp deploy worker version mới.

### Các metadata cần version

```text
source schema version
target schema version
mapping/transform version
checkpoint serialization version
manifest format version
driver SDK version
chunk encryption/compression version
```

### Chiến lược

- **Pin version per run:** không nâng mapper giữa chừng; deploy worker mới tương thích cùng schema.
- **Versioned checkpoints:** có khả năng đọc checkpoint cũ và transform theo mapping đã ghi.
- **Restart new generation:** nếu semantic mapping thay đổi lớn, xây target staging mới rồi cutover lại.

### Không đổi token format âm thầm

Một opaque paging token từ SDK version khác không đảm bảo decode/restore được. Khi upgrade SDK, kiểm tra documentation và khả năng resume; nếu không có bảo đảm, checkpoint nên lưu stable boundary hoặc kế hoạch restart range.

### Rolling deployment

Hai versions cùng xử lý ranges phải dùng **owner epoch + CAS** và data version guards. Đừng để old worker overwrite target state của new worker.

## 65. Tính chi phí và ảnh hưởng lên source đang phục vụ

Bulk export có thể gây:

- Full scans làm disk I/O/cache pressure.
- Cross-shard fan-out.
- Replication lag/compaction pressure.
- Network egress cost.
- Đọc snapshot quá lâu giữ resources/retention.
- Lock/transaction overhead nếu snapshot isolation dùng long transaction.

Bulk import có thể gây:

- Target write units/IOPS cao.
- Write amplification từ indexes.
- Compaction/flush/GC.
- Network ingress và disk capacity.
- Index build và query latency tạm thời.

### Đặt budget

```text
Source read budget: bounded QPS/bytes/s
Target write budget: bounded ops/s or capacity units
Max concurrent partitions: measured limit
Allowed p99 impact on production: pre-agreed SLO
Max retry amplification: bounded
Max source log retention headroom consumption: monitored
```

### Không chỉ đo job throughput

Một job nhập 100.000 rows/s nhưng làm checkout p99 vượt SLO **không phải tối ưu thành công**. Cần theo dõi **interactive workloads** và có admission control/schedule/traffic shaping.

## 66. Bảo mật trong export/import và checkpoint

Đích export có thể là object storage, file system, stream broker hoặc workspace CI. Tất cả bản copy phải được phân loại theo nội dung, không theo tên “temporary”.

### Một data-flow an toàn

```text
Approved source access
    |
    v
Worker with short-lived identity
    |
    v
TLS + minimal projection
    |
    v
Encrypted temp/chunk output
    |
    v
Private object storage + KMS + scoped IAM
    |
    v
Authorized import worker
    |
    v
Target with tenant ACL and audit
```

### Kiểm soát

- Export approval, purpose, data minimization và region policy.
- Least privilege cho source read, target write, KMS decrypt.
- Encryption at rest/in transit, integrity/authenticity cho manifests.
- Không đặt secrets trong checkpoint, log, filenames, pre-signed URLs.
- Không lưu raw PII trong metrics/alerts.
- Quarantine/DLQ cũng cần encryption, retention và scope quyền.
- Object versions/replicas, stale dumps và snapshot copies cần lifecycle.
- Tách credentials và buckets staging/prod.
- Ghi audit cho export, download, restore, cutover, rollback.

### Snapshot có thể chứa nhiều tenants

Một physical snapshot/table export thường không bảo đảm chỉ chứa tenant mà người request được phép xem. Nếu chỉ cần subset, dùng logical extraction có scope và validation, không chia sẻ toàn volume snapshot.

### Xóa dữ liệu trong lúc migration

Data deletion/consent revocation có thể đòi sync tới target trước cutover, và xử lý exports/chunks cũ theo retention policy. Một successful import không tự làm những copies trung gian hết nhạy cảm.

## 67. Monitoring và cảnh báo có thể hành động

| Signal | Ý nghĩa | Khi cần hành động |
|---|---|---|
| `last_durable_checkpoint_age` | Mốc bền không tiến | Worker kẹt hoặc sink failure |
| `read_minus_committed_records` | Backlog giữa reader và writer | Queue tăng, memory risk |
| `retry_rate` | Requests phải retry | Throttling/network/unknown outcomes |
| `partial_batch_errors` | Items không hoàn tất trong bulk | Phân loại retry/permanent |
| `unknown_commit_outcomes` | Sink outcome mơ hồ | Reconcile, không mark completed |
| `quarantined_records` | Items chưa nhập theo policy | Cutover có bị block không? |
| `source_log_retention_headroom` | Còn bao lâu có thể resume CDC | Nguy cơ resnapshot |
| `cdc_oldest_unapplied_age` | Freshness lag | Tiến đến/lố SLO |
| `worker_lease_expirations` | Ownership thay đổi liên tục | Worker/pool/network health |
| `checkpoint_cas_conflicts` | Worker tranh quyền ghi progress | Fencing/rebalance |
| `snapshot_expiry_remaining` | Snapshot/PITR sắp hết hiệu lực | Nguy cơ không thể resume |
| `bytes_in_flight` | Memory/network pressure | Backpressure |
| `verified_chunk_ratio` | Verification tiến đến đâu | Điều kiện cutover |
| `source_target_mismatch_count` | Correctness violations | Điều tra/repair |
| `interactive_p99_during_migration` | Tác động production | Throttle/pause job |

Các metric names là ví dụ, không phải built-in của engine.

### Alerts đúng mục tiêu

**Nên cảnh báo** khi job không tiến trong thời gian vượt error/recovery budget, source log sắp hết retention, xuất hiện non-reconcilable data mismatch hoặc tải job gây user SLO violation.

**Không nên page** chỉ vì một batch retry thành công hoặc cursor đổi token bình thường. Dùng grouping theo `jobId, range class, error category` thay vì mỗi source record ID.

### Missing telemetry

Nếu worker/exporter chết, metrics có thể biến mất và query error rate trả rỗng. Có worker heartbeat/job progress no-data alert độc lập; không coi missing = healthy.

## 68. Runbook: job dừng tiến độ

Tình huống:

```text
job.state=IMPORTING
lastDurableCheckpointAge=45m
recordsRead increasing
recordsCommitted flat
retryRate increasing
```

### Các bước

1. Xác minh jobId/source/target generation và ownership hiện tại.
2. Kiểm tra source read latency, token validity, snapshot/log retention.
3. Kiểm tra sink throttling, index build, disk/CPU/connection pool.
4. Xem partial successes và queue bytes/in-flight batches.
5. Xác định exception transient hay permanent schema error.
6. Nếu source log headroom thấp, ưu tiên bảo tồn history/resnapshot plan.
7. Throttle/pause job nếu đang ảnh hưởng service production.
8. Reconcile unknown outcomes trước khi resume/skip.
9. Kiểm tra checksum/row counts và target data versions.
10. Resume từ checkpoint bền, có idempotency.

### Không làm

- Tăng concurrency đến vô hạn vì “job quá chậm”.
- Tự set progress=100% hoặc nhảy checkpoint qua errors.
- Xóa checkpoint để chạy lại không kiểm tra existing sink effects.
- Skip poison records và không lưu bằng chứng.
- Xóa source logs/old target trước khi confirm correctness.

### Sau sự cố

Ghi root cause, số records impacted, time to recovery, retries, mismatches và thay đổi runbook/metrics.

## 69. Runbook: không biết write batch đã thành công hay chưa

```text
Batch B42 sent
Connection lost
Target response unknown
```

Không coi mọi item fail. Quy trình:

1. Lấy immutable batch/chunk ID và danh sách source IDs/revisions từ manifest.
2. Query target bằng identity/tenant/version, nếu API/source consistency cho phép.
3. Phân loại mỗi item: already correct, stale, missing, conflicting, unknown.
4. Retry **missing/retryable** bằng deterministic keys/conditional update.
5. Quarantine conflicts cần manual resolution, không overwrite mù.
6. Chỉ mark chunk complete khi mọi item có terminal durable outcome phù hợp.
7. Lưu checkpoint CAS và ghi evidence.

### Nếu target không cho query tất cả IDs?

Thiết kế migration phải cung cấp cơ chế khác: per-item ledger, conditional write, immutable chunk-generation hoặc idempotent full replay. Không nên phát hiện giữa disaster rằng không có cách biết một write đã commit.

### Tránh “read target rồi quyết định insert” không atomic

Hai workers có thể cùng thấy item missing rồi cùng insert. Cần uniqueness/conditional put/CAS ở **authority**, không chỉ client-side precheck.

## 70. Runbook: source paging token hết hạn

```text
Checkpoint contains token T at 70% progress
Resume call -> TOKEN_EXPIRED
```

Các câu hỏi:

1. Token gắn server cursor đã hết TTL hay source history đã bị truncate?
2. Snapshot S còn có thể được dựng/đọc không?
3. Có stable last durable key để seek?
4. Query identity/filter/sort có đổi không?
5. Data range còn đúng sau reshard/topology change không?

### Các phương án

- Nếu có snapshot/keyset stable: restart range từ **last durable key** theo same snapshot.
- Nếu token không còn nhưng đã có immutable chunk files: resume **import từ sealed manifest**, không cần đọc lại source.
- Nếu source historical boundary đã mất: dừng online catch-up, lấy **new consistent snapshot + new CDC boundary**, rebuild/reconcile target theo protocol.

### Không tự reset token sang null

Token null có thể nghĩa “trang đầu”. Một worker tự reset và ghi checkpoint là một hành vi không kiểm soát được duplicate/gap. Nếu bắt buộc restart range, thay generation/epoch, log reason và dùng idempotency.

## 71. Runbook: verification mismatch sau import

Một bảng:

```text
Source snapshot:
  range A count=10,000 hash=H1

Target:
  range A count=10,000 hash=H2

H1 != H2
```

### Triage

- Canonicalization/field mapping có giống không?
- Source và target được so ở cùng snapshot/revision boundary không?
- Có null/missing, Decimal, timezone, Unicode khác semantics?
- Có TTL expiry/deletes/CDC update trong lúc compare?
- Có id collisions hoặc tenant scope mistakes?
- Chunk file có checksum/integrity đúng không?
- Target có stale overwrites hoặc partial errors?

### Repair

1. Khoanh vùng theo range/chunk ID.
2. Diff keys và canonical records có quyền truy cập phù hợp.
3. Định danh missing/extra/stale records.
4. Replay/replace **có version guard** hoặc rebuild range từ snapshot.
5. Chạy lại verification.
6. Chỉ cutover khi acceptance criteria đạt, hoặc documented exception được phê duyệt.

Không sửa hash trong manifest để làm bảng xanh. Nếu mismatch do transformation semantics được duyệt, phải **đổi canonicalization/version** và kiểm tra lại, không đổi expected value tùy tiện.

## 72. Fault injection: thử những cửa sổ nguy hiểm

Diễn tập trên lab/staging với synthetic data, không phá production không có phê duyệt.

| Fault đặt tại | Kỳ vọng |
|---|---|
| Sau source read, trước transform | Replay an toàn |
| Sau transform, trước target write | Checkpoint không tiến |
| Sau sink commit, trước checkpoint | Replay không tạo duplicate/stale overwrite |
| Sau checkpoint CAS commit, trước ACK | Re-read metadata, không đếm trùng |
| Partial bulk success | Retry đúng failed items hoặc replay idempotent |
| Worker lease hết hạn khi paused | Old worker bị fence |
| Cursor/token hết hạn sau restart | Dừng/rebuild theo protocol |
| Crash trong lúc object chunk upload | Không publish incomplete chunk |
| Chunk upload thành công, manifest chưa ghi | Reconcile orphan chunk |
| Manifest sealed, một chunk missing | Integrity validation chặn import |
| Source reshard/recreate | Source identity mismatch được phát hiện |
| Target đổi mapping version giữa run | Không trộn silently |
| Import batch chứa oversized record | Quarantine/fail theo policy, không OOM |
| Source filter trả empty page + next token | Không coi EOF |
| CDC snapshot và update đồng thời | Không stale overwrite |
| Delete event trước snapshot row cũ | Tombstone ngăn hồi sinh |
| Source log retention quá ngắn | Recovery-required, không silently skip |
| Target disk/throughput bị throttle | Backpressure, không làm hỏng source SLO |
| Network mất ở lúc cutover | Old/new authority fencing, no split-brain |
| Restore target backup trước cutover | Reconcile target checkpoint và output |
| Cancel job khi 20 batches in-flight | Terminal state có unknown outcomes rõ |
| Export PII sang đích sai | Authorization/policy chặn, audit incident |

### Điều kiện đánh giá

Một test chỉ có kết quả “worker restart thành công” là chưa đủ. Cần chứng minh:

- Không mất acknowledged business records/required changes.
- Không tạo duplicate effects không được phép.
- Checkpoint không vượt dữ liệu chưa durable.
- Token/source generations đúng.
- Target query/read model đúng sau recovery.
- Resource pressure nằm trong giới hạn.
- Progress metrics và alerts phản ánh sự thật.

## 73. Mẫu báo cáo sau diễn tập

```text
Job: MIG-007
Environment: isolated preproduction
Source boundary: snapshot S + CDC position C
Fault: worker killed after sink batch commit before checkpoint
Expected: replay same page, no duplicated logical records

Observed (hypothetical):
  source records in test range: 10,000
  first attempt durably applied: 9,950
  commit ACK lost for some items: 50
  replayed from last checkpoint: 500
  final target unique records: 10,000
  data mismatches after verify: 0
  checkpoint owner/version: expected
  PII leak or unauthorized export: none

Verdict: PASS for specified scenario only
Follow-up: test changing source schema and token expiry
```

Các con số trên là **giả định**, không phải benchmark thực. Một pass chỉ áp cho fault scope và conditions đã thực sự kiểm tra, không chứng minh mọi migration hay mọi engine sẽ đúng.

## 74. Case study A: checkpoint đã tiến trước khi target commit

Một chương trình cũ:

```text
READ page 1: O1..O100
SAVE nextToken=T2
SEND bulk write O1..O100
CRASH after first 60 writes
```

Khi chạy lại từ T2, records O61..O100 không được gửi lại. Job có thể báo “đã duyệt hết nguồn” nhưng target thiếu 40 records.

### Tìm và sửa

1. Chặn cutover.
2. Dùng manifest/source snapshot/range để tìm đoạn thiếu.
3. Reconcile O1..O100 theo target key/revision.
4. Replay missing records bằng idempotent writes.
5. Đổi protocol: **chỉ checkpoint sau sink durable success**.
6. Thêm fault test crash đúng cửa sổ checkpoint-before-write.

### Bài học

Đây là **data loss do sai commit ordering**, không phải chỉ là một lỗi của retry/backoff. Tăng số worker sẽ không sửa nó.

## 75. Case study B: crash sau commit tạo duplicate side effects

Một migration chuyển event delta `InventoryAdjusted(+5)` bằng thao tác target `INCR`:

```text
T0 sink INCR +5 commits
T1 worker crashes before checkpoint
T2 worker restarts and replays +5
Target counter increased by +10
```

### Cách sửa

- Tạo stable event ID từ source change position/operation ID.
- Dùng unique processed-event ledger **atomic với counter mutation** trong một supported transaction/conditional protocol.
- Hoặc dựng target state từ authoritative absolute balance/revision, nếu business cho phép.
- Reconcile result sau import.

### Điểm cần nhớ

“Cùng document ID” không giúp `INCR` idempotent. **Ghi trạng thái tuyệt đối có version** và **áp delta có ledger** là hai thiết kế khác nhau.

## 76. Case study C: source thay đổi trong lúc quét bằng offset

Ban đầu:

```text
Ordered records: A,B,C,D,E,F
Page 1 skip=0 limit=3 -> A,B,C
```

Một writer insert X vào đầu:

```text
Now: X,A,B,C,D,E,F
Page 2 skip=3 limit=3 -> C,D,E
```

C bị đọc hai lần. Nếu một record trước cursor bị xóa, có thể bỏ một record khác.

### Thay đổi

- Dùng snapshot-consistent read hoặc immutable keyset/partitioned traversal.
- Nếu source đang ghi, phối hợp CDC boundary.
- Dedup ở target không thay thế phương pháp đảm bảo không **bỏ sót**.
- Chứng minh coverage bằng verification, không chỉ count pages.

## 77. Case study D: job đạt 100% nhưng search vẫn không dùng được

```text
Imported documents: 100%
Search mapping/index build: 60%
Source-to-search visible lag: 15 minutes
Query parity pass rate: 82%
Operator dashboard: "COMPLETE"
```

### Lỗi

Dashboard dùng `records_attempted` hoặc `records_written` làm tiến độ toàn job. Chưa kiểm tra query-visible correctness, CDC catch-up và target readiness.

### Sửa

Đặt phases riêng:

```text
EXPORT_COMPLETE
IMPORT_COMPLETE
INDEX_READY
CDC_CAUGHT_UP
VERIFIED
CUTOVER_READY
```

Chỉ khi mỗi phase đáp ứng acceptance criteria, controller mới cho phép cutover. Nếu một phase fail, tiếp tục repair/rollback, không sửa percentage.

## 78. Case study E: token cũ được dùng sau khi source recreate

Một source collection được drop/recreate cùng tên `orders`, nhưng ID và shard layout mới khác. Worker còn một checkpoint chứa source token T của collection cũ.

Nếu chỉ kiểm tra collection name, nó có thể resume tại position không còn ý nghĩa, dẫn đến missing/duplicates.

### Sửa

- Lưu source cluster/table incarnation hoặc snapshot generation khi engine cung cấp.
- Ràng buộc checkpoint với query fingerprint và schema version.
- Khi identity mismatch, dừng và tạo new run/snapshot; không tự assume token còn hợp lệ.
- Không viết target bằng source revision không thuộc cùng generation.

### Bài học

**Đường dẫn tài nguyên giống nhau không có nghĩa cùng một dataset**.

## 79. Ba mươi bài tập thực hành

### Bài 1 — Bốn mốc tiến độ

Một batch có 500 records đã được đọc, 497 transform thành công, 495 sink ACK bền, 2 lỗi tạm thời. Bạn sẽ báo `read`, `transformed`, `applied` và `checkpointed` thế nào? Có được báo hoàn tất batch không?

### Bài 2 — Crash window

Mô tả hậu quả nếu worker lưu continuation token của page tiếp theo **trước khi** gửi bulk import. Thiết kế protocol an toàn và test tương ứng.

### Bài 3 — Ambiguous commit

Target đã commit 40/50 documents rồi connection timeout. Không biết 10 documents còn lại có commit hay không. Những thông tin/IDs nào cần để reconcile mà không tạo bản ghi trùng?

### Bài 4 — Idempotency

Một migration replay event `$inc amount +10` sau crash. Vì sao deterministic document key chưa đủ? Đề xuất ledger transaction hoặc absolute revision state.

### Bài 5 — Last-key semantics

Source sort `createdAt DESC, id DESC`. Hãy viết predicate cho page kế tiếp và giải thích vì sao timestamp không unique khiến chỉ lưu timestamp không đủ.

### Bài 6 — Offset bị dịch

Với source records A..F và page size 3, chèn X ở đầu giữa hai lần `skip/limit`. Xác định duplicate/missing và đề xuất keyset + snapshot/CDC.

### Bài 7 — Opaque token

Một paging token được tạo từ Query tenant T01 nhưng worker dùng cho tenant T02. Những metadata nào trong checkpoint/query fingerprint phải giúp phát hiện?

### Bài 8 — Range partition

Một dataset chia A:[0,100), B:[100,200), C:[200,300). Worker B crash sau khi commit key 150; worker C đã xong. Vì sao global checkpoint=300 không hợp lệ?

### Bài 9 — Hot range

90% records tập trung trong một range, ba ranges còn lại rất nhỏ. Đề xuất adaptive range splitting và cách bảo vệ ownership/checkpoint khi chia thêm workers.

### Bài 10 — Fencing

Worker W1 epoch 7 bị pause; W2 epoch 8 xử lý xong rồi W1 tỉnh lại. Hãy chỉ ra hai chỗ cần kiểm soát stale write: **target data** và **checkpoint store**.

### Bài 11 — Keyset không phải snapshot

Một record đã được scan rồi bị update sort key sang vị trí sau checkpoint. Có thể đọc lại hoặc bỏ sót record khác không? Điều gì giúp business đạt consistent export?

### Bài 12 — Snapshot/CDC boundary

Full scan bắt đầu 09:00, xong 09:40, CDC bắt đầu từ 09:41. Writer update record đã scan lúc 09:20. Tại sao mất cập nhật và nên capture từ mốc nào?

### Bài 13 — Stale overwrite

Target đã nhận O1 revision 12 từ CDC, sau đó bulk snapshot retry O1 revision 8. Viết quy tắc conditional write để target vẫn ở revision 12.

### Bài 14 — Tombstone

Delete O1 revision 15 đến trước snapshot O1 revision 10. Nếu hard delete O1 rồi upsert v10, chuyện gì xảy ra? Tại sao cần tombstone/version metadata?

### Bài 15 — TTL

Key source expires 10:00, export 09:55, import 10:10. Có nên tạo lại với TTL 5 phút? Thiết kế expiry-preserving transformation.

### Bài 16 — Chunk manifest

Export ghi 20 chunks, trong đó chunk 17 đã upload nhưng manifest chưa ghi do crash. Hãy thiết kế deterministic ID, integrity validation và orphan cleanup.

### Bài 17 — Integrity

Một attacker thay cả chunk file và SHA-256 trong manifest. Vì sao checksum không còn là bằng chứng authenticity? Đề xuất verified/signed manifest hoặc trust boundary khác.

### Bài 18 — MongoDB

Một Java exporter dùng `find().into(new ArrayList<>())` cho 30 triệu docs và OOM. Viết lại bằng cursor/batch size/streaming và durable last-key checkpoint. Nêu giới hạn của server cursor khi restart.

### Bài 19 — DynamoDB Query

Query Limit=100 với `FilterExpression` trả 0 items nhưng `LastEvaluatedKey` khác rỗng. Worker có được đánh dấu EOF không? Khi nào được lưu token đó làm checkpoint?

### Bài 20 — DynamoDB BatchWriteItem

Có 93 put/delete requests. Chia thành các batches theo API, xử lý `UnprocessedItems` và giải thích vì sao không dùng nó cho conditional version updates.

### Bài 21 — Cassandra

Một migration scan cả keyspace bằng `ALLOW FILTERING`, pageSize=1000 và không dùng partition keys. Nó có thể tác động thế nào đến cluster? Đề xuất partition/bucket scan và bounded async writes.

### Bài 22 — Redis SCAN

`SCAN` trả 0 keys nhưng cursor=12345. Worker dừng lại là đúng hay sai? Nếu keyspace có concurrent writes/deletes, làm sao bảo đảm một snapshot/coverage nhất quán?

### Bài 23 — Elasticsearch

Bulk API HTTP 200 nhưng trong body có 12 failed items. Worker ghi chunk COMPLETE. Hậu quả là gì? Sau khi retry, khi nào mới có thể gọi search projection query-ready?

### Bài 24 — Graph import

Nodes imported 100%, edges imported 85%, indexes still building. Có được cutover không? Thiết kế integrity checks cho references, edge count, paths và query parity.

### Bài 25 — ETA

Còn 200 GiB dữ liệu, durable write throughput 50 MiB/s. Tính ETA tuyến tính, rồi giải thích ít nhất năm lý do ETA có thể thay đổi.

### Bài 26 — Backpressure

Source fetch 12.000 records/s, sink ghi 4.000 records/s. Sau 45 giây, queue tăng bao nhiêu nếu không giới hạn? Thiết kế item/byte queue budget, pause/resume fetch và retry throttle.

### Bài 27 — Checkpoint CAS outcome unknown

Metadata CAS từ version 22→23 thành công nhưng ACK mất. Nếu worker retry bằng “increment confirmedRecords +500” mù, điều gì có thể sai? Viết quy trình readback reconcile.

### Bài 28 — Cutover

Source vẫn nhận writes, CDC backlog còn 30 giây và search lag 60 giây. SLO target yêu cầu freshness tối đa 10 giây. Hãy xây cutover criteria và các bước cần làm trước khi flip traffic.

### Bài 29 — Rollback

Sau cutover, target nhận 100 đơn mới nhưng source cũ không còn đồng bộ. Có được chuyển DNS về source ngay không? Đề xuất reverse sync/epoch fencing/reconciliation hoặc forward fix.

### Bài 30 — Thiết kế tổng hợp

Thiết kế migration:

```text
MongoDB source (live writes)
  -> snapshot export to encrypted chunks
  -> manifest and per-range checkpoints
  -> Java import workers
  -> DynamoDB or Elasticsearch target
  -> CDC catch-up
  -> verification and cutover
```

Cần xác định source boundary, chunk IDs, byte/count/time batch limits, idempotency, TTL/deletion, schema version, progress/ETA, retries/quarantine, target consistency, security, fault injection, rollback và decommission.

## 80. Checklist trước khi chạy export/import

### 80.1. Định nghĩa dữ liệu và hợp đồng

1. **Source/target identity** đã được xác định chính xác theo cluster/table/collection/incarnation chưa?
2. Scope tenant, partitions, time ranges và filtering có được phê duyệt không?
3. Có schema/mapping versions được pin cho cả run không?
4. Mục tiêu là offline snapshot hay online snapshot + CDC?
5. Source có tiếp tục nhận writes và deletes trong lúc chạy không?
6. Snapshot/CDC boundary có bảo đảm **không có khoảng trống**?
7. Có định nghĩa source revision/ordering cho từng entity không?
8. Có data types nhạy cảm: decimal, null/missing, UUID, timestamp, TTL, binary?
9. Có denormalized read models và relationship invariants cần verify?
10. RPO/RTO/downtime, freshness và cutover criteria đã rõ chưa?

### 80.2. Chia work và điểm tiếp tục

11. Reader dùng keyset/cursor/token/range scan theo semantics được tài liệu hóa chưa?
12. Có tránh deep offset scan không cần thiết không?
13. Nếu keyset, sort có unique immutable tie-breaker không?
14. Nếu opaque token, có gắn với query fingerprint/source generation không?
15. Cursor/PITR/source log retention có đủ cho thời lượng job?
16. Ranges có ranh giới không overlap/missing và có checkpoint riêng?
17. Các ranges lớn/hot có chính sách split/chia tải không?
18. Checkpoint store có durable CAS/ownerEpoch và access controls không?
19. Có explicit EOF/terminal state, không dùng null token hai nghĩa không?
20. Worker cũ sau lease expiry có bị fence ở checkpoint và target khi cần không?

### 80.3. Batching và failure handling

21. Batch có giới hạn items, bytes và max wait time không?
22. Có max in-flight batches/bytes và bounded backpressure không?
23. Có đo p95/p99, retry amplification, source/target capacity không?
24. Sink APIs có trả per-item outcome và client kiểm tra đầy đủ không?
25. Có xử lý HTTP 200 kèm `UnprocessedItems`/partial errors không?
26. Retry có budget/backoff/jitter và dùng stable item IDs không?
27. Unknown commit có reconciliation plan không?
28. Chỉ checkpoint sau durable sink effect hay durable quarantine hợp lệ?
29. Có bảo vệ stale overwrite bằng revision/tombstone hoặc ordered protocol?
30. Có thử crash sau commit trước checkpoint, và sau checkpoint CAS trước ACK?

## 81. Checklist trước cutover và sau migration

### 81.1. Verification

31. Export manifest đã seal, chunks đầy đủ/checksum hợp lệ chưa?
32. Import ledger đã VERIFIED toàn bộ required chunks/ranges chưa?
33. Có đối soát counts, IDs, canonical digests, revisions và deletions không?
34. Có kiểm tra unique constraints, references, tenant isolation và business invariants?
35. Source và target đang được so ở cùng snapshot/CDC boundary không?
36. Có kiểm tra target query parity, latency và capacity dưới workload đại diện?
37. Search/graph/vector indexes đã query-ready, không chỉ import ACK?
38. Có permanent errors/quarantined records chưa được phê duyệt không?
39. Có kiểm chứng TTL/expiry và source deletes không bị hồi sinh?
40. CDC source-to-target lag đã trong budget và có coverage evidence chưa?

### 81.2. Cutover và rollback

41. Ai là write authority trước/sau cutover, có fencing hoặc quiesce writes không?
42. Các old clients, caches, DNS/connection pools sẽ đổi route thế nào?
43. Có đo requests vẫn route tới source cũ sau cutover không?
44. Có plan cho writes đang in-flight và unknown outcomes không?
45. Có monitoring/alerts cho data mismatches và source log retention không?
46. Rollback còn an toàn sau khi target có target-only writes không?
47. Có cơ chế reverse sync/reconciliation nếu phải rollback?
48. Source/backup/keys vẫn được giữ theo rollback window và legal policy?
49. Có quy trình pause/stop/import repair và escalation rõ owner?
50. Khi kết thúc, có decommission source và xóa temporary exports theo retention?

### 81.3. Progress và vận hành

51. Progress API có phân biệt read/transformed/applied/checkpointed/verified không?
52. Exact total/estimate/unknown total được hiển thị đúng?
53. ETA dựa durable throughput và nêu uncertainty/window?
54. Có per-range/chunk progress để nhận biết vùng chậm?
55. Có alerts khi checkpoint đứng, source token hết hạn, log headroom thấp hoặc mismatches?
56. Metrics không chứa raw PII/IDs/cardinality quá cao?
57. Source production SLO có được bảo vệ bằng rate limits/quota và schedule?
58. Các audit events cho export, import, cutover, rollback được lưu an toàn?
59. Fault tests có sử dụng synthetic data và phạm vi được phê duyệt?
60. Tất cả kết luận “complete” có bằng chứng từ **durable, verified target**?

## 82. Tóm tắt: một quy trình có thể tiếp tục đáng tin

Để kết nối các khái niệm, hãy nhìn toàn bộ flow:

```text
1. Define scope, source identity, schema and acceptance criteria.
                         |
                         v
2. Establish snapshot and CDC consistency boundary.
                         |
                         v
3. Partition source by stable ranges / supported paging.
                         |
                         v
4. Read bounded page and transform under pinned version.
                         |
                         v
5. Write idempotently to target with per-item outcomes.
                         |
                         v
6. On success, CAS durable checkpoint per range/owner.
                         |
                         v
7. On crash, resume from last durable boundary and replay safely.
                         |
                         v
8. Verify chunks, IDs, revisions, deletes and business queries.
                         |
                         v
9. Catch up CDC and establish final source position.
                         |
                         v
10. Controlled cutover with fencing, monitoring and rollback plan.
                         |
                         v
11. Observe, reconcile and decommission according to policy.
```

### Sáu nguyên tắc cần nhớ

1. **Checkpoint phải đứng sau ranh giới bền.** Không đánh đồng fetched cursor, attempted writes và committed progress.
2. **Replay là bình thường; duplicate business effect mới là lỗi.** Dùng deterministic identity, revision guards, inbox/event ledger hoặc chunk manifests.
3. **Một batch không mặc định atomic.** Kiểm tra từng item, xử lý partial success và unknown outcome.
4. **Snapshot và CDC cần nối nhau không có gap.** Không bắt đầu CDC “từ bây giờ” sau khi full scan hoàn tất rồi hy vọng không có updates bị bỏ.
5. **Progress cần nhiều chiều.** Read, written, checkpointed, verified, index-ready và caught-up khác nhau; ETA phải công bố độ không chắc.
6. **Cutover dựa trên correctness và khả năng phục vụ**, không dựa vào con số “100% đã đọc”.

### Câu hỏi quyết định

> **Nếu tiến trình chết ngay sau khi target commit một phần hoặc toàn bộ batch nhưng trước khi checkpoint được lưu, từ chính dữ liệu bền nào chúng ta biết cần đọc lại chỗ nào, và điều gì ngăn replay ghi trùng hoặc ghi đè phiên bản mới hơn?**

Khi trả lời được bằng **source boundary, per-range checkpoint, owner epoch, idempotent target semantics, manifest và verification**, một pipeline xuất/nhập NoSQL mới có cơ sở để tiếp tục sau lỗi và được dùng trong migration production có kiểm soát.

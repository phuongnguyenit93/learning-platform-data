# Change Data Capture bằng log, stream hoặc cơ chế của từng hệ

## 1. CDC giải quyết bài toán gì trong kiến trúc NoSQL?

Một ứng dụng Java lưu thông tin đơn hàng trong MongoDB, đồng thời cần:

- Cập nhật Elasticsearch/OpenSearch để tìm kiếm.
- Xóa hoặc cập nhật Redis cache.
- Gửi dữ liệu tới kho phân tích.
- Phát sự kiện cho dịch vụ giao hàng.
- Tạo lịch sử thay đổi phục vụ đối soát.

Một cách làm dễ nghĩ đến là ghi database xong rồi gửi thông điệp:

```text
Order Service
    |
    +---- 1. MongoDB: UPDATE Order O100
    |
    +---- 2. Kafka: PUBLISH OrderUpdated
```

Nhưng nếu MongoDB commit ở bước 1 rồi process chết trước bước 2, dữ liệu đã thay đổi mà downstream không biết. Đổi thứ tự gửi message trước rồi commit database lại có rủi ro **message được phát cho thay đổi chưa bao giờ commit**.

**Change Data Capture (CDC)** là cách quan sát, ghi nhận và chuyển tiếp **thay đổi đã xảy ra ở nguồn dữ liệu** mà không yêu cầu mọi ứng dụng tự gửi một message độc lập cho mỗi thao tác ghi.

Một kiến trúc ví dụ:

```text
                  Java Order Service
                          |
                          | commit
                          v
                      MongoDB
                          |
                    Change Stream
                          |
                          v
                      CDC Relay
                          |
                          v
                    Kafka Topics
                    /     |     \
                   v      v      v
             Search Index Cache Analytics
```

Mục tiêu không chỉ “đọc được thay đổi”, mà là **có thể bắt kịp, tiếp tục sau sự cố, xử lý trùng lặp, giữ đúng thứ tự trong phạm vi cần thiết và biết khi nào phải tái đồng bộ**.

Bài học thuộc chương **Sự kiện và CDC**, giải thích CDC dựa trên log, stream và các cơ chế cụ thể ở từng NoSQL, cùng cách kết nối vào ứng dụng Java.

## 2. Định nghĩa và giới hạn của CDC

**CDC** là kỹ thuật phát hiện và trích xuất những thao tác làm thay đổi trạng thái nguồn dữ liệu, rồi đưa thông tin thay đổi đến một consumer hoặc hệ thống đích.

Một thay đổi có thể là:

- Insert/create một item hoặc document.
- Update một hoặc nhiều field.
- Delete một key/document.
- Thay đổi quan hệ trong graph.
- Thay đổi thông qua TTL, tùy sản phẩm có ghi nhận bằng loại event nào.
- Thay đổi metadata hoặc schema, nếu cơ chế capture có hỗ trợ.

Đầu ra thường chứa:

```json
{
  "source": "orders-db",
  "entityId": "O100",
  "operation": "UPDATE",
  "sourcePosition": "opaque-position",
  "capturedAt": "2026-11-14T10:10:00Z",
  "after": {
    "status": "PAID"
  }
}
```

Đây là **envelope minh họa do ứng dụng/connector chuẩn hóa**, không phải format mặc định của MongoDB, DynamoDB hay Cosmos DB.

### 2.1. CDC không phải thao tác query theo lịch

CDC thường nhấn mạnh việc theo dõi thay đổi trực tiếp từ log/stream hoặc cơ chế thông báo. Tuy vậy, một số kiến trúc dùng **polling trên cột `updatedAt` hoặc bảng outbox** để mô phỏng/change extraction. Polling có hạn chế riêng và không nên được quảng bá là tương đương log-based CDC.

### 2.2. CDC không tự tạo một business event có nghĩa đầy đủ

Database có thể biết:

```text
Order O100.status: PENDING -> PAID
```

Nhưng không tự biết đó là:

- `PaymentCaptured`;
- `PaymentAuthorizationSucceeded`;
- `OrderManuallyOverridden`;
- `FraudReviewResolved`.

**Mutation event** mô tả dữ liệu; **domain/integration event** mô tả sự thật nghiệp vụ đã được thiết kế. Muốn sự kiện giàu ngữ nghĩa, thường cần transactional outbox hoặc một event mapping có quy tắc rõ.

### 2.3. CDC không tự bảo đảm exactly-once end-to-end

Dù source event chỉ được tạo một lần, relay hoặc consumer có thể xử lý lại khi checkpoint/ACK bị mất. Các hệ đích còn có transaction và timeout riêng.

## 3. Bốn hướng lấy thay đổi

| Cách thu thập | Cơ chế | Lợi ích | Hạn chế |
|---|---|---|---|
| Log-based CDC | Đọc commit log, oplog, WAL hoặc replication stream | Gần source commit, ít phải scan toàn dữ liệu | Log retention, decoding, quyền truy cập và phiên bản |
| Native change stream/feed | API có cursor, token, iterator hoặc feed | Dễ tích hợp, thường là giao diện được hỗ trợ | Ordering, history window và payload tùy sản phẩm |
| Trigger/hook | Chạy logic khi DB mutation | Có thể bắt sự kiện tại nơi ghi | Tăng coupling và chi phí đường ghi; tính bền vững phụ thuộc trigger |
| Polling | Quét records theo version/`updatedAt`/outbox status | Dễ triển khai ở hệ không có stream | Có thể bỏ sót delete/changes, scan tốn kém, cần watermark |

Một NoSQL có thể dùng **native stream được xây trên log nội bộ**; hai cách không loại trừ nhau.

### 3.1. Log-based

```text
Client write -> Storage engine -> Commit/replication log
                                        |
                                        v
                                  CDC reader
```

Source log thường được ghi phục vụ recovery/replication và CDC tái sử dụng nó. Nhưng không phải mọi commit log đều có **public CDC API** ổn định; đọc log thô có thể cần công cụ hỗ trợ chính thức.

### 3.2. Native change feed

```text
Application -> NoSQL storage
                    |
                    v
             Managed Change Feed
                    |
               Cursor/Token
                    |
                    v
                 Consumer
```

Provider có thể quản lý một phần log decoding và publish metadata cho client.

### 3.3. Trigger

```text
OnDocumentUpdated:
    emit event / write side table
```

Phải hỏi trigger có cùng atomic transaction không, có thể retry không, khi external destination down thì transaction nguồn ra sao và trigger code có quyền gì.

### 3.4. Polling

```text
SELECT records
WHERE updatedAt > lastSeen
ORDER BY updatedAt, id
```

Cách này có thể **bỏ sót** những update cùng timestamp, delete vật lý và records được commit muộn nhưng mang `updatedAt` cũ; cần composite cursor, tombstone, monotonic source version và overlap window phù hợp.

## 4. CDC khác replication, event sourcing và outbox thế nào?

| Khái niệm | Mục đích chính | Nguồn dữ liệu/thứ tự |
|---|---|---|
| Replication | Duy trì các bản sao cùng dữ liệu | Replication protocol/log |
| CDC | Trích xuất và truyền thay đổi đã commit | Native log/stream/change feed |
| Transactional outbox | Ghi state và event intent trong một transaction cục bộ | Outbox trong source DB |
| Event sourcing | Dùng event history làm nguồn authoritative để dựng state | Append-only domain event log |
| Pub/Sub | Phân phối message tới subscribers | Broker hoặc notification channel |
| CQRS projection | Xây read model phù hợp truy vấn | Events/CDC/commands từ source |

**CDC là kỹ thuật truyền thay đổi**, không tự quyết định data ownership, mô hình sự kiện hoặc transaction semantics giữa services.

### 4.1. CDC và replication dùng cùng log nhưng có hợp đồng khác

Replication có thể tối ưu để giữ replicas tương đồng; CDC thường phải cung cấp feed cho downstream readers với cursor/checkpoint. Một replication protocol nội bộ không nhất thiết là API ổn định dành cho consumer.

### 4.2. CDC không tự biến source database thành event-sourced system

Nếu nguồn lưu document trạng thái hiện tại và chỉ dùng CDC để đồng bộ search, nó vẫn là **state-based database**. Một stream CDC có thể hết retention và không chứa toàn bộ lịch sử nghiệp vụ từ lúc bắt đầu.

### 4.3. CDC + outbox có thể bổ trợ nhau

```text
Local DB transaction:
    UPDATE Order.status = PAID
    INSERT Outbox(PaymentRecorded event)
    COMMIT

CDC connector reads Outbox -> Broker
```

Như vậy CDC vận chuyển **integration events đã được ứng dụng đặt tên và lưu atomically**, thay vì để downstream phải đoán nghiệp vụ từ mọi thay đổi field.

## 5. Pipeline CDC đầu cuối

Một hệ điển hình:

```text
 Source NoSQL
      |
      | append committed change
      v
 Native log / change feed
      |
      v
 Source connector / tailer
      |
      | decode, normalize, filter, route
      v
 Broker / durable stream
      |
      | partitions, offsets
      v
 Consumer / projector
      |
      | idempotent mutation
      v
 Search / Cache / Analytics / Service DB
      |
      v
 Sink checkpoint / ACK
```

Trong pipeline tồn tại **nhiều checkpoint**:

1. Position của source log/change feed.
2. Offset event đã publish bền vững tại broker.
3. Offset event consumer đã xử lý xong.
4. Version hoặc sequence cuối cùng đã áp dụng vào sink.

Không được coi các số này là một mốc duy nhất. Một connector đã publish event không chứng minh Elasticsearch đã index xong, và broker offset đã commit không chứng minh payment provider đã nhận side effect.

## 6. Anatomy của một CDC event

Một envelope minh họa:

```json
{
  "eventId": "orders:partition-3:sequence-8842",
  "source": {
    "system": "orders-mongo",
    "database": "commerce",
    "collection": "orders",
    "partition": "partition-3",
    "position": "opaque-resume-token"
  },
  "operation": "UPDATE",
  "key": {
    "orderId": "O100"
  },
  "before": {
    "status": "PENDING"
  },
  "after": {
    "status": "PAID"
  },
  "changedFields": ["status"],
  "sourceTimestamp": "2026-11-14T10:00:00Z",
  "capturedTimestamp": "2026-11-14T10:00:01Z",
  "schemaVersion": 3
}
```

Đây là **schema đề xuất**, không có một envelope bắt buộc chung cho các NoSQL.

### 6.1. `eventId`

Giúp consumer deduplicate, nhưng phải ổn định qua relay retry. Một `UUID.randomUUID()` mới ở mỗi lần publish khiến hai bản sao của cùng source change bị coi là hai events khác nhau.

### 6.2. `sourcePosition`

Có thể là offset, resume token, sequence number, shard iterator, LSN, commit timestamp hoặc token opaque. **Không suy có thể dùng dấu `>` để so hai tokens bất kỳ**.

### 6.3. `before`/`after`

Không phải feed nào cũng cung cấp cả hai. Full document image có thể tốn băng thông và có thể cần bật tính năng.

### 6.4. `changedFields`

Một update event có thể chỉ mô tả delta, không có full document. Sink cần biết áp dụng patch hay nạp lại state.

### 6.5. Thời gian

Phân biệt **event/source time**, **commit time**, **capture time** và **sink apply time**. Không dùng timestamp thời gian nhận làm thứ tự quyết định khi có nhiều writers mà chưa chứng minh bảo đảm.

### 6.6. Metadata nhạy cảm

Feed có thể chứa PII, payment details hoặc các field trước khi bị xóa. CDC pipeline phải tuân thủ IAM, encryption, retention, redaction và data-governance policy.

## 7. Bootstrap: vì sao chỉ theo dõi sự kiện mới là chưa đủ?

Khi lập một search index mới từ database có hàng triệu documents, CDC listener mở tại thời điểm hiện tại chỉ nhận mutations **sau lúc bắt đầu**.

```text
Source already has 1,000,000 documents
             |
             v
Start CDC at T0
             |
             v
Search sees only changes after T0
```

Để dựng read model đầy đủ cần:

1. **Initial snapshot/backfill:** đọc trạng thái hiện tại.
2. **Continuous change capture:** nhận mutations xảy ra khi snapshot đang chạy.
3. **Reconciliation:** nối snapshot với stream mà không bỏ sót hoặc ghi đè state mới bằng snapshot cũ.

### 7.1. Vì sao không snapshot xong rồi mới mở stream?

```text
T0: Snapshot starts
T1: Order O100 updated
T2: Snapshot completes
T3: CDC starts from "now"
```

Nếu O100 được đọc trước T1, search có thể mãi giữ giá trị cũ; thay đổi giữa snapshot và CDC start bị bỏ lỡ.

### 7.2. Vì sao không stream trước rồi cứ backfill upsert?

```text
T0: CDC started
T1: CDC applies O100 version 12
T2: Backfill upserts O100 version 9
```

Nếu sink không có version guard, snapshot cũ ghi đè event mới.

### 7.3. Phải thiết kế boundary rõ

Ví dụ một thuật toán tổng quát:

```text
1. Chọn start checkpoint P0 theo hợp đồng source.
2. Mở hoặc bảo đảm retention của stream từ P0.
3. Chạy consistent snapshot/scan.
4. Áp dụng snapshot với version guard.
5. Replay stream từ P0 theo thứ tự/source partition.
6. Lưu progress bền vững.
7. Chuyển sang steady-state streaming.
```

Đây là **mô hình khái niệm**, không phải thuật toán có thể copy nguyên sang mọi NoSQL. Cách lấy snapshot nhất quán với P0 phụ thuộc hệ; nếu source không cung cấp snapshot/log boundary, cần overlap window hoặc reconciliation bổ sung.

## 8. Consistent snapshot là một bảo đảm cụ thể

Một snapshot đọc hàng triệu records có thể kéo dài nhiều giờ. Trong thời gian đó, database vẫn nhận ghi.

Các mức snapshot có thể gặp:

- Một database transaction/snapshot timestamp trong phạm vi hỗ trợ.
- Một scan có checkpoint nhưng **không** đại diện một trạng thái tức thời thống nhất.
- Backup/snapshot vật lý với semantics riêng.
- Snapshot theo từng partition/shard có checkpoints riêng.
- Connector-provided incremental snapshot hoặc snapshot-plus-stream mode.

### 8.1. Scan không luôn nhất quán

Nếu quét A lúc 10:00 và B lúc 10:30, kết quả không tự là một snapshot ở 10:00 hoặc 10:30.

### 8.2. Watermark

Một **watermark** hoặc source position có thể đánh dấu phần mutations đã được bao phủ. Phải định nghĩa watermark theo partition/shard/log, không suy một số global có ý nghĩa nếu source không cung cấp.

### 8.3. Key changes

Nếu primary key/partition key thay đổi, CDC có thể mô tả như delete+insert, update đặc biệt hoặc thay đổi identity, tùy engine. Rebuild cần biết tránh orphan records.

### 8.4. Deleted-before-snapshot-finish

Một record bị xóa sau khi đã được snapshot nhưng trước khi stream bắt kịp; delete event phải tới sink và thắng snapshot cũ.

## 9. Source positions, offsets và resume tokens

Một connector cần nhớ vị trí đã đọc.

```text
Source stream: E1 E2 E3 E4 E5 E6
                     ^
               checkpoint E3
```

Khi restart, nó đọc tiếp từ vị trí phù hợp theo source API, có thể nhận lại một phần dữ liệu.

### 9.1. Position không đồng nghĩa timestamp

Một opaque resume token chứa thông tin internal không nhất thiết được so sánh theo chuỗi hoặc convert ra epoch.

### 9.2. Checkpoint có thứ tự an toàn

Nếu làm:

```text
1. Save checkpoint for E4
2. Apply E4 to sink
```

crash giữa hai bước có thể khiến E4 **bị bỏ qua vĩnh viễn**.

Nếu làm:

```text
1. Apply E4 to sink
2. Save checkpoint for E4
```

crash giữa hai bước khiến E4 được xử lý lại. Cần consumer idempotency.

### 9.3. Atomic sink mutation + checkpoint

Khi sink và checkpoint cùng database/transaction scope hỗ trợ, có thể commit cả hai một cách nguyên tử. Nếu không, thiết kế theo at-least-once + dedupe/version-aware handling.

### 9.4. Nhiều partitions

Mỗi shard/partition thường có checkpoint riêng:

```json
{
  "shard-A": "sequence-101",
  "shard-B": "sequence-901",
  "shard-C": "sequence-402"
}
```

Không dùng một offset toàn cục tự tạo nếu connector thực sự có nhiều independent streams.

## 10. Retention: nguồn log không giữ lịch sử mãi mãi

Một native change stream có history window. Consumer dừng quá lâu có thể không tiếp tục từ checkpoint cũ.

```text
Log retention window
|----------------------------|
                 ^          ^
             oldest       newest

Checkpoint consumer quá cũ < oldest => gap
```

Hậu quả:

- Resume token có thể invalid/expired.
- Shard iterator không còn hợp lệ.
- Source đã loại bỏ những mutations cần đọc.
- Connector không thể bảo đảm toàn bộ downstream state là đúng.

### 10.1. Không được lặng lẽ skip về “now”

Nếu CDC không resume được, chuyển thẳng sang vị trí mới rồi tiếp tục có thể khiến index mất mọi update/delete đã xảy ra trong khoảng hở.

### 10.2. Recovery đúng

- Đưa pipeline vào trạng thái `GAP_DETECTED`.
- Dừng tuyên bố projection fully synchronized.
- Xác định phạm vi dữ liệu ảnh hưởng.
- Rebuild/backfill với thuật toán snapshot+stream nhất quán.
- Dùng source version reconciliation.
- Chỉ trả trạng thái healthy sau xác minh.
- Ghi lại loss window và incident nếu có.

### 10.3. Capacity planning cho retention

Nếu CDC consumer có thể down 8 giờ và rebuild cần 4 giờ, source retention phải có margin đủ; tuy nhiên không thể chỉ cộng giờ khi throughput có thể khiến size-based oplog bị ghi đè nhanh hơn.

## 11. Ordering: trong phạm vi nào?

Không phải mọi CDC stream đều có **total order toàn database**.

Có thể gặp:

- Thứ tự trong một shard.
- Thứ tự theo partition key.
- Thứ tự theo một aggregate/item.
- Thứ tự commit trong một transaction log.
- Thứ tự không bảo đảm giữa nhiều regions.
- Message broker ordering chỉ trong một partition.

### 11.1. Ví dụ

```text
Order O100:
  version 10 -> CREATED
  version 11 -> PAID
  version 12 -> CANCELLED
```

Nếu consumer nhận v12 rồi v11, blind upsert sẽ làm search kết thúc `PAID` dù source đang `CANCELLED`.

### 11.2. Snapshot events và delta events

- Nếu mỗi event chứa **full snapshot** cùng monotonic version, có thể chỉ áp dụng event mới nhất.
- Nếu mỗi event là **delta** như `INCREMENT +1`, bỏ qua version 11 rồi áp version 12 có thể làm mất delta.
- Nếu event tạo một side effect, cần operationId/idempotency; chọn last timestamp không đủ.

### 11.3. Không so sequence giữa streams khác nhau

`shard-A:sequence=100` không nhất thiết trước hoặc sau `shard-B:sequence=90` theo thời gian thực. Muốn join xuyên partitions, cần correlation, transaction metadata hoặc workflow.

### 11.4. Broker partition key

Route events cùng `aggregateId` vào cùng partition khi cần ordered processing theo aggregate. Repartitioning, retries, snapshotting và concurrent producers vẫn cần quy định rõ.

## 12. Transaction boundaries và CDC

Một transaction source có thể thay nhiều documents/items. Feed có thể:

- Phát một event cho mỗi document;
- Mang transaction ID/commit metadata;
- Gom hoặc phân tách theo connector;
- Chỉ cho consumers thấy một phần events tại một thời điểm.

### 12.1. Không tự có transaction xuyên sink

Ví dụ source commit atomically hai records:

```text
Order.status = PAID
PaymentAttempt.status = APPROVED
```

CDC đưa thành hai events. Elasticsearch có thể áp event thứ nhất trước và event thứ hai sau. Trong khoảng đó, projection **không atomically giống source**.

### 12.2. Khi cần atomic projection

- Thiết kế aggregate snapshot event cho những fields phải cùng xuất hiện.
- Dùng sink transaction nếu hỗ trợ và biết đủ transaction group.
- Dùng event grouping/transaction metadata và apply sau khi nhận đủ.
- Chấp nhận eventual consistency có trạng thái trung gian trong read model.
- Với quyết định quan trọng, đọc authoritative source thay vì projection.

### 12.3. CDC event “commit” khác business commit

Một mutation `status=PAYMENT_PENDING` đã commit trong DB không có nghĩa thanh toán đã thành công. Downstream phải hiểu domain state machine.

## 13. Delivery semantics: at-most-once, at-least-once và exactly-once

| Semantics | Ý nghĩa | Đánh đổi |
|---|---|---|
| At-most-once | Có thể bỏ sót event, không cố giao lại | Ít duplicate, có loss |
| At-least-once | Sẽ giao lại cho tới khi xác nhận theo policy | Phải xử lý duplicates |
| Exactly-once trong scope | Một kết quả được commit một lần trong phạm vi cơ chế cụ thể | Scope và preconditions rất quan trọng |

CDC pipelines phổ biến dùng **at-least-once giữa các biên** và idempotent sink.

### 13.1. Tại sao duplicate hợp lệ?

```text
T0: Connector gửi E100 tới broker
T1: Broker ghi E100 thành công
T2: ACK tới connector bị mất
T3: Connector restart từ checkpoint cũ
T4: Connector gửi E100 lần nữa
```

Source không sai; network khiến một source event được publish hai lần.

### 13.2. Broker exactly-once chưa giải quyết external API

Một Kafka Streams transactional flow có thể có guarantees trong Kafka scope được cấu hình. Nhưng consumer gọi Payment Provider HTTP hoặc ghi một DB bên ngoài thì phải thiết kế idempotency/transaction boundary riêng.

### 13.3. Không nhầm retry với re-execute business command

CDC event `OrderPaid` replay không nên thực hiện lại `chargePayment`; đó là một sự kiện về kết quả đã xảy ra, không phải instruction để thu tiền lần hai.

## 14. Idempotent sink: khóa để CDC đáng tin cậy

Một sink nên nhận diện **cùng event** và **stale version**.

Ví dụ projection:

```json
{
  "orderId": "O100",
  "status": "CANCELLED",
  "sourceVersion": 12
}
```

Nhận event:

```json
{
  "orderId": "O100",
  "status": "PAID",
  "sourceVersion": 11
}
```

Rule:

```text
IF event.version > stored.sourceVersion:
    update state and version atomically
ELSE:
    ignore stale/duplicate
```

### 14.1. Atomic condition ở đâu?

Ở sink database. Một pattern sai:

```text
GET stored version=10
Another consumer writes version=12
Current consumer writes version=11
```

Nếu compare và update không atomic, version guard vẫn bị race.

### 14.2. Khi event không có source version

Có thể dùng persisted event IDs (inbox), source position theo một partition, hoặc rebuild từ authoritative source. Không dùng `System.currentTimeMillis()` ở consumer để tự tạo thứ tự “mới”.

### 14.3. Delete cũng cần marker

Nếu event DELETE v12 khiến sink xóa luôn lastVersion, UPSERT v11 tới sau có thể tạo record cũ. Giữ tombstone/version marker đủ lâu hoặc dùng source lookup để chặn resurrection.

### 14.4. Các operation kiểu tăng số

Một `+1` event cần applied-operation ID hoặc ordered event log; chỉ so max version mà bỏ qua gaps có thể mất increment.

## 15. Deletes, TTL và tombstones

Xóa dữ liệu thường là trường hợp khó nhất của CDC.

### 15.1. Hard delete

Nếu source phát DELETE với key, sink phải biết record nào cần xóa dù không có full `after` image:

```json
{
  "operation": "DELETE",
  "key": { "orderId": "O100" },
  "after": null
}
```

### 15.2. Soft delete

Ứng dụng có thể cập nhật:

```json
{
  "deleted": true,
  "deletedAt": "2026-11-14T10:00:00Z"
}
```

CDC nhìn thấy UPDATE, không phải DELETE. Sink phải hiểu `deleted=true` theo domain/schema policy.

### 15.3. TTL expiration

Cơ chế TTL có thể loại dữ liệu ở một thời điểm sau khi hết hạn; **feed có phát sự kiện expiration hay không** phụ thuộc sản phẩm, mode và source stream semantics.

Không mặc định một TTL expiry giống một explicit DELETE event trong mọi NoSQL.

### 15.4. Database tombstone khác broker tombstone

- Cassandra tombstone: metadata xóa trong storage reconciliation/compaction.
- Kafka compacted-topic tombstone: thông thường một message có key và null value để báo xóa trạng thái key trong log-compacted topic.
- Search sink tombstone: marker/version để chặn event cũ tái tạo document.

Cùng chữ “tombstone” nhưng **vòng đời và semantics khác nhau**.

### 15.5. Xóa vì privacy

Một CDC pipeline có thể sao chép PII sang search/warehouse/backup trước khi source xóa. Cần data inventory, delete propagation, retention, DLQ sanitization, snapshot/log retention và policy xóa ở downstream.

## 16. Schema evolution trong CDC

Documents NoSQL thường có schema linh hoạt:

```json
// Version 1
{
  "orderId": "O100",
  "status": "PAID"
}
```

```json
// Version 2
{
  "orderId": "O100",
  "payment": {
    "state": "PAID",
    "method": "CARD"
  }
}
```

Consumer cũ có thể không biết `payment.state`.

### 16.1. Các thay đổi có thể gây lỗi

- Rename field.
- Đổi `int` sang `string` hoặc ngược lại.
- Chuyển nested object thành array.
- Phân tách một collection thành nhiều collections.
- Thay primary key/partition key.
- Thay đổi encoding tiền tệ hoặc ngày giờ.
- Thêm enum value mà consumer chưa hiểu.

### 16.2. Event schema version

Đưa version vào envelope/payload và quản lý migration:

```json
{
  "eventType": "OrderStatusChanged",
  "schemaVersion": 2,
  "payload": {
    "orderId": "O100",
    "state": "PAID"
  }
}
```

### 16.3. Expand–migrate–contract

1. Producer phát dữ liệu tương thích cả schema cũ và mới nếu có thể.
2. Consumer cập nhật để đọc cả hai.
3. Backfill/rebuild projections.
4. Producer chuyển sang schema mới.
5. Chỉ bỏ schema cũ sau khi retention/replay window và các consumers được nâng cấp.

### 16.4. CDC không bắt buộc cung cấp schema registry

Một số connectors hỗ trợ Avro/Protobuf/JSON Schema và schema registry, một số chỉ trả raw JSON/BSON. Cần chọn rõ contract.

## 17. MongoDB Change Streams: cơ chế native

MongoDB cung cấp **Change Streams** cho deployment được hỗ trợ (thường replica set/sharded cluster), tận dụng oplog và các cơ chế nội bộ để xuất sự kiện thay đổi.

Một pipeline:

```text
MongoDB writes
     |
     v
Replica set oplog / change stream infrastructure
     |
     v
collection.watch() / database.watch() / client.watch()
     |
     v
Java Consumer
```

Các event thường có metadata như:

- `operationType`: insert/update/replace/delete và các loại khác tùy scope/version.
- `documentKey`: khóa định danh.
- `namespace`: database/collection.
- `fullDocument`: nếu có và mode yêu cầu.
- `updateDescription`: fields thay đổi ở update.
- `resumeToken`: để tiếp tục từ vị trí đã đọc.
- `clusterTime`: timestamp nguồn có semantics riêng.

### 17.1. `fullDocument` không luôn là after image tại chính xác thời điểm update

Với `FullDocument.UPDATE_LOOKUP`, driver/server có thể tra lại document sau khi update event, và nếu document đã thay đổi lần nữa trước lookup, nội dung fullDocument có thể phản ánh **trạng thái mới hơn** so với delta event.

Nếu cần before/after images chính xác theo semantics server cung cấp, tìm hiểu change stream pre/post image features và cấu hình/version, thay vì mặc nhiên coi `updateLookup` là snapshot transaction của event.

### 17.2. Pre/post images

Tùy version và cấu hình collection, MongoDB có khả năng change stream pre-images/post-images và retention riêng. Không phải mọi deployment mặc định bật hoặc giữ images mãi.

### 17.3. Resume token

Token là **opaque BSON document**, không được tự decode thành chuỗi số hoặc sắp xếp bằng lexicographic order.

### 17.4. Retention

Oplog history window ảnh hưởng khả năng resume. Consumer downtime dài hoặc lưu token không hợp lệ có thể buộc resnapshot.

## 18. Java MongoDB driver: watch change stream

Ví dụ dùng MongoDB Java Driver synchronous API; giả định đã cấu hình replica set/sharded cluster, quyền truy cập và MongoDB URI.

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

public final class MongoChangeStreamExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                    client.getDatabase("commerce")
                            .getCollection("orders");

            ChangeStreamIterable<Document> feed =
                    orders.watch()
                            .fullDocument(
                                    FullDocument.UPDATE_LOOKUP
                            );

            try (MongoCursor<ChangeStreamDocument<Document>>
                         cursor = feed.iterator()) {

                while (cursor.hasNext()) {
                    ChangeStreamDocument<Document> event =
                            cursor.next();

                    System.out.println(
                            "type=" + event.getOperationType()
                    );
                    System.out.println(
                            "key=" + event.getDocumentKey()
                    );
                    System.out.println(
                            "token=" + event.getResumeToken()
                    );

                    // Production:
                    // 1. Process idempotently at sink.
                    // 2. Persist token only after sink success.
                    // 3. Catch resume errors and recover.
                }
            }
        }
    }
}
```

### 18.1. Vì sao ví dụ chưa đủ cho production?

- Chưa lấy checkpoint cũ và dùng `resumeAfter(...)`.
- Chưa có handling cho stream idle, network disconnect hoặc shutdown.
- Chưa phân tách `UPDATE` với `DELETE`, `INVALIDATE`, collection drop/rename.
- Chưa xử lý poison payload hoặc schema migration.
- Chưa có sink atomic version/idempotency.
- `System.out.println` không phải message broker.
- Chưa giới hạn retry/backoff.
- Chưa kiểm tra đủ ordering khi scale nhiều consumers.

### 18.2. Cursor có thể block

Sync `hasNext()`/`next()` là API blocking. Không gọi trên event-loop thread của WebFlux. Có thể dùng MongoDB reactive streams driver với flow/backpressure phù hợp.

### 18.3. Scope watch

Collection-level, database-level và deployment-level watches khác phạm vi, permissions và sự kiện hệ thống. Chọn scope hẹp cần thiết.

### 18.4. Đừng biến Change Stream thành một trigger side-effect trong DB transaction

Listener hoạt động **sau thay đổi nguồn**, và consumer có thể bị delay/retry; không thể dùng một event chưa tới để chứng minh payment/inventory đã atomic commit cùng MongoDB.

## 19. MongoDB resume, invalidation và checkpoint

Một flow phục hồi:

```text
Startup:
  token = checkpointStore.read("orders-consumer")
  feed = orders.watch().resumeAfter(token)

Loop:
  event = next(feed)
  applyToSinkIdempotently(event)
  checkpointStore.save(event.resumeToken)
```

Đây là pseudocode quy trình, cần xử lý token null và các tùy chọn change stream phù hợp.

### 19.1. Token được lưu khi nào?

Sau khi sink xử lý thành công và metadata đủ bền, không phải ngay lúc vừa nhận event.

### 19.2. Lưu token riêng có thể tạo replay

Nếu sink commit nhưng checkpoint save fail, event tới lần nữa khi restart. Đây là lý do sink cần idempotency.

### 19.3. Không giả định mọi resume token hợp lệ mãi

Nếu oplog entries cần thiết đã bị prune, `resumeAfter` có thể không khôi phục được. Phải phát hiện lỗi và làm snapshot/reconciliation.

### 19.4. Invalidation event

Các thao tác như drop/rename có thể gây `invalidate` cho một stream theo scope; resuming sau invalidate có semantics/API riêng và không thể tùy tiện dùng lại mọi token như event thường.

### 19.5. Scale-out

Nhiều consumers cùng `watch()` một collection có thể nhận cùng events nếu không có sharding/work assignment. Cần phân phối công việc và tránh hai readers cùng ghi sink trùng, hoặc thiết kế sink idempotent.

## 20. MongoDB: initial snapshot kết hợp Change Streams

Một workflow dựng index:

1. Xác định connector-supported snapshot và start position.
2. Bảo đảm source oplog retention đủ trong lúc snapshot.
3. Scan documents từ MongoDB qua cursor với batch size phù hợp.
4. Viết vào Elasticsearch theo source version/consistent snapshot guard.
5. Tail changes xảy ra trong lúc scan.
6. Reconcile deletes/updates và lưu resume token.
7. Tiếp tục stream ổn định.

### 20.1. Không coi query thường là consistent snapshot

Một `find()` kéo dài qua nhiều phút có thể thấy dữ liệu thay đổi trong khi quét. Nếu không có snapshot isolation/connector coordination, cần overlap/reconciliation.

### 20.2. Không tăng oplog retention bằng cách đoán

Oplog có giới hạn theo size/window và tốc độ writes có thể làm history biến mất nhanh. Theo dõi actual oplog window và source connector lag.

### 20.3. Consumer có thể dùng change stream để cập nhật cache

Nhưng cache invalidation đến **sau source commit**, nên không nên dựa vào đó cho những reads yêu cầu hoàn toàn đồng bộ với source.

## 21. DynamoDB Streams: theo dõi thay đổi item

DynamoDB cung cấp **DynamoDB Streams** cho bảng được bật tính năng, ghi lại thông tin thay đổi item theo cấu hình stream view.

Sơ đồ:

```text
DynamoDB Table
      |
      | committed item changes
      v
 DynamoDB Streams
      |
    shards
      |
      +--> Lambda event source mapping
      |
      +--> Custom consumer using Streams API
```

Các stream view types phổ biến:

| View type | Nội dung |
|---|---|
| `KEYS_ONLY` | Khóa của item thay đổi |
| `NEW_IMAGE` | Hình ảnh item sau mutation theo semantics |
| `OLD_IMAGE` | Hình ảnh item trước mutation |
| `NEW_AND_OLD_IMAGES` | Cả before và after images |

Không phải ứng dụng nào cũng cần cả hai images; payload lớn hơn tăng băng thông và chi phí xử lý.

### 21.1. Retention

DynamoDB Streams có **retention khoảng 24 giờ** cho records theo hợp đồng dịch vụ. Consumer down quá window có thể mất khả năng replay từ vị trí cũ.

### 21.2. Ordering

Records có thứ tự theo semantics của shard/item, nhưng **không được suy một total order cho mọi items trên mọi shards**. Mỗi consumer phải xử lý checkpoint/shard lineage.

### 21.3. TTL deletes

DynamoDB TTL có thể xóa items bất đồng bộ và ghi sự kiện vào Streams. Metadata nhận diện service deletion có phạm vi/hành vi theo region và replication; không nên suy mọi vùng đều nhận một TTL event giống hệt nhau.

### 21.4. Global Tables

Nếu dùng multi-region replication, Streams và change consumers ở từng region có thể quan sát mutations/replication events theo semantics của mode. Phải thiết kế deduplication/ordering và tránh phát hai business effects từ cùng một ý định.

## 22. Java DynamoDB Streams: xử lý record

Một consumer có thể nhận record từ AWS SDK for Java v2 `DynamoDbStreamsClient`, hoặc nhận batch qua Lambda event source mapping.

Pseudocode handler:

```java
public final class DynamoStreamProjector {

    public void handle(StreamRecordEnvelope event) {
        String eventId = event.eventId();
        String eventName = event.eventName();
        String orderId = event.key("orderId");

        if ("REMOVE".equals(eventName)) {
            projection.deleteIfNewer(
                    orderId,
                    event.sourceVersion(),
                    eventId
            );
            return;
        }

        if ("INSERT".equals(eventName)
                || "MODIFY".equals(eventName)) {

            projection.upsertIfNewer(
                    orderId,
                    event.newImage(),
                    event.sourceVersion(),
                    eventId
            );
        }
    }

    private final ProjectionStore projection;

    public DynamoStreamProjector(
            ProjectionStore projection
    ) {
        this.projection = projection;
    }

    public interface ProjectionStore {
        void upsertIfNewer(
                String id,
                Object image,
                long version,
                String eventId
        );

        void deleteIfNewer(
                String id,
                long version,
                String eventId
        );
    }

    // Adapter phải map AWS record thành envelope
    // với identity/version do source contract cung cấp.
    public interface StreamRecordEnvelope {
        String eventId();
        String eventName();
        String key(String name);
        Object newImage();
        long sourceVersion();
    }
}
```

**Giới hạn quan trọng:** Đây là **interface pseudocode** cho adapter, không phải class AWS SDK. DynamoDB stream record không tự cung cấp một `sourceVersion()` business tăng đều cho mọi item; schema của bảng hoặc adapter phải cấp thông tin phù hợp. Nếu stream chỉ có sequence number theo shard, không được biến nó thành global entity version mà không kiểm tra scope.

### 22.1. Nếu dùng Lambda

Lambda event source mapping có thể retry batch khi function lỗi. Idempotent handler và partial batch failure handling tùy cấu hình cần được thiết kế, nếu không một event lỗi có thể làm replay các events đã thành công.

### 22.2. Nếu dùng custom poller

Phải xử lý shard iterators, checkpoints, iterator expiry, child shards, throttling và retention. Không chỉ chạy một vòng `GetRecords` mãi mãi mà bỏ qua thay đổi shard topology.

### 22.3. DynamoDB Streams khác Kinesis Data Streams

DynamoDB có thể tích hợp xuất changes sang Kinesis Data Streams trong những cấu hình phù hợp, nhưng **DynamoDB Streams và Kinesis là hai dịch vụ/retention/consumer semantics khác nhau**. Không đổi tên một stream ARN thành Kinesis ARN.

## 23. DynamoDB CDC cho bảng inventory

Một item:

```json
{
  "PK": "PRODUCT#P100",
  "SK": "INVENTORY",
  "available": 5,
  "reserved": 2,
  "version": 42
}
```

Mutation trên source dùng atomic conditional write:

```text
IF available >= 1 AND version=42:
    available -= 1
    reserved += 1
    version = 43
```

Stream event sau commit có thể cập nhật read model để hiển thị inventory ước lượng.

### 23.1. Stream không quyết định có được reserve không

Client không được chỉ đọc inventory projection rồi tự hứa reserve. Điều kiện phải được kiểm tra tại DynamoDB authoritative item/transaction.

### 23.2. Event trùng

`version=43` được giao lại hai lần: projector phải upsert idempotent.

### 23.3. Record đến muộn

Projection đã có v44 rồi nhận v43: không được rollback v44.

### 23.4. TTL

Nếu một reservation item hết TTL, consumer cần phân biệt service expiration với explicit user cancellation nếu nghiệp vụ yêu cầu. Với TTL không có deadline chính xác, đừng dùng thời điểm stream record xuất hiện làm sự kiện expiry đúng chính xác từng mili-giây.

## 24. Cassandra: CDC liên quan commit log, không phải tự có Kafka topic

Apache Cassandra có cơ chế **CDC gắn với commitlog mutations** trên những phiên bản/cấu hình có hỗ trợ. Với table bật `cdc = true`, hệ có thể cung cấp dữ liệu CDC ở dạng commitlog segments/metadata để tooling xử lý.

Một sơ đồ khái niệm:

```text
Client -> Cassandra coordinator -> Replicas
                                      |
                                      v
                              Commitlog mutations
                                      |
                                      v
                              CDC raw log segments
                                      |
                                      v
                                CDC consumer
                                      |
                                      v
                                  Broker
```

### 24.1. Table-level CDC setting

Trong các phiên bản hỗ trợ cơ chế liên quan, CQL có thể cấu hình:

```sql
ALTER TABLE orders_by_id
WITH cdc = true;
```

Đây không phải lệnh kích hoạt một managed Kafka connector tự động. Cần hạ tầng đọc, decode, checkpoint và publish dữ liệu.

### 24.2. Commitlog không phải domain event log

Commitlog chứa mutations phục vụ durability/recovery. Consumer phải diễn giải partition keys, timestamps, tombstones và schema/serialization theo format/version.

### 24.3. Có thể có trùng lặp

Replication giữa nodes và retry khiến một logical business operation có thể được quan sát qua các mutations ở nhiều replicas nếu connector đọc không đúng mô hình dedupe. Không mặc định “mỗi row update tạo đúng một event duy nhất toàn cluster”.

### 24.4. CDC storage/backpressure

Cassandra CDC raw log retention/disk capacity cần được vận hành cẩn thận. Khi consumer không thu dọn CDC segments kịp và dung lượng giới hạn, source có thể bị ảnh hưởng đến write availability theo cấu hình. Đây là rủi ro khác với một managed stream tự giữ vài giờ rồi silently trim.

### 24.5. Ghi chú phiên bản

Các Cassandra distributions và hệ tương thích như ScyllaDB có CDC features/format/API khác nhau. Không dùng một hướng dẫn đọc binary commitlog của Cassandra 3.x làm quy trình chung cho mọi hệ.

## 25. Cassandra: deletes, TTL và LWW khi xuất event

Cassandra có timestamp reconciliation, tombstones và TTL semantics. CDC consumer phải phân biệt:

- Insert/update cell;
- Row/partition/range delete;
- TTL/expiration;
- Mutation timestamp do client/coordinator cấp;
- Replay/hints/repair;
- Thứ tự theo partition/replica.

### 25.1. Event từ mutation không luôn là full row sau commit

Một CQL `UPDATE` có thể chỉ sửa một vài cells. Muốn dựng document đầy đủ ở sink có thể cần materialization/lookup.

### 25.2. LWW timestamps không tự là transaction order toàn cục

Hai updates với client-supplied timestamps có thể được hòa giải khác arrival order. Nếu projector lấy “event tới sau thì thắng”, sink có thể khác source.

### 25.3. Tombstone và zombie data

Một replica offline lâu có thể bỏ lỡ tombstone. Sau grace/compaction và repair không đúng lịch, old data có thể xuất hiện trở lại. CDC đích không được coi một mutation DELETE đã broadcast là bằng chứng source không thể resurrect trong mọi điều kiện.

### 25.4. TTL có thể không hiện thành một event expiry riêng như mong đợi

Phải kiểm tra CDC semantics của bảng/engine/version và quản lý expiry ở projection theo `expiresAt`/TTL contract.

## 26. Azure Cosmos DB Change Feed

Azure Cosmos DB cung cấp **Change Feed** cho những APIs/tài khoản và modes phù hợp, giúp theo dõi thay đổi items trong container.

```text
Cosmos DB Container
        |
        v
     Change Feed
        |
        +--> Change Feed Processor
        |
        +--> Custom iterator/SDK
        |
        v
     Java Consumer
```

### 26.1. Latest-version mode

Một mode phổ biến hiển thị những item changes theo latest-version semantics, thích hợp cập nhật projection từ trạng thái cuối cùng. Không suy nó luôn cung cấp mọi intermediate update hoặc mọi DELETE như một event độc lập.

### 26.2. All versions and deletes / full-fidelity mode

Một số tính năng/mode hỗ trợ quan sát nhiều phiên bản và deletes, với các điều kiện về account, retention, API và configuration. Đây không phải mặc định cho mọi Cosmos DB deployment.

### 26.3. Ordering

Change Feed thường có ordering guarantees trong scope logical partition key; không suy global total order giữa các partition keys.

### 26.4. Change Feed Processor

SDK processor có thể quản lý lease/checkpoint và phân phối partitions cho nhiều workers. Nhưng message duplicates, retry và downstream idempotency vẫn là trách nhiệm thiết kế.

### 26.5. Transactional batch

Một transactional batch trong cùng logical partition key có thể ghi state và outbox items atomically theo phạm vi API. Change Feed sau đó vận chuyển outbox events tới broker/downstream.

### 26.6. Java

Java SDK có các APIs/processor cho Change Feed theo phiên bản. Trước khi triển khai, kiểm tra chính xác package, SDK version, feed mode, lease container và checkpoint method; không copy mã processor cũ sang SDK mới mà bỏ qua breaking changes.

## 27. Cosmos DB Change Feed: snapshot và processor leases

Ví dụ một service scale từ một worker lên ba workers:

```text
Feed ranges:
  range-0 -> Worker A
  range-1 -> Worker B
  range-2 -> Worker C
```

Processor quản lý lease ownership/checkpoint theo cơ chế của SDK.

### 27.1. Lease không đồng nghĩa sink write atomic

Worker A có thể xử lý event rồi crash trước checkpoint; worker B tiếp quản và xử lý lại. Sink phải idempotent.

### 27.2. Scale-out và partitions

Không cho hai workers tự ý coi mình là owner cùng một range mà không tuân thủ lease protocol. Với lỗi lease expiry, stale worker có thể vẫn đang thực hiện external write; fencing/version guard ở sink hữu ích.

### 27.3. Retention và start point

Trong những modes, có thể đọc từ đầu lịch sử change feed đang được service giữ; nhưng không suy feed chứa mọi phiên bản từ vô hạn thời gian. Đọc đúng contract mode/account.

### 27.4. Delete handling

Nếu dùng latest-version feed không ghi đầy đủ deletes, có thể cần **soft-delete marker** hoặc mode hỗ trợ delete capture để đảm bảo downstream xóa.

## 28. Couchbase: Database Change Protocol (DCP)

Couchbase có **Database Change Protocol (DCP)** làm nền tảng cho một số chức năng streaming/indexing/replication và connectors.

```text
Couchbase Data Service
       |
       v
DCP mutation stream
       |
       v
Connector / consumer
       |
       v
Kafka / search / analytics
```

### 28.1. vBucket và sequence

DCP theo dõi mutations theo vBuckets, có sequence numbers/rollback/failover semantics. Không được coi một sequence number vBucket A có thể so trực tiếp với vBucket B thành total order.

### 28.2. Failover/rollback

Trong một số điều kiện failover, consumer cần xử lý rollback request/checkpoints để tránh tin vào lịch sử không còn hợp lệ. Dùng connector được hỗ trợ sẽ giảm rủi ro tự triển khai protocol phức tạp.

### 28.3. Deletes và expiry

DCP có mutations/deletions và các event types tùy phiên bản/phương thức. Phải xác minh connector có chuyển expiration thành delete event phù hợp downstream hay không.

### 28.4. Data vs index update

Một document mới được commit trong KV service nhưng index/query service có thể lag; CDC/DCP pipeline không tự biến mọi index read thành linearizable.

## 29. Neo4j: graph changes và CDC

Đối với graph database, CDC có thể bao gồm:

- Node creation/update/deletion.
- Relationship creation/update/deletion.
- Labels, properties và relationship endpoints.
- Transaction metadata.

Neo4j có CDC capabilities trong những phiên bản/edition phù hợp, với query/procedure/API contract riêng. Không giả định mọi Neo4j server đều có một `watch()` method giống MongoDB.

### 29.1. Graph mutation khác row mutation

```text
CREATE (u:User {id:"U42"})-[:FOLLOWS]->(v:User {id:"U99"})
```

Consumer muốn dựng recommendation graph ở đích cần xử lý cả nodes và relationships theo ordering/identity.

### 29.2. Delete relationship

Nếu chỉ theo dõi node snapshots, việc xóa edge có thể bị bỏ sót. Phải subscribe đúng loại change hoặc dùng graph-specific reconciliation.

### 29.3. Stable identifiers

Graph internal IDs có thể có lifecycle khác business ID. Integration events nên dùng stable external/business key theo domain.

### 29.4. Transaction scope

Một graph transaction có thể thay nhiều nodes/relationships. CDC exporter có thể tách events, nên sink cần chọn semantics khi thấy một phần thay đổi.

## 30. Redis: Streams không tự là CDC cho mọi key

Redis có nhiều cơ chế **dễ bị nhầm lẫn**:

1. **Redis Streams (`XADD`, `XREAD`, consumer groups):** một cấu trúc dữ liệu stream mà ứng dụng chủ động ghi events.
2. **Keyspace notifications:** Pub/Sub thông báo về một số thao tác trên keys.
3. **AOF/replication stream:** cơ chế persistence/replication nội bộ.
4. **Modules/connectors:** có thể cung cấp integration theo sản phẩm.

### 30.1. Redis Streams

Ví dụ:

```text
XADD order-events * orderId O100 status PAID
```

Ứng dụng **phải phát event bằng XADD** hoặc qua một cơ chế liên quan. Redis không tự biến mọi `SET order:*` thành record trong stream `order-events`.

### 30.2. Keyspace notifications

Có thể bật notifications cho events theo policy. Nhưng dựa trên Pub/Sub thường **không bảo đảm durable replay** cho subscriber offline. Không dùng như CDC đáng tin cho ledger hoặc xóa dữ liệu quan trọng.

### 30.3. AOF

AOF phục vụ Redis persistence; không mặc định là API change feed ổn định để xây external CDC decoder tùy ý.

### 30.4. Redis Streams consumer groups

Có pending entries, acknowledgement, reclaim/claim semantics; nhưng một `XACK` sau sink commit vẫn có duplicate window. `XACK` trước sink commit có nguy cơ mất business effect.

### 30.5. Redis là cache hay source?

Nếu Redis chỉ làm cache của MongoDB, thông thường CDC nên xuất từ **MongoDB authoritative DB**, không phải quan sát mọi Redis key mutations rồi coi chúng là business source events.

## 31. Elasticsearch/OpenSearch: index changes khác source CDC

Elasticsearch/OpenSearch thường là đích search projection nhận CDC từ MongoDB/DynamoDB/Cassandra hoặc ứng dụng.

Không nên mặc định một search index cung cấp một native public CDC feed với semantics giống oplog/Change Streams của source DB. Có thể có hooks/integration/snapshot hoặc cơ chế đọc cập nhật theo từng hệ, nhưng phải kiểm tra contract.

### 31.1. Bulk indexing không phải transaction toàn batch

Nếu một batch 100 documents index và 3 records lỗi, response có thể chỉ báo partial failures. Connector phải retry từng item đúng cách.

### 31.2. External versioning

Sử dụng source version để tránh event cũ ghi đè record mới, với semantics external version/version conflict API phù hợp. Với delete, phải xem retention/version-marker behavior để old event không recreate.

### 31.3. Refresh lag

Sink write success không có nghĩa search query lập tức nhìn thấy record. Elasticsearch refresh semantics và projection lag là những mốc riêng.

### 31.4. Rebuild index

Có thể build index mới song song, tail CDC, catch up đến watermark, kiểm tra tính đúng rồi chuyển alias theo procedure; không xóa index cũ trước khi có recovery path.

## 32. Kafka Connect và source connectors

**Kafka Connect** là framework chạy connectors giữa hệ thống ngoài và Kafka.

```text
NoSQL DB
   |
   v
Source Connector
   |
   | Connect tasks, source offsets
   v
Kafka topic(s)
   |
   v
Sink Connector / Consumer
   |
   v
Search / Warehouse / Cache
```

### 32.1. Source connector

Đọc CDC/change feed và publish records, quản lý checkpoints theo khả năng source và framework.

### 32.2. Sink connector

Nhận Kafka records và ghi vào database/search/analytics. Delivery và atomicity tùy connector.

### 32.3. Task parallelism

Tăng số tasks không tự tăng throughput nếu source có một partition hoặc một stream không chia được. Phải xét source partition topology, broker partitions và sink capacity.

### 32.4. Kafka Connect offsets

Source offsets và Kafka broker offsets thuộc phạm vi khác nhau. Connectors có thể flush offset theo chu kỳ, tạo duplicate window khi crash.

### 32.5. Connector version

Một connector hỗ trợ MongoDB version X không mặc nhiên tương thích MongoDB version Y hoặc tất cả document/pre-image features. Kiểm tra supported versions và licensing.

### 32.6. Không có một YAML “chuẩn” cho mọi connector

Mọi connector có config riêng: source URI, include collections, snapshot mode, converters, schema registry, dead-letter policy và offset storage.

## 33. Debezium và kiến trúc outbox

Debezium là hệ sinh thái CDC connectors, phổ biến trong kiến trúc event-driven với Kafka Connect và cả những integration modes khác.

Một số source connectors/transformations có phạm vi hỗ trợ theo database/version. **Đừng giả định có connector chính thức cho mọi NoSQL hoặc mọi bản phân phối**.

### 33.1. Outbox pattern

```text
Business DB Transaction
    |
    +-- UPDATE Order O100
    +-- INSERT Outbox Event E100
             |
             v
        CDC Connector
             |
             v
          Broker
```

### 33.2. Vì sao outbox tốt hơn suy domain event từ raw row update?

Outbox event chứa:

```json
{
  "eventId": "E100",
  "aggregateType": "Order",
  "aggregateId": "O100",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "payload": {
    "orderId": "O100",
    "paymentIntentId": "PI100"
  }
}
```

Consumer không cần suy “tại sao field status vừa đổi” bằng cách so BSON.

### 33.3. Outbox có yêu cầu nguyên tử thật

Nếu Order nằm ở partition A còn outbox event ở partition B mà database **không** hỗ trợ transaction giữa hai partitions, code gọi hai writes không thành transactional outbox.

### 33.4. Một outbox event có thể publish hai lần

Source connector có thể restart sau broker publish nhưng trước checkpoint. Dùng stable `eventId`, inbox/consumer dedupe.

### 33.5. Cleanup outbox

Không xóa outbox record quá sớm trước khi connector chắc chắn đã đọc và checkpoint. Cleanup retention phải tính tới CDC lag, broker availability và recovery.

## 34. Từ CDC thô sang integration event

Một raw mutation:

```json
{
  "operation": "UPDATE",
  "collection": "orders",
  "documentKey": {
    "_id": "O100"
  },
  "changedFields": {
    "status": "PAID"
  }
}
```

Nếu Payment Service nhận raw mutation, nó phải tự suy trạng thái/domain rules. Điều này gây coupling lớn giữa database schema và consumer.

### 34.1. Anti-corruption layer

Đặt một layer chuyển đổi:

```text
Raw CDC -> Mapper/Validator -> Domain Integration Event
```

Nó cần:

- Entity identity.
- Schema version.
- Expected state transition.
- Source transaction/aggregate version.
- Correlation/operation ID.
- Payload privacy filter.
- Business event naming.

### 34.2. Khi không nên tự suy

Nếu cùng `status=PAID` có thể đến từ capture thực tế, manual repair hoặc data migration, raw CDC không đủ để phát `PaymentCaptured` một cách đáng tin. Outbox từ nơi thực thi nghiệp vụ phù hợp hơn.

### 34.3. Khi raw CDC đủ dùng

Search indexing, cache invalidation, analytics capture theo schema source thường có thể xử lý raw `INSERT/UPDATE/DELETE` mà không cần domain event phức tạp.

## 35. Java consumer: idempotent projection handler

Một interface tổng quát:

```java
import java.util.Map;

public record ChangeEvent(
        String eventId,
        String aggregateId,
        long aggregateVersion,
        Operation operation,
        Map<String, Object> image
) {
    public enum Operation {
        UPSERT, DELETE
    }
}

public interface VersionedProjectionStore {
    // Contract: compare version and mutation must be atomic.
    boolean applyIfNewer(ChangeEvent event);
}
```

Handler:

```java
public final class OrderProjectionConsumer {

    private final VersionedProjectionStore store;

    public OrderProjectionConsumer(
            VersionedProjectionStore store
    ) {
        this.store = store;
    }

    public void onEvent(ChangeEvent event) {
        if (event.eventId() == null
                || event.aggregateId() == null
                || event.aggregateVersion() < 0) {
            throw new IllegalArgumentException(
                    "Invalid CDC event"
            );
        }

        store.applyIfNewer(event);

        // Broker ACK/checkpoint sau khi sink thành công.
        // Nếu ACK mất, retry được xử lý idempotently.
    }
}
```

### 35.1. Version do ai cấp?

Giá trị `aggregateVersion` trong ví dụ là **trường do nguồn authoritative cấp**, không phải thuộc tính có sẵn của mọi native CDC feed. Nếu source không có business version, adapter phải xác định cơ chế dedup/order khác phù hợp.

### 35.2. `applyIfNewer` phải thật sự nguyên tử

Không được triển khai bằng `get()` và `save()` tách rời khi nhiều consumer có thể tranh chấp cùng aggregate.

### 35.3. Delete handling

Một DELETE được áp dụng với version 12 cần để lại marker phù hợp để event UPSERT version 11 tới muộn không hồi sinh record.

### 35.4. Không ACK poison event như success mà không có policy

Khi schema không hợp lệ, đẩy DLQ/quarantine kèm diagnostics an toàn; không im lặng bỏ qua event nếu loss không được chấp nhận.

## 36. Java: MongoDB-to-projector với checkpoint abstraction

Thực tế checkpoint nên là một component riêng:

```java
import org.bson.BsonDocument;

public interface ResumeTokenStore {
    BsonDocument load(String consumerId);
    void save(String consumerId, BsonDocument token);
}

public interface ChangeSink {
    // Idempotent transaction/update at destination.
    void apply(String eventType, String documentId,
               Object payload, String stableEventId);
}
```

Vòng xử lý khái niệm:

```java
public final class ChangeStreamRunner {
    private final ResumeTokenStore tokens;
    private final ChangeSink sink;

    public ChangeStreamRunner(
            ResumeTokenStore tokens,
            ChangeSink sink
    ) {
        this.tokens = tokens;
        this.sink = sink;
    }

    public void processEvent(
            String consumerId,
            String type,
            String documentId,
            Object payload,
            String stableEventId,
            BsonDocument resumeToken
    ) {
        // Phải xử lý sink một cách idempotent.
        sink.apply(
                type, documentId, payload, stableEventId
        );

        // Có thể retry event nếu process crash
        // giữa apply và checkpoint.
        tokens.save(consumerId, resumeToken);
    }
}
```

### 36.1. Mã chưa chứng minh exact-once

Nếu sink update commit nhưng token save fail, event replay. `ChangeSink` bắt buộc có dedupe/version rules.

### 36.2. Không chỉ convert token thành string tùy ý

MongoDB resume token là BSON token opaque; checkpoint store cần serialize/deserialize nguyên vẹn theo compatible representation.

### 36.3. Lỗi token hết hạn

Không catch rồi chạy lại `watch()` từ hiện tại mà không cảnh báo. Cần resnapshot/reconciliation vì có thể đã bỏ một đoạn dữ liệu.

### 36.4. Multi-instance

Nhiều runners cùng consumerId không được tự tranh ownership và overwrite checkpoint; cần lease/fencing hoặc connector framework quản lý partitions.

## 37. Sink update bằng optimistic version guard

Giả sử nguồn Order là MongoDB và sink cũng MongoDB, có thể thiết kế một projector collection:

```json
{
  "_id": "O100",
  "status": "CANCELLED",
  "sourceVersion": 12,
  "deleted": false
}
```

Rule:

```text
UPDATE projected_orders
IF sourceVersion < incoming.sourceVersion OR item absent
SET status, sourceVersion, deleted
```

Nếu dùng MongoDB native `updateOne`, có thể đưa điều kiện vào filter, nhưng việc **upsert cùng filter chứa version** dưới concurrency cần unique key và xử lý duplicate-key/conflict theo đúng thiết kế. Không giả định một upsert filter bất kỳ tự thực thi atomic max-register trên mọi đường race.

### 37.1. Phân biệt duplicate với gap

Nếu sink current v10 nhận v12:

- Với snapshot state event: có thể chấp nhận v12, nếu business semantics cho phép bỏ v11.
- Với delta v12: phải chờ/replay v11 hoặc xử lý gap.
- Với transactional event nhóm: có thể cần toàn bộ nhóm trước apply.

### 37.2. Event-ID inbox

Một sink có thể ghi `Inbox(eventId)` cùng business update trong local transaction. Cần retention đủ lâu cho replay window.

### 37.3. External effects

Nếu consumer gửi email thay vì chỉ update projection, `sourceVersion` không thay idempotency của email provider/workflow.

## 38. Monitoring: biết CDC đang bắt kịp hay mất dữ liệu

Các nhóm metrics nên có:

| Nhóm | Metrics/điều cần quan sát | Ý nghĩa |
|---|---|---|
| Source | Log size, oldest retained position, oplog window | Consumer còn cơ hội resume không? |
| Connector | Source position, last poll time, retries/errors | Có đọc stream tiến triển không? |
| Broker | Publish lag, topic partitions, write errors | Events có tới nơi phát không? |
| Consumer | Lag, last checkpoint, retry count | Sink xử lý tới đâu? |
| Sink | Applied version, write failures, stale events rejected | Projection đúng độ mới không? |
| Snapshot | Records scanned, snapshot watermark, progress | Bootstrap có kẹt không? |
| Schema | Serialization/decode failures, unknown versions | Thay đổi schema có phá pipeline không? |
| Delete | Tombstones applied, orphan records | Xóa có được chuyển tới sink không? |
| Capacity | Queue backlog, throughput, hot partitions | Có nghẽn/backpressure không? |
| Business | Missing orders in search, cache stale, orphan payments | Invariant cuối cùng có đúng không? |

### 38.1. Lag có nhiều định nghĩa

- Source event time → connector capture time.
- Connector capture time → broker publish time.
- Broker publish time → sink apply time.
- Source commit version → sink applied version.

Một pipeline báo “consumer lag=0” ở broker nhưng source connector đã đứng im không publish events vẫn có thể **mất cập nhật nghiêm trọng**.

### 38.2. Oldest available position

Khi checkpoint tiến chậm hơn tốc độ log retention, cần alert trước khi history mất.

### 38.3. Coverage

Giám sát số source items, sample checksums, key coverage và reconciliation results; CDC lag thấp không đảm bảo từng record đúng.

### 38.4. Alert theo SLO

Ví dụ “90% Product updates xuất hiện trong Search trong 10 giây; p99 trong 60 giây” chỉ là minh họa SLO cần đo, không phải guarantee mặc định của CDC.

## 39. Backpressure và thay đổi tải

Giả sử:

```text
Source emits:        20,000 events/s
Connector processes: 15,000 events/s
```

Theo mô hình đơn giản:

\[
\text{backlog tăng}=20\,000-15\,000=5\,000\ \text{events/s}
\]

Sau 10 phút, backlog tăng khoảng 3 triệu events nếu tốc độ giữ nguyên và không có coalescing.

### 39.1. Tăng số workers chưa chắc hiệu quả

Nếu một shard đơn lẻ là bottleneck, thêm 10 consumers có thể không tăng throughput theo tỷ lệ. Cần kiểm tra partition topology và sink bottleneck.

### 39.2. Burst

Snapshot/backfill phát hàng triệu writes vào Elasticsearch gây spike. Cần batch size, bulk API, throttling và traffic isolation.

### 39.3. Source safety

Một số CDC implementations có thể ảnh hưởng disk/CPU hoặc source write availability khi output không được drain. Đừng xem CDC là “đọc log miễn phí”.

### 39.4. Bounded queues

Queue không giới hạn che giấu sự cố bằng cách tăng memory/disk cho đến khi sập. Giới hạn capacity, reject/throttle hoặc scale có kiểm soát.

### 39.5. Retry budget

Exponential backoff, jitter, DLQ cho poison events. Retry storm có thể làm cả source và sink chậm hơn.

## 40. Bảo mật và quyền truy cập CDC

CDC thường nhạy cảm hơn query thông thường vì có thể nhìn thấy **mọi thay đổi của một collection**, bao gồm dữ liệu đã xóa hoặc chưa từng được trả qua application API.

### 40.1. Least privilege

Connector nên chỉ có quyền đọc những collections/logs cần thiết; tránh cấp admin/root nếu API cho phép hạn chế.

### 40.2. TLS, secrets và rotation

Bảo vệ connection giữa source, connector, broker và sink. Credentials không được hardcode trong YAML/config Git.

### 40.3. PII và before images

Một before image có thể chứa số điện thoại/địa chỉ cũ người dùng đã yêu cầu xóa. Việc lưu vào broker/DLQ cần retention và deletion policy.

### 40.4. Audit

Lưu connector identity, configuration changes, last checkpoint và người có quyền đọc replay logs.

### 40.5. Multi-tenant isolation

Nếu events nhiều tenants chia topic, subscriber phải được ủy quyền. Nếu index một record sai tenant do thiếu tenantId trong key, CDC có thể gây data leak.

### 40.6. DLQ cũng là nơi lưu dữ liệu

Không đẩy raw customer payload vào dead-letter topic vô thời hạn rồi coi đã đáp ứng data deletion từ source.

## 41. Case study A: MongoDB sang Elasticsearch

**Bối cảnh:** MongoDB chứa sản phẩm authoritative. Search là read model cho truy vấn full-text.

```text
Product Service
     |
     v
MongoDB products
     |
     v
Change Streams
     |
     v
Kafka / CDC relay
     |
     v
Elasticsearch products_v2
```

### 41.1. Bootstrap

- Tạo index versioned `products_v2`.
- Bắt đầu CDC từ checkpoint phù hợp.
- Snapshot products.
- Apply theo version guard.
- Reconcile deletes và late updates.
- Đợi CDC consumer catch up tới watermark.
- Kiểm tra counts/samples và alias switch.

### 41.2. UPDATE

Một raw `$set` event có thể chỉ chứa delta; có thể đọc full document theo mode hoặc materialize state rồi index. Tránh coi `updateLookup` luôn là exact after-image cho mọi event.

### 41.3. DELETE

Dùng documentKey để delete đúng index ID. Giữ source version/tombstone strategy chống old upsert replay.

### 41.4. Query freshness

Sau MongoDB commit, search có thể chưa thấy record do CDC lag và index refresh. Checkout/pricing không dùng Search index làm authority.

### 41.5. Failure

Nếu resume token quá cũ, rebuild thay vì skip events. Nếu Elasticsearch bulk partial failure, retry failed items idempotently.

## 42. Case study B: DynamoDB Streams sang cache invalidation

**Bối cảnh:** DynamoDB là source, Redis cache chứa public product view.

```text
DynamoDB Product table
      |
      v
DynamoDB Streams
      |
      v
Lambda consumer
      |
      v
Redis DEL product:P100
```

### 42.1. Vấn đề cơ bản

Delete event có thể tới trễ sau khi source update. Trong khoảng đó, Redis còn dữ liệu cũ.

### 42.2. Một stale fill race

Reader nạp version 41 từ nguồn stale rồi ghi cache sau khi event version 42 đã invalidate. Nếu cần monotonic cached state, dùng version-aware cache update hoặc source minVersion path.

### 42.3. Stream retention

Nếu Lambda/connector ngừng quá khoảng retention, không thể dựa vào Streams để phát lại mọi update; phải có cách rebuild/invalidate toàn bộ namespace hoặc reconciliation.

### 42.4. Không biến event thành payment trigger

Một mutation product description không được làm phát sinh payment/fulfillment; consumer chỉ cập nhật projection/cache đúng trách nhiệm.

## 43. Case study C: Cassandra CDC sang analytics

**Bối cảnh:** Cassandra lưu time-series theo thiết bị, analytics muốn dữ liệu thay đổi.

```text
Java Ingest
    |
    v
Cassandra time_series_by_device
    |
    v
CDC commitlog stream / connector
    |
    v
Kafka
    |
    v
Warehouse
```

### 43.1. Row update vs metric event

Nếu Cassandra lưu cùng một row aggregate được cập nhật nhiều lần, CDC bắt mutations của row không tự là một event nghiệp vụ cho mỗi sensor reading.

### 43.2. TTL

Dữ liệu time-series hết hạn theo TTL. Warehouse retention có thể khác Cassandra; phải định nghĩa xóa, expiration và privacy policy.

### 43.3. Repair/replay

Cassandra reconciliation và CDC commitlog semantics khác với thứ tự arrival. Dùng mutation timestamp/version/operationId phù hợp để chống old update.

### 43.4. Source pressure

Nếu consumer chậm, CDC raw log disks có thể đầy; cần disk thresholds, cleanup theo API, alert và recovery runbook.

## 44. Case study D: Order + transactional outbox qua CDC

**Bối cảnh:** Order Service muốn phát `OrderConfirmed` tới các service khác.

```text
Local transaction:
  Order O100.status=CONFIRMED
  Outbox E100=OrderConfirmed
  COMMIT
       |
       v
  CDC on Outbox
       |
       v
  Broker order-events
       |
       v
  Shipping, Notification, Analytics
```

### 44.1. Phân biệt mutation và intent

Source `Order.status` chỉ chứa trạng thái. Outbox `OrderConfirmed` biểu diễn business fact.

### 44.2. Dedupe

E100 có stable eventId. Nếu connector publish lại sau crash, shipping không tạo hai shipments cho cùng `orderId/shipmentOperationId`.

### 44.3. Unknown result ở Payment

Một `PaymentCaptured` event không được suy từ timeout của API. Payment Service chỉ phát sự thật sau khi provider outcome được xác minh.

### 44.4. Compensation

Nếu shipment đã được tạo và order bị hủy, cần cancellation workflow, không thể “rollback Kafka message”.

### 44.5. Khi nào cần Saga?

Khi Order, Inventory và Payment sở hữu các local DB khác nhau, CDC/outbox truyền events nhưng **không tự tạo atomic transaction xuyên services**. Saga/TCC và idempotency giải quyết workflow.

## 45. Chọn CDC theo use case

| Use case | Hướng thường phù hợp | Lưu ý |
|---|---|---|
| Đồng bộ MongoDB sang search | MongoDB Change Streams/connector | Resume token, snapshot, delete, refresh |
| DynamoDB item changes sang Lambda | DynamoDB Streams | 24h retention, shards, duplicate batches |
| Cosmos DB sang projection | Change Feed/Processor | Feed mode, partitions, deletes, leases |
| Cassandra bảng có CDC | Native CDC/connector | Commitlog decode, disk, tombstones, versions |
| Couchbase sang Kafka | DCP connector được hỗ trợ | vBucket seq/rollback |
| Neo4j graph changes | Native CDC feature theo version | Nodes + relationships, stable IDs |
| Redis ứng dụng cần durable event flow | Redis Streams do app phát, hoặc source CDC | Không nhầm keyspace notifications với durable CDC |
| Order domain events | Transactional outbox + CDC | Không suy domain facts từ mọi raw mutation |
| Analytical backfill | Snapshot + streaming | Watermarks, schema, reconciliation |
| Cache invalidation | CDC/outbox -> consumers | Lag và stale fill race |
| Billing/ledger external effects | Authoritative transaction + event intent | Idempotency/provider reconciliation |
| System không có native CDC | Polling outbox/version hoặc ứng dụng phát events | Không bỏ sót deletes/timestamp collisions |

Bảng là định hướng, không thay compatibility matrix hoặc service documentation.

## 46. Những nhầm lẫn phổ biến

**“CDC và replication là một.”** Không. Có thể dùng cùng log nhưng khác mục tiêu và consumer contract.

**“Có stream là tự động có event nghiệp vụ.”** Không. Raw mutation chưa đủ diễn tả business intent.

**“Đã publish Kafka thì downstream đã cập nhật.”** Không. Sink có checkpoint/lag riêng.

**“Một source event chỉ tới một lần.”** Không. Retry/replay có thể tạo duplicate.

**“Chạy connector từ now là copy toàn bộ database.”** Không. Cần snapshot/backfill.

**“Snapshot xong mới mở stream sẽ không có gap.”** Sai nếu có writes trong thời gian snapshot.

**“Chỉ cần ghi checkpoint trước để khỏi duplicate.”** Nguy hiểm vì có thể bỏ mất event khi crash trước sink commit.

**“Resume token giữ mãi mãi.”** Không; log/feed có retention và invalidation semantics.

**“Sequence lớn hơn ở shard B luôn mới hơn shard A.”** Không. Sequence có scope.

**“Một source transaction sinh một Kafka message.”** Không mặc định; có thể tách nhiều change events.

**“Event tới sau là state mới hơn.”** Không. Out-of-order delivery và source timestamps/versions.

**“Delete xong có thể xóa mọi marker.”** Cẩn thận old upserts có thể hồi sinh document.

**“TTL expiry luôn xuất hiện thành DELETE event trong mọi DB.”** Không. Tùy engine/mode.

**“MongoDB UPDATE_LOOKUP luôn trả đúng post-image tại thời điểm update.”** Không phải guarantee tổng quát.

**“DynamoDB Streams giữ mọi dữ liệu vĩnh viễn.”** Không; retention hữu hạn.

**“Cassandra bật cdc=true sẽ tự phát Kafka topic.”** Không. Cần consumer/connector.

**“Cosmos Change Feed luôn chứa deletes trong mọi mode.”** Không.

**“Redis Streams tự bắt mọi SET.”** Không; ứng dụng phải XADD hoặc dùng integration cụ thể.

**“Keyspace notifications đủ cho audit bền vững.”** Không; Pub/Sub không bảo đảm replay.

**“Kafka exactly-once biến email/payment thành exactly-once.”** Không qua external API mặc định.

**“Search bulk success có nghĩa toàn batch đã index thành công.”** Phải kiểm tra từng item.

**“Thêm consumers vô hạn sẽ hết lag.”** Không nếu source shard/sink là bottleneck.

**“CDC lag=0 nghĩa mọi dữ liệu đã đúng.”** Không; connector có thể ngừng đọc hoặc sink đã drop events.

**“CDC dữ liệu đã xóa không cần retention/privacy policy.”** Sai; log/DLQ/warehouse có thể còn PII.

## 47. Kiểm thử các failure modes quan trọng

### Test 1 — Source update và capture

Ghi `Order O100.status=PAID`; xác minh một change được quan sát với key đúng.

### Test 2 — Connector crash trước broker publish

Đọc event nhưng crash; restart từ checkpoint phải xử lý lại, không bỏ event.

### Test 3 — Broker publish thành công, ACK mất

Connector publish lại; consumer phải nhận diện duplicate.

### Test 4 — Sink commit rồi checkpoint lỗi

Restart replay; sink giữ một kết quả đúng nhờ idempotency.

### Test 5 — Checkpoint quá sớm

Cố tình mô phỏng save checkpoint trước sink update rồi crash; quan sát nguy cơ lost event. Đây là anti-pattern để học, không triển khai production.

### Test 6 — Oplog/stream retention gap

Dừng consumer quá window; pipeline phải báo `GAP_DETECTED`, không im lặng chuyển đến latest.

### Test 7 — Snapshot và concurrent update

Snapshot đọc v9, CDC apply v12, snapshot v9 tới sau. Sink không được rollback.

### Test 8 — Snapshot và delete

Snapshot ghi document cũ, delete event đến. Kết quả phải xóa đúng.

### Test 9 — Out-of-order

Giao v12 rồi v11; full-state projection phải giữ v12.

### Test 10 — Delta gap

Giao increment v12 trước v11; consumer phải phát hiện missing delta/hold/replay, không bỏ qua tùy tiện.

### Test 11 — Multi-partition

Events từ shard A/B đảo thứ tự; chỉ dựa vào ordering trong scope hỗ trợ.

### Test 12 — Transaction across documents

Nguồn commit hai documents trong một transaction; sink có chấp nhận trạng thái trung gian không?

### Test 13 — CDC delete/no before image

Sink vẫn xóa được record dựa vào document key.

### Test 14 — TTL

Source TTL expires; kiểm tra feed mode có record nào và sink biết expiry bằng cách nào.

### Test 15 — Schema rename

Producer đổi `status` thành `payment.state`; consumer cũ xử lý đúng backward compatibility hoặc quarantine.

### Test 16 — Poison event

Một payload invalid không được làm worker crash loop vô hạn hoặc skip event không có log.

### Test 17 — Slow sink

Giảm sink throughput; quan sát backlog, retention risk và backpressure.

### Test 18 — Search partial bulk failure

Một batch có 3 records lỗi; retry riêng records lỗi mà không nhân đôi những records thành công.

### Test 19 — Consumer rebalancing

Worker A mất lease, B tiếp quản; không để A stale write làm sink rollback.

### Test 20 — Multi-region duplicates

Cùng logical mutation có thể được nhìn qua nhiều region feeds; tránh phát external side effect hai lần.

### Test 21 — CDC outage rồi resnapshot

Khởi động lại pipeline bằng snapshot mới, xử lý race với live stream và deletes.

### Test 22 — GDPR-style deletion

Xóa user ở source; xác minh search, warehouse, cache, DLQ retention và backfill không tái tạo dữ liệu.

### Test 23 — Change Stream invalidation

MongoDB collection drop/rename; kiểm tra token/stream lifecycle và recovery path.

### Test 24 — DynamoDB TTL event

Xác minh behavior DELETE metadata trong đúng stream view và region mode.

### Test 25 — Cassandra CDC raw logs

Consumer không drain; quan sát disk budget và source write pressure trong staging.

### Test 26 — Duplicate event ID collision

Hai payloads khác nhau dùng cùng eventId; hệ phải phát hiện integrity error.

### Test 27 — Replay old update after delete

DELETE v12 đã áp dụng, UPSERT v11 replay; sink không hồi sinh record.

### Test 28 — Replay payment event

`PaymentCaptured` được nhận hai lần; không gọi provider charge thêm lần nào.

### Test 29 — Consumer lag metric sai

Broker lag gần zero nhưng source connector không đọc events; monitor phải phát hiện source position đứng yên.

### Test 30 — Migration cutover

Build index mới, catch-up đến watermark, so counts/sample queries, chuyển alias và giữ rollback route.

## 48. Bài tập thực hành

### Bài tập 1 — Phân biệt CDC và outbox

Một service chỉ ghi `Order.status=PAID` vào MongoDB và Change Stream phát UPDATE.

**Câu hỏi:** Đây đã là business event `PaymentCaptured` đáng tin chưa?

**Gợi ý:** Chưa; một raw mutation không giải thích đầy đủ business cause. Có thể dùng transactional outbox.

### Bài tập 2 — Dual write

MongoDB commit nhưng process crash trước Kafka publish.

**Câu hỏi:** CDC/outbox giải quyết khoảng trống nào?

**Gợi ý:** Phát hiện/ghi intent sau source commit mà không phụ thuộc lời gọi publish riêng.

### Bài tập 3 — Snapshot gap

Snapshot hoàn tất lúc 11:00, CDC bắt đầu ở 11:01.

**Câu hỏi:** Vì sao một update 10:59 có thể mất?

**Gợi ý:** Snapshot đã quét key trước đó.

### Bài tập 4 — Backfill stale

CDC v12 đã index, snapshot v9 đến sau.

**Câu hỏi:** Cần gì?

**Gợi ý:** Version-aware conditional apply.

### Bài tập 5 — Checkpoint

Consumer xử lý event rồi checkpoint, nhưng crash giữa hai bước.

**Câu hỏi:** Event có thể bị giao lại không? Làm sao an toàn?

**Gợi ý:** Có; sink idempotent.

### Bài tập 6 — Checkpoint trước sink

Consumer lưu checkpoint rồi crash trước update.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Lost event.

### Bài tập 7 — Opaque token

Một team so MongoDB resume tokens bằng chuỗi để quyết định token nào lớn hơn.

**Câu hỏi:** Đúng không?

**Gợi ý:** Không; token opaque, dùng API/documentation.

### Bài tập 8 — Retention

Consumer downtime vượt lịch sử oplog/stream.

**Câu hỏi:** Có được restart từ newest và báo healthy không?

**Gợi ý:** Không; cần resnapshot/reconciliation.

### Bài tập 9 — DynamoDB Streams

Muốn cả before và after images.

**Câu hỏi:** Chọn view type nào?

**Gợi ý:** `NEW_AND_OLD_IMAGES`.

### Bài tập 10 — DynamoDB 24h

Consumer ngừng 36 giờ.

**Câu hỏi:** Có thể tin Streams replay toàn bộ không?

**Gợi ý:** Không; retention khoảng 24 giờ. Cần recovery.

### Bài tập 11 — Cassandra CDC

Bật `cdc = true`, chưa cài connector/reader.

**Câu hỏi:** Kafka đã có topic chứa events chưa?

**Gợi ý:** Không mặc định.

### Bài tập 12 — Cosmos latest-version feed

Consumer muốn biết mọi intermediate update và deletes.

**Câu hỏi:** Dùng latest-version mode mặc định có đủ không?

**Gợi ý:** Không suy; xem all versions/deletes mode và limits.

### Bài tập 13 — Redis Streams

Ứng dụng gọi `SET order:O100 PAID` và không XADD.

**Câu hỏi:** Stream `order-events` tự có record không?

**Gợi ý:** Không.

### Bài tập 14 — Redis keyspace notifications

Một subscriber offline 5 phút.

**Câu hỏi:** Có replay tất cả events từ Pub/Sub notifications không?

**Gợi ý:** Không mặc định.

### Bài tập 15 — Delete tombstone

Sink nhận DELETE v12 rồi UPSERT v11.

**Câu hỏi:** Nếu delete đã xóa lastVersion thì sao?

**Gợi ý:** Record cũ có thể resurrect; giữ marker/version.

### Bài tập 16 — Delta stream

Events `INCREMENT +1` v11 và v12 đến đảo thứ tự.

**Câu hỏi:** Chỉ giữ version lớn nhất có đúng không?

**Gợi ý:** Không; có thể mất một increment.

### Bài tập 17 — Search lag

MongoDB commit Order v12, Elasticsearch chưa thấy.

**Câu hỏi:** Có chứng minh source write thất bại không?

**Gợi ý:** Không; projection CDC/index refresh có thể trễ.

### Bài tập 18 — Schema evolution

`status` đổi thành `payment.state`.

**Câu hỏi:** Vì sao consumer cần schema version?

**Gợi ý:** Tránh decode/interpret sai old/new payloads.

### Bài tập 19 — Multi-shard order

Event shard A seq=100 và shard B seq=120.

**Câu hỏi:** Có thể kết luận B xảy ra sau A không?

**Gợi ý:** Không nếu sequences có scope theo shard.

### Bài tập 20 — Two-phase order

Một MongoDB transaction thay 2 documents, CDC phát 2 events.

**Câu hỏi:** Sink thấy cả hai atomically không?

**Gợi ý:** Không tự động.

### Bài tập 21 — MongoDB fullDocument

`UPDATE_LOOKUP` trả fullDocument có state mới hơn delta event.

**Câu hỏi:** Tại sao có thể xảy ra?

**Gợi ý:** Lookup sau event, document có thể đã bị sửa tiếp.

### Bài tập 22 — Couchbase DCP

Sau failover connector nhận rollback instruction.

**Câu hỏi:** Có thể tiếp tục blindly từ seq cũ không?

**Gợi ý:** Không; phải xử lý failover/rollback protocol.

### Bài tập 23 — Neo4j delete edge

Consumer chỉ rebuild nodes, bỏ qua relationship events.

**Câu hỏi:** Projection graph có chính xác không?

**Gợi ý:** Không; edges cần event handling riêng.

### Bài tập 24 — Outbox duplicate

CDC relay publish outbox E100 hai lần.

**Câu hỏi:** Shipping Service cần làm gì?

**Gợi ý:** Inbox/idempotent shipment create theo operation identity.

### Bài tập 25 — Payment event

Consumer nhận `PaymentCaptured` rồi gọi charge payment lần nữa.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Event báo kết quả đã xảy ra, không phải command thu tiền.

### Bài tập 26 — SLO

Connector lag 0 nhưng source log position đứng yên 20 phút dù writes liên tục.

**Câu hỏi:** Metric thiếu gì?

**Gợi ý:** Source progress/freshness và end-to-end reconciliation.

### Bài tập 27 — Ảnh hưởng privacy

User yêu cầu xóa dữ liệu, source đã xóa nhưng DLQ còn raw before image.

**Câu hỏi:** Đã hoàn tất yêu cầu chưa?

**Gợi ý:** Cần policy đối với mọi copies, retention, backup và downstream.

### Bài tập 28 — Scale-out

Một source shard tối đa xử lý 1.000 events/s, thêm 20 consumers.

**Câu hỏi:** Throughput có chắc tăng 20 lần không?

**Gợi ý:** Không; shard và sink limits.

### Bài tập 29 — Initial index cutover

Build products_v2 từ snapshot rồi tail CDC, nhưng chưa kiểm tra deletes.

**Câu hỏi:** Có nên chuyển alias ngay?

**Gợi ý:** Không; kiểm tra completeness, deletes, lag/watermark, parity.

### Bài tập 30 — Thiết kế kiến trúc

Một công ty dùng MongoDB cho Orders, DynamoDB cho Inventory, Redis cho cache, Elasticsearch cho search và Kafka làm broker.

**Yêu cầu:** Đề xuất CDC/outbox theo từng nguồn, checkpoint, idempotency, delete handling và runbook sau downtime 2 ngày.

**Gợi ý:** MongoDB Change Streams+outbox, DynamoDB Streams với retention risk, Redis cache không là source CDC, index version guard, snapshot/rebuild khi gap, API quyền ghi vẫn tại source authority.

## 49. Checklist thiết kế CDC production

- [ ] Đã phân biệt raw mutation event và business/integration event.
- [ ] Đã xác định source of truth và ownership từng collection/table.
- [ ] Đã biết log-based, native feed, trigger hay polling đang dùng.
- [ ] Đã đọc đúng CDC contract theo database edition/version.
- [ ] Đã chọn capture scope (collection/table/partition/region) rõ.
- [ ] Đã xác định source position và token có opaque không.
- [ ] Đã thiết kế initial snapshot cùng stream boundary.
- [ ] Đã xử lý concurrency giữa backfill và live updates.
- [ ] Đã thiết kế deletes, soft deletes, TTL và tombstone retention.
- [ ] Đã xác định before/after images có sẵn hay phải lookup.
- [ ] Không suy `UPDATE_LOOKUP` là exact post-image mọi lần.
- [ ] Đã định nghĩa ordering scope theo shard/key/aggregate.
- [ ] Có stable eventId hoặc atomic source version cho dedupe.
- [ ] Có sink idempotency/version-aware apply.
- [ ] Có xử lý delta events và version gaps.
- [ ] Chỉ checkpoint sau sink success theo contract.
- [ ] Có policy khi checkpoint save fail và event replay.
- [ ] Có detection khi source history hết retention.
- [ ] Không tự skip về latest khi có gap.
- [ ] Có backfill/rebuild/reconciliation runbook.
- [ ] Có schema evolution và compatibility policy.
- [ ] Có retry, DLQ/quarantine và poison event policy.
- [ ] Có backpressure, bounded queues và throughput capacity.
- [ ] Có source log/disk retention margin đủ.
- [ ] Có connector ownership/lease và rebalance strategy.
- [ ] Đã test multi-region duplicates và failover semantics.
- [ ] Có metrics source position, connector lag và sink version.
- [ ] Có business completeness/freshness checks ngoài broker lag.
- [ ] Có TLS, IAM, least privilege và secrets rotation.
- [ ] Có PII redaction, retention, audit và delete propagation.
- [ ] Không biến CDC vào một distributed ACID transaction tưởng tượng.
- [ ] Không coi broker exactly-once là payment/email exactly-once.
- [ ] Đã diễn tập snapshot, replay, rollback, failover và cutover.
- [ ] Đã kiểm tra production SLA cho source stream và sink indexing.

## 50. Tổng kết

**Change Data Capture** giúp ứng dụng lấy các thay đổi đã commit từ NoSQL mà không phải thực hiện một dual write riêng cho mọi database mutation. Nhưng mỗi hệ cung cấp một cơ chế khác nhau:

- **MongoDB:** Change Streams/oplog với resume tokens, update descriptions và cấu hình fullDocument/pre-post images.
- **DynamoDB:** Streams theo item/shards với stream view types và history window ngắn, thường khoảng 24 giờ.
- **Cassandra:** CDC gắn commitlog/mutations, cần consumer/connector và quản lý disk, tombstones, timestamps.
- **Cosmos DB:** Change Feed/Processor với modes, partition ordering, leases và khả năng delete capture theo cấu hình.
- **Couchbase:** DCP với vBucket sequences, rollback/failover semantics.
- **Neo4j:** CDC phù hợp với graph nodes/relationships trong versions/editions được hỗ trợ.
- **Redis:** Streams do ứng dụng ghi khác keyspace notifications hoặc AOF; không tự là CDC cho mọi mutation.

Một CDC pipeline đáng tin cậy phải có **snapshot + stream không gap, checkpoint đúng thời điểm, idempotent sinks, ordering đúng phạm vi, delete/tombstone handling, schema evolution, retention-aware recovery và observability end-to-end**.

Khi cần truyền **ý định nghiệp vụ** thay vì chỉ trạng thái dữ liệu thô, kết hợp **transactional outbox với CDC** để tách local transaction khỏi message relay. Khi nghiệp vụ trải qua nhiều dịch vụ, dùng Saga/transaction/idempotency đúng phạm vi; CDC không tự tạo atomic commit trên các hệ đích.

**Nguyên tắc cốt lõi:** *CDC đáng tin không chỉ là nhận được event khi mọi thứ hoạt động bình thường, mà là chứng minh không bỏ sót thay đổi khi snapshot, network lỗi, consumer restart, schema đổi, record bị xóa, log hết retention và dữ liệu được replay.* Nếu không chứng minh được điều đó, hãy coi read model là một bản sao cần đối soát chứ chưa phải nguồn sự thật.


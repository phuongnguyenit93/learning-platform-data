# Luồng xóa dữ liệu, tombstone và thời gian lưu log

## 1. Mở đầu: bản ghi đã xóa vẫn xuất hiện trở lại

Một hệ thống thương mại điện tử dùng NoSQL làm nguồn dữ liệu chính, Change Data Capture (CDC) chuyển các thay đổi sang Kafka, rồi các consumer xây read model cho Search và Analytics:

~~~text
                        +--> Search Index
                        |
Orders NoSQL --> CDC --> Kafka --> Analytics NoSQL
                        |
                        +--> Notification/Other Consumer
~~~

Vào 10:00, người dùng xóa địa chỉ giao hàng. Database nguồn xác nhận xóa. CDC phát thay đổi và Search consumer cập nhật index. Tuy nhiên Analytics consumer đang offline; nó chỉ kết nối lại sau khi một phần log đã hết thời hạn lưu.

Khi đó có thể xảy ra:

~~~text
10:00  Source: DELETE address:42
10:00  CDC: phát delete event
10:01  Search: loại address:42
10:01  Analytics: đang offline
Ngày 3 Kafka/CDC log: một phần lịch sử đã bị dọn
Ngày 4 Analytics: khởi động từ snapshot cũ hoặc checkpoint hết hiệu lực
       -> không còn thấy delete event
       -> giữ hoặc phục hồi address:42
~~~

Nếu chỉ kiểm tra database nguồn, thao tác xóa đã thành công. Nhưng ở toàn bộ hệ thống, bản ghi vẫn tồn tại trong một read model. Nếu đây là dữ liệu cá nhân, hậu quả còn liên quan đến bảo mật và yêu cầu xóa dữ liệu.

Bài học **“Luồng xóa dữ liệu, tombstone và thời gian lưu log”** thuộc chương **“Sự kiện và CDC”** trong module **Database No SQL**.

Điểm cốt lõi là: **xóa một row/document ở nguồn không đồng nghĩa mọi bản sao và downstream projection tự biết phải xóa**, nhất là khi sự kiện bị mất, đến trễ, bị compact hoặc consumer phục hồi từ snapshot cũ.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt business delete, soft delete, physical delete, database tombstone, CDC delete event và Kafka tombstone.
2. Hiểu vì sao CDC phải mang định danh, thứ tự phiên bản và semantics xóa đủ rõ.
3. Giải thích sự khác biệt giữa `retention.ms`, `delete.retention.ms`, log compaction, oplog/stream retention và backup retention.
4. Thiết kế consumer xử lý delete idempotently, không resurrect dữ liệu vì event đến muộn hoặc replay.
5. Phân tích đặc điểm xóa và CDC của MongoDB, DynamoDB, Cassandra, Redis và Kafka/Debezium.
6. Tính thời gian consumer có thể downtime và backlog catch-up trước khi mất khả năng replay.
7. Phối hợp snapshot và CDC stream khi rebuild một read model.
8. Đề xuất cách xử lý TTL expiration, privacy deletion, index cleanup và deletion audit.
9. Viết Java handler có kiểm tra phiên bản và giữ logical tombstone ở projection.
10. Thiết kế runbook, fault-injection tests và các chỉ số để biết deletion thực sự lan đến đâu.

---

## 2. Sáu loại “xóa” không được đánh đồng

| Khái niệm | Đối tượng | Ý nghĩa | Rủi ro nếu hiểu nhầm |
|---|---|---|---|
| **Business delete** | Thực thể nghiệp vụ | Người dùng/hệ thống yêu cầu chấm dứt sử dụng dữ liệu | Event chỉ biểu thị ý định, chưa chắc physical purge |
| **Soft delete** | Document/row | Đánh dấu `deleted=true`, có thể giữ nội dung | Consumer vẫn hiển thị nếu quên filter |
| **Physical delete** | Storage record | Xóa bản ghi khỏi đường đọc thông thường | Có thể còn trong log, backup, replica |
| **DB tombstone** | Storage engine | Metadata đánh dấu dữ liệu đã xóa để reconcile/compaction | GC quá sớm có thể làm dữ liệu cũ hồi sinh |
| **CDC delete event** | Event stream | Thông báo một thay đổi xóa từ nguồn | Consumer có thể bỏ qua, parse sai, trễ |
| **Kafka tombstone** | Log-compacted topic | Message có **key** và **value null** biểu thị xóa giá trị cho key trong log compacted | Consumer hiểu `null` là parse error hoặc giữ stale state |

**Không có một “tombstone chung” cho toàn hệ**. Cassandra tombstone là cơ chế lưu trữ của Cassandra, còn Kafka tombstone là record có giá trị null dùng với log compaction. Hai cơ chế có mục đích liên quan nhưng retention, xóa và giao thức khác nhau.

### 2.1. Ví dụ business delete

~~~json
{
  "eventType": "CustomerAddressRemoved",
  "eventId": "evt-delete-9001",
  "tenantId": "tenant-7",
  "addressId": "address-42",
  "sourceVersion": 18,
  "occurredAt": "2026-11-14T09:30:00Z",
  "reasonCode": "USER_REQUEST"
}
~~~

Đây là **một domain event có ý nghĩa**. Nó có thể được lưu trong outbox, có schema/version và có metadata; không phải Kafka tombstone đơn thuần.

### 2.2. Ví dụ physical delete trong NoSQL

~~~javascript
db.addresses.deleteOne({
  tenantId: "tenant-7",
  _id: "address-42"
});
~~~

Nếu lệnh thành công, document không còn trong collection theo semantics ghi được chọn. Nhưng một search index được cập nhật qua CDC **không tự biết** document đã biến mất trừ khi nhận và áp dụng tín hiệu phù hợp.

### 2.3. Ví dụ tombstone ở Kafka

~~~text
Topic: address-compacted
Key:   tenant-7|address-42
Value: null
~~~

Dạng này biểu thị rằng giá trị cuối cùng của key được đánh dấu xóa trong compacted topic. Nó khác event JSON `"operation":"DELETE"` có value không null.

### 2.4. Ví dụ tombstone ở Cassandra

Trong Cassandra, một mutation xóa thường tạo marker/tombstone để các replica và quá trình đọc/compaction biết không được phục hồi giá trị cũ. Không nên xem Cassandra tombstone là một message Kafka có payload null.

---

## 3. Phân biệt xóa logic, ngừng hiển thị và xóa vật lý

Một thực thể có thể đi qua những giai đoạn:

~~~mermaid
flowchart TD
    A["ACTIVE"] --> B["DELETE_REQUESTED"]
    B --> C["LOGICALLY_DELETED"]
    C --> D["CDC/Outbox DELETE emitted"]
    D --> E["Read models and indexes updated"]
    E --> F["Physical purge / retention cleanup"]
    F --> G["Backups and archives reconciled by policy"]
~~~

Tùy nghiệp vụ, một số bước có thể hợp nhất hoặc có thể không được phép giữ dữ liệu sau deletion request. Sơ đồ là **một mô hình vận hành minh họa**, không là quy trình pháp lý áp dụng cho mọi dữ liệu.

### 3.1. Soft delete

Ví dụ:

~~~json
{
  "_id": "address-42",
  "customerId": "cus-9",
  "deleted": true,
  "deletedAt": "2026-11-14T09:30:00Z",
  "version": 18
}
~~~

Ưu điểm: dễ giữ version, có thể phát hiện restore/replay cũ, giúp đồng bộ. Nhược điểm: dữ liệu có thể còn tồn tại; mọi query/index phải loại document đã xóa, và privacy policy có thể không cho giữ payload.

### 3.2. Physical purge

Một lệnh xóa document ở source có thể cần sau khi đã phát event hoặc ghi outbox đủ bền. Nếu xóa **trước khi CDC/outbox có khả năng ghi nhận**, downstream có thể không bao giờ nhận được tín hiệu.

### 3.3. Xóa khỏi giao diện không đồng nghĩa xóa khỏi hệ

Một API trả `404` có thể do filter `deleted=true`, trong khi object vẫn còn trong storage, backup, CDC log hoặc analytics export. Vì vậy phải định nghĩa **phạm vi xóa**: source, replica, cache, index, archive, durable event log và các bản sao liên quan.

### 3.4. Không suy chính sách retention từ tên `deletedAt`

Có timestamp xóa không tự đặt TTL hay xác nhận mọi bản sao sẽ được purge. Cần cơ chế cleanup, telemetry và bằng chứng thực thi.

---

## 4. Tại sao Delete event phải có thông tin đủ để downstream xử lý?

Một delete event nên giải đáp:

1. **Xóa thực thể nào?** Key đầy đủ theo tenant/entity.
2. **Thực thể thuộc phiên bản nào?** Version/generation để không xóa nhầm bản mới.
3. **Ai là nguồn có thẩm quyền?** Producer/stream/aggregate owner.
4. **Delete đã commit chưa?** Chỉ là ý định hay thay đổi đã được xác nhận?
5. **Delete có được phát lại?** Event ID và retry semantics.
6. **Có phải xóa tạm, vô hiệu hóa hay purge?** Semantics nghiệp vụ.
7. **Có liên quan đến dữ liệu cá nhân?** Tránh mang PII thừa vào event.
8. **Consumer xử lý thế nào khi không biết entity?** Idempotent delete, không cần before-image.
9. **Thứ tự so với create/update?** Per-key ordering/version.
10. **Consumer làm gì khi mất lịch sử?** Rebuild from source/tombstone ledger.

### 4.1. Một envelope minh họa

~~~json
{
  "eventId": "evt-901",
  "eventType": "CustomerAddressDeleted",
  "schemaVersion": 2,
  "tenantId": "tenant-7",
  "entityId": "address-42",
  "entityGeneration": 3,
  "sourceVersion": 18,
  "operation": "DELETE",
  "committedAt": "2026-11-14T09:30:00Z",
  "source": "customer-service",
  "payload": {}
}
~~~

`payload` rỗng có chủ ý: consumer có thể xóa theo key mà không cần phát lại địa chỉ cá nhân. Các field là thiết kế ví dụ, không phải chuẩn chung cho mọi CDC engine.

### 4.2. Không cần toàn bộ `before` payload để xóa

Một search index thường chỉ cần document ID để xóa. Phát toàn bộ thông tin người dùng trước khi xóa có thể làm lộ dữ liệu trong topic, logs hoặc DLQ.

Nếu consumer cần before-image để cập nhật aggregate, hãy xem có thể dùng data model lưu `lastAppliedSnapshot` hoặc metadata không nhạy cảm thay cho đưa nguyên dữ liệu vào event không.

### 4.3. Event ID khác entity ID

- `eventId` duy nhất cho **một thay đổi logic**, phục vụ idempotency.
- `entityId` định danh **thực thể bị xóa**.
- `sourceVersion` bảo vệ thứ tự trên thực thể.
- `entityGeneration` phân biệt nhiều vòng đời nếu cùng ID được tái sử dụng.

Không được tạo event ID mới khi retry publish cùng một delete logic nếu dedup phụ thuộc event ID.

---

## 5. Một dòng CDC thường có những thành phần nào?

Ví dụ envelope khái niệm cho delete:

~~~json
{
  "source": {
    "table": "customer_addresses",
    "partition": "tenant-7"
  },
  "key": {
    "tenantId": "tenant-7",
    "addressId": "address-42"
  },
  "op": "d",
  "before": {
    "tenantId": "tenant-7",
    "addressId": "address-42"
  },
  "after": null,
  "sourceOffset": "opaque-source-checkpoint",
  "eventTime": "2026-11-14T09:30:00Z"
}
~~~

Đây là **envelope minh họa**, không phải JSON byte-for-byte của tất cả connector. Một số CDC sources cung cấp before-image, số khác chỉ có keys; có nguồn phát thêm tombstone record hoặc metadata riêng.

### 5.1. `op=d` không đồng nghĩa `value=null`

Một JSON event với `op="d"` có **value là object**. Kafka tombstone có **value null**. Consumer phải phân biệt hai dạng.

### 5.2. `before` không luôn có sẵn

MongoDB change streams có thể chỉ chứa document key với delete event; pre-image cần được cấu hình và bị giới hạn bởi retention/availability. DynamoDB Streams chỉ có old image nếu StreamViewType tương ứng. Không xây delete flow bắt buộc có full before-image nếu source không bảo đảm.

### 5.3. `after=null` cũng cần ngữ cảnh

Trong envelope CDC, `after=null` với `op=d` có thể biểu thị delete. Trong một message schema khác, `after=null` có thể là unknown hoặc không có snapshot. Dùng **operation type** và codec schema; không đoán từ một field null.

### 5.4. Delete phải gắn với commit

Một database có thể ghi nhận một delete mutation trong transaction nhưng rollback trước commit. CDC cần phát theo **committed change** như contract; nếu ứng dụng tự phát event trước commit, downstream có thể xóa nhầm.

---

## 6. Luồng xóa từ nguồn tới consumer

~~~mermaid
sequenceDiagram
    participant U as User/API
    participant DB as Authoritative NoSQL
    participant CDC as CDC Connector
    participant K as Event Log
    participant C as Consumer
    participant P as Search/Projection

    U->>DB: Delete entity K (commit)
    DB-->>U: ACK theo write contract
    DB-->>CDC: Committed change / source log
    CDC->>K: Delete event for K
    K->>C: Deliver event (may retry)
    C->>P: Conditional delete / logical tombstone
    P-->>C: Applied or duplicate
    C-->>K: Commit offset/checkpoint
~~~

### 6.1. Độ trễ từng đoạn là riêng biệt

- Commit source.
- Source log/CDC availability.
- Connector capture.
- Broker publish.
- Consumer poll.
- Projection apply.
- Search index refresh.
- Cache invalidation.

Một ACK từ NoSQL source không đảm bảo search index đã xóa nếu đường đồng bộ bất đồng bộ.

### 6.2. Crash trước hoặc sau ACK

Nếu consumer xóa ở projection rồi crash **trước khi commit offset**, Kafka có thể redeliver. Consumer cần coi delete là idempotent theo event/version.

Nếu consumer commit offset **trước khi xóa projection**, rồi process crash, delete có thể bị mất về mặt nghiệp vụ. Checkpoint phải phù hợp với kết quả đã áp, hoặc workflow có durable retry/reconciliation.

### 6.3. CDC source log có thể hết hạn trước khi connector đọc

Ngay cả khi Kafka topic retention dài, source oplog/stream/commit-log có thể đã mất các thay đổi trước khi CDC chuyển chúng tới Kafka. Vì thế cần quản lý **cả hai retention horizons**.

---

## 7. Kafka: log retention và log compaction là hai cơ chế khác nhau

Kafka lưu các records theo partition. Hai nhóm cleanup thường được bàn đến:

- **Delete retention:** xóa các log segments cũ theo thời gian/dung lượng với topic `cleanup.policy=delete`.
- **Log compaction:** giữ trạng thái gần nhất theo **record key** theo quy tắc cleaner, với topic `cleanup.policy=compact`.

Có thể cấu hình kết hợp `compact,delete`; khi đó cả hai cơ chế có thể ảnh hưởng tập records còn tồn tại.

### 7.1. Topic dạng event history

~~~text
Key K: CREATE(v1)
Key K: UPDATE(v2)
Key K: DELETE(v3)
```

Nếu `cleanup.policy=delete`, sau retention window những records cũ có thể bị xóa ở mức log segment. Một consumer offline lâu có thể không còn replay đủ event history.

### 7.2. Compacted topic dạng latest state

~~~text
K -> value(v1)
K -> value(v2)
K -> null
```

Cleaner có thể bỏ các giá trị cũ của cùng key và cuối cùng xóa marker tombstone khi điều kiện retention/compaction cho phép.

### 7.3. Compaction không phải “ngay khi có update”

Records cũ và tombstones có thể còn một thời gian. Consumer không được giả định log đã chỉ còn một record/key tại mọi thời điểm.

### 7.4. Giữ order trong partition không giải quyết mọi chuyện

Kafka có ordering theo partition trong điều kiện giao thức tương ứng. Nếu cùng entity K bị publish vào **hai partitions khác nhau** do đổi key/partitioning strategy, không thể dùng offset giữa hai partitions làm global order.

### 7.5. `null` trong Kafka phải được xử lý trước deserializer business

Nếu consumer chỉ chấp nhận JSON object, Kafka tombstone có value `null` có thể tạo parsing failure hoặc bị bỏ qua. Handler cần nhận diện tombstone theo **record key + null value**.

---

## 8. Kafka tombstone: marker xóa cho key

Một log-compacted topic có thể chứa:

~~~text
Offset 100: key=user-42, value={"name":"An"}
Offset 120: key=user-42, value={"name":"Bình"}
Offset 150: key=user-42, value=null
```

Tombstone ở offset 150 đánh dấu user-42 đã bị xóa khỏi latest key state.

### 8.1. Tại sao cần key ổn định?

Compaction nhóm records theo **serialized key bytes**. Nếu producer thay khóa từ `"user-42"` sang `{"tenantId":"t1","userId":"42"}` mà không có migration, hai dạng key có thể bị coi là các keys khác nhau.

Delete tombstone dùng key mới có thể **không xóa** bản cũ theo key cũ.

### 8.2. Tombstone không có value JSON

Không phát:

~~~json
{
  "deleted": true
}
~~~

rồi mặc định Kafka cleaner coi đây là tombstone. Đó là **một giá trị bình thường** có flag. Chỉ **null value** của keyed record có semantics tombstone cho compacted topic.

### 8.3. Consumer không thể chỉ giữ “last non-null value”

Nếu consumer đọc từ đầu mà bỏ qua tombstones, nó có thể giữ latest value trước delete và làm dữ liệu hồi sinh.

### 8.4. Tombstone có thể biến mất sau compaction

Khi tombstone đã bị cleaner loại theo policy, đọc lại compacted log từ đầu có thể **không còn record cho key đã xóa**. Điều này hợp lý khi xây một **state mới từ log được compact đúng**, nhưng một consumer có **state cũ bên ngoài** vẫn cần cách biết phải xóa nó.

### 8.5. Không đồng nhất Kafka tombstone với domain delete event

Một domain event `CustomerDeleted` có thể cần giữ audit/replay/side effects; Kafka tombstone chỉ mô tả **latest state của một key** trong log compacted. Một pipeline có thể cần **cả hai** cho mục đích khác nhau.

---

## 9. `retention.ms` và `delete.retention.ms`

Các cấu hình Kafka thường gặp:

| Cấu hình | Vai trò khái quát | Điều không nên suy ra |
|---|---|---|
| `cleanup.policy=delete` | Xóa log segments theo retention | Mỗi record biến mất chính xác lúc hết TTL |
| `retention.ms` | Thời gian giữ segments theo delete policy | Consumer được replay mãi nếu log compacted có key |
| `retention.bytes` | Giới hạn kích thước log theo delete policy | Event history an toàn khi vượt capacity |
| `cleanup.policy=compact` | Compaction theo key | Log giữ mọi lịch sử giá trị |
| `delete.retention.ms` | Khoảng giữ delete tombstone trước khi cleaner có thể loại | Tombstone còn mãi, hay xóa ngay ở đúng timestamp |
| `min.compaction.lag.ms` | Trì hoãn eligible compaction cho records | Đủ thay thế retention của source CDC |
| `max.compaction.lag.ms` | Giới hạn thời gian record chưa eligible theo các điều kiện Kafka hỗ trợ | Mọi record sẽ bị compact chính xác theo giờ |
| `segment.ms`/segment size | Ảnh hưởng việc roll segments, liên quan cleanup | Retention tác động từng message ngay lập tức |

Các tương tác cụ thể phụ thuộc phiên bản Kafka/topic configuration. Khi vận hành phải kiểm tra config thực tế và hành vi của log cleaner, không tự đặt SLA từ tên tham số.

### 9.1. Ý nghĩa quan trọng của `delete.retention.ms`

Trong compacted topics, tombstone có thể cần tồn tại đủ lâu để **consumer đang đọc một log từ đầu** nhìn thấy delete marker trước khi nó bị cleaner loại. Nếu việc scan/rebuild kéo quá lâu, consumer có thể bỏ lỡ marker và tạo một latest-state không hợp lệ.

### 9.2. Không coi `delete.retention.ms` là retention của mọi CDC event

Nó có vai trò riêng với tombstone markers trong log compaction. Những events create/update/delete dạng envelope ở topic không compact có thể bị ảnh hưởng bởi retention policy khác.

### 9.3. Kết hợp `compact,delete`

Nếu topic dùng cả hai cleanup policies, một số data vẫn có thể bị xóa do time/size retention dù compaction giữ latest record theo key. Vì vậy không hứa “compacted topic luôn là full source of truth” khi delete cleanup cũng đang hoạt động.

### 9.4. Chỉ số offset không tự thể hiện hết retention

Một offset có thể không còn đọc được sau cleanup. Consumer có checkpoint offset X không đảm bảo Kafka còn dữ liệu từ X; cần so với earliest available offset và khả năng khởi động lại.

---

## 10. Debezium delete event và tombstone event

Trong nhiều cấu hình Debezium connector, một source delete có thể dẫn tới **hai record có ý nghĩa khác nhau**:

~~~text
Record 1:
  key = {"id":"42"}
  value = {
    "op":"d",
    "before": {...},
    "after":null,
    "source":{...}
  }

Record 2:
  key = {"id":"42"}
  value = null
```

Record 1 cung cấp **thông tin thay đổi**; record 2 là **Kafka tombstone** để hỗ trợ log compaction. Việc phát tombstone có thể cấu hình, và hình dạng envelope/field/tên option phụ thuộc connector và phiên bản.

### 10.1. Hai record không nhất thiết là hai lần xóa nghiệp vụ

Một consumer cập nhật search index có thể nhận cả `op=d` và tombstone. Nó nên xử lý idempotently; không gửi hai email “đã xóa” hay tính hai lần user deletion.

### 10.2. Consumer có thể chọn một trong hai làm tín hiệu, nhưng cần biết cả hai

Nếu chỉ dùng `op=d`, tombstone vẫn phải được bỏ qua/áp đúng khi decode. Nếu chỉ dùng tombstone, một topic không compact/connector tắt tombstone emission có thể không có record đó.

### 10.3. SMT/transformation có thể thay hình dạng

Một single-message transform như unwrap/envelope flattening có thể thay cách thể hiện delete. Sau khi cấu hình, cần kiểm thử **cả delete và tombstone**; không dựa vào ví dụ envelope của connector trước transform.

### 10.4. Schema registry

Tombstone có value null, nên schema-aware decoder phải biết xử lý null trước khi cố parse payload business. Không gán null value là “JSON corrupt” rồi retry vô hạn.

---

## 11. Ba nơi có thể giới hạn replay: source log, broker và consumer checkpoint

Một pipeline:

~~~text
NoSQL source log ---> CDC connector ---> Kafka topic ---> Consumer ---> Projection
        A                   B                C           D
~~~

Điều kiện khôi phục phụ thuộc nhiều mắt xích.

### 11.1. Source change history

Nguồn có thể dùng oplog, stream/shard, commit log, WAL hoặc retention buffer. Nếu CDC connector offline vượt khả năng giữ lịch sử, nó có thể phải snapshot lại hoặc khởi tạo một luồng mới.

### 11.2. Broker event history

Kafka topic/stream có retention hoặc compaction. Consumer offline lâu có thể không còn những records mà checkpoint cũ tham chiếu.

### 11.3. Consumer offset/checkpoint

Offset cho biết consumer đã xử lý tới đâu trong một partition; **nó không tạo thêm dữ liệu đã bị nguồn/broker xóa**. Nếu checkpoint bị mất, consumer có thể replay quá nhiều hoặc bỏ qua dữ liệu tùy reset policy.

### 11.4. Projection state

Một consumer có thể còn projection đã xử lý event X nhưng offset chưa commit. Khi replay phải deduplicate; nếu snapshot projection cũ hơn offset, có thể bị missing changes.

### 11.5. Backup/archive

Nếu cần khôi phục lâu hơn window online, có thể cần snapshots, durable event archive hoặc rebuild từ authoritative state. Không tự gọi một compacted cache/log là backup đầy đủ.

---

## 12. Tính retention window và khả năng catch-up

Giả sử:

- Source tạo \(\lambda\) events/giây.
- Consumer xử lý được \(\mu\) events/giây khi chạy.
- Consumer offline trong \(T_d\) giây.
- Kafka giữ lịch sử cần thiết trong \(T_r\) giây, dưới các điều kiện policy cụ thể.

Backlog đơn giản:

\[
B=\lambda T_d.
\]

Nếu \(\mu>\lambda\), tốc độ xả backlog ròng:

\[
\Delta=\mu-\lambda.
\]

Thời gian bắt kịp ước lượng:

\[
T_c=\frac{B}{\mu-\lambda}.
\]

### 12.1. Ví dụ

~~~text
Event arrival rate:     2.000 events/s
Consumer downtime:      3 giờ
Consumer rate sau hồi:  5.000 events/s
~~~

Backlog:

\[
B=2000\times(3\times3600)=21\,600\,000\text{ events}.
\]

Net catch-up:

\[
5000-2000=3000\text{ events/s}.
\]

Thời gian:

\[
T_c=\frac{21\,600\,000}{3000}
    =7200\text{ s}=2\text{ giờ}.
\]

Từ lúc bắt đầu downtime tới lúc bắt kịp khoảng **5 giờ** trong mô hình lý tưởng. Nếu cần dữ liệu earliest event vẫn còn khi consumer đọc, retention phải chừa **margin vượt khoảng này**, cộng thời gian failover, spikes, throttling và sai số vận hành.

### 12.2. Điều kiện quan trọng

Nếu \(\mu\le\lambda\), consumer không thể tự bắt kịp khi events tiếp tục đến cùng tốc độ. Tăng `retention.ms` chỉ trì hoãn thời điểm mất dữ liệu.

### 12.3. Với Kafka compaction, công thức chưa đủ

`delete.retention.ms` có mục tiêu riêng với delete markers. Ngay cả khi tổng event retention rộng, compaction có thể loại tombstones theo policy. Phải xét **thời gian hoàn tất replay/snapshot và tuổi marker**, không chỉ tuổi consumer downtime.

### 12.4. Với source TTL log

Nếu CDC connector mới bắt đầu đọc sau 26 giờ nhưng source chỉ giữ thay đổi 24 giờ, Kafka retention 7 ngày **không cứu được events chưa từng được publish vào Kafka**.

### 12.5. Đây không phải một công thức bảo đảm tổng quát

Giả định arrival/service rates ổn định, không đổi partitions, không có retry amplification hoặc message size variance. Capacity planning thực tế cần đo p95/p99 lag và failure drills.

---

## 13. Kiểm tra khả năng replay theo hai đường

### Đường A — Replay đầy đủ event log

Phù hợp khi event history còn đủ, consumer có idempotency, thứ tự per key và checkpoint hợp lệ.

~~~text
Existing projection at checkpoint X
   + read events from X+1
   -> update to latest state
~~~

### Đường B — Rebuild từ authoritative snapshot

Khi event history đã thiếu, cần tạo một **snapshot hợp lệ** của source rồi tiếp tục CDC từ một checkpoint nhất quán.

~~~text
Snapshot at source position S
     +
Replay changes after S
     ->
New complete projection
~~~

### 13.1. Chỉ copy dữ liệu “đang còn” chưa đủ cho projection cũ

Nếu projection cũ có bản ghi đã xóa nhưng snapshot source hiện tại **không còn bản ghi đó**, một incremental upsert-only backfill sẽ không xóa giá trị thừa.

Cần:

- Rebuild vào **projection mới trống**, hoặc
- So sánh keyset và xóa keys vắng ở source trong phạm vi xác định, hoặc
- Áp durable deletion ledger/tombstone history đầy đủ.

### 13.2. Cutover shadow projection

Một quy trình có thể:

~~~text
Create projection-v2 (empty).
Snapshot current source at S.
Apply CDC changes after S.
Validate counts and key differences.
Validate delete/TTL behavior.
Wait until desired watermark.
Switch reads to projection-v2.
Retire old projection safely.
~~~

### 13.3. Source snapshot phải nhất quán với CDC position

Nếu lấy snapshot ở thời điểm T nhưng khởi động CDC từ T+10s, writes và deletes trong khoảng đó có thể mất. Cần API/connector hỗ trợ consistency checkpoint hoặc protocol snapshot-and-tail đúng nghĩa.

### 13.4. Nếu source giữ lịch sử không đủ

Không khôi phục bằng cách đoán một offset “gần đây nhất”. Phải báo trạng thái không thể incremental replay, rồi rebootstrap/reconcile theo authoritative source.

---

## 14. Tombstone có thời hạn: nguy cơ “resurrection” sau replica hoặc client offline

Kịch bản:

~~~text
T0  Replica A và B chứa User K version 4.
T1  Replica B offline.
T2  A lưu tombstone DELETE K version 5.
T3  Tombstone bị dọn sau retention/GC.
T4  B trở lại với K version 4.
T5  Hệ đồng bộ nhầm state cũ như state còn sống.
~~~

**Hồi sinh dữ liệu (resurrection/zombie data)** xảy ra khi thông tin “K đã bị xóa” không còn đủ để bác bỏ một bản sao cũ.

### 14.1. Hai cơ chế khác nhau cùng có thể tạo nguy cơ

- Trong **Cassandra**, tombstone bị GC quá sớm so với thời gian replica stale có thể gây zombie data.
- Trong **consumer projection**, logical deletion marker bị purge trong khi event cũ có thể được replay có thể khiến old upsert tạo lại record.

### 14.2. Không phải cứ giữ tombstone vô hạn là giải pháp duy nhất

Có thể giảm rủi ro bằng:

- Resnapshot/reseed offline replica thay vì hòa trộn dữ liệu quá cũ.
- Version/generation authority không reset.
- Delete ledger lưu lâu hơn replay horizon.
- Reject old events sau watermark.
- Full rebuild từ authoritative source khi lịch sử đã hết.
- Giới hạn thời gian client/replica được phép offline mà vẫn incremental merge.

### 14.3. Thời gian giữ marker cần theo failure model

Ví dụ một thiết kế có:

~~~text
Maximum supported offline consumer: 7 ngày
Maximum catch-up/replay duration:    2 ngày
Operational safety margin:           2 ngày
~~~

Một policy có thể yêu cầu **khả năng giữ lịch sử delete tối thiểu vượt 11 ngày** nếu chỉ dựa vào replay markers để chống state cũ. Đây là **heuristic kiến trúc cho tình huống cụ thể**, không phải khuyến nghị cấu hình trực tiếp một tham số Kafka/Cassandra duy nhất.

### 14.4. Phải có điểm cắt an toàn

Khi consumer đã offline quá giới hạn hỗ trợ, hãy **ngừng replay incremental** và chạy quy trình rebootstrap có đối soát. Không coi “resume thành công” là bằng chứng không có lỗ hổng deletion.

---

## 15. Xóa theo TTL không đồng nghĩa delete ngay lập tức

TTL có thể đóng hai vai trò:

1. **Ngữ nghĩa hết hạn**: đối tượng không còn hợp lệ sau thời điểm.
2. **Cleanup vật lý**: storage tự dọn record sau thời điểm, có thể chậm.

### 15.1. DynamoDB TTL

DynamoDB TTL có thể xóa expired items một cách bất đồng bộ; không cam kết record bị xóa chính xác tại giây `expireAt`. Nếu business cần reservation hết hiệu lực ngay, logic phải kiểm tra `expiresAt` trong authoritative decision path, không chỉ đợi TTL service.

### 15.2. MongoDB TTL indexes

MongoDB TTL background process xóa documents khi đủ điều kiện; không thực hiện như timer chính xác ở từng millisecond. CDC có thể quan sát delete xảy ra khi TTL monitor thực sự xóa, **không nhất thiết đúng lúc logical expiry**.

### 15.3. Cassandra TTL

Cassandra TTL có thể dẫn tới expiry/tombstone semantics bên trong storage. Không cho rằng mỗi cell hết TTL sẽ tự phát một **business `EntityDeleted` event** theo cùng protocol CDC như explicit delete; cần kiểm tra dữ liệu model và CDC connector thực tế.

### 15.4. Redis expiry

Redis key expiry là thao tác của cache engine; keyspace notification về `expired` phụ thuộc cấu hình và thường không là durable event log. Nó không thay thế domain event của nghiệp vụ.

### 15.5. Tách logical expiry khỏi physical cleanup

~~~text
Reservation expires at 10:00.
At 10:00 business reads must reject reservation.
At 10:05 TTL maintenance physically removes record.
At 10:05 CDC REMOVE event may be emitted.
~~~

Nếu downstream chỉ nhìn CDC event ở 10:05, nó có thể hiển thị reservation còn hợp lệ thêm 5 phút. Dữ liệu thời gian nhạy cảm nên có **hợp đồng đọc dựa trên expiresAt** hoặc event expiry riêng.

---

## 16. MongoDB change streams: xóa và resume token

MongoDB change streams có thể theo dõi thay đổi trên collections/database/deployment theo phạm vi hỗ trợ, gồm operations như insert, update, replace, delete.

Một delete event khái quát:

~~~json
{
  "operationType": "delete",
  "documentKey": {
    "_id": "address-42"
  },
  "_id": {
    "_data": "opaque-resume-token"
  }
}
~~~

Đây là hình minh họa đã lược bỏ những trường có thể xuất hiện; resume token là **opaque**, không nên tự parse để suy thời gian/offset.

### 16.1. Document key

Consumer nên dùng `documentKey` theo contract để xóa projection tương ứng. Với sharded collections, key fields/metadata có thể khác tùy topology và version; không hardcode giả định mọi event chỉ có `_id` nếu query/key design thực tế khác.

### 16.2. Full document và pre-image

Một delete thường không có full document để “lookup sau khi xóa” vì record đã mất. Các tùy chọn pre/post images cần hỗ trợ/configuration và có giới hạn retention. Không buộc event bắt buộc có pre-image khi driver/server không hứa.

### 16.3. Resume token và oplog retention

Consumer/connector nên lưu resume token/checkpoint **sau khi xử lý thành công**. Nếu downtime đủ dài để history cần cho resume bị xóa khỏi oplog/change stream history, resume có thể không còn thực hiện được; cần resnapshot/rebuild.

### 16.4. Invalidate/drop

Drop/rename hoặc những sự kiện invalidate stream có handling/resume behavior riêng. Không mặc định `resumeAfter` hoạt động qua mọi invalidate; kiểm tra `startAfter` hoặc restart protocol của phiên bản MongoDB được dùng.

### 16.5. MongoDB Java change stream minh họa

~~~java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import org.bson.Document;

public final class MongoDeleteWatcher {

    public void consume(MongoCollection<Document> source) {
        ChangeStreamIterable<Document> stream =
            source.watch();

        try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                cursor = stream.cursor()) {

            while (cursor.hasNext()) {
                ChangeStreamDocument<Document> event =
                    cursor.next();

                if (event.getOperationType()
                        == OperationType.DELETE) {
                    Document key = event.getDocumentKey();

                    // TODO:
                    // 1. Map stable tenant/document key.
                    // 2. Apply idempotent projection delete.
                    // 3. Persist resume token/checkpoint.
                    // 4. Classify failures/retry/rebuild.
                    handleDelete(key);
                }
            }
        }
    }

    private void handleDelete(Document key) {
        // Ví dụ: triển khai cụ thể ở consumer.
    }
}
~~~

Đây là skeleton để nhận diện delete. Production cần có durable checkpoint, error handling, resume/snapshot strategy, cancellation và giới hạn quyền truy cập. Không coi vòng lặp trên là đủ cho CDC service production.

### 16.6. TTL delete vẫn là vấn đề ngữ nghĩa thời gian

Nếu delete đến từ TTL monitor, nó có thể là physical cleanup muộn hơn logical expiry; đừng dùng thời điểm event duy nhất để quyết định time-sensitive business state.

---

## 17. DynamoDB Streams: `REMOVE`, OldImage và TTL

Khi DynamoDB Streams được bật, stream records có thể chứa sự kiện thay đổi item như `INSERT`, `MODIFY`, `REMOVE`. Với delete, consumer thường dựa vào `eventName=REMOVE` và key information.

~~~json
{
  "eventName": "REMOVE",
  "dynamodb": {
    "Keys": {
      "PK": { "S": "TENANT#tenant-7" },
      "SK": { "S": "ADDRESS#address-42" }
    }
  }
}
~~~

Đây là JSON rút gọn. Records thực tế có thể chứa sequence numbers, approximate creation time, stream metadata, old/new images tùy cấu hình.

### 17.1. StreamViewType

DynamoDB Streams hỗ trợ các lựa chọn như:

- `KEYS_ONLY`.
- `NEW_IMAGE`.
- `OLD_IMAGE`.
- `NEW_AND_OLD_IMAGES`.

Delete consumers cần key; nếu muốn biết giá trị trước khi xóa, phải chọn cấu hình cung cấp old image phù hợp. Không tự suy `REMOVE` luôn có `OldImage`.

### 17.2. Retention của DynamoDB Streams

DynamoDB Streams giữ records trong **khoảng 24 giờ** theo service contract phổ biến. Cần xem tài liệu phiên bản/dịch vụ hiện hành khi triển khai, nhưng quan trọng là **không thiết kế replay vô hạn**.

Nếu consumer bị gián đoạn qua window này, cần cơ chế rebuild từ source/snapshot khác thay vì tiếp tục từ checkpoint không còn dữ liệu.

### 17.3. TTL removal

DynamoDB TTL service xóa expired items bất đồng bộ. TTL delete có thể tạo `REMOVE` record, và trong những ngữ cảnh nhất định có service identity metadata giúp phân biệt với user-initiated delete.

Nhưng **không suy** mọi global tables region hoặc mọi stream record đều mang giống nhau service identity; phải xét replication origin và mode của deployment.

### 17.4. Global tables

Khi một region phát TTL delete, những thay đổi replicate tới region khác có thể có metadata khác ở streams. Không thiết kế audit “mọi TTL delete đều có serviceUser” nếu cross-region replication có thể không giữ signal đó như bạn kỳ vọng.

### 17.5. Java AWS SDK v2 — phân loại event

~~~java
import software.amazon.awssdk.services.dynamodb.model.Record;
import software.amazon.awssdk.services.dynamodb.model.OperationType;

public final class DynamoDeleteHandler {

    public void onRecord(Record record) {
        if (record.eventName() == OperationType.REMOVE) {
            var keys = record.dynamodb().keys();

            // Dùng keys và stream metadata để xác định item.
            // Map sang projection delete/idempotent operation.
            // Chỉ checkpoint sau khi apply thành công.
            handleDelete(keys);
        }
    }

    private void handleDelete(
            java.util.Map<String,
                software.amazon.awssdk.services.dynamodb.model.AttributeValue>
                keys) {
        // Application-specific mapping.
    }
}
~~~

Tên packages và enum cần đối chiếu với SDK module `dynamodbstreams` đang dùng (không nhầm `dynamodb` và `dynamodbstreams`); đoạn là hình thức xử lý khái niệm, không phải mã đã chạy độc lập. Một implementation thực phải dùng đúng các models của `DynamoDbStreamsClient`/SDK phiên bản được chọn.

---

## 18. Cassandra: tombstone ở storage engine và zombie data

Cassandra dùng dữ liệu được nhân bản theo replication factor. Khi một row/cell bị xóa, một replica không thể chỉ “quên giá trị” vì các replicas khác có thể còn bản cũ.

### 18.1. Vì sao có tombstone?

~~~text
Replica A has K=value(version 4).
Replica B has K=value(version 4).

Client DELETE K via coordinator.
A receives tombstone K(version 5).
B offline, still has value(version 4).
~~~

Tombstone giúp A biết rằng K đã bị xóa, để read/repair/compaction không phục hồi dữ liệu cũ từ B.

### 18.2. Tombstone không phải event log vô hạn

Tombstones nằm trong data storage/LSM lifecycle, có thể được compact/garbage collected theo điều kiện. Chúng không phải CDC envelope có event IDs và ordering contract để downstream replay mọi thay đổi.

### 18.3. `gc_grace_seconds`

Cấu hình này liên quan thời gian một tombstone cần được giữ trước khi có thể được loại theo điều kiện compaction phù hợp. Nếu một replica offline lâu và tombstone ở các replicas khỏe bị GC trước khi stale replica đồng bộ, giá trị cũ có thể hồi sinh.

**Không chỉ tăng hoặc giảm `gc_grace_seconds` mà bỏ qua repair schedule, consistency levels và failure recovery model.**

### 18.4. Repair và offline replica horizon

Một mô hình vận hành cần bảo đảm các replica mang dữ liệu cũ được repair/reseed theo lịch đủ an toàn trước khi tombstones biến mất, hoặc xử lý node đã offline quá lâu bằng quy trình tái tạo đầy đủ.

### 18.5. Tombstone cost

Quá nhiều tombstones có thể tăng chi phí read/compaction và gây áp lực disk/memory. Giảm grace quá thấp để cải thiện latency mà không có repair discipline có thể làm tăng rủi ro zombie data.

### 18.6. TTL tạo nhiều tombstones

TTL trên dữ liệu có volume lớn có thể tạo storage tombstones. Cần cân nhắc data modeling theo time buckets, TWCS khi phù hợp và workload/compaction strategy; không coi TTL “miễn phí”.

### 18.7. CDC Cassandra khác Kafka tombstone

Cassandra CDC dựa trên commit-log/dữ liệu được hỗ trợ bởi hệ sinh thái connector. Những delete mutations muốn mang ra downstream phải được decode/mapping theo semantics; **không tự giả định** mọi storage tombstone sẽ trở thành một Kafka record `value=null`.

### 18.8. Bài test bắt buộc

Cho replica offline, thực hiện DELETE, chạy compaction/repair theo cấu hình staging, đưa replica quay lại; xác minh K không resurrect và đo tombstone/repair state. Không thử phá retention/replica trên production khi chưa phê duyệt.

---

## 19. Redis: `DEL`, expiry và keyspace notifications không phải CDC bền

Redis hỗ trợ xóa keys qua `DEL`, `UNLINK`, expiry và các thao tác khác theo protocol. Có thể cấu hình keyspace notifications để quan sát events.

### 19.1. Notification không là durable log

Keyspace notifications trong Redis truyền theo cơ chế Pub/Sub thường không đảm bảo consumer offline có thể replay events. Nếu consumer cần biết **mọi lần xóa**, phải có source/event log bền hơn hoặc cơ chế reconciliation.

### 19.2. Expiry không chính xác từng millisecond

Key quá TTL có thể được phát hiện khi truy cập hoặc background maintenance. Sự kiện expiry không phải timer business chính xác; không dùng để quyết định duy nhất rằng một reservation được release đúng thời điểm.

### 19.3. Key bị eviction khác explicit delete

Một key biến mất do memory eviction không nhất thiết có ý nghĩa “người dùng đã xóa dữ liệu nguồn”. Đừng gửi domain `UserDeleted` mỗi khi Redis cache entry bị eviction.

### 19.4. Redis Streams cũng cần phân biệt

Redis Stream lưu sự kiện nhưng durability vẫn phụ thuộc persistence/replication của Redis. `XDEL`/stream trimming khác Kafka compacted-topic tombstone và khác xóa domain entity.

### 19.5. Cache-aside invalidation

Nếu Redis chỉ là cache, workflow thường là DB source commit + invalidate cache. Khi event invalidation mất, TTL/version check có thể giới hạn stale risk. Nếu quyền truy cập cần ngay lập tức, đừng dựa vào Pub/Sub không bền như chứng cứ revoke.

---

## 20. Delete event phải nằm trong đúng partition/key ordering scope

Nếu entity K có:

~~~text
v12 UPSERT(K)
v13 UPDATE(K)
v14 DELETE(K)
```

Consumer nên có cách biết `v14` mới hơn `v12`, `v13`.

### 20.1. Delivery đảo thứ tự

Giả sử mạng/broker/retry khiến consumer nhận:

~~~text
DELETE v14
UPSERT v12
UPDATE v13
```

Nếu consumer áp lệnh theo **thứ tự đến**, nó có thể xóa rồi tạo lại entity cũ.

### 20.2. Version guard

Một projection có thể lưu:

~~~json
{
  "_id": "tenant-7|address-42",
  "lastAppliedVersion": 14,
  "deleted": true
}
~~~

Khi `UPDATE v13` đến, nó phải bị coi là stale. Không được update payload chỉ vì document đã bị đánh dấu deleted.

### 20.3. Version theo đúng entity

`sourceVersion` nên được cấp trong phạm vi mà ứng dụng có thể bảo đảm thứ tự. Kafka offset trong **một partition** có thể hữu ích cho stream ordering, nhưng không là global source version cho mọi partition hoặc mọi lần migrate topic.

### 20.4. Key reuse và generation

Nếu một business ID có thể được tái sử dụng sau delete, ví dụ SKU code `"ABC"` gắn với thực thể mới, version có thể reset nếu application không thiết kế. Cần thêm `generation` hoặc ID immutable mới để tránh delete cũ xóa nhầm incarnation mới.

### 20.5. Tombstone phải có identity không nhạy cảm

Dùng key ổn định đủ để xóa projection; tránh để email/phone/secret làm key nếu không cần. Key có thể sống lâu trong log và DLQ kể cả khi value null.

---

## 21. Java: mô hình consumer xử lý DELETE và UPSERT an toàn theo version

Ví dụ Java 17 sau là **một mô hình logic in-memory** cho unit test. Nó không thay transaction/CAS của NoSQL production, nhưng minh họa vì sao **logical tombstone** phải giữ version để chống replay cũ.

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class VersionedProjection {

    public enum Operation { UPSERT, DELETE }

    public record Change(
        String entityKey,
        long sourceVersion,
        String eventId,
        Operation operation,
        Map<String, String> body
    ) {
        public Change {
            Objects.requireNonNull(entityKey);
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(operation);
            body = body == null ? Map.of() : Map.copyOf(body);
            if (entityKey.isBlank() || eventId.isBlank()
                    || sourceVersion <= 0) {
                throw new IllegalArgumentException(
                    "Invalid change identity/version"
                );
            }
        }
    }

    public record State(
        long lastVersion,
        String lastEventId,
        boolean deleted,
        Map<String, String> body
    ) {
        public State {
            body = Map.copyOf(body);
        }
    }

    private final ConcurrentHashMap<String, State> states =
        new ConcurrentHashMap<>();

    public void apply(Change event) {
        states.compute(event.entityKey(), (key, previous) -> {
            if (previous != null) {
                if (event.sourceVersion()
                        < previous.lastVersion()) {
                    return previous; // Stale replay.
                }
                if (event.sourceVersion()
                        == previous.lastVersion()) {
                    if (!event.eventId().equals(
                            previous.lastEventId())) {
                        throw new IllegalStateException(
                            "Conflicting events at same version"
                        );
                    }
                    return previous; // Duplicate.
                }
            }

            if (event.operation() == Operation.DELETE) {
                // Giữ version dù ẩn/xóa payload.
                return new State(
                    event.sourceVersion(),
                    event.eventId(),
                    true,
                    Map.of()
                );
            }

            // Chỉ phù hợp khi UPSERT là full snapshot,
            // không phụ thuộc mọi delta bị bỏ lỡ.
            return new State(
                event.sourceVersion(),
                event.eventId(),
                false,
                event.body()
            );
        });
    }

    public Optional<Map<String, String>> read(String key) {
        State state = states.get(key);
        if (state == null || state.deleted()) {
            return Optional.empty();
        }
        return Optional.of(state.body());
    }

    public Optional<State> internalState(String key) {
        return Optional.ofNullable(states.get(key));
    }
}
~~~

### 21.1. Đường đọc ẩn tombstone

`read()` trả empty khi deleted, nhưng `internalState()` vẫn có `lastVersion=14` và `deleted=true`. Nếu bỏ hoàn toàn entry sau delete, `UPSERT v12` tới muộn có thể tạo lại dữ liệu.

### 21.2. Duplicate DELETE phải an toàn

Hai lần apply cùng event ID/version không gây thêm side effect trong mô hình. Nhưng nếu handler còn gọi external API hoặc tăng counter, các effects đó cũng cần idempotency riêng.

### 21.3. Gaps và deltas

Ví dụ cho phép `v12 -> v14` nếu UPSERT là **full snapshot**. Nếu events là **partial deltas**, consumer phải phát hiện gap và lấy lại những thay đổi thiếu; không được bỏ v13.

### 21.4. Cần xử lý create-after-delete theo domain

Một UPSERT `v15` sau DELETE `v14` được chấp nhận ở đây. Nếu entity đã xóa **không được tái tạo**, domain contract phải bác bỏ hoặc buộc `entityGeneration` mới.

### 21.5. In-memory không là phân tán

`ConcurrentHashMap.compute()` atomic **trong một process**. Hai consumer instances ghi cùng MongoDB/DynamoDB/Cassandra table cần điều kiện atomic ở **database**, không chỉ một map/JVM lock.

---

## 22. Java/JUnit 5: kiểm tra chống resurrection

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

public class VersionedProjectionTest {

    @Test
    void deleteWinsAgainstStaleUpsert() {
        var model = new VersionedProjection();

        model.apply(new VersionedProjection.Change(
            "tenant-7|address-42",
            14L,
            "event-delete-14",
            VersionedProjection.Operation.DELETE,
            Map.of()
        ));

        model.apply(new VersionedProjection.Change(
            "tenant-7|address-42",
            12L,
            "event-upsert-12",
            VersionedProjection.Operation.UPSERT,
            Map.of("city", "Hanoi")
        ));

        assertTrue(
            model.read("tenant-7|address-42").isEmpty()
        );
        assertEquals(
            14L,
            model.internalState("tenant-7|address-42")
                .orElseThrow()
                .lastVersion()
        );
    }

    @Test
    void duplicateDeleteIsIdempotent() {
        var model = new VersionedProjection();

        var delete = new VersionedProjection.Change(
            "K", 5L, "E5",
            VersionedProjection.Operation.DELETE,
            Map.of()
        );

        model.apply(delete);
        model.apply(delete);

        assertTrue(model.read("K").isEmpty());
        assertEquals(
            5L, model.internalState("K")
                .orElseThrow().lastVersion()
        );
    }

    @Test
    void newSnapshotMayFollowDeleteIfContractAllows() {
        var model = new VersionedProjection();

        model.apply(new VersionedProjection.Change(
            "K", 5L, "E5",
            VersionedProjection.Operation.DELETE,
            Map.of()
        ));

        model.apply(new VersionedProjection.Change(
            "K", 6L, "E6",
            VersionedProjection.Operation.UPSERT,
            Map.of("state", "ACTIVE")
        ));

        assertEquals(
            "ACTIVE",
            model.read("K").orElseThrow().get("state")
        );
    }

    @Test
    void twoDifferentEventsCannotShareOneVersion() {
        var model = new VersionedProjection();

        model.apply(new VersionedProjection.Change(
            "K", 8L, "E8",
            VersionedProjection.Operation.DELETE,
            Map.of()
        ));

        assertThrows(
            IllegalStateException.class,
            () -> model.apply(
                new VersionedProjection.Change(
                    "K", 8L, "OTHER",
                    VersionedProjection.Operation.UPSERT,
                    Map.of("state", "ACTIVE")
                )
            )
        );
    }
}
~~~

Các tests mô tả một contract cụ thể: version **tăng theo cùng logical entity**, event ID ổn định qua redelivery. Chúng không thay tests cho CDC source, broker retention, database concurrency hoặc physical purge.

---

## 23. Atomic delete trong read model NoSQL

Khi dùng MongoDB/DynamoDB/Cassandra, cần bảo vệ:

~~~text
if incomingVersion <= lastAppliedVersion:
    ignore
else:
    atomically set deleted=true and lastAppliedVersion=incomingVersion
```

### 23.1. Không dùng read-then-write tách rời

Sai:

~~~text
read currentVersion -> 12
if incomingVersion=14:
    write deleted=true

Meanwhile another worker:
    reads 12
    applies UPSERT v13 after the DELETE
~~~

Hai thao tác riêng có race, dù mỗi handler “có if-check”.

### 23.2. MongoDB example strategy

Một cách thiết kế là lưu một projection metadata record với `_id` cố định và `lastAppliedVersion`; dùng conditional update/CAS hoặc transaction/unique key để bảo vệ một phiên bản mới hơn không bị ghi đè.

Nếu dùng `upsert=true` với filter điều kiện version và record đã tồn tại nhưng version quá mới, cần xử lý **duplicate-key conflict** chính xác, không coi `upsert` đơn giản là lệnh update-anything. Cần test concurrent insertion và stale delivery.

### 23.3. DynamoDB example strategy

`UpdateItem` với `ConditionExpression` so `sourceVersion` có thể ngăn stale event ghi đè:

~~~javascript
const commandInput = {
  TableName: "AddressProjection",
  Key: {
    PK: "TENANT#tenant-7",
    SK: "ADDRESS#address-42"
  },
  UpdateExpression: [
    "SET deleted = :true",
    "sourceVersion = :v",
    "lastEventId = :e"
  ].join(", "),
  ConditionExpression:
    "attribute_not_exists(sourceVersion) OR sourceVersion < :v",
  ExpressionAttributeValues: {
    ":true": true,
    ":v": 14,
    ":e": "evt-delete-14"
  }
};
~~~

Đây là **pseudocode object** cho SDK mapper: SDK v2 dùng typed `AttributeValue` thay vì plain booleans/strings. Phải xử lý `ConditionalCheckFailed` như stale/duplicate hoặc conflict theo contract và kiểm tra cùng key scope.

### 23.4. Cassandra strategy

Có thể cần per-partition ordered consumer, LWT/CAS khi thích hợp hoặc single-writer projection protocol. Regular last-write-wins timestamps có những semantics khác `sourceVersion`; không tự coi `UPDATE ...` thông thường là CAS.

### 23.5. Physical delete và lưu metadata ở đâu?

Nếu projection phải xóa PII vật lý nhưng vẫn cần version guard, có thể tách **payload store** và **minimal deletion metadata/ledger**. Metadata phải không chứa PII không cần thiết và có retention phù hợp với legal/security policy.

---

## 24. Cần giữ tombstone bao lâu?

Không có một con số áp dụng cho mọi tầng. Cần phân biệt:

| Tầng | Tombstone/retention liên quan | Chọn theo |
|---|---|---|
| Cassandra storage | Tombstone GC grace/compaction | Replica outage + repair/reseed policy |
| Kafka compacted topic | Delete marker retention | Thời gian complete scan/rebuild và cleaner behavior |
| Kafka event-history topic | Event log retention | Consumer downtime + catch-up + replay needs |
| MongoDB change stream source | Oplog/history window | CDC connector downtime và snapshot strategy |
| DynamoDB Streams | Service stream retention | Max consumer lag, resnapshot requirement |
| Projection database | Logical deletion marker | Late events, restore, source version horizon |
| Cache | Invalidated key/TTL | Staleness contract, not durable evidence |
| Backup/archive | Retention/purge schedule | Recovery, compliance và source deletion policy |
| Offline mobile client | Local change history | Client rejoin window và conflict resolution |

### 24.1. Dùng “horizon” thay vì chỉ đếm ngày

Gọi:

- \(T_o\): thời gian offline tối đa hỗ trợ.
- \(T_c\): thời gian catch-up/replay tối đa.
- \(T_f\): margin cho failover/repair/maintenance.

Một kiến trúc **chỉ dựa vào retained delete history** có thể cần:

\[
T_{\text{delete evidence}}>T_o+T_c+T_f.
\]

Nhưng đây không phải cấu hình trực tiếp `gc_grace_seconds` hay `delete.retention.ms`; mỗi hệ có điều kiện cleanup và semantics riêng.

### 24.2. Nếu không thể giữ marker đủ lâu

Thiết kế **rebootstrap boundary**. Consumer offline quá ngưỡng phải xóa/rebuild projection từ authoritative snapshot hợp lệ, không được hồi phục tùy tiện từ state cũ.

### 24.3. Tombstone tồn tại quá lâu cũng có chi phí

Storage, compaction, search, metadata và backup đều tăng. Cần cân bằng **cost, correctness, replay window, privacy**. Tối ưu chi phí không được âm thầm phá deletion guarantees.

### 24.4. Lập hợp đồng bằng câu có thể kiểm chứng

Ví dụ:

> “Projection consumer offline quá 48 giờ không được tiếp tục incremental replay từ checkpoint cũ; phải rebuild từ snapshot đồng bộ với source position và kiểm keyset deletion trước cutover.”

Câu này hữu ích hơn “giữ tombstones thật lâu” nếu service retention chỉ hỗ trợ 24 giờ.

---

## 25. Đừng nhầm compaction với xóa vật lý trên mọi bản sao

Một log compacted có thể loại old records, nhưng không tự xóa:

- Document đã copy sang Search.
- Analytics aggregation đã tính.
- Cached version ở Java JVM.
- Backups chứa data.
- Files được export.
- Một replica offline.
- Dữ liệu ở external partner.

### 25.1. Materialized view cần logic delete riêng

Nếu Search có document ID K, Kafka tombstone cho K chỉ có ích khi consumer thực sự gọi delete/upsert-deleted theo API Search tương ứng.

### 25.2. Aggregates khó “xóa” hơn document projection

Nếu một event create đã cộng `dailyUserCount` rồi delete đến sau, consumer cần biết có nên decrement, giữ historical statistic, hay rebuild theo business semantics. Một update `DELETE K` không tự đảo mọi aggregate đã tính.

### 25.3. Append-only audit logs

Có trường hợp phải giữ audit evidence nhưng không được giữ PII. Cần chính sách minimal metadata/anonymization/pseudonymization, không mặc định “audit bất biến” cho phép lưu mãi toàn bộ raw deleted payload.

### 25.4. Không có universal exact-once delete

CDC thường liên quan retry/redelivery; consumer phải xử lý delete nhiều lần đúng. “Delete twice” có thể idempotent với một key, nhưng side effect như decrement count twice phải được dedup bằng event ID.

---

## 26. Xóa nhiều tài nguyên: transaction và saga

Một khách hàng xóa account, hệ cần xử lý:

~~~text
Customer document
Addresses
Saved payment references
Search profiles
Recommendations
Sessions
Caches
Analytics identifiers
Object storage attachments
~~~

### 26.1. Một transaction NoSQL có phạm vi hữu hạn

Không thể coi một lệnh xóa Customer ở MongoDB/DynamoDB tự tạo atomic delete trên Redis, Kafka, search và object storage.

### 26.2. Workflow trạng thái

Một mô hình:

~~~text
DELETE_REQUESTED
  -> AUTHORITY_UPDATED / NO_LONGER_ACCESSIBLE
  -> OUTBOX_DELETE_EVENT_COMMITTED
  -> DOWNSTREAM_PROJECTIONS_DELETED
  -> PHYSICAL_PURGE_QUEUED
  -> PURGE_VERIFIED
~~~

Tùy chính sách, có thể cần quarantine hoặc retry khi external store unreachable. Thứ tự/điều kiện phải được thiết kế theo yêu cầu bảo mật và thời gian xóa cho phép.

### 26.3. Outbox

Khi local DB transaction hỗ trợ:

~~~text
BEGIN TRANSACTION
  Mark Customer as deleted / apply deletion in source
  INSERT Outbox(
    eventId,
    entityKey,
    eventType=CustomerDeleted,
    sourceVersion
  )
COMMIT
~~~

Relay gửi event sau commit. Relay có thể publish lại nên consumer vẫn cần idempotency.

### 26.4. Transactional outbox không xóa toàn bộ ngay

Nó đảm bảo một thay đổi nguồn và **ý định phát event** cùng được commit trong boundary hỗ trợ, nhưng downstream vẫn là eventual workflow. Cần tracking state và SLA xử lý delete.

---

## 27. Soft delete, hard delete và privacy yêu cầu khác nhau

### 27.1. Soft delete có thể là trạng thái trung gian

Một `deleted=true` giúp không hiển thị record ngay, đồng thời giữ version để CDC và projections bắt kịp. Nhưng raw payload vẫn còn trong source; không gọi đó là physical erasure.

### 27.2. Hard delete từ source không tự xóa lịch sử

Dữ liệu có thể còn trong:

- CDC before images.
- Kafka event payloads.
- DLQ và retry logs.
- Source replicas.
- Backups/snapshots.
- Export files.
- Search/Analytics.
- Caches và offline devices.

### 27.3. Data minimization

Delete event nên mang ID opaque, tenant, version và operation thay vì toàn bộ địa chỉ/email/số điện thoại. Nếu cần audit lý do, dùng reason code không chứa PII.

### 27.4. Backup restoration có thể hồi sinh dữ liệu

Một snapshot tạo trước khi xóa có thể được restore sau nhiều tuần. Hệ phải có deletion ledger/watermark hoặc quy trình restore áp lại các delete requests trước khi đưa dữ liệu ra phục vụ.

### 27.5. Quy tắc retention pháp lý tùy bối cảnh

Các nghĩa vụ xóa, lưu trữ chứng từ, legal hold và backup có thể khác theo khu vực, loại dữ liệu và hợp đồng. Thiết kế cần có privacy/legal review; không tự đưa ra một TTL “đúng luật cho mọi nơi”.

### 27.6. Crypto-erasure có phạm vi

Xóa encryption key có thể làm một tập dữ liệu không đọc được nếu encryption design thỏa điều kiện, nhưng cần đánh giá keys được chia sẻ, plaintext copies, replicas, backups và metadata. Không tự xem nó thay toàn bộ deletion workflow.

---

## 28. Delete trong event-sourced system khác xóa ở current-state table

### 28.1. Event sourcing

Một event log có thể chứa:

~~~text
CustomerCreated
CustomerAddressUpdated
CustomerDeleted
```

Khi rebuild state, consumer phải áp `CustomerDeleted` theo đúng sequence. Nếu log retention đã cắt mất events, nó không còn đầy đủ để replay toàn bộ lịch sử.

### 28.2. Compacted state topic

Một topic `customer-state` có thể lưu latest value per key và tombstone cho delete. Nó hữu ích để bootstrap một materialized state, nhưng không nhất thiết chứa lý do, actor và mọi bước thay đổi của khách hàng.

### 28.3. Hai luồng có thể tồn tại song song

~~~text
customer-events (business event history)
customer-state  (compacted latest state)
~~~

Cần có producer/consumer contract để tránh một event delete bị hiểu là hai lệnh xóa nghiệp vụ hoặc hai lần gửi notification.

### 28.4. Rebuild từ snapshot cũ

Một snapshot đã tạo trước `CustomerDeleted` phải được **tail** qua delete event trước khi trở thành state mới. Nếu snapshot thiếu marker và event đã bị dọn, phải lấy authoritative current-state hoặc deletion ledger.

---

## 29. Event ordering khi delete và recreate cùng ID

Tình huống:

~~~text
v4: CREATE user-42
v5: DELETE user-42
v6: CREATE user-42 (business cho phép tái tạo)
```

Nếu consumer nhận v6 rồi v5 và chỉ xử lý arrival order, nó có thể xóa bản mới.

### 29.1. Generation

Một cách thiết kế:

~~~text
EntityKey = tenantId + stableId + generation
```

Nếu hệ cho phép cấp lại public identifier, generation tăng qua các vòng đời, hoặc internal immutable ID đổi mới.

### 29.2. Không tái sử dụng ID nếu không cần

Một immutable identity mới cho mỗi entity giúp giảm rủi ro delete cũ tác động sai incarnation. Public alias có thể có mapping riêng.

### 29.3. CDC physical delete không luôn mang thế hệ mới

Nếu source row bị hard-delete rồi insert lại cùng key, một CDC stream chỉ có key và timestamp có thể khó phân biệt hai vòng đời. Nên bổ sung authoritative version/generation ở domain layer khi cần.

### 29.4. Stale update sau delete

Ngay cả khi chưa recreate, một old UPDATE/UPSERT xuất hiện muộn có thể resurrect record nếu projection xóa marker version quá sớm.

---

## 30. Consistency và phạm vi ACK khi xóa

Một hệ có thể hứa:

- **Source delete committed:** authoritative database đã xác nhận theo write concern.
- **CDC emitted:** connector đã publish event.
- **Projection updated:** consumer đã áp vào một downstream store.
- **Global delete observed:** mọi read path được liệt kê đã phản ánh deletion.
- **Physical purge verified:** các bản sao/snapshot theo scope đã được xử lý.

Đây là các mốc khác nhau.

### 30.1. Không dùng source ACK thay CDC completion ACK

Nếu API trả `204 No Content` sau source commit, nó **không tự đảm bảo** search/cache đã xóa. API contract có thể chấp nhận eventual propagation, nhưng cần mô tả latency.

### 30.2. Nếu cần xóa quyền ngay

Đối với security revocation, có thể cần chặn truy cập từ authoritative policy ngay khi source commit, thay vì chờ cached projection/invalidation event. Chậm CDC không được cho phép user tiếp tục có quyền ngoài policy.

### 30.3. SLO delete propagation

Ví dụ:

~~~text
99% CustomerDeleted events reflected in Search
within 60 seconds after source commit,
under healthy CDC connectivity.
```

Đây là **SLO minh họa**; cần đo event time, connector lag, consumer apply time và tỷ lệ missing.

### 30.4. Delete verification là một workflow

Có thể dùng durable deletion request ID và per-destination acknowledgments để theo dõi việc xóa ở các systems quan trọng; không dùng Redis cache key làm bằng chứng duy nhất khi yêu cầu accountability.

---

## 31. Monitoring và cảnh báo

| Nhóm | Chỉ số | Câu hỏi |
|---|---|---|
| Source change log | Oplog/stream oldest position, age | Connector còn đủ history để resume? |
| CDC connector | Lag, retries, snapshot state | Có đưa delete từ source sang broker? |
| Kafka | Earliest/latest offsets, retention, compaction | Events/tombstones có còn đọc được? |
| Consumer | Lag theo partition/time, checkpoint age | Có nguy cơ quá replay horizon? |
| Delete operations | Count by entity/type/tenant | Có bất thường, thiếu event? |
| Tombstones | Count, age, cleaner/compaction lag | Có marker chưa xử lý hoặc retention quá ngắn? |
| Projection | Last applied version/watermark | Có ghi lùi hoặc replay sai? |
| Reconciliation | Source vs projection deleted key mismatch | Có resurrection hoặc orphan record? |
| Restore | Backup age, restore test success | Rebuild có an toàn? |
| Cassandra | Tombstone scans, GC/repair/compaction | Nguy cơ zombie data và read overhead? |
| DynamoDB | Stream consumer lag, expired iterator, TTL backlog | REMOVE có bị bỏ lỡ? |
| MongoDB | Resume failures, stream restart, oplog window | Need resnapshot? |
| DLQ | Oldest delete event, count, reason | Delete events có bị mắc lâu? |
| Privacy | Outstanding deletion requests, breach of deadline | Đã xóa đủ scope chưa? |
| Correctness | Reappeared deleted IDs | Dữ liệu xóa có hồi sinh? |

### 31.1. Không chỉ đo total consumer lag

Lag trung bình thấp có thể che một partition hot chứa nhiều deletes đang mắc kẹt. Đo theo partition/key cohort và **tuổi event chưa được xử lý**.

### 31.2. Không chỉ đo throughput

Consumer báo 100.000 events/s nhưng bỏ qua tất cả tombstones là sai. Cần metric riêng cho delete applied, duplicate skipped, stale rejected, unknown schema và DLQ.

### 31.3. Reconciliation theo keyset

Sample keys đã delete hoặc các deletion request IDs, kiểm các downstream projections không còn hiển thị (hoặc có tombstone hợp lệ) theo SLA. Đối soát phải tôn trọng bảo mật, không log dữ liệu nhạy cảm thô.

---

## 32. Ma trận fault-injection cho delete CDC

| ID | Tình huống | Oracle quan trọng |
|---|---|---|
| D01 | Single physical DELETE ở nguồn | CDC nhận đúng key, projection xóa |
| D02 | Soft delete `deleted=true` | Consumer nhận biết semantics, không tiếp tục hiển thị |
| D03 | Delete event duplicate | Apply idempotent, không double side effect |
| D04 | Delete đến trước old upsert | Không resurrect nhờ version guard |
| D05 | Delete đến sau new recreate | Không xóa incarnation mới |
| D06 | Consumer crash sau projection delete trước offset commit | Replay an toàn |
| D07 | Consumer checkpoint trước delete commit rồi crash | Phát hiện data loss, sửa protocol |
| D08 | Consumer offline trong retention | Catch-up/replay đủ |
| D09 | Consumer offline vượt retention | Rebootstrap, không pretend resume |
| D10 | Source log expired trước connector | Alert connector recovery/snapshot |
| D11 | Kafka compacted tombstone đủ lâu | Rebuild nhìn đúng deletion |
| D12 | Kafka tombstone GC trước replay xong | Phát hiện/không dùng stale projection |
| D13 | Debezium `op=d` + tombstone | Không tính hai delete business |
| D14 | Null payload bị JSON deserializer reject | Consumer phân loại đúng |
| D15 | Key serialization/partition thay đổi | Delete vẫn tìm đúng old key hoặc migration |
| D16 | DynamoDB TTL deletes muộn | Business expiry vẫn đúng |
| D17 | MongoDB pre-image unavailable | Delete vẫn xử lý được qua document key |
| D18 | Cassandra node offline qua GC horizon | Không zombie/resnapshot đúng |
| D19 | Redis invalidation Pub/Sub mất | Fallback/TTL/version semantics đúng |
| D20 | Backfill upsert-only vào old projection | Phát hiện stale keys vắng ở source |
| D21 | Rebuild snapshot + tail CDC | Không gap/duplicate effect |
| D22 | Restore backup trước deletion | Không phục hồi deleted PII trái policy |
| D23 | Cross-region failover | Delete event và state không bị ghi lùi |
| D24 | Consumer xử lý một delete 10 lần | Idempotency ledger/version vẫn đúng |
| D25 | DLQ lưu raw before-image | Data minimization/redaction đúng |
| D26 | Kafka topic `compact,delete` | Bootstrap/retention assumptions được kiểm |
| D27 | Full source snapshot có key reused | Generation/version conflict được xử lý |
| D28 | Aggregate analytics cộng rồi delete | Compensation/rebuild đúng domain |
| D29 | TTL + manual delete cạnh tranh | Không hai side effects |
| D30 | Mixed connector versions/SMT | Delete envelope và tombstone được decode đúng |
| D31 | Application restart mất checkpoint | Replay an toàn, có correct offset policy |
| D32 | Source DB partition/replication lag | Không claim global purge từ local ACK |

Các ca phá network, cưỡng bức TTL/tombstone GC, corruption và restore chỉ thực hiện trong **staging/disposable cluster được phê duyệt**.

---

## 33. Thiết kế test D09: consumer vượt log retention

### Setup

~~~text
Source key K exists in Analytics projection.
CDC events have finite retention.
Analytics consumer is stopped.
Source deletes K.
Downtime deliberately exceeds retention window in staging.
```

### Steps

1. Ghi snapshot/source position và consumer checkpoint ban đầu.
2. Stop consumer theo cách an toàn ở test environment.
3. Delete K ở authoritative source.
4. Xác minh CDC phát delete theo contract.
5. Chờ tới khi history chứa delete không còn replay được.
6. Restart consumer từ checkpoint cũ.
7. Quan sát missing offsets/resume errors hoặc gap detector.
8. Kích hoạt rebootstrap/repair.
9. So K trong source và projection.
10. Đưa consumer trở về serving chỉ khi data hợp lệ.

### Oracle

- Consumer **không được âm thầm bỏ qua gap**.
- Nếu replay không đủ, nó phải khởi động rebuild thay vì giữ stale state.
- K không xuất hiện lại sau rebuilt projection cutover.
- Có alert và diagnostics về retention violation.

### Anti-pattern

~~~text
offset out of range -> reset to latest -> continue
```

Việc tự động nhảy tới latest có thể làm mất mọi delete/update trong khoảng bỏ lỡ. Chỉ dùng reset policy phù hợp khi domain cho phép mất lịch sử hoặc đã rebootstrap hoàn chỉnh.

---

## 34. Thiết kế test D11/D12: tombstone compaction

### Setup

~~~text
Compacted topic:
  K -> value v1
  K -> value v2
  K -> null (tombstone)

Consumer rebuilds a state store from offset 0.
```

### Kiểm thử

1. Publish sequence trên vào staging topic.
2. Kiểm config cleanup policy và tombstone retention.
3. Khởi tạo một consumer state store trống.
4. Rebuild chậm và theo dõi thời gian hoàn thành.
5. Quan sát khi cleaner loại records/tombstones theo điều kiện.
6. Kiểm state cuối không chứa K.
7. Lặp với consumer bắt đầu từ một **stale external state store**.
8. Thiết kế cơ chế clear/rebuild nếu marker đã biến mất.

### Oracle

Một consumer **tạo state mới từ log đã compact nhất quán** có thể không thấy K nào và kết quả vẫn đúng. Một consumer mang theo state cũ cần đủ delete evidence hoặc phải reset state. Không đánh đồng hai bài toán.

### Lưu ý

Không dựa vào một `sleep(n)` để ép Kafka log cleaner chạy chính xác tại thời điểm mong muốn. Test cần quan sát earliest offsets/records và cleaner behavior thực tế.

---

## 35. Thiết kế test D18: Cassandra tombstone và replica stale

### Setup

~~~text
RF=3.
K có giá trị tại A/B/C.
C offline.
A/B nhận DELETE K.
```

### Steps

1. Trong staging, xác định repair/tombstone GC settings hiện hành.
2. Ghi dữ liệu và thực hiện DELETE theo consistency requirements.
3. Cho C offline trong phạm vi scenario.
4. Quan sát tombstone tại các replicas còn sống.
5. Mô phỏng offline lâu/compaction theo test policy.
6. Đưa C trở lại hoặc re-seed theo runbook.
7. Dùng reads/repair để kiểm K.
8. Xác nhận không có zombie data và compaction/repair healthy.

### Oracle

- Nếu node đã offline quá horizon, hệ phải **reseed/rebuild đúng** hoặc bảo vệ chống đưa state cũ vào cluster.
- Không xuất hiện record K sau khi deletion đã được xác nhận theo contract.
- Có bằng chứng repair không bỏ sót replica/range.

### Không nên làm

Giảm `gc_grace_seconds` xuống quá ngắn trên production chỉ để thấy nhanh tombstone biến mất trong test; việc đó có thể tạo rủi ro zombie data thật.

---

## 36. Thiết kế test D22: khôi phục bản sao cũ chứa dữ liệu đã xóa

### Setup

~~~text
T0: Backup chứa Profile P.
T1: User xóa Profile P.
T2: CDC/consumers xóa P khỏi Search/Analytics.
T3: Restore backup T0 sang môi trường phục hồi.
```

### Oracle

- Trước khi phục vụ traffic, reapply deletion ledger/source changes kể từ T0 theo policy.
- P không bị phục hồi như một active profile.
- Dữ liệu phải xóa/ẩn trong downstream indexes theo yêu cầu.
- Audit không cần chứa raw PII để chứng minh việc xử lý.
- Restore procedure được kiểm chứng bằng deletion requests trên nhiều tenants.

### Bài học

**Restore thành công về kỹ thuật có thể là thất bại về tính đúng đắn** nếu restored snapshot hồi sinh dữ liệu đã xóa.

---

## 37. Runbook khi delete event không tới consumer

### Bước 1 — Xác định phạm vi

- Entity/key/tenant nào?
- Source hard delete hay soft delete?
- Có outbox/domain event hay raw CDC?
- Consumer nào không xóa: Search, Analytics, Cache, Audit?
- Dữ liệu có thuộc lớp privacy/security critical không?

### Bước 2 — Xác minh source commit

Kiểm authoritative source/version/write concern. Không suy từ một read stale hoặc GSI rằng delete chưa commit.

### Bước 3 — Kiểm connector

- Connector sống không?
- Source offset/resume token còn hợp lệ?
- Oplog/stream history window đủ không?
- Connector bị lỗi schema/pre-image/authorization?
- Delete có bị filter bởi SMT không?

### Bước 4 — Kiểm broker/stream

- Topic/partition/key đúng?
- `op=d`, tombstone null hay cả hai?
- Retention/compaction có xóa history cần thiết?
- Earliest offset so với checkpoint?
- Producer publish lỗi hoặc connector DLQ?

### Bước 5 — Kiểm consumer

- Consumer đang pause/offline?
- Null tombstone có bị parser reject?
- Delete event vào DLQ?
- Có ACK/checkpoint trước projection commit?
- Có version guard chống stale overwrite?
- Có schema/key migration làm delete sai key?

### Bước 6 — Bảo vệ dữ liệu đang bị lộ

Nếu dữ liệu đáng lẽ phải ẩn/xóa theo policy, cân nhắc chặn đường đọc, thu hồi quyền hoặc temporary quarantine trong phạm vi được phép, thay vì chỉ chờ consumer bắt kịp.

### Bước 7 — Chọn recovery

- **Replay** nếu history còn đầy đủ.
- **Rebuild projection** nếu history đã mất.
- **Reconcile theo deletion ledger** nếu cần vá keyset.
- **Manual case handling** nếu có external side effects/privacy obligations.

### Bước 8 — Xác nhận end-to-end

Đọc source và các projection theo những consistency/read paths được công bố; kiểm tombstone/version và khả năng old events resurrect.

### Bước 9 — Phòng tái diễn

Điều chỉnh retention/capacity, checkpoint protocol, rebootstrap gate, schema tests, consumer lag alerts và backup restore drills. Không tăng retention một cách mù quáng mà bỏ qua consumer throughput.

---

## 38. Checklist hợp đồng DELETE CDC

- [ ] Delete event có stable entity key và tenant scope.
- [ ] Event ID ổn định qua retry.
- [ ] Có operation type rõ ràng (`DELETE`, `op=d`, v.v.).
- [ ] Consumer phân biệt envelope delete và Kafka null tombstone.
- [ ] Source commit semantics được mô tả.
- [ ] Before-image chỉ dùng khi cần và được hỗ trợ.
- [ ] Delete event không chứa PII thừa.
- [ ] Per-key ordering/version/generation có policy.
- [ ] Old UPSERT đến muộn không resurrect record.
- [ ] Duplicate delete không tạo side effect trùng.
- [ ] Source log retention và broker retention đều được đo.
- [ ] Kafka tombstone retention được kiểm trong compaction/rebuild plan.
- [ ] Consumer checkpoint chỉ tiến sau apply theo protocol.
- [ ] Có phát hiện out-of-range offset/resume token invalid.
- [ ] Có đường rebootstrap khi thiếu event history.
- [ ] Snapshot + tail CDC có checkpoint nhất quán.
- [ ] Upsert-only backfill không giữ stale deleted keys trong old projection.
- [ ] TTL physical cleanup không bị nhầm với business expiry time.
- [ ] Cassandra tombstone GC đi cùng repair/reseed policy.
- [ ] DynamoDB Stream/TTL/OldImage configuration phù hợp.
- [ ] MongoDB pre-image/resume token và oplog window được đánh giá.
- [ ] Redis keyspace notifications không được dùng như durable CDC.
- [ ] Search/Analytics/Cache delete propagation có SLO riêng.
- [ ] Restore backups không hồi sinh dữ liệu đã xóa.
- [ ] Có privacy/security review và audit không lộ raw payload.
- [ ] Có metrics cho delete lag, DLQ, tombstone, reconciliation.
- [ ] Incident runbook phân biệt replay được và phải rebuild.
- [ ] Test gồm offline consumer, late update, failover, TTL, compaction và restore.

---

## 39. Bài tập 1 — Phân biệt các tombstone

Cho năm trường hợp:

~~~text
A. Cassandra DELETE row K.
B. Debezium emits op=d with JSON envelope.
C. Kafka record with key K and value=null.
D. MongoDB document has deleted=true.
E. DynamoDB Streams emits REMOVE.
```

Hãy lập bảng:

1. Đó là storage marker, business state hay stream event?
2. Ai tạo nó?
3. Nó tồn tại bao lâu?
4. Có đủ thông tin cho consumer xóa một read model không?
5. Có tự loại bỏ PII khỏi backup không?
6. Khi consumer offline một tuần, cần kiểm tra điều gì?

**Gợi ý:** A, B, C không đồng nhất; D là soft delete, E là change stream record theo cấu hình.

---

## 40. Bài tập 2 — Tính backlog và retention

Một CDC topic nhận 3.000 records/s. Consumer offline 4 giờ. Khi phục hồi, consumer xử lý ổn định 7.000 records/s trong khi source tiếp tục phát 3.000/s.

1. Tính backlog sau downtime.
2. Tính tốc độ xả backlog ròng.
3. Tính thời gian bắt kịp lý tưởng.
4. Tính tổng thời gian từ lúc downtime bắt đầu đến lúc catch-up.
5. Nếu history retention chỉ 5 giờ, rủi ro gì?
6. Nếu topic compacted với tombstones, chỉ tăng `retention.ms` có đủ không?
7. Nếu source DynamoDB Streams chỉ giữ một cửa sổ ngắn hơn, ai phải khởi động rebootstrap?
8. Đề xuất cảnh báo dựa trên age của earliest unprocessed event.

Gợi ý:

\[
B=3000\times4\times3600
=43\,200\,000.
\]

\[
T_c=\frac{43\,200\,000}{7000-3000}
=10\,800\text{ s}=3\text{ giờ}.
\]

Tổng lý tưởng là 7 giờ, chưa tính failover và hiệu năng biến động.

---

## 41. Bài tập 3 — Delete, late update và recreate

Dòng sự kiện:

~~~text
v10 UPSERT(K, name="An")
v11 UPDATE(K, name="Bình")
v12 DELETE(K)
v13 CREATE(K, name="Chi") — nếu domain cho phép
```

Consumer nhận theo thứ tự:

~~~text
v12, v10, v13, v11
```

1. Sau mỗi event, logical state và `lastVersion` phải là gì?
2. Nếu domain không cho recreate, xử lý v13 thế nào?
3. Nếu ID được tái sử dụng với generation mới, model thay đổi ra sao?
4. Nếu consumer xóa physical row khi nhận v12 và không còn lastVersion, nguy cơ gì?
5. Viết test JUnit cho stale replay.
6. Nếu event v11 là delta, xử lý gap thế nào?

---

## 42. Bài tập 4 — Debezium và Kafka compacted topic

Một connector phát:

~~~text
key K, value {"op":"d","before":{...},"after":null}
key K, value null
```

1. Hai records có cùng ý nghĩa với một nghiệp vụ DELETE không?
2. Consumer làm gì với `value=null`?
3. `delete.retention.ms` bảo vệ trường hợp nào?
4. Nếu tombstone bị compact nhưng consumer rebuild từ **state store trống**, nó cần xử lý ra sao?
5. Nếu consumer có state store cũ chứa K thì sao?
6. Nếu key schema/serialization thay đổi sau migration, cách xóa key cũ?
7. Nếu `cleanup.policy=compact,delete`, những rủi ro bổ sung là gì?

---

## 43. Bài tập 5 — TTL và tính đúng thời điểm

Một reservation có:

~~~text
expiresAt = 10:00:00
DynamoDB TTL service deletes item at 10:07:00
CDC REMOVE reaches consumer at 10:07:05
```

1. Reservation có được xem còn hợp lệ lúc 10:03 không?
2. Có nên đợi `REMOVE` mới release quota?
3. Nếu quota cần atomic, giải pháp nào?
4. Nếu downstream chỉ dùng TTL delete time, sai lệch là bao nhiêu?
5. Nếu region B nhận replicated TTL delete nhưng không có service identity metadata, consumer phải làm gì?
6. Hãy thiết kế event `ReservationExpired` riêng với request/version.
7. Kiểm toán/retention cần dữ liệu nào mà không giữ PII quá mức?

---

## 44. Bài tập 6 — Cassandra zombie data

Cụm Cassandra RF=3. Một replica ngừng hoạt động lâu; ở các replicas còn lại xảy ra delete và compaction.

1. Vì sao Cassandra cần tombstone?
2. Vì sao xóa tombstone quá sớm nguy hiểm?
3. `gc_grace_seconds` liên quan gì đến repair?
4. Khi node offline quá lâu, nên re-seed hay chỉ cho join ngay?
5. Chỉ tăng read consistency level có đủ chữa mọi trường hợp không?
6. Kế hoạch test trong staging gồm những bước nào?
7. Tombstone nhiều tác động thế nào đến read performance?
8. Lý do không dùng Cassandra tombstone retention như Kafka event history?

---

## 45. Bài tập 7 — Rebuild Search index sau khi mất log

Một Search index được dựng từ MongoDB changes. Consumer tắt 5 ngày; oplog không còn resume token. Search vẫn giữ các document đã xóa trong thời gian đó.

Thiết kế quy trình:

1. Xác nhận stream history không thể resume.
2. Bắt đầu snapshot nhất quán với một source position.
3. Dựng index **mới trống** thay vì upsert vào index cũ.
4. Tail change events sau snapshot checkpoint.
5. Áp các delete theo version.
6. So key counts và sample deleted IDs.
7. Kiểm privacy-sensitive keys trước serving.
8. Chuyển alias/read path sang index mới có kiểm soát.
9. Có rollback/cleanup kế hoạch.
10. Theo dõi retention/catch-up để tránh lặp sự cố.

---

## 46. Bài tập 8 — Thiết kế data deletion protocol end-to-end

Một ứng dụng có:

~~~text
Source: MongoDB
CDC: change streams -> Debezium-like pipeline
Broker: Kafka
Consumers: Search, Analytics, Email preference view
Cache: Redis
Backups: nightly snapshots
Clients: có thể offline 7 ngày
```

Hãy viết một **Delete Contract** gồm:

- Entity IDs, event IDs, source version và generation.
- Commit/ACK semantics ở source.
- CDC event type và Kafka tombstone policy.
- Source log + Kafka log retention.
- Consumer checkpoint/replay/rebootstrap.
- Handling late upserts/recreates.
- TTL và logical expiry.
- Read models + cache invalidation.
- Backup restore + deletion ledger.
- Privacy/minimization.
- SLO propagation và verification.
- Incident runbook.
- Test matrix với ít nhất 12 trường hợp lỗi.

Giải thích vì sao **xóa từ source** chỉ là một mốc trong chuỗi xử lý này.

---

## 47. Những ngộ nhận thường gặp

| Ngộ nhận | Điều đúng hơn |
|---|---|
| “DB đã delete thì Search tự mất.” | Search cần nhận và xử lý delete hoặc rebuild |
| “Soft delete giống hard delete.” | Soft delete còn record/payload |
| “Kafka tombstone là JSON `{deleted:true}`.” | Tombstone keyed record có value null |
| “Debezium `op=d` chính là Kafka tombstone.” | Delete envelope và tombstone có thể là hai records |
| “`after:null` luôn nghĩa delete.” | Cần operation/schema context |
| “Log compaction giữ mọi sự kiện.” | Giữ latest state theo key, lịch sử có thể mất |
| “Tombstone ở compacted topic không bao giờ mất.” | Marker có retention/compaction lifecycle |
| “`retention.ms` là đủ cho tombstone.” | Cần xem `delete.retention.ms`/cleanup policy |
| “Offset còn trong DB nghĩa Kafka vẫn giữ event.” | Log có thể đã cleanup records |
| “Kafka giữ 7 ngày, source CDC có thể offline 7 ngày.” | Source oplog/stream retention riêng |
| “CDC xóa có full before image.” | Phụ thuộc source và config |
| “TTL đến hạn thì DELETE event xuất hiện ngay.” | Background physical cleanup thường trễ |
| “Một `REMOVE` DynamoDB luôn do user.” | TTL service cũng có thể xóa |
| “Cassandra tombstone là Kafka null record.” | Hai cơ chế khác nhau |
| “Giảm `gc_grace_seconds` luôn cải thiện Cassandra.” | Có thể gây zombie data |
| “Redis expired notification là durable CDC.” | Pub/Sub notifications không đảm bảo replay |
| “Consumer replay luôn đủ chỉ cần tăng threads.” | Có thể hết retention hoặc không bắt kịp |
| “Restart rồi reset offset latest là ổn.” | Có thể bỏ qua delete |
| “Rebuild bằng upsert-only là đủ.” | Stale keys không còn ở source vẫn ở projection cũ |
| “Delete rồi update đến trễ được phép tạo lại.” | Cần version/generation guard |
| “Xóa payload nghĩa không cần giữ metadata.” | Có thể cần tombstone/ledger chống resurrection |
| “ACK ở source nghĩa mọi read models đã xóa.” | CDC propagation là bất đồng bộ |
| “Restore backup cũ không ảnh hưởng delete.” | Có thể hồi sinh deleted PII |
| “Một `DELETE` consumer chạy hai lần chắc chắn không sao.” | Side effects/aggregates có thể bị nhân đôi |
| “Logs và DLQ không chứa dữ liệu đã xóa.” | Before-images/keys có thể giữ PII |
| “Tăng retention là giải pháp duy nhất.” | Có thể rebootstrap/reconcile từ source |
| “Tombstone quá lâu miễn phí.” | Storage/compaction/performance costs |
| “Read model nhất quán là business audit đầy đủ.” | Deletion history/ack scope cần riêng |

---

## 48. Tổng kết

Đường xóa dữ liệu trong kiến trúc NoSQL + CDC không kết thúc tại lệnh `DELETE`. Nó đi qua **source commit, change log, connector, broker, consumer checkpoint, projection, cache, backups và quy trình khôi phục**.

Những nguyên tắc chính:

1. **Phân biệt loại xóa và tombstone.** Business delete, DB storage tombstone, CDC `op=d` và Kafka value-null tombstone không phải một thứ.
2. **Delete event cần đủ identity và ordering.** Stable key, event ID, source version/generation giúp consumer xóa đúng và chống late replay.
3. **Log retention là một ranh giới tính đúng đắn.** Khi source/broker đã mất lịch sử, consumer không thể chỉ resume tùy tiện và giả định đã xử lý hết deletes.
4. **Kafka compaction không lưu toàn bộ lịch sử.** Tombstones cũng có vòng đời; snapshot/rebuild phải được thiết kế theo marker retention và trạng thái projection ban đầu.
5. **Cassandra tombstone phải được quản lý với repair/GC.** GC trước khi stale replica được xử lý có thể làm dữ liệu cũ hồi sinh.
6. **TTL physical cleanup thường không đúng một thời điểm tuyệt đối.** Business expiry cần được kiểm theo nguồn có thẩm quyền.
7. **Consumer phải idempotent và version-aware.** Delete sau đó old UPSERT đến muộn không được tạo lại record.
8. **Backup restore và read-model rebuild là nguồn resurrection thực tế.** Phải reconcile các yêu cầu xóa trước khi đưa restored data ra phục vụ.
9. **Privacy và security deletion cần verification end-to-end.** Raw PII có thể còn trong before-image, logs, DLQ và exports, dù source đã xóa.
10. **Khi quá retention horizon, hãy rebootstrap có đối soát**, không tự reset offsets sang latest và bỏ qua những thay đổi đã mất.

**Câu cần nhớ: “Một bản ghi chỉ thực sự được xem là đã xóa theo hợp đồng hệ thống khi mọi nơi được yêu cầu phản ánh việc xóa đều có đủ bằng chứng, và không bản sao cũ, event đến muộn hay bản restore nào có thể đưa dữ liệu đó trở lại trái quy tắc.”**

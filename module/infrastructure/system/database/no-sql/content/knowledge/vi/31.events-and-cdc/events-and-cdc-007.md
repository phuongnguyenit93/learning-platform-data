# Checkpoint, offset và thời điểm xác nhận xử lý thành công trong sự kiện và CDC

## 1. Tình huống mở đầu: đã đọc sự kiện có nghĩa đã xử lý xong chưa?

Một dịch vụ NoSQL lưu đơn hàng trong MongoDB. Mọi thay đổi được đưa qua CDC (*Change Data Capture*) rồi chuyển thành sự kiện trên một topic. Một Java worker nhận sự kiện và cập nhật chỉ mục tìm kiếm:

```text
 MongoDB source              CDC connector               Message broker             Search worker
      |                           |                             |                        |
      | order O1 -> PAID          |                             |                        |
      |-------------------------->|                             |                        |
      |                           | publish OrderPaid           |                        |
      |                           |---------------------------->|                        |
      |                           |                        offset 104                   |
      |                           |                             |---- deliver 104 ------>|
      |                           |                             |                        | update search
      |                           |                             |                        |  ...?
```

Giả sử worker **đánh dấu offset 105 là đã tiêu thụ** ngay khi nhận message 104, rồi tiến trình crash trước khi cập nhật search. Khi restart, broker bắt đầu từ offset 105. Sự kiện 104 có thể **không được chạy lại**, dù chỉ mục vẫn giữ trạng thái cũ. Người dùng thấy đơn đã PAID trong source nhưng search hiển thị PENDING.

Trường hợp ngược lại:

1. Worker nhận message tại offset 104.
2. Cập nhật search thành công.
3. Crash **trước khi** commit checkpoint 105.
4. Restart từ offset 104 và xử lý cùng sự kiện lần nữa.

Lần thứ hai không phải lỗi broker: hệ không có bằng chứng bền rằng worker đã xử lý xong. Nếu handler chỉ gán trạng thái PAID, chạy lại có thể tương đối an toàn; nếu handler phát email, tăng counter hoặc tính phí bằng một API ngoài, **tác dụng nghiệp vụ có thể xảy ra hai lần**.

Vậy thời điểm “xác nhận xử lý thành công” là thời điểm nào?

- Database nguồn đã commit?
- CDC connector đã đọc bản ghi?
- Broker đã ghi event vào log?
- Consumer đã nhận event?
- Worker đã bắt đầu xử lý?
- Ghi vào sink đã commit?
- Kết quả đã trở nên nhìn thấy trong read model?
- Đã ghi checkpoint để không cần replay?

**Mỗi dấu mốc là một cam kết khác nhau.** Thiết kế CDC đáng tin phải định nghĩa rõ *checkpoint của ai, offset thuộc log nào, và ACK đại diện cho hành động nào đã bền*.

## 2. Mục tiêu học tập

Sau bài học, bạn cần:

1. Phân biệt **source position, broker offset, consumer position, committed offset, checkpoint, resume token và watermark**.
2. Hiểu offset là vị trí **theo partition/shard/log**, không phải “số thứ tự toàn hệ” mặc định.
3. Xác định đúng **thời điểm commit checkpoint** so với việc áp dụng side effect vào NoSQL sink.
4. Phân tích cửa sổ crash giữa **effect commit** và **checkpoint commit**, từ đó phân biệt at-most-once, at-least-once và exactly-once trong phạm vi cụ thể.
5. Thiết kế **idempotent consumer, inbox ledger, conditional update, source revision guard**, transaction hoặc outbox.
6. Hiểu giới hạn của **Kafka transactions**, cross-system atomicity và cụm từ “exactly once”.
7. Xử lý batching, xử lý song song, thứ tự partition, group rebalance, fencing và handoff.
8. Hiểu checkpoint cho MongoDB Change Streams, PostgreSQL WAL CDC, DynamoDB Streams, Kafka Connect và các loại feed khác ở mức khái niệm.
9. Lập kế hoạch snapshot + streaming, retention, backpressure, poison messages, DLQ, replay và phục hồi sau sự cố.
10. Thực hành bằng Java, mô hình state machine, bảng lịch sử lỗi và các bài kiểm thử fault injection.

## 3. Một pipeline sự kiện có nhiều điểm ACK khác nhau

```text
     ┌─────────────────┐
     │ Source database │
     │ COMMIT order v8 │
     └────────┬────────┘
              │ change log/CDC
              ▼
     ┌─────────────────┐
     │ Source reader   │── source position S
     │ read/transform  │
     └────────┬────────┘
              │ publish event
              ▼
     ┌─────────────────┐
     │ Durable broker  │── broker partition offset P
     │ append accepted │
     └────────┬────────┘
              │ consume
              ▼
     ┌─────────────────┐
     │ Java consumer   │── in-memory position
     │ dispatch work   │
     └────────┬────────┘
              │ apply
              ▼
     ┌─────────────────┐
     │ NoSQL sink      │── business effect committed?
     │ / Search index  │
     └────────┬────────┘
              │ checkpoint
              ▼
     ┌─────────────────┐
     │ Offset store    │── durable consumer checkpoint C
     └─────────────────┘
```

Điểm nào cũng có thể xảy ra timeout, crash, network partition hoặc failover. Một ACK ở phía trên không tự trở thành ACK ở phía dưới:

| Tầng | “Thành công” thường có nghĩa gì? | Chưa chứng minh được điều gì? |
|---|---|---|
| Source DB | Write commit theo consistency/durability contract của source | Broker đã có event |
| CDC reader | Đọc được record từ change log | Event đã ghi bền vào broker |
| Broker producer | Broker nhận bản ghi theo producer ACK/config | Consumer đã áp dụng vào sink |
| Consumer poll/read | Event được giao vào process/buffer | Handler đã chạy hoặc ghi bền |
| Sink write | Sink ACK theo write concern/transaction semantics | Offset đã commit; các side effect khác đã thành công |
| Consumer offset commit | Checkpoint tiến lên trong offset store | Chính handler đã đúng nghiệp vụ |
| UI/API read | Read model trả được state | Các replica khác hội tụ hoặc side effect ngoài đã xong |

**Quy tắc:** chỉ ACK một mốc khi bạn có bằng chứng bền phù hợp cho điều mà mốc đó hứa, đồng thời biết phần việc nào còn phải retry.

## 4. Định nghĩa offset, position và checkpoint

### 4.1. Offset

Offset là vị trí hoặc định danh tiến độ trong **một log/shard/partition**. Chẳng hạn Kafka:

```text
Topic: order-events
Partition 0:
    offset 102: OrderCreated(O1)
    offset 103: OrderUpdated(O2)
    offset 104: OrderPaid(O1)
    offset 105: OrderCanceled(O3)
```

Offset **104** chỉ có nghĩa trong partition 0 của topic đó; không thể so trực tiếp với offset 104 của partition 1 để nói event nào xảy ra trước toàn hệ.

### 4.2. Consumer position

Vị trí mà **consumer hiện tại** sẽ lấy record tiếp theo hoặc đã fetch tới. Nó có thể tiến trước tiến độ xử lý thật:

```text
poll() returned offsets 100..199
consumer current fetch position: 200
business processing finished only through: 106
```

### 4.3. Committed offset

Checkpoint bền được consumer group/offset store ghi nhận. Trong Kafka, một committed offset thường biểu thị **offset của bản ghi tiếp theo** cần tiêu thụ sau khi khôi phục.

Nếu đã xử lý an toàn record offset 104, giá trị commit là **105**, không phải 104:

```text
Processed: 100, 101, 102, 103, 104
Committed next offset: 105
Recovery begins from: 105
```

### 4.4. Checkpoint

Checkpoint là một **mốc khôi phục bền**. Nó có thể là:

- Kafka committed offset theo topic-partition.
- Một resume token của MongoDB change stream.
- Một source log position/LSN với partition/slot identifier tương ứng.
- Sequence number hoặc iterator state theo shard trong một stream.
- Một tuple gồm snapshot phase, cursor, source position và schema version.
- Một transactionally stored position của consumer cùng với dữ liệu sink.

Không có một kiểu số `long offset` toàn năng cho mọi CDC backend.

### 4.5. Watermark

Watermark trong stream processing thường là **mốc event-time** dùng để đánh giá mức hoàn tất của các cửa sổ thời gian, có thể chấp nhận late events theo policy. Nó **khác** committed source position:

```text
Committed offset: no need to replay earlier broker records.
Event-time watermark: windows earlier than time T can progress
                      under assumptions about late events.
```

Đừng lấy watermark làm checkpoint durable hoặc dùng offset làm thời gian phát sinh sự kiện.

## 5. Một source có thể sinh nhiều loại position

| Nguồn | Loại position tham khảo | Đặc điểm cần lưu ý |
|---|---|---|
| Kafka topic | Topic + partition + offset | Thứ tự trong partition; không có global order |
| MongoDB Change Streams | Opaque resume token | Resume theo ngữ nghĩa stream/pipeline và lịch sử còn khả dụng |
| PostgreSQL logical decoding | WAL LSN và metadata transaction/slot | Read/flush/apply/restart position khác nhau; retention WAL |
| MySQL binlog CDC | Binlog file/position hoặc GTID | Scope theo nguồn/timeline, GTID semantics theo topology |
| DynamoDB Streams | Stream ARN + shard + sequence/iterator context | Ordering và retention theo shard; reshard/shard lineage |
| Kafka Connect source | Source partition + source offset | Connector-specific; không đồng nhất với Kafka sink offset |
| Cassandra-style CDC | Commitlog/CDC segment và connector-specific cursor | Không có một global Kafka offset mặc định |
| Application outbox | Outbox ID, transaction sequence, source revision | Phụ thuộc schema, transaction và worker |

Bảng trên mô tả khái niệm, không thay thế API từng phiên bản/connector. Đặc biệt resume token có thể **opaque** và không được parse thành một timestamp tự chế.

## 6. Checkpoint là vector theo partitions, không nhất thiết là một số

Một consumer đọc ba partitions:

```text
topic order-events:
  partition 0 -> committed next offset 301
  partition 1 -> committed next offset 84
  partition 2 -> committed next offset 152
```

Trạng thái checkpoint thực chất là một map:

```json
{
  "order-events-0": 301,
  "order-events-1": 84,
  "order-events-2": 152
}
```

Nếu một partition lỗi và các partition khác vẫn xử lý tốt, tiến độ từng partition có thể khác. Đừng dùng **offset lớn nhất trên toàn topic** để bỏ những bản ghi chưa xử lý ở partition khác.

### Khi partition thay đổi

Repartition, reshard hoặc một stream bị recreate có thể tạo identity/epoch mới. Cần checkpoint bao gồm **source identity**, không chỉ số 301. Một số giống nhau trên hai stream khác nhau **không có cùng nghĩa**.

### Thứ tự theo entity

Nếu nghiệp vụ cần OrderCreated → OrderPaid → OrderCanceled đúng thứ tự cho **một order**, producer nên chọn partition/shard key thích hợp và consumer giữ ordering theo key. Nhưng sự kiện nhiều entity/phân vùng vẫn có thể đến xen kẽ, và CDC từ nhiều collection/table không tự có một global causal order nếu source không cung cấp.

## 7. Ba trục độc lập: đọc, áp dụng và ghi checkpoint

Gọi:

- **R:** record được fetch/read.
- **E:** hiệu ứng nghiệp vụ được commit vào sink.
- **C:** checkpoint được commit.

Có thể quan sát:

```text
R -> E -> C    (at-least-once processing pattern)
R -> C -> E    (at-most-once risk)
R -> [E + C atomically] (when same transactional authority supports it)
```

### Không được suy từ R ra E

Một `poll()`, `onNext()`, `getRecords()` hoặc callback “received” chỉ chứng minh message đã tới một tầng. Nếu worker crash trước khi ghi sink, cần replay.

### Không được suy từ E ra C

Ghi sink thành công nhưng checkpoint chưa bền dẫn tới **replay** sau restart. Handler phải chịu được.

### Không được suy từ C ra E

Nếu checkpoint commit trước khi sink effect thành công, restart có thể **skip message**. Đây là nguy cơ mất dữ liệu nghiệp vụ.

## 8. Lịch sử crash A: commit checkpoint trước side effect

```text
T0 Consumer poll offset 104.
T1 Consumer commits offset 105.
T2 Process crashes.
T3 NoSQL sink still has old state.
T4 Consumer restarts from offset 105.
```

Message 104 không còn trong đường replay bình thường của consumer group. Nếu không có audit/reconciliation độc lập, effect đó có thể **không bao giờ được thực hiện**.

Đây là kiểu “ACK sớm” dẫn đến **at-most-once delivery/handling trong một số cấu hình**, thường không phù hợp với nghiệp vụ cần không mất sự kiện.

### Khi nào at-most-once chấp nhận được?

Một số telemetry/metrics ít quan trọng có thể ưu tiên latency và chấp nhận mất mẫu nhỏ. Nhưng với:

- Thanh toán.
- Ledger.
- Đồng bộ search chính thức.
- Cập nhật quota.
- Gửi thông báo bắt buộc.
- Audit/compliance events.

thường không nên commit tiến độ trước khi effect được bảo đảm theo hợp đồng.

## 9. Lịch sử crash B: side effect thành công rồi mới checkpoint

```text
T0 Consumer poll offset 104.
T1 Sink applies update version 8, acknowledges success.
T2 Process crashes before committing offset 105.
T3 Consumer restarts at offset 104.
T4 Handler receives offset 104 again.
```

Không bị mất event, nhưng **có thể lặp xử lý**. Đây là pattern phổ biến cho **at-least-once**: sau khi consumer ổn định, một record có thể được áp dụng một hoặc nhiều lần nếu không có dedup.

### “Sink ACK” cũng cần hiểu đúng

Một ACK database có thể tương ứng với:

- Write đã được primary chấp nhận.
- Write đã đạt write concern/quorum.
- Transaction đã commit.
- Update được lưu vào một durable log.
- Search index đã chấp nhận update nhưng chưa refresh để truy vấn nhìn thấy.

Phải đọc consistency/durability contract của sink. Đừng gọi một HTTP 200 từ service wrapper là bằng chứng tất cả replicas đã hội tụ hoặc search đã visible.

### Hai trạng thái khác nhau

```text
businessEffectCommitted = true
checkpointCommitted = false
```

Đây là một trạng thái hợp lệ. Hệ cần **idempotent replay**, không cần tự xóa effect đã commit để làm history đẹp hơn.

## 10. Ma trận điểm crash

| Điểm crash | Sink đã commit? | Checkpoint bền? | Sau restart | Nguy cơ |
|---|---|---|---|---|
| Trước khi fetch | Không | Không thay đổi | Fetch như thường | Không |
| Sau fetch, trước process | Không | Không | Replay/fetch lại | Không nếu retention còn |
| Sau checkpoint sớm, trước sink | Không | Có | Bỏ qua event | **Mất effect** |
| Trong khi sink write, timeout | Không rõ | Không | Replay | Trùng nếu write đã commit |
| Sau sink commit, trước checkpoint | Có | Không | Replay | **Duplicate attempt** |
| Trong khi checkpoint write, timeout | Có | Không rõ | Có thể replay hoặc skip | Cần idempotency |
| Sau sink commit và checkpoint commit | Có | Có | Bắt đầu sau event | Bình thường |
| Sau ACK source position nhưng trước broker publish | Chưa chắc broker bền | Source đã tiến | CDC có thể bỏ event | **Mất chuyển tiếp** |
| Broker ACK nhưng consumer chưa xử lý | Chưa | Consumer checkpoint chưa tiến | Delivery lại nếu log còn | Chậm/retention |

Các hàng mô tả những tình huống có thể xảy ra theo thiết kế cụ thể, không khẳng định mọi CDC engine đều commit ở từng bước giống nhau.

## 11. At-most-once, at-least-once và exactly-once theo phạm vi

### At-most-once

Một message không được cố áp dụng lại sau khi đã ACK trước; có thể mất effect nếu xử lý lỗi. Chỉ phù hợp nơi mất mát có thể chấp nhận.

### At-least-once

Hệ cố truyền/xử lý lại cho đến khi ghi nhận thành công hoặc đi vào một trạng thái terminal có chủ đích. Có thể nhận duplicate.

At-least-once **không tự chứng minh sẽ hoàn tất vô hạn** nếu log retention hết, process dừng mãi hoặc message không giải được; liveness phụ thuộc khả năng phục hồi và error policy.

### Exactly-once delivery vs exactly-once effect

Một engine có thể bảo đảm đúng một lần **trong phạm vi transaction/stream nội bộ**, nhưng điều đó **không** tự khiến:

- Gọi payment provider.
- Gửi email SMTP.
- Tăng counter Redis.
- Ghi MongoDB bên ngoài transaction Kafka.
- Gọi HTTP endpoint không idempotent.

chỉ có một business effect.

**Đặt câu hỏi “exactly-once *ở đâu*?” trước khi chấp nhận một tuyên bố.**

### Kết quả mong muốn trong nhiều hệ nghiệp vụ

At-least-once delivery + idempotent handler + durable checkpoint/reconciliation thường giúp đạt **một business effect logic cho mỗi event** trong phạm vi authority được bảo vệ, dù một event có nhiều delivery attempts.

## 12. Phân biệt source checkpoint với consumer checkpoint

Trong pipeline:

```text
Source DB -> CDC Connector -> Kafka -> Consumer A -> Search
                                 |
                                 +-> Consumer B -> Analytics
```

có ít nhất ba tiến độ:

1. **Source connector checkpoint:** đã chuyển các thay đổi nào từ source sang broker.
2. **Consumer A checkpoint:** đã xử lý những offsets nào vào search.
3. **Consumer B checkpoint:** đã xử lý những offsets nào vào analytics.

Nếu source connector đã ACK position S sau khi publish event bền vào Kafka, điều đó **không** có nghĩa search hoặc analytics đã áp dụng event.

Consumer A và B có checkpoints **độc lập**, có thể tiến độ khác nhau. Không nên để việc consumer B chậm tự được báo thành lỗi source publish nếu kiến trúc cho phép fan-out độc lập.

### Vì sao hai tầng checkpoint quan trọng?

Nếu connector checkpoint source trước khi broker ghi bền, crash có thể mất bridge event. Nếu connector đợi mọi downstream cuối cùng ACK, có thể không còn fan-out độc lập và source retention/latency bị ràng buộc bởi consumer chậm nhất.

Trong thực tế, cần chọn **điểm bàn giao trách nhiệm bền** giữa các tầng: từ source log sang broker durable log, rồi từ broker sang consumer effects.

## 13. Kafka: committed offset là “bản ghi tiếp theo”

Với Kafka Consumer API, khi tự commit offsets, ta dùng:

```text
TopicPartition(order-events, 0)
last fully processed record offset = 104
commit offset = 105
```

Ví dụ logic:

```java
TopicPartition tp =
    new TopicPartition("order-events", 0);

Map<TopicPartition, OffsetAndMetadata> commitPositions =
    Map.of(tp, new OffsetAndMetadata(105L));

consumer.commitSync(commitPositions);
```

Không nhầm `commit offset 104` với “đã xử lý record 104”: như thế thường sẽ **đọc lại 104** khi phục hồi.

### Offset commit không kiểm tra business state

Broker lưu vị trí do consumer báo; nó không tự vào MongoDB để xác minh invoice đã được ghi, hay vào email provider để xác minh email đã gửi. Nếu application gọi commit quá sớm, broker không tự ngăn.

### Auto-commit

Khi enable auto-commit, driver có thể commit vị trí đã poll theo thời gian, **không chờ business processing async của bạn**. Với handler có side effect quan trọng và có thể kéo dài, cần cân nhắc manual offset commit, giới hạn in-flight và lập luận rõ các điểm hoàn tất.

## 14. Ordering và “contiguous completed prefix”

Giả sử một partition có:

```text
Offset:        10  11  12  13  14
Status:        OK  OK  RUN OK  OK
```

Nếu offset 12 còn xử lý, **không commit next offset 15** chỉ vì 13 và 14 đã xong: như vậy recovery sẽ bỏ qua 12.

Chỉ có thể xác nhận **đoạn liên tục đã hoàn tất tính từ checkpoint trước**:

```text
Processed safely: 10, 11
Still pending:     12
Completed later:   13, 14
Commit next offset: 12
```

Khi 12 hoàn tất, có thể tiến checkpoint qua 13, 14 nếu tất cả vẫn được chứng minh durable.

### Hệ quả của xử lý song song

Xử lý song song trong một partition làm tăng throughput nhưng cần **per-partition completion tracker**, tránh dùng max completed offset.

Nếu domain đòi thứ tự tác động cho một entity, xử lý song song không được làm `PAID` hoàn tất sau `CANCELED` rồi ghi đè trạng thái mới. Có thể xử lý tuần tự theo partition/key, hoặc dùng entity revision/CAS để chặn stale event.

### Có thể commit các partitions khác độc lập

Nếu partition 0 dừng ở 12, partition 1 đã hoàn tất tới 300, có thể commit partition 1 tới 301 mà không ép chờ partition 0, nếu thiết kế consumer hỗ trợ.

## 15. Offset, event ID và entity revision không thay thế nhau

Một event có thể mang:

```json
{
  "eventId": "EV-9081",
  "aggregateId": "ORDER-1001",
  "aggregateRevision": 8,
  "eventType": "OrderPaid",
  "sourcePosition": "opaque-source-position",
  "occurredAt": "2026-11-14T10:00:00Z"
}
```

Sau khi publish vào Kafka nó còn có:

```text
topic=order-events
partition=2
offset=104
```

Mỗi trường làm việc khác nhau:

| Trường | Mục đích |
|---|---|
| `eventId` | Dedup cùng event khi retry/republish |
| `aggregateId` | Route/serialize các event một entity |
| `aggregateRevision` | Chặn update cũ đè mới, phát hiện thiếu phiên bản |
| `sourcePosition` | Resume CDC từ source theo giao thức đó |
| Topic/partition/offset | Replay theo broker log |
| `occurredAt` | Event-time/windowing/audit, không phải checkpoint |
| `processedAt` | Tracing/SLO, không làm bằng chứng effect commit |

Không dùng `occurredAt` hoặc timestamp máy worker để suy rằng event này có offset mới hơn mọi partition, hoặc tự đổi opaque source position thành thứ tự số.

## 16. Idempotent consumer: cùng event chạy lại vẫn chỉ có một hiệu ứng logic

Nếu hệ thống chấp nhận **at-least-once**, handler phải an toàn trước duplicate. Một pattern là **inbox ledger**:

```text
Incoming event EV-9081
    |
    v
Check/claim eventId at authoritative sink
    |
    +-- Already committed -> no-op / return stored outcome
    |
    +-- First time -> apply business mutation
                    -> record event as processed
                    -> COMMIT atomically
    |
    v
Commit broker offset AFTER durable sink outcome
```

Điều cần phân biệt là **dedup theo event** và **dedup theo delivery attempt**. Nếu retry cùng event được tạo với offset khác hoặc một relay publish duplicate, cùng `eventId` phải định danh một *logical event*, không lấy Kafka offset của mỗi attempt làm business key duy nhất.

### Ví dụ inbox

```json
{
  "tenantId": "T01",
  "subscriberId": "search-indexer",
  "eventId": "EV-9081",
  "aggregateId": "ORDER-1001",
  "sourceRevision": 8,
  "state": "APPLIED",
  "appliedAt": "2026-11-14T10:00:02Z"
}
```

Key uniqueness cần scoped theo **subscriber và tenant/source identity** nếu nhiều subscribers có quyền xử lý một event độc lập. Nếu cùng eventId được tái sử dụng sai bởi hai nguồn, phải có namespace nguồn.

### Vì sao `exists(eventId)` rồi `insert` không đủ?

Hai workers có thể cùng nhận một event:

```text
Worker A: inbox.exists(EV-9081) -> false
Worker B: inbox.exists(EV-9081) -> false
Worker A: apply +1
Worker B: apply +1
Worker A: insert inbox
Worker B: insert inbox (duplicate error)
```

Đã double effect trước khi phát hiện duplicate. Cần **unique conditional claim/transaction** sao cho thao tác claim và business effect được ràng buộc đúng phạm vi.

## 17. Inbox và cập nhật sink phải có cùng transaction boundary

Giả sử muốn cập nhật counter khi nhận event:

```text
Step 1: INSERT inbox(eventId) IF ABSENT
Step 2: INCREMENT counter
```

Nếu hai bước nằm trong hai database/transactions độc lập:

- Crash sau inbox insert trước increment → restart thấy duplicate, **bỏ increment**.
- Crash sau increment trước inbox insert → restart thực hiện increment lần hai.

Đây là lỗi **dual-write** ở ngay bên trong consumer.

### Phương án A: transaction cùng authority

```text
BEGIN TRANSACTION
  conditional insert processed_events(eventId)
  update order projection / increment counter
COMMIT
THEN checkpoint consumer offset
```

Khi cả hai mutations được database hỗ trợ atomically, event được đánh dấu processed **cùng lúc** effect trở nên durable.

### Phương án B: một atomic conditional update

Nếu business state và metadata event có thể đặt cùng document/item/partition theo API, một update có điều kiện có thể:

```text
IF eventId not applied:
  append/dedup mark
  apply update
  advance revision
```

Cần lưu ý giới hạn document size/retention nếu chứa vô hạn event IDs.

### Phương án C: external provider có idempotency key

Nếu effect là charge payment ở hệ khác:

```text
record durable intent with provider idempotency key
invoke provider with same key on retries
verify provider outcome/reference
record terminal result
checkpoint event only after agreed terminal handling
```

**Không có một transaction NoSQL tự động commit chung với provider bên ngoài.** Provider idempotency và reconciliation là một phần của protocol nghiệp vụ.

## 18. MongoDB: transaction giữa inbox và projection

Ví dụ thiết kế:

```text
Collection: processedEvents
  _id = subscriberId + ":" + sourceId + ":" + eventId
  unique

Collection: orderSearchProjection
  tenantId + orderId -> projection fields, sourceRevision
```

Trong một transaction MongoDB được deployment/driver hỗ trợ:

```javascript
await session.withTransaction(async () => {
  await db.collection("processedEvents").insertOne(
    {
      _id: processedKey,
      eventId: event.eventId,
      subscriberId: "search-indexer",
      tenantId: event.tenantId
    },
    { session }
  );

  await db.collection("orderSearchProjection").updateOne(
    {
      tenantId: event.tenantId,
      orderId: event.orderId,
      sourceRevision: { $lt: event.revision }
    },
    {
      $set: {
        state: event.state,
        sourceRevision: event.revision
      }
    },
    { session }
  );
});
```

Đây là **pseudocode MongoDB-style**, không phải implementation production hoàn chỉnh: phải xử lý trường hợp document chưa tồn tại, unique index, previous revision bằng null, matchedCount, duplicate key, transaction retry/commit ambiguity, authorization và write concern.

### Cảnh báo quan trọng về callback retry

MongoDB `withTransaction` có thể chạy lại transaction callback trong một số lỗi transient. Không đặt lời gọi gửi email, charge hoặc publish event không idempotent **bên trong callback** rồi giả định callback chỉ chạy một lần.

### Sau commit transaction

Chỉ khi transaction thành công theo hợp đồng cần thiết, consumer mới commit offset. Nếu commit MongoDB trả **unknown result**, không tự tiếp tục như chắc chắn thất bại; phải tra inbox/projection hoặc dùng commit retry theo driver contract.

### Nếu duplicate key

Khi `processedEvents` đã có key với trạng thái APPLIED hợp lệ, có thể coi event đã xử lý và tiến checkpoint sau khi **xác minh**. Nhưng duplicate key do **payload khác cùng eventId** là lỗi integrity, không được im lặng bỏ.

## 19. Conditional projection với source revision

Một handler cập nhật materialized view:

```text
Event Order v7 -> state=CREATED
Event Order v8 -> state=PAID
Event Order v9 -> state=CANCELED
```

Network/retry có thể khiến event v7 tới sau v9. Nếu handler ghi đè vô điều kiện, view lùi từ CANCELED về CREATED.

### Version guard

```text
apply(event):
  if event.revision <= current.sourceRevision:
      no-op (duplicate or stale)
  else:
      update projection to event.revision
```

Điều kiện so sánh và update phải **atomic trong scope của projection**.

### Có được nhảy từ revision 7 sang 9?

Tùy event semantics:

- **Full-state replacement event:** nếu v9 chứa toàn bộ state hợp lệ, có thể áp v9 và bỏ v8 trong một số read model.
- **Delta event:** nếu v8 là cộng tiền và v9 là trừ tiền, bỏ v8 khiến kết quả sai. Phải đảm bảo **contiguous revision**, buffer, fetch source snapshot hoặc repair gap.

### Không dùng max revision toàn hệ

Revision của Order O1 và O2 có thể không so được; phải giữ theo **aggregate/source scope**. Một số source không có số revision đơn điệu; khi đó thiết kế idempotency/ordering cần source protocol khác.

## 20. Kafka transactions bảo đảm gì?

Kafka hỗ trợ producer transactions và một số mô hình stream processing có thể **atomically ghi output records vào Kafka và commit consumed offsets** trong cùng transaction Kafka khi sử dụng đúng API.

Sơ đồ:

```text
Kafka input topic (offset 104)
   |
   v
Consume -> transform
   |
   +-- Produce output to Kafka topic
   +-- Send input offset 105 to Kafka transaction
   |
   v
Commit Kafka transaction atomically
```

Các readers sử dụng `isolation.level=read_committed` chỉ nhìn thấy những records transactional đã commit theo protocol. Producer fencing và transaction IDs giúp bảo vệ trước producer instance cũ trong phạm vi Kafka.

### Nhưng có giới hạn lớn

Kafka transaction **không tự commit atomically** với:

- MongoDB update.
- DynamoDB conditional write.
- Redis INCR.
- Một HTTP payment call.
- Email/SMS provider.
- Một external search engine.

Nếu output chỉ nằm trong Kafka và offset commit cũng ở Kafka, có thể có semantics mạnh hơn. Nếu sink là database ngoài Kafka, cần transactional sink/inbox/idempotency hoặc cơ chế connector-specific đúng.

### “Exactly-once” luôn cần định nghĩa boundary

Không dùng quảng cáo “Kafka exactly once” để bỏ inbox cho một external side effect không idempotent. Phải chứng minh **hai thứ cần atomic** thật sự nằm trong cùng authority, hoặc có giao thức khôi phục/reconciliation khi không thể atomic.

## 21. Outbox ở source: checkpoint không sửa được sự cố dual-write

Giả sử service làm:

```text
1. Update order in MongoDB
2. Publish OrderPaid to Kafka
```

Crash giữa 1 và 2:

```text
Order committed, event not published
```

Không có consumer checkpoint nào cứu được event chưa từng xuất hiện.

### Transactional outbox

Trong một transaction source được hỗ trợ:

```text
BEGIN
  update order -> PAID
  insert outbox(eventId, orderId, revision, payload)
COMMIT
```

Sau đó CDC/outbox relay publish event. Relay có thể publish trùng nếu response broker mất hoặc crash trước khi đánh dấu giao thành công. Vì vậy consumer vẫn cần idempotency.

### Hai mốc khác nhau

- **Source transaction commit:** business state và outbox intent đã tồn tại bền.
- **Relay checkpoint:** event đã được chuyển tới durable broker theo điều kiện relay chấp nhận.

Không mark outbox event `published=true` **trước** broker ACK phù hợp rồi coi job hoàn thành. Cũng không suy broker ACK chứng minh mọi subscribers đã xử lý.

### Khi broker/relay outage

Outbox vẫn giữ events chờ publish, làm tăng backlog nhưng tránh mất intent (trong giới hạn retention/correctness). Cần metrics queue age, retry/backoff, DLQ và disk usage. Hãy phân biệt **lag của relay** với **lag của từng downstream consumer**.

## 22. Kafka Consumer Java: commit sau effect bền

Ví dụ Java sử dụng Kafka Consumer API với manual commits. Đoạn mã ưu tiên minh họa **thứ tự xử lý**, không phải toàn bộ retry/rebalance production.

```java
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;

public final class OrderEventConsumer {
    interface DurableSink {
        // Return only after atomic inbox+effect commit (or a
        // verified duplicate with committed business outcome).
        void applyIdempotently(
            String topic,
            int partition,
            long offset,
            String eventJson
        ) throws Exception;
    }

    public static void run(
        String bootstrapServers,
        DurableSink sink
    ) throws Exception {
        Properties props = new Properties();
        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        );
        props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-search-indexer");
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName());
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName());
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (KafkaConsumer<String, String> consumer =
                new KafkaConsumer<>(props)) {
            consumer.subscribe(List.of("order-events"));

            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(500));

                for (ConsumerRecord<String, String> event : records) {
                    // If this throws, fail this processing loop:
                    // do not advance offset past the failed event.
                    sink.applyIdempotently(
                        event.topic(),
                        event.partition(),
                        event.offset(),
                        event.value()
                    );

                    TopicPartition tp = new TopicPartition(
                        event.topic(), event.partition());

                    // Checkpoint points to the NEXT record.
                    consumer.commitSync(Map.of(
                        tp, new OffsetAndMetadata(event.offset() + 1L)
                    ));
                }
            }
        }
    }
}
```

### Vì sao ví dụ commit từng event?

Cách này đơn giản hóa lập luận: **durable sink effect trước, next offset commit sau**. Nó có thể tốn network round trips và giảm throughput. Production thường batch commits hoặc dùng async, nhưng phải bảo vệ contiguous prefix, group rebalance và commit retries.

### Những điều code chưa giải quyết

- Nếu `sink.applyIdempotently` ném exception, cần bounded retry, pause/seek hoặc thoát và restart theo orchestration; đoạn này để exception truyền lên để **không tiếp tục poll rồi bỏ qua event lỗi**.
- `consumer.commitSync` có thể ném lỗi vì rebalance, timeout hoặc broker không sẵn; effect đã commit, nên lần xử lý lại phải idempotent.
- `auto.offset.reset=earliest` **không khôi phục dữ liệu đã bị retention xóa**. Đó chỉ là chính sách khi group thiếu offset hợp lệ.
- Không mô tả clean shutdown với `consumer.wakeup()`, signal handling hoặc rebalance listener.
- Consumer API thường **không thread-safe**; đoạn này dùng một polling thread sở hữu consumer.
- Không tự chứng minh event schema/authorization, source ordering hoặc correctness của `DurableSink`.
- Việc commit từng event vào một topic partition không cho phép dùng offset đó để checkpoint partition khác.

## 23. Batch processing: chỉ ACK đoạn đã hoàn tất

Một batch:

```text
Offsets delivered: 100, 101, 102, 103, 104
Sink committed:    100, 101, 102
Failed:            103
Not started:       104
```

Nếu worker muốn tiến checkpoint, chỉ được commit next offset **103** cho partition đó; không commit 105.

### Batch all-or-nothing

Nếu tất cả writes của batch và inbox claims nằm trong **một transaction sink**, có thể:

```text
BEGIN -> apply 100..104 + ledger -> COMMIT
THEN commit offset 105
```

Nếu transaction abort, không commit 105. Nếu sink commit thành công nhưng offset commit lỗi, batch được replay và dedup.

### Batch partial successes

Nếu sink ghi từng record, có thể có 100..102 thành công, 103 lỗi, 104 chưa chạy. Phải lưu đủ progress hoặc replay 103..; không giả định cả batch đều hoàn tất chỉ vì `bulkWrite` trả response 200 cho một số item.

### Bulk API trả partial failures

Một NoSQL bulk API hoặc search bulk endpoint có thể báo một số records thành công, một số fail. **HTTP-level success** có thể không đồng nghĩa **all items committed**. Check per-item results, phân loại retryable/permanent, giữ checkpoint không vượt lỗ hổng.

## 24. Async workers: offset không được theo max completed

Một consumer poll một batch và dispatch:

```text
offset 50 -> worker A  DONE
offset 51 -> worker B  SLOW
offset 52 -> worker C  DONE
offset 53 -> worker D  DONE
```

Vị trí checkpoint hợp lệ là 51 (next sau 50), **không phải 54**.

### Pseudocode completion tracker

```text
state per TopicPartition:
  nextCommittableOffset
  completedOffsetsSet
  outstandingAttempts

onDurableSuccess(offset):
  mark offset complete
  while nextCommittableOffset is complete:
      remove it from completed set
      nextCommittableOffset += 1
  commit nextCommittableOffset only if
      this consumer still owns partition generation
```

### Bộ nhớ và backpressure

Nếu offset 51 mắc kẹt còn hàng nghìn offsets sau hoàn tất, completed set có thể lớn. Cần giới hạn số in-flight per partition và pause input khi đạt ngưỡng, không xử lý vô hạn trong khi checkpoint đứng yên.

### Order-sensitive sinks

Nếu cập nhật một tài khoản/order dựa trên delta, không được xử lý hai events cùng aggregate ngoài thứ tự rồi chỉ dùng contiguous checkpoint để cứu. Checkpoint chỉ theo dõi delivery progress; entity state cần **ordering/transaction/revision logic** riêng.

## 25. Consumer group rebalance: người xử lý cũ còn quyền commit không?

Khi thành viên group join/leave, partitions được chuyển cho consumer khác:

```text
Consumer A owns partition P
  poll offset 104
  dispatch slow worker W

Group rebalance
  P reassigned to Consumer B
  B starts at last committed checkpoint

W wakes and writes late
```

Nếu W dùng stale ownership mà vẫn ghi, có thể có **hai consumers đồng thời tạo effect** cho cùng event.

### Các biện pháp

- Trong callback revoke, ngừng dispatch mới, hoàn tất/huỷ có kiểm soát in-flight work, commit **chỉ prefix đã an toàn** khi còn hợp lệ.
- Sau khi revoke, worker cũ không được commit offsets cho partition không còn sở hữu.
- Cần **generation/lease fencing** tại sink nếu application dùng async tasks lâu hoặc ownership có thể thay đổi.
- Nếu không thể fence một side effect ngoài, dùng provider idempotency và reconciliation.
- Đừng chia sẻ một Kafka `Consumer` qua nhiều worker threads để cùng poll/commit.

### Rebalance không tự bảo đảm đúng một consumer handler tại mọi thời điểm thực

Broker kiểm soát group assignment/commits, nhưng một task đã dispatch trước revoke vẫn có thể chạy trên CPU hoặc gọi network. **Exclusive assignment danh nghĩa không đồng nghĩa external effect được fence**.

### `max.poll.interval.ms` và workload dài

Nếu consumer xử lý quá lâu mà không poll, group có thể coi nó không đáp ứng yêu cầu liveness và bắt đầu rebalance. Giải pháp không đơn giản là tăng timeout vô hạn: cân nhắc bounded dispatch, pause/resume, worker isolation và manual tracking.

## 26. Checkpoint trong chính sink transaction

Một cách giảm cửa sổ dual-write là lưu **consumer checkpoint cùng business effect trong cùng NoSQL transaction**, nếu cả hai nằm trong authority hỗ trợ:

```text
BEGIN SINK TRANSACTION
  apply OrderPaid to order_projection
  update checkpoint(topic, partition, consumerGroup) to 105
COMMIT
```

Khi restart, consumer có thể **đọc checkpoint từ sink** và `seek` source stream tới offset phù hợp. Hai dữ liệu có một commit point tại sink.

### Điều kiện cần

- Transaction thực sự atomic cho projection + checkpoint.
- Checkpoint record phân biệt topic, partition, group và source incarnation.
- Chỉ một owner hợp lệ được update checkpoint; CAS/generation fencing cho rebalance.
- Advance checkpoint theo **contiguous prefix**, không theo record lớn nhất đã thấy.
- Offset nguồn còn trong retention hoặc có snapshot/recovery plan.
- Cần định nghĩa cách reconcile khi Kafka committed offset và sink checkpoint lệch nhau.

### Không phải mọi NoSQL transaction đa key đều tồn tại

Một DynamoDB item/transaction và một MongoDB transaction có ranh giới khác Redis Cluster hoặc Cassandra partition. Không tự giả định có transaction phân tán giữa một datastore và Kafka broker.

### Vì sao vẫn có thể dùng Kafka offset commit?

Có thể commit Kafka offset như **tối ưu/khả năng vận hành**, còn source of truth của tiến độ là sink checkpoint. Nhưng phải định nghĩa ai là authority khi chúng khác nhau, và không tự lấy **max của hai offsets** vì điều đó có thể bỏ lỗ hổng chưa xử lý.

## 27. Checkpoint và external API: cần một durable workflow

Một handler nhận `OrderPaid` rồi gửi email:

```text
Consume OrderPaid
Call email provider
Checkpoint offset
```

Provider có thể **đã gửi email nhưng response mất**. Không thể chắc chắn từ timeout rằng email chưa gửi. Nếu handler retry, có thể gửi hai lần.

### Pattern

1. Tạo durable notification job với **eventId/notificationId** trong sink/inbox transaction.
2. Commit input processing checkpoint sau khi job đã được chấp nhận bền.
3. Worker riêng gửi email với idempotency key nếu provider hỗ trợ.
4. Ghi status `SENT`/`UNKNOWN`/`RETRYABLE`/`FAILED_FINAL`.
5. Reconcile theo provider reference trước khi retry có nguy cơ duplicate.

Điều này thay đổi semantics:

- Input event được xem là “đã xử lý thành công” khi **durable notification intent được lưu**.
- **Email delivery** là một workflow khác có checkpoint/status riêng.

Không được trả lời business “email đã gửi” chỉ vì Kafka consumer offset đã commit.

### Nếu không có provider idempotency

Đôi khi không thể bảo đảm đúng một external effect. Hãy nêu rõ khả năng duplicate, chọn chính sách retry/manual review và đưa business reconciliation vào yêu cầu; đừng tuyên bố exactly-once không có chứng minh.

## 28. Poison message, retry và DLQ

Một event không xử lý được vì:

- Payload malformed.
- Schema version không tương thích.
- Unknown enum.
- Thiếu reference mà sớm muộn source sẽ có.
- Sink tạm unavailable.
- Permission/tenant mismatch.
- Invariant nghiệp vụ bị vi phạm.

Nếu không có error policy, một record có thể **chặn cả partition** mãi.

### Phân loại

| Lỗi | Xử lý gợi ý |
|---|---|
| Timeout/transient sink outage | Retry bounded với backoff/jitter |
| Rate limiting | Respect retry-after/quota |
| Thiếu dependency tạm thời | Retry/reconcile theo source revision |
| Payload malformed | Quarantine/DLQ có lưu raw reference an toàn |
| Unsupported schema | Dừng/route DLQ, báo incompatibility |
| Tenant scope violation | Security incident; không silently skip |
| Duplicate event đã applied | No-op rồi có thể checkpoint |
| Permanent business rejection | Terminal status theo contract, có audit |

### Có thể commit offset sau khi gửi DLQ không?

**Có điều kiện.** Nếu policy quy định “chuyển bền sang DLQ để xử lý sau” được xem là hoàn thành trách nhiệm của consumer chính, có thể commit offset **sau khi DLQ append thành công bền**. Khi đó DLQ có một **workflow xử lý và checkpoint riêng**.

Không commit trước DLQ ACK rồi tự coi event đã được bảo tồn.

### Kafka transaction cho DLQ

Nếu DLQ cũng là Kafka topic và offset input cùng nằm trong một Kafka transaction được cấu hình đúng, có thể commit **DLQ record + consumed offset** atomically trong phạm vi Kafka. Nếu DLQ là database ngoài, cần pattern idempotency/outbox phù hợp.

### Rủi ro sai thứ tự khi skip

Nếu record offset 103 có delta quan trọng nhưng được đưa DLQ, tiếp tục áp delta ở 104 có thể làm state sai. Chính sách “quarantine và tiếp tục” phải dựa trên **kiểu event**, tính phụ thuộc và khả năng repair, không đơn thuần vì muốn offset tiến.

## 29. Retention: checkpoint đứng yên không giữ dữ liệu mãi mãi

Kafka và nhiều change stream có **retention hữu hạn**. Nếu consumer outage dài:

```text
Committed offset 100
Broker log now retains only offsets >= 500
Consumer restarts -> offset 100 no longer available
```

Không có retry đơn giản nào đọc lại được record đã bị xóa khỏi nguồn hiện tại.

### Cần kế hoạch

- Theo dõi lag dưới cả dạng **offset lag** và **time lag**.
- Alert trước khi gap tiến đến retention window.
- Tăng capacity hoặc xử lý poison message để tránh đứng yên.
- Nếu mất lịch sử: khôi phục từ backup/snapshot/replay khác hoặc rebuild projection từ source, theo cơ chế data-specific.
- Không auto-reset silently sang `latest` với consumer quan trọng; như vậy có thể bỏ mất toàn bộ khoảng sự kiện.

### Offset ngoài retention

`auto.offset.reset=earliest` có thể đưa consumer về bản ghi **sớm nhất còn lưu**, không quay ngược thời gian để lấy dữ liệu đã retention xóa. `latest` cũng không phải “khôi phục từ checkpoint gần nhất”; nó có thể bỏ backlog.

### Retention của inbox

Nếu event replay có thể xảy ra sau 30 ngày nhưng inbox dedup IDs bị TTL sau 7 ngày, hệ có thể áp lại event cũ. Cần retention phù hợp với **source replay khả dĩ, broker retention, DLQ/redrive, snapshots và external provider window**.

## 30. Nguồn CDC cũng bị backpressure từ checkpoint

Khác với một consumer đọc log bền từ broker, một CDC connector đọc **transaction log của database nguồn**.

Ví dụ PostgreSQL logical replication có thể giữ WAL segments vì replication slot hoặc lagging consumers. Một connector không advance những vị trí đã xác nhận có thể khiến source **tăng dung lượng WAL**, cần giám sát và giới hạn phù hợp.

MongoDB Change Streams phụ thuộc lịch sử change log/oplog còn khả dụng để resume. Nếu consumer ngắt quá lâu và token không còn trong lịch sử, cần cơ chế resnapshot/rebuild phù hợp.

### Hai mặt của checkpoint

- **Advance quá sớm:** có nguy cơ mất event trong lúc bàn giao.
- **Advance quá chậm:** log retention/backlog/disk pressure và độ trễ tăng.

Do đó thiết kế không chỉ tối ưu “không mất message”, mà còn phải đảm bảo **tiến độ bền, có giới hạn tài nguyên và chiến lược phục hồi**.

### Theo dõi source retention

Đừng chỉ nhìn Kafka consumer lag. Với CDC cần thêm source WAL/oplog retention headroom, slot lag, connector publish failures, snapshot progress và khả năng source vẫn giữ được change log cho resume.

## 31. MongoDB Change Streams: checkpoint bằng resume token

MongoDB Change Streams trả các change events kèm **resume token**, thường nằm ở field `_id` của change event. Đây là token của **stream resume protocol**, không phải application event ID tùy ý và không nên parse thành số offset đơn giản.

Ví dụ khái niệm:

```json
{
  "_id": { "_data": "opaque-resume-token" },
  "operationType": "update",
  "ns": {
    "db": "shop",
    "coll": "orders"
  },
  "documentKey": { "_id": "ORDER-1001" },
  "updateDescription": {
    "updatedFields": { "state": "PAID" }
  }
}
```

Đây là event minh họa; event thật có những field khác nhau theo operation, stream scope và MongoDB version.

### Thứ tự an toàn ở CDC relay

```text
1. Read change event E with token T.
2. Transform E into business event with stable identity.
3. Publish E to durable broker; wait for required ACK.
4. Persist checkpoint T under correct stream identity.
5. Continue.
```

Nếu crash giữa bước 3 và 4, khi resume từ token cũ, E có thể được publish lại. Consumer cần event identity/dedup.

Nếu persist T **trước** khi broker nhận bền E, crash có thể khiến connector **bỏ qua E** khi resume.

### Resume options không hoàn toàn giống nhau

Các lựa chọn như `resumeAfter`, `startAfter` và `startAtOperationTime` có điều kiện và phạm vi hỗ trợ khác nhau tùy MongoDB version/stream state. Đặc biệt một sự kiện invalidate có thể ảnh hưởng cách resume. Không copy token từ stream/pipeline khác rồi tự giả định hợp lệ.

### Token phải thuộc đúng stream

Checkpoint nên gắn với:

- Cluster/connection identity theo topology được quản lý.
- Database/collection/stream scope.
- Pipeline/options tương thích với resume.
- Resume token nhận từ stream.
- Consumer/connector ownership hoặc generation.

### Khi history đã bị cắt

Nếu token không còn có thể resume vì history/oplog không còn, connector không nên âm thầm bắt đầu từ “now” mà bỏ gap dữ liệu. Cần báo trạng thái **recovery required**, resnapshot/rebuild hoặc dùng nguồn lịch sử khác.

### Full document lookup không là source snapshot của event

Với change streams, option lấy full document hiện tại có semantics riêng. Một document có thể thay đổi **sau** mutation tạo event nhưng **trước** lúc lookup, nên không được tự suy rằng mọi fullDocument lookup là after-image chính xác tại thời điểm event. Nếu nghiệp vụ cần full before/after state và revision, phải dùng tính năng và điều kiện được source hỗ trợ hoặc xây event payload phù hợp.

## 32. PostgreSQL WAL CDC: đọc LSN khác với xác nhận LSN

Một CDC connector đọc logical change stream của PostgreSQL có thể gặp các mốc:

```text
Database WAL record written/committed
   |
   v
Logical replication sender
   |
   v
Connector receives changes up to LSN X
   |
   v
Broker publication and durable ACK
   |
   v
Connector reports/persists safe source position
```

**WAL LSN** (*Log Sequence Number*) là vị trí trong log PostgreSQL, không phải Kafka offset. Một source transaction có thể sinh nhiều record/change events; cần xử lý ranh giới transaction và metadata do connector cung cấp.

### Không đồng nhất các mốc

- LSN đã **đọc tới**.
- LSN đã **được giao vào connector buffer**.
- LSN mà **broker đã nhận durable events tương ứng**.
- LSN được connector/checkpoint mechanism **xác nhận an toàn**.
- Vị trí replication slot còn phải **giữ WAL** để có thể phát lại.

Các mốc có thể khác nhau theo protocol/connector config. Không lấy offset cuối cùng của một Kafka partition rồi tự đổi thành LSN của Postgres.

### Backpressure ảnh hưởng database nguồn

Nếu replication slot không advance do connector chậm, WAL segments có thể bị giữ lâu, làm đầy disk. Đây là rủi ro vận hành quan trọng: một source connector ngừng quá lâu không chỉ làm search stale mà còn tạo áp lực tài nguyên cho primary.

### Một transaction nguồn có nhiều row changes

Nếu transaction cập nhật order, payment ledger và outbox cùng lúc, connector cần giữ semantics theo source log/transaction boundary khi publish. Nếu sink cần nhìn thấy một **aggregate-consistent snapshot**, xử lý rời rạc ba row changes mà không có transaction context có thể cho ra trạng thái tạm thời không nhất quán.

## 33. Kafka Connect và Debezium: source offsets không phải sink offsets

Một Kafka Connect **source connector** thường theo dõi:

```text
sourcePartition:
  which database/stream/shard?

sourceOffset:
  up to which source log position?
```

Một CDC record khi được ghi vào Kafka còn nhận **Kafka topic/partition/offset**. Hai mốc này thuộc **hai hệ log khác nhau**.

Ví dụ khái niệm:

```text
Source DB: change position S=LSN-X
Kafka output: topic=orders.cdc, partition=3, offset=948

Source connector checkpoint: S
Consumer checkpoint: 949 for topic partition 3
```

### Connector offset storage

Trong các deployment Kafka Connect, source offsets và connector metadata có thể được lưu qua offset backing store do runtime/config quyết định. Nội dung cụ thể là connector-specific. Không sửa một offset key bằng tay rồi mặc định nó có thể resume an toàn.

### Debezium snapshot + streaming

Debezium có các cơ chế snapshot/streaming/change event metadata theo connector. Source offset có thể biểu diễn snapshot progress, log position và các thông tin khác. Không ép tất cả thành `long offset`.

### Heartbeats

Một số connectors gửi heartbeat để thể hiện tiến độ, hỗ trợ giải quyết tình huống ít thay đổi ở một partition/source. Heartbeat không có cùng ý nghĩa “đã xử lý một business mutation”. Phải hiểu heartbeat có được tính vào checkpoint/lag measurement theo connector configuration hay không.

### Producer ACK từ Kafka chưa phải sink applied

Nếu Connect source publish thành công và checkpoint nguồn tiến, search worker vẫn có thể lag. Trách nhiệm tiếp theo thuộc Kafka retention + consumer group offsets. Đây là lý do monitoring phải tách **source connector lag** khỏi **consumer lag**.

## 34. DynamoDB Streams: sequence number theo shard

DynamoDB Streams xuất ra records thay đổi item với metadata stream/shard và sequence ordering theo giao thức.

Một worker có thể xử lý:

```text
Stream S
  Shard A: sequence 101, 102, 103
  Shard B: sequence 501, 502
```

**Đừng so** 103 ở shard A với 501 ở shard B để suy ra thứ tự giao dịch toàn hệ.

### Iterator không đồng nghĩa checkpoint

Một **shard iterator** là cơ chế truy cập records ở vị trí nào đó theo API, có vòng đời/giới hạn riêng. Checkpoint cần bền theo sequence/record identity và shard lineage mà worker có thể tái tạo khi restart.

### Shard splitting/resharding

Một stream có thể có shards mới và quan hệ parent/child. Worker cần tôn trọng ordering/lineage contract của API, xử lý checkpoint per shard và không áp record của child theo cách vi phạm các bảo đảm thứ tự được thiết kế.

### Retention có giới hạn

Không được coi stream là backup vĩnh viễn. Nếu worker dừng quá hạn còn records, có thể cần rescan từ DynamoDB table/source, rebuild projection hoặc dữ liệu phục hồi khác. Khi rebuild, phải giải quyết cập nhật xảy ra trong lúc scan và ranh giới chuyển sang stream.

### Lambda event source mapping

Nếu dùng AWS Lambda để đọc stream, *batch success/failure handling* và retry semantics phụ thuộc event source mapping và cấu hình. Không lấy “function được gọi” làm bằng chứng batch đã được checkpoint. Với partial batch response, phải hiểu record nào có thể được replay theo API, không tự tính checkpoint bằng max successful sequence.

## 35. Redis Streams: `XACK` không giống `XDEL`

Redis Streams consumer groups là một mô hình khác với Kafka nhưng có câu hỏi ACK tương tự.

Ví dụ:

```redis
XGROUP CREATE order-stream search-workers 0 MKSTREAM
XREADGROUP GROUP search-workers consumer-1 COUNT 1 STREAMS order-stream >
```

Sau khi consumer nhận một entry, nó có thể nằm trong **Pending Entries List (PEL)** của group. Consumer cần áp effect vào NoSQL sink rồi mới ACK:

```redis
XACK order-stream search-workers 1699999999999-0
```

ID chỉ là ví dụ. `XACK` đánh dấu entry **đã được xử lý/ack bởi group** theo cơ chế Redis Streams; nó **không xóa entry khỏi stream**. `XDEL` là lệnh khác tác động vào dữ liệu stream.

### Crash windows

```text
Receive entry -> XACK -> crash before sink
    => entry no longer pending for this group; effect lost.

Receive entry -> sink commit -> crash before XACK
    => entry remains pending; can be claimed/replayed.
```

### Pending và claim

Trong trường hợp consumer chết, consumer khác có thể kiểm tra pending entries và claim/recover entries theo API phù hợp (ví dụ các cơ chế pending/auto-claim ở những phiên bản hỗ trợ). Cần retry/idempotency vì worker cũ có thể hồi phục.

### Retention/trimming

Stream trimming hoặc delete có thể xóa dữ liệu trước khi một group xử lý xong. PEL metadata và stream entries có quan hệ cần hiểu theo version/config. Không mặc định chỉ cần XACK sau đó là dữ liệu chắc còn để replay. Cần giới hạn retention, pending age và recovery policy.

### Redis durability/failover

Redis replication/persistence có cấu hình khác Kafka commit log. Một ACK sau primary write không nhất thiết chứng minh đã tồn tại bền qua mọi failover. Chọn durability contract đúng nếu stream là đường truyền sự kiện quan trọng.

## 36. Snapshot ban đầu và chuyển sang streaming mà không có lỗ hổng

Một consumer mới muốn xây search index từ toàn bộ 10 triệu orders. Nếu chỉ bắt đầu đọc CDC từ lúc start, những order cũ không có update sẽ không bao giờ xuất hiện. Cần **snapshot + stream**.

```text
T0: Start snapshot / establish log boundary
T1: Scan historical documents
T2: Concurrent writes continue at source
T3: Catch up changes during snapshot
T4: Finish snapshot, enter steady-state CDC
```

### Sai: scan xong mới bật CDC

```text
T0 scan begins
T1 order O1 updated while scan running
T2 scan finishes
T3 CDC subscription starts from "now"
```

Update tại T1 có thể không xuất hiện trong snapshot final lẫn CDC tail tùy scan semantics. Đây là **snapshot-to-stream gap**.

### Một chiến lược có ranh giới an toàn

1. Thiết lập nguồn log cursor/boundary có thể replay ở thời điểm phù hợp.
2. Snapshot dữ liệu theo consistency model được nguồn hỗ trợ.
3. Trong khi snapshot chạy, giữ các changes phát sinh sau boundary ở một log/buffer đủ bền.
4. Áp snapshot rows và changes với source revisions/ordering rules không làm state cũ đè state mới.
5. Checkpoint **snapshot progress** và **log position** theo giao thức cụ thể.
6. Chỉ tuyên bố “caught up” khi đã áp những thay đổi cần thiết qua ranh giới cutover.

### Không thể mô tả snapshot bằng một offset duy nhất

Checkpoint có thể là:

```json
{
  "phase": "SNAPSHOT",
  "collection": "orders",
  "lastScannedKey": "ORDER-4000000",
  "streamBoundary": "opaque-source-position",
  "targetSchemaVersion": 3
}
```

Đây là cấu trúc minh họa. Cách snapshot một MongoDB change stream, DynamoDB table và PostgreSQL table nhất quán khác nhau; dùng hỗ trợ của connector nếu có, không tự phát minh transaction toàn hệ.

## 37. Race giữa snapshot row và CDC update

Giả sử:

```text
Snapshot scan reads ORDER-1 revision 7.
CDC observes update to revision 8.
Sink applies CDC revision 8.
Snapshot worker later writes revision 7.
```

Nếu snapshot writer dùng blind upsert, projection lùi từ v8 về v7.

### Guard cần thiết

```text
applySnapshotRow(row):
  update only when row.revision > current.sourceRevision

applyCdcEvent(event):
  update only when event.revision > current.sourceRevision
```

Những điều kiện này phải được áp **atomically tại sink**. Nhưng với **delta-only events** có các phiên bản bắt buộc liên tiếp, chỉ chọn max revision chưa chắc đủ.

### Snapshot progress cũng cần durable

Nếu scan 9 triệu rows rồi crash trước khi ghi snapshot checkpoint, startup có thể quét lại nhiều rows. Điều đó an toàn hơn bỏ dữ liệu nếu sink updates idempotent, nhưng có thể rất tốn tài nguyên; nên lưu progress và có rate limits.

### Checkpoint “snapshot complete” quá sớm

Đánh dấu complete trước khi tất cả rows đã vào sink sẽ gây lỗ hổng: restart chuyển ngay sang CDC và bỏ các rows chưa từng scan. Chỉ đánh dấu phase transition khi điều kiện cutover được thỏa.

## 38. Một source transaction có thể phát nhiều events

Ví dụ transaction nguồn:

```text
TX-1001:
  Update order O1 -> PAID
  Insert payment ledger L1
  Insert outbox notification N1
COMMIT
```

Connector có thể phát nhiều records. Một consumer riêng có thể xử lý:

```text
order updated    -> sink committed
payment ledger   -> sink pending
notification     -> sink pending
```

Nếu read model cần một snapshot **nguyên tử của cả transaction**, checkpoint riêng từng record chưa đủ để cung cấp atomic visibility. Cần protocol nhận diện source transaction boundary, buffering/grouping hoặc sink transaction, trong phạm vi API được hỗ trợ.

### Không gộp transaction không rõ nguồn

Nếu connector mất transaction ID/boundary hoặc source khác nhau không cùng transaction authority, không thể tùy ý nhóm events theo timestamp rồi tuyên bố transactionally consistent.

### Một event nên là business fact hay row mutation?

CDC raw row mutation có thể thiếu ngữ cảnh business. Một **outbox event** có thể bao gồm transactionally committed business fact. Chọn loại event theo nhu cầu sink, không mặc định CDC update statement luôn có đủ ý nghĩa “thanh toán đã hoàn tất”.

## 39. Delete, tombstone và checkpoint của event xóa

Một NoSQL document bị xóa:

```text
Source: DELETE customer C01
CDC: CustomerDeleted event
Sink: remove/mark deleted in search
Checkpoint: advance only after durable handling
```

Nếu consumer checkpoint trước khi xóa index, khách đã bị xóa ở source có thể **vẫn tìm thấy lâu dài** trong search.

### Xóa vật lý khác xóa logic

Sink có thể lưu tombstone:

```json
{
  "tenantId": "T01",
  "customerId": "C01",
  "sourceRevision": 30,
  "deleted": true
}
```

Tombstone/version giúp ngăn một event `CustomerUpdated` cũ đến muộn làm dữ liệu hồi sinh.

### TTL tombstone và inbox

Nếu tombstone bị GC trước khi replay cũ có thể xảy ra, sink có thể resurrect deleted record. Retention phải phù hợp source log, broker log, DLQ redrive, restored snapshots và rejoin policy.

### Quyền riêng tư

Event delete có thể yêu cầu xóa cache/index/projection/backup theo chính sách; checkpoint một consumer không có nghĩa mọi bản sao vật lý đã được xóa. Mỗi downstream cần trạng thái hoàn tất và audit trong phạm vi của nó.

## 40. Schema evolution và checkpoint khi gặp event không đọc được

Một CDC event có thể chứa:

```json
{
  "eventType": "OrderPaid",
  "eventSchema": 4,
  "payload": {
    "amountMinorUnits": 500000,
    "currency": "VND"
  }
}
```

Consumer chỉ hiểu schema 3. Nếu đọc đến offset 104 rồi commit 105 trước khi decode, event 104 có thể bị bỏ mà không ai nhận ra.

### Chính sách rõ

- **Backward/forward compatibility:** decoder đọc được schema mới theo hợp đồng.
- **Pause & upgrade:** giữ checkpoint, triển khai reader mới, replay.
- **Quarantine/DLQ:** lưu event bền ở đường xử lý riêng rồi cho consumer chính tiến, nếu nghiệp vụ cho phép.
- **Fail closed:** với event bảo mật/tài chính không được đoán field hoặc default sai.

### Schema registry không làm business policy biến mất

Một registry giúp quản lý schemas/compatibility; nó không tự xác định “field total đổi từ đồng sang minorUnits thì default giá trị nào an toàn”. Cần cả semantic version và migration plan.

### Checkpoint nên chứa version gì?

Checkpoint source không cần tự mang toàn bộ schema của mỗi message, nhưng các trạng thái snapshot/connector có thể cần **schema history/serialization version** để resume. Một checkpoint không thể giải mã sau deploy có thể chặn recovery; cần migration hoặc giữ decoder cũ có kiểm soát.

## 41. Định nghĩa “xử lý thành công” theo từng consumer

Một event `OrderPaid` có thể có ba subscribers:

```text
                   OrderPaid
                      |
       +--------------+--------------+
       |              |              |
       v              v              v
   Search index     Email service   Analytics
   update index     schedule mail   aggregate view
```

Các subscribers không nhất thiết cùng định nghĩa thành công:

| Subscriber | Hành động được xem là thành công trước checkpoint | Việc còn lại |
|---|---|---|
| Search indexer | Search mutation được xác nhận bền theo sink contract hoặc durable intent được ghi | Có thể còn refresh lag |
| Email orchestrator | Durable notification job/outbox được ghi | Provider gửi email và nhận trạng thái sau |
| Analytics aggregator | Event đã được áp vào aggregate + dedup ledger atomically | Downstream dashboard refresh |
| Billing projector | Ledger/projection transaction commit | Audit/reconciliation ngoài phạm vi nếu có |
| Audit archiver | Object/batch được ghi bền theo storage contract | Index/search archiving, retention policy |

Nếu subscriber chỉ có trách nhiệm **tạo durable intent** để worker khác xử lý, checkpoint sau durable intent là hợp lý. Nhưng API/report phải nói “job accepted”, không tuyên bố “email đã gửi”.

### Một state machine gợi ý

```text
RECEIVED
    |
    v
VALIDATED
    |
    v
APPLYING -----> RETRYABLE_ERROR ------> RETRYING
    |                                      |
    |                                      +----> APPLYING
    v
APPLIED_DURABLE
    |
    v
CHECKPOINT_PENDING
    |
    +--> CHECKPOINT_COMMITTED

Permanent failure -> QUARANTINED/DLQ (durable alternative)
Unknown sink outcome -> RECONCILIATION_REQUIRED
```

Không phải mọi project cần lưu state trên cho từng delivery. Nhưng **mô hình hóa rõ** giúp đặt checkpoint đúng và phân loại metrics.

## 42. Checkpoint store cũng có thể mất hoặc trả timeout

Giả sử sink đã cập nhật đơn v8, consumer gọi `commitSync(offset=105)` nhưng broker/network timeout. Hai thế giới:

**A — Checkpoint thực sự chưa được ghi:**

```text
Sink v8 exists
Committed offset remains 104
Restart -> reprocess 104
```

**B — Checkpoint đã được ghi nhưng response mất:**

```text
Sink v8 exists
Committed offset is 105
Caller sees timeout
Restart -> 105
```

Ứng dụng không thể từ timeout xác định A/B. Thường không cần biết để tránh dữ liệu sai **nếu effect idempotent và retry/restart được quản lý**.

### Không tự tăng offset thêm lần nữa

Nếu commit 105 mơ hồ, không có nghĩa “thử 106 cho chắc”. Offset 106 sẽ bỏ record 105 nếu chưa xử lý.

### Không để commit callback cũ ghi lùi checkpoint

Với async commits, responses/callbacks có thể đến không theo thứ tự kỳ vọng; một retry của commit offset thấp có thể gây lỗi progression nếu thiếu quản lý. Thiết kế cần **monotonic checkpoint per partition/ownership generation** và tránh phát commits cạnh tranh không kiểm soát.

### Khi checkpoint store phân vùng

Đừng để consumer vừa đánh dấu event là done trong RAM, vừa tiếp tục xử lý không giới hạn nếu không ghi được checkpoint và retention sắp hết. Có thể dừng/pause intake, báo degraded, giữ buffer giới hạn và retry có backoff.

## 43. Idempotency key và retention khi replay

Một event identity có thể cần:

```text
subscriberId
sourceSystemId
tenantId
eventId
```

Nếu cùng `eventId=42` xuất hiện ở hai source clusters khác nhau, dedup chỉ bằng `42` có thể xóa nhầm một event hợp lệ. Nếu một event được republish sang topic mới, business eventId nên giữ ổn định để những subscribers cần dedup có thể nhận biết.

### Kafka offset không luôn là business ID

Một relay có thể publish lại cùng event tại:

```text
first publish:  topic A, partition 0, offset 104
second publish: topic A, partition 0, offset 109
``

Hai Kafka offsets khác nhau nhưng **cùng logical event**.

### Một event có thể được phép xử lý lại có chủ đích

Ví dụ rebuild search index bằng replay cũ:

```text
same eventId EV-9081
subscriberId = search-indexer-v2
```

Nếu dùng cùng inbox ledger `search-indexer-v1`, replay có thể bị coi là duplicate và không xây lại index mới. Do đó event dedup scope đôi khi cần **sink generation/rebuild ID**. Nhưng cấp generation mới cho một **payment effect** có thể gây charge lại; không được áp pattern rebuild một cách máy móc cho nghiệp vụ tài chính.

### Retention

Một ledger giữ eventId 7 ngày nhưng DLQ có thể redrive sau 30 ngày là chưa đủ nếu effect không idempotent. Chọn retention dựa trên **cửa sổ replay thực tế**, không chỉ broker retention.

## 44. Checkpoint và sink không cùng authority: các lựa chọn thực tế

| Kiến trúc | Điểm mạnh | Cửa sổ rủi ro |
|---|---|---|
| Sink commit → Kafka offset commit | Dễ triển khai, at-least-once | Replay sau sink commit |
| Kafka offset commit → sink commit | Có thể giảm replay | **Mất effect** sau crash |
| Inbox + sink effect trong cùng DB transaction → offset commit | Duplicate không làm lặp effect trong phạm vi DB | Offset có thể replay, cần retention |
| Sink effect + sink checkpoint trong cùng transaction | Một commit point tại sink | Rebalance/fencing, source log retention |
| Kafka transaction output + Kafka input offsets | Atomic trong Kafka boundary | External DB/API không tự nằm trong transaction |
| Durable outbox job → checkpoint → external worker | Giảm coupling, phân chia trách nhiệm | External job cần retry/idempotency/status |
| Idempotent full-state projection by revision | Dễ replay/out-of-order một số event | Không phù hợp delta/gaps nếu không repair |

Chọn theo invariant và authority. Một hệ có thể phối hợp nhiều pattern: transactional outbox ở source, Kafka log ở giữa, transactional inbox ở sink và reconciliation với payment provider.

### Không đòi “một transaction giữa mọi thứ” bằng cách vô tình khóa toàn hệ

Distributed transactions đa hệ có chi phí và giới hạn; không phải mọi service/NoSQL engine tham gia được. Một workflow bền với state machine, idempotency và compensation có thể là cách đúng nếu một atomic commit toàn phần không khả thi.

## 45. Checkpoint, visibility và tính nhất quán của projection

Giả sử sink là Elasticsearch/OpenSearch:

```text
T0 index update accepted
T1 consumer commits offset
T2 search query still returns old result
T3 refresh makes new result visible
``

Không nhất thiết có bug: **write acceptance** và **search visibility** có semantics khác. Nếu consumer gọi thành công ở T0 và commit checkpoint, read model có thể bị trễ cho đến refresh.

### Định nghĩa contract

- Nếu mục tiêu “event đã được search engine chấp nhận bền”, ACK sau response/write contract phù hợp.
- Nếu mục tiêu “ngay lập tức truy vấn phải thấy”, cần refresh/read-after-write strategy theo API, với chi phí hiệu năng, hoặc đọc từ authoritative source.
- Nếu mục tiêu “mọi dashboard đều đã cập nhật”, còn nhiều sinks/replicas phía sau; một consumer checkpoint không chứng minh cả pipeline.

### Đặt tên metrics

Không dùng một metric `processed_total` duy nhất cho mọi giai đoạn. Có thể tách:

```text
events_fetched_total
events_sink_applied_total
events_checkpoint_committed_total
events_projection_visible_total (if measurable)
``

## 46. Latency và throughput khi commit checkpoint

Commit offset sau mỗi event rất dễ lý luận nhưng có overhead. Batch commit tăng throughput, đổi lại số events replay sau crash có thể lớn hơn.

Ví dụ:

```text
Rate: 1,000 events/s
Checkpoint every 10 s
Potential replay window from checkpoint lag: about 10,000 events
``

Con số là **ước lượng trong workload ổn định**, không phải SLA; event size, partition throughput, batch boundaries và crash timing ảnh hưởng thực tế.

### Hai chiều tối ưu

1. **Hiệu năng:** giảm số lần commit qua batching.
2. **Phục hồi:** giảm amount of replay, độ trễ catch-up và tài nguyên sink.

Nếu handler idempotent và sink đủ capacity, replay vài nghìn events có thể chấp nhận. Nếu mỗi event gọi provider với chi phí cao, cần durable workflow khác trước khi tăng batch.

### Commit quá thường xuyên

- Tăng request load lên broker/offset store.
- Tăng network overhead và p99.
- Có thể tạo contention khi nhiều consumers.

### Commit quá thưa

- Tăng replay khi crash/rebalance.
- Tăng thời gian phục hồi.
- Tăng nguy cơ hết retention khi tiến độ đứng.

### Chính sách kết hợp

Có thể commit khi:

- Đã áp thành công N events **liên tục**.
- Hoặc đã qua T giây.
- Hoặc trước revoke/shutdown khi còn ownership.

Các mốc không được vượt incomplete offsets và phải giữ bounded in-flight state.

## 47. Observability: đo lag theo đúng tầng

Một dashboard có thể chia:

### Source → connector

- Thời điểm/position source mutation đã commit.
- CDC connector last-read source position.
- Connector safely checkpointed/published source position.
- Source WAL/oplog/stream retention headroom.
- Snapshot progress/phase.
- Connector error/restart count.

### Connector → broker

- Produce ACK latency/errors.
- Broker topic partition end offsets.
- Backlog event age.
- Duplicate publish/retry attempts.

### Broker → consumer

- Committed offset per topic-partition.
- Last fetched position.
- Last durably applied position.
- Contiguous completion watermark (offset-based, khác event-time watermark).
- Consumer lag (records and time).
- Poll/rebalance frequency.

### Consumer → sink

- Sink write latency/error.
- Inbox dedup hits.
- Unknown sink commit outcomes.
- Version conflict/stale events ignored.
- DLQ/quarantine backlog.
- Projection/read visibility lag.

### Ops

- OOM/restart events.
- Checkpoint store failures.
- Worker lease/fencing rejects.
- Redrive duration.
- Time to rebuild projection.

Tên metric thực tế phụ thuộc Kafka exporter, MongoDB/Redis/driver, connector, infrastructure. **Không đo lag toàn hệ bằng một số Kafka offset duy nhất**.

## 48. Phân biệt ba loại lag

### Record/offset lag

\[
\mathrm{lagRecords}_p =
\mathrm{endOffset}_p-\mathrm{committedOffset}_p
\]

Đây là công thức minh họa khi dùng offsets của **cùng partition và cùng semantics**. Nó nói có bao nhiêu vị trí log chưa được consumer checkpoint, không trực tiếp nói data staleness theo thời gian.

### Processing-time lag

```text
now - time when event was durably applied
``

Cần hiểu clock skew, queue delays, retries và event timestamp nguồn. Một event không có timestamp tin cậy sẽ khó suy lag chính xác.

### End-to-end freshness lag

```text
source commit time -> query-visible sink state time
``

Đây thường là metric business quan tâm nhất: user cần search thấy đơn PAID sau bao lâu? Muốn đo, phải có source revision/timestamp được xác minh và probe/read visibility, không chỉ broker checkpoint.

### Ví dụ

```text
Kafka lag = 0
Search visibility lag = 2 seconds
``

Hai số này có thể cùng đúng vì index refresh hoặc cache stale.

## 49. Runbook: consumer bị kẹt tại một offset

### Bước 1 — Xác định identity

Ghi:

```text
consumerGroup
topic / partition / offset
eventId / aggregateId / revision
source connector and source position
sink target and deployment version
``

Tránh log PII, credentials hoặc full event payload nhạy cảm nếu không có quyền và quy trình bảo vệ.

### Bước 2 — Xem record có thực sự còn trong log

Xác nhận earliest/latest offsets, retention gap, topic recreation/repartition. Nếu data không còn, không cứ retry vô hạn.

### Bước 3 — Phân loại nguyên nhân dừng

- Sink unavailable.
- Poison event/schema incompatibility.
- Deadlock/long transaction.
- Retry storm/rate limit.
- Group rebalances.
- Offset store errors.
- Worker đã apply effect nhưng chưa commit offset.

### Bước 4 — Xác minh business effect tại authority

Đọc inbox/event ledger, projection revision, transaction result hoặc provider reference. **Không kết luận từ consumer log “handler started” rằng effect đã thành công.**

### Bước 5 — Chọn recovery

- Retry cùng eventId khi idempotent.
- Pause và deploy schema fix.
- Reconcile unknown commit.
- Đưa vào DLQ một cách bền nếu policy cho phép.
- Rebuild snapshot khi log gap không thể replay.

### Bước 6 — Không nâng offset mù

Một lệnh admin thay đổi offset có thể bỏ hàng nghìn events. Chỉ dùng với **change ticket, audit, snapshot/repair plan và xác nhận phạm vi**. Đối với sự kiện tiền/quyền/audit, cần chứng minh tác động trước khi skip.

### Bước 7 — Quan sát sau sửa

Theo dõi lag giảm, DLQ/inbox, source retention headroom, sink revision đúng và không xuất hiện duplicate business effect.

## 50. Runbook: có duplicate effect nhưng checkpoint đúng

Giả sử report phát hiện hai email hoặc hai lần tăng counter cùng `eventId`.

### Timeline điều tra

```text
Event published
Worker A sink commit
Worker A crash before checkpoint
Worker B reprocess
Worker B sink commit
Checkpoint advances
``

Đây có thể là consumer at-least-once hoạt động đúng về delivery nhưng **sink thiếu idempotency**.

### Sửa nguyên nhân

- Xem eventId có giữ nguyên qua republish hay không.
- Kiểm tra inbox claim có atomic với side effect không.
- Kiểm tra consumer group rebalance có worker cũ đang chạy không.
- Kiểm tra ledger TTL có ngắn hơn replay window không.
- Kiểm tra exception handler có retry external API bằng ID mới không.
- Với counter, xem retry đã increment hai lần hay chỉ analytics aggregation trùng.

### Xử lý hậu quả

Nếu có double charge, phải theo payment/refund workflow và audit; không đơn giản xóa một record log để “sửa count”. Với search projection, có thể rebuild từ source; với email đã gửi, không thể thu hồi lại theo DB rollback.

### Kết luận nghiệp vụ

Checkpoint đúng không tự chứng minh business exactly-once. Hệ có thể checkpoint an toàn **sau hai lần side effect** nếu handler không idempotent.

## 51. Checkpoint bảo vệ gì khi disaster recovery?

Sau khi mất cả cụm sink, recovery có thể có:

- Backup sink tại thời điểm B.
- CDC/broker log còn giữ events sau B.
- Consumer checkpoint tại thời điểm C, với C tiến xa hơn B.

Nếu restore sink về B nhưng tiếp tục consumer từ checkpoint C:

```text
Sink restored before events B..C
Consumer starts after C
=> missing effects in rebuilt sink
``

### Phải phối hợp source of truth

Các lựa chọn:

1. Restore **sink và checkpoint cùng một consistent backup**.
2. Rewind/replay từ mốc sớm hơn backup sink và dựa vào idempotent handlers.
3. Rebuild sink từ authoritative source snapshot + CDC.
4. Dùng replay generation mới có inbox scope riêng khi phù hợp với projection, nhưng tránh lặp external effects.

### RPO/RTO

- **RPO:** tối đa bao nhiêu dữ liệu hoặc sự kiện có thể bị mất sau disaster theo architecture/retention.
- **RTO:** cần bao lâu để phục hồi service/read model về trạng thái sử dụng được.

Checkpoint chỉ góp phần vào hai mục tiêu; retention, backup consistency, replication, replay capacity và downstream side effects cũng quan trọng.

### Không sao chép checkpoint vào môi trường khác một cách tùy ý

Topic/stream identity, partition layout, incarnation, source cluster ID và sink snapshot phải tương thích. Một số offset được restore sang topic đã recreate có thể chỉ vào vị trí khác hoặc không còn tồn tại.

## 52. Kế hoạch fault injection: đặt lỗi vào các cửa sổ nguy hiểm

Thử trong **lab/staging với dữ liệu giả**, không cố ý làm mất mạng hoặc xóa logs production.

| Thời điểm chèn lỗi | Kỳ vọng nếu thiết kế đúng | Điều cần quan sát |
|---|---|---|
| Sau `poll`, trước sink write | Event được replay | Offset chưa tiến |
| Sau commit offset, trước sink write (anti-pattern) | Test lộ mất effect | Projection thiếu record |
| Sau sink commit, trước offset commit | Replay không nhân đôi effect | Inbox duplicate / revision guard |
| Mất response sink commit | Reconcile unknown state | Không tạo effect mới bằng ID khác |
| Mất response offset commit | Có thể replay; vẫn an toàn | Ledger nhận diện duplicate |
| Sau source log read, trước broker ACK | Connector đọc lại/publish lại an toàn | Source checkpoint chưa qua record |
| Sau broker ACK, trước source checkpoint | Có thể duplicate publish | Stable event identity |
| Consumer rebalance trong async processing | Owner cũ bị fence hoặc side effect idempotent | Generation/lease logs |
| Offset 12 còn pending, 13-15 done | Không commit quá 12 | Contiguous progress |
| Consumer mất kết nối lâu hơn retention | Báo recovery gap rõ | Không silently reset latest |
| Mongo resume token hết lịch sử | Resnapshot/rebuild theo policy | Error không bị nuốt |
| CDC snapshot và update đồng thời | Source revision mới không bị snapshot cũ đè | Projection revision |
| Out-of-order delete/update | Deleted state không hồi sinh | Tombstone/version guard |
| Kafka batch partial failure | Không skip failed record | Per-item status, checkpoint |
| DLQ publish timeout | Chưa commit input offset | Event không mất |
| Search write ACK trước refresh | Status processed và visible phân biệt | Read visibility lag |
| Restore sink backup cũ + offset mới | Detect/replay gap | Consistent restore |
| Inbox ledger TTL trước redrive | Test phát hiện duplicate | Retention policy |
| Provider ACK mất sau charge | Không charge lại bằng ID mới | Provider reference/status |
| Source WAL backlog tăng | Alert trước hết disk | WAL/slot headroom |

### Điều kiện đánh giá

Một test không chỉ hỏi “consumer có restart không”. Nó cần xác minh:

1. Record không bị bỏ ngoài policy đã công bố.
2. Những replay không tạo duplicate business effect vượt contract.
3. Checkpoint phản ánh **đoạn liên tục đã xử lý bền**.
4. Poison messages không gây bỏ dữ liệu âm thầm.
5. Source/broker retention còn đủ cho recovery.
6. Read model đạt correctness và freshness như đã hứa.
7. Worker cũ không được commit sai khi ownership thay đổi.

## 53. Lab nhỏ: tính checkpoint cho một batch song song

Giả sử source đang có một partition:

```text
Committed offset initially: 20
Delivered offsets: 20,21,22,23,24,25
```

Workers lần lượt hoàn tất:

```text
Time T1: 20 complete
Time T2: 23 complete
Time T3: 22 complete
Time T4: 24 complete
Time T5: 21 complete
Time T6: 25 complete
``

Đoạn đã hoàn tất liên tục:

| Thời điểm | Completed set | Next committable offset |
|---|---|---|
| Bắt đầu | rỗng | 20 |
| T1 | {20} | 21 |
| T2 | {20,23} | 21 |
| T3 | {20,22,23} | 21 |
| T4 | {20,22,23,24} | 21 |
| T5 | {20,21,22,23,24} | 25 |
| T6 | {20,21,22,23,24,25} | 26 |

Không được commit 24 tại T2 chỉ vì offset 23 hoàn tất; điều đó bỏ qua offsets 21/22. Nếu crash ở T4, có thể replay từ 21 và handler phải nhận ra 22/23/24 đã được áp vào sink hoặc đã được lưu trong inbox.

### Biến thể: offset 21 đi vào DLQ

Nếu event 21 vĩnh viễn malformed, chính sách cho phép **durable quarantine** trước khi coi 21 hoàn tất đối với consumer chính:

```text
21 -> DLQ durable ACK
22..24 -> sink effects already durable
next checkpoint -> 25
``

Điều kiện là DLQ có owner, retention, redrive plan và audit rõ. Nếu 22..24 phụ thuộc vào effect của 21, việc tiến tiếp không còn đúng dù checkpoint kỹ thuật có thể tiến.

## 54. Lab Java 17: mô phỏng crash giữa effect và checkpoint

Mục đích là phân biệt **business effect** với **committed offset** mà không cần cụm Kafka thật. Ví dụ này chỉ mô phỏng trong bộ nhớ; không có durability thật và không được dùng làm bằng chứng production.

```java
import java.util.HashSet;
import java.util.Set;

record Event(long offset, String eventId, int amount) {}

final class SimulatedSink {
    private final Set<String> inbox = new HashSet<>();
    private long total = 0;

    void applyIdempotently(Event event) {
        if (!inbox.add(event.eventId())) {
            return; // duplicate logical event
        }
        total += event.amount();
    }

    long total() {
        return total;
    }
}

public final class CheckpointCrashDemo {
    public static void main(String[] args) {
        SimulatedSink sink = new SimulatedSink();
        Event event = new Event(104L, "EV-104", 10);

        long committedNextOffset = 104L;

        // First process attempt:
        sink.applyIdempotently(event);

        // SIMULATED CRASH: committedNextOffset not advanced.

        // Restart from committed offset 104:
        sink.applyIdempotently(event);
        committedNextOffset = 105L;

        System.out.println("total=" + sink.total()); // 10
        System.out.println(
            "nextOffset=" + committedNextOffset);    // 105
    }
}
```

### Vì sao ví dụ chỉ có ý nghĩa minh họa?

`HashSet` và `long total` cùng ở RAM, nên nếu process thực sự crash, chúng cũng biến mất; production cần inbox và effect **cùng được commit bền trong một transaction/atomic operation** hoặc một protocol tương đương. Dùng synchronized/lock ở JVM cũng không thay được transaction NoSQL trên nhiều workers.

### Biến thể gây lỗi có chủ đích

Bỏ inbox dedup, tăng `total` trực tiếp hai lần; kết quả sẽ là 20. Đây chính là rủi ro khi **sink effect commit xong nhưng checkpoint chưa commit**, rồi event được replay.

## 55. Hai mươi bài tập thực hành

### Bài 1 — Vẽ timeline chính xác

Source DB commit OrderPaid, CDC connector đọc, Kafka append, consumer poll, MongoDB sink update, Kafka offset commit. Vẽ từng ACK và giải thích ACK nào không chứng minh bước sau đã thành công.

### Bài 2 — Offset kế tiếp

Consumer xử lý bền các Kafka offsets 91, 92, 93 của partition 2. Giá trị committed offset cần ghi là bao nhiêu? Nếu một lỗi khiến phải restart, bản ghi tiếp theo là gì?

### Bài 3 — Hai partitions

Partition 0 đã xử lý đến offset 200; partition 1 mới xử lý tới offset 15. Thiết kế checkpoint map. Vì sao dùng `max(200,15)` cho cả topic là sai?

### Bài 4 — Commit trước effect

Consumer commit offset 105 rồi crash trước khi ghi NoSQL sink cho event 104. Phân tích hậu quả và lựa chọn phục hồi nếu source log vẫn còn.

### Bài 5 — Effect trước checkpoint

Consumer ghi counter +1 thành công rồi crash trước khi commit offset. Nếu event được replay, điều gì xảy ra? Đề xuất inbox transaction/operation ID.

### Bài 6 — Unknown sink result

MongoDB transaction đã commit nhưng ACK bị mất. Handler muốn retry bằng cách insert một document mới với ID khác. Vì sao nguy hiểm? Làm sao xác minh ledger theo eventId?

### Bài 7 — Inbox claim race

Hai workers cùng đọc `processedEvents` chưa thấy eventId, sau đó cùng increment counter. Viết lịch sử gây duplicate. Dùng unique constraint và atomic effect+claim sửa thế nào?

### Bài 8 — Revision guard

Search projection đang ở Order revision 9; event revision 8 tới muộn. Nếu event là full-state replacement, nên xử lý thế nào? Nếu event là delta-only, tại sao bài toán phức tạp hơn?

### Bài 9 — Kafka transaction boundary

Một ứng dụng consume Kafka, produce Kafka output và gọi Redis `INCR`. Kafka transaction bảo đảm atomic những thao tác nào? Còn Redis phải làm gì để không tăng trùng?

### Bài 10 — Transactional outbox

Một service update order thành PAID rồi publish event. Crash trước publish. Thiết kế outbox sao cho business write và publish intent không bị lệch.

### Bài 11 — Batch partial failure

Batch 100..105: 100/101/102 thành công, 103 lỗi, 104/105 chưa xử lý. Consumer được commit đến offset nào? Nếu 104/105 đã hoàn tất out-of-order thì sao?

### Bài 12 — Async processing và rebalance

Consumer A giao offset 104 cho worker W, sau đó partition được chuyển sang B. W hồi phục và định ghi sink. Cần generation/fencing hoặc idempotency ở đâu?

### Bài 13 — Redis Streams

Consumer group nhận message qua `XREADGROUP`, ACK ngay trước khi update MongoDB. Nếu crash sẽ ra sao? Phân biệt `XACK` và `XDEL`.

### Bài 14 — MongoDB resume token

Một CDC relay ghi resume token T sau khi đọc change event nhưng trước khi Kafka ACK. Khi crash, có thể mất gì? Thứ tự checkpoint an toàn hơn là gì?

### Bài 15 — PostgreSQL WAL retention

Connector bị lỗi publish vào broker và không advance logical replication position trong nhiều giờ. Rủi ro nào xuất hiện ở source database? Cần theo dõi metric gì?

### Bài 16 — Snapshot cutover

Một job quét toàn bộ source xong rồi mới bắt đầu CDC từ “now”. Có những update nào có thể lọt khỏi cả snapshot và CDC? Hãy thiết kế snapshot boundary + log catch-up.

### Bài 17 — DynamoDB Streams

Một stream có hai shards và một shard bị split. Vì sao checkpoint chỉ một `long` toàn stream không đủ? Khi một shard lag, shard còn lại có thể tiến checkpoint riêng không?

### Bài 18 — DLQ

Offset 103 là event schema không hỗ trợ; 104/105 là events hợp lệ. Khi nào có thể commit qua 103 sau khi gửi DLQ? Vì sao phải xem 104/105 có phụ thuộc event 103 không?

### Bài 19 — Disaster recovery

Sink được restore từ backup version v7 nhưng Kafka committed offset đã vượt các event đưa sink lên v9. Nếu cứ tiếp tục từ offset hiện tại, chuyện gì xảy ra? Đề xuất replay/rebuild.

### Bài 20 — Thiết kế end-to-end

Tạo sơ đồ `MongoDB source -> CDC -> Kafka -> Java consumer -> NoSQL search projection`. Xác định source token, Kafka offsets, consumer checkpoint, inbox/eventId, entity revision, DLQ, snapshot boundary, retention SLO và fault injection tương ứng. Nêu chính xác **thời điểm ACK được phép phát ra ở từng tầng**.

## 56. Checklist triển khai CDC/consumer

1. **Source position là gì?** Kafka offset, Mongo resume token, WAL LSN, stream shard sequence hay connector-specific tuple?
2. **Checkpoint mang identity đầy đủ chưa?** Cluster/stream/topic/partition/group/generation/snapshot phase?
3. **Committed offset được hiểu là bản ghi tiếp theo chưa?**
4. **Đã phân biệt fetched position và durably applied position chưa?**
5. **Có commit offset trước khi sink effect bền không?** Nếu có, mất event có được chấp nhận trong contract?
6. **Side effect đã commit nhưng checkpoint chưa tiến có replay an toàn không?**
7. **EventId có ổn định qua publish retries và đủ scope tenant/source/subscriber không?**
8. **Inbox ledger và effect có nằm trong cùng atomicity boundary không?**
9. **Nếu có external provider, có idempotency key, status lookup và reconciliation không?**
10. **Handler có xử lý source revision, out-of-order và delta gaps đúng không?**
11. **Kafka transactions chỉ đang bảo vệ những thành phần thuộc Kafka boundary chứ?**
12. **Batch có check partial failures và contiguous completion per partition không?**
13. **Async worker có giới hạn in-flight và không dùng max completed offset làm checkpoint không?**
14. **Rebalance có revoke handoff, generation fencing và cleanup đúng không?**
15. **Consumer loop không bị auto-commit vượt các effects đang chạy chứ?**
16. **Poison event có bounded retry, quarantine/DLQ durable và owner xử lý không?**
17. **Commit input offset chỉ xảy ra sau khi alternative durable handling thành công không?**
18. **Inbox/tombstone retention có đủ cho source/broker/DLQ replay window không?**
19. **Snapshot + CDC có cutover không để mất updates không?**
20. **Source WAL/oplog/stream retention headroom có được monitor không?**
21. **Resume token hết lịch sử có tạo recovery-required thay vì silently skip không?**
22. **Sink visibility và processed status có được phân biệt theo contract không?**
23. **Metrics có phân tầng source lag, broker lag, consumer lag và end-to-end freshness không?**
24. **Backup sink và checkpoint được restore nhất quán hoặc có replay plan không?**
25. **Đã test crash ngay sau sink commit và ngay trước/ sau checkpoint commit chưa?**
26. **Đã test duplicate publish, out-of-order events, failover, rebalance, DLQ, expired retention chưa?**
27. **Có runbook kiểm tra effect tại authority trước khi tua offset thủ công không?**
28. **Có data privacy/audit controls cho event logs, payload và checkpoint metadata không?**

## 57. Kết luận

Trong **Sự kiện và CDC**, checkpoint không phải một con số thể hiện “mọi thứ đã xong”. Nó là **lời hứa khôi phục tại một ranh giới cụ thể**: từ đâu một process có thể bắt đầu đọc lại mà vẫn thỏa hợp đồng xử lý của mình.

Những nguyên tắc cốt lõi:

1. **Một pipeline có nhiều checkpoints.** Source position, broker offset, consumer group offset và sink progress là những khái niệm độc lập.
2. **Offset thường thuộc partition/shard.** Không dùng số lớn nhất trên toàn topic hoặc một timestamp làm checkpoint chung.
3. **Commit offset sau effect bền giúp tránh mất event**, nhưng có thể replay nếu crash trước commit checkpoint. Đây là một đặc trưng của at-least-once.
4. **Không commit vượt lỗ hổng chưa hoàn tất.** Khi xử lý async/batch, chỉ xác nhận contiguous completed prefix theo từng partition.
5. **Idempotency là phần còn thiếu giữa replay và business correctness.** Inbox ledger, atomic conditional updates, source revision và provider idempotency giúp chống duplicate effect.
6. **Exactly-once phải có phạm vi rõ.** Kafka transaction có thể gắn output Kafka và consumed offsets; không tự bao MongoDB, Redis hay email provider.
7. **Source CDC cần checkpoint ở điểm bàn giao bền.** Không advance Mongo resume token hoặc WAL position trước khi event được bảo tồn ở downstream theo contract.
8. **Snapshot và streaming cần cutover an toàn.** Scan lịch sử và tail changes phải không có lỗ hổng, và snapshot rows cũ không được đè events mới.
9. **Rebalance, retention, DLQ và disaster recovery là các phần của semantics.** Một consumer có thể đúng khi bình thường nhưng sai khi worker bị revoke, token hết hạn hoặc backup không đi cùng checkpoint.
10. **“Processed” cần được định nghĩa theo trách nhiệm subscriber.** Durable notification intent không phải email delivery; search ACK không chắc search visible; offset commit không chứng minh toàn hệ đã hội tụ.

Câu hỏi quyết định:

> **“Nếu tiến trình chết ngay sau khi side effect được commit nhưng ngay trước khi ghi checkpoint, hệ sẽ đọc lại event nào, có thực hiện thêm hiệu ứng nghiệp vụ nào không, và làm sao chứng minh điều đó bằng dữ liệu bền?”**

Nếu một kiến trúc trả lời được câu hỏi này cho **mọi ranh giới source → connector → broker → consumer → sink**, đồng thời có kế hoạch retention và replay hợp lệ, nó đã có nền tảng vững chắc để vận hành event/CDC đáng tin trong NoSQL.

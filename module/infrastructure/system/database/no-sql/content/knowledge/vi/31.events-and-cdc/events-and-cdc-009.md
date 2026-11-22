# Xử lý sự kiện đến muộn, đảo thứ tự và bản cập nhật trùng

Trong kiến trúc **Database No SQL** dựa trên **sự kiện (event-driven)** và **Change Data Capture (CDC)**, ứng dụng thường ghi dữ liệu nghiệp vụ vào nguồn có thẩm quyền, sau đó phát thay đổi cho các hệ khác: Search Index, Redis Cache, Materialized View, Analytics, Notification hay một service khác. Cơ chế này giảm phụ thuộc đồng bộ và mở rộng khả năng xử lý, nhưng không có nghĩa mọi event luôn tới đúng lúc, đúng thứ tự và đúng một lần.

Xét một Product:

~~~text
t0  Product v40: price=100000, status=ACTIVE
t1  Source commit v41: price=120000
t2  Source commit v42: status=INACTIVE

Consumer nhận:
    Event v42 trước
    Event v41 đến sau
    Event v41 được broker gửi lại một lần nữa
~~~

Nếu consumer chỉ làm `SET` theo event đến cuối cùng, Search có thể bị cập nhật ngược về thông tin cũ. Nếu event là `StockDecreased(amount=1)` và được xử lý hai lần, số lượng tồn kho trong read model có thể bị trừ thừa. Nếu event `ProductDeleted(v43)` đã xử lý rồi mà một bản `ProductUpdated(v40)` được replay, dữ liệu có thể **sống lại sau khi đã xóa**.

Bài này thuộc chương **Sự kiện và CDC** trong **Database No SQL**. Nội dung đi từ phân loại lỗi giao nhận, khái niệm ordering scope, định danh event và version, đến những thuật toán apply idempotent, version guard, inbox, tombstone, snapshot kết hợp CDC, event-time/watermark, Java consumers và các ví dụ MongoDB Change Streams, DynamoDB Streams, Redis Streams và Kafka.

**Nguyên tắc tổng quát:** Một event chỉ được tạo ra **tác động nghiệp vụ hợp lệ một lần theo định danh và thứ tự mà domain quy định**. Không suy rằng timestamp lớn hơn đồng nghĩa luôn mới hơn, hoặc broker gửi đúng một lần đồng nghĩa database đích chỉ thay đổi đúng một lần.

## 1. Vì sao sự kiện không đến theo thứ tự ta mong đợi?

Một đường đi đơn giản:

~~~mermaid
flowchart LR
    A["Write at source"] --> B["Outbox / CDC"]
    B --> C["Broker / Stream"]
    C --> D["Consumer"]
    D --> E["NoSQL projection"]
    D --> F["Search / Cache"]
~~~

Ở mỗi chặng đều có khả năng chậm hoặc lặp:

- Producer publish lại vì không thấy acknowledgment.
- Network mất kết nối và gửi retry.
- Broker giao event tới một consumer mới sau rebalance.
- Consumer xử lý thành công nhưng crash trước khi acknowledgment.
- Consumer xử lý song song nhiều messages.
- Một partition/shard xử lý nhanh hơn partition khác.
- Một event bị đưa vào DLQ rồi replay sau.
- Backfill/snapshot tạo bản ghi cũ trong khi live CDC đang chạy.
- Một region đồng bộ chậm hơn region khác.
- Clock skew khiến timestamp quan sát không phản ánh commit order.

Kết luận: **giao nhận (delivery)**, **áp dụng (apply)** và **trật tự nghiệp vụ (business order)** là ba vấn đề khác nhau.

## 2. Phân biệt late, out-of-order và duplicate

| Hiện tượng | Mô tả | Ví dụ |
|---|---|---|
| **Late event** | Event được quan sát muộn so với mốc thời gian hoặc cửa sổ xử lý quan tâm | Event có eventTime 09:55 đến lúc 10:20 |
| **Out-of-order delivery** | Hai event được nhận khác thứ tự kỳ vọng trong scope có thứ tự | Product v42 đến trước v41 |
| **Duplicate delivery** | Cùng logical event được nhận nhiều lần | EventId E123 xuất hiện hai lần |
| **Duplicate business command** | Hai requests cùng một ý định tạo các event/ID khác nhau | Client retry CreateOrder dùng requestId mới |
| **Missing event** | Event chưa tới hoặc không còn khả năng đọc từ retention | Nhận v43 khi chưa thấy v42 |
| **Replay** | Đọc lại event lịch sử có chủ đích hoặc do recovery | Rebuild projection từ offset cũ |
| **Concurrent conflicting updates** | Hai nguồn cùng sửa một entity mà không có thứ tự chung | Multi-region writers cùng update price |

Những trường hợp này có thể xuất hiện đồng thời nhưng **không dùng một giải pháp duy nhất**. Dedupe giải quyết bản trùng; version guard giúp chặn downgrade; gap recovery xử lý event thiếu; watermark giúp quyết định mức độ chấp nhận event-time trễ.

## 3. Event đến muộn khác event cũ

**Event đến muộn** có thể vẫn chứa thông tin hợp lệ chưa được hệ thống nhìn thấy. Ví dụ một đơn được thanh toán lúc 09:00 nhưng sự kiện đến lúc 11:00; báo cáo doanh thu của ngày vẫn phải tính khoản thanh toán ấy theo business event-time.

**Event cũ** theo version có thể không còn là trạng thái hiện tại. Ví dụ Product v40 đến sau v42. Nếu read model chỉ hiển thị tình trạng mới nhất, nó thường không được phép ghi v40 đè v42.

Vì vậy:

- **Current-state projection:** ưu tiên trạng thái đúng theo source version.
- **Historical event log:** lưu sự kiện theo identity và business time.
- **Windowed analytics:** xử lý late events theo watermark/allowed lateness.
- **Side-effect workflow:** deduplicate effect theo business operation ID.

Một hệ có thể **bỏ qua event v40 cho CurrentProduct**, đồng thời vẫn **ghi nhận event v40 trong audit history** nếu nó chưa từng được ingest.

## 4. Hai loại đồng hồ: event time và processing time

Một event có thể mang các mốc:

~~~json
{
  "eventId": "e-421",
  "aggregateId": "product-101",
  "aggregateVersion": 42,
  "eventTime": "2026-11-14T09:00:00Z",
  "sourceCommittedAt": "2026-11-14T09:00:01Z",
  "publishedAt": "2026-11-14T09:00:02Z"
}
~~~

Consumer có thể nhận lúc 09:10:00.

Phân biệt:

- **Event time:** thời gian nghiệp vụ ghi trong event.
- **Commit time:** thời gian nguồn đã chấp nhận thay đổi; semantics tùy engine.
- **Publish time:** lúc đưa event vào broker.
- **Ingest/processing time:** lúc consumer quan sát hoặc xử lý.
- **Apply time:** lúc projection đích commit effect.
- **Visibility time:** lúc read API nhìn thấy projection mới.

Các timestamp có thể được sinh từ những đồng hồ khác nhau. **Không so sánh timestamp như một total order toàn cục nếu giao thức không bảo đảm điều đó.**

## 5. Định dạng event envelope đáng tin cậy

Một mẫu:

~~~json
{
  "eventId": "evt-9d31",
  "eventType": "ProductStateChanged",
  "eventSchemaVersion": 2,
  "source": "CatalogService",
  "tenantId": "tenant-17",
  "aggregateType": "Product",
  "aggregateId": "product-101",
  "aggregateGeneration": 1,
  "aggregateVersion": 42,
  "occurredAt": "2026-11-14T09:00:00Z",
  "committedAt": "2026-11-14T09:00:01Z",
  "operationId": "cmd-8fa2",
  "payload": {
    "title": "Bàn phím cơ",
    "priceMinor": 120000,
    "status": "INACTIVE"
  }
}
~~~

Các trường có vai trò khác nhau:

| Trường | Vai trò chính |
|---|---|
| `eventId` | Phát hiện cùng logical event đã nhận trước |
| `operationId` | Gắn nhiều event với một business intent |
| `aggregateId` | Xác định entity và scope ordering |
| `aggregateVersion` | Thứ tự trạng thái của **cùng aggregate** |
| `aggregateGeneration` | Phân biệt entity xóa rồi tạo lại cùng ID |
| `eventSchemaVersion` | Phiên bản cấu trúc payload |
| `committedAt` | Quan sát thời gian commit nếu nguồn hỗ trợ |
| `eventTime`/`occurredAt` | Event-time analytics/domain |
| Broker offset/sequence | Vị trí trong một stream/partition cụ thể |

`eventId`, `aggregateVersion`, `schemaVersion` và broker offset **không thay thế nhau**.

## 6. Event ID cần ổn định qua retry

Nếu producer gửi event E nhưng không nhận acknowledgment, nó có thể gửi lại. Nếu lần gửi thứ hai tạo **eventId mới**, consumer không thể nhận biết hai messages là cùng một logical event chỉ bằng eventId.

Quy tắc:

~~~text
One source change -> one stable eventId
Retry publish     -> same eventId
Consumer replay   -> same eventId
```

Với transactional outbox, eventId nên được tạo **cùng bản ghi outbox**, lưu bền và giữ nguyên mỗi lần publisher retry.

Không dùng UUID mới mỗi lần Kafka producer callback chạy lại để đại diện cùng business fact.

## 7. Event ID và business operation ID

Một checkout có thể tạo:

~~~text
operationId = checkout-K100
events:
  OrderCreated(E101)
  InventoryReserved(E102)
  PaymentRequested(E103)
~~~

Đây là **ba logical events khác nhau** nhưng cùng business intent. Vì vậy:

- `eventId` dedupe từng event.
- `operationId` dedupe/tra trạng thái của business command.
- `aggregateVersion` bảo vệ thứ tự state change trên một aggregate.
- External payment cần idempotency key phù hợp với **payment intent**, không chỉ eventId bất kỳ.

**Message deduplication không tự ngăn hai lần CreateOrder từ client nếu chúng có eventIds khác nhau.**

## 8. Ordering chỉ có nghĩa trong một phạm vi

Có thể có trật tự:

- Theo một aggregate/entity.
- Theo một shard/partition.
- Theo một transaction log.
- Theo một broker partition.
- Theo một stream group/region.
- Theo một source process.
- Theo một global sequencer nếu thực sự có.

Ví dụ:

~~~text
Product A: v10 -> v11 -> v12
Product B: v50 -> v51
```

Không thể nói Product B v51 “mới hơn về nghiệp vụ” Product A v12. Version thường **local theo aggregate**.

Để tránh rối, trong mỗi consumer design hãy ghi:

~~~text
orderingKey = tenantId + aggregateType + aggregateId
orderingField = aggregateVersion
orderingGuarantee = monotonic per aggregate, single authoritative writer
```

Nếu có nhiều writers không qua cùng sequencer, cần conflict policy khác; một số integer version tự đặt không tự giải quyết concurrency.

## 9. Partition key góp phần giữ thứ tự

Trong broker có order theo partition, các event của cùng aggregate thường nên được xuất với **cùng partition key**.

~~~text
key = "tenant-17#product-101"
event v40 -> Partition P3
event v41 -> Partition P3
event v42 -> Partition P3
~~~

Một partition có thứ tự trong log, nhưng điều đó **không bảo đảm consumer apply theo thứ tự** nếu ứng dụng:

- Giao messages cho nhiều threads xử lý song song.
- Đưa một message lỗi qua retry queue rồi xử lý message tiếp.
- Rebalance/ack offset không đúng.
- Gộp nhiều nguồn/streams khác nhau.
- Replay snapshot đồng thời với live stream.

**Broker order là điều kiện thuận lợi, không tự là chứng minh thứ tự apply ở database đích.**

## 10. Broker offset không phải source version

Giả sử Kafka partition P2:

~~~text
offset=1000 -> Product A v11
offset=1001 -> Product B v51
offset=1002 -> Product A v12
~~~

Offset giúp consumer biết vị trí đọc **trong P2**, không phải version riêng của Product A/B. Nếu key đổi partition, offset giữa hai partitions không thể so để biết state mới hơn.

Tương tự, một CDC sequence number có thể chỉ so được trong một log/shard. Nếu muốn áp “latest state wins” theo entity, hãy dùng **thứ tự nguồn đã được xác nhận**, không lấy số offset tùy ý so với version.

## 11. Trạng thái đầy đủ khác sự kiện delta

Hai event payloads:

**State event:**

~~~json
{
  "eventType": "InventorySnapshot",
  "sku": "SKU-A",
  "version": 20,
  "available": 7
}
~~~

**Delta event:**

~~~json
{
  "eventType": "StockDecreased",
  "eventId": "dec-333",
  "sku": "SKU-A",
  "aggregateVersion": 20,
  "quantity": 2
}
~~~

Với **snapshot đầy đủ** mang version đáng tin, có thể áp version mới hơn và bỏ qua bản cũ cho current-state projection.

Với **delta**, event bị lặp sẽ làm giảm nhiều lần; event bị mất tạo state thiếu; đảo thứ tự có thể thay đổi kết quả nếu phép toán không giao hoán. Cần deduplication, gap detection và/hoặc rehydrate lại từ nguồn.

## 12. “Latest state wins” chỉ đúng cho một lớp use case

Ví dụ:

~~~text
Target ProductCard sourceVersion=42
Incoming ProductStateChanged v41
-> skip state update

Incoming ProductStateChanged v43
-> apply full state v43, với guard nguyên tử
~~~

Điều kiện:

1. Event thực sự mang **đầy đủ trạng thái các field thuộc projection** hoặc có thể tái dựng từ nguồn.
2. Version có thứ tự đáng tin trong scope.
3. Target áp version một cách nguyên tử.
4. Không có những side effects phải thực thi cho mọi event trung gian.
5. Delete/generation được xử lý riêng.

Nếu event chỉ mang patch, việc bỏ qua v42 rồi áp patch v43 có thể làm mất field đã đổi ở v42. Không áp latest-wins vô điều kiện cho mọi `updateDescription`.

## 13. Bảng quyết định theo loại event

| Loại event | Duplicate | Đảo thứ tự | Bị thiếu |
|---|---|---|---|
| Full snapshot state | Skip nếu version đã áp | Guard theo version/generation | Có thể áp snapshot mới nhất nếu đủ field |
| Partial patch | Dedup và kiểm version | Buffer/request snapshot hoặc replay đúng thứ tự | Không apply khi gap ảnh hưởng field |
| Increment/decrement | Dedup theo event ID và atomic effect | Phụ thuộc phép toán/invariant | Cần replay đủ contribution |
| Set membership add/remove | Dedupe và mô hình membership semantics | Cần ordering/CRDT phù hợp | Có thể sai membership |
| Payment/notification request | Dedupe theo operation intent | Dựa vào state machine | Không được mất side effect quan trọng |
| Analytics fact | Dedup fact/event ID | Có thể nhận trễ và cập nhật window | Phải backfill/correction nếu quá retention |
| Delete/tombstone | Idempotent delete versioned | Ngăn stale resurrection | Cần reconciliation/deletion manifest |

## 14. Version guard tại nơi ghi

Trường hợp:

~~~text
Target v40
Consumer A chuẩn bị apply v42, bị pause
Consumer B apply v43 thành công
Consumer A resume và apply v42
```

Một `if (targetVersion < incomingVersion)` trong RAM không đủ vì target có thể đổi sau lần đọc.

Cần **conditional write/CAS tại database đích**:

~~~text
if current.generation == incoming.generation:
    accept only if incoming.version > current.version
else:
    compare generation according to ownership policy
```

Với version bằng, kiểm tra payload hash/schema hoặc idempotency; không overwrite tùy tiện.

## 15. Mẫu apply một full-state event

Pseudocode:

~~~text
applyFullState(event):
    assertValidSchemaAndTenant(event)
    target = readProjection(event.key)

    if target missing:
        conditionalInsertIfAbsent(event)
        return

    if target.generation > event.generation:
        return STALE_GENERATION

    if same generation and target.sourceVersion > event.version:
        return STALE_EVENT

    if same generation and target.sourceVersion == event.version:
        if same canonicalDigest and schema:
            return DUPLICATE_OR_ALREADY_APPLIED
        return INTEGRITY_MISMATCH

    atomicCompareAndReplace(
        expectedTargetVersion=target.sourceVersion,
        expectedTargetGeneration=target.generation,
        incomingState=event.fullState,
        incomingVersion=event.version
    )
```

Nếu conditional replace không match, có thể consumer khác vừa thắng. Re-read và quyết định, không ghi đè với state cũ.

## 16. Không phải event nào cũng có `version`

Một CDC feed chỉ có:

~~~json
{
  "documentKey": { "_id": "p-101" },
  "updateDescription": {
    "updatedFields": { "status": "INACTIVE" }
  }
}
~~~

Nếu không có sourceVersion, consumer phải dựa vào ordering guarantee thực của stream và cơ chế replay/checkpoint, hoặc **re-read authoritative state** để xây full projection. Gắn `System.currentTimeMillis()` ở consumer rồi coi đó là source version là một thiết kế dễ sai.

Đối với aggregate quan trọng, thường nên lưu version tăng nguyên tử cùng source mutation, hoặc có một source log position có semantics đủ mạnh cho routing/application.

## 17. Phát hiện version gap

Đích có v40 nhưng event mới đến là v43.

~~~text
Target lastAppliedVersion=40
Incoming partial event version=43
Missing versions: 41,42
~~~

Nếu event là **patch**, đích có thể thiếu hai thay đổi cần thiết. Những cách xử lý:

- Buffer v43 có giới hạn và đợi v41/v42.
- Đọc events thiếu từ source log.
- Rehydrate full snapshot mới nhất từ source.
- Đánh dấu projection `NEEDS_REBUILD`.
- Đưa key vào reconciliation queue.
- Nếu không thể khôi phục, alert thay vì im lặng áp sai.

Nếu v43 là **full snapshot state tự chứa**, nhiều current-state views có thể áp thẳng v43, nhưng audit/history hoặc side effects cho v41/v42 vẫn là trách nhiệm riêng.

## 18. Đợi gap có thời hạn, không vô hạn

Một consumer nhận v43 nhưng thiếu v42. Nó có thể tạm giữ v43:

~~~text
pending[key] = { v43, firstSeenAt, attempts }
```

Rủi ro:

- v42 thật sự đã mất khỏi retention.
- Queue đọng làm RAM tăng.
- Một hot key bị block vô hạn.
- Consumer group partition bị tắc sau một poison message.

Cần:

- Timeout/recovery budget.
- Giới hạn pending bytes/entries mỗi key.
- Backpressure hoặc DLQ cho data không thể xử lý.
- Nguồn để request snapshot/replay.
- Alert gap duration.
- Rõ hậu quả khi bỏ qua gap.

Không thể bảo đảm mạnh bằng cách chỉ hy vọng các event thiếu sẽ đến sau.

## 19. Dedupe theo event ID

Một consumer có thể lưu:

~~~text
ProcessedEvent:
  consumerName
  eventId
  processedAt
  payloadDigest
~~~

Nếu cùng eventId xuất hiện lại, consumer biết nó đã xử lý.

Nhưng **thao tác check rồi ghi marker riêng biệt** có race:

~~~text
Worker A: eventId chưa thấy
Worker B: eventId chưa thấy
A thực hiện increment
B thực hiện increment
A ghi processed marker
B ghi processed marker
~~~

Với non-idempotent effect, marker và effect phải được bảo vệ **cùng transaction/atomic boundary** hoặc qua một cơ chế khác được chứng minh an toàn.

## 20. Inbox pattern

**Inbox** là một bảng/collection theo dõi event nào consumer đã chấp nhận xử lý.

Sơ đồ:

~~~mermaid
flowchart TD
    E["Incoming event E"] --> Tx["Begin DB transaction"]
    Tx --> I{"Inbox already contains E?"}
    I -->|"Yes"| N["Return already processed"]
    I -->|"No"| P["Insert inbox record"]
    P --> D["Apply domain/projection effect"]
    D --> C["Commit transaction"]
    C --> A["Acknowledge broker"]
    N --> A
~~~

Điều kiện: inbox và data effect phải nằm trong **một transaction có bảo đảm phù hợp**. Nếu source/destination khác database, cần outbox/idempotency/workflow khác; một `@Transactional` ở Java không tự commit hai hệ độc lập.

## 21. Atomic dedupe cho delta update

Ví dụ nhận event:

~~~json
{
  "eventId": "stock-dec-333",
  "sku": "SKU-A",
  "quantity": 2
}
~~~

Một thiết kế với transaction:

~~~text
BEGIN
  INSERT ProcessedEvent(consumerId,eventId) IF ABSENT
  IF duplicate:
      RETURN ALREADY_PROCESSED
  UPDATE StockProjection SET available = available - 2
  COMMIT
ACK event
```

Trong engine có multi-document transactions, insert marker unique và update Stock phải cùng transaction. Nếu transaction abort, cả hai mất. Nếu commit thành công nhưng ACK mất, event được gửi lại và marker giúp bỏ qua.

**Không giảm stock trước rồi mới ghi marker ở transaction khác** nếu mục tiêu exactly-once effect.

## 22. Dedupe window không được quá ngắn

Nếu một event được replay sau 30 ngày nhưng ProcessedEvent marker TTL chỉ 24 giờ, consumer có thể xử lý nó lần nữa.

Cần so:

- Broker retention.
- DLQ retention và thời gian replay.
- Disaster recovery từ snapshot.
- Thời gian một worker có thể offline.
- Business idempotency retention.
- Privacy/data retention policy.
- Khả năng rehydrate từ trạng thái authoritative.

Với full-state event có monotonic version, version guard có thể giảm nhu cầu lưu eventId vô hạn. Với `INCREMENT`, `CHARGE`, `SEND` thì retention idempotency cần được thiết kế theo rủi ro thực tế.

## 23. Dedupe không giải quyết mất thứ tự

Nhận v43 rồi v42, hai events có eventIds khác nhau:

~~~text
E43: status=INACTIVE
E42: price=120000
```

Dedupe chỉ biết cả hai đều chưa xử lý. Nếu consumer apply partial patches tùy tiện, target có thể là state lai không có trong bất kỳ source snapshot nào.

Phải kết hợp:

- Idempotency.
- Ordering hoặc version checks.
- Gap detection.
- Transformation rules.
- Snapshot/rebuild khi không thể áp patch đúng.

**At-least-once processing safety = không lặp effect + không lùi state + xử lý thiếu/thứ tự theo domain.**

## 24. Dedupe event không chặn business command trùng

Client gửi `POST /orders` một lần, server commit Order nhưng response mất. Client retry bằng request mới, tạo eventId mới:

~~~text
E101 OrderCreated order-1
E102 OrderCreated order-2
```

Inbox coi E101 và E102 là hai facts khác nhau. Muốn chặn duplicate order, source cần **business idempotency key/unique business intent**. Message dedupe không thay thế command idempotency.

## 25. At-most-once, at-least-once và exactly-once

| Delivery/processing expectation | Diễn giải | Rủi ro |
|---|---|---|
| At-most-once | Không tự gửi lại theo đường đang xét | Có thể mất event |
| At-least-once | Có thể giao lại cho tới khi ACK | Consumer có thể thấy duplicate |
| Exactly-once effect | Business effect được bảo vệ đúng một lần trong một scope | Cần transactional/idempotent design |

“Exactly-once” phải luôn gắn với **phạm vi**: trong một Kafka transaction, trong một DB transaction, hay end-to-end qua payment gateway? Một broker có guarantees nhất định **không tự làm external API được gọi đúng một lần**.

## 26. ACK sau commit và recovery

Một đường phổ biến:

~~~text
1. Receive event E
2. Apply to target database
3. Target commits
4. ACK message/commit consumer offset
```

Nếu crash giữa (3) và (4), event bị giao lại. Vì thế cần **idempotent effect**.

Nếu ACK ở (2) trước commit target, rồi worker crash trước (3), message có thể bị bỏ qua dù effect chưa tồn tại. Đây là nguy cơ **data loss**.

Không có thứ tự ACK đơn giản nào tự giải quyết cả mất lẫn trùng. Cần transaction/inbox/monotonic apply và checkpoint strategy.

## 27. Kafka offset commit và thứ tự hoàn tất

Một partition giao offsets 100,101,102. Ứng dụng xử lý song song:

~~~text
offset 100: slow
offset 101: success
offset 102: success
```

Nếu consumer commit offset sau 102 như thể mọi record trước đều xử lý xong, crash có thể làm mất processing của 100.

Nếu xử lý parallel trong một partition, cần tracking **contiguous completed offsets** hoặc giao thức tương đương. Đơn giản nhất cho projection có yêu cầu thứ tự mạnh là xử lý tuần tự mỗi key/partition và chỉ commit sau khi effect bền vững.

## 28. Concurrency theo key thay vì toàn bộ stream

Một consumer có nhiều events:

~~~text
Product A v10
Product B v50
Product A v11
Product C v30
```

Có thể xử lý song song **giữa các aggregate keys** mà giữ thứ tự **bên trong mỗi key**.

Thiết kế như per-key serial executor/sharded worker queues giúp throughput tốt hơn serialize tất cả events trên một thread. Nhưng vẫn cần xử lý rebalance, worker restart và version guard ở target để chặn race còn lại.

## 29. Sử dụng full snapshot để phục hồi từ gap

Nếu không thể lấy đủ partial events v41/v42, có thể đọc full source state v43:

~~~text
Target v40
Missing patches v41,v42
Source snapshot v43 with full fields
-> conditional replace target with snapshot v43
```

Điều kiện:

- Source read đủ authoritative/fresh.
- Snapshot bao gồm mọi field mà projection cần hoặc transformation có đủ dependencies.
- Projection không cần side effects/history của events bị thiếu.
- Delete/generation và schema được xử lý.
- Tác động repair được version-guarded.

Nếu có một notification phải gửi cho mỗi transition, **snapshot không tự tái tạo tất cả event-level side effects**.

## 30. Tombstone ngăn dữ liệu sống lại

Timeline:

~~~text
Product v30 ACTIVE
Product v31 DELETED (tombstone)
Consumer apply delete v31
Delayed ProductUpdated v29 arrives
```

Nếu target hard-delete mà không giữ metadata version/generation, consumer có thể xem v29 là record mới và insert lại.

Một tombstone marker:

~~~json
{
  "_id": "tenant-17#product-101",
  "generation": 1,
  "sourceVersion": 31,
  "deleted": true
}
~~~

cho phép từ chối mọi event v30 trở xuống của cùng generation. Khi cần xóa payload PII, có thể giữ **metadata tối thiểu** nếu policy cho phép; không giữ bản sao dữ liệu cá nhân vô hạn chỉ vì kỹ thuật.

## 31. ABA và tái sử dụng entity ID

Nếu ID được dùng lại:

~~~text
Generation 1: Product P v100, then DELETE
Generation 2: Product P v1, created again
```

So sánh version đơn lẻ có thể sai: v100 của entity cũ không phải trạng thái “mới hơn” v1 của entity mới theo identity generation.

Cần:

- ID mới không tái sử dụng, hoặc
- `aggregateGeneration`/epoch có thứ tự/authority rõ, hoặc
- Identity bao gồm generation.

Consumer so `(generation,version)` theo domain policy và không cho event generation cũ ghi lên bản mới.

## 32. Version và delete phải được tạo nguyên tử với source mutation

Một source update:

~~~text
SET Product.status=INACTIVE
SET Product.version=42
EMIT ProductChanged(version=42)
```

Nếu ba bước độc lập không có cơ chế tin cậy, có thể có event nói v42 trong khi source thực vẫn v41, hoặc source v42 mà event mất.

Giải pháp thường là:

- Tăng version cùng một source write.
- Ghi outbox trong cùng transaction/atomic scope nếu hỗ trợ.
- Hoặc đọc CDC trực tiếp từ committed log.
- Publish retry dùng stable eventId.
- Consumer apply idempotently.

**Giao dịch source/outbox không tự bao trùm external Search hay Redis**; consumer vẫn phải chịu redelivery.

## 33. Transactional outbox

Một transaction nguồn:

~~~text
BEGIN
  Update Order.status=PENDING, version=8
  Insert Outbox(
      eventId=E100,
      aggregateId=Order-100,
      aggregateVersion=8,
      type=OrderChanged,
      payload=...
  )
COMMIT
```

Publisher đọc outbox:

~~~text
Read pending event E100
Publish E100
Mark delivered when safe under publication contract
```

Nếu publish thành công nhưng publisher crash trước khi mark, E100 có thể publish lại. **Outbox giải quyết atomicity giữa source state và intent-to-publish**, không phải chứng minh delivery exactly once tới mọi sink.

## 34. CDC lấy event từ dữ liệu đã commit

CDC đọc những thay đổi từ log hoặc stream của database theo khả năng engine. Ưu điểm:

- Hạn chế dual-write kiểu “ghi DB thành công, gửi queue thất bại”.
- Event được dẫn từ committed mutations.
- Có thể phục vụ audit, search projection và analytics.

Nhưng CDC cũng có các thách thức:

- Format và schema evolution.
- Position/resume token.
- Retention/lag.
- Transaction grouping.
- Snapshot khởi tạo.
- Delete và TTL expirations.
- Partition ordering.
- Source field version/identity.
- Reprocess và consumer checkpoints.

Không coi CDC là một message bus có global order bất biến giữa mọi shards/databases.

## 35. Initial snapshot và CDC stream

Khi tạo projection mới, có thể cần load hàng triệu records hiện hữu và đồng thời nhận changes.

Một race:

~~~text
Snapshot reader thấy Product v40
Source update Product v41
CDC consumer apply v41
Snapshot loader ghi v40 sau đó
```

Nếu loader overwrite vô điều kiện, projection bị lùi. Cần snapshot/CDC cutover protocol đúng hoặc **version guard thống nhất** giữa backfill và live consumer.

Một chiến lược khái quát:

1. Ghi lại stream position/watermark theo cơ chế nguồn hỗ trợ.
2. Đọc consistent snapshot hoặc thực hiện thuật toán backfill an toàn.
3. Buffer/replay CDC changes từ mốc đủ sớm.
4. Apply snapshot và CDC với version/generation guard.
5. Verify coverage, gaps và drift.
6. Chuyển live-only khi checkpoint an toàn.

**Không giả định một cursor scan có snapshot nhất quán toàn cluster nếu engine không cung cấp semantics đó.**

## 36. Mất vị trí resume sau khi hết retention

Consumer offline dài hơn thời gian giữ log. Resume token/offset cũ không còn dùng được.

Lúc này:

- Không được nhảy thẳng tới latest rồi tuyên bố projection đúng.
- Phải đánh dấu gap/coverage unknown.
- Rebuild/resnapshot theo nguồn có thẩm quyền.
- Replay các changes mới hơn snapshot.
- Verify delete/orphan.
- Alert lag lớn hơn retention safety margin.

Đây là lý do cần đo **oldest available log position**, consumer lag và time-to-rebuild, không chỉ số events/giây.

## 37. MongoDB Change Streams: phạm vi và checkpoint

MongoDB Change Streams cho phép theo dõi thay đổi trên collection/database/deployment theo capability, với resume token để tiếp tục stream trong giới hạn lưu trữ và điều kiện hỗ trợ.

Một event có thể chứa:

- `operationType` như insert/update/replace/delete.
- `documentKey`.
- `resumeToken`/`_id` của change event.
- `clusterTime` và transaction metadata theo tình huống.
- `updateDescription` cho update.
- `fullDocument` nếu được yêu cầu và available theo semantics.
- Namespace/collection metadata.

**Resume token phục vụ resume stream, không phải version của Product.** Không dùng token của hai namespace tùy ý để tự tạo total order cho tất cả entity updates.

## 38. MongoDB Change Streams: updateDescription khác full state

Một update event có thể là:

~~~json
{
  "operationType": "update",
  "documentKey": { "_id": "p-101" },
  "updateDescription": {
    "updatedFields": { "status": "INACTIVE" }
  }
}
~~~

Đây là **partial mutation**, không phải full Product snapshot. Nếu consumer bỏ qua những update trước đó, nó có thể thiếu title/price.

Tùy nhu cầu:

- Replay ordered updates đầy đủ.
- Truy vấn source để rebuild full projection.
- Dùng change stream options phù hợp với contract.
- Thêm aggregate version do ứng dụng quản lý.
- Reconciliation khi phát hiện gap.

Đừng lấy `updateDescription` rồi áp như một replace toàn bộ document.

## 39. fullDocument updateLookup không luôn là ảnh tại thời điểm event

Khi dùng MongoDB Change Streams với `fullDocument: "updateLookup"` trong những mode phù hợp, phần full document được tìm theo trạng thái tại thời điểm lookup, **có thể phản ánh một thay đổi mới hơn event đang xem**, không nhất thiết là before/after image chính xác của mutation gốc.

Vì vậy:

- Không suy `fullDocument.version` luôn bằng version của event.
- Một event update v41 có thể đi kèm lookup thấy document v43.
- Với current-state projection, full latest state có thể hữu ích nếu apply guarded.
- Với audit/history cần event-specific before/after images theo capability và retention được hỗ trợ, không dựa nhầm vào updateLookup.
- Khi fullDocument không available, cần fallback/retry theo hợp đồng.

## 40. MongoDB Java: đọc Change Stream

Một ví dụ Java Sync Driver mang tính minh họa:

~~~java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

public final class MongoProductWatcher {
    public void consume(MongoCollection<Document> source) {
        ChangeStreamIterable<Document> stream = source.watch()
            .fullDocument(FullDocument.UPDATE_LOOKUP);

        try (MongoCursor<ChangeStreamDocument<Document>> cursor =
                 stream.iterator()) {
            while (cursor.hasNext()) {
                ChangeStreamDocument<Document> change = cursor.next();

                // 1. Xác định loại thay đổi + documentKey.
                // 2. Chuyển thành projection event với version đúng.
                // 3. Apply target idempotently/conditional.
                // 4. Persist resume token CHỈ SAU khi effect bền vững.
                processAndPersistCheckpoint(change);
            }
        }
    }

    private void processAndPersistCheckpoint(
            ChangeStreamDocument<Document> change) {
        // Pseudocode: implement theo sink/checkpoint cụ thể.
    }
}
~~~

Ví dụ này chưa xử lý reconnect, backoff, resume token serialization, updateLookup lag, transaction grouping, no-visibility, error classification hoặc retention. Không dùng nguyên xi làm production daemon.

## 41. Checkpoint MongoDB Change Stream

Nếu consumer:

~~~text
receive token T100
persist T100
crash before writing Search
```

khi restart nó có thể resume sau T100 và **bỏ qua effect** của T100.

Phương án an toàn thường là:

~~~text
receive T100
apply idempotent target
persist checkpoint T100
```

Nếu crash sau apply nhưng trước checkpoint, T100 được đọc lại và bị version guard/inbox bỏ qua.

Nếu checkpoint và effect ở cùng database hỗ trợ transaction, có thể commit atomically khi hợp lý. Nếu ở hai hệ khác nhau, **at-least-once replay + idempotency** là thiết kế cần dựa vào.

## 42. MongoDB projection Java: optimistic update

Giả sử target MongoDB document:

~~~json
{
  "_id": "tenant-17#product-101",
  "generation": 1,
  "sourceVersion": 40,
  "status": "ACTIVE"
}
~~~

Một Repository nhận full state event v42. Nếu đã đọc target v40, có thể dùng CAS:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public boolean replaceIfUnchanged(
        MongoCollection<Document> target,
        String key,
        long expectedVersion,
        long incomingVersion,
        String status) {

    if (incomingVersion <= expectedVersion) {
        return false;
    }

    UpdateResult result = target.updateOne(
        and(
            eq("_id", key),
            eq("generation", 1),
            eq("sourceVersion", expectedVersion)
        ),
        combine(
            set("status", status),
            set("sourceVersion", incomingVersion)
        )
    );
    return result.getMatchedCount() == 1;
}
~~~

Đây là ví dụ cho **nhánh target đã tồn tại**, với generation cố định nhằm làm rõ CAS. Nhánh target không tồn tại cần conditional insert/unique key riêng; trường hợp `matchedCount=0` cần re-read. Để projection nhiều fields, phải thay toàn bộ source-owned fields nhất quán theo schema, không chỉ status.

## 43. MongoDB inbox và projection trong một transaction

Nếu consumer nhận event delta và inbox/projection cùng ở một MongoDB deployment hỗ trợ transaction, có thể làm:

~~~text
withTransaction:
  insert Inbox(consumerId,eventId)  // unique key
  update projection by delta
commit
ACK broker
```

Nếu event đã trong inbox, callback phải nhận diện duplicate theo unique constraint/lookup và không chạy delta.

Cần lưu ý:

- Nếu duplicate key exception làm transaction abort, xử lý ở ngoài attempt đúng cách.
- `withTransaction` có thể retry callback trong một số lỗi.
- Không gọi email/payment trong callback.
- Dùng cùng ClientSession cho inbox và projection operations.
- Isolation/transaction scope được engine hỗ trợ.
- Commit result có thể unknown; không replay external effect mù.

## 44. DynamoDB Streams: record order và identity

DynamoDB Streams có records thay đổi của items và cung cấp sequence/stream metadata theo shard trong scope được hỗ trợ. Sự kiện cho cùng item được thiết kế có ordering guarantees theo stream, nhưng khi dùng Lambda, shard readers, retry, re-drive hoặc nhiều consumer paths, **ứng dụng vẫn cần idempotency và version guard** để bảo vệ sink.

Một stream record có thể cung cấp:

- Keys của item.
- `NewImage` hoặc `OldImage` theo StreamViewType.
- Sequence number trong shard.
- Event name INSERT/MODIFY/REMOVE.
- Approximate creation time.
- Stream ARN/shard metadata.

Đừng dùng sequence number như source version toàn cục qua mọi shards hoặc regions.

## 45. DynamoDB: cập nhật projection có điều kiện

Giả sử source phát full state v42, target table lưu `sourceVersion`.

Một request AWS SDK for Java v2 minh họa:

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.*;
import java.util.Map;

public boolean applyLatest(
        DynamoDbClient dynamo,
        String pk, String sk,
        long version, String status) {

    UpdateItemRequest request = UpdateItemRequest.builder()
        .tableName("ProductReadModel")
        .key(Map.of(
            "pk", AttributeValue.fromS(pk),
            "sk", AttributeValue.fromS(sk)
        ))
        .updateExpression("SET #s = :status, sourceVersion = :v")
        .conditionExpression(
            "attribute_not_exists(sourceVersion) OR sourceVersion < :v"
        )
        .expressionAttributeNames(Map.of("#s", "status"))
        .expressionAttributeValues(Map.of(
            ":status", AttributeValue.fromS(status),
            ":v", AttributeValue.fromN(Long.toString(version))
        ))
        .build();

    try {
        dynamo.updateItem(request);
        return true;
    } catch (ConditionalCheckFailedException alreadyNewer) {
        return false;
    }
}
~~~

Ví dụ giả định sourceVersion tăng đơn điệu và target là record có thể cập nhật bằng UpdateItem. Trong production cần thêm tenant/generation, schema/digest, delete semantics, IAM, và phân biệt `already applied` với `target ahead` bằng read nếu cần. **Không coi ConditionalCheckFailedException là lỗi có thể retry mù.**

## 46. DynamoDB: dedupe delta trong transaction

Nếu một event `CreditAdded` cần tăng balance projection đúng một lần, một hướng là dùng DynamoDB `TransactWriteItems` để:

- Put một processed-event marker với condition `attribute_not_exists(pk)`.
- Update target item với delta trong cùng transaction.
- Commit cùng nhau.
- ACK stream/broker sau khi transaction có outcome xác định.

Không tạo hai actions trên **cùng item** trong một `TransactWriteItems`, vì DynamoDB có giới hạn đó; dùng marker item riêng. Cần xét transaction limits, cùng account/region scope được hỗ trợ, cancellation reasons, idempotency token window và unknown result.

Nếu source/target nằm khác regions hoặc databases độc lập, một transaction DynamoDB local không bao trùm tất cả chúng.

## 47. DynamoDB Global Tables và concurrent updates

Với multi-region writes, có thể có hai cập nhật cùng một logical item ở hai regions:

~~~text
Region A writes status=ACTIVE
Region B writes status=INACTIVE concurrently
```

Đây không chỉ là “event đến đảo thứ tự”; đây là **concurrent conflict**. Thứ tự và conflict resolution phụ thuộc mode/version của Global Tables và dịch vụ. Không tự chọn timestamp client cao hơn để kết luận đúng nghiệp vụ.

Cần domain policy:

- Single authoritative write region cho aggregate khi phù hợp.
- Conditional writes/fencing trong scope được hỗ trợ.
- Conflict-free/commutative merge nếu domain cho phép.
- Reconciliation và audit khi có concurrent writes.

## 48. Redis Streams: Consumer Groups và pending entries

Trong Redis Streams, các thao tác thường gặp:

~~~text
XADD        publish entry
XREADGROUP  read within consumer group
XACK        acknowledge processed entry
XPENDING    inspect pending entries
XAUTOCLAIM  reclaim idle pending entries
```

Một consumer crash trước `XACK` có thể để message trong Pending Entries List, rồi message được claim/reprocess. Cần **idempotent effect** ở target.

Redis Stream ID giúp xác định entry trong **một stream**, không tự là business version của Product. Nếu một event nghiệp vụ được `XADD` lại với stream ID mới, consumer cần stable `eventId` trong payload để dedupe.

## 49. Redis Streams: xử lý và ACK

Pseudocode:

~~~text
messages = XREADGROUP(group,consumer,stream)

for message in messages:
    try:
        applyIdempotentlyToAuthoritativeTarget(message)
        XACK(stream,group,message.streamId)
    catch transient:
        do not ACK yet
        retry with backoff or allow claim
    catch invalid:
        move to DLQ/quarantine according to policy
        ACK only after durable disposition
```

Không ACK trước khi effect bền vững. Nhưng nếu Redis Streams và sink NoSQL khác nhau, vẫn không có một atomic transaction chung mặc định; re-delivery là điều phải xử lý.

## 50. Redis caching projection: versioned SET

Nếu Redis chỉ là cache đọc, event v42 có thể dùng để invalidate key, thay vì sửa đầy đủ.

~~~text
ProductChanged(v42):
  invalidate ProductCard tenant-17#product-101
```

Nếu muốn refresh trực tiếp:

~~~text
incoming v42
cached v43 -> do not overwrite
cached v40 -> replace with v42
```

Một Lua script hoặc Redis Function có thể thực hiện compare-and-set nguyên tử trên cùng key trong phạm vi được hỗ trợ. Không dùng `GET` rồi `SET` hai lệnh độc lập khi cần bảo vệ race.

Với Redis Cluster, multi-key script/transaction cần tuân thủ hash slot constraints.

## 51. Kafka: order theo partition không phải mọi topic

Một Kafka topic có nhiều partitions:

~~~text
Partition 0: A-v1, A-v2
Partition 1: B-v1, B-v2
```

Order trong partition có ý nghĩa; không có thứ tự toàn cục tự động giữa partition 0 và 1.

Nếu cùng aggregate được gửi với nhiều keys khác nhau hoặc topic config thay đổi, event có thể đi qua các partitions khác nhau và mất ordering guarantee kỳ vọng. Producer nên xác định stable partition key; consumer vẫn cần version guard ở sink.

## 52. Kafka consumer group rebalance

Khi consumer A chết, partition được giao cho consumer B. Có thể xảy ra:

~~~text
A đã apply event E
A chưa commit offset
B nhận lại E
```

Đây là hành vi phù hợp với at-least-once processing. Target phải an toàn khi B apply lại E.

Nếu A còn tác vụ async đang chạy sau khi mất quyền partition, nó có thể ghi muộn. Một **version/CAS guard** ở sink giúp tránh stale overwrite. Với side effects không thể rollback, cần idempotency/fencing hoặc state machine riêng.

## 53. Kafka Java: consumer loop minh họa

Pseudocode Java với ý tưởng commit sau effect:

~~~java
while (running) {
    ConsumerRecords<String, Event> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, Event> record : records) {
        Event event = record.value();

        try {
            projectionService.applyIdempotently(event);
            // Khi mọi prior records cần thiết của partition
            // đã xử lý xong, cập nhật commit position an toàn.
            checkpointManager.markProcessed(
                record.topic(),
                record.partition(),
                record.offset()
            );
        } catch (RetryableFailure ex) {
            retryCoordinator.defer(record, ex);
            // Không commit qua một gap chưa được xử lý.
        } catch (InvalidEvent ex) {
            quarantineStore.persist(record, ex);
            checkpointManager.markDurablyDisposed(record);
        }
    }
    checkpointManager.commitContiguousPositions(consumer);
}
~~~

**Đây là pseudocode, không phải Kafka Java client chạy được ngay**; `ConsumerRecords`, `Event`, `checkpointManager`, `retryCoordinator` và các exceptions cần được hiện thực/nhập theo project. Ý tưởng cốt lõi là **chỉ commit offset sau effect đã commit hoặc event đã được đưa vào trạng thái xử lý bền vững**, không commit vượt qua record chưa xong.

## 54. Kafka exactly-once có giới hạn phạm vi

Kafka có transactional producer và xử lý exactly-once trong những pipelines Kafka-to-Kafka phù hợp nếu cấu hình đúng. Tuy nhiên:

~~~text
Kafka input -> Java consumer -> MongoDB -> external Email
```

một Kafka transaction **không tự bao trùm MongoDB write và Email API**. Cần idempotent MongoDB sink, inbox/outbox hoặc giao thức phù hợp. Không quảng cáo “exactly-once end-to-end” chỉ vì Kafka bật idempotent producer.

## 55. Event-time analytics khác state projection

Một event:

~~~json
{
  "eventId": "purchase-100",
  "eventTime": "2026-11-14T09:55:00Z",
  "ingestTime": "2026-11-14T10:20:00Z",
  "amountMinor": 100000
}
~~~

Nếu dashboard tính doanh thu mỗi giờ theo **eventTime**, khoản tiền thuộc cửa sổ 09:00–10:00, không phải 10:00–11:00.

Nếu consumer chỉ cộng vào “giờ đang xử lý” thì báo cáo sai khi event muộn. Cần event-time windowing, watermark/allowed lateness hoặc backfill/correction.

## 56. Watermark là mốc tiến độ, không phải bảo đảm clock chính xác

Trong stream processing, **watermark** là một ước lượng/cam kết có điều kiện về mức tiến độ event-time của dữ liệu đã quan sát, theo semantics của framework. Nó cho biết hệ dự đoán những event có event-time trước mốc nào đã gần như đến đủ, với policy xử lý late arrivals.

Watermark không tự:

- Sắp lại toàn bộ events theo source version.
- Dedupe một event ID.
- Sửa projection bị ghi đè.
- Chứng minh không có event cũ nào xuất hiện nữa trong mọi hệ.
- Thay consumer checkpoint.

Một stream có thể có watermark 10:00, rồi vẫn nhận eventTime 09:55; cách xử lý tùy allowed lateness/retention.

## 57. Allowed lateness và window update

Giả sử analytics dùng window:

~~~text
Window: [09:00,10:00)
Watermark advanced past 10:00
EventTime=09:55 arrives at 10:20
```

Các lựa chọn nghiệp vụ:

1. **Drop late event** và ghi metric/audit (chỉ nếu domain chấp nhận).
2. **Update/retract result** của window đã phát.
3. **Side output/quarantine** để backfill thủ công.
4. **Reopen/recompute** window trong thời hạn cho phép.
5. **Store correction ledger** cho báo cáo tài chính.

Allowed lateness không nên chọn chỉ vì tiện bộ nhớ. Cần xét **SLO độ chính xác**, thời gian thực tế event đến muộn và khả năng downstream chấp nhận kết quả cập nhật hồi tố.

## 58. Cửa sổ kết quả đã phát có thể cần correction

Ban đầu:

~~~text
Revenue 09:00–10:00 = 10,000,000
```

Sau đó một thanh toán 200.000 đến muộn:

~~~text
Corrected Revenue 09:00–10:00 = 10,200,000
```

Nếu consumer chỉ phát thêm số tổng 10.200.000 và downstream lại cộng nó vào 10.000.000, dashboard sai. Phải thiết kế **upsert by window key + resultVersion**, hoặc publish **retraction/correction event** có semantics rõ.

Đây là một bài toán **idempotent aggregate update**, không chỉ “nhận event trễ”.

## 59. Dedupe facts trước khi cộng tổng

Một payment fact có `eventId=P100`, amount 200.000. Nếu event được nhận hai lần:

~~~text
P100 -> add 200000
P100 -> add 200000 again
```

Doanh thu bị cộng gấp đôi.

Một giải pháp:

- Contribution ledger lưu từng `paymentId`/fact ID.
- Chỉ insert contribution nếu chưa có.
- Tổng được cập nhật cùng transaction phù hợp hoặc được recompute từ ledger.
- Đổi/cancel/refund dùng event riêng và rule bổ sung.
- Khi replay, fact cũ trở thành no-op.

Không dùng **timestamp khác** làm lý do chấp nhận cùng logical payment thêm lần nữa.

## 60. Phép toán giao hoán giúp nhưng không đủ

Một số operations có tính giao hoán:

\[
a+b=b+a
\]

Hai event cộng 2 và cộng 3 có thể áp đảo thứ tự vẫn ra 5. Nhưng **áp trùng event cộng 2** sẽ ra 7; tính giao hoán **không tự có idempotency**.

Tương tự:

- Set union theo event/member ID có thể idempotent nếu mô hình đúng.
- `SET status=X` có thể idempotent cho cùng X nhưng dễ bị overwrite bởi trạng thái cũ.
- `INCREMENT` không idempotent.
- Add/remove membership có thể cần causal semantics.
- CRDT có thể xử lý một số concurrent merges, nhưng phải chọn loại đúng domain.

Đừng biến mọi nghiệp vụ thành “last write wins” chỉ vì nó dễ implement.

## 61. Khi domain cần mọi transition

Current-state projection chỉ cần biết Order đã DELIVERED có thể bỏ qua trạng thái trung gian cho màn hình đọc. Nhưng workflow có thể yêu cầu:

~~~text
CREATED -> PAID -> SHIPPED -> DELIVERED
```

Một event `OrderDelivered` đến trước `OrderPaid` có thể không được thực thi nếu side effect của `OrderPaid` còn thiếu.

Cần phân biệt:

- **State materialization:** kết quả cuối cho read.
- **Workflow orchestration:** điều kiện trước/sau và side effects.
- **Audit:** mọi transition.
- **Notification:** có thể yêu cầu gửi mỗi thông báo một lần.

Một version guard “nhận v4, bỏ v2/v3” có thể hợp lệ cho read card nhưng **sai cho workflow cần thanh toán, shipment và audit đầy đủ**.

## 62. Sự kiện giữa nhiều aggregate có phụ thuộc nhân quả

Ví dụ:

~~~text
CustomerCreated(C1)
OrderCreated(O1, customerId=C1)
```

Hai events có thể ở topics/partitions khác nhau, consumer Order nhận trước Customer.

Không có source version chung đủ để sắp tất cả. Các cách thiết kế:

- Consumer order tự tạo placeholder hoặc lưu pending reference có hạn.
- Retry với backoff và dead-letter khi dependency chưa có.
- Dùng saga/orchestrator điều phối tiến trình.
- Đưa facts vào cùng transactional envelope khi engine hỗ trợ.
- Cho eventual referential integrity và periodic reconciliation.
- Có idempotency nếu event được xử lý lại sau khi dependency xuất hiện.

Đừng chặn một partition vô hạn chỉ vì một entity phụ chưa được materialize.

## 63. Multi-writer: scalar version chưa chắc phân biệt conflict

Giả sử hai vùng ghi cùng entity:

~~~text
Region A: version=10, status=ACTIVE
Region B: version=10, status=INACTIVE
```

Hai version bằng nhau nhưng content khác. Đây là concurrent conflict; không phải duplicate và không có “event nào đến trước thì đúng” rõ ràng.

Cần:

- Single-writer authority hoặc ownership epoch.
- Cơ chế transaction/consensus đủ mạnh.
- Vector clocks/dotted version vectors nếu mô hình phù hợp.
- CRDT khi domain cho phép merge.
- Conflict resolution rule có thể audit.
- Human intervention nếu không thể tự merge an toàn.

**Timestamp mới hơn** có thể là một LWW policy hợp lệ cho một số fields, nhưng không tự bảo đảm tính đúng của account balance, approval hay payment state.

## 64. LWW có thể làm mất cập nhật

Một policy “last-write-wins theo timestamp”:

~~~text
A updates address to X at clock 10:00:01
B updates address to Y at clock 10:00:02
```

Nếu đồng hồ A/B lệch, timestamp order có thể không khớp causal order. Hơn nữa, LWW chỉ chọn một winner; nó **bỏ một thay đổi**.

LWW có thể chấp nhận cho một số preference field, nhưng đối với counter, ledger, stock hoặc workflow transitions, cần domain merge/coordination rõ ràng.

## 65. Schema evolution và event đến trễ

Một consumer phiên bản mới có thể nhận event được phát từ schema cũ:

~~~text
E100 schemaVersion=1, field price
E200 schemaVersion=2, fields amountMinor + currency
```

Consumer phải có:

- Schema registry/version handling theo hệ dùng.
- Upcaster hoặc compatibility mapping.
- Default values có nghĩa nghiệp vụ.
- Test với historical events.
- Không dùng một serializer mới tự đoán sai đơn vị tiền.
- Routing/filter khi không còn hỗ trợ schema quá cũ.
- Quarantine và alert thay vì làm hỏng projection.

Một sự kiện đến muộn có thể mang **business state cũ và schema cũ**, hai bài toán khác nhau.

## 66. Event trùng nhưng payload khác là dấu hiệu integrity issue

Nếu nhận hai messages cùng `eventId=E100` nhưng payload khác:

~~~text
E100 amount=100000
E100 amount=900000
```

Không nên chọn message tới trước và im lặng. Có thể producer tái sử dụng ID sai, mutation payload sau publish hoặc corruption.

Inbox có thể lưu `payloadDigest`/schemaVersion để phát hiện:

- Same ID + same digest → duplicate.
- Same ID + different digest → **integrity mismatch**, quarantine/alert.

Đừng đưa raw PII hoặc payment credentials vào log để chứng minh mismatch; dùng digest và metadata.

## 67. Poison event và retry không giới hạn

Một event schema không parse được sẽ thất bại dù retry một triệu lần. Một consumer retry mãi cùng record có thể chặn toàn partition.

Phân loại:

| Lỗi | Ví dụ | Xử lý |
|---|---|---|
| Transient | Timeout tới MongoDB | Retry bounded/backoff |
| Dependency not ready | Customer projection chưa tạo | Bounded defer, snapshot/reconcile |
| Duplicate | Inbox đã có event ID | ACK/no-op |
| Stale version | Incoming v40, target v42 | ACK/no-op cho state projection |
| Gap | Incoming patch v43, target v40 | Buffer/replay/rebuild |
| Schema invalid | Thiếu field bắt buộc | Quarantine/DLQ |
| Integrity conflict | Same ID khác payload | Alert/quarantine |
| Business rejection | State transition không hợp lệ | Domain disposition, không retry mù |
| Unknown commit | Response mất sau write | Reconcile/idempotency trước replay |

Một DLQ cũng cần retention, ownership và quy trình re-drive. Không để DLQ là “thùng rác” không ai kiểm.

## 68. Retry và backoff

Khi sink NoSQL throttling hoặc timeout:

- Dùng retryability signals của driver.
- Exponential backoff + jitter.
- Max attempts và toàn bộ deadline.
- Per-key/partition concurrency limits.
- Không ACK trước khi effect/durable disposition.
- Không tự tạo eventId mới cho retry.
- Không để nhiều tầng retry nhân tải không kiểm soát.
- Khi replay sau lâu, vẫn áp version/inbox guards.

Không retry một event stale như thể chờ thêm sẽ làm nó mới lại.

## 69. Backpressure để bảo vệ cả source và sink

Nếu CDC phát 50.000 events/s nhưng Search chỉ index được 10.000/s, backlog sẽ tăng. Những lựa chọn:

- Scale consumer/sink nếu bottleneck cho phép.
- Batch writes theo routing key/partition policy.
- Coalesce full-state updates cho một key khi business cho phép.
- Giới hạn load/concurrency.
- Chia hot partitions hoặc đổi key design nếu phù hợp.
- Giảm refresh/reindex cost.
- Alert lag tới ngưỡng retention.
- Ưu tiên delete/security events theo policy phù hợp.

Không coalesce `PaymentCaptured` hay `BalanceIncremented` tùy tiện: mỗi fact có thể quan trọng.

## 70. Event coalescing chỉ an toàn cho trạng thái tự chứa

Một Product thay đổi:

~~~text
v40 title=A
v41 title=B
v42 title=C
```

Nếu Search chỉ cần title mới nhất, có thể coalesce thành full snapshot v42, khi source version và delete semantics đúng.

Nhưng một event stream:

~~~text
v40 StockDecreased 1
v41 StockDecreased 2
v42 StockIncreased 1
```

không được bỏ v40/v41 nếu v42 chỉ mang delta +1. Muốn coalesce cần tính **net contribution** từ tất cả facts hoặc dùng full-state snapshot có authority.

## 71. Reconciliation sau replay

Một consumer có thể “đọc hết topic” nhưng projection vẫn sai do:

- Event bị mất trước thời hạn retention.
- Mapping bug trước đây.
- Write bị skip nhưng checkpoint vẫn tiến.
- Delete không có tombstone.
- Một target bị sửa thủ công.
- Schema migration dở dang.
- Version guard dùng sai scope.

Cần **periodic source-to-target comparison** và **target-to-source reverse scan** cho orphan khi phù hợp. Dùng source version, generation, schema và canonical digest để detect drift; repair có conditional write không downgrade.

Event processing đáng tin cậy và reconciliation là hai lớp bổ trợ.

## 72. Kiểm soát delete sau khi source hard-delete

Một Source đã hard-delete entity, trong khi target còn record. Nếu không có tombstone hoặc deletion manifest, source GET `NOT_FOUND` có thể chưa đủ bằng chứng để auto-delete vì:

- Read replica stale/inconsistent.
- Tenant/key mapping sai.
- Source đang unavailable.
- Entity đang migrate.
- Key được tạo lại với generation mới.

Cần authoritative deletion evidence và retention policy. Đối với PII, ưu tiên xóa đúng deadline và ngăn event replay tái tạo payload.

## 73. Security và tenant context trên event

Một event:

~~~json
{
  "tenantId": "tenant-17",
  "aggregateId": "order-100",
  "eventType": "OrderStatusChanged"
}
~~~

Consumer phải kiểm:

- Nguồn event được xác thực/authorized.
- Namespace tenant là một phần key hoặc routing.
- Một event tenant A không cập nhật projection tenant B.
- Event payload không tự cấp quyền hành động cho người khác.
- Schema/size/input validation chống payload độc.
- PII được mã hóa/lưu trữ/tracing theo policy.
- Secrets không bị ghi vào DLQ payload/plain logs.
- Replay tools có access control và audit.

**Ordering key đầy đủ thường bao gồm tenant + aggregate type + ID**, không chỉ raw `orderId`.

## 74. Quan sát một event qua các chặng

Một tracing envelope có thể ghi:

~~~json
{
  "eventId": "E42",
  "operationId": "checkout-K100",
  "source": "OrderService",
  "aggregateId": "order-100",
  "aggregateVersion": 42,
  "brokerPartition": "P2",
  "brokerOffset": "1001",
  "attemptNo": 2,
  "applyOutcome": "SKIPPED_STALE",
  "latencyMs": 31
}
~~~

Không log nguyên dữ liệu nhạy cảm. AggregateId có thể có cardinality cao, nên dùng ở logs/traces kiểm soát quyền thay vì Prometheus label cho mọi key.

## 75. Metrics quan trọng

| Metric | Đo điều gì? |
|---|---|
| `eventsReceived` | Lượng messages nhận |
| `eventsApplied` | Những effects được commit |
| `eventsDuplicate` | Cùng eventId đã thấy |
| `eventsStaleSkipped` | Bị từ chối do version thấp |
| `eventsOutOfOrder` | Phiên bản đến không theo kỳ vọng |
| `versionGapCount` | Khoảng trống phát hiện |
| `gapRecoveryAge` | Mất bao lâu để phục hồi |
| `inboxConflictCount` | Marker conflict/dedupe |
| `sameVersionDigestMismatch` | Integrity issue |
| `tombstoneResurrectionPrevented` | Số event cũ bị chặn sau delete |
| `consumerLagSeconds` | Delay giữa source/stream và sink |
| `oldestUnprocessedAge` | Backlog già nhất |
| `cdcRetentionMargin` | Còn bao lâu trước nguy cơ mất resume |
| `projectionDriftCount` | Lệch so với source |
| `retryCount` | Backoff/retry |
| `dlqBacklog` | Poison events chưa giải quyết |
| `windowLateEventCount` | Event-time đến trễ |
| `windowCorrectionCount` | Kết quả analytics cập nhật hồi tố |
| `projectionApplyP95/P99` | Độ trễ xử lý |
| `unknownWriteOutcomeCount` | Các commits cần reconcile |

Không đánh đồng `received == applied` là bắt buộc: duplicate/stale có thể được xử lý hợp lệ thành no-op.

## 76. Lag nên đo ở đúng đoạn

Có thể tách:

~~~text
Source commit -> broker published
Broker published -> consumer received
Consumer received -> target committed
Target committed -> read visible
```

Một hệ có consumer lag nhỏ nhưng Search refresh delay lớn vẫn trả bản cũ cho user.

Cần đo theo source timestamps/versions và khả năng so sánh tin cậy, không trừ bừa timestamp từ nhiều clock khác nhau rồi khẳng định có độ chính xác mili giây.

## 77. Alert không chỉ vì số duplicate tăng

Duplicate có thể là bình thường với at-least-once delivery. Alert quan trọng hơn:

- Duplicate effect làm sai dữ liệu.
- Version gap không hồi phục trong deadline.
- Lag sắp vượt retention window.
- DLQ backlog không được xử lý.
- Same ID/digest mismatch.
- Old event resurrect data sau delete.
- Stale write guard không được áp.
- Projection drift vượt SLO.
- Correctness invariant bị phá.

Một deployment mới có thể làm duplicate count tăng do rebalance; đây là tín hiệu điều tra, không mặc định incident mất dữ liệu.

## 78. Test duplicate delivery

Setup:

~~~text
Initial projection: credits=10
Event E100: CreditAdded(amount=5)
Deliver E100 twice, even concurrently
```

Assert:

- Final credits=15, không phải 20.
- Inbox/dedupe marker đúng.
- Hai workers không cùng áp delta.
- ACK/retry không mất event.
- Metrics có duplicate count.
- Same event ID với payload khác bị quarantine.

## 79. Test out-of-order full state

Setup:

~~~text
Initial Product target v40
Deliver v43 first, then v41, then v42
```

Assert:

- Final target v43.
- V41/v42 không downgrade.
- Same version duplicate thành no-op.
- Digest/schema đúng.
- Không bỏ side effect nghiệp vụ nếu use case thật sự yêu cầu event-level processing riêng.

## 80. Test gap trong partial patches

Setup:

~~~text
Target v40
v41 updates price
v42 updates title
Deliver v43 updates status without v41,v42
```

Assert:

- Consumer không âm thầm tuyên bố đủ state khi thiếu fields.
- Có gap detection.
- Có replay/snapshot rebuild.
- Event v43 được xử lý sau recovery hoặc có disposition bền.
- Không loop vô hạn khi v41/v42 hết retention.

## 81. Test delete/replay

Setup:

~~~text
Source Delete v44
Target gets tombstone v44
Replay ProductUpdate v40
```

Assert:

- Không resurrect.
- Target/metadata giữ generation và sourceVersion thích hợp.
- PII payload không quay lại.
- Event v40 được ACK/no-op chứ không retry mãi.

## 82. Test crash sau apply trước ACK

Setup:

~~~text
Consumer receives E100
Target commit succeeds
Kill consumer before ACK
Restart, broker redelivers E100
```

Assert:

- Không apply effect hai lần.
- Consumer có thể ACK sau nhận biết duplicate.
- Checkpoint cuối cùng tiến.
- Không mất event khác khi commit offsets.

## 83. Test snapshot và live event race

Setup:

~~~text
Snapshot reader loads Source v40
Live consumer applies v41
Snapshot reader tries write v40 after
```

Assert:

- Target vẫn v41.
- Backfill và live updater dùng cùng guard.
- Không ghi đè schema generation mới.
- Coverage/cutover checkpoint đúng.

## 84. Test event-time đến muộn

Setup:

~~~text
Window [09:00,10:00)
Watermark passes 10:00
Event E100 has eventTime 09:55 and arrives 10:20
```

Assert theo business policy:

- Nếu trong allowed lateness: window update/retraction đúng.
- Nếu ngoài: side output/backfill hoặc drop có audit.
- Event E100 không bị tính trùng khi replay.
- Downstream không cộng hai lần một giá trị tổng đã correction.

## 85. Test concurrent consumer và rebalance

Cho hai consumers cùng nhận hoặc overlap xử lý một aggregate sau rebalance:

~~~text
A: event v42 slow
B: event v43 fast
A commits late
```

Assert final target v43, không v42. Với delta, event ID và transaction guard đảm bảo effect đúng một lần. Không commit offset vượt record chưa xử lý.

## 86. Test same ID khác payload

Cùng `eventId` nhưng hai payload khác amount.

Assert:

- Không xử lý payload thứ hai như duplicate bình thường mà không báo.
- Quarantine integrity conflict.
- Không log PII/plain secrets.
- Có trace/audit để truy nguồn producer bug.

## 87. Test log retention hết hạn

Giả lập consumer offline lâu, resume token không còn hợp lệ.

Assert:

- Không skip thẳng tới live và tuyên bố data hợp lệ.
- Kích hoạt snapshot/rebuild.
- Replay được những changes sau snapshot.
- Delete/orphan được verify.
- Alerts và metrics nêu coverage gap.

## 88. Bài tập A — Bản cập nhật đảo thứ tự

Target v10. Consumer nhận full snapshot v12 trước v11.

**Hỏi:** có nên ghi v11 sau v12 không?

**Hướng giải:** không cho current-state projection. Guard version tại target chặn downgrade, miễn v12 đủ field và version có thứ tự đáng tin.

## 89. Bài tập B — Delta trùng

Stock projection=10. Event `Decrement(2)` được nhận hai lần.

**Hỏi:** chỉ so version lớn hơn có đủ không?

**Hướng giải:** cần semantics event/delta rõ. Dedupe event ID và effect phải được bảo vệ atomically; không để trừ 2 hai lần.

## 90. Bài tập C — Version gap

Target v5; nhận patch v8.

**Hỏi:** có thể apply ngay không?

**Hướng giải:** thường không an toàn nếu v6/v7 chứa thay đổi field cần giữ. Buffer/replay hoặc rebuild full snapshot.

## 91. Bài tập D — Snapshot đầy đủ

Target v5; nhận full Product snapshot v8.

**Hỏi:** có nhất thiết chờ v6/v7?

**Hướng giải:** có thể không cần cho current-state view nếu v8 tự chứa, version authority đúng và không cần side effects/history của events trung gian.

## 92. Bài tập E — Broker offset

Kafka P0 offset 100 của Product A và P1 offset 200 của Product B.

**Hỏi:** có thể kết luận Product B mới hơn A?

**Hướng giải:** không. Offsets thuộc partitions và không là entity versions có thể so ngang.

## 93. Bài tập F — Timestamp

Region A eventTime 10:01, region B eventTime 10:02 và clocks lệch.

**Hỏi:** chọn timestamp lớn hơn có bảo toàn mọi business invariant không?

**Hướng giải:** không; cần source ordering, conflict ownership, domain merge hoặc coordination.

## 94. Bài tập G — Ack trước commit

Consumer ACK E1 rồi crash trước khi cập nhật MongoDB.

**Hỏi:** rủi ro gì?

**Hướng giải:** mất effect vì broker có thể không giao lại. ACK sau commit/durable disposition, cùng idempotency.

## 95. Bài tập H — Commit trước ACK

Consumer ghi thành công vào DB nhưng crash trước ACK.

**Hỏi:** rủi ro gì và cách bảo vệ?

**Hướng giải:** broker gửi lại event; dùng inbox/monotonic update/idempotent consumer.

## 96. Bài tập I — Delete rồi update cũ

Product deleted v20. Update event v17 đến sau.

**Hỏi:** làm sao ngăn resurrect?

**Hướng giải:** tombstone/version/generation guard và retention tương thích replay window.

## 97. Bài tập J — Inbox và effect riêng transaction

Consumer ghi ProcessedEvent marker, commit; crash trước khi tăng counter.

**Hỏi:** hậu quả?

**Hướng giải:** lần replay thấy marker và bỏ qua, làm mất effect. Marker và effect cần cùng atomic transaction hoặc protocol tương đương.

## 98. Bài tập K — Kafka rebalance

A apply offset 100 rồi crash trước commit, B nhận lại 100.

**Hỏi:** đây là lỗi broker không?

**Hướng giải:** không mặc định; đó là tình huống at-least-once. Consumer phải idempotent.

## 99. Bài tập L — Mongo updateLookup

Change stream event v41 nhận fullDocument đang chứa state v43.

**Hỏi:** có thể gọi đó là after-image chính xác của v41 không?

**Hướng giải:** không. updateLookup có thể trả state mới hơn. Cần semantics phù hợp cho audit và version guard cho current-state projection.

## 100. Bài tập M — Redis Stream ID

Producer XADD cùng business event hai lần, tạo hai stream IDs khác nhau.

**Hỏi:** stream IDs có giúp dedupe như một event ID ổn định không?

**Hướng giải:** không đủ; payload cần logical eventId ổn định, hoặc nguồn có contract khác bảo vệ.

## 101. Bài tập N — EventTime window

Payment event xảy ra 09:55 nhưng đến 10:20.

**Hỏi:** tính vào doanh thu giờ nào?

**Hướng giải:** nếu báo cáo theo event-time, thuộc [09:00,10:00); phải xử lý late arrival/correction theo policy.

## 102. Bài tập O — Aggregate retraction

Dashboard đã xuất tổng 1 triệu, sau late event tính lại thành 1,2 triệu. Downstream cộng thêm 1,2 triệu.

**Hỏi:** lỗi gì?

**Hướng giải:** nhầm “tổng mới” với “delta”. Dùng upsert theo window key/version hoặc correction/retraction semantics.

## 103. Bài tập P — Two source versions

Search Card giữ Product v10 và Inventory v400. Product event v11 đến.

**Hỏi:** có bỏ Product v11 vì 11 nhỏ hơn 400 không?

**Hướng giải:** không. Version của từng owner/stream khác nhau; so Product v11 với Product v10.

## 104. Bài tập Q — Same ID khác payload

Hai messages cùng E100 nhưng giá trị price khác nhau.

**Hỏi:** chỉ bỏ message thứ hai là đủ không?

**Hướng giải:** không. Đây là integrity mismatch hoặc producer bug; cần cảnh báo/quarantine và xác minh owner/version.

## 105. Bài tập R — Dedupe TTL

ProcessedEvent TTL 1 ngày, broker giữ messages 7 ngày và replay sau 4 ngày.

**Hỏi:** nguy cơ?

**Hướng giải:** dedupe marker đã mất, delta có thể chạy lại. Cần retention/strategy tương thích replay horizon.

## 106. Bài tập S — Partial patch đã mất

Consumer chỉ thấy `status` mới nhưng không thấy patch `price` trước đó.

**Hỏi:** target có đủ để tạo full Search Card không?

**Hướng giải:** không chắc; cần replay gap hoặc full authoritative snapshot.

## 107. Bài tập T — Source tombstone hard delete

Source GET timeout, Search vẫn có record.

**Hỏi:** có nên xóa target ngay không?

**Hướng giải:** không. Timeout không là authoritative deletion evidence; retry/quarantine, đọc tombstone/deletion manifest nếu có.

## 108. Bài tập U — Concurrent region writes

Hai regions phát cùng version với payload trái nhau.

**Hỏi:** version guard có chọn được winner đúng không?

**Hướng giải:** không. Cần conflict resolution policy/ownership protocol hoặc merge theo domain.

## 109. Bài tập V — Multi-thread reorder

Broker delivery offsets 100,101,102 đúng thứ tự, nhưng Java worker pool hoàn tất 102 trước 100.

**Hỏi:** broker order đã bảo vệ target chưa?

**Hướng giải:** chưa. Cần serial apply per key, guard tại target và commit checkpoint không vượt gap.

## 110. Bài tập W — Chọn giải pháp cho audit

Read projection chỉ cần trạng thái Order cuối, nhưng audit cần mọi transition.

**Hỏi:** cả hai có thể dùng policy “chỉ áp version cao nhất” không?

**Hướng giải:** không. Audit phải bảo tồn từng fact/id và order semantics; current-state card có thể dùng full latest snapshot.

## 111. Checklist thiết kế xử lý event và CDC

1. Event mang **full state, patch, delta hay business fact**?
2. Có stable `eventId` qua retries/replay không?
3. `operationId` cho business intent có tách khỏi eventId không?
4. Có `tenantId`, `aggregateId`, `generation` và version scope rõ không?
5. Version có tăng atomically với source mutation không?
6. Ordering được bảo đảm theo key/partition/log nào?
7. Broker offset có bị nhầm với source entity version không?
8. Consumer có parallel apply trong cùng key không?
9. Có gap detection khi nhận patch v43 sau v40 không?
10. Gap có recovery budget, snapshot/replay và alert không?
11. Full snapshot có thật sự chứa mọi source-owned fields không?
12. Target có atomic conditional write/CAS để chặn downgrade không?
13. Same-version different digest có được triage riêng không?
14. Delete có tombstone/version marker chống resurrection không?
15. Có ID reuse/generation/ABA risk không?
16. Inbox dedupe marker và non-idempotent effect có atomic cùng scope không?
17. Dedupe retention có đủ cho log/DLQ/replay horizon không?
18. Acknowledgment/checkpoint chỉ tiến sau durable apply/disposition không?
19. Async processing có theo dõi contiguous offsets không?
20. Initial snapshot có chống race với live CDC không?
21. Consumer có nhận biết log retention hết hạn và resnapshot không?
22. Event-time, ingest-time và source version có phân biệt rõ không?
23. Watermark và allowed lateness có theo business reporting policy không?
24. Window correction có idempotent/versioned upsert không?
25. Multi-writer concurrency có domain conflict policy không?
26. Schema evolution có test historical events và upcaster không?
27. Poison event có DLQ/quarantine và re-drive procedure không?
28. Retry có bounded backoff, jitter và backpressure không?
29. Data owner/tenant/security/PII được bảo vệ trong replay không?
30. Có metric lag, duplicates, stale, gaps, DLQ và integrity mismatch không?
31. Có reconciliation so source/target và reverse orphan scan không?
32. Đã test duplicate đồng thời, reorder, missing patch, tombstone, crash/ACK, snapshot/live race và retention expiry chưa?
33. Những external side effects có stable idempotency key và workflow riêng không?
34. Lời hứa exactly-once có ghi rõ **scope** và failure model không?

## 112. Một hợp đồng event-processing minh họa

~~~yaml
pipeline: ProductStateProjection
sourceOfTruth:
  owner: CatalogService
  key: tenantIdAndProductId
  version: monotonicPerAggregate
event:
  logicalId: stableEventId
  identity:
    - tenantId
    - aggregateType
    - aggregateId
    - aggregateGeneration
  schemaVersion: required
  payloadType: fullState
  businessTime: occurredAt
delivery:
  guarantee: atLeastOnce
  orderingScope: perAggregateKeyWithinPartition
  retries: boundedWithBackoffAndJitter
processing:
  applyPolicy: incomingVersionGreaterThanTarget
  sameVersionSameDigest: noOp
  sameVersionDifferentDigest: quarantine
  staleEvent: acknowledgeWithoutDowngrade
  sourceVersionGap:
    fullState: allowedForCurrentStateOnly
    patch: replayOrRebuild
  parallelism: perKeySerial
  checkpoint: afterDurableEffect
  unknownOutcome: reconcileBeforeReapply
delete:
  tombstone: versioned
  staleResurrection: reject
  generation: requiredIfIdsReused
snapshot:
  bootstrap: snapshotPlusCDC
  cutover: supportedWatermarkAndVersionGuard
  retentionGap: resnapshotAndVerify
observability:
  - appliedEvents
  - duplicateEvents
  - staleSkipped
  - versionGaps
  - sameVersionDigestMismatch
  - oldestUnprocessedAge
  - consumerLag
  - dlqBacklog
  - projectionDrift
tests:
  - duplicateDelivery
  - outOfOrderFullState
  - missingPatch
  - lostAckAfterCommit
  - tombstoneThenOldUpdate
  - backfillAndLiveRace
  - retentionExpired
  - eventTimeLateCorrection
~~~

Đây là **mẫu YAML tài liệu kiến trúc**, không phải cấu hình mà MongoDB, DynamoDB, Redis, Kafka hay một Java framework tự áp dụng. Những guarantee phải được triển khai đúng trong driver, source schema, consumer và database sink.

## 113. Mẫu hợp đồng cho analytics khác current-state view

~~~yaml
pipeline: RevenueByHour
event:
  type: PaymentCaptured
  identity: stablePaymentFactId
  eventTimeField: capturedAt
window:
  type: tumbling
  duration: oneHour
  allowedLateness: accordingToBusinessSlo
  beyondLateness: correctionLedgerOrBackfill
effect:
  deduplication: factId
  aggregateKey: tenantAndHourAndCurrency
  updateSemantics: versionedUpsertOrRetraction
  cannotSkipIntermediateFacts: true
sink:
  checkpointAfterDurableCommit: true
  consumerRetrySafe: true
observability:
  - lateEventCount
  - correctedWindowCount
  - duplicateFactCount
  - unreconciledContributionCount
~~~

Hai YAML cho thấy **cùng vấn đề late/duplicate events nhưng hai chính sách khác nhau**: một Product Card có thể chỉ cần snapshot phiên bản mới nhất, còn doanh thu phải hạch toán từng payment fact và có cơ chế cập nhật hồi tố.

## 114. Kết luận

Sự kiện đến muộn, đảo thứ tự và bản cập nhật trùng là **điều kiện bình thường phải dự trù** khi dùng CDC, event stream và NoSQL read models. Điểm khó không phải chỉ nhận thêm một message, mà là bảo đảm message ấy không làm sai trạng thái đích hoặc tạo lại một tác động đã xảy ra.

Cần phân biệt rõ:

- **Đến muộn theo event-time** không tự là **stale theo source version**.
- **Dedupe eventId** không tự giải quyết **ordering** hay **business command trùng**.
- **Version guard** phù hợp cho **full-state projection**, nhưng **delta/patch** có thể phải replay đầy đủ.
- **Watermark** hỗ trợ xử lý event-time windows, không sửa source-ordering.
- **ACK sau commit** thường dẫn tới khả năng redelivery; consumer phải idempotent.
- **Tombstone/generation** chặn event cũ khôi phục dữ liệu đã xóa.
- **Snapshot+CDC cutover** cần bảo vệ race và coverage khi backfill.
- **Exactly-once** chỉ có nghĩa trong một scope được thiết kế, không tự trải sang external side effects.

> **Một consumer đúng không hỏi “message này vừa đến chưa?”, mà hỏi “đây là fact nào, thuộc lịch sử nào, đã được áp chưa, có còn hợp lệ với phiên bản hiện tại không, và sẽ ảnh hưởng invariant nghiệp vụ ra sao?”**

Khi source ownership, event identity, ordering scope, checkpoint và idempotent target writes được định nghĩa rõ, pipeline NoSQL có thể **hội tụ an toàn** dù messages tới trễ, trùng hoặc đảo thứ tự; còn những use case cần mọi sự kiện lịch sử sẽ có cơ chế replay và correction riêng thay vì bị che dưới một chính sách latest-wins đơn giản.

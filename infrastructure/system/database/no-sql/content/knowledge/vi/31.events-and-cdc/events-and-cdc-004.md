# Định danh sự kiện, thứ tự và phạm vi thứ tự theo khóa/phân vùng

Trong một ứng dụng NoSQL phân tán, dữ liệu thường được sao chép qua **sự kiện** và **Change Data Capture (CDC)**. Một đơn hàng thay đổi từ `PENDING` sang `CONFIRMED`; dịch vụ thanh toán, tồn kho, tìm kiếm và thông báo có thể nhận sự kiện để cập nhật trạng thái tương ứng. Nhưng điều gì xảy ra nếu mạng mất ACK, một sự kiện được gửi lại, hai workers xử lý đồng thời hoặc hai bản ghi nằm ở hai phân vùng khác nhau?

Xét:

~~~text
Order O-100:
    OrderCreated (seq 40)
    OrderConfirmed (seq 41)
    OrderCanceled (seq 42)

Order O-200:
    OrderCreated (seq 7)
    OrderConfirmed (seq 8)
~~~

Consumer của O-100 cần biết `Canceled` kế thừa `Confirmed` trong lịch sử của **cùng đơn hàng**. Nhưng `OrderConfirmed(O-200)` và `OrderCanceled(O-100)` có bắt buộc một thứ tự toàn cục hay không? Nếu hai orders ở hai partitions, nhiều brokers/consumers có thể quan sát chúng theo trình tự xen kẽ khác nhau mà vẫn đúng hợp đồng **per-order ordering**.

Đồng thời, một event có thể được phát lại khi publisher crash sau khi broker đã append, hoặc consumer crash sau khi ghi read model nhưng chưa ACK vị trí đọc. Để xử lý đúng, cần phân biệt rõ **định danh sự kiện** với **định danh ý định**, **phiên bản aggregate**, **event sequence**, **offset**, **source change token** và **key phân vùng**.

Bài học thuộc chương **Sự kiện và CDC** của module **Database No SQL** đi từ nền tảng identity, thứ tự và phạm vi bảo đảm, tới cách thiết kế outbox/CDC, partitioning, replay, idempotent consumers, mã Java và các tình huống thực tế.

> **Nguyên tắc trung tâm:** Không có một con số offset, timestamp hay UUID nào tự nó đại diện cho thứ tự nhân–quả của mọi dữ liệu trong toàn hệ. Bất kỳ lời hứa ordering nào cũng phải nêu **key, stream, partition, nguồn gốc sequence, thời điểm commit, consumer behavior và cách xử lý lỗi**.

## 1. Sự kiện nghiệp vụ và bản ghi CDC không giống nhau

Một **domain event** diễn tả một sự thật nghiệp vụ:

~~~json
{
  "eventType": "OrderConfirmed",
  "orderId": "O-100",
  "confirmedAt": "2026-11-14T09:00:00Z"
}
~~~

Một **CDC change record** diễn tả mutation của storage:

~~~json
{
  "operation": "UPDATE",
  "source": "orders",
  "documentKey": "tenant-A/O-100",
  "updatedFields": {
    "status": "CONFIRMED",
    "version": 41
  }
}
~~~

Một thao tác xác nhận Order có thể sửa Order, ghi Outbox và cập nhật audit records, tạo nhiều raw changes. Ngược lại, một update `status=CONFIRMED` có thể đến từ migration/repair, không tự chứng minh một command xác nhận mới đã được nghiệp vụ chấp nhận.

### 1.1. Ba lớp của event pipeline

| Lớp | Đặc điểm | Consumer phù hợp |
|---|---|---|
| Domain event | Có nghĩa nghiệp vụ trong bounded context | Domain workflow, aggregate |
| Integration event | Schema/hợp đồng ổn định giữa services | Downstream services |
| Raw CDC record | Thay đổi vật lý theo database API | Sync, projection, replication, connector |

**Integration event** có thể được tạo từ transactional outbox rồi CDC phát ra; consumer không nhất thiết phải biết BSON, native stream metadata hoặc transaction internals.

### 1.2. Không tự suy domain intent từ mọi field change

`available=8` ở Inventory chưa nói đó là `StockReserved`, `StockReturned` hay correction bởi admin. Nếu hệ nghiệp vụ cần phân biệt, hãy lưu sự kiện rõ nghĩa ở source/outbox thay vì suy đoán bằng hiệu của hai snapshots.

### 1.3. Thứ tự raw CDC và thứ tự domain không luôn trùng

Một transaction có thể có nhiều updates; connector có batching, retries và partitions. Cần xác định phạm vi mà engine/connector bảo đảm thứ tự và ánh xạ sang stream nghiệp vụ.

## 2. Các định danh không được dùng thay nhau

| Trường | Định danh | Câu hỏi về phạm vi |
|---|---|---|
| `eventId` | Một sự kiện logic | Unique trong namespace nào? |
| `commandId` | Một ý định nghiệp vụ | Một command sinh bao nhiêu events? |
| `aggregateId` | Một thực thể | Có scope tenant/type không? |
| `aggregateType` | Loại aggregate | `Order`, `InventoryItem`, `Payment` |
| `tenantId` | Phạm vi dữ liệu khách hàng | Có được xác thực không? |
| `partitionKey` | Đầu vào quyết định routing | Có ổn định qua updates không? |
| `partitionId` | Partition log/stream | Có thể đổi khi reshard/repartition không? |
| `offset` | Vị trí trong partition log | Không so xuyên partitions |
| `eventSequence` | Thứ tự sự kiện trong một stream | Ai cấp số, có liên tục không? |
| `aggregateVersion` | Phiên bản state của aggregate | Có một hay nhiều events mỗi version? |
| `sourceTransactionId` | Nhóm changes trong một transaction nguồn | Có scope, retention gì? |
| `resumeToken` | Vị trí tiếp tục CDC | Opaque và theo nguồn/API |
| `correlationId` | Chuỗi xử lý cùng business request | Không tự là event order |
| `causationId` | Sự kiện/lệnh gây ra event hiện tại | Hữu ích để vẽ causal chain |
| `schemaVersion` | Phiên bản encoding event payload | Không phải source revision |
| `occurredAt` | Thời điểm theo clock policy | Không chứng minh global order |

### 2.1. Tại sao `eventId` không phải `aggregateId`?

Đơn hàng O-100 có thể phát `Created`, `Confirmed`, `Canceled`; nếu mọi event đều có ID O-100, consumer dùng ID làm dedupe sẽ bỏ mất các transitions hợp lệ.

### 2.2. Tại sao `eventId` không phải `commandId`?

Một command checkout có thể tạo `OrderConfirmed`, `InvoiceRequested` và `OutboxNotificationRequested`. Cùng commandId, nhưng chúng là **những events khác nhau**.

### 2.3. Tại sao `eventId` không phải offset?

Offset 42 có thể tồn tại đồng thời trên partition 0 và 1. Sau rebootstrap/migration, cùng logical event cũng có thể được publish lại tại vị trí transport mới.

### 2.4. Tại sao `schemaVersion` không phải `aggregateVersion`?

Đổi event schema từ v1 sang v2 không có nghĩa Order state vừa tăng một phiên bản. Hai dimensions phải quản lý riêng.

## 3. Thiết kế event envelope bền vững

Một envelope minh họa:

~~~json
{
  "eventId": "evt-8d91",
  "eventType": "OrderConfirmed",
  "eventSchemaVersion": 2,
  "tenantId": "tenant-A",
  "aggregateType": "Order",
  "aggregateId": "O-100",
  "eventSequence": 41,
  "aggregateVersion": 17,
  "partitionKey": "tenant-A|Order|O-100",
  "commandId": "cmd-confirm-100",
  "correlationId": "checkout-900",
  "causationId": "evt-order-created-100",
  "occurredAt": "2026-11-14T09:00:00Z",
  "payload": {
    "status": "CONFIRMED",
    "totalMinor": 250000,
    "currency": "VND"
  }
}
~~~

Đây là **hợp đồng tự thiết kế**, không phải format mặc định của Kafka, Redis Streams hoặc MongoDB. `partitionKey` trong JSON chỉ là metadata; khi publish phải thực sự dùng key phù hợp ở client broker.

### 3.1. `eventSequence` có thể khác `aggregateVersion`

Một state mutation có thể phát nhiều integration events. Aggregate version 17 có thể sinh event sequences 41 và 42; không tự đồng nhất hai field nếu thiết kế không bảo đảm một event/one version.

### 3.2. Định danh phải được tạo một lần

Publisher retry **không sinh eventId mới**. Stable event ID nên được lưu trong outbox/source event record, có thể tái phát cùng payload/schema khi mất ACK.

### 3.3. Thời gian không là bằng chứng nhân–quả

`occurredAt` có thể do JVM clock tạo, `publishedAt` muộn vài phút, consumer nhận muộn vì backlog. Dùng timestamps cho observability và business deadlines, không kết luận một event causally sau event khác chỉ từ milliseconds.

### 3.4. Không lấy payload hash làm event identity

Hai users có thể cùng gửi `status=ACTIVE`, payload bằng nhau nhưng command khác. Hash còn phụ thuộc canonical serialization, nested order và representation. Dedupe theo stable ID, không theo equality của payload.

## 4. Một command, nhiều attempts và nhiều events

~~~mermaid
flowchart TD
    USER["User bấm Confirm"] --> CMD["Command cmd-77"]
    CMD --> REQ1["HTTP attempt 1"]
    CMD --> REQ2["HTTP retry 2"]
    REQ1 --> TX["Source transaction commit"]
    REQ2 --> RES["Resolve command outcome"]
    TX --> E1["Event evt-101: OrderConfirmed"]
    TX --> E2["Event evt-102: InvoiceRequested"]
    E1 --> SEND1["Broker send attempt A"]
    E1 --> SEND2["Broker retry B"]
~~~

### 4.1. `commandId` giữ ý định qua retry

Nếu request đầu đã commit nhưng ACK mất, request sau với cùng `commandId` phải không làm mutation lần hai. Reuse cùng commandId với payload khác nên bị coi là idempotency mismatch.

### 4.2. `eventId` giữ sự kiện qua publish retry

Đã tạo event `evt-101`, hai lần gửi vẫn là `evt-101`. Consumer có thể nhận hai copies và loại lần lặp mà không bỏ một event mới.

### 4.3. Trace ID không phải business ID

Mỗi network attempt có thể có requestId/traceId mới. Chúng phục vụ quan sát; không dùng thay commandId hoặc eventId.

### 4.4. Causation liên kết các bước

`PaymentAuthorized` có thể ghi `causationId=OrderConfirmed.eventId`. Đây là cạnh trong causal graph, không biến mọi events chia sẻ correlationId thành một log có thứ tự toàn phần.

## 5. Mỗi ID có phạm vi duy nhất riêng

Một UUID/ULID được sinh đúng có thể có xác suất trùng rất thấp, nhưng **thứ tự từ điển của ID** không phải commit order. Một ID chứa timestamp không tự phản ánh thứ tự các transactions giữa hai regions bị lệch đồng hồ.

### 5.1. Event namespace

Dedupe key có thể là `(producerNamespace,eventId)` hoặc `(tenantId,eventId)` theo hợp đồng. Không mặc định một chuỗi ngắn `"42"` unique toàn hệ.

### 5.2. Aggregate identity

Thực thể nên được định danh bằng `(tenantId,aggregateType,aggregateId)` nếu IDs chỉ unique trong tenant. Cùng `O-100` ở tenants khác nhau không phải một stream.

### 5.3. Transport identity

Kafka-like position cần `(topic,partition,offset)`; DynamoDB Streams cần stream/shard/sequence scope; Redis cần stream key + entry ID. Không bỏ phần scope khi lưu checkpoint.

### 5.4. Resume token opaque

Đừng parse CDC resume token để suy ngày giờ, business version hoặc ID lâu dài khi nhà cung cấp chỉ cam kết nó là bookmark.

### 5.5. ID ổn định có thể cần giữ lâu hơn transport

Sau khi broker xóa log do retention, application có thể vẫn cần `eventId`/command ledger cho audit và chống retry xa. Xác định retention riêng cho identity, payload, inbox và outbox.

## 6. “Thứ tự” tồn tại ở nhiều điểm

Một pipeline thường có:

1. **Business decision order** tại service nhận commands.
2. **Source commit order** tại cơ sở dữ liệu gốc.
3. **CDC observation order** ở connector.
4. **Publication order** khi publisher gửi.
5. **Broker append order** trong partition log.
6. **Delivery order** tới consumer.
7. **Processing start order** khi workers bắt đầu.
8. **Effect commit order** của projection/DB đích.
9. **Visibility order** mà user quan sát.

### 6.1. Các thứ tự có thể khác nhau

~~~text
Source commits:
    O-100 seq 41
    O-100 seq 42

Publisher:
    worker A delayed publishing 41
    worker B publishes 42

Broker:
    append 42, then 41
~~~

Nếu publisher không bảo vệ per-key sequence, đúng source commit order **không tự giữ** ở broker.

### 6.2. Delivery đúng thứ tự vẫn có thể apply sai

~~~text
Consumer receives seq 41, then 42.
Worker 41 waits 100 ms.
Worker 42 commits in 5 ms.
Worker 41 commits later and overwrites 42.
~~~

Application phải có per-key serial processing hoặc version/sequence guard atomically tại sink.

### 6.3. Thứ tự user nhìn thấy là một vấn đề khác

Một read model eventual có thể còn trạng thái 41 trong khi source đã version 42. Broker lag=0 chưa chứng minh mọi client đã thấy state mới nếu cache/projection riêng bị stale.

## 7. Partial order, causality và global total order

Ký hiệu \(a \rightarrow b\) là quan hệ **happens-before**: a là tiền nhiệm nhân–quả của b. Quan hệ ấy có thể đến từ thứ tự trong một process, gửi–nhận message hoặc tính bắc cầu.

~~~text
Order O-100 Confirmed --> Order O-100 Shipped

Order O-200 Confirmed

Không có bằng chứng O-200 Confirmed trước/sau
O-100 Shipped về mặt nhân–quả.
~~~

### 7.1. Concurrent trong hệ phân tán

Hai events cách nhau vài phút theo wall-clock vẫn có thể không có causal relationship nếu producers độc lập, partition mạng và chưa trao đổi context.

### 7.2. Total order là thứ tự được chọn/chứng nhận

Một single sequencer hoặc ordered consensus log có thể sắp tất cả entries trong một scope. Nhưng dùng total order như vậy có chi phí coordination, latency và throughput bottleneck.

### 7.3. Logical clocks không thay mọi scope

Lamport clock có \(a\rightarrow b\Rightarrow L(a)<L(b)\); chiều ngược không đúng. Hybrid logical clocks có thể giúp ordering gần wall clock, nhưng vẫn không biến mọi cặp IDs/timestamps thành causal proof.

### 7.4. Không sort timestamps để sửa lịch sử

Hai regions có clock skew; một event tạo trước về nhân–quả có timestamp lớn hơn event sau. Sort theo `occurredAt` có thể đảo order; sort theo receive time còn phụ thuộc network lag.

## 8. Partition key, partition và stream

**Aggregate key** định danh dòng lịch sử của một thực thể. **Partition key** giúp chọn nơi ghi/read. **Partition** là đơn vị ordering/storage theo broker hoặc database.

~~~text
Topic orders.events:
    P0: offset 10, 11, 12...
    P1: offset 10, 11, 12...
    P2: offset 10, 11, 12...

hash(tenant-A|Order|O-100) -> P1
hash(tenant-A|Order|O-200) -> P2
~~~

Hàm hash ở đây minh họa, không khẳng định SDK nào có đúng thuật toán ấy.

### 8.1. Per-key ordering

Nếu tất cả events của O-100 đến một ordered partition và publisher phát theo thứ tự, consumer xử lý/commit theo thứ tự, hệ có thể duy trì **per-Order ordering**.

### 8.2. Per-partition ordering

Một log append đơn trong partition thường có thứ tự offsets, kể cả khi chứa nhiều keys. Tuy nhiên, consumer có thể parallelize và phá thứ tự apply nếu không điều phối.

### 8.3. Per-topic không mặc định globally ordered

Topic có nhiều partitions có nhiều sequences độc lập. Không tồn tại một offset tổng cho toàn topic khi không có protocol riêng.

### 8.4. Source partition khác broker partition

Cosmos logical partition, DynamoDB stream shard, MongoDB shard, Kafka partition và Cassandra partition key không phải một khái niệm duy nhất. Scope ordering của mỗi hệ phải đọc theo API/version/topology.

## 9. Ví dụ hai partitions: offsets không so được

~~~text
P0:
    offset 100 -> O-100 seq 41
    offset 101 -> O-100 seq 42

P1:
    offset 100 -> O-200 seq 7
    offset 101 -> O-200 seq 8
~~~

`P0:101` và `P1:100` không thể so bằng offset. Một consumer có thể thấy O-100:41, O-200:7, O-100:42, O-200:8; consumer khác thấy O-200:7, O-200:8, O-100:41, O-100:42. Cả hai vẫn hợp lệ nếu mỗi Order giữ đúng thứ tự nội bộ.

### 9.1. Offset không phải aggregateVersion

Offset 102 của P0 có thể thuộc O-999; nó không nói O-100 đã tăng eventSequence từ 101 lên 102.

### 9.2. Một partition toàn topic có tradeoff

Gom mọi events vào P0 có thể tạo total append order trên log, nhưng giảm parallelism, tăng hot partition và không tự bảo đảm nguồn đã phát đúng business order.

### 9.3. Không yêu cầu global order nếu business không cần

Ứng dụng có 10 triệu Orders thường chỉ cần mỗi Order có lịch sử hợp lệ. Total-order across unrelated Orders tạo coordination không mang lại giá trị tương xứng.

## 10. Chọn khóa phân vùng từ aggregate identity

Một key dễ hiểu:

~~~text
partitionKey = encode(tenantId, aggregateType, aggregateId)
~~~

### 10.1. Không partition bằng eventId ngẫu nhiên

`OrderCreated` và `OrderConfirmed` cùng O-100 nhưng eventIds khác có thể rơi hai partitions, mất ordering theo Order.

### 10.2. Không partition bằng field thay đổi

Nếu key dựa trên `status`, Order chuyển `PENDING` sang `CONFIRMED` và `CANCELED` có thể bị chuyển partition đúng lúc thứ tự quan trọng nhất.

### 10.3. Tenant scope và collision

O-100 trong tenant A và B phải khác logical aggregate streams. Encoding dạng nối chuỗi cần escape/length-prefix để không bị delimiter ambiguity.

### 10.4. Hot key vs hot tenant

Key chỉ là tenantId khiến whale tenant dồn lên một partition. Key `(tenantId,orderId)` phân tải tốt hơn nhưng **đổi guarantee** từ tenant-wide ordering sang per-order ordering.

### 10.5. Sequence authority vẫn bắt buộc

Cùng key vào một partition không làm source hai writers đồng thời có version đúng. Source phải dùng CAS, transaction hoặc append protocol có authority.

## 11. Hai writers đồng thời và event sequence

Hai instances cùng đọc Order version 40, cả hai muốn chuyển state:

~~~text
Writer A: confirm, propose event seq=41.
Writer B: cancel, propose event seq=41.
~~~

Nếu mỗi worker tự tăng counter từ snapshot cũ, cả hai có thể ghi hai events cùng sequence.

### 11.1. Atomic conditional write

~~~text
IF order.version=40 AND status=PENDING:
    order.status=CONFIRMED
    order.version=41
    insert outbox(eventId=evt-A, eventSeq=41)
COMMIT in supported transaction boundary
~~~

Writer B phải re-read/revalidate hoặc trả business conflict theo contract. Không “sửa” tình huống này bằng cách sort broker timestamps.

### 11.2. Một aggregate version có thể sinh nhiều events

Nếu một update phát event 41 và 42, cần allocate **eventSequence** riêng hoặc một ID trong nhóm commit để định nghĩa thứ tự. Không tự đặt cả hai `seq=41` rồi kỳ vọng consumer hiểu.

### 11.3. Sequence có thể có gaps do rollback

Nếu sequence được cấp trước commit bằng counter riêng, transaction abort có thể để lại gap. Nếu hợp đồng consumer yêu cầu contiguous numbers, thiết kế cấp sequence phải hỗ trợ; nếu không, phải ghi rõ gaps được phép.

### 11.4. Không tin sequence client tự cấp

Mobile offline có thể tự đưa `eventSequence=9999`; authority cần kiểm/quy đổi theo protocol. Sequence không phải trường metadata tự khai tùy ý khi quyết định state.

## 12. Transactional outbox giữ trạng thái và event cùng nhau

Hai lệnh độc lập:

~~~text
1. Update Order in NoSQL.
2. Publish OrderConfirmed to broker.
~~~

gây failure window nếu crash giữa hai bước.

### 12.1. Mẫu đúng về mặt ý định

~~~mermaid
sequenceDiagram
    participant API as Application
    participant DB as NoSQL Source
    participant PUB as Outbox Publisher
    participant LOG as Event Broker
    API->>DB: Validate Order, write state + outbox together
    DB-->>API: Source commit ACK
    PUB->>DB: Read persisted outbox entry
    PUB->>LOG: Publish eventId with aggregate key
    LOG-->>PUB: Broker ACK
    PUB->>DB: Persist sent/checkpoint marker
~~~

### 12.2. Phạm vi atomicity phải thật

Một số NoSQL hỗ trợ transaction nhiều records trong scope cụ thể, số khác chủ yếu atomic single-item/partition. Nếu Order và outbox ở hai partitions không hỗ trợ giao dịch chung, không được gọi hai writes là atomic outbox chỉ vì cùng method Java.

### 12.3. Stable eventId trong outbox

Source commit lưu eventId, partition key, sequence, payload/schema version. Publisher retry đọc **cùng record**, không sinh ID mới khi gọi `send()`.

### 12.4. Mark-as-sent không chứng minh exactly once

Broker append thành công nhưng ACK mất; publisher không mark-sent rồi gửi lại. Consumer phải idempotent hoặc có giao thức exactly-once trong **phạm vi được chứng minh**.

### 12.5. Publisher concurrency có thể đảo order

Hai pollers đọc seq 41 và 42 của cùng Order; poller 42 gửi trước. Cần per-key ordered dispatch/lease, sequence barrier hoặc consumer guard.

## 13. CDC record, source log position và resume token

CDC có thể đọc commit logs, change streams, write-ahead logs hoặc change feed. Connector lưu **vị trí nguồn**:

~~~text
sourceCheckpoint = (resource, stream/shard identity, token/position)
~~~

### 13.1. Checkpoint để restart

Nếu connector crash, checkpoint giúp đọc tiếp. Lưu checkpoint trước khi downstream durable ACK có nguy cơ bỏ event; lưu sau ACK có thể tạo duplicate khi crash giữa hai bước.

### 13.2. Resume token không mặc định là eventId

Token giúp tiếp tục một stream theo API. Nó có thể phụ thuộc resource, stream generation và retention. Đừng parse nó để suy globally ordered business event ID.

### 13.3. Raw CDC có thể nhiều records cho một nghiệp vụ

Xác nhận Order cập nhật Order, Inventory và Outbox; nguồn có thể phát nhiều changes. Consumer phải biết domain contract hoặc transaction grouping nếu muốn sự kiện có nghĩa.

### 13.4. Cùng source transaction không tạo atomic view ở mọi downstream partitions

Một DB commit atomic nhiều items nhưng CDC translator đưa changes sang nhiều partitions. Consumer ở partition A có thể cập nhật xong trước B. Nếu cần coordinated multi-entity snapshot, phải thiết kế protocol bổ sung.

### 13.5. CDC retention có giới hạn

Connector đứng lâu quá cửa sổ change history có thể không thể resume. Cần alert, rebootstrap snapshot và reconciliation thay vì âm thầm bỏ gaps.

## 14. Kafka: thứ tự gắn với partition

Một Kafka-like topic gồm nhiều partitions, mỗi partition có offset sequence riêng:

~~~text
orders.events:
  partition 0: offset 0, 1, 2...
  partition 1: offset 0, 1, 2...
  partition 2: offset 0, 1, 2...
~~~

### 14.1. Key routing

Producer dùng key ổn định `(tenantId,Order,orderId)` để các events cùng Order đi vào cùng partition theo partitioner đang dùng. Nếu publisher gửi đúng thứ tự và consumer xử lý có guard, giữ được per-key order.

### 14.2. Idempotent producer không tự đảm bảo end-to-end exactly once

Producer/broker có các protocol chống duplicate do retry trong một phạm vi nhất định. Chúng không tự tạo atomic transaction giữa Order NoSQL, Kafka log, consumer Redis projection và email gateway.

### 14.3. Consumer group rebalance

Partition có thể chuyển từ worker cũ sang worker mới. Nếu worker cũ đang xử lý dở, cần offset commit/ownership fencing và idempotency; không lấy consumer instance ID làm stream identity.

### 14.4. In-flight sends và retry

Producer gửi seq 41 rồi 42 nhưng 41 gặp retry; ordering guarantee phụ thuộc client configuration/idempotence/protocol. Không suy `send()` được gọi trước nghĩa broker luôn append trước trong mọi cấu hình.

### 14.5. Partition count thay đổi

Một hash partitioner phụ thuộc số partitions có thể map cùng key sang partition khác khi tăng partitions. Cần kế hoạch barrier/drain/cutover khi strict per-key order phải giữ xuyên thay đổi topology.

## 15. Java Kafka producer: gửi cùng key và ID ổn định

Ví dụ Java với Kafka client API:

~~~java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public record OutboxEntry(
    String eventId,
    String aggregateKey,
    String jsonEnvelope
) {}

public final class OutboxPublisher {
    private final KafkaProducer<String, String> producer;

    public OutboxPublisher(KafkaProducer<String, String> producer) {
        this.producer = producer;
    }

    public void publish(OutboxEntry entry) {
        var record = new ProducerRecord<String, String>(
            "orders.events",
            entry.aggregateKey(),
            entry.jsonEnvelope()
        );
        record.headers().add(
            "event-id",
            entry.eventId().getBytes(StandardCharsets.UTF_8)
        );

        producer.send(record, (metadata, exception) -> {
            if (exception != null) {
                scheduleDurableRetry(entry.eventId(), exception);
            } else {
                recordAcknowledgement(
                    entry.eventId(),
                    metadata.partition(),
                    metadata.offset()
                );
            }
        });
    }

    private void scheduleDurableRetry(String id, Exception error) {
        // Application-specific durable dispatch state.
    }

    private void recordAcknowledgement(
        String id, int partition, long offset
    ) {
        // Application-specific checkpoint/outbox transition.
    }
}
~~~

### 15.1. Điều quan trọng trong ví dụ

`eventId` đến từ outbox, không được sinh mới mỗi lần retry. Kafka key đi theo aggregate, không đi theo eventId.

### 15.2. Điều ví dụ chưa bảo đảm

Chưa có durable retry worker, broker configuration, transaction producer, sender ordering, deadline/backpressure, poison event handling hoặc graceful shutdown. Chỉ là minh họa ranh giới identity/publishing, không phải library production.

### 15.3. Commit offset không đủ cho ứng dụng đích

Producer nhận broker offset khi append; consumer cần lưu tiến độ của **projection effect** riêng, không suy từ broker ACK rằng mọi consumers đã xử lý.

## 16. MongoDB change streams và resume token

MongoDB change streams theo dõi thay đổi trên resource/scope được hỗ trợ và cung cấp resume token cho việc đọc tiếp.

### 16.1. Token là opaque

Không tự parse change event `_id` để lấy global sequence, nhân–quả hoặc `eventId` domain. API chỉ bảo đảm các ý nghĩa của token theo documented stream semantics.

### 16.2. Change stream order và downstream order

Một stream có thể có guarantees về thứ tự thay đổi trong scope của nó, nhưng khi connector publish sang broker nhiều partitions hoặc consumer song song, end-to-end apply order có thể khác.

### 16.3. Full document lookup

Nếu connector lấy full document cho một update, phải hiểu lookup policy/snapshot semantics; document có thể đã đổi tiếp tại thời điểm lookup. Không tự coi nó luôn là exact post-image của event nếu API không cung cấp bảo đảm đó.

### 16.4. Change event không nhất thiết là domain event

Một update `status=CONFIRMED` từ migration không tự là lệnh xác nhận hợp lệ. Đặt domain meaning trong outbox hoặc translator có business context.

### 16.5. Resume không phải vĩnh viễn

Oplog/history retention hoặc topology/resource changes có thể làm token cũ không usable. Connector cần rebootstrap, version reconciliation và idempotent replay.

## 17. DynamoDB Streams: shard scope

DynamoDB Streams tổ chức changes với stream/shard và sequence number/iterator semantics. Chúng phục vụ checkpoint và xử lý events trong scope tương ứng.

### 17.1. Không so sequence numbers giữa shards

Sequence ở shard A và B không thuộc cùng một thước đo tổng thứ tự cho mọi items. Checkpoint cần stream identity, shard ID và vị trí theo API.

### 17.2. Ordering của cùng item

DynamoDB có những guarantees cho thay đổi của cùng item; cần đọc chính xác scope và stream view mode của API/SDK đang dùng. Không suy thành global ordering xuyên cả table hoặc regions.

### 17.3. Shard lifecycle

Shards có thể đóng và stream ownership thay đổi. Consumer phải quản lý parent/child shard dependencies và checkpoint theo API, không có một biến `lastSequence` toàn table.

### 17.4. Stream view type

`KEYS_ONLY`, `NEW_IMAGE`, `OLD_IMAGE`, `NEW_AND_OLD_IMAGES` cung cấp dữ liệu khác nhau. Một stream chỉ có keys không tự đủ để dựng domain event đầy đủ nếu source không lưu intent.

### 17.5. Retention/recovery

Stream là nguồn thay đổi có retention hữu hạn, không phải immutable archive không giới hạn. Dừng consumer quá lâu có thể cần snapshot/reconciliation.

## 18. Cosmos DB change feed và logical partition

Cosmos DB for NoSQL có change feed với những modes, ordering và retention semantics cụ thể. **Logical partition key** thường là phạm vi quan trọng cho local transaction và change ordering.

### 18.1. Thứ tự theo logical partition

Nếu deployment/mode bảo đảm thứ tự updates trong một logical partition, không kéo dài nó sang mọi logical partitions hoặc regions. Cần kiểm API version/mode.

### 18.2. Mode quyết định delete semantics

Các change feed modes có thể khác nhau ở việc biểu diễn inserts/updates/deletes và versions được giữ. Nếu consumer cần đồng bộ deletion, không dựa vào một mode không cung cấp delete records như mong đợi.

### 18.3. Lease processor

Các workers sở hữu feed ranges thông qua lease/checkpoints; rebalance có thể đổi worker. Consumer state phải idempotent và không dùng worker identity làm sequence.

### 18.4. Cross-region

Trong multi-writer deployment, conflict resolution/replication semantics có thể thay đổi lịch sử quan sát. Một event đến muộn chưa chắc causally sau một event đến sớm.

### 18.5. Outbox theo transaction scope

Nếu domain mutation và outbox nằm trong cùng supported logical partition transaction, có thể xây atomic intent; nếu khác partition cần kiến trúc khác, không thay bằng hai writes liên tiếp.

## 19. Redis Streams: entry ID khác logical event ID

Redis Streams có các entry IDs và consumer groups:

~~~text
XADD orders:events * eventId evt-101 orderId O-100 type Confirmed
XREADGROUP GROUP projection worker-A COUNT 10 STREAMS orders:events >
~~~

Các lệnh chỉ minh họa cú pháp và cách sử dụng; chưa bao gồm group creation, ACK, retries hoặc error handling.

### 19.1. Stream entry ID

ID đại diện cho một entry trong **một stream** theo Redis rules. Không dùng ID ấy làm globally unique domain event ID khi có nhiều streams.

### 19.2. Publication retry có thể tạo entry mới

Nếu publisher `XADD` lại cùng logical event sau ACK loss, có thể sinh stream entry khác. Stable `eventId` trong fields giúp consumer dedupe.

### 19.3. Consumer groups và PEL

Pending Entries List theo dõi đã giao/chưa ACK. Worker crash có thể dẫn tới redelivery/claim. Consumer không được coi mỗi delivery là một business event mới.

### 19.4. Một stream ordered nhưng consumer effects có thể đảo

Nhiều group workers xử lý song song có thể commit offset lớn trước offset nhỏ. Cần per-key sequence guard hoặc serial processing.

### 19.5. Retention, trimming, memory

Redis Stream trimming/TTL/persistence/replication được triển khai theo policy. Không đặt stream chứa unreplayed financial commands vào cache eviction domain tùy ý rồi mặc định events luôn còn để replay.

## 20. Cassandra/ScyllaDB CDC và local log order

CDC ở Cassandra/ScyllaDB có các triển khai dựa vào commitlog/segments/streams tùy sản phẩm và phiên bản. Một local position trên node không tự là global commit order cho toàn cluster.

### 20.1. Node-local không đồng nghĩa cluster-global

Nhiều replicas, coordinators và partitions có thể nhận mutations theo các đường khác nhau. Muốn một event sequence có meaning cho aggregate, source application cần cấp sequence/identity theo authoritative protocol.

### 20.2. Phân vùng theo primary key

Một partition key giúp giữ locality truy cập nhưng không tự chứng minh mọi CDC records của nhiều nodes có total order cho toàn dataset.

### 20.3. TTL, tombstones và deletion

Physical compaction không tự là business `EntityDeleted`. Muốn có integration event xóa, phải hiểu CDC/deletion semantics, retention và replica repair.

### 20.4. Multi-replica observations

Có pipeline có thể quan sát mutation qua nhiều nguồn/replicas. Không lấy số raw records làm số nghiệp vụ đã xảy ra nếu chưa dedupe theo mutation/domain identity.

## 21. So sánh phạm vi ordering

| Nguồn | Vị trí/đơn vị đặt thứ tự | Không nên suy |
|---|---|---|
| Kafka-like broker | Topic partition + offset | Tổng thứ tự trên mọi partitions |
| Redis Stream | Stream key + entry ID | Total order xuyên streams |
| DynamoDB Streams | Stream/shard sequence và rules theo item | Một số sequence duy nhất toàn table |
| Cosmos DB change feed | Logical partition/range và feed mode | Cross-region/global ordering không điều kiện |
| MongoDB change stream | Stream scope + opaque resume token | Token là business eventId chung |
| Cassandra/Scylla CDC | Node/segment/partition scope theo implementation | Local log offset là global history |
| Transactional outbox | Aggregate key + source-assigned sequence | Publisher tự giữ thứ tự không cần điều phối |
| Event store per aggregate | Expected stream revision | Thứ tự giữa các aggregates |

Các bảo đảm cụ thể phụ thuộc API/version/configuration/topology; bảng chỉ tóm tắt phạm vi cần kiểm, không thay tài liệu sản phẩm.

## 22. Java: domain event envelope không phụ thuộc SDK

Ví dụ Java 17+ với Jackson `JsonNode`:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;

public record IntegrationEvent(
    String eventId,
    String tenantId,
    String aggregateType,
    String aggregateId,
    long eventSequence,
    long aggregateVersion,
    String eventType,
    int schemaVersion,
    String commandId,
    String correlationId,
    String causationId,
    Instant occurredAt,
    JsonNode payload
) {
    public IntegrationEvent {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId required");
        }
        if (tenantId == null || tenantId.isBlank()
                || aggregateType == null || aggregateType.isBlank()
                || aggregateId == null || aggregateId.isBlank()) {
            throw new IllegalArgumentException("identity required");
        }
        if (eventSequence < 1 || aggregateVersion < 0
                || schemaVersion < 1) {
            throw new IllegalArgumentException("invalid version");
        }
        if (payload == null || !payload.isObject()) {
            throw new IllegalArgumentException("object payload required");
        }
        payload = payload.deepCopy();
    }

    public String partitionKey() {
        // Example only: production should use collision-safe encoding.
        return tenantId + "|" + aggregateType + "|" + aggregateId;
    }

    @Override public JsonNode payload() {
        return payload.deepCopy();
    }
}
~~~

### 22.1. DTO validation không cấp sequence

`eventSequence > 0` chỉ là input validation. Sequence phải được source/event store **cấp nguyên tử trong đúng stream scope**; DTO không tự tạo ordering guarantee.

### 22.2. Immutable payload

Jackson JsonNode có mutable implementations; dùng `deepCopy()` để tránh sửa payload sau khi tạo. Production cần schema validation và canonical serialized bytes nếu hash/signature dựa vào payload.

### 22.3. Key encoding

Chuỗi nối bởi `|` chỉ để dễ hiểu. Trong thực tế, nên encode có escaping/length-prefix vì `tenantId`/`aggregateId` có thể chứa delimiter.

### 22.4. Tenant authorization

Không tin field `tenantId` do producer/client bất kỳ tự điền. Broker ACLs, producer identity, API authorization và data residency là trách nhiệm độc lập với event model.

## 23. At-least-once và idempotent consumer

Timeline điển hình:

~~~text
1. Consumer nhận eventId=evt-42.
2. Consumer ghi projection thành công.
3. Consumer crash trước broker offset ACK.
4. Broker giao lại evt-42.
5. Consumer phải không tạo effect lần hai.
~~~

### 23.1. Dedupe event theo stable identity

Dùng `(consumerName, producerNamespace, eventId)` hoặc scope phù hợp. Không chỉ dùng event payload hash hoặc transport delivery ID.

### 23.2. Dedupe và effect phải nhất quán

~~~text
BEGIN supported atomic boundary
    IF inbox contains eventId:
        COMMIT; return DUPLICATE
    validate schema, aggregate, sequence
    update projection
    insert processed-event entry
COMMIT
ACK broker/CDC position after commit
~~~

Nếu projection và inbox ở hai stores độc lập không có transaction chung, cần thiết kế đồng bộ/idempotency protocol khác; không gọi hai writes là atomic.

### 23.3. Dedupe retention

Nếu stream có thể replay 90 ngày nhưng inbox chỉ giữ một ngày, events cũ có thể tạo duplicate effect khi replay. Điều chỉnh TTL/retention hoặc dùng per-aggregate version guards.

### 23.4. External side effects

Consumer gửi email hoặc charge payment rồi crash trước ACK có thể làm tác dụng lặp. Dùng external idempotency key, durable outbox/intent hoặc compensating workflow; không đặt effect không thể undo trong callback có thể tự động retry mà thiếu kiểm soát.

### 23.5. ACK trước khi commit effect là nguy hiểm

Nếu broker offset đã được commit nhưng sink update thất bại, event có thể bị bỏ qua trên lần khởi động sau. Chọn thứ tự commit rõ và thiết kế theo at-least-once + idempotency.

## 24. Per-aggregate sequence guard: duplicate và gap

Consumer lưu `lastAppliedSequence=41` cho O-100:

~~~text
incoming seq=42 -> next event; apply.
incoming seq=41 -> old/duplicate; inspect eventId.
incoming seq=44 -> gap, need 42/43 or snapshot rule.
incoming seq=42 with different eventId after applied 42 -> conflict.
~~~

### 24.1. Cần biết sequence có thực sự liên tục không

Nếu stream cấp sequence cho mọi events nhưng consumer **lọc một số types**, việc thấy 41 rồi 44 có thể bình thường. Muốn phát hiện missing events, sequence phải được định nghĩa cho tập events mà consumer nhận hoặc có metadata về events bị lọc.

### 24.2. Nhận cũ không luôn là duplicate

Một event seq 40 với eventId lạ có thể là sự kiện từng bị bỏ sót, conflict hoặc dữ liệu lỗi. Một latest-state projection có thể bỏ stale event, nhưng financial ledger không thể âm thầm bỏ giao dịch.

### 24.3. Cùng sequence, khác identity

Nếu contract hứa unique sequence per aggregate, hai events khác nhau cùng seq là vi phạm. Không tùy chọn payload đến cuối rồi bỏ record kia như trường hợp retry.

### 24.4. Sequence gap không nên chờ vô hạn

Buffer phải có giới hạn bytes/entries/time. Sau timeout, chuyển sang replay, rebootstrap snapshot, quarantine hoặc incident theo retention/domain policy.

### 24.5. Không skip transition quan trọng

Không áp `OrderShipped` nếu còn thiếu `OrderPaid` và reducer bắt buộc trạng thái Paid. Chỉ được jump bằng latest-state snapshot khi domain cho phép và đã chứng minh bỏ intermediate events không mất side effects.

## 25. Java: hợp đồng apply outcome của consumer

~~~java
public enum ApplyResult {
    APPLIED,
    DUPLICATE_EVENT,
    STALE_SEQUENCE,
    SEQUENCE_GAP,
    CONFLICTING_SEQUENCE,
    UNSUPPORTED_SCHEMA,
    RETRYABLE_STORAGE_FAILURE
}

public interface OrderedProjectionStore {
    // Effect, last sequence and processed event identity must
    // be committed atomically, or use an equivalent safe protocol.
    ApplyResult apply(IntegrationEvent event);
}

public final class OrderedEventHandler {
    private final OrderedProjectionStore store;

    public OrderedEventHandler(OrderedProjectionStore store) {
        this.store = store;
    }

    public ApplyResult handle(IntegrationEvent event) {
        return store.apply(event);
    }
}
~~~

### 25.1. Vì sao handler đơn giản?

Business handler **không** tự read lastSeq rồi update state bằng hai lệnh riêng. `OrderedProjectionStore` chịu trách nhiệm atomic guard trên key `(consumer,tenant,aggregateType,aggregateId)` theo backend contract.

### 25.2. ACK policy theo kết quả

`APPLIED`/`DUPLICATE_EVENT` có thể ACK sau commit. `SEQUENCE_GAP` cần chờ/replay, `UNSUPPORTED_SCHEMA` cần quarantine hoặc upgrade, `RETRYABLE_STORAGE_FAILURE` cần retry có giới hạn.

### 25.3. Không phải mọi stale sequence đều có thể bỏ

Event ledger/accounting yêu cầu giữ tất cả effects. Latest-state cache có thể chỉ cần version mới nhất. `STALE_SEQUENCE` phải được application định nghĩa chứ không auto-drop cho mọi domain.

### 25.4. Output event

Nếu reducer còn phát derived events, chúng cần outbox hoặc transactional stream processing trong scope hỗ trợ. Ghi projection thành công rồi gửi event kế tiếp độc lập có failure window.

## 26. Pseudocode atomically apply theo sequence

~~~text
function apply(event):
    begin supported transaction

    if inbox.contains(consumerName, event.eventId):
        commit
        return DUPLICATE

    state = read aggregateProjection(event.aggregateKey)
    expected = state.lastSequence + 1

    if event.eventSequence > expected:
        abort
        return GAP

    if event.eventSequence < expected:
        abort
        return STALE_OR_CONFLICT

    next = reduce(state, event)
    write projection(next, lastSequence=event.eventSequence)
    insert inbox(event.eventId)
    commit
    return APPLIED
~~~

### 26.1. Không phải mọi NoSQL hỗ trợ transaction hai items

Inbox và projection có thể ở hai partitions. Nếu atomic transaction không có trong scope, hãy co-locate metadata vào một document/item, dùng CAS hoặc protocol an toàn khác; không dựa vào `@Transactional` annotation mà bỏ qua capability.

### 26.2. Deterministic reducer

Cùng event + prior state phải cho cùng next state theo business rules. Không gọi payment gateway hoặc gửi email trực tiếp trong pure reducer mà không có idempotency.

### 26.3. Gaps do filtered topics

Nếu consumer chỉ nhận một subset, một `expected+1` cứng có thể báo gap giả. Hãy định nghĩa per-consumer stream sequence hoặc dùng source state version monotonic với phép update chấp nhận skipped versions.

### 26.4. Dedupe khác ordering

Hai events có ID khác nhau seq 42 và 43 nhưng đến đảo; inbox không phát hiện vấn đề thứ tự. Cần cả event identity **và** version/sequence guard.

## 27. Late, duplicate và out-of-order: chính sách rõ

Một consumer nhận events `41, 43, 42` cho O-100:

~~~text
Receive 41 -> apply.
Receive 43 -> detect gap for 42; buffer/pause.
Receive 42 -> apply.
Resume 43 -> apply.
~~~

### 27.1. Bounded per-key buffer

Đặt giới hạn count/bytes/age; tránh giữ một map vô hạn theo aggregate và bị OOM khi một event bị mất vĩnh viễn.

### 27.2. Replay from source

Nếu event store cho fetch by aggregate sequence, consumer có thể yêu cầu 42. Nếu CDC chỉ có partition cursor, có thể phải rewind checkpoint hoặc rebootstrap. Không giả định mọi NoSQL có API “get event by sequence”.

### 27.3. Pause phạm vi nhỏ nhất

Nếu ordering cần theo Order, có thể pause riêng key/partition tùy framework; không block cả cluster chỉ vì một aggregate. Nhưng một Kafka partition có processing order scope, việc bỏ qua event đầu để tiếp tục phải có guard.

### 27.4. Dead-letter queue

Một event không parse được có thể chặn partition. Chuyển DLQ giúp vận hành nhưng có thể phá invariant nếu consumer tiếp tục event sau. Cần lưu raw payload, original position, error category, event identity và replay plan.

### 27.5. Quarantine không phải xóa event

Poison event nên được quản lý như một exception có thể điều tra; không coi việc ACK+drop là đạt exactly-once.

## 28. Cross-partition workflow dùng causation, không giả global order

Checkout có nhiều aggregates:

~~~mermaid
flowchart TD
    OC["OrderCreated O-100"] --> RC["ReserveInventory cmd-R1"]
    RC --> IR["InventoryReserved R1"]
    IR --> PC["AuthorizePayment cmd-P1"]
    PC --> PA["PaymentAuthorized P1"]
    PA --> CONF["OrderConfirmed O-100"]
~~~

Inventory, Payment và Order có thể thuộc ba event streams/partitions độc lập.

### 28.1. Causal dependency khác arrival order

Payment event có thể được giao tới orchestrator trước inventory event do paths khác nhau. Orchestrator dựa vào workflow state/commands/correlation để biết prerequisites, không chỉ sort timestamps.

### 28.2. Saga state

Coordinator lưu `WAITING_FOR_INVENTORY`, `WAITING_FOR_PAYMENT`, `CONFIRMED`, `COMPENSATING` với stable command IDs. Nó có thể xử lý duplicates và events đến trễ theo state machine.

### 28.3. Idempotency mỗi service

Inventory reserve theo reservationId; Payment charge theo idempotency key; Order confirm theo state/version. Kafka order không thay các guard ở nguồn.

### 28.4. Không sửa oversell bằng sắp xếp events

Hai regions đã ACK reserve 8 từ stock 10 thì sorting sự kiện sau đó không tự hoàn tác lời hứa với users. Invariant phải được bảo vệ tại commit hoặc có escrow/compensation.

## 29. Global order có cần thiết không?

Một số nghiệp vụ cần một sequencer/consensus log cho một scope, nhưng cái giá là thêm coordination và giới hạn parallelism.

### 29.1. Thứ tự tối thiểu thường tốt hơn

Nếu chỉ cần per-order order, partition theo Order; không ép tất cả Orders đi qua một Kafka partition toàn hệ.

### 29.2. Global sequence phải có nguồn cấp đáng tin

Một counter phát trước commit có thể để lại gaps do aborted transactions; số nhỏ hơn không chứng minh effect được visible trước event số lớn hơn.

### 29.3. External consistency mạnh hơn tùy ý total order

Muốn guarantees theo real-time completed operations cần protocol và clock/failure assumptions khác so với việc gán một số tăng khi nhận request.

### 29.4. “Không có global order” không đồng nghĩa vô tổ chức

Per-aggregate sequences, causal IDs, idempotency, saga states và per-partition checkpoints đủ cho rất nhiều kiến trúc mà không cần global lock.

## 30. Tăng partitions và di chuyển key

Một hệ tăng Kafka partitions từ 8 lên 16:

~~~text
Before:
    O-100 -> partition 3, seq 1..100

After:
    O-100 -> partition 11, seq 101..
~~~

Consumer P11 có thể xử lý 101 trước khi P3 hoàn tất 100, dù mỗi partition vẫn tự ordered.

### 30.1. Stable hash mapping không tự có

Với partitioner phụ thuộc partition count, thay số partitions có thể đổi mapping. Phải review cách key được route trong client/broker version cụ thể.

### 30.2. Barrier và drain

Một cách là dừng/đóng routing cũ cho key, ghi barrier/checkpoint, drain old partition, chuyển epoch và mở publication mới. Hệ thống cần protocol chống old publisher tiếp tục ghi sau cutover.

### 30.3. Virtual shards

Một bảng mapping virtual partition→physical partition có thể hỗ trợ di chuyển có kiểm soát. Nhưng ownership epoch, fencing, replay và lag vẫn cần thiết kế.

### 30.4. Đổi key là đổi contract

Từ per-tenant key sang per-order key: thứ tự tenant-wide không còn được hứa. Đừng coi đây chỉ là tối ưu performance trong PR.

### 30.5. Historical replay

Replaying old and new partitions cần merge theo aggregate sequence và migration checkpoint. Không dùng `max(offset)` vì offsets ở hai scopes khác nhau.

## 31. Snapshot + CDC: chồng lấp và khoảng trống

Một consumer mới xây read model từ snapshot rồi đọc changes:

~~~text
Snapshot contains Order O-100 state version 42.

CDC around bootstrap:
    O-100 version 41
    O-100 version 42
    O-100 version 43
~~~

### 31.1. Cần source checkpoint/high-water mark đúng

Snapshot phải có cách liên hệ với change-stream position theo DB/bootstrap protocol. Một `System.currentTimeMillis()` ở application không đủ tạo consistent snapshot xuyên shards.

### 31.2. Overlap có thể chấp nhận nếu idempotent

Nếu snapshot đã chứa v42, có thể bỏ updates cũ ≤42 theo semantics latest-state projection rồi áp v43, nếu nguồn/version thực sự hỗ trợ. Không áp v41 đè v42.

### 31.3. Không mất deletes

Snapshot có Product đã bị xóa ngay sau khi scan, CDC delete bị skip thì projection hồi sinh. Tombstone/deletion semantics phải nằm trong bootstrap plan.

### 31.4. Retention có thể làm bootstrap bất khả thi

Nếu snapshot chạy ba ngày nhưng CDC chỉ giữ history ngắn hơn, connector không bắt kịp từ start checkpoint. Cần tăng capacity/retention, chia snapshot hoặc restart với protocol khác.

### 31.5. Snapshot không thay replay business effects

Latest-state search projection có thể bootstrap từ snapshot. Financial ledger/email workflow cần mọi required events/side effects; không tự skip lịch sử bằng một state snapshot.

## 32. Retention, compaction và tombstones

**Broker retention** xóa log entries theo thời gian/kích thước, không có nghĩa Order bị xóa khỏi NoSQL source.

### 32.1. Log compaction

Compacted topic có thể lưu latest value per key và bỏ intermediate updates, thích hợp cho state changelog. Nó không phù hợp nếu consumer cần mọi business transaction/event như ledger.

### 32.2. Tombstone

Tombstone trong compacted stream báo xóa key theo log protocol. Nó khác source TTL, application `OrderDeleted` event và physical purge của database. Contract cần mapping rõ.

### 32.3. Replay horizon

Không thể hứa đọc lại “từ đầu thời gian” khi source/broker đã trim. Consumer mới phải seed authoritative snapshot rồi catch-up khi lịch sử không đủ.

### 32.4. Dedupe store retention

Nếu replay 30 ngày mà inbox dedupe records expire sau một giờ, replay có thể double-apply. Align các cửa sổ này hoặc dùng state/version-aware replay.

### 32.5. Delete và privacy

Sự kiện có PII có thể tồn tại lâu trong logs, DLQ, backup. Xóa entity ở source không tự xóa mọi bản sao event; cần retention/erasure strategy và quyền replay.

## 33. Checkpoint transport và progress nghiệp vụ

Một consumer thường cần theo dõi:

~~~text
Transport position:
    topic=orders.events, partition=3, offset=12345

Domain progress:
    (tenant-A, Order, O-100) lastEventSeq=42
~~~

### 33.1. Transport checkpoint

Cho biết vị trí restart đọc một partition/stream. Nó không chứng minh Order O-100 đã áp tới seq 42 nếu pipeline lọc events, xử lý song song hoặc commit offset sớm.

### 33.2. Domain progress

Cho biết tiến độ projection per aggregate. Nó cần đi cùng effect/dedupe trong atomic boundary để không hiển thị `lastSeq=42` mà effect 42 chưa commit.

### 33.3. Commit effect trước rồi ACK

Một pattern at-least-once: apply effect atomically với inbox/progress, sau đó ACK offset. Crash giữa hai bước gây duplicate, nhưng inbox giúp không áp lần nữa.

### 33.4. Exactly-once luôn có phạm vi

Một hệ có thể đạt transactional consume–transform–produce trong cùng broker, nhưng external NoSQL database và HTTP payment không tự tham gia transaction đó. Khi nói “exactly once”, phải nêu nguồn, sink và commit boundary.

### 33.5. Checkpoint sau poison event

Skip để tiến offset có thể bỏ qua một transition cần thiết. Cần quarantine/audit và quyết định domain rõ ràng trước khi bỏ event.

## 34. Unknown publication/commit outcomes

Publisher gửi `evt-42`; broker append xong nhưng response bị mất:

~~~text
Publisher does not know if append succeeded.
Retry same outbox entry with same eventId.
Consumer sees one or more deliveries of logical evt-42.
Inbox and version guards prevent double effect.
~~~

### 34.1. Không sinh ID mới khi retry

Một ID mới khiến consumer tưởng đó là một sự kiện khác. Attempt có requestId mới là bình thường; eventId phải không đổi.

### 34.2. Retry có thể làm đảo thứ tự

Nếu 42 đang retry nhưng publisher cho 43 đi tiếp, log có thể nhận 43 trước. Per-key dispatch, producer settings và consumer guard cần hỗ trợ contract.

### 34.3. Retry budget

Transient errors có thể backoff/jitter; invalid schema/permission thường không retry vô hạn. Unknown outcome cần resolve/checkpoint strategy.

### 34.4. Source commit khác event publication

Ứng dụng không được trả `OrderConfirmed` chỉ vì broker publish đã thành công nếu state transaction ở source chưa commit. Ngược lại, source committed nhưng event pending publish phải có outbox recovery.

## 35. Bảo mật, provenance và multi-tenancy

### 35.1. Source authenticity

Consumer cần xác minh publisher/topic ACLs, producer identity và schema permissions. Một client tự gửi `eventSequence=999999` không được quyền cập nhật state vì ID trông lớn.

### 35.2. Tenant scope

Aggregate key, inbox dedupe và authorization cần tenant identity đúng. Event cùng `orderId=100` từ hai tenants không được ghi đè vào cùng projection.

### 35.3. Data residency

CDC/broker/backup có thể truyền payload sang region khác. Nếu tenant bị ràng buộc địa lý, phải kiểm source, sink, replication, DLQ và observability.

### 35.4. Payload minimization

Đừng phát raw customer document với PII cho mọi services khi consumer chỉ cần orderId/status. Event history có thể được lưu lâu và replay nhiều lần.

### 35.5. Replay là hành động có quyền

Biết resume token hoặc eventId không phải authorization token. Endpoint/tool replay phải được bảo vệ và ghi audit.

## 36. Observability đo theo đúng phạm vi

| Metric | Câu hỏi |
|---|---|
| Source commit→CDC lag | Connector chậm bao lâu? |
| CDC→broker lag | Publisher có backlog không? |
| Broker partition lag | Partitions nào chậm? |
| Oldest outbox age | Event nào chưa publish? |
| Consumer apply latency | Sink effect chậm không? |
| Duplicate eventId count | Retry/redelivery mức nào? |
| Per-aggregate gap count | Có missing/out-of-order không? |
| Conflicting sequence count | Có source sequence violation? |
| DLQ and poison backlog | Event không xử lý được? |
| Rebalance/restart count | Ownership ổn định không? |
| Hot partition skew | Khóa/tenant nào gây imbalance? |
| Snapshot catch-up watermark | Bootstrap đủ coverage chưa? |
| Retention remaining | Có nguy cơ mất khả năng resume? |
| Reconciliation mismatch | Projection khác source không? |
| End-to-end business latency | User nhận outcome cuối khi nào? |

### 36.1. Offset lag khác time lag

1.000 events nhỏ có thể xử lý trong giây; 10 events chậm có thể mất phút. Đo tuổi event/commit-to-apply, rate và backlog cùng nhau.

### 36.2. Không cộng offset như một global clock

Offsets từng partition là tọa độ độc lập. Có thể tính tổng pending events đúng cách, nhưng không lấy `max(offset)` làm watermark mọi partitions.

### 36.3. Trace nhiều identity

Log/traces có thể gồm commandId, eventId, aggregate key, source position, broker position và correlation/causation IDs. Không tạo metric label cho từng eventId hoặc payload PII vì cardinality và bảo mật.

### 36.4. Lag bằng 0 không chứng minh đúng dữ liệu

Consumer có thể apply sai thứ tự trong thread pool dù offset đã commit hết. Cần source–projection reconciliation và version regression alerts.

## 37. Kiểm thử ordering contract

| Tình huống | Kỳ vọng |
|---|---|
| Emit seq 1..N cùng aggregate | Apply đúng thứ tự |
| Hai aggregates ở hai partitions | Không đòi global interleaving |
| Same eventId redelivery | Không double effect |
| ACK loss sau effect commit | Replay dedupe |
| Broker publish ACK loss | Publisher reuse eventId |
| Concurrent publishers seq 42/43 | Detect/reorder/pause, không overwrite |
| Gap 41→43 | Bounded buffer/replay hoặc quarantine |
| Same seq hai eventIds | Data integrity incident |
| Consumer group rebalance | Không mất effect, replay idempotent |
| Partition count change | Cutover/fencing giữ per-key contract |
| Snapshot and CDC overlap | Không bỏ update mới |
| CDC retention expired | Detect và resnapshot |
| Unknown schema | Fail/quarantine theo policy |
| Delete rồi replay update cũ | Không resurrect |
| Cross-partition saga event đến sớm | Workflow vẫn đợi prerequisites |

### 37.1. Không chỉ test một thread

Happy path gửi 1,2,3 trên localhost không chứng minh ordering khi có multi-publisher, rebalances, retries và parallel reducers.

### 37.2. Fault injection đúng thời điểm

Để test duplicate, cho sink **commit thành công** rồi drop offset ACK. Throw exception trước khi ghi chưa kiểm trường hợp nguy hiểm nhất.

### 37.3. Verify per-aggregate

Assert O-100:41→42 và O-200:7→8, không assert thứ tự giữa O-100/O-200 khi contract không hứa.

### 37.4. Fencing old workers

Rebalance có thể khiến old worker vẫn đang xử lý khi new worker nhận ownership. Lease epoch/conditional checkpoint/version guard giúp tránh concurrent overwrite.

### 37.5. Môi trường test cô lập

Partition, kill brokers, trim streams và replay dữ liệu phải thực hiện với dataset/cluster test, không gây ảnh hưởng production mà chưa được phép.

## 38. Case study: chuỗi trạng thái Order

~~~text
O-100:
    seq 41 OrderCreated
    seq 42 OrderPaid
    seq 43 OrderShipped
~~~

### 38.1. Key theo Order

Mọi events của O-100 dùng cùng aggregate key; các Orders khác có thể xử lý ở partitions khác. Source bảo đảm transition bằng CAS/transaction.

### 38.2. Duplicate OrderPaid

Consumer nhận `evt-paid` hai lần do ACK loss. Inbox nhận diện, không tăng doanh thu hai lần và không gửi hai confirmations.

### 38.3. OrderShipped đến trước OrderPaid

Consumer nhận seq 43 khi lastSeq=41: pause/replay 42, không tự set `SHIPPED` nếu thiếu business prerequisite.

### 38.4. Một Order khác xen vào

O-200 `OrderPaid` đến trước O-100 `OrderShipped` là bình thường nếu hai aggregates không có causal dependency. Không cần global total order.

## 39. Case study: Inventory, Payment và Saga

~~~text
OrderSubmitted(O-200)
    -> ReserveStock(SKU-9, cmd-R)
    -> InventoryReserved(reservation-R)
    -> AuthorizePayment(cmd-P)
    -> PaymentAuthorized(payment-P)
    -> OrderConfirmed(O-200)
~~~

### 39.1. Mỗi aggregate có sequence riêng

Inventory, Payment và Order không dùng cùng một eventSequence nếu thuộc streams khác. Dùng causation/correlation và saga state để liên kết.

### 39.2. Event đến trước dependency

PaymentAuthorized có thể tới orchestrator trước khi nó nhận InventoryReserved do transport scheduling. Coordinator không sort timestamps rồi bỏ prerequisite; nó đối chiếu workflow state.

### 39.3. Idempotency per effect

Payment gateway cần idempotency key, Inventory cần stable reservation command, Order confirm cần CAS. Ordering ở Kafka không thay bảo vệ nguồn.

### 39.4. Global invariant

Nếu hai regions đã ACK over-reservation, sắp lại events không sửa được stock. Dùng authoritative reservation, escrow hoặc compensation theo business protocol.

## 40. Case study: dựng search projection từ snapshot + CDC

~~~text
Snapshot:
    O-100 version 42

CDC:
    O-100 version 41 (overlap)
    O-100 version 42 (overlap)
    O-100 version 43 (new update)
~~~

### 40.1. Chọn consistency checkpoint

Snapshot source và change feed cần checkpoint gắn với nhau. Không lấy thời điểm OS clock của client làm mốc tuyệt đối để bảo đảm không gap.

### 40.2. Version-aware apply

Latest-state projection có thể bỏ 41/42 khi snapshot đã có 42, rồi apply 43 theo contract. Một event ledger cần các records lịch sử thì không thể bỏ chỉ vì snapshot state mới.

### 40.3. Delete race

Nếu O-100 bị delete sau snapshot mà CDC tombstone mất, search có thể hồi sinh Order cũ. Cần retention/CDC delete semantics và version guard.

### 40.4. Backfill kéo dài

Nếu backfill lâu hơn feed retention, connector không còn đủ history để catch-up; phải báo lỗi, điều chỉnh capacity/retention hoặc rebootstrap, không tuyên bố projection đã đầy đủ.

## 41. Checklist review event identity và ordering

1. **Phân loại nguồn:** Domain event, integration event hay raw CDC?
2. **Gắn stable eventId** tại source/outbox; không tái sinh khi retry.
3. **Gắn commandId riêng** cho ý định nghiệp vụ và idempotency.
4. **Định nghĩa aggregate identity** gồm tenant/type/id.
5. **Định nghĩa sequence** và authority cấp số atomically.
6. **Nêu rõ ordering scope:** Per aggregate/key/partition/stream/global.
7. **Không suy global order** từ timestamp, UUID hoặc partition offset.
8. **Chọn partition key ổn định** theo aggregate nếu cần ordering per aggregate.
9. **Xử lý hot key/tenant** mà không tùy tiện phá scope.
10. **Publisher giữ per-key order** hoặc consumer có sequence guard.
11. **Kiểm soát in-flight sends/retries** theo broker configuration.
12. **Dedupe tại consumer** bằng stable eventId và cùng atomic effect.
13. **Xử lý gap và conflicting sequence** rõ theo domain.
14. **Có bounded buffering và replay/resync** khi event đến trễ.
15. **Tách transport checkpoint khỏi domain progress**.
16. **ACK sau durable effect** theo at-least-once/idempotency policy.
17. **Kiểm CDC resume retention và token scope**.
18. **Tạo snapshot+CDC watermark** trước bootstrap.
19. **Thiết kế tombstone/delete** để không resurrect.
20. **Dùng saga/causation cho cross-partition workflows**, không giả global log.
21. **Chuẩn bị repartition/cutover/fencing** trước đổi partition count hoặc key.
22. **Event schema versioning** và unsupported-event handling rõ.
23. **Theo dõi lag/gaps/duplicates theo đúng scope**.
24. **Bảo vệ tenant, PII, access và replay authorization**.
25. **Fault-test ACK loss, concurrent senders, rebalance và retention**.

### 41.1. Mẫu hợp đồng sự kiện

~~~yaml
eventFamily: orders.events
source: "Order authoritative state and durable outbox"

identity:
  eventId: "stable across all publish attempts"
  commandId: "stable across command retries"
  aggregate: "(tenantId, aggregateType, aggregateId)"

ordering:
  requiredScope: "per Order"
  sourceSequence: "atomic with state mutation"
  partitionKey: "stable aggregate identity encoding"
  globallyOrdered: false
  onGap: "bounded pause/replay/resnapshot"

delivery:
  assumedMode: "at least once"
  dedupe: "atomic inbox and effect or equivalent"
  retry: "same eventId/payload"
  replayHorizon: "<documented retention>"

transport:
  stream: "<topic/change-feed>"
  checkpointScope: "<partition/shard plus position>"
  repartitionPlan: "<barrier, drain and fencing>"

consumer:
  supportedSchemaVersions: "<versions>"
  poisonEventPolicy: "<quarantine/replay>"
  sideEffects: "<idempotent external calls>"

tests:
  duplicateAfterAckLoss: required
  sameKeySequence: required
  snapshotCdcOverlap: required
  partitionMigration: required
~~~

Đây là mẫu thiết kế, không phải cấu hình sản phẩm có sẵn. Các dấu placeholder cần điền từ API/version/topology và test thực tế.

## 42. Bài tập thực hành

### Bài 1 — Phân biệt IDs

Một event có `eventId=evt-9`, `commandId=cmd-2`, `aggregateId=O-100`, `eventSequence=42`, `partition=3`, `offset=881`. Hãy mô tả nhiệm vụ và phạm vi của từng trường.

### Bài 2 — Hai events cùng payload

Hai users độc lập gửi `status=ACTIVE`; payload bằng nhau nhưng eventIds khác. Có được coi là duplicate không? Nên dùng field nào để chống retry?

### Bài 3 — Publication ACK loss

Broker append `evt-42`, response mất. Hãy thiết kế publisher retry với outbox stable ID và consumer inbox.

### Bài 4 — Offset scope

Kafka P0 offset=50 và P1 offset=200. Có chứng minh event P1 mới hơn P0 không? Hãy biểu diễn transport position đầy đủ.

### Bài 5 — Per-aggregate interleavings

O-100 có seq 41,42; O-200 có 7,8. Cho hai interleavings hợp lệ và hai interleavings làm đảo thứ tự nội bộ một Order.

### Bài 6 — Sai partition key

Producer dùng UUID eventId để chọn partition. Phân tích hậu quả và sửa thành aggregate partition key có tenant scope.

### Bài 7 — Key thay đổi theo status

Hệ partition theo Order status. Khi Order chuyển PENDING→PAID→CANCELED, điều gì xảy ra với ordering guarantee?

### Bài 8 — Hot tenant

Một tenant sinh 70% events. Phân tích per-tenant key vs per-order key và tradeoff về throughput/order.

### Bài 9 — Concurrent writers

Hai writers cùng đọc version=41 và muốn phát seq=42 với payload khác. Thiết kế source transaction/CAS đảm bảo chỉ một transition hợp lệ.

### Bài 10 — Outbox order

Hai publishers phát event seq 43 trước seq 42 của cùng Order. Nêu giải pháp per-key dispatch/sequence barriers và consumer gap detection.

### Bài 11 — MongoDB resume token

Một connector parse change stream token thành “global event sequence”. Giải thích vì sao không nên và công dụng đúng của resume token.

### Bài 12 — DynamoDB Streams

Consumer dùng duy nhất một `lastSequence` cho toàn table có nhiều stream shards. Thiết kế checkpoint theo shard và idempotent projection.

### Bài 13 — Cosmos change feed

Hai logical partitions có events cùng timestamp. Có global order không? Thiết kế processing theo partition và cross-partition workflow.

### Bài 14 — Redis Streams

Cùng logical event được `XADD` hai lần với stream entry IDs khác. Dùng field nào để dedupe và ACK consumer group như thế nào?

### Bài 15 — Cassandra CDC

Ba nodes có commitlog positions khác nhau. Vì sao không thể so chúng thành tổng commit order? Cần source identity/sequence gì?

### Bài 16 — Consumer crash

Consumer ghi projection rồi crash trước offset ACK. Viết pseudocode inbox/effect trong atomic boundary để redelivery không double-apply.

### Bài 17 — Gap

Consumer lastSeq=41 nhận eventSeq=44. Thiết kế buffer có giới hạn, replay source, timeout và fallback snapshot.

### Bài 18 — Filtered consumers

Consumer chỉ nhận `OrderPaid` nhưng aggregate eventSequence tăng cả với `OrderCreated`, `OrderShipped`. Thấy seq 41→44 có chắc mất message không?

### Bài 19 — Conflicting sequence

Hai events khác ID cùng aggregate seq 42. Phân biệt với retry cùng eventId và đề xuất xử lý data integrity.

### Bài 20 — Concurrent reducers

Một partition consumer nhận events 41 rồi 42 nhưng thread 42 commit trước 41. Thiết kế per-key serial execution hoặc CAS guard.

### Bài 21 — Repartition

Tăng partitions từ 8 lên 16 khiến O-100 chuyển partition. Đề xuất barrier, drain, fencing và sequence replay.

### Bài 22 — Snapshot/CDC overlap

Snapshot chứa O-100 v42, CDC phát v41,v42,v43. Thiết kế safe apply theo version và high-water mark.

### Bài 23 — Tombstone

Order bị delete ở source rồi một event update cũ được replay. Làm sao bảo đảm không resurrect trong search projection?

### Bài 24 — Cross-partition saga

`PaymentAuthorized` tới trước `InventoryReserved` ở coordinator. Vì sao sort theo publishedAt không đủ? Thiết kế state chờ prerequisite.

### Bài 25 — Exactly-once

Nhóm tuyên bố idempotent Kafka producer đảm bảo email từ consumer chỉ gửi đúng một lần. Hãy phân tích scope và thêm external effect idempotency.

### Bài 26 — Retention hết

CDC consumer dừng quá lâu và không resume được. Viết runbook detect–resnapshot–catch-up–reconcile.

### Bài 27 — Schema unknown

Consumer V1 không hiểu event type `OrderSuspended`. Có được skip để áp event sau không? Nêu domain risk và DLQ/upgrade strategy.

### Bài 28 — Metrics

Thiết kế metrics per-partition lag, duplicate event IDs, per-key gaps, outbox pending age, DLQ và projection mismatch, tránh cardinality vô hạn.

### Bài 29 — Multi-tenant security

Broker topic chứa events nhiều tenants. Thiết kế event key namespace, ACL, payload minimization, authorization và replay protection.

### Bài 30 — Fault injection

Thiết kế test: hai writers cạnh tranh một Order, outbox commit, publisher mất ACK, consumer crash sau effect và trước offset ACK. Kỳ vọng final projection đúng một lần.

### Bài 31 — Key migration

Đổi key từ tenantId sang `(tenantId,orderId)`. Phân tích thay đổi ordering scope, hot partition, consumer progress và cutover safety.

### Bài 32 — Phản biện kiến trúc

Một tài liệu nói: “Timestamp là eventId; offset lớn hơn nghĩa event mới hơn trên mọi partitions; cùng key tự sửa việc publisher gửi đảo; CDC token là business ID vĩnh viễn; ACK offset trước sink commit vẫn an toàn.” Hãy chỉ ra từng sai lầm và thiết kế đúng.

---

**Kết luận:** Với sự kiện và CDC của NoSQL, **định danh** và **thứ tự** phải được thiết kế như hai hợp đồng riêng nhưng phối hợp. `eventId` là identity của sự kiện logic qua retry/replay; `commandId` là ý định của caller; `(tenantId,aggregateType,aggregateId)` là scope của thực thể; `eventSequence`/`aggregateVersion` mô tả lịch sử nghiệp vụ, còn offset, stream sequence và resume token mô tả tiến độ trong **phân vùng nguồn/transport cụ thể**. Để duy trì thứ tự theo aggregate, cần **sequence được cấp nguyên tử tại source, partition key ổn định, publisher có per-key ordering, consumer có idempotency/sequence guards, và replay/checkpoint đúng**. Hai keys hoặc hai partitions không mặc nhiên có thứ tự toàn cục; timestamp hay so số offset khác partitions không thể tạo ra nhân–quả. Mỗi bảo đảm cần ghi rõ **phạm vi, điểm commit, điều kiện áp dụng và cách xử lý khi trùng, thiếu hoặc đảo sự kiện**.

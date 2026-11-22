# Transactional outbox trong phạm vi hệ có khả năng hỗ trợ

Khi xây dựng hệ thống NoSQL theo kiến trúc microservices hoặc event-driven, một yêu cầu thường gặp là: **sau khi cập nhật dữ liệu nghiệp vụ thành công, hệ thống phải phát sự kiện để các thành phần khác biết đến thay đổi đó**. Ví dụ, Order Service chuyển đơn hàng sang `CONFIRMED`, rồi phát `OrderConfirmed` để Inventory, Payment, Notification và Analytics tiếp tục xử lý.

Mẫu triển khai trực giác:

~~~text
1. UPDATE orders SET status = CONFIRMED
2. PUBLISH OrderConfirmed TO message broker
~~~

có một lỗ hổng nghiêm trọng: **database write và broker publish thuộc hai hệ thống khác nhau**, nên một process crash, mất mạng hoặc timeout giữa hai bước có thể khiến dữ liệu đã đổi nhưng sự kiện không được gửi. Nếu đảo thứ tự, sự kiện có thể đã được gửi nhưng database write thất bại.

**Transactional outbox** giải quyết khoảng trống đó bằng cách ghi **thay đổi nghiệp vụ và ý định phát event** vào cùng **ranh giới ghi nguyên tử (`atomic commit boundary`)**, sau đó một thành phần độc lập đọc các outbox records đã commit và publish chúng đến broker. Nhưng cụm từ *transactional* chỉ đúng khi **sản phẩm, topology, API và cấu hình thực sự hỗ trợ một commit nguyên tử cho cả hai loại dữ liệu**.

Trong NoSQL, tính nguyên tử có thể chỉ tồn tại ở **một document**, **một item**, **một logical partition**, hoặc rộng hơn nếu engine cung cấp **multi-document/multi-item transactions**. Một batch, một stream, một `SET`, một “write concern majority” hoặc một số lệnh ghi độc lập **không mặc nhiên là transaction**. Bài học này tập trung làm rõ **phạm vi có thể áp dụng**, lựa chọn triển khai thực tế, những gì outbox bảo đảm và những gì ứng dụng vẫn phải tự bảo vệ.

> **Thông điệp cốt lõi:** Outbox chỉ loại bỏ “khe hở giữa dữ liệu và ý định phát event” nếu hai phần được **commit nguyên tử trong đúng phạm vi engine hỗ trợ**. Nó **không** biến việc giao event đến broker và thực hiện side effect ở consumer thành exactly-once toàn hệ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả **dual-write problem** và ba cửa sổ crash nguy hiểm trước/giữa/sau các bước ghi database và publish broker.
2. Phân biệt **outbox record**, **business aggregate**, **relay/publisher**, **broker**, **consumer** và **idempotency/dedup ledger**.
3. Xác định **atomicity boundary** trong một NoSQL engine: document, partition, transaction nhiều items/documents, table/region hoặc các giới hạn vendor khác.
4. Thiết kế bản ghi outbox chứa event ID, aggregate ID, aggregate version, event type, payload/schema version, created time và trạng thái phát.
5. Mô tả hai hướng **polling publisher** và **CDC/change stream publisher**, gồm ưu, nhược và failure modes.
6. Chứng minh vì sao relay có thể phát event **ít nhất một lần (at-least-once)**, kể cả khi outbox transaction đã chính xác.
7. Thiết kế **idempotent consumer/inbox** và atomic business effect + dedup khi có khả năng hỗ trợ.
8. Giải thích **ordering theo aggregate**, retry, backoff, dead-letter/recovery, retention, replay và version guard.
9. Phân tích các phương án MongoDB, DynamoDB, Cosmos DB và những giới hạn khi dùng các hệ không có transaction phù hợp.
10. Xây dựng bài kiểm thử fault injection và bộ chỉ số để theo dõi **event loss, duplicate delivery, lag và bất biến nghiệp vụ**.

## 2. Tình huống xuyên suốt: xác nhận đơn hàng

Giả sử ứng dụng thương mại có Order:

~~~json
{
  "tenantId": "tenant-a",
  "orderId": "O900",
  "status": "CREATED",
  "version": 17,
  "totalVnd": 1200000
}
~~~

Khi `confirmOrder("O900")` thành công, cần:

1. Chuyển `orders[O900].status` từ `CREATED` sang `CONFIRMED`.
2. Tăng `orders[O900].version` từ 17 lên 18 theo conditional mutation.
3. Phát `OrderConfirmed` để Inventory Service thực hiện việc giữ hàng theo business workflow.

Một event dự kiến:

~~~json
{
  "eventId": "evt-O900-18-confirmed",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "tenant-a/O900",
  "aggregateVersion": 18,
  "occurredAt": "2026-11-14T08:00:00Z",
  "payload": {
    "orderId": "O900",
    "tenantId": "tenant-a",
    "status": "CONFIRMED",
    "totalVnd": 1200000
  }
}
~~~

Các định danh/giá trị ở đây chỉ để minh họa. Trong hệ thật, event ID và operation ID cần được cấp theo quy tắc uniqueness/idempotency rõ ràng; business state và event schema phải dựa trên domain.

### 2.1. Đường đi sai: update trước, publish sau

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as NoSQL DB
    participant Broker as Broker
    API->>DB: Update O900 to CONFIRMED
    DB-->>API: Commit success
    Note over API: Process crashes here
    API--xBroker: OrderConfirmed never published
~~~

Kết quả: `orders[O900] = CONFIRMED` nhưng các service khác **không hề biết có event**. Nếu service chỉ dựa vào event để tiếp tục, workflow có thể bị kẹt.

### 2.2. Đường đi sai: publish trước, update sau

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant Broker as Broker
    participant DB as NoSQL DB
    API->>Broker: Publish OrderConfirmed
    Broker-->>API: ACK
    API->>DB: Update Order
    DB-->>API: Conflict / failure
    Note over Broker,DB: Consumer can see a fact that never committed
~~~

Kết quả: Inventory hoặc Notification có thể thực hiện công việc dựa trên `OrderConfirmed` dù Order vẫn `CREATED`.

### 2.3. Vì sao chỉ dùng `try/catch` không đủ?

~~~java
try {
    repository.confirm(orderId);
    broker.publish(event);
} catch (Exception error) {
    retryLater(error);
}
~~~

Process có thể bị kill **ngay sau repository.confirm commit** nhưng trước khi ghi retry intent ở bất kỳ đâu bền vững. Không phải mọi lỗi đều đi qua `catch`: process crash, power loss, OS kill và network partitions tạo khoảng trống.

### 2.4. Vì sao “đặt broker publish trong transaction DB” không tự đúng?

~~~text
BEGIN DATABASE TRANSACTION
  UPDATE Order
  PUBLISH TO BROKER     <-- external side effect
COMMIT DATABASE TRANSACTION
~~~

Database transaction thông thường **không kiểm soát commit của broker**. Nếu publish thành công rồi transaction rollback, broker không tự rollback event. Muốn có transaction xuyên hai hệ phải có một giao thức/nhà cung cấp cam kết rõ việc phối hợp commit, thường có chi phí và giới hạn đáng kể. Transactional outbox **tránh phụ thuộc** vào một distributed transaction như vậy bằng cách **commit ý định publish vào chính database**.

## 3. Ý tưởng chính: commit nghiệp vụ và outbox record cùng nhau

~~~mermaid
flowchart LR
    C["Client"] --> API["Order Service"]
    API --> TX["Atomic DB commit"]
    TX --> O["Order aggregate"]
    TX --> E["Outbox event record"]
    E --> Relay["Outbox relay / CDC connector"]
    Relay --> Broker["Message broker"]
    Broker --> Consumer["Consumer / Inbox"]
    Consumer --> Target["Downstream state"]
~~~

Trong một transaction được hỗ trợ:

~~~text
BEGIN atomic commit
  Conditional update Order O900: CREATED -> CONFIRMED, v17 -> v18
  Insert Outbox event E18: OrderConfirmed, aggregateVersion=18
COMMIT
~~~

Có hai khả năng:

- **Commit thành công:** Order đổi và outbox event tồn tại cùng nhau.
- **Transaction không commit:** Cả hai thay đổi không có hiệu lực theo transactional contract.

Không có trạng thái bền vững “Order đã đổi nhưng outbox event không tồn tại” **do chính transaction đó** nếu transaction đúng về phạm vi, isolation và durability đã chọn.

**Lưu ý:** Một transaction có thể trả timeout/unknown commit outcome cho client, dù cuối cùng đã commit. Outbox không tự làm mọi response trở nên xác định; phần ứng dụng vẫn phải xử lý **idempotency và đối soát**.

### 3.1. Một record outbox là gì?

Outbox là dữ liệu bền nằm trong database, thường cùng hệ lưu business aggregate.

~~~json
{
  "_id": "evt-O900-18-confirmed",
  "eventType": "OrderConfirmed",
  "eventSchemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "tenant-a/O900",
  "aggregateVersion": 18,
  "payload": {
    "orderId": "O900",
    "status": "CONFIRMED"
  },
  "status": "PENDING",
  "createdAt": "2026-11-14T08:00:00Z",
  "publishedAt": null,
  "attemptCount": 0
}
~~~

`PENDING` không có nghĩa transaction Order đang pending: nó thường có nghĩa **ý định phát event đã được commit nhưng relay chưa xác nhận publish thành công**.

### 3.2. Ai được quyền tạo event?

Event phải được tạo từ **transition nghiệp vụ đã được transaction chấp nhận**. Nếu conditional update Order thất bại vì đã `CONFIRMED` hoặc `CANCELLED`, không được vẫn tạo `OrderConfirmed` dựa trên ý định đầu vào.

### 3.3. Khi nào một operation tạo nhiều event?

Một transaction có thể cần tạo `OrderConfirmed` và `OrderReadyForFulfillment`, hoặc ghi một event mô tả transition duy nhất. Điều quan trọng là **tất cả ý định event cần đi kèm state commit** nằm trong phạm vi transaction; không tự tách một phần sang network call ngoài DB và vẫn tuyên bố atomic.

### 3.4. Outbox bảo vệ điều gì?

Nó bảo vệ **sự gắn kết giữa state change đã commit và record event dự kiến**.

Nó chưa tự bảo đảm:

- Relay sẽ publish ngay lập tức.
- Broker ACK tương đương consumer hoàn tất.
- Broker chỉ nhận đúng một bản event.
- Consumer chỉ thực hiện một side effect.
- Events của nhiều shards có total order.
- Mọi transaction bên ngoài service được commit nguyên tử.
- Một event đã phát được “thu hồi” nếu các hệ khác thay đổi.

## 4. Bốn ranh giới cần phân biệt

~~~text
Boundary 1:
  Business record + Outbox record
  => one database atomic commit (if supported)

Boundary 2:
  Outbox record -> Broker
  => asynchronous publish/ACK, at-least-once common

Boundary 3:
  Broker -> Consumer processing
  => delivery/ack/retry governed by broker contract

Boundary 4:
  Consumer -> Downstream database/external API
  => independent transaction/idempotency requirements
~~~

### 4.1. Atomicity không phải durability

Một database API có thể bảo đảm atomic transaction nhưng độ bền sau failover phụ thuộc **write acknowledgement, replication, persistence và topology**. Khi thiết kế event không được mất, phải xác minh **commit ACK nghĩa là gì** ở cấu hình cụ thể.

### 4.2. Atomicity không phải isolation

Một transaction có thể nguyên tử nhưng mức isolation vẫn có những giới hạn. Phải bảo vệ transition bằng condition/version và đọc contract isolation, không suy chỉ cần hai lệnh cùng transaction thì sẽ không có mọi dạng race nghiệp vụ.

### 4.3. Atomicity không phải event delivery

Outbox record tồn tại chỉ chứng minh **ý định phát event đã được lưu bền**. Relay phải có cơ chế quét/CDC, retry và vận hành để cuối cùng phát nó theo điều kiện liveness phù hợp.

### 4.4. Đúng phạm vi mới có “transactional”

Nếu Order nằm trong **một partition** và outbox item thuộc **partition khác**, mà engine chỉ có atomic batch trong một partition, thì **đặt hai lệnh vào một batch không tạo cross-partition transaction**. Phải dùng transaction API bao cả hai, chuyển outbox vào cùng atomic aggregate hoặc chọn kiến trúc khác.

## 5. “Phạm vi hệ có khả năng hỗ trợ” nghĩa là gì?

Điều kiện tiên quyết quan trọng nhất của mẫu này là có một **nguồn ghi nguyên tử chung** cho business state và outbox intent.

| Khả năng engine | Có thể làm gì? | Điểm cần cẩn trọng |
| --- | --- | --- |
| Atomic mutation **một document/item** | Gắn outbox intent vào cùng document nếu model và giới hạn cho phép | Kích thước document, concurrency, array growth, extraction |
| Atomic batch **một logical partition** | Đặt aggregate và outbox trong cùng partition key | Không dùng across partitions nếu contract không hỗ trợ |
| Multi-document/item transaction | Cập nhật aggregate và tạo outbox riêng trong một transaction | Scope, size/operations limits, read/write concerns, sharding |
| Commit log/change stream của **business write** | Suy ra event từ thay đổi đã commit, có thể tránh explicit outbox record | Event semantics, retention, resume, duplicate delivery |
| Batch ghi không có transaction isolation/atomicity phù hợp | **Không đủ** để cam kết 2 writes cùng commit | Crash window, partial apply, recovery |
| Single-key SET hoặc CAS chỉ một entity | Có thể bảo vệ một aggregate nhưng chưa bảo vệ outbox ở key khác | Cần cùng atomic unit hoặc transaction khác |
| Transaction xuyên DB và broker theo vendor | Có thể có giải pháp đặc thù | Phải đọc chính thức phạm vi, coordinator, costs, failure model |

### 5.1. Không nhầm cùng database với cùng transaction

Hai collections hoặc tables cùng nằm trong một database **không làm hai writes trở thành nguyên tử**. Cần API transaction thực sự, đúng cấu hình.

### 5.2. Không nhầm cùng partition với cùng entity

Một logical partition có thể chứa nhiều documents/items, và một engine có thể hỗ trợ batch atomic trong partition ấy. Nhưng “hai records có cùng tenant” không có nghĩa chúng **thực sự chia cùng partition key** theo schema. Phải kiểm tra partition-key value mà engine dùng.

### 5.3. Không nhầm replicated với transactional

Replication factor 3 nghĩa có nhiều bản sao, **không bảo đảm nhóm writes across keys commit cùng nhau**. Quorum/consistency levels và transaction atomicity là các bảo đảm khác nhau.

### 5.4. Không nhầm Kafka transaction với DB transaction

Một broker có thể hỗ trợ transaction trong phạm vi messages/offsets của broker, nhưng điều đó không mặc nhiên bao gồm **NoSQL database write** của application. Transactional outbox vẫn cần gắn ý định publish với source business write.

## 6. Ba cách bố trí outbox trong NoSQL

### 6.1. Outbox collection/table riêng trong transaction đa record

~~~text
orders:
  key = tenant-a/O900
  status = CONFIRMED
  version = 18

outbox:
  key = evt-O900-18-confirmed
  aggregateId = tenant-a/O900
  aggregateVersion = 18
  status = PENDING
~~~

Ưu điểm: relay có thể query/filter outbox dễ, quản lý retention/partition riêng, payload không làm aggregate to dần.

Nhược điểm: **bắt buộc transaction hỗ trợ cả hai records**, và multi-record transaction có thể tăng latency, contention, storage/log overhead.

### 6.2. Outbox entries nằm ngay trong cùng aggregate/document

~~~json
{
  "_id": "tenant-a/O900",
  "status": "CONFIRMED",
  "version": 18,
  "pendingEvents": [
    {
      "eventId": "evt-O900-18-confirmed",
      "type": "OrderConfirmed",
      "aggregateVersion": 18
    }
  ]
}
~~~

Nếu một atomic update vừa đổi `status/version` vừa thêm event vào **cùng document**, có thể đạt atomicity một document **ngay cả khi engine không hỗ trợ transaction đa document**.

Tuy nhiên cần quan tâm:

- Giới hạn kích thước document/item.
- Array tăng vô hạn nếu relay không dọn.
- Concurrency khi relay xóa/đánh dấu event trong document mà API đang cập nhật.
- Index và khả năng quét `pendingEvents`.
- Không xóa event trước khi có broker ACK đúng nghĩa.
- Chính sách xóa event đã publish có thể xảy ra đồng thời với business writes.

**Không dùng embedded array vô hạn trong một Order nóng** mà không có thiết kế bounded retention và atomic update.

### 6.3. CDC từ committed business changes

Một số engine cung cấp **change stream/CDC** cho writes đã commit, để relay suy ra event:

~~~text
Business transaction
  -> database commit log / change stream
      -> CDC connector
          -> broker event
~~~

Ưu điểm: có thể tránh explicit outbox write cho những event được định nghĩa hoàn toàn từ business-state mutation.

Nhược điểm:

- Không phải mọi thay đổi kỹ thuật của record đều tương ứng một **domain event có ý nghĩa**.
- Payload change stream có thể chỉ chứa delta hoặc ảnh chụp tùy API/config.
- Consumer cần hiểu version/ordering và schema evolution.
- Retention, resume token/checkpoint và CDC lag phải được xử lý.
- Nếu một business transaction đổi nhiều records, cần hiểu stream representation/order theo engine; không tự giả định một domain event duy nhất.

Đây là phương án liên quan nhưng **không luôn thay thế được explicit transactional outbox** khi cần sự kiện mang intent/metadata không suy ra từ một mutation đơn lẻ.

## 7. Chọn ranh giới theo business aggregate

Một **aggregate** là đơn vị nghiệp vụ mà những invariant và transitions liên quan được bảo vệ tại một authority phù hợp.

Ví dụ Order aggregate:

~~~text
Order O900:
  status: CREATED -> CONFIRMED
  version: 17 -> 18
  outbox: OrderConfirmed(v18)
~~~

Một lựa chọn thiết kế:

- Business key: `(tenantId, orderId)`.
- Một aggregate version được cấp atomically tại commit.
- Event ID tương ứng transition đã thắng.
- Outbox cùng atomic scope.
- Broker partition key dựa trên aggregate key để giữ thứ tự mong muốn.

### 7.1. Không cố đưa cả hệ vào một aggregate

Order, Inventory, Payment và Shipping có thể thuộc **services/datastores riêng**. Không thể “outbox transaction” bao mọi database bằng cách đặt tất cả thao tác trong một method Java có annotation `@Transactional` nếu transaction manager chỉ quản lý một nguồn.

### 7.2. Outbox thường đi kèm workflow bất đồng bộ

~~~text
Order: CONFIRMED + OrderConfirmed outbox
   |
   v
Inventory consumes -> reserve stock + StockReserved outbox
   |
   v
Payment consumes -> capture + PaymentCaptured outbox
   |
   v
Order consumes -> READY_FOR_SHIPMENT + event
~~~

Mỗi service bảo vệ local invariant của mình, phát event qua outbox phù hợp, và workflow có thể được điều phối bằng **saga/process manager**, với idempotency và compensation khi cần.

Không có atomic commit toàn bộ chuỗi chỉ vì mỗi bước local đều dùng outbox.

## 8. MongoDB: transaction đa document giữa Order và Outbox

MongoDB là một ví dụ về NoSQL document database **có khả năng hỗ trợ multi-document transactions** trong những deployment/version được hỗ trợ. Có thể lưu Order trong collection `orders`, event trong collection `outbox`, rồi commit cả hai bằng **một session transaction**.

### 8.1. Thiết kế collections

`orders`:

~~~json
{
  "_id": "tenant-a/O900",
  "tenantId": "tenant-a",
  "orderId": "O900",
  "status": "CREATED",
  "version": 17
}
~~~

`outbox`:

~~~json
{
  "_id": "evt-O900-18-confirmed",
  "tenantId": "tenant-a",
  "aggregateId": "tenant-a/O900",
  "aggregateVersion": 18,
  "eventType": "OrderConfirmed",
  "payload": {
    "orderId": "O900",
    "status": "CONFIRMED"
  },
  "status": "PENDING",
  "attemptCount": 0
}
~~~

### 8.2. MongoDB-style transaction minh họa

~~~javascript
// Minh họa điều phối transaction; phiên bản/driver cụ thể
// phải dùng đúng API và retry/commit handling của MongoDB.
const session = client.startSession();

try {
  await session.withTransaction(async () => {
    const result = await db.collection("orders").updateOne(
      {
        _id: "tenant-a/O900",
        status: "CREATED",
        version: 17
      },
      {
        $set: { status: "CONFIRMED" },
        $inc: { version: 1 }
      },
      { session }
    );

    if (result.modifiedCount !== 1) {
      throw new Error("ORDER_STATE_CONFLICT");
    }

    await db.collection("outbox").insertOne(
      {
        _id: "evt-O900-18-confirmed",
        aggregateId: "tenant-a/O900",
        aggregateVersion: 18,
        eventType: "OrderConfirmed",
        eventSchemaVersion: 1,
        payload: { orderId: "O900", status: "CONFIRMED" },
        status: "PENDING",
        attemptCount: 0,
        createdAt: new Date()
      },
      { session }
    );
  }, {
    // Cấu hình transaction/readConcern/writeConcern
    // phải được chọn từ official docs và deployment thực tế.
  });
} finally {
  await session.endSession();
}
~~~

Đoạn mã thể hiện một **ý tưởng transaction**; trong application thực, `db` phải tương ứng cùng database/cluster/session, cùng cấu hình transaction hợp lệ. Phải dùng cách xử lý lỗi của driver theo hợp đồng phiên bản đang chạy.

### 8.3. Vì sao conditional update nằm trong transaction?

Nếu Order đã ở `CANCELLED` hoặc `CONFIRMED`, update với predicate `status=CREATED,version=17` không match. Application ném lỗi trong callback để transaction **không commit outbox event**. Như vậy sự kiện `OrderConfirmed` chỉ đi kèm transition thực sự được chấp nhận.

### 8.4. Vì sao event ID cần ổn định?

Một callback transaction có thể được driver thử lại khi gặp loại lỗi retry được, tùy API. Nếu mỗi attempt tự sinh event ID mới rồi không có idempotency ở cấp request, client retry sau unknown outcome có thể khó xác định event nào đã commit.

Cách tiếp cận:

- Cấp `logicalOperationId` trước transaction.
- Thiết kế event identity từ transaction/business transition hoặc duy trì mapping bền giữa operation và kết quả.
- Dùng unique constraint/index phù hợp cho event ID/business key.
- Xử lý duplicate request bằng lookup kết quả thay vì tạo mutation mới.

### 8.5. Unknown transaction commit result

Có tình huống transaction đã commit nhưng client timeout khi nhận ACK. Không được suy `withTransaction()` throw nghĩa **chắc chắn transaction chưa commit**. Driver có thể có retry commit logic và các error labels/protocol riêng; application cần có đường tra state/operation ID.

### 8.6. Khi collection được sharding

MongoDB có hỗ trợ transactions trong các sharded deployment phù hợp, nhưng cần đọc theo version/cấu hình về:

- Session/transaction requirements và transaction lifetime.
- Read concern, write concern, snapshot behavior.
- Distributed transaction overhead khi đụng nhiều shards.
- Shard-key, unique index và targeting.
- Transaction retries/abort conflicts.
- Chi phí kéo dài transaction trong lúc migration hoặc high contention.

**Không suy transaction 2 records ở một shard sẽ có cùng chi phí và liveness với một transaction across shards.**

### 8.7. Phương án atomic single document

Nếu không muốn multi-document transaction, một atomic mutation có thể đổi Order và `pendingEvents` trên **chính document Order**.

Ví dụ minh họa:

~~~javascript
db.orders.updateOne(
  {
    _id: "tenant-a/O900",
    status: "CREATED",
    version: 17
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 },
    $push: {
      pendingEvents: {
        eventId: "evt-O900-18-confirmed",
        type: "OrderConfirmed",
        aggregateVersion: 18
      }
    }
  }
);
~~~

Chỉ dùng nếu domain/retention/size hỗ trợ. Nếu relay cần xóa phần tử khỏi array, phải quản lý cạnh tranh với các updates mới để không xóa nhầm hoặc mất event.

### 8.8. MongoDB Change Streams

Một relay có thể dùng **change stream** trên `outbox` để phát hiện những events đã commit; cần lưu **resume token/checkpoint**, xử lý disconnect, retention và retry. Change stream **không** làm broker publish trở thành một phần database transaction.

Nếu relay dùng `watch()` và nhận cùng event nhiều lần sau restart/resume, consumer vẫn cần idempotency.

## 9. DynamoDB: TransactWriteItems với Order và Outbox

DynamoDB có API **`TransactWriteItems`** để thực hiện các actions có transaction semantics trong **phạm vi, giới hạn và deployment được tài liệu dịch vụ hỗ trợ**. Đây là một lựa chọn để ghi:

1. Conditional update Order.
2. Put outbox item mới.
3. (Tùy thiết kế) Put idempotency record.

trong cùng một request transaction.

### 9.1. Mô hình items

~~~text
Orders table:
  PK = TENANT#tenant-a
  SK = ORDER#O900
  status = CREATED
  version = 17

Outbox table:
  PK = OUTBOX#tenant-a#bucket-2026-11-14
  SK = EVENT#evt-O900-18-confirmed
  aggregateId = tenant-a/O900
  aggregateVersion = 18
  state = PENDING
~~~

Chọn partition keys theo workload thực tế. Một `OUTBOX#ALL` duy nhất có thể tạo **hot partition**; chia buckets có thể cần thêm checkpoint/order logic.

### 9.2. Transaction pseudocode

~~~text
TransactWriteItems(
  Update Orders item:
    Key=(TENANT#tenant-a, ORDER#O900)
    Condition: status=CREATED AND version=17
    Effect: status=CONFIRMED, version=18

  Put Outbox item:
    Key=(OUTBOX#tenant-a#bucket, EVENT#evt-O900-18-confirmed)
    Condition: attribute_not_exists(PK)
    Fields: eventType=OrderConfirmed, aggregateVersion=18, ...
)
~~~

Nếu transaction thành công theo contract, business update và outbox item cùng commit. Nếu một action fail điều kiện, transaction không được coi là đã tạo event.

**Điểm cần tra tài liệu** của `TransactWriteItems` đang dùng:

- Giới hạn số actions và tổng dung lượng.
- Tables cùng account/Region và các giới hạn deployment.
- Không được nhắm nhiều actions vào cùng một item theo ràng buộc API.
- Transaction conflict/throttling/cancellation.
- Client request token/idempotency window và retry behavior.
- Không suy transaction này là **cross-region transaction** cho Global Tables.

### 9.3. Idempotency khi retry API

DynamoDB có những cơ chế idempotency token nhất định cho transaction APIs, nhưng **cửa sổ thời gian, cùng payload và hành vi sau timeout** phải đọc đúng hợp đồng phiên bản hiện hành. Application không nên dựa duy nhất vào một token ngắn hạn nếu nghiệp vụ có thể retry sau nhiều ngày.

Thiết kế lâu dài có thể lưu `operationId`/result trong cùng transaction (một item riêng nếu phạm vi/giới hạn cho phép), rồi tra khi client retry.

### 9.4. DynamoDB Streams làm nguồn cho relay

Nếu outbox item đã được transaction commit, một consumer của **DynamoDB Streams** có thể nhận change record của item và publish tới broker:

~~~text
TransactWriteItems commit:
  Order updated
  Outbox item created
            |
       DynamoDB Streams
            |
       Stream relay
            |
        Broker
~~~

Lưu ý:

- Stream là cơ chế **truyền change records**, không phải broker publish trong transaction.
- Consumer stream có thể retry/duplicate; phải dùng event ID để chống lặp.
- Ordering được bảo đảm trong những phạm vi cụ thể, **không suy global order giữa toàn bộ bảng/partitions hoặc tất cả items trong transaction**.
- Stream có retention/replay giới hạn; relay ngừng quá lâu có thể cần nguồn bền khác để backfill.
- Nếu lọc/transform event, phải hiểu stream view type và những thuộc tính event có mặt.

### 9.5. TTL không thể là sự xác nhận publish

Không dùng TTL DynamoDB để tuyên bố “event đã được gửi” hoặc dựa vào thời điểm TTL để xóa ngay record. TTL deletion có cơ chế nền và timing khác transaction ACK.

Một cleanup worker phải dựa vào trạng thái publish/retention/replay policy rõ ràng, không chỉ `expiresAt`.

### 9.6. Global Tables và multi-region writes

Nếu nhiều regions có thể cùng cập nhật Order, cần đọc hợp đồng conflict resolution/transaction scope của Global Tables. Một transaction `TransactWriteItems` trong một Region **không tự bảo đảm rằng state và outbox ở mọi Region được quan sát nguyên tử cùng thời điểm**.

Với invariant mạnh, có thể cần **single authoritative region cho aggregate** hoặc giao thức ownership/cross-region đặc biệt. Outbox không tự giải quyết xung đột giữa hai `OrderConfirmed` khác nhau.

## 10. Azure Cosmos DB for NoSQL: TransactionalBatch theo logical partition

Một lựa chọn khác là **`TransactionalBatch`** khi các operations cùng nằm trong **một logical partition** của cùng container theo hợp đồng sản phẩm.

### 10.1. Aggregate và outbox chung partition key

Ví dụ:

~~~text
Container: OrdersAndEvents
Partition key path: /tenantOrderKey

Item Order:
  id = order-O900
  tenantOrderKey = tenant-a/O900
  type = ORDER

Item Outbox:
  id = evt-O900-18-confirmed
  tenantOrderKey = tenant-a/O900
  type = OUTBOX
~~~

Hai items cùng `tenantOrderKey` có thể tham gia cùng transactional batch được hỗ trợ trong scope đó.

### 10.2. TransactionalBatch pseudocode

~~~text
TransactionalBatch(partitionKey="tenant-a/O900")
  Patch Order id=order-O900
    with conditional version/state guard
  Create Outbox id=evt-O900-18-confirmed
Execute
~~~

Điều kiện về predicate/ETag/patch hỗ trợ cụ thể phải theo API/version SDK. Nếu batch vượt logical partition boundary, **không được coi nó vẫn là cùng transaction**.

### 10.3. Change feed và outbox

Cosmos DB change feed có thể được dùng để quan sát item outbox đã commit và đẩy ra broker. Vẫn phải lưu checkpoint, xử lý duplicate, ordering theo scope đã công bố, replay và lifecycle của outbox items.

### 10.4. Lợi ích và trade-off của single-partition colocating

Ưu điểm: thiết kế atomicity rõ, không cần distributed transaction giữa partitions.

Đổi lại:

- Aggregate/outbox phải **cùng logical partition key thực tế**.
- Traffic của một tenant/order nóng có thể tạo hot partition.
- Outbox retention/read pattern liên quan container/partition design.
- Transaction batch có giới hạn API/cost/size, cần kiểm tra theo bản dịch vụ đang dùng.

Không đặt outbox ở partition `OUTBOX` khác nhưng vẫn gọi đây là một single-partition atomic batch.

## 11. Những hệ cần đặc biệt thận trọng về transactional scope

### 11.1. Cassandra/ScyllaDB và CQL BATCH

Các hệ wide-column có `BATCH`, `LOGGED BATCH`, `UNLOGGED BATCH` và conditional statements/LWT theo sản phẩm/phiên bản. Nhưng:

- **Batch không đồng nghĩa arbitrary ACID multi-partition transaction** với full isolation.
- Logged batch có những bảo đảm phục hồi/atomic application cụ thể cần đọc chính xác; không tự suy nó cho phép một atomic conditional Order update + independent Outbox row theo mọi lịch lỗi.
- LWT có transaction/consensus semantics trong những phạm vi nhất định, không tự mở rộng qua mọi partitions.
- Cross-partition workflows cần đánh giá rất kỹ source of truth và compensation/replay.

Vì vậy không nên viết:

~~~sql
BEGIN BATCH
  UPDATE orders ...;
  INSERT INTO outbox ...;
APPLY BATCH;
~~~

rồi mặc định **đã có cùng bảo đảm của một multi-document transaction serializable**. Muốn dùng pattern đó phải chứng minh được **atomicity và điều kiện commit** đúng các invariant cần bảo vệ bằng tài liệu chính thức của engine/version/topology.

### 11.2. Redis MULTI/EXEC và Lua scripts

Redis có cơ chế chạy nhóm lệnh không bị interleave như `MULTI/EXEC` hoặc script trong phạm vi được hỗ trợ; nhưng:

- Không suy Redis `MULTI/EXEC` có rollback transaction kiểu ACID khi một command trong nhóm gặp runtime error.
- Độ bền và trạng thái khi failover phụ thuộc persistence/replication contract.
- Cluster có giới hạn về multi-key operations/slots theo cách sử dụng.
- TTL/eviction/memory pressure có thể không phù hợp lưu outbox bền dài hạn nếu không được thiết kế rõ.
- Broker publish vẫn nằm ngoài Redis command execution.

Nếu chọn Redis để giữ ý định publish, cần **phân tích sâu durability, eviction, replication, recovery và atomic key scope**; không gọi một cặp `SET`/`PUBLISH` là transactional outbox.

### 11.3. Document database không có multi-document transaction

Khi engine chỉ có atomic single-document update:

- Có thể **embed outbox intent cùng aggregate** trong một atomic update nếu dung lượng/retention cho phép.
- Có thể phát event từ **change feed** của business document nếu domain event có thể suy ra đủ.
- Hoặc cần thay thiết kế/đổi storage có atomicity phù hợp.
- Không được tự ghi aggregate rồi ghi outbox ở hai documents và gắn nhãn “transactional”.

### 11.4. Nếu cùng database nhưng hai clusters khác nhau

Hai NoSQL clusters khác nhau không chia sẻ một local transaction chỉ vì có cùng tên vendor. Giải pháp cần một **common authoritative commit boundary** hoặc một distributed workflow có reconciliation riêng.

## 12. Đọc hợp đồng giao thức trước khi chốt kiến trúc

Một bảng design review nên được điền bằng **tài liệu chính thức đúng phiên bản và cấu hình**:

| Câu hỏi | Vì sao cần |
| --- | --- |
| Business record và outbox nằm trong **cùng atomic scope** nào? | Điều kiện cốt lõi của outbox |
| API transaction nào thực hiện hai writes cùng commit? | Không nhầm batch với transaction |
| Giao dịch có dùng được qua collections/tables/partitions/shards không? | Xác định giới hạn topology |
| Conditional mutation có được kiểm tra tại commit không? | Ngăn event sinh từ transition thất bại |
| Một crash ngay sau commit ACK có làm mất writes không? | Durability và failover |
| Transaction timeout/unknown commit outcome được trả thế nào? | Idempotency/reconciliation |
| SDK có tự retry callback/commit không? | Tránh tạo event ID mới và duplicate |
| CDC/stream event phát sau commit với guarantee gì? | Publisher design |
| Stream retention/checkpoint/resume semantics? | Recovery khi relay chết lâu |
| Cleanup/TTL có diễn ra ngay không? | Không xóa event quá sớm |
| Giới hạn size/number of operations/transaction lifetime? | Capacity planning |
| Có global order không hay chỉ per-key/per-partition? | Ordering theo aggregate |
| Multi-region concurrent writers xử lý xung đột ra sao? | Không bảo vệ sai authority |

### 12.1. Đừng suy bảo đảm từ tên API

“Batch”, “transaction”, “stream”, “atomic” hoặc “exactly-once” có thể có **phạm vi rất khác nhau** tùy sản phẩm. Không có contract chính thức cho đúng scope thì chưa được dùng tên gọi để kết luận kiến trúc an toàn.

### 12.2. Phiên bản và driver cũng là một phần của hợp đồng

Khi thay đổi:

- Version database hoặc SDK.
- Replication mode/read/write concern.
- Từ một partition sang sharded multi-partition.
- Một region sang active-active nhiều regions.
- Độ lớn aggregate/outbox.
- CDC retention hoặc broker producer mode.

cần đọc lại hợp đồng. Một thiết kế atomic trong một partition có thể **mất điều kiện áp dụng** sau khi partitioning đổi.

## 13. Relay: outbox record đi từ database tới broker như thế nào?

Sau transaction Order + Outbox:

~~~text
Database:
  Order O900 = CONFIRMED, v18
  Outbox E18 = PENDING

Broker:
  chưa có OrderConfirmed
~~~

Một thành phần **outbox relay**, còn gọi là publisher/dispatcher/connector, có nhiệm vụ tìm các records đã commit nhưng chưa xác nhận publish rồi gửi chúng.

### 13.1. Hai mô hình relay phổ biến

**Polling publisher:**

~~~text
Loop:
  1. Query due PENDING events.
  2. Claim event (nếu nhiều workers).
  3. Publish với eventId và aggregateKey.
  4. Chờ broker ACK.
  5. Mark PUBLISHED hoặc advance checkpoint.
  6. Khi lỗi: retry/backoff/reconcile.
~~~

**CDC/change stream publisher:**

~~~text
Database commit
   -> commit log / change stream
      -> connector sees outbox insertion
         -> publishes event
            -> persists checkpoint/resume position
~~~

Hai hướng **không thể tự loại bỏ duplicate**: crash giữa broker ACK và mark/checkpoint vẫn có thể dẫn tới publish lại.

### 13.2. Polling vs CDC

| Tiêu chí | Polling outbox | CDC/change stream |
| --- | --- | --- |
| Phát hiện record mới | Query index/table | Subscribe commit stream |
| Độ trễ | Liên quan polling interval | Gần thời gian commit nếu stream khỏe |
| Tải database | Queries, claims, updates | Log/stream read và checkpoint |
| Ordering | Phải tự tổ chức claim/query | Theo scope stream/shards được bảo đảm |
| Recovery | Scan PENDING/lease expired | Resume token/sequence + backfill khi gap |
| Scale-out | Shard/bucket claims | Parallel consumers theo stream partitions |
| Retention | Outbox records chủ động giữ | Stream retention hữu hạn; có thể kết hợp outbox |
| Lỗi phổ biến | Claim race, retry storm, hot pending index | Expired resume token, lag, backpressure |
| Dễ debug | Record trạng thái dễ truy vấn | Cần log checkpoint và event identity |

**Không có mô hình luôn tốt hơn**. Chọn dựa trên nguồn dữ liệu, độ trễ, tần suất events, khả năng CDC, yêu cầu replay, chi phí và operational maturity.

## 14. Polling publisher và thiết kế trạng thái

Một bản ghi outbox có thể đi qua:

~~~mermaid
flowchart TD
    P["PENDING"] --> C["CLAIMED / IN_FLIGHT"]
    C -->|Broker ACK| S["PUBLISHED"]
    C -->|Transient error| R["RETRY_WAIT"]
    R --> P
    C -->|Lease expires / crash| P
    C -->|Poison event| D["QUARANTINED / DLQ"]
    D -->|Reviewed and repaired| P
~~~

`CLAIMED` là **trạng thái relay**, không có nghĩa broker đã nhận event.

### 14.1. Schema để polling

~~~json
{
  "eventId": "evt-O900-18-confirmed",
  "aggregateId": "tenant-a/O900",
  "aggregateVersion": 18,
  "eventType": "OrderConfirmed",
  "payload": {"orderId": "O900", "status": "CONFIRMED"},
  "status": "PENDING",
  "createdAt": "2026-11-14T08:00:00Z",
  "nextAttemptAt": "2026-11-14T08:00:00Z",
  "attemptCount": 0,
  "claimOwner": null,
  "claimGeneration": 0,
  "claimUntil": null,
  "lastErrorCode": null,
  "publishedAt": null
}
~~~

### 14.2. Indexing/partitioning cho relay

Polling cần tìm nhanh **event cần gửi**, thường theo `status` + `nextAttemptAt` + bucket/shard. Không đặt tất cả event vào một partition có key cố định nếu traffic cao.

Ví dụ mô hình truy vấn:

~~~text
WHERE status IN (PENDING, RETRY_WAIT)
  AND nextAttemptAt <= now
ORDER BY nextAttemptAt
LIMIT batchSize
~~~

Phải xác minh engine hỗ trợ query/index tương ứng. Cassandra/DynamoDB có access patterns và index semantics khác MongoDB; không áp SQL pseudo-query nguyên xi vào mọi hệ.

### 14.3. Claim bằng conditional update

Nếu nhiều workers cùng poll, không được:

~~~text
Worker A: read PENDING
Worker B: read PENDING
Worker A: publish
Worker B: publish
~~~

mà không có quy tắc claim. Một transaction/CAS có thể chuyển:

~~~text
PENDING -> CLAIMED(worker-A, claimGeneration=42, claimUntil=T)
~~~

chỉ nếu event vẫn PENDING/lease expired. Worker B thua claim có thể bỏ qua.

### 14.4. Claim không tạo exactly-once

Worker A được claim rồi bị pause lâu hơn lease. Worker B tiếp quản và publish. A resume rồi **cũng có thể publish**. Broker không tự biết hai publish là cùng business event nếu publisher không dùng event identity/ordering protocol.

Vì vậy `CLAIMED` giúp giảm cạnh tranh và cân bằng workload, nhưng **idempotency của consumer vẫn cần**.

### 14.5. Fencing ở thao tác cập nhật outbox

Khi A resume, nếu nó cố update status/attempt count, nên dùng `claimOwner + claimGeneration` hoặc condition tương đương để không ghi đè state do worker mới quản lý.

Tuy nhiên một ACK từ broker do A nhận được có thể là bằng chứng event đã được publish; tùy thiết kế, có thể đánh dấu PUBLISHED nếu event immutable và commit ACK thỏa điều kiện. Điều cốt lõi là **định nghĩa state transition đúng semantics**, không tự suy claim lease quyết định duy nhất delivery outcome.

### 14.6. Payload của event phải bất biến

Một `eventId` nên luôn đại diện **cùng một nội dung logical event**. Nếu retry E18 với payload khác E18 ban đầu, consumer dedup theo eventId có thể bỏ qua một nội dung quan trọng mà không nhận ra.

Có thể lưu:

~~~text
eventId
eventSchemaVersion
payloadHash
immutablePayload
~~~

Khi phát hiện cùng ID nhưng payload hash khác, coi đó là **data integrity conflict**, không âm thầm chấp nhận.

## 15. Relay pseudocode Java: claim, publish, ACK

Mã sau mô tả luồng; các kiểu `OutboxStore`, `BrokerProducer`, `Claim` là interface giả định. Điều kiện CAS/claim/mark phải được thay bằng operation **được NoSQL engine hỗ trợ đúng atomic scope**.

~~~java
void dispatchOnce(OutboxStore store, BrokerProducer producer) {
    List<OutboxEvent> due = store.findDueEvents(100);

    for (OutboxEvent candidate : due) {
        Claim claim = store.tryClaim(
            candidate.eventId(),
            "relay-node-7",
            Duration.ofSeconds(30)
        );

        if (claim == null) {
            continue; // Another worker claimed or event already done.
        }

        OutboxEvent event = claim.event();

        try {
            // The broker message keeps the SAME logical event ID
            // across every delivery attempt.
            BrokerAck ack = producer.publishAndAwaitAck(
                event.aggregateId(),  // partition/routing key
                event.eventId(),      // message/event ID
                event.eventType(),
                event.schemaVersion(),
                event.payload()
            );

            if (!ack.meetsConfiguredDurabilityContract()) {
                throw new RetryablePublishException("ACK not sufficient");
            }

            store.markPublishedIfClaimMatches(
                event.eventId(),
                claim.owner(),
                claim.generation(),
                ack.ackMetadata()
            );
        } catch (RetryablePublishException ex) {
            store.rescheduleIfClaimMatches(
                event.eventId(),
                claim.owner(),
                claim.generation(),
                computeBackoffWithJitter(event.attemptCount())
            );
        } catch (UnknownPublishOutcomeException ex) {
            // May have been accepted by the broker.
            // Retrying may duplicate delivery; consumer MUST deduplicate.
            store.rescheduleIfClaimMatches(
                event.eventId(),
                claim.owner(),
                claim.generation(),
                computeBackoffWithJitter(event.attemptCount())
            );
        }
    }
}
~~~

### 15.1. Những điều mã giả không triển khai

- Không có driver/client thật và schema mapping.
- Không mô tả broker producer transaction/ack types.
- Không có scheduler, rate limiter, resource cleanup.
- Không xử lý mọi error class và `markPublishedIfClaimMatches` thất bại.
- Không chứng minh strict order cho hai events cùng aggregate.
- Không có DLQ, alerting, pause/replay.

**Đây không phải một đoạn code có thể copy vào production**, mà là điểm xuất phát để xác định các hợp đồng nghiệp vụ.

### 15.2. Vì sao `publishAndAwaitAck` không đảm bảo consumer xử lý?

Broker ACK nghĩa là broker chấp nhận message theo producer/configuration contract. Consumer có thể chưa đọc, chưa commit nghiệp vụ hoặc bị lỗi. Đừng trả `OrderFulfilled` cho client chỉ dựa vào producer ACK của `OrderConfirmed`.

### 15.3. Có nên delete outbox record ngay sau ACK?

Có thể, nhưng chỉ khi:

- Contract broker ACK đủ mạnh theo yêu cầu.
- Không cần replay/audit vượt cửa sổ đó.
- Có cách đối soát khi mark/delete thất bại.
- Quá trình delete không làm mất index/checkpoint cần thiết.

Thường giữ trạng thái `PUBLISHED` và cleanup theo retention rõ ràng sẽ dễ debug hơn xóa ngay tức thì.

## 16. Bốn cửa sổ crash của relay

| Điểm crash | Database outbox | Broker | Hệ quả khi restart |
| --- | --- | --- | --- |
| A. Trước khi relay đọc | PENDING | Chưa publish | Relay đọc sau, publish |
| B. Sau claim, trước send | CLAIMED | Chưa publish | Lease hết, worker khác retry |
| C. Broker đã nhận, ACK mất | PENDING/CLAIMED | **Có thể đã có event** | Retry có thể publish trùng |
| D. Broker ACK thành công, trước mark PUBLISHED | PENDING/CLAIMED | Event đã có | Retry phát lại event |

**Đây là bằng chứng trực giác vì sao at-least-once phổ biến**. Nếu muốn không phát duplicate dưới một điều kiện đặc thù, cần một giao thức giao dịch end-to-end mạnh hơn trong phạm vi vendor hỗ trợ; không mặc định transactional outbox tự làm được.

### 16.1. Điều kiện để không mất event

Outbox record phải:

1. Được commit bền cùng business change.
2. Không bị xóa trước khi delivery được xác nhận đủ.
3. Còn khả dụng cho retry/recovery sau crash.
4. Có relay chạy lại và retry thành công khi những phụ thuộc phục hồi.

Do đó câu “outbox bảo đảm event cuối cùng luôn được publish” cần kèm **liveness assumptions**: nguồn bền, broker eventually available, relay hoạt động, policy không bỏ event và khả năng phục hồi.

### 16.2. Duplicates không đồng nghĩa lỗi outbox

Hai broker messages cùng `eventId` thường là **kết quả retry hợp lệ** của at-least-once delivery. Thiết kế đúng phải khiến consumer không áp business effect hai lần.

### 16.3. ACK mất không thể suy thất bại

~~~text
Relay -> Broker: E18
Broker: persisted E18
Broker -> Relay: ACK (lost)
Relay: timeout
~~~

Nếu relay ghi `FAILED_PERMANENT` ngay khi timeout, hệ có thể mất khả năng hoàn tất đúng workflow. Thường nên đưa về retry với cùng event ID và chấp nhận duplicate.

## 17. CDC/change stream publisher: checkpoint là một phần correctness

Giả sử relay đọc stream:

~~~text
offset 100: Outbox E17 committed
offset 101: Outbox E18 committed
offset 102: Outbox E19 committed
~~~

Relay cần lưu **vị trí đã xử lý** để tiếp tục sau restart. Nhưng checkpoint và broker ACK **không cùng một transaction** nếu không có protocol kết hợp.

### 17.1. Checkpoint trước publish gây mất event

~~~text
Read E18 at offset 101.
Save checkpoint=101.
Process crashes before broker publish E18.
Restart resumes after 101.
E18 may be skipped.
~~~

**Không advance durable checkpoint vượt quá những event mà relay chưa có bảo đảm publish phù hợp.**

### 17.2. Checkpoint sau publish tạo duplicate window

~~~text
Publish E18 -> broker ACK.
Process crashes before checkpoint=101.
Restart re-reads E18.
Publishes duplicate E18.
~~~

Đây là đường at-least-once; consumer dedup là bắt buộc nếu side effect không được lặp.

### 17.3. Resume token / sequence semantics

Các sản phẩm có thể dùng:

- Resume token.
- Stream shard iterator/sequence number.
- Partition offset.
- CDC log sequence/watermark.

**Không so offsets của hai partitions độc lập** để suy event nào có causal order toàn hệ. Không tự chuyển đổi những token này thành timestamp hoặc business version.

### 17.4. Khi checkpoint đã bị retention vượt qua

Nếu connector chết lâu hơn retention, resume có thể không còn hợp lệ.

Cần có phương án:

- Scan outbox records PENDING chưa publish.
- Snapshot/backfill có reconciliation.
- Lưu commit log/change feed vào lưu trữ bền hơn.
- Kiểm soát gap và tăng alert.

Không âm thầm bắt đầu ở “latest” rồi tuyên bố toàn bộ domain events cũ đã được gửi.

### 17.5. CDC từ outbox vs CDC trực tiếp từ Order

**CDC từ outbox:** Event payload, schemaVersion và eventId là **domain intent do transaction tạo**.

**CDC trực tiếp từ Order:** Connector phải suy eventType từ before/after state hoặc delta; có thể không phân biệt được `OrderConfirmedByUser` với `OrderConfirmedByBatch` nếu chỉ thấy status mới. Khi domain semantics quan trọng, explicit outbox thường dễ kiểm soát event contract hơn.

## 18. Idempotent consumer: chặn event được áp hai lần

Giả sử Inventory Service nhận hai lần cùng `OrderConfirmed`:

~~~text
Broker delivers event E18 attempt #1.
Broker delivers event E18 attempt #2.
~~~

Consumer không được trừ stock hai lần.

### 18.1. Sai lầm: check rồi update bằng hai bước độc lập

~~~text
IF not processed(E18):
    decrement inventory
    record processed(E18)
~~~

Nếu process crash **sau decrement nhưng trước record processed**, retry E18 sẽ decrement lần nữa.

Nếu hai workers nhận duplicate đồng thời, cả hai có thể thấy `not processed` rồi cùng áp.

### 18.2. Đúng khi cùng transaction/atomic boundary

Một thiết kế inbox:

~~~text
BEGIN atomic transaction
  IF inbox[E18] already exists:
      RETURN previous result

  IF enough stock / business condition:
      reserve inventory for order O900
      INSERT inbox[E18] = PROCESSED, result=reservationId
  ELSE:
      record valid business outcome for E18
COMMIT
~~~

Điều kiện phải được kiểm tra **atomically** với business effect trong engine hỗ trợ. Nếu `inbox` và `inventory` nằm ở partitions khác mà transaction không hỗ trợ, pattern không tự an toàn.

### 18.3. Inbox schema

~~~json
{
  "consumerId": "inventory-reserver-v1",
  "eventId": "evt-O900-18-confirmed",
  "payloadHash": "sha256-of-canonical-payload",
  "result": "RESERVED",
  "reservationId": "RES-O900",
  "processedAt": "2026-11-14T08:00:03Z"
}
~~~

Định danh unique nên thường là `(consumer identity, eventId)` vì **cùng event được các consumer khác nhau xử lý độc lập**. Một event có thể phải đi qua Inventory, Notifications và Analytics; không dùng một global “processed” flag khiến các consumer còn lại bỏ qua.

### 18.4. Business key đôi khi tốt hơn event ID

Nếu hai **event IDs khác nhau** nhưng đều mang một ý định reserve cho Order O900, dedup chỉ theo event ID không ngăn double reservation.

Một business invariant như:

~~~text
At most one successful reservation per (tenantId, orderId, sku)
~~~

cần unique/conditional reservation key hoặc cơ chế tương đương. Event-id dedup giúp replay, **không thay uniqueness theo nghiệp vụ**.

### 18.5. External API chưa hỗ trợ inbox transaction

Nếu consumer gọi payment provider hay email gateway ở ngoài database, không thể đưa external call vào local transaction theo cách thông thường. Cần:

- Provider idempotency key nếu có.
- Persisted workflow state và operation ID.
- Outcome lookup/reconciliation.
- Compensation phù hợp khi không có atomicity.
- Không phát biểu “exactly-once payment” khi chưa có contract từ provider.

### 18.6. Kafka/broker offset commit là một phạm vi khác

Consumer có thể commit broker offset sau khi xử lý business effect. Nếu DB commit rồi process crash trước offset ACK, event bị replay. Nếu commit offset trước DB commit, event có thể bị bỏ qua. **Inbox + atomic business write** xử lý duplicate ở nguồn, còn offset xử lý vị trí đọc trong broker.

## 19. End-to-end flow với publisher và consumer

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant ODB as Order DB
    participant Relay as Outbox relay
    participant Broker as Broker
    participant Inv as Inventory consumer
    participant IDB as Inventory DB
    API->>ODB: Commit Order v18 and Outbox E18 atomically
    ODB-->>API: Commit ACK
    Relay->>ODB: Read E18 from outbox / stream
    ODB-->>Relay: E18
    Relay->>Broker: Publish E18, key=tenant-a/O900
    Broker-->>Relay: ACK
    Relay->>ODB: Mark E18 published
    Broker->>Inv: Deliver E18
    Inv->>IDB: Conditional reserve + inbox E18 atomically
    IDB-->>Inv: RESERVED (or prior result)
    Inv-->>Broker: Consumer ACK
~~~

### 19.1. Outbox và inbox là hai ranh giới riêng

**Order DB:** bảo vệ Order transition + event intent.

**Inventory DB:** bảo vệ reservation effect + processed event marker.

**Broker:** vận chuyển, retry và có thể phát trùng.

Tất cả cùng vận hành cho **end-to-end reliability**, nhưng không có một transaction toàn hệ chỉ vì cả hai phía đều dùng local transactions.

### 19.2. Không coi receipt của downstream là dữ liệu source đã cập nhật

Order Service nhận `Outbox E18=PUBLISHED` không chứng minh Inventory đã reserve. Nếu workflow cần biết, Inventory phải phát `StockReserved`/`StockReservationFailed` qua outbox của nó; Order Service consume và chuyển Order state theo một transaction/conditional policy riêng.

### 19.3. Cần correlation ID

Nên phân biệt:

~~~text
requestId           = HTTP request attempt / trace
logicalOperationId   = idempotency key của hành động nghiệp vụ
eventId              = một domain event cụ thể
aggregateId          = entity có lifecycle riêng
correlationId        = workflow/order xuyên nhiều events
causationId          = event/operation làm sinh ra event hiện tại
consumerId           = thành phần dùng dedup namespace
~~~

Không dùng một UUID tùy ý cho mọi vai trò nếu cần những semantics khác nhau.

## 20. Ordering: không phải event nào cũng có thể phát song song

Giả sử Order O900 có hai transitions đã commit theo thứ tự:

~~~text
Version 18: OrderConfirmed
Version 19: OrderCancelled
~~~

Nếu relay gửi E19 trước E18 và consumer xử lý mù theo thứ tự nhận:

~~~text
Consumer sees CANCELLED
Consumer then sees CONFIRMED
Final state incorrectly becomes CONFIRMED.
~~~

Outbox giúp **không mất ý định publish**, nhưng không tự bảo đảm mọi event được consumer áp đúng thứ tự.

### 20.1. Phạm vi ordering nên rõ ràng

Thường cần:

~~~text
For same aggregateId:
  E18 before E19 before E20
~~~

Không nhất thiết yêu cầu:

~~~text
All events for all orders globally have one total order.
~~~

Global total order đắt và có thể không cần cho nghiệp vụ. Các version `Order O900=18` và `Order O901=6` cũng không so được để suy causal order giữa hai Orders.

### 20.2. Aggregate version và event sequence

Một record:

~~~json
{
  "eventId": "evt-O900-19-cancelled",
  "aggregateId": "tenant-a/O900",
  "aggregateVersion": 19,
  "eventType": "OrderCancelled"
}
~~~

Consumer có thể lưu `lastAppliedAggregateVersion` và dùng **version guard** khi event là full-state transition hoặc có semantics phù hợp.

### 20.3. Out-of-order full-state snapshots

~~~text
Consumer receives E19:
  full-state Order.status=CANCELLED, version=19.
Consumer receives E18:
  full-state Order.status=CONFIRMED, version=18.
~~~

Nếu read model chỉ cần trạng thái gần nhất:

~~~text
if incoming.version > current.lastAppliedVersion:
    replace projection using incoming full state
else:
    ignore duplicate/older snapshot
~~~

Điều kiện: `aggregateVersion` thực sự **tăng đơn điệu trong một authority**, event mang snapshot đầy đủ/trạng thái đủ cho projection, và không có business side effect phải thực thi cho event bị bỏ.

### 20.4. Out-of-order delta events không thể bỏ tùy ý

~~~text
E18: add 5 points
E19: subtract 2 points
~~~

Nếu consumer nhận E19 trước, áp nó và bỏ E18 vì version thấp, kết quả sai.

Với **delta events**, cần:

- Đợi version liên tiếp, ví dụ `current=17` chỉ áp `18` rồi `19`.
- Buffer events đến sớm theo aggregate.
- Yêu cầu replay khi phát hiện gap.
- Hoặc dùng operation/CRDT semantics được thiết kế để xử lý reordering.

**Không dùng một version guard duy nhất cho mọi loại event.**

### 20.5. Broker partition key theo aggregate

Một chiến lược:

~~~text
partitionKey = tenantId + "/" + orderId
~~~

Các events cùng Order sẽ thường được gán vào cùng broker partition theo chính sách của broker, hỗ trợ ordering trong **phạm vi partition**.

Nhưng điều đó chưa đủ nếu:

- Nhiều relay workers publish **E19 trước E18** vào broker.
- Producer retry làm thay đổi thứ tự nếu cấu hình cho phép.
- Broker re-partitioning hoặc failover có semantics riêng.
- Consumer xử lý messages cùng partition theo nhiều threads, rồi commit out-of-order.

Ordering phải được bảo vệ **từ outbox selection đến publisher/broker/consumer**, không chỉ bằng partition key.

### 20.6. Giữ một publisher in-flight cho một aggregate khi cần strict order

Cách làm:

~~~text
For aggregate O900:
  eligible E18 first.
  Do not send E19 until E18 satisfies publish rule.
  Publish E19 next.
~~~

Không có nghĩa cả hệ chỉ có một worker; có thể xử lý **nhiều aggregates song song**, nhưng tuần tự hóa theo aggregate key. Tăng concurrency phải xét **hot aggregate** và hiệu năng.

### 20.7. Đừng dùng createdAt làm thứ tự duy nhất

`createdAt` có thể bị trùng hoặc clock skew. Nếu cần order chuẩn, dùng aggregate version/commit sequence/log position trong **phạm vi sản phẩm cam kết**, kèm tie-breaker/event ID cho deterministic scan.

### 20.8. Một transaction tạo nhiều events cho cùng aggregate

Nếu một transaction tạo hai domain events tại cùng aggregate version, cần thêm:

~~~text
(aggregateVersion, eventOrdinal)
~~~

Ví dụ `(18,1)` và `(18,2)`. Không gán cả hai cùng version rồi tưởng phép so version duy nhất quyết định thứ tự.

## 21. Event contract và schema evolution

Một outbox record tồn tại đủ lâu có thể được publish bởi **version ứng dụng mới hơn version tạo nó**. Consumer có thể được deploy độc lập. Vì vậy event schema cần quản lý như một API.

### 21.1. Các trường gợi ý

~~~json
{
  "eventId": "evt-O900-18-confirmed",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "aggregateType": "Order",
  "aggregateId": "tenant-a/O900",
  "aggregateVersion": 18,
  "tenantId": "tenant-a",
  "occurredAt": "2026-11-14T08:00:00Z",
  "correlationId": "checkout-512",
  "causationId": "cmd-confirm-O900",
  "payload": {
    "orderId": "O900",
    "currency": "VND",
    "totalMinorUnits": 1200000,
    "status": "CONFIRMED"
  }
}
~~~

### 21.2. Vì sao phải có schemaVersion?

Giả sử v1 dùng:

~~~json
{"total": 1200000}
~~~

v2 đổi sang:

~~~json
{"currency": "VND", "totalMinorUnits": 1200000}
~~~

Một event v1 có thể được replay sau khi consumer chỉ còn code v2. Không dùng “deploy đồng thời” làm bảo đảm, vì outbox và broker giữ events cũ.

### 21.3. Các chiến lược compatibility

- Thêm optional fields theo cách consumer cũ có thể bỏ qua.
- Không xóa/đổi nghĩa field mà không có migration contract.
- Dùng schema registry/validation nếu phù hợp.
- Hỗ trợ nhiều versions trong consumer một giai đoạn.
- Upcaster/transformer chuyển payload cũ sang model mới một cách xác định.
- Đặt thời hạn hỗ trợ/replay theo retention.

### 21.4. Event là fact đã commit, không phải command tuỳ ý

`OrderConfirmed` là **sự kiện mô tả một fact** trong domain. `ConfirmOrder` là **lệnh yêu cầu thử chuyển trạng thái**, có thể thất bại.

Nếu outbox chứa `ConfirmOrder` khi transition chưa thắng, consumer khác có thể hiểu nhầm một intent thành fact. Cần tên, payload và transaction semantics rõ.

### 21.5. Không phát mọi field nội bộ

Outbox event thường là API giữa services. Không đưa mật khẩu, token, địa chỉ cá nhân không cần thiết hay dữ liệu nhạy cảm vào broker vì “có sẵn trong document”. Áp dụng data minimization, encryption/access control, retention và policy xóa dữ liệu.

### 21.6. Quyền riêng tư và replay lịch sử

Một event payload có thể bị lưu ở outbox, broker, DLQ và analytics store. Nếu có yêu cầu xóa/anonymize dữ liệu cá nhân, cần chính sách xuyên mọi bản sao; chỉ xóa Order gốc không đủ. Thiết kế có thể dùng opaque IDs và cho consumer fetch dữ liệu cần thiết theo quyền thay vì nhúng toàn bộ PII.

## 22. Backpressure, retry và poison events

Outbox relay có thể gặp:

- Broker tạm không có leader.
- Network timeout.
- Producer bị throttled.
- Broker message vượt giới hạn kích thước.
- Event schema không hợp lệ.
- Auth/ACL lỗi.
- Partition mismatch hoặc serialization bug.

### 22.1. Phân loại retry

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Transient | Timeout, broker unavailable | Retry có backoff/jitter |
| Throttling | Quota/bandwidth vượt ngưỡng | Rate limit, adapt batch size |
| Unknown outcome | ACK mất | Retry cùng eventId; chấp nhận duplicate |
| Poison payload | Serialization/schema sai | Quarantine/DLQ + alert |
| Authorization/config | Producer thiếu ACL | Sửa cấu hình, không retry dồn dập |
| Data integrity | Cùng eventId khác payloadHash | Block + điều tra |
| Ordering gap | E19 tới trước E18 | Buffer/replay hoặc pause aggregate |

### 22.2. Exponential backoff với jitter

Ví dụ thuật toán:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
nextAttempt = now + randomizedDelayWithin(delay)
~~~

Nếu hàng nghìn events cùng fail lúc 10:00, jitter tránh tất cả retry đồng loạt sau 1s, 2s, 4s và quá tải broker khi vừa phục hồi.

### 22.3. Tại sao retry không nên vô hạn theo nhịp gấp?

Một outbox event bị lỗi payload không thể serialize có thể retry 1 triệu lần mà vẫn không thành công, gây log spam và chiếm worker. Cần quarantine/DLQ, alert và quy trình sửa/replay.

### 22.4. Nhưng DLQ không phải “đã xử lý xong”

Nếu event `OrderConfirmed` bị đưa vào DLQ, downstream có thể vẫn chưa giữ hàng. Không được đánh dấu Order workflow hoàn tất chỉ vì relay không còn retry event đó.

Nên có trạng thái:

~~~text
QUARANTINED
  reason = SCHEMA_INVALID
  owner = responsible team
  replay policy = after repair
~~~

### 22.5. Poison event và strict ordering

Nếu E18 không thể publish và E19 cùng Order đã sẵn sàng, một hệ muốn bảo vệ per-aggregate order cần **tạm chặn E19** hoặc có policy skip/backfill rõ. Nếu cứ publish E19, consumer phải đủ khả năng xử lý gap/out-of-order.

Đây là trade-off **liveness vs ordering**: không có một quyết định phù hợp cho mọi domain.

### 22.6. Backpressure từ consumer

Broker ACK nhanh không chứng minh downstream theo kịp. Consumer lag tăng có thể cần:

- Scale consumer workers/partitions.
- Hạn chế producer nếu downstream resources có hạn.
- Batch processing khi event semantics cho phép.
- Phân loại hot aggregates/partitions.
- Theo dõi DLQ và end-to-end completion.

Nếu broker backlog vượt retention, có nguy cơ mất khả năng replay dù outbox relay đã đánh dấu `PUBLISHED`.

## 23. Retention và dọn outbox an toàn

Outbox records sẽ tăng liên tục. Nếu 2.000 events/s, mỗi event 2 KiB:

\[
\text{Raw write volume per day}
=2000\times 2048\times 86400
\approx 353{,}9\ \text{GB/ngày}
\]

Đây là dung lượng **payload raw xấp xỉ**, chưa tính indexes, replicas, compression, metadata hay storage class. Một hệ thực cần capacity planning.

### 23.1. Không giữ PENDING vô hạn mà không cảnh báo

Nếu relay ngừng một ngày, outbox có thể backlog lớn. Cần:

- Alert theo **oldest PENDING age**.
- Relay autoscaling có giới hạn.
- Phân bổ read/write capacity.
- Quy trình backfill.
- Dead-letter triage.
- Có cách kiểm tra event nào đã publish nhưng chưa được mark.

### 23.2. Cleanup chỉ sau publish và policy audit

Một cleanup worker có thể:

~~~text
DELETE FROM outbox
WHERE state = PUBLISHED
  AND publishedAt < retentionCutoff
~~~

Nhưng phải tuân thủ replay/audit needs, retention của broker/stream và business obligations. Nếu cần replay domain events sau nhiều tháng, outbox database có thể không phải nguồn duy nhất; có thể archive sang lưu trữ bền phù hợp.

### 23.3. TTL không thay cleanup logic

TTL tự xóa record theo thời gian không được dùng để quyết định event đã được publish. Event `PENDING` đến hạn TTL nhưng broker chưa nhận là **event loss nếu bị xóa**.

Nếu chỉ áp TTL cho `PUBLISHED` và engine có cơ chế xóa bất đồng bộ, cần hiểu timing và read/index behavior; nó vẫn không thay yêu cầu đối soát.

### 23.4. Event payload lớn

Một event 50 MB có thể vượt giới hạn outbox item/transaction hoặc broker message. Có thể dùng **claim-check pattern**:

~~~text
Outbox event:
  eventId
  payloadRef = durable object store URI
  payloadHash
  schemaVersion
~~~

Nhưng nếu payload ở **object store khác database**, việc ghi object và outbox record **không còn tự nguyên tử**. Cần đặt object bền trước, xử lý orphan objects/cleanup, hoặc thiết kế content-addressed immutable storage và recovery/reconciliation; không gọi toàn bộ hai hệ đó là một DB transaction.

### 23.5. Immutable event và GDPR/delete

Đừng nhầm event immutability với được giữ thông tin cá nhân vô hạn. Có thể thiết kế event chỉ chứa keys/IDs, tokenization hoặc retention policy phù hợp, đồng thời giữ audit tối thiểu cần thiết.

## 24. Backfill và reconciliation khi hệ đã từng mất event

Transactional outbox giúp **ngăn tạo khe hở mới** khi áp dụng đúng. Nhưng một hệ đã từng chạy dual-write có thể có Orders `CONFIRMED` mà không có event.

### 24.1. Phân biệt “event chưa publish” và “event chưa tồn tại”

~~~text
Case A:
  Order CONFIRMED, Outbox E18=PENDING.
  -> Relay/retry có thể publish.

Case B:
  Order CONFIRMED, no Outbox E18 at all.
  -> Không thể chờ relay quét PENDING.
  -> Cần repair/backfill business state hoặc event history.
~~~

### 24.2. Backfill từ nguồn có thẩm quyền

Một kế hoạch:

1. Xác định khoảng thời gian/scope bị ảnh hưởng.
2. Đọc Order/source-of-truth có version.
3. Đối chiếu outbox/broker/event audit.
4. Sinh **repair event hoặc reconstructed event** theo policy rõ; không giả vờ nó chắc chắn có cùng semantics với event lịch sử chưa từng được ghi.
5. Gắn `reconciliationRunId`, provenance và reason.
6. Publish/replay qua cùng cơ chế idempotent.
7. Kiểm tra downstream state trước/sau.

### 24.3. Cẩn thận khi backfill data đã thay đổi thêm

Nếu O900 hiện đã `SHIPPED`, không được tái tạo mù một `OrderConfirmed` với payload status CONFIRMED rồi áp như event mới nhất. Có thể cần lịch sử events, snapshot state với sourceVersion hiện hành hoặc domain-specific compensation.

### 24.4. Dual-run migration sang transactional outbox

Khi chuyển từ `UPDATE then PUBLISH` sang outbox:

- Định nghĩa điểm cutover và feature flag.
- Không để hai publisher độc lập tạo hai **event IDs khác nhau** cho cùng transition mà downstream coi là hai tác động.
- Dùng cùng event identity/operationId trong giai đoạn chuyển tiếp khi có thể.
- Đối soát backlog của đường cũ và đường mới.
- Theo dõi duplicate rate và event gaps.
- Chỉ tắt đường cũ sau khi các invariants đã được xác nhận.

### 24.5. Consumer rebuild từ event stream

Nếu downstream projection cần rebuild, cần biết retention và khả năng truy cập event history. Outbox đã cleanup có thể không giữ toàn bộ lịch sử; broker cũng có retention. Hãy thiết kế **snapshot + event replay** hoặc nguồn authoritative để backfill theo đúng consistency yêu cầu.

## 25. Observability: biết event bị kẹt ở bước nào

Nếu chỉ log “publish failed” mà không có event ID, aggregate version, source commit state và broker response, rất khó xác định một workflow có bị mất hay bị duplicate.

| Metric | Điều muốn theo dõi |
| --- | --- |
| `outbox_events_created_total` | Số event intent được commit |
| `outbox_pending_count` | Backlog chưa publish |
| `outbox_oldest_pending_age_seconds` | Event pending lâu nhất |
| `outbox_claim_conflicts_total` | Các relay workers tranh claim |
| `outbox_claim_expired_total` | Worker crash/pause/lease expired |
| `outbox_publish_attempts_total` | Số lần cố publish |
| `outbox_publish_success_total` | ACK đúng cấu hình |
| `outbox_unknown_publish_outcomes_total` | Timeout/ACK không rõ |
| `outbox_retry_scheduled_total` | Số retries |
| `outbox_quarantined_total` | Events cần xử lý thủ công |
| `outbox_stream_checkpoint_lag` | CDC consumer chậm bao nhiêu |
| `consumer_duplicate_events_total` | Event được giao lại |
| `consumer_inbox_conflicts_total` | Nhiều consumer workers tranh cùng event |
| `aggregate_sequence_gaps_total` | Thiếu một version trong chuỗi |
| `reconciliation_backlog_total` | Công việc cần đối soát |
| `business_invariant_violations_total` | Double charge, oversell, double reservation |

### 25.1. Phân biệt ba loại độ trễ

~~~text
Commit-to-publish:
  outbox transaction commit -> broker ACK

Publish-to-consume:
  broker ACK -> consumer business commit

End-to-end workflow:
  original command accepted -> downstream state settled
~~~

Broker publish nhanh chưa chứng minh Inventory đã reserve. Cần đo downstream completion theo workflow.

### 25.2. Correlation và causation

Một trace có thể chứa:

~~~json
{
  "eventId": "evt-O900-18-confirmed",
  "aggregateId": "tenant-a/O900",
  "aggregateVersion": 18,
  "logicalOperationId": "confirm-O900-req-15",
  "correlationId": "checkout-512",
  "causationId": "cmd-confirm-O900",
  "relayAttempt": 3,
  "brokerPublishOutcome": "UNKNOWN",
  "consumerId": "inventory-reserver",
  "consumerOutcome": "ALREADY_PROCESSED"
}
~~~

Không gắn raw eventId/aggregateId vào metric labels nếu có hàng triệu giá trị; chi tiết thuộc trace/log có kiểm soát quyền truy cập.

### 25.3. Alert theo bất biến

Relay trả health=200 nhưng pending backlog tăng mỗi giờ thì workflow vẫn có vấn đề. Nên alert:

- Event PENDING lâu hơn SLO.
- Không có broker ACK dù backlog dương.
- Stream checkpoint lag gần vượt retention.
- Quarantined event không có owner.
- Event gaps và duplicate business effects.
- End-to-end workflow không đạt thời hạn.

## 26. Capacity planning và hot partitions

Giả sử 4.000 events/s, payload trung bình 1,5 KiB:

\[
\text{Raw bytes/s}=4000\times1536=6{,}144{,}000
\]

Một ngày:

\[
6{,}144{,}000\times86400\approx530{,}8\text{ GB}
\]

Đây là payload raw xấp xỉ, chưa tính index, replication, compression, transaction log và broker copies. Một outbox partition nóng có thể bị throttling dù database có khả năng lưu tổng dung lượng lớn.

### 26.1. Chia polling workload

~~~text
bucket = stableHash(aggregateId) % 64

partition = (tenantId, bucket, day)
~~~

Relay có thể chia buckets cho nhiều workers, nhưng **per-aggregate ordering** vẫn cần giữ nếu domain yêu cầu. Một tenant lớn có thể chiếm nhiều buckets, còn tenants nhỏ cần fairness.

### 26.2. Không quét toàn table mỗi giây

Khi có hàng triệu records đã publish, full scan tốn read units, tăng p95 và chi phí. Tạo index/access pattern cho các PENDING records đến hạn; engine NoSQL khác nhau có query semantics khác nhau.

### 26.3. Event quá lớn

Payload lớn có thể vượt transaction/item/broker limits. Có thể dùng claim-check với payload reference đến object store, nhưng việc tạo object ở hệ khác **không tự nằm trong database transaction**. Cần durable immutable object, hash, orphan cleanup và recovery để không tạo event trỏ tới payload chưa có.

### 26.4. Không để hot tenant làm chậm mọi tenant

Có thể dùng per-tenant rate limiting, bucket routing, separate worker pools. Nếu ưu tiên event theo trọng số, cần xác định nó ảnh hưởng strict order từng aggregate ra sao.

## 27. Fault-injection lab cho Order v17 → v18

Lab chỉ chạy trên môi trường kiểm thử riêng; không kill hay partition production.

~~~yaml
experiment: transactional-outbox-row395
aggregate:
  id: tenant-a/O900
  status: CREATED
  version: 17
command:
  logicalOperationId: confirm-O900-req-15
  expectedVersion: 17
  newStatus: CONFIRMED
outbox:
  eventId: evt-O900-18-confirmed
  eventType: OrderConfirmed
  aggregateVersion: 18
assertions:
  - "committed Order CONFIRMED implies committed outbox E18"
  - "aborted transition creates no success outbox event"
  - "duplicate delivery applies at most one inventory reservation"
  - "pending event survives relay restart"
~~~

### 27.1. Case A — API crash trước commit

1. Mở transaction.
2. Update Order và insert Outbox E18.
3. Crash trước commit.
4. Restart và đọc bằng consistency phù hợp.
5. Theo transaction contract, không được thấy Order CONFIRMED **do transaction này** nhưng thiếu E18.

### 27.2. Case B — API crash sau commit, trước ACK

1. Commit transaction thành công.
2. Mất response đối với client.
3. Retry cùng logicalOperationId.
4. Tra outcome từ nguồn; **không tăng Order version lần nữa** hoặc tạo domain event mới với ID khác.

### 27.3. Case C — Relay crash trước publish

1. Outbox E18=PENDING.
2. Relay A claim E18 rồi crash trước broker send.
3. Claim hết hạn hoặc recovery đưa E18 trở lại eligible.
4. Worker khác publish E18.

### 27.4. Case D — Broker ACK bị mất

1. Relay publish E18.
2. Broker đã nhận và commit message.
3. Chặn ACK quay về relay.
4. Relay timeout rồi gửi lại **cùng E18 eventId**.
5. Broker có thể nhận hai attempts nhưng Inventory chỉ reserve một lần.

### 27.5. Case E — Relay crash sau ACK, trước mark PUBLISHED

1. Broker ACK E18.
2. Relay crash trước update outbox status.
3. E18 được quét lại sau restart.
4. Relay publish duplicate.
5. Consumer inbox/idempotent business key bảo vệ effect.

### 27.6. Case F — Consumer crash sau DB commit, trước broker ACK

1. Inventory nhận E18.
2. Transaction reserve + inbox E18 commit.
3. Consumer crash trước ACK.
4. Broker redeliver E18.
5. Consumer tra inbox và trả kết quả cũ, không reserve thêm.

### 27.7. Case G — Hai relay workers tranh event

1. Hai workers đọc cùng PENDING event.
2. Conditional claim để chỉ một worker thắng trong một generation.
3. Pause worker A lâu hơn lease; B takeover.
4. A resume; duplicate publish **vẫn có thể xảy ra**.
5. Outbox claim-generation guard và consumer idempotency xử lý tương ứng.

### 27.8. Case H — Out-of-order E19 trước E18

1. Commit E18=Confirmed và E19=Cancelled cho cùng Order.
2. Cố ý publish/consume E19 trước E18.
3. Với full-state projection, version guard chặn regression.
4. Với delta operations, phải buffer/replay thay vì bỏ E18.

### 27.9. Case I — CDC resume token hết hạn

1. Lưu checkpoint trước E18.
2. Ngắt connector lâu hơn stream retention trong lab.
3. Restart và xác minh phát hiện gap.
4. Backfill/reconcile từ nguồn bền, không âm thầm bắt đầu tại latest.

### 27.10. Case J — Outbox khác partition atomic

1. Đặt business item và outbox item ở hai logical partitions.
2. Đánh giá engine chỉ cho transactional batch trong một partition.
3. Không tuyên bố cặp writes là nguyên tử nếu API không hỗ trợ.
4. Sửa bằng transaction bao đúng scope hoặc colocate vào cùng atomic unit.

## 28. Assertions sau fault injection

**Atomic source:**

~~~text
Order CONFIRMED at version 18
  => a committed E18 outbox intent exists.

Aborted Order transition
  => no success event E18 from that transition.
~~~

**At-most-once business effect theo logical event:**

~~~text
Repeated E18 delivery
  => at most one successful reservation for O900.
~~~

**Ordering:**

~~~text
Projection must not regress from version 19 to version 18.
Delta events must not be silently skipped.
~~~

**Conditional liveness:**

~~~text
If source, relay and broker eventually recover,
and event is retained, pending events eventually progress.
~~~

Điều cuối là bảo đảm **với giả định về recovery và availability**, không phải “event đến ngay cả khi broker vĩnh viễn offline”.

### 28.1. Không chỉ xem final state

Hai reservations có thể đã được tạo, rồi một cái bị xóa. Trạng thái cuối “chỉ một reservation” không chứng minh chưa từng double reserve. Thu history về ACK, side effect IDs và transitions.

### 28.2. Clock skew

Timestamp từ hai services có thể lệch. Dùng aggregate version, DB transaction/commit position, broker partition offset, logicalOperationId và causal trace để phân tích thứ tự; không lấy wall-clock sort làm bằng chứng duy nhất.

## 29. Ma trận chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể | Câu hỏi cần hỏi |
| --- | --- | --- |
| Order đã CONFIRMED nhưng không có outbox event | Hai writes không cùng atomic scope hoặc bug migration | Transaction API, partition key, commit history |
| Outbox PENDING tăng đều | Relay ngừng, broker lỗi, query/index chậm | Oldest pending age, relay worker health |
| Broker thấy cùng eventId nhiều lần | ACK mất, relay crash, lease expiry | Publisher retry và consumer dedup |
| Inventory reserve hai lần | Consumer thiếu inbox hoặc unique business key | Transaction boundary ở consumer |
| E19 được xử lý trước E18 | Relay song song, broker partition/order | Aggregate sequencing, delta vs snapshot |
| Events biến mất sau connector restart | Checkpoint trước publish, stream gap | Resume token, retention, backfill |
| Outbox table quá lớn | Retention/cleanup chưa có | Published age và audit policy |
| Một tenant bị chậm | Hot partition, backlog hoặc unfair scheduling | Partition key, per-tenant QPS |
| Client timeout nhưng outbox đã tạo | Unknown transaction outcome | Idempotency, operation lookup |
| Event lỗi serialize liên tục | Schema mismatch/poison payload | Event schemaVersion, payloadHash |
| Consumer ACK nhanh nhưng workflow không hoàn tất | Downstream effect chưa xảy ra | End-to-end correlation/status |
| Transaction conflict tăng | Contention cùng Order/outbox | Access patterns, CAS retries |
| Analytics đảo trạng thái | Out-of-order snapshots/deltas | AggregateVersion, consumer ordering |
| Duplicate event ID với payload khác | ID generator hoặc mutable payload | Integrity conflict, immutable event |
| PUBLISHED nhưng broker history không tìm thấy | ACK/retention assumptions sai hoặc thao tác manual | Producer config, broker retention/replay |

### 29.1. Trình tự điều tra

1. Source Order đã commit transition nào và ở version bao nhiêu?
2. Event record có tồn tại trong cùng atomic commit không?
3. Có cùng eventId và payloadHash khi retry không?
4. Relay đã thử publish bao nhiêu lần?
5. Broker ACK là loại nào và broker có retention/compaction gì?
6. CDC checkpoint có vượt qua event chưa publish không?
7. Consumer nhận event mấy lần và có cùng consumer ID không?
8. Inbox marker và business mutation có cùng transaction không?
9. Ordering theo aggregate/partition có được bảo vệ không?
10. Có thay đổi topology, replay, schema, retention hay region owner không?

## 30. Những sai lầm thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| UPDATE DB rồi publish và gọi đó là “outbox” | Crash giữa hai bước làm mất event | Commit state + intent cùng atomic unit |
| Broker publish trong DB transaction callback | Broker không tự rollback theo DB | Chỉ ghi outbox trong transaction |
| Hai collections cùng DB nên “tự nguyên tử” | Cùng DB khác cùng transaction | Dùng transaction API đúng scope |
| Một logged batch nên “tương đương ACID” | Batch semantics có giới hạn riêng | Đọc docs engine/version, chọn đúng primitive |
| TransactionalBatch across partitions | Vượt scope hỗ trợ | Colocate hoặc dùng API khác |
| CDC là exactly-once broker delivery | Checkpoint/ACK có crash window | Event ID và idempotent consumer |
| Relay mark PUBLISHED trước ACK | Crash có thể bỏ publish | Mark/checkpoint sau ACK đúng contract |
| Relay xóa ngay sau send không chờ ACK | Có thể mất event | Persist đến delivery confirmation |
| Consumer check inbox rồi mutate tách rời | Crash/đua có thể double apply | Atomic inbox + business effect |
| Dedup theo eventId nhưng business key không unique | Hai events khác ID vẫn double side effect | Unique reservation/order key |
| Mỗi retry tạo event ID mới | Consumer không nhận ra duplicate | Stable logical event identity |
| Chỉ lưu one boolean “published” | Thiếu retry/unknown/audit information | State, attempt, ACK metadata |
| Claim lease có nghĩa chỉ publish một lần | Stale worker vẫn có thể publish | At-least-once, claim guard, consumer dedup |
| Mọi events vào một hot partition | Throughput/throttling bottleneck | Bucketing/partitioning phù hợp |
| Ordering bằng createdAt | Clock skew, ties | Aggregate version/sequence |
| Skip E18 khi đã thấy E19 delta | Mất một effect | Buffer/replay sequence |
| DLQ nghĩa business flow thành công | Event chưa được xử lý | Quarantine+recovery owner |
| TTL xóa PENDING sau 7 ngày | Event loss khi broker outage | Cleanup chỉ sau publish policy |
| Broker offset là global business version | Offset scoped theo partition | Aggregate version độc lập |
| Outbox schema không versioned | Replay phá consumer mới | Event schemaVersion và compatibility |
| Payload sửa sau commit | Cùng ID nhiều ý nghĩa | Immutable payload/hash |
| Chỉ đo worker health | Không phát hiện workflow kẹt | Oldest PENDING, lag, invariant metrics |
| Outbox giải quyết distributed transaction toàn saga | Chỉ local atomicity | Workflow state, compensation/reconciliation |
| Coi successful event publish = downstream success | Consumer chưa xử lý | Downstream acknowledgement/event |
| Chỉ kiểm thử happy path | Bỏ lỡ duplicate/loss windows | Fault injection tại commit/ACK/checkpoint |

## 31. Bài tập thực hành

### Bài 1 — Tìm dual-write gap

Đoạn chương trình:

~~~text
updateOrderStatus("O900", "CONFIRMED")
publish("OrderConfirmed", "O900")
~~~

1. Liệt kê mọi cửa sổ crash.
2. Đảo thứ tự hai dòng có giải quyết vấn đề không?
3. Vì sao một try/catch không đủ?
4. Một outbox record phải được ghi khi nào?

### Bài 2 — Phạm vi atomicity

Engine A có atomic write **một document**, không hỗ trợ multi-document transaction.

1. Có thể ghi Order document và outbox document độc lập nhưng vẫn gọi transactional outbox không?
2. Thiết kế pending event **embedded trong Order** như thế nào?
3. Khi array pendingEvents tăng mãi, cần xử lý gì?
4. Relay xóa event đã publish như thế nào để không xóa nhầm event mới?

### Bài 3 — MongoDB transaction

Order ở §orders§, event ở §outbox§.

1. Những writes nào phải ở cùng session transaction?
2. Nếu conditional update không match, nên tạo event không?
3. Nếu commit ACK mất, application xử lý ra sao?
4. Nếu collections ở hai shards, cần đọc điều gì trong docs?

### Bài 4 — DynamoDB TransactWriteItems

Một transaction gồm:

~~~text
Update Order item: condition version=17
Put Outbox item: condition eventId not exists
~~~

1. Lợi ích của transaction là gì?
2. Nếu một condition failed, result cần hiểu sao?
3. Nếu chuyển sang global multi-region writes, có tự giữ atomic cross-region không?
4. Nếu client retry sau một ngày, vì sao cần application idempotency bền?

### Bài 5 — Cosmos DB logical partition

Order item có §tenantOrderKey=tenant-a/O900§, Outbox item có §tenantOrderKey=tenant-a/O901§.

1. Hai items có nằm trong một logical partition không?
2. Có thể dùng một TransactionalBatch như bài học không?
3. Cần thay partition key hoặc transaction design thế nào?
4. Trade-off giữa colocating và hot partition là gì?

### Bài 6 — Cassandra batch semantics

Team dùng:

~~~sql
BEGIN BATCH
  UPDATE orders ...;
  INSERT INTO outbox ...;
APPLY BATCH;
~~~

1. Vì sao không kết luận ngay đó là multi-partition ACID transaction?
2. Cần đọc chính xác những guarantees nào của logged/unlogged batch?
3. Nếu một update dùng conditional LWT, scope điều kiện là gì?
4. Nếu không có atomic boundary, có hướng kiến trúc nào khác?

### Bài 7 — Redis như outbox

Team dùng Redis §SET order§ rồi §PUBLISH event§.

1. Đây có phải transactional outbox không? Vì sao?
2. Nếu process crash giữa hai lệnh, điều gì xảy ra?
3. Nếu dùng MULTI/EXEC hoặc script, những điều gì vẫn phải đọc về durability/failover?
4. Broker publish ngoài Redis vẫn cần gì?

### Bài 8 — Relay crash sau ACK

~~~text
T1: Relay publishes E18.
T2: Broker ACK success.
T3: Relay crashes.
T4: Relay restarts with E18 still PENDING.
~~~

1. Có thể có bao nhiêu broker deliveries?
2. Đây có phải lỗi kiến trúc outbox không?
3. Consumer cần gì để không reserve hai lần?
4. Nếu event payload thay đổi giữa hai attempts thì sao?

### Bài 9 — Claim lease hết hạn

Relay A đã claim E18, bị pause. Relay B claim sau khi lease hết hạn, publish thành công. A resume và publish.

1. CAS claim đã giúp điều gì?
2. Vì sao vẫn có duplicate?
3. Claim generation bảo vệ metadata update thế nào?
4. Destination-side idempotency giải quyết điều gì khác?

### Bài 10 — Inbox chưa đủ nguyên tử

Consumer làm:

~~~text
1. decrement inventory
2. insert inbox E18 as processed
~~~

1. Crash giữa hai bước tạo lỗi gì?
2. Đảo thứ tự có giải quyết không?
3. Làm sao đặt business mutation và inbox trong cùng atomic boundary?
4. Nếu nguồn không hỗ trợ transaction đa records, cần model lại gì?

### Bài 11 — Business ID khác event ID

OrderConfirmed E18 và OrderPaid E19 đều kích hoạt reserve cho cùng Order do bug routing.

1. Dedup theo eventId có chặn double reservation không?
2. Một business key uniqueness nên gồm những trường nào?
3. Nếu hai side effects có ý nghĩa khác nhau, cần state machine thế nào?

### Bài 12 — Out-of-order events

~~~text
E18: OrderConfirmed (version 18)
E19: OrderCancelled (version 19)
~~~

1. Consumer nhận E19 trước E18; full-state projection nên làm gì?
2. Nếu E18/E19 là deltas liên quan counter, version guard có đủ không?
3. Cách đảm bảo per-aggregate order từ relay qua broker?
4. Có cần global order cho mọi Orders không?

### Bài 13 — CDC checkpoint

Connector đọc E18 rồi lưu checkpoint trước khi publish. Sau đó crash.

1. Event có thể bị mất thế nào?
2. Nếu publish trước checkpoint, lỗi khác nào xuất hiện?
3. Có thể dùng source outbox records để backfill không?
4. Nếu stream position đã hết retention, cần làm gì?

### Bài 14 — Event schema evolution

Event v1 chứa §total§ dạng number. Event v2 chứa §currency§ và §totalMinorUnits§.

1. Consumer hỗ trợ cả v1/v2 ra sao?
2. Backfill event cũ cần gì?
3. Vì sao event ID phải ổn định khi upgrade relay?
4. Có nên publish raw Order chứa mọi trường PII không?

### Bài 15 — Poison event

Một event có payload không thể deserialize. Relay retry 10.000 lần mỗi giây.

1. Vấn đề về tải và liveness?
2. Khi nào dùng quarantine/DLQ?
3. Nếu cần strict order, E19 có được đi trước E18 bị lỗi không?
4. Ai chịu trách nhiệm sửa và replay?

### Bài 16 — Retention và backfill

Outbox giữ §PUBLISHED§ 7 ngày; broker giữ event 2 ngày; một consumer offline 15 ngày.

1. Consumer có thể replay từ broker không?
2. Có thể replay từ outbox không?
3. Nguồn nào là source-of-truth để rebuild?
4. Cần đổi retention/archival/snapshot strategy thế nào?

### Bài 17 — Capacity planning

Hệ tạo 3.000 events/s, payload 2 KiB, replication factor 3.

1. Tính raw payload mỗi giây và một ngày.
2. Vì sao tổng storage thực lớn hơn raw × RF?
3. Một partition §OUTBOX#ALL§ có thể gây vấn đề gì?
4. Polling scan/index nên thiết kế theo access pattern nào?

### Bài 18 — End-to-end checkout saga

Workflow:

~~~text
OrderConfirmed
  -> InventoryReserved
  -> PaymentCaptured
  -> ShipmentRequested
~~~

1. Mỗi service cần transactional outbox riêng ở đâu?
2. Consumer cần inbox/unique business key ở đâu?
3. Nếu InventoryFailed, có thể dùng compensation nào?
4. Nếu Payment API timeout, saga nên xem outcome là gì?
5. Có thể tuyên bố một transaction toàn workflow không?

### Bài 19 — Design review phiên bản sản phẩm

Chọn một NoSQL engine bạn đang dùng và hoàn thiện:

~~~text
Engine / SDK versions:
Deployment topology:
Atomic transaction API:
Supported data scope:
Read / write concern or consistency:
Unknown commit outcome behavior:
CDC / stream / resume semantics:
Retention and TTL policy:
Cross-region constraints:
Broker ACK semantics:
Recovery after relay failure:
Official documentation sections:
~~~

Không dùng benchmark hoặc một blog cũ làm nguồn cho những bảo đảm correctness quan trọng.

### Bài 20 — Fault-injection test plan

Thiết kế test với hai API instances, ba relay workers, một broker và hai Inventory consumers.

- 1.000 logical OrderConfirm operations.
- 200 API attempts bị timeout sau database commit.
- 100 broker ACKs bị drop.
- 20 relay crashes sau ACK, trước mark.
- 30 consumer crashes sau DB commit, trước ACK.
- Events cùng Order có hai transitions liên tiếp.

Hãy xác định assertions về:

1. Mỗi committed Order transition phải có outbox intent.
2. Số distinct domain event IDs theo business transitions.
3. At-most-once inventory reservation effect theo Order.
4. Không đảo trạng thái projection.
5. Không mất events do checkpoint hoặc retention.
6. Backlog có thể hồi phục khi hệ khỏe lại.
7. Alerting cho PENDING quá lâu và unknown outcomes.

## 32. Gợi ý giải một số bài

### 32.1. Bài 8 — Relay crash sau ACK

Relay có thể publish **hai lần hoặc nhiều lần** trong các lần retry cho cùng event. Đây là behavior phù hợp với at-least-once khi không có một atomic commit chung cho broker ACK và outbox marker. Giải pháp là giữ **cùng eventId**, dedup ở consumer và business-key guard tại destination khi cần.

### 32.2. Bài 10 — Đảo thứ tự không tạo atomicity

Nếu ghi inbox trước rồi decrement inventory, crash giữa hai bước khiến event bị coi đã xử lý dù effect **chưa xảy ra**. Nếu decrement trước inbox, crash tạo double decrement ở replay. Phải có transaction/atomic boundary hoặc workflow phục hồi được bảo vệ bởi một source-of-truth.

### 32.3. Bài 12 — Full state và delta khác nhau

Full-state version19 có thể làm projection đi thẳng đến state mới nhất, sau đó bỏ snapshot version18. Nhưng delta version18 có thể cần cho phép cộng/trừ, nên phải giữ thứ tự/gap management.

### 32.4. Bài 17 — Tính raw volume

\[
3000\times2048=6{,}144{,}000\text{ bytes/s}
\]

\[
6{,}144{,}000\times86400\approx530{,}8\text{ GB/day raw}
\]

Với RF=3, chỉ dữ liệu thô đã xấp xỉ ba lần trước khi tính metadata, indexes, WAL/log, retry attempts và storage optimization. Không lấy con số raw làm capacity thực mà không đo/cân nhắc cấu hình.

## 33. Checklist triển khai transactional outbox

### Nguồn dữ liệu và commit

1. Business aggregate và outbox intent có thực sự ở **cùng atomic commit boundary** không?
2. Transaction API có bao đúng collections/tables/partitions/shards dùng không?
3. Conditional mutation có chặn business conflict không?
4. Outbox event được tạo **chỉ sau khi transition thực sự được chấp nhận** không?
5. Event ID có ổn định qua API retries/transaction callback retries không?
6. Unknown commit outcome có đường tra idempotency/source state không?
7. Write ACK/durability phù hợp SLO khi failover không?
8. Payload/event schema có kích thước nằm trong transaction limits không?

### Relay và broker

9. Relay dùng polling hay CDC, có checkpoint/claim rõ không?
10. Query PENDING có index/partition design phù hợp không?
11. Broker ACK semantics đã được xác định và cấu hình đúng chưa?
12. Mark PUBLISHED/checkpoint có diễn ra **sau** publish ACK phù hợp không?
13. Relay retry bằng cùng event ID và immutable payload không?
14. Có bounded retries, backoff, jitter, DLQ/quarantine và owner xử lý không?
15. Multi-relay claims có CAS/lease generation và recovery không?
16. Có strict order theo aggregate khi business yêu cầu không?
17. CDC retention/resume/backfill có chịu được outage dài không?

### Consumer và nghiệp vụ

18. Inbox/processed-event marker có scope theo consumer ID không?
19. Inbox và business effect có commit atomically nếu cần không?
20. Có unique business key để chống hai event IDs tạo cùng side effect không?
21. External provider có idempotency/outcome lookup và reconciliation không?
22. Consumer có phân biệt full-state vs delta events không?
23. Có chính sách xử lý gaps, duplicates và replay không?
24. Downstream outcome có được phản hồi qua event/workflow riêng khi cần không?

### Vận hành và thay đổi

25. Event schema có version và compatibility policy không?
26. Retention/TTL có tránh xóa PENDING chưa publish không?
27. Có metrics oldest pending, CDC lag, duplicate delivery, DLQ, consumer backlog không?
28. Có fault tests tại DB commit, broker ACK, consumer commit không?
29. Có cách reconcile những Orders đã commit nhưng event lịch sử chưa từng được tạo không?
30. Có chính sách tenant isolation, PII, encryption và quyền truy cập broker/outbox không?
31. Khi đổi topology/Region/version, atomicity contract có được review lại không?

## Kết luận

**Transactional outbox** là một mẫu tích hợp giúp ngăn “ghi state thành công nhưng quên phát event” bằng cách **lưu state change và event intent trong cùng một commit nguyên tử**. Trong NoSQL, điều kiện tiên quyết là hiểu **đúng khả năng atomicity của engine**: một document, một logical partition, multi-document/item transaction hoặc một cơ chế CDC trực tiếp từ commit log với những trade-offs riêng.

Những điều cần nhớ:

- **Dual-write DB → broker không nguyên tử.** Đổi thứ tự hai writes không tự khắc phục crash window.
- **Transaction chỉ có giá trị trong phạm vi được hỗ trợ.** Không suy hai records cùng database hoặc cùng batch luôn commit nguyên tử.
- **MongoDB multi-document transactions, DynamoDB TransactWriteItems, Cosmos DB TransactionalBatch** có các phạm vi/cấu hình khác nhau; phải đọc docs đúng version/topology.
- **Embedded outbox** có thể tận dụng single-document atomic update, nhưng phải giải quyết document size, concurrency và cleanup.
- **CDC/change streams** giúp phát event từ thay đổi đã commit, nhưng cần checkpoint, retention, resume, idempotency và mô hình domain event.
- **Relay thường mang ngữ nghĩa at-least-once**. Publish thành công rồi crash trước mark/checkpoint sẽ dẫn đến duplicate attempts.
- **Consumer inbox/idempotency** phải bảo vệ side effect ở downstream, tốt nhất bằng atomic dedup + mutation nếu engine hỗ trợ.
- **Ordering có scope**: aggregate version, broker partition và relay sequencing cần phối hợp, đặc biệt với delta events.
- **Retry không được đổi event identity**, và timeout sau commit có thể là unknown outcome.
- **DLQ, retention và backfill** là phần của reliability design; không xóa PENDING chỉ vì hết TTL.
- **Một local outbox không tạo distributed transaction cho saga nhiều services**. Mỗi service vẫn cần authority, workflow state và reconciliation của mình.
- **Kiểm chứng bằng fault-injection histories và business invariants**, không chỉ bằng số event đã gửi hoặc node health.

Khi thiết kế outbox cho một NoSQL cụ thể, câu hỏi quyết định không phải “database này có outbox hay không?”, mà là: **“Business mutation và ý định phát event có thể được lưu ở đâu để cùng commit nguyên tử, relay có thể phát lại an toàn ra sao, và consumer có thể chấp nhận duplicate mà không nhân đôi kết quả nghiệp vụ hay không?”**

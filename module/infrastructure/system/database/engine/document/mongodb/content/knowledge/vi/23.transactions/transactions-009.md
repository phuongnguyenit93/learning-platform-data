# Phối hợp giao dịch với gửi sự kiện bằng transactional outbox trong MongoDB

## Mục tiêu bài học

Một hệ thống đặt hàng thường phải thực hiện hai việc sau khi khách bấm **Đặt hàng**: cập nhật dữ liệu nghiệp vụ trong MongoDB và thông báo sự kiện `OrderPlaced` tới message broker để các dịch vụ thanh toán, giao hàng và phân tích xử lý tiếp. Nếu viết trực tiếp vào MongoDB rồi gọi broker thành hai thao tác độc lập, một lỗi mạng hoặc crash có thể làm **đơn hàng đã lưu nhưng không có sự kiện**, hoặc **sự kiện đã gửi nhưng đơn hàng không được lưu**. Đây là bài toán **dual-write**.

**Transactional outbox** là mô hình khắc phục bằng cách **ghi thay đổi nghiệp vụ và một bản ghi sự kiện outbox trong cùng một MongoDB transaction**, sau đó một chương trình **relay** riêng đọc bản ghi đã commit và publish tới broker. Relay có thể thử gửi lại khi lỗi, nên consumers phải nhận diện và bỏ qua những lần xử lý trùng.

Bài thuộc **Database Engine Document MongoDB → Giao dịch → Phối hợp giao dịch với gửi sự kiện bằng transactional outbox**. Sau bài, bạn có thể:

1. Phân biệt atomic database transaction với publication tới hệ thống bên ngoài.
2. Chỉ ra những điểm lỗi của hai trình tự “database trước, broker sau” và “broker trước, database sau”.
3. Thiết kế collection `outboxEvents`, event envelope, event ID, schema version, trạng thái và các indexes.
4. Dùng session và transaction để commit business state + outbox atomically.
5. Hiểu vòng đời `PENDING → PROCESSING → PUBLISHED`, atomic claim, lease, retry/backoff và dead-letter/replay.
6. Giải thích **at-least-once publication**, rủi ro duplicate và consumer idempotency/inbox pattern.
7. Sử dụng polling relay hoặc MongoDB change streams, biết giới hạn của resume tokens và oplog retention.
8. Bảo vệ ordering per aggregate bằng version, routing key và chính sách xử lý gap.
9. Viết ví dụ mongosh, Java Sync Driver, callback transaction và relay publication.
10. Đặt write concern, giám sát backlog age, xử lý unknown commit outcome và kiểm thử crash windows.
11. Chọn retention/TTL an toàn cho outbox và cơ chế đối soát dữ liệu.
12. Phân biệt outbox, event sourcing, CDC, distributed transaction và saga.

> **Điểm quan trọng nhất:** MongoDB transaction chỉ làm **business write + outbox write** nguyên tử. Nó **không** tự đưa Kafka/RabbitMQ/HTTP vào cùng transaction. Relay thường publish theo **at-least-once**, nên mọi consumer quan trọng phải **idempotent**.

---

## 1. Dual-write problem: vì sao chỉ commit rồi publish không đủ?

### 1.1. Nghiệp vụ đặt hàng

Giả sử API nhận:

~~~json
{
  "requestId": "REQ-1001",
  "orderId": "ORD-1001",
  "customerId": "CUS-101",
  "productId": "SKU-BOOK-01",
  "quantity": 2
}
~~~

Ứng dụng cần:

- Trừ 2 sản phẩm trong `inventory`.
- Tạo một document `orders`.
- Publish `OrderPlaced` để Payment Service hoặc Shipping Service biết có đơn.

Nếu tất cả hoàn thành thì hệ thống nhất quán; nếu một phần không hoàn thành thì nghiệp vụ có nguy cơ bị kẹt.

### 1.2. Database trước, broker sau

~~~text
API                MongoDB                  Broker
 |                    |                       |
 |--- update stock -->|                       |
 |--- create order -->|                       |
 |<--- commit OK -----|                       |
 |                    |                       |
 |       CRASH        |                       |
 X                    |                       |
 |         Không có publish OrderPlaced       |
~~~

MongoDB đã có đơn và stock đã giảm, nhưng các dịch vụ downstream không biết điều đó. Dù update stock và tạo order đã nằm trong một MongoDB transaction, thao tác gửi broker vẫn nằm **ngoài** transaction.

### 1.3. Broker trước, database sau

~~~text
API                    Broker               MongoDB
 |                        |                     |
 |-- OrderPlaced -------->|                     |
 |<-- broker ACK ---------|                     |
 |                        |                     |
 |--- create order/update stock -------------->|
 |                        |              ABORT / lỗi
 X                        |                     |
~~~

Consumer có thể đã bắt đầu giao hàng dù order chưa được tạo. Gửi broker trước không làm dual-write an toàn hơn.

### 1.4. Không thể sửa bằng cách đổi thứ tự

| Trình tự | Cửa sổ lỗi | Hậu quả |
|---|---|---|
| MongoDB commit → broker publish | Crash sau commit, trước publish | **Mất sự kiện** |
| Broker publish → MongoDB commit | Abort sau publish | **Sự kiện không có business state tương ứng** |
| Broker publish → lưu dấu đã gửi | Broker ack mất hoặc relay crash | **Có thể phát lại** |
| Gửi broker trong callback transaction | Callback bị retry trước commit | **Có thể phát nhiều lần** |
| Đợi broker trả về trong transaction | Broker chậm, network partition | **Giao dịch kéo dài** và vẫn không có distributed atomicity |

Một transaction MongoDB không thể rollback một message đã tới broker. Tương tự, broker transaction không tự rollback MongoDB order.

### 1.5. Tại sao lỗi này nghiêm trọng?

Trong distributed systems, process có thể dừng ở **bất kỳ dòng lệnh nào**, network có thể cắt giữa việc server hoàn thành thao tác và client nhận kết quả. Không được xây bảo đảm tính đúng đắn trên giả định hai thao tác liên tiếp “hầu như luôn thành công”.

---

## 2. Kiến trúc transactional outbox

### 2.1. Luồng xử lý

~~~text
                       Order Service
                             |
                     startTransaction()
                             |
       +---------------------+--------------------+
       |                     |                    |
       v                     v                    v
 update inventory       insert order       insert outbox event
       |                     |                    |
       +---------------------+--------------------+
                             |
                    commitTransaction()
                             |
                    MongoDB transaction
                     /              \
                    /                \
                 COMMIT             ABORT
                    |                  |
                    v                  v
          Order và event cùng     Không business
          tồn tại bền vững        write/outbox commit
                    |
                    v
              Outbox relay
                    |
               publish message
                    |
               broker ACK
                    |
              mark PUBLISHED
                    |
                    v
              Message broker
                    |
                    v
            Idempotent consumer
~~~

### 2.2. Bốn thành phần quan trọng

| Thành phần | Việc thực hiện | Bảo đảm hoặc trách nhiệm |
|---|---|---|
| Business service | Ghi documents nghiệp vụ | Điều kiện business, concurrency, idempotency |
| MongoDB transaction | Ghi business state và outbox cùng session | **Atomic commit/abort** trong MongoDB |
| Relay | Đọc outbox, publish, retry, đánh dấu | Eventual publication khi hạ tầng/retention cho phép |
| Consumer | Nhận events, cập nhật trạng thái riêng | Deduplicate và xử lý business effects an toàn |

### 2.3. Hai mốc thành công khác nhau

Mốc 1 — **Business commit**: order và outbox đã được MongoDB xác nhận commit theo write concern.

Mốc 2 — **Broker publish**: relay đã gửi event và nhận acknowledgment theo durability policy của broker.

Đến mốc 1, không thể nói broker đã có event. Đến mốc 2, cũng chưa thể nói consumer đã xử lý xong.

### 2.4. Tại sao event phải là một document được commit?

Nếu API crash sau commit, outbox event vẫn tồn tại. Relay khởi động lại có thể tìm và gửi. Event không còn chỉ là một object trong RAM của tiến trình đã chết.

### 2.5. Ranh giới nguyên tử chính xác

Trong MongoDB:

~~~text
transaction:
  update inventory
  insert order
  insert outbox
commit
~~~

Cả ba writes là một nhóm. Sau commit, thao tác:

~~~text
broker.publish(...)
~~~

**không** thuộc transaction đó. Đây là giới hạn và đồng thời là điểm làm pattern đơn giản hơn distributed two-phase commit.

---

## 3. Outbox bảo đảm gì, không bảo đảm gì?

### 3.1. Bảo đảm có điều kiện

Nếu transaction commit và outbox được lưu bền theo cấu hình thích hợp:

- Không có order đã commit mà **do code đúng** lại quên ghi event tương ứng.
- Không có event outbox đã commit độc lập trong khi các business writes của transaction bị abort.
- Relay có thể thử publish sau process restart.
- Broker outage không nhất thiết làm API ghi orders thất bại ngay; backlog tồn tại trong outbox.

Các điều kiện: không có TTL xóa PENDING, relay được khôi phục, MongoDB có durability/backup thích hợp, không có bug bỏ qua event và vận hành xử lý lỗi kéo dài.

### 3.2. Không được cam kết sai

Outbox **không tự** đảm bảo:

- Broker nhận ngay khi API commit.
- Message chỉ được publish đúng một lần.
- Mọi consumer xử lý đúng một lần.
- Các events luôn tới theo đúng version khi nhiều relay workers chạy song song.
- External API, email hoặc payment gateway được rollback cùng MongoDB.
- Dữ liệu không thể mất khi mất toàn bộ hệ thống và backup.
- Không cần monitoring/operational replay.

### 3.3. Tính nhất quán cuối cùng

Trong một khoảng thời gian:

~~~text
Orders:       ORD-1001 đã PLACED
Outbox:       OrderPlaced đang PENDING
Broker:       chưa có message
Shipping:     chưa tạo shipment
~~~

Trạng thái này **có thể chấp nhận được** nếu hệ thống có SLA eventual publication. Nó không phải lỗi atomicity; là một giai đoạn của xử lý bất đồng bộ.

---

## 4. Điều kiện MongoDB cho pattern này

### 4.1. Transactions cần đúng deployment

Multi-document transactions được hỗ trợ trên **replica sets** từ MongoDB 4.0 và **sharded clusters** từ MongoDB 4.2, với storage engine và cấu hình tương ứng. Standalone `mongod` không hỗ trợ cùng multi-document transaction API.

Để học một máy có thể dùng single-node replica set. Tuy nhiên, single-node replica set không có high availability nếu máy đó hỏng.

### 4.2. Session là bắt buộc

Các thao tác cần atomicity phải dùng **cùng ClientSession**:

~~~java
inventory.updateOne(session, filter, update);
orders.insertOne(session, orderDoc);
outbox.insertOne(session, eventDoc);
~~~

Nếu quên session ở outbox insert:

~~~java
outbox.insertOne(eventDoc);
~~~

thì thao tác đó có thể chạy ngoài transaction, phá bất biến “order + outbox cùng commit hoặc abort”.

### 4.3. Transaction options

Một cấu hình minh họa:

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: "primary"
});
~~~

- `readConcern:"snapshot"`: snapshot isolation theo semantics MongoDB.
- `writeConcern:"majority"`: mức confirmation của commit.
- `readPreference:"primary"`: phù hợp cho transaction ghi.

Cần kiểm tra default concerns và journaling theo MongoDB version/deployment. `w:"majority"` không có nghĩa tất cả secondary đã áp dụng và không thay thế backup.

### 4.4. Không chờ broker trong MongoDB transaction

Một transaction dài giữ resources/snapshot và có thể tăng write conflict, cache pressure, timeout. MongoDB có giới hạn transaction lifetime, thông thường mặc định khoảng 60 giây trong những cấu hình liên quan. Không mở transaction rồi gọi broker chờ 30 giây vì thao tác đó vẫn **không trở thành atomic với MongoDB**.

### 4.5. Idempotency là yêu cầu xuyên suốt

Có hai nhóm retry:

- Driver retry transaction/commit.
- Client/API gateway gửi lại request vì timeout.

Một transaction đúng chưa đủ bảo vệ khỏi việc **API được gọi lại như một nghiệp vụ mới**. Dùng `requestId` và `eventId` ổn định cùng unique constraints.

---

## 5. Mô hình dữ liệu Orders, Inventory, Outbox

### 5.1. Inventory

~~~javascript
{
  _id: "SKU-BOOK-01",
  title: "MongoDB Handbook",
  available: 10
}
~~~

### 5.2. Order

~~~javascript
{
  _id: "ORD-1001",
  requestId: "REQ-1001",
  customerId: "CUS-101",
  productId: "SKU-BOOK-01",
  quantity: 2,
  status: "PLACED",
  createdAt: ISODate("2026-11-14T01:00:00Z")
}
~~~

`requestId` nhận diện cùng một yêu cầu qua retries. Nếu client gửi cùng requestId với payload khác, API nên trả conflict chứ không âm thầm tạo thêm đơn.

### 5.3. Outbox event

~~~javascript
{
  _id: "EVT-ORD-1001-PLACED-v1",
  eventId: "EVT-ORD-1001-PLACED-v1",

  eventType: "OrderPlaced",
  schemaVersion: 1,

  aggregateType: "Order",
  aggregateId: "ORD-1001",
  aggregateVersion: 1,

  topic: "orders.events",
  partitionKey: "ORD-1001",

  occurredAt: ISODate("2026-11-14T01:00:00Z"),
  createdAt: ISODate("2026-11-14T01:00:00Z"),

  payload: {
    orderId: "ORD-1001",
    customerId: "CUS-101",
    productId: "SKU-BOOK-01",
    quantity: 2,
    status: "PLACED"
  },

  status: "PENDING",
  attempts: 0,
  nextAttemptAt: ISODate("2026-11-14T01:00:00Z")
}
~~~

### 5.4. Giải thích metadata

| Field | Ý nghĩa |
|---|---|
| `_id` | Identity của outbox document |
| `eventId` | ID bền vững để deduplicate publication/processing |
| `eventType` | Domain event, ví dụ OrderPlaced |
| `schemaVersion` | Phiên bản hợp đồng payload |
| `aggregateType` | Loại đối tượng, ví dụ Order |
| `aggregateId` | ID đối tượng nghiệp vụ |
| `aggregateVersion` | Thứ tự logic các thay đổi trên cùng aggregate |
| `topic` | Destination logical topic |
| `partitionKey` | Routing key cho broker partition nếu có |
| `occurredAt` | Thời gian phát sinh sự kiện nghiệp vụ |
| `createdAt` | Thời điểm event được lưu |
| `payload` | Nội dung sự kiện tại thời điểm commit |
| `status` | Trạng thái relay |
| `attempts` | Số lần claim/publish attempted |
| `nextAttemptAt` | Lịch retry |
| `claimToken` | ID quyền sở hữu một lần claim |
| `leaseUntil` | Thời điểm claim hết hiệu lực |
| `publishedAt` | Khi broker đã ack và relay mark xong |

### 5.5. Event nên là bản chụp business fact

Nếu relay chỉ lưu `orderId` rồi đọc order hiện tại khi publish, order có thể đã chuyển từ PLACED sang PAID. Event OrderPlaced lúc đó có nguy cơ chứa trạng thái không đúng thời điểm.

Thiết kế tốt thường ghi payload bất biến tại transaction tạo event hoặc quy định rõ contract cho event dạng notification với lookup.

### 5.6. Hạn chế dữ liệu nhạy cảm

Không copy toàn bộ order document chứa thông tin cá nhân, access tokens hoặc dữ liệu nhạy cảm sang broker. Chọn field có chủ đích, áp dụng schema, authorization, TLS và retention policy.

---

## 6. Chuẩn bị database và indexes

Các lệnh chỉ dùng trên **lab replica set**.

~~~javascript
use outbox_lab

db.inventory.insertOne({
  _id: "SKU-BOOK-01",
  title: "MongoDB Handbook",
  available: 10
});

db.orders.createIndex(
  { requestId: 1 },
  {
    unique: true,
    name: "uk_orders_requestId"
  }
);

db.outboxEvents.createIndex(
  { eventId: 1 },
  {
    unique: true,
    name: "uk_outbox_eventId"
  }
);

db.outboxEvents.createIndex(
  { status: 1, nextAttemptAt: 1, createdAt: 1 },
  { name: "idx_outbox_pending_due" }
);

db.outboxEvents.createIndex(
  { status: 1, leaseUntil: 1, createdAt: 1 },
  { name: "idx_outbox_expired_leases" }
);
~~~

Lưu ý:

- Unique `requestId` giúp ngăn duplicate order do client retry.
- Stable `eventId` giúp consumer dedupe.
- Có thể dùng `_id` làm eventId để giảm một index; cần quyết định theo API.
- Relay tìm events PENDING và lease hết hạn nên cần indexes hỗ trợ query pattern thật.
- Indexes làm tăng chi phí ghi trên outbox; kiểm tra `explain` và write amplification trước khi thêm quá nhiều.

Khi chạy lại lab, insert product cùng `_id` có thể báo duplicate key. Dùng database lab mới hoặc reset có kiểm soát, tuyệt đối không xóa dữ liệu production chỉ để làm ví dụ.

---

## 7. MongoDB transaction: ghi dữ liệu nghiệp vụ cùng sự kiện

### 7.1. Ví dụ mongosh đầy đủ

~~~javascript
const session = db.getMongo().startSession();

const requestId = "REQ-1001";
const orderId = "ORD-1001";
const eventId = "EVT-ORD-1001-PLACED-v1";
const productId = "SKU-BOOK-01";
const customerId = "CUS-101";
const quantity = 2;

let commitAttempted = false;

try {
  const sdb = session.getDatabase("outbox_lab");
  const inventory = sdb.getCollection("inventory");
  const orders = sdb.getCollection("orders");
  const outbox = sdb.getCollection("outboxEvents");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  const stock = inventory.updateOne(
    {
      _id: productId,
      available: { $gte: quantity }
    },
    {
      $inc: { available: -quantity }
    }
  );

  if (stock.matchedCount !== 1) {
    throw new Error("OUT_OF_STOCK_OR_NOT_FOUND");
  }

  const now = new Date();

  orders.insertOne({
    _id: orderId,
    requestId: requestId,
    customerId: customerId,
    productId: productId,
    quantity: quantity,
    status: "PLACED",
    createdAt: now
  });

  outbox.insertOne({
    _id: eventId,
    eventId: eventId,
    eventType: "OrderPlaced",
    schemaVersion: 1,
    aggregateType: "Order",
    aggregateId: orderId,
    aggregateVersion: 1,
    topic: "orders.events",
    partitionKey: orderId,
    occurredAt: now,
    createdAt: now,
    payload: {
      orderId: orderId,
      customerId: customerId,
      productId: productId,
      quantity: quantity,
      status: "PLACED"
    },
    status: "PENDING",
    attempts: 0,
    nextAttemptAt: now
  });

  commitAttempted = true;
  session.commitTransaction();

  print("Commit được xác nhận, event đang chờ relay");
} catch (error) {
  if (!commitAttempted) {
    try {
      session.abortTransaction();
    } catch (abortError) {
      print("Abort cũng lỗi: cần điều tra");
    }
  } else {
    print("Commit outcome chưa chắc chắn, không tự retry body");
  }

  throw error;
} finally {
  session.endSession();
}
~~~

**Quan trọng:** Code ở đây minh họa atomic boundary và dùng đúng session handle. Nó **chưa triển khai retry commit đầy đủ** khi lỗi có `UnknownTransactionCommitResult`. Production nên dùng transaction callback của official driver hoặc hướng dẫn retry commit đúng loại lỗi; không mặc định lỗi mạng ở commit nghĩa là transaction abort.

### 7.2. Vì sao trừ tồn kho có điều kiện?

~~~javascript
{
  _id: "SKU-BOOK-01",
  available: { $gte: 2 }
}
~~~

giúp operation chỉ giảm stock khi còn đủ hai đơn vị. Kiểm tra trước bằng `findOne()` rồi update không điều kiện dễ sinh race khi nhiều requests đồng thời.

### 7.3. Nếu insert outbox lỗi

Giả sử eventId đã tồn tại, outbox insert gặp duplicate key. Transaction cần abort, do đó stock không nên bị giảm và order không được giữ lại từ transaction này.

### 7.4. Nếu commit thành công

Sau commit:

~~~javascript
db.inventory.findOne({ _id: "SKU-BOOK-01" });
db.orders.findOne({ requestId: "REQ-1001" });
db.outboxEvents.findOne({
  eventId: "EVT-ORD-1001-PLACED-v1"
});
~~~

Khi lab bắt đầu với stock 10 và được xử lý một lần:

| Collection | Dự kiến |
|---|---|
| `inventory` | `available: 8` |
| `orders` | Một document ORD-1001 |
| `outboxEvents` | Một event OrderPlaced, `status:"PENDING"` |

**Lúc này chưa thể khẳng định broker đã nhận message.**

### 7.5. Nếu API retry cùng requestId

Transaction mới có thể bị duplicate key từ `orderId` hoặc `requestId`. Vì mọi business writes nằm trong cùng transaction, một lần thử bị abort không nên làm stock trừ thêm.

Tầng API cần tra cứu order đã commit có cùng requestId, so khớp payload gốc và trả kết quả tương ứng. Unique index là nền tảng, nhưng không tự thiết kế toàn bộ idempotency response.

---

## 8. Khi nào nên commit và khi nào abort?

### 8.1. Commit

Gọi `commitTransaction()` khi:

- Điều kiện business hợp lệ.
- Tất cả MongoDB writes cần atomicity đều thành công trong cùng session.
- Outbox event đã được ghi.
- Không còn lỗi cần dừng nghiệp vụ.

### 8.2. Abort

Gọi `abortTransaction()` khi:

- Không đủ hàng.
- Người dùng không được phép đặt hàng.
- Tài khoản/địa chỉ sản phẩm không hợp lệ.
- Insert order/outbox gặp lỗi không thể tiếp tục.
- Nghiệp vụ quyết định hủy trước commit.

### 8.3. Không publish trước commit

Nếu event được publish ngay sau outbox insert nhưng **trước** MongoDB commit, transaction có thể abort, còn event ngoài broker không thể thu hồi. Relay phải chỉ thấy dữ liệu **đã commit**, không tham gia callback transaction để publish.

### 8.4. Abort không hoàn tác side effects bên ngoài

Một email hoặc lệnh gọi thanh toán đã gửi không biến mất khi MongoDB abort. Không có ý nghĩa khi bao bọc external API trong transaction rồi tin nó được rollback.

---

## 9. State machine của relay

Outbox event cần một vòng đời vận hành rõ.

~~~text
            MongoDB transaction COMMIT
                         |
                         v
                      PENDING
                         |
               Worker atomic claim
                         |
                         v
                    PROCESSING
                    /     |      \
                   /      |       \
         broker ack      lỗi      worker crash
              |           |            |
              v           v            |
          PUBLISHED     PENDING         |
                        retry           |
                               lease hết hạn
                                    |
                                    v
                                 reclaim
                                    |
                               PROCESSING

     Nếu lỗi không thể giải quyết tự động:
       DEAD / QUARANTINED + alert + replay plan
~~~

### 9.1. Ý nghĩa các trạng thái

| Status | Ý nghĩa |
|---|---|
| PENDING | Event đã commit, chưa được broker xác nhận |
| PROCESSING | Một relay instance đã claim với lease |
| PUBLISHED | Relay đã có broker ack theo policy và mark thành công |
| DEAD | Tạm dừng retry tự động, cần vận hành kiểm tra/replay |
| CANCELLED | Chỉ dùng khi domain có quy tắc hủy event rõ; không xóa lịch sử committed fact tùy ý |

### 9.2. Các field bổ sung khi claim

~~~javascript
{
  status: "PROCESSING",
  attempts: 3,
  claimToken: "worker-claim-123",
  leaseUntil: ISODate("2026-11-14T02:00:30Z"),
  nextAttemptAt: ISODate("2026-11-14T02:00:00Z")
}
~~~

- `claimToken` là ID riêng cho mỗi lần claim.
- `leaseUntil` cho phép recovery nếu worker chết.
- `attempts` đo số lần đã thử.
- `nextAttemptAt` kiểm soát backoff/retry.

### 9.3. Lease không phải exactly-once lock

Worker A có lease 30 giây nhưng publish chậm 35 giây. Worker B reclaim và gửi cùng event. Worker A vẫn có thể nhận broker ack sau đó. Claim đúng **không loại bỏ duplicate message trên broker**. Consumer vẫn phải idempotent.

---

## 10. Polling relay: atomic claim với findOneAndUpdate

### 10.1. Vì sao cần claim nguyên tử?

Sai:

~~~javascript
const event = db.outboxEvents.findOne({
  status: "PENDING"
});

// Hai workers có thể cùng đọc một event trước khi update.
db.outboxEvents.updateOne(
  { _id: event._id },
  { $set: { status: "PROCESSING" } }
);
~~~

Cả Worker A và B đều có thể đọc event rồi cùng publish.

### 10.2. Atomic claim

~~~javascript
const now = new Date();
const leaseDurationMs = 30000;
const claimToken = new ObjectId().toHexString();

const claimed = db.outboxEvents.findOneAndUpdate(
  {
    nextAttemptAt: { $lte: now },
    $or: [
      { status: "PENDING" },
      {
        status: "PROCESSING",
        leaseUntil: { $lte: now }
      }
    ]
  },
  {
    $set: {
      status: "PROCESSING",
      claimToken: claimToken,
      leaseUntil: new Date(
        now.getTime() + leaseDurationMs
      )
    },
    $inc: { attempts: 1 }
  },
  {
    sort: {
      createdAt: 1,
      _id: 1
    },
    returnDocument: "after"
  }
);

printjson(claimed);
~~~

`findOneAndUpdate` atomically chọn và thay đổi **một document** theo filter. Nếu không có event đủ điều kiện, kết quả là null.

### 10.3. Query ưu tiên PENDING và reclaim

Filter gồm:

- PENDING có `nextAttemptAt <= now`.
- PROCESSING có `leaseUntil <= now` và đến lịch retry phù hợp.

Khi có nhiều workers, đây là nền tảng claim được chia sẻ qua MongoDB, không cần một global mutex đặt trong memory một instance.

### 10.4. Đồng hồ và lease

Các workers có thể có clock skew. Đặt lease duration theo broker publish p99, timeout, GC pauses và network conditions; kiểm soát đồng hồ hệ thống hoặc dùng chiến lược đồng hồ nhất quán. Nếu publish dài hơn lease, có thể gia hạn lease theo claimToken và trạng thái hiện có.

### 10.5. Atomic claim không bảo đảm strict event order

Hai workers có thể claim hai events liên tiếp của cùng aggregate; một worker publish nhanh hơn worker kia. Sort theo `createdAt` trong `findOneAndUpdate` chỉ quyết định chọn candidate tại thời điểm claim, không bảo đảm broker receive order trong mọi concurrency scenario.

Nếu cần strict per-aggregate ordering, phải bổ sung thiết kế riêng.

---

## 11. Publish, broker ack và mark PUBLISHED

### 11.1. Publish phải chờ acknowledgment thật

Ở mức giao diện giả lập:

~~~text
publish(
  topic = event.topic,
  key = event.partitionKey,
  headers = { eventId, eventType, schemaVersion },
  body = event.payload
)

Await broker acknowledgement.
Chỉ sau ACK theo durability policy mới mark PUBLISHED.
~~~

Nếu producer API chỉ ghi vào buffer trong RAM rồi trả về, việc đánh dấu PUBLISHED ngay có thể gây mất message khi producer process crash.

### 11.2. Update có điều kiện sau ack

~~~javascript
const updated = db.outboxEvents.updateOne(
  {
    _id: claimed._id,
    status: "PROCESSING",
    claimToken: claimed.claimToken
  },
  {
    $set: {
      status: "PUBLISHED",
      publishedAt: new Date()
    },
    $unset: {
      claimToken: "",
      leaseUntil: ""
    }
  }
);

printjson(updated);
~~~

Nếu `modifiedCount` = 0, không nên overwrite bất chấp điều kiện. Có thể lease đã hết và worker khác claim. Event có thể đã được broker nhận nên consumer phải deduplicate.

### 11.3. Tại sao không mark trước publish?

~~~text
Mark PUBLISHED
  |
  v
Process crash
  |
  v
Broker không có event
  |
  v
Relay bỏ qua vì đã PUBLISHED
~~~

Khi đó mất event. **Publish → ACK → mark** thường được chọn để ưu tiên at-least-once dù phải chấp nhận duplicate.

### 11.4. Case broker ack mất

Producer timeout không đồng nghĩa broker chưa nhận. Nếu relay retry, message có thể tới hai lần. Giữ cùng eventId qua mọi lần gửi.

---

## 12. Retry, backoff và event DEAD

### 12.1. Khi publish lỗi

Relay nên:

- Phân loại lỗi (network timeout, permission, topic not found, schema invalid...).
- Tính retry delay.
- Đổi về PENDING với `nextAttemptAt` mới nếu còn claim.
- Ghi metric và lỗi được làm sạch khỏi thông tin nhạy cảm.
- Đưa vào DEAD/quarantine khi cần can thiệp.

~~~javascript
const retryDelayMs = 5000;

db.outboxEvents.updateOne(
  {
    _id: claimed._id,
    status: "PROCESSING",
    claimToken: claimed.claimToken
  },
  {
    $set: {
      status: "PENDING",
      nextAttemptAt: new Date(
        Date.now() + retryDelayMs
      ),
      lastErrorCode: "BROKER_TIMEOUT"
    },
    $unset: {
      claimToken: "",
      leaseUntil: ""
    }
  }
);
~~~

### 12.2. Exponential backoff với jitter

Một công thức minh họa:

\[
delay(n)=\min(maxDelay,\ baseDelay \times 2^{n-1})+jitter
\]

Ví dụ 1s, 2s, 4s, 8s... đến maxDelay; thêm jitter để không gây retry storm.

### 12.3. Không retry mãi một event sai schema

Nếu broker từ chối payload không tương thích, retry nhanh liên tục không sửa được lỗi. Nên đánh dấu DEAD hoặc QUARANTINED có alert, sửa schema/destination rồi replay có kiểm soát.

**DEAD không có nghĩa publish thành công.** Đó là trách nhiệm delivery chưa hoàn thành.

### 12.4. Retry có thể làm event tới muộn

Một event version 1 bị retry lâu, version 2 có thể được publish trước nếu nhiều workers không bị chặn. Consumer cần quản lý ordering hoặc relay phải duy trì per-aggregate sequencing.

---

## 13. Ma trận các điểm lỗi phải hiểu

| Điểm lỗi | MongoDB business state | Outbox | Broker | Recovery |
|---|---|---|---|---|
| Lỗi trước commit | Không commit | Không commit | Không phát | Abort, không tạo event giả |
| Commit thành công rồi API crash | Có | PENDING | Chưa chắc có | Relay tìm outbox sau restart |
| Claim rồi worker chết trước publish | Có | PROCESSING | Chưa chắc có | Hết lease, worker khác reclaim |
| Broker ack rồi crash trước mark | Có | PROCESSING/PENDING | **Có thể đã nhận** | Republish, consumer dedupe |
| Mark PUBLISHED rồi worker chết | Có | PUBLISHED | Đã ack | Không cần relay gửi lại |
| Broker down dài hạn | Có | Backlog PENDING | Không nhận thêm | Retry, alert, bảo toàn outbox |
| Consumer đã commit local DB nhưng broker ack mất | Có | PUBLISHED | Broker redeliver | Inbox/dedupe tránh side effect trùng |

### 13.1. Vì sao outbox tăng tính bền vững?

Sau commit, intent publish là một database document, không phụ thuộc process API còn sống.

### 13.2. Vì sao vẫn có duplicate?

Broker publish và MongoDB mark là **hai thao tác không nguyên tử xuyên hệ thống**. Crash giữa chúng tạo điều kiện phát lại. Đây không phải bug có thể xóa bằng vài dòng try/catch.

### 13.3. Tính chất chính là at-least-once

Outbox relay được vận hành đúng có thể đạt eventual at-least-once publication. Exactly-once business effect cần lớp consumer idempotency và định nghĩa rõ phạm vi bảo đảm.

---

## 14. Consumer idempotency và inbox pattern

### 14.1. Một event có thể đến nhiều lần

~~~json
{
  "eventId": "EVT-ORD-1001-PLACED-v1",
  "eventType": "OrderPlaced",
  "aggregateId": "ORD-1001",
  "payload": {
    "orderId": "ORD-1001",
    "productId": "SKU-BOOK-01",
    "quantity": 2
  }
}
~~~

Dù broker nhận hai messages, Shipping Service nên tạo **một shipment** cho cùng order nếu nghiệp vụ chỉ cần một.

### 14.2. Inbox record

~~~javascript
{
  _id: "ShippingService:EVT-ORD-1001-PLACED-v1",
  consumer: "ShippingService",
  eventId: "EVT-ORD-1001-PLACED-v1",
  processedAt: ISODate("2026-11-14T01:05:00Z")
}
~~~

`_id` hoặc unique index trên `consumer,eventId` giúp ngăn cùng consumer ghi nhận một event nhiều lần.

### 14.3. Inbox marker phải cùng transaction với business effect

Consumer xử lý:

~~~text
Local MongoDB transaction:
  insert inbox eventId
  create shipment
commit
  |
  v
ack broker message
~~~

Nếu transaction abort, inbox và shipment đều không được ghi. Nếu transaction commit nhưng broker ack mất, message được redeliver, consumer thấy inbox eventId đã xử lý và bỏ qua tác động nghiệp vụ lần nữa.

### 14.4. Mongosh consumer demo

~~~javascript
const session = db.getMongo().startSession();
let commitAttempted = false;

try {
  const sdb = session.getDatabase("shipping_lab");
  const inbox = sdb.getCollection("processedEvents");
  const shipments = sdb.getCollection("shipments");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  inbox.insertOne({
    _id: "ShippingService:EVT-ORD-1001-PLACED-v1",
    consumer: "ShippingService",
    eventId: "EVT-ORD-1001-PLACED-v1",
    processedAt: new Date()
  });

  shipments.insertOne({
    _id: "SHIP-ORD-1001",
    orderId: "ORD-1001",
    status: "PENDING"
  });

  commitAttempted = true;
  session.commitTransaction();
} catch (error) {
  if (!commitAttempted) {
    try { session.abortTransaction(); } catch (ignored) {}
  }
  throw error;
} finally {
  session.endSession();
}
~~~

Đây là **demo atomic inbox + shipment**, không phải complete broker callback. Production phải phân biệt duplicate đã xử lý, lỗi transient, unknown commit và chỉ **ack message sau khi local commit được xác nhận** hoặc đã đối soát là event trước đó đã xử lý.

### 14.5. Nếu consumer phải gọi HTTP API?

Inbox transaction không rollback được API bên ngoài. Cần idempotency key ở bên được gọi, outbox thứ hai, saga/compensation hoặc quy trình đối soát phù hợp. Không nói “inbox đã bảo đảm exactly once cho mọi email”.

---

## 15. At-least-once, exactly-once và hiệu ứng nghiệp vụ

| Mức | Ý nghĩa | Lưu ý |
|---|---|---|
| At-most-once | Tối đa một lần, có thể mất | Nếu mark trước publish, loss window xuất hiện |
| At-least-once | Sẽ được thử chuyển đi cho đến khi nhận ack/recovery theo policy | Có thể duplicate |
| Exactly-once trong broker | Bảo đảm trong phạm vi protocol/tính năng được chỉ rõ | Không tự bao phủ MongoDB |
| Effectively-once business effect | Dù message lặp, business effect áp dụng một lần | Dedupe + atomic local state/idempotent side effects |

### 15.1. Tại sao một relay không chứng minh exactly-once?

Nếu relay publish thành công và chết trước khi mark, nó sẽ gửi lại event theo cơ chế recovery. Với các hệ thống khác nhau, không thể đồng thời atomically commit broker và update outbox status chỉ bằng MongoDB transaction.

### 15.2. Broker exactly-once không tự bao trùm database

Kafka và một số broker có transaction/exactly-once features trong phạm vi broker hoặc ứng dụng được hỗ trợ. Tính năng đó không tự biến MongoDB business commit và broker publish thành một distributed transaction chung.

### 15.3. Quy tắc thiết kế

- Giữ eventId ổn định.
- Publisher có thể retry.
- Consumer idempotent.
- Local business writes + inbox marker commit atomically nếu có thể.
- External side effects cũng phải có idempotency hoặc compensation.
- Có metrics nhận diện duplicate và đối soát kết quả.

---

## 16. Bảo toàn thứ tự theo aggregate

### 16.1. Tại sao event order quan trọng?

Với một order:

~~~text
OrderPlaced    version 1
OrderPaid      version 2
OrderShipped   version 3
~~~

Nếu consumer nhận OrderShipped trước OrderPlaced, logic có thể thất bại hoặc suy đoán sai trạng thái.

### 16.2. Timestamp không đủ

Hai events có thể có cùng timestamp; đồng hồ giữa producers khác nhau; network delays làm thứ tự nhận không trùng thứ tự business commit. Sử dụng **aggregateVersion** hoặc sequence được cấp theo quy tắc concurrency control.

### 16.3. Version phải gắn với business state

Khi update order version, nên làm atomic với event write để không có event v2 nhưng business state vẫn ở v1. Dùng optimistic concurrency filter trên aggregate version nếu thiết kế cần:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    version: 1
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);
~~~

Thao tác này chỉ là ví dụ conditional update; trong outbox pattern, nó phải nằm **cùng transaction** với insert event OrderPaid version 2.

### 16.4. Partition key

Với broker hỗ trợ ordered partitions, key theo `aggregateId` giúp các sự kiện cùng order tới cùng partition. Nhưng nếu nhiều publishers gửi v2 trước v1, broker không tự sắp xếp lại theo version.

### 16.5. Muốn strict order cần thêm quy tắc

- Serialize publication theo aggregate hoặc giao một aggregate cho một relay lane.
- Không publish version N+1 trước khi version N được xử lý theo policy.
- Bảo vệ state concurrency bằng atomic claim/owner.
- Consumer lưu lastAppliedVersion.
- Phát hiện duplicate (N đã xử lý) và gap (nhận N+2 trước N+1).
- Reconcile dữ liệu khi gap kéo dài hoặc predecessor event DEAD.

Chỉ sort candidates theo `createdAt` trong polling query **không đủ** nếu nhiều relay workers publish song song.

### 16.6. Không phải mọi event cần strict total ordering

Nếu analytics chỉ cộng thống kê idempotent và có thể hội tụ cuối, có thể không cần chi phí strict sequencing. Hãy quy định ordering **per consumer/business invariant**.

---

## 17. Change Streams làm tín hiệu cho relay

MongoDB **change streams** theo dõi những thay đổi đã được commit trên collection/database/deployment hỗ trợ, thường là replica set hoặc sharded cluster.

### 17.1. Theo dõi outbox inserts

~~~javascript
const stream = db.outboxEvents.watch([
  {
    $match: {
      operationType: "insert"
    }
  }
]);

while (stream.hasNext()) {
  const change = stream.next();

  printjson({
    eventId: change.fullDocument.eventId,
    resumeToken: change._id
  });

  // Demo chỉ in.
  // Production phải publish/ack/checkpoint an toàn.
}
~~~

### 17.2. Ưu điểm

- Có thể nhận tín hiệu ngay khi outbox record xuất hiện.
- Giảm polling interval hoặc số empty queries.
- Event mới được relay biết đến sớm.
- Cơ chế resume token giúp tiếp tục stream theo điều kiện lịch sử.

### 17.3. Resume token phải được checkpoint an toàn

Sai:

~~~text
Change stream nhận evt1
  |
  v
Lưu resume token như đã xử lý
  |
  v
Crash trước broker publish
  |
  v
Resume từ token mới => evt1 có thể bị bỏ qua
~~~

Token checkpoint phải phản ánh **tiến độ xử lý đã hoàn tất**. Với xử lý song song, token của event mới hơn không tự chứng minh các events cũ đã được publish.

### 17.4. Change streams phụ thuộc oplog history

Nếu relay offline lâu và resume token không còn dùng được trong lịch sử oplog, có thể không resume như mong đợi. Phải có recovery plan.

### 17.5. Thiết kế vững: change stream + backlog scan

~~~text
Source of truth: outboxEvents collection
Change stream: signal có event mới
Periodic scan: PENDING + expired PROCESSING leases
Broker: publish và ack
State: mark PUBLISHED
~~~

Khi khởi động lại, relay scan outbox để lấy các events đã tồn tại trước khi watch bắt đầu. Nếu stream lỗi, polling recovery vẫn hoạt động.

### 17.6. Cẩn thận watch update events

Nếu watch toàn bộ updates trên outbox, chính các lần chuyển PENDING→PROCESSING→PUBLISHED có thể phát sinh nhiều change events. Filter theo operationType/event field hoặc dùng stream như wake-up signal để không tạo vòng lặp vô hạn.

---

## 18. Polling vs Change Streams

| Tiêu chí | Polling | Change Streams |
|---|---|---|
| Cơ chế | Query state PENDING/lease expired theo chu kỳ | Subscribe change events |
| Khởi động | Dễ hiểu | Cần stream lifecycle/resume |
| Độ trễ | Theo polling interval | Có thể thấp hơn |
| Load khi ít events | Có empty queries | Thường ít polling hơn |
| Recovery event cũ | Scan outbox | Cần scan hoặc checkpoint đáng tin |
| Oplog history | Gián tiếp qua MongoDB replication | Quan trọng cho resume |
| Event duplicate | Có thể | Vẫn có thể |
| Strict ordering broker | Không tự bảo đảm | Không tự bảo đảm khi publish parallel |
| Cần inbox idempotency | Có | Có |

Chọn giải pháp theo SLA, complexity và khả năng vận hành. Change streams không đồng nghĩa “exactly-once”.

---

## 19. Java Sync Driver: transaction tạo order và outbox

Ví dụ này dùng callback transaction của official driver để giảm rủi ro tự viết retry. Giả định đã có các collections và indexes lab, đang kết nối tới replica set.

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.Date;

public class OrderOutboxService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    public OrderOutboxService(MongoClient client) {
        this.client = client;

        MongoDatabase db = client.getDatabase("outbox_lab");
        inventory = db.getCollection("inventory");
        orders = db.getCollection("orders");
        outbox = db.getCollection("outboxEvents");
    }

    public void placeOrder(
            String orderId,
            String requestId,
            String customerId,
            String productId,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity phải dương"
            );
        }

        String eventId = "EVT-" + orderId + "-PLACED-v1";

        TransactionOptions options =
            TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {

                var stock = inventory.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", productId),
                        Filters.gte("available", quantity)
                    ),
                    Updates.inc("available", -quantity)
                );

                if (stock.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "OUT_OF_STOCK_OR_NOT_FOUND"
                    );
                }

                Date now = new Date();

                orders.insertOne(
                    session,
                    new Document("_id", orderId)
                        .append("requestId", requestId)
                        .append("customerId", customerId)
                        .append("productId", productId)
                        .append("quantity", quantity)
                        .append("status", "PLACED")
                        .append("createdAt", now)
                );

                Document payload =
                    new Document("orderId", orderId)
                        .append("customerId", customerId)
                        .append("productId", productId)
                        .append("quantity", quantity)
                        .append("status", "PLACED");

                outbox.insertOne(
                    session,
                    new Document("_id", eventId)
                        .append("eventId", eventId)
                        .append("eventType", "OrderPlaced")
                        .append("schemaVersion", 1)
                        .append("aggregateType", "Order")
                        .append("aggregateId", orderId)
                        .append("aggregateVersion", 1)
                        .append("topic", "orders.events")
                        .append("partitionKey", orderId)
                        .append("occurredAt", now)
                        .append("createdAt", now)
                        .append("payload", payload)
                        .append("status", "PENDING")
                        .append("attempts", 0)
                        .append("nextAttemptAt", now)
                );

                return null;
            }, options);
        }
    }
}
~~~

### 19.1. Tại sao callback phù hợp?

`session.withTransaction` cung cấp cơ chế quản lý start/commit/abort và xử lý một số lỗi tạm thời/commit uncertainty theo contract driver. Callback có thể chạy lại, vì vậy chỉ chứa **MongoDB operations và business checks an toàn khi retry**.

### 19.2. Không gửi external side effects trong callback

Sai:

~~~java
session.withTransaction(() -> {
    orders.insertOne(session, orderDocument);

    // Có thể chạy nhiều lần nếu transaction callback retry.
    emailService.sendConfirmation(orderId);

    outbox.insertOne(session, eventDocument);
    return null;
});
~~~

Email không thuộc transaction, nên có thể gửi ngay cả khi transaction abort hoặc callback được chạy lại.

### 19.3. RequestId cần ổn định

Một HTTP request retry sau timeout nên giữ `requestId` và `orderId` ổn định. Nếu lần trước đã commit và lần sau chạy lại, unique constraint giúp phát hiện duplicate; tầng ứng dụng tra cứu order cũ, so payload rồi trả kết quả idempotent.

### 19.4. Error labels

Không bắt mọi lỗi MongoDB rồi retry vô hạn. Lỗi thiếu hàng hoặc duplicate request payload khác là lỗi nghiệp vụ. Lỗi transaction transient có hướng retry whole transaction; `UnknownTransactionCommitResult` có hướng retry/đối soát commit, không tự thực hiện cùng nghiệp vụ lần nữa với ID mới.

### 19.5. Spring Data MongoDB

Trong Spring, có thể sử dụng `MongoTransactionManager` và `@Transactional` khi cấu hình đúng replica set, version và transaction manager. Nhưng **@Transactional không tự bao phủ call broker** hay hệ thống SQL khác.

Trong service layer, business writes và outbox insert phải cùng session/transaction context. Tránh self-invocation bypass proxy hoặc dùng repository/driver connection không tham gia transaction.

---

## 20. Java Sync Driver: relay claim và publish

### 20.1. Producer interface có ngữ nghĩa ACK

~~~java
public interface EventPublisher {

    /**
     * Chỉ return khi broker đã ACK theo durability policy.
     * Nếu timeout, broker vẫn có thể đã nhận message.
     */
    void publishAndAwaitAck(
        String topic,
        String partitionKey,
        String eventId,
        Document payload
    ) throws Exception;
}
~~~

Không dùng một method chỉ queue message trong RAM rồi coi là publish đã thành công.

### 20.2. Atomic claim

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Updates;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Duration;
import java.util.Date;
import java.util.UUID;

public class OutboxClaims {

    public static Document claimOne(
            MongoCollection<Document> outbox,
            Duration lease) {

        Date now = new Date();
        Date until = new Date(
            now.getTime() + lease.toMillis()
        );

        String token = UUID.randomUUID().toString();

        Bson eligible = Filters.and(
            Filters.lte("nextAttemptAt", now),
            Filters.or(
                Filters.eq("status", "PENDING"),
                Filters.and(
                    Filters.eq("status", "PROCESSING"),
                    Filters.lte("leaseUntil", now)
                )
            )
        );

        Bson update = Updates.combine(
            Updates.set("status", "PROCESSING"),
            Updates.set("claimToken", token),
            Updates.set("leaseUntil", until),
            Updates.inc("attempts", 1)
        );

        FindOneAndUpdateOptions options =
            new FindOneAndUpdateOptions()
                .sort(Sorts.ascending("createdAt", "_id"))
                .returnDocument(ReturnDocument.AFTER);

        return outbox.findOneAndUpdate(
            eligible, update, options
        );
    }
}
~~~

### 20.3. Publish và mark

~~~java
Document event = OutboxClaims.claimOne(
    outbox,
    Duration.ofSeconds(30)
);

if (event != null) {
    publisher.publishAndAwaitAck(
        event.getString("topic"),
        event.getString("partitionKey"),
        event.getString("eventId"),
        event.get("payload", Document.class)
    );

    var result = outbox.updateOne(
        Filters.and(
            Filters.eq("_id", event.get("_id")),
            Filters.eq("status", "PROCESSING"),
            Filters.eq(
                "claimToken",
                event.getString("claimToken")
            )
        ),
        Updates.combine(
            Updates.set("status", "PUBLISHED"),
            Updates.set("publishedAt", new Date()),
            Updates.unset("claimToken"),
            Updates.unset("leaseUntil")
        )
    );

    if (result.getModifiedCount() != 1) {
        // Có thể lease đã hết hoặc worker khác reclaim.
        // Broker có thể đã nhận; consumer phải dedupe.
    }
}
~~~

Đoạn này chỉ minh họa **happy path**. Relay production phải bổ sung try/catch, backoff, retry scheduling, broker timeout, lease renewal nếu cần, metrics và graceful shutdown.

### 20.4. Graceful shutdown

Khi stop service:

1. Ngừng claim events mới.
2. Hoàn tất hoặc giới hạn thời gian chờ các publish đang chạy.
3. Chỉ mark PUBLISHED sau broker ack.
4. Để lease hết hạn nếu chưa thể hoàn tất.
5. Không xóa outbox events chưa publish.
6. Khi restart, quét PENDING và expired leases.

---

## 21. TTL, retention và không làm mất event

### 21.1. Sai: TTL toàn outbox theo createdAt

~~~javascript
db.outboxEvents.createIndex(
  { createdAt: 1 },
  {
    expireAfterSeconds: 3600
  }
);
~~~

Nếu broker down hơn một giờ, event PENDING có thể bị TTL xóa trước khi publish. Như vậy outbox không còn giữ được intent.

### 21.2. Tốt hơn: TTL theo publishedAt

~~~javascript
db.outboxEvents.createIndex(
  { publishedAt: 1 },
  {
    name: "ttl_published_outbox_30d",
    expireAfterSeconds: 2592000
  }
);
~~~

Chỉ những documents có `publishedAt` phù hợp mới chịu TTL trên field này. PENDING và PROCESSING nên **không** có publishedAt.

### 21.3. TTL không phải scheduler real-time

MongoDB TTL monitor xóa documents theo chu kỳ và có thể trễ; `nextAttemptAt` mới là thời điểm relay kiểm tra retry. Không dùng TTL làm cơ chế gửi sự kiện.

### 21.4. Retention của nhiều hệ thống phải tương thích

- Outbox retention.
- Broker retention/replay.
- Consumer inbox/dedup retention.
- Audit/security retention.
- Backup/PITR retention.

Nếu consumer dedup records bị xóa sau một ngày nhưng broker còn replay message cũ sau 30 ngày, có thể phát sinh xử lý trùng khi replay. Policy phải được thiết kế cùng nhau.

### 21.5. Archive và replay

Có thể archive events PUBLISHED sang object storage/audit archive trước TTL. Khi replay, giữ eventId cũ nếu đó là cùng sự kiện, theo dõi replay attempt và giới hạn tốc độ, tránh gửi lại nhiều notifications ngoài ý muốn.

---

## 22. Độ mới, hiệu năng và chi phí

### 22.1. Outbox tăng writes

Một order có thể tạo:

- Update inventory.
- Insert order.
- Insert outbox.
- Update outbox PROCESSING.
- Update outbox PUBLISHED.
- Index maintenance tương ứng.

Nếu có hàng nghìn orders mỗi giây, outbox tăng storage, oplog volume, replication traffic, disk I/O và cache pressure. Cần capacity planning, không coi đây là một tính năng miễn phí.

### 22.2. Polling interval và latency

Polling rất thường xuyên giảm thời gian chờ sự kiện nhưng tạo empty queries. Polling thưa giảm query load nhưng tăng commit-to-publish latency.

Benchmark p50/p95/p99 của:

~~~text
business commit timestamp -> broker acknowledgment timestamp
~~~

Kết hợp pending backlog age để phát hiện tail latency khi traffic tăng.

### 22.3. Index trade-off

Cần index cho PENDING due và PROCESSING expired, nhưng quá nhiều indexes làm tăng chi phí ghi. Dùng `explain("executionStats")` để quan sát keys/docs examined và sort, nhất là khi outbox có hàng triệu documents.

### 22.4. Payload size

BSON document có giới hạn kích thước; không nhét file lớn hoặc binary vào outbox event. Tránh payload chứa toàn bộ personal data. Có thể lưu reference tới data bền vững với các quyền đọc và retention tương thích.

### 22.5. Transactions trên sharded cluster

Nếu business collections và outbox nằm trên nhiều shards, transaction có thể cần phối hợp distributed commit, tăng latency. Thiết kế shard key/access patterns theo workload và atomic boundary, đồng thời cân nhắc unique index rules của sharded collections.

### 22.6. Tenant fairness

Trong SaaS multi-tenant, một tenant có backlog lớn có thể chiếm hết workers. Có thể partition/limit concurrency theo tenant, theo aggregate hoặc theo topic; phải tránh vi phạm ordering requirements.

---

## 23. Monitoring và cảnh báo

| Metric | Câu hỏi cần trả lời |
|---|---|
| PENDING count | Còn bao nhiêu events chưa gửi? |
| Oldest PENDING age | Event lâu nhất đã chờ bao lâu? |
| PROCESSING count | Có bao nhiêu events đang có lease? |
| Expired lease count | Có worker nào chết/kẹt? |
| DEAD count | Có event nào cần can thiệp? |
| Publish successes/failures | Broker publishing có khỏe không? |
| Retry attempts | Có retry storm không? |
| Broker ack latency | Broker phản hồi có chậm? |
| Commit-to-publish p95/p99 | SLA gửi event có đạt? |
| Consumer duplicate count | Có nhiều duplicate delivery không? |
| Consumer processing lag | Downstream có theo kịp không? |
| Transaction abort rate | Producer có write conflict hoặc lỗi business tăng? |

### 23.1. Lệnh mongosh quan sát

~~~javascript
db.outboxEvents.countDocuments({
  status: "PENDING"
});

db.outboxEvents.countDocuments({
  status: "DEAD"
});

db.outboxEvents.find(
  { status: "PENDING" },
  {
    _id: 1,
    eventType: 1,
    attempts: 1,
    createdAt: 1,
    nextAttemptAt: 1
  }
).sort({ createdAt: 1 }).limit(20);
~~~

Đây là quan sát state; không dump toàn payload chứa thông tin nhạy cảm vào logs.

### 23.2. Alert điển hình

- Oldest PENDING age vượt SLA.
- Backlog tăng liên tục.
- DEAD count > 0.
- Broker errors tăng đột ngột.
- Expired leases tăng bất thường.
- Consumer lag vượt ngưỡng.
- Write concern errors hoặc replica set lag.
- TTL hoặc storage capacity sắp quá mức.

Ngưỡng phụ thuộc workload thực tế, không có một giá trị phù hợp mọi deployment.

---

## 24. Runbook khi relay bị lỗi

### Bước 1 — Xác định event nào bị kẹt

Lọc PENDING, PROCESSING hết hạn và DEAD; ghi nhận eventId/aggregateId/attempts/age.

### Bước 2 — Kiểm tra MongoDB

Xác minh replica set primary, replication lag, write concern errors, disk, query/index và TTL policy.

### Bước 3 — Kiểm tra broker

Authentication, TLS, topic/exchange, producer acknowledgment, quotas, partition availability và schema validation.

### Bước 4 — Phân loại lỗi

- Transient network.
- Broker outage.
- Payload sai schema.
- Destination không tồn tại.
- Message quá lớn.
- Sai quyền publish.
- Ordering gap.
- Consumer incompatibility.

### Bước 5 — Khôi phục có kiểm soát

Sửa nguyên nhân, đặt lại trạng thái/`nextAttemptAt` theo runbook, giữ eventId, kiểm tra ordering và giới hạn publish rate khi backlog lớn.

### Bước 6 — Kiểm tra duplicates

Trước replay hàng loạt, xác minh consumer inbox/idempotency. Nếu downstream gọi API bên ngoài, xác định idempotency keys và compensating actions.

### Bước 7 — Đối soát

So business orders đã PLACED với outbox OrderPlaced events, broker events và consumer processing records theo time range/requestId. Reconciliation phát hiện bugs hoặc dữ liệu legacy trước khi pattern được áp dụng.

### Bước 8 — Hậu kiểm

Lưu timeline, nguyên nhân, event IDs đã replay, số duplicate, thời gian backlog phục hồi và cải tiến alerts/tests.

---

## 25. Các phương án liên quan

### 25.1. Publish trực tiếp sau commit

Dễ code nhưng có crash gap. Chỉ phù hợp khi mất event được chấp nhận.

### 25.2. Polling outbox

Dễ khôi phục bằng collection state, không bắt buộc resume tokens, nhưng có polling queries/latency và cần lease/retry.

### 25.3. Outbox với change streams

Có thể giảm latency, nhưng phải quản lý change stream lifecycle, resume token, oplog history và backlog scan. Vẫn cần dedupe.

### 25.4. CDC trên business collections

Change data capture có thể theo dõi order updates trực tiếp; tuy nhiên raw document change không luôn tương đương domain event có ý định nghiệp vụ. Outbox ghi event envelope có chủ đích.

### 25.5. Event sourcing

Event sourcing lưu event log làm nguồn sự thật của aggregate. Transactional outbox thường giữ business state bình thường và thêm event để phát ra ngoài. Có thể phối hợp nhưng không đồng nghĩa.

### 25.6. Saga

Saga phối hợp nhiều bước giữa services và dùng compensation khi cần. Outbox giúp một bước local đã commit có event bền vững để bước tiếp theo được kích hoạt. Hai pattern bổ sung cho nhau.

### 25.7. Distributed two-phase commit

Một hệ thống phân tán có thể dùng transaction coordinators khi các resources/protocol hỗ trợ, nhưng không thể giả định MongoDB và broker tạo được một atomic transaction phân tán chỉ nhờ `@Transactional`.

---

## 26. Lỗi thiết kế thường gặp

**Lỗi 1 — Gửi broker trong transaction callback.** Callback có thể chạy lại; message không được rollback.

**Lỗi 2 — Insert outbox ngoài session.** Nếu business transaction abort, outbox event có thể còn và gửi sai.

**Lỗi 3 — Mark PUBLISHED trước broker ACK.** Crash gây mất sự kiện.

**Lỗi 4 — Không giữ eventId qua retries.** Consumer không thể nhận diện duplicate.

**Lỗi 5 — Tin atomic claim ngăn mọi duplicate.** Lease expiry và unknown broker ack vẫn cho phép duplicate.

**Lỗi 6 — Retry broker timeout với eventId mới.** Làm mất cơ hội dedupe.

**Lỗi 7 — Ghi inbox marker trước business effect nhưng không cùng transaction.** Crash tạo processed marker giả.

**Lỗi 8 — Ack broker trước local consumer commit.** Crash có thể làm mất side effect.

**Lỗi 9 — Chỉ sort createdAt rồi tưởng strict order khi có nhiều workers.** Parallel publishing có thể đảo thứ tự.

**Lỗi 10 — Không có aggregateVersion.** Consumer khó phát hiện event thiếu hoặc out-of-order.

**Lỗi 11 — TTL theo createdAt của mọi documents.** Broker outage dài có thể xóa PENDING.

**Lỗi 12 — Lưu change stream token trước khi publish.** Restart có thể bỏ qua event chưa gửi.

**Lỗi 13 — Chỉ watch inserts, không scan backlog khi startup.** Events có từ trước sẽ không tự xuất hiện.

**Lỗi 14 — Không phân biệt commit unknown với transaction abort.** Client có thể tạo đơn trùng khi retry.

**Lỗi 15 — Retry vô hạn lỗi schema.** Tạo poison message loop và chiếm tài nguyên.

**Lỗi 16 — Xem DEAD là đã hoàn thành.** Thực chất delivery vẫn chưa xong.

**Lỗi 17 — Không có metrics backlog age.** Event có thể kẹt lâu mà không ai phát hiện.

**Lỗi 18 — Lưu full MongoDB document làm message.** Dễ lộ PII, schema coupling và payload quá lớn.

**Lỗi 19 — Outbox PUBLISHED nghĩa là consumer đã xong.** Đây là hai mốc độc lập.

**Lỗi 20 — Dùng one global transaction để publish batch.** Không tạo atomicity broker và khiến MongoDB transaction kéo dài.

---

## 27. Kiểm thử những điểm lỗi thực tế

### 27.1. Abort trước commit

Cố ý throw sau khi giảm inventory nhưng trước outbox insert/commit. Sau abort, stock giữ nguyên, không có order hay outbox event.

### 27.2. Outbox insert bị duplicate key

Tạo eventId trùng. Verify transaction rollback cả update inventory và order insert.

### 27.3. Crash ngay sau MongoDB commit

Tắt relay, commit order, xác nhận outbox PENDING vẫn tồn tại. Bật relay và kiểm tra event được publish.

### 27.4. Crash sau claim

Claim PENDING, kill worker trước broker call. Chờ lease hết, worker khác reclaim và gửi.

### 27.5. Crash sau broker ACK

Broker nhận event nhưng relay chưa mark PUBLISHED. Restart relay, publish lại, kiểm tra consumer chỉ tạo một business effect nhờ inbox.

### 27.6. Two-worker race

Cho hai workers claim một PENDING event đồng thời. Verify chỉ một claim thành công khi lease đang có hiệu lực. Thử lease expiry để thấy duplicate vẫn có thể xảy ra.

### 27.7. Broker outage dài

Dừng broker lâu hơn polling intervals. Events không được TTL xóa; backlog tăng, alert hoạt động, rồi phục hồi khi broker trở lại.

### 27.8. Commit outcome không xác định

Cắt network tại MongoDB commit. API retry với cùng requestId/orderId, verify không trừ stock hai lần.

### 27.9. Consumer redelivery

Consumer commit shipment + inbox rồi crash trước broker ACK. Message redelivery; inbox giúp không tạo shipment thứ hai.

### 27.10. Ordering gap

Phát version 2 trước version 1. Consumer phải block/reconcile hoặc xử lý theo policy đã nêu; không âm thầm đánh dấu version 1 đã có.

### 27.11. Change stream resume failure

Làm stream offline trong staging, thử resume token không còn hợp lệ. Relay phải scan backlog PENDING thay vì bỏ qua events.

### 27.12. TTL retention test

Tạo PENDING và PUBLISHED events đã cũ. Kiểm tra TTL chỉ tác động PUBLISHED có publishedAt phù hợp, còn PENDING không mất.

### 27.13. Schema evolution

Consumer v1 và v2 cùng hoạt động trong rollout. Event schemaVersion 2 thêm field mới; contract tests bảo đảm tương thích hoặc có migration strategy.

---

## 28. Bài tập thực hành

### Bài 1 — Phân tích dual-write

Vẽ timeline cho hai thứ tự database/broker. Chỉ ra điểm crash gây event mất hoặc event giả.

### Bài 2 — Schema & indexes

Tạo inventory, orders, outboxEvents, unique index requestId và eventId, index claim/expiry. Giải thích từng index.

### Bài 3 — Transaction commit

Viết mongosh transaction giảm stock, tạo order và insert outbox OrderPlaced. Verify tất cả cùng commit.

### Bài 4 — Transaction abort

Cố tình đặt số lượng vượt stock. Verify stock giữ nguyên, không có order/outbox event.

### Bài 5 — Duplicate request

Gửi lại request với cùng requestId. Verify không giảm stock hai lần. Tầng API nên trả kết quả nào khi payload trùng hoặc khác?

### Bài 6 — Polling atomic claim

Dùng findOneAndUpdate claim PENDING. Chạy hai workers và giải thích vì sao lease/filter quan trọng.

### Bài 7 — Lease expiry

Worker A claim rồi dừng. Worker B reclaim sau khi lease hết. Phân tích duplicate nếu Worker A chậm thay vì chết.

### Bài 8 — Broker ACK và crash

Cho relay publish thành công nhưng không mark. Sau restart publish lại. Viết consumer idempotent xử lý cùng eventId một lần.

### Bài 9 — Inbox local transaction

Ghi processedEvents và shipments trong cùng MongoDB transaction. Verify khi lỗi giữa hai writes thì cả hai abort.

### Bài 10 — Backoff và DEAD

Đề xuất exponential backoff, jitter, max attempts và quy trình replay cho poison event.

### Bài 11 — Change streams

Watch outbox inserts. Phân tích vì sao phải có startup scan, resume token checkpoint và oplog retention awareness.

### Bài 12 — Ordering

Tạo OrderPlaced v1, OrderPaid v2, OrderShipped v3. Thiết kế aggregateVersion và consumer gap detection.

### Bài 13 — Java producer

Viết OrderOutboxService bằng ClientSession + withTransaction. Không gọi message broker trong callback.

### Bài 14 — Java relay

Viết claimOne, publishAndAwaitAck và mark PUBLISHED theo claimToken. Bổ sung xử lý publish failure/retry.

### Bài 15 — TTL

Tại sao TTL createdAt 1 giờ có thể làm mất events khi broker down 2 giờ? Thiết kế TTL publishedAt.

### Bài 16 — Consumer external API

Nếu consumer gọi hãng vận chuyển, cần idempotency key và reconciliation thế nào khi HTTP response mất?

### Bài 17 — Load test

Giả sử 5.000 orders/giây, mỗi order tạo một outbox event. Thiết kế benchmark MongoDB writes, relay throughput, backlog growth, broker ack và catch-up time.

### Bài 18 — Reconciliation

Viết kế hoạch so orders PLACED với outbox events, broker acknowledgments và consumer processing records theo requestId/time window.

---

## 29. Câu hỏi ôn tập

1. Dual-write là gì?
2. Vì sao MongoDB commit rồi broker publish có thể mất event?
3. Vì sao broker publish rồi MongoDB commit có thể tạo event giả?
4. Outbox event nằm trong transaction nào?
5. Vì sao phải dùng cùng ClientSession?
6. Khi business transaction abort, outbox còn không?
7. Khi business transaction commit, broker đã chắc nhận event chưa?
8. Relay làm gì?
9. PENDING khác PROCESSING và PUBLISHED ở đâu?
10. Vì sao chỉ mark PUBLISHED sau broker ACK?
11. Mark trước publish nguy hiểm như thế nào?
12. Atomic findOneAndUpdate ngăn race nào?
13. ClaimToken và leaseUntil dùng để làm gì?
14. Lease có loại bỏ duplicate broker publication hoàn toàn không?
15. Backoff giúp gì?
16. DEAD event có nghĩa là đã xử lý xong không?
17. At-least-once publication là gì?
18. Vì sao consumer phải idempotent?
19. Inbox pattern là gì?
20. Tại sao consumer inbox và business effect nên cùng transaction?
21. Khi nào consumer ACK broker?
22. Vì sao eventId phải ổn định qua retry?
23. AggregateVersion khác schemaVersion thế nào?
24. Tại sao timestamp không đủ bảo đảm ordering?
25. Khi nào dùng broker partition key theo aggregateId?
26. Change streams giúp relay như thế nào?
27. Vì sao cần backlog scan dù đã có change stream?
28. Resume token lưu quá sớm có thể gây lỗi gì?
29. TTL theo createdAt nguy hiểm thế nào?
30. Vì sao TTL theo publishedAt phù hợp hơn?
31. MongoDB write concern majority có tác dụng gì?
32. UnknownTransactionCommitResult cần xử lý thế nào?
33. Vì sao transaction callback không nên gọi external API?
34. Outbox PUBLISHED có chứng minh consumer đã xử lý không?
35. Sự khác nhau giữa outbox và event sourcing?
36. Outbox hỗ trợ saga như thế nào?
37. Vì sao sharded transaction có thể tốn kém?
38. Metrics nào phát hiện relay kẹt?
39. Khi broker downtime dài, điều gì phải còn bền trong MongoDB?
40. Kiểm thử crash nào chứng minh consumer xử lý duplicate an toàn?

---

## 30. Tổng kết

Transactional outbox là cách phối hợp **business transaction trong MongoDB** với **sự kiện bất đồng bộ**:

~~~text
API
 |
 v
MongoDB transaction:
  update business data
  insert outbox event
 |
 v
commit
 |
 v
relay claim
 |
 v
publish broker + await ACK
 |
 v
mark PUBLISHED
 |
 v
consumer dedupe/inbox
 |
 v
local business commit
 |
 v
broker ACK
~~~

Những nguyên tắc quan trọng:

1. **Business writes và outbox insert phải cùng session và transaction.**
2. **Không publish trực tiếp tới broker trong transaction callback.**
3. **MongoDB commit không đồng nghĩa broker đã nhận event.**
4. **Relay phải publish và đợi broker ACK trước khi mark PUBLISHED.**
5. **Chấp nhận at-least-once và thiết kế consumer idempotent**, không hứa exactly-once end-to-end.
6. **Atomic claim, lease, retry/backoff và crash recovery** giúp relay hoạt động bền vững.
7. **EventId ổn định, aggregateVersion và ordering policy** giúp xử lý duplicate/out-of-order.
8. **Change streams không thay thế trạng thái outbox và recovery scan.**
9. **Retention chỉ được xóa published events theo policy**, không xóa PENDING quá sớm.
10. **Monitoring, replay và reconciliation** là một phần của kiến trúc production.

Một hệ thống transactional outbox đáng tin phải trả lời được: **Sau business commit, sự kiện còn tồn tại bền vững không? Khi relay chết, nó có được gửi lại không? Nếu broker nhận trùng, consumer có xử lý an toàn không? Nếu event bị kẹt lâu, đội vận hành có phát hiện và phục hồi được không?**

## Tài liệu tham khảo

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions and Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/)
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Concern Snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — db.collection.findOneAndUpdate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — BSON Limits](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Microservices Patterns — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Microservices Patterns — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html)

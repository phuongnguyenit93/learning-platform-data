# Giao dịch với dữ liệu dẫn xuất, chỉ mục hoặc sự kiện bên ngoài trong NoSQL

## 1. Một nghiệp vụ, nhiều nơi cần thay đổi

Giả sử người dùng nộp một đơn hàng. Ứng dụng cần:

1. Đổi `orders.status` từ `DRAFT` thành `SUBMITTED` trong MongoDB.
2. Làm cho đơn xuất hiện ở chỉ mục tìm kiếm Elasticsearch.
3. Xóa hoặc cập nhật cache trạng thái đơn trong Redis.
4. Phát sự kiện `OrderSubmitted` cho dịch vụ kho và thông báo.

Nếu viết bốn lệnh nối tiếp:

```text
1. MongoDB update order        OK
2. Elasticsearch index         OK
3. Redis invalidate cache      ERROR
4. Broker publish event        Chưa thực hiện
```

thì đơn trong MongoDB đã được nộp, nhưng cache còn trạng thái cũ và hệ thống kho không nhận sự kiện. Nếu đảo thứ tự, phát event trước khi commit nguồn, consumer có thể hành động dựa trên một trạng thái chưa từng được commit.

Đây là **bài toán giao dịch xuyên ranh giới**. Một cơ sở dữ liệu NoSQL có thể cung cấp tính nguyên tử mạnh **trong một document, một phân vùng hoặc một transaction mà nó hỗ trợ**, nhưng transaction đó không tự bao trùm search engine, cache, event broker và các service độc lập.

Bài học tập trung vào **cách xác định ranh giới nguyên tử**, thiết kế **transactional outbox/CDC**, xử lý **duplicate, ordering, idempotency**, tổ chức **saga/bù trừ**, và xây dựng **reconciliation/rebuild** để những dữ liệu dẫn xuất cuối cùng phù hợp với nguồn.

## 2. Dữ liệu nguồn, dữ liệu dẫn xuất và side effect

Trước khi thiết kế transaction, phân loại những gì nghiệp vụ sẽ thay đổi:

| Nhóm | Ví dụ | Trách nhiệm chính |
|---|---|---|
| **Nguồn có thẩm quyền** (*source of truth*) | Đơn hàng, payment ledger, quyền truy cập | Bảo vệ bất biến và đưa ra quyết định nghiệp vụ |
| **Chỉ mục/read model dẫn xuất** | Search document, dashboard, bảng tra theo status | Tối ưu việc đọc; có thể xây lại nếu nguồn đầy đủ |
| **Cache** | Redis key lưu trạng thái đơn | Tăng tốc đọc; có chính sách TTL/invalidation |
| **Sự kiện** | `OrderSubmitted`, `PaymentConfirmed` | Truyền thông tin thay đổi hoặc ý định cho consumer |
| **Side effect bên ngoài** | Gửi email, giữ kho, charge thẻ, tạo vận đơn | Có thể không đảo ngược nguyên tử bằng rollback |

Sơ đồ:

```text
                       +------------------+
Request -------------->| Order database   | Source of truth
                       +------------------+
                                |
                    Change stream / outbox
                                |
                      +---------+---------+
                      |         |         |
                      v         v         v
                    Search     Cache     Broker
                                            |
                                     +------+------+
                                     v             v
                                  Inventory    Notification
```

**Câu hỏi cốt lõi:** dữ liệu nào **phải đúng ngay tại commit** để nghiệp vụ an toàn; dữ liệu nào **được phép hội tụ sau commit**, với độ trễ và cách sửa được quy định rõ?

Ví dụ, một search index có thể cập nhật chậm vài giây nếu UI chấp nhận. Nhưng việc trừ kho không được chỉ dựa vào search index “còn hàng” khi nguồn kho thực sự đã hết, và việc thu hồi quyền đọc tài liệu không thể để một bản cache cũ tiếp tục tiết lộ nội dung.

## 3. Ranh giới của tính nguyên tử

**Atomicity** nói rằng các thay đổi thuộc **phạm vi được bảo vệ** được commit trọn vẹn hoặc không được commit.

### 3.1. Một document

MongoDB thực hiện update một document nguyên tử:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    tenantId: "T01",
    status: "DRAFT",
    version: 7
  },
  {
    $set: { status: "SUBMITTED" },
    $inc: { version: 1 }
  }
);
```

Nếu `matchedCount=1`, trạng thái và version được thay trong cùng update. Nếu `matchedCount=0`, có thể document đã đổi version, status khác, không tồn tại hoặc không thuộc tenant; **không được bỏ điều kiện để ép ghi**.

Thao tác đó **không** đồng thời gửi message hoặc cập nhật Redis.

### 3.2. Nhiều document trong cùng database

Ở deployment MongoDB hỗ trợ multi-document transaction, ta có thể:

```text
BEGIN TRANSACTION
    orders: status = SUBMITTED, version = 8
    outbox: insert OrderSubmitted v8
COMMIT
```

Sau commit, **cả thay đổi nguồn lẫn event pending cùng tồn tại**. Nếu abort, không được coi một trong hai đã commit riêng lẻ. Đây là nền tảng của transactional outbox.

### 3.3. Nhiều hệ thống độc lập

```text
MongoDB COMMIT     Kafka publish ACK     Redis DEL
        |                  |                 |
        +------------------+-----------------+
               Không có atomic commit chung
```

Một transaction Kafka hoặc một lệnh Redis `MULTI/EXEC` chỉ cung cấp cam kết **trong phạm vi hệ đó**, không tự bao phủ MongoDB. Muốn atomic commit giữa nhiều resource manager cần giao thức phối hợp mà mọi bên cùng hỗ trợ, chẳng hạn 2PC hoặc giải pháp chuyên biệt khác. Các dịch vụ NoSQL, search, Redis, broker, payment API thường **không cung cấp một giao thức giao dịch chung dễ sử dụng**; chi phí khóa/chờ và vận hành cũng đáng kể.

**Đừng gọi một hàm `async` chạy ba lệnh tuần tự là distributed transaction.**

## 4. “Chỉ mục” có nhiều nghĩa: nội bộ hay bên ngoài?

| Đối tượng | Người quản lý | Liên hệ với transaction nguồn |
|---|---|---|
| MongoDB secondary index trên collection | Storage engine MongoDB | Được database duy trì theo cơ chế ghi/commit của chính nó |
| DynamoDB GSI | Dịch vụ DynamoDB | Chỉ mục được đồng bộ theo semantics riêng, có thể trễ so với base table |
| Materialized view của từng hệ | Hệ quản trị tương ứng | Phụ thuộc engine, phiên bản, kiểu view; không mặc nhiên atomic |
| Redis set chứa ID đơn PAID | Mã ứng dụng | Không tự đổi khi MongoDB update |
| Elasticsearch/OpenSearch index | Search engine hoặc projector | Có commit/refresh/replication độc lập |
| Cassandra bảng `orders_by_status` do ứng dụng duy trì | Writer/consumer | Có thể là bản denormalized riêng, cần đồng bộ |
| Dashboard aggregation | Consumer/pipeline | Có thể cập nhật bất đồng bộ |

### Index nội bộ không phải dual-write bên ngoài

```javascript
db.orders.createIndex({ tenantId: 1, status: 1 });

db.orders.updateOne(
  { _id: "ORD-1001", tenantId: "T01" },
  { $set: { status: "SUBMITTED" } }
);
```

Ứng dụng **không cần tự gọi lệnh cập nhật MongoDB index nội bộ**. Database chịu trách nhiệm về cấu trúc đó theo quy tắc của nó.

Ngược lại:

```redis
SADD orders:status:T01:SUBMITTED ORD-1001
```

là một thao tác ở Redis **độc lập**. Nếu MongoDB commit nhưng ứng dụng crash trước `SADD`, danh sách Redis có thể thiếu đơn; nếu Redis commit nhưng MongoDB abort, danh sách có thể chứa đơn không đủ điều kiện.

### Chú ý materialized view và GSI

Không suy luận “do database tự quản lý nên mọi lần đọc index đều thấy bản ghi mới ngay”. DynamoDB GSI có đặc điểm eventual consistency; nhiều materialized view của các hệ khác có quy tắc cập nhật và độ bền riêng. Phải kiểm tra **đúng hệ, đúng phiên bản, đúng loại index/view**.

## 5. Dual-write problem và ma trận sự cố

Code thường gặp:

```javascript
// Pseudocode: không có nguyên tử xuyên MongoDB và broker.
await orders.updateOne(
  { _id: orderId },
  { $set: { status: "SUBMITTED" } }
);
await broker.publish("orders", {
  type: "OrderSubmitted",
  orderId
});
```

| Source write | Broker publish | Kết quả |
|---|---|---|
| Thành công | Thành công | Hai nơi có thể khớp |
| Thành công | Lỗi trước khi gửi | Source đã đổi, event không có |
| Thành công | Broker nhận nhưng ACK thất lạc | Retry có thể phát event trùng |
| Thất bại | Không gửi | Không có event, nhưng cần xử lý lỗi nguồn |
| Broker gửi trước | Source thất bại | Event mô tả một thay đổi không được commit |

**`try/catch` không biến hai commit thành một commit.** Retry cũng không đủ vì đôi khi client không biết thao tác đã thành công hay chưa.

```text
update source -- ACK -- [CRASH] -- publish event -- ACK
                      ^
               Khoảng có thể mất event
```

Hướng khắc phục: **lưu ý định phát event một cách bền vững cùng thay đổi nguồn**, rồi phát về sau bằng relay có khả năng retry.

## 6. Transactional outbox: ghi nguồn và ý định phát cùng commit

**Transactional outbox** gồm:

1. Writer cập nhật aggregate và insert một outbox event trong cùng database transaction.
2. Relay đọc các event đã commit, gửi chúng tới broker/consumer.
3. Consumer áp dụng event, chống duplicate và ordering.

```text
             Cùng transaction trong source database
          +--------------------------------------------+
Request ->| Update Order  +  Insert Outbox Event      |
          +--------------------+-----------------------+
                               |
                            COMMIT
                               |
                               v
                      Outbox PENDING
                               |
                       Poller hoặc CDC
                               |
                               v
                             Broker
                           /    |     \
                          v     v      v
                        Search Cache  Inventory
```

**Invariant cần đảm bảo trong phạm vi transaction nguồn:**

\[
\mathrm{OrderChanged} \Longleftrightarrow \mathrm{OutboxRecorded}
\]

Biểu thức mang nghĩa khái niệm: thay đổi nghiệp vụ và ý định phát sự kiện phải **cùng commit hoặc cùng không commit**. **Việc broker nhận event không thuộc giao dịch nguồn**, nên được hoàn tất bất đồng bộ.

### Outbox giải quyết điều gì?

- Process writer crash **sau commit** nhưng **trước publish**: event pending vẫn nằm trong database.
- Worker relay crash: có thể chạy lại từ outbox.
- Connector ngừng ngắn hạn: có thể bắt kịp các event còn lưu.
- Có thể theo dõi độ tuổi và số event pending.

### Outbox không hứa điều gì?

- Không bảo đảm event đến broker **ngay lập tức**.
- Không bảo đảm publish đúng một lần.
- Không bảo đảm consumer đã áp dụng event trước HTTP response.
- Không tự tạo transaction giữa MongoDB, Kafka, Redis và Elasticsearch.
- Không tự giải quyết event đến sai thứ tự, schema sai hoặc tác động không idempotent.

## 7. Thiết kế cấu trúc sự kiện outbox

Ví dụ:

```json
{
  "_id": "Order:ORD-1001:v8:submitted",
  "eventType": "OrderSubmitted",
  "aggregateType": "Order",
  "aggregateId": "ORD-1001",
  "tenantId": "T01",
  "aggregateVersion": 8,
  "schemaVersion": 1,
  "occurredAt": "2026-11-14T09:00:00Z",
  "payload": {
    "orderId": "ORD-1001",
    "status": "SUBMITTED"
  },
  "deliveryState": "PENDING",
  "attempts": 0
}
```

| Field | Lý do |
|---|---|
| `_id` / `eventId` | Định danh ổn định qua retry/dedup |
| `eventType` | Nêu loại thay đổi nghiệp vụ |
| `aggregateId` | Ordering và phân vùng theo thực thể |
| `aggregateVersion` | Chặn event cũ ghi lùi, phát hiện gap |
| `schemaVersion` | Tương thích producer–consumer |
| `occurredAt` | Theo dõi độ trễ; không thay thế version |
| `tenantId` | Định tuyến, scope quyền |
| `payload` | Thông tin phục vụ consumer |
| `deliveryState/attempts` | Trạng thái relay nếu dùng polling |

**Event ID cần ổn định** trong mọi lần publish lại **cùng một sự kiện**. Nếu một version tạo nhiều sự kiện khác nhau, ID phải chứa loại/sequence hoặc có ID duy nhất riêng; không giả định cứ một version là chỉ một event.

Không đưa bí mật, token hoặc toàn bộ dữ liệu cá nhân vào event khi không cần thiết: broker, DLQ, log và backup có thể giữ payload rất lâu.

## 8. Ví dụ MongoDB + Node.js: transaction ghi order và outbox

Nguồn:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T01",
  status: "DRAFT",
  version: 7,
  totalVnd: 520000
}
```

Ví dụ Node.js driver trên MongoDB deployment **hỗ trợ transaction đa document**:

```javascript
// mongoClient và db đã kết nối; đầu vào đã được validate.
const orders = db.collection("orders");
const outbox = db.collection("outbox");

async function submitOrder({
  mongoClient, orderId, tenantId, expectedVersion
}) {
  const nextVersion = expectedVersion + 1;
  const eventId = "Order:" + orderId + ":v" + nextVersion + ":submitted";
  const session = mongoClient.startSession();

  try {
    await session.withTransaction(async () => {
      const result = await orders.updateOne(
        {
          _id: orderId,
          tenantId: tenantId,  // Phải lấy từ principal đã xác thực.
          status: "DRAFT",
          version: expectedVersion
        },
        {
          $set: { status: "SUBMITTED" },
          $inc: { version: 1 }
        },
        { session }
      );

      if (result.matchedCount !== 1) {
        throw new Error("CONFLICT_OR_NOT_ALLOWED");
      }

      await outbox.insertOne(
        {
          _id: eventId,
          eventType: "OrderSubmitted",
          aggregateType: "Order",
          aggregateId: orderId,
          tenantId: tenantId,
          aggregateVersion: nextVersion,
          schemaVersion: 1,
          occurredAt: new Date(),
          payload: { orderId, status: "SUBMITTED" },
          deliveryState: "PENDING",
          attempts: 0
        },
        { session }
      );
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });

    return { orderId, version: nextVersion, eventId };
  } finally {
    await session.endSession();
  }
}
```

Trong một transaction hợp lệ, nếu insert outbox lỗi thì cả update order phải bị abort. Relay chỉ nhìn thấy những event **đã được commit** theo semantics nguồn.

### Điều kiện để dùng đúng

1. `tenantId` phải được lấy từ **identity/quyền đã xác thực**, không tin tưởng query string/body client.
2. `expectedVersion` và `status` ngăn thay đổi không hợp lệ do concurrency; `matchedCount=0` là conflict hoặc không đủ điều kiện, không phải lý do bỏ filter.
3. `withTransaction` có thể chạy lại callback trong các lỗi transient. Không gọi broker, email hoặc API thanh toán **bên trong callback**.
4. Event ID được tính trước callback để giữ ổn định khi retry.
5. Nếu commit có kết quả mơ hồ do timeout/mất kết nối, cần dùng driver retry contract và kiểm tra **idempotency của request nghiệp vụ**; không tự tạo một event ID mới rồi ghi lại.
6. `w:"majority"` có ý nghĩa theo topology MongoDB. Mức journal/durability qua failover cần hiểu đúng cấu hình thực tế; outbox không tự bảo vệ source write chưa commit bền.
7. Đây là minh họa **DRAFT → SUBMITTED**, chưa thay thế các kiểm tra thanh toán, tồn kho hay quyền sửa từng đơn.

### Idempotency của HTTP request khác idempotency của event

Nếu client timeout sau khi transaction đã commit rồi retry, update có thể trả `matchedCount=0` vì order đã là SUBMITTED. Muốn trả **cùng kết quả cho cùng request**, có thể lưu `requestId`/idempotency ledger trong transaction hoặc truy vấn nguồn để xác minh chính xác yêu cầu trước đã hoàn tất.

Chỉ biết order đang SUBMITTED **không đủ chứng minh chính request hiện tại đã tạo ra trạng thái đó**.

## 9. Relay và ma trận crash: vì sao event có thể trùng

Một relay có thể:

```text
claimPendingOutboxBatch()
for each event:
    publishToBroker(event)
    waitForBrokerAck()
    markOutboxDelivered(event.id)
```

Đây là **pseudocode**, chưa có lease/fencing/retry.

| Crash tại đâu? | Trạng thái thực | Hành vi khi chạy lại |
|---|---|---|
| Trước publish | Event còn pending | Publish sau |
| Broker chưa nhận | Event còn pending | Retry |
| Broker nhận nhưng ACK mất | Relay không biết đã gửi | Retry có thể phát trùng |
| Broker ACK, relay chết trước mark | Event vẫn pending | Publish lại |
| Đã mark delivered | Broker đã xác nhận theo chính sách | Hoàn tất phía relay |

**Mark delivered trước publish** không phải cách khắc phục:

```text
1. Đánh dấu DELIVERED
2. Crash trước khi publish
3. Không có worker nào còn thấy event cần gửi
```

Chấp nhận **at-least-once + idempotent consumer** thường an toàn hơn cố loại duplicate bằng cách có nguy cơ làm mất event.

### Nhiều relay chạy song song

Cần atomic claim/lease để tránh tất cả worker cùng lấy một record:

- `leaseOwner`, `leaseUntil`, `attempts` hoặc cơ chế hàng đợi tương ứng.
- Fencing token/claim version khi đánh dấu hoàn tất.
- Retry với exponential backoff và jitter.
- Giới hạn worker concurrency, cảnh báo backlog.
- Trường hợp worker cũ tiếp tục sau lease hết hạn vẫn có thể publish trùng.

**Lease không phải bằng chứng exactly-once.** Dedup ở consumer vẫn cần event ID ổn định.

## 10. Polling outbox và CDC

### 10.1. Polling

Worker query:

```javascript
db.outbox.createIndex({ deliveryState: 1, occurredAt: 1 });

db.outbox
  .find({ deliveryState: "PENDING" })
  .sort({ occurredAt: 1, _id: 1 })
  .limit(100);
```

Truy vấn chỉ **đọc danh sách ứng viên**, chưa claim atomically. Production phải xử lý nhiều worker, lease, trạng thái in-flight, retry và cleanup.

Ưu điểm: cơ chế đơn giản, thấy được backlog từ bảng outbox. Đánh đổi: poll tạo tải, có độ trễ theo lịch, cần thiết kế ordering.

### 10.2. Change Data Capture

CDC đọc thay đổi đã commit từ log/change stream:

```text
MongoDB commit
     |
     v
Change stream/CDC connector
     |
     v
Broker
     |
     v
Consumers
```

CDC có thể vận chuyển **thay đổi trực tiếp ở source** hoặc **outbox records được tạo cùng transaction nguồn**. Hai cách khác nhau:

- **Source CDC:** thấy việc document thay đổi, nhưng có thể cần suy ra event nghiệp vụ và snapshot trước/sau.
- **Outbox + CDC:** writer đã chủ động ghi `OrderSubmitted` với event ID, version và schema, CDC vận chuyển event đó.

CDC cần **offset/resume token, checkpoint, schema contract, retry, giám sát lag**. Nếu connector ngừng quá lâu, log/oplog dùng để resume có thể bị dọn; cần resnapshot/rebuild. Không coi CDC là một log vĩnh viễn nếu retention không đáp ứng.

### 10.3. Ordering không hoàn toàn tự có

Một broker có thể giữ thứ tự **trong một partition**, nhưng không có nghĩa mọi aggregate trên mọi partition cùng có một total order. Nhiều producer/relay publish cạnh tranh cũng có thể đưa event cùng aggregate vào broker sai thứ tự nếu không bảo vệ.

Chọn partition key theo aggregate (ví dụ `Order#ORD-1001`), đặt **monotonic aggregateVersion** ở nguồn và dùng version guard/gap handling tại consumer.

## 11. At-most-once, at-least-once và exactly-once đúng phạm vi

| Hình thức | Ý nghĩa | Điều có thể xảy ra |
|---|---|---|
| **At-most-once delivery** | Không tự retry một số trường hợp không rõ kết quả | Event có thể mất |
| **At-least-once delivery** | Retry đến khi có bằng chứng được nhận/xử lý | Event có thể đến lặp |
| **Exactly-once processing trong một hệ có transaction hỗ trợ** | Tránh duplicate effect trong ranh giới hệ đó | Không mở rộng tự động qua mọi datastore/API |
| **Exactly-once business effect** | Một yêu cầu nghiệp vụ logic chỉ tạo tác động một lần | Cần idempotency tại nơi tác động có thẩm quyền |

Một broker có thể hỗ trợ transaction để xử lý stream trong **phạm vi broker**. Nhưng consumer thực hiện `updateOne` ở MongoDB và ACK offset trên broker vẫn có hai commit độc lập.

Ví dụ:

```text
Event E tới worker
Worker ghi MongoDB thành công
Worker crash trước broker ACK
Broker giao lại E
```

Nếu worker cộng doanh thu thêm lần nữa, dữ liệu sai dù broker và MongoDB đều hoạt động đúng. Để đạt **một tác động nghiệp vụ**, worker phải nhận ra event đã áp dụng hoặc bảo vệ cập nhật bằng unique request/event key.

## 12. Inbox: dedup bền ở consumer

**Inbox** lưu event ID đã xử lý cho một consumer logic:

```javascript
{
  _id: "revenue-projector:payment-PAY-1001-confirmed",
  consumer: "revenue-projector",
  eventId: "payment-PAY-1001-confirmed",
  processedAt: ISODate("2026-11-14T10:00:00Z")
}
```

Nếu inbox và projection thuộc cùng database hỗ trợ transaction, quy trình:

```text
BEGIN TRANSACTION
    if inbox already contains eventId:
        NO_OP
    else:
        update projection
        insert inbox eventId
COMMIT
ACK broker
```

Sắp xếp các lệnh có thể thay đổi; điều quan trọng là **projection và inbox cùng commit nguyên tử**. Chỉ lưu event ID trong RAM là không đủ: worker restart sẽ quên lịch sử và tạo tác động trùng.

### Không có transaction chung với email/payment provider

```text
1. Email provider gửi thành công
2. Worker crash trước khi ghi inbox
3. Broker giao lại event
4. Email có thể gửi lần hai
```

Với hệ ngoài:

- Dùng idempotency key của provider nếu được hỗ trợ.
- Lưu một job/request ID bền và truy vấn trạng thái thực khi response mơ hồ.
- Với payment, không retry bằng transaction ID mới nếu chưa biết lần trước đã charge hay chưa.
- Nếu provider không hỗ trợ dedup/tra cứu, phải nói rõ giới hạn **không thể bảo đảm exactly-once** và có quy trình xử lý trùng/bù trừ.

## 13. Thứ tự event và source version

Source order có lịch sử:

```text
v7: DRAFT
v8: SUBMITTED
v9: CANCELLED
```

Consumer nhận v9 trước v8. Nếu áp vô điều kiện, projection có thể kết thúc ở `SUBMITTED` dù nguồn đang `CANCELLED`.

### 13.1. Full-state event

Với event mang **toàn bộ trạng thái mà projection cần**:

```text
apply(event):
    atomically:
        if event.aggregateVersion <= projection.sourceVersion:
            return NO_OP
        projection.fields = event.fullState
        projection.sourceVersion = event.aggregateVersion
```

**So sánh version và ghi phải nguyên tử.** Đọc version trong request A, sau đó ghi ở request B không điều kiện tạo race giữa các worker.

```text
Worker A đọc projection v7, định ghi v8
Worker B ghi projection v9
Worker A ghi v8 muộn
=> projection bị lùi
```

MongoDB target có thể dùng transaction/CAS hoặc update có điều kiện; search engine có thể cung cấp cơ chế versioning được hỗ trợ. Phải xét trường hợp insert/upsert trùng và đảm bảo **version nguồn** là monotonic theo aggregate.

### 13.2. Delta event

Event chỉ mô tả:

```json
{
  "eventId": "stock:P10:v12",
  "aggregateVersion": 12,
  "operation": "DECREMENT",
  "quantity": 2
}
```

là **delta**. Nếu consumer đang v10, bỏ qua v11 rồi áp v12 có thể khiến tồn kho sai. Với delta:

- Yêu cầu event tiếp theo có version/sequence liền kề.
- Khi phát hiện gap, buffer/retry/replay từ offset phù hợp.
- Dedup event ID để tránh áp delta hai lần.
- Khi không thể replay đầy đủ, rebuild từ snapshot/ledger có thẩm quyền.

**Không áp dụng logic “version mới hơn thì ghi” của full-state cho mọi delta**.

### 13.3. Timestamp không phải thứ tự đáng tin tuyệt đối

Hai service có đồng hồ lệch hoặc event đến muộn. `occurredAt` có ích để đo lag, nhưng không nên là cơ sở duy nhất để quyết định thay đổi mới nhất. Dùng **sequence/version do nguồn có thẩm quyền cấp** trong một aggregate.

## 14. Delete, tombstone và tránh hồi sinh dữ liệu

Một product bị xóa ở v12. Projector xóa document tìm kiếm, rồi nhận `ProductUpdated v11`:

```text
Delete v12 -> search document biến mất
Late Update v11 -> projector index lại P10
=> dữ liệu bị hồi sinh
```

Một cách bảo vệ là giữ **tombstone logic**:

```json
{
  "_id": "P10",
  "sourceVersion": 12,
  "deleted": true
}
```

Event v11 đến sau sẽ bị từ chối; API/search phải không trả nội dung của `deleted=true`. Tombstone logic ở read model khác với tombstone ở tầng lưu trữ LSM/Cassandra, dù cùng ý tưởng báo dữ liệu đã xóa.

Không xóa tombstone khi vẫn có khả năng replay event cũ mà hệ không còn cách so version. Khi cần xóa thông tin nhạy cảm, có thể tách metadata ID/version không nhạy cảm khỏi payload đã xóa theo chính sách.

**Thu hồi quyền là trường hợp nghiêm ngặt:** nếu ACL vừa thay mà search index trễ, phải xác minh quyền hiện hành ở đường trả nội dung hoặc fail-closed. Không coi “sẽ hội tụ trong vài giây” là lý do cho phép tiếp tục lộ tài liệu.

## 15. Cache invalidation và stale-write race

Cache-aside thường hoạt động:

```text
READ:  Redis miss -> read MongoDB -> populate Redis
WRITE: commit MongoDB -> DEL cache
```

Crash sau commit MongoDB trước `DEL` để lại cache cũ. Outbox/CDC có thể phát ý định invalidate với retry; TTL có thể giới hạn vòng đời cache, nhưng **TTL không thay thế điều kiện đúng ngay khi xử lý quyền hoặc thanh toán**.

### Race khó thấy ngay cả khi đã DEL

```text
T0 Reader A cache miss, đọc source v7
T1 Writer commit v8, invalidate Redis
T2 Reader B đọc source v8, populate cache v8
T3 Reader A populate cache v7 sau cùng
```

Cache cuối là v7, dù thao tác invalidate ở T1 thành công. Để tránh, có thể lưu:

```json
{
  "sourceVersion": 8,
  "status": "SUBMITTED"
}
```

và chỉ ghi cache nếu incoming version **không thấp hơn** version đang có, bằng thao tác CAS nguyên tử của cache. Đọc version rồi gọi `SET` riêng không đủ chống race.

Các lựa chọn khác gồm cache key gắn version, read-through/fallback theo nguồn, ngắn TTL hoặc barrier theo generation; chọn theo business SLA và giới hạn kỹ thuật.

## 16. Projection tổng hợp: trùng event làm sai doanh thu

Giả sử dashboard dùng Redis counter:

```text
revenue:T01:2026-11-14 = 0
```

Consumer nhận `PaymentConfirmed` cho giao dịch `PAY-1001`, số tiền 520.000 VND. Nếu handler đơn thuần:

```redis
INCRBY revenue:T01:2026-11-14 520000
```

thì một event bị broker gửi lại hai lần có thể làm counter tăng thành 1.040.000. `INCRBY` nguyên tử trên Redis nhưng **“một payment chỉ cộng một lần” chưa được bảo vệ**.

Có thể:

- Dùng inbox + counter **trong một transaction target** nếu cùng datastore hỗ trợ.
- Lưu event ID cùng counter trong một script/transaction nguyên tử ở Redis nếu durability đáp ứng.
- Tính lại doanh thu từ **payment ledger** như nguồn có thẩm quyền.
- Dùng event full-state mang tổng đã tính + version nếu nguồn có thể phát một giá trị đáng tin.

Nếu có hoàn tiền, hủy giao dịch, điều chỉnh hoặc currency, công thức doanh thu phải định nghĩa rõ những trạng thái nào được tính. **Không mặc định counter cache là sổ cái**.

### Retention của inbox rất quan trọng

Nếu inbox xóa event ID sau 1 ngày nhưng broker có thể replay sau 7 ngày, event cũ có thể được áp lại. Dedup retention phải khớp replay window hoặc có khả năng đối chiếu ledger/snapshot khác.

## 17. Saga khi có nhiều giao dịch nghiệp vụ độc lập

Đặt hàng thực tế có thể cần:

```text
Create order -> ReserveInventory -> ChargePayment -> ScheduleShipping
```

Mỗi bước có database và transaction riêng. **Saga** tổ chức local transactions và **compensating actions**, chứ không biến toàn bộ quy trình thành một transaction ACID chung.

```text
OrderCreated
      |
      v
ReserveInventory
      |
      +-- FAIL ---> CancelOrder
      |
      v
ChargePayment
      |
      +-- FAIL ---> ReleaseInventory + CancelOrder
      |
      v
ScheduleShipping
      |
      +-- FAIL ---> Refund/ManualReview theo chính sách
      |
      v
OrderConfirmed
```

### Compensation không phải rollback thời gian

Một khoản tiền đã charge có thể được **refund bằng giao dịch mới**, không xóa lịch sử charge. Refund có thể chậm, chịu phí hoặc thất bại. Giữ kho rồi release cũng có thể yêu cầu đối soát nếu việc phân bổ hàng đã tiến xa.

Mỗi bước saga cần:

- ID/request key ổn định.
- Local transaction và outbox để không mất ý định chuyển bước.
- Trạng thái workflow lưu bền và có thể resume sau crash.
- Retry policy và timeout.
- Compensation rõ ràng.
- Chế độ cách ly/xử lý thủ công khi không thể bù trừ tự động.

### Orchestration và choreography

| Mô hình | Cách phối hợp | Đánh đổi |
|---|---|---|
| **Orchestration** | Coordinator bền điều khiển bước tiếp theo | Dễ nhìn trạng thái; coordinator cần HA/recovery |
| **Choreography** | Service phản ứng với event từ nhau | Ít trung tâm; luồng phức tạp khó quan sát |

Nếu chỉ cần cập nhật **search index** thì saga có thể quá nặng; outbox + projector là đủ. Nếu nhiều hệ phải thực hiện các **tác động nghiệp vụ có bù trừ**, saga đáng cân nhắc.

## 18. Chọn nhất quán mạnh hay eventual theo invariant

| Nhu cầu | Eventual consistency phù hợp? | Cơ chế chính |
|---|---|---|
| Trang tìm kiếm đơn mới nộp | Thường có, nếu UI chịu được trễ | Outbox + search projection |
| Cache mô tả sản phẩm | Có giới hạn thời gian | Invalidate, version, TTL |
| Dashboard tổng hợp | Có, nếu có watermark và đối soát | Stream projector + dedup/rebuild |
| Trừ kho tránh bán vượt | Không cho phép sai tại commit | Atomic conditional update/transaction ở nguồn kho |
| Thanh toán không nhân đôi | Không cho tác động trùng | Idempotency/ledger/provider contract |
| Thu hồi quyền xem tài liệu | Không cho stale read làm lộ nội dung | Authoritative ACL/fail-closed |
| Gửi email | Có thể async, nhưng duplicate cần kiểm soát | Durable job/outbox + provider dedup |
| Đồng bộ catalog sang search | Có | Version guard + rebuild |

Một kiến trúc có thể **strong consistency trong aggregate** và **eventual consistency giữa các read model**. Vấn đề không phải chọn một nhãn cho toàn hệ, mà là định nghĩa bất biến theo từng đường quyết định.

## 19. Rebuild index và backfill khi mất event

Connector CDC có thể ngừng rất lâu, resume token hết hiệu lực, search index mất toàn bộ hoặc mapper có lỗi. Phải có cách **tái tạo projection** từ dữ liệu nguồn.

Vấn đề khó: nguồn vẫn có ghi mới khi job snapshot đang quét.

```text
T0 Backfill đọc Order v7
T1 Nguồn cập nhật thành v8
T2 CDC projector ghi Search v8
T3 Backfill ghi Search v7 muộn
=> Search bị lùi
```

Một quy trình khái niệm:

1. Thiết lập checkpoint/resume position CDC phù hợp trước hoặc cùng điểm cắt snapshot.
2. Snapshot/backfill nguồn theo phạm vi có thể kiểm chứng.
3. Áp dữ liệu backfill với **sourceVersion guard**.
4. Replay CDC/outbox từ mốc đã xác định, xử lý trùng theo ID/version.
5. Đợi pipeline bắt kịp **watermark** mục tiêu.
6. Đối soát count, ID, version và trường quan trọng.
7. Chuyển traffic sang projection mới (ví dụ blue/green index + alias) theo cơ chế hệ tìm kiếm hỗ trợ.

Thứ tự snapshot và CDC chính xác phụ thuộc công cụ. Bất biến cần chứng minh là **không bỏ sót thay đổi trong khoảng giao nhau**, và event cũ không thể ghi lùi.

### Không chỉ so tổng số record

Hai index có thể cùng 100.000 document nhưng chứa những ID khác nhau. Cần so:

- ID bị thiếu và ID thừa.
- Document đã xóa nhưng còn hiện.
- Version thấp hơn source.
- Trường được mapping sai.
- Checksum của biểu diễn đã chuẩn hóa khi thích hợp.
- Phạm vi theo tenant, ngày và loại dữ liệu.

Nếu source và search được đọc ở hai thời điểm, chênh lệch có thể chỉ là **đang hội tụ**. Dùng version/watermark và grace period để giảm cảnh báo giả.

## 20. Reconciliation: phát hiện và sửa lệch dữ liệu liên tục

Một job đối soát:

```text
Source (authoritative)
          |
      batch scan
          |
          v
Compare with projection by ID/version
       /               \
      OK             Difference
                       |
               Check CDC watermark
                  /          \
             In flight      Confirmed gap
                |               |
              Recheck       Replay/rebuild
                                |
                                v
                        Verify + audit
```

Finding minh họa:

```json
{
  "ruleId": "ORDER_SEARCH_VERSION_MATCH",
  "entityId": "ORD-1001",
  "sourceVersion": 8,
  "projectionVersion": 6,
  "detectedAt": "2026-11-14T10:00:00Z",
  "state": "PENDING_RECHECK"
}
```

Job nên quét theo ID/tenant có checkpoint, giới hạn tải, đọc lại nguồn trước repair và ghi projection có version guard. Không sử dụng search index đang sai làm căn cứ **ghi đè nguồn có thẩm quyền** nếu chưa xác minh.

### Một điểm về SLA

“99% event hội tụ trong 10 giây” là **SLO giả định**, không phải bảo đảm từ tên công nghệ. Với quyền truy cập, một cửa sổ 10 giây lộ dữ liệu có thể không chấp nhận được; đường đọc phải bảo vệ invariant ngay cả khi projection trễ.

## 21. Schema evolution: producer và consumer không luôn nâng cấp cùng lúc

Sự kiện v1:

```json
{
  "schemaVersion": 1,
  "eventType": "OrderSubmitted",
  "orderId": "ORD-1001",
  "totalVnd": 520000
}
```

Sự kiện v2:

```json
{
  "schemaVersion": 2,
  "eventType": "OrderSubmitted",
  "orderId": "ORD-1001",
  "money": {
    "amountMinor": 520000,
    "currency": "VND"
  }
}
```

Nếu consumer cũ chỉ biết `totalVnd`, bỏ đột ngột field này có thể khiến event bị reject và pipeline kẹt.

Các biện pháp:

- Thêm trường theo hướng **backward compatible** khi có thể.
- Đặt `schemaVersion` và chuyển đổi event theo phiên bản.
- Contract testing giữa producer và consumer.
- Rollout có canary và quan sát deserialize failures.
- Backfill/rebuild khi ý nghĩa dữ liệu thay đổi, không chỉ tên field.

Event không hiểu được cần xử lý bằng DLQ/quarantine hoặc chính sách tương đương. Không được tự ACK bỏ qua một event quan trọng rồi coi pipeline đã hoàn tất.

Metadata như `correlationId`, `causationId`, `occurredAt`, `publishedAt` giúp truy vết, nhưng không thay thế event ID, aggregate version hay authorization.

## 22. Retry, backoff và poison message

**Lỗi tạm thời** thường gồm timeout, throttling, search cluster ngừng ngắn hạn. Dùng exponential backoff có jitter, giới hạn concurrency và cảnh báo khi backlog tăng.

**Lỗi không thể tự hồi phục** gồm payload sai kiểu, event schema không hỗ trợ, mapping index reject hoặc transition nghiệp vụ không hợp lệ. Retry vô hạn những event này có thể chặn cả partition.

Thiết kế cần:

1. Giới hạn số lần thử, lưu nguyên nhân cuối.
2. DLQ/quarantine có quyền truy cập và retention phù hợp.
3. Quy trình sửa dữ liệu hoặc deploy consumer mới.
4. Quy trình replay an toàn sau khi sửa.
5. Giữ ordering/dependency nếu event là delta.

**Không đẩy một delta bị lỗi vào DLQ rồi áp tiếp delta mới mà không xét gap.** Với full-state projection có version, đôi khi có thể rebuild từ snapshot mới hơn; với counter delta, bỏ một event sẽ làm lệch tổng.

## 23. Giám sát hiệu năng và tính đúng

| Metric | Câu hỏi |
|---|---|
| `outbox_pending_count` | Có bao nhiêu event chờ gửi? |
| `outbox_oldest_pending_age_seconds` | Event pending lâu nhất là bao lâu? |
| `outbox_publish_failure_total` | Relay lỗi bao nhiêu? |
| `broker_consumer_lag` | Consumer bị chậm bao nhiêu? |
| `duplicate_event_total` | Bao nhiêu event bị giao lại? |
| `stale_event_rejected_total` | Bao nhiêu update version cũ bị từ chối? |
| `version_gap_detected_total` | Bao nhiêu lần thiếu sequence? |
| `projection_source_version_gap` | Read model đang trễ mấy phiên bản? |
| `reconciliation_mismatch_count` | Có bao nhiêu lệch sau grace period? |
| `dead_letter_queue_size` | Event cần xử lý thủ công? |
| `saga_compensation_failure_total` | Có bù trừ nào thất bại? |
| `rebuild_duration_seconds` | Mất bao lâu để khôi phục projection? |

Không đưa `orderId`, `email` hoặc raw payload vào metric label gây cardinality cao và nguy cơ lộ dữ liệu. Chi tiết điều tra được lưu trong audit/log có quyền truy cập phù hợp.

Một SLO minh họa:

```text
99% OrderSubmitted xuất hiện trên search trong 10 giây
Outbox pending > 60 giây -> alert
Duplicate payment business effect -> không được chấp nhận
Search hỏng hoàn toàn -> phải có quy trình rebuild đã thử nghiệm
ACL revoke -> không được trả nội dung bị cấm trong lúc search trễ
```

## 24. Ma trận sự cố đầu–cuối

| Tình huống | Rủi ro nếu triển khai ngây thơ | Cơ chế |
|---|---|---|
| Writer crash sau source commit trước publish | Mất event | Transactional outbox |
| Broker ACK nhưng relay crash | Publish lại | Event ID + consumer dedup |
| Consumer ghi rồi crash trước ACK broker | Áp effect trùng | Inbox/CAS/idempotency |
| Event v9 đến trước v8 | Ghi lùi projection | AggregateVersion guard |
| Delta bị thiếu v11 | Counter sai | Gap detection + replay |
| Delete v12 rồi update v11 đến trễ | Hồi sinh document | Tombstone + version |
| Cache DEL bị bỏ lỡ | Trạng thái cũ | Outbox invalidation + TTL |
| Reader cũ populate cache sau writer mới | Cache bị ghi lùi | Versioned CAS |
| Search index mất | Không tìm được dữ liệu | Rebuild từ source + CDC |
| Payment provider timeout | Có thể charge rồi nhưng client không biết | Provider idempotency/reconciliation |
| Event schema đổi không tương thích | Consumer kẹt | Schema version, DLQ, replay |
| ACL update đến search chậm | Lộ dữ liệu | Authoritative ACL/fail-closed |
| Source bị sửa sai hợp lệ về transaction | Tất cả projection sao chép dữ liệu sai | Validation, audit, sửa/bù trừ |

Các sự cố này có thể xảy ra **dù từng hệ quản trị riêng lẻ không có bug**. Workflow phải được bảo vệ ở cấp ứng dụng và hợp đồng giữa các hệ.

## 25. Quy trình thiết kế và triển khai

**Bước 1 — Xác định source of truth.** Với mỗi field/aggregate, ai quyết định trạng thái đúng? Search index có thể được rebuild từ đâu?

**Bước 2 — Định nghĩa invariant.** Những gì phải đúng ngay (giữ kho, không charge trùng, không lộ quyền) và những gì eventual được?

**Bước 3 — Xác định ranh giới transaction thực.** Một document, nhiều document cùng database, hay nhiều service?

**Bước 4 — Ghi nguồn và outbox cùng commit.** Dùng ID sự kiện ổn định, monotonic version, tenant và schema contract.

**Bước 5 — Chọn relay.** Polling hoặc CDC; checkpoint, retry, lease/fencing và monitoring.

**Bước 6 — Thiết kế consumer.** Inbox/dedup, version guard, gap handling, tombstone, error policy.

**Bước 7 — Xác định cách rebuild.** Snapshot + CDC với checkpoint không bỏ sót thay đổi, đối soát qua watermark.

**Bước 8 — Xác định retention.** Outbox/inbox, broker topic, DLQ, event payload và backup cần giữ bao lâu?

**Bước 9 — Kiểm thử lỗi.** Gây crash/timeout ở mỗi bước trong môi trường cô lập với dữ liệu giả.

**Bước 10 — Viết runbook.** Từ replay một event tới rebuild toàn read model và xử lý compensation lỗi.

## 26. Bài tập thực hành

### Bài 1 — Phân biệt transaction

Một handler gọi MongoDB update, Redis DEL và Kafka publish tuần tự. Hãy nêu ba thời điểm crash tạo khác biệt giữa các hệ. Vì sao đặt tất cả trong một hàm `try/catch` không làm chúng nguyên tử?

### Bài 2 — Outbox

Cho `ORD-1001` version 7 đổi sang 8 và trạng thái SUBMITTED. Thiết kế document outbox có event ID, aggregate version, schema version và payload. Vì sao event ID phải ổn định khi relay retry?

### Bài 3 — Transaction đa document

Viết pseudocode sử dụng MongoDB transaction để cùng commit update `orders` và insert `outbox`. Điều gì xảy ra nếu insert outbox lỗi? Có nên gửi Kafka message ngay trong callback transaction có thể được retry?

### Bài 4 — ACK bị mất

Broker đã nhận E1 nhưng relay crash trước mark delivered. Khi restart, E1 được gửi lại. Hãy mô tả consumer dùng inbox và unique event ID để không áp nghiệp vụ hai lần.

### Bài 5 — Event đảo thứ tự

Projection nhận v9=CANCELLED rồi v8=SUBMITTED. Với **full-state event**, viết version guard. Vì sao kiểm tra version và ghi trong hai request độc lập vẫn có race?

### Bài 6 — Delta gap

Counter có event v10=-2, v11=+5, v12=-1. Consumer đang ở v10 nhưng nhận v12. Có được áp ngay v12 không? Hãy đề xuất buffer/replay/snapshot rebuild.

### Bài 7 — Cache stale race

Reader A lấy source v7; writer commit v8 và DEL cache; reader B ghi cache v8; reader A ghi v7 cuối cùng. Vì sao invalidation không đủ và cách dùng versioned CAS để chống ghi lùi?

### Bài 8 — Tombstone

Product đã delete ở v12, nhưng projector nhận ProductUpdated v11. Nếu đã xóa cả sourceVersion khỏi projection, điều gì xảy ra? Thiết kế tombstone không chứa nội dung nhạy cảm.

### Bài 9 — Saga

Order giữ kho thành công, charge thành công, nhưng tạo vận đơn thất bại. Bước compensation nào có thể cần? Vì sao refund không phải rollback ACID của charge?

### Bài 10 — Rebuild search

CDC connector ngừng tới khi resume token hết hạn. Mô tả backfill + checkpoint + replay + version guard + watermark để rebuild index mà không bỏ sót đơn mới cập nhật.

### Bài 11 — Quyền truy cập

ACL đã thu hồi quyền vào 10:00, search nhận event lúc 10:00:20. Có được trả tài liệu qua search trong 20 giây đó không? Nêu cách bảo vệ tại đường đọc.

### Bài 12 — Counter và replay

Ledger có 1.000 payment ID khác nhau, dashboard có 1.002 vì event trùng. Hãy nêu cách đối soát, dedup, tính lại aggregate, và lưu ý khi có hoàn tiền.

## 27. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách thay thế |
|---|---|---|
| Gọi source + broker tuần tự rồi coi là transaction | Crash làm mất event | Transactional outbox |
| Publish trong transaction callback | Event có thể phát từ transaction abort/retry | Publish sau commit qua relay |
| Mark outbox delivered trước publish | Mất event khi crash | Publish rồi mark, dedup ở consumer |
| Tin exactly-once của broker bao trùm email/Redis/MongoDB | Duplicate business effect | Idempotency ở nơi tác động |
| Dedup chỉ trong RAM | Restart mất lịch sử | Inbox bền |
| Áp mọi event không kiểm tra version | Ghi lùi | CAS/version guard |
| Bỏ qua delta gap | Bộ đếm sai | Replay/sequence |
| Dọn tombstone quá sớm | Hồi sinh dữ liệu | Version xóa bền |
| Chỉ dùng cache DEL | Stale value do crash/race | Outbox/TTL/CAS |
| Dùng GSI hoặc search như source để chốt thanh toán | Stale business decision | Verify tại authoritative source |
| Không quản lý schemaVersion | Consumer kẹt | Contract tests + migration |
| Không có DLQ hoặc cảnh báo lag | Pipeline hỏng âm thầm | Monitoring + replay runbook |
| Dọn inbox trước cửa sổ replay | Event trùng được áp lại | Retention/dedup phù hợp |
| Rebuild snapshot không ghép CDC checkpoint | Mất thay đổi concurrent | Snapshot + CDC + watermark |
| Saga được hiểu là rollback ACID toàn cục | Compensation có thể thất bại | Workflow bền + idempotency |
| Chỉ test happy path | Lỗi chỉ lộ khi crash | Fault injection + reconciliation |

## 28. Kết luận

**Giao dịch với dữ liệu dẫn xuất, chỉ mục hoặc sự kiện bên ngoài trong NoSQL** trước hết là bài toán xác định **phạm vi của atomicity**:

- **Chỉ mục nội bộ** được database quản lý theo semantics của nó, nhưng **search index, cache, broker và service ngoài** thường không nằm trong transaction nguồn.
- **Transactional outbox** làm thay đổi nguồn và ý định phát event **cùng commit**, để crash không làm mất ý định đồng bộ.
- **At-least-once delivery** thường kéo theo event trùng; **inbox, idempotency và version guard** giúp bảo vệ tác động nghiệp vụ.
- **Ordering, gap handling và tombstone** ngăn projection bị ghi lùi hoặc hồi sinh dữ liệu đã xóa.
- **CDC, checkpoint, rebuild và reconciliation** tạo đường phục hồi khi pipeline bị ngắt, index mất hoặc mapper sai.
- **Saga và compensating actions** dùng cho nhiều local transaction tạo tác động nghiệp vụ; không phải giao dịch ACID chung.
- **Monitoring và kiểm thử crash** chứng minh khả năng hội tụ sau lỗi, thay vì chỉ thấy mọi bước thành công trong lần chạy bình thường.

Một kiến trúc đáng tin cậy không đòi mọi hệ phải cùng commit tức thời. Nó định nghĩa rõ **điều gì phải đúng ngay tại transaction nguồn**, **điều gì được phép nhất quán cuối cùng**, và **cách phát lại, đối soát hoặc bù trừ khi một bước thất bại**.

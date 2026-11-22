# Phân biệt dữ liệu trạng thái, sự kiện nghiệp vụ và bản ghi thay đổi

Một hệ thống thương mại điện tử lưu đơn hàng trong MongoDB. Khi người mua thanh toán thành công, document đơn hàng chuyển sang **PAID**. Nhóm phát triển muốn gửi email, cộng điểm thưởng, cập nhật báo cáo doanh thu và đồng bộ sang search index. Trong buổi thiết kế, ba đề xuất xuất hiện:

- “Đọc document hiện tại có status=PAID là biết khách vừa thanh toán.”
- “Chỉ cần bắt mọi UPDATE trường status rồi phát PaymentCaptured.”
- “Bật CDC là đã có sẵn tất cả sự kiện nghiệp vụ.”

Ba cách hiểu trên đều có thể gây lỗi. **Document hiện tại** cho biết trạng thái đã được ghi, không nhất thiết cho biết đầy đủ lịch sử và nguyên nhân. **CDC (Change Data Capture)** cho biết dữ liệu lưu trữ thay đổi ra sao, không tự xác minh nguyên nhân nghiệp vụ. **Sự kiện nghiệp vụ** biểu thị một sự thật đã được xác nhận theo quy tắc domain, không chỉ là tên mới đặt cho một lệnh UPDATE.

Ví dụ, trường status có thể được đổi sang PAID vì một payment thực sự được capture, vì đối soát sau sự cố, vì migration dữ liệu hoặc vì nhân viên được phép sửa thủ công. Cùng một mutation ở database nhưng ý nghĩa không giống nhau. Ngược lại, một thao tác **OrderPlaced** có thể tạo order, ghi reservation, trừ quota và lưu event trong outbox: **một nghiệp vụ tạo nhiều bản ghi thay đổi**.

Bài học thuộc chương **Sự kiện và CDC**, module **Database No SQL**. Mục tiêu là phân biệt rõ **dữ liệu trạng thái (state data)**, **sự kiện nghiệp vụ (business/domain event)** và **bản ghi thay đổi (change record/CDC record)**; từ đó biết khi nào dùng mỗi loại, cách kết hợp chúng với transactional outbox, event sourcing, CQRS, snapshots, replay, ordering, idempotency, DELETE, schema evolution và các NoSQL engines thực tế.

## 1. Ba câu hỏi khác nhau

| Dữ liệu | Câu hỏi | Ví dụ | Điều không tự chứng minh |
|---|---|---|---|
| **Trạng thái hiện tại** | Đối tượng đang ra sao? | Order 101 hiện PAID, version 7 | Vì sao nó PAID, có bao nhiêu lần thử thanh toán |
| **Sự kiện nghiệp vụ** | Fact có ý nghĩa nào đã xảy ra? | PaymentCaptured, OrderCancelled | Trạng thái đầy đủ của mọi bảng tại thời điểm đọc |
| **Bản ghi CDC** | Nguồn lưu trữ đã ghi mutation nào? | UPDATE orders/101 từ version 6 lên 7 | Mutation có phải kết quả của PaymentCaptured |

Một cách nhớ:

~~~text
STATE:
  order-101.status = PAID

BUSINESS EVENT:
  PaymentCaptured(paymentId=pay-101, amount=500000 VND)

CDC RECORD:
  UPDATE orders/order-101
    status: PENDING_PAYMENT -> PAID
    version: 6 -> 7
~~~

Ba biểu diễn thường liên hệ nhau nhưng **không có quy luật một-một**.

## 2. Một timeline minh họa

~~~text
10:00:00  Khách tạo checkout intent.
10:00:01  Order service commit order-101.
10:02:00  Payment provider báo kết quả thành công.
10:02:01  Payment service xác minh và commit.
10:02:02  Change stream chuyển các writes đã commit.
10:02:03  Relay publish domain event từ outbox.
10:02:04  Search, loyalty và analytics cập nhật.
~~~

Sơ đồ một lựa chọn kiến trúc:

~~~mermaid
flowchart TD
    P["Payment đã được xác minh"] --> H["Business handler"]
    H --> TX["Atomic commit nghiệp vụ"]
    TX --> S["Order/Payment state"]
    TX --> O["Outbox: PaymentCaptured"]
    S --> C1["CDC state changes"]
    O --> C2["CDC outbox changes"]
    C1 --> R["Search / state projection"]
    C2 --> B["Broker: domain event"]
    B --> L["Loyalty / notifications / analytics"]
~~~

Khi đó:

- Order document phục vụ truy vấn **trạng thái hiện hành**.
- PaymentCaptured event phục vụ phản ứng với **mốc thanh toán được công nhận**.
- CDC record phục vụ **phát hiện/vận chuyển sự thay đổi** theo giao thức nguồn.

Không phải mọi hệ phải có đúng kiến trúc này; đây là ví dụ giúp phân biệt vai trò.

## 3. Dữ liệu trạng thái là gì?

State document mô tả đối tượng tại một mốc:

~~~json
{
  "_id": "order-101",
  "tenantId": "shop-a",
  "customerId": "customer-9",
  "status": "PAID",
  "totalAmount": 500000,
  "paidAmount": 500000,
  "currency": "VND",
  "version": 7,
  "updatedAt": "2026-11-14T10:02:01Z"
}
~~~

Nó trả lời được: order nào, thuộc tenant nào, tổng tiền, trạng thái và phiên bản hiện tại.

Nó **không nhất thiết** trả lời được:

- Đã có bao nhiêu lần thanh toán thất bại trước đó?
- Khi nào payment được authorize, capture và settle?
- Có từng refund một phần rồi được điều chỉnh?
- Ai đã thay đổi trạng thái: khách, admin, reconciliation worker?
- Đã có email nào được gửi?

Nếu các thông tin đó được nhúng vào document thì phải do **schema cố ý lưu**, không phải do đặc tính mặc định của state.

## 4. State giống một bức ảnh hiện tại hơn là toàn bộ câu chuyện

Một order có lịch sử:

~~~text
OrderCreated -> PaymentAuthorized -> PaymentCaptured
             -> OrderPacked -> OrderShipped
~~~

Document cuối có thể chỉ là:

~~~json
{
  "_id": "order-101",
  "status": "SHIPPED",
  "version": 5
}
~~~

Trạng thái hiện tại là kết quả của những bước trước, nhưng **không thể suy ngược duy nhất lịch sử** chỉ từ kết quả.

Trong mô hình tổng quát:

\[
S_n = \operatorname{apply}(S_{n-1}, \Delta_n)
\]

Trong hệ event-sourced:

\[
S_n = \operatorname{fold}(S_0, E_1,\ldots,E_n)
\]

Nhưng một hệ CRUD chỉ lưu state **có thể không còn** các sự kiện \(E_1,\ldots,E_n\). Vì vậy không thể “replay quá khứ” từ current document nếu chưa thiết kế history riêng.

## 5. State có thể nằm trong một hoặc nhiều documents

Ví dụ:

**Nhúng trong một document:**

~~~json
{
  "_id": "order-101",
  "status": "PAID",
  "payment": {
    "paymentId": "pay-101",
    "status": "CAPTURED"
  }
}
~~~

**Tách collection:**

~~~text
orders/order-101: status=PAID
payments/pay-101: status=CAPTURED
ledger/txn-900: amount=500000
~~~

Một fact **PaymentCaptured** có thể cần thay đổi một hoặc nhiều state records tùy consistency boundary và data model.

Do đó:

~~~text
Số state mutations != số business events
Số CDC records != số business operations
~~~

Không lấy số record changes làm số đơn hàng hay số giao dịch tài chính đã xảy ra.

## 6. Sự kiện nghiệp vụ là một fact có ý nghĩa domain

Ví dụ một event:

~~~json
{
  "eventId": "evt-payment-900",
  "eventType": "PaymentCaptured",
  "eventVersion": 1,
  "aggregateType": "Payment",
  "aggregateId": "pay-101",
  "tenantId": "shop-a",
  "occurredAt": "2026-11-14T10:02:00Z",
  "recordedAt": "2026-11-14T10:02:01Z",
  "payload": {
    "orderId": "order-101",
    "amount": 500000,
    "currency": "VND"
  }
}
~~~

Một event hữu ích trả lời:

- **Điều gì đã xảy ra?** Thanh toán đã được capture.
- **Với đối tượng nào?** Payment pay-101, Order order-101.
- **Theo quy tắc nào?** Producer đã xác minh một capture được công nhận.
- **Phạm vi nào?** Tenant shop-a.
- **Có thể nhận ra retry không?** eventId ổn định.

**Tên ở thì quá khứ không đủ chứng minh event là sự thật.** Producer phải định nghĩa điểm commit và các bất biến nghiệp vụ trước khi phát.

## 7. Command khác event

~~~text
Command:
  CapturePayment(order-101, amount=500000)

Outcome:
  SUCCESS hoặc DECLINED hoặc UNKNOWN

Business event sau khi được công nhận:
  PaymentCaptured(paymentId=pay-101, amount=500000)
~~~

| Khái niệm | Vai trò | Có thể bị từ chối? |
|---|---|---|
| **Command** | Yêu cầu thực hiện hành động | Có |
| **Business event** | Fact đã được producer công nhận | Consumer có thể lỗi khi xử lý, nhưng fact không phải một yêu cầu |
| **State** | Giá trị hiện hành đã lưu | Có thể đổi ở bước tiếp theo |
| **CDC record** | Biểu diễn mutation từ nguồn lưu trữ | Được relay lại/đọc lại, không tự tạo ý nghĩa nghiệp vụ |

Không phát PaymentCaptured chỉ vì đã nhận CapturePayment: provider có thể từ chối, chưa hoàn tất hoặc timeout có kết quả không rõ.

Nếu cần báo thất bại, có thể định nghĩa PaymentCaptureDeclined hoặc một outcome record theo domain, không biến **lỗi network tạm thời** thành một fact thất bại cuối cùng không được chứng minh.

## 8. Domain event khác technical audit record

Một audit record:

~~~json
{
  "actorId": "admin-4",
  "action": "UPDATE_DOCUMENT",
  "resourceId": "order-101",
  "field": "status",
  "before": "PENDING_PAYMENT",
  "after": "PAID",
  "requestId": "req-900",
  "recordedAt": "2026-11-14T10:02:01Z"
}
~~~

Audit giúp trả lời: ai/công cụ nào đã sửa field nào, qua request nào, khi nào.

Nhưng UPDATE_DOCUMENT không đồng nghĩa PaymentCaptured. Người quản trị có thể sửa sau reconciliation hoặc migration.

Có thể cần ba nguồn:

~~~text
Business event history -> timeline nghiệp vụ.
Technical audit logs   -> thao tác, truy cập, thay đổi cấu hình.
CDC change stream      -> mutation của storage.
~~~

Mỗi nguồn có schema, retention, quyền truy cập và độ tin cậy khác nhau.

## 9. Business event không nhất thiết mang toàn bộ state

**Event notification:**

~~~json
{
  "eventId": "evt-1",
  "eventType": "OrderPaid",
  "orderId": "order-101"
}
~~~

Consumer cần hỏi lại source để lấy dữ liệu khác.

**Event-carried state transfer:**

~~~json
{
  "eventId": "evt-1",
  "eventType": "OrderPaid",
  "orderId": "order-101",
  "orderVersion": 7,
  "amount": 500000,
  "currency": "VND"
}
~~~

Loại thứ hai giảm source lookups nhưng:

- Tăng payload và phụ thuộc schema producer.
- Có nguy cơ mang PII sang những nơi không cần.
- Một số fields mang state tạm thời, không phải fact bất biến.
- Cần version/compatibility khi event được lưu lâu.

Nên chứa **những fields được contract bảo đảm**, không mặc định copy toàn bộ document.

## 10. CDC thực chất là gì?

**Change Data Capture** giúp theo dõi những thay đổi được ghi nhận tại nguồn:

- INSERT/CREATE.
- UPDATE/PATCH/REPLACE.
- DELETE.
- Một số metadata liên quan transactions và log positions tùy engine.

CDC có thể dựa vào transaction log, oplog, write-ahead log, stream chính thức của dịch vụ hoặc connector; một số hệ ứng dụng dùng polling như một cơ chế thay thế với những giới hạn riêng.

CDC phục vụ:

- Tạo read model và search index.
- Đồng bộ state sang warehouse/analytics.
- Cache invalidation.
- Cập nhật projections.
- Chuyển tải outbox records.
- Data replication theo contract.

**CDC ghi những gì storage làm, không tự suy mọi nguyên nhân business.**

## 11. Một CDC envelope trông ra sao?

Ví dụ mô hình hóa, **không phải schema chính xác của mọi connector**:

~~~json
{
  "source": {
    "database": "commerce",
    "collection": "orders"
  },
  "operation": "UPDATE",
  "documentKey": {
    "_id": "order-101"
  },
  "before": {
    "status": "PENDING_PAYMENT",
    "version": 6
  },
  "after": {
    "status": "PAID",
    "version": 7
  },
  "sourcePosition": "opaque-position-9001",
  "capturedAt": "2026-11-14T10:02:02Z"
}
~~~

Các trường có thể có hoặc không:

- Before image.
- After image.
- Changed fields.
- Transaction identifiers.
- Commit timestamp.
- Opaque resume token/log position.
- Connector metadata.

Không thiết kế consumer phụ thuộc **before** nếu nguồn/option chỉ cung cấp **new image**.

## 12. CDC không biết nguyên nhân nghiệp vụ

Ví dụ lệnh:

~~~javascript
db.orders.updateOne(
  { _id: "order-101" },
  { $set: { status: "PAID" } }
);
~~~

Một change record có thể biết trường status đổi thành PAID, nhưng không tự biết:

- Đã capture payment nào?
- Amount/currency nào?
- Có retry payment?
- Có phải reconciliation sau lỗi?
- Có phải operator sửa thủ công?
- Có phải migration đổi status?

Không tự phát PaymentCaptured từ điều kiện **status=PAID** trừ khi domain contract thực sự bảo đảm **mọi cách ghi status ấy** đều tương ứng fact đó, đồng thời chống duplicate/corrections.

## 13. Một nghiệp vụ tạo nhiều CDC records

Một OrderPlaced có thể thực hiện:

~~~text
Atomic unit:
  INSERT orders/order-101
  UPDATE inventory/sku-42
  INSERT reservations/res-900
  INSERT outbox/evt-order-101
COMMIT
~~~

CDC có thể thấy:

~~~text
1. INSERT orders/order-101
2. UPDATE inventory/sku-42
3. INSERT reservations/res-900
4. INSERT outbox/evt-order-101
~~~

**Bốn storage mutations không có nghĩa bốn orders được đặt**. Một fact nghiệp vụ có thể ghi nhiều records, và số events nghiệp vụ được thiết kế không bằng số storage writes.

Nếu consumer đếm CDC records làm số orders, dữ liệu phân tích sẽ sai.

## 14. Một CDC record có thể phản ánh nhiều facts hoặc không có fact

Ví dụ update cùng lúc:

~~~json
{
  "_id": "order-101",
  "status": "PAID",
  "couponRedeemed": true,
  "loyaltyEligible": true
}
~~~

Ứng dụng có thể cần phát:

~~~text
PaymentCaptured
CouponRedeemed
OrderEligibleForLoyalty
~~~

Hoặc một business event gộp theo domain.

Ngược lại:

~~~text
UPDATE lastViewedAt
UPDATE denormalizedSearchText
UPDATE schemaVersion
UPDATE retryCounter
~~~

có thể là thao tác kỹ thuật, không cần domain event mới.

**Granularity của domain event phải do domain quyết định**, không do số field trong UPDATE.

## 15. Đừng đặt tên mọi event là OrderUpdated

Tên OrderUpdated có thể bao gồm:

~~~text
Shipping address changed.
Payment captured.
Order cancelled.
Order packed.
Internal note changed.
Technical migration.
~~~

Consumers khó biết hành vi đúng khi chỉ nhìn OrderUpdated.

Tên phản ánh business fact rõ hơn:

~~~text
OrderPlaced
OrderShippingAddressChanged
PaymentCaptured
OrderCancelled
OrderShipmentDispatched
~~~

Nhưng không nhất thiết tách từng field thành một loại event. Cần chọn **ngữ nghĩa, ranh giới aggregate và mức hạt ổn định**, không chỉ tăng số event types.

## 16. Mối quan hệ giữa state, outbox và CDC

~~~mermaid
flowchart TD
    CMD["Business command"] --> V["Validate domain invariants"]
    V --> TX["Transaction / recovery protocol"]
    TX --> STATE["Persist authoritative state"]
    TX --> EVENT["Persist domain event in outbox"]
    STATE --> CDC1["CDC state records"]
    EVENT --> CDC2["CDC outbox records"]
    CDC1 --> SEARCH["Search / state projections"]
    CDC2 --> RELAY["Broker publisher"]
    RELAY --> CONSUMER["Domain event consumers"]
~~~

CDC trên **business collection** phù hợp khi consumer muốn duy trì bản sao trạng thái.

CDC trên **outbox collection** phù hợp khi consumer cần một sự kiện nghiệp vụ mà producer đã **chủ động định nghĩa, xác minh và ghi**.

Outbox record tồn tại trong database, vì vậy CDC vẫn thấy thao tác **INSERT outbox record**. Nhưng **nội dung event** đến từ domain, không do CDC tự tạo ra.

## 17. Transactional outbox giải bài toán gì?

Một code flow không an toàn:

~~~text
1. Commit order status=PAID vào MongoDB.
2. Publish OrderPaid tới broker.
~~~

Nếu crash sau 1 trước 2, state PAID đã tồn tại nhưng không có event.

Đảo thứ tự cũng sai:

~~~text
1. Publish OrderPaid.
2. DB transaction rollback.
~~~

Consumer nhận fact của order không được công nhận.

**Transactional outbox** lưu state mutation và event intent trong **cùng atomic unit** của source:

~~~text
BEGIN ATOMIC UNIT
  UPDATE orders/order-101 -> PAID
  INSERT outbox/evt-900 -> OrderPaid
COMMIT

Relay:
  publish evt-900
  retry khi ACK mất
~~~

Phạm vi transaction phải được engine hỗ trợ. Nếu state và outbox ở hai nơi không có atomicity chung, phải có protocol recovery tương đương.

## 18. Ví dụ MongoDB transaction ở mức ý tưởng

~~~javascript
const session = client.startSession();

try {
  await session.withTransaction(async () => {
    const result = await db.collection("orders").updateOne(
      {
        _id: "order-101",
        tenantId: "shop-a",
        status: "PENDING_PAYMENT",
        version: 6
      },
      {
        $set: { status: "PAID" },
        $inc: { version: 1 }
      },
      { session }
    );

    if (result.matchedCount !== 1) {
      throw new Error("STATE_TRANSITION_NOT_APPLIED");
    }

    await db.collection("outbox").insertOne(
      {
        _id: "evt-order-paid-900",
        tenantId: "shop-a",
        aggregateId: "order-101",
        aggregateVersion: 7,
        eventType: "OrderPaid",
        eventVersion: 1,
        payload: { orderId: "order-101" }
      },
      { session }
    );
  });
} finally {
  await session.endSession();
}
~~~

Đây là **ví dụ logic, chưa phải handler production**. Cần:

- Transaction-capable deployment và driver/configuration đúng.
- Kiểm authentication/authorization và fact payment đã được xác minh.
- Stable event ID, idempotency key/unique constraints.
- Xử lý retry commit khi outcome UNKNOWN.
- Không gọi email/payment provider trong callback có thể được driver retry.
- Xác nhận sharding/transaction scope và write concern theo yêu cầu.

Chỉ khi order transition thực sự được áp dụng mới nên ghi OrderPaid event; nếu conditional update không match thì phải xử lý business outcome, không commit event giả.

## 19. So sánh CDC trực tiếp và outbox CDC

| Yếu tố | CDC business collection | CDC outbox |
|---|---|---|
| Source | Orders/Payments documents | Documents chứa domain event |
| Nội dung tự nhiên | Mutation/field change | Event payload đã định nghĩa |
| Thích hợp | State replication, search, cache invalidation | Business reactions, domain integrations |
| Coupling schema DB | Thường cao hơn | Có thể tách contract khỏi schema |
| DELETE | Thường là DELETE/soft-delete change | Event nghiệp vụ với ý nghĩa được khai báo |
| Audit business | Không tự đủ | Có thể hữu ích nếu được thiết kế theo audit needs |
| Retry | Cần checkpoint/idempotency | Cần checkpoint/idempotency |
| Replay | Phụ thuộc log retention/snapshot | Phụ thuộc outbox/broker retention và event history |

**Outbox không làm CDC trở thành exactly-once delivery**. Nó giúp không mất ý định phát event khi business commit; relay và consumer vẫn phải chịu được duplicate delivery.

## 20. Event sourcing khác CDC

Trong **state-centric CRUD**:

~~~text
Authoritative source:
  orders/order-101 status=PAID

Event:
  optional history/outbox.
~~~

Trong **event sourcing**:

~~~text
Authoritative event stream:
  seq1 OrderCreated
  seq2 PaymentAuthorized
  seq3 PaymentCaptured
  seq4 OrderConfirmed

State document:
  projection của events.
~~~

State được dựng:

\[
S_n=\operatorname{fold}(S_0,E_1,\ldots,E_n)
\]

Ở event sourcing, **business event log là nguồn có thẩm quyền**, còn current state là projection/snapshot.

**Bật CDC trên CRUD database không tự tạo event sourcing**. CDC ghi storage mutations, vốn có thể không chứa đủ domain facts và semantics để dựng lại lịch sử chính xác.

## 21. Event sourcing không phải lưu mọi JSON patch

Hai chuỗi:

~~~text
Business:
  PaymentAuthorized
  PaymentCaptured
  RefundIssued
~~~

và:

~~~text
Storage:
  set payment.status=AUTHORIZED
  set payment.status=CAPTURED
  set payment.refundedAmount=100000
~~~

không nhất thiết tương đương.

Event sourcing cần:

- Aggregate boundaries và business invariants.
- Domain event contracts có ý nghĩa ổn định.
- Ordering/expected aggregate version.
- Deterministic projection/replay semantics.
- Event schema migration/upcasting.
- Snapshots cho lịch sử dài.
- Tách replay state khỏi việc phát external side effects.
- Cơ chế correction/compensation thay vì tự ý sửa lịch sử.

Nếu chỉ lưu changes của fields, khi schema thay đổi hoặc khi cần biết vì sao state đổi, lịch sử đó có thể không đủ.

## 22. Snapshot trạng thái trong event sourcing

Một aggregate có 10.000 events; đọc mọi event cho mỗi GET có thể tốn kém.

Snapshot:

~~~json
{
  "aggregateId": "order-101",
  "lastAppliedSequence": 9500,
  "state": {
    "status": "SHIPPED",
    "paidAmount": 500000
  }
}
~~~

Đọc:

~~~text
Load snapshot ở seq 9500.
Apply events seq 9501 ... 10000.
Return current state.
~~~

Snapshot là **tối ưu hóa đọc**; nếu hệ coi event log là authority thì snapshot không thay thế lịch sử. Sequence/checkpoint phải được lưu đủ để tránh bỏ sót hoặc apply lặp.

Một **database backup snapshot** trong hệ CRUD phục vụ recovery, không mặc nhiên là event-sourcing snapshot.

## 23. CQRS có thể độc lập với event sourcing và CDC

**CQRS** tách command/write model với query/read model khi cần:

~~~text
Command model:
  Order service + MongoDB.

Query model:
  Search index / materialized view.
~~~

Read model có thể được cập nhật bằng CDC hoặc business events.

Điều quan trọng:

- CQRS **không bắt buộc** event sourcing.
- Event sourcing **không bắt buộc** CQRS phức tạp.
- CDC **không đồng nghĩa** CQRS.

Ba lựa chọn giải ba vấn đề khác nhau: **ngữ nghĩa dữ liệu có thẩm quyền**, **tách mô hình truy vấn**, và **phát hiện thay đổi**.

## 24. Một event ID không giống một broker offset

Ví dụ:

~~~text
Domain event:
  eventId = evt-900.

Publish 1:
  Kafka partition 2, offset 120.

Publish retry:
  Kafka partition 2, offset 125.
~~~

Hai broker records có thể chứa cùng **evt-900** nếu publisher retry sau khi ACK bị mất.

Phân biệt:

| Identifier | Mục tiêu |
|---|---|
| Business eventId | Logical fact, dùng dedup |
| AggregateId | Business entity/stream |
| AggregateVersion | Thứ tự trong aggregate theo contract |
| Command/idempotency key | Một ý định nghiệp vụ qua retries |
| CDC source position/resume token | Điểm đọc change log |
| Broker partition/offset | Vị trí message trong broker log |
| Trace/request ID | Truy vết attempt/flow |

**Dùng broker offset làm business eventId** thường sai nếu cùng event có thể republish ở offset khác.

## 25. Consumer phải idempotent

Timeline:

~~~text
1. Outbox evt-900 commit.
2. Relay publish evt-900.
3. ACK bị mất.
4. Relay publish lại evt-900.
5. Loyalty consumer nhận hai bản.
~~~

Nếu consumer cộng điểm 10 hai lần, số dư sai.

Một thiết kế:

~~~text
Atomic consumer unit:
  IF inbox[(consumerName, evt-900)] absent:
      create ledger record earn-evt-900
      apply/project +10 points
      mark inbox processed
  ELSE:
      ignore duplicate
~~~

Nếu inbox và business effect ở hai systems không cùng transaction, cần thiết kế recovery/ledger phù hợp. Check-then-insert không nguyên tử không chặn hai workers đồng thời.

**At-least-once delivery với idempotent effect** thường là lựa chọn thực tế; không hứa broker giao một lần duy nhất trong mọi failure schedule.

## 26. Idempotency của producer quan trọng không kém consumer

Client gọi CapturePayment với cùng idempotency key hai lần vì HTTP response mất.

Đúng:

~~~text
Attempt 1:
  Commit PaymentCaptured evt-900.

Attempt 2:
  Lookup saved operation outcome.
  Return same result.
  Không tạo evt-901.
~~~

Nếu mỗi retry sinh eventId mới, consumer có thể xem đó là hai facts độc lập. Lưu result và event identity theo **logical intent**, không theo mỗi HTTP attempt.

Với financial operations, còn cần stable payment provider identity, external reconciliation và business uniqueness.

## 27. Thứ tự sự kiện: trong phạm vi nào?

Một order:

~~~text
OrderCreated v1
PaymentCaptured v2
OrderConfirmed v3
OrderCancelled v4
~~~

Thứ tự **trong aggregate order-101** có thể quan trọng.

Nhưng không nhất thiết có một total order toàn cầu giữa order-101 và order-102 hoặc giữa nhiều regions.

| Scope | Ví dụ | Điều cần kiểm chứng |
|---|---|---|
| Aggregate | Order 101 v1 rồi v2 | Producer version contract |
| Partition | Kafka messages trong cùng partition | Key routing/consumer semantics |
| Transaction | Nhiều mutations cùng commit | CDC transaction metadata, nếu hỗ trợ |
| Global | Tất cả writes mọi regions | Không tự giả định |
| Wall-clock | Timestamp trước/sau | Clock skew, retries và concurrency |

Không lấy **thời điểm consumer nhận được** làm thứ tự business fact nếu có replication delay, retry hoặc partitions.

## 28. Full-state replacement khác incremental delta

**Full state:**

~~~json
{
  "orderId": "order-101",
  "version": 7,
  "status": "PAID",
  "totalAmount": 500000
}
~~~

**Delta:**

~~~json
{
  "eventId": "evt-points-900",
  "type": "PointsEarned",
  "delta": 10
}
~~~

Với full state, consumer có thể chọn bản có sourceVersion mới nhất nếu hợp đồng cho phép.

Với delta, bỏ mất một message có thể làm tổng điểm sai; không thể chỉ nhảy tới bản cuối nếu không có snapshot/ledger authoritative khác.

Một CDC patch cũng không nhất thiết là full state. Consumer phải biết **replace**, **patch** hay **apply business transition**, vì mỗi loại yêu cầu replay/gap handling khác nhau.

## 29. Version guard cho projection

Ví dụ source đã có:

~~~text
order-101 version 7, status PAID.
~~~

Search index lưu version 7, sau đó nhận event version 6:

~~~text
incoming.version = 6
indexed.version = 7

=> bỏ bản cũ.
~~~

Pseudocode:

~~~text
if incoming.version <= indexed.version:
    ignore duplicate/stale
else:
    apply conditionally with new version
~~~

Compare và apply phải nguyên tử trong sink hoặc giao thức bảo vệ tương đương. Nếu consumer cần áp dụng từng domain event liên tiếp, gap ở version 6 có thể không được bỏ qua; cần **replay missing events** hoặc rebuild từ snapshot phù hợp.

Không dùng cùng một guard cho mọi message mà không xét nghĩa full-state/delta.

## 30. Mỗi mutation trong một transaction có thể là một CDC record riêng

Ví dụ:

~~~text
Transaction T:
  UPDATE orders/order-101
  UPDATE inventory/sku-42
  INSERT outbox/evt-900
COMMIT
~~~

CDC transport có thể phát nhiều records với cùng transaction context tùy engine. Một consumer thấy UPDATE order trước UPDATE inventory **không tự chứng minh transaction ở nguồn mới commit một nửa**: đó có thể là thứ tự vận chuyển nhiều messages của cùng commit.

Nếu consumer cần **một fact hoàn chỉnh**, outbox business event thường rõ nghĩa hơn việc đợi đủ một tập mutations mà schema sau này có thể thay đổi.

Nếu NoSQL không hỗ trợ transaction xuyên các partitions liên quan, producer cần workflow/saga; event phải nói rõ **bước nào đã hoàn tất**, không nhận vơ toàn bộ operation đã thành công.

## 31. MongoDB Change Streams

MongoDB Change Streams cho phép quan sát inserts, updates, replaces, deletes và một số event types khác trên deployment/cấu hình hỗ trợ.

Ví dụ Node.js:

~~~javascript
const stream = db.collection("orders").watch([], {
  fullDocument: "updateLookup"
});

for await (const change of stream) {
  console.log(change.operationType, change.documentKey);
  // Lưu resume token bền vững theo consumer protocol.
}
~~~

Lưu ý:

- Có thể nhận **operationType**, **documentKey** và **resume token** theo dạng event.
- **updateDescription** thường cho changed fields với UPDATE, không mặc nhiên là before/after đầy đủ.
- **fullDocument: updateLookup** lấy document theo semantics của lookup; không nhất thiết là immutable after-image đúng tại thời điểm UPDATE nếu đã có writes khác.
- **Pre-images** cần cấu hình hỗ trợ và retention phù hợp.
- Resume token chỉ dùng được trong điều kiện lịch sử nguồn còn đủ; consumer offline lâu có thể phải rebuild.
- Change Streams **không tự biết** bản cập nhật PAID có nghĩa PaymentCaptured.

Một ứng dụng có thể dùng Change Streams để chuyển outbox records, trong đó domain event payload đã được producer tạo.

## 32. DynamoDB Streams

DynamoDB Streams ghi nhận item changes theo view type được cấu hình, chẳng hạn:

- **KEYS_ONLY**: item keys.
- **NEW_IMAGE**: item mới.
- **OLD_IMAGE**: item cũ.
- **NEW_AND_OLD_IMAGES**: cả hai.

Ví dụ:

~~~text
PutItem ORDER#101.
UpdateItem ORDER#101 status=PAID.
DeleteItem ORDER#101.
~~~

Các stream records không tự xác nhận payment workflow.

Cần hiểu:

- Stream retention hữu hạn.
- Ordering và transaction semantics trong phạm vi mà dịch vụ bảo đảm.
- Idempotent consumer và failover.
- Payload chứa dữ liệu nhạy cảm khi bật old/new images.
- Một nghiệp vụ nhiều items không mặc nhiên hiện thành một stream record.

Nếu cần domain event chính xác, có thể tạo **event/outbox item** trong transaction đúng phạm vi DynamoDB hỗ trợ và dùng Stream để relay.

## 33. Cassandra CDC

Apache Cassandra có cơ chế CDC liên quan commit log ở mức engine/cấu hình; việc đưa changes ra một stream để tiêu thụ thường cần connector, checkpoint, retention và failure recovery được thiết kế riêng.

Lưu ý:

- Không có mapping tự động giữa một write vào bảng và một business event.
- Một logical order có thể được denormalize vào nhiều tables.
- TTL/tombstone, repair và write semantics cần được hiểu đúng.
- Node failure, segment lifecycle, disk pressure và replay tạo chi phí vận hành.
- Những thay đổi thuộc nhiều partitions không tự là transaction nghiệp vụ chung.

Không lấy “đã bật CDC” làm bằng chứng một consumer có thể phát OrderPlaced không trùng, đủ fields và đúng domain invariants.

## 34. CouchDB _changes feed

Apache CouchDB cung cấp **_changes feed** để hỗ trợ replication/đồng bộ document revisions và deletion information.

Ví dụ khái niệm:

~~~text
doc note-42 changed at sequence S1.
doc note-42 deleted at sequence S2.
~~~

Nó có ích cho:

- Đồng bộ offline-first.
- Phát hiện document changes.
- Cập nhật read models.
- Truyền deletion/revision information theo protocol.

Nhưng:

- Sequence/checkpoint không mặc nhiên là global business order.
- Conflict revisions/winning revision không tự định nghĩa business merge policy.
- _deleted/purge có semantics khác nhau.
- _changes không tự phát DocumentApproved, PaymentCaptured hoặc CollaboratorInvited.

Các facts ấy thuộc về application domain.

## 35. Redis keyspace notifications không phải event store

Redis hỗ trợ thông báo một số hoạt động liên quan keys qua **keyspace notifications/Pub/Sub** nếu được cấu hình.

Nhưng:

- Đây không mặc nhiên là persistent log cho consumer offline replay.
- Một event expired không nhất thiết được phát đúng giây TTL vừa về 0.
- Connection loss/restart có thể gây gaps theo cơ chế Pub/Sub.
- Key SET/DEL không tự mang domain semantics.

Không dùng một key expiration notification làm bằng chứng duy nhất rằng **ReservationExpired** đã được nghiệp vụ công nhận.

Redis Streams là một khả năng lưu/tiêu thụ messages riêng, có retention, consumer group, ACK và recovery semantics; dùng Streams cũng không tự biến key changes thành business events.

## 36. So sánh một số nguồn change

| Công nghệ | Nguồn thường gặp | Phù hợp | Không mặc nhiên cung cấp |
|---|---|---|---|
| MongoDB | Change Streams/oplog-backed | Đồng bộ collections, outbox relay | Domain meaning từ UPDATE |
| DynamoDB | DynamoDB Streams | Item changes, state projections | Lịch sử business vĩnh viễn |
| Cassandra | CDC/commit-log ecosystem | Data changes theo connector | Transaction nghiệp vụ xuyên tables |
| CouchDB | _changes/revisions | Document replication | Business conflict policy |
| Redis | Keyspace notifications hoặc Streams do app định nghĩa | Cache telemetry / custom transport | Durable domain facts từ key notification |

Cụ thể còn phụ thuộc engine version, deployment mode, retention, connector và cấu hình thực tế. Đừng mang guarantees của một hệ sang hệ khác.

## 37. Event envelope nên có identity và context

Ví dụ:

~~~json
{
  "eventId": "evt-900",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "tenantId": "shop-a",
  "aggregateType": "Order",
  "aggregateId": "order-101",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-14T10:02:00Z",
  "recordedAt": "2026-11-14T10:02:01Z",
  "correlationId": "checkout-551",
  "causationId": "command-capture-100",
  "payload": {
    "paymentId": "pay-101",
    "amount": 500000,
    "currency": "VND"
  }
}
~~~

Ý nghĩa:

- **eventId**: logical fact identity.
- **aggregateId**: business entity.
- **aggregateVersion**: thứ tự theo aggregate nếu producer đảm bảo.
- **schemaVersion**: phiên bản message contract, khác aggregateVersion.
- **correlationId**: liên kết workflow.
- **causationId**: thao tác/event trực tiếp gây ra.
- **occurredAt**: khi fact xảy ra theo định nghĩa domain.
- **recordedAt**: khi producer ghi nhận.

Không bắt buộc dùng tất cả fields nếu không có yêu cầu; đặc biệt không giả lập timestamp/ordering mà producer không thể cam kết.

## 38. Các mốc thời gian khác nhau

~~~text
businessOccurredAt
sourceCommittedAt
connectorCapturedAt
brokerPublishedAt
consumerProcessedAt
~~~

| Mốc | Vai trò |
|---|---|
| occurredAt | Khi fact nghiệp vụ xảy ra theo contract |
| committedAt | Khi source công nhận mutation |
| capturedAt | Khi connector nhận biết change |
| publishedAt | Khi broker nhận message |
| processedAt | Khi consumer hoàn thành xử lý |

Thường có độ trễ giữa các mốc. **capturedAt mới hơn** không chứng minh **payload business mới hơn**; một event cũ có thể được replay hôm nay.

Để so freshness, cần phân biệt **commit-to-capture**, **capture-to-publish**, **publish-to-process** và **end-to-end**.

## 39. CorrelationId và causationId

Một checkout:

~~~text
correlationId=checkout-551

PlaceOrder command-1
  -> OrderPlaced evt-1
  -> StockReserved evt-2 (causation=evt-1)
  -> PaymentAuthorized evt-3 (causation=evt-1)
  -> OrderConfirmed evt-4 (causation=evt-3)
~~~

CDC có thể mang source transaction metadata hoặc application fields, nhưng **không tự suy ra correlation graph** chính xác nếu producer không lưu các IDs đó.

Nên phân biệt request/trace ID của mỗi HTTP attempt với **business operation ID** ổn định qua retry.

## 40. DELETE dưới ba góc nhìn

**State tombstone:**

~~~json
{
  "_id": "doc-42",
  "deleted": true,
  "revision": 19
}
~~~

**Business event:**

~~~json
{
  "eventId": "evt-delete-900",
  "eventType": "DocumentDeleted",
  "documentId": "doc-42",
  "revision": 19,
  "actorId": "user-11"
}
~~~

**CDC record:**

~~~json
{
  "operation": "DELETE",
  "documentKey": {"_id": "doc-42"},
  "sourcePosition": "opaque-901"
}
~~~

Nếu ứng dụng dùng soft delete, CDC có thể ghi **UPDATE**, không phải DELETE.

Một CDC DELETE chưa cho biết:

- User chủ ý xóa hay TTL/cleanup xóa?
- Xóa shared object hay chỉ ẩn với một user?
- Dữ liệu có phải erasure theo privacy requirement?
- Tất cả caches/projections/backups đã xóa chưa?

Business event và deletion lifecycle phải định nghĩa scope cùng ý nghĩa riêng.

## 41. Tránh hồi sinh dữ liệu cũ do out-of-order

Timeline:

~~~text
v18: DocumentUpdated.
v19: DocumentDeleted.

Consumer nhận:
  DELETE v19.
  UPDATE v18 (đến trễ).
~~~

Nếu consumer chỉ:

~~~text
DELETE search document.
UPSERT v18.
~~~

thì document đã xóa có thể **xuất hiện trở lại**.

Cần tombstone hoặc version floor:

~~~text
projection[doc-42].maxAppliedVersion=19
projection[doc-42].deleted=true

incoming v18:
  ignore.
~~~

Nếu xóa luôn revision metadata sau DELETE, event v18 có thể bị hiểu là CREATE. GC của tombstone phải tính thời gian nguồn/consumer còn có thể replay event cũ.

## 42. Tại sao một sự kiện DELETE khác một yêu cầu xóa dữ liệu?

~~~text
Command:
  EraseUserPersonalData(user-11)

Business event:
  UserDataErasureRequested(user-11)

CDC:
  DELETE users/user-11
~~~

Không được coi một CDC DELETE đơn lẻ là **erasure complete**.

Có thể còn:

- Search index.
- Redis cache.
- Analytics projection.
- Object attachments.
- Backups.
- Thiết bị offline.

Nếu sản phẩm phát event **UserDataErasureCompleted**, producer phải định nghĩa bằng chứng hoàn tất và giới hạn phạm vi, không phát chỉ vì xóa một row thành công.

## 43. Schema evolution có ba lớp

1. **Persistence schema:** tên field/collection trong nguồn.
2. **Business event schema:** contract domain event.
3. **CDC envelope schema:** format của engine/connector.

Ví dụ:

~~~text
MongoDB:
  rename status -> paymentState.

Domain event:
  OrderPaid vẫn có orderId + amount + currency.

CDC direct consumer:
  phải cập nhật mapping sang paymentState.
~~~

Tách domain event khỏi storage schema giúp giảm coupling, nhưng event schema **vẫn cần versioning/compatibility**.

Không dùng cùng một version number cho persistence, aggregate và event schema nếu chúng thay đổi độc lập.

## 44. Event versioning và backwards compatibility

Event v1:

~~~json
{
  "eventType": "PaymentCaptured",
  "eventVersion": 1,
  "amount": 500000
}
~~~

Event v2:

~~~json
{
  "eventType": "PaymentCaptured",
  "eventVersion": 2,
  "amount": 500000,
  "currency": "VND"
}
~~~

Thêm currency có vẻ đơn giản, nhưng consumer cũ có thể mặc định amount theo đơn vị khác.

Nguyên tắc:

- Khai báo required/optional fields.
- Thay đổi bổ sung có semantics tương thích nếu có thể.
- Không tái sử dụng tên field cho ý nghĩa mới.
- Có schema contract tests hoặc registry khi phù hợp.
- Dùng upcaster/migration nếu consumer cần đọc event history cũ.
- Đảm bảo replay v1 không bị hiểu theo rules v2 một cách sai lệch.

**Event schema version khác aggregate version**, và khác CDC connector version.

## 45. Correction event thay vì âm thầm sửa lịch sử

Giả sử:

~~~text
PaymentCaptured amount=500000.
Reconciliation phát hiện settled amount là 450000.
~~~

Không nên tự sửa historical event rồi khiến các consumers có lịch sử không đồng nhất.

Có thể phát:

~~~text
PaymentCaptureCorrected
ReconciliationAdjustmentRecorded
RefundIssued
~~~

tùy thực chất nghiệp vụ. Correction event tham chiếu fact trước và nêu lý do/amount thay đổi.

**Một event quá khứ có thể sai và cần correction**, nhưng correction là một sự kiện có ý nghĩa riêng; không đồng nhất với CDC UPDATE sửa payload cũ.

## 46. Initial snapshot và CDC catch-up

Search index mới cần backfill 100 triệu documents, nguồn vẫn ghi liên tục.

Quy trình:

~~~text
1. Xác định snapshot/checkpoint S.
2. Backfill dữ liệu tại mốc logic S.
3. Capture changes phát sinh từ S theo giao thức.
4. Apply với version guards/idempotency.
5. Đối soát source và projection.
6. Cutover.
~~~

Không làm:

~~~text
Quét hết documents.
Sau đó mới bật CDC từ thời điểm hiện tại.
~~~

vì writes trong lúc scan có thể bị mất.

Cần cân nhắc:

- Snapshot consistency qua nhiều pages.
- Event xảy ra trong lúc backfill.
- DELETE/tombstone propagation.
- Cursor retention.
- Dữ liệu bị quét hai lần.
- Source load/rate limit và checkpoint.

## 47. CDC retention thường hữu hạn

Ví dụ:

~~~text
Consumer checkpoint=900.
Consumer offline quá lâu.
Log chứa position 901 đã bị dọn.
Consumer không thể resume từ 900.
~~~

Phản ứng đúng:

- Phát hiện **expired/invalid resume token**.
- Không tự đặt position=latest rồi coi là đồng bộ.
- Bootstrap lại state qua snapshot + catch-up.
- Reconcile deletes và versions.
- Lập kế hoạch log/broker retention theo SLA offline.

**CDC stream không tự là event store/audit log vĩnh viễn**.

Nếu yêu cầu lịch sử nhiều năm, phải có nguồn lưu giữ tương ứng với schema và compliance policy riêng.

## 48. Retention của state, outbox, CDC, event log khác nhau

~~~text
Order state:
  retention theo nghiệp vụ/pháp lý.

Outbox:
  giữ đủ để publish/recover theo policy.

Source CDC log:
  giới hạn theo engine/configuration.

Broker event log:
  retention/compaction policy.

Business ledger/audit:
  retention theo yêu cầu riêng.
~~~

Không hứa replay một năm nếu outbox/broker chỉ giữ ít ngày và không có event archive.

Không xóa outbox quá sớm khi consumer chưa có cơ chế recovery độc lập. Đồng thời không lưu payload chứa PII vô hạn nếu không có yêu cầu và biện pháp bảo vệ.

## 49. Log compaction khác lưu đầy đủ domain history

Một state-oriented compacted log:

~~~text
key=order-101, value=CREATED
key=order-101, value=PAID
key=order-101, value=SHIPPED
~~~

Sau compaction theo key, có thể chỉ giữ value gần nhất trong phạm vi chính sách.

Phù hợp bootstrap **trạng thái gần hiện tại**.

Nhưng nếu domain cần biết đủ:

~~~text
OrderCreated
PaymentCaptured
OrderShipped
~~~

thì không thể mất PaymentCaptured chỉ vì có OrderShipped mới hơn.

**State compaction và append-only business history có semantics lưu giữ khác nhau.**

## 50. Replay phải tránh side effects

Khi rebuild search index:

~~~text
Reprocess OrderPaid event -> update search projection.
~~~

Điều đó **không nên đồng thời**:

~~~text
Re-send receipt email.
Capture payment lần nữa.
Award loyalty points lần nữa.
~~~

Các biện pháp:

- Tách projection replay khỏi external actions.
- Idempotent inbox/ledger ở consumer.
- Phân biệt rebuild mode và live mode khi cần.
- Chỉ side effect nếu hợp đồng thực sự yêu cầu và có bảo vệ.
- Dùng same eventId thay vì sinh ID mới khi replay.

Domain event là một fact lịch sử, không phải lời cho phép thực thi lại mọi tác động đã xảy ra.

## 51. Case study: doanh thu

Một báo cáo sai:

~~~text
Mỗi khi CDC thấy order.status chuyển thành PAID:
  revenue += order.totalAmount
~~~

Sai khi:

- Một order bị update/reconciled nhiều lần.
- Có refunds và partial captures.
- Migration đổi status.
- CDC messages bị giao lại.
- Amount hiện tại khác amount settled.
- Một order có nhiều payment attempts.

Thiết kế đúng tùy domain:

- Financial ledger có transaction identity ổn định.
- PaymentCaptured/RefundIssued/SettlementRecorded events được công nhận.
- Unique business keys để tránh đếm trùng.
- Quy tắc gross/net/currency/settlement rõ.
- Đối soát với nguồn tài chính có thẩm quyền.

**State PAID không phải toàn bộ lịch sử thu tiền, còn CDC UPDATE không phải chứng từ giao dịch.**

## 52. Case study: thưởng điểm khách hàng

Nếu Loyalty consumer nghe mọi status=PAID CDC UPDATE và cộng 10 điểm, duplicate delivery hoặc migration có thể làm điểm tăng sai.

Một thiết kế:

~~~text
Producer:
  OrderPaid eventId=evt-900.

Consumer:
  IF inbox[(loyalty,evt-900)] absent:
      INSERT loyalty ledger event
      APPLY/project points
      SAVE inbox marker
~~~

Nếu business rule chỉ thưởng **một lần cho mỗi order**, nên thêm unique key:

~~~text
(tenantId, orderId, rewardType)
~~~

vì ngay cả hai eventIds hợp lệ khác nhau có thể cùng tranh một bất biến nghiệp vụ.

## 53. Case study: đồng bộ search index

Search index cần:

~~~text
tenantId
orderId
status
createdAt
productNames
sourceVersion
~~~

Ở đây **state CDC** có thể phù hợp hơn việc bắt consumers hiểu hàng chục business events.

Pipeline:

1. Bootstrap snapshot.
2. Capture INSERT/UPDATE/DELETE.
3. Decode patch hoặc full image theo nguồn.
4. Ghi với sourceVersion guard.
5. Đối soát missing/stale/extra IDs.
6. Quản lý schema mapping và backfill.
7. Chặn query sai tenant/permission.
8. Recover khi CDC cursor hết hạn.

Đừng tạo một domain event riêng chỉ để nói “field updatedAt đổi” nếu search chỉ cần current state.

## 54. Case study: quyền truy cập và xóa dữ liệu

Một tài liệu bị thu hồi quyền:

~~~text
Business:
  DocumentAccessRevoked(user-B, doc-42)

State:
  ACL không còn user-B.

CDC:
  UPDATE documents/doc-42 hoặc ACL collection.
~~~

Search/cache có thể đồng bộ bất đồng bộ. Nếu revocation phải hiệu lực ngay, **read authorization path** không được chỉ tin vào projection stale.

Tương tự, **DocumentDeleted** không nhất thiết là **DataErasureCompleted**. Các bản sao, backups và offline clients có phạm vi xử lý riêng.

## 55. Multi-region cần kiểm soát nguồn phát event

Giả sử MongoDB hoặc một NoSQL khác có state replication giữa regions.

Consumer ở region A và B có thể cùng thấy một thay đổi được replicate. Nếu cả hai biến change thành OrderPaid domain event, có thể phát fact hai lần.

Phải xác định:

- Region/leader/aggregate owner nào được quyền tạo domain event.
- Stable eventId có được giữ xuyên replication/replay?
- Replica apply có bị xem nhầm là business action mới?
- Transaction version/generation khi failover có còn đúng?
- Multi-region conflict resolution ảnh hưởng state/event thế nào?

Không được suy từ một wall-clock timestamp rằng một region luôn có business truth mới hơn region kia.

## 56. CDC và PII

CDC với before/after images có thể chứa:

~~~text
Email cũ và mới.
Địa chỉ giao hàng.
Thông tin user profile.
Payment metadata.
Document content.
~~~

Mỗi stream/broker/topic mới có thể trở thành một **bản sao dữ liệu nhạy cảm**.

Cần:

- Classification/allowlist fields.
- Minimize payload theo nhu cầu.
- Encryption và access controls.
- Tenant isolation.
- Retention/replay policy.
- Audit access và incident response.
- Kiểm phạm vi data deletion/erasure trong event history và backups.

**Immutable log không tự miễn nghĩa vụ bảo vệ hoặc xóa dữ liệu cá nhân**. Tùy yêu cầu, có thể dùng tokenization, encryption/crypto-shredding, retention giới hạn hoặc kiến trúc tách PII khỏi fact lâu dài.

## 57. Technical audit, business history và backup khác nhau

| Mục đích | Nguồn thường thích hợp |
|---|---|
 Khôi phục service sau sự cố | Backup/snapshot + logs |
 Tra timeline nghiệp vụ | Domain event/ledger |
 Truy ai đã sửa field/đọc record | Technical audit |
 Đồng bộ read models | CDC/change streams |
 Kiểm tra thao tác duplicate | Idempotency/inbox/ledger |

Một backup chụp lúc 10:00 không nhất thiết cho biết ai đã capture payment lúc 09:50 nếu history không được lưu.

Một CDC stream có retention ngắn không đủ cho audit lâu dài.

Một domain event log cũng không thay tất cả database backups, infrastructure/configuration và recovery plans.

## 58. Observability cho chuỗi sự kiện

| Metric | Câu hỏi |
|---|---|
| cdc_capture_lag | Source commit tới connector mất bao lâu? |
| cdc_checkpoint_age | Consumer cách nguồn bao xa? |
| outbox_backlog_age | Event commit nhưng chưa publish lâu chưa? |
| event_publish_retry_total | Có mất ACK/timeouts? |
| duplicate_event_delivery_total | Có redelivery bao nhiêu? |
| consumer_processing_lag | Event tới effect mất bao lâu? |
| dead_letter_count | Consumer lỗi payload/schema? |
| schema_incompatibility_total | Event versions có tương thích? |
| projection_version_gap | Read model có lùi source không? |
| delete_propagation_lag | DELETE tới search/cache mất bao lâu? |
| reconciliation_mismatch_total | Source và projection có lệch? |
| snapshot_backfill_progress | Bootstrap tiến triển tới đâu? |
| stream_retention_headroom | Consumer còn đủ thời gian để resume? |

Không đưa từng eventId/orderId thành metric label cardinality vô hạn. Dùng tracing/logs được bảo vệ để điều tra event cụ thể.

## 59. Runbook: state PAID nhưng consumer không có event

1. Xác định order/payment authoritative state và business operation ID.
2. Kiểm event có được producer xác nhận và ghi outbox không.
3. Nếu thiếu outbox nhưng state commit, kiểm transaction boundary, retry và bug producer.
4. Nếu outbox có, kiểm relay checkpoint, lag, publish retry/ACK.
5. Kiểm broker retention/consumer subscription.
6. Kiểm dead-letter, schema incompatibility và retry.
7. Kiểm inbox/ledger: có thể consumer xử lý rồi nhưng ACK mất.
8. Nếu replay, dùng **cùng logical eventId**, không tự sinh fact mới.
9. Đối soát business uniqueness để không cộng điểm/email hai lần.
10. Sửa nguyên nhân, bổ sung alert và fault test.

Không chữa lỗi bằng cách phát OrderPaid mới với ID mới mà chưa biết effect cũ đã xảy ra hay chưa.

## 60. Runbook: source và projection lệch

~~~text
Source:
  order-101 status=PAID version=7

Search:
  order-101 status=PENDING_PAYMENT version=6
~~~

Kiểm tra:

1. CDC có thấy change v7?
2. Consumer checkpoint đã vượt vị trí v7 chưa?
3. Có schema decode error hoặc dead-letter?
4. Có out-of-order v6 overwrite v7?
5. Version guard đã so/ghi atomically chưa?
6. Có expired cursor khiến v7 bị mất?
7. DELETE/tombstone có bị loại nhầm?
8. Rebuild từ source có hạn chế tải và catch-up chưa?
9. Endpoint đã hội tụ sau repair chưa?
10. Có automated reconciliation để phát hiện sớm không?

**Rebuild projection từ state** khác **replay business events**; không nên chạy external side effects khi chỉ muốn sửa read model.

## 61. Bảng kiểm thử lỗi

| Tình huống | Kết quả cần đạt |
|---|---|
| DB commit, app crash trước broker publish | Outbox bảo tồn event intent |
| Broker publish, ACK mất | Consumer dedup |
| Một domain fact ghi nhiều collections | Không đếm thành nhiều events |
| Migration đổi status sang PAID | Không phát PaymentCaptured giả |
| Consumer nhận v8 trước v7 | Version/gap policy đúng |
| DELETE v9 rồi UPDATE v8 | Không hồi sinh projection |
| Snapshot scan trong lúc UPDATE | Không bỏ sót giữa snapshot và CDC |
| Resume token hết hạn | Full rebuild/catch-up |
| Event schema v2 xuất hiện | Consumers xử lý compatible hoặc fail rõ |
| Replay lịch sử | Không thu tiền/email thêm |
| Consumer crash sau effect trước checkpoint | Inbox/effect recovery |
| Multi-region replay/replication | Không nhân domain fact |
| CDC chứa PII | Access/retention đúng |
| Backfill nhiều records | Source SLO vẫn được bảo vệ |

Fault tests cần ghi cả source state, event identity, consumer business effects và checkpoint; chỉ thấy broker message đến không đủ.

## 62. Chọn nguồn nào theo mục đích

~~~mermaid
flowchart TD
    A["Consumer cần điều gì?"] --> B{"State gần hiện tại?"}
    B -->|"Có"| C["State API / CDC / projection"]
    B -->|"Không"| D{"Fact nghiệp vụ?"}
    D -->|"Có"| E["Business events / outbox / event store"]
    D -->|"Không"| F{"Mirror mutations?"}
    F -->|"Có"| G["CDC / change feed"]
    F -->|"Không"| H["Làm rõ use case"]
    C --> I["Version, DELETE, snapshot, freshness"]
    E --> J["Event meaning, ID, ordering, replay"]
    G --> K["Source position, retention, before/after"]
    I --> L["Idempotency + recovery + security"]
    J --> L
    K --> L
~~~

Các bước thiết kế:

1. Viết câu hỏi consumer cần trả lời.
2. Xác định cần **state hiện tại**, **fact đã xảy ra** hay **storage mutation**.
3. Chọn authoritative source của dữ liệu.
4. Định nghĩa event contract nếu cần phản ứng theo domain.
5. Chọn CDC nếu cần projection/mirror.
6. Chọn transaction/outbox hoặc event store theo tính đúng.
7. Thiết kế event ID, source version, ordering và idempotency.
8. Xử lý DELETE, schema evolution, PII.
9. Quy định snapshot/replay/retention/recovery.
10. Dựng metrics, reconciliation và fault tests.

## 63. Các hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Order PAID nghĩa vừa thanh toán” | State có thể do migration/reconciliation | Fact cần xác minh theo domain |
| “UPDATE CDC là domain event” | Storage không biết mọi nguyên nhân | Domain contract |
| “Một nghiệp vụ = một CDC record” | Nhiều writes per transaction | Khác granularity |
| “Một CDC record = một nghiệp vụ” | Technical writes cũng có | Chọn business facts rõ |
| “Command CapturePayment = PaymentCaptured” | Command có thể thất bại | Event sau fact được công nhận |
| “Event name đủ chứng minh fact” | Producer có thể phát sai | Commit/invariants |
| “Event phải chứa full document” | Coupling và PII | Payload theo contract |
| “Current state là toàn bộ history” | Bỏ các trạng thái cũ | Event/audit riêng |
| “CDC = event sourcing” | CDC phản ánh writes | Event sourcing dùng facts làm authority |
| “CQRS buộc event sourcing” | Hai lựa chọn độc lập | Hiểu đúng phạm vi |
| “Hai API calls trong Java method atomic” | Crash giữa DB và broker | Outbox |
| “Outbox bảo đảm broker giao một lần” | Relay có thể retry | Consumer idempotent |
| “Broker offset = eventId” | Republish tạo offset mới | Logical event ID |
| “Timestamp cho global order” | Clock skew/retry/partition | Aggregate version/scope |
| “CDC luôn có before image” | Nguồn/cấu hình khác nhau | Kiểm contract |
| “MongoDB updateLookup là immutable after-image tại commit” | Lookup timing semantics riêng | Không tự suy exact before/after |
| “DynamoDB Streams lưu vô hạn” | Stream retention hữu hạn | History store riêng |
| “Cassandra CDC tự tạo business events” | Commit log changes không có domain | Outbox/event producer |
| “CouchDB _changes tự quyết định domain conflict” | Revision replication khác business | Application policy |
| “Redis keyspace notifications là durable history” | Pub/Sub có gaps | Transport phù hợp |
| “CDC DELETE = erasure complete” | Backups/cache còn | Deletion lifecycle |
| “Xóa search row là xong” | UPDATE cũ có thể upsert lại | Version floor/tombstone |
| “Snapshot rồi bật CDC từ latest” | Bỏ writes lúc scan | Snapshot + catch-up |
| “Rebuild index cần replay emails” | Side effects bị nhân đôi | Tách projection replay |
| “Event schema và DB schema luôn cùng version” | Thay đổi độc lập | Versioned contracts |
| “Event immutable không sửa được lỗi” | Correction là fact mới | Compensating/correction events |
| “Change stream đủ cho audit nhiều năm” | Retention/meaning hạn chế | Audit/event ledger riêng |
| “CDC captured nghĩa consumer đã xử lý” | Transport nhiều chặng | End-to-end metrics |

## 64. Bài tập thực hành

### Bài tập 1 — Phân loại ba bản ghi

Cho:

~~~text
A. orders/order-101 status=PAID, version=7.
B. PaymentCaptured(paymentId=pay-101, amount=500000).
C. UPDATE orders/order-101 PENDING_PAYMENT -> PAID.
~~~

Hãy phân loại state, domain event và CDC; nêu điều mỗi loại không tự chứng minh.

### Bài tập 2 — Command và event

Phân biệt PlaceOrder, OrderPlaced, CapturePayment, PaymentCaptureDeclined và RefundIssued theo ý nghĩa command/fact/outcome.

### Bài tập 3 — Một fact, nhiều writes

OrderPlaced tạo order, inventory reservation, payment intent và outbox record. Vẽ số CDC records và số business facts; vì sao không đếm CDC thành số orders?

### Bài tập 4 — Một UPDATE, nhiều ý nghĩa

Document thay status, couponRedeemed và loyaltyEligible cùng lúc. Đề xuất domain events, giải thích cách xác minh chúng.

### Bài tập 5 — Migration gây event giả

Một migration sửa mọi status PAYMENT_DONE thành PAID. Nếu consumer phát PaymentCaptured từ UPDATE status, rủi ro nào xuất hiện?

### Bài tập 6 — State không giữ history

Order hiện SHIPPED nhưng muốn đo thời gian giữa PaymentAuthorized và PaymentCaptured. Dữ liệu nào cần được lưu thêm?

### Bài tập 7 — Event envelope

Thiết kế OrderPaid v1 gồm eventId, aggregateId/version, amount/currency, occurredAt và correlationId. Trường nào cần bỏ để giảm PII?

### Bài tập 8 — Notification vs carried state

Search consumer cần full current state, Notification chỉ cần biết OrderShipped. Nên dùng event notification, state transfer hay CDC?

### Bài tập 9 — DB commit trước publish

State commit nhưng process crash trước broker publish. Thiết kế transactional outbox để không mất event.

### Bài tập 10 — Publish trước commit

Broker nhận OrderPlaced trước khi DB rollback. Consumer có thể tạo tác động sai nào? Vì sao đảo thứ tự hai operations không tạo atomicity?

### Bài tập 11 — MongoDB transaction

Viết pseudocode conditional update expected version và outbox insert; giải thích tại sao phải kiểm matchedCount.

### Bài tập 12 — CDC business collection vs outbox

Chọn nguồn cho Search index và Loyalty consumer, nêu schema, event ID và replay strategy.

### Bài tập 13 — Event sourcing

Dựng event stream OrderCreated, PaymentAuthorized, PaymentCaptured, OrderShipped; tạo snapshot sau seq3 và apply seq4.

### Bài tập 14 — CDC không phải event sourcing

20 CDC records gồm 15 technical metadata changes. Vì sao không đủ để dựng domain timeline bằng cách gọi tất cả là OrderUpdated?

### Bài tập 15 — MongoDB Change Streams

Giải thích operationType, documentKey, updateDescription, fullDocument updateLookup, pre-image và resume token. Những fields nào cần cấu hình riêng?

### Bài tập 16 — DynamoDB Streams

So sánh KEYS_ONLY, NEW_IMAGE, OLD_IMAGE và NEW_AND_OLD_IMAGES khi xây state projection.

### Bài tập 17 — Cassandra CDC

Order denormalize ở ba tables; vì sao không được phát ba OrderPlaced events cho ba row changes?

### Bài tập 18 — CouchDB _changes

Một client offline đồng bộ document và DELETE. _changes giải quyết gì? Vì sao không tự xác định DocumentApproved?

### Bài tập 19 — Redis keyspace notifications

Một nhóm dùng expired notification làm nguồn ReservationExpired. Phân tích giới hạn retention/durability/timing.

### Bài tập 20 — Snapshot + CDC

Nạp 100 triệu documents khi source vẫn ghi. Thiết kế checkpoint, consistent snapshot, catch-up, DELETE handling và cutover.

### Bài tập 21 — Expired cursor

Connector offline quá log retention. Vì sao resume từ latest gây thiếu dữ liệu và cần full bootstrap?

### Bài tập 22 — Duplicate events

evt-900 được publish hai lần vì ACK mất. Thiết kế inbox/ledger để chỉ cộng 10 điểm một lần.

### Bài tập 23 — Broker offset

evt-900 có offsets 120 và 125 sau republish. Consumer nên dedup theo gì, offset có vai trò gì?

### Bài tập 24 — Out-of-order

Search consumer nhận v8 trước v7. Đề xuất version guard cho full-state replacement và gap handling cho delta stream.

### Bài tập 25 — DELETE resurrection

Consumer nhận DELETE v19 rồi UPDATE v18. Thiết kế tombstone/version floor.

### Bài tập 26 — Schema evolution

MongoDB đổi field status sang paymentState nhưng OrderPaid event cần ổn định. Phân tích impacts lên CDC consumers và event consumers.

### Bài tập 27 — Correction

PaymentCaptured amount=500000 nhưng settlement chỉ 450000. Thiết kế correction event và audit.

### Bài tập 28 — Revenue analytics

Một báo cáo đếm mọi UPDATE status=PAID. Phân tích các trường hợp double count, refunds, partial captures, migration.

### Bài tập 29 — Multi-region

Hai regions cùng phát OrderPaid khi nhận replication changes. Thiết kế một event producer authority và stable IDs.

### Bài tập 30 — PII

CDC before/after images chứa email, địa chỉ. Thiết kế field minimization, ACL, encryption, retention và deletion policy.

### Bài tập 31 — Observability

Đề xuất dashboard cho CDC capture lag, outbox backlog, publish retry, consumer processing lag, dead-letter, version gaps và delete propagation.

### Bài tập 32 — Debug thiếu event

Order state PAID nhưng Loyalty không nhận OrderPaid. Viết runbook từ DB, outbox, connector, broker, inbox đến effect ledger.

### Bài tập 33 — Thiết kế kiến trúc hoàn chỉnh

Một nền tảng có MongoDB order/payment, DynamoDB user preferences, Redis cache, search index và Kafka. Yêu cầu email khi giao hàng, điểm thưởng sau thanh toán, search theo trạng thái, analytics doanh thu và deletion theo tenant. Hãy mô tả:

1. Authoritative state và các read models.
2. Các business events theo từng nghiệp vụ.
3. Những changes phù hợp để lấy trực tiếp từ CDC.
4. Transactional outbox và idempotent inbox.
5. Snapshot/backfill/catch-up cho search.
6. Event IDs, aggregate versions, ordering.
7. DELETE/tombstone và tránh out-of-order resurrection.
8. Security/PII/retention.
9. Recovery khi mất resume token.
10. Fault tests, reconciliation và metrics.

### Bài tập 34 — Phát hiện thiết kế sai

Một nhóm đề xuất:

~~~text
Mọi MongoDB UPDATE -> một BusinessEvent.
Tên event lấy từ field vừa đổi.
Broker offset làm idempotency key.
Mất cursor thì resume từ latest.
DELETE chỉ xóa search doc không giữ version.
Replay event sẽ gửi lại toàn bộ email.
~~~

Chỉ ra từng sai lầm, hệ quả và thiết kế thay thế.

---

**Kết luận:** **Dữ liệu trạng thái** mô tả đối tượng đang ra sao tại một phiên bản; **sự kiện nghiệp vụ** là fact có ý nghĩa được producer công nhận theo domain; còn **bản ghi CDC** mô tả mutation tại nguồn lưu trữ. Một nghiệp vụ có thể tạo nhiều writes, một write có thể mang nhiều hoặc không mang business meaning, và cùng một trạng thái có thể xuất phát từ nhiều nguyên nhân. Dùng **state/CDC** khi cần đồng bộ giá trị hiện hành, **domain events/outbox** khi cần phản ứng theo sự thật nghiệp vụ, và chỉ dùng **event sourcing** khi đã chọn event history làm nguồn có thẩm quyền với replay semantics riêng. Mọi pipeline cần xác định **identity, transaction boundary, idempotency, ordering, versioning, snapshot/catch-up, DELETE, schema evolution, retention, privacy và recovery**. Phân biệt đúng ba loại dữ liệu giúp tích hợp NoSQL chính xác hơn, tránh biến thay đổi kỹ thuật thành giao dịch nghiệp vụ hoặc nhân đôi hiệu ứng khi network và consumers gặp lỗi.

# Thao tác có thể thực hiện lặp an toàn và bảo vệ kết quả nghiệp vụ

Một người dùng bấm **Đặt hàng**, server đã trừ tồn kho và tạo đơn, nhưng kết nối ngắt trước khi trình duyệt nhận phản hồi. Trình duyệt, load balancer hoặc worker có thể gửi lại yêu cầu. Nếu mỗi lần gửi lại đều tạo đơn mới hoặc trừ hàng thêm lần nữa, hệ thống đã biến **một ý định nghiệp vụ** thành nhiều tác động.

Trong chương **Cập nhật đồng thời** của Database NoSQL, “thao tác có thể thực hiện lặp an toàn” không chỉ là một lệnh chạy không lỗi khi gọi lại. Nó phải giữ được **kết quả nghiệp vụ mong muốn** khi request bị retry, message được phát lại, hai worker chạy đồng thời, response mất hoặc server crash giữa chừng.

Bài học giải thích idempotency, khóa định danh ý định, atomic condition/CAS, result ledger, state machine, Outbox/Inbox, việc xác định kết quả sau timeout và kỹ thuật tương ứng trên MongoDB, DynamoDB, Cassandra/ScyllaDB và Redis. Phạm vi transaction, isolation, retry và durability phụ thuộc sản phẩm, phiên bản, topology và driver; ví dụ cần được điều chỉnh theo hợp đồng của hệ thống thật.

## 1. Một request có thể được thực thi nhiều lần

~~~text
Client                       API                       Database
  | POST /reservations         |                            |
  |--------------------------->|                            |
  |                            | reserve stock + save hold  |
  |                            |--------------------------->|
  |                            |<---------------------------|
  |                            |       committed            |
  |               X            |                            |
  |<------- response lost -----|                            |
  |                            |                            |
  | POST /reservations (retry) |                            |
  |--------------------------->|                            |
~~~

Cần phân biệt:

- **Business intent:** khách muốn giữ 2 sản phẩm SKU-A cho `reservationId=R1001`.
- **Attempt:** một lần HTTP request hoặc event được giao cho worker.
- **Effect:** thay đổi thực sự đã được commit.
- **Response:** kết quả client có thể đã nhận hoặc chưa.

Một intent có nhiều attempts. Một effect có thể đã commit mà response không tới client. Thiết kế đúng phải giới hạn **số tác động theo intent**, không dựa trên số lần handler chạy.

## 2. Định nghĩa idempotency

Một thao tác `f` với cùng intent `r` được gọi là idempotent về trạng thái khi việc lặp lại không tạo thêm thay đổi sau khi đã áp dụng:

\[
f(f(S,r),r)=f(S,r)
\]

Trong đó `S` là trạng thái hệ thống. Ví dụ:

~~~text
SET product.status = "INACTIVE":
  một lần:  INACTIVE
  hai lần: INACTIVE

INCREMENT product.viewCount by 1:
  một lần:  101
  hai lần: 102
~~~

Có thể phân biệt ba lớp:

| Lớp | Điều được bảo vệ |
|---|---|
| Idempotent command | Gọi lại cùng command không tạo thêm effect trạng thái |
| Idempotent business outcome | Cùng ý định không giữ/trừ/thu/hoàn thêm lần thứ hai |
| Stable result replay | Cùng key có thể trả quyết định đầu tiên, kể cả từ chối |

Hai lần `SET status="ACTIVE"` có thể để lại cùng giá trị, nhưng nếu mỗi lượt lại gửi email kích hoạt, nghiệp vụ không idempotent. **Lặp an toàn phải xét cả các side effects liên quan**, không chỉ một field trong database.

Idempotency cũng không nhất thiết yêu cầu mọi HTTP response có byte giống hệt: API có thể trả kết quả đã lưu hoặc trạng thái hiện tại theo một hợp đồng rõ ràng. Điều không được phép là áp thêm business effect trái với ý định.

## 3. Idempotency khác exactly-once delivery

Trong các hệ phân tán:

- **At-most-once:** tránh giao lặp nhưng có thể mất thông điệp trong một số mô hình lỗi.
- **At-least-once:** retry để tăng khả năng giao, chấp nhận message đến lặp.
- **Exactly-once processing semantics:** một engine có thể bảo đảm trong phạm vi giao dịch/stream cụ thể, không tự bao trùm external payment, email và database khác.

Mục tiêu thường triển khai là **at-least-once delivery + idempotent effect + durable outcome tracking**.

~~~mermaid
flowchart TD
    A["Business intent có ID ổn định"] --> B["Request hoặc message có thể lặp"]
    B --> C["Atomic dedup / conditional check"]
    C --> D{"Intent đã được quyết định?"}
    D -->|Có| E["Trả outcome cũ, hoặc conflict nếu payload khác"]
    D -->|Chưa| F["Áp dụng effect một lần"]
    F --> G["Lưu durable result và khả năng recovery"]
~~~

Một flag `processed=true` chỉ lưu trong RAM không đủ: worker restart hoặc hai instances xử lý đồng thời sẽ không tự chia sẻ trạng thái đáng tin cậy.

## 4. Retry của một ý định khác một ý định mới

~~~text
Request A:
  tenant=t01, reservationId=R1001, SKU-A, quantity=2

Request B:
  tenant=t01, reservationId=R1001, SKU-A, quantity=2
  -> cùng ý định, có thể là retry

Request C:
  tenant=t01, reservationId=R1002, SKU-A, quantity=2
  -> ý định mới, dù hàng và số lượng giống A

Request D:
  tenant=t01, reservationId=R1001, SKU-A, quantity=7
  -> key cũ nhưng payload khác: conflict
~~~

Hai payload giống nhau không tự là duplicate: khách có thể cố ý mua hai đơn tương tự. Một request đến với cùng key nhưng quantity khác không được âm thầm nhận kết quả của quantity cũ như thể đáp ứng yêu cầu mới.

Một định danh nên được phạm vi hóa, ví dụ:

~~~text
(tenantId, operationType, idempotencyKey)
~~~

Không dùng mỗi `userId` làm idempotency key khi một user được đặt nhiều đơn. Không tạo key mới cho mỗi retry. Quy tắc tái sử dụng key giữa các API versions, nghiệp vụ RESERVE/RELEASE hoặc tenant phải được mô tả tường minh.

## 5. Hợp đồng API khi key được sử dụng lại

| Trường hợp | Hành vi nên thiết kế |
|---|---|
| Key mới, payload hợp lệ | Xử lý hoặc ghi nhận intent |
| Key đã có, payload tương đương, outcome đã biết | Trả outcome trước hoặc state theo contract |
| Key đã có, payload khác | Báo conflict, không tạo effect mới |
| Key đã có, công việc còn PENDING | Trả pending hoặc chờ có giới hạn |
| Commit trước đó chưa xác định | Tra outcome và đối soát |
| Key từng dùng nhưng ledger hết TTL | Áp chính sách chống replay theo vòng đời nguồn |

Một HTTP API có thể dùng `409 Conflict` cho key/payload xung đột, `202 Accepted` cho đang xử lý và `200/201` cho kết quả đã ghi; không có một response code duy nhất áp được cho mọi tình huống. Cần ghi rõ behavior trong API contract.

Biết một key không đồng nghĩa có quyền đọc result của người khác. Server vẫn phải xác thực tenant, user và quyền truy cập trước khi trả business outcome.

## 6. Fingerprint ràng buộc key với payload

Lưu thêm fingerprint của **nội dung có ý nghĩa nghiệp vụ**:

~~~json
{
  "tenantId": "t01",
  "operation": "RESERVE",
  "idempotencyKey": "R1001",
  "payload": {
    "sku": "SKU-A",
    "quantity": 2
  }
}
~~~

Một ledger record:

~~~json
{
  "_id": "t01:RESERVE:R1001",
  "tenantId": "t01",
  "operation": "RESERVE",
  "fingerprint": "sha256:<digest>",
  "status": "COMMITTED",
  "resourceId": "R1001",
  "outcome": {
    "kind": "HELD",
    "acceptedQuantity": 2
  }
}
~~~

Fingerprint không nên dựa máy móc vào chuỗi JSON gốc. Nếu thứ tự field đổi mà ý nghĩa giữ nguyên, kết quả nên được xem là cùng payload. Cần **canonicalization**:

1. Xác định trường nào là một phần ý định.
2. Chuẩn hóa SKU/quantity theo schema; không tự ép string `"2"` thành number 2 nếu contract không cho.
3. Phân biệt missing, null và default theo quy tắc.
4. Sắp xếp order lines nếu thứ tự không có ý nghĩa nghiệp vụ.
5. Không để tracing timestamp hoặc network nonce làm fingerprint khác.
6. Chọn phương pháp lưu digest hoặc payload chuẩn hóa đủ để phát hiện conflict đáng tin cậy.

Fingerprint chỉ là công cụ so ý định; nó **không tự cấp quyền**. Nếu ledger lưu response/payload chứa dữ liệu nhạy cảm, cần chính sách lưu trữ, truy cập và retention phù hợp.

## 7. Vì sao check-then-act không đủ khi concurrent?

Hai worker nhận cùng key:

~~~text
Worker A: GET dedup(R1001) -> missing
Worker B: GET dedup(R1001) -> missing
Worker A: decrement stock
Worker B: decrement stock
Worker A: insert dedup
Worker B: insert dedup -> duplicate
~~~

Unique constraint chặn marker thứ hai, nhưng **đã quá muộn** nếu hai phép decrement chạy trước marker. Check-then-act qua nhiều lệnh độc lập tạo race.

Một mô hình an toàn khi database hỗ trợ transaction tương ứng:

~~~text
BEGIN ATOMIC TRANSACTION
  INSERT Intent(R1001) IF ABSENT
  CONDITIONAL UPDATE Stock
  SAVE Outcome
COMMIT
~~~

Nếu hai worker cùng chạm unique key, chỉ một transaction có thể ghi intent hợp lệ. Worker còn lại phải đọc outcome hoặc xử lý transient conflict. Nếu marker và effect ở những nơi không thể commit cùng nhau, cần một data model atomic khác hoặc durable state machine có recovery.

**Đừng nuốt mọi duplicate key rồi trả success.** Cùng key khác fingerprint là conflict.

## 8. Lệnh nào lặp an toàn, lệnh nào không?

| Lệnh/tác động | Khi gọi lặp | Cần lưu ý |
|---|---|---|
| `$set: {status:"ACTIVE"}` | Giá trị cuối thường như cũ | Side effect/event/version có thể lặp |
| `$unset` field | Field vẫn missing | Missing khác explicit null |
| `$addToSet` tag | Không thêm lại giá trị tương đương | Không giải quyết mọi uniqueness của array object |
| `DELETE` record | Record vẫn không tồn tại | Release quota/audit có thể bị gọi thêm |
| `$inc: {stock:-2}` | Trừ nhiều lần | Cần business intent ID |
| `$push` vào array | Thêm phần tử lần nữa | Cần key riêng hoặc đổi thao tác |
| Tạo Order với ID mới | Có thể tạo nhiều đơn | Định danh ổn định và uniqueness |
| Gửi email | Có thể gửi nhiều | Message ID, dedup và policy |
| Thu tiền | Có thể charge nhiều | Provider idempotency và reconcile |

Tính idempotent về trạng thái cũng không có nghĩa retry không tốn chi phí. Nó vẫn có thể tạo thêm read/write load, cache traffic, index updates và tracing events.

## 9. Idempotency và optimistic concurrency giải hai vấn đề khác nhau

Một `SET status="ACTIVE"` lặp có thể idempotent nhưng vẫn **ghi đè** thay đổi mới hơn của một writer khác:

~~~text
T0: Product status=ACTIVE, version=7
A đọc v7, muốn status=INACTIVE
B đọc v7, muốn status=ARCHIVED
A ghi INACTIVE
B ghi ARCHIVED từ snapshot cũ
~~~

Cần điều kiện version/status hiện hành:

~~~javascript
db.products.updateOne(
  {
    _id: "p100",
    tenantId: "t01",
    version: 7,
    status: "ACTIVE"
  },
  {
    $set: { status: "INACTIVE" },
    $inc: { version: 1 }
  }
);
~~~

Nếu version đã thay đổi, `matchedCount=0` yêu cầu đọc lại hoặc trả conflict. Không tự thay expectedVersion bằng version mới để ép ghi đè từ snapshot cũ.

- **Idempotency key:** cùng một ý định không tác động hai lần.
- **CAS/optimistic concurrency:** hai ý định khác nhau không ghi đè sai một thay đổi mới hơn.
- **State machine:** chỉ cho phép các chuyển trạng thái nghiệp vụ hợp lệ.

Ba cơ chế bổ sung nhau, không phải thay thế nhau.

## 10. State machine bảo vệ kết quả nghiệp vụ

Reservation có thể đi qua:

~~~mermaid
flowchart LR
    A["REQUESTED"] --> B["HELD"]
    A --> F["REJECTED"]
    B --> C["CONFIRMED"]
    B --> D["EXPIRED"]
    B --> E["CANCELLED"]
~~~

Một transition có điều kiện:

~~~javascript
db.reservations.updateOne(
  {
    _id: "R1001",
    tenantId: "t01",
    status: "HELD"
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);
~~~

Nếu retry gặp `matchedCount=0`, không được mặc định thất bại hoặc thành công: cần đọc trạng thái và xác định intent hiện tại có đúng là nguyên nhân làm record đã `CONFIRMED` không. Nếu record đã `CANCELLED`, không được làm nó sống lại chỉ vì một message xác nhận cũ bị gửi trễ.

State machine phải quy định các chuyển tiếp hợp lệ và ưu tiên khi `CONFIRM`, `CANCEL`, `EXPIRE` cạnh tranh. Các tác động đi kèm stock/payment phải nằm trong consistency boundary phù hợp.

## 11. Create-only khác upsert

Nếu ứng dụng cần “tạo đơn nếu chưa có, từ chối nếu đã tồn tại”, nên sử dụng create-only cùng khóa duy nhất. Trong MongoDB:

~~~javascript
db.orders.insertOne({
  _id: "ord-1001",
  tenantId: "t01",
  status: "CREATED",
  createdAt: new Date()
});
~~~

Lượt thứ hai với cùng ID bị duplicate key. API có thể đọc đơn cũ, so owner/fingerprint và trả kết quả của ý định cũ.

Ngược lại:

~~~javascript
db.orders.updateOne(
  { _id: "ord-1001" },
  {
    $set: {
      status: "CREATED"
    }
  },
  { upsert: true }
);
~~~

Nếu đơn đã `PAID`, thao tác trên có thể ghi lùi về `CREATED`. **Upsert không đồng nghĩa create-only idempotent.** Nó phù hợp khi nghiệp vụ cho phép cập nhật bản ghi đã tồn tại; không phù hợp nếu mỗi lần create phải giữ nguyên đơn cũ.

Unique index trên `(tenantId, externalOrderId)` bảo vệ uniqueness theo business scope, nhưng chỉ mục unique không tự hiểu payload trùng hay khác.

## 12. Atomic decrement chống oversell nhưng chưa chống duplicate intent

Một pool ban đầu còn 10 chiếc:

~~~javascript
const qty = 2;

const result = db.stockPools.updateOne(
  {
    _id: "pool-SKU-A",
    tenantId: "t01",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      held: qty
    }
  }
);
~~~

Điều kiện `available >= qty` và phép giảm diễn ra trong cùng update document. Nó ngăn hai **ý định khác nhau** cùng trừ làm giá trị âm nếu đều dùng cùng nguồn có thẩm quyền.

Nhưng:

~~~text
Stock available = 10
R1001 giảm 2 -> available = 8, response mất
Retry R1001  -> available = 6
~~~

Hai lần đều qua điều kiện còn đủ hàng. **Conditional decrement bảo vệ capacity, không tự bảo vệ idempotency của R1001**. Cần định danh intent và ghi nhận effect đã áp dụng.

## 13. Result ledger: bảo vệ effect và quyết định

Một bản ghi kết quả:

~~~javascript
{
  _id: "t01:RESERVE:R1001",
  tenantId: "t01",
  operation: "RESERVE",
  fingerprint: "digest...",
  status: "COMMITTED",   // hoặc REJECTED / PENDING
  resourceId: "R1001",
  outcome: {
    kind: "HELD",
    acceptedQuantity: 2
  },
  createdAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

Có hai hợp đồng thường gặp:

- **Effect ledger:** bảo đảm cùng intent chỉ áp dụng effect một lần. Retry có thể đọc trạng thái hiện tại của resource.
- **Result ledger:** ghi cả quyết định đầu tiên (ví dụ HELD hoặc OUT_OF_STOCK) để replay cùng key trả outcome tương đương lần đầu.

Điểm khác biệt quan trọng: nếu lần đầu không đủ hàng và trả `REJECTED`, sau đó kho được nhập thêm, retry với cùng key có được chuyển sang `HELD` không? Nếu contract yêu cầu **same intent, same decision**, phải lưu cả REJECTED và không thay đổi quyết định vì dữ liệu sau này khác đi. Nếu sản phẩm muốn cho phép “thử mua lại khi có hàng”, cần tạo **ý định/attempt mới** hoặc công bố một contract khác.

Idempotency không có nghĩa mọi lỗi đều phải được cache vĩnh viễn: validation/permission errors, lỗi kỹ thuật transient và business rejection phải được phân loại và có retention riêng.

## 14. MongoDB: dedup và stock trong cùng transaction

Nếu intent ledger, stock và reservation nằm ở các document khác nhau, muốn bảo vệ invariant giữa chúng phải có consistency boundary phù hợp. MongoDB hỗ trợ multi-document transactions trên những topology đã được hỗ trợ.

Mô hình:

~~~text
BEGIN TRANSACTION
  intent = find intent by unique (tenant,operation,key)
  if exists:
      if fingerprint mismatch:
          return IDEMPOTENCY_CONFLICT
      else:
          return stored outcome

  insert unique intent(key,fingerprint,status=DECIDING)
  conditional update Stock if available >= quantity

  if stock matched:
      insert Reservation with stable ID
      update intent outcome=HELD, status=COMMITTED
  else:
      update intent outcome=OUT_OF_STOCK, status=REJECTED

COMMIT
~~~

Nếu muốn lưu cả kết quả từ chối, transaction cần **commit ledger REJECTED mà không thay stock**. Không ném exception làm rollback mọi thứ rồi tưởng đã lưu được quyết định.

Hai transaction cùng key có thể cùng không thấy ledger lúc đọc, nhưng **unique key và conflict handling** ngăn cả hai commit ledger độc lập. Bên thua đọc lại outcome sau khi transaction thắng hoàn tất, kiểm tra fingerprint và trả kết quả phù hợp.

### 14.1. Pseudocode ngắn cho handler

~~~javascript
// Pseudocode; runAtomicTransaction, findIntent, reserveStock
// là abstraction minh họa, KHÔNG phải MongoDB driver methods.
async function reserveOnce(db, command) {
  const intentKey = [
    command.tenantId, "RESERVE", command.reservationId
  ].join(":");
  const fp = canonicalFingerprint(command);

  return await db.runAtomicTransaction(async (tx) => {
    const old = await tx.findIntent(intentKey);

    if (old) {
      return old.fingerprint === fp
        ? old.outcome
        : { kind: "IDEMPOTENCY_CONFLICT" };
    }

    await tx.insertIntent({
      key: intentKey,
      fingerprint: fp,
      state: "DECIDING"
    });

    const reserved = await tx.reserveStockIfAvailable({
      poolId: command.poolId,
      quantity: command.quantity
    });

    const outcome = reserved
      ? { kind: "HELD", id: command.reservationId }
      : { kind: "OUT_OF_STOCK" };

    if (reserved) {
      await tx.insertReservation({
        id: command.reservationId,
        poolId: command.poolId,
        quantity: command.quantity,
        status: "HELD"
      });
    }

    await tx.saveIntentDecision(intentKey, outcome);
    return outcome;
  });
}
~~~

Để triển khai thật với MongoDB, dùng session/`withTransaction`, `insertOne`, `updateOne` với `$gte/$inc`, unique index và xử lý duplicate/write conflict/unknown commit. Mọi thao tác liên quan phải dùng **cùng session**, đồng thời kiểm tra tenant, payload, quantity, uniqueness và business state. Đoạn pseudocode không thể copy chạy như driver API.

**Không gọi payment/email bên trong transaction callback**: một số helper có thể retry callback do transient conflict. ID/payload phải ổn định giữa các lần retry và side effect ngoài DB được điều phối riêng.

## 15. Vì sao một marker PENDING riêng chưa đủ?

Thiết kế dễ mắc lỗi:

~~~text
1. INSERT Intent(R1001,PENDING)
2. DECREMENT stock by 2
3. UPDATE Intent(R1001,COMMITTED)
~~~

Nếu worker crash sau bước 1, có thể chưa trừ stock. Nếu crash sau bước 2, stock đã trừ nhưng ledger vẫn PENDING. Worker mới không thể chỉ nhìn PENDING rồi quyết định **có được trừ lại** không.

Những hướng thay thế:

- Gắn intent và effect trong cùng atomic aggregate/transaction.
- Dùng durable movement ledger mà việc ghi movement là nguồn chuẩn cho tính available.
- Dùng state machine có các bước recoverable, mỗi bước mang ID riêng và được kiểm soát bởi condition/version.
- Dùng Saga có compensation idempotent và reconciliation.
- Dùng một hệ giao dịch khác có phạm vi bảo đảm phù hợp.
- Thiết kế escrow quota hoặc phân bổ quyền cấp phát trước nếu hot key là điểm nghẽn.

**Hai lệnh atomic riêng rẽ không tự tạo atomicity xuyên chúng**. Phải mô tả rõ crash windows và cách xác định “effect đã áp dụng chưa”.

## 16. Redis: script vừa dedup vừa sửa counter

Nếu quota và dấu intent ở **cùng phạm vi atomic execution** của Redis, có thể dùng Lua script minh họa:

~~~lua
-- KEYS[1]: hash quota với fields available, held
-- KEYS[2]: hash intentId -> outcome
-- ARGV[1]: intentId
-- ARGV[2]: positive integer quantity

local intentId = ARGV[1]
local qty = tonumber(ARGV[2])

if not qty or qty < 1 or qty % 1 ~= 0 then
  return redis.error_reply("INVALID_QUANTITY")
end

local old = redis.call("HGET", KEYS[2], intentId)
if old then
  -- Production: phải kiểm tra fingerprint/payload.
  return old
end

local available = tonumber(
  redis.call("HGET", KEYS[1], "available")
)
if not available or available < qty then
  redis.call("HSET", KEYS[2], intentId, "REJECTED")
  return "REJECTED"
end

redis.call("HINCRBY", KEYS[1], "available", -qty)
redis.call("HINCRBY", KEYS[1], "held", qty)
redis.call("HSET", KEYS[2], intentId, "HELD")
return "HELD"
~~~

Lượt chạy sau với cùng intent ID sẽ thấy outcome và không trừ thêm. Nhưng đây là mẫu **chưa đủ cho production**: cần fingerprint, validation kiểu số/overflow, retention, giới hạn kích thước hash, action RELEASE/CONFIRM và chính sách khôi phục.

Một script atomic không tự bảo đảm **durability qua failover**, vì persistence (AOF/RDB), fsync, replication và ACK còn có semantics riêng. Với Redis Cluster, các keys trong một script cần tuân thủ giới hạn hash slot; có thể dùng cùng hash tag khi mô hình phù hợp.

Nếu Redis là cache có thể mất/evict, không dùng một dedup marker chỉ ở Redis để bảo vệ việc charge/ghi kho tại một database giao dịch khác mà không có cơ chế durable ở nguồn.

## 17. DynamoDB: condition và transactional write

Một intent item chỉ được tạo khi chưa tồn tại:

~~~text
PutItem(
  TableName = "Idempotency",
  Item = {
    PK:"TENANT#t01",
    SK:"RESERVE#R1001",
    fingerprint:"..."
  },
  ConditionExpression = "attribute_not_exists(PK)"
)
~~~

Đây là pseudocode, không phải payload SDK đầy đủ. Nếu condition thất bại, caller phải đọc lại item, so fingerprint và xác định outcome, thay vì trả success mù quáng.

Nếu effect cập nhật một Stock item khác, **conditional PutItem intent rồi UpdateItem stock riêng** vẫn có crash window. Cần `TransactWriteItems` trong phạm vi được hỗ trợ, hoặc một mô hình atomic/state machine phù hợp. Khi thiết kế phải xác nhận giới hạn item/request, transaction conflicts, region scope, idempotency token, read consistency và durability.

Một **client transaction token** của API có thể có cửa sổ/semantics riêng. Nó không nhất thiết thay thế business key gắn với vòng đời Order và khả năng replay sau nhiều ngày.

## 18. Cassandra/ScyllaDB: LWT và CREATE-only theo khóa

Cassandra/ScyllaDB thường xử lý CQL `INSERT` theo semantics upsert. Một bảng intents:

~~~sql
CREATE TABLE reservation_intents_by_tenant (
  tenant_id text,
  reservation_id text,
  pool_id text,
  quantity int,
  fingerprint text,
  status text,
  PRIMARY KEY ((tenant_id), reservation_id)
);
~~~

Tạo có điều kiện khi engine/phiên bản hỗ trợ:

~~~sql
INSERT INTO reservation_intents_by_tenant
  (tenant_id, reservation_id, pool_id, quantity,
   fingerprint, status)
VALUES
  ('t01','R1001','pool-SKU-A',2,'digest...','PENDING')
IF NOT EXISTS;
~~~

LWT/conditional write giúp tránh hai insert cạnh tranh tại cùng key theo phạm vi bảo đảm. **Nhưng tạo intent ở partition này rồi sửa stock ở partition khác không tự thành một transaction ACID hai partition.** CQL batch cũng không phải công cụ chung thay cho transaction đa partition tùy ý.

Cần thiết kế state machine, reconciliation và conditional transitions, hoặc biến đổi mô hình để invariant nằm trong phạm vi atomic được hỗ trợ. Khi timeout, kết quả CQL có thể chưa rõ ở phía caller; không được giả định chưa áp dụng.

## 19. Retryable writes của driver khác idempotency ở API

Một số driver/database hỗ trợ **retryable writes** cho những operation nhất định, kèm session/statement identity và retention của giao thức. Chúng có thể giảm rủi ro áp lại thao tác trong **phạm vi engine**, nhưng không tự bảo vệ:

- Một endpoint chạy nhiều lệnh database không cùng transaction.
- Một request mới có business ID khác.
- Payment, email, search hoặc một hệ khác.
- Message redelivery ngoài session của driver.
- Một callback do ứng dụng tự chạy lại với side effect khác.
- Một idempotency contract cần tồn tại nhiều ngày/tháng.

Muốn “giữ hàng một lần cho R1001”, business key và outcome là yêu cầu độc lập với cơ chế retry ở tầng driver.

## 20. HTTP method và tính lặp an toàn

| Method | Ý nghĩa thường gặp | Lưu ý |
|---|---|---|
| `GET` | Đọc, không chủ ý tạo side effect nghiệp vụ | Tracking/logging cần phân biệt |
| `PUT` | Đặt representation tại URI | Được thiết kế idempotent ở hiệu ứng mong muốn |
| `DELETE` | Yêu cầu xóa | Không được hoàn quota thêm lần khi gọi lại |
| `POST` | Tạo/process một command | Không idempotent mặc định; cần key nếu retry |
| `PATCH` | Thay đổi một phần | `set` khác `increment` về khả năng lặp |

~~~http
POST /v1/reservations
Idempotency-Key: R1001
Content-Type: application/json

{
  "poolId": "pool-SKU-A",
  "quantity": 2
}
~~~

Một `DELETE /reservations/R1001` có thể được gọi hai lần. Nếu lần đầu chuyển HELD→CANCELLED và hoàn 2 chiếc, lần hai không được hoàn tiếp. HTTP method idempotent không cứu được handler nội bộ `stock += 2` không điều kiện.

Tương tự, hai lần PUT cùng representation có thể để lại cùng product, nhưng nếu mỗi lượt phát email hoặc tăng `version` bất kể trạng thái, cần xác định đó là side effect được phép hay phải dedup theo business intent.

## 21. Inbox: xử lý message được giao lại

Nếu broker phát `OrderConfirmed(evt-101)`, consumer cập nhật projection thành công nhưng mất ACK, broker có thể giao lại event:

~~~text
Broker -> Consumer: evt-101
Consumer -> DB: apply projection
Consumer -> Broker: ACK (lost)
Broker -> Consumer: evt-101 again
~~~

Một **Inbox** lưu event ID trong cùng transaction với tác động trên projection:

~~~text
BEGIN LOCAL TRANSACTION
  INSERT Inbox(evt-101) IF ABSENT
  UPDATE projection
COMMIT
ACK broker
~~~

Nếu Inbox và projection nằm ở hai hệ không có transaction chung, vẫn có crash window; cần idempotent target operation hoặc một recovery protocol. ACK sau commit giúp không mất effect, nhưng không ngăn broker phát lại. **Consumer phải chịu được redelivery.**

Phân biệt:

| Định danh | Vai trò |
|---|---|
| Event ID | Nhận diện một event đã xử lý |
| Aggregate ID | Xác định thực thể Order/Product |
| Aggregate version | Bảo vệ thứ tự cập nhật |
| Business intent ID | Nhận diện yêu cầu của khách |
| Trace ID | Quan sát một attempt, có thể thay mỗi lần retry |

Event ID khác nhau không có nghĩa phiên bản mới hơn. Nếu projection đã cập nhật version 12, event version 11 tới trễ không được ghi lùi trạng thái. Với snapshot events, một guard version có thể đủ; với delta events cần đủ từng bước, phải buffer/replay các sequence còn thiếu thay vì bỏ qua mọi version thấp tùy tiện.

## 22. Outbox: ghi business change và event cùng transaction

Nếu service commit Order CONFIRMED rồi crash trước khi gửi event, một consumer có thể không biết Order đã đổi. **Transactional Outbox** xử lý:

~~~text
BEGIN LOCAL TRANSACTION
  UPDATE Order -> CONFIRMED
  INSERT OutboxEvent(
    eventId=evt-order-1001-v3,
    aggregateId=ord-1001,
    version=3
  )
COMMIT

Publisher đọc outbox rồi gửi tới broker.
Consumer dùng Inbox/event ID và version guard.
~~~

Publish thành công nhưng publisher mất ACK có thể khiến event được gửi lại. Do đó outbox không tự đảm bảo phát đúng một lần; **consumer idempotent** là một phần thiết kế. Đồng thời cần xử lý outbox backlog, poison messages, retention và replay.

Không gọi email hoặc payment provider trực tiếp trong database transaction callback có thể được retry. External effects có ID và cơ chế idempotency riêng.

## 23. Payment: bên ngoài transaction database

Ví dụ:

~~~text
1. paymentAttemptId = pay-1001-1
2. Gọi payment provider authorize với ID ổn định
3. Provider đã authorize
4. Response timeout trước khi ứng dụng nhận được
~~~

Gửi lại với ID mới có thể tạo thêm authorization/charge. Nếu provider hỗ trợ idempotency key, phải giữ **cùng ID, cùng payload** theo hợp đồng provider; thời hạn provider lưu key có thể có giới hạn.

~~~mermaid
flowchart TD
    A["PAYMENT_PENDING"] --> B["AUTHORIZING"]
    B --> C{"Provider outcome?"}
    C -->|Authorized| D["AUTHORIZED"]
    C -->|Declined| E["DECLINED"]
    C -->|Unknown| F["RECONCILING"]
    F --> G["Query by paymentAttemptId / webhook"]
    G --> C
~~~

Nguyên tắc: lưu durable paymentAttemptId trước khi gọi, đối soát khi timeout, dedup webhook theo provider event ID, kiểm tra amount/currency/order và dùng action IDs riêng cho capture/refund/void. Không suy exactly-once end-to-end chỉ từ idempotency ở database.

## 24. Cancel, Expire và Confirm phải cạnh tranh an toàn

Một reservation đang giữ 2 chiếc có thể:

~~~text
HELD -> CONFIRMED: không release
HELD -> CANCELLED: release 2 once
HELD -> EXPIRED: release 2 once
~~~

Nếu Cancel và Expire cùng xử lý, không được cả hai hoàn 2 chiếc. Cần điều kiện current status và business effect trong một consistency boundary:

~~~text
IF reservation.status == HELD:
    transition to CANCELLED
    stock.available += quantity
    stock.held -= quantity
ELSE:
    return existing/current outcome
~~~

Nếu Stock và Reservation ở hai document không có transaction, cần release ledger hoặc state machine có recovery, không phải hai update độc lập thiếu đối soát.

**TTL không tự hoàn quota.** TTL xóa record theo cơ chế database và có thể chậm. Một Expire worker nên ghi nhận transition có điều kiện, hoàn stock một lần rồi mới dọn record theo retention. Record bị TTL xóa trước có thể làm mất thông tin quantity cần hoàn hoặc tạo notification lặp.

## 25. Last-write-wins không hiểu trình tự nghiệp vụ

~~~text
10:00 Order HELD
10:01 Order CONFIRMED
10:02 Event HELD cũ phát lại và ghi timestamp mới
~~~

Nếu handler chỉ SET status không điều kiện, Order có thể trở về HELD. **Last-write-wins (LWW)** là cơ chế xử lý xung đột của một số mô hình dữ liệu, không tự hiểu trạng thái payment/fulfillment.

Dùng allowed transitions, CAS theo version/current state, aggregate sequence và quy tắc xử lý out-of-order. Không tự lấy wall-clock timestamp mới của replay làm bằng chứng business event mới hơn.

## 26. Retention idempotency key và nguy cơ replay muộn

Nếu ledger xóa key sau 5 phút nhưng queue phát lại event sau 2 giờ, key cũ có thể được xem là mới. Retention phải xét:

- Retry của HTTP client, load balancer và job worker.
- Queue retention, replay archive và disaster recovery.
- Vòng đời Reservation, Order, Cancel, Expire, Refund.
- Provider idempotency retention và các webhook chậm.
- Unique resource ID còn tồn tại hay có thể tái sử dụng.
- Yêu cầu bảo mật, pháp lý và dữ liệu cá nhân.

Không có TTL phù hợp mọi hệ. Nếu không thể giữ ledger vĩnh viễn, cần stable business resource identity, retention đủ dài hoặc version/epoch namespace rõ ràng để chặn ý định cũ bị tái xử lý.

## 27. Hai loại cạnh tranh phải kiểm thử riêng

**Cùng intent ID:**

~~~text
Worker A: R1001 quantity=2
Worker B: R1001 quantity=2
Expected: only one stock hold
~~~

**Khác intent ID nhưng cùng stock pool:**

~~~text
Available=10
Worker A: R1001 quantity=7
Worker B: R1002 quantity=7
Expected: not both accepted
~~~

**Cùng intent ID, khác payload:**

~~~text
Worker A: R1001 quantity=2
Worker B: R1001 quantity=7
Expected: one fingerprint wins, other conflicts
~~~

Một unique dedup key chống cùng ý định lặp, còn conditional stock update bảo vệ nguồn hàng giữa những ý định khác nhau. Hai lớp không thay thế nhau.

## 28. Phân loại lỗi trước khi retry

| Quan sát | Có chắc effect chưa xảy ra? | Xử lý |
|---|---|---|
| Validation failure trước ghi | Thường có | Sửa input |
| Conditional check failed | Lệnh đó không áp effect | Đọc state/result |
| Duplicate key, same fingerprint | Có record cùng key | Tra outcome |
| Duplicate key, payload khác | Conflict | Từ chối |
| Transaction abort đã xác nhận | Chưa commit transaction | Retry có budget |
| Network timeout trước ACK | **Không chắc** | Query outcome / commit protocol |
| Broker redelivery | Có thể đã xử lý | Inbox + version |
| Provider timeout | Có thể đã charge | Reconcile theo attempt ID |
| Crash giữa non-atomic writes | Có thể trạng thái một phần | Durable workflow / repair |
| Retry budget exhausted | Vẫn có thể unknown | Pending/reconciliation |

Không dùng tình trạng `timeout` làm bằng chứng transaction rollback. Một kết quả chưa biết cần được mô hình hóa thay vì tự quyết định “thất bại” hoặc “thành công”.

Retry transient conflicts phải có **exponential backoff, jitter và giới hạn tổng số lần/thời gian**. Business rejection như hết hàng hoặc không đủ quyền không nên được retry vô hạn.

## 29. Replay outcome cũ hay trả trạng thái mới nhất?

Có ba lựa chọn hợp lệ nếu được công bố:

1. **Stored response:** trả lại kết quả/status/body của lần đầu.
2. **Stored business decision:** trả HELD/REJECTED gắn với intent, có thể thêm metadata mới.
3. **Current resource state:** retry Reserve trả trạng thái hiện tại, có thể đã CONFIRMED.

Ví dụ Reserve HELD lúc 10:00, thanh toán lúc 10:01, retry Reserve lúc 10:02. Cả trả HELD cũ hoặc CONFIRMED hiện tại đều có thể đáp ứng idempotency **nếu không trừ thêm stock** và API contract rõ.

Khi lưu response cũ cần cân nhắc dữ liệu nhạy cảm, tenant access, API schema evolution, header, trace ID và thời gian lưu. Idempotency không đơn giản là cache HTTP response vô thời hạn.

## 30. Quan sát vận hành: đếm ý định, không chỉ request

| Metric | Giải thích |
|---|---|
| New intents/sec | Số ý định mới |
| Attempts per intent | Mức độ retry/redelivery |
| Dedup hit rate | Tỷ lệ request được nhận diện là lặp |
| Key/payload conflicts | Lỗi tái sử dụng ID sai |
| Pending intent age | Các yêu cầu có kết quả chưa rõ |
| Business effects | Số hold/charge/release thực sự |
| Conditional conflicts | Các ý định khác nhau tranh resource |
| Transaction abort | Lỗi hạ tầng/concurrency |
| Inbox/Outbox lag | Độ trễ đồng bộ event |
| Reconciliation backlog | Số intent chưa quyết định |
| p50/p95/p99 new vs duplicate | Tác động độ trễ khi xử lý mới/lặp |
| Ledger retention/TTL | Nguy cơ replay sau dọn dữ liệu |

Một intent có 5 HTTP attempts và chỉ một stock hold là kết quả mong muốn, không phải hiệu suất thấp do “chỉ một lần thành công”. Log nên dùng business ID/correlation ID phù hợp, không ghi thông tin nhạy cảm không cần thiết. Không gộp business rejection vì hết hàng với technical abort do database.

## 31. Runbook khi intent bị kẹt PENDING hoặc UNKNOWN

Một `reservationId=R1001` được ghi PENDING quá lâu. Không nên sửa bằng cách “gửi lại tất cả lệnh” vì effect trước đó có thể đã xảy ra.

1. **Nhận diện:** tenant, operation, intent ID, payload fingerprint, thời điểm và attempt IDs.
2. **Đọc nguồn chuẩn:** intent ledger, Reservation, stock movements, Order và payment provider nếu có.
3. **Phân loại:** đã commit, đã reject, đang xử lý hợp lệ, hoàn tất một phần hoặc chưa rõ.
4. Nếu **đã commit**, ghi/khôi phục kết quả và bảo đảm retry không tạo effect thứ hai.
5. Nếu **chưa thực hiện**, tiếp tục bằng cùng business key và protocol an toàn.
6. Nếu **một phần**, dùng compensation/recovery có điều kiện và action ID riêng.
7. Nếu **payment UNKNOWN**, tra theo paymentAttemptId và đối soát, không charge hoặc refund mù.
8. Sau khắc phục, kiểm tra invariants: available không âm, held/released hợp lý, không có duplicate.
9. Ghi nguyên nhân như ACK lost, race, TTL dedup ngắn, code cũ hoặc transaction không atomic.
10. Bổ sung alert pending age, retry budget và bài thử fault injection tái hiện.

Không cộng stock thủ công chỉ vì số available “thấp hơn dự đoán”: có thể đang có những Reservation hợp lệ khác. Cần ledger của các movement/intent và người chịu trách nhiệm xử lý khi kết quả không thể kiểm chứng.

## 32. Thực nghiệm A — 100 attempts cùng một intent

Trong database thực hành, tạo pool với `available=100`, sau đó gửi 100 request đồng thời, đều có cùng payload:

~~~json
{
  "tenantId": "t01",
  "reservationId": "R1001",
  "poolId": "pool-SKU-A",
  "quantity": 2
}
~~~

Kỳ vọng sau khi mọi tác vụ được xử lý/đối soát:

~~~text
holds applied for R1001 = 1
stock.available = 98
stock.held increased by 2
one durable business outcome for R1001
every repeated attempt creates no further stock effect
~~~

Không bắt buộc cả 100 HTTP responses đều 200; có thể có pending, conflict transient hoặc timeout. Điều quan trọng là **effect nghiệp vụ và nguồn dữ liệu chuẩn**.

Gửi tiếp 20 request cùng `R1001` nhưng `quantity=7`. Chúng phải nhận fingerprint conflict, không được có thêm hold 7 hoặc bị báo đã giữ 7 khi thực tế chỉ giữ 2.

### 32.1. Mất response sau commit

Giả lập DB commit thành công nhưng ngắt kết nối trước ACK. Retry bằng cùng key. Đọc ledger, Reservation và Stock; kiểm tra không trừ thêm. Nếu không thể biết commit đã hay chưa, thiết kế còn thiếu outcome-tracking/recovery protocol.

## 33. Thực nghiệm B — 100 intents khác nhau trên 10 sản phẩm

Tạo 100 reservation IDs khác nhau, mỗi ID giữ 1 sản phẩm, stock ban đầu 10:

~~~text
for i = 1..100 concurrently:
    reserve(
      reservationId = "R-" + i,
      poolId = "pool-SKU-A",
      quantity = 1
    )

after settlement:
    assert availableStock >= 0
    assert totalHeldAndConfirmed <= 10
    assert each reservationId has at most one effect
~~~

Khác thí nghiệm A, một unique dedup key cho mỗi intent **không đủ ngăn oversell**. Nguồn stock phải bảo vệ điều kiện còn hàng với atomic update/transaction hoặc mô hình quota khác được chứng minh đúng.

Đo offered load, achieved throughput, p50/p95/p99, business rejections, transaction aborts, retries và duplicate rate. Hết hàng là kết quả nghiệp vụ có thể đúng; lỗi write conflict/timeout là tình huống kỹ thuật cần xử lý riêng.

## 34. Thực nghiệm C — Fault injection và event đến sai thứ tự

| Tình huống | Bất biến cần xác nhận |
|---|---|
| HTTP response mất sau DB commit | Retry không tạo effect thứ hai |
| Worker crash sau marker nhưng trước effect | Recovery không bỏ ý định |
| Worker crash sau effect nhưng trước outcome | Có cách xác định đã áp và sửa ledger |
| Hai worker cùng ID và payload | Một outcome duy nhất |
| Hai worker cùng ID, payload khác | Chỉ một fingerprint hợp lệ, bên kia conflict |
| Broker redeliver `OrderConfirmed` | Không confirm/fulfill thêm |
| Event version 12 đến trước version 11 | Không ghi lùi projection |
| Cancel cùng lúc Expire | Chỉ release một lần |
| Payment provider timeout sau success | Không charge lặp |
| Cache dedup bị eviction/TTL | Nguồn bền vẫn chống replay |
| Replica failover hoặc restore | Outcome và effect phù hợp RPO được công bố |
| Worker V1 xử lý message cũ sau deploy | Không làm lùi trạng thái mới |

Fault injection cần môi trường thử nghiệm có thể gián đoạn và khôi phục, không chạy tự phát trên production. Mỗi tình huống phải kiểm tra kết quả từ nguồn có thẩm quyền, không chỉ một HTTP status.

## 35. Bài tập thiết kế: giữ vé và thanh toán

**Bối cảnh:** Nền tảng bán 1.000 vé, mỗi người giữ 1–4 vé tối đa 5 phút. Có hai loại vé, một payment provider bên ngoài và message broker để gửi thông báo.

### A. Identity và response contract

1. Thiết kế `reservationId`, `paymentAttemptId`, `releaseId` và `eventId`.
2. Chọn phạm vi tenant/event/operation của idempotency key.
3. Định nghĩa fingerprint và xử lý danh sách vé thay thứ tự.
4. Nêu response khi key cũ nhận payload khác.
5. Quyết định có lưu OUT_OF_STOCK như kết quả cố định không.

### B. Invariant và atomic boundary

1. Viết quan hệ giữa capacity, available, held, confirmed.
2. Thiết kế conditional decrement ngăn oversell.
3. Phân tích crash window khi dedup marker và stock effect tách rời.
4. Thiết kế ledger + effect trong transaction/aggregate phù hợp.
5. Nếu hai loại vé thuộc hai database, chọn Saga/reconciliation và mô tả trạng thái trung gian.

### C. Cancel/Expire/Payment

1. Vẽ transitions REQUESTED → HELD → CONFIRMED/CANCELLED/EXPIRED.
2. Cho Cancel và Expire chạy song song, chứng minh chỉ release một lần.
3. Thiết kế cách dùng stable paymentAttemptId khi provider timeout.
4. Dedup webhook và xử lý event out-of-order.
5. Khi provider đã capture nhưng Order chưa xác nhận, mô tả đối soát/void/refund.

### D. Kiểm thử và vận hành

1. Chạy 100 attempts cùng key và 100 keys khác nhau trên một pool nhỏ.
2. Đo idempotency hit rate, pending age và số business effects thật.
3. Xác định retention ledger dựa trên queue replay và business lifecycle.
4. Viết runbook xử lý Reservation PENDING quá deadline.
5. Tạo fault-injection test cho tình huống commit thành công nhưng response mất.

## 36. Những ngộ nhận phổ biến

| Ngộ nhận | Vấn đề | Cách phòng tránh |
|---|---|---|
| Driver retryable write làm API idempotent | Không bao phủ nhiều lệnh và external side effects | Business key + durable outcome |
| SET cùng giá trị là đủ | Có thể phát event/email lặp | Xác định business outcome đầy đủ |
| Có unique marker là hết race | Effect trên record khác vẫn có crash window | Atomic boundary/recovery |
| GET missing rồi INSERT là an toàn | Hai worker đều có thể thấy missing | Unique/conditional insert |
| Conditional decrement không thể lặp | Một intent có thể trừ nhiều lần khi còn hàng | Dedup theo intent |
| Payload giống nhau nghĩa cùng ý định | Có thể là hai đơn riêng | Stable intent ID |
| Key cũ khác payload vẫn trả success | Che xung đột về số lượng/nội dung | Fingerprint check |
| Timeout nghĩa rollback | Write có thể đã commit | Query/reconcile |
| Event ID cũng là ordering sequence | Dedup không chặn event cũ ghi đè | Aggregate version |
| Outbox là exactly-once delivery | Publisher có thể gửi lại | Inbox/idempotent consumer |
| TTL xóa hold sẽ tự hoàn stock | Chưa có business compensation | Conditional transition |
| Redis atomic script là durable qua mọi lỗi | Persistence/replication khác atomicity | Kiểm chứng contract |
| Lease TTL loại bỏ worker stale | Worker cũ có thể tiếp tục ghi | Fencing/CAS ở nguồn |
| LWW tự bảo vệ trạng thái đã thanh toán | Timestamp không hiểu nghiệp vụ | State machine/version |
| TTL dedup vài phút đủ mọi replay | Event có thể đến nhiều giờ sau | Retention theo vòng đời |
| HTTP DELETE tự hoàn quota đúng một lần | Implementation có thể cộng quota lặp | Release ledger |
| Payment trong transaction sẽ rollback cùng DB | Provider không cùng transaction | Workflow/idempotency riêng |

## 37. Câu hỏi tự kiểm tra

1. Idempotent state khác trả cùng response bytes ra sao?
2. Vì sao hai request giống payload chưa chắc cùng ý định?
3. Key vì sao cần scope tenant và operation?
4. Fingerprint nên dùng canonical representation như thế nào?
5. Vì sao check-then-act không atomic tạo race?
6. Unique key chống duplicate nhưng vì sao chưa chống oversell?
7. `$set` và `$inc` khác nhau khi retry như thế nào?
8. CAS/version ngăn lost update nhưng có tự chống duplicate intent không?
9. Vì sao một result ledger có thể cần lưu cả REJECTED?
10. Crash giữa marker PENDING và decrement gây trạng thái nào?
11. Redis dedup key hết TTL sẽ gây nguy cơ gì?
12. Cassandra IF NOT EXISTS có tạo atomicity đa partition không?
13. Driver transaction token khác business ID ở vòng đời nào?
14. Inbox và Outbox giải quyết các bước khác nhau ra sao?
15. Event ID và aggregate version phục vụ những mục tiêu gì?
16. Vì sao paymentAttemptId phải giữ ổn định qua timeout?
17. Cancel và Expire làm sao tránh release hai lần?
18. TTL có phải business timer chính xác không?
19. Network timeout có chứng minh commit chưa xảy ra không?
20. API nên trả stored decision hay current state khi replay?
21. Vì sao test cùng key khác test nhiều key trên cùng pool?
22. Những metric nào đếm intent so với attempts?
23. Vì sao cần phân biệt business rejection với transaction abort?
24. Đến khi nào có thể xóa ledger idempotency cũ?
25. Một runbook xử lý UNKNOWN phải tìm dữ liệu từ nguồn nào?

## 38. Tổng kết

**Thao tác có thể thực hiện lặp an toàn** nghĩa là cùng một **ý định nghiệp vụ** không tạo thêm tác động trái hợp đồng dù request, message hoặc worker chạy nhiều lần. Việc này đòi hỏi intent ID ổn định, payload fingerprint, bảo vệ uniqueness và state, cùng durable outcome để phân biệt **chưa thực hiện, đã thực hiện và chưa thể xác định**.

Các nguyên tắc trọng tâm:

- **Idempotency key + fingerprint** phân biệt retry với yêu cầu mới hoặc payload bị thay.
- **Conditional update/CAS** bảo vệ invariant khi các ý định khác nhau tranh cùng resource.
- **Result ledger và effect** cần cùng consistency boundary khi phải quyết định một lần; nếu không, cần durable workflow, compensation và reconciliation.
- **State machine, aggregate version, Outbox/Inbox** giúp chống phát lại và đảo thứ tự.
- **Payment/external provider** dùng key riêng, không được gọi thiếu kiểm soát trong transaction callback.
- **Retention** bao phủ retry/replay windows và vòng đời nghiệp vụ.
- **Concurrency tests và fault injection** phải kiểm tra effect đã commit chứ không chỉ HTTP status.

Thiết kế đúng không phải thiết kế không bao giờ nhận request trùng. Đó là thiết kế **chấp nhận lặp mà vẫn giữ bất biến, trả quyết định nhất quán, không trừ/hoàn/thu tiền thêm lần nữa và có thể phục hồi sau sự cố**.







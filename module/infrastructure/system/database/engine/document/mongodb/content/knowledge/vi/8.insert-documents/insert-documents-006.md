# Thiết kế thao tác thêm có thể gửi lại mà không tạo dữ liệu trùng trong MongoDB

Trong ứng dụng thực tế, client có thể gửi lại cùng một yêu cầu tạo dữ liệu nhiều lần. Người dùng nhấn nút hai lần; gateway thử lại sau timeout; worker xử lý lại message sau khi khởi động; hoặc database đã ghi thành công nhưng phản hồi bị mất trên đường truyền. Nếu mỗi lần gửi đều chạy `insertOne()` với một `_id` ngẫu nhiên mới, hệ thống có thể tạo hai đơn hàng, hai phiếu thanh toán hoặc hai công việc giống nhau.

Mục tiêu của bài này là thiết kế thao tác **thêm document có tính idempotent**: với cùng một yêu cầu nghiệp vụ, dù được thực thi lặp lại, hệ thống vẫn ghi nhận **một kết quả nghiệp vụ duy nhất**. Để làm được điều đó, cần thiết kế danh tính của yêu cầu, ràng buộc duy nhất ở MongoDB, phân loại lỗi và chiến lược phục hồi sau khi không biết lần ghi trước đã thành công hay chưa.

Bài học dùng MongoDB, **mongosh** và database thử nghiệm `insert_once_lab`. Các ví dụ sử dụng ID chuỗi dễ đọc, không giả định mọi ứng dụng đều phải thay ObjectId bằng chuỗi. Chỉ chạy lệnh ghi/xóa trong môi trường lab do bạn kiểm soát.

## 1. Hiểu rõ vấn đề: một yêu cầu được giao nhiều lần

Một thao tác thêm document điển hình:

~~~javascript
db.orders.insertOne({
  _id: new ObjectId(),
  customerId: "customer-01",
  productId: "sku-001",
  qty: 2,
  createdAt: new Date()
})
~~~

Mỗi lần chạy sẽ tạo `_id` mới, nên dù nội dung nghiệp vụ giống hệt, MongoDB coi đó là **hai document khác nhau**. MongoDB không tự biết đây là một yêu cầu được gửi lại.

### Kịch bản mất phản hồi

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant M as MongoDB
    C->>A: POST /orders, yêu cầu X
    A->>M: insertOne(order)
    M-->>A: Đã ghi thành công
    Note over A,C: Kết nối mất trước khi client nhận phản hồi
    C->>A: Gửi lại yêu cầu X
    A->>M: insertOne(order với _id mới)
    M-->>A: Tạo thêm document thứ hai
    A-->>C: Thành công
~~~

Trong sơ đồ, vấn đề không nằm ở việc MongoDB “ghi trùng cùng `_id`”, mà ở chỗ ứng dụng **phát sinh danh tính mới ở mỗi lần thử**. Khi client mất phản hồi, nó không biết lần đầu đã commit hay chưa; gửi lại là hành vi hợp lý. API phải chịu trách nhiệm nhận diện yêu cầu cũ.

### Những nguồn gây gửi lại

| Nguồn | Tình huống | Rủi ro nếu không chống trùng |
|---|---|---|
| Người dùng | Bấm “Đặt hàng” nhiều lần | Tạo nhiều đơn |
| Client/mobile | Timeout, mạng chuyển Wi-Fi/4G | Gửi lại POST chưa biết kết quả |
| API Gateway | Chính sách retry khi gặp lỗi mạng | Một request vào backend nhiều lần |
| Worker/queue | Message được giao lại sau crash hoặc chưa ack | Xử lý cùng sự kiện nhiều lần |
| Driver | Thử lại một thao tác ghi được hỗ trợ sau lỗi tạm thời | Cần hiểu giới hạn retry của driver |
| Batch importer | Job chạy lại từ checkpoint | Tạo nhiều bản ghi cho cùng source row |
| Webhook | Bên gửi lặp thông báo | Ghi nhiều event/order/payment cho một thông báo |

**Yêu cầu đúng:** “Cùng một ý định tạo” không được tạo thêm hiệu ứng mới khi xử lý lại. Nhưng **hai ý định mới hợp lệ** dù payload giống nhau vẫn có thể tạo hai document. Do đó, không thể chống trùng chỉ bằng cách tìm document có toàn bộ field giống nhau.

## 2. Idempotency nghĩa là gì khi thêm document?

Một thao tác `f` gọi là idempotent nếu lặp lại cùng đầu vào không làm thay đổi kết quả hệ thống sau lần thành công đầu tiên:

\[
f(f(S, K), K) = f(S, K)
\]

Trong đó `S` là trạng thái lưu trữ và `K` là danh tính của một yêu cầu. Đây là mô hình về **hiệu ứng nghiệp vụ**, không nhất thiết nói rằng mọi lần gọi đều trả cùng mã HTTP hoặc chỉ tạo đúng một log kỹ thuật.

Ví dụ với `Idempotency-Key: req-2026-0007`:

| Lần gọi | Key | Ý định | Hành vi mong muốn |
|---|---|---|---|
| 1 | `req-2026-0007` | Tạo đơn cho 2 sản phẩm A | Tạo đúng một đơn |
| 2 | `req-2026-0007` | Gửi lại y hệt | Trả kết quả của đơn đã tạo |
| 3 | `req-2026-0007` | Gửi lại y hệt sau timeout | Vẫn không tạo đơn thứ hai |
| 4 | `req-2026-0007` | Thay thành 3 sản phẩm A | Báo **key đã dùng với nội dung khác** |
| 5 | `req-2026-0008` | Tạo đơn mới cho 2 sản phẩm A | Có thể tạo đơn thứ hai hợp lệ |

Ba điều kiện cần thiết:

1. **Danh tính ổn định:** mỗi ý định tạo có một khóa nhận dạng, giữ nguyên qua các lần gửi lại.
2. **Ràng buộc nguyên tử:** MongoDB ngăn hai thực thi đồng thời ghi hai kết quả cho một danh tính, thường nhờ unique index hoặc `_id`.
3. **Kết quả có thể truy hồi:** khi nhận request lặp, backend đọc trạng thái hoặc phản hồi đã lưu và xử lý đúng trường hợp nội dung không khớp.

### Phân biệt “không tạo trùng” và “trả kết quả y hệt”

Ngăn tạo trùng là mức bảo đảm tối thiểu. API có thể còn cần trả **cùng mã đơn, cùng trạng thái nghiệp vụ đã xác nhận** khi client retry. Nếu muốn trả đúng nguyên trạng phản hồi ban đầu, nên lưu snapshot response hoặc những trường ổn định đủ để dựng lại phản hồi. Đọc order hiện tại có thể trả trạng thái mới (`SHIPPED` thay vì `CREATED`), điều này không giống replay response ban đầu dù dữ liệu không trùng.

API cần công bố hợp đồng rõ: replay trả phản hồi gốc, hay trả resource hiện tại; cả hai có thể hợp lý cho nghiệp vụ khác nhau.

## 3. Những khái niệm cần phân biệt

### 3.1. Retry khác idempotency

**Retry** là gửi lại khi lỗi hoặc chưa biết kết quả. **Idempotency** bảo đảm gửi lại không làm thay đổi nghiệp vụ ngoài ý muốn. Có retry mà không có idempotency là một nguồn gây duplicate; có idempotency giúp retry an toàn hơn.

### 3.2. Unique index khác kiểm tra trước khi insert

Đoạn sau **không an toàn khi chạy đồng thời**:

~~~javascript
if (!db.orders.findOne({ externalOrderId: "cart-123" })) {
  db.orders.insertOne({
    externalOrderId: "cart-123",
    total: 250000
  })
}
~~~

Hai request có thể cùng nhìn thấy “chưa tồn tại”, rồi cùng insert. Nếu không có unique index cho `externalOrderId`, cả hai document có thể được tạo.

Một unique index buộc tính duy nhất ngay tại database:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uq_tenant_external_order" }
)
~~~

Với dữ liệu phù hợp, MongoDB sẽ từ chối thao tác cạnh tranh tạo duplicate key. **Đọc trước** vẫn có thể hữu ích để trả phản hồi nhanh hoặc thông báo thân thiện, nhưng không thay thế ràng buộc database.

### 3.3. Retryable writes của MongoDB không thay thế idempotency của API

MongoDB driver hỗ trợ **retryable writes** trong những cấu hình/topology và loại thao tác được hỗ trợ. Cơ chế này giúp driver thử lại **chính thao tác ghi** sau một số lỗi tạm thời mà không xử lý lần ghi hợp lệ đó hai lần trong phạm vi retryable write.

Tuy nhiên:

- Client có thể gửi **hai HTTP request riêng**, tạo hai thao tác MongoDB khác nhau.
- API có thể sinh `_id` mới mỗi lần HTTP request, dù payload nghiệp vụ là một.
- Retryable writes không bảo đảm “mỗi đơn hàng chỉ được đặt một lần” trên toàn hệ thống.
- Không phải mọi loại thao tác ghi/topology/error đều được retry theo cùng cơ chế.
- Retry ở driver không tự giải quyết side effect ngoài MongoDB như thanh toán hoặc gửi email.

Do đó cần **idempotency ở tầng nghiệp vụ** ngay cả khi connection string bật `retryWrites=true`.

### 3.4. At-least-once delivery và exactly-once effect

Trong hệ thống phân tán, transport có thể giao một message nhiều lần (**at least once**). Thiết kế idempotent giúp đạt mục tiêu **một hiệu ứng nghiệp vụ** đối với yêu cầu có danh tính ổn định. Không nên tuyên bố bảo đảm “exactly once” tuyệt đối qua mọi database, message broker và external API nếu chưa định nghĩa rõ phạm vi, giao thức xác nhận và xử lý lỗi.

## 4. Thiết kế danh tính của yêu cầu thêm

Đây là quyết định đầu tiên, trước khi chọn `insertOne()` hay `upsert`.

### 4.1. Khóa nghiệp vụ ổn định

Nếu hệ thống đã có một khóa nghiệp vụ thực sự duy nhất, nên tận dụng nó:

- `externalOrderId` do hệ thống nguồn cấp cho một đơn.
- `providerEventId` của một webhook.
- `invoiceNumber` duy nhất trong một công ty và kỳ phù hợp.
- `importBatchId + sourceRowId` cho một bản ghi nhập.
- `tenantId + clientRequestId` cho một yêu cầu tạo từ API.

Ví dụ cùng mã hàng có thể xuất hiện nhiều lần trong đơn, nên **`productId` không phải idempotency key cho tạo đơn**. Tương tự, cùng một người có thể đặt hai đơn cùng nội dung vào hai thời điểm khác nhau.

### 4.2. Client-generated key

Với thao tác POST tạo đơn chưa có mã nghiệp vụ, client có thể sinh một khóa khó trùng cho **mỗi lần người dùng bắt đầu một ý định tạo mới**, ví dụ một UUID. Client phải giữ khóa đó khi retry request đang chờ hoặc chưa rõ kết quả.

~~~http
POST /orders HTTP/1.1
Authorization: Bearer <token>
Idempotency-Key: 8e821db3-4b86-4664-9f2d-6ed23e8df13c
Content-Type: application/json

{
  "items": [
    { "productId": "sku-001", "qty": 2 }
  ],
  "shippingAddressId": "address-03"
}
~~~

`Idempotency-Key` là một lựa chọn thiết kế API phổ biến; phía server vẫn phải quy định phạm vi, thời gian tồn tại, nội dung fingerprint và cách trả lỗi. Khóa từ client **không phải bằng chứng quyền truy cập**; tenant/user phải được xác thực độc lập.

### 4.3. Phạm vi uniqueness

Khóa `req-001` của tenant A không nhất thiết cùng yêu cầu với `req-001` của tenant B. Một hợp đồng có thể là:

~~~text
requestIdentity =
  tenantId
  + operationScope (ví dụ "POST /orders")
  + idempotencyKey
~~~

Index tương ứng:

~~~javascript
db.idempotency_requests.createIndex(
  { tenantId: 1, operation: 1, requestKey: 1 },
  {
    unique: true,
    name: "uq_idempotency_scope"
  }
)
~~~

Server phải lấy `tenantId` từ principal đã xác thực, không tin một `tenantId` bất kỳ trong body để cấp quyền. Nếu scope là người dùng thay vì tenant, hoặc một webhook của provider, hãy thay khóa scope theo đúng ranh giới nghiệp vụ.

### 4.4. Fingerprint của payload

Một key không được tùy tiện dùng lại để tạo nội dung khác. Sau khi xác thực và chuẩn hóa request, server tạo fingerprint đại diện cho **những giá trị quyết định nghiệp vụ**:

~~~text
Idempotency identity: tenant-01 / POST /orders / req-007

Payload chuẩn hóa:
  item sku-001, qty 2
  shippingAddressId address-03
  currency VND

Fingerprint:
  SHA-256(canonical representation of operation + payload)
~~~

Khi request trùng key:

- Fingerprint giống: trả kết quả đã lưu hoặc thông báo đang xử lý.
- Fingerprint khác: trả conflict, không tự thay document cũ.

**Canonicalization quan trọng:** thứ tự field JSON, khoảng trắng, kiểu số `2`/`2.0`, thứ tự item, chữ hoa/thường, timezone và các giá trị mặc định có thể gây fingerprint khác dù nghiệp vụ tương đương. Hãy chuẩn hóa theo contract trước khi hash; không hash trực tiếp raw JSON bytes nếu API cho phép nhiều biểu diễn tương đương. Không đưa các giá trị biến động của server như `createdAt: new Date()` vào fingerprint.

Không lưu payload thô chứa thông tin nhạy cảm chỉ để chống trùng nếu lưu fingerprint và metadata là đủ. Fingerprint không thay thế kiểm tra quyền/kiểm soát truy cập.

## 5. Mô hình 1 — Cố định `_id` theo danh tính nghiệp vụ

Đây là giải pháp đơn giản nhất cho thao tác **chỉ tạo một document**.

### 5.1. Thiết lập dữ liệu lab

~~~javascript
use insert_once_lab

db.createCollection("simple_orders")
~~~

Trong MongoDB, mỗi document có `_id`, và collection thông thường có unique index cho `_id`. Thay vì tạo ObjectId mới mỗi lần retry, dùng ID ổn định được server tạo từ khóa nghiệp vụ, hoặc một mã đơn đã cấp ổn định:

~~~javascript
const orderId = "tenant-01:client-order-007"

db.simple_orders.insertOne({
  _id: orderId,
  tenantId: "tenant-01",
  clientOrderId: "client-order-007",
  productId: "sku-001",
  qty: 2,
  payloadFingerprint: "demo-fingerprint-v1",
  status: "CREATED",
  createdAt: new Date()
})
~~~

Chạy lại **cùng lệnh tạo `_id`** sẽ gặp duplicate key thay vì tạo bản thứ hai:

~~~text
MongoServerError: E11000 duplicate key error ...
~~~

Đó là bảo vệ uniqueness, **chưa tự biến lời gọi thứ hai thành phản hồi thành công**. Ứng dụng cần đọc document hiện có, so fingerprint và trả kết quả đúng.

### 5.2. Mẫu xử lý duplicate key

Giả mã logic service:

~~~text
createOrder(request):
  identity = deriveStableIdentity(request)
  fingerprint = canonicalFingerprint(request)
  document = buildOrder(identity, request, fingerprint)

  try:
    insertOne(document)
    return CREATED(document)
  catch error:
    if error is not DuplicateKey:
      propagate error

    previous = findOneByIdentity(identity)
    if previous is missing:
      return RETRYABLE_AMBIGUOUS_RESULT
    if previous.fingerprint != fingerprint:
      return IDEMPOTENCY_KEY_CONFLICT

    return REPLAY(previous)
~~~

**Không nuốt mọi duplicate key như thành công.** Có thể lỗi duplicate do một unique field khác (ví dụ số hóa đơn), không phải do `_id` yêu cầu; cần kiểm tra document theo danh tính cố định và so nội dung nghiệp vụ.

### 5.3. Khi nào mô hình này phù hợp?

- Một request chỉ tạo một document và không cần thay đổi document khác.
- Có khóa nghiệp vụ duy nhất, ổn định và không bị cấp lại sai.
- Có thể truy hồi kết quả từ document đã tạo.
- Document được giữ đủ lâu để nhận diện retry trong thời hạn mong muốn.

Nếu ID trong document là ObjectId nhưng ứng dụng vẫn cần khóa bên ngoài, có thể đặt unique compound index trên `tenantId + externalOrderId` thay vì ép `_id` thành chuỗi.

## 6. Mô hình 2 — `upsert` với `$setOnInsert`

MongoDB hỗ trợ `updateOne(filter, update, { upsert: true })`. Khi không có document khớp, thao tác có thể tạo document; khi đã có, có thể cập nhật document hiện có. Để **chỉ ghi nội dung lúc tạo**, dùng `$setOnInsert`.

### 6.1. Một lần tạo, nhiều lần gửi

~~~javascript
use insert_once_lab

db.createCollection("upsert_orders")
db.upsert_orders.createIndex(
  { tenantId: 1, clientOrderId: 1 },
  { unique: true, name: "uq_client_order_per_tenant" }
)

const identity = {
  tenantId: "tenant-01",
  clientOrderId: "cart-checkout-008"
}

const requestFingerprint = "demo-payload-v1-sku-001-qty-2"

const result = db.upsert_orders.updateOne(
  identity,
  {
    $setOnInsert: {
      productId: "sku-001",
      qty: 2,
      payloadFingerprint: requestFingerprint,
      status: "CREATED",
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(result)
printjson(db.upsert_orders.findOne(identity))
~~~

Lần đầu có thể nhận `upsertedCount: 1`. Những lần sau, filter tìm thấy document; `$setOnInsert` không thay các field của document đã tồn tại. `matchedCount` có thể bằng 1, còn `modifiedCount` thường bằng 0 vì không có cập nhật hữu hiệu.

**Phải kiểm tra fingerprint sau upsert**: cùng `clientOrderId` nhưng khác `qty` không được âm thầm trả thành công như thể request mới đã được xử lý.

~~~javascript
const saved = db.upsert_orders.findOne(identity)

if (!saved) {
  throw new Error("RESULT_NOT_VISIBLE_OR_OPERATION_FAILED")
}

if (saved.payloadFingerprint !== requestFingerprint) {
  throw new Error("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD")
}

printjson({
  orderId: saved._id,
  status: saved.status
})
~~~

Trong lab, fingerprint là chuỗi minh họa. Ứng dụng thật cần tạo fingerprint từ payload đã chuẩn hóa, không chấp nhận chuỗi tùy ý do client khai báo là bằng chứng nội dung trùng.

### 6.2. Vì sao không dùng `$set` trong request replay?

~~~javascript
// KHÔNG phù hợp để replay việc "chỉ tạo một lần".
db.upsert_orders.updateOne(
  identity,
  {
    $set: {
      status: "CREATED",
      createdAt: new Date()
    }
  },
  { upsert: true }
)
~~~

Khi document tồn tại, `$set` vẫn thay nội dung. Lần retry có thể ghi đè trạng thái `PAID` hoặc `SHIPPED` về `CREATED` và sửa thời điểm tạo. `$setOnInsert` tránh lỗi này cho dữ liệu chỉ được khởi tạo.

Tương tự, `$inc: { balance: -100 }` hoặc `$push: { events: ... }` sẽ tạo **thêm hiệu ứng ở mỗi lần chạy**. Chúng không trở nên idempotent chỉ vì filter có key; phải có một cơ chế claim/guard đảm bảo chỉ một lần thực thi nghiệp vụ.

### 6.3. Race condition giữa hai upsert đồng thời

~~~text
Request A tìm theo (tenantId, clientOrderId) → chưa thấy
Request B tìm theo (tenantId, clientOrderId) → chưa thấy
A cố tạo document
B cố tạo document
~~~

Nếu **không có unique index** trên cặp khóa, hai thao tác upsert đồng thời có thể tạo hai document. Với unique index phù hợp, không thể commit hai document cùng key. Trong một số điều kiện, MongoDB có thể xử lý tranh chấp upsert theo cách cập nhật document đã xuất hiện; trong điều kiện khác một request có thể nhận **E11000**. Vì vậy:

1. Tạo unique index trước khi cho hệ thống nhận request.
2. Filter upsert bằng danh tính duy nhất, rõ ràng.
3. Dùng `$setOnInsert` cho field chỉ ghi khi tạo.
4. Bắt duplicate key, đọc lại document theo identity và xác thực fingerprint.
5. Không tự retry vô hạn; có thời hạn và chiến lược xử lý kết quả chưa rõ.

**Unique index là hàng rào đúng đắn cuối cùng**. Logic “find trước rồi insert” hoặc “upsert theo field không unique” không đủ.

### 6.4. `findOneAndUpdate` khi cần lấy document sau upsert

~~~javascript
const doc = db.upsert_orders.findOneAndUpdate(
  {
    tenantId: "tenant-01",
    clientOrderId: "cart-checkout-009"
  },
  {
    $setOnInsert: {
      productId: "sku-002",
      qty: 1,
      payloadFingerprint: "demo-payload-v1-sku-002-qty-1",
      status: "CREATED",
      createdAt: new Date()
    }
  },
  {
    upsert: true,
    returnDocument: "after"
  }
)

printjson(doc)
~~~

Phương thức này thuận tiện khi muốn trả document vừa tạo hoặc đã tồn tại trong một lượt gọi ở mức API. Dù vậy, fingerprint vẫn phải được kiểm tra, và cần xử lý race/duplicate key/timeout tương tự. Trong các driver khác, API trả về document hoặc wrapper có thể khác.

## 7. Mô hình 3 — Request ledger cho nghiệp vụ nhiều bước

Một thao tác “tạo đơn” thường không chỉ insert vào `orders`:

1. Kiểm tra tồn kho.
2. Trừ tồn kho.
3. Tạo đơn hàng.
4. Ghi nhận request đã hoàn tất.
5. Có thể phát sự kiện để gửi email hoặc xử lý thanh toán.

Nếu chỉ đảm bảo unique `orders._id` nhưng mỗi lần retry vẫn chạy `$inc: {stock: -2}`, bạn có thể chỉ có một order **nhưng stock bị trừ hai lần**. Tính idempotent phải bao phủ **toàn bộ hiệu ứng nghiệp vụ**, không chỉ số lượng document trong collection chính.

### 7.1. Thiết kế collection ghi nhận yêu cầu

Một request ledger có thể gồm:

~~~javascript
{
  tenantId: "tenant-01",
  operation: "POST /orders",
  requestKey: "req-010",
  fingerprint: "sha256-of-canonical-order-request",
  status: "COMPLETED",
  result: {
    orderId: "order-010",
    status: "CREATED"
  },
  createdAt: ISODate("2026-05-10T08:00:00Z"),
  completedAt: ISODate("2026-05-10T08:00:01Z")
}
~~~

Trường fingerprint là chuỗi minh họa. Một hệ thống có thể dùng `PENDING`, `COMPLETED`, `FAILED` theo vòng đời xử lý; ý nghĩa mỗi trạng thái phải được định nghĩa và có cơ chế phục hồi khi worker chết. Với nghiệp vụ được commit trọn trong một transaction, có thể chỉ lưu bản ghi `COMPLETED` cùng các thay đổi nghiệp vụ.

Tạo unique index theo phạm vi:

~~~javascript
use insert_once_lab

db.createCollection("request_ledger")

db.request_ledger.createIndex(
  { tenantId: 1, operation: 1, requestKey: 1 },
  {
    unique: true,
    name: "uq_request_ledger_identity"
  }
)
~~~

### 7.2. Transaction đảm bảo nhiều document cùng commit

Với replica set hoặc sharded cluster hỗ trợ transaction, có thể đưa bản ghi request, thay đổi stock và order vào **một transaction**. Trong ví dụ lab, product phải có trước:

~~~javascript
use insert_once_lab

db.products.updateOne(
  { _id: "sku-001" },
  {
    $setOnInsert: {
      name: "Sản phẩm demo",
      stock: 10
    }
  },
  { upsert: true }
)

db.createCollection("transaction_orders")
~~~

Ví dụ transaction (chạy một lần trong lab có replica set/sharded cluster):

~~~javascript
const session = db.getMongo().startSession()

const tenantId = "tenant-01"
const operation = "POST /orders"
const requestKey = "req-010"
const fingerprint = "demo-payload-sku-001-qty-2"
const orderId = "order-010"
const qty = 2

try {
  const response = await session.withTransaction(async () => {
    const txDb = session.getDatabase("insert_once_lab")

    const previous = await txDb.request_ledger.findOne({
      tenantId,
      operation,
      requestKey
    })

    if (previous) {
      if (previous.fingerprint !== fingerprint) {
        throw new Error("IDEMPOTENCY_KEY_CONFLICT")
      }
      return previous.result
    }

    const now = new Date()

    // Giành danh tính duy nhất trong cùng transaction.
    await txDb.request_ledger.insertOne({
      tenantId,
      operation,
      requestKey,
      fingerprint,
      status: "COMPLETED",
      result: { orderId, status: "CREATED" },
      createdAt: now,
      completedAt: now
    })

    // Chỉ trừ kho nếu còn đủ, ngay trong điều kiện update.
    const stockUpdate = await txDb.products.updateOne(
      { _id: "sku-001", stock: { $gte: qty } },
      { $inc: { stock: -qty } }
    )

    if (stockUpdate.modifiedCount !== 1) {
      throw new Error("INSUFFICIENT_STOCK")
    }

    await txDb.transaction_orders.insertOne({
      _id: orderId,
      tenantId,
      productId: "sku-001",
      qty,
      status: "CREATED",
      createdAt: now
    })

    return { orderId, status: "CREATED" }
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  printjson(response)
} finally {
  await session.endSession()
}
~~~

Transaction đảm bảo bản ghi ledger, giảm stock và insert order **cùng commit hoặc cùng abort**. Nếu stock không đủ, exception khiến transaction abort; ledger `COMPLETED` cũng không được commit. Nếu request đã hoàn tất và gọi lại, nhánh đọc ledger trả result trước đó, không giảm stock lần nữa.

Lưu ý:

- **Không chạy trên standalone thông thường** rồi cho rằng transaction nhiều document được hỗ trợ; cần topology phù hợp.
- Trong trường hợp hai transaction cạnh tranh cùng key, cả hai có thể không nhìn thấy bản ghi chưa commit của nhau. Unique index sẽ làm một giao dịch thất bại do conflict/duplicate; lớp service cần xử lý lỗi đó bằng cách đọc lại kết quả sau khi giao dịch bên kia commit hoặc retry có giới hạn.
- `withTransaction` có thể retry transaction callback trong những lỗi nhất định theo driver/shell; không gọi payment API, gửi email hoặc thực hiện side effect ngoài database bên trong callback.
- Một lỗi commit không rõ kết quả cần xử lý theo API transaction và bằng cách **truy hồi ledger theo key**; không tạo đơn mới ngay.
- `writeConcern: {w: "majority"}` tăng mức bảo đảm xác nhận ghi trong nhiều deployment, nhưng không thay thế backup hoặc logic nghiệp vụ.
- Ví dụ dùng key và fingerprint hằng để dễ quan sát; API thực phải lấy key từ request đã xác thực và tính fingerprint từ payload chuẩn hóa.

### 7.3. Nếu muốn ghi cả kết quả thất bại

Ví dụ stock không đủ: transaction trên abort và không có ledger `COMPLETED`. Theo một contract, retry cùng key sau khi stock được nhập lại **có thể thành công**. Theo contract khác, lỗi nghiệp vụ terminal cần được nhớ lại và các retry phải trả đúng kết quả thất bại ban đầu.

Nếu muốn replay cả lỗi terminal, cần thiết kế cách ghi trạng thái `FAILED` và response theo transaction hoặc cơ chế claim riêng. Không ghi `FAILED` cho mọi lỗi mạng tạm thời, vì như vậy có thể đánh dấu một thao tác chưa biết kết quả thành thất bại vĩnh viễn.

## 8. Khi xử lý bất đồng bộ hoặc có external side effect

Một giao dịch MongoDB **không thể tự commit nguyên tử** với các hệ thống ngoài nó: message broker, cổng thanh toán, email/SMS, dịch vụ vận chuyển. Nếu DB commit rồi API gọi bên ngoài thất bại, hoặc bên ngoài thành công nhưng API chưa ghi trạng thái, retry có thể gây trùng.

### 8.1. Transactional outbox

Mẫu **transactional outbox** ghi một document `outbox` trong cùng transaction với dữ liệu nghiệp vụ:

~~~javascript
{
  _id: "order-010:OrderCreated:v1",
  aggregateId: "order-010",
  eventType: "OrderCreated",
  payload: {
    orderId: "order-010"
  },
  status: "PENDING",
  createdAt: ISODate("2026-05-10T08:00:00Z")
}
~~~

~~~mermaid
flowchart LR
    API["API / command handler"] --> TX["MongoDB transaction"]
    TX --> Order["Order + request ledger"]
    TX --> Outbox["Outbox event"]
    Outbox --> Worker["Publisher/worker"]
    Worker --> Broker["Message broker / external service"]
    Broker --> Consumer["Consumer có dedupe theo eventId"]
~~~

Nhờ ghi cùng transaction, khi order đã commit thì outbox event tương ứng cũng tồn tại. Worker có thể gửi event nhiều lần nếu bị crash sau khi gửi nhưng trước khi đánh dấu đã gửi; **consumer vẫn phải idempotent theo event ID**, và outbox phải có trạng thái/retry/reconciliation phù hợp.

### 8.2. Payment API cần key riêng

Nếu gọi cổng thanh toán, backend nên dùng cơ chế idempotency mà provider hỗ trợ, hoặc lưu một định danh payment request ổn định rồi đối soát. Chống trùng trong MongoDB **không tự ngăn provider thu tiền hai lần** nếu mỗi retry gọi cổng thanh toán với mã yêu cầu mới.

### 8.3. Message queue có thể giao lại

Ví dụ message:

~~~javascript
{
  messageId: "evt-order-010",
  eventType: "OrderCreated",
  orderId: "order-010"
}
~~~

Consumer có thể lưu `messageId` trong collection có unique index cùng transaction với thay đổi bên trong MongoDB. Nếu message được giao lại, consumer đọc dấu vết đã xử lý và bỏ qua phần tác động. Không dùng “đã nhận message” ở memory process làm bằng chứng bền vững sau restart.

### 8.4. Job chạy lâu với trạng thái `PROCESSING`

Với workflow không thể gói trong một transaction ngắn, request ledger có thể dùng:

~~~text
NEW -> PROCESSING -> COMPLETED
                  \-> FAILED / RETRYABLE
~~~

Trạng thái `PROCESSING` cần có **lease/timeout, worker owner, attempt ID** và cơ chế recovery. Nếu worker chết, key không được kẹt mãi ở PROCESSING; nhưng worker khác cũng không được nhận job bằng cách cập nhật mù rồi xử lý song song với worker cũ. Có thể dùng conditional update theo trạng thái và lease token (fencing) để chuyển quyền xử lý. Quy trình này phức tạp hơn mẫu tạo một document và phải được thiết kế theo từng tác vụ.

## 9. Xử lý kết quả không chắc chắn sau timeout

Đây là phần khó nhất của idempotency: **client mất phản hồi không có nghĩa database chưa ghi**.

### 9.1. Bốn khả năng sau khi client timeout

| Tình huống thực tế | Client biết gì? | Hành động an toàn |
|---|---|---|
| Request chưa tới server | Chỉ biết timeout | Gửi lại **cùng key** |
| Server nhận nhưng chưa ghi | Chỉ biết timeout | Gửi lại cùng key, server thực thi một lần |
| MongoDB đã commit, phản hồi mất | Chỉ biết timeout | Đọc ledger/resource theo key; replay kết quả |
| Hai bản retry đang chạy đồng thời | Có thể cùng chờ | Unique index + xử lý conflict/in-progress |

Không thể suy luận từ một exception kiểu timeout rằng thao tác thất bại, hoặc đã thành công. Cần query danh tính ổn định và áp dụng hợp đồng retry.

### 9.2. Một máy trạng thái API minh họa

~~~mermaid
flowchart TD
    R["POST kèm request key"] --> Lookup["Tra theo tenant + operation + key"]
    Lookup --> Found{"Đã có ledger?"}
    Found -->|"Có"| Compare{"Fingerprint trùng?"}
    Compare -->|"Không"| Conflict["409 Conflict"]
    Compare -->|"Có, completed"| Replay["Trả kết quả đã lưu"]
    Compare -->|"Có, processing"| Pending["202 / 409 / Retry-After theo API contract"]
    Found -->|"Chưa"| Claim["Tạo/claim identity với unique index"]
    Claim --> Tx["Thực thi nghiệp vụ"]
    Tx --> Commit["Commit + lưu kết quả"]
    Commit --> Created["Trả kết quả tạo mới"]
    Claim -->|"Tranh chấp unique"| Lookup
~~~

Trong hệ thống thực, nhánh quay lại cần **retry có giới hạn, backoff và deadline** để tránh vòng lặp vô hạn khi request đang xử lý hoặc lỗi kéo dài. Một endpoint riêng như `GET /requests/{key}` có thể giúp client tự tra trạng thái mà không lặp lại side effect.

### 9.3. Mã HTTP là một phần contract

Một quy ước minh họa:

| Trạng thái | Phản hồi tham khảo | Ý nghĩa |
|---|---|---|
| Tạo lần đầu hoàn tất | `201 Created` | Trả ID của resource mới |
| Replay cùng key + payload | `200 OK` hoặc replay nguyên `201` đã lưu | Không tạo resource mới |
| Key cũ nhưng payload khác | `409 Conflict` | Client không được dùng lại key cho ý định khác |
| Request cùng key vẫn chạy | `202 Accepted` kèm cách tra trạng thái; hoặc `409` với retry guidance | Không khởi tạo tác vụ thứ hai |
| Tạm thời không biết commit | `503`/`504` hoặc response retryable theo contract | Client retry cùng key hoặc tra trạng thái |
| Input không hợp lệ | `400`/`422` | Không retry vô hạn khi input không đổi |

Đây là lựa chọn API, không phải MongoDB tự trả các HTTP status. Hợp đồng nên quy định thời hạn giữ key, kết quả được replay, trường hợp conflict và cách client xử lý lỗi.

## 10. TTL và thời gian giữ idempotency key

Ledger có thể tăng lớn theo traffic. Một số hệ thống chỉ giữ idempotency key trong thời hạn được công bố, chẳng hạn 24 giờ hoặc 7 ngày. Nhưng xóa key đồng nghĩa **sau đó server có thể không còn nhận ra request cũ**.

### 10.1. Thời hạn dựa trên retry horizon

Hãy hỏi:

- Mobile app có thể offline rồi gửi lại sau bao lâu?
- Gateway/queue giữ và phát lại request trong bao lâu?
- Nghiệp vụ có thể bị replay sau nhiều tháng khi import/reconciliation?
- Resource đã tạo có một khóa nghiệp vụ giữ lâu hơn ledger không?
- Nếu key hết hạn và request được gửi lại, hệ thống sẽ xử lý ra sao?

Với những nghiệp vụ như hóa đơn hoặc thanh toán, có thể cần unique business identity bền vững hơn thời hạn ledger ngắn. TTL chỉ là một chính sách lưu trữ, không phải bảo đảm chống trùng vĩnh viễn.

### 10.2. Ví dụ TTL cho ledger ngắn hạn

~~~javascript
db.idempotency_requests.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_idempotency_expiry"
  }
)
~~~

Document có `expiresAt` dạng BSON Date sẽ đủ điều kiện bị TTL monitor xóa từ thời điểm đó. **TTL deletion diễn ra bất đồng bộ**, không bảo đảm xóa đúng sát mốc. Đừng dùng “key còn tồn tại tới đúng mili giây T” làm giả định nghiệp vụ.

Nếu request bị xóa khỏi ledger nhưng order còn giữ một khóa duy nhất, unique business index vẫn bảo vệ sự tồn tại của order. Nếu cả hai dấu vết đều biến mất, cùng request có thể được coi là mới sau expiry. Contract phải công bố giới hạn này.

### 10.3. Không tự xóa `COMPLETED` nếu cần đối soát

Trước khi bật TTL, xác định có cần giữ `orderId`, fingerprint, audit ID hoặc giao dịch tài chính trong thời gian dài hơn không. Có thể archive ledger hoặc tách:

- **Request replay cache** có TTL.
- **Business identity** tồn tại theo vòng đời đơn/giao dịch.
- **Audit/reconciliation records** giữ theo quy định nghiệp vụ.

Không dùng TTL trên collection nghiệp vụ chỉ để “dọn key” nếu nó khiến dữ liệu cần giữ bị mất.

## 11. Các lỗi thường gặp và cách phân biệt

### 11.1. Duplicate key — `E11000`

Nguyên nhân: thao tác cố tạo/đổi giá trị vi phạm unique index, có thể là `_id` hoặc một khóa nghiệp vụ khác.

**Xử lý:**

1. Xác định unique constraint bị vi phạm.
2. Tìm document theo **request identity**.
3. So fingerprint.
4. Nếu match, trả kết quả đã lưu; nếu mismatch, trả conflict.
5. Nếu không có document tương ứng, không đoán đó là replay thành công; xử lý lỗi dữ liệu hoặc trạng thái đang tranh chấp.

### 11.2. Write concern timeout

Thao tác có thể đã được áp dụng nhưng mức xác nhận ghi mong muốn chưa được nhận trong thời hạn. Không lập tức tạo lại document với ID mới. Truy hồi theo key hoặc retry cùng key theo chính sách.

### 11.3. Network timeout sau commit

Đây là lý do điển hình cần idempotency. Client không thể phân biệt server chưa xử lý với server xử lý xong nhưng mất response. Kiểm tra ledger/resource theo identity.

### 11.4. Validation error

Document sai schema (ví dụ thiếu field bắt buộc) không tự thành hợp lệ sau retry. Sửa input hoặc contract; đừng retry vô hạn một request sai dữ liệu.

### 11.5. Transaction conflict / commit result unknown

Ở workload đồng thời, transaction có thể gặp write conflict, transient error hoặc kết quả commit chưa biết. Dùng cơ chế retry transaction/commit được driver hỗ trợ, có deadline và kiểm tra idempotency ledger. Không tự viết retry logic phát side effect mới ngoài transaction.

### 11.6. Unique index chưa được tạo thành công

`createIndex({tenantId:1,externalOrderId:1},{unique:true})` có thể thất bại nếu collection đã có dữ liệu trùng. Cần xử lý dữ liệu cũ theo kế hoạch trước khi bật traffic mới. **Không deploy code và giả định unique index tồn tại** chỉ vì migration từng cố chạy lệnh tạo.

## 12. Anti-pattern: những cách tưởng đúng nhưng vẫn tạo trùng

| Anti-pattern | Vì sao sai? | Hướng thay thế |
|---|---|---|
| Tạo `new ObjectId()` trong mỗi lần retry HTTP | Hai request có ID khác nhau | ID nghiệp vụ ổn định hoặc unique request key |
| `findOne()` rồi `insertOne()`, không unique index | Hai request có thể cùng thấy trống | Unique index + xử lý conflict |
| Upsert theo field không unique | Upsert đồng thời có thể tạo hai document | Unique index bao phủ khóa filter |
| `$set` trong mọi replay | Ghi đè thông tin đã thay đổi sau lần tạo | `$setOnInsert`, so fingerprint |
| `$inc` stock mỗi lần retry | Một order nhưng trừ kho nhiều lần | Transaction + ledger hoặc operation guard |
| Bắt **mọi** `E11000` rồi trả success | Có thể vi phạm unique field khác | Tìm đúng identity và so payload |
| Retry khi timeout bằng key mới | Coi cùng ý định là đơn khác | Reuse key và tra kết quả |
| Dedupe bằng `hash(payload)` thay request key | Hai đơn hợp lệ cùng nội dung bị gộp | Mỗi ý định một request key, fingerprint để kiểm tra reuse |
| Lưu key chỉ trong RAM | Restart làm mất dấu yêu cầu đã xử lý | Durable ledger / unique index trong MongoDB |
| Xóa key ngay khi HTTP response trả về | Client mất response rồi retry thành request mới | Retention theo retry horizon |
| Tin key do client gửi là quyền truy cập | User có thể đoán key của tenant khác | Xác thực/ủy quyền và scope identity từ server |
| Gửi email/thanh toán trong transaction callback | Callback có thể retry và side effect lặp | Outbox/consumer idempotent, provider key |
| Trả “đã thất bại” ngay khi network timeout | Không biết commit thực tế | Tra trạng thái, retry có giới hạn cùng key |
| Chặn trùng bằng lock trong một process | Nhiều instance/worker không chia sẻ lock | Ràng buộc bền vững ở database |

### Ví dụ sai: dùng payload hash làm identity duy nhất

~~~javascript
// Sai nếu hai khách hoặc một khách được phép mua cùng giỏ hai lần.
const orderId = hash(customerId + JSON.stringify(items))
~~~

Một ý định đặt hàng mới hợp lệ có thể có cùng giỏ. Fingerprint dùng để kiểm tra **cùng key đã bị tái sử dụng với nội dung khác**; identity dùng để phân biệt các **ý định**.

### Ví dụ sai: xác nhận tồn kho rồi insert riêng

~~~javascript
// Minh họa lỗi logic; không dùng để tạo order thực tế.
const p = db.products.findOne({ _id: "sku-001" })
if (p.stock >= 2) {
  db.products.updateOne(
    { _id: "sku-001" },
    { $inc: { stock: -2 } }
  )
  db.orders.insertOne({ productId: "sku-001", qty: 2 })
}
~~~

Hai request có thể cùng đọc `stock: 2` và cùng trừ; một retry có thể trừ hai lần. Tối thiểu, cập nhật phải có điều kiện `stock: {$gte: 2}` và kiểm tra `modifiedCount`; nếu cần tạo order cùng lúc thì transaction/ledger hoặc quy trình nhất quán tương đương.

## 13. Thiết kế service API từ đầu đến cuối

Giả sử endpoint `POST /orders` có contract:

~~~text
Input:
  Authorization token
  Idempotency-Key
  items, shippingAddressId

Identity:
  tenantId từ auth
  operation = "POST /orders"
  requestKey từ header

Fingerprint:
  canonical payload với schema/field được định nghĩa

Output:
  orderId, trạng thái tạo
  replay theo policy
  conflict nếu cùng key khác payload
~~~

Luồng đề xuất:

~~~text
1. Xác thực user/tenant, kiểm tra quyền tạo order.
2. Validate header key và business payload.
3. Chuẩn hóa payload và tính fingerprint.
4. Tra result của cùng (tenant, operation, key).
5. Nếu đã COMPLETED:
      - fingerprint khác -> 409
      - fingerprint giống -> replay result
6. Nếu đang PROCESSING:
      - trả trạng thái/retry guidance theo contract
7. Nếu chưa có:
      - claim identity với unique index
      - thực hiện business write đúng một lần
      - ghi result/metadata trong transaction (nếu nhiều doc)
8. Nếu unique race/timeout/unknown commit:
      - đọc lại ledger theo key, bounded retry/backoff
9. Trả response ổn định và metric/correlation ID.
~~~

### 13.1. Pseudocode handler độc lập driver

~~~text
function createOrder(authContext, key, request):
    tenant = authContext.tenantId
    operation = "POST /orders"
    validateKey(key)
    normalized = normalizeOrderRequest(request)
    fingerprint = sha256(operation + canonical(normalized))

    result = findRequest(tenant, operation, key)
    if result exists:
        if result.fingerprint != fingerprint:
            return HTTP 409
        if result.state == COMPLETED:
            return replay(result.savedResponse)
        return inProgressResult()

    try:
        return performOneBusinessTransaction(
            tenant, operation, key, fingerprint, normalized
        )
    catch DuplicateKey or RetryableConflict:
        return resolveByReadingSameRequestIdentity()
    catch UnknownCommitResult:
        return resolveByReadingSameRequestIdentityOrRetrySafely()
~~~

Chú ý: tìm ledger ở bước đầu chỉ là **fast path**. Tính đúng đắn đến từ unique constraint và transaction/claim ở bước thực thi. Hai request có thể cùng không thấy ledger trước khi một request tạo nó.

### 13.2. Tránh ghi trùng từ nhiều instance

Nếu API có 10 replica sau load balancer, request retry có thể đến một instance khác. In-memory `Map<key,result>`, `synchronized` hoặc mutex trong từng process không đủ. Ràng buộc ở MongoDB mới là điểm phối hợp chung cho tất cả instance. Redis lock hoặc hệ thống phân tán khác có thể bổ trợ nhưng không loại bỏ yêu cầu xác định unique business state và recovery sau crash.

### 13.3. Bảo vệ dữ liệu và tài nguyên

Idempotency key và ledger còn cần:

- Giới hạn kích thước/độ dài key, tốc độ tạo key, số request đang xử lý.
- Định nghĩa thời hạn retry và cách làm sạch ledger.
- Không dùng key làm đường dẫn/chỉ số phân quyền không qua auth.
- Không ghi payload nhạy cảm vào ledger nếu hash và metadata đủ.
- Có cơ chế chống flooding bằng nhiều key khác nhau cho một user/tenant.
- Kiểm soát thông tin trả về khi key được đoán hoặc bị dùng chéo tài khoản.

Idempotency không thay thế chống spam, quota hay kiểm tra quyền tạo tài nguyên.

## 14. Bài lab: quan sát một yêu cầu tạo chỉ ghi một document

Lab này tập trung một document để thấy rõ điểm khác giữa insert thường, unique ID và upsert.

### Bước 1 — Tạo collection và unique index

~~~javascript
use insert_once_lab

db.createCollection("lab_orders")

db.lab_orders.createIndex(
  { tenantId: 1, requestKey: 1 },
  { unique: true, name: "uq_lab_order_request" }
)
~~~

Nếu collection đã tồn tại từ lần học trước, `createCollection` có thể báo namespace exists. Dùng tên lab mới khi cần học lại, và không xóa collection không thuộc dữ liệu thử nghiệm.

### Bước 2 — Tạo lần đầu

~~~javascript
const filter = {
  tenantId: "lab-tenant-1",
  requestKey: "create-order-001"
}

const fingerprint = "product-A|qty=2|currency=VND"

const first = db.lab_orders.updateOne(
  filter,
  {
    $setOnInsert: {
      productId: "product-A",
      qty: 2,
      currency: "VND",
      payloadFingerprint: fingerprint,
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(first)
~~~

### Bước 3 — Gửi lại cùng yêu cầu

Chạy lại thao tác `updateOne` với **cùng filter và cùng fingerprint**:

~~~javascript
const again = db.lab_orders.updateOne(
  filter,
  {
    $setOnInsert: {
      productId: "product-A",
      qty: 2,
      currency: "VND",
      payloadFingerprint: fingerprint,
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(again)
printjson(db.lab_orders.findOne(filter))
print(db.lab_orders.countDocuments(filter))
~~~

Số document theo identity vẫn là **1**; `createdAt` của document đã tồn tại không bị viết lại bởi `$setOnInsert`.

### Bước 4 — Thử cùng key nhưng nội dung khác

Giả sử request mới muốn thay `qty` thành 3 nhưng vẫn dùng key cũ:

~~~javascript
const requestedFingerprint = "product-A|qty=3|currency=VND"
const saved = db.lab_orders.findOne(filter)

if (saved.payloadFingerprint !== requestedFingerprint) {
  print("IDEMPOTENCY_KEY_CONFLICT: không tạo đơn khác")
}
~~~

Trong service, trả `409 Conflict` (hoặc error contract tương đương). Không thực hiện insert hoặc sửa `qty` của document cũ.

### Bước 5 — Cùng payload nhưng ý định tạo mới

~~~javascript
const another = db.lab_orders.updateOne(
  {
    tenantId: "lab-tenant-1",
    requestKey: "create-order-002"
  },
  {
    $setOnInsert: {
      productId: "product-A",
      qty: 2,
      currency: "VND",
      payloadFingerprint: fingerprint,
      createdAt: new Date()
    }
  },
  { upsert: true }
)

printjson(another)
~~~

Lần này một đơn **mới hợp lệ** có thể được tạo: key đã thay đổi thể hiện ý định khác, dù payload giống.

### Bước 6 — Quan sát index và query

~~~javascript
db.lab_orders.getIndexes()

db.lab_orders.find({
  tenantId: "lab-tenant-1",
  requestKey: "create-order-001"
}).explain("executionStats")
~~~

Với dữ liệu vài document, query planner có thể chọn scan đơn giản. Khi dữ liệu tăng, index phù hợp giúp tra key hiệu quả và là ràng buộc ngăn trùng. Quan trọng nhất ở bài lab là quan sát **không có hai document cùng khóa unique**.

## 15. Bài thực hành nâng cao: mô phỏng timeout và concurrency

Hãy thiết kế một API tạo đơn hoặc job ingest event, rồi thử các trường hợp sau trong **môi trường riêng**:

| Tình huống | Cách tạo tình huống | Kết quả mong muốn |
|---|---|---|
| Retry tuần tự | Gửi POST cùng key 5 lần | Một order, kết quả replay ổn định |
| Retry đồng thời | Gửi 20 request cùng key trong cùng thời điểm | Một hiệu ứng nghiệp vụ; request còn lại replay/wait/conflict kỹ thuật có xử lý |
| Dùng lại key sai payload | Gửi `qty=2` rồi `qty=3` cùng key | Conflict, order cũ không bị sửa |
| Hai ý định hợp lệ cùng nội dung | Dùng hai key mới khác nhau, cùng payload | Hai order nếu nghiệp vụ cho phép |
| Mất response sau commit | Mô phỏng ngắt mạng sau khi DB commit | Client retry cùng key, không tạo order mới |
| Primary failover | Chỉ thử trong replica set lab | Driver/handler retry và tra trạng thái đúng |
| Transaction thiếu stock | Hai order cạnh tranh 1 sản phẩm còn ít | Không bán âm kho, không trừ stock lặp |
| Worker crash giữa xử lý | Kill worker lab tại checkpoint được kiểm soát | Job có thể phục hồi, không double effect |
| Consumer nhận event hai lần | Publish cùng eventId hai lần | Consumer chỉ thực hiện tác động một lần |
| Ledger hết hạn | Dựng tình huống expiry trong lab | Hành vi sau expiry đúng contract, không hứa dedupe vô hạn |

### Các quan sát nên ghi lại

- Số document theo unique request identity.
- Số order và stock trước/sau các lần retry.
- Tần suất `DuplicateKey`, transaction conflict, retry và request replay.
- Độ trễ p95/p99 khi 20 request cùng key hoặc nhiều key khác nhau.
- Trạng thái ledger sau lỗi/timeout.
- Correlation ID, request key đã được che bớt nếu nhạy cảm, order ID trong log.

Điểm quan trọng là **xác minh toàn bộ hiệu ứng**. Thấy `countDocuments({requestKey}) === 1` chưa đủ nếu tồn kho đã bị trừ hai lần hoặc email được gửi ba lần.

## 16. Tính toán phạm vi lưu trữ của request ledger

Một hệ thống có 100 request tạo đơn/giây, lưu key trong 24 giờ:

~~~text
Số request ledger một ngày:
100 × 60 × 60 × 24 = 8.640.000

Giả sử mỗi bản ghi + index chiếm 1 KiB trung bình:
8.640.000 KiB ≈ 8,24 GiB/ngày
~~~

Đây là **ước lượng minh họa**, không phải footprint thực của WiredTiger. Kích thước BSON, index, compression, mức lưu trữ cấp phát, replication, journal và backup đều làm con số khác. Nếu giữ bảy ngày, số document có thể lớn hơn nhiều trước khi TTL xóa.

Do đó cần:

1. Ước tính retry horizon theo client/queue.
2. Chọn lưu response tối giản hay đủ nguyên bản.
3. Đo footprint và tốc độ tăng trong môi trường thực.
4. Có metric về TTL backlog, archive và tỷ lệ replay.
5. Cân nhắc business identity duy nhất lâu dài để bảo vệ các nghiệp vụ quan trọng sau khi ledger ngắn hạn hết hạn.

Không nên vì tiết kiệm dung lượng mà xóa key ngay sau phản hồi; sự cố mất phản hồi thường xảy ra chính vào thời điểm đó.

## 17. Các quyết định thiết kế theo loại nghiệp vụ

| Nghiệp vụ thêm document | Identity phù hợp | Mô hình thường hợp lý | Lưu ý |
|---|---|---|---|
| Tạo bản ghi từ nguồn import | `sourceSystem + sourceRecordId` | Unique compound index + upsert `$setOnInsert` | Chạy lại toàn batch không sinh trùng |
| Nhận webhook provider | `provider + eventId` | Event inbox unique, consumer idempotent | Cần xác thực chữ ký/provider trước khi xử lý |
| Tạo đơn từ nút checkout | `tenant/user + requestKey` | Request ledger + order unique + transaction stock | Replay result, xử lý timeout và xung đột |
| Tạo invoice từ một order | `tenant + orderId + invoiceType` | Unique business key | Không tạo nhiều hóa đơn cùng nghĩa vụ |
| Đăng ký tài khoản | Email normalized hoặc external identity theo contract | Unique index + validation | Email không phải lúc nào cũng là identity bất biến |
| Tạo job xử lý file | `tenant + fileUploadId + processingType` | Unique job identity + trạng thái/lease | Worker restart không tạo job thứ hai |
| Ghi nhận giao dịch tài chính | Business transaction ID bền vững | Ledger, transaction/outbox, reconciliation | Không xóa dấu vết chống trùng quá sớm |

Mỗi dòng đều cần tự xác định khi nào được xem là “một ý định mới”. Ví dụ một file có thể được cố ý xử lý lại bằng phiên bản thuật toán khác; lúc đó `processingType` hoặc `generation` phải là một phần identity nếu nghiệp vụ cho phép tạo kết quả mới.

## 18. Checklist trước khi đưa chức năng tạo dữ liệu vào production

- [ ] Có định nghĩa rõ **một ý định tạo** và **một lần retry**.
- [ ] Request key ổn định qua mọi lần gửi lại, nhưng thay đổi khi người dùng tạo ý định mới.
- [ ] Identity được scope theo tenant/user/operation đã xác thực.
- [ ] Có unique index hoặc `_id` cưỡng chế tính duy nhất ở database.
- [ ] Đã kiểm tra migration tạo unique index thật sự thành công, không có duplicate dữ liệu cũ.
- [ ] Có fingerprint canonical để phát hiện key bị tái sử dụng với payload khác.
- [ ] Dữ liệu tạo ban đầu dùng `$setOnInsert` hoặc insert có khóa ổn định, không ghi đè khi replay.
- [ ] Duplicate key được phân loại đúng index, không bị nuốt thành success vô điều kiện.
- [ ] Timeout/unknown commit được xử lý bằng truy hồi theo key hoặc retry an toàn có giới hạn.
- [ ] Nhiều thao tác MongoDB cùng một nghiệp vụ có transaction/guard bảo đảm consistency.
- [ ] Side effect ngoài MongoDB dùng outbox/consumer idempotent hoặc key của provider.
- [ ] Có hợp đồng HTTP cho created, replay, processing, key conflict và retryable error.
- [ ] Thời hạn giữ key phù hợp retry horizon; biết giới hạn sau TTL.
- [ ] Có kiểm thử request đồng thời, lỗi mạng, crash và replay message.
- [ ] Có metric theo dõi replay, duplicate key, transaction retry và số hiệu ứng nghiệp vụ thực.
- [ ] Không lưu hoặc log dữ liệu nhạy cảm quá mức trong request ledger.

## 19. Câu hỏi ôn tập

**1. `insertOne()` với một ObjectId mới mỗi lần retry có idempotent không?**

Không. Các lần gọi tạo document có `_id` khác nhau. Phải dùng danh tính yêu cầu ổn định hoặc ràng buộc unique trên khóa nghiệp vụ.

**2. Chỉ chạy `findOne()` trước khi insert có chống trùng được không?**

Không khi có concurrency. Hai request có thể cùng thấy “chưa có”. Cần unique index và xử lý lỗi cạnh tranh.

**3. Vì sao `$setOnInsert` phù hợp hơn `$set` khi replay thao tác tạo?**

Vì `$setOnInsert` chỉ thiết lập field khi upsert thực sự tạo mới, không ghi đè document đã tồn tại. `$set` có thể sửa lại trạng thái hoặc `createdAt` khi retry.

**4. Có unique index là đủ cho nghiệp vụ trừ tồn kho và tạo đơn không?**

Không. Unique index có thể ngăn hai order cùng key nhưng không ngăn một đoạn code ngoài transaction trừ stock nhiều lần. Cần transaction hoặc cơ chế đồng bộ hiệu ứng nghiệp vụ.

**5. Tại sao phải so fingerprint?**

Để không âm thầm coi cùng key nhưng nội dung khác là replay hợp lệ. Một key chỉ đại diện một ý định đã định nghĩa.

**6. Nếu MongoDB trả E11000, có luôn được trả thành công không?**

Không. E11000 có thể do unique field khác hoặc request dùng key cũ sai payload. Phải đọc đúng identity và kiểm tra nội dung đã lưu.

**7. Retryable writes có giải quyết hai HTTP POST cùng nội dung không?**

Không. Driver retry một thao tác ghi theo cơ chế của nó; hai HTTP POST có thể sinh hai thao tác nghiệp vụ mới. Cần idempotency ở cấp API.

**8. Client timeout có chứng minh database chưa ghi không?**

Không. Có thể đã commit nhưng response mất. Client phải giữ key và backend phải truy hồi kết quả.

**9. Vì sao cần key khác nhau khi cùng khách hàng cố ý đặt hai đơn giống hệt?**

Vì hai đơn là hai ý định mới. Dùng payload hash như identity sẽ gộp nhầm chúng; mỗi ý định có request key riêng.

**10. Ledger TTL hết hạn có còn chống trùng vĩnh viễn không?**

Không. Hệ thống cần công bố phạm vi thời gian chống trùng và có thể giữ business unique identity lâu dài hơn.

**11. Transaction MongoDB có bảo đảm email chỉ gửi một lần không?**

Không. Email là external side effect. Dùng outbox và cơ chế idempotency của worker/consumer.

**12. Làm sao xử lý hai request cùng key tới hai instance API khác nhau?**

Cùng truy cập unique index/request ledger ở MongoDB. Một request có thể thành công, request kia đọc lại kết quả hoặc xử lý conflict/đang xử lý; lock trong memory từng instance không đủ.

## 20. Kết luận

Thiết kế thao tác thêm có thể gửi lại đòi hỏi nhận diện **ý định nghiệp vụ** qua một khóa ổn định, áp dụng **unique constraint** làm hàng rào ở database và **truy hồi kết quả** khi nhận request lặp hoặc gặp timeout. Với một document, cố định `_id` hoặc upsert bằng `$setOnInsert` thường đủ. Với nghiệp vụ gồm nhiều document, tồn kho, event hay dịch vụ bên ngoài, cần request ledger, transaction, outbox và idempotency của các bên liên quan.

Nguyên tắc quan trọng nhất: **retry cùng key chỉ được lặp lại việc tìm hoặc hoàn tất kết quả của một ý định; không được tạo một ý định mới hay phát sinh thêm hiệu ứng ngoài dự kiến**. Mỗi chức năng tạo dữ liệu cần được thử dưới điều kiện request gửi lại, xử lý đồng thời và mất phản hồi sau commit trước khi coi là an toàn cho production.

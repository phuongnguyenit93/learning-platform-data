# E11000 duplicate key và xung đột dữ liệu khi upsert trong MongoDB

Một dịch vụ nhận yêu cầu thanh toán có thể nhận hai HTTP requests cùng mang `requestId`. Cả hai request đều gọi MongoDB với `upsert: true` vì muốn “nếu chưa có thì tạo, có rồi thì cập nhật”. Đôi khi cả hai thành công, đôi khi một request nhận lỗi:

```text
E11000 duplicate key error collection: shop.payment_requests
index: uk_tenant_request dup key:
{ tenantId: "tenant-a", requestId: "REQ-1001" }
```

Đây không nhất thiết là MongoDB “mất tính nguyên tử”. Nó thường là bằng chứng rằng **unique index đã bảo vệ dữ liệu khỏi hai bản ghi có cùng khóa**, trong khi logic tìm kiếm, điều kiện upsert hoặc thao tác đồng thời chưa được thiết kế theo cùng khóa duy nhất.

Bài **“E11000 duplicate key và xung đột dữ liệu khi upsert”** thuộc chương **Xử lý sự cố** của module **Database Engine Document MongoDB**. Chúng ta sẽ đi từ cơ chế index và cách upsert hoạt động đến điều tra lỗi trong `mongosh`, Java Sync Driver và Spring Data MongoDB; sau đó xây dựng phương án idempotency, xử lý race condition, kiểm thử concurrency và runbook production.

Sau bài học, bạn có thể:

1. Đọc thông báo **E11000 (error code 11000)** để xác định collection, index và khóa bị trùng.
2. Phân biệt lỗi unique `_id`, unique index đơn, compound, partial, sparse và collation.
3. Hiểu tại sao **kiểm tra tồn tại rồi insert** không an toàn khi nhiều writers cùng chạy.
4. Thiết kế filter/upsert khớp **business unique key** và dùng `$setOnInsert` đúng chỗ.
5. Hiểu khi nào hai upserts đồng thời có thể **một insert, một update**, và khi nào vẫn phát sinh E11000.
6. Xử lý E11000 có điều kiện thay vì bắt mọi duplicate rồi coi như thành công.
7. Xây dựng idempotency cho request trùng, nhận diện retry mơ hồ sau network/write concern timeout.
8. Kiểm tra dữ liệu hiện có, index definitions, lỗi migration/bulk write và đặc điểm sharded cluster.
9. Viết integration tests mô phỏng concurrent upserts và bảo đảm bất biến “một khóa nghiệp vụ – một document”.

> **An toàn vận hành:** tất cả collection, dữ liệu và lệnh tạo/xóa index trong bài chỉ nên thực hành trên database lab riêng. Không xóa unique index của production để “dẹp lỗi”, không chạy cập nhật dữ liệu hàng loạt hay `drop()` trên production khi chưa có change approval, backup và kế hoạch rollback.

## 1. E11000 có nghĩa gì?

**E11000 duplicate key** là lỗi MongoDB phát ra khi một write làm phát sinh **giá trị khóa trùng** với một document khác theo ràng buộc của **unique index**.

Lỗi có thể xảy ra khi:

- `insertOne()` chèn document có `_id` trùng.
- `insertOne()` hoặc `insertMany()` chèn giá trị trùng tại một unique secondary index.
- `updateOne()` sửa field được unique index bảo vệ thành giá trị đã tồn tại.
- `replaceOne()` hoặc `findOneAndUpdate()` gây trùng khóa.
- `updateOne(..., {upsert:true})` chuyển sang nhánh insert và đụng một unique constraint.
- `createIndex(...,{unique:true})` không thể xây index vì **dữ liệu hiện hữu đã có duplicate keys**.
- Một migration/import/bulk write đụng nhiều unique constraints khác nhau.

**E11000 không tự chỉ ra thao tác nào đã chạy trước hoặc document nào là “đúng”.** Muốn xử lý phải biết index và bối cảnh nghiệp vụ.

### E11000 khác lỗi khác

| Lỗi/hiện tượng | Tầng nguyên nhân | Có đồng nghĩa duplicate không? |
| --- | --- | --- |
| `E11000`, code `11000` | Unique index constraint | Có |
| `Document failed validation` | Schema validator | Không |
| `WriteConflict` | Xung đột ghi/transaction ở engine | Không |
| `Unauthorized` | Database RBAC | Không |
| `NetworkTimeout` | Giao tiếp/không rõ kết quả | Không |
| `WriteConcernError` | Điều kiện xác nhận ghi chưa đạt | Không |
| `OptimisticLockingFailureException` | Version predicate không match theo Spring Data | Không nhất thiết |

Không nên bắt tất cả các lỗi write rồi đổi thành HTTP 409 “duplicate”. Điều đó che mất lỗi mạng, quyền và validation thật.

## 2. Unique index là nơi MongoDB bảo vệ khóa

Collection MongoDB mặc định có unique index trên `_id`. Ngoài ra, ứng dụng có thể tạo unique index:

```javascript
db.customers.createIndex(
  { email: 1 },
  { unique: true, name: "uk_customer_email" }
);
```

Nếu `email = "alice@example.invalid"` đã tồn tại, một insert khác cùng giá trị thường bị từ chối:

```javascript
db.customers.insertOne({
  _id: "C1",
  email: "alice@example.invalid"
});

// Lệnh sau lỗi E11000 trên uk_customer_email.
db.customers.insertOne({
  _id: "C2",
  email: "alice@example.invalid"
});
```

Đáng chú ý: hai documents có `_id` **khác nhau**, nhưng vẫn trùng ở secondary index. Vì vậy thay `_id` hoặc tạo một ObjectId mới **không sửa được** lỗi trùng business key `email`.

### Unique index không được suy ra từ tên field

Một field tên `email`, `externalId` hay `requestId` không tự unique. Ràng buộc tồn tại khi có index có `unique:true` được tạo thành công (hoặc unique constraint thích hợp của deployment).

Kiểm tra:

```javascript
db.customers.getIndexes();
```

Nếu không có unique index phù hợp, hai upserts đồng thời có thể **cùng insert** và tạo hai documents trùng về mặt nghiệp vụ.

## 3. Đọc cấu trúc thông báo lỗi E11000

Ví dụ:

```text
MongoServerError: E11000 duplicate key error
collection: shop.customers
index: uk_customer_email
dup key: { email: "alice@example.invalid" }
```

Diễn giải:

| Thành phần | Ý nghĩa |
| --- | --- |
| `E11000` / code `11000` | Unique constraint bị vi phạm |
| `collection` | Namespace xảy ra lỗi |
| `index` | Index có uniqueness constraint gây lỗi |
| `dup key` | Giá trị index key xung đột |
| `keyPattern` (khi có) | Những fields thuộc key pattern |
| `keyValue` (khi có) | Giá trị khóa trùng được server trả |

Thông tin lỗi và cách driver expose `keyPattern/keyValue` thay đổi theo MongoDB/driver version; đừng viết parser dựa vào một chuỗi message duy nhất nếu có error code và structured details.

### Thông báo lỗi có thể chứa dữ liệu nhạy cảm

`dup key` đôi khi bao gồm email, số định danh hoặc khóa nghiệp vụ. Không in nguyên raw error response ra HTTP hay log công khai. Khi cần quan sát, log **index name, code, correlation ID và giá trị đã được mask/hash theo policy**.

### Lỗi trên `_id_`

```text
index: _id_ dup key: { _id: ObjectId("...") }
```

Điều này nói rằng đã có document dùng cùng `_id`. Nguyên nhân có thể là insert lại cùng object, retry sau kết quả mơ hồ hoặc dữ liệu nguồn trùng — không mặc định là lỗi ở secondary index.

## 4. Quy trình dựng lab tối thiểu

Trong `mongosh` kết nối tới môi trường thực hành:

```javascript
use e11000_lab

db.customers.drop();

db.customers.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, name: "uk_tenant_email" }
);

db.customers.insertOne({
  _id: "customer-1",
  tenantId: "tenant-a",
  email: "alice@example.invalid",
  status: "ACTIVE"
});
```

**`drop()` chỉ an toàn trong database lab disposable** như ví dụ, không copy vào production. Việc drop collection cũng xóa indexes của collection đó; tạo lại index trước khi chạy các tình huống.

### Thử chèn duplicate

```javascript
db.customers.insertOne({
  _id: "customer-2",
  tenantId: "tenant-a",
  email: "alice@example.invalid",
  status: "NEW"
});
```

Lệnh thứ hai bị E11000 do cặp `(tenantId,email)` đã tồn tại.

Nhưng:

```javascript
db.customers.insertOne({
  _id: "customer-3",
  tenantId: "tenant-b",
  email: "alice@example.invalid",
  status: "NEW"
});
```

thường thành công vì compound unique index bảo đảm **sự duy nhất của cả cặp**, không bắt `email` phải duy nhất giữa mọi tenant.

## 5. Compound unique index khác unique index đơn

Hai index:

```javascript
{ email: 1 }                 // unique email toàn collection

{ tenantId: 1, email: 1 }    // unique tổ hợp tenantId + email
```

không tương đương.

Với SaaS đa tenant:

| tenantId | email | Unique theo `{tenantId,email}` |
| --- | --- | --- |
| tenant-a | a@example.invalid | Chấp nhận lần đầu |
| tenant-a | a@example.invalid | Trùng |
| tenant-b | a@example.invalid | Không trùng với tenant-a |
| tenant-b | b@example.invalid | Không trùng |

Nếu service upsert bằng `{email}` nhưng unique index là `{tenantId,email}`, filter có thể match một tenant khác hoặc dẫn tới hành vi không đúng phạm vi. **Business identity và database unique key phải được thiết kế cùng nhau.**

### Tên index không quyết định tính duy nhất

`name: "uk_tenant_email"` chỉ đặt tên dễ theo dõi. Key pattern, options như `unique`, `partialFilterExpression` và `collation` mới quyết định semantics.

## 6. E11000 cũng xảy ra khi UPDATE

Giả sử:

```javascript
db.customers.insertOne({
  _id: "customer-4",
  tenantId: "tenant-a",
  email: "bob@example.invalid"
});
```

Thao tác:

```javascript
db.customers.updateOne(
  { _id: "customer-4" },
  { $set: { email: "alice@example.invalid" } }
);
```

vi phạm unique index `uk_tenant_email` vì tenant-a đã có email Alice.

**Không phải chỉ insert/upsert mới có E11000.** Khi cập nhật một phần của unique key, phải kiểm tra toàn bộ constraints và giải quyết business conflict.

Với update trên một document, nếu constraint bị vi phạm, MongoDB không được phép áp dụng kết quả ghi không hợp lệ của thao tác đó. Với bulk operations, các thao tác khác trong cùng batch có thể đã thành công; phải kiểm tra từng kết quả.

## 7. Upsert hoạt động như thế nào?

`upsert` là kết hợp **update** và **insert**:

```text
updateOne(filter, update, { upsert: true })
                     |
                     v
             Có document match?
               /         \
             Có           Không
             |             |
             v             v
          Update         Insert mới từ
          một doc        filter + update
```

Ví dụ:

```javascript
db.customers.updateOne(
  {
    tenantId: "tenant-a",
    email: "carol@example.invalid"
  },
  {
    $set: { status: "ACTIVE" },
    $setOnInsert: { createdAt: new Date() }
  },
  { upsert: true }
);
```

Nếu chưa có document match, MongoDB tạo document mới từ các điều kiện equality phù hợp và update expressions. Nếu đã có, update sẽ sửa document đang tồn tại.

### Upsert không phải “insert nếu không có ID”

Việc chọn nhánh insert hay update dựa trên **toàn bộ filter**, không chỉ `_id` hoặc một unique field. Một document có thể đã tồn tại theo unique business key nhưng **không match filter** vì filter chứa điều kiện khác; upsert lúc đó vẫn thử insert và có thể nhận E11000.

## 8. Đọc kết quả `updateOne(..., upsert:true)`

Một kết quả được xác nhận có thể chứa:

```javascript
{
  acknowledged: true,
  matchedCount: 0,
  modifiedCount: 0,
  upsertedCount: 1,
  upsertedId: ObjectId("...")
}
```

Diễn giải:

| Field | Ý nghĩa |
| --- | --- |
| `acknowledged` | Có phản hồi write theo write concern |
| `matchedCount` | Số document được match (0 hoặc 1 cho updateOne) |
| `modifiedCount` | Số document thực sự thay đổi |
| `upsertedCount` | Số document được insert do upsert |
| `upsertedId` | ID của document mới nếu upsert insert |

Ví dụ:

- `matchedCount=0, upsertedCount=1`: insert do không có match.
- `matchedCount=1, upsertedCount=0`: một document cũ được match; `modifiedCount` có thể là 0 nếu update không đổi giá trị.
- Command ném E11000: **không có một kết quả update thành công bình thường cho operation lỗi**.

Không coi `modifiedCount=0` là bằng chứng thiếu document. Nó có thể là một no-op update trên document đã match.

## 9. Race condition của hai upserts đồng thời

Giả sử collection chưa có key `REQ-1001`. Hai workers gần như cùng lúc chạy:

```javascript
db.payment_requests.updateOne(
  { tenantId: "tenant-a", requestId: "REQ-1001" },
  { $setOnInsert: { status: "RECEIVED" } },
  { upsert: true }
);
```

Timeline khái niệm:

```text
Worker A                            Worker B
   |                                   |
   | query: chưa có key                 | query: chưa có key
   |                                   |
   | thử insert (tenant-a, REQ-1001)    | thử insert cùng key
   |                                   |
   | INSERT thành công                  |
   |                                   | unique index nhận ra
   |                                   | key đã tồn tại
   v                                   v
  Một document                   Có thể update document
                                  vừa tạo hoặc E11000
                                  tùy điều kiện server
```

Điểm cần nhớ:

- **MongoDB không cho hai documents vi phạm cùng một unique index được cùng tồn tại.**
- Nhưng mỗi operation không phải là một “khóa phân tán” giữ từ lúc bắt đầu query đến lúc business workflow kết thúc.
- Hệ quả của worker thua race có thể là **update** hoặc **duplicate key error** tùy filter, unique index, update expression và điều kiện documented của server.
- Ứng dụng phải xử lý **cả hai khả năng**.

## 10. Không có unique index thì race còn nguy hiểm hơn

Ví dụ:

```javascript
use e11000_lab

db.requests_without_unique.drop();

// Không tạo unique index trên requestId.
db.requests_without_unique.updateOne(
  { requestId: "REQ-1001" },
  { $setOnInsert: { createdAt: new Date() } },
  { upsert: true }
);
```

Nếu nhiều clients đồng thời vượt qua giai đoạn tìm kiếm trước khi một insert được nhìn thấy, chúng có thể tạo **nhiều documents có cùng requestId**. Một lần chạy tuần tự có thể không tái hiện duplicate; điều đó không chứng minh thiết kế an toàn.

**Unique index là chốt chặn invariant ở database.** Chỉ viết:

```text
if (!existsByRequestId(requestId)) {
    insert(request);
}
```

không loại bỏ race vì có khoảng thời gian giữa `exists` và `insert`.

### Một document được cập nhật nguyên tử không có nghĩa toàn workflow nguyên tử

MongoDB đảm bảo atomicity cho một write trên một document theo semantics được hỗ trợ. Nhưng việc hai clients cùng quyết định “chưa tồn tại” là hành vi cạnh tranh; unique constraint là cơ chế bảo vệ để không tạo hai documents trùng business key.

## 11. Khi concurrent upserts có thể hội tụ thành UPDATE

MongoDB document behavior cho biết trong tình huống nhiều upserts cùng đụng unique index, **một operation insert**, những operations khác **có thể cập nhật document vừa insert** thay vì luôn nhận E11000 nếu cùng thỏa các điều kiện.

Điều kiện quan trọng gồm:

1. Có **unique index** gây va chạm.
2. Operation là **single-document update** (không phải `updateMany/multi:true`).
3. Filter là **một equality predicate** hoặc AND của các equality predicates.
4. Tập fields trong equality predicates **khớp với fields của unique index key pattern**.
5. Update **không sửa các fields thuộc unique index key pattern**.

Ví dụ phù hợp ý tưởng:

```javascript
db.requests.createIndex(
  { requestId: 1 },
  { unique: true, name: "uk_request_id" }
);

db.requests.updateOne(
  { requestId: "REQ-1001" },
  { $setOnInsert: { status: "RECEIVED" } },
  { upsert: true }
);
```

Khi hai clients race, không nên mặc định một client chắc chắn nhận E11000. Tùy tình huống documented, server có thể cho operation còn lại match và cập nhật document vừa chèn.

**Dù vậy, không được xây business logic giả định rằng “MongoDB luôn tự retry mọi duplicate upsert”.** Chỉ khi các điều kiện trên được đáp ứng mới có cơ hội hội tụ theo behavior được hỗ trợ; các trường hợp khác vẫn có thể lỗi.

## 12. Một filter thêm điều kiện làm mất khả năng hội tụ

Unique index:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true, name: "uk_email" }
);
```

Upsert:

```javascript
db.users.updateOne(
  {
    email: "alice@example.invalid",
    status: "PENDING"
  },
  {
    $set: { lastCheckedAt: new Date() }
  },
  { upsert: true }
);
```

Nếu một document đã có `email = "alice@example.invalid"` nhưng `status = "ACTIVE"`:

- Filter **không match** vì status khác.
- Upsert cố insert document mới với email Alice.
- Unique index `uk_email` từ chối vì email đã tồn tại.
- Operation có thể trả **E11000**.

Ở đây nguyên nhân **không phải hai threads**. Một request duy nhất cũng đủ gây lỗi vì **filter chứa điều kiện không cùng nghĩa với unique identity**.

### Sửa theo invariant

Nếu mục đích là cập nhật một account đã tồn tại chỉ khi status PENDING, hãy dùng **update có điều kiện, không upsert**:

```javascript
db.users.updateOne(
  {
    email: "alice@example.invalid",
    status: "PENDING"
  },
  { $set: { lastCheckedAt: new Date() } }
);
```

Nếu không match, ứng dụng phân biệt account không tồn tại, account đã đổi status hoặc conflict theo business policy. Không dùng upsert để che tình huống “bản ghi có tồn tại nhưng đang ở trạng thái khác”.

## 13. Unique index và filter phải biểu diễn cùng identity

Giả sử business identity là cặp:

```text
(tenantId, externalOrderId)
```

Hãy tạo unique index:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uk_tenant_external_order" }
);
```

Và dùng filter:

```javascript
{
  tenantId: "tenant-a",
  externalOrderId: "EXT-1001"
}
```

Tránh:

```javascript
{
  externalOrderId: "EXT-1001"
}
```

vì thiếu tenant scope.

Cũng tránh thêm `status`, `updatedAt` hoặc điều kiện range vào filter **khi ý nghĩa mong muốn là “tìm đúng business entity bằng unique identity”**; điều kiện bổ sung có thể khiến document đã tồn tại không match và upsert cố insert trùng.

**Lưu ý:** filter khớp unique index là điều kiện quan trọng, nhưng không thay thế kiểm tra business invariants và khả năng lỗi do **những unique indexes khác**.

## 14. `$setOnInsert` và `$set` khác nhau

Ví dụ:

```javascript
db.payment_requests.updateOne(
  {
    tenantId: "tenant-a",
    requestId: "REQ-1001"
  },
  {
    $setOnInsert: {
      status: "RECEIVED",
      createdAt: new Date(),
      payloadHash: "fake-hash-001"
    },
    $set: {
      lastSeenAt: new Date()
    }
  },
  { upsert: true }
);
```

| Operator | Khi insert do upsert | Khi match document có sẵn |
| --- | --- | --- |
| `$setOnInsert` | Thiết lập fields | Không áp dụng |
| `$set` | Thiết lập fields | Thiết lập fields |
| `$inc` | Tăng numeric field theo rules | Tăng numeric field |
| `$unset` | Loại bỏ field theo rules | Loại bỏ field |

Trong ví dụ:

- `status` và `createdAt` chỉ được đặt lúc tạo.
- `lastSeenAt` được cập nhật cả khi insert lẫn match.
- `payloadHash` giữ nội dung nguồn lúc đầu; nếu request sau dùng **cùng requestId nhưng payload khác**, ứng dụng phải phát hiện và trả conflict, không âm thầm ghi đè.

### Không viết cùng path trong nhiều modifiers xung đột

Ví dụ sai:

```javascript
{
  $set: { status: "ACTIVE" },
  $setOnInsert: { status: "RECEIVED" }
}
```

Hai operators cùng muốn sửa một path `status`; điều này có thể gây **conflicting update operators** chứ không phải E11000. Thiết kế update rõ ràng: một path do một operator chịu trách nhiệm trong cùng operation.

## 15. Upsert không phải một phép “merge thông minh”

Giả sử request đầu:

```json
{
  "requestId": "REQ-1001",
  "amount": "100.00",
  "currency": "USD"
}
```

Request sau có cùng ID nhưng:

```json
{
  "requestId": "REQ-1001",
  "amount": "900.00",
  "currency": "USD"
}
```

Hai payload **khác nhau**, dù requestId giống. Nếu service dùng:

```javascript
db.payment_requests.updateOne(
  { requestId: "REQ-1001" },
  { $set: { amount: NumberDecimal("900.00") } },
  { upsert: true }
);
```

thì lệnh thứ hai có thể **thay amount của request đầu**. Nó không bảo đảm tính idempotent theo nghiệp vụ.

Một thiết kế idempotency an toàn thường cần:

1. **Idempotency key** do client/server thống nhất.
2. **Unique index** ở phạm vi đúng (ví dụ tenant + requestId).
3. **Canonical fingerprint/hash** của payload có ý nghĩa nghiệp vụ.
4. Quy tắc khi same key/same payload: trả cùng kết quả hoặc trạng thái hiện có.
5. Quy tắc khi same key/different payload: **báo conflict**, không ghi đè.
6. Bảo vệ side effects (payment/email/event) khỏi chạy lặp.

Một unique index chỉ biết **khóa có trùng không**, không tự biết hai payload tương đương hay không.

## 16. Thiết kế collection cho idempotent request

Ví dụ:

```javascript
use e11000_lab

db.payment_requests.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    name: "uk_tenant_request"
  }
);
```

Document:

```javascript
{
  _id: ObjectId("65f000000000000000000101"),
  tenantId: "tenant-a",
  requestId: "REQ-1001",
  payloadHash: "sha256-of-canonical-request",
  amount: NumberDecimal("125000.00"),
  currency: "VND",
  status: "RECEIVED",
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  resultReference: null
}
```

`payloadHash` là minh họa, không phải một hash đã tính thực. Trong production phải định nghĩa canonicalization rõ (thứ tự JSON fields, kiểu số, currency, optional fields), tránh cùng payload logic lại có nhiều hashes do serialize khác nhau.

### Create-only upsert

```javascript
db.payment_requests.updateOne(
  { tenantId: "tenant-a", requestId: "REQ-1001" },
  {
    $setOnInsert: {
      payloadHash: "sha256-of-canonical-request",
      amount: NumberDecimal("125000.00"),
      currency: "VND",
      status: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

Nếu record đã tồn tại, phần `$setOnInsert` không ghi đè. Sau write, ứng dụng đọc record theo **unique key** rồi so payloadHash/result/status. Với request khác payload, trả conflict.

### Không nhất thiết phải xử lý nghiệp vụ ngay trong transaction của upsert

Idempotent record chỉ đóng vai trò **khóa ghi nhận yêu cầu**. Việc thực thi thanh toán, gửi email hoặc tạo outbox event vẫn cần state machine/claim/transaction strategy riêng. Không cho hai workers cùng gọi payment provider chỉ vì cả hai đọc được record `status:"RECEIVED"`.

## 17. Trường hợp một insert một E11000 có thể là hành vi đúng

Nếu hai requests dùng **cùng business key nhưng payload khác nhau**, một unique index giúp phát hiện không thể tạo hai records.

Một chiến lược xử lý:

```text
Upsert/insert attempt
      |
      +--> Success
      |      |
      |      v
      |   Read/return stored result
      |
      +--> E11000
             |
             v
          Xác định index và key
             |
             v
          Read theo business unique key
             |
             +--> Existing payload tương đương
             |      -> áp dụng idempotency policy
             |
             +--> Existing payload khác
             |      -> trả conflict
             |
             +--> Không tìm thấy/khác index
                    -> giữ lỗi, điều tra/retry có kiểm soát
```

**Không chuyển mọi E11000 thành thành công.** Một write có thể trùng `_id` hoặc một unique index khác, khiến việc “đọc theo requestId” không tìm ra record tương ứng. Hoặc record tồn tại nhưng có payload sai.

## 18. Vì sao pre-check rồi insert vẫn có race?

Anti-pattern:

```java
if (!repository.existsByRequestId(requestId)) {
    repository.insert(newRequest);
}
```

Timeline:

```text
T1: exists -> false
T2: exists -> false
T1: insert -> success
T2: insert -> E11000 (nếu unique index)
```

Không thể làm hai thao tác này nguyên tử chỉ bằng Java `synchronized` khi ứng dụng chạy nhiều instances. Unique index + một lệnh atomic upsert/CAS, hoặc insert-only với xử lý duplicate có điều kiện, phù hợp hơn.

### Pre-check vẫn có ích ở đâu?

Nó có thể giúp UI trả thông tin sớm, nhưng **không phải chốt chặn cuối cùng**. Database constraint vẫn phải quyết định tính duy nhất khi ghi. Đừng dùng pre-check thay unique index.

## 19. Khi nào dùng `insertOne()` thay vì upsert?

Nếu business semantics là **“chỉ được tạo mới; tồn tại rồi thì báo conflict”**, `insertOne()` với unique key có thể đơn giản hơn upsert.

Ví dụ:

```javascript
db.external_events.insertOne({
  _id: "tenant-a:EVENT-1001",
  tenantId: "tenant-a",
  eventId: "EVENT-1001",
  payloadHash: "hash-001",
  receivedAt: new Date()
});
```

Nếu cùng `_id` đến lần nữa, server trả E11000. Application đọc existing event, so nội dung rồi quyết định idempotent duplicate hay conflict.

Đối với create-only semantics, **insert + catch duplicate** thường diễn đạt rõ hơn một upsert có `$set` dễ ghi đè.

### Nhưng dùng `_id` chuỗi ghép cũng cần quy tắc

Nếu chọn `tenantId + ":" + eventId` làm `_id`, phải có canonicalization và tránh collisions do delimiter/normalization. Một compound unique index trên hai fields có thể dễ quản lý hơn; chọn theo schema và nhu cầu truy vấn.

## 20. E11000 do unique index trên `null` hoặc missing

MongoDB unique **single-field** index có quy tắc quan trọng: đối với một index bình thường, document thiếu field và document có field `null` tạo index key null tương ứng. Vì unique chỉ cho một index entry với key null, insert document thứ hai thiếu field/null có thể bị E11000.

Ví dụ lab:

```javascript
db.contacts.drop();

db.contacts.createIndex(
  { email: 1 },
  { unique: true, name: "uk_email" }
);

db.contacts.insertOne({ _id: 1, name: "A" });

// Trùng key null đối với unique single-field index:
db.contacts.insertOne({ _id: 2, name: "B" });
```

Không có email nào được gửi, nhưng vẫn trùng do index semantics.

### Khác biệt compound unique index

Với index `{tenantId:1, email:1}`, uniqueness áp cho **cặp giá trị**. Các tổ hợp null/missing cần được hiểu theo toàn bộ key pattern. Không áp dụng máy móc quy tắc “chỉ một null trong toàn collection” cho mọi compound indexes.

### Đừng sửa bằng cách gán email = ""

Chuỗi rỗng `""` cũng là một giá trị có thể trùng, và thường làm sai semantics “chưa có email”. Cần chọn partial index, sparse index, hoặc data model phù hợp.

## 21. Partial unique index cho field optional

Nếu chỉ muốn unique email **khi field có BSON String**:

```javascript
db.contacts.drop();

db.contacts.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uk_email_when_string",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Ý nghĩa:

- Documents thiếu email không được index theo điều kiện này.
- Documents có email `null` không thuộc điều kiện string.
- Documents có email kiểu string phải unique với các documents cũng được index.

Một ví dụ với tenant:

```javascript
db.contacts.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    name: "uk_tenant_email_string",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

**Đây là policy cần được cân nhắc**: BSON field email sai kiểu số/object có thể bị bỏ ngoài unique partial index. Dùng schema validation để đảm bảo chỉ những kiểu được phép xuất hiện.

### Partial index và query planner

Query muốn dùng partial index phải có predicate phù hợp để không bỏ sót documents ngoài subset. Tính duy nhất của index vẫn được MongoDB áp cho documents thuộc partial filter, nhưng hiệu năng truy vấn còn phụ thuộc predicate/collation/index selection.

## 22. Sparse unique index khác partial unique index

Một sparse unique index có thể bỏ qua documents **thiếu field** theo semantics sparse, nhưng không nhất thiết bỏ qua documents mà field hiện diện với `null`.

Ví dụ:

```javascript
db.customers.createIndex(
  { alternateEmail: 1 },
  { unique: true, sparse: true }
);
```

Hãy phân biệt:

| Trạng thái | Unique single-field thường | Unique sparse | Partial `$type:"string"` |
| --- | --- | --- | --- |
| Missing field | Tham gia key null | Thường không index | Không index |
| Field = null | Tham gia key null | Field hiện diện, có thể được index | Không index |
| Field = string | Unique | Unique | Unique |

Không thay `partialFilterExpression` bằng `sparse:true` mà chưa xét tài liệu có explicit BSON Null. MongoDB giới hạn một số cách phối hợp index options; tra manual theo server version.

## 23. Collation và duplicate không phân biệt hoa thường

Giả sử:

```text
Alice@Example.invalid
alice@example.invalid
```

Nếu index dùng collation có so sánh case-insensitive phù hợp, hai giá trị trên có thể được coi trùng:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    name: "uk_email_case_insensitive",
    unique: true,
    collation: { locale: "en", strength: 2 }
  }
);
```

Chạy insert thứ hai có thể E11000 dù hai strings có khác case.

### Filter upsert cũng phải thống nhất collation

Nếu unique index không phân biệt case nhưng upsert filter **dùng simple/default collation khác**, query có thể không match document hiện hữu, dẫn tới cố insert và va vào unique index.

Ví dụ:

```javascript
db.users.updateOne(
  { email: "alice@example.invalid" },
  { $setOnInsert: { createdAt: new Date() } },
  {
    upsert: true,
    collation: { locale: "en", strength: 2 }
  }
);
```

Collation của query phải được chọn theo business identity/index strategy; không cứ thêm collation tùy ý rồi coi là chữa mọi E11000.

### Canonicalization ở ứng dụng

Ngoài collation, ứng dụng có thể lưu `normalizedEmail` theo quy tắc đã định nghĩa và unique index trên field đó. Khi normalize Unicode, case, whitespace và domain-specific email semantics phải được kiểm thử. Không tự suy rằng tất cả email providers coi dấu chấm, dấu cộng hoặc local part giống nhau.

## 24. Multikey unique index có điểm đặc biệt

Khi index áp trên một array field, MongoDB có thể tạo nhiều index keys từ các phần tử. Unique constraint ngăn **các documents khác nhau** tạo cùng index key. Các phần tử lặp trong **cùng một document** có những semantics riêng: một unique multikey index không đơn thuần là validator “mọi phần tử trong array phải khác nhau”.

Ví dụ:

```javascript
db.members.createIndex(
  { emails: 1 },
  { unique: true }
);
```

Không kết luận index này chắc chắn từ chối:

```javascript
{ _id: 1, emails: ["a@example.invalid", "a@example.invalid"] }
```

chỉ vì một array chứa duplicate nội bộ. Mục tiêu của unique index khác một JSON Schema validator cho tính độc nhất của các phần tử trong cùng mảng.

Nếu business rule yêu cầu một document không chứa phần tử trùng, hãy kiểm tra ở tầng schema/application hoặc dùng update operators/conditions phù hợp.

## 25. Một document có nhiều unique constraints

Giả sử:

```javascript
db.users.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, name: "uk_tenant_email" }
);

db.users.createIndex(
  { tenantId: 1, externalUserId: 1 },
  { unique: true, name: "uk_tenant_external_user" }
);
```

Một upsert filter theo `(tenantId,externalUserId)` có thể match đúng business user, nhưng update cố gán `email` đã thuộc user khác → E11000 trên **`uk_tenant_email`**.

Vì vậy:

- Filter matching đúng unique key **không bảo đảm không có lỗi từ index khác**.
- Không nên catch E11000 rồi đọc chỉ theo `externalUserId` và luôn trả success.
- Cần xác định **index nào thất bại** và quy tắc resolve corresponding business conflict.

Một system có nhiều external identifiers phải quản lý tính nhất quán giữa chúng theo policy, có thể cần transaction hoặc workflow riêng nếu ảnh hưởng nhiều documents.

## 26. Sharded cluster và unique constraints

Trên sharded collections, khả năng enforce unique index across shards có **quy tắc liên quan shard key và unique index key pattern**. Thông thường một unique index trên sharded collection phải đáp ứng yêu cầu prefix shard key theo tài liệu server version; các trường hợp `_id` và hashed indexes có chi tiết riêng.

Ví dụ:

```text
Shard key: { tenantId: 1 }

Ứng dụng muốn unique:
  (tenantId, requestId)
```

Thiết kế này cần đánh giá routing và quy tắc unique index của sharded collection. Không tự cho rằng unique `requestId` toàn cluster được thực thi chỉ vì có một local index trên từng shard.

### Upsert sharded collections có version-specific behavior

MongoDB 8.0 đã thay đổi một số yêu cầu với `upsert:true` trên sharded collections, ví dụ không còn luôn bắt buộc filter chứa toàn bộ shard key. Nhưng:

- Điều kiện định tuyến/shard-key modifications vẫn có những restrictions.
- Unique enforcement vẫn phụ thuộc index support và topology.
- Filter business identity phải đúng, bất kể server có cho phép operation chạy.

Nếu E11000 chỉ xuất hiện ở sharded deployment hoặc khi migrate topology, cần ghi rõ **server version, shard key, unique index definitions và route qua mongos**, không chỉ xem Java method.

## 27. Lỗi khi tạo unique index trên dữ liệu đã trùng

Một migration:

```javascript
db.customers.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, name: "uk_tenant_email" }
);
```

có thể thất bại nếu collection hiện có duplicates. MongoDB không tự chọn document nào để xóa.

### Tìm duplicates bằng aggregation

```javascript
db.customers.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        email: "$email"
      },
      count: { $sum: 1 },
      sampleIds: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 50 }
]);
```

**Chỉ dùng pipeline minh họa trên tập phù hợp**: `$push` toàn bộ IDs của một nhóm cực lớn có thể làm tài liệu tổng hợp vượt giới hạn. Trong production, thiết kế báo cáo theo batch/top-N, giới hạn memory và lưu key list theo quy trình an toàn.

### Tại sao không xóa bản ghi trùng ngay?

Hai bản ghi cùng email có thể có:

- Orders/payments/references khác nhau.
- Quyền sở hữu hoặc tenant khác do dữ liệu sai.
- Timestamp khác nhưng không chắc bản mới hơn là bản chuẩn.
- Payload nhạy cảm không được merge tự động.

Phải xác định source of truth, tham chiếu liên collection, chính sách giữ/xóa và audit. Sau cleanup mới tạo unique index và kiểm thử concurrent writes.

## 28. Phân biệt lỗi E11000 với lỗi lược đồ BSON

Ví dụ:

```javascript
{ _id: "A", externalId: "1001" }
{ _id: "B", externalId: NumberLong("1001") }
```

Hai giá trị trên khác BSON type (string và numeric). Một unique index có thể xem chúng không cùng key, nhưng application lại coi chúng là cùng external ID khi convert sang string. Đây là **logical duplicate** mà unique index theo BSON values chưa chắc ngăn được.

Ngược lại, MongoDB có quy tắc so sánh chung cho một số numeric BSON types; không nên dựa vào việc Int32/Int64/Double khác class Java để mặc định chúng luôn unique khác nhau.

### Bài học

1. Chuẩn hóa BSON type trước khi tạo unique index.
2. Đồng bộ schema giữa Java, Spring Data, API và migration scripts.
3. Không trộn ObjectId và string hex cho cùng một loại identity.
4. Nếu dùng UUID, thống nhất BSON binary subtype và representation.
5. Nếu dùng email/phone, chọn normalization rõ ràng.

Unique index chỉ enforce uniqueness theo **MongoDB key semantics thực tế**, không phải mọi khái niệm tương đương của application.

## 29. Java Sync Driver: bắt E11000 đúng loại

Giả sử collection:

```java
MongoCollection<Document> requests =
    database.getCollection("payment_requests");
```

Java Sync Driver:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;

Document doc = new Document("tenantId", "tenant-a")
    .append("requestId", "REQ-1001")
    .append("payloadHash", "hash-001");

try {
    InsertOneResult result = requests.insertOne(doc);
    System.out.println(result.getInsertedId());
} catch (MongoWriteException ex) {
    if (ex.getError().getCode() == 11000) {
        // Duplicate unique key: phân loại key và xử lý nghiệp vụ.
        // Không mặc định success.
        throw ex;
    }
    throw ex;
}
```

Các operations có thể ném exception khác nhau tùy driver/server/API:

- `MongoWriteException` cho nhiều single-write failures.
- `MongoBulkWriteException` cho bulk writes.
- `MongoCommandException` cho một số command errors (ví dụ index management).
- `MongoException` cho nhóm lỗi tổng quát.

Không chỉ catch `Exception` rồi tìm substring `"E11000"` khi có thể đọc **error code 11000** qua structured driver API.

### Exception type có thể bị Spring chuyển đổi

Khi dùng `MongoTemplate` hoặc repository, Spring Data có exception translation. Bạn có thể nhận `org.springframework.dao.DuplicateKeyException` thay vì raw driver exception. Đừng dùng cùng một `catch (MongoWriteException)` cho mọi framework code path.

## 30. Java Sync Driver: idempotent upsert thực tế

Ví dụ service cố “đăng ký một request chỉ một lần”, dùng unique index `{tenantId:1,requestId:1}`:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;
import java.util.Objects;

public final class RequestRegistration {

    public static Document register(
            MongoCollection<Document> collection,
            String tenantId,
            String requestId,
            String payloadHash) {

        var filter = Filters.and(
            Filters.eq("tenantId", tenantId),
            Filters.eq("requestId", requestId)
        );

        var update = Updates.combine(
            Updates.setOnInsert("payloadHash", payloadHash),
            Updates.setOnInsert("createdAt", new Date()),
            Updates.setOnInsert("status", "RECEIVED")
        );

        try {
            UpdateResult result = collection.updateOne(
                filter, update,
                new UpdateOptions().upsert(true)
            );
            // result.getUpsertedId() != null nếu vừa insert.
        } catch (MongoWriteException ex) {
            if (ex.getError().getCode() != 11000) {
                throw ex;
            }

            // Có thể là request trùng hoặc unique index khác.
            // Đọc lại và so nội dung trước khi kết luận.
            Document existing = collection.find(filter).first();
            if (existing == null ||
                !Objects.equals(
                    existing.getString("payloadHash"), payloadHash)) {
                throw ex;
            }

            return existing;
        }

        Document existing = collection.find(filter).first();
        if (existing == null) {
            throw new IllegalStateException(
                "Không tìm thấy request sau upsert");
        }

        if (!Objects.equals(
                existing.getString("payloadHash"), payloadHash)) {
            throw new IllegalStateException(
                "Cùng requestId nhưng payload khác");
        }

        return existing;
    }
}
```

Lưu ý phạm vi ví dụ:

- Client cần **acknowledged write concern** để quan sát kết quả.
- Unique index phải được tạo thành công trước khi chạy.
- Dữ liệu `tenantId/requestId` cần được validate và normalize phù hợp.
- Nếu duplicate đến từ unique index **khác**, đoạn code chỉ có thể kết luận idempotent nếu existing theo filter có payload tương đương và policy cho phép; production nên phân loại **index/key thật** thay vì dựa duy nhất vào lần đọc lại.
- Giữa upsert và read, document có thể bị xóa/đổi bởi worker khác; service cần thiết kế retention/state transitions.
- Nếu kết quả read trả `status:"RECEIVED"`, không có nghĩa **payment đã xử lý xong**.
- Production cần exception riêng cho **same key/different payload**, không dùng `IllegalStateException` như public API contract.

### Vì sao code không tự xử lý payment?

Đây chỉ là bước **đăng ký request**. Nếu cả hai workers cùng gọi payment provider ngay khi method trả Document, sẽ có nguy cơ xử lý trùng. Cần thêm **atomic claim/state transition**, outbox hoặc transaction/workflow được thiết kế riêng.

## 31. Idempotent upsert khác “update mọi lần đến”

So sánh:

```javascript
// Nhánh A: bảo vệ dữ liệu đầu tiên.
db.requests.updateOne(
  { requestId: "REQ-1001" },
  { $setOnInsert: { payloadHash: "hash-001" } },
  { upsert: true }
);
```

và:

```javascript
// Nhánh B: request sau ghi đè.
db.requests.updateOne(
  { requestId: "REQ-1001" },
  { $set: { payloadHash: "hash-002" } },
  { upsert: true }
);
```

Nhánh A giữ payload đầu. Nhánh B sửa payload khi record đã tồn tại.

Với idempotency key, thông thường không nên cho một request với cùng key nhưng nội dung khác ghi đè dữ liệu ban đầu. Điều này không có nghĩa không bao giờ được update trạng thái; **status/result** có thể thay đổi theo state machine được kiểm soát và các cập nhật đó nên có điều kiện riêng.

## 32. Xử lý xung đột theo state machine

Ví dụ trạng thái:

```text
RECEIVED
   |
   v
PROCESSING
   |
   +--> SUCCEEDED
   |
   +--> FAILED
```

Một worker phải **claim** task bằng conditional update:

```javascript
db.payment_requests.findOneAndUpdate(
  {
    tenantId: "tenant-a",
    requestId: "REQ-1001",
    status: "RECEIVED"
  },
  {
    $set: {
      status: "PROCESSING",
      workerId: "worker-a",
      claimedAt: new Date()
    }
  },
  { returnDocument: "after" }
);
```

Trong tình huống nhiều workers cùng claim, chỉ operation có điều kiện khớp trạng thái mới được cập nhật trước theo atomicity single-document.

**Không bật `upsert:true` cho claim operation này**. Nếu request tồn tại nhưng đã PROCESSING hoặc SUCCEEDED, upsert cố insert có thể nhận E11000; lỗi nằm ở việc state transition đáng ra chỉ là update có điều kiện.

### Một lần claim chưa bảo đảm exactly-once side effect

Nếu worker crash sau khi gọi payment provider nhưng trước khi ghi SUCCEEDED, worker khác có thể phải retry; không thể suy từ MongoDB status rằng payment chưa xảy ra. Dùng idempotency key tại provider, recovery procedure và transactional outbox phù hợp.

## 33. FindOneAndUpdate với upsert và E11000

`findOneAndUpdate()` có thể tìm/insert và trả document theo options. Ví dụ:

```javascript
db.requests.findOneAndUpdate(
  { requestId: "REQ-1001" },
  { $setOnInsert: { createdAt: new Date(), state: "NEW" } },
  { upsert: true, returnDocument: "after" }
);
```

Nếu concurrent upserts đụng unique index, semantics giải quyết có thể giống cơ chế nêu ở mục upsert: một writer insert, writer khác cập nhật hoặc gặp E11000 theo điều kiện.

**`returnDocument:"after"` không tự xử lý duplicate**. Khi command ném E11000, client không nhận bình thường một document mới như thể thành công; code phải catch, đọc lại, đối chiếu payload và phân loại.

### Khi chỉ cần record nếu tồn tại

Nếu operation chỉ muốn cập nhật một record có sẵn, dùng `upsert:false` và xác nhận null/no-match. Không bật upsert theo thói quen ở mọi `findOneAndUpdate()`.

## 34. Spring Data MongoDB: unique index mapping

Với Spring Data, có thể khai báo unique index bằng annotation:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "payment_requests")
@CompoundIndex(
    name = "uk_tenant_request",
    def = "{'tenantId': 1, 'requestId': 1}",
    unique = true
)
public class PaymentRequest {
    @Id
    private String id;
    private String tenantId;
    private String requestId;
    private String payloadHash;

    public PaymentRequest() {}
    // Getters/setters hoặc mapping phù hợp được khai báo thêm.
}
```

**Annotation không phải bằng chứng index đã tồn tại trong production.** Spring Data có cấu hình quản lý auto-index-creation, migration/index operations và lifecycle riêng; nhiều ứng dụng disable auto-index-creation để kiểm soát schema changes. Phải kiểm tra index thực tế:

```javascript
db.payment_requests.getIndexes();
```

Nếu code deploy annotation nhưng unique index chưa được tạo, concurrent upserts vẫn có thể tạo duplicates.

### Index migration

Nếu muốn tạo index qua `MongoTemplate`:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

Index index = new Index()
    .on("tenantId", Sort.Direction.ASC)
    .on("requestId", Sort.Direction.ASC)
    .unique()
    .named("uk_tenant_request");

template.indexOps("payment_requests").ensureIndex(index);
```

Lệnh này thay đổi schema/index. Trong production phải chạy theo migration policy, sau khi đã kiểm tra dữ liệu hiện có không trùng và có đủ quyền/tài nguyên.

## 35. Spring Data: catch `DuplicateKeyException`

Spring thường dịch lỗi MongoDB duplicate key sang:

```java
import org.springframework.dao.DuplicateKeyException;
```

Ví dụ:

```java
try {
    paymentRequestRepository.insert(entity);
} catch (DuplicateKeyException ex) {
    // Xác định đã có record theo business key,
    // đối chiếu payloadHash/status rồi trả kết quả phù hợp.
    throw ex;
}
```

**Không tự coi mọi `DuplicateKeyException` là cùng request**, vì có thể trùng `_id` hoặc unique index khác. Khi cần xác định index, kiểm tra root cause/structured error hoặc dùng logs đã sanitize, và so state bằng business key với chính sách rõ ràng.

### Repository.save không phải “upsert theo email”

`save(entity)` thường dựa vào entity identity như `_id` và mapping lifecycle. Nó không tự tìm business key `email` hoặc `requestId` chỉ vì field ấy có unique index.

Hai entities khác `_id` nhưng cùng `requestId` có thể khiến `save()` của entity thứ hai nhận E11000; không có nghĩa Spring đã tự gộp chúng thành một object.

## 36. Spring Data: `MongoTemplate.upsert()`

Ví dụ:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("requestId").is("REQ-1001")
);

Update update = new Update()
    .setOnInsert("payloadHash", "hash-001")
    .setOnInsert("status", "RECEIVED")
    .setOnInsert("createdAt", new java.util.Date());

UpdateResult result = template.upsert(
    query, update, PaymentRequest.class);
```

Đây là upsert ở cấp MongoDB theo filter được biểu diễn qua Spring Data. Nếu unique index và query không nhất quán, E11000 vẫn xảy ra.

### Cẩn thận với `@Version`

Nếu entity có `@Version` để chống lost update, không mặc định mọi `template.upsert()` hoặc raw update đều enforce optimistic locking như `repository.save(entity)`. Một số Spring Data update operations có thể tự tăng version field, nhưng **tăng version không đồng nghĩa có predicate expectedVersion**.

Khi cần CAS, đưa expectedVersion/business condition vào **cùng query update**. Nếu chỉ đăng ký idempotency request mới, hãy tách rõ bước create-only và bước chuyển state.

## 37. HTTP API nên trả gì khi có duplicate?

Không có một HTTP status đúng cho mọi E11000. Cần dựa vào business semantics.

| Tình huống | Xử lý API thường cân nhắc |
| --- | --- |
| POST tạo user mới, email đã thuộc người khác | `409 Conflict` |
| POST idempotent cùng key, payload tương đương và kết quả đã có | Trả lại kết quả trước đó theo contract |
| Cùng idempotency key, payload khác | `409 Conflict` hoặc lỗi tương đương |
| Update status sai lifecycle | `409 Conflict` hoặc domain error |
| E11000 do index khác không thuộc request key | Không đổi thành idempotent success; điều tra |
| MongoDB authentication/network failure | Lỗi hạ tầng, không phải duplicate business |
| Input thiếu field bắt buộc | Validation error, thường `400` hoặc `422` theo contract |

**Không trả raw `dup key: { email: ... }` cho client** nếu có thể tiết lộ PII hoặc sự tồn tại của tài khoản người khác. Có thể dùng thông báo trung tính theo security policy.

## 38. Retryable writes, timeout và E11000

Một request có thể:

1. Được server apply thành công.
2. Nhưng client mất kết nối **trước khi nhận acknowledgment**.
3. Client/app thực hiện lại request.
4. Lần sau gặp duplicate key do record đã tồn tại.

E11000 trong tình huống này **không chứng minh lần đầu thất bại**. Tuy nhiên, nó cũng không đủ chứng minh lần đầu thành công **đúng payload**.

### Phân biệt retry ở tầng driver và application

MongoDB drivers có hỗ trợ **retryable writes** trong các điều kiện deployment/operation phù hợp. Điều này không biến mọi nghiệp vụ thành idempotent và không bảo đảm mọi lỗi sẽ được retry.

Application retry khi không rõ kết quả cần:

- Giữ nguyên business idempotency key.
- Đọc lại result theo unique key.
- So canonical payload/fingerprint.
- Dựa trên trạng thái processing/result để trả response.
- Không tạo ObjectId/requestId mới mỗi lần retry nếu intent là cùng request.
- Không gọi external payment/email hai lần mà không có idempotency protection.

### WriteConcern timeout không phải duplicate

`wtimeout` nói về điều kiện xác nhận write; thao tác có thể đã được áp dụng. Sau timeout, **đừng lập tức tạo document mới với key mới**. Hãy đối soát theo stable identity và theo dõi replication/commit state phù hợp.

## 39. Trong transaction có thể gặp E11000 không?

Có. Một transaction có thể insert/update những documents vi phạm unique index và nhận duplicate key failure.

Transactions giải quyết atomicity của những operations thuộc transaction theo semantics được hỗ trợ; chúng **không cho phép phá unique constraint**.

Ví dụ luồng:

```text
Transaction:
  insert payment_requests(key=REQ-1001)
  update orders(status=PAID)

Nếu insert vi phạm unique index:
  Transaction không thể coi như thành công bình thường.
  Phải xử lý lỗi/abort/retry theo contract.
```

### Không retry cả transaction một cách mù quáng

Lỗi `TransientTransactionError` và `UnknownTransactionCommitResult` có semantics retry riêng. E11000 là **business/data constraint violation**; không được tự gộp mọi E11000 vào transient retry loop.

Nếu một phiên bản server có behavior retry upsert khác giữa transaction và ngoài transaction, cần tra release notes tương ứng. Đặc biệt không gọi external side effect không idempotent trong phần transaction callback có thể được retry.

## 40. Bulk writes: một lỗi không có nghĩa cả batch rollback

Giả sử:

```javascript
db.events.insertMany(
  [
    { _id: "E1", externalId: "A" },
    { _id: "E2", externalId: "A" },
    { _id: "E3", externalId: "B" }
  ],
  { ordered: false }
);
```

Nếu có unique index trên `externalId`:

- Có operation tạo key A thành công.
- Operation còn lại với A bị E11000.
- Với `ordered:false`, những operations khác có thể vẫn được thực hiện; đây **không phải transaction atomic toàn batch**.

### Ordered vs unordered

| Kiểu bulk | Khi gặp write error |
| --- | --- |
| `ordered:true` | Thường dừng xử lý các thao tác tiếp theo theo thứ tự đã đặt |
| `ordered:false` | Có thể tiếp tục các thao tác còn lại; không giả định thứ tự hoàn tất |

Không lấy tổng số lỗi/đếm inserted rồi coi rằng mọi intended records đã được xử lý. Cần đọc **writeErrors với index trong batch**, successes, writeConcernErrors và đối chiếu business keys.

### Java driver

Một bulk operation có thể ném `MongoBulkWriteException` và cung cấp danh sách write errors, mỗi lỗi có code/index để biết operation nào thất bại.

Không parse một stack trace dài rồi xóa cả batch/collection để retry. Với dữ liệu tài chính hoặc events, từng operation cần idempotency key và policy retry riêng.

## 41. Kiểm tra index và dữ liệu mà không thay đổi production

Các lệnh **chỉ đọc**:

```javascript
const target = db.getSiblingDB("shop");

target.payment_requests.getIndexes();

target.payment_requests.find(
  { tenantId: "tenant-a", requestId: "REQ-1001" },
  {
    _id: 1,
    tenantId: 1,
    requestId: 1,
    payloadHash: 1,
    status: 1
  }
);
```

Xác minh:

1. Index được báo trong E11000 có tồn tại?
2. Key pattern, `unique`, `collation`, `partialFilterExpression`, `sparse` là gì?
3. Query thực sự sử dụng những fields/types/normalization nào?
4. Existing document có cùng business identity hay chỉ va vào index khác?
5. Có key `null`/missing hoặc field bị viết sai BSON type không?
6. Server/driver version và topology có khác lúc incident trước không?

**Không cần drop unique index để điều tra.** Bỏ constraint có thể khiến application ghi thêm duplicates và làm cleanup khó hơn.

## 42. Cách khảo sát dữ liệu null/missing và mixed types

Khi error có `dup key: { email: null }`, kiểm tra:

```javascript
db.getSiblingDB("shop").customers.find(
  { email: null },
  { _id: 1, email: 1, tenantId: 1 }
).limit(50);
```

Truy vấn `{email:null}` match cả **BSON Null và missing field**. Nếu cần phân biệt:

```javascript
// Chỉ field có BSON Null:
db.customers.find({ email: { $type: 10 } });

// Chỉ field không tồn tại:
db.customers.find({ email: { $exists: false } });
```

Kiểm tra BSON types:

```javascript
db.customers.aggregate([
  {
    $project: {
      emailType: { $type: "$email" },
      tenantType: { $type: "$tenantId" }
    }
  },
  { $limit: 50 }
]);
```

Nếu unique key được thiết kế cho string nhưng data chứa null/object/array, cần giải quyết schema validation/migration, không chỉ sửa upsert code.

## 43. Lỗi upsert do điều kiện status khác version conflict

Một document:

```javascript
{
  _id: "order-1001",
  externalId: "EXT-1001",
  status: "SHIPPED",
  version: NumberLong("8")
}
```

Service muốn cập nhật:

```javascript
db.orders.updateOne(
  {
    externalId: "EXT-1001",
    status: "NEW",
    version: NumberLong("7")
  },
  { $set: { status: "CANCELLED" } },
  { upsert: true }
);
```

Vì document đã SHIPPED/version 8:

- Filter không match.
- Upsert cố insert một document mới với `externalId:"EXT-1001"`.
- Unique index trên externalId có thể báo E11000.

Tuy nhiên ý nghĩa nghiệp vụ là **request stale hoặc transition không hợp lệ**, không phải “phải tạo order khác”.

### Sửa semantics

Sử dụng **update có điều kiện nhưng không upsert**:

```javascript
db.orders.updateOne(
  {
    externalId: "EXT-1001",
    status: "NEW",
    version: NumberLong("7")
  },
  {
    $set: { status: "CANCELLED" },
    $inc: { version: NumberLong("1") }
  }
);
```

Nếu `matchedCount=0`, API trả conflict/not-found theo policy. Không dùng upsert để “tự sửa” stale version.

**Quy tắc:** upsert phù hợp “được phép tạo nếu business identity chưa tồn tại”. State transition trên entity bắt buộc đã có thường **không nên upsert**.

## 44. Đừng tự động bỏ unique index để chữa E11000

Anti-pattern:

```javascript
// KHÔNG chạy trên production để 'sửa nhanh' duplicate:
db.payment_requests.dropIndex("uk_tenant_request");
```

Điều này loại bỏ chốt chặn dữ liệu:

- Hai requests cùng key có thể tạo hai payment intents.
- Bảng quan hệ nghiệp vụ có thể sinh duplicates khó reconcile.
- Khả năng build lại index sau đó có thể thất bại vì duplicates mới.
- Một số thành phần khác dựa vào unique invariant có thể hỏng.

Phương án phù hợp hơn:

1. Ghi lại full error/index definition.
2. Phân loại duplicate key nào xảy ra.
3. Kiểm tra request/filter/update semantics.
4. Quyết định giữ existing record, trả conflict hay migration.
5. Cập nhật application code và test.
6. Chỉ đổi index definition khi **business requirement thật sự thay đổi** và đã có rollout/cleanup plan.

## 45. Runbook điều tra E11000 theo từng bước

### Bước A — Khoanh vùng lỗi

Thu thập:

```text
Incident ID:
Timestamp:
Environment / cluster:
Namespace:
Operation: insertOne/updateOne/findOneAndUpdate/bulk/index build
Error code: 11000
Index name:
Key pattern:
Sanitized key value:
Server version/topology:
Driver/framework version:
Correlation ID:
Business request identity:
```

Không dán raw credentials, PII hoặc toàn bộ request body chứa secrets vào ticket.

### Bước B — Phân loại operation

```text
E11000
  |
  +--> INSERT: key đã tồn tại? retry mơ hồ?
  |
  +--> UPDATE: field thuộc unique index bị đổi thành key trùng?
  |
  +--> UPSERT: filter không match dù business key đã tồn tại?
  |            race nhiều writers?
  |            filter/index equality mismatch?
  |
  +--> INDEX BUILD: dữ liệu hiện hữu đã trùng?
  |
  +--> BULK: operation nào failed, operation nào đã thành công?
```

### Bước C — Kiểm tra index

```javascript
db.getSiblingDB("shop")
  .payment_requests.getIndexes();
```

Xem `unique`, `key`, `name`, `partialFilterExpression`, `sparse`, `collation` và topology. Không kết luận chỉ dựa vào index name.

### Bước D — Đối chiếu existing record

Query bằng **business unique key**; khi cần, query theo keyValue của lỗi bằng user đủ quyền trên môi trường được duyệt. Đánh giá payload hash, status và các liên kết.

### Bước E — Xác định root cause

Các nhóm thường gặp:

1. Request hợp lệ đến lặp (retry/idempotency).
2. Concurrent upserts trên unique key.
3. Upsert filter chứa status/version/range gây no-match.
4. Unique index/key scope không đồng bộ với tenant model.
5. Unique index optional field với null/missing.
6. Collation/normalization khác nhau giữa query/index.
7. Code cập nhật một unique field thành giá trị trùng.
8. Index migration gặp dữ liệu trùng đã tồn tại.
9. Mixed BSON types hoặc thay đổi schema.
10. Không rõ kết quả sau timeout/network/failover.

### Bước F — Khôi phục an toàn

- Không xóa/replace existing document nếu chưa có owner nghiệp vụ xác nhận.
- Với same key/same payload, dùng idempotent response/state reconciliation.
- Với same key/different payload, trả conflict và lưu audit phù hợp.
- Với migration duplicates, lập danh sách tham chiếu, cleanup theo plan và tạo index có kiểm soát.
- Với lỗi hệ thống, có retry/backoff bounded và idempotency.
- Khi cần thay logic upsert, ưu tiên staging/load test trước production.

### Bước G — Xác minh sau sửa

- Unique index còn hoạt động.
- Concurrent requests không tạo hai documents cùng business key.
- Request trùng đúng payload không thực thi side effect lặp.
- Request trùng khác payload được từ chối.
- Không phát sinh lỗi validation/network/authorization bị mask thành duplicate.
- Metrics lỗi, latency và write throughput ổn định.

## 46. Test concurrency với hai workers

Một integration test nên dùng **MongoDB thật có unique index thật**, không chỉ mock repository.

Ví dụ cấu trúc:

```text
Setup:
  create unique index (tenantId,requestId)
  delete fixture REQ-RACE-01 trong test DB

Thread A:
  await barrier
  upsert REQ-RACE-01

Thread B:
  await barrier
  upsert REQ-RACE-01

Assertions:
  countDocuments({tenantId,requestId}) == 1
  stored payloadHash đúng policy
  không có unwanted side effect lặp
  mỗi outcome thuộc allowed set (insert/update/E11000 được xử lý)
```

### Vì sao không assert “chắc chắn một E11000”?

MongoDB có thể cho operation thứ hai **update record vừa insert** khi điều kiện upsert cùng unique index thỏa. Test không nên phụ thuộc một race order hoặc đúng một loại lỗi nếu business invariant chỉ là **một record và response hợp lệ**.

### Test cố ý tạo E11000 ổn định

Để kiểm tra error mapping, dùng một test **tuần tự** chèn hai documents với cùng unique key trên collection lab. Đó là cách ổn định hơn test race ngẫu nhiên để chứng minh exception translation.

### Test worker đồng thời

Nếu dùng Java `CountDownLatch` hoặc `CyclicBarrier`, cần:

- Hai tasks có client/collection handles an toàn theo driver contract.
- Mỗi task có request context riêng.
- Cùng start barrier nhưng không giả định thread scheduling.
- Bounded timeout để test không treo.
- Đọc count final bằng acknowledged read có consistency phù hợp.
- Dọn test documents sau khi cả hai tasks hoàn tất.

## 47. Ma trận kiểm thử upsert cần có

| Case | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| UPSERT-01 | Chưa có key, một request | Insert một record |
| UPSERT-02 | Đã có key, payload giống | Giữ idempotent state, không ghi đè |
| UPSERT-03 | Đã có key, payload khác | Conflict, không thay existing payload |
| UPSERT-04 | Hai requests đồng thời cùng key | Chỉ một record cuối cùng |
| UPSERT-05 | Hai requests khác tenant, cùng requestId | Mỗi tenant có record riêng nếu policy |
| UPSERT-06 | Filter thêm status gây no-match | Không tạo record sai; xử lý conflict |
| UPSERT-07 | Một field optional bị null/missing | Unique/partial policy đúng |
| UPSERT-08 | Email khác case | Theo collation/normalization đã chọn |
| UPSERT-09 | Duplicate do secondary index khác | Không nhầm với idempotent request |
| UPSERT-10 | Timeout sau write | Retry cùng key, reconcile outcome |
| UPSERT-11 | Bulk có một duplicate | Đối soát partial successes |
| UPSERT-12 | Unique index chưa được deploy | Test fail, không chấp nhận duplicates |
| UPSERT-13 | Legacy mixed BSON types | Migration/validation có kế hoạch |
| UPSERT-14 | Duplicate ở sharded deployment | Enforce theo shard/index constraints |
| UPSERT-15 | Worker claim status đã PROCESSING | No-match, không upsert mới |

Một test suite tốt phải có cả positive, negative và concurrency cases. Đừng coi “thử 100 lần không thấy E11000” là bằng chứng race không thể xảy ra.

## 48. Logging và monitoring cho duplicate key

Các metrics hữu ích:

| Signal | Ý nghĩa |
| --- | --- |
| E11000 count theo namespace/index | Xác định constraint đang gây lỗi |
| E11000 rate theo endpoint/service | Phân biệt API tạo mới và background job |
| Upsert inserted vs matched ratio | Quan sát hành vi create/update |
| Retry attempts/success | Phát hiện retry storm |
| Idempotency hit rate | Tỷ lệ requests lặp hợp lệ |
| Same-key different-payload conflicts | Chỉ báo bug hoặc misuse API |
| Duplicate key during migration | Dữ liệu legacy chưa sạch |
| Write concern/network timeout | Có thể liên quan kết quả mơ hồ |
| MongoDB index build failures | Schema deployment chưa hoàn tất |
| Payment/event side-effect duplicates | Sự cố nghiệp vụ nghiêm trọng |

Log có thể có:

```json
{
  "event": "MONGODB_DUPLICATE_KEY",
  "errorCode": 11000,
  "namespace": "shop.payment_requests",
  "indexName": "uk_tenant_request",
  "operation": "upsert",
  "correlationId": "req-abc123",
  "businessKeyHash": "redacted-hash",
  "handledAs": "IDEMPOTENT_REPLAY"
}
```

Đây là schema log minh họa. Không log raw email/phone/secret hoặc toàn bộ payload khi không được phép. Với high-volume retry, cần aggregation/sampling hợp lý và alert theo tỷ lệ thay vì gửi cảnh báo cho mọi duplicate mong đợi.

## 49. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “E11000 nghĩa là MongoDB đã ghi hai bản trùng” | Unique index thường **đã ngăn** write gây trùng |
| “Chỉ insert mới duplicate” | Update, upsert, bulk và index build cũng có thể lỗi |
| “Cứ đổi `_id` là hết lỗi” | Có thể trùng secondary unique index |
| “Field tên requestId tự unique” | Phải có unique index/constraint thực |
| “Pre-check exists rồi insert an toàn” | Race giữa hai lệnh |
| “Upsert luôn không thể gây E11000” | Filter/index mismatch và concurrency vẫn có thể lỗi |
| “Hai upserts cùng key chắc một E11000” | Server có thể chuyển thành update khi đủ điều kiện |
| “Có unique index là hai requests có payload khác cũng idempotent” | Unique index không kiểm tra payload equivalence |
| “`$set` và `$setOnInsert` như nhau” | Một bên chạy mọi match, một bên chỉ insert |
| “E11000 nào cũng có thể trả HTTP 200” | Có thể là conflict sai payload/index khác |
| “E11000 luôn là lỗi đáng retry” | Constraint violation thường cần business decision |
| “`modifiedCount=0` nghĩa là record không tồn tại” | Có thể matched nhưng không đổi |
| “Thêm status vào upsert filter giúp an toàn” | Có thể gây no-match và duplicate insert |
| “Unique email cho phép bao nhiêu null tùy ý” | Unique single-field thường giới hạn null/missing key |
| “Sparse index bỏ qua null và missing như nhau” | Có khác biệt vì field hiện diện null |
| “Collation không ảnh hưởng duplicate” | Case-insensitive unique index có thể coi strings là trùng |
| “Một unique multikey index cấm mọi duplicate trong một array” | Ràng buộc chủ yếu giữa different documents |
| “Spring @Indexed(unique=true) bảo đảm index đã deploy” | Cần kiểm tra index creation/migration |
| “Repository.save tự upsert theo email” | Save theo entity identity, không phải mọi unique field |
| “Unacknowledged writes vẫn xử lý E11000 đầy đủ” | Không có write result đáng tin cậy |
| “Transaction cho phép bỏ qua unique constraint” | Unique constraint vẫn áp dụng |
| “Bulk write lỗi thì mọi bản ghi rollback” | Có thể partial successes ngoài transaction |
| “Đổi lại index bằng drop là cách sửa nhanh nhất” | Có nguy cơ tạo duplicates thật và mất invariant |
| “Timeout nghĩa là chưa insert” | Write có thể đã thành công nhưng ACK bị mất |

## 50. Bài tập có đáp án

### Bài 1. Đọc lỗi

Lệnh insert báo `E11000 ... index: _id_ dup key: {_id:"A"}`. Kết luận chính?

**Đáp án:** Collection đã có document với `_id:"A"` hoặc một thao tác khác đã tạo cùng ID; cần xác minh trước khi retry hoặc thay ID.

### Bài 2. Unique secondary index

Hai documents có `_id` khác nhưng cùng `email`, collection có unique index trên email. Insert thứ hai thế nào?

**Đáp án:** Bị E11000 trên unique email index. Khác `_id` không làm business unique key hợp lệ.

### Bài 3. Compound key

Unique index `{tenantId:1,email:1}`. Email giống nhau ở tenant A và B có trùng không?

**Đáp án:** Không, nếu tenantId khác và không vi phạm unique constraint khác.

### Bài 4. Update gây duplicate

Document C2 được sửa email bằng email của C1 trong cùng tenant. Kết quả?

**Đáp án:** E11000 nếu unique index trên cặp tenant/email. Duplicate không chỉ có ở insert.

### Bài 5. Ý nghĩa upsert

`upsert:true` làm gì khi filter không match?

**Đáp án:** MongoDB cố insert document mới dựa trên filter và update. Nếu unique key của document mới trùng, có thể E11000.

### Bài 6. Race không index

Hai workers upsert cùng requestId nhưng không có unique index. Có thể có hai documents không?

**Đáp án:** Có, nếu cả hai cùng đi qua giai đoạn no-match trước khi thấy insert của nhau.

### Bài 7. Race có index

Hai workers upsert cùng key có unique index. Có luôn đúng một E11000 không?

**Đáp án:** Không. Một writer insert, writer còn lại có thể update newly inserted document hoặc fail theo điều kiện documented.

### Bài 8. Conditions của server

Unique index `{requestId:1}`, filter `{requestId:"A",status:"NEW"}`. Có khớp đúng index fields cho điều kiện hội tụ không?

**Đáp án:** Không. Filter có thêm status, không cùng tập fields với unique index; có thể E11000.

### Bài 9. Status no-match

Record email Alice có status ACTIVE, upsert filter email Alice + status PENDING. Vì sao có duplicate?

**Đáp án:** Không match existing record do status khác, nhưng nhánh insert vẫn dùng email Alice và va unique email index.

### Bài 10. SetOnInsert

`$setOnInsert: {status:"RECEIVED"}` có ghi đè status của record đã tồn tại không?

**Đáp án:** Không. Nó chỉ áp dụng khi upsert insert mới.

### Bài 11. Set

`$set:{payloadHash:"new"}` dùng trong upsert có thể thay dữ liệu cũ không?

**Đáp án:** Có, nếu filter match existing record. Điều này nguy hiểm với idempotency key khi payload không được phép đổi.

### Bài 12. Lệnh nguy hiểm

Team muốn drop unique index vì E11000 quá nhiều. Vấn đề?

**Đáp án:** Loại bỏ chốt chặn uniqueness, làm phát sinh duplicate thực và có thể không tạo lại được index; phải điều tra root cause.

### Bài 13. Null

Unique single-field index trên email, hai documents đều thiếu email. Insert thứ hai có thể lỗi?

**Đáp án:** Có, vì missing/null có thể tạo cùng index key null theo quy tắc unique index.

### Bài 14. Partial index

Muốn unique email chỉ khi email là BSON String. Có thể dùng gì?

**Đáp án:** Unique partial index với `partialFilterExpression: {email: {$type:"string"}}`, đi kèm schema validation phù hợp.

### Bài 15. Sparse index

Unique sparse index có luôn bỏ qua field hiện diện `null` giống field missing không?

**Đáp án:** Không. Sparse thường bỏ qua missing, còn field hiện diện null có thể được index.

### Bài 16. Collation

Unique email index case-insensitive có thể coi `"Alice"` và `"alice"` là trùng không?

**Đáp án:** Có, tùy collation đã định nghĩa.

### Bài 17. Different unique index

Upsert theo requestId nhưng E11000 index email. Có nên coi đây là idempotent replay cùng requestId?

**Đáp án:** Không. Cần xử lý constraint email theo business policy và xác minh existing record/payload.

### Bài 18. Retry timeout

Insert timeout nhưng server có thể đã ghi. Retry nên tạo requestId mới không?

**Đáp án:** Không nếu intent vẫn là cùng request. Giữ stable key, đối soát existing state và retry idempotent theo policy.

### Bài 19. Java exception

Java Sync Driver single write thường bắt lỗi E11000 qua loại nào?

**Đáp án:** Thường là `MongoWriteException` với `getError().getCode()==11000`; tùy operation còn có bulk/command exceptions.

### Bài 20. Spring Data exception

`MongoTemplate.insert()` có duplicate key và Spring chuyển lỗi. Loại exception nào thường gặp?

**Đáp án:** `org.springframework.dao.DuplicateKeyException`.

### Bài 21. Repository.save

Hai entities khác `_id` nhưng trùng email; dùng repository.save() có tự merge theo email không?

**Đáp án:** Không. Save thường theo entity identity; unique email index có thể báo E11000.

### Bài 22. Index annotation

Có `@CompoundIndex(unique=true)` trong Java class nhưng production chưa có index. Race có thể tạo duplicate không?

**Đáp án:** Có. Phải bảo đảm index được triển khai/kiểm tra thực tế, không chỉ annotation.

### Bài 23. Modified count

Upsert trả `matchedCount=1, modifiedCount=0`. Có nghĩa không tìm thấy document?

**Đáp án:** Không. Document đã match nhưng update không làm thay đổi nội dung.

### Bài 24. Unique multikey

Một unique index trên array có cấm các phần tử trùng trong cùng document không?

**Đáp án:** Không thể coi như validator nội bộ array; unique multikey chủ yếu áp constraint giữa documents theo index keys.

### Bài 25. Bulk writes

InsertMany unordered có một duplicate. Có thể có những inserts khác đã thành công không?

**Đáp án:** Có. Phải xem từng write error và trạng thái cuối, không coi batch tự rollback toàn bộ.

### Bài 26. Transaction

Trong transaction, insert trùng unique key có được phép vì các writes là atomic không?

**Đáp án:** Không. Unique constraints vẫn áp dụng; lỗi phải được xử lý theo transaction/error contract.

### Bài 27. Stale version

Upsert filter chứa `version:7` nhưng record đã version 8, unique externalId giữ nguyên. Tại sao lỗi?

**Đáp án:** No-match do stale version khiến upsert thử insert cùng externalId; đúng ra phải conditional update không upsert và trả conflict.

### Bài 28. Idempotency

Hai requests cùng key nhưng payloadHash khác. Có thể trả success vì unique index đã ngăn duplicate không?

**Đáp án:** Không. Business request không tương đương; cần trả conflict hoặc xử lý theo explicit policy.

### Bài 29. Test race

Integration test kỳ vọng hai concurrent upserts cùng key phải cho **một success và một E11000**. Đây có phải invariant đúng không?

**Đáp án:** Không phải invariant chung. Server có thể hội tụ thành update; invariant nên là chỉ một record và side effects đúng.

### Bài 30. Root cause

E11000 xảy ra khi tạo unique index trên collection đã có dữ liệu. Có nên xóa đại mọi record bị trùng rồi build lại?

**Đáp án:** Không. Phải đối chiếu references, owner nghiệp vụ và policy dedupe trước khi cleanup.

## 51. Checklist trước khi triển khai

### Schema và index

- [ ] Business identity được mô tả rõ (tenant, externalId, requestId, email...).
- [ ] Unique index tồn tại thực tế và đã build thành công.
- [ ] Compound key scope đúng tenant/organization.
- [ ] Optional fields có null/missing policy rõ.
- [ ] Partial/sparse/collation options phù hợp dữ liệu.
- [ ] BSON types và canonicalization đồng nhất giữa writers.
- [ ] Sharded topology có hỗ trợ uniqueness mong muốn.

### Upsert design

- [ ] Chỉ dùng `upsert:true` khi được phép tạo record nếu identity chưa tồn tại.
- [ ] Filter theo identity ổn định; không thêm status/version một cách không cần thiết.
- [ ] Fields create-only nằm trong `$setOnInsert`.
- [ ] Fields mutable trong `$set/$inc` có chính sách rõ.
- [ ] Không sửa unique key fields trong upsert một cách vô ý.
- [ ] Không dùng upsert cho state transition bắt buộc đã tồn tại.
- [ ] Đọc `matchedCount/upsertedId` phù hợp, không nhầm no-op.

### Conflict và idempotency

- [ ] Same key/same payload có response idempotent được định nghĩa.
- [ ] Same key/different payload được báo conflict.
- [ ] E11000 được phân loại theo index và key, không catch-all success.
- [ ] Retry dùng stable idempotency key.
- [ ] Timeout/write concern unknown outcome được đối soát trước khi replay.
- [ ] Payment/email/event side effects có idempotency protection.
- [ ] Logging không làm lộ PII trong `dup key`.

### Kiểm thử và vận hành

- [ ] Có test insert duplicate tuần tự để xác nhận error mapping.
- [ ] Có test concurrent upserts với unique index thật.
- [ ] Có test filter/index mismatch gây no-match.
- [ ] Có test null/missing/partial/collation theo policy.
- [ ] Có test bulk partial successes và retries.
- [ ] Có monitoring lỗi theo namespace/index/endpoint.
- [ ] Có runbook phân biệt E11000 với timeout/validation/WriteConflict.
- [ ] Không bỏ unique index chỉ vì lỗi tăng.

## 52. Tổng kết

**E11000 duplicate key** là lỗi MongoDB báo một write đã xung đột với **unique index**. Khi điều tra, cần tìm **collection, index, key pattern/value và operation thật**, không chỉ nhìn vào một chuỗi message. Lỗi có thể xuất hiện khi insert, update, upsert, bulk import hoặc tạo unique index trên dữ liệu đã trùng.

**Upsert không bảo đảm “đã có bản ghi theo business key thì không bao giờ E11000”**. Nếu filter có thêm status/version hoặc không khớp index, nó có thể không tìm được document đã tồn tại, chuyển sang insert rồi đụng unique constraint. Khi nhiều upserts cùng chạy, một writer insert; writer khác **có thể update record vừa tạo hoặc gặp duplicate key error** theo các điều kiện server hỗ trợ. Thiếu unique index còn nguy hiểm hơn vì có thể tạo nhiều documents trùng.

Thiết kế vững chắc cần **business identity ổn định + unique index đúng phạm vi + filter upsert phù hợp + `$setOnInsert` cho dữ liệu chỉ được tạo một lần + xử lý conflict/idempotency rõ ràng**. Những thao tác chuyển trạng thái phải dùng conditional update thay vì upsert bừa bãi. Nếu có E11000, ứng dụng cần phân biệt request trùng thật sự với payload khác hoặc unique index khác, và không tự retry/suppress mọi lỗi.

Cuối cùng, **unique constraint là một lớp bảo vệ dữ liệu, không phải thứ nên tắt khi lỗi xuất hiện**. Giữ constraint, tìm nguyên nhân, sửa đường ghi, kiểm thử concurrency thật và đo tác động nghiệp vụ mới là cách xử lý sự cố bền vững.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — updateOne and Upsert](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — update (Upsert with Duplicate Values)](https://www.mongodb.com/docs/manual/reference/method/db.collection.update/)
- [MongoDB Manual — findAndModify (Upsert with Unique Index)](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/)
- [MongoDB Manual — insertOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertOne/)
- [MongoDB Manual — $setOnInsert](https://www.mongodb.com/docs/manual/reference/operator/update/setOnInsert/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)

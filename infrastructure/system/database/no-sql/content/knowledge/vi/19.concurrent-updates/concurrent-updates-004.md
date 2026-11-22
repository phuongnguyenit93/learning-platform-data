# Compare-and-set, điều kiện tồn tại và cập nhật có điều kiện

Khi nhiều request cùng cập nhật một bản ghi NoSQL, từng lệnh ghi có thể thành công theo đúng bảo đảm của database nhưng kết quả nghiệp vụ vẫn sai. Một khách hàng mua sản phẩm cuối cùng trong kho đúng lúc khách khác cũng mua; hai nhân viên cùng duyệt một phiếu; hai phiên chỉnh sửa cùng ghi đè hồ sơ; hoặc hai worker cùng nhận một job chưa xử lý.

Điểm chung: ứng dụng **đọc một trạng thái, quyết định hành động, rồi ghi ở thời điểm khác**. Nếu trạng thái thay đổi giữa hai bước, quyết định ban đầu có thể không còn hợp lệ.

**Compare-and-set (CAS)** và **conditional write** bảo vệ những tình huống này bằng cách biến điều kiện và cập nhật thành **một thao tác có bảo đảm nguyên tử trong phạm vi mà hệ NoSQL hỗ trợ**.

> Chỉ ghi khi giá trị/version/trạng thái hiện tại còn đáp ứng điều kiện; nếu không đáp ứng thì không áp thay đổi và báo kết quả điều kiện thất bại.

Bài thuộc chương **Cập nhật đồng thời** trong chủ đề **Database No SQL**. Ví dụ chính dùng MongoDB, đồng thời trình bày DynamoDB, Cassandra Lightweight Transactions, Redis và cách thực hiện từ Java/Spring. Tính đúng đắn phải xét theo tài liệu, phiên bản, consistency level và topology của sản phẩm thực tế.

## 1. Race condition: đọc rồi ghi là chưa đủ

Document tồn kho:

~~~javascript
{
  _id: "shop-17#sku-A",
  available: 1
}
~~~

Hai request cùng đặt một sản phẩm:

~~~text
Request A: READ available=1
Request B: READ available=1
Request A: IF available>=1, WRITE available=0
Request B: IF available>=1, WRITE available=0
Request A: trả BOOKED
Request B: trả BOOKED
~~~

Database cuối cùng vẫn chứa `available=0`, nhưng hệ thống xác nhận hai giao dịch cho một sản phẩm. Lỗi không nằm ở phép trừ; lỗi ở **khoảng thời gian giữa check và act**.

### Check-then-act cần một điểm quyết định nguyên tử

Thay vì:

~~~text
read available
if available >= requested:
    write available - requested
~~~

hãy diễn đạt:

~~~text
ATOMically at source:
    IF available >= requested
    THEN available -= requested
    ELSE conditionFailed
~~~

Engine phải kiểm tra điều kiện trên trạng thái đủ mới theo semantics của phép ghi và thực hiện cập nhật trong cùng atomic unit. Một lần read riêng, dù nhất quán mạnh, vẫn không khóa trạng thái đến tận lệnh write tiếp theo.

## 2. Compare-and-set là gì?

CAS có ba ý tưởng:

1. **Expected:** giá trị hoặc version mà caller đã quan sát và kỳ vọng chưa đổi.
2. **Current:** giá trị hiện hành tại nơi quản lý state.
3. **New state:** cập nhật được thực hiện chỉ khi expected khớp current.

Mã giả:

~~~text
compareAndSet(key, expectedVersion, change):
    atomically:
        if state[key].version != expectedVersion:
            return CONFLICT

        apply(state[key], change)
        state[key].version += 1
        return SUCCESS
~~~

Biểu thức logic với một giá trị đơn:

\[
\operatorname{CAS}(x,e,n)=
\begin{cases}
x\leftarrow n,\ \mathrm{true} & \text{khi }x=e\\
x\text{ giữ nguyên},\ \mathrm{false} & \text{khi }x\ne e
\end{cases}
\]

Trong NoSQL, CAS có thể mang tên khác: MongoDB `updateOne` với filter version, DynamoDB `ConditionExpression`, Cassandra `IF` trong Lightweight Transaction, Redis `WATCH`/`MULTI`/`EXEC` hoặc script Lua.

**Quan trọng hơn tên API là phạm vi nguyên tử**: một document, một item, một row, một partition, hay transaction trên nhiều tài nguyên.

## 3. Các thuật ngữ dễ nhầm

| Thuật ngữ | Trả lời câu hỏi gì? |
|---|---|
| Atomic update | Một update không bị thực hiện nửa chừng trong phạm vi hỗ trợ? |
| Conditional update | Chỉ ghi khi predicate đúng? |
| Compare-and-set | Giá trị/version kỳ vọng có còn bằng hiện tại? |
| Optimistic concurrency control | Có thể phát hiện xung đột lúc ghi, không cần khóa dài khi đọc? |
| Unique constraint | Hai bản ghi có thể cùng dùng một business key không? |
| Insert-if-absent | Một key có thể chỉ được claim khi chưa có? |
| Upsert | Nếu tìm thấy thì update, nếu không thì insert? |
| Idempotency | Retry cùng một ý định có tạo hiệu ứng lặp không? |
| Transaction | Một nhóm thay đổi có commit/abort chung theo phạm vi hỗ trợ không? |
| Consistency | Các client/replica quan sát thứ tự và độ mới ra sao? |

Một ứng dụng có thể cần nhiều cơ chế cùng lúc. Ví dụ Order được tạo duy nhất bằng unique key, stock bị trừ bằng conditional update, request retry được nhận diện bằng idempotency key, còn nhiều document liên quan được ghi theo transaction hoặc workflow.

## 4. Lost update: thay đổi của một người bị ghi đè

Ban đầu:

~~~javascript
{
  _id: "product-101",
  name: "Bàn phím",
  description: "Bản đầu",
  version: NumberLong("7")
}
~~~

Hai người mở form:

~~~text
A đọc version=7, sửa name
B đọc version=7, sửa description
A lưu toàn document từ snapshot version 7
B lưu toàn document từ snapshot version 7
~~~

Nếu B ghi document cũ với một field mới, `name` mà A vừa sửa có thể bị ghi đè trở lại. Đây là **lost update**.

### Cách dùng version

Mỗi người phải nêu `expectedVersion=7` khi ghi. Nếu A được chấp nhận, version thành 8. B còn kỳ vọng 7, nên lệnh ghi của B không áp dụng; B cần tải version mới và quyết định merge.

CAS **phát hiện xung đột**, không tự biết nên giữ ý định của A hay B. Có trường hợp thay đổi các field độc lập có thể merge tự động, nhưng việc đó phải được định nghĩa rõ trong domain.

## 5. MongoDB: CAS với filter ID và version

Giả sử Product:

~~~javascript
db.products.insertOne({
  _id: "product-101",
  tenantId: "shop-17",
  name: "Bàn phím",
  version: NumberLong("7"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
});
~~~

Client đã đọc version 7 và muốn đổi tên:

~~~javascript
const result = db.products.updateOne(
  {
    _id: "product-101",
    tenantId: "shop-17",
    version: NumberLong("7")
  },
  {
    $set: {
      name: "Bàn phím cơ"
    },
    $inc: {
      version: NumberLong("1")
    },
    $currentDate: {
      updatedAt: true
    }
  }
);

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount
});
~~~

MongoDB cung cấp atomicity ở **một document** cho những update được hỗ trợ. Filter `version=7` được kiểm tra trong thao tác cập nhật; nếu một request khác đã tăng version, request cũ không còn match.

### Cách diễn giải kết quả

- `matchedCount=1`: một document đã khớp điều kiện.
- `matchedCount=0`: không document nào khớp ID + tenant + expected version.
- `modifiedCount` cho biết số document thực sự thay đổi theo semantics của lệnh; không được dùng thay máy móc cho `matchedCount` khi nhận diện precondition.

Nếu update chỉ `$set` một field bằng đúng giá trị đã có, có thể match nhưng không có sự thay đổi giá trị quan sát được. Trong mẫu trên có `$inc` version nên update khớp sẽ tăng version theo thiết kế.

### Không khớp chưa có nghĩa là không tồn tại

`matchedCount=0` có thể vì:

1. Document không tồn tại.
2. Đã bị xóa.
3. Version đã đổi.
4. Trạng thái nghiệp vụ không còn thỏa điều kiện khác.
5. `tenantId` không khớp hoặc caller không được phép.

Tầng API có thể đọc lại **trong phạm vi đã được ủy quyền** để quyết định trả 404, 409 hoặc 412. Nhưng lần đọc sau là một quan sát mới, không phải bằng chứng rằng nguyên nhân không thay đổi thêm.

## 6. Optimistic concurrency và version monotonic

Một flow phổ biến:

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant DB as NoSQL

    A->>DB: Read product
    DB-->>A: version=7
    B->>DB: Read product
    DB-->>B: version=7
    A->>DB: Update WHERE version=7
    DB-->>A: matched=1, new version=8
    B->>DB: Update WHERE version=7
    DB-->>B: matched=0, conflict
    B->>DB: Reload current state
    DB-->>B: version=8
~~~

Optimistic nghĩa là không giữ một lock dài từ lúc người dùng mở trang tới lúc bấm lưu. Thay vào đó, server kiểm tra tại lúc ghi.

Một version tốt cần:

- Được khởi tạo khi tạo entity.
- Tăng sau mọi thay đổi mà contract muốn bảo vệ.
- Không cho client tự chọn version mới.
- Thống nhất kiểu BSON và Java (`long`/`Long` khi đã chọn).
- Không reset vô tình trong import, migration hoặc upsert.
- Có chính sách về delete rồi tái tạo cùng ID.
- Không trộn `schemaVersion` với version trạng thái.

Nếu một code path cập nhật document mà quên tăng version, CAS có thể không phát hiện stale data.

## 7. Vì sao chỉ dùng `updatedAt` có rủi ro?

Một cách CAS khác là dùng timestamp từ lần đọc trước:

~~~javascript
{
  _id: "product-101",
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

Nhưng timestamp có thể:

- Trùng do độ phân giải.
- Bị ảnh hưởng bởi đồng hồ máy khác nhau.
- Không được thay bởi một writer.
- Bị giữ nguyên khi import dữ liệu.
- Phản ánh thời gian nghiệp vụ chứ không phải thứ tự cập nhật.
- Bị nhận từ client không đáng tin.

Một counter version tăng đơn điệu thường dễ kiểm chứng hơn. `updatedAt` vẫn hữu ích cho audit và hiển thị, nhưng không tự là concurrency token chắc chắn.

## 8. CAS theo trạng thái nghiệp vụ

Một Order có trạng thái `PENDING`. Chỉ được xác nhận khi vẫn ở trạng thái đó:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "shop-17",
    status: "PENDING"
  },
  {
    $set: {
      status: "CONFIRMED"
    },
    $currentDate: {
      confirmedAt: true
    }
  }
);
~~~

Điều kiện `status=PENDING` diễn đạt **chuyển trạng thái hợp lệ**. Nó khác version CAS: nếu trạng thái đã đổi rồi quay về PENDING, điều kiện trên giá trị vẫn có thể khớp.

Có thể kết hợp:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "shop-17",
    status: "PENDING",
    version: NumberLong("4")
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
);
~~~

Status bảo vệ điều kiện domain; version bảo vệ snapshot mà client dựa vào.

## 9. Vấn đề ABA

Giả sử:

~~~text
t0: status=PENDING, version=10
t1: status=PROCESSING, version=11
t2: status=PENDING, version=12
t3: Client cũ đang giữ trạng thái từ t0
~~~

Ở t3, check `status=PENDING` vẫn thành công. Nhưng trạng thái đã đi qua một chu kỳ khác. Đây là **ABA problem**: A → B → A khiến việc chỉ so sánh giá trị A không phát hiện lịch sử đã thay đổi.

Filter thêm `version=10` sẽ không khớp vì hiện là 12.

Nếu document bị delete rồi recreate cùng ID và version bị reset, cần generation/epoch hoặc chính sách không tái sử dụng ID, vì version thấp được tạo mới có thể làm stale operation có vẻ hợp lệ trong một số kịch bản.

## 10. Điều kiện tồn tại và insert-if-absent

Một tình huống thường gặp: hai request cùng muốn đăng ký username `NOVA` trong tenant `shop-17`.

Mẫu nguy hiểm:

~~~javascript
const found = db.users.findOne({
  tenantId: "shop-17",
  usernameKey: "NOVA"
});

if (!found) {
  db.users.insertOne({
    _id: "user-101",
    tenantId: "shop-17",
    usernameKey: "NOVA"
  });
}
~~~

Hai request có thể cùng nhận `found=null` trước khi cả hai insert.

### Hàng rào đúng: unique constraint theo scope

~~~javascript
db.users.createIndex(
  {
    tenantId: 1,
    usernameKey: 1
  },
  {
    unique: true,
    name: "uq_users_tenant_username"
  }
);
~~~

Unique index chặn hai document cùng thỏa khóa unique trong phạm vi được index bảo vệ. Một request thành công; request còn lại có thể gặp duplicate-key error và phải được ánh xạ thành business conflict.

**Pre-check chỉ hỗ trợ UX, không thay unique constraint**. Với MongoDB sharded collection, khả năng tạo/enforce unique index còn bị giới hạn bởi shard key và topology; phải kiểm tra cấu hình thật.

## 11. MongoDB: tạo claim bằng `_id` duy nhất

Để giữ một request ID:

~~~javascript
db.idempotencyRequests.insertOne({
  _id: "tenant-a#checkout-9001",
  state: "PROCESSING",
  payloadHash: "sha256-of-canonical-request",
  createdAt: ISODate("2026-11-14T09:00:00Z")
});
~~~

Một insert khác cùng `_id` sẽ gặp unique-key conflict theo ràng buộc document ID. Đây là primitive hữu ích cho **claim khi chưa tồn tại**.

Tuy nhiên nó chưa tự bảo đảm toàn bộ checkout chỉ được tính một lần. Cần biết:

- Nếu request lặp cùng key, payload có giống không?
- Claim được giữ bao lâu?
- Nếu worker chết sau khi claim nhưng trước khi tạo Order thì sao?
- Nếu Order đã tạo nhưng worker chết trước khi mark COMPLETED thì sao?
- Retry có được phép tiếp quản claim hết lease không?
- Claim record và Order được ghi nguyên tử hay theo workflow có bù trừ?

`_id` unique chỉ bảo vệ việc claim item; **idempotency của side effect** còn cần thiết kế riêng.

## 12. MongoDB: upsert và `$setOnInsert`

Upsert cho phép “update nếu có, insert nếu không tìm thấy”.

~~~javascript
db.settings.updateOne(
  {
    _id: "tenant-a#uiTheme"
  },
  {
    $setOnInsert: {
      tenantId: "tenant-a",
      theme: "LIGHT",
      createdAt: ISODate("2026-11-14T09:00:00Z")
    }
  },
  {
    upsert: true
  }
);
~~~

`$setOnInsert` chỉ áp dụng khi upsert tạo document mới, không ghi đè theme của document đã tồn tại.

Nếu filter không có unique constraint phù hợp, nhiều upsert đồng thời có thể tạo nhiều document. Phải thiết kế **khóa unique** đúng access pattern.

### Vì sao CAS không nên tự bật upsert?

Document `_id="product-101", version=8` đã tồn tại, nhưng client gọi:

~~~javascript
db.products.updateOne(
  {
    _id: "product-101",
    version: NumberLong("7")
  },
  {
    $set: { name: "Tên cũ" }
  },
  {
    upsert: true
  }
);
~~~

Filter không khớp do version 8. Upsert có thể thử insert một document mới cùng `_id` và nhận duplicate-key error. Điều này khác với một CAS update thông thường có `matchedCount=0`.

Khi mục tiêu là “sửa document nếu version đúng”, dùng update **không upsert**. Khi mục tiêu là “tạo nếu chưa có”, dùng insert-if-absent/unique key theo contract riêng.

## 13. Missing, null và existence predicate

Trong MongoDB:

~~~javascript
{ _id: "a" }

{ _id: "b", ownerId: null }

{ _id: "c", ownerId: "user-1" }
~~~

Những điều kiện sau khác nhau:

~~~javascript
// Field không tồn tại
db.resources.find({
  ownerId: { $exists: false }
});

// Field tồn tại, kể cả giá trị null
db.resources.find({
  ownerId: { $exists: true }
});

// Equality null có thể khớp cả field null và missing
db.resources.find({
  ownerId: null
});

// Chỉ BSON type null
db.resources.find({
  ownerId: { $type: "null" }
});
~~~

Nếu một business rule ghi “chỉ claim khi ownerId chưa tồn tại”, phải quyết định rõ **null có được coi là chưa có owner hay không**.

### Claim một field khi nó thiếu

~~~javascript
db.resources.updateOne(
  {
    _id: "resource-101",
    ownerId: { $exists: false }
  },
  {
    $set: { ownerId: "user-1" }
  }
);
~~~

Hai request cùng tranh một document sẽ không cùng thêm field khi điều kiện được kiểm tra trong atomic update.

Nhưng hai document khác nhau đều thiếu ownerId thì cả hai có thể được cập nhật. Muốn “một username/resource chỉ có một owner toàn hệ”, cần unique index hoặc **claim record** dùng khóa duy nhất cho resource đó.

## 14. Trạng thái nghiệp vụ nên có state machine

Ví dụ Order:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CONFIRMED
    PENDING --> CANCELLED
    CONFIRMED --> FULFILLED
    CONFIRMED --> CANCELLED
    FULFILLED --> [*]
    CANCELLED --> [*]
~~~

Các cạnh trong sơ đồ là chính sách ví dụ, không phải quy trình chung cho mọi hệ.

Một lệnh chuyển trạng thái nên mô tả:

- From-state cho phép.
- To-state cần ghi.
- Người gọi có quyền thực hiện không.
- Các điều kiện bổ sung: payment, expiration, owner, version.
- Việc ghi timestamp/audit.
- Hành vi retry request cũ hoặc request trùng.
- Có side effect hay không.

Nếu một điều kiện nằm ở document khác, single-document conditional update **không tự bảo vệ invariant liên document**.

## 15. Conditional decrement chống bán vượt tồn kho

Với tồn kho `available=5` và khách muốn mua 3:

~~~javascript
const r = db.inventory.updateOne(
  {
    _id: "shop-17#sku-KB-RED",
    available: { $gte: 3 }
  },
  {
    $inc: { available: -3 },
    $currentDate: { updatedAt: true }
  }
);

printjson({ matchedCount: r.matchedCount });
~~~

Ở một document MongoDB, điều kiện `available>=3` và `$inc:-3` được thực hiện cùng update nguyên tử theo bảo đảm engine.

Nếu hai request đều mua 3:

~~~text
Ban đầu: available=5
Request A: so khớp >=3 -> thành công; available=2
Request B: so khớp >=3 -> thất bại; available=2
~~~

Không cần một lần `findOne` trước làm chốt an toàn; kiểm tra đúng phải ở **chính lệnh ghi**.

### Chỉ `$inc` mà không có condition thì sao?

~~~javascript
db.inventory.updateOne(
  { _id: "shop-17#sku-KB-RED" },
  { $inc: { available: -3 } }
);
~~~

Phép trừ atomic nhưng có thể đưa available xuống âm nếu không có predicate bảo vệ. **Atomicity không thay thế bất biến nghiệp vụ.**

### Có cần version thêm không?

Version giúp phát hiện những thay đổi phức tạp, audit hoặc reset stock. Nhưng riêng bất biến “không trừ quá available” được diễn đạt trực tiếp bằng filter trên available; dùng CAS version không thay thế điều kiện số lượng.

## 16. Counter cộng dồn và retry

Một counter lượt xem:

~~~javascript
db.metrics.updateOne(
  { _id: "page-101" },
  { $inc: { views: 1 } }
);
~~~

Các `$inc` trên cùng document được thực hiện theo atomic update semantics của MongoDB; không gây lost update kiểu app tự đọc–cộng–ghi.

Tuy nhiên client timeout sau khi DB đã cộng, rồi retry có thể cộng lần hai. Nếu mỗi event phải được tính **đúng một lần theo business key**, cần idempotency/event ledger/transaction phù hợp.

Phân biệt:

- **Atomic increment:** không mất phép cộng khi nhiều update đồng thời.
- **Exactly once per business event:** mỗi ý định không tạo nhiều effect khi retry.
- **Durability:** phép cộng được xác nhận tồn tại qua fault model nào.
- **Consistency of readers:** client đọc số đếm mới tới đâu.

Không đồng nhất bốn thuộc tính này.

## 17. Ví dụ số dư: invariant cục bộ và giới hạn

Một ví có số dư bằng minor unit:

~~~javascript
db.wallets.updateOne(
  {
    _id: "wallet-101",
    tenantId: "shop-17",
    balanceMinor: { $gte: NumberLong("50000") }
  },
  {
    $inc: {
      balanceMinor: NumberLong("-50000")
    }
  }
);
~~~

Điều kiện bảo vệ việc không trừ quá số dư của **một document**. Nhưng để xây nghiệp vụ tài chính thật, còn cần:

- Idempotency theo lệnh debit.
- Ledger/audit, các khoản ghi nợ/ghi có.
- Quy tắc loại tiền và làm tròn.
- Phân quyền và hạn mức.
- Transaction nếu phải ghi ledger cùng balance.
- Đối soát external payment.
- Xử lý timeout và trạng thái outcome chưa biết.

Đừng xem một conditional decrement như toàn bộ thiết kế hệ thống thanh toán.

## 18. Idempotency khác CAS

CAS trả lời: **“Tại lúc ghi, state có còn đúng như tôi kỳ vọng?”**

Idempotency trả lời: **“Một ý định đã được xử lý chưa, để gửi lại không làm thêm effect?”**

Ví dụ request:

~~~text
Idempotency-Key: tenant-a#checkout-9001
Payload: product=KB-RED, quantity=1
~~~

Một record:

~~~javascript
{
  _id: "tenant-a#checkout-9001",
  requestHash: "hash-of-canonical-payload",
  status: "COMPLETED",
  orderId: "order-101"
}
~~~

Khi client retry:

1. Cùng key và cùng payload → có thể trả lại kết quả đã lưu.
2. Cùng key nhưng payload khác → báo conflict.
3. Key chưa tồn tại → một worker có quyền claim.
4. Key đang PROCESSING → chờ hoặc trả trạng thái in-progress theo contract.
5. Claim hết lease → cần cơ chế tiếp quản an toàn và kiểm tra side effect đã commit.

Unique claim không tự đảm bảo rằng Order, stock và idempotency record đã commit nguyên tử nếu chúng nằm ở các document/hệ thống riêng.

## 19. Timeout: không rõ ghi đã thành công chưa

Một request có thể:

~~~text
Client -> DB: conditional write
DB: đã commit
Network: response bị mất
Client: timeout, không biết outcome
~~~

Nếu retry CAS bằng expected version cũ, lần hai có thể bị conflict. Nhưng conflict **không chứng minh lần đầu chính request này thành công**; một request khác cũng có thể đã đổi version.

Nếu retry atomic increment vô điều kiện, có thể cộng hoặc trừ lần hai.

Cần thiết kế:

- Operation/request ID ổn định.
- Kết quả hoặc event/ledger có thể tra cứu.
- State transitions idempotent theo command.
- Retry có giới hạn, backoff và jitter.
- Reconciliation khi outcome chưa rõ.
- Không trả lời chắc chắn “chưa ghi” chỉ vì request timeout.

**CAS bảo vệ cạnh tranh trạng thái; idempotency bảo vệ retry cùng ý định.**

## 20. Delete có điều kiện

Nếu chỉ cho xóa draft đã được người dùng kiểm tra ở version 8:

~~~javascript
db.drafts.deleteOne({
  _id: "draft-101",
  tenantId: "shop-17",
  version: NumberLong("8")
});
~~~

Nếu `deletedCount=0`, có thể đã bị xóa, version thay đổi hoặc không đúng tenant. Không nhất thiết phải trả một loại lỗi duy nhất cho mọi nguyên nhân.

Một delete có điều kiện vẫn có rủi ro **recreate cùng ID** nếu hệ thống cho phép tái sử dụng. Với event consumer và tombstone, cần version/generation để tránh một update cũ làm tài nguyên vừa xóa xuất hiện lại.

## 21. TTL, claim lease và quyền sở hữu

Ví dụ một job được worker claim:

~~~javascript
{
  _id: "job-101",
  state: "RUNNING",
  ownerId: "worker-A",
  ownerEpoch: NumberLong("3"),
  leaseUntil: ISODate("2026-11-14T09:30:00Z")
}
~~~

Nếu một worker khác cần tiếp quản khi lease hết hạn, điều kiện phải xét owner/generation, trạng thái hiện hành và thời điểm theo chính sách nguồn. Không chỉ đọc lease rồi ghi vô điều kiện.

Cần phân biệt:

- **Lease:** thời hạn một worker có quyền xử lý.
- **Idempotency window:** thời hạn nhận diện retry cùng request.
- **TTL cleanup:** dọn vật lý các record hết hạn.
- **Tombstone retention:** giữ marker để ngăn event cũ.
- **Backup retention:** khả năng phục hồi trong lịch sử.

TTL của MongoDB được xử lý ở nền; không đảm bảo document biến mất chính xác tại thời điểm hết hạn. Đường quyết định nghiệp vụ vẫn cần đánh giá deadline.

## 22. Trả lỗi từ conditional write

| Kết quả | Nguyên nhân có thể | Xử lý |
|---|---|---|
| `matchedCount=1` | Điều kiện ghi khớp | Trả kết quả đã áp dụng |
| `matchedCount=0` | Sai version, status, tenant hoặc không tồn tại | Đọc lại trong scope và phân loại |
| Duplicate key | Business key hoặc ID đã được claim | 409 hoặc kết quả idempotent theo contract |
| Condition failed | Predicate không còn đúng | Conflict hoặc nghiệp vụ như SOLD_OUT |
| Timeout | Không biết commit chưa | Tra operation ID/reconcile trước retry |
| Throttling | Tải cao/tạm thiếu capacity | Bounded retry với backoff |
| Validation error | Dữ liệu hoặc điều kiện sai kiểu | 400/422 theo API contract |
| Unauthorized | Người gọi không có quyền | 403 hoặc chính sách che tồn tại |

**HTTP 409 Conflict** thường phù hợp business/version conflict; **412 Precondition Failed** có thể phù hợp khi API dùng `If-Match` theo chuẩn HTTP. Lựa chọn phải được tài liệu hóa.

Không dùng `modifiedCount=0` để tự suy ra mọi trường hợp “version conflict”; một update hợp lệ có thể match nhưng không làm đổi giá trị khi không có version increment.

## 23. ETag và `If-Match`: CAS ở HTTP API

Một server trả:

~~~http
GET /products/product-101
ETag: "v7"
~~~

Client gửi cập nhật:

~~~http
PATCH /products/product-101
If-Match: "v7"
Content-Type: application/json

{"name":"Bàn phím cơ"}
~~~

Server phải chuyển ETag thành precondition gắn với trạng thái và thực hiện CAS **ở lệnh ghi vào database**, không chỉ check version bằng một read rồi ghi sau.

Nếu không khớp, có thể trả 412 theo HTTP contract. Một ETag có thể là hash hoặc token opaque thay vì dạng version đơn giản, miễn semantics và cách đối chiếu được định nghĩa.

Lưu ý nếu nhiều API representation cùng một resource có version khác nhau: cần xác định ETag gắn với representation nào để không chấp nhận những update stale.

## 24. Java/Spring Data MongoDB: conditional update

Một service Java có thể dùng `MongoTemplate`:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class ProductUpdater {
    private final MongoTemplate mongoTemplate;

    public ProductUpdater(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean rename(
            String authenticatedTenantId,
            String productId,
            long expectedVersion,
            String newName) {

        Query query = new Query(
            Criteria.where("_id").is(productId)
                .and("tenantId").is(authenticatedTenantId)
                .and("version").is(expectedVersion)
        );

        Update update = new Update()
            .set("name", newName)
            .inc("version", 1)
            .currentDate("updatedAt");

        UpdateResult result = mongoTemplate.updateFirst(
            query,
            update,
            ProductDocument.class
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

Ví dụ chưa khai báo `ProductDocument`, validation, controller và mapping lỗi hoàn chỉnh. Dự án thật phải thống nhất kiểu BSON version với kiểu Java, và bảo đảm mọi code path tăng version.

### `@Version` là công cụ, không phải phép màu

Spring Data MongoDB có optimistic locking dựa trên `@Version` ở những operation được hỗ trợ. Nó có thể giúp tự động kiểm tra version khi lưu entity.

Nhưng cần hiểu:

- Operation nào thật sự dùng optimistic locking.
- Bulk update/direct update/custom pipeline có tự dùng version không.
- Migration/job import có tăng version không.
- Các thao tác thành công/thất bại được xác nhận theo write concern nào.
- Mọi service writer có cùng chính sách không.

Không chỉ thêm annotation rồi mặc định mọi write đã được bảo vệ.

## 25. DynamoDB: insert-if-absent bằng `ConditionExpression`

DynamoDB có conditional write trong PutItem/UpdateItem/DeleteItem. Với table primary key đơn là `PK`:

~~~text
PutItem:
  Item:
    PK = "TENANT#shop-17#REQUEST#8001"
    state = "PROCESSING"

  ConditionExpression:
    attribute_not_exists(PK)
~~~

Nếu item với key này đã tồn tại, thao tác không được áp dụng và thường trả lỗi `ConditionalCheckFailedException`.

Với table có cả PK và SK, sự tồn tại một item xác định bằng **toàn bộ primary key**. Không nhầm “partition có item khác” với “item cùng PK+SK đã tồn tại”.

### Conditional update với version

Item:

~~~json
{
  "PK": "TENANT#shop-17",
  "SK": "PRODUCT#product-101",
  "name": "Bàn phím",
  "version": 7
}
~~~

Biểu thức UpdateItem minh họa:

~~~text
Key:
  PK = "TENANT#shop-17"
  SK = "PRODUCT#product-101"

UpdateExpression:
  SET #name = :newName, #ver = #ver + :one

ConditionExpression:
  #ver = :expectedVersion

ExpressionAttributeNames:
  #name = "name"
  #ver = "version"

Values:
  :newName = "Bàn phím cơ"
  :one = 1
  :expectedVersion = 7
~~~

Điều kiện được đánh giá trong thao tác write theo semantics của DynamoDB. Nếu version không khớp, update không được áp dụng.

### Không tạo item vô ý khi muốn update

Với UpdateItem, nếu key chưa tồn tại, một số biểu thức có thể dẫn đến tạo item theo semantics API khi không có condition tồn tại. Nếu nghiệp vụ yêu cầu **chỉ cập nhật bản có sẵn**, thêm precondition như `attribute_exists(PK)` (và những yêu cầu key/field thích hợp) thay vì chỉ dựa vào ý nghĩa chữ “Update”.

## 26. DynamoDB: giảm stock khi đủ số lượng

Lệnh khái niệm:

~~~text
Key:
  PK = "TENANT#shop-17"
  SK = "STOCK#KB-RED"

UpdateExpression:
  SET available = available - :qty

ConditionExpression:
  attribute_exists(PK) AND available >= :qty

Values:
  :qty = 3
~~~

Predicate `available >= :qty` phải nằm trong lệnh update; không dùng một GetItem trước đó làm hàng rào cạnh tranh chính.

Một GetItem eventual-consistent có thể đọc trạng thái cũ trong một số chế độ, nhưng điều kiện của write có bảo đảm riêng ở nguồn. Cần phân biệt read consistency và conditional write semantics.

### Global Tables

Khi dùng Global Tables hoặc multi-region write, không tự suy ra một CAS thành công ở region A tạo ra một invariant serializable toàn cầu đối với mọi update đồng thời ở region B. Phải xem replication, conflict-resolution và transaction constraints của chế độ/phiên bản đang dùng.

## 27. DynamoDB transaction khi invariant trải nhiều item

Nếu một checkout cần:

1. Claim idempotency key.
2. Trừ stock khi còn đủ.
3. Tạo Order khi ID chưa tồn tại.

Một conditional update trên stock **không khiến hai item khác tự commit cùng lúc**.

DynamoDB có `TransactWriteItems` theo giới hạn dịch vụ để nhóm các thay đổi vào một transaction. Một thiết kế có thể yêu cầu:

~~~text
Update stock IF available >= qty
Put order IF attribute_not_exists(PK)
Put requestClaim IF attribute_not_exists(PK)
~~~

Cần kiểm tra giới hạn transaction, schema, khu vực, retry/throttling, khóa và consistency thực tế. External payment API **không** thuộc transaction DynamoDB theo cách thông thường; vẫn cần outbox/saga và idempotency.

## 28. Cassandra: Lightweight Transactions (LWT)

Cassandra có cơ chế conditional write thông qua **Lightweight Transactions**, dùng câu lệnh `IF` với protocol đồng thuận theo thiết kế Cassandra.

### Insert nếu row chưa tồn tại

~~~sql
CREATE TABLE user_names (
    tenant_id text,
    username_key text,
    user_id text,
    PRIMARY KEY ((tenant_id), username_key)
);
~~~

~~~sql
INSERT INTO user_names (
    tenant_id, username_key, user_id
)
VALUES (
    'shop-17', 'NOVA', 'user-101'
)
IF NOT EXISTS;
~~~

Kết quả LWT cho biết condition được áp dụng hay không qua trường như `[applied]`, cùng metadata/giá trị theo API driver.

### CAS theo version

~~~sql
CREATE TABLE product_state (
    tenant_id text,
    product_id text,
    name text,
    version bigint,
    PRIMARY KEY (tenant_id, product_id)
);
~~~

~~~sql
UPDATE product_state
SET name = 'Bàn phím cơ',
    version = 8
WHERE tenant_id = 'shop-17'
  AND product_id = 'product-101'
IF version = 7;
~~~

Nếu version không còn 7, write không được áp dụng. Cần kiểm tra các semantics cụ thể của CQL và mức consistency/serial consistency tương ứng trong hệ thực tế.

### Đánh đổi

LWT phải phối hợp nhiều hơn lệnh ghi thông thường, dẫn tới latency/throughput/contension khác. Không nên dùng LWT cho mọi update chỉ vì nó tồn tại, đặc biệt trên hot partition.

Thêm nữa, `IF NOT EXISTS` bảo vệ sự tồn tại **theo primary key đã thiết kế**, không tự cho uniqueness của một non-key field toàn cluster. Username unique theo tenant cần khóa claim có scope đúng.

## 29. Redis: `WATCH`, `MULTI` và `EXEC`

Redis hỗ trợ optimistic concurrency bằng `WATCH`: theo dõi key trước khi bắt đầu transaction; nếu key đổi trước `EXEC` theo semantics Redis, transaction có thể bị abort.

Ví dụ pseudocode:

~~~text
WATCH inventory:KB-RED
available = GET inventory:KB-RED

if available < 3:
    UNWATCH
    return SOLD_OUT

MULTI
DECRBY inventory:KB-RED 3
EXEC

if EXEC aborted:
    retry with bounded backoff
else:
    return RESERVED
~~~

Điều cần hiểu:

- `WATCH` và transaction gắn với connection.
- Phải xử lý trường hợp EXEC không commit.
- Redis persistence/failover có bảo đảm riêng với những ghi vừa được chấp nhận.
- Không dùng Redis CAS để hứa transaction với MongoDB hoặc external payment.
- Retry sau timeout vẫn có nguy cơ trừ hai lần nếu thiếu idempotency.

## 30. Redis: Lua script cho điều kiện và phép trừ

Nếu chỉ cần đọc stock, so sánh và trừ trong cùng Redis instance, một Lua script có thể diễn đạt trực tiếp:

~~~lua
local current = tonumber(redis.call("GET", KEYS[1]) or "0")
local qty = tonumber(ARGV[1])

if qty == nil or qty <= 0 then
  return redis.error_reply("INVALID_QUANTITY")
end

if current < qty then
  return 0
end

redis.call("DECRBY", KEYS[1], qty)
return 1
~~~

Theo mô hình thực thi script của Redis, những lệnh trong script không bị client khác xen vào trong cùng execution context, hỗ trợ atomic check+decrement.

Nhưng cần:

- Giới hạn thời gian chạy script.
- Tuân thủ quy định hash slot/keys trong Redis Cluster.
- Hiểu failover, replication và persistence.
- Thực hiện idempotency riêng cho retry.
- Bảo vệ invariant ở database **nguồn thật** nếu Redis chỉ là cache.

Một lệnh Lua trong Redis không biến write ở nguồn NoSQL khác thành nguyên tử.

## 31. Redis `SET NX`, lease và fencing

Một lock claim phổ biến:

~~~text
SET lock:resource-101 owner-token-7 NX PX 30000
~~~

- `NX`: chỉ tạo key nếu chưa có.
- `PX 30000`: đặt TTL 30 giây.
- Token giúp nhận diện người giữ lock.

Tuy nhiên lease có thể hết hạn trong lúc worker đang pause:

~~~text
t0 A nhận lock, TTL 30s
t1 A pause vì GC/network
t2 lock hết hạn
t3 B nhận lock mới và bắt đầu ghi
t4 A tỉnh dậy, tiếp tục ghi theo lock cũ
~~~

A và B có thể cùng thực hiện side effect nếu nơi ghi không kiểm tra quyền sở hữu hiện hành.

Một giải pháp cho các trường hợp cần bảo vệ tài nguyên ngoài là **fencing token/epoch tăng đơn điệu** được kiểm tra ở nơi thực hiện ghi. Một conditional write trực tiếp ở source of truth có thể đơn giản và an toàn hơn việc dùng lock ngoài.

### Compare-and-delete khi unlock

Worker A không được xóa lock B sau khi A hết lease. Có thể dùng Lua:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
~~~

Script chỉ xóa khi token đúng. Nhưng **compare-and-delete không ngăn worker cũ đã hết lease thực hiện side effect**. Fencing hoặc conditional check tại đích vẫn quan trọng khi cần tính đúng đắn mạnh.

## 32. Hot document và contention

Optimistic CAS phù hợp khi conflict không quá nhiều. Nếu 10.000 request mỗi giây cùng sửa một document:

- Nhiều client có cùng expected version.
- Một số update thành công, nhiều update conflict.
- Retry có thể làm tăng tải.
- P95/P99 latency tăng.
- Hot key/partition thành điểm nghẽn.

Các hướng cân nhắc:

1. Dùng `$inc`/atomic operator khi phép toán độc lập.
2. Dùng một owner/queue serialize command theo key.
3. Giảm những field thường xuyên sửa vào aggregate lớn.
4. Phân vùng counter nếu invariant cho phép, có cơ chế tổng hợp.
5. Giới hạn retry, dùng backoff và jitter.
6. Thiết kế API cho phép người dùng giải quyết conflict thay vì retry mù.
7. Đo contention theo key, không chỉ theo trung bình toàn cluster.

Sharded counters không tự bảo vệ một **ngưỡng tổng toàn hệ** nếu không có coordination; đừng đánh đổi invariant để tăng throughput.

## 33. Retry đúng theo ý nghĩa nghiệp vụ

Mã giả:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    current = read(entityId)
    plannedChange = calculate(current, command)

    outcome = conditionalWrite(
        id=entityId,
        expectedVersion=current.version,
        change=plannedChange
    )

    if outcome == SUCCESS:
        return SUCCESS

    if outcome == CONFLICT:
        if command cannot be safely recomputed:
            return USER_CONFLICT
        backoffWithJitter()
        continue

    if outcome == UNKNOWN:
        return reconcileByOperationId()

return TOO_MUCH_CONTENTION
~~~

Không phải conflict nào cũng nên retry tự động:

- **Đổi tên Product:** client khác đã sửa; nên để người dùng quyết định merge.
- **Trừ stock:** thiếu hàng thì retry liên tục không tạo ra hàng mới.
- **Confirm Order:** Order đã CANCELLED thì không ép transition.
- **Atomic counter:** có thể retry nhưng phải bảo vệ idempotency khi timeout.
- **Lấy lease:** retry có giới hạn và phải xét token/generation.

**Retry cho tới khi thành công không đồng nghĩa làm đúng yêu cầu ban đầu.**

## 34. CAS ở source nhưng event/projection vẫn có thể stale

Document Order nguồn chuyển:

~~~text
v10 PENDING
v11 CONFIRMED
v12 FULFILLED
~~~

Nếu search projection nhận event theo thứ tự:

~~~text
v12 rồi v11
~~~

và upsert vô điều kiện, projection có thể quay về `CONFIRMED`.

Consumer nên dùng **versioned conditional apply**:

~~~text
apply incoming event only if
incoming.sourceVersion > indexed.sourceVersion
~~~

Điều kiện so sánh và ghi phải atomic tại nơi projection được quản lý; chỉ đọc version trước rồi ghi sau vẫn có race.

Khi delete xảy ra, có thể cần **versioned tombstone** để event update cũ không tái tạo document đã xóa.

CAS trong nguồn bảo vệ nguồn, **không tự bảo vệ các bản sao bất đồng bộ**.

## 35. CAS trên một document không bảo vệ invariant nhiều document

Giả sử quy tắc: **ít nhất một bác sĩ đang trực**.

~~~javascript
{ _id: "doctor-A", onCall: true }
{ _id: "doctor-B", onCall: true }
~~~

Hai transaction nghiệp vụ độc lập:

~~~text
T1 đọc thấy B đang trực -> cho A nghỉ
T2 đọc thấy A đang trực -> cho B nghỉ

T1 CAS doctor-A onCall=false
T2 CAS doctor-B onCall=false
~~~

CAS trên hai document khác nhau đều có thể thành công, nhưng cuối cùng không ai trực. Đây là một ví dụ **write skew/invariant liên document**.

Các cách giải quyết có thể là:

- Đưa thông tin đủ để kiểm tra invariant vào **một atomic aggregate**.
- Dùng transaction với isolation/validation phù hợp, tạo điểm xung đột thực sự.
- Dùng coordination record/claim có conditional update.
- Thiết kế một owner quyết định thay đổi lịch trực.

Không mặc định bất kỳ transaction nào cũng ngăn mọi write skew; isolation và khả năng phát hiện xung đột của từng hệ khác nhau.

## 36. Transaction bổ sung, không thay thế CAS

Một checkout có thể cần:

1. Claim request ID.
2. Giảm stock có điều kiện.
3. Tạo Order nếu chưa tồn tại.
4. Ghi outbox event.

Nếu các thay đổi nằm trong transaction scope được database hỗ trợ, có thể nhóm chúng để commit/abort cùng nhau. Tuy nhiên vẫn cần:

- Conditional predicates đúng business rules.
- Unique keys đúng scope.
- Idempotency khi transaction result không rõ.
- Retry xử lý transaction conflict.
- Audit và monitoring.
- Thiết kế workflow/saga cho side effect ở hệ khác.

Đặc biệt một external payment API không nằm trong transaction database thông thường. Dùng outbox, idempotent command, saga hoặc reconciliation theo yêu cầu, không giả định transaction DB bao phủ thế giới ngoài.

## 37. Phân quyền và tenant isolation

Một CAS update an toàn về concurrency vẫn có thể **không an toàn về security** nếu client được phép chọn ID của tenant khác.

Ví dụ MongoDB:

~~~javascript
db.products.updateOne(
  {
    _id: "product-101",
    tenantId: authenticatedTenantId,
    version: expectedVersion
  },
  {
    $set: { name: newName },
    $inc: { version: NumberLong("1") }
  }
);
~~~

`authenticatedTenantId` phải đến từ ngữ cảnh xác thực/ủy quyền, không đơn thuần do client tự gửi.

Ngoài filter tenant, API còn phải kiểm tra quyền của role/người gọi đối với thao tác. ID khó đoán không thay thế authorization.

Nếu thất bại do sai tenant, response cũng phải tuân thủ policy chống lộ sự tồn tại của resource.

## 38. Conditional update và dữ liệu cache cũ

Giả sử tồn kho nguồn lưu MongoDB, Redis chỉ là cache:

~~~text
Redis.available -> 5 (stale)
MongoDB.available -> 2
~~~

Nếu app dựa vào Redis để quyết định đặt 3 rồi trừ MongoDB vô điều kiện, tồn kho có thể âm.

Mô hình đúng hơn:

~~~text
Client
   |
   v
Inventory source:
   UPDATE stock IF available >= 3
   |
   +-- SUCCESS -> commit / event
   |
   +-- FAILURE -> SOLD_OUT
                     |
                     v
             Cache/search update later
~~~

Cache có thể giúp hiển thị nhanh, nhưng **invariant phải được quyết định ở nơi dữ liệu có thẩm quyền**, hoặc một owner khác được hợp đồng xác định rõ.

## 39. Những kiểm thử đồng thời cần có

| Tình huống | Kỳ vọng |
|---|---|
| Hai client cùng expected version | Tối đa một CAS với version đó thành công |
| Hai insert cùng unique business key | Không có hai document hợp lệ trùng khóa |
| Hai request mua 3 khi tồn 5 | Tối đa một reservation thành công |
| Hai lần PENDING → CONFIRMED | Không có hai transition hiệu lực |
| Owner field missing vs null | Điều kiện tồn tại có semantics đúng |
| State A→B→A | Version CAS từ chối snapshot A cũ |
| Timeout sau commit + retry | Không nhân đôi side effect |
| Event v12 trước v11 | Projection không lùi version |
| Delete v14, update v13 đến muộn | Không resurrect document |
| Two-document invariant | Transaction/coordination thực sự bảo vệ |
| High contention | Retry không chạy vô hạn |
| Cross-tenant ID | Không sửa tài nguyên tenant khác |

### Ví dụ test ý tưởng cho tồn kho

Ban đầu:

~~~javascript
db.inventory.insertOne({
  _id: "stock-A",
  available: 5
});
~~~

Nhiều worker cùng chạy:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-A",
    available: { $gte: 3 }
  },
  {
    $inc: { available: -3 }
  }
);
~~~

Kỳ vọng: một worker có thể thành công, các worker sau không khớp; stock cuối cùng 2. Test cần ghi nhận **response thực của từng update**, không chỉ xem giá trị cuối, vì app có thể báo success sai.

Không chạy concurrency test gây ghi thật trên collection production.

## 40. Quan sát contention và conditional failures

Metric gợi ý:

- Tỷ lệ CAS conflict theo resource/endpoint.
- Duplicate-key errors do cạnh tranh tạo.
- ConditionalCheckFailed counts.
- Số transition bị từ chối vì source state sai.
- Retry count, backoff duration.
- Unknown-outcome/timeouts.
- Latency P95/P99 của conditional writes.
- Hot keys/partitions.
- Negative stock violations (kỳ vọng bằng 0).
- Business key duplicates (kỳ vọng bằng 0).
- Version drift giữa source và read model.
- Số lần user phải tải lại form.

Conflict không phải lúc nào cũng là lỗi hệ thống. Một CAS conflict là **kết quả đúng** khi cần ngăn stale update. Cần tối ưu khi contention quá cao hoặc UX không phù hợp, không cố loại bỏ hết conflict bằng ghi đè vô điều kiện.

## 41. Những sai lầm thường gặp

**“Mỗi read/write atomic nên đọc rồi kiểm tra rồi ghi cũng atomic.”** Chuỗi nhiều lệnh vẫn có race.

**“Thêm field version là đủ.”** Phải đưa expected version vào điều kiện của lệnh ghi, và mọi writer cập nhật state đều tăng version.

**“Không match nghĩa là không tồn tại.”** Có thể version sai, status đã đổi hoặc tenant không hợp lệ.

**“`modifiedCount=0` luôn là conflict.”** Có thể match nhưng giá trị không đổi.

**“`upsert:true` tốt cho CAS.”** Có thể cố insert khi expected version không khớp, dẫn tới duplicate key.

**“Pre-check findOne chặn được tạo trùng.”** Hai request có thể cùng đọc “chưa có”.

**“MongoDB `field:null` chỉ khớp field thật sự null.”** Equality null có thể khớp cả missing.

**“Atomic increment tự làm retry an toàn.”** Timeout sau commit có thể khiến retry nhân đôi.

**“A hiện vẫn là A nghĩa là chưa có biến đổi.”** Có thể xảy ra ABA; version/generation giúp phát hiện.

**“Conditional update trên một document bảo vệ mọi document.”** Invariant liên document cần transaction/coordination hoặc thiết kế aggregate.

**“Cassandra LWT giống ghi thông thường về chi phí.”** LWT có thêm coordination và contention.

**“Conditional write ở một DynamoDB region bảo vệ đồng thời mọi global region.”** Phải xem multi-region semantics.

**“Redis lock TTL bảo đảm worker cũ không còn ghi.”** Worker cũ có thể tiếp tục sau lease, cần fencing/check tại đích.

**“CAS thành công khiến cache/search có dữ liệu mới tức thì.”** Projection có thể trễ và nhận event sai thứ tự.

**“Retry CAS mãi đến khi pass.”** Có thể ghi đè ý định của người khác hoặc làm hệ quá tải.

## 42. Bài tập thực hành

### Bài A — Lost update

Product version 3; hai request đọc version 3 rồi cùng update có điều kiện.

**Câu hỏi:** có bao nhiêu update với expectedVersion=3 có thể tăng version lên 4?

**Hướng giải:** tối đa một theo atomic scope phù hợp; lần còn lại conflict.

### Bài B — Tồn kho

Còn 5, hai request cùng đặt 3. Hãy viết update tránh overselling:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-A",
    available: { $gte: 3 }
  },
  {
    $inc: { available: -3 }
  }
);
~~~

Vì sao `findOne` trước rồi `$set available=2` là không đủ?

### Bài C — Tạo username

Hai request cùng đăng ký `NOVA` trong cùng tenant. Hàng rào nào cần?

**Hướng giải:** unique index `(tenantId, usernameKey)` hoặc conditional claim có khóa đúng scope; pre-check chỉ hỗ trợ UI.

### Bài D — Null và missing

Document có `ownerId:null`. Filter `ownerId:{$exists:false}` có match không?

**Hướng giải:** không, vì field tồn tại dù giá trị là null.

### Bài E — ABA

`PENDING(v4) → PROCESSING(v5) → PENDING(v6)`. Client cũ giữ v4. Điều kiện status=PENDING có phát hiện lịch sử không?

**Hướng giải:** không; version CAS expected 4 sẽ không khớp version 6.

### Bài F — Upsert không đúng ngữ cảnh

Document `_id=x`, version=8; client filter `_id=x, version=7` và `upsert:true`.

**Hướng giải:** có thể thử insert document mới cùng ID và gặp duplicate-key error. Không bật upsert cho update CAS chỉ nhằm sửa bản tồn tại.

### Bài G — Retry sau timeout

DB trừ 1 stock thành công nhưng response mất. Client gửi lại lệnh giảm 1 vô điều kiện. Có an toàn không?

**Hướng giải:** không nếu một checkout chỉ được trừ một lần. Cần idempotency/operation record và đối soát.

### Bài H — Write skew

Hai bác sĩ đều trực, hai request cập nhật hai document khác nhau để cả hai nghỉ. CAS mỗi document có đủ?

**Hướng giải:** không; invariant “ít nhất một người trực” trải hai document, cần transaction/serialization point phù hợp.

### Bài I — Redis lease

A giữ lock 30 giây, pause 40 giây, B nhận lock sau khi TTL hết. A tỉnh lại. Vì sao cần fencing?

**Hướng giải:** A vẫn có thể ghi dù đã mất lock; nguồn đích phải từ chối token/epoch cũ.

### Bài J — DynamoDB condition

GetItem trả version cũ; client sau đó update. Vì sao cần ConditionExpression trên UpdateItem?

**Hướng giải:** read có thể stale và race. Condition phải được đánh giá trong atomic write.

### Bài K — Cassandra LWT

Hai request cùng `INSERT ... IF NOT EXISTS` một username claim. Điểm khác với find-before-insert?

**Hướng giải:** điều kiện và insert được điều phối bằng LWT theo key, không có cửa sổ read-check-write ở client như cách thủ công.

### Bài L — Projection sai thứ tự

Search index nhận event v12 trước v11. CAS ở source có tự ngăn projection lùi v11 không?

**Hướng giải:** không; indexer cần conditional apply theo sourceVersion ở hệ đích.

## 43. Checklist thiết kế CAS/conditional write

Trước khi đưa một API vào sản phẩm, hãy tự trả lời:

1. **Invariant là gì?** Không âm, unique key, chuyển trạng thái, chỉ một owner?
2. **Nguồn sự thật ở đâu?** Document/item/partition nào quyết định?
3. **Atomic scope của engine là gì?** Một document, một item, một partition hay transaction?
4. **Điều kiện nào kiểm tra được tại write-time?** Status, version, available, existence?
5. **Khi không khớp thì xử lý thế nào?** Conflict, SOLD_OUT, NotFound hay retry?
6. **Nếu timeout sau commit?** Idempotency/operation ID và cách reconcile?
7. **Nếu state đổi A→B→A?** Version/generation?
8. **Nếu document bị xóa rồi tạo lại?** Khóa/generation/tombstone?
9. **Nếu nhiều document?** Transaction, ownership hoặc coordination?
10. **Nếu nhiều region/shard?** Constraint có đúng phạm vi cần không?
11. **Nếu cache/search stale?** Có kiểm tra ở source không?
12. **Nếu client biết ID tenant khác?** Authorization và scope?
13. **Nếu contention cao?** Bounded retry, backoff, queue?
14. **Nếu event sai thứ tự?** Conditional apply theo sourceVersion?
15. **Có test interleaving và metrics?** Đo conflict và invariant violations?

Một hợp đồng cập nhật có thể ghi:

~~~yaml
operation: ReserveInventory
owner: InventoryService
source:
  collection: inventory
  key: "tenantId + skuKey"
precondition:
  field: available
  operator: greaterOrEqual
  value: requestedQuantity
mutation:
  available: "decrement by requestedQuantity"
atomicScope: singleInventoryDocument
outcomes:
  success: reserved
  conditionFailed: insufficientStock
idempotency:
  key: "tenantId + checkoutRequestId"
  outcomeStorage: required
security:
  tenantScope: authenticatedContext
  authorization: required
concurrency:
  strategy: atomicConditionalUpdate
  retry: boundedWithBackoff
multiDocument:
  orderCreation: "transaction or workflow"
  audit: "outbox or reconciled ledger"
monitoring:
  - conditionalConflicts
  - unknownWriteOutcomes
  - negativeStockViolations
~~~

Đây là **mẫu hợp đồng**, không phải YAML tự được MongoDB/DynamoDB/Cassandra thực thi. Các bảo đảm phải được hiện thực bằng lệnh và cấu hình thật.

## 44. Kết luận

**Compare-and-set** so sánh version/giá trị kỳ vọng với state hiện tại trước khi ghi. **Điều kiện tồn tại** giúp claim một key chỉ khi chưa được cấp. **Cập nhật có điều kiện** bảo vệ bất biến cục bộ như tồn kho không âm, owner chỉ được gán một lần hoặc Order chỉ chuyển từ `PENDING` sang `CONFIRMED`.

Điểm chung là **điều kiện và cập nhật cần nằm trong cùng thao tác nguyên tử theo đúng phạm vi mà nguồn dữ liệu hỗ trợ**. Một read trước rồi write vô điều kiện không loại bỏ race, dù cả hai lệnh riêng lẻ đều hợp lệ.

Tuy nhiên CAS không tự giải quyết mọi bài toán. Nó không thay thế unique constraint xuyên nhiều document, idempotency của retry, transaction cho invariant liên tài nguyên hoặc versioned synchronization cho projection bất đồng bộ.

> **Đưa điều kiện vào thao tác ghi; dùng unique constraint để chặn cấp trùng; dùng version để phát hiện stale state; dùng idempotency cho retry; dùng transaction/workflow khi invariant trải nhiều tài nguyên.**

Khi áp dụng đúng năm nguyên tắc đó, hệ NoSQL có thể chống lost update, overselling, duplicate creation và stale overwrite mà vẫn khai thác được hiệu năng của cập nhật có điều kiện.

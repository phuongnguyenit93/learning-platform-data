# Retry khi giao dịch xung đột và phạm vi dữ liệu cần đọc lại

Trong **Database No SQL** phân tán, hai request hợp lệ có thể cùng thay đổi những dữ liệu liên quan. Database có thể phát hiện xung đột, hủy một transaction, báo version mismatch hoặc từ chối một conditional write. Lúc này, ứng dụng thường được khuyên **retry**. Tuy nhiên, retry không đơn giản là lặp lại câu lệnh ghi: nếu kết quả được tính từ dữ liệu cũ, lần ghi tiếp theo có thể thành công về kỹ thuật nhưng **sai nghiệp vụ**.

Hãy hình dung một lượt checkout: ứng dụng đọc tồn kho, giá sản phẩm, trạng thái khách hàng và hạn mức coupon rồi tính tổng tiền. Một giao dịch khác mua hàng hoặc đổi giá trước khi checkout commit. Nếu transaction đầu bị abort, việc chỉ đọc lại tồn kho mà giữ nguyên giá, coupon và quyền mua từ snapshot cũ có thể tạo một đơn hàng không còn hợp lệ.

Bài này thuộc chương **Lỗi phân tán và retry**. Ta sẽ làm rõ:

- Các loại xung đột và sự khác nhau với timeout, lỗi mạng hoặc kết quả commit chưa rõ.
- Ba cấp retry: conditional operation, toàn transaction và commit.
- **Read set**, **write set**, cùng **tập dữ kiện phụ thuộc quyết định**.
- Cách xác định phải đọc lại document nào, query/predicate nào và invariant nào.
- Các trường hợp write skew, phantom, unique constraint và quyền truy cập.
- Ví dụ MongoDB, DynamoDB, Cassandra, Redis cùng quy trình backend Java.
- Idempotency, outbox, backoff/jitter, retry budget, đo lường và kiểm thử concurrency.

**Nguyên tắc:** Khi transaction bị abort và phải làm lại, hãy **đọc lại và tính lại mọi dữ kiện mutable có thể làm thay đổi quyết định ghi trong lượt mới**. Không nhất thiết đọc lại cả database; cần đọc lại **đúng tập phụ thuộc của nghiệp vụ**, trong một consistency scope đủ mạnh.

## 1. Giao dịch xung đột là gì?

Ví dụ số lượng sản phẩm:

~~~text
Ban đầu: available = 1, version = 7
T1: đọc available=1, version=7
T2: đọc available=1, version=7
T2: ghi version=8, available=0, commit
T1: cố ghi dựa trên version=7
T1: conflict/conditional check failed
~~~

Một cơ chế optimistic concurrency đúng có thể ngăn T1 ghi đè trạng thái mới. Đây có thể là hành vi mong muốn, không phải bug.

Nhưng nếu T1 chỉ đổi expected version từ 7 sang 8 mà vẫn giữ kết quả đã tính, nó có thể **bỏ qua điều kiện available >= 1**. Cách retry phải bảo toàn invariant ngay cả khi dữ liệu thay đổi giữa các attempts.

## 2. Phân biệt các lỗi thường gặp

| Hiện tượng | Ví dụ | Có thể làm gì? |
|---|---|---|
| Optimistic locking conflict | Version không còn khớp | Đọc lại state và quyết định |
| Write conflict/transaction abort | Hai transaction ghi vào dữ liệu cạnh tranh | Retry toàn transaction nếu lỗi retryable |
| Serialization failure | Engine không thể bảo toàn lịch sử theo isolation đã chọn | Chạy lại transaction từ snapshot mới |
| Deadlock victim | Một transaction bị abort để giải deadlock | Retry transaction trong ngân sách |
| Conditional check failed | Tồn kho đã hết, trạng thái không còn cho phép | Có thể là từ chối nghiệp vụ |
| Duplicate key | Key đã được tạo | Xét idempotency hoặc trả lỗi nghiệp vụ |
| Throttling | Quota/capacity tạm thời | Backoff, jitter, giảm tải |
| Network timeout trước outcome | Response mất | Tra outcome hoặc dùng idempotency |
| Unknown commit result | Commit có thể đã xảy ra | Retry commit/reconcile theo driver, không replay mù |
| Validation/authorization error | Schema sai hoặc không đủ quyền | Không retry nguyên trạng |
| Read too stale | Replica chưa đạt mốc yêu cầu | Chờ/route/error theo consistency contract |

**Không dùng một nhánh `catch (Exception e) { retry(); }` cho tất cả.** Một số lỗi là tín hiệu để tính toán lại, một số lỗi phải trả business rejection, và một số đòi xác minh commit trước.

## 3. Retry có những phạm vi khác nhau

| Cấp retry | Lặp lại cái gì? | Hợp đồng cần có |
|---|---|---|
| Operation retry | Một request/lệnh đơn lẻ | Idempotent hoặc conditional semantics |
| CAS retry | Đọc version mới và thử compare-and-swap | Kiểm tra invariant trên state hiện hành |
| Transaction retry | Begin mới, read–validate–write–commit lại | Lỗi abort được xác nhận; read dependencies trong attempt mới |
| Commit retry | Thử commit của cùng attempt | Hành vi cho unknown outcome được driver hỗ trợ |
| Workflow retry | Một bước trong quy trình nhiều service | Durable state, idempotency và reconciliation |
| Message retry | Consumer nhận lại event | Deduplication, ordering và side-effect safety |

**Retry commit không đồng nghĩa retry transaction body.** Nếu commit đã thành công nhưng ACK mất, chạy lại body có thể tạo đơn hàng, thanh toán hoặc event trùng.

## 4. Lập sơ đồ xung đột

~~~mermaid
sequenceDiagram
    participant T1 as Transaction A
    participant DB as NoSQL
    participant T2 as Transaction B
    T1->>DB: Read item v10
    T2->>DB: Read item v10
    T2->>DB: Conditional write v10→v11
    DB-->>T2: Commit
    T1->>DB: Write dựa trên v10
    DB-->>T1: Conflict / abort
    Note over T1,DB: T1 cần attempt mới và state mới
~~~

Thông báo conflict có thể chỉ cho biết **điểm chạm kỹ thuật**. Nó không nhất thiết liệt kê tất cả dữ kiện đã ảnh hưởng tới quyết định nghiệp vụ trong T1.

## 5. Read set, write set và decision dependencies

Ba khái niệm quan trọng:

- **Read set R:** dữ liệu, phiên bản hoặc tập kết quả mà transaction đã quan sát.
- **Write set W:** state mà transaction sẽ thay đổi.
- **Decision dependencies D:** tất cả dữ kiện được dùng để quyết định *được làm hay không*, *làm bao nhiêu*, *với điều kiện nào* và *cho ai*.

Ví dụ checkout:

~~~text
R:
  Inventory(sku-A)
  Price(sku-A)
  Coupon(X)
  Customer(C9)
  CouponUsages where coupon=X and customer=C9

W:
  Inventory(sku-A)
  CouponUsage(X,C9)
  Order(O101)
  OutboxEvent(E101)

D:
  available >= quantity
  current effective price
  coupon eligible, not expired, quota available
  customer active and tenant authorized
  operationId not processed
~~~

**D không trùng W.** Price hoặc Customer có thể không được ghi, nhưng có thể quyết định toàn bộ transaction có được commit hay không.

## 6. Quy tắc chọn dữ liệu cần đọc lại

Khi bắt đầu attempt mới, cần:

1. Xác định **nguồn có thẩm quyền** của mỗi dependency.
2. Đọc lại các state mutable cần dùng.
3. Đọc lại các **predicate** về tồn tại/không tồn tại nếu quyết định phụ thuộc chúng.
4. Tính lại các derived values.
5. Xác minh business rule/authorization hiện hành nếu cần.
6. Dùng conditional write, transaction hoặc isolation phù hợp để bảo vệ invariant **tại commit**.
7. Dừng nếu điều kiện không còn hợp lệ; không cố ép transaction cũ thành công.

Không cần tải mọi record của tenant, nhưng cũng không được chỉ đọc document mà exception nêu tên.

## 7. Snapshot nhất quán nhưng có thể cũ

Một transaction có thể đọc theo snapshot:

~~~text
Attempt 1 snapshot S10:
  Inventory v10
  Price v5
  Coupon v2

Transaction khác:
  sửa Price thành v6
  sửa Inventory thành v11
  commit

Attempt 1:
  write conflict -> abort
~~~

Retry phải dùng **attempt/snapshot mới** cho những dữ liệu có ảnh hưởng, thay vì giữ price/coupon từ S10 một cách vô điều kiện.

Lưu ý: “đọc mới” chưa đủ nếu các dữ kiện đến từ **replica/cache khác nhau với consistency khác nhau**. Cần consistency scope có thể chứng minh các write và điều kiện hợp lệ đồng thời.

## 8. Đọc lại duy nhất document bị conflict có thể sai

Giả sử attempt đầu đọc:

~~~text
stock=5
price=100000
coupon.discount=10%
total=90000
~~~

Sau đó có transaction khác giảm stock và thay price thành 120000. Attempt đầu abort vì stock conflict.

Retry sai:

~~~text
Read stock mới=4
Giữ price cũ=100000
Giữ total cũ=90000
Ghi Order
~~~

Retry đúng phải đọc lại price nếu giá tại thời điểm checkout mới có hiệu lực, hoặc phải có **price quote hợp lệ** đã được bảo vệ theo contract. Nếu coupon quota, thuế hoặc quyền khách hàng có thể đổi, những phụ thuộc ấy cũng phải được kiểm tra lại.

**Phạm vi đọc lại do business invariant quyết định, không do error message quyết định.**

## 9. Trường hợp chỉ một document là đủ

Nếu điều kiện và mutation đều nằm trong một document:

~~~text
Mục tiêu: giảm stock một đơn vị
Điều kiện: available >= 1
Không có side condition ở document khác
~~~

Một MongoDB single-document conditional update:

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "tenant-1#sku-A",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1 }
  }
);
~~~

Điều kiện được kiểm tra ở **lúc ghi**, tránh race giữa GET và UPDATE. Nếu không match, cần xem đó là hết hàng hay tài nguyên mất, không retry vô hạn.

## 10. CAS với version

Document:

~~~javascript
{
  _id: "wallet-A",
  balance: 10,
  version: NumberLong("7")
}
~~~

Sau khi đọc version 7, ứng dụng muốn trừ 2:

~~~javascript
db.wallets.updateOne(
  {
    _id: "wallet-A",
    version: NumberLong("7"),
    balance: { $gte: 2 }
  },
  {
    $inc: { balance: -2, version: 1 }
  }
);
~~~

Nếu không match, có thể vì version đã đổi, số dư không đủ hoặc ID không tồn tại. Retry đúng phải **đọc trạng thái mới**, rồi phân biệt business rejection với CAS conflict.

Sai:

~~~text
CAS v7 fail
Tự thay expectedVersion=8
Giữ nguyên số dư tính từ v7
Thử ghi lại
~~~

Đúng:

~~~text
CAS v7 fail
Read current balance/version
Re-evaluate amount và điều kiện
Thử CAS với version mới hoặc trả insufficient funds
~~~

## 11. Cần retry transaction hay CAS?

| Dạng nghiệp vụ | Hướng tiếp cận |
|---|---|
| Giảm stock một document | Conditional update đơn document |
| Thay field nếu version đúng | Optimistic CAS |
| Create Order + reserve nhiều item | Transaction/workflow tùy engine |
| Username unique | Unique constraint/conditional insert |
| Hai ví chuyển tiền | Atomic multi-item transaction hoặc ledger workflow |
| Một giới hạn phụ thuộc tập kết quả | Serializable constraint hoặc owner/counter phối hợp |
| Side effect ngoài database | Outbox, idempotency, reconciliation |

**Đừng tạo transaction dài cho một điều kiện có thể viết thành atomic single-document update.** Transaction rộng làm tăng contention, nhưng cố “đơn giản hóa” thành nhiều writes độc lập cũng có thể phá invariant.

## 12. Sơ đồ retry transaction

~~~mermaid
flowchart TD
    In["Request và stable operationId"] --> Begin["Mở transaction mới"]
    Begin --> Read["Đọc lại decision dependencies"]
    Read --> Valid{"Điều kiện nghiệp vụ hợp lệ?"}
    Valid -->|"Không"| Reject["Trả business rejection"]
    Valid -->|"Có"| Write["Thực hiện write-set"]
    Write --> Commit["Commit"]
    Commit --> Outcome{"Outcome"}
    Outcome -->|"Committed"| Success["Success"]
    Outcome -->|"Retryable abort"| Budget{"Còn retry budget?"}
    Budget -->|"Có"| Delay["Backoff có jitter"]
    Delay --> Begin
    Budget -->|"Không"| Busy["Báo contention / unavailable"]
    Outcome -->|"Unknown commit"| Resolve["Retry commit hoặc reconcile"]
    Resolve --> Outcome
~~~

Nhánh **unknown commit** không được tự chuyển tới Begin khi chưa hiểu outcome.

## 13. Những dữ liệu nên giữ giữa các attempts

| Dữ liệu | Giữ nguyên? | Vì sao |
|---|---|---|
| Client request ID | Có | Cùng một ý định |
| Idempotency key | Có | Chặn side effect lặp |
| Quantity khách yêu cầu | Có | Input của khách |
| Stable Order ID dự định | Có thể | Giúp deduplicate nếu ID cấp trước |
| Price đọc lần đầu | Thường không | Có thể đã thay đổi |
| Stock đọc lần đầu | Không | Có thể đã bị mua |
| Coupon quota đọc lần đầu | Không | Có thể hết |
| Expected version cũ | Không | CAS phải dùng version hiện hành |
| Business rule thuần túy | Có | Code logic có thể dùng lại |
| Mutable policy value | Cần xem lại | Có thể thay đổi |
| External payment outcome | Không gửi lại mù | Có thể đã thực thi |
| Query shape | Có | Logic truy vấn không đổi |
| Result set IDs từ lần trước | Không mặc định | Có thể xuất hiện phantom |

Phân biệt **input bất biến của ý định** với **state mutable tại nguồn**.

## 14. Read set theo ID và theo predicate

Có thể đọc:

~~~text
By ID:
  Product(P1)
  Inventory(P1)
  Customer(C9)

By predicate:
  Bookings where room=R and overlaps interval I
  CouponUsages where customer=C9 and coupon=X
  Doctors where onCall=true in region=R
~~~

Khi retry, một predicate cần được chạy lại nếu quyết định phụ thuộc vào tập kết quả. Chỉ đọc lại các ID xuất hiện ở lần đầu là chưa đủ vì **document mới** có thể thỏa predicate, hoặc document cũ có thể biến mất.

## 15. Phantom: “không có record” cũng là dữ liệu

Quy tắc:

> Không được có hai booking chồng thời gian cho cùng phòng.

Lượt đầu:

~~~text
Query overlapping bookings -> empty
Attempt abort
Request khác tạo booking mới
~~~

Retry sai: giữ kết luận “empty” từ attempt trước rồi insert.

Retry đúng: kiểm tra lại predicate hoặc dùng một cấu trúc dữ liệu có **atomic owner/constraint** kiểm soát quyền đặt. Đặc biệt, chỉ query lại predicate trong snapshot isolation **không tự bảo đảm không có phantom** nếu isolation/engine không bảo vệ predicate hoặc tạo xung đột ghi phù hợp.

## 16. Write skew khi không cùng write document

Quy tắc: một bệnh viện luôn phải có ít nhất một bác sĩ trực.

~~~text
A.onCall=true
B.onCall=true

T1: đọc A,B -> quyết định A.offCall
T2: đọc A,B -> quyết định B.offCall
T1: ghi A=false
T2: ghi B=false
~~~

Nếu T1 và T2 ghi hai document khác nhau, dưới một số mô hình snapshot isolation chúng có thể cùng commit, làm count=0.

Điểm quan trọng:

- Retry khi có conflict chỉ giúp nếu conflict được phát hiện.
- Không có write-write conflict không có nghĩa invariant an toàn.
- Cần serializable isolation hoặc thiết kế một **shared owner/counter/constraint** để các transaction cùng tranh nhau một điểm bảo vệ.

Đọc lại là điều kiện cần cho retry, **không phải phép thay thế isolation guarantee**.

## 17. Dùng owner document để tạo conflict có nghĩa

Ví dụ một document policy:

~~~javascript
{
  _id: "hospital-1#2026-11-14#on-call",
  onCallCount: 2,
  version: 17
}
~~~

Muốn cho một bác sĩ nghỉ trực, phải đảm bảo count vẫn >=2 trước khi giảm. Nếu trạng thái bác sĩ ở document khác, việc giảm counter và đổi trạng thái bác sĩ phải nằm trong một transaction/workflow đủ đúng hoặc một aggregate document, tùy engine.

Nếu cả hai transaction tranh cùng policy document bằng conditional update, hệ có điểm để phát hiện conflict thay vì write skew âm thầm.

Nhưng một owner document duy nhất có thể thành **hot document** khi concurrency cao. Cần cân bằng correctness, contention và phạm vi aggregate.

## 18. Unique username: retry không thay constraint

Hai request cùng kiểm tra username NOVA chưa tồn tại:

~~~text
T1: query user where username=NOVA -> none
T2: query user where username=NOVA -> none
T1: insert NOVA
T2: insert NOVA
~~~

Muốn unique thật, cần unique index/conditional insert trên source phù hợp.

Ví dụ MongoDB:

~~~javascript
db.usernames.createIndex(
  { tenantId: 1, normalizedUsername: 1 },
  { unique: true }
);
~~~

Trên sharded collection, cần kiểm tra ràng buộc unique index với shard key và phiên bản MongoDB. Không mặc định index tùy ý thực thi uniqueness toàn cluster.

Khi insert xung đột:

- Nếu cùng idempotency key, có thể trả lại outcome đã có.
- Nếu username đã do người khác dùng, trả lỗi nghiệp vụ.
- Không retry insert vô tận với cùng username như thể lỗi chỉ tạm thời.

## 19. Dữ kiện về quyền truy cập cũng là dependency

Một transaction duyệt đơn có thể dựa vào:

~~~text
Order.status=PENDING
Order.version=7
Actor.role=APPROVER
Policy.maxAmount=1000000
Order.tenantId=T
~~~

Nếu retry sau conflict, có thể trong lúc đó:

- Order bị hủy.
- Role bị thu hồi.
- Hạn mức phê duyệt bị thay đổi.
- Tenant bị khóa.
- Người dùng đã logout hoặc token hết hạn.

Khi quyết định nghiệp vụ đòi quyền hiện hành, phải xác minh lại tại nguồn/consistency phù hợp. **Không dùng role cache cũ để cấp một quyền đã bị revoke** chỉ vì read trước transaction đã thành công.

Một số hợp đồng nghiệp vụ dùng policy snapshot theo mốc định sẵn; cần thiết kế rõ effective time và bằng chứng, không mặc định quyền luôn bất biến.

## 20. Read-only dependencies có thể rất quan trọng

Chuyển tiền có write set:

~~~text
Debit Wallet A
Credit Wallet B
Record Transfer
~~~

Nhưng decision dependencies có thể gồm:

~~~text
Wallet A balance
Wallet B status
Account A blocked flag
Daily transfer limit
Fee policy
Currency quote
Anti-fraud decision
~~~

Nếu transaction conflict ở Wallet A, không thể chỉ đọc lại Wallet A nếu fee/policy/recipient status có thể quyết định tính hợp lệ của transfer.

Với dữ liệu thuộc service ngoài, cần xác định **atomicity boundary**: một transaction NoSQL không tự bao trùm anti-fraud API hoặc external FX quote. Có thể cần quote version/TTL, authorization token, reservation hoặc saga.

## 21. Derived values phải được tính lại

Ví dụ:

~~~text
subtotal = sum(currentUnitPrice * requestedQuantity)
discount = applyEligibleCoupon(currentCoupon)
tax = applyTaxPolicy(currentPolicy)
total = subtotal - discount + tax
~~~

Trong lượt retry, nếu một dependency có thể đổi, `total` cũ phải được bỏ hoặc tái xác minh.

Một thiết kế tốt tách **pure decision function** khỏi I/O:

~~~java
Decision calculate(
    CheckoutRequest request,
    PriceState prices,
    InventoryState inventory,
    CouponState coupon,
    CustomerState customer
) {
    // Không gọi email, payment hay queue.
    // Kiểm tra business rules và trả decision.
    return decision;
}
~~~

Mỗi attempt mới lấy trạng thái mới rồi gọi lại cùng hàm quyết định. Điều này giúp test concurrency và tránh side effect lặp.

## 22. Khi nào có thể giữ dữ liệu của attempt trước?

Nếu một dữ kiện thật sự **immutable theo domain** hoặc được gắn với một quote có hiệu lực được bảo vệ, có thể giữ nó qua retry.

Ví dụ:

~~~text
PriceQuote:
  quoteId=Q100
  productId=P9
  amount=100000
  expiresAt=2026-11-14T10:05:00Z
  version=3
~~~

Có thể dùng lại quote nếu hợp đồng business cho phép giá đã báo được giữ trong thời hạn, quote không bị đổi trái contract và transaction xác minh nó còn hiệu lực.

Đây không giống việc “price cache chưa refresh”. **Dữ liệu bất biến theo hợp đồng và dữ liệu tình cờ chưa đổi là hai khái niệm khác nhau.**

## 23. Dữ liệu hết hạn theo thời gian

Những điều kiện có thể đổi khi retry:

- Coupon expiry.
- Reservation TTL.
- Checkout deadline.
- Exchange quote expiration.
- Daily quota reset.
- Token revocation.
- Shipping capacity cutoff.

Một attempt hợp lệ lúc 09:59:59 nhưng retry lúc 10:00:02 có thể phải từ chối.

Cần phân biệt:

- **Request time:** thời điểm người dùng gửi.
- **Transaction/commit time:** thời điểm hệ chấp nhận thay đổi.
- **Event/effective time:** mốc nghiệp vụ áp chính sách.

Nếu business chọn “giá/coupon hiệu lực tại commit”, retry phải tính theo điều kiện mới. Nếu business bảo đảm giữ quote trong năm phút, phải xác minh **quote còn sống**, không tự làm mới vô hạn.

## 24. Consistent snapshot và đọc từ cache

Một retry có thể đọc Stock từ source nhưng Price từ Redis:

~~~text
Stock source version=11
Price cache version=5
Price source version=6
~~~

Dù ứng dụng đã “đọc lại cả hai”, dữ kiện có thể không nhất quán.

Các câu hỏi cần trả lời:

1. Dữ liệu nào là source-of-truth?
2. Cache có freshness guarantee gì?
3. Transaction có bao trùm cả hai source không?
4. Có snapshot/causal token nào áp dụng không?
5. Conditional write tại commit có kiểm tra version của Price/Quote không?
6. Nếu source không available, API có được phép dùng stale không?

**Read-after-retry không tự là strong read**, càng không tự là transaction snapshot qua nhiều database.

## 25. Khi conflict liên quan quyền sở hữu partition

Một hệ phân mảnh có thể đổi partition owner/leader giữa attempts.

~~~text
Attempt 1:
  Owner epoch 15, read item v10
  Conflict/step-down

Attempt 2:
  Owner epoch 16
  Need new routing and authoritative state
~~~

Không reuse session/transaction ID hoặc connection cũ nếu driver yêu cầu tạo attempt mới. Fencing epoch, token, lease và consistency scope có thể khác.

Khi gặp NotLeader/PrimarySteppedDown, **driver/discovery** nên cập nhật topology. Nhưng việc chọn đúng leader mới không tự làm derived values từ leader cũ hợp lệ.

## 26. Query theo predicate có thể thay đổi tập kết quả

Ví dụ khách chỉ được dùng một coupon cho mỗi campaign:

~~~text
Attempt 1:
  SELECT usages WHERE campaign=C and customer=U
  result empty

Attempt 1 abort

Attempt khác:
  INSERT usage(C,U)

Attempt 2:
  Cần kiểm tra lại sự tồn tại của usage
~~~

Giải pháp mạnh thường là dùng một **unique compound key** `campaign#customer` và conditional insert, thay vì chỉ query thiếu bản ghi rồi hy vọng không ai ghi giữa chừng.

Đây là nguyên tắc tổng quát: **đưa invariant vào đúng write primitive nếu có thể**, thay vì trông chờ transaction retry chữa mọi race.

## 27. Read set và dependency closure

Một phương pháp thiết kế:

~~~text
Decision: ApproveOrder(O)

Dependencies:
  O.status
  O.version
  Customer(O.customerId).active
  Approver.role
  ApprovalPolicy.maxAmount
  O.total
  CurrencyQuote.version (nếu ảnh hưởng)
  IdempotencyRecord(requestId)
~~~

Tập này là **decision closure**: mọi dữ kiện mutable mà outcome của operation phụ thuộc vào.

Khi retry:

- Reread hoặc validate những dependency có thể đổi.
- Không tự thêm mọi record không liên quan.
- Nếu dependency được mô hình hóa bằng predicate, rerun predicate.
- Nếu dependency nằm ngoài transaction, phải có contract riêng.
- Nếu dữ liệu immutable, có thể giữ cùng content/version theo hợp đồng.

Giúp tránh hai cực đoan: **chỉ reread conflict document** và **quét lại toàn bộ tenant**.

## 28. Java: mẫu retry theo transaction callback

Ở tầng Java, có thể viết một abstraction dạng pseudocode framework-independent:

~~~java
CheckoutOutcome executeCheckout(CheckoutRequest request) {
    String operationId = request.operationId(); // ổn định giữa các attempts

    for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        if (deadlineExceeded()) {
            return CheckoutOutcome.temporarilyUnavailable();
        }

        try {
            return transactionManager.inNewTransaction(tx -> {
                // Tất cả read thuộc cùng attempt/consistency scope.
                InventoryState stock = inventoryRepo.read(tx, request.sku());
                PriceState price = priceRepo.read(tx, request.sku());
                CouponState coupon = couponRepo.read(tx, request.coupon());
                CustomerState customer = customerRepo.read(tx, request.customerId());
                OperationState op = idempotencyRepo.read(tx, operationId);

                if (op.isCompleted()) {
                    return op.existingOutcome();
                }

                Decision decision = checkoutPolicy.evaluate(
                    request, stock, price, coupon, customer
                );

                if (decision.isRejected()) {
                    return CheckoutOutcome.rejected(decision.reason());
                }

                inventoryRepo.reserveConditionally(tx, stock, request.quantity());
                couponRepo.consumeConditionally(tx, coupon, request.customerId());
                orderRepo.insert(tx, operationId, decision);
                idempotencyRepo.complete(tx, operationId, decision);
                outboxRepo.append(tx, operationId, "OrderPlaced", decision);

                return CheckoutOutcome.accepted(decision);
            });
        } catch (RetryableTransactionAborted ex) {
            if (!hasRetryBudget(attempt)) {
                return CheckoutOutcome.temporarilyUnavailable();
            }
            sleepWithJitter(attempt);
        }
    }

    return CheckoutOutcome.temporarilyUnavailable();
}
~~~

**Đây là Java pseudocode**: `transactionManager`, repositories, exceptions và result types là abstraction minh họa, không phải một SDK có thể biên dịch ngay.

Điểm cốt lõi:

- `inNewTransaction` phải tạo attempt mới, có commit đúng scope.
- Mọi state dependency được read trong callback mới.
- Business rejection khác retryable abort.
- Idempotency record và outbox nằm trong transaction nếu engine hỗ trợ.
- Không gọi payment/email/network bên trong callback có thể bị chạy nhiều lần.
- Unknown commit outcome cần nhánh xử lý riêng, không coi là aborted.
- Java Thread.sleep không phù hợp nếu đang chặn event loop hoặc hết request deadline; dùng scheduler/cancellation phù hợp môi trường.

## 29. Không nuốt lỗi để tự commit một transaction đã abort

Một anti-pattern:

~~~java
try {
    tx.updateInventory(...);
} catch (WriteConflictException ex) {
    // Thử chạy lại một câu UPDATE bên trong tx cũ.
    tx.updateInventory(...);
}
tx.commit();
~~~

Ở nhiều engine, transaction đã bị đánh dấu abort hoặc snapshot không còn hợp lệ. Retry một statement **trong cùng transaction** không thể giải quyết state cũ hoặc quy tắc abort.

Khi driver báo cần retry toàn transaction, phải **hủy attempt cũ và mở attempt mới**. Những transaction đã commit/unknown outcome lại cần xử lý khác.

## 30. Scope retry và scope transaction phải khớp

Một lỗi thường gặp:

~~~text
Outer:
  read Product Price
  read Coupon

Inner retry:
  begin transaction
  read Inventory
  write Order
  commit
~~~

Chỉ **inner** được chạy lại. Nếu outer reads quyết định amount hoặc permission, scope retry quá hẹp.

Thiết kế lại:

~~~text
Outer:
  operationId, request payload, deadline

Each transaction attempt:
  read mutable Product Price
  read Coupon
  read Inventory
  read Customer status
  evaluate
  conditional write
  commit
~~~

Khi kiểm tra code, hãy nhìn xem các **đọc mutable** nằm ở đâu so với vòng retry, không chỉ nhìn vào catch block.

## 31. MongoDB: transaction conflict và retry

MongoDB hỗ trợ multi-document transaction trong những deployment được hỗ trợ. Trong các tình huống như write conflict, transaction có thể abort và driver/ứng dụng phải bắt đầu lượt mới theo contract.

Phân biệt các khái niệm:

- `session`: ngữ cảnh của các operation liên quan.
- `startTransaction`: mở transaction attempt.
- `readConcern`: semantics của dữ liệu được đọc.
- `writeConcern`: mức acknowledgment của commit/write.
- `TransientTransactionError`: một nhãn lỗi giúp nhận diện trường hợp có thể retry **toàn transaction** theo driver contract.
- `UnknownTransactionCommitResult`: một nhãn chỉ **kết quả commit chưa rõ**, thường cần retry commit theo quy trình được hỗ trợ, không tự replay body.
- Driver helper như `withTransaction` có cơ chế retry theo SDK và version, với các giới hạn riêng.

**Không tự áp dụng việc retry mọi lỗi MongoDB dưới dạng full transaction**. Phải xét labels, stage, session state và driver.

## 32. MongoDB: callback có thể chạy nhiều lần

Ví dụ Node.js minh họa đơn giản đường transaction (API cụ thể cần dùng theo MongoDB Node driver version):

~~~javascript
const session = client.startSession();

try {
  const outcome = await session.withTransaction(async () => {
    const stock = await db.collection("inventory").findOne(
      { _id: "tenant-1#sku-A" },
      { session }
    );

    const price = await db.collection("prices").findOne(
      { _id: "tenant-1#sku-A" },
      { session }
    );

    if (!stock || stock.available < 1 || !price) {
      return { accepted: false, reason: "UNAVAILABLE" };
    }

    const result = await db.collection("inventory").updateOne(
      { _id: stock._id, available: { $gte: 1 } },
      { $inc: { available: -1 } },
      { session }
    );

    if (result.matchedCount !== 1) {
      throw new Error("Reservation failed");
    }

    await db.collection("orders").insertOne(
      {
        _id: "order-101",
        sku: stock._id,
        unitPriceMinor: price.unitPriceMinor,
        quantity: 1
      },
      { session }
    );

    return { accepted: true, orderId: "order-101" };
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  return outcome;
} finally {
  await session.endSession();
}
~~~

**Ví dụ giới hạn để giải thích vị trí của read trong transaction**, không phải production checkout code: chưa gồm idempotency lookup, toàn bộ business validation, stable request IDs, deadline, error classification, unique constraints, outbox hoặc external payments.

Điểm chính: các lệnh `findOne` cho stock và price nằm **trong callback**, nên khi helper phải chạy lại transaction theo contract, chúng được thực thi lại. Không nên đặt chúng ngoài callback rồi capture các object cũ.

Trong transaction MongoDB, tránh chạy song song các operation trên cùng session nếu driver/session contract không cho phép. Đọc tuần tự như ví dụ giúp rõ thứ tự.

## 33. Không gọi external API trong callback transaction

Anti-pattern:

~~~javascript
await session.withTransaction(async () => {
  await db.collection("orders").insertOne(order, { session });
  await paymentGateway.charge(card, amount);
  await emailService.sendConfirmation(userEmail);
});
~~~

Nếu callback bị retry do conflict:

- Payment có thể bị charge nhiều lần.
- Email có thể gửi trùng.
- HTTP call có thể thành công dù transaction sau đó abort.
- External service không tự rollback theo MongoDB transaction.

Hướng phù hợp:

~~~text
Within DB transaction:
  validate state
  update inventory
  insert Order
  write Outbox event
  commit

After commit:
  Outbox consumer dispatches event
  Payment worker uses stable idempotency key
  Reconcile unknown payment outcomes
~~~

Nếu nghiệp vụ yêu cầu reserve/authorize payment trước commit, cần saga/state machine và compensation được thiết kế; không giả định database transaction bao trùm payment gateway.

## 34. UnknownTransactionCommitResult khác TransientTransactionError

Một sơ đồ khái quát:

~~~text
Error during transaction body:
  Transaction definitely aborted/retryable
    -> retry whole body with new reads

Error while committing:
  Outcome unknown
    -> retry commit / resolve status per driver
    -> do not blindly rerun side effects
~~~

Trong một số driver MongoDB, tiện ích `withTransaction` quản lý những nhánh này. Nếu tự implement, phải tuân thủ thuật toán retry đúng mà driver công bố, không chỉ so string message.

Unknown commit không có nghĩa transaction thất bại. Nếu client đã gửi commit và response mất, server có thể đã commit. Một lần replay toàn bộ body có thể chèn Order thứ hai nếu không có idempotency.

## 35. Commit thành công nhưng response bị mất

Timeline:

~~~text
t0 Client gửi checkout K
t1 DB commit Order O101
t2 Network mất response
t3 Client nhận timeout
t4 Client retry checkout K
~~~

Bắt buộc phân biệt:

- Có thể Order đã tồn tại.
- Client chưa biết outcome.
- Không được trừ inventory thêm một lần nếu cùng ý định K.
- Server cần truy vấn idempotency record hoặc key unique để trả outcome cũ.
- Trong một số trường hợp phải retry **commit của cùng attempt**, không tự mở business transaction mới.
- Request mới dùng **cùng operationId**, không tạo operation ID mới mỗi lần.

**Idempotency bảo vệ hiệu ứng nghiệp vụ; transaction retry bảo vệ tính nhất quán của một attempt.** Chúng bổ sung cho nhau.

## 36. DynamoDB: transactional writes và conditional checks

DynamoDB hỗ trợ conditional writes và transactional APIs với semantics được công bố. Một transaction gồm nhiều actions có thể bị hủy do **conflict**, **condition failed**, **capacity/throttling** hoặc lý do khác.

Ý tưởng TransactWriteItems:

~~~text
TransactWriteItems:
  Update Inventory if available >= requestedQuantity
  Update CouponQuota if remainingUses >= 1
  Put Order if orderId does not exist
  Put IdempotencyRecord if operationId does not exist
~~~

Cần:

- Xác định condition failure là business outcome hay race.
- Đọc lại state cần thiết để tính giá/coupon nếu muốn retry một quyết định mới.
- Dùng transaction idempotency token theo giới hạn SDK/API nếu thích hợp.
- Không mặc định mỗi failure có thể được giải quyết bằng backoff.
- Giữ stable operation ID ở tầng nghiệp vụ.
- Không suy một DynamoDB transaction local tự bao trùm mọi Global Tables region hoặc external service.

## 37. DynamoDB: phân biệt transaction conflict và condition failed

Ví dụ:

~~~text
T1 và T2 cùng cập nhật Inventory
T1 commit thành công
T2 bị transaction conflict
~~~

Một retry T2 có thể đọc lại và thử tiếp.

Nhưng:

~~~text
Inventory.available = 0
T2 đòi available >= 1
ConditionCheckFailed
~~~

Đây có thể là **hết hàng thật**, không phải transient conflict. Retry nguyên request 100 lần không làm xuất hiện stock; còn có thể gây overload.

Thông thường logic nên:

1. Xác định cancellation reason/mã lỗi theo SDK.
2. Nếu conflict retryable, backoff và làm lại decision dependencies.
3. Nếu điều kiện nghiệp vụ không thỏa, trả rejection.
4. Nếu capacity quá tải, backoff với retry budget theo khuyến nghị dịch vụ.
5. Nếu outcome commit không rõ, tra idempotency/transaction semantics, không gửi tác dụng phụ mù.

## 38. DynamoDB: Java pseudocode hướng transaction

Ví dụ khái niệm Java:

~~~java
CheckoutOutcome retryCheckout(CheckoutRequest request) {
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        InventoryState stock = readInventoryFresh(request.sku());
        PriceState price = readPriceFresh(request.sku());
        CouponState coupon = readCouponFresh(request.coupon());

        Decision decision = evaluate(request, stock, price, coupon);
        if (!decision.allowed()) {
            return CheckoutOutcome.rejected(decision.reason());
        }

        try {
            // Transactional Update/Put với ConditionExpression.
            transactWriteItems(
                request.operationId(),
                stock.version(),
                price.version(),
                coupon.version(),
                decision
            );
            return CheckoutOutcome.accepted(decision);
        } catch (TransactionConflictDetected e) {
            backoffWithJitter(attempt);
        } catch (BusinessConditionFailed e) {
            // Có thể đọc để trả lý do hiện hành; không retry mù.
            return CheckoutOutcome.rejected("CURRENT_CONDITION_FAILED");
        }
    }
    return CheckoutOutcome.temporarilyUnavailable();
}
~~~

**Pseudocode không phải SDK Java có thể build trực tiếp.** Trước khi triển khai phải gắn actual exception classes, cancellation reasons, condition expressions, read consistency, transaction token và commit outcome semantics của AWS SDK v2 và cấu hình bảng.

Quan trọng: nếu transaction cần bảo đảm giá không đổi từ lúc đọc đến commit, **cần kiểm tra price version hoặc một price quote hợp lệ trong transaction**. Chỉ đọc `readPriceFresh` rồi gửi một UpdateInventory không đủ.

## 39. Cassandra: LWT và điều kiện IF

Cassandra Lightweight Transactions cho phép compare-and-set-style conditional operations theo phạm vi được hỗ trợ.

Ví dụ:

~~~sql
UPDATE inventory
SET available = 4, version = 8
WHERE tenant_id = 'tenant-1'
  AND sku = 'sku-A'
IF version = 7;
~~~

Một conditional statement có thể trả thông tin về việc điều kiện `IF` có được áp dụng hay không; **not applied** không nhất thiết là exception transient.

Nếu điều kiện không match:

- Đọc lại partition/row liên quan.
- Xác minh invariant trên state hiện hành.
- Tính mutation mới.
- Thử LWT mới nếu còn hợp lệ và còn retry budget.

Không tự sửa `IF version=8` mà giữ giá trị mới dựa trên v7. Nếu business invariant liên quan nhiều partition, LWT của một partition **không tự thành transaction serializable xuyên toàn Cassandra**.

## 40. Redis WATCH/MULTI/EXEC: optimistic transaction

Redis có mẫu optimistic concurrency với `WATCH`:

~~~text
WATCH key
GET key
Compute new value
MULTI
SET key newValue
EXEC
~~~

Nếu watched key bị thay đổi trước `EXEC`, transaction có thể không được thực hiện; client cần retry bằng cách **WATCH/GET/tính lại** trên lượt mới.

Một ví dụ pseudo-code:

~~~text
while attemptsRemain:
    WATCH inventoryKey
    value = GET inventoryKey
    if value <= 0:
        UNWATCH
        return SOLD_OUT
    MULTI
    SET inventoryKey (value - 1)
    success = EXEC
    if success:
        return RESERVED
    backoff
~~~

Thực tế có thể dùng atomic script hoặc primitive phù hợp thay cho WATCH ở bài toán đơn key. Cần hiểu Redis replication/durability/failover semantics, vì **atomic execution trên primary** không tự bảo đảm mọi acknowledged write sống sót qua mọi crash.

## 41. Không dùng one-size-fits-all transaction abstraction

Cùng một method `retryTransaction` không thể mặc định có cùng semantics ở:

- MongoDB multi-document transaction.
- DynamoDB TransactWriteItems.
- Cassandra LWT.
- Redis WATCH.
- Couchbase CAS.
- Một database có snapshot isolation nhưng không serializable.
- Một workflow qua nhiều services.

Phải ánh xạ:

- Operation scope.
- Conflict signal.
- Isolation level.
- Commit acknowledgment/unknown outcome.
- Retryable error classification.
- Read consistency.
- Idempotency primitives.
- Transaction limits.
- Multi-region behavior.

Không đặt tên abstraction “serializable” chỉ vì có nhiều conditional writes nếu engine không cung cấp guarantee tương ứng.

## 42. Retry với exponential backoff và jitter

Nếu 100 request cùng tranh một document, tất cả retry ngay lập tức có thể tiếp tục đụng nhau và tạo **retry storm**.

Một chiến lược thường dùng:

\[
d_a=\min(d_{\max},d_0\cdot 2^{a-1})
\]

Trong đó:

- `a` là số attempt.
- `d_0` là base delay.
- `d_max` là delay cap.

Sau đó lấy jitter, ví dụ **full jitter** trong khoảng từ 0 tới `d_a`.

~~~text
Attempt 1: random(0, 20ms)
Attempt 2: random(0, 40ms)
Attempt 3: random(0, 80ms)
Attempt 4: random(0, 160ms)
...
Cap theo deadline và maxDelay
~~~

Các con số chỉ minh họa. Hệ thực tế còn có SDK-managed retries, Retry-After, capacity quotas và SLO. Đừng để **retry ở nhiều tầng nhân nhau**: 3 lần ở SDK × 3 lần service × 3 lần gateway có thể tạo tới 27 thao tác phía dưới trong tình huống xấu.

## 43. Giới hạn retry bằng budget và deadline

Một loop an toàn cần:

- Số attempt tối đa.
- Deadline toàn request.
- Backoff có jitter.
- Cancellation khi client không còn chờ nếu hợp đồng cho phép.
- Chỉ retry lỗi được phân loại.
- Không retry business rejection.
- Dừng trước khi vượt thời gian sống của quote/reservation.
- Giới hạn concurrency và backpressure.
- Telemetry số attempts và nguyên nhân failure.

Không cần giữ transaction mở trong lúc backoff. Thường nên **abort/close attempt trước, chờ ngoài transaction, rồi mở attempt mới** để tránh giữ lock/snapshot/resource.

## 44. Retry storm là lỗi kiến trúc vận hành

Một hot key có thể khiến nhiều transaction abort. Nếu mỗi transaction lại retry quá nhiều lần:

~~~text
Higher conflicts
   -> More retries
   -> Higher concurrency and load
   -> More conflicts
~~~

Biện pháp ngoài backoff:

- Serial hóa command theo key/aggregate owner khi hợp lý.
- Queue hoặc admission control.
- Giảm transaction scope và thời gian giữ transaction.
- Thay read–modify–write bằng atomic increment/decrement.
- Tách hot partition/key theo domain.
- Batch hoặc combine writes nếu semantics cho phép.
- Giới hạn số concurrent transaction trên một resource.
- Dùng reservation token/lease với fencing khi cần.
- Scale capacity nhưng vẫn phân tích contention trên cùng key.

**Tăng throughput phần cứng không luôn giải quyết một hot document cần serialize mọi write.**

## 45. Giảm phạm vi đọc/ghi để giảm xung đột

Một transaction đọc quá nhiều tài nguyên, làm network call trong callback hoặc giữ transaction mở lâu dễ tăng xác suất state đổi trước commit.

Có thể cải thiện:

- Dời những bước thuần tính toán nặng ra ngoài transaction, nhưng đọc state mutable/validate lại trong attempt.
- Dùng index để đọc đúng document và giảm scan.
- Giảm số entity trong một invariant nếu business cho phép.
- Dùng atomic conditional update thay transaction khi chỉ cần một document.
- Đặt idempotency check gần authoritative write.
- Chuẩn hóa order of operations để giảm deadlock nơi áp dụng.
- Tối ưu payload, tránh external I/O trong transaction.
- Dùng outbox thay gọi service bên ngoài trước commit.

Nhưng không được “tối ưu” bằng cách bỏ bớt dependency khiến invariant bị phá.

## 46. Phân biệt business rejection với transient contention

Một API tốt không luôn trả HTTP 500 cho mọi CAS fail.

Ví dụ:

~~~text
Attempt 1: available=1
Transaction conflict
Attempt 2: available=0
Result: SOLD_OUT
~~~

Outcome cuối **không phải lỗi database cần retry thêm**. Đây là kết quả nghiệp vụ: hết hàng.

Tương tự:

- Order bị CANCELLED -> không được APPROVE.
- Coupon expired -> không được áp discount.
- User role revoked -> authorization denied.
- Version đổi nhưng cập nhật mới vẫn hợp lệ -> có thể retry.
- Duplicate requestId đã hoàn tất -> trả lại result cũ.
- Conflict liên tục vượt retry budget -> tạm unavailable/busy.

## 47. Quyết định retry phải có scope theo tenant

NoSQL nhiều tenant có thể dùng khóa `tenantId + entityId`. Một retry không được tự đọc một entity trùng business ID từ tenant khác vì thay routing hoặc bỏ điều kiện tenant.

Mỗi attempt phải:

1. Lấy tenant identity từ authentication context tin cậy.
2. Đọc các document đúng tenant scope.
3. Kiểm tra authorization.
4. Dùng full key/conditional write phù hợp.
5. Không để event/retry queue làm mất tenant context.
6. Không reuse idempotency key của tenant khác mà không namespace.

**Idempotency key thường cần scope theo tenant + operation type**, không chỉ raw string client gửi.

## 48. Khi đọc từ secondary hoặc search projection

Một attempt bị conflict, ứng dụng chờ vài mili giây rồi đọc từ secondary cũ:

~~~text
Source v12
Secondary v11
Retry reads v11
CAS based on v11 fails again
~~~

Điều này tạo vòng retry vô ích. Nếu nghiệp vụ cần current state, phải chọn read path có guarantee/freshness phù hợp, ví dụ authoritative source hoặc session/causal token theo engine.

Search index, GSI, cache và materialized view có thể stale dù source transaction đã abort. Đọc lại từ projection cũ **không bảo đảm decision được cập nhật**.

## 49. Không phải mọi xung đột đều đòi làm lại toàn bộ workflow

Giả sử saga có các bước:

~~~text
1. CreateOrder transaction đã commit
2. ReserveStock transaction đã commit
3. Payment authorization failed/transient
~~~

Nếu bước 3 retry, không nhất thiết tạo lại Order ở bước 1. Saga phải lưu **durable workflow state** và idempotency của từng step.

Phân biệt:

- Transaction retry: attempt chưa commit, làm lại bộ read/validate/write liên quan.
- Workflow retry: tiếp tục từ checkpoint đã commit, có compensation khi cần.
- Commit unknown: đối soát outcome trước khi quyết định bước sau.

Một business process nhiều service **không nằm trong một transaction NoSQL duy nhất** chỉ vì code dùng một method tên `executeWorkflow`.

## 50. Outbox và idempotent consumer

Một transaction có thể ghi:

~~~text
Order.status=CONFIRMED
OutboxEvent(type=OrderConfirmed, operationId=K)
~~~

Sau commit, worker đọc event và gọi hệ ngoài. Nếu worker crash sau khi gửi nhưng trước khi đánh dấu xử lý, event có thể được gửi lại.

Consumer cần:

- Event ID/operation ID ổn định.
- Deduplication state hoặc idempotent external API.
- Hành vi khi event out-of-order.
- Retry/backoff và dead-letter/reconciliation.
- Không đánh dấu processed trước side effect nếu điều đó làm mất event.
- Không tuyên bố exactly-once end-to-end chỉ vì outbox được commit atomically với Order.

Transaction retry có thể chạy callback nhiều lần, nhưng outbox chỉ nên **ghi effect của committed attempt**, có key chống trùng.

## 51. Đo contention và retries

Một bảng metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `transactionAttemptsPerRequest` | Một request tạo bao nhiêu attempts |
| `retryableAbortRate` | Tỷ lệ abort do conflict/transient |
| `businessRejectionRate` | Outcome do điều kiện không thỏa |
| `unknownCommitRate` | Số lần không biết commit outcome |
| `idempotencyHitRate` | Request trùng được trả outcome cũ |
| `conflictByAggregateKey` | Hot entity nào gây tranh chấp |
| `readSetSize` | Số document/predicate được đọc |
| `writeSetSize` | Số document thay đổi |
| `transactionDuration` | Thời gian transaction mở |
| `retryBackoffMs` | Thời gian chờ retry |
| `p95/p99EndToEndLatency` | UX/tail latency |
| `capacityThrottles` | Quota/throughput pressure |
| `sideEffectDuplicatePrevented` | Tín hiệu idempotency hiệu quả |
| `invariantViolationCount` | Lỗi correctness, quan trọng nhất |

Phân tách metric theo tenant, operation type, key/partition và error category. Không chỉ nhìn trung bình requests thành công: nếu bỏ mẫu timeout, số liệu có thể che sự cố retry storm.

## 52. Correlation ID qua các attempts

Một request nên có stable `operationId` nhưng mỗi attempt có `attemptNo` và tracing span riêng.

Ví dụ log an toàn:

~~~json
{
  "operationId": "checkout-K100",
  "tenantId": "tenant-17",
  "attemptNo": 3,
  "transactionId": "tx-attempt-3",
  "errorCategory": "RETRYABLE_CONFLICT",
  "readVersions": {
    "stock": 14,
    "price": 8,
    "coupon": 5
  },
  "retryDelayMs": 43
}
~~~

Tránh log card number, secrets hoặc dữ liệu cá nhân không cần thiết. Đừng dùng cùng một transaction ID cho mọi attempt mới nếu engine/driver đòi transaction ID riêng.

## 53. Kiểm thử hai request tranh một document

Bài test:

~~~text
Initial stock=1
Start T1 and T2 concurrently
Both attempt reserve one item
Assert:
  Exactly one reservation committed
  Stock never below zero
  Loser gets SOLD_OUT or bounded conflict
  No duplicate Order for same operationId
~~~

Chỉ kiểm tra “có một conflict exception” chưa đủ; phải kiểm tra **invariant cuối cùng**.

Chạy với nhiều concurrency, random scheduling và simulated delays để tăng khả năng phát hiện race.

## 54. Kiểm thử write skew

Initial:

~~~text
Doctor A onCall=true
Doctor B onCall=true
Invariant count(onCall)=at least 1
~~~

Chạy đồng thời:

- T1 cố đưa A thành off.
- T2 cố đưa B thành off.

Assert số bác sĩ đang trực luôn >=1 khi cả hai requests kết thúc, kể cả khi chúng retry.

Nếu test thất bại dù mọi transaction báo commit, cần **thiết kế lại invariant protection**, không chỉ tăng số lần retry.

## 55. Kiểm thử phantom

Cho hai request đặt cùng room/time interval. Cả hai query “chưa có booking overlap” và cố insert.

Assert:

- Không tồn tại hai booking overlap đã confirmed.
- Có unique/constraint/owner serialization thích hợp.
- Lần retry luôn kiểm tra tập mới hoặc điều kiện có thẩm quyền.
- Không có lỗi do query chỉ đọc những ID của attempt cũ.

Đây là test về **predicate-level invariant**, không chỉ CAS một booking document.

## 56. Kiểm thử response mất sau commit

Cố ý làm response bị rơi sau khi DB commit, rồi để client retry cùng idempotency key.

Assert:

- Chỉ một Order được tạo.
- Inventory chỉ bị reserve một lần.
- Chỉ một business payment intent.
- Idempotency lookup trả lại cùng Order ID.
- Outbox và consumer không tạo side effect trùng.
- Client nhận được outcome cuối hoặc trạng thái cần reconciliation.

Không kiểm thử unknown commit outcome thì một retry framework có thể trông hoàn hảo khi chỉ xét conflicts, nhưng lại nhân đôi đơn hàng ngoài production.

## 57. Fault injection và đường đọc

| Tình huống | Điều cần quan sát |
|---|---|
| Primary step-down giữa transaction | Abort/unknown commit được phân loại đúng |
| Replica lag | Attempt retry có đọc snapshot phù hợp |
| Network timeout lúc commit | Không replay side effect mù |
| Cache price stale | Total không dựa trên price không hợp lệ |
| Coupon đổi quota đồng thời | Không dùng coupon quá giới hạn |
| User role revoked | Authorization được kiểm tra theo contract |
| Hot inventory key | Retry storm có bị chặn |
| Event out-of-order | Projection không lùi sourceVersion |
| Leader failover | Session/routing và retry đúng |
| Concurrent insert cùng unique key | Trả result cũ hoặc conflict nghiệp vụ |
| Transaction callback chạy hai lần | Không có payment/email trùng |
| Deadline hết | Transaction đóng, không lặp vô hạn |

Fault injection cần chạy ở môi trường được phép, có khả năng cô lập/khôi phục. Không cố gây network partition production chỉ để thử retry.

## 58. Anti-pattern: retry write nhưng không reread

~~~java
int oldValue = repo.readBalance();
int newValue = oldValue - amount;

for (...) {
    try {
        repo.updateBalance(newValue);
        break;
    } catch (Conflict e) {
        // Không cập nhật oldValue/newValue.
    }
}
~~~

Sai ở chỗ giữ derived result từ state cũ.

Đúng hơn là đưa **read + validation + calculation** vào từng attempt và dùng conditional write hoặc transaction. Nếu logic chỉ là phép trừ số dư, có thể dùng atomic decrement có điều kiện thay vòng đọc thủ công.

## 59. Anti-pattern: retry cả callback có payment

~~~text
transactionCallback:
  read stock
  charge card
  update stock
  insert order
~~~

Nếu callback retry, payment có thể bị gọi nhiều lần.

Dùng transaction cho DB mutations và outbox để phát yêu cầu payment; hoặc dựng workflow reserve/authorize/capture với durable state, external idempotency và reconciliation.

## 60. Anti-pattern: tăng retry limit để chữa conflict vĩnh viễn

Nếu một tài nguyên đã hết hàng, version/condition sẽ liên tục fail. Retry 1000 lần chỉ tạo tải.

Đặt retry budget không thay **business logic**. Sau mỗi lượt, hãy xác định:

- Xung đột còn có thể giải quyết khi đọc state mới?
- Điều kiện đã vĩnh viễn không thỏa với request này?
- Có bị throttling/system overload không?
- Deadline và quote TTL còn không?
- Operation có thể đã commit rồi không?

Trả kết quả phù hợp, đừng che business rejection thành database exception.

## 61. Bài tập A — CAS v7 thất bại

Wallet balance=10,v7. Client muốn trừ 2. Request khác trừ 8, state thành balance=2,v8. CAS của client đầu thất bại.

**Hỏi:** có thể chỉ đổi expectedVersion thành 8 và giữ số dư đã tính là 8 không?

**Hướng giải:** không. Phải đọc balance=2,v8, sau đó quyết định trừ 2 có hợp lệ không, rồi dùng conditional update phù hợp. Nếu muốn giữ minimum balance lớn hơn 0 thì có thể phải từ chối.

## 62. Bài tập B — Giá và stock

Attempt đầu đọc stock=5, price=100.000. Transaction abort do stock conflict; giá đã tăng thành 120.000.

**Hỏi:** ngoài stock, phải đọc lại gì?

**Hướng giải:** price và mọi phụ thuộc khác của total nếu business dùng giá hiện hành. Chỉ giữ giá cũ khi có price quote/version contract hợp lệ được bảo vệ.

## 63. Bài tập C — Retry toàn transaction

MongoDB transaction callback đã đọc Product, Coupon, Stock rồi gặp retryable transaction abort.

**Hỏi:** retry một câu update Stock bên trong transaction cũ có đủ không?

**Hướng giải:** không. Khi transaction đã abort, cần transaction attempt mới, đọc lại các decision dependencies và viết lại bộ mutation. Driver helper có thể tự quản lý callback theo contract.

## 64. Bài tập D — Unknown commit

Client gửi COMMIT rồi timeout; không biết DB đã commit chưa.

**Hỏi:** có thể mở transaction mới cùng nội dung ngay không?

**Hướng giải:** không mù quáng. Retry commit/reconcile theo SDK và dùng idempotency; transaction trước có thể đã commit.

## 65. Bài tập E — Coupon usage là predicate

Attempt đầu query không có CouponUsage cho user; request khác insert usage trước khi retry.

**Hỏi:** chỉ reread Coupon document có đủ không?

**Hướng giải:** không. Cần kiểm tra lại predicate/quyền sử dụng, tốt hơn bảo vệ bằng unique/conditional usage key.

## 66. Bài tập F — Write skew bác sĩ

Hai bác sĩ cùng đang trực, mỗi transaction tắt trạng thái của một người. Không có write-write conflict.

**Hỏi:** tăng retry attempts có giải quyết được không?

**Hướng giải:** không nếu cả hai commit mà engine không phát hiện conflict. Cần thiết kế lại invariant protection hoặc isolation phù hợp.

## 67. Bài tập G — Quyền bị thu hồi

User có role APPROVER khi attempt đầu đọc, sau conflict role bị revoke.

**Hỏi:** retry có được dùng role cache cũ không?

**Hướng giải:** không khi operation đòi authorization hiện hành. Phải xác minh lại theo policy/consistency thích hợp.

## 68. Bài tập H — DynamoDB conditional failure

Stock available=0, TransactWriteItems trả condition failed.

**Hỏi:** có nên backoff và retry mãi không?

**Hướng giải:** không. Có thể là hết hàng, một business rejection, không phải transient conflict.

## 69. Bài tập I — Redis WATCH

WATCH stock, GET=3, MULTI SET=2, EXEC thất bại vì key đổi.

**Hỏi:** attempt mới làm gì?

**Hướng giải:** WATCH lại, GET giá trị mới, kiểm tra điều kiện và tính lại mutation trước EXEC mới.

## 70. Bài tập J — Outbox

Transaction callback gửi email trước commit. Lần đầu bị conflict và callback retry, email gửi hai lần.

**Hỏi:** sửa cách nào?

**Hướng giải:** không gửi email trong callback; ghi outbox trong committed transaction rồi consumer xử lý idempotently.

## 71. Bài tập K — Hot key

Một key nhận 500 concurrent writes/s, 40% transaction bị conflict, retry mỗi request 10 lần ngay.

**Hỏi:** rủi ro gì?

**Hướng giải:** retry storm làm tải và xung đột cao hơn. Dùng capped jitter, admission control, giảm scope, atomic primitive hoặc partition ownership phù hợp.

## 72. Bài tập L — Stable request ID

Client retry CreateOrder với idempotency key mới mỗi lần timeout.

**Hỏi:** key mới có chặn đơn trùng không?

**Hướng giải:** không. Cần key ổn định cho cùng business intent, cùng namespace tenant/operation.

## 73. Bài tập M — Snapshot và search index

Transaction conflict, retry đọc Order mới từ source nhưng trạng thái Product từ search index đang trễ.

**Hỏi:** có đảm bảo decision hiện hành không?

**Hướng giải:** không. Phải dùng source-of-truth và consistency scope thích hợp hoặc xác minh version/quote tại commit.

## 74. Checklist thiết kế retry transaction

1. Lỗi này là **retryable abort, business rejection, throttling hay unknown outcome**?
2. Driver có tự retry transaction body hoặc commit không?
3. Transaction trước đã chắc chắn abort chưa?
4. Read set gồm document và predicate nào?
5. Write set gồm những document nào?
6. Những dữ liệu **read-only** nào ảnh hưởng quyết định?
7. Dependency nào đã đọc ngoài transaction?
8. Retry có mở **snapshot/attempt mới** không?
9. Derived values (price, quota, tax, permission) có tính lại không?
10. Điều kiện **không tồn tại/unique** có được bảo vệ ở write-time không?
11. Isolation có ngăn write skew/phantom cho invariant này không?
12. Có thể thay transaction bằng atomic conditional update không?
13. Version/ETag có được đọc lại thay vì tự nâng không?
14. Read sau conflict có tới authoritative source đủ mới không?
15. External payment/email/queue có nằm trong callback retryable không?
16. Có stable operation ID/idempotency key không?
17. Unknown commit có đường reconcile riêng không?
18. Có backoff+jitter, deadline và retry budget không?
19. Có kiểm soát hot key/concurrency không?
20. Tenant/authorization có được xác minh đúng scope không?
21. Đã test conflict, phantom, write skew và timeout-after-commit chưa?
22. Có metric về attempts, abort, business rejection, unknown outcome và invariant violations không?

## 75. Mẫu hợp đồng retry cho một use case

~~~yaml
operation: Checkout
sourceOfTruth: OrderServiceNoSQL
requestIdentity:
  idempotencyKey: required
  scope: tenantAndOperation
transaction:
  scope:
    - inventory
    - couponUsage
    - order
    - outbox
  readDependencies:
    - inventory
    - currentPriceOrValidQuote
    - couponEligibilityAndQuota
    - customerStatus
    - idempotencyRecord
  predicates:
    - noPriorCouponUsageForCustomer
  consistency: verifyForEngineAndTopology
  onRetryableAbort: restartAndReread
  onBusinessConditionFailed: reject
  onUnknownCommit: retryCommitOrReconcile
retry:
  maxAttempts: bounded
  deadline: bounded
  backoff: exponentialWithJitter
externalEffects:
  payment: idempotentWorkflow
  email: outboxConsumer
observability:
  - retryAttempts
  - transactionConflicts
  - readDependencyVersions
  - unknownCommitResults
  - businessRejections
  - invariantViolations
tests:
  - concurrentCheckout
  - couponQuotaRace
  - writeSkewOrPredicateRace
  - lostCommitResponse
  - staleReplicaRead
~~~

Đây là YAML mô tả thiết kế, **không phải cấu hình mà một NoSQL engine tự thực thi**. Việc bảo đảm transaction, condition, error classification và retry phải dùng API chính thức của engine/SDK đang triển khai.

## 76. Kết luận

Một transaction bị xung đột không đồng nghĩa nghiệp vụ phải thất bại, nhưng cũng không có nghĩa cứ gửi lại lệnh ghi là đúng.

Phương pháp có hệ thống:

- **Phân loại lỗi:** chỉ retry khi semantics cho phép.
- **Đổi attempt:** nếu transaction abort, mở transaction/snapshot mới.
- **Đọc lại dependency closure:** document, predicate, trạng thái quyền và mọi dữ liệu mutable quyết định outcome.
- **Tính lại decision:** không giữ giá trị derived từ attempt cũ.
- **Bảo vệ invariant tại commit:** conditional write, unique constraint, transaction hoặc isolation thích hợp.
- **Phân biệt unknown commit:** không replay tác dụng phụ chưa biết outcome.
- **Giữ idempotency:** một business intent không bị thực hiện hai lần vì retry.
- **Kiểm soát contention:** backoff, deadline, metrics và thiết kế aggregate phù hợp.

> **Retry đúng không phải “thử ghi lần nữa”; retry đúng là “ra quyết định lại trên trạng thái hợp lệ mới, rồi commit với điều kiện bảo vệ tính đúng đắn”.**

Khi phạm vi dữ liệu cần đọc lại được xác định từ invariant thay vì từ exception, ứng dụng NoSQL mới xử lý được cạnh tranh đồng thời mà không vô tình tạo đơn hàng trùng, dùng coupon quá quota, cấp quyền sau khi bị thu hồi hoặc thực hiện những side effect không thể hoàn tác.

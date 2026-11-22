# Kiểm chứng tính lũy đẳng khi yêu cầu ghi bị gửi lại

Một yêu cầu ghi NoSQL không nhất thiết chỉ đến cơ sở dữ liệu một lần. Client có thể gửi lại sau timeout; HTTP gateway có thể retry; Java driver có thể thử lại một thao tác theo chính sách; queue hoặc CDC consumer có thể giao lại cùng event sau khi worker đã ghi dữ liệu nhưng chưa ACK. Điều nguy hiểm nhất không phải **hai requests giống nhau**, mà là **một hành động nghiệp vụ được áp hai lần** trong khi người dùng chỉ yêu cầu một lần.

Ví dụ, hệ thống cho thuê chỉ còn một chỗ trống:

```text
10:00:00.000  POST /reservations, operationId=RES-77, quantity=1
10:00:00.010  NoSQL commit: available 1 -> 0, reservation RES-77 created
10:00:00.015  Response 201 bị mất do đứt mạng
10:00:01.000  Client retry cùng operationId=RES-77
```

Nếu retry làm `available` giảm lần nữa hoặc tạo một reservation khác, hệ thống sai. Nếu retry tìm thấy receipt đã commit và trả đúng kết quả của thao tác cũ mà không có hiệu ứng mới, hệ thống có thể đạt **tính lũy đẳng ở tầng nghiệp vụ (business-effect idempotency)**.

Bài này là một **thực hành tổng hợp** trong chương **Database No SQL**. Bạn sẽ xây hợp đồng API, thiết kế lưu trữ receipt, viết một mô phỏng chạy được bằng **Java 17**, tạo lỗi nhân tạo ở các điểm commit/ACK, kiểm thử concurrency và replay, sau đó chuyển nguyên tắc sang **MongoDB, DynamoDB, Cassandra/ScyllaDB và Redis**. Mục tiêu không phải chỉ nói “dùng UUID để chống trùng” mà là **tạo bằng chứng** rằng khi yêu cầu được gửi lại với các lịch trình bất lợi, dữ liệu vẫn đúng.

> **Kết luận cần chứng minh bằng test:** Nhiều lần giao cùng một *logical command* được nhận dạng đúng, nhưng số **business effects** được commit cho command đó không vượt quá một; các trường hợp chưa rõ kết quả phải được tra cứu hoặc đối soát, không đoán từ timeout.

---

## 1. Kết quả học tập

Sau khi hoàn thành bài thực hành, bạn có thể:

- Phân biệt **idempotent command**, **idempotent result replay**, **deduplication**, **exactly-once delivery** và **exactly-once business effect**.
- Nhận diện các nơi request bị gửi lại: client, gateway, HTTP library, Java driver, queue, CDC, job runner và failover.
- Thiết kế **Idempotency-Key/operationId** có scope, thời hạn, fingerprint của payload và cơ chế phân biệt trùng key khác nội dung.
- Bảo đảm **receipt và mutation** nằm trong một atomicity boundary hoặc dùng protocol đối soát khi engine không hỗ trợ.
- Thử duplicate **tuần tự** và **đồng thời**, bao gồm timeout mất ACK sau commit.
- Kiểm tra chống double-decrement, double-capture, duplicate inserts, stale writes và tombstone resurrection.
- Xây test oracle theo **số effect, số receipt, invariant** thay vì chỉ HTTP status hoặc latency.
- Hiểu cách áp dụng conditional writes/transactions, Lua scripts và LWT theo đúng giới hạn từng NoSQL engine.
- Thiết kế retry budget, backoff/jitter, deadline, TTL retention và operational reconciliation.
- Lập báo cáo PASS/FAIL/INCONCLUSIVE từ evidence có provenance và mức coverage xác định.

## 2. Điều kiện để bắt đầu thực hành

Có thể hoàn thành phần Java 17 bằng:

```text
JDK 17+
Terminal có lệnh javac/java
Không cần database, Docker, Maven hay thư viện ngoài cho mô phỏng
```

Phần kiểm thử với database thực là **bài thực hành mở rộng**; nếu không có môi trường cô lập đã được phê duyệt, chỉ mô tả/prototype các thao tác theo API, không chạy fault injection làm sai dữ liệu production.

Đặt mục tiêu workload:

```text
Domain: inventory reservation for a rental listing
Tenant: T1
Listing: L-1001
Initial availability: 3
Command: Reserve quantity=1
Logical command identity: (tenantId, operationId)
Expected after one logical command: available=2, one reservation
```

Những số liệu này là fixture, không phải một cấu hình hệ thống sẵn có.

## 3. Định nghĩa tính lũy đẳng

Với một hàm chuyển trạng thái \(f\), lũy đẳng trong toán học thường viết:

\[
f(f(x))=f(x)
\]

Trong hệ phân tán, bài toán cụ thể hơn: cùng **logical operation** được vận chuyển tới service nhiều lần, nhưng **hiệu ứng nghiệp vụ** chỉ được áp một lần.

Với command \(c\), nếu các lần giao là \(d_1,\ldots,d_n\):

\[
\mathrm{AppliedBusinessEffects}(c,d_1,\ldots,d_n)\le 1
\]

Đối với command đã được ACK thành công và không bị bù trừ bởi một command nghiệp vụ khác, mong muốn:

\[
\mathrm{AppliedBusinessEffects}(c)=1
\]

Hai biểu thức khác nhau: **at-most-once effect** bảo vệ khỏi trùng, trong khi **eventual completion/liveness** bảo đảm command hợp lệ không bị bỏ quên mãi. Một hệ từ chối mọi request thì không tạo duplicate, nhưng cũng không phải dịch vụ đúng.

## 4. “Request được gửi lại” không luôn là cùng command

Có hai POST:

```http
POST /reservations
Idempotency-Key: RES-77

{"tenantId":"T1","listingId":"L-1001","quantity":1}
```

và:

```http
POST /reservations
Idempotency-Key: RES-77

{"tenantId":"T1","listingId":"L-1001","quantity":2}
```

Cùng key nhưng **payload nghiệp vụ khác nhau**. Không được trả receipt của request đầu rồi âm thầm xem request thứ hai thành công.

Hợp đồng cần:

```text
same key + same canonical business payload:
    duplicate; replay committed result or report in progress

same key + different canonical business payload:
    409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD

new key + same-looking payload:
    a distinct logical command unless business constraint says otherwise
```

Idempotency key **không tự suy ra business identity**. Nó là cách khách hàng định danh một ý định thao tác cụ thể.

## 5. Định danh command cần scope

Một định danh an toàn hơn thường có cấu trúc:

\[
K=(tenantId,operationType,idempotencyKey)
\]

hoặc hệ có thể scope theo authenticated user/account và endpoint, tùy hợp đồng.

Ví dụ:

```text
(T1, reserve, RES-77)
(T2, reserve, RES-77)
```

là hai lệnh khác nếu key được phép trùng giữa tenants. Không dùng key toàn cục không scope rồi vô tình trả response của tenant khác.

Cần kiểm:

- `tenantId` lấy từ identity/authorization đã xác minh, không tin body do client tự gửi.
- Giới hạn độ dài/charset của key.
- Entropy đủ để tránh va chạm vô ý.
- Tồn tại xuyên client retry, app restart và failover.
- Không chứa PII hoặc secrets.
- Dùng cùng key cho cùng ý định, không tạo key mới ở mỗi retry.
- Không cho gọi receipt cross-tenant để dò dữ liệu người khác.

## 6. Fingerprint của payload

Một receipt cần lưu **fingerprint** của nội dung nghiệp vụ đã chấp nhận:

```text
operationType=reserve
tenantId=T1
listingId=L-1001
quantity=1
currency=none
schemaVersion=v1
```

Có thể tính:

\[
F=\mathrm{SHA256}(\mathrm{CanonicalEncode}(\mathrm{BusinessCommand}))
\]

Khi replay:

- So operation identity.
- So fingerprint.
- Trùng → trả kết quả phù hợp contract.
- Khác → conflict, không mutate.
- Không có receipt → thử tạo command theo atomicity protocol.

**Không hash raw JSON một cách mù**: thứ tự field, whitespace, `1` so với `1.0`, null/missing, Unicode và default values có thể khác bytes nhưng cùng hoặc khác nghĩa tùy nghiệp vụ. Hợp đồng canonicalization phải có phiên bản.

## 7. Metadata nào không nên nằm trong fingerprint?

Thông thường **không** đưa vào:

```text
HTTP request timestamp
retry attempt count
traceId/correlationId
connection ID
user-agent
gateway hop
server-generated transport metadata
```

Vì những yếu tố này thay đổi giữa retries, sẽ tạo false conflict. Nhưng **phải** đưa vào các trường quyết định hiệu ứng, như target entity, amount, currency, quantity, command type, expected revision và tenant scope theo contract.

Nếu `expectedRevision` là một precondition có nghĩa nghiệp vụ, việc retry cùng command phải giữ chính precondition ban đầu, không tự đọc revision mới rồi thay đổi fingerprint để “giúp request qua”.

## 8. Quyết định response replay

Có hai thiết kế hợp lệ tùy API:

**A. Replay original outcome:**

```text
First POST commits reservation R1, returns 201 Created.
Repeat identical POST returns stored outcome 201/receipt R1.
```

**B. Return an explicit duplicate state:**

```text
First POST returns 201 Created.
Repeat returns 200 AlreadyApplied with receipt R1.
```

Về **effect**, hai cách đều có thể lũy đẳng. Về HTTP semantics, chúng khác nhau; test oracle phải dựa hợp đồng được công bố.

Một số sản phẩm lưu cả response status/body để replay chính xác. Các hệ khác lưu receipt kết quả rồi tái tạo response từ authority. Cần cân nhắc thay đổi schema/response API và retention.

## 9. Vì sao `GET`, `SET`, `INCR` có mức an toàn khác nhau?

| Command | Replay giống hệt | Điều kiện và cảnh báo |
| --- | --- | --- |
| GET/read | Thường không tạo write effect | Logging/counter side effects có thể tồn tại |
| SET field = X | Có thể idempotent về giá trị | Conditional version và side effects khác cần xem |
| UPSERT deterministic ID | Có thể không tăng số records | Có thể overwrite phiên bản mới hơn |
| INSERT unique business key | Duplicate nên bị reject/return receipt | Unique scope đúng chưa? |
| DELETE by stable key | Thường idempotent về trạng thái “không tồn tại” | Tombstone, conditional delete, trigger |
| INCR counter | **Không idempotent** khi replay | Cần receipt/dedup và atomicity |
| APPEND list/event | **Không idempotent** nếu thiếu unique event ID | Duplicate entry/sequence |
| CAS by version | Một lần commit có thể chặn retry tiếp | Cần reconcile outcome/receipt |
| MULTI-record transaction | Tùy transaction semantics | Timeout commit UNKNOWN |
| External charge/payment | Không an toàn nếu gọi lại tùy tiện | Provider idempotency/reconciliation |
| Batch | Không mặc định atomic | Có thể partial success, unprocessed subset |

Không có một `retry=true` dùng an toàn cho mọi lệnh.

## 10. Tầng retry chồng nhau

Một luồng có thể:

```text
Client retry = 3 attempts
Gateway retry = 2 attempts
Java application retry = 3 attempts
Driver retry = 2 attempts
```

Số lần thử vật lý tiềm năng có thể tăng rất lớn do tích các tầng nếu chúng đều hoạt động độc lập. Hệ còn có CDC replay riêng.

**Biện pháp:** định nghĩa retry owner/contract theo operation, tổng deadline, budget, jitter và idempotency. Mọi attempt của cùng logical command phải mang **cùng operationId**; không để mỗi tầng tự tạo command ID mới.

## 11. Timeline quan trọng nhất: commit thành công, ACK bị mất

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB
    Client->>API: POST reserve(op-77)
    API->>DB: commit stock + receipt
    DB-->>API: commit OK
    Note over API: Connection lost before response
    Client--xAPI: no ACK, timeout
    Client->>API: retry reserve(op-77)
    API->>DB: lookup receipt(op-77)
    DB-->>API: APPLIED, reservation R-77
    API-->>Client: original outcome; no new effect
```

Điều cần kiểm:

1. Commit bền vững xảy ra trước ACK loss.
2. Receipt vẫn tìm được ở nguồn có thẩm quyền.
3. Retry trả identity của **cùng reservation**, không cấp ID mới.
4. Inventory chỉ giảm **một lần**.
5. Không sinh outbox/payment side effect thêm lần hai.
6. Nếu receipt chưa thể đọc, service trả trạng thái `UNKNOWN/RETRY_LATER` theo contract thay vì tạo thao tác mới.

## 12. Phân loại kết quả sau timeout

| Trạng thái chứng cứ | Ý nghĩa | Hành động |
| --- | --- | --- |
| `APPLIED` | Có durable receipt và effect hợp lệ | Replay response, không mutate |
| `REJECTED` | Durable business rejection | Replay hoặc retry theo policy được định nghĩa |
| `NOT_APPLIED_CONFIRMED` | Authority chứng minh không commit | Có thể thực hiện lại cùng command |
| `IN_PROGRESS` | Một owner đang xử lý, outcome chưa cuối | Chờ/tra cứu bounded |
| `UNKNOWN` | Không đủ bằng chứng commit/abort | Reconcile; không nhân đôi effect |
| `CONFLICT` | Same key, khác fingerprint hoặc trạng thái không hợp lệ | Trả conflict, không mutate |
| `INCONSISTENT` | Receipt và effect trái nhau | Data incident/repair có kiểm soát |

**Client timeout tự nó chỉ là triệu chứng transport**, không phải bằng chứng `NOT_APPLIED`.

## 13. Hợp đồng API thực hành

Request minh họa:

```http
POST /api/v1/reservations
Authorization: Bearer <access-token>
Idempotency-Key: RES-77
Content-Type: application/json

{
  "listingId": "L-1001",
  "quantity": 1
}
```

Server lấy tenant từ principal đã xác thực. Khi lần đầu thành công:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/v1/reservations/R-RES-77

{
  "reservationId": "R-RES-77",
  "listingId": "L-1001",
  "quantity": 1,
  "status": "RESERVED",
  "operationId": "RES-77"
}
```

Khi retry cùng payload:

```text
Same idempotency identity
Same reservationId
Same effective stock mutation count (1)
```

Ví dụ JSON/HTTP chỉ là contract đề xuất. Không dùng literal token trong môi trường thực và không trả fingerprint/receipt của người dùng khác.

## 14. API tra cứu status độc lập

Một endpoint:

```http
GET /api/v1/operations/RES-77
```

trả trạng thái nếu người gọi có quyền:

```json
{
  "operationId": "RES-77",
  "state": "APPLIED",
  "resourceId": "R-RES-77",
  "operationType": "RESERVE"
}
```

Tác dụng:

- Reconcile sau timeout.
- Tránh retry mù.
- Hỗ trợ operator/customer support.
- Tránh trả success giả trước commit.
- Có thể xác minh receipt sau app restart.

Lưu ý endpoint status phải đọc **authority theo consistency phù hợp**; `NOT_FOUND` từ replica stale không tự chứng minh command chưa commit.

## 15. Mô hình dữ liệu nghiệp vụ

Một mô hình đơn giản:

```text
Inventory:
    tenantId
    listingId
    availableUnits
    version

Reservation:
    tenantId
    reservationId
    listingId
    quantity
    status

OperationReceipt:
    tenantId
    operationType
    operationId
    fingerprint
    state
    reservationId
    responseStatus
    responseBody or responseReference
    schemaVersion
    createdAt
    expiresAt/retention policy
```

Cần thêm các fields phù hợp khi có thanh toán, user auditing, canceled reservations hoặc transaction lineage.

Một invariant:

\[
Available = Initial - \sum_{\text{unique active reservations}}Quantity
\]

nếu nghiệp vụ thật định nghĩa inventory theo cách này và không có restock/fulfillment/expiry. Trong hệ đầy đủ, dùng **ledger có dấu, trạng thái và lifecycle** để đối soát; không áp công thức đơn giản cho mọi inventory model.

## 16. Receipt phải gắn với effect như thế nào?

Một giao dịch đúng về nguyên tắc:

```text
BEGIN atomic boundary
    assert operation key not previously applied
    assert availableUnits >= requested quantity
    reserve quantity / update version
    create reservation with stable resource identity
    insert OperationReceipt(APPLIED, fingerprint, result)
COMMIT
```

Nếu cùng một atomicity boundary được hỗ trợ, không có trạng thái bền vững:

```text
inventory decremented but receipt absent
```

hoặc:

```text
receipt APPLIED but inventory unchanged
```

Khi DB không thể atomically update những records/partitions này, **không được vẽ giả một transaction**. Cần thiết kế aggregate khác, operation ledger + reconciler, conditional per-key ownership hoặc saga với trạng thái rõ.

## 17. Vì sao check-then-write không an toàn?

Anti-pattern:

```text
if not exists(operations, op-77):
    decrement(inventory)
    insert(operations, op-77)
```

Hai workers có thể:

```text
Worker A: receipt not found
Worker B: receipt not found
Worker A: decrement
Worker B: decrement
Worker A: insert receipt
Worker B: insert receipt (duplicate rejected)
```

Dù unique index bảo vệ receipt insert cuối, inventory đã bị trừ **hai lần**. Một `GET` trước `INSERT` không thay unique/conditional write **trong atomic boundary**.

## 18. Điểm crash giữa effect và receipt

Mô hình lỗi:

```text
A. write inventory effect
B. write receipt
```

Các cửa sổ:

| Điểm crash | Trạng thái còn lại | Retry nguy hiểm gì? |
| --- | --- | --- |
| Trước A | Chưa effect/receipt | Có thể retry |
| Sau A, trước B | Effect có, receipt thiếu | Retry có thể double effect |
| Sau B | Effect+receipt có | Nếu cả hai durable thì replay |
| B trước A | Receipt có, effect thiếu | Retry có thể bỏ effect mãi |
| Sau commit trước ACK | Effect+receipt có, caller UNKNOWN | Retry cần lookup |

Atomic transaction xử lý một số cửa sổ; ngoài transaction phải có state machine/reconciliation với proof thích hợp.

## 19. Race của hai request cùng operationId

Timeline:

```text
Client A sends op-77.
Client B sends op-77 almost simultaneously.

A and B both pass local "not seen" cache.
Both reach different API instances.
```

Một `ConcurrentHashMap` trong **mỗi JVM** không đủ: hai instances không chia sẻ bộ nhớ. Tương tự một Redis cache chứa key dedup nhưng inventory ở MongoDB chưa đồng bộ atomically cũng không bảo đảm nhất quán xuyên hai hệ.

Chỉ cơ chế được enforce tại **nguồn thẩm quyền hoặc transaction/coordination boundary hợp lệ** mới có thể quyết định một winner và một duplicate/replay một cách chắc chắn.

## 20. Dedupe ở queue/CDC khác dedupe ở API

Một luồng:

```text
POST reserve -> database commit -> outbox E1
Outbox publisher -> broker
Consumer -> search projection
```

Ngay cả khi API đã chống duplicate POST, outbox publisher có thể giao E1 hai lần. Cần **một deduplication scope riêng cho consumer**:

\[
ConsumerEffectIdentity=(consumerId,eventId)
\]

Nếu hai consumers xử lý hai loại projection, một event có thể được áp **một lần trên mỗi projection consumer**, không nhất thiết chỉ một lần toàn hệ.

Không dùng operationId API làm eventId một cách máy móc khi một command sinh nhiều distinct events. Thiết kế event identities theo business/event semantics.

## 21. Test oracle: không chỉ nhìn response

Bộ oracle thực hành gồm:

```text
A. One logical operation identity.
B. One business reservation resource identity.
C. One APPLIED receipt with matching fingerprint.
D. Inventory delta applied exactly once.
E. No stale/out-of-order reapplication.
F. Correct tenant authorization.
G. Any emitted event has unique effect in each consumer.
H. Confirmed response matches durable receipt.
```

Nếu chỉ assert:

```java
assert response.statusCode() == 201;
```

có thể vẫn tồn tại hai reservations ở DB. Một test integration cần đọc authoritative state/ledger sau khi workers đã hội tụ.

## 22. Bảng test fixtures

| Fixture | Initial available | Request | Expected unique effects |
| --- | ---: | --- | ---: |
| Normal | 3 | `op-A`, qty 1 | 1; available=2 |
| Repeat | 3 | `op-A` lặp 10 lần | 1; available=2 |
| Concurrent same key | 3 | 50 workers cùng `op-A` | 1; available=2 |
| Same key different body | 3 | `op-A qty1`, rồi `op-A qty2` | 1; conflict second |
| Different keys | 3 | `op-A`,`op-B` qty1 | 2; available=1 |
| Exceed stock | 1 | `op-A qty2` | 0; business rejection |
| Last unit race | 1 | `op-A`, `op-B` qty1 | 1 winner; available=0 |
| Commit then ACK lost | 1 | `op-A` then retry | 1; same reservation |
| App process restart | 3 | Commit then new app instance retry | 1 if DB receipt durable |
| Cross-tenant key reuse | T1/T2 1 | both key `op-A` | one effect per scoped tenant |

Tất cả expected results chỉ đúng khi inventory model là mô hình số lượng đơn giản của bài.

## 23. Test cần xem cả số hiệu ứng và số attempts

Ví dụ:

```text
Logical command IDs = 1
HTTP attempts = 10
DB command attempts = 13
Confirmed reservations = 1
Inventory delta = -1
Receipts APPLIED for identity = 1
```

Kết quả có thể PASS. Nếu HTTP attempts = 1 nhưng reservations = 2 do worker duplication, FAIL.

Định nghĩa:

\[
RetryAmplification=\frac{PhysicalAttempts}{UniqueLogicalOperations}
\]

\[
EffectMultiplicity(c)=\#\mathrm{committedEffectsFor}(c)
\]

Kiểm `EffectMultiplicity(c) <= 1` trên mọi command hợp lệ đã xác minh. Không dùng số lượng `HTTP 200` làm số hiệu ứng.

## 24. Nhận diện duplicate và conflict bằng fingerprint

Ví dụ:

```text
K=(T1,RESERVE,RES-77)
F1=hash("L1,quantity=1")

Retry1: same K,F1 -> REPLAY.
Retry2: same K,F1 -> REPLAY.
Retry3: same K,F2 -> CONFLICT.
```

Nếu service **thay key thành một ID mới khi conflict** để “giúp client”, sẽ phá lời hứa idempotency. Client phải tạo operationId khác **chỉ khi thực sự có ý định nghiệp vụ mới**, không vì timeout.

## 25. Những lệnh `SET` cũng có thể gây side effect

Giả sử:

```text
SET order.status = PAID
```

lặp lại vẫn là `PAID`, nhưng mỗi lần có thể:

- Sinh outbox `OrderPaid`.
- Gửi webhook/email.
- Tăng `paidCount`.
- Ghi audit event.
- Update timestamp gây event replay.

Vì vậy kiểm:

```text
same final field value
```

là chưa đủ. Cần kiểm các **downstream business effects** và có operation receipts/event IDs cho các nhánh có ý nghĩa.

## 26. Tính lũy đẳng và tính giao hoán không giống nhau

Hai commands khác nhau:

```text
Set status=PAID.
Set status=CANCELED.
```

có thể mỗi command riêng lũy đẳng nhưng **thứ tự** quyết định trạng thái cuối.

Định nghĩa:

- **Idempotency:** replay cùng command không đổi effect sau lần đầu.
- **Commutativity:** đổi thứ tự hai commands không đổi kết quả.
- **Ordering:** một stream/transaction giữ thứ tự theo scope.
- **Concurrency control:** ngăn updates vi phạm revision/invariant.

Không có tính lũy đẳng nào tự bảo đảm chống **out-of-order updates** từ hai operation IDs khác nhau.

## 27. Version guard cho command khác nhau

Nếu:

```text
op-A at rev7: set status=PAID
op-B at rev8: set status=REFUNDED
```

một event cũ `op-A` đến muộn sau `op-B` không được ghi đè trạng thái thành `PAID`.

Cần:

- Revision/version monotonic trên authority.
- CAS/conditional update.
- Per-key event order hoặc gap detection.
- Unique operation receipts.
- Business state transition validation.
- Conflict policy.

Lưu ý replay `op-A` đã apply phải được xem duplicate **trước khi** cố áp update. Nếu receipt đã hết hạn thì cần nguồn revision/tombstone/business ledger khác để chống stale replay.

## 28. TTL của receipt là một quyết định correctness

Nếu receipt hết hạn sau 15 phút nhưng retry hoặc queue replay có thể xảy ra sau 24 giờ:

```text
t=0: op-A committed.
t=15m: dedup marker expired.
t=2h: old op-A redelivered.
```

Service có thể không còn chứng cứ và áp lại effect.

Cần xác định:

\[
Retention_{\mathrm{receipt}}\ge
\max(
ClientRetryWindow,
QueueRedeliveryWindow,
CDCReplayWindow,
RollbackRecoveryWindow,
ExternalCallbackWindow
)
\]

với headroom/chính sách data retention phù hợp. Đây là **quy tắc thiết kế bảo thủ**, không đồng nghĩa mọi receipt phải sống vĩnh viễn.

Nếu privacy/retention yêu cầu xóa sớm hơn, cần một cơ chế bảo vệ khác (ledger minimum data, one-way generation, authoritative business ID uniqueness) được phê duyệt.

## 29. Những business rejections có được “ghi nhớ” không?

Ví dụ:

```text
op-A requests qty=3 when stock=1 -> INSUFFICIENT_STOCK.
10 minutes later stock=10.
Same op-A retried.
```

Hai hợp đồng có thể khác:

**Hợp đồng 1 — Replay terminal rejection:** cùng key luôn trả `INSUFFICIENT_STOCK`; người dùng phải tạo **một logical intent mới** với key khác để thử mua lại. Dễ giải thích và test.

**Hợp đồng 2 — Retry certain pre-commit rejections:** cùng key có thể được thử lại nếu trước đó chưa có committed business effect; cần định nghĩa chính xác loại lỗi nào không được coi terminal, và race handling.

Không lấy việc “không lưu receipt cho failure” làm mặc định chung; có thể tạo hành vi thay đổi khó hiểu và race.

Trong bài thực hành Java dưới đây, chọn **hợp đồng 1** để trạng thái terminal phản hồi ổn định.

## 30. Chỉ ghi receipt khi đã có authority decision

Một `OperationReceipt` lý tưởng phân biệt:

```text
RECEIVED
IN_PROGRESS
APPLIED
REJECTED
UNKNOWN/NEEDS_RECONCILIATION
```

Nếu `IN_PROGRESS` được lưu độc lập trước khi mutation:

- Có lease/owner/fencing.
- Có thời hạn xử lý.
- Sau crash có reconciler.
- Không để `IN_PROGRESS` treo mãi.
- Không cho owner cũ commit muộn sau handover.
- Nếu mutation đã commit nhưng status chưa đổi, phải tra business receipt/ledger.

Cách ít phức tạp hơn khi DB hỗ trợ: **atomic transaction ghi effect và final receipt**, tránh cần trạng thái trung gian durable cho một command ngắn.

## 31. Liệu mỗi request nên tạo reservationId ngẫu nhiên?

Một anti-pattern:

```text
Request op-A attempt1 -> reservationId=random R1.
Request op-A attempt2 -> reservationId=random R2.
```

Nếu effect path thiếu receipt và unique business key, hai attempts có thể tạo hai resources.

Có thể dùng:
- `reservationId` deterministic từ authenticated scope và operationId (khi không lộ secret/PII).
- Hoặc resource ID do DB cấp **một lần**, lưu trong receipt atomically.
- Lookup prior receipt trước khi cấp mới.
- Unique constraint theo operation identity.

Không thay toàn bộ model ID bằng hash operationId nếu có rủi ro collision, cross-tenant inference hoặc yêu cầu opaque IDs; mục tiêu là **giữ identity của cùng logical result**.

## 32. Contract về response khi đang có request đồng thời

Hai requests giống nhau tới cùng lúc:

```text
A wins and commits.
B sees the command in progress.
```

Các phản hồi có thể hợp lệ tùy API:

```text
A -> 201 APPLIED
B -> wait bounded then replay 201
```

hoặc:

```text
B -> 202/409/425-like in-progress status
     with Retry-After and operation status URL
```

Không dùng một status code cố định cho mọi API; hãy định nghĩa rõ retryability và liệu caller có được tiếp tục cùng key. Nếu B bị `409` do fingerprint mismatch, đó là lỗi terminal; nếu là concurrency in-progress, response phải giúp caller tra tiếp, không nhầm với payload conflict.

## 33. Authority read sau timeout

Một read từ cache/replica chưa theo kịp có thể trả:

```text
Operation receipt not found.
```

Nhưng authority đã commit. Nếu app suy `NOT_APPLIED` và ghi lại, duplicate effect có thể xảy ra.

Yêu cầu:

- Receipt lookup qua nguồn đáng tin với consistency được xác nhận.
- Unique/conditional write **enforce tại DB** chứ không chỉ tin readback.
- Không dùng eventual GSI/cache làm proof của absence.
- Khi authority không thể truy cập, giữ `UNKNOWN` hoặc trả trạng thái chờ.
- Test failover/replica lag chính xác tại cửa sổ commit.

## 34. Retry và exponential backoff

Một chiến lược bounded:

\[
D_n=\min(D_{\max},D_{\mathrm{base}}\times 2^n)
\]

Sau đó chọn **jitter** trong phạm vi. Ví dụ:

```text
base 100ms, cap 2s
attempt 0: random delay 0..100ms
attempt 1: random delay 0..200ms
attempt 2: random delay 0..400ms
...
```

Cần:
- Tổng deadline.
- Max attempts.
- Rate limit.
- `Retry-After` nếu service quy định.
- Retry only transient classes.
- Không retry validation/payload-conflict.
- Tra operation receipt khi commit outcome ambiguous.
- Không có nested retry storm.
- Cùng operationId/fingerprint ở mọi attempts.

Backoff giảm tải, **không thay idempotency**.

## 35. Các phép kiểm nghiệm thu ban đầu

Đối với một `operationId`, kiểm:

```text
N identical deliveries >= 2
N unique committed reservations = 1
N unique APPLIED receipts = 1
Inventory actual = Inventory initial - qty
No duplicate outbox/business effects
Responses reference same resource
Payload conflict rejected with no new mutation
```

Với hai `operationId` khác nhau và available=1:

```text
At most one reservation succeeds.
At most one unit consumed.
Other command gets legitimate rejection.
```

Một hệ đạt duplicate suppression nhưng vẫn oversell khi **hai logical commands khác nhau** cần được phân loại rõ: **idempotency có thể PASS, inventory concurrency correctness FAIL**. Bài tổng hợp kiểm cả hai để không đánh đồng.
## 36. Thực hành Java 17 — bộ mô phỏng lũy đẳng chạy độc lập

Ta xây một service dùng **bộ nhớ trong một JVM** với ba điều kiện:

1. `reserve` chạy trong một `synchronized` atomic region của demo.
2. Mỗi logical command có một `OperationReceipt` terminal gắn với fingerprint.
3. Thay đổi tồn kho và ghi receipt xảy ra trong cùng critical section của demo.

Mục đích là quan sát **hành vi chính xác** trước khi thay storage bằng NoSQL thật. Không coi `synchronized` là giải pháp distributed correctness cho các Java service instances khác nhau.

### 36.1. Các lớp và phương thức

Lưu nội dung sau vào `IdempotentReservationLab.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class IdempotentReservationLab {

    record StockKey(String tenantId, String listingId) {}

    record OperationKey(String tenantId, String operationId) {}

    record Command(
            String tenantId,
            String operationId,
            String listingId,
            int quantity) {}

    record Receipt(
            String state,
            int statusCode,
            String fingerprint,
            String reservationId,
            int quantity) {}

    static final class ReservationService {
        private final Map<StockKey, Integer> stock =
                new HashMap<>();
        private final Map<OperationKey, Receipt> receipts =
                new HashMap<>();

        synchronized void seed(
                String tenantId, String listingId, int available) {
            if (available < 0) {
                throw new IllegalArgumentException("Negative stock");
            }
            stock.put(new StockKey(tenantId, listingId), available);
        }

        synchronized Receipt reserve(Command command) {
            validate(command);

            OperationKey operationKey = new OperationKey(
                command.tenantId(), command.operationId());

            String fingerprint = fingerprint(command);
            Receipt existing = receipts.get(operationKey);

            if (existing != null) {
                if (!existing.fingerprint().equals(fingerprint)) {
                    return new Receipt(
                        "IDEMPOTENCY_CONFLICT",
                        409, fingerprint, null, 0);
                }

                // Returning a terminal result; no new mutation.
                return existing;
            }

            StockKey stockKey = new StockKey(
                command.tenantId(), command.listingId());

            int available = stock.getOrDefault(stockKey, 0);

            if (available < command.quantity()) {
                // Demo contract: business rejection is terminal.
                Receipt rejected = new Receipt(
                    "REJECTED_NO_STOCK",
                    409, fingerprint, null, 0);

                receipts.put(operationKey, rejected);
                return rejected;
            }

            // The mutation and receipt are in one synchronized
            // region ONLY within this demo JVM.
            stock.put(
                stockKey, available - command.quantity());

            String resourceId = "R-"
                + command.tenantId()
                + "-" + command.operationId();

            Receipt applied = new Receipt(
                "APPLIED", 201, fingerprint,
                resourceId, command.quantity());

            receipts.put(operationKey, applied);
            return applied;
        }

        synchronized int available(
                String tenantId, String listingId) {
            return stock.getOrDefault(
                new StockKey(tenantId, listingId), 0);
        }

        synchronized int appliedReceiptCount() {
            int count = 0;
            for (Receipt receipt : receipts.values()) {
                if ("APPLIED".equals(receipt.state())) {
                    count++;
                }
            }
            return count;
        }

        synchronized int totalReceiptCount() {
            return receipts.size();
        }

        synchronized Receipt receipt(
                String tenantId, String operationId) {
            return receipts.get(
                new OperationKey(tenantId, operationId));
        }
    }

    static void validate(Command c) {
        if (c == null
                || c.tenantId() == null
                || c.operationId() == null
                || c.listingId() == null
                || c.tenantId().isBlank()
                || c.operationId().isBlank()
                || c.listingId().isBlank()
                || c.quantity() <= 0) {

            throw new IllegalArgumentException("Invalid command");
        }
    }

    static void writeUtf8(
            DataOutputStream out, String value)
            throws IOException {

        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String fingerprint(Command c) {
        try {
            ByteArrayOutputStream buffer =
                    new ByteArrayOutputStream();

            DataOutputStream out =
                    new DataOutputStream(buffer);

            out.writeInt(1);  // Fingerprint schema version.
            writeUtf8(out, "RESERVE");
            writeUtf8(out, c.tenantId());
            writeUtf8(out, c.listingId());
            out.writeInt(c.quantity());
            out.flush();

            MessageDigest digest =
                MessageDigest.getInstance("SHA-256");

            return java.util.HexFormat.of().formatHex(
                digest.digest(buffer.toByteArray()));

        } catch (IOException | NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    static Receipt send(
            ReservationService service,
            Command command,
            boolean loseAckAfterCommit) throws IOException {

        Receipt result = service.reserve(command);

        if (loseAckAfterCommit) {
            // Simulates ACK loss only AFTER the service committed.
            throw new IOException("SIMULATED_ACK_LOST_AFTER_COMMIT");
        }

        return result;
    }

    static List<Receipt> sendConcurrent(
            ReservationService service,
            List<Command> commands) throws Exception {

        int count = commands.size();
        ExecutorService workers =
            Executors.newFixedThreadPool(count);

        CountDownLatch ready = new CountDownLatch(count);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<Receipt>> futures = new ArrayList<>();

            for (Command command : commands) {
                futures.add(workers.submit(() -> {
                    ready.countDown();
                    start.await();
                    return service.reserve(command);
                }));
            }

            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Workers did not become ready");
            }

            start.countDown();

            List<Receipt> results = new ArrayList<>();
            for (Future<Receipt> future : futures) {
                results.add(future.get());
            }
            return results;

        } finally {
            start.countDown();
            workers.shutdownNow();
        }
    }

    static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        ReservationService service =
            new ReservationService();

        service.seed("T1", "L1", 3);

        Command opA = new Command(
            "T1", "OP-A", "L1", 1);

        // 1. Effect commits, response is lost.
        try {
            send(service, opA, true);
            throw new AssertionError("Expected ACK loss");
        } catch (IOException expected) {
            System.out.println("ACK_LOST_AFTER_COMMIT");
        }

        // 2. Same operation is retried after timeout.
        Receipt retryA = send(service, opA, false);

        require("APPLIED".equals(retryA.state()),
            "Retry must return APPLIED receipt");
        require(service.available("T1", "L1") == 2,
            "One command must decrement once");
        require(service.appliedReceiptCount() == 1,
            "One receipt for first logical command");

        System.out.println(
            "ACK loss retry: PASS, reservation="
                + retryA.reservationId());

        // 3. Sixteen simultaneous copies of one command.
        Command opB = new Command(
            "T1", "OP-B", "L1", 1);

        List<Command> repeated =
            new ArrayList<>();

        for (int i = 0; i < 16; i++) {
            repeated.add(opB);
        }

        List<Receipt> concurrent =
            sendConcurrent(service, repeated);

        for (Receipt receipt : concurrent) {
            require("APPLIED".equals(receipt.state()),
                "Duplicate must replay committed receipt");
            require(receipt.reservationId().equals(
                    "R-T1-OP-B"),
                "All duplicates must reference one resource");
        }

        require(service.available("T1", "L1") == 1,
            "Concurrent duplicates must decrement once");

        require(service.appliedReceiptCount() == 2,
            "Only two unique operations applied");

        System.out.println("16 concurrent duplicates: PASS");

        // 4. Reusing a key with changed payload is a conflict.
        Receipt conflict = service.reserve(
            new Command("T1", "OP-B", "L1", 2));

        require("IDEMPOTENCY_CONFLICT".equals(
                    conflict.state()),
            "Fingerprint mismatch must fail");

        require(service.available("T1", "L1") == 1,
            "Conflict must not alter inventory");

        System.out.println("Payload fingerprint conflict: PASS");

        // 5. Two DIFFERENT commands race for the last unit.
        Command opC = new Command(
            "T1", "OP-C", "L1", 1);
        Command opD = new Command(
            "T1", "OP-D", "L1", 1);

        List<Receipt> competing =
            sendConcurrent(service, List.of(opC, opD));

        long winners = competing.stream()
            .filter(r -> "APPLIED".equals(r.state()))
            .count();

        long rejected = competing.stream()
            .filter(r -> "REJECTED_NO_STOCK".equals(r.state()))
            .count();

        require(winners == 1 && rejected == 1,
            "One winner, one business rejection");

        require(service.available("T1", "L1") == 0,
            "No overselling of last unit");

        require(service.appliedReceiptCount() == 3,
            "Exactly three reservations were accepted");

        require(service.totalReceiptCount() == 4,
            "Four unique operation receipts, including rejection");

        System.out.println("Different-key last-unit race: PASS");
        System.out.println("Available=" +
            service.available("T1", "L1"));
        System.out.println("AppliedReceipts=" +
            service.appliedReceiptCount());
        System.out.println("TotalReceipts=" +
            service.totalReceiptCount());
    }
}
```

### 36.2. Chạy chương trình

```bash
javac IdempotentReservationLab.java
java IdempotentReservationLab
```

Output minh họa:

```text
ACK_LOST_AFTER_COMMIT
ACK loss retry: PASS, reservation=R-T1-OP-A
16 concurrent duplicates: PASS
Payload fingerprint conflict: PASS
Different-key last-unit race: PASS
Available=0
AppliedReceipts=3
TotalReceipts=4
```

Điểm cốt lõi:

- `OP-A` được **commit nhưng mất ACK**; retry không tạo effect thứ hai.
- Mười sáu lần gửi đồng thời `OP-B` cùng thấy một resource.
- Dùng lại `OP-B` với quantity khác bị **CONFLICT**.
- `OP-C` và `OP-D` là **hai intents khác nhau**: chỉ một được phép lấy chỗ cuối cùng.
- Các receipts có tính bền vững **chỉ trong bộ nhớ của JVM đang chạy**, không phải receipt production.

### 36.3. Vì sao demo dùng `synchronized`?

Trong demo, cùng một lock bảo vệ:

```text
Check receipt existence
Check available stock
Decrement stock
Insert final receipt
```

Điều đó tạo một atomic critical section **chỉ cho một JVM**. Nó đơn giản và phù hợp để thấy expected behavior trước khi gắn database.

Nó **không** giải quyết:

- Hai service instances/pods cùng thao tác.
- Process crash làm mất cả stock và receipts trong memory.
- Network partition và primary failover.
- DB commit outcome UNKNOWN.
- Server/driver retry độc lập.
- Transaction qua nhiều storage engines.
- Outbox/CDC/external payment effects.
- Receipt TTL/retention.
- Data backup/restore.
- Tenant authorization thực sự.

Khi chuyển sang NoSQL, phải thay **critical section in-memory** bằng transaction/conditional update/ledger protocol có phạm vi đúng ở **database authority**, không giữ thêm `synchronized` rồi tưởng đã xong.

## 37. Bài lab A: gửi lại tuần tự 100 lần

Từ chương trình Java trên, mở rộng:

```java
for (int i = 0; i < 100; i++) {
    Receipt result = service.reserve(opA);
    require("APPLIED".equals(result.state()),
        "Original result must be replayed");
}
```

Chạy sau khi OP-A đã commit và kiểm:

```text
available không giảm thêm
appliedReceiptCount không tăng
reservationId vẫn R-T1-OP-A
fingerprint không đổi
```

**Bằng chứng cần lưu:** số lần gửi, số logical operation IDs, trạng thái stock trước/sau, số receipts/effects.

Không chỉ in 100 dòng `HTTP 201`, vì đó là **transport outcomes**, không chứng minh dữ liệu không đổi.

## 38. Bài lab B: 100 clients cùng gửi một command

Thay 16 bằng 100 trong fixture, nhưng:

- Không tạo quá nhiều threads không giới hạn ở môi trường thật.
- Giữ start barrier để tăng cơ hội requests đến gần nhau.
- Thu results và receipt identities.
- Kiểm chỉ một mutation.
- Kiểm không có `ConcurrentModificationException`/data race trong demo.
- Khi chuyển sang DB thật, dùng nhiều service instances và connection pools.

Test concurrency phải có **evidence ở authority**, không dựa vào việc local cache của một JVM trả cùng response.

## 39. Bài lab C: đổi payload nhưng giữ key

Thử:

```text
K=(T1,RESERVE,OP-B), listingId=L1, qty=1 -> APPLIED
K=(T1,RESERVE,OP-B), listingId=L2, qty=1 -> CONFLICT
K=(T1,RESERVE,OP-B), listingId=L1, qty=2 -> CONFLICT
```

Những thay đổi có ý nghĩa nghiệp vụ này cần fingerprint khác. Không tự cập nhật stored fingerprint để request mới “được chấp nhận”.

Thử thêm:

```text
HTTP JSON key order changes.
Whitespace changes.
TraceId changes.
```

Nếu canonical business payload không đổi, fingerprint phải giữ nguyên theo contract, khác raw JSON bytes không được tạo conflict giả.

## 40. Bài lab D: phản hồi bị mất ở nhiều điểm

Fault locations:

```text
F0: before server accepts command
F1: after validation, before DB transaction
F2: during transaction, commit unknown
F3: after confirmed DB commit, before API response
F4: after API sends response, before client receives
F5: after event delivered to consumer, before consumer ACK
```

Đối với mỗi điểm:

1. Nêu trạng thái command có thể đã commit chưa.
2. Xác định source evidence.
3. Retry dùng operationId nào?
4. Reconcile ở đâu?
5. Có thể có duplicate effect không?
6. Có thể bỏ mất effect không?
7. Hợp đồng response/error cần như thế nào?

**F3/F4** là trường hợp quan trọng: client timeout nhưng mutation thực tế đã commit. **F2** có thể UNKNOWN ngay cả với server, tùy engine/client connection state.

## 41. Bài lab E: so sánh thiết kế sai và đúng

**Thiết kế sai:**

```text
Read dedup key from cache.
If not present:
    decrement inventory counter.
    write dedup key to cache.
```

Inject crash:

```text
decrement succeeded
worker crashes
dedup key not written
retry decrements again
```

Bằng chứng:

```text
one logical key
two decrements
one/few cache markers
```

**Thiết kế đúng có điều kiện:**

```text
Atomic authority boundary:
    commit inventory mutation + unique receipt
```

hoặc một protocol có thể đối soát nếu atomicity không khả thi. So kết quả dưới cùng fault.

Không sửa anti-pattern bằng cách tăng TTL/cache replication đơn thuần; **cửa sổ ghi effect rồi mới ghi marker vẫn tồn tại**.

## 42. Bài lab F: phản hồi từ replica stale

Tạo:

```text
Authority receipt: APPLIED
Replica/cache receipt: NOT_FOUND
Client retries same command
```

Kỳ vọng:

- Không có second effect vì authority-side unique/conditional rule.
- API không tự kết luận NOT_APPLIED từ stale NOT_FOUND.
- Có thể fallback authoritative lookup hoặc trả UNKNOWN.
- Eventual view hội tụ sau replication lag.
- Trace ghi read path và observed checkpoint.

Phân biệt:

```text
Duplicate found in stale cache?
```

với:

```text
Effect uniquely enforced at authoritative write point?
```

Chỉ cái thứ hai bảo vệ race khi cache miss hoặc replica lag.

## 43. Bài lab G: thử lại sau khi server restart

Trong mô phỏng memory, restart chương trình sẽ **mất receipts**. Đây là giới hạn có chủ ý.

Trong DB integration lab:

1. Gửi command và xác nhận durable receipt.
2. Kill/restart **application process**, không xóa DB.
3. Retry cùng key/payload qua instance mới.
4. Kiểm same result, no second effect.
5. Nếu DB failover, kiểm storage durability/consistency contract.
6. Nếu restore từ backup cũ, đánh giá receipt retention và log replay coverage.

Điều cần chứng minh là **idempotency sống lâu hơn tiến trình app**, không phải một static map sống trong cùng JVM.

## 44. Bài lab H: kiểm idempotency khi có giới hạn tài nguyên

Giả sử service đang quá tải:

```text
request times out at gateway
database command may still be running
retry arrives while first request is in flight
```

Kỳ vọng:
- Same key được serialize hoặc atomic de-dupe.
- Không queue vô hạn trên một key.
- Không tạo hàng chục DB commands cạnh tranh.
- Có bounded wait/status response.
- `Retry-After`/backoff theo contract.
- Không gây timeout storm cho hot partition.
- Goodput là **unique confirmed reservations/s**, không phải DB attempts/s.

Idempotency đảm bảo safety không tự đảm bảo latency, nhưng cần kiểm cả liveness và backpressure.

## 45. Bài lab I: zero stock và terminal rejection

Thiết lập:

```text
available=1
op-A requests quantity=2 -> REJECTED_NO_STOCK
```

Gửi lại cùng key dù một command khác đã restock, theo hợp đồng bài học:

```text
op-A still -> REJECTED_NO_STOCK
new op-B -> can reserve after restock, if policy allows
```

Một business rejection lưu trong receipt không phải lỗi transport. Một client không nên liên tục retry một payload đã bị từ chối nghiệp vụ như retry `503`.

Nếu sản phẩm chọn hợp đồng khác cho transient precondition failure, hãy đổi **spec + test oracle** rõ ràng, không để mỗi deployment xử lý khác.

## 46. Bài lab J: receipt retention hết hạn

Mô phỏng bằng cách xóa receipt `op-A` rồi giao lại command cũ.

Những câu hỏi:

- Có sinh duplicate effect không?
- Entity/business ID unique có chặn không?
- Revision guard có chặn không?
- API còn status lookup không?
- Queue/CDC có khả năng replay từ lâu hơn TTL không?
- Khi compliance yêu cầu xóa receipts, cơ chế chống duplicate còn lại là gì?

Trong production, không xóa receipts để thử trên dữ liệu thật. Dùng test database hoặc giả lập TTL với operation IDs tổng hợp. Mục đích là chứng minh **retention window lớn hơn exposure window**, không chỉ rằng TTL “đang hoạt động”.

## 47. Bài lab K: phiên bản canonicalization thay đổi

Giả sử API v1:

```json
{"listingId":"L1","quantity":1}
```

API v2:

```json
{"quantity":1,"listingId":"L1","clientNote":null}
```

Nếu `clientNote` không quyết định hiệu ứng, hai payload có thể cùng logical meaning. Nhưng nếu `clientNote` là trường được audit và có ý nghĩa, bỏ nó khỏi fingerprint có thể sai.

Cần:

- Versioned fingerprint schema.
- Không tính trace/retry metadata.
- Phân biệt null/missing/default theo contract.
- Giữ old canonicalizer để kiểm old receipts trong retention window hoặc có migration.
- Test Unicode, number precision và nested arrays.
- Không tự đổi digest algorithm mà không lưu version.

Nếu không thể so fingerprints across versions, trả `INCONCLUSIVE/CONFLICT` có mô tả rõ, không áp lại effect vô điều kiện.

## 48. Bài lab L: cùng command nhưng hai tầng phát event

Mô hình:

```text
HTTP client retries command.
DB commits once.
Outbox publisher delivers event twice.
Projection consumer retries event.
```

Oracle:

```text
unique source business effects = 1
outbox logical event IDs for this transition = 1
delivery attempts may be >=2
unique consumer-projection effect = 1
```

Nếu consumer có nhiều projections, đếm mỗi `(consumerId,eventId)` đúng scope. Kiểm:

- Applied-event ledger.
- Source revision.
- Target revision.
- Delete propagation.
- Crash after target effect before broker ACK.
- Checkpoint gaps.
- Replay after restore.

**Chống duplicate POST** không chứng minh **chống duplicate CDC effects**; chúng là hai boundary.

## 49. Bài lab M: request khác nhau tranh chỗ cuối

```text
Available = 1.
op-A -> reserve qty 1.
op-B -> reserve qty 1.
```

Cả hai có idempotency keys **khác nhau**, vì đó là hai yêu cầu thực sự khác nhau. Chỉ một phải thành công nếu chính sách không cho overbooking.

Cần:
- CAS/conditional update.
- Unique reservation identity.
- Monotonic version.
- Business rejection ổn định.
- Không dùng same-key dedup thay cho check stock.

Một hệ chống duplicate tốt nhưng chấp nhận cả hai intents trên cùng một unit vẫn **không đúng toàn bài**. Điều này giúp phân biệt **per-operation idempotency** và **cross-operation concurrency safety**.

## 50. Bài lab N: delete/cancel request được gửi lại

Lệnh:

```text
Cancel reservation R1, operationId=C-77
```

Thử:
- Gửi lại nhiều lần.
- Cancel khi R1 đã canceled.
- Cancel và payment capture race.
- Cancel retry sau TTL.
- Late `RESERVED` event đến sau `CANCELED`.
- Một lệnh khác `RESUME` hoặc `REBOOK` có revision mới.

Bất biến:
- Một cancellation chỉ release inventory **một lần**.
- Không release hai lần làm available tăng sai.
- Old reservation event không tái tạo active booking.
- Refund/fee chỉ áp theo business receipt, không tùy tiện retry.

`DELETE` raw có thể idempotent về “record không tồn tại”, nhưng **cancel business workflow có side effects** cần các receipts riêng.

## 51. Bài lab O: payment capture được gửi lại

Một payment request:

```text
Capture payment order O1, providerKey=PAY-O1-CAPTURE1
```

Có thể xảy ra:
- DB records intent.
- PSP captures tiền.
- HTTP response lost.
- App retries.
- PSP returns same capture receipt if provider idempotency contract supports.
- Internal ledger needs consistent receipt.

Bất biến mẫu:
- Một logical capture có một provider reference.
- Captured amount không vượt rule được phê duyệt.
- Refund có unique operation IDs.
- Không suy payment failed từ timeout.
- Reconcile PSP ledger khi local database thiếu receipt.

**Không thử capture tiền thật** trong bài thực hành. Dùng sandbox provider hoặc fake deterministic adapter, và không giả mọi PSP có cùng retention/capture idempotency semantics.

## 52. Bài lab P: batch writes có partial outcome

Một batch:

```text
op-A, op-B, op-C, op-D
```

DB trả:

```text
processed: A, B
unprocessed: C, D
```

Client phải:
- Giữ stable IDs.
- Retry chính C,D theo API semantics.
- Không tự tái phát A,B nếu chúng non-idempotent.
- Nếu retry cả batch, dedup per-operation tại authority.
- Đối soát logical effects và receipts.
- Không coi HTTP request thành công là toàn batch complete.

Một batch **không mặc định atomic** hoặc exactly-once, kể cả có tùy chọn ordered execution.

## 53. Bài lab Q: schema evolution và phản hồi cũ

Một receipt lưu:

```text
responseSchemaVersion=v1
responseBody={ "reservationId": "R1" }
```

Sau deploy API v2 yêu cầu thêm fields.

Khi replay cùng operationId từ client v1/v2, phải chọn:
- Replay nguyên status/body v1;
- Convert receipt result sang v2 theo mapping không mất nghĩa;
- Trả status resource theo version negotiated.

Không được tái tạo một reservation mới chỉ vì response schema đã đổi. Cần test across deployments và rollback app versions.

## 54. Bài lab R: multi-tenant authorization

Cho:

```text
T1 operationId=RES-77
T2 operationId=RES-77
```

Kiểm:
- Có thể là hai operations hợp lệ theo scope.
- T1 không thể tra receipt/response của T2.
- `tenantId` được bind từ trusted identity.
- Same key khác tenant không va chạm nếu contract cho phép.
- Receipt lookup không tiết lộ existence của tenant khác.
- Logs/traces không in raw payment/user PII.
- Quota/rate limit theo tenant.

Security violation dù không duplicate stock vẫn là **FAIL tổng thể**.

## 55. Bài lab S: two-phase receipt bị treo

Nếu kiến trúc dùng `IN_PROGRESS`:

```text
op-A receipt state=IN_PROGRESS, owner=worker-1, leaseEpoch=5
worker-1 crashes.
worker-2 takes over epoch=6.
```

Kiểm:
- Worker-1 không thể commit sau khi worker-2 được cấp quyền.
- Worker-2 tra source business effect trước khi retry.
- `IN_PROGRESS` không treo mãi.
- Nếu effect đã commit, status được cập nhật APPLIED đúng.
- Nếu commit UNKNOWN, không tự áp effect mới.
- Lease không thay database-side fencing.
- Có reconciler với metrics oldest pending.

Mô hình này phức tạp hơn transaction commit cuối và chỉ nên chọn khi nghiệp vụ cần workflow dài.
## 56. Đưa mô phỏng Java sang NoSQL thật

Mô phỏng dùng một lock trong một JVM. Đối với hệ phân tán thật, cần xác định:

```text
Where is the authoritative write boundary?
What operation enforces uniqueness under concurrency?
Can receipt and business effect commit atomically?
How is an unknown commit reconciled?
Can the same command be replayed across regions/restarts?
What if a service or database fails over mid-write?
```

Không dùng kết quả demo `synchronized` để khẳng định MongoDB, DynamoDB, Cassandra hoặc Redis tự có đúng behavior đó. Với mỗi engine, phải thiết kế data model và fault tests theo semantics cụ thể.

## 57. MongoDB: một thiết kế transaction với receipt

Mô hình collections:

```text
inventory:
    _id = tenantId + ":" + listingId
    available
    revision

reservations:
    _id = stable reservationId
    tenantId
    listingId
    quantity
    status
    operationId

operations:
    _id = scoped operation identity
    payloadFingerprint
    state
    reservationId
    responseStatus
    responseSchemaVersion
    createdAt

outbox:
    _id = stable business eventId
    type
    aggregateId
    revision
```

Cần unique indexes thực sự tương ứng business identity (ví dụ unique `(tenantId,operationType,operationId)` nếu không mã hóa identity vào `_id`).

Trong deployment/phiên bản MongoDB hỗ trợ transaction phù hợp với collections/shards liên quan, một thao tác khái niệm:

```text
start transaction with supported session/read/write concerns
    prior = find operation receipt by scoped key

    if prior exists:
        if fingerprint mismatch:
            return conflict after transaction-safe handling
        return prior receipt

    update inventory
        where available >= quantity
        and owner/tenant conditions
        increment revision/decrement available

    if no inventory record matched:
        insert terminal REJECTED receipt under chosen contract
    else:
        insert reservation with stable ID
        insert final APPLIED receipt
        insert corresponding outbox event

commit transaction
```

**Các chi tiết phải kiểm khi triển khai:**

- Read/write concerns và transaction retry behavior theo version/driver.
- Unique index scope, collation/partial index semantics.
- Retry nguyên transaction khi transient conflict, không đổi operationId.
- Nếu `commitTransaction` trả kết quả **UNKNOWN**, không tự chạy lại external effect; dùng driver commit-retry semantics và authoritative receipt reconciliation.
- Unique key collision có thể là duplicate command hoặc conflict khác payload; tra receipt.
- Không dùng eventual cache/secondary read `NOT_FOUND` làm proof không tồn tại.
- Transaction có giới hạn thời gian, tài nguyên và phạm vi; không nhét external PSP call vào DB transaction rồi nghĩ cả hai cùng atomic.

Nếu transaction không bao phủ đúng các data items trong workload thực, cần thay model hoặc dùng durable saga/reconciliation.

## 58. MongoDB: ví dụ pseudo Java

Đây là **mã định hướng**, không phải source copy-paste chạy được vì APIs/exception handling cụ thể phụ thuộc MongoDB Java Driver:

```java
// PSEUDOCODE: implement with correct driver and error labels.
Result reserveWithTransaction(Command c) {
    String key = scopedOperationKey(c);
    String fingerprint = canonicalFingerprint(c);

    return mongoTransaction(session -> {
        var prior = operations.findByKey(session, key);

        if (prior != null) {
            return compareAndReplay(prior, fingerprint);
        }

        var inventoryResult = inventory.conditionalDecrement(
            session, c.tenantId(), c.listingId(), c.quantity());

        if (!inventoryResult.applied()) {
            operations.insertTerminalReceipt(
                session, key, fingerprint, "NO_STOCK");
            return rejectedResult();
        }

        String reservationId = stableId(c);
        reservations.insert(session, reservationId, c);
        operations.insertAppliedReceipt(
            session, key, fingerprint, reservationId);
        outbox.insert(session,
            eventId(c), "ReservationCreated", reservationId);

        return appliedResult(reservationId);
    });
}
```

Điểm cần lập test:
- Hai requests cùng key tới hai Java instances.
- Hai requests khác key tranh một unit.
- DB primary election sau business writes trước commit response.
- Transaction conflict/dedup unique constraint.
- Commit UNKNOWN.
- Outbox delivery duplicate.
- Retry sau app restart.
- Replay khi schema khác version.

Nếu chỉ có unique receipt nhưng inventory decrement nằm ngoài transaction, test sẽ phát hiện race chưa được giải quyết.

## 59. MongoDB: retryable write khác business idempotency

Một số thao tác MongoDB và driver có hỗ trợ **retryable writes**, nhưng chúng có phạm vi cụ thể: commands/conditions, session/transaction info và deployment support.

Tính năng đó không tự ngăn:
- Client tạo operationId mới rồi gọi lại.
- App gọi hai commands khác nhau cho một business intent.
- External payment capture bị gọi hai lần.
- Outbox consumer áp duplicate effect.
- Application transaction được chạy lại với side effect ngoài DB.
- Receipt retention ngắn hơn replay window.

Vì vậy cần business operationId, unique receipt/conditional guard, commit UNKNOWN reconciliation, và invariant/ledger tests. Driver retry là **một lớp kỹ thuật**, không thay hợp đồng nghiệp vụ end-to-end.

## 60. DynamoDB: conditional item writes và transaction

Một model:

```text
PK=TENANT#T1, SK=INVENTORY#L1
    availableUnits=3, revision=10

PK=TENANT#T1, SK=OPERATION#RESERVE#OP-A
    fingerprint=..., state=APPLIED, reservationId=...

PK=TENANT#T1, SK=RESERVATION#R-T1-OP-A
    quantity=1, status=RESERVED
```

Có thể thiết kế `TransactWriteItems` để:
1. `Put` operation receipt với điều kiện key chưa tồn tại.
2. `Update` inventory có điều kiện `availableUnits >= quantity`.
3. `Put` reservation với điều kiện chưa tồn tại.

**Pseudocode transaction actions:**

```text
TransactWriteItems:
  Put receipt:
      condition: attribute_not_exists(PK) and
                 attribute_not_exists(SK)

  Update inventory:
      availableUnits = availableUnits - :qty
      condition: availableUnits >= :qty

  Put reservation:
      condition: attribute_not_exists(PK) and
                 attribute_not_exists(SK)
```

Cần hiểu chính xác API constraints và expressions cho từng item/key. Nếu tất cả trong transaction được hỗ trợ và request commit, receipt và effect cùng tồn tại.

Khi một action fail do duplicate receipt:
- Không giả đó luôn là hết hàng.
- Tra receipt theo authenticated scope.
- So fingerprint.
- Replay APPLIED/REJECTED outcome hoặc trả CONFLICT.
- Không dùng eventual GSI để chứng minh absence.
- Nếu transaction outcome UNKNOWN, ưu tiên receipt lookup/reconciliation, không phát key mới.

## 61. DynamoDB: terminal failure receipt cần thiết kế riêng

Nếu transaction trên thất bại vì `availableUnits < quantity`, **toàn transaction không commit**. Do đó `Put receipt(REJECTED)` trong transaction ấy cũng không xảy ra.

Nếu bài thực hành yêu cầu:
```text
Same operationId that got NO_STOCK must keep returning NO_STOCK
```
phải thiết kế thêm nhánh persist terminal rejection có concurrency/race guard hoặc chuyển sang state-machine/aggregate khác.

Các lựa chọn:
- Chỉ cache terminal validation failures, còn `NO_STOCK` là retryable business condition theo contract mới (bài test phải đổi).
- Dùng durable rejection receipt khi không có stock, có condition bảo vệ và reconciliation giữa các đường.
- Serialise per-key reservation decision trong authoritative aggregate/protocol.

**Không tuyên bố một transaction abort vừa ghi được receipt**. Đây là chỗ test `same key after restock` phát hiện mâu thuẫn giữa spec và implementation.

## 62. DynamoDB: service token không thay receipt dài hạn

DynamoDB có cơ chế idempotency cho một số transaction APIs với **request token và cửa sổ thời gian/điều kiện cụ thể**. Cần tra tài liệu API đúng phiên bản, thời hạn và hành vi khi thay payload.

Không dựa duy nhất vào token dịch vụ để bảo vệ:
- Callback thanh toán sau nhiều giờ/ngày.
- CDC replay lịch sử.
- Restore từ snapshot cũ.
- Client retries vượt token window.
- Một business intent đi qua nhiều API requests hoặc external systems.

Với business command dài hạn, cần **stable operation receipt/ledger theo retention được thiết kế**. SDK token là lớp bảo vệ bổ sung, không phải thay thế tất cả.

## 63. DynamoDB: batch API và idempotent writes

`BatchWriteItem` không phải `TransactWriteItems`:
- Có thể trả `UnprocessedItems`.
- Không có conditional write trên từng item theo cùng semantics với API đơn lẻ.
- Có giới hạn actions/bytes riêng.
- Retry subset phải an toàn.
- Overwrite có thể xóa version mới nếu app thiết kế sai.

Vì vậy không dùng `BatchWriteItem` đơn thuần để triển khai một reservation cần conditional decrement + receipt atomic.

## 64. Cassandra/ScyllaDB: per-partition LWT và giới hạn

Cassandra/ScyllaDB có các primitive CQL conditional writes/LWT theo phạm vi được engine/version hỗ trợ. Chúng có thể giúp một writer thắng trên **một logical key/partition được thiết kế phù hợp**.

Nhưng:
- `INSERT receipt IF NOT EXISTS` trên partition P1.
- `UPDATE inventory ...` trên partition P2.

không tự trở thành một atomic multi-partition business transaction chỉ vì cả hai lệnh dùng LWT hoặc nằm trong `BATCH`.

Các lựa chọn:
- Đặt invariant trong **cùng authoritative aggregate/partition** có CAS/LWT phù hợp.
- Đưa decision vào một service/DB hỗ trợ atomic conditional operation đúng scope, còn Cassandra lưu ledger/projection.
- Dùng idempotent operation ledger + saga/reconciliation.
- Giới hạn conflict domain/key cardinality.

Không khuyên lưu unbounded `appliedOperationIds` trong một partition mãi mãi vì sẽ tạo large partition và CAS cost; cần tính retention.

## 65. Cassandra/ScyllaDB: ledger chưa chắc bảo đảm inventory

Layout minh họa:

```text
reservations_by_operation:
    partition key (tenantId, operationId)
    listingId, quantity, state, version

availability_by_listing:
    partition key (tenantId, listingId)
    dateBucket, state, version
```

Một reservation ID unique có thể được claim bằng conditional write, nhưng điều đó **không đủ** để bảo đảm một chỗ trống khi hai operation IDs khác nhau cùng tranh.

Cần **single authoritative availability decision**, ví dụ per listing/date slot owner, conditional aggregate hoặc ledger với strong decision protocol phù hợp.

Nếu availability là eventual projection, test phải phân biệt:
- Authoritative acceptance.
- Read model lag.
- Replayed events.
- Projection convergence.
- Business invariant at authority.

Không dùng increment/decrement counter non-idempotent khi thiếu dedup/receipt. Nếu counter update đã commit nhưng marker chưa commit, retry có thể áp lần hai.

## 66. Cassandra/ScyllaDB: timestamps, TTL và stale replay

Một update cũ được replay với **timestamp mới** có thể ghi đè value mới hơn theo conflict resolution của engine.

Cần:
- Source revision/operationId.
- Fencing/conditional acceptance.
- Không lấy thời gian consumer replay làm business commit order.
- Tombstone/TTL retention đủ replay window.
- Test network partition/repair.
- Reconcile ledger/unique receipts.

LWT timeout có thể là `UNKNOWN`: không tự phát thêm effect với key mới. Read consistency và repair topology ảnh hưởng khả năng quan sát receipt.

## 67. Redis: Lua script atomically dedup + mutation

Trong một Redis instance, Lua script có thể kiểm receipt và decrement counter **nguyên tử ở phạm vi Redis execution**. Trong Redis Cluster, keys trong script phải thỏa **hash-slot constraints**.

Ví dụ keys cùng hash tag:

```text
KEYS[1] = "{listing:T1:L1}:available"
KEYS[2] = "{listing:T1:L1}:receipt:OP-A"
```

Arguments:

```text
ARGV[1] = payload fingerprint
ARGV[2] = quantity
ARGV[3] = stable reservationId
ARGV[4] = retention milliseconds
```

Script mô hình hóa:

```lua
local oldFingerprint =
    redis.call("HGET", KEYS[2], "fingerprint")

if oldFingerprint then
    if oldFingerprint ~= ARGV[1] then
        return {"CONFLICT"}
    end

    local prior = redis.call("HGET", KEYS[2], "result")
    return {"REPLAY", prior}
end

local quantity = tonumber(ARGV[2])
local available = tonumber(
    redis.call("GET", KEYS[1]) or "0"
)

if quantity == nil or quantity <= 0 then
    return {"INVALID"}
end

if available < quantity then
    redis.call(
        "HSET", KEYS[2],
        "fingerprint", ARGV[1],
        "result", "REJECTED_NO_STOCK"
    )
    redis.call("PEXPIRE", KEYS[2], ARGV[4])
    return {"REJECTED_NO_STOCK"}
end

redis.call("DECRBY", KEYS[1], quantity)

redis.call(
    "HSET", KEYS[2],
    "fingerprint", ARGV[1],
    "result", ARGV[3]
)
redis.call("PEXPIRE", KEYS[2], ARGV[4])

return {"APPLIED", ARGV[3]}
```

**Đây là script minh họa**, phải review input/type/expiry và deployment-specific behavior trước khi dùng. Đặc biệt:
- Các keys phải cùng Redis Cluster slot.
- Validate types và arguments **trước mọi mutating command**; một Redis Lua script bị lỗi runtime không tự rollback tất cả writes đã chạy trước lỗi.
- `PEXPIRE` phải có value hợp lệ, receipt TTL đủ replay window.
- Script dài có thể block event loop.
- Redis memory eviction có thể làm mất receipt.

Atomic execution không tự bảo đảm **durability across failover** theo RDB/AOF/replication settings và không atomically commit với một database/payment provider khác.

## 68. Redis: cache marker không đủ khi effect ở hệ khác

Nếu Redis chỉ chứa dedup key, inventory authority nằm ở MongoDB:

```text
Redis key OP-A exists.
MongoDB inventory decremented.
```

Khi Redis evicts/hết TTL key, retry có thể decrement database lần nữa. Hai effects không cùng atomic durable boundary nên không phải chống duplicate chắc chắn.

Nếu Redis là authority duy nhất, cần persistence/replication/failover durability tests và memory policies không xóa receipts sớm. Nếu Redis là cache, dùng nó để **giảm duplicate load** nhưng vẫn cần unique/conditional guard ở authoritative database.

## 69. Bảng lựa chọn primitive theo phạm vi

| Hệ | Primitive hữu ích | Ranh giới nguy hiểm | Evidence |
| --- | --- | --- | --- |
| MongoDB | Unique index + transaction/conditional update | Commit UNKNOWN, external PSP | No duplicate effect qua primary election |
| DynamoDB | ConditionExpression, TransactWriteItems | Eventual GSI, abort/rejection semantics, token TTL | One stock decision, receipt, no double effect |
| Cassandra/ScyllaDB | Per-partition LWT/CAS, ledger | Cross-partition invariant, counters/tombstones | Unique command + stock invariant |
| Redis | Lua/functions atomic execution | Failover persistence, eviction, Cluster slots | Replay, durability, no duplicate |
| Queue/CDC | Event ID, marker, checkpoint | At-least-once + crash before ACK | One consumer effect |
| Payment provider | Provider idempotency key + receipt | Provider window, external settlement | One capture per logical intent |

Không có primitive nào tự tạo **exactly-once delivery end-to-end qua mọi mạng và mọi storage**. Mục tiêu khả thi là **at-least-once retry + durable idempotent business effect + reconciliation**.

## 70. Cross-region active-active: hai writers có thể cùng nhận command

Giả sử hai Regions:

```text
Region A receives OP-A.
Region B receives OP-A at the same moment.
```

Nếu dedup chỉ local, cả hai có thể cùng thấy `NOT_FOUND` và commit.

Cần:
- Single authority per key/tenant/epoch.
- Global coordination/conditional write có semantics phù hợp.
- Routing/fencing.
- Conflict resolution giữ business invariant.
- Receipt replication với consistency đủ mạnh.
- Bounded failover và reconciliation.

Không dựa vào eventual replication của receipt IDs để bảo đảm **một winner toàn cầu** nếu cả hai Regions được phép ghi độc lập.

## 71. Client offline queue và replay sau nhiều ngày

App mobile có thể lưu:

```text
operationId=OP-42
intent=reserve listing L1
queuedAt=day 1
deliveredAt=day 3
```

Cần:
- Policy command expiry.
- Stable key, không tạo key mới khi retry.
- Current stock/revision check.
- Auth renewal/user consent.
- Receipt retention đủ.
- Response `EXPIRED_COMMAND` khi cần.
- Không dùng marker TTL 15 phút cho replay sau hai ngày.

## 72. TraceId không phải idempotency key

Nếu gateway tạo một ID mới mỗi HTTP retry:

```text
Frontend operationId: OP-1
Gateway attemptId 1: GW-11
Gateway attemptId 2: GW-22
```

Backend phải dedup theo `OP-1`, không phải `GW-11/22`.

- OperationId gắn logical intent.
- AttemptId gắn physical request.
- TraceId gắn observability/correlation.
- IDs có scopes/retention khác nhau.

Cần propagate đúng và chống client input giả tenant.

## 73. Replay response cũ khi resource đã có trạng thái mới

```text
OP-CREATE committed -> R1 RESERVED
OP-CANCEL committed -> R1 CANCELED
Client retries OP-CREATE
```

Nếu API replay original outcome, có thể trả receipt tạo R1 thành công dù trạng thái hiện tại đã `CANCELED`; resource GET sẽ phản ánh state hiện tại.

Nếu API trả current state, có thể báo `CANCELED`. Cả hai không tạo effect mới nhưng **response semantics khác**. Chọn rõ hợp đồng, không để retry `CREATE` ghi đè cancellation mới hơn.

## 74. Fingerprint collisions, encoding và privacy

SHA-256 của canonical command có khả năng trùng tình cờ cực thấp, nhưng:
- Phải có versioned encoding.
- Tránh delimiter ambiguity.
- Không hash transport fields.
- Không coi digest là xác thực danh tính.
- Hash dữ liệu miền nhỏ có thể bị đoán.
- Giữ fingerprint/receipt ở nơi có quyền truy cập phù hợp.
- Không tiết lộ raw payload của người dùng khác qua conflict response.

## 75. Idempotency không chữa mọi lỗi

Một hệ có thể luôn trả cùng receipt nhưng:
- Receipt sai quantity.
- Stock âm do hai operationIds khác nhau.
- Outbox event bị bỏ.
- Refund tạo hai lần với keys khác.
- Stale event ghi đè state mới.
- Tenant authorization sai.
- Receipt mất sau failover.
- TTL quá ngắn.

Vì vậy nghiệm thu phải gồm idempotency, business invariants, durability, authorization, projection, recovery và load.

## 76. Kết hợp với optimistic concurrency control

Lệnh:

```text
operationId=OP-9
expectedRevision=17
newStatus=CONFIRMED
```

Lần đầu commit rev18 nhưng ACK mất. Retry vẫn có expectedRevision=17, CAS riêng lẻ sẽ fail nếu không tra prior receipt.

Logic phải:
1. Dedupe theo operationId.
2. Nếu prior APPLIED, replay rev18.
3. Nếu chưa có, kiểm precondition.
4. Commit business effect + receipt atomically.
5. Không tự tăng expectedRevision trong retry.

**CAS failure ở retry không đồng nghĩa command ban đầu FAILED**.

## 77. Downstream event redelivery

Event:

```json
{
  "eventId": "EVENT-001",
  "type": "ReservationCreated",
  "reservationId": "R-OP-A",
  "sourceRevision": 11
}
```

Projection consumer nhận hai lần. Nếu chỉ dùng `INCR reservationCount`, sẽ sai. Cần:
- Consumer-scoped applied eventId.
- Atomic target effect + marker hoặc reconciler.
- Monotonic source revision.
- Checkpoint after durable effect.
- Gap/out-of-order handling.
- Tombstone/rebuild.

Đo **effect multiplicity** chứ không chỉ delivery count.

## 78. Snapshot/restore có thể mất receipts đã commit

```text
T0 snapshot.
T1 OP-A committed, receipt APPLIED.
T2 crash.
T3 restore only snapshot T0.
T4 client retries OP-A.
```

Restored DB có thể thiếu receipt T1. Nếu PSP đã capture, retry có thể trùng.

Cần PITR/CDC replay, đối soát external receipts, recovery cut/RPO rõ và quarantine UNKNOWN commands. Một snapshot hợp lệ về bytes không chứng minh hệ sau restore chống duplicate an toàn.

## 79. Receipt retention và quyền riêng tư

Receipt chứa tenant/user IDs, payload digest, business ID hoặc payment reference. Cần:
- Phân loại dữ liệu.
- Retention hợp lệ.
- Quyền scoped access.
- Không log raw PII/tokens.
- Backup restore policy.
- Data-erasure lifecycle.
- Bảo vệ anti-replay sau khi phải xóa receipts bằng cơ chế thay thế.

Không lưu toàn bộ request body vô hạn chỉ để chống retry.

## 80. At-most-once chưa đủ: cần liveness

Hệ luôn trả `IN_PROGRESS` sẽ không tạo duplicate nhưng không hoàn thành nghiệp vụ.

Kiểm:
- Command hợp lệ đạt APPLIED/REJECTED terminal.
- Pending có owner/lease/reconciler.
- Có deadline/status API.
- Oldest unresolved age và alert.
- Không giữ lock vô hạn.
- Có backpressure/rate limiting.

At-most-once effect và eventual resolution là **hai gates độc lập**.

## 81. Ma trận lỗi theo thời điểm commit

| Fault | Có thể commit? | Chứng cứ | Hành động |
| --- | --- | --- | --- |
| Validation reject trước DB | Không nếu không có effect | Validation outcome | Không retry unchanged |
| Connection refused trước gửi | Thường chưa gửi, nhưng cần xác nhận boundary | Transport/authority | Same key retry |
| Timeout server đang chạy | Có | Receipt/log | Reconcile |
| Primary election sau commit | Có | Durable receipt | Lookup |
| DB commit nhưng API ACK lost | Có, thực tế APPLIED | Receipt | Replay |
| Consumer crash trước effect | Chưa ở target | Applied ledger | Retry same event |
| Consumer crash sau effect trước ACK | Có | Target marker | Dedupe |
| Marker-only commit | Effect có thể thiếu | Business state | Incident |
| Effect-only commit | Receipt có thể thiếu | Ledger/versions | Incident |
| Retry sau TTL | Đã commit trong quá khứ | Business ID/ledger | Không blind apply |
| Restore cũ | External effect có thể tồn tại | PITR/provider | Reconcile |
| Concurrent writes in two Regions | Hai commits có thể xảy ra | Global owner | Fence |

Không coi timeout/exception class tự nó là bằng chứng non-commit.

## 82. Metrics cho việc chứng minh idempotency

```text
logical_commands_received_total
physical_write_attempts_total
idempotency_receipt_created_total
idempotency_replay_total
idempotency_payload_conflict_total
operation_unknown_total
operation_unknown_age_seconds
duplicate_business_effect_confirmed_total
inventory_invariant_violation_total
cdc_redelivery_total
receipt_without_effect_total
effect_without_receipt_total
```

Đừng tạo metric label cho mỗi raw operationId (cardinality/PII). Aggregate theo operation class, endpoint, tenant cohort, Region và outcome; dùng scoped trace khi điều tra.

## 83. Goodput không phải số DB attempts

Ví dụ:

```text
1000 logical commands/s
3000 physical attempts/s
950 confirmed unique effects/s
30 business rejections/s
20 unresolved commands/s
```

\[
Goodput=\frac{\mathrm{ConfirmedCorrectUniqueEffects}}{\Delta t}
\]

Ở đây goodput là 950 effects/s nếu receipts đã được xác minh, không phải 3000. Đo time-to-terminal-receipt, retry amplification, DB load, p95/p99, reconciliation lag và duplicate violations.

## 84. HTTP response của duplicate/in-progress/unknown

| Trường hợp | Phản hồi ví dụ | Client |
| --- | --- | --- |
| New committed | 201/200 + receipt | Lưu result |
| Exact duplicate | Replay 201/200 | Không tạo intent mới |
| Same key different payload | 409 conflict | Dừng, sửa payload/key cho intent khác |
| In progress | 202 + status URL/Retry-After | Poll bounded |
| Authority unavailable/UNKNOWN | 503/202 theo contract | Giữ key, reconcile |
| Business rejection | 409/422 theo contract | Không retry transient mù |
| Invalid key/body | 400/422 | Không retry unchanged |
| Unauthorized | 401/403 | Không lộ receipt |

Status code cụ thể tùy API; quan trọng không ACK thành công trước durability contract.

## 85. Retry storm do nhiều tầng

```text
client retries × gateway retries × service retries × driver retries
```

Cần retry owner, per-command deadline, max attempts, exponential backoff/jitter, circuit breaker/bulkhead, rate budget, `Retry-After`, và receipt lookup trước expensive mutation. Idempotency giảm sai dữ liệu nhưng không tự giảm duplicate load.

## 86. Key reuse sau retention

Operation key `OP-1` đã dùng tháng trước, receipt hết hạn, giờ client dùng lại cho intent mới; hệ có thể hoặc đánh nhầm duplicate, hoặc áp lại retry cũ.

Giữ high-entropy keys, scope, creation epoch/business deadlines, ID uniqueness, replay window và retention contract rõ. Không dùng counter reset sau app reinstall mà thiếu namespace.

## 87. Đổi phiên bản API/codec

Một deploy có thể đổi field defaults, money units, canonicalizer, response schema hoặc TTL. Cần test:

```text
v1 request commits
v2 handles retry of same logical command
v2 does not create second effect
v1 still reads receipt after rollback if required
```

Không mutate lại chỉ vì không hiểu receipt schema cũ; đó là compatibility issue.
## 88. Bộ ma trận kiểm thử lũy đẳng

Mỗi trường hợp bên dưới cần ghi:
- `logicalOperationId` và các request/attempt IDs.
- Initial authoritative state.
- Injection point/timeline.
- Final authoritative state.
- Durable operation receipts.
- Business effects và downstream effects.
- Expected result theo contract.
- `PASS/FAIL/INCONCLUSIVE`.

Không phải mọi trường hợp đều cần thực hiện bằng fault injection trên production. Dùng test cluster cô lập, synthetic keys và phạm vi được phê duyệt.

| Mã | Kịch bản | Kết quả bắt buộc |
| --- | --- | --- |
| T01 | Một reserve hợp lệ | Một effect, một receipt |
| T02 | Cùng request gửi 2 lần tuần tự | Same resource, one effect |
| T03 | Cùng request gửi 100 lần | Effect multiplicity = 1 |
| T04 | 16 clients cùng key | At most one committed effect |
| T05 | 100 clients cùng key qua nhiều pods | Distributed unique guard đạt |
| T06 | Cùng key, quantity đổi | Fingerprint conflict, no effect |
| T07 | Cùng key, listing đổi | Conflict |
| T08 | JSON field order đổi | Canonical equivalent nếu business contract cho |
| T09 | Whitespace/traceId đổi | Không tạo false conflict |
| T10 | Null vs missing có nghĩa khác | Fingerprint phân biệt |
| T11 | Unicode equivalent theo canonical schema | Stable fingerprint |
| T12 | Money decimal/scale khác | Không làm sai amount semantics |
| T13 | Duplicate key ở hai tenants | Scope không lẫn |
| T14 | Unauthorized receipt lookup | Không lộ data |
| T15 | Timeout trước server nhận | Retry same key an toàn |
| T16 | Timeout sau DB commit | Receipt replay |
| T17 | Lost ACK trước HTTP client nhận | One effect |
| T18 | Timeout commit UNKNOWN | Không suy failed; reconcile |
| T19 | Primary failover sau commit | Acknowledged effect preserved theo durability |
| T20 | App restart rồi retry | Durable receipt vẫn có |
| T21 | Multiple app replicas, local cache miss | DB authority guard vẫn có |
| T22 | Stale replica receipt NOT_FOUND | Không double effect |
| T23 | Same key đang IN_PROGRESS | Bounded wait/status, no double commit |
| T24 | Worker chết sau marker, trước effect | Incident/recover without lost effect |
| T25 | Worker chết sau effect, trước marker | No duplicate after replay |
| T26 | Durable marker và effect atomic | No inconsistent half-commit |
| T27 | Receipt expired sớm | Safety gate FAIL |
| T28 | Replay sau expected retention | Proper expired-command/business guard |
| T29 | Key reuse trong window | Conflict/replay as contract |
| T30 | Same key rejection, restock later | Contract ổn định |
| T31 | Two distinct keys tranh chỗ cuối | One winner, no oversell |
| T32 | Multiple keys quantity > remaining | No negative stock |
| T33 | Concurrent CAS retries | Correct version and receipts |
| T34 | New command after cancel | Correct state machine |
| T35 | Duplicate cancel | Inventory released once |
| T36 | Late create event after cancel | No resurrection |
| T37 | Duplicate outbox publication | One downstream effect |
| T38 | Consumer crash before ACK | Idempotent replay |
| T39 | Consumer marker without effect | Detected |
| T40 | Consumer effect without marker | Detected/reconciled |
| T41 | CDC replay with gap | Not false PASS |
| T42 | Out-of-order different operations | Revision guard |
| T43 | Partial batch success | Only unresolved items retried |
| T44 | Retry storm/hot key | Bounded attempts, invariants preserved |
| T45 | HTTP 200 before durability ACK | Rejected design |
| T46 | Database restore before receipt commit | Recover/reconcile external effects |
| T47 | Multi-Region dual authority | No duplicate commit or explicit conflict protocol |
| T48 | Provider payment capture ACK lost | Unique provider receipt |
| T49 | API v1 receipt replay under v2 | No second business effect |
| T50 | Security/retention deletion | No unauthorized receipt exposure |
| T51 | Receipt matches but amount/inventory wrong | Business invariant FAIL |
| T52 | Fast duplicate responses but stuck pending ops | Liveness FAIL |
| T53 | Multiple request IDs, one logical ID | Goodput correct, attempts separate |
| T54 | High retries under throttling | Backoff/jitter and bounded budgets |
| T55 | Duplicate in Redis Cluster across slots | Slot/atomicity constraints enforced |
| T56 | MongoDB transaction commit uncertainty | Commit-retry/lookup preserves effect |
| T57 | DynamoDB transaction conditional abort | Correct absence/rejection semantics |
| T58 | Cassandra counter increment redelivered | No double contribution |
| T59 | Redis marker evicted after effect | Critical cross-store dedup test fails |
| T60 | Burst after Region failover | Ownership/fencing + receipt proof |

Một test suite tốt có **negative tests**: nó phải phát hiện lỗi của một implementation cố tình thiếu guard. Nếu chỉ chạy happy path và 20 lần gửi lại tuần tự trong cùng JVM, bằng chứng chưa đủ.

## 89. Tiêu chí nghiệm thu (acceptance criteria)

| Mã | Điều kiện | Evidence |
| --- | --- | --- |
| AC-01 | Logical command identity có scope rõ | API spec/keys |
| AC-02 | Tenant lấy từ authenticated identity | Auth tests |
| AC-03 | Key không bị thay giữa retries | Traces/headers |
| AC-04 | Key uniqueness/collision policy rõ | Contract |
| AC-05 | Canonical fingerprint có version | Schema/spec |
| AC-06 | Same key + different payload bị từ chối | Negative test |
| AC-07 | Same key + same payload không tạo effect mới | Receipt + state diff |
| AC-08 | Duplicate requests tuần tự đạt | Integration history |
| AC-09 | Duplicate requests đồng thời nhiều instances đạt | Concurrent integration |
| AC-10 | Different keys bảo vệ stock invariant | CAS/concurrency |
| AC-11 | Receipt lưu đủ resource/result identity | Stored receipt |
| AC-12 | Receipt và effect cùng atomic boundary hoặc protocol chứng minh tương đương | Transaction/design |
| AC-13 | Không có effect without receipt ngoài expected recoverable state | Reconciliation |
| AC-14 | Không có receipt APPLIED without effect | Invariant report |
| AC-15 | Commit UNKNOWN được phân loại | Receipt lookup |
| AC-16 | ACK lost after commit không tạo duplicate | Fault injection |
| AC-17 | Failover giữ durability contract | Recovery test |
| AC-18 | Receipt lookup không dựa vào stale absence | Read consistency test |
| AC-19 | Retry strategy có owner/deadline/budget | Config/load report |
| AC-20 | Retry không dùng operationId mới | Attempt correlation |
| AC-21 | Business rejections có contract terminal/retryable rõ | API docs/tests |
| AC-22 | IN_PROGRESS có resolution/liveness | Recovery job |
| AC-23 | Receipt TTL đủ retry/replay window | Retention analysis |
| AC-24 | Old events và tombstones không resurrect dữ liệu | Revision tests |
| AC-25 | Outbox/CDC consumers idempotent | Delivery/effect proof |
| AC-26 | Checkpoint sau target effect durable | Crash tests |
| AC-27 | Batch partial outcomes không được bỏ qua | Per-item reports |
| AC-28 | Payment/external effects dùng provider receipts | PSP reconciliation |
| AC-29 | Database engine-specific limitations được ghi rõ | Architecture record |
| AC-30 | Multi-Region owner/fencing thực sự enforce | Two-writer tests |
| AC-31 | API versions có compatible receipt replay | Version tests |
| AC-32 | Access control không tiết lộ receipt khác tenant | Negative auth |
| AC-33 | Không log payload nhạy cảm/secret | Logging review |
| AC-34 | Operation identifiers được dùng trong tracing có phân quyền | Observability design |
| AC-35 | Goodput đo unique confirmed effects | Metrics/report |
| AC-36 | DB attempts và HTTP responses không bị đánh đồng business effects | Measurement report |
| AC-37 | Kết luận PASS nêu đủ data scope và consistency cut | Verification manifest |
| AC-38 | Unknown outcomes chưa resolve không tự ghi PASS | Decision gate |
| AC-39 | Có recovery khi receipt hết hạn/bị mất sau restore | Disaster-recovery drill |
| AC-40 | Các business invariants độc lập idempotency đều đạt | Inventory/payment ledger |
| AC-41 | Có stop criteria khi duplicate effect được xác nhận | Runbook |
| AC-42 | Có owner/approval cho sửa dữ liệu | Incident record |
| AC-43 | Có negative test cho unsafe check-then-write | Regression |
| AC-44 | Có full evidences trước go-live | Test manifest |
| AC-45 | Kịch bản timeout sau commit được tái lập | Fault timeline |
| AC-46 | API không báo success giả trước durable ACK | Contract assertion |
| AC-47 | Canonical payload không bỏ trường nghiệp vụ quan trọng | Schema tests |
| AC-48 | Idempotency retention tương thích privacy/legal policy | Data policy approval |

Không phải mọi ứng dụng đều cần tất cả ngoại lệ cross-Region/payment; dùng những hàng liên quan tới hệ thật, nhưng **không bỏ bất biến critical** để đạt điểm pass đẹp.

## 90. Các trạng thái báo cáo phải chính xác

**PASS:**

```text
Required scope covered.
Business effect multiplicity at most one per command.
All required terminal receipts/effects consistent.
No critical invariant violation.
Unknown outcomes resolved according to contract.
```

**FAIL:**

```text
Duplicate effect.
Missing acknowledged effect.
Receipt/effect contradiction not explained by valid protocol.
Payload mismatch accepted as same command.
Cross-tenant receipt leak.
Unsafe replay after delete or TTL expiry.
```

**INCONCLUSIVE:**

```text
Cannot establish authoritative commit boundary.
Test only observed HTTP responses, not final state.
Receipt source unavailable.
Recovery history/gaps missing.
Coverage incomplete.
Some UNKNOWN operations have no reliable evidence.
```

**RECOVERING:**

```text
Operations queued for reconciliation.
Read model/receipt replication not yet caught up.
Quarantine active; no unsafe mutations admitted.
```

Đừng ghi `PASS` chỉ vì chưa quan sát thấy duplicate khi test không bao phủ concurrency/ACK loss.

## 91. Evidence manifest cho một lượt lab

```yaml
verificationId: "IDEMPOTENCY-LAB-EXAMPLE"
environment: "isolated-staging"
applicationBuild: "<build-id>"
javaRuntime: "17+"
database:
  engine: "<name/version>"
  topology: "<nodes/regions>"
  receiptConsistency: "<declared>"
scenario:
  name: "ack-loss-after-commit"
  logicalOperationId: "<synthetic-id>"
  payloadFingerprintVersion: "v1"
  attemptedRequestCount: 20
  concurrentClients: 16
injection:
  point: "after-db-commit-before-http-ack"
  method: "<fault-hook>"
expected:
  committedBusinessEffects: 1
  uniqueAppliedReceipts: 1
  inventoryDelta: -1
  distinctReservationIds: 1
observed:
  committedBusinessEffects: "<measured>"
  uniqueAppliedReceipts: "<measured>"
  inventoryDelta: "<measured>"
  distinctReservationIds: "<measured>"
  unresolvedOutcomes: "<measured>"
coverage:
  tenants: "<scope>"
  operations: "<scope>"
  faultPoints: "<scope>"
  verifierVersion: "<version>"
decision:
  correctness: "INCONCLUSIVE"
  reason: "awaiting authoritative evidence"
```

Các placeholder không phải số liệu thật. Một manifest cần gắn hash/provenance của logs và report, quyền đọc hạn chế và không đưa PII vào evidence public.

## 92. Báo cáo tổng hợp theo từng kịch bản

| Kịch bản | Logical cmds | Attempts | Confirmed effects | Duplicate effects | Unknown | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Same key 100 retries | 1 | 100 | 1 | 0 | 0 | PASS |
| Same key 16 concurrent | 1 | 16 | 1 | 0 | 0 | PASS |
| Same key changed payload | 1 key, conflict | 2 | 1 | 0 | 0 | PASS |
| Two distinct keys, last unit | 2 | 2 | 1 | 0 | 0 | PASS |
| Commit then ACK lost | 1 | 2 | 1 | 0 | 0 after reconciliation | PASS |
| DB lost, no receipt evidence | 1 | 2 | ? | ? | 1 | INCONCLUSIVE |
| Duplicate payment capture | 1 | 2+ | 2 | 1 | 0 | FAIL |

Các số là ví dụ minh họa, không phải output thực. `PASS` còn cần thỏa business authorization/durability/retention và coverage tương ứng.

## 93. Bài tập 1 — Tìm lỗi của check-then-write

Cho pseudo-code:

```text
if redis.get("op:" + operationId) == null:
    mongo.inventory.inc(-quantity)
    redis.setex("op:" + operationId, 3600, "DONE")
```

Hãy:
1. Liệt kê ít nhất ba race/crash windows.
2. Phân biệt Redis eviction và MongoDB commit UNKNOWN.
3. Nêu cách hai Java pods cùng pass check.
4. Thiết kế lại với authoritative receipt + effect.
5. Dựng fault test mô phỏng crash ngay sau `inc`.
6. Nêu vì sao tăng TTL không sửa được vấn đề atomicity.

## 94. Bài tập 2 — Tạo lịch trình hai request đồng thời

Tạo trace:

```text
A: read receipt -> absent
B: read receipt -> absent
A: decrement inventory
B: decrement inventory
A: insert receipt
B: insert receipt -> unique conflict
```

Yêu cầu:
- Số mutations có thể đã xảy ra?
- Tại sao unique receipt insert cuối không đủ?
- Nếu dùng transaction, test ở boundary nào?
- Khi unique conflict xảy ra, có nên retry toàn workflow?
- Tạo lịch trình tương ứng với đúng một effect.

## 95. Bài tập 3 — Phân loại timeout

Các trường hợp:

```text
F0 before TCP send
F1 after DB receives
F2 after business commit
F3 after HTTP body sent but client connection dropped
```

Với mỗi:
- Client biết gì?
- DB có thể đã commit không?
- Chứng cứ nào xác nhận?
- Có nên tạo key mới không?
- Trạng thái operation nào đúng?
- Ghi retry budget/deadline thế nào?

## 96. Bài tập 4 — Khác fingerprint

Request 1:

```json
{"listingId":"L1","quantity":1}
```

Retry A:

```json
{"quantity":1,"listingId":"L1"}
```

Retry B:

```json
{"listingId":"L1","quantity":2}
```

Hãy:
- Thiết kế canonical encoder.
- Xác định A trùng/B conflict.
- Chọn fields được tính/bỏ khỏi hash.
- Giải thích null/missing semantics.
- Ghi fingerprint schema version.
- Thiết kế negative test cho tenant khác.

## 97. Bài tập 5 — Hai command tranh tồn kho

```text
Stock=1
op-A reserve 1
op-B reserve 1
```

Hai keys khác nhau. Viết:
- Invariant.
- Cơ chế CAS/conditional write.
- Expected statuses.
- Receipt rules.
- Concurrency test 100 workers.
- Vì sao idempotency chỉ theo key không đủ.

## 98. Bài tập 6 — Consumer bị kill đúng lúc

```text
Consume E1.
Target increments projection.
Worker crashes before ACK.
E1 redelivered.
```

Yêu cầu:
- Thiết kế applied-event ID/marker.
- Phân biệt effect và offset ACK.
- Chọn atomic boundary.
- Nếu không có transaction, mô tả reconciler.
- Test old version arrive after new version.
- Đo duplicated deliveries và confirmed effects riêng.

## 99. Bài tập 7 — DynamoDB transaction abort

Một transaction gồm `Put receipt`, `Update inventory condition`, `Put reservation`, nhưng stock không đủ.

Hỏi:
- Receipt REJECTED đã được lưu chưa?
- Vì sao API bị abort?
- Muốn lưu terminal rejection phải làm gì?
- Nếu giữ rejection retryable, contract/test nào thay?
- Khi retry cùng key sau restock, behavior mong muốn?
- Thế nào là `UNKNOWN` và khi nào tra receipt?

## 100. Bài tập 8 — Redis Lua và durability

Giả sử Lua script atomic chạy xong, client ACK success, sau đó Redis failover và mất recent writes theo cấu hình persistence.

Yêu cầu:
- Execution atomicity khác durability thế nào?
- Receipt và counter có thể bị mất gì?
- Nếu PSP bên ngoài đã charge, rủi ro nào?
- Thiết kế recovery/receipt authority.
- Kịch bản test failover và cache eviction.
- Nếu Redis Cluster keys khác slots, giải pháp data model?

## 101. Bài tập 9 — Receipt TTL và offline retries

```text
Receipt TTL: 30 minutes.
Mobile offline queue: up to 7 days.
Webhook callback retries: up to 3 days.
```

Hãy:
- Xác định mismatch retention.
- Chọn dedup ledger/business ID guard khác.
- Thiết kế command expiry policy.
- Xử lý bản ghi đã xóa.
- Kiểm legal/privacy retention.
- Lập test với fake clock và restored backup.

## 102. Bài tập 10 — Go/no-go của migration

Kết quả giả định:

```text
Sequential duplicate: PASS
Concurrent duplicate on same pod: PASS
Concurrent duplicate across pods: NOT_TESTED
Commit ACK loss: FAIL (2 effects)
Payment provider reconciliation: NOT_RUN
p99 latency: excellent
```

Yêu cầu:
- Quyết định GO/NO-GO.
- Nêu vì sao p99 không bù được duplicate effect.
- Xác định tests bắt buộc còn thiếu.
- Viết stop/incident plan.
- Chọn owner và evidence cần có.
- Đề xuất thiết kế sửa atomicity.

## 103. Runbook khi phát hiện duplicate effect

**Trigger:** một logical operationId có nhiều business effects được commit.

1. Tạo incident ID, xác định affected tenants/keys/operations và khoảng thời gian.
2. Dừng hoặc giảm những write paths tạo thêm duplication theo policy, không phá các invariants khác.
3. Giữ logs, request attempts, operation receipts, DB commit evidence, CDC positions.
4. Phân biệt duplicate transport attempts với duplicate committed effects.
5. Đối soát source authoritative ledger.
6. Xác định window: receipt race, cache eviction, crash, TTL, failover hay schema.
7. Kiểm các external side effects (payments, shipping, notifications).
8. Không tự delete receipt hoặc “đặt stock về số đẹp” không có ledger.
9. Thiết kế repair/compensation idempotent có owner approval.
10. Kiểm per-key amounts, revisions, unique contributions.
11. Rerun fault cases sau sửa.
12. Cập nhật runbook, regression tests và monitoring.

Nếu đã có duplicate payment, ưu tiên payment provider reconciliation và quy trình tài chính; không giả xóa một DB row là hoàn tiền.

## 104. Runbook khi nhiều operations ở trạng thái UNKNOWN

1. Xác định request/operation IDs và last acknowledged responses.
2. Tra authority receipts với consistency phù hợp.
3. Phân biệt stale replica NOT_FOUND.
4. Kiểm DB transaction log/CDC/outbox theo phạm vi được phép.
5. Kiểm external providers nếu business effect ra ngoài DB.
6. Không tạo operation IDs mới để thử cho “ra kết quả”.
7. Giới hạn retries/concurrency để tránh storm.
8. Chuyển các operations chưa rõ vào reconciliation queue.
9. Ghi `APPLIED`, `NOT_APPLIED_CONFIRMED`, `UNKNOWN`.
10. Chỉ cho phép tiếp tục mutation khi có nguồn chứng cứ/atomic guard.
11. Đo age của UNKNOWN và SLA xử lý.
12. Ghi user-facing status chính xác.

Một read timeout khi tra receipt không phải chứng cứ original write đã thất bại.

## 105. Runbook khi receipt và business effect không khớp

Có hai hướng lỗi:

```text
Receipt APPLIED nhưng không có reservation.
Reservation/inventory effect có nhưng không có receipt.
```

Quy trình:

1. Bảo toàn evidence và chặn replays có thể gây hại.
2. Xác định commit boundary thực và transaction scope.
3. Kiểm record versions, tombstones, TTL và backup/restore cut.
4. Kiểm có eventual read model lag hay authority thực sự thiếu.
5. Phân loại source of truth.
6. Đánh giá business invariant và external effects.
7. Thiết kế sửa đúng một lần có receipts và phê duyệt.
8. Không đổi `UNKNOWN` thành `REJECTED` chỉ vì marker vắng.
9. Rerun verification counts/key digests/ledger.
10. Không mở traffic bình thường tới khi risk gate đạt.

## 106. Runbook khi retry storm làm hot partition

1. Tách logical commands/s khỏi physical DB attempts/s.
2. Kiểm tầng nào đang retry: client, gateway, app, SDK, consumer.
3. Giữ stable operation IDs.
4. Bật bounded backoff+jitter/deadline theo policy.
5. Giảm concurrency và duplicate in-flight work.
6. Kiểm receipt lookup có dùng authority không.
7. Kiểm hot key/CAS contention.
8. Kiểm timeout budget/pool queue.
9. Không hạ consistency/atomicity chỉ để tăng RPS.
10. Đo goodput, p99 terminal confirmation, unknown backlog.
11. Verify inventory/payment ledger sau sự cố.
12. Ghi lessons về retry ownership.

## 107. Runbook khi cần triển khai idempotency lên hệ cũ

1. Inventory toàn bộ write endpoints và business side effects.
2. Chọn scope idempotency key và payload canonicalization version.
3. Chọn terminal rejection policy, response replay format.
4. Thiết kế unique/durable receipt storage.
5. Chứng minh atomicity với business mutation, hoặc chọn protocol thay thế.
6. Chỉ định authoritative lookup consistency.
7. Quy định retention/retry/CDC/rollback windows.
8. Instrument operation IDs, attempt IDs và outcomes.
9. Chạy shadow/read-only validation nếu phù hợp.
10. Test duplicate tuần tự/đồng thời, ACK loss, restart/failover.
11. Test negative changed payload/cross-tenant access.
12. Test old clients và API rollback compatibility.
13. Canary có stop criteria khi duplicate effect.
14. Đối soát business ledger và external effects.
15. Chỉ triển khai rộng sau khi full gates đạt.

## 108. Mẫu báo cáo bài thực hành

```markdown
# Kiểm chứng tính lũy đẳng khi yêu cầu ghi bị gửi lại

## Thông tin
- Experiment/incident ID:
- Chức năng/endpoint:
- Business operation scope:
- Application build/Java version:
- Database engine/version/topology:
- Environment và timestamp:
- Tester/reviewer:

## Hợp đồng
- Idempotency key format/scope:
- Payload canonicalization/fingerprint version:
- Business invariant:
- Receipt schema/retention:
- Response replay/terminal rejection:
- Authority consistency:
- Retry/deadline policy:

## Tình huống
- Fault injection point:
- Concurrent clients:
- Logical commands:
- Physical attempts:
- API response/timeout breakdown:
- Authoritative commit cut/watermark:

## Bằng chứng
- Unique operation receipts:
- Confirmed business effects:
- Inventory/ledger pre/post:
- Duplicate/changed-key conflicts:
- UNKNOWN operations:
- Outbox/CDC downstream effects:
- Security/tenant negative results:
- Failover/restart behavior:

## Kết luận
- Correctness PASS/FAIL/INCONCLUSIVE:
- Business invariants PASS/FAIL:
- Liveness/performance PASS/FAIL:
- Coverage and limitations:
- Violating trace IDs:
- Action/owner/approval:
- Evidence location/hash:
```

Mẫu chỉ có giá trị khi điền **dữ liệu thật** từ test/lab, không tự ghi PASS theo mong muốn.

## 109. Bộ checklist ngắn trước khi báo PASS

```text
[ ] Command có stable idempotency identity theo authenticated scope.
[ ] Fingerprint bao gồm mọi trường nghiệp vụ có ý nghĩa.
[ ] Cùng key khác payload bị từ chối.
[ ] Retry cùng key không tạo reservation thứ hai.
[ ] Concurrent duplicates qua nhiều instances không tạo second effect.
[ ] Receipt và mutation cùng atomic boundary hoặc protocol được kiểm.
[ ] Commit ACK-loss được kiểm, không suy timeout=failed.
[ ] Read receipt dùng consistency/authority phù hợp.
[ ] In-progress không treo vô hạn.
[ ] Terminal rejection semantics rõ.
[ ] Two different operations tranh stock giữ invariant.
[ ] Duplicate cancel không release stock hai lần.
[ ] Receipt TTL/retention đủ replay và recovery window.
[ ] Old events không ghi đè revisions/tombstones mới.
[ ] Outbox/CDC consumers có event dedup, checkpoint an toàn.
[ ] Payment/external effects được reconcile độc lập.
[ ] Restore/failover không tạo mất receipt đã hứa.
[ ] Retry policies bounded, không tạo retry storm.
[ ] Attempt ID khác operationId và traceId.
[ ] Logging redacted, tenant authorization đạt.
[ ] Source/target states được đọc ở logical cut phù hợp.
[ ] Counts/effects/receipts đã đối soát.
[ ] Có negative tests và fault injection.
[ ] UNKNOWN không bị làm tròn thành success/failure.
[ ] PASS/FAIL/INCONCLUSIVE và limitations ghi rõ.
[ ] Có owner và stop conditions nếu duplicate được phát hiện.
```

## 110. Những hiểu nhầm thường gặp

**“Client chỉ gửi một request nên effect chỉ một lần.”** Gateway, driver, queue và CDC có thể gửi lại.

**“HTTP timeout nghĩa DB chưa commit.”** Có thể commit trước khi ACK mất.

**“Dùng UUID là đã idempotent.”** UUID phải ổn định xuyên retries, được enforce tại authority và gắn với receipt/effect.

**“Cùng payload luôn là cùng ý định.”** Hai purchases giống nhau có thể là hai intents khác nhau, cần operation IDs.

**“Same key + khác payload nên chấp nhận và update receipt.”** Có thể che client bug và sinh effect không mong muốn.

**“Hash JSON string là fingerprint đúng.”** Thứ tự fields/encoding/decimal/null cần canonicalization.

**“Lưu dedup key trong local map đủ cho nhiều pods.”** Không chia sẻ state.

**“Kiểm receipt trước rồi mới mutate là atomic.”** Check-then-write có race.

**“Unique receipt insert cuối sẽ undo double decrement.”** DB không tự undo mutation trước đó nếu ngoài transaction.

**“Transaction abort vẫn có thể lưu REJECTED receipt trong chính transaction.”** Không thể coi một transaction đã abort là đã commit receipt.

**“Redis Lua atomic nghĩa commit với payment provider cũng atomic.”** Không có transaction xuyên hai hệ như vậy.

**“Redis receipt có TTL nên luôn chống duplicate.”** TTL, eviction và failover có thể xóa receipt.

**“DynamoDB token của SDK bảo vệ mọi retry nhiều năm.”** Có scope/window cụ thể; cần business receipt dài hạn nếu yêu cầu.

**“Cassandra BATCH làm mọi writes xuyên partitions thành ACID transaction tổng quát.”** Không được suy như vậy.

**“MongoDB driver retryable writes thay business operation IDs.”** Không chống mọi application/external/consumer duplicate.

**“Một GET từ replica trả NOT_FOUND chứng minh original write chưa commit.”** Có thể stale.

**“CAS failure khi retry nghĩa original write failed.”** Lần đầu có thể đã commit.

**“SET lại cùng value nghĩa không có side effect trùng.”** Outbox/webhook/audit/counter có thể vẫn bị nhân đôi.

**“DELETE hai lần luôn an toàn.”** Business cancel có thể release inventory/refund hai lần.

**“Một command idempotent nghĩa các commands khác nhau không xung đột.”** Cần concurrency control/invariant.

**“Một consumer nhận event một lần là business effect đúng một lần.”** Delivery khác commit effect.

**“Outbox không duplicate vì DB transaction atomic.”** Publisher có thể deliver trùng; consumer cần idempotency.

**“Receipt sống một giờ đủ cho mọi hệ.”** Cần tính offline/replay/callback/recovery windows.

**“Restore snapshot cũ vẫn giữ mọi receipt.”** Các commits sau snapshot có thể thiếu.

**“Không có duplicate trong 10 requests tuần tự nghĩa production an toàn.”** Race/failover cần stress/fault tests.

**“Kết quả HTTP giống nhau chứng minh inventory đúng.”** Phải kiểm business state/ledger.

**“Tăng retry count luôn cải thiện reliability.”** Có thể nhân storm và làm quá tải hot partition.

**“Exactly-once delivery là mặc định của mọi queue.”** Cần đọc guarantee cụ thể và bảo vệ business effects.

**“Không thể xác định write outcome thì cứ retry key mới.”** Cực kỳ nguy hiểm với tiền/tồn kho.

**“Chỉ cần không duplicate, pending forever cũng PASS.”** Liveness là yêu cầu riêng.

**“p99 tốt có thể bù một double payment.”** Correctness gate là điều kiện bắt buộc.

## Kết luận

**Kiểm chứng tính lũy đẳng khi yêu cầu ghi bị gửi lại** là một bài thực hành về **bằng chứng**, không phải về một annotation hoặc tham số `retry=true`. Khi một HTTP request, database command hay CDC event được gửi lại, hệ thống phải nhận ra **cùng ý định nghiệp vụ**, đối chiếu **payload fingerprint**, và bảo đảm **effect cùng receipt được commit theo một atomicity/protocol có thể chứng minh**. Một timeout sau commit phải được phân loại là kết quả chưa rõ ở phía client cho tới khi có receipt, không được tùy tiện tạo intent mới.

Bộ thực hành Java 17 minh họa đúng những cửa sổ nguy hiểm: mất ACK sau commit, gửi lại tuần tự, 16 clients cùng gửi một command, dùng lại key với payload khác, và hai commands khác nhau tranh chỗ cuối. Khi triển khai trên NoSQL thật, phải thay lock trong JVM bằng primitive phù hợp: **MongoDB transaction + unique receipt**, **DynamoDB conditional transactions với semantics rõ cho rejection**, **Cassandra/ScyllaDB LWT theo ranh giới partition**, hoặc **Redis Lua cùng hash slot và durability contract**. Không engine nào tự bảo vệ hiệu ứng ngoài database như payment capture; những tác vụ đó cần receipt và reconciliation riêng.

Nghiệm thu chỉ đạt khi đã kiểm **không có double business effect, không mất acknowledged effect, không có receipt/effect mâu thuẫn, không phá inventory/payment invariants, không lộ dữ liệu tenant, không bỏ qua retries/CDC/recovery windows**, và mọi kết quả UNKNOWN được xử lý minh bạch. Số requests, HTTP 200 hay latency thấp không thay được nguồn chứng cứ này. Tính lũy đẳng đáng tin không chỉ là “gửi lại vẫn không lỗi”, mà là **dù mạng, tiến trình hoặc hệ thống có gửi lại, người dùng vẫn chỉ nhận đúng hiệu ứng mà họ đã yêu cầu một lần**.

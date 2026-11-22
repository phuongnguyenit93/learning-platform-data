# Timeout, retry và kiểm tra tính lũy đẳng của từng lệnh

Một chương trình Java kết nối NoSQL phải đối mặt với những lỗi rất bình thường trong hệ phân tán: mất kết nối TCP, chờ replica quá lâu, node chuyển vai trò, database trả throttling, hoặc người dùng gửi lại request khi ứng dụng đã báo timeout. Điều nguy hiểm không nằm ở bản thân exception mà nằm ở **hành động tiếp theo của chương trình**.

Ví dụ một lệnh `INCR` hoặc `UPDATE balance = balance + 1` đã được server thực hiện, nhưng ACK bị mất. Java bắt được `SocketTimeoutException` rồi gọi lại lệnh. Kết quả: bộ đếm tăng hai lần. Ngược lại, với một truy vấn `GET` thuần đọc, việc thử lại trong cùng consistency contract thường không tạo tác động ghi, dù vẫn phải giới hạn thời gian và tránh làm quá tải database.

Trong bài **Database No SQL → Kết nối Java**, chúng ta xây dựng một cách làm có hệ thống cho **timeout, retry và kiểm tra tính lũy đẳng của từng lệnh**. Mục tiêu là khi nhìn vào một câu lệnh từ MongoDB Java Driver, AWS SDK for Java cho DynamoDB, Java Driver cho Cassandra/ScyllaDB hoặc client Redis, bạn có thể trả lời:

1. Lệnh đã được gửi đến server hay chưa?
2. Server có thể đã commit trước khi Java nhận timeout không?
3. Nếu thực hiện lệnh nhiều lần, trạng thái và **hiệu ứng nghiệp vụ** có giữ nguyên không?
4. Có writer khác chạy đồng thời làm thay đổi ý nghĩa của retry không?
5. Driver đã tự retry chưa, và ứng dụng có đang nhân số attempts lên không?
6. Có operation ID, điều kiện ghi, transaction hoặc ledger để thực hiện lại an toàn không?
7. Phải trả `APPLIED`, `REJECTED`, `PENDING` hay `UNKNOWN` cho caller?
8. Giới hạn số lần, khoảng chờ, deadline và recovery như thế nào?

> Quy tắc quan trọng nhất: **timeout không có nghĩa lệnh chưa được thực hiện**; **một câu lệnh có vẻ lũy đẳng về giá trị lưu trữ không tự động lũy đẳng về hiệu ứng nghiệp vụ**. Tên exception, nhãn retryable, mặc định timeout và cơ chế retry phụ thuộc phiên bản client/driver và cách cấu hình. Các ví dụ phải được kiểm tra với phiên bản SDK đang sử dụng trước khi đưa vào production.

---

## 1. Tính lũy đẳng là gì?

Một phép biến đổi trạng thái \(f\) gọi là **lũy đẳng** (*idempotent*) nếu:

\[
f(f(s)) = f(s)
\]

với mọi trạng thái \(s\) thuộc phạm vi được định nghĩa.

Một số ví dụ trực giác:

```text
SET user.status = ACTIVE
    Lần 1: ACTIVE
    Lần 2: ACTIVE
    Lần 3: ACTIVE

INCREMENT user.loginCount by 1
    Lần 1: 11
    Lần 2: 12
    Lần 3: 13
```

Nếu chỉ xét một field và không có writer khác, phép gán cùng một giá trị là lũy đẳng về **trạng thái cuối**; tăng số đếm không phải.

Tuy nhiên, cần phân biệt ba phạm vi:

- **Lũy đẳng của một storage operation:** chạy lại câu lệnh làm field có cùng kết quả không?
- **Lũy đẳng của một business command:** chạy lại cả thao tác có tạo thêm email, charge, log, reservation hay event không?
- **Lũy đẳng dưới concurrency/failover:** khi các writer khác thay đổi state hoặc replica đổi vai, retry có ghi đè dữ liệu mới, hồi sinh bản ghi đã xóa hay áp lại hiệu ứng không?

Một lệnh chỉ có thể được gọi là “retry an toàn” **trong một hợp đồng cụ thể**, không chỉ dựa vào tên phương thức `save()`, `update()`, `put()` hoặc `execute()`.

## 2. Timeout trong Java: nó báo điều gì?

Một timeout là kết quả của việc **một tầng không hoàn tất công việc trong thời hạn quan sát**. Nó không mô tả đầy đủ lịch sử lệnh ở tầng dưới.

```text
Client Java         Driver        Coordinator        Storage replicas
     |                |                |                   |
     |-- command ---->|                |                   |
     |                |--- request --->|                   |
     |                |                |--- write -------> |
     |                |                |<-- ACK? --------- |
     |                |<-- response? --|                   |
     |<-- timeout ----|                |                   |
```

Có ít nhất bốn lịch sử cùng dẫn tới timeout:

```text
A. Request chưa rời client.
B. Request đến coordinator nhưng chưa commit.
C. Một số replica đã áp mutation, chưa đủ commit/ACK theo policy.
D. Commit hoàn tất, response bị thất lạc hoặc đến sau deadline.
```

Trong trường hợp D, một lần retry mù của lệnh không lũy đẳng có thể tạo **hiệu ứng trùng**.

Vì vậy, **đối với lệnh ghi đã có thể được dispatch**, khi không có bằng chứng về kết quả, hãy mô hình hóa **commit outcome = UNKNOWN**. Sau đó tra cứu operation ID hoặc retry cùng danh tính theo một giao thức được bảo đảm, thay vì khẳng định `FAILED`.

## 3. Phân biệt các tầng timeout

| Tầng | Ví dụ | Điều suy ra được | Không được suy |
| --- | --- | --- | --- |
| **Pool acquire** | Driver không lấy được connection | Attempt này có thể chưa dispatch | Database chắc chắn chết |
| **DNS/connect** | DNS lỗi, TCP connect timeout | Chưa thiết lập connection mới | Chưa có attempt trước đó |
| **TLS/authentication** | TLS handshake timeout | Channel chưa sẵn sàng | Tất cả nodes đều hỏng |
| **Server selection** | Không tìm được server phù hợp | Driver chưa chọn được authority theo yêu cầu | Hạ consistency là an toàn |
| **Socket read** | Không nhận response kịp | Request có thể đã được gửi | Mutation chưa commit |
| **Request execution** | Coordinator quá thời gian | Operation chưa hoàn tất theo quan sát | Không replica nào đã ghi |
| **Quorum/consistency** | Không đủ ACK từ replicas | Không đạt contract của request | Có thể tự đổi sang consistency yếu hơn |
| **Transaction commit** | Response của commit thất lạc | Quyết định có thể chưa biết ở client | Transaction chắc chắn rollback |
| **HTTP/API deadline** | Gateway 504 | Caller hết budget chờ | Backend không còn xử lý |
| **Job deadline** | Worker quá hạn | Workflow cần recovery/escalation | Có thể bỏ operation ledger |

Tên cấu hình trong từng SDK khác nhau; không gom mọi thứ vào một `socketTimeout=3000` rồi nghĩ rằng đã quản lý được toàn bộ.

## 4. Phân biệt connect timeout và read timeout

**Connect timeout** xảy ra trước khi kết nối mới được thiết lập:

```text
Client --TCP SYN--> endpoint
Client chờ...
Connect timeout
```

Nếu chắc chắn chưa có request payload nào được gửi qua attempt đó, retry có thể an toàn hơn. Nhưng một lời gọi SDK có thể bao gồm **nhiều attempts nội bộ** hoặc đã dùng một connection khác trước đó.

**Read timeout** xuất hiện sau khi lệnh có thể đã tới server:

```text
Client --UPDATE--> DB
DB commit
Response bị mất
Client read timeout
```

Lệnh có thể đã được áp. Với write, cần xác minh kết quả theo operation ID, session/transaction protocol hoặc idempotency strategy.

**Kết luận:** loại timeout giúp khoanh vùng, nhưng **không thể thay thế thông tin về dispatch phase và commit receipt**.

## 5. Cancellation không tự hủy một mutation đã gửi

Trong Java:

```java
future.cancel(true);
```

hoặc HTTP client hết deadline có thể chỉ hủy phần **chờ ở phía ứng dụng**. Backend vẫn có thể đang xử lý lệnh và commit sau khi caller đã thoát.

Cần trả lời:

- Driver có hỗ trợ cancellation server-side cho API này không?
- Cancellation có được server xác nhận không?
- Nếu server chưa xác nhận, transaction hoặc write có thể hoàn tất muộn không?
- Có operation ID để tra kết quả sau đó không?
- Có thể chặn các attempts cũ bằng epoch/fencing khi ownership thay đổi không?

Không dùng `InterruptedException` hay `CancellationException` để kết luận write chắc chắn chưa tồn tại.

## 6. “Retry được” khác “nên retry”

Giả sử `GET order by id` không gây thay đổi trạng thái:

```text
GET -> timeout
GET -> timeout
GET -> success
```

Về mặt hiệu ứng ghi, nó có thể an toàn khi retry. Nhưng nếu 10.000 clients cùng retry ngay lập tức, cluster có thể bị **retry storm**.

Một retry hợp lệ cần đồng thời:

1. Operation có thể thực hiện lại trong đúng semantics.
2. Lỗi thuộc loại có thể phục hồi, hoặc recovery protocol cho phép.
3. Vẫn còn **overall deadline**.
4. Vẫn còn số lần và **retry budget**.
5. Số requests bổ sung không đẩy dependency vào quá tải.
6. Thay endpoint không hạ read/write consistency trái contract.
7. Caller chưa hủy yêu cầu và workflow vẫn cần kết quả.
8. Với write không chắc kết quả, cơ chế dedup/commit lookup phải đủ mạnh.

**Idempotency là điều kiện an toàn quan trọng, không phải lý do để retry vô hạn.**

## 7. Một ma trận lũy đẳng cho những câu lệnh thường gặp

| Lệnh hoặc ý định | Lũy đẳng về trạng thái trong điều kiện đơn giản? | Rủi ro khi retry | Cách bảo vệ |
| --- | --- | --- | --- |
| `GET key` | Có, không ghi | Tải tăng, stale read nếu đổi replica | Deadline, bounded retry, giữ consistency |
| `QUERY` có filter | Thường là đọc | Tốn scan/fan-out, kết quả có thể đổi theo thời gian | Retry bounded, cursor/snapshot contract |
| `SET key=value` | Có trong phạm vi giá trị field | Ghi đè update mới của writer khác | Version guard/CAS |
| `PUT same document` | Có thể | Overwrite fields/version; triggers/audit | Conditional revision, idempotency key |
| `INSERT` với ID ổn định | Có thể quan sát duplicate key | Sau timeout không rõ insert lần trước đã commit | Unique identity và authoritative lookup |
| `INSERT` với ID sinh mới mỗi attempt | Không | Hai records | Stable business ID |
| `UPDATE field = constant` | Thường có về field | Side effects, stale overwrite | CAS + operation ledger |
| `INCREMENT counter` | Không | Tăng hai lần | Atomic dedup + increment hoặc recompute |
| `APPEND item` vào list | Không | Phần tử lặp | Set semantics/unique element ID |
| `ADD member` vào set | Có theo membership | TTL, event side effects, concurrency | Identity ổn định, kiểm tra lifecycle |
| `DELETE key` | Có thể về trạng thái absent | Xóa generation mới, duplicate event | Conditional delete, tombstone/generation |
| `CAS(expectedVersion)` | Có điều kiện | Timeout rồi CAS fail không chứng minh lệnh cũ chưa apply | OperationId + re-read/reconcile |
| `BATCH` nhiều writes | Tùy từng operation và atomic boundary | Partial failures, trùng effect | Transaction/protocol, per-item receipt |
| `TRANSACTION` | Tùy contract/driver | Commit outcome unknown, callback lặp | Retry theo transaction protocol, stable ID |
| `CALL payment provider` | Không mặc định | Duplicate charge | Provider idempotency key + status lookup |

“Lũy đẳng” ở cột hai luôn có **điều kiện**. Chẳng hạn hai lần `DELETE` đưa key về absent nếu không ai tạo lại key giữa hai lần; trong một hệ có recreate, lần delete thứ hai có thể xóa **bản ghi mới**.

## 8. GET có vẻ dễ nhưng consistency vẫn quan trọng

Ví dụ một ứng dụng cần nhìn thấy version vừa ghi:

```text
Client A:
    write order status=PAID -> committed.

Client A:
    GET order status -> timeout.
```

Nếu driver retry GET sang một eventual replica chưa bắt kịp, có thể nhận:

```text
status=PENDING
```

GET không tạo write trùng, nhưng **vi phạm read-your-writes/strong-read contract** nếu ứng dụng đã hứa trạng thái mới nhất.

Với retry read phải giữ:

- Read concern/consistency level được yêu cầu.
- Routing theo leader/authority khi cần.
- Session/casual consistency token nếu dùng.
- Min revision hoặc read barrier nếu API hỗ trợ.
- Cursor semantics nếu truy vấn phân trang.

**Retry đọc an toàn về side effect không bảo đảm kết quả đúng về độ tươi.**

## 9. SET có tính lũy đẳng, nhưng blind overwrite không an toàn dưới concurrency

Giả sử:

```text
Initial: user.status = PENDING, version=7.

Writer A:
    SET status=ACTIVE
    timeout sau commit.

Writer B:
    SET status=SUSPENDED
    commit.

Writer A:
    retry SET status=ACTIVE.
```

Kết quả cuối `ACTIVE`, làm mất quyết định mới hơn của B.

Vấn đề không phải công thức `SET x=ACTIVE` không lũy đẳng khi chạy hai lần liên tiếp; vấn đề là **interleaving với một writer khác**.

Một biện pháp:

```text
UPDATE user
SET status=ACTIVE, version=8
WHERE version=7
```

Khi A retry sau khi B đã đổi version, CAS không khớp. A phải **tra operation ID hoặc lịch sử version** để biết write ban đầu đã commit hay chưa; CAS failure một mình không chứng minh attempt A thất bại.

## 10. INSERT: ổn định ID trước khi retry

**Không nên:**

```java
// Mỗi attempt sinh một ID mới.
String orderId = UUID.randomUUID().toString();
repository.insert(orderId, order);
```

Nếu caller retry cả hàm, mỗi attempt có thể tạo một order khác.

**Nên cân nhắc:**

```java
// ID được tạo khi ý định bắt đầu và giữ qua retries.
String orderId = command.orderId();
String operationId = command.operationId();

repository.insertIfAbsent(orderId, operationId, order);
```

Những điều cần kiểm tra:

- Unique key thực sự được bảo đảm trong phạm vi tenant/business.
- `insertIfAbsent` là atomic operation của engine, không phải GET rồi PUT.
- Nếu trả duplicate/condition failed, cần phân biệt **cùng operationId** với **business conflict của một ý định khác**.
- ID không tái sử dụng sau khi record bị xóa nếu late retry có thể tới.
- Có receipt để trả đúng kết quả của attempt trước.

Một lỗi duplicate-key sau timeout **có thể là dấu hiệu lệnh trước đã thành công**, nhưng cũng có thể do một writer khác. Không tự trả success nếu chưa xác minh identity/fingerprint.

## 11. INCREMENT: ví dụ điển hình không lũy đẳng

Ban đầu:

```text
viewCount = 100
```

Client:

```text
INCRBY viewCount 1
```

Server đã tăng lên `101` nhưng ACK bị mất; client retry thì counter thành `102`.

Để đảm bảo một business event chỉ tăng một lần, có thể dùng:

- Operation marker cùng atomic boundary với increment.
- EventId và dedup trong consumer xử lý.
- Unique contribution records rồi aggregate.
- Ledger/transaction khi giá trị mang tính tài chính.
- Tính lại counter từ events/source nếu business cho phép.

Không thể giải quyết triệt để bằng tăng `socketTimeout` hay thêm `sleep(100)`.

## 12. APPEND, PUSH và các lệnh tạo side effect

Lệnh append:

```text
PUSH notificationLog "OrderPaid"
```

retry có thể tạo hai entries.

Một lệnh **add-to-set** có thể giữ membership không lặp nếu phần tử có ID ổn định, nhưng vẫn phải xét:

- Event/email được tạo mỗi lần hay chỉ khi record thay đổi?
- Element equality có dựa vào identity hay một timestamp khác mỗi attempt?
- TTL hoặc remove có xảy ra giữa hai attempts không?
- Concurrent writers có cập nhật cùng collection không?
- Side effect ngoài database có được dedup riêng không?

Đánh giá tính lũy đẳng phải gồm **dữ liệu phụ, message, counter, audit và external calls**, không chỉ một field chính.

## 13. DELETE: tưởng an toàn nhưng cần generation

Một timeline:

```text
T0: Entity X generation=3 tồn tại.
T1: Client gửi DELETE X generation=3.
T2: DELETE đã commit, response mất.
T3: Một workflow tạo lại X generation=4.
T4: Client retry DELETE X không có điều kiện.
```

Lần retry tại T4 có thể xóa **entity mới**.

Một command an toàn hơn:

```text
DELETE X IF generation=3 AND expectedRevision=...
```

Hoặc ghi tombstone/versioned deletion và operation receipt. Cần bảo vệ cả late events từ CDC/replay để không hồi sinh generation cũ.

**Tính lũy đẳng theo trạng thái absent không đủ khi ID có thể tái sử dụng hoặc có recreate.**

## 14. CAS và optimistic locking: an toàn hơn nhưng chưa tự cho biết kết quả timeout

Giả sử:

```text
UPDATE order
SET status=PAID, version=8
WHERE version=7
```

Attempt 1 commit, response mất. Attempt 2 thấy `version != 7` và trả `CONDITION_FAILED`.

Hai khả năng:

1. Attempt 1 của chính client đã đổi version thành 8.
2. Writer khác đã đổi version trước đó.

Do đó:

```text
CONDITION_FAILED != PROOF_OF_PRIOR_SUCCESS
```

Cần đọc lại state/operation receipt, kiểm tra status transition và business intent.

Nếu caller muốn đổi `PENDING → PAID`, nó không thể tự tăng expectedVersion và retry mà không kiểm tra state mới. Một order có thể đã `CANCELLED` vì quy tắc khác.

## 15. Transaction body có thể được thực hiện lại

Một số driver hỗ trợ callback transaction và **retry transaction body** với các loại lỗi transient theo protocol.

Sai:

```java
transactionRunner.run(() -> {
    orderRepository.markPaid(orderId);
    paymentProvider.capture(paymentIntentId);
});
```

Nếu callback chạy lại, `paymentProvider.capture()` có thể được gọi nhiều lần. Dù database transaction rollback/commit đúng, side effect bên ngoài không thuộc atomic boundary đó.

Hướng phù hợp:

```text
Database transaction:
    validate order
    update source state
    store outbox PaymentCaptureRequested
    commit

Outbox worker:
    call provider with stable paymentIntentId
    reconcile result
```

**Retry database transaction** và **retry cả nghiệp vụ có external side effects** là hai phạm vi khác nhau.

## 16. Lũy đẳng không đồng nghĩa không có duplicate network attempts

Một client có thể gửi cùng request nhiều lần:

```text
Attempt 1 --> Server
Attempt 2 --> Server
Attempt 3 --> Server
```

Mục tiêu thực tế thường là **at-most-once business effect** trong một phạm vi được định nghĩa, không phải “chỉ có một message đi qua mạng”.

Hệ có thể dùng delivery at-least-once để tăng khả năng phục hồi, với:

- Stable operation ID.
- Atomic deduplication.
- Business command/receipt.
- Reconciliation khi outcome chưa rõ.
- Consumer idempotency cho outbox/CDC.
- Retention đủ cho late retries.

Không tuyên bố exactly-once end-to-end chỉ vì một thành phần broker hoặc SDK có tính năng retryable commands.

## 17. Một công thức kiểm tra từng command

Trước khi bật retry cho một method, lập phiếu:

```yaml
operation:
  name: "reserveInventory"
  type: "write"
  businessIntentId: "reserve-O501-L1"
  command:
    effect: "available -= quantity"
    precondition: "available >= quantity"
  identity:
    stableAcrossAttempts: true
    requestFingerprint: true
  atomicity:
    dedupAndEffectSameCommit: true
  possibleUnknownCommit: true
  safeRetry:
    withoutIdempotency: false
    withSameIdempotencyKey: true
  readback:
    authoritativeLookupByOperationId: true
  errorPolicy:
    validation: "STOP"
    conflict: "REVALIDATE"
    throttled: "BACKOFF"
    timeoutAfterSend: "RECONCILE"
  budget:
    maxAttempts: 3
    totalDeadlineMs: 1500
```

Các giá trị và ngưỡng minh họa, không phải cấu hình của bất kỳ SDK nào. Điều quan trọng là **lũy đẳng được chứng minh theo operation cụ thể**.

## 18. Phân loại trạng thái kết quả thay vì dùng boolean

Hạn chế API:

```java
boolean executeCommand();
```

Khi trả `false`, caller không phân biệt được:

- Validation bị từ chối.
- Business precondition không thỏa.
- Database quá tải.
- Timeout sau commit.
- Có một job đang xử lý.
- Commit đã áp nhưng projection chưa bắt kịp.

Một mô hình tốt hơn:

```text
APPLIED(receipt)
REJECTED(reason)
PENDING(jobId)
UNKNOWN(operationId)
RETRYABLE_TRANSIENT(errorCategory)
```

`RETRYABLE_TRANSIENT` chỉ nên được dùng khi **adapter biết cách retry an toàn theo contract**. Một write timeout sau dispatch thường vẫn thuộc `UNKNOWN` nếu không có cơ chế đảm bảo khác.

## 19. Bảng quyết định xử lý lỗi trong Java

| Kết quả/lỗi | Thường làm gì? | Vì sao? |
| --- | --- | --- |
| Invalid input / schema | Stop | Retry không sửa payload |
| Unauthorized / forbidden | Stop | Không bỏ qua auth để kết nối thành công |
| Duplicate key same operationId | Read verified receipt | Có thể attempt trước đã commit |
| Duplicate key different command | Business conflict | Không được trả success giả |
| CAS version mismatch | Re-read và validate intent | State đã thay đổi |
| Throttling/rate limit | Backoff+jitter trong budget | Tải có thể tạm cao |
| Connect failure trước dispatch chắc chắn | Retry có điều kiện | Attempt này chưa gửi |
| Read timeout sau write | Reconcile/SDK-safe retry với cùng ID | Commit có thể đã xảy ra |
| Unknown transaction commit | Transaction commit recovery protocol | Không tự tạo transaction business mới |
| Node/leader unavailable | Discovery/failover theo protocol | Không hạ consistency ngầm |
| Replica stale trên strong read | Đổi sang authoritative read path | Retry cùng eventual replica chưa chắc đủ |
| Pool acquire timeout | Backpressure/fail fast, chẩn đoán pool | Tăng retry có thể làm queue đầy |
| Client deadline expired | Stop new attempts | Không còn budget; giữ operation outcome nếu UNKNOWN |
| Permanent config/TLS error | Stop và điều tra | Retry vô hạn không sửa cấu hình |

Một exception có thể được đặt tên khác giữa MongoDB, DynamoDB, Cassandra và Redis. Adapter nên chuẩn hóa **ngữ nghĩa**, không chuẩn hóa bằng tìm chuỗi trong exception message.

## 20. Chỉ nên có một chủ sở hữu retry cho mỗi tầng nghiệp vụ

Giả sử:

```text
API gateway:   3 attempts
Service:       3 attempts
Repository:    3 attempts
Driver:        2 attempts
```

Trong một tình huống mọi tầng thực hiện đủ lần:

\[
3 \times 3 \times 3 \times 2 = 54
\]

attempts xuống dependency cho **một yêu cầu đầu vào**.

Trong outage, chúng có thể tạo **retry storm** khiến database nghẽn hơn.

Khuyến nghị:

- Driver xử lý những retry protocol được SDK bảo đảm.
- Service sở hữu business-level retry/reconciliation theo operationId.
- API/gateway không tự retry non-idempotent POST chỉ từ HTTP 5xx.
- Có **retry budget tổng** và deadline truyền xuống từng tầng.
- Log/trace mỗi attempt để biết số lượt thực tế.
- Không cho những tầng độc lập đều dùng maxAttempts mà không phối hợp.

## 21. Retry với exponential backoff và jitter

Một lịch backoff:

\[
B_n = \min(B_{\max}, B_0 \times 2^n)
\]

Trong đó:

- \(B_0\): delay cơ sở.
- \(B_{\max}\): trần delay.
- \(n\): số lần retry đã thực hiện.
- `full jitter`: chọn delay ngẫu nhiên từ 0 đến \(B_n\).

Ví dụ:

```text
base=50 ms
max=800 ms

Retry 1: random 0..50 ms
Retry 2: random 0..100 ms
Retry 3: random 0..200 ms
Retry 4: random 0..400 ms
```

Jitter giảm khả năng hàng nghìn clients đồng thời retry đúng một nhịp. Trong môi trường rất tải, cũng cần **retry budget/token bucket**, vì backoff không tự giới hạn tổng số callers.

**Không backoff để vượt qua conflict nghiệp vụ vĩnh viễn**; khi version mismatch, cần đọc lại và tính lại command nếu domain cho phép.

## 22. Deadline tổng quan trọng hơn từng per-attempt timeout

Ví dụ:

```text
HTTP request deadline:   1200 ms
Driver per-attempt:      1000 ms
Max attempts:            3
Backoff:                 100..200 ms
```

Nếu cho đủ ba attempts, request có thể vượt 3 giây dù API chỉ còn 1,2 giây.

Cần một **overall deadline**:

```text
remaining = deadline - elapsed
if remaining <= 0:
    stop new attempts
else:
    configure next attempt within remaining
```

Khi caller đã hết deadline:

- Đối với read, có thể trả timeout và dừng.
- Đối với write đã dispatch, giữ `UNKNOWN` nếu outcome chưa rõ.
- Durable reconciliation có thể tiếp tục **sau** HTTP deadline.
- Không kéo dài HTTP request vô hạn.
- Không tự hủy operation marker khi client đóng kết nối.

## 23. Dùng đồng hồ đơn điệu cho elapsed time

Trong Java:

```java
long started = System.nanoTime();

long elapsedNanos = System.nanoTime() - started;

long remainingNanos =
        budgetNanos - elapsedNanos;
```

`System.nanoTime()` phù hợp để tính **thời lượng tương đối** trong cùng tiến trình. Không dùng `System.currentTimeMillis()` để đo khoảng chờ chính xác khi wall clock có thể bị chỉnh bởi NTP.

Khi deadline cần sống qua restart hoặc được gửi qua network, không thể truyền raw `nanoTime()` của một máy sang máy khác. Cần timeout budget hoặc mốc thời gian có semantics rõ và tính đến clock uncertainty.

## 24. Java 17: một ví dụ nhỏ chứng minh lost response

Đoạn chương trình sau chạy độc lập bằng Java 17+. Nó mô phỏng **một server giữ operation receipt theo operationId**, commit rồi làm mất response ở lần đầu; client tra lại theo cùng ID để biết đã áp. Đây là mô hình **chỉ trong một JVM**, không thay cho NoSQL transaction/durability thực tế.

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class LostResponseDemo {
    record Command(String operationId, int delta) {}
    record Receipt(String operationId, int resultingCounter) {}

    static final class ToyServer {
        private final Map<String, Receipt> receipts =
                new ConcurrentHashMap<>();
        private int counter = 0;

        synchronized Receipt apply(Command command) {
            Receipt old = receipts.get(command.operationId());
            if (old != null) {
                return old;
            }

            counter += command.delta();
            Receipt result =
                    new Receipt(command.operationId(), counter);
            receipts.put(command.operationId(), result);
            return result;
        }

        synchronized Receipt lookup(String operationId) {
            return receipts.get(operationId);
        }

        synchronized int counter() {
            return counter;
        }
    }

    public static void main(String[] args) {
        ToyServer server = new ToyServer();
        Command command = new Command("increment-op-42", 1);

        // Server đã apply; client giả lập mất ACK.
        server.apply(command);
        System.out.println("Client: TIMEOUT / UNKNOWN");

        // Tra theo operation ID ổn định.
        Receipt receipt = server.lookup(command.operationId());
        System.out.println("Recovered: " + receipt);

        // Kể cả gửi lại cùng ID, không tăng tiếp.
        server.apply(command);
        System.out.println("Counter = " + server.counter());
    }
}
```

Kết quả ý tưởng:

```text
Client: TIMEOUT / UNKNOWN
Recovered: Receipt[operationId=increment-op-42, resultingCounter=1]
Counter = 1
```

### Những giới hạn quan trọng

- `synchronized` chỉ bảo vệ một instance JVM, **không bảo vệ nhiều pods/nodes**.
- `ConcurrentHashMap` không durable sau crash.
- Ví dụ không kiểm tra cùng operationId nhưng payload khác.
- Một NoSQL production cần **atomic effect + dedup receipt** hoặc một transaction/recovery protocol.
- Cần retention đủ dài và tenant-scoped operation identity.
- Nếu command gửi tới payment provider, idempotency phải được thực hiện tại **provider hoặc authority của payment**.

## 25. Fingerprint để chống dùng lại key với payload khác

Nếu client gửi:

```json
{
  "operationId": "op-42",
  "sku": "SKU-A",
  "quantity": 1
}
```

sau đó gửi cùng ID:

```json
{
  "operationId": "op-42",
  "sku": "SKU-B",
  "quantity": 5
}
```

Server không nên trả receipt cũ một cách vô điều kiện, cũng không áp payload mới.

Một contract:

```text
same (tenantId, operationId) + same semantic fingerprint
    -> return old receipt

same (tenantId, operationId) + different fingerprint
    -> IDEMPOTENCY_KEY_REUSE_CONFLICT
```

Fingerprint phải được tạo từ **dữ liệu ngữ nghĩa đã chuẩn hóa**, không chỉ bytes JSON tùy thứ tự field. Khi version API đổi, cần có policy tương thích và lưu schema version.

## 26. Operation ledger và atomic effect

Một record:

```json
{
  "tenantId": "T1",
  "operationId": "reserve-O501-L1",
  "fingerprint": "sha256:...",
  "status": "APPLIED",
  "result": {
    "reservationId": "RSV-501"
  },
  "sourceRevision": 18,
  "createdAt": "2026-11-14T08:00:00Z"
}
```

Lỗi thiết kế thường gặp:

```text
1. Decrement stock -> COMMITTED.
2. Insert ledger marker -> CRASH.
```

Sau đó lookup operationId `NOT_FOUND` dù stock đã giảm.

Muốn lũy đẳng đúng, phải làm một trong những cách phù hợp:

- Lưu marker và effect trong **cùng atomic document/item**.
- Transaction giữa source record và marker trong phạm vi NoSQL hỗ trợ.
- Ledger-first protocol có durable command state và xử lý có điều kiện.
- Append-only ledger làm authority và materialize projection.
- Operation-specific recovery với state machine, fencing và audit.

**GET marker không thấy trên một eventual replica không chứng minh command chưa commit**.

## 27. OperationId phải có vòng đời đủ dài

Giả sử:

```text
Marker TTL:    1 giờ
Queue replay:  3 ngày
Client retry:  tới 2 ngày
```

Sau hai ngày, marker không còn; một message cũ cùng operationId được coi là mới và có thể làm hiệu ứng lặp.

Cần đối chiếu:

- Max client retry window.
- Queue/DLQ retention và replay.
- Provider webhook retry behavior.
- Khả năng job bị dừng nhiều ngày rồi resume.
- Audit/retention theo quy định.
- Unique business identity của domain.
- Delete/recreate entity và generation.

Không chọn TTL chỉ để tiết kiệm storage mà bỏ qua cửa sổ **late retry**. Một số thao tác tài chính cần ledger/uniqueness mạnh hơn marker TTL ngắn.

## 28. Java: phân loại operation trước khi gọi driver

Có thể đưa semantics vào một descriptor thay vì để mọi repository method dùng cùng một retry policy:

```java
public enum CommandSemantics {
    READ_ONLY,
    IDEMPOTENT_STATE_WRITE,
    CONDITIONAL_STATE_WRITE,
    DEDUPLICATED_BUSINESS_WRITE,
    NON_IDEMPOTENT_WRITE,
    MULTI_STEP_WORKFLOW
}

public record OperationDescriptor(
        String operationName,
        CommandSemantics semantics,
        String operationId,
        boolean authoritativeResultLookupSupported
) {}
```

Ví dụ:

```text
getProductById
    -> READ_ONLY

replaceProfileIfVersion
    -> CONDITIONAL_STATE_WRITE

reserveStockWithOperationLedger
    -> DEDUPLICATED_BUSINESS_WRITE

incrementRawCounter
    -> NON_IDEMPOTENT_WRITE

capturePaymentAndConfirmOrder
    -> MULTI_STEP_WORKFLOW
```

Cẩn thận: descriptor là **khai báo**. Một developer đặt `DEDUPLICATED_BUSINESS_WRITE` không tạo ra dedup thực tế. Phải có integration tests với adapter/data store chứng minh atomicity hoặc recovery.

## 29. Java: không nên retry bằng cách bắt `Exception` chung

Ví dụ nguy hiểm:

```java
for (int attempt = 0; attempt < 5; attempt++) {
    try {
        inventoryRepository.decrement(sku, 1);
        return;
    } catch (Exception ignored) {
        Thread.sleep(100);
    }
}
```

Sai ở nhiều điểm:

- Không phân biệt validation, auth, conflict, throttling và timeout.
- Không có operation ID.
- Không biết lệnh đã commit chưa.
- Không có deadline tổng.
- Dùng delay cố định, dễ retry đồng loạt.
- Nuốt exception và mất thông tin điều tra.
- Không rõ repository/driver đã tự retry chưa.
- Nếu thread bị interrupt, code có thể xử lý sai cancellation.

Một lớp retry chuẩn phải nhận **kết quả phân loại từ driver adapter**, không dựa vào `catch(Exception)`.

## 30. Java: một chính sách retry có cấu trúc

Mô hình pseudo-interfaces:

```java
public sealed interface AttemptResult
        permits Applied, Rejected, TransientNoApply, Unknown {
}

public record Applied(String receipt) implements AttemptResult {}
public record Rejected(String reason) implements AttemptResult {}
public record TransientNoApply(String reason)
        implements AttemptResult {}
public record Unknown(String operationId)
        implements AttemptResult {}

@FunctionalInterface
public interface Attempt {
    AttemptResult execute(long remainingNanos) throws Exception;
}
```

Ý nghĩa:

- `Applied`: có bằng chứng commit theo contract.
- `Rejected`: bị từ chối chắc chắn, không sửa trạng thái.
- `TransientNoApply`: chỉ sử dụng khi adapter **chứng minh được** attempt chưa áp hoặc retry được bảo đảm.
- `Unknown`: đã có khả năng commit nhưng chưa đủ bằng chứng.

Không map mọi `SocketTimeoutException` thành `TransientNoApply`. Với write đã dispatch, timeout thường phải được xem là `Unknown`.

## 31. Java: retry loop với deadline và full jitter

Đoạn dưới là **mẫu thuật toán**, yêu cầu các interface trên và một phương thức `lookupByOperationId` ở tầng service. Trong hệ thật cần không-blocking scheduling nếu throughput cao.

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public final class RetryCoordinator {
    private final int maxAttempts = 4;
    private final long baseDelayMs = 40L;
    private final long maxDelayMs = 400L;

    public AttemptResult run(
            Attempt action,
            String operationId,
            Duration budget) throws Exception {

        long started = System.nanoTime();
        long budgetNanos = budget.toNanos();

        for (int attemptNumber = 0;
             attemptNumber < maxAttempts;
             attemptNumber++) {

            long remaining =
                    budgetNanos - (System.nanoTime() - started);

            if (remaining <= 0) {
                return new Unknown(operationId);
            }

            AttemptResult result = action.execute(remaining);

            if (result instanceof Applied
                    || result instanceof Rejected) {
                return result;
            }

            if (result instanceof Unknown) {
                // Không tạo business operation mới.
                // Tra authoritative operationId theo service protocol.
                return result;
            }

            // Chỉ retry khi adapter đã xác định an toàn.
            if (!(result instanceof TransientNoApply)) {
                return new Unknown(operationId);
            }

            if (attemptNumber == maxAttempts - 1) {
                return new Unknown(operationId);
            }

            long cap = Math.min(
                    maxDelayMs,
                    baseDelayMs * (1L << attemptNumber));

            long delay = ThreadLocalRandom.current()
                    .nextLong(cap + 1);

            long left =
                    budgetNanos - (System.nanoTime() - started);

            long delayNanos =
                    Math.min(TimeUnit.MILLISECONDS.toNanos(delay), left);

            if (delayNanos > 0) {
                TimeUnit.NANOSECONDS.sleep(delayNanos);
            }
        }

        return new Unknown(operationId);
    }
}
```

### Hạn chế cần biết

- `TimeUnit.NANOSECONDS.sleep()` có thể bị interrupt; caller phải xử lý đúng.
- Nếu `action.execute()` ném exception, adapter phải map **lỗi đã biết** thành `AttemptResult` hoặc propagate phù hợp; không dùng code trên trực tiếp cho bất kỳ exception nào.
- `maxAttempts` ở đây là **số attempts tổng**, bao gồm lần đầu.
- Không có retry budget chia sẻ giữa nhiều callers.
- Caller phải dừng nếu business intent bị hủy; backend write có thể vẫn commit sau cancellation.
- `UNKNOWN` cần một **durable reconciliation workflow**, không phải chỉ return rồi quên.
- Nếu protocol xác minh một lệnh write đã hoàn tất dù response mất, có thể trả saved receipt; nếu chưa, giữ UNKNOWN.

## 32. Retry loop phải biết SDK đã làm gì

Một adapter có thể được cấu hình:

```text
SDK retries internally: max 3 attempts
Application retries:    max 4 attempts
```

Một operation có thể tạo tới 12 requests xuống backend trong tình huống đủ attempts.

Nên ghi:

```text
app.operationId
app.logicalAttempt
sdk.attemptNumber
targetEndpoint
retryReason
outcome
```

Nếu SDK **tự retry transaction commit hoặc retryable write theo protocol**, việc bọc thêm một vòng gọi business service từ đầu có thể làm mất idempotency/session identity.

Một cách quản lý:

- Dùng retry chính thức của SDK cho những lệnh được hỗ trợ.
- Ứng dụng dùng một retry budget/deadline tổng.
- Business-level retries chỉ dành cho lỗi mà policy/adapter cho phép.
- Reconciliation xử lý riêng những unknown outcomes.
- Không để gateway tự retry POST non-idempotent chỉ vì 502/504.

## 33. Backpressure và connection pool

Một hệ quá tải có thể tạo chuỗi:

```text
Queries chậm
    -> connections bị giữ lâu
    -> pool pending tăng
    -> acquire timeout
    -> app retry
    -> còn nhiều queries chờ hơn
```

Tăng số retries không giải quyết được pool starvation.

Metrics quan trọng:

```text
connection_pool_active
connection_pool_idle
connection_pool_pending
connection_acquire_latency
inflight_requests
db_query_latency_p99
db_throttled_requests
retry_attempts_per_operation
request_queue_wait
```

Cách xử lý có thể là:

- Bounded concurrency.
- Admission control hoặc load shedding.
- Giảm query fan-out/index scan.
- Giảm retry amplification.
- Điều chỉnh pool size theo capacity backend.
- Tách background jobs khỏi foreground requests.
- Fix connection/cursor leaks.

**Pool timeout ở Java không tự chứng minh NoSQL node đã chết.**

## 34. MongoDB Java Driver: lệnh nào retry được?

MongoDB Java Driver có cơ chế retryable reads/writes theo **topology, phiên bản server/driver, session và loại operation hỗ trợ**. Không mặc định mọi write đều có semantics giống nhau.

Những điều cần xác định:

1. `retryReads`/`retryWrites` có được bật trong kết nối đang chạy không?
2. Operation cụ thể có thuộc tập retryable theo tài liệu không?
3. Có read/write concern phù hợp không?
4. Lỗi xảy ra trong transaction body hay ở commit?
5. SDK có retry theo session/statement identity để tránh double-apply không?
6. Business command có side effect ngoài MongoDB không?

Ví dụ connection string minh họa:

```text
mongodb://db1.example:27017,db2.example:27017/mydb?retryWrites=true&retryReads=true
```

Không dùng ví dụ hostname cho production; cấu hình topology, TLS, credentials, server selection và timeout cần quản lý riêng. Một flag retryable write không biến mọi **multi-step business workflow** thành exactly-once.

## 35. MongoDB: `updateOne` với CAS và operation ID

Ví dụ Java Driver theo ý tưởng API:

```java
Bson filter = Filters.and(
    Filters.eq("_id", orderId),
    Filters.eq("version", expectedVersion),
    Filters.eq("status", "PENDING")
);

Bson update = Updates.combine(
    Updates.set("status", "PAID"),
    Updates.inc("version", 1),
    Updates.set("lastOperationId", operationId)
);

UpdateResult result =
        orders.updateOne(filter, update);

if (result.getMatchedCount() == 0) {
    // Có thể version/status đã thay đổi.
    // Cần authoritative lookup và business revalidation.
}
```

`lastOperationId` trên một document **không phải ledger đầy đủ** nếu nhiều operations có thể ghi đè nó. Sau timeout, một writer khác có thể thay giá trị và khiến bạn không nhận diện được command cũ. Với yêu cầu không double-charge, cần idempotency record/transaction hoặc domain identity mạnh hơn.

### Retry sau network timeout

Nếu write đã dispatch, không chỉ làm:

```java
orders.updateOne(filter, update);
```

lần nữa bằng một vòng `catch` mới và coi `matchedCount=0` là lỗi. Cần xét **MongoDB driver retryable write support** và **operation receipt** theo hợp đồng ứng dụng.

## 36. MongoDB: tăng counter và `$inc`

Một update:

```java
orders.updateOne(
    Filters.eq("_id", orderId),
    Updates.inc("retryCount", 1)
);
```

Về mặt toán học, `$inc` không lũy đẳng nếu bị thực thi hai lần. MongoDB có retryable-write protocol cho **những operation được hỗ trợ và điều kiện phù hợp**, có thể tránh áp trùng trong phạm vi đó; nhưng **một vòng gọi ứng dụng mới với session/operation identity khác không tự được bảo vệ**.

Do đó:

- Phân biệt driver-level retry của cùng operation với application-level business retry.
- Không suy từ `$inc` rằng có thể retry mù.
- Nếu counter là business-effect critical, dùng stable eventId/operation ledger.
- Nếu counter chỉ là telemetry, có thể chấp nhận sai số trong contract cụ thể.
- Không bỏ qua `UnknownTransactionCommitResult` nếu có transaction.

## 37. MongoDB: transaction commit outcome chưa xác định

Trong MongoDB, cần phân biệt những error labels theo driver/transaction API, ví dụ:

```text
TransientTransactionError
UnknownTransactionCommitResult
```

Một lỗi trong transaction body có thể cần retry transaction theo protocol; một lỗi khi commit có thể đòi **retry commit/recovery** thay vì chạy lại business intent từ đầu.

Ví dụ nguy hiểm:

```text
MongoDB transaction:
    Update order
    Call external payment
    Insert operation receipt
```

Nếu callback transaction bị retry, payment có thể được gọi hai lần.

Một thiết kế phù hợp:

```text
Source transaction:
    validate state
    update order
    insert outbox event with stable eventId
COMMIT

Worker:
    call payment with stable paymentIntentId
    reconcile unknown response
```

Phần Java cần dùng đúng `ClientSession`, transaction API và error labels của **phiên bản driver đang chạy**, không copy một vòng retry chung.

## 38. DynamoDB: điều kiện ghi và AWS SDK for Java

Một số API quan trọng:

```text
GetItem
PutItem
UpdateItem
DeleteItem
TransactWriteItems
TransactGetItems
```

`GetItem` thường là read-only, nhưng phải giữ **read consistency** đúng. Một `UpdateItem` với `ADD counter :delta` là phép cộng, không lũy đẳng về trạng thái. Một `PutItem` với dữ liệu cố định có thể lũy đẳng về một item trong điều kiện đơn giản, nhưng có thể ghi đè concurrent data.

Ví dụ ý tưởng condition:

```text
UpdateItem:
    Key = inventory item
    ConditionExpression:
        available >= :quantity
        AND attribute_not_exists(appliedOperationId)
    UpdateExpression:
        SET available = available - :quantity
            appliedOperationId = :operationId
```

Đây là **pseudo-expression** minh họa atomic compare-and-write; không phải một pattern hoàn chỉnh để lưu nhiều operation IDs. `attribute_not_exists(appliedOperationId)` chỉ bảo vệ một marker hiện có, không có khả năng dedup lịch sử nhiều lệnh nếu field bị ghi đè. Với nhiều operations cần ledger/transaction/aggregate phù hợp.

## 39. DynamoDB: `TransactWriteItems` và idempotency token

DynamoDB cung cấp transaction APIs có cơ chế idempotency theo **client request token** trong một cửa sổ được tài liệu định nghĩa. Khi retry một transaction request, cần:

- Giữ token ổn định.
- Giữ payload không đổi theo hợp đồng.
- Kiểm tra token expiration window.
- Không xem token ngắn hạn thay cho business operation ledger lâu dài.
- Với timeout sau dispatch, không tạo token mới mù.
- Tra authoritative base record hoặc status ledger nếu có.
- Không dùng GSI eventual `NOT_FOUND` làm proof chưa commit.

AWS SDK retry strategy có những chế độ/semantics thay đổi theo phiên bản. Cần cấu hình **max attempts, adaptive/standard behavior và timeout** một cách nhất quán; SDK đã retry không có nghĩa ứng dụng nên gọi lại toàn bộ business workflow.

## 40. DynamoDB: throttling không giống conditional failure

Hai kết quả:

```text
ConditionalCheckFailedException
```

và:

```text
ProvisionedThroughputExceeded /
Throttling-related error
```

có ý nghĩa khác.

- Condition failed: request không thỏa điều kiện tại state được đánh giá; phải re-read/revalidate.
- Throttling: service/partition đang giới hạn; có thể retry bounded với jitter nếu operation an toàn.
- Timeout sau dispatch: có thể unknown outcome; phải dùng idempotency/receipt.

Một table còn capacity tổng nhưng có hot partition key vẫn có thể throttling; **tăng app retries** có thể làm hot key xấu hơn. Cần điều tra partition-key distribution và consumed capacity.

## 41. Cassandra/ScyllaDB Java Driver: đánh dấu idempotence phải có cơ sở

Một số Java driver cho CQL cung cấp **idempotence metadata** trên statement để retry policy quyết định có thể thử lại.

Ví dụ dạng API của Java Driver 4.x:

```java
SimpleStatement select = SimpleStatement.builder(
        "SELECT * FROM orders_by_id " +
        "WHERE tenant_id = ? AND order_id = ?")
    .addPositionalValues(tenantId, orderId)
    .setIdempotent(true)
    .build();

ResultSet result = session.execute(select);
```

Đoạn code là ví dụ API pattern; cần imports và driver version tương ứng.

Một mutation delta:

```java
SimpleStatement increment = SimpleStatement.builder(
        "UPDATE counters SET value = value + 1 " +
        "WHERE tenant_id = ? AND counter_id = ?")
    .addPositionalValues(tenantId, counterId)
    .setIdempotent(false)
    .build();
```

**Lưu ý kỹ thuật:** CQL thường không hỗ trợ phép `value = value + 1` trên mọi kiểu cột thường; với counter columns, cú pháp và quy tắc riêng. Đoạn minh họa cho thấy **quyết định không-idempotent**, không phải DDL/câu lệnh tổng quát cho mọi bảng. Không đưa một mutation có side effect tích lũy vào driver retry policy như thể an toàn.

### Điều thực sự quan trọng

`.setIdempotent(true)` là **metadata khai báo cho driver**, không tự làm lệnh trở nên lũy đẳng. Đánh dấu sai có thể khiến driver retry và áp mutation hai lần trong lỗi timeout/connection.

## 42. CQL: `INSERT`, `UPDATE`, `DELETE` phải xét timestamp, TTL và concurrency

Trong Cassandra/ScyllaDB, nhiều mutations theo kiểu *upsert* có thể có kết quả cuối gần như giống nhau khi lặp lại trong một số điều kiện. Nhưng cần xét:

- Write timestamp và last-write-wins reconciliation.
- Client-generated vs server-generated timestamps.
- TTL làm thay đổi expiry nếu retry ở thời điểm khác.
- Counter update là đặc biệt, không-idempotent.
- Collections append/prepend và mutation semantics.
- LWT/conditional write.
- Concurrent writers cùng partition.
- Tombstone và delete resurrection.
- Consistency level và timeout ACK.
- Batch atomicity/semantics không tương đương transaction tùy ý.

Không kết luận lệnh `INSERT` luôn an toàn chỉ vì CQL có cú pháp `INSERT` mà không có unique SQL constraint kiểu quan hệ.

## 43. CQL LWT: `[applied] = false` không giống timeout

Ví dụ:

```sql
UPDATE inventory_by_sku
SET reserved = ?, revision = ?
WHERE tenant_id = ? AND sku = ?
IF revision = ?;
```

Nếu trả:

```text
[applied] = false
```

đây là kết quả điều kiện không thỏa theo protocol; caller cần đọc lại và đánh giá intent.

Nếu client nhận timeout khi LWT đang chạy, có thể có **unknown outcome**. Retry phải tuân theo driver/consistency/idempotency semantics và business dedup, không tự coi CAS chưa được thực hiện.

Nếu batch/transaction liên quan nhiều partitions, đừng giả rằng LWT trên một partition bảo vệ invariants nhiều entities.

## 44. Redis Java client: `SET` và `INCR` khác nhau

Với Redis qua Lettuce/Jedis hoặc client tương ứng:

```text
SET product:42:name "Example"
```

có thể lũy đẳng về field value khi không có concurrency và side effects.

```text
INCR product:42:views
```

không lũy đẳng. Nếu timeout xảy ra sau khi Redis xử lý, phát lại `INCR` gây tăng hai lần.

Redis còn có:

- `SET ... NX/XX` với conditional semantics.
- `HSET` theo field.
- `LPUSH/RPUSH` gây thêm phần tử.
- `SADD` có membership semantics.
- `ZADD` tùy option và score.
- `DEL` với nguy cơ recreate.
- Lua script atomic execution trong phạm vi Redis command processing.
- Redis Cluster redirects `MOVED/ASK`.
- Replication/failover/persistence guarantees tùy cấu hình.

**Auto reconnect không tự biến một lệnh đang chờ response thành exactly-once operation**. Cần hiểu client behavior đối với pending commands và replay.

## 45. Redis Lua: atomic dedup + tăng bộ đếm

Ví dụ concept với hai keys:

```lua
-- KEYS[1]: counter key
-- KEYS[2]: operation dedup key
-- ARGV[1]: delta
-- ARGV[2]: dedup TTL seconds
-- ARGV[3]: fingerprint

local marker = redis.call("GET", KEYS[2])
if marker then
    if marker ~= ARGV[3] then
        return { "REUSE_CONFLICT" }
    end
    return { "ALREADY_APPLIED" }
end

local delta = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
if not delta or delta <= 0 or not ttl or ttl <= 0 then
    return { "INVALID_ARGUMENT" }
end

redis.call("INCRBY", KEYS[1], delta)
redis.call("SET", KEYS[2], ARGV[3], "EX", ttl)
return { "APPLIED" }
```

Điều cần kiểm tra:

- Trong Redis Cluster, tất cả keys mà script truy cập phải thỏa hash-slot constraint.
- Marker TTL phải bao phủ replay window.
- Same operationId/different payload phải bị chặn.
- Script atomic ở cấp thực thi Redis, **không đồng nghĩa durable exactly-once qua crash/failover**.
- Nếu payment/inventory có yêu cầu chặt, authority/ledger cần có bảo đảm bền vững phù hợp.
- Khi marker expired, late retries vẫn có nguy cơ double increment.

Không dùng script này như một giải pháp tài chính production mà chưa xem durability, failover và business audit.

## 46. Driver-level retry và business-level idempotency là hai lớp

Một Java driver có thể làm:

```text
Retry same network operation / session identity.
```

Ứng dụng làm:

```text
Retry business command with operationId.
```

Sự khác biệt:

- Driver có thể có **protocol-level dedup** cho một tập lệnh hỗ trợ.
- Ứng dụng có thể có nhiều bước qua database, broker, email, provider.
- Một transaction callback có thể chạy lại.
- Một command sau timeout có thể bị gửi bởi một API pod khác.
- Webhook/event redelivery có thể đến vài giờ/ngày sau.

Không dựa vào driver-only retry để thay thế **stable business operation identity và audit** khi nghiệp vụ yêu cầu không có duplicate effects.

## 47. Status lookup sau UNKNOWN phải đọc đúng nơi

Một lệnh đã commit vào source, nhưng một read model eventual chưa cập nhật:

```text
Authoritative source:
    order O-501 status=PAID.

Search/GSI/read projection:
    order O-501 status=PENDING.
```

Nếu Java lookup projection và thấy PENDING, nó không được kết luận payment chưa xảy ra rồi gọi provider thêm lần nữa.

Status query phải có:

- Stable operationId.
- Tenant/user scope.
- Authority/read consistency phù hợp.
- Revision/receipt hoặc provider reference.
- Phân biệt `NOT_FOUND`, `UNAVAILABLE`, `STALE` và `PENDING`.
- Retention của operation ledger.
- Không phụ thuộc một search index asynchronous để quyết định commit.

**Nhiều lần `GET` từ cùng replica stale không làm nó trở thành nguồn chứng cứ mạnh hơn.**

## 48. Không kết luận từ state hiện tại nếu nhiều writers có thể tạo cùng kết quả

Ví dụ counter:

```text
Before: balance=100.

My increment +1 -> timeout.

After: balance=101.
```

`101` không chứng minh chính operation của bạn đã commit; có thể một writer khác đã cộng 1, còn operation của bạn chưa chạy.

Cần:

- Operation ledger.
- Transaction/commit receipt.
- Unique event/charge/reservation ID.
- Source version có liên hệ với operation ID.
- Đối soát với provider có thẩm quyền nếu đó là external effect.

**State equality khác operation identity.**

## 49. Một chính sách retry theo nhóm API

| API | Hợp đồng | Chính sách mẫu |
| --- | --- | --- |
| `GET /products/{id}` | Eventual read được phép | Retry transient có deadline, backoff |
| `GET /payments/{id}` | Authoritative status | Retry nhưng giữ read consistency và scope |
| `POST /orders` | Tạo đơn đúng một lần theo intent | Stable operationId + conditional insert |
| `PATCH /orders/{id}/status` | Transition có version | CAS + re-read/revalidate |
| `POST /inventory/reserve` | Không trừ stock hai lần | Atomic dedup + source receipt |
| `POST /payments/capture` | Không charge hai lần | Provider idempotency + reconcile |
| `POST /notifications/send` | Không spam người dùng | Delivery key/dedup hoặc at-least-once policy rõ |
| `POST /counters/increment` | Increment per event | EventId + dedup; nếu telemetry có thể chấp nhận sai số |
| `DELETE /users/{id}` | Không xóa thế hệ mới | Generation guard + tombstone |
| `POST /batch-import` | Có thể partial | Per-row stable identity và progress ledger |

Bảng này là ví dụ. Một sản phẩm có thể chấp nhận đếm page views xấp xỉ nhưng **không thể chấp nhận thanh toán xấp xỉ**. Retry policy cần dựa trên business correctness contract.

## 50. Phân biệt HTTP 429, 409, 500, 503 và 504

Những mã HTTP thường là **biểu hiện ở API layer**, không thay thế DB error code:

- `400`: payload không hợp lệ, thường sửa request.
- `401/403`: auth/authorization, không retry blind.
- `409/412`: business/version conflict, cần revalidate.
- `429`: throttling/quota, có thể backoff nếu safe.
- `500`: nhiều nguyên nhân; write có thể đã commit trước khi response lỗi.
- `503`: service/authority không sẵn sàng; cần giữ outcome semantics.
- `504`: gateway hết thời gian chờ; backend có thể tiếp tục.

Không viết:

```java
if (status >= 500) {
    retryPaymentWithNewId();
}
```

Một code `504` không chứng minh provider chưa charge. Trả UI “thanh toán thất bại” chỉ vì timeout có thể khiến người dùng tạo duplicate operation.

## 51. Retry có thể biến một sự cố nhỏ thành cascading failure

Ví dụ:

```text
Normal traffic:       10.000 ops/s.
Server slows down.
60% requests timeout.
Every client retries 3 times.
```

Trong worst-case nếu mỗi failed request đều tạo đủ retries, tải thêm:

\[
10.000 \times 0{,}6 \times 3 = 18.000
\]

requests/giây, tổng khoảng 28.000 attempts/giây — chưa tính retries tiếp tục thất bại, những lớp khác và concurrency backlog. Đây là tính toán minh họa.

Biện pháp:

- Retry budget chung.
- Jitter.
- Bounded concurrency.
- Queue/worker capacity limits.
- Load shedding/circuit breaker.
- Per-tenant throttling.
- Giảm timeout do query scan/compaction.
- Fail fast khi không có quorum thay vì gửi nhiều lần ngay lập tức.

**Retry không tạo lại node/quorum bị mất; nó chỉ tăng số attempts.**

## 52. Circuit breaker không giải quyết UNKNOWN commit

Circuit breaker thường:

```text
CLOSED -> OPEN -> HALF_OPEN -> CLOSED
```

Nó giúp không gọi dependency đang suy giảm liên tục. Nhưng:

- Breaker OPEN không chứng minh những writes đang chạy chưa commit.
- Một version conflict không nên tính như outage của database.
- Fallback cache không hợp với authoritative payment/inventory.
- Khi HALF_OPEN, probe phải giới hạn concurrency.
- Nếu breaker mở sau một timeout, operation ledger/reconciliation vẫn phải tồn tại.

Circuit breaker bảo vệ **availability/capacity**; operationId và commit protocol bảo vệ **correctness**.

## 53. Retry sau leader failover

Timeline:

```text
T0: Java gửi write tới leader L1.
T1: L1 có thể commit theo protocol.
T2: L1 stepdown/crash; socket đóng.
T3: Driver chọn leader L2.
T4: Ứng dụng retry.
```

Cần kiểm tra:

- Write concern/commit level của lần trước.
- Có session/operation identity được giữ không?
- L2 có dữ liệu đã commit không?
- Có stale leader writes bị fencing không?
- Retryable write/transaction API chính thức được hỗ trợ không?
- Có external side effect ngoài database không?

Không tự chuyển mọi write sang một replica chỉ vì nó còn TCP port. **Quyền ghi và consistency contract** là quyết định của database protocol, không phải health-check boolean.

## 54. Retry trong network partition một phần

Một client ở AZ A có thể không đến được primary, trong khi client AZ B vẫn kết nối bình thường.

```text
Client A ----X----> Primary
Client B ---------> Primary
```

Hoặc coordinator có thể không tới một subset replicas, dù client kết nối coordinator bình thường.

Các điều cần tránh:

- Tuyên bố toàn cluster chết chỉ từ một client timeout.
- Hạ `QUORUM` thành `ONE` trái contract để ghi cho được.
- Chuyển strong read sang stale replica không công bố.
- Cho hai Regions nhận authoritative writes mâu thuẫn nếu business cần uniqueness.
- Tăng retry liên tục cùng network path hỏng.

Khi không thể xác minh authority, thao tác quan trọng có thể cần `UNKNOWN`, `PENDING` có chứng cứ, hoặc fail-closed/`UNAVAILABLE`.

## 55. Lập bảng evidence cho một attempt

Một Java trace hữu ích:

```text
traceId: req-781
operationId: reserve-O501-L1
logicalAttempt: 2
sdkAttempt: 1
dbOperation: conditionalReserve
targetGroup: write-primary
dispatchStarted: true
responseReceived: false
errorCategory: SOCKET_READ_TIMEOUT
elapsedMs: 550
commitOutcome: UNKNOWN
nextAction: STATUS_LOOKUP
```

Không đưa password, token hoặc payload nhạy cảm vào log. Có thể dùng IDs cụ thể trong trace có access control, nhưng **không dùng operationId làm metric label** có cardinality vô hạn.

Ghi cả driver-level attempts để thấy trường hợp:

```text
one HTTP request -> multiple SDK attempts -> one unknown outcome
```

## 56. Metrics để đánh giá chính sách retry

```text
java_db_requests_total
java_db_attempts_total
java_db_attempts_per_operation
java_db_timeout_connect_total
java_db_timeout_read_total
java_db_pool_acquire_timeout_total
java_db_server_selection_failures_total

java_db_write_conflicts_total
java_db_throttling_total
java_db_retry_attempts_total
java_db_retry_budget_exhausted_total
java_db_deadline_exceeded_total

operation_applied_total
operation_rejected_total
operation_unknown_total
operation_reconciled_total
operation_reconcile_oldest_age_seconds
idempotency_duplicate_suppressed_total
idempotency_key_reuse_conflicts_total
duplicate_business_effect_detected_total

driver_pool_active
driver_pool_pending
node_or_partition_hotspot_ratio
replica_lag_seconds
end_to_end_request_latency_p95_p99
```

Tên chỉ là ví dụ thiết kế observability, không khẳng định SDK có sẵn.

Phân nhóm theo operation class, error class, client region, tenant tier và backend pool; operationId cụ thể thuộc log/trace/ledger, không nên làm một time series cho mỗi ID.

## 57. Java: đưa deadline xuống driver nhưng giữ budget chung

Một mô hình gọi:

```java
Duration remaining = deadline.remaining();

if (remaining.isZero() || remaining.isNegative()) {
    return OperationStatus.unknown(operationId);
}

DriverRequest request = requestFactory.create(
        command,
        remaining);
```

Đây là pseudocode vì các driver khác nhau. Cần:

- Đảm bảo per-attempt timeout không vượt remaining.
- Truyền cancellation hợp lý.
- Tránh `Duration` âm/overflow.
- Đảm bảo retry delay nằm trong budget.
- Phân biệt request timeout với reconciliation deadline.
- Cấu hình driver pool/connect/socket/server-selection timeouts không mâu thuẫn.

Nếu HTTP deadline hết lúc backend đã dispatch, workflow idempotency/reconciliation vẫn phải có thể tiếp tục.

## 58. Retry read với cursor và pagination

Một query:

```text
LIST orders WHERE customerId=C1
ORDER BY createdAt DESC
LIMIT 20
```

sau khi trả trang 1, request trang 2 bị timeout. Retry cùng cursor có thể không tạo side effect, nhưng dữ liệu có thể thay đổi giữa hai trang.

Các nguy cơ:

- Một order mới chen vào làm offset pagination trùng/bỏ record.
- Một order đổi sort field.
- Read replica chưa bắt kịp.
- Cursor đã hết hạn.
- Query fan-out khiến p99 tăng.
- Client retry và append kết quả trùng vào danh sách.

Cần stable cursor/keyset pagination hoặc snapshot semantics theo contract; client cũng cần dedup UI theo entity identity.

**Read idempotency không đồng nghĩa snapshot consistency của nhiều requests.**

## 59. Batch write: kiểm tra từng phần tử

Một lệnh batch có thể gặp:

```text
Item A: committed
Item B: committed
Item C: not applied
Response: timeout
```

Một số APIs hỗ trợ atomic batch theo phạm vi nhất định, một số trả **unprocessed items**, một số chỉ bảo đảm từng item.

Nếu retry cả batch mù mà có increment/append:

```text
A: applied twice
B: applied twice
C: applied once
```

Cần:

- Xác định transaction/batch semantics thật.
- Stable item/operation IDs.
- Per-item receipt hoặc progress ledger nếu batch partial.
- Retry chỉ unprocessed items khi API cho biết an toàn.
- Phân biệt batch-level timeout và per-item rejection.
- Không giả batch là serializable transaction xuyên partitions.

## 60. Java async APIs và retry song song

Với `CompletableFuture` hoặc reactive streams, một lỗi có thể đến **sau** khi caller đã chuyển trạng thái.

Ví dụ:

```text
Attempt A sent.
Client deadline expires.
Attempt B triggered by another layer.
Attempt A later commits.
Attempt B also commits.
```

Phải có **same operationId + atomic dedup**. Ngoài ra:

- Không cho retry overlap nếu không cần thiết.
- Nếu dùng hedged read requests, phân biệt với write.
- Không start write speculation sang nhiều nodes nếu protocol không bảo đảm.
- Chỉ cancel future không đủ fence server-side request.
- Trace từng attempt, nhưng gắn cùng business operation.
- Worker lease phải có fencing để stale worker không ghi đè owner mới.

Một pattern async an toàn là **completion stage cho kết quả hiện tại** kết hợp **durable operation status** dùng cho reconciliation lâu hơn.

## 61. Một bài test để chứng minh không lũy đẳng

Dữ liệu ban đầu:

```text
counter=10
operationId=op-1
```

Kịch bản:

```text
1. Server INCR counter.
2. Server commit.
3. Fault proxy chặn response.
4. Java nhận timeout.
5. Java retry lệnh.
```

**Nếu counter=12**, retry policy đã tạo duplicate effect.

**Nếu counter=11 và có operation receipt đúng**, hệ đã áp một lần trong phạm vi test.

Không mock method “nếu lỗi thì ném exception” trước khi mutation chạy, vì test đó **không mô phỏng lỗi sau commit**.

## 62. Một bài test cho CAS timeout

```text
Initial order version=7, PENDING.

Attempt A:
    CAS version 7 -> PAID version 8.
    Commit ACK lost.

Attempt B:
    Retry same CAS version 7.
    Returns applied=false.
```

Câu hỏi test:

- Có operationId/receipt chứng minh A đã commit không?
- Nếu một writer C cũng có thể đổi version, làm sao phân biệt C và A?
- Hệ có trả `APPLIED` cho A dựa trên bằng chứng không?
- Có side effect payment được lặp không?
- Version conflict có bị hiểu nhầm là “A không bao giờ chạy” không?

Một test tốt không chỉ assert `version==8`, mà kiểm tra **operation identity** và business workflow.

## 63. Fault injection: bộ kịch bản tối thiểu

| Mã | Lỗi được chèn | Điều phải được kiểm chứng |
| --- | --- | --- |
| F01 | Pool acquire timeout trước dispatch | Không nhận nhầm là commit unknown khi chắc chưa gửi |
| F02 | Connect refused | Có policy retry/failover theo authority |
| F03 | Response drop sau successful write commit | Không duplicate effect |
| F04 | Database write đã reject, response drop | Unknown được reconcile thay vì success giả |
| F05 | Throttling liên tục | Bounded attempts, backoff+jitter |
| F06 | Version mismatch | Re-read/revalidate, không retry blind |
| F07 | Increment timeout | Idempotency marker hoặc chấp nhận sai số theo contract |
| F08 | Insert response lost | Không tạo ID mới |
| F09 | Delete/recreate rồi retry delete | Không xóa generation mới |
| F10 | Transaction commit timeout | Driver commit recovery protocol |
| F11 | Leader failover ngay sau dispatch | Không stale-owner write, outcome traceable |
| F12 | Partial network partition | Không downgrade consistency |
| F13 | Driver retry + app retry | Tổng attempts nằm trong budget |
| F14 | Worker crash sau side effect trước ACK queue | Redelivery idempotent |
| F15 | Provider charge success, response lost | Same intent ID và lookup |
| F16 | Status lookup từ eventual replica stale | Không kết luận absent giả |
| F17 | Marker TTL hết trước queue replay | Phát hiện duplicate risk |
| F18 | Two concurrent attempts same operationId | Atomic dedup, một business effect |
| F19 | Same operationId, different payload | Fingerprint reuse conflict |
| F20 | Client deadline/cancel sau dispatch | Không giả server rollback |
| F21 | Batch partial success | Per-item retry/reconcile |
| F22 | Redis failover sau Lua script | Đối chiếu durability/receipt policy |
| F23 | CQL timeout ở consistency level cụ thể | Không suy chắc chắn no-apply |
| F24 | GSI/search lag | Authoritative lookup vẫn trả đúng |

Test môi trường staging/CI hoặc một fault harness được phê duyệt; không chủ động gây hỏng giao dịch người dùng thật.

## 64. Bảng acceptance criteria

| Mã | Tiêu chí | Bằng chứng |
| --- | --- | --- |
| AC-01 | Mỗi command có đánh giá lũy đẳng rõ | Command semantics inventory |
| AC-02 | Không retry validation/auth rejection | Negative tests |
| AC-03 | CAS conflict không bị retry mù | Concurrent update test |
| AC-04 | Timeout sau commit không tạo duplicate effect | Response-drop test |
| AC-05 | Same operationId/different payload bị chặn | Fingerprint conflict test |
| AC-06 | OperationId được giữ qua retry và restart | Integration test |
| AC-07 | Ledger/marker đủ atomic với effect | Crash boundary test |
| AC-08 | Unknown commit có reconciliation | Status lookup/recovery test |
| AC-09 | Absent trên eventual read không thành REJECTED | Stale replica test |
| AC-10 | SDK retry được tính trong tổng attempts | Instrumentation test |
| AC-11 | Có max attempts và overall deadline | Retry exhaustion test |
| AC-12 | Retry dùng jitter và bounded concurrency | Load test |
| AC-13 | Throttling không gây retry storm | Fault/load test |
| AC-14 | Đổi leader không tạo stale authority write | Failover/fencing test |
| AC-15 | Read retry giữ consistency contract | Read-after-write test |
| AC-16 | Delete retry không xóa generation mới | Delete/recreate test |
| AC-17 | Batch partial results được xử lý riêng | Partial batch test |
| AC-18 | Provider timeout không gây duplicate payment | Provider sandbox receipt audit |
| AC-19 | Worker redelivery không nhân đôi events/side effects | Queue crash test |
| AC-20 | Idempotency retention đủ replay window | Delayed replay test |
| AC-21 | Metrics phân biệt connect/read/pool/commit unknown | Observability drill |
| AC-22 | Lỗi khiến UNKNOWN không bị hiển thị thành FAILED | API/UI contract test |
| AC-23 | Không rò rỉ dữ liệu khác tenant khi lookup operation | Authorization test |
| AC-24 | Tài liệu cấu hình timeout phản ánh driver version | Configuration review |
| AC-25 | Có runbook xử lý unknown/reconcile backlog | Incident drill |

Các ngưỡng hiệu năng và cửa sổ retention phải được đặt theo SLO, workload và durability contract của sản phẩm.

## 65. Bài tập 1: phân loại lũy đẳng

Cho danh sách lệnh:

```text
A. GET user by ID
B. SET user.name = "An"
C. INCR loginCount by 1
D. INSERT order with server-generated ID on every attempt
E. INSERT order with stable orderId and unique key
F. DELETE user by ID without generation guard
G. CAS status from PENDING to PAID when version=7
H. SADD "friend:100:group", memberId=42
I. APPEND audit record with new timestamp
J. Capture payment with stable provider idempotency key
```

Yêu cầu phân loại:

1. Trạng thái cuối có lũy đẳng không?
2. Có concurrency hazard không?
3. Timeout sau commit có gây outcome unknown không?
4. Cần condition/operationId/ledger nào?
5. Driver retry tự động có đủ không?

**Gợi ý:** A read-only; B có thể stale overwrite; C, D, I không lũy đẳng; E cần unique identity/readback; F cần generation; G cần operation receipt nếu commit timeout; H set membership có điều kiện; J cần provider contract và reconciliation.

## 66. Bài tập 2: sửa một vòng retry nguy hiểm

Code:

```java
void increaseStock(String sku) throws Exception {
    for (int i = 0; i < 10; i++) {
        try {
            db.increment(sku, 1);
            return;
        } catch (Exception e) {
            Thread.sleep(50);
        }
    }
}
```

Hãy sửa thiết kế theo các yêu cầu:

- `operationId` được tạo trước và giữ qua retries.
- Dedup và increment phải atomic.
- Phân biệt validation, throttling, timeout.
- Timeout sau dispatch phải tra ledger.
- Backoff+jitter có deadline và maxAttempts.
- Không retry sau cancellation.
- Có metrics `attemptsPerOperation` và `unknownOutcome`.
- Không gọi cả business workflow lại nếu SDK đang retry theo protocol.

**Gợi ý:** thay method `increment` bằng `applyIncrementOnce(operationId, sku, delta)` có receipt và repository semantics rõ.

## 67. Bài tập 3: xếp timeout theo tầng

Một Java API có:

```text
HTTP deadline:             1000 ms
Driver connect timeout:    2000 ms
Driver request timeout:    1500 ms
Application retry:         3 attempts
Base backoff:              100 ms
```

Hãy phân tích:

- Có khả năng request vượt HTTP deadline không?
- Backend có thể commit sau khi HTTP trả 504 không?
- Nếu client retry với operationId mới, rủi ro gì?
- Cần đặt overall budget và per-attempt timeout thế nào?
- Khi client không còn chờ, reconciliation có cần tiếp tục không?

Đáp án tốt phải phân biệt **deadline của response** và **lifecycle của command đã dispatch**.

## 68. Bài tập 4: Cassandra idempotence metadata

Hai statements CQL:

```sql
SELECT * FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

và:

```sql
UPDATE inventory_counter
SET value = value + 1
WHERE tenant_id = ? AND sku = ?;
```

Yêu cầu:

1. Statement nào được khai báo idempotent theo semantics?
2. Vì sao statement thứ hai không mặc định an toàn?
3. Nếu có LWT/transaction wrapper, còn cần operationId không?
4. Nếu dùng TTL hoặc timestamp, retry có thể thay đổi outcome ra sao?
5. Vì sao `.setIdempotent(true)` không phải biện pháp tự động bảo vệ dữ liệu?

Cần xem cả CQL driver version và loại cột: counter có quy tắc riêng.

## 69. Bài tập 5: MongoDB transaction callback

Giả sử:

```text
withTransaction callback:
    update order to PAID
    call paymentProvider.capture
    insert outbox
```

Yêu cầu:

- Chỉ ra nơi một external side effect có thể lặp.
- Đề xuất cấu trúc nguồn+outbox.
- Giải thích xử lý `UnknownTransactionCommitResult`.
- Định nghĩa paymentIntentId và operationId.
- Viết một test drop response sau provider capture.
- Chỉ ra điểm cần dừng để đối soát thay vì tạo lệnh mới.

## 70. Bài tập 6: Redis và TTL của marker

Thiết kế:

```text
INCRBY counter 1
SET dedup:op42 1 EX 600
```

Hãy giải thích:

- Vì sao hai command rời nhau không atomic?
- Crash giữa hai lệnh gây hậu quả gì?
- Lua script giải quyết phần nào?
- Nếu marker hết sau 10 phút nhưng replay tới sau 1 ngày, rủi ro gì?
- Với Redis Cluster cần điều kiện hash slot nào?
- Vì sao Lua atomic không tự bảo đảm durability qua failover?

## 71. Một runbook khi Java service tăng timeout và retry

### Pha A — Giữ an toàn cho dữ liệu

1. Xác định những operations có side effect không lũy đẳng.
2. Giữ operation IDs, receipts và idempotency markers.
3. Không dùng HTTP timeout để kết luận payment/stock write thất bại.
4. Tắt hoặc giới hạn những outer retries không an toàn.
5. Không hạ consistency level hoặc auth.
6. Không đổi provider payment intent ID cho cùng business intent.

### Pha B — Khoanh vùng lỗi

7. Tách connect, read, server selection và pool timeouts.
8. Xem driver retries đã thực hiện bao nhiêu attempts.
9. Kiểm tra per-node/partition hot spots, throttling, queue/compaction.
10. Kiểm tra leader election, replica lag, network partition.
11. Phân nhóm theo operation và tenant tier.
12. Đối chiếu HTTP deadline với driver timeouts.

### Pha C — Hạn chế retry storm

13. Dùng bounded attempts + jitter + retry budget.
14. Giảm in-flight concurrency với backpressure.
15. Ưu tiên read-only/idempotent requests theo policy.
16. Fail fast khi authority/quorum unavailable.
17. Để reconciliation xử lý unknown writes ngoài HTTP request.
18. Theo dõi retry attempts per original operation.

### Pha D — Đối soát

19. Tra authoritative operation ledger/provider status.
20. Xác minh same ID/same fingerprint.
21. Không dùng eventual index absence làm proof.
22. Ghi `APPLIED/REJECTED/PENDING/UNKNOWN` theo chứng cứ.
23. Xử lý cases mâu thuẫn bằng manual review, audit và compensation nếu cần.
24. Kiểm tra không duplicate charges, reservation, counters.

### Pha E — Hậu kiểm

25. Thử lại lost ACK sau commit trong staging.
26. Kiểm tra driver version và retry defaults.
27. Tạo tests cho từng operation category.
28. Đo p95/p99, time-to-terminal, unknown backlog.
29. Điều chỉnh timeout/deadline theo workload, không chữa mọi lỗi bằng tăng timeout.
30. Ghi lại chính sách retry trong source và runbook.

## 72. Checklist triển khai cho một Java NoSQL repository

```text
[ ] Mỗi command có một semantic classification rõ.
[ ] Có stable operationId trước lần dispatch đầu.
[ ] Same ID/different payload được phát hiện.
[ ] Driver retry behavior đã được đọc theo version.
[ ] Không có outer retry mù cho non-idempotent writes.
[ ] Connect/pool/read/command/transaction timeouts được phân biệt.
[ ] Có overall deadline và backoff với jitter.
[ ] Có retry budget và bounded concurrency.
[ ] Condition failures không bị coi là lỗi mạng.
[ ] CAS conflict dẫn tới re-read/revalidate.
[ ] Timeout sau commit được biểu diễn UNKNOWN khi cần.
[ ] Có authoritative operation status query.
[ ] Dedup receipt và business effect có atomic/recovery semantics.
[ ] Marker retention đủ cửa sổ replay.
[ ] Không retry DELETE mù qua delete/recreate generation.
[ ] Không retry INCREMENT/APPEND mà thiếu dedup.
[ ] Multi-item batch có per-item outcome hoặc transaction contract.
[ ] Transaction callback không chứa side effect ngoài DB không idempotent.
[ ] Payment/provider calls dùng provider idempotency và reconciliation.
[ ] Failover không hạ consistency hoặc ghi vào stale authority.
[ ] Metrics cho retries, unknown outcomes, pool và p99 có mặt.
[ ] Fault tests có drop response sau commit, không chỉ mock throw trước write.
[ ] UI phân biệt FAILED chắc chắn với UNKNOWN/PENDING.
```

## Kết luận

Khi Java kết nối tới NoSQL, việc cấu hình **timeout và retry** không thể tách khỏi **tính lũy đẳng của từng lệnh**. Một `GET` thuần đọc, một phép `SET` hằng, một conditional update, một `$inc`/counter, một insert có ID ổn định, một delete có generation guard và một transaction gọi payment provider **không có cùng mức an toàn khi phát lại**. Thêm `try/catch`, tăng `maxAttempts` hoặc bật driver retries không tự bảo vệ business effects.

Cách làm đáng tin cậy là **lập bảng semantics cho từng command**, xác định commit/ACK boundary, phân biệt lỗi chắc chắn bị từ chối với **outcome chưa xác định**, giữ một `operationId` ổn định và gắn **dedup receipt với business effect trong atomic authority hoặc protocol recovery phù hợp**. Khi retry được phép, cần **deadline tổng, capped exponential backoff, jitter, retry budget, bounded concurrency** và biết rõ SDK đã retry mấy lần. Khi write timeout sau dispatch mà chưa có bằng chứng, **đối soát theo nguồn có thẩm quyền** thay vì tạo một lệnh có side effect mới.

Cuối cùng, phải kiểm thử đúng các cửa sổ lỗi: **commit rồi mất phản hồi, retry song song, failover, throttling, stale status lookup, worker crash và marker TTL hết trước replay**. Một kết nối Java có khả năng phục hồi tốt không phải là kết nối “thử lại mãi”, mà là hệ có thể **tiếp tục tiến triển mà không làm sai dữ liệu và không nhân đôi ý định nghiệp vụ**.

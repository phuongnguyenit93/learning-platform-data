# Mô phỏng lỗi trước gửi, sau áp dụng ghi và trước nhận phản hồi

Một ứng dụng Java gửi lệnh tạo đơn hàng đến dịch vụ dùng MongoDB. Kết nối bị ngắt, phía Java thấy `SocketTimeoutException` và lập tức gửi lại lệnh. Sau vài giây, người dùng thấy **hai đơn hàng giống nhau**. Một lần khác, API báo lỗi nhưng đơn hàng đã tồn tại; người dùng thử tạo lại và tiếp tục nhận thêm đơn. Trường hợp thứ ba, client lỗi khi chưa gửi byte nào, nên retry lẽ ra hoàn toàn an toàn nếu giữ nguyên ý định nghiệp vụ. Cả ba tình huống đều có thể được gọi chung là “request thất bại” trên màn hình, nhưng ý nghĩa đối với dữ liệu khác nhau căn bản.

Bài học thuộc chương **Kiểm thử lỗi và tải**, module **Database No SQL**. Chúng ta sẽ mô phỏng lỗi tại ba điểm đặc biệt trong vòng đời một thao tác ghi:

1. **Trước gửi**: client gặp lỗi trước khi request thực sự được gửi.
2. **Sau áp dụng ghi**: server/database đã thực hiện write theo một ranh giới xác nhận được định nghĩa, nhưng tiến trình có thể gặp lỗi tiếp.
3. **Trước nhận phản hồi**: write có thể đã thành công, phản hồi có thể đã được tạo/gửi, nhưng client chưa nhận được hoặc không thể tin chắc outcome.

Mục tiêu không phải chỉ làm ứng dụng ném exception; mục tiêu là **tạo lỗi tại đúng ranh giới, quan sát cả hai phía và chứng minh hệ vẫn giữ bất biến nghiệp vụ** qua retry, concurrent requests, failover và tải thực tế.

> **Nguyên tắc:** Trạng thái request ở client và trạng thái commit ở database là **hai sự thật khác nhau**. Một ngoại lệ giao tiếp không được tự biến thành kết luận “write chưa xảy ra”, cũng không được biến thành kết luận “write đã xảy ra”. Thiết kế thử nghiệm phải kiểm **state và side effects có thể quan sát được sau lỗi**.

Các API, lệnh và giá trị timeout trong bài chỉ dùng làm ví dụ. Khả năng fault injection, durability, retry và visibility phụ thuộc engine, driver, SDK, phiên bản, topology và cấu hình thực tế; không thực hiện thử nghiệm phá hoại trên production ngoài quy trình đã được phê duyệt.

## 1. Phân biệt bốn mốc trong một request ghi

~~~text
Client                         Network                        Server / Database
  |                               |                                |
  | A. tạo logical command         |                                |
  |---- B. send request ---------->|---- request đến -------------->|
  |                               |                     C. validate/auth
  |                               |                     D. apply/commit
  |                               |<---- E. create/send response ---|
  |<------- F. receive response ---|                                |
  | G. interpret outcome          |                                |
~~~

Các mốc cần đặt tên chính xác:

- **A**: Ý định nghiệp vụ được tạo, ví dụ `PlaceOrder` với `operationId` ổn định.
- **B**: Client bắt đầu truyền request.
- **C**: Server có thể từ chối trước khi ghi vì xác thực, phân quyền, validation hoặc conflict.
- **D**: Database thực hiện hoặc xác nhận ghi theo hợp đồng consistency/durability cụ thể.
- **E**: Server tạo và gửi phản hồi.
- **F**: Client nhận phản hồi.
- **G**: Client suy diễn kết quả và có thể retry hoặc tiếp tục workflow.

Không đồng nhất **apply trong RAM**, **write đã được ghi vào log**, **write được majority ACK**, **write đã durable**, **write đã visible với mọi reader**, và **business side effect đã hoàn tất**. Chúng có thể là những thời điểm khác nhau.

## 2. Ba điểm lỗi cần chủ động phân biệt

| Điểm thử | Nơi chèn lỗi | Server chắc chắn đã nhận request? | Write chắc chắn xảy ra? | Kết luận của client |
|---|---|---|---|---|
| F1 — **trước gửi** | Ngay trước lời gọi transport/send | Không, nếu harness chứng minh chưa gửi | Chưa từ request này | Có thể retry cùng command |
| F2 — **sau áp dụng ghi** | Hook sau write đã được xác minh, trước response | Có | Có trong ranh giới đã được xác minh | Client vẫn có thể thấy lỗi |
| F3 — **trước nhận phản hồi** | Proxy chặn response hoặc cắt đường về | Có thể | **Không thể suy chỉ từ timeout** | Outcome có thể UNKNOWN |

Quan trọng: F3 là vị trí **client không nhận được bằng chứng**, không nhất thiết vị trí server đã commit. Một packet bị drop trên đường về có thể xảy ra cả khi server trả `200 OK`, `409 Conflict` hoặc `500 Error`. Harness cần ghi nhận kết quả server độc lập nếu muốn biết ground truth của từng case.

## 3. F1: lỗi trước gửi thật sự

Một mô phỏng đúng:
~~~text
T0: Client tạo commandId = op-101.
T1: Inject failure trong client interceptor trước transport.send().
T2: Không mở/gửi request tới API.
T3: Java trả lỗi giả lập.
T4: Retry cùng op-101.
T5: Server mới xử lý request lần đầu.
~~~

Nếu client interceptor bảo đảm đường gửi chưa được gọi, F1 là trường hợp **chắc chắn request chưa có effect**. Nhưng một timeout ở socket khi client đang gửi **không thể tự gọi là F1**, vì một phần request có thể đã đến server.

Phép thử F1 phải đặt hook **trước lời gọi có thể gửi byte**, không chỉ cắt mạng sau khi `sendAsync` đã bắt đầu.

## 4. F2: lỗi sau write đã được áp dụng

~~~text
T0: Server nhận command op-101.
T1: Authn/authz và validation đạt.
T2: Database chấp nhận/commit write theo contract kiểm thử.
T3: Test hook xác nhận write result và chặn trước HTTP response.
T4: Process crash hoặc ném exception.
T5: Client chỉ thấy timeout/connection reset/5xx.
T6: Readback và retry được thực hiện.
~~~

Đây là trường hợp nguy hiểm với **retry mù**: effect đã xảy ra nhưng client không biết.

Để mô phỏng đúng F2 phải định nghĩa “sau áp dụng”:
- Sau lệnh UPDATE local memory? Có thể chưa durable.
- Sau write ACK với `w:1`? Tùy engine, có thể bị rollback khi failover.
- Sau write majority/journal/durable ACK? Bảo đảm mạnh hơn theo cấu hình và phiên bản.
- Sau transaction commit response? Có thể đã commit nhưng kết quả chưa được chuyển tới lớp HTTP.

**Đừng ghi test tên “after durable commit” nếu hook đặt trước durability boundary.**

## 5. F3: phản hồi mất trước khi đến client

~~~text
T0: Server xử lý request.
T1: Server tạo response (có thể success hoặc failure).
T2: Proxy trên đường trả về drop/delay/reset.
T3: Client hết timeout, không đọc được response.
T4: Client phải xác định bước tiếp theo.
~~~

Server có thể đã:
- Commit thành công.
- Từ chối vì duplicate idempotency key.
- Từ chối do thiếu quyền.
- Rollback vì conflict.
- Chưa hoàn tất do server crash.

Bởi vậy F3 thường tạo **trạng thái kết quả chưa biết từ phía client**, trừ khi harness có thêm nguồn xác minh. Cách xử lý an toàn là **retry cùng logical identity hoặc truy vấn trạng thái operation qua API được thiết kế cho việc đó**, không tự phát một command mới.

## 6. Định nghĩa các trạng thái outcome

Một logical command có thể có:
- `NOT_SENT`: chỉ khi client/test harness biết chắc chưa gửi.
- `RECEIVED`: server đã nhận nhưng chưa quyết định.
- `REJECTED`: server từ chối trước business effect.
- `COMMITTED`: business write đã được commit theo contract.
- `FAILED_FINAL`: lỗi không được phép retry nguyên request, ví dụ validation conflict.
- `UNKNOWN`: client không biết commit outcome.
- `RECONCILING`: hệ đang truy vấn/đối chiếu outcome.
- `COMPLETED`: client có kết quả đủ chắc để trả hoặc tiếp tục workflow.

Các trạng thái **không nhất thiết nằm trong một database record duy nhất**; đây là ngôn ngữ mô tả trạng thái logic. Không được gán `FAILED_FINAL` chỉ vì TCP timeout.

## 7. Cùng một ngoại lệ có thể tương ứng nhiều thực tế

| Client thấy | Có thể xảy ra ở server | Có nên tạo operation ID mới khi retry? |
|---|---|---|
| Timeout trước kết nối do local interceptor | Server không thấy request | Không cần ID mới; giữ ID cũ |
| Timeout khi write đang gửi | Chưa nhận, nhận một phần hoặc đã nhận đủ | **Không** |
| Connection reset sau commit | Write có thể đã commit | **Không** |
| HTTP 503 từ gateway | Backend có thể đã xử lý trước lỗi gateway | **Không** khi retry cùng ý định |
| HTTP 409 do duplicate key | Có thể là replay hoặc conflict payload | Không tạo ID mới chỉ để lách |
| HTTP 400 validation | Thường chưa có business effect nếu contract đúng | Sửa request; ý định mới cần được phân biệt |
| HTTP 200/201 nhận đầy đủ | API đã xác nhận outcome theo contract | Không retry chỉ vì user bấm lại |

Không dựa duy nhất vào HTTP status; semantics phải được xác định trong API contract. Một `500` sau commit có thể đến từ bước serialize response thất bại, không chứng minh ghi đã rollback.

## 8. Ý định nghiệp vụ khác mỗi HTTP attempt

Ví dụ:
~~~text
Logical intent: tạo một đơn từ checkout session X.
operationId = checkout-X-001.

Attempt #1: request gửi, ACK mất.
Attempt #2: retry.
Attempt #3: retry sau failover.
~~~

Cả ba attempts phải giữ **cùng `operationId`** nếu vẫn là một ý định, để server có thể trả **cùng effect/result**.

Nếu mỗi retry gọi:
~~~text
new UUID -> POST /orders
~~~

thì phía server có thể coi đó là ba lệnh tạo đơn độc lập, gây duplicate.

## 9. Idempotency: tính chất cần kiểm, không phải tên một header

Định nghĩa trong phạm vi API:
> Với cùng `tenant`, `operation`, `idempotencyKey` và payload tương ứng, nhiều lần gửi cùng logical command chỉ tạo **tối đa một business effect**, và các lần thử lại nhận kết quả phù hợp contract.

Ví dụ:
~~~http
POST /orders
Idempotency-Key: checkout-tenant7-001
~~~

Server cần xử lý:
- First attempt thành công và lưu result.
- Replay sau response loss.
- Hai requests cùng key đến đồng thời.
- Cùng key nhưng payload khác.
- Key hết TTL.
- Crash khi đang xử lý.
- Retry sau failover/region switch.
- Data/response retention theo privacy policy.

Header tự nó không tạo idempotency. **Phải có vùng lưu identity, uniqueness và atomic effect**.

## 10. Một nguồn ID đáng tin

Không để client chỉ tùy ý chọn `userId` hoặc `tenantId` rồi dùng làm scope. Một idempotency identity nên có:
- Tenant/account scope **từ verified authorization context**.
- Operation type (`order.create`, `payment.capture`, ...).
- Client-provided stable key có giới hạn độ dài/format.
- Payload fingerprint/canonical semantics.
- Server-side record cho result/outcome.

Ví dụ key composition logic:
~~~text
dedupKey = (verifiedTenantId, operationType, idempotencyKey)
~~~

Cùng một chuỗi key có thể được dùng ở tenants khác mà không trùng; trong cùng scope, payload không khớp phải trả conflict thay vì dùng kết quả của người khác.

## 11. Payload fingerprint để ngăn key reuse sai

Hai attempts:
~~~json
{"key":"K1","productId":"P7","quantity":1}
{"key":"K1","productId":"P7","quantity":10}
~~~

Nếu server chỉ so key và trả kết quả cũ không kiểm payload, caller có thể nhận một order sai mà không biết.

Cần:
- Canonical hóa fields có ý nghĩa nghiệp vụ.
- Kiểu số/đơn vị và thứ tự arrays theo contract.
- Domain separation và hashing phù hợp.
- Không hash raw secrets vào telemetry.
- Không lộ payload gốc trong error messages.

Khi cùng key nhưng fingerprint khác, API nên trả **conflict có cấu trúc** và không thực thi effect mới.

## 12. Mô hình trạng thái idempotency record

~~~mermaid
flowchart TD
    N["Chưa có key"] --> P["PROCESSING"]
    P --> C["COMPLETED + saved result"]
    P --> F["FAILED_FINAL + saved decision"]
    P --> U["UNKNOWN / needs reconciliation"]
    U --> C
    U --> F
    U --> P2["Safe recover/retry"]
    C --> R["Replay same result"]
    F --> RF["Replay final failure"]
~~~

`PROCESSING` cần cơ chế owner/lease/timeout để tránh kẹt vô hạn sau crash. Nhưng lease hết hạn **không chứng minh worker cũ chưa commit**: worker takeover phải kiểm durable operation state, và nếu có khả năng writer cũ vẫn chạy, cần fencing hoặc atomic condition.

## 13. Atomicity: hiệu ứng và bằng chứng phải đi cùng nhau

Thiết kế lỗi:
~~~text
1. Write business record.
2. Return success.
3. Persist idempotency record.
~~~

Crash giữa 1 và 3 khiến retry không thấy dedup và tạo effect lần hai.

Một thiết kế mạnh:
~~~text
Atomic unit:
  apply business mutation
  persist stable operationId/result evidence
commit
~~~

Có thể thực hiện bằng:
- Một document/record chứa business effect và operation ID với unique identity.
- Transaction trong phạm vi database thực sự hỗ trợ.
- Conditional update + operation record được thiết kế trong một atomic boundary.
- Saga/outbox và reconciliation nếu effect vượt nhiều stores.

**Không giả định hai database độc lập cùng commit chỉ nhờ gọi hai API liên tiếp.**

## 14. Đơn giản hóa create bằng deterministic business ID

Nếu một order logic có stable ID `order-{operationId}`:
~~~text
First attempt INSERT _id = order-op-101 -> success.
Replay INSERT same _id -> duplicate key.
Server fetches existing record and verifies intent -> same result.
~~~

Điều kiện:
- `_id` thực sự unique trong scope.
- Không có collision giữa tenants/operations.
- Record đủ để xác minh payload/result.
- Retention đủ cho retry window.
- Delete/recreate semantics rõ.
- Readback với consistency phù hợp.

Đây là ví dụ gần atomic hơn cách tạo random order ID mỗi lần retry. Nhưng nó **không tự giải quyết side effects ngoài order store** như payment capture, email, event publishing; các bước ấy cũng cần idempotent/outbox.

## 15. Một ví dụ MongoDB idempotent create

~~~javascript
// Ý tưởng minh họa, không phải toàn bộ HTTP/security handler.
const orderId = `order-${operationId}`;

try {
  db.orders.insertOne({
    _id: orderId,
    verifiedTenantId: tenantFromAuth,
    idempotencyKey: operationId,
    payloadFingerprint: canonicalFingerprint,
    status: "CREATED",
    amountMinorUnits: amountMinorUnits,
    resultVersion: 1
  });
  return { status: 201, orderId };
} catch (error) {
  if (!isDuplicateKeyError(error)) throw error;

  const existing = db.orders.findOne({
    _id: orderId,
    verifiedTenantId: tenantFromAuth
  });

  if (!existing) {
    throw new Error("COMMIT_OUTCOME_REQUIRES_RECONCILIATION");
  }
  if (existing.payloadFingerprint !== canonicalFingerprint) {
    return { status: 409, code: "IDEMPOTENCY_KEY_CONFLICT" };
  }
  return { status: 200, orderId: existing._id, replayed: true };
}
~~~

Lưu ý:
- Code chỉ minh họa **single-document unique create**, chưa có đầy đủ error classification, auth, read concern hoặc retry policy.
- Duplicate key do nguyên nhân khác không được tự coi là replay thành công.
- Nếu write ACK chưa durable và có failover, cần consistency/durability và reconciliation đúng contract.
- Có thể lưu cả original response để replay đúng HTTP status/body nếu API quy định; ví dụ đang trả `200` khi replay để minh họa, **không phải lựa chọn duy nhất**.
- Không log raw request/card data trong error path.

## 16. HTTP idempotency và SDK retryable writes là hai lớp khác

Một driver có thể tự retry một số thao tác khi mất kết nối trong những điều kiện cụ thể. Nhưng:
- Driver retry không tạo business idempotency cho **nhiều HTTP requests mới**.
- Retryable command coverage tùy engine/version/topology và loại operation.
- Một transaction commit bị mất response có quy tắc retry khác ordinary write.
- Driver có thể báo lỗi với nhãn/metadata chỉ dẫn outcome hoặc retry phù hợp.
- Cấu hình application retry chồng với SDK retry có thể nhân số attempts.

Test phải đo **attempt ở API, driver và database**, không chỉ đếm số request do client sinh.

## 17. Client timeout không phải server timeout

Đặt:
~~~text
Client timeout: 700 ms.
Server operation xử lý: 900 ms.
Database commit: 850 ms.
~~~

Client có thể hết thời gian ở 700 ms, trong khi server tiếp tục và commit ở 850 ms. Hủy `Future` hoặc đóng socket không nhất thiết hủy transaction đã khởi động.

Một server có thể phát hiện client disconnect nhưng vẫn hoàn tất business effect. Test phải mô phỏng cả:
- Client timeout trong lúc server đang chạy.
- Server cancel được operation trước commit.
- Server không cancel được sau commit.
- Lệnh bị hủy trước gửi.
- Connection reset khi response đang truyền.

## 18. Lỗi trước gửi không đồng nghĩa lỗi trước commit

Một transport call có nhiều stages:
~~~text
Local validation -> DNS -> connect -> TLS -> write bytes
-> server read headers/body -> handler -> DB command.
~~~

`ConnectException` thường gợi ý không có server xử lý request đó, nhưng trong hệ có retry/proxy/multiple endpoints, vẫn cần biết attempt nào và đã gửi qua đường nào.

Muốn chứng minh F1, nên chèn hook **ở code trước khi handoff cho transport** và quan sát không có server ingress/event tương ứng. Không dựa vào tên exception để gắn phase.

## 19. F2 phải xác minh durable apply

Một hook lý tưởng:
~~~text
Apply business write.
Await write result under chosen durability policy.
Record test-only commit marker in trusted test sink.
Inject exception/drop connection before producing HTTP response.
~~~

Sau đó test oracle đọc:
- Business record.
- Operation/idempotency evidence.
- Event/outbox record nếu nằm trong transaction.
- Replica durability/visibility state theo engine.
- Side effects downstream sau khi queue xử lý.

Nếu chỉ `sleep(100)` rồi crash, không có chứng minh write đã đi qua boundary. **Fault injection phải gắn với một milestone có thể quan sát được**.

## 20. F3 cần chặn đúng chiều đường truyền

Một proxy có thể:
- Drop **upstream** request (client → server).
- Drop **downstream** response (server → client).
- Delay response vượt client timeout.
- Reset kết nối khi server đã bắt đầu trả response.
- Throttle stream gây partial response.

Không thể mô phỏng **response lost after server success** bằng cách đơn giản tắt cả mạng trước khi request đến. Harness cần phân biệt ingress/egress, có server-side proof và ghi rõ fault timing.

## 21. Kiến trúc fault injection có kiểm soát

~~~mermaid
flowchart LR
    TEST["JUnit / load generator"] --> CLIENT["Java client with stable operationId"]
    CLIENT --> PROXY["Fault proxy / transport interceptor"]
    PROXY --> API["Test API service"]
    API --> HOOK["Server-side failpoints"]
    HOOK --> DB["NoSQL test cluster"]
    DB --> ORACLE["Independent readback / operation ledger"]
    API --> OBS["Safe audit / tracing"]
    TEST --> ORACLE
    TEST --> OBS
~~~

Vai trò:
- **Client interceptor:** tạo F1 chắc chắn trước send.
- **Server failpoint:** tạo F2 sau commit milestone.
- **Reverse proxy:** tạo F3 mất response.
- **Readback oracle:** kiểm state độc lập với HTTP response.
- **Fault scheduler:** chọn đúng request, phase, attempt.
- **Telemetry:** liên kết `operationId`, `attemptId`, safe event type.

Thử trong sandbox có scope và data synthetic; không bật failpoint production diện rộng.

## 22. Thiết kế test fixture chuẩn

Ví dụ:
~~~yaml
caseId: after-commit-before-reply
tenant: test-tenant-7
operationId: op-test-101
businessAction: create-order
request:
  sku: sample-product
  quantity: 2
  amountMinorUnits: 50000
inject:
  phase: AFTER_DURABLE_COMMIT_BEFORE_RESPONSE
  attempt: 1
expected:
  firstClientOutcome: "exception_or_timeout"
  replayOutcome: "same_logical_order"
  businessEffects: 1
  uniqueOrderCount: 1
  durableOperationRecords: 1
  forbidden:
    - duplicate-payment
    - negative-inventory
~~~

Các expected fields do bài test định nghĩa, không phải API chuẩn của một công cụ. `firstClientOutcome` có thể khác tùy proxy và timing, nhưng **bất biến cuối** phải được xác định chặt.

## 23. Test oracle phải độc lập với response của request bị lỗi

Không đủ:
~~~java
assertThrows(TimeoutException.class, () -> client.createOrder(...));
~~~

Timeout chỉ chứng minh client **không nhận được kết quả**. Cần hỏi database:
- Có bao nhiêu orders theo stable operation ID?
- Có bao nhiêu payment captures?
- Inventory còn bao nhiêu?
- Có outbox event nào?
- Có bản ghi idempotency/result không?
- Đã có duplicate command attempts không?
- Có trạng thái in-progress không được giải quyết?

Readback có thể cần chờ convergence theo consistency contract; không được tự đọc replica stale rồi kết luận write chưa xảy ra.

## 24. Một bảng kết quả kỳ vọng

| Scenario | Client attempt đầu | Server effect đầu | Retry cùng key | Final invariant |
|---|---|---|---|---|
| F1 chắc chắn chưa gửi | Injected error | 0 | Tạo effect lần đầu | 1 |
| F2 commit rồi lỗi | Timeout/reset | 1 | Replay result, không tạo mới | 1 |
| F3 mất success response | Timeout/reset | 1 | Replay result, không tạo mới | 1 |
| F3 mất validation failure | Timeout/reset | 0 | Vẫn bị từ chối theo contract | 0 |
| F3 mất unknown commit response | Timeout | Chưa xác định | Safe retry/reconcile | ≤1 effect |
| Two concurrent same-key attempts | Cả hai có thể nhận response khác thời điểm | 1 logical effect | Dedup/processing response | 1 |
| Same key/different payload | Conflict | Chỉ payload đầu hợp lệ có effect | Reject mismatch | Không tạo effect mới |

Trong thực nghiệm cần ghi rõ **đã chứng minh gì bằng server-side hook** và phần nào vẫn `UNKNOWN` từ phía client.

## 25. Chương trình thí nghiệm JUnit — mô tả hành vi

~~~java
@Test
void retryAfterCommittedWriteDoesNotCreateAnotherOrder() {
    String operationId = "op-fi-552";
    OrderCommand command = syntheticOrder(operationId);

    harness.failOnce(
        operationId,
        FailurePoint.AFTER_DURABLE_COMMIT_BEFORE_HTTP_RESPONSE
    );

    assertThrows(IOException.class, () -> api.placeOrder(command));

    // Kết quả đầu đã được commit theo test server hook.
    OrderResult replay = api.placeOrder(command);

    assertEquals(
        1L,
        independentOracle.countOrdersByOperationId(operationId)
    );
    assertEquals(
        1L,
        independentOracle.countOrderCreatedEvents(operationId)
    );
    assertEquals(
        independentOracle.findOrderId(operationId),
        replay.orderId()
    );
}
~~~

Đây là mã **minh họa phương pháp test**, không phải thư viện JUnit/driver hoàn chỉnh. Cần cung cấp implementations cho `harness`, `api` và `independentOracle` trong dự án. Trong hệ eventual consistency, test nên có bounded wait/poll để xác minh convergence, tránh `Thread.sleep` cố định rồi giả định mọi dữ liệu đã kịp đồng bộ.

## 26. F1 với client interceptor

~~~java
@Test
void beforeSendFailureHasNoEffectUntilRetry() {
    String operationId = "op-before-send-552";
    OrderCommand command = syntheticOrder(operationId);

    harness.failClientBeforeTransportOnce(operationId);

    assertThrows(IOException.class, () -> api.placeOrder(command));

    assertEquals(
        0L,
        independentOracle.countOrdersByOperationId(operationId)
    );
    assertEquals(
        0L,
        independentOracle.countIngressAttempts(operationId)
    );

    OrderResult result = api.placeOrder(command);
    assertNotNull(result.orderId());

    assertEquals(
        1L,
        independentOracle.countOrdersByOperationId(operationId)
    );
}
~~~

Ở test này việc khẳng định **0 ingress** dựa trên hook nằm trước bất kỳ lời gọi send nào và nguồn quan sát ingress đáng tin. Với một lỗi mạng ngẫu nhiên khi request đang đi, không thể dùng expected 0 ingress như thế.

## 27. F3 với proxy chặn response

~~~text
Harness setup:
  Route request op-552 through a test proxy.
  Let full request reach server.
  Observe server response completed or chosen milestone.
  Drop only server -> client bytes.
  Leave database service reachable to independent oracle.

Assertions:
  Client receives timeout/connection error.
  Server-side outcome recorded independently.
  Retry uses same operationId and payload fingerprint.
  No duplicate order/payment/inventory effect.
~~~

Có thể dùng network proxy/fault-injection framework được hỗ trợ trong test environment, nhưng cách chèn lỗi phải được xác định theo hướng traffic. Một số proxy chỉ bảo đảm cắt kết nối, không bảo đảm response bị drop **sau durable commit**; khi đó cần kết hợp server failpoint.

## 28. Lỗi ở client, API và database không giống nhau

| Lớp | Ví dụ lỗi | Phần biết chắc |
|---|---|---|
| Client beforeSend | Interceptor ném lỗi | Chưa giao cho transport |
| Client socket | Timeout/reset | Outcome có thể unknown |
| Gateway | Timeout, retry hoặc trả 502/503 | Backend có thể đã xử lý |
| API handler | Crash trước validation/write | Có thể chưa effect, nếu được chứng minh |
| API handler | Crash sau commit | Effect có thể đã durable |
| Database client | Timeout lệnh ghi | Outcome tùy write concern/driver |
| Database replica | Failover/rollback | ACK semantics quan trọng |
| Stream/consumer | Apply rồi crash trước ack | Duplicate delivery khi replay |
| Downstream payment | Timeout sau capture | External effect có thể thành công |

Mỗi loại phải được kiểm **ở ranh giới hiệu lực riêng**. “Kill pod” ngẫu nhiên chỉ tạo lỗi tổng quát và không thay thế tests cho ba điểm rõ ràng.

## 29. Write acknowledgement không đồng nghĩa business completion

Ví dụ:
~~~text
DB insert order commit.
Outbox event phát vào queue.
Payment service capture.
Email sent.
API trả success.
~~~

Nếu F2 xảy ra ngay sau DB insert, payment có thể chưa capture. Nếu F3 xảy ra sau tất cả steps, có thể đã hoàn tất. Do đó cần định nghĩa:
- Endpoint trả thành công khi order ở state nào?
- Payment capture có là một bước đồng bộ không?
- Outbox có commit atomically với order không?
- Consumer có idempotency riêng không?
- Nếu payment timeout, order `PENDING_PAYMENT` hay `PAID`?
- Client query operation status ở đâu?

Đừng chỉ đếm một document và kết luận không có duplicate side effects trên toàn workflow.

## 30. Một state machine nghiệp vụ giúp retry an toàn

~~~mermaid
flowchart TD
    N["NEW"] --> R["RECEIVED"]
    R --> P["PENDING_PAYMENT"]
    P --> PAID["PAID"]
    P --> FAIL["PAYMENT_FAILED"]
    R --> REJ["REJECTED"]
    PAID --> RES["Result can be replayed"]
    FAIL --> RETRY["Retry under business rules"]
    REJ --> FINAL["Final rejection"]
~~~

Các transition nên có expected state/version và operation identity. Nếu API timeout ở `PENDING_PAYMENT`, retry tạo **cùng order** và tiếp tục/quan sát payment attempt, không tạo order mới.

Với payment provider, idempotency key riêng cho capture phải có phạm vi, thời hạn và semantics theo provider; không chỉ dùng DB dedup rồi gửi capture hai lần.

## 31. Counter decrement và inventory reservation

Một lệnh nguy hiểm:
~~~text
DECR inventory by 1.
~~~

Nếu F2 xảy ra sau decrement rồi client retry, tồn kho có thể bị trừ hai lần.

Các hướng:
- Reservation ID ổn định; insert unique reservation và update inventory trong atomic boundary nếu hỗ trợ.
- Conditional update theo expected stock/state.
- Idempotent command ledger để kiểm đã áp dụng decrement chưa.
- Saga với compensating action và reconciliation nếu nhiều stores.
- Versioned state transition thay vì blind increment/decrement khi có thể.

**`SET quantity=oldQuantity-1` không an toàn nếu giá trị oldQuantity đã stale**. Conditional write và audit cùng operation ID phải giữ invariant không âm và không double-reserve.

## 32. Atomicity và idempotency trong DynamoDB

DynamoDB có conditional writes và transactional APIs theo điều kiện được hỗ trợ. Một thiết kế minh họa:
- Tạo item `ORDER#{operationId}` nếu chưa tồn tại.
- Kiểm payload fingerprint nếu item đã có.
- Dùng `ConditionExpression attribute_not_exists(PK)` cho create.
- Nếu cùng transaction cần reservation/operation ledger, dùng TransactWriteItems trong phạm vi hỗ trợ.
- Phân biệt `ClientRequestToken` của transactional API với business-level idempotency record có thời hạn/semantics riêng.
- Khi thấy timeout, không tự tạo random order ID mới.
- Kiểm item state với consistency options phù hợp ở đúng table/region.

Một conditional write rejected **không luôn đồng nghĩa order đã tồn tại do replay**; có thể conflict vì invariant khác. Test cần phân biệt code/condition reason và đọc lại state hợp lệ.

## 33. DynamoDB: mô phỏng response loss sau conditional put

~~~text
1. Test API nhận op-552.
2. PutItem với condition item chưa tồn tại.
3. DB xác nhận thành công theo API.
4. Test hook drop HTTP response.
5. Client retry cùng op-552.
6. Conditional Put gặp item đã tồn tại.
7. API xác minh fingerprint và trả saved result.
8. Oracle thấy đúng một business order.
~~~

Cần thêm cases:
- Two attempts cùng key khác payload.
- Timeout trước khi DynamoDB chấp nhận write.
- Global table/multi-region behavior theo service contract.
- TTL cleanup của idempotency record.
- Throttling và SDK retries.
- Item vừa tạo nhưng read từ đường eventually consistent có thể chưa thấy ngay.

Không thiết kế API trả `success` sau bất kỳ conditional error nào mà chưa xác minh đó là replay hợp lệ.

## 34. MongoDB: write concern và ambiguous outcome

Trong MongoDB, tình huống cần thử:
- Write với write concern như cấu hình production.
- Driver mất kết nối trước khi nhận write result.
- Failover sau ACK ở mức yếu hơn.
- Retryable writes nếu được hỗ trợ trong topology/mode.
- Transaction commit response lost và driver error labels.
- Readback ở primary/consistency phù hợp.
- Unique index và transactions khi business effect cần atomic nhiều records.

Ví dụ F2 “đã ghi sau `w:1` ACK” có mức chắc chắn khác “đã ghi theo policy majority/journal được phê duyệt”. Đừng test kịch bản này bằng mock repository, vì mock không mô phỏng durability/replication rollback.

## 35. MongoDB: transaction commit response lost

Một flow:
~~~text
start transaction
update order
insert audit/outbox
commit request
server commits
reply lost
client receives commit error/unknown outcome
~~~

Một hành vi sai là tự chạy lại **business transaction mới với operationId mới**, có thể nhân effect. Cần dùng hướng dẫn driver về retry commit/transaction labels và business idempotency để:
- Nhận biết outcome không chắc.
- Retry commit theo protocol được hỗ trợ nếu thích hợp.
- Không phát side effect ngoài transaction trong retryable callback.
- Query durable operation record khi cần.
- Giữ idempotency key và payload fingerprint.

Không khẳng định mọi lỗi `commitTransaction` đều có thể retry mù, hoặc rằng every transaction callback chỉ chạy một lần.

## 36. Cassandra: timeout và consistency level

Ở Cassandra:
- Coordinator có thể timeout dù một hoặc nhiều replica đã ghi.
- Hợp đồng `ONE`, `LOCAL_QUORUM`, `QUORUM` và replication factor ảnh hưởng mức xác nhận.
- Client reconnect/retry sau timeout có thể gặp write cũ đã apply.
- Last-write-wins/timestamps, tombstones và counter semantics cần được hiểu.
- Một số conditional operations dùng lightweight transactions (LWT/Paxos) theo khả năng engine.
- Một read từ replica không đủ consistency có thể trả state cũ.

Do đó không suy `WriteTimeout` là rollback. Test phải kiểm scope của consistency, replica failure, readback và eventual convergence. Với counter updates hoặc increment không idempotent, một retry có thể gây double effect nếu không có dedup/protocol riêng.

## 37. Cassandra: dùng LWT cho logical claim khi thích hợp

Khung CQL minh họa:
~~~sql
INSERT INTO command_claims (
  scope_id, operation_id, payload_fingerprint, state
) VALUES (
  'tenant-7', 'op-552', 'hash-opaque', 'CLAIMED'
) IF NOT EXISTS;
~~~

LWT có thể giúp chỉ một caller claim cùng operation trong phạm vi row/key, nhưng:

- Claim tạo thành công **không tự commit business effect ở table khác**.
- Crash sau claim trước business write tạo `CLAIMED` kẹt.
- Phải có recovery/reconciliation và token/lease guard.
- Cross-partition atomicity không tự có.
- TTL dọn claim có thể làm old operation chạy lại nếu retry sau retention.
- Latency/throughput cost của LWT cần đo.

Một `SELECT` rồi `INSERT` không có điều kiện không thay được atomic claim dưới concurrency.

## 38. Redis: lệnh nguyên tử vẫn có outcome không xác định

Redis có nhiều commands có hiệu lực nguyên tử tại server theo semantics của lệnh, nhưng client có thể mất reply sau khi command đã chạy.

~~~text
Client: INCR order-counter.
Redis: counter tăng.
Reply lost.
Client: INCR lại.
~~~

Counter có thể tăng hai lần.

Giải pháp tùy nghiệp vụ:
- Dùng operationId và lưu processed marker/result cùng effect trong một atomic Lua script/transaction khi cùng Redis atomic boundary phù hợp.
- Không dùng Redis cache marker riêng để đảm bảo effect ở database khác.
- Xem persistence/replication/failover để xác định durability, không chỉ lệnh chạy xong trong RAM.
- Nếu Redis chỉ là cache, có thể chấp nhận retry theo mô hình cache-idempotent, khác với ledger tài chính.
- Kiểm Redis Cluster hash slot restrictions cho multi-key scripts/transactions.

`SET key value` có thể idempotent theo value, trong khi `INCR`/`LPUSH`/`XADD` thường cần cân nhắc duplicate effects.

## 39. Redis: SET NX không tự bảo đảm exactly-once workflow

Một phương án phổ biến:
~~~text
SET dedup:{opId} processing NX EX 600
Nếu được thì ghi order vào MongoDB.
~~~

Có thể lỗi:
1. Marker Redis được tạo.
2. MongoDB write thất bại.
3. Retry thấy marker đã tồn tại, không tạo order.
4. Sau TTL marker biến mất, old retry có thể tạo order mới.

Hoặc ngược lại: MongoDB commit nhưng Redis marker mất do failover/expiration, retry tạo duplicate.

Để bảo vệ business effect, **nguồn có thẩm quyền** phải có unique business identity/operation record hoặc giao thức recovery phù hợp; Redis marker là lớp hỗ trợ, không chứng minh transaction qua hai hệ.

## 40. Phân biệt operation idempotent với operation chỉ có điều kiện

- `SET status="PAID"` lặp có thể không thay business state nếu không có side effects khác.
- `UPDATE status=PAID IF status=PENDING` có thể chặn transition lặp.
- `INCREMENT balance += 100` lặp hai lần gây sai.
- `INSERT row unique by operationId` có thể chặn record trùng.
- `DELETE key` lặp có thể idempotent về state cuối, nhưng audit/events có thể bị phát hai lần.
- `PUBLISH notification` lặp có side effect downstream.

Phép thử không chỉ so state cuối của một key; phải kiểm **tất cả side effects được định nghĩa trong contract**.

## 41. Failpoints nên dùng một lần theo attempt

Nếu failpoint luôn bật:
~~~text
Attempt #1 commit rồi mất reply.
Attempt #2 commit rồi mất reply.
Attempt #3 commit rồi mất reply.
~~~

Test không quan sát được replay response và không phân biệt logic business với mạng lỗi liên tục.

Nên có:
- `failOnce(operationId, attempt=1, phase=...)`.
- Server hook chỉ mở cho synthetic test identities.
- Expiration/automatic cleanup.
- Metrics/test logs xác nhận hook đã kích hoạt **đúng một lần**.
- Cách bật test khác với production.
- Thời gian timeout đủ để xác định intended phase.

Cũng cần test **persistent fault** riêng để kiểm retry budget, queue exhaustion và degraded modes.

## 42. Lập ma trận fault × retry policy

| Fault | Retry 0 | Retry 1 cùng key | Retry 3 cùng key | Retry 3 key mới |
|---|---|---|---|---|
| F1 before send | Không effect | Một effect | Một effect | Có thể nhiều effect nếu từng attempt là command mới |
| F2 post-commit | Client UNKNOWN | Một effect | Một effect | Rủi ro duplicate |
| F3 reply loss | Client UNKNOWN | Một effect hoặc kết quả final tương ứng | Giữ invariant | Rủi ro duplicate |
| F3 response deny | Không effect | Cùng denial theo contract | Không effect | Không giải quyết authorization |
| Same-key concurrent | N/A | Một logical winner | Một logical winner | Mỗi key có thể được coi là business command riêng |

Bảng thể hiện **yêu cầu của hệ được thiết kế idempotent**, không phải thứ mà mọi database/endpoint tự bảo đảm.

## 43. Retry policy cần giới hạn và có jitter

Một chính sách gợi ý:
~~~text
maxAttempts = 3
baseDelay = 100 ms
maxDelay = 2 s
perRequestDeadline = 5 s
exponentialBackoffWithJitter = true
retrySameOperationId = true
~~~

Các con số chỉ minh họa. Khi triển khai cần:
- Tính deadline của toàn logical operation, không reset vô hạn qua retries.
- Chỉ retry transient errors theo classification.
- Không retry validation/authz failures vô hạn.
- Giữ payload và operationId nhất quán.
- Dùng jitter giảm thundering herd.
- Có circuit breaker/bulkhead khi dependency đang mất.
- Trả `UNKNOWN`/`PENDING` nếu đã hết budget nhưng outcome chưa chắc.

**Retry budget là kiểm soát tải**, không thay idempotency hoặc reconciliation.

## 44. Timeout tối ưu cho latency không tự tối ưu correctness

Nếu client đặt timeout quá ngắn, nó sẽ thường xuyên hết hạn dù server đang commit đúng, làm tăng retry traffic và khả năng trùng nếu server không idempotent.

Nếu quá dài:
- Thread/socket/connection pool bị giữ.
- Người dùng phải chờ.
- Retry sau đó có thể trễ hơn RTO của workflow.

Cần đo:
- Server processing latency p50/p95/p99.
- Database commit latency.
- Network tail latency.
- Queue delays.
- Retry amplification.
- Outcome unknown rate.
- Total logical operation latency, không chỉ thời gian mỗi attempt.

Mục tiêu là giữ SLO và ngăn duplicate effects, **không chỉ giảm exception count**.

## 45. Retry amplification dưới tải

Giả sử 10.000 logical commands/s, tỷ lệ 10% gặp timeout và mỗi timeout thêm hai attempts:
~~~text
Initial rate: 10.000 attempts/s.
Extra attempts: 10.000 × 0,1 × 2 = 2.000.
Total offered rate: 12.000 attempts/s.
~~~

Đây là ví dụ đơn giản, giả định các attempts lại không tiếp tục timeout. Với nhiều tầng retry (API gateway, Java client, driver), số attempts có thể lớn hơn nhiều.

Bài test tải phải phân biệt:
- **Logical commands/s**.
- **HTTP attempts/s**.
- **Database commands/s**.
- **Committed business effects/s**.

Không coi 12.000 HTTP success/attempts là 12.000 đơn hàng mới.

## 46. Load generator phải giữ identity nhất quán

Một load test sai:
~~~text
Mỗi retry là một request generator mới, UUID mới.
~~~

Khi đó không thể đánh giá idempotency thật.

Một generator đúng:
- Tạo logical command + stable ID.
- Sinh 0..N transport attempts với cùng ID.
- Inject faults được xác định trước.
- Theo dõi kết quả từng attempt.
- Xác minh final source state theo logical ID.
- Tách unique business operations khỏi request attempts.
- Lưu expected effect count.
- Có test keys khác nhau và same-key concurrency.

Với kịch bản same-key/different-payload, cố ý thay payload để kiểm `409` và không làm side effect mới.

## 47. Tải được mở và tải đóng có thể cho kết luận khác

**Closed-loop generator:** chỉ gửi request mới sau khi request trước kết thúc. Khi server chậm, tải tự giảm; có thể che overload.

**Open-loop generator:** phát logical commands theo lịch độc lập với response, nhìn rõ queueing và saturation nhưng cần bounded clients/resources.

Cả hai có giá trị, nhưng phải:
- Ghi offered vs completed logical QPS.
- Đo p95/p99 và timeout.
- Không bỏ qua coordinated omission nếu mục tiêu đo tail latency.
- Giữ retry amplification được tách khỏi arrival rate gốc.
- Có warm-up và workload distributions.
- Ghi baseline không lỗi và giai đoạn injection.

Không chỉ nhìn throughput khi API chậm rồi kết luận fault không gây vấn đề.

## 48. Kịch bản tải kết hợp lỗi có thể làm lộ race condition

Một số case:
1. Hai requests cùng operationId đến cùng lúc.
2. Một request commit, response mất; request kia đã bắt đầu xử lý trước khi dedup record hoàn tất.
3. Server crash ở ranh giới business write/idempotency record.
4. Driver retry khi gateway cũng retry.
5. Redis marker hết TTL trong khi request cũ vẫn đang chạy.
6. Database failover khiến readback trả state stale.
7. CDC consumer nhận duplicate event sau restart.
8. Load cao kéo dài làm PROCESSING record timeout rồi worker mới takeover.
9. Client gửi lại command cũ sau nhiều ngày.
10. Shard hot gây timeout dồn vào một tenant.

Các test này tìm lỗi **atomicity và ownership**, không chỉ năng lực xử lý một request.

## 49. Concurrent same-key requests phải quyết định được một winner

~~~text
Client A: POST /orders key=K.
Client B: POST /orders key=K, cùng payload.
~~~

Một thiết kế an toàn có:
- Atomic unique claim/insert cho K.
- Hai requests không cùng chạy business effect.
- Request thứ hai có thể chờ, nhận 202/409-processing hoặc replay saved result tùy contract.
- Key/payload mismatch bị từ chối.
- Crash của winner được recover bằng durable outcome.
- Không cho hai workers takeover không có fencing.

Test phải xác minh cả **effect count** và **response semantics**, không chấp nhận hai order rồi xử lý bằng xóa một order sau đó.

## 50. Fencing khi worker cũ tỉnh lại

Timeline:
~~~text
Worker A claim operation K, lease 30 giây.
A bị pause 40 giây.
Worker B takeover, xử lý K.
A tiếp tục từ pause và gửi write.
~~~

Nếu A vẫn có thể ghi, cả hai có thể thực hiện effect.

Cần:
- Versioned/monotonic fencing token hoặc ownership epoch do nguồn đáng tin cấp.
- Sink kiểm atomic owner/version trước effect.
- Idempotency/unique business identity.
- Reconcile effects đã commit trước takeover.
- Không lấy lease expiration làm bằng chứng worker cũ dừng hẳn.

**Fencing và idempotency bổ sung cho nhau**: fencing kiểm quyền tác nhân còn hợp lệ; idempotency ngăn logical effect lặp.

## 51. Sự kiện gửi downstream cũng phải idempotent

Một order write:
~~~text
Order saved.
Outbox event inserted.
Publisher sends event.
Broker ACK lost.
Publisher sends again.
Consumer receives twice.
~~~

Nếu consumer gửi email hai lần hoặc reserve inventory hai lần, API idempotent vẫn chưa đủ.

Thiết kế:
- Stable eventId.
- Transactional outbox khi engine/atomic scope cho phép.
- Consumer inbox/dedup cùng effect.
- Downstream idempotency keys.
- Replay semantics theo event version.
- Metrics duplicate/skipped/applied.
- Reconciliation khi side effect external outcome unknown.

Kiểm thử F2/F3 ở cả **API → DB**, **DB → outbox**, **outbox → broker**, **broker → consumer**, và **consumer → external provider** nếu workflow yêu cầu.

## 52. Một end-to-end invariant cho checkout

Giả sử logical checkout `C` gồm:
- Một order.
- Một inventory reservation.
- Tối đa một payment capture thành công.
- Một committed OrderCreated event.
- Một e-mail xác nhận theo policy.

Bất biến:
~~~text
count(order by C) == 1 after success.
count(reservation by C) <= 1.
count(successfulPaymentCapture by C) <= 1.
count(logicalOrderCreatedEvents by C) == 1.
No negative inventory.
No duplicate customer charge.
~~~

Trong giai đoạn `PENDING`, có thể chưa có payment/e-mail. Test nên xác định **mốc terminal state** trước khi assert final counts. Nếu một bước chưa chắc outcome, dùng reconciler với provider/backend, không tạo effect mới vô điều kiện.

## 53. Nguồn oracle nào đủ mạnh?

Một kiểm tra chỉ dùng `GET /orders/{id}` có thể đọc từ cache, search index hoặc follower trễ.

Oracle đáng tin hơn cần:
- Authoritative business store.
- Consistency/read concern tương xứng.
- Stable operation/aggregate identity.
- Nếu cần, source transaction/outbox ledger.
- Payment provider state qua API được phân quyền.
- Inventory/reservation store.
- Bounded eventual convergence window.
- Cross-check số lượng effect, không chỉ response body.

Không tự mở quyền đọc toàn bộ production chỉ để test; sử dụng synthetic data/tenant riêng và quyền tối thiểu.

## 54. Durability khác visibility

Một write có thể:
- Được nhận ở primary.
- Ghi vào memory.
- Ghi journal/WAL.
- Replicate đến quorum.
- Visible ở primary.
- Chưa visible ở follower/cache/read model.

Sau F2, client có thể retry rồi readback từ follower trả `not found`. Nếu server hiểu đó là chưa commit và tạo lại order với ID mới, sẽ sinh duplicate.

Test cần:
- Primary/consistent readback theo contract.
- Replica failover.
- Read-your-writes.
- Read concern/consistency level.
- Cache invalidation.
- CDC/search lag.
- Convergence deadline.

**Stale read không phải bằng chứng để phủ nhận một write đã durable ở nơi khác.**

## 55. Failover sau ACK yếu

Một thử nghiệm:
~~~text
Primary nhận write.
Client được ACK ở mức yếu.
Primary lỗi trước khi replica bắt kịp.
Một follower trở thành primary.
Write có thể không còn sau failover tùy engine/contract.
~~~

Ở đây F2 “đã áp dụng” không nhất thiết “đã tồn tại bền qua failover”. Cần phân biệt:
- Lỗi response mất của write đã commit chắc chắn.
- Lỗi primary giữa local apply và majority durability.
- Kết quả client ACK nhưng được phép rollback theo policy yếu.
- Hệ dùng synchronous/quorum ACK để bảo vệ acknowledged writes.

Không gọi tất cả những case này là cùng một lỗi; test names và expected outcomes phải ghi **write concern/durability config**.

## 56. Lỗi xung quanh transaction và batch

Một batch có thể gồm nhiều writes:
~~~text
A succeeded.
B succeeded.
C failed.
D not attempted.
~~~

Nếu SDK/API không có atomic all-or-nothing:
- Client retry toàn batch có thể lặp A/B.
- `partial success` có thể bị bỏ qua khi response mất.
- Dedup phải theo từng item hoặc batch operation semantics.
- Source count có thể khác expected ngay cả khi retry kết thúc.
- Transactional write với outcome unknown vẫn phải reconcile.

Test matrix nên phân biệt **per-item atomicity**, **batch partial failures**, **transaction commit** và **cross-system saga**.

## 57. Một lệnh UPDATE có thể thành công nhưng không thay dữ liệu

Ví dụ:
~~~text
UPDATE product SET status="ACTIVE" WHERE status="ACTIVE".
~~~

Client nhận ACK, nhưng `modifiedCount=0`. Điều này khác:
- Không match entity.
- Conflict do revision.
- Validation reject.
- Operation failed.
- Already in desired state.

API phải định nghĩa `success` theo **business postcondition**, không chỉ một trường result có giá trị 0. Test F2/F3 nên kiểm **postcondition thực**, không đơn thuần đếm `modifiedCount=1`.

## 58. Lỗi authentication và validation không được retry mù

Có những lỗi không cần fault injection:
- 401/403 do token/permission.
- 400 payload invalid.
- 409 payload khác cùng key.
- Document vượt giới hạn.
- Invariant vi phạm.
- Unique conflict do business key khác.

Nếu client retry vô hạn:
- Tăng tải.
- Gây log storm.
- Không giúp sửa lỗi.
- Có thể gây side effects nếu API semantics không rõ.

Test nên xác minh classifier trả **final/repair-needed** tương ứng và không tạo mutation.

## 59. Các trường hợp cần fault injection chính xác hơn

Bên cạnh F1/F2/F3:
- F1a: fail trước serialization.
- F1b: fail sau serialize nhưng trước transport call.
- F2a: fail sau local apply nhưng trước durable ACK.
- F2b: fail sau durable commit nhưng trước outbox publish.
- F2c: fail sau outbox publish nhưng trước checkpoint.
- F3a: drop success response.
- F3b: drop validation/conflict response.
- F3c: delay response vượt client deadline.
- F3d: partial response body.
- F3e: server sends reply nhưng gateway fails before forwarding.
- F4: client nhận success rồi retry do user double-click.

Với mỗi case cần xác định **ground truth** và **expected business invariant**. F4 không phải lỗi mạng nhưng test cùng idempotency rất hữu ích.

## 60. Quan sát một thí nghiệm: schema sự kiện

~~~json
{
  "testCase": "response-drop-after-commit",
  "operationId": "op-552",
  "attemptId": "attempt-1",
  "faultPoint": "DOWNSTREAM_RESPONSE_DROP",
  "serverCommitMilestone": "DURABLE_WRITE_CONFIRMED",
  "clientOutcome": "TIMEOUT",
  "finalBusinessEffectCount": 1,
  "replayResult": "SAME_LOGICAL_ORDER"
}
~~~

Đây là test report minh họa, không ghi raw user payload. Logs nên giữ:
- Stable operation ID.
- Unique attempt ID.
- Fault point/trigger count.
- Commit milestone theo chuẩn test.
- Source transaction reference (opaque).
- Retry reason và attempt number.
- Final oracle state.
- SLO/latency/retry amplification.

Không gắn operationId vào metric label có cardinality vô hạn; dùng restricted structured logs và aggregated metrics.

## 61. Kết quả thử phải mô tả được trường hợp UNKNOWN

Nếu request timeout và harness không chứng minh commit:
~~~text
observedClientOutcome = TIMEOUT.
observedServerCommit = UNKNOWN.
currentSourceState = absent at t0+100 ms.
~~~

Không được tự viết:
~~~text
writeDidNotHappen = true.
~~~

có thể bởi readback stale hoặc write đang in-flight.

Một kết quả tốt nêu **những gì đã đo được**, thời điểm, consistency của readback và timeout quan sát. Nếu chưa thể quyết định, giữ case là `INCONCLUSIVE/REQUIRES_RECONCILIATION`, thay vì gán success/fail cho đẹp báo cáo.

## 62. Timeout không cho phép suy luận nhân quả từ timestamp

Timeline:
~~~text
Client A timeout lúc 12:00:00.800.
Server write event recorded 12:00:00.790.
~~~

Clock drift, log buffering và eventual ingestion có thể làm thứ tự trông khác thật.

Để tạo bằng chứng:
- Đặt hook/correlation IDs trong cùng trusted process.
- Dùng causal milestones (write result → injected fault).
- Ghi source sequence/transaction state.
- Kiểm metrics clock drift.
- Không chỉ ghép logs theo wall-clock gần nhất.

Test failure boundary dựa trên **hàng rào có thể điều khiển**, không phải đoán từ log thời gian.

## 63. Không chạy fault injection ngoài phạm vi đã duyệt

Những hành động như chặn mạng, kill process, làm disk-full, disable replicas có thể gây mất dữ liệu và ảnh hưởng khách hàng nếu chạy sai môi trường.

Một harness tốt:
- Chỉ bật ở test cluster/canary được phê duyệt.
- Dùng synthetic accounts và namespace riêng.
- Có xác thực để điều khiển failpoint.
- Scope theo operationId/attempt, không wildcard.
- Time-box và auto-disable.
- Có resource limits và cleanup.
- Có backup/recovery nếu test tác động storage.
- Không log secrets/PII vào báo cáo.
- Có owner và stop conditions.

Không được dùng production MongoDB failpoints hoặc Redis command disruption tùy tiện chỉ để chứng minh một case.

## 64. Lịch thử theo các mức tải

| Giai đoạn | Tải | Fault | Kỳ vọng |
|---|---|---|---|
| Unit | Một logical command | F1 | Không effect trước retry |
| API integration | Một request | F2 | Commit nhưng reply mất, replay an toàn |
| Network integration | Một request | F3 | Timeout/UNKNOWN, same-key replay |
| Concurrent | 2–100 cùng key | F2/F3 | Một logical effect |
| Mixed workload | Nhiều tenants/keys | Random bounded F1/F2/F3 | Không cross-key interference |
| Soak | Kéo dài | Retry storms/lag | Không tăng duplicate/stuck |
| Failover drill | Controlled node failure | During commit | Durability contract giữ đúng |
| End-to-end | Order + inventory + payment | At each step | Side effects at-most-once theo contract |
| Recovery | Crash/restart | Checkpoint/claim boundary | Reconcile được unknown |
| Expiration | Retry sau retention TTL | Old operation replay | Business dedup policy rõ |

Chỉ nâng mức tải sau khi đã có phép đo oracle và điều kiện dừng; đừng dùng soak test để “hy vọng” phát hiện lỗi logic mà chưa có assertions.

## 65. Thực nghiệm với nhiều retry layers

Một Java service có thể chịu:
~~~text
Browser retry.
API gateway retry.
Service retry.
Database driver retry.
Broker retry.
Consumer retry.
~~~

Không nên cấu hình mỗi tầng tự retry 3 lần rồi quên tổng số attempts và deadline. Cần:
- Chỉ rõ tầng nào được quyền retry thao tác nào.
- Stable operationId xuyên các tầng.
- Request budget truyền xuống dependency.
- Exponential backoff/jitter có giới hạn.
- Không retry non-idempotent commands nếu chưa có dedup.
- Metrics theo retry origin.
- Chặn duplicate side effects ở authoritative sink.

Test F2/F3 nên bật từng layer riêng và phối hợp để nhìn retry amplification.

## 66. Một bảng câu hỏi trước khi chấp nhận hệ đúng

1. Với lỗi **chắc chắn trước gửi**, server không có effect trước retry chứ?
2. Với lỗi **sau durable commit**, retry có tạo record mới không?
3. Khi response thành công bị drop, client có giữ key cũ không?
4. Khi response thất bại bị drop, client có tự tạo effect sai không?
5. Hai requests cùng key cùng lúc có một owner/effect không?
6. Cùng key khác payload có bị conflict không?
7. Một worker crash sau commit trước lưu result có được reconcile không?
8. Idempotency record có cùng atomic boundary với business effect không?
9. Nếu không cùng boundary, failure recovery path là gì?
10. Khi driver/gateway cùng retry, tổng attempts có giới hạn không?
11. Counter/inventory/payment có bị nhân đôi không?
12. Event/outbox/consumer có dedup không?
13. Readback oracle có đủ consistency để kết luận không?
14. Failover có giữ durability đúng write concern không?
15. Retention key/operation records có dài hơn retry window cần thiết không?
16. Old replay sau TTL sẽ tạo duplicate hay bị chặn bởi business unique key?
17. Logs có ghi đúng fault milestone và outcome unknown không?
18. p99/error/throughput có đạt SLO khi fault load không?
19. Security/tenant scope có bị lộ hoặc trộn key không?
20. Có runbook sửa những `UNKNOWN` operations kéo dài không?

## 67. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
|---|---|---|
| Timeout = chưa ghi | Server có thể đã commit | UNKNOWN + retry/reconcile |
| HTTP 500 = rollback | Serialize response có thể fail sau commit | Check authoritative state |
| Connection reset chắc chưa gửi | Request có thể đến đủ | Hook trước send mới chắc |
| Write apply = durable | RAM/ACK/replication khác nhau | Định nghĩa milestone |
| Có replica là không mất write | ACK yếu có thể rollback | Durability policy |
| `GET` không thấy = chưa commit | Read có thể stale | Consistent oracle |
| Retry luôn tạo UUID mới | Biến một intent thành nhiều commands | Stable operationId |
| Idempotency header tự đủ | Server cần atomic dedup | Key+fingerprint+result |
| Redis SET NX đủ cho MongoDB effect | Hai stores không atomic | Source-side unique claim |
| Retryable driver = HTTP idempotency | Khác phạm vi | Business-level identity |
| Exact-once delivery tự có | At-least-once phổ biến | Idempotent effects |
| Checkpoint trước apply nhanh hơn | Có thể mất event | Apply then checkpoint |
| Checkpoint sau apply chống trùng | Crash tạo replay | Dedup/version guards |
| Retry INCR không gây hại | Counter có thể tăng hai lần | Operation ledger |
| Delete luôn idempotent end-to-end | Audit/event có thể lặp | Check all side effects |
| Same-key concurrency tự tuần tự | Race tạo hai effects | Atomic claim/fencing |
| Lease hết nghĩa worker chết | Paused worker có thể tỉnh | Sink-side fencing |
| F2 có thể mô phỏng bằng sleep | Không xác minh commit | Hook sau ACK milestone |
| Drop mọi network gói = F3 | Request có thể chưa đến | Reverse direction proxy |
| HTTP response lost nghĩa server success | Có thể response là lỗi | Ground truth/oracle |
| Test assertThrows là đủ | Chỉ thấy client exception | State oracle |
| Cùng count là đủ | Không biết duplicate payments | Multi-store invariants |
| One retry policy cho mọi lỗi | Validation/auth errors vô ích | Error classification |
| Nhiều retries tăng độ tin cậy mãi | Retry storm | Bounded budgets |
| Retry QPS = business QPS | Attempts khác logical commands | Measure separately |
| Closed-loop đo được mọi overload | Tải tự giảm khi chậm | Open-loop khi thích hợp |
| Một timeout đo được thứ tự commit | Clock drift/log buffering | Causal milestones |
| ACK success là mọi cache đã mới | Eventual projections có lag | Read/write contract |
| Test trên mock DB là đủ | Không có failover/durability | Real integration tests |
| Source DB dedup bảo vệ payment | External side effect riêng | Provider idempotency |
| Kết quả UNKNOWN phải coi fail | Có thể đã commit | Reconciliation |
| Fault injection production không cần scope | Có thể gây outage | Isolated controlled test |

## 68. Bài tập thực hành

### Bài tập 1 — Ba điểm lỗi

Vẽ timeline client/network/server cho F1 trước gửi, F2 sau durable commit và F3 mất phản hồi. Ở mỗi case, ghi điều client biết và điều oracle cần xác minh.

### Bài tập 2 — Không gửi được request

Một interceptor ném lỗi trước transport call. Viết test chứng minh server ingress 0 trước retry và business effect đúng 1 sau retry.

### Bài tập 3 — Sau áp dụng ghi

API đã commit order, process crash trước `201 Created`. Giải thích tại sao Java timeout không chứng minh rollback.

### Bài tập 4 — Mất HTTP response

Proxy drop response sau server trả. Nếu response thật là 409 chứ không phải 201, client nên xử lý thế nào?

### Bài tập 5 — UNKNOWN outcome

Một write timeout và readback từ replica không tìm thấy. Vì sao không được kết luận write không xảy ra? Nêu cách đối soát.

### Bài tập 6 — Idempotency key

Thiết kế key theo verified tenant, operation type và stable key. Cùng key khác payload phải xử lý thế nào?

### Bài tập 7 — Duplicate order

Client tạo UUID mới mỗi retry. Hãy sửa client và server để một logical checkout chỉ tạo một order.

### Bài tập 8 — Atomic outcome

Server ghi order rồi mới ghi idempotency record. Chèn crash ở mọi mốc, nêu nơi có thể tạo duplicate và cách sửa.

### Bài tập 9 — MongoDB unique create

Thiết kế deterministic order ID + unique index. Test duplicate key, readback, fingerprint mismatch và failover.

### Bài tập 10 — MongoDB transaction

Commit response bị mất. So sánh retry commit với retry một business command hoàn toàn mới và nêu điều kiện cần idempotency.

### Bài tập 11 — DynamoDB conditional write

PutItem có `attribute_not_exists` thành công nhưng phản hồi bị drop. Retry gặp conditional failure. Làm sao phân biệt replay hợp lệ và conflict khác?

### Bài tập 12 — DynamoDB ClientRequestToken

Phân biệt idempotency token của transaction API với business-level operation key cần bảo vệ một checkout lâu hơn.

### Bài tập 13 — Cassandra WriteTimeout

Coordinator timeout với RF=3 và consistency level đã chọn. Vì sao write vẫn có thể tồn tại ở replicas? Thiết kế readback test.

### Bài tập 14 — Cassandra LWT

Claim `IF NOT EXISTS` thành công, process crash trước business effect. Thiết kế recovery tránh operation kẹt và double execution.

### Bài tập 15 — Redis INCR

Redis tăng counter, reply mất, client retry. Chứng minh counter tăng hai lần và đề xuất script/dedup protocol.

### Bài tập 16 — Redis marker khác Mongo effect

`SET NX` thành công nhưng Mongo write fail; lần khác Mongo success nhưng Redis marker bị mất. Phân tích hai failure windows.

### Bài tập 17 — Inventory decrement

Một reservation `qty=1` được gửi lại sau timeout. Thiết kế reservationId, unique constraint và stock guard chống trừ hai lần.

### Bài tập 18 — Payment capture

Payment provider commit rồi response mất. Phân biệt database idempotency và provider idempotency; nêu cách reconcile không charge lại.

### Bài tập 19 — Concurrent same-key

Cho 100 requests cùng key đến một lúc. Test điều gì về winner, payload fingerprint, PROCESSING state, replay và effect count?

### Bài tập 20 — Worker takeover

Worker A pause quá lease, B xử lý rồi A tỉnh. Thiết kế fencing/atomic condition để không có hai effects.

### Bài tập 21 — At-least-once CDC

Consumer apply event rồi crash trước checkpoint. Làm sao phát lại event mà vẫn chỉ có một business effect?

### Bài tập 22 — Oracle độc lập

Một API GET dùng Redis cache và follower eventual. Vì sao không đủ để kết luận write chưa commit? Chọn oracle có consistency phù hợp.

### Bài tập 23 — Weak ACK failover

Một leader ACK write ở mức yếu, sau đó crash. Thiết kế matrix giữa write concern, primary/follower reads và durability expectations.

### Bài tập 24 — HTTP error classifier

Phân loại timeout, connection reset, 400, 401, 403, 409, 429, 503 thành retry/reconcile/final theo contract; giải thích các ngoại lệ.

### Bài tập 25 — Retry amplification

10.000 commands/s, 10% timeout, mỗi command timeout thêm hai attempts. Tính attempts/s và nêu tác động nếu các retries tiếp tục timeout.

### Bài tập 26 — Backoff

Thiết kế bounded exponential backoff với jitter và deadline cho Java API, giữ cùng operationId qua attempts.

### Bài tập 27 — Open-loop vs closed-loop

So sánh hai load generators khi F2/F3 làm p99 tăng; ghi những metrics cần có để không nhầm giảm QPS với hệ đã ổn.

### Bài tập 28 — Fault timing

Một proxy tắt cả mạng trước request rồi team gọi test “response lost after commit”. Vì sao không hợp lệ? Thiết kế test hook/proxy đúng chiều.

### Bài tập 29 — Kết quả không chắc

Test thấy client timeout, source read ở 100 ms chưa thấy record. Viết report ghi uncertainty, observation timestamps, read consistency và bước reconcile.

### Bài tập 30 — Batch partial success

Một batch ghi A/B thành công, C lỗi, D chưa gửi; response bị mất. Thiết kế per-item IDs, result tracking và safe retry.

### Bài tập 31 — End-to-end checkout

Vẽ đường order → inventory → payment → outbox → email. Inject F2/F3 sau từng bước, chỉ ra các idempotency/compensation obligations.

### Bài tập 32 — Fault injection an toàn

Thiết kế test harness có synthetic tenant, failOnce per operation, automatic cleanup, limits, observability và stop conditions; nêu vì sao không nên bật production failpoints.

### Bài tập 33 — Bảng báo cáo

Tạo báo cáo có `operationId`, `attemptId`, fault phase, server commit milestone, client observed outcome, retry count, source state, side effects, oracle consistency và final pass/fail/inconclusive.

### Bài tập 34 — Tổng hợp đa NoSQL

Một hệ Java API dùng MongoDB orders, DynamoDB preferences, Cassandra activity, Redis counters và một payment provider. Xây kế hoạch kiểm thử:

1. F1/F2/F3 và ground truth ở mỗi lớp.
2. Stable operation identity, tenant scope, fingerprint.
3. Database atomicity và durability boundaries.
4. Conditional writes, retryable writes, LWT và Redis script limits.
5. Same-key concurrency, failover, leases/fencing.
6. End-to-end side-effect dedup/outbox.
7. Readback consistency, event replay và reconciliation.
8. Timeout/retry budgets và load generator semantics.
9. Bảo mật synthetic data, giới hạn fault injection.
10. Metrics, exit conditions, unknown outcomes và runbooks.

### Bài tập 35 — Phản biện chiến lược sai

Một đội thiết kế:

~~~text
Mọi timeout nghĩa database chưa ghi.
Client retry bằng UUID mới.
Idempotency chỉ là header; server không lưu key.
Redis SET NX làm marker, sau đó ghi MongoDB và coi atomic.
Driver tự retry nên API không cần xử lý duplicate.
F2 test bằng cách sleep 100ms rồi kill random pod.
F3 test bằng ngắt mạng hai chiều trước khi gửi request.
Sau retry chỉ assert API trả HTTP 200.
Không kiểm payment, inventory hoặc outbox.
Cứ retry mãi cho tới khi hết lỗi.
~~~

Chỉ ra từng lỗi, failure window và thay bằng thiết kế **chèn lỗi đúng mốc, idempotency business-level, durable result, retry bounded, reconciliation và kiểm toàn bộ side effects**.

---

**Kết luận:** Mô phỏng lỗi quanh thao tác ghi NoSQL phải tách rõ **trước khi gửi**, **sau khi write thực sự áp dụng/commit theo một durability contract được kiểm chứng**, và **trước khi client nhận được phản hồi**. Trong hai trường hợp sau, một timeout có thể che giấu write đã thành công; trong trường hợp phản hồi bị mất, client không thể tự suy outcome chỉ từ exception. Muốn thử đúng, phải có **fault hook ở mốc nhân quả, proxy chặn đúng chiều, operationId ổn định, idempotent hoặc conditional writes, durable dedup/result evidence và readback oracle độc lập**. Hệ đáng tin không chỉ retry được, mà còn ngăn **tạo đơn hàng, trừ tồn kho, thanh toán và phát event lặp**, chịu failover và tải cao, đồng thời biết báo `UNKNOWN` và đối soát khi chưa đủ bằng chứng. **Timeout không phải rollback; retry an toàn là một tính chất được thiết kế và kiểm thử, không phải hy vọng của client.**

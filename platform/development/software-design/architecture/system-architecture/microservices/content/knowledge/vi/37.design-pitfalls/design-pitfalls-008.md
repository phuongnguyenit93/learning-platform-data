# Thử lại không giới hạn và nhân đôi thao tác nghiệp vụ

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Sai lầm thiết kế  
> **Mục tiêu:** Hiểu vì sao retry vô hạn hoặc retry thiếu kiểm soát có thể làm quá tải hệ thống, tạo giao dịch và side effects trùng lặp; thiết kế retry có giới hạn, idempotency, deduplication, timeout, backoff và quy trình xử lý outcome không xác định.

## 1. Retry là gì và vì sao hệ thống cần retry?

Retry là việc thử thực hiện lại một thao tác sau khi lần thực hiện trước không thành công hoặc không nhận được kết quả đáng tin cậy.

Trong hệ thống phân tán, lỗi tạm thời có thể xảy ra vì:

- Network packet bị mất hoặc kết nối bị reset.
- Service đích tạm thời quá tải.
- Database failover hoặc connection pool hết kết nối.
- Message broker rebalance hoặc consumer restart.
- DNS, TLS handshake hoặc service discovery gặp lỗi.
- External provider trả 429, 503 hoặc timeout.
- Một transaction bị deadlock hoặc serialization conflict.
- Pod bị restart trong lúc request đang xử lý.

Retry có thể tăng khả năng hoàn thành thao tác khi lỗi thực sự tạm thời. Nhưng nếu retry không có giới hạn, không phân loại lỗi và không bảo vệ side effects, nó có thể làm hệ thống tệ hơn.

Ví dụ một request tạo payment:

~~~text
Order Service
     |
     | POST /payments
     v
Payment Service
     |
     | charge provider
     v
External Payment Provider
~~~

Provider đã charge thành công nhưng response bị mất trên đường về. Order Service thấy timeout và gửi lại POST. Nếu Payment không có idempotency, khách hàng có thể bị charge hai lần.

**Timeout chỉ nói rằng caller chưa nhận được kết quả trong thời hạn. Nó không chứng minh thao tác phía server chưa xảy ra.**

## 2. Sai lầm: Thử lại không giới hạn

Một vòng lặp retry vô hạn có thể trông đơn giản:

~~~text
while request fails:
    send request again
~~~

Nhưng khi dependency đang lỗi, vòng lặp tạo thêm traffic vào chính dependency đang yếu nhất.

Hậu quả:

- Request queue tăng nhanh.
- Connection pool bị chiếm bởi các request retry.
- CPU tốn cho serialization, TLS, logging và xử lý lỗi lặp.
- Downstream tiếp tục quá tải và thời gian phản hồi dài hơn.
- Caller timeout rồi tạo thêm retry.
- Nhiều service cùng retry tạo thành retry storm.
- Một lỗi nhỏ lan thành outage toàn hệ thống.
- Các thao tác nghiệp vụ có side effects bị thực hiện nhiều lần.

~~~text
Normal load
    |
    v
Dependency slows down
    |
    v
Requests time out
    |
    v
Callers retry immediately
    |
    v
More load on slow dependency
    |
    v
More timeouts and retries
    |
    +------> Retry storm
~~~

Retry vô hạn cũng giữ tài nguyên quá lâu: threads, memory, sockets, database connections và message leases. Một request không còn giá trị với người dùng vẫn có thể tiếp tục tiêu tốn capacity.

**Retry phải có giới hạn về số lần, thời gian và tổng tài nguyên được phép sử dụng.**

## 3. Sai lầm: Retry một thao tác không idempotent

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng ý định mà trạng thái cuối tương đương một lần thực hiện.

Ví dụ:

- Đặt trạng thái một resource thành INACTIVE có thể idempotent nếu cùng điều kiện và semantics.
- Đọc một record thường không tạo side effect nghiệp vụ.
- Tăng số dư thêm 100.000 là không idempotent nếu mỗi lần gọi đều cộng thêm.
- Tạo đơn hàng mới có thể tạo nhiều đơn nếu mỗi lần request sinh ID mới.
- Gửi email, phát hành coupon hoặc tạo shipment có thể bị lặp.
- Charge thẻ có thể tạo nhiều giao dịch tiền thật.

Ví dụ:

~~~text
Request 1: POST /orders
  -> Order ORD-1001 created
  -> Response lost

Retry:
  -> Order ORD-1002 created
  -> Response received

Result:
  One user intent, two orders
~~~

Caller chỉ biết lần đầu timeout. Nếu endpoint không hỗ trợ idempotency, retry có thể tạo ra một nghiệp vụ mới.

**Idempotency là một thuộc tính của contract và implementation, không phải điều tự động có được khi dùng HTTP hoặc message broker.**

## 4. Phân biệt delivery attempt, request attempt và business operation

Ba khái niệm này cần được tách biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Delivery attempt** | Một lần message được broker chuyển tới consumer | Broker giao event lần thứ hai sau khi consumer chưa ack |
| **Request attempt** | Một lần caller gửi HTTP/gRPC request | Client gửi lại sau timeout |
| **Business operation** | Ý định nghiệp vụ duy nhất cần được thực hiện | Khách hàng muốn thanh toán đơn ORD-1001 |

Một business operation có thể có nhiều request attempts và delivery attempts. Hệ thống phải bảo đảm các attempts cùng một ý định không tạo nhiều side effects ngoài mong muốn.

Đừng dùng số lần message delivery làm số lượng payment thật. Cần có business operation ID hoặc provider transaction reference để nhận diện thao tác nghiệp vụ.

## 5. Retry không phải giải pháp cho mọi lỗi

Phân loại lỗi trước khi retry:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| **Transient network error** | Connection reset, temporary DNS failure | Có thể retry bounded |
| **Temporary overload** | 503, 429 | Tuân thủ backoff, Retry-After và budget |
| **Concurrency conflict** | Deadlock, serialization failure | Retry transaction nếu có thể chạy lại an toàn |
| **Validation error** | Thiếu field, amount không hợp lệ | Không retry nếu input không đổi |
| **Authentication error** | Token hết hạn/sai issuer | Refresh hoặc sửa credentials theo policy; không lặp vô hạn |
| **Authorization error** | 403 do thiếu quyền | Không retry mù |
| **Business rejection** | Không đủ tồn kho, payment declined | Không retry cùng request như lỗi mạng |
| **Resource not found** | Order không tồn tại | Không retry vô hạn |
| **Unknown outcome** | Timeout sau khi gửi thao tác có side effect | Tra cứu trạng thái trước khi quyết định |
| **Permanent configuration error** | Sai endpoint, schema hoặc secret | Dừng và cảnh báo owner |

HTTP 5xx không phải lúc nào cũng retry được. Một server có thể trả 500 sau khi đã commit database nhưng lỗi khi tạo response. Tương tự, một số 4xx có thể là transient theo contract, nhưng cần được quy định cụ thể.

**Retryability phải được định nghĩa theo semantics của operation và error code**, không chỉ theo việc status code lớn hơn 499.

## 6. Bounded retries: Giới hạn số lần thử

Một policy retry cần có:

- Maximum attempts.
- Total deadline.
- Per-attempt timeout.
- Backoff schedule.
- Jitter.
- Retryable error classification.
- Retry budget.
- Cancellation behavior.
- Final failure handling.

Ví dụ:

~~~text
Maximum attempts: 3 total (1 initial + 2 retries)
Per-attempt timeout: 1 second
Backoff base: 100 ms
Backoff cap: 500 ms
Jitter: enabled
Total operation deadline: 3 seconds
~~~

Các con số chỉ là ví dụ. API người dùng có thể cần deadline ngắn; batch job có thể chấp nhận nhiều attempts và thời gian dài hơn. Không áp một policy cho mọi workload.

Cần làm rõ **maximum attempts** có tính lần đầu hay chỉ tính retry. Nếu cấu hình "3 retries" thường có thể là tổng cộng 4 attempts. Tên cấu hình phải tránh mơ hồ.

## 7. Exponential backoff

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại:

~~~text
delay(n) = min(cap, base × 2^n)
~~~

Ví dụ base 100 ms và cap 2 giây:

| Lần retry | Delay trước jitter |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |
| 6 | 2.000 ms (cap) |

Backoff giúp giảm tần suất gọi lại khi dependency đang hồi phục. Nhưng nếu mọi client cùng retry đúng các mốc 100, 200, 400 ms, traffic vẫn có thể dồn thành đợt.

## 8. Jitter: Tránh retry đồng bộ

Jitter thêm độ ngẫu nhiên vào delay để các clients không retry cùng lúc.

Một dạng full jitter:

~~~text
delay = random(0, min(cap, base × 2^attempt))
~~~

Một số biến thể khác có thể cộng hoặc nhân một khoảng random quanh backoff. Điều quan trọng là chọn một policy nhất quán, giới hạn delay và test được.

Ví dụ 10.000 clients cùng timeout:

~~~text
Without jitter:
  10.000 retries at approximately the same instant

With jitter:
  retries spread across a bounded time window
~~~

Jitter không thay maximum attempts hoặc deadline. Một client vẫn có thể tạo tải lớn nếu được phép retry vô hạn.

## 9. Total deadline và per-attempt timeout

Hai giới hạn này có vai trò khác nhau:

- **Per-attempt timeout:** thời gian tối đa chờ một lần gọi.
- **Total deadline:** thời gian tối đa cho toàn bộ operation, gồm attempts và backoff.

Ví dụ:

~~~text
Total deadline: 3 seconds

Attempt 1: 700 ms
Backoff:   100 ms
Attempt 2: 700 ms
Backoff:   200 ms
Attempt 3: 700 ms
-------------------
Total:    2.400 ms
~~~

Nếu caller còn 500 ms deadline, không nên bắt đầu một attempt mới có timeout 2 giây. Deadline cần được truyền qua các tầng để downstream không làm việc lâu hơn thời gian caller còn chờ.

Khi deadline hết:

- Dừng tạo attempts mới.
- Hủy công việc có thể hủy an toàn.
- Giải phóng connections/threads.
- Ghi nhận outcome là failed hoặc unknown theo semantics.
- Không mặc định server-side operation đã bị rollback.

Cancellation ở client không nhất thiết dừng transaction đã commit trên server hoặc request đã tới external provider.

## 10. Retry budget: Giới hạn tổng lượng retry của hệ thống

Maximum attempts cho từng request vẫn có thể tạo ra lượng retry khổng lồ khi traffic đầu vào tăng.

Retry budget giới hạn phần traffic retry so với traffic gốc trong một cửa sổ thời gian hoặc theo một cơ chế token budget.

Ví dụ:

~~~text
Original requests: 100.000 / minute
Retry budget: 5% of original traffic
Maximum retry attempts admitted: 5.000 / minute
~~~

Đây là ví dụ policy, không phải giá trị chuẩn cho mọi hệ thống.

Có thể áp dụng:

- Budget theo service/dependency.
- Budget theo tenant hoặc priority class nếu cần.
- Global retry quota cho client library.
- Giảm hoặc ngừng retries khi error rate tăng.
- Ưu tiên traffic mới có giá trị hơn retries cũ.
- Alert khi budget cạn.

Retry budget giúp bảo vệ dependency khi outage kéo dài. Nếu budget hết, caller có thể fail fast hoặc đưa tác vụ vào durable queue theo contract.

## 11. Tránh retry ở mọi tầng

Một lỗi phổ biến là mỗi tầng đều tự retry:

~~~text
Mobile client: 3 attempts
    |
API Gateway: 3 attempts
    |
Order Service: 3 attempts
    |
Payment Client: 3 attempts
    |
Payment Service: 3 attempts
~~~

Trong trường hợp xấu, số attempts có thể nhân lên theo từng tầng. Bốn tầng mỗi tầng tối đa 3 attempts có thể tạo tới 81 lời gọi ở tầng cuối, tùy cách lồng retry.

Cần xác định **retry owner** cho mỗi dependency boundary:

- Client có thể retry request nếu contract idempotent và deadline cho phép.
- Gateway thường nên tránh retry các operation có side effects nếu không hiểu idempotency semantics.
- Service có thể retry dependency tạm thời trong budget của request.
- Message consumer có retry policy riêng theo delivery model.
- External provider integration cần tuân theo provider's retry/rate-limit contract.

Không phải mọi tầng đều phải retry. Retry phải được thiết kế end-to-end với deadline và budget chung.

## 12. Idempotency key là gì?

Idempotency key là một định danh do caller cung cấp hoặc được tạo cho một business intent duy nhất. Server dùng key để nhận biết các attempts là cùng một thao tác.

Ví dụ:

~~~http
POST /payments
Idempotency-Key: checkout-ORD-1001-attempt-1
Content-Type: application/json

{
  "orderId": "ORD-1001",
  "amountMinor": 590000,
  "currency": "VND"
}
~~~

Nếu request được gửi lại với cùng key và cùng payload theo contract, server trả lại kết quả đã ghi nhận hoặc trạng thái operation hiện có, thay vì thực hiện charge lần nữa.

Một key cần:

- Phạm vi uniqueness rõ: tenant, merchant, endpoint hoặc operation.
- Được tạo ổn định cho cùng một ý định.
- Không tái sử dụng cho một thao tác mới.
- Gắn với payload fingerprint hoặc các trường bất biến.
- Có retention/expiry phù hợp với retry horizon và nghiệp vụ.
- Được lưu bền vững, không chỉ ở memory.
- Có trạng thái processing/succeeded/failed/unknown theo model.
- Có behavior rõ khi cùng key nhưng payload khác.

Không dùng timestamp hiện tại hoặc random UUID mới ở mỗi retry. Làm vậy mỗi attempt sẽ có key khác và không deduplicate được.

## 13. Idempotency store và state machine

Một bảng idempotency có thể chứa:

~~~text
idempotency_records
  scope
  idempotency_key
  request_hash
  operation_id
  status
  response_reference
  created_at
  expires_at
~~~

Unique constraint nên được áp dụng trên scope và key theo thiết kế:

~~~sql
CREATE UNIQUE INDEX uq_idempotency_scope_key
ON idempotency_records(scope, idempotency_key);
~~~

State machine minh họa:

~~~text
NEW
 |
 v
PROCESSING
 |       \
 |        \--> UNKNOWN
 v
SUCCEEDED
 |
 +--> repeated request returns stored result/reference
~~~

Các trạng thái terminal và retry behavior cần định nghĩa. Một thao tác thất bại do validation trước khi tạo side effect có thể được lưu FAILED. Một timeout khi gọi provider có thể cần UNKNOWN cho tới khi reconciliation xác định kết quả.

**Không xóa idempotency record quá sớm.** Nếu caller retry sau khi record hết hạn, một charge cũ có thể bị thực hiện lại. Retention phải dài ít nhất theo retry window, provider idempotency window và business recovery policy.

## 14. Xử lý cùng key nhưng payload khác

Giả sử cùng idempotency key được gửi với amount khác:

~~~text
Attempt 1:
  key=K1001
  amount=590000 VND

Attempt 2:
  key=K1001
  amount=690000 VND
~~~

Server không nên âm thầm trả kết quả cũ hoặc thực hiện thao tác mới. Đây là xung đột contract.

Có thể trả một error code ổn định như IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST và ghi audit phù hợp.

Payload fingerprint nên dựa trên canonicalized fields có ý nghĩa nghiệp vụ, không nhất thiết hash raw JSON bytes vì thứ tự field/whitespace có thể khác. Cần định nghĩa những field nào là immutable.

## 15. Atomicity giữa idempotency record và side effect

Một lỗi tinh vi:

1. Server lưu idempotency key.
2. Server gọi payment provider.
3. Provider charge thành công.
4. Server crash trước khi lưu kết quả.
5. Retry thấy key đang PROCESSING hoặc record không có kết quả.
6. Nếu gọi provider lại, có thể charge trùng.

Giải pháp phụ thuộc side effect:

- Dùng idempotency key của chính provider nếu được hỗ trợ.
- Persist operation intent trước khi gọi provider.
- Lưu provider reference khi nhận được.
- Dùng transactional outbox cho các bước nội bộ.
- Có trạng thái UNKNOWN và reconciliation query.
- Không tự chuyển UNKNOWN thành FAILED chỉ vì timeout.
- Có worker tiếp tục hoàn tất hoặc xác định trạng thái.

Một local database transaction không thể bao trùm atomicity với một external payment provider. Phải thiết kế workflow có thể phục hồi sau crash ở từng bước.

## 16. Payment: Timeout không đồng nghĩa charge thất bại

Ví dụ:

~~~text
Order Service
   |
   | Charge 590000 VND, key K1001
   v
Payment Service
   |
   | Provider processes charge
   v
Provider: SUCCESS
   |
   | Response lost
   X
Payment Service sees timeout
~~~

Payment Service không thể kết luận transaction thất bại. Trạng thái phù hợp có thể là UNKNOWN/PENDING_RECONCILIATION.

Quy trình:

1. Giữ operation ID và idempotency key.
2. Tra cứu provider theo reference/key nếu API hỗ trợ.
3. Kiểm tra webhook/event có đến muộn không.
4. Đối soát ledger nội bộ và provider statement.
5. Chỉ retry charge khi có bằng chứng và policy xác nhận an toàn.
6. Cập nhật Order qua event/command có idempotency.
7. Ghi audit và xử lý exception nếu outcome không thể xác định.

Không tạo payment attempt mới với key mới chỉ vì caller timeout. Một request retry phải đại diện cho cùng ý định nếu đó là cùng một checkout attempt.

## 17. HTTP method không tự bảo đảm idempotency nghiệp vụ

HTTP định nghĩa semantics cho một số methods:

- GET thường được thiết kế safe và idempotent.
- PUT và DELETE có semantics idempotent theo HTTP contract.
- POST thường không mặc định idempotent.
- PATCH phụ thuộc operation và patch semantics.

Nhưng method name không đủ để chứng minh implementation đúng. Một PUT có thể gửi email mỗi lần, hoặc DELETE có thể tạo side effect phụ lặp lại nếu code không được thiết kế idempotent.

Một endpoint POST vẫn có thể hỗ trợ idempotency key. Ngược lại, một endpoint GET mà vô tình thay đổi trạng thái nghiệp vụ là thiết kế sai.

**Hãy định nghĩa idempotency theo business operation và contract**, đồng thời tuân thủ HTTP semantics để clients biết khi nào retry.

## 18. Database transaction và retry an toàn

Một transaction có thể thất bại vì deadlock hoặc serialization conflict. Trong một số DBMS, retry toàn bộ transaction là cách xử lý hợp lệ nếu:

- Transaction chưa commit.
- Logic có thể chạy lại an toàn.
- Không có external side effect bên trong transaction.
- Input và expected version còn hợp lệ.
- Retry có giới hạn.
- Các unique constraints bảo vệ duplicate operations.

Ví dụ pseudocode:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    begin transaction
    try:
        validate current state
        apply domain changes
        commit
        return success
    catch retryable transaction conflict:
        rollback
        wait bounded backoff
        continue
    catch permanent error:
        rollback
        return failure

return retryable failure
~~~

Không gửi email, charge provider hoặc publish message trực tiếp bên trong transaction rồi retry toàn bộ transaction. Nếu transaction rollback nhưng side effect bên ngoài đã xảy ra, lần chạy lại có thể tạo side effect trùng.

Dùng outbox hoặc ghi nhận intent để tách database commit khỏi external delivery.

## 19. Optimistic concurrency và expected version

Idempotency ngăn lặp cùng một ý định; optimistic concurrency bảo vệ trước các cập nhật cạnh tranh.

Ví dụ update một order:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

Nếu số rows cập nhật bằng 0, record có thể đã thay đổi hoặc không còn ở version kỳ vọng. Caller phải đọc trạng thái mới và quyết định theo domain rules.

Không retry lệnh UPDATE vô điều kiện khi gặp conflict. Có thể ghi đè một thay đổi mới hơn hoặc làm sai state transition.

Một operation idempotent và một operation version-checked giải quyết hai vấn đề khác nhau; nhiều workflow cần cả hai.

## 20. Message broker: At-least-once và duplicate delivery

Nhiều hệ thống message broker phổ biến cung cấp delivery semantics at-least-once trong cấu hình thông thường. Consumer có thể nhận lại message khi:

- Xử lý xong nhưng chưa ack/commit offset.
- Consumer crash sau khi ghi DB nhưng trước khi commit offset.
- Rebalance làm message được giao lại.
- Network timeout khiến broker không biết ack đã đến chưa.
- Retry/DLQ workflow đưa message quay lại queue.

~~~text
Broker delivers Event E1
        |
        v
Consumer updates database
        |
        X crash before ack/offset commit
        |
        v
Broker redelivers E1
        |
        v
Consumer sees E1 again
~~~

Consumer phải có idempotent processing hoặc deduplication bền vững. Không giả định message chỉ đến một lần.

## 21. Inbox/deduplication pattern cho consumer

Một inbox table có thể ghi nhận event đã xử lý:

~~~text
processed_messages
  consumer_name
  event_id
  processed_at

UNIQUE(consumer_name, event_id)
~~~

Một transaction consumer:

~~~text
BEGIN
  INSERT processed_messages(consumer_name, event_id)
  ON CONFLICT DO NOTHING

  if insert did not happen:
      COMMIT
      return already_processed

  apply projection/business update
COMMIT

ack/commit broker offset
~~~

Điều quan trọng là **dedup record và business database update phải nằm trong cùng transaction** nếu cùng database. Nếu ghi dedup trước rồi crash trước business update, redelivery có thể bị bỏ qua dù nghiệp vụ chưa được áp dụng.

Nếu side effect nằm ngoài database, cần provider idempotency hoặc workflow/outbox tương ứng. Inbox table không thể tự làm cho email hoặc payment provider exactly-once.

## 22. Outbox pattern và publish retries

Producer có thể commit business state và event intent cùng một transaction:

~~~text
BEGIN
  UPDATE orders ...
  INSERT INTO outbox(event_id, event_type, payload)
COMMIT
~~~

Relay đọc outbox và publish lên broker. Nếu publish thành công nhưng relay crash trước khi đánh dấu delivered, event có thể được publish lại.

Do đó:

- Event cần stable event_id.
- Relay cần checkpoint/retry bounded theo policy.
- Consumer phải idempotent.
- Outbox rows cần retention/cleanup có kiểm soát.
- Monitoring phải có pending age và delivery lag.
- Dead-letter/failed publish cần owner và runbook.

Outbox giải quyết atomicity giữa business write và event intent trong database. Nó không tự cung cấp exactly-once side effects xuyên broker và mọi consumer.

## 23. Exactly-once: Tránh hiểu sai thuật ngữ

Một broker hoặc stream processor có thể cung cấp exactly-once semantics trong phạm vi transaction và state store được hỗ trợ. Nhưng điều đó không tự đảm bảo toàn bộ business workflow chỉ xảy ra đúng một lần qua:

- HTTP clients.
- Database.
- Broker.
- Payment provider.
- Email/SMS vendor.
- Shipping carrier.
- External APIs.

Một transaction broker có thể commit offset và output record cùng nhau, nhưng nếu consumer đã gọi external provider trước khi transaction commit, provider side effect có thể đã xảy ra dù broker rollback.

Vì vậy, cần nói rõ **exactly-once trong boundary nào**. Với external side effects, thường phải kết hợp idempotency keys, deduplication, transactional outbox/inbox và reconciliation.

## 24. Queue retries, visibility timeout và poison messages

Với work queues, message có thể được giao lại khi consumer không ack trước visibility timeout hoặc lease expiry.

Cần thiết kế:

- Visibility/lease timeout lớn hơn thời gian xử lý hợp lý hoặc có heartbeat extension.
- Bounded delivery count.
- Exponential backoff và jitter nếu broker hỗ trợ hoặc worker điều phối.
- DLQ sau số lần thử hoặc điều kiện phù hợp.
- Redrive policy có kiểm soát.
- Idempotent handler.
- Alert cho age/depth của DLQ.
- Quy trình xử lý poison message.
- Retention phù hợp với business value.

Một message luôn lỗi do payload sai sẽ không tự trở nên hợp lệ sau 1.000 lần retry. Nó cần quarantine, sửa producer/contract hoặc xử lý thủ công.

DLQ không phải thùng rác để quên. Cần owner, alert, replay policy và audit.

## 25. Retry-After và rate limiting

Khi dependency trả 429 hoặc 503 kèm Retry-After, client nên tuân thủ contract nếu giá trị hợp lệ và nằm trong deadline/budget.

Cần chú ý:

- Retry-After có thể là số giây hoặc HTTP date.
- Client vẫn cần giới hạn tổng deadline.
- Không để mọi clients retry đồng loạt sau cùng một thời điểm; có thể kết hợp jitter theo policy.
- Tôn trọng quota theo tenant/API key/provider.
- Không retry nếu operation không idempotent hoặc outcome unknown chưa được tra cứu.
- Có circuit breaker/load shedding khi dependency không thể nhận thêm traffic.

Rate limiting bảo vệ dependency; retry không được trở thành cách vượt qua quota.

## 26. Circuit breaker: Ngừng gọi dependency đang lỗi

Circuit breaker có các trạng thái thường gặp:

~~~text
CLOSED
  |
  | failure threshold reached
  v
OPEN
  |
  | cool-down expires
  v
HALF_OPEN
  |
  +--> success threshold reached --> CLOSED
  |
  +--> failure -------------------> OPEN
~~~

- **Closed:** requests được phép đi qua.
- **Open:** fail fast, không tiếp tục gửi requests làm dependency quá tải.
- **Half-open:** cho một số probes giới hạn để kiểm tra hồi phục.

Circuit breaker không thay retry policy. Nó quyết định khi nào nên ngừng gọi; retry policy quyết định một operation có thể thử lại bao nhiêu lần và cách chờ.

Cần tránh:

- Dùng một breaker cho mọi operation có semantics khác nhau.
- Threshold quá nhạy gây flapping.
- Half-open cho quá nhiều probes.
- Không phân biệt lỗi local với lỗi dependency.
- Dùng fallback trả dữ liệu sai mà không báo rõ.
- Coi circuit OPEN là business success.

Fallback phải được domain chấp nhận. Ví dụ search có thể trả kết quả cache stale, nhưng payment authorization không thể giả vờ thành công.

## 27. Bulkhead và load shedding

Bulkhead giới hạn tài nguyên mà một dependency hoặc workload có thể chiếm:

- Connection pool riêng.
- Thread pool/concurrency limit.
- Queue capacity giới hạn.
- Semaphore theo dependency.
- CPU/memory quotas.
- Per-tenant concurrency.
- Separate worker deployments.

Load shedding từ chối sớm phần tải vượt capacity thay vì để mọi request timeout và retry.

~~~text
Incoming traffic
      |
      v
Admission / concurrency limit
      |
      +--> within capacity --> process
      |
      +--> over capacity ----> fast reject / queue per policy
~~~

Một 503/429 rõ ràng và nhanh có thể tốt hơn việc giữ request 30 giây rồi timeout. Nhưng caller cần biết retryability, deadline và idempotency semantics.

## 28. Retry storm và cascading failure

Một lỗi downstream có thể lan rộng:

~~~text
Service A
   |
   v
Service B
   |
   v
Service C (slow)
   |
   +--> B retries
   |
   +--> A retries B
   |
   +--> Gateway retries A
            |
            v
        More traffic to C
~~~

Các biện pháp bảo vệ:

1. Retry có giới hạn và backoff/jitter.
2. Deadline được truyền end-to-end.
3. Retry budget theo dependency.
4. Circuit breaker và load shedding.
5. Bulkhead/concurrency limit.
6. Cache/fallback chỉ khi semantics cho phép.
7. Queue bền vững cho workload bất đồng bộ phù hợp.
8. Không retry ở nhiều tầng cùng lúc.
9. Autoscaling có giới hạn và quan sát saturation.
10. Runbook có cách tắt retry/giảm traffic an toàn.

Autoscaling không phải giải pháp vô hạn. Nếu dependency bị giới hạn quota hoặc database đã quá tải, scale caller chỉ tạo thêm traffic.

## 29. Timeout quá dài cũng là một dạng retry risk

Nếu request timeout sau 60 giây nhưng người dùng đã rời trang sau 3 giây, server vẫn có thể giữ resources và hoàn thành side effect. Client có thể gửi một request mới sau đó.

Timeout nên phù hợp với:

- User experience.
- Downstream deadline.
- Database transaction duration.
- Queue processing semantics.
- External provider timeout.
- End-to-end SLO.
- Khả năng cancellation.

Không chọn timeout quá ngắn khiến các requests hợp lệ bị retry liên tục; cũng không chọn timeout quá dài giữ connection và threads trong lúc dependency đã chết.

**Timeout và retry phải được thiết kế cùng nhau.** Per-attempt timeout, total deadline và cancellation policy cần nhất quán.

## 30. Retry cho các operation khác nhau

| Operation | Retry guidance |
|---|---|
| GET dữ liệu không tạo side effect | Có thể retry bounded với deadline |
| PUT trạng thái theo resource/version | Chỉ retry nếu semantics và expected version rõ |
| DELETE resource | Idempotent theo contract nhưng cần xử lý response/authorization |
| POST tạo order | Dùng idempotency key hoặc unique business operation ID |
| Payment charge | Provider idempotency + lookup/reconciliation trước retry |
| Gửi email/SMS | Dedup bằng notification/job ID; provider hỗ trợ idempotency nếu có |
| Reserve inventory | Reservation ID, expiry và state machine |
| Publish event | Stable event ID, outbox và idempotent consumers |
| Database transaction conflict | Retry toàn transaction khi chưa có external side effect |
| File upload | Stable object key, checksum, multipart resume và completion idempotency |

Không suy ra một operation an toàn chỉ từ HTTP method hoặc tên hàm. Cần biết side effects và contract cụ thể.

## 31. Notification: Gửi email hoặc SMS trùng lặp

Ví dụ:

1. Notification worker gửi email thành công.
2. Provider trả response nhưng worker crash trước khi mark job complete.
3. Queue redelivers message.
4. Worker gửi email lần nữa.

Có thể giảm duplicate bằng:

- Notification ID ổn định.
- Unique constraint trên logical notification.
- Lưu trạng thái và provider message reference.
- Provider idempotency nếu được hỗ trợ.
- Outbox/inbox pattern.
- Reconciliation/lookup nếu provider cho phép.
- Template/version và recipient scope rõ.

Không đảm bảo email exactly-once nếu provider không có idempotency hoặc lookup. Khi outcome unknown, cần chọn policy cân bằng giữa duplicate risk và missing notification; ghi nhận limitation và có monitoring.

## 32. Inventory reservation: Retry phải giữ cùng một ý định

Một order yêu cầu giữ 2 sản phẩm. Nếu request retry tạo reservation ID mới mỗi lần, hệ thống có thể giữ 4 hoặc 6 sản phẩm.

Nên có:

- Stable reservation ID gắn với order/attempt.
- Unique constraint theo business scope.
- Quantity và SKU bất biến cho cùng reservation ID.
- TTL/expiry và release semantics.
- State machine: REQUESTED, RESERVED, RELEASED, EXPIRED, REJECTED.
- Idempotent reserve/release commands.
- Reconciliation với order lifecycle.

Nếu cùng reservation ID nhưng quantity khác, trả conflict và yêu cầu workflow tạo một operation mới có chủ đích.

## 33. Sagas và compensation không phải retry vô hạn

Một saga có nhiều bước và hành động bù:

~~~text
Create Order
    |
    v
Reserve Inventory
    |
    v
Authorize Payment
    |
    v
Confirm Order
~~~

Nếu Payment thất bại, saga có thể release reservation. Nhưng compensation cũng có thể timeout hoặc bị gửi lại.

Mỗi saga step cần:

- Saga ID và step ID ổn định.
- Command ID/idempotency key.
- Retry policy riêng.
- Deadline và timeout.
- State persisted để resume sau crash.
- Compensation idempotent.
- Handling cho outcome unknown.
- Escalation khi compensation không thể hoàn thành.
- Reconciliation để xác nhận trạng thái cuối.

Compensation không phải rollback vật lý toàn hệ thống. Ví dụ refund là một giao dịch mới, không xóa việc charge đã xảy ra.

## 34. Không retry lỗi validation hoặc business rejection

Một lỗi do input không hợp lệ sẽ không tự sửa sau 100 attempts.

Ví dụ:

~~~json
{
  "code": "INSUFFICIENT_INVENTORY",
  "retryable": false,
  "message": "Requested quantity is not available"
}
~~~

Hoặc một response payment declined theo business policy. Client nên hiển thị kết quả phù hợp hoặc yêu cầu người dùng hành động khác.

Nếu có thể retry sau khi trạng thái thay đổi, đó là **một business decision mới** hoặc một workflow được thiết kế rõ, không phải lặp mù request cũ.

Error contract có thể cung cấp retryability hint, nhưng client không được tin hint ngoài trust boundary nếu server semantics không được kiểm chứng.

## 35. Retry và concurrency: Nhiều attempts đồng thời

Một request có thể bị retry bởi client trong khi request đầu vẫn đang xử lý ở server. Hai attempts có thể chạy song song.

Ví dụ:

~~~text
Attempt A starts
  |
  +--> slow database transaction

Client timeout
  |
  +--> Attempt B starts
          |
          +--> same business operation
~~~

Nếu không có idempotency/locking, cả hai có thể cùng tạo record hoặc charge.

Cần:

- Atomic insert idempotency key với unique constraint.
- Lock hoặc optimistic concurrency theo resource khi cần.
- Một operation owner/lease có fencing token nếu worker phân tán.
- Trả trạng thái PROCESSING cho duplicate request thay vì chạy lại.
- Chờ kết quả trong giới hạn hoặc trả 202/status URL nếu async.
- Không giữ database lock trong suốt một external network call dài.
- Có stale-processing recovery và reconciliation.

Một mutex trong memory của một Pod không bảo vệ khi có nhiều replicas hoặc process restart.

## 36. Idempotency record ở trạng thái PROCESSING bị kẹt

Nếu worker crash, record có thể ở PROCESSING mãi mãi.

Một cách xử lý:

- Lưu started_at, lease_until và owner/attempt token.
- Có worker recovery quét các lease hết hạn.
- Tra cứu side effect bên ngoài trước khi chạy lại.
- Dùng fencing/version để worker cũ không ghi đè kết quả mới.
- Chuyển sang UNKNOWN khi chưa thể xác định.
- Escalate các record quá tuổi.
- Không tự xóa record đang kẹt rồi cho phép charge lại.

Lease timeout chỉ cho biết worker có thể đã chết; nó không chứng minh operation chưa xảy ra.

## 37. Retry trong background jobs

Background jobs thường có thời gian dài hơn request đồng bộ, nhưng vẫn cần giới hạn.

Job metadata có thể gồm:

~~~text
job_id
business_operation_id
attempt_count
max_attempts
next_attempt_at
deadline_at
last_error_code
status
created_at
updated_at
~~~

Các trạng thái:

~~~text
QUEUED
  |
  v
RUNNING
  |       \
  |        \--> RETRY_SCHEDULED
  v
SUCCEEDED
  |
  +--> FAILED / DEAD_LETTER / NEEDS_REVIEW
~~~

Cần phân biệt job retry với tạo job mới. Scheduler không nên enqueue duplicate jobs cho cùng một business operation khi chạy lại sau crash.

Các jobs có giá trị thấp có thể hết hạn; jobs tài chính/critical có thể cần durable retention và reconciliation. Chính sách phải theo domain.

## 38. Retry cho external APIs

External providers có thể có quota, idempotency windows và semantics riêng. Cần:

- Đọc tài liệu chính thức về retryable status codes.
- Tuân thủ Retry-After và rate limits.
- Dùng provider idempotency key nếu hỗ trợ.
- Lưu provider request/reference IDs.
- Có total deadline và bounded attempts.
- Không retry các business declines như lỗi mạng.
- Query operation status sau timeout khi có API lookup.
- Có circuit breaker và provider-specific concurrency limits.
- Alert khi tỷ lệ UNKNOWN tăng.
- Có reconciliation theo settlement/report khi thích hợp.

Không giả định mọi provider dùng cùng semantics cho idempotency keys hoặc retention. Adapter cần thể hiện khác biệt đó và không để domain service phải đoán.

## 39. Retry policy configuration mẫu

~~~yaml
dependency: payment-provider
operation: create-charge
retry:
  maxAttempts: 3
  perAttemptTimeout: 2s
  totalDeadline: 8s
  backoff:
    type: exponential
    baseDelay: 200ms
    maxDelay: 2s
    jitter: full
  retryable:
    networkErrors: true
    statusCodes: [429, 502, 503, 504]
  nonRetryable:
    statusCodes: [400, 401, 403, 422]
  retryBudget:
    ratio: 0.05
    window: 1m
idempotency:
  required: true
  keyScope: merchant-and-operation
  sameKeyDifferentPayload: reject
unknownOutcome:
  action: query-provider-before-retry
~~~

Đây là cấu hình minh họa, không phải schema chuẩn của một framework. Timeout, status codes và retry budget phải được xác nhận với provider, workload và SLO thực tế. Một số lỗi 5xx có thể xảy ra sau khi provider đã xử lý request; idempotency và lookup vẫn cần thiết.

## 40. Pseudocode cho một retry loop có giới hạn

~~~text
function execute(operation, deadline, idempotencyKey):
    attempt = 0

    while attempt < MAX_ATTEMPTS:
        if deadline.expired():
            return timeout_or_unknown(operation)

        attempt += 1
        remaining = deadline.remaining()
        timeout = min(PER_ATTEMPT_TIMEOUT, remaining)

        result = call_dependency(
            operation,
            timeout,
            idempotencyKey
        )

        if result.success:
            return result

        if result.outcome_unknown:
            return reconcile_before_retry(operation, idempotencyKey)

        if not is_retryable(result.error):
            return result

        if not retry_budget.allow():
            return retry_budget_exhausted()

        if attempt == MAX_ATTEMPTS:
            break

        delay = exponential_backoff_with_jitter(attempt)

        if delay >= deadline.remaining():
            break

        sleep(delay)

    return bounded_retry_exhausted()
~~~

Pseudocode cần được điều chỉnh theo runtime. Không dùng sleep trên request thread nếu có thể schedule retry bất đồng bộ; cancellation và deadline phải được giữ. Với operation có side effects, mọi attempt dùng cùng idempotency key cho cùng business intent.

## 41. Observability: Đo retry để biết nó đang giúp hay gây hại

Các metrics hữu ích:

~~~text
client_requests_total
client_retry_attempts_total
client_retry_exhausted_total
client_retry_budget_exhausted_total
dependency_timeouts_total
dependency_circuit_open_total
idempotency_replays_total
idempotency_conflicts_total
unknown_operation_outcomes_total
duplicate_messages_detected_total
dead_letter_messages_total
operation_duration_seconds
~~~

Tên metric là ví dụ. Labels nên bounded: service, dependency, operation, error class, environment. Không dùng idempotency key, order ID, trace ID hoặc customer ID làm metric labels.

Logs/traces có thể mang operation ID hoặc correlation ID theo policy để điều tra một case cụ thể. Không log bearer tokens, payment credentials hoặc raw PII.

Dashboard nên thể hiện:

- Original request rate và retry rate.
- Retry amplification ratio.
- Attempts per successful operation.
- Retry exhaustion.
- Timeout/unknown outcomes.
- Circuit breaker state.
- Dependency latency/error rate.
- Idempotency hits/conflicts.
- Queue age, redelivery và DLQ depth.
- Business duplicate outcomes.

Retry rate tăng có thể là triệu chứng dependency degradation, không phải bằng chứng hệ thống đang phục hồi tốt.

## 42. Retry amplification ratio

Một chỉ số đơn giản:

~~~text
Retry amplification ratio
  = total retry attempts / original operations
~~~

Ví dụ 100.000 original operations và 15.000 retry attempts:

~~~text
ratio = 15%
~~~

Cần định nghĩa numerator/denominator rõ, tránh đếm một attempt ở nhiều tầng thành nhiều business retries mà không phân biệt. Theo dõi ratio theo dependency và operation.

Một retry ratio tăng cùng latency và error rate thường báo hiệu dependency đang gặp vấn đề. Một retry ratio nhỏ nhưng duplicate payment tăng vẫn là incident nghiêm trọng; cần kết hợp technical và business metrics.

## 43. Alerting và runbook khi retry tăng bất thường

Alert có thể kích hoạt khi:

- Retry budget cạn.
- Retry amplification vượt baseline.
- Circuit breaker mở kéo dài.
- Timeout/unknown outcomes tăng.
- DLQ age/depth vượt ngưỡng.
- Idempotency conflicts tăng.
- Provider rate limit tăng.
- Duplicate business operations được xác nhận.
- Queue backlog không catch up.
- Dependency latency vượt SLO.

Runbook:

1. Xác định dependency/operation bị ảnh hưởng.
2. So original traffic với retry traffic.
3. Kiểm tra deployment/config changes.
4. Kiểm tra provider status, rate limits và network.
5. Xác định lỗi retryable hay business rejection.
6. Giảm retry budget hoặc bật fail-fast/load shedding theo policy.
7. Bảo vệ critical operations và tránh tạo attempts mới không an toàn.
8. Tra cứu unknown payment/order operations.
9. Kiểm tra DLQ và duplicate side effects.
10. Khôi phục traffic dần khi dependency ổn định.
11. Đối soát business outcomes.
12. Ghi RCA và cập nhật retry/contract tests.

Không tắt tất cả retry một cách mù quáng nếu có operation cần retry để hoàn tất. Cần phân loại theo dependency và side effects.

## 44. Testing: Chứng minh retry an toàn

### Functional tests

- Retryable network error rồi thành công.
- Non-retryable validation error dừng ngay.
- Max attempts được tuân thủ.
- Total deadline được tôn trọng.
- Retry-After được xử lý theo contract.
- Jitter/backoff nằm trong bounds.

### Idempotency tests

- Cùng key, cùng payload tạo một operation.
- Cùng key, payload khác bị reject.
- Duplicate requests đồng thời không tạo hai records.
- Response replay trả cùng operation result/reference.
- Key expiry phù hợp retry window.
- Crash ở giữa processing được recovery an toàn.

### Failure-injection tests

- Server commit rồi response bị drop.
- Provider charge thành công rồi client timeout.
- Consumer update DB rồi crash trước ack.
- Outbox publish thành công rồi relay crash.
- Database deadlock/serialization conflict.
- Circuit breaker open/half-open.
- Broker redelivery và DLQ.

### Load/resilience tests

- Dependency chậm kéo dài.
- Nhiều clients timeout cùng lúc.
- Retry budget cạn.
- Một dependency trả 429.
- Burst traffic và thundering herd.
- Consumer backlog catch-up.
- Pod restart khi operation đang PROCESSING.

Một test chỉ mô phỏng HTTP 503 trước khi server xử lý không chứng minh hệ thống an toàn khi timeout xảy ra sau commit.

## 45. Chaos engineering và retry storm

Có thể mô phỏng:

- Network latency tăng 500 ms.
- Packet loss hoặc connection reset.
- Dependency trả 503 theo tỷ lệ.
- Broker ngắt kết nối trong lúc ack.
- Database failover.
- Provider chậm nhưng vẫn hoàn thành operation.
- Consumer crash sau commit.
- Clock skew ảnh hưởng expiry/lease.

Quan sát:

- Retry budget có giới hạn không?
- Circuit breaker có mở đúng lúc?
- Request mới có được bảo vệ khỏi retries cũ?
- Duplicate business operations có phát sinh?
- Unknown outcomes có được giữ lại để reconciliation?
- Recovery có tạo một đợt retry storm mới không?
- SLO và resource saturation có nằm trong guardrails?

Chaos test phải có phạm vi, môi trường và rollback rõ; không gây fault injection production ngoài quy trình được phê duyệt.

## 46. Những anti-pattern cần tránh

**1. Retry vô hạn.** Một dependency đang lỗi bị caller liên tục tạo thêm tải.

**2. Retry ngay lập tức.** Nhiều clients đồng bộ retry và tạo thundering herd.

**3. Không có total deadline.** Request tiếp tục chạy dù caller không còn chờ.

**4. Mỗi tầng tự retry tối đa nhiều lần.** Attempts nhân lên qua dependency chain.

**5. Retry mọi HTTP 5xx.** Có thể lặp side effect đã commit trước khi server trả lỗi.

**6. Tạo idempotency key mới cho mỗi attempt.** Server không nhận ra các requests cùng một business intent.

**7. Dùng random key hoặc timestamp không ổn định.** Retry không deduplicate được.

**8. Chỉ lưu idempotency key trong memory.** Restart hoặc nhiều replicas làm mất bảo vệ.

**9. Lưu dedup record trước business update ở transaction khác.** Crash có thể khiến message bị bỏ qua dù nghiệp vụ chưa hoàn tất.

**10. Dùng idempotency key nhưng không kiểm tra payload.** Cùng key với amount/resource khác có thể bị xử lý sai.

**11. Xóa idempotency records quá sớm.** Retry muộn có thể tạo giao dịch mới.

**12. Coi timeout là failure chắc chắn.** Có thể charge hoặc tạo đơn đã thành công.

**13. Retry payment bằng key mới sau timeout.** Có nguy cơ double charge.

**14. Retry validation/business rejection.** Tạo tải nhưng không thể sửa input.

**15. Retry transaction có external side effect.** Database rollback không hoàn tác email/charge đã gửi.

**16. Consumer không idempotent.** Broker redelivery tạo side effects lặp.

**17. Gọi external API trước khi ghi operation intent.** Crash làm mất khả năng phục hồi và đối soát.

**18. Không có DLQ owner.** Poison messages bị retry mãi hoặc bị quên.

**19. Scale caller để chữa downstream overload.** Tạo thêm traffic và connections vào dependency.

**20. Tắt retries toàn cục khi có incident.** Có thể làm mất khả năng hoàn tất các workflow cần retry an toàn.

## 47. Checklist thiết kế retry và idempotency

1. Operation có side effect nghiệp vụ nào?
2. Timeout có thể xảy ra sau khi server/provider đã commit?
3. Error taxonomy có phân biệt transient, permanent và unknown outcome?
4. Có maximum attempts và total deadline?
5. Per-attempt timeout có nhỏ hơn remaining deadline?
6. Backoff có exponential cap và jitter?
7. Có retry budget theo dependency/operation?
8. Có retry ở nhiều tầng gây amplification?
9. Có cancellation và fail-fast behavior?
10. Operation có stable idempotency key?
11. Key có scope, retention và payload fingerprint?
12. Duplicate request đồng thời được xử lý atomically?
13. Idempotency record và business write có transaction boundary phù hợp?
14. External provider có idempotency/lookup API?
15. Unknown outcome có trạng thái và reconciliation path?
16. Consumer có inbox/dedup và event ID?
17. Outbox publish có stable IDs và replay safety?
18. DLQ có owner, alert và redrive policy?
19. Retry-After/rate limits được tôn trọng?
20. Circuit breaker, bulkhead và load shedding có phù hợp?
21. Retry metrics có phân biệt original operations và attempts?
22. Tests có mô phỏng commit-then-timeout và crash-before-ack?
23. Có kiểm thử peak traffic/retry storm?
24. Runbook có cách giảm retries mà không tạo duplicate business effects?
25. Business reconciliation xác nhận số operation thực tế, không dựa vào số request attempts?

## 48. Kết luận

**Retry giúp hệ thống phục hồi khỏi lỗi tạm thời, nhưng retry không giới hạn và không có idempotency có thể biến một lỗi nhỏ thành outage hoặc một thao tác thành nhiều giao dịch nghiệp vụ.**

Một thiết kế an toàn cần:

- **Giới hạn:** maximum attempts, per-attempt timeout, total deadline và retry budget.
- **Điều tiết:** exponential backoff, jitter, Retry-After, circuit breaker, bulkhead và load shedding.
- **Bảo vệ nghiệp vụ:** idempotency keys, unique constraints, inbox/dedup, outbox và expected version.
- **Xử lý điều chưa biết:** timeout sau side effect phải được tra cứu/reconcile trước khi retry.
- **Quan sát:** retry amplification, unknown outcomes, duplicate detections, DLQ và business outcomes.
- **Kiểm chứng:** fault injection cho các điểm crash/timeout sau commit, không chỉ test lỗi trước khi xử lý.

**Câu hỏi tự kiểm tra:** *Nếu Payment Provider đã charge thành công nhưng response bị mất, Order Service retry ba lần và Payment Worker nhận cùng message hai lần, thiết kế có bảo đảm chỉ một business charge được ghi nhận, xác định được outcome cuối và phục hồi được sau crash mà không tạo thêm side effect không?*

Một hệ thống đáng tin cậy không phải hệ thống retry nhiều nhất. Đó là hệ thống biết **khi nào retry, retry bao nhiêu, dùng cùng định danh nào, khi nào phải dừng và cách chứng minh nghiệp vụ chỉ được thực hiện theo đúng ý định**.

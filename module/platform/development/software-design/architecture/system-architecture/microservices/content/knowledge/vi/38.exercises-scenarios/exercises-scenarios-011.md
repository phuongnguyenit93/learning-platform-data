# Thử lại không giới hạn và nhân đôi thao tác nghiệp vụ

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Sai lầm thiết kế  
> **Mục tiêu:** Nhận diện rủi ro khi retry không giới hạn hoặc retry thiếu kiểm soát; hiểu vì sao một request có thể tạo nhiều side effects; thiết kế bounded retries, deadline, backoff, idempotency, deduplication và reconciliation để hệ thống phục hồi mà không nhân đôi nghiệp vụ.

## 1. Retry là gì?

Retry là việc gửi lại một thao tác sau khi lần thực hiện trước gặp lỗi hoặc caller không nhận được kết quả trong thời hạn chờ.

Trong hệ thống phân tán, lỗi tạm thời là điều bình thường:

- Kết nối mạng bị reset hoặc packet bị mất.
- Service đích đang deploy, restart hoặc failover.
- Database tạm thời hết connection hoặc gặp deadlock.
- Message broker rebalance hoặc consumer bị dừng.
- External provider trả 429, 502, 503 hoặc timeout.
- DNS, TLS handshake hoặc service discovery bị gián đoạn.
- Một request bị queue lâu hơn deadline.
- Caller nhận response quá muộn và đã đóng kết nối.

Retry có thể giúp hoàn thành một thao tác khi lỗi thực sự có thể hồi phục. Nhưng retry chỉ an toàn khi hệ thống hiểu **lỗi nào có thể thử lại, thao tác có side effect gì, caller còn bao nhiêu thời gian và lần trước đã thực hiện tới đâu**.

Một ví dụ thanh toán:

~~~text
Order Service
     |
     | POST /payments
     v
Payment Service
     |
     | create charge
     v
External Payment Provider
~~~

Provider có thể đã xử lý giao dịch thành công, nhưng response bị mất trên mạng. Order Service thấy timeout và gửi lại request. Nếu Payment Service hoặc provider không nhận diện được hai lần gửi là cùng một ý định, khách hàng có thể bị charge hai lần.

**Timeout chỉ chứng minh caller không nhận được kết quả đúng hạn. Nó không chứng minh server chưa commit hoặc external side effect chưa xảy ra.**

## 2. Hai sai lầm cần phân biệt

**Retry không giới hạn** là tiếp tục thử mà không có giới hạn rõ về số lần, thời gian, tài nguyên hoặc điều kiện dừng.

**Retry không idempotent** là gửi lại một thao tác có side effect mà hệ thống không nhận ra các lần gửi thuộc cùng một business operation.

Hai lỗi có thể xuất hiện riêng hoặc cùng lúc:

- Retry vô hạn một GET có thể tạo retry storm và làm sập dependency dù không tạo dữ liệu trùng.
- Retry ba lần một POST charge không có idempotency vẫn có thể tạo ba giao dịch.
- Retry một message consumer sau khi đã commit database nhưng chưa ack có thể chạy lại side effect.
- Retry một operation có outcome unknown bằng key mới có thể tạo một operation thứ hai.

Giải pháp phải xử lý cả **tải hệ thống** và **tính đúng đắn nghiệp vụ**. Bounded retry giảm tải; idempotency/deduplication ngăn cùng một ý định tạo nhiều kết quả.

## 3. Phân biệt request attempt với business operation

Một người dùng có thể chỉ thực hiện một ý định, nhưng hệ thống tạo nhiều lần gửi:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Business operation** | Ý định nghiệp vụ duy nhất | Thanh toán đơn ORD-1001 |
| **Request attempt** | Một lần caller gửi request | Client gửi lại POST sau timeout |
| **Message delivery** | Một lần broker giao message | Consumer nhận event lần thứ hai |
| **Execution attempt** | Một lần worker chạy logic | Worker restart rồi chạy lại job |
| **Provider transaction** | Giao dịch được hệ thống ngoài ghi nhận | Charge reference do payment provider cấp |

Một business operation có thể có nhiều request attempts, message deliveries và execution attempts. Hệ thống cần một định danh ổn định để biết các lần thực thi đó có thuộc cùng một ý định hay không.

Không đếm số request thành công làm số giao dịch nghiệp vụ nếu một operation có thể được retry. Cần phân biệt operation ID, attempt ID và provider transaction ID trong data model, logs và metrics.

## 4. Retry vô hạn tạo retry storm như thế nào?

Một vòng lặp đơn giản:

~~~text
while request fails:
    send request again
~~~

có thể biến một lỗi nhỏ thành outage:

~~~text
Normal traffic
     |
     v
Dependency slows down
     |
     v
Requests exceed timeout
     |
     v
Callers retry immediately
     |
     v
Dependency receives more traffic
     |
     v
Queue, CPU and connections saturate
     |
     v
More timeouts and retries
     |
     +------> Retry storm
~~~

Khi dependency đang quá tải, retry thêm request làm nó càng khó hồi phục. Caller giữ connection và thread lâu hơn, queue tăng, memory bị chiếm và các request mới cũng timeout.

Retry storm có thể lan theo chuỗi:

- API Gateway retry service A.
- Service A retry service B.
- Service B retry database hoặc provider.
- Worker cũng retry cùng dependency.
- Autoscaling tăng số replicas và số connection.
- Các retry mới tiếp tục dồn vào dependency đã yếu.

**Retry không giới hạn là cơ chế khuếch đại lỗi.** Một dependency chậm có thể kéo cả hệ thống vào vòng lặp tự tạo tải.

## 5. Retry amplification: Một lỗi có thể nhân số lần gọi

Giả sử một request đi qua ba tầng và mỗi tầng cho phép tối đa ba attempts tổng cộng. Nếu retry lồng nhau, số lần gọi tới dependency cuối có thể lên tới 27 lần cho một business operation, tùy cấu trúc và thời điểm lỗi.

~~~text
Gateway attempts: 3
  Service A attempts: 3 per gateway attempt
    Service B attempts: 3 per A attempt

Worst-case downstream attempts:
  3 × 3 × 3 = 27
~~~

Không phải mọi kiến trúc đều nhân chính xác theo phép nhân này, nhưng nó minh họa rủi ro khi mỗi tầng tự đặt retry policy mà không có budget end-to-end.

Cần theo dõi:

- Original operations.
- Request attempts.
- Retry attempts ở từng tầng.
- Message deliveries.
- External provider calls.
- Successful business operations.

Một metric “HTTP requests” không đủ để biết có bao nhiêu ý định nghiệp vụ thực sự được hoàn thành.

## 6. Không phải lỗi nào cũng retry được

Trước khi retry, cần phân loại lỗi theo semantics:

| Loại lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| **Transient network** | Connection reset, temporary DNS failure | Retry bounded nếu operation an toàn |
| **Temporary overload** | 429, 503 | Backoff, Retry-After và retry budget |
| **Dependency timeout** | Không nhận response đúng hạn | Xác định outcome; side effect có thể đã xảy ra |
| **Deadlock/serialization conflict** | Transaction chưa commit | Có thể retry toàn transaction |
| **Validation failure** | Amount thiếu hoặc sai định dạng | Không retry cùng input |
| **Authentication failure** | Token sai issuer/hết hạn | Refresh hoặc sửa credentials theo policy |
| **Authorization failure** | Không đủ quyền | Không retry mù |
| **Business rejection** | Hết tồn kho, payment declined | Chờ business state mới hoặc yêu cầu hành động mới |
| **Permanent configuration** | Sai endpoint, secret hoặc schema | Dừng và cảnh báo owner |
| **Unknown outcome** | Timeout sau khi gửi side effect | Tra cứu/reconcile trước khi retry |

Không retry mọi HTTP 5xx theo một quy tắc chung. Server có thể đã commit database rồi lỗi khi serialize response. Ngược lại, một lỗi 4xx có thể có semantics đặc thù theo provider, nhưng phải được quy định trong contract.

**Retryability cần dựa trên error code và operation contract**, không chỉ dựa vào status code.

## 7. Bounded retries: Giới hạn số lần thử

Một retry policy cần xác định:

- Maximum attempts.
- Per-attempt timeout.
- Total operation deadline.
- Backoff schedule.
- Jitter.
- Retryable error classes.
- Retry budget.
- Cancellation behavior.
- Final failure handling.
- Unknown-outcome handling.

Ví dụ minh họa:

~~~text
Maximum attempts: 3 total
Per-attempt timeout: 1 second
Backoff base: 100 ms
Backoff cap: 500 ms
Jitter: enabled
Total deadline: 3 seconds
~~~

Cần ghi rõ maximum attempts có tính lần gửi đầu tiên hay chỉ tính số lần retry. “3 retries” thường có thể hiểu là một lần đầu cộng ba lần thử lại, tức bốn attempts.

Giới hạn phải phù hợp workload. Một API đồng bộ cho người dùng thường cần deadline ngắn; một batch job có thể retry lâu hơn nhưng phải dùng queue bền vững và có trạng thái theo dõi.

Không đặt một policy duy nhất cho mọi operation chỉ để tiện cấu hình.

## 8. Per-attempt timeout và total deadline

**Per-attempt timeout** giới hạn thời gian chờ cho một lần gọi.

**Total deadline** giới hạn toàn bộ operation, gồm tất cả attempts, backoff và xử lý liên quan.

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

Nếu caller chỉ còn 300 ms deadline, không nên bắt đầu một attempt mới có timeout 2 giây.

Deadline nên được truyền qua các service để downstream biết thời gian còn lại. Mỗi tầng cần dùng timeout nhỏ hơn hoặc bằng remaining deadline, có trừ một khoảng dự phòng cho response/cleanup nếu cần.

Khi deadline hết:

- Không bắt đầu attempts mới.
- Hủy phần công việc có thể hủy an toàn.
- Giải phóng connections và threads.
- Trả trạng thái phù hợp với operation semantics.
- Nếu side effect có thể đã xảy ra, ghi nhận UNKNOWN thay vì khẳng định FAILED.

Client cancellation không tự động rollback transaction đã commit hoặc hủy request đã tới external provider.

## 9. Exponential backoff

Exponential backoff tăng thời gian chờ giữa các attempts:

~~~text
delay(n) = min(cap, base × 2^n)
~~~

Ví dụ base 100 ms, cap 2 giây:

| Lần retry | Delay trước jitter |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |
| 6 | 2.000 ms (cap) |

Backoff giảm tần suất gọi khi dependency đang hồi phục. Tuy nhiên, nếu hàng nghìn clients cùng chờ đúng 100, 200 và 400 ms, requests vẫn có thể đến theo từng đợt đồng bộ.

Backoff phải có cap. Một operation không nên chờ theo cấp số nhân vô hạn hoặc vượt deadline của chính nó.

## 10. Jitter: Phân tán thời điểm retry

Jitter thêm ngẫu nhiên vào thời gian chờ để các clients không cùng retry một lúc.

Một dạng full jitter:

~~~text
delay = random(0, min(cap, base × 2^attempt))
~~~

Ví dụ 10.000 clients cùng timeout:

~~~text
Without jitter:
  many retries arrive at nearly the same instant

With jitter:
  retries spread across a bounded time window
~~~

Có nhiều biến thể jitter. Hãy chọn một policy thống nhất, có giới hạn và có thể kiểm thử. Jitter không thay thế maximum attempts hoặc retry budget; nó chỉ phân tán thời điểm gửi.

## 11. Retry budget: Giới hạn tải retry tổng thể

Ngay cả khi mỗi request chỉ retry hai lần, traffic lớn vẫn có thể tạo hàng triệu retries.

Retry budget giới hạn lượng traffic retry trong một cửa sổ hoặc theo quota.

Ví dụ:

~~~text
Original operations: 100.000 / minute
Retry budget: 5%
Maximum retry attempts admitted: 5.000 / minute
~~~

Các con số chỉ minh họa. Budget có thể được quản lý:

- Theo service.
- Theo dependency.
- Theo operation class.
- Theo tenant/priority nếu có nhu cầu.
- Theo thời gian rolling window.
- Bằng token bucket hoặc quota tương đương.

Khi budget cạn, hệ thống có thể fail fast, giảm traffic hoặc chuyển tác vụ phù hợp sang durable queue. Không nên tiếp tục retry vô hạn chỉ vì từng request vẫn còn attempts.

## 12. Tránh retry ở mọi tầng

Một cấu hình nguy hiểm:

~~~text
Mobile client: 3 attempts
    |
API Gateway: 3 attempts
    |
Order Service: 3 attempts
    |
Payment client: 3 attempts
    |
Payment Provider
~~~

Mỗi tầng không biết những tầng khác đã retry bao nhiêu lần. Tổng số provider calls có thể tăng rất nhanh.

Cần xác định retry ownership theo dependency boundary:

- Client retry chỉ khi contract cho phép và có idempotency.
- Gateway không tự retry side-effecting operations nếu không hiểu operation semantics.
- Service có thể retry dependency tạm thời trong deadline và budget.
- Worker có retry policy riêng theo queue delivery model.
- External provider adapter tuân thủ rate limits và idempotency semantics của provider.

Không cần tất cả tầng đều retry. Một policy end-to-end cần tránh lồng retry không kiểm soát.

## 13. Idempotency là gì?

Một operation idempotent có thể được thực hiện nhiều lần với cùng một ý định mà kết quả nghiệp vụ tương đương một lần thực hiện.

Ví dụ:

- Đặt trạng thái resource thành INACTIVE có thể idempotent nếu cùng điều kiện.
- Đọc dữ liệu không tạo side effect thường an toàn để retry.
- Cộng 100.000 vào số dư mỗi lần gọi là không idempotent.
- Tạo order mới với ID mới mỗi lần là không idempotent.
- Charge payment, gửi email hoặc tạo shipment có thể tạo side effects trùng.

Ví dụ:

~~~text
Attempt 1:
  POST /orders
  -> creates ORD-1001
  -> response lost

Attempt 2:
  POST /orders
  -> creates ORD-1002
  -> response received

One user intent, two orders
~~~

Idempotency phải được thiết kế trong business contract và implementation. HTTP method, message broker hoặc database transaction không tự bảo đảm tính chất này cho toàn bộ workflow.

## 14. Idempotency key

Idempotency key là một định danh ổn định cho một business intent. Caller gửi cùng key ở mọi attempt của cùng operation.

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

Nếu cùng key và payload hợp lệ được gửi lại, server có thể trả lại operation result đã lưu hoặc trạng thái PROCESSING thay vì charge lần nữa.

Một key cần:

- Scope rõ: tenant, merchant, endpoint hoặc operation.
- Được tạo một lần cho business intent.
- Giữ nguyên qua các retries.
- Không dùng lại cho một operation mới.
- Có retention phù hợp retry window và nghiệp vụ.
- Được lưu bền vững, không chỉ trong memory.
- Liên kết với payload fingerprint hoặc immutable fields.
- Có xử lý đồng thời cho hai attempts cùng key.

Không tạo UUID mới mỗi lần retry. Nếu key thay đổi, server không nhận ra các requests cùng một ý định.

## 15. Cùng key nhưng payload khác phải bị từ chối

Ví dụ:

~~~text
Attempt 1:
  key=K1001
  amount=590000 VND

Attempt 2:
  key=K1001
  amount=690000 VND
~~~

Server không nên âm thầm trả kết quả cũ hoặc thực hiện một charge mới. Đây là xung đột contract.

Có thể trả error code ổn định như IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST và ghi audit theo policy.

Payload fingerprint nên dựa trên canonicalized business fields, không nhất thiết hash raw JSON bytes. Thứ tự fields hoặc whitespace có thể khác dù ý nghĩa giống nhau. Contract cần xác định field nào bất biến trong cùng operation.

## 16. Lưu idempotency record bền vững

Một bảng có thể chứa:

~~~text
idempotency_records
  scope
  idempotency_key
  request_hash
  operation_id
  status
  response_reference
  created_at
  updated_at
  expires_at
~~~

Có thể đặt unique constraint:

~~~sql
CREATE UNIQUE INDEX uq_idempotency_scope_key
ON idempotency_records(scope, idempotency_key);
~~~

Unique constraint giúp hai requests đồng thời không cùng tạo hai operation records trong cùng scope.

Một state model đơn giản:

~~~text
NEW
 |
 v
PROCESSING
 |        \
 |         +----> UNKNOWN
 v
SUCCEEDED / FAILED
~~~

Trạng thái terminal và retry behavior cần được định nghĩa. Một validation failure trước side effect có thể là FAILED. Timeout sau khi gửi charge có thể cần UNKNOWN cho tới khi tra cứu provider.

Không xóa idempotency record quá sớm. Nếu caller retry sau khi record hết hạn, một charge cũ có thể bị thực hiện lại. Retention cần tính tới client retry horizon, provider idempotency window và business recovery policy.

## 17. Atomicity giữa idempotency và side effect

Một cửa sổ crash nguy hiểm:

1. Server lưu idempotency key.
2. Server gọi provider.
3. Provider charge thành công.
4. Server crash trước khi lưu provider result.
5. Caller retry.
6. Server thấy record đang PROCESSING nhưng không biết charge đã xảy ra chưa.

Nếu server gọi provider lại mà không dùng cùng provider idempotency key hoặc tra cứu trạng thái, có thể tạo double charge.

Cần kết hợp:

- Persist operation intent trước khi gọi provider.
- Dùng provider idempotency key nếu hỗ trợ.
- Lưu provider reference khi có.
- Có trạng thái UNKNOWN.
- Tra cứu trạng thái qua provider API/webhook/statement.
- Dùng outbox cho các event nội bộ.
- Có reconciliation worker.
- Không tự chuyển UNKNOWN thành FAILED chỉ vì timeout.

Local database transaction không thể bảo đảm atomicity với một external provider. Phải thiết kế workflow phục hồi qua từng failure window.

## 18. Payment: Timeout không chứng minh charge thất bại

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

Quy trình an toàn:

1. Giữ operation ID và idempotency key.
2. Tra cứu provider bằng reference/key nếu API hỗ trợ.
3. Kiểm tra webhook hoặc event đến muộn.
4. Đối chiếu Payment ledger và provider statement.
5. Chỉ retry charge khi policy và bằng chứng xác nhận an toàn.
6. Cập nhật Order bằng command/event idempotent.
7. Ghi audit cho trạng thái cuối và exception.

Không tạo payment attempt mới với key mới chỉ vì caller timeout. Nếu đó vẫn là cùng một checkout intent, attempts phải được liên kết với cùng operation identity.

## 19. Tạo Order: Chống duplicate submission

Người dùng có thể nhấn nút Place Order hai lần hoặc browser gửi lại request khi mạng chập chờn.

Các lớp bảo vệ:

- Client tạo stable submission ID cho một lần checkout.
- API nhận idempotency key và tenant/user scope.
- Database có unique constraint cho business operation ID.
- Server lưu kết quả hoặc resource ID đã tạo.
- Duplicate request trả lại order hiện có.
- Cùng key với payload khác bị reject.
- UI hiển thị trạng thái PROCESSING nếu chưa có kết quả cuối.

Không chỉ disable nút trên frontend. Người dùng có thể mở nhiều tab, gửi từ mobile và web, hoặc request có thể được retry ở tầng mạng.

Business uniqueness constraint là lớp bảo vệ cuối cùng cho invariant quan trọng.

## 20. Inventory reservation: Retry phải giữ cùng một ý định

Một order cần giữ 2 sản phẩm. Nếu mỗi retry tạo reservation ID mới, hệ thống có thể giữ 4 hoặc 6 sản phẩm.

Nên có:

- Stable reservation ID gắn với order/attempt.
- Unique constraint theo business scope.
- SKU, warehouse và quantity bất biến cho cùng reservation ID.
- TTL/expiry và release semantics.
- State machine: REQUESTED, RESERVED, RELEASED, EXPIRED, REJECTED.
- Idempotent reserve/release commands.
- Reconciliation với order lifecycle.

Nếu cùng reservation ID nhưng quantity khác, trả conflict và yêu cầu workflow tạo một operation mới có chủ đích. Không tăng reserved quantity thêm một lần khi nhận lại cùng command.

## 21. Database transaction retry

Database có thể trả deadlock hoặc serialization conflict. Trong một số trường hợp, retry toàn bộ transaction là phù hợp nếu:

- Transaction chắc chắn chưa commit.
- Logic có thể chạy lại an toàn.
- Không có external side effect bên trong transaction.
- Input và expected version còn hợp lệ.
- Attempts có giới hạn.
- Unique constraints bảo vệ duplicate operations.

Pseudocode:

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

return bounded retry failure
~~~

Không gửi email, charge provider hoặc publish message trực tiếp bên trong transaction rồi retry toàn bộ transaction. Database rollback không thể hoàn tác external side effect đã xảy ra.

Dùng transactional outbox để ghi event intent cùng transaction, rồi publish sau commit.

## 22. Optimistic concurrency và expected version

Idempotency ngăn lặp cùng một ý định. Optimistic concurrency bảo vệ trước các cập nhật cạnh tranh.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = :order_id
  AND version = :expected_version;
~~~

Nếu số rows cập nhật bằng 0, record có thể đã thay đổi hoặc không còn ở version kỳ vọng. Caller cần đọc trạng thái mới và quyết định theo domain rules.

Không retry UPDATE vô điều kiện khi gặp conflict. Có thể ghi đè một thay đổi mới hơn hoặc làm sai state transition.

Một workflow có thể cần cả idempotency key lẫn expected version.

## 23. HTTP method không tự bảo đảm idempotency nghiệp vụ

HTTP semantics có những đặc tính phổ biến:

- GET thường được thiết kế safe và idempotent.
- PUT và DELETE có semantics idempotent theo contract HTTP.
- POST thường không mặc định idempotent.
- PATCH phụ thuộc loại patch operation.

Nhưng method name không đủ để chứng minh implementation đúng. Một PUT có thể gửi email mỗi lần, hoặc một DELETE có thể tạo side effect phụ lặp lại nếu code không được thiết kế cẩn thận.

POST vẫn có thể hỗ trợ idempotency key. GET mà vô tình thay đổi trạng thái nghiệp vụ là thiết kế sai.

**Định nghĩa idempotency theo business operation**, đồng thời công bố rõ behavior trong API contract để clients biết khi nào có thể retry.

## 24. Message broker: At-least-once và duplicate delivery

Trong cấu hình phổ biến, broker có thể giao lại message khi:

- Consumer xử lý xong nhưng chưa ack/commit offset.
- Consumer crash sau khi ghi database nhưng trước khi commit offset.
- Network timeout khiến broker không biết ack đã đến chưa.
- Consumer rebalance.
- Visibility timeout/lease hết hạn.
- Retry policy đưa message quay lại queue.

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
Consumer receives E1 again
~~~

Consumer phải có idempotent processing hoặc deduplication bền vững. Không giả định message chỉ đến đúng một lần.

## 25. Inbox pattern cho consumer deduplication

Một inbox table có thể ghi nhận event đã xử lý:

~~~text
processed_messages
  consumer_name
  event_id
  processed_at

UNIQUE(consumer_name, event_id)
~~~

Transaction xử lý:

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

Điều quan trọng là dedup record và business database update nằm trong cùng transaction nếu chúng cùng database.

Nếu ghi dedup trước rồi crash trước business update trong transaction khác, redelivery có thể bị bỏ qua dù nghiệp vụ chưa hoàn tất.

Nếu side effect nằm ngoài database, cần provider idempotency hoặc workflow/outbox tương ứng. Inbox table không thể tự bảo đảm email hay payment provider chỉ thực hiện một lần.

## 26. Outbox pattern cho publish retry

Producer có thể commit business state và event intent cùng một transaction:

~~~text
BEGIN
  UPDATE orders ...
  INSERT INTO outbox(event_id, event_type, payload)
COMMIT
~~~

Relay đọc outbox và publish lên broker. Nếu publish thành công nhưng relay crash trước khi đánh dấu delivered, event có thể được publish lại.

Cần:

- Stable event ID.
- Relay checkpoint và retry policy.
- Idempotent consumers.
- Outbox retention/cleanup có kiểm soát.
- Pending age và delivery lag metrics.
- Owner và runbook cho failed publish.
- Replay an toàn.

Outbox giải quyết atomicity giữa business write và event intent trong database. Nó không tự bảo đảm exactly-once side effects xuyên broker và mọi consumer.

## 27. Exactly-once: Phải nói rõ boundary

Một broker hoặc stream processor có thể hỗ trợ exactly-once trong phạm vi transaction và state store cụ thể. Điều đó không tự đảm bảo toàn bộ workflow chỉ xảy ra một lần qua:

- HTTP client.
- Database.
- Broker.
- Payment provider.
- Email/SMS vendor.
- Shipping carrier.
- External APIs.

Một broker transaction có thể commit offset và output record cùng nhau. Nhưng nếu consumer gọi provider trước khi transaction commit, provider side effect có thể đã xảy ra dù broker rollback.

Vì vậy, cần nói rõ **exactly-once trong boundary nào**. Với external side effects, thường cần idempotency keys, deduplication, outbox/inbox và reconciliation.

## 28. Queue retry, visibility timeout và poison messages

Với work queues, message có thể được giao lại khi consumer không ack trước visibility timeout hoặc lease expiry.

Thiết kế cần:

- Visibility/lease timeout lớn hơn thời gian xử lý hợp lý hoặc có heartbeat extension.
- Bounded delivery count.
- Exponential backoff và jitter nếu broker/worker hỗ trợ.
- DLQ sau số lần thử hoặc điều kiện phù hợp.
- Redrive policy có kiểm soát.
- Idempotent handler.
- Alert cho DLQ depth và age.
- Retention phù hợp business value.
- Owner xử lý poison messages.

Một message lỗi do payload sai sẽ không tự trở nên hợp lệ sau 1.000 lần retry. Nó cần quarantine, sửa producer/contract hoặc xử lý thủ công.

DLQ không phải thùng rác để quên. Cần owner, alert, replay policy và audit.

## 29. Retry-After và rate limiting

Khi dependency trả 429 hoặc 503 kèm Retry-After, client nên tuân thủ contract nếu giá trị hợp lệ và còn nằm trong deadline/budget.

Cần chú ý:

- Retry-After có thể là số giây hoặc HTTP date.
- Client vẫn cần giới hạn total deadline.
- Có thể kết hợp jitter để tránh mọi clients cùng retry một thời điểm.
- Tôn trọng quota theo tenant/API key/provider.
- Không retry operation non-idempotent khi outcome còn unknown.
- Có circuit breaker/load shedding khi dependency không thể nhận thêm traffic.

Rate limiting bảo vệ dependency. Retry không được trở thành cách vượt quota.

## 30. Circuit breaker: Ngừng gọi dependency đang lỗi

Circuit breaker thường có ba trạng thái:

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

- **Closed:** request được phép đi qua.
- **Open:** fail fast, ngừng gửi thêm traffic tới dependency.
- **Half-open:** cho một số probes giới hạn để kiểm tra hồi phục.

Circuit breaker không thay retry policy. Retry quyết định một operation được thử lại bao nhiêu lần; breaker quyết định khi nào nên ngừng gọi dependency đang lỗi.

Fallback phải được domain chấp nhận. Search có thể trả cache stale trong giới hạn, nhưng Payment Authorization không thể giả vờ thành công.

## 31. Bulkhead và load shedding

Bulkhead giới hạn tài nguyên mà một dependency hoặc workload được phép chiếm:

- Connection pool riêng.
- Thread pool/concurrency limit.
- Queue capacity giới hạn.
- Semaphore theo dependency.
- CPU/memory quotas.
- Per-tenant concurrency.
- Worker deployment riêng.

Load shedding từ chối sớm phần tải vượt capacity:

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

Một 503/429 rõ ràng và nhanh có thể tốt hơn việc giữ request 30 giây rồi timeout. Caller cần biết retryability, deadline và idempotency semantics.

## 32. Saga: Retry từng bước và compensation có kiểm soát

Một saga gồm nhiều bước nghiệp vụ:

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

Nếu Payment thất bại, saga có thể release reservation. Nhưng compensation cũng có thể timeout hoặc được gửi lại.

Mỗi saga step cần:

- Saga ID và step ID ổn định.
- Command ID/idempotency key.
- Retry policy riêng.
- Deadline và timeout.
- State được persist để resume sau crash.
- Compensation idempotent.
- Xử lý outcome unknown.
- Escalation khi compensation không thể hoàn thành.
- Reconciliation xác nhận trạng thái cuối.

Compensation không phải rollback vật lý toàn hệ thống. Refund là một giao dịch mới, không xóa việc charge đã xảy ra.

## 33. Nhiều attempts đồng thời

Client có thể timeout trong khi request đầu vẫn đang xử lý ở server, rồi gửi attempt thứ hai.

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

Nếu không có idempotency hoặc concurrency control, hai attempts có thể cùng tạo record hoặc charge.

Cần:

- Atomic insert idempotency key với unique constraint.
- Lock hoặc optimistic concurrency theo resource khi cần.
- Một operation owner/lease có fencing token nếu worker phân tán.
- Trả trạng thái PROCESSING cho duplicate request.
- Chờ kết quả trong giới hạn hoặc trả 202/status URL nếu async.
- Không giữ DB lock trong suốt external network call dài.
- Có stale-processing recovery và reconciliation.

Mutex trong memory của một Pod không bảo vệ khi có nhiều replicas hoặc process restart.

## 34. Idempotency record bị kẹt ở PROCESSING

Worker có thể crash khiến record ở PROCESSING mãi mãi.

Một cách xử lý:

- Lưu started_at, lease_until và owner/attempt token.
- Worker recovery quét các lease hết hạn.
- Tra cứu side effect bên ngoài trước khi chạy lại.
- Dùng fencing/version để worker cũ không ghi đè kết quả mới.
- Chuyển sang UNKNOWN khi chưa thể xác định.
- Escalate record quá tuổi.
- Không tự xóa record kẹt rồi cho phép charge lại.

Lease timeout chỉ cho biết worker có thể đã chết; nó không chứng minh operation chưa xảy ra.

## 35. Background jobs cũng cần retry bounded

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

State machine:

~~~text
QUEUED
  |
  v
RUNNING
  |       \
  |        +--> RETRY_SCHEDULED
  v
SUCCEEDED
  |
  +--> FAILED / DEAD_LETTER / NEEDS_REVIEW
~~~

Cần phân biệt retry một job với tạo job mới. Scheduler không nên enqueue duplicate jobs cho cùng business operation khi chạy lại sau crash.

Một job có thể hết hạn nếu kết quả không còn giá trị; một payment/financial operation có thể cần durable retention và reconciliation. Policy phải theo domain.

## 36. External APIs có semantics retry riêng

External providers có thể có quota, idempotency windows và status semantics riêng.

Cần:

- Đọc contract chính thức về retryable errors.
- Tuân thủ Retry-After và rate limits.
- Dùng provider idempotency key nếu hỗ trợ.
- Lưu provider request/reference IDs.
- Có total deadline và bounded attempts.
- Không retry business declines như lỗi mạng.
- Query operation status sau timeout khi có API lookup.
- Có circuit breaker và provider-specific concurrency limits.
- Alert khi unknown outcomes tăng.
- Reconcile theo settlement/report khi thích hợp.

Không giả định mọi provider dùng cùng semantics cho key hoặc retention. Adapter cần thể hiện khác biệt đó để domain service không phải đoán.

## 37. Retry policy configuration mẫu

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

Đây là cấu hình minh họa, không phải schema chuẩn của framework cụ thể. Timeout, status codes và retry budget cần được xác nhận với provider, workload và SLO. Một số lỗi 5xx có thể xảy ra sau khi provider đã xử lý request; idempotency và lookup vẫn cần thiết.

## 38. Pseudocode cho retry loop có giới hạn

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

        wait_or_schedule(delay)

    return bounded_retry_exhausted()
~~~

Pseudocode cần điều chỉnh theo runtime. Không sleep trên request thread nếu có thể schedule retry bất đồng bộ. Cancellation và deadline phải được giữ. Với operation có side effect, mọi attempt của cùng business intent dùng cùng idempotency key.

## 39. Observability: Đo retry để biết nó đang giúp hay gây hại

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

Đây là tên metric minh họa. Labels nên bounded: service, dependency, operation, error class và environment. Không dùng idempotency key, order ID, trace ID hoặc customer ID làm metric labels.

Logs/traces có thể mang operation ID hoặc correlation ID theo policy để điều tra một case cụ thể. Không log bearer tokens, payment credentials hoặc raw PII.

Dashboard nên thể hiện:

- Original operation rate và retry rate.
- Retry amplification ratio.
- Attempts per successful operation.
- Retry exhaustion và budget exhaustion.
- Timeout/unknown outcomes.
- Circuit breaker state.
- Dependency latency/error rate.
- Idempotency hits/conflicts.
- Queue age, redelivery và DLQ depth.
- Duplicate business outcomes đã xác nhận.

Retry rate tăng có thể là triệu chứng dependency degradation, không phải bằng chứng hệ thống đang phục hồi tốt.

## 40. Retry amplification ratio

Một chỉ số đơn giản:

~~~text
Retry amplification ratio
  = total retry attempts / original operations
~~~

Ví dụ 100.000 original operations và 15.000 retry attempts:

~~~text
ratio = 15%
~~~

Cần định nghĩa numerator/denominator rõ, tránh đếm một attempt ở nhiều tầng thành nhiều business retries mà không phân biệt.

Theo dõi ratio theo dependency và operation. Retry ratio tăng cùng latency/error rate thường báo hiệu dependency đang gặp vấn đề. Một retry ratio nhỏ nhưng duplicate payment tăng vẫn là incident nghiêm trọng; cần kết hợp technical và business metrics.

## 41. Runbook khi retry tăng bất thường

1. Xác định dependency và operation bị ảnh hưởng.
2. So original traffic với retry traffic.
3. Kiểm tra deployment/configuration changes.
4. Kiểm tra provider status, rate limits và network.
5. Xác định lỗi retryable hay business rejection.
6. Giảm retry budget hoặc bật fail-fast/load shedding theo policy.
7. Bảo vệ critical operations và tránh tạo attempts mới không an toàn.
8. Tra cứu các payment/order operations có outcome unknown.
9. Kiểm tra DLQ và duplicate side effects.
10. Khôi phục traffic dần khi dependency ổn định.
11. Đối soát business outcomes.
12. Ghi root cause và cập nhật retry/contract tests.

Không tắt tất cả retries một cách mù quáng nếu có operation cần retry để hoàn tất. Cần phân loại theo dependency và side effects.

## 42. Testing: Chứng minh retry an toàn

### Functional tests

- Retryable network error rồi thành công.
- Non-retryable validation error dừng ngay.
- Maximum attempts được tuân thủ.
- Total deadline được tôn trọng.
- Retry-After được xử lý theo contract.
- Jitter/backoff nằm trong bounds.
- Retry budget ngăn tải vượt mức.

### Idempotency tests

- Cùng key, cùng payload tạo một operation.
- Cùng key, payload khác bị reject.
- Duplicate requests đồng thời không tạo hai records.
- Response replay trả cùng operation result/reference.
- Key retention phù hợp retry window.
- Crash giữa processing được recovery an toàn.

### Failure-injection tests

- Server commit rồi response bị drop.
- Provider charge thành công rồi caller timeout.
- Consumer update DB rồi crash trước ack.
- Outbox publish thành công rồi relay crash.
- Database deadlock/serialization conflict.
- Circuit breaker open/half-open.
- Broker redelivery và DLQ.
- Worker crash khi record đang PROCESSING.

### Load/resilience tests

- Dependency chậm kéo dài.
- Nhiều clients timeout cùng lúc.
- Retry budget cạn.
- Dependency trả 429.
- Burst traffic và thundering herd.
- Consumer backlog catch-up.
- Pod restart khi operation đang xử lý.

Một test chỉ mô phỏng HTTP 503 trước khi server xử lý không chứng minh hệ thống an toàn khi timeout xảy ra sau commit.

## 43. Chaos engineering và retry storm

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
- Unknown outcomes có được giữ để reconciliation?
- Recovery có tạo retry storm mới?
- SLO và resource saturation có nằm trong guardrails?

Chaos test phải có phạm vi, môi trường và rollback rõ. Không gây fault injection production ngoài quy trình được phê duyệt.

## 44. Những anti-pattern cần tránh

**1. Retry vô hạn.** Dependency đang lỗi bị caller liên tục tạo thêm tải.

**2. Retry ngay lập tức.** Nhiều clients đồng bộ retry và tạo thundering herd.

**3. Không có total deadline.** Request tiếp tục chạy dù caller không còn chờ.

**4. Mỗi tầng tự retry tối đa nhiều lần.** Attempts nhân lên qua dependency chain.

**5. Retry mọi HTTP 5xx.** Side effect có thể đã commit trước khi server trả lỗi.

**6. Tạo idempotency key mới cho mỗi attempt.** Server không nhận ra cùng một business intent.

**7. Dùng random key hoặc timestamp không ổn định.** Retry không deduplicate được.

**8. Chỉ lưu idempotency key trong memory.** Restart hoặc nhiều replicas làm mất bảo vệ.

**9. Lưu dedup record và business update ở hai transaction không liên kết.** Crash có thể khiến message bị bỏ qua dù nghiệp vụ chưa hoàn tất.

**10. Cùng key nhưng không kiểm tra payload.** Có thể xử lý sai amount hoặc resource.

**11. Xóa idempotency records quá sớm.** Retry muộn có thể tạo giao dịch mới.

**12. Coi timeout là failure chắc chắn.** Charge hoặc order có thể đã thành công.

**13. Retry payment bằng key mới sau timeout.** Có nguy cơ double charge.

**14. Retry validation/business rejection.** Tạo tải nhưng không sửa được input.

**15. Retry transaction có external side effect.** Database rollback không hoàn tác email hoặc charge.

**16. Consumer không idempotent.** Broker redelivery tạo side effects lặp.

**17. Không ghi operation intent trước external call.** Crash làm mất khả năng phục hồi và đối soát.

**18. Không có DLQ owner.** Poison messages bị retry mãi hoặc bị quên.

**19. Scale caller để chữa downstream overload.** Tạo thêm traffic và connections vào dependency.

**20. Tắt retries toàn cục khi incident.** Có thể làm workflow cần retry an toàn không thể hoàn tất.

## 45. Checklist thiết kế retry và idempotency

1. Operation có side effect nghiệp vụ nào?
2. Timeout có thể xảy ra sau khi server/provider đã commit?
3. Error taxonomy phân biệt transient, permanent và unknown outcome?
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
21. Retry metrics phân biệt original operations và attempts?
22. Tests mô phỏng commit-then-timeout và crash-before-ack?
23. Có kiểm thử peak traffic/retry storm?
24. Runbook có cách giảm retries mà không tạo duplicate business effects?
25. Business reconciliation xác nhận số operation thực tế, không dựa vào số request attempts?

## 46. Kết luận

**Retry giúp hệ thống phục hồi khỏi lỗi tạm thời, nhưng retry không giới hạn và không có idempotency có thể biến một lỗi nhỏ thành outage hoặc biến một thao tác thành nhiều giao dịch nghiệp vụ.**

Một thiết kế an toàn cần:

- **Giới hạn:** maximum attempts, per-attempt timeout, total deadline và retry budget.
- **Điều tiết:** exponential backoff, jitter, Retry-After, circuit breaker, bulkhead và load shedding.
- **Bảo vệ nghiệp vụ:** idempotency keys, unique constraints, inbox/dedup, outbox và expected version.
- **Xử lý điều chưa biết:** timeout sau side effect phải được tra cứu/reconcile trước khi retry.
- **Quan sát:** retry amplification, unknown outcomes, duplicate detections, DLQ và business outcomes.
- **Kiểm chứng:** fault injection cho các điểm crash/timeout sau commit, không chỉ test lỗi trước khi xử lý.

**Câu hỏi tự kiểm tra:** *Nếu Payment Provider đã charge thành công nhưng response bị mất, Order Service retry ba lần và Payment Worker nhận cùng message hai lần, thiết kế có bảo đảm chỉ một business charge được ghi nhận, xác định được outcome cuối và phục hồi sau crash mà không tạo thêm side effect không?*

Một hệ thống đáng tin cậy không phải hệ thống retry nhiều nhất. Đó là hệ thống biết **khi nào retry, retry bao nhiêu, dùng cùng định danh nào, khi nào phải dừng và cách chứng minh nghiệp vụ chỉ được thực hiện theo đúng ý định**.

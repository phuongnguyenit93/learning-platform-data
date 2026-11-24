# Retry và backoff theo loại lỗi trong Spring Integration Adapters

> **Chương:** Production  
> **Bài học:** Retry và backoff theo loại lỗi  
> **Module:** Spring Integration Adapters  
> **Phạm vi:** Luồng trao đổi message qua inbound/outbound adapter, gateway, poller, MessageChannel và hệ ngoài như File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Phân biệt **lỗi tạm thời (transient)**, **lỗi vĩnh viễn (permanent)**, **lỗi dữ liệu**, **lỗi xác thực/ủy quyền**, **lỗi quá tải**, **lỗi xung đột** và **kết quả không chắc chắn (unknown outcome)**.
2. Chọn retry theo **loại lỗi + thao tác + tính idempotent + ranh giới transaction/ack**, không retry mọi exception.
3. Tính được ngân sách thời gian từ số attempts, timeout mỗi lần và backoff; thiết kế exponential backoff, jitter và giới hạn tốc độ.
4. Hiểu các lớp Spring Integration có thể áp retry: handler advice, poller, inbound listener/container, client library, broker và một worker retry bất đồng bộ.
5. Quản lý message lỗi bằng ErrorMessage, error channel, DLQ/DLT/quarantine, circuit breaker và runbook replay.
6. Áp dụng chính sách khác nhau cho File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC với các giới hạn về thứ tự, acknowledgment và giao dịch.
7. Chứng minh qua failure drill rằng retry **không làm mất message, không nhân đôi side effect, không gây retry storm và có thể kiểm toán**.

**Bài toán xuyên suốt:** Một dịch vụ Spring Boot dùng Spring Integration nhận đơn hàng từ SFTP, kiểm tra rồi lưu JDBC, gửi Kafka event và gọi HTTP API đối tác. Khi đối tác trả 503, nên retry. Khi JSON sai schema, retry nhiều lần cũng không giúp. Khi HTTP client timeout sau khi đối tác đã tạo thanh toán, retry với request ID mới có thể tạo thanh toán lần hai. Cùng là “exception”, nhưng chính sách xử lý phải khác nhau.

**Lưu ý phiên bản:** Cơ chế và tên API của Spring Integration, Spring Retry, Spring AMQP, Spring Kafka, JDBC driver, JMS provider và client HTTP/SFTP có thể thay đổi theo phiên bản. Các ví dụ sử dụng mô hình phổ biến, không khẳng định mọi adapter hay release đều có một thuộc tính retry chung.

## 2. Retry khác gì với redelivery, replay và recovery?

| Khái niệm | Điều gì xảy ra? | Bên thường chịu trách nhiệm | Rủi ro |
|---|---|---|---|
| **Retry tại chỗ** | Lặp lại một thao tác trong lần xử lý hiện tại | Client, handler advice, service | Giữ thread/connection, vượt deadline |
| **Broker redelivery** | Message chưa ack được phát lại | JMS/AMQP broker, Kafka consumer sau offset chưa commit | Tác động nghiệp vụ trùng |
| **Scheduled retry** | Đưa tác vụ vào hàng đợi bền vững để thử sau | Ứng dụng, retry topic/queue, job | Ordering và backlog |
| **Replay** | Chạy lại message đã lưu ở DLQ/DLT/quarantine hoặc event log | Operator/worker có phê duyệt | Dữ liệu đã đổi, side effect cũ |
| **Recovery** | Chuyển sang trạng thái thay thế hợp lệ khi retry hết | Error flow, compensation, fallback | Nuốt lỗi hoặc trả success sai |
| **Compensation** | Hành động bù trừ tác động đã xảy ra | Workflow/saga, owner nghiệp vụ | Không phải rollback ACID |
| **Circuit breaker** | Ngừng gọi tạm một dependency đang lỗi nặng | Resilience layer | Không sửa dữ liệu và không tự replay message |
| **Backpressure** | Giảm lượng message/inflight theo năng lực xử lý | Poller, channel, broker, limiter | Tăng backlog nếu không giám sát |

**Retry** không đồng nghĩa **idempotency**. Một message có thể được chuyển tới cùng consumer hai lần dù adapter đã retry “đúng cách”. Idempotency ngăn tác động không mong muốn khi yêu cầu hợp lệ được nhận hoặc xử lý lặp.

### 2.1. Chuỗi xử lý có phân loại lỗi

~~~mermaid
flowchart TD
    IN["Inbound message / request"] --> VALID["Validate contract + business key"]
    VALID --> DECIDE{"Kết quả / loại lỗi?"}
    DECIDE -->|"Đúng"| EFFECT["Business action + durable state"]
    DECIDE -->|"Sai schema/quyền"| REJECT["Reject / quarantine + alert"]
    DECIDE -->|"Đã xử lý"| NOOP["Idempotent no-op"]
    DECIDE -->|"Lỗi tạm thời"| BUDGET{"Còn retry budget?"}
    DECIDE -->|"Không rõ side effect"| VERIFY["Verify actual outcome"]
    VERIFY -->|"Đã hoàn tất"| DONE["Mark complete"]
    VERIFY -->|"Chưa thực hiện"| BUDGET
    VERIFY -->|"Vẫn không rõ"| HOLD["Unknown-outcome queue + owner"]
    BUDGET -->|"Có"| BACKOFF["Backoff + jitter"]
    BACKOFF --> EFFECT
    BUDGET -->|"Hết"| DLQ["Durable retry / DLQ / incident"]
    EFFECT --> ACK["Ack / checkpoint đúng thời điểm"]
    DLQ --> OPS["Runbook replay có kiểm soát"]
~~~

Sơ đồ mang tính logic: lựa chọn **ack**, **rethrow**, **DLQ** phụ thuộc ranh giới transaction và đặc điểm từng adapter. Nếu lỗi được “recover” bằng cách chỉ log rồi return, upstream có thể coi message đã hoàn tất dù chưa thực hiện nghiệp vụ.

## 3. Taxonomy lỗi: quyết định retry trước khi quyết định backoff

Một exception class không phải lúc nào cũng cung cấp đủ ngữ nghĩa. Cần biết **operation**, **giai đoạn gửi/nhận**, **business key**, **idempotency** và **phản hồi thực tế**.

| Nhóm | Ví dụ | Retry mặc định? | Hướng xử lý |
|---|---|---|---|
| **Transient network** | Connection reset, timeout, DNS tạm thời, broker reconnect | Có điều kiện | Retry giới hạn + backoff/jitter; outcome có thể mơ hồ |
| **Overload / throttling** | HTTP 429, 503, pool saturation, quota tạm thời | Có điều kiện | Tôn trọng Retry-After khi hợp lệ; giảm concurrency |
| **Transient dependency** | Broker leader chuyển, DB deadlock, temporary unavailable | Có điều kiện | Retry tại boundary đúng, idempotent, giới hạn thời gian |
| **Permanent schema** | JSON/XML/CSV sai cấu trúc, unsupported version | Không cho cùng payload | Quarantine; sửa producer/schema/code |
| **Business validation** | Thiếu trường, số tiền âm, trạng thái nghiệp vụ không hợp lệ | Không, trừ khi có dependency có thể làm điều kiện thay đổi | Reject/DLQ business review |
| **Authentication** | Credential sai/hết hạn, client certificate invalid | Không retry nóng | Rotate/refresh hợp lệ hoặc ticket |
| **Authorization** | HTTP 403, broker ACL denied, DB permission denied | Không | Sửa quyền sau phê duyệt; audit |
| **Conflict** | Optimistic lock, unique constraint, HTTP 409 | Theo hợp đồng | Có thể reread/recompute; không luôn retry nguyên request |
| **Resource not found** | HTTP 404, file/row chưa xuất hiện | Thường không | Chỉ retry nếu eventual-consistency contract cho phép |
| **Duplicate** | Business ID đã được xử lý | Không cần lặp side effect | Idempotent success/no-op hoặc báo conflict |
| **Unknown outcome** | Request sent nhưng response/confirm/commit ack mất | Không retry mù | Query/reconcile actual state; reuse idempotency key |
| **Poison message** | Payload kích hoạt lỗi lặp vô hạn | Không retry không giới hạn | Bounded attempts rồi quarantine |
| **Cancellation/deadline exceeded** | Caller hết SLA hoặc pod dừng | Không tự retry trong luồng đã hết deadline | Durable handoff/recovery theo workflow |

**Không có quy tắc “mọi 5xx đều retry” tuyệt đối.** Đôi khi 500 do dữ liệu không được hỗ trợ nhưng server trả sai mã; đôi khi 409 là conflict có thể giải quyết sau khi đọc lại trạng thái. Phải ưu tiên contract của hệ ngoài và quan sát thực tế.

### 3.1. Lỗi 401/403: phân biệt refresh credential và lỗi quyền

- **401 Unauthorized:** Có thể token vừa hết hạn. Nếu hệ thống hỗ trợ refresh token đáng tin cậy, có thể làm mới credential **một lần có kiểm soát** rồi gửi lại thao tác được phép, vẫn phải cân nhắc idempotency.
- **403 Forbidden:** Thường là thiếu quyền hoặc policy từ chối; retry với cùng credential không sửa được.
- **TLS/SSH host key invalid:** Không chuyển lỗi bảo mật thành lỗi network để retry hoặc tắt verification.
- **Broker ACL/DB permission denied:** Cần owner xử lý cấu hình, không tăng số lần gọi.

### 3.2. Conflict không phải lúc nào cũng lỗi vĩnh viễn

Một `OptimisticLockingFailureException` có thể được xử lý bằng cách đọc lại bản ghi, tính lại nghiệp vụ rồi thử một transaction mới. Nhưng một `DuplicateKeyException` do business key trùng có thể nghĩa là **request đã được xử lý** hoặc **xung đột dữ liệu thật**; không retry insert mù. HTTP 409 cũng có semantics theo API: có nơi nghĩa “resource đang bận”, có nơi nghĩa “state transition không hợp lệ”.

### 3.3. Khi ngoại lệ bị wrapper che mất nguyên nhân

Trong Spring Integration, một lỗi có thể bị bọc trong `MessageHandlingException`, `MessagingException` hoặc exception của client/framework. Nếu classifier chỉ kiểm tra exception top-level, lỗi mạng bên trong có thể bị xem thành permanent; ngược lại nếu chỉ đọc thông điệp text có từ “timeout” có thể retry nhầm.

Checklist:

- [ ] Phân loại bằng **type/status/SQLState/broker error code** đáng tin khi có thể.
- [ ] Có xử lý nested cause có giới hạn, tránh vòng tham chiếu hoặc bỏ qua nguyên nhân gốc.
- [ ] Không phân loại theo phép `exception.getMessage().contains(...)` đơn thuần.
- [ ] Bảo toàn original message ID, business ID, attempt và correlation ID.
- [ ] Log cause chain đã che dữ liệu nhạy cảm.
- [ ] Có test wrapper exception ở cả synchronous và asynchronous flows.

## 4. Tầng nào sở hữu retry?

Một luồng có thể có retry ở nhiều nơi:

1. HTTP/SFTP/JDBC/broker client;
2. Spring Integration request-handler advice;
3. Service method/transaction;
4. Inbound adapter, listener container hoặc poller;
5. Broker redelivery hoặc retry topic/queue;
6. Error flow, scheduled job hoặc operator replay;
7. Upstream sender gửi lại request vì không nhận acknowledgment.

Nếu không phối hợp, các tầng retry **nhân số lần gọi** thay vì bổ trợ nhau.

### 4.1. Ma trận trách nhiệm

| Điểm | Nên retry cái gì? | Không nên làm |
|---|---|---|
| **Client library** | Lỗi protocol/connection mà client hiểu chắc là an toàn; retry theo khả năng client | Retry lệnh side effect mơ hồ không có idempotency |
| **Handler advice** | Lặp một lời gọi handler idempotent do lỗi transient cụ thể | Bao trùm transaction hoặc handler không an toàn mà không phân loại |
| **Business service** | Recompute rồi thử lại transaction khi lock/deadlock được nhận diện | Retry nguyên flow có outbound side effect đã chạy |
| **Poller/source** | Lấy lại item có checkpoint rõ, điều chỉnh tốc độ khi nguồn lỗi | Quét cùng file/row nhiều lần mà thiếu deduplication |
| **JMS/AMQP listener/broker** | Redelivery message chưa hoàn tất, bounded DLQ policy | Requeue poison message vô hạn |
| **Kafka listener / retry topic** | Reprocess hoặc schedule record lỗi theo policy, DLT cuối | Giả định offset/ordering luôn không đổi |
| **Application retry queue** | Dời thao tác vượt synchronous deadline sang xử lý bền vững | Nhồi queue memory không giới hạn |
| **Operator replay** | Re-drive sau root-cause fix và approval | Clear queue/seek offset tuỳ tiện |

**Quy tắc thiết kế:** Mỗi operation nên có **một retry owner chủ đạo**. Các tầng còn lại phải dùng budget/guardrail phối hợp, tránh một bên đã recover nhưng bên kia vẫn retry.

### 4.2. Giao dịch đi qua nhiều hệ: retry cái nào?

Giả sử một service activator:

~~~text
read input -> update DB -> invoke HTTP partner -> publish Kafka -> ack input
~~~

Nếu lời gọi HTTP lỗi sau DB update, retry **cả service activator** có thể cập nhật DB hai lần và gửi nhiều event. Giải pháp có thể là:

- Transaction DB + idempotency key cho thay đổi nội bộ;
- Outbox event cho nghĩa vụ publish;
- Workflow/outbound command riêng có trạng thái, retry idempotent;
- HTTP idempotency key hoặc query trạng thái đối tác;
- Ack đầu vào tại thời điểm hợp đồng đã được bảo đảm;
- Reconciliation cho từng target thay vì một cờ “SUCCESS” toàn hệ.

Không có transaction ACID mặc định bao trùm DB, HTTP, file, SFTP và Kafka trong một luồng Spring Integration.

## 5. Chính sách retry là một decision function

Một policy có thể được hình dung như sau:

~~~text
retryDecision(
    errorCategory,
    operationType,
    isIdempotent,
    sideEffectStatus,
    sourceCheckpointStatus,
    attemptsMade,
    remainingDeadline,
    dependencyHealth,
    retryAfter
) -> RETRY_NOW | RETRY_LATER | RECONCILE | QUARANTINE | FAIL
~~~

**Cần ít nhất năm quyết định độc lập**:

1. **Có thể thử lại không?** Loại lỗi, contract, operation idempotency.
2. **Thử lại ở đâu?** Client, handler, source redelivery, durable retry queue hay operator.
3. **Bao nhiêu lần và tối đa bao lâu?** Attempt count, per-attempt timeout, elapsed/deadline budget.
4. **Chờ bao lâu trước lần kế tiếp?** Fixed/exponential/decorrelated backoff, Retry-After và jitter.
5. **Khi hết hoặc không được thử lại thì sao?** Fail, quarantine, dead-letter, reconcile, compensate, alert.

### 5.1. Sơ đồ quyết định theo loại lỗi

| Điều kiện | Hướng xử lý ưu tiên |
|---|---|
| Schema/business validation sai | Reject/quarantine, không retry cùng payload |
| Unauthorized do token có thể refresh hợp lệ | Refresh một lần theo contract; nếu vẫn lỗi thì fail |
| Forbidden/ACL denied | Fail, alert/ticket; không retry nóng |
| 429 có Retry-After hợp lệ | Chờ theo chính sách và deadline, giảm concurrency |
| 503, connection reset trước khi side effect | Retry bounded theo budget |
| Timeout với thao tác side effect không có idempotency | Đối soát actual outcome trước khi gửi lại |
| Deadlock/serialization failure cho DB transaction thuần | Retry transaction có giới hạn, không lặp external side effect |
| DuplicateKey với same business key đã hoàn tất | Idempotent no-op; không retry insert |
| Broker confirm/offset ack mơ hồ | Kiểm tra trạng thái, cho phép duplicate delivery và dùng idempotent consumer |
| Dependency lỗi kéo dài | Mở circuit, durable retry/dead-letter và alert |
| Deadline đã hết | Không tiếp tục retry đồng bộ; chuyển cơ chế phục hồi phù hợp |

### 5.2. Scope của retry phải nhỏ và đúng

Thử lại **một thao tác đọc HTTP GET** ít rủi ro hơn thử lại **toàn bộ flow gồm lưu DB và phát event**. Retry chỉ nên bao lấy đoạn idempotent và có thể hoàn tác, không lấy một handler lớn vừa biến đổi dữ liệu vừa gọi ba hệ ngoài làm đơn vị retry mặc định.

## 6. Backoff: fixed, exponential, jitter và Retry-After

### 6.1. Các thuật toán phổ biến

| Chiến lược | Công thức/trực giác | Khi hữu ích | Hạn chế |
|---|---|---|---|
| **Immediate retry** | Không chờ | Một số lỗi rất ngắn, chỉ một lần an toàn | Dễ gây tải đột biến |
| **Fixed backoff** | Luôn đợi 1 s chẳng hạn | Tải thấp, hệ đối tác ổn định, thử nghiệm | Nhiều client đồng pha |
| **Linear backoff** | 1 s, 2 s, 3 s... | Tăng chậm áp lực chờ | Vẫn dễ đồng pha |
| **Exponential backoff** | 1 s, 2 s, 4 s, 8 s... tới max cap | Outage và rate limit | Client cùng bắt đầu vẫn đồng bộ |
| **Exponential + full jitter** | Chọn ngẫu nhiên trong khoảng từ 0 tới exponential cap | Giảm thundering herd | Một số lần có delay rất ngắn |
| **Equal jitter** | Một phần cố định + một phần ngẫu nhiên | Tránh delay quá ngắn, phân tán tải | Điều chỉnh thêm so full jitter |
| **Decorrelated jitter** | Delay kế tiếp phụ thuộc delay trước và random trong giới hạn | Giảm đồng pha qua nhiều đợt | Khó lý giải/tái hiện |
| **Server-directed** | `Retry-After` hoặc tín hiệu quota hợp lệ | HTTP 429/503, API có hợp đồng backoff | Phải kiểm tra thời gian/deadline và độ tin cậy nguồn |

Một mô hình exponential được giới hạn:

\[
D_k = \min(D_{\max}, D_0 \times m^{k-1}), \quad k = 1,2,\ldots,N-1
\]

với `N` là **tổng số attempts**, không phải số lần retry thêm. Độ trễ `D_k` nằm **giữa attempt k và k+1**. Nếu đặt `N=4`, thường chỉ có **3 khoảng backoff**.

**Ví dụ:** 4 attempts, mỗi attempt tối đa 5 giây, backoff 1 s, 2 s, 4 s. Tổng thời gian worst-case đơn giản:

\[
T_{\max} \approx 4 \times 5\mathrm{s} + (1+2+4)\mathrm{s} = 27\mathrm{s}
\]

chưa tính pool wait, DNS/TLS, serialization, queue, cleanup và scheduling. Nếu gateway caller có deadline 20 s, policy trên **không hợp lệ**, dù từng timeout đều có giá trị hữu hạn.

### 6.2. Jitter giúp giảm retry storm

Giả sử 500 worker đồng thời nhận 503 lúc 10:00:00. Nếu tất cả backoff đúng 1 s, họ có thể gọi lại cùng lúc, làm đối tác quá tải thêm. Jitter phân tán thời điểm gửi và kết hợp với **rate limiter + circuit breaker** để tránh thundering herd.

Không dùng random làm mất khả năng audit: log attempt, effective delay và retry decision (không cần log seed ngẫu nhiên).

### 6.3. Tôn trọng Retry-After nhưng không vượt deadline

HTTP `Retry-After` có thể là **delay-seconds** hoặc **HTTP-date**. Khi sử dụng:

1. Parse đúng format và giới hạn giá trị theo chính sách.
2. Không tin blind vào giá trị âm, vô hạn hoặc ngày sai.
3. Đối chiếu với **remaining deadline**.
4. Không giữ thread đồng bộ chờ quá lâu; có thể chuyển sang durable scheduled retry.
5. Dùng throttling chung khi quota áp dụng cho nhiều instance/tenant.
6. Không coi Retry-After là giấy phép tự động retry unsafe operation nếu side effect còn mơ hồ.

**Retry-After** là tín hiệu điều phối chờ, không thay cho idempotency hoặc authorization.

## 7. Ngân sách retry và deadline toàn luồng

### 7.1. Thiết kế từ business SLA

Với HTTP inbound gọi downstream:

- Client/proxy có thể chỉ đợi 15 giây.
- Handler cần 2 giây validation, tối đa 3 giây DB, và ít nhất 2 giây dự phòng.
- Chỉ còn khoảng 8 giây cho outbound retries.
- Hai attempts 3 giây mỗi lần + backoff 1 giây có thể phù hợp; bốn attempts thì không.

Một cách tính **ước lượng**:

\[
T_{\mathrm{retry}} \approx \sum_{i=1}^{N}T_{\mathrm{attempt},i}
+ \sum_{i=1}^{N-1}D_i
\]

Toàn luồng cần thêm queue, connection acquisition, serialization, cleanup, DB và reserve. Không cộng trùng các timeout đã bao hàm nhau; hãy xác minh semantics client.

### 7.2. Quy tắc còn ngân sách mới retry

~~~text
for attempt in 1..maxAttempts:
    remaining = deadline - monotonicElapsed()
    if remaining <= minimumUsefulTime:
        return DEADLINE_EXCEEDED

    result = invokeWithPerAttemptTimeout(
        min(configuredAttemptTimeout, remaining - reserve)
    )

    if result.success:
        return SUCCESS

    decision = classify(error, operation, sideEffectState)

    if decision == MUST_RECONCILE:
        return UNKNOWN_OUTCOME
    if decision != RETRYABLE:
        return FAIL_OR_QUARANTINE
    if attempt == maxAttempts:
        return RETRIES_EXHAUSTED

    delay = calculateBackoffWithJitter(attempt)
    if delay + reserve >= remaining:
        return RETRIES_EXHAUSTED_OR_DEFERRED

    sleepOrSchedule(delay)
~~~

Pseudocode minh họa **quy tắc điều phối**, không phải mã có thể chạy trực tiếp. Trên Java, dùng đồng hồ monotonic để đo elapsed, không dùng `System.currentTimeMillis()` làm đồng hồ duration quan trọng; dùng timestamps wall-clock cho audit.

### 7.3. Không giữ thread trong backoff dài

Retry sau vài giây có thể thực hiện tại chỗ khi workload thấp và SLA cho phép. Với delay vài phút:

- Dùng retry queue/job **bền vững** có thời điểm chạy lại;
- Lưu business key, số attempts, next-attempt time, error category và trạng thái;
- Không giữ HTTP request thread, JMS listener session hoặc SFTP connection trong khi ngủ;
- Có lease/claim khi nhiều replica chạy retry worker;
- Có TTL/maximum age, DLQ và chính sách hủy khi business request hết hiệu lực;
- Có alert cho backlog và oldest retry item.

**Backoff tại chỗ** không tự bảo đảm message sống sót qua process restart. Một timer in-memory dùng cho tác vụ quan trọng cần được thay hoặc bổ sung durable mechanism.

## 8. Idempotency: điều kiện tiên quyết khi redelivery có thể xảy ra

### 8.1. Business key ổn định

Chọn khóa được contract bảo đảm ổn định qua retry:

- `(sourceSystem, sourceEventId)` cho sự kiện có ID nguồn đáng tin;
- `(tenantId, orderId, revision)` cho xử lý một phiên bản đơn hàng;
- `paymentRequestId` cho thao tác thanh toán được đối tác hỗ trợ idempotency;
- `(fileSource, fileBusinessId, contentVersion)` nếu file có version rõ.

Không mặc định sử dụng Spring `MessageHeaders.ID`, Kafka offset, file name hoặc correlation ID làm business dedupe key cho mọi tình huống. Những giá trị này có phạm vi và lifecycle khác nhau.

### 8.2. Transactional idempotency pattern

~~~text
receive(message):
    key = stableBusinessKey(message)
    validate(message)

    begin database transaction
        if processed_message(key) already committed:
            commit
            return ALREADY_PROCESSED

        applyBusinessMutation(key)
        insertProcessedKeyWithUniqueConstraint(key)
        insertOutboxEvent(key, outboundEvent)
    commit

    # Ack nguồn theo semantics adapter.
    # Outbox worker publish độc lập với retry idempotent.
~~~

Để tránh race condition khi hai workers nhận cùng key, phải có **unique constraint/transaction isolation hoặc lock** phù hợp; SELECT trước INSERT không đủ. Nếu một outbound side effect xảy ra **ngoài** DB transaction, cần idempotency hoặc reconciliation riêng.

### 8.3. Timeout tạo trạng thái không rõ kết quả

Một yêu cầu POST, publish hoặc commit bị timeout **sau khi gửi** có thể đã thành công. Nếu không chắc:

1. Ghi trạng thái `UNKNOWN_OUTCOME` cùng business key.
2. Tra cứu kết quả ở hệ ngoài bằng API/query/reconciliation khi có.
3. Nếu đích hỗ trợ idempotency, retry bằng **cùng khóa**.
4. Nếu không hỗ trợ, yêu cầu owner xác minh hoặc workflow bù trừ phù hợp.
5. Không coi timeout là bằng chứng “chưa thực hiện”.
6. Sau khi kết quả rõ, cập nhật state, ack/replay theo contract.

## 9. Spring Integration: advice, errorChannel và điểm đặt retry

Spring Integration xử lý các message qua endpoint và channel. Cơ chế retry có thể là **advice quanh handler** hoặc nằm tại **source/listener/container**, tùy mô hình.

### 9.1. RequestHandlerRetryAdvice

`RequestHandlerRetryAdvice` có thể bọc một **message handler** để thử lại khi handler ném exception theo policy. Nó không tự bảo đảm mọi nguồn redelivery, transaction hay idempotency.

**Ví dụ Spring Retry + Spring Integration (minh họa cấu hình cho thao tác remote idempotent như GET):**

~~~java
import java.net.SocketTimeoutException;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Bean
RequestHandlerRetryAdvice idempotentReadRetryAdvice() {
    RetryTemplate template = RetryTemplate.builder()
            .maxAttempts(4)
            .exponentialBackoff(500L, 2.0, 5_000L, true)
            .retryOn(SocketTimeoutException.class)
            .build();

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    return advice;
}
~~~

Đoạn code thể hiện **max attempts, exponential backoff có random và class lỗi được phép retry**. Việc `SocketTimeoutException` có xuất hiện trực tiếp hay nằm trong wrapper phụ thuộc handler/client: cần thiết kế exception classifier và test cause chain theo phiên bản Spring Retry đang dùng. Cũng cần kiểm tra builder/API của **phiên bản Spring Retry cụ thể** trước khi biên dịch.

**Không gắn advice này vô điều kiện cho một handler POST không idempotent** hoặc một handler đã thực hiện nhiều side effect. Dù advice đúng kỹ thuật, retry scope sai vẫn có thể gây tác động lặp.

### 9.2. Chọn chỗ đặt advice

| Vị trí | Khi phù hợp | Cần tránh |
|---|---|---|
| Handler chỉ thực hiện GET/lookup | Có thể retry transient read errors tại chỗ | Giữ connection/thread trong backoff quá lâu |
| Outbound handler có idempotency key | Retry theo contract của remote | Đổi request ID mỗi attempt |
| Handler cập nhật DB | Transaction retry cho lỗi serialization/deadlock được xác minh | Retry cả handler sau khi outbound đã gửi |
| Inbound poller | Retry lấy nguồn sau lỗi tạm thời | Gây scan loop và duplicate file/row |
| JMS/AMQP listener container | Cho broker redeliver theo ack/transaction | Advice + broker retry nhân nhiều tầng |
| Kafka listener | Error handler/retry topic theo record/partition | Giả định DLT không ảnh hưởng ordering |

### 9.3. ErrorMessage và error channel

Với Spring Integration:

- `DirectChannel` đồng bộ có thể để exception nổi về sender, ảnh hưởng rollback/ack.
- Với poller, executor hoặc listener bất đồng bộ, error handling có thể dùng `ErrorMessage`, error channel và handler tùy cấu hình.
- Exception bị recover bằng cách log rồi return có thể khiến nguồn nghĩ thao tác đã thành công.
- Error channel **không** mặc định là một DLQ bền vững, cũng không mặc định tự retry.
- Phải biết **lỗi được rethrow, bị recover hay được chuyển vào store có xác nhận bền vững** trước khi upstream ack.

**Câu hỏi review:** Sau khi hết attempts, ai sở hữu message, đã lưu ở đâu, ai sẽ replay và bên nguồn đã acknowledge hay chưa?

### 9.4. Một policy cho mọi endpoint là anti-pattern

Lỗi từ SFTP stat, HTTP 503, JMS redelivery, Kafka commit và JDBC deadlock có boundary khác nhau. Nên dùng policy theo **adapter/operation** hoặc tối thiểu theo error category và side-effect class, không áp một `RetryTemplate` chung cho mọi handler chỉ vì tiện cấu hình.

## 10. HTTP adapter và gateway: phân loại theo status + operation

HTTP outbound thường là nơi lỗi retry dễ tạo tác động lặp nhất, vì request có thể đã được server xử lý trước khi response mất.

### 10.1. Ma trận HTTP

| Kết quả | Nhóm lỗi | Chính sách gợi ý | Điều kiện |
|---|---|---|---|
| **200/201/202** | Thành công theo contract | Không retry | Nếu 202, cần theo dõi trạng thái bất đồng bộ |
| **400/422** | Payload/business validation | Không retry cùng payload | Quarantine hoặc trả lỗi cho caller |
| **401** | Authentication | Chỉ refresh credential hợp lệ theo quy trình, có giới hạn | Không dùng refresh loop vô hạn |
| **403** | Authorization | Không retry | Sửa quyền sau kiểm soát, không bypass |
| **404** | Resource không tồn tại | Thường không retry | Chỉ retry khi API cam kết eventual consistency |
| **408** | Request timeout từ server | Retry có điều kiện | Cần biết side effect đã xảy ra chưa |
| **409** | Conflict | Không retry nguyên trạng theo mặc định | Có thể reread/recompute nếu conflict là optimistic locking |
| **412** | Precondition failed | Đọc lại state, quyết định lại | Không tự bỏ điều kiện `If-Match` |
| **425** | Too Early | Chỉ retry theo semantics của API và giao thức | Chú ý thao tác unsafe |
| **429** | Rate limited | Retry có giới hạn, dùng `Retry-After` khi có | Cần limiter dùng chung nếu quota cấp tenant |
| **500** | Server error | Thường là candidate cho transient retry | Phải bảo vệ POST/side effect bằng idempotency |
| **502/503/504** | Gateway/downstream unavailable | Retry bounded/backoff | Có thể response bị mất sau commit |
| **Network reset / connect refused** | Transport | Retry có điều kiện | Phân biệt trước gửi với sau khi gửi |
| **Client read timeout** | Transport/unknown outcome | Ưu tiên reconcile nếu request có side effect | Timeout không chứng minh server chưa làm việc |
| **TLS certificate invalid** | Security/config | Fail, alert | Không tắt hostname verification |

### 10.2. Idempotency theo HTTP method

- **GET/HEAD:** Thường có semantics an toàn về tác động nghiệp vụ, nhưng API thực tế vẫn có rate limits và side effect gián tiếp; bounded retry là ứng viên hợp lý khi lỗi transient.
- **PUT/DELETE:** Có semantics idempotent ở chuẩn HTTP, nhưng implementation có thể gắn side effect phụ; xác minh hợp đồng.
- **POST/PATCH:** Không mặc định idempotent. Nếu API có `Idempotency-Key` hoặc business request ID, giữ nguyên khóa trên mọi attempt; nếu không có, cần query/compensation thay vì retry mù.
- **202 Accepted:** Nghĩa request được chấp nhận xử lý bất đồng bộ; không tự retry chỉ vì business result chưa xuất hiện ngay. Theo dõi status endpoint/callback.

### 10.3. Deadline và Retry-After

Nếu gateway ingress chỉ còn 3 giây deadline trong khi đối tác yêu cầu `Retry-After: 30`, không giữ request chờ 30 giây. Hãy trả response đúng hợp đồng và chuyển thao tác retry sang hàng đợi bền vững nếu nghiệp vụ cho phép, hoặc fail/alert có kiểm soát.

**Checklist HTTP:**

- [ ] Chính sách được phân theo status, operation, idempotency và side-effect state.
- [ ] Connect/read/pool acquisition timeout có giới hạn và nằm trong retry budget.
- [ ] `Retry-After` được parse, giới hạn và giám sát.
- [ ] Không retry 400/422/403/certificate error bằng cùng request.
- [ ] Có circuit breaker/bulkhead tránh retry storm lên API đang suy giảm.
- [ ] Retry POST chỉ khi có idempotency contract hoặc reconciliation.
- [ ] Lỗi timeout sau remote commit được kiểm thử bằng request ID ổn định.
- [ ] API inbound trả status hợp lệ, không báo thành công khi business chưa hoàn tất.
- [ ] Client timeout/gateway reply timeout/proxy deadline không mâu thuẫn.

## 11. File inbound/outbound: retry chưa chắc cần kết nối mạng

File adapter làm việc với filesystem. Lỗi có thể là **file chưa hoàn tất**, **permission denied**, **disk full**, **sai schema** hoặc **tác động nghiệp vụ đã thực hiện nhưng file chưa được archive**.

### 11.1. Chia lỗi File thành bốn nhóm

| Lỗi | Có retry? | Biện pháp |
|---|---|---|
| File producer vẫn đang ghi | **Chờ file ready**, không parse ngay | Temporary filename/ready marker, stable-size check theo contract |
| I/O transient trên filesystem/network mount | Có điều kiện | Bounded retry, cảnh báo hạ tầng |
| Permission denied, path sai, disk full | Không retry nóng | Fix permission/capacity, alert và pause nếu cần |
| CSV/JSON sai schema | Không retry cùng bytes | Quarantine, thông báo producer |
| File đã được parse nhưng business commit lỗi | Retry theo transaction/side effect | Giữ file và business key cho re-drive |
| File đã business commit nhưng rename/move DONE thất bại | Không chạy lại nghiệp vụ mù | Reconcile processed state rồi archive |
| File quá lớn hoặc path traversal | Fail/security action | Giới hạn file/path, quarantine phù hợp |

### 11.2. Accept-once filter khác business idempotency

Một `AcceptOnceFileListFilter` hoặc persistent metadata filter giúp tránh lấy lại file đã nhìn thấy theo cấu hình. Tuy nhiên:

1. File có thể được mark là đã nhận **trước** khi handler business hoàn tất.
2. App có thể crash sau ingest nhưng trước DB commit.
3. File có thể bị thay nội dung với cùng tên.
4. Nhiều pod có thể cùng nhìn file nếu store/claim không được chia sẻ đúng.
5. Nếu metadata bị xóa, file có thể được poll lại.

**Thiết kế an toàn:** File-ready protocol + source metadata/filter + durable business processing state + idempotency key + trạng thái archive/quarantine. Không xem filter là cơ chế bảo đảm exactly-once end-to-end.

### 11.3. File outbound và ghi đè

Nếu retry thao tác tạo file sau timeout/lỗi I/O, phải xác định file đã tồn tại và hoàn chỉnh chưa. Có thể dùng deterministic filename, ghi temporary file rồi rename hoặc checksum/manifest. Không retry bằng cách tạo một filename ngẫu nhiên mới cho cùng business event vì consumer có thể xử lý hai bản.

**Checklist File:**

- [ ] Có ready/processing/done/failed và recovery khi restart.
- [ ] File lỗi dữ liệu không bị poll lặp mãi.
- [ ] Retry tạm thời không làm mất thứ tự nếu nghiệp vụ cần.
- [ ] Trạng thái business commit quyết định hoàn tất, không chỉ filter.
- [ ] Có kiểm thử file đã commit DB nhưng archive thất bại.
- [ ] Nếu dùng shared/network filesystem, locking và I/O failure semantics được xác minh.

## 12. SFTP: phân biệt transfer lỗi, metadata và file đích đã có

### 12.1. Phân loại lỗi SFTP

| Lỗi | Quyết định |
|---|---|
| Connection reset, remote session closed, timeout tạm thời | Retry bounded với reconnect và backoff |
| Server quá tải hoặc giới hạn số session | Giảm concurrency và chờ lâu hơn có jitter |
| SSH host key mismatch | **Không retry để bypass**; fail security |
| Authentication failed, private key hết hạn | Không retry nóng; rotate credential và alert |
| Remote path không tồn tại | Thường fail/alert; có thể retry nếu producer contract chấp nhận folder xuất hiện sau |
| Permission denied | Fail/config, không retry nguyên trạng |
| Remote file chưa ready hoặc đang upload | Chờ ready marker/rename, không coi corrupt |
| Download dở | Retry/resume theo khả năng client; kiểm tra checksum/content |
| Upload/rename timeout sau khi server đã ghi | Reconcile remote file/path trước retry |
| File đã download nhưng parse invalid | Quarantine dữ liệu, không retry network vô hạn |

### 12.2. Backoff phù hợp poller và session pool

Nếu poll interval 5 giây, session pool có 5 connection và remote server lỗi 30 phút, mỗi replica có thể liên tục reconnect, làm server quá tải khi trở lại. Cần:

- Retry bounded tại client hoặc poller theo contract;
- Reconnect backoff có jitter;
- Circuit breaker hoặc tạm pause endpoint khi remote outage kéo dài;
- Giới hạn concurrent transfers và inflight file;
- Persistent metadata/claim khi nhiều replica;
- Cảnh báo oldest pending file và session failure rate;
- Runbook resume/re-drive sau khi đối tác khôi phục.

### 12.3. Resume upload và trạng thái mơ hồ

Một SFTP upload có thể thành công nhưng client mất response của `rename`. Không dùng ngay một filename mới hoặc copy file thứ hai. Hãy kiểm tra:

1. Temporary path còn tồn tại không?
2. Final path đã xuất hiện chưa?
3. File size/checksum/manifest có khớp không?
4. File đích có được consumer xử lý chưa, có cơ chế dedupe không?
5. Một retry có ghi đè file không cùng version không?

**Checklist SFTP:**

- [ ] Host-key verification, session timeout, retry/backoff rõ ràng.
- [ ] File-ready protocol được phía đối tác xác nhận.
- [ ] Có idempotency theo source + file/version hoặc business record.
- [ ] Lỗi auth/permission/host key được tách khỏi transient network.
- [ ] Có recovery cho file đã tải nhưng business xử lý chưa xong.
- [ ] Có runbook kiểm chứng remote upload outcome.

## 13. JMS: redelivery thuộc broker/container chứ không chỉ handler advice

Với JMS listener, **exception propagation**, transaction và acknowledge mode quyết định broker có redeliver hay không. Đây là khác biệt lớn so với retry một phương thức Java.

### 13.1. Trình tự cần hiểu

~~~text
JMS broker -> listener receives message
              |
              +-> business handler begins
              +-> DB commit successful
              +-> listener/process crash before JMS ack
              |
JMS broker redelivers (theo session/transaction policy)
              |
              +-> consumer idempotency avoids duplicate business effect
~~~

**Nếu handler đã commit DB nhưng ack chưa hoàn tất**, không có lựa chọn retry chỉ bằng “tăng timeout” để biến nó thành exactly-once. Phải dùng idempotency.

### 13.2. Checklist JMS

- [ ] Xác định session transacted/acknowledgement mode và thời điểm ack thực tế.
- [ ] Chọn retry owner: handler advice **hoặc** broker redelivery, tránh nhân attempts không chủ đích.
- [ ] Broker/JMS provider có policy giới hạn redelivery và DLQ được kiểm chứng.
- [ ] Poison message sai schema không redeliver vô hạn.
- [ ] Lỗi DB tạm thời có retry budget phù hợp transaction/ack.
- [ ] Listener concurrency/prefetch không làm cạn connection hoặc phá ordering.
- [ ] Request/reply gateway có reply timeout và late reply handling.
- [ ] Có idempotency key qua nhiều lần broker phát lại.
- [ ] Có audit và metric redelivery count/age, DLQ backlog, pending queue.
- [ ] Đã thử broker restart và listener crash ở các điểm trước/sau commit/ack.

### 13.3. Đừng nuốt exception khi muốn redelivery

Một handler có thể catch exception rồi chỉ log:

~~~java
try {
    processBusiness(message);
} catch (Exception ex) {
    log.warn("processing failed", ex);
    // Không rethrow
}
~~~

Trong nhiều cấu hình listener, handler return thành công có thể khiến container/broker acknowledge dù nghiệp vụ thất bại. Nếu recovery quyết định **lưu bền vững vào quarantine** rồi ack, phải chứng minh thao tác lưu quarantine đã thành công. Nếu chưa có recovery, cần để exception đi theo đúng cơ chế rollback/redelivery.

### 13.4. JMS request/reply

Nếu JMS gateway timeout khi chờ reply:

- Request vẫn có thể đang xử lý ở consumer.
- Reply muộn có thể đến sau khi gateway bỏ correlation.
- Retry phải dùng business ID/idempotency contract.
- Không tăng redelivery và gateway retry đồng thời mà không tính tổng attempts.
- Nếu xử lý lâu, chuyển durable async request/status thay vì giữ synchronous RPC.

## 14. AMQP/RabbitMQ: publisher retries, consumer requeue và DLQ

### 14.1. Producer publish là một loại retry riêng

Publisher có thể gửi message nhưng mất connection **trước khi nhận broker confirm**. Không có confirm không đồng nghĩa message chưa vào broker. Retry publish có thể tạo duplicate, do đó:

- Dùng stable message/business ID;
- Có cơ chế publisher confirms/returns nếu cần theo topology;
- Log/đối soát ambiguous publishes;
- Consumer downstream phải idempotent;
- Không dùng random ID mới mỗi lần retry cho cùng sự kiện;
- Có outbox hoặc delivery ledger nếu business yêu cầu recover sau restart.

### 14.2. Consumer acknowledgement

| Phản ứng khi handler lỗi | Điều có thể xảy ra | Kiểm soát |
|---|---|---|
| **Nack/requeue** | Broker giao lại record; có thể rất nhanh | Bounded policy/backoff và không loop |
| **Reject không requeue** | Message vào DLX/DLQ nếu topology hỗ trợ, nếu không có thể bị bỏ | Đảm bảo DLQ được cấu hình, quan sát và lưu đủ dữ liệu |
| **Ack sau recovery** | Broker coi xử lý xong | Chỉ khi đã lưu bền vững trạng thái thay thế hợp lệ |
| **Không ack do process chết** | Redelivery sau connection/channel close | Consumer idempotent |
| **Retry advice tại listener** | Lặp handler trong một delivery | Không kết hợp mù với broker requeue |

### 14.3. Cơ chế delayed retry

Tùy broker/topology, có thể dùng TTL + dead-letter exchange, delayed-message mechanism được hỗ trợ hoặc một application scheduler/queue để dời message. Phải kiểm tra:

- Delay thực tế và ordering;
- Message expiration và retention;
- Số attempts được lưu ở đâu;
- Poison message có tới DLQ cuối không;
- Nếu DLX/queue đích không tồn tại thì message mất hay được xử lý thế nào;
- Điều gì xảy ra nếu retry worker/publisher crash;
- Có ảnh hưởng queue gốc hoặc gây head-of-line blocking không.

**Checklist AMQP:**

- [ ] Publisher confirm/return và unknown outcome được xử lý.
- [ ] Consumer ack/requeue/reject policy rõ ràng.
- [ ] Error handler không requeue infinite poison message.
- [ ] Có DLQ, retention, replay runbook và alert.
- [ ] Backoff/delayed retry không làm broker bị flooding.
- [ ] Consumer idempotent, đúng prefetch/concurrency.
- [ ] Test crash sau DB commit trước ack và confirm bị mất.

## 15. Kafka: phân biệt producer retries và record retry ở consumer

### 15.1. Kafka producer

Kafka producer có retry, acknowledgement, idempotence và giới hạn delivery theo Kafka client; nó không thể đảm bảo DB/HTTP side effect an toàn.

| Tình huống | Quy tắc |
|---|---|
| Metadata/broker tạm unavailable | Client retry theo policy khi hợp lệ; giới hạn block/delivery timeout |
| Kafka producer delivery timeout | Callback có lỗi; record có thể có trạng thái không chắc chắn ở broker |
| Producer idempotence bật | Giảm duplicate từ retry của producer trong phạm vi hỗ trợ | Không bảo vệ khi ứng dụng tự tạo event ID mới |
| Outbox worker retry publish | Có thể publish trùng nếu broker đã nhận nhưng ack mất | Consumer vẫn phải idempotent |
| Schema/serialization error | Thường là lỗi permanent của record | Quarantine/correct schema, không gửi lặp mãi |
| ACL/authentication error | Fail/alert; không retry nóng | Sửa quyền/credential theo quy trình |

**Lưu ý:** Các tham số như `retries`, `delivery.timeout.ms`, `request.timeout.ms`, `retry.backoff.ms` có semantics và ràng buộc theo Apache Kafka client version. Không đặt một RetryTemplate bên ngoài producer rồi coi đó là cơ chế delivery duy nhất.

### 15.2. Kafka consumer

Với Kafka listener, Spring for Apache Kafka có các cơ chế error handler/retry topic/DLT tùy phiên bản, ví dụ `DefaultErrorHandler` hoặc `DeadLetterPublishingRecoverer`. Trong Spring Integration, phải xác định Kafka inbound adapter đang sử dụng **listener container nào**, ai sở hữu error handling và khi nào offset được commit.

| Lỗi | Cách xử lý thường phù hợp |
|---|---|
| Network/broker outage | Reconnect/client retry có kiểm soát, alert |
| Deserialization/schema lỗi | Error recovery/quarantine theo record, không poison partition vô hạn |
| Transient DB timeout | Bounded retry trong transaction hoặc retry topic phù hợp |
| Business validation permanent | DLT/quarantine, theo contract và offset policy |
| Handler bug lặp lại | Có giới hạn attempts; cảnh báo owner sửa code |
| DB commit thành công, offset chưa commit | Consumer idempotency để redelivery an toàn |
| Record phải xử lý đúng thứ tự theo key | Cân nhắc block/retry đúng partition hoặc giữ ordering khi dời ra retry topic |

### 15.3. Blocking vs non-blocking retry

- **Blocking retry:** Giữ record/partition tại vị trí hiện tại và thử lại sau delay, có thể làm trễ các record theo sau. Phù hợp khi bảo toàn ordering là bắt buộc và delay ngắn.
- **Non-blocking retry:** Chuyển record sang retry topic/queue hoặc scheduler, cho record sau tiếp tục. Giúp throughput nhưng có thể **phá thứ tự nghiệp vụ** nếu revision sau được xử lý trước.
- **DLT:** Record không thể xử lý được đưa vào nơi cách ly. DLT publish phải thành công bền vững trước khi đường nguồn đánh dấu record đã recover theo chính sách.

**Ví dụ:** OrderRevision 2 lỗi, bị chuyển retry topic; Revision 3 ở partition chính được xử lý trước. Nếu business logic yêu cầu thứ tự 1→2→3, thiết kế retry topic cần cơ chế version gating hoặc chặn cùng business key.

### 15.4. Checklist Kafka

- [ ] Producer retry/delivery timeout/idempotence/acks được xác minh.
- [ ] Consumer error handler thuộc một tầng duy nhất, không retry nhân chồng.
- [ ] Phân loại deserialization/schema lỗi khác transient handler lỗi.
- [ ] DLT/retry topic có owner, ACL, retention, partition/key policy và alert.
- [ ] Khi record đã vào DLT, offset commit đúng và không mất record nếu DLT publish thất bại.
- [ ] Consumer DB side effect idempotent.
- [ ] Đã thử producer confirm/ack mất, rebalance và crash sau DB commit.
- [ ] Ordering theo partition/business key được bảo toàn hoặc khác biệt được phê duyệt.

## 16. JDBC/database: retry transaction, không retry toàn flow mù

JDBC có lỗi mạng, deadlock, serialization conflict, lock timeout, unique constraint và schema/permission error. Trong ứng dụng Spring, ngoại lệ có thể được chuyển thành họ `DataAccessException` theo cơ chế exception translation, hoặc xuất hiện dưới dạng `SQLException` có `SQLState` và vendor error code.

### 16.1. Phân loại lỗi database

| Lỗi | Retry? | Điều kiện |
|---|---|---|
| Deadlock được DB phát hiện | Thường có | Retry **nguyên transaction** có giới hạn, không lặp external side effect |
| Serialization/concurrent update conflict | Có điều kiện | Re-read state và recompute, optimistic lock |
| Lock wait/query timeout | Có điều kiện | Điều chỉnh contention/query, tránh retry storm |
| Connection reset trước khi thực thi | Có điều kiện | Retry bằng connection mới và idempotency |
| Connection loss lúc commit | **Unknown outcome** | Đối soát DB state bằng business key |
| Unique constraint/business duplicate | Không retry insert nguyên trạng | Idempotent success hoặc conflict review |
| Missing table/invalid SQL | Không | Sửa schema/migration/code |
| Permission denied/auth invalid | Không retry nóng | Quy trình security/credential |
| Disk full/quota/DB overload | Không retry ngay dồn dập | Giảm tải, alert, deferred retry |
| Constraint vi phạm nghiệp vụ | Không | Sửa dữ liệu hoặc rule, quarantine |

Theo chuẩn SQLState, các lớp như **08 (connection exception)**, **40 (transaction rollback)** thường giúp phân loại; **23 (integrity constraint violation)** và **42 (syntax/access rule)** thường không phù hợp retry mù. Mỗi database/driver có cách báo lỗi và mã riêng, phải review theo vendor cụ thể.

### 16.2. Retry ở ranh giới transaction phù hợp

Một cách thiết kế:

~~~text
retryableDatabaseOperation():
    for attempt in boundedAttempts:
        begin NEW transaction
            read latest state
            validate state transition
            write row with uniqueness/business version
        commit
        if success:
            return
        if transient deadlock/serialization conflict:
            backoff then retry
        else:
            fail

after committed transaction:
    outbox worker publishes external event
~~~

**Không** mở một transaction DB rồi retry cùng các câu SQL sau khi transaction đã bị đánh dấu rollback-only. Mỗi attempt cần transaction mới phù hợp và code re-read state khi cần. Tránh gọi HTTP/SFTP hoặc gửi broker event trực tiếp bên trong đoạn có thể retry nhiều lần.

### 16.3. Transactional outbox giải quyết cửa sổ nào?

Nếu business DB commit nhưng broker publish thất bại, retry **cả handler** có thể ghi DB thêm lần nữa. Với outbox, record nghiệp vụ và outbox event được ghi trong cùng transaction. Worker riêng gửi event với retry theo adapter/broker, có ledger trạng thái và consumer idempotent.

### 16.4. Checklist JDBC

- [ ] Driver/pool/query timeout cùng retry budget phù hợp.
- [ ] Loại lỗi dựa trên `DataAccessException`, SQLState/vendor code được kiểm thử.
- [ ] Retry deadlock/serialization ở transaction boundary có owner.
- [ ] Unique constraint ngăn cùng business key chạy song song.
- [ ] Lỗi connection loss lúc commit được đối soát trước retry.
- [ ] Không retry SQL syntax/constraint/permission bằng cùng input.
- [ ] Không giữ lock qua backoff hoặc remote API call.
- [ ] Có metric deadlock, lock wait, pool wait, query timeout và retries exhausted.
- [ ] Đã thử nhiều workers, DB failover và commit outcome ambiguous.

## 17. Scheduled retry, DLQ/quarantine và bền vững qua restart

### 17.1. Khi nào cần chuyển retry ra khỏi thread hiện tại?

| Tình huống | Hướng đề xuất |
|---|---|
| Một HTTP GET lỗi transient, dự kiến hồi phục trong vài giây | Bounded retry tại handler/client theo SLA |
| HTTP 429 yêu cầu chờ 60 giây, inbound deadline 15 giây | Durable retry job/queue, trả trạng thái async hợp lệ |
| SFTP server offline hàng giờ | Pause poller + backoff/reconnect theo runbook; giữ file upstream |
| JMS/AMQP message lỗi dữ liệu | Bounded redelivery rồi DLQ |
| Kafka poison record | Recovery/DLT có kiểm soát ordering |
| DB lock conflict vài lần ngắn | Retry transaction ngắn, có giới hạn |
| Đối tác thanh toán timeout sau commit có thể xảy ra | Unknown-outcome reconciliation trước retry |
| Consumer lỗi do bug cần hotfix | Quarantine, owner sửa và replay có phê duyệt |

### 17.2. Durable retry record

Một retry item nên lưu:

- Stable business key / source event ID, tenant và loại operation;
- Target/protocol/endpoint alias, không lưu raw secret;
- Payload hoặc reference bền vững được quản lý retention/PII;
- Error category và nguyên nhân kỹ thuật an toàn;
- Current attempt count, max attempts, nextAttemptAt;
- Deadline/expiry và chính sách hết hạn;
- Idempotency key, expected business version, prior outcome;
- Correlation ID, source offset/file marker, owner/reviewer;
- Status: PENDING, LEASED, SUCCEEDED, QUARANTINED, UNKNOWN_OUTCOME;
- Audit khi worker claim, retry, recover, replay hoặc xóa.

Nhiều instance cần **claim/lease phân tán** với expiry/recovery. Nếu một worker chết sau khi gọi remote nhưng trước khi đánh dấu success, retry worker khác sẽ xử lý lại — side effect phải idempotent.

### 17.3. DLQ khác retry queue

- **Retry queue:** Chứa các thao tác được xem là retryable, có lịch lần thử kế tiếp và ngân sách.
- **DLQ/DLT:** Chứa message đã vượt retry policy hoặc lỗi không thể tự phục hồi trong đường hiện tại.
- **Quarantine:** Cách ly thông tin sai contract/nhạy cảm/không chắc chắn để owner quyết định.
- **Unknown-outcome store:** Dùng khi chưa biết side effect thực tế của thao tác có rủi ro, cần reconciliation.

Không coi mọi message trong DLQ đều nên replay ngay sau khi service khởi động lại. Có thể contract hoặc state nghiệp vụ đã thay đổi, hoặc một phần side effect đã hoàn thành.

## 18. Observability, giới hạn tải và bảo mật khi retry

### 18.1. Không được thiếu thông tin nào trong log?

| Trường | Vì sao quan trọng |
|---|---|
| `eventId` / idempotency key | Ghép các lần retry của cùng yêu cầu |
| `correlationId` / trace ID | Truy vết ingress → handler → outbound |
| `source`, `target`, `adapterType` | Biết đối tác/broker/database nào lỗi |
| `errorCategory`, exception type/status | Phân loại transient, permanent, unknown |
| `attempt`, `maxAttempts` | Biết còn thử tiếp không |
| `elapsedMs`, `remainingBudgetMs` | Giải thích vì sao hủy retry |
| `backoffMs`, `retryAfter` | Phát hiện retry dồn dập |
| `sideEffectState` | Chưa gọi / đang xử lý / đã commit / không rõ |
| `ackState` / offset / file checkpoint | Điều tra redelivery hoặc mất dữ liệu |
| `recoveryTarget` | Retry queue, DLQ, quarantine hay incident |
| `instanceId`, handler/client version | Xác định lỗi theo replica/deployment |
| `outcome`, `owner`, `ticket` | Theo dõi phục hồi cuối cùng |

Không log token, password, SFTP private key, JDBC credential, Authorization header, session cookie hoặc payload nhạy cảm. Đặc biệt, **DLQ/DLT không phải kho dữ liệu có thể đọc tự do**: cần ACL, encryption và retention.

### 18.2. Metrics và alert

| Chỉ số | Dấu hiệu cần điều tra |
|---|---|
| Retry attempts theo target và error category | Tăng đột biến hoặc kéo dài |
| Retries exhausted | Những thao tác đã hết ngân sách |
| Backoff wait p50/p95 | Nhiều workers đang ngủ/throttled |
| Timeout/429/503/5xx rate | Dependency có vấn đề |
| Unknown outcome count và age | Side effect chưa xác minh |
| Circuit breaker open duration | Dependency suy giảm kéo dài |
| Handler/integration error rate | Lỗi tăng sau release hoặc schema change |
| DLQ/DLT/quarantine size và oldest age | Message lỗi không có xử lý |
| Kafka lag/JMS-AMQP queue depth | Backlog do retry hoặc nguồn không xử lý |
| File/SFTP oldest pending file | Remote outage hoặc file stuck |
| DB deadlock/lock wait/pool exhaustion | Contention tăng hoặc retry sai |
| Deduplicated events count | Producer resend hoặc redelivery tăng |
| Business completion latency | Hệ hoàn tất trong SLA hay không |
| Dead-letter replay success/failure | Đánh giá runbook và idempotency |

Metric nên phân theo **adapter, operation, target, exception category và outcome**, nhưng không gắn mỗi eventId/userId làm metric tag làm tăng cardinality. Business ID phù hợp hơn trong log/trace có quyền truy cập.

### 18.3. Retry storm và thundering herd

Khi dependency khôi phục sau outage, hàng nghìn worker có thể đồng loạt retry.

- [ ] Dùng backoff có jitter và rate limit chung khi quota tính theo tenant/API key.
- [ ] Chặn retry vô hạn ở client, advice và broker.
- [ ] Dùng circuit breaker/bulkhead để không giữ hết threads/connections.
- [ ] Đặt bounded channel queue, poller throttle và concurrency limit.
- [ ] Theo dõi backlog drain rate khi dependency hồi phục.
- [ ] Với batch replay, giới hạn batch size và số thao tác inflight.
- [ ] Nếu quota là global, cân nhắc distributed limiter hoặc phối hợp giữa replicas.
- [ ] Không chọn retry delay quá ngắn chỉ để hạ latency trung bình trong test local.

### 18.4. Những lỗi không được bị che bởi retry

- TLS certificate/SSH host key lỗi;
- 403/broker ACL denied/DB permission denied;
- Schema invalid, message không rõ version, dữ liệu bị giả mạo;
- Không đủ idempotency với thao tác thanh toán hoặc xóa tài nguyên;
- Credential lộ hoặc partner endpoint không đúng;
- Dead-letter message có dữ liệu cần phê duyệt trước replay.

Trong các trường hợp này cần **fail có kiểm soát, security/operational alert và owner review**, không tăng số lần thử.

## 19. Kiểm thử fault injection theo loại lỗi

Một policy chỉ được coi là sẵn sàng khi các lỗi đại diện đã được tạo ra trong môi trường kiểm thử và kết quả được **đọc lại tại hệ đích**. Không chỉ xác nhận một exception đã bị catch.

### 19.1. Cách thiết kế test

1. Chọn một business key ổn định và một message mô phỏng.
2. Đặt adapter và dependency trong môi trường giống production ở mức cần thiết.
3. Tiêm lỗi tại đúng điểm: trước gửi, trong gửi, sau remote commit, trước source ack.
4. Đo attempt count, backoff thực tế, elapsed/deadline và tài nguyên còn giữ.
5. Đọc business state tại DB, file, broker hoặc API đích.
6. Xác minh DLQ/quarantine hoặc retry queue có owner và đủ audit.
7. Khởi động lại worker, replay và đối soát không tạo tác động trùng.
8. Thử lại với nhiều replica/traffic song song, đặc biệt với cùng business key.

### 19.2. Ma trận 55 test cases

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| **T01** | HTTP GET bị connect timeout tạm thời | Bounded retry + backoff, thành công khi đích phục hồi |
| **T02** | HTTP 429 có Retry-After hợp lệ | Delay/rate limit không vượt deadline |
| **T03** | HTTP 429 có Retry-After cực lớn/sai format | Giá trị được validate/cap hoặc defer hợp lệ |
| **T04** | HTTP 503 kéo dài | Attempts exhausted, circuit/open hoặc durable retry |
| **T05** | HTTP 400 thiếu field | Không retry; validation/quarantine có reason |
| **T06** | HTTP 422 business validation | Không retry cùng payload |
| **T07** | HTTP 401 do token hết hạn | Refresh có giới hạn theo policy; không loop vô hạn |
| **T08** | HTTP 403 | Fail/alert, không retry |
| **T09** | HTTP TLS hostname mismatch | Fail closed, không bypass verification |
| **T10** | HTTP 409 optimistic conflict | Read current state/recompute, không retry nguyên lệnh mù |
| **T11** | HTTP POST commit xong nhưng response timeout | Reuse idempotency key hoặc reconcile, không double charge |
| **T12** | Proxy timeout trước backend | Outcome có audit; client retry không duplicate |
| **T13** | HTTP client, handler advice và ingress cùng retry | Tổng attempts không vượt ngân sách |
| **T14** | 500 workers nhận 503 cùng lúc | Jitter/limiter tránh peak đồng thời |
| **T15** | Request còn 1 giây deadline, backoff yêu cầu 5 giây | Không retry tại chỗ, chuyển deferred/fail |
| **T16** | SFTP TCP reset trong list | Retry bounded với reconnect an toàn |
| **T17** | SFTP host key mismatch | Không retry bypass, security alert |
| **T18** | SFTP authentication failed | Không retry nóng, incident credential |
| **T19** | SFTP file chưa ready | Chờ theo protocol, không parse hỏng |
| **T20** | SFTP download dở, retry | Không mất dữ liệu hoặc xử lý bản không đủ |
| **T21** | SFTP rename response timeout sau upload | Check remote checksum/state, tránh duplicate |
| **T22** | SFTP session pool quá tải | Giảm concurrency/backoff, không storm |
| **T23** | File input sai schema | Quarantine, không poll lại vô hạn |
| **T24** | File đã ghi DB nhưng archive thất bại | Reconcile business state rồi archive, không insert lại |
| **T25** | File có business ID trùng nhưng tên khác | Dedupe đúng business key |
| **T26** | File trên shared volume được hai pod nhận | Claim/idempotency giữ đúng một tác động |
| **T27** | JMS consumer bị kill trước ack, sau DB commit | Redelivery idempotent |
| **T28** | JMS poison message có 20 lần redelivery | Bounded policy chuyển DLQ, không chặn queue mãi |
| **T29** | JMS handler nuốt exception | Test phát hiện ack sai và sửa error propagation |
| **T30** | JMS RPC reply đến muộn | Correlation xử lý an toàn; không double side effect |
| **T31** | JMS broker restart khi message đang xử lý | Recovery/redelivery theo semantics có audit |
| **T32** | AMQP publish thành công nhưng confirm mất | Sender coi outcome mơ hồ; consumer idempotent |
| **T33** | AMQP consumer crash trước ack | Redelivery không nhân đôi business effect |
| **T34** | AMQP poison message bị requeue liên tục | Chặn storm, DLX/DLQ đúng |
| **T35** | AMQP DLQ đích không tồn tại | Alert topology, không lặng lẽ đánh dấu đã recover |
| **T36** | AMQP delayed retry qua TTL/DLX | Attempts/delay/ordering theo contract |
| **T37** | Kafka broker tạm unavailable khi producer gửi | Client retry có giới hạn, callback/delivery status |
| **T38** | Kafka producer callback timeout nhưng record vào broker | Consumer idempotent, sender không tạo ID mới |
| **T39** | Kafka serialization/schema error | Quarantine, không retry producer vô hạn |
| **T40** | Kafka consumer DB deadlock | Retry đúng transaction boundary |
| **T41** | Kafka consumer DB commit xong nhưng offset chưa commit | Redelivery không insert trùng |
| **T42** | Kafka record lỗi chuyển DLT | DLT durable, commit/recovery policy đúng |
| **T43** | Retry topic làm revision 3 chạy trước revision 2 | Ordering/version guard xử lý hợp lệ |
| **T44** | Kafka consumer rebalance giữa retry | Không mất record, không vượt budget |
| **T45** | JDBC deadlock | New transaction retry bounded, kết quả đúng |
| **T46** | JDBC serialization conflict | Reread/recompute theo business version |
| **T47** | JDBC unique key conflict do duplicate event | Idempotent no-op hoặc conflict review |
| **T48** | JDBC connection lost lúc commit | Reconcile DB state trước khi retry |
| **T49** | JDBC thiếu bảng/syntax invalid | Không retry, alert deployment |
| **T50** | JDBC pool cạn do 200 workers | Backpressure/circuit, không giữ vô hạn |
| **T51** | Quarantine replay sau sửa schema | Business key ngăn tác động lặp |
| **T52** | Worker retry chết khi đã claim job | Lease/recovery xử lý lại an toàn |
| **T53** | Deadline hết trong lúc backoff | Dừng local attempts; durable handoff nếu phù hợp |
| **T54** | Pod rolling restart khi còn retry queue | Pending state còn bền vững, không mất event |
| **T55** | Circuit breaker mở do retry storm | Dependency không bị tiếp tục dồn tải, có recovery policy |

**Bằng chứng cho mỗi test:** expected/actual result, adapter/target, error category và exception chain, business/event ID, configured policy, attempts thực tế, tổng elapsed, side-effect state, ack/offset, DLQ record/correlation ID, người kiểm tra và issue cần xử lý.

## 20. Runbook: khi retry tăng cao hoặc message mắc kẹt

### 20.1. Chẩn đoán theo thứ tự

1. **Nhận diện:** Adapter/endpoint nào đang có retry tăng, từ khi nào?
2. **Phân loại lỗi:** Transient network, overload, schema, auth, conflict hay unknown outcome?
3. **Xem trạng thái nguồn:** Message đã ack? Offset đã commit? File đã được mark accepted/archived?
4. **Xem trạng thái đích:** DB đã commit? HTTP remote side effect đã thực hiện? Kafka broker đã nhận? SFTP file tồn tại?
5. **Kiểm tra retry owner:** Client, advice, listener, broker, scheduled worker hay operator?
6. **Tính ngân sách:** Attempts × timeout + backoff, deadline và max in-flight có an toàn?
7. **Đánh giá phụ thuộc:** Remote server đang down/rate limit hay code vừa đổi schema?
8. **Giảm tải:** Pause poller, giảm concurrency, mở circuit, chuyển deferred retry nếu cần.
9. **Phục hồi:** Fix root cause, replay có idempotency, đo business completion.
10. **Đóng incident:** Xác minh backlog drain, DLQ age giảm, audit và postmortem.

### 20.2. Quyết định theo loại lỗi khi vận hành

| Quan sát | Không nên làm | Hành động nên làm |
|---|---|---|
| HTTP 429 liên tục | Tăng số attempts không giới hạn | Tôn trọng quota/Retry-After, limiter và deferred retry |
| HTTP POST timeout | Gửi request với ID mới | Query remote result hoặc retry cùng idempotency key |
| TLS/SSH host-key mismatch | Tắt xác minh bảo mật | Dừng và xác minh thay đổi certificate/key |
| SFTP file thiếu dữ liệu | Retry parse mãi | Kiểm tra ready protocol hoặc quarantine |
| JMS/AMQP poison message | Requeue ngay vô hạn | DLQ + owner sửa root cause |
| Kafka consumer lag do retry record lỗi | Reset offset tùy tiện | Phân loại lỗi, recovery/DLT có ordering policy |
| DB deadlock nhiều | Chỉ tăng attempts | Phân tích lock/query, giảm contention, bounded transaction retry |
| DB connection mất lúc commit | Insert lại ngay | Reconcile bằng business ID và transaction state |
| Retry queue tăng nhưng success rate giảm | Tăng concurrency vô hạn | Giảm tải, circuit/bulkhead, đánh giá dependency |
| DLQ record xử lý lại thất bại | Xóa message | Ghi nhận failure, cập nhật policy/runbook |

### 20.3. Replay sau khi sửa lỗi

- [ ] Owner xác nhận nguyên nhân đã sửa hoặc có ngoại lệ được phê duyệt.
- [ ] Đối soát side effect của từng message quan trọng trước replay.
- [ ] Sử dụng **business key cũ**, không đổi eventId để “né dedupe”.
- [ ] Thử batch nhỏ và giới hạn concurrent retries.
- [ ] Giữ ordering theo business key nếu contract yêu cầu.
- [ ] Theo dõi queue/DLT/DB actual state và message completion.
- [ ] Không replay message quá TTL nếu hành động không còn hợp lệ.
- [ ] Chỉ xóa/retire DLQ record theo retention và audit.

## 21. Case study: SFTP → JDBC/outbox → Kafka + HTTP

Giả sử dịch vụ nhận CSV đơn hàng từ SFTP mỗi 5 phút, chuẩn hóa dữ liệu, ghi database, phát Kafka event và gọi HTTP để đăng ký vận chuyển. Producer có thể gửi file trùng và partner HTTP đôi khi trả 429 hoặc timeout.

### 21.1. Thiết kế ban đầu thiếu an toàn

- Poller SFTP quét mỗi 2 giây và retry ngay khi remote không kết nối.
- Parse file lỗi cũng bị retry như network error.
- DB insert không có unique constraint; file retry làm tạo hai order.
- HTTP POST logistics được gọi lại với request ID mới sau timeout.
- Handler phát Kafka ngay sau DB commit, không có outbox.
- Kafka consumer lỗi sẽ retry vô hạn, làm partition chậm.
- Không có metric retries exhausted và unknown outcome.
- Không giới hạn số replica/poller, tạo thundering herd khi SFTP phục hồi.

### 21.2. Thiết kế cải thiện

**SFTP:** Có file-ready marker, host-key verification, bounded reconnect backoff với jitter và giới hạn transfer. File parse invalid đi quarantine; file chưa hoàn tất chờ source thay vì parse lại liên tục. Có distributed claim/metadata và business idempotency.

**JDBC:** Mỗi order có `(partnerId, orderId, revision)` duy nhất. Transaction ghi order + processed key + outbox event. Deadlock/serialization có retry **ở transaction boundary**, không bao trùm remote HTTP.

**Kafka:** Outbox publisher retry theo client/broker settings; event giữ ID ổn định. Consumer phía nhận vẫn idempotent. Record poison chuyển DLT/recovery theo policy ordering.

**HTTP logistics:** 429 dùng Retry-After trong deadline; lỗi 503 retry bounded. Khi POST timeout sau khả năng remote commit, query logistics status bằng business shipment ID hoặc retry với **cùng idempotency key** nếu API hỗ trợ.

**Error flow:** Permanent schema lỗi → quarantine; transient network lỗi → retry/backoff; unknown outcome → reconciliation queue; exhausted retries → DLQ/ticket; owner có runbook replay. Trong mọi trường hợp, không ack hoặc archive file khi nghĩa vụ nghiệp vụ chưa bảo đảm theo contract.

### 21.3. Chọn budget minh họa

| Operation | Attempts | Per-attempt timeout | Backoff | Ràng buộc |
|---|---:|---:|---|---|
| SFTP list khi remote lỗi tạm | 3 | 5 s | 1 s, 2 s + jitter | Pause poller nếu outage kéo dài |
| JDBC transaction deadlock | 3 | 4 s | 100 ms, 300 ms có jitter | Retry transaction mới |
| Kafka outbox publish | Theo producer + worker policy | Phụ thuộc delivery timeout | Bounded/backoff | Event ID giữ nguyên, consumer dedupe |
| HTTP GET tra trạng thái | 3 | 3 s | 0,5 s, 1 s có jitter | Chỉ trong remaining deadline |
| HTTP POST logistics có idempotency key | 2 | 4 s | 1 s + jitter | Same key; nếu ambiguous thì verify |
| HTTP POST không có idempotency | Không retry mù | 4 s | Không áp tự động | Reconcile hoặc manual review |

Đây là **số liệu giả định**, không phải ngưỡng chuẩn. Dự án thực cần đo latency p95/p99, rate limit, transaction cost, SLO và khả năng idempotent của từng hệ.

### 21.4. Ba failure drills chính

**Drill A — DB đã commit, worker chết trước Kafka publish.** Outbox vẫn giữ event; publisher khác gửi sau restart. Business record không bị thêm lần hai.

**Drill B — HTTP đối tác commit, response mất.** Dịch vụ đánh dấu unknown outcome, xác minh shipment theo business ID hoặc retry cùng idempotency key; không tạo shipment thứ hai.

**Drill C — SFTP lỗi mạng 20 phút, sau đó phục hồi.** Poller giảm tốc/được pause có kiểm soát, không sinh hàng nghìn connection retry đồng thời. File pending vẫn được xử lý, không bị bỏ sót hoặc xử lý duplicate.

### 21.5. Điều kiện nghiệm thu

- Retry chỉ xảy ra cho lỗi được cho phép và side effect đủ an toàn.
- Mọi error category có recovery path và owner.
- Không mất order hoặc tạo order trùng qua crash/retry test.
- Kafka/JMS/AMQP redelivery không gây duplicate business effect.
- SFTP/file không biến mất khi parse/commit lỗi.
- Timeout và Retry-After không làm vượt SLA đồng bộ.
- Backlog, DLQ và unknown-outcome queue được giám sát.
- Replay runbook và rollback được thử bằng dữ liệu đại diện.

## 22. Mẫu cấu hình chính sách retry để review

Đây là một **định dạng YAML minh họa do ứng dụng tự định nghĩa**, không phải property tự động được Spring Integration/Spring Boot nhận. Đội phát triển phải bind, validate và thực thi bằng adapter/client/error handler tương ứng.

~~~yaml
flow: supplier-orders
owner:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations

retryPolicies:
  http-read:
    operation: idempotent-GET
    transientCategories: [NETWORK, HTTP_429, HTTP_503]
    maxAttemptsIncludingFirst: 3
    perAttemptTimeout: 3s
    backoff:
      type: exponential-full-jitter
      initial: 500ms
      max: 5s
    deadlineSource: inbound-request
    exhaustedAction: durable-retry-or-fail

  logistics-create:
    operation: POST
    idempotencyKey: partner-orderId-shipmentRevision
    transientCategories: [HTTP_429, HTTP_503, NETWORK_TIMEOUT]
    maxAttemptsIncludingFirst: 2
    backoff:
      type: retry-after-then-jitter
      max: 10s
    ambiguousOutcome: verify-by-shipmentId
    exhaustedAction: UNKNOWN_OUTCOME_QUEUE

  sftp-read:
    operation: DOWNLOAD
    transientCategories: [NETWORK_RESET, SESSION_CLOSED]
    permanentCategories: [HOST_KEY_MISMATCH, AUTH_FAILED, ACCESS_DENIED]
    maxAttemptsIncludingFirst: 3
    backoff:
      type: exponential-jitter
      initial: 1s
      max: 30s
    exhaustedAction: pause-and-alert

  jdbc-transaction:
    operation: BUSINESS_TRANSACTION
    transientCategories: [DEADLOCK, SERIALIZATION_FAILURE]
    maxAttemptsIncludingFirst: 3
    backoff:
      type: exponential-jitter
      initial: 100ms
      max: 1s
    duplicatePolicy: unique-business-key
    exhaustedAction: fail-to-source-retry-policy

  kafka-consumer:
    operation: PROCESS_RECORD
    transientCategories: [DB_TEMPORARY_FAILURE]
    permanentCategories: [INVALID_SCHEMA]
    maxAttemptsIncludingFirst: 4
    exhaustedAction: DLT
    orderingConstraint: preserve-order-per-business-key

controls:
  failOnUnknownCategory: true
  deduplicateByBusinessKey: true
  maxInflightPerTarget: REVIEW_REQUIRED
  circuitBreaker: reviewed-per-target
  auditDecision: true

approval:
  businessOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

**Lưu ý:** Mẫu trên diễn đạt intent; danh mục errorCategory, thuật toán jitter và behavior phải do code/connector thực tế implement và test. Không chuyển trạng thái GO khi còn `REVIEW_REQUIRED` hoặc `PENDING`.

### 22.1. Phiếu kiểm tra policy cho một handler

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Error classifier | Dựa trên exception/status/SQLState nào? Có unwrap cause? |
| Operation | Đọc hay ghi? Side effect có idempotent không? |
| Retry owner | Client, handler advice, container, broker hay worker? |
| Attempts | Có tính cả lần đầu? Giới hạn bao nhiêu? |
| Per-attempt timeout | Những connection/pool/read/query stages nào được bao phủ? |
| Backoff | Fixed/exponential/jitter/Retry-After với cap nào? |
| Deadline | Synchronous SLA còn đủ trước retry không? |
| Ordering | Có nguy cơ vượt record/phiên bản phía sau không? |
| Transaction/ack | Khi retry/recovery, message nguồn đang ở trạng thái nào? |
| Exhaustion | DLQ/quarantine/unknown-outcome/fail ra sao? |
| Visibility | Có log, metric, alert và correlation ID không? |
| Recovery | Ai replay, điều kiện nào và đối soát state ở đâu? |

## 23. Quyết định go/no-go và checklist triển khai

### 23.1. Checklist bắt buộc

- [ ] Có taxonomy lỗi cho từng adapter và operation.
- [ ] Lỗi permanent/auth/security không bị retry nóng.
- [ ] Có stable business ID/idempotency key và test duplicate.
- [ ] Có đúng một retry owner chính; đã kiểm tra client/advice/container/broker retries chồng nhau.
- [ ] Số attempts, per-attempt timeout, backoff và jitter nằm trong deadline.
- [ ] Có Retry-After/rate limit/circuit breaker khi target hỗ trợ hoặc cần bảo vệ.
- [ ] Source ack/offset/file archive gắn với durable business outcome.
- [ ] Có DLQ/DLT/quarantine bền vững và runbook replay.
- [ ] Có cơ chế UNKNOWN_OUTCOME và reconciliation cho thao tác side effect.
- [ ] Có guardrail cho retry storm, queue growth, nhiều replica và overload.
- [ ] Có metrics retry attempts/exhausted, DLQ age và business completion.
- [ ] Đã thử crash, redelivery, late response, broker outage và DB failover.
- [ ] Có owner, on-call, canary và rollback plan.
- [ ] Mọi ngoại lệ và chính sách nhạy cảm đã được phê duyệt.

### 23.2. Quyết định nghiệm thu

| Trạng thái | Điều kiện |
|---|---|
| **GO** | Loại lỗi được phân loại, idempotency/recovery đã test, SLO và bảo mật đạt |
| **GO WITH EXCEPTION** | Ngoại lệ giới hạn phạm vi, có owner, expiry và mitigation được duyệt |
| **HOLD / RETEST** | Chưa có kết quả fault injection hoặc chưa xác minh retry/ack semantics |
| **NO-GO** | Retry tạo side effect trùng, làm mất message, bypass bảo mật hoặc không có recovery path |

Không dùng “GO WITH EXCEPTION” để hợp thức hóa retry POST không idempotent chứa thao tác tài chính hoặc mất dữ liệu đã xác định mà không có kiểm soát thay thế phù hợp.

## 24. Những anti-pattern thường gặp

**Retry mọi exception:** schema invalid, 403 và lỗi network được xử lý giống nhau; tạo tải và không bao giờ sửa nguyên nhân. Phân loại lỗi có policy.

**Một RetryTemplate dùng cho mọi adapter:** JMS redelivery, Kafka offsets, HTTP request và JDBC transaction có ranh giới khác nhau. Gán policy theo operation/side effect.

**Retry nhiều tầng không có budget:** client 3 attempts × handler 4 × broker 5 gây số lần gọi tăng vọt. Xác định retry owner.

**Exponential backoff không jitter:** hàng trăm replica hồi phục cùng lúc có thể làm dependency sập lại. Thêm jitter, limiter và circuit.

**Coi timeout nghĩa chưa gửi:** HTTP/AMQP/Kafka có thể đã thực hiện dù caller không nhận response. Ghi unknown outcome và đối soát.

**Đổi idempotency key sau mỗi attempt:** biến cùng một yêu cầu thành nhiều lệnh mới; phải giữ key ổn định.

**Catch exception rồi chỉ log:** có thể làm container/source ack message thất bại như thành công. Xác định rollback/rethrow/recover rõ.

**Retry toàn handler gồm DB + HTTP + broker:** một lần thử có thể đã commit nhiều side effect. Tách ranh giới transaction/outbox.

**Dùng retry ngủ nhiều phút trong HTTP thread hoặc poller:** làm cạn threads/connection pool. Chuyển sang scheduled durable retry.

**Kafka retry topic mà bỏ quên ordering:** revision sau vượt revision lỗi. Có policy per-key/version gating.

**RabbitMQ requeue poison message vô hạn:** broker/consumer bị kẹt. Bounded attempts và DLQ.

**File accept-once filter là exactly-once:** filter không chứng minh DB commit thành công. Có business idempotency và recovery.

**DB deadlock thì retry trên transaction rollback-only:** phải tạo transaction mới phù hợp, reread state.

**Tăng maxAttempts để giải quyết mọi outage:** làm latency và áp lực cao hơn. Giảm tải, alert và sửa nguyên nhân.

**Xóa DLQ sau khi service hồi phục:** mất bằng chứng và khả năng replay. Quản lý retention/owner và audit.

## 25. Tự kiểm tra và tài liệu nền tảng

### 25.1. Câu hỏi ôn tập

1. Retry, broker redelivery và manual replay khác nhau thế nào?
2. Vì sao một HTTP 503 có thể retry nhưng một HTTP 422 thường không?
3. Khi HTTP 401 xảy ra, có trường hợp nào hợp lệ để thử lại? Tại sao 403 khác?
4. `Retry-After` cần được kiểm tra cùng deadline như thế nào?
5. Vì sao `maxAttempts=4` thường chỉ có ba khoảng backoff?
6. Thêm jitter giải quyết hiện tượng gì khi nhiều replica cùng lỗi?
7. Khi exception bị bọc trong `MessageHandlingException`, classifier cần làm gì?
8. Vì sao RequestHandlerRetryAdvice không tự bảo đảm idempotency?
9. Khi handler lỗi nhưng error handler chỉ log rồi return, source ack có thể sai thế nào?
10. Khi SFTP download xong nhưng parse/DB commit lỗi, có nên bỏ file khỏi nguồn không?
11. Vì sao HTTP POST timeout chưa thể kết luận phía nhận chưa tạo resource?
12. JMS broker redelivery khác retry tại handler advice ở đâu?
13. AMQP publisher confirm bị mất có nghĩa broker chắc chắn chưa nhận message không?
14. Kafka producer retries và Kafka listener error handler khác nhiệm vụ thế nào?
15. Kafka retry topic/DLT có thể ảnh hưởng thứ tự per-key như thế nào?
16. DB deadlock nên retry tại ranh giới nào?
17. Vì sao unique constraint quan trọng hơn SELECT kiểm tra key trước khi INSERT?
18. Khi cùng một exception được client, advice và broker retry, làm sao tính tổng attempts?
19. Khi nào nên dùng durable scheduled retry thay vì sleep trong thread?
20. Những bằng chứng nào đủ để xác nhận replay DLQ không nhân đôi tác động nghiệp vụ?

**Gợi ý trả lời:** Mỗi tình huống cần mô tả **loại lỗi → mức độ an toàn của operation → retry owner → attempts/backoff/deadline → ranh giới side effect và ack → cách đối soát kết quả cuối cùng**.

### 25.2. Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Transient / permanent** | Lỗi có thể tự phục hồi / lỗi cần sửa dữ liệu, cấu hình hoặc code |
| **Retry policy** | Quyết định điều kiện, số lần và nơi thực hiện thử lại |
| **Backoff** | Khoảng chờ giữa các lần thử |
| **Jitter** | Ngẫu nhiên hóa delay để giảm retry đồng pha |
| **Retry-After** | Tín hiệu server hướng dẫn thời điểm có thể thử lại |
| **Retry budget / deadline** | Giới hạn attempts và thời gian còn lại của luồng |
| **Idempotency key** | Khóa giúp xử lý lại mà không tạo tác động nghiệp vụ lặp |
| **Unknown outcome** | Không biết chắc side effect phía nhận đã hoàn thành chưa |
| **ErrorMessage / errorChannel** | Cơ chế thông báo/xử lý lỗi trong Spring Integration |
| **RequestHandlerRetryAdvice** | Advice áp retry quanh handler theo policy |
| **DLQ / DLT / quarantine** | Nơi chứa message lỗi hoặc chưa thể phục hồi |
| **Redelivery** | Nguồn/broker giao lại một message chưa hoàn tất |
| **Circuit breaker / bulkhead** | Giảm gọi dependency lỗi / giới hạn tài nguyên bị chiếm |
| **Transactional outbox** | Lưu nghĩa vụ gửi event trong transaction DB nghiệp vụ |
| **Reconciliation** | Đối soát actual side effect/state với desired state |
| **Poison message** | Dữ liệu gây lỗi lặp, cần cách ly hoặc sửa |
| **Soak / fault injection test** | Kiểm thử thời gian dài / chủ động tạo lỗi |

### 25.3. Tài liệu cần tra cứu theo phiên bản đang dùng

- **Spring Integration Reference Guide:** Request-handler advice, polling consumer, MessageChannel, error handling, endpoint lifecycle, File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC endpoints.
- **Spring Retry Reference:** RetryTemplate, RetryPolicy, BackOffPolicy, exception classification, recovery callbacks và RetryContext.
- **Spring for Apache Kafka Reference:** listener container error handling, DefaultErrorHandler, DeadLetterPublishingRecoverer, non-blocking retries/retry topics và transactions.
- **Spring AMQP Reference / RabbitMQ documentation:** publisher confirms, listener retry, consumer acknowledgement, redelivery, requeue, DLX/DLQ và TTL.
- **Jakarta Messaging (JMS) và tài liệu broker vendor:** acknowledgement, transacted sessions, redelivery policy, reply destination và DLQ.
- **Apache Kafka Client Documentation:** producer retries/delivery timeout/idempotence, consumer offsets, group rebalance và semantics của từng release.
- **HTTP semantics (RFC 9110) và tài liệu API đối tác:** idempotent methods, 429/5xx, Retry-After, request idempotency và error contracts.
- **JDBC driver / database vendor documentation:** SQLState, deadlock/serialization failure, transaction rollback, timeout và unique constraints.
- **Tài liệu SFTP/SSH server/client:** host-key verification, session recovery, file readiness và transfer errors.

**Kết luận:** Retry và backoff chỉ an toàn khi hệ thống hiểu **loại lỗi, ngữ nghĩa thao tác và trạng thái side effect**. Với Spring Integration Adapters, phải chọn đúng retry owner, giới hạn attempts/thời gian, dùng jitter và backpressure, bảo vệ idempotency, phân biệt ack/redelivery giữa các giao thức, đồng thời chuẩn bị DLQ, reconciliation, quan sát và runbook. Một luồng chỉ được xem là đủ điều kiện production khi **thử lại không tạo sai lệch nghiệp vụ và mọi thất bại đều có đường xử lý đã được kiểm thử**.




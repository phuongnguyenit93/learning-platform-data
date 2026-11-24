# Resilience khi hệ thống ngoài chậm trong Spring Integration Adapters

## 1. Bài toán và mục tiêu học tập

Trong hệ thống tích hợp, một đối tác HTTP có thể phản hồi sau 20 giây, máy chủ SFTP có thể mất kết nối, broker Kafka/JMS/AMQP có thể quá tải hoặc database đích có thể giữ lock lâu. Nếu inbound adapter vẫn tiếp tục nhận message không kiểm soát, các yêu cầu đang chờ sẽ chiếm thread, connection, bộ nhớ và kéo chậm toàn bộ ứng dụng.

**Resilience khi hệ thống ngoài chậm** là khả năng duy trì trạng thái an toàn, kiểm soát tải, phục hồi có giới hạn và bảo toàn dữ liệu khi một dependency phản hồi chậm hơn mức dự kiến. Resilience không có nghĩa “cứ retry đến khi được”, cũng không phải luôn làm thời gian phản hồi nhanh hơn; mục đích là cô lập sự cố để hệ thống còn đáp ứng các mục tiêu nghiệp vụ đã đặt.

Trong module `SPRING_INTEGRATION_ADAPTERS`, ta kết nối bên ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel` qua file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu. Bài học này trình bày cách kết hợp **timeout, backpressure, bounded concurrency, circuit breaker, bulkhead, retry, durable queue, idempotency và observability** mà không làm mất message hoặc gây duplicate side effect.

Sau bài học, người học có thể xác định nơi dependency chậm gây lan truyền áp lực, chọn cơ chế phù hợp từng transport, thiết kế flow phục hồi, và kiểm thử thực tế các trạng thái thành công, lỗi, timeout, kết quả không xác định.

## 2. Chậm khác lỗi ngay lập tức

| Tình huống | Điều quan sát được | Nguy cơ |
|---|---|---|
| HTTP trả 503 ngay | Lỗi rõ ràng | Retry storm nếu không giới hạn |
| HTTP giữ kết nối 30 giây | Thread/connection chờ | Cạn pool, request xếp hàng |
| SFTP đọc file vài MB rồi đứng | Đã có dữ liệu một phần | Session leak, file không hoàn chỉnh |
| Kafka broker trả ack trễ | Producer còn in-flight | Buffer đầy, timeout và gửi lặp |
| JMS/AMQP consumer xử lý lâu | Broker message chưa ack hoặc bị redeliver | Lag, duplicate, requeue liên tục |
| JDBC query giữ lock | DB connection chờ | Deadlock, nghẽn datasource |
| Đối tác xử lý xong nhưng response mất | Kết quả UNKNOWN | Retry có thể tạo tác dụng kép |

Một lời gọi không có exception **chưa chắc hoàn tất đúng SLA**. Cần tách **latency**, **availability**, **business acknowledgement** và **outcome ambiguity**. Một HTTP 202 chỉ chứng minh request được chấp nhận theo hợp đồng API, không chứng minh công việc cuối đã xong. Ngược lại, timeout không chứng minh server chưa xử lý.

## 3. Điểm áp lực trong message flow

~~~mermaid
flowchart LR
    A[Inbound adapter] --> B[MessageChannel]
    B --> C[Transform / validate]
    C --> D[Outbound gateway]
    D --> E[Slow external system]
    E -.-> F[Timeout / error / unknown]
    B -.-> G[Queue / executor capacity]
    D -.-> H[Thread and connection pools]
    G -.-> I[Backpressure and admission]
    H -.-> J[Bulkhead and timeout]
    F -.-> K[Retry / reconcile / DLQ]
~~~

Một flow `DirectChannel` đồng bộ thường giữ thread upstream trong lúc downstream handler thực thi. Khi outbound gateway chờ HTTP, poller hoặc listener có thể bị giữ lại — đôi lúc giúp giảm số request nguồn, nhưng cũng có thể khiến transaction/ack kéo dài. Với `ExecutorChannel` hay `QueueChannel`, áp lực được tách thành một bộ đệm: nếu queue không giới hạn, độ trễ biến thành **tăng bộ nhớ vô hạn**; nếu queue không bền vững, crash có thể làm mất công việc.

Câu hỏi cần trả lời cho **từng đoạn** của flow: tối đa bao nhiêu message in-flight, hàng đợi nằm ở đâu, dữ liệu có bền không, ai nhận tín hiệu đầy, và ai chịu trách nhiệm retry?

## 4. Thiết lập timeout theo ngân sách đầu cuối

Không có một giá trị timeout phù hợp cho mọi hệ thống. Cần phân định:
- **Connection timeout**: thời gian tối đa để thiết lập kết nối.
- **Read/response timeout**: thời gian chờ dữ liệu hoặc phản hồi.
- **Request deadline/total budget**: giới hạn tổng cho một attempt, gồm DNS, TLS, ghi body, chờ và đọc body nếu hạ tầng hỗ trợ.
- **Transaction timeout**: giới hạn thời gian giao dịch cục bộ; không nên dùng để thay cho network timeout.
- **Message processing deadline**: thời gian tối đa để đưa message sang trạng thái hoàn thành, retry hoặc escalation.

Ví dụ giả lập một nghiệp vụ có SLA 15 giây: kiểm tra/transform 200 ms, outbound budget 3 giây mỗi attempt, tối đa hai attempts cùng backoff và thời gian dự phòng. Không nên đặt ba lần retry với mỗi lần chờ 15 giây rồi báo SLA 15 giây. Timeout phải tương thích với thời hạn visibility/lease, consumer ack và request cancellation.

Khi request đã được gửi, **timeout có thể là UNKNOWN**, không phải chắc chắn FAILED. Trước khi gửi lại thao tác không idempotent, cần tra cứu theo business ID hoặc thực hiện biện pháp đối soát thích hợp.

## 5. Retry: chỉ thử lại khi có cơ sở

Retry hữu ích với lỗi tạm thời, như 429, 503, connection reset. Nhưng retry sai có thể khuếch đại outage của đối tác. Một chính sách phải xác định:
1. Lỗi nào retry được và lỗi nào không.
2. Số attempts tối đa, timeout từng attempt, tổng deadline.
3. Backoff tăng dần và jitter để tránh nhiều worker retry cùng lúc.
4. Idempotency key ổn định xuyên mọi attempt.
5. Trạng thái sau khi hết attempts: delayed queue, DLT/quarantine hoặc manual review.
6. Cách phân biệt remote đã xử lý nhưng client chưa biết.

~~~text
attempt #1: POST order-301 -> timeout, remote status UNKNOWN
  -> query remote by business ID
  -> if already applied: mark delivered
  -> if reliably absent: retry with same idempotency key
  -> if unknown: schedule reconciliation, not unbounded retry
~~~

Tránh retry các lỗi xác thực không thể tự hồi phục hoặc payload/schema hỏng. Tránh retry một giao dịch JDBC đã được đánh dấu rollback-only trong cùng transaction; mỗi attempt cần transaction scope phù hợp.

## 6. Circuit breaker và bulkhead

**Circuit breaker** giảm gọi tới dependency đang lỗi hoặc chậm kéo dài. Trạng thái logic thường gồm `CLOSED` (cho gọi), `OPEN` (fail fast) và `HALF_OPEN` (cho số request thử có giới hạn). Các ngưỡng lỗi/chậm phải được lựa chọn theo cửa sổ quan sát và lưu lượng thực tế.

**Bulkhead** giới hạn concurrency của từng dependency để một nhà cung cấp chậm không chiếm toàn bộ worker threads và connections dùng chung.

| Cơ chế | Khi nào cần | Không giải quyết một mình |
|---|---|---|
| Timeout | Một request treo quá lâu | Không thu hồi side effect remote |
| Circuit breaker | Dependency lỗi/chậm nhiều lần | Không lưu message bền vững |
| Bulkhead | Một dependency chiếm hết capacity | Không bảo đảm delivery |
| Rate limiter | Đích có quota | Không thay cơ chế retry/recovery |
| Bounded queue | Inbound nhanh hơn outbound | Không giải quyết crash nếu in-memory |
| Retry/backoff | Lỗi transient | Có thể nhân đôi thao tác |

Khi breaker mở, **công việc không được âm thầm biến mất**. Nếu nghiệp vụ bắt buộc xử lý, lưu lại ở durable queue/outbox và chỉ lấy ra khi recovery cho phép. Nếu yêu cầu tương tác tức thời, trả lỗi có cấu trúc như “đang quá tải” cho caller theo contract.

## 7. Backpressure, queue và giới hạn concurrency

Một ví dụ tốc độ: inbound 500 message/giây, outbound phục vụ 50 message/giây. Backlog tăng khoảng 450 message/giây nếu không giới hạn. Thêm executor không thể giúp vượt năng lực của dependency, còn queue không giới hạn chỉ trì hoãn thời điểm hệ thống cạn bộ nhớ.

Cần phối hợp:
- Giới hạn số worker/in-flight request theo từng target.
- Hàng đợi **bounded** hoặc persistent store với chính sách khi đầy.
- Giảm tốc poller, `maxMessagesPerPoll` và concurrency listener nếu nguồn hỗ trợ.
- Chọn `DirectChannel`, `QueueChannel`, `ExecutorChannel` và channel bền vững theo tính chất nguồn.
- Đặt giới hạn payload và thời gian lưu; theo dõi tuổi message cũ nhất.
- Điều chỉnh rate limit dựa trên throughput và quota đối tác.

Không giả định `ExecutorChannel` có backpressure an toàn chỉ vì nó bất đồng bộ. Cần hiểu queue của executor, rejection policy và cách propagate lỗi vào flow. Với `FluxMessageChannel` hoặc reactive publisher, tín hiệu demand chỉ có tác dụng ở các đoạn thực sự hỗ trợ Reactive Streams; đoạn gọi blocking adapter phải được kiểm soát riêng.

## 8. Durable handoff: không giữ transaction khi đợi dịch vụ chậm

Giả sử JDBC inbound poller mở transaction, cập nhật đơn rồi gọi HTTP gateway chậm trước khi commit:

~~~text
BEGIN JDBC TX -> claim order -> HTTP wait 25 seconds -> COMMIT
~~~

Trong suốt 25 giây, JDBC connection/lock có thể bị giữ, nhưng HTTP không tham gia transaction JDBC. Một kiến trúc bền vững hơn là **transactional outbox**:

~~~mermaid
flowchart TD
    A[Inbound message] --> T[Short JDBC transaction]
    T --> B[Business state update]
    T --> O[Insert outbox job]
    B --> C[Commit]
    O --> C
    C --> P[Worker claims job in short TX]
    P --> H[HTTP / SFTP / Kafka outbound outside claim TX]
    H --> D{Outcome}
    D -->|Accepted| M[Short TX: mark delivered]
    D -->|Unknown| R[Reconcile / retry scheduled]
    D -->|Permanent failure| X[Quarantine with owner]
~~~

Worker nên chia **claim–send–finalize**: claim công việc và commit, gọi mạng không giữ DB transaction, sau đó mở transaction ngắn để cập nhật kết quả. Nếu worker chết sau remote accepted nhưng trước finalize, job có thể gửi lại; phải dựa vào idempotency key và remote status query.

## 9. Thiết kế idempotency và trạng thái UNKNOWN

Mỗi thao tác nghiệp vụ cần định danh ổn định, ví dụ `shipment:create:order-301`, không tạo UUID mới cho mỗi lần retry của cùng một operation. Khi đích hỗ trợ idempotency key, cùng operation phải dùng lại key đó theo TTL/hợp đồng của đích.

Một state machine tham khảo:

~~~text
PENDING -> CLAIMED -> IN_FLIGHT
                    |        |
                    |        +-> ACCEPTED -> DELIVERED
                    |        +-> TIMEOUT  -> UNKNOWN
                    |        +-> REJECTED -> QUARANTINED
                    +-> LEASE_EXPIRED -> RETRY_ELIGIBLE
UNKNOWN -> remote query -> DELIVERED / RETRY_ELIGIBLE / MANUAL_REVIEW
~~~

`LEASE_EXPIRED` không có nghĩa request cũ đã kết thúc tại đối tác. Worker cũ và mới có thể chạy trùng; dùng phiên bản lease/fencing token và kiểm optimistic update khi finalize. Không thể dựa chỉ vào unique constraint ở DB nguồn để ngăn remote tạo hai lần.

## 10. Ví dụ Spring Integration Java DSL

Phần sau mô tả một luồng outbound đồng bộ có `RequestHandlerRetryAdvice` và cấu hình timeout ở HTTP client riêng. Tên bean và DSL phải được đối chiếu với phiên bản Spring Integration thực tế; đây là đoạn minh họa, không phải project biên dịch độc lập.

~~~java
@Bean
IntegrationFlow outboundFlow(
        MessageChannel outboundRequests,
        MessageHandler partnerHandler,
        RequestHandlerRetryAdvice boundedRetryAdvice) {

    return IntegrationFlow.from(outboundRequests)
        .handle(partnerHandler, endpoint ->
            endpoint.advice(boundedRetryAdvice))
        .get();
}
~~~

Retry advice dùng với handler thích hợp; khi gateway có semantics request–reply và cần reply, không được thay bừa bằng one-way handler. Việc cấu hình backoff và retryable exceptions phải thực hiện ở retry policy. Nếu handler bắt exception rồi trả về bình thường, retry advice không biết có lỗi; vì vậy phải xác định rõ exception propagation.

Một service-level wrapper thể hiện intent:

~~~java
public DeliveryResult sendWithPolicy(OutboundJob job) {
    if (!partnerCapacity.tryAcquire()) {
        return DeliveryResult.defer("bulkhead_full");
    }
    try {
        return partnerClient.send(
            job.payload(),
            job.idempotencyKey(),
            job.deadline()
        );
    } catch (OutcomeUnknownException ex) {
        return DeliveryResult.reconcile(job.id());
    } finally {
        partnerCapacity.release();
    }
}
~~~

Đây là pseudocode Java về contract; `partnerCapacity`, `partnerClient` và `DeliveryResult` là abstraction do ứng dụng cung cấp. Không thực hiện I/O network bên trong transaction JDBC đang giữ lock chỉ để ép “send thành công rồi mới commit”.

## 11. HTTP adapter: chậm, connection pooling và lỗi không rõ kết quả

Với outbound HTTP gateway:
1. Định nghĩa connect timeout, response timeout, pool acquisition timeout và toàn bộ request deadline theo HTTP client thực tế.
2. Không coi response `202 Accepted` là hoàn tất nghiệp vụ nếu hệ thống đích xử lý nền.
3. Giới hạn kết nối đồng thời đến một host; quản lý keep-alive, pool và idle eviction.
4. Retry 429/503 theo `Retry-After` khi phù hợp với contract.
5. Phân biệt lỗi trước khi gửi body và lỗi sau khi server có thể đã nhận.
6. Nếu dùng streaming request/response body, quản lý đóng resource và cancellation.
7. Bảo vệ credential, không log Authorization header hoặc toàn payload khi chẩn đoán.

Ví dụ API giao hàng phản hồi timeout ở client trong khi server tạo shipment. Nếu worker quay lại nhận cùng message từ JMS/Kafka, cần kiểm API theo business ID hoặc dùng cùng idempotency key. **Transaction rollback ở nguồn không hoàn tác POST đã thành công**.

## 12. SFTP và file adapter: chậm giữa luồng truyền

Với SFTP, một file có thể truyền được 80% rồi connection drop. Một thư mục đích có thể chứa partial file khiến đối tác đọc nhầm. Thiết kế nên xem xét:
- Upload dưới tên tạm, xác minh kích thước/checksum nếu contract yêu cầu, rồi rename khi hoàn chỉnh.
- Không coi `rename` là atomic trên mọi server/filesystem; kiểm semantics thực tế.
- Giới hạn số SFTP sessions và số file concurrent; không dùng pool vô hạn.
- Dùng stable file ID, checksum và remote readback trước khi retry.
- Quản lý local staging và recovery khi remote session bị đóng.
- Tránh giữ stream live đi qua `ExecutorChannel` nếu session lifecycle không bao phủ downstream.
- Có cảnh báo cho file quá tuổi hoặc retry vượt ngân sách.

File inbound poller có thể tiếp tục quan sát cùng file sau lỗi; persistent accept-once filter, metadata store và locking có semantics riêng, cần kiểm thử redelivery. File move/rename không tự rollback cùng JDBC transaction.

## 13. JMS, AMQP, Kafka: resilience theo broker

| Transport | Khi consumer/outbound chậm | Cách kiểm soát |
|---|---|---|
| JMS | Session chưa ack, listener throughput giảm | Container concurrency, ack/transaction, retry và DLQ |
| AMQP | Unacked deliveries tăng; requeue có thể lặp | Prefetch, consumer concurrency, nack/DLX/DLQ |
| Kafka | Consumer lag tăng; xử lý chậm dễ ảnh hưởng poll/rebalance | Tuning poll cadence, `max.poll.interval.ms`, concurrency, retry/DLT |
| JDBC | Connection/row locks bị giữ | Short transactions, pool/lock timeout, outbox |
| File/SFTP | File chờ trong nguồn hoặc session chờ lâu | Bounded polling, staging, retry/reconciliation |

Với Kafka, `max.poll.interval.ms` bị vượt có thể khiến consumer bị coi là không tiến triển và gây rebalance theo cấu hình. Không dùng callback xử lý chậm vô hạn trong listener thread rồi giả định offset sẽ an toàn. Nếu chuyển sang worker async, phải bảo đảm nhiệm vụ đã lưu bền trước khi source offset được commit.

Với JMS/AMQP, ack nguồn sau khi chỉ enqueue một task vào memory executor có nguy cơ mất message khi crash. Nếu broker redeliver sau remote accepted, phải có idempotency. Dead-letter không đồng nghĩa xử lý xong: cần alert, owner và quy trình replay.

## 14. Chọn cách xử lý khi dependency không sẵn sàng

Ba hướng chính:
- **Fail fast:** phù hợp request tương tác không thể đáp ứng đúng SLA; trả tín hiệu retryable rõ ràng.
- **Defer:** ghi công việc vào persistent queue/outbox, trả acknowledgement rằng đã *tiếp nhận* chứ không nói đã xử lý cuối.
- **Degrade:** dùng tính năng thay thế hoặc dữ liệu cache nếu business cho phép, nêu rõ độ mới và hạn chế.

Ví dụ một API nhận yêu cầu xuất báo cáo: khi SFTP đối tác chậm, API có thể trả job ID và trạng thái `ACCEPTED`; worker tiếp tục theo dõi, thay vì giữ HTTP caller mở tới khi upload kết thúc. Với thanh toán hoặc cấp quyền nhạy cảm, không được degrade bằng cách bỏ qua bước kiểm soát nghiệp vụ.

Khi retry queue đầy hoặc bị cô lập, cần chính sách admission: từ chối yêu cầu mới hoặc tạm dừng nguồn, không nhận vô hạn rồi mất dữ liệu.

## 15. Observability và SLO

Theo dõi cả độ trễ và sự tích tụ công việc:
- `remote_call_latency` (p50/p95/p99), timeout rate, error rate theo dependency.
- `in_flight_requests`, thread pool active/queue/rejected, HTTP connection pool pending.
- `circuit_breaker_state`, bulkhead rejections, retry attempt count.
- `inbound_rate`, `outbound_success_rate`, queue depth và **oldest message age**.
- JMS/AMQP unacked/redelivery/DLQ counts; Kafka consumer lag/rebalance.
- JDBC transaction duration, connection pool wait và lock wait.
- Tỷ lệ `UNKNOWN`, reconciliation backlog, duplicate suppressed, time-to-business-completion.

SLO không chỉ là uptime của process. Ví dụ “99% job được xác nhận trong 5 phút” cần đo từ khi tiếp nhận đến khi có outcome business. Một queue tăng liên tục trong khi HTTP server trả 200 không phải tín hiệu hệ thống khỏe. Tracing nên dùng `correlationId`, `businessId`, attempt number và target, nhưng không lấy businessId làm metric label có cardinality cao.

## 16. Ma trận kiểm thử sức chịu lỗi

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| RL01 | HTTP response trễ hơn timeout | Không giữ thread vô hạn; outcome UNKNOWN đúng |
| RL02 | HTTP 503 ngay | Retry bounded với backoff, không storm |
| RL03 | HTTP remote thành công nhưng response mất | Không tạo duplicate khi retry |
| RL04 | Circuit breaker OPEN | Không gửi request mới; durable job còn nguyên |
| RL05 | Bulkhead full | Từ chối/defer có kiểm soát, không OOM |
| RL06 | Outbound 10 msg/s, inbound 100 msg/s | Queue bounded và cơ chế giảm tải |
| RL07 | Worker crash sau DB commit trước outbound | Outbox phục hồi job |
| RL08 | Worker crash sau remote accepted trước finalize | Replay idempotent |
| RL09 | Lease expire khi request cũ còn chạy | Stale worker không ghi đè state mới |
| RL10 | SFTP drop giữa upload | Không cho đối tác thấy file complete giả |
| RL11 | JMS/AMQP redelivery | Business effect không nhân đôi |
| RL12 | Kafka listener bị xử lý chậm | Phát hiện lag/rebalance và recovery |
| RL13 | `ExecutorChannel` memory bị mất khi crash | Test chứng minh rủi ro, thay bằng durable handoff |
| RL14 | JDBC lock wait kéo dài | Timeout/short transaction giúp cô lập |
| RL15 | Payload không hợp lệ | Không retry vô hạn, quarantine đúng |
| RL16 | Retry queue đầy | Admission policy rõ và evidence đủ |

Để xác minh, test phải quan sát trạng thái nguồn/đích, timeout thực tế, queue, số lần gửi và tài nguyên đang mở. Unit test chỉ verify mock gọi một lần không đủ cho kết luận resilience.

## 17. Bài thực hành: đơn hàng qua HTTP và SFTP

Thiết kế flow:

~~~text
JDBC inbound / HTTP request
   -> validate
   -> short JDBC transaction: business state + outbox job
   -> outbox worker with concurrency limit
   -> HTTP shipment gateway
   -> SFTP document upload (if required)
   -> finalize or retry/reconcile
~~~

Yêu cầu:
1. Tạo HTTP test server giả lập trễ, 429, 503 và timeout sau khi lưu đơn.
2. Đặt connect/response deadline, retry budget và circuit breaker theo một SLO tự chọn, giải thích cách chọn.
3. Triển khai outbox claim–send–finalize để không giữ JDBC transaction trong lúc chờ mạng.
4. Giới hạn concurrency/queue, gây tải inbound cao hơn outbound và đo oldest message age.
5. SFTP upload bằng tên tạm; gây lỗi giữa chừng rồi kiểm remote state.
6. Giả lập crash sau khi remote đã nhận nhưng trước finalize; bảo đảm idempotency.
7. Bổ sung alert khi breaker mở, retry queue tăng, oldest job vượt SLA hoặc số UNKNOWN tăng.
8. Nộp báo cáo `caseId, dependency, remoteLatencyMs, attempt, sourceState, targetState, queueAgeMs, expected, observed, evidence`.

## 18. Checklist review thiết kế

1. Mỗi dependency có connect/read/request timeout hữu hạn và ngân sách đầu cuối?
2. Có xác định acknowledgement nghĩa là nhận request hay hoàn tất nghiệp vụ?
3. Có giới hạn workers, connections và in-flight message theo target?
4. Queue là bounded, bền vững và có chiến lược khi đầy?
5. Circuit breaker và bulkhead có ngăn dependency chậm gây lan truyền lỗi?
6. Retry có giới hạn, backoff/jitter, phân loại lỗi và dùng stable idempotency key?
7. Trạng thái UNKNOWN được đối soát thay vì mặc định retry ngay?
8. JDBC transaction có kết thúc trước lời gọi HTTP/SFTP chậm?
9. Khi broker redeliver, consumer có dedup và DLQ/quarantine?
10. Có test các cửa sổ crash sau source commit và trước khi finalize?
11. Có runbook replay, escalation, cleanup tài nguyên và dashboard theo SLO?
12. Có tránh log secret, payload nhạy cảm, hoặc mở connection không kiểm soát?

**Kết luận:** Resilience khi hệ thống ngoài chậm cần được xây dựng **theo ranh giới từng adapter và transport**. Timeout ngăn chờ vô hạn, bulkhead/circuit breaker bảo vệ tài nguyên, backpressure giới hạn công việc, còn outbox/idempotency/reconciliation bảo vệ kết quả nghiệp vụ khi gửi lặp hoặc mất phản hồi. Một flow được xem là chịu lỗi tốt khi sự cố của đối tác không làm sụp toàn hệ thống và mọi message đều có trạng thái xử lý, phục hồi hoặc escalation có thể kiểm chứng.

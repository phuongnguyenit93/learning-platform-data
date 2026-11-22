# Xử lý retry sau khi handler thất bại

## 1. Bài toán: đã đánh dấu message rồi handler mới ném exception

Một dịch vụ nhận `PaymentEvent` từ broker, dùng **Idempotent Receiver** để không ghi nhận cùng một thanh toán hai lần. Luồng ban đầu:

~~~text
Broker message EV-901
  → Idempotent Receiver: kiểm tra eventId
  → Ghi marker "EV-901 đã thấy"
  → PaymentHandler: ghi sổ cái
  → Publish kết quả
  → ACK message
~~~

Giả sử handler ném exception **sau khi marker đã được lưu** nhưng **trước khi nghiệp vụ commit**:

~~~text
T1  Broker gửi EV-901 lần đầu.
T2  Dedupe check: EV-901 chưa có → ghi "seen".
T3  Handler gọi database → lỗi, transaction nghiệp vụ rollback.
T4  RetryAdvice hoặc broker gửi lại EV-901.
T5  Dedupe check: EV-901 đã có → coi là duplicate.
T6  Handler có thể không được gọi lại: công việc mất dù chưa hoàn tất.
~~~

Đây là lỗi **poisoned idempotency marker**: dấu vết “đã được nhìn thấy” bị nhầm với “đã xử lý thành công”. Ở chiều ngược lại, nếu handler **đã commit nhưng process crash trước ACK**, broker cũng sẽ phát lại; không có bảo vệ thì side effect bị thực thi lần hai.

~~~mermaid
flowchart TD
    IN["Message đến / retry"] --> CHECK{"Key đã có?"}
    CHECK -->|"Chưa"| MARK["Ghi marker SEEN"]
    MARK --> WORK["Handler"]
    WORK -->|"Lỗi trước commit"| FAIL["Exception / retry"]
    FAIL --> CHECK
    CHECK -->|"Có"| DROP["Duplicate: có thể bị bỏ qua"]
    DROP --> LOST["Nguy cơ mất xử lý"]
    WORK -->|"Commit"| DONE["Business completed"]
~~~

**Câu hỏi quan trọng:** marker có đại diện cho **nhận message**, **quyền xử lý tạm thời**, hay **nghiệp vụ đã commit**? Không xác định đúng ngữ nghĩa này thì tăng số lần retry vẫn có thể làm hệ thống sai.

Bài thuộc chương **Idempotent receiver** của module **SPRING_INTEGRATION_PATTERN**, trong lộ trình triển khai Enterprise Integration Patterns bằng Spring Integration: Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, cùng việc kiểm thử và theo dõi các nhánh xử lý.

Sau bài, bạn sẽ phân biệt các failure windows; giải thích tương tác `IdempotentReceiverInterceptor` và `RequestHandlerRetryAdvice`; dùng transaction/inbox/outbox hoặc lease/fencing khi cần; và kiểm thử retry sau handler thất bại, broker redelivery và external side effects.

## 2. Idempotent Receiver, deduplication và retry không đồng nghĩa

**Idempotent Receiver** là mục tiêu: nhiều lần tiếp nhận **cùng một logical operation** không tạo hiệu ứng nghiệp vụ lặp ngoài ý định. Không bắt buộc handler chỉ được gọi đúng một lần.

\[
\operatorname{effect}(\operatorname{handle}(m),\operatorname{handle}(m))
=\operatorname{effect}(\operatorname{handle}(m))
\]

| Khái niệm | Đảm nhiệm | Không tự bảo đảm |
|---|---|---|
| Idempotent Receiver | Nhận lại message mà không tạo side effect sai | Không tự biến broker thành exactly-once |
| Dedupe selector | Xác định key đã từng được ghi hay chưa | Không chứng minh lần trước đã thành công |
| Retry | Thử lại khi lỗi có thể phục hồi | Không biết remote side effect đã xảy ra hay chưa |
| Transaction | Atomic commit/rollback trong phạm vi transaction manager | Không tự rollback HTTP hoặc broker khác |
| Inbox/processed record | Lưu durable state đã tiếp nhận/xử lý | Cần state semantics và uniqueness chính xác |
| Outbox | Lưu durable intent publish cùng business commit | Publisher vẫn có thể phát trùng |
| Broker ACK | Xác nhận theo semantics của transport | Không đồng nghĩa business commit |

**Phát hiện duplicate chỉ là một bước.** Quyết định **chặn, trả kết quả cũ, đợi, retry hay quarantine** phụ thuộc vào trạng thái thật của operation cũ.

## 3. Bốn cửa sổ lỗi

~~~text
Receive → Claim/Dedupe → Business handler → Commit → ACK
~~~

| Lỗi ở đâu? | Business side effect | Hành vi khi message về lại |
|---|---|---|
| Trước claim | Chưa xảy ra | Được xử lý lại |
| Sau claim nhưng trước business commit | Chưa hoặc không chắc | Không được chặn retry hợp lệ bằng marker “seen” |
| Sau commit nhưng trước ACK | Đã xảy ra | Phải tránh side effect lần hai |
| Trong external API call và response mất | **Không biết** remote đã commit chưa | Reconcile hoặc dùng cùng remote idempotency key |

**Exception không chứng minh toàn bộ side effect đã rollback.** HTTP server có thể commit payment dù client gặp timeout; message producer có thể gửi thành công dù chưa nhận được broker ACK.

Thứ tự giữa marker, business transaction, publish và acknowledgment quyết định độ an toàn của cả flow.

## 4. Chọn khóa idempotency theo logical operation

Không dùng `MessageHeaders.ID` làm khóa nghiệp vụ dài hạn nếu broker/Transformer có thể tái tạo Spring Message với ID mới. Cũng không dùng `attemptId` hoặc thời điểm hiện tại để định danh cùng logical work.

Ví dụ:

~~~text
key = (tenantId, paymentId, operation, revision)
~~~

Hoặc dùng `eventId` duy nhất, ổn định qua các retries **nếu contract bảo đảm một event chỉ biểu diễn một operation**.

| Field | Vai trò |
|---|---|
| `tenantId` | Tách tenant và quyền |
| `eventId` | Định danh event bền vững từ producer |
| `paymentId` | Đối tượng business |
| `operation` | CAPTURE, REFUND, CANCEL có side effects khác nhau |
| `revision` | Lượt xử lý mới hợp lệ nếu cần |
| `attemptId` | Quan sát lần thử, không đưa vào logical key |
| `MessageHeaders.ID` | ID message instance, không phải business identity |

Ví dụ hai operation `CAPTURE` và `REFUND` trên cùng payment **không được ghép chung** chỉ vì có chung `paymentId`.

Key là một **định danh, không phải authorization**. Tenant phải được xác minh từ identity đáng tin ở ingress, không chỉ từ một header do client tự khai.

## 5. “Đã thấy” khác “đã thành công”

Một Boolean đơn giản:

~~~text
processedEvents.contains("EV-901") == true
~~~

không nói rõ operation đang:

- được một worker xử lý;
- thất bại trước commit;
- đã commit sổ cái;
- gửi remote call nhưng chưa biết outcome;
- hoặc đã publish kết quả.

Mô hình trạng thái rõ hơn:

| State | Ý nghĩa | Lần retry cùng key |
|---|---|---|
| `NEW` | Chưa có record | Claim và xử lý |
| `PROCESSING` | Một worker đang sở hữu lease | Defer/chờ, không chạy song song |
| `SUCCEEDED` | Business outcome đã commit | Không lặp side effect; trả kết quả cũ nếu cần |
| `FAILED_RETRYABLE` | Chưa thành công, có thể thử lại | Retry bounded |
| `FAILED_PERMANENT` | Không được xử lý lại tự động | Reject/quarantine hoặc trả failure |
| `UNKNOWN_OUTCOME` | Side effect bên ngoài có thể đã xảy ra | Reconcile trước retry mù |

Với **marker và side effect cùng một database transaction**, có thể chỉ cần lưu **record đã hoàn tất** khi commit. Với remote service và worker nhiều node, state machine thường cần thiết hơn.

## 6. Sơ đồ quyết định khi nhận duplicate

~~~mermaid
flowchart TD
    IN["Receive message"] --> V{"Validate key, tenant, payload"}
    V -->|"Sai"| Q["Reject / quarantine"]
    V -->|"Đúng"| S{"Operation state?"}
    S -->|"NEW / retryable"| C["Atomic claim"]
    S -->|"PROCESSING còn lease"| WAIT["Defer; tránh concurrency"]
    S -->|"SUCCEEDED"| ACK["ACK / trả cached outcome"]
    S -->|"FAILED_PERMANENT"| TERM["Terminal failure"]
    S -->|"UNKNOWN_OUTCOME"| REC["Reconciliation"]
    C --> H["Handler"]
    H -->|"Commit thành công"| DONE["SUCCEEDED"]
    H -->|"Transient failure"| RETRY["Rollback / retryable state"]
    H -->|"Unknown remote result"| REC
    DONE --> ACK
    RETRY --> C
~~~

Một duplicate `SUCCEEDED` và một duplicate `PROCESSING` **không nên có cùng hành vi**. Bản đầu có thể ACK an toàn; bản sau cần đợi/defer hoặc một thuật toán lease/recovery, không được trả kết quả thành công giả.

## 7. Phương án ưu tiên khi có thể: một database transaction

Nếu **marker, business mutation và outbox record** đều dùng **cùng một database và transaction manager**, xử lý:

~~~text
BEGIN TRANSACTION
  INSERT idempotency key nếu chưa tồn tại
  IF duplicate:
      xác minh payload fingerprint
      không chạy side effect
  ELSE:
      cập nhật sổ cái / domain tables
      ghi outbox event
COMMIT TRANSACTION
~~~

Khi handler ném exception **trước commit**, rollback **cả marker lẫn business mutation**. Lần retry sau đó có thể claim lại. Khi business commit **trước ACK**, marker committed giúp phát hiện redelivery.

**Điều kiện:** tất cả các thao tác phải thực sự tham gia cùng transaction. `@Transactional` trên JDBC handler **không rollback được một Redis marker độc lập** hoặc remote HTTP POST.

## 8. SQL minh họa: inbox, ledger và outbox

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE processed_event (
    tenant_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    operation VARCHAR(40) NOT NULL,
    payload_fingerprint VARCHAR(128) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, event_id, operation)
);

CREATE TABLE payment_ledger (
    ledger_entry_id UUID PRIMARY KEY,
    tenant_id VARCHAR(48) NOT NULL,
    payment_id VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    amount_minor BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, payment_id, event_id)
);

CREATE TABLE outbox_event (
    outbox_id UUID PRIMARY KEY,
    tenant_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    payload_json JSONB NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Schema này chỉ minh họa; production phải xác định currency, bản chất debit/credit, key của refund, quyền và retention theo domain. Uniqueness ở `processed_event` ngăn cùng event claim hai lần; uniqueness ở `payment_ledger` là lớp bảo vệ cho business side effect. Outbox giúp không mất **ý định publish** khi process crash.

## 9. Handler Java transaction với marker cùng database

Model Java 17+:

~~~java
record PaymentEvent(
    String tenantId,
    String eventId,
    String paymentId,
    String operation,
    long amountMinor,
    String payloadFingerprint
) {}

enum ReceiveOutcome { PROCESSED, DUPLICATE }
~~~

Service:

~~~java
@Service
class PaymentReceiver {
    private final ProcessedEventRepository inbox;
    private final PaymentLedgerRepository ledger;
    private final OutboxRepository outbox;

    PaymentReceiver(ProcessedEventRepository inbox,
                    PaymentLedgerRepository ledger,
                    OutboxRepository outbox) {
        this.inbox = inbox;
        this.ledger = ledger;
        this.outbox = outbox;
    }

    @Transactional
    public ReceiveOutcome process(PaymentEvent event) {
        validateAndAuthorize(event);

        // INSERT ... ON CONFLICT DO NOTHING trong cùng transaction.
        boolean inserted = inbox.insertIfAbsent(
            event.tenantId(), event.eventId(),
            event.operation(), event.payloadFingerprint());

        if (!inserted) {
            inbox.assertSameFingerprint(
                event.tenantId(), event.eventId(),
                event.operation(), event.payloadFingerprint());
            return ReceiveOutcome.DUPLICATE;
        }

        ledger.applyEventOnce(event);
        outbox.recordPaymentProcessed(event);
        return ReceiveOutcome.PROCESSED;
    }

    private void validateAndAuthorize(PaymentEvent event) {
        // Triển khai schema/domain validation + tenant authorization.
    }
}
~~~

Các repository ở đây là **abstraction do ứng dụng triển khai**, không phải type mặc định của Spring Integration. `insertIfAbsent` dùng unique key database, ví dụ `INSERT ... ON CONFLICT DO NOTHING` trong PostgreSQL. Cần bảo đảm các repository **thực sự dùng cùng transaction manager**.

**Spring proxy:** `@Transactional` có hiệu lực khi gọi qua bean được Spring quản lý; tự gọi `this.process(event)` có thể bỏ qua proxy. Không catch exception rồi return success khi domain failed, vì điều đó có thể làm transaction commit marker sai. Nếu nghiệp vụ phải catch, cần chủ động xác định rollback policy.

## 10. Gắn handler vào Spring Integration Java DSL

~~~java
@Configuration
@EnableIntegration
class PaymentFlow {

    @Bean
    IntegrationFlow paymentFlow(PaymentReceiver receiver) {
        return IntegrationFlow.from("payments.in")
            .handle(PaymentEvent.class,
                (event, headers) -> receiver.process(event))
            .channel("payments.outcomes")
            .get();
    }
}
~~~

Đây là ví dụ flow, import lược bỏ. `PaymentReceiver` là Spring bean có proxy transaction; `payments.outcomes` cần consumer thực hoặc test channel.

**Không bắt buộc gắn IdempotentReceiverInterceptor khi handler đã có transactional inbox.** Nếu đặt thêm một interceptor ghi Redis “seen” **trước** receiver thì chính interceptor có thể chặn retry mà SQL transaction chưa kịp hoàn tất.

## 11. Sequence diagram: rollback trước commit

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant H as Handler
    participant DB as Database
    B->>H: EV-901 attempt 1
    H->>DB: BEGIN + insert marker
    H->>DB: Update ledger
    Note over H: Transient exception
    H->>DB: ROLLBACK marker + ledger + outbox
    B->>H: EV-901 redelivery
    H->>DB: BEGIN + insert marker
    H->>DB: Update ledger + outbox
    H->>DB: COMMIT
    H-->>B: ACK theo policy
~~~

Marker không tồn tại sau rollback, nên lần retry có thể thực thi lại. Muốn hành vi này đúng, rollback phải áp dụng cả **marker** và **mutation**, không chỉ một trong hai.

## 12. Sequence diagram: commit trước ACK

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant H as Handler
    participant DB as Database
    B->>H: EV-902 attempt 1
    H->>DB: INSERT marker + ledger + outbox
    H->>DB: COMMIT
    Note over H: Crash trước broker ACK
    B->>H: EV-902 redelivery
    H->>DB: INSERT ... ON CONFLICT DO NOTHING
    DB-->>H: Duplicate + fingerprint giống
    H-->>B: ACK, không ghi ledger lần hai
~~~

Đây là cách xử lý **at-least-once delivery** với business effect **effectively-once trong phạm vi database**. Không gọi đó là global exactly-once khi các dịch vụ bên ngoài chưa có idempotency tương ứng.

## 13. Cùng key nhưng payload khác phải được coi là conflict

~~~text
Attempt 1: EV-901, amount=10000, fingerprint=F1
Attempt 2: EV-901, amount=99000, fingerprint=F2
~~~

Nếu `eventId` giống nhưng nội dung khác, đó có thể là producer bug, replay khác revision hoặc dữ liệu bị sửa. Không tự xem là duplicate thành công.

Quy trình:

1. Đọc fingerprint/schema version lưu cùng key.
2. So sánh với fingerprint **canonical payload** hiện tại.
3. Trùng → trả `DUPLICATE`/cached outcome.
4. Khác → `IDEMPOTENCY_KEY_CONFLICT`, reject/quarantine và audit.

Không dùng `Object.hashCode()` của Java làm payload fingerprint bền vững xuyên restart/process. Với hash cryptographic, phải chuẩn hóa thứ tự field, kiểu số và phiên bản schema; tránh đưa thông tin nhạy cảm thô vào log.

## 14. IdempotentReceiverInterceptor: phát hiện duplicate trước handler

Spring Integration cung cấp `IdempotentReceiverInterceptor`, một request-handler advice dựa trên `MessageSelector`, thường kết hợp `MetadataStoreSelector` và `ConcurrentMetadataStore` để nhận biết key đã thấy.

Ví dụ cách cấu hình định hướng:

~~~java
@Bean
IdempotentReceiverInterceptor idempotentAdvice(
        ConcurrentMetadataStore store) {
    MetadataStoreSelector selector = new MetadataStoreSelector(
        message -> {
            PaymentEvent event =
                (PaymentEvent) message.getPayload();
            return event.tenantId() + ":" + event.eventId()
                + ":" + event.operation();
        },
        store);
    return new IdempotentReceiverInterceptor(selector);
}
~~~

Đây là ví dụ minh họa API; xác minh constructor và strategy signatures theo phiên bản Spring Integration thực tế. Key cần có delimiter/validation không nhập nhằng như domain contract, không nối trực tiếp chuỗi tùy ý từ client.

**Điểm nguy hiểm:** một selector kiểu **accept-once** có thể lưu key **ngay khi message được chấp nhận**, **trước lúc handler hoàn tất**. Nếu metadata store độc lập với business transaction, marker vẫn còn sau handler exception và retry có thể bị đánh dấu duplicate.

Hành vi với duplicate phụ thuộc cấu hình interceptor: có thể đánh dấu bằng header duplicate, chuyển discard channel, hoặc ném lỗi theo tùy chọn. **Không mặc định duplicate chắc chắn bị drop hoặc handler chắc chắn không chạy.** Test trực tiếp trạng thái duplicate, handler invocation, reply và ACK.

## 15. Redis metadata store + PostgreSQL transaction: failure window điển hình

~~~text
Redis: putIfAbsent("EV-901", "seen") → success
PostgreSQL: BEGIN + update ledger → exception → ROLLBACK
Retry EV-901:
Redis: putIfAbsent("EV-901", "seen") → exists
→ message có thể không được handler xử lý lại
~~~

Rollback PostgreSQL **không tự xóa** Redis key. TTL chỉ khiến key biến mất sau thời gian, không chứng minh handler đã thành công.

**Không xóa marker bằng lệnh `DEL key` vô điều kiện sau exception**: một worker khác có thể đã claim lại key hoặc remote side effect đã commit. Nếu cần release claim, phải dùng lease/version và compare-and-set theo owner token, hoặc đặt marker trong transaction phù hợp.

Các hướng khắc phục:

- Đưa marker và business side effect vào **cùng DB transaction**.
- Hoặc dùng **inbox có state, lease và fencing**.
- Nếu liên quan external API, dùng **remote idempotency key và reconciliation**.

## 16. Retry Advice nằm ngoài hay trong Idempotent Advice?

Hai cách sắp thứ tự khái niệm:

~~~text
A. RetryAdvice( IdempotentAdvice( Handler ) )

B. IdempotentAdvice( RetryAdvice( Handler ) )
~~~

**A:** mỗi attempt do RetryAdvice khởi tạo có thể đi qua IdempotentAdvice. Nếu attempt đầu đã lưu “seen”, attempt thứ hai có thể gặp duplicate trước handler.

**B:** IdempotentAdvice chạy một lần trước vòng retry nội bộ. Retry của handler có thể đi tiếp, nhưng **sau khi hết attempts**, marker vẫn có thể tồn tại và **broker redelivery ở vòng ngoài** gặp duplicate.

**Thay thứ tự advice không giải quyết cốt lõi** nếu marker đã lưu trước business commit mà không được rollback/đổi state. Cần kiểm thử thứ tự lời gọi, exception/recovery behavior và state backend thật, không chỉ nhìn bean names.

## 17. RequestHandlerRetryAdvice: retry có ngân sách, không vô hạn

Spring Integration có `RequestHandlerRetryAdvice` để gắn retry cho handler. Ví dụ RetryTemplate:

~~~java
@Bean
RequestHandlerRetryAdvice handlerRetryAdvice() {
    RetryTemplate template = new RetryTemplate();
    template.setRetryPolicy(new SimpleRetryPolicy(3));

    FixedBackOffPolicy backoff = new FixedBackOffPolicy();
    backoff.setBackOffPeriod(200);
    template.setBackOffPolicy(backoff);

    RequestHandlerRetryAdvice advice =
        new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    return advice;
}
~~~

`SimpleRetryPolicy(3)` ở đây hướng tới **tổng ba attempts**, không phải ba retries thêm. Đây là code giải thích cơ chế; production phải phân loại exception, deadline, recovery callback, jitter/backoff và vị trí advice trong flow.

**RetryAdvice chỉ bắt exception trong phạm vi advice.** Nếu handler đã đưa task sang `ExecutorChannel`/broker rồi trả về, exception xảy ra sau đó thuộc error boundary khác; advice quanh publisher không tự retry lỗi của consumer.

## 18. Lỗi nào cần retry, lỗi nào cần terminal outcome?

| Lỗi | Chính sách hợp lý |
|---|---|
| DB deadlock, connection tạm mất | Retry bounded, transaction mới |
| HTTP 503/429 có hợp đồng retry | Backoff và quota, tôn trọng deadline |
| HTTP timeout, remote outcome không rõ | Reconcile hoặc retry cùng remote key |
| Invalid schema/payment amount | Reject/quarantine, không retry vô hạn |
| Tenant unauthorized | Security failure, không retry như lỗi mạng |
| Cùng idempotency key nhưng payload khác | Conflict, không tiếp tục xử lý |
| Duplicate đã SUCCEEDED | Không lặp side effect, ACK/cached reply |
| PROCESSING còn lease | Defer/requeue có kiểm soát |
| Permanent business rejection | Lưu terminal failure và trả outcome |

Retry vô hạn cho lỗi permanent có thể tạo **retry storm** và giữ inbox ở trạng thái chờ không bao giờ kết thúc. Cần phân biệt **failure outcome có cấu trúc** với exception mất reply.

## 19. External HTTP call: transaction database không bao trùm side effect bên ngoài

Một handler thực hiện:

~~~text
BEGIN local DB transaction
  INSERT inbox marker
  POST /payments/capture tới provider
  UPDATE payment state
COMMIT local DB
~~~

Nếu remote provider **đã capture** nhưng kết nối bị ngắt trước khi client nhận response, local transaction có thể rollback trong khi tiền **đã được capture**. Retry bằng một remote operation ID mới có thể capture lần hai.

**Rollback JDBC không rollback một HTTP request đã commit**. Khi side effect ở ngoài transaction local:

1. Ghi một **durable operation intent** với logical idempotency key.
2. Dùng **cùng remote idempotency key** qua retries khi provider hỗ trợ.
3. Nếu response mất, query trạng thái remote theo operation ID/key.
4. Chỉ đánh dấu `SUCCEEDED` sau khi outcome đã xác minh.
5. Nếu outcome không xác định và remote không có idempotency/query, **đừng retry POST mù**; đưa vào reconciliation/manual review.
6. Dùng compensation/correction khi domain cho phép, không giả định có thể đảo ngược mọi external side effect.

Ví dụ timeout ở HTTP client chỉ có nghĩa **client chưa nhận được kết quả**, không chứng minh remote server chưa làm gì.

## 20. State machine khi không thể dùng một atomic transaction

Một inbox record bền vững có thể chứa:

~~~text
logical_key
tenant_id
payload_fingerprint
state: NEW | PROCESSING | SUCCEEDED | FAILED_RETRYABLE
     | FAILED_PERMANENT | UNKNOWN_OUTCOME
attempt_count
lease_owner
lease_until
fencing_version
remote_operation_id
result_reference
updated_at
~~~

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PROCESSING: claim + lease
    PROCESSING --> SUCCEEDED: verified commit
    PROCESSING --> FAILED_RETRYABLE: safe transient failure
    PROCESSING --> UNKNOWN_OUTCOME: remote result unknown
    PROCESSING --> FAILED_PERMANENT: nonretryable error
    FAILED_RETRYABLE --> PROCESSING: bounded retry
    UNKNOWN_OUTCOME --> PROCESSING: reconciled, safe retry
    SUCCEEDED --> [*]
    FAILED_PERMANENT --> [*]
~~~

Mọi transition quan trọng phải atomic hoặc có điều kiện. Một claim `PROCESSING` không đồng nghĩa đã hoàn tất. Khi state tồn tại và chưa hết lease, bản duplicate cần **chờ/defer**, không tự chạy song song và cũng không ACK như một success nếu chưa có durable responsibility.

## 21. Lease và fencing: khi worker chết hoặc chạy quá lâu

Hai worker có thể nhận cùng message:

~~~text
W1: claim EV-901 token=8 → PROCESSING
W2: thấy PROCESSING token=8 → defer

W1 pause lâu, lease hết hạn.
W2: reclaim token=9 → xử lý.
W1 tỉnh dậy: cố mark SUCCEEDED bằng token=8.
Store phải từ chối W1.
~~~

Một update có điều kiện:

~~~sql
UPDATE inbox_operation
SET state = 'SUCCEEDED',
    updated_at = NOW()
WHERE logical_key = :key
  AND state = 'PROCESSING'
  AND fencing_version = :expected_token;
~~~

Nếu affected rows bằng 0, worker đã mất quyền hoàn tất. Không cập nhật state chỉ dựa vào `logical_key` mà không kiểm tra owner/version.

**Fencing local không chặn remote side effect**: worker cũ vẫn có thể gửi HTTP request sau khi lease hết. External system cũng cần cùng idempotency key hoặc khả năng kiểm soát version/fencing để tránh double side effect.

Lease TTL **không phải lệnh hủy worker**. Phải đo lock age, renewal, reclaim và xử lý lỗi khi hai worker đang chạy cùng lúc.

## 22. Xử lý `UNKNOWN_OUTCOME` sau timeout

~~~text
POST /capture key=CAPTURE-901
  → Provider đã commit.
  → Network rớt trước HTTP response.
  → Client ném timeout.
~~~

Không nên chuyển ngay thành `FAILED_RETRYABLE` rồi gửi một yêu cầu capture mới với key khác. Một state riêng `UNKNOWN_OUTCOME` giúp workflow **reconcile**.

| Provider hỗ trợ | Cách xử lý |
|---|---|
| Idempotency key có hợp đồng ổn định | Retry **cùng key** trong cửa sổ provider cam kết |
| Query operation/status API | Tra cứu trạng thái, ghi outcome local sau khi xác minh |
| Event webhook có operation ID | Chờ callback đúng correlation, có deadline/reconciliation |
| Không có idempotency hay query | Escalate/manual review, tránh retry side effect nguy hiểm |

Phải giữ payload fingerprint: cùng key nhưng amount/currency khác không được coi là retry vô hại.

## 23. Transactional Outbox: không mất kết quả khi crash trước publish

Một lỗi nữa:

~~~text
Ledger COMMIT thành công.
Process crash trước khi publish PaymentProcessed.
Broker redelivery được dedupe vì event đã SUCCEEDED.
Downstream không bao giờ nhận event kết quả.
~~~

**Transactional Outbox** lưu ý định publish cùng transaction với ledger và inbox:

~~~mermaid
flowchart LR
    I["Incoming event"] --> TX["Database transaction"]
    TX --> P["processed_event"]
    TX --> L["payment_ledger"]
    TX --> O["outbox_event"]
    O --> PUB["Outbox publisher"]
    PUB --> BROKER["Broker"]
    BROKER --> C["Idempotent downstream consumer"]
~~~

Outbox publisher đọc record chưa phát, gửi rồi đánh dấu trạng thái. Nếu publisher crash **sau send nhưng trước mark-published**, cùng outbox event có thể bị gửi lại. Receiver downstream vẫn cần dedupe theo durable event ID.

Outbox không tạo global exactly-once; nó giúp **không mất intent publish** sau local business commit. Nếu cần ordering cho một payment, thêm aggregate version/sequence và chính sách partition theo key.

## 24. ACK, requeue và DLQ phải căn theo durable state

Adapter Kafka/AMQP/JMS có ACK modes và error handler khác nhau; không có một dòng `ack()` dùng đúng cho tất cả.

| Outcome | Hành động thường xem xét |
|---|---|
| `PROCESSED` + transaction committed | ACK |
| `DUPLICATE_SUCCEEDED` + fingerprint khớp | ACK hoặc trả cached response |
| Transient failure trước commit | Retry bounded, nack/requeue có backoff |
| `PROCESSING` do worker khác giữ | Defer có giới hạn, tránh retry nóng |
| Permanent validation/authorization error | Quarantine/DLQ, ACK theo contract |
| `UNKNOWN_OUTCOME` | Ghi durable reconciliation intent; ACK chỉ khi trách nhiệm đã được chuyển bền vững |

**Không ACK vô điều kiện khi handler trả exception** nếu điều đó khiến message không còn nguồn để phục hồi. Nhưng cũng không requeue vô hạn message có dữ liệu sai hoặc conflict vĩnh viễn.

Nếu workflow được chuyển cho một durable coordinator, ACK khi đã ghi durable intent có thể hợp lệ ngay cả khi side effect chưa hoàn tất; cần định nghĩa rõ đây là **async accepted**, không phải `SUCCEEDED`.

## 25. Error channel và ranh giới bất đồng bộ

Một handler gọi từ `DirectChannel` có thể ném exception về caller. Với `ExecutorChannel`, poller hoặc broker listener, exception có thể xảy ra **sau khi upstream `send()` trả về**:

~~~mermaid
flowchart TD
    IN["Input"] --> B{"Execution boundary"}
    B -->|"Synchronous"| H1["Handler trên caller thread"]
    B -->|"Asynchronous"| H2["Handler trên worker thread"]
    H1 -->|"Exception"| E1["Caller / Retry advice"]
    H2 -->|"Exception"| E2["Error channel / container recoverer"]
    H1 -->|"Commit"| OK1["Reply / ACK policy"]
    H2 -->|"Commit"| OK2["Async terminal state / ACK"]
~~~

Để xử lý đúng lỗi:

1. Xác định RetryAdvice có **bọc đúng handler ném exception** không.
2. Kiểm tra error handler/container có nhận `failedMessage` và business idempotency key không.
3. Đảm bảo lỗi cập nhật/rollback inbox theo state transition cho phép.
4. Phân biệt failure outcome sẽ gửi tới Gateway/Aggregator với lỗi hạ tầng làm retry.
5. Bảo đảm ACK/DLQ không vô tình xóa công việc còn đang ở `PROCESSING`.

**Error channel không tự động xóa một marker SEEN hoặc hoàn tất inbox record.** Cần component có trách nhiệm và transaction/recovery policy rõ.

## 26. Retry exhausted: không trả thành công giả để dừng vòng lặp

~~~text
EV-901:
  Attempt 1 → DB timeout
  Attempt 2 → DB timeout
  Attempt 3 → DB timeout
  → RETRY_EXHAUSTED
~~~

Sau khi hết attempts:

- Ghi lỗi có cấu trúc và state `FAILED_RETRYABLE`/`UNKNOWN_OUTCOME` theo sự thật.
- Release claim hoặc hết lease **có điều kiện**, không xóa marker vô trách nhiệm.
- Lưu message vào DLQ/queue retry lâu hơn nếu hợp đồng cho phép.
- Đặt owner, deadline và cách replay an toàn.
- Nếu Gateway cần reply, trả infrastructure failure/pending thay vì `SUCCESS`.

Không catch exception rồi trả một success result chỉ để message được ACK. Việc đó có thể làm marker được commit trong khi business chưa hoàn tất.

## 27. Splitter và Aggregator: một child thất bại có thể làm group chờ mãi

~~~text
Batch B-101 → Splitter → L1, L2, L3
L1 → SUCCESS
L2 → handler throws → retry / idempotent check
L3 → SUCCESS
               ↓
            Aggregator
~~~

Nếu Idempotent Receiver gắn marker cho L2 trước xử lý rồi chặn retry, Aggregator chỉ thấy hai outcomes. Hệ thống phải phân biệt:

- **Parent correlation** như `batchId`/`processingGroupId`.
- **Member ID** như `lineId`.
- **Idempotency operation key** như `(tenant,batch,revision,lineId,operation)`.
- **Attempt ID** chỉ cho tracing.

Không dùng một idempotency key chung cho mọi child của batch, nếu không child thứ hai sẽ bị coi là duplicate của child thứ nhất.

Khi một member hết khả năng retry, có thể phát `LineOutcome(success=false, reasonCode=...)` mang **cùng correlation/member ID**, cho Aggregator kết luận `PARTIAL/FAILED`. Nhưng nếu member còn retry được, cần policy ngăn failure terminal cũ và success muộn làm group xuất hiện hai outcomes trái nhau.

**Release bằng `group.size()==N` chưa đủ** nếu duplicate L1 được đếm hai lần; cần distinct member IDs và manifest của group.

## 28. Gateway timeout không hủy operation đang chạy

~~~text
Gateway.submitPayment()
  → handler đang xử lý
  → caller timeout sau 2 giây
  → handler có thể commit ở giây thứ 3
~~~

Nếu caller thấy timeout và tạo **eventId mới** cho cùng thao tác, receiver có thể hiểu là một operation mới rồi thực thi hai lần. Với cùng một logical request, caller nên dùng **cùng idempotency key**.

Các trạng thái phù hợp cho request–reply:

- `SUCCEEDED` → có thể trả lại cached result.
- `PROCESSING` → trả PENDING/202 hoặc cung cấp status endpoint theo contract.
- `UNKNOWN_OUTCOME` → reconciliation; không báo thất bại chắc chắn.
- `FAILED_PERMANENT` → trả business failure rõ ràng.

`replyChannel` là return address của một invocation, **không phải business idempotency ID**. Nó có thể thay đổi giữa retry hoặc không thể serialize qua broker.

## 29. Router, Transformer, Content Enricher và retry

| Endpoint | Nguy cơ | Cần thiết kế |
|---|---|---|
| Router | Policy đổi khiến replay vào nhánh khác | Pin route/policy version nếu cần deterministic replay |
| Filter | Drop một child rồi Aggregator thiếu outcome | Reject/failure message có correlation |
| Transformer | Tạo Message mới, mất eventId | Giữ stable business key trong payload/header |
| Content Enricher | Lookup request lặp hoặc reply gắn nhầm | Child request ID + parent correlation |
| Splitter | Replay phát lại N children | Key idempotency riêng cho từng child |
| Aggregator | Duplicate làm đủ count giả/double release | Manifest, unique members, completed-group policy |
| Gateway | Timeout rồi caller retry với key mới | Stable client request ID |

**Đừng dựa vào `MessageHeaders.ID`** khi có Transformer dựng Spring Message mới hoặc broker redelivery. Khi cần truyền qua transport, dùng business identity theo contract, có tenant scope và schema version.

## 30. Metadata store bị mất kết nối: fail-open có thể gây lặp side effect

Khi `ConcurrentMetadataStore` không đọc/ghi được, cách nguy hiểm là:

~~~java
try {
    dedupeStore.claim(key);
} catch (StoreUnavailableException failure) {
    handler.process(event); // Không kiểm tra trùng!
}
~~~

Nếu nhiều consumers nhận cùng message, họ có thể chạy song song và double charge.

Chính sách an toàn:

- **Fail-closed/defer** cho đến khi store phục hồi, với backoff/deadline.
- Chuyển sang durable queue có quota để retry sau.
- Hoặc để domain database uniqueness constraint đảm nhận idempotency nếu đã kiểm chứng đủ mạnh.

Không thay distributed idempotency store bằng một in-memory map riêng trên mỗi node khi multiple nodes cùng nhận redelivery và không có bảo vệ ở side effect.

## 31. TTL và retention của idempotency key

Key `SUCCEEDED` nên được giữ theo:

1. Broker redelivery/replay window.
2. Thời gian producer có thể retry cùng request ID.
3. Retention của remote provider idempotency key.
4. Yêu cầu audit và nghiệp vụ.

TTL quá ngắn: duplicate cũ tới sau expiry và được xử lý lại. TTL vô hạn: store phình to và một key được tái sử dụng có thể chặn operation mới hợp lệ.

Các state cần retention khác nhau: `PROCESSING` dùng **lease + recovery**, `UNKNOWN_OUTCOME` cần **reconciliation**, `SUCCEEDED` giữ tombstone trong cửa sổ chống replay, `FAILED_PERMANENT` có thể cần audit dài hơn.

**Không dùng TTL như một bằng chứng “handler đã ngừng chạy”.** Một worker bị pause có thể tiếp tục sau khi lease hết hạn; fencing và remote idempotency mới giải quyết cạnh tranh.

## 32. Test rollback sau handler failure

Một integration test với database thật:

~~~java
@Test
void exceptionBeforeCommitDoesNotPoisonRetry() {
    PaymentEvent event = sampleEvent("EV-901");
    ledger.failNextUpdate();

    assertThrows(TransientDataAccessException.class,
        () -> receiver.process(event));

    assertFalse(inbox.existsCommitted(
        event.tenantId(), event.eventId(), event.operation()));
    assertEquals(0, ledger.countFor(event.eventId()));

    assertEquals(ReceiveOutcome.PROCESSED,
        receiver.process(event));
    assertEquals(1, ledger.countFor(event.eventId()));
    assertEquals(1, outbox.countFor(event.eventId()));

    assertEquals(ReceiveOutcome.DUPLICATE,
        receiver.process(event));
    assertEquals(1, ledger.countFor(event.eventId()));
}
~~~

`sampleEvent`, `failNextUpdate` và repository test methods là **test fixtures do ứng dụng tự định nghĩa**. Dùng test DB/transaction manager thật hoặc Testcontainers để kiểm tra rollback; mock Java không chứng minh marker và ledger cùng transaction.

**Cẩn thận:** nếu cả test method được bao `@Transactional`, các lần gọi có thể nằm trong cùng transaction thử nghiệm và che giấu commit/rollback thực tế. Tách transaction boundaries như production.

## 33. Test crash sau commit nhưng trước broker ACK

Kịch bản:

~~~text
Attempt #1:
  processed_event + ledger + outbox COMMIT
  giả lập crash trước ACK

Attempt #2:
  redelivery cùng eventId, Spring Message ID khác
  receiver trả DUPLICATE
  ledger count không đổi
~~~

Xác minh:

- Inbox marker và ledger vẫn tồn tại sau restart.
- Same key + same fingerprint là duplicate an toàn.
- Same key + different fingerprint là conflict.
- Outbox record tồn tại để publisher tiếp tục gửi.
- Broker ack/redelivery không làm business mutation lần hai.

Chỉ gọi receiver hai lần chưa chứng minh ACK behavior. Để test adapter thật, dùng broker/container và inject crash tại boundary thích hợp.

## 34. Test concurrency và lease/fencing

Để lộ race condition, dùng `CountDownLatch` hoặc barrier cho hai workers:

~~~text
W1: INSERT EV-901 → pending
W2: INSERT EV-901 → conflict / wait
W1: UPDATE ledger + COMMIT
W2: phát hiện duplicate completed

Expected:
  inbox committed rows = 1
  ledger entries       = 1
  outbox intents       = 1
~~~

Một test khác cho state machine:

~~~text
W1 claim token 8 → lease expires
W2 reclaim token 9 → COMMIT
W1 mark SUCCEEDED(token 8) → affected rows = 0
~~~

Kiểm thử với transaction/unique constraint thật. Test tuần tự hai lần không phơi bày race. Với remote side effect, bổ sung test cùng idempotency key khi cả hai worker cùng gọi provider.

## 35. Test remote timeout và unknown outcome

Fake provider:

~~~text
POST /capture idempotencyKey=K
  → provider commits capture
  → client không nhận response
  → timeout

Retry POST /capture idempotencyKey=K
  → provider trả kết quả cũ
  → tổng số captures = 1
~~~

Kỳ vọng:

1. Không sinh K mới cho retry cùng logical operation.
2. `UNKNOWN_OUTCOME` được reconcile rồi chuyển terminal state.
3. Không double charge, kể cả khi response lần đầu mất.
4. Conflicting payload cùng K bị từ chối.
5. Nếu provider không hỗ trợ idempotency, không tự retry lệnh capture nguy hiểm mà thiếu giao thức xác minh.

## 36. Ma trận kiểm thử end-to-end

| Test case | Fault injection | Điều chứng minh |
|---|---|---|
| Happy path | Không lỗi | Một marker, một side effect, một outbox intent |
| Pre-claim failure | Store không ghi được | Không mất message |
| After marker/before commit | Ledger ném exception | Marker rollback hoặc retryable state |
| After commit/before ACK | Crash | Redelivery không double mutation |
| Same key/different content | Fingerprint khác | Conflict/quarantine |
| Retry exhausted | Tất cả attempts lỗi | Không success giả hoặc stuck marker |
| Redis marker độc lập | DB rollback | Phát hiện và tránh poisoned marker |
| Concurrent duplicate | Hai workers | Unique owner/commit |
| Lease expiry | Worker cũ tỉnh dậy | Fencing từ chối stale completion |
| Remote timeout | Provider đã commit | Reconcile với cùng remote key |
| Broker redelivery | Spring Message ID mới | Business key ổn định |
| Splitter child retry | Một line thất bại | Không chặn các member khác |
| Aggregator release | Duplicate result | Không đếm duplicate thành member mới |
| Gateway timeout | Caller retry cùng key | Không tạo operation mới |
| Async error | Worker ném exception | Error path giữ correlation |
| Store unavailable | Dedupe backend down | Không fail-open nguy hiểm |
| Restart | App bị kill | Recovery theo durable state |
| Late reply | Reply sau completed | Không double publish |
| TTL expiry | Replay ngoài window | Hợp đồng retention/replay rõ |

**Đặc biệt:** với `IdempotentReceiverInterceptor`, test trực tiếp duplicate header, discard/exception/reply, thứ tự advice và lúc metadata được commit. Không suy ra semantics từ tên interceptor.

## 37. Observability: phát hiện “retry có chạy nhưng handler không chạy”

| Metric gợi ý | Công dụng |
|---|---|
| `receiver.message.received.count` | Số messages và attempts tới |
| `receiver.idempotency.claim.count` | Số claim mới |
| `receiver.idempotency.duplicate.count` | Số duplicate |
| `receiver.idempotency.conflict.count` | Key trùng nhưng payload khác |
| `receiver.inbox.processing.count` | In-flight operations |
| `receiver.handler.failure.count` | Lỗi business handler |
| `receiver.retry.attempts.count` | Retry amplification |
| `receiver.retry.exhausted.count` | Operations không tự hồi phục |
| `receiver.unknown.outcome.count` | Side effect ngoài chưa rõ |
| `receiver.lease.expired.count` | Leases quá hạn |
| `receiver.fencing.rejected.count` | Stale worker cập nhật state |
| `receiver.business.committed.count` | Business commits thực |
| `receiver.outbox.pending.count` | Intent chưa publish |
| `receiver.ack.failure.count` | Transport redelivery risk |
| `receiver.inbox.state.age` | Operations treo trong state |

Đây là **metric đề xuất**, không phải các meter mặc định của Spring Integration. Tag nên có cardinality thấp như `flow`, `operation`, `outcome`, `reasonCode`; không dùng `eventId/paymentId/idempotencyKey` làm metric tag động.

Structured logs/tracing có kiểm soát:

~~~text
eventId=EV-901
operation=CAPTURE
attempt=2
inboxState=FAILED_RETRYABLE
handlerPhase=BEFORE_COMMIT
transactionOutcome=ROLLED_BACK
brokerRedelivery=true
reasonCode=DB_DEADLOCK
~~~

Mục tiêu: trả lời được **marker đã commit chưa, side effect đã commit chưa, ai giữ lease, và ai quyết định ACK/retry**. Không log raw payment data, credentials hoặc idempotency token bí mật.

## 38. Runbook khi message bị coi là duplicate nhưng chưa hoàn tất

1. **Xác định logical key** từ tenant/event/operation/revision có kiểm chứng.
2. **Xem inbox/metadata:** trạng thái `SEEN`, `PROCESSING` hay `SUCCEEDED` thực tế?
3. **Đối chiếu sổ cái:** side effect và outbox record đã commit chưa?
4. **Xem transaction:** marker có nằm trong cùng transaction với handler không?
5. **Xem advice chain:** RetryAdvice đang trong hay ngoài IdempotentAdvice?
6. **Xem error path:** lỗi xảy ra trước commit, sau commit, hay ở remote API?
7. **Xem ACK/DLQ:** message có bị ACK khi chưa durable hay bị requeue vô hạn?
8. **Xem lock/lease:** worker khác đang giữ hay lease đã hết hạn?
9. **Reconcile external outcome** nếu API timeout nhưng chưa biết đã commit chưa.
10. **Khôi phục có điều kiện:** retry khi chắc chắn chưa có effect hoặc dùng cùng remote key; nếu đã commit thì complete/cached reply.
11. **Kiểm tra pending Aggregator groups** nếu message này là một child kết quả.
12. **Thêm regression test** tái hiện đúng failure window.

**Không xóa mọi Redis metadata key rồi replay toàn bộ**. Các key khác có thể bảo vệ những operation đã commit; xóa bừa bãi tạo rủi ro duplicate charge hoặc double event.

## 39. Bài thực hành: ba cách xử lý retry sau handler failure

Xây ứng dụng **PaymentEventReceiver** với ba phiên bản:

1. **Cố tình sai:** dùng metadata store `seen(eventId)` tách rời DB, inject exception sau marker; quan sát lần retry bị coi duplicate.
2. **Transactional:** dùng `processed_event + payment_ledger + outbox_event` trong một transaction; lỗi trước commit rollback tất cả.
3. **External operation:** dùng inbox state/lease/fencing, remote idempotency key và reconciliation.

Sau đó:

4. Gắn `RequestHandlerRetryAdvice` với ba attempts vào flow thích hợp.
5. Thử hai thứ tự advice cùng IdempotentReceiverInterceptor; đếm selector và handler invocations.
6. Dùng PostgreSQL/Testcontainers để kiểm tra constraint và rollback.
7. Inject lỗi **sau marker, trước ledger**, **sau ledger, trước COMMIT**, **sau COMMIT, trước ACK**.
8. Tạo hai message cùng key nhưng khác payload để kiểm tra conflict.
9. Gửi đồng thời hai bản cùng event, dùng latch/barrier.
10. Test lease timeout và worker cũ bị fencing.
11. Mô phỏng remote server đã commit nhưng response mất.
12. Thử broker redelivery khi Spring Message ID đổi.
13. Kết nối Splitter/Aggregator và tạo failure outcome cho một child.
14. Làm dashboard retry, duplicate, inbox state age, remote unknown và outbox backlog.

**Tiêu chí hoàn thành:** retry sau lỗi trước commit **không bị marker chặn sai**; redelivery sau commit **không lặp side effect**; payload conflict bị phát hiện; remote timeout được reconcile; không có claim treo vô hạn; mọi trạng thái ACK/DLQ có thể truy vết.

## 40. Những hiểu lầm thường gặp

**“Đã thấy message nghĩa là đã xử lý thành công.”** Sai. Claim và commit khác nhau.

**“IdempotentReceiverInterceptor mặc định rollback marker khi handler lỗi.”** Không nên giả định; phụ thuộc selector, metadata store và transaction.

**“Chỉ đổi thứ tự RetryAdvice và IdempotentAdvice là đủ.”** Không nếu marker tồn tại sau exhausted retries hoặc broker redelivery.

**“Redis marker tự rollback bởi `@Transactional` của JDBC handler.”** Không nếu hai hệ thống không tham gia cùng transaction.

**“Catch exception rồi return success sẽ giúp retry an toàn.”** Có thể commit marker nhưng bỏ công việc.

**“Duplicate luôn phải ném exception.”** Không. Duplicate `SUCCEEDED` có thể ACK/return cached; duplicate `PROCESSING` cần defer.

**“HTTP timeout nghĩa là remote chưa commit.”** Sai; outcome có thể chưa biết.

**“Mỗi retry dùng UUID mới sẽ an toàn hơn.”** Sai nếu UUID là remote/business idempotency key.

**“Gateway timeout sẽ tự hủy handler.”** Không tự động.

**“Inbox unique constraint tự bảo đảm exactly-once cho HTTP capture.”** Không; remote cần idempotency/reconciliation riêng.

**“Outbox khiến broker không bao giờ nhận duplicate.”** Sai; publisher có thể phát lại.

**“ACK broker nghĩa là payment đã thành công.”** Không nhất thiết: ACK có thể chỉ xác nhận trách nhiệm được lưu bền vững.

**“TTL ngắn luôn tiết kiệm và an toàn.”** Sai nếu có redelivery sau TTL.

**“Một map in-memory mỗi JVM đủ cho cả cluster.”** Không nếu nhiều consumers có thể xử lý cùng key.

**“Mọi exception đều retry vô hạn.”** Sai; lỗi permanent, authorization và key conflict cần terminal policy.

## 41. Ghi nhớ

Khi handler thất bại, **Idempotent Receiver không được dùng dấu “đã nhận” như bằng chứng “đã hoàn tất”**. Nếu metadata key được ghi trước handler rồi vẫn tồn tại sau rollback, retry có thể bị chặn mặc dù công việc chưa thành công. Nếu business đã commit trước ACK, redelivery lại phải được ngăn lặp side effect.

Với thao tác trong **một database**, ưu tiên **atomic transaction** cho marker, business mutation và outbox. Với external operations, cần **inbox state machine, atomic claim, lease/fencing, remote idempotency key và reconciliation**. Thứ tự `IdempotentReceiverInterceptor` và `RequestHandlerRetryAdvice` phải được kiểm thử, nhưng **không thay thế một giao thức commit đúng**.

Giữ business key bền vững qua Router, Filter, Transformer, Splitter, Gateway và broker; tách key của group/member với attempt ID; xử lý lỗi theo sync/async boundary và ACK/retry policy. Mục tiêu là **retry đúng phần chưa hoàn tất, nhận ra phần đã commit, và không làm mất hoặc nhân đôi công việc**.

### Tài liệu tham khảo

- Spring Integration Reference, **Idempotent Receiver**: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Integration Reference, **Retry Advice**: https://docs.spring.io/spring-integration/reference/handler-advice/classes.html
- Spring Integration Reference, **Metadata Store**: https://docs.spring.io/spring-integration/reference/metadata-store.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Enterprise Integration Patterns, **Idempotent Receiver**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html
